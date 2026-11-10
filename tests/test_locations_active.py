"""Tests for location active flag (T026)."""


def test_new_location_is_active_by_default(client, loc_a):
    assert loc_a["active"] is True

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is True


def test_put_can_deactivate_location(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is False
    assert body["code"] == loc_a["code"]  # unchanged
    assert body["name"] == loc_a["name"]  # unchanged

    # Persisted.
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_put_can_reactivate_location(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"active": False})
    assert r.status_code == 200
    r = client.put(f"/locations/{loc_a['id']}", json={"active": True})
    assert r.status_code == 200
    assert r.json()["active"] is True

    r = client.get(f"/locations/{loc_a['id']}")
    assert r.json()["active"] is True


def test_put_active_alongside_other_fields(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}",
        json={"name": "Mothballed", "active": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Mothballed"
    assert body["active"] is False


def test_list_locations_filters_by_active(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"active": False})
    assert r.status_code == 200

    r = client.get("/locations", params={"active": "true"})
    assert r.status_code == 200
    ids = [loc["id"] for loc in r.json()]
    assert ids == [loc_a["id"]]
    assert all(loc["active"] is True for loc in r.json())

    r = client.get("/locations", params={"active": "false"})
    assert r.status_code == 200
    ids = [loc["id"] for loc in r.json()]
    assert ids == [loc_b["id"]]
    assert all(loc["active"] is False for loc in r.json())


def test_list_locations_without_filter_returns_all(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"active": False})
    assert r.status_code == 200

    r = client.get("/locations")
    assert r.status_code == 200
    ids = sorted(loc["id"] for loc in r.json())
    assert ids == sorted([loc_a["id"], loc_b["id"]])
