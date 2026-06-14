import os

import httpx


class MassiveClient:
    """Safe initial client wrapper for Massive API configuration."""

    def __init__(self, api_key: str | None = None, timeout: float = 30.0) -> None:
        self.api_key = api_key or os.getenv("MASSIVE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "MASSIVE_API_KEY is required. Set it in your environment or local .env file."
            )

        self.client = httpx.Client(timeout=timeout)
