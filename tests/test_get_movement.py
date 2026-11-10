"""GET /movements/{id} (T015)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_get_movement_returns_same_shape_as_post(client, item, loc_a):
    created = _move(
        client,
        item_id=item["id"],
        kind="receive",
        quantity=10,
        to_location_id=loc_a["id"],
        note="initial stock",
        reference="PO-1",
    ).json()

    r = client.get(f"/movements/{created['id']}")
    assert r.status_code == 200
    assert r.json() == created


def test_get_movement_unknown_id_returns_404(client):
    r = client.get("/movements/999")
    assert r.status_code == 404
    # The HTTPException is raised with detail "movement 999 not found"; the
    # app-wide error envelope surfaces that detail as error.message.
    body = r.json()
    detail = body["detail"] if "detail" in body else body["error"]["message"]
    assert detail == "movement 999 not found"
