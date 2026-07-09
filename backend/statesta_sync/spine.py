"""EPL-2025 static-spine sync worker (SYNC_INGESTION_DESIGN.md Parts 2-5).

Sync order is the topological sort of the curated FK graph (D-072):

    leagues -> league_seasons -> venues -> teams -> standings

Each entity: fetch -> land raw -> normalize FROM the landed payload (D-071)
-> upsert with ON CONFLICT ... RETURNING id (D-073), all inside one transaction
so the raw row and the curated rows commit together.

Run one entity at a time:
    python -m statesta_sync.spine --entity leagues
    python -m statesta_sync.spine --entity teams
    python -m statesta_sync.spine --entity standings
    python -m statesta_sync.spine --entity fixtures   # event data (see fixtures.py)

There is no default entity: nothing writes unless you name it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Any, NamedTuple

from psycopg.types.json import Jsonb

from .api_football import ApiFootballClient
from .config import load_config
from .db import connect
from .raw_landing import land_raw, read_raw, utcnow
from .upsert import ISSUED, ResolutionMap, upsert_returning_id

SPORT = "football"
SOURCE = "api_football"
UNMAPPED_TIER = "?"  # D-012: newly discovered leagues land unmapped, awaiting review

DEFAULT_LEAGUE = 39  # API-Football: Premier League
DEFAULT_SEASON = 2025


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


def _as_date(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


def _lower_or_none(value: Any) -> str | None:
    return value.lower() if isinstance(value, str) and value else None


def _extra(obj: dict, mapped_keys: set[str]) -> Jsonb | None:
    """Capture any payload keys we don't model as columns (§6.1 capture-every-field).

    Returns NULL when the source carried nothing beyond what we mapped. If the
    vendor adds a field later it lands here automatically instead of being lost.
    """
    leftover = {k: v for k, v in obj.items() if k not in mapped_keys}
    return Jsonb(leftover) if leftover else None


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


# ---------------------------------------------------------------------------
# Entity 1 — /leagues -> curated.leagues + curated.league_seasons
# ---------------------------------------------------------------------------


def sync_leagues(conn, api, resolver: ResolutionMap, league: int, season: int) -> dict:
    endpoint = "/leagues"
    params = {"id": league, "season": season}
    fetched = _fetch(conn, api, endpoint, params)

    with conn.transaction():
        with conn.cursor() as cur:
            payload, fetched_at = _land(cur, fetched)

            entries = payload.get("response") or []
            if not entries:
                raise SyncError(f"{endpoint} {params}: empty response[]")
            entry = entries[0]

            league_obj = entry.get("league") or {}
            country_obj = entry.get("country") or {}

            # --- curated.leagues -------------------------------------------
            # tier_id/needs_review are set on INSERT only. They are deliberately
            # NOT in update_columns: a re-run must never reset an admin-assigned
            # tier back to '?' (D-012, §4.2.4).
            league_id = upsert_returning_id(
                cur,
                "curated.leagues",
                values={
                    "source": SOURCE,
                    "source_ref": str(league_obj["id"]),
                    "source_fetched_at": fetched_at,
                    "sport": SPORT,
                    "name": league_obj["name"],
                    "type": _lower_or_none(league_obj.get("type")),
                    "country_name": country_obj.get("name"),
                    "country_code": country_obj.get("code"),
                    "logo_url": league_obj.get("logo"),
                    "flag_url": country_obj.get("flag"),
                    "tier_id": UNMAPPED_TIER,
                    "needs_review": True,
                },
                conflict_columns=["sport", "source", "source_ref"],
                update_columns=[
                    "source_fetched_at",
                    "name",
                    "type",
                    "country_name",
                    "country_code",
                    "logo_url",
                    "flag_url",
                ],
            )
            resolver.remember("leagues", league_obj["id"], league_id)

            # --- curated.league_seasons ------------------------------------
            seasons = entry.get("seasons") or []
            season_obj = next((s for s in seasons if s.get("year") == season), None)
            if season_obj is None:
                raise SyncError(f"{endpoint} {params}: season {season} not in seasons[]")

            coverage = season_obj.get("coverage") or {}
            fixtures_cov = coverage.get("fixtures") or {}

            # cov_fixtures has no literal boolean in the payload; it is the OR of
            # the four fixtures sub-flags. If none are present it stays NULL
            # ("we don't yet know"), never false (§6.7).
            sub_flags = [
                fixtures_cov.get("events"),
                fixtures_cov.get("lineups"),
                fixtures_cov.get("statistics_fixtures"),
                fixtures_cov.get("statistics_players"),
            ]
            present = [f for f in sub_flags if f is not None]
            cov_fixtures = any(present) if present else None

            league_season_id = upsert_returning_id(
                cur,
                "curated.league_seasons",
                values={
                    "source": SOURCE,
                    "source_ref": None,  # derived row, identity is (league_id, season) — D-057
                    "source_fetched_at": fetched_at,
                    "league_id": league_id,
                    "season": season,
                    "start_date": _as_date(season_obj.get("start")),
                    "end_date": _as_date(season_obj.get("end")),
                    "is_current": bool(season_obj.get("current")),
                    "cov_standings": coverage.get("standings"),
                    "cov_fixtures": cov_fixtures,
                    "cov_fixture_statistics": fixtures_cov.get("statistics_fixtures"),
                    "cov_lineups": fixtures_cov.get("lineups"),
                    "cov_player_statistics": fixtures_cov.get("statistics_players"),
                    "cov_odds": coverage.get("odds"),
                    # full verbatim coverage object: keeps the sub-flags we don't
                    # model as columns (players, top_scorers, injuries, ...)
                    "source_extra": Jsonb({"coverage": coverage}),
                },
                conflict_columns=["league_id", "season"],
                update_columns=[
                    "source_fetched_at",
                    "start_date",
                    "end_date",
                    "is_current",
                    "cov_standings",
                    "cov_fixtures",
                    "cov_fixture_statistics",
                    "cov_lineups",
                    "cov_player_statistics",
                    "cov_odds",
                    "source_extra",
                ],
            )

    return {"league_id": league_id, "league_season_id": league_season_id}


# ---------------------------------------------------------------------------
# Entity 2 — /teams -> curated.venues then curated.teams   (NOT RUN YET)
# ---------------------------------------------------------------------------


def sync_teams(conn, api, resolver: ResolutionMap, league: int, season: int) -> dict:
    endpoint = "/teams"
    params = {"league": league, "season": season}
    fetched = _fetch(conn, api, endpoint, params)

    with conn.transaction():
        with conn.cursor() as cur:
            payload, fetched_at = _land(cur, fetched)

            our_league_id = resolver.resolve(cur, "leagues", league)
            if our_league_id is None:
                raise SyncError(
                    f"league source_ref={league} not in curated.leagues — run --entity leagues first"
                )

            entries = payload.get("response") or []
            if not entries:
                raise SyncError(f"{endpoint} {params}: empty response[]")

            venue_count = 0
            for entry in entries:
                team_obj = entry.get("team") or {}
                venue_obj = entry.get("venue") or {}

                # --- curated.venues (parent — must exist before teams) ------
                our_venue_id = None
                if venue_obj.get("id") is not None:
                    our_venue_id = upsert_returning_id(
                        cur,
                        "curated.venues",
                        values={
                            "source": SOURCE,
                            "source_ref": str(venue_obj["id"]),
                            "source_fetched_at": fetched_at,
                            "name": venue_obj.get("name"),
                            "address": venue_obj.get("address"),
                            "city": venue_obj.get("city"),
                            # the venue payload carries no country field -> NULL
                            "country_name": None,
                            "capacity": venue_obj.get("capacity"),
                            "surface": venue_obj.get("surface"),
                            "image_url": venue_obj.get("image"),
                            "source_extra": _extra(
                                venue_obj,
                                {"id", "name", "address", "city", "capacity", "surface", "image"},
                            ),
                        },
                        conflict_columns=["source", "source_ref"],
                        update_columns=[
                            "source_fetched_at",
                            "name",
                            "address",
                            "city",
                            "capacity",
                            "surface",
                            "image_url",
                            "source_extra",
                        ],
                    )
                    resolver.remember("venues", venue_obj["id"], our_venue_id)
                    venue_count += 1

                # --- curated.teams ------------------------------------------
                our_team_id = upsert_returning_id(
                    cur,
                    "curated.teams",
                    values={
                        "source": SOURCE,
                        "source_ref": str(team_obj["id"]),
                        "source_fetched_at": fetched_at,
                        "sport": SPORT,
                        "name": team_obj["name"],
                        "code": team_obj.get("code"),
                        "country_name": team_obj.get("country"),
                        # team payload has no country code -> NULL, never invented
                        "country_code": None,
                        "founded": team_obj.get("founded"),
                        "is_national": bool(team_obj.get("national")),
                        "logo_url": team_obj.get("logo"),
                        "venue_id": our_venue_id,
                        # soft denormalized pointer; last sync wins (Q-NEW-AG)
                        "current_league_id": our_league_id,
                        "source_extra": _extra(
                            team_obj,
                            {"id", "name", "code", "country", "founded", "national", "logo"},
                        ),
                    },
                    conflict_columns=["sport", "source", "source_ref"],
                    update_columns=[
                        "source_fetched_at",
                        "name",
                        "code",
                        "country_name",
                        "founded",
                        "is_national",
                        "logo_url",
                        "venue_id",
                        "current_league_id",
                        "source_extra",
                    ],
                )
                resolver.remember("teams", team_obj["id"], our_team_id)

    return {"teams": len(entries), "venues": venue_count}


# ---------------------------------------------------------------------------
# Entity 3 — /standings -> curated.standings   (NOT RUN YET)
# ---------------------------------------------------------------------------


def sync_standings(conn, api, resolver: ResolutionMap, league: int, season: int) -> dict:
    endpoint = "/standings"
    params = {"league": league, "season": season}
    fetched = _fetch(conn, api, endpoint, params)

    with conn.transaction():
        with conn.cursor() as cur:
            payload, fetched_at = _land(cur, fetched)

            our_league_id = resolver.resolve(cur, "leagues", league)
            if our_league_id is None:
                raise SyncError(f"league source_ref={league} not in curated.leagues")

            cur.execute(
                "select id from curated.league_seasons where league_id = %s and season = %s",
                (our_league_id, season),
            )
            row = cur.fetchone()
            if row is None:
                raise SyncError(
                    f"league_season (league_id={our_league_id}, season={season}) missing "
                    "— run --entity leagues first"
                )
            league_season_id = row[0]

            entries = payload.get("response") or []
            if not entries:
                raise SyncError(f"{endpoint} {params}: empty response[]")

            groups = _dig(entries[0], "league", "standings") or []
            single_group = len(groups) == 1  # single-table comp -> group_label NULL

            written = 0
            for group in groups:
                for srow in group:
                    vendor_team_id = _dig(srow, "team", "id")
                    our_team_id = resolver.resolve(cur, "teams", vendor_team_id)
                    if our_team_id is None:
                        raise SyncError(
                            f"team source_ref={vendor_team_id} not in curated.teams "
                            "— run --entity teams first"
                        )

                    update_ts = srow.get("update")
                    upsert_returning_id(
                        cur,
                        "curated.standings",
                        values={
                            "source": SOURCE,
                            "source_ref": None,  # derived row (D-057)
                            "source_fetched_at": fetched_at,
                            "league_season_id": league_season_id,
                            "team_id": our_team_id,
                            "group_label": None if single_group else srow.get("group"),
                            "rank": srow.get("rank"),
                            "points": srow.get("points"),
                            "goals_diff": srow.get("goalsDiff"),
                            "form": srow.get("form"),
                            "status": srow.get("status"),
                            "description": srow.get("description"),
                            "all_played": _dig(srow, "all", "played"),
                            "all_win": _dig(srow, "all", "win"),
                            "all_draw": _dig(srow, "all", "draw"),
                            "all_lose": _dig(srow, "all", "lose"),
                            "all_goals_for": _dig(srow, "all", "goals", "for"),
                            "all_goals_against": _dig(srow, "all", "goals", "against"),
                            "home_played": _dig(srow, "home", "played"),
                            "home_win": _dig(srow, "home", "win"),
                            "home_draw": _dig(srow, "home", "draw"),
                            "home_lose": _dig(srow, "home", "lose"),
                            "home_goals_for": _dig(srow, "home", "goals", "for"),
                            "home_goals_against": _dig(srow, "home", "goals", "against"),
                            "away_played": _dig(srow, "away", "played"),
                            "away_win": _dig(srow, "away", "win"),
                            "away_draw": _dig(srow, "away", "draw"),
                            "away_lose": _dig(srow, "away", "lose"),
                            "away_goals_for": _dig(srow, "away", "goals", "for"),
                            "away_goals_against": _dig(srow, "away", "goals", "against"),
                            "source_extra": Jsonb({"update": update_ts}) if update_ts else None,
                        },
                        conflict_columns=["league_season_id", "team_id"],
                        update_columns=[
                            "source_fetched_at",
                            "group_label",
                            "rank",
                            "points",
                            "goals_diff",
                            "form",
                            "status",
                            "description",
                            "all_played", "all_win", "all_draw", "all_lose",
                            "all_goals_for", "all_goals_against",
                            "home_played", "home_win", "home_draw", "home_lose",
                            "home_goals_for", "home_goals_against",
                            "away_played", "away_win", "away_draw", "away_lose",
                            "away_goals_for", "away_goals_against",
                            "source_extra",
                        ],
                    )
                    written += 1

    return {"standings": written, "groups": len(groups)}


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

ENTITIES = {
    "leagues": sync_leagues,
    "teams": sync_teams,
    "standings": sync_standings,
}

# Event-data workers live in their own modules (fixtures, later players/odds/...)
# and import shared helpers back from this one. To keep a single import direction
# (worker -> spine) and avoid an import cycle, they are resolved lazily here.
LAZY_ENTITIES = frozenset({"fixtures"})


def _entity_fn(name: str):
    """Return the worker fn for an --entity, importing lazily where needed."""
    if name == "fixtures":
        from .fixtures import ingest_fixtures

        return ingest_fixtures
    return ENTITIES[name]


def main() -> int:
    parser = argparse.ArgumentParser(description="Statesta static-spine sync worker")
    parser.add_argument(
        "--entity", required=True, choices=sorted(set(ENTITIES) | LAZY_ENTITIES)
    )
    parser.add_argument("--league", type=int, default=DEFAULT_LEAGUE)
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument("--show-sql", action="store_true", help="print every statement issued")
    args = parser.parse_args()

    config = load_config()
    resolver = ResolutionMap()

    with connect(config.database_url) as conn, ApiFootballClient(config.api_football_key) as api:
        try:
            result = _entity_fn(args.entity)(conn, api, resolver, args.league, args.season)
        except SyncError as exc:
            print(f"SYNC FAILED — {exc}")
            return 1

    print(f"OK  entity={args.entity} league={args.league} season={args.season}  ->  {result}")

    if args.show_sql:
        print(f"\n--- {len(ISSUED)} statement(s) issued ---")
        for stmt, params in ISSUED:
            print(f"\n{stmt}\n  params: {params}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
