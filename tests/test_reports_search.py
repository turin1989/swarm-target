"""Reports and search."""


def _seed(client, sku, name, reorder, quantity, loc, price=1.0):
    item = client.post(
        "/items", json={"sku": sku, "name": name, "reorder_level": reorder, "unit_price": price}
    ).json()
    if quantity:
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "quantity": quantity, "to_location_id": loc["id"]},
        )
    return item


def test_low_stock_lists_items_below_reorder_level(client, loc_a):
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
        "reorder_level": 5,
        "shortfall": 3,
    }


def test_low_stock_includes_items_exactly_at_reorder_level(client, loc_a):
    _seed(client, "EDGE", "Edge", reorder=5, quantity=5, loc=loc_a)
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["EDGE"]
    assert entries[0]["total_qty"] == 5
    assert entries[0]["reorder_level"] == 5


def test_low_stock_includes_zero_reorder_level_with_zero_stock(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, quantity=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["ZERO"]


def test_low_stock_excludes_items_strictly_above_reorder_level(client, loc_a):
    _seed(client, "ABOVE", "Above", reorder=5, quantity=6, loc=loc_a)
    assert client.get("/reports/low-stock").json() == []


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


def test_low_stock_shortfall_is_reorder_level_minus_total_qty(client, loc_a):
    _seed(client, "S1", "s1", reorder=10, quantity=4, loc=loc_a)
    _seed(client, "S2", "s2", reorder=7, quantity=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert {e["sku"]: e["shortfall"] for e in entries} == {"S1": 6, "S2": 7}


def test_low_stock_shortfall_never_negative(client, loc_a):
    # At the reorder point exactly, and with a zero reorder point,
    # the shortfall is 0 rather than negative.
    _seed(client, "EDGE", "Edge", reorder=5, quantity=5, loc=loc_a)
    _seed(client, "ZERO", "Zero", reorder=0, quantity=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert {e["sku"]: e["shortfall"] for e in entries} == {"EDGE": 0, "ZERO": 0}
    assert all(e["shortfall"] >= 0 for e in entries)


def test_low_stock_scoped_to_location_counts_only_that_location(client, loc_a, loc_b):
    # 2 units at A + 10 at B: fine overall, but low when scoped to A.
    item = _seed(client, "SPLIT", "Split", reorder=5, quantity=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_b["id"]},
    )
    # Plenty at A: never low when scoped to A.
    _seed(client, "OK-A", "Fine at A", reorder=5, quantity=10, loc=loc_a)

    scoped = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert scoped.status_code == 200
    entries = scoped.json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["total_qty"] == 2  # only stock at A counted
    assert entries[0]["shortfall"] == 3

    # Scoped to B, SPLIT has 10 units and is not low (OK-A has none at B, so it is).
    skus_at_b = [
        e["sku"]
        for e in client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json()
    ]
    assert "SPLIT" not in skus_at_b
    assert skus_at_b == ["OK-A"]


def test_low_stock_scoped_location_with_no_stock_counts_zero(client, loc_a, loc_b):
    _seed(client, "ONLY-A", "Only at A", reorder=5, quantity=10, loc=loc_a)
    entries = client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json()
    assert [e["sku"] for e in entries] == ["ONLY-A"]
    assert entries[0]["total_qty"] == 0
    assert entries[0]["shortfall"] == 5


def test_low_stock_unknown_location_returns_404(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, quantity=2, loc=loc_a)
    r = client.get("/reports/low-stock", params={"location_id": 999})
    assert r.status_code == 404


def test_low_stock_without_location_param_unchanged(client, loc_a, loc_b):
    # Totals are still summed across all locations without the parameter.
    item = _seed(client, "SPLIT", "Split", reorder=5, quantity=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "quantity": 10, "to_location_id": loc_b["id"]},
    )
    _seed(client, "LOW", "Low", reorder=5, quantity=1, loc=loc_a)
    r = client.get("/reports/low-stock")
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["LOW"]
    assert entries[0]["total_qty"] == 1


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, quantity=1, loc=loc_a, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_inventory_value_filtered_by_location(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, quantity=1, loc=loc_b, price=10.0)
    assert client.get("/reports/value", params={"location_id": loc_a["id"]}).json() == {
        "value": 6.0
    }
    assert client.get("/reports/value", params={"location_id": loc_b["id"]}).json() == {
        "value": 10.0
    }


def test_inventory_value_without_location_unchanged(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, quantity=1, loc=loc_b, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_inventory_value_unknown_location_returns_404(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    r = client.get("/reports/value", params={"location_id": 999})
    assert r.status_code == 404


def test_inventory_value_location_with_no_stock_is_zero(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, quantity=3, loc=loc_a, price=2.0)
    assert client.get("/reports/value", params={"location_id": loc_b["id"]}).json() == {
        "value": 0.0
    }


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


def test_search_by_name_is_case_insensitive(client):
    client.post("/items", json={"sku": "S1", "name": "Blue Widget"})
    client.post("/items", json={"sku": "S2", "name": "Red Gadget"})
    for q in ("widget", "WIDGET", "Widget"):
        r = client.get("/search", params={"q": q})
        assert r.status_code == 200
        assert [i["sku"] for i in r.json()] == ["S1"], q


def test_search_by_sku_is_case_insensitive(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    for q in ("bolt", "BOLT", "Bolt"):
        assert [i["sku"] for i in client.get("/search", params={"q": q}).json()] == ["BOLT-M8"], q


def test_search_case_insensitive_keeps_ordering_and_limit(client):
    for n, name in enumerate(["Cable C", "Cable A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "cable", "limit": 2}).json()]
    assert names == ["Cable A", "Cable B"]


def test_search_sorted_by_name_and_limited(client):
    for n, name in enumerate(["Cable C", "Cable A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "Cable", "limit": 2}).json()]
    assert names == ["Cable A", "Cable B"]


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_search_trims_leading_and_trailing_whitespace(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    r = client.get("/search", params={"q": "  bolt "})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["BOLT-M8"]
    # behaves exactly like the already-trimmed query
    assert r.json() == client.get("/search", params={"q": "bolt"}).json()


def test_search_query_longer_than_100_chars_returns_422(client):
    client.post("/items", json={"sku": "S1", "name": "Bolt"})
    assert client.get("/search", params={"q": "x" * 101}).status_code == 422
    # exactly 100 characters is still accepted
    assert client.get("/search", params={"q": "x" * 100}).status_code == 200


def test_search_whitespace_only_query_returns_422(client):
    client.post("/items", json={"sku": "S1", "name": "Bolt"})
    for q in (" ", "   ", "\t", " \t "):
        assert client.get("/search", params={"q": q}).status_code == 422, repr(q)


def test_search_by_description_substring(client):
    client.post(
        "/items",
        json={"sku": "S1", "name": "Blue Widget", "description": "contains foo inside"},
    )
    client.post(
        "/items",
        json={"sku": "S2", "name": "Red Gadget", "description": "nothing relevant"},
    )
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["S1"]


def test_search_by_description_is_case_insensitive(client):
    client.post(
        "/items", json={"sku": "S1", "name": "Blue Widget", "description": "Premium Foo grade"}
    )
    client.post("/items", json={"sku": "S2", "name": "Red Gadget", "description": "plain"})
    for q in ("foo", "FOO", "Foo"):
        assert [i["sku"] for i in client.get("/search", params={"q": q}).json()] == ["S1"], q


def test_search_no_duplicates_when_sku_name_and_description_all_match(client):
    client.post(
        "/items",
        json={"sku": "FOO-1", "name": "Foo Thing", "description": "a foo for everyone"},
    )
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["FOO-1"]


def test_search_description_matches_keep_name_ordering(client):
    client.post("/items", json={"sku": "D1", "name": "Zeta", "description": "has foo in it"})
    client.post("/items", json={"sku": "D2", "name": "Alpha", "description": "also foo here"})
    client.post("/items", json={"sku": "FOO-X", "name": "Mid", "description": ""})
    names = [i["name"] for i in client.get("/search", params={"q": "foo"}).json()]
    assert names == ["Alpha", "Mid", "Zeta"]
