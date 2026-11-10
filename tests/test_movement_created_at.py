"""T042: movements record created_at (ISO-8601 UTC string)."""

import re
import sqlite3
from datetime import datetime, timezone

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _receive(client, item, loc, qty=5):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "receive",
            "quantity": qty,
            "to_location_id": loc["id"],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_movement_response_includes_created_at(client, item, loc_a):
    body = _receive(client, item, loc_a)
    assert "created_at" in body
    assert ISO_UTC.match(body["created_at"]), body["created_at"]


def test_created_at_is_current_utc_time(client, item, loc_a):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    body = _receive(client, item, loc_a)
    after = datetime.now(timezone.utc).replace(microsecond=0)
    created = datetime.strptime(body["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    assert before <= created <= after


def test_created_at_in_get_and_list_movements(client, item, loc_a):
    created = _receive(client, item, loc_a)

    got = client.get(f"/movements/{created['id']}")
    assert got.status_code == 200
    assert got.json()["created_at"] == created["created_at"]

    listed = client.get("/movements")
    assert listed.status_code == 200
    movements = listed.json()
    assert movements and all(ISO_UTC.match(m["created_at"]) for m in movements)


def test_created_at_column_persisted_in_db(client, item, loc_a, tmp_path):
    body = _receive(client, item, loc_a)
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        row = conn.execute(
            "SELECT created_at FROM movements WHERE id = ?", (body["id"],)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == body["created_at"]
    assert ISO_UTC.match(row[0])


def test_migration_adds_created_at_to_legacy_db(tmp_path):
    """Databases created before the column existed get migrated and backfilled."""
    from inventory import db as dbmod

    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
            barcode TEXT UNIQUE
        );
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );
        CREATE TABLE movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            qty INTEGER NOT NULL,
            from_location_id INTEGER REFERENCES locations(id),
            to_location_id INTEGER REFERENCES locations(id),
            note TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO items (sku, name) VALUES ('S1', 'Thing');
        INSERT INTO locations (code, name) VALUES ('WH-A', 'A');
        INSERT INTO movements (item_id, kind, qty, to_location_id)
        VALUES (1, 'receive', 3, 1);
        """
    )
    conn.commit()
    conn.close()

    dbmod.init_db(path)

    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT created_at FROM movements WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert ISO_UTC.match(row[0]), row[0]
