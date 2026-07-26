from datetime import date
from pathlib import Path
import sys

import duckdb
import httpx
import pandas as pd
import pytest

from market_dashboard.data.massive_reference_client import MassiveReferenceClient
from market_dashboard.data.security_master import (
    SecurityMasterClassifier,
    SecurityMasterStore,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_security_master import validate_security_master


def security_master_config() -> dict:
    return {
        "candidate_filters": {
            "locale": "us",
            "active_only": True,
            "allowed_exchange_mics": ["XNYS", "XNAS", "ARCX", "XASE", "BATS"],
            "allowed_categories": ["Common Stock", "ETF"],
            "excluded_security_types": {
                "ETS": "Single-security ETF excluded from core swing universe"
            },
            "acquisition_vehicle_name_patterns": [
                "acquisition corp",
                "blank check",
            ],
        },
        "exchange_mapping": {
            "XNYS": "NYSE",
            "XNAS": "Nasdaq",
            "ARCX": "NYSE Arca",
            "XASE": "NYSE American",
            "BATS": "Cboe BZX",
        },
        "security_type_mapping": {
            "CS": "Common Stock",
            "ETF": "ETF",
            "ETS": "ETF",
            "ETV": "Exchange Traded Vehicle",
            "PFD": "Preferred Share",
            "WARRANT": "Warrant",
            "RIGHT": "Right",
            "UNIT": "Unit",
        },
    }


def make_record(
    ticker: str,
    *,
    name: str = "Example Inc.",
    exchange: str = "XNYS",
    security_type: str = "CS",
    active: bool = True,
    locale: str = "us",
    market: str = "stocks",
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "locale": locale,
        "primary_exchange": exchange,
        "type": security_type,
        "active": active,
        "currency_symbol": "USD",
        "cik": "0000000001",
        "composite_figi": "BBG000000001",
        "share_class_figi": "BBG001000001",
        "last_updated_utc": "2026-07-25T12:00:00Z",
    }


def test_reference_client_follows_next_url_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        assert "apiKey" not in str(request.url)
        if "cursor" not in request.url.params:
            assert request.url.path == "/v3/reference/tickers"
            assert request.url.params["market"] == "stocks"
            assert request.url.params["locale"] == "us"
            assert request.url.params["active"] == "true"
            assert request.url.params["date"] == "2026-07-25"
            assert request.url.params["limit"] == "1000"
            return httpx.Response(
                200,
                json={
                    "results": [make_record("AAA")],
                    "next_url": "https://api.massive.test/v3/reference/tickers?cursor=next",
                },
            )
        return httpx.Response(200, json={"results": [make_record("BBB")]})

    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    client = MassiveReferenceClient(
        api_key="test-key",
        base_url="https://api.massive.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    rows = client.get_active_us_securities("2026-07-25")

    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert len(requests) == 2


def test_reference_client_rejects_cross_origin_next_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    client = MassiveReferenceClient(
        api_key="test-key",
        base_url="https://api.massive.test",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={
                        "results": [],
                        "next_url": "https://example.test/steal",
                    },
                )
            )
        ),
    )

    with pytest.raises(RuntimeError, match="changed origin"):
        client.get_active_us_securities("2026-07-25")


def test_type_and_exchange_normalization() -> None:
    classifier = SecurityMasterClassifier(security_master_config())

    assert classifier.normalize_type("cs") == "Common Stock"
    assert classifier.normalize_type("ETF") == "ETF"
    assert classifier.normalize_type("ETS") == "ETF"
    assert classifier.normalize_type("ETV") == "Exchange Traded Vehicle"
    assert classifier.normalize_type("PFD") == "Preferred Share"
    assert classifier.normalize_exchange("xnys") == "NYSE"
    assert classifier.normalize_exchange("ARCX") == "NYSE Arca"
    assert classifier.normalize_exchange("BATS") == "Cboe BZX"


def test_unknown_codes_are_review_needed_and_excluded() -> None:
    classifier = SecurityMasterClassifier(security_master_config())

    classification = classifier.classify(
        make_record("MYSTERY", exchange="ZZZZ", security_type="NEW")
    )

    assert classification.normalized_category == "Review Needed"
    assert classification.normalized_exchange == "Review Needed"
    assert classification.candidate_eligible is False
    assert classification.exclusion_reason == "unknown_security_type"


@pytest.mark.parametrize(
    ("record", "expected_reason"),
    [
        (make_record("PREF", security_type="PFD"), "preferred_share"),
        (make_record("WARR", security_type="WARRANT"), "warrant"),
        (make_record("RIGHT", security_type="RIGHT"), "right"),
        (make_record("UNIT", security_type="UNIT"), "unit"),
        (make_record("OTC", exchange="OTCM", market="otc"), "otc"),
        (
            make_record("VEHICLE", security_type="ETV"),
            "exchange_traded_vehicle",
        ),
        (
            make_record("LEVERED", security_type="ETS"),
            "Single-security ETF excluded from core swing universe",
        ),
        (make_record("OLD", active=False), "inactive"),
        (
            make_record("SPAC", name="Example Acquisition Corp."),
            "acquisition_vehicle",
        ),
    ],
)
def test_exclusion_logic(record: dict, expected_reason: str) -> None:
    classification = SecurityMasterClassifier(security_master_config()).classify(record)

    assert classification.candidate_eligible is False
    assert classification.exclusion_reason == expected_reason


def test_common_stock_and_etf_are_included() -> None:
    classifier = SecurityMasterClassifier(security_master_config())

    assert classifier.classify(make_record("IBM")).candidate_eligible is True
    assert classifier.classify(
        make_record("SPY", exchange="ARCX", security_type="ETF")
    ).candidate_eligible is True
    assert classifier.classify(
        make_record("BZXETF", exchange="BATS", security_type="ETF")
    ).candidate_eligible is True


def test_persistence_is_idempotent_and_preserves_previous_snapshots(
    tmp_path: Path,
) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    parquet_directory = tmp_path / "security_master"
    store = SecurityMasterStore(
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
    )
    classifier = SecurityMasterClassifier(security_master_config())

    store.persist(
        [make_record("AAA"), make_record("BBB")],
        "2026-07-24",
        classifier,
    )
    store.persist(
        [make_record("AAA", name="Updated Inc."), make_record("BBB")],
        "2026-07-24",
        classifier,
    )
    store.persist([make_record("AAA")], "2026-07-25", classifier)

    with duckdb.connect(str(duckdb_path), read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT snapshot_date, ticker, name
            FROM security_master
            ORDER BY snapshot_date, ticker
            """
        ).fetchall()
        duplicate_groups = connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT snapshot_date, ticker
                FROM security_master
                GROUP BY snapshot_date, ticker
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]

    assert rows == [
        (date(2026, 7, 24), "AAA", "Updated Inc."),
        (date(2026, 7, 24), "BBB", "Example Inc."),
        (date(2026, 7, 25), "AAA", "Example Inc."),
    ]
    assert duplicate_groups == 0
    frame = pd.read_parquet(
        parquet_directory
        / "snapshot_date=2026-07-24"
        / "security_master.parquet"
    )
    assert len(frame) == 2
    assert frame.loc[frame["ticker"] == "AAA", "name"].item() == "Updated Inc."


def test_validator_reports_counts_unknowns_and_candidates(tmp_path: Path) -> None:
    duckdb_path = tmp_path / "market.duckdb"
    parquet_directory = tmp_path / "security_master"
    store = SecurityMasterStore(
        duckdb_path=duckdb_path,
        parquet_directory=parquet_directory,
    )
    store.persist(
        [
            make_record("IBM"),
            make_record("SPY", exchange="ARCX", security_type="ETF"),
            make_record("PREF", security_type="PFD"),
            make_record("MYSTERY", exchange="ZZZZ", security_type="NEW"),
        ],
        "2026-07-25",
        SecurityMasterClassifier(security_master_config()),
    )

    exit_code, metrics = validate_security_master(
        duckdb_path,
        parquet_directory,
        snapshot_date="2026-07-25",
        sample_size=10,
    )

    assert exit_code == 0
    assert metrics["total_rows"] == 4
    assert metrics["unique_tickers"] == 4
    assert metrics["duplicate_snapshot_ticker_groups"] == 0
    assert metrics["candidate_universe_size"] == 2
    assert metrics["unknown_mapping_count"] == 1
    assert metrics["raw_type_counts"] == {"CS": 1, "ETF": 1, "NEW": 1, "PFD": 1}
    assert metrics["excluded_reason_counts"]["preferred_share"] == 1
    assert metrics["duckdb_parquet_row_count_match"] is True
