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


def test_create_item_normalises_sku_trim_and_uppercase(client):
    r = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r.status_code == 201
    assert r.json()["sku"] == "ABC-1"
    # stored value is normalised too
    assert client.get(f"/items/{r.json()['id']}").json()["sku"] == "ABC-1"


def test_create_item_duplicate_sku_conflicts_after_normalisation(client):
    assert client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"}).status_code == 201
    assert client.post("/items", json={"sku": "ABC-1", "name": "Dup"}).status_code == 409
    assert client.post("/items", json={"sku": "abc-1", "name": "Dup"}).status_code == 409


def test_create_item_whitespace_only_sku_is_422(client):
    assert client.post("/items", json={"sku": "   ", "name": "x"}).status_code == 422
    assert client.post("/items", json={"sku": "\t \n", "name": "x"}).status_code == 422


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
    client.post("/items", json={"sku": "WIDGET-2", "name": "Other Widget"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body] == ["WIDGET-1"]
    assert body[0] == item


def test_list_items_filter_sku_is_exact_not_partial(client, item):
    client.post("/items", json={"sku": "WIDGET-10", "name": "Bigger Widget"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]
    # a partial sku matches nothing
    r = client.get("/items", params={"sku": "WIDGET"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_unknown_returns_empty_list(client, item):
    r = client.get("/items", params={"sku": "NO-SUCH-SKU"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_combines_with_active(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Other Widget"})
    # deactivate WIDGET-1
    client.put(f"/items/{item['id']}", json={"active": False})

    r = client.get("/items", params={"sku": "WIDGET-1", "active": "true"})
    assert r.status_code == 200
    assert r.json() == []

    r = client.get("/items", params={"sku": "WIDGET-1", "active": "false"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]


def test_list_items_filter_sku_combines_with_barcode(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Other Widget", "barcode": "BC-2"})
    client.post("/items", json={"sku": "WIDGET-3", "name": "Third Widget", "barcode": "BC-3"})

    # matching sku + barcode pair returns the item
    r = client.get("/items", params={"sku": "WIDGET-2", "barcode": "BC-2"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-2"]

    # mismatched sku/barcode pair returns nothing (filters are ANDed)
    r = client.get("/items", params={"sku": "WIDGET-2", "barcode": "BC-3"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_x_total_count_respects_sku_filter(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Other Widget"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "1"


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
    # ship the stock back out so the item is at zero and may be deleted
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
    # item is untouched
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_across_locations_conflicts(client, item, loc_a, loc_b):
    for loc in (loc_a, loc_b):
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": 2, "to_location_id": loc["id"]},
        )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    assert "4" in r.json()["detail"]


def test_delete_item_allowed_after_stock_returns_to_zero(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 409
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 5, "from_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    # same shape/content as GET /items/{id}
    assert r.json() == client.get(f"/items/{item['id']}").json()
    assert r.json() == item


def test_get_item_by_sku_exact_match_only(client, item):
    # item fixture sku is "WIDGET-1"; a non-exact sku must 404
    r = client.get("/items/by-sku/widget-1")
    assert r.status_code == 404


def test_get_item_by_unknown_sku_404(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    assert r.json()["detail"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # numeric path still resolves to GET /items/{item_id}
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json() == item
    # and the by-sku route works even for a numeric-looking sku
    r2 = client.post("/items", json={"sku": "123", "name": "Numeric"})
    assert r2.status_code == 201
    r3 = client.get("/items/by-sku/123")
    assert r3.status_code == 200
    assert r3.json() == r2.json()


def test_list_items_x_total_count_all_items(client):
    for sku in ["A", "B", "C"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"


def test_list_items_x_total_count_ignores_limit_and_offset(client):
    for i in range(5):
        client.post("/items", json={"sku": f"SKU-{i}", "name": f"Item {i}"})
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_x_total_count_respects_active_filter(client):
    for i in range(4):
        client.post("/items", json={"sku": f"SKU-{i}", "name": f"Item {i}"})
    # deactivate the first item
    client.put("/items/1", json={"active": False})

    r = client.get("/items", params={"active": "true", "limit": 1})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "3"

    r = client.get("/items", params={"active": "false"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "1"


def test_list_items_x_total_count_zero_when_empty(client):
    r = client.get("/items")
    assert r.status_code == 200
    assert r.json() == []
    assert r.headers["X-Total-Count"] == "0"


def test_update_reorder_point_persists_and_returns(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # persisted
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12


def test_update_reorder_point_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_point": 7, "name": "Widget v2", "unit_price": 9.99},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_point"] == 7
    assert body["name"] == "Widget v2"
    assert body["unit_price"] == 9.99
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_point"] == 7
    assert stored["name"] == "Widget v2"
    assert stored["unit_price"] == 9.99


def test_update_without_reorder_point_leaves_it_untouched(client, item):
    assert client.put(f"/items/{item['id']}", json={"reorder_point": 12}).status_code == 200
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed"})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12
