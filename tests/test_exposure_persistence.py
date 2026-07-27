from __future__ import annotations

from pathlib import Path
import shutil

import duckdb
import pandas as pd
import pytest

from market_dashboard.data.exposure_policy import (
    ExposureClassificationStore,
    classification_fingerprint,
)
from market_dashboard.data.swing_universe import SwingUniverseBuilder

from scripts.validate_exposure_classification import (
    validate_exposure_classification,
)


SNAPSHOT = "2026-07-26"
POLICY = "exposure-policy-v2"


def classification_frame(*, reason: str = "classified") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "snapshot_date": SNAPSHOT,
                "ticker": "AAA",
                "policy_version": POLICY,
                "exposure_scope": "direct_equity",
                "classification_method": "instrument_category",
                "underlying_ticker": "AAA",
                "policy_reason": reason,
                "classification_provenance": "test",
            },
            {
                "snapshot_date": SNAPSHOT,
                "ticker": "ETF",
                "policy_version": POLICY,
                "exposure_scope": "diversified",
                "classification_method": "default_etf",
                "underlying_ticker": None,
                "policy_reason": "diversified",
                "classification_provenance": "test",
            },
        ]
    )


def make_store(
    tmp_path: Path,
    *,
    failure_point: str | None = None,
    replace=None,
) -> ExposureClassificationStore:
    def inject(point: str) -> None:
        if point == failure_point:
            raise RuntimeError(f"injected failure at {point}")

    return ExposureClassificationStore(
        duckdb_path=tmp_path / "market.duckdb",
        parquet_directory=tmp_path / "classification",
        failure_injector=inject if failure_point else None,
        atomic_replace=replace,
    )


def add_security_master(database: Path) -> None:
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS security_master AS
            SELECT * FROM (VALUES
                (DATE '2026-07-26', 'AAA', 'AAA Corp', 'CS', 'Common Stock'),
                (DATE '2026-07-26', 'ETF', 'ETF Fund', 'ETF', 'ETF')
            ) v(snapshot_date, ticker, name, security_type, normalized_category)
            """
        )


def validate(tmp_path: Path) -> tuple[int, dict]:
    add_security_master(tmp_path / "market.duckdb")
    return validate_exposure_classification(
        tmp_path / "market.duckdb",
        parquet_directory=tmp_path / "classification",
        snapshot_date=SNAPSHOT,
        policy_version=POLICY,
    )


def test_fingerprint_is_deterministic_and_covers_all_fields() -> None:
    frame = classification_frame()
    assert classification_fingerprint(frame) == classification_fingerprint(
        frame.iloc[::-1]
    )
    changed = frame.copy()
    changed.loc[0, "classification_provenance"] = "different"
    assert classification_fingerprint(frame) != classification_fingerprint(changed)


def test_temporary_parquet_write_failure_leaves_no_partial_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs) -> None:
        raise OSError("injected write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail)
    store = make_store(tmp_path)
    with pytest.raises(OSError, match="write failure"):
        store.persist(classification_frame())
    assert not (tmp_path / "market.duckdb").exists()
    assert not store.staged_path(pd.Timestamp(SNAPSHOT).date(), POLICY).exists()


@pytest.mark.parametrize(
    "failure_point",
    ["after_pending_update", "after_upsert", "after_stale_delete", "before_commit"],
)
def test_transaction_failures_roll_back_entire_slice(
    tmp_path: Path, failure_point: str
) -> None:
    store = make_store(tmp_path, failure_point=failure_point)
    with pytest.raises(RuntimeError, match="injected failure"):
        store.persist(classification_frame())
    with duckdb.connect(str(tmp_path / "market.duckdb"), read_only=True) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        assert "security_exposure_classification" not in tables
        assert "exposure_classification_publication" not in tables
    assert not store.staged_path(pd.Timestamp(SNAPSHOT).date(), POLICY).exists()


def test_committed_without_publish_is_explicit_and_recoverable(tmp_path: Path) -> None:
    store = make_store(tmp_path, failure_point="after_commit_before_publish")
    with pytest.raises(RuntimeError, match="after_commit_before_publish"):
        store.persist(classification_frame())
    record = store.publication_record(SNAPSHOT, POLICY)
    assert record["publication_state"] == "recovery_required"
    assert store.staged_path(pd.Timestamp(SNAPSHOT).date(), POLICY).exists()
    assert not store.parquet_path(pd.Timestamp(SNAPSHOT).date(), POLICY).exists()

    result = make_store(tmp_path).recover(SNAPSHOT, POLICY)
    assert result["action"] == "published_staged_parquet"
    assert result["state"] == "complete"


def test_atomic_replace_failure_preserves_previous_complete_final(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    final = store.persist(classification_frame())
    original = final.read_bytes()

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("injected replace failure")

    broken = make_store(tmp_path, replace=fail_replace)
    with pytest.raises(OSError, match="replace failure"):
        broken.persist(classification_frame(reason="new classification"))
    assert final.read_bytes() == original
    assert broken.publication_record(SNAPSHOT, POLICY)["publication_state"] == (
        "recovery_required"
    )


def test_precommit_failure_preserves_previous_complete_slice_and_final(
    tmp_path: Path,
) -> None:
    stable = make_store(tmp_path)
    final = stable.persist(classification_frame())
    original_file = final.read_bytes()
    original_fingerprint = stable.publication_record(SNAPSHOT, POLICY)[
        "content_fingerprint"
    ]
    broken = make_store(tmp_path, failure_point="after_upsert")
    with pytest.raises(RuntimeError):
        broken.persist(classification_frame(reason="must roll back"))
    assert final.read_bytes() == original_file
    assert stable.publication_record(SNAPSHOT, POLICY)["publication_state"] == "complete"
    assert (
        classification_fingerprint(stable._read_duckdb_slice(  # noqa: SLF001
            pd.Timestamp(SNAPSHOT).date(), POLICY
        ))
        == original_fingerprint
    )


def test_verification_failure_never_marks_publication_complete(
    tmp_path: Path,
) -> None:
    def publish_corrupt(source: Path, target: Path) -> None:
        source.replace(target)
        corrupt = pd.read_parquet(target)
        corrupt.loc[0, "policy_reason"] = "corrupt after publication"
        corrupt.to_parquet(target, index=False)

    store = make_store(tmp_path, replace=publish_corrupt)
    with pytest.raises(ValueError, match="mismatch"):
        store.persist(classification_frame())
    assert store.publication_record(SNAPSHOT, POLICY)["publication_state"] == (
        "recovery_required"
    )


def test_recovery_without_staged_regenerates_from_duckdb(tmp_path: Path) -> None:
    store = make_store(tmp_path, failure_point="after_commit_before_publish")
    with pytest.raises(RuntimeError):
        store.persist(classification_frame())
    store.staged_path(pd.Timestamp(SNAPSHOT).date(), POLICY).unlink()
    result = make_store(tmp_path).recover(SNAPSHOT, POLICY)
    assert result["action"] == "regenerated_and_published_parquet"
    assert make_store(tmp_path).publication_record(SNAPSHOT, POLICY)[
        "publication_state"
    ] == "complete"


def test_final_exists_while_pending_and_repeated_recovery_is_idempotent(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    store.persist(classification_frame())
    with duckdb.connect(str(tmp_path / "market.duckdb")) as connection:
        connection.execute(
            """
            UPDATE exposure_classification_publication
            SET publication_state = 'pending'
            WHERE snapshot_date = ? AND policy_version = ?
            """,
            [SNAPSHOT, POLICY],
        )
    first = store.recover(SNAPSHOT, POLICY)
    second = store.recover(SNAPSHOT, POLICY)
    assert first["action"] == "verified_existing_final"
    assert second == {"state_found": "complete", "action": "none", "state": "complete"}


def test_recovery_repairs_mismatched_final_and_preserves_other_partition(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    final = store.persist(classification_frame())
    other = store.parquet_path(pd.Timestamp("2026-07-25").date(), POLICY)
    other.parent.mkdir(parents=True)
    shutil.copyfile(final, other)
    other_before = other.read_bytes()
    corrupt = classification_frame()
    corrupt.loc[0, "policy_reason"] = "corrupt"
    corrupt.to_parquet(final, index=False)
    store.recover(SNAPSHOT, POLICY)
    assert other.read_bytes() == other_before
    assert classification_fingerprint(pd.read_parquet(final)) == (
        classification_fingerprint(classification_frame())
    )


def test_recorded_fingerprint_disagreement_blocks_recovery(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.persist(classification_frame())
    with duckdb.connect(str(tmp_path / "market.duckdb")) as connection:
        connection.execute(
            """
            UPDATE exposure_classification_publication
            SET publication_state = 'pending', content_fingerprint = 'wrong'
            WHERE snapshot_date = ? AND policy_version = ?
            """,
            [SNAPSHOT, POLICY],
        )
    with pytest.raises(ValueError, match="fingerprint disagrees"):
        store.recover(SNAPSHOT, POLICY)


def test_same_policy_rebuild_is_idempotent(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = store.persist(classification_frame())
    before = first.read_bytes()
    store.persist(classification_frame().iloc[::-1])
    with duckdb.connect(str(tmp_path / "market.duckdb"), read_only=True) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM security_exposure_classification"
        ).fetchone()[0] == 2
    assert first.read_bytes() == before


@pytest.mark.parametrize(
    ("mutation", "metric"),
    [
        ("duplicate", "parquet_duplicate_rows"),
        ("missing", "missing_keys"),
        ("extra", "extra_keys"),
        ("field", "field_mismatch_counts"),
    ],
)
def test_validator_reports_store_disagreements(
    tmp_path: Path, mutation: str, metric: str
) -> None:
    store = make_store(tmp_path)
    final = store.persist(classification_frame())
    parquet = pd.read_parquet(final)
    if mutation == "duplicate":
        parquet = pd.concat([parquet, parquet.iloc[[0]]], ignore_index=True)
    elif mutation == "missing":
        parquet = parquet.iloc[1:].copy()
    elif mutation == "extra":
        extra = parquet.iloc[[0]].copy()
        extra["ticker"] = "ZZZ"
        extra["underlying_ticker"] = "ZZZ"
        parquet = pd.concat([parquet, extra], ignore_index=True)
    else:
        parquet.loc[0, "policy_reason"] = "mismatch"
    parquet.to_parquet(final, index=False)
    code, metrics = validate(tmp_path)
    assert code == 1
    assert metrics[metric]


def test_validator_rejects_pending_wrong_partition_and_extra_file(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    final = store.persist(classification_frame())
    extra = final.parent / "unexpected.parquet"
    shutil.copyfile(final, extra)
    with duckdb.connect(str(tmp_path / "market.duckdb")) as connection:
        connection.execute(
            """
            UPDATE exposure_classification_publication
            SET publication_state = 'pending', final_parquet_path = ?
            WHERE snapshot_date = ? AND policy_version = ?
            """,
            [str(final.parent.parent / "policy_version=wrong" / final.name), SNAPSHOT, POLICY],
        )
    code, metrics = validate(tmp_path)
    assert code == 1
    assert metrics["publication_state"] == "pending"
    assert not metrics["path_identity_correct"]
    assert metrics["extra_parquet_files"] == [str(extra)]


def test_downstream_builder_blocks_incomplete_publication_first(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path, failure_point="after_commit_before_publish")
    with pytest.raises(RuntimeError):
        store.persist(classification_frame())
    builder = SwingUniverseBuilder(
        duckdb_path=tmp_path / "market.duckdb",
        parquet_directory=tmp_path / "universe",
        exposure_classification_directory=tmp_path / "classification",
        thresholds={
            "minimum_latest_close": 5,
            "minimum_average_dollar_volume_20": 1,
            "minimum_valid_observations": 1,
            "minimum_session_coverage_percent": 1,
        },
    )
    with pytest.raises(ValueError, match="not complete"):
        builder.build(
            snapshot_date=SNAPSHOT,
            security_master_snapshot_date=SNAPSHOT,
            source_start_date=SNAPSHOT,
            source_end_date=SNAPSHOT,
            policy_version=POLICY,
        )
