import httpx
import pytest

from market_dashboard.data import massive_client
from market_dashboard.data.massive_client import MassiveClient


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
    api_key: str = "test_api_key",
) -> MassiveClient:
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "apiKey" not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {api_key}"
        assert request.url.path == "/v2/aggs/ticker/SPY/range/1/day/2024-03-01/2024-03-31"
        assert request.url.params["adjusted"] == "true"
        assert request.url.params["sort"] == "asc"
        assert request.url.params["limit"] == "50000"
        return response

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    return MassiveClient(
        api_key=api_key,
        base_url="https://api.massive.test",
        http_client=http_client,
    )


def test_get_adjusted_daily_bars_success(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        json={
            "results": [
                {
                    "t": 1710115200000,
                    "o": 510.0,
                    "h": 515.0,
                    "l": 508.0,
                    "c": 512.5,
                    "v": 1000000,
                    "vw": 511.7,
                    "n": 12000,
                }
            ]
        },
    )

    client = make_client(monkeypatch, response)

    assert client.get_adjusted_daily_bars("spy", "2024-03-01", "2024-03-31") == [
        {
            "ticker": "SPY",
            "date": "2024-03-11",
            "open": 510.0,
            "high": 515.0,
            "low": 508.0,
            "close": 512.5,
            "volume": 1000000,
            "vwap": 511.7,
            "transactions": 12000,
        }
    ]


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(massive_client, "load_dotenv", lambda: None)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="MASSIVE_API_KEY is required"):
        MassiveClient()


def test_placeholder_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(massive_client, "load_dotenv", lambda: None)
    monkeypatch.setenv("MASSIVE_API_KEY", "replace_with_your_api_key")

    with pytest.raises(ValueError, match="placeholder value"):
        MassiveClient()


def test_authentication_failure_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = make_client(monkeypatch, httpx.Response(401, json={"error": "unauthorized"}))

    with pytest.raises(ValueError, match="authentication failed"):
        client.get_adjusted_daily_bars("SPY", "2024-03-01", "2024-03-31")


def test_empty_results_return_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    client = make_client(monkeypatch, httpx.Response(200, json={"results": []}))

    assert client.get_adjusted_daily_bars("SPY", "2024-03-01", "2024-03-31") == []


def test_normalized_field_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    response = httpx.Response(
        200,
        json={
            "results": [
                {
                    "t": 1710115200000,
                    "o": 510.0,
                    "h": 515.0,
                    "l": 508.0,
                    "c": 512.5,
                    "v": 1000000,
                    "vw": 511.7,
                    "n": 12000,
                }
            ]
        },
    )
    client = make_client(monkeypatch, response)

    row = client.get_adjusted_daily_bars("SPY", "2024-03-01", "2024-03-31")[0]

    assert set(row) == {
        "ticker",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "vwap",
        "transactions",
    }
