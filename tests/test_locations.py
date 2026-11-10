"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3

from inventory.db import SCHEMA


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["error"]["message"]


def test_duplicate_location_does_not_create_second_row(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409
    rows = client.get("/locations").json()
    assert [loc["code"] for loc in rows] == ["WH-A"]


def test_distinct_location_codes_still_accepted(client, loc_a, loc_b):
    assert loc_a["code"] == "WH-A"
    assert loc_b["code"] == "WH-B"


def test_locations_code_column_is_unique_in_schema():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        import pytest

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
    finally:
        conn.close()


# --- T013: DELETE /locations/{id} ---------------------------------------------


def test_delete_empty_location_returns_204_and_removes_it(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert loc_a["id"] not in [loc["id"] for loc in client.get("/locations").json()]


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/9999")
    assert r.status_code == 404, r.text


def test_delete_location_holding_stock_returns_409(client, item, loc_a):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 7, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409, r.text
    # location must still exist
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row_succeeds(client, item, loc_a):
    # receive then ship everything out: stock_levels row exists with quantity == 0
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 4, "to_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 4, "from_location_id": loc_a["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_location_does_not_touch_other_locations_stock(client, item, loc_a, loc_b):
    r = client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 3, "to_location_id": loc_b["id"]},
    )
    assert r.status_code == 201, r.text
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204, r.text
    levels = client.get(f"/locations/{loc_b['id']}/stock").json()["levels"]
    assert levels == [{"item_id": item["id"], "location_id": loc_b["id"], "quantity": 3}]


# --- T026: locations can be deactivated -----------------------------------------


def test_new_location_is_active_by_default(client, loc_a):
    assert loc_a["active"] is True
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_locations_active_column_defaults_to_1_in_schema():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        row = conn.execute("SELECT active FROM locations WHERE code = 'X'").fetchone()
        assert row["active"] == 1
    finally:
        conn.close()


def test_put_location_can_deactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["id"] == loc_a["id"]
    assert body["code"] == loc_a["code"]
    assert body["name"] == loc_a["name"]
    # change persists
    assert client.get(f"/locations/{loc_a['id']}").json()["active"] is False


def test_put_location_can_reactivate(client, loc_a):
    assert client.put(f"/locations/{loc_a['id']}", json={"active": False}).status_code == 200
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True
    assert client.get(f"/locations/{loc_a['id']}").json()["active"] is True


def test_put_location_without_active_leaves_it_unchanged(client, loc_a):
    assert client.put(f"/locations/{loc_a['id']}", json={"active": False}).status_code == 200
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["active"] is False


def test_put_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"active": False})
    assert r.status_code == 404, r.text


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    assert client.put(f"/locations/{loc_b['id']}", json={"active": False}).status_code == 200

    active = client.get("/locations", params={"active": "true"}).json()
    assert [loc["id"] for loc in active] == [loc_a["id"]]
    assert all(loc["active"] is True for loc in active)

    inactive = client.get("/locations", params={"active": "false"}).json()
    assert [loc["id"] for loc in inactive] == [loc_b["id"]]
    assert all(loc["active"] is False for loc in inactive)


def test_list_locations_without_filter_returns_all(client, loc_a, loc_b):
    assert client.put(f"/locations/{loc_b['id']}", json={"active": False}).status_code == 200
    rows = client.get("/locations").json()
    assert sorted(loc["id"] for loc in rows) == sorted([loc_a["id"], loc_b["id"]])


def test_init_db_migrates_legacy_locations_table(tmp_path):
    """Databases created before the active column was added get migrated."""
    from inventory import db

    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE locations ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "code TEXT NOT NULL UNIQUE, "
            "name TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO locations (code, name) VALUES ('OLD', 'Legacy')")
        conn.commit()
    finally:
        conn.close()

    db.init_db(path)

    conn = db.connect(path)
    try:
        row = conn.execute("SELECT active FROM locations WHERE code = 'OLD'").fetchone()
        assert row["active"] == 1
    finally:
        conn.close()
