from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from market_dashboard.data.deepvue_taxonomy import _atomic_parquet, _clean_ticker
from market_dashboard.data.storage import DUCKDB_PATH, PROCESSED_DIRECTORY


SOURCE_PROVIDER = "deepvue"
SOURCE_TAXONOMY = "deepvue_theme_tracker"
EXPECTED_COLUMNS = {"Theme", "Symbol"}
CATALOG_COLUMNS = [
    "source_as_of_date",
    "source_provider",
    "source_taxonomy",
    "theme",
    "constituent_count",
    "membership_status",
    "source_row_fingerprint",
    "ingested_at",
]
MEMBERSHIP_COLUMNS = [
    "source_as_of_date",
    "ticker",
    "source_provider",
    "source_taxonomy",
    "theme",
    "source_row_fingerprint",
    "ingested_at",
]


@dataclass(frozen=True)
class DeepvueThemeSummary:
    source_as_of_date: str
    source_rows: int
    unique_themes: int
    populated_themes: int
    empty_themes: int
    membership_rows: int
    unique_tickers: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeepvueThemeNormalizer:
    """Normalize an explicitly captured Theme Tracker membership snapshot."""

    def read_csv(
        self,
        csv_path: str | Path,
        source_as_of_date: str | date,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        snapshot = date.fromisoformat(str(source_as_of_date))
        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        missing = EXPECTED_COLUMNS.difference(raw.columns)
        if missing:
            raise ValueError(
                "Deepvue theme snapshot is missing required columns: "
                + ", ".join(sorted(missing))
            )

        raw = raw.loc[:, ["Theme", "Symbol"]].copy()
        raw["theme"] = raw["Theme"].map(lambda value: str(value).strip())
        raw["ticker"] = raw["Symbol"].map(_clean_ticker)
        if raw["theme"].eq("").any():
            raise ValueError("Deepvue theme snapshot contains a blank theme")

        membership_mask = raw["ticker"].ne("")
        duplicated = raw.loc[membership_mask, ["theme", "ticker"]].duplicated(
            keep=False
        )
        if duplicated.any():
            sample = raw.loc[membership_mask].loc[duplicated, ["theme", "ticker"]]
            pairs = ", ".join(
                f"{row.theme}/{row.ticker}" for row in sample.itertuples(index=False)
            )
            raise ValueError(
                "Deepvue theme snapshot contains duplicate memberships: " + pairs
            )

        ingested_at = datetime.now(tz=UTC).replace(tzinfo=None)
        members = raw.loc[membership_mask, ["theme", "ticker"]].copy()
        members.insert(0, "source_as_of_date", snapshot)
        members.insert(2, "source_provider", SOURCE_PROVIDER)
        members.insert(3, "source_taxonomy", SOURCE_TAXONOMY)
        members["source_row_fingerprint"] = members.apply(
            lambda row: _fingerprint(snapshot, row["theme"], row["ticker"]), axis=1
        )
        members["ingested_at"] = ingested_at
        members = members[MEMBERSHIP_COLUMNS].sort_values(
            ["theme", "ticker"]
        ).reset_index(drop=True)

        themes = sorted(raw["theme"].unique())
        counts = members.groupby("theme").size().to_dict()
        catalog = pd.DataFrame(
            [
                {
                    "source_as_of_date": snapshot,
                    "source_provider": SOURCE_PROVIDER,
                    "source_taxonomy": SOURCE_TAXONOMY,
                    "theme": theme,
                    "constituent_count": int(counts.get(theme, 0)),
                    "membership_status": (
                        "POPULATED" if counts.get(theme, 0) else "EMPTY"
                    ),
                    "source_row_fingerprint": _fingerprint(snapshot, theme, ""),
                    "ingested_at": ingested_at,
                }
                for theme in themes
            ],
            columns=CATALOG_COLUMNS,
        )
        return catalog, members

    def summarize(
        self,
        catalog: pd.DataFrame,
        memberships: pd.DataFrame,
        *,
        source_rows: int,
    ) -> DeepvueThemeSummary:
        return DeepvueThemeSummary(
            source_as_of_date=str(catalog["source_as_of_date"].iloc[0]),
            source_rows=source_rows,
            unique_themes=len(catalog),
            populated_themes=int(catalog["membership_status"].eq("POPULATED").sum()),
            empty_themes=int(catalog["membership_status"].eq("EMPTY").sum()),
            membership_rows=len(memberships),
            unique_tickers=int(memberships["ticker"].nunique()),
        )


class DeepvueThemeStore:
    """Persist normalized snapshots; source captures remain outside Git."""

    def __init__(
        self,
        *,
        duckdb_path: str | Path = DUCKDB_PATH,
        parquet_directory: str | Path = PROCESSED_DIRECTORY / "deepvue_themes",
    ) -> None:
        self.duckdb_path = Path(duckdb_path)
        self.parquet_directory = Path(parquet_directory)

    def persist(
        self,
        catalog: pd.DataFrame,
        memberships: pd.DataFrame,
    ) -> tuple[Path, Path]:
        if catalog.empty:
            raise ValueError("cannot persist an empty Deepvue theme catalog")
        snapshot = date.fromisoformat(str(catalog["source_as_of_date"].iloc[0]))
        catalog_path = self._path(snapshot, "theme_catalog.parquet")
        membership_path = self._path(snapshot, "theme_membership.parquet")
        _atomic_parquet(catalog, catalog_path)
        _atomic_parquet(memberships, membership_path)
        self._write_duckdb(catalog, memberships, snapshot)
        return catalog_path, membership_path

    def _path(self, snapshot: date, filename: str) -> Path:
        partition = f"source_as_of_date={snapshot.isoformat()}"
        return self.parquet_directory / partition / filename

    def _write_duckdb(
        self,
        catalog: pd.DataFrame,
        memberships: pd.DataFrame,
        snapshot: date,
    ) -> None:
        self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self.duckdb_path)) as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                connection.register("incoming_deepvue_theme_catalog", catalog)
                connection.register("incoming_deepvue_theme_memberships", memberships)
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS deepvue_theme_catalog AS "
                    "SELECT * FROM incoming_deepvue_theme_catalog WHERE FALSE"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS deepvue_theme_membership AS "
                    "SELECT * FROM incoming_deepvue_theme_memberships WHERE FALSE"
                )
                connection.execute(
                    "DELETE FROM deepvue_theme_catalog WHERE source_as_of_date = ?",
                    [snapshot],
                )
                connection.execute(
                    "DELETE FROM deepvue_theme_membership WHERE source_as_of_date = ?",
                    [snapshot],
                )
                connection.execute(
                    "INSERT INTO deepvue_theme_catalog "
                    "SELECT * FROM incoming_deepvue_theme_catalog"
                )
                connection.execute(
                    "INSERT INTO deepvue_theme_membership "
                    "SELECT * FROM incoming_deepvue_theme_memberships"
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise


def _fingerprint(snapshot: date, theme: str, ticker: str) -> str:
    return sha256(f"{snapshot.isoformat()}|{theme}|{ticker}".encode()).hexdigest()
