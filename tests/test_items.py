"""Item CRUD and listing."""


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_item_returns_201_and_fields(client):
    r = client.post("/items", json={"sku": "A-1", "name": "Alpha", "unit_price": 1.25})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == 1
    assert body["sku"] == "A-1"
    assert body["name"] == "Alpha"
    assert body["unit_price"] == 1.25
    assert body["reorder_point"] == 0
    assert body["active"] is True


def test_create_item_duplicate_sku_conflicts(client, item):
    r = client.post("/items", json={"sku": item["sku"], "name": "Dup"})
    assert r.status_code == 409


def test_create_item_requires_sku_and_name(client):
    assert client.post("/items", json={"name": "x"}).status_code == 422
    assert client.post("/items", json={"sku": "x"}).status_code == 422
    assert client.post("/items", json={"sku": "", "name": "x"}).status_code == 422


def test_get_item(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_missing_item_404(client):
    r = client.get("/items/999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_list_items_ordered_by_id(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["C", "A", "B"]


def test_list_items_limit(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2})
    assert [i["sku"] for i in r.json()] == ["S0", "S1"]


def test_list_items_filter_active(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    assert [i["sku"] for i in client.get("/items", params={"active": "true"}).json()] == ["WIDGET-1"]
    assert [i["sku"] for i in client.get("/items", params={"active": "false"}).json()] == ["INACTIVE"]


def test_update_item_name_and_price(client, item):
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed", "unit_price": 9.99})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["unit_price"] == 9.99
    # untouched fields preserved
    assert r.json()["sku"] == item["sku"]


def test_update_item_deactivate(client, item):
    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.json()["active"] is False


def test_update_missing_item_404(client):
    assert client.put("/items/42", json={"name": "x"}).status_code == 404


def test_delete_item(client, item):
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    # ship everything back out so the item is at zero stock and can be deleted
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get("/movements").json() == []


def test_delete_item_with_stock_conflicts(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert "7" in r.json()["detail"]
    # item still exists
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_detail_mentions_remaining_quantity(client, item, loc_a, loc_b):
    for loc, qty in ((loc_a, 2), (loc_b, 3)):
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    # total across all locations is reported
    assert "5" in r.json()["detail"]


def test_delete_item_after_stock_drained_succeeds(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 409
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 4, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_create_item_description_too_long_422(client):
    r = client.post(
        "/items",
        json={"sku": "LONG-1", "name": "Long", "description": "x" * 2001},
    )
    assert r.status_code == 422


def test_create_item_description_at_limit_ok(client):
    r = client.post(
        "/items",
        json={"sku": "LONG-2", "name": "Long", "description": "x" * 2000},
    )
    assert r.status_code == 201
    assert r.json()["description"] == "x" * 2000


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2001})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json() == item


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "x" * 2000
