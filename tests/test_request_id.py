import uuid


def test_echoes_provided_request_id(client):
    r = client.get("/health", headers={"X-Request-ID": "my-custom-id-123"})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "my-custom-id-123"


def test_generates_uuid4_when_missing(client):
    r = client.get("/health")
    assert r.status_code == 200
    value = r.headers["X-Request-ID"]
    parsed = uuid.UUID(value)
    assert parsed.version == 4


def test_generated_ids_are_unique_per_request(client):
    r1 = client.get("/health")
    r2 = client.get("/health")
    assert r1.headers["X-Request-ID"] != r2.headers["X-Request-ID"]


def test_error_response_echoes_request_id(client):
    r = client.get("/items/999999", headers={"X-Request-ID": "err-id-456"})
    assert r.status_code == 404
    assert r.headers["X-Request-ID"] == "err-id-456"


def test_error_response_generates_request_id_when_missing(client):
    r = client.get("/no-such-route")
    assert r.status_code == 404
    parsed = uuid.UUID(r.headers["X-Request-ID"])
    assert parsed.version == 4


def test_validation_error_carries_request_id(client):
    r = client.post("/items", json={}, headers={"X-Request-ID": "val-id-789"})
    assert r.status_code == 422
    assert r.headers["X-Request-ID"] == "val-id-789"
