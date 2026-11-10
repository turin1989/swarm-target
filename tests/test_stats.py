"""GET /stats endpoint."""

from inventory.db import connect, init_db
from inventory.services import reports


def test_stats_empty_database(client):
    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 0,
        "active_items": 0,
        "locations": 0,
        "movements": 0,
        "total_units": 0,
    }


def test_stats_counts_entities_and_sums_units(client, loc_a, loc_b):
    a = client.post(
        "/items", json={"sku": "A-1", "name": "Alpha", "unit_price": 1.0, "reorder_point": 0}
    ).json()
    b = client.post(
        "/items", json={"sku": "B-1", "name": "Beta", "unit_price": 1.0, "reorder_point": 0}
    ).json()
    # three movements: receive 10 into A, receive 4 into B, ship 3 from A
    assert client.post(
        "/movements",
        json={"item_id": a["id"], "kind": "receive", "qty": 10, "to_location_id": loc_a["id"]},
    ).status_code == 201
    assert client.post(
        "/movements",
        json={"item_id": b["id"], "kind": "receive", "qty": 4, "to_location_id": loc_b["id"]},
    ).status_code == 201
    assert client.post(
        "/movements",
        json={"item_id": a["id"], "kind": "ship", "qty": 3, "from_location_id": loc_a["id"]},
    ).status_code == 201

    # deactivate one item after its movements are recorded
    client.put(f"/items/{b['id']}", json={"active": False})

    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json() == {
        "items": 2,
        "active_items": 1,
        "locations": 2,
        "movements": 3,
        "total_units": 11,  # 10 - 3 + 4
    }


def test_stats_total_units_sums_across_locations(client, item, loc_a, loc_b):
    for loc, qty in ((loc_a, 7), (loc_b, 5)):
        client.post(
            "/movements",
            json={"item_id": item["id"], "kind": "receive", "qty": qty, "to_location_id": loc["id"]},
        )
    body = client.get("/stats").json()
    assert body["total_units"] == 12
    assert body["locations"] == 2
    assert body["items"] == 1


def test_reports_stats_queries_connection_directly(tmp_path):
    path = str(tmp_path / "stats.db")
    init_db(path)
    conn = connect(path)
    try:
        conn.execute(
            "INSERT INTO items (sku, name, unit_price, reorder_point) VALUES ('X', 'X', 1.0, 0)"
        )
        conn.execute("INSERT INTO locations (code, name) VALUES ('L-1', 'Loc')")
        conn.execute(
            "INSERT INTO stock_levels (item_id, location_id, qty) VALUES (1, 1, 9)"
        )
        assert reports.stats(conn) == {
            "items": 1,
            "active_items": 1,
            "locations": 1,
            "movements": 0,
            "total_units": 9,
        }
    finally:
        conn.close()
