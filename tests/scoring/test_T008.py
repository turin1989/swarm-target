"""Hidden scoring test for T008."""
from tests.scoring.conftest import mk_item


def test_negative_unit_price_rejected(sclient):
    assert sclient.post("/items", json={"sku": "N", "name": "n", "unit_price": -1}).status_code == 422
    assert sclient.post("/items", json={"sku": "Z", "name": "z", "unit_price": 0}).status_code == 201
    item = mk_item(sclient, sku="U")
    assert sclient.put(f"/items/{item['id']}", json={"unit_price": -0.5}).status_code == 422
    assert sclient.get(f"/items/{item['id']}").json()["unit_price"] == 0
