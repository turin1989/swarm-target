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
