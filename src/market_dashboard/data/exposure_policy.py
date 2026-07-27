from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


EXPOSURE_SCOPES = {
    "direct_equity",
    "single_security",
    "diversified",
    "non_equity",
    "review_needed",
}
SINGLE_SECURITY_EXCLUSION = (
    "Single-security product excluded from core swing universe"
)
REVIEW_NEEDED_EXCLUSION = "Exposure classification requires review"
CLASSIFICATION_COLUMNS = [
    "snapshot_date",
    "ticker",
    "policy_version",
    "exposure_scope",
    "classification_method",
    "underlying_ticker",
    "policy_reason",
    "classification_provenance",
]
PUBLICATION_STATES = {"pending", "complete", "recovery_required"}
PUBLICATION_KEY = ["snapshot_date", "policy_version"]
CLASSIFICATION_KEY = ["snapshot_date", "ticker", "policy_version"]


@dataclass(frozen=True)
class ExposureOverride:
    ticker: str
    effective_start_date: date
    effective_end_date: date | None
    exposure_scope: str
    underlying_ticker: str | None
    reason: str
    provenance: str


@dataclass(frozen=True)
class ExposureClassification:
    snapshot_date: date
    ticker: str
    policy_version: str
    exposure_scope: str
    classification_method: str
    underlying_ticker: str | None
    policy_reason: str
    classification_provenance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExposurePolicy:
    """Versioned classification of economic exposure, separate from provider facts."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.policy_version = str(config.get("policy_version", "")).strip()
        if not self.policy_version:
            raise ValueError("exposure policy version cannot be empty")
        self.registry: dict[str, tuple[str, str, str]] = {}
        for scope, group in config.get("maintained_classifications", {}).items():
            self._validate_scope(scope)
            reason = str(group.get("reason", "")).strip()
            provenance = str(group.get("provenance", "")).strip()
            if not reason or not provenance:
                raise ValueError(f"maintained {scope} classifications need reason and provenance")
            for ticker in group.get("tickers", []):
                normalized = str(ticker).strip().upper()
                if not normalized:
                    raise ValueError("maintained classification ticker cannot be empty")
                if normalized in self.registry:
                    raise ValueError(f"duplicate maintained classification: {normalized}")
                self.registry[normalized] = (scope, reason, provenance)
        self.overrides = self._parse_overrides(config.get("overrides", []))

    def classify_snapshot(
        self,
        records: pd.DataFrame | Iterable[dict[str, Any]],
        snapshot_date: str | date,
    ) -> pd.DataFrame:
        snapshot = date.fromisoformat(str(snapshot_date))
        frame = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records)
        if frame.empty:
            return pd.DataFrame(columns=CLASSIFICATION_COLUMNS)
        required = {"ticker", "name", "security_type", "normalized_category"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"exposure classification missing columns: {sorted(missing)}")
        known_equities = set(
            frame.loc[frame["normalized_category"] == "Common Stock", "ticker"]
            .astype(str)
            .str.upper()
        )
        rows = [
            self.classify_record(row._asdict(), snapshot, known_equities)
            for row in frame.itertuples(index=False)
        ]
        return pd.DataFrame(
            [row.to_dict() for row in rows], columns=CLASSIFICATION_COLUMNS
        ).sort_values("ticker").reset_index(drop=True)

    def classify_record(
        self,
        record: dict[str, Any],
        snapshot: date,
        known_equities: set[str],
    ) -> ExposureClassification:
        ticker = str(record.get("ticker", "")).strip().upper()
        category = str(record.get("normalized_category", "")).strip()
        raw_type = str(record.get("security_type", "")).strip().upper()
        name = str(record.get("name", "")).strip()

        override = self._active_override(ticker, snapshot)
        if override:
            return self._result(
                snapshot,
                ticker,
                override.exposure_scope,
                "explicit_override",
                override.underlying_ticker,
                override.reason,
                override.provenance,
            )
        maintained = self.registry.get(ticker)
        if maintained:
            scope, reason, provenance = maintained
            return self._result(
                snapshot, ticker, scope, "maintained_registry", None, reason, provenance
            )
        if category == "Common Stock":
            return self._result(
                snapshot,
                ticker,
                "direct_equity",
                "instrument_category",
                ticker,
                "Direct common-stock exposure",
                "provider_normalized_category",
            )
        if category != "ETF":
            return self._result(
                snapshot,
                ticker,
                "non_equity",
                "instrument_category",
                None,
                f"Unsupported core instrument category: {category or 'unknown'}",
                "provider_normalized_category",
            )

        rule_match = self._match_single_security_name(name, known_equities)
        if rule_match:
            rule_id, underlying = rule_match
            return self._result(
                snapshot,
                ticker,
                "single_security",
                f"name_rule:{rule_id}",
                underlying,
                f"Name identifies wrapper exposure to {underlying}",
                "deterministic_name_rule",
            )
        if raw_type == "ETS" or self._is_suspicious_name(name):
            return self._result(
                snapshot,
                ticker,
                "review_needed",
                "provider_signal" if raw_type == "ETS" else "suspicious_name",
                None,
                "Potential single-security exposure is unresolved",
                "provider_type_and_name",
            )
        return self._result(
            snapshot,
            ticker,
            "diversified",
            "default_etf",
            None,
            "No high-confidence single-security signal",
            "deterministic_policy_default",
        )

    def _match_single_security_name(
        self, name: str, known_equities: set[str]
    ) -> tuple[str, str] | None:
        patterns = (
            ("daily_bull_bear", r"\bDaily\s+([A-Z][A-Z0-9.]*)\s+(?:Bull|Bear)\b"),
            ("long_short_daily", r"\b(?:Long|Short)\s+([A-Z][A-Z0-9.]*)\s+Daily\b"),
            ("daily_target", r"\b(?:Long|Short)\s+([A-Z][A-Z0-9.]*)\s+Daily Target\b"),
            ("option_income", r"\b([A-Z][A-Z0-9.]*)\s+(?:Short\s+)?Option Income\b"),
            ("ultra_single", r"\bUltra\s+([A-Z][A-Z0-9.]*)$"),
            ("adr_hedged", r"^(.+?)\s+ADRhedged$"),
        )
        for rule_id, pattern in patterns:
            match = re.search(pattern, name, flags=re.IGNORECASE)
            if not match:
                continue
            candidate = match.group(1).upper()
            if candidate in known_equities:
                return rule_id, candidate
        return None

    @staticmethod
    def _is_suspicious_name(name: str) -> bool:
        return bool(
            re.search(
                r"(?i)\b(single[ -]?stock|weeklypay|daily income|adrhedged|"
                r"option income|daily target|autocallable)\b",
                name,
            )
        )

    def _active_override(self, ticker: str, snapshot: date) -> ExposureOverride | None:
        matches = [
            item
            for item in self.overrides
            if item.ticker == ticker
            and item.effective_start_date <= snapshot
            and (item.effective_end_date is None or snapshot <= item.effective_end_date)
        ]
        if len(matches) > 1:
            raise ValueError(f"multiple active exposure overrides for {ticker} on {snapshot}")
        return matches[0] if matches else None

    def _parse_overrides(self, rows: Iterable[dict[str, Any]]) -> list[ExposureOverride]:
        overrides: list[ExposureOverride] = []
        for row in rows:
            scope = str(row.get("exposure_scope", "")).strip()
            self._validate_scope(scope)
            start = date.fromisoformat(str(row.get("effective_start_date")))
            end_value = row.get("effective_end_date")
            end = date.fromisoformat(str(end_value)) if end_value else None
            if end and start > end:
                raise ValueError("exposure override start date cannot follow end date")
            override = ExposureOverride(
                ticker=str(row.get("ticker", "")).strip().upper(),
                effective_start_date=start,
                effective_end_date=end,
                exposure_scope=scope,
                underlying_ticker=(
                    str(row["underlying_ticker"]).strip().upper()
                    if row.get("underlying_ticker")
                    else None
                ),
                reason=str(row.get("reason", "")).strip(),
                provenance=str(row.get("provenance", "")).strip(),
            )
            if not override.ticker or not override.reason or not override.provenance:
                raise ValueError("exposure overrides need ticker, reason, and provenance")
            for existing in overrides:
                if existing.ticker == override.ticker and _ranges_overlap(existing, override):
                    raise ValueError(f"overlapping exposure overrides for {override.ticker}")
            overrides.append(override)
        return overrides

    @staticmethod
    def _validate_scope(scope: str) -> None:
        if scope not in EXPOSURE_SCOPES:
            raise ValueError(f"invalid exposure scope: {scope}")

    def _result(
        self,
        snapshot: date,
        ticker: str,
        scope: str,
        method: str,
        underlying: str | None,
        reason: str,
        provenance: str,
    ) -> ExposureClassification:
        return ExposureClassification(
            snapshot_date=snapshot,
            ticker=ticker,
            policy_version=self.policy_version,
            exposure_scope=scope,
            classification_method=method,
            underlying_ticker=underlying,
            policy_reason=reason,
            classification_provenance=provenance,
        )


class ExposureClassificationStore:
    """Recoverably publish versioned classifications to DuckDB and Parquet.

    DuckDB and a filesystem rename cannot share a transaction.  Once the pending
    DuckDB transaction commits, its classification slice and fingerprint are the
    recovery authority until the Parquet file is verified and marked complete.
    """

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "exposure_classification",
        failure_injector: Callable[[str], None] | None = None,
        atomic_replace: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)
        self.failure_injector = failure_injector
        self.atomic_replace = atomic_replace or self._replace

    def persist(self, frame: pd.DataFrame) -> Path:
        if frame.empty:
            raise ValueError("cannot persist an empty exposure classification")
        frame = canonicalize_classification(frame)
        _validate_classification_frame(frame)
        snapshot, version = _frame_identity(frame)
        path = self.parquet_path(snapshot, version)
        staged = self.staged_path(snapshot, version)
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = self.publication_record(snapshot, version)
        if existing:
            self.recover(snapshot, version)
            existing = self.publication_record(snapshot, version)
            fingerprint = classification_fingerprint(frame)
            if (
                existing
                and existing["publication_state"] == "complete"
                and existing["expected_row_count"] == len(frame)
                and existing["content_fingerprint"] == fingerprint
            ):
                self.require_complete(snapshot, version)
                return path

        fingerprint = classification_fingerprint(frame)
        self._checkpoint("before_temporary_write")
        try:
            if staged.exists():
                staged.unlink()
            frame.to_parquet(staged, index=False)
            self._fsync_file(staged)
            self._checkpoint("after_temporary_write")
        except Exception:
            staged.unlink(missing_ok=True)
            raise

        committed = False
        try:
            self._checkpoint("before_transaction")
            with duckdb.connect(str(self.duckdb_path)) as connection:
                connection.execute("BEGIN TRANSACTION")
                try:
                    self._ensure_tables(connection)
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO exposure_classification_publication
                        (snapshot_date, policy_version, publication_state,
                         expected_row_count, content_fingerprint, final_parquet_path,
                         staged_parquet_path, failure_message, updated_at)
                        VALUES (?, ?, 'pending', ?, ?, ?, ?, NULL, current_timestamp)
                        """,
                        [
                            snapshot,
                            version,
                            len(frame),
                            fingerprint,
                            str(path),
                            str(staged),
                        ],
                    )
                    self._checkpoint("after_pending_update")
                    connection.register("incoming_exposure_classification", frame)
                    connection.execute(
                        f"""
                        INSERT OR REPLACE INTO security_exposure_classification
                        ({", ".join(CLASSIFICATION_COLUMNS)})
                        SELECT {", ".join(CLASSIFICATION_COLUMNS)}
                        FROM incoming_exposure_classification
                        """
                    )
                    self._checkpoint("after_upsert")
                    connection.execute(
                        """
                        DELETE FROM security_exposure_classification
                        WHERE snapshot_date = ? AND policy_version = ?
                          AND ticker NOT IN (
                            SELECT ticker FROM incoming_exposure_classification
                          )
                        """,
                        [snapshot, version],
                    )
                    self._checkpoint("after_stale_delete")
                    self._checkpoint("before_commit")
                    connection.execute("COMMIT")
                    committed = True
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except Exception:
            if not committed:
                staged.unlink(missing_ok=True)
            raise

        try:
            self._checkpoint("after_commit_before_publish")
            self._checkpoint("before_atomic_replace")
            self.atomic_replace(staged, path)
            self._checkpoint("after_atomic_replace")
            self._verify_committed_output(snapshot, version)
            self._checkpoint("after_verification")
            self._mark_complete(snapshot, version)
        except Exception as exc:
            self._mark_recovery_required(snapshot, version, exc)
            raise
        return path

    def recover(self, snapshot: str | date, policy_version: str) -> dict[str, Any]:
        """Repair one incomplete publication from its committed DuckDB slice."""
        snapshot_date = date.fromisoformat(str(snapshot))
        version = str(policy_version).strip()
        record = self.publication_record(snapshot_date, version)
        if not record:
            raise ValueError(
                f"publication record not found: {snapshot_date}/{version}"
            )
        if record["publication_state"] not in PUBLICATION_STATES:
            raise ValueError(
                f"invalid publication state: {record['publication_state']}"
            )
        expected_path = self.parquet_path(snapshot_date, version)
        expected_staged = self.staged_path(snapshot_date, version)
        if Path(record["final_parquet_path"]) != expected_path:
            raise ValueError("publication final Parquet path does not match identity")
        if Path(record["staged_parquet_path"]) != expected_staged:
            raise ValueError("publication staged Parquet path does not match identity")

        if record["publication_state"] == "complete":
            try:
                self.require_complete(snapshot_date, version)
                expected_staged.unlink(missing_ok=True)
                return {"state_found": "complete", "action": "none", "state": "complete"}
            except ValueError as exc:
                self._mark_recovery_required(snapshot_date, version, exc)
                record["publication_state"] = "recovery_required"

        authoritative = self._read_duckdb_slice(snapshot_date, version)
        actual_fingerprint = classification_fingerprint(authoritative)
        if len(authoritative) != record["expected_row_count"]:
            raise ValueError("committed DuckDB row count disagrees with publication record")
        if actual_fingerprint != record["content_fingerprint"]:
            raise ValueError("committed DuckDB fingerprint disagrees with publication record")

        action = "verified_existing_final"
        if not self._parquet_matches_record(expected_path, record):
            if self._parquet_matches_record(expected_staged, record):
                action = "published_staged_parquet"
            else:
                expected_staged.unlink(missing_ok=True)
                expected_staged.parent.mkdir(parents=True, exist_ok=True)
                authoritative.to_parquet(expected_staged, index=False)
                self._fsync_file(expected_staged)
                action = "regenerated_and_published_parquet"
            self.atomic_replace(expected_staged, expected_path)
        else:
            expected_staged.unlink(missing_ok=True)

        self._verify_committed_output(snapshot_date, version)
        self._mark_complete(snapshot_date, version)
        return {
            "state_found": record["publication_state"],
            "action": action,
            "state": "complete",
        }

    def require_complete(self, snapshot: str | date, policy_version: str) -> dict[str, Any]:
        snapshot_date = date.fromisoformat(str(snapshot))
        record = self.publication_record(snapshot_date, policy_version)
        if not record:
            raise ValueError(
                f"exposure classification publication absent: "
                f"{snapshot_date}/{policy_version}"
            )
        if record["publication_state"] != "complete":
            raise ValueError(
                "exposure classification publication is not complete: "
                f"{record['publication_state']}"
            )
        self._verify_committed_output(snapshot_date, policy_version)
        if self.staged_path(snapshot_date, policy_version).exists():
            raise ValueError("unexplained staged exposure-classification file remains")
        return record

    def publication_record(
        self, snapshot: str | date, policy_version: str
    ) -> dict[str, Any] | None:
        if not self.duckdb_path.exists():
            return None
        snapshot_date = date.fromisoformat(str(snapshot))
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            exists = connection.execute(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'exposure_classification_publication'
                """
            ).fetchone()[0]
            if not exists:
                return None
            row = connection.execute(
                """
                SELECT snapshot_date, policy_version, publication_state,
                       expected_row_count, content_fingerprint,
                       final_parquet_path, staged_parquet_path, failure_message
                FROM exposure_classification_publication
                WHERE snapshot_date = ? AND policy_version = ?
                """,
                [snapshot_date, policy_version],
            ).fetchone()
        if not row:
            return None
        keys = [
            "snapshot_date",
            "policy_version",
            "publication_state",
            "expected_row_count",
            "content_fingerprint",
            "final_parquet_path",
            "staged_parquet_path",
            "failure_message",
        ]
        return dict(zip(keys, row, strict=True))

    def parquet_path(self, snapshot: date, policy_version: str) -> Path:
        return (
            self.parquet_directory
            / f"snapshot_date={snapshot.isoformat()}"
            / f"policy_version={policy_version}"
            / "security_exposure_classification.parquet"
        )

    def staged_path(self, snapshot: date, policy_version: str) -> Path:
        return self.parquet_path(snapshot, policy_version).with_name(
            ".security_exposure_classification.staged.parquet"
        )

    @staticmethod
    def _ensure_tables(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS security_exposure_classification (
                snapshot_date DATE NOT NULL,
                ticker VARCHAR NOT NULL,
                policy_version VARCHAR NOT NULL,
                exposure_scope VARCHAR NOT NULL,
                classification_method VARCHAR NOT NULL,
                underlying_ticker VARCHAR,
                policy_reason VARCHAR NOT NULL,
                classification_provenance VARCHAR NOT NULL,
                UNIQUE(snapshot_date, ticker, policy_version)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS exposure_classification_publication (
                snapshot_date DATE NOT NULL,
                policy_version VARCHAR NOT NULL,
                publication_state VARCHAR NOT NULL CHECK (
                    publication_state IN (
                        'pending', 'complete', 'recovery_required'
                    )
                ),
                expected_row_count BIGINT NOT NULL,
                content_fingerprint VARCHAR NOT NULL,
                final_parquet_path VARCHAR NOT NULL,
                staged_parquet_path VARCHAR NOT NULL,
                failure_message VARCHAR,
                updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
                UNIQUE(snapshot_date, policy_version)
            )
            """
        )

    def _read_duckdb_slice(
        self, snapshot: date, policy_version: str
    ) -> pd.DataFrame:
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            frame = connection.execute(
                f"""
                SELECT {", ".join(CLASSIFICATION_COLUMNS)}
                FROM security_exposure_classification
                WHERE snapshot_date = ? AND policy_version = ?
                ORDER BY ticker
                """,
                [snapshot, policy_version],
            ).fetchdf()
        return canonicalize_classification(frame)

    def _parquet_matches_record(self, path: Path, record: dict[str, Any]) -> bool:
        if not path.exists():
            return False
        try:
            frame = canonicalize_classification(pd.read_parquet(path))
            return (
                len(frame) == record["expected_row_count"]
                and classification_fingerprint(frame)
                == record["content_fingerprint"]
            )
        except Exception:
            return False

    def _verify_committed_output(self, snapshot: date, policy_version: str) -> None:
        record = self.publication_record(snapshot, policy_version)
        if not record:
            raise ValueError("publication record disappeared during verification")
        duckdb_frame = self._read_duckdb_slice(snapshot, policy_version)
        path = self.parquet_path(snapshot, policy_version)
        if not path.exists():
            raise ValueError("published exposure-classification Parquet is missing")
        parquet_frame = canonicalize_classification(pd.read_parquet(path))
        agreement = compare_classification_frames(duckdb_frame, parquet_frame)
        if agreement["has_mismatch"]:
            raise ValueError(
                "DuckDB/Parquet exposure classification mismatch: "
                f"{agreement['summary']}"
            )
        if len(duckdb_frame) != record["expected_row_count"]:
            raise ValueError("published row count disagrees with publication record")
        fingerprint = classification_fingerprint(duckdb_frame)
        if fingerprint != record["content_fingerprint"]:
            raise ValueError("published fingerprint disagrees with publication record")

    def _mark_complete(self, snapshot: date, policy_version: str) -> None:
        with duckdb.connect(str(self.duckdb_path)) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.execute(
                    """
                    UPDATE exposure_classification_publication
                    SET publication_state = 'complete',
                        failure_message = NULL,
                        updated_at = current_timestamp
                    WHERE snapshot_date = ? AND policy_version = ?
                    """,
                    [snapshot, policy_version],
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _mark_recovery_required(
        self, snapshot: date, policy_version: str, error: Exception
    ) -> None:
        message = _sanitize_failure(error)
        with duckdb.connect(str(self.duckdb_path)) as connection:
            connection.execute(
                """
                UPDATE exposure_classification_publication
                SET publication_state = 'recovery_required',
                    failure_message = ?,
                    updated_at = current_timestamp
                WHERE snapshot_date = ? AND policy_version = ?
                """,
                [message, snapshot, policy_version],
            )

    def _checkpoint(self, point: str) -> None:
        if self.failure_injector:
            self.failure_injector(point)

    @staticmethod
    def _fsync_file(path: Path) -> None:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())

    @staticmethod
    def _replace(source: Path, target: Path) -> None:
        source.replace(target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def canonicalize_classification(frame: pd.DataFrame) -> pd.DataFrame:
    missing = set(CLASSIFICATION_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"classification frame missing columns: {sorted(missing)}")
    result = frame.loc[:, CLASSIFICATION_COLUMNS].copy()
    result["snapshot_date"] = pd.to_datetime(result["snapshot_date"]).dt.date
    for column in CLASSIFICATION_COLUMNS[1:]:
        result[column] = result[column].astype("string")
    result["underlying_ticker"] = result["underlying_ticker"].replace(
        {"": pd.NA}
    )
    return result.sort_values(CLASSIFICATION_KEY, kind="stable").reset_index(drop=True)


def classification_fingerprint(frame: pd.DataFrame) -> str:
    canonical = canonicalize_classification(frame)
    digest = hashlib.sha256()
    for row in canonical.itertuples(index=False, name=None):
        values = [
            value.isoformat()
            if isinstance(value, date)
            else None
            if pd.isna(value)
            else str(value)
            for value in row
        ]
        digest.update(
            json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def compare_classification_frames(
    duckdb_frame: pd.DataFrame, parquet_frame: pd.DataFrame
) -> dict[str, Any]:
    left = canonicalize_classification(duckdb_frame)
    right = canonicalize_classification(parquet_frame)
    left_duplicates = int(left.duplicated(CLASSIFICATION_KEY, keep=False).sum())
    right_duplicates = int(right.duplicated(CLASSIFICATION_KEY, keep=False).sum())
    left_keys = set(map(tuple, left[CLASSIFICATION_KEY].itertuples(index=False, name=None)))
    right_keys = set(map(tuple, right[CLASSIFICATION_KEY].itertuples(index=False, name=None)))
    missing_keys = sorted(left_keys - right_keys)
    extra_keys = sorted(right_keys - left_keys)
    field_mismatches: dict[str, int] = {}
    affected_keys: set[tuple[Any, ...]] = set(missing_keys) | set(extra_keys)
    if not left_duplicates and not right_duplicates:
        merged = left.merge(
            right,
            on=CLASSIFICATION_KEY,
            how="inner",
            suffixes=("_duckdb", "_parquet"),
            validate="one_to_one",
        )
        for column in [item for item in CLASSIFICATION_COLUMNS if item not in CLASSIFICATION_KEY]:
            left_values = merged[f"{column}_duckdb"].fillna("<NULL>")
            right_values = merged[f"{column}_parquet"].fillna("<NULL>")
            mismatch = left_values.ne(right_values)
            field_mismatches[column] = int(mismatch.sum())
            affected_keys.update(
                map(
                    tuple,
                    merged.loc[mismatch, CLASSIFICATION_KEY].itertuples(
                        index=False, name=None
                    ),
                )
            )
    else:
        field_mismatches = {
            column: 0
            for column in CLASSIFICATION_COLUMNS
            if column not in CLASSIFICATION_KEY
        }
    has_mismatch = bool(
        len(left) != len(right)
        or left_duplicates
        or right_duplicates
        or missing_keys
        or extra_keys
        or any(field_mismatches.values())
    )
    summary = {
        "duckdb_rows": len(left),
        "parquet_rows": len(right),
        "duckdb_duplicate_rows": left_duplicates,
        "parquet_duplicate_rows": right_duplicates,
        "missing_keys": len(missing_keys),
        "extra_keys": len(extra_keys),
        "field_mismatches": field_mismatches,
    }
    return {
        **summary,
        "missing_key_values": missing_keys,
        "extra_key_values": extra_keys,
        "affected_keys": sorted(affected_keys),
        "duckdb_fingerprint": classification_fingerprint(left),
        "parquet_fingerprint": classification_fingerprint(right),
        "has_mismatch": has_mismatch,
        "summary": summary,
    }


def _frame_identity(frame: pd.DataFrame) -> tuple[date, str]:
    snapshots = set(frame["snapshot_date"])
    versions = set(frame["policy_version"].astype(str))
    if len(snapshots) != 1 or len(versions) != 1:
        raise ValueError("classification frame must contain one snapshot and policy")
    return next(iter(snapshots)), next(iter(versions))


def _sanitize_failure(error: Exception) -> str:
    message = re.sub(
        r"(?i)(api[_-]?key|authorization|bearer|secret|token)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        str(error),
    )
    return message[:500]


def _validate_classification_frame(frame: pd.DataFrame) -> None:
    missing = set(CLASSIFICATION_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"classification frame missing columns: {sorted(missing)}")
    if frame["policy_version"].astype(str).str.strip().eq("").any():
        raise ValueError("classification policy version cannot be empty")
    invalid = set(frame["exposure_scope"]) - EXPOSURE_SCOPES
    if invalid:
        raise ValueError(f"invalid exposure scopes: {sorted(invalid)}")
    if frame.duplicated(["snapshot_date", "ticker", "policy_version"]).any():
        raise ValueError("duplicate snapshot/ticker/policy classification")
    needs_reason = frame["exposure_scope"].isin(["single_security", "review_needed"])
    if frame.loc[needs_reason, "policy_reason"].astype(str).str.strip().eq("").any():
        raise ValueError("single-security and review classifications require a reason")
    known = set(frame["ticker"].astype(str).str.upper())
    supplied = set(
        frame.loc[frame["underlying_ticker"].notna(), "underlying_ticker"]
        .astype(str)
        .str.upper()
    )
    if supplied - known:
        raise ValueError(f"unknown underlying tickers: {sorted(supplied - known)}")


def _ranges_overlap(left: ExposureOverride, right: ExposureOverride) -> bool:
    left_end = left.effective_end_date or date.max
    right_end = right.effective_end_date or date.max
    return left.effective_start_date <= right_end and right.effective_start_date <= left_end
