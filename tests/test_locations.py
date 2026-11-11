"""Tests for location endpoints, including duplicate code handling (T007)."""

import sqlite3


def test_create_location_duplicate_code_returns_409(client):
    r1 = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r1.status_code == 201, r1.text

    r2 = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A clone"})
    assert r2.status_code == 409, r2.text


def test_duplicate_location_error_detail_mentions_code(client):
    client.post("/locations", json={"code": "WH-DUP", "name": "First"})
    r = client.post("/locations", json={"code": "WH-DUP", "name": "Second"})
    assert r.status_code == 409
    assert "WH-DUP" in r.json()["detail"]


def test_duplicate_location_does_not_create_second_row(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    client.post("/locations", json={"code": "WH-A", "name": "Copy"})
    r = client.get("/locations")
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    from inventory.db import init_db

    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'one')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('X', 'two')")
        except sqlite3.IntegrityError as exc:
            assert "unique" in str(exc).lower()
        else:
            raise AssertionError("expected IntegrityError for duplicate locations.code")
    finally:
        conn.close()


def test_distinct_location_codes_still_allowed(client, loc_a, loc_b):
    assert loc_a["code"] == "WH-A"
    assert loc_b["code"] == "WH-B"
