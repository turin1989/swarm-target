"""X-Request-ID echoing on all responses."""

import uuid


def test_request_id_echoed_when_provided(client):
    r = client.get("/health", headers={"X-Request-ID": "my-custom-id-123"})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "my-custom-id-123"


def test_request_id_generated_when_absent(client):
    r = client.get("/health")
    assert r.status_code == 200
    request_id = r.headers["X-Request-ID"]
    # must be a valid uuid4
    parsed = uuid.UUID(request_id)
    assert parsed.version == 4


def test_request_id_generated_fresh_per_request(client):
    id1 = client.get("/health").headers["X-Request-ID"]
    id2 = client.get("/health").headers["X-Request-ID"]
    assert id1 != id2


def test_request_id_echoed_on_404_error(client):
    r = client.get("/items/99999", headers={"X-Request-ID": "err-id-404"})
    assert r.status_code == 404
    assert r.headers["X-Request-ID"] == "err-id-404"


def test_request_id_generated_on_error_when_absent(client):
    r = client.get("/items/99999")
    assert r.status_code == 404
    assert uuid.UUID(r.headers["X-Request-ID"]).version == 4


def test_request_id_echoed_on_409_conflict(client, item):
    r = client.post(
        "/items",
        json={"sku": item["sku"], "name": "Dup"},
        headers={"X-Request-ID": "err-id-409"},
    )
    assert r.status_code == 409
    assert r.headers["X-Request-ID"] == "err-id-409"


def test_request_id_echoed_on_422_validation_error(client):
    r = client.post("/items", json={"name": "x"}, headers={"X-Request-ID": "err-id-422"})
    assert r.status_code == 422
    assert r.headers["X-Request-ID"] == "err-id-422"
