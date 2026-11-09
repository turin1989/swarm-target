"""SQLite connection handling and schema."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import Request

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    unit_price REAL NOT NULL DEFAULT 0,
    reorder_point INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    barcode TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS stock_levels (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    qty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (item_id, location_id)
);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    qty INTEGER NOT NULL,
    from_location_id INTEGER REFERENCES locations(id),
    to_location_id INTEGER REFERENCES locations(id),
    note TEXT NOT NULL DEFAULT '',
    reference TEXT
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""

SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string, e.g. '2026-01-02T03:04:05Z'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        # Older databases may predate the barcode column; add it if missing.
        item_columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        if "barcode" not in item_columns:
            conn.execute("ALTER TABLE items ADD COLUMN barcode TEXT")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_items_barcode ON items(barcode)"
            )
        # Older databases may predate the created_at column; add it if missing
        # and backfill existing rows so the column is always a valid timestamp.
        if "created_at" not in item_columns:
            conn.execute(
                "ALTER TABLE items ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            "UPDATE items SET created_at = ? WHERE created_at IS NULL OR created_at = ''",
            (utc_now_iso(),),
        )
        # Older databases may predate the locations.active column; add it if missing.
        location_columns = {r["name"] for r in conn.execute("PRAGMA table_info(locations)")}
        if "active" not in location_columns:
            conn.execute(
                "ALTER TABLE locations ADD COLUMN active INTEGER NOT NULL DEFAULT 1"
            )
        # Older databases may predate the UNIQUE constraint on locations.code;
        # enforce it with a unique index.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_locations_code ON locations(code)"
        )
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    finally:
        conn.close()


def get_schema_version(path: str) -> int:
    conn = connect(path)
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        return int(row["version"])
    finally:
        conn.close()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, committed on success."""
    conn = connect(request.app.state.db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
