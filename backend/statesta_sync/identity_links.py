"""Identity-link reconciliation — curated -> curated. No API. No raw landing.

WHAT THIS IS
    The first DERIVATION worker. Every worker before it is an INGEST worker:
    call the vendor, land the payload verbatim, normalize from the landed row
    (D-071). This one calls nothing. It reads curated, reasons over it, and
    writes a conclusion back to curated with the evidence attached.

    That is why it does NOT live in spine.py's ENTITIES dict. The dispatcher
    there opens an ApiFootballClient and passes a ResolutionMap; this job needs
    neither, and registering it would force an API key onto a worker that makes
    no calls. It has its own __main__ instead. Expect the Computed layer to be
    full of jobs shaped like this one.

WHAT IT SOLVES (D-110 / Q-NEW-AZ)
    API-Football issues two player ids for the same human. /fixtures/lineups
    mints its own; /players + /fixtures/players + /fixtures/statistics agree on
    a canonical one. So curated.players holds duplicate person rows — thin
    lineup seeds carrying zero statistics, because the stats landed under the
    other id. This worker records which alias is which canonical, and why.

THE MATCH RULE
    Jersey number is unique per team per match, so a same-(fixture, team,
    jersey) pairing between an alias's lineup row and a stat row is identity,
    not coincidence. Verified empirically before this was built on: zero
    uniqueness violations and zero NULL jerseys across both leagues.

    But a raw per-row jersey join is NOT a function. The vendor's
    /fixtures/lineups feed occasionally mis-slots a substitute into the
    OPPONENT's team block, where that jersey belongs to a real opponent player
    (Q-NEW-BG). Proven from the vendor's own payloads: for fixture 1400805 it
    lists alias 561126 as team 1123's #19, while /fixtures/players says team
    1123's #19 is Alfarela — and the alias's true self has a correctly
    attributed stat row on his real team in that same match.

    So we aggregate: per alias, tally every candidate and take the strict
    majority. A true pairing recurs in every fixture the player appears in; a
    mis-slot collision needs the vendor to err AND the jersey to collide, so it
    is structurally a one-off. Observed: majorities of 93.3%-97.1%, median
    96.7%, zero cases below 80%, every dissent exactly one row.

WHAT IT REFUSES TO DO
    * It never touches curated.players. No merge, no delete, no flag. Both
      vendor rows stay as landed (D-051/D-086).
    * It never overwrites a match_method='manual' link. A human decision
      outranks this matcher.
    * It writes no link where the evidence is not decisive. Absence of a row
      means unresolved — a clean third state, not a lie (cf. Q-NEW-BE).
    * It never hand-sets updated_at; the trigger owns it (the S12 convention).

ALIAS DEFINITION — the subtle part, and the one that took two wrong tries
    An alias is a player id with ZERO stat rows ANYWHERE (global, not
    league-scoped, not fixture-scoped). That is what the vendor mints for
    lineups-only: an id that never carries statistics.

    NOT an alias: a canonical player missing a stat row in ONE fixture. That is
    a vendor stat-gap, and he already has his own identity — linking him would
    assert that two humans are one. Scoping by "no stat row for THIS fixture"
    silently swallows those and is wrong.

--dry-run IS A PROOF, NOT A REPORT
    It runs the REAL write path — same upsert_returning_id calls, same Jsonb
    binding, same CHECK constraints, same FKs, same unique key — and then
    raises _DryRunRollback so the transaction unwinds and nothing is committed.
    This is the S14 discipline (synthetic cases rolled back so nothing reaches
    curated). A dry-run that skipped the writes would go green while proving
    nothing about the only part likely to be wrong.

USAGE
    python -m statesta_sync.identity_links --league 197 --season 2025 --dry-run
    python -m statesta_sync.identity_links --league 197 --season 2025
"""

from __future__ import annotations

import argparse
from collections import Counter

from psycopg.types.json import Jsonb

from .config import load_config
from .db import connect
from .ingest_common import SOURCE, SPORT, SyncError
from .upsert import upsert_returning_id

TABLE = "curated.player_identity_links"
MATCH_METHOD = "jersey_fixture_team_majority"

# updated_at is absent on purpose — the trigger owns it (S12 convention).
# created_at is absent on purpose — it must survive a re-run.
_UPDATE_COLUMNS = [
    "canonical_player_id",
    "match_method",
    "match_evidence",
    "match_pair_count",
    "match_dissent_count",
    "needs_review",
]

# Cap the sample pairs stored in evidence. The full pair list is re-derivable
# from curated at any time; the evidence is a reader's aid, not an archive.
_SAMPLE_CAP = 5


class _DryRunRollback(Exception):
    """Raised to unwind the transaction after exercising the real write path."""


_LEAGUE_SEASON_SQL = """
select ls.id
from curated.league_seasons ls
join curated.leagues l on l.id = ls.league_id
where l.sport = %(sport)s
  and l.source = %(source)s
  and l.source_ref = %(league_ref)s
  and ls.season = %(season)s
"""

# Every alias in this league-season, whether or not it resolves. Needed so the
# run can report what it could NOT link — silence about an unresolved alias is
# how a gap gets mistaken for completeness.
_ALIASES_SQL = """
select distinct l.player_id, pl.source_ref, pl.name
from curated.lineups l
join curated.fixtures f on f.id = l.fixture_id
join curated.players  pl on pl.id = l.player_id
where f.league_season_id = %(ls_id)s
  and not exists (
      select 1 from curated.player_match_stats p
      where p.player_id = l.player_id
  )
order by l.player_id
"""

# One candidate row per (alias lineup row, matching stat row). Aggregation
# happens in Python so the tally and the dissent are both inspectable.
_PAIRS_SQL = """
with alias_ids as (
    select distinct l.player_id
    from curated.lineups l
    join curated.fixtures f on f.id = l.fixture_id
    where f.league_season_id = %(ls_id)s
      and not exists (
          select 1 from curated.player_match_stats p
          where p.player_id = l.player_id
      )
)
select l.player_id            as alias_player_id,
       p.player_id            as canonical_player_id,
       l.fixture_id,
       l.team_id,
       l.jersey_number
from curated.lineups l
join alias_ids a on a.player_id = l.player_id
join curated.fixtures f on f.id = l.fixture_id
join curated.player_match_stats p
      on  p.fixture_id    = l.fixture_id
      and p.team_id       = l.team_id
      and p.jersey_number = l.jersey_number
where f.league_season_id = %(ls_id)s
  and l.jersey_number is not null
order by l.player_id, p.player_id, l.fixture_id
"""

_EXISTING_SQL = f"""
select alias_player_id, match_method
from {TABLE}
where sport = %(sport)s and source = %(source)s
"""


def _decide(alias_id: int, rows: list[tuple]) -> dict:
    """Turn one alias's candidate rows into a decision, or refuse to.

    Returns a dict with 'outcome' in {'linked', 'ambiguous'}. Ambiguous means
    no strict majority — we write nothing and say so.
    """
    tally = Counter(r[1] for r in rows)
    total = sum(tally.values())
    ranked = tally.most_common()
    top_id, top_n = ranked[0]

    # Strict majority required. A tie is not a decision; refusing is.
    if len(ranked) > 1 and ranked[1][1] == top_n:
        return {
            "outcome": "ambiguous",
            "alias_player_id": alias_id,
            "candidates": dict(tally),
            "reason": f"tie: {top_n} rows each for {ranked[0][0]} and {ranked[1][0]}",
        }

    dissent = total - top_n
    dissent_rows = [
        {
            "fixture_id": r[2],
            "team_id": r[3],
            "jersey_number": r[4],
            "canonical_player_id": r[1],
        }
        for r in rows
        if r[1] != top_id
    ]
    samples = [
        {"fixture_id": r[2], "team_id": r[3], "jersey_number": r[4]}
        for r in rows
        if r[1] == top_id
    ][:_SAMPLE_CAP]

    # A single uncorroborated row is indistinguishable from a mis-slot: one row
    # is exactly what a vendor mis-slot produces. Link it, but flag it as a
    # hypothesis rather than pretend it is a fact.
    needs_review = top_n == 1

    return {
        "outcome": "linked",
        "alias_player_id": alias_id,
        "canonical_player_id": top_id,
        "match_pair_count": top_n,
        "match_dissent_count": dissent,
        "needs_review": needs_review,
        "evidence": {
            "chosen": top_id,
            "candidates": {str(k): v for k, v in tally.items()},
            "majority_fraction": round(top_n / total, 4),
            "dissent_rows": dissent_rows,
            "sample_pairs": samples,
        },
    }


def reconcile_identity_links(
    conn,
    league: int,
    season: int,
    *,
    dry_run: bool = False,
) -> dict:
    """Reconcile vendor dual-identity for one league-season. Returns a report."""
    ls_id = None
    aliases: dict[int, dict] = {}
    linked = inserted = updated = 0
    needs_review = with_dissent = manual_preserved = 0
    ambiguous: list[dict] = []
    unmatched: list[dict] = []

    try:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(
                    _LEAGUE_SEASON_SQL,
                    {
                        "sport": SPORT,
                        "source": SOURCE,
                        "league_ref": str(league),
                        "season": season,
                    },
                )
                row = cur.fetchone()
                if row is None:
                    raise SyncError(
                        f"no curated.league_seasons row for league source_ref={league} "
                        f"season={season} — run --entity leagues first"
                    )
                ls_id = row[0]

                cur.execute(_ALIASES_SQL, {"ls_id": ls_id})
                aliases = {
                    r[0]: {"source_ref": r[1], "name": r[2]} for r in cur.fetchall()
                }

                cur.execute(_PAIRS_SQL, {"ls_id": ls_id})
                pairs = cur.fetchall()

                by_alias: dict[int, list[tuple]] = {}
                for r in pairs:
                    by_alias.setdefault(r[0], []).append(r)

                cur.execute(_EXISTING_SQL, {"sport": SPORT, "source": SOURCE})
                existing = {r[0]: r[1] for r in cur.fetchall()}

                print(
                    f"NOTE league_season_id={ls_id}  aliases={len(aliases)}  "
                    f"candidate pair rows={len(pairs)}  existing links={len(existing)}"
                )

                for alias_id in sorted(aliases):
                    meta = aliases[alias_id]

                    if alias_id not in by_alias:
                        unmatched.append({"player_id": alias_id, **meta})
                        continue

                    if existing.get(alias_id) == "manual":
                        manual_preserved += 1
                        print(f"NOTE alias={alias_id} left alone — match_method='manual'")
                        continue

                    d = _decide(alias_id, by_alias[alias_id])

                    if d["outcome"] == "ambiguous":
                        ambiguous.append(d)
                        print(
                            f"WARNING alias={alias_id} ambiguous — {d['reason']} — NOT linked"
                        )
                        continue

                    linked += 1
                    if d["needs_review"]:
                        needs_review += 1
                    if d["match_dissent_count"]:
                        with_dissent += 1

                    # Honest insert/update counting: classify against the set
                    # read BEFORE any write (the player_bio.inserted pattern,
                    # which was exact — unlike the per-appearance counter in
                    # Q-NEW-BB).
                    if alias_id in existing:
                        updated += 1
                    else:
                        inserted += 1

                    upsert_returning_id(
                        cur,
                        TABLE,
                        {
                            "sport": SPORT,
                            "source": SOURCE,
                            "alias_player_id": alias_id,
                            "canonical_player_id": d["canonical_player_id"],
                            "match_method": MATCH_METHOD,
                            "match_evidence": Jsonb(d["evidence"]),
                            "match_pair_count": d["match_pair_count"],
                            "match_dissent_count": d["match_dissent_count"],
                            "needs_review": d["needs_review"],
                        },
                        conflict_columns=["alias_player_id"],
                        update_columns=_UPDATE_COLUMNS,
                    )

                if dry_run:
                    print(
                        "NOTE --dry-run: real write path exercised "
                        f"({linked} upsert(s) issued) — rolling back now"
                    )
                    raise _DryRunRollback
    except _DryRunRollback:
        print("NOTE --dry-run: transaction rolled back, nothing committed")

    return {
        "league_season_id": ls_id,
        "aliases_found": len(aliases),
        "linked": linked,
        "inserted": inserted,
        "updated": updated,
        "needs_review": needs_review,
        "with_dissent": with_dissent,
        "manual_preserved": manual_preserved,
        "ambiguous": ambiguous,
        "unmatched": unmatched,
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile vendor dual-identity into curated.player_identity_links "
        "(reads curated, writes curated; no API calls, no raw landing)."
    )
    ap.add_argument("--league", type=int, required=True, help="vendor league id, e.g. 197")
    ap.add_argument("--season", type=int, required=True, help="season year, e.g. 2025")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="exercise the real write path, then roll back and write nothing",
    )
    args = ap.parse_args()

    config = load_config()
    with connect(config.database_url) as conn:
        try:
            result = reconcile_identity_links(
                conn, args.league, args.season, dry_run=args.dry_run
            )
        except SyncError as exc:
            print(f"RECONCILE FAILED — {exc}")
            return 1

    print(f"OK  league={args.league} season={args.season}  ->  {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
