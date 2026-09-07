"""Reviewed representation authority, never historical publication attestation."""

import math
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field

from market_dashboard.aperture.contracts import ContractModel
from market_dashboard.aperture.leadership import fingerprint


class AdjustedAuthorityV1(ContractModel):
    version: Literal["massive-adjusted-authority-v1"] = "massive-adjusted-authority-v1"
    reviewed_on: Literal["2026-09-06"] = "2026-09-06"
    data_vendor: Literal["Massive.com"] = "Massive.com"
    dataset_id: Literal["stocks-custom-daily-aggregates"] = (
        "stocks-custom-daily-aggregates"
    )
    price_basis: Literal["split_adjusted"] = "split_adjusted"
    dividend_treatment: Literal["not_dividend_total_return_adjusted"] = (
        "not_dividend_total_return_adjusted"
    )
    volume_convention: Literal["provider_returned_split_adjusted_numeric"] = (
        "provider_returned_split_adjusted_numeric"
    )
    volume_storage: Literal["DOUBLE"] = "DOUBLE"
    historical_authority: Literal["reviewed_existing_parquet_values"] = (
        "reviewed_existing_parquet_values"
    )
    authenticates_missing_receipts: Literal[False] = False
    calendar_id: Literal["XNYS"] = "XNYS"
    calendar_package: Literal["exchange-calendars==4.13.2"] = (
        "exchange-calendars==4.13.2"
    )


AUTHORITY = AdjustedAuthorityV1()


class AggregateResponseEvidenceV1(ContractModel):
    schema_version: Literal["adjusted-response-evidence-v1"] = (
        "adjusted-response-evidence-v1"
    )
    endpoint_class: Literal["GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}"] = (
        "GET /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}"
    )
    source_version: Literal["massive-adjusted-authority-v1"] = AUTHORITY.version
    ticker: str = Field(pattern=r"^[A-Z0-9][A-Z0-9.\-]*$")
    requested_adjusted: Literal[True] = True
    returned_adjusted: bool | None
    requested_start: date
    requested_end: date
    observed_start: date | None
    observed_end: date | None
    rows: int = Field(ge=0)
    mapped_artifact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    http_status: Literal[200] = 200


def response_evidence(ticker, start, end, payload, mapped):
    """Allowlist only; no raw body, URL, header, query or request ID is retained."""
    adjusted = payload.get("adjusted")
    if adjusted is not None and adjusted is not True:
        raise ValueError("ADJUSTED_RESPONSE_BASIS_MISMATCH")
    if payload.get("next_url"):
        raise ValueError("UNEXPECTED_AGGREGATE_PAGINATION")
    if payload.get("ticker", ticker) != ticker:
        raise ValueError("AGGREGATE_IDENTITY_MISMATCH")
    for row in mapped:
        v, n = row["volume"], row["transactions"]
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or v < 0
        ):
            raise ValueError("INVALID_PROVIDER_NUMERIC_VOLUME")
        if isinstance(v, int) and int(float(v)) != v:
            raise ValueError("PROVIDER_VOLUME_NOT_EXACT_DOUBLE")
        if n is not None and (
            isinstance(n, bool)
            or not isinstance(n, (int, float))
            or not math.isfinite(n)
            or n < 0
            or int(n) != n
        ):
            raise ValueError("INVALID_INTEGRAL_TRANSACTION_COUNT")
    days = sorted(date.fromisoformat(row["date"]) for row in mapped)
    first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if first > last or any(d < first or d > last for d in days):
        raise ValueError("AGGREGATE_RESPONSE_OUTSIDE_REQUEST")
    return AggregateResponseEvidenceV1(
        ticker=ticker,
        returned_adjusted=adjusted,
        requested_start=first,
        requested_end=last,
        observed_start=days[0] if days else None,
        observed_end=days[-1] if days else None,
        rows=len(mapped),
        mapped_artifact_fingerprint=fingerprint(mapped),
    )


def require_double_volume(connection, table="daily_bars"):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", table):
        raise ValueError("UNSUPPORTED_VOLUME_TABLE")
    columns = connection.execute(
        "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='main' AND table_name=?",
        [table],
    ).fetchall()
    if columns and dict(columns).get("volume") != "DOUBLE":
        raise ValueError("ADJUSTED_VOLUME_MIGRATION_REQUIRED:" + table)


def check_volume_schema(path, tables=("daily_bars",)):
    """Preflight before requests, manifests, Parquet writes or feature mutation."""
    path = Path(path)
    if not path.exists():
        return
    import duckdb

    with duckdb.connect(
        str(path), read_only=True, config={"enable_external_access": False}
    ) as connection:
        for table in tables:
            require_double_volume(connection, table)
