"""Hidden scoring test for T037."""
from tests.scoring.conftest import mk_item


def test_items_total_count_header(sclient):
    for n in range(5):
        mk_item(sclient, sku=f"S{n}", name="s")
    r = sclient.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert r.headers.get("x-total-count") == "5"
    sclient.put("/items/1", json={"active": False})
    r = sclient.get("/items", params={"active": "true", "limit": 1})
    assert r.headers.get("x-total-count") == "4"
