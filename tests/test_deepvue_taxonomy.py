from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from market_dashboard.data.deepvue_taxonomy import (
    DeepvueTaxonomyNormalizer,
    DeepvueTaxonomyStore,
)


def write_export(path: Path, rows: list[dict[str, str]]) -> None:
    pd.DataFrame(rows).to_csv(path, index=False)


def test_normalizes_placeholders_and_does_not_infer_parent_taxonomy(tmp_path: Path) -> None:
    source = tmp_path / "deepvue.csv"
    write_export(
        source,
        [
            {
                "Symbol": "abc",
                "Industry Rank - 3 Month": "7",
                "Sub-Industry": "Application Software",
            },
            {
                "Symbol": "spy",
                "Industry Rank - 3 Month": "NaN",
                "Sub-Industry": "-",
            },
        ],
    )

    frame = DeepvueTaxonomyNormalizer().read_csv(source, "2026-09-05")

    assert frame["ticker"].tolist() == ["ABC", "SPY"]
    assert frame["classification_status"].tolist() == ["CLASSIFIED", "UNCLASSIFIED"]
    assert frame.loc[frame["ticker"] == "SPY", "sub_industry"].isna().item()
    assert "sector" not in frame.columns
    assert "industry" not in frame.columns
    assert frame["source_row_fingerprint"].str.len().eq(64).all()


def test_group_rank_is_only_published_when_constituents_agree(tmp_path: Path) -> None:
    source = tmp_path / "deepvue.csv"
    write_export(
        source,
        [
            {"Symbol": "AAA", "Industry Rank - 3 Month": "4", "Sub-Industry": "One"},
            {"Symbol": "BBB", "Industry Rank - 3 Month": "4", "Sub-Industry": "One"},
            {"Symbol": "CCC", "Industry Rank - 3 Month": "8", "Sub-Industry": "Two"},
            {"Symbol": "DDD", "Industry Rank - 3 Month": "9", "Sub-Industry": "Two"},
        ],
    )
    normalizer = DeepvueTaxonomyNormalizer()
    symbols = normalizer.read_csv(source, "2026-09-05")

    groups = normalizer.build_group_snapshot(symbols).set_index("sub_industry")

    assert groups.loc["One", "rank_status"] == "CONSISTENT"
    assert groups.loc["One", "industry_rank_3m"] == 4
    assert groups.loc["Two", "rank_status"] == "AMBIGUOUS"
    assert pd.isna(groups.loc["Two", "industry_rank_3m"])


def test_rejects_duplicate_symbols_and_missing_columns(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.csv"
    write_export(
        duplicate,
        [
            {"Symbol": "AAA", "Industry Rank - 3 Month": "1", "Sub-Industry": "One"},
            {"Symbol": "aaa", "Industry Rank - 3 Month": "1", "Sub-Industry": "One"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate symbols"):
        DeepvueTaxonomyNormalizer().read_csv(duplicate, "2026-09-05")

    missing = tmp_path / "missing.csv"
    pd.DataFrame([{"Symbol": "AAA"}]).to_csv(missing, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        DeepvueTaxonomyNormalizer().read_csv(missing, "2026-09-05")


def test_store_is_idempotent_and_keeps_dated_snapshots(tmp_path: Path) -> None:
    normalizer = DeepvueTaxonomyNormalizer()
    store = DeepvueTaxonomyStore(
        duckdb_path=tmp_path / "market.duckdb",
        parquet_directory=tmp_path / "deepvue",
    )
    source = tmp_path / "deepvue.csv"
    write_export(
        source,
        [{"Symbol": "AAA", "Industry Rank - 3 Month": "3", "Sub-Industry": "One"}],
    )
    symbols = normalizer.read_csv(source, "2026-09-05")
    groups = normalizer.build_group_snapshot(symbols)
    store.persist(symbols, groups)
    store.persist(symbols, groups)

    write_export(
        source,
        [{"Symbol": "BBB", "Industry Rank - 3 Month": "2", "Sub-Industry": "Two"}],
    )
    symbols2 = normalizer.read_csv(source, "2026-09-06")
    store.persist(symbols2, normalizer.build_group_snapshot(symbols2))

    with duckdb.connect(str(tmp_path / "market.duckdb"), read_only=True) as connection:
        rows = connection.execute(
            "SELECT source_as_of_date, ticker FROM deepvue_symbol_classification "
            "ORDER BY source_as_of_date, ticker"
        ).fetchall()
    assert rows == [(date(2026, 9, 5), "AAA"), (date(2026, 9, 6), "BBB")]
    assert (tmp_path / "deepvue/source_as_of_date=2026-09-05/symbol_classification.parquet").exists()
