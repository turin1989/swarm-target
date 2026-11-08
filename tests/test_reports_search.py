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
    }


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


def test_low_stock_scoped_to_location(client, loc_a, loc_b):
    # 2 units in A + 4 in B = 6 total, above reorder point of 5
    item = _seed(client, "SPLIT", "Split", reorder=5, qty=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    )
    # unscoped: not low
    assert client.get("/reports/low-stock").json() == []
    # scoped to A: only 2 counted -> low
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["total_qty"] == 2
    # scoped to B: 4 counted -> still low
    entries_b = client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json()
    assert [e["sku"] for e in entries_b] == ["SPLIT"]
    assert entries_b[0]["total_qty"] == 4


def test_low_stock_scoped_counts_zero_for_items_without_stock_at_location(client, loc_a, loc_b):
    _seed(client, "ONLY-A", "Only A", reorder=5, qty=10, loc=loc_a)
    entries = client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json()
    assert [e["sku"] for e in entries] == ["ONLY-A"]
    assert entries[0]["total_qty"] == 0


def test_low_stock_unknown_location_returns_404(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, qty=2, loc=loc_a)
    r = client.get("/reports/low-stock", params={"location_id": 999})
    assert r.status_code == 404


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_a, price=10.0)
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
