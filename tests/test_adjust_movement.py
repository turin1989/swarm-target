"""Tests for the 'adjust' movement kind (T039)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_adjust_sets_stock_to_absolute_qty(client, item, loc_a):
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="adjust", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 3
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 3}]


def test_adjust_sets_stock_when_no_prior_level(client, item, loc_a):
    # no stock_levels row exists yet: adjust still sets an absolute value
    r = _move(client, item_id=item["id"], kind="adjust", qty=7, to_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 7
    assert s["levels"] == [{"item_id": item["id"], "location_id": loc_a["id"], "qty": 7}]


def test_adjust_is_absolute_not_a_delta(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=5, to_location_id=loc_a["id"])
    # applying the same adjust twice does not accumulate
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 5


def test_adjust_only_affects_target_location(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", qty=4, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="receive", qty=6, to_location_id=loc_b["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=loc_b["id"])
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert [lvl["qty"] for lvl in s["levels"]] == [4, 1]


def test_adjust_requires_to_location(client, item, loc_a):
    r = _move(client, item_id=item["id"], kind="adjust", qty=3)
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "required" in body["error"]["message"]
    # nothing was recorded
    assert client.get("/movements").json() == []


def test_adjust_rejects_from_location(client, item, loc_a, loc_b):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "bad_request"
    assert "from_location_id" in body["error"]["message"]
    # nothing was recorded and stock is untouched
    assert client.get("/movements").json() == []
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 0


def test_adjust_movement_recorded_with_kind_adjust(client, item, loc_a):
    r = _move(
        client,
        item_id=item["id"],
        kind="adjust",
        qty=9,
        to_location_id=loc_a["id"],
        note="cycle count",
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "adjust"
    assert body["qty"] == 9
    assert body["to_location_id"] == loc_a["id"]
    assert body["from_location_id"] is None
    assert body["note"] == "cycle count"

    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "adjust"

    # retrievable by id and filterable by kind
    assert client.get(f"/movements/{body['id']}").json() == body
    filtered = client.get("/movements", params={"kind": "adjust"}).json()
    assert [m["id"] for m in filtered] == [body["id"]]


def test_adjust_unknown_location_404(client, item):
    r = _move(client, item_id=item["id"], kind="adjust", qty=3, to_location_id=123)
    assert r.status_code == 404


def test_adjust_unknown_item_404(client, loc_a):
    r = _move(client, item_id=999, kind="adjust", qty=3, to_location_id=loc_a["id"])
    assert r.status_code == 404


def test_adjust_cannot_be_reversed(client, item, loc_a):
    created = _move(
        client, item_id=item["id"], kind="adjust", qty=4, to_location_id=loc_a["id"]
    ).json()
    r = client.post(f"/movements/{created['id']}/reverse")
    assert r.status_code == 400
    # stock untouched, no extra movement written
    assert client.get(f"/items/{item['id']}/stock").json()["total"] == 4
    assert len(client.get("/movements").json()) == 1


def test_ship_more_than_adjusted_level_is_409(client, item, loc_a):
    # the insufficient-stock guard (T005) sees the absolute level set by adjust
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])
    _move(client, item_id=item["id"], kind="adjust", qty=2, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=3, from_location_id=loc_a["id"])
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]


def test_ship_within_adjusted_level_succeeds(client, item, loc_a):
    _move(client, item_id=item["id"], kind="adjust", qty=4, to_location_id=loc_a["id"])
    r = _move(client, item_id=item["id"], kind="ship", qty=4, from_location_id=loc_a["id"])
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 0


def test_transfer_after_adjust_credits_destination(client, item, loc_a, loc_b):
    # transfer must debit the source and credit the destination of the adjusted stock
    _move(client, item_id=item["id"], kind="adjust", qty=6, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 6
    levels = {lv["location_id"]: lv["qty"] for lv in s["levels"]}
    assert levels == {loc_a["id"]: 2, loc_b["id"]: 4}


def test_transfer_more_than_adjusted_level_is_409(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="adjust", qty=1, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 409
    assert "insufficient" in r.json()["error"]["message"]
