"""Reversing movements via POST /movements/{id}/reverse (T045)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_reverse_receive_creates_ship(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    original = r.json()

    rev = client.post(f"/movements/{original['id']}/reverse")
    assert rev.status_code == 201, rev.text
    body = rev.json()
    assert body["id"] != original["id"]
    assert body["kind"] == "ship"
    assert body["item_id"] == item["id"]
    assert body["qty"] == 10
    assert body["from_location_id"] == loc_a["id"]
    assert body["to_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    # stock is back to zero
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_reverse_ship_creates_receive(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_a["id"])
    original = r.json()

    rev = client.post(f"/movements/{original['id']}/reverse")
    assert rev.status_code == 201, rev.text
    body = rev.json()
    assert body["kind"] == "receive"
    assert body["qty"] == 3
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == f"reversal of {original['id']}"

    # stock is restored
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10


def test_reverse_transfer_swaps_locations(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    original = r.json()

    rev = client.post(f"/movements/{original['id']}/reverse")
    assert rev.status_code == 201, rev.text
    body = rev.json()
    assert body["kind"] == "transfer"
    assert body["qty"] == 2
    assert body["from_location_id"] == loc_b["id"]
    assert body["to_location_id"] == loc_a["id"]
    assert body["note"] == f"reversal of {original['id']}"

    # stock is back to all at loc_a
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels.get(loc_a["id"]) == 5
    assert levels.get(loc_b["id"], 0) == 0


def test_reversal_is_persisted_as_movement(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    original = r.json()
    rev = client.post(f"/movements/{original['id']}/reverse").json()

    movements = client.get("/movements").json()
    assert [m["id"] for m in movements] == [original["id"], rev["id"]]
    assert movements[1]["note"] == f"reversal of {original['id']}"


def test_reverse_unknown_movement_404(client):
    r = client.post("/movements/999/reverse")
    assert r.status_code == 404


def test_reverse_receive_after_stock_moved_409(client, item, loc_a):
    # receive 2 then ship both; reversing the receive would go negative
    r = _move(client, item_id=item["id"], kind="receive", qty=2, to_location_id=loc_a["id"])
    original = r.json()
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])

    rev = client.post(f"/movements/{original['id']}/reverse")
    assert rev.status_code == 409
    assert "insufficient" in rev.json()["error"]["message"]


def test_transfer_moves_stock_between_locations(client, item, loc_a, loc_b):
    # supporting behaviour for transfer reversal: transfers actually move stock
    _move(client, item_id=item["id"], kind="receive", qty=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    s = client.get(f"/items/{item['id']}/stock").json()
    levels = {lvl["location_id"]: lvl["qty"] for lvl in s["levels"]}
    assert levels[loc_a["id"]] == 3
    assert levels[loc_b["id"]] == 2
