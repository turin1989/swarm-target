"""Hidden scoring test for T047."""
from tests.scoring.conftest import mk_item, mk_loc, move


def test_quantity_field_rename(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    r = move(sclient, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quantity"] == 7 and "qty" not in body
    s = sclient.get(f"/items/{item['id']}/stock").json()
    assert s["levels"][0]["quantity"] == 7 and "qty" not in s["levels"][0]
    assert move(sclient, item_id=item["id"], kind="receive", qty=1, to_location_id=loc["id"]).status_code == 422
