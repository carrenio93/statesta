"""Database helper — psycopg (v3) connection to Supabase Postgres.

Plumbing only: open a connection from DATABASE_URL. No schema/ingestion logic.

Connection-string note (matches backend/.env.example): the worker will run
multi-statement transactions and use RETURNING, so DATABASE_URL should be the
Supabase SESSION POOLER or DIRECT connection (port 5432), NOT the transaction
pooler (port 6543). We emit a warning if a 6543 URL is detected, but still try.
"""

from __future__ import annotations

import psycopg


def connect(database_url: str) -> psycopg.Connection:
    """Open a psycopg v3 connection to the given DATABASE_URL.

    Caller owns the connection (use it as a context manager to auto-close).
    """
    if ":6543" in database_url:
        print(
            "WARNING: DATABASE_URL points at port 6543 (Supabase transaction "
            "pooler). The sync worker needs multi-statement transactions and "
            "RETURNING — use the Session pooler or direct connection (port 5432) "
            "instead."
        )
    return psycopg.connect(database_url)
