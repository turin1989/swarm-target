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
    assert body["reorder_level"] == 0
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
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "not found" in body["error"]["message"]


def test_list_items_ordered_by_id(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["C", "A", "B"]


def test_list_items_limit(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2})
    assert [i["sku"] for i in r.json()["items"]] == ["S0", "S1"]


def test_list_items_filter_active(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    active_page = client.get("/items", params={"active": "true"}).json()
    inactive_page = client.get("/items", params={"active": "false"}).json()
    assert [i["sku"] for i in active_page["items"]] == ["WIDGET-1"]
    assert [i["sku"] for i in inactive_page["items"]] == ["INACTIVE"]


def test_list_items_envelope_shape(client):
    for n in range(3):
        client.post("/items", json={"sku": f"E{n}", "name": f"E{n}"})
    r = client.get("/items")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert isinstance(body["items"], list)
    assert body["total"] == 3
    assert body["limit"] == 100
    assert body["offset"] == 0


def test_list_items_total_ignores_pagination(client):
    for n in range(5):
        client.post("/items", json={"sku": f"P{n}", "name": f"P{n}"})
    body = client.get("/items", params={"limit": 2, "offset": 1}).json()
    assert [i["sku"] for i in body["items"]] == ["P1", "P2"]
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_list_items_total_respects_active_filter(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    body = client.get("/items", params={"active": "true", "limit": 1}).json()
    assert body["total"] == 1
    body_all = client.get("/items", params={"limit": 1}).json()
    assert body_all["total"] == 2
    assert len(body_all["items"]) == 1


def test_list_items_empty_envelope(client):
    body = client.get("/items").json()
    assert body == {"items": [], "total": 0, "limit": 100, "offset": 0}


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
        json={"item_id": item["id"], "kind": "receive", "quantity": 3, "to_location_id": loc_a["id"]},
    )
    client.delete(f"/items/{item['id']}")
    assert client.get("/movements").json() == []


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
    assert len(r.json()["description"]) == 2000


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2001})
    assert r.status_code == 422


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert len(r.json()["description"]) == 2000


def test_create_item_negative_unit_price_422(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "unit_price": -0.01})
    assert r.status_code == 422


def test_create_item_zero_unit_price_ok(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "unit_price": 0})
    assert r.status_code == 201
    assert r.json()["unit_price"] == 0


def test_update_item_negative_unit_price_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": -1})
    assert r.status_code == 422
    # value unchanged
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == item["unit_price"]


def test_update_item_zero_unit_price_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0


def test_create_item_accepts_reorder_level(client):
    r = client.post("/items", json={"sku": "RL-1", "name": "Rl", "reorder_level": 7})
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_create_item_rejects_reorder_point_422(client):
    r = client.post("/items", json={"sku": "RP-1", "name": "Rp", "reorder_point": 7})
    assert r.status_code == 422


def test_update_item_rejects_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 9})
    assert r.status_code == 422
    # value unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == item["reorder_level"]


def test_get_item_exposes_reorder_level_not_reorder_point(client, item):
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 5
    assert "reorder_point" not in body


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_same_shape_as_get_by_id(client, item):
    by_sku = client.get(f"/items/by-sku/{item['sku']}").json()
    by_id = client.get(f"/items/{item['id']}").json()
    assert by_sku == by_id


def test_get_item_by_sku_exact_match_only(client, item):
    # prefixes / near-misses must not match
    assert client.get("/items/by-sku/WIDGET").status_code == 404
    assert client.get("/items/by-sku/widget-1").status_code == 404


def test_get_item_by_sku_unknown_404_detail(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # numeric id lookup still works alongside the by-sku route
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]
