# COMPUTED_LAYER_DESIGN.md — v2

> **Version 2 (Session 20).** v1 (Session 19, commit `521a291`) established the layer's purpose, the Season Resolver, point-in-time correctness, tiered freshness, and the build order. **v2 makes it buildable.** It was triggered by eight screenshots of the ScoutEngine v2.7 prototype, checked against `CURATED_SCHEMA_REFERENCE.md` and `REQUIREMENTS.md` — the check found enough structural gaps that revising before building is far cheaper than retrofitting after.
>
> **What changed from v1:** the storage model (§3 — base measures vs derived metrics, the central idea), the grain model (§4 — entities beyond teams), the Season Resolver contract (§5 — season mode), two artifacts v1 never named (§8 — point-in-time standings, league completion), and a concrete performance and incremental-compute design (§7).
>
> **Superseded:** D-128 and D-134 are revised by D-137/D-138 — the direction (KPIs are data, not columns; no pre-baked windows) is unchanged and reaffirmed; the *storage shape* that delivers it is better.
>
> **Status:** proposed. Decisions D-137 → D-148 become final when logged into `PROJECT_STATUS.md` §7 at session close.

---

## 1. What this layer is for

**In one sentence:** the Computed layer turns clean curated data into the pre-chewed answers the product sells, so a user's filter is an indexed *lookup and a tiny arithmetic step* rather than a live scan of history.

### 1.1 The user concept it serves

> A user builds filters — some describing the **home** team, some describing the **away** team (player-prop filters come later) — and gets back the **upcoming fixtures** whose teams match those conditions, ranked by how well they match.

Each filter asks: *"did this team have [metric] [≥/≤] [value] in [≥/≤] [pct]% of its last [N | this season] [all/home/away] matches?"* A fixture scores by how many filters pass; the user sets a minimum score (REQUIREMENTS §4.1; prototype §5).

| The user wants… | …served by |
|---|---|
| filters on **home** *and* **away** teams | per-team form base (§3), combined into a fixture score by the Filter Engine |
| **recent form**, window *they* choose (last 7? 15? this season?) | query-time windowing over an ordered base (§3.4) + Season Resolver season mode (§5.3) |
| **future events** that match | the **hot tier** (§6) — the upcoming window, fresh intraday |
| **new KPI ideas later**, cheaply | the **metric registry** (§3.2) — one config row, zero backfill |
| answers that feel **instant** | §7 — bounded reads, covering indexes, hot-window cache |
| **player props**, later | Phase 2 player grain (§4) |

### 1.2 Non-negotiables

- **Never the source of truth.** Fully regenerable from Curated; losing it costs compute time, not data.
- **Never written by the `web` service.** Only the job-worker writes here — a user request cannot corrupt analytical data.
- **Never leaks the future into the past.** §5. The single most important rule in the layer.

---

## 2. The workload, measured

Design decisions should follow the actual shape of the work, so:

| Quantity | Value | Source |
|---|---|---|
| Historical fixtures (prototype scale) | ~175,000 | v2.7 doc |
| Fixtures currently ingested (3 leagues) | 996 | EPL 380 + Greece 236 + Brazil 380 |
| Upcoming fixtures live at any moment | ~614 | prototype header |
| **Share of data that is "live"** | **~0.35%** | 614 / 175,223 |
| Base-measure rows implied at full scale | ~350,000 (2 per fixture) | §3.1 |
| Filter look-back ceiling | 40 matches | REQUIREMENTS §4.1 |

**Three consequences.** (1) Over 99% of the data is **immutable history** — compute once, freeze (§6). (2) The live read path touches **at most 40 rows per team**, which is why it can be fast (§7). (3) The genuinely heavy path is the **backtest** (12 months × all fixtures in scope), which is why it belongs on a background queue and why the frozen tier is what makes it survivable.

---

## 3. The storage model — base measures vs derived metrics

**This is the central idea of v2, and it came from reading the prototype's metric dropdown carefully.**

### 3.1 The observation

The catalogue advertises ~40 metrics. But look at the Goals group: *Goals Scored, Goals Conceded, Total Goals, Both Teams Scored, Clean Sheet, Won to Nil, Scored 2+, Scored 3+, Over 2.5, Over 3.5, Goalless Draw*, plus *Win / Draw / Loss*. **Thirteen metrics, two underlying numbers** — goals for and goals against. Clean Sheet is `against = 0`. Over 2.5 is `for + against > 2.5`. Win is `for > against`.

The Cards group behaves identically: yellows and reds (own and opponent) generate *Cards For, Cards Against, Cards Total, 3+/4+/5+ Cards Match, 2+ Yellows*. Corners: three metrics from two numbers.

So the catalogue is not ~40 independent things to store. It is **~15 irreducible measurements** and **~25 questions asked about them**.

### 3.2 The decision (D-137)

> **Store the irreducible base measurements. Define every derived metric as a registry entry evaluated at query time.**

- **Base measures** — what the vendor actually measured, per team per match: goals for/against, half-time goals for/against, corners for/against, yellows/reds (own and opponent), shots and shots-on-target (for/against), possession, fouls, offsides, xG, goals prevented, passes (total/accurate), GK saves. A bounded, slow-changing set that mirrors `curated.match_statistics` + `curated.fixtures`.
- **Derived metrics** — registry rows carrying a name, a category, and an expression over base measures (`clean_sheet := goals_against = 0`). **No storage at all.**

**Why this is the right cut.** The two groups have completely different change profiles. Base measures change when *the vendor changes what it sends* — rare, and genuinely new data either way. Derived metrics change when *we have a new idea* — often, and that must be free.

**What it buys — the direct answer to "can I add a KPI later without a rebuild":**

| New KPI kind | Cost |
|---|---|
| A question over measures we already store (e.g. *won by 3+*, *over 1.5 corners*, *won to nil away*) | **One registry row. Zero DDL, zero backfill.** Works instantly across all history. |
| Needs a measurement we never stored | One nullable column + a backfill from `raw.api_responses` (0 API cost). Unavoidable in *any* design — it is new data. |

### 3.3 Base measures are stored **wide**, one row per (entity, fixture) (D-138)

v1 proposed a long/tall table — one row per `(team, match, metric)`. Now that the open-ended part lives in the registry, long format for the *base* is strictly worse:

| | Long (one row per measure) | **Wide (one row per team-match)** |
|---|---|---|
| Rows at full scale | ~5.2M | **~350k** |
| A 4-filter evaluation | 4 index scans, 40 rows each | **1 index scan, 40 rows, reused by all 4** |
| Adding a derived KPI | registry row | **registry row** (identical) |
| Adding a base measure | insert rows + backfill | `ALTER TABLE ADD COLUMN` (instant in PG) + backfill |
| FK integrity | same | same |

The extensibility promise is **preserved intact** — it now lives in the registry, which is where it belongs — while reads get ~15× cheaper. This is the correction v1's framing invited by conflating "measurements" (bounded) with "KPIs" (open-ended).

**Grain: one row per (entity, fixture).** Crucially, the row carries **both perspectives** — `goals_for` *and* `goals_against`, `corners_for` *and* `corners_against`, `yellows_own` *and* `yellows_opp`. So "Goals Conceded" and "Yellow Cards Earned (opp)" need no join to the opponent's row. Two rows per fixture, one per team.

**Home/away is a stored property, not a stored dimension.** The row records `is_home`; the user's Overall/Home/Away context is a `WHERE` clause. v1 implied three stored copies — this is one.

**Context columns** travel on the row because filters and future methodology need them: `match_date`, `is_home`, `opponent_team_id`, `league_season_id`, `group_label` (split seasons, D-100), `competition`, and the **opponent-quality tag as of that date** (§8.1).

*Exact column names are confirmed against `information_schema` / `CURATED_SCHEMA_REFERENCE.md` at implementation — never hand-typed from this document (standing rule).*

### 3.4 Windows are **never** pre-baked (reaffirmed from v1, D-128)

The user controls the window (`last N`, 1–40, **or** `season`), the threshold, and the percentage. The combinatorics — ~40 metrics × 3 contexts × 41 window options × arbitrary threshold × arbitrary percentage — are thousands of possible answers per team, composed across multiple filters. **No table can hold those answers.**

So: **as-of-date is a query predicate** (`match_date < :as_of`), not a stored key; and the final *"≥ threshold in ≥ pct% of last N"* test is computed live over a bounded row set. This is not a compromise — it is both the only structure that honours user-tunable windows *and* the faster one (§7).

**It also enables shapes a pre-baked table structurally cannot serve:** *Unbeaten Streak* and *Winning Streak* are run-lengths over an ordered sequence. You can compute a streak from ordered per-match rows; you cannot recover one from a stored "last-10 average."

---

## 4. Entity grains — teams now, others later, without a migration (D-139)

Teams are not the only thing that accumulates form. The prototype also profiles **referees** (1,352 of them, with CARDS/G, %O2.5, PENS/G, HOME%, a strictness tier); **coaches** are a known entity case (D-112); **venues** are plausible.

**Decision: parallel per-grain tables sharing one column contract and one compute engine** — not a single polymorphic table.

- **Shared contract.** Every form base has the same shape: `entity_id`, `fixture_id`, `match_date`, context columns, base measures. A new grain is a migration from the template + a worker from the template + registry rows — roughly half a session, not a redesign.
- **Why not polymorphic (`entity_type` + `entity_id`)?** It would cost **foreign-key integrity**, which this project has treated as load-bearing (RESTRICT FKs, zero-orphan verification every session since S7). It would also mix a ~350k-row team table with a ~1k-row referee table under one index.
- **The registry carries `grain`**, so each metric declares which entity it belongs to.

**MVP builds the team grain only.** Player form is Phase 2 (REQUIREMENTS §6.3). Referee is **post-MVP** (§10). The point of deciding now is that the team table gets shaped as *an instance of a pattern* rather than as a one-off — which is precisely the difference between "add referees later" costing half a session versus a migration.

---

## 5. Point-in-time correctness and the Season Resolver

### 5.1 The rule

> **Every form number is computed *as of* a date and may only see completed fixtures strictly *before* that date.**

When we say "scored in 70% of its last 10," that window is defined relative to a date. For an upcoming match it's today; for a **backtest** of a match played last October it must be the 10 matches before *that* date. Include anything later and the backtest becomes silently, wildly profitable — because it is betting with knowledge of results that hadn't happened. That is **look-ahead bias**, and for a product whose entire proposition is trustworthy research, it is fatal.

### 5.2 The Resolver (D-127, carried from v1)

One **stateless, pure** component answers one question, and every consumer calls it — filter engine, backtest, form-base build, opportunities engine. Sharing the implementation is what makes filter and backtest agree *by construction* rather than by discipline.

### 5.3 The v2 contract — season mode added (D-140)

v1's signature returned "completed fixtures strictly before the as-of-date, in tier-scope, most-recent-first," and treated *last N* as the first N. The screenshots surfaced a second mode we had not designed:

`REQUIREMENTS.md` §4.1 defines `sample` as **`int (1–40)` or `"season"`** — the prototype's **Season** checkbox — and explicitly ties it to **Q-NEW-G**, the very question the Resolver exists to answer. So the contract becomes:

```
resolve(entity_id, as_of_date, scope) -> ordered fixture list
    scope = { tier_scope, competition_scope, window_mode }
    window_mode = LAST_N            → first N of the ordered list
                | CURRENT_SEASON    → bounded to the entity's season as of as_of_date
```

**"Current season" must be derived, never taken from the vendor.** S17 proved the vendor's `is_current` flag reports Brazil's current season as 2026 while the complete 2025 season sits in our database (D-045/D-122). Trusting the flag would silently return an empty or wrong window. Derive it from fixture dates within the league-season instead.

**Two open questions gate the build (decide at the top of S21):**

- **Q-NEW-BP — as-of-date granularity.** *Proposed:* the resolver is a pure function evaluated at query time, so the only *materialised* as-of-dates are those the hot-window projection caches (§7.4) — kickoff dates of upcoming fixtures, plus "today." History needs no materialised snapshots at all. This is a simpler answer than v1 implied and falls out of §3.4.
- **Q-NEW-BQ — split-season scope.** For the Greek Super League (Regular Season → Championship / Relegation groups, D-100), does a Championship-round match share a form window with the team's Regular-Season matches? *Proposed:* **yes — one continuous chronological window**, with `group_label` stored so a future methodology can weight or split them. **This is a sporting-judgement call, not a technical one — confirm explicitly.** It also determines what `CURRENT_SEASON` means for half our launch market.

---

## 6. Freshness and incremental computation

### 6.1 Tiered freshness (D-135, carried; sharpened by §2)

With ~0.35% of fixtures live at any moment, tiering is not an optimisation, it is the obvious shape:

| Tier | What | Cadence | Why |
|---|---|---|---|
| **Frozen** | Form rows for past fixtures | Computed **once**; recomputed only if a past result is corrected | History is immutable — 99.65% of the data |
| **Hot** | The upcoming window + its opportunities + the cached projections | **Event-driven, intraday** + nightly full sweep as safety net | The only slice users query live and the only one whose inputs still move |

### 6.2 Per-category triggers — different clocks, correctly (D-135)

There is no single "sync." Each data category has its own cadence (REQUIREMENTS §6.6): match stats within ~1 h of a fixture ending, lineups every 3–4 h on match days, odds daily plus intraday, standings daily, fixtures nightly plus intraday. The hot tier **subscribes to each independently**:

| Event | Recompute |
|---|---|
| Match stats land for a completed fixture | That fixture's 2 form rows; invalidate both teams' cached windows; refresh standings snapshot + league completion |
| Odds move | Opportunities for the affected fixtures **only** — no form work at all |
| New upcoming fixtures appear | Warm their teams' hot-window projections |

Different frequencies for odds versus fixtures versus stats fall out **naturally** as independent triggers rather than being bolted onto one monolithic job.

### 6.3 Incremental technique (D-141)

- **Watermarks.** Each (league_season, artifact) carries a high-water mark — the last fixture/timestamp processed. A run processes only what's past it. Restartable by construction.
- **Affected-set propagation.** A landed result affects a known, small set: the two form rows, the two teams' cached windows, that league-season's standings snapshot and completion. Never a global recompute.
- **Idempotent upsert on the natural key** — `(entity_id, fixture_id)`. A crashed run resumes without duplication; a re-run overwrites cleanly. This is the transaction-per-unit discipline that carried the ingestion workers through three mid-run interruptions in S17.
- **Full rebuild always available** as an on-demand job (regenerability, §1.2). Incremental and full must produce identical results — and that equality is itself a cross-check (§11).

---

## 7. Performance — how "ultra-fast" is actually achieved (D-142)

Speed comes from **bounded work, covering indexes, and caching** — not from column count, and not from pre-computing answers.

**1. The work is bounded and constant.** A filter evaluation reads **at most 40 rows** for one team, regardless of whether we hold 1,000 fixtures or 10 million. Small N is the whole game.

**2. One read serves every filter.** Because base measures are wide (§3.3), a 4-filter strategy fetches the team's last-N rows **once** and evaluates all four in a single pass over them, in memory. Long format would have cost four separate scans.

**3. Covering index → index-only scans.** `(entity_id, is_home, match_date DESC)` with the base measures carried via `INCLUDE`, so the hot query is answered from the index without touching the table heap.

**4. Partition + prune.** Partition the form base by season (and/or league_season); add BRIN on `match_date` for near-free range pruning on the large historical partitions.

**5. The hot-window projection (the biggest single win).** For teams with upcoming fixtures, materialise the **last 40 rows** as a single compact record (ordered arrays per measure) in Postgres and/or Redis/Upstash. Evaluating *"≥2 in ≥60% of last 10"* then becomes: **one key read, slice the first 10, count.** No scan, no join — a single round trip plus in-memory arithmetic. Invalidated by the §6.2 events. This is the mature version of the prototype's in-process LRU cache, moved out of process so every server instance shares it.

**6. Batch, never N+1.** A filter run over 614 upcoming fixtures fetches all involved teams' windows in **one** batched query, not 1,228 round trips.

**7. Heavy work is asynchronous.** Backtests scan long histories (targets <10 s typical, <60 s heavy — REQUIREMENTS §8.1) and run as Dramatiq background jobs, never blocking a request. They read the **frozen** tier, which is precisely why freezing history matters.

**8. Measure before adding more.** Targets are <3 s typical filter, <500 ms general endpoint (§8.1). Further materialisation is added **only** where measurement shows a miss. Don't pre-optimise.

---

## 8. Supporting computed artifacts (both missing from v1)

### 8.1 Point-in-time standings (D-143)

**The gap.** Opponent-Quality metrics — *win/scored/BTTS vs top-half or bottom-half* (REQUIREMENTS §4.1) — need to know whether an opponent was top-half **at the time of that match**. `curated.standings` holds a *current/final* table, not a time series, so this is not answerable from Curated. The prototype used final standings as a proxy and shipped a warning: ~90% accurate mid-season, degrading badly early (v2.7 §5.2).

**The decision.** Compute `computed.standings_snapshot` — the league table **as of a date**, derived from completed fixtures before that date. We hold every fixture and every score, so this is exactly computable. It is another frozen-tier artifact (compute once per league-season per matchday, never changes).

**Why it's worth it.** It removes a known-inaccurate proxy from a *research* product, and it's the same "compute once, freeze" pattern we already need. Each form row then stores its opponent-quality tag **as of that date** (§3.3), so the filter never recomputes it.

*Fallback, if measurement shows this is too expensive: keep the final-standings proxy with the visible warning (prototype behaviour). Decide on evidence, not assumption.*

### 8.2 League completion % (D-144)

The scope filter takes **MIN and MAX completion %** (D-011). That is a computed per-league-season value as of a date — completed fixtures ÷ scheduled fixtures — and it sits on essentially every query. Small, but it must exist and be indexed; v1 never named it.

---

## 9. The metric registry (D-145)

The registry is the config table that makes KPIs data. Attributes, several of which came directly from reading the prototype dropdown:

| Attribute | Purpose |
|---|---|
| `metric_key`, `display_name`, `category` | identity + UI grouping (Goals / Results / Form / Half Time / Corners / Cards / Shots / Possession / Opponent Quality) |
| `grain` | which entity (§4) — team / player / referee / … |
| **`value_source`** | **own row / opponent row / match aggregate** — from the dropdown: *Goals Scored* (own), *Yellow Cards Earned (opp)* (opponent), *Cards Total (match)* (aggregate) |
| **`value_type`** | **count / boolean / percentage / rating / categorical** — many metrics are per-match booleans (*Clean Sheet*, *Won to Nil*, *BTTS*, *Goalless Draw*, *Winning at HT*, *3+ Cards Match*), not continuous values; this changes how a threshold and a NULL are interpreted |
| `expression` | the derivation over base measures (§3.2) |
| `null_policy` | `zero` \| `unknown` (D-129, §10.1) |
| `coverage_aware` | whether the metric must report coverage (D-130, §10.2) |
| `methodology_version` | for metrics with tunable numbers (§9.1) |
| `proxy_warning` | surfaces the Opponent-Quality caveat in the UI (REQUIREMENTS §4.1) |

**Categorical outputs are first-class.** The prototype's referee **strictness tier** (Lenient→Very Strict), its **sample-size band** (HIGH / MEDIUM), and the player card's **verdict** (STRONG PLAY / MARGINAL / AVOID) are metrics whose output is a *category* produced by thresholds. They are pure methodology (§9.1) and must be versioned; v1's registry assumed numbers only.

**Expression mechanism — open (Q-NEW-BS).** A declarative expression covers the simple predicates (`goals_against = 0`); genuinely complex metrics (*Weighted Form*'s recency weighting, streak run-lengths) want a registered pure function keyed by `metric_key`. *Proposed:* support both, with declarative as the default and functions as the escape hatch; decide the exact mechanism at the registry slice.

### 9.1 Methodology versioning (D-132, carried)

Every computed row and every threshold-driven classification carries the **methodology version** that produced it. The mechanism is decided here; **the v1 numbers are not.** Choosing recency weights, edge thresholds, strictness cut-offs, and verdict boundaries is a modelling exercise that gets **its own session** before the opportunities slice. Stamping is what keeps "did this strategy work last season?" answerable across methodology changes.

---

## 10. Curated-data landmines every KPI must respect

### 10.1 Per-measure NULL policy (D-129)

`NULL` does not mean one thing. Proven in S15 across 1,232 team-rows with zero counterexamples: `red_cards IS NULL` ≡ **zero** (fold in as 0), while `expected_goals IS NULL` ≡ **genuinely unknown** (exclude from numerator *and* denominator; report the sample size actually used). Carried as `null_policy` on each registry entry — never a blanket per-table rule.

> **Docs-reconciliation flag (carried from v1, still open):** `REQUIREMENTS.md` §6.7 and `CURATED_SCHEMA_REFERENCE.md` §6.7 both still state the old blanket rule — *"a filter that hits NULL treats it as insufficient sample and auto-fails."* D-108 overturned that. Both should be updated in a later docs pass.

### 10.2 Coverage-aware measures (D-130)

xG coverage is **date-windowed** — 100% null before Feb 2026 for Greece, partial in Feb, full after (D-109) — and the `cov_*` booleans structurally cannot express a date window. So xG-family metrics report the fraction of their sample that actually carried the measure, and below a threshold emit **"insufficient coverage"** rather than a confident-looking number built on two data points. The prototype's HIGH / MEDIUM sample band is the same idea, already validated in the UI.

### 10.3 Player identity (D-131, Phase 2)

Player-grain aggregation must **canonicalise `player_id` through `curated.player_identity_links` first** (D-110) — otherwise one player's stats split across two vendor ids and every per-player rate is wrong. And `source_ref LIKE '0:%'` synthetics ("Unidentified player", D-124) are **excluded from player-identity metrics** but **retained in team aggregates** — their shots and cards really happened for the team; only the identity is absent.

### 10.4 Explicitly out of scope

`height`/`weight` heterogeneity (D-111 / Q-NEW-BD) is a player-bio *display* concern. The Computed layer does not consume it.

---

## 11. Cross-check discipline

Our standing lesson, held four straight sessions: **design the cross-check, don't trust the model.** Each artifact ships with its verification:

| Artifact | Check |
|---|---|
| **Season Resolver** | **Look-ahead guard** — assert no returned fixture has `match_date >= as_of_date`. This is *the* check that catches future-leakage. Plus: known-season equality against a hand-derived list (EPL 38-round, Greek split-season, Brazil calendar-year); tier-scope containment; `CURRENT_SEASON` correct where the vendor's `is_current` is wrong (Brazil). |
| **Form base** | Hand-compute one team's last-5 **and** last-13 hit rate from Curated as of a known date; assert equality against the live query (proves user-tunable N). Assert idempotency (re-run → identical rows, `created_at` preserved). Assert **incremental == full rebuild** on a sample league-season. |
| **Derived metrics** | For each registry entry, assert the derived value equals an independent hand-computation from Curated on a sample of fixtures — the raw-vs-curated shape that caught S18's five silently-dropped players. |
| **NULL policy** | Assert an `unknown`-policy measure never contributes a 0 to an average — compare the computed denominator against a hand-filtered "rows where present" count. |
| **Coverage** | On a Greek team straddling the Feb-2026 xG boundary, assert the reported coverage fraction is right and the metric flips to "insufficient" below threshold. |
| **Standings snapshot** | Reconstruct a known matchday's table and compare against the real published table. |
| **Hot projection** | Assert the cached window and a direct query return identical results, and that the documented events invalidate it. |

---

## 12. Roadmap

No time pressure has been stated, so the sequence favours correctness over compression. Sessions are indicative, not promises.

**Main line**

1. **S21 — Season Resolver.** The shared primitive (§5). Opens by settling Q-NEW-BP and Q-NEW-BQ. Pure, standalone, testable against three known league shapes.
2. **S22 — base-measure schema + the team form-base worker.** The wide table (§3.3), built as an instance of the grain template (§4). Backfill the 996 fixtures we hold.
3. **S23 — the metric registry + derived-metric evaluation.** Seed the full catalogue from REQUIREMENTS §4.1. Settle Q-NEW-BS.
4. **S24 — supporting artifacts:** point-in-time standings (§8.1) + league completion (§8.2).
5. **S25 — the query path + hot-window projection + caching** (§7), measured against the §8.1 targets.
6. **Methodology session** — lock the v1 numbers (§9.1). Prerequisite for opportunities.
7. **Opportunities engine** (D-030), then **Best Picks** (D-034).
8. **Phase 2 — player grain**, where D-131 becomes critical.

**Sequenced side quests (not dropped — each has a *when*)**

| Item | When |
|---|---|
| **Q-NEW-BL** — workers exit 0 on failure | Immediately before the first unattended/scheduled run — i.e. the session that wires the §6.2 triggers |
| **Q-NEW-BK** — Brazil venue aliases | When a venue-based KPI or display first needs it |
| **Q-NEW-BG** — lineup mis-slot detector | Alongside any lineup-consuming feature |
| **`curated.coaches`** (D-112) | Coach grain, when a coach feature appears |
| **Referees** (§13) | **Post-MVP** — Alex's call |
| REQUIREMENTS §6.7 / schema §6.7 null-rule correction | Next docs pass |

---

## 13. Referees — logged, not built (D-146)

The prototype ships a full referee module: 1,352 referees with CARDS/G, %O2.5 / %O3.5 / %O4.5, PENS/G, GOALS/G, %BTTS, HOME%, a derived strictness tier and sample band, plus a detail view promising card timing, home/away bias and per-league splits.

**Status: nice-to-have, post-MVP.** Recorded so it is visibly *deferred* rather than accidentally lost. What we know:

- **`REQUIREMENTS.md` does not mention referees at all** — the module never entered the rebuild requirements. This design doc is now the record that it exists and was consciously deferred.
- **The data is already paid for.** `curated.fixtures.referee` is a text column landed on every fixture we hold. **Coverage is unverified** — a read-only check (non-null count, distinct names, split by league; zero API cost) should run before any estimate is trusted.
- **Most KPIs are derivable today** from fixtures + `match_statistics` + the five penalty counters in `player_match_stats`.
- **Card timing is not.** It needs minute-level events (`/fixtures/events`), which we do not ingest and which is not in `SYNC_INGESTION_DESIGN.md`. That is an **ingestion** dependency, deferred indefinitely.
- **Identity is name-only** — no vendor referee id confirmed. That is the D-118/D-120 trap (names are the weakest evidence), mitigated by referee names varying far less than player names. Check for a vendor id before building on names.
- **Cost when it happens:** ~1 session for the entity + worker + KPIs (the grain template of §4 is what keeps it cheap); card timing is a separate 1–2 sessions plus a backfill.

---

## 14. Decisions proposed (draft — finalise at close)

| ID | Decision |
|---|---|
| **D-137** | **Base measures vs derived metrics.** Store the ~15 irreducible measurements; define every derived metric (~25 of the ~40 catalogue) as a **registry entry evaluated at query time**. A new KPI over existing measures = one registry row, zero DDL, zero backfill, instantly valid across all history. |
| **D-138** | **Base measures are stored wide: one row per `(entity, fixture)`**, carrying both perspectives (for/against) so opponent-derived metrics need no join, with `is_home` as a stored property rather than three stored splits. **Supersedes the long-format element of D-134**; the "KPIs are data, not columns" principle is preserved and now lives in the registry. ~15× fewer rows and one read serving all filters. |
| **D-139** | **Entity grains are parallel per-grain tables sharing one column contract and one compute engine** — not a polymorphic table. Preserves FK integrity (load-bearing since S7) and per-grain indexing; a new grain costs a template migration + template worker + registry rows. MVP = team grain only. |
| **D-140** | **Season Resolver v2 adds `CURRENT_SEASON` window mode** (REQUIREMENTS §4.1 `sample = "season"`, Q-NEW-G). **"Current season" is derived from fixture dates, never from the vendor's `is_current` flag** (D-045/D-122 — the flag reports Brazil's current season as 2026 while the complete 2025 season is in our DB). |
| **D-141** | **Incremental computation via watermarks + affected-set propagation**, idempotent upsert on `(entity_id, fixture_id)`, with a full rebuild always available; incremental and full must produce identical results, and that equality is a cross-check. |
| **D-142** | **Performance model:** bounded ≤40-row reads; one read serving all filters (enabled by D-138); covering index `(entity_id, is_home, match_date DESC) INCLUDE (measures)`; season/league partitioning + BRIN on date; a **hot-window projection** (last-40 as ordered arrays in Postgres/Redis) reducing a filter to one key read + a slice; batched multi-team fetches; async backtests via Dramatiq; further materialisation only where measurement shows a miss. |
| **D-143** | **`computed.standings_snapshot` — the league table as of a date**, derived from completed fixtures, replacing the prototype's final-standings proxy for Opponent-Quality metrics. Frozen-tier artifact. Fallback to the proxy-with-warning only if measurement shows it is too expensive. |
| **D-144** | **`computed.league_completion` — completed ÷ scheduled fixtures per league-season as of a date**, backing the MIN/MAX completion scope filter (D-011). Named here because v1 omitted it. |
| **D-145** | **Metric registry attribute set**, including three that the prototype dropdown revealed: **`value_source`** (own / opponent / match aggregate), **`value_type`** (count / boolean / percentage / rating / **categorical**), and `proxy_warning`. Categorical, threshold-driven outputs (strictness tier, sample band, verdict) are first-class and methodology-versioned. |
| **D-146** | **Referees are in-scope-but-deferred (post-MVP), logged in §13** rather than left as an accidental omission from REQUIREMENTS. Data already landed; card timing needs `/fixtures/events` and is deferred indefinitely; coverage check required before any estimate. |
| **D-147** | **The Filter Engine evaluates all of a strategy's filters in a single pass over one fetched window per team** — a consequence of D-138 that must be honoured by the query layer, not re-derived per filter. |
| **D-148** | **Design-before-build is reaffirmed as the method for this layer**: v2 exists because eight prototype screenshots, checked against the schema and requirements, surfaced structural gaps (grain generality, season mode, registry attributes, two missing artifacts) that would each have been a migration if found after S21–S22. |

## 15. Open questions

| ID | Question | Proposed default |
|---|---|---|
| **Q-NEW-BP** | As-of-date granularity. | No materialised historical snapshots — the resolver is evaluated at query time; only the hot-window projection is materialised (§5.3, §7.5). Confirm at S21. |
| **Q-NEW-BQ** | Split-season (Greek) form-window scope — do Championship-round matches share a window with Regular Season? | One continuous chronological window, `group_label` stored for future weighting. **Sporting-judgement call — confirm explicitly at S21.** |
| **Q-NEW-BR** | The exact base-measure list — which columns are irreducible vs derivable. | Derive from `information_schema` against `curated.match_statistics` + `curated.fixtures` at S22; do not hand-type from this doc. |
| **Q-NEW-BS** | Derived-metric expression mechanism — declarative expression vs registered pure function. | Support both; declarative default, function escape hatch for Weighted Form / streaks. Decide at the registry slice (S23). |
| **Q-NEW-BT** | Form-base storage cost at scale (~350k rows × ~30 columns) against the 400 MiB upgrade trigger (D-084, currently 11.74%). | Measure on the 996 fixtures we hold at S22 and extrapolate before committing to partitioning strategy. |
| **Q-NEW-BU** | Referee coverage in `curated.fixtures.referee` — non-null share, distinct count, per-league split; and whether the vendor exposes a referee **id** anywhere. | Read-only check, 0 API cost. Run before any referee estimate is trusted (§13). |

---

*End of COMPUTED_LAYER_DESIGN.md v2 (Session 20, proposed). No code, no live tables touched. Next: Season Resolver implementation (S21), opening with Q-NEW-BP and Q-NEW-BQ.*
