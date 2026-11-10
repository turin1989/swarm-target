"""Tests for PUT /locations/{id} (T012)."""


def test_update_location_name_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Renamed Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == loc_a["id"]
    assert body["name"] == "Renamed Warehouse"
    assert body["code"] == loc_a["code"]  # unchanged


def test_update_location_code_only(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-A2"
    assert body["name"] == loc_a["name"]  # unchanged


def test_update_location_both_fields(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "New Name", "code": "NEW-CODE"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "New Name"
    assert body["code"] == "NEW-CODE"

    # Change is persisted.
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json() == body


def test_update_location_empty_payload_is_noop(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_location_unknown_id_returns_404(client):
    r = client.put("/locations/9999", json={"name": "Ghost"})
    assert r.status_code == 404


def test_update_location_does_not_affect_others(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Only A"})
    assert r.status_code == 200

    r = client.get(f"/locations/{loc_b['id']}")
    assert r.status_code == 200
    assert r.json() == loc_b
