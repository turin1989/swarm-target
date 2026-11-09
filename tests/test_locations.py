"""Tests for location endpoints, including activation/deactivation."""


def test_create_location_defaults_to_active(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active"] is True


def test_get_location_includes_active(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_location_can_deactivate_and_reactivate(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.json()["active"] is False

    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_location_can_update_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"code": "WH-A2", "name": "Warehouse A2"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == "Warehouse A2"
    assert body["active"] is True


def test_put_location_404_for_missing(client):
    r = client.put("/locations/9999", json={"active": False})
    assert r.status_code == 404


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"active": False})
    assert r.status_code == 200

    r = client.get("/locations")
    assert r.status_code == 200
    assert {loc["id"] for loc in r.json()} == {loc_a["id"], loc_b["id"]}

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200
    assert [loc["id"] for loc in r.json()] == [loc_a["id"]]

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200
    assert [loc["id"] for loc in r.json()] == [loc_b["id"]]


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
