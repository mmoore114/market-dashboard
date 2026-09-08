"""Synthetic local publications; no fixture production relabeling."""

from datetime import UTC, date, datetime, time, timedelta

import pandas as pd

from market_dashboard.aperture.contracts import UniverseMembership, UniverseMemberships
from market_dashboard.aperture.leadership_contracts import (
    DatedProvenanceV1,
    ResearchUniverseV1,
    StrengthSourceV1,
)
from market_dashboard.aperture.regime_contracts import SpotVolatilityIdentityV1
from market_dashboard.workstation.materialization.audit import (
    count_rows,
    date_bounds,
    logical,
    rules,
)
from market_dashboard.workstation.materialization.contracts import (
    ArtifactV1,
    CalendarV1,
    ManifestV1,
    MaterializationPlanV1,
    MemberV1,
    SourceBindingV1,
    UniverseScheduleV1,
    UniverseSliceV1,
)
from market_dashboard.workstation.materialization.io import file_hash
from market_dashboard.workstation.models import VersionsV1


def synthetic_plan(tmp_path, n=30, symbols=("AAA", "BBB"), start=date(2024, 1, 1)):
    source_dir = tmp_path / "inputs"
    source_dir.mkdir()
    workspace = tmp_path / "output"
    sessions = tuple(start + timedelta(days=i) for i in range(n + 5))
    # Explicit fictional daily exchange for test only, not a generated production calendar.
    closes = tuple(datetime.combine(d, time(20), tzinfo=UTC) for d in sessions)
    t = sessions[n - 1]
    calendar = CalendarV1(
        calendar_id="synthetic-daily-v1",
        version="synthetic-calendar-v1",
        sessions=sessions,
        closes=closes,
    )
    yes = UniverseMembership(
        eligible=True,
        membership_mode="strict",
        reason_codes=("SYNTHETIC",),
        reasons=("Synthetic membership",),
    )
    membership = UniverseMemberships(
        market_mapping=yes, equity_research=yes, equity_trade=yes
    )
    provenance = DatedProvenanceV1(
        snapshot_id="synthetic-universe-v1",
        version="synthetic-membership-v1",
        source_as_of_date=sessions[0],
        known_session=sessions[0],
        effective_session=sessions[0],
        valid_through=sessions[-1],
    )
    universe = UniverseScheduleV1(
        snapshots=(
            UniverseSliceV1(
                universe=ResearchUniverseV1(
                    provenance=provenance,
                    policy_version=rules().universe_policy_version,
                    symbols=symbols,
                ),
                members=tuple(
                    MemberV1(symbol=s, memberships=membership) for s in symbols
                ),
                security_master_version="synthetic-master-v1",
                exposure_policy_version="exposure-policy-v3",
                rules_fingerprint=rules().logical_fingerprint,
            ),
        )
    )
    tickers = (*symbols, "SPY", "QQQ", "IWM", "RSP", "QQQE")
    master = pd.DataFrame(
        [
            {"ticker": s, "name": "Synthetic " + s, "snapshot_date": sessions[0]}
            for s in tickers
        ]
    )
    exposure = pd.DataFrame(
        [
            {
                "ticker": s,
                "snapshot_date": sessions[0],
                "policy_version": "exposure-policy-v3",
                "exposure_scope": "direct_equity" if s in symbols else "diversified",
            }
            for s in tickers
        ]
    )
    bars = pd.DataFrame(
        [
            {
                "ticker": s,
                "date": d,
                "open": 100 + i * 0.1,
                "high": 102 + i * 0.1,
                "low": 98 + i * 0.1,
                "close": 100 + i * 0.1,
                "volume": 1000000.0,
            }
            for s in tickers
            for i, d in enumerate(sessions[:n])
        ]
    )
    spot = pd.DataFrame(
        [{"series_id": "SYNTHETIC_VIX", "date": d, "close": 18.0} for d in sessions[:n]]
    )
    values = {
        "calendar": calendar,
        "universe": universe,
        "security_master": master,
        "exposure": exposure,
        "bars": bars,
        "spot": spot,
    }
    artifacts, bindings = [], []
    for role, value in values.items():
        path = source_dir / (
            role + (".parquet" if isinstance(value, pd.DataFrame) else ".json")
        )
        if isinstance(value, pd.DataFrame):
            value.to_parquet(path, index=False)
        else:
            path.write_text(value.model_dump_json())
        version = {
            "calendar": calendar.version,
            "security_master": "synthetic-master-v1",
            "exposure": "exposure-policy-v3",
            "universe": rules().universe_policy_version,
        }.get(role, "synthetic-" + role + "-v1")
        artifacts.append(
            ArtifactV1(
                role=role,
                version=version,
                paths=(path,),
                format="parquet" if isinstance(value, pd.DataFrame) else "json",
            )
        )
        # Fingerprints use the exact reader representation (Parquet date precision).
        readback = pd.read_parquet(path) if isinstance(value, pd.DataFrame) else value
        first, last = date_bounds(readback)
        bindings.append(
            SourceBindingV1(
                role=role,
                version=version,
                artifact_hashes=(file_hash(path),),
                row_count=count_rows(readback),
                first_date=first,
                last_date=last,
                publication_state="complete",
                observed_at=closes[n - 1],
                fetched_at=closes[n - 1],
                published_at=closes[n - 1],
                valid_from=sessions[0],
                valid_through=sessions[-1],
                fresh_until=closes[n],
                security_master_version="synthetic-master-v1",
                exposure_policy_version="exposure-policy-v3",
                universe_policy_version=rules().universe_policy_version,
                logical_fingerprint=logical(readback),
            )
        )
    manifest = ManifestV1(
        version="synthetic-manifest-v1",
        source=StrengthSourceV1(
            data_vendor="synthetic",
            dataset_id="synthetic-adjusted-v1",
            price_basis="split_adjusted",
            dividend_treatment="no-dividends",
            volume_convention="split-adjusted-shares",
            calendar_id=calendar.calendar_id,
        ),
        matching_split_adjusted_volume=True,
        calendar_sha256=file_hash(source_dir / "calendar.json"),
        volatility_identity=SpotVolatilityIdentityV1(
            source_symbol="SYNTHETIC_VIX",
            data_vendor="synthetic",
            dataset_id="synthetic-spot-v1",
            equivalence_evidence="Synthetic spot points only",
        ),
        bindings=tuple(bindings),
    )
    manifest_path = source_dir / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json())
    artifacts.append(
        ArtifactV1(
            role="manifest",
            version=manifest.version,
            paths=(manifest_path,),
            format="json",
        )
    )
    plan = MaterializationPlanV1(
        artifacts=tuple(artifacts),
        workspace=workspace,
        output=workspace / "review.json",
        as_of_session=t,
        action_session=sessions[n],
        freshness_deadline=closes[n],
        versions=VersionsV1.v1(security_master="synthetic-master-v1"),
    )
    return plan


def reseal(plan, role):
    """Model a separately supplied new synthetic publication after a test mutation."""
    from market_dashboard.workstation.materialization.audit import JSON_MODELS

    a = next(a for a in plan.artifacts if a.role == role)
    mp = next(a.paths[0] for a in plan.artifacts if a.role == "manifest")
    manifest = ManifestV1.model_validate_json(mp.read_text())
    value = (
        pd.read_parquet(a.paths[0])
        if a.format == "parquet"
        else JSON_MODELS[role].model_validate_json(a.paths[0].read_text())
    )
    first, last = date_bounds(value)
    bindings = tuple(
        b.model_copy(
            update={
                "artifact_hashes": (file_hash(a.paths[0]),),
                "logical_fingerprint": logical(value),
                "row_count": count_rows(value),
                "first_date": first,
                "last_date": last,
            }
        )
        if b.role == role
        else b
        for b in manifest.bindings
    )
    updates = {"bindings": bindings}
    if role == "calendar":
        updates["calendar_sha256"] = file_hash(a.paths[0])
    mp.write_text(manifest.model_copy(update=updates).model_dump_json())


def attach(plan, role, value):
    from market_dashboard.workstation.materialization.contracts import (
        ArtifactV1,
        SourceBindingV1,
    )

    path = plan.artifacts[0].paths[0].parent / (role + ".json")
    path.write_text(value.model_dump_json())
    mp = next(a.paths[0] for a in plan.artifacts if a.role == "manifest")
    manifest = ManifestV1.model_validate_json(mp.read_text())
    template = manifest.bindings[0]
    first, last = date_bounds(value)
    binding = SourceBindingV1(
        **{
            **template.model_dump(),
            "role": role,
            "version": "synthetic-" + role + "-v1",
            "artifact_hashes": (file_hash(path),),
            "row_count": count_rows(value),
            "first_date": first,
            "last_date": last,
            "logical_fingerprint": logical(value),
        }
    )
    mp.write_text(
        manifest.model_copy(
            update={"bindings": (*manifest.bindings, binding)}
        ).model_dump_json()
    )
    return plan.model_copy(
        update={
            "artifacts": (
                *plan.artifacts,
                ArtifactV1(
                    role=role, version=binding.version, paths=(path,), format="json"
                ),
            )
        }
    )
