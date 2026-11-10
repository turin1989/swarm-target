from fastapi.testclient import TestClient

from inventory import __version__
from inventory.main import create_app


def test_health_ok_includes_db_status_and_version(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_health_returns_503_when_database_cannot_be_opened(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    # Point the app at a database path that cannot be opened.
    app.state.db_path = str(tmp_path / "missing-dir" / "nope.db")
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 503
    body = r.json()
    assert body["db"] == "error"
    assert "status" in body
    assert body["version"] == __version__
