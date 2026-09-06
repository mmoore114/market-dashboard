from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from market_dashboard.data.deepvue_themes import (
    DeepvueThemeNormalizer,
    DeepvueThemeStore,
)


def write_snapshot(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_normalizes_many_to_many_membership_and_preserves_empty_theme(
    tmp_path: Path,
) -> None:
    source = tmp_path / "themes.csv"
    write_snapshot(
        source,
        [
            {"Theme": "AI", "Symbol": " nvda "},
            {"Theme": "AI", "Symbol": "msft"},
            {"Theme": "Robotics", "Symbol": "NVDA"},
            {"Theme": "Bitcoin", "Symbol": ""},
        ],
    )

    catalog, memberships = DeepvueThemeNormalizer().read_csv(source, "2026-09-05")

    assert memberships[["theme", "ticker"]].values.tolist() == [
        ["AI", "msft"],
        ["AI", "nvda"],
        ["Robotics", "NVDA"],
    ]
    assert catalog.set_index("theme").loc["Bitcoin", "membership_status"] == "EMPTY"
    assert catalog.set_index("theme").loc["AI", "constituent_count"] == 2
    assert memberships["source_row_fingerprint"].str.len().eq(64).all()


def test_rejects_missing_columns_blank_themes_and_duplicate_membership(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.csv"
    pd.DataFrame([{"Theme": "AI"}]).to_csv(missing, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        DeepvueThemeNormalizer().read_csv(missing, "2026-09-05")

    invalid = tmp_path / "invalid.csv"
    write_snapshot(
        invalid,
        [
            {"Theme": "", "Symbol": "AAA"},
            {"Theme": "AI", "Symbol": "NVDA"},
            {"Theme": "AI", "Symbol": "NVDA"},
        ],
    )
    with pytest.raises(ValueError, match="blank theme"):
        DeepvueThemeNormalizer().read_csv(invalid, "2026-09-05")

    duplicate = tmp_path / "duplicate.csv"
    write_snapshot(
        duplicate,
        [
            {"Theme": "AI", "Symbol": "NVDA"},
            {"Theme": "AI", "Symbol": "NVDA"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate memberships"):
        DeepvueThemeNormalizer().read_csv(duplicate, "2026-09-05")


def test_store_is_idempotent_and_keeps_empty_catalog_entries(tmp_path: Path) -> None:
    source = tmp_path / "themes.csv"
    write_snapshot(
        source,
        [
            {"Theme": "AI", "Symbol": "NVDA"},
            {"Theme": "Bitcoin", "Symbol": ""},
        ],
    )
    normalizer = DeepvueThemeNormalizer()
    catalog, memberships = normalizer.read_csv(source, "2026-09-05")
    store = DeepvueThemeStore(
        duckdb_path=tmp_path / "market.duckdb",
        parquet_directory=tmp_path / "deepvue_themes",
    )
    store.persist(catalog, memberships)
    store.persist(catalog, memberships)

    with duckdb.connect(str(tmp_path / "market.duckdb"), read_only=True) as connection:
        themes = connection.execute(
            "SELECT theme, constituent_count FROM deepvue_theme_catalog ORDER BY theme"
        ).fetchall()
        members = connection.execute(
            "SELECT source_as_of_date, theme, ticker FROM deepvue_theme_membership"
        ).fetchall()

    assert themes == [("AI", 1), ("Bitcoin", 0)]
    assert members == [(date(2026, 9, 5), "AI", "NVDA")]
