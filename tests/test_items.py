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
    assert body["reorder_level"] == 0
    assert body["active"] is True


def test_create_item_rejects_reorder_point(client):
    r = client.post(
        "/items", json={"sku": "A-2", "name": "Alpha", "reorder_point": 3}
    )
    assert r.status_code == 422


def test_update_item_rejects_reorder_point(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 3})
    assert r.status_code == 422


def test_create_item_accepts_reorder_level(client):
    r = client.post("/items", json={"sku": "A-3", "name": "Alpha", "reorder_level": 7})
    assert r.status_code == 201
    assert r.json()["reorder_level"] == 7


def test_create_item_duplicate_sku_conflicts(client, item):
    r = client.post("/items", json={"sku": item["sku"], "name": "Dup"})
    assert r.status_code == 409


def test_create_item_requires_sku_and_name(client):
    assert client.post("/items", json={"name": "x"}).status_code == 422
    assert client.post("/items", json={"sku": "x"}).status_code == 422
    assert client.post("/items", json={"sku": "", "name": "x"}).status_code == 422


def test_create_item_rejects_negative_reorder_level(client):
    r = client.post("/items", json={"sku": "NEG-1", "name": "Neg", "reorder_level": -1})
    assert r.status_code == 422


def test_create_item_allows_zero_reorder_level(client):
    r = client.post("/items", json={"sku": "ZERO-1", "name": "Zero", "reorder_level": 0})
    assert r.status_code == 201
    assert r.json()["reorder_level"] == 0


def test_update_item_rejects_negative_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": -5})
    assert r.status_code == 422


def test_update_item_allows_nonnegative_reorder_level(client, item):
    # Non-negative values must pass validation (not a 422).
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 7})
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


def test_list_items_total_count_header(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items")
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_total_count_ignores_limit_and_offset(client):
    for n in range(5):
        client.post("/items", json={"sku": f"S{n}", "name": f"N{n}"})
    r = client.get("/items", params={"limit": 2, "offset": 4})
    assert len(r.json()["items"]) == 1
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_total_count_respects_filters(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    assert client.get("/items", params={"active": "true"}).headers["X-Total-Count"] == "1"
    assert client.get("/items", params={"active": "false"}).headers["X-Total-Count"] == "1"
    assert client.get("/items").headers["X-Total-Count"] == "2"


def test_list_items_total_count_respects_sku_filter(client, item):
    client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    assert client.get("/items", params={"sku": "WIDGET-1"}).headers["X-Total-Count"] == "1"
    assert client.get("/items", params={"sku": "NOPE"}).headers["X-Total-Count"] == "0"
    assert client.get("/items").headers["X-Total-Count"] == "2"


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


def test_list_items_filter_sku_exact(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Other"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body["items"]] == ["WIDGET-1"]
    assert body["total"] == 1
    # no partial matches
    partial = client.get("/items", params={"sku": "WIDGET"}).json()
    assert partial["items"] == []
    assert partial["total"] == 0


def test_list_items_filter_sku_unknown_returns_empty_list(client, item):
    r = client.get("/items", params={"sku": "NOPE"})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_items_filter_sku_combined_with_active(client, item):
    client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    client.put("/items/2", json={"active": False})
    assert [
        i["sku"]
        for i in client.get("/items", params={"sku": "WIDGET-1", "active": "true"}).json()["items"]
    ] == ["WIDGET-1"]
    assert client.get("/items", params={"sku": "WIDGET-1", "active": "false"}).json()["items"] == []
    assert [
        i["sku"]
        for i in client.get("/items", params={"sku": "GADGET-1", "active": "false"}).json()["items"]
    ] == ["GADGET-1"]


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


def test_update_item_reorder_level(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 12})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 12
    # value is persisted
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 12


def test_update_item_reorder_level_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_level": 7, "name": "Renamed", "unit_price": 3.75},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_level"] == 7
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 3.75
    stored = client.get(f"/items/{item['id']}").json()
    assert stored["reorder_level"] == 7
    assert stored["name"] == "Renamed"


def test_update_item_omitting_reorder_level_preserves_value(client, item):
    assert item["reorder_level"] == 5
    r = client.put(f"/items/{item['id']}", json={"name": "StillWidget"})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


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
    # drain the stock so the item is deletable
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 3, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get("/movements").json() == []


def test_delete_item_with_stock_conflicts(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "7" in body["error"]["message"]
    # item is untouched
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_after_stock_drained_to_zero(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 2, "to_location_id": loc_a["id"]},
    )
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "quantity": 2, "from_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 204
    assert client.get(f"/items/{item['id']}").status_code == 404


def test_create_item_description_too_long_422(client):
    r = client.post("/items", json={"sku": "LONGDESC", "name": "X", "description": "d" * 2001})
    assert r.status_code == 422


def test_create_item_description_at_limit_ok(client):
    r = client.post("/items", json={"sku": "MAXDESC", "name": "X", "description": "d" * 2000})
    assert r.status_code == 201
    assert len(r.json()["description"]) == 2000


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "d" * 2001})
    assert r.status_code == 422


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "d" * 2000})
    assert r.status_code == 200
    assert len(r.json()["description"]) == 2000


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


# --- barcode -------------------------------------------------------------------


def test_create_item_barcode_defaults_to_null(client, item):
    assert item["barcode"] is None
    assert client.get(f"/items/{item['id']}").json()["barcode"] is None


def test_create_item_with_barcode(client):
    r = client.post("/items", json={"sku": "B-1", "name": "Bar", "barcode": "0123456789"})
    assert r.status_code == 201
    assert r.json()["barcode"] == "0123456789"
    assert client.get(f"/items/{r.json()['id']}").json()["barcode"] == "0123456789"


def test_create_item_with_barcode_and_reorder_level(client):
    r = client.post(
        "/items",
        json={"sku": "B-9", "name": "Both", "barcode": "9999", "reorder_level": 4},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["barcode"] == "9999"
    assert body["reorder_level"] == 4
    stored = client.get(f"/items/{body['id']}").json()
    assert stored["barcode"] == "9999"
    assert stored["reorder_level"] == 4


def test_create_item_duplicate_barcode_conflicts(client):
    r1 = client.post("/items", json={"sku": "B-1", "name": "Bar", "barcode": "4711"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "B-2", "name": "Baz", "barcode": "4711"})
    assert r2.status_code == 409
    body = r2.json()
    assert body["error"]["code"] == "conflict"
    assert "barcode" in body["error"]["message"]


def test_multiple_items_without_barcode_allowed(client):
    assert client.post("/items", json={"sku": "N-1", "name": "One"}).status_code == 201
    assert client.post("/items", json={"sku": "N-2", "name": "Two"}).status_code == 201
    assert (
        client.post("/items", json={"sku": "N-3", "name": "Three", "barcode": None}).status_code
        == 201
    )


def test_list_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "F-1", "name": "One", "barcode": "111"})
    client.post("/items", json={"sku": "F-2", "name": "Two", "barcode": "222"})
    client.post("/items", json={"sku": "F-3", "name": "Three"})
    r = client.get("/items", params={"barcode": "222"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "F-2"
    assert body["items"][0]["barcode"] == "222"
    assert body["total"] == 1


def test_list_items_filter_by_unknown_barcode_returns_empty(client, item):
    r = client.get("/items", params={"barcode": "no-such"})
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_list_items_filter_barcode_combined_with_active(client):
    client.post("/items", json={"sku": "C-1", "name": "One", "barcode": "999"})
    client.put("/items/1", json={"active": False})
    assert (
        client.get("/items", params={"barcode": "999", "active": "true"}).json()["items"] == []
    )
    r = client.get("/items", params={"barcode": "999", "active": "false"})
    assert [i["sku"] for i in r.json()["items"]] == ["C-1"]


def test_list_items_total_count_respects_barcode_filter(client):
    client.post("/items", json={"sku": "F-1", "name": "One", "barcode": "111"})
    client.post("/items", json={"sku": "F-2", "name": "Two"})
    assert client.get("/items", params={"barcode": "111"}).headers["X-Total-Count"] == "1"
    assert client.get("/items", params={"barcode": "nope"}).headers["X-Total-Count"] == "0"


# --- bulk creation -------------------------------------------------------------


def test_bulk_create_returns_201_and_created_items(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "B-1", "name": "Bulk One", "unit_price": 1.0},
            {"sku": "B-2", "name": "Bulk Two", "unit_price": 2.0, "reorder_level": 3},
        ],
    )
    assert r.status_code == 201
    body = r.json()
    assert [i["sku"] for i in body] == ["B-1", "B-2"]
    assert all(i["id"] > 0 for i in body)
    assert body[0]["active"] is True
    assert body[1]["reorder_level"] == 3
    # items are persisted
    assert [i["sku"] for i in client.get("/items").json()["items"]] == ["B-1", "B-2"]


def test_bulk_create_normalises_sku(client):
    r = client.post("/items/bulk", json=[{"sku": "  bulk-1 ", "name": "Bulk"}])
    assert r.status_code == 201
    assert r.json()[0]["sku"] == "BULK-1"


def test_bulk_create_duplicate_sku_is_atomic(client, item):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New One"},
            {"sku": item["sku"], "name": "Dup"},
            {"sku": "NEW-2", "name": "New Two"},
        ],
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    # nothing was created: only the pre-existing fixture item remains
    listing = client.get("/items").json()
    assert [i["sku"] for i in listing["items"]] == [item["sku"]]
    assert listing["total"] == 1


def test_bulk_create_duplicate_sku_within_payload_is_atomic(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "SAME", "name": "First"},
            {"sku": "SAME", "name": "Second"},
        ],
    )
    assert r.status_code == 409
    listing = client.get("/items").json()
    assert listing["items"] == []
    assert listing["total"] == 0


def test_bulk_create_empty_list_422(client):
    r = client.post("/items/bulk", json=[])
    assert r.status_code == 422


def test_bulk_create_invalid_entry_422(client):
    r = client.post("/items/bulk", json=[{"sku": "OK-1", "name": "Ok"}, {"name": "missing sku"}])
    assert r.status_code == 422
    listing = client.get("/items").json()
    assert listing["items"] == []
    assert listing["total"] == 0


# --- bulk creation x barcode -----------------------------------------------------


def test_bulk_create_persists_barcodes(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "B-1", "name": "One", "barcode": "111"},
            {"sku": "B-2", "name": "Two"},
        ],
    )
    assert r.status_code == 201
    body = r.json()
    assert body[0]["barcode"] == "111"
    assert body[1]["barcode"] is None
    listed = client.get("/items", params={"barcode": "111"}).json()
    assert [i["sku"] for i in listed["items"]] == ["B-1"]


def test_bulk_create_duplicate_barcode_is_atomic(client):
    assert (
        client.post("/items", json={"sku": "EXIST", "name": "Pre", "barcode": "4711"}).status_code
        == 201
    )
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "NEW-1", "name": "New One"},
            {"sku": "NEW-2", "name": "New Two", "barcode": "4711"},
        ],
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "barcode" in body["error"]["message"]
    # nothing from the bulk payload was created
    listing = client.get("/items").json()
    assert [i["sku"] for i in listing["items"]] == ["EXIST"]
    assert listing["total"] == 1


def test_bulk_create_duplicate_barcode_within_payload_is_atomic(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "P-1", "name": "First", "barcode": "99"},
            {"sku": "P-2", "name": "Second", "barcode": "99"},
        ],
    )
    assert r.status_code == 409
    assert "barcode" in r.json()["error"]["message"]
    listing = client.get("/items").json()
    assert listing["items"] == []
    assert listing["total"] == 0


# --- created_at ----------------------------------------------------------------


ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_create_item_sets_created_at_iso_utc(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    assert r.status_code == 201
    created_at = r.json()["created_at"]
    assert ISO_UTC.match(created_at), created_at


def test_created_at_returned_by_get_list_and_search(client, item):
    assert ISO_UTC.match(item["created_at"])

    got = client.get(f"/items/{item['id']}").json()
    assert got["created_at"] == item["created_at"]

    listed = client.get("/items").json()
    assert listed["items"][0]["created_at"] == item["created_at"]

    found = client.get("/search", params={"q": item["sku"]}).json()
    assert found[0]["created_at"] == item["created_at"]


def test_created_at_cannot_be_set_by_client_on_create(client):
    # created_at is server-managed; with strict payload validation an attempt
    # to set it is rejected outright rather than silently ignored.
    r = client.post(
        "/items",
        json={"sku": "TS-2", "name": "Sneaky", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 422
    # no item was created with the forged timestamp
    skus = [i["sku"] for i in client.get("/items").json()["items"]]
    assert "TS-2" not in skus


def test_created_at_ignored_on_put(client, item):
    # created_at is server-managed; with strict payload validation an attempt
    # to change it on update is rejected outright rather than silently ignored.
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Renamed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 422

    # item is completely unchanged when fetched again
    got = client.get(f"/items/{item['id']}").json()
    assert got["created_at"] == item["created_at"]
    assert got["name"] == item["name"]


def test_bulk_create_sets_created_at(client):
    r = client.post("/items/bulk", json=[{"sku": "B-TS", "name": "Bulk TS"}])
    assert r.status_code == 201
    assert ISO_UTC.match(r.json()[0]["created_at"])


# --- sort parameter ------------------------------------------------------------


def _seed_sortable_items(client):
    # insertion order: ids 1, 2, 3
    client.post("/items", json={"sku": "SKU-B", "name": "Charlie"})
    client.post("/items", json={"sku": "SKU-C", "name": "Alpha"})
    client.post("/items", json={"sku": "SKU-A", "name": "Bravo"})


def test_list_items_sort_default_is_id(client):
    _seed_sortable_items(client)
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_name_ascending_seeded(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Alpha", "Bravo", "Charlie"]


def test_list_items_sort_by_name_descending(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Charlie", "Bravo", "Alpha"]


def test_list_items_sort_by_sku_ascending(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["SKU-A", "SKU-B", "SKU-C"]


def test_list_items_sort_by_sku_descending(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "-sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["SKU-C", "SKU-B", "SKU-A"]


def test_list_items_sort_by_id_explicit_seeded(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_id_descending(client):
    _seed_sortable_items(client)
    r = client.get("/items", params={"sort": "-id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [3, 2, 1]


def test_list_items_sort_invalid_values_422(client):
    _seed_sortable_items(client)
    for bad in ["price", "-price", "unit_price", "name; DROP TABLE items", "--name", "-", ""]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, bad


def test_list_items_sort_combines_with_filters_and_pagination(client):
    _seed_sortable_items(client)
    client.put("/items/1", json={"active": False})
    r = client.get("/items", params={"sort": "-name", "active": "true", "limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [i["name"] for i in body["items"]] == ["Bravo"]
