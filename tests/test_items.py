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
    assert [
        i["sku"] for i in client.get("/items", params={"active": "true"}).json()["items"]
    ] == ["WIDGET-1"]
    assert [
        i["sku"] for i in client.get("/items", params={"active": "false"}).json()["items"]
    ] == ["INACTIVE"]


# --- pagination envelope ---------------------------------------------------------


def test_list_items_returns_envelope_shape(client):
    for n in range(3):
        client.post("/items", json={"sku": f"E{n}", "name": f"E{n}"})
    r = client.get("/items")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 3
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert [i["sku"] for i in body["items"]] == ["E0", "E1", "E2"]


def test_list_items_total_ignores_pagination(client):
    for n in range(5):
        client.post("/items", json={"sku": f"P{n}", "name": f"P{n}"})
    r = client.get("/items", params={"limit": 2, "offset": 1})
    body = r.json()
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert [i["sku"] for i in body["items"]] == ["P1", "P2"]


def test_list_items_total_respects_filters(client, item):
    client.post("/items", json={"sku": "INACTIVE", "name": "Old"})
    client.put("/items/2", json={"active": False})
    body = client.get("/items", params={"active": "true", "limit": 1}).json()
    assert body["total"] == 1
    assert [i["sku"] for i in body["items"]] == ["WIDGET-1"]


def test_list_items_offset_past_end_empty_items_but_total_set(client):
    for n in range(2):
        client.post("/items", json={"sku": f"O{n}", "name": f"O{n}"})
    body = client.get("/items", params={"offset": 10}).json()
    assert body["items"] == []
    assert body["total"] == 2


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
    r = client.delete("/items/42")
    assert r.status_code == 404
    assert r.json()["error"]["message"] == "item 42 not found"


def test_delete_item_twice_second_returns_404(client, item):
    assert client.delete(f"/items/{item['id']}").status_code == 204
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 404
    assert r.json()["error"]["message"] == f"item {item['id']} not found"


def test_delete_item_cascades_stock(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_a["id"]},
    )
    # ship everything back out so the item is at zero stock and can be deleted
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    )
    assert client.delete(f"/items/{item['id']}").status_code == 204
    assert client.get("/movements").json() == []


# --- reorder_level (renamed from reorder_point) ---------------------------------


def test_create_item_accepts_reorder_level(client):
    r = client.post("/items", json={"sku": "RL-1", "name": "Reorderable", "reorder_level": 7})
    assert r.status_code == 201
    body = r.json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body
    # persisted and returned on GET
    body = client.get(f"/items/{body['id']}").json()
    assert body["reorder_level"] == 7
    assert "reorder_point" not in body


def test_create_item_with_legacy_reorder_point_returns_422(client):
    r = client.post("/items", json={"sku": "RP-1", "name": "Legacy", "reorder_point": 7})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    # nothing was created
    assert client.get("/items").json()["items"] == []


def test_update_item_with_legacy_reorder_point_returns_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_point": 9})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    # item unchanged
    assert client.get(f"/items/{item['id']}").json() == item


def test_update_item_accepts_reorder_level_field(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 9})
    assert r.status_code == 200
    assert "reorder_point" not in r.json()


def test_items_table_uses_reorder_level_column(tmp_path):
    from inventory import db as db_module

    path = str(tmp_path / "schema.db")
    db_module.init_db(path)
    conn = db_module.connect(path)
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
    finally:
        conn.close()
    assert "reorder_level" in cols
    assert "reorder_point" not in cols


def test_legacy_reorder_point_column_is_migrated(tmp_path):
    import sqlite3

    from inventory import db as db_module

    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            unit_price REAL NOT NULL DEFAULT 0,
            reorder_point INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            barcode TEXT UNIQUE
        )
        """
    )
    conn.execute("INSERT INTO items (sku, name, reorder_point) VALUES ('OLD-1', 'Old', 4)")
    conn.commit()
    conn.close()

    db_module.init_db(path)
    conn = db_module.connect(path)
    try:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
        row = conn.execute("SELECT reorder_level FROM items WHERE sku = 'OLD-1'").fetchone()
    finally:
        conn.close()
    assert "reorder_level" in cols
    assert "reorder_point" not in cols
    assert row["reorder_level"] == 4


def test_delete_item_with_stock_conflicts(client, item, loc_a):
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 7, "to_location_id": loc_a["id"]},
    )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "7" in body["error"]["message"]
    # item still exists
    assert client.get(f"/items/{item['id']}").status_code == 200


def test_delete_item_with_stock_detail_mentions_remaining_quantity(client, item, loc_a, loc_b):
    for loc, qty in ((loc_a, 2), (loc_b, 3)):
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    r = client.delete(f"/items/{item['id']}")
    assert r.status_code == 409
    # total across all locations is reported
    assert "5" in r.json()["error"]["message"]


def test_delete_item_after_stock_drained_succeeds(client, item, loc_a):
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


# --- barcode -------------------------------------------------------------------


def test_create_item_without_barcode_defaults_to_null(client):
    r = client.post("/items", json={"sku": "NB-1", "name": "No Barcode"})
    assert r.status_code == 201
    assert r.json()["barcode"] is None


def test_create_item_with_barcode(client):
    r = client.post("/items", json={"sku": "BC-1", "name": "Barcoded", "barcode": "123456789"})
    assert r.status_code == 201
    assert r.json()["barcode"] == "123456789"
    # persisted and returned on GET
    r = client.get(f"/items/{r.json()['id']}")
    assert r.json()["barcode"] == "123456789"


def test_duplicate_barcode_conflicts(client):
    r = client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "DUP-CODE"})
    assert r.status_code == 201
    r = client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "DUP-CODE"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "conflict"
    assert "barcode" in body["error"]["message"]


def test_multiple_items_without_barcode_allowed(client):
    assert client.post("/items", json={"sku": "N1", "name": "n1"}).status_code == 201
    assert client.post("/items", json={"sku": "N2", "name": "n2"}).status_code == 201
    assert client.post("/items", json={"sku": "N3", "name": "n3", "barcode": None}).status_code == 201


def test_list_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "CODE-1"})
    client.post("/items", json={"sku": "F2", "name": "f2", "barcode": "CODE-2"})
    client.post("/items", json={"sku": "F3", "name": "f3"})
    r = client.get("/items", params={"barcode": "CODE-2"})
    assert r.status_code == 200
    body = r.json()["items"]
    assert len(body) == 1
    assert body[0]["sku"] == "F2"
    assert body[0]["barcode"] == "CODE-2"


def test_list_items_filter_by_unknown_barcode_returns_empty(client):
    client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "CODE-1"})
    r = client.get("/items", params={"barcode": "NOPE"})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_list_items_filter_barcode_combined_with_active(client):
    client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "CODE-1"})
    client.put("/items/1", json={"active": False})
    assert (
        client.get("/items", params={"barcode": "CODE-1", "active": "true"}).json()["items"] == []
    )
    r = client.get("/items", params={"barcode": "CODE-1", "active": "false"})
    assert [i["sku"] for i in r.json()["items"]] == ["F1"]


# --- sku filter ------------------------------------------------------------------


def test_list_items_filter_by_sku_exact_match(client, item):
    client.post("/items", json={"sku": "WIDGET-2", "name": "Widget Two"})
    client.post("/items", json={"sku": "GADGET-1", "name": "Gadget"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert r.status_code == 200
    body = r.json()["items"]
    assert len(body) == 1
    assert body[0]["sku"] == "WIDGET-1"


def test_list_items_filter_by_sku_is_exact_not_prefix(client, item):
    # "WIDGET-1" must not match "WIDGET-10" or "WIDGET" partially
    client.post("/items", json={"sku": "WIDGET-10", "name": "Widget Ten"})
    r = client.get("/items", params={"sku": "WIDGET-1"})
    assert [i["sku"] for i in r.json()["items"]] == ["WIDGET-1"]
    r = client.get("/items", params={"sku": "WIDGET"})
    assert r.json()["items"] == []


def test_list_items_filter_by_unknown_sku_returns_empty_list_200(client, item):
    r = client.get("/items", params={"sku": "NO-SUCH-SKU"})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0


def test_list_items_filter_sku_combined_with_active(client, item):
    client.put(f"/items/{item['id']}", json={"active": False})
    assert (
        client.get("/items", params={"sku": "WIDGET-1", "active": "true"}).json()["items"] == []
    )
    r = client.get("/items", params={"sku": "WIDGET-1", "active": "false"})
    assert [i["sku"] for i in r.json()["items"]] == ["WIDGET-1"]


# --- description length --------------------------------------------------------


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
    # item unchanged
    assert client.get(f"/items/{item['id']}").json() == item


def test_update_item_description_at_limit_ok(client, item):
    r = client.put(f"/items/{item['id']}", json={"description": "x" * 2000})
    assert r.status_code == 200
    assert r.json()["description"] == "x" * 2000


def test_create_item_negative_reorder_level_422(client):
    r = client.post(
        "/items",
        json={"sku": "NEG-1", "name": "Neg", "reorder_level": -1},
    )
    assert r.status_code == 422


def test_create_item_zero_reorder_level_ok(client):
    r = client.post(
        "/items",
        json={"sku": "ZERO-1", "name": "Zero", "reorder_level": 0},
    )
    assert r.status_code == 201
    assert r.json()["reorder_level"] == 0


def test_create_item_with_barcode_and_negative_reorder_level_422(client):
    # Both merged features must coexist: barcode is accepted as a field,
    # but a negative reorder_level is still rejected with 422.
    r = client.post(
        "/items",
        json={"sku": "BC-NEG", "name": "Neg", "barcode": "BC-123", "reorder_level": -1},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_update_item_negative_reorder_level_422(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": -5})
    assert r.status_code == 422
    # item unchanged
    assert client.get(f"/items/{item['id']}").json() == item


def test_update_item_nonnegative_reorder_level_not_rejected(client, item):
    # Non-negative reorder_level values must pass validation (no 422).
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 7})
    assert r.status_code == 200


# --- T004: PUT /items/{id} must persist the reorder field (reorder_level, the
# --- renamed reorder_point) instead of silently ignoring it ----------------------


def test_update_item_reorder_level_persists_and_is_returned(client, item):
    r = client.put(f"/items/{item['id']}", json={"reorder_level": 12})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 12
    # persisted: visible on a subsequent GET, not just echoed back
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 12


def test_update_item_reorder_level_together_with_other_fields(client, item):
    r = client.put(
        f"/items/{item['id']}",
        json={"reorder_level": 3, "name": "Renamed", "unit_price": 4.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reorder_level"] == 3
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 4.5
    body = client.get(f"/items/{item['id']}").json()
    assert body["reorder_level"] == 3
    assert body["name"] == "Renamed"
    assert body["unit_price"] == 4.5


def test_update_item_omitting_reorder_level_leaves_value_untouched(client, item):
    # item fixture is created with reorder_level=5
    assert item["reorder_level"] == 5
    r = client.put(f"/items/{item['id']}", json={"name": "Still Widget"})
    assert r.status_code == 200
    assert r.json()["reorder_level"] == 5
    assert client.get(f"/items/{item['id']}").json()["reorder_level"] == 5


# --- T021: sort parameter for GET /items -----------------------------------------


def _make_sortable_items(client):
    # Insert out of order so sort behaviour is distinguishable from insert order.
    client.post("/items", json={"sku": "M-2", "name": "Charlie"})  # id 1
    client.post("/items", json={"sku": "M-3", "name": "Alpha"})  # id 2
    client.post("/items", json={"sku": "M-1", "name": "Bravo"})  # id 3


def test_list_items_default_sort_is_id_ascending(client):
    _make_sortable_items(client)
    r = client.get("/items")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_id_explicit(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [1, 2, 3]


def test_list_items_sort_by_name_ascending(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Alpha", "Bravo", "Charlie"]


def test_list_items_sort_by_sku_ascending(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["M-1", "M-2", "M-3"]


def test_list_items_sort_by_name_descending(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "-name"})
    assert r.status_code == 200
    assert [i["name"] for i in r.json()["items"]] == ["Charlie", "Bravo", "Alpha"]


def test_list_items_sort_by_sku_descending(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "-sku"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()["items"]] == ["M-3", "M-2", "M-1"]


def test_list_items_sort_by_id_descending(client):
    _make_sortable_items(client)
    r = client.get("/items", params={"sort": "-id"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["items"]] == [3, 2, 1]


def test_list_items_invalid_sort_value_422(client):
    _make_sortable_items(client)
    for bad in ["price", "name; DROP TABLE items", "--name", "", "ID", "-unknown"]:
        r = client.get("/items", params={"sort": bad})
        assert r.status_code == 422, bad


def test_list_items_sort_combines_with_filters_and_pagination(client):
    _make_sortable_items(client)
    client.put("/items/1", json={"active": False})
    r = client.get("/items", params={"sort": "-name", "active": "true", "limit": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert [i["name"] for i in body["items"]] == ["Bravo"]
