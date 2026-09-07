"""Offline, recoverable security-master publication, independent of exposures."""

import os
from pathlib import Path

import duckdb
import pandas as pd

from .security_identity import (
    COMPATIBILITY_VERSION,
    IDENTITY_VERSION,
    publication_blockers,
)
from .security_master import SECURITY_MASTER_COLUMNS
from .security_master_refresh import (
    JULY,
    digest,
    fingerprint,
    safe_path,
    validated_artifact,
)


def preserve_reference_nanoseconds(connection):
    """Widen UTC-naive reference timestamps without changing any existing value.

    Called only inside the confirmed publication transaction. An exact-schema
    shadow table preserves constraints and index SQL while widening timestamps;
    DuckDB cannot recreate a dropped UNIQUE index after ALTER in one transaction.
    No timezone conversion or precision truncation is permitted.
    """
    kind = connection.execute(
        "SELECT data_type FROM information_schema.columns WHERE table_catalog=current_database() AND table_schema='main' AND table_name='security_master' AND column_name='last_updated_utc'"
    ).fetchone()
    if kind == ("TIMESTAMP_NS",):
        return
    if kind != ("TIMESTAMP",):
        raise ValueError("Unsupported reference timestamp representation")
    indexes = connection.execute(
        "SELECT index_name,sql FROM duckdb_indexes() WHERE database_name=current_database() AND schema_name='main' AND table_name='security_master'"
    ).fetchall()
    ddl = connection.execute(
        "SELECT sql FROM duckdb_tables() WHERE database_name=current_database() AND schema_name='main' AND table_name='security_master'"
    ).fetchone()[0]
    prefix = "CREATE TABLE security_master("
    if not ddl.startswith(prefix) or ddl.count("last_updated_utc TIMESTAMP") != 1:
        raise ValueError("Unrecognized reference schema; exact migration required")
    replacement = ddl.replace(
        prefix, "CREATE TABLE reference_precision_candidate(", 1
    ).replace("last_updated_utc TIMESTAMP", "last_updated_utc TIMESTAMP_NS", 1)
    connection.execute(replacement)
    connection.execute(
        "INSERT INTO reference_precision_candidate SELECT * FROM security_master"
    )
    connection.execute("DROP TABLE security_master")
    connection.execute(
        "ALTER TABLE reference_precision_candidate RENAME TO security_master"
    )
    for _, sql in indexes:
        connection.execute(sql)


def compare(connection, snapshot_date, parquet):
    stored = connection.execute(
        "SELECT * FROM security_master WHERE snapshot_date = ? ORDER BY ticker",
        [snapshot_date],
    ).df()
    artifact = pd.read_parquet(parquet)
    if set(stored.columns) != set(artifact.columns) or fingerprint(
        stored, logical=False
    ) != fingerprint(artifact, logical=False):
        raise ValueError("DuckDB/Parquet field mismatch")
    return stored


def protect_july(connection, p):
    path = safe_path(
        Path(p["parquet_directory"]) / f"snapshot_date={JULY}/security_master.parquet"
    )
    if digest(path) != p["input_hashes"]["july"]:
        raise ValueError("Protected July Parquet bytes changed")
    july = compare(connection, JULY, path)
    if fingerprint(july, logical=False) != p["protected_fingerprint"]:
        raise ValueError("Protected July content changed")


def publish(
    workspace, *, confirm=False, authorize_revision=None, checkpoint=lambda stage: None
):
    if not confirm:
        raise ValueError("Explicit publication confirmation required")
    p, receipt, frame = validated_artifact(workspace)
    if (
        receipt.get("identity_version") != IDENTITY_VERSION
        or receipt.get("compatibility_version") != COMPATIBILITY_VERSION
        or publication_blockers(frame.ticker)
    ):
        raise ValueError(
            "Publication blocked: identity compatibility ambiguity or unsafe reader"
        )
    db = safe_path(p["database"])
    if not db.is_file():
        raise ValueError("Existing master database required")
    directory = safe_path(
        Path(p["parquet_directory"]) / f"snapshot_date={p['snapshot_date']}"
    )
    target = safe_path(directory / "security_master.parquet")
    pending = safe_path(directory / "security_master.pending.parquet")
    connection = duckdb.connect(str(db))
    committed = False
    try:
        protect_july(connection, p)
        existing = connection.execute(
            "SELECT * FROM security_master WHERE snapshot_date = ? ORDER BY ticker",
            [p["snapshot_date"]],
        ).df()
        table_exists = connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name='security_master_publication'"
        ).fetchone()[0]
        state = (
            connection.execute(
                "SELECT state, artifact_hash FROM security_master_publication WHERE snapshot_date=?",
                [p["snapshot_date"]],
            ).fetchone()
            if table_exists
            else None
        )
        artifact_hash = receipt["hashes"]["security_master.parquet"]
        recovering = state and state[0] != "complete"
        if recovering and state[1] != artifact_hash:
            raise ValueError("Recovery requires original validated artifact")
        if target.exists() and not len(existing) and not recovering:
            raise ValueError("Orphan same-date Parquet requires manual recovery")
        if len(existing) and not recovering:
            previous = fingerprint(existing)
            if previous == receipt["logical_fingerprint"]:
                compare(connection, p["snapshot_date"], target)
                return {"state": "complete", "action": "no_op", "rows": len(existing)}
            if authorize_revision != previous:
                raise ValueError(
                    "Changed same-date content requires existing fingerprint revision authorization"
                )
        directory.mkdir(parents=True, exist_ok=True)
        with pending.open("wb") as stream:
            stream.write((Path(workspace) / "security_master.parquet").read_bytes())
            stream.flush()
            os.fsync(stream.fileno())
        if digest(pending) != artifact_hash:
            raise ValueError("Validated artifact changed during staging")
        checkpoint("staged")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS security_master_publication (snapshot_date DATE PRIMARY KEY, state VARCHAR, artifact_hash VARCHAR, logical_fingerprint VARCHAR)"
        )
        connection.register("refresh_incoming", frame[SECURITY_MASTER_COLUMNS])
        connection.execute("BEGIN TRANSACTION")
        try:
            preserve_reference_nanoseconds(connection)
            connection.execute(
                "DELETE FROM security_master WHERE snapshot_date=?",
                [p["snapshot_date"]],
            )
            columns = ", ".join(SECURITY_MASTER_COLUMNS)
            connection.execute(
                f"INSERT INTO security_master ({columns}) SELECT {columns} FROM refresh_incoming"
            )
            connection.execute(
                "INSERT OR REPLACE INTO security_master_publication VALUES (?, 'pending', ?, ?)",
                [p["snapshot_date"], artifact_hash, receipt["logical_fingerprint"]],
            )
            connection.execute("COMMIT")
            committed = True
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        checkpoint("committed")
        pending.replace(target)
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        checkpoint("renamed")
        compare(connection, p["snapshot_date"], target)
        protect_july(connection, p)
        connection.execute(
            "UPDATE security_master_publication SET state='complete' WHERE snapshot_date=?",
            [p["snapshot_date"]],
        )
        return {
            "state": "complete",
            "action": "recovered" if recovering else "published",
            "rows": len(frame),
            "logical_fingerprint": receipt["logical_fingerprint"],
        }
    except BaseException:
        if committed:
            connection.execute(
                "UPDATE security_master_publication SET state='recovery_required' WHERE snapshot_date=?",
                [p["snapshot_date"]],
            )
        raise
    finally:
        connection.close()
