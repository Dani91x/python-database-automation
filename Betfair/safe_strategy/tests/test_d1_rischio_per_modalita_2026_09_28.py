# -*- coding: utf-8 -*-
"""D1 (28/09) - SAFE: I CAP DI UNA RICHIESTA CONTANO LA MODALITA' DELL'ORDINE.

Catalogo §7.21. I segnali automatici hanno gia' un contesto di rischio per
modalita' (``scan_and_place._ctx_di``). Le richieste della UI e le proposte
approvate (``_request_place``, ``_request_place_combo``) usavano invece il
contesto del CICLO, costruito sulla modalita' del SERVIZIO: con
``strategy_modes`` un ordine paper a servizio live si confrontava con
esposizione e liability giornaliera del live (e non contava quelle del paper).

Il finto ``aggregates(mode=...)`` filtra per modalita' come la RPC vera
``get_safe_aggregates(p_mode)`` (``safe_strategy_paper_live_2026-09-13.sql``).
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_db as B
from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, FakeMarket,
                                                          _feed_row, _place_payload,
                                                          _reset_module_state)


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()
    S._AGG_ULTIMO_BUONO.clear()
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    yield
    _reset_module_state()


class DbModi(FakeDB):
    def aggregates(self, mode=None):
        return B.aggregate_rows([t for t in self.trades
                                 if mode is None or str(t.get("mode")) == str(mode)])


def _db_live_quasi_al_tetto():
    db = DbModi(status="running", mode="live",
                params={"strategy_modes": {"manual": "paper"}})
    db.insert_trade({"event_id": "9.9", "market_id": "m9", "market_type": "MATCH_ODDS",
                     "selection_id": 3, "side": "lay", "price": 100.0, "size": 5.0,
                     "liability": 495.0, "status": "open", "mode": "live",
                     "origin": "auto", "strategy": "base", "signal_key": "9.9:base:x",
                     "placed_at": NOW.isoformat(), "commission": 0.05, "meta": {}})
    return db


def test_richiesta_PAPER_a_servizio_LIVE_non_e_frenata_dai_numeri_del_live():
    db = _db_live_quasi_al_tetto()
    params = S.resolve_params(db.control["params"])
    ctx_ciclo = S.build_risk_ctx(db, NOW, params, mode="live")
    res = S._request_place(db=db, market=FakeMarket(), rows_by_event={"1.1": _feed_row()},
                           payload=_place_payload(size=10.0, mode="paper"), params=params,
                           now=NOW, risk_ctx=ctx_ciclo, control_mode="live")
    assert res.get("error") != S.RK.R_DAILY_LIAB, f"frenata dal cap del live: {res}"
    assert res.get("ok") is True or res.get("trade_id"), res
    nuova = [t for t in db.trades if t.get("mode") == "paper"]
    assert len(nuova) == 1


def test_stessa_modalita_si_riusa_il_contesto_del_ciclo():
    db = _db_live_quasi_al_tetto()
    params = S.resolve_params(db.control["params"])
    ctx = S.build_risk_ctx(db, NOW, params, mode="live")
    assert S._ctx_della_modalita(db, NOW, params, ctx, "live", "live") is ctx
    altro = S._ctx_della_modalita(db, NOW, params, ctx, "live", "paper")
    assert altro is not ctx
    assert all(str(t.get("mode")) == "paper" for t in altro.get("open_tutte") or [])
