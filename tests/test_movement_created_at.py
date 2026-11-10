"""Movements carry a server-managed created_at timestamp (T042)."""

import re
import sqlite3

from inventory import db as db_module

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_apply_movement_sets_created_at_iso_utc(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert "created_at" in body
    assert ISO_UTC.match(body["created_at"]), body["created_at"]


def test_created_at_returned_by_list_movements(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"]
    ).json()
    rows = client.get("/movements").json()
    assert rows and rows[0]["created_at"] == created["created_at"]


def test_created_at_returned_by_item_movements(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"]
    ).json()
    rows = client.get(f"/items/{item['id']}/movements").json()
    assert rows and rows[0]["created_at"] == created["created_at"]


def test_created_at_persisted_in_database(client, item, loc_a, tmp_path):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    conn = db_module.connect(str(tmp_path / "test.db"))
    try:
        row = conn.execute("SELECT created_at FROM movements").fetchone()
        assert row["created_at"] is not None
        assert ISO_UTC.match(row["created_at"]), row["created_at"]
    finally:
        conn.close()


def test_created_at_set_for_all_movement_kinds(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    moves = [
        _move(client, item_id=item["id"], kind="ship", quantity=2, from_location_id=loc_a["id"]),
        _move(
            client,
            item_id=item["id"],
            kind="transfer",
            quantity=3,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        ),
        _move(client, item_id=item["id"], kind="adjust", quantity=7, to_location_id=loc_a["id"]),
    ]
    for r in moves:
        assert r.status_code == 201, r.text
        assert ISO_UTC.match(r.json()["created_at"]), r.json()


def test_init_db_backfills_movements_created_at_for_legacy_databases(tmp_path):
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
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            qty INTEGER NOT NULL,
            from_location_id INTEGER,
            to_location_id INTEGER,
            note TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.execute("INSERT INTO items (sku, name) VALUES ('OLD-1', 'Legacy')")
    conn.execute(
        "INSERT INTO movements (item_id, kind, qty, to_location_id) VALUES (1, 'receive', 5, 1)"
    )
    conn.commit()
    conn.close()

    db_module.init_db(path)

    conn = db_module.connect(path)
    try:
        row = conn.execute("SELECT created_at FROM movements").fetchone()
        assert row["created_at"] is not None
        assert ISO_UTC.match(row["created_at"]), row["created_at"]
    finally:
        conn.close()
