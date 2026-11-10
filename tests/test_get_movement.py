"""GET /movements/{id} (T015)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_get_movement_matches_post_response(client, item, loc_a, loc_b):
    created = _move(
        client,
        item_id=item["id"],
        kind="receive",
        qty=10,
        to_location_id=loc_a["id"],
        note="initial",
    ).json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_transfer_shape(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    created = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
        note="rebalance",
    ).json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body == created
    assert body["kind"] == "transfer"
    assert body["qty"] == 2
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] == loc_b["id"]
    assert body["note"] == "rebalance"


def test_get_movement_unknown_id_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "movement 999 not found"
