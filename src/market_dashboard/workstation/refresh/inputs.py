"""Bounded daily input generations using existing acquisition/population pipelines."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd

from market_dashboard.data.current_population import build_action_population
from market_dashboard.data.current_publication import publish_bars
from market_dashboard.features.equity_features import EquityFeaturePipeline
from market_dashboard.workstation.materialization.bootstrap import verify_hashes
from market_dashboard.workstation.materialization.comparison import load_verified
from market_dashboard.workstation.materialization.sparse import sparse_history
from market_dashboard.workstation.materialization.xnys_calendar import generate_xnys
from market_dashboard.workstation.models import EvaluationV1, InputClockBindingV1

from .acquire import acquire_job
from .operations import digest


def prepare(config, run, window, *, api_key=None):
    seed, loaded, _baseline, hashes = load_verified(
        config["seed_workspace"], config["seed_snapshot"]
    )
    root = Path(config["workspace"])
    run = Path(run)
    # Only the fixed verified initial population and benchmark set are acquired.
    source_bars = loaded["bars"].copy()
    manifest_paths = list(dict(loaded["manifest"].artifact_hashes))

    def one(suffix):
        found = [Path(p) for p in manifest_paths if p.endswith(suffix)]
        if len(found) != 1:
            raise ValueError("EXACT_SEED_INPUT_REQUIRED")
        return found[0]

    reference = pd.read_parquet(one("reference-current-v1.parquet"))
    exposure = pd.read_parquet(one("security_exposure_classification.parquet"))
    calendar = generate_xnys(loaded["calendar"].sessions[0], window["action"])
    loaded["calendar"] = calendar
    previous = root / "last-inputs.json"
    if previous.exists():
        receipt = json.loads(previous.read_text())
        verify_hashes(receipt["hashes"])
        source_bars = pd.read_parquet(receipt["bars"])
    source_bars["date"] = pd.to_datetime(source_bars.date)
    if set(source_bars.ticker) != set(loaded["bars"].ticker):
        raise ValueError("UNIVERSE_EXPANSION_REFUSED")
    jobs = []
    acquisition = []
    for symbol, frame in source_bars.groupby("ticker", sort=True):
        missing = [
            str(d)
            for d in calendar.sessions
            if frame.date.max().date() < d <= window["market"]
        ]
        if missing:
            jobs.append((symbol, [str(frame.date.max().date()), *missing]))
    additions = []
    for symbol, days in jobs:
        rows, path = acquire_job(
            root,
            "bars",
            {"ticker": symbol, "start": days[0], "end": days[-1]},
            days,
            api_key=api_key,
        )
        prior = source_bars[
            (source_bars.ticker == symbol)
            & (source_bars.date.dt.date == pd.Timestamp(days[0]).date())
        ].iloc[0]
        overlap = rows[0]
        if any(
            float(prior[k]) != float(overlap[k])
            for k in ("open", "high", "low", "close", "volume")
        ):
            raise ValueError("CORRECTED_HISTORY_REPLAY_REQUIRED")
        for row in rows[1:]:
            row["ingested_at"] = datetime.now(UTC).replace(tzinfo=None)
        additions.extend(rows[1:])
        acquisition.append(path)
    bars = source_bars
    if additions:
        newer = pd.DataFrame(additions)
        newer["date"] = pd.to_datetime(newer.date)
        newer = newer.reindex(columns=bars.columns)
        bars = pd.concat([bars, newer], ignore_index=True).sort_values(
            ["ticker", "date"]
        )
    for symbol, frame in bars.groupby("ticker"):
        if frame.date.max().date() != window["market"]:
            raise ValueError("LATEST_COMPLETED_BAR_MISSING")
    spot = loaded["spot"].copy()
    spot["date"] = pd.to_datetime(spot.date)
    if previous.exists() and receipt.get("spot"):
        spot = pd.read_parquet(receipt["spot"])
        spot["date"] = pd.to_datetime(spot.date)
    missing_inputs = []
    if spot.date.max().date() < window["market"]:
        try:
            days = [
                str(d)
                for d in calendar.sessions
                if spot.date.max().date() <= d <= window["market"]
            ]
            rows, path = acquire_job(
                root,
                "spot",
                {"ticker": "VIXCLS", "start": days[0], "end": days[-1]},
                days,
            )
            acquisition.append(path)
            observed = pd.DataFrame(rows)
            observed["date"] = pd.to_datetime(observed.date)
            # Nontrading FRED rows and explicit missing publication values are not bars.
            observed = observed[
                observed.date.dt.date.isin(calendar.sessions) & observed.close.notna()
            ]
            for column in spot.columns:
                if column not in observed:
                    values = spot[column].dropna().unique()
                    if len(values) != 1:
                        raise ValueError("SPOT_METADATA_AMBIGUOUS")
                    observed[column] = values[0]
            spot = (
                pd.concat([spot, observed[spot.columns]])
                .drop_duplicates(["series_id", "date"], keep="last")
                .sort_values("date")
            )
        except ValueError as e:
            missing_inputs.append(str(e))
    if not ((spot.date.dt.date == window["market"]) & spot.close.notna()).any():
        missing_inputs.append("VIX_COMPLETED_SESSION_UNPUBLISHED_VOLATILITY_UNKNOWN")
    # Decision controls are action-scoped, not advanced by a UTC midnight.
    if window["action"] != seed.action_session:
        rows = []
        for symbol in sorted(reference.ticker):
            items, path = acquire_job(
                root,
                "reference",
                {
                    "ticker": symbol,
                    "start": str(window["market"]),
                    "end": str(window["market"]),
                },
                [],
                api_key=api_key,
            )
            rows.extend(items)
            acquisition.append(path)
        reference = pd.DataFrame(rows)
        master = loaded["security_master"].copy().set_index("ticker")
        for row in reference.to_dict("records"):
            if row.get("type") != master.loc[row["ticker"], "security_type"]:
                raise ValueError("INSTRUMENT_CLASSIFICATION_REBUILD_REQUIRED")
            for field in ("active", "locale", "primary_exchange"):
                if row.get(field) is None:
                    raise ValueError("CURRENT_REFERENCE_CONTROL_MISSING")
                master.loc[row["ticker"], field] = row[field]
        loaded["security_master"] = master.reset_index()
    now = datetime.now(UTC)
    features = EquityFeaturePipeline().calculate_features(bars)
    latest = features[features.date == window["market"]]
    symbols = tuple(m.symbol for m in loaded["universe"].snapshots[0].members)
    prior_trade_members = {
        m.symbol
        for m in loaded["universe"].snapshots[0].members
        if m.memberships.equity_trade.eligible
    }
    if previous.exists() and receipt.get("population"):
        from market_dashboard.workstation.materialization.contracts import (
            UniverseScheduleV1,
        )

        prior_population = UniverseScheduleV1.model_validate_json(
            Path(receipt["population"]).read_bytes()
        )
        prior_trade_members = {
            m.symbol
            for m in prior_population.snapshots[0].members
            if m.memberships.equity_trade.eligible
        }
    population = build_action_population(
        loaded["security_master"],
        exposure,
        latest,
        reference,
        symbols,
        market_session=window["market"],
        evaluation=now,
        action_session=window["action"],
        rules=loaded["rules"],
        master_version=seed.versions.security_master,
        action_open=window["opening"],
        prior_trade_members=prior_trade_members,
    )
    if not set(population.snapshots[0].universe.symbols) <= {
        s for s, _ in seed.bootstrap.first_observations
    }:
        raise ValueError("RESEARCH_POPULATION_EXPANSION_REFUSED")
    coverage = [
        sparse_history(bars, s, calendar.sessions, window["market"])[1]
        for s in population.snapshots[0].universe.symbols
    ]
    current = population.snapshots[0]
    boot = seed.bootstrap.model_copy(
        update={
            "market_as_of_session": window["market"],
            "evaluation_timestamp": now,
            "action_session": window["action"],
            "first_observations": tuple(
                (c["symbol"], c["first_observation"]) for c in coverage
            ),
            "covered_population": len(current.members),
            "strict_trade_members": sum(
                m.memberships.equity_trade.eligible for m in current.members
            ),
            "mapping_members": sum(
                m.memberships.market_mapping.eligible for m in current.members
            ),
            "not_yet_observed": sum(c["not_yet_observed"] for c in coverage),
            "missing_observations": sum(c["missing_observations"] for c in coverage),
        }
    )
    current = current.model_copy(
        update={
            "universe": current.universe.model_copy(
                update={
                    "provenance": current.universe.provenance.model_copy(
                        update={"bootstrap": boot}
                    )
                }
            )
        }
    )
    loaded.update(
        bars=bars,
        spot=spot,
        universe=population.model_copy(update={"snapshots": (current,)}),
    )
    paths = {}
    for name, frame in [
        ("bars", bars),
        ("spot", spot),
        ("features", features),
        ("reference", reference),
        ("master", loaded["security_master"]),
    ]:
        p = run / f"{name}.parquet"
        frame.to_parquet(p, index=False)
        readback = pd.read_parquet(p).astype(object)
        expected = frame.reset_index(drop=True).astype(object)
        pd.testing.assert_frame_equal(
            readback.where(pd.notna(readback), None),
            expected.where(pd.notna(expected), None),
            check_dtype=False,
            check_exact=True,
        )
        paths[name] = str(p)
        hashes[str(p)] = digest(p)
    population_path = run / "population.json"
    population_path.write_text(population.model_dump_json())
    paths["population"] = str(population_path)
    hashes[str(population_path)] = digest(population_path)
    if additions:
        # Existing recoverable append-only publisher operates on an isolated copy.
        old_db = run / "local.duckdb"
        shutil.copy2(one("/data/database/market_dashboard.duckdb"), old_db)
        backup = run / "before-publication.duckdb"
        shutil.copy2(old_db, backup)
        assert digest(backup) == digest(old_db)
        with duckdb.connect(str(old_db)) as con:
            con.execute("DELETE FROM current_foundation_publication")
            con.execute("DELETE FROM daily_bars")
            con.register("prior", source_bars)
            con.execute("INSERT INTO daily_bars SELECT * FROM prior")
            con.execute("CHECKPOINT")
        partitions = run / "partitions"
        candidate = run / "candidate"
        partitions.mkdir()
        candidate.mkdir()
        for symbol, frame in source_bars.groupby("ticker"):
            frame.to_parquet(partitions / f"{symbol}.parquet", index=False)
        for symbol, frame in bars.groupby("ticker"):
            frame.to_parquet(candidate / f"{symbol}.parquet", index=False)
        publish_bars(
            old_db,
            partitions,
            candidate,
            run / "publication",
            expected_database_hash=digest(old_db),
        )
        EquityFeaturePipeline(old_db).run()
        paths["database"] = str(old_db)
        hashes[str(old_db)] = digest(old_db)
    for acquisition_path in acquisition:
        for evidence_path in acquisition_path.glob("*.json"):
            hashes[str(evidence_path)] = digest(evidence_path)
    bindings = []
    for name in ("bars", "spot", "features"):
        frame = bars if name != "spot" else spot
        bindings.append(
            InputClockBindingV1(
                name=name,
                role="market_observation",
                observation_date=pd.to_datetime(frame.date).max().date(),
                available_at=now,
                artifact_sha256=hashes[paths[name]],
            )
        )
    for name in ("master", "reference"):
        bindings.append(
            InputClockBindingV1(
                name=name,
                role="decision_control",
                effective_date=window["action"],
                available_at=now,
                artifact_sha256=hashes[paths[name]],
            )
        )
    evaluation = EvaluationV1(
        market_as_of_session=window["market"],
        evaluation_timestamp=now,
        action_session=window["action"],
        population_scope=boot.population_scope,
        bootstrap=boot,
        input_bindings=tuple(bindings),
    )
    seed = seed.model_copy(
        update={
            "as_of_session": window["market"],
            "action_session": window["action"],
            "bootstrap": boot,
            "evaluation": evaluation,
        }
    )
    return seed, loaded, hashes, paths, missing_inputs
