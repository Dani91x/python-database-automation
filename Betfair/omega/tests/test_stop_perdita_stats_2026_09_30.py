"""30/09 (backend per la UI) - ``omega_control.stats.stop_perdita``.

Chiave ADDITIVA ``{"soglia": number, "chiave": string, "scattato": boolean}``:
il tetto di perdita giornaliera che il bot usa DAVVERO per fermare le
aperture (stessa chiave, stessa soglia, stesso R dei numeri del bot).
Nessun cambiamento di comportamento.

Il finto della riga ``omega_control`` ha le colonne VERE della tabella
(lette in sola lettura da information_schema il 30/09: id, status, mode,
daily_goal, params, stats, error, started_at, stopped_at, heartbeat_at,
updated_at, created_at).
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_config
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (NOW, FakeDB, FakeMarket, _cs, _event,
                                              _open_snapshot)
from Betfair.omega.tests.runner_paper_finto import attiva_runner_paper
# importato QUI perche' la fixture autouse di Betfair/conftest.py
# (_kill_switch_del_db_senza_rete) lo trovi gia' caricato e ne neutralizzi la
# lettura del DB (altrimenti il freno prova la rete a ogni apertura)
import Betfair.stream.trading.controls  # noqa: F401,E402


def _riga_control(status: str = "running", params: dict | None = None) -> dict:
    return {"id": 1, "status": status, "mode": "paper", "daily_goal": 100.0,
            "params": params or {}, "stats": {}, "error": None,
            "started_at": NOW.isoformat(), "stopped_at": None,
            "heartbeat_at": None, "updated_at": NOW.isoformat(),
            "created_at": "2026-07-01T00:00:00+00:00"}


def _perdita_di_oggi(db: FakeDB, pnl: float) -> None:
    db.trades.append({
        "id": 99, "event_id": "past", "status": "lost", "pnl": pnl, "liability": 500,
        "selection_id": 1, "price": 50, "size": 10, "commission": 0.05,
        "placed_at": NOW.isoformat(), "settled_at": NOW.isoformat(), "mode": "paper",
    })
    db._id = 99


# ---------------------------------------------------------------------------
# la regola (unita'): parametri di PRODUZIONE risolti dal config vero
# ---------------------------------------------------------------------------
def test_v3_di_produzione_usa_v3_daily_loss_cap():
    # in produzione ``DEFAULTS['strategy_version']`` = 3 (omega_config.py:221);
    # la suite lo riporta a 2 (Betfair/omega/conftest.py:68): qui si dichiara
    params = omega_config.resolve_params({"strategy_version": 3})
    assert int(params["strategy_version"]) >= 3 and params["engine"] == "legs"
    soglia = float(params["v3_daily_loss_cap"])
    agg = E.aggregate_trades([], None)
    assert S._stop_perdita(params, agg, True) == {
        "soglia": soglia, "chiave": "v3_daily_loss_cap", "scattato": False}
    agg_perdita = {**agg, "realized_today": -soglia}
    assert S._stop_perdita(params, agg_perdita, True)["scattato"] is True
    agg_quasi = {**agg, "realized_today": -soglia + 0.01}
    assert S._stop_perdita(params, agg_quasi, True)["scattato"] is False


def test_soglia_zero_non_scatta_mai():
    params = {"daily_loss_cap": 0.0, "strategy_version": 2}
    r = S._stop_perdita(params, {"realized_today": -10_000.0}, False)
    assert r == {"soglia": 0.0, "chiave": "daily_loss_cap", "scattato": False}


def test_il_bloccato_in_perdita_conta_come_per_la_decisione():
    """Stesso R della decisione (``E.realized_effective``): una perdita gia'
    bloccata dalle coperture fa scattare il freno come nelle aperture."""
    params = {"daily_loss_cap": 10.0, "strategy_version": 2}
    agg = {"realized_today": 0.0, "locked_pnl_open_today": -12.0}
    assert E.realized_effective(agg) <= -10.0
    assert S._stop_perdita(params, agg, False)["scattato"] is True


# ---------------------------------------------------------------------------
# il servizio intero: run_once scrive la chiave nella riga vera
# ---------------------------------------------------------------------------
def test_run_once_scrive_stop_perdita_scattato_e_non_apre():
    db = FakeDB(_riga_control(params={"daily_loss_cap": 10}))
    _perdita_di_oggi(db, -20.0)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res["placed"] == 0                                  # comportamento di prima
    assert any(k == "loss_stop" for k, _ in db.activity)
    sp = db.control["stats"]["stop_perdita"]
    assert sp == {"soglia": 10.0, "chiave": "daily_loss_cap", "scattato": True}
    assert isinstance(sp["soglia"], float) and isinstance(sp["scattato"], bool)


def test_run_once_stop_perdita_non_scattato():
    db = attiva_runner_paper(FakeDB(_riga_control(params={"daily_loss_cap": 10})))
    _perdita_di_oggi(db, -5.0)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert db.control["stats"]["stop_perdita"] == {
        "soglia": 10.0, "chiave": "daily_loss_cap", "scattato": False}


def test_bot_fermo_con_ultimi_parametri(monkeypatch):
    monkeypatch.setattr(S, "_ULTIMI_PARAMS", {"daily_loss_cap": 10.0, "engine": "single",
                                               "strategy_version": 2})
    db = FakeDB(_riga_control(status="stopped", params={"daily_loss_cap": 10}))
    _perdita_di_oggi(db, -20.0)
    st = S._idle_stats(db, db.control, NOW)
    assert st["stop_perdita"] == {"soglia": 10.0, "chiave": "daily_loss_cap", "scattato": True}
    assert st["bot_running"] is False


def test_bot_fermo_senza_parametri_tiene_il_precedente(monkeypatch):
    monkeypatch.setattr(S, "_ULTIMI_PARAMS", None)
    riga = _riga_control(status="stopped")
    riga["stats"] = {"stop_perdita": {"soglia": 5.0, "chiave": "daily_loss_cap",
                                      "scattato": False}}
    db = FakeDB(riga)
    st = S._idle_stats(db, db.control, NOW)
    assert st["stop_perdita"] == {"soglia": 5.0, "chiave": "daily_loss_cap", "scattato": False}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
