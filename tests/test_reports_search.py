"""Reports and search."""


def _seed(client, sku, name, reorder, qty, loc, price=1.0):
    item = client.post(
        "/items", json={"sku": sku, "name": name, "reorder_level": reorder, "unit_price": price}
    ).json()
    if qty:
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    return item


def test_low_stock_lists_items_below_reorder_level(client, loc_a):
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
        "reorder_level": 5,
        "shortfall": 3,
    }


def test_low_stock_includes_items_exactly_at_reorder_level(client, loc_a):
    _seed(client, "EXACT", "Exact", reorder=5, qty=5, loc=loc_a)
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["EXACT"]
    assert entries[0]["total_qty"] == 5
    assert entries[0]["reorder_level"] == 5


def test_low_stock_includes_zero_reorder_level_with_zero_stock(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["ZERO"]


def test_low_stock_excludes_items_strictly_above_reorder_level(client, loc_a):
    _seed(client, "ABOVE", "Above", reorder=5, qty=6, loc=loc_a)
    assert client.get("/reports/low-stock").json() == []


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


def test_low_stock_shortfall_is_reorder_level_minus_total_qty(client, loc_a):
    _seed(client, "SHORT", "Short", reorder=10, qty=3, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["SHORT"]
    assert entries[0]["shortfall"] == 7


def test_low_stock_shortfall_zero_when_exactly_at_reorder_level(client, loc_a):
    _seed(client, "EXACT", "Exact", reorder=4, qty=4, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["shortfall"] == 0


def test_low_stock_shortfall_never_negative(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["ZERO"]
    assert all(e["shortfall"] >= 0 for e in entries)
    assert entries[0]["shortfall"] == 0


def test_low_stock_shortfall_with_no_stock_equals_reorder_level(client, loc_a):
    _seed(client, "NONE", "Nothing", reorder=8, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["shortfall"] == 8


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


def test_search_by_description_substring(client):
    client.post("/items", json={"sku": "D1", "name": "Hammer", "description": "foo grade steel"})
    client.post("/items", json={"sku": "D2", "name": "Chisel", "description": "plain steel"})
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["D1"]


def test_search_no_duplicates_when_all_fields_match(client):
    client.post(
        "/items",
        json={"sku": "foo-1", "name": "foo thing", "description": "a foo for everything"},
    )
    results = client.get("/search", params={"q": "foo"}).json()
    assert [i["sku"] for i in results] == ["foo-1"]


def test_search_description_matches_keep_name_ordering(client):
    client.post("/items", json={"sku": "M1", "name": "Zeta", "description": "has foo inside"})
    client.post("/items", json={"sku": "M2", "name": "Alpha foo"})
    client.post("/items", json={"sku": "M3", "name": "Mid", "description": "also foo here"})
    names = [i["name"] for i in client.get("/search", params={"q": "foo"}).json()]
    assert names == ["Alpha foo", "Mid", "Zeta"]


def test_search_name_is_case_insensitive(client):
    client.post("/items", json={"sku": "S1", "name": "Blue Widget"})
    client.post("/items", json={"sku": "S2", "name": "Red Gadget"})
    for q in ("widget", "WIDGET", "Widget", "wIdGeT"):
        r = client.get("/search", params={"q": q})
        assert r.status_code == 200
        assert [i["sku"] for i in r.json()] == ["S1"], q


def test_search_sku_is_case_insensitive(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    for q in ("bolt", "BOLT", "Bolt"):
        assert [i["sku"] for i in client.get("/search", params={"q": q}).json()] == ["BOLT-M8"], q


def test_search_description_is_case_insensitive(client):
    client.post("/items", json={"sku": "D1", "name": "Hammer", "description": "Foo grade steel"})
    client.post("/items", json={"sku": "D2", "name": "Chisel", "description": "plain steel"})
    assert [i["sku"] for i in client.get("/search", params={"q": "FOO"}).json()] == ["D1"]


def test_search_case_insensitive_keeps_ordering_and_limit(client):
    for n, name in enumerate(["cable C", "CABLE A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "cAbLe", "limit": 2}).json()]
    assert names == ["CABLE A", "Cable B"]


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422
