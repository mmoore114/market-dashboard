"""Recoverable publication of a validated, append-only adjusted-bar candidate."""

import json
import os
import shutil
from pathlib import Path

import duckdb
import pandas as pd

from market_dashboard.data.adjusted_authority import require_double_volume
from market_dashboard.data.current_sources import write_new
from market_dashboard.data.security_master_refresh import digest, safe_path
from market_dashboard.workstation.materialization.reconciliation import compare_copies


def publish_bars(
    database,
    parquet_directory,
    candidate_directory,
    workspace,
    *,
    expected_database_hash,
    checkpoint=lambda _: None,
):
    database, parquet_directory, candidate_directory, workspace = map(
        safe_path, (database, parquet_directory, candidate_directory, workspace)
    )
    if candidate_directory == parquet_directory or database.is_relative_to(workspace):
        raise ValueError("ISOLATED_CANDIDATE_REQUIRED")
    files = sorted(candidate_directory.glob("*.parquet"))
    if not files:
        raise ValueError("NO_BAR_CANDIDATE")
    frames = [pd.read_parquet(p) for p in files]
    frame = pd.concat(frames, ignore_index=True)
    hashes = {p.name: digest(p) for p in files}
    binding = (
        __import__("hashlib")
        .sha256(json.dumps(hashes, sort_keys=True).encode())
        .hexdigest()
    )
    if frame.duplicated(["ticker", "date"]).any():
        raise ValueError("DUPLICATE_CANDIDATE_KEYS")
    if any(set(f.ticker) != {p.stem} for f, p in zip(frames, files)):
        raise ValueError("PARTITION_IDENTITY_MISMATCH")
    backup = workspace / "backup"
    workspace.mkdir(parents=True, exist_ok=True)
    committed = False
    with duckdb.connect(str(database)) as con:
        require_double_volume(con)
        exists = con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='current_foundation_publication'"
        ).fetchone()[0]
        state = (
            con.execute(
                "SELECT state,binding FROM current_foundation_publication WHERE phase='adjusted-bars-v1'"
            ).fetchone()
            if exists
            else None
        )
        if state and state[1] != binding:
            raise ValueError("RECOVERY_CANDIDATE_CHANGED")

        def verify():
            actual = con.execute("SELECT * FROM daily_bars").fetchdf()
            if not compare_copies(actual, frame, ["ticker", "date"])["equivalent"]:
                raise ValueError("BAR_CANDIDATE_DISAGREEMENT")
            for p in files:
                if (
                    digest(p) != hashes[p.name]
                    or digest(parquet_directory / p.name) != hashes[p.name]
                ):
                    raise ValueError("BAR_PARTITION_CHANGED")
            return len(actual)

        if state and state[0] == "complete":
            return {
                "state": "complete",
                "action": "no_op",
                "rows": verify(),
                "binding": binding,
            }
        if not state:
            if (
                Path(str(database) + ".wal").exists()
                or digest(database) != expected_database_hash
            ):
                raise ValueError("DATABASE_PREFLIGHT_CHANGED")
            if backup.exists():
                raise ValueError("BACKUP_EXISTS_WITHOUT_COMMITTED_STATE")
            backup.mkdir()
            shutil.copy2(database, backup / "database.duckdb")
            shutil.copytree(parquet_directory, backup / "partitions")
            if digest(backup / "database.duckdb") != expected_database_hash:
                raise ValueError("BACKUP_HASH_MISMATCH")
            for p in (
                backup / "database.duckdb",
                *(backup / "partitions").glob("*.parquet"),
            ):
                with p.open("rb") as stream:
                    os.fsync(stream.fileno())
            old = con.execute("SELECT * FROM daily_bars").fetchdf()
            con.register("verified_current_candidate", frame)
            if con.execute(
                "SELECT COUNT(*) FROM (SELECT * FROM daily_bars EXCEPT ALL SELECT * FROM verified_current_candidate)"
            ).fetchone()[0]:
                raise ValueError("PRIOR_HISTORY_CHANGED")
            if len(frame) <= len(old):
                raise ValueError("APPEND_ONLY_INCREMENT_REQUIRED")
            con.execute("BEGIN")
            try:
                con.execute(
                    "CREATE TABLE IF NOT EXISTS current_foundation_publication(phase VARCHAR PRIMARY KEY,state VARCHAR,binding VARCHAR)"
                )
                con.execute(
                    "INSERT INTO daily_bars SELECT c.* FROM verified_current_candidate c WHERE NOT EXISTS (SELECT 1 FROM daily_bars b WHERE b.ticker=c.ticker AND b.date=c.date)"
                )
                con.execute(
                    "INSERT INTO current_foundation_publication VALUES ('adjusted-bars-v1','pending',?)",
                    [binding],
                )
                if not compare_copies(
                    con.execute("SELECT * FROM daily_bars").fetchdf(),
                    frame,
                    ["ticker", "date"],
                )["equivalent"]:
                    raise ValueError("TRANSACTION_CANDIDATE_MISMATCH")
                con.execute("COMMIT")
                committed = True
            except BaseException:
                con.execute("ROLLBACK")
                raise
        else:
            committed = True
        try:
            checkpoint("committed")
            for p in files:
                target = parquet_directory / p.name
                pending = target.with_suffix(".current-pending")
                if pending.exists():
                    if digest(pending) != hashes[p.name]:
                        raise ValueError("PENDING_PARTITION_CHANGED")
                else:
                    write_new(pending, p.read_bytes())
                os.replace(pending, target)
            descriptor = os.open(parquet_directory, os.O_RDONLY)
            os.fsync(descriptor)
            os.close(descriptor)
            checkpoint("renamed")
            rows = verify()
            con.execute(
                "UPDATE current_foundation_publication SET state='complete' WHERE phase='adjusted-bars-v1'"
            )
            con.execute("CHECKPOINT")
        except BaseException:
            if committed:
                con.execute(
                    "UPDATE current_foundation_publication SET state='recovery_required' WHERE phase='adjusted-bars-v1'"
                )
            raise
    # Independently reopen after closing all publishing connections.
    with duckdb.connect(str(database), read_only=True) as con:
        if not compare_copies(
            con.execute("SELECT * FROM daily_bars").fetchdf(),
            pd.concat(
                [pd.read_parquet(parquet_directory / p.name) for p in files],
                ignore_index=True,
            ),
            ["ticker", "date"],
        )["equivalent"]:
            raise ValueError("POST_CLOSE_BAR_DISAGREEMENT")
    return {
        "state": "complete",
        "action": "recovered" if state else "published",
        "rows": rows,
        "binding": binding,
        "database_sha256": digest(database),
        "backup_sha256": digest(backup / "database.duckdb"),
    }


def replace_feature_tables(connection, candidate):
    """Replace only validated derived tables inside caller's maintenance transaction.

    Caller owns backup, BEGIN/COMMIT/ROLLBACK and publication receipt. Exact DDL
    and index definitions come from the isolated existing-pipeline candidate.
    """
    candidate = safe_path(candidate)
    connection.execute(
        "ATTACH '"
        + str(candidate).replace("'", "''")
        + "' AS rebuilt_features (READ_ONLY)"
    )
    difference = connection.execute(
        "SELECT COUNT(*) FROM ((SELECT * FROM main.daily_bars EXCEPT ALL SELECT * FROM rebuilt_features.daily_bars) UNION ALL (SELECT * FROM rebuilt_features.daily_bars EXCEPT ALL SELECT * FROM main.daily_bars))"
    ).fetchone()[0]
    if difference:
        raise ValueError("FEATURE_SOURCE_BARS_CHANGED")
    for table in ("daily_equity_features", "latest_equity_snapshot"):
        dtype = connection.execute(
            "SELECT data_type FROM information_schema.columns WHERE table_catalog='rebuilt_features' AND table_name=? AND column_name='volume'",
            [table],
        ).fetchone()
        if dtype != ("DOUBLE",):
            raise ValueError("FEATURE_VOLUME_NOT_DOUBLE")
        ddl = connection.execute(
            "SELECT sql FROM duckdb_tables() WHERE database_name='rebuilt_features' AND table_name=?",
            [table],
        ).fetchone()[0]
        indexes = connection.execute(
            "SELECT sql FROM duckdb_indexes() WHERE database_name='rebuilt_features' AND table_name=?",
            [table],
        ).fetchall()
        connection.execute(f"DROP TABLE main.{table}")
        connection.execute(ddl)
        connection.execute(
            f"INSERT INTO main.{table} SELECT * FROM rebuilt_features.{table}"
        )
        for (sql,) in indexes:
            connection.execute(sql)
        if connection.execute(
            f"SELECT COUNT(*) FROM ((SELECT * FROM main.{table} EXCEPT ALL SELECT * FROM rebuilt_features.{table}) UNION ALL (SELECT * FROM rebuilt_features.{table} EXCEPT ALL SELECT * FROM main.{table}))"
        ).fetchone()[0]:
            raise ValueError("FEATURE_REPLACEMENT_MISMATCH")
