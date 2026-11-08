"""Hidden scoring test for T011."""
from tests.scoring.conftest import mk_item


def test_get_item_by_sku(sclient):
    item = mk_item(sclient, sku="BOLT-M8", name="Bolt")
    r = sclient.get("/items/by-sku/BOLT-M8")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == item["id"]
    r = sclient.get("/items/by-sku/NOPE")
    assert r.status_code == 404
    assert "NOPE" in r.text
    assert sclient.get(f"/items/{item['id']}").status_code == 200
