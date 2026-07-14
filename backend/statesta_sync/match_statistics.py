"""Match-statistics ingest — /fixtures/statistics -> curated.match_statistics.

One row per (fixture, team). This is the first worker that loops over fixtures,
so it costs one API call per fixture (380 for an EPL season) rather than one call
per entity. Everything else follows the established discipline: raw-first, land
before normalizing (D-071), normalize FROM the landed row, upsert with
ON CONFLICT ... RETURNING id (D-073).

Three things are new here versus fixtures.py:

  * No pagination. /fixtures/statistics returns every team block in one call
    (paging.total == 1 always), so D-082's page loop does not apply.
  * Per-fixture fault isolation. Each fixture gets its own transaction and its
    own try/except: one bad fixture is logged and skipped, never aborting the
    other 379. The failed source_refs are reported at the end so a re-run picks
    up exactly those.
  * Resumability. Fixtures that already have match_statistics rows are skipped
    (saves API calls, makes a re-run cheap). This is only sound because a
    fixture's team rows are written in ONE transaction — see below.

Absent, not invented (D-081): if the statistics array is empty, or fewer than two
team blocks arrive, or a team cannot be resolved, we write NOTHING for that
fixture — 0 rows, never 1 — and log it. Both team rows are validated before
either is upserted, so a fixture is always all-or-nothing. That invariant is what
lets the skip-set trust "has any row" to mean "is complete".

Identity is the (fixture_id, team_id) pair (D-057), so source_ref stays NULL and
the ON CONFLICT target names those two columns. Note `sport` is NOT part of the
key here, unlike the spine's (sport, source, source_ref) tables.

Run (via the shared worker entrypoint):
    python -m statesta_sync.spine --entity match_statistics --league 39 --season 2025 --limit 1
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .ingest_common import SOURCE, SPORT, SyncError, _dig, _fetch, _land
from .upsert import ResolutionMap, upsert_returning_id

ENDPOINT = "/fixtures/statistics"


# ---------------------------------------------------------------------------
# value parsing — absent stays NULL, a parse failure RAISES (never a silent NULL)
#
# The distinction matters: `value: null` is the vendor saying "no data", which is
# NULL (§6.7, D-051 — never 0). A string we cannot parse is OUR bug, or a vendor
# format change, and must surface loudly rather than masquerade as absent data.
# ---------------------------------------------------------------------------


def _reject_bool(value: Any) -> None:
    """bool is a subclass of int in Python; True would silently store as 1."""
    if isinstance(value, bool):
        raise SyncError(f"unexpected boolean value {value!r}")


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    _reject_bool(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise SyncError(f"cannot parse {value!r} as integer") from exc
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as integer")


def _parse_percent(value: Any) -> Decimal | None:
    """'61%' -> Decimal('61'). Stored in numeric(5,2), so a future '61.5%' works."""
    if value is None:
        return None
    _reject_bool(value)
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise SyncError(f"cannot parse {value!r} as percent") from exc
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as percent")


def _parse_decimal(value: Any) -> Decimal | None:
    """'2.21' -> Decimal('2.21'); '-0.95' -> Decimal('-0.95').

    goals_prevented is legitimately negative. Decimal() accepts the leading '-'
    and numeric(6,3) is signed, so negatives are stored verbatim, never rejected.
    """
    if value is None:
        return None
    _reject_bool(value)
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise SyncError(f"cannot parse {value!r} as decimal") from exc
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as decimal")


# Vendor `type` strings, VERBATIM — including their inconsistent casing
# ("Total passes", "Shots insidebox", "expected_goals"). We deliberately do not
# normalize case: a vendor rename must surface as an unmapped type (-> logged,
# -> source_extra) rather than silently binding to the wrong column.
_TYPE_TO_COLUMN: dict[str, tuple[str, Callable[[Any], Any]]] = {
    "Shots on Goal": ("shots_on_goal", _parse_int),
    "Shots off Goal": ("shots_off_goal", _parse_int),
    "Total Shots": ("shots_total", _parse_int),
    "Blocked Shots": ("shots_blocked", _parse_int),
    "Shots insidebox": ("shots_inside_box", _parse_int),
    "Shots outsidebox": ("shots_outside_box", _parse_int),
    "Fouls": ("fouls", _parse_int),
    "Corner Kicks": ("corners", _parse_int),
    "Offsides": ("offsides", _parse_int),
    "Ball Possession": ("possession_pct", _parse_percent),
    "Yellow Cards": ("yellow_cards", _parse_int),
    "Red Cards": ("red_cards", _parse_int),
    "Goalkeeper Saves": ("gk_saves", _parse_int),
    "Total passes": ("passes_total", _parse_int),
    "Passes accurate": ("passes_accurate", _parse_int),
    "Passes %": ("passes_pct", _parse_percent),
    "expected_goals": ("expected_goals", _parse_decimal),
    "goals_prevented": ("goals_prevented", _parse_decimal),
}

_MEASURE_COLUMNS = [column for column, _ in _TYPE_TO_COLUMN.values()]

# The natural key (fixture_id, team_id) and the provenance identity columns are
# deliberately excluded — a re-run refreshes measures, never rewrites identity.
_UPDATE_COLUMNS = ["source_fetched_at", *_MEASURE_COLUMNS, "source_extra"]


# ---------------------------------------------------------------------------
# cross-run FK resolution — one SELECT each, up front (D-073 fallback)
# ---------------------------------------------------------------------------


def _preload_fixture_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football fixture.

    Fixture lookups do NOT go through ResolutionMap: it has no 'fixtures' branch
    and would raise. Preloading mirrors fixtures.py's _preload_team_ids.
    """
    cur.execute(
        "select source_ref, id from curated.fixtures where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: fid for ref, fid in cur.fetchall()}


def _preload_team_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football team, read once."""
    cur.execute(
        "select source_ref, id from curated.teams where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: tid for ref, tid in cur.fetchall()}


def _preload_done_fixture_ids(cur) -> set[int]:
    """Our fixture ids that already have stats rows (resume + save API calls).

    Sound only because each fixture's team rows commit in ONE transaction, so a
    fixture is never half-written: any row present => that fixture is complete.
    """
    cur.execute("select distinct fixture_id from curated.match_statistics")
    return {row[0] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# rate-limit visibility — log only, no backoff / auto-pause
# ---------------------------------------------------------------------------


def _remaining_budget(api) -> str | None:
    """x-ratelimit-requests-remaining off the most recent response, if exposed."""
    headers = getattr(api, "last_headers", None)
    if not headers:
        return None
    return headers.get("x-ratelimit-requests-remaining")


def _log_account_status(api) -> None:
    """ONE /status call before the loop, so --sleep is set against the real ceiling.

    Purely diagnostic: a failure here warns and continues. A broken /status must
    never stop us from ingesting.
    """
    try:
        status, body = api.get("/status")
    except Exception as exc:  # noqa: BLE001 — diagnostic must never abort the run
        print(f"WARNING  /status call failed ({exc!r}) — proceeding without limits")
        return

    if status != 200 or not isinstance(body, dict):
        print(f"WARNING  /status returned HTTP {status} — proceeding without limits")
        return

    response = body.get("response") or {}
    subscription = response.get("subscription") or {}
    requests = response.get("requests") or {}
    headers = getattr(api, "last_headers", None) or {}

    print("--- account status (GET /status) ---")
    print(f"  plan={subscription.get('plan')!r}  active={subscription.get('active')}")
    print(f"  requests today: {requests.get('current')} / {requests.get('limit_day')}")
    print(f"  header x-ratelimit-requests-remaining: {headers.get('x-ratelimit-requests-remaining')}")
    print(f"  header x-ratelimit-remaining (per-minute): {headers.get('x-ratelimit-remaining')}")
    print(f"  header x-ratelimit-limit  (per-minute): {headers.get('x-ratelimit-limit')}")
    print("------------------------------------")


# ---------------------------------------------------------------------------
# normalization — every value read FROM the landed payload (D-071)
# ---------------------------------------------------------------------------


def _build_row(
    block: dict,
    our_fixture_id: int,
    our_team_id: int,
    fetched_at: Any,
    unmapped_seen: set[str],
) -> dict:
    """Turn one team block into a curated.match_statistics values dict.

    Raises SyncError on any unparseable value (ruling C) — the caller's
    per-fixture except turns that into a logged failure, not a NULL.
    """
    values: dict[str, Any] = {column: None for column in _MEASURE_COLUMNS}
    extra: dict[str, Any] = {}

    for stat in block.get("statistics") or []:
        stat_type = stat.get("type")
        raw_value = stat.get("value")

        mapping = _TYPE_TO_COLUMN.get(stat_type)
        if mapping is None:
            # Unmodelled stat: keep it verbatim rather than lose it (§6.1).
            extra[str(stat_type)] = raw_value
            unmapped_seen.add(str(stat_type))
            continue

        column, parse = mapping
        try:
            values[column] = parse(raw_value)
        except SyncError as exc:
            raise SyncError(f"type={stat_type!r}: {exc}") from exc

    return {
        "source": SOURCE,
        "source_ref": None,  # identity is (fixture_id, team_id) — D-057
        "source_fetched_at": fetched_at,
        "sport": SPORT,
        "fixture_id": our_fixture_id,
        "team_id": our_team_id,
        **values,
        "source_extra": Jsonb(extra) if extra else None,
    }


def ingest_match_statistics(
    conn,
    api,
    resolver: ResolutionMap,
    league: int,
    season: int,
    *,
    limit: int | None = None,
    sleep: float = 0.5,
) -> dict:
    """Ingest per-team statistics for every completed fixture of one league-season.

    Signature matches the other --entity workers; --limit / --sleep arrive as
    keyword-only options from the CLI.
    """
    _log_account_status(api)
    calls_made = 1  # the /status call above

    # --- parents, coverage pre-check, and the work list, all read once ---------
    with conn.transaction():
        with conn.cursor() as cur:
            our_league_id = resolver.resolve(cur, "leagues", league)
            if our_league_id is None:
                raise SyncError(
                    f"league source_ref={league} not in curated.leagues "
                    "— run --entity leagues first"
                )

            cur.execute(
                "select id, cov_fixture_statistics from curated.league_seasons "
                "where league_id = %s and season = %s",
                (our_league_id, season),
            )
            row = cur.fetchone()
            if row is None:
                raise SyncError(
                    f"league_season (league_id={our_league_id}, season={season}) missing "
                    "— run --entity leagues first"
                )
            league_season_id, cov_fixture_statistics = row

            # Coverage pre-check: warn, never hard-block (the flag is the vendor's
            # claim about the season, not a guarantee about any single fixture).
            if not cov_fixture_statistics:
                print(
                    f"WARNING  cov_fixture_statistics={cov_fixture_statistics!r} for "
                    f"league_season_id={league_season_id} — the source claims fixture "
                    "statistics are not covered for this season. Proceeding anyway."
                )

            team_ids = _preload_team_ids(cur)
            fixture_ids = _preload_fixture_ids(cur)
            done_fixture_ids = _preload_done_fixture_ids(cur)

            cur.execute(
                "select id, source_ref from curated.fixtures "
                "where league_season_id = %s and sport = %s and source = %s "
                "order by match_date asc, id asc",
                (league_season_id, SPORT, SOURCE),
            )
            all_fixtures = cur.fetchall()

    print(
        f"{len(all_fixtures)} fixture(s) in league_season_id={league_season_id}; "
        f"{len(done_fixture_ids)} already have stats; "
        f"{len(team_ids)} teams / {len(fixture_ids)} fixtures preloaded"
    )

    written = 0
    collisions = 0
    skipped_existing = 0
    no_stats: list[str] = []
    dup_fixtures: list[str] = []
    failed: list[tuple[str, str]] = []
    unmapped_seen: set[str] = set()
    processed = 0
    remaining = None

    for our_fixture_id, source_ref in all_fixtures:
        if our_fixture_id in done_fixture_ids:
            skipped_existing += 1
            continue

        # --limit counts fixtures actually PROCESSED, so --limit 1 always makes
        # exactly one fixture call however many are already done.
        if limit is not None and processed >= limit:
            break

        if processed and sleep:
            time.sleep(sleep)

        processed += 1
        params = {"fixture": int(source_ref)}

        try:
            fetched = _fetch(conn, api, ENDPOINT, params)
            calls_made += 1
            remaining = _remaining_budget(api)

            # One transaction per fixture. The raw row and both curated rows commit
            # together (D-071); the except below sits OUTSIDE, so a failure rolls
            # this fixture back cleanly and the connection stays usable.
            with conn.transaction():
                with conn.cursor() as cur:
                    payload, fetched_at = _land(cur, fetched)

                    blocks = payload.get("response") or []

                    # Absent, not invented (D-081): decide FIRST, write SECOND.
                    # Anything short of two resolvable team blocks -> write nothing.
                    reason = None
                    if not blocks:
                        reason = "empty response[]"
                    elif len(blocks) < 2:
                        reason = f"only {len(blocks)} team block(s)"

                    # Keyed on team_id — the discriminator of the (fixture_id, team_id)
                    # conflict key inside one fixture. Two blocks for the same team would
                    # upsert the same row twice, the second silently overwriting the first:
                    # a list would report 2 rows where 1 landed. That is the standings
                    # collapse (D-100/D-101). This is a 2-row entity, so a same-team
                    # duplicate means a team is probably MISSING — write nothing rather
                    # than a half-populated fixture (see the dup_reason branch below).
                    rows: dict[int, dict] = {}
                    dup_reason = None
                    if reason is None:
                        for block in blocks:
                            team_ref = _dig(block, "team", "id")
                            if team_ref is None:
                                reason = "team block missing team.id"
                                break
                            our_team_id = team_ids.get(str(team_ref))
                            if our_team_id is None:
                                reason = f"team source_ref={team_ref} not in curated.teams"
                                break
                            if our_team_id in rows:
                                dup_reason = f"duplicate team block for team_ref={team_ref}"
                                break
                            rows[our_team_id] = _build_row(
                                block, our_fixture_id, our_team_id,
                                fetched_at, unmapped_seen,
                            )

                    if reason is not None:
                        # Raw row still lands (append-only audit) — the transaction
                        # commits with zero curated rows, so the gap is provable.
                        no_stats.append(str(source_ref))
                        print(f"  NO STATS fixture={source_ref} ({reason}) -> 0 rows")
                        continue

                    if dup_reason is not None:
                        # Distinct from no_stats: the payload HAD stats, but its team
                        # identity is unusable. Writing the one good block would land a
                        # half-fixture that the skip-set ("has any row") would then call
                        # complete, silently losing the other team forever. Write 0 rows:
                        # the fixture stays out of the skip-set and is retried next run.
                        collisions += 1
                        dup_fixtures.append(str(source_ref))
                        print(
                            f"  WARNING  match_statistics collapse: fixture={source_ref} — "
                            f"{dup_reason}; refusing to write a half-populated fixture "
                            "(0 rows written), will retry next run"
                        )
                        continue

                    for values in rows.values():
                        upsert_returning_id(
                            cur,
                            "curated.match_statistics",
                            values=values,
                            conflict_columns=["fixture_id", "team_id"],
                            update_columns=_UPDATE_COLUMNS,
                        )
                    fixture_rows = len(rows)
                    written += fixture_rows

            print(
                f"  [{processed}] fixture={source_ref} -> {fixture_rows} row(s)  "
                f"remaining={remaining}"
            )

        except Exception as exc:  # noqa: BLE001 — one bad fixture must not abort the run
            failed.append((str(source_ref), str(exc)))
            print(f"  FAILED fixture={source_ref}: {exc}")
            continue

    # --- report ---------------------------------------------------------------
    if unmapped_seen:
        print(f"\nNOTE  {len(unmapped_seen)} unmapped stat type(s) -> source_extra:")
        for stat_type in sorted(unmapped_seen):
            print(f"        {stat_type!r}")
    else:
        print("\nNOTE  every stat type mapped to a column; source_extra NULL throughout")

    if no_stats:
        print(f"\nNOTE  {len(no_stats)} fixture(s) had no usable stats (0 rows written):")
        print(f"        {', '.join(no_stats)}")

    if failed:
        print(f"\nFAILED  {len(failed)} fixture(s) — re-run to retry exactly these:")
        for source_ref, message in failed:
            print(f"        fixture={source_ref}: {message}")

    print(f"\nAPI calls made: {calls_made}  (last remaining budget: {remaining})")

    return {
        "written": written,
        "collisions": collisions,
        "dup_fixtures": dup_fixtures,
        "skipped_existing": skipped_existing,
        "no_stats": len(no_stats),
        "failed": [source_ref for source_ref, _ in failed],
        "calls_made": calls_made,
        "remaining_budget": remaining,
    }
