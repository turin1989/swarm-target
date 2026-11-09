"""Item CRUD and listing."""

import re


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


def test_create_item_rejects_negative_unit_price(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "unit_price": -0.01})
    assert r.status_code == 422


def test_create_item_accepts_zero_unit_price(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "unit_price": 0})
    assert r.status_code == 201
    assert r.json()["unit_price"] == 0


def test_update_item_rejects_negative_unit_price(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": -5})
    assert r.status_code == 422
    # persisted value unchanged
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == item["unit_price"]


def test_update_item_accepts_zero_unit_price(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0


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
    assert [i["sku"] for i in r.json()["items"]] == ["C", "A", "B"]


def test_list_items_limit(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2})
    assert [i["sku"] for i in r.json()["items"]] == ["S0", "S1"]


def test_list_items_filter_active(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    active = client.get("/items", params={"active": "true"}).json()["items"]
    inactive = client.get("/items", params={"active": "false"}).json()["items"]
    assert [i["sku"] for i in active] == ["WIDGET-1"]
    assert [i["sku"] for i in inactive] == ["INACTIVE"]


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


def test_delete_item_twice_second_returns_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    assert r.json()["detail"] == f"item {item['id']} not found"


def test_delete_missing_item_does_not_affect_existing_items(client, item):
    missing_id = item["id"] + 1000
    r = client.delete(f"/items/{missing_id}")
    assert r.status_code == 404
    assert r.json()["detail"] == f"item {missing_id} not found"
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    client.delete(f"/items/{item['id']}")
    assert client.get("/movements").json() == []


# --- created_at ---------------------------------------------------------------

ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_create_item_sets_created_at(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    assert r.status_code == 201
    body = r.json()
    assert "created_at" in body
    assert ISO_UTC_RE.match(body["created_at"]), body["created_at"]


def test_created_at_returned_by_all_item_endpoints(client, item):
    created_at = item["created_at"]
    assert ISO_UTC_RE.match(created_at)

    # GET /items/{id}
    assert client.get(f"/items/{item['id']}").json()["created_at"] == created_at
    # GET /items
    assert client.get("/items").json()["items"][0]["created_at"] == created_at
    # PUT /items/{id}
    assert client.put(f"/items/{item['id']}", json={"name": "New"}).json()["created_at"] == created_at
    # GET /search
    results = client.get("/search", params={"q": "WIDGET"}).json()
    assert results[0]["created_at"] == created_at


def test_created_at_ignored_on_create(client):
    r = client.post(
        "/items",
        json={"sku": "NOPE-1", "name": "Nope", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 201
    assert r.json()["created_at"] != "1999-01-01T00:00:00Z"
    assert ISO_UTC_RE.match(r.json()["created_at"])


def test_created_at_cannot_be_changed_on_put(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Renamed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.json()["created_at"] == item["created_at"]
    # persisted value unchanged too
    assert client.get(f"/items/{item['id']}").json()["created_at"] == item["created_at"]


def test_list_items_x_total_count_header(client):
    for i in range(5):
        client.post("/items", json={"sku": f"TC-{i}", "name": f"Item {i}"})
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_x_total_count_ignores_limit_and_offset(client):
    for i in range(5):
        client.post("/items", json={"sku": f"TC-{i}", "name": f"Item {i}"})
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_x_total_count_respects_filters(client):
    for i in range(4):
        client.post("/items", json={"sku": f"TC-{i}", "name": f"Item {i}"})
    # deactivate one item
    r = client.put("/items/1", json={"active": False})
    assert r.status_code == 200

    r = client.get("/items", params={"active": "true", "limit": 1})
    assert r.headers["X-Total-Count"] == "3"
    assert len(r.json()["items"]) == 1

    r = client.get("/items", params={"active": "false"})
    assert r.headers["X-Total-Count"] == "1"


def test_list_items_x_total_count_empty(client):
    r = client.get("/items")
    assert r.headers["X-Total-Count"] == "0"


# --- pagination envelope --------------------------------------------------------


def test_list_items_returns_paginated_envelope(client):
    for i in range(3):
        client.post("/items", json={"sku": f"PG-{i}", "name": f"Item {i}"})
    r = client.get("/items")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert [i["sku"] for i in body["items"]] == ["PG-0", "PG-1", "PG-2"]
    assert body["total"] == 3
    assert body["limit"] == 100  # default
    assert body["offset"] == 0


def test_list_items_envelope_total_ignores_pagination(client):
    for i in range(5):
        client.post("/items", json={"sku": f"PG-{i}", "name": f"Item {i}"})
    r = client.get("/items", params={"limit": 2, "offset": 3})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body["items"]] == ["PG-3", "PG-4"]
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 3


def test_list_items_envelope_total_respects_filters(client):
    for i in range(4):
        client.post("/items", json={"sku": f"PG-{i}", "name": f"Item {i}"})
    client.put("/items/1", json={"active": False})
    body = client.get("/items", params={"active": "true", "limit": 1}).json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_list_items_envelope_empty(client):
    body = client.get("/items").json()
    assert body == {"items": [], "total": 0, "limit": 100, "offset": 0}


# --- barcode -------------------------------------------------------------------


def test_create_item_barcode_defaults_to_null(client):
    r = client.post("/items", json={"sku": "NB-1", "name": "No barcode"})
    assert r.status_code == 201
    assert r.json()["barcode"] is None


def test_create_item_with_barcode(client):
    r = client.post("/items", json={"sku": "BC-1", "name": "Scanned", "barcode": "0123456789012"})
    assert r.status_code == 201
    assert r.json()["barcode"] == "0123456789012"
    # persisted and returned on GET too
    assert client.get(f"/items/{r.json()['id']}").json()["barcode"] == "0123456789012"


def test_create_item_duplicate_barcode_conflicts(client):
    r1 = client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "DUP-123"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "DUP-123"})
    assert r2.status_code == 409
    assert "barcode" in r2.json()["detail"]


def test_create_many_items_without_barcode_allowed(client):
    # NULL barcodes must not collide with each other
    for n in range(3):
        r = client.post("/items", json={"sku": f"NULL-{n}", "name": f"N{n}"})
        assert r.status_code == 201
        assert r.json()["barcode"] is None


def test_list_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "111"})
    client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "222"})
    client.post("/items", json={"sku": "BC-3", "name": "Three"})
    r = client.get("/items", params={"barcode": "222"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "BC-2"
    assert body["items"][0]["barcode"] == "222"
    assert r.headers["X-Total-Count"] == "1"


def test_list_items_filter_by_barcode_no_match(client):
    client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "111"})
    r = client.get("/items", params={"barcode": "nope"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_items_filter_barcode_combines_with_active(client):
    client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "111"})
    client.put("/items/1", json={"active": False})
    assert client.get("/items", params={"barcode": "111", "active": "true"}).json()["items"] == []
    assert (
        len(client.get("/items", params={"barcode": "111", "active": "false"}).json()["items"]) == 1
    )
