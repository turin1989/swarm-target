"""T005: shipping/transferring more than is on hand is rejected with 409."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _detail(response) -> str:
    """The error detail message from the uniform error response shape."""
    body = response.json()
    assert body["error"]["code"] == "conflict"
    return body["error"]["message"]


def _receive(client, item, loc, qty):
    r = _move(client, item_id=item["id"], kind="receive", quantity=qty, to_location_id=loc["id"])
    assert r.status_code == 201, r.text


def test_ship_more_than_on_hand_is_409(client, item, loc_a):
    _receive(client, item, loc_a, 5)
    r = _move(client, item_id=item["id"], kind="ship", quantity=6, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in _detail(r).lower()


def test_ship_from_empty_location_is_409(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="ship", quantity=1, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in _detail(r).lower()


def test_transfer_more_than_source_stock_is_409(client, item, loc_a, loc_b):
    _receive(client, item, loc_a, 3)
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    assert "insufficient" in _detail(r).lower()


def test_rejected_ship_writes_no_movement_and_leaves_stock_unchanged(client, item, loc_a):
    _receive(client, item, loc_a, 5)
    before_movements = client.get("/movements").json()

    r = _move(client, item_id=item["id"], kind="ship", quantity=99, from_location_id=loc_a["id"])
    assert r.status_code == 409

    assert client.get("/movements").json() == before_movements
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}]


def test_rejected_transfer_writes_no_movement_and_leaves_stock_unchanged(
    client, item, loc_a, loc_b
):
    _receive(client, item, loc_a, 2)
    before_movements = client.get("/movements").json()

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409

    assert client.get("/movements").json() == before_movements
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 2
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 2}]


def test_ship_exact_on_hand_is_allowed(client, item, loc_a):
    _receive(client, item, loc_a, 5)
    r = _move(client, item_id=item["id"], kind="ship", quantity=5, from_location_id=loc_a["id"])
    assert r.status_code == 201
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_transfer_exact_on_hand_is_allowed(client, item, loc_a, loc_b):
    _receive(client, item, loc_a, 4)
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 4
    assert {(lv["location_id"], lv["quantity"]) for lv in s["levels"] if lv["quantity"]} == {
        (loc_b["id"], 4)
    }
