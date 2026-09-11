"""Chiusura certificazione 11/09: etichetta ``ht_open`` e formato italiano dei motivi."""
from __future__ import annotations

from Betfair.safe_strategy import exits


def test_motivi_uscita_in_formato_italiano():
    kind, why = exits.decide_time_exit(p_lose=0.2, locked_pnl=0.14, hold_profit=1.0,
                                          stake=5.0, params={}, loss_if_lose=5.0)
    assert kind == "exit"
    assert "+0,14 €" in why and "EUR" not in why


def test_hold_reason_usa_formato_italiano():
    kind, why = exits.decide_time_exit(p_lose=0.02, locked_pnl=-4.0, hold_profit=2.0,
                                          stake=2.0, loss_if_lose=100.0,
                                          params={"hold_max_risk": 0.0, "risk_cap": 0.5, "ev_margin": 0.0})
    assert kind == "hold"
    assert "€" in why and "EUR" not in why and "," in why


def test_ht_open_porta_la_sua_regola():
    import inspect
    from Betfair.safe_strategy import anomaly

    src = inspect.getsource(anomaly)
    assert 'rule="ht_open"' in src
    assert 'rule: str = "decided"' in src
