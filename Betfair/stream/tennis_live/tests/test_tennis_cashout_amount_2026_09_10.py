"""Tennis (10/09) — ``params.amount`` sul green-up: stake ASSOLUTO in EUR.

Mirror del calcio (``live_order_worker._do_greenup``): l'importo VINCE su ``fraction``,
e' cappato al green totale (mai un ordine che inverte la posizione) e un valore
malformato e' un ERRORE di richiesta (mai un green TOTALE inatteso).
Nessuna rete, nessun ordine reale: market/blotter/sessione sono mock.
"""
from __future__ import annotations

import types

import pytest

from Betfair.stream.tennis_live import tennis_live_order_worker as tow


class _GreenBlotter:
    def __init__(self, w, l):
        self._w, self._l = w, l

    def get_exposures(self, strategy, lookup):  # noqa: ARG002
        return {"matched_profit_if_win": self._w, "matched_profit_if_lose": self._l}

    def strategy_orders(self, strategy):  # noqa: ARG002
        return []


def _market(w, l, best_back=None, best_lay=None):
    ex = types.SimpleNamespace(
        available_to_back=[{"price": best_back, "size": 100}] if best_back else [],
        available_to_lay=[{"price": best_lay, "size": 100}] if best_lay else [],
    )
    runner = types.SimpleNamespace(selection_id=5, handicap=0.0, ex=ex)
    market = types.SimpleNamespace(
        market_id="1.1",
        blotter=_GreenBlotter(w, l),
        market_book=types.SimpleNamespace(runners=[runner]),
        placed=[],
    )
    market.place_order = lambda order, customer_strategy_ref=None: (
        market.placed.append(order) or True
    )
    return market


def _session():
    return types.SimpleNamespace(
        market_meta={"ev1": {"market_id": "1.1"}},
        capture={"ev1": object()},
        tracked_orders={},
        order_mode="PAPER",
        framework_gen=0,
    )


def _flumine(market):
    return types.SimpleNamespace(markets=types.SimpleNamespace(markets={"1.1": market}))


def _cmd(**params):
    return {"action": "greenup", "mode": "paper", "market_id": "1.1",
            "selection_id": 5, "handicap": 0.0, "params": params}


def test_amount_limita_lo_stake_dell_hedge():
    # BACK 2 @ 2.00: W=+2.00, L=-2.00 -> LAY. Green totale = 4/1.90 = 2.11.
    market = _market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    res = tow._dispatch(_flumine(market), _session(), _cmd(amount=1.25), "awtq50")
    assert res["ok"] is True
    order = market.placed[0]
    assert order.side == "LAY"
    assert order.order_type.size == pytest.approx(1.25)


def test_amount_cappato_al_green_totale():
    market = _market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    res = tow._dispatch(_flumine(market), _session(), _cmd(amount=999.0), "awtq51")
    assert res["ok"] is True
    assert market.placed[0].order_type.size == pytest.approx(round(4.0 / 1.90, 2))


def test_amount_vince_su_fraction():
    market = _market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    tow._dispatch(_flumine(market), _session(), _cmd(amount=0.80, fraction=0.1), "awtq52")
    assert market.placed[0].order_type.size == pytest.approx(0.80)


def test_amount_malformato_e_errore_esplicito():
    market = _market(2.0, -2.0, best_back=1.88, best_lay=1.90)
    with pytest.raises(ValueError, match="amount"):
        tow._dispatch(_flumine(market), _session(), _cmd(amount=-1.0), "awtq53")
    assert market.placed == []


def test_amount_infinito_e_errore_esplicito():
    # MEDIUM-5 (review 10/09): un importo NON finito passa il check "> 0" ma non e' uno
    # stake: errore esplicito, mai un ordine.
    for bad in (float("inf"), "inf"):
        market = _market(2.0, -2.0, best_back=1.88, best_lay=1.90)
        with pytest.raises(ValueError, match="amount"):
            tow._dispatch(_flumine(market), _session(), _cmd(amount=bad), "awtq54")
        assert market.placed == []
