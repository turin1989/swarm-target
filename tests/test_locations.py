"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3

from inventory.db import SCHEMA


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["detail"]


def test_duplicate_location_does_not_create_second_row(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409
    rows = client.get("/locations").json()
    assert [loc["code"] for loc in rows] == ["WH-A"]


def test_distinct_location_codes_still_accepted(client, loc_a, loc_b):
    assert loc_a["code"] == "WH-A"
    assert loc_b["code"] == "WH-B"


# --- T026: locations can be deactivated ---------------------------------------


def test_new_location_is_active_by_default(client, loc_a):
    assert loc_a["active"] is True


def test_get_location_includes_active_flag(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True


def test_put_location_can_deactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    # persisted
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.json()["active"] is False


def test_put_location_can_reactivate(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True


def test_put_location_without_active_keeps_flag(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"active": False})
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["active"] is False


def test_put_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"active": False})
    assert r.status_code == 404


def test_list_locations_filters_by_active_true(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})
    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200, r.text
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A"]


def test_list_locations_filters_by_active_false(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})
    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200, r.text
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-B"]


def test_list_locations_without_filter_returns_all(client, loc_a, loc_b):
    client.put(f"/locations/{loc_b['id']}", json={"active": False})
    r = client.get("/locations")
    assert r.status_code == 200, r.text
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A", "WH-B"]


def test_locations_active_column_defaults_to_1_in_schema():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        row = conn.execute("SELECT active FROM locations WHERE code = 'X'").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


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
