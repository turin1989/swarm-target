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


def test_create_item_rejects_negative_reorder_point(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "reorder_point": -1})
    assert r.status_code == 422


def test_create_item_allows_zero_reorder_point(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "reorder_point": 0})
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_rejects_negative_reorder_point(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -5})
    assert r.status_code == 422


def test_update_item_allows_nonnegative_reorder_point(client, item):
    # Non-negative values must pass validation (not a 422).
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 7})
    assert r.status_code == 200


def test_create_item_normalises_sku(client):
    r = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r.status_code == 201
    assert r.json()["sku"] == "ABC-1"
    # stored normalised too
    assert client.get(f"/items/{r.json()['id']}").json()["sku"] == "ABC-1"


def test_create_item_duplicate_sku_conflicts_case_insensitive(client):
    assert client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"}).status_code == 201
    assert client.post("/items", json={"sku": "ABC-1", "name": "Dup"}).status_code == 409
    assert client.post("/items", json={"sku": "abc-1", "name": "Dup"}).status_code == 409


def test_create_item_whitespace_only_sku_422(client):
    assert client.post("/items", json={"sku": "   ", "name": "x"}).status_code == 422


def test_get_item(client, item):
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == item


def test_get_item_by_sku_unknown_404(client):
    r = client.get("/items/by-sku/NOPE-1")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "sku NOPE-1 not found"


def test_get_item_by_sku_does_not_shadow_get_by_id(client, item):
    # numeric id lookups still work alongside the by-sku route
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
    body = r.json()
    assert [i["sku"] for i in body["items"]] == ["C", "A", "B"]
    assert body["total"] == 3
    assert body["limit"] == 100
    assert body["offset"] == 0


def test_list_items_limit(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2})
    body = r.json()
    assert [i["sku"] for i in body["items"]] == ["S0", "S1"]
    assert body["total"] == 5  # total ignores pagination
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_list_items_offset(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2, "offset": 3})
    body = r.json()
    assert [i["sku"] for i in body["items"]] == ["S3", "S4"]
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 3


def test_list_items_sort_by_name_ascending(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Alpha", "Bravo", "Charlie"]


def test_list_items_sort_by_sku(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["A", "B", "C"]


def test_list_items_sort_by_id_explicit(client):
    for sku in ["C", "A", "B"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["C", "A", "B"]


def test_list_items_sort_descending(client):
    for sku, name in [("S1", "Alpha"), ("S2", "Charlie"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Charlie", "Bravo", "Alpha"]

    r = client.get("/items", params={"sort": "-id"})
    assert [i["sku"] for i in r.json()["items"]] == ["S3", "S2", "S1"]


def test_list_items_sort_invalid_value_422(client):
    assert client.get("/items", params={"sort": "price"}).status_code == 422
    assert client.get("/items", params={"sort": "-unknown"}).status_code == 422
    assert client.get("/items", params={"sort": ""}).status_code == 422


def test_list_items_default_sort_is_id(client):
    for sku in ["B", "A"]:
        client.post("/items", json={"sku": sku, "name": sku})
    r = client.get("/items")
    assert [i["sku"] for i in r.json()["items"]] == ["B", "A"]


def test_list_items_sort_with_pagination_envelope(client):
    for sku, name in [("S1", "Charlie"), ("S2", "Alpha"), ("S3", "Bravo")]:
        client.post("/items", json={"sku": sku, "name": name})
    r = client.get("/items", params={"sort": "name", "limit": 2, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert [i["name"] for i in body["items"]] == ["Bravo", "Charlie"]
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 1


def test_list_items_filter_active(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    active_body = client.get("/items", params={"active": "true"}).json()
    assert [i["sku"] for i in active_body["items"]] == ["WIDGET-1"]
    assert active_body["total"] == 1
    inactive_body = client.get("/items", params={"active": "false"}).json()
    assert [i["sku"] for i in inactive_body["items"]] == ["INACTIVE"]
    assert inactive_body["total"] == 1


def test_list_items_envelope_shape(client, item):
    body = client.get("/items").json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["items"] == [item]
    assert body["total"] == 1


def test_create_item_negative_unit_price_rejected(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "unit_price": -0.01})
    assert r.status_code == 422


def test_create_item_zero_unit_price_accepted(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "unit_price": 0})
    assert r.status_code == 201
    assert r.json()["unit_price"] == 0


def test_update_item_negative_unit_price_rejected(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": -5})
    assert r.status_code == 422


def test_update_item_zero_unit_price_accepted(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0


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


def test_update_item_reorder_point(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 12})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 12
    # value is persisted
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


def test_update_item_omitting_reorder_point_preserves_value(client, item):
    assert item["reorder_point"] == 5
    r = client.put(f"/items/{item['id']}", json={"name": "StillWidget"})
    assert r.status_code == 200
    assert r.json()["reorder_point"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == 5


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

def test_delete_missing_item_404(client):
    r = client.delete("/items/999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "item 999 not found"


def test_delete_item_twice_returns_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == f"item {item['id']} not found"
