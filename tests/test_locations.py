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
    assert r.json()["error"]["code"] == "conflict"


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
