# RECORD ONLY — executed once in Session 18, kept for audit. NOT a live worker,
# NOT imported by spine.py. Relative imports below will not resolve from docs/;
# this file documents how the player.id=0 remediation was performed. See
# docs/S18_deleted_identity_links.json and PROJECT_STATUS.md D-124/D-125.
"""id0_backfill.py â€” Session 18, gate 4. Remediation for the player.id=0 phantom.

THROWAWAY (not committed): a one-shot DERIVATION worker (D-115) â€” reads curated + raw,
writes curated, NO API, NO new raw. Reuses the committed guard's own normalisation
(_build_stats_values) and seed (_upsert_player_seed) so remediated rows are byte-identical
to what a fresh guarded ingest would produce (D-124).

Fixes both S18 defects on the EXISTING data:
  * N pms rows merged onto the phantom players.id (misattribution) -> re-pointed to
    per-appearance synthetic players.
  * the pms rows never landed (fixture-scoped seen_refs data loss) -> inserted.
Then deletes the dead identity links (canonical = phantom) and the phantom row itself.

Atomic: everything runs in ONE transaction. --dry-run exercises every real write then
raises _DryRunRollback so nothing commits (D-119). Idempotent: a second live run finds
no phantom and is a clean no-op.

Run from backend/ with the venv interpreter:
    & '.\\.venv\\Scripts\\python.exe' -m statesta_sync.id0_backfill --dry-run
    & '.\\.venv\\Scripts\\python.exe' -m statesta_sync.id0_backfill        # live
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .config import ConfigError, load_config
from .db import connect
from .ingest_common import SOURCE, SPORT, _dig
from .player_match_stats import (
    _UPDATE_COLUMNS,
    _build_stats_values,
    _effective_player_ref,
    _parse_int,
    _upsert_player_seed,
)


class _DryRunRollback(RuntimeError):
    """Raised at the end of a --dry-run to unwind the transaction (D-119)."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="exercise every write, then roll back (commit nothing)")
    args = ap.parse_args()
    dry = args.dry_run

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 1

    print(f"=== id=0 backfill â€” {'DRY-RUN (rolls back)' if dry else 'LIVE (commits)'} ===\n")

    with connect(config.database_url) as conn:
        try:
            with conn.transaction():
                with conn.cursor() as cur:
                    _run(cur)
                    if dry:
                        raise _DryRunRollback()
        except _DryRunRollback:
            print("\n[dry-run] transaction rolled back â€” nothing committed.")
            return 0
    print("\n[live] transaction committed.")
    return 0


def _run(cur) -> None:
    # --- 0. locate the phantom (derive id, never hardcode) -------------------
    cur.execute(
        "select id, name from curated.players "
        "where source_ref = %s and source = %s and sport = %s",
        ("0", SOURCE, SPORT),
    )
    prow = cur.fetchall()
    if not prow:
        print("no phantom (source_ref='0') found â€” already remediated. No-op.")
        return
    if len(prow) != 1:
        raise RuntimeError(f"ABORT: expected 1 phantom, found {len(prow)}: {prow}")
    phantom_id, phantom_name = prow[0]
    print(f"phantom players.id={phantom_id} name={phantom_name!r}\n")

    # --- 1. identity-links premise (assert-and-abort) ------------------------
    cur.execute("select count(*) from curated.player_identity_links "
                "where canonical_player_id = %s", (phantom_id,))
    links_canon = cur.fetchone()[0]
    cur.execute("select count(*) from curated.player_identity_links "
                "where alias_player_id = %s", (phantom_id,))
    links_alias = cur.fetchone()[0]
    print(f"identity links referencing phantom: canonical={links_canon} alias={links_alias}")
    if links_alias != 0:
        raise RuntimeError(
            f"ABORT: phantom is an ALIAS in {links_alias} link(s) â€” unexpected, re-plan")

    # --- 2. existing phantom pms rows -> (fixture,team,jersey) -> pms.id ------
    cur.execute(
        "select id, fixture_id, team_id, jersey_number "
        "from curated.player_match_stats where player_id = %s", (phantom_id,))
    phantom_rows = cur.fetchall()
    phantom_map: dict[tuple[int, int, Any], int] = {}
    for pms_id, fid, tid, jersey in phantom_rows:
        phantom_map[(fid, tid, jersey)] = pms_id
    if len(phantom_map) != len(phantom_rows):
        raise RuntimeError("ABORT: phantom pms rows share a (fixture,team,jersey) key")
    print(f"phantom pms rows: {len(phantom_rows)}\n")

    # --- 3. resolution maps + affected fixtures ------------------------------
    cur.execute("select source_ref, id from curated.fixtures where sport=%s and source=%s",
                (SPORT, SOURCE))
    fixture_ids = {ref: fid for ref, fid in cur.fetchall()}
    id_to_fref = {fid: ref for ref, fid in fixture_ids.items()}
    cur.execute("select source_ref, id from curated.teams where sport=%s and source=%s",
                (SPORT, SOURCE))
    team_ids = {ref: tid for ref, tid in cur.fetchall()}

    affected_fids = {r[1] for r in phantom_rows}
    affected_refs = sorted(id_to_fref[fid] for fid in affected_fids)

    cur.execute(
        "select distinct on (request_params->>'fixture') "
        "request_params->>'fixture', response_body, source_fetched_at "
        "from raw.api_responses "
        "where endpoint = '/fixtures/players' and request_params->>'fixture' = any(%s) "
        "order by request_params->>'fixture', id desc",
        (affected_refs,))
    raw_by_fixture = {fr: (body, fetched) for fr, body, fetched in cur.fetchall()}
    print(f"affected fixtures: {len(affected_refs)}; raw bodies read: {len(raw_by_fixture)}\n")

    # --- 4. PASS A: read-only plan + assertions (no writes) ------------------
    plan = []  # (fref, tref, jersey, our_fid, our_tid, synthetic_ref, stat, fetched, vendor_name, klass)
    for fref, (body, fetched) in raw_by_fixture.items():
        for block in (body.get("response") or []):
            tref = _dig(block, "team", "id")
            for entry in (block.get("players") or []):
                pl = entry.get("player") or {}
                if pl.get("id") != 0:
                    continue
                stat = (entry.get("statistics") or [{}])[0] or {}
                jersey = _parse_int(_dig(stat, "games", "number"))
                if jersey is None:
                    raise RuntimeError(
                        f"ABORT: id=0 with NULL jersey in fixture={fref} team={tref} "
                        "â€” unexpected in this corpus (Q-NEW-BN)")
                our_fid = fixture_ids.get(str(fref))
                our_tid = team_ids.get(str(tref))
                if our_fid is None or our_tid is None:
                    raise RuntimeError(
                        f"ABORT: cannot resolve fixture={fref}/team={tref} to our ids")
                sref = _effective_player_ref(0, fref, tref, jersey)
                key = (our_fid, our_tid, jersey)
                klass = "REPOINT" if key in phantom_map else "INSERT"
                plan.append((fref, tref, jersey, our_fid, our_tid, sref, stat,
                             fetched, pl.get("name"), klass))

    repoints = [p for p in plan if p[9] == "REPOINT"]
    inserts = [p for p in plan if p[9] == "INSERT"]

    # assertion: target-collision â€” every (fixture, synthetic_ref) distinct
    targets = [(p[3], p[5]) for p in plan]
    if len(set(targets)) != len(targets):
        raise RuntimeError("ABORT: duplicate (fixture, synthetic_ref) target â€” key collision")
    # assertion: every phantom row consumed exactly once by a re-point
    repoint_ids = [phantom_map[(p[3], p[4], p[2])] for p in repoints]
    if sorted(repoint_ids) != sorted(phantom_map.values()):
        raise RuntimeError("ABORT: re-points do not bijectively cover the phantom rows")
    if len(repoint_ids) != len(set(repoint_ids)):
        raise RuntimeError("ABORT: a phantom row targeted by two appearances")

    print("--- PLAN (read-only) ---")
    print(f"  total id=0 appearances : {len(plan)}")
    print(f"  RE-POINT (existing)    : {len(repoints)}  (== phantom rows {len(phantom_rows)})")
    print(f"  INSERT (recovered)     : {len(inserts)}")
    print(f"  identity links to delete: {links_canon}")
    print("  appearances:")
    for fref, tref, jersey, _fid, _tid, sref, _stat, _f, vname, klass in sorted(plan):
        print(f"    [{klass:7}] {sref:22}  vendor_name={vname!r}")
    print("  (vendor_name shown for audit only â€” NOT stored on the player; "
          "name='Unidentified player', vendor name -> source_extra provenance)\n")

    # --- 5. PASS B: writes ---------------------------------------------------
    print("--- WRITES ---")
    ref_to_synthetic: dict[str, int] = {}
    for _fref2, _tref2, _j, _fid2, _tid2, sref, _stat2, fetched, _vn, _k in plan:
        # reuse the committed seed: id=0 branch -> name='Unidentified player',
        # vendor name -> source_extra, photo dropped. player dict carries id 0 + name.
        pl_dict = {"id": 0, "name": _vn, "photo": None}
        ref_to_synthetic[sref] = _upsert_player_seed(cur, pl_dict, sref, fetched)
    print(f"  synthetic players seeded : {len(ref_to_synthetic)}")

    repointed = 0
    for fref, tref, jersey, our_fid, our_tid, sref, _stat, _f, _vn, _k in repoints:
        target_pms_id = phantom_map[(our_fid, our_tid, jersey)]
        cur.execute(
            "update curated.player_match_stats set player_id = %s where id = %s",
            (ref_to_synthetic[sref], target_pms_id))
        if cur.rowcount != 1:
            raise RuntimeError(f"ABORT: re-point updated {cur.rowcount} rows for pms.id={target_pms_id}")
        repointed += 1
    print(f"  pms rows re-pointed      : {repointed}")

    unmapped_seen: set[str] = set()
    inserted = 0
    for fref, tref, jersey, our_fid, our_tid, sref, stat, fetched, _vn, _k in inserts:
        values = _build_stats_values(
            stat, our_fid, ref_to_synthetic[sref], our_tid, fetched, unmapped_seen)
        from .upsert import upsert_returning_id
        upsert_returning_id(cur, "curated.player_match_stats", values=values,
                            conflict_columns=["fixture_id", "player_id"],
                            update_columns=_UPDATE_COLUMNS)
        inserted += 1
    print(f"  pms rows inserted        : {inserted}")
    if unmapped_seen:
        print(f"  WARNING unmapped leaves on recovered rows: {sorted(unmapped_seen)}")
    else:
        print("  (recovered rows: every leaf mapped; source_extra NULL)")

    # --- 6. phantom must now be orphaned, then delete links + phantom --------
    cur.execute("select count(*) from curated.player_match_stats where player_id=%s",
                (phantom_id,))
    remaining = cur.fetchone()[0]
    if remaining != 0:
        raise RuntimeError(f"ABORT: phantom still has {remaining} pms rows after re-point")

    cur.execute("delete from curated.player_identity_links where canonical_player_id=%s",
                (phantom_id,))
    print(f"  identity links deleted   : {cur.rowcount} (expected {links_canon})")
    if cur.rowcount != links_canon:
        raise RuntimeError("ABORT: identity-link delete count mismatch")

    cur.execute("delete from curated.players where id=%s", (phantom_id,))
    print(f"  phantom players deleted  : {cur.rowcount} (expected 1)")
    if cur.rowcount != 1:
        raise RuntimeError("ABORT: phantom delete did not remove exactly 1 row")


if __name__ == "__main__":
    sys.exit(main())

