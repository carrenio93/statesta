-- =====================================================================
--  Statesta  —  Migration 001
--  Curated Layer (Part A: Static / Reference entities)
--  Session 4A
-- =====================================================================
--  Produced by: architect chat (Session 4A)
--  Layer: Curated  (ARCHITECTURE.md §4 — normalized, application-shaped
--                   entities derived from the Raw layer)
--
--  Scope of THIS file (4A — the "spine"):
--      curated.tiers                 reference catalogue of the 8 + '?' tiers
--      curated.leagues               the competition entity (stable across seasons)
--      curated.league_seasons        one row per (league, season) + coverage flags
--      curated.league_tier_changes   audit trail of tier assignments (data is MVP)
--      curated.venues                stadium / venue reference (capture-every-field)
--      curated.teams                 the team entity
--      curated.standings             one row per (league_season, team)
--
--  Out of scope (4B — event data, separate migration 002):
--      fixtures, match_statistics, lineups, players, player_match_stats, odds
--
--  Conventions honored (logged as decisions in PROJECT_STATUS.md):
--    • Layer = its own Postgres schema  ............... ARCHITECTURE §4.1
--    • Surrogate primary keys (our own id) ............ D-041 multi-source
--    • Provenance block on every row .................. D-041 / §6.8
--    • sport identifier on sport-specific entities .... D-039 / §6.4
--    • Absent ≠ zero  (measures are nullable) ......... §6.7
--    • timestamptz (UTC) for every moment in time
--    • source_extra jsonb catch-all on high-variance rows .. §6.1
--    • No RLS on curated tables (service-role reads only)
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0.  Schema + shared helper
-- ---------------------------------------------------------------------

create schema if not exists curated;

comment on schema curated is
  'Curated Layer: normalized, application-shaped entities derived from the Raw layer. '
  'Platform-wide data, read via the service role. Never exposed to the anon key; no RLS.';

-- Keeps updated_at honest without application code having to remember.
create or replace function curated.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

comment on function curated.set_updated_at() is
  'BEFORE UPDATE trigger helper: stamps updated_at = now() on any row change.';


-- ---------------------------------------------------------------------
-- 1.  curated.tiers
--     The fixed catalogue of league/competition tiers (REQUIREMENTS §4.2.3).
--     This is the *set* of tiers (a product structure), modelled as a small
--     lookup table rather than a Postgres enum so that:
--       (a) leagues.tier_id can be a real foreign key (no typos possible), and
--       (b) tier metadata (label, ordering, default-on) can change without a
--           schema migration — in the spirit of D-037 (config, not code).
--     Per-sport so a future sport can define its own ladder (D-039).
--     NOTE: the per-tier *gating values* and auto-scoring *weights* are NOT
--     here — those belong to the Configuration Layer session.
-- ---------------------------------------------------------------------

create table curated.tiers (
    sport               text        not null default 'football',
    tier_id             text        not null,
    label               text        not null,
    sort_order          integer     not null,
    -- friendlies is OFF by default; the other 7 user-facing tiers are ON (§4.2.1).
    selected_by_default boolean     not null default true,
    -- '?' (unmapped) is not shown to users until an admin assigns a real tier (§4.2.3/§4.2.5).
    is_user_visible     boolean     not null default true,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),

    constraint pk_tiers primary key (sport, tier_id)
);

comment on table curated.tiers is
  'Catalogue of league tiers per sport (top, medium, ... friendlies, plus ? unmapped). '
  'Referenced by curated.leagues.tier_id. Gating values and auto-scoring weights live in the Configuration Layer, not here.';
comment on column curated.tiers.is_user_visible is
  'False for the ? (unmapped) tier so unmapped leagues are excluded from user-facing queries (§4.2.5).';

create trigger trg_tiers_updated_at
  before update on curated.tiers
  for each row execute function curated.set_updated_at();

-- Seed the football tier ladder (REQUIREMENTS §4.2.3).
insert into curated.tiers (sport, tier_id, label, sort_order, selected_by_default, is_user_visible) values
  ('football', 'top',            'Top',            1, true,  true),
  ('football', 'medium',         'Medium',         2, true,  true),
  ('football', 'low',            'Low',            3, true,  true),
  ('football', 'very_low',       'Very Low',       4, true,  true),
  ('football', 'women',          'Women',          5, true,  true),
  ('football', 'youth_reserves', 'Youth/Reserves', 6, true,  true),
  ('football', 'cup_domestic',   'Cup',            7, true,  true),
  ('football', 'friendlies',     'Friendlies',     8, false, true),   -- opt-in (§4.2.1)
  ('football', '?',              'Unmapped',       9, false, false);   -- hidden until reviewed


-- ---------------------------------------------------------------------
-- 2.  curated.venues
--     Stadium / venue reference. Not in the §6.3 required-entities list,
--     but captured under the "capture every field" principle (§6.1) — the
--     API-Football team payload carries a venue object we don't want to lose.
--     Sport-agnostic (a stadium is not sport-specific), so no sport column.
-- ---------------------------------------------------------------------

create table curated.venues (
    id               bigint generated always as identity primary key,

    -- provenance (D-041)
    source           text        not null default 'api_football',
    source_ref       text        not null,           -- API-Football venue id (as text)
    source_fetched_at timestamptz,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now(),

    name             text,
    address          text,
    city             text,
    country_name     text,
    capacity         integer,                         -- nullable: absent ≠ zero (§6.7)
    surface          text,                            -- e.g. 'grass', 'artificial turf'
    image_url        text,

    source_extra     jsonb,                           -- any venue fields not modelled above

    constraint uq_venues_source unique (source, source_ref)
);

comment on table curated.venues is
  'Stadium/venue reference, captured from the API-Football team/venue payload (§6.1). Sport-agnostic.';

create trigger trg_venues_updated_at
  before update on curated.venues
  for each row execute function curated.set_updated_at();


-- ---------------------------------------------------------------------
-- 3.  curated.leagues
--     The COMPETITION entity — one row per competition (e.g. "Premier
--     League", id 39). Stable across seasons. Season-specific facts live in
--     curated.league_seasons (§4 below). This league/season split is more
--     correct than v2.7's flattened single-season row.
--
--     Tier handling (the "mix", per your call):
--       • tier_id            = the league's CURRENT assigned tier (curated attribute,
--                              read by every form query — §4.2.5). Defaults to '?'.
--       • suggested_tier_id  = auto-scoring output; never overrides an admin set tier.
--       • tier_is_admin_set  = once true, auto-scoring leaves this league alone (§4.2.4).
--       • needs_review       = newly discovered / auto-migrated leagues await review (§4.2.8).
--       • is_active          = false when a league ceases to exist mid-season (§4.2.6).
-- ---------------------------------------------------------------------

create table curated.leagues (
    id                bigint generated always as identity primary key,

    -- provenance (D-041)
    source            text        not null default 'api_football',
    source_ref        text        not null,           -- API-Football league id (as text)
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    -- multi-sport (D-039)
    sport             text        not null default 'football',

    name              text        not null,
    type              text,                            -- 'league' | 'cup' (API-Football "type")
    country_name      text,
    country_code      text,                            -- ISO code; null for international comps
    logo_url          text,
    flag_url          text,

    -- tier assignment (curated attribute)
    tier_id           text        not null default '?',
    suggested_tier_id text,                            -- auto-score suggestion (nullable)
    tier_is_admin_set boolean     not null default false,
    needs_review      boolean     not null default true,
    is_active         boolean     not null default true,

    source_extra      jsonb,

    constraint uq_leagues_source unique (sport, source, source_ref),
    constraint fk_leagues_tier
        foreign key (sport, tier_id)
        references curated.tiers (sport, tier_id)
        on update cascade on delete restrict,
    constraint fk_leagues_suggested_tier
        foreign key (sport, suggested_tier_id)
        references curated.tiers (sport, tier_id)
        on update cascade on delete restrict
);

comment on table curated.leagues is
  'The competition entity (stable across seasons). Season-specific facts live in curated.league_seasons.';
comment on column curated.leagues.tier_id is
  'Current tier of this competition (FK to curated.tiers). Defaults to ? (unmapped). Governs which matches count as form (§4.2.5).';
comment on column curated.leagues.tier_is_admin_set is
  'Once true, the auto-scoring algorithm never overwrites this league''s tier (§4.2.4).';

create trigger trg_leagues_updated_at
  before update on curated.leagues
  for each row execute function curated.set_updated_at();

create index ix_leagues_sport_tier   on curated.leagues (sport, tier_id);
create index ix_leagues_country      on curated.leagues (country_name);
-- Partial index powering the admin "leagues awaiting review" queue (§4.2.2).
create index ix_leagues_needs_review on curated.leagues (needs_review) where needs_review;


-- ---------------------------------------------------------------------
-- 4.  curated.league_seasons
--     One row per (league, season). Holds the season window and the
--     API-Football per-season COVERAGE flags (what data exists for this
--     season). Coverage booleans are nullable: null = "we don't yet know",
--     honouring absent ≠ zero (§6.7).
--
--     DELIBERATE EXCLUSION: season completion % is NOT stored here. It is a
--     derived metric (played / total fixtures) and therefore belongs to the
--     Computed Layer session, not Curated. The completion-range filter (D-011)
--     will read it from there.
-- ---------------------------------------------------------------------

create table curated.league_seasons (
    id                      bigint generated always as identity primary key,

    -- provenance (D-041)
    source                  text        not null default 'api_football',
    source_ref              text,                      -- composite-keyed row; native id not always present
    source_fetched_at       timestamptz,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now(),

    league_id               bigint      not null,
    season                  integer     not null,      -- season "year", e.g. 2025
    start_date              date,
    end_date                date,
    is_current              boolean     not null default false,

    -- API-Football per-season coverage flags (nullable = unknown)
    cov_standings           boolean,
    cov_fixtures            boolean,
    cov_fixture_statistics  boolean,
    cov_lineups             boolean,
    cov_player_statistics   boolean,
    cov_odds                boolean,

    source_extra            jsonb,

    constraint uq_league_seasons unique (league_id, season),
    constraint fk_league_seasons_league
        foreign key (league_id) references curated.leagues (id)
        on delete cascade
);

comment on table curated.league_seasons is
  'Per-season facts for a competition: window + API-Football coverage flags. Completion % is excluded (it is Computed-layer, derived from fixtures).';
comment on column curated.league_seasons.is_current is
  'Mirrors API-Football "current" flag for the season. Used by the Season Resolver (D-045).';

create trigger trg_league_seasons_updated_at
  before update on curated.league_seasons
  for each row execute function curated.set_updated_at();

create index ix_league_seasons_league  on curated.league_seasons (league_id);
create index ix_league_seasons_current on curated.league_seasons (league_id) where is_current;


-- ---------------------------------------------------------------------
-- 5.  curated.league_tier_changes
--     Audit trail of tier assignments (REQUIREMENTS §4.2.5 / §4.2.9 — the
--     audit DATA is MVP; the admin UI for it is Phase 2). Records who, when,
--     from-tier, to-tier, and why.
--
--     changed_by is a uuid (Supabase auth user id) but has NO foreign key
--     yet — the User/admin tables are designed in a later session. The FK
--     will be added then. (Logged as D-058.)
-- ---------------------------------------------------------------------

create table curated.league_tier_changes (
    id            bigint generated always as identity primary key,
    league_id     bigint      not null,
    from_tier_id  text,                                -- null on first assignment
    to_tier_id    text        not null,
    -- 'admin'  = manual override | 'auto_migration' = v2.7→v3 launch mapping (§4.2.8)
    -- 'auto_score' = algorithm suggestion accepted on a fresh league
    change_source text        not null default 'admin',
    changed_by    uuid,                                -- soft ref to admin user; FK deferred
    note          text,
    changed_at    timestamptz not null default now(),

    constraint fk_ltc_league
        foreign key (league_id) references curated.leagues (id)
        on delete cascade
);

comment on table curated.league_tier_changes is
  'Append-only audit of league tier assignments (who/when/from/to/why). Data captured in MVP; admin UI is Phase 2.';

create index ix_ltc_league     on curated.league_tier_changes (league_id);
create index ix_ltc_changed_at on curated.league_tier_changes (changed_at);


-- ---------------------------------------------------------------------
-- 6.  curated.teams
--     The team entity. current_league_id is a soft, denormalized convenience
--     pointer to the team's primary current league (satisfies §6.3's literal
--     "current league"); the authoritative record of who-plays-where lives in
--     standings + fixtures. (See open question Q-NEW-AG.)
-- ---------------------------------------------------------------------

create table curated.teams (
    id                bigint generated always as identity primary key,

    -- provenance (D-041)
    source            text        not null default 'api_football',
    source_ref        text        not null,            -- API-Football team id (as text)
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    -- multi-sport (D-039)
    sport             text        not null default 'football',

    name              text        not null,
    code              text,                             -- 3-letter code, e.g. 'MUN'
    country_name      text,
    country_code      text,
    founded           integer,
    is_national       boolean     not null default false,  -- national team vs club
    logo_url          text,

    venue_id          bigint,                           -- home venue (nullable)
    current_league_id bigint,                           -- soft denormalized pointer (Q-NEW-AG)

    source_extra      jsonb,

    constraint uq_teams_source unique (sport, source, source_ref),
    constraint fk_teams_venue
        foreign key (venue_id) references curated.venues (id)
        on delete set null,
    constraint fk_teams_current_league
        foreign key (current_league_id) references curated.leagues (id)
        on delete set null
);

comment on table curated.teams is
  'The team entity (clubs and national teams). current_league_id is a denormalized convenience; authoritative participation is via standings/fixtures (Q-NEW-AG).';

create trigger trg_teams_updated_at
  before update on curated.teams
  for each row execute function curated.set_updated_at();

create index ix_teams_country        on curated.teams (country_name);
create index ix_teams_current_league on curated.teams (current_league_id);


-- ---------------------------------------------------------------------
-- 7.  curated.standings
--     One row per (league_season, team). Full fidelity: overall + home +
--     away splits captured (§6.1). All measures nullable (absent ≠ zero, §6.7).
--     Identity is the (league_season_id, team_id) composite, so source_ref is
--     nullable here (this is a derived/relationship row, not a vendor entity).
-- ---------------------------------------------------------------------

create table curated.standings (
    id                bigint generated always as identity primary key,

    -- provenance (D-041)
    source            text        not null default 'api_football',
    source_ref        text,
    source_fetched_at timestamptz,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),

    league_season_id  bigint      not null,
    team_id           bigint      not null,

    group_label       text,                             -- e.g. 'Group A'; null for single-table comps
    rank              integer,
    points            integer,
    goals_diff        integer,
    form              text,                             -- recent form string, e.g. 'WWDLW'
    status            text,                             -- 'same' | 'up' | 'down'
    description       text,                             -- e.g. 'Promotion - Champions League'

    -- overall split
    all_played        integer,
    all_win           integer,
    all_draw          integer,
    all_lose          integer,
    all_goals_for     integer,
    all_goals_against integer,

    -- home split
    home_played       integer,
    home_win          integer,
    home_draw         integer,
    home_lose         integer,
    home_goals_for    integer,
    home_goals_against integer,

    -- away split
    away_played       integer,
    away_win          integer,
    away_draw         integer,
    away_lose         integer,
    away_goals_for    integer,
    away_goals_against integer,

    source_extra      jsonb,

    constraint uq_standings unique (league_season_id, team_id),
    constraint fk_standings_league_season
        foreign key (league_season_id) references curated.league_seasons (id)
        on delete cascade,
    constraint fk_standings_team
        foreign key (team_id) references curated.teams (id)
        on delete cascade
);

comment on table curated.standings is
  'League table rows, one per (league_season, team), with overall/home/away splits. All measures nullable (§6.7).';

create trigger trg_standings_updated_at
  before update on curated.standings
  for each row execute function curated.set_updated_at();

create index ix_standings_team on curated.standings (team_id);

-- =====================================================================
--  End of Migration 001 (Curated Layer — Part A: Static / Reference)
--  Next: 002_curated_events.sql (fixtures, match_statistics, lineups,
--        players, player_match_stats, odds) — Session 4B.
-- =====================================================================
