"""Hidden scoring test for T005."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive, total


def test_ship_more_than_on_hand_is_409(sclient):
    item = mk_item(sclient)
    a, b = mk_loc(sclient, "A"), mk_loc(sclient, "B")
    receive(sclient, item["id"], a["id"], 3)
    r = move(sclient, item_id=item["id"], kind="ship", qty=5, quantity=5, from_location_id=a["id"])
    assert r.status_code == 409, r.text
    assert "insufficient" in r.text.lower()
    assert total(sclient, item["id"]) == 3
    assert len(sclient.get("/movements").json()) == 1

    r = move(
        sclient, item_id=item["id"], kind="transfer", qty=5, quantity=5,
        from_location_id=a["id"], to_location_id=b["id"],
    )
    assert r.status_code == 409, r.text
    assert total(sclient, item["id"]) == 3
    assert len(sclient.get("/movements").json()) == 1
