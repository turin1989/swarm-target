"""Hidden scoring test for T027."""
from tests.scoring.conftest import mk_loc, receive


def test_low_stock_has_shortfall(sclient):
    loc = mk_loc(sclient)
    r = sclient.post("/items", json={"sku": "S", "name": "s", "reorder_point": 10})
    if r.status_code == 422:  # after T049
        r = sclient.post("/items", json={"sku": "S", "name": "s", "reorder_level": 10})
    assert r.status_code == 201, r.text
    receive(sclient, r.json()["id"], loc["id"], 4)
    entries = sclient.get("/reports/low-stock").json()
    assert len(entries) == 1
    assert entries[0]["shortfall"] == 6
