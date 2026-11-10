"""Optional ``reference`` field on movements (T043)."""

import sqlite3

from inventory import db


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_movement_reference_stored_and_returned_on_post(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=5,
        to_location_id=loc_a["id"],
        reference="PO-12345",
    )
    assert r.status_code == 201, r.text
    assert r.json()["reference"] == "PO-12345"


def test_movement_reference_returned_on_get(client, item, loc_a):
    _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=5,
        to_location_id=loc_a["id"],
        reference="PO-9",
    )
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["reference"] == "PO-9"


def test_movement_reference_defaults_to_none(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])
    assert r.status_code == 201
    assert r.json()["reference"] is None
    assert client.get("/movements").json()[0]["reference"] is None


def test_movement_reference_explicit_null_accepted(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference=None,
    )
    assert r.status_code == 201
    assert r.json()["reference"] is None


def test_movement_reference_exactly_64_chars_accepted(client, item, loc_a):
    ref = "R" * 64
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference=ref,
    )
    assert r.status_code == 201
    assert r.json()["reference"] == ref


def test_movement_reference_longer_than_64_chars_rejected_422(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=1,
        to_location_id=loc_a["id"],
        reference="R" * 65,
    )
    assert r.status_code == 422
    # nothing was recorded
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_movement_reference_persisted_in_db_column(client, item, loc_a, tmp_path):
    _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=2,
        to_location_id=loc_a["id"],
        reference="PO-777",
    )
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    try:
        (ref,) = conn.execute("SELECT reference FROM movements WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert ref == "PO-777"


def test_movements_table_has_reference_column(tmp_path):
    path = str(tmp_path / "fresh.db")
    db.init_db(path)
    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()]
    finally:
        conn.close()
    assert "reference" in columns


def test_init_db_adds_reference_column_to_existing_db(tmp_path):
    """Databases created before the column existed get it via migration."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                qty INTEGER NOT NULL,
                from_location_id INTEGER,
                to_location_id INTEGER,
                note TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = sqlite3.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(movements)").fetchall()]
    finally:
        conn.close()
    assert "reference" in columns
