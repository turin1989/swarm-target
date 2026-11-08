"""Hidden scoring test for T013."""
from tests.scoring.conftest import mk_item, mk_loc, receive


def test_delete_location(sclient):
    empty = mk_loc(sclient, "E")
    assert sclient.delete(f"/locations/{empty['id']}").status_code == 204
    assert sclient.get(f"/locations/{empty['id']}").status_code == 404
    assert sclient.delete("/locations/999").status_code == 404
    full = mk_loc(sclient, "F")
    item = mk_item(sclient)
    receive(sclient, item["id"], full["id"], 2)
    assert sclient.delete(f"/locations/{full['id']}").status_code == 409
    assert sclient.get(f"/locations/{full['id']}").status_code == 200
