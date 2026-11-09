"""Tests for location endpoints."""


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "WH-A" in body["error"]["message"]


def test_distinct_location_codes_allowed(client, loc_a):
    r = client.post("/locations", json={"code": "WH-C", "name": "Warehouse C"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "WH-C"


def test_locations_code_column_is_unique_in_schema():
    import sqlite3

    from inventory.db import SCHEMA

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA)
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_cols = set()
        for idx in indexes:
            if idx[2]:  # unique flag
                for info in conn.execute(f"PRAGMA index_info('{idx[1]}')"):
                    unique_cols.add(info[2])
        assert "code" in unique_cols
    finally:
        conn.close()
