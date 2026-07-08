"""Upsert helper + in-run resolution map (D-073).

Implements the one pattern every worker uses:

    INSERT ... ON CONFLICT (natural key) DO UPDATE ... RETURNING id

which gives idempotency (ARCHITECTURE §6.6): run the worker once or ten times
and you end up with exactly one row per entity, with our surrogate `id` stable.

`ResolutionMap` turns the vendor's `source_ref` into our surrogate `id`, using
an in-memory map (fast path, populated from RETURNING) and a SELECT fallback for
ids created in earlier runs.
"""

from __future__ import annotations

from typing import Any

from psycopg import sql

SPORT = "football"
SOURCE = "api_football"

# Every statement this module issues, as (sql_text, params). Purely for
# transparency/debugging — lets the caller print exactly what was sent.
ISSUED: list[tuple[str, list[Any]]] = []


# ---------------------------------------------------------------------------
# Admin-owned columns (project rule).
#
# A column is ADMIN-OWNED when a human, not the data source, is its authority.
# Such columns may be seeded on INSERT (so a newly discovered row has a sane
# starting value) but must NEVER appear in a DO UPDATE set — otherwise every
# re-sync would silently stomp an admin's decision (D-012, §4.2.4).
#
# Everything else is SOURCE-OWNED: the vendor is authoritative and a re-sync
# should refresh it.
#
# Registering a table here is mandatory; `upsert_returning_id` refuses to run
# against an unregistered table so a new entity can't quietly skip the rule.
# ---------------------------------------------------------------------------
ADMIN_OWNED_COLUMNS: dict[str, frozenset[str]] = {
    "curated.leagues": frozenset(
        {"tier_id", "needs_review", "suggested_tier_id", "tier_is_admin_set", "is_active"}
    ),
    # All source-owned today; registered so the guardrail still applies.
    "curated.league_seasons": frozenset(),
    "curated.venues": frozenset(),
    "curated.teams": frozenset(),
    "curated.standings": frozenset(),
}


def upsert_returning_id(
    cur,
    table: str,
    values: dict[str, Any],
    conflict_columns: list[str],
    update_columns: list[str],
) -> int:
    """INSERT ... ON CONFLICT (conflict_columns) DO UPDATE SET update_columns ... RETURNING id.

    `update_columns` deliberately excludes anything we must not clobber on a
    re-run (e.g. a league's admin-assigned tier). Columns are composed as SQL
    identifiers; values are always bound as parameters.
    """
    if not update_columns:
        raise ValueError("update_columns must be non-empty (else RETURNING id yields no row)")

    if table not in ADMIN_OWNED_COLUMNS:
        raise ValueError(
            f"{table!r} is not registered in ADMIN_OWNED_COLUMNS. Add it (with an empty "
            "frozenset if every column is source-owned) so the insert-only rule is explicit."
        )
    clobbered = ADMIN_OWNED_COLUMNS[table].intersection(update_columns)
    if clobbered:
        raise ValueError(
            f"{table}: admin-owned column(s) {sorted(clobbered)} may not appear in DO UPDATE — "
            "a re-sync must never overwrite an admin's choice. Set them on INSERT only."
        )

    schema_name, _, table_name = table.partition(".")
    columns = list(values)

    statement = sql.SQL(
        "insert into {tbl} ({cols}) values ({placeholders}) "
        "on conflict ({conflict}) do update set {assignments} "
        "returning id"
    ).format(
        tbl=sql.Identifier(schema_name, table_name),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        placeholders=sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
        conflict=sql.SQL(", ").join(sql.Identifier(c) for c in conflict_columns),
        assignments=sql.SQL(", ").join(
            sql.SQL("{c} = excluded.{c}").format(c=sql.Identifier(c))
            for c in update_columns
        ),
    )

    params = [values[c] for c in columns]
    ISSUED.append((statement.as_string(cur), params))
    cur.execute(statement, params)
    return cur.fetchone()[0]


class ResolutionMap:
    """vendor source_ref -> our surrogate id, per entity.

    Fast path: remember() the ids returned by RETURNING during this run.
    Fallback: a SELECT on the same natural key, for parents written in an
    earlier run and therefore absent from memory.
    """

    def __init__(self, sport: str = SPORT, source: str = SOURCE) -> None:
        self._map: dict[tuple[str, str], int] = {}
        self.sport = sport
        self.source = source

    def remember(self, entity: str, source_ref: Any, surrogate_id: int) -> None:
        self._map[(entity, str(source_ref))] = surrogate_id

    def resolve(self, cur, entity: str, source_ref: Any) -> int | None:
        """Return our id for this vendor ref, or None if we've never seen it."""
        key = (entity, str(source_ref))
        if key in self._map:
            return self._map[key]

        # SELECT fallback — same natural key, just read instead of write.
        if entity == "venues":
            cur.execute(
                "select id from curated.venues where source = %s and source_ref = %s",
                (self.source, str(source_ref)),
            )
        elif entity == "leagues":
            cur.execute(
                "select id from curated.leagues "
                "where sport = %s and source = %s and source_ref = %s",
                (self.sport, self.source, str(source_ref)),
            )
        elif entity == "teams":
            cur.execute(
                "select id from curated.teams "
                "where sport = %s and source = %s and source_ref = %s",
                (self.sport, self.source, str(source_ref)),
            )
        else:
            raise ValueError(f"no SELECT fallback configured for entity {entity!r}")

        row = cur.fetchone()
        if row is None:
            return None
        self._map[key] = row[0]
        return row[0]
