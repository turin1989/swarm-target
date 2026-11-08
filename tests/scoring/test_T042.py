"""Hidden scoring test for T042."""
import re

from tests.scoring.conftest import mk_item, mk_loc, receive


def test_movements_have_created_at(sclient):
    item = mk_item(sclient)
    loc = mk_loc(sclient)
    m = receive(sclient, item["id"], loc["id"], 1)
    assert "created_at" in m
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", m["created_at"])
    assert sclient.get("/movements").json()[0]["created_at"] == m["created_at"]
