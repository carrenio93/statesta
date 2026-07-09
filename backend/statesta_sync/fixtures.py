"""Fixtures event-data ingest — /fixtures -> curated.fixtures (D-072 step 7).

This is the first *event-data* worker (the spine — leagues/teams/standings — is
its prerequisite and runs in an earlier pass). It follows exactly the same
raw-first, normalize-from-the-landed-payload discipline as the spine (D-071),
and the same INSERT ... ON CONFLICT ... RETURNING id upsert (D-073).

Two things are new here versus the spine:

  * Pagination. /fixtures returns `paging.{current,total}`; we loop pages until
    current == total. A single league-season is usually one page, but /players
    and /odds will need the same loop, so it is wired now.
  * Cross-run FK resolution. The parents (league_season, teams, venues) were
    written in a *prior* run, so they are absent from the in-run resolution map.
    We resolve them ONCE up front via SELECT (the D-073 fallback), not per-row:
    league_season_id is a single value; teams/venues are preloaded into
    {source_ref -> id} dicts.

Venues follow "absent, not invented" (D-081, consistent with D-077): if a
fixture's venue id is null or not yet in curated.venues we set venue_id = NULL
and never create a venue here. The count of such fixtures is logged at the end.

Run (via the shared worker entrypoint):
    python -m statesta_sync.spine --entity fixtures --league 39 --season 2025
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Shared helpers live in spine.py; reuse them rather than duplicating (imported
# from spine, which in turn imports ingest_fixtures below its own definitions so
# the cycle resolves cleanly).
from .spine import SOURCE, SPORT, SyncError, _dig, _fetch, _land
from .upsert import ResolutionMap, upsert_returning_id


def _as_timestamp(value: Any) -> datetime | None:
    """Parse an API-Football ISO-8601 instant into a tz-aware datetime.

    fixture.date arrives like '2025-08-15T19:00:00+00:00'. curated.fixtures
    stores match_date as timestamptz (UTC), so we keep the offset and let
    psycopg bind it as a timestamptz. Absent -> None (but match_date is NOT
    NULL, so a dateless fixture will surface as a clear insert error).
    """
    return datetime.fromisoformat(value) if value else None


def _preload_team_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every football team, read once (D-073 fallback)."""
    cur.execute(
        "select source_ref, id from curated.teams where sport = %s and source = %s",
        (SPORT, SOURCE),
    )
    return {ref: tid for ref, tid in cur.fetchall()}


def _preload_venue_ids(cur) -> dict[str, int]:
    """{source_ref -> our id} for every venue, read once (venues have no sport)."""
    cur.execute(
        "select source_ref, id from curated.venues where source = %s",
        (SOURCE,),
    )
    return {ref: vid for ref, vid in cur.fetchall()}


# Columns refreshed on a re-sync. The natural key (sport, source, source_ref) is
# deliberately excluded — a re-run must never rewrite it (D-073). Everything else
# is source-owned and mutable (scores/status change as a match progresses).
_FIXTURE_UPDATE_COLUMNS = [
    "source_fetched_at",
    "league_season_id",
    "home_team_id",
    "away_team_id",
    "venue_id",
    "match_date",
    "referee",
    "round",
    "status_short",
    "status_long",
    "status_elapsed",
    "status_extra",
    "home_goals",
    "away_goals",
    "home_goals_ht",
    "away_goals_ht",
    "home_goals_ft",
    "away_goals_ft",
    "home_goals_et",
    "away_goals_et",
    "home_goals_pen",
    "away_goals_pen",
]


def ingest_fixtures(conn, api, resolver: ResolutionMap, league: int, season: int) -> dict:
    """Ingest every fixture for one league-season into curated.fixtures.

    Signature matches the spine's sync_* functions so it slots straight into the
    worker's --entity dispatch. Returns a summary dict.
    """
    endpoint = "/fixtures"

    # --- resolve the parents ONCE, up front (cross-run SELECT fallback) --------
    # These were written in a prior run, so they are not in the in-run map.
    with conn.transaction():
        with conn.cursor() as cur:
            our_league_id = resolver.resolve(cur, "leagues", league)
            if our_league_id is None:
                raise SyncError(
                    f"league source_ref={league} not in curated.leagues "
                    "— run --entity leagues first"
                )

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

            team_ids = _preload_team_ids(cur)
            venue_ids = _preload_venue_ids(cur)

    # --- paginate: land raw FIRST per page, then normalize from the landed payload
    page = 1
    total_pages = 1
    fixtures_written = 0
    unresolved_venues = 0

    while True:
        # page is optional; API-Football defaults to page 1 and /fixtures rejects
        # an explicit page field. Send it only for page >= 2 (paginated endpoints).
        params = {"league": league, "season": season}
        if page > 1:
            params["page"] = page
        fetched = _fetch(conn, api, endpoint, params)

        with conn.transaction():
            with conn.cursor() as cur:
                payload, fetched_at = _land(cur, fetched)

                paging = payload.get("paging") or {}
                total_pages = paging.get("total") or 1

                entries = payload.get("response") or []
                if page == 1 and not entries:
                    raise SyncError(f"{endpoint} {params}: empty response[]")

                for entry in entries:
                    fx = entry.get("fixture") or {}
                    lg = entry.get("league") or {}
                    teams_obj = entry.get("teams") or {}
                    goals = entry.get("goals") or {}
                    score = entry.get("score") or {}
                    status = fx.get("status") or {}

                    # home/away are NOT NULL — a missing parent is a hard error,
                    # exactly like the spine's standings resolution.
                    home_ref = _dig(teams_obj, "home", "id")
                    away_ref = _dig(teams_obj, "away", "id")
                    home_team_id = team_ids.get(str(home_ref))
                    away_team_id = team_ids.get(str(away_ref))
                    if home_team_id is None or away_team_id is None:
                        missing = home_ref if home_team_id is None else away_ref
                        raise SyncError(
                            f"team source_ref={missing} not in curated.teams "
                            "— run --entity teams first"
                        )

                    # venue: absent, not invented (D-081). Null id or unknown id
                    # -> venue_id NULL; never create a venue in the fixtures pass.
                    venue_ref = _dig(fx, "venue", "id")
                    venue_id = (
                        venue_ids.get(str(venue_ref)) if venue_ref is not None else None
                    )
                    if venue_id is None:
                        unresolved_venues += 1

                    upsert_returning_id(
                        cur,
                        "curated.fixtures",
                        values={
                            "source": SOURCE,
                            "source_ref": str(fx["id"]),
                            "source_fetched_at": fetched_at,
                            "sport": SPORT,
                            "league_season_id": league_season_id,
                            "home_team_id": home_team_id,
                            "away_team_id": away_team_id,
                            "venue_id": venue_id,
                            "match_date": _as_timestamp(fx.get("date")),
                            "referee": fx.get("referee"),
                            "round": lg.get("round"),
                            "status_short": status.get("short"),
                            "status_long": status.get("long"),
                            "status_elapsed": status.get("elapsed"),
                            "status_extra": status.get("extra"),
                            # scores — all nullable, absent stays NULL never 0 (D-067, §6.7)
                            "home_goals": _dig(goals, "home"),
                            "away_goals": _dig(goals, "away"),
                            "home_goals_ht": _dig(score, "halftime", "home"),
                            "away_goals_ht": _dig(score, "halftime", "away"),
                            "home_goals_ft": _dig(score, "fulltime", "home"),
                            "away_goals_ft": _dig(score, "fulltime", "away"),
                            "home_goals_et": _dig(score, "extratime", "home"),
                            "away_goals_et": _dig(score, "extratime", "away"),
                            "home_goals_pen": _dig(score, "penalty", "home"),
                            "away_goals_pen": _dig(score, "penalty", "away"),
                        },
                        conflict_columns=["sport", "source", "source_ref"],
                        update_columns=_FIXTURE_UPDATE_COLUMNS,
                    )
                    fixtures_written += 1

        current = paging.get("current") or page
        if current >= total_pages:
            break
        page += 1

    # D-081: report how much venue data was absent (never silently invented).
    print(
        f"NOTE  venue absent/unresolved for {unresolved_venues} of "
        f"{fixtures_written} fixture(s) -> venue_id NULL (D-081)"
    )

    return {
        "fixtures": fixtures_written,
        "pages": total_pages,
        "unresolved_venues": unresolved_venues,
    }
