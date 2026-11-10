"""Item CRUD and listing."""

import re

import pytest


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
    r = client.post("/items", json={"sku": "LONG", "name": "x", "description": "d" * 2001})
    assert r.status_code == 422


def test_create_item_description_at_limit_ok(client):
    r = client.post("/items", json={"sku": "LIMIT", "name": "x", "description": "d" * 2000})
    assert r.status_code == 201
    assert r.json()["description"] == "d" * 2000


# --- unit_price validation (T008) ----------------------------------------------


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
    # item unchanged
    assert client.get(f"/items/{item['id']}").json()["unit_price"] == item["unit_price"]


def test_update_item_zero_unit_price_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"unit_price": 0})
    assert r.status_code == 200
    assert r.json()["unit_price"] == 0


# --- reorder_point validation (T009) --------------------------------------------


def test_create_item_negative_reorder_point_422(client):
    r = client.post("/items", json={"sku": "NEG-RP", "name": "Neg", "reorder_point": -1})
    assert r.status_code == 422


def test_create_item_zero_reorder_point_ok(client):
    r = client.post("/items", json={"sku": "ZERO-RP", "name": "Zero", "reorder_point": 0})
    assert r.status_code == 201
    assert r.json()["reorder_point"] == 0


def test_update_item_negative_reorder_point_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": -5})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json()["reorder_point"] == item["reorder_point"]


def test_update_item_zero_reorder_point_accepted(client, item):
    # Zero is a valid reorder_point and must not be rejected by validation.
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 0})
    assert r.status_code == 200


def test_update_item_description_too_long_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "d" * 2001})
    assert r.status_code == 422


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "d" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "d" * 2000


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


# --- sku filter (T010) ----------------------------------------------------------


def test_list_items_filter_sku_exact_match(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Widget 2"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()
    assert [i["sku"] for i in body] == ["WIDGET-1"]


def test_list_items_filter_sku_is_exact_not_prefix(client, item):
    client.post("/items", json={"sku": "WIDGET-10", "name": "Widget 10"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["WIDGET-1"]


def test_list_items_filter_sku_unknown_returns_empty_list_200(client, item):
    r = client.get("/items", params={"sku": "NOPE"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_filter_sku_combines_with_active(client, item):
    # item WIDGET-1 is active; make it inactive and verify combined filtering
    client.post("/items", json={"sku": "OTHER", "name": "Other"})
    assert (
        client.get("/items", params={"sku": "WIDGET-1", "active": "true"}).json()[0]["sku"]
        == "WIDGET-1"
    )
    assert client.get("/items", params={"sku": "WIDGET-1", "active": "false"}).json() == []

    client.put(f"/items/{item['id']}", json={"active": False})
    assert client.get("/items", params={"sku": "WIDGET-1", "active": "true"}).json() == []
    assert [
        i["sku"]
        for i in client.get("/items", params={"sku": "WIDGET-1", "active": "false"}).json()
    ] == ["WIDGET-1"]


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
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "item 999 not found"


def test_delete_item_twice_second_is_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == f"item {item['id']} not found"


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    client.delete(f"/items/{item['id']}")
    assert client.get("/movements").json() == []


# --- created_at (T020) ---------------------------------------------------------

ISO_8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def test_create_item_sets_created_at_iso8601_utc(client):
    r = client.post("/items", json={"sku": "TS-1", "name": "Timestamped"})
    assert r.status_code == 201
    created_at = r.json()["created_at"]
    assert ISO_8601_UTC.match(created_at), created_at


def test_created_at_returned_by_every_item_endpoint(client, item):
    assert ISO_8601_UTC.match(item["created_at"])

    # GET /items/{id}
    r = client.get(f"/items/{item['id']}")
    assert r.json()["created_at"] == item["created_at"]

    # GET /items
    r = client.get("/items")
    assert all(ISO_8601_UTC.match(i["created_at"]) for i in r.json())

    # PUT /items/{id}
    r = client.put(f"/items/{item['id']}", json={"name": "Renamed"})
    assert r.json()["created_at"] == item["created_at"]

    # GET /search
    r = client.get("/search", params={"q": "WIDGET"})
    assert r.status_code == 200
    assert [i["created_at"] for i in r.json()] == [item["created_at"]]


def test_created_at_cannot_be_set_by_client_on_create(client):
    r = client.post(
        "/items",
        json={"sku": "NO-SET", "name": "NoSet", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 201
    assert r.json()["created_at"] != "1999-01-01T00:00:00Z"
    assert ISO_8601_UTC.match(r.json()["created_at"])


def test_created_at_ignored_on_put(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"name": "Changed", "created_at": "1999-01-01T00:00:00Z"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Changed"
    assert r.json()["created_at"] == item["created_at"]
    # Still unchanged on a fresh read
    assert client.get(f"/items/{item['id']}").json()["created_at"] == item["created_at"]


# --- GET /items/by-sku/{sku} (T011) ---------------------------------------------


def test_get_item_by_sku_returns_same_shape_as_get_by_id(client, item):
    r = client.get(f"/items/by-sku/{item['sku']}")
    assert r.status_code == 200
    assert r.json() == client.get(f"/items/{item['id']}").json()
    assert r.json() == item


def test_get_item_by_sku_exact_match_only(client, item):
    # partial / case-different skus do not match
    assert client.get("/items/by-sku/WIDGET").status_code == 404
    assert client.get("/items/by-sku/widget-1").status_code == 404


def test_get_item_by_sku_unknown_404_with_detail(client):
    r = client.get("/items/by-sku/NOPE-99")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "sku NOPE-99 not found"


def test_get_item_by_sku_does_not_shadow_get_item_by_id(client, item):
    # numeric id lookups still work
    r = client.get(f"/items/{item['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == item["id"]
    # and a sku that collides with sub-resource names still resolves via by-sku
    client.post("/items", json={"sku": "stock", "name": "Stocky"})
    r = client.get("/items/by-sku/stock")
    assert r.status_code == 200
    assert r.json()["sku"] == "stock"
    # item sub-resources remain reachable
    assert client.get(f"/items/{item['id']}/stock").status_code == 200
    assert client.get(f"/items/{item['id']}/movements").status_code == 200


# --- X-Total-Count header (T037) -------------------------------------------------


def test_list_items_total_count_empty(client):
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "0"


def test_list_items_total_count_ignores_limit_and_offset(client):
    for i in range(5):
        assert client.post("/items", json={"sku": f"TC-{i}", "name": f"Item {i}"}).status_code == 201
    r = client.get("/items", params={"limit": 2, "offset": 3})
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"


def test_list_items_total_count_respects_filters(client):
    for i in range(3):
        assert client.post("/items", json={"sku": f"ACT-{i}", "name": "Active"}).status_code == 201
    r = client.post("/items", json={"sku": "INACT", "name": "Inactive"})
    assert r.status_code == 201
    inactive_id = r.json()["id"]
    assert client.put(f"/items/{inactive_id}", json={"active": False}).status_code == 200

    r = client.get("/items", params={"active": "true", "limit": 1})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "3"

    r = client.get("/items", params={"active": "false"})
    assert r.headers["X-Total-Count"] == "1"


# --- sort parameter (T021) --------------------------------------------------------


def _skus(resp):
    return [i["sku"] for i in resp.json()]


@pytest.fixture()
def sortable_items(client):
    # ids 1..3; names and skus deliberately out of insertion order
    client.post("/items", json={"sku": "B-SKU", "name": "Charlie"})
    client.post("/items", json={"sku": "C-SKU", "name": "Alpha"})
    client.post("/items", json={"sku": "A-SKU", "name": "Bravo"})


def test_list_items_default_sort_is_id(client, sortable_items):
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()] == [1, 2, 3]
    assert _skus(r) == ["B-SKU", "C-SKU", "A-SKU"]


def test_list_items_sort_by_name_ascending(client, sortable_items):
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()] == ["Alpha", "Bravo", "Charlie"]


def test_list_items_sort_by_sku_ascending(client, sortable_items):
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert _skus(r) == ["A-SKU", "B-SKU", "C-SKU"]


def test_list_items_sort_by_id_explicit(client, sortable_items):
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()] == [1, 2, 3]


def test_list_items_sort_descending_with_minus_prefix(client, sortable_items):
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()] == ["Charlie", "Bravo", "Alpha"]

    r = client.get("/items", params={"sort": "-sku"})
    assert _skus(r) == ["C-SKU", "B-SKU", "A-SKU"]

    r = client.get("/items", params={"sort": "-id"})
    assert [i["id"] for i in r.json()] == [3, 2, 1]


def test_list_items_sort_invalid_value_422(client, sortable_items):
    for bad in ["price", "-price", "name;DROP TABLE items", "", "-", "--name", "NAME"]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, f"sort={bad!r} -> {r.status_code}"


def test_list_items_sort_combines_with_filters_and_pagination(client, sortable_items):
    r = client.get("/items", params={"sort": "sku", "limit": 2, "offset": 1})
    assert r.status_code == 200
    assert _skus(r) == ["B-SKU", "C-SKU"]
    assert r.headers["X-Total-Count"] == "3"
