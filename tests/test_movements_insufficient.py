"""T005: rejected movements must leave no trace (no rows, stock unchanged)."""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def test_rejected_movements_write_nothing(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])

    assert (
        _move(
            client, item_id=item["id"], kind="ship", quantity=9, from_location_id=loc_a["id"]
        ).status_code
        == 409
    )
    assert (
        _move(
            client,
            item_id=item["id"],
            kind="transfer",
            quantity=9,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        ).status_code
        == 409
    )

    # No movement rows were written for the rejected requests.
    movements = client.get("/movements").json()
    assert len(movements) == 1
    assert movements[0]["kind"] == "receive"

    # Stock levels are unchanged.
    s = client.get(f"/items/{item['id']}/stock").json()
    assert s["total"] == 5
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 5}
    ]
