"""Tests for DELETE /locations/{id} (T013)."""


def _receive(client, item_id, loc_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": qty, "to_location_id": loc_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _ship(client, item_id, loc_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "ship", "qty": qty, "from_location_id": loc_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_delete_empty_location_returns_204_and_removes_it(client, loc_a):
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404
    assert loc_a["id"] not in [loc["id"] for loc in client.get("/locations").json()]


def test_delete_location_with_stock_returns_409(client, item, loc_a):
    _receive(client, item["id"], loc_a["id"], 7)
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 409
    # location still exists
    assert client.get(f"/locations/{loc_a['id']}").status_code == 200


def test_delete_location_with_zero_qty_stock_row_succeeds(client, item, loc_a):
    # create a stock_levels row, then drain it to qty == 0
    _receive(client, item["id"], loc_a["id"], 5)
    _ship(client, item["id"], loc_a["id"], 5)
    r = client.delete(f"/locations/{loc_a['id']}")
    assert r.status_code == 204
    assert client.get(f"/locations/{loc_a['id']}").status_code == 404


def test_delete_unknown_location_returns_404(client):
    r = client.delete("/locations/99999")
    assert r.status_code == 404
