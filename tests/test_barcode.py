"""Optional unique barcode on items (T025)."""


def test_barcode_defaults_to_null(client):
    r = client.post("/items", json={"sku": "NB-1", "name": "NoBarcode"})
    assert r.status_code == 201
    assert r.json()["barcode"] is None


def test_create_item_with_barcode(client):
    r = client.post(
        "/items", json={"sku": "BC-1", "name": "Barcoded", "barcode": "0123456789012"}
    )
    assert r.status_code == 201
    assert r.json()["barcode"] == "0123456789012"
    # persisted and returned by GET /items/{id}
    item_id = r.json()["id"]
    assert client.get(f"/items/{item_id}").json()["barcode"] == "0123456789012"


def test_duplicate_barcode_conflicts_409(client):
    r1 = client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "DUP-123"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "DUP-123"})
    assert r2.status_code == 409
    assert "DUP-123" in r2.json()["error"]["message"]
    # no partial insert
    skus = [i["sku"] for i in client.get("/items").json()]
    assert skus == ["BC-1"]


def test_multiple_items_without_barcode_allowed(client):
    assert client.post("/items", json={"sku": "N-1", "name": "A"}).status_code == 201
    assert client.post("/items", json={"sku": "N-2", "name": "B"}).status_code == 201
    assert (
        client.post("/items", json={"sku": "N-3", "name": "C", "barcode": None}).status_code
        == 201
    )


def test_get_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "F-1", "name": "One", "barcode": "BAR-1"})
    client.post("/items", json={"sku": "F-2", "name": "Two", "barcode": "BAR-2"})
    client.post("/items", json={"sku": "F-3", "name": "Three"})

    r = client.get("/items", params={"barcode": "BAR-2"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["sku"] == "F-2"
    assert body[0]["barcode"] == "BAR-2"


def test_get_items_filter_by_unknown_barcode_returns_empty(client):
    client.post("/items", json={"sku": "F-1", "name": "One", "barcode": "BAR-1"})
    r = client.get("/items", params={"barcode": "NOPE"})
    assert r.status_code == 200
    assert r.json() == []


def test_barcode_filter_combines_with_active(client):
    r = client.post("/items", json={"sku": "CA-1", "name": "One", "barcode": "COMBO"})
    item_id = r.json()["id"]
    client.put(f"/items/{item_id}", json={"active": False})
    assert client.get("/items", params={"barcode": "COMBO", "active": "true"}).json() == []
    found = client.get("/items", params={"barcode": "COMBO", "active": "false"}).json()
    assert [i["sku"] for i in found] == ["CA-1"]


def test_duplicate_sku_still_reports_sku_conflict(client, item):
    r = client.post("/items", json={"sku": item["sku"], "name": "Dup", "barcode": "UNIQUE-X"})
    assert r.status_code == 409
    assert "sku" in r.json()["error"]["message"]
