"""Tests for the optional unique barcode on items (T025)."""


def _create(client, sku, barcode=None, **extra):
    payload = {"sku": sku, "name": f"Item {sku}", **extra}
    if barcode is not None:
        payload["barcode"] = barcode
    return client.post("/items", json=payload)


def test_create_item_without_barcode_defaults_to_null(client):
    r = _create(client, "NOBAR-1")
    assert r.status_code == 201, r.text
    assert r.json()["barcode"] is None


def test_create_item_with_barcode_roundtrips(client):
    r = _create(client, "BAR-1", barcode="0123456789012")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["barcode"] == "0123456789012"

    # Also present when fetched back by id.
    got = client.get(f"/items/{body['id']}")
    assert got.status_code == 200
    assert got.json()["barcode"] == "0123456789012"


def test_duplicate_barcode_returns_409(client):
    r1 = _create(client, "BAR-A", barcode="DUP-CODE")
    assert r1.status_code == 201, r1.text
    r2 = _create(client, "BAR-B", barcode="DUP-CODE")
    assert r2.status_code == 409, r2.text
    assert r2.json()["error"]["code"] == "conflict"
    assert "barcode" in r2.json()["error"]["message"]


def test_multiple_items_with_null_barcode_allowed(client):
    r1 = _create(client, "NULL-1")
    r2 = _create(client, "NULL-2")
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    assert r1.json()["barcode"] is None
    assert r2.json()["barcode"] is None


def test_list_items_filters_by_barcode(client):
    _create(client, "F-1", barcode="CODE-1")
    _create(client, "F-2", barcode="CODE-2")
    _create(client, "F-3")

    r = client.get("/items", params={"barcode": "CODE-2"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "F-2"
    assert body["items"][0]["barcode"] == "CODE-2"


def test_list_items_filter_unknown_barcode_returns_empty(client):
    _create(client, "F-4", barcode="CODE-4")
    r = client.get("/items", params={"barcode": "NOPE"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_bulk_create_duplicate_barcode_rolls_back_with_409(client):
    r = client.post(
        "/items/bulk",
        json=[
            {"sku": "BULK-1", "name": "One", "barcode": "BULK-CODE"},
            {"sku": "BULK-2", "name": "Two", "barcode": "BULK-CODE"},
        ],
    )
    assert r.status_code == 409, r.text
    assert "barcode" in r.json()["error"]["message"]
    # Neither item was created.
    assert client.get("/items", params={"sku": "BULK-1"}).json()["total"] == 0
