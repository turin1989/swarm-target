"""Tests for PUT /locations/{id} (rename / recode a location)."""


def test_update_location_name_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Main Warehouse"
    assert body["code"] == loc_a["code"]


def test_update_location_code_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == loc_a["name"]


def test_update_location_both_fields(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Renamed", "code": "NEW-CODE"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed"
    assert body["code"] == "NEW-CODE"
    # change is persisted
    r2 = client.get(f"/locations/{loc_a['id']}")
    assert r2.status_code == 200
    assert r2.json() == body


def test_update_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_unknown_id_404(client):
    r = client.put("/locations/9999", json={"name": "Nope"})
    assert r.status_code == 404
