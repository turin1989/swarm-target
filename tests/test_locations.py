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
