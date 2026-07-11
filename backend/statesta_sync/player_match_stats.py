"""Per-player match-stats ingest — /fixtures/players -> curated.players +
curated.player_match_stats.

The second per-fixture worker, closely modelled on match_statistics.py: same
raw-first discipline (D-071), same ON CONFLICT ... RETURNING id upsert (D-073),
same --limit/--sleep loop, skip-set resume, /status + last_headers logging, and
the same per-fixture transaction that gives an all-or-nothing (N-rows-or-0)
guarantee.

Two things make this worker different from match_statistics:

  * It writes TWO tables per player. /fixtures/players carries a *thin* player
    identity (id / name / photo only — no birth, nationality, height, weight), so
    each player is upserted into curated.players as a THIN SEED (decision 2A): we
    set name + photo_url and nothing else, and on a re-sync we refresh only those
    — never the bio columns, which a later /players enrichment owns (D-064). Its
    RETURNING id is then the player_id FK for the stats row.
  * team_id is NOT NULL with ON DELETE RESTRICT (the per-match team, D-064). If a
    team block's team.id does not resolve to curated.teams we RAISE, failing the
    whole fixture (it rolls back) — we never skip the block or default the team.

Payload shape (verified against fixture 1378969): response is a list of 2 team
entries, each with `team` (id/name/logo/update) and ~20 `players`. Each player has
a `player` object (id/name/photo) and `statistics` — a list of length 1. Every
stat block (games, offsides, shots, goals, passes, tackles, duels, dribbles,
fouls, cards, penalty) is ALWAYS present as an object; leaves are `null` when
absent, never missing — so leaf paths are read directly, each nullable.

Not paginated (paging.total == 1 for a single fixture), so no page loop.

Run (via the shared worker entrypoint):
    python -m statesta_sync.spine --entity player_match_stats --league 39 --season 2025 --limit 1
"""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from psycopg.types.json import Jsonb

from .ingest_common import SOURCE, SPORT, SyncError, _dig, _fetch, _land
from .upsert import ResolutionMap, upsert_returning_id

ENDPOINT = "/fixtures/players"


# ---------------------------------------------------------------------------
# value parsing — absent stays NULL, a parse failure RAISES (never a silent NULL)
#
# Same discipline as match_statistics (D-085/D-086): `null` is the vendor saying
# "no data" -> NULL, never 0; `0` is a real zero -> stored verbatim; a value we
# cannot parse is a bug or a vendor format change and must surface loudly.
# ---------------------------------------------------------------------------


def _reject_bool(value: Any) -> None:
    """bool is a subclass of int in Python; True would silently store as 1."""
    if isinstance(value, bool):
        raise SyncError(f"unexpected boolean value {value!r}")


def _parse_int(value: Any) -> int | None:
    """int passthrough; numeric strings like '33' (passes.accuracy) -> int.

    Stored AS-IS: passes.accuracy is a count-shaped number the vendor ships as a
    string — we do NOT convert it to/from a percentage (schema ref §5.5).
    """
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


def _parse_decimal(value: Any) -> Decimal | None:
    """'6.3' -> Decimal('6.3'). rating is numeric(4,2); the vendor ships a string."""
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


def _parse_bool(value: Any) -> bool | None:
    """games.captain / games.substitute arrive as real JSON booleans.

    This is the one place a bool is WANTED (unlike the measure parsers, which
    reject it). null -> NULL; anything not a bool -> raise.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as boolean")


def _parse_text(value: Any) -> str | None:
    """games.position etc. — text passthrough; null -> NULL, non-string -> raise."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as text")


# ---------------------------------------------------------------------------
# field map: statistics[0].<path> -> column, keyed on the API's ACTUAL keys.
#
# Paths are read with _dig (tolerates missing/None levels). `offsides` is a scalar
# leaf directly on statistics[0]; everything else is nested one level deep.
#
# NOTE the vendor typo: the penalty block ships "commited" (one 'm'). We key on the
# misspelled string and write to the correctly-spelled column penalty_committed —
# keying on the column name would read null forever and silently lose the stat.
# ---------------------------------------------------------------------------
_FIELD_MAP: list[tuple[tuple[str, ...], str, Callable[[Any], Any]]] = [
    (("games", "minutes"), "minutes_played", _parse_int),
    (("games", "number"), "jersey_number", _parse_int),
    (("games", "position"), "position_played", _parse_text),
    (("games", "rating"), "rating", _parse_decimal),
    (("games", "captain"), "is_captain", _parse_bool),
    (("games", "substitute"), "is_substitute", _parse_bool),
    (("offsides",), "offsides", _parse_int),
    (("shots", "total"), "shots_total", _parse_int),
    (("shots", "on"), "shots_on", _parse_int),
    (("goals", "total"), "goals_total", _parse_int),
    (("goals", "conceded"), "goals_conceded", _parse_int),
    (("goals", "assists"), "assists", _parse_int),
    (("goals", "saves"), "goals_saves", _parse_int),
    (("passes", "total"), "passes_total", _parse_int),
    (("passes", "key"), "passes_key", _parse_int),
    (("passes", "accuracy"), "passes_accuracy", _parse_int),
    (("tackles", "total"), "tackles_total", _parse_int),
    (("tackles", "blocks"), "tackles_blocks", _parse_int),
    (("tackles", "interceptions"), "tackles_interceptions", _parse_int),
    (("duels", "total"), "duels_total", _parse_int),
    (("duels", "won"), "duels_won", _parse_int),
    (("dribbles", "attempts"), "dribbles_attempts", _parse_int),
    (("dribbles", "success"), "dribbles_success", _parse_int),
    (("dribbles", "past"), "dribbles_past", _parse_int),
    (("fouls", "drawn"), "fouls_drawn", _parse_int),
    (("fouls", "committed"), "fouls_committed", _parse_int),
    (("cards", "yellow"), "cards_yellow", _parse_int),
    (("cards", "red"), "cards_red", _parse_int),
    (("penalty", "won"), "penalty_won", _parse_int),
    (("penalty", "commited"), "penalty_committed", _parse_int),  # API typo: one 'm'
    (("penalty", "scored"), "penalty_scored", _parse_int),
    (("penalty", "missed"), "penalty_missed", _parse_int),
    (("penalty", "saved"), "penalty_saved", _parse_int),
]

_KNOWN_PATHS = {path for path, _, _ in _FIELD_MAP}
_MEASURE_COLUMNS = [column for _, column, _ in _FIELD_MAP]

# team_id is source-owned (the per-match team, D-064) and mutable across re-syncs,
# so it IS refreshed — only the natural key (fixture_id, player_id) and provenance
# identity columns are excluded from the update.
_UPDATE_COLUMNS = ["source_fetched_at", "team_id", *_MEASURE_COLUMNS, "source_extra"]

# curated.players is a THIN SEED here: refresh only what this endpoint carries.
# The bio columns (firstname/birth_*/nationality/height/weight) are deliberately
# NOT set and NOT updated, so a later /players enrichment is never clobbered.
_PLAYER_UPDATE_COLUMNS = ["source_fetched_at", "name", "photo_url"]


# ---------------------------------------------------------------------------
# cross-run FK resolution — one SELECT each, up front (D-073 fallback)
# ---------------------------------------------------------------------------


def _preload_team_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football team, read once."""
    cur.execute(
        "select source_ref, id from curated.teams where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: tid for ref, tid in cur.fetchall()}


def _preload_fixture_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football fixture, read once."""
    cur.execute(
        "select source_ref, id from curated.fixtures where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: fid for ref, fid in cur.fetchall()}


def _preload_done_fixture_ids(cur) -> set[int]:
    """Our fixture ids that already have player_match_stats rows (resume + save calls).

    Sound only because every row for a fixture commits in ONE transaction, so a
    fixture is never half-written: any row present => that fixture is complete.
    """
    cur.execute("select distinct fixture_id from curated.player_match_stats")
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


def _build_stats_values(
    stat: dict,
    our_fixture_id: int,
    our_player_id: int,
    our_team_id: int,
    fetched_at: Any,
    unmapped_seen: set[str],
) -> dict:
    """Turn one player's statistics[0] into a curated.player_match_stats values dict.

    Raises SyncError on any unparseable leaf (D-085) — the caller's per-fixture
    except turns that into a logged, rolled-back failure, not a silent NULL.
    """
    values: dict[str, Any] = {}
    for path, column, parse in _FIELD_MAP:
        raw = _dig(stat, *path)
        try:
            values[column] = parse(raw)
        except SyncError as exc:
            raise SyncError(f"path={'.'.join(path)}: {exc}") from exc

    # Q-NEW-AO: any leaf the vendor ships that we don't model is kept verbatim in
    # source_extra and logged, so a new block/leaf on another league is never lost.
    extra: dict[str, Any] = {}
    for key, node in (stat or {}).items():
        if isinstance(node, dict):
            for leaf, leaf_value in node.items():
                if (key, leaf) not in _KNOWN_PATHS:
                    extra[f"{key}.{leaf}"] = leaf_value
                    unmapped_seen.add(f"{key}.{leaf}")
        elif (key,) not in _KNOWN_PATHS:
            extra[key] = node
            unmapped_seen.add(key)

    return {
        "source": SOURCE,
        "source_ref": None,  # identity is (fixture_id, player_id) — D-057
        "source_fetched_at": fetched_at,
        "sport": SPORT,
        "fixture_id": our_fixture_id,
        "player_id": our_player_id,
        "team_id": our_team_id,
        **values,
        "source_extra": Jsonb(extra) if extra else None,
    }


def _upsert_player_seed(cur, player: dict, fetched_at: Any) -> int:
    """Thin-seed a player and return our surrogate id.

    Only name + photo_url are set/refreshed; the bio columns stay untouched so a
    later /players enrichment is never overwritten (decision 2A, D-064).
    """
    return upsert_returning_id(
        cur,
        "curated.players",
        values={
            "source": SOURCE,
            "source_ref": str(player["id"]),
            "source_fetched_at": fetched_at,
            "sport": SPORT,
            "name": player.get("name"),
            "photo_url": player.get("photo"),
        },
        conflict_columns=["sport", "source", "source_ref"],
        update_columns=_PLAYER_UPDATE_COLUMNS,
    )


def ingest_player_match_stats(
    conn,
    api,
    resolver: ResolutionMap,
    league: int,
    season: int,
    *,
    limit: int | None = None,
    sleep: float = 0.5,
) -> dict:
    """Ingest per-player statistics for every completed fixture of one league-season.

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
                "select id, cov_player_statistics from curated.league_seasons "
                "where league_id = %s and season = %s",
                (our_league_id, season),
            )
            row = cur.fetchone()
            if row is None:
                raise SyncError(
                    f"league_season (league_id={our_league_id}, season={season}) missing "
                    "— run --entity leagues first"
                )
            league_season_id, cov_player_statistics = row

            # Coverage pre-check: warn, never hard-block (the flag is the vendor's
            # claim about the season, not a guarantee about any single fixture).
            if not cov_player_statistics:
                print(
                    f"WARNING  cov_player_statistics={cov_player_statistics!r} for "
                    f"league_season_id={league_season_id} — the source claims player "
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
        f"{len(done_fixture_ids)} already have player stats; "
        f"{len(team_ids)} teams / {len(fixture_ids)} fixtures preloaded"
    )

    written = 0            # player_match_stats rows written
    players_upserted = 0   # curated.players thin-seed upserts (incl. re-seeds)
    skipped_existing = 0
    no_stats: list[str] = []
    failed: list[tuple[str, str]] = []
    unmapped_seen: set[str] = set()
    processed = 0
    remaining = None

    for our_fixture_id, source_ref in all_fixtures:
        if our_fixture_id in done_fixture_ids:
            skipped_existing += 1
            continue

        # --limit counts fixtures actually PROCESSED, so --limit 1 always makes
        # exactly one fixture call however many are already done (D-088).
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

            # One transaction per fixture: the raw row and every curated row (both
            # tables) commit together (D-071). The except below sits OUTSIDE, so any
            # failure rolls the whole fixture back cleanly — N-rows-or-0, never a
            # partial fixture — and the connection stays usable.
            with conn.transaction():
                with conn.cursor() as cur:
                    payload, fetched_at = _land(cur, fetched)

                    blocks = payload.get("response") or []

                    # Absent, not invented (D-081): a fixture with no usable team
                    # blocks writes nothing (0 rows) and is logged — the raw row
                    # still lands, so the gap is provable from raw.api_responses.
                    reason = None
                    if not blocks:
                        reason = "empty response[]"
                    elif len(blocks) < 2:
                        reason = f"only {len(blocks)} team block(s)"

                    if reason is not None:
                        no_stats.append(str(source_ref))
                        print(f"  NO STATS fixture={source_ref} ({reason}) -> 0 rows")
                        continue

                    fixture_rows = 0
                    for block in blocks:
                        # team_id is NOT NULL / ON DELETE RESTRICT: an unresolved
                        # team RAISES and rolls the whole fixture back — we never
                        # skip the block or default the team (explicit ruling 3b).
                        team_ref = _dig(block, "team", "id")
                        if team_ref is None:
                            raise SyncError(
                                f"team block missing team.id (fixture={source_ref})"
                            )
                        our_team_id = team_ids.get(str(team_ref))
                        if our_team_id is None:
                            raise SyncError(
                                f"team source_ref={team_ref} not in curated.teams "
                                "— run --entity teams first"
                            )

                        for entry in block.get("players") or []:
                            player = entry.get("player") or {}
                            if player.get("id") is None:
                                raise SyncError(
                                    f"player entry missing player.id "
                                    f"(fixture={source_ref}, team={team_ref})"
                                )

                            our_player_id = _upsert_player_seed(cur, player, fetched_at)
                            players_upserted += 1

                            stats_list = entry.get("statistics") or []
                            stat = stats_list[0] if stats_list else {}
                            values = _build_stats_values(
                                stat, our_fixture_id, our_player_id,
                                our_team_id, fetched_at, unmapped_seen,
                            )
                            upsert_returning_id(
                                cur,
                                "curated.player_match_stats",
                                values=values,
                                conflict_columns=["fixture_id", "player_id"],
                                update_columns=_UPDATE_COLUMNS,
                            )
                            fixture_rows += 1

                    written += fixture_rows

            print(
                f"  [{processed}] fixture={source_ref} -> {fixture_rows} player row(s)  "
                f"remaining={remaining}"
            )

        except Exception as exc:  # noqa: BLE001 — one bad fixture must not abort the run
            failed.append((str(source_ref), str(exc)))
            print(f"  FAILED fixture={source_ref}: {exc}")
            continue

    # --- report ---------------------------------------------------------------
    if unmapped_seen:
        print(f"\nNOTE  {len(unmapped_seen)} unmapped stat leaf(s) -> source_extra:")
        for leaf in sorted(unmapped_seen):
            print(f"        {leaf!r}")
    else:
        print("\nNOTE  every stat leaf mapped to a column; source_extra NULL throughout")

    if no_stats:
        print(f"\nNOTE  {len(no_stats)} fixture(s) had no usable player stats (0 rows written):")
        print(f"        {', '.join(no_stats)}")

    if failed:
        print(f"\nFAILED  {len(failed)} fixture(s) — re-run to retry exactly these:")
        for source_ref, message in failed:
            print(f"        fixture={source_ref}: {message}")

    print(
        f"\nAPI calls made: {calls_made}  (last remaining budget: {remaining})"
        f"  players upserted: {players_upserted}"
    )

    return {
        "written": written,
        "players_upserted": players_upserted,
        "skipped_existing": skipped_existing,
        "no_stats": len(no_stats),
        "failed": [source_ref for source_ref, _ in failed],
        "calls_made": calls_made,
        "remaining_budget": remaining,
    }
