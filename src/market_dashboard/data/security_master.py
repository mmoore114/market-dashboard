from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


SECURITY_MASTER_COLUMNS = [
    "snapshot_date",
    "ticker",
    "name",
    "market",
    "locale",
    "primary_exchange",
    "security_type",
    "active",
    "currency",
    "cik",
    "composite_figi",
    "share_class_figi",
    "last_updated_utc",
    "normalized_exchange",
    "normalized_category",
    "candidate_eligible",
    "exclusion_reason",
    "ingested_at",
]


@dataclass(frozen=True)
class CandidateClassification:
    normalized_exchange: str
    normalized_category: str
    candidate_eligible: bool
    exclusion_reason: str | None


@dataclass(frozen=True)
class SecurityMasterSummary:
    snapshot_date: str
    rows_fetched: int
    rows_written_to_parquet: int
    rows_written_to_duckdb: int
    unique_tickers: int
    candidate_tickers: int
    parquet_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SecurityMasterClassifier:
    """Normalize provider codes and apply configured structural universe filters."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.exchange_mapping = {
            str(code).upper(): str(name)
            for code, name in config.get("exchange_mapping", {}).items()
        }
        self.type_mapping = {
            str(code).upper(): str(category)
            for code, category in config.get("security_type_mapping", {}).items()
        }
        filters = config["candidate_filters"]
        self.required_locale = str(filters["locale"]).lower()
        self.active_only = bool(filters["active_only"])
        self.allowed_exchange_mics = {
            str(code).upper() for code in filters["allowed_exchange_mics"]
        }
        self.allowed_categories = {str(value) for value in filters["allowed_categories"]}
        self.excluded_security_types = {
            str(code).upper(): str(reason)
            for code, reason in filters.get("excluded_security_types", {}).items()
        }
        self.acquisition_patterns = [
            str(pattern).strip().lower()
            for pattern in filters.get("acquisition_vehicle_name_patterns", [])
            if str(pattern).strip()
        ]

    def normalize_exchange(self, raw_exchange: object) -> str:
        code = _clean_string(raw_exchange).upper()
        if not code:
            return "Review Needed"
        return self.exchange_mapping.get(code, "Review Needed")

    def normalize_type(self, raw_type: object) -> str:
        code = _clean_string(raw_type).upper()
        if not code:
            return "Review Needed"
        return self.type_mapping.get(code, "Review Needed")

    def classify(self, record: dict[str, Any]) -> CandidateClassification:
        raw_exchange = _clean_string(record.get("primary_exchange")).upper()
        normalized_exchange = self.normalize_exchange(raw_exchange)
        normalized_category = self.normalize_type(record.get("type"))
        name = _clean_string(record.get("name")).lower()
        locale = _clean_string(record.get("locale")).lower()
        market = _clean_string(record.get("market")).lower()
        active = record.get("active") is True

        reason: str | None = None
        if not _clean_string(record.get("ticker")):
            reason = "missing_ticker"
        elif self.active_only and not active:
            reason = "inactive"
        elif locale != self.required_locale:
            reason = "non_us_locale"
        elif market == "otc" or raw_exchange.startswith("OTC"):
            reason = "otc"
        elif normalized_category == "Review Needed":
            reason = "unknown_security_type"
        elif normalized_exchange == "Review Needed":
            reason = "unknown_exchange"
        elif raw_exchange not in self.allowed_exchange_mics:
            reason = "exchange_not_allowed"
        elif _clean_string(record.get("type")).upper() in self.excluded_security_types:
            reason = self.excluded_security_types[
                _clean_string(record.get("type")).upper()
            ]
        elif normalized_category not in self.allowed_categories:
            reason = _category_exclusion_reason(normalized_category)
        elif any(pattern in name for pattern in self.acquisition_patterns):
            reason = "acquisition_vehicle"

        return CandidateClassification(
            normalized_exchange=normalized_exchange,
            normalized_category=normalized_category,
            candidate_eligible=reason is None,
            exclusion_reason=reason,
        )


class SecurityMasterStore:
    """Persist auditable dated security-master snapshots in DuckDB and Parquet."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "security_master",
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def persist(
        self,
        records: Iterable[dict[str, Any]],
        snapshot_date: str | date,
        classifier: SecurityMasterClassifier,
    ) -> dict[str, Any]:
        snapshot = date.fromisoformat(str(snapshot_date))
        frame = self._build_frame(records, snapshot, classifier)
        parquet_path = self.parquet_path(snapshot)
        self._write_parquet(frame, parquet_path)
        self._write_duckdb(frame, snapshot)
        return SecurityMasterSummary(
            snapshot_date=snapshot.isoformat(),
            rows_fetched=len(frame),
            rows_written_to_parquet=len(frame),
            rows_written_to_duckdb=len(frame),
            unique_tickers=int(frame["ticker"].nunique()) if not frame.empty else 0,
            candidate_tickers=int(frame["candidate_eligible"].sum()) if not frame.empty else 0,
            parquet_path=str(parquet_path),
        ).to_dict()

    def reclassify_snapshot(
        self,
        snapshot_date: str | date,
        classifier: SecurityMasterClassifier,
    ) -> dict[str, Any]:
        snapshot = date.fromisoformat(str(snapshot_date))
        with duckdb.connect(str(self.duckdb_path), read_only=True) as connection:
            rows = connection.execute(
                """
                SELECT ticker, name, market, locale, primary_exchange,
                       security_type, active, currency, cik, composite_figi,
                       share_class_figi, last_updated_utc
                FROM security_master
                WHERE snapshot_date = ?
                ORDER BY ticker
                """,
                [snapshot],
            ).fetchall()
        if not rows:
            raise ValueError(f"security master snapshot not found: {snapshot}")
        records = [
            {
                "ticker": row[0],
                "name": row[1],
                "market": row[2],
                "locale": row[3],
                "primary_exchange": row[4],
                "type": row[5],
                "active": row[6],
                "currency_symbol": row[7],
                "cik": row[8],
                "composite_figi": row[9],
                "share_class_figi": row[10],
                "last_updated_utc": row[11],
            }
            for row in rows
        ]
        return self.persist(records, snapshot, classifier)

    def parquet_path(self, snapshot_date: date) -> Path:
        return (
            self.parquet_directory
            / f"snapshot_date={snapshot_date.isoformat()}"
            / "security_master.parquet"
        )

    def _build_frame(
        self,
        records: Iterable[dict[str, Any]],
        snapshot_date: date,
        classifier: SecurityMasterClassifier,
    ) -> pd.DataFrame:
        ingested_at = datetime.now(tz=UTC).replace(tzinfo=None)
        rows: list[dict[str, Any]] = []
        for record in records:
            classification = classifier.classify(record)
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "ticker": _clean_string(record.get("ticker")).upper() or None,
                    "name": _clean_string(record.get("name")) or None,
                    "market": _clean_string(record.get("market")).lower() or None,
                    "locale": _clean_string(record.get("locale")).lower() or None,
                    "primary_exchange": (
                        _clean_string(record.get("primary_exchange")).upper() or None
                    ),
                    "security_type": _clean_string(record.get("type")).upper() or None,
                    "active": record.get("active"),
                    "currency": (
                        _clean_string(
                            record.get("currency_symbol") or record.get("currency_name")
                        ).upper()
                        or None
                    ),
                    "cik": _clean_string(record.get("cik")) or None,
                    "composite_figi": _clean_string(record.get("composite_figi")) or None,
                    "share_class_figi": _clean_string(record.get("share_class_figi")) or None,
                    "last_updated_utc": pd.to_datetime(
                        record.get("last_updated_utc"),
                        errors="coerce",
                        utc=True,
                    ).tz_localize(None),
                    "normalized_exchange": classification.normalized_exchange,
                    "normalized_category": classification.normalized_category,
                    "candidate_eligible": classification.candidate_eligible,
                    "exclusion_reason": classification.exclusion_reason,
                    "ingested_at": ingested_at,
                }
            )

        frame = pd.DataFrame(rows, columns=SECURITY_MASTER_COLUMNS)
        if frame.empty:
            return frame
        frame = (
            frame.drop_duplicates(subset=["snapshot_date", "ticker"], keep="last")
            .sort_values(["snapshot_date", "ticker"], na_position="last")
            .reset_index(drop=True)
        )
        return frame

    def _write_parquet(self, frame: pd.DataFrame, parquet_path: Path) -> None:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            suffix=".parquet",
            prefix=".security_master.",
            dir=parquet_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            frame.to_parquet(temp_path, index=False)
            temp_path.replace(parquet_path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _write_duckdb(self, frame: pd.DataFrame, snapshot_date: date) -> None:
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_table(connection)
            connection.execute("BEGIN TRANSACTION")
            try:
                if not frame.empty:
                    connection.register("incoming_security_master", frame)
                    connection.execute(
                        f"""
                        INSERT OR REPLACE INTO security_master (
                            {", ".join(SECURITY_MASTER_COLUMNS)}
                        )
                        SELECT {", ".join(SECURITY_MASTER_COLUMNS)}
                        FROM incoming_security_master
                        """
                    )
                    connection.execute(
                        """
                        DELETE FROM security_master
                        WHERE snapshot_date = ?
                          AND ticker NOT IN (
                            SELECT ticker FROM incoming_security_master
                          )
                        """,
                        [snapshot_date],
                    )
                    connection.unregister("incoming_security_master")
                else:
                    connection.execute(
                        "DELETE FROM security_master WHERE snapshot_date = ?",
                        [snapshot_date],
                    )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _ensure_table(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS security_master (
                snapshot_date DATE NOT NULL,
                ticker VARCHAR NOT NULL,
                name VARCHAR,
                market VARCHAR,
                locale VARCHAR,
                primary_exchange VARCHAR,
                security_type VARCHAR,
                active BOOLEAN,
                currency VARCHAR,
                cik VARCHAR,
                composite_figi VARCHAR,
                share_class_figi VARCHAR,
                last_updated_utc TIMESTAMP,
                normalized_exchange VARCHAR NOT NULL,
                normalized_category VARCHAR NOT NULL,
                candidate_eligible BOOLEAN NOT NULL,
                exclusion_reason VARCHAR,
                ingested_at TIMESTAMP NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_security_master_snapshot_ticker
            ON security_master (snapshot_date, ticker)
            """
        )


def _clean_string(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _category_exclusion_reason(category: str) -> str:
    return {
        "Preferred Share": "preferred_share",
        "Warrant": "warrant",
        "Right": "right",
        "Unit": "unit",
        "Depositary Receipt": "depositary_receipt",
        "Fund": "unsupported_fund",
        "Exchange Traded Note": "exchange_traded_note",
        "Exchange Traded Vehicle": "exchange_traded_vehicle",
        "Structured Product": "structured_product",
        "Other Security": "unsupported_instrument_type",
    }.get(category, "unsupported_instrument_type")
