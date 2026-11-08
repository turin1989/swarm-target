"""Hidden scoring test for T007."""
from tests.scoring.conftest import mk_loc


def test_duplicate_location_code_is_409(sclient):
    mk_loc(sclient, code="WH-1", name="One")
    r = sclient.post("/locations", json={"code": "WH-1", "name": "Two"})
    assert r.status_code == 409, r.text
    assert "WH-1" in r.text
    assert len(sclient.get("/locations").json()) == 1
