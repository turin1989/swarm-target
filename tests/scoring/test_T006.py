"""Hidden scoring test for T006."""
from tests.scoring.conftest import mk_item


def test_delete_unknown_item_is_404(sclient):
    r = sclient.delete("/items/999")
    assert r.status_code == 404
    assert "999" in r.text and "not found" in r.text
    item = mk_item(sclient)
    assert sclient.delete(f"/items/{item['id']}").status_code == 204
    assert sclient.delete(f"/items/{item['id']}").status_code == 404
