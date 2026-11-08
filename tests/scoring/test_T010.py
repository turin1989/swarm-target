"""Hidden scoring test for T010."""
from tests.scoring.conftest import mk_item


def _items(body):
    return body["items"] if isinstance(body, dict) else body


def test_filter_items_by_sku(sclient):
    mk_item(sclient, sku="AAA", name="a")
    mk_item(sclient, sku="BBB", name="b")
    r = sclient.get("/items", params={"sku": "BBB"})
    assert r.status_code == 200
    assert [i["sku"] for i in _items(r.json())] == ["BBB"]
    assert _items(sclient.get("/items", params={"sku": "NOPE"}).json()) == []
    assert _items(sclient.get("/items", params={"sku": "BBB", "active": "false"}).json()) == []
