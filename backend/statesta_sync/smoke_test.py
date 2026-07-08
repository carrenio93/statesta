"""Connectivity smoke test — the ONLY runnable entrypoint for this step.

It proves the plumbing works end to end, with NO ingestion logic:

  API side:  GET /status  -> print subscription plan + requests used/limit
  DB side:   `select 1`   -> print DB OK
             `select count(*) from curated.tiers` -> print the row count

The API result and the DB result are printed on separate lines, each independently
succeeding or failing, so a failure is easy to localize (is it the API or the DB?).

Run from the backend/ directory:
    python -m statesta_sync.smoke_test
"""

from __future__ import annotations

import sys

from .api_football import ApiFootballClient
from .config import ConfigError, load_config
from .db import connect


def _check_api(api_key: str) -> tuple[bool, str]:
    """Call GET /status and summarize plan + request usage."""
    try:
        with ApiFootballClient(api_key) as api:
            status, body = api.get("/status")
    except Exception as exc:  # network/timeout/etc.
        return False, f"API  FAILED — {type(exc).__name__}: {exc}"

    if status != 200 or not isinstance(body, dict):
        return False, f"API  FAILED — HTTP {status}: {body!r}"

    # API-Football returns errors inside a 200 body under "errors".
    errors = body.get("errors")
    if errors:
        return False, f"API  FAILED — HTTP 200 but errors={errors!r}"

    resp = body.get("response") or {}
    plan = (resp.get("subscription") or {}).get("plan")
    requests = resp.get("requests") or {}
    used = requests.get("current")
    limit = requests.get("limit_day")
    return True, f"API  OK — plan={plan}, requests used {used}/{limit}"


def _check_db(database_url: str) -> tuple[bool, str]:
    """Run `select 1` and `select count(*) from curated.tiers`."""
    try:
        with connect(database_url) as conn, conn.cursor() as cur:
            cur.execute("select 1")
            cur.fetchone()
            cur.execute("select count(*) from curated.tiers")
            tiers_count = cur.fetchone()[0]
    except Exception as exc:
        return False, f"DB   FAILED — {type(exc).__name__}: {exc}"

    return True, f"DB   OK — select 1 succeeded; curated.tiers has {tiers_count} rows"


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        # Fail fast, naming the missing secret(s). Nothing is invented.
        print(f"CONFIG FAILED — {exc}")
        return 2

    api_ok, api_line = _check_api(config.api_football_key)
    db_ok, db_line = _check_db(config.database_url)

    # Separate lines so a failure is easy to localize.
    print(api_line)
    print(db_line)

    return 0 if (api_ok and db_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
