"""Offline copied-volume correction simulation. There is deliberately no apply mode."""

import tempfile
from pathlib import Path
from typing import Literal

import duckdb
from pydantic import Field

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership import fingerprint
from market_dashboard.data.adjusted_authority import AUTHORITY

from .contracts import MaterializationPlanV1
from .io import (
    Refusal,
    artifact_hashes,
    atomic_write,
    file_hash,
    read_table,
    resolve_plan,
    safe_path,
)
from .reconciliation import canonical_dates, compare_copies


class VolumeMigrationPlanV1(ContractModel):
    schema_version: Literal["adjusted-volume-migration-plan-v1"] = (
        "adjusted-volume-migration-plan-v1"
    )
    source_plan: MaterializationPlanV1
    source_hashes: tuple[str, ...] = Field(min_length=2)
    output_name: Literal["authority-volume-simulation.duckdb"] = (
        "authority-volume-simulation.duckdb"
    )
    authority_version: Literal["massive-adjusted-authority-v1"] = AUTHORITY.version


def describe_migration(plan):
    """Pure plan validation: no path stat/resolve, database read or output write."""
    plan = VolumeMigrationPlanV1.model_validate(plan.model_dump())
    w = plan.source_plan.workspace
    if w.name != "workstation-local-snapshot-v1" or w.parent.name != "aperture-staging":
        raise Refusal("MIGRATION_WORKSPACE_REQUIRED")
    bars = next(a for a in plan.source_plan.artifacts if a.role == "bars")
    if bars.format != "duckdb" or bars.table != "daily_bars" or not bars.parquet_copies:
        raise Refusal("EXACT_NATIVE_BAR_COPIES_REQUIRED")
    paths = (w, *bars.paths, *bars.parquet_copies)
    if any(not p.is_absolute() or ".." in p.parts for p in paths):
        raise Refusal("ABSOLUTE_MIGRATION_PATH_REQUIRED")
    if len(plan.source_hashes) != len(bars.paths) + len(bars.parquet_copies) or any(
        len(h) != 64 or set(h) - set("0123456789abcdef") for h in plan.source_hashes
    ):
        raise Refusal("MIGRATION_SOURCE_HASHES_INVALID")
    return {
        "plan": plan.model_dump(mode="json"),
        "plan_fingerprint": fingerprint(plan.model_dump(mode="json")),
        "production_apply_available": False,
    }


def migration_inputs(plan):
    describe_migration(plan)
    resolve_plan(plan.source_plan)
    bars = next(a for a in plan.source_plan.artifacts if a.role == "bars")
    if artifact_hashes(bars, plan.source_plan) != plan.source_hashes:
        raise Refusal("MIGRATION_INPUT_CHANGED")
    with duckdb.connect(
        str(bars.paths[0]), read_only=True, config={"enable_external_access": False}
    ) as con:
        schema = dict(
            con.execute(
                "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='main' AND table_name='daily_bars'"
            ).fetchall()
        )
    if schema.get("volume") != "BIGINT" or schema.get("transactions") != "BIGINT":
        raise Refusal("MIGRATION_EXPECTS_LEGACY_BIGINT_SCHEMA")
    primary, copies = (
        read_table(bars, plan.source_plan),
        read_table(bars, plan.source_plan, copies=True),
    )
    if any(frame[["ticker", "date"]].isna().any().any() for frame in (primary, copies)):
        raise Refusal("MIGRATION_NULL_KEYS")
    diff = compare_copies(primary, copies, ["ticker", "date"])
    if (
        diff["primary"]["duplicate_keys"]
        or diff["copies"]["duplicate_keys"]
        or diff["primary_only_keys"]
        or diff["copies_only_keys"]
        or diff["primary_only_columns"]
        or diff["copies_only_columns"]
    ):
        raise Refusal("MIGRATION_KEYS_OR_COLUMNS_DIFFER")
    if any(v["count"] for k, v in diff["field_mismatches"].items() if k != "volume"):
        raise Refusal("MIGRATION_NON_VOLUME_FIELDS_DIFFER")
    if any(diff[side].get("invalid_ohlcv", 0) for side in ("primary", "copies")):
        raise Refusal("MIGRATION_INVALID_OHLCV")
    expected = canonical_dates(primary).set_index(["ticker", "date"]).sort_index()
    volumes = canonical_dates(copies).set_index(["ticker", "date"]).sort_index().volume
    expected["volume"] = volumes.astype("float64")
    expected = expected.reset_index()[primary.columns]
    if artifact_hashes(bars, plan.source_plan) != plan.source_hashes:
        raise Refusal("MIGRATION_INPUT_CHANGED")
    return expected, copies, diff


def _state(con, state):
    con.execute("UPDATE authority_migration SET state=?", [state])
    con.execute(
        "INSERT INTO authority_migration_events SELECT COALESCE(MAX(sequence),0)+1,? FROM authority_migration_events",
        [state],
    )


def _open(path, read_only=False):
    safe_path(path, output=True)
    return duckdb.connect(
        str(path),
        read_only=read_only,
        config={"enable_external_access": False, "threads": 1, "memory_limit": "512MB"},
    )


def _metadata(con, digest):
    rows = con.execute(
        "SELECT state,plan_fingerprint FROM authority_migration"
    ).fetchall()
    if (
        len(rows) != 1
        or rows[0][1] != digest
        or rows[0][0] not in ("pending", "complete", "recovery_required")
    ):
        raise Refusal("MIGRATION_STATE_OR_BINDING_INVALID")
    return rows[0][0]


def simulate_migration(plan, *, interrupt_after=None):
    if interrupt_after not in (None, "pending", "replacement"):
        raise Refusal("UNKNOWN_SIMULATION_INTERRUPTION")
    description = describe_migration(plan)
    expected, copies, _diff = migration_inputs(plan)
    target = safe_path(plan.source_plan.workspace / plan.output_name, output=True)
    digest = description["plan_fingerprint"]
    if target.exists():
        with _open(target, True) as con:
            state = _metadata(con, digest)
        if state == "complete":
            result = validate_migration(plan)
            return {**result, "operation": "NO_OP"}
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Only this temporary copy is writable. Atomic no-replace publication
        # refuses a competing simulator without replacing its evidence.
        with tempfile.TemporaryDirectory(
            prefix=".authority-", dir=target.parent
        ) as temp:
            temporary = Path(temp) / "simulation.duckdb"
            with duckdb.connect(
                str(temporary), config={"enable_external_access": False}
            ) as con:
                con.execute(
                    "CREATE TABLE authority_migration(state VARCHAR,plan_fingerprint VARCHAR)"
                )
                con.execute(
                    "INSERT INTO authority_migration VALUES ('pending',?)", [digest]
                )
                con.execute(
                    "CREATE TABLE authority_migration_events(sequence INTEGER,state VARCHAR)"
                )
                con.execute(
                    "INSERT INTO authority_migration_events VALUES (1,'pending')"
                )
            atomic_write(target, temporary.read_bytes())
    if interrupt_after == "pending":
        return {"state": "pending", "operation": "SIMULATED_PROCESS_INTERRUPTION"}
    with _open(target) as con:
        _metadata(con, digest)
        try:
            con.execute("BEGIN")
            _state(con, "pending")
            con.register("verified_copy", expected)
            con.execute(
                "CREATE OR REPLACE TABLE daily_bars AS SELECT * REPLACE (CAST(volume AS DOUBLE) AS volume, CAST(transactions AS BIGINT) AS transactions) FROM verified_copy"
            )
            actual = con.execute("SELECT * FROM daily_bars").fetchdf()
            if not compare_copies(actual, copies, ["ticker", "date"])["equivalent"]:
                raise Refusal("SIMULATED_REPLACEMENT_NOT_EXACT")
            if interrupt_after == "replacement":
                _state(con, "recovery_required")
                con.execute("COMMIT")
                return {
                    "state": "recovery_required",
                    "operation": "SIMULATED_POST_REPLACEMENT_FAILURE",
                }
            _state(con, "complete")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            _state(con, "recovery_required")
            raise
    return {**validate_migration(plan), "operation": "SIMULATION_COMPLETE"}


def validate_migration(plan):
    description = describe_migration(plan)
    _, copies, original = migration_inputs(plan)
    target = safe_path(plan.source_plan.workspace / plan.output_name, output=True)
    before = file_hash(target)
    with _open(target, True) as con:
        if _metadata(con, description["plan_fingerprint"]) != "complete":
            raise Refusal("SIMULATION_NOT_COMPLETE")
        schema = dict(
            con.execute(
                "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='main' AND table_name='daily_bars'"
            ).fetchall()
        )
        if schema.get("volume") != "DOUBLE" or schema.get("transactions") != "BIGINT":
            raise Refusal("SIMULATION_SCHEMA_INVALID")
        actual = con.execute("SELECT * FROM daily_bars").fetchdf()
        events = con.execute(
            "SELECT sequence,state FROM authority_migration_events ORDER BY sequence"
        ).fetchall()
    comparison = compare_copies(actual, copies, ["ticker", "date"])
    if not comparison["equivalent"] or comparison["primary"]["duplicate_keys"]:
        raise Refusal("SIMULATION_PARQUET_DISAGREEMENT")
    if before != file_hash(target):
        raise Refusal("SIMULATION_CHANGED_DURING_VALIDATION")
    return {
        "state": "complete",
        "plan_fingerprint": description["plan_fingerprint"],
        "database_sha256": before,
        "rows": len(actual),
        "restored_fractional_values": original["field_mismatches"]["volume"]["count"],
        "comparison": comparison,
        "events": [list(x) for x in events],
        "production_applied": False,
    }


def future_commands(plan):
    """Reviewable commands only. None is dispatched by any mode in this module."""
    describe_migration(plan)
    bars = next(a for a in plan.source_plan.artifacts if a.role == "bars")
    source, staged = (
        str(bars.paths[0]),
        str(plan.source_plan.workspace / plan.output_name),
    )
    quoted_staged = staged.replace("'", "''")
    select = "SELECT * FROM daily_bars"
    diff = "SELECT COUNT(*) FROM ((SELECT * FROM main.daily_bars EXCEPT ALL SELECT * FROM restored.daily_bars) UNION ALL (SELECT * FROM restored.daily_bars EXCEPT ALL SELECT * FROM main.daily_bars))"
    return {
        "status": "LATER_APPROVAL_REQUIRED_NOT_EXECUTABLE_MODE",
        "maintenance": "Stop all database writers/readers and verify exclusive maintenance ownership before backup; keep them stopped through verification or rollback.",
        "backup_argv": [
            "cp",
            "--no-clobber",
            "--reflink=auto",
            source,
            source + ".pre-authority-backup",
        ],
        "verify_backup_argv": ["sha256sum", source, source + ".pre-authority-backup"],
        "required_source_sha256": plan.source_hashes[0],
        "required_candidate_validation": "validate mode with this exact plan; pin returned candidate database SHA256 before approval",
        "apply_sql_for_separate_review": [
            f"ATTACH '{quoted_staged}' AS restored (READ_ONLY)",
            "BEGIN TRANSACTION",
            "ALTER TABLE main.daily_bars ALTER COLUMN volume TYPE DOUBLE",
            "UPDATE main.daily_bars AS b SET volume=r.volume FROM restored.daily_bars AS r WHERE b.ticker=r.ticker AND b.date=r.date",
            diff,
            "COMMIT",
        ],
        "commit_gate": "Assert difference_count is zero inside the transaction; execute ROLLBACK instead of COMMIT on any mismatch.",
        "post_apply_verification_sql": [
            diff,
            "SELECT data_type FROM information_schema.columns WHERE table_schema='main' AND table_name='daily_bars' AND column_name='volume'",
            "SELECT ticker,date,COUNT(*) FROM main.daily_bars GROUP BY ticker,date HAVING COUNT(*)<>1",
        ],
        "rollback_argv": [
            "cp",
            "--reflink=auto",
            source + ".pre-authority-backup",
            source,
        ],
        "rollback_condition": "Close/checkpoint the approved connection first; verify no WAL or active reader/writer before restoring the full backup and matching its SHA256. Do not remove unrelated sidecars.",
        "parquet_writes": 0,
        "derived_features": "Existing integer-volume feature tables remain blocked; separate reviewed schema correction and rebuild is required. Do not overwrite legacy feature outputs in this migration.",
        "original_selection": select,
    }
