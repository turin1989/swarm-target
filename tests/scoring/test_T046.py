"""Hidden scoring test for T046."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive


def test_transfer_to_same_location_rejected(sclient):
    item = mk_item(sclient)
    a = mk_loc(sclient, "A")
    receive(sclient, item["id"], a["id"], 5)
    r = move(
        sclient, item_id=item["id"], kind="transfer", qty=1, quantity=1,
        from_location_id=a["id"], to_location_id=a["id"],
    )
    assert r.status_code == 400, r.text
    assert "same location" in r.text.lower()
    assert len(sclient.get("/movements").json()) == 1
