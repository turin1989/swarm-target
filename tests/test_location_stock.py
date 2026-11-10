"""Tests for GET /locations/{id}/stock (T014)."""


def _receive(client, item_id, location_id, qty):
    r = client.post(
        "/movements",
        json={
            "item_id": item_id,
            "kind": "receive",
            "quantity": qty,
            "to_location_id": location_id,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_location_stock_lists_levels_ordered_by_item_id(client, loc_a):
    # Create items so that insertion into stock happens out of item-id order.
    ids = []
    for sku in ("S-1", "S-2", "S-3"):
        r = client.post("/items", json={"sku": sku, "name": sku, "unit_price": 1.0})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    # Receive in reverse item order to prove the response sorts by item_id.
    _receive(client, ids[2], loc_a["id"], 7)
    _receive(client, ids[0], loc_a["id"], 3)
    _receive(client, ids[1], loc_a["id"], 5)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["location_id"] == loc_a["id"]
    assert body["levels"] == [
        {"item_id": ids[0], "location_id": loc_a["id"], "quantity": 3},
        {"item_id": ids[1], "location_id": loc_a["id"], "quantity": 5},
        {"item_id": ids[2], "location_id": loc_a["id"], "quantity": 7},
    ]


def test_location_stock_empty_location(client, loc_a):
    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json() == {"location_id": loc_a["id"], "levels": []}


def test_location_stock_omits_zero_quantity_levels(client, item, loc_a, loc_b):
    _receive(client, item["id"], loc_a["id"], 4)
    # Transfer everything away so the loc_a level exists but is zero.
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "transfer",
            "quantity": 4,
            "from_location_id": loc_a["id"],
            "to_location_id": loc_b["id"],
        },
    )
    assert r.status_code == 201, r.text

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json()["levels"] == []

    r = client.get(f"/locations/{loc_b['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json()["levels"] == [
        {"item_id": item["id"], "location_id": loc_b["id"], "quantity": 4}
    ]


def test_location_stock_unknown_location_404(client):
    r = client.get("/locations/9999/stock")
    assert r.status_code == 404, r.text
    body = r.json()
    assert body["error"]["code"] == "not_found"


def test_location_stock_only_includes_requested_location(client, item, loc_a, loc_b):
    _receive(client, item["id"], loc_a["id"], 2)
    _receive(client, item["id"], loc_b["id"], 9)

    r = client.get(f"/locations/{loc_a['id']}/stock")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "location_id": loc_a["id"],
        "levels": [{"item_id": item["id"], "location_id": loc_a["id"], "quantity": 2}],
    }


def test_get_location_levels_service(client, item, loc_a):
    """stock.get_location_levels is callable directly against the DB."""
    import pytest

    from inventory.db import connect
    from inventory.services import stock
    from inventory.services.errors import NotFoundError

    _receive(client, item["id"], loc_a["id"], 6)
    conn = connect(client.app.state.db_path)
    try:
        levels = stock.get_location_levels(conn, loc_a["id"])
        assert [(lvl.item_id, lvl.quantity) for lvl in levels] == [(item["id"], 6)]

        with pytest.raises(NotFoundError):
            stock.get_location_levels(conn, 123456)
    finally:
        conn.close()
