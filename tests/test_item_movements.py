"""GET /items/{id}/movements — per-item movement history (T032)."""

import pytest


def _move(client, **kw):
    r = client.post("/movements", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def item2(client):
    r = client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def history(client, item, item2, loc_a, loc_b):
    """Interleaved movements for two items; ids are sequential from 1."""
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])  # 1
    _move(client, item_id=item2["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])  # 2
    _move(client, item_id=item["id"], kind="ship", quantity=2, from_location_id=loc_a["id"])  # 3
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=3,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )  # 4
    _move(client, item_id=item2["id"], kind="ship", quantity=1, from_location_id=loc_a["id"])  # 5
    _move(client, item_id=item["id"], kind="ship", quantity=1, from_location_id=loc_a["id"])  # 6


def test_item_movements_ordered_by_id(client, item, history):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    movements = r.json()
    assert [m["id"] for m in movements] == [1, 3, 4, 6]
    assert all(m["item_id"] == item["id"] for m in movements)
    assert [m["kind"] for m in movements] == ["receive", "ship", "transfer", "ship"]


def test_item_movements_only_include_that_item(client, item, item2, history):
    r = client.get(f"/items/{item2['id']}/movements")
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [2, 5]
    assert all(m["item_id"] == item2["id"] for m in r.json())


def test_item_movements_limit(client, item, history):
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [1, 3]


def test_item_movements_offset(client, item, history):
    r = client.get(f"/items/{item['id']}/movements", params={"offset": 2})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [4, 6]


def test_item_movements_limit_and_offset(client, item, history):
    r = client.get(f"/items/{item['id']}/movements", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()] == [3, 4]


def test_item_movements_empty_for_item_without_history(client, item):
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert r.json() == []


def test_item_movements_unknown_item_404(client, history):
    r = client.get("/items/999/movements")
    assert r.status_code == 404


def test_item_movements_invalid_pagination_422(client, item):
    assert client.get(f"/items/{item['id']}/movements", params={"limit": 0}).status_code == 422
    assert client.get(f"/items/{item['id']}/movements", params={"offset": -1}).status_code == 422


def test_item_movements_uses_stock_list_movements(client, item, loc_a, monkeypatch):
    """The endpoint must be implemented via stock.list_movements(conn, item_id=...)."""
    from inventory.services import stock

    _move(client, item_id=item["id"], kind="receive", quantity=1, to_location_id=loc_a["id"])

    calls = []
    original = stock.list_movements

    def spy(conn, *args, **kwargs):
        calls.append(kwargs)
        return original(conn, *args, **kwargs)

    monkeypatch.setattr("inventory.api.stock.list_movements", spy)
    r = client.get(f"/items/{item['id']}/movements")
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0].get("item_id") == item["id"]
