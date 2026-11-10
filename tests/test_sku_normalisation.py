"""Tests for T017: sku normalisation on item create."""


def test_create_trims_and_uppercases_sku(client):
    r = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r.status_code == 201
    body = r.json()
    assert body["sku"] == "ABC-1"

    # stored normalised, not just echoed back
    fetched = client.get(f"/items/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["sku"] == "ABC-1"


def test_duplicate_sku_exact_case_conflicts(client):
    r1 = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "ABC-1", "name": "Dup"})
    assert r2.status_code == 409


def test_duplicate_sku_different_case_conflicts(client):
    r1 = client.post("/items", json={"sku": "  abc-1 ", "name": "Alpha"})
    assert r1.status_code == 201
    r2 = client.post("/items", json={"sku": "abc-1", "name": "Dup"})
    assert r2.status_code == 409


def test_whitespace_only_sku_rejected(client):
    r = client.post("/items", json={"sku": "   ", "name": "Blank"})
    assert r.status_code == 422
