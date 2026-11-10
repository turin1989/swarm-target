"""Health endpoint database connectivity checks."""

from inventory import __version__


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_returns_503_when_db_cannot_be_opened(client, tmp_path):
    # Point the app at a path that cannot be opened as a SQLite database
    # (a directory is not a valid database file).
    bad_path = tmp_path / "not-a-db-dir"
    bad_path.mkdir()
    client.app.state.db_path = str(bad_path)

    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert body["version"] == __version__
