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


def test_create_item_sku_is_trimmed_and_uppercased(client):
    r = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r.status_code == 201
    assert r.json()["sku"] == "ABC-1"
    # stored normalised, retrievable by normalised sku
    assert client.get("/items/by-sku/ABC-1").status_code == 200


def test_create_item_duplicate_sku_after_normalisation_conflicts(client):
    assert client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"}).status_code == 201
    assert client.post("/items", json={"sku": "ABC-1", "name": "Dup"}).status_code == 409
    assert client.post("/items", json={"sku": "abc-1", "name": "Dup"}).status_code == 409


def test_create_item_whitespace_only_sku_422(client):
    r = client.post("/items", json={"sku": "   ", "name": "Blank"})
    assert r.status_code == 422


def test_get_item(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_missing_item_404(client):
    r = client.get("/items/999")
    assert r.status_code == 404
    assert "not found" in r.json()["error"]["message"]
    assert r.json()["error"]["code"] == "not_found"


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
    assert active_page["total"] == 1
    assert inactive_page["total"] == 1


def test_list_items_envelope_shape(client):
    for n in range(3):
        client.post("/items", json={"sku": f"E{n}", "name": f"E{n}"})
    r = client.get("/items")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 3
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert len(body["items"]) == 3


def test_list_items_total_ignores_pagination(client):
    for n in range(5):
        client.post("/items", json={"sku": f"P{n}", "name": f"P{n}"})
    body = client.get("/items", params={"limit": 2, "offset": 1}).json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [i["sku"] for i in body["items"]] == ["P1", "P2"]


def test_list_items_empty_page(client):
    body = client.get("/items").json()
    assert body == {"items": [], "total": 0, "limit": 100, "offset": 0}


def test_list_items_x_total_count_header(client):
    for n in range(3):
        client.post("/items", json={"sku": f"H{n}", "name": f"H{n}"})
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"


def test_list_items_x_total_count_ignores_pagination(client):
    for n in range(5):
        client.post("/items", json={"sku": f"HP{n}", "name": f"HP{n}"})
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert len(r.json()["items"]) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_x_total_count_respects_active_filter(client):
    for n in range(4):
        client.post("/items", json={"sku": f"HF{n}", "name": f"HF{n}"})
    client.put("/items/1", json={"active": False})
    r_active = client.get("/items", params={"active": "true", "limit": 1})
    r_inactive = client.get("/items", params={"active": "false"})
    assert r_active.headers["X-Total-Count"] == "3"
    assert r_inactive.headers["X-Total-Count"] == "1"


def test_list_items_x_total_count_empty(client):
    r = client.get("/items")
    assert r.headers["X-Total-Count"] == "0"


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


def test_delete_missing_item_404_with_detail(client):
    r = client.delete("/items/999")
    assert r.status_code == 404
    assert r.json()["error"] == {"code": "not_found", "message": "item 999 not found"}


def test_delete_item_twice_second_is_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found",
        "message": f"item {item['id']} not found",
    }


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    # stock must be zero before the item can be deleted
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    client.delete(f"/items/{item['id']}")
    assert client.get("/movements").json() == []


def test_delete_item_with_stock_409(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    # error message mentions the remaining quantity
    assert r.json()["error"]["code"] == "conflict"
    assert "7" in r.json()["error"]["message"]
    # item is untouched
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_409_detail_sums_locations(client, item, loc_a, loc_b):
    for loc, qty in [(loc_a, 2), (loc_b, 3)]:
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert "5" in r.json()["error"]["message"]


def test_delete_item_after_stock_shipped_out_succeeds(client, item, loc_a):
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


def test_delete_item_zero_stock_deletes_as_before(client, item):
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_create_item_description_too_long_422(client):
    r = client.post(
        "/items", json={"sku": "LONG-1", "name": "Long", "description": "x" * 2001}
    )
    assert r.status_code == 422


def test_create_item_description_at_limit_ok(client):
    r = client.post(
        "/items", json={"sku": "LONG-2", "name": "Long", "description": "x" * 2000}
    )
    assert r.status_code == 201
    assert r.json()["description"] == "x" * 2000


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2001})
    assert r.status_code == 422


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "x" * 2000


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
    # item unchanged
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == item["unit_price"]


def test_update_item_zero_unit_price_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_same_shape_as_get_by_id(client, item):
    by_sku = client.get(f"/items/by-sku/{item['sku']}").json()
    by_id = client.get(f"/items/{item['id']}").json()
    assert by_sku == by_id


def test_get_item_by_sku_unknown_404(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    assert r.json()["error"]["message"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]


# --- PUT /items/{id} reorder_point (T004) --------------------------------------


def test_update_item_reorder_point_persists_and_returns(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # persisted, not just echoed
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12


def test_update_item_reorder_point_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_point": 7, "name": "Renamed", "unit_price": 3.75},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_point"] == 7
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 3.75
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_point"] == 7
    assert stored["name"] == "Renamed"
    assert stored["unit_price"] == 3.75


def test_update_item_omitting_reorder_point_keeps_stored_value(client, item):
    assert item["reorder_point"] == 5
    r = client.put(f"/items/{item['id']}", json={"name": "No RP change"})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 5


# --- reorder_point validation (T009) --------------------------------------------


def test_create_item_negative_reorder_point_returns_422(client):
    r = client.post(
        "/items", json={"sku": "NEG-1", "name": "Negative", "reorder_point": -1}
    )
    assert r.status_code == 422


def test_create_item_zero_reorder_point_is_allowed(client):
    r = client.post(
        "/items", json={"sku": "ZERO-1", "name": "Zero", "reorder_point": 0}
    )
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_negative_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -3})
    assert r.status_code == 422
    # stored value unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 5


def test_update_item_zero_reorder_point_is_allowed(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 0})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 0
