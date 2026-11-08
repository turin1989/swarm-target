"""Hidden scoring test for T048."""
from tests.scoring.conftest import mk_item


def test_items_envelope(sclient):
    for n in range(3):
        mk_item(sclient, sku=f"S{n}", name="s")
    r = sclient.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict), body
    assert body["total"] == 3
    assert body["limit"] == 2 and body["offset"] == 1
    assert [i["sku"] for i in body["items"]] == ["S1", "S2"]
