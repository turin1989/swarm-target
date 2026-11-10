"""Movements record a created_at timestamp (T042)."""

from datetime import datetime, timedelta, timezone

from inventory.db import connect, init_db


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 string and require it to be UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert dt.tzinfo is not None, "created_at must carry a timezone"
    assert dt.utcoffset() == timedelta(0), "created_at must be UTC"
    return dt


def test_movement_response_includes_created_at(client, item, loc_a):
    before = datetime.now(timezone.utc)
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    after = datetime.now(timezone.utc)

    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    created = _parse_utc(body["created_at"])
    assert before <= created <= after


def test_created_at_persisted_in_movements_table(client, item, loc_a, tmp_path):
    _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    conn = connect(str(tmp_path / "test.db"))
    try:
        row = conn.execute("SELECT created_at FROM movements WHERE id = 1").fetchone()
    finally:
        conn.close()
    assert row is not None
    _parse_utc(row["created_at"])  # stored as ISO-8601 UTC string


def test_get_and_list_movements_include_created_at(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", quantity=2, to_location_id=loc_a["id"]
    ).json()

    got = client.get(f"/movements/{created['id']}").json()
    assert got["created_at"] == created["created_at"]
    _parse_utc(got["created_at"])

    listed = client.get("/movements").json()
    assert [m["created_at"] for m in listed] == [created["created_at"]]


def test_reverse_movement_gets_its_own_created_at(client, item, loc_a):
    original = _move(
        client, item_id=item["id"], kind="receive", quantity=4, to_location_id=loc_a["id"]
    ).json()
    reversal = client.post(f"/movements/{original['id']}/reverse").json()
    _parse_utc(reversal["created_at"])
    assert _parse_utc(reversal["created_at"]) >= _parse_utc(original["created_at"])


def test_migration_adds_created_at_to_existing_db(tmp_path):
    """Databases created before the created_at column are migrated in place."""
    db_path = str(tmp_path / "old.db")
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                unit_price REAL NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                barcode TEXT UNIQUE
            );
            CREATE TABLE locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL
            );
            CREATE TABLE stock_levels (
                item_id INTEGER NOT NULL,
                location_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (item_id, location_id)
            );
            CREATE TABLE movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                qty INTEGER NOT NULL,
                from_location_id INTEGER,
                to_location_id INTEGER,
                note TEXT NOT NULL DEFAULT '',
                reference TEXT
            );
            CREATE TABLE schema_version (version INTEGER NOT NULL);
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    conn = connect(db_path)
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(movements)")}
    finally:
        conn.close()
    assert "created_at" in cols
