"""Optional unique barcode on items (T025)."""


def test_create_item_without_barcode_defaults_null(client):
    r = client.post("/items", json={"sku": "NB-1", "name": "No Barcode"})
    assert r.status_code == 201
    assert r.json()["barcode"] is None


def test_create_item_with_barcode_round_trips(client):
    r = client.post(
        "/items", json={"sku": "BC-1", "name": "Barcoded", "barcode": "0123456789012"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["barcode"] == "0123456789012"
    # persisted: GET by id returns the same barcode
    assert client.get(f"/items/{body['id']}").json()["barcode"] == "0123456789012"


def test_duplicate_barcode_conflicts_409(client):
    r1 = client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "EAN-1"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "EAN-1"})
    assert r2.status_code == 409
    assert "barcode" in r2.json()["error"]["message"]


def test_duplicate_sku_still_409(client):
    assert client.post("/items", json={"sku": "S-1", "name": "A"}).status_code == 201
    r = client.post("/items", json={"sku": "S-1", "name": "B", "barcode": "UNIQ-1"})
    assert r.status_code == 409
    assert "sku" in r.json()["error"]["message"]


def test_multiple_null_barcodes_allowed(client):
    assert client.post("/items", json={"sku": "N-1", "name": "A"}).status_code == 201
    assert client.post("/items", json={"sku": "N-2", "name": "B"}).status_code == 201
    assert (
        client.post("/items", json={"sku": "N-3", "name": "C", "barcode": None}).status_code
        == 201
    )


def test_get_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "F-1", "name": "A", "barcode": "BAR-A"})
    client.post("/items", json={"sku": "F-2", "name": "B", "barcode": "BAR-B"})
    client.post("/items", json={"sku": "F-3", "name": "C"})
    r = client.get("/items", params={"barcode": "BAR-B"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert [i["sku"] for i in body["items"]] == ["F-2"]
    assert body["items"][0]["barcode"] == "BAR-B"


def test_get_items_filter_by_unknown_barcode_empty(client):
    client.post("/items", json={"sku": "F-1", "name": "A", "barcode": "BAR-A"})
    body = client.get("/items", params={"barcode": "NOPE"}).json()
    assert body["items"] == []
    assert body["total"] == 0


def test_barcode_filter_combines_with_active(client):
    client.post("/items", json={"sku": "C-1", "name": "A", "barcode": "BAR-X"})
    client.put("/items/1", json={"active": False})
    assert client.get("/items", params={"barcode": "BAR-X", "active": "true"}).json()[
        "items"
    ] == []
    inactive = client.get("/items", params={"barcode": "BAR-X", "active": "false"}).json()
    assert [i["sku"] for i in inactive["items"]] == ["C-1"]


def test_list_items_unfiltered_includes_barcode_field(client):
    client.post("/items", json={"sku": "L-1", "name": "A", "barcode": "BAR-L"})
    client.post("/items", json={"sku": "L-2", "name": "B"})
    items = client.get("/items").json()["items"]
    assert [i["barcode"] for i in items] == ["BAR-L", None]
