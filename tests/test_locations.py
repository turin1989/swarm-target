"""Tests for location endpoints, in particular duplicate-code handling (T007)."""

import sqlite3

from inventory.db import SCHEMA


def test_create_location_ok(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text

    r2 = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r2.status_code == 409, r2.text


def test_duplicate_location_code_detail_mentions_code(client):
    client.post("/locations", json={"code": "WH-DUP", "name": "Warehouse"})
    r = client.post("/locations", json={"code": "WH-DUP", "name": "Other"})
    assert r.status_code == 409
    assert "WH-DUP" in r.json()["detail"]


def test_duplicate_code_does_not_create_extra_location(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    client.post("/locations", json={"code": "WH-A", "name": "Dup"})
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


# --- PUT /locations/{id} (T012) ------------------------------------------------


def test_update_location_name_only(client):
    created = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"}).json()
    r = client.put(f"/locations/{created['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == "WH-A"


def test_update_location_code_only(client):
    created = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"}).json()
    r = client.put(f"/locations/{created['id']}", json={"code": "WH-B"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-B"
    assert body["name"] == "Warehouse A"


def test_update_location_name_and_code(client):
    created = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"}).json()
    r = client.put(
        f"/locations/{created['id']}", json={"code": "WH-Z", "name": "Warehouse Z"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Warehouse Z"


def test_update_location_empty_payload_is_noop(client):
    created = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"}).json()
    r = client.put(f"/locations/{created['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == created


def test_update_location_persists(client):
    created = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"}).json()
    client.put(f"/locations/{created['id']}", json={"name": "New Name"})
    r = client.get(f"/locations/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


def test_update_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404, r.text
    assert "9999" in r.json()["detail"]


def test_update_location_duplicate_code_returns_409(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    other = client.post("/locations", json={"code": "WH-B", "name": "Warehouse B"}).json()
    r = client.put(f"/locations/{other['id']}", json={"code": "WH-A"})
    assert r.status_code == 409, r.text


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
            raise AssertionError("locations.code should be UNIQUE in the schema")

        # Confirm a unique index exists on the code column.
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_on_code = False
        for idx in indexes:
            name, unique = idx[1], idx[2]
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info('{name}')").fetchall()]
            if unique and cols == ["code"]:
                unique_on_code = True
        assert unique_on_code
    finally:
        conn.close()
