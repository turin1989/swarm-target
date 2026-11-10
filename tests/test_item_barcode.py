"""Tests for the optional unique barcode on items (T025)."""


def _create(client, sku, **extra):
    return client.post("/items", json={"sku": sku, "name": f"Item {sku}", **extra})


def test_create_item_without_barcode_defaults_to_null(client):
    r = _create(client, "NOBAR-1")
    assert r.status_code == 201, r.text
    assert r.json()["barcode"] is None


def test_create_item_with_barcode_round_trips(client):
    r = _create(client, "BAR-1", barcode="0123456789012")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["barcode"] == "0123456789012"

    # Also visible on GET by id
    r = client.get(f"/items/{body['id']}")
    assert r.status_code == 200
    assert r.json()["barcode"] == "0123456789012"


def test_duplicate_barcode_returns_409(client):
    r = _create(client, "BAR-A", barcode="SAME-CODE")
    assert r.status_code == 201, r.text
    r = _create(client, "BAR-B", barcode="SAME-CODE")
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "conflict"
    assert "barcode" in error["message"]


def test_multiple_items_without_barcode_allowed(client):
    assert _create(client, "NULL-1").status_code == 201
    assert _create(client, "NULL-2").status_code == 201
    assert _create(client, "NULL-3", barcode=None).status_code == 201


def test_list_items_filter_by_barcode(client):
    _create(client, "FIL-1", barcode="CODE-1")
    _create(client, "FIL-2", barcode="CODE-2")
    _create(client, "FIL-3")

    r = client.get("/items", params={"barcode": "CODE-2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "FIL-2"
    assert body["items"][0]["barcode"] == "CODE-2"


def test_list_items_filter_by_unknown_barcode_returns_empty(client):
    _create(client, "FIL-4", barcode="CODE-4")
    r = client.get("/items", params={"barcode": "NOPE"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_bulk_create_supports_barcode_and_conflicts(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-1", "name": "Bulk 1", "barcode": "BULK-CODE-1"},
            {"sku": "BULK-2", "name": "Bulk 2"},
        ],
    )
    assert r.status_code == 201, r.text
    barcodes = {i["sku"]: i["barcode"] for i in r.json()}
    assert barcodes == {"BULK-1": "BULK-CODE-1", "BULK-2": None}

    r = client.post(
        "/items/bulk",
        json=[{"sku": "BULK-3", "name": "Bulk 3", "barcode": "BULK-CODE-1"}],
    )
    assert r.status_code == 409, r.text
    assert "barcode" in r.json()["error"]["message"]


def test_duplicate_sku_still_reports_sku_conflict(client):
    assert _create(client, "DUP-1", barcode="X-1").status_code == 201
    r = _create(client, "DUP-1", barcode="X-2")
    assert r.status_code == 409
    assert "sku" in r.json()["error"]["message"]
