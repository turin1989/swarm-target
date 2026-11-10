"""Tests for the optional `reference` field on movements (T043)."""


def _receive(client, item, loc, **extra):
    payload = {
        "item_id": item["id"],
        "kind": "receive",
        "quantity": 5,
        "to_location_id": loc["id"],
    }
    payload.update(extra)
    return client.post("/movements", json=payload)


def test_create_movement_with_reference(client, item, loc_a):
    r = _receive(client, item, loc_a, reference="PO-12345")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["reference"] == "PO-12345"


def test_reference_defaults_to_none(client, item, loc_a):
    r = _receive(client, item, loc_a)
    assert r.status_code == 201, r.text
    assert r.json()["reference"] is None


def test_reference_explicit_null(client, item, loc_a):
    r = _receive(client, item, loc_a, reference=None)
    assert r.status_code == 201, r.text
    assert r.json()["reference"] is None


def test_reference_returned_on_get(client, item, loc_a):
    created = _receive(client, item, loc_a, reference="PO-GET-1").json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["reference"] == "PO-GET-1"


def test_reference_returned_in_listings(client, item, loc_a):
    _receive(client, item, loc_a, reference="PO-LIST-1")

    r = client.get("/movements")
    assert r.status_code == 200, r.text
    refs = [m["reference"] for m in r.json()]
    assert "PO-LIST-1" in refs

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200, r.text
    assert r.json()[0]["reference"] == "PO-LIST-1"


def test_reference_max_64_chars(client, item, loc_a):
    ok = _receive(client, item, loc_a, reference="X" * 64)
    assert ok.status_code == 201, ok.text
    assert ok.json()["reference"] == "X" * 64

    too_long = _receive(client, item, loc_a, reference="X" * 65)
    assert too_long.status_code == 422


def test_reference_persisted_in_db_column(client, item, loc_a, tmp_path):
    import sqlite3

    created = _receive(client, item, loc_a, reference="PO-DB-1").json()

    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(movements)")}
        assert "reference" in columns
        row = conn.execute(
            "SELECT reference FROM movements WHERE id = ?", (created["id"],)
        ).fetchone()
        assert row["reference"] == "PO-DB-1"
    finally:
        conn.close()


def test_migration_adds_reference_column(tmp_path):
    import sqlite3

    from inventory import db as dbmod

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                qty INTEGER NOT NULL,
                from_location_id INTEGER,
                to_location_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    dbmod.init_db(path)

    conn = dbmod.connect(path)
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(movements)")}
        assert "reference" in columns
    finally:
        conn.close()
