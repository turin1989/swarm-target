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


def test_generated_ids_are_unique(client):
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_echoes_request_id_on_404_error(client):
    r = client.get("/items/999999", headers={"X-Request-ID": "err-id-404"})
    assert r.status_code == 404
    assert r.headers["X-Request-ID"] == "err-id-404"


def test_generates_request_id_on_error_when_missing(client):
    r = client.get("/items/999999")
    assert r.status_code == 404
    parsed = uuid.UUID(r.headers["X-Request-ID"])
    assert parsed.version == 4


def test_echoes_request_id_on_validation_error(client):
    r = client.post("/items", json={}, headers={"X-Request-ID": "err-id-422"})
    assert r.status_code == 422
    assert r.headers["X-Request-ID"] == "err-id-422"


def test_echoes_request_id_on_domain_error(client, item, loc_a):
    # InventoryError responses (handled by the custom exception handler)
    # must carry the request id too.
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "quantity": 1,
            "from_location_id": loc_a["id"],
        },
        headers={"X-Request-ID": "err-id-409"},
    )
    assert r.status_code == 409
    assert r.headers["X-Request-ID"] == "err-id-409"


def test_generates_request_id_on_domain_error_when_missing(client, item, loc_a):
    r = client.post(
        "/movements",
        json={
            "item_id": item["id"],
            "kind": "ship",
            "quantity": 1,
            "from_location_id": loc_a["id"],
        },
    )
    assert r.status_code == 409
    parsed = uuid.UUID(r.headers["X-Request-ID"])
    assert parsed.version == 4
