"""Hidden scoring test for T002."""
from tests.scoring.conftest import mk_item, mk_loc, receive


def _item_with_reorder(client, sku, n):
    r = client.post("/items", json={"sku": sku, "name": sku, "reorder_point": n})
    if r.status_code == 422:  # after T049 the field is called reorder_level
        r = client.post("/items", json={"sku": sku, "name": sku, "reorder_level": n})
    assert r.status_code == 201, r.text
    return r.json()


def test_low_stock_includes_item_at_reorder_point(sclient):
    loc = mk_loc(sclient)
    at = _item_with_reorder(sclient, "AT", 5)
    receive(sclient, at["id"], loc["id"], 5)
    mk_item(sclient, sku="ZERO", name="Zero")  # reorder 0, stock 0 -> included
    above = _item_with_reorder(sclient, "ABOVE", 1)
    receive(sclient, above["id"], loc["id"], 2)
    skus = [e["sku"] for e in sclient.get("/reports/low-stock").json()]
    assert skus == ["AT", "ZERO"]
