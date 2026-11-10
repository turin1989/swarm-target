"""Reports and search."""


def _seed(client, sku, name, reorder, qty, loc, price=1.0):
    item = client.post(
        "/items", json={"sku": sku, "name": name, "reorder_point": reorder, "unit_price": price}
    ).json()
    if qty:
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    return item


def test_low_stock_lists_items_below_reorder_point(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, qty=2, loc=loc_a)
    _seed(client, "OK", "Fine", reorder=5, qty=10, loc=loc_a)
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


def test_low_stock_includes_items_exactly_at_reorder_point(client, loc_a):
    _seed(client, "EXACT", "Exact", reorder=5, qty=5, loc=loc_a)
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["EXACT"]
    assert entries[0]["total_qty"] == 5
    assert entries[0]["reorder_point"] == 5


def test_low_stock_includes_zero_reorder_point_with_zero_stock(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [(e["sku"], e["total_qty"], e["reorder_point"]) for e in entries] == [("ZERO", 0, 0)]


def test_low_stock_excludes_items_strictly_above_reorder_point(client, loc_a):
    _seed(client, "ABOVE", "Above", reorder=5, qty=6, loc=loc_a)
    _seed(client, "ZSTOCKED", "Stocked", reorder=0, qty=1, loc=loc_a)
    assert client.get("/reports/low-stock").json() == []


def test_low_stock_scoped_to_location_includes_exact_match(client, loc_a, loc_b):
    # 5 at A + 3 at B = 8 total (> 5), but exactly 5 at A (== reorder point)
    item = _seed(client, "EDGE", "Edge", reorder=5, qty=5, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_b["id"]},
    )
    assert client.get("/reports/low-stock").json() == []
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert [(e["sku"], e["total_qty"]) for e in r.json()] == [("EDGE", 5)]


def test_low_stock_includes_items_with_no_stock(client, loc_a):
    _seed(client, "NONE", "Nothing", reorder=1, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["NONE"]


def test_low_stock_excludes_inactive(client, loc_a):
    item = _seed(client, "GONE", "Gone", reorder=5, qty=0, loc=loc_a)
    client.put(f"/items/{item['id']}", json={"active": False})
    assert client.get("/reports/low-stock").json() == []


def test_low_stock_sorted_by_sku(client, loc_a):
    _seed(client, "Z", "z", reorder=1, qty=0, loc=loc_a)
    _seed(client, "A", "a", reorder=1, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["A", "Z"]


def test_low_stock_scoped_to_location_counts_only_that_location(client, loc_a, loc_b):
    # 2 at A + 4 at B = 6 total (>= 5), but only 2 at A (< 5)
    item = _seed(client, "SPLIT", "Split", reorder=5, qty=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    )
    # not low overall
    assert client.get("/reports/low-stock").json() == []
    # low when scoped to A
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["total_qty"] == 2
    # also low when scoped to B (4 < 5), counting only B's stock
    r = client.get("/reports/low-stock", params={"location_id": loc_b["id"]})
    assert [(e["sku"], e["total_qty"]) for e in r.json()] == [("SPLIT", 4)]


def test_low_stock_scoped_excludes_items_well_stocked_at_location(client, loc_a, loc_b):
    _seed(client, "FULL", "Full", reorder=5, qty=10, loc=loc_a)
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    assert r.json() == []
    # no stock at B, so it is low there
    r = client.get("/reports/low-stock", params={"location_id": loc_b["id"]})
    assert [(e["sku"], e["total_qty"]) for e in r.json()] == [("FULL", 0)]


def test_low_stock_unknown_location_returns_404(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, qty=2, loc=loc_a)
    r = client.get("/reports/low-stock", params={"location_id": 9999})
    assert r.status_code == 404


def test_low_stock_without_location_param_unchanged(client, loc_a, loc_b):
    item = _seed(client, "LOW", "Low", reorder=10, qty=3, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    )
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [(e["sku"], e["total_qty"]) for e in entries] == [("LOW", 7)]


def test_low_stock_shortfall_is_reorder_point_minus_total_qty(client, loc_a):
    _seed(client, "LOW", "Low", reorder=10, qty=3, loc=loc_a)
    _seed(client, "NONE", "Nothing", reorder=4, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [(e["sku"], e["shortfall"]) for e in entries] == [("LOW", 7), ("NONE", 4)]


def test_low_stock_shortfall_scoped_to_location(client, loc_a, loc_b):
    item = _seed(client, "SPLIT", "Split", reorder=5, qty=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    )
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert [(e["sku"], e["shortfall"]) for e in r.json()] == [("SPLIT", 3)]
    r = client.get("/reports/low-stock", params={"location_id": loc_b["id"]})
    assert [(e["sku"], e["shortfall"]) for e in r.json()] == [("SPLIT", 1)]


def test_low_stock_shortfall_never_negative(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, qty=2, loc=loc_a)
    _seed(client, "OK", "Fine", reorder=5, qty=10, loc=loc_a)
    for entry in client.get("/reports/low-stock").json():
        assert entry["shortfall"] >= 0


def test_low_stock_entry_model_rejects_negative_shortfall():
    import pytest
    from pydantic import ValidationError

    from inventory.models import LowStockEntry

    with pytest.raises(ValidationError):
        LowStockEntry(
            item_id=1, sku="X", name="x", total_qty=10, reorder_point=5, shortfall=-5
        )


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_a, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_inventory_value_scoped_to_location_sums_only_that_location(client, loc_a, loc_b):
    item = _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 5, "to_location_id": loc_b["id"]},
    )
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_b, price=10.0)
    r = client.get("/reports/value", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 6.0}
    r = client.get("/reports/value", params={"location_id": loc_b["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 20.0}


def test_inventory_value_location_with_no_stock_is_zero(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    r = client.get("/reports/value", params={"location_id": loc_b["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 0.0}


def test_inventory_value_unknown_location_returns_404(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    r = client.get("/reports/value", params={"location_id": 9999})
    assert r.status_code == 404


def test_inventory_value_without_location_param_unchanged(client, loc_a, loc_b):
    item = _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 1, "to_location_id": loc_b["id"]},
    )
    assert client.get("/reports/value").json() == {"value": 8.0}


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
