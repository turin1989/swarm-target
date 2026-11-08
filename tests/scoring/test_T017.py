"""Hidden scoring test for T017."""
from tests.scoring.conftest import mk_item


def test_sku_is_normalised(sclient):
    item = mk_item(sclient, sku="  abc-1 ", name="x")
    assert item["sku"] == "ABC-1"
    assert sclient.post("/items", json={"sku": "ABC-1", "name": "y"}).status_code == 409
    assert sclient.post("/items", json={"sku": "abc-1", "name": "y"}).status_code == 409
    assert sclient.post("/items", json={"sku": "   ", "name": "y"}).status_code == 422
