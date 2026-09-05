import json
from datetime import datetime

import httpx
import pytest

from market_dashboard.data.reference_errors import (
    MAX_BODY_BYTES,
    MAX_MESSAGE_CHARS,
    capture_reference_error,
)


def response(body: bytes, *, content_type: str = "application/json", status: int = 400,
             request: httpx.Request | None = None) -> httpx.Response:
    transport = httpx.MockTransport(lambda _: httpx.Response(
        status, content=body, headers={"content-type": content_type}
    ))
    with httpx.Client(transport=transport) as client:
        return client.send(request or client.build_request(
            "GET", "https://api.massive.com/v3/reference/tickers/%24SPX"
        ))


def test_http400_json_preserves_only_error_evidence() -> None:
    result = capture_reference_error(response(json.dumps({
        "code": "INVALID_TICKER", "error": "Ticker format is invalid",
        "apiKey": "excluded-extra-field", "cookies": "excluded-cookie",
    }).encode()), "$SPX")
    assert result is not None
    assert result["ticker_requested"] == "$SPX"
    assert result["http_status"] == 400
    assert result["provider_error_code"] == "INVALID_TICKER"
    assert result["provider_error_message"] == "Ticker format is invalid"
    assert result["endpoint_path"] == "/v3/reference/tickers/%24SPX"
    assert datetime.fromisoformat(result["captured_at"]).tzinfo is not None
    assert "excluded" not in json.dumps(result)


def test_plain_text_error_is_supported_and_bounded() -> None:
    result = capture_reference_error(response(
        b"Invalid ticker: " + b"x" * 3000, content_type="text/plain"
    ), "S4B--USA")
    assert result["provider_error_message"].startswith("Invalid ticker: ")
    assert len(result["provider_error_message"]) == MAX_MESSAGE_CHARS
    assert result["provider_error_code"] is None
    assert result["endpoint_path"].endswith("S4B--USA")


@pytest.mark.parametrize("body", [b'{"error":', b'[]', b'null', b'\xff{'])
def test_malformed_response_does_not_raise_or_dump_body(body: bytes) -> None:
    result = capture_reference_error(response(body), "AAA")
    assert result["provider_error_message"] in {
        "Malformed JSON error response", "Unexpected JSON error response shape"
    }


def test_oversized_response_fails_closed_before_truncating_a_secret() -> None:
    result = capture_reference_error(response(
        b"x" * MAX_BODY_BYTES + b"password=secret", content_type="text/plain"
    ), "AAA")
    assert result["provider_error_message"] == "Error response exceeds diagnostic body limit"


@pytest.mark.parametrize("as_json", [True, False])
def test_credentials_headers_and_complete_queries_are_redacted(as_json: bool) -> None:
    request = httpx.Request(
        "GET", "https://api.massive.com/v3/reference/tickers/AAA"
        "?apiKey=querysecret&other=paramsecret",
        headers={"Authorization": "Bearer authsecret", "Cookie": "session=cookiesecret"},
    )
    message = (
        "authsecret querysecret paramsecret cookiesecret\n"
        "https://otheruser:otherpass@api.massive.com/path?unknown=hiddenquery&x=hiddenmore\n"
        "/relative?foo=relativesecret\n"
        "api_key=bodysecret token=tokensecret password=bodypassword\n"
        "Bearer unknownbearer\n"
        "prefix Cookie: a=firstcookie; b=secondcookie\n"
        "Authorization: Basic basicauth\n"
    )
    body = json.dumps({"code": "authsecret", "message": message}).encode() if as_json else message.encode()
    result = capture_reference_error(response(body, request=request,
        content_type="application/json" if as_json else "text/plain"), "AAA")
    serialized = json.dumps(result)
    for secret in ["authsecret", "querysecret", "paramsecret", "cookiesecret", "usersecret",
                   "passsecret", "otheruser", "otherpass", "hiddenquery", "hiddenmore",
                   "relativesecret", "bodysecret", "tokensecret", "bodypassword",
                   "unknownbearer", "firstcookie", "secondcookie", "basicauth"]:
        assert secret not in serialized
    assert "?" not in serialized
    assert result["endpoint_path"] == "/v3/reference/tickers/AAA"


def test_successful_response_is_unchanged() -> None:
    body = b'{"status":"OK","results":{"ticker":"AAA","name":"Example"}}'
    res = response(body, status=200)
    assert capture_reference_error(res, "AAA") is None
    assert res.content == body
    assert res.json()["results"] == {"ticker": "AAA", "name": "Example"}


def test_nested_error_and_code_length_limit() -> None:
    result = capture_reference_error(response(json.dumps({
        "error": {"code": "E" * 1000, "message": "Bad format"}
    }).encode()), "AAA")
    assert len(result["provider_error_code"]) == 128
    assert result["provider_error_message"] == "Bad format"


def test_url_credentials_are_redacted_even_when_echoed_without_labels() -> None:
    request = httpx.Request("GET", "https://urluser:urlpassword@api.massive.com/path")
    result = capture_reference_error(response(
        b"urluser urlpassword", request=request, content_type="text/plain"
    ), "AAA")
    assert "urluser" not in json.dumps(result)
    assert "urlpassword" not in json.dumps(result)


def test_query_value_cannot_disable_secret_label_redaction() -> None:
    request = httpx.Request("GET", "https://api.massive.com/path?search=password")
    result = capture_reference_error(response(
        b"password=unrelatedsecret", request=request, content_type="text/plain"
    ), "AAA")
    assert "unrelatedsecret" not in json.dumps(result)
