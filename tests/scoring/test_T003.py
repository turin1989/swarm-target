"""Hidden scoring test for T003."""
from tests.scoring.conftest import mk_item, mk_loc, move, qty_key, receive


def test_transfer_moves_stock_between_locations(sclient):
    item = mk_item(sclient)
    a, b = mk_loc(sclient, "A"), mk_loc(sclient, "B")
    receive(sclient, item["id"], a["id"], 10)
    r = move(
        sclient, item_id=item["id"], kind="transfer", qty=4, quantity=4,
        from_location_id=a["id"], to_location_id=b["id"],
    )
    assert r.status_code == 201, r.text
    s = sclient.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 10
    k = qty_key(s["levels"][0])
    by_loc = {lvl["location_id"]: lvl[k] for lvl in s["levels"]}
    assert by_loc[a["id"]] == 6
    assert by_loc[b["id"]] == 4
