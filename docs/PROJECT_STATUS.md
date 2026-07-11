# Statesta — Project Status Tracker

> **THIS IS THE MASTER TRACKER.** Paste the full contents of this file at the start of every new Claude chat related to this project. It is the single source of truth. Update it at the end of every session.

---

## 0. INSTRUCTIONS FOR CLAUDE — READ FIRST

**This is your memory. You have no other context across chats.** You are reading this file because the user pasted it at the start of a new session. Act on these rules without exception.

**Companion file:** A `CRITICAL_RULES.md` file should also be pasted by the user. If it's missing, ask the user to paste it before proceeding. The two files together govern your behavior in every session.

### 0.1 Start-of-session protocol (MANDATORY VERIFICATION RITUAL)

Do these steps in order. Do not skip. Do not produce any work output until step 6 is complete.

1. **Read this entire file end to end.** Every section. Do not skim. Pay special attention to Sections 6 (last session), 7 (decisions), 8 (open questions), 9 (current active task).
2. **Read CRITICAL_RULES.md if pasted.** If not pasted, ask the user to paste it.
3. **Read any additional artifact files the user pasted.** Identify each by filename.
4. **Produce a verification summary** in this exact format:

   ```
   📋 Session Verification

   • Session number: [N]
   • Last completed session: [N-1] — [title], produced [files]
   • Most recent decisions: [list last 3 decision IDs and one-line summaries]
   • Open questions relevant today: [list any from Section 8 that affect today]
   • Active task per Section 9: [what PROJECT_STATUS.md says is next]
   • Today's session goal (as I understand it): [restate]
   • Additional files pasted: [list with role in today's session]
   • My proposed plan for today: [3-5 bullet points, estimated time]

   Please confirm this is correct before I begin, or correct anything I got wrong.
   ```

5. **WAIT for user confirmation.** Do not proceed on assumed correctness. If the user corrects anything, regenerate the verification summary with the correction and ask again. Repeat until the user confirms.
6. **Only after explicit user confirmation, begin the session work.**

This ritual exists because in long projects across many chats, small misreads compound. Catching them in the first 60 seconds is cheap. Catching them after producing artifacts based on wrong context is expensive.

### 0.2 During-session protocol

- Stay focused on the single declared session goal. If the conversation drifts toward another topic, stop and ask the user whether to defer it (add to Section 6 as a future session) or pivot.
- Long-form artifacts go in named files, never embedded in chat messages.
- Log decisions as they're made (you'll move them to Section 7 at end of session).
- Log new open questions as they arise (you'll move them to Section 8).
- Match the user's pace. The user is a beginner — explain reasoning, not just outputs.
- **Stay strictly in the scope of the current session's deliverable.** Requirements documents specify *what* the platform does, not *how it looks*. Architecture sessions specify *how systems connect*, not *what tables exist*. Schema sessions specify *table structure*, not *API shapes*. Drift compounds quickly; resist it.

### 0.3 End-of-session protocol (NON-SKIPPABLE — do every time)

Before the user closes the chat, you MUST:

1. **Update Section 6 (Sessions Log):** add this session as a row with date, title, deliverable, and ✅ Complete status.
2. **Update Section 7 (Decisions Log):** add every meaningful decision made this session with rationale. Use the next D-XXX number.
3. **Update Section 8 (Open Questions):** add new questions raised, mark resolved ones, update statuses.
4. **Update Section 9 (Current Active Task):** mark this session done; describe the next session (goal, why next, estimate).
5. **Update Section 10 (File Inventory):** add every new file produced this session.
6. **Produce the updated PROJECT_STATUS.md as a downloadable file** alongside any session artifacts.
7. **Show the user the diff explicitly.** In the chat (not just in the file), produce a "Changes to PROJECT_STATUS.md" block with this format:

   ```
   📝 Changes to PROJECT_STATUS.md this session:

   • Section 6: Added Session [N] row — [title] — ✅ Complete
   • Section 7: Added [D-0XX] — [one-line decision summary]
                Added [D-0XY] — [one-line decision summary]
   • Section 8: Added [Q-0XX] — [question]
                Resolved [Q-00X] — [resolution]
   • Section 9: Active task moved from Session [N] to Session [N+1]
   • Section 10: Added [filename] to inventory
   ```

   This lets the user verify nothing was missed before saving the new file.

8. **Tell the user explicitly:**
   - Which files were produced this session.
   - What to save and where.
   - Which ClickUp task to update or create.
   - For the next session: which files to paste alongside PROJECT_STATUS.md and CRITICAL_RULES.md, the next session's goal, and the next ClickUp task title.

9. **Invite verification.** End with: *"Please review the changes above. If anything is missing or wrong, tell me now and I'll fix it before you close the chat."* Wait for user response. Only close out if user confirms or makes corrections.

If you skip any step in 0.3, the user will lose context permanently. The end-of-session protocol is the most important thing you do in any session.

### 0.4 Hard rules — never violate

- **Never** produce code or schema before requirements are captured (REQUIREMENTS.md exists). ✅ Requirements now exist as of Session 2.
- **Never** dump multiple major artifacts in one session; one focused deliverable per session.
- **Never** skip the end-of-session update to this file.
- **Never** assume context not present in the pasted files. If something seems missing, ask.
- **Never** rush the user. Beginner-pace is the default. Explain "why" before "what."
- **Never** drift outside the current session's scope — see 0.2.

### 0.5 Self-check questions before responding

Before any non-trivial response, ask yourself:
- Is this in scope of the declared session goal?
- Is the user a beginner, and am I explaining reasoning, not just outputs?
- Is this output a file artifact, or appropriate to keep inline?
- At the end of this session, will I have everything I need to update Sections 6–10?
- Am I making a UI/product/design decision that should belong to Stratos, not me?

If you can't answer yes to all five, pause.

---

## 1. Project Overview

**Project name:** Statesta (domain secured June 2026; previously working-named ScoutEngine v3)
**Owner:** Alex (developer/architect, beginner)
**Partner:** Stratos (designer, owns visual design)
**Goal:** Build a public-facing, multi-sport pre-match scouting and player props SaaS platform with paid subscriptions, scaling to thousands of users.
**Started:** May 2026
**Target launch:** TBD (after designs land in ~1 month + build time)

**Current status:** Curated Layer designed (Sessions 4A/4B) and **applied live to Supabase** (Session 5) — 15 tables in the cloud, tiers seeded, private GitHub repo in sync. Next: Computed Layer design **or** sync workers to fill the tables.

---

## 2. Background & Context

The v2.7 prototype (originally built under the name ScoutEngine) is a working local-only tool built with the user in May 2026:
- Single-user, runs on Windows local machine
- DuckDB + FastAPI + single-file HTML dashboard
- Football data via API-Football Ultra plan (~75k calls/day budget)
- Three modules: Match Analysis (filter engine), Backtest, Player Props
- Tier system (1-9) for league prestige scoring
- 40+ KPIs for team form, player performance, opponent quality
- Pre-computed nightly KPI tables for instant filter performance

**Key principles carried into v3:**
- Multi-sport extensibility from day one (`sport` column on every relevant table)
- Pre-computation over real-time calculation
- Capture every field from API-Football, even unused ones (raw + curated layers)

**What's changing in v3:**
- Public SaaS, not local tool
- Postgres replaces DuckDB as primary database (DuckDB possibly added later as analytical layer)
- Next.js + React replaces single-file HTML
- Auth, paid subscriptions, multi-user
- Production-grade infrastructure (hosting, monitoring, CI/CD)
- **New analytical engines** (per Session 2): Opportunities Engine (per-fixture per-market hit-rate vs implied), Best Picks (algorithmic curated feed), Pre-built Strategies (admin-curated library).
- **Event Page, Team Page, League Page** as first-class analytical destinations with per-view tier gating.
- **Backtest reshaped** as async background job with queue + progress + persistence + tier-based priority.

---

## 3. Stack Decisions (LOCKED)

| Layer | Choice | Status |
|---|---|---|
| Frontend | Next.js 15 + React + TypeScript + Tailwind + shadcn/ui | LOCKED |
| Backend | FastAPI (Python) | LOCKED |
| Primary database | PostgreSQL via Supabase | LOCKED |
| Analytics database | DuckDB (deferred — added later if needed) | LOCKED (deferred) |
| Cache & rate limiting | Redis (Upstash) | LOCKED |
| Auth | Supabase Auth | LOCKED |
| Payments | Stripe | LOCKED |
| Frontend hosting | Vercel | LOCKED |
| Backend hosting | Railway or Fly.io (decide later) | TENTATIVE |
| Background jobs | TBD (decide in Session 3) | TBD |
| Observability | Sentry + Logtail/Axiom + Uptime Robot | LOCKED (general approach) |
| CI/CD | GitHub Actions | LOCKED |
| Project management | ClickUp | LOCKED |

---

## 4. Working Pattern

**Roles:**
- **This chat (Claude Opus, project-scoped):** Architect. Designs, plans, documents. Doesn't write production code directly.
- **Claude Code (terminal):** Engineer. Implements specs from this chat, edits files, runs tests, opens commits.
- **ClickUp:** Source of truth for task tracking. Every major task = one ClickUp item.
  - **Access note (for Claude):** ClickUp is often connected to this chat as an MCP tool — **check available tools before assuming either way** (do not claim you lack access without checking; do not assume you have it). If the ClickUp tools are present, update tasks directly. If they are *not* connected in a given session, hand the user ready-to-paste prompts for Claude Code (which has the ClickUp integration on the local side). Tool access is set per-chat and does not carry across sessions.
  - **Sync Engine list ID:** `901217784130`. Session tasks: `status: "backlog"` on creation, `status: "done"` on completion. `clickup_filter_tasks` needs `include_closed: true` to surface completed tasks.
- **GitHub:** Source of truth for code (when it exists).
- **PROJECT_STATUS.md (this file):** Source of truth for decisions and current state across all chats.

**Session workflow:**
1. Open new chat in this Anthropic project.
2. Paste this PROJECT_STATUS.md as first message.
3. State the session goal (one focused deliverable).
4. Work through it.
5. End of session: Claude updates this file (Section 6, 7, 9 as needed) and exports the new version.
6. User commits the new PROJECT_STATUS.md (and any artifacts produced) to the repo when one exists, or saves locally for now.
7. ClickUp tasks updated to reflect what was completed.

**Principles:**
- One deliverable per session.
- Every artifact is a named file with a description file.
- Tasks sized for 30 min – 2 hours of work.
- Plan before code, always.
- Beginner-pace; no rushing.

---

## 5. Features Captured So Far

This is the running list of features. **Fully formalized in REQUIREMENTS.md as of Session 2.** Section 5 below is a quick index; the authoritative spec is REQUIREMENTS.md.

**Core analytics (port from v2.7, extended in v3):**
- Match Analysis filter engine (40+ KPIs, multi-criteria, scoring) — with `sample = "season"` mode, completion range, strategy with line modes
- Backtest engine — **now async with queue, progress, persistence, tier priority**; real captured odds only
- Player Props engine — **deferred to Phase 2** (data collected MVP)
- Saved strategies — with schema versioning, pre-built (admin-curated) variants
- League tier system — **8 tiers** (top/medium/low/very_low/women/youth_reserves/cup_domestic/friendlies + ? unmapped), admin-managed mapping with audit log

**v3-new analytical features:**
- **Opportunities Engine** — per-fixture per-market hit-rate vs implied probability with Best Bet annotation
- **Best Picks** — algorithmic curated feed across all upcoming matches
- **Pre-built Strategies** — admin-curated library, tier-gated
- **Event Page** — multi-view per-match analytical destination
- **Team Page & League Page** — multi-view per-entity analytical destinations

**Public platform additions:**
- User authentication (email/password + Google OAuth) — others Phase 2
- User profiles & settings — with light/dark theme + language switcher
- Subscription tiers (free + trial + paid) — Stripe-backed; one-trial-per-account, no card
- Search — matches (upcoming + completed with date filter), teams, leagues; per-user search history
- Shortlist — folder-organized by saved strategy, no auto-prune; finished items retained
- Accumulators — built from shortlist pool; virtual only, no real-money

**Data scope:**
- Capture EVERY field from API-Football, even ones not currently used
- Multi-sport extensibility from schema day one
- Multi-source data integration architecturally prepared in MVP (provenance tracking; secondary sources Phase 2)

**Operational:**
- Resumable, deduplicated, error-logged syncs
- Background job queue with concurrency control, tier-based priority
- Pre-computed form snapshots (D-016)
- Pre-computed per-fixture opportunities (D-030)
- Methodology versioning (D-037)
- Historical odds backfill as pre-launch operational task (D-025)

---

## 6. Sessions Log

| # | Date | Session Title | Deliverable | Status |
|---|---|---|---|---|
| 1 | 2026-05-05 | Project Organization Setup | PROJECT_STATUS.md, CLICKUP_STRUCTURE.md, SESSION_WORKFLOW.md, CRITICAL_RULES.md | ✅ Complete |
| 2 | 2026-05-18 | Requirements Capture | REQUIREMENTS.md (full feature/role/page/endpoint inventory) | ✅ Complete |
| 3 | 2026-06-02 | High-Level Architecture | ARCHITECTURE.md (11 sections, topology + data flow Mermaid diagrams, cross-cutting patterns, resolved Q-002/Q-004/Q-NEW-G/Q-NEW-H at architecture level) | ✅ Complete |
| 4A | 2026-06-26 | Curated Layer Schema — Static Spine | `001_curated_static.sql`, `CURATED_SCHEMA_REFERENCE.md` (v0.1 — conventions + static entities) | ✅ Complete |
| 4B | 2026-06-26 | Curated Layer Schema — Event Data | `002_curated_events.sql` (fixtures, players, match stats, lineups, player stats, odds), `CURATED_SCHEMA_REFERENCE.md` → v0.2 | ✅ Complete |
| 5 | 2026-07-04 | Infrastructure Setup — repo + Supabase + migrations applied | Private GitHub repo `carrenio93/statesta`; Supabase project (EU/Frankfurt); `CLAUDE.md`, `.gitignore`, `README.md`, `supabase/config.toml`; **Curated migrations applied to hosted DB** (15 tables live, tiers seeded) | ✅ Complete |
| 6 | 2026-07-04 | Sync Workers — Ingestion Design | `SYNC_INGESTION_DESIGN.md` (raw-first model + minimal `raw.api_responses` landing table, FK-ordered sync chain, upsert/`source_ref→id` resolution, endpoint→table map, EPL-2025 vertical-slice spec) | ✅ Complete |
| 7 | 2026-07-08 | Sync Workers — EPL-2025 Spine Implementation | Working sync worker (`backend/statesta_sync/`): config, API-Football client, psycopg v3 DB helper, smoke test, raw-landing, `upsert_returning_id` + `ResolutionMap`, spine worker (leagues → league_seasons → venues → teams → standings). `raw.api_responses` migration applied. **Validated end-to-end vs EPL 2025: 1/1/20/20/20, real PL table reproduced, idempotent re-run, admin-override protection proven.** | ✅ Complete |
| 8 | 2026-07-09 | Sync Workers — EPL-2025 Fixtures Ingestion | `backend/statesta_sync/fixtures.py` (new) + `--entity fixtures` dispatch (lazy import) + `curated.fixtures` registered in the admin guardrail (empty set). First **event-data** worker; FK resolution via cross-run SELECT preload. **Validated vs EPL 2025: 380 fixtures, 0 unresolved venues, D-067 nullable score breakdown proven (headline/HT/FT populated on all 380, ET/PEN NULL on all 380), zero orphaned FKs, idempotent re-run (curated flat at 380, raw append-only). Learned API-Football `/fixtures` rejects an explicit `page` field → send `page` only when ≥ 2.** | ✅ Complete |
| 9 | 2026-07-11 | Sync Workers — `ingest_common.py` refactor + EPL-2025 `match_statistics` (first per-fixture worker) | **(1)** Extracted shared helpers into a neutral `backend/statesta_sync/ingest_common.py` (D-083 executed; `_fetch`/`_land`/`_dig`/`SyncError`/`SOURCE`/`SPORT` + private `_api_ok`/`_Fetched`), rewired `spine.py`/`fixtures.py`, removed the lazy import — byte-identical bodies (AST-verified), cycle gone (both import orders), package-wide undefined-name pass clean. Commit `b48ab87`. `.gitattributes` added to pin LF (`89a66b3`). **(2)** New `backend/statesta_sync/match_statistics.py`: `/fixtures/statistics` per fixture → `curated.match_statistics` on `(fixture_id, team_id)`, two rows/fixture, full 18-column fidelity + `source_extra`. Commit `33ccf96`. **Validated vs EPL 2025: 380/380 fixtures, 760 rows, 2-rows-or-0 invariant HELD across a mid-run power loss + resume, zero orphaned FKs, zero unmapped types (Q-NEW-AO closed for EPL), INSERT + DO-UPDATE (landed-raw re-upsert, 0 API calls) both verified. D-084 baseline: DB = 13,454,483 bytes (13 MB), `raw.api_responses` already largest at 784 kB / 391 rows.** | ✅ Complete |
| ... | TBD | (more added as we go) | | |

---

## 7. Decisions Log

A running log of important decisions, with rationale.

| # | Date | Decision | Rationale |
|---|---|---|---|
| D-001 | 2026-05-05 | Use Supabase (Postgres + Auth) | Solo dev needs auth + RLS + hosting bundled. Saves weeks of work. Open source so migration possible later. |
| D-002 | 2026-05-05 | Defer DuckDB analytical layer | Premature optimization. Postgres handles backtest workload for first hundreds of users. Add only when measured to be needed. |
| D-003 | 2026-05-05 | Three independent rate-limit layers | Sync workers respect API-Football budget. Redis middleware prevents abuse of our infra. Subscription gating handles free vs paid. Each layer protects something different. |
| D-004 | 2026-05-05 | Throw away first schema draft, rebuild after requirements | First draft was rushed and missed features (shortlist, betslips). Schema must come AFTER requirements are formalized. |
| D-005 | 2026-05-05 | Working pattern: chat = architect, Claude Code = engineer, ClickUp = tracker | Matches user's existing successful pattern from v2.7. Beginner-friendly. |
| D-006 | 2026-05-05 | Encode Claude's binding rules in Section 0 of PROJECT_STATUS.md itself | Claude has no memory across chats. Rules in Section 0 are self-enforcing. End-of-session update protocol is non-skippable. |
| D-007 | 2026-05-05 | Add three robustness safeguards: rigid verification ritual, CRITICAL_RULES.md companion file, end-of-session diff display | Catches misreads in first 60 seconds; CRITICAL_RULES.md stays in active attention; diff display lets user verify before saving. |
| D-008 | 2026-05-18 | No-card free trial | Customer-friendly; trades higher conversion drop-off for greater honesty. Captured implications: abuse vector, manual user activation post-trial. |
| D-009 | 2026-05-18 | Filter engine shared across Match Analysis and Backtest | One filter engine, two consumers (user-driven upcoming-match analysis + system-driven historical analysis). Avoids parallel maintenance. |
| D-010 | 2026-05-18 | Strategy = Betting Market + Selection + Line Modifier; data model captures every line of every market | Auto-pick-middle logic comes later; capture all lines now. |
| D-011 | 2026-05-18 | League completion is a configurable range (min/max), not just a minimum | Both early-season and late-season samples have quality issues; range gives users control. |
| D-012 | 2026-05-18 | League tier assignment is auto-scored as a baseline but human-overridable via admin panel; unmapped leagues surfaced for review | Auto-scoring as starting point; human admin is source of truth. Newly-discovered leagues enter `?` state. |
| D-013 | 2026-05-18 (revised) | Friendlies are not excluded at the data layer; they are a first-class tier (`friendlies`), off by default in user-facing scope filters; all other 7 tiers default on | Originally agreed to exclude friendlies entirely; revised after introducing 8-tier ladder. Form sample inclusion governed by the single rule: a match counts if its league's tier is in the user's currently selected scope. |
| D-014 | 2026-05-18 | Filter cache TTL = 1 hour | Balance between freshness and load. |
| D-015 | 2026-05-18 | Filter performance targets: 3s typical, 10s heavy (p95) | Achievable with pre-computed form snapshots; non-negotiable for usable analytics. |
| D-016 | 2026-05-18 | Pre-computed team form snapshots are MVP | Storage cost accepted in exchange for query-time performance. Per-team, per-as-of-date snapshots avoid recomputation at filter-evaluation time. |
| D-017 | 2026-05-18 | Backtest job queue is MVP | Synchronous backtests are operationally dangerous; single user can saturate API server. Queue is hard requirement, not optimization. |
| D-018 | 2026-05-18 | Backtest progress reporting via real percentage (engine reports candidate progress), not spinner | Candidate count known after Phase 1 pre-filter; real progress possible. UX honesty vs spinner ambiguity. |
| D-019 | 2026-05-18 | Backtest results persisted per user, retention configurable per tier | Stored, not transient. Tier-gated retention is an upgrade lever. |
| D-020 | 2026-05-18 | Paid users get queue priority over free users; configurable per tier | Standard SaaS pattern. Within tier, FIFO. |
| D-021 | 2026-05-18 (deferred) | Pre-computed player form snapshots — deferred to Phase 2 alongside Player Props (D-022) | Deferred because Player Props deferred. Data still collected MVP. |
| D-022 | 2026-05-18 | Player Props module (entire 4.4) deferred to Phase 2 | Reduces MVP scope. Schema and data collection (lineups, player_match_stats) stay in MVP so launch dataset is ready. UI, filter engine, Player Card, verdict engine, player form snapshots all move to Phase 2. |
| D-023 | 2026-05-18 | Backtest uses captured real odds only; no assumed-odd fallback; fixtures without captured odds for the chosen selection excluded from bet sample | Honest ROI; sample size reflects real odds coverage. API-Football provides historical odds (backfill via D-025). |
| D-024 | 2026-05-18 | Auto-alerts on saved strategies deferred until mobile app launch (Phase 3 or Future) | Alerts most valuable as push notifications on phones. Building before mobile apps means infrastructure that gets full value only post-mobile. |
| D-025 | 2026-05-18 | Historical odds backfill (Bet365, etc.) is a pre-launch operational task | Critical for backtest meaningfulness at launch. Not a post-launch enhancement. |
| D-026 | 2026-05-18 | Light/dark theme toggle and language switcher MVP | Architecture must support; English-only at launch (translation work later). |
| D-027 | 2026-05-18 | Search includes matches (by team name) as first-class result alongside teams and leagues; completed-fixture search with date filter MVP; per-user search history MVP | Match discovery via search is fundamental, not Phase 2. |
| D-028 | 2026-05-18 | League-tier visibility gating (`scope.league_tiers_visible`) removed from gating inventory; all users see all leagues and upcoming matches; depth-gating happens inside Event/Team/League pages | "Discovery free; depth paid" SaaS model. |
| D-029 | 2026-05-18 | Event Page is a first-class module with multi-view structure; each view per-tier-gateable; admin-configurable | Section 4.6 of REQUIREMENTS.md. Tab inventory is product design. |
| D-030 | 2026-05-18 (revised) | Opportunities Engine is MVP: per-fixture, per-market, pre-computed background; stored in `fixture_opportunities` table; Best Bet identification part of Opportunities, not separate | Single engine, not two. Result Probabilities and Analysis Summary deferred to product design. |
| D-031 | 2026-05-18 | Shortlist and Betslip/Accumulator unified into single Shortlist module with two functional modes | Replaces separate "Betslip Builder" concept. Reduces complexity. |
| D-032 | 2026-05-18 | Shortlist items are not auto-pruned after kickoff; finished fixtures retained; manual unstar is only removal | User wants to review outcomes; auto-prune would lose data. |
| D-033 | 2026-05-18 | Pre-built (platform-curated) strategies are MVP; admin-managed library; tier-gated visibility | Onboarding for new users; showcases analytical depth; major upgrade lever. |
| D-034 | 2026-05-18 | Best Picks curated surface is MVP; computed from Opportunities engine; tier-gated visibility (top-N for free, fuller for paid) | Transforms platform from tool to service. Algorithmic — no human editorial. |
| D-035 | 2026-05-18 | Completed-fixtures search with date filter moved to MVP | Discovery via past results is genuine product value, not Phase 2. |
| D-036 | 2026-05-18 | Per-user search history MVP, retention last 20 searches, FIFO, user-clearable | Privacy-friendly default. |
| D-037 | 2026-05-18 | **All gating values, limits, thresholds, labels, methodology coefficients, tab availability, retention windows are admin-tunable runtime configuration, not code** | Single most consequential decision in Session 2. Everything in Session 3 (architecture) and Session 4+ (schema) must respect this. No code deploys to adjust pricing, limits, gates, etc. |
| D-038 | 2026-05-18 | Analytical-output surfaces must display a user-facing disclaimer that platform output is based on historical analysis rather than predictive certainty; specific wording is product/legal design | Capability is required; copy is design work. |
| D-039 | 2026-05-18 | Multi-sport extensibility — sport column on every plausibly-sport-specific entity, default 'football'; schema designed for filtered queries from day one | Adding a sport in the future doesn't require schema migration. |
| D-040 | 2026-05-18 | Raw layer retained indefinitely with cold archival after 12 months | Storage cost accepted in exchange for replayability and methodology re-runs. |
| D-041 | 2026-05-18 | Multi-source data integration architecturally prepared in MVP (provenance tracking, source-specific sync workflows) even though only API-Football integrated at launch | Retrofitting provenance later is painful. Small upfront cost; large future flexibility. |
| D-042 | 2026-05-18 | GDPR compliance in MVP — full rights of access, erasure, rectification | EU users expected; compliance is non-negotiable. |
| D-043 | 2026-06-02 | **Backend hosting: Railway, single EU region (Amsterdam), Shape B with three services (`web`, `sync-worker`, `job-worker`).** Resolves Q-002. | Users mostly in Europe at launch; Fly.io's multi-region edge buys nothing today. Railway DX better for solo dev at beginner pace; cron + worker primitives map cleanly to three-service shape. Migration cost to Fly.io later is low (Docker portability). |
| D-044 | 2026-06-02 | **Background job system: Dramatiq on Redis (Upstash) for user-triggered async jobs; Railway built-in cron triggers for scheduled sync workloads.** Supabase Edge Functions ruled out (language mismatch, execution time limits). Resolves Q-004. | Dramatiq's smaller surface area + cleaner defaults fit a solo developer better than Celery; job needs aren't exotic. Separating scheduled syncs (Railway cron) from user jobs (Dramatiq) keeps operational concerns clean. |
| D-045 | 2026-06-02 | **Season Resolver — stateless pure-function component answering "what is this team's current season as of this date and tier scope?" Single implementation called by filter engine, backtest engine, form snapshot pre-computer, opportunities engine. Resolves Q-NEW-G at architecture level.** | Single source of truth for "current season" prevents drift across engines. Algorithm itself remains open and is implementation work for a later session. |
| D-046 | 2026-06-02 | **Line Resolver — stateless pure-function component answering "which specific line should this strategy use for this fixture, and what was the captured odd?" Single implementation called by filter engine, backtest engine, opportunities engine. Resolves Q-NEW-H at architecture level.** | Same rationale as D-045 — consistency across surfaces. MVP algorithm is trivial deterministic middle; Phase 2 may evolve to probability-weighted. |
| D-047 | 2026-06-02 | **Pure Resolver pattern named as a cross-cutting architectural convention.** Where ambiguity exists across multiple engines, one stateless function answers it; engines never reimplement. Stateless, deterministic, versioned, read-only. | Names a pattern that will recur (Season Resolver, Line Resolver, future methodology version selector, tier scope resolver). Naming once prevents future-Claude from reinventing it. |
| D-048 | 2026-06-02 | **Configuration Layer named as a first-class subsystem alongside the four data layers.** Holds gating values, methodology config, tier mappings, operational config, feature flags. Typed, validated, audited, Redis-cached with short TTL. Mechanism for D-037. | Configuration is not "a few env vars." It's a real subsystem that every service depends on. Architecturally first-class so Session 4+ schema treats it that way. |
| D-049 | 2026-06-26 | **Surrogate primary keys on every Curated entity (`id bigint generated always as identity`); API-Football IDs stored as `source` + `source_ref`, never reused as our keys.** | Honors D-041 multi-source readiness: a second provider becomes another `source` value without disturbing our identity or foreign keys. Cost is a cheap `source_ref`→`id` lookup in the sync worker. |
| D-050 | 2026-06-26 | **Each data layer is its own Postgres schema; Curated tables live in `curated.*` (not `public`).** | Implements ARCHITECTURE §4.1 (layers separated by schema). Keeps curated data out of the anon-exposed `public` schema, so no RLS needed and no accidental browser access. |
| D-051 | 2026-06-26 | **Absent ≠ zero: every measure/stat/count column is nullable with no numeric default.** | §6.7. A missing value must never read as a real zero; downstream filters treat NULL as insufficient sample. |
| D-052 | 2026-06-26 | **Tier "mix" placement: `leagues.tier_id` + sync workflow columns (`suggested_tier_id`, `tier_is_admin_set`, `needs_review`, `is_active`), the `tiers` catalogue, and the `league_tier_changes` audit log all live in Curated; auto-scoring weights and the review-queue workflow are deferred to the Configuration session.** | A league's current tier is a curated attribute read by every form query; tier auto-scoring tuning is config (D-037). Splits the concern cleanly per user direction. |
| D-053 | 2026-06-26 | **League/season split: `curated.leagues` is the stable competition entity; `curated.league_seasons` holds per-season facts + API-Football coverage flags.** | More correct than v2.7's flattened single-season league row; competition attributes (tier, country) don't change per season, while coverage and standings do. |
| D-054 | 2026-06-26 | **`curated.venues` table added (sport-agnostic) to capture the venue object shipped with every team.** | Justified by capture-every-field (§6.1). Not in §6.3's required-entity list, but it is static reference data belonging to the spine. |
| D-055 | 2026-06-26 | **Season completion % excluded from Curated; it is a derived value owned by the Computed Layer.** | Completion = fixtures played ÷ total — a computed metric. Keeps layer boundaries clean (D-011's completion-range filter reads it from Computed). |
| D-056 | 2026-06-26 | **Session 4 split into 4A (static spine) + 4B (event data), packaged as two ordered migrations (`001_curated_static.sql`, `002_curated_events.sql`).** | The odds point-in-time model and full-fidelity stats tables deserve dedicated focus; keeps one clean deliverable per session (Rule 2) at beginner pace. |
| D-057 | 2026-06-26 | **`source_ref` is nullable on derived/relationship rows (`league_seasons`, `standings`); identity is governed by a composite UNIQUE constraint instead.** | These rows have no single vendor ID; their real-world identity is a combination of foreign keys (e.g. league_season + team). |
| D-058 | 2026-06-26 | **`league_tier_changes.changed_by` is a `uuid` soft reference with no foreign key yet; the FK to the admin user is added when the User Layer is designed.** | Avoids a forward dependency on the (later) User Layer session while still recording who made each tier change. |
| D-059 | 2026-06-26 | **Project name finalized as `Statesta` (domain purchased June 2026); supersedes the working name ScoutEngine and the earlier candidate Onesta.** | Brand locked. All governance files renamed. Neutral research-tool positioning unaffected; no overt gambling language in the name. |
| D-060 | 2026-06-26 | **`curated.odds` is an append-only change log** — one row per observed price; the table holds the full history; "odds at T" = latest row with `captured_at ≤ T`. | Satisfies "capture every change" (general use) and "real captured odds" for backtest (D-023, D-010) from one source of truth. |
| D-061 | 2026-06-26 | **`odds.phase` (`pre_match` / `in_play`)** — closing = latest `pre_match` price at or before kickoff. | In-play not built yet; the flag is added now (like `sport`) so closing can never be polluted by a live tick, with no later migration. |
| D-062 | 2026-06-26 | **Resolved closing odds live in the Computed layer (`computed.closing_odds`, later session), not in Curated.** | Closing is a derived, post-kickoff judgment; derived values belong to Computed (same rule as D-055). Backtest reads a small fast table. |
| D-063 | 2026-06-26 | **Odds modelled as three tables: `odds_bookmakers` + `odds_markets` (reference) and `odds` (fact).** | Keeps repeated bookmaker/market names out of the millions of rows in the fact table. |
| D-064 | 2026-06-26 | **`players` is team-agnostic; the per-match team is recorded on `lineups` and `player_match_stats`.** | A player's team is a fact about a match, not the person. Fixes the v2.7 transferred-player bug at the schema level. |
| D-065 | 2026-06-26 | **`lineups` is a single table with `formation` and `coach` denormalised onto each player row.** | Simpler reads; matches the v2.7 mental model. Coaches not yet their own entity (Q-NEW-AH). |
| D-066 | 2026-06-26 | **`match_statistics` and `player_match_stats` capture the full API-Football field set** (incl. xG, goals prevented, duels, dribbles, penalties). | Capture-every-field (§6.1); avoids re-deriving from Raw later. `source_extra jsonb` absorbs anything new. |
| D-067 | 2026-06-26 | **`fixtures` stores the full score breakdown — headline, half-time, full-time, extra-time, penalties — all nullable.** | Filter engine needs HT and FT markets; absent ≠ zero (§6.7) so unplayed/unreported scores read as NULL. |
| D-068 | 2026-07-04 | **Infrastructure provisioned:** private GitHub repo `carrenio93/statesta`; Supabase project in EU/Frankfurt; Supabase CLI migration workflow; Curated migrations applied to the hosted DB (validated on local PostgreSQL 16 first). | Design was ahead of infrastructure; this makes the schema real and validated, and switches on the architect → Claude Code split. Frankfurt = lowest latency to Greece. |
| D-069 | 2026-07-04 | **Supabase↔GitHub auto-deploy intentionally NOT connected; schema changes are applied deliberately via `supabase db push`.** | Keep the human in the loop while learning; avoid surprise auto-deploys. Can enable later if desired. |
| D-070 | 2026-07-04 | **Migration files use Supabase timestamp naming (`<timestamp>_<name>.sql`);** the design-number names (`001_`, `002_`) are retired. Live files: `20260626120000_curated_static.sql`, `20260626120100_curated_events.sql`. | Supabase tracks and orders migrations by timestamp; the sequential-number prefixes would not be tracked correctly. |
| D-071 | 2026-07-04 | **Raw-first ingestion confirmed, with a *minimal* `raw.api_responses` landing table** (one row per API call: verbatim `response_body jsonb` + provenance + `response_hash`). Normalization runs *from the landed raw row*, not the live HTTP response, so the fresh-call and replay paths are one code path. Full Raw layer (per-entity tables, cold archival per D-040, diffing) deferred to its own session. | Architecture already committed to raw-first (§4, §5.3, D-040); the only open choice was how much raw structure to build now. Minimal table = replayability/audit/debuggability for the cost of one extra insert, without over-building. |
| D-072 | 2026-07-04 | **Sync order = topological sort of the curated FK graph:** `venues → leagues → league_seasons → teams → standings → fixtures → players → match_statistics / lineups / player_match_stats → odds_bookmakers / odds_markets → odds`. | A child row can't be written before its parent's surrogate `id` exists. Spine steps run once per league-season; event-data steps run per fixture (the budget-heavy bulk). |
| D-073 | 2026-07-04 | **Upsert strategy: `INSERT … ON CONFLICT (natural key) DO UPDATE … RETURNING id`.** Natural key = `(sport, source, source_ref)` for real sport entities, `(source, source_ref)` for venues + reference lists, composite-FK for derived rows (D-057). FKs wired via an in-run `source_ref → id` resolution map with a `SELECT` fallback. `odds` is the append-only exception (insert-on-change, D-060), not upserted. | Implements D-049's surrogate-key/provenance model and gives idempotency (§6.6): re-runs never duplicate. |
| D-074 | 2026-07-04 | **First vertical slice = EPL (league 39), season 2025, static spine only** (`leagues → teams → standings`, ~3 calls, ~61 rows). Verified by reproducing the real Premier League table via a join + an idempotency re-run. | Smallest slice that exercises all three hard parts end-to-end — raw→curated, multi-table writes, and FK resolution — with a trivially checkable result. |
| D-075 | 2026-07-08 | **`league_seasons.cov_fixtures` = logical OR of the four `coverage.fixtures` sub-flags** (umbrella "any fixture-level coverage this season"), not a copy of one sub-flag. | The specific sub-flags are already captured by sibling columns (`cov_fixture_statistics`, `cov_lineups`, `cov_player_statistics`), so the umbrella meaning is the non-redundant, most useful reading. Raw keeps the verbatim object regardless. |
| D-076 | 2026-07-08 | **`leagues.type` is normalized to lowercase (`'league'`/`'cup'`) in Curated;** Raw keeps the API's verbatim `"League"`. | `type` is a category/enum — a clean, case-consistent contract downstream is a data-quality gain, not a distortion. Applies to all leagues, all sources. Contrast D-051: reformatting a value the source gave us, not inventing one. |
| D-077 | 2026-07-08 | **`venues.country_name` stays NULL when the `/teams` venue object omits country;** never copied from `team.country`. | Absent-not-invented (D-051): the venue payload doesn't assert a country, and copying one smuggles a derived assumption in as source truth. If needed later, fill properly from the dedicated `/venues` endpoint. |
| D-078 | 2026-07-08 | **`standings.group_label` = NULL for single-table competitions;** only genuine group labels (e.g. World Cup "Group A") are stored. | API-Football echoes the competition name into `group` for single-table leagues; storing that is noise. NULL makes the column mean exactly one thing (NULL = no real grouping). Matches the schema comment. |
| D-079 | 2026-07-08 | **Admin-owned columns are INSERT-only and must never appear in any `DO UPDATE` set** — enforced mechanically, not by convention. Registry `ADMIN_OWNED_COLUMNS` in the upsert helper raises if an admin column is in an update and refuses to run against an unregistered table. Columns: `tier_id`, `needs_review`, `suggested_tier_id`, `tier_is_admin_set`, `is_active`. | The single most important ingestion-safety behavior: a nightly re-sync must never wipe a human admin's decision (D-012, §4.2.4). Design doc hadn't spelled this out; Claude Code surfaced it. Proven against a non-default value (`tier_id='top'` survived a re-sync while `updated_at` advanced). |
| D-080 | 2026-07-08 | **Commits go directly to `main`** for now (no feature-branch/PR flow). | Solo dev, sequential slices, no CI gate or collaborators to protect yet; matches existing history. **Revisit** the moment Stratos or anyone else commits, or CI review gates are added. |
| D-081 | 2026-07-09 | **On `fixtures`, an absent or unresolved venue → `venue_id = NULL`; a venue is never created in the fixtures pass.** Unresolved count is logged, not hidden. | "Absent, not invented" (D-051), consistent with D-077: the `/fixtures` payload's job isn't venue creation, so manufacturing partial venue rows from it would blur ownership and smuggle assumptions in as truth. Venue creation stays owned by `/teams` (and a later `/venues` sync). Proven harmless in practice — the run resolved **0 of 380** as unresolved (every EPL venue was already loaded). |
| D-082 | 2026-07-09 | **Pagination convention: send the `page` query param only for page ≥ 2.** API-Football defaults to page 1 and `/fixtures` *rejects* an explicit `page` field (returns HTTP 200 with an `errors` block). The worker's loop still reads `paging.total` and breaks correctly. | Universal, not a `/fixtures` special-case — the same rule is correct for the future paginated endpoints (`/players`, `/odds`). Side effect: page-1 raw rows record `request_params` without a `"page"` key, which still fully identifies the call. Surfaced by a real API error on the first run. |
| D-083 | 2026-07-09 | **Shared worker helpers (`_fetch`, `_land`, `_dig`, `SyncError`, `SOURCE`/`SPORT`) will be extracted into a neutral `ingest_common.py` as the first task of Session 9.** The interim lazy-import in `spine.py` is accepted for Session 8. | `fixtures.py` imports helpers back from `spine.py`, so a plain module-level import created a circular-import that broke when fixtures loaded first. Lazy import is the minimal fix now; the extraction is the clean fix and is cheap while there's only one sibling worker — before `match_statistics`, `lineups`, `player_match_stats` each add another. **Executed Session 9 (commit `b48ab87`): the two private helpers `_api_ok`/`_Fetched` travelled with `_fetch`/`_land`; byte-identical bodies (AST-verified); cycle gone in both import orders.** |
| D-084 | 2026-07-11 | **Upgrade Supabase to Pro at the *earlier* of: total DB size ≥ 400 MB, or immediately before public launch (for daily backups + PITR).** Total DB size is checked at the **end of every ingestion session** (`pg_database_size` + top-tables breakdown) and Claude reports a plain verdict; the person monitors nothing. Baseline anchored end of Session 9: **13,454,483 bytes (13 MB, 3.2% of the 400 MB trigger)**; `raw.api_responses` already the largest table (784 kB / 391 rows). | Removes the upgrade decision from the person's memory and makes it a standing, automatic check. 400 MB (not the 500 MB free cap) leaves an 80% buffer — crossing 500 MB flips the DB to **read-only**, which would freeze the sync worker mid-run. The size trigger will bite during ingestion (raw jsonb + odds change-log + multi-league growth), well before the launch/backups trigger. The 7-day inactivity pause does *not* apply: the nightly sync keeps the DB active. |
| D-085 | 2026-07-11 | **`match_statistics` value-parsing rules (against the real payload):** percent strings (`"61%"`) → strip `%` → **`Decimal`** (columns are `numeric(5,2)`, *not* int — absorbs a future fractional percent like `"61.5%"`); xG / `goals_prevented` decimal strings → `Decimal`, **signed values stored verbatim** (`goals_prevented` is legitimately negative); vendor `null` → **NULL, never 0**; a string that is neither `%`-suffixed nor a valid decimal → **raise** (parse failure is a bug, must never masquerade as absent data); `bool` explicitly rejected (Python `bool` is an `int` subclass). Type→column map matches **verbatim vendor strings** including inconsistent casing (`"Total passes"`, `"Shots insidebox"`), so a vendor rename surfaces as an unmapped type rather than silently binding wrong. | Parse to match the *column*, not today's sample. Recon against fixture 1378969 showed the four real value formats (int / percent-string / signed-decimal-string / null); designing to the observed reality (not an assumed shape) is what prevents a latent data-dependent `ValueError` deep in a future loop. |
| D-086 | 2026-07-11 | **Vendor-`null` count stats are stored NULL, never coerced to 0** — reaffirms D-051/§6.7 specifically for *count* measures where 0 is a plausible real value. The full run's null census is recorded as evidence: `red_cards` **680/760 (89%) NULL**, `offsides` 42/760, while `expected_goals`/`possession_pct`/`shots_blocked`/`goals_prevented` are 0 NULL. | Curation stores what the source *asserted*, not what it probably *meant*; coercing `null → 0` would permanently destroy the distinction between "no red card occurred" and "unknown". The consequence (naive `AVG`/`SUM` over count stats will silently skip NULL rows and overstate per-match rates) is a **Computed-layer** concern, logged as Q-NEW-AP — fixed there with per-measure `COALESCE`, never by contaminating Curated. |
| D-087 | 2026-07-11 | **Rate-limit visibility is log-only.** `ApiFootballClient.get()` stores `self.last_headers` (additive; return signature `(status_code, body)` unchanged) so the worker can log `x-ratelimit-requests-remaining` after each call; one `GET /status` call runs before the per-fixture loop to log the account's real ceiling. **No logic branches on any of this** (no auto-pause, no backoff). Throttle is a plain `--sleep` (default **0.5s** ≈ 2 req/s, deliberately conservative under the Ultra plan's **450/min** ceiling). | Q-NEW-AK's rate-limit half. Visibility now, mechanism later: the binding constraint is per-minute (450), not the daily budget (~75k, a rounding error against 380 calls). A full budget-meter/backoff subsystem was deliberately **not** built (Rule 2) — defer until it's needed at multi-league scale. Note: vendor budget headers *lag by a call*, so the header is a rough gauge, not an audit trail — `raw.api_responses` is the ledger. |
| D-088 | 2026-07-11 | **`--limit N` counts fixtures *processed*, not *visited*.** Already-ingested fixtures are skipped (via a skip-set on `curated.match_statistics.fixture_id`) *before* the limit check and before any fetch, so `--limit 1` always makes exactly one fixture call even on a resumed run — a useful retry/probe. Resumability rests on the per-fixture transaction (**2-rows-or-0**, never a partial fixture), so presence of any row ⇒ that fixture is complete. | Makes `--limit 1` a real probe rather than a no-op on resumed runs, and makes the whole loop crash-safe: verified when a **mid-run power loss** left 254 clean fixtures (508 rows, zero partials) and a plain re-run finished the remaining 126 with no cleanup. The skip happens before `_fetch`, so resumed runs waste no API budget. |
| D-089 | 2026-07-11 | **The `ON CONFLICT DO UPDATE` (re-sync) path is verified by re-upserting from the *landed raw row*, at 0 API calls** — not by re-calling the API. Proof pattern: row count stays flat, `upsert_returning_id` returns the *existing* surrogate ids, `created_at` preserved while `updated_at` advances (an INSERT would mint new ids + reset `created_at`; a no-op would leave `updated_at` still). | Leverages D-071: because normalization runs *from* the landed raw row, the fresh-call and replay paths are one code path, so replaying an old raw row exercises the exact production upsert for free. Same proof shape that validated the admin guardrail in Session 8 (D-079: value survives while `updated_at` advances). |

---

## 8. Open Questions

Questions that need answering before relevant sessions can run.

| ID | Question | Blocks | Owner | Status |
|---|---|---|---|---|
| Q-001 | What pricing model and tier-specific values (gating, limits)? | Stripe setup, feature gating configuration, pre-launch | User | Decide before "Stripe Integration" session |
| Q-002 | Backend hosting: Railway vs Fly.io? | Repo deployment config | User + Claude | ✅ Resolved Session 3 (D-043) — Railway |
| Q-003 | Domain name for the platform? | Branding, deployment | User | Not blocking yet |
| Q-004 | Background job system? (Celery vs Dramatiq vs Supabase Edge Functions) | Sync engine architecture | Claude (recommendation) | ✅ Resolved Session 3 (D-044) — Dramatiq + Railway cron |
| Q-005 | Will free users see ANY player props, or is it Pro-only? | Feature gating, Pro upgrade incentive | User | Deferred — Phase 2 launch |
| Q-006 | Multi-sport: which sport is realistically next after football? | Schema decisions for extensibility (already handled per D-039) | User | Not blocking — football-first is fine |
| Q-NEW-A | Specific filter availability per tier (which filters are anonymous, free, paid) | Filter gating values | User + Stratos | Open — admin-configurable per D-037 |
| Q-NEW-B | Trial length and re-trial mechanics (trial different tier later?) | Trial config | User | Open — admin-configurable per D-037 |
| Q-NEW-G | "Current season" detection logic (leagues span calendar years differently) | Filter engine implementation | Claude (architecture) | ⚙️ Architecture resolved Session 3 (D-045 — Season Resolver pattern); algorithm open for later implementation session |
| Q-NEW-H | "Auto-pick middle line" exact algorithm | Filter engine implementation | Claude (architecture) | ⚙️ Architecture resolved Session 3 (D-046 — Line Resolver pattern); MVP rule is deterministic middle; sophisticated algorithm Phase 2 |
| Q-NEW-I | Auto-scoring algorithm tuning UI (admin-configurable scoring weights) | Tier mapping (Phase 2) | User | Deferred |
| Q-NEW-O | Minimum edge threshold for Opportunities (default indicative ~5 pts) | Opportunities Engine | User | Open — admin-configurable |
| Q-NEW-Q | Methodology version handling when methodology changes | Opportunities Engine | Resolved — preserve old versions for historical consistency | Resolved |
| Q-NEW-R | Result Probabilities / narrative summary view (deferred from Scout Verdict) | Phase 2 product design | User + Stratos | Open — product design |
| Q-NEW-U | Operational log retention defaults | Operational setup | User | Admin-configurable |
| Q-NEW-V | Multi-source conflict resolution rule | Phase 2 (when secondary sources integrated) | User | Deferred |
| Q-NEW-W | Backup frequency and retention defaults | Operational setup | User | Admin-configurable |
| Q-NEW-X | Rate limit values per endpoint per tier | Gating values | User | Open — admin-configurable |
| Q-NEW-Y | Data residency / hosting region | Deployment | User + Claude | Decide before deployment |
| Q-NEW-Z | Cookie consent banner mechanism | Pre-launch compliance | User + legal | Product/legal decision |
| Q-NEW-AA | Geo-restriction launch policy | Pre-launch compliance | User + legal | Legal/product decision |
| Q-NEW-AB | Configuration Layer schema — typed value storage, validation rules, history tracking shape | A dedicated Configuration Layer schema session (NOT Session 4) | Claude | Open — confirmed in Session 4A that Configuration is its own later session, separate from the Curated schema work |
| Q-NEW-AC | Search index path — Postgres full-text at MVP; threshold for switching to external service (Meilisearch / Typesense / Algolia) | Phase 2 scaling | Deferred | Open — Postgres FT MVP; revisit at ~5K users |
| Q-NEW-AD | Read replica routing strategy — when to add replicas, how the application chooses replica vs primary | Phase 2 scaling | Deferred | Open — not needed until ~1K active users |
| Q-NEW-AE | Transactional email provider — Resend vs Postmark vs alternatives | Pre-launch engineering | Engineering decision | Open — not architectural |
| Q-NEW-AF | Methodology version registry shape — how versions are identified, parameter sets versioned, default selection | Opportunities Engine implementation session | Later session | Open — implementation-time concern |
| Q-NEW-AG | "Current league" for a team — keep the denormalized `current_league_id` convenience pointer, or introduce a full `team_league_seasons` participation table? | Team-related queries; possible later refinement | Claude + User | Open — denormalized pointer chosen for MVP (Session 4A); revisit if full participation history is needed |
| Q-NEW-AH | Coaches — keep the soft `coach_name` + `coach_source_ref` on `lineups`, or promote coaches to a `curated.coaches` entity later? | Coach-related features (none in MVP) | Claude + User | Open — soft fields chosen for MVP (Session 4B) |
| Q-NEW-AI | Odds capture cadence (how often the sync snapshots odds) + design of the post-kickoff job that resolves `computed.closing_odds` | Closing-odds accuracy; backtest quality | User (cadence) + Claude (job) | Open — operational / Computed-layer concern; raised in Session 4B |
| Q-NEW-AJ | Raw granularity at scale — keep one-row-per-API-call, or add per-entity raw tables when incremental diffing is built? | Full Raw-layer session | Claude | Open — per-call chosen for MVP (Session 6); revisit when diffing/archival is designed |
| Q-NEW-AK | Pagination + rate-limit/API-budget handling for high-volume endpoints (`/players`, `/odds`, per-fixture loops) | Sync worker implementation | Claude + User | ✅ **Resolved Session 9.** Pagination settled Session 8 (D-082). Rate-limit/budget handled (D-087): `--sleep` throttle (0.5s, conservative under the 450/min ceiling), `/status` pre-loop ceiling log, `last_headers` remaining-budget log (log-only, no branching), skip-set resumability. A full budget-meter/backoff subsystem was **deliberately deferred** (Rule 2) — revisit only if multi-league scale needs it. |
| Q-NEW-AL | EPL 2025 reports `cov_odds = false` — which league-seasons actually have odds coverage on API-Football, and how does that constrain D-023 (backtest needs real captured odds) and D-025 (historical odds backfill)? | Odds session; backtest viability | User + Claude | Open — surfaced in Session 7; check coverage before the odds work |
| Q-NEW-AM | Our ingested data is validated against the vendor itself. Do we want an independent spot-check against a non-API-Football source (at least for launch leagues) before go-live? | Data-quality / launch confidence | User | Open — surfaced in Session 7; pre-launch data-quality task |
| Q-NEW-AN | Raw landing and normalization currently share **one transaction per page**, so a normalization failure rolls back the raw audit row too — that payload then can't be replayed without re-calling the API. Do we split them (land-commit-then-normalize) for true replayability? | Full Raw-layer session (retry/replay semantics) | Claude | Open — surfaced in Session 8; not a regression (spine behaves the same). **Session 9 data point:** in `match_statistics`, `_fetch` commits its raw row in its own txn (survives) but a *parse* failure inside the per-fixture txn would roll back that fixture's raw row — the concrete instance of this question, and sharper here (18 typed fields = real parse-failure surface). When the split is designed it should apply to `fixtures.py` too, not just here. Revisit when archival/diffing is designed. |
| Q-NEW-AO | Should event-data workers populate a `source_extra` catch-all for unmodelled vendor fields (the "capture every field" principle, D-066-style)? The fixtures worker currently does **not** — the column map was explicit. | Per-table, during each event-data worker | Claude + User | ✅ **Closed for `match_statistics` (Session 9):** worker keeps the `source_extra` catch-all + logs any unmapped type; across all **380 EPL fixtures / 760 rows, zero unmapped types** → the 18 typed columns are exhaustive for API-Football *EPL* fixture statistics, so `source_extra` is NULL throughout. **Caveat: EPL-only; other leagues/competitions unverified** — keep the catch-all + logging on for every new league. Re-open the *general* question per table for `lineups` / `player_match_stats`. |
| Q-NEW-AP | When aggregating **count** stats, which measures must the Computed layer `COALESCE(...,0)` (vendor-`null`-means-zero) vs leave NULL (genuinely absent)? Curated stores vendor-`null` as NULL (D-086), so absent-vs-true-zero is preserved but must be resolved *per measure* downstream. | Computed-layer aggregation correctness (form snapshots, opportunities, any per-match rate over `match_statistics`) | Claude (Computed session) | **Open — new in Session 9.** Evidence from 760 EPL rows: `red_cards` 680/760 NULL (89% — naive `AVG`/`SUM` overstates the rate ~10× without COALESCE), `offsides` 42/760, while `xG`/`possession_pct`/`shots_blocked`/`goals_prevented` never NULL. Likely recurs on other count stats (saves, cards, blocked shots) in quiet matches. Decide per measure when the Computed layer is designed. |

---

## 9. Current Active Task

**Session 9: Sync Workers — `ingest_common.py` refactor + EPL-2025 `match_statistics`** — ✅ COMPLETE → **first per-fixture worker live; per-fixture cadence + crash-safe resume proven**

Two deliverables. **(1)** Executed the D-083 extraction: shared helpers moved into a neutral `backend/statesta_sync/ingest_common.py` (importing neither `spine` nor `fixtures`), `spine.py`/`fixtures.py` rewired, lazy import removed. Pure move — byte-identical bodies (AST-verified), circular import gone (verified *both* import orders), package-wide undefined-name pass clean. Commit `b48ab87`; `.gitattributes` added to pin LF everywhere (commit `89a66b3`). **(2)** New worker `backend/statesta_sync/match_statistics.py`: `GET /fixtures/statistics?fixture=<id>` per fixture → land raw → upsert `curated.match_statistics` on `(fixture_id, team_id)` (**two rows per fixture**, D-057), full 18-column fidelity incl. xG / goals_prevented (D-066), `source_extra` catch-all, all measures nullable (§6.7). Wired into `--entity match_statistics` (now a normal top-level import), `curated.match_statistics` registered in the admin guardrail (empty set). Commit `33ccf96`. Rulings locked: D-085 (parse rules), D-086 (null-count discipline), D-087 (rate-limit log-only), D-088 (`--limit` = processed), D-089 (DO-UPDATE via landed-raw re-upsert), D-084 (Supabase Pro trigger + baseline).

**Validation (all criteria met):** EPL (league 39) season 2025 → **380/380 fixtures, 760 rows** (exactly 2×380); **2-rows-or-0 invariant held across a mid-run power loss + plain resume** (254 clean fixtures at the cut, zero partials, finished the other 126 with no cleanup — crash-safety proven, not assumed); **zero orphaned FKs**; **zero unmapped types** across all 760 rows (Q-NEW-AO closed for EPL); **INSERT + DO-UPDATE both verified** (the update path via a 0-API-call re-upsert from the landed raw row — `created_at` preserved, `updated_at` advanced, ids stable); null census recorded (`red_cards` 680/760 NULL → Q-NEW-AP). `/status` confirmed the real ceiling is **450/min** (daily budget ~75k is a non-constraint).

*(Independent Supabase browser cross-check still offered / still deferred — optional, non-blocking.)*

**State of the schema:** Curated Layer = COMPLETE and APPLIED. Raw = minimal landing table live. **Ingestion pattern now proven across three layers** (static spine, first event-data table, first *per-fixture* worker) plus cross-run resolution *and* crash-safe resumability. Ingested so far: leagues, league_seasons, venues, teams, standings, fixtures, **match_statistics**. Not yet ingested: **players, lineups, player_match_stats, odds**. Still not designed: full Raw layer, Computed, User, Configuration. **D-084 size baseline: 13,454,483 bytes (13 MB); `raw.api_responses` largest at 784 kB / 391 rows** — the raw layer is the metric that will approach the 400 MB Pro trigger first.

*(Prior: 8 — fixtures ✅; 7 — spine ingestion ✅; 6 — ingestion design ✅; 5 — Infrastructure ✅; 4B/4A — schema ✅; 3 — Architecture ✅.)*

---

**Next session (10) — Recommended: `players` + `player_match_stats` via `/fixtures/players` (Claude Code):**

- **Goal:** ingest `curated.player_match_stats` for EPL 2025 — the next per-fixture worker — which in the same payload **seeds the `curated.players` entity** (D-064: players are team-agnostic; the per-match team lives on `player_match_stats`).
  1. **Standing first step (D-084):** run the DB-size check and report a plain verdict against the 13 MB baseline. This is now a permanent end-of-session ritual, but reading it at *start* too costs nothing.
  2. `GET /fixtures/players?fixture=<id>` per fixture → land raw → **(a)** upsert new players into `curated.players` (real vendor IDs → `source`/`source_ref`, D-049), **(b)** upsert `curated.player_match_stats` on `(fixture_id, player_id)` (D-057), full player stat block (D-066), `team_id` = the team the player turned out for *this match* (D-064). All measures nullable; reuse the D-085 parse rules; keep the `source_extra` catch-all + unmapped-type logging (Q-NEW-AO still open for this table).
  3. Reuse everything proven in Session 9: skip-set resumability, per-fixture 2-or-0 transaction, `--sleep`/`--limit`, `/status` + `last_headers` logging. Watch the `passes_accuracy` count-vs-percent ambiguity (CURATED_SCHEMA_REFERENCE §5.5 note) — store as-is, don't guess.
- **Why next:** it's the correct dependency order — `players` must exist before `lineups` can resolve player FKs (topological sort D-072), and `/fixtures/players` seeds players + stats in one payload. It also completes the Player-Props launch dataset (collected in MVP even though the UI is Phase 2, D-022). It introduces the **first two-table-per-fixture worker** (a new entity *and* a stat table from one call) — a genuinely new shape, so worth its own session.
- **Alternative if preferred (product call):** `lineups` via `/fixtures/lineups` (simpler, single table, but *also* needs players to exist first) — so `/fixtures/players` really does come first either way. Or defer per-fixture workers and extend `match_statistics` to a **second league** to exercise the Q-NEW-AO "EPL-only" caveat. Recommend the `/fixtures/players` worker.
- **Scope caution (Rule 2):** seeding a new entity (`players`) *and* a per-fixture stat table in one session is more moving parts than Session 9. If it feels like two deliverables, split: session 10 = players seeding + `player_match_stats`; keep it to one league (EPL 2025).
- **What to paste at session start:** PROJECT_STATUS.md, CRITICAL_RULES.md, REQUIREMENTS.md, ARCHITECTURE.md, `CURATED_SCHEMA_REFERENCE.md`, `SYNC_INGESTION_DESIGN.md`.
- **ClickUp (already done this session):** Session 9 task (`869e28z0d`) marked ✅ done; **Session 10 task already created** in Sync Engine (list `901217784130`) — `869e3awwx`, status backlog: "Session 10 — Ingest players + player_match_stats for EPL 2025 (`/fixtures/players`; seeds the players entity)". **Do not create a duplicate** — this task already exists; just mark it done at Session 10 close.

---

## 10. File Inventory

Every artifact produced by this project, in order. Living index.

| File | Session | Description | Status |
|---|---|---|---|
| `PROJECT_STATUS.md` | 1 (updated each session) | Master tracker (this file). Section 0 contains binding rules for Claude. **Paste at the start of every session.** | Active |
| `CRITICAL_RULES.md` | 1 | Short focused guardrails for Claude. **Paste at the start of every session, alongside PROJECT_STATUS.md.** | Active |
| `CLICKUP_STRUCTURE.md` | 1 | ClickUp setup instructions (one-time setup, reference only) | Active |
| `SESSION_WORKFLOW.md` | 1 | How chat sessions work (user-facing reference) | Active |
| `REQUIREMENTS.md` | 2 | Full functional spec (14 sections + executive summary). Authoritative for what the platform must do. **Paste at the start of Session 3+ alongside PROJECT_STATUS.md.** | Active |
| `ARCHITECTURE.md` | 3 | High-level architecture (11 sections, Mermaid diagrams). Three-service Shape B topology on Railway, four data layers + Configuration Layer, six cross-cutting patterns, four resolved decisions. **Paste at the start of Session 4+ alongside PROJECT_STATUS.md, CRITICAL_RULES.md, and REQUIREMENTS.md.** | Active |
| `001_curated_static.sql` | 4A | Curated static spine (design copy). Applied to hosted DB as `20260626120000_curated_static.sql` (D-070). | Applied (live) |
| `CURATED_SCHEMA_REFERENCE.md` | 4A–4B | Plain-language Curated schema reference (v0.2 — conventions + static + event entities + decisions). | Active |
| `002_curated_events.sql` | 4B | Curated event data (design copy). Applied to hosted DB as `20260626120100_curated_events.sql` (D-070). | Applied (live) |
| `CLAUDE.md` | 5 | Repo-root instructions auto-read by Claude Code every session (stack, conventions, migration rules, guardrails). Lives in repo root. | Active |
| `20260626120000_curated_static.sql` | 5 | Live migration (timestamped) in `supabase/migrations/`. | Applied (live) |
| `20260626120100_curated_events.sql` | 5 | Live migration (timestamped) in `supabase/migrations/`. | Applied (live) |
| `.gitignore` / `README.md` / `supabase/config.toml` | 5 | Repo scaffolding. `.gitignore` blocks secrets; `config.toml` holds only the project ref. | Active |
| `INFRA_SETUP_RUNBOOK.md` | 5 | Beginner step-by-step for repo + Supabase setup (reference; not committed to repo). | Reference |
| `SYNC_INGESTION_DESIGN.md` | 6 | Ingestion design (raw-first, FK-ordered chain, upsert/resolution, endpoint→table map, EPL-2025 slice spec). Committed to `docs/`. **Paste at implementation sessions.** | Active |
| `20260704165243_create_raw_api_responses.sql` | 7 | Live migration — `raw` schema + `raw.api_responses` landing table (+ 2 indexes). | Applied (live) |
| `backend/statesta_sync/` | 7 | Sync worker package: `config.py`, `api_football.py`, `db.py`, `smoke_test.py`, `raw_landing.py`, `upsert.py` (`upsert_returning_id` + `ResolutionMap` + `ADMIN_OWNED_COLUMNS` guardrail), `spine.py` (leagues/league_seasons/venues/teams/standings). Committed. | Active (proven) |
| `backend/requirements.txt` / `backend/.env.example` | 7 | Deps (`psycopg[binary]`, `httpx`, `python-dotenv`) + secrets template (key names only, no values). | Active |
| `backend/statesta_sync/fixtures.py` | 8 | First event-data worker: `/fixtures` → `curated.fixtures`. Raw-first, pagination loop (D-082), cross-run SELECT FK resolution, venue absent-not-invented (D-081), full nullable score breakdown (D-067). Committed. | Active (proven) |
| `backend/statesta_sync/spine.py` / `upsert.py` | 8 (updated) | `spine.py`: added `--entity fixtures` dispatch (lazy import, interim per D-083). `upsert.py`: registered `curated.fixtures` in `ADMIN_OWNED_COLUMNS` (empty set). | Active |
| `backend/statesta_sync/ingest_common.py` | 9 | Neutral shared-helpers module (D-083 executed): `SyncError`, `SOURCE`/`SPORT`, `_fetch`, `_land`, `_dig` (+ private `_api_ok`, `_Fetched`). Imports neither `spine` nor `fixtures` — kills the circular import at its root. Commit `b48ab87`. | Active (proven) |
| `backend/statesta_sync/match_statistics.py` | 9 | First **per-fixture** worker: `/fixtures/statistics` per fixture → `curated.match_statistics` on `(fixture_id, team_id)`, two rows/fixture. 18-column fidelity + `source_extra` (D-066); D-085 parse rules; D-086 null discipline; skip-set resume; 2-or-0 per-fixture txn; `--limit`/`--sleep` (D-088); `/status` + `last_headers` logging (D-087). Registered in the admin guardrail. Commit `33ccf96`. **Validated: 380/380 EPL-2025, 760 rows, survived power-loss + resume.** | Active (proven) |
| `backend/statesta_sync/spine.py` / `fixtures.py` / `api_football.py` / `upsert.py` | 9 (updated) | `spine.py` + `fixtures.py`: import helpers from `ingest_common`; `spine.py` now has a top-level `match_statistics` dispatch + `--limit`/`--sleep` (loop-only). `api_football.py`: `self.last_headers` added (D-087, signature unchanged). `upsert.py`: registered `curated.match_statistics` in `ADMIN_OWNED_COLUMNS` (empty set). | Active |
| `.gitattributes` | 9 | Repo-root file pinning line endings (`* text=auto eol=lf` + binaries marked) so on-disk bytes are identical on Windows / macOS / Linux CI. Commit `89a66b3`. | Active |

---

## 11. Glossary

Quick reference for terms we'll use across many chats.

- **OLTP** — Online Transactional Processing. The "live application" workload (logins, saves, fast small queries).
- **OLAP** — Online Analytical Processing. The "report and analytics" workload (large scans, aggregations).
- **RLS** — Row Level Security. PostgreSQL feature that enforces "users can only see their own data" at the database layer.
- **Service role key** — Supabase admin key that bypasses RLS. Used by backend only, never by frontend.
- **Anon key** — Supabase public key that respects RLS. Safe to use in frontend.
- **MVP** — Minimum Viable Product. The first launchable version with the smallest useful feature set.
- **Sync worker** — Background process that pulls data from API-Football into our database.
- **Raw layer** — Database tables storing the unmodified API responses for replayability.
- **Curated layer** — Normalized application tables built from raw responses.
- **Pre-computed KPI** — Statistic calculated once nightly and stored, instead of calculated at query time.
- **Form snapshot** — Per-team, per-as-of-date pre-computed form metrics. Avoids recomputation during filter evaluation.
- **Opportunities** — Per-fixture per-market value bets identified by the Opportunities Engine (platform hit rate vs bookmaker implied probability).
- **Best Bet** — The single highest-edge opportunity for a fixture (annotated on the Opportunities row).
- **Best Picks** — Platform-curated feed of high-edge opportunities across all upcoming matches.
- **Pre-built Strategy** — Admin-curated strategy in the strategy library; users can apply, copy, or backtest. `owner = system`.
- **Tier scope** — User's currently selected league tiers. Determines which matches count toward form samples and which appear in results.
- **Methodology version** — Version identifier of the platform's hit-rate methodology; stamped on computed opportunities so historical performance is consistent.

---

*Last updated: 2026-07-11 (end of Session 9 — `ingest_common.py` extracted; EPL-2025 `match_statistics` ingested & validated, 380/380 fixtures / 760 rows, survived a mid-run power loss + resume; DB baseline 13 MB)*
