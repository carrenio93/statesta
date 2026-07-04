# Statesta — Curated Layer Schema Reference

**Document version:** 0.2 (Session 4A static spine + Session 4B event data — Curated Layer complete)
**Companion migrations:** `001_curated_static.sql` (4A), `002_curated_events.sql` (4B)
**Status:** Covers the full Curated Layer. Static spine in Part 2 (4A); event entities in Part 5 (4B). The next layers (Raw, Computed, User, Configuration) are separate sessions.

> **How to read this.** Each table has: what it is, why it exists, and a column-by-column rationale. Design decisions that apply everywhere are explained once, up front, in **Part 1 — Conventions**, so the per-table sections stay short.

---

## Part 1 — Conventions (apply to every Curated table)

These are the rules baked into every table. They come straight from the locked decisions in `PROJECT_STATUS.md` and `ARCHITECTURE.md`.

### 1.1 Each data layer is its own Postgres *schema*

ARCHITECTURE §4.1 says the four data layers are "separated by schema, not by physical database." So the Curated layer lives in a Postgres schema called `curated`. Every table is `curated.<name>`.

Why this matters in plain terms: a Postgres "schema" is like a labelled drawer inside the one database. Putting curated tables in their own drawer keeps them out of the `public` drawer (the one Supabase exposes to the browser via the anon key). That means:

- The browser can never accidentally read or write curated data.
- We don't need Row Level Security (RLS) on these tables — only our backend's service role touches them.
- Raw, Computed, User, and Configuration each get their own drawer later (`raw`, `computed`, `app`, `config`).

### 1.2 Surrogate primary keys + provenance (the multi-source decision)

Every entity gets **our own** primary key — `id bigint generated always as identity`. We do **not** reuse API-Football's IDs as our keys.

API-Football's ID is stored separately, in a **provenance block** present on (almost) every table:

| Column | Meaning |
|---|---|
| `source` | Which provider this row came from. Defaults to `'api_football'`. |
| `source_ref` | The provider's own ID for this thing (stored as text). |
| `source_fetched_at` | When the sync worker last pulled this row from the source. |
| `created_at` | When our row was first written. |
| `updated_at` | When our row last changed (kept honest by a trigger). |

Why: we committed to **multi-source readiness** (D-041). If a second data provider is added later, it just becomes another `source` value — our identity system and all our foreign keys don't have to change. The only cost is that the sync worker translates "API-Football team 33" into "our team `id` 1029" when it writes (a cheap, normal lookup, done with `INSERT ... ON CONFLICT (sport, source, source_ref)`).

**Two flavours of `source_ref`:**
- **Real entities** that have a vendor ID (leagues, teams, venues) → `source_ref` is **NOT NULL** and is part of a uniqueness rule.
- **Derived / relationship rows** (league_seasons, standings) → identity is a combination of other keys (e.g. league + season). For these `source_ref` is **nullable**, and a composite `UNIQUE` constraint is what guarantees one row per real-world thing.

### 1.3 `sport` on sport-specific entities (D-039)

Anything whose meaning depends on the sport carries `sport text not null default 'football'`. At MVP every query passes `'football'`; adding a second sport later needs no migration. Truly sport-agnostic things (a stadium) do **not** get the column.

### 1.4 Absent ≠ zero (§6.7)

This is important and easy to get wrong. A measurement we **don't have** is stored as `NULL`, never as `0`. A team with an unknown corner count is `NULL`; a team that genuinely had zero corners is `0`. That's why every statistic / count column is **nullable with no numeric default**. Downstream, a filter that hits `NULL` treats it as "insufficient sample" and auto-fails — it must never read a missing value as a real zero.

### 1.5 Time is always `timestamptz` (UTC)

Every moment-in-time column is `timestamptz`, stored in UTC. No naive timestamps. Kickoff times, sync times, audit times — all UTC, formatted for the user's timezone only at display time.

### 1.6 `source_extra jsonb` — the safety net (§6.1)

The Raw layer keeps the verbatim API payload, but to query an occasional field we didn't explicitly model, the high-variance tables carry a `source_extra jsonb` column. Anything API-Football sends that we haven't given a typed column lands here, so it's never lost and is still queryable. Typed columns remain the primary, clean representation.

### 1.7 No RLS on curated tables

Curated data is platform-wide and identical for all users. Only the backend service role reads/writes it. RLS (the "users see only their own rows" mechanism) belongs to the **User layer** session, not here.

---

## Part 2 — The static entities (Session 4A)

Dependency order (each table only references ones above it):

```
tiers
venues
leagues ─────────► (tiers)
league_seasons ──► (leagues)
league_tier_changes ► (leagues, tiers*)   * by tier_id text, not FK-enforced both ways
teams ───────────► (venues, leagues)
standings ───────► (league_seasons, teams)
```

### 2.1 `curated.tiers`

**What it is:** the fixed catalogue of league tiers — the 8 user-facing tiers plus `?` (unmapped) from REQUIREMENTS §4.2.3.

**Why a table and not a Postgres enum:** an enum would need a migration to change. A small lookup table lets `leagues.tier_id` be a real foreign key (so a typo like `'tpo'` is impossible) while keeping tier *metadata* (label, ordering, default-on) editable — in the spirit of D-037 (config, not code). The per-tier *gating values* and the auto-scoring *weights* are **not** here; those are Configuration-layer concerns for a later session. This is the deliberate "mix" split you asked me to design.

| Column | Why |
|---|---|
| `sport`, `tier_id` | Composite primary key. Per-sport so a future sport can have its own ladder (D-039). |
| `label` | Display text for the tier pill ("Top", "Women", …). |
| `sort_order` | Fixed left-to-right pill ordering. |
| `selected_by_default` | `friendlies` = false (opt-in, §4.2.1); the other 7 user-facing tiers = true. |
| `is_user_visible` | `?` = false, so unmapped leagues are hidden from users until reviewed (§4.2.5). |

The migration **seeds** all 9 football rows.

### 2.2 `curated.venues`

**What it is:** stadiums / venues, captured from the API-Football team payload.

**Why it's here even though §6.3 doesn't list it:** the "capture every field" principle (§6.1) — the venue object arrives with every team and we don't want to throw it away. It's static reference data, so it belongs in the 4A spine. *Flagged for your sign-off* (logged as D-054). Sport-agnostic, so **no `sport` column**.

Key columns: `name`, `address`, `city`, `country_name`, `capacity` (nullable — absent ≠ zero), `surface`, `image_url`. Unique on `(source, source_ref)`.

### 2.3 `curated.leagues`

**What it is:** the **competition** entity — one row per competition (e.g. "Premier League"), stable across seasons.

**Key design choice — the league/season split.** v2.7 flattened a single season onto the league row. v3 separates the stable competition (`leagues`) from per-season facts (`league_seasons`). This is more correct: a competition's tier, country, and logo don't change season to season, but its coverage and standings do.

| Column group | Columns | Why |
|---|---|---|
| Provenance | `source`, `source_ref`, … | §1.2 |
| Identity | `sport`, `name`, `type` | `type` is `'league'`/`'cup'` — drives cup detection and auto-scoring. |
| Display | `country_name`, `country_code`, `logo_url`, `flag_url` | `country_code` null for international comps. |
| **Tier (the "mix")** | `tier_id` | Current tier. FK to `tiers`. Defaults to `'?'`. Read by every form query (§4.2.5). |
| | `suggested_tier_id` | Auto-scoring's suggestion; nullable. |
| | `tier_is_admin_set` | Once true, auto-scoring never touches this league again (§4.2.4). |
| | `needs_review` | New / auto-migrated leagues await admin review (§4.2.8). Defaults true. |
| | `is_active` | False when a competition stops existing mid-season (§4.2.6). |

**Indexes:** `(sport, tier_id)` for tier-scoped queries; `country_name` for browse/search; a **partial** index on `needs_review` (only indexes rows that are true) to power the admin review queue cheaply.

### 2.4 `curated.league_seasons`

**What it is:** one row per `(league, season)` — the season window plus API-Football's per-season **coverage** flags (does this season have standings? lineups? player stats? odds?).

| Column | Why |
|---|---|
| `league_id`, `season` | Unique together. `season` is the year, e.g. `2025`. |
| `start_date`, `end_date` | Season window. |
| `is_current` | Mirrors API-Football's "current" flag — feeds the Season Resolver (D-045). |
| `cov_standings`, `cov_fixtures`, `cov_fixture_statistics`, `cov_lineups`, `cov_player_statistics`, `cov_odds` | Coverage flags. **Nullable** — null means "we don't yet know," honouring absent ≠ zero. |

**Deliberate exclusion — season completion %.** The completion-range filter (D-011) needs a "how far through the season are we?" number. That number is *derived* (fixtures played ÷ total), which makes it a **Computed-layer** value, not curated. So it is intentionally **not** in this table; the Computed-layer session will own it. (Logged as D-055.)

### 2.5 `curated.league_tier_changes`

**What it is:** an append-only audit log of tier assignments — who changed a league's tier, when, from what, to what, and why (§4.2.5). The audit *data* is MVP (§4.2.9); the admin *UI* for it is Phase 2.

| Column | Why |
|---|---|
| `league_id` | Which league changed. |
| `from_tier_id`, `to_tier_id` | `from` is null on first assignment. |
| `change_source` | `'admin'` (manual), `'auto_migration'` (the v2.7→v3 launch mapping, §4.2.8), or `'auto_score'`. |
| `changed_by` | `uuid` soft reference to the admin user. **No FK yet** — the user/admin tables are a later session, so the FK is added then (logged as D-058). |
| `note` | Optional reason. |
| `changed_at` | UTC timestamp. |

### 2.6 `curated.teams`

**What it is:** the team entity — clubs and national teams.

| Column | Why |
|---|---|
| Provenance + `sport` | §1.2, §1.3 |
| `name`, `code` | `code` is the 3-letter shorthand (e.g. `'MUN'`). |
| `country_name`, `country_code`, `founded` | Metadata. |
| `is_national` | National team vs club. |
| `logo_url` | Crest. |
| `venue_id` | Home venue (FK to `venues`, `ON DELETE SET NULL`). |
| `current_league_id` | **Soft, denormalized** pointer to the team's primary current league. |

**Open question Q-NEW-AG — "current league."** §6.3 literally asks teams to record a "current league," but a team plays in several competitions at once (domestic + cup + continental). I've added `current_league_id` as a convenience pointer the sync worker maintains (the primary domestic league), while the *authoritative* record of who-plays-where comes from standings and fixtures. If we later want full participation history, that's a `team_league_seasons` link table — deferred for now to avoid over-building.

### 2.7 `curated.standings`

**What it is:** league-table rows, one per `(league_season, team)`.

**Full fidelity (§6.1):** we capture the overall **and** home **and** away splits — played / win / draw / lose / goals-for / goals-against for each — plus `rank`, `points`, `goals_diff`, `form` (e.g. `'WWDLW'`), `status` (`up`/`down`/`same`), `description` (e.g. "Promotion - Champions League"), and `group_label` for group-stage competitions. Every measure is nullable (§6.7).

**Identity:** the `(league_season_id, team_id)` unique constraint is what guarantees one row per team per season — this is a derived/relationship row, so `source_ref` is nullable here (§1.2).

---

## Part 3 — Decisions captured this session

These will be logged formally in `PROJECT_STATUS.md` §7 at end-of-session.

| ID | Decision |
|---|---|
| D-049 | Surrogate primary keys (`id`) on every curated entity; vendor IDs stored as `source` + `source_ref`. Honors D-041 multi-source readiness. |
| D-050 | Each data layer is its own Postgres schema; Curated tables live in `curated.*`. |
| D-051 | Absent ≠ zero — all measure columns nullable, no numeric defaults (§6.7). |
| D-052 | Tier "mix": `leagues.tier_id` + sync workflow columns are Curated; `tiers` catalogue + `league_tier_changes` audit are Curated; auto-scoring weights and review-queue workflow are deferred to Configuration. |
| D-053 | League/season split: `leagues` = stable competition entity; `league_seasons` = per-season facts + coverage flags. |
| D-054 | `curated.venues` added under capture-every-field (§6.1); sport-agnostic. *(Pending your sign-off.)* |
| D-055 | Season completion % excluded from Curated — it is a derived, Computed-layer value. |
| D-056 | Session 4 split into 4A (static spine) + 4B (event data); packaged as two ordered migrations. |
| D-057 | `source_ref` nullable on derived/relationship rows (league_seasons, standings); composite uniqueness governs identity. |
| D-058 | `league_tier_changes.changed_by` is a `uuid` soft reference; FK to the admin user added when the User layer is designed. |

## Part 4 — Open questions raised this session

| ID | Question |
|---|---|
| Q-NEW-AG | "Current league" for teams — keep the denormalized `current_league_id` convenience pointer, or introduce a full `team_league_seasons` participation table? Denormalized pointer chosen for MVP. |

---

## Part 5 — The event entities (Session 4B)

These are the high-traffic, constantly-changing tables. They all reference the 4A spine via foreign keys, which is why the spine had to exist first.

Dependency order:

```
fixtures ─────────► (league_seasons, teams, venues)
players                                   (team-agnostic — no FK out)
match_statistics ─► (fixtures, teams)
lineups ──────────► (fixtures, teams, players)
player_match_stats ► (fixtures, players, teams)
odds_bookmakers                           (reference)
odds_markets                              (reference)
odds ─────────────► (fixtures, odds_bookmakers, odds_markets)
```

### 5.1 `curated.fixtures`

**What it is:** one row per match.

It points at the spine: `league_season_id` (which competition + season), `home_team_id` / `away_team_id`, and `venue_id`. Plus `match_date` (kickoff in UTC), `referee`, `round`, and the match `status` (`status_short` like `NS`/`FT`, `status_long`, `status_elapsed` minutes, `status_extra`).

**The score is captured at every breakdown (D-067):** headline `home_goals`/`away_goals`, then half-time (`*_ht`), 90-minute full-time (`*_ft`), after-extra-time (`*_et`), and penalty shootout (`*_pen`). Every one is nullable — a match not yet played, or a score the source didn't report, is `NULL`, never `0` (§6.7). The filter engine reads these directly (BTTS, Over 2.5 from the headline goals; half-time markets from `*_ht`).

**Indexes** are chosen for the filter engine's core question — "a team's last N matches before date D": `(home_team_id, match_date)` and `(away_team_id, match_date)` let Postgres walk a team's matches newest-first cheaply. Plus `(league_season_id, match_date)` for league browsing and a partial index on upcoming (`status_short = 'NS'`).

### 5.2 `curated.players`

**What it is:** the player as a *person* — name, birth info, nationality, height/weight (the source ships these as strings like `'180 cm'`, so we keep them as text), photo.

**Key design choice — team-agnostic (D-064).** There is deliberately **no team column** here. A player isn't owned by a team; which club they turned out for is a fact *about a match*, recorded in `lineups` and `player_match_stats`. This is the clean fix for the v2.7 bug where a transferred player showed his old team everywhere.

### 5.3 `curated.match_statistics`

**What it is:** team-level match stats, one row per `(fixture, team)` — so each match has two rows.

**Full fidelity (D-066):** the complete API-Football statistic set, not just the v2.7 subset — shots (on/off/total/blocked/inside/outside box), fouls, corners, offsides, possession %, cards, GK saves, passes (total/accurate/%), plus modern metrics **expected goals (xG)** and **goals prevented**. Anything new the source adds lands in `source_extra`. All measures nullable (§6.7).

Identity is the `(fixture_id, team_id)` pair, so `source_ref` is nullable here (D-057).

### 5.4 `curated.lineups`

**What it is:** who was named for a match — one row per `(fixture, team, player)`, covering both the starting XI and the bench.

**Single-table design (D-065):** the team-level `formation` and `coach` are copied onto every player row rather than living in a separate header table. It's a little redundant, but it keeps reads simple and matches how v2.7 thought about lineups. `is_starting` separates the XI (true) from substitutes (false); `grid` is the pitch coordinate (e.g. `'1:4'`); `player_name` is denormalised for fast display.

*Coaches* are stored as a soft `coach_name` + `coach_source_ref` for now — see open question Q-NEW-AH.

### 5.5 `curated.player_match_stats`

**What it is:** per-player, per-match performance — one row per `(fixture, player)`. This is the backbone of the (Phase 2) Player Props engine; we **collect the data from launch** even though the UI comes later (D-022).

`team_id` records the team the player turned out for *in this match* (transfer-safe, per D-064). `minutes_played` drives the "≥ 45 minutes" threshold filter. The rest is the full API-Football player stat block (D-066): shots, goals/assists/conceded/saves, passes (total/key/accuracy), tackles/blocks/interceptions, duels, dribbles, fouls, cards, and the five penalty counters. All nullable.

> **Field note — `passes_accuracy`.** API-Football reports this as a number that, depending on endpoint/season, can mean either a count of accurate passes or a percentage. We store it as-is (`integer`) and will normalise meaning in the Computed layer if needed, rather than guessing at curation time.

### 5.6 The odds tables (`odds_bookmakers`, `odds_markets`, `odds`)

This is the most carefully designed part of the layer, because the requirements need two different things from odds: **the full history of every price change** (general use) and **the closing price** (backtesting).

**`odds_bookmakers`** and **`odds_markets`** are tiny reference lists (Bet365 today; "Match Winner", "Goals Over/Under", … as markets). They exist so the bookmaker name and market name are stored *once* and referenced by id, instead of being repeated as free text across millions of odds rows.

**`odds`** is the important one — an **append-only change log (D-060)**. One row = one price we observed for one selection at one moment:

`(fixture_id, bookmaker_id, market_id, selection, line, odd, phase, captured_at)`

- `selection` is e.g. `'Home'` / `'Over'` / `'Yes'`.
- `line` is the handicap/total, e.g. `2.5` — and is `NULL` for markets that have no line (like Match Winner).
- `captured_at` is when *we* saw the price; `source_updated_at` is the source's own stamp.
- `phase` is `pre_match` or `in_play` (D-061).

Rows are **never updated** — the sync inserts a new row only when a price moves. So the table literally *is* every change, in order.

**How the two questions are answered from this one table:**

- *"Odds at time T?"* → the latest row for that exact selection with `captured_at ≤ T`.
- *"Closing odds?"* → the latest row with `phase = 'pre_match'` and `captured_at ≤ kickoff`. The `pre_match` filter is why the `phase` flag exists: once we ever capture live prices, the closing line must never accidentally be an in-play tick.

**Where "closing" actually gets stored (D-062):** the *resolved* closing price is a **derived** value — you only know which row was "closing" *after* kickoff, by looking back. By our own layer rule (the same one that pushed season-completion % out of Curated, D-055), derived values belong to the **Computed layer**. So a later session builds a small `computed.closing_odds` table, filled by a post-kickoff job, that the backtest reads directly — fast, and honest (real captured odds only, D-023). Curated keeps the raw history; Computed keeps the resolved answer.

**Honest caveat:** the schema *supports* rich price history, but how much history actually exists depends on how often the sync captures odds. At launch we may often have just one near-closing snapshot per selection — fine, and the design gets richer later with no schema change.

**Indexes:** `ix_odds_pit` puts the selection-identity columns first and `captured_at DESC` last, which is exactly the shape a point-in-time / closing lookup needs; plus a plain `fixture_id` index for "show all odds for this match." The append-only nature means no `updated_at` and no trigger on this table.

---

## Part 6 — Decisions captured in Session 4B

| ID | Decision |
|---|---|
| D-060 | `curated.odds` is an append-only change log — one row per observed price; the table is the full history; "odds at T" = latest row with `captured_at ≤ T`. |
| D-061 | `odds.phase` (`pre_match` / `in_play`) so closing = latest `pre_match` price at or before kickoff. In-play not built yet; flag added now to avoid a later migration. |
| D-062 | The *resolved* closing odd is a derived value and lives in the **Computed layer** (`computed.closing_odds`, later session), not in Curated. |
| D-063 | Odds modelled as three tables: `odds_bookmakers` + `odds_markets` (reference) and `odds` (fact), keeping repeated names out of the fact table. |
| D-064 | `players` is team-agnostic; the per-match team is recorded on `lineups` and `player_match_stats`. Fixes the v2.7 transferred-player bug. |
| D-065 | `lineups` is a single table with `formation` and `coach` denormalised onto each player row (no separate header table). |
| D-066 | `match_statistics` and `player_match_stats` capture the full API-Football field set (incl. xG, goals prevented, duels, dribbles, penalties), per §6.1. |
| D-067 | `fixtures` stores the full score breakdown — headline, half-time, full-time, extra-time, penalties — all nullable (§6.7). |

## Part 7 — Open questions raised in Session 4B

| ID | Question |
|---|---|
| Q-NEW-AH | Coaches — keep the soft `coach_name` + `coach_source_ref` on `lineups`, or promote coaches to their own `curated.coaches` entity later? Soft fields chosen for MVP. |
| Q-NEW-AI | Odds capture cadence — how often the sync snapshots odds (operational), and the design of the post-kickoff job that resolves `computed.closing_odds`. Belongs to an operational / Computed-layer session. |
