"""Tests for the optional unique item barcode (T025)."""


def _create(client, sku, **extra):
    payload = {"sku": sku, "name": f"Item {sku}"}
    payload.update(extra)
    return client.post("/items", json=payload)


def test_barcode_defaults_to_null(client):
    r = _create(client, "NOBAR-1")
    assert r.status_code == 201, r.text
    assert r.json()["barcode"] is None

    # It also round-trips as null on fetch.
    r2 = client.get(f"/items/{r.json()['id']}")
    assert r2.status_code == 200
    assert r2.json()["barcode"] is None


def test_create_item_with_barcode(client):
    r = _create(client, "BAR-1", barcode="0123456789012")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["barcode"] == "0123456789012"

    r2 = client.get(f"/items/{body['id']}")
    assert r2.status_code == 200
    assert r2.json()["barcode"] == "0123456789012"


def test_duplicate_barcode_returns_409(client):
    r1 = _create(client, "BAR-A", barcode="DUP-123")
    assert r1.status_code == 201, r1.text
    r2 = _create(client, "BAR-B", barcode="DUP-123")
    assert r2.status_code == 409, r2.text
    error = r2.json()["error"]
    assert error["code"] == "conflict"
    assert "barcode" in error["message"]
    assert "DUP-123" in error["message"]


def test_multiple_items_without_barcode_allowed(client):
    assert _create(client, "NULL-1").status_code == 201
    assert _create(client, "NULL-2").status_code == 201
    assert _create(client, "NULL-3", barcode=None).status_code == 201


def test_filter_items_by_barcode(client):
    _create(client, "F-1", barcode="BC-001")
    _create(client, "F-2", barcode="BC-002")
    _create(client, "F-3")

    r = client.get("/items", params={"barcode": "BC-002"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "F-2"
    assert body["items"][0]["barcode"] == "BC-002"


def test_filter_items_by_unknown_barcode_returns_empty(client):
    _create(client, "G-1", barcode="BC-100")
    r = client.get("/items", params={"barcode": "NO-SUCH"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_duplicate_sku_still_reports_sku_conflict(client):
    assert _create(client, "SAME-SKU").status_code == 201
    r = _create(client, "SAME-SKU")
    assert r.status_code == 409
    assert "sku" in r.json()["error"]["message"]
