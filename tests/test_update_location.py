"""PUT /locations/{id} behaviour."""


def test_update_location_name(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"name": "Main Warehouse"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "id": loc_a["id"],
        "code": loc_a["code"],
        "name": "Main Warehouse",
        "active": True,
    }
    # change is persisted
    assert client.get(f"/locations/{loc_a['id']}").json()["name"] == "Main Warehouse"


def test_update_location_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-Z"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == "WH-Z"
    assert body["name"] == loc_a["name"]


def test_update_location_name_and_code(client, loc_a):
    r = client.put(
        f"/locations/{loc_a['id']}", json={"name": "Overflow", "code": "WH-X"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "id": loc_a["id"],
        "code": "WH-X",
        "name": "Overflow",
        "active": True,
    }


def test_update_location_empty_payload_returns_unchanged(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={})
    assert r.status_code == 200, r.text
    assert r.json() == loc_a


def test_update_unknown_location_returns_404(client):
    r = client.put("/locations/999", json={"name": "Nowhere"})
    assert r.status_code == 404


def test_update_location_rejects_invalid_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "bad code!"})
    assert r.status_code == 422


def test_update_location_duplicate_code_returns_409(client, loc_a, loc_b):
    r = client.put(f"/locations/{loc_b['id']}", json={"code": loc_a["code"]})
    assert r.status_code == 409
