"""Tests for GET /locations/{id}/stock (T014)."""


def _receive(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={"item_id": item_id, "kind": "receive", "qty": qty, "to_location_id": location_id},
    )
    assert r.status_code == 201, r.text


def _make_item(client, sku):
    r = client.post("/items", json={"sku": sku, "name": sku, "unit_price": 1.0})
    assert r.status_code == 201, r.text
    return r.json()


def test_empty_location_returns_empty_levels(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_levels_listed_and_ordered_by_item_id(client, loc_a, loc_b):
    item1 = _make_item(client, "SKU-1")
    item2 = _make_item(client, "SKU-2")
    item3 = _make_item(client, "SKU-3")
    # Receive out of item-id order to exercise the ORDER BY.
    _receive(client, item3["id"], loc_a["id"], 7)
    _receive(client, item1["id"], loc_a["id"], 3)
    _receive(client, item2["id"], loc_a["id"], 5)
    # Stock at another location must not appear.
    _receive(client, item1["id"], loc_b["id"], 99)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    assert body["levels"] == [
        {"item_id": item1["id"], "location_id": loc_a["id"], "qty": 3},
        {"item_id": item2["id"], "location_id": loc_a["id"], "qty": 5},
        {"item_id": item3["id"], "location_id": loc_a["id"], "qty": 7},
    ]


def test_zero_qty_levels_are_omitted(client, loc_a):
    item1 = _make_item(client, "SKU-A")
    item2 = _make_item(client, "SKU-B")
    _receive(client, item1["id"], loc_a["id"], 4)
    _receive(client, item2["id"], loc_a["id"], 2)
    # Ship all of item2 out so its level is exactly 0.
    r = client.post(
        "/movements",
        json={
            "item_id": item2["id"],
            "kind": "ship",
            "qty": 2,
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 201, r.text

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200
    body = r.json()
    assert body["levels"] == [
        {"item_id": item1["id"], "location_id": loc_a["id"], "qty": 4}
    ]


def test_unknown_location_returns_404(client):
    r = client.get("/locations/9999/stock")
    assert r.status_code == 404


def test_service_function_exists_and_raises_for_unknown_location(tmp_path):
    import pytest

    from inventory.db import connect, init_db
    from inventory.services import stock
    from inventory.services.errors import NotFoundError

    db_path = str(tmp_path / "svc.db")
    init_db(db_path)
    conn = connect(db_path)
    with pytest.raises(NotFoundError) as exc_info:
        stock.get_location_levels(conn, 1234)
    assert exc_info.value.status_code == 404
