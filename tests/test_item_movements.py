"""GET /items/{id}/movements (T032): per-item movement history."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _seed(client, item, loc_a, loc_b):
    """Create a second item and movements for both; return the second item."""
    item2 = client.post(
        "/items",
        json={"sku": "GADGET-1", "name": "Gadget", "unit_price": 1.0, "reorder_level": 2},
    ).json()
    _move(client, item_id=item["id"], kind="receive", qty=10, to_location_id=loc_a["id"])  # id 1
    _move(client, item_id=item2["id"], kind="receive", qty=8, to_location_id=loc_a["id"])  # id 2
    _move(client, item_id=item["id"], kind="ship", qty=2, from_location_id=loc_a["id"])  # id 3
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        qty=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )  # id 4
    return item2


def test_item_movements_only_for_that_item_ordered_by_id(client, item, loc_a, loc_b):
    item2 = _seed(client, item, loc_a, loc_b)

    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    body = r.json()
    assert [m["id"] for m in body] == [1, 3, 4]
    assert all(m["item_id"] == item["id"] for m in body)
    assert [m["kind"] for m in body] == ["receive", "ship", "transfer"]

    r2 = client.get(f"/items/{item2['id']}/movements")
    assert r2.status_code == 200
    assert [m["id"] for m in r2.json()] == [2]


def test_item_movements_shape_matches_movement_model(client, item, loc_a, loc_b):
    _seed(client, item, loc_a, loc_b)
    single = client.get("/movements/1").json()
    listed = client.get(f"/items/{item['id']}/movements").json()[0]
    assert listed == single


def test_item_movements_empty_for_item_without_history(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_unknown_item_404(client):
    r = client.get("/items/9999/movements")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "item 9999 not found"


def test_item_movements_pagination(client, item, loc_a, loc_b):
    _seed(client, item, loc_a, loc_b)
    for _ in range(3):
        _move(client, item_id=item["id"], kind="receive", qty=1, to_location_id=loc_a["id"])

    all_ids = [m["id"] for m in client.get(f"/items/{item['id']}/movements").json()]
    assert len(all_ids) == 6

    page1 = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 0}).json()
    page2 = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 2}).json()
    page3 = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 4}).json()
    assert [m["id"] for m in page1] == all_ids[:2]
    assert [m["id"] for m in page2] == all_ids[2:4]
    assert [m["id"] for m in page3] == all_ids[4:]


def test_item_movements_offset_past_end_returns_empty(client, item, loc_a, loc_b):
    _seed(client, item, loc_a, loc_b)
    r = client.get(f"/items/{item['id']}/movements", params={"offset": 50})
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_invalid_pagination_422(client, item):
    assert client.get(f"/items/{item['id']}/movements", params={"limit": 0}).status_code == 422
    assert client.get(f"/items/{item['id']}/movements", params={"limit": 501}).status_code == 422
    assert client.get(f"/items/{item['id']}/movements", params={"offset": -1}).status_code == 422
