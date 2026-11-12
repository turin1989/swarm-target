"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3

from inventory.db import connect, init_db


def test_create_location(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "WH-A" in detail


def test_duplicate_location_code_not_inserted(client, loc_a):
    client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO locations (code, name) VALUES (?, ?)", ("WH-X", "Warehouse X")
        )
        try:
            conn.execute(
                "INSERT INTO locations (code, name) VALUES (?, ?)", ("WH-X", "Duplicate")
            )
        except sqlite3.IntegrityError as exc:
            assert "locations.code" in str(exc)
        else:
            raise AssertionError("expected IntegrityError for duplicate locations.code")
    finally:
        conn.close()
