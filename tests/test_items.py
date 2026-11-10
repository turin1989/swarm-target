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


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_same_shape_as_get_by_id(client, item):
    by_sku = client.get(f"/items/by-sku/{item['sku']}").json()
    by_id = client.get(f"/items/{item['id']}").json()
    assert by_sku == by_id


def test_get_item_by_sku_exact_match_only(client, item):
    assert client.get("/items/by-sku/WIDGET").status_code == 404
    assert client.get("/items/by-sku/widget-1").status_code == 404


def test_get_item_by_sku_missing_404(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    assert r.json()["detail"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # numeric path still resolves to get-by-id
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]
    # and the by-sku route works even for a sku that looks numeric
    created = client.post("/items", json={"sku": "123", "name": "Numeric SKU"}).json()
    r = client.get("/items/by-sku/123")
    assert r.status_code == 200
    assert r.json() == created


def test_list_items_ordered_by_id(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["C", "A", "B"]


def test_list_items_sort_default_is_id(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku.lower()})
    r = client.get("/items")
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


def test_list_items_sort_descending(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()] == ["Charlie", "Bravo", "Alpha"]

    r = client.get("/items", params={"sort": "-sku"})
    assert [i["sku"] for i in r.json()] == ["S3", "S2", "S1"]

    r = client.get("/items", params={"sort": "-id"})
    assert [i["sku"] for i in r.json()] == ["S3", "S2", "S1"]


def test_list_items_sort_invalid_422(client):
    for bad in ["unit_price", "name; DROP TABLE items", "-", "--name", ""]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, bad


def test_list_items_sort_combines_with_active_filter(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    client.put("/items/2", json={"active": False})
    r = client.get("/items", params={"sort": "name", "active": "true"})
    assert [i["name"] for i in r.json()] == ["Bravo", "Charlie"]


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


def test_delete_missing_item_404(client):
    r = client.delete("/items/999")
    assert r.status_code == 404
    assert r.json()["detail"] == "item 999 not found"


def test_delete_item_twice_second_404(client, item):
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


def test_create_item_negative_reorder_point_422(client):
    r = client.post(
        "/items", json={"sku": "NEG-1", "name": "Neg", "reorder_point": -1}
    )
    assert r.status_code == 422


def test_create_item_zero_reorder_point_ok(client):
    r = client.post(
        "/items", json={"sku": "ZERO-RP", "name": "Zero", "reorder_point": 0}
    )
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_negative_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -5})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json() == item


def test_update_item_nonnegative_reorder_point_accepted(client, item):
    # a non-negative reorder_point passes validation (no 422)
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 7})
    assert r.status_code == 200


def test_update_item_reorder_point_persists_and_returned(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # persisted
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 12


def test_update_item_reorder_point_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_point": 9, "name": "Renamed", "unit_price": 3.75},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_point"] == 9
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 3.75
    fetched = client.get(f"/items/{item['id']}").json()
    assert fetched["reorder_point"] == 9
    assert fetched["name"] == "Renamed"
    assert fetched["unit_price"] == 3.75


def test_update_item_omitting_reorder_point_leaves_it_untouched(client, item):
    assert item["reorder_point"] == 5
    r = client.put(f"/items/{item['id']}", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 5


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


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "x" * 2000
