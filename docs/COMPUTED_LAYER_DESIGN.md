# COMPUTED_LAYER_DESIGN.md

> **Session 19 deliverable — scoping & design, NOT implementation.**
> This document decides *what* the Computed layer produces, *how* it is computed and stored, *how* it must respect the data landmines we found in S15–S18, and *in what order* we build it. It contains no DDL and no worker code — those come in later sessions, one slice at a time, the way ingestion did.
>
> **Grounded in:** `ARCHITECTURE.md` §4 (data layers), §5 (services & cadence), §6.3 (methodology versioning), the Season Resolver decision (§ "Season Resolver"); `REQUIREMENTS.md` §4.1 (Filter Engine), §4.3 (Backtest), §4.6 (Opportunities), §7.2 (Computed-layer workflows); and decisions D-016, D-030, D-034, D-108, D-109, D-110, D-124.
>
> **Status:** proposed. Decisions below are drafted as D-126…D-133 and become final only when logged into `PROJECT_STATUS.md` §7 at session close.

---

## 1. What the Computed layer is for

**In one sentence:** the Computed layer is where we turn clean curated data into the pre-chewed answers the product sells, so that when a user runs a filter or opens a match, the server does an indexed *lookup* instead of a live *calculation*.

Everything we have built for 18 sessions is the Curated layer: one honest, normalised record per real-world thing (a fixture, a team's match stats, a player's appearance). That data is correct, but it is *raw material*. A user does not want "here are 380 fixtures and their stats" — they want "these 6 upcoming matches fit your strategy, and here is the one bet with the biggest edge." Producing that answer means scanning hundreds of past matches, computing hit rates, comparing to bookmaker odds. Doing that *live*, per request, would be slow and would repeat the same heavy work for every user who runs a similar filter. So we do it **once, nightly, in the background**, and store the results. (`ARCHITECTURE.md` §3, "the commitment"; REQUIREMENTS Architectural Commitment 2.)

**Its consumers (who reads it):**
- The **Filter Engine** (Match Analysis, REQUIREMENTS §4.1) — reads pre-computed team form snapshots and mostly just looks up "did this team clear this threshold often enough."
- The **Event Page / Opportunities** (REQUIREMENTS §4.6) — reads per-fixture opportunities.
- **Best Picks** (REQUIREMENTS §5.7) — reads the high-edge opportunities across all upcoming fixtures.
- The **Backtest Engine** (REQUIREMENTS §4.3) — reuses the *same* form logic against historical fixtures.

**What it must NEVER do:**
- It must never be the source of truth. It is **regenerable** — if we lost the entire Computed layer, we could rebuild it from Curated. Losing it costs compute time, not data (`ARCHITECTURE.md` §4).
- It must never be written by the user-facing `web` service. Only the `job-worker` writes here (`ARCHITECTURE.md` §5). This is architectural: a user request physically cannot corrupt analytical data.
- It must never leak the future into the past. See §3 — this is the single most important rule in the whole layer.

### 1.1 The user concept this layer exists to serve

Stated in the product owner's words, because every technical choice below serves only this:

> A user builds filters — some describing the **home** team, some describing the **away** team (player-prop filters come later) — and gets back the **upcoming fixtures** whose teams match those conditions, ranked by how well they match.

Each filter is a question of the form *"has this team done X often enough in its recent matches?"* (e.g. "scored 2+ goals in ≥60% of its last 10"). A fixture is scored by how many filters pass; the user sets a minimum score, and matches below it are dropped (ScoutEngine prototype §5; REQUIREMENTS §4.1). The mapping from that concept to this design:

| The user wants… | …served by |
|---|---|
| filters on the **home** team *and* the **away** team | the per-team **form base** (§3.3) — home filters read the home team's form, away filters the away team's; the Filter Engine combines them into the fixture score |
| **recent form** with a window *they* choose (last 7? last 15?) | **query-time windowing** over the form base (§3.3) — no window is pre-baked |
| **future events** that match | the **hot tier** (§4.3) — the upcoming window, kept fresh intraday |
| **player props**, later | **Phase 2 player form** (§2, D-131) — sequenced after the team-level MVP |
| answers that feel **instant** | the **cached, index-only, bounded scan** read path (§4.5) |

Everything after this point is *how* we make that concept correct (§3), extensible (§4.2), fresh (§4.3), and fast (§4.5).

---

## 2. The catalogue — what lives in the Computed layer

The layer holds three stored artifacts plus one shared primitive underneath them. They form a dependency chain: each one is computed *after* the one it depends on, nightly (REQUIREMENTS §7.2; `ARCHITECTURE.md` §5).

| Artifact | Grain (one row per…) | Depends on | MVP? | Decision |
|---|---|---|---|---|
| **Season Resolver** *(primitive, not a stored table — see §3)* | — (a function/component) | Curated fixtures + standings | **MVP** | Q-NEW-G shape |
| **Team form base** | team × completed match × measure *(query-time windowing, §3.3)* | Season Resolver + curated match stats | **MVP** | D-016 / D-128 |
| **Per-fixture opportunities** | fixture × market × selection | Form snapshots + curated odds + methodology | **MVP** | D-030 |
| **Best Picks feed** | (a filtered view over opportunities) | Opportunities | **MVP** | D-034 |
| Player form snapshots | player × as-of-date | Resolver + curated player stats + identity links | **Phase 2** | REQUIREMENTS §6.3 |

**Player form snapshots are explicitly Phase 2** (REQUIREMENTS §6.3, §4.4). This matters for our roadmap (§6): the two hardest curated landmines — dual identity (D-110) and id=0 synthetics (D-124) — only become *critical* at the player-form slice, which is Phase 2. They do not block the MVP team-form work.

The **cadence chain** (nightly, dependency-aware, each step restartable, upstream failure blocks downstream — REQUIREMENTS §7.2):

```
match-stats sync ──▶ team form base ──▶ opportunities ──▶ Best Picks
                          (D-128)              (D-030)          (D-034)
        (Season Resolver is called *inside* form-base build + opportunities)
```

---

## 3. Point-in-time correctness & the Season Resolver — the heart of the design

**This is the section that justifies making S19 a design session.** Get this wrong and every number the product shows is quietly a lie.

### 3.1 The landmine, in plain language

When we tell a user "Arsenal scored in 70% of their last 10 matches," the phrase *last 10* is defined **relative to a specific date**. For an upcoming match on 1 March, "last 10" means the 10 completed matches *before* 1 March. For a **backtest** of a match that was played on 1 October last year, "last 10" must mean the 10 completed *before* 1 October last year — it must **not** include anything that happened on or after that date.

If a backtest accidentally includes future results, it becomes wildly, silently profitable — because it is effectively betting with knowledge of what already happened. This is called **look-ahead bias**, and it is the classic way analytics products fool themselves. Our whole value proposition is "trusted, transparent research"; a backtest that leaks the future destroys that in one stroke.

So the rule, stated once and enforced everywhere:

> **Every form number is computed *as of* a date, and may only see completed fixtures strictly *before* that date.**

### 3.2 The Season Resolver (D-127)

Rather than re-implement "which matches count, and in what order" in four different places (filter engine, backtest, form-snapshot computer, opportunities engine), the architecture already commits to a **single stateless component** that answers one question (`ARCHITECTURE.md` "Season Resolver"; Q-NEW-G):

> **Given `(team_id, as_of_date, tier_scope)`, return the ordered list of fixtures that count as this team's relevant history as of that date.**

Every consumer calls this one implementation. That guarantees the filter engine and the backtest engine agree by construction — they can't drift, because they share the resolver. The resolver's contract:

- **Input:** a team, an as-of-date, and a tier-scope (which league tiers the user's analysis is restricted to — REQUIREMENTS §4.2, the "Tier scope" glossary term).
- **Output:** the team's completed fixtures, strictly before the as-of-date, within the tier-scope, ordered most-recent-first. The "last N" is then simply the first N of that list.
- **It is stateless and pure:** same inputs → same output, always. It reads Curated, computes nothing persistent, writes nothing. That makes it trivially testable (§8).

**Two real design questions the resolver forces us to answer** (I am flagging these rather than silently deciding — Rule 9):

- **Q-NEW-BP — as-of-date granularity.** We can't snapshot "every possible date." The natural choice: compute a snapshot **as of each fixture's kickoff date** (so every match that ever needed a form number has one) plus a rolling **"today"** snapshot for upcoming fixtures. This keeps the snapshot table finite and aligned to real decision points. *Proposed default: kickoff-date + today. Confirm at review.*
- **Q-NEW-BQ — split-season scope (Greek Super League).** Greece splits into Regular Season → Championship/Relegation groups (D-100, S13). Does a team's Championship-round match belong in the *same* form window as its Regular-Season matches, or are they separate competitions? This changes what "last 10" means for half our launch market. *Proposed default: same continuous window (they are the same team, same season, chronological), with the group recorded so a future methodology can weight them differently. Confirm at review — this is a genuine sporting-logic call, not a purely technical one.*

### 3.3 The form base on top of the resolver (D-128, revised in S19)

**A correction driven directly by how users interact — and it's the important one.** In the filter, the user controls the window: "last N" is user-set (roughly 1–40), and so are the threshold and the percentage (ScoutEngine prototype §5.1/§5.3; REQUIREMENTS §4.1). There is therefore **no single window to pre-bake.** Storing "last-10 goals average = 1.4" is useless the moment the user picks last-7 or last-15. So we deliberately do **not** pre-store finished per-window answers. Instead:

- We pre-compute the **form base**: for each team, **one ordered row per completed match per measure** — the measure's value in that match, plus context (home/away split, opponent, opponent-quality *as of that date*, competition/group). Ordered most-recent-first; point-in-time by construction, because the ordering *is* the Season Resolver's output.
- **"As of date X" becomes a query predicate** (`match_date < X`), not a stored key — so any as-of-date works for free, with no snapshot explosion.
- The final test — *"≥ threshold in ≥ pct% of the last N"* — is computed **at query time** as a bounded scan over at most ~40 rows per team. That's microseconds, and it is the *only* way to honour user-tunable N / threshold / percentage.

**The pre-computation boundary, stated once:** pre-compute the expensive, reusable *ingredients* (the ordered per-match values and the opponent-quality tags, which are costly to derive live because they need standings as-of-date); compute the cheap, user-specific *final aggregation* live. This is both more flexible (any N, any threshold, any date) **and** fast (§4.5) — the two stop being in tension once we stop pre-baking answers.

The **measures** the form base carries (goals, corners, cards, shots, possession, form points, etc.) are **defined by REQUIREMENTS §4.1** and governed by the metric registry (§4.2) — not re-invented here. Fixed-window numbers that appear on a card or drive a Best-Picks default (e.g. "form last 5") are an *optional derived convenience* materialised on top of the form base, never the primary structure. Exact column/measure names are confirmed against `CURATED_SCHEMA_REFERENCE.md` at implementation — **not hand-typed here** (standing rule).

---

## 4. Computation, storage, extensibility & freshness

### 4.1 Schema, ownership, idempotency

- **Its own schema.** The Computed layer lives in a dedicated `computed` Postgres schema, consistent with our one-schema-per-layer convention (raw / curated / …). (D-126.)
- **Written only by the job-worker**, chained off sync completion, plus on-demand and event-driven triggers (§4.3; REQUIREMENTS §7.2; `ARCHITECTURE.md` §5). The `web` service never writes here.
- **Idempotent by natural key.** Every artifact upserts on its grain key (§2). A re-run overwrites cleanly; a crashed run resumes without duplication. This mirrors the transaction-per-unit discipline that carried our ingestion workers through three mid-run interruptions (S17).
- **Regenerable from Curated.** No artifact is authoritative; all are rebuildable. (D-126.)

### 4.2 Extensibility — adding a KPI later must not be a rebuild (D-134)

**This is a first-class design goal, not an afterthought:** we must be able to invent a new KPI six months from now and add it *without* a schema migration, a backfill scramble, or touching unrelated code. There are two ways to store form metrics, and the choice *is* this goal:

- **Wide table** — one column per metric-and-window (`goals_scored_last10`, `corners_for_last10`, …). Reads look trivial, but it fails **twice**: every new KPI is a schema migration (alter, backfill, edit worker, edit API — the "messing up the whole tables" fear), *and* it hard-codes the window (`last10`), which the user actually controls (§3.3). A wide table literally cannot represent "user picked last-7."
- **Long (tall) form base** — one row per `(team_id, match_date, metric_key, split)` carrying `value`, plus context (opponent, opponent-quality-as-of-date, group), `coverage_present`, `methodology_version`. Adding a KPI = write rows under a new `metric_key`. **Zero DDL** — *and* the window is not baked in, so any user N works (§3.3).

**Decision (D-134): the long-format form base (§3.3) is the extensibility spine, fronted by a metric registry.** The **metric registry** is a small config table describing each KPI: its `metric_key`, human description, the curated measure(s) it reads, its **NULL policy** (`zero` | `unknown`, per D-129), and whether it is **coverage-aware** (per D-130). We store per-match *values*, never per-window aggregates or user thresholds — those are query-time (§3.3). Consequences:

- **Adding a KPI = one registry row** (+ one small pure function only if it needs genuinely new math). No migration, no table surgery, no risk to existing metrics, and it immediately works at every N the user can pick.
- The awkward-data policies (D-129 NULL handling, D-130 coverage) **live on the metric definition**, so they travel with the metric automatically — a new metric declares its own policy and the compute engine honours it generically.
- **Performance escape hatch:** if a handful of the hottest *fixed-window* numbers (card displays, Best-Picks defaults) ever need extra speed for the <3s / <500ms targets (REQUIREMENTS §8.1), we add a *derived* index-only projection for only those — built *from* the form base, never a second source of truth, and added only if measurement shows we need it (don't pre-optimize).

This is the concrete answer to "can we add KPIs we haven't thought of yet without a mess": yes — KPIs are **data (registry rows), not columns.**

### 4.3 Freshness — tiers, not one nightly batch (D-135)

"The sync must be very frequent — this is a real app." Correct. The reconciliation rests on two distinctions.

**Two clocks.** *Ingestion sync* (the upstream workers pulling facts from API-Football — how fast new facts land) and *compute refresh* (this layer — how fast KPIs reflect those facts) are **different machinery**. This document owns the second; the first is an adjacent lever (and affordable — Ultra is flat-rate with ~75k/day budget against a few-thousand actual, so frequent polling costs us nothing extra).

**The past never changes.** A match played last October has a fixed history, so its snapshot is computed **once and frozen**. This means we never need to recompute the universe on a fast clock — only the slice that can still move.

**So the freshness design is tiered (D-135):**

| Tier | What | Refresh cadence | Why |
|---|---|---|---|
| **Frozen** | Snapshots as-of any *past* date | Computed once; never recomputed (except a rare corrected past result → targeted recompute) | History is immutable |
| **Hot** | Snapshots for the **upcoming window** (today + next few match-days) + opportunities for upcoming fixtures | **Event-driven, intraday** — retriggered when new match stats land (~1 h after a fixture ends, §6.6) or odds move; nightly full sweep as the safety net | This is the *only* window users query live, and the only one whose inputs are still changing |

**Grounding in how users actually interact.** Users build a filter and run it against **upcoming** matches, expecting a result in **under 3 seconds** (REQUIREMENTS §8.1); they open an **event page** for an upcoming fixture to see opportunities; they scan the **Best Picks** feed of upcoming high-edge bets (REQUIREMENTS §4.1, §4.6, §5.7). Nobody runs a live filter against a 2019 season. So the *upcoming window* is exactly what must be both **pre-computed** (for the <3s lookup) and **fresh** (intraday on match days, §6.6). Tiering gives us "very frequent where it matters, cheap everywhere else."

The exact trigger wiring (event hooks vs short-interval polling of the hot window) is an implementation detail for the relevant slice; the design commitment is the tiering and the event-driven hot refresh.

**Per-category cadences — different clocks for odds vs fixtures vs stats (and that's correct).** There is no single "sync." Each data type refreshes on its own schedule (REQUIREMENTS §6.6): match stats within ~1 h of a fixture ending, lineups every 3–4 h on match days, odds daily-plus-intraday, standings daily, fixtures nightly-plus-intraday on match days. These are *ingestion* schedules (upstream of this layer, and cheap — flat-rate Ultra), but they matter here because **the hot-tier compute refresh subscribes to each category independently**: a fresh odds pull re-runs opportunities for the affected fixtures only; a landed match stat re-runs the affected slice of the form base only. So "a different frequency for odds than for fixtures" isn't something we bolt on — it falls out naturally as independent triggers feeding independent recomputes. *(The precise per-category ingestion schedule is owned by the ingestion/scheduling work, not this doc; it's wired when we set up the unattended cadence — the same session Q-NEW-BL's exit-code hardening lands, §7.)*

### 4.4 Full vs incremental recompute; methodology stamp

- **Full vs incremental.** The normal refresh is incremental — recompute only new/affected rows (the hot tier). A full rebuild from Curated is always available as an on-demand job (regenerability, §4.1). Both modes must produce identical results.
- **Methodology-version stamped.** Every computed row carries the methodology version that produced it (§5), including every row in the form base.

### 4.5 Performance — how "ultra-fast" is actually achieved (D-136)

Your instinct is right: a wide table with many columns is neither flexible nor obviously fast. Speed comes from **bounded work + indexes + cache**, *not* from column count:

1. **Bounded final step.** The filter's live computation is a scan over ≤~40 rows per team (§3.3), never a full-table scan. Small N is the whole game — the work per team is tiny and constant regardless of how much history we hold.
2. **Index-only scans.** The form base is indexed on `(team_id, metric_key, split, match_date DESC)` with `value` carried in the index, so "last N of this measure for this team" is answered from the index without touching the table heap.
3. **Partitioning + cheap date pruning.** Partition the form base by season (and/or league) so a query touches only relevant partitions; a BRIN index on `match_date` makes range pruning almost free.
4. **Application cache (Redis / Upstash — already in our planned stack).** Hot filter *results* and hot team form bases are cached, invalidated by the hot-tier refresh events (§4.3). This is the grown-up version of the prototype's in-memory LRU (4 h TTL, 8k entries), moved out of process so every server instance shares it.
5. **Optional fast-lane materializations.** For the few highest-traffic *fixed-window* numbers (card displays, Best-Picks defaults), a tiny derived index-only projection — added only if measurement shows the live path misses the <3s / <500ms targets (§8.1). Don't pre-optimize.
6. **Heavy work is async.** Backtests scan many historical fixtures (targets <10s typical, <60s heavy, §8.1); those run as Dramatiq background jobs, never blocking a live request.

Net: the live read path is a **cached, index-only, bounded scan.** That's how the app stays fast *and* stays flexible — the two only conflicted while we were pre-baking answers, and §3.3 stopped doing that.

---

## 5. Methodology versioning — mechanism now, numbers later

The math behind hit rates, opportunities, and Best Picks — the coefficients, look-back sizes, weighting factors, edge thresholds — is **versioned** (`ARCHITECTURE.md` §6.3; REQUIREMENTS Configuration Layer). Every Computed row is **stamped with the methodology version that produced it**.

**Why it matters:** methodology *will* change as we improve. If old outputs aren't stamped, "did this strategy work last season?" becomes unanswerable — you'd be comparing numbers made by different math and not know it. Stamping keeps historical performance honest across methodology changes.

**What S19 decides (D-132):** *that* we version, and the *mechanism* — a methodology version identifier read from the Configuration Layer, written onto every Computed row, immutable once stamped.

**What S19 deliberately does NOT decide:** the actual v1 numbers. Choosing the real look-back sizes, weightings, and edge thresholds is a substantial modelling exercise and gets its **own dedicated session** before the Opportunities slice. This document sets up the slot; it does not fill it. *(This is the "designing on sand" boundary I flagged — opportunities and Best Picks are structurally designed here, numerically designed later.)*

---

## 6. The curated-data landmines the Computed layer must respect

This is where the open questions from S15–S18 get a home. Each is a way the curated data can quietly produce a wrong KPI if the compute step is naïve. The design commitment for each:

### 6.1 Per-measure NULL policy (D-108 → D-129)

`NULL` does **not** mean the same thing for every measure. We proved (S15, 1,232 team-rows, 0 counterexamples): `red_cards IS NULL` ≡ **zero** (safe to treat as 0 in a sum or average), but `expected_goals IS NULL` ≡ **genuinely unknown** (must NOT be treated as 0 — a 0 would drag the average down and lie).

**Design commitment (D-129):** the Computed layer carries a **per-measure classification** — each measure is either *null-means-zero* (fold NULLs in as 0) or *null-means-unknown* (exclude from BOTH numerator and denominator, and report the sample size actually used). This classification is the `null_policy` column on the metric registry (§4.2), seeded from D-108, stamped and auditable — **not** a blanket per-table rule (the blanket "NULL = auto-fail" rule we once had is wrong, D-108). The exact per-column assignment is confirmed against `CURATED_SCHEMA_REFERENCE.md` at implementation.

> **Docs-reconciliation flag:** REQUIREMENTS §6.7 still states the *old* blanket rule — "Filters with null data treat as insufficient sample (auto-fail)." D-108 (S15) overturned that in favour of per-measure handling, and D-129 encodes the correct version. **REQUIREMENTS §6.7 should be updated to match in a later docs pass** so the two documents agree (Rule 8).

### 6.2 Date-windowed coverage, especially xG (D-109 → D-130)

xG coverage is **date-windowed**: 100% null before Feb 2026 for Greece, partial in Feb, full after (D-109). A "last 10 xG average" computed blindly across that boundary silently mixes real values with unknowns — and the `cov_*` boolean flags structurally *cannot* express "covered from this date" (D-109).

**Design commitment (D-130):** xG-family KPIs are **coverage-aware**. A form window computes and reports the fraction of its sample that actually had the measure; below a configurable coverage threshold, the KPI is emitted as **"insufficient coverage"** — never as a confident-looking number built on two data points. This protects the "trusted research" promise directly: we would rather show "not enough data" than a precise-looking lie.

### 6.3 Player identity — dual identity (D-110) & id=0 synthetics (D-124)

*(Relevant at the **player** form slice, which is Phase 2 — noted here so it isn't rediscovered later.)*

- **Dual identity (D-110):** the same player appears under different vendor ids across endpoints; we resolved this with `curated.player_identity_links` (S16). Any player-level aggregation MUST canonicalise `player_id` through that link table **first**, or one player's stats get split across two ids and every per-player rate is wrong.
- **id=0 synthetics (D-124):** "Unidentified player" rows carry `source_ref` like `"0:{fixture}:{team}:{jersey}"`. These are **not real identities** and must be **excluded from player-identity KPIs** (you can't compute "this player's shot rate" for a player the vendor couldn't name). BUT their match events still happened for the *team* — so their shots/cards still count toward **team** totals. The `"0:%"` marker is the exclusion key (D-124).

**Design commitment (D-131):** player-level compute canonicalises via identity links and excludes `"0:%"` synthetics from player metrics while retaining their events in team aggregates.

### 6.4 Out of scope for KPI compute

`height`/`weight` heterogeneity (D-111 / Q-NEW-BD) is a **player-bio display** concern, not a KPI input — the Computed layer does not consume it. Noted so it isn't accidentally pulled into scope.

---

## 7. The slicing roadmap (S20 onward) — *how nothing gets dropped, only sequenced*

This is the section that answers "if we do the Computed layer, do we abandon everything else?" — **no.** The roadmap sequences the remaining work; the side quests slot in at the point where they actually block something.

**Main line (product value):**

1. **S20 — Season Resolver.** The shared primitive (§3.2). Standalone, pure, testable against seasons whose shape we already know (EPL 38-round, Greek split-season, Brazil calendar-year). Nothing downstream can be trusted until this is right, so it goes first.
2. **S21+ — Team form snapshots.** Built on the resolver, MVP metric set from REQUIREMENTS §4.1, with the D-129/D-130 NULL/coverage policies applied. Likely more than one session (metric families in groups).
3. **Methodology session** — lock the v1 numbers (§5). Prerequisite for step 4.
4. **Opportunities engine** (D-030) — needs form snapshots + odds + the methodology numbers.
5. **Best Picks** (D-034) — a thin, high-edge filter over opportunities; cheap once step 4 exists.
6. **Phase 2 — Player form snapshots** — where D-131 (identity links + id=0 exclusion) becomes critical.

**Where the side quests slot in (sequenced, not dropped):**

- **Q-NEW-BL (worker exit codes)** → **right before the first scheduled nightly run of the computed chain.** That is the moment execution becomes *unattended*, which is exactly when "exits 0 despite failures" becomes dangerous. It's cheap and it lands the session we wire the nightly cadence — not before (we're still running everything by hand today).
- **Q-NEW-BK (Brazil venue aliases)** → only when a KPI or feature reads venue. No MVP form metric does, so this waits until venue-based analytics — self-contained, ready when needed.
- **Q-NEW-BG (lineup mis-slot detector)** → a lineup-data-quality item; affects lineup-derived features, not core team form. Slots in alongside any lineup-consuming feature.
- **`curated.coaches` (D-112)** → enrichment; slots in when a coach-based feature appears.
- **Q-NEW-BP / BQ (resolver granularity & split-season scope)** → decided *at the top of S20*, because the resolver can't be built without them.

The point: the flat list of open questions that feels like "everything at once" becomes an **ordered map** the moment we fix the build order. Each item has a *when*.

---

## 8. Cross-check discipline — how we trust each number

Our standing lesson (held four straight sessions, S15–S18): **design the cross-check, don't trust the model.** Every computed artifact ships with a designed verification before it's believed:

- **Season Resolver:** for a known team and date, assert the returned fixture set matches a hand-derived list; and the **look-ahead guard** — assert *no* returned fixture has a date ≥ the as-of-date (this is the single check that catches future-leakage, the §3 landmine).
- **Form base:** recompute one team's last-5 *and* last-13 hit rate for a measure by hand from curated as of a known date, and assert equality against a live query over the form base (proves user-tunable N works); assert idempotency (re-run → identical rows, `created_at` preserved).
- **NULL policy (D-129):** assert a *null-means-unknown* measure never contributes a 0 to an average — compare the computed denominator against a hand-filtered "rows where the measure is present" count.
- **Coverage (D-130):** on a team straddling the xG coverage boundary, assert the KPI reports the correct coverage fraction and flips to "insufficient" below threshold.
- **Opportunities/Best Picks (later):** cross-check platform hit-rate vs bookmaker implied probability against a hand-computed edge on a sample fixture.

Each of these is a *raw-vs-curated / hand-vs-computed* comparison — the exact shape that caught S18's five silently-dropped players.

---

## 9. Decisions proposed this session (draft — finalise at close)

| Draft ID | Decision |
|---|---|
| **D-126** | Computed layer lives in its own `computed` schema; regenerable from Curated; written only by the job-worker (nightly + on-demand). |
| **D-127** | A single stateless **Season Resolver** `(team_id, as_of_date, tier_scope) → ordered fixtures strictly before as_of_date` is the shared primitive for filter engine, backtest, form-snapshot computer, and opportunities engine. |
| **D-128** | Team form is stored as an ordered **form base** — one row per `(team_id, match_date, metric_key, split)` with the per-match value + context — **not** as pre-windowed aggregates. Point-in-time via strictly-before ordering; **as-of-date is a query predicate, not a stored key.** User-tunable N / threshold / percentage are applied **at query time** as a bounded (~≤40-row) scan. Optional fixed-window projections may be derived for display/defaults only. |
| **D-129** | Per-measure NULL policy: each measure classified *null-means-zero* or *null-means-unknown* (seeded from D-108); unknown measures excluded from numerator and denominator with sample size reported. |
| **D-130** | xG-family (and other date-windowed) KPIs are coverage-aware; below a coverage threshold the KPI is emitted as "insufficient coverage," never as a confident number (from D-109). |
| **D-131** | Player-level compute canonicalises `player_id` via `player_identity_links` and excludes `"0:%"` synthetics from player metrics while retaining their events in team aggregates (D-110/D-124). Phase 2. |
| **D-132** | Methodology is versioned: S19 sets the mechanism and the immutable per-row stamp; the actual v1 numbers are deferred to a dedicated methodology session. |
| **D-133** | Build order: Season Resolver → team form snapshots → methodology → opportunities → Best Picks → (Phase 2) player form; side quests (BL/BK/BG/coaches) sequenced to the slice that first needs them (§7). |
| **D-134** | **KPIs are data, not columns.** Metric *values* are stored in the long-format **form base** (D-128), fronted by a **metric registry** carrying each KPI's NULL policy (D-129) and coverage-awareness (D-130). Adding a KPI = one registry row (+ a pure function only if new math); no migration, and it works at every user N immediately. We store per-match values, **never** per-window aggregates or user thresholds. Optional derived index-only projection for the hottest fixed-window numbers only if measured perf requires it. |
| **D-135** | **Freshness is tiered, not one nightly batch.** *Frozen tier* (past-date form) computed once, never recomputed barring a corrected past result. *Hot tier* (upcoming window + its opportunities) refreshed **event-driven / intraday**, per data category independently (odds-trigger ≠ stats-trigger, §4.3), with a nightly full sweep as safety net. Ingestion-sync cadence is a distinct, adjacent lever (REQUIREMENTS §6.6). |
| **D-136** | **Performance model:** live reads are a **cached, index-only, bounded (~≤40-row) scan** — index on `(team_id, metric_key, split, match_date DESC)`, season/league partitioning + BRIN on date, Redis/Upstash cache invalidated by hot-tier events, optional fast-lane projections, heavy backtests async via Dramatiq. Speed comes from bounded work + indexes + cache, not column count. |

## 10. Open questions raised this session

| ID | Question | Proposed default |
|---|---|---|
| **Q-NEW-BP** | As-of-date granularity for snapshots. | Snapshot per fixture-kickoff-date + a rolling "today"; confirm at S20 top. |
| **Q-NEW-BQ** | Split-season (Greek) form-window scope — do Championship-round matches share a window with Regular-Season? | Same continuous chronological window, group recorded for future weighting; confirm at S20 top (sporting-logic call). |

---

*End of COMPUTED_LAYER_DESIGN.md (Session 19, proposed). No live tables touched; no code produced. Next: Season Resolver implementation (S20), starting from Q-NEW-BP/BQ.*
