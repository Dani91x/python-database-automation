"""R-STREAM-1 (26/09): stallo dello stream rilevato SEMPRE, ricostruzione che
escala a un processo nuovo, stessa forma nel tennis; guasti di rete nel ciclo
principale che non uccidono piu' il processo.

Reperto: alle 10:41:41Z una caduta di rete ha lasciato il runner calcio con
battito vivo e ZERO dati per 4 ore (il controllo di stallo era gatato da
``RAW_STATE.enabled and session.market_to_event``: con i soli mercati
dell'auto-follow la mappa manuali era vuota); la ricostruzione delle 14:39Z
non ha ridato dati; il tennis non aveva alcun controllo.

Finti con le chiavi del vero: messaggi grezzi Betfair (``op/clk/pt/ct/mc``),
``RAW_STATE``/``RAW_TEE`` VERI (``_RawState``/``TennisRawTee``), ``LiveSession``
e ``TennisLiveSession`` VERE; finti solo flumine (``markets``/``handler_queue``)
e DB (``insert_alert``/``upsert_live_heartbeat``, stesse firme di stream/db.py).
"""
from __future__ import annotations

import json
import queue
import time
from types import SimpleNamespace
from typing import Any, List, Tuple

import pytest

import Betfair.stream.raw_listener as RL
import Betfair.stream.runner as R
from Betfair.stream.raw_listener import _RawState
from Betfair.stream.runner_lifecycle import (
    MSG_DATI,
    MSG_HEARTBEAT,
    VERDETTO_ATTENDI,
    VERDETTO_ESCALA,
    VERDETTO_GUARITO,
    classifica_messaggio_stream,
    e_errore_di_rete,
    verdetto_post_ricostruzione,
)
from Betfair.stream.tennis_live import tennis_recorder as TREC
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tennis_recorder import TennisRawTee

MARKET_ID = "1.250000001"


def _mcm_compatto(pt: int) -> str:
    # forma reale dello stream Betfair: JSON compatto
    return json.dumps({"op": "mcm", "id": 2, "clk": "AAA", "pt": pt,
                       "mc": [{"id": MARKET_ID, "rc": [{"id": 1, "ltp": 2.0}]}]},
                      separators=(",", ":"))


def _mcm_spazi(pt: int) -> str:
    return json.dumps({"op": "mcm", "clk": "1", "pt": pt,
                       "mc": [{"id": MARKET_ID, "rc": [{"id": 1, "ltp": 2.0}]}]})


def _heartbeat(pt: int) -> str:
    return json.dumps({"op": "mcm", "id": 2, "clk": "AAA", "pt": pt, "ct": "HEARTBEAT"},
                      separators=(",", ":"))


# ---------------------------------------------------------------------------
# 1) funzioni pure
# ---------------------------------------------------------------------------
def test_classifica_messaggio_stream() -> None:
    assert classifica_messaggio_stream(_mcm_compatto(1)) == MSG_DATI
    assert classifica_messaggio_stream(_mcm_spazi(1)) == MSG_DATI
    assert classifica_messaggio_stream(_heartbeat(1)) == MSG_HEARTBEAT
    assert classifica_messaggio_stream(json.dumps({"op": "mcm", "pt": 1, "mc": []})) is None
    assert classifica_messaggio_stream('{"op":"status","statusCode":"SUCCESS"}') is None
    assert classifica_messaggio_stream('{"op":"connection","connectionId":"x"}') is None
    assert classifica_messaggio_stream(None) is None
    assert classifica_messaggio_stream(b'{"op":"mcm"}') is None


@pytest.mark.parametrize("stall,dati,since,atteso", [
    (None, False, 100.0, VERDETTO_ATTENDI),     # finestra non ancora passata
    (999.0, False, 179.9, VERDETTO_ATTENDI),
    (5.0, False, 180.0, VERDETTO_ESCALA),       # nessun dato dopo il rebuild (subscription rotta)
    (200.0, True, 200.0, VERDETTO_ESCALA),      # 26/09: pochi ladder poi tutto fermo
    (180.0, True, 181.0, VERDETTO_ESCALA),
    (179.0, True, 300.0, VERDETTO_ATTENDI),     # mercato quieto con heartbeat: si osserva
    (10.0, True, 900.0, VERDETTO_GUARITO),      # osservazione conclusa
    (None, True, 900.0, VERDETTO_GUARITO),
])
def test_verdetto_post_ricostruzione(stall: Any, dati: bool, since: float, atteso: str) -> None:
    assert verdetto_post_ricostruzione(stall, dati, since, 180.0, 900.0) == atteso


def test_verdetto_spento_con_finestra_zero() -> None:
    assert verdetto_post_ricostruzione(9999.0, False, 9999.0, 0.0, 900.0) == VERDETTO_GUARITO


def test_e_errore_di_rete() -> None:
    import httpx
    import requests

    assert e_errore_di_rete(ConnectionError("reset"))
    assert e_errore_di_rete(TimeoutError("t"))
    assert e_errore_di_rete(httpx.ConnectError("getaddrinfo failed"))
    assert e_errore_di_rete(requests.ConnectionError("dns"))
    assert e_errore_di_rete(RuntimeError(
        "Betting RPC failed after 3 retries. Last error: Network error: dns"))
    try:
        try:
            raise httpx.ReadTimeout("lento")
        except httpx.ReadTimeout as inner:
            raise ValueError("avvolto") from inner
    except ValueError as outer:
        assert e_errore_di_rete(outer), "la causa di rete si legge nella catena"
    # NON rete: si rilancia
    assert not e_errore_di_rete(KeyError("event_id"))
    assert not e_errore_di_rete(ValueError("x"))
    assert not e_errore_di_rete(FileNotFoundError("raw"))
    assert not e_errore_di_rete(RuntimeError(
        "Betting RPC failed after 3 retries. Last error: RPC error: {'code': -32099}"))


# ---------------------------------------------------------------------------
# 2) il battito si aggiorna anche a registrazione SPENTA (calcio e tennis)
# ---------------------------------------------------------------------------
def test_raw_state_spento_aggiorna_il_battito(tmp_path: Any) -> None:
    st = _RawState()
    st.configure(str(tmp_path), {MARKET_ID: "E1"}, False)
    prima = int(time.time() * 1000)
    st.write_message(_heartbeat(5))
    assert st.last_heartbeat_ms >= prima and st.last_data_ms == 0
    st.write_message(_mcm_compatto(6))
    assert st.last_data_ms >= prima
    assert st.health()["last_data_ms"] == st.last_data_ms
    assert list(tmp_path.iterdir()) == [], "registrazione spenta: niente su disco"


def test_raw_state_senza_cartella_aggiorna_il_battito() -> None:
    st = _RawState()   # mai configurato: dir None, enabled False
    st.write_message(_mcm_compatto(6))
    assert st.last_data_ms > 0


def test_tee_tennis_senza_registrazioni_aggiorna_il_battito() -> None:
    tee = TennisRawTee()
    assert not tee.enabled_events
    tee.write_message(_heartbeat(1))
    assert tee.last_heartbeat_ms > 0 and tee.last_data_ms == 0
    tee.write_message(_mcm_compatto(2))
    assert tee.last_data_ms > 0


# ---------------------------------------------------------------------------
# 3) runner calcio: heartbeat_worker
# ---------------------------------------------------------------------------
class _FakeDb:
    """Stesse firme di Betfair/stream/db.py (insert_alert, upsert_live_heartbeat)."""

    def __init__(self) -> None:
        self.alerts: List[Tuple[str, str, str]] = []

    def insert_alert(self, level: str, code: str, message: str,
                     event_id: Any = None, **_kw: Any) -> None:
        self.alerts.append((level, code, message))

    def upsert_live_heartbeat(self, *, runner: bool, pid: int, mode: Any = None) -> None:
        return None


class _FakeFlumine:
    def __init__(self) -> None:
        self.markets: List[Any] = []
        self.handler_queue: "queue.Queue[Any]" = queue.Queue()
        self._running = True


@pytest.fixture()
def calcio(monkeypatch: Any, tmp_path: Any) -> SimpleNamespace:
    fdb = _FakeDb()
    monkeypatch.setattr(R, "db", fdb)
    st = _RawState()
    st.configure(str(tmp_path), {}, False)        # tee raw SPENTO
    monkeypatch.setattr(RL, "RAW_STATE", st)
    monkeypatch.setattr(R, "_RAW_STALL_LAST_RESTART", -1e9)
    monkeypatch.setattr(R, "_RAW_STALL_ALERTED", False)
    monkeypatch.setattr(R, "_STREAM_KA_LAST", time.monotonic())   # niente keepAlive
    monkeypatch.setattr(R, "_pubblica_battito", lambda s: None)
    monkeypatch.setattr(R, "_lifecycle_blockers", lambda fw, fresh=False: None)
    soft: List[str] = []

    def _soft(fw: Any, session: Any, reason: str) -> Any:
        soft.append(reason)
        return None

    monkeypatch.setattr(R, "_request_soft_restart", _soft)
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    s = R.LiveSession()
    s.stream_market_count = 32                     # 26/09: solo mercati auto-follow
    s.stream_started_monotonic = time.monotonic() - 1000.0
    return SimpleNamespace(db=fdb, st=st, session=s, soft=soft, fw=_FakeFlumine())


def test_stallo_misurato_senza_tee_e_senza_mercati_manuali(calcio: SimpleNamespace) -> None:
    assert calcio.session.market_to_event == {}
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert len(calcio.soft) == 1, "stream muto da 1000s: la ricostruzione DEVE partire"
    assert calcio.session.stallo_rebuild_mono is not None
    assert any(lv == "CRITICAL" for lv, _c, _m in calcio.db.alerts)


def test_stream_vivo_a_tee_spento_non_ricostruisce(calcio: SimpleNamespace) -> None:
    calcio.st.write_message(_heartbeat(1))
    calcio.st.write_message(_mcm_compatto(2))
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert calcio.soft == []
    assert calcio.db.alerts == []


def test_heartbeat_freschi_dati_fermi_sotto_cap_non_ricostruisce(calcio: SimpleNamespace) -> None:
    calcio.st.last_data_ms = int(time.time() * 1000) - 700_000      # 700s < cap 1800
    calcio.st.write_message(_heartbeat(1))
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert calcio.soft == [], "mercato quieto con heartbeat freschi: nessun restart"


def test_nessun_mercato_sottoscritto_nessun_controllo(calcio: SimpleNamespace) -> None:
    calcio.session.stream_market_count = 0
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert calcio.soft == []


def test_mercati_sottoscritti() -> None:
    s = SimpleNamespace(market_to_event={"1.1": "E", "1.2": "E"}, stream_market_count=0)
    assert R._mercati_sottoscritti(s) == 2
    s.stream_market_count = 32
    assert R._mercati_sottoscritti(s) == 32


def _in_osservazione(calcio: SimpleNamespace, secondi_fa: float) -> None:
    calcio.session.stallo_rebuild_mono = time.monotonic() - secondi_fa
    calcio.session.stream_started_monotonic = time.monotonic() - secondi_fa + 5.0


def test_escalation_nessun_dato_dopo_rebuild_esce_con_75(calcio: SimpleNamespace) -> None:
    _in_osservazione(calcio, 200.0)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    s = calcio.session
    assert s.shutdown_requested.is_set()
    assert s.planned_restart is True and s.riavvio_per_stallo is True
    assert calcio.soft == [], "in osservazione: niente seconda ricostruzione"
    assert not calcio.fw.handler_queue.empty(), "TerminationEvent accodato"
    assert any("riavvio del processo" in m for _l, _c, m in calcio.db.alerts)


def test_escalation_attende_la_finestra(calcio: SimpleNamespace) -> None:
    _in_osservazione(calcio, 60.0)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert not calcio.session.shutdown_requested.is_set()
    assert calcio.soft == []


def test_escalation_guarisce_con_dati_vivi(calcio: SimpleNamespace) -> None:
    _in_osservazione(calcio, 950.0)
    calcio.st.write_message(_heartbeat(1))
    calcio.st.write_message(_mcm_compatto(2))
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert not calcio.session.shutdown_requested.is_set()
    assert calcio.session.stallo_rebuild_mono is None


def test_escalation_bloccata_da_ordini_vivi(calcio: SimpleNamespace, monkeypatch: Any) -> None:
    monkeypatch.setattr(R, "_lifecycle_blockers",
                        lambda fw, fresh=False: "1 ordini vivi sul mercato 1.250000001")
    _in_osservazione(calcio, 200.0)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    s = calcio.session
    assert not s.shutdown_requested.is_set(), "MAI uscire con ordini vivi"
    assert s.planned_restart is False
    rinvii = [m for lv, _c, m in calcio.db.alerts if lv == "CRITICAL" and "RINVIATO" in m]
    assert len(rinvii) == 1, "alert di rinvio al piu' ogni 5 minuti"
    assert s.stallo_rebuild_mono is not None, "si ritenta al prossimo giro"


def test_escalation_blocker_comparso_al_check_finale(calcio: SimpleNamespace,
                                                   monkeypatch: Any) -> None:
    monkeypatch.setattr(R, "_lifecycle_blockers",
                        lambda fw, fresh=False: "regole armate" if fresh else None)
    _in_osservazione(calcio, 200.0)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert not calcio.session.shutdown_requested.is_set()


def test_escalation_senza_watchdog_non_esce(calcio: SimpleNamespace, monkeypatch: Any) -> None:
    monkeypatch.delenv("LIVE_RUNNER_KEEP_ALIVE", raising=False)
    _in_osservazione(calcio, 200.0)
    R.heartbeat_worker({}, calcio.fw, calcio.session)
    assert not calcio.session.shutdown_requested.is_set()
    assert calcio.session.stallo_rebuild_mono is None


def test_attendi_se_rete(monkeypatch: Any) -> None:
    dormite: List[float] = []
    monkeypatch.setattr(R.time, "sleep", lambda s: dormite.append(s))
    R._attendi_se_rete("lettura dei follow", ConnectionError("dns"))
    assert dormite == [R._ATTESA_RETE_SEC]
    with pytest.raises(KeyError):
        R._attendi_se_rete("lettura dei follow", KeyError("event_id"))


# ---------------------------------------------------------------------------
# 4) runner tennis: stall_worker
# ---------------------------------------------------------------------------
@pytest.fixture()
def tennis(monkeypatch: Any) -> SimpleNamespace:
    tee = TennisRawTee()
    monkeypatch.setattr(TR, "RAW_TEE", tee)
    monkeypatch.setattr(TREC, "RAW_TEE", tee)
    alerts: List[Tuple[str, str]] = []
    monkeypatch.setattr(TR, "_alert_stallo_tennis", lambda lv, m: alerts.append((lv, m)))
    richieste: List[str] = []

    def _req(fw: Any, session: Any, reason: str, forza: bool = True) -> bool:
        richieste.append(reason)
        assert forza is False, "lo stallo non forza mai il restart"
        return True

    monkeypatch.setattr(TR, "_request_restart", _req)
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fw, s: [])
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    s = TR.TennisLiveSession(trading=None)
    s.market_meta["E9"] = {"market_id": MARKET_ID}
    s.stream_started_monotonic = time.monotonic() - 1000.0
    return SimpleNamespace(tee=tee, session=s, alerts=alerts, richieste=richieste,
                           fw=_FakeFlumine())


def test_tennis_stallo_ricostruisce(tennis: SimpleNamespace) -> None:
    TR.stall_worker({}, tennis.fw, tennis.session)
    assert len(tennis.richieste) == 1
    assert tennis.session.stallo_rebuild_mono is not None
    assert tennis.alerts and tennis.alerts[0][0] == "CRITICAL"


def test_tennis_stream_vivo_non_ricostruisce(tennis: SimpleNamespace) -> None:
    tennis.tee.write_message(_heartbeat(1))
    tennis.tee.write_message(_mcm_compatto(2))
    TR.stall_worker({}, tennis.fw, tennis.session)
    assert tennis.richieste == []


def test_tennis_senza_partite_nessun_controllo(tennis: SimpleNamespace) -> None:
    tennis.session.market_meta.clear()
    TR.stall_worker({}, tennis.fw, tennis.session)
    assert tennis.richieste == []


def test_tennis_escala_se_la_ricostruzione_non_rida_dati(tennis: SimpleNamespace) -> None:
    TR.stall_worker({}, tennis.fw, tennis.session)          # ricostruzione
    tennis.session.stallo_rebuild_mono = time.monotonic() - 200.0
    tennis.session.stream_started_monotonic = time.monotonic() - 195.0
    TR.stall_worker({}, tennis.fw, tennis.session)          # nessun dato dopo: escala
    s = tennis.session
    assert s.shutdown_requested.is_set() and s.planned_restart is True
    assert len(tennis.richieste) == 1


def test_tennis_escalation_bloccata_da_bot_non_flat(tennis: SimpleNamespace,
                                                   monkeypatch: Any) -> None:
    TR.stall_worker({}, tennis.fw, tennis.session)
    monkeypatch.setattr(TR, "_hosted_not_flat",
                        lambda fw, s: [("E9", "scalper", object())])
    tennis.session.stallo_rebuild_mono = time.monotonic() - 200.0
    TR.stall_worker({}, tennis.fw, tennis.session)
    TR.stall_worker({}, tennis.fw, tennis.session)
    assert not tennis.session.shutdown_requested.is_set()
    rinvii = [m for lv, m in tennis.alerts if "RINVIATO" in m]
    assert len(rinvii) == 1


def test_tennis_guarisce_con_dati_dopo_rebuild(tennis: SimpleNamespace) -> None:
    TR.stall_worker({}, tennis.fw, tennis.session)
    tennis.session.stallo_rebuild_mono = time.monotonic() - 950.0
    tennis.tee.write_message(_heartbeat(1))
    tennis.tee.write_message(_mcm_compatto(2))
    TR.stall_worker({}, tennis.fw, tennis.session)
    assert not tennis.session.shutdown_requested.is_set()
    assert tennis.session.stallo_rebuild_mono is None


# ---------------------------------------------------------------------------
# 5) cablaggio nei cicli principali (setup_and_run e' monolitico: controllo
#    sul sorgente VERO; la logica e' provata sopra sulle funzioni estratte)
# ---------------------------------------------------------------------------
def test_cablaggio_calcio() -> None:
    import inspect

    src = inspect.getsource(R.setup_and_run)
    assert "session.stream_market_count = len(market_ids)" in src
    assert '_attendi_se_rete("lettura dei follow", e)' in src
    assert '_attendi_se_rete("catalogo mercati (REST)", e)' in src
    # uscita per stallo = ricambio del processo: i follow NON si chiudono nel finally
    assert 'if getattr(session, "riavvio_per_stallo", False)' in src


def test_cablaggio_tennis() -> None:
    import inspect

    src = inspect.getsource(TR.setup_and_run)
    assert "function=stall_worker" in src
    assert "session.stream_started_monotonic = time.monotonic()" in src
    assert "if not e_errore_di_rete(e):" in src
