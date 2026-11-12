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


def test_duplicate_location_not_persisted(client, loc_a):
    r = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert r.status_code == 409
    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


def test_locations_code_column_is_unique_in_schema(tmp_path):
    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = connect(db_path)
    try:
        conn.execute("INSERT INTO locations (code, name) VALUES (?, ?)", ("X1", "First"))
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES (?, ?)", ("X1", "Second"))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected IntegrityError for duplicate location code")
    finally:
        conn.close()


def test_update_location_name(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == "WH-A"


def test_update_location_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Warehouse A"


def test_update_location_both_fields(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"code": "WH-NEW", "name": "New Warehouse"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-NEW"
    assert body["name"] == "New Warehouse"


def test_update_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == loc_a["code"]
    assert body["name"] == loc_a["name"]


def test_update_location_persists(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Persisted Name"})
    assert r.status_code == 200
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Persisted Name"


def test_update_unknown_location_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Nope"})
    assert r.status_code == 404, r.text
    assert "9999" in r.json()["detail"]


def test_update_location_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": "WH-A"})
    assert r.status_code == 409, r.text
