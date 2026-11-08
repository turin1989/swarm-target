"""Hidden scoring test for T009."""
from tests.scoring.conftest import mk_item


def test_negative_reorder_point_rejected(sclient):
    item = mk_item(sclient, sku="K")
    key = "reorder_point" if "reorder_point" in item else "reorder_level"
    assert sclient.post("/items", json={"sku": "N", "name": "n", key: -1}).status_code == 422
    assert sclient.post("/items", json={"sku": "P", "name": "p", key: 1}).status_code == 201
    assert sclient.put(f"/items/{item['id']}", json={key: -3}).status_code == 422
