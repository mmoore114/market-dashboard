import json
from datetime import UTC, datetime

import httpx
import pytest

from market_dashboard.data.expansion.acquire import (
    Acquirer,
    AcquisitionError,
    grouped_rows,
)


def payload():
    return {
        "adjusted": True,
        "results": [
            {
                "T": "ABC",
                "t": datetime(2026, 9, 4, tzinfo=UTC).timestamp() * 1000,
                "o": 10,
                "h": 12,
                "l": 9,
                "c": 11,
                "v": 1000,
            }
        ],
    }


def setup(tmp_path, handler):
    (tmp_path / "plan.json").write_text(
        json.dumps(
            {
                "schema_version": "universe-expansion-plan-v1",
                "source_hashes": {},
                "candidates": [{"source_symbol": "ABC"}],
                "required_benchmarks": [],
                "local_history": {},
                "reference_candidates": ["ABC"],
                "history_sessions": ["2026-09-04"],
                "acquisition_bounds": {
                    "attempts_per_job": 3,
                    "requests_per_second": 10000,
                    "workers": 1,
                    "response_bytes_max": 10000,
                    "storage_reserve_bytes": 0,
                },
            }
        )
    )
    return Acquirer(
        tmp_path,
        "test-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_resume_does_not_fetch_or_reset_receipt(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    a = setup(tmp_path, handler)
    first = a.job("grouped", "2026-09-04")
    receipt = (tmp_path / "acquisition/grouped/2026-09-04/receipt.json").read_bytes()
    assert a.job("grouped", "2026-09-04") == first
    assert len(calls) == 1
    assert (
        tmp_path / "acquisition/grouped/2026-09-04/receipt.json"
    ).read_bytes() == receipt
    assert b"test-secret" not in receipt


def test_unauthorized_stops_batch(tmp_path):
    a = setup(tmp_path, lambda request: httpx.Response(403, text="private error"))
    with pytest.raises(AcquisitionError, match="PROVIDER_AUTHORIZATION_REQUIRED"):
        a.job("grouped", "2026-09-04")
    assert a.stop.is_set()
    assert (
        "private error"
        not in (tmp_path / "acquisition/grouped/2026-09-04/receipt.json").read_text()
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda p: p.update(adjusted=False), "SPLIT_ADJUSTED"),
        (lambda p: p["results"].append(p["results"][0]), "DUPLICATE"),
        (lambda p: p["results"][0].update(v=-1), "OHLCV"),
        (lambda p: p["results"][0].update(t=0), "NON_SESSION"),
    ],
)
def test_invalid_provider_data(change, reason):
    p = payload()
    change(p)
    with pytest.raises(AcquisitionError, match=reason):
        grouped_rows(p, "2026-09-04", {"ABC"})


def test_unplanned_request_refused_before_http(tmp_path):
    a = setup(tmp_path, lambda request: pytest.fail("HTTP forbidden"))
    with pytest.raises(AcquisitionError, match="UNPLANNED"):
        a.job("reference", "XYZ")


def test_delayed_daily_bars_are_not_cached_as_complete(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={"adjusted": True, "results": []} if len(calls) == 1 else payload(),
        )

    a = setup(tmp_path, handler)
    # Only the explicit daily contract requires all published identities; initial
    # candidate acquisition keeps genuine absence in the coverage report.
    a.plan["authorization"] = "PUBLISHED_COVERAGE_DAILY_INCREMENT"
    with pytest.raises(AcquisitionError, match="COMPLETED_BAR_MISSING"):
        a.job("grouped", "2026-09-04")
    receipt = tmp_path / "acquisition/grouped/2026-09-04/receipt.json"
    assert not json.loads(receipt.read_text()).get("complete")
    assert a.job("grouped", "2026-09-04")["rows"][0]["ticker"] == "ABC"
    assert len(calls) == 2
    assert len(json.loads(receipt.read_text())["attempts"]) == 2
