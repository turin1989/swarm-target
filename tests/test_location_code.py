import pytest


def _create(client, code):
    return client.post("/locations", json={"code": code, "name": "Loc"})


@pytest.mark.parametrize(
    "code",
    [
        "WH-A",
        "A",
        "0",
        "WH-B-2",
        "A" * 32,
        "A" + "-" * 31,
    ],
)
def test_valid_location_codes_accepted(client, code):
    r = _create(client, code)
    assert r.status_code == 201, r.text
    assert r.json()["code"] == code


@pytest.mark.parametrize(
    "code",
    [
        "",            # empty
        "-WH",         # cannot start with hyphen
        "wh-a",        # lowercase not allowed
        "WH A",        # spaces not allowed
        "WH_A",        # underscore not allowed
        "WH.A",        # dot not allowed
        "A" * 33,      # too long (max 32 chars)
        "WH-A\n",      # trailing newline not allowed
    ],
)
def test_invalid_location_codes_rejected(client, code):
    r = _create(client, code)
    assert r.status_code == 422, r.text
