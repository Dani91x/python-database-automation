"""Punto 6 dell'audit tempo reale (25/09) - lato RUNNER calcio.

Due topic nuovi sul canale locale del runner (47331), entrambi STATO DEL
PROCESSO gia' in memoria, nessun IO in piu':

* ``battito`` ``{ts, mode, streaming}`` dove si scrive ``betfair_live_heartbeat``
  (``runner.heartbeat_worker`` e ``runner._battito_in_attesa``);
* ``modo_ordini`` = ``modo_ordini.stato_corrente()`` + ``ts``, SOLO AL CAMBIO,
  dove il worker lo registra (``live_order_worker._refresh_settings``).

Il canale finto e' un ``LocalChannel`` VERO (non avviato) con il solo
``publish`` registrato: ``set_hello``/``_hello_extra`` sono quelli veri.
Il JSON dei finti del frontend (``frontend/src/lib/__fixtures__/runnerCanaleFinti.json``)
deve avere le STESSE chiavi dei messaggi veri: lo controlla l'ultimo test.
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple

import pytest

from Betfair.stream import canale_bot as CB
from Betfair.stream import live_order_worker as W
from Betfair.stream import local_channel as LC
from Betfair.stream import modo_ordini as MO
from Betfair.stream import runner as R

_RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_FINTI_UI = os.path.join(_RADICE, "frontend", "src", "lib", "__fixtures__",
                         "runnerCanaleFinti.json")


class _CanaleRegistrato(LC.LocalChannel):
    """Il canale VERO, non avviato, con ``publish`` che registra."""

    def __init__(self) -> None:
        super().__init__(47331, "calcio")
        self.usciti: List[Tuple[str, Any]] = []

    def publish(self, topic: str, payload: Any) -> None:  # type: ignore[override]
        # come il vero: il payload deve essere serializzabile (json.dumps)
        json.dumps({"t": topic, "d": payload}, default=str)
        self.usciti.append((topic, payload))


@pytest.fixture
def canale(monkeypatch):
    ch = _CanaleRegistrato()
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    CB.azzera_statistiche()
    yield ch
    CB.azzera_statistiche()


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    MO.azzera()
    monkeypatch.setattr(W, "_MODO_CANALE_FIRMA", None)
    monkeypatch.setenv("LIVE_ORDER_MODE", "LIVE")
    yield
    MO.azzera()


def _battiti(ch: _CanaleRegistrato) -> List[Dict[str, Any]]:
    return [d for t, d in ch.usciti if t == "battito"]


def _modi(ch: _CanaleRegistrato) -> List[Dict[str, Any]]:
    return [d for t, d in ch.usciti if t == "modo_ordini"]


def _ambiente_worker(monkeypatch, upsert=None):
    """``heartbeat_worker`` senza rete: niente keepAlive, recorder spento."""
    import Betfair.stream.raw_listener as RL

    monkeypatch.setattr(R, "_STREAM_KA_LAST", _time.monotonic())
    monkeypatch.setattr(R.db, "upsert_live_heartbeat", upsert or (lambda **k: None))
    monkeypatch.setattr(RL.RAW_STATE, "health", lambda: {"enabled": False})
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    return R.LiveSession()


# ---------------------------------------------------------------- battito
def test_battito_a_ogni_giro_del_heartbeat_worker_con_le_chiavi_giuste(canale, monkeypatch):
    session = _ambiente_worker(monkeypatch)
    prima = int(_time.time() * 1000)
    R.heartbeat_worker({}, None, session)
    R.heartbeat_worker({}, None, session)
    dopo = int(_time.time() * 1000)
    b = _battiti(canale)
    assert len(b) == 2, canale.usciti
    for m in b:
        assert tuple(m.keys()) == CB.CHIAVI_BATTITO == ("ts", "mode", "streaming")
        assert isinstance(m["ts"], int) and prima <= m["ts"] <= dopo
        assert m["mode"] == R.heartbeat_mode() == "LIVE+PAPER"
        assert m["streaming"] == 0


def test_battito_esce_anche_col_database_giu(canale, monkeypatch):
    def _ko(**_k):
        raise RuntimeError("503 PGRST002")
    session = _ambiente_worker(monkeypatch, upsert=_ko)
    R.heartbeat_worker({}, None, session)
    assert len(_battiti(canale)) == 1


def test_battito_in_attesa_alla_cadenza_del_heartbeat(canale, monkeypatch):
    scritti = []
    monkeypatch.setattr(R.db, "upsert_live_heartbeat", lambda **k: scritti.append(k))
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    monkeypatch.setattr(R, "HEARTBEAT_SEC", 10.0)
    session = R.LiveSession()
    R._battito_in_attesa(session, 1000.0)
    R._battito_in_attesa(session, 1005.0)      # dentro la cadenza: niente
    R._battito_in_attesa(session, 1010.0)      # cadenza compiuta: battito
    b = _battiti(canale)
    assert len(b) == 2 == len(scritti)
    assert all(tuple(m.keys()) == CB.CHIAVI_BATTITO for m in b)
    assert all(m["mode"] == scritti[0]["mode"] for m in b)   # stesso mode del DB
    assert all(m["streaming"] == 0 for m in b)               # in attesa: nessuna partita


def test_streaming_conta_le_partite_della_memoria_del_runner(canale, monkeypatch):
    from Betfair.stream import auto_follow as AF

    piano = AF.PianoFollow(tetto=50)
    esito = piano.richiedi("E3", {"1.30"}, priorita=1, protetti=set(),
                           puo_espellere=False, ora=_time.monotonic())
    assert esito.ok
    auto = SimpleNamespace(piano=piano)
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": auto})
    session = R.LiveSession()
    session.cataloged_events.update({"E1", "E2"})
    session.finished_events.add("E2")
    assert R._partite_in_streaming(session) == 2          # E1 manuale + E3 auto
    R._pubblica_battito(session)
    assert _battiti(canale)[-1]["streaming"] == 2


def test_streaming_non_contabile_vale_none_non_zero(monkeypatch):
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    rotta = SimpleNamespace(cataloged_events=object(), finished_events=set())
    assert R._partite_in_streaming(rotta) is None
    assert CB.battito_runner("LIVE+PAPER", None)["streaming"] is None


def test_canale_assente_nessuna_chiamata_nessun_errore(monkeypatch):
    monkeypatch.setattr(LC, "_CHANNEL", None)
    CB.azzera_statistiche()
    session = _ambiente_worker(monkeypatch)
    R.heartbeat_worker({}, None, session)
    R._battito_in_attesa(session, 5000.0)
    MO.registra_settings({"order_mode": "PAPER"})
    assert W._pubblica_modo_ordini_se_cambiato() is False
    # la firma NON si segna senza canale: al primo canale il modo esce
    assert W._MODO_CANALE_FIRMA is None
    st = CB.statistiche()
    assert st["pubblicati"] == 0 and st["errori"] == 0


def test_canale_che_solleva_non_ferma_il_runner(monkeypatch):
    class _Rotto(_CanaleRegistrato):
        def publish(self, topic, payload):  # type: ignore[override]
            raise OSError("socket chiuso")
    monkeypatch.setattr(LC, "_CHANNEL", _Rotto())
    CB.azzera_statistiche()
    session = _ambiente_worker(monkeypatch)
    R.heartbeat_worker({}, None, session)          # non solleva
    assert CB.statistiche()["errori"] == 1


# ------------------------------------------------------------ modo ordini
class _SbFinto:
    """``sb.rpc('get_live_settings', {}).execute().data`` come PostgREST: la
    riga di ``betfair_live_settings`` (migrations/live_order_mode_control_2026-09-24.sql)."""

    def __init__(self) -> None:
        self.riga: Dict[str, Any] = {
            "kill_switch": False, "order_mode": "PAPER",
            "order_mode_updated_at": "2026-09-25T12:00:00.123456+00:00",
            "order_mode_updated_by": "avvio_app",
        }
        self.errore = False

    def rpc(self, nome, _args):
        assert nome == "get_live_settings"
        sb = self

        class _Q:
            def execute(self_inner):
                if sb.errore:
                    raise RuntimeError("DB giu'")
                return SimpleNamespace(data=dict(sb.riga))
        return _Q()


def test_modo_ordini_solo_al_cambio(canale):
    sb = _SbFinto()
    W._refresh_settings(sb)
    W._refresh_settings(sb)                    # due giri uguali: UNA pubblicazione
    m = _modi(canale)
    assert len(m) == 1
    atteso = set(MO.stato_corrente().keys()) | {"ts"}
    assert set(m[0].keys()) == atteso
    assert m[0]["effettivo"] == "PAPER" and m[0]["tetto_ambiente"] == "LIVE"
    assert m[0]["scelto_ui"] == "PAPER" and m[0]["motivo"] == "ok"
    assert isinstance(m[0]["ts"], int)
    # chi si collega dopo lo riceve nell'hello (il vero ``_hello_extra``)
    assert canale._hello_extra["modo_ordini"] == m[0]

    sb.riga.update({"order_mode": "LIVE", "order_mode_updated_by": "utente",
                    "order_mode_updated_at": "2026-09-25T12:05:00+00:00"})
    W._refresh_settings(sb)
    m = _modi(canale)
    assert len(m) == 2
    assert m[1]["effettivo"] == "LIVE" and m[1]["scelto_ui_da"] == "utente"
    W._refresh_settings(sb)
    assert len(_modi(canale)) == 2


def test_modo_ordini_lettura_scaduta_esce_off(canale, monkeypatch):
    sb = _SbFinto()
    orologio = {"t": 100.0}
    monkeypatch.setattr(MO, "_ora", lambda: orologio["t"])
    W._refresh_settings(sb)
    sb.errore = True
    orologio["t"] += MO.VALIDITA_S + 1         # la lettura buona scade
    W._refresh_settings(sb)
    m = _modi(canale)
    assert [x["effettivo"] for x in m] == ["PAPER", "OFF"]
    assert m[1]["motivo"] == "db_assente"


def test_modo_ordini_mai_sul_canale_del_runner_tennis(monkeypatch):
    """Il runner tennis rilegge i settings con la stessa funzione (kill-switch),
    ma il suo tetto e' TENNIS_LIVE_ORDER_MODE: il modo del calcio sul 47332
    sarebbe falso. Canale tennis -> nessun messaggio, firma non segnata."""
    ch = _CanaleRegistrato()
    ch.sport = "tennis"
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    W._refresh_settings(_SbFinto())
    assert _modi(ch) == []
    assert "modo_ordini" not in ch._hello_extra
    assert W._MODO_CANALE_FIRMA is None


def test_modo_ordini_nessuna_lettura_in_piu(canale):
    chiamate = []

    class _Contato(_SbFinto):
        def rpc(self, nome, args):
            chiamate.append(nome)
            return super().rpc(nome, args)
    sb = _Contato()
    W._refresh_settings(sb)
    assert chiamate == ["get_live_settings"]   # la sola lettura che c'era gia'


# ---------------------------------------------- finti del frontend = veri
def test_i_finti_del_frontend_hanno_le_chiavi_dei_messaggi_veri(canale):
    with open(_FINTI_UI, encoding="utf-8") as fh:
        finti = json.load(fh)
    vero_battito = CB.battito_runner("LIVE+PAPER", 2)
    assert set(finti["battito"].keys()) == set(vero_battito.keys())
    for k, v in vero_battito.items():
        assert type(finti["battito"][k]) is type(v), k
    sb = _SbFinto()
    W._refresh_settings(sb)
    vero_modo = _modi(canale)[0]
    for nome in ("modo_ordini", "modo_ordini_live"):
        assert set(finti[nome].keys()) == set(vero_modo.keys()), nome
    assert set(finti["hello"].keys()) >= {"sport", "mode", "modo_ordini"}
    assert set(finti["hello"]["modo_ordini"].keys()) == set(vero_modo.keys())
