# Statesta — REQUIREMENTS.md

**Document version:** 1.0
**Session produced:** Session 2 — Requirements Capture
**Date:** May 2026
**Status:** Structurally complete; ready to drive Session 3 (Architecture) and Session 4+ (Schema)

---

## Executive Summary

Statesta is a public, multi-user SaaS platform for **pre-match sports scouting and analytics** with paid subscriptions. Football at launch; multi-sport ready architecturally.

The platform answers two questions for serious bettors:
- *"Which upcoming matches meet historical performance criteria I care about?"* — the **Filter Engine** (user-driven, Match Analysis + Backtest).
- *"Which upcoming matches has the platform identified as having value?"* — the **Opportunities Engine** (system-driven, automatic per-fixture).

Users save filter strategies, build shortlists from results, combine selections into virtual accumulators, and validate strategies against historical data.

### What MVP delivers

- **Authenticated platform** with free, trial, and paid tiers (Stripe-backed). Trial requires no card. All gating is admin-configurable runtime data.
- **Match Analysis** — user-defined filter engine with 40+ metrics, scope by tier/country/league/season-completion-range, betting market & selection (with any-line resolution), tier-gated filter availability.
- **Backtest** — same filter engine applied to historical fixtures, **async background jobs** with progress reporting, queue, persistence, tier-based priority. Real captured odds only; no assumed-odd fallback.
- **Saved Strategies** — user-private and platform-curated (pre-built). Schema-versioned for forward compatibility.
- **Event Page, Team Page, League Page** — multi-view analytical destinations with per-view tier gating.
- **Opportunities Engine** — per-fixture per-market hit-rate vs implied-probability, edge identification, Best Bet annotation. Deterministic, explainable, methodology-versioned.
- **Best Picks** — algorithmic curated feed across all upcoming matches.
- **Shortlist & Accumulators** — user collection of saved selections grouped by saved strategy, combinable into virtual accumulators. No real-money handling.
- **Search** — unified across matches (upcoming + completed), teams, leagues, with per-user search history.
- **Player Props module is Phase 2.** Data (lineups, player_match_stats) collected from launch; user-facing surfaces deferred.

### Architectural commitments

Four commitments are load-bearing for everything downstream:

1. **Everything is configuration, not code (D-037).** Every gate, limit, threshold, label, methodology coefficient, tab availability, retention window is admin-tunable runtime data. No deploy required to adjust.
2. **Pre-computation over real-time calculation.** Team form snapshots (D-016), per-fixture opportunities (D-030) are computed nightly in the background. User-facing reads are indexed lookups.
3. **Async execution for heavy workloads.** Backtests run as background jobs with queue, progress, persistence, tier priority (D-017–D-020). Never block the request thread.
4. **Multi-sport ready from day one (D-039).** Every plausibly-sport-specific entity carries a `sport` column. MVP queries filter to `football`; adding a sport in the future doesn't require schema migration.

### Tier ladder (league/competition classification)

Eight user-facing tiers (admin-managed mapping): top, medium, low, very_low, women, youth_reserves, cup_domestic, friendlies. Plus `?` for unmapped (admin review queue). Default user scope: all tiers ON except friendlies.

### User access principle

All users see all leagues, all upcoming and completed matches, all teams. Tier-gating happens **inside** the analytical surfaces (which tabs, which filters, which features), not at the discovery layer.

### What's explicitly out of scope

No bet placement. No real-money handling. No live in-play features. No social/community features. No native mobile apps in MVP (Phase 3+). No public API for third-party developers. No human-curated tipster content. No automated decision-making for users.

### Status at end of Requirements

- **42 decisions logged** in PROJECT_STATUS.md. Most consequential: the four architectural commitments above, plus the gating mechanism (Section 3), the Opportunities Engine methodology requirements (4.6), and the eight-tier ladder (4.2).
- **22 open questions remain**, most resolvable as admin-configurable values at launch (Q-001 pricing is the big one). None block Sessions 3 or 4 from starting.
- **Document is structurally complete.** Schema and architecture sessions can begin without additional requirements work.

---

## 1. Purpose & Scope

### 1.1 What this document is

This is the **authoritative requirements specification** for Statesta — the public, multi-user SaaS evolution of the local v2.7 tool.

It defines:
- Who uses the platform (user roles)
- What they can do (functional requirements)
- What rules govern those actions (business rules, edge cases)
- What pages and endpoints exist to support those actions
- What is explicitly *not* in scope

All downstream artifacts — architecture, schema, API design, UI design, ClickUp tasks — must serve these requirements. If a future artifact conflicts with this document, **this document wins** and the conflict is raised as an open question.

### 1.2 What this document is not

It is deliberately not:
- **Architecture** — no decisions about services, queues, hosting topology, or data flow (Session 3).
- **Schema** — no table designs, column lists, or relationships (Session 4+).
- **API design** — no request/response shapes, status codes, or auth header formats. Section 10 lists *which* endpoints must exist, not *how* they look.
- **UX/visual design** — no wireframes, no styling, no copy. Section 9 lists pages by what the user accomplishes on them; Stratos's designs will dress them up later without changing the inventory.
- **Implementation plan** — no estimates, no sprint planning, no ordering of work beyond the MVP/Phase 2/Future tags.

If a question is "should we use X technology?" or "what does the screen look like?" — it doesn't belong here.

### 1.3 Sport scope

**MVP is football-only.** All other sports are Future.

However, every requirement in this document — schema constraints, API endpoint naming, user-facing language, filter logic — must be expressed in a way that **does not assume football**. If a requirement only makes sense for football (e.g., "corners filter"), it is tagged as football-specific so future-us knows it lives inside a sport-pluggable system, not at the platform's core.

This mirrors the v2.7 principle: `sport` column on every relevant table, default `'football'`. v3 carries this forward and extends it to API routes and feature definitions.

### 1.4 Phasing convention

Every functional requirement in Sections 4, 5, and 9 carries one of three tags:

| Tag | Definition |
|---|---|
| **MVP** | Must exist on day one of public launch. Day-one launch includes working auth, billing, core filter engine, and at least one paid tier working end-to-end. A missing MVP feature blocks launch. |
| **Phase 2** | Built after launch, before "v3 is considered complete." No fixed timeframe. Typically features needing real user feedback to design well, or that depend on data we don't have on day one. |
| **Future** | Beyond Phase 2. Captured here so the schema and architecture don't actively prevent them, but no commitment to build. Multi-sport expansion, social features, mobile apps fall here. |

A feature being tagged `Future` does **not** mean "ignore it." It means "build today's foundation in a way that doesn't make this impossible tomorrow." This is the same principle that drove v2.7's `sport` column.

### 1.5 Open question handling

Some requirements depend on decisions not yet made (e.g., final pricing tiers per Q-001, player props gating per Q-005). Rather than block this document, those requirements are written as **configurable** rather than hard-coded:

> Example: "Free users have access to the player props module" is *not* an answer. The answer is "the player props module is gated by a subscription tier flag whose value is configurable per environment." When Q-005 resolves, the value is set; no schema or code change required.

Section 14 (Open Questions Index) cross-references every such configurable requirement back to the PROJECT_STATUS.md open question that drives it.

### 1.6 Audience

Primary readers:
- **Alex (architect/developer):** uses this doc to drive every downstream session and to push back when an implementation creeps outside scope.
- **Future-Claude (architect chat):** uses this doc as the source of truth for schema, architecture, and API design sessions.
- **Claude Code (engineer):** uses this doc — via the specs derived from it — to know what to build.
- **Stratos (designer):** uses Section 9 (Pages & Flows) to scope his design work.

Not in the audience: end users, marketing copy, investor pitches. Don't write for them here.

### 1.7 Maintenance

This document is **version-controlled** alongside PROJECT_STATUS.md. When a requirement changes:
1. Update the relevant section here.
2. Log the change as a decision (D-XXX) in PROJECT_STATUS.md Section 7.
3. If the change cascades (e.g., affects schema), note it in the relevant session log.

Requirements drift silently is one of the top failure modes of long projects. This rule prevents it.

---

## 2. User Roles

### 2.1 Role overview

| Role | Authenticated? | Pays? | MVP? |
|---|---|---|---|
| Anonymous Visitor | No | No | MVP |
| Free User | Yes | No | MVP |
| Paid User | Yes | Yes | MVP |
| Admin | Yes | N/A (internal) | MVP |
| Sync Worker (system) | N/A (service credential) | N/A | MVP |

"Paid User" is intentionally singular here — at the role level there's just *one* paid concept. Multiple paid tiers (Pro, Elite, etc.) are a **subscription tier** layered on top, handled in Section 3.

### 2.2 Anonymous Visitor — MVP

**Who:** Anyone with the URL who hasn't logged in.

**Can:**
- View public marketing pages (landing, pricing, about, terms, privacy).
- View league pages, match/event pages, and team pages (read-only public data: fixtures, scores, basic standings, team rosters).
- Run filter analysis with a restricted basic filter subset — the user can experience the core engine, but with limited filter options to encourage signup. Exact filter inclusion is admin-configurable.
- View a configurable teaser of player props data — scope governed by Q-005.
- Sign up for an account.
- Log in to an existing account.
- Initiate password reset.

**Cannot:**
- Access the full filter set (only the basic subset).
- Run backtests.
- Save anything (no shortlists, accumulators, saved strategies).
- View any user-specific or admin data.

**Identified by:** No identity. Tracked only by session cookie / IP for rate-limiting purposes (Section 7).

**Key design implication:** Filter availability is **per-filter configurable**, not a single boolean. Each filter has an attribute indicating the minimum tier required to use it (`anonymous`, `free`, `paid:pro`, `paid:elite`, etc.). Q-NEW-A and Q-005 can both resolve later by adjusting flags — no code or schema rebuild required.

### 2.3 Free User — MVP

**Who:** Anyone who has signed up but has no active paid subscription.

**Can:**
- Everything an Anonymous Visitor can do.
- Manage their own profile (display name, email, password, account deletion).
- Access the expanded filter set available to free users (larger than anonymous, smaller than paid).
- Access whichever other features are configured as free-tier-accessible in Section 3.
- See upgrade prompts when they hit a free-tier limit.
- Initiate a paid subscription via Stripe checkout.
- Start a free trial of paid features (no card required — see Section 3).

**Cannot:**
- Access features configured as paid-only (except during an active trial).
- Exceed free-tier limits (saved strategies count, backtest history retention, etc.).
- Access admin functions.

**Identified by:** Supabase Auth user ID (`auth.uid()`). All their data is row-level-secured to this ID.

**Lifecycle considerations:**
- Account creation flow must capture: email, password (or OAuth), optional display name, acceptance of terms.
- Account deletion is **soft delete by default** — grace period and GDPR hard-delete handling per Section 11.
- Free user has no payment method on file.

### 2.4 Paid User — MVP

**Who:** A free user who has activated a paid subscription (any tier) and whose subscription status is `active` or `trialing`.

**Can:**
- Everything a Free User can do.
- Access features configured as paid-tier-accessible in Section 3, scoped to their specific tier.
- Manage their subscription: view current plan, upgrade/downgrade, view billing history, update payment method, cancel.

**Cannot:**
- Bypass tier-specific gating. A Pro user cannot access Elite features even if they "could just click through" — gating is server-enforced.
- Access admin functions.

**Identified by:** Same Supabase Auth user ID as Free User. Subscription status determined by joining to a subscription record (Stripe sync state).

**Lifecycle considerations:**
- Status transitions tracked:
  - `trialing` → `active` (trial converted, payment method added)
  - `trialing` → `free` (trial expired without conversion — user reverts to Free, no charge)
  - `active` → `past_due` (payment failed, grace period)
  - `past_due` → `canceled` (grace period exhausted)
  - `active` → `canceled` (user-initiated cancellation, retains access until period end)
  - `canceled` → `active` (resubscribe)
- A `canceled` user with time remaining on their paid period **still has paid access** until period end. Then they become a Free User again, without losing their account or their saved data.
- **Downgrade behavior (soft-cap):** existing data is not deleted. They can read all of it, but cannot create new items above the new limit until they're under it.

### 2.5 Admin — MVP

**Who:** Internal team members. **Initial admins: Alex and Stratos.** The admin model is designed so adding or removing admins is a database flag change, not a code change.

**Can:**
- View any user account (read-only) for support purposes.
- Manage subscription overrides (grant complimentary access, refund, manual cancel).
- View platform-wide observability: sync job health, API budget consumption, error logs, user growth metrics.
- Trigger manual syncs (e.g., re-sync a specific league or fixture).
- Manage league tier assignments (override auto-assigned tiers).
- Manage feature flags (the configurable gating values — filter availability per tier, player props teaser scope, etc.).
- Read but not modify user-private data (saved strategies, shortlists) — unless explicitly needed for support and logged.

**Cannot:**
- Impersonate a user without an audit log entry.
- Modify user-generated content silently.
- Bypass payment for their own personal use without it being logged as a complimentary grant.

**Identified by:** Same Supabase Auth user ID, but with a server-side admin flag stored in the database. **Admin status is never determined by the client.**

**Phasing nuance:** A minimal admin capability is MVP because you need *some* way to handle support tickets, refunds, and broken syncs on day one. A full admin dashboard with charts and bulk operations is Phase 2.

**MVP admin capabilities (minimum):**
- View user account by email/ID.
- Trigger manual sync for a league or fixture.
- View sync job status and recent errors.
- Grant/revoke complimentary subscription.
- Toggle feature flags (MVP version may be via env vars or a minimal config UI).

**Phase 2 admin capabilities:**
- Bulk operations.
- Analytics dashboards.
- User impersonation with audit log.
- Full feature flag UI.

### 2.6 Sync Worker (System) — MVP

**Who:** Backend processes that pull data from external data sources and write to the database. Not a human.

**Can (MVP):**
- Read and write to all raw and curated data tables.
- Update sync job status, log entries, and API budget counters.
- Trigger downstream computational workflows.
- Make outbound calls to API-Football and internal infrastructure only.

**Can (Future expansion — captured for architectural foresight):**
- Make outbound calls to additional external data providers (dedicated odds providers, affiliate/bookmaker APIs). The sync architecture must support **pluggable data sources** rather than a hardcoded API-Football client. Adding a new data source should be a matter of writing a new source adapter, not refactoring the sync engine.

**Cannot (always, including future):**
- Read or write user-private data (saved strategies, shortlists, accumulators, profiles).
- Make outbound calls to anything other than approved data providers and internal infrastructure.

**Identified by:** Service-role credential (Supabase service role key, used only by backend). **Never exposed to any frontend.**

**Why this is a "role":** The sync worker's credential, if leaked, must not be able to read user data. This is enforced at the database level (RLS policies separate user-data tables from operational-data tables) and at the network level.

### 2.7 Roles explicitly *not* in scope for MVP

- **Team/organization accounts.** No "company A has 5 seats." Single-user accounts only.
- **Affiliate / referrer role.** No referral program in MVP.
- **API consumer (third-party developer).** No public API for our customers to build on top of in MVP.
- **Tipster / content creator role.** No "share my strategy publicly and earn revenue" role.
- **Moderator role.** No user-generated content needing moderation in MVP.

All of the above are **Future**. The auth model (Supabase Auth + a `users` table) does not preclude any of them; they just aren't built.

---

## 3. Subscription Tiers & Feature Gating

### 3.1 Why this is a separate section

Roles (Section 2) define *what a user fundamentally is*. Tiers define *how much they get*. Keeping these separate matters because:
- A single role (Paid User) can have many tiers (Pro, Elite, future tiers).
- A user's tier can change frequently (upgrade, downgrade, trial expiry); their role rarely changes.
- The schema treats them differently: role is a property of the user record; tier is a property of their active subscription record.

### 3.2 The tier ladder (structure, not values)

| Level | Identifier | Authenticated? | Paid? |
|---|---|---|---|
| 0 | `anonymous` | No | No |
| 1 | `free` | Yes | No |
| 2 | `trial` | Yes | No (during trial window) |
| 3+ | `paid:<tier_name>` | Yes | Yes |

- **The number of paid tiers is configurable, not hardcoded.** MVP might launch with one paid tier (`paid:pro`). Q-001 might later resolve to two (`paid:pro`, `paid:elite`) or three.
- **`trial` is a pseudo-tier**, not a real one. On trial end, user drops back to `free`.
- **Levels are ordered. Each higher tier is a strict superset of the lower.** A feature available at level N is automatically available at all levels > N.
- **`anonymous` is treated as a tier** for gating purposes. One mechanism, not two.

### 3.3 The gating matrix — mechanism

| Gate type | What it controls | Stored as |
|---|---|---|
| **Feature gate** | Whether the entire feature is accessible | A flag on the feature definition |
| **Filter gate** | Which individual filters within the filter engine are available | A flag on each filter definition |
| **Quantitative limit** | How much of something you can have | A per-tier numeric limit |
| **Data scope gate** | Which slice of data is visible | A per-tier scope definition |
| **Rate limit gate** | How many requests per time window | A per-tier rate limit |

**Critical design rule:** the **gating values must live in configuration (database or config table), never hardcoded in application code.** The mechanism in code reads the configuration and applies it.

### 3.4 What gets gated — the inventory

| Gate | Type | What it controls |
|---|---|---|
| `feature.match_analysis` | Feature | Access to filter analysis module |
| `feature.backtest` | Feature | Access to the backtest module |
| `feature.player_props` | Feature | Access to player props module (Phase 2) |
| `feature.player_props_teaser` | Feature | Teaser preview for non-eligible tiers |
| `feature.saved_strategies` | Feature | Access to save/load strategies |
| `feature.shortlist` | Feature | Access to shortlisting feature |
| `feature.accumulators` | Feature | Access to in-app accumulator building |
| `feature.event_page.<view_id>` | Feature | Per-view gating on Event Page (per 4.6) |
| `feature.team_page.<view_id>` | Feature | Per-view gating on Team Page (per 4.7) |
| `feature.league_page.<view_id>` | Feature | Per-view gating on League Page (per 4.7) |
| `feature.best_picks` | Feature | Access to Best Picks feed |
| `feature.pre_built_strategies` | Feature | Access to pre-built strategy library |
| `filter.<filter_id>.min_tier` | Filter | Minimum tier to use each individual filter |
| `limit.saved_strategies` | Limit | Max strategies a user can save |
| `limit.shortlist_items` | Limit | Max items in a user's shortlist |
| `limit.accumulator_legs` | Limit | Max legs per accumulator |
| `limit.saved_accumulators` | Limit | Max saved accumulators per user |
| `limit.backtest_months` | Limit | How far back a backtest can run |
| `limit.backtest_history_retention` | Limit | How many past backtests retained per user |
| `limit.best_picks_visible` | Limit | How many Best Picks visible per tier |
| `priority.backtest_queue` | Priority | Queue priority for backtest jobs |
| `rate.filter_analyses_per_hour` | Rate | Filter analysis requests per hour |
| `rate.backtests_per_hour` | Rate | Backtest requests per hour |
| `rate.player_searches_per_hour` | Rate | Player searches per hour |

Every entry resolves to a value per tier when the open questions are answered. Until then, the system must support querying *any* of these for *any* tier, and getting back a real answer (even if "unlimited" or "blocked entirely").

### 3.5 Enforcement — server-side, always

Every gate must be enforced **server-side**. The client may *also* hide gated features for UX reasons, but the server is the source of truth.

- The frontend can render an "Upgrade to Pro" button instead of a backtest button — but if someone bypasses the UI and calls the backtest API directly, the API returns 403.
- Filter availability is enforced in the filter engine itself, not just in the filter picker UI.
- Quantitative limits are enforced at the database write — the API rejects a "save strategy" call if the user is at their limit.

This is non-negotiable for a paid product. UI-only gating is bypassable in 30 seconds with browser dev tools.

### 3.6 Trial mechanics — MVP

**Free trial, no card required.**

**Trial structure:**
- Any free user can start a trial of a paid tier.
- Trial length is configurable (TBD per Q-NEW-B; system supports any value).
- During trial, user has access at the level of the trialed tier.
- At trial end, user reverts to `free` automatically. No charge. No card to charge anyway.
- To continue with paid access, user must add a card and convert.

**Trial restrictions (to prevent abuse):**
- **One trial per account.**
- **One trial per email address.**
- **Phase 2 anti-abuse:** device fingerprinting, IP-based heuristics. Not MVP — accept some abuse as the cost of card-free trials at launch.

**Trial state on the user:**
- `trial_started_at` (timestamp)
- `trial_ends_at` (timestamp)
- `trial_tier` (which tier they're trialing)
- `has_used_trial` (boolean, persists after trial ends)

These are properties on the subscription record, not the user record.

### 3.7 Plan changes — handling rules

| Change | Effective when | Billing implication |
|---|---|---|
| **Free → Trial** | Immediately | None (no card) |
| **Trial → Paid (any tier)** | Immediately on payment success | Charged in full for the new period |
| **Trial → Free (expiry)** | At `trial_ends_at` | None |
| **Free → Paid** | Immediately on payment success | Charged in full |
| **Paid Upgrade** | Immediately | Prorated charge for the remaining period (Stripe default) |
| **Paid Downgrade** | At end of current period | No immediate charge; new price applies next cycle |
| **Cancel** | At end of current period | No immediate charge; reverts to Free at period end |
| **Resubscribe after Cancel** | Immediately on payment success | Charged in full for new period |

### 3.8 Stripe-side vs database-side state

Stripe is the **source of truth for billing state**. Our database is the source of truth for **what the user currently has access to**. These two must stay in sync via webhooks.

**Webhook events the system must handle (MVP):**
- `checkout.session.completed` — user started a subscription
- `customer.subscription.updated` — plan change, status change
- `customer.subscription.deleted` — subscription ended
- `invoice.payment_succeeded` — renewal succeeded
- `invoice.payment_failed` — renewal failed, enters `past_due`
- `customer.subscription.trial_will_end` — 3 days before trial end (Phase 2 for notifications)

**Failure mode this prevents:** user's Stripe subscription gets canceled, our database doesn't update, user retains access for weeks. Webhook handling is **not optional** even for MVP.

### 3.9 Phasing

| Capability | Phase |
|---|---|
| Configurable gating mechanism | MVP |
| Anonymous, Free, and at least one Paid tier working end-to-end | MVP |
| Free trial (no card) for one paid tier | MVP |
| Stripe checkout, webhook handling, billing portal | MVP |
| Per-filter gating | MVP (mechanism); values configurable later |
| Multiple paid tiers | MVP if Q-001 resolves before launch; otherwise Phase 2 |
| Promotional codes, discounts | Phase 2 |
| Annual billing | Phase 2 |
| Lifetime tier, gift subscriptions | Future |
| Team/multi-seat billing | Future |

### 3.10 Open questions cross-reference

- **Q-001** — final pricing tiers and per-tier limits.
- **Q-005** — free-tier visibility of player props.
- **Q-NEW-A** — which filters are available at which tier.
- **Q-NEW-B** — trial length, whether trialing different tiers is allowed.

None block the *design* of Section 3. They block the *values* loaded into the gating configuration at launch.

---

## 4. Functional Requirements — Core Analytics

### 4.1 Match Analysis (Filter Engine) — MVP

The foundation of the entire platform. Answers: *"Of all upcoming matches, which ones meet a set of historical performance criteria I care about?"*

#### 4.1.1 What the user can do

- Build a set of filters, each expressing one historical performance criterion.
- Combine multiple filters into a strategy (filters combined by counting how many pass per match — a "score").
- Set a minimum score threshold.
- Define a betting strategy (Betting Market + Selection) the match is being analyzed for.
- Scope analysis by league tier, country, specific leagues, league completion range, days ahead.
- Optionally restrict to matches with available odds for the chosen strategy.
- Run the analysis and see matches sorted by score.
- Inspect each match — pass/fail breakdown per filter, underlying numbers.
- Save the filter set as a Strategy (per 4.5).
- Send the filter set to the Backtest module (per 4.3) — same filter definition reused, not rebuilt.

#### 4.1.2 Filter anatomy

Every filter answers: *"Did [home/away] team have [metric] [operator] [threshold] in [≥/≤] [pct]% of their last [N or current season] [overall/home/away] matches?"*

| Parameter | Type | Description |
|---|---|---|
| `apply_to` | enum | `home` or `away` |
| `metric` | enum | Which performance metric (per 4.1.3) |
| `operator` | enum | `gte` (≥) or `lte` (≤) |
| `threshold` | number | The value the metric must hit |
| `sample` | int (1–40) or `"season"` | Recent matches count, or all of team's current season |
| `split` | enum | `overall`, `home_only`, `away_only` |
| `pct_operator` | enum | `gte` or `lte` |
| `pct_value` | int (0–100) | Hit-rate threshold |

The `sample = "season"` mode requires the platform to resolve "the team's current season" reliably. Captured as Q-NEW-G for architecture session.

#### 4.1.3 Available metrics (MVP)

Ported from v2.7. Each metric is data, not code (a row in a `metrics` table with id, name, category, unit, computation formula reference, minimum tier).

| Category | Metrics |
|---|---|
| Goals | Scored, conceded, total goals, BTTS, clean sheet, scored 2+/3+, over 2.5/3.5/4.5, won/lost to nil, goalless draw |
| Results | Win, draw, loss, points earned |
| Form | Weighted form (recency-weighted pts/game), unbeaten streak, winning streak |
| Half Time | Goals scored HT, goals conceded HT, total HT, BTTS HT, winning at HT |
| Corners | Corners for, corners against, corners total |
| Cards | Yellow cards, total cards, 3+ cards in match |
| Shots | Shots total, shots on target |
| Possession | Possession percentage |
| Opponent Quality ⚠ | Win/draw/loss/scored/clean sheet/over 2.5/BTTS vs top half or bottom half |

**Opponent quality proxy warning** — same as v2.7. ~90% accurate mid-to-late-season, degrades early-season. Filters using these metrics must be visually flagged.

#### 4.1.4 Strategy (Betting Market + Selection)

A strategy has three components:

| Component | Description |
|---|---|
| `betting_market` | The market category (Match Winner, Goals Over/Under, etc.) |
| `selection` | The specific outcome within the market |
| `line_mode` | For line-based markets: specific line OR "any line — auto-pick middle" |

**For line-based markets:**
- **Specific line mode:** user picks one line. System matches only fixtures with odds on that exact line.
- **Any-line mode:** user picks a direction. System matches fixtures with odds on *any* line within the **Allowed Lines whitelist**.
  - Empty whitelist or "Any" pill = all lines eligible.
  - Multiple eligible lines with odds → system **picks the middle line** for that fixture.
  - Only one eligible line → that one is used.

**Specific line and any-line modes are mutually exclusive.**

**Data model implication:** the system must store odds for **every line of every market**, not just one canonical line per market.

Auto-pick middle for MVP: deterministic middle-of-available-eligible-lines. Sophisticated probability-weighted picker is Q-NEW-H (Phase 2 or Future).

#### 4.1.5 Scope parameters

| Parameter | Description | Default |
|---|---|---|
| `days_ahead` | How many days ahead (1–14) | 7 |
| `min_score` | Minimum filters-passed threshold | 1 |
| `tiers` | Which league tiers to include | Per user tier defaults |
| `countries` | Optional filter by country | All |
| `league_ids` | Optional filter by specific leagues | All |
| `league_completion_min` | Lower bound of season completion % | 50 |
| `league_completion_max` | Upper bound of season completion % | 100 |
| `odds_only` | Only matches with odds available for the strategy's selection | false |

**Why `_min` / `_max` matters:** early-season samples are thin; late-season samples are distorted (relegated teams field reserves, mid-table teams have nothing to play for). Bracketing both bounds gives users control over data quality.

#### 4.1.6 Outputs

| Field | Description |
|---|---|
| Match metadata | Fixture ID, date/time (UTC + user's timezone), league, country, tier |
| Teams | Home and away (ID, name, logo) |
| Score | Number of filters passed |
| Score band | Green (≥80%), Amber (50–79%), Red (<50%) |
| Filter breakdown | Per-filter passed/failed, actual value, threshold |
| Odds | Per strategy market/selection/line; the actual decimal odd if available |
| Resolved line | When in any-line mode, which line was picked |
| Actions | Save to Shortlist, View Team, View Match |

#### 4.1.7 Business rules

- **Filter with insufficient sample auto-fails.**
- **`home_only`/`away_only` split requires ≥50% of requested sample** in that split.
- **`sample = "season"`** uses all team's current-season matches that are not friendlies. Minimum 3 matches required.
- **Matches with status `abandoned`, `postponed`, `cancelled`, `awarded`** excluded from both history and upcoming.
- **Half-time stats required for HT filters.** Matches without HT data excluded from those filters' samples only.
- **Friendlies excluded from form calculations by default** via tier-scope rule (per 4.2.5). Continental club competitions and cup competitions are **not** friendlies; they count toward form when their tier is in scope.
- **Results capped** at `limit.match_filter_results` per user's tier.

#### 4.1.8 Edge cases

- **Team transferred between leagues mid-season.** History follows the team across leagues.
- **Newly promoted teams.** History spans leagues; uses most recent N matches.
- **Penalty shootouts and extra time.** ET goals count toward "goals scored"; shootout goals don't (football statistical convention).
- **Mid-season league restructure.** Affects standings-proxy filters. Documented limitation; no special handling for MVP.
- **Lineup unavailable.** Match still appears; filters evaluate normally.
- **League with no standings data.** Opponent-quality proxy filters auto-fail for that match.
- **Any-line strategy mode with no odds.** Match excluded when `odds_only=true`; included with "no odds" indicator otherwise.

#### 4.1.9 Performance requirements

| Workload | Target (p95) |
|---|---|
| Typical query (one tier, 7 days, ≤10 filters, ~200 candidates) | < 3 seconds |
| Heavy query (multiple tiers, 14 days, 20+ filters, thousands of matches) | < 10 seconds |

**Pre-computation required:** v2.7's `team_form_stats` equivalent must port to v3, refreshed nightly.

#### 4.1.10 Caching

- Results cached server-side keyed by `(filter set hash, scope hash, strategy hash, user tier)`.
- TTL: **1 hour.**
- Cache is **not user-specific** — two users with identical inputs share.
- Invalidated on relevant data writes (new fixture sync, odds update).

#### 4.1.11 Phasing

| Capability | Phase |
|---|---|
| Filter engine with all v2.7 metrics | MVP |
| `sample = "season"` mode | MVP |
| Strategy with market + selection + line mode | MVP |
| Any-line mode with allowed-lines whitelist | MVP |
| All scope parameters incl. completion range | MVP |
| Filter breakdown per match | MVP |
| Send filter set to Backtest | MVP |
| Save filter set as Strategy | MVP |
| Opponent quality proxy warning | MVP |
| Sophisticated middle-line logic | Phase 2 or Future (Q-NEW-H) |
| New metrics beyond v2.7 (xG, set pieces) | Phase 2 |
| Boolean expression filters (AND/OR) | Future |
| User-defined custom metrics | Future |

### 4.2 League Tier System — MVP

The primary scope filter across every analytical module. Groups leagues and competitions into eight user-facing tier buckets.

v2.7 used pure auto-scoring. v3 keeps auto-scoring as a baseline but introduces **human-overridable, admin-managed mapping** as a first-class concern.

#### 4.2.1 What the user can do

- Filter analyses and backtests by tier — multi-select across every relevant scope.
- See tier counts (each pill shows how many leagues in that tier).
- Default tier selection per user tier; the tier filter itself is gated.
- **`friendlies` is OFF by default; all other 7 tiers are ON by default.** Users opt in to friendlies.

#### 4.2.2 What the admin can do

- View all leagues with current tier assignment, country, metadata.
- Override any league's tier manually. Persistent; survives re-sync.
- See a queue of unmapped or recently-discovered leagues for review.
- Approve, override, or reject queue entries.
- Audit trail of tier changes (data captured MVP; UI Phase 2).

#### 4.2.3 The tier ladder

| Tier ID | Label | Contents |
|---|---|---|
| `top` | Top | Top domestic divisions + continental club (UCL, Europa, Conference, Copa Libertadores, Sudamericana) + elite international (World Cup, Euros, Copa América, Nations League) |
| `medium` | Medium | Second domestic divisions |
| `low` | Low | Third domestic divisions |
| `very_low` | Very Low | Regional, fourth-tier, non-league |
| `women` | Women | All women's football, all levels |
| `youth_reserves` | Youth/Reserves | Youth, academy, U-age, reserve teams, B teams |
| `cup_domestic` | Cup | Domestic cup competitions |
| `friendlies` | Friendlies | Club friendlies, pre-season tournaments, international friendlies between nations |
| `?` | Unmapped | New leagues awaiting admin review — not visible to users until tier assigned |

- **Tier identifiers are strings**, not integers. Self-explanatory pill labels; survives future re-ordering.
- **Eight user-facing tiers** is the right balance.
- **`?` is a real value**, not null.

#### 4.2.4 Auto-scoring algorithm

The auto-scoring algorithm runs on new leagues entering the system. It outputs a **suggested tier** but **never overrides an admin-set tier**. Once a human touches a league's tier, the algorithm leaves it alone.

#### 4.2.5 Business rules

- Every league has exactly one tier at any time.
- **Tier filtering is the universal mechanism for "what counts as form."** A match counts toward a team's form sample if and only if its league's tier is in the user's currently selected tier scope.
- Newly-discovered leagues default to `?` and are excluded from user queries.
- Current tier governs filtering (a league moved to `top` makes all its historical matches count as `top` matches).
- Tier-gating at user level (Section 3) applies after tier mapping.
- Every admin tier change records who, when, from-tier, to-tier, optional note.

#### 4.2.6 Edge cases

- League that ceases to exist mid-season → tier remains; `is_active = false`.
- Same competition split across multiple league IDs by API-Football → admin manually corrects.
- Reserve leagues that occasionally contain first-team players → tier stays as `youth_reserves`.
- Newly-promoted team's old fixtures → kept under league's actual tier; team's history crosses tiers naturally.

#### 4.2.7 Operational implications (Sync engine)

The sync engine must:
- Detect newly-appeared leagues on every sync run.
- Run auto-scoring; populate `suggested_tier`.
- Insert new leagues with `tier = '?'`.
- Surface in admin review queue.
- Never overwrite admin-set tier without explicit admin action.

#### 4.2.8 Migration path from v2.7

When v3 launches with the existing v2.7 dataset:
- Auto-map v2.7's 1–9 tiers to v3's 8-tier system per known mappings (T1→top, T2→medium, T3→low, T4→very_low, T7→youth_reserves, T8→women, T9→youth_reserves; cups and friendlies detected via API-Football competition type).
- Every auto-mapped entry flagged `needs_review = true` for admin validation.
- Admin review queue at launch will be large (~1,200 leagues). Plan accordingly.

#### 4.2.9 Phasing

| Capability | Phase |
|---|---|
| Eight-tier ladder + `?` unmapped state | MVP |
| Auto-scoring on new leagues | MVP |
| Admin queue for unmapped + needs-review | MVP |
| Admin manual tier override | MVP |
| Tier filter pills in UI | MVP |
| Tier-gating per user subscription | MVP |
| Friendlies as opt-in tier (off by default) | MVP |
| Tier-change audit log (data) | MVP |
| Migration of existing v2.7 dataset | MVP (launch task) |
| Audit log UI | Phase 2 |
| Bulk admin operations | Phase 2 |
| Admin notification when queue grows | Phase 2 |
| Algorithm-tuning UI | Phase 2 or Future |
| Historical tier context | Future |
| User-customizable tier groupings | Future |

### 4.3 Backtest Engine — MVP

The Backtest Engine applies the same filter logic as Match Analysis, but runs against historical completed matches.

Per D-009, the filter engine is shared: filters built in Match Analysis are *reused* by Backtest, not redefined.

#### 4.3.1 What the user can do

- Carry filters over from Match Analysis (no re-entry).
- See a summary of inherited filters in the backtest sidebar.
- Set a historical time range (1–12 months back, default 6).
- Choose an outcome to bet on — market + selection (mirrors Match Analysis strategy).
- Apply the same scope as Match Analysis.
- Submit the backtest as a job. Receive a job ID, progress updates, and a result when complete.
- Watch real-time progress (percentage bar).
- See queue status when at capacity.
- View past backtest runs from a Backtest History page (tier-based retention).
- Open the event page for any bet in the result list.
- Export the bet list to CSV.
- Save the strategy.
- Cancel a queued or running job.

#### 4.3.2 Backtest input parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `filters` | inherited | active set | Same definitions per 4.1.2 |
| `months_back` | int (1–12) | 6 | How far back |
| `outcome_market` | enum | — | Which betting market |
| `outcome_selection` | enum + line | — | Selection (any-line or specific-line) |
| `min_score` | int | from filter set | Same as Match Analysis |
| `tiers` / `countries` / `league_ids` | inherited | from scope | Same |
| `league_completion_min` / `_max` | int / int | 50 / 100 | Same |

#### 4.3.3 Supported outcomes (MVP)

The 17 outcomes from v2.7:

| Category | Outcomes |
|---|---|
| Match Result | Home Win, Away Win, Draw, Home or Draw (1X), Away or Draw (X2) |
| Goals | BTTS, Over 2.5 / 3.5 / 4.5, Under 2.5 / 3.5, Goalless Draw |
| Corners | Corners Over 8.5 / 9.5 / 10.5 |
| Cards | Cards Over 3.5 / 4.5 |

**The same betting markets and selections available in the Match Analysis strategy must also be available as backtest outcomes.**

#### 4.3.4 Odds source

**Backtest uses captured real odds only.** No assumed-odd fallback (D-023).

- Real odds source: API-Football historical odds, backfilled to the database (D-025) as a pre-launch operational task.
- Fixtures without captured odds for the chosen selection are excluded from the bet sample.
- The output includes a "Real-odds Coverage %" KPI — what % of filter-matched fixtures had odds available.

#### 4.3.5 ROI calculation

Flat-stake: 1 unit per bet.

| Term | Formula |
|---|---|
| Total Staked | bets × 1 |
| Total Return | Σ (win × odd_for_that_bet) |
| P&L | Return − Staked |
| ROI % | (P&L / Staked) × 100 |

Kelly criterion staking is **Phase 2**.

#### 4.3.6 Outputs

| Output | Description |
|---|---|
| Summary KPIs | Hit rate %, ROI %, P&L (units), Total Bets, Best Streak, Worst Streak, Real-odds Coverage % |
| Cumulative P&L curve | Line chart over time |
| Monthly breakdown | Bar chart, P&L per calendar month |
| Full bet list | Every matched fixture: date, teams, league, score, outcome (W/L), odd, P&L |
| Bet list interaction | Each row clickable — opens event page |
| CSV export | Full bet list downloadable |

#### 4.3.7 Business rules

- **Only finished matches** are part of the historical sample.
- **No data leakage:** filters evaluate using only data available before that match's kickoff.
- **Tier scope applies to form samples too** — if `friendlies` is deselected, friendlies excluded from candidate set *and* from prior-match samples used to evaluate filters.
- **No partial periods.** Whole-day boundaries.
- **Bounded by available history.** If 12 months requested but only 8 exist, engine uses what's available.

#### 4.3.8 Edge cases

- Sparse data: warn when bet count < 30. Result still displayed but flagged.
- No matches: clear "0 bets matched" message.
- Missing outcome data: fixture excluded; reported separately.
- Any-line outcome with no eligible line: excluded.
- League tier changed during window: current tier governs.

#### 4.3.9 Performance requirements

| Workload | Target (p95) |
|---|---|
| Typical backtest end-to-end (incl. queue) | < 10 seconds |
| Heavy backtest end-to-end | < 60 seconds |
| Queue wait (typical load) | < 5 seconds |
| Queue wait (heavy load) | Reported; no hard upper bound |

These targets assume the four-phase execution model (4.3.13) is in place. The system must support graceful degradation under load.

#### 4.3.10 Caching

- Results cached server-side keyed by `(filter set hash, scope hash, outcome hash, months_back, user tier)`.
- TTL: **24 hours.**
- Identical inputs from different users share the cache.
- Invalidated when historical odds backfill or pre-computed snapshots refresh.

#### 4.3.11 Strategy save flow

A *strategy* is saved, not the result. A strategy = filter set + outcome + scope + optional name/description. Detailed in 4.5.

#### 4.3.12 Phasing

| Capability | Phase |
|---|---|
| Backtest engine sharing filter definitions with Match Analysis | MVP |
| All 17 v2.7 outcomes | MVP |
| Captured real odds only | MVP |
| Time range 1–12 months | MVP |
| Cumulative P&L curve, monthly breakdown | MVP |
| Full bet list with clickable rows | MVP |
| Bet list CSV export | MVP |
| Sample-size warning (< 30 bets) | MVP |
| Async job execution with queue, progress, persistence | MVP |
| Backtest history page (per-user retention) | MVP |
| Tier-based queue priority | MVP |
| Pre-computed form snapshots | MVP |
| Kelly criterion staking | Phase 2 |
| Compounding bankroll model | Phase 2 |
| Time range >12 months | Phase 2 |
| Variable-stake per-filter-score | Phase 2 |
| Backtest of player props metrics | Phase 2 |
| Multi-strategy backtest comparison | Future |
| Walk-forward / out-of-sample testing | Future |

#### 4.3.13 Execution model — MVP

Backtests are **asynchronous background jobs**, not synchronous API requests. Hard requirement, not an optimization.

**Architectural shape — four phases:**

1. **Phase 1: Pre-filter the candidate fixture set.** Tier scope, country/league, date range, completion range, outcome-data availability, odds availability — all indexed lookups. By the time Phase 2 starts, candidate set is typically 100×–1000× smaller than the raw historical table.
2. **Phase 2: Filter evaluation against pre-computed form snapshots.** Mostly lookups, not recomputation.
3. **Phase 3: Score aggregation and outcome resolution.** Per-fixture: sum filter passes, check min_score, resolve outcome (W/L), apply odd, compute P&L.
4. **Phase 4: Aggregation and result serialization.** Cumulative curve, monthly breakdown, summary KPIs.

The candidate count is known after Phase 1 — which makes a real progress percentage possible.

**Queue model:**
- Central job queue holds pending submissions.
- Pool of worker processes consumes the queue.
- Concurrency cap at the platform level (configurable).
- Tier-based queue priority (paid users' jobs dequeue first; within tier, FIFO).
- Per-user submission rate limits.
- Job lifecycle states: `queued`, `running`, `completed`, `failed`, `cancelled`.
- User can cancel a queued or running job.

**Result persistence:**
- Completed backtest results stored, scoped to user.
- Retention tier-based, configurable via `limit.backtest_history_retention`.
- Older results auto-pruned (FIFO, oldest first).
- Identical input within cache TTL returns cached; outside TTL runs new job.

**Progress reporting to client:**
- Polling or websocket: `state`, `progress_pct`, `position_in_queue`, `eta_seconds`, `result_id`.
- UI: percentage bar with queue position fallback.

### 4.4 Player Props Engine — Phase 2

**Phase 2 module.** Player Props is deferred from MVP per D-022. This section is the full specification, ready to implement post-MVP. **Data collection (lineups, player_match_stats) begins at launch so historical depth exists when the module ships.**

The Player Props module answers: *"Which individual players in upcoming matches have historically performed well on a given metric against this type of opponent?"* It has two entry modes — **Find Players** (filter-driven discovery) and **Match Lineups** (browse by match) — both converging on the same **Player Card** as the analytical detail view.

#### 4.4.1 What the user can do

**Find Players mode:**
- Build percentage-based filters on player metrics (same shape as match filters).
- Filter by position (Attacker / Midfielder / Defender / Goalkeeper / All).
- Enforce minimum minutes played per match in the sample (default 45).
- Enforce "starting XI only" toggle, cross-referencing lineup data.
- Scope by league tier, country, league.
- Submit search — receive a ranked list of players matching the filter set across upcoming fixtures.
- Click any player to open the full Player Card.

**Match Lineups mode (default entry):**
- Browse today's and tomorrow's matches with lineup status (✅ confirmed / ⏳ pending).
- Expand any confirmed match to view starting XI and substitutes.
- Click any player to open the Player Card.

**Player Card (shared analytical view):**
- See the player's recent performance on a chosen metric (sparkline, avg/min/max, total matches).
- See auto-generated hit rates at 50%, 75%, 100%, 125%, 150% of the player's average.
- See **opponent analysis** — how much of this metric the upcoming opponent typically allows for players in this position.
- See a **verdict** — STRONG PLAY / MARGINAL / AVOID, computed from player form + opponent quality.
- See available odds for the match.
- Switch metrics within the card without leaving.

#### 4.4.2 Available player metrics (Phase 2)

Ported from v2.7. Each metric has a category, position-relevance hint, and gate.

| Category | Metrics |
|---|---|
| Attacking | Goals, Assists, Shots Total, Shots on Target, Rating |
| Creative | Key Passes, Dribbles Attempted, Dribbles Successful |
| Passing | Passes Total, Passes Accuracy % |
| Defensive | Tackles, Blocks, Interceptions |
| Discipline | Yellow Cards, Red Cards |
| Volume | Minutes Played |

#### 4.4.3 Player filter anatomy

Similar to match filters but on player data:

| Parameter | Type | Description |
|---|---|---|
| `metric` | enum | Which player metric |
| `operator` | enum | `gte` or `lte` |
| `threshold` | number | Threshold value |
| `sample` | int (1–20) or `"season"` | Last N matches or current season |
| `pct_operator` | enum | `gte` or `lte` |
| `pct_value` | int (0–100) | Hit-rate threshold |
| `min_minutes` | int | Default 45 |
| `position` | enum | `all` / `F` / `M` / `D` / `G` |
| `starting_xi_only` | boolean | Only confirmed starters |

#### 4.4.4 Opponent analysis logic

**Option B (Primary) — Position-specific.** How many of this metric did players in this position average against this opponent in their last 5 matches?

**Option A (Fallback) — Team-level.** How much of this metric does this team's opposition allow per game on average?

System tries B first; falls back to A when B has insufficient data.

#### 4.4.5 Verdict thresholds (admin-configurable)

| Metric | Very Favorable | Favorable | Neutral | Tough |
|---|---|---|---|---|
| Shots on Target | ≥ 4.0/game | ≥ 2.8 | ≥ 1.8 | < 1.8 |
| Goals | ≥ 1.8/game | ≥ 1.2 | ≥ 0.8 | < 0.8 |
| Key Passes / Shots Total | ≥ 14.0/game | ≥ 10.0 | ≥ 7.0 | < 7.0 |
| Tackles | ≥ 20.0/game | ≥ 14.0 | ≥ 8.0 | < 8.0 |

#### 4.4.6 Business rules

- A player's match counts toward their form sample if `minutes_played >= min_minutes`.
- `position_played` is source of truth for position filter (not registered position).
- Starting XI toggle requires confirmed lineup.
- Tier-scope rule applies to player form samples too.
- Player form data ports across leagues.
- Maximum 200 players returned (configurable per tier).

#### 4.4.7 Edge cases

- Player transferred mid-season — Player Card shows current team and league.
- Player with no recent matches at minutes threshold — excluded from search.
- Goalkeeper-specific metrics — not in initial Phase 2 release (uses outfield metrics for all positions).
- League without player stats coverage — falls back to Option A team-level logic.

#### 4.4.8 Phasing

All listed in 4.4 is Phase 2 unless specified otherwise. Lineup data collection is MVP (data captured, not user-surfaced).

### 4.5 Saved Strategies — MVP

A **Strategy** is a reusable bundle of analysis configuration. The connective tissue between Match Analysis and Backtest. Also a serious retention feature.

#### 4.5.1 What is a Strategy

| Component | Source |
|---|---|
| Filter set | Active filters from Match Analysis |
| Strategy / outcome | Betting market + selection + line mode |
| Scope | Tiers, countries, leagues, completion range, days ahead |
| `min_score` threshold | From Match Analysis |
| Name + optional description | User-provided |
| Created/updated timestamps | System |
| Owner | The user who created it (or `system` for pre-built) |

What is **not** part of a Strategy: results, run history (linked separately), sharing state (Future).

#### 4.5.2 What the user can do

**Manage strategies:**
- Save the current Match Analysis configuration as a Strategy (with name + optional description).
- View all saved strategies.
- Load a saved strategy (restores filter set, scope, outcome into Match Analysis).
- Rename, edit description.
- Update (overwrite the saved config with currently-active one).
- Duplicate as a starting point for variations.
- Delete (with confirmation; soft delete per Section 11).

**Use strategies:**
- Run a strategy on upcoming matches.
- Backtest a strategy directly.
- Strategies expose "Run" and "Backtest" buttons in the list.

**Tier-gated:**
- Number of saved strategies capped per user tier.
- Soft-cap on downgrade (existing strategies retained; new saves blocked).

#### 4.5.3 Save flow

1. User builds filters in Match Analysis.
2. User clicks Save.
3. Modal: name (required, 1–80 chars), description (optional, up to 500 chars).
4. Saved via API.
5. Appears in strategies list.
6. At tier limit: blocked with upgrade prompt.

#### 4.5.4 Load flow

Three default actions on any strategy: Load, Run on Upcoming, Backtest. Load restores all parameters.

#### 4.5.5 Update flow

- **Save changes (update in place):** strategy overwritten; ID preserved; linked backtest history preserved.
- **Save as new:** treat current state as a new strategy.

#### 4.5.6 Backtest history attached to strategies

Backtest runs linked to a saved strategy are visible on the strategy detail view. Retention bounded by `limit.backtest_history_retention`.

#### 4.5.7 Business rules

- Strategy ownership is strict (one user, or `system` for pre-built).
- Names user-scoped (not globally unique).
- **Schema versioning required.** As filter engine evolves, old strategies must remain loadable. Strategy record stores schema version; load logic handles or surfaces incompatibility cleanly.
- Tier-limit at save time, not at use time.
- Deletion is soft for 30 days, then hard delete.

#### 4.5.8 Edge cases

- Metric in saved strategy removed: surfaced visibly on load.
- Tier in saved strategy renamed: auto-mapped per migration rules.
- League_id in saved strategy ceases to exist: marked as unavailable.
- `sample = "season"` re-evaluated against current season at run time.
- Concurrent edits from two sessions: last-write-wins.

#### 4.5.9 Performance

| Workload | Target (p95) |
|---|---|
| Save strategy | < 500ms |
| Load strategies list | < 500ms |
| Load specific strategy | < 200ms |

#### 4.5.10 Phasing

| Capability | Phase |
|---|---|
| Save / load / rename / delete / duplicate / update | MVP |
| Strategy attached to user (private) | MVP |
| Tier-gated `limit.saved_strategies` | MVP |
| Backtest history linked to strategy | MVP |
| 30-day soft delete | MVP |
| Schema versioning | MVP |
| Strategy detail view with run history | MVP |
| Public sharing | Future |
| Strategy import/export (JSON) | Phase 2 |
| Strategy templates surfaced as pre-built (per 5.6) | MVP |
| Strategy tags or folders | Phase 2 |
| Cross-strategy comparison | Future |
| Auto-alerts when strategy fires | Phase 3 (with mobile apps) |

#### 4.5.11 Anonymous access

Anonymous users get no save capability. Saving requires authentication. (Q-NEW-M resolved.)

### 4.6 Event Page & Opportunities Engine — MVP

#### 4.6.1 Concept

The Event Page is the platform's per-match analytical destination. For every fixture in the database (upcoming or completed), an Event Page exists as a navigable destination accessible via search, from match cards anywhere in the platform, and via direct link.

#### 4.6.2 What the user can do

- Open an Event Page for any fixture in the database.
- Star the fixture to add it to their shortlist (with folder picker per 5.5).
- See multiple analytical views of the fixture, each focused on a different category of insight (form summary, market opportunities, head-to-head, streaks, statistical categories, standings context, etc.).
- Navigate to related entities (teams, leagues) from the page.
- Continue searching for other teams/leagues without leaving the page.

The **specific inventory of views (tabs) and their visual organization is a product design concern**, finalized with Stratos. The architectural commitment is that the Event Page is multi-view, with each view independently gateable.

#### 4.6.3 Per-view gating

The Event Page is structured so that each analytical view is independently gateable per user tier. Some views may be available to anonymous users, some to free users only, some to paid users only — the specific cuts are admin-configurable runtime values, not part of this requirements document.

Mechanism per Section 3 and D-037:
- Server-side enforced.
- UI may render gated views in a locked state with upgrade prompt; the server is the source of truth.
- Cuts adjustable without code deployment.

#### 4.6.4 Analytical views — categories required in MVP

| Category | Required MVP capability |
|---|---|
| Form summary | High-level form context for both teams |
| Market opportunities | All value bets discovered by the Opportunities Engine (4.6.6) for this fixture |
| Streaks | Active streaks for both teams across measured categories |
| Statistical category breakdowns | Goals, corners, cards, half-time stats — averages, hit rates, splits |
| Head-to-head | Historical record between the two teams |
| Standings context | Current league standings with the two participating teams highlighted |
| Player-specific data | Phase 2 (deferred with Player Props per D-022) |

#### 4.6.5 Behavior

- Every fixture in the database has an Event Page. Upcoming, completed, postponed — all accessible.
- Completed fixtures display result and final stats.
- Form metrics on the Event Page respect the user's tier scope.
- Star action routes to the Shortlist with the strategy-folder picker (5.5).
- A user-facing disclaimer is displayed on analytical-output views indicating that platform output is based on historical analysis rather than predictive certainty. Specific wording is product/legal design (per D-038).

#### 4.6.6 The Opportunities Engine — MVP

**Purpose:** for every upcoming match, automatically compute hit rate vs implied probability across a fixed set of standard betting markets and identify positive-edge opportunities. Output stored and served as pre-computed data.

**This is system-driven, not user-driven.** Distinct from the Filter Engine (user-driven, criteria-based).

**Inputs (per fixture):**
- Both teams' historical form metrics (from pre-computed snapshots per D-016)
- Head-to-head historical record
- Current standings context for the fixture's league
- Captured pre-kickoff odds across covered markets
- Fixture metadata (league, league tier, kickoff time)

**Computation per market:**
- Platform hit rate (estimate of outcome's probability)
- Implied probability (from captured odd)
- Edge (hit rate − implied, percentage points)
- EV % ((hit_rate × (odd − 1)) − (1 − hit_rate)), as percent
- Supporting stats — denormalized for fast display

**Canonical market set (MVP):** the 17 outcomes from 4.3.3 plus Match Winner (Home/Draw/Away) and standard line variations. Specific market inventory configurable by admin.

**Methodology:**
The platform's hit-rate methodology per market is the **core analytical asset**. Methodology itself is **out of scope for this requirements document** — it is engineering work for Session 3+.

Required properties:
- Deterministic and explainable (no opaque ML in MVP).
- Per-market (corners and goals have distinct signal weighting).
- Admin-tunable (coefficients, sample sizes, weighting factors stored as configuration).
- Versioned (methodology has a version identifier; computed outputs stamped with the version).

**Best Bet annotation:**
After computing all opportunities for a fixture, engine identifies the single highest-edge opportunity (with tiebreakers: higher EV, lower-variance market, simpler market preferred) and annotates with `is_best_bet` flag.

**Output storage:**
Per fixture, engine writes rows to `fixture_opportunities` table (or equivalent). One row per (fixture, market, selection) where edge meets configurable minimum threshold. Each row stores: hit rate, implied, edge, EV, supporting stats, methodology version, computed-at timestamp, is_best_bet flag.

**Minimum-edge threshold:**
Configurable minimum edge for inclusion (default indicative ~5 pts; not locked). Threshold adjustable per admin and per user tier.

**Cadence:**
- Nightly for all upcoming fixtures in next 14 days.
- On-demand re-computation after major data syncs.

**Performance:**
- Per-fixture computation: < 1 second per fixture in the worker.
- Full nightly batch: thousands of fixtures × ~30 markets. Must complete within nightly sync window.
- Read latency on Event Page: < 200ms.

#### 4.6.7 Methodology versioning

When the platform's hit-rate methodology changes:
- New computations use the new methodology version.
- Existing stored opportunities are preserved with their original methodology version stamp.
- New computations may regenerate prior opportunities, but the system preserves the version history so historical performance analysis remains consistent.

#### 4.6.8 Caching

- Event Page response data cached server-side per `(fixture_id, user_tier)`.
- TTL: 1 hour for upcoming, 24 hours for completed.
- Underlying Opportunities table rows are the durable storage.
- Cache invalidated when engine recomputes for the fixture.

#### 4.6.9 Edge cases

- Fixture with no captured odds: opportunities not computable; view surfaces "no odds available" with explanation.
- Fixture with limited historical depth: engine falls back to broader sample windows or skips computation per methodology rules.
- Postponed/cancelled fixture: Event Page accessible; status reflects postponement; analytical views marked stale.
- Newly-promoted/relegated team: form spans leagues per 4.1.8.

#### 4.6.10 Phasing

| Capability | Phase |
|---|---|
| Event Page core (header, star, navigation) | MVP |
| Categories of view per 4.6.4 (excluding players) | MVP |
| Players view | Phase 2 |
| Opportunities Engine — full computation per market | MVP |
| Best Bet annotation within Opportunities | MVP |
| Per-view tier gating mechanism | MVP |
| Methodology versioning | MVP |
| Admin-tunable methodology coefficients | MVP |
| Result Probabilities (1X2 model) as dedicated view | Phase 2 or Future — product design with Stratos |
| Rule-based or AI-generated narrative summary view | Phase 2 or Future — product design |
| Live in-play updates | Future |

### 4.7 Team Page & League Page — MVP

#### 4.7.1 Concept

The platform provides dedicated pages for **teams** and **leagues**. Each is a navigable destination accessible via search, by clicking team/league badges anywhere, and via direct link.

#### 4.7.2 What the user can do

**Team Page:**
- Open a Team Page for any team in the database.
- See the team's recent and upcoming fixtures.
- View the team's analytical context across categories (form summary, statistical breakdowns, streaks, market opportunities for upcoming fixtures, etc.), team-focused.
- Star upcoming fixtures.
- Navigate to related entities (specific fixtures, the team's league).

**League Page:**
- Open a League Page for any league in the database.
- See current standings, upcoming fixtures, recent results.
- View league-wide analytical context (averages, hit rates, completion %).
- See market opportunities discovered for fixtures in this league.
- Navigate to related entities.

The specific inventory of views and their visual organization is **product design**, finalized with Stratos.

#### 4.7.3 Architectural commitments

Both pages follow the same pattern as the Event Page:
- Multi-view, tab-based structure.
- Per-view tier gating, admin-configurable.
- Server-side enforcement of gating.
- Pulled from the same underlying analytics — no new engines.
- Star-to-shortlist consistent with Event Page mechanism.
- Disclaimer banner on analytical-output views.

#### 4.7.4 Behavior

- All users can open a Team Page or League Page. Page-level access is universal; views within are gated.
- Team Page reflects the team's current state.
- League Page reflects the current season by default.
- Form metrics respect the user's tier scope.
- Defunct teams or leagues remain accessible as historical archives.

#### 4.7.5 Performance

| Workload | Target (p95) |
|---|---|
| Team Page initial load | < 1 second |
| League Page initial load | < 1 second |
| View switch | < 200ms |

#### 4.7.6 Caching

Both pages cached server-side per `(entity_id, user_tier)`. TTL: 1 hour for active, 24 hours for inactive.

#### 4.7.7 Phasing

| Capability | Phase |
|---|---|
| Team Page core | MVP |
| League Page core | MVP |
| Per-view tier gating | MVP |
| Players-related views | Phase 2 |
| Past-season views or season toggle | Product design with Stratos |
| Defunct entity archive view | MVP |

---

## 5. Functional Requirements — Public Platform Additions

Features new to v3 that don't exist in v2.7.

### 5.1 Authentication — MVP

**What the user can do:**
- Sign up via email + password.
- Sign up via Google OAuth (works with any Google account — Gmail, Workspace, Android, YouTube, not just Gmail addresses).
- Log in with the credentials/provider used at signup.
- Log out from any session.
- Initiate password reset via email link (1-hour expiry, single-use).
- Verify email via emailed link (required within 7 days for paid actions).
- Stay signed in across sessions (30-day default).
- Sign in from multiple devices.

**Not in MVP:**
- 2FA (Phase 2)
- Magic-link login (Phase 2)
- OAuth providers beyond Google (Phase 2)

**Business rules:**
- Email is canonical identifier (no two accounts share email).
- OAuth + email collision: offer to link OAuth to existing account after password verification.
- Email verification grace period: 7 days.
- Password minimum: 8 characters.
- Session tokens httpOnly, secure, SameSite=Lax.

**Phasing:**

| Capability | Phase |
|---|---|
| Email + password signup/login | MVP |
| Google OAuth | MVP |
| Email verification | MVP |
| Password reset | MVP |
| Multi-session | MVP |
| Email-change flow | MVP |
| 2FA | Phase 2 |
| Magic-link | Phase 2 |
| Apple / Facebook / GitHub OAuth | Phase 2 |
| Self-service "log out all sessions" | Phase 2 |
| SSO for team accounts | Future |

### 5.2 User Profile & Settings — MVP

**What the user can do:**
- Edit display name, timezone.
- Read-only: email, account creation date, current tier, verification status.
- Change password.
- Change email (with verification of both old and new).
- Toggle theme (light/dark). Persists per account.
- Switch language (mechanism present; English only at launch; adding languages later is translation work).
- Manage notification preferences (dormant toggles in MVP; ready when notifications ship).
- Initiate account deletion (soft delete; grace period).
- Request GDPR data export.

**Not in MVP:**
- Avatar upload (Phase 2; MVP uses initial-based default avatars).

### 5.3 Subscription Management — MVP

**What the user can do:**
- View current subscription (tier, status, next renewal date, period dates).
- View billing history with downloadable Stripe-hosted receipts.
- Upgrade or downgrade.
- Update payment method (Stripe-hosted billing portal).
- Cancel subscription (effective end-of-period).
- Start free trial (one-per-account, no card).
- Resubscribe after cancellation.

Platform owns simpler views (current plan, Upgrade, Cancel, trial flow). Stripe's billing portal owns payment-method, invoice detail, dispute flows. Platform deep-links into the billing portal.

### 5.4 Search — MVP

A unified search bar accessible from every page. The user types a partial team name, league name, or competition name; system returns matching results across three entity types:

- **Upcoming matches** — fixtures where one of the teams matches
- **Completed matches** — same with date filter (per D-035)
- **Teams** — by name match
- **Leagues / competitions** — by name match

Player search is Phase 2.

**What the user can do:**
- Type into global search box — debounced (300ms typical) live results.
- See mixed-type results in a single ranked list.
- Click a match result → opens Event Page.
- Click a team result → opens Team Page.
- Click a league result → opens League Page.
- See match metadata inline.
- See recent search history (per D-036) in the empty state when typing nothing.
- Use search to find a team/league to add to scope filters in Match Analysis.

**Business rules:**
- All users see all search results.
- Case-insensitive and accent-insensitive ("Atletico" matches "Atlético").
- Partial/prefix/substring matching supported.
- Result ranking: exact match > prefix match > substring match. Higher-tier entities rank above lower-tier. Sooner fixtures rank above later.
- Date filter for completed matches (today, this week, last week, custom range).
- Top-N cap (typically 20 across all types).
- Search history: last 20 per user; FIFO eviction; user can clear from settings.

**Performance:**

| Workload | Target (p95) |
|---|---|
| Search query response | < 300ms |

Requires a proper search index (Postgres full-text or external service).

**Phasing:**

| Capability | Phase |
|---|---|
| Team search | MVP |
| League search | MVP |
| Upcoming match search by team name | MVP |
| Completed match search with date filter | MVP |
| Search history per user | MVP |
| Debouncing, ranking, accent-insensitivity | MVP |
| All-users-see-all results | MVP |
| Inline metadata | MVP |
| Player search | Phase 2 (with Player Props) |
| Alternate-name aliases | Phase 2 |
| Trending searches | Future |

### 5.5 Shortlist — MVP

#### 5.5.1 Concept

The Shortlist is the user's collection of saved selections — centralized "things I'm tracking." Selections are saved from anywhere in the platform (filter results, Event Page, Team Page, Best Picks).

The Shortlist has **two functional modes**: managing saved-selections, and building accumulator combinations. Visual organization of these modes is product design.

#### 5.5.2 Saving selections

**What the user can do:**
- Add a (fixture, market, selection) triplet to the shortlist from any surface presenting selections.
- At the moment of adding, choose to file under a specific saved strategy or under a default ungrouped bucket.
- Move a saved selection between folders.
- Remove a selection.

**Business rules:**
- Each saved item is a (fixture, market, selection) triplet — multiple selections on same fixture are distinct.
- Duplicate prevention.
- User-private; no sharing in MVP.
- Size tier-gated per `limit.shortlist_items`.
- Folder is the saved-strategy ID (or default). If a strategy is deleted, items move to default automatically.
- Live odd displayed; refreshed on load and on user request.
- Tier downgrade soft-cap.

**No auto-prune of finished items.** Finished fixtures retained with their result computed and displayed (won/lost). Manual unstar is the only removal.

**Edge cases:**
- Postponed/cancelled fixtures: kept with new status.
- Selection becomes unavailable: kept with "no odd" indicator.
- Saved strategy renamed: filed items reflect new name automatically.

#### 5.5.3 Accumulator combinations

**What the user can do:**
- Combine shortlist selections into accumulators (singles or multi-leg).
- See per-leg odds and combined math (legs, total odds, payout from virtual stake, profit).
- Save accumulator combinations.
- Open, edit, or remove saved accumulators.
- See accumulator outcome status (pending/won/lost).

**Business rules:**
- **Virtual and informational only.** No real-money handling.
- Combined odds: standard product of per-leg decimal odds.
- Number of legs tier-gated.
- Number of saved accumulators tier-gated.
- Same-fixture multi-leg accumulators allowed with advisory (bookmakers price differently).
- Stake input display-only; not persisted across sessions in MVP.
- Outcome status binary: pending → won (all legs won) → lost (any leg lost).
- Unstarring a shortlist item doesn't affect existing saved accumulators.

**Edge cases:**
- Leg in saved accumulator becomes unavailable: accumulator blocked until fixture resolves or user removes leg.
- All legs resolved: accumulator marked won or lost.

#### 5.5.4 Quick-action capability

The platform must support convenience actions on the Shortlist that group or pre-select items for accumulator building. The **specific quick-action set is product design** with Stratos.

#### 5.5.5 Performance

| Workload | Target (p95) |
|---|---|
| Add item to shortlist | < 300ms |
| Load shortlist view | < 500ms |
| Save accumulator | < 500ms |
| Load saved accumulators | < 500ms |

#### 5.5.6 Phasing

| Capability | Phase |
|---|---|
| Save from filter results, Event Page, Team Page, Best Picks | MVP |
| Folder organization by saved strategy | MVP |
| Live odds display | MVP |
| Finished-fixture outcome evaluation | MVP |
| No auto-prune | MVP |
| Move between folders | MVP |
| Shortlist tier limit | MVP |
| Accumulator builder consuming shortlist pool | MVP |
| Combined-odds math, stake, payout, profit | MVP |
| Save accumulator | MVP |
| Status tracking (pending/won/lost) | MVP |
| Tier limits on legs and saved accumulators | MVP |
| Same-game multi advisory | MVP |
| Quick-action capability (set TBD by product) | MVP |
| Live odds polling | Phase 3 (with mobile apps) |
| Persistent default stake | Phase 2 |
| Multi-bookmaker odds comparison | Phase 2 |
| Bookmaker deep-linking | Phase 2 |
| Affiliate revenue from bookmaker click-throughs | Phase 2 |
| Shortlist sharing (public link) | Future |
| Real-money bet placement | Out of scope — Section 13 |

### 5.6 Pre-built Strategies — MVP

The platform provides a library of **curated strategies** — pre-defined filter sets + outcomes that users can adopt, modify, and run.

**What the user can do:**
- Browse the pre-built strategy library.
- Apply a pre-built strategy (loads it into Match Analysis).
- Copy a pre-built strategy to their own saved strategies.
- Backtest a pre-built strategy with one click.
- See historical performance of pre-built strategies.

**Business rules:**
- Pre-built strategies managed by admin. Stored as `owner = system`.
- Tier-gating per pre-built strategy.
- Pre-built strategies count toward `limit.saved_strategies` only when copied.
- Subject to schema versioning.
- Curation cadence: periodic admin review; no fixed cadence in MVP.

**Edge cases:**
- Pre-built updated after user copy: user's copy unchanged; may show indicator.
- Pre-built deprecated: user copies persist.
- Free user tries to apply paid pre-built: blocked with upgrade prompt.

**Phasing:**

| Capability | Phase |
|---|---|
| Pre-built strategy library | MVP |
| Tier-gated visibility | MVP |
| Apply / copy / backtest | MVP |
| Historical performance summary | MVP |
| Admin-managed library | MVP |
| Schema-versioning migration | MVP |
| User notification on pre-built update | Phase 2 |
| Community-submitted strategies | Future |
| Paid creator marketplace | Future |

### 5.7 Best Picks — MVP

A platform-curated feed of **high-conviction selections across all upcoming matches**, automatically computed from the Opportunities Engine.

**What the user can do:**
- Browse the Best Picks feed.
- Filter by tier scope, date range, market category, minimum edge threshold.
- Star a pick to shortlist.
- Click through to Event Page.
- See "why this pick" — a brief explainer auto-generated from the underlying analytics.

**Business rules:**
- Computed from `fixture_opportunities` table filtered to high-edge across all upcoming fixtures.
- Tier-gated visibility (top N for free, fuller for paid).
- Computation cadence: regenerated nightly and after major data syncs.
- **100% algorithmic.** No human editorial overrides.
- Disclaimer banner on the feed (per D-038).

**Edge cases:**
- Slow data day: feed may be smaller. Don't pad with low-edge picks.
- High data day: tier cap still applies.
- No captured odd for a fixture's market: excluded.

**Phasing:**

| Capability | Phase |
|---|---|
| Best Picks feed page | MVP |
| Algorithmic computation | MVP |
| Tier-gated visibility | MVP |
| Filters (market, date, edge) | MVP |
| Direct star to shortlist | MVP |
| "Why this pick" auto-summary | MVP |
| Disclaimer | MVP |
| User-configurable feed preferences | Phase 2 |
| Notifications on major opportunity | Phase 3 (with mobile apps) |
| Editorial overlay | Future |
| Performance dashboard for Best Picks | Phase 2 |

### 5.8 Strategy Sharing — Future

User-to-user strategy sharing is explicitly Future. Deferred for privacy, IP, discovery, moderation, and monetization questions.

### 5.9 Notifications — Phase 3

Per D-024, auto-alerts and notifications deferred until mobile apps exist. Settings UI carries dormant toggles in MVP.

When notifications ship: push (mobile), email (non-mobile), in-app inbox.

Events: saved strategy fires, trial expiry, payment failure, shortlist odds change, renewal upcoming, major Best Picks opportunity.

---

## 6. Data Requirements

### 6.1 Data scope principle

**Capture every field provided by data sources, including ones not currently used.** Data not captured cannot be reconstructed. Storage cost is low; future product optionality is high.

Applies to all integrated data sources (API-Football MVP; future additional sources per Section 2.6).

### 6.2 Data layers

| Layer | Purpose |
|---|---|
| **Raw layer** | Unmodified API responses, archived for replayability and audit |
| **Curated layer** | Normalized, application-shaped data derived from raw |
| **Computed layer** | Pre-computed analytics: form snapshots, opportunities, KPIs |
| **User layer** | User-private data: accounts, strategies, shortlists, accumulators, etc. |

The four logical layers must exist with the responsibilities above, and be independently accessible.

### 6.3 Required entities

| Entity | Required in MVP | Notes |
|---|---|---|
| Leagues / competitions | Yes | With tier mapping per 4.2 |
| Teams | Yes | Logos, country, current league |
| Standings | Yes | Per league per season |
| Fixtures | Yes | Upcoming and completed; status tracked |
| Match statistics | Yes | Full v2.7 set + every API field |
| Lineups | Yes | Data collected from launch; user-facing in Phase 2 (D-022) |
| Player match statistics | Yes | Same reason as lineups |
| Odds | Yes | Multiple markets, multiple lines per market; current + historical |
| Pre-computed team form snapshots | Yes | Per D-016 |
| Pre-computed opportunities | Yes | Per fixture per market (D-030) |
| Users | Yes | Auth + profile data |
| Subscriptions | Yes | Stripe-synced state |
| User-saved strategies | Yes | Including pre-built (admin-owned) |
| User shortlists | Yes | Grouped by saved strategy |
| User saved accumulators | Yes | Referencing shortlist items |
| User backtest history | Yes | Persisted; retention per tier |
| User search history | Yes | Per D-036 |
| Tier mapping (league → tier) | Yes | With audit trail |
| Sync logs, error logs | Yes | Operational data |
| Feature flags / gating config | Yes | Per D-037 |
| Methodology version registry | Yes | Per 4.6.7 |
| Pre-computed player form snapshots | No | Phase 2 |
| Player-specific odds | No | Phase 2 |

### 6.4 Multi-sport extensibility

Per D-039: every plausibly sport-specific entity carries a sport identifier (default `'football'`). Includes leagues, teams, fixtures, match statistics, player statistics, lineups, odds, opportunities.

Entities sport-agnostic (users, subscriptions, saved strategies, search history, feature flags) do not need sport identifier.

Adding a second sport: configure new data source adapter; insert new metric definitions. **No schema migrations.**

### 6.5 Data retention

| Data category | Retention |
|---|---|
| Raw API responses | Indefinite; archive to cold storage after 12 months acceptable |
| Curated entity data | Indefinite |
| Computed form snapshots | Indefinite; pruning of snapshots older than ~2 seasons acceptable |
| Computed opportunities | Indefinite (preserve methodology-version history) |
| Odds (historical) | Indefinite — critical for backtest |
| User account data | Active: indefinite. Soft-deleted: grace period then purge |
| User-private data | Lifetime of account; purge on hard-delete |
| User backtest history | Per-user tier-gated retention |
| User search history | Last N per user; FIFO eviction |
| Sync logs | Operational retention — admin-tunable |
| Audit logs | Indefinite for compliance |

### 6.6 Data freshness

| Data category | Required freshness |
|---|---|
| Upcoming fixtures | Nightly minimum; intraday updates on match days |
| Match statistics | Within ~1 hour of fixture finishing |
| Standings | Daily |
| Lineups | Every 3–4 hours on match days |
| Odds | Daily minimum; intraday updates desirable |
| Form snapshots | Nightly after match stats sync |
| Opportunities | Nightly after form snapshot refresh |
| User-facing search index | Reflects DB within ~5 minutes |

### 6.7 Data quality constraints

- Detect and log fixtures with incomplete data (missing stats, missing lineups, missing odds).
- Flag fixtures with anomalous data.
- Validate ranges on numeric fields.
- **Treat absent data as absent, not as zero.** Missing corner count is `null`, not `0`. Filters with null data treat as "insufficient sample" (auto-fail).

### 6.8 Multi-source data integration

Per D-041: platform must be architecturally prepared to ingest data from sources beyond API-Football.

- Identify data provenance per record.
- Support conflict resolution when sources disagree (per-source priority).
- Support source-specific sync workflows.

### 6.9 Personal data and GDPR

Personal data captured:
- Account identifiers (email, display name, optional avatar)
- Subscription and billing data (references; Stripe handles details)
- Behavioral data (search history, saved strategies, shortlist, accumulators, backtest history)
- Session and authentication data

Requirements (per D-042):
- **Right of access** — full data export per 5.2.
- **Right of erasure** — soft delete with grace period; hard delete on request or expiration.
- **Right of rectification** — profile correction per 5.2.
- **Data minimization** — capture only what's needed.
- **Consent** — captured at signup.
- **Data Processing Agreement** with each subprocessor (Stripe, Supabase, etc.).

---

## 7. Operational Requirements

### 7.1 Data sync workflows

| Sync workflow | Required cadence | Notes |
|---|---|---|
| Master nightly sync | Nightly | Leagues, teams, standings, fixtures, match stats |
| Odds sync | Daily morning + intraday on match days | All covered markets for upcoming fixtures |
| Lineup sync | Every 3–4 hours on match days | Concurrent worker pattern |
| Player stats sync | Weekly | Even though Player Props is Phase 2 — data collected from launch |
| New leagues discovery | Within nightly sync | Per 4.2 |
| Historical odds backfill | Pre-launch operational task | Per D-025 |

**Required behaviors:**
- Resumability after interruption.
- Deduplication.
- Error logging.
- Per-source rate limit awareness.
- API budget tracking.
- Incremental sync where possible.

### 7.2 Computed-layer workflows

| Workflow | Cadence | Notes |
|---|---|---|
| Team form snapshot recomputation | Nightly after match stats sync | Per D-016 |
| Opportunities computation | Nightly after form snapshot recomputation | Per D-030 |
| Best Picks regeneration | Nightly after opportunities | Per D-034 |
| Pre-built strategy performance refresh | Configurable | Per 5.6 |
| On-demand recomputation triggers | As needed | After major data changes |

- Workflows are dependency-aware.
- Failure of upstream blocks downstream and surfaces in admin observability.
- Workflows are independently restartable.

### 7.3 Background job infrastructure

Per D-017:
- Queue persistence — jobs survive worker restarts.
- Concurrency control — configurable cap on simultaneously running jobs.
- Priority queues — paid users' jobs jump ahead.
- Per-user rate limits.
- Job lifecycle: submitted → queued → running → completed/failed/cancelled.
- Progress reporting (real percentage per D-018).
- Result persistence (tier-based retention per D-019).
- Cancellation by users on their own jobs.
- Failure handling: worker exceptions caught; user-friendly error context.

**Job types in MVP:**
- Backtest runs.
- On-demand opportunities recomputation.
- Pre-built strategy backtest refresh.
- GDPR data export generation.
- Historical odds backfill (one-time).

### 7.4 Caching infrastructure

- Cache keys deterministic.
- Cache invalidation triggered by relevant data writes.
- Manual cache clear capability for admins.
- Cache size limits.
- **Cache never the source of truth** — every cached result reproducible.

### 7.5 Admin capabilities (MVP)

- Trigger manual sync for league/fixture/full domain.
- View sync job status and recent errors.
- View API budget consumption.
- View background job queue status.
- Cancel any running job (admin override).
- Manage feature flags / gating configuration (per D-037).
- Manage tier mapping.
- Manage pre-built strategy library.
- Manage methodology version.
- Grant/revoke complimentary subscriptions.
- View user accounts for support.
- Trigger user data export on behalf of user.
- Trigger account hard-delete on GDPR request.

**Phase 2:** full admin dashboard UI, bulk operations, audit log UI, user impersonation with audit trail.

### 7.6 Observability

Telemetry visible to admin:
- Sync job health.
- API budget consumption per source.
- Background job queue depth and processing time.
- Database health.
- Application error rates.
- User-facing performance.
- Subscription state changes.

### 7.7 Failure handling

Graceful degradation:
- External data source unavailable → sync fails, retries on next cadence; application continues serving cached/historical data.
- Background workers down → queue accumulates; honest queue status.
- Caching layer down → fall back to direct database queries.
- Database read replicas down → primary serves; degrade to read-only if primary also affected.
- Stripe webhooks delayed → subscription state lags reality; reconciliation job catches drift.

### 7.8 Security and rate limiting

- Rate limiting per IP/session/user.
- Input validation on all user inputs.
- SQL injection prevention through parameterized queries.
- Secrets management — never in source control.
- Audit logging of admin actions.

### 7.9 Disaster recovery

- Database backups — automated, regular, restorable.
- Point-in-time recovery for user-data layer.
- Sync log retention.
- Raw layer retention enables data reconstruction.

---

## 8. Non-Functional Requirements

### 8.1 Performance

| Operation class | Target (p95) |
|---|---|
| Page load | < 1 second |
| Tab/view switch | < 200ms |
| Search query | < 300ms |
| Filter analysis (typical) | < 3 seconds |
| Filter analysis (heavy) | < 10 seconds |
| Backtest job (typical end-to-end) | < 10 seconds |
| Backtest job (heavy end-to-end) | < 60 seconds |
| Add to shortlist | < 300ms |
| Save / load strategy | < 500ms |
| API endpoint p95 (general) | < 500ms |

### 8.2 Scalability

- Concurrent users: 1,000+ at launch; architecture should not require fundamental redesign for 10x growth.
- Data volume: storage grows linearly; query performance must not degrade with table growth.
- User-private data scales with user base.
- Worker pool horizontally scalable.

Required:
- Stateless application servers.
- Database read replicas.
- Worker pool independently scalable from web tier.
- Caching layer absorbs read load.

### 8.3 Availability

| Component | Required uptime |
|---|---|
| User-facing read-only browse | 99.9% |
| User-facing authenticated actions | 99.5% |
| Sync workflows | Best-effort; no SLA |
| Background job processing | 99% |

Maintenance windows acceptable if pre-announced.

### 8.4 Security

- Auth tokens — short-lived access + refresh tokens.
- Authorization on every endpoint.
- Row Level Security on user-private tables.
- Service role isolation.
- Secrets management.
- HTTPS everywhere.
- CSRF protection.
- XSS protection — output encoding by default.
- Dependency vulnerability scanning.
- Audit logging.

Not stored: credit card data (Stripe handles), real-money transactions.

### 8.5 Privacy and data protection

Per Section 6.9 and D-042. Subprocessor DPAs required. Data residency depends on Q-002 and Supabase region. Sensitive data never logged.

### 8.6 Observability

Per 7.6.

### 8.7 Maintainability

- Deployment automation via CI/CD (GitHub Actions).
- Versioned database migrations.
- Feature flag changes without code deployment (per D-037).
- Configuration-based, not hard-coded.

### 8.8 Compliance

- GDPR per Section 6.9.
- PCI compliance inherited via Stripe.
- Cookie consent / ePrivacy for EU visitors.
- Accessibility — target WCAG 2.1 Level AA where reasonable.
- Terms of service and privacy policy required at signup.

**Gambling-adjacent compliance:**
- Platform is analytics/information service, not gambling operator.
- Jurisdictional compliance is legal/product work, out of scope here.
- Architecture must support geographic restrictions (capability requirement, not launch commitment).

### 8.9 Cost and budget awareness

Operational costs to manage:
- API-Football call budget.
- Database storage growth.
- Background worker compute.
- Caching layer sizing.
- Hosting costs (Vercel, Railway/Fly.io, Supabase).

Expose cost-relevant telemetry.

---

## 9. Pages & User Flows

Per the cleanup pass and D-037, **specific page composition, layouts, tab structures, and visual flows are product design with Stratos**, not requirements.

### 9.1 Required page concepts (MVP)

| Page concept | Required | Access |
|---|---|---|
| Public marketing / landing | Yes | Anonymous |
| Pricing | Yes | Anonymous |
| Terms of service, Privacy policy, About | Yes | Anonymous |
| Signup / Login / Password reset | Yes | Anonymous |
| Email verification | Yes | Post-signup |
| Match Analysis | Yes | All (subject to gating) |
| Backtest | Yes | Authenticated only |
| Saved Strategies | Yes | Authenticated only |
| Pre-built Strategies library | Yes | All (tier-gated within) |
| Best Picks | Yes | All (tier-gated within) |
| Event Page | Yes | All (per-view gated) |
| Team Page | Yes | All (per-view gated) |
| League Page | Yes | All (per-view gated) |
| Shortlist | Yes | Authenticated only |
| Backtest History | Yes | Authenticated only |
| Profile / Settings | Yes | Authenticated only |
| Subscription Management | Yes | Authenticated only |
| Admin pages | Yes | Admin role only |
| Error pages | Yes | All |

### 9.2 Cross-cutting UI requirements

- Trial status visibility on every authenticated request so frontend can render trial UI.
- Upgrade prompts on gated features.
- Disclaimer banner on analytical-output surfaces (per D-038).
- Search box accessible from every page.
- Theme toggle and language switcher in settings.

### 9.3 Anonymous vs authenticated routing

- Pages listed as "all users" accessible without auth.
- Authenticated-only pages redirect to login with return-URL preservation.
- Admin pages reject non-admin users.

---

## 10. API Endpoint Inventory

Logical endpoint surface required. Specific shapes are API design work.

### 10.1 System
- Health check, cache management (admin), tier mapping inventory, country list, league list, completion %.

### 10.2 Auth and account
- Signup (email/password, Google OAuth), login, logout, password reset request/confirm, email verification, email change, get current user, update profile, change password, delete account, export user data.

### 10.3 Subscriptions and billing
- Get subscription, billing history, initiate Stripe checkout, billing portal session, start free trial, cancel subscription, Stripe webhook receiver.

### 10.4 Search
- Unified search (with date filter), search history, clear search history.

### 10.5 Matches and filtering
- Filter analysis, upcoming fixtures, today's matches, available markets/selections/lines.

### 10.6 Backtest
- Submit job, job status, get result, cancel job, list history, get specific past run.

### 10.7 Strategies
- List, get, create, update, delete, duplicate, list pre-built, copy pre-built to user.

### 10.8 Shortlist and accumulators
- List shortlist (grouped), add item with folder, move between folders, remove item, refresh odds, list saved accumulators, create, update, delete.

### 10.9 Event Page, Team Page, League Page
- Get Event Page data (per fixture, subject to gating), get Team Page, get League Page, get standings.

### 10.10 Opportunities and Best Picks
- Get Opportunities per fixture, get Best Picks feed.

### 10.11 Player Props (Phase 2)
- Endpoints exist as Phase 2 work. Lineup endpoints exist at MVP for data collection but not user-facing.

### 10.12 Admin
- View user, manual sync trigger, sync status, API budget, job queue status, cancel job, feature flag management, tier mapping, pre-built library management, methodology version, complimentary subscription grants, data export trigger, hard-delete trigger.

### 10.13 Design principles
- REST conventions.
- Authentication required on user-private endpoints.
- Server-side gating enforcement.
- Rate limiting per 7.8.
- Versioning strategy (TBD architecture).
- Consistent error response shape.
- Pagination on list endpoints.

---

## 11. Business Rules & Constraints

### 11.1 Form sample rules
- A match counts toward form if its league's tier is in user's currently selected tier scope.
- Friendlies tier off by default in user scope filters.
- Minimum sample size; insufficient auto-fail.
- `sample = "season"` requires minimum 3 matches.
- Shootout goals don't count; ET goals do.
- Tier scope applies to backtest historical samples too.

### 11.2 Soft-cap on tier downgrades
- Existing items above new limit retained; new creation blocked until under.
- Applies to: saved strategies, shortlist items, accumulator legs, saved accumulators, backtest history retention.

### 11.3 Soft-delete grace periods
- Account deletion: default 30 days, configurable.
- Strategy deletion: default 30 days.
- Hard delete on explicit GDPR request bypasses grace period.

### 11.4 Trial mechanics
- One per account, one per email.
- No card required.
- Trial elevates user to configured paid tier for duration.
- Trial expiry reverts user to free; no charge.

### 11.5 Subscription state and gating
- Paid access requires status `active` or `trialing`.
- Canceled retains access until period end, then reverts to free.
- Past-due enters grace period before cancellation.
- All gating server-enforced.
- All gating values admin-configurable.

### 11.6 Odds handling
- Backtest uses captured real odds only; no assumed-odd fallback.
- Fixtures without captured odds for the selection excluded from backtest.
- Any-line mode resolves middle line per-fixture.
- Any-line + allowed-lines whitelist restricts eligibility.

### 11.7 Tier mapping
- One tier per league at any time.
- New leagues default to unmapped (`?`); excluded from users until admin reviews.
- Admin override never gets overwritten by auto-scoring.
- Audit log captured in MVP.

### 11.8 Analytical methodology
- Deterministic and explainable; no opaque ML in MVP.
- Methodology versioned; computations stamped with version.
- Coefficients admin-tunable.

### 11.9 Caching
- Caches never source of truth.
- TTLs per feature.
- Manual cache clear available to admin.

### 11.10 Tier scope universality
- The tier scope rule applies to all analytical surfaces: Match Analysis, Backtest, Event Page, Team Page, Best Picks.

---

## 12. Edge Cases & Error Conditions

### 12.1 Data quality
- Missing match stats post-finish: detected, logged, excluded from dependent samples.
- Anomalous data: flagged for admin review.
- League with no standings: standings-dependent features show "n/a"; others unaffected.
- New season early: features show "limited data" notices.
- Mid-season restructure: documented limitation.

### 12.2 Team and player
- Team transferred between leagues: history follows team.
- Newly promoted: history spans leagues.
- Defunct teams: archived, accessible.
- Same name across countries: disambiguated in search.

### 12.3 Fixture
- Postponed/cancelled: excluded from samples; status preserved in shortlist.
- Abandoned: excluded entirely.
- HT stats missing: HT-dependent filters exclude match.

### 12.4 Odds
- No captured odd: excluded from backtest; opportunities not computable for that market.
- Any-line with no eligible line: excluded in strict.
- Same-game multi-leg: allowed with advisory.

### 12.5 User and account
- OAuth/email collision: offer to link.
- Downgrade exceeding limits: soft-cap.
- Trial chained via duplicate accounts: blocked by email uniqueness.
- Compromised account: admin-assisted recovery.

### 12.6 Strategy and shortlist
- Removed metric in saved strategy: surfaced visibly on load.
- Renamed tier in saved strategy: auto-mapped.
- Deleted strategy: filed shortlist items move to default.
- Concurrent edits: last-write-wins.

### 12.7 System
- External data source unavailable: graceful degradation.
- Workers down: queue accumulates.
- Methodology version changes: historical preservation.

---

## 13. Out of Scope — Explicit Non-Goals

### 13.1 Real-money handling
- No wagers, no funds, no real-money transactions.
- Accumulators are virtual and informational only.
- Payment processing is for subscription to platform only.

### 13.2 Bet placement and bookmaker integration
- No bet placement on behalf of users.
- No direct API to bookmakers for bet placement.
- Phase 2 may add deep-link or affiliate flows; bet placed on bookmaker's surface, never on platform.

### 13.3 Live in-play features
- Pre-match focused.
- No live odds tracking during matches.
- No live betting features.

### 13.4 Social and community features
- No public profiles, follower systems, comment systems, forums.
- No user-to-user messaging.
- No public leaderboards.
- Strategy sharing: Future.

### 13.5 Automated decision-making for users
- No automatic bet placement.
- No auto-modify of user strategies.
- All decisions remain with the user.

### 13.6 Native mobile apps
- Native iOS and Android apps Phase 3+.
- MVP is web-only (responsive).

### 13.7 Editorial / human-curated content
- No human tipsters selling picks.
- Best Picks and Opportunities are 100% algorithmic.
- Future: paid creator marketplace as long-term possibility; no commitment.

### 13.8 Multi-sport at launch
- Football only at launch.
- Architecture ready; data and feature work for other sports Phase 2+.

### 13.9 Team and organization accounts
- Single-user accounts only at MVP.
- No multi-seat or team billing.

### 13.10 Public API for third-party developers
- No public API for customers to build on.
- Internal API for the platform's frontend only.

### 13.11 Specific data scopes
- Player Props analytics: Phase 2 (data collected MVP).
- Goalkeeper-specific metrics: Phase 2.
- Player-prop-specific betting markets: Phase 2.
- Historical odds older than 12 months: depends on data backfill scope.

### 13.12 Specific compliance/legal scopes
- Jurisdictional gambling-content licensing: legal/product, out of scope.
- Tax handling on subscription revenue beyond Stripe: out of scope.
- KYC/AML for users: out of scope.

---

## 14. Open Questions Index

### 14.1 Carried from PROJECT_STATUS.md

| ID | Question | Blocks | Owner |
|---|---|---|---|
| Q-001 | Final pricing model and tier-specific values | Stripe setup, gating values | User |
| Q-002 | Backend hosting: Railway vs Fly.io | Deployment | User + Claude |
| Q-003 | Domain name | Branding, deployment | User |
| Q-004 | Background job system specifics | Architecture session | Claude (recommendation) |
| Q-005 | Free tier visibility of player props | Phase 2 launch | User |
| Q-006 | Next sport after football | Phase 2+ | User |

### 14.2 Raised during this requirements session

| ID | Question | Status |
|---|---|---|
| Q-NEW-A | Specific filter availability per tier | Open — admin-configurable |
| Q-NEW-B | Trial length and re-trial mechanics | Open — admin-configurable |
| Q-NEW-G | "Current season" detection logic | Architecture session |
| Q-NEW-H | "Auto-pick middle line" exact algorithm | Architecture session |
| Q-NEW-I | Auto-scoring algorithm tuning UI | Deferred (Phase 2) |
| Q-NEW-O | Minimum edge threshold for Opportunities | Open — admin-configurable |
| Q-NEW-Q | Methodology version handling on changes | Resolved — preserve old versions |
| Q-NEW-R | Result Probabilities / narrative summary view | Open — product design with Stratos |
| Q-NEW-U | Operational log retention defaults | Admin-configurable |
| Q-NEW-V | Multi-source conflict resolution rule | Deferred (Phase 2) |
| Q-NEW-W | Backup frequency and retention defaults | Admin-configurable |
| Q-NEW-X | Rate limit values per endpoint per tier | Open — admin-configurable |
| Q-NEW-Y | Data residency / hosting region | Decide before deployment |
| Q-NEW-Z | Cookie consent banner mechanism | Product/legal decision |
| Q-NEW-AA | Geo-restriction launch policy | Legal/product decision |

### 14.3 Resolved during this session

- Q-NEW-C (friendlies / continental competitions) — resolved by universal tier scope rule.
- Q-NEW-D (league completion data source) — resolved: computed from fixtures played/total per league season.
- Q-NEW-E (auto-pick middle algorithm) — captured as Q-NEW-H.
- Q-NEW-F (tier identifiers) — resolved with the 8-tier ladder.
- Q-NEW-J (migration from v2.7 tier data) — resolved: auto-map + needs_review flag.
- Q-NEW-K (player sample cap) — moot since Player Props is Phase 2.
- Q-NEW-L (Find Players sync vs async) — moot, Phase 2.
- Q-NEW-M (anonymous save strategy) — resolved: no.
- Q-NEW-N (free user save slots) — resolved in direction: 2–3 slots; exact value with Q-001.
- Q-NEW-P (per-tab gating defaults) — resolved: admin-configurable, no defaults locked.
- Q-NEW-S (Team Page opportunities scope) — moot (product design with Stratos).
- Q-NEW-T (past-season view) — moot (product design).

---

*End of REQUIREMENTS.md v1.0*
