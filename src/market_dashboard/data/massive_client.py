import os
from datetime import UTC, date, datetime
from typing import Any

import httpx
from dotenv import load_dotenv


MASSIVE_BASE_URL = "https://api.massive.com"
PLACEHOLDER_API_KEY = "replace_with_your_api_key"


class MassiveClient:
    """Small Massive API client for safe stock aggregate requests."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        base_url: str = MASSIVE_BASE_URL,
        http_client: httpx.Client | None = None,
    ) -> None:
        load_dotenv()

        resolved_api_key = (api_key or os.getenv("MASSIVE_API_KEY") or "").strip()
        if not resolved_api_key:
            raise ValueError(
                "MASSIVE_API_KEY is required. Set it in your environment or local .env file."
            )
        if resolved_api_key == PLACEHOLDER_API_KEY:
            raise ValueError(
                "MASSIVE_API_KEY still contains the placeholder value. Replace it with a real key."
            )

        self._api_key = resolved_api_key
        self.base_url = base_url.rstrip("/")
        self.client = http_client or httpx.Client(timeout=timeout)

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

        response = self.client.get(
            f"{self.base_url}/v2/aggs/ticker/{normalized_ticker}/range/1/day/{start_date}/{end_date}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            params={
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000,
            },
        )

        if response.status_code in {401, 403}:
            raise ValueError("Massive authentication failed. Check MASSIVE_API_KEY.")

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            reason = exc.response.reason_phrase
            raise RuntimeError(f"Massive API request failed: {status_code} {reason}") from exc

        payload = response.json()
        results = payload.get("results") or []
        return [
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

    @staticmethod
    def _timestamp_to_date(timestamp_ms: int | None) -> str | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date().isoformat()
