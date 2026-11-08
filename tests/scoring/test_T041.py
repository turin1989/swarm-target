"""Hidden scoring test for T041."""
from tests.scoring.conftest import mk_item, mk_loc, move, total


def test_movement_for_inactive_item_is_409(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    assert sclient.put(f"/items/{item['id']}", json={"active": False}).status_code == 200
    r = move(sclient, item_id=item["id"], kind="receive", qty=1, quantity=1, to_location_id=loc["id"])
    assert r.status_code == 409, r.text
    assert "inactive" in r.text.lower()
    assert total(sclient, item["id"]) == 0
    assert sclient.get("/movements").json() == []
