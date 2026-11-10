"""X-Total-Count header on GET /items (T037)."""


def _make_items(client, n, prefix="SKU", active=True):
    for i in range(n):
        r = client.post("/items", json={"sku": f"{prefix}-{i}", "name": f"Item {i}"})
        assert r.status_code == 201, r.text
        if not active:
            r = client.put(f"/items/{r.json()['id']}", json={"active": False})
            assert r.status_code == 200, r.text


def test_total_count_empty(client):
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "0"
    assert r.json() == []


def test_total_count_matches_all_items(client):
    _make_items(client, 3)
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"
    assert len(r.json()) == 3


def test_total_count_ignores_limit_and_offset(client):
    _make_items(client, 5)
    r = client.get("/items", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"

    r = client.get("/items", params={"offset": 10})
    assert r.status_code == 200
    assert r.json() == []
    assert r.headers["X-Total-Count"] == "5"


def test_total_count_respects_active_filter(client):
    _make_items(client, 2, prefix="ON", active=True)
    _make_items(client, 3, prefix="OFF", active=False)

    r = client.get("/items", params={"active": "true", "limit": 1})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "2"

    r = client.get("/items", params={"active": "false", "limit": 1})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"


def test_total_count_respects_sku_filter(client):
    _make_items(client, 4)
    r = client.get("/items", params={"sku": "SKU-2"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "1"

    r = client.get("/items", params={"sku": "NOPE"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "0"
