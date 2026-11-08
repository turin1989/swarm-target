"""Hidden scoring test for T001."""
from tests.scoring.conftest import mk_item


def test_search_is_case_insensitive(sclient):
    mk_item(sclient, sku="BLT-1", name="Blue Widget")
    for q in ("widget", "WIDGET", "Widget", "blt"):
        got = [i["sku"] for i in sclient.get("/search", params={"q": q}).json()]
        assert got == ["BLT-1"], q
