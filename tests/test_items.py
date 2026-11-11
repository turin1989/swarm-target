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


def test_create_item_negative_reorder_point_422(client):
    r = client.post("/items", json={"sku": "NEG", "name": "Neg", "reorder_point": -1})
    assert r.status_code == 422


def test_create_item_zero_reorder_point_allowed(client):
    r = client.post("/items", json={"sku": "ZERO-RP", "name": "Zero", "reorder_point": 0})
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_negative_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -5})
    assert r.status_code == 422
    # stored value unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == item["reorder_point"]


def test_create_item_negative_unit_price_rejected(client):
    r = client.post("/items", json={"sku": "NEG", "name": "Neg", "unit_price": -0.01})
    assert r.status_code == 422


def test_create_item_zero_unit_price_accepted(client):
    r = client.post("/items", json={"sku": "ZERO", "name": "Zero", "unit_price": 0})
    assert r.status_code == 201
    assert r.json()["unit_price"] == 0


def test_update_item_negative_unit_price_rejected(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": -5})
    assert r.status_code == 422
    # stored value unchanged
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == item["unit_price"]


def test_update_item_zero_unit_price_accepted(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == 0


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


def test_list_items_filter_sku_exact_match(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Widget 2"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body] == ["WIDGET-1"]
    assert body[0] == item


def test_list_items_filter_sku_is_exact_not_partial(client, item):
    client.post("/items", json={"sku": "WIDGET-10", "name": "Widget 10"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]


def test_list_items_filter_sku_unknown_returns_empty_list(client, item):
    r = client.get("/items", params={"sku": "NO-SUCH-SKU"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_combines_with_active(client, item):
    # a second, inactive item sharing nothing with WIDGET-1
    client.post("/items", json={"sku": "WIDGET-2", "name": "Widget 2"})
    client.put("/items/2", json={"active": False})

    # active item matches sku + active=true
    r = client.get("/items", params={"sku": "WIDGET-1", "active": "true"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]

    # active item does not match active=false
    r = client.get("/items", params={"sku": "WIDGET-1", "active": "false"})
    assert r.status_code == 200
    assert r.json() == []

    # inactive item matches sku + active=false
    r = client.get("/items", params={"sku": "WIDGET-2", "active": "false"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-2"]


def test_update_item_name_and_price(client, item):
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed", "unit_price": 9.99})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["unit_price"] == 9.99
    # untouched fields preserved
    assert r.json()["sku"] == item["sku"]


def test_update_item_reorder_point(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # value is persisted, not just echoed back
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12


def test_update_item_reorder_point_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_point": 7, "name": "Renamed", "unit_price": 3.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_point"] == 7
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 3.5
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_point"] == 7
    assert stored["name"] == "Renamed"
    assert stored["unit_price"] == 3.5


def test_update_item_omitting_reorder_point_preserves_value(client, item):
    client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    r = client.put(f"/items/{item['id']}", json={"name": "Other"})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12


def test_update_item_deactivate(client, item):
    r = client.put(f"/items/{item['id']}", json={"active": False})
    assert r.json()["active"] is False


def test_update_missing_item_404(client):
    assert client.put("/items/42", json={"name": "x"}).status_code == 404


def test_delete_item(client, item):
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_delete_missing_item_404_with_detail(client):
    r = client.delete("/items/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "item 999 not found"


def test_delete_item_twice_second_returns_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    assert r.json()["detail"] == f"item {item['id']} not found"


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    client.delete(f"/items/{item['id']}")
    assert client.get("/movements").json() == []


# --- GET /items/by-sku/{sku} ---------------------------------------------------


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_same_shape_as_get_by_id(client, item):
    by_sku = client.get(f"/items/by-sku/{item['sku']}").json()
    by_id = client.get(f"/items/{item['id']}").json()
    assert by_sku == by_id


def test_get_item_by_sku_exact_match_not_partial(client, item):
    client.post("/items", json={"sku": "WIDGET-10", "name": "Widget 10"})
    r = client.get("/items/by-sku/WIDGET-1")
    assert r.status_code == 200
    assert r.json()["sku"] == "WIDGET-1"


def test_get_item_by_sku_unknown_404_with_detail(client):
    r = client.get("/items/by-sku/NO-SUCH-SKU")
    assert r.status_code == 404
    assert r.json()["detail"] == "sku NO-SUCH-SKU not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # numeric path still resolves to the id-based route
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json() == item
    # and a missing numeric id still reports the item-id message
    r = client.get("/items/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "item 999 not found"
