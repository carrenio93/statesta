"""Raw landing zone helpers (D-071).

One row per API call into `raw.api_responses`: the verbatim payload plus
provenance and a sha256 fingerprint of the body.

The important discipline here is `read_raw()`: normalization must read FROM the
landed payload, never from the live HTTP response. That keeps the "fresh call"
path and the "replay an old raw row" path as one single code path, so they can
never drift (SYNC_INGESTION_DESIGN.md Part 1).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from psycopg.types.json import Jsonb

SOURCE = "api_football"


def utcnow() -> datetime:
    """Timezone-aware UTC now (schema stores every moment as timestamptz)."""
    return datetime.now(timezone.utc)


def response_hash(response_body: Any) -> str:
    """sha256 of the response body.

    Hashed over a canonical JSON rendering (sorted keys, no incidental
    whitespace) so the same payload always yields the same fingerprint,
    regardless of key ordering. Enables later dedupe/diffing.
    """
    canonical = json.dumps(
        response_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def land_raw(
    cur,
    endpoint: str,
    params: dict[str, Any],
    http_status: int | None,
    response_body: Any,
    source_fetched_at: datetime | None = None,
    source: str = SOURCE,
) -> int:
    """Insert one verbatim API response into raw.api_responses. Returns its id."""
    if source_fetched_at is None:
        source_fetched_at = utcnow()

    cur.execute(
        """
        insert into raw.api_responses
            (source, endpoint, request_params, http_status,
             response_body, response_hash, source_fetched_at)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            source,
            endpoint,
            Jsonb(params),
            http_status,
            Jsonb(response_body),
            response_hash(response_body),
            source_fetched_at,
        ),
    )
    return cur.fetchone()[0]


def read_raw(cur, raw_id: int) -> tuple[Any, datetime]:
    """Read a landed payload back out. Returns (response_body, source_fetched_at).

    D-071: normalization consumes THIS, not the live HTTP response.
    """
    cur.execute(
        "select response_body, source_fetched_at from raw.api_responses where id = %s",
        (raw_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise LookupError(f"raw.api_responses id={raw_id} not found")
    return row[0], row[1]
