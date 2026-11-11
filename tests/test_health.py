from fastapi.testclient import TestClient

from inventory import __version__
from inventory.main import create_app


def test_health_includes_db_ok_when_database_reachable(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_returns_503_with_db_error_when_database_unopenable(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    # Point the app at a path that cannot be opened as a SQLite database.
    app.state.db_path = str(tmp_path)  # a directory, not a file
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert body["version"] == __version__
