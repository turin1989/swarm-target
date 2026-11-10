"""T003: transfer movements must debit the source and credit the destination.

Regression tests ensuring a transfer never credits the source location
(or leaves both locations untouched) and that totals are conserved.
"""


def _move(client, **kw):
    return client.post("/movements", json=kw)


def _stock(client, item_id):
    r = client.get(f"/items/{item_id}/stock")
    assert r.status_code == 200, r.text
    return r.json()


def _qty_at(stock_body, location_id):
    for lvl in stock_body["levels"]:
        if lvl["location_id"] == location_id:
            return lvl["quantity"]
    return 0


def test_transfer_debits_source_and_credits_destination(client, item, loc_a, loc_b):
    r = _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    assert r.status_code == 201, r.text

    before = _stock(client, item["id"])
    assert _qty_at(before, loc_a["id"]) == 5
    assert _qty_at(before, loc_b["id"]) == 0

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201, r.text

    after = _stock(client, item["id"])
    # source decreases by exactly N
    assert _qty_at(after, loc_a["id"]) == 3
    # destination increases by exactly N
    assert _qty_at(after, loc_b["id"]) == 2


def test_transfer_preserves_total_stock(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=9, to_location_id=loc_a["id"])
    assert _stock(client, item["id"])["total"] == 9

    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=4,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201, r.text
    assert _stock(client, item["id"])["total"] == 9


def test_item_stock_endpoint_reflects_both_locations_after_transfer(
    client, item, loc_a, loc_b
):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )

    s = _stock(client, item["id"])
    assert s["total"] == 5
    assert s["levels"] == [
        {"item_id": item["id"], "location_id": loc_a["id"], "quantity": 3},
        {"item_id": item["id"], "location_id": loc_b["id"], "quantity": 2},
    ]


def test_full_transfer_empties_source_and_fills_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=7, to_location_id=loc_a["id"])
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=7,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    assert r.status_code == 201, r.text

    s = _stock(client, item["id"])
    assert s["total"] == 7
    assert _qty_at(s, loc_a["id"]) == 0
    assert _qty_at(s, loc_b["id"]) == 7


def test_repeated_transfers_accumulate_at_destination(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=10, to_location_id=loc_a["id"])
    for _ in range(3):
        r = _move(
            client,
            item_id=item["id"],
            kind="transfer",
            quantity=2,
            from_location_id=loc_a["id"],
            to_location_id=loc_b["id"],
        )
        assert r.status_code == 201, r.text

    s = _stock(client, item["id"])
    assert s["total"] == 10
    assert _qty_at(s, loc_a["id"]) == 4
    assert _qty_at(s, loc_b["id"]) == 6


def test_transfer_back_restores_original_distribution(client, item, loc_a, loc_b):
    _move(client, item_id=item["id"], kind="receive", quantity=5, to_location_id=loc_a["id"])
    _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_a["id"],
        to_location_id=loc_b["id"],
    )
    r = _move(
        client,
        item_id=item["id"],
        kind="transfer",
        quantity=2,
        from_location_id=loc_b["id"],
        to_location_id=loc_a["id"],
    )
    assert r.status_code == 201, r.text

    s = _stock(client, item["id"])
    assert s["total"] == 5
    assert _qty_at(s, loc_a["id"]) == 5
    assert _qty_at(s, loc_b["id"]) == 0
