"""Hidden scoring test for T040."""
from tests.scoring.conftest import mk_item, mk_loc, move


def test_non_positive_quantity_rejected(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    for n in (0, -2):
        r = move(sclient, item_id=item["id"], kind="receive", qty=n, quantity=n, to_location_id=loc["id"])
        assert r.status_code == 422, r.text
    assert sclient.get("/movements").json() == []
