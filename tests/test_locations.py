"""Tests for T007: duplicate location codes are rejected."""

import sqlite3

from inventory.db import SCHEMA


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text


def test_duplicate_location_code_detail_mentions_code(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    assert "WH-A" in r.json()["detail"]


def test_distinct_location_codes_still_accepted(client, loc_a, loc_b):
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes == ["WH-A", "WH-B"]


def test_duplicate_code_does_not_create_location(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert len(r.json()) == 1


def test_locations_code_column_is_unique_in_schema():
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("locations.code is not UNIQUE in the schema")
    finally:
        conn.close()


# --- T012: PUT /locations/{id} -------------------------------------------------


def test_update_location_name(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == "WH-A"
    assert body["id"] == loc_a["id"]


def test_update_location_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == "Warehouse A"


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"code": "WH-Z", "name": "Warehouse Z"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Warehouse Z"


def test_update_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_persists(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"name": "Persisted Name"})
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Persisted Name"


def test_update_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404, r.text
    assert "9999" in r.json()["detail"]


def test_update_location_to_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": "WH-A"})
    assert r.status_code == 409, r.text
