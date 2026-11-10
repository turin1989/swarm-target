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
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["ZERO"]


def test_low_stock_excludes_items_strictly_above_reorder_point(client, loc_a):
    _seed(client, "ABOVE", "Above", reorder=5, qty=6, loc=loc_a)
    _seed(client, "ZABOVE", "ZeroAbove", reorder=0, qty=1, loc=loc_a)
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


def test_low_stock_shortfall_is_reorder_point_minus_total_qty(client, loc_a):
    _seed(client, "SHORT", "Short", reorder=10, qty=3, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["shortfall"] == 7


def test_low_stock_shortfall_with_no_stock_equals_reorder_point(client, loc_a):
    _seed(client, "EMPTY", "Empty", reorder=4, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["shortfall"] == 4


def test_low_stock_shortfall_is_never_negative(client, loc_a):
    _seed(client, "EXACT", "Exact", reorder=5, qty=5, loc=loc_a)
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert all(e["shortfall"] >= 0 for e in entries)
    assert {e["sku"]: e["shortfall"] for e in entries} == {"EXACT": 0, "ZERO": 0}


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_a, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_inventory_value_filtered_by_location(client, loc_a, loc_b):
    item_a = _seed(client, "V1", "v1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "V2", "v2", reorder=0, qty=1, loc=loc_b, price=10.0)
    # also receive some of item_a at loc_b to ensure per-location split
    client.post(
        "/movements",
        json={"item_id": item_a["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    )
    r = client.get("/reports/value", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 6.0}
    r = client.get("/reports/value", params={"location_id": loc_b["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 18.0}


def test_inventory_value_unknown_location_returns_404(client, loc_a):
    _seed(client, "V3", "v3", reorder=0, qty=1, loc=loc_a, price=5.0)
    r = client.get("/reports/value", params={"location_id": 9999})
    assert r.status_code == 404


def test_inventory_value_without_location_param_unchanged(client, loc_a, loc_b):
    _seed(client, "V4", "v4", reorder=0, qty=2, loc=loc_a, price=3.0)
    _seed(client, "V5", "v5", reorder=0, qty=1, loc=loc_b, price=4.0)
    r = client.get("/reports/value")
    assert r.status_code == 200
    assert r.json() == {"value": 10.0}


def test_inventory_value_empty_location_is_zero(client, loc_a, loc_b):
    _seed(client, "V6", "v6", reorder=0, qty=2, loc=loc_a, price=3.0)
    r = client.get("/reports/value", params={"location_id": loc_b["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 0.0}


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
    client.post(
        "/items",
        json={"sku": "D1", "name": "Hammer", "description": "heavy foo tool"},
    )
    client.post(
        "/items",
        json={"sku": "D2", "name": "Saw", "description": "cutting tool"},
    )
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["D1"]


def test_search_no_duplicates_when_all_fields_match(client):
    client.post(
        "/items",
        json={"sku": "foo-1", "name": "foo thing", "description": "a foo item"},
    )
    results = client.get("/search", params={"q": "foo"}).json()
    assert [i["sku"] for i in results] == ["foo-1"]


def test_search_description_matches_keep_name_ordering(client):
    client.post("/items", json={"sku": "M1", "name": "Zeta", "description": "foo"})
    client.post("/items", json={"sku": "M2", "name": "Alpha foo"})
    client.post("/items", json={"sku": "foo-3", "name": "Mid"})
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
    client.post(
        "/items",
        json={"sku": "D1", "name": "Hammer", "description": "Heavy FOO tool"},
    )
    client.post(
        "/items",
        json={"sku": "D2", "name": "Saw", "description": "cutting tool"},
    )
    assert [i["sku"] for i in client.get("/search", params={"q": "foo"}).json()] == ["D1"]


def test_search_case_insensitive_keeps_name_ordering_and_limit(client):
    for n, name in enumerate(["cable C", "CABLE A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "cAbLe", "limit": 2}).json()]
    assert names == ["CABLE A", "Cable B"]


def test_search_does_not_treat_percent_or_underscore_as_wildcards(client):
    client.post("/items", json={"sku": "W1", "name": "100% Cotton"})
    client.post("/items", json={"sku": "W2", "name": "100x Cotton"})
    client.post("/items", json={"sku": "W_3", "name": "Underscore"})
    client.post("/items", json={"sku": "WX3", "name": "NoUnderscore"})
    assert [i["sku"] for i in client.get("/search", params={"q": "100%"}).json()] == ["W1"]
    assert [i["sku"] for i in client.get("/search", params={"q": "W_3"}).json()] == ["W_3"]


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_search_trims_surrounding_whitespace(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    r = client.get("/search", params={"q": "  Bolt "})
    assert r.status_code == 200
    trimmed = client.get("/search", params={"q": "Bolt"})
    assert r.json() == trimmed.json()
    assert [i["sku"] for i in r.json()] == ["BOLT-M8"]


def test_search_query_longer_than_100_chars_rejected(client):
    assert client.get("/search", params={"q": "x" * 101}).status_code == 422


def test_search_query_of_exactly_100_chars_accepted(client):
    r = client.get("/search", params={"q": "x" * 100})
    assert r.status_code == 200
    assert r.json() == []


def test_search_whitespace_only_query_rejected(client):
    assert client.get("/search", params={"q": "   "}).status_code == 422
    assert client.get("/search", params={"q": "\t\n "}).status_code == 422
