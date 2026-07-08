# Statesta — Sync Workers: Ingestion Design

**Session:** 6
**Status:** Design only. This document defines *how* ingestion works and specifies the first runnable slice. It contains **no worker code**. The only executable SQL here is one small table definition you approved for today.
**Companions to read alongside:** `ARCHITECTURE.md` (§4 data layers, §5.3 sync-worker, §6.6 idempotency), `CURATED_SCHEMA_REFERENCE.md` (the 15 curated tables + FK order).

---

## Part 0 — What this session is (and isn't)

**Is:** the *plan* for pulling data out of API-Football and landing it in the database — the shape of the raw landing zone, the order things must be fetched in, how we translate the vendor's IDs into ours, which endpoint fills which table, and one tiny end-to-end slice you can actually run and eyeball.

**Isn't:** the worker code, the odds pipeline, the full Raw layer (archival, per-entity raw tables, incremental diffing), or anything about fixtures/stats/lineups/players beyond mapping them. Those are later sessions.

One deliverable, per Rule 2: **this document**.

---

## Part 1 — Raw-first vs straight-to-curated

### The short version
This was framed as an open question, but the pasted files have effectively already answered the *whether*: **raw-first is a locked architectural commitment.** ARCHITECTURE.md §4 shows the flow `API-Football → Raw → normalize → Curated`; §5.3 lists the sync-worker's two jobs as "writing raw API responses to the Raw Layer" *and* "normalizing raw responses into Curated"; and D-040 keeps Raw indefinitely. So the real decision for today was only *how much* raw structure to build now — which you settled: a minimal landing table.

### Why raw-first, in plain terms
Two ways to ingest:

| Approach | What happens | Cost | What you lose |
|---|---|---|---|
| **Straight-to-curated** | Fetch from API, transform in memory, write only to `curated.*`. The raw JSON is discarded once the request returns. | One write per row. Simplest. | Replayability, audit, methodology re-runs, and debugging. If a normalize bug corrupts a stat, the original truth is **gone** — you must re-hit the API (costing budget, and the vendor may have changed the data). |
| **Raw-first** (chosen) | Fetch → store the verbatim payload in `raw.*` → normalize *from the stored payload* into `curated.*`. | One extra write (the raw landing row). | Nothing. You keep the source-of-truth. |

The decisive reasons (all already committed):

- **Replayability (D-040).** If we improve a normalizer or add a curated column later, we re-run normalization over stored raw payloads — no new API calls, no budget spent, no risk the vendor's numbers moved.
- **Audit / provenance (D-041).** We can prove exactly what API-Football said, and when, for any row.
- **Debugging.** When a curated value looks wrong, the raw payload right next to it tells you whether the bug is in the source or in our transform.

The only price is one cheap extra insert. Accepted.

### One important refinement: normalize *from the landed payload*, not from the live response
When a worker runs, it should:

1. call the API,
2. **write the raw row first**,
3. then read that raw row back (or hand the just-landed payload forward) and normalize into curated.

This makes normalization **replayable by construction** — the exact same code path runs whether we're processing a fresh call or re-processing an old raw row months later. If we normalized straight off the live HTTP response and only saved raw as a side-effect, the "replay" path and the "live" path would be two different code paths that can drift.

### The minimal Raw landing table (approved for today)

Design goals: append-only, verbatim, provenance-tagged, cheap to write, easy to look up. One row per **API call** (not per entity) — the whole payload lands intact, matching "unmodified API responses."

```sql
-- Statesta — minimal Raw landing zone
-- Session 6 design. Becomes a timestamped Supabase migration next session (D-070 naming).
-- NOT applied to the database in this design session.

create schema if not exists raw;

create table raw.api_responses (
    id                bigint generated always as identity primary key,
    source            text        not null default 'api_football',
    endpoint          text        not null,                        -- e.g. '/leagues'
    request_params    jsonb       not null default '{}'::jsonb,    -- e.g. {"league":39,"season":2025,"page":1}
    http_status       integer,                                     -- 200, 429, ...
    response_body     jsonb       not null,                        -- the verbatim payload
    response_hash     text,                                        -- sha256 of response_body, for later diffing/dedupe
    source_fetched_at timestamptz not null default now(),          -- when we called the API
    created_at        timestamptz not null default now()
);

-- The normalizer and admin tooling look up "latest payload for this endpoint+params"
create index ix_raw_api_responses_endpoint_fetched
    on raw.api_responses (endpoint, source_fetched_at desc);

-- Find all calls that touched a given league/season/fixture
create index ix_raw_api_responses_params
    on raw.api_responses using gin (request_params);
```

Column rationale (why each exists):

- `source` / `endpoint` / `request_params` — provenance + enough to reproduce the exact call. `request_params` is `jsonb` so we can query "every call about league 39."
- `http_status` — lets us keep a record of failures (e.g. a `429` rate-limit) without them polluting curated data.
- `response_body jsonb` — the whole point: the untouched truth.
- `response_hash` — a fingerprint of the body. Later, incremental sync can skip re-normalizing a payload identical to the last one (ARCHITECTURE §4 notes Raw is read "for incremental sync diffing"). Optional to *use* now, cheap to *store* now, and adding it later would be a migration — so it goes in from the start (same reasoning as `phase` on odds, D-061).
- No `sport` column — Raw is a landing zone; `sport` is assigned during normalization. No RLS — `raw` is a backend-only schema, never exposed to the browser (§1.7 reasoning).

**Deliberately deferred to the full Raw-layer session:** per-entity raw tables, 12-month cold archival (D-040), retention config, and the diffing algorithm. This one table is the minimum that makes the slice runnable and honours raw-first.

---

## Part 2 — Sync order & dependency chain

### The rule that dictates order
A foreign key means a child row **cannot be written until its parent exists** — because the child stores the parent's *surrogate `id`*, and that id only exists after the parent is inserted. So the sync order is simply a **topological sort of the foreign-key graph**: parents before children, always.

### The order (static spine → event data)

```
  1. tiers                ✅ already seeded (Session 5) — nothing to fetch
  2. venues               ← arrive embedded in the /teams payload
  3. leagues              ← /leagues
  4. league_seasons       ← /leagues (same payload, seasons[] array)   depends on: leagues
  5. teams                ← /teams                                     depends on: venues, leagues
  6. standings            ← /standings                                 depends on: league_seasons, teams
  ── event data (high volume; per-fixture loops) ──
  7. fixtures             ← /fixtures                                  depends on: league_seasons, teams, venues
  8. players              ← /players (person profile)                  no FK out (team-agnostic, D-064)
  9. match_statistics     ← /fixtures/statistics                       depends on: fixtures, teams
 10. lineups              ← /fixtures/lineups                          depends on: fixtures, teams, players
 11. player_match_stats   ← /fixtures/players                          depends on: fixtures, players, teams
  ── reference + fact ──
 12. odds_bookmakers      ← /odds/bookmakers    (reference list)
 13. odds_markets         ← /odds/bets          (reference list)
 14. odds                 ← /odds               depends on: fixtures, odds_bookmakers, odds_markets
```

Two things worth internalising:

- **Cardinality changes at the line.** Steps 3–6 run **once per league-season** (a handful of calls). Steps 7–14 run **per fixture** (thousands of calls, and the bulk of the API budget). This is why the spine syncs nightly-cheap and the event data needs careful scheduling (the cron cadences in ARCHITECTURE §4.4).
- **`players` has no FK out** (D-064). A player is a person, not a team member, so it can be written any time after fixtures. Its *link* to a team lives on `lineups` / `player_match_stats`, which is why those come after both `players` and `fixtures`.

---

## Part 3 — Upsert & `source_ref → id` resolution (implements D-049)

This is the mechanical heart of every worker, so here it is slowly.

### The problem
API-Football calls the Premier League `39`. We refuse to use `39` as our primary key (D-049) — we mint our own `id` (say `1`) and store `39` as `source_ref`. So every time we write a row, we face two questions:

1. **Is this thing already in our table?** (don't create duplicates on re-runs)
2. **What is our `id` for it?** (so children can point at it)

### The pattern: `INSERT … ON CONFLICT (natural key) DO UPDATE … RETURNING id`

For a real entity like a team:

```
INSERT INTO curated.teams (sport, source, source_ref, name, ...)
VALUES ('football', 'api_football', '33', 'Manchester United', ...)
ON CONFLICT (sport, source, source_ref)
DO UPDATE SET name = EXCLUDED.name, source_fetched_at = now(), ...
RETURNING id;
```

In plain terms:

- **Try to insert.** If this `(sport, source, source_ref)` is new → a fresh row is created with a new `id`.
- **If it already exists** (the "conflict") → instead of erroring, *update* the existing row (refresh the name, bump `source_fetched_at`) and keep its existing `id`.
- **`RETURNING id`** hands us our surrogate id either way.

This single statement gives us **idempotency** (ARCHITECTURE §6.6): run the worker once or ten times, you end up with exactly one Man United row. Nothing duplicates, nothing crashes.

### The natural key differs by table type

| Table type | Examples | Conflict target (the "natural key") | Why |
|---|---|---|---|
| **Real entity (has vendor ID + sport)** | leagues, teams, fixtures, players | `(sport, source, source_ref)` | The vendor's own ID uniquely identifies it. |
| **Real entity (sport-agnostic)** | venues | `(source, source_ref)` | No `sport` column (§2.2). |
| **Reference list** | odds_bookmakers, odds_markets | `(source, source_ref)` | Small vendor-keyed lookups. |
| **Derived / relationship** | league_seasons, standings, match_statistics, lineups, player_match_stats | a **composite** of foreign keys, e.g. `(league_season_id, team_id)` for standings | No single vendor ID; identity *is* the combination (D-057). `source_ref` is nullable here. |
| **Append-only fact** | **odds** | *(none — no upsert)* | D-060: never updated. Insert a **new** row only when a price moves. This is the one exception to the pattern above. Cadence parked on Q-NEW-AI. |

### Wiring foreign keys within a run: the resolution map
When we normalize `/standings`, each row names a team by the vendor's id (`33`), but `curated.standings.team_id` needs *our* id (`1029`). Two ways to resolve:

- **In-run map (recommended default).** As we upsert teams, we build a dictionary `{ '33' → 1029, '50' → 1030, ... }` from the `RETURNING id` values. When we then write standings, we look up `team_id` in that dictionary — no extra database round-trips.
- **SQL-side lookup (fallback).** If the parent was written in an earlier run and isn't in memory, resolve with a `SELECT id FROM curated.teams WHERE source='api_football' AND source_ref='33'`. Same natural key, just read instead of write.

The map is the fast path; the SELECT is the safety net for cross-run references. Both implement the "cheap `source_ref → id` lookup" that D-049 explicitly accepts as the price of surrogate keys.

### One nuance you flagged earlier: `teams.current_league_id` (Q-NEW-AG)
`current_league_id` is a *soft convenience pointer*, not authoritative. During the `/teams?league=39` sync, the worker sets it to the league being synced. If a team plays in several competitions, whichever sync last touched it wins — that's acceptable because the authoritative "who plays where" comes from fixtures/standings, not this pointer. No special handling needed for the slice.

---

## Part 4 — Endpoint → curated table mapping

| API-Football endpoint | Key params | Populates (curated) | Notes |
|---|---|---|---|
| `GET /leagues` | `id`, `season` | `leagues`, `league_seasons` | One payload yields both: the `league`/`country` object → `leagues`; the `seasons[]` array (with `coverage` flags) → `league_seasons`. New leagues land with `tier_id = '?'`, `needs_review = true`. |
| `GET /teams` | `league`, `season` | `teams`, **`venues`** | The `venue` object is embedded per team → upsert `venues` first, then `teams` with the resolved `venue_id` (D-054). |
| `GET /standings` | `league`, `season` | `standings` | Rows reference teams by vendor id → resolve to `team_id`. Captures overall/home/away splits, `form`, `rank`, `points`, `description`, `group_label`. |
| `GET /fixtures` | `league`, `season` | `fixtures` | Full score breakdown → `*_ht`, `*_ft`, `*_et`, `*_pen` (D-067), all nullable. |
| `GET /fixtures/statistics` | `fixture` | `match_statistics` | Per-team stat block; full fidelity incl. xG, goals-prevented (D-066). Anything unmodelled → `source_extra`. |
| `GET /fixtures/lineups` | `fixture` | `lineups` | `formation` + `coach` denormalised onto each player row (D-065); coach stored as soft `coach_name`/`coach_source_ref` (Q-NEW-AH). |
| `GET /fixtures/players` | `fixture` | `player_match_stats` (and can seed `players`) | Per-match performance + player identity in one payload. |
| `GET /players` | `league`, `season`, `page` | `players` (profile) | Richer person profile (birth, nationality, height/weight, photo). Paginated. Best source for the person entity; `/fixtures/players` is the per-match source. |
| `GET /odds/bookmakers` | — | `odds_bookmakers` | Reference list. |
| `GET /odds/bets` | — | `odds_markets` | Reference list. |
| `GET /odds` | `fixture` / `league`+`season`, `page` | `odds` | Append-only, insert-on-change (D-060). Cadence = Q-NEW-AI. Paginated. |

**Coverage-flag mapping** (from `/leagues` `seasons[].coverage` → `league_seasons.cov_*`):
`standings → cov_standings`, `fixtures → cov_fixtures`, `fixtures.statistics_fixtures → cov_fixture_statistics`, `fixtures.lineups → cov_lineups`, `fixtures.statistics_players → cov_player_statistics`, `odds → cov_odds`. Absent flags stay `NULL` ("don't yet know"), not `false` (§6.7).

**Operational notes (design-level, not built today):** several endpoints paginate (`/players`, `/odds`) — the worker loops pages until `paging.current = paging.total`. Every call is budget-metered against the API-Football plan (tracked in Redis per ARCHITECTURE §824). Exact per-minute limits are operational config (Q-NEW-X), not needed for this design.

---

## Part 5 — The first vertical slice (runnable & verifiable)

**Scope:** English Premier League (`league = 39`), season `2025`. Static spine only. **~3 API calls, ~61 curated rows.** No fixtures, stats, lineups, players, or odds.

**Why this slice:** it's the smallest thing that exercises *all three* hard parts end-to-end — the raw→curated flow, writing across multiple related tables, and **FK resolution** (standings rows must resolve to team ids, which must resolve to a league_season id). And the result is trivially checkable against reality: the standings should match the actual Premier League table.

### Prerequisites
- `raw.api_responses` exists (the Part 1 DDL, applied as a migration next session).
- `curated.tiers` seeded ✅ (Session 5).

### Steps
Each step is: **fetch → land raw row → normalize from the landed payload.**

1. **`GET /leagues?id=39&season=2025`**
   → land 1 raw row → upsert `curated.leagues` (EPL; `source_ref='39'`; `tier_id='?'`; `needs_review=true`) → capture `league_id`.
   → upsert `curated.league_seasons` (`league_id`, `season=2025`, coverage flags) → capture `league_season_id`.

2. **`GET /teams?league=39&season=2025`**
   → land 1 raw row → for each of the 20 teams: upsert `curated.venues` (from embedded venue) → `venue_id`; upsert `curated.teams` (`source_ref=team.id`, `venue_id`, `current_league_id=league_id`) → add `{team.id → our id}` to the resolution map.

3. **`GET /standings?league=39&season=2025`**
   → land 1 raw row → for each of the 20 rows: resolve `team_id` from the map; upsert `curated.standings` (`league_season_id`, `team_id`, `rank`, `points`, `form`, splits, …).

### Verification (run these `SELECT`s and eyeball)

```sql
-- 3 raw payloads landed
SELECT endpoint, source_fetched_at FROM raw.api_responses ORDER BY id;              -- expect 3 rows

-- spine populated
SELECT count(*) FROM curated.leagues;                                              -- >= 1 (EPL present)
SELECT count(*) FROM curated.league_seasons WHERE season = 2025;                   -- >= 1
SELECT count(*) FROM curated.teams;                                                -- 20
SELECT count(*) FROM curated.venues;                                               -- ~20
SELECT count(*) FROM curated.standings;                                            -- 20

-- the real test: does our data reproduce the actual Premier League table?
SELECT s.rank, t.name, s.points, s.form
FROM   curated.standings s
JOIN   curated.teams t ON t.id = s.team_id
JOIN   curated.league_seasons ls ON ls.id = s.league_season_id
WHERE  ls.season = 2025
ORDER  BY s.rank;                                                                   -- eyeball vs reality

-- idempotency proof: re-run the whole slice, then confirm counts are UNCHANGED (no duplicates)
```

If the last query prints the Premier League ladder in order and re-running doesn't inflate the counts, one worker is proven end-to-end and we can scale the same pattern to every other table.

---

## Part 6 — What we are deliberately NOT doing today

- **No worker code.** This is the spec; the code is next session (Claude Code).
- **No odds, fixtures, stats, lineups, or players** in the slice — spine only.
- **No full Raw layer** — just the one landing table; archival/diffing/per-entity raw tables are their own session.
- **No odds cadence / closing-odds job** — stays on Q-NEW-AI.

### Suggested next session
**Implement the slice** with Claude Code: (1) turn the Part 1 DDL into a timestamped migration and `supabase db push`; (2) write the leagues→teams→standings worker following Parts 3–4; (3) run it against EPL 2025; (4) verify with the Part 5 queries. Then generalise to fixtures and the rest.

---

## Appendix — Decisions & open questions raised this session

*Proposed for logging into `PROJECT_STATUS.md` at end-of-session (numbers provisional).*

**Decisions**
- **D-071** — Raw-first confirmed as the ingestion model, with a *minimal* `raw.api_responses` landing table (one row per API call, verbatim payload + provenance + response hash). Full Raw layer deferred. Normalization runs *from the landed payload* to keep live and replay paths identical.
- **D-072** — Sync order is the topological sort of the curated FK graph: `venues → leagues → league_seasons → teams → standings → fixtures → players → match_statistics/lineups/player_match_stats → odds_bookmakers/odds_markets → odds`.
- **D-073** — Upsert strategy: `INSERT … ON CONFLICT (natural key) DO UPDATE … RETURNING id`; natural key = `(sport, source, source_ref)` for real entities, `(source, source_ref)` for venues/reference lists, composite-FK for derived rows; FK wiring via an in-run `source_ref → id` resolution map with a SELECT fallback. Implements D-049; idempotent per §6.6. Odds is the append-only exception (D-060).
- **D-074** — First vertical slice = EPL (league 39), season 2025, static spine only (leagues → teams → standings), ~3 calls, verified against the real league table + an idempotency re-run.

**Open questions**
- **Q-NEW-AJ** — Raw granularity at scale: keep one-row-per-call, or add per-entity raw tables when incremental diffing is built? (MVP: per-call. Revisit in the full Raw-layer session.)
- **Q-NEW-AK** — Pagination + rate-limit/budget handling for high-volume endpoints (`/players`, `/odds`, per-fixture loops) — operational detail for the implementation session.
