"""Health endpoint database connectivity checks."""


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert "version" in body


def test_health_returns_503_when_db_cannot_be_opened(client, tmp_path):
    # Point the app at a database path whose parent directory does not exist,
    # so sqlite cannot open it.
    client.app.state.db_path = str(tmp_path / "missing-dir" / "nope.db")
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert "version" in body
