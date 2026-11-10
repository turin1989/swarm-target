"""Movements record created_at (T042)."""

import re
import sqlite3
from datetime import datetime, timezone

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _assert_iso_utc(value):
    assert isinstance(value, str)
    assert ISO_UTC.match(value), value
    # Parseable as ISO-8601 and actually UTC.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_movement_response_includes_created_at(client, item, loc_a):
    before = datetime.now(timezone.utc).replace(microsecond=0)
    r = _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    after = datetime.now(timezone.utc)
    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    _assert_iso_utc(body["created_at"])
    parsed = datetime.fromisoformat(body["created_at"].replace("Z", "+00:00"))
    assert before <= parsed <= after


def test_created_at_column_set_in_database(client, item, loc_a, tmp_path):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT created_at FROM movements WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert row is not None
    _assert_iso_utc(row["created_at"])


def test_list_movements_includes_created_at(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    movements = client.get("/movements").json()
    assert len(movements) == 2
    for m in movements:
        _assert_iso_utc(m["created_at"])


def test_item_movements_include_created_at(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=3, to_location_id=loc_a["id"])
    movements = client.get(f"/items/{item['id']}/movements").json()
    assert len(movements) == 1
    _assert_iso_utc(movements[0]["created_at"])


def test_all_movement_kinds_record_created_at(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    _move(client, item_id=item["id"], kind="ship", qty=1, from_location_id=loc_b["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=2, to_location_id=loc_a["id"])
    movements = client.get("/movements").json()
    assert [m["kind"] for m in movements] == ["receive", "transfer", "ship", "adjust"]
    for m in movements:
        _assert_iso_utc(m["created_at"])


def test_apply_movement_sets_created_at_at_service_layer():
    from inventory.db import SCHEMA, connect
    from inventory.models import MovementCreate
    from inventory.services.stock import apply_movement

    conn = connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO items (sku, name, description, unit_price, reorder_point, active) "
        "VALUES ('S1', 'Widget', '', 1.0, 0, 1)"
    )
    conn.execute("INSERT INTO locations (code, name) VALUES ('WH-A', 'Warehouse A')")

    movement = apply_movement(
        conn,
        MovementCreate(item_id=1, kind="receive", qty=3, to_location_id=1),
    )
    _assert_iso_utc(movement.created_at)
    row = conn.execute("SELECT created_at FROM movements WHERE id = ?", (movement.id,)).fetchone()
    assert row["created_at"] == movement.created_at


def test_init_db_adds_created_at_to_existing_database(tmp_path):
    """Databases created before the column existed are migrated on init."""
    from inventory import db

    path = str(tmp_path / "old.db")
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
            active INTEGER NOT NULL DEFAULT 1
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
        """
    )
    conn.commit()
    conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(movements)").fetchall()}
    finally:
        conn.close()
    assert "created_at" in cols
