"""Bounded reference-error diagnostics; never persist raw responses or requests."""

from datetime import UTC, datetime
import json
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx


MAX_BODY_BYTES = 65_536
MAX_MESSAGE_CHARS = 1_024
MAX_CODE_CHARS = 128
_SENSITIVE = r"(?:api[_-]?key|authorization|proxy-authorization|cookie|set-cookie|password|passwd|secret|access[_-]?token|refresh[_-]?token|token|credential)"


def _sanitize(text: str, response: httpx.Response, limit: int) -> str:
    # Request-derived values catch credential echoes even without a field label.
    values: set[str] = set()
    try:
        request = response.request
        values.update(request.url.params.values())
        values.update(v for v in (request.url.username, request.url.password) if v)
        for name, value in request.headers.items():
            if re.search(_SENSITIVE, name, re.I):
                values.add(value)
                values.update(value.split())
                values.update(re.split(r"[\s=;,:]+", value))
    except RuntimeError:
        pass

    def clean_url(match: re.Match[str]) -> str:
        try:
            url = urlsplit(match.group())
            return urlunsplit((url.scheme, url.hostname or "", url.path, "", ""))
        except ValueError:
            return "[REDACTED_URL]"

    text = re.sub(r"https?://[^\s\"'<>]+", clean_url, text)
    # Remove complete query/fragment tails, including relative URLs.
    text = re.sub(r"[?#][^\s\"'<>]*", "[REDACTED_QUERY]", text)
    text = re.sub(r"(?im)\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:[^\r\n]*", "[REDACTED_HEADER]", text)
    text = re.sub(r"(?i)\b(?:Bearer|Basic)\s+[^\s,;\"'<>]+", "[REDACTED_AUTH]", text)
    text = re.sub(rf"(?i)\b{_SENSITIVE}\b[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;}}]+)", "[REDACTED_SECRET]", text)
    for value in sorted(values, key=len, reverse=True):
        if value and value.lower() not in {"bearer", "basic"}:
            for form in {value, unquote(value), quote(value, safe="")}:
                if form:
                    text = text.replace(form, "[REDACTED]")
    return " ".join(text.split())[:limit]


def capture_reference_error(response: httpx.Response, ticker: str) -> dict | None:
    """Return safe diagnostics for HTTP errors; successful responses are untouched.

    The caller supplies its allowlisted source ticker. No URL, headers, cookies,
    arbitrary JSON fields or raw response body are included in the output.
    """
    if response.is_success:
        return None
    if not re.fullmatch(r"[A-Za-z0-9$.:_-]{1,80}", ticker):
        raise ValueError("Invalid reference ticker for diagnostics")
    code = None
    if len(response.content) > MAX_BODY_BYTES:
        message = "Error response exceeds diagnostic body limit"
    else:
        text = response.content.decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except (ValueError, RecursionError):
            message = (
                "Malformed JSON error response"
                if "json" in response.headers.get("content-type", "").lower()
                or text.lstrip().startswith(("{", "["))
                else text
            )
        else:
            if isinstance(body, dict):
                code = body.get("code", body.get("error_code"))
                message = body.get("message", body.get("error", "No scalar error message supplied"))
                if isinstance(message, dict):
                    code = message.get("code", code)
                    message = message.get("message", "No scalar error message supplied")
            else:
                message = "Unexpected JSON error response shape"
    if not isinstance(message, str):
        message = "No scalar error message supplied"
    return {
        "ticker_requested": ticker,
        "http_status": response.status_code,
        "provider_error_code": _sanitize(str(code), response, MAX_CODE_CHARS)
        if isinstance(code, (str, int)) and not isinstance(code, bool) else None,
        "provider_error_message": _sanitize(message, response, MAX_MESSAGE_CHARS),
        "endpoint_path": "/v3/reference/tickers/" + quote(ticker, safe=""),
        "captured_at": datetime.now(UTC).isoformat(),
    }
