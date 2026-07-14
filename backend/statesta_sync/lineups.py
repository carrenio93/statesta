"""Lineups ingest — /fixtures/lineups -> curated.lineups.

The third per-fixture worker, modelled on player_match_stats.py: same raw-first
discipline (D-071), same ON CONFLICT ... RETURNING id upsert (D-073), same
--limit/--sleep loop, skip-set resume, /status + last_headers logging (D-087),
and the same per-fixture transaction giving an all-or-nothing (N-rows-or-0)
guarantee.

Payload shape (probed against fixture 1378969): `response` is a list of exactly 2
team blocks. Each block carries `team` (id/name/logo/colors), `coach`
(id/name/photo), `formation` (e.g. '4-2-3-1'), `startXI` (11 entries) and
`substitutes` (9 entries). Every entry is `{"player": {id, name, number, pos,
grid}}`. `grid` ("row:column") is populated for starters and null for EVERY
substitute — so grid is NOT a starter flag. `is_starting` is NOT NULL in curated
and its ONLY source is which array the entry came from.

Three things make this worker different from player_match_stats:

  * curated.lineups is one row PER PLAYER but its natural key is the THREE-column
    (fixture_id, team_id, player_id) — uq_lineups — not the two-column key
    player_match_stats uses. The team-level facts (formation, coach) are
    denormalized onto every player row of the block.
  * Player seeding is READ-MOSTLY. /fixtures/lineups carries no photo and no bio,
    so we resolve an existing player by SELECT and only INSERT ... DO NOTHING when
    genuinely absent. We never UPDATE an existing player row: reusing the
    player_match_stats thin seed here would write photo_url=NULL over the photo
    that /fixtures/players already stored (D-090 applies to /fixtures/players,
    which HAS a photo; this endpoint does not).
  * The two arrays are deduped in memory before the upsert. If the vendor ever
    lists the same player in both startXI and substitutes, Postgres would abort
    the fixture with "ON CONFLICT DO UPDATE cannot affect row a second time";
    startXI wins and we log the anomaly.

Not paginated (one fixture per call), so no page loop.

Run (via the shared worker entrypoint):
    python -m statesta_sync.spine --entity lineups --league 39 --season 2025 --limit 1
"""

from __future__ import annotations

import time
from typing import Any

from psycopg.types.json import Jsonb

from .ingest_common import SOURCE, SPORT, SyncError, _dig, _fetch, _land
from .upsert import ResolutionMap, upsert_returning_id

ENDPOINT = "/fixtures/lineups"


# ---------------------------------------------------------------------------
# value parsing — absent stays NULL, a parse failure RAISES (never a silent NULL)
# Same discipline as the sibling workers (D-085/D-086).
# ---------------------------------------------------------------------------


def _parse_int(value: Any) -> int | None:
    """player.number -> integer. null -> NULL. bool is rejected (bool is an int)."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise SyncError(f"unexpected boolean value {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as exc:
            raise SyncError(f"cannot parse {value!r} as integer") from exc
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as integer")


def _parse_text(value: Any) -> str | None:
    """Text passthrough. null -> NULL; a non-string is a vendor change -> raise."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as text")


def _parse_grid(value: Any) -> str | None:
    """grid is 'row:column' for starters and null for every substitute.

    Stored verbatim as text. An empty/whitespace string is the vendor saying
    "nothing", which is NULL — never the string '' (absent != empty, §6.7).
    """
    text = _parse_text(value)
    if text is None:
        return None
    text = text.strip()
    return text or None


# ---------------------------------------------------------------------------
# leaf census (Q-NEW-AO) — what we map, and what we deliberately drop.
#
# KNOWN = mapped to a column. IGNORED = seen, understood, intentionally not in
# curated (cosmetic or already held elsewhere). Anything else is UNMAPPED: it is
# logged loudly AND kept verbatim in source_extra, so a new field on a future
# league can never be silently lost.
# ---------------------------------------------------------------------------

_KNOWN_TEAM_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("team", "id"),
        ("formation",),
        ("coach", "id"),
        ("coach", "name"),
    }
)

# Deliberately dropped, raw-only:
#   team.name / team.logo  — already on curated.teams; team_id is the FK to it.
#   team.colors.*          — kit colours are a property of the TEAM, not of a
#                            lineup row; smearing 6 hex strings across ~40 rows
#                            per fixture would be pure duplication. If we ever
#                            want them they belong on curated.teams.
#   coach.photo            — cosmetic; we keep coach_name + coach_source_ref only
#                            (there is no curated.coaches table today).
_IGNORED_TEAM_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("team", "name"),
        ("team", "logo"),
        ("team", "colors", "player", "primary"),
        ("team", "colors", "player", "number"),
        ("team", "colors", "player", "border"),
        ("team", "colors", "goalkeeper", "primary"),
        ("team", "colors", "goalkeeper", "number"),
        ("team", "colors", "goalkeeper", "border"),
        ("coach", "photo"),
    }
)

# The two player arrays are walked separately (they ARE the is_starting signal),
# so they are not "leaves" of the team block.
_PLAYER_ARRAYS = ("startXI", "substitutes")

_KNOWN_PLAYER_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("player", "id"),
        ("player", "name"),
        ("player", "number"),
        ("player", "pos"),
        ("player", "grid"),
    }
)

# team_id is part of the conflict key (uq_lineups) and therefore MUST NOT appear
# in the DO UPDATE set — "cannot affect row a second time" aside, a row's team is
# what identifies it here. Everything else the endpoint owns is refreshed, and
# that includes is_starting: a bench<->XI correction must apply in place.
_UPDATE_COLUMNS = [
    "source_fetched_at",
    "formation",
    "coach_name",
    "coach_source_ref",
    "player_name",
    "jersey_number",
    "position",
    "grid",
    "is_starting",
    "source_extra",
]


def _collect_leaves(node: Any, prefix: tuple[str, ...], out: dict[tuple[str, ...], Any]) -> None:
    """Flatten a nested object into {path_tuple: leaf_value}."""
    if isinstance(node, dict):
        for key, value in node.items():
            _collect_leaves(value, prefix + (key,), out)
    elif isinstance(node, list):
        # No list-valued leaf exists in this payload outside the player arrays;
        # if one appears, record it whole rather than guess at its shape.
        out[prefix] = node
    else:
        out[prefix] = node


def _unmapped(node: Any, known: frozenset, ignored: frozenset, skip_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    """{dotted_path: value} for every leaf that is neither mapped nor ignored."""
    leaves: dict[tuple[str, ...], Any] = {}
    for key, value in (node or {}).items():
        if key in skip_keys:
            continue
        _collect_leaves(value, (key,), leaves)
    return {
        ".".join(path): value
        for path, value in leaves.items()
        if path not in known and path not in ignored
    }


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


def _preload_player_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football player, read once.

    The fast path for FK resolution: on EPL every player already exists (seeded by
    /fixtures/players), so this map answers every lookup with zero extra queries.
    """
    cur.execute(
        "select source_ref, id from curated.players where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: pid for ref, pid in cur.fetchall()}


def _preload_done_fixture_ids(cur) -> set[int]:
    """Our fixture ids that already have lineup rows (resume + save calls).

    Sound only because every row for a fixture commits in ONE transaction, so a
    fixture is never half-written: any row present => that fixture is complete.
    """
    cur.execute("select distinct fixture_id from curated.lineups")
    return {row[0] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# rate-limit visibility — log only, no backoff / auto-pause (D-087)
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
# player resolution — READ-MOSTLY (deliberately NOT the D-090 thin seed)
# ---------------------------------------------------------------------------


def _resolve_or_seed_player(
    cur,
    player: dict,
    fetched_at: Any,
    player_ids: dict[str, int],
    staged_ids: dict[str, int],
) -> tuple[int, bool]:
    """Return (our player id, seeded?) for a lineup player.

    Resolve first; only INSERT when the player is genuinely unknown, and then with
    ON CONFLICT DO NOTHING — never DO UPDATE. This endpoint carries no photo and
    no bio, so an update would write photo_url=NULL over what /fixtures/players
    already stored. An existing player row is READ here, never rewritten.

    The insert path is not dead code: an unused substitute (named on the bench,
    never came on) has no /fixtures/players stat row, so a lineup can legitimately
    be the first place we ever see that player.

    Q-NEW-AR: this function NEVER writes `player_ids`. Anything it resolves or seeds
    goes into `staged_ids`, the caller's PER-FIXTURE staging map, because we are inside
    that fixture's still-open transaction. If the fixture later rolls back (an unresolved
    team, D-092, or a parse failure), the seeded row is undone — and a cached id would
    then be a phantom: a later fixture naming the same player would take the fast path,
    get an id whose row does not exist, and build a lineup row on a dead FK. The caller
    merges staged_ids into player_ids only AFTER the fixture commits.
    """
    ref = str(player["id"])

    our_id = player_ids.get(ref)
    if our_id is not None:
        return our_id, False

    # Seeded earlier in THIS fixture's transaction: uncommitted, but our own transaction
    # sees it, so it resolves normally and a repeated player costs no second INSERT.
    our_id = staged_ids.get(ref)
    if our_id is not None:
        return our_id, False

    name = player.get("name")
    if name is None:
        # curated.players.name is NOT NULL — we cannot invent one.
        raise SyncError(f"player source_ref={ref} is new but has no name; refusing to seed")

    # DO NOTHING (not DO UPDATE): if a concurrent run created it between our SELECT
    # and this INSERT, we keep their row untouched and simply read the id back.
    cur.execute(
        "insert into curated.players (source, source_ref, source_fetched_at, sport, name) "
        "values (%s, %s, %s, %s, %s) "
        "on conflict (sport, source, source_ref) do nothing "
        "returning id",
        (SOURCE, ref, fetched_at, SPORT, name),
    )
    row = cur.fetchone()
    if row is None:
        # DO NOTHING suppressed the RETURNING — the row already existed. Read it.
        cur.execute(
            "select id from curated.players where sport = %s and source = %s and source_ref = %s",
            (SPORT, SOURCE, ref),
        )
        row = cur.fetchone()
        if row is None:
            raise SyncError(f"player source_ref={ref} neither inserted nor found")
        staged_ids[ref] = row[0]
        return row[0], False

    staged_ids[ref] = row[0]
    return row[0], True


# ---------------------------------------------------------------------------
# normalization — every value read FROM the landed payload (D-071)
# ---------------------------------------------------------------------------


def _build_lineup_values(
    entry: dict,
    *,
    is_starting: bool,
    our_fixture_id: int,
    our_team_id: int,
    our_player_id: int,
    formation: str | None,
    coach_name: str | None,
    coach_source_ref: str | None,
    team_extra: dict[str, Any],
    fetched_at: Any,
    unmapped_seen: set[str],
) -> dict:
    """Turn one startXI/substitutes entry into a curated.lineups values dict."""
    player = entry.get("player") or {}

    extra: dict[str, Any] = dict(team_extra)
    for path, value in _unmapped(entry, _KNOWN_PLAYER_PATHS, frozenset()).items():
        extra[path] = value
        unmapped_seen.add(path)

    return {
        "source": SOURCE,
        "source_ref": None,  # composite-keyed row: identity is (fixture, team, player) — D-057
        "source_fetched_at": fetched_at,
        "sport": SPORT,
        "fixture_id": our_fixture_id,
        "team_id": our_team_id,
        "player_id": our_player_id,
        "formation": formation,
        "coach_name": coach_name,
        "coach_source_ref": coach_source_ref,
        "player_name": _parse_text(player.get("name")),
        "jersey_number": _parse_int(player.get("number")),
        "position": _parse_text(player.get("pos")),
        "grid": _parse_grid(player.get("grid")),
        "is_starting": is_starting,
        "source_extra": Jsonb(extra) if extra else None,
    }


def ingest_lineups(
    conn,
    api,
    resolver: ResolutionMap,
    league: int,
    season: int,
    *,
    limit: int | None = None,
    sleep: float = 0.5,
) -> dict:
    """Ingest starting XI + bench for every fixture of one league-season.

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
                "select id, cov_lineups from curated.league_seasons "
                "where league_id = %s and season = %s",
                (our_league_id, season),
            )
            row = cur.fetchone()
            if row is None:
                raise SyncError(
                    f"league_season (league_id={our_league_id}, season={season}) missing "
                    "— run --entity leagues first"
                )
            league_season_id, cov_lineups = row

            # Coverage pre-check: warn, never hard-block (the flag is the vendor's
            # claim about the season, not a guarantee about any single fixture).
            if not cov_lineups:
                print(
                    f"WARNING  cov_lineups={cov_lineups!r} for league_season_id="
                    f"{league_season_id} — the source claims lineups are not covered "
                    "for this season. Proceeding anyway."
                )

            team_ids = _preload_team_ids(cur)
            player_ids = _preload_player_ids(cur)
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
        f"{len(done_fixture_ids)} already have lineups; "
        f"{len(team_ids)} teams / {len(player_ids)} players preloaded"
    )

    written = 0             # curated.lineups rows written
    players_seeded = 0      # NEW players inserted (expect 0 on EPL)
    skipped_existing = 0
    no_stats: list[str] = []
    failed: list[tuple[str, str]] = []
    unmapped_seen: set[str] = set()
    deduped = 0             # (team, player) collisions across startXI/substitutes
    coach_blocks = 0        # team blocks seen
    coach_null_blocks = 0   # ... of which coach.name was NULL (census -> Q-NEW-AH)
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
        # Fresh per fixture (Q-NEW-AR). staged_ids holds ids seeded/resolved inside this
        # fixture's transaction — invisible to later fixtures until this one COMMITS. The
        # seed count and its log lines are buffered on the same boundary, for the same
        # reason: on rollback all three die with the iteration, so there is no phantom id,
        # no phantom count, and no orphan SEEDED line above the FAILED line.
        staged_ids: dict[str, int] = {}
        fixture_seeded = 0
        seed_logs: list[str] = []

        try:
            fetched = _fetch(conn, api, ENDPOINT, params)
            calls_made += 1
            remaining = _remaining_budget(api)

            # One transaction per fixture: the raw row and every curated row commit
            # together (D-071). The except below sits OUTSIDE, so any failure rolls
            # the whole fixture back cleanly — N-rows-or-0, never a partial fixture —
            # and the connection stays usable.
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
                        print(f"  NO LINEUPS fixture={source_ref} ({reason}) -> 0 rows")
                        continue

                    # Build every row for the fixture first, deduped on the natural
                    # key. Two entries with the same (team, player) would make the
                    # ON CONFLICT DO UPDATE hit one row twice, which Postgres aborts
                    # with "cannot affect row a second time" — losing the fixture.
                    # startXI is walked first, so first-wins == starter-wins.
                    rows: dict[tuple[int, int], dict] = {}
                    fixture_deduped = 0

                    for block in blocks:
                        # team_id is NOT NULL / ON DELETE RESTRICT: an unresolved team
                        # RAISES and rolls the whole fixture back — we never skip the
                        # block or default the team (D-092).
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

                        formation = _parse_text(block.get("formation"))
                        coach_name = _parse_text(_dig(block, "coach", "name"))
                        coach_ref = _dig(block, "coach", "id")
                        coach_source_ref = None if coach_ref is None else str(coach_ref)

                        coach_blocks += 1
                        if coach_name is None:
                            coach_null_blocks += 1

                        # Team-level leaves we neither map nor knowingly drop go to
                        # source_extra on every row of this block, and are logged.
                        team_extra = _unmapped(
                            block, _KNOWN_TEAM_PATHS, _IGNORED_TEAM_PATHS,
                            skip_keys=_PLAYER_ARRAYS,
                        )
                        for path in team_extra:
                            unmapped_seen.add(path)

                        for section, is_starting in (
                            ("startXI", True),
                            ("substitutes", False),
                        ):
                            for entry in block.get(section) or []:
                                player = entry.get("player") or {}
                                if player.get("id") is None:
                                    raise SyncError(
                                        f"{section} entry missing player.id "
                                        f"(fixture={source_ref}, team={team_ref})"
                                    )

                                our_player_id, seeded = _resolve_or_seed_player(
                                    cur, player, fetched_at, player_ids, staged_ids
                                )
                                if seeded:
                                    fixture_seeded += 1
                                    seed_logs.append(
                                        f"  SEEDED new player id={player['id']} "
                                        f"{player.get('name')!r} (no /fixtures/players row)"
                                    )

                                key = (our_team_id, our_player_id)
                                if key in rows:
                                    # startXI already claimed this player — keep it.
                                    fixture_deduped += 1
                                    continue

                                rows[key] = _build_lineup_values(
                                    entry,
                                    is_starting=is_starting,
                                    our_fixture_id=our_fixture_id,
                                    our_team_id=our_team_id,
                                    our_player_id=our_player_id,
                                    formation=formation,
                                    coach_name=coach_name,
                                    coach_source_ref=coach_source_ref,
                                    team_extra=team_extra,
                                    fetched_at=fetched_at,
                                    unmapped_seen=unmapped_seen,
                                )

                    if fixture_deduped:
                        deduped += fixture_deduped
                        print(
                            f"  WARNING fixture={source_ref}: {fixture_deduped} player(s) "
                            "appeared in BOTH startXI and substitutes — kept the startXI "
                            "entry (is_starting=True)"
                        )

                    for values in rows.values():
                        upsert_returning_id(
                            cur,
                            "curated.lineups",
                            values=values,
                            conflict_columns=["fixture_id", "team_id", "player_id"],
                            update_columns=_UPDATE_COLUMNS,
                        )

                    fixture_rows = len(rows)
                    written += fixture_rows

            # The transaction context manager exited cleanly == COMMITTED. Only now are
            # these ids backed by rows that survive, so only now may they enter the
            # persistent cache and be handed to later fixtures — and only now is a seed
            # real enough to count and to log.
            player_ids.update(staged_ids)
            players_seeded += fixture_seeded
            for line in seed_logs:
                print(line)

            print(
                f"  [{processed}] fixture={source_ref} -> {fixture_rows} lineup row(s)  "
                f"remaining={remaining}"
            )

        except Exception as exc:  # noqa: BLE001 — one bad fixture must not abort the run
            # staged_ids / fixture_seeded / seed_logs die with this iteration: player_ids
            # never saw the phantom id, the count never counted it, the log never claimed it.
            failed.append((str(source_ref), str(exc)))
            print(f"  FAILED fixture={source_ref}: {exc}")
            continue

    # --- report ---------------------------------------------------------------
    if unmapped_seen:
        print(f"\nNOTE  {len(unmapped_seen)} unmapped leaf(s) -> source_extra:")
        for leaf in sorted(unmapped_seen):
            print(f"        {leaf!r}")
    else:
        print("\nNOTE  every leaf mapped or knowingly dropped; source_extra NULL throughout")

    # Free census (log-only) — feeds Q-NEW-AH: is a coaches table worth having?
    if coach_blocks:
        pct = coach_null_blocks / coach_blocks * 100
        print(
            f"NOTE  coach census: {coach_null_blocks}/{coach_blocks} team block(s) had "
            f"coach.name NULL ({pct:.1f}%)"
        )

    if deduped:
        print(f"NOTE  {deduped} startXI/substitutes duplicate(s) deduped (startXI won)")

    if no_stats:
        print(f"\nNOTE  {len(no_stats)} fixture(s) had no usable lineups (0 rows written):")
        print(f"        {', '.join(no_stats)}")

    if failed:
        print(f"\nFAILED  {len(failed)} fixture(s) — re-run to retry exactly these:")
        for source_ref, message in failed:
            print(f"        fixture={source_ref}: {message}")

    print(
        f"\nAPI calls made: {calls_made}  (last remaining budget: {remaining})"
        f"  players seeded: {players_seeded}"
    )

    return {
        "written": written,
        "players_seeded": players_seeded,
        "skipped_existing": skipped_existing,
        "no_stats": len(no_stats),
        "deduped": deduped,
        "coach_blocks": coach_blocks,
        "coach_null_blocks": coach_null_blocks,
        "failed": [source_ref for source_ref, _ in failed],
        "calls_made": calls_made,
        "remaining_budget": remaining,
    }
