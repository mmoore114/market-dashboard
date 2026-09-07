import os
import random
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from dotenv import load_dotenv

from market_dashboard.data.adjusted_authority import response_evidence

MASSIVE_BASE_URL = "https://api.massive.com"
PLACEHOLDER_API_KEYS = {
    "replace_with_your_api_key",
    "replace_with_your_massive_api_key",
}
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}


class MassiveRequestError(RuntimeError):
    """Sanitized adjusted-aggregate request failure with retry diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None,
        attempts: int,
        error_type: str,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.attempts = attempts
        self.error_type = error_type


class MassiveClient:
    """Small Massive API client for safe stock aggregate requests."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        base_url: str = MASSIVE_BASE_URL,
        http_client: httpx.Client | None = None,
        maximum_attempts: int = 4,
        retry_backoff_seconds: float = 2,
        retry_max_backoff_seconds: float = 60,
        retry_jitter_ratio: float = 0.25,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        load_dotenv()

        resolved_api_key = (api_key or os.getenv("MASSIVE_API_KEY") or "").strip()
        if not resolved_api_key:
            raise ValueError(
                "MASSIVE_API_KEY is required. Set it in your environment or local .env file."
            )
        if resolved_api_key in PLACEHOLDER_API_KEYS:
            raise ValueError(
                "MASSIVE_API_KEY still contains the placeholder value. Replace it with a real key."
            )

        self._api_key = resolved_api_key
        self.base_url = base_url.rstrip("/")
        self.client = http_client or httpx.Client(timeout=timeout)
        if maximum_attempts < 1:
            raise ValueError("maximum_attempts must be at least 1")
        self.maximum_attempts = maximum_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_max_backoff_seconds = retry_max_backoff_seconds
        self.retry_jitter_ratio = retry_jitter_ratio
        self._sleep = sleep
        self._jitter = jitter
        self._now = now
        self.last_attempt_count = 0
        self.last_http_status: int | None = None
        self.last_error_type: str | None = None
        self.last_response_evidence = None

    def get_adjusted_daily_bars(
        self,
        ticker: str,
        start_date: str | date,
        end_date: str | date,
    ) -> list[dict[str, Any]]:
        """Return adjusted daily aggregate bars for a ticker and date range."""
        normalized_ticker = ticker.upper().strip()
        if not normalized_ticker:
            raise ValueError("ticker is required.")

        self.last_response_evidence = None
        self.last_attempt_count = 0
        self.last_http_status = None
        self.last_error_type = None
        response: httpx.Response | None = None
        for attempt in range(1, self.maximum_attempts + 1):
            self.last_attempt_count = attempt
            try:
                response = self.client.get(
                    f"{self.base_url}/v2/aggs/ticker/{normalized_ticker}/range/1/day/{start_date}/{end_date}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    params={
                        "adjusted": "true",
                        "sort": "asc",
                        "limit": 50000,
                    },
                )
                self.last_http_status = response.status_code
                if response.status_code in {401, 403}:
                    self.last_error_type = "authentication"
                    raise ValueError(
                        "Massive authentication failed. Check MASSIVE_API_KEY."
                    )
                if response.status_code in RETRYABLE_HTTP_STATUSES:
                    self.last_error_type = "http"
                    if attempt < self.maximum_attempts:
                        self._sleep(self._retry_delay(attempt, response))
                        continue
                    raise MassiveRequestError(
                        f"Massive API request failed after {attempt} attempts: "
                        f"{response.status_code} {response.reason_phrase}",
                        status_code=response.status_code,
                        attempts=attempt,
                        error_type="http",
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    self.last_error_type = "http"
                    raise MassiveRequestError(
                        f"Massive API request failed: "
                        f"{exc.response.status_code} {exc.response.reason_phrase}",
                        status_code=exc.response.status_code,
                        attempts=attempt,
                        error_type="http",
                    ) from exc
                break
            except ValueError:
                raise
            except MassiveRequestError:
                raise
            except httpx.RequestError as exc:
                self.last_error_type = exc.__class__.__name__
                if attempt < self.maximum_attempts:
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                raise MassiveRequestError(
                    f"Massive API connection failed after {attempt} attempts: "
                    f"{exc.__class__.__name__}",
                    status_code=None,
                    attempts=attempt,
                    error_type=exc.__class__.__name__,
                ) from exc

        if response is None:
            raise MassiveRequestError(
                "Massive API request produced no response.",
                status_code=None,
                attempts=self.last_attempt_count,
                error_type=self.last_error_type or "unknown",
            )

        if response.history:
            raise ValueError("AGGREGATE_REDIRECT_REFUSED")
        payload = response.json()
        results = payload.get("results") or []
        mapped = [
            {
                "ticker": normalized_ticker,
                "date": self._timestamp_to_date(result.get("t")),
                "open": result.get("o"),
                "high": result.get("h"),
                "low": result.get("l"),
                "close": result.get("c"),
                "volume": result.get("v"),
                "vwap": result.get("vw"),
                "transactions": result.get("n"),
            }
            for result in results
        ]
        self.last_response_evidence = response_evidence(
            normalized_ticker, start_date, end_date, payload, mapped
        )
        return mapped

    def _retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            parsed_retry_after = self._parse_retry_after(retry_after)
            if parsed_retry_after is not None:
                return parsed_retry_after
        base_delay = min(
            self.retry_max_backoff_seconds,
            self.retry_backoff_seconds * (2 ** (attempt - 1)),
        )
        jitter = base_delay * self.retry_jitter_ratio * self._jitter()
        return min(self.retry_max_backoff_seconds, base_delay + jitter)

    def _parse_retry_after(self, value: str | None) -> float | None:
        if not value:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - self._now()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _timestamp_to_date(timestamp_ms: int | None) -> str | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date().isoformat()
