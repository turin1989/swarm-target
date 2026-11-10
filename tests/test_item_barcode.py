"""Optional unique barcode on items (T025)."""


def test_create_item_without_barcode_defaults_to_null(client):
    r = client.post("/items", json={"sku": "NO-BC", "name": "No Barcode"})
    assert r.status_code == 201
    assert r.json()["barcode"] is None


def test_create_item_with_barcode_roundtrips(client):
    r = client.post(
        "/items", json={"sku": "BC-1", "name": "Barcoded", "barcode": "0123456789012"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["barcode"] == "0123456789012"
    # persisted and returned on GET
    r = client.get(f"/items/{body['id']}")
    assert r.status_code == 200
    assert r.json()["barcode"] == "0123456789012"


def test_duplicate_barcode_conflicts_409(client):
    r = client.post("/items", json={"sku": "BC-1", "name": "One", "barcode": "DUP-123"})
    assert r.status_code == 201
    r = client.post("/items", json={"sku": "BC-2", "name": "Two", "barcode": "DUP-123"})
    assert r.status_code == 409
    assert "DUP-123" in r.json()["detail"]


def test_multiple_items_without_barcode_are_allowed(client):
    assert client.post("/items", json={"sku": "N1", "name": "n1"}).status_code == 201
    assert client.post("/items", json={"sku": "N2", "name": "n2"}).status_code == 201
    assert client.post(
        "/items", json={"sku": "N3", "name": "n3", "barcode": None}
    ).status_code == 201


def test_list_items_filter_by_barcode(client):
    client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "BC-AAA"})
    client.post("/items", json={"sku": "F2", "name": "f2", "barcode": "BC-BBB"})
    client.post("/items", json={"sku": "F3", "name": "f3"})
    r = client.get("/items", params={"barcode": "BC-BBB"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["sku"] == "F2"
    assert items[0]["barcode"] == "BC-BBB"


def test_list_items_filter_by_unknown_barcode_returns_empty(client):
    client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "BC-AAA"})
    r = client.get("/items", params={"barcode": "NOPE"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_items_barcode_filter_combines_with_active(client):
    r = client.post("/items", json={"sku": "F1", "name": "f1", "barcode": "BC-AAA"})
    item_id = r.json()["id"]
    client.put(f"/items/{item_id}", json={"active": False})
    assert client.get("/items", params={"barcode": "BC-AAA", "active": "true"}).json() == []
    got = client.get("/items", params={"barcode": "BC-AAA", "active": "false"}).json()
    assert [i["sku"] for i in got] == ["F1"]


def test_item_with_barcode_also_has_created_at(client):
    """Merged behaviour: barcode (T025) and created_at (T020) coexist on items."""
    import re

    r = client.post(
        "/items", json={"sku": "BC-TS", "name": "Both", "barcode": "BC-WITH-TS"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["barcode"] == "BC-WITH-TS"
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", body["created_at"])
    # both fields persist on GET
    r = client.get(f"/items/{body['id']}")
    got = r.json()
    assert got["barcode"] == "BC-WITH-TS"
    assert got["created_at"] == body["created_at"]


def test_duplicate_sku_still_reports_sku_conflict(client):
    client.post("/items", json={"sku": "SAME", "name": "a", "barcode": "X-1"})
    r = client.post("/items", json={"sku": "SAME", "name": "b", "barcode": "X-2"})
    assert r.status_code == 409
    assert "SAME" in r.json()["detail"]
