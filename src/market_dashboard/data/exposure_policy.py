from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Any, Iterable

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
    """Persist versioned derived classifications without changing provider facts."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "exposure_classification",
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def persist(self, frame: pd.DataFrame) -> Path:
        if frame.empty:
            raise ValueError("cannot persist an empty exposure classification")
        _validate_classification_frame(frame)
        snapshot = pd.Timestamp(frame["snapshot_date"].iloc[0]).date()
        version = str(frame["policy_version"].iloc[0])
        path = self.parquet_path(snapshot, version)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(suffix=".parquet", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            frame.to_parquet(temporary, index=False)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
        with duckdb.connect(str(self.duckdb_path)) as connection:
            self._ensure_table(connection)
            connection.register("incoming_exposure_classification", frame)
            connection.execute(
                f"""
                INSERT OR REPLACE INTO security_exposure_classification
                ({", ".join(CLASSIFICATION_COLUMNS)})
                SELECT {", ".join(CLASSIFICATION_COLUMNS)}
                FROM incoming_exposure_classification
                """
            )
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
        return path

    def parquet_path(self, snapshot: date, policy_version: str) -> Path:
        return (
            self.parquet_directory
            / f"snapshot_date={snapshot.isoformat()}"
            / f"policy_version={policy_version}"
            / "security_exposure_classification.parquet"
        )

    @staticmethod
    def _ensure_table(connection: duckdb.DuckDBPyConnection) -> None:
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
