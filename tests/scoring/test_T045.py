"""Hidden scoring test for T045."""
from tests.scoring.conftest import mk_item, mk_loc, move, receive, total


def test_reverse_movement(sclient):
    item = mk_item(sclient)
    a, b = mk_loc(sclient, "A"), mk_loc(sclient, "B")
    m = receive(sclient, item["id"], a["id"], 10)
    r = sclient.post(f"/movements/{m['id']}/reverse")
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["kind"] == "ship"
    assert rev["from_location_id"] == a["id"]
    assert rev["note"] == f"reversal of {m['id']}"
    assert total(sclient, item["id"]) == 0

    receive(sclient, item["id"], a["id"], 10)
    tr = move(
        sclient, item_id=item["id"], kind="transfer", qty=4, quantity=4,
        from_location_id=a["id"], to_location_id=b["id"],
    )
    assert tr.status_code == 201, tr.text
    rev = sclient.post(f"/movements/{tr.json()['id']}/reverse").json()
    assert rev["kind"] == "transfer"
    assert (rev["from_location_id"], rev["to_location_id"]) == (b["id"], a["id"])
    assert sclient.post("/movements/999/reverse").status_code == 404
