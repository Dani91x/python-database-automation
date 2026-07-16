"""pnl_settled famiglia scalper CALCIO (16/07, pattern tennis).

Verità del settlement simulato (``order.simulated.profit``) accumulata alla
chiusura del mercato, ADDITIVA a ``pnl_locked`` (proiezione dei chiamanti),
con DEDUP via ``_settled_by_id`` (flumine può rilanciare
``process_closed_market`` sullo stesso mercato: mai doppio conteggio).
Il theta eredita il percorso dal sniper (``super().process_closed_market``).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Betfair.stream.scalper.scalper_bot import ScalperStrategy
from Betfair.stream.scalper.sniper_bot import SniperStrategy


def _settled_order(profit, *, oid=None, with_sim=True):
    o = SimpleNamespace(id=oid)
    if with_sim:
        o.simulated = SimpleNamespace(profit=profit)
    return o


class _Blotter:
    def __init__(self, orders):
        self._orders = list(orders)

    def strategy_orders(self, strategy):
        return list(self._orders)


def _market(orders):
    return SimpleNamespace(market_id="1.1", blotter=_Blotter(orders))


def _mb():
    return SimpleNamespace(
        market_id="1.1",
        market_definition=SimpleNamespace(market_type="OVER_UNDER_25"),
    )


@pytest.mark.parametrize("make", [
    lambda: ScalperStrategy(market_filter={}, scalper_params={"stake": 25.0}),
    lambda: SniperStrategy(market_filter={}, sniper_params={"stake": 10.0}),
])
def test_pnl_settled_accumula_e_dedup(make):
    s = make()
    m = _market([_settled_order(0.50, oid="A"), _settled_order(-0.20, oid="B")])
    s.process_closed_market(m, _mb())
    assert s.stats["pnl_settled"] == pytest.approx(0.30)
    # ri-chiusura dello STESSO mercato: nessun raddoppio (dedup _settled_by_id)
    s.process_closed_market(m, _mb())
    assert s.stats["pnl_settled"] == pytest.approx(0.30)
    # mercato DIVERSO (ordini nuovi): si accumula
    s.process_closed_market(_market([_settled_order(0.10, oid="C")]), _mb())
    assert s.stats["pnl_settled"] == pytest.approx(0.40)


def test_pnl_settled_robusto_senza_simulated():
    s = SniperStrategy(market_filter={}, sniper_params={"stake": 10.0})
    m = _market([
        _settled_order(0.0, oid="A", with_sim=False),   # simulated assente
        SimpleNamespace(id="B", simulated=None),          # simulated=None
        _settled_order(None, oid="C"),                    # profit=None
        SimpleNamespace(id="D",
                        simulated=SimpleNamespace(profit="boom")),  # non numerico
    ])
    s.process_closed_market(m, _mb())
    assert s.stats["pnl_settled"] == 0.0


def test_pnl_settled_non_tocca_pnl_locked():
    s = ScalperStrategy(market_filter={}, scalper_params={"stake": 25.0})
    s.stats["pnl_locked"] = 1.23
    s.process_closed_market(_market([_settled_order(0.50, oid="A")]), _mb())
    assert s.stats["pnl_locked"] == pytest.approx(1.23)
    assert s.stats["pnl_settled"] == pytest.approx(0.50)
