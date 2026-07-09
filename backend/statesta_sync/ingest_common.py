"""Helpers shared by every ingest worker (spine, fixtures, later players/odds/...).

This module is the bottom of the worker import graph: it depends on the transport
and persistence layers (api_football, raw_landing) and on nothing above them. In
particular it must never import spine or fixtures — the workers import *from*
here, never the other way round. That single import direction is what keeps the
--entity dispatch free of cycles.

What lives here is the raw-first discipline itself (D-071): call the API, land the
verbatim payload, normalize from the landed row. Entity-specific mapping stays in
the entity's own module.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from .api_football import ApiFootballClient
from .raw_landing import land_raw, read_raw, utcnow

SPORT = "football"
SOURCE = "api_football"


class SyncError(RuntimeError):
    """The API call failed, or returned something we refuse to normalize."""


# ---------------------------------------------------------------------------
# small mapping helpers — absent stays NULL, never 0 / false (D-051, §6.7)
# ---------------------------------------------------------------------------


def _dig(obj: Any, *path: str) -> Any:
    """Nested .get() that tolerates missing/None levels and returns None."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _api_ok(status: int, body: Any) -> bool:
    return status == 200 and isinstance(body, dict) and not body.get("errors")


class _Fetched(NamedTuple):
    """A validated API response, not yet landed."""

    endpoint: str
    params: dict
    http_status: int
    body: Any
    fetched_at: Any


def _fetch(conn, api: ApiFootballClient, endpoint: str, params: dict) -> _Fetched:
    """Call the API and validate the response.

    On failure the raw row is committed in its own transaction (so the failure
    stays auditable via http_status) and we raise. Failures never reach curated.
    On success nothing is written yet — the caller lands it inside the entity's
    transaction, so the raw row and the curated rows commit together.
    """
    fetched_at = utcnow()
    status, body = api.get(endpoint, params)

    if not _api_ok(status, body):
        with conn.transaction():
            with conn.cursor() as cur:
                land_raw(cur, endpoint, params, status, body, fetched_at)
        errors = body.get("errors") if isinstance(body, dict) else None
        raise SyncError(
            f"{endpoint} {params}: HTTP {status}"
            + (f", errors={errors!r}" if errors else "")
            + " (raw row landed for audit; nothing written to curated)"
        )

    return _Fetched(endpoint, params, status, body, fetched_at)


def _land(cur, fetched: _Fetched) -> tuple[Any, Any]:
    """Land the validated payload, then read it back. Returns (payload, source_fetched_at).

    D-071: everything downstream normalizes from the value returned here — the
    landed row — never from the live HTTP response.
    """
    raw_id = land_raw(
        cur,
        fetched.endpoint,
        fetched.params,
        fetched.http_status,
        fetched.body,
        fetched.fetched_at,
    )
    return read_raw(cur, raw_id)
