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


# --- PUT /locations/{id} (T012) ------------------------------------------------


def test_update_location_name(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Warehouse Alpha"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Warehouse Alpha"
    assert body["code"] == loc_a["code"]  # unchanged


def test_update_location_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == loc_a["name"]  # unchanged


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "New Name", "code": "NEW-CODE"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New Name"
    assert body["code"] == "NEW-CODE"


def test_update_location_empty_payload_returns_unchanged(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_persists(client, loc_a):
    client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed"})
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


def test_update_location_unknown_id_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404, r.text
    assert "9999" in r.json()["detail"]


def test_update_location_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": loc_a["code"]})
    assert r.status_code == 409, r.text


def test_location_update_model_exists():
    from inventory.models import LocationUpdate

    upd = LocationUpdate()
    assert upd.name is None
    assert upd.code is None
    upd2 = LocationUpdate(name="N", code="C")
    assert upd2.name == "N"
    assert upd2.code == "C"
