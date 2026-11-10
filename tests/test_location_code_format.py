"""Tests for location code format validation (T034).

`code` must match ^[A-Z0-9][A-Z0-9-]{0,31}$; otherwise 422.
"""

import pytest

VALID_CODES = ["WH-A", "A", "0", "WH-A2", "A-B-C-1", "X" * 32, "A" + "-" * 31]

INVALID_CODES = [
    "wh-a",       # lowercase not allowed
    "-WHA",       # must start with letter/digit
    "WH_A",       # underscore not allowed
    "WH A",       # space not allowed
    "WH.A",       # dot not allowed
    "",           # empty
    "A" * 33,     # too long (33 chars)
    "ÉCLAIR",     # non-ASCII
]


@pytest.mark.parametrize("code", VALID_CODES)
def test_create_location_valid_code(client, code):
    r = client.post("/locations", json={"code": code, "name": f"Loc {code[:10]}"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize("code", INVALID_CODES)
def test_create_location_invalid_code_returns_422(client, code):
    r = client.post("/locations", json={"code": code, "name": "Bad Loc"})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("code", INVALID_CODES)
def test_update_location_invalid_code_returns_422(client, loc_a, code):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": code})
    assert r.status_code == 422, r.text

    # Location is unchanged.
    r = client.get(f"/locations/{loc_a['id']}")
    assert r.status_code == 200
    assert r.json() == loc_a


def test_update_location_valid_code(client, loc_a):
    r = client.put(f"/locations/{loc_a['id']}", json={"code": "WH-A-NEW"})
    assert r.status_code == 200, r.text
    assert r.json()["code"] == "WH-A-NEW"


def test_existing_code_wh_a_remains_valid(client):
    r = client.post("/locations", json={"code": "WH-A", "name": "Warehouse A"})
    assert r.status_code == 201, r.text
    assert r.json()["code"] == "WH-A"
