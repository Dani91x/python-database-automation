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


# ---------------------------------------------------------------------------
# Validazione money-critical di _do_place (fix review HIGH): min stake .it,
# whitelist side/persistence, range prezzo, cap opzionale — ULTIMA barriera
# esplicita prima di un ordine reale (mai delegare al rifiuto grezzo di Betfair).
# ---------------------------------------------------------------------------
from types import SimpleNamespace

import Betfair.stream.tennis_live.tennis_live_order_worker as tow


def _fake_env(monkeypatch, market_id="1.1"):
    market = SimpleNamespace(market_id=market_id)
    flumine = SimpleNamespace(markets=SimpleNamespace(markets={market_id: market}))
    session = SimpleNamespace(
        market_meta={"ev1": {"market_id": market_id}},
        capture={"ev1": object()},   # basta non-None: le validazioni scattano prima del Trade
        tracked_orders={},
    )
    monkeypatch.delenv("TENNIS_LIVE_JURISDICTION", raising=False)
    monkeypatch.delenv("TENNIS_LIVE_MAX_STAKE_PER_ORDER", raising=False)
    return flumine, session


def _place_cmd(**kw):
    base = {"action": "place", "mode": "paper", "market_id": "1.1",
            "selection_id": 5, "side": "back", "price": 2.0, "size": 5.0,
            "persistence": "LAPSE", "handicap": 0.0, "liability": None}
    base.update(kw)
    return base


def test_place_rejects_submin_back_it(monkeypatch):
    flumine, session = _fake_env(monkeypatch)
    with pytest.raises(ValueError, match="minimo"):
        tow._do_place(flumine, session, _place_cmd(size=1.0), "awtq1")   # < €2.00 .it


def test_place_rejects_submin_lay_it(monkeypatch):
    flumine, session = _fake_env(monkeypatch)
    with pytest.raises(ValueError, match="minimo"):
        tow._do_place(flumine, session, _place_cmd(side="lay", size=0.2), "awtq1")  # < €0.50


def test_place_rejects_invalid_side_and_persistence(monkeypatch):
    flumine, session = _fake_env(monkeypatch)
    with pytest.raises(ValueError, match="side"):
        tow._do_place(flumine, session, _place_cmd(side="banana"), "awtq1")
    with pytest.raises(ValueError, match="persistence"):
        tow._do_place(flumine, session, _place_cmd(persistence="FOREVER"), "awtq1")


def test_place_rejects_over_cap(monkeypatch):
    flumine, session = _fake_env(monkeypatch)
    monkeypatch.setenv("TENNIS_LIVE_MAX_STAKE_PER_ORDER", "10")
    with pytest.raises(ValueError, match="cap"):
        tow._do_place(flumine, session, _place_cmd(size=25.0), "awtq1")


def test_place_derives_lay_size_from_liability_then_validates(monkeypatch):
    """liability 0.4 @2.0 -> size 0.4 < minimo LAY .it 0.50 -> rifiutato PRIMA del place."""
    flumine, session = _fake_env(monkeypatch)
    with pytest.raises(ValueError, match="minimo"):
        tow._do_place(flumine, session,
                      _place_cmd(side="lay", size=None, liability=0.4), "awtq1")
