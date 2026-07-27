from datetime import date
from pathlib import Path
import sys

import duckdb
import pandas as pd
import pytest
import yaml

from market_dashboard.data.exposure_policy import (
    ExposureClassificationStore,
    ExposurePolicy,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_exposure_classification import (
    validate_exposure_classification,
)


def policy_config(**overrides) -> dict:
    return {
        "policy_version": "exposure-policy-v2",
        "maintained_classifications": {
            "single_security": {
                "reason": "confirmed",
                "provenance": "test",
                "tickers": ["MUU", "SNXX", "TSLL", "NVDL", "PLTD", "CONY", "ARMH", "MSTZ"],
            },
            "diversified": {
                "reason": "confirmed diversified",
                "provenance": "test",
                "tickers": ["BSTP", "MSOX", "DULL", "SHNY"],
            },
            "review_needed": {
                "reason": "ambiguous",
                "provenance": "test",
                "tickers": ["OARK"],
            },
        },
        "overrides": list(overrides.get("overrides", [])),
    }


def frame() -> pd.DataFrame:
    rows = [
        ("MU", "Micron Technology, Inc.", "CS", "Common Stock"),
        ("SNDK", "Sandisk Corporation", "CS", "Common Stock"),
        ("NVDA", "NVIDIA Corporation", "CS", "Common Stock"),
        ("SPY", "SPDR S&P 500 ETF", "ETF", "ETF"),
        ("MUU", "Direxion Daily MU Bull 2X ETF", "ETF", "ETF"),
        ("SNXX", "Tradr 2X Long SNDK Daily ETF", "ETF", "ETF"),
        ("TSLL", "Direxion Daily TSLA Bull 2X ETF", "ETF", "ETF"),
        ("NVDL", "GraniteShares 2x Long NVDA Daily ETF", "ETF", "ETF"),
        ("PLTD", "Direxion Daily PLTR Bear 1X ETF", "ETF", "ETF"),
        ("BSTP", "Innovator Buffer Step-Up Strategy ETF", "ETS", "ETF"),
        ("MSOX", "AdvisorShares MSOS Daily Leveraged ETF", "ETS", "ETF"),
        ("DULL", "MicroSectors Gold -3x Inverse Leveraged ETN", "ETS", "ETF"),
        ("SHNY", "MicroSectors Gold 3x Leveraged ETN", "ETS", "ETF"),
        ("TQQQ", "ProShares UltraPro QQQ", "ETF", "ETF"),
        ("SQQQ", "ProShares UltraPro Short QQQ", "ETF", "ETF"),
        ("SOXL", "Direxion Daily Semiconductor Bull 3X ETF", "ETF", "ETF"),
        ("SOXS", "Direxion Daily Semiconductor Bear 3X ETF", "ETF", "ETF"),
        ("QLD", "ProShares Ultra QQQ", "ETF", "ETF"),
        ("KORU", "Direxion Daily MSCI South Korea Bull 3X ETF", "ETF", "ETF"),
        ("CONY", "YieldMax COIN Option Income Strategy ETF", "ETS", "ETF"),
        ("ARMH", "Arm Holdings PLC ADRhedged", "ETS", "ETF"),
        ("MSTZ", "T-Rex 2X Inverse MSTR Daily Target ETF", "ETF", "ETF"),
        ("OARK", "YieldMax Innovation Option Income Strategy ETF", "ETS", "ETF"),
    ]
    return pd.DataFrame(
        rows, columns=["ticker", "name", "security_type", "normalized_category"]
    )


def classifications(config: dict | None = None) -> pd.DataFrame:
    return ExposurePolicy(config or policy_config()).classify_snapshot(
        frame(), "2026-07-26"
    )


@pytest.mark.parametrize("ticker", ["MUU", "SNXX", "TSLL", "NVDL", "PLTD"])
def test_raw_etf_confirmed_single_security_is_excluded(ticker: str) -> None:
    row = classifications().set_index("ticker").loc[ticker]
    assert row["exposure_scope"] == "single_security"
    assert row["classification_method"] == "maintained_registry"


@pytest.mark.parametrize("ticker", ["BSTP", "MSOX", "DULL", "SHNY"])
def test_raw_ets_diversified_corrections(ticker: str) -> None:
    row = classifications().set_index("ticker").loc[ticker]
    assert row["exposure_scope"] == "diversified"


@pytest.mark.parametrize("ticker", ["TQQQ", "SQQQ", "SOXL", "SOXS", "QLD", "KORU"])
def test_diversified_leveraged_controls_remain_allowed(ticker: str) -> None:
    assert classifications().set_index("ticker").loc[ticker, "exposure_scope"] == "diversified"


@pytest.mark.parametrize("ticker", ["CONY", "ARMH", "MSTZ"])
def test_single_company_strategy_registry_exclusions(ticker: str) -> None:
    assert classifications().set_index("ticker").loc[ticker, "exposure_scope"] == "single_security"


def test_ambiguous_product_requires_review() -> None:
    row = classifications().set_index("ticker").loc["OARK"]
    assert row["exposure_scope"] == "review_needed"
    assert row["policy_reason"] == "ambiguous"


def test_validated_name_rule_extracts_underlying() -> None:
    config = policy_config()
    config["maintained_classifications"]["single_security"]["tickers"] = []
    row = ExposurePolicy(config).classify_snapshot(frame(), "2026-07-26").set_index("ticker").loc["MUU"]
    assert row["exposure_scope"] == "single_security"
    assert row["underlying_ticker"] == "MU"
    assert row["classification_method"] == "name_rule:daily_bull_bear"


def test_suspicious_unvalidated_name_requires_review() -> None:
    source = pd.DataFrame(
        [("MYST", "Example WeeklyPay ETF", "ETF", "ETF")],
        columns=["ticker", "name", "security_type", "normalized_category"],
    )
    row = ExposurePolicy(policy_config()).classify_snapshot(source, "2026-07-26").iloc[0]
    assert row["exposure_scope"] == "review_needed"


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("diversified", "diversified"),
        ("single_security", "single_security"),
        ("review_needed", "review_needed"),
    ],
)
def test_override_precedence(scope: str, expected: str) -> None:
    config = policy_config(
        overrides=[
            {
                "ticker": "MUU",
                "effective_start_date": "2026-01-01",
                "effective_end_date": "2026-12-31",
                "exposure_scope": scope,
                "reason": "manual decision",
                "provenance": "review board",
            }
        ]
    )
    row = classifications(config).set_index("ticker").loc["MUU"]
    assert row["exposure_scope"] == expected
    assert row["classification_method"] == "explicit_override"


def test_override_effective_dates() -> None:
    config = policy_config(
        overrides=[
            {
                "ticker": "SPY",
                "effective_start_date": "2027-01-01",
                "exposure_scope": "review_needed",
                "reason": "future",
                "provenance": "test",
            }
        ]
    )
    assert classifications(config).set_index("ticker").loc["SPY", "exposure_scope"] == "diversified"


def test_invalid_and_overlapping_overrides_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid exposure scope"):
        ExposurePolicy(policy_config(overrides=[{
            "ticker": "SPY", "effective_start_date": "2026-01-01",
            "exposure_scope": "invalid", "reason": "x", "provenance": "x",
        }]))
    with pytest.raises(ValueError, match="overlapping"):
        ExposurePolicy(policy_config(overrides=[
            {"ticker": "SPY", "effective_start_date": "2026-01-01", "effective_end_date": "2026-06-30", "exposure_scope": "diversified", "reason": "x", "provenance": "x"},
            {"ticker": "SPY", "effective_start_date": "2026-06-01", "exposure_scope": "review_needed", "reason": "y", "provenance": "y"},
        ]))


def test_versions_coexist_and_validator_reports_conflicts(tmp_path: Path) -> None:
    database = tmp_path / "market.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            CREATE TABLE security_master AS
            SELECT DATE '2026-07-26' snapshot_date, *
            FROM (VALUES
              ('MU','Micron','CS','Common Stock'),
              ('MUU','Direxion Daily MU Bull 2X ETF','ETF','ETF')
            ) v(ticker,name,security_type,normalized_category)
            """
        )
    store = ExposureClassificationStore(
        duckdb_path=database, parquet_directory=tmp_path / "classifications"
    )
    source = frame().loc[frame()["ticker"].isin(["MU", "MUU"])]
    v2 = ExposurePolicy(policy_config()).classify_snapshot(source, "2026-07-26")
    v1_config = policy_config()
    v1_config["policy_version"] = "legacy-policy-v1"
    v1_config["maintained_classifications"]["single_security"]["tickers"] = []
    store.persist(v2)
    store.persist(ExposurePolicy(v1_config).classify_snapshot(source, "2026-07-26"))
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM security_exposure_classification"
        ).fetchone()[0] == 4
    code, metrics = validate_exposure_classification(
        database,
        parquet_directory=tmp_path / "classifications",
        snapshot_date="2026-07-26",
        policy_version="exposure-policy-v2",
    )
    assert code == 0
    assert metrics["raw_type_conflicts"] == [
        {"ticker": "MUU", "security_type": "ETF", "exposure_scope": "single_security"}
    ]


def test_repository_policy_covers_audited_conflicts_and_residuals() -> None:
    with (PROJECT_ROOT / "config" / "exposure_policy.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        policy = ExposurePolicy(yaml.safe_load(handle))
    confirmed_core = {
        "MUU", "SNXX", "TSLL", "NVDL", "PLTD", "MULL", "AMDL", "SNDU",
        "MSTZ", "MSFU", "TSDD", "MUD", "GGLL", "METU", "TSLQ", "INTW",
        "AMZD", "MVLL", "NVDX", "AMZU", "AAPD", "ASTX", "AAOX", "AVS",
        "RKLX", "PLTU", "TSMX", "NBIL", "BEX", "MSTX", "NEBX", "LITX",
        "ORCX", "AAPU", "PTIR", "WDCX", "SMCX", "IONZ", "GLWG", "IREZ",
    }
    false_positive_corrections = {
        "BSTP", "DULL", "EAPR", "EBUF", "EJAN", "EJUL", "EOCT", "IAPR",
        "IAUG", "IBUF", "IDEC", "IFEB", "IJAN", "IJUL", "IJUN", "IMAR",
        "IMAY", "INOV", "IOCT", "ISEP", "MSOX", "PSTP", "QFLR", "RFLR",
        "RSDE", "RSJN", "RSSE", "SFLR", "SHNY",
    }
    residuals = {"AIYY", "GDXY", "HYNX", "JPO", "OARK", "SPAX", "YSPC"}
    assert all(policy.registry[ticker][0] == "single_security" for ticker in confirmed_core)
    assert all(policy.registry[ticker][0] == "diversified" for ticker in false_positive_corrections)
    assert all(policy.registry[ticker][0] == "review_needed" for ticker in residuals)
