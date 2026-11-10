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
    _seed(client, "EDGE", "Edge", reorder=5, qty=5, loc=loc_a)
    _seed(client, "ABOVE", "Above", reorder=5, qty=6, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["EDGE"]
    assert entries[0]["total_qty"] == 5
    assert entries[0]["reorder_level"] == 5


def test_low_stock_includes_zero_reorder_level_with_zero_stock(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["ZERO"]


def test_low_stock_excludes_items_strictly_above_reorder_level(client, loc_a):
    _seed(client, "PLENTY", "Plenty", reorder=3, qty=4, loc=loc_a)
    assert client.get("/reports/low-stock").json() == []


def test_low_stock_includes_items_with_no_stock(client, loc_a):
    _seed(client, "NONE", "Nothing", reorder=1, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["NONE"]


def test_low_stock_excludes_inactive(client, loc_a):
    item = _seed(client, "GONE", "Gone", reorder=5, qty=0, loc=loc_a)
    client.put(f"/items/{item['id']}", json={"active": False})
    assert client.get("/reports/low-stock").json() == []


def test_low_stock_entries_expose_reorder_level_not_reorder_point(client, loc_a):
    _seed(client, "LOW", "Low", reorder=5, qty=2, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["reorder_level"] == 5
    assert "reorder_point" not in entries[0]


def test_low_stock_sorted_by_sku(client, loc_a):
    _seed(client, "Z", "z", reorder=1, qty=0, loc=loc_a)
    _seed(client, "A", "a", reorder=1, qty=0, loc=loc_a)
    assert [e["sku"] for e in client.get("/reports/low-stock").json()] == ["A", "Z"]


def test_low_stock_scoped_to_location_counts_only_that_location(client, loc_a, loc_b):
    # 2 at A + 10 at B = 12 total, above reorder point of 5; at A alone it is low.
    item = _seed(client, "SPLIT", "Split", reorder=5, qty=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 10, "to_location_id": loc_b["id"]},
    )
    # Globally not low-stock.
    assert client.get("/reports/low-stock").json() == []
    # Scoped to A: only the 2 units there count.
    r = client.get("/reports/low-stock", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    entries = r.json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["total_qty"] == 2
    # Scoped to B: 10 units there, not low.
    assert client.get("/reports/low-stock", params={"location_id": loc_b["id"]}).json() == []


def test_low_stock_scoped_to_location_item_with_no_stock_there(client, loc_a, loc_b):
    _seed(client, "ELSEWHERE", "Elsewhere", reorder=3, qty=5, loc=loc_b)
    entries = client.get("/reports/low-stock", params={"location_id": loc_a["id"]}).json()
    assert [e["sku"] for e in entries] == ["ELSEWHERE"]
    assert entries[0]["total_qty"] == 0


def test_low_stock_unknown_location_returns_404(client, loc_a):
    r = client.get("/reports/low-stock", params={"location_id": 9999})
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "9999" in body["error"]["message"]


def test_low_stock_scoped_to_location_exposes_reorder_level_not_reorder_point(
    client, loc_a, loc_b
):
    # The location-scoped report must also use the renamed field.
    _seed(client, "SCOPED", "Scoped", reorder=5, qty=2, loc=loc_a)
    entries = client.get("/reports/low-stock", params={"location_id": loc_a["id"]}).json()
    assert [e["sku"] for e in entries] == ["SCOPED"]
    assert entries[0]["reorder_level"] == 5
    assert "reorder_point" not in entries[0]


def test_low_stock_shortfall_is_reorder_level_minus_total_qty(client, loc_a):
    _seed(client, "SHORT", "Short", reorder=7, qty=2, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["SHORT"]
    assert entries[0]["shortfall"] == 5


def test_low_stock_shortfall_for_item_with_no_stock(client, loc_a):
    _seed(client, "EMPTY", "Empty", reorder=4, qty=0, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries[0]["shortfall"] == 4


def test_low_stock_shortfall_is_zero_at_exact_reorder_level(client, loc_a):
    # qty == reorder level -> included, but shortfall must be 0, never negative.
    _seed(client, "EXACT", "Exact", reorder=5, qty=5, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["EXACT"]
    assert entries[0]["shortfall"] == 0


def test_low_stock_shortfall_never_negative(client, loc_a):
    _seed(client, "ZERO", "Zero", reorder=0, qty=0, loc=loc_a)
    _seed(client, "EDGE", "Edge", reorder=3, qty=3, loc=loc_a)
    _seed(client, "LOW", "Low", reorder=9, qty=1, loc=loc_a)
    entries = client.get("/reports/low-stock").json()
    assert entries, "expected low-stock entries"
    for entry in entries:
        assert entry["shortfall"] >= 0
        assert entry["shortfall"] == max(
            0, entry["reorder_level"] - entry["total_qty"]
        )


def test_low_stock_scoped_to_location_includes_shortfall(client, loc_a, loc_b):
    item = _seed(client, "SPLIT", "Split", reorder=5, qty=2, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 10, "to_location_id": loc_b["id"]},
    )
    entries = client.get("/reports/low-stock", params={"location_id": loc_a["id"]}).json()
    assert [e["sku"] for e in entries] == ["SPLIT"]
    assert entries[0]["shortfall"] == 3


def test_low_stock_entry_model_rejects_negative_shortfall():
    import pytest
    from pydantic import ValidationError

    from inventory.models import LowStockEntry

    with pytest.raises(ValidationError):
        LowStockEntry(
            item_id=1,
            sku="X",
            name="x",
            total_qty=10,
            reorder_level=5,
            shortfall=-5,
        )


def test_low_stock_without_location_param_unchanged(client, loc_a, loc_b):
    # 3 at A + 3 at B = 6 total, which is at the reorder point of 6 -> included.
    item = _seed(client, "SUM", "Sum", reorder=6, qty=3, loc=loc_a)
    client.post(
        "/movements",
        json={"item_id": item["id"], "kind": "receive", "qty": 3, "to_location_id": loc_b["id"]},
    )
    entries = client.get("/reports/low-stock").json()
    assert [e["sku"] for e in entries] == ["SUM"]
    assert entries[0]["total_qty"] == 6


def test_inventory_value(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_a, price=10.0)
    assert client.get("/reports/value").json() == {"value": 16.0}


def test_inventory_value_filtered_by_location(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_b, price=10.0)
    r = client.get("/reports/value", params={"location_id": loc_a["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 6.0}
    r = client.get("/reports/value", params={"location_id": loc_b["id"]})
    assert r.status_code == 200
    assert r.json() == {"value": 10.0}


def test_inventory_value_unknown_location_returns_404(client, loc_a):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    r = client.get("/reports/value", params={"location_id": 9999})
    assert r.status_code == 404


def test_inventory_value_without_filter_unchanged(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
    _seed(client, "P2", "p2", reorder=0, qty=1, loc=loc_b, price=10.0)
    r = client.get("/reports/value")
    assert r.status_code == 200
    assert r.json() == {"value": 16.0}


def test_inventory_value_filtered_empty_location_is_zero(client, loc_a, loc_b):
    _seed(client, "P1", "p1", reorder=0, qty=3, loc=loc_a, price=2.0)
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


def test_search_by_name_is_case_insensitive(client):
    client.post("/items", json={"sku": "S1", "name": "Blue Widget"})
    client.post("/items", json={"sku": "S2", "name": "Red Gadget"})
    lower = client.get("/search", params={"q": "widget"})
    upper = client.get("/search", params={"q": "WIDGET"})
    title = client.get("/search", params={"q": "Widget"})
    assert lower.status_code == upper.status_code == title.status_code == 200
    assert [i["sku"] for i in lower.json()] == ["S1"]
    assert lower.json() == upper.json() == title.json()


def test_search_by_sku_is_case_insensitive(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "Nut"})
    lower = client.get("/search", params={"q": "bolt-m8"})
    upper = client.get("/search", params={"q": "BOLT-M8"})
    mixed = client.get("/search", params={"q": "BoLt-M8"})
    assert [i["sku"] for i in lower.json()] == ["BOLT-M8"]
    assert lower.json() == upper.json() == mixed.json()


def test_search_case_insensitive_keeps_order_and_limit(client):
    for n, name in enumerate(["Cable C", "Cable A", "Cable B"]):
        client.post("/items", json={"sku": f"C{n}", "name": name})
    names = [i["name"] for i in client.get("/search", params={"q": "cable", "limit": 2}).json()]
    assert names == ["Cable A", "Cable B"]


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422
    assert client.get("/search", params={"q": ""}).status_code == 422


def test_search_trims_surrounding_whitespace(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "Bolt"})
    trimmed = client.get("/search", params={"q": "Bolt"})
    padded = client.get("/search", params={"q": "  Bolt "})
    assert padded.status_code == 200
    assert padded.json() == trimmed.json()
    assert [i["sku"] for i in padded.json()] == ["BOLT-M8"]


def test_search_query_too_long_returns_422(client):
    assert client.get("/search", params={"q": "x" * 101}).status_code == 422


def test_search_query_at_max_length_is_accepted(client):
    r = client.get("/search", params={"q": "x" * 100})
    assert r.status_code == 200
    assert r.json() == []


def test_search_whitespace_only_query_returns_422(client):
    assert client.get("/search", params={"q": "   "}).status_code == 422


def test_search_matches_description_substring(client):
    client.post(
        "/items",
        json={"sku": "S1", "name": "Widget", "description": "contains foo inside"},
    )
    client.post(
        "/items",
        json={"sku": "S2", "name": "Gadget", "description": "nothing relevant"},
    )
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["S1"]


def test_search_description_is_case_insensitive(client):
    client.post(
        "/items",
        json={"sku": "S1", "name": "Widget", "description": "Premium FOO grade"},
    )
    lower = client.get("/search", params={"q": "foo"})
    upper = client.get("/search", params={"q": "FOO"})
    assert lower.status_code == upper.status_code == 200
    assert [i["sku"] for i in lower.json()] == ["S1"]
    assert lower.json() == upper.json()


def test_search_no_duplicates_when_sku_name_and_description_all_match(client):
    client.post(
        "/items",
        json={"sku": "FOO-1", "name": "foo thing", "description": "a foo item"},
    )
    r = client.get("/search", params={"q": "foo"})
    assert r.status_code == 200
    results = r.json()
    assert [i["sku"] for i in results] == ["FOO-1"]
    assert len(results) == 1


def test_search_description_matches_keep_name_ordering(client):
    client.post("/items", json={"sku": "D1", "name": "Zeta", "description": "has foo"})
    client.post("/items", json={"sku": "D2", "name": "Alpha", "description": "also foo"})
    client.post("/items", json={"sku": "D3", "name": "Mid foo name", "description": ""})
    names = [i["name"] for i in client.get("/search", params={"q": "foo"}).json()]
    assert names == ["Alpha", "Mid foo name", "Zeta"]


def test_search_description_only_match_does_not_leak_unrelated_items(client):
    client.post("/items", json={"sku": "A1", "name": "Anchor", "description": "steel foo bolt"})
    client.post("/items", json={"sku": "A2", "name": "Anchor 2", "description": "steel bolt"})
    assert [i["sku"] for i in client.get("/search", params={"q": "foo"}).json()] == ["A1"]
