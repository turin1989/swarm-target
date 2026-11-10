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


def _create_sortable_items(client):
    # ids 1..3; names and skus deliberately out of id order
    client.post("/items", json={"sku": "SKU-C", "name": "Banana"})
    client.post("/items", json={"sku": "SKU-A", "name": "Cherry"})
    client.post("/items", json={"sku": "SKU-B", "name": "Apple"})


def test_list_items_sort_default_is_id(client):
    _create_sortable_items(client)
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_id_explicit(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_name_ascending(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Apple", "Banana", "Cherry"]


def test_list_items_sort_by_sku_ascending(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["SKU-A", "SKU-B", "SKU-C"]


def test_list_items_sort_by_name_descending(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Cherry", "Banana", "Apple"]


def test_list_items_sort_by_sku_descending(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "-sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["SKU-C", "SKU-B", "SKU-A"]


def test_list_items_sort_by_id_descending(client):
    _create_sortable_items(client)
    r = client.get("/items", params={"sort": "-id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [3, 2, 1]


def test_list_items_sort_invalid_value_422(client):
    _create_sortable_items(client)
    for bad in ["price", "unit_price", "-unknown", "ID", "name;DROP TABLE items", ""]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, f"sort={bad!r} should be rejected"


def test_list_items_sort_combines_with_pagination(client):
    _create_sortable_items(client)
    body = client.get("/items", params={"sort": "name", "limit": 2, "offset": 1}).json()
    assert [i["name"] for i in body["items"]] == ["Banana", "Cherry"]
    assert body["total"] == 3


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


def test_delete_missing_item_404(client):
    r = client.delete("/items/999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "item 999 not found"


def test_delete_item_twice_second_404(client, item):
    first = client.delete(f"/items/{item['id']}")
    assert first.status_code == 204
    second = client.delete(f"/items/{item['id']}")
    assert second.status_code == 404
    body = second.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == f"item {item['id']} not found"


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 3, "to_location_id": loc_a["id"]},
    )
    # drain stock to zero so the delete is allowed, then verify cascade
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 3, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get("/movements").json() == []


def test_delete_item_with_stock_409(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    # detail mentions the remaining quantity
    assert "7" in body["error"]["message"]
    # item is untouched
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_409_sums_across_locations(client, item, loc_a, loc_b):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 2, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 3, "to_location_id": loc_b["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert "5" in r.json()["error"]["message"]


def test_delete_item_after_stock_drained_to_zero_204(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 4, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 4, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_delete_item_never_stocked_still_deletes(client, item):
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


def test_update_item_reorder_level_persists_and_is_returned(client, item):
    # T004: PUT must not silently ignore the reorder field
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 12})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 12
    # persisted, not just echoed
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 12


def test_update_item_reorder_level_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_level": 3, "name": "Renamed", "unit_price": 4.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_level"] == 3
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 4.5
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_level"] == 3
    assert stored["name"] == "Renamed"
    assert stored["unit_price"] == 4.5


def test_update_item_omitting_reorder_level_leaves_value_untouched(client, item):
    client.put(f"/items/{item['id']}", json={"reorder_level": 12})
    r = client.put(f"/items/{item['id']}", json={"name": "NoReorderChange"})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 12
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 12


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

def test_create_item_rejects_negative_reorder_point_422(client):
    r = client.post("/items", json={"sku": "NRP-1", "name": "Nrp", "reorder_point": -1})
    assert r.status_code == 422


def test_update_item_rejects_negative_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -3})
    assert r.status_code == 422
    # value unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == item["reorder_level"]


def test_create_item_rejects_negative_reorder_level_422(client):
    r = client.post("/items", json={"sku": "NRL-1", "name": "Nrl", "reorder_level": -1})
    assert r.status_code == 422


def test_update_item_rejects_negative_reorder_level_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": -5})
    assert r.status_code == 422
    # value unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == item["reorder_level"]


def test_update_item_zero_reorder_level_not_rejected(client, item):
    # zero is a valid (non-negative) value, so validation must not return 422
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 0})
    assert r.status_code == 200


# --- X-Total-Count header (T037) ---------------------------------------------


def test_list_items_sets_x_total_count_header(client):
    for n in range(3):
        client.post("/items", json={"sku": f"H{n}", "name": f"H{n}"})
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"


def test_x_total_count_ignores_limit_and_offset(client):
    for n in range(5):
        client.post("/items", json={"sku": f"HP{n}", "name": f"HP{n}"})
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_x_total_count_respects_active_filter(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    r_active = client.get("/items", params={"active": "true", "limit": 1})
    assert r_active.headers["X-Total-Count"] == "1"
    r_inactive = client.get("/items", params={"active": "false"})
    assert r_inactive.headers["X-Total-Count"] == "1"
    r_all = client.get("/items", params={"limit": 1})
    assert r_all.headers["X-Total-Count"] == "2"


def test_x_total_count_zero_when_no_items(client):
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "0"


def test_x_total_count_when_offset_beyond_results(client):
    for n in range(3):
        client.post("/items", json={"sku": f"OB{n}", "name": f"OB{n}"})
    r = client.get("/items", params={"offset": 10})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.headers["X-Total-Count"] == "3"
