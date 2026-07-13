-- Session 13 — fix curated.standings for split-season / grouped competitions.
-- Root cause: uq_standings (league_season_id, team_id) allowed only one standings row
-- per team per season. Split seasons and every group-stage competition legitimately give
-- a team a row in more than one group, so the second silently overwrote the first
-- (Greek Super League 2025: 28 rows collapsed to 14). group_label now enters the key;
-- NULLS NOT DISTINCT keeps the one-row-per-team guarantee if a future payload omits a
-- group name (PG15+; server is PG17).

ALTER TABLE curated.standings
    DROP CONSTRAINT uq_standings;

ALTER TABLE curated.standings
    ADD CONSTRAINT uq_standings
        UNIQUE NULLS NOT DISTINCT (league_season_id, team_id, group_label);
