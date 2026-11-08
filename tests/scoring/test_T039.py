"""Hidden scoring test for T039."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive, total


def test_adjust_sets_absolute_quantity(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    receive(sclient, item["id"], loc["id"], 10)
    r = move(sclient, item_id=item["id"], kind="adjust", qty=3, quantity=3, to_location_id=loc["id"])
    assert r.status_code == 201, r.text
    assert r.json()["kind"] == "adjust"
    assert total(sclient, item["id"]) == 3
    # adjust needs a destination and must not carry a source
    r = move(sclient, item_id=item["id"], kind="adjust", qty=3, quantity=3)
    assert r.status_code in (400, 422)
    r = move(
        sclient, item_id=item["id"], kind="adjust", qty=3, quantity=3,
        to_location_id=loc["id"], from_location_id=loc["id"],
    )
    assert r.status_code in (400, 422)
