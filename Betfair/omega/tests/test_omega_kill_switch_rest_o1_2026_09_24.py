"""O1 (24/09) - Omega in ripiego REST e il kill-switch.

Prima: ``LIVE_KILL_SWITCH`` e ``betfair_live_settings.kill_switch`` fermavano il
worker della coda, ma Omega con il runner giu' (``live_follow`` non STREAMING o
battito oltre 90 s) ripiegava sul REST e piazzava lo stesso.

Le due strade REST di Omega sono aperture (``_place_one`` -> ``place_lay_live``,
il manuale -> ``place_order_live``); le chiusure passano da
``safe_strategy.execution`` (collaudate in
``safe_strategy/tests/test_safe_kill_switch_rest_o1_2026_09_24.py``).
Fake di ``test_omega_service`` (stesse chiavi del vero): il FakeDB non ha
``live_follow_status``, quindi il gate e' chiuso e si va sul REST, cioe'
esattamente il ramo del reperto.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot,
)
from Betfair.stream.trading import controls as CTL


@pytest.fixture
def kill(monkeypatch):
    """Imposta il kill-switch: 'env', 'db' o None (spento)."""
    def _imposta(sorgente):
        monkeypatch.setenv("LIVE_KILL_SWITCH", "true" if sorgente == "env" else "false")
        monkeypatch.setattr(CTL, "get_live_settings",
                            lambda *a, **k: {"kill_switch": sorgente == "db"})
    return _imposta


def _manuale(db):
    db.manual_reqs = [{
        "id": 1, "kind": "place", "status": "pending",
        "payload": {"event_id": "1.100", "market_id": "m-1.100", "selection_id": 3,
                    "runner_name": "2 - 1", "side": "lay", "mode": "live", "size": 2},
    }]


# ---------------------------------------------------------------------------
# Automatico: _place_one -> place_lay_live
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_automatico_live_kill_attivo_nessun_ordine(kill, sorgente):
    kill(sorgente)
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert market.placed == [], "a kill-switch attivo nessuna lay REST parte"
    assert res["placed"] == 0
    # la riserva e' chiusa come rifiuto CERTO: nessuna riga 'pending' resta a
    # far credere che un ordine sia vivo
    assert not [t for t in db.trades if t.get("status") == "pending"]
    motivo = ("live_kill_switch_attivo" if sorgente == "env" else "db_kill_switch_attivo")
    skip = [p for k, p in db.activity if k == "skip" and p.get("reason") == "kill_switch"]
    assert skip and skip[0]["motivo"] == motivo and skip[0]["percorso"] == "rest"


def test_automatico_live_kill_spento_parita(kill):
    kill(None)
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 1
    assert len(market.placed) == 1
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "b1"
    assert not [p for k, p in db.activity if p.get("reason") == "kill_switch"]


def test_automatico_paper_non_guarda_il_kill_switch(kill):
    """Il paper non muove soldi: il freno non cambia niente (come il worker)."""
    kill("db")
    db = FakeDB(_control(mode="paper"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    assert S.run_once(market=market, db=db, now=NOW)["placed"] == 1


# ---------------------------------------------------------------------------
# Manuale: _manual_place -> place_order_live
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_manuale_live_kill_attivo_nessun_ordine(kill, sorgente):
    kill(sorgente)
    db = FakeDB(_control(status="idle"))
    _manuale(db)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert market.placed == []
    t = db.trades[0]
    assert t["status"] == "error"
    assert t["meta"]["reason"] == "kill_switch"
    assert t["meta"]["error_final"] is True and t["meta"]["manual"] is True
    motivo = ("live_kill_switch_attivo" if sorgente == "env" else "db_kill_switch_attivo")
    assert t["meta"]["motivo"] == motivo
    assert db.manual_reqs[0]["result"] == {"error": motivo, "trade_id": t["id"]}


def test_manuale_live_kill_spento_parita(kill):
    kill(None)
    db = FakeDB(_control(status="idle"))
    _manuale(db)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(market.placed) == 1
    assert db.trades[0]["status"] == "open" and db.trades[0]["bet_id"] == "bm1"


def test_freno_non_valutabile_ferma_l_apertura(monkeypatch):
    import builtins

    vero_import = builtins.__import__

    def _import(nome, *a, **k):
        if nome == "Betfair.stream.trading" or nome.endswith("trading.controls"):
            raise ImportError("controls assente")
        return vero_import(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _import)
    assert S._freno_rest_aperture() == "kill_switch_illeggibile"
