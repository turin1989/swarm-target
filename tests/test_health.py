"""Health endpoint database connectivity checks."""

from inventory import __version__


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_returns_503_when_db_cannot_be_opened(client):
    # Point the app at a database path that cannot be opened
    # (a file inside a directory that does not exist).
    client.app.state.db_path = "/nonexistent-dir-for-health-test/inventory.db"
    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert body["version"] == __version__
