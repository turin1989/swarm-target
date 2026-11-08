"""Hidden scoring test for T044."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive


def test_filter_movements(sclient):
    i1, i2 = mk_item(sclient, sku="A"), mk_item(sclient, sku="B")
    loc = mk_loc(sclient)
    receive(sclient, i1["id"], loc["id"], 5)
    receive(sclient, i2["id"], loc["id"], 5)
    r = move(sclient, item_id=i1["id"], kind="ship", qty=1, quantity=1, from_location_id=loc["id"])
    assert r.status_code == 201, r.text
    assert [m["id"] for m in sclient.get("/movements", params={"item_id": i1["id"]}).json()] == [1, 3]
    assert [m["id"] for m in sclient.get("/movements", params={"kind": "ship"}).json()] == [3]
    assert sclient.get("/movements", params={"item_id": i2["id"], "kind": "ship"}).json() == []
    assert [m["id"] for m in sclient.get("/movements", params={"item_id": i1["id"], "limit": 1, "offset": 1}).json()] == [3]
    assert sclient.get("/movements", params={"kind": "bogus"}).status_code == 422
