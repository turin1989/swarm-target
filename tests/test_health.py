from fastapi.testclient import TestClient

from inventory import __version__
from inventory.main import create_app


def test_health_reports_db_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_reports_db_error_when_db_cannot_be_opened(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    # Point the app at a path that cannot be opened as a SQLite database.
    bad_path = tmp_path / "not-a-db-dir"
    bad_path.mkdir()
    app.state.db_path = str(bad_path)
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert body["version"] == __version__
