"""Tests for the /health endpoint database connectivity check."""


def test_health_ok_includes_db_status_and_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert "version" in body


def test_health_returns_503_when_db_cannot_be_opened(client, tmp_path):
    # Point the app at a path that cannot be opened as a SQLite database
    # (a directory), so connecting fails.
    bad_path = tmp_path / "not-a-db-dir"
    bad_path.mkdir()
    client.app.state.db_path = str(bad_path)

    r = client.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert "version" in body
