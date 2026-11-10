"""DELETE /locations/{id} behaviour."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_delete_location_returns_204_and_location_is_gone(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert r.content == b""
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert loc_a["id"] not in [loc["id"] for loc in client.get("/locations").json()]


def test_delete_location_with_stock_returns_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409
    # location still exists
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_allowed_when_stock_level_is_zero(client, item, loc_a):
    # create a stock_levels row, then drain it back to zero
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="ship", quantity=5, from_location_id=loc_a["id"])

    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/999")
    assert r.status_code == 404
