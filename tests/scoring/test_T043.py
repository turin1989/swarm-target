"""Hidden scoring test for T043."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive


def test_movement_reference(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    r = move(
        sclient, item_id=item["id"], kind="receive", qty=1, quantity=1,
        to_location_id=loc["id"], reference="PO-77",
    )
    assert r.status_code == 201, r.text
    assert r.json()["reference"] == "PO-77"
    assert sclient.get("/movements").json()[0]["reference"] == "PO-77"
    m = receive(sclient, item["id"], loc["id"], 1)
    assert m["reference"] is None
    r = move(
        sclient, item_id=item["id"], kind="receive", qty=1, quantity=1,
        to_location_id=loc["id"], reference="x" * 65,
    )
    assert r.status_code == 422
