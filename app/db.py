"""Database access layer for Gbox.

Uses SQLite via stdlib by default; swap DATABASE_URL to a postgresql:// URI later
and install asyncpg + SQLAlchemy/psycopg for production. The JSON columns are
stored as TEXT and (de)serialized here so callers always deal in Python objects.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = os.getenv("GBOX_DB", str(Path(__file__).resolve().parent.parent / "gbox.db"))
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "sqlite.sql"


def init_db() -> None:
    """Create tables if they do not exist."""
    with _connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _jdump(value) -> str | None:
    return None if value is None else json.dumps(value)


def _jload(value):
    return None if value is None else json.loads(value)


def insert(table: str, **fields) -> int:
    """Insert a row, serializing any dict/list values to JSON text. Returns rowid."""
    cols, placeholders, values = [], [], []
    for k, v in fields.items():
        if v is None:
            continue  # let column defaults apply
        cols.append(k)
        placeholders.append("?")
        values.append(_jdump(v) if isinstance(v, (dict, list)) else v)
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
    with _connect() as conn:
        cur = conn.execute(sql, values)
        conn.commit()
        return cur.lastrowid


def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def fetchone(sql: str, params: tuple = ()) -> dict | None:
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return None if row is None else dict(row)
