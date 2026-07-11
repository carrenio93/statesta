"""Minimal API-Football (api-sports.io) HTTP client.

Plumbing only: a thin wrapper that attaches auth and returns the raw
(http_status, parsed_json) pair. No endpoint-specific logic, no normalization,
no ret/pagination — those belong to the ingestion code in a later step.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

# The direct API-Football host (api-sports.io). Note: this is the api-sports.io
# host, not the RapidAPI proxy — so auth is the `x-apisports-key` header.
BASE_HOST = "https://v3.football.api-sports.io"


class ApiFootballClient:
    """Tiny client around httpx that authenticates every request.

    Usage:
        with ApiFootballClient(api_key) as api:
            status, body = api.get("/status")
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=BASE_HOST,
            headers={"x-apisports-key": api_key},
            timeout=timeout,
        )
        # Response headers of the most recent call. Carries the rate-limit budget
        # (x-ratelimit-requests-remaining), which callers log. None until first get().
        self.last_headers: Optional[httpx.Headers] = None

    def get(
        self, endpoint: str, params: Optional[dict[str, Any]] = None
    ) -> tuple[int, Any]:
        """GET an endpoint and return (http_status, parsed_json).

        `endpoint` is a path like "/status" or "/leagues".
        Returns the parsed JSON body, or None if the body was not valid JSON.
        Side effect: `self.last_headers` is updated with this response's headers.
        """
        response = self._client.get(endpoint, params=params or {})
        self.last_headers = response.headers
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiFootballClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
