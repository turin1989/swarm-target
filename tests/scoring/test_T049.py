"""Hidden scoring test for T049."""


def test_reorder_level_rename(sclient):
    r = sclient.post("/items", json={"sku": "R", "name": "r", "reorder_level": 4})
    assert r.status_code == 201, r.text
    assert r.json()["reorder_level"] == 4 and "reorder_point" not in r.json()
    assert sclient.post("/items", json={"sku": "R2", "name": "r", "reorder_point": 4}).status_code == 422
    r = sclient.put(f"/items/{r.json()['id']}", json={"reorder_level": 9})
    assert r.json()["reorder_level"] == 9
    entries = sclient.get("/reports/low-stock").json()
    assert entries and entries[0]["reorder_level"] == 9 and "reorder_point" not in entries[0]
