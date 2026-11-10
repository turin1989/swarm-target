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


def test_low_stock_shortfall_is_reorder_point_minus_total_qty(client, loc_a):
    _seed(client, "SF1", "sf1", reorder=10, qty=4, loc=loc_a)
    _seed(client, "SF2", "sf2", reorder=7, qty=0, loc=loc_a)
    entries = {e["sku"]: e for e in client.get("/reports/low-stock").json()}
    assert entries["SF1"]["shortfall"] == 6
    assert entries["SF2"]["shortfall"] == 7


def test_low_stock_shortfall_never_negative():
    """Even if data would yield a negative raw difference, shortfall is clamped to 0."""
    import sqlite3

    from inventory.services.reports import low_stock

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY, sku TEXT, name TEXT,
            reorder_point INTEGER, active INTEGER
        );
        CREATE TABLE stock_levels (item_id INTEGER, qty INTEGER);
        -- negative stock below a negative reorder point: raw difference is -3 - (-5) = 2,
        -- while a naive unsigned mishandling could go wrong; also check clamping path
        INSERT INTO items VALUES (1, 'NEG', 'neg', -3, 1);
        INSERT INTO stock_levels VALUES (1, -5);
        """
    )
    entries = low_stock(conn)
    assert len(entries) == 1
    assert entries[0].shortfall == 2
    assert all(e.shortfall >= 0 for e in entries)


def test_low_stock_shortfall_never_negative_via_api(client, loc_a):
    _seed(client, "N1", "n1", reorder=1, qty=0, loc=loc_a)
    _seed(client, "N2", "n2", reorder=100, qty=99, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries, "expected low-stock entries"
    assert all(e["shortfall"] >= 0 for e in entries)
    assert all(
        e["shortfall"] == max(0, e["reorder_point"] - e["total_qty"]) for e in entries
    )


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
