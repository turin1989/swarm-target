"""Health endpoint database connectivity checks."""


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert "version" in body


def test_health_returns_503_when_db_cannot_be_opened(client):
    # Point the app at a path that cannot be opened (missing directory).
    client.app.state.db_path = "/nonexistent-dir/does/not/exist.db"
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert body["status"] == "ok"
    assert "version" in body
