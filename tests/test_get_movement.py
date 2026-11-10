"""GET /movements/{id}."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_get_movement_returns_same_shape_as_post(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"]
    ).json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_after_transfer(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    created = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    ).json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_unknown_id_returns_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    # the endpoint raises HTTPException(detail="movement 999 not found"); the
    # app-wide handler renders that detail in the uniform error shape
    body = r.json()
    assert body == {"error": {"code": "not_found", "message": "movement 999 not found"}}
