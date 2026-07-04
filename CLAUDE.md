# CLAUDE.md — Statesta

> This file is read automatically by Claude Code at the start of every session in this repo.
> Keep it short and current. It tells Claude Code how this project works and what the hard rules are.

## What Statesta is

Statesta is a **football analytics and betting-intelligence SaaS**. It is deliberately positioned as a **neutral research tool** ("check what Statesta has to say before placing bets"), not an edge-selling or gambling-language product. Football at launch (Greece-first), multi-sport-ready architecturally. v3 is the cloud, multi-user evolution of a local prototype (built in May 2026 under the working name "ScoutEngine").

## Golden rules (read before doing anything)

1. **Read `PROJECT_STATUS.md` and `CRITICAL_RULES.md` first, every session.** They are the authoritative record. If anything here or in memory conflicts with them, the files win.
2. **Never change the remote database directly.** No edits via the Supabase Dashboard SQL editor / Table editor on the remote project. **All schema changes go through migration files** in `supabase/migrations/`. Direct edits break migration history and make `db push` fail.
3. **Never edit a migration that has already been applied.** Migrations are forward-only. To change something, add a *new* migration.
4. **The user approves before execution.** This is an architect → executor split: design and decisions happen in the architect chat; Claude Code implements only what the user has approved. When in doubt, ask.
5. **One focused change at a time.** Don't expand scope silently.

## Tech stack

- **Database:** PostgreSQL on **Supabase** (schema-per-layer; see below)
- **Backend:** **FastAPI** (Python) on **Railway**
- **Frontend:** **Next.js 15** + TypeScript + Tailwind + shadcn/ui on **Vercel**
- **Auth:** Supabase Auth · **Payments:** Stripe · **Cache/rate-limit:** Redis via Upstash · **CI/CD:** GitHub Actions
- **Data sources:** **API-Football** (entities + deep stats, fixed-rate plan) and **BetsAPI** (odds + in-play)

## Database conventions (locked — see CURATED_SCHEMA_REFERENCE.md for full rationale)

- **Each data layer is its own Postgres schema:** `curated`, then later `raw`, `computed`, `app` (user), `config`. Not everything in `public`.
- **Surrogate primary keys** (`id bigint generated always as identity`). Vendor IDs are stored as `source` + `source_ref`, never reused as our keys (multi-source readiness).
- **Provenance block on every row:** `source`, `source_ref`, `source_fetched_at`, `created_at`, `updated_at` (kept current by the `curated.set_updated_at()` trigger).
- **`sport`** column (default `'football'`) on every sport-specific table.
- **Absent ≠ zero:** every measure/stat column is nullable with no numeric default. A missing value is `NULL`, never `0`.
- **`timestamptz` (UTC)** for every moment in time.
- **`source_extra jsonb`** catch-all on high-variance tables.
- **No RLS on `curated.*`** (platform data, service-role only). RLS belongs to the `app`/user layer.

## Migrations

- Live in `supabase/migrations/`, named `<timestamp>_<name>.sql` (Supabase applies them in **timestamp order** and tracks them in `supabase_migrations.schema_migrations`).
- Current migrations:
  - `…_curated_static.sql` — Curated static spine (tiers, venues, leagues, league_seasons, league_tier_changes, teams, standings)
  - `…_curated_events.sql` — Curated event data (fixtures, players, match_statistics, lineups, player_match_stats, odds + odds_bookmakers + odds_markets)
- Apply with `supabase db push` against the **linked** project. Verify with `supabase migration list`.

## Repo layout (target)

```
statesta/
  docs/            governance: PROJECT_STATUS.md, CRITICAL_RULES.md, REQUIREMENTS.md,
                   ARCHITECTURE.md, CURATED_SCHEMA_REFERENCE.md
  supabase/
    migrations/    timestamped .sql migrations (source of truth for schema)
    config.toml
  backend/         FastAPI app (later)
  frontend/        Next.js app (later)
  CLAUDE.md        this file
  README.md
  .gitignore
  .env             (never committed)
```

## Working method (the user runs strict sessions)

- One deliverable per session; plan before producing; beginner pace (explain *why* before *what*).
- Decisions are logged with `D-###` IDs and open questions with `Q-###` IDs in `PROJECT_STATUS.md`.
- ClickUp mirrors session tasks (workspace is the project tracker).

## Never

- Commit secrets (`.env`, API keys, the Supabase DB password, service-role key).
- Touch the remote DB outside migrations.
- Reformat or rewrite whole files when a targeted edit will do.
- Introduce gambling-forward language into the product copy or naming.
