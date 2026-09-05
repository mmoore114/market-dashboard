from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


SOURCE_PROVIDER = "deepvue"
SOURCE_TAXONOMY = "deepvue_sub_industry"
EXPECTED_COLUMNS = {
    "Symbol",
    "Industry Rank - 3 Month",
    "Sub-Industry",
}
SYMBOL_COLUMNS = [
    "source_as_of_date",
    "ticker",
    "source_provider",
    "source_taxonomy",
    "sub_industry",
    "industry_rank_3m",
    "classification_status",
    "source_row_fingerprint",
    "ingested_at",
]
GROUP_COLUMNS = [
    "source_as_of_date",
    "source_provider",
    "source_taxonomy",
    "sub_industry",
    "industry_rank_3m",
    "rank_status",
    "constituent_count",
    "ranked_constituent_count",
    "ingested_at",
]


@dataclass(frozen=True)
class DeepvueTaxonomySummary:
    source_as_of_date: str
    source_rows: int
    unique_tickers: int
    classified_tickers: int
    unclassified_tickers: int
    unique_sub_industries: int
    ranked_tickers: int
    publishable_group_ranks: int
    ambiguous_group_ranks: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeepvueTaxonomyNormalizer:
    """Normalize a dated Deepvue screener export without inferring missing levels."""

    def read_csv(
        self,
        csv_path: str | Path,
        source_as_of_date: str | date,
    ) -> pd.DataFrame:
        snapshot = date.fromisoformat(str(source_as_of_date))
        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        missing = EXPECTED_COLUMNS.difference(raw.columns)
        if missing:
            raise ValueError(
                "Deepvue export is missing required columns: "
                + ", ".join(sorted(missing))
            )

        raw = raw.copy()
        raw["ticker"] = raw["Symbol"].map(_clean_ticker)
        if raw["ticker"].eq("").any():
            raise ValueError("Deepvue export contains a blank symbol")
        duplicates = raw.loc[raw["ticker"].duplicated(keep=False), "ticker"].unique()
        if len(duplicates):
            sample = ", ".join(sorted(duplicates)[:10])
            raise ValueError(f"Deepvue export contains duplicate symbols: {sample}")

        raw["sub_industry"] = raw["Sub-Industry"].map(_clean_classification)
        rank = pd.to_numeric(raw["Industry Rank - 3 Month"], errors="coerce")
        non_integral = rank.notna() & rank.mod(1).ne(0)
        if non_integral.any():
            raise ValueError("Deepvue industry ranks must be whole numbers")
        if (rank.dropna() <= 0).any():
            raise ValueError("Deepvue industry ranks must be positive")

        ingested_at = datetime.now(tz=UTC).replace(tzinfo=None)
        frame = pd.DataFrame(
            {
                "source_as_of_date": snapshot,
                "ticker": raw["ticker"],
                "source_provider": SOURCE_PROVIDER,
                "source_taxonomy": SOURCE_TAXONOMY,
                "sub_industry": raw["sub_industry"],
                "industry_rank_3m": rank.astype("Int64"),
                "classification_status": raw["sub_industry"].map(
                    lambda value: "CLASSIFIED" if value is not None else "UNCLASSIFIED"
                ),
                "ingested_at": ingested_at,
            }
        )
        frame["source_row_fingerprint"] = frame.apply(_row_fingerprint, axis=1)
        return frame[SYMBOL_COLUMNS].sort_values("ticker").reset_index(drop=True)

    def build_group_snapshot(self, symbols: pd.DataFrame) -> pd.DataFrame:
        classified = symbols.loc[symbols["sub_industry"].notna()].copy()
        rows: list[dict[str, Any]] = []
        for sub_industry, members in classified.groupby("sub_industry", sort=True):
            ranks = sorted(
                {int(value) for value in members["industry_rank_3m"].dropna().tolist()}
            )
            if len(ranks) == 1:
                rank_status = "CONSISTENT"
                published_rank: int | None = ranks[0]
            elif len(ranks) == 0:
                rank_status = "MISSING"
                published_rank = None
            else:
                rank_status = "AMBIGUOUS"
                published_rank = None
            rows.append(
                {
                    "source_as_of_date": members["source_as_of_date"].iloc[0],
                    "source_provider": SOURCE_PROVIDER,
                    "source_taxonomy": SOURCE_TAXONOMY,
                    "sub_industry": sub_industry,
                    "industry_rank_3m": published_rank,
                    "rank_status": rank_status,
                    "constituent_count": len(members),
                    "ranked_constituent_count": int(
                        members["industry_rank_3m"].notna().sum()
                    ),
                    "ingested_at": members["ingested_at"].iloc[0],
                }
            )
        return pd.DataFrame(rows, columns=GROUP_COLUMNS)

    def summarize(
        self,
        symbols: pd.DataFrame,
        groups: pd.DataFrame,
    ) -> DeepvueTaxonomySummary:
        classified = symbols["classification_status"].eq("CLASSIFIED")
        return DeepvueTaxonomySummary(
            source_as_of_date=str(symbols["source_as_of_date"].iloc[0]),
            source_rows=len(symbols),
            unique_tickers=int(symbols["ticker"].nunique()),
            classified_tickers=int(classified.sum()),
            unclassified_tickers=int((~classified).sum()),
            unique_sub_industries=int(groups["sub_industry"].nunique()),
            ranked_tickers=int(symbols["industry_rank_3m"].notna().sum()),
            publishable_group_ranks=int(groups["rank_status"].eq("CONSISTENT").sum()),
            ambiguous_group_ranks=int(groups["rank_status"].eq("AMBIGUOUS").sum()),
        )


class DeepvueTaxonomyStore:
    """Persist normalized snapshots; raw Deepvue exports remain outside Git."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "deepvue_taxonomy",
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def persist(
        self,
        symbols: pd.DataFrame,
        groups: pd.DataFrame,
    ) -> tuple[Path, Path]:
        if symbols.empty:
            raise ValueError("cannot persist an empty Deepvue taxonomy snapshot")
        snapshot = date.fromisoformat(str(symbols["source_as_of_date"].iloc[0]))
        symbol_path = self._path(snapshot, "symbol_classification.parquet")
        group_path = self._path(snapshot, "group_rank.parquet")
        _atomic_parquet(symbols, symbol_path)
        _atomic_parquet(groups, group_path)
        self._write_duckdb(symbols, groups, snapshot)
        return symbol_path, group_path

    def _path(self, snapshot: date, filename: str) -> Path:
        return self.parquet_directory / f"source_as_of_date={snapshot.isoformat()}" / filename

    def _write_duckdb(
        self,
        symbols: pd.DataFrame,
        groups: pd.DataFrame,
        snapshot: date,
    ) -> None:
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.duckdb_path)) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.register("incoming_deepvue_symbols", symbols)
                connection.register("incoming_deepvue_groups", groups)
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS deepvue_symbol_classification AS "
                    "SELECT * FROM incoming_deepvue_symbols WHERE FALSE"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS deepvue_group_rank AS "
                    "SELECT * FROM incoming_deepvue_groups WHERE FALSE"
                )
                connection.execute(
                    "DELETE FROM deepvue_symbol_classification WHERE source_as_of_date = ?",
                    [snapshot],
                )
                connection.execute(
                    "DELETE FROM deepvue_group_rank WHERE source_as_of_date = ?",
                    [snapshot],
                )
                connection.execute(
                    "INSERT INTO deepvue_symbol_classification SELECT * FROM incoming_deepvue_symbols"
                )
                connection.execute(
                    "INSERT INTO deepvue_group_rank SELECT * FROM incoming_deepvue_groups"
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise


def _clean_ticker(value: object) -> str:
    return str(value).strip().upper()


def _clean_classification(value: object) -> str | None:
    cleaned = str(value).strip()
    if cleaned.lower() in {"", "-", "—", "n/a", "na", "nan", "none"}:
        return None
    return cleaned


def _row_fingerprint(row: pd.Series) -> str:
    rank = "" if pd.isna(row["industry_rank_3m"]) else str(int(row["industry_rank_3m"]))
    payload = "|".join(
        [
            str(row["source_as_of_date"]),
            row["ticker"],
            row["sub_industry"] or "",
            rank,
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _atomic_parquet(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        suffix=".parquet",
        prefix=f".{destination.stem}.",
        dir=destination.parent,
        delete=False,
    ) as temp_file:
        temp_path = Path(temp_file.name)
    try:
        frame.to_parquet(temp_path, index=False)
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()
