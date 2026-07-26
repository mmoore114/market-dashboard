from __future__ import annotations

from datetime import date
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from market_dashboard.data.massive_client import MASSIVE_BASE_URL


PLACEHOLDER_API_KEYS = {
    "replace_with_your_api_key",
    "replace_with_your_massive_api_key",
}


class MassiveReferenceClient:
    """Paginated client for Massive stock ticker-reference records."""

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
        if resolved_api_key in PLACEHOLDER_API_KEYS:
            raise ValueError("MASSIVE_API_KEY still contains a placeholder value.")
        self._api_key = resolved_api_key
        self.base_url = base_url.rstrip("/")
        self.client = http_client or httpx.Client(timeout=timeout)

    def get_active_us_securities(
        self,
        snapshot_date: str | date,
        *,
        market: str = "stocks",
        locale: str = "us",
        active: bool = True,
        page_limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if page_limit < 1 or page_limit > 1000:
            raise ValueError("page_limit must be between 1 and 1000")

        url = f"{self.base_url}/v3/reference/tickers"
        params: dict[str, Any] | None = {
            "market": market,
            "locale": locale,
            "active": str(active).lower(),
            "date": str(snapshot_date),
            "limit": page_limit,
            "sort": "ticker",
            "order": "asc",
        }
        records: list[dict[str, Any]] = []
        visited_urls: set[str] = set()

        while url:
            self._validate_page_url(url)
            if url in visited_urls:
                raise RuntimeError("Massive ticker-reference pagination loop detected")
            visited_urls.add(url)
            response = self.client.get(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                params=params,
            )
            params = None
            if response.status_code in {401, 403}:
                raise ValueError("Massive authentication failed. Check MASSIVE_API_KEY.")
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    "Massive ticker-reference request failed: "
                    f"{exc.response.status_code} {exc.response.reason_phrase}"
                ) from exc

            payload = response.json()
            page_results = payload.get("results") or []
            if not isinstance(page_results, list):
                raise RuntimeError("Massive ticker-reference results must be a list")
            records.extend(page_results)
            url = payload.get("next_url") or ""

        return records

    def _validate_page_url(self, url: str) -> None:
        expected = urlparse(self.base_url)
        candidate = urlparse(url)
        if candidate.scheme != expected.scheme or candidate.netloc != expected.netloc:
            raise RuntimeError("Massive ticker-reference next_url changed origin")
