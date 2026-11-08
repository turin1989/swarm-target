"""Hidden scoring test for T004."""
from tests.scoring.conftest import mk_item


def test_put_updates_reorder_point(sclient):
    item = mk_item(sclient)
    key = "reorder_point" if "reorder_point" in item else "reorder_level"
    r = sclient.put(f"/items/{item['id']}", json={key: 12})
    assert r.status_code == 200, r.text
    assert r.json()[key] == 12
    assert sclient.get(f"/items/{item['id']}").json()[key] == 12
    r = sclient.put(f"/items/{item['id']}", json={"name": "Renamed", key: 3})
    assert r.json()[key] == 3 and r.json()["name"] == "Renamed"
    r = sclient.put(f"/items/{item['id']}", json={"name": "Again"})
    assert r.json()[key] == 3
