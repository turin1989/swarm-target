"""T005: shipping/transferring more than is on hand is rejected with 409."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _stock(client, item_id):
    return client.get(f"/items/{item_id}/stock").json()


def test_ship_more_than_on_hand_409(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", quantity=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]


def test_ship_from_empty_location_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", quantity=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]


def test_ship_rejection_writes_no_movement_and_keeps_stock(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", quantity=100, from_location_id=loc_a["id"])
    assert r.status_code == 409

    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"

    s = _stock(client, item["id"])
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}]


def test_transfer_more_than_source_stock_409(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "insufficient" in body["error"]["message"]


def test_transfer_rejection_writes_no_movement_and_keeps_stock(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=3, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=10,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409

    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"

    s = _stock(client, item["id"])
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 3}]


def test_transfer_checks_source_not_destination(client, item, loc_a, loc_b):
    # Stock sits at loc_b; transferring *from* loc_a must still be rejected.
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_b["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=1,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]


def test_ship_exact_stock_ok(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", quantity=5, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert _stock(client, item["id"])["total"] == 0


def test_transfer_exact_stock_ok_and_moves_stock(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=5,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201
    s = _stock(client, item["id"])
    assert s["total"] == 5
    assert {(lvl["location_id"], lvl["quantity"]) for lvl in s["levels"]} >= {(loc_b["id"], 5)}
