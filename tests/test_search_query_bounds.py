"""T029: the search query `q` is trimmed and bounded."""


def _assert_validation_error_shape(body):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}
    assert body["error"]["code"] == "validation_error"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_leading_and_trailing_whitespace_is_ignored(client):
    client.post("/items", json={"sku": "BOLT-M8", "name": "bolt"})
    client.post("/items", json={"sku": "NUT-M8", "name": "nut"})
    padded = client.get("/search", params={"q": "  bolt "})
    plain = client.get("/search", params={"q": "bolt"})
    assert padded.status_code == 200
    assert plain.status_code == 200
    assert padded.json() == plain.json()
    assert [i["sku"] for i in padded.json()] == ["BOLT-M8"]


def test_trimmed_query_does_not_match_on_surrounding_whitespace(client):
    # The padding itself must not take part in the substring match.
    client.post("/items", json={"sku": "W1", "name": "bolt"})
    r = client.get("/search", params={"q": " bolt"})
    assert r.status_code == 200
    assert [i["sku"] for i in r.json()] == ["W1"]


def test_query_longer_than_100_chars_is_rejected(client):
    r = client.get("/search", params={"q": "x" * 101})
    assert r.status_code == 422
    _assert_validation_error_shape(r.json())


def test_query_of_exactly_100_chars_is_accepted(client):
    r = client.get("/search", params={"q": "x" * 100})
    assert r.status_code == 200
    assert r.json() == []


def test_whitespace_only_query_is_rejected(client):
    for q in (" ", "   ", "\t", "\n", " \t\n "):
        r = client.get("/search", params={"q": q})
        assert r.status_code == 422, repr(q)
        _assert_validation_error_shape(r.json())
