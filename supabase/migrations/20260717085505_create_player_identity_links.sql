-- Session 16 — Q-NEW-AZ / D-110: vendor dual-identity reconciliation
--
-- WHAT THIS SOLVES
--   API-Football issues two different player ids for the same human:
--   /fixtures/lineups uses a divergent id space; /players + /fixtures/players
--   + /fixtures/statistics agree on a canonical id. curated.players therefore
--   holds 56 duplicate person rows (48 Greek + 8 EPL) — thin lineup seeds that
--   carry zero match statistics because the stats landed under the other id.
--
-- WHAT THIS TABLE IS
--   A record that one vendor player id (the alias) denotes the same human as
--   another (the canonical), together with the evidence for that claim.
--
-- WHAT THIS TABLE IS NOT
--   It does not modify curated.players. No merge, no delete, no flag column.
--   Both vendor rows stay exactly as landed (D-051/D-086 verbatim storage).
--   Identity is INTERPRETATION and lives beside the data, not inside it —
--   the same shape as D-108 (NULL semantics), D-111 (height/weight units) and
--   D-097 (source_extra): record faithfully, interpret downstream.
--
-- WHY A TABLE AND NOT A NULLABLE COLUMN ON curated.players
--   A canonical_player_id column would make NULL mean two different things at
--   once — "I am canonical" AND "unresolved, never matched". That is exactly
--   the epistemic hazard named in Q-NEW-BE (a NULL that reads as "nothing
--   arrived" when it means "we never looked"). Here, absence of a row is a
--   clean third state: unresolved. Presence always carries its evidence.
--
-- OWNERSHIP
--   Reconciler-owned. No sync worker writes here. lineups.py and player_bio.py
--   are unchanged and structurally cannot clobber it. Re-running any ingest
--   worker at 0 API cost leaves this table untouched.

CREATE TABLE curated.player_identity_links (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Convention columns (D-039 sport, D-049 source). Descriptive/queryable:
    -- the real key is alias_player_id, which is already sport+source scoped by
    -- virtue of being a curated.players row. Kept for scoping and for the
    -- multi-source future (Q-NEW-V).
    sport                text NOT NULL,
    source               text NOT NULL,

    -- The duplicate id (lineups-side thin seed) and the id that carries the
    -- match statistics. "Canonical" is defined OPERATIONALLY as the id holding
    -- the player_match_stats rows — NOT as "the id on the /players roster".
    -- Roster presence was disproven as a canonicity test in S16: Tzovaras
    -- appears on the roster under BOTH ids (2386 page 1, 353061 page 13).
    alias_player_id      bigint NOT NULL,
    canonical_player_id  bigint NOT NULL,

    -- How the link was established.
    --   jersey_fixture_team_majority — jersey is unique per team per match
    --     (empirically verified: 0 violations, 0 NULL jerseys, both leagues),
    --     so a same-(fixture, team, jersey) pairing is identity. Aggregated by
    --     majority vote across all of the alias's rows, because the vendor's
    --     /fixtures/lineups feed occasionally mis-slots a substitute into the
    --     OPPONENT's team block, where that jersey belongs to a real opponent
    --     player (Q-NEW-BG). Those collisions are structurally one-off; true
    --     pairings recur. Observed majorities: 93.3%-97.1%, median 96.7%,
    --     zero cases below 80%.
    --   birth_date_name — retained as a permitted value, but it matched ZERO
    --     of the 817 known pairs: the vendor sends birth.date = null for the
    --     canonical twins (verified in the landed payload for 353061), and the
    --     alias thin seeds have no bio at all. It is a dead end for THIS
    --     population; it may serve a future league. Supersedes the premise of
    --     D-113, which named birth_date the natural reconciliation key.
    --   manual — a human decision, for anything the matcher cannot settle.
    match_method         text NOT NULL,

    -- The evidence for the claim, so a future league that breaks the jersey
    -- assumption is a re-run rather than an archaeology project. Shape:
    --   {"chosen": <canonical_id>,
    --    "candidates": {"<canonical_id>": <supporting_row_count>, ...},
    --    "majority_fraction": <numeric>,
    --    "dissent_rows": [{"fixture_id":…, "team_id":…, "jersey_number":…,
    --                      "canonical_player_id":…}],
    --    "sample_pairs":  [{"fixture_id":…, "team_id":…, "jersey_number":…}]}
    match_evidence       jsonb NOT NULL,

    -- Rows supporting the chosen canonical, and rows supporting anything else.
    -- match_dissent_count > 0 means the vendor contradicted itself somewhere in
    -- this alias's history; the link still stands on the majority.
    match_pair_count     integer NOT NULL,
    match_dissent_count  integer NOT NULL DEFAULT 0,

    -- Set by the reconciler when the evidence is not decisive (no strict
    -- majority, or a single supporting row with no corroboration). A link with
    -- needs_review = true is a hypothesis, not a fact.
    needs_review         boolean NOT NULL DEFAULT false,

    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_pil_alias FOREIGN KEY (alias_player_id)
        REFERENCES curated.players(id) ON DELETE RESTRICT,
    CONSTRAINT fk_pil_canonical FOREIGN KEY (canonical_player_id)
        REFERENCES curated.players(id) ON DELETE RESTRICT,

    -- A player cannot be an alias of himself.
    CONSTRAINT ck_pil_not_self CHECK (alias_player_id <> canonical_player_id),

    CONSTRAINT ck_pil_method CHECK (match_method IN
        ('jersey_fixture_team_majority', 'birth_date_name', 'manual')),

    CONSTRAINT ck_pil_counts CHECK (
        match_pair_count > 0 AND match_dissent_count >= 0),

    -- One canonical per alias. This is the constraint that makes the table a
    -- function rather than a suggestion. Verified reachable: reverse ambiguity
    -- (one canonical claimed by two aliases) and chains (an alias resolving to
    -- something that is itself an alias) are both 0 in both leagues.
    CONSTRAINT uq_pil_alias UNIQUE (alias_player_id)
);

-- updated_at is owned by the trigger, never hand-set by any writer (the S12
-- convention). curated.set_updated_at() already exists — do not recreate it.
CREATE TRIGGER trg_player_identity_links_updated_at
    BEFORE UPDATE ON curated.player_identity_links
    FOR EACH ROW EXECUTE FUNCTION curated.set_updated_at();

-- Reverse lookup: "which ids are aliases of this canonical player?"
CREATE INDEX ix_pil_canonical
    ON curated.player_identity_links (canonical_player_id);

-- Partial index — the review queue is expected to stay small or empty.
CREATE INDEX ix_pil_needs_review
    ON curated.player_identity_links (needs_review)
    WHERE needs_review;

COMMENT ON TABLE curated.player_identity_links IS
    'Vendor dual-identity reconciliation (D-110 / Q-NEW-AZ). Records that '
    'alias_player_id and canonical_player_id are the same human, with the '
    'evidence. Reconciler-owned; no sync worker writes here. Absence of a row '
    'means unresolved. curated.players is never modified.';
