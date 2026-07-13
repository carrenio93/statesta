"""Player bio enrichment — /players -> curated.players.

The first PAGINATED worker. Its three siblings (fixtures, match_statistics,
lineups, player_match_stats) all loop over FIXTURES, one API call each. This one
loops over PAGES of a league-season roster, so the unit of work — and therefore
the unit of the transaction, of --limit, and of the N-rows-or-0 guarantee — is a
PAGE, not a fixture.

Everything else is the house pattern: raw-first (D-071 — call, land, normalize
from the LANDED payload, never from the live HTTP response), ON CONFLICT ...
RETURNING id via upsert_returning_id (D-073), one transaction per unit of work so
the raw row and its ~20 curated rows commit together, /status + last_headers
budget logging (D-087).

Payload shape (probed against league=39 season=2025 page=1): `paging` is
{current, total} — total is the page count and therefore the whole run's API-call
budget (34 for EPL 2025). `response` is a list of ~20 items, each
{"player": {...}, "statistics": [...]}. We ingest the PERSON and ignore the
season stats entirely: this worker enriches who a player IS, not how they played.

Two things make this worker different from its siblings:

  * It ENRICHES rows it did not create. curated.players is seeded thin by
    /fixtures/players (D-090) and /fixtures/lineups (D-095) — 687 rows whose bio
    is 100% NULL. So the DO-UPDATE path is the NORMAL path here, not the
    idempotent-re-run path, and what the update set contains matters more than
    usual.
  * `photo_url` is CONDITIONALLY in the update set, per player. 679 of our rows
    already carry a photo (from /fixtures/players); 8 do not (bench players seeded
    by /fixtures/lineups, which carries no photo). We must fill those 8 without
    ever blanking the 679. upsert_returning_id emits a literal `col = excluded.col`
    for every update column and cannot express
    `coalesce(excluded.photo_url, players.photo_url)`, so the coalesce is done in
    Python: photo_url joins the update set ONLY when the incoming value is
    non-None. Absent photo => column simply not updated => existing value survives.

`name` is NEVER in the update set: the thin seed owns identity (D-090/D-095), and
the /players `name` is an abbreviated form ("C. Gakpo") that must not overwrite
whatever the seed established. `updated_at` is never written by hand either — the
trg_players_updated_at trigger owns it.

No skip-set: enrichment is idempotent, so resume is simply "run it again".

Run (via the shared worker entrypoint):
    python -m statesta_sync.spine --entity player_bio --league 39 --season 2025 --limit 1
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from .ingest_common import SOURCE, SPORT, SyncError, _dig, _fetch, _land
from .upsert import ResolutionMap, upsert_returning_id

ENDPOINT = "/players"


# ---------------------------------------------------------------------------
# value parsing — absent stays NULL, a parse failure RAISES (never a silent NULL)
# Same discipline as the sibling workers (D-085/D-086).
# ---------------------------------------------------------------------------


def _parse_text(value: Any) -> str | None:
    """Text passthrough. null -> NULL; a non-string is a vendor change -> raise.

    height and weight go through here UNCHANGED: the API sends them as bare
    strings ("193", "76") and curated.players.height/.weight are text columns.
    We store the vendor's string verbatim — no int parse, no unit assumption.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as text")


def _parse_date(value: Any) -> date | None:
    """birth.date 'YYYY-MM-DD' -> date. null -> NULL. Anything else RAISES."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise SyncError(f"cannot parse {value!r} ({type(value).__name__}) as date")
    text = value.strip()
    if not text:
        return None  # empty string is the vendor saying "nothing" -> NULL (§6.7)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SyncError(f"cannot parse {value!r} as an ISO date (YYYY-MM-DD)") from exc


# ---------------------------------------------------------------------------
# leaf census (Q-NEW-AQ) — what we map, and what we deliberately drop.
#
# KNOWN = mapped to a column. IGNORED = seen, understood, intentionally not in
# curated. Anything else is UNMAPPED: logged loudly AND kept verbatim in
# source_extra, so a field the vendor adds on some future league can never be
# silently lost. Recon says EPL page 1 has exactly 13 leaves = 11 + 2, so we
# expect the unmapped set to stay empty.
# ---------------------------------------------------------------------------

_KNOWN_PLAYER_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("id",),
        ("name",),
        ("firstname",),
        ("lastname",),
        ("birth", "date"),
        ("birth", "place"),
        ("birth", "country"),
        ("nationality",),
        ("height",),
        ("weight",),
        ("photo",),
    }
)

# Deliberately dropped, raw-only — the D-097 "cosmetics" precedent:
#   age      — DERIVED. It is birth.date and today's date, and it would go stale
#              the moment we stored it. Compute it at read time from birth_date.
#   injured  — VOLATILE point-in-time flag, not a biographical fact. Freezing it
#              at sync time would give us a value that is wrong within days and
#              carries no as-of timestamp. If we ever want injuries they deserve
#              their own endpoint (/injuries) and their own table.
# Neither goes to source_extra, and neither trips the unmapped alarm.
_IGNORED_PLAYER_PATHS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("age",),
        ("injured",),
    }
)

# The base DO-UPDATE set. photo_url is appended PER PLAYER, and only when the
# incoming photo is non-None (see _update_columns_for).
#
# Deliberately absent:
#   name       — the thin seed owns identity (D-090/D-095). /players sends an
#                abbreviated "C. Gakpo"; the seed holds the fuller form.
#   updated_at — owned by trg_players_updated_at. Writing it by hand would fight
#                the trigger.
#   sport / source / source_ref — the conflict key itself.
_BASE_UPDATE_COLUMNS = [
    "firstname",
    "lastname",
    "birth_date",
    "birth_country",
    "birth_place",
    "nationality",
    "height",
    "weight",
    "source_fetched_at",
    "source_extra",
]


def _collect_leaves(node: Any, prefix: tuple[str, ...], out: dict[tuple[str, ...], Any]) -> None:
    """Flatten a nested object into {path_tuple: leaf_value}."""
    if isinstance(node, dict):
        for key, value in node.items():
            _collect_leaves(value, prefix + (key,), out)
    elif isinstance(node, list):
        # No list-valued leaf exists under `player` in this payload; if one
        # appears, record it whole rather than guess at its shape.
        out[prefix] = node
    else:
        out[prefix] = node


def _unmapped(player: dict) -> dict[str, Any]:
    """{dotted_path: value} for every leaf under `player` we neither map nor drop."""
    leaves: dict[tuple[str, ...], Any] = {}
    for key, value in (player or {}).items():
        _collect_leaves(value, (key,), leaves)
    return {
        ".".join(path): value
        for path, value in leaves.items()
        if path not in _KNOWN_PLAYER_PATHS and path not in _IGNORED_PLAYER_PATHS
    }


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
# normalization — every value read FROM the landed payload (D-071)
# ---------------------------------------------------------------------------


def _build_player_values(
    player: dict,
    *,
    fetched_at: Any,
    unmapped_seen: set[str],
) -> dict:
    """Turn one `player` object into a curated.players values dict (INSERT path).

    Every one of the 11 mapped leaves is optional in the payload except `id` and
    `name`, which back NOT NULL columns and therefore cannot be invented (D-086).
    """
    if player.get("id") is None:
        raise SyncError("player object has no id — refusing to guess a source_ref")

    # curated.players.name is NOT NULL. On the INSERT path we must have one; on the
    # DO-UPDATE path the value is discarded anyway (name is not an update column).
    name = _parse_text(player.get("name"))
    if name is None:
        raise SyncError(f"player id={player['id']} has no name — refusing to seed")

    extra: dict[str, Any] = {}
    for path, value in _unmapped(player).items():
        extra[path] = value
        unmapped_seen.add(path)

    return {
        "source": SOURCE,
        "source_ref": str(player["id"]),
        "source_fetched_at": fetched_at,
        "sport": SPORT,
        "name": name,
        "firstname": _parse_text(player.get("firstname")),
        "lastname": _parse_text(player.get("lastname")),
        "birth_date": _parse_date(_dig(player, "birth", "date")),
        "birth_country": _parse_text(_dig(player, "birth", "country")),
        "birth_place": _parse_text(_dig(player, "birth", "place")),
        "nationality": _parse_text(player.get("nationality")),
        # verbatim TEXT — the vendor sends "193" / "76"; no parse, no unit.
        "height": _parse_text(player.get("height")),
        "weight": _parse_text(player.get("weight")),
        "photo_url": _parse_text(player.get("photo")),
        "source_extra": Jsonb(extra) if extra else None,
    }


def _update_columns_for(values: dict) -> list[str]:
    """The DO-UPDATE set for THIS player — the Python-side coalesce.

    upsert_returning_id can only emit `col = excluded.col`, so it cannot express
    `photo_url = coalesce(excluded.photo_url, players.photo_url)`. We get the same
    effect by deciding per row whether photo_url is in the set at all:

      incoming photo present -> photo_url IS updated  (fills the 8 NULL photos)
      incoming photo absent  -> photo_url is NOT in the set, so the column is left
                                exactly as it was     (never blanks the 679)

    Absent means "no new information", never "set it to NULL" (§6.7).
    """
    columns = list(_BASE_UPDATE_COLUMNS)
    if values.get("photo_url") is not None:
        columns.append("photo_url")
    return columns


def ingest_player_bio(
    conn,
    api,
    resolver: ResolutionMap,
    league: int,
    season: int,
    *,
    limit: int | None = None,
    sleep: float = 0.5,
) -> dict:
    """Enrich curated.players with the person-level bio for one league-season roster.

    Signature matches the other --entity workers; --limit / --sleep arrive as
    keyword-only options from the CLI. --limit bounds PAGES, not players.
    """
    _log_account_status(api)
    calls_made = 1  # the /status call above

    # The league must exist, for the same reason every other worker checks: a typo'd
    # --league would otherwise ingest a different competition's roster into our
    # players table without complaint. curated.players has no league FK, so this is
    # a sanity gate, not a foreign-key resolution.
    #
    # The same transaction preloads every player source_ref we already hold. The
    # upsert is a single ON CONFLICT statement and cannot tell us which arm it took,
    # so this set is how we report insert-vs-update honestly: the roster carries both
    # players we know (appeared in a fixture -> thin-seeded) and players we don't
    # (registered but never played). Read once, up front — the same preload pattern
    # the sibling workers use for FK resolution.
    with conn.transaction():
        with conn.cursor() as cur:
            our_league_id = resolver.resolve(cur, "leagues", league)
            if our_league_id is None:
                raise SyncError(
                    f"league source_ref={league} not in curated.leagues "
                    "— run --entity leagues first"
                )

            cur.execute(
                "select source_ref from curated.players where sport = %s and source = %s",
                (SPORT, SOURCE),
            )
            existing_refs = {row[0] for row in cur.fetchall()}

    print(f"{len(existing_refs)} player(s) already in curated.players before this run")

    written = 0                    # curated.players rows upserted
    inserted = 0                   # ... of which NEW (never seen before this run)
    updated = 0                    # ... of which enriched in place
    photos_supplied = 0            # payload carried a photo -> photo_url in update set
    photos_absent = 0              # payload had no photo -> column left untouched
    pages_done = 0
    processed = 0                  # pages ATTEMPTED (what --limit bounds)
    total_pages: int | None = None
    empty_pages: list[int] = []
    failed: list[tuple[int, str]] = []
    unmapped_seen: set[str] = set()
    remaining = None
    page = 1

    while True:
        # --limit bounds PAGES processed, so --limit 1 makes exactly one /players call.
        if limit is not None and processed >= limit:
            break

        if processed and sleep:
            time.sleep(sleep)

        processed += 1
        params = {"league": league, "season": season, "page": page}

        try:
            # Explicit page=1 is ACCEPTED by /players (verified in recon: HTTP 200,
            # errors=[], parameters echoes "page":"1"). This is NOT the /fixtures
            # behaviour, where an explicit page field is rejected and must be sent
            # only when >= 2. The endpoints differ; do not "fix" one to match the other.
            fetched = _fetch(conn, api, ENDPOINT, params)
            calls_made += 1
            remaining = _remaining_budget(api)

            # One transaction per PAGE: the raw row and every curated row from that
            # page commit together (D-071). The except below sits OUTSIDE, so a
            # mid-page failure rolls the whole page back — 20-rows-or-0, never a
            # half-written page — and the connection stays usable.
            with conn.transaction():
                with conn.cursor() as cur:
                    payload, fetched_at = _land(cur, fetched)

                    if total_pages is None:
                        total_pages = _dig(payload, "paging", "total")
                        if not isinstance(total_pages, int) or total_pages < 1:
                            raise SyncError(
                                f"{ENDPOINT} {params}: paging.total is {total_pages!r} "
                                "— cannot determine how many pages to fetch"
                            )
                        print(
                            f"paging.total={total_pages} page(s) for league={league} "
                            f"season={season}  (~{total_pages * 20} players, "
                            f"{total_pages} API call(s) for a full run)"
                        )

                    items = payload.get("response") or []

                    # Absent, not invented (D-081): an empty page writes nothing and is
                    # logged. The raw row still lands, so the gap is provable from raw.
                    if not items:
                        empty_pages.append(page)
                        print(f"  EMPTY page={page} (no response[] items) -> 0 rows")
                        page_rows = 0
                    else:
                        page_rows = 0
                        for item in items:
                            # item.statistics is the season aggregate. This worker
                            # enriches the PERSON, not the season — we never read it,
                            # never warehouse it, and it never trips the unmapped alarm.
                            player = item.get("player") or {}

                            values = _build_player_values(
                                player,
                                fetched_at=fetched_at,
                                unmapped_seen=unmapped_seen,
                            )

                            if values["photo_url"] is not None:
                                photos_supplied += 1
                            else:
                                photos_absent += 1

                            # Classify BEFORE the upsert — afterwards the ON CONFLICT
                            # statement looks identical either way. Adding the new ref
                            # immediately means a player repeated on a later page counts
                            # as one insert and then an update, never two inserts.
                            ref = values["source_ref"]
                            if ref in existing_refs:
                                updated += 1
                            else:
                                inserted += 1
                                existing_refs.add(ref)

                            upsert_returning_id(
                                cur,
                                "curated.players",
                                values=values,
                                conflict_columns=["sport", "source", "source_ref"],
                                update_columns=_update_columns_for(values),
                            )
                            page_rows += 1

                    written += page_rows

            pages_done += 1
            print(
                f"  [{page}/{total_pages}] -> {page_rows} player row(s)  "
                f"remaining={remaining}"
            )

        except Exception as exc:  # noqa: BLE001 — one bad page must not abort the run
            # Page 1 is different: it is the page that tells us paging.total. Without
            # it we do not know how many pages exist, so there is no run to continue.
            if page == 1:
                raise
            failed.append((page, str(exc)))
            print(f"  FAILED page={page}: {exc}")

        if total_pages is not None and page >= total_pages:
            break
        page += 1

    # --- report ---------------------------------------------------------------
    if unmapped_seen:
        print(f"\nNOTE  {len(unmapped_seen)} unmapped leaf(s) -> source_extra:")
        for leaf in sorted(unmapped_seen):
            print(f"        {leaf!r}")
    else:
        print("\nNOTE  every leaf mapped or knowingly dropped; source_extra NULL throughout")

    print(
        f"NOTE  upsert census: {written} row(s) upserted = {inserted} INSERTED "
        f"(on the roster but never seen in a fixture) + {updated} UPDATED "
        "(thin-seeded row enriched in place)"
    )

    print(
        f"NOTE  photo census: {photos_supplied} player(s) carried a photo "
        f"(photo_url in the update set), {photos_absent} did not "
        "(photo_url left untouched — an existing photo is never blanked)"
    )

    if empty_pages:
        print(f"\nNOTE  {len(empty_pages)} empty page(s) (0 rows written): {empty_pages}")

    if failed:
        print(f"\nFAILED  {len(failed)} page(s) — re-run to retry (enrichment is idempotent):")
        for failed_page, message in failed:
            print(f"        page={failed_page}: {message}")

    print(f"\nAPI calls made: {calls_made}  (last remaining budget: {remaining})")

    return {
        "written": written,
        "inserted": inserted,
        "updated": updated,
        "pages_done": pages_done,
        "total_pages": total_pages,
        "photos_supplied": photos_supplied,
        "photos_absent": photos_absent,
        "empty_pages": empty_pages,
        "failed": [failed_page for failed_page, _ in failed],
        "calls_made": calls_made,
        "remaining_budget": remaining,
    }
