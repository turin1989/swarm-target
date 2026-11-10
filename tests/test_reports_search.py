"""Reports and search."""


def _seed(client, sku, name, reorder, quantity, loc, price=1.0):
    item = client.post(
        "/items", json={"sku": sku, "name": name, "reorder_point": reorder, "unit_price": price}
    ).json()
    if quantity:
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "quantity": quantity, "to_location_id": loc["id"]},
        )
    return item


def test_low_stock_lists_items_below_reorder_point(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, quantity=2, loc=loc_a)
    _seed(client, "OK", "Fine", reorder=5, quantity=10, loc=loc_a)
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["LOW"]
    assert entries[0] == {
        "item_id": 1,
        "sku": "LOW",
        "name": "Low",
        "total_qty": 2,
        "reorder_point": 5,
        "shortfall": 3,
    }


def test_low_stock_shortfall_is_reorder_point_minus_total_qty(client, loc_a):
    _seed(client, "SF1", "s1", reorder=10, quantity=4, loc=loc_a)
    _seed(client, "SF2", "s2", reorder=7, quantity=0, loc=loc_a)
    entries = {e["sku"]: e for e in client.get("/reports/low-stock").json()}
    assert entries["SF1"]["shortfall"] == 6
    assert entries["SF2"]["shortfall"] == 7


def test_low_stock_shortfall_never_negative(client, loc_a):
    # Items at or above their reorder point are excluded from the report,
    # so every reported shortfall must be strictly positive (never negative).
    _seed(client, "NEG", "neg", reorder=5, quantity=2, loc=loc_a)
    _seed(client, "FULL", "full", reorder=5, quantity=50, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["NEG"]
    assert all(e["shortfall"] >= 0 for e in entries)


def test_low_stock_entry_model_rejects_negative_shortfall():
    import pytest as _pytest
    from pydantic import ValidationError

    from inventory.models import LowStockEntry

    with _pytest.raises(ValidationError):
        LowStockEntry(
            item_id=1, sku="X", name="x", total_qty=10, reorder_point=5, shortfall=-5
        )


def test_low_stock_includes_items_with_no_stock(client, loc_a):
    _seed(client, "NONE", "Nothing", reorder=1, quantity=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["NONE"]


def test_low_stock_excludes_inactive(client, loc_a):
    item = _seed(client, "GONE", "Gone", reorder=5, quantity=0, loc=loc_a)
    client.put(f"/items/{item['id']}", json={"active": False})
    assert client.get("/reports/low-stock").json() == []


def test_low_stock_sorted_by_sku(client, loc_a):
    _seed(client, "Z", "z", reorder=1, quantity=0, loc=loc_a)
    _seed(client, "A", "a", reorder=1, quantity=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["A", "Z"]


def test_low_stock_scoped_to_location_counts_only_that_location(client, loc_a, loc_b):
    # 10 units total (above reorder point of 6), but only 2 at loc_a.
    item = _seed(client, "SPLIT", "Split", reorder=6, quantity=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 8, "to_location_id": loc_b["id"]},
    )

    # Globally not low on stock.
    assert client.get("/reports/low-stock").json() == []

    # Scoped to loc_a only the 2 units there count.
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["total_qty"] == 2
    assert entries[0]["shortfall"] == 4

    # Scoped to loc_b the 8 units there exceed the reorder point.
    assert client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json() == []


def test_low_stock_scoped_location_includes_items_with_no_stock_there(client, loc_a, loc_b):
    _seed(client, "ONLY-B", "OnlyB", reorder=3, quantity=5, loc=loc_b)
    entries = client.get("/reports/low-stock", params={"location_id": loc_a["id"]}).json()
    assert [e["sku"] for e in entries] == ["ONLY-B"]
    assert entries[0]["total_qty"] == 0
    assert entries[0]["shortfall"] == 3


def test_low_stock_unknown_location_returns_404(client, loc_a):
    _seed(client, "ANY", "Any", reorder=5, quantity=0, loc=loc_a)
    r = client.get("/reports/low-stock", params={"location_id": 9999})
    assert r.status_code == 404


def test_low_stock_without_location_param_unchanged(client, loc_a, loc_b):
    item = _seed(client, "GLOB", "Glob", reorder=10, quantity=3, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 4, "to_location_id": loc_b["id"]},
    )
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["GLOB"]
    assert entries[0]["total_qty"] == 7
    assert entries[0]["shortfall"] == 3


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, quantity=1, loc=loc_a, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_search_by_name_substring(client):
    client.post("/items", json={"sku": "S1", "name": "Blue Widget"})
    client.post("/items", json={"sku": "S2", "name": "Red Gadget"})
    r = client.get("/search", params={"q": "Widget"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["S1"]


def test_search_by_sku(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    assert [i["sku"] for i in client.get("/search", params={"q": "BOLT"}).json()] == ["BOLT-M8"]


def test_search_sorted_by_name_and_limited(client):
    for n, name in enumerate(["Cable C", "Cable A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "Cable", "limit": 2}).json()]
    assert names == ["Cable A", "Cable B"]


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422
