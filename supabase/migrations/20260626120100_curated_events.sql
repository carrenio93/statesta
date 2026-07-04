-- =====================================================================
--  Statesta  —  Migration 002
--  Curated Layer (Part B: Event data)
--  Session 4B
-- =====================================================================
--  Depends on: 001_curated_static.sql (the `curated` schema, the
--              curated.set_updated_at() trigger helper, and the static
--              tables this file references via foreign keys:
--              league_seasons, teams, venues).
--
--  Scope of THIS file (4B — event data):
--      curated.fixtures            one row per match
--      curated.players             the person (team-agnostic)
--      curated.match_statistics    one row per (fixture, team)
--      curated.lineups             one row per (fixture, team, player)
--      curated.player_match_stats  one row per (fixture, player)
--      curated.odds_bookmakers     reference list of bookmakers
--      curated.odds_markets        reference list of betting markets
--      curated.odds                append-only price CHANGE LOG (point-in-time)
--
--  Conventions inherited from 4A (D-049 → D-058):
--    • surrogate id PKs; vendor IDs in source + source_ref
--    • provenance block on every row; sport on sport-specific entities
--    • absent ≠ zero  (every measure nullable, no numeric default)  ... §6.7
--    • timestamptz (UTC); source_extra jsonb on high-variance rows  ... §6.1
--    • source_ref nullable on derived/relationship rows; composite key governs
--    • no RLS on curated tables (service-role reads only)
--
--  New decisions logged this session (see CURATED_SCHEMA_REFERENCE.md):
--    D-060 odds = append-only change log (full history; "at T" = latest ≤ T)
--    D-061 odds.phase (pre_match | in_play); closing = latest pre_match ≤ kickoff
--    D-062 RESOLVED closing odds live in the Computed layer, not here
--    D-063 odds modelled as 3 tables (bookmakers + markets reference, odds fact)
--    D-064 players team-agnostic; per-match team comes from lineups / stats
--    D-065 lineups one table; formation + coach denormalised onto each row
--    D-066 match_statistics & player_match_stats capture the full AF field set
--    D-067 fixtures store the full score breakdown (HT/FT/ET/PEN), all nullable
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1.  curated.fixtures
--     The match. References the 4A spine: which competition-season, which
--     two teams, which venue. Score is captured at every breakdown the
--     source provides (D-067) — all nullable, because a not-yet-played or
--     unreported score must read as "unknown", never 0 (§6.7).
-- ---------------------------------------------------------------------

create table curated.fixtures (
    id                bigint generated always as identity primary key,

    -- provenance (D-041)
    source            text        not null default 'api_football',
    source_ref        text        not null,            -- API-Football fixture id (as text)
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    sport             text        not null default 'football',

    league_season_id  bigint      not null,            -- which competition + season
    round             text,                            -- e.g. 'Regular Season - 5'

    home_team_id      bigint      not null,
    away_team_id      bigint      not null,
    venue_id          bigint,

    referee           text,
    match_date        timestamptz not null,            -- kickoff (UTC)

    -- status (API-Football)
    status_short      text,                            -- NS, 1H, HT, 2H, FT, AET, PEN, PST, CANC, ...
    status_long       text,
    status_elapsed    integer,                         -- minutes played so far
    status_extra      integer,                         -- stoppage / extra info

    -- score breakdown (all nullable — absent ≠ zero)
    home_goals        integer,                         -- headline score
    away_goals        integer,
    home_goals_ht     integer,                         -- half-time
    away_goals_ht     integer,
    home_goals_ft     integer,                         -- 90-minute full-time
    away_goals_ft     integer,
    home_goals_et     integer,                         -- after extra time
    away_goals_et     integer,
    home_goals_pen    integer,                         -- penalty shootout
    away_goals_pen    integer,

    source_extra      jsonb,

    constraint uq_fixtures_source unique (sport, source, source_ref),
    constraint fk_fixtures_league_season
        foreign key (league_season_id) references curated.league_seasons (id)
        on delete cascade,
    constraint fk_fixtures_home_team
        foreign key (home_team_id) references curated.teams (id)
        on delete restrict,
    constraint fk_fixtures_away_team
        foreign key (away_team_id) references curated.teams (id)
        on delete restrict,
    constraint fk_fixtures_venue
        foreign key (venue_id) references curated.venues (id)
        on delete set null
);

comment on table curated.fixtures is
  'One row per match. References the 4A spine (league_season, two teams, venue). Full score breakdown captured, all nullable (§6.7).';

create trigger trg_fixtures_updated_at
  before update on curated.fixtures
  for each row execute function curated.set_updated_at();

-- Read patterns: a team''s last N matches before a date (filter engine),
-- league browsing by date, and upcoming-match lists.
create index ix_fixtures_date          on curated.fixtures (match_date);
create index ix_fixtures_home_date     on curated.fixtures (home_team_id, match_date);
create index ix_fixtures_away_date     on curated.fixtures (away_team_id, match_date);
create index ix_fixtures_league_date   on curated.fixtures (league_season_id, match_date);
create index ix_fixtures_upcoming      on curated.fixtures (match_date) where status_short = 'NS';


-- ---------------------------------------------------------------------
-- 2.  curated.players
--     The person — deliberately TEAM-AGNOSTIC (D-064). A player is not
--     "owned" by a team; which team they turned out for is recorded per
--     match in lineups and player_match_stats. This fixes the v2.7 bug
--     where transferred players displayed the wrong team.
-- ---------------------------------------------------------------------

create table curated.players (
    id                bigint generated always as identity primary key,

    -- provenance (D-041)
    source            text        not null default 'api_football',
    source_ref        text        not null,            -- API-Football player id (as text)
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    sport             text        not null default 'football',

    name              text        not null,
    firstname         text,
    lastname          text,
    birth_date        date,
    birth_country     text,
    birth_place       text,
    nationality       text,
    height            text,                            -- API ships strings, e.g. '180 cm'
    weight            text,                            -- e.g. '75 kg'
    photo_url         text,

    source_extra      jsonb,

    constraint uq_players_source unique (sport, source, source_ref)
);

comment on table curated.players is
  'The player as a person (team-agnostic). Per-match team is recorded in lineups / player_match_stats (D-064), fixing the v2.7 transferred-player bug.';

create trigger trg_players_updated_at
  before update on curated.players
  for each row execute function curated.set_updated_at();


-- ---------------------------------------------------------------------
-- 3.  curated.match_statistics
--     One row per (fixture, team). Full API-Football fixture-statistics
--     set (D-066) — including xG and goals-prevented. Identity is the
--     (fixture, team) pair, so source_ref is nullable (D-057). All
--     measures nullable (§6.7).
-- ---------------------------------------------------------------------

create table curated.match_statistics (
    id                bigint generated always as identity primary key,

    source            text        not null default 'api_football',
    source_ref        text,
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    sport             text        not null default 'football',

    fixture_id        bigint      not null,
    team_id           bigint      not null,

    shots_on_goal     integer,
    shots_off_goal    integer,
    shots_total       integer,
    shots_blocked     integer,
    shots_inside_box  integer,
    shots_outside_box integer,
    fouls             integer,
    corners           integer,
    offsides          integer,
    possession_pct    numeric(5,2),
    yellow_cards      integer,
    red_cards         integer,
    gk_saves          integer,
    passes_total      integer,
    passes_accurate   integer,
    passes_pct        numeric(5,2),
    expected_goals    numeric(6,3),                    -- xG
    goals_prevented   numeric(6,3),

    source_extra      jsonb,                           -- any stat "type" not modelled above

    constraint uq_match_statistics unique (fixture_id, team_id),
    constraint fk_match_stats_fixture
        foreign key (fixture_id) references curated.fixtures (id) on delete cascade,
    constraint fk_match_stats_team
        foreign key (team_id) references curated.teams (id) on delete restrict
);

comment on table curated.match_statistics is
  'Per-team match statistics, one row per (fixture, team). Full API-Football field set incl. xG/goals_prevented (§6.1). All measures nullable.';

create trigger trg_match_statistics_updated_at
  before update on curated.match_statistics
  for each row execute function curated.set_updated_at();

create index ix_match_stats_team on curated.match_statistics (team_id);


-- ---------------------------------------------------------------------
-- 4.  curated.lineups
--     One row per (fixture, team, player). Single table (D-065): the
--     team-level formation and coach are denormalised onto every player
--     row, matching the v2.7 mental model and keeping reads simple.
-- ---------------------------------------------------------------------

create table curated.lineups (
    id                bigint generated always as identity primary key,

    source            text        not null default 'api_football',
    source_ref        text,
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    sport             text        not null default 'football',

    fixture_id        bigint      not null,
    team_id           bigint      not null,
    player_id         bigint      not null,

    formation         text,                            -- team-level, e.g. '4-3-3'
    coach_name        text,                            -- denormalised; no coaches table yet (Q-NEW-AH)
    coach_source_ref  text,                            -- API-Football coach id (soft ref)

    player_name       text,                            -- denormalised for fast display
    jersey_number     integer,
    position          text,                            -- F / M / D / G
    grid              text,                            -- pitch coordinate, e.g. '1:4'
    is_starting       boolean     not null,            -- true = starting XI, false = substitute

    source_extra      jsonb,

    constraint uq_lineups unique (fixture_id, team_id, player_id),
    constraint fk_lineups_fixture
        foreign key (fixture_id) references curated.fixtures (id) on delete cascade,
    constraint fk_lineups_team
        foreign key (team_id) references curated.teams (id) on delete restrict,
    constraint fk_lineups_player
        foreign key (player_id) references curated.players (id) on delete restrict
);

comment on table curated.lineups is
  'Lineup entries, one row per (fixture, team, player). Formation/coach denormalised onto each row (D-065). is_starting separates XI from subs.';

create trigger trg_lineups_updated_at
  before update on curated.lineups
  for each row execute function curated.set_updated_at();

create index ix_lineups_player          on curated.lineups (player_id);
create index ix_lineups_fixture_starting on curated.lineups (fixture_id, is_starting);


-- ---------------------------------------------------------------------
-- 5.  curated.player_match_stats
--     One row per (fixture, player). The backbone of the (Phase 2) Player
--     Props engine; data collected from launch (D-022). team_id records
--     who the player turned out for IN THIS MATCH (D-064). Full AF player
--     stat set (D-066); all measures nullable (§6.7).
-- ---------------------------------------------------------------------

create table curated.player_match_stats (
    id                  bigint generated always as identity primary key,

    source              text        not null default 'api_football',
    source_ref          text,
    source_fetched_at   timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),

    sport               text        not null default 'football',

    fixture_id          bigint      not null,
    player_id           bigint      not null,
    team_id             bigint      not null,          -- team in THIS fixture (transfer-safe)

    -- games block
    minutes_played      integer,                       -- drives the ≥45 min threshold filter
    jersey_number       integer,
    position_played     text,                          -- F / M / D / G (actual, not registered)
    rating              numeric(4,2),
    is_captain          boolean,
    is_substitute       boolean,

    offsides            integer,
    shots_total         integer,
    shots_on            integer,
    goals_total         integer,
    goals_conceded      integer,
    assists             integer,
    goals_saves         integer,
    passes_total        integer,
    passes_key          integer,
    passes_accuracy     integer,                        -- AF ships this as a number; see reference doc note
    tackles_total       integer,
    tackles_blocks      integer,
    tackles_interceptions integer,
    duels_total         integer,
    duels_won           integer,
    dribbles_attempts   integer,
    dribbles_success    integer,
    dribbles_past       integer,
    fouls_drawn         integer,
    fouls_committed     integer,
    cards_yellow        integer,
    cards_red           integer,
    penalty_won         integer,
    penalty_committed   integer,
    penalty_scored      integer,
    penalty_missed      integer,
    penalty_saved       integer,

    source_extra        jsonb,

    constraint uq_player_match_stats unique (fixture_id, player_id),
    constraint fk_pms_fixture
        foreign key (fixture_id) references curated.fixtures (id) on delete cascade,
    constraint fk_pms_player
        foreign key (player_id) references curated.players (id) on delete restrict,
    constraint fk_pms_team
        foreign key (team_id) references curated.teams (id) on delete restrict
);

comment on table curated.player_match_stats is
  'Per-player per-fixture statistics. MVP for data collection (D-022); Player Props UI is Phase 2. team_id is the per-match team (D-064). Full AF field set, all nullable.';

create trigger trg_player_match_stats_updated_at
  before update on curated.player_match_stats
  for each row execute function curated.set_updated_at();

create index ix_pms_player on curated.player_match_stats (player_id);
create index ix_pms_team   on curated.player_match_stats (team_id);


-- ---------------------------------------------------------------------
-- 6.  curated.odds_bookmakers   (reference)
--     Small list of bookmakers (Bet365 today; ready for more). Keeps the
--     bookmaker name out of the millions of rows in curated.odds.
-- ---------------------------------------------------------------------

create table curated.odds_bookmakers (
    id                bigint generated always as identity primary key,
    source            text        not null default 'api_football',
    source_ref        text        not null,            -- API-Football bookmaker id
    name              text        not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint uq_odds_bookmakers unique (source, source_ref)
);

comment on table curated.odds_bookmakers is
  'Reference list of bookmakers. Referenced by curated.odds. Populated by the odds sync.';

create trigger trg_odds_bookmakers_updated_at
  before update on curated.odds_bookmakers
  for each row execute function curated.set_updated_at();


-- ---------------------------------------------------------------------
-- 7.  curated.odds_markets   (reference)
--     Reference list of betting markets ("Match Winner", "Goals
--     Over/Under", "Both Teams Score", ...). Labels markets once instead
--     of repeating free text on every odds row.
-- ---------------------------------------------------------------------

create table curated.odds_markets (
    id                bigint generated always as identity primary key,
    source            text        not null default 'api_football',
    source_ref        text        not null,            -- API-Football bet/market id
    name              text        not null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    constraint uq_odds_markets unique (source, source_ref)
);

comment on table curated.odds_markets is
  'Reference list of betting markets. Referenced by curated.odds. Populated by the odds sync.';

create trigger trg_odds_markets_updated_at
  before update on curated.odds_markets
  for each row execute function curated.set_updated_at();


-- ---------------------------------------------------------------------
-- 8.  curated.odds   (fact — APPEND-ONLY change log)
--     One row = one OBSERVED price for one selection at one moment
--     (D-060). The sync inserts a new row only when a price moves, so the
--     table IS the full history of every change. Rows are never updated
--     (hence no updated_at / trigger).
--
--     "Odds at time T"  = latest row for (fixture, bookmaker, market,
--                          selection, line) with captured_at <= T.
--     "Closing odds"    = latest row with phase = 'pre_match' and
--                          captured_at <= kickoff (D-061). The RESOLVED
--                          closing price is computed and stored in the
--                          Computed layer, not here (D-062).
-- ---------------------------------------------------------------------

create table curated.odds (
    id                bigint generated always as identity primary key,

    source            text        not null default 'api_football',
    source_ref        text,
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),

    sport             text        not null default 'football',

    fixture_id        bigint      not null,
    bookmaker_id      bigint      not null,
    market_id         bigint      not null,

    selection         text        not null,            -- e.g. 'Home', 'Over', 'Yes'
    line              numeric(6,2),                     -- e.g. 2.5; NULL for line-less markets (Match Winner)
    odd               numeric(8,3) not null,            -- decimal odd

    phase             text        not null default 'pre_match',  -- 'pre_match' | 'in_play'
    captured_at       timestamptz not null,             -- when WE observed this price
    source_updated_at timestamptz,                      -- the source's own "last update" for the odd

    source_extra      jsonb,

    -- One observation per selection per moment. NULLS NOT DISTINCT (PG15+)
    -- so two NULL-line rows at the same instant are treated as duplicates.
    constraint uq_odds unique nulls not distinct
        (fixture_id, bookmaker_id, market_id, selection, line, captured_at),
    constraint fk_odds_fixture
        foreign key (fixture_id) references curated.fixtures (id) on delete cascade,
    constraint fk_odds_bookmaker
        foreign key (bookmaker_id) references curated.odds_bookmakers (id) on delete restrict,
    constraint fk_odds_market
        foreign key (market_id) references curated.odds_markets (id) on delete restrict,
    constraint ck_odds_phase check (phase in ('pre_match', 'in_play'))
);

comment on table curated.odds is
  'Append-only price change log. One row = one observed price (fixture, bookmaker, market, selection, line, captured_at, phase). Full history; resolved closing odds are Computed-layer (D-062).';
comment on column curated.odds.phase is
  'pre_match or in_play. Closing odds must be the latest pre_match price at or before kickoff (D-061).';

-- Point-in-time lookup: equality on the selection identity, then newest-first
-- by captured_at. Powers "odds at T" and "closing" reads.
create index ix_odds_pit on curated.odds
    (fixture_id, bookmaker_id, market_id, selection, line, phase, captured_at desc);
-- "All odds for a fixture" (Event Page / odds display).
create index ix_odds_fixture on curated.odds (fixture_id);

-- =====================================================================
--  End of Migration 002 (Curated Layer — Part B: Event data)
--  The Curated Layer is now complete. Next layers (own sessions):
--    Raw, Computed (incl. resolved closing_odds + form snapshots),
--    User, and the Configuration subsystem.
-- =====================================================================
