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


def test_create_item_description_too_long_422(client):
    r = client.post("/items", json={"sku": "LONG", "name": "Long", "description": "x" * 2001})
    assert r.status_code == 422


def test_create_item_description_at_limit_ok(client):
    r = client.post("/items", json={"sku": "LIMIT", "name": "Limit", "description": "x" * 2000})
    assert r.status_code == 201
    assert r.json()["description"] == "x" * 2000


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2001})
    assert r.status_code == 422


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "x" * 2000


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


def test_list_items_sort_by_name(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()] == ["Alpha", "Bravo", "Charlie"]


def test_list_items_sort_by_sku(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["A", "B", "C"]


def test_list_items_sort_by_id_explicit(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["C", "A", "B"]


def test_list_items_default_sort_is_id(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()] == [1, 2, 3]


def test_list_items_sort_descending(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()] == ["Charlie", "Bravo", "Alpha"]
    r = client.get("/items", params={"sort": "-id"})
    assert [i["id"] for i in r.json()] == [3, 2, 1]
    r = client.get("/items", params={"sort": "-sku"})
    assert [i["sku"] for i in r.json()] == ["S3", "S2", "S1"]


def test_list_items_invalid_sort_422(client):
    for bad in ["price", "unit_price", "-price", "NAME", "name,sku", "--name", ""]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, f"sort={bad!r} should be rejected"


def test_list_items_sort_combined_with_filter_and_limit(client, item):
    client.post("/items", json={"sku": "AAA", "name": "Aardvark"})
    client.post("/items", json={"sku": "ZZZ", "name": "Zebra"})
    client.put("/items/3", json={"active": False})
    r = client.get("/items", params={"sort": "-name", "active": "true", "limit": 1})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]


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


def test_list_items_filter_by_sku_exact_match(client, item):
    client.post("/items", json={"sku": "WIDGET-10", "name": "Widget Ten"})
    client.post("/items", json={"sku": "OTHER-1", "name": "Other"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body] == ["WIDGET-1"]
    assert body[0] == item


def test_list_items_filter_by_unknown_sku_returns_empty_200(client, item):
    r = client.get("/items", params={"sku": "NOPE-99"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_is_not_substring_match(client, item):
    # "WIDGET" is a prefix of the existing sku but not an exact match
    r = client.get("/items", params={"sku": "WIDGET"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_combines_with_active(client, item):
    client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    client.put(f"/items/{item['id']}", json={"active": False})
    # sku matches but item is inactive -> excluded when active=true
    r = client.get("/items", params={"sku": "WIDGET-1", "active": "true"})
    assert r.status_code == 200
    assert r.json() == []
    # sku matches and item is inactive -> included when active=false
    r = client.get("/items", params={"sku": "WIDGET-1", "active": "false"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]
    # other active item is not returned for a different sku filter
    r = client.get("/items", params={"sku": "GADGET-1", "active": "true"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["GADGET-1"]


def test_update_item_name_and_price(client, item):
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed", "unit_price": 9.99})
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"
    assert r.json()["unit_price"] == 9.99
    # untouched fields preserved
    assert r.json()["sku"] == item["sku"]


def test_create_item_negative_reorder_point_422(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "reorder_point": -1})
    assert r.status_code == 422


def test_create_item_zero_reorder_point_ok(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "reorder_point": 0})
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_negative_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -1})
    assert r.status_code == 422
    # value is unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == item["reorder_point"]


def test_update_item_zero_reorder_point_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 0})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 0


def test_update_item_reorder_point(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # value is persisted
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


def test_update_item_omitting_reorder_point_preserves_it(client, item):
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


def test_delete_missing_item_404(client):
    r = client.delete("/items/4242")
    assert r.status_code == 404
    assert r.json()["detail"] == "item 4242 not found"


def test_delete_item_twice_second_404(client, item):
    item_id = item["id"]
    assert client.delete(f"/items/{item_id}").status_code == 204
    r = client.delete(f"/items/{item_id}")
    assert r.status_code == 404
    assert r.json()["detail"] == f"item {item_id} not found"


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get("/movements").json() == []


def test_delete_item_with_stock_409(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert "7" in r.json()["detail"]
    # item is untouched
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_across_locations_409(client, item, loc_a, loc_b):
    for loc, qty in ((loc_a, 2), (loc_b, 4)):
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert "6" in r.json()["detail"]


def test_delete_item_after_stock_zeroed(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 5, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_matches_get_by_id_shape(client, item):
    by_sku = client.get(f"/items/by-sku/{item['sku']}").json()
    by_id = client.get(f"/items/{item['id']}").json()
    assert by_sku == by_id


def test_get_item_by_sku_unknown_404(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    assert r.json()["detail"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # /items/{item_id} still works for ids after adding the by-sku route
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]
    # and non-integer single-segment paths still 422 against the id route
    assert client.get("/items/not-an-int").status_code == 422


def test_create_item_negative_unit_price_422(client):
    r = client.post("/items", json={"sku": "NEG", "name": "Neg", "unit_price": -0.01})
    assert r.status_code == 422


def test_create_item_zero_unit_price_ok(client):
    r = client.post("/items", json={"sku": "ZERO", "name": "Zero", "unit_price": 0})
    assert r.status_code == 201
    assert r.json()["unit_price"] == 0


def test_update_item_negative_unit_price_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": -1})
    assert r.status_code == 422


def test_update_item_zero_unit_price_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0
