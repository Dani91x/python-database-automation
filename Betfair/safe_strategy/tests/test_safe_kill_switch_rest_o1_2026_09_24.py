"""O1 (24/09) - il kill-switch del worker (env + DB) davanti a OGNI place REST.

Reperto dell'audit delle strade dell'ordine: ``LIVE_KILL_SWITCH`` fermava il
worker della coda ma non Omega in ripiego REST; il kill-switch del DATABASE
(``betfair_live_settings.kill_switch``, quello della UI) non fermava nessuna
strada REST. Il freno e' uno solo (``controls.motivo_kill_switch``) e vale solo
per le APERTURE: le chiusure passano sempre (``_CLOSING_ACTIONS``).

Qui: ``safe_strategy.execution.place`` (Safe calcio/tennis e Mike, stessa
funzione), il freno condiviso, e la parita' a freno spento.
Ambiente dichiarato dal conftest della cartella: LIVE_ORDER_MODE=LIVE,
LIVE_KILL_SWITCH=false.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.omega import omega_market as M
from Betfair.safe_strategy import execution as X
from Betfair.stream.trading import controls as CTL

NOW = datetime(2026, 9, 24, 20, 0, tzinfo=timezone.utc)


class _Db:
    """Il minimo che ``X.place`` tocca sulla via REST (gate chiuso)."""

    def __init__(self) -> None:
        self.activity: list = []
        self.trades: dict = {}

    def log(self, kind, payload=None):
        self.activity.append((kind, payload or {}))

    def update_trade(self, trade_id, **fields):
        self.trades.setdefault(trade_id, {}).update(fields)

    def get_trade(self, trade_id):
        return self.trades.get(trade_id)

    # gate flumine: runner giu' -> ripiego REST (il caso del reperto)
    def live_follow_status(self, event_id):
        return "NONE"

    def runner_heartbeat(self):
        return None


class _Mercato:
    """Stessa firma e stesso ``PlaceResult`` di ``omega_market``."""

    def __init__(self) -> None:
        self.placed: list = []

    def place_order_live(self, **kw):
        self.placed.append(kw)
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-1",
                             size_matched=kw["size"], avg_price_matched=kw["price"])

    def place_submin_live(self, **kw):
        self.placed.append({**kw, "_submin": True})
        return M.PlaceResult(ok=True, order_status="EXECUTION_COMPLETE", bet_id="b-2",
                             size_matched=kw["size"], avg_price_matched=kw["price"])


def _place(mk, *, meta=None, size=5.0):
    return X.place(db=_Db(), market=mk, mode="live", event_id="1.1", market_id="m1",
                   selection_id=7, side="back", price=2.5, size=size, best_size=500.0,
                   client_ref="safe-t9", trade_id=9, meta=meta, now=NOW,
                   params={"execution_mode": "rest"})


def _kill_db(monkeypatch, attivo: bool):
    monkeypatch.setattr(CTL, "get_live_settings",
                        lambda *a, **k: {"kill_switch": attivo})


# ---------------------------------------------------------------------------
# Il freno condiviso
# ---------------------------------------------------------------------------
def test_motivo_kill_switch_env_e_db(monkeypatch):
    _kill_db(monkeypatch, False)
    assert CTL.motivo_kill_switch() is None
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    assert CTL.motivo_kill_switch() == "live_kill_switch_attivo"
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    _kill_db(monkeypatch, True)
    assert CTL.motivo_kill_switch() == "db_kill_switch_attivo"


def test_motivo_kill_switch_letto_a_caldo_dalla_cache_del_db(monkeypatch):
    """Stessa colonna e stessa cache che leggono i controlli nativi: il freno
    tirato dalla UI vale al giro dopo, senza riavvii."""
    monkeypatch.setitem(CTL._SETTINGS_CACHE, "ts", float("inf"))
    monkeypatch.setitem(CTL._SETTINGS_CACHE, "data", {"kill_switch": True})
    assert CTL.motivo_kill_switch() == "db_kill_switch_attivo"
    monkeypatch.setitem(CTL._SETTINGS_CACHE, "data", {"kill_switch": False})
    assert CTL.motivo_kill_switch() is None


def test_freno_illeggibile_ferma_l_apertura(monkeypatch):
    def _rotto(*a, **k):
        raise RuntimeError("settings rotti")

    monkeypatch.setattr(CTL, "get_live_settings", _rotto)
    assert CTL.motivo_kill_switch() == "kill_switch_illeggibile"


# ---------------------------------------------------------------------------
# X.place (Safe e Mike sulla via REST)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_kill_attivo_apertura_rest_rifiutata_con_motivo(monkeypatch, sorgente):
    if sorgente == "env":
        monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
        _kill_db(monkeypatch, False)
    else:
        _kill_db(monkeypatch, True)
    mk = _Mercato()
    out = _place(mk)
    assert out.status == "error"
    assert out.fill_note == ("live_kill_switch_attivo" if sorgente == "env"
                        else "db_kill_switch_attivo")
    assert mk.placed == [], "a kill-switch attivo nessuna apertura arriva a Betfair"


@pytest.mark.parametrize("meta", [{"closes_trade_id": 3}, {"cashout": True}])
def test_kill_attivo_la_chiusura_rest_passa(monkeypatch, meta):
    _kill_db(monkeypatch, True)
    monkeypatch.setenv("LIVE_KILL_SWITCH", "true")
    mk = _Mercato()
    out = _place(mk, meta=meta)
    assert out.status == "open"
    assert len(mk.placed) == 1, "il freno non deve mai impedire di chiudere"


def test_kill_attivo_anche_il_sotto_minimo_si_ferma(monkeypatch):
    _kill_db(monkeypatch, True)
    mk = _Mercato()
    out = _place(mk, size=0.73)
    assert out.status == "error" and out.fill_note == "db_kill_switch_attivo"
    assert mk.placed == []


def test_kill_spento_parita_col_comportamento_di_oggi(monkeypatch):
    _kill_db(monkeypatch, False)
    mk = _Mercato()
    out = _place(mk)
    assert out.status == "open"
    assert mk.placed == [{"market_id": "m1", "selection_id": 7, "price": 2.5, "size": 5.0,
                          "event_id": "1.1", "side": "back", "customer_ref": "safe-t9"}]


def test_live_brake_resta_anche_il_freno_della_modalita(monkeypatch):
    """Il freno del DB si AGGIUNGE: LIVE_ORDER_MODE resta com'era."""
    _kill_db(monkeypatch, False)
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    assert X._live_brake() == "live_order_mode_non_live:PAPER"
    _kill_db(monkeypatch, True)
    assert X._live_brake() == "db_kill_switch_attivo"
