# CROSS-LEAGUE COVERAGE REFERENCE

> **Produced:** Session 15 (2026-07-15) — the Q-NEW-AQ deliverable.
> **Scope:** English Premier League (39 / 2025) vs Greek Super League 1 (197 / 2025), both fully ingested.
> **Status:** Living document. Extend it every time a new league is ingested.

---

## 0. How to use this document

Read this **before adding league #3**, and before designing anything in the Computed layer.

Its purpose is narrow and specific: our five ingestion workers are **league-agnostic by design**, but until S15 they had only ever been *validated* against one league. This document records what changed when a second, structurally different league (a split-season competition in a smaller market) went through the same code.

The short version: **every worker ran clean on Greece. Not one line of code needed changing.** No unmapped leaves, no failures, no dedup, no clobbers. The ingestion engine is genuinely league-agnostic.

But the **data** is not uniform, and four of the differences are load-bearing. Those are Sections 2–5. Section 9 is the checklist to run against league #3.

---

## 1. What was ingested (the ground truth for both leagues)

| Table | EPL (39/2025) | Greece (197/2025) |
|---|---:|---:|
| `fixtures` | 380 | 236 |
| `match_statistics` | 760 | 472 |
| `player_match_stats` | 15,189 | 10,638 |
| `lineups` | 15,189 | 10,639 |
| `players` (league-linked) | 679 | 557 roster-enriched |

**Greek fixture composition** (reconciles exactly to 236, which is how we know the single-page response hid nothing):

| Round block | Teams | Rounds | Matches |
|---|---:|---:|---:|
| Regular Season 1–26 | 14 | 26 | 182 |
| Championship Group 1–6 | 4 | 6 | 12 |
| Relegation Group 1–10 | 6 | 10 | 30 |
| Conference League Group 1–6 | 4 | 6 | 12 |
| **Total** | | **48 distinct rounds** | **236** |

The three playoff groups partition the 14 teams exactly once (4 + 6 + 4 = 14).

**Session cost:** ≈750 API calls (from `calls_made`, the honest counter — see §8.4), 8.20 MiB of storage.

---

## 2. FINDING: Coverage is date-windowed, not league-scoped

**This is the most structurally important finding in the document.**

`expected_goals` and `goals_prevented` are **100% present on EPL** and **56.4% absent on Greece** (206 non-null / 266 null across 472 team-rows). But the absence is not random and not league-wide:

| Kickoff month | xG null rate |
|---|---:|
| Aug 2025 – Jan 2026 | **100% null** |
| Feb 2026 | 24.1% null (44 set / 14 null) |
| Mar – May 2026 | **0% null** |

**The vendor began supplying xG for the Greek Super League in early February 2026.** The trigger is the fixture's **kickoff date**, not its round.

### Why we know it's the calendar and not the round

A round-number cut *looks* plausible (rounds 1–19 ≈ 100% null, rounds 21–26 = 0%) — but **round 1 and round 18 each have 2 rows with xG** inside otherwise-100%-null rounds. Those are **postponed fixtures played after the February cutoff**. The anomaly that breaks the round theory is the same fact that confirms the calendar theory. The calendar cut is monotonic; the round cut is not.

Corroborating: xG is never split within a fixture (0 fixtures have exactly one team-row with xG, in either league). `expected_goals` and `goals_prevented` move together identically — one coverage signal, not two.

### The consequence: our coverage flags cannot express this

`curated.league_seasons.cov_*` are **booleans per league-season**. For Greece, `cov_fixture_statistics = TRUE` is *true* and *useless* for xG — it cannot say "from 2026-02". 

**Any future question of the form "does this league support xG filters?" cannot be answered from the coverage flags as currently designed.** This is a schema-design gap, discovered by data. It is not a bug in the ingest; it is a limit of the model. Whoever designs coverage-gating in the Computed or Configuration layer must know this before they trust `cov_*`.

**Correct way to state coverage for xG: date-based, never round-based, never a league-level boolean.**

---

## 3. FINDING: NULL semantics are per-measure, not per-table

`CURATED_SCHEMA_REFERENCE.md` §1.4 says a filter hitting NULL treats it as "insufficient sample" and auto-fails. **That rule is correct for xG and wrong for red cards.** Both are NULL. They do not mean the same thing.

### The vendor is internally inconsistent — proven from the landed raw payload

From `raw.api_responses` id=1208 (Olympiakos, fixture 1400742), verbatim, **in the same statistics array**:

```json
{ "type": "Yellow Cards", "value": 0 }
{ "type": "Red Cards",    "value": null }
```

Both mean "no cards of that colour occurred." The vendor sends an explicit `0` for one and an explicit `null` for the other. **Neither key is absent** — which is also why every worker logged zero unmapped leaves: the type is always in the array, only the value differs.

Our storage is faithful and correct (D-051): we record what arrived and invent nothing.

### Red cards ≡ zero — proven, not inferred

Cross-checked `match_statistics.red_cards` against the **independent player-level sum** from `player_match_stats.cards_red`, across **all 1,232 team-rows in both leagues**:

| League | NULL & player_sum = 0 | **NULL & player_sum > 0** | set & equal | set & unequal | Total |
|---|---:|---:|---:|---:|---:|
| EPL | 680 | **0** | 80 | 0 | 760 |
| Greece | 358 | **0** | 114 | 0 | 472 |

**Zero counterexamples.** Every NULL corresponds to a player-level sum of exactly 0; every populated value equals the player sum exactly.

### The resulting rule

| Measure | `NULL` means | Evidence |
|---|---|---|
| `red_cards` | **zero** | 1,232 team-rows, 0 counterexamples, both leagues |
| `expected_goals` / `goals_prevented` | **genuinely unknown** | calendar-gated; absent before ~Feb 2026 |

A filter for *"team had ≤ 0 red cards in ≥ 80% of last 10"* under a blanket NULL→auto-fail rule **fails on exactly the matches that should pass**. This is a latent correctness bug in any Computed-layer design that treats NULL uniformly.

**The method generalises:** where an independent player-level corroboration exists, cross-check the measure against it. Where it doesn't (xG), find the structural boundary instead. Do not infer NULL semantics from null-rates alone — `red_cards` and `yellow_cards` have wildly different null-rates for reasons that have nothing to do with coverage (see §7).

---

## 4. FINDING: Vendor dual identity — `/fixtures/lineups` uses a separate player id space

> ### ⚠️ UPDATED BY SESSION 16 — READ THIS BEFORE THE REST OF §4
>
> **The finding is confirmed and now RESOLVED** (D-114): `curated.player_identity_links`
> holds 56 live alias→canonical links, and `identity_links.py` reconciles any league at
> 0 API cost. **But four claims below were corrected in S16. They are struck through in
> place; the surrounding prose is otherwise as written in S15.**
>
> 1. **"`/players` emits ONLY the canonical id … the canonical side is unambiguous"** —
>    the *fact* is right (1 of 48 refs on the roster), the *inference* is wrong.
>    **Roster presence does not imply canonicity:** Tzovaras is on the roster under
>    **both** ids (`2386` page 1, `353061` page 13). **Canonical is defined
>    operationally: the id carrying the `player_match_stats` rows.**
> 2. **"`birth_date` + name works as a fixture-independent key"** — **DEAD** (D-118).
>    The vendor sends `{"date": null}` for the canonical twins; **0 of 817 matched pairs
>    carry a birth date on both sides.** It could not have matched one.
> 3. **The impact figures (381 / 898 / 65) DO NOT REPRODUCE** — S16 gets 257 / 784 / 2.
>    **Treat every count in §4 as unverified** (Q-NEW-BF). The *population* (56 = 48+8)
>    and the *matcher's behaviour* both reproduce exactly; only the magnitudes differ.
> 4. **A raw jersey join is NOT a function.** It needs per-alias **majority vote**,
>    because the vendor **mis-slots substitutes into the opponent's team block**
>    (Q-NEW-BG) — 11 Greek aliases, one dissenting row each.
>
> **Also new:** the vendor supplies a different **name** as well as a different id
> (`M. Flores` ↔ `Wellity Lucky Omoruyi` — same human, Liverpool #92). **Names are the
> weakest evidence here; recurrence is the strongest** (D-120).

**The vendor issues two different `player.id`s for the same human**, depending on the endpoint.

| Endpoint | id space |
|---|---|
| `/players` (roster) | **canonical** |
| `/fixtures/players` | canonical |
| `/fixtures/statistics` | canonical |
| **`/fixtures/lineups`** | **divergent** — mostly freshly-minted `56xxxx` ids |

Three endpoints agree. `/fixtures/lineups` alone diverges.

### Proof: the jersey test

Jersey numbers are unique per team per match. A jersey match within the same fixture is identity, not coincidence.

| League | jersey-matched (lineups-only, pms-only) pairs |
|---|---:|
| EPL | 33 |
| Greece | 898 |

Sample matched pairs (Greek):

| Fixture | Team | Jersey | lineups ref / name | pms ref / name | Min |
|---|---|---:|---|---|---:|
| 1141 | 47 | 19 | `561126` P. Castano *(starter)* | `1686` Pepe Castaño | 86 |
| 1143 | 45 | 28 | `540063` L. Kojic *(starter)* | `45968` Lazar Kojić | 90 |
| 1143 | 45 | 22 | `561127` Esteban Diego *(starter)* | `181198` Diego Esteban | 72 |
| 1143 | 45 | 9 | `561130` J. Aguirre *(starter)* | `200994` Jorge Aguirre | 61 |
| 1141 | 47 | 40 | `553932` K. Ketu *(sub)* | `124081` Kalvin Ketu | 22 |

Abbreviated vs full names, identical jerseys, same match. Note `Esteban Diego` ↔ `Diego Esteban` — even name order flips.

### Scale, both leagues

| | EPL | Greece |
|---|---:|---:|
| Players seeded by `lineups` | 8 | 48 |
| …that are **duplicates** | **8 (100%)** | **48 (100%)** |
| …genuinely new unused subs | **0** | **0** |
| Affected appearances | 33 | ~1,045 |
| Duplicate starters | **0** (all bench) | **381** |

**EPL is not clean — it is smaller.** The same phenomenon, at 1/6 scale, entirely on the bench, which is why it never visibly corrupted anything. **Greece did not introduce this bug; Greece made a pre-existing vendor bug visible by scaling it 6× and putting it on starters.** This is exactly what cross-league validation exists to do.

### Greek lineups-only starters — three numbers, three criteria

State all three or none; any one alone misleads:

| Criterion | Count |
|---|---:|
| lineups-only rows with `is_starting = TRUE` | **381** |
| …jersey-matched to a specific pms-only counterpart in the same fixture+team | **316** |
| …no jersey match | **65** |

381 = 316 + 65. The 65 are **not new humans** — they are among the known 48 duplicates; the same-match linkage fails (different jersey that match, or no pms row that specific fixture). A residual to understand, not a new population.

> **S16 correction (Q-NEW-BF): these three numbers do not reproduce.** S16 gets **257 / 255 / 2** (row-level) or **253 / 246 / 7** (player-level). `lineups` and `player_match_stats` are byte-identical to the S15 close and are the only inputs, so one of the two queries is wrong; S15's scratchpad SQL is gone, so it cannot be adjudicated. **EPL reconciles perfectly** (28→33 = S15's 33), so the definitional shift explains EPL and almost none of Greece. **Under the corrected S16 definitions there are 0 unmatched aliases in either league** — the "65" was a scoping artefact, not a population. The reconciler's own output (`aliases_found` / `linked` / `with_dissent` / `needs_review`) is now the authoritative count.

### The enrichment consequence

`/players` emits **only** the canonical id. Verified against the full 28-page landed roster:

- Castaño: `561126` (lineup-side) **not in roster**; `1686` (canonical) **in roster**.
- Kojić: `540063` **not in roster**; `45968` **in roster**.
- Of the 48 Greek lineup-side refs, exactly **1** (`2386`) appears in the roster.

**Therefore 47 of 48 Greek lineup-side duplicate rows are permanently bio-less.** `player_bio` reads the roster; the roster never emits their ids; they can never enrich. Not a worker defect — a structural consequence of the vendor's id split.

> **S16 correction:** still true, and now **moot** — the 47 are *linked*, and their canonicals already carry bio. Read the bio **through the link**; do not enrich the alias. The alias's `photo_url` is NULL **by construction** (this endpoint carries no photo), so a UI reading the alias row directly still needs a null-photo fallback.

### This retroactively solves the EPL "8 bench-only" residual (Q-NEW-AT)

Q-NEW-AT characterised EPL's 39-row bio residual as *29 transferred-out + 2 stats-only + **8 bench-only***. The jersey test finds **exactly 8 EPL dual-identity players, all bench**. Those 8 were never "registered but never played" — the note in `player_bio.py` recorded an **assumption as a fact**. They are lineup-side duplicate ids that `/players` structurally never emits, which is precisely *why* they never enriched. A sub-population unexplained since S12 is now closed.

### What is and isn't damaged

- ✅ **Nothing is corrupted.** Both workers landed exactly what the vendor sent. Raw-first means every payload is re-derivable at zero cost.
- ✅ **`player_bio` cannot merge or clobber them** — it upserts on `(sport, source, source_ref)`, so duplicate rows are inert.
- ⚠️ **`curated.players` holds 56 duplicate person rows** (48 Greek + 8 EPL).
- ⚠️ **`lineups` ↔ `player_match_stats` cannot be joined on `player_id`** for these players.
- ⚠️ **Any downstream logic treating lineup membership as ground truth for "did this player start?" is wrong for ~10% of Greek player-fixture slots.**

~~**Safe practice until reconciled:** join within a table on `(fixture_id, player_id)`. Never assume cross-table player-id membership between `lineups` and `player_match_stats`.~~

> **S16 — SUPERSEDED (D-114).** Cross-table player joins are now safe **through the link table**: resolve `lineups.player_id` via `curated.player_identity_links.alias_player_id → canonical_player_id`, falling back to the id itself when no link row exists (absence = already canonical, or unresolved). **Do not join raw `player_id` across the two tables without that resolution step** — the 56 aliases will silently miss. A `v_lineups_resolved` view was deliberately deferred (Rule 2): nothing consumes it yet, and the link table is the source of truth regardless.

---

## 5. FINDING: `height` / `weight` arrive in mixed formats

EPL sends bare strings uniformly (`"193"`, `"76"`). **Greece does not.**

Of 557 roster-enriched Greek players, **61 (~11%)** carry unit suffixes:

```
Óscar Pinchi      171 cm / 62 kg
Soufiane Chakla   188 cm / 73 kg
Davide Calabria   177 cm / 70 kg
Diego Esteban     183 cm / 68 kg     <- also a dual-identity player
Goni Naor         185 cm / (null)
```

The rest are bare (`184` / `76`). Both columns are `text`, stored **verbatim, with no unit parsing** — which is correct and lossless, and is why nothing broke.

**But `int(height)` crashes on `"171 cm"`.** Nothing parses these today, so nothing is broken *yet*. This is a live landmine for the first Computed-layer feature that treats height or weight as a number. **Read-time normalisation is required, and it must handle: bare digits, `cm`/`kg` suffixes, and NULL.**

### How this was nearly missed — a method lesson

The S15 **smoke test** examined one player (Masouras: `184`/`76`) and concluded *"Greece sends bare, like EPL."* That conclusion was **the opposite of the truth**, and it survived until the 557-player census.

**A smoke test proves the worker runs. Only a census characterises a distribution.** The smoke test wasn't executed badly — it was asked a question it structurally cannot answer. Never answer a coverage question from a sample of one.

---

## 6. FINDING: Coaches are a real entity with turnover and a stable id

**Null rate: 0.0% in both leagues** (EPL 0/760; Greece 0/470 team-blocks, 0/10,639 lineup rows). `coach_source_ref` is populated and stable.

EPL made coaches look like a boring always-present string. Greece shows otherwise:

- **23 distinct coaches** across 14 teams.
- **10 of 14 teams changed coach mid-season.** Larisa had **three**: Festa → Petrakis → Pantelidis.
- **Savvas Pantelidis appears at two different clubs** (Larisa and Asteras) — coach identity is independent of team.

**Implication for a future `curated.coaches` entity (resolves Q-NEW-AH):** the case is now real, not hypothetical. A `coach_name` string denormalised onto 10,639 lineup rows cannot represent an entity that changes mid-season and moves between clubs. `coach_source_ref` gives a usable key, so the entity is tractable whenever it's wanted.

*Caveat: two leagues is two data points, not a law.*

---

## 7. The full coverage census — `match_statistics`

Greek (472 rows) vs EPL (760 rows), sorted by divergence:

| Column | GK null% | EPL null% | \|Δ\| | Reading |
|---|---:|---:|---:|---|
| `goals_prevented` | 56.4% | 0.0% | 56.4% | **Real gap** — calendar-gated (§2) |
| `expected_goals` | 56.4% | 0.0% | 56.4% | **Real gap** — calendar-gated (§2) |
| `red_cards` | 75.8% | 89.5% | 13.6% | **Not a gap** — event frequency (§3) |
| `offsides` | 3.4% | 5.5% | 2.1% | Not a gap — event frequency |
| `gk_saves` | 1.7% | 0.5% | 1.2% | Not a gap — event frequency |
| `yellow_cards` | 2.5% | 3.7% | 1.1% | Not a gap — event frequency |
| `shots_total`, `shots_on_goal`, `shots_off_goal`, `shots_inside_box`, `shots_outside_box`, `shots_blocked` | 0.0% | 0.0% | 0.0% | Identical |
| `possession_pct`, `passes_total`, `passes_accurate`, `passes_pct` | 0.0% | 0.0% | 0.0% | Identical |
| `fouls`, `corners` | 0.0% | 0.0% | 0.0% | Identical |

**Read the middle band carefully.** `red_cards` is *less* null on Greece than EPL — that is not better coverage, it's more red cards. Null-rate divergence on rare-event measures reflects **event frequency, not vendor supply**. Only the xG pair is a genuine coverage gap.

**No measure is Greek-supplied-but-EPL-missing.** Greece equals EPL on all 16 core measures.

### Bio coverage (557 roster-enriched Greek players)

| Field group | Null rate |
|---|---:|
| `firstname`, `lastname`, `birth_date`, `birth_country`, `nationality` | 8.6% |
| `photo_url` | **0.0%** |
| `height` | 31.2% |
| `weight` | 40.0% |
| `birth_place` | 35.4% |

Identity and photo coverage is strong; **physical attributes are the real gap**. (Page 1 alone suggested ~60% height/weight null — a biased sample dominated by never-played inserts. The census corrected it. Same lesson as §5.)

---

## 8. Operational notes

### 8.1 Storage — the first real unit-economics datum

| | bytes | MiB | % of 400 MiB trigger |
|---|---:|---:|---:|
| S15 open | 25,971,859 | 24.77 | 6.19% |
| S15 close | 34,565,267 | 32.96 | 8.24% |
| **One league-season** | **8,593,408** | **8.20** | **2.05 pp** |

**≈ 36 KB per fixture, including landed raw payloads.** At 367 MiB of headroom: **≈ 45 more league-seasons** before the D-084 Pro-upgrade trigger. This is the number the expansion roadmap needs.

### 8.2 Vendor group vocabulary does not match between endpoints (feeds Q-NEW-AU)

`fixtures.round` and `standings.group_label` use **different words for the same phase**:

| `fixtures.round` | `standings.group_label` | Rows |
|---|---|---:|
| `Regular Season - N` | `'Super League '` *(trailing space)* | 14 |
| `Championship Group - N` | `'Super League , Championship Round'` | 4 |
| `Relegation Group - N` | `'Super League , Relegation Round'` | 6 |
| `Conference League Group - N` | `'Super League , Qualifying Round'` | **4** |

Cardinality picks the regular-season table cleanly (14 = largest). **But it cannot disambiguate the two 4-team groups** — and the one place names would help, the vendor changed the word (`Conference League` vs `Qualifying`). **Never string-match these labels.** Curation is unaffected: both vocabularies are stored verbatim.

### 8.3 Venues: 81% of Greek fixtures carry no vendor venue id

`fixture.venue.id` is null on **191 of 236** Greek fixtures (`venue.name` is always present). All **45** non-null ids resolve cleanly (3 distinct: Panthessaliko→52, Serron→51, OPAP Arena→42). The unresolvable branch (present id, no matching venue row) **does not occur** in this season and remains untested by real data.

The 191 nulls are genuine vendor absence — D-081 by design. **If those venues are ever wanted, the lever is `venue.name`/`city` (always present), not the vendor id.**

*Note: the 14 Greek teams have 14 distinct venues. The predicted Athens groundshare does not exist per the vendor (AEK→OPAP Arena, Panathinaikos→Apostolos Nikolaidis, Olympiakos→Karaiskaki). D-104c's silent-collapse branch stays unexercised by real data.*

### 8.4 `remaining_budget` is unreliable; `calls_made` is honest

The vendor's `x-ratelimit-requests-remaining` header is **non-monotonic** — it moved *backwards* mid-run (74884 → 74896) and read 74991 late in the session after 67015 earlier. Likely multiple API nodes with divergent counts. **Trust `calls_made` (our own count). Never compute session cost from `remaining_budget` deltas.**

### 8.5 `PYTHONUNBUFFERED`

Long worker runs writing to a file appear **frozen** — Python block-buffers stdout (~8 KB) when not attached to a terminal. This cost real attention in S15 ("stuck at 128" was buffering, not a stall). **Always set `$env:PYTHONUNBUFFERED = "1"` alongside `PYTHONIOENCODING` for background runs.**

Also: set `chcp 65001` before reading any non-English payload. The Windows console defaults to cp1252 and mangles UTF-8 on display — cosmetic, but it makes logs untrustworthy exactly when you're reading them for surprises.

---

## 9. Checklist for league #3

Run this before trusting a new league's data. Each item exists because it caught something real.

**Spine, before ingest**
1. League row, season row, coverage flags. Standings row-count and distinct teams.
2. `0` fixtures — confirm a clean slate.
3. Teams vs venues: any shared `venue_id`? (Groundshare → D-104c's silent branch.)

**Probe, before running any worker**
4. Live payload probe. **Reconcile the fixture count arithmetically** (teams × rounds). If it doesn't reconcile, the paging is lying.
5. Distinct `round` labels and `status.short` values.
6. `venue.id` null rate; do non-null ids **resolve** against `curated.venues`?

**Per worker**
7. Smoke first **where `--limit` works** (`LOOP_ENTITIES` only: `match_statistics`, `player_match_stats`, `lineups`, `player_bio`). For `fixtures`, `--limit` is **silently ignored** — a single page transaction is all-or-nothing.
8. Read **every** unmapped-leaf log. Empty `source_extra` is only meaningful if the worker *has* catch-all logic — `fixtures` does not (Q-NEW-AO), so its silence is not evidence.
9. Landed vs attempts (D-104). Cross-check every reported count against a DB delta.

**Census, after ingest — never from the smoke test**
10. **Null-rate census per measure, vs an already-characterised league.** Sort by divergence.
11. For every divergent measure, ask: **coverage gap, or event frequency?** Rare-event measures diverge for reasons that aren't coverage.
12. For every real gap, find the **structural boundary** — cut by date *and* by round. Postponed fixtures are the tell.
13. **Format census on every text column** (`height`, `weight`): are values homogeneous? A sample of one will lie.
14. **Membership cross-check**: `lineups` vs `player_match_stats` player sets, per fixture+team. Then the **jersey test** on any divergence.
15. Coach null-rate; distinct coaches; mid-season changes.
16. DB size delta → cost per league-season.

**Identity — added Session 16 (D-114…D-121)**

17. **Verify jersey uniqueness BEFORE relying on it.** `(fixture_id, team_id, jersey_number)` in *both* `lineups` and `player_match_stats` — **no DB constraint enforces it**; it is a data property. Also count NULL jerseys: a NULL cannot match. (Both leagues: 0 violations, 0 NULLs — but that is two data points, not a law.)
18. **Run the reconciler — it is NOT automatic** (D-115). `python -m statesta_sync.identity_links --league N --season Y --dry-run` first (it exercises the real write path and rolls back, D-119), then live. It must run **after** `player_match_stats` and `lineups`, and it makes **zero API calls**.
19. **Read the reconciler's output as the census, not the run log**: `aliases_found` (how many divergent ids this league minted), `linked`, `with_dissent` (Q-NEW-BG mis-slots), `needs_review` (single-row hypotheses), `ambiguous` (ties — refused, **investigate every one**), `unmatched` (aliases with no jersey counterpart at all — **investigate every one**).
20. **Eyeball the alias→canonical name pairs.** Not as a test — as a *sanity read*. **Names disagreeing does NOT mean the link is wrong** (D-120: `M. Flores` ↔ `Wellity Lucky` is one human; the vendor renames as well as re-ids). Names agreeing does not mean it is right either. **Recurrence is the evidence; names are decoration.**
21. **If this league breaks the majority-vote rule** — a near-even split, a chain, reverse ambiguity — **stop and re-derive**. `uq_pil_alias` assumes one canonical per alias, and that assumption is earned per league, not granted.

**The standing lesson**

> Architectural reasoning about this vendor has been wrong repeatedly and empirical checks have been right every time. When a prediction is cheap to test, test it instead of trusting it. Several S15 findings — dual identity, mixed units, the EPL "8 bench-only" — were the *opposite* of a confident prediction.
>
> **S16 sharpened this to the point of embarrassment: seven predictions falsified in a single session**, including an "unknown process writing to production" that was S15's own `player_bio` run crossing midnight, and a "zero ambiguity, both leagues" result that was an artefact of a filter which also hid the counter-example. **Every one was caught by a check designed because the prediction was uncertain.** The rule now extends to Claude's own artefacts: **derive literals from the code, never hand-type from memory** — S16 lost time to a missing `updated_at` trigger, `Json` vs `Jsonb`, and an expectation about a comment in a file written forty minutes earlier.
