"""X-Total-Count header on GET /items (T037)."""


def _create_items(client, n, active=True):
    for i in range(n):
        r = client.post(
            "/items",
            json={"sku": f"SKU-{'A' if active else 'I'}-{i}", "name": f"Item {i}"},
        )
        assert r.status_code == 201, r.text
        if not active:
            item_id = r.json()["id"]
            r = client.put(f"/items/{item_id}", json={"active": False})
            assert r.status_code == 200, r.text


def test_total_count_header_present(client):
    _create_items(client, 3)
    r = client.get("/items")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "3"


def test_total_count_ignores_limit_and_offset(client):
    _create_items(client, 7)
    r = client.get("/items", params={"limit": 2, "offset": 4})
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2
    assert r.headers["X-Total-Count"] == "7"


def test_total_count_respects_filters(client):
    _create_items(client, 4, active=True)
    _create_items(client, 2, active=False)

    r = client.get("/items", params={"active": "true", "limit": 1})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "4"

    r = client.get("/items", params={"active": "false", "limit": 1})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "2"

    r = client.get("/items", params={"sku": "SKU-A-0"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "1"


def test_total_count_zero_when_no_match(client):
    r = client.get("/items", params={"sku": "NOPE"})
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "0"
    assert r.json()["items"] == []
