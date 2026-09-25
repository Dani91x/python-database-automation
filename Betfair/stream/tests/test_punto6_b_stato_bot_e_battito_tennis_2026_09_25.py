"""Punto 6 dell'audit tempo reale (25/09) - PATCH B: bot Omega/Safe e runner tennis.

* ``omega_stato`` e ``safe_stato`` portano anche ``control`` = {status, mode,
  params, updated_at} della riga di control GIA' LETTA a inizio giro (come
  ``mike_stato``). Provato sul ``run_once`` VERO dei due bot, con i finti dei
  loro test e la riga costruita dalle COLONNE VERE della migrazione
  (``riga_control``).
* Il runner tennis in attesa pubblica ``battito`` sul suo canale (47332), con le
  stesse chiavi del calcio (``canale_bot.battito_runner``). Provato su
  ``setup_and_run`` VERO, fermato al primo sonno del giro di attesa.

Nessuna strategia toccata: solo pubblicazione di dati gia' in memoria.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.stream import canale_bot as CB
from Betfair.stream import local_channel as LC
from Betfair.stream.tests.test_avvio_app_2026_09_16 import riga_control

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_FINTI_UI = os.path.join(_RADICE, "frontend", "src", "lib", "__fixtures__",
                         "statoBotCanaleFinti.json")
T_RIGA = "2026-09-25T13:00:05.123456+00:00"


def _registra(monkeypatch) -> List[Tuple[str, Any]]:
    usciti: List[Tuple[str, Any]] = []

    def _publish(topic: str, payload: Any) -> None:
        json.dumps({"t": topic, "d": payload}, default=str)   # come il vero
        usciti.append((topic, payload))
    monkeypatch.setattr(LC, "publish", _publish)
    return usciti


# ------------------------------------------------------------------ Omega
def _omega_giro(monkeypatch) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from Betfair.omega import omega_service as S
    from Betfair.omega.test_omega_service import (
        NOW, FakeDB, FakeMarket, _cs, _event, _open_snapshot,
    )
    usciti = _registra(monkeypatch)
    riga = riga_control("omega_control", id=1, status="running", mode="paper",
                        daily_goal=250, params={"stake_lay": 1.0}, updated_at=T_RIGA)
    db = FakeDB(riga)
    S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    stati = [d for t, d in usciti if t == "omega_stato"]
    assert stati, usciti
    return stati[-1], riga


def test_omega_stato_porta_le_colonne_della_riga_letta(monkeypatch):
    msg, riga = _omega_giro(monkeypatch)
    assert set(msg.keys()) == {"stats", "last_cycle", "control"}
    assert set(msg["control"].keys()) == {"status", "mode", "params", "updated_at"}
    for k in ("status", "mode", "params", "updated_at"):
        assert msg["control"][k] == riga[k], k
    # gli stats restano quelli di sempre (lo STESSO oggetto del set_control)
    assert msg["stats"]["last_cycle"] == msg["last_cycle"]


def test_omega_senza_control_il_messaggio_resta_quello_di_prima(monkeypatch):
    from Betfair.omega import omega_service as S
    usciti = _registra(monkeypatch)
    S._pubblica_stato({"last_cycle": "x"}, "x")
    assert usciti == [("omega_stato", {"stats": {"last_cycle": "x"}, "last_cycle": "x"})]


# ------------------------------------------------------------------- Safe
def _safe_giro(monkeypatch) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    from Betfair.safe_strategy import bot_service as S
    from Betfair.safe_strategy.tests.test_bot_service import (
        NOW, FakeDB, FakeMarket, _feed_row, _reset_module_state,
    )
    _reset_module_state()
    S._GUARDIA_AVVIO.azzera()
    usciti = _registra(monkeypatch)
    db = FakeDB(status="running", mode="paper")
    db.control = riga_control("safe_strategy_control", id=1, status="running", mode="paper",
                              params={"variants": ["base"], "strategy_modes": {"base": "paper"}},
                              updated_at=T_RIGA)
    db.scan_rows = [_feed_row()]
    try:
        S.run_once(db=db, market=FakeMarket(), now=NOW)
    finally:
        _reset_module_state()
        S._GUARDIA_AVVIO.azzera()
    stati = [d for t, d in usciti if t == "safe_stato"]
    assert stati, usciti
    return stati[-1], db.control


def test_safe_stato_porta_le_colonne_della_riga_letta(monkeypatch):
    msg, riga = _safe_giro(monkeypatch)
    assert set(msg.keys()) == {"stats", "last_cycle", "control"}
    assert set(msg["control"].keys()) == {"status", "mode", "params", "updated_at"}
    assert msg["control"]["updated_at"] == T_RIGA
    assert msg["control"]["mode"] == "paper"
    assert msg["control"]["params"] == riga["params"]


def test_safe_senza_control_il_messaggio_resta_quello_di_prima(monkeypatch):
    from Betfair.safe_strategy import bot_service as S
    usciti = _registra(monkeypatch)
    S._pubblica_stato({"last_cycle": "x"}, "x")
    assert usciti == [("safe_stato", {"stats": {"last_cycle": "x"}, "last_cycle": "x"})]


def test_canale_che_solleva_non_ferma_i_bot(monkeypatch):
    from Betfair.omega import omega_service as SO
    from Betfair.safe_strategy import bot_service as SS

    def _rotto(*_a, **_k):
        raise OSError("socket chiuso")
    monkeypatch.setattr(LC, "publish", _rotto)
    riga = riga_control("omega_control", id=1, status="running", updated_at=T_RIGA)
    SO._pubblica_stato({}, "x", riga)
    SS._pubblica_stato({}, "x", riga)


# ----------------------------------------------------------- runner tennis
class _Fermo(Exception):
    """Ferma ``setup_and_run`` al primo sonno del giro di attesa."""


class _CanaleTennis(LC.LocalChannel):
    def __init__(self) -> None:
        super().__init__(47332, "tennis")
        self.usciti: List[Tuple[str, Any]] = []

    def publish(self, topic: str, payload: Any) -> None:  # type: ignore[override]
        json.dumps({"t": topic, "d": payload}, default=str)
        self.usciti.append((topic, payload))


def _tennis_fino_al_sonno(monkeypatch, follows: List[Dict[str, Any]]) -> _CanaleTennis:
    from Betfair.stream.tennis_live import tennis_runner as TR
    from Betfair.stream.tennis_live import tennis_bot_service as TBS

    ch = _CanaleTennis()

    def _start(port, sport, solo_lettura=False):
        assert (port, sport) == (47332, "tennis")
        monkeypatch.setattr(LC, "_CHANNEL", ch)
        return ch
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "OFF")
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setattr(TR, "build_client", lambda login=True: object())
    monkeypatch.setattr(TBS, "ferma_bot_al_nuovo_avvio", lambda *a, **k: None)
    monkeypatch.setattr(TR, "_cleanup_orphan_bot_controls", lambda: None)
    monkeypatch.setattr(TR, "_avvia_sveglia_armamento", lambda s: None)
    monkeypatch.setattr(TR, "_announce_order_mode", lambda m: None)
    monkeypatch.setattr(TR, "_catalog_follow", lambda s, f: None)
    monkeypatch.setattr(TR, "safe_logout", lambda t: None)
    monkeypatch.setattr(TR.tennis_db, "list_pending_tennis_follows", lambda: list(follows))
    monkeypatch.setattr(LC, "start_channel", _start)
    sonni: List[float] = []

    def _sonno(s):
        sonni.append(s)
        raise _Fermo()
    monkeypatch.setattr(TR.time, "sleep", _sonno)
    with pytest.raises(_Fermo):
        TR.setup_and_run()
    assert sonni, "il giro di attesa non e' stato raggiunto"
    return ch


def test_tennis_in_attesa_senza_eventi_pubblica_il_battito(monkeypatch):
    ch = _tennis_fino_al_sonno(monkeypatch, [])
    battiti = [d for t, d in ch.usciti if t == "battito"]
    assert len(battiti) == 1, ch.usciti
    b = battiti[0]
    assert tuple(b.keys()) == CB.CHIAVI_BATTITO
    assert isinstance(b["ts"], int)
    assert b["mode"] == "OFF" == ch._hello_extra["mode"]     # la modalita' dell'hello
    assert b["streaming"] == 0


def test_tennis_in_attesa_senza_mercati_pubblica_il_battito(monkeypatch):
    ch = _tennis_fino_al_sonno(monkeypatch, [{"event_id": "35000001"}])
    battiti = [d for t, d in ch.usciti if t == "battito"]
    assert len(battiti) == 1, ch.usciti
    assert battiti[0]["streaming"] == 0


def test_tennis_battito_senza_canale_nessun_errore(monkeypatch):
    from Betfair.stream.tennis_live import tennis_runner as TR
    monkeypatch.setattr(LC, "_CHANNEL", None)
    CB.azzera_statistiche()
    TR._pubblica_battito_attesa()
    assert CB.statistiche()["pubblicati"] == 0
    assert CB.statistiche()["errori"] == 0


# ---------------------------------------------- finti del frontend = veri
def test_i_finti_del_frontend_hanno_le_chiavi_dei_messaggi_veri(monkeypatch):
    with open(_FINTI_UI, encoding="utf-8") as fh:
        finti = json.load(fh)
    omega, _ = _omega_giro(monkeypatch)
    safe, _ = _safe_giro(monkeypatch)
    for nome, vero in (("omega_stato", omega), ("safe_stato", safe)):
        assert set(finti[nome].keys()) == set(vero.keys()), nome
        assert set(finti[nome]["control"].keys()) == set(vero["control"].keys()), nome
        for k, v in vero["control"].items():
            assert type(finti[nome]["control"][k]) is type(v), (nome, k)
