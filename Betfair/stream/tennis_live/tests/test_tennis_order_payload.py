"""Test del parsing PURO del payload della coda ordini tennis."""

import pytest

from Betfair.stream.tennis_live.tennis_live_order_worker import parse_order_payload


def test_place_flat_columns():
    row = {
        "id": 1, "action": "place", "mode": "paper", "market_id": "1.23",
        "selection_id": 111, "side": "back", "price": 2.0, "size": 5,
        "client_ref": "abc",
    }
    cmd = parse_order_payload(row)
    assert cmd["action"] == "place"
    assert cmd["mode"] == "paper"
    assert cmd["market_id"] == "1.23"
    assert cmd["selection_id"] == 111
    assert cmd["side"] == "back"
    assert cmd["price"] == 2.0
    assert cmd["size"] == 5.0
    assert cmd["client_ref"] == "abc"


def test_place_nested_payload():
    row = {
        "id": 2,
        "payload": {
            "action": "place", "mode": "live", "market_id": "1.99",
            "selection_id": 222, "side": "lay", "price": 3.0, "liability": 10,
            "client_ref": "xyz",
        },
    }
    cmd = parse_order_payload(row)
    assert cmd["market_id"] == "1.99"
    assert cmd["side"] == "lay"
    assert cmd["liability"] == 10.0
    assert cmd["mode"] == "live"


def test_place_missing_price_raises():
    with pytest.raises(ValueError):
        parse_order_payload({"id": 3, "action": "place", "market_id": "1.1",
                             "selection_id": 1, "side": "back"})


def test_cancel_requires_bet_id():
    with pytest.raises(ValueError):
        parse_order_payload({"id": 4, "action": "cancel", "market_id": "1.1"})
    cmd = parse_order_payload({"id": 5, "action": "cancel", "bet_id": "9988"})
    assert cmd["action"] == "cancel"
    assert cmd["bet_id"] == "9988"


def test_replace_requires_new_price():
    with pytest.raises(ValueError):
        parse_order_payload({"id": 6, "action": "replace", "bet_id": "1"})
    cmd = parse_order_payload({"id": 7, "action": "replace", "bet_id": "1", "new_price": 2.5})
    assert cmd["new_price"] == 2.5


def test_defaults_persistence_and_handicap():
    cmd = parse_order_payload({
        "id": 8, "action": "place", "market_id": "1.1", "selection_id": 1,
        "side": "back", "price": 2.0, "size": 2,
    })
    assert cmd["persistence"] == "LAPSE"
    assert cmd["handicap"] == 0.0
    assert cmd["order_type"] == "LIMIT"


def test_missing_action_raises():
    with pytest.raises(ValueError):
        parse_order_payload({"id": 9, "market_id": "1.1"})
