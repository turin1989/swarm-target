"""Tests for PUT /locations/{id} (rename a location)."""


def test_update_location_name_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Main Warehouse"
    assert body["code"] == loc_a["code"]  # unchanged


def test_update_location_code_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-MAIN"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-MAIN"
    assert body["name"] == loc_a["name"]  # unchanged


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Depot", "code": "DEP-1"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Depot"
    assert body["code"] == "DEP-1"

    # change is persisted
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json() == body


def test_update_location_empty_payload_returns_unchanged(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_unknown_id_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404
