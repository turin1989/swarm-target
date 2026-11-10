"""Tests for location endpoints (T007: duplicate location codes)."""

import sqlite3


def test_create_location(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["code"] == "WH-A"
    assert body["name"] == "Warehouse A"


def test_duplicate_location_code_returns_409(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text

    dup = client.post("/locations", json={"code": "WH-A", "name": "Another Warehouse"})
    assert dup.status_code == 409, dup.text


def test_duplicate_location_code_detail_mentions_code(client):
    r = client.post("/locations", json={"code": "WH-X", "name": "Warehouse X"})
    assert r.status_code == 201, r.text

    dup = client.post("/locations", json={"code": "WH-X", "name": "Duplicate"})
    assert dup.status_code == 409, dup.text
    body = dup.json()
    assert body["error"]["code"] == "conflict"
    assert "WH-X" in body["error"]["message"]


def test_duplicate_does_not_create_extra_location(client):
    client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    client.post("/locations", json={"code": "WH-A", "name": "Duplicate"})

    r = client.get("/locations")
    assert r.status_code == 200
    codes = [loc["code"] for loc in r.json()]
    assert codes.count("WH-A") == 1


# --- T012: PUT /locations/{id} -------------------------------------------------


def _create_location(client, code="WH-A", name="Warehouse A"):
    r = client.post("/locations", json={"code": code, "name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_update_location_name(client):
    loc = _create_location(client)
    r = client.put(f"/locations/{loc['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc["id"]
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == "WH-A"


def test_update_location_code(client):
    loc = _create_location(client)
    r = client.put(f"/locations/{loc['id']}", json={"code": "WH-B"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-B"
    assert body["name"] == "Warehouse A"


def test_update_location_name_and_code(client):
    loc = _create_location(client)
    r = client.put(f"/locations/{loc['id']}", json={"code": "WH-Z", "name": "Zone Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == "Zone Z"


def test_update_location_empty_body_is_noop(client):
    loc = _create_location(client)
    r = client.put(f"/locations/{loc['id']}", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == loc["code"]
    assert body["name"] == loc["name"]


def test_update_location_is_persisted(client):
    loc = _create_location(client)
    client.put(f"/locations/{loc['id']}", json={"name": "Persisted Name"})
    r = client.get(f"/locations/{loc['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Persisted Name"


def test_update_location_unknown_id_returns_404(client):
    r = client.put("/locations/99999", json={"name": "Nope"})
    assert r.status_code == 404, r.text


def test_update_location_duplicate_code_returns_409(client):
    _create_location(client, code="WH-A", name="Warehouse A")
    loc_b = _create_location(client, code="WH-B", name="Warehouse B")
    r = client.put(f"/locations/{loc_b['id']}", json={"code": "WH-A"})
    assert r.status_code == 409, r.text


def test_location_update_model_exists():
    from inventory.models import LocationUpdate

    upd = LocationUpdate()
    assert upd.name is None
    assert upd.code is None
    upd = LocationUpdate(name="N", code="C")
    assert upd.name == "N"
    assert upd.code == "C"


def test_locations_code_column_is_unique_in_schema(tmp_path):
    from inventory.db import init_db

    db_path = str(tmp_path / "schema.db")
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        # The UNIQUE constraint on locations.code must exist at the schema level.
        indexes = conn.execute("PRAGMA index_list('locations')").fetchall()
        unique_cols = set()
        for idx in indexes:
            # idx: (seq, name, unique, origin, partial)
            if idx[2]:  # unique
                for col in conn.execute(f"PRAGMA index_info('{idx[1]}')").fetchall():
                    unique_cols.add(col[2])
        assert "code" in unique_cols

        conn.execute("INSERT INTO locations (code, name) VALUES ('DUP', 'first')")
        try:
            conn.execute("INSERT INTO locations (code, name) VALUES ('DUP', 'second')")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("expected IntegrityError for duplicate location code")
    finally:
        conn.close()
