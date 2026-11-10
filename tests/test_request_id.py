import uuid


def test_request_id_echoed_when_provided(client):
    r = client.get("/health", headers={"X-Request-ID": "my-custom-id-123"})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "my-custom-id-123"


def test_request_id_generated_when_missing(client):
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers["X-Request-ID"]
    # must be a valid uuid4
    assert uuid.UUID(rid).version == 4


def test_request_id_unique_per_request(client):
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_request_id_on_404_error(client):
    r = client.get("/items/999999", headers={"X-Request-ID": "err-id-404"})
    assert r.status_code == 404
    assert r.headers["X-Request-ID"] == "err-id-404"


def test_request_id_generated_on_error_when_missing(client):
    r = client.get("/items/999999")
    assert r.status_code == 404
    assert uuid.UUID(r.headers["X-Request-ID"]).version == 4


def test_request_id_on_validation_error(client):
    r = client.post("/items", json={}, headers={"X-Request-ID": "err-id-422"})
    assert r.status_code == 422
    assert r.headers["X-Request-ID"] == "err-id-422"
