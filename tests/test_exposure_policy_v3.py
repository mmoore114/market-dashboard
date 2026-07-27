from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from market_dashboard.data.exposure_policy import (
    ExposureClassificationStore,
    load_exposure_policy,
    load_exposure_policy_config,
)

from scripts.validate_exposure_classification import (
    validate_exposure_classification,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "2026-07-26"
V2 = "exposure-policy-v2"
V3 = "exposure-policy-v3"
V2_CONFIG_SHA256 = "d5e6c0ba7c19ae7d39ceaf9939d079d9233ab5852401ef118f6be753a9a2f346"

SINGLE_SECURITY = {
    "AAPW", "AAPX", "AHD", "AIYY", "AMA", "AMDW", "AMKL", "AMPU", "AMZW",
    "ANEL", "ANV", "ARMW", "ASTN", "ASTY", "ATC", "AVGW", "AVGX", "AVXX",
    "BABW", "BRKW", "COIW", "CORD", "COSW", "CRCD", "DKNX", "GOOW", "GOOX",
    "HIMZ", "HOOW", "HOOX", "HYNX", "INFH", "IONX", "JPO", "KEEX", "LMNX",
    "LNOK", "LUNL", "METW", "MRA", "MSFW", "MSFX", "MSR", "MSTW", "NFLW",
    "NVDQ", "NVDW", "OKLL", "ONDL", "OSCX", "OSSL", "OUSL", "PLA", "PLTW",
    "PLTZ", "PLU", "POEL", "PUR", "QBTZ", "RCAX", "RGTX", "RGTZ", "RKLZ",
    "RKTL", "SCA", "SMCZ", "SMST", "SOFX", "SOUX", "SPAX", "SPCQ", "SPCU",
    "STXL", "TLA", "TOPW", "TSLT", "TSLW", "TSLZ", "UBEW", "UMAL", "UNHW",
    "VELL", "VSTL", "WYFL", "YSPC",
}
DIVERSIFIED = {
    "ACEI", "ACII", "ACYN", "ACYQ", "ACYS", "ATCL", "BIGY", "CAGE", "CAIE",
    "CAIQ", "CHPY", "COPZ", "DRAL", "GDXW", "GDXY", "GPTY", "LFGY", "MINY",
    "OARK", "PAYH", "PAYM", "QVOL", "RAM", "RNTY", "SLTY", "SOXY", "TDAQ",
    "TMGN", "TSPY", "ULTY", "VAIE", "WEEL", "XOVL", "YBST", "YMAG", "YMAX",
    "YQQQ",
}
NON_EQUITY = {
    "BITY", "BTCL", "BTCZ", "BUCK", "CPXR", "ETTY", "ETU", "GLDW", "IETH",
    "SOLM", "TLTP", "TSYW", "XRPM", "YBIT",
}
RESOLVED = SINGLE_SECURITY | DIVERSIFIED | NON_EQUITY


def policies():
    return (
        load_exposure_policy(PROJECT_ROOT / "config" / "exposure_policy.yaml"),
        load_exposure_policy(PROJECT_ROOT / "config" / "exposure_policy_v3.yaml"),
    )


def resolved_fixture() -> pd.DataFrame:
    config = load_exposure_policy_config(
        PROJECT_ROOT / "config" / "exposure_policy_v3.yaml"
    )
    underlyings = {
        row["underlying_ticker"]
        for row in config["overrides"]
        if row.get("underlying_ticker")
    }
    controls = {"TQQQ", "SQQQ", "SOXL", "SOXS", "QLD", "UPRO"}
    rows = [
        (ticker, f"{ticker} reviewed product", "ETF", "ETF")
        for ticker in sorted(RESOLVED | controls)
    ]
    rows.extend(
        (ticker, f"{ticker} underlying", "CS", "Common Stock")
        for ticker in sorted(underlyings - RESOLVED - controls)
    )
    return pd.DataFrame(
        rows,
        columns=["ticker", "name", "security_type", "normalized_category"],
    )


def test_v2_configuration_is_immutable_and_reproducible() -> None:
    path = PROJECT_ROOT / "config" / "exposure_policy.yaml"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == V2_CONFIG_SHA256
    v2, _ = policies()
    assert v2.policy_version == V2
    assert all(
        v2.registry[ticker][0] == "review_needed"
        for ticker in {"AIYY", "GDXY", "HYNX", "JPO", "OARK", "SPAX", "YSPC"}
    )


def test_default_configuration_advances_to_v3_and_explicit_v2_remains() -> None:
    with (PROJECT_ROOT / "config" / "settings.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        settings = yaml.safe_load(handle)
    assert (
        settings["swing_universe"]["exposure_policy_config"]
        == "config/exposure_policy_v3.yaml"
    )
    v2, v3 = policies()
    assert (v2.policy_version, v3.policy_version) == (V2, V3)
    with (PROJECT_ROOT / "config" / "exposure_policy_v3.yaml").open(
        "r", encoding="utf-8"
    ) as handle:
        v3_source = yaml.safe_load(handle)
    resolutions = v3_source["review_resolutions"]
    assert str(resolutions["review_date"]) == SNAPSHOT
    assert resolutions["classification_source"] == (
        "manual policy review with issuer/prospectus confirmation"
    )


def test_all_review_resolutions_have_exact_final_scopes_and_counts() -> None:
    _, v3 = policies()
    classified = v3.classify_snapshot(resolved_fixture(), SNAPSHOT).set_index(
        "ticker"
    )
    resolved = classified.loc[sorted(RESOLVED)]
    assert set(resolved.loc[resolved["exposure_scope"] == "single_security"].index) == (
        SINGLE_SECURITY
    )
    assert set(resolved.loc[resolved["exposure_scope"] == "diversified"].index) == (
        DIVERSIFIED
    )
    assert set(resolved.loc[resolved["exposure_scope"] == "non_equity"].index) == (
        NON_EQUITY
    )
    assert resolved["exposure_scope"].value_counts().to_dict() == {
        "single_security": 85,
        "diversified": 37,
        "non_equity": 14,
    }
    assert not resolved["exposure_scope"].eq("review_needed").any()
    assert resolved["classification_method"].eq("explicit_override").all()
    assert resolved["classification_provenance"].eq(
        "manual_issuer_prospectus_review_2026-07-26"
    ).all()


def test_required_underlying_and_reference_controls() -> None:
    _, v3 = policies()
    classified = v3.classify_snapshot(resolved_fixture(), SNAPSHOT).set_index(
        "ticker"
    )
    expected_underlyings = {
        "BRKW": "BRK.B",
        "JPO": "JPM",
        "AIYY": "AI",
        "HYNX": "SKHY",
        "SPAX": "SPCX",
        "YSPC": "SPCX",
    }
    assert classified.loc[
        list(expected_underlyings), "underlying_ticker"
    ].to_dict() == expected_underlyings
    for ticker in ("OARK", "RAM", "DRAL", "XOVL", "CHPY"):
        assert classified.loc[ticker, "exposure_scope"] == "diversified"
    for ticker in ("BTCZ", "BUCK"):
        assert classified.loc[ticker, "exposure_scope"] == "non_equity"
    for ticker in ("TQQQ", "SQQQ", "SOXL", "SOXS", "QLD", "UPRO"):
        assert classified.loc[ticker, "exposure_scope"] == "diversified"


def test_v2_and_v3_publish_validate_and_recover_in_separate_partitions(
    tmp_path: Path,
) -> None:
    database = tmp_path / "market.duckdb"
    parquet = tmp_path / "classification"
    source = resolved_fixture()
    with duckdb.connect(str(database)) as connection:
        connection.register("source", source)
        connection.execute(
            """
            CREATE TABLE security_master AS
            SELECT DATE '2026-07-26' AS snapshot_date, * FROM source
            """
        )
    v2, v3 = policies()
    store = ExposureClassificationStore(
        duckdb_path=database,
        parquet_directory=parquet,
    )
    v2_path = store.persist(v2.classify_snapshot(source, SNAPSHOT))
    v3_frame = v3.classify_snapshot(source, SNAPSHOT)

    def fail_after_commit(point: str) -> None:
        if point == "after_commit_before_publish":
            raise RuntimeError("injected v3 interruption")

    interrupted = ExposureClassificationStore(
        duckdb_path=database,
        parquet_directory=parquet,
        failure_injector=fail_after_commit,
    )
    try:
        interrupted.persist(v3_frame)
    except RuntimeError:
        pass
    assert store.publication_record(SNAPSHOT, V2)["publication_state"] == "complete"
    assert store.publication_record(SNAPSHOT, V3)["publication_state"] == (
        "recovery_required"
    )
    store.recover(SNAPSHOT, V3)
    v3_path = store.parquet_path(date.fromisoformat(SNAPSHOT), V3)
    assert v2_path != v3_path
    assert v2_path.exists() and v3_path.exists()

    for version in (V2, V3):
        code, metrics = validate_exposure_classification(
            database,
            parquet_directory=parquet,
            snapshot_date=SNAPSHOT,
            policy_version=version,
        )
        assert code == 0
        assert metrics["publication_state"] == "complete"
        assert metrics["duckdb_parquet_agreement"] is True
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute(
            """
            SELECT policy_version, COUNT(*)
            FROM security_exposure_classification
            GROUP BY policy_version ORDER BY policy_version
            """
        ).fetchall() == [(V2, len(source)), (V3, len(source))]
