"""CANTIERE J2 (28/09/2026) - blocco 2: STREAM MUTO cablato in scalper, runner
calcio e runner tennis.

Ordine dell'utente (28/09): «il bot deve sapere se il flusso dati e'
interrotto». I bot flumine (scalper, sniper, theta, bot tennis) agiscono SOLO su
un book nuovo: a stream muto una posizione aperta non e' gestita da nessuno.
Qui si prova che:
  * la misura riusa il battito che il processo GIA' tiene (runner calcio:
    ``FrammentoListener.ultimo_msg_mono`` per connessione; runner tennis:
    ``RAW_TEE.last_heartbeat_ms``/``last_data_ms``), mai una seconda misura;
  * l'avviso CRITICAL (``live_alerts``) e la riga d'attivita' escono UNA volta
    per episodio, con la posizione non gestita, e INFO al rientro;
  * lo stato del bot dichiara «flusso interrotto» finche' dura
    (``stats.flusso`` della sessione scalper e dei bot tennis, topic
    ``flusso_stream`` sul canale dei runner).
Listener VERI di betfairlightweight/del runner alimentati con messaggi grezzi
Betfair; contenitori di flumine finti con i soli attributi letti.
"""
from __future__ import annotations

import inspect
import json
import time
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from Betfair.stream import stream_muto as SM


# ===========================================================================
# la misura
# ===========================================================================
def _frammento(ids=("1.200",), aperto_mono=None):
    """Un frammento del runner calcio: listener VERO (``FrammentoListener``)."""
    from Betfair.stream.frammenti_mercato import FrammentoListener

    li = FrammentoListener(max_latency=None)
    li.register_stream(1, "marketSubscription")
    s = SimpleNamespace(_listener=li, market_filter={"marketIds": list(ids)}, stream_id=1,
                        chiuso=False)
    if aperto_mono is not None:
        s.aperto_mono = aperto_mono
    return s, li


def _hb(li) -> None:
    li.on_data(json.dumps({"op": "mcm", "id": 1, "clk": "A", "pt": 1789000000000,
                           "ct": "HEARTBEAT"}))


def test_runner_calcio_usa_il_battito_del_frammento_non_una_seconda_misura():
    """``time_updated`` di betfairlightweight e' fresco (il messaggio e' appena
    arrivato) ma l'orologio del battito del frammento dice 20 s: vale il
    battito del frammento."""
    s, li = _frammento()
    _hb(li)
    assert li.ultimo_msg_mono > 0
    fw = SimpleNamespace(streams=[s])
    vivo = SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + 2.0)
    assert vivo["vivo"] is True
    muto = SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + SM.SOGLIA_S + 5.0)
    assert muto["vivo"] is False and muto["motivo"] == SM.MOTIVO_INTERROTTO
    assert muto["mercati_fermi"] == ["1.200"]


def test_status_diverso_da_null_o_200_non_conferma_col_suo_codice():
    """Reperto 3: fail-closed su OGNI status del messaggio diverso da null/200,
    col codice nel motivo (che finisce nell'avviso e nell'attivita')."""
    s, li = _frammento()
    fw = SimpleNamespace(streams=[s])
    for status, motivo in ((503, SM.MOTIVO_LATENTE), (500, "stream_status_500"),
                           ("boh", "stream_status_boh")):
        li.on_data(json.dumps({"op": "mcm", "id": 1, "clk": "A", "pt": 1789000000000,
                               "ct": "HEARTBEAT", "status": status}))
        st = SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + 1.0)
        assert st["vivo"] is False and st["motivo"] == motivo, (status, st)
    li.on_data(json.dumps({"op": "mcm", "id": 1, "clk": "A", "pt": 1789000000000,
                           "ct": "HEARTBEAT", "status": 200}))
    assert SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + 1.0)["vivo"] is True
    sv = SM.SorvegliaStream()
    a = sv.osserva({"vivo": False, "motivo": "stream_status_500", "eta_s": 1.0}, 100.0)
    assert "stream_status_500" in a["message"]


def test_soglia_e_tre_volte_l_heartbeat_chiesto():
    """Reperto 2: la soglia viene dal valore VERO, mai scritta a mano: 3 volte
    quello che chiede lo scanner (5000 ms), e sulle connessioni del runner 3
    volte l'``heartbeatMs`` che Betfair ha RIMANDATO sull'immagine iniziale."""
    from Betfair.safe_strategy import stream as SS

    assert SM.HEARTBEAT_MS_RICHIESTO == SS._HEARTBEAT_MS == 5000
    assert SM.SOGLIA_S == 3 * SS._HEARTBEAT_MS / 1000.0
    s, li = _frammento()
    li.on_data(json.dumps({"op": "mcm", "id": 1, "clk": "A", "pt": 1789000000000,
                           "ct": "SUB_IMAGE", "heartbeatMs": 10000, "mc": []}))
    assert li.heartbeat_ms_server == 10000 and SM.soglia_per(li) == 30.0
    fw = SimpleNamespace(streams=[s])
    # 20 s senza messaggi: sotto i 30 s della SUA soglia -> vivo
    assert SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + 20.0)["vivo"] is True
    assert SM.stato_stream(fw, adesso_mono=li.ultimo_msg_mono + 31.0)["vivo"] is False


def test_shard_dello_scanner_fail_closed_sullo_status():
    from Betfair.safe_strategy import stream as SS

    sh = SS.StreamShard(client=None, index=0)
    for st, latente in ((None, False), (200, False), (503, True), (500, True), ("x", True)):
        sh._listener = SimpleNamespace(status=st)
        assert sh.latente() is latente, st


def test_frammento_appena_aperto_non_e_interrotto_ma_dopo_la_grazia_si():
    ora = time.monotonic()
    s, _li = _frammento(aperto_mono=ora)
    fw = SimpleNamespace(streams=[s])
    assert SM.stato_stream(fw, adesso_mono=ora + 5.0)["vivo"] is None
    dopo = SM.stato_stream(fw, adesso_mono=ora + SM.GRAZIA_CONNESSIONE_S + 1.0)
    assert dopo["vivo"] is False and dopo["motivo"] == SM.MOTIVO_MAI_CONNESSO


def test_frammento_chiuso_non_conta():
    s, li = _frammento()
    _hb(li)
    s.chiuso = True
    assert SM.stato_stream(SimpleNamespace(streams=[s]),
                           adesso_mono=li.ultimo_msg_mono + 999)["vivo"] is None


def test_battiti_del_tee_tennis():
    ora = 1_800_000_000_000.0
    assert SM.stato_da_battiti(ora - 3000, 0, ora, mercati=["1.5"])["vivo"] is True
    m = SM.stato_da_battiti(ora - 20000, ora - 60000, ora, mercati=["1.5"])
    assert m["vivo"] is False and m["motivo"] == SM.MOTIVO_INTERROTTO and m["eta_s"] == 20.0
    assert SM.stato_da_battiti(0, 0, ora, mercati=["1.5"])["motivo"] == SM.MOTIVO_MAI_CONNESSO
    assert SM.stato_da_battiti(ora, ora, ora, mercati=[])["vivo"] is None


def test_all_avvio_la_connessione_ha_la_grazia_poi_e_un_episodio():
    sv = SM.SorvegliaStream()
    mai = {"vivo": False, "motivo": SM.MOTIVO_MAI_CONNESSO, "eta_s": None}
    assert sv.osserva(mai, 100.0) is None
    assert sv.osserva(mai, 100.0 + SM.GRAZIA_CONNESSIONE_S - 1) is None
    a = sv.osserva(mai, 100.0 + SM.GRAZIA_CONNESSIONE_S + 1)
    assert a is not None and a["code"] == SM.CODICE_INIZIO
    assert sv.dichiarazione(200.0)["interrotto"] is True


def test_messaggio_del_canale_ha_le_chiavi_fisse():
    sv = SM.SorvegliaStream()
    sv.osserva({"vivo": False, "motivo": "flusso_interrotto", "eta_s": 17.0,
                "mercati_fermi": ["1.2"]}, 10.0)
    m = SM.messaggio_canale(sv.dichiarazione(15.0), 15000.0)
    assert tuple(m.keys()) == SM.CHIAVI_CANALE
    assert m["interrotto"] is True and m["muto_da_s"] == 5.0 and m["mercati_fermi"] == ["1.2"]


# ===========================================================================
# sessione scalper (maker, sniper, theta)
# ===========================================================================
class _Tabella:
    def __init__(self, dove: List[Dict[str, Any]]) -> None:
        self.dove = dove
        self._riga: Dict[str, Any] = {}

    def insert(self, riga):
        self._riga = dict(riga)
        return self

    def execute(self):
        self.dove.append(self._riga)
        return SimpleNamespace(data=[self._riga])


class DbScalper:
    """Le porte di ``scalper_session.Db`` usate (stesse firme): ``sb.table``
    per ``live_alerts``, ``log(event_id, kind, payload)``."""

    def __init__(self) -> None:
        self.alerts: List[Dict[str, Any]] = []
        self.attivita: List[tuple] = []
        self.sb = SimpleNamespace(table=lambda nome: _Tabella(self.alerts))

    def log(self, event_id, kind, payload):
        self.attivita.append((event_id, kind, dict(payload)))


def test_scalper_episodio_detto_una_volta_con_la_posizione_e_il_rientro(monkeypatch):
    from Betfair.stream.scalper import scalper_session as SS

    monkeypatch.setattr(SS, "_dichiarazione_non_flat",
                        lambda fw: "1.200/11 residuo accettato 2.00")
    db = DbScalper()
    sv = SM.SorvegliaStream()
    muto = {"vivo": False, "motivo": "flusso_interrotto", "eta_s": 21.0, "mercati_fermi": ["1.200"]}
    vivo = {"vivo": True, "motivo": None, "eta_s": 1.0, "mercati_fermi": []}
    d = SS.sorveglia_flusso_sessione(db, "E1", None, sv, adesso_s=100.0, stato=muto)
    assert d["interrotto"] is True
    for t in (105.0, 110.0, 115.0):
        assert SS.sorveglia_flusso_sessione(db, "E1", None, sv, adesso_s=t, stato=muto)["interrotto"]
    assert len(db.alerts) == 1 and db.alerts[0]["level"] == "CRITICAL"
    assert db.alerts[0]["code"] == SM.CODICE_INIZIO and db.alerts[0]["event_id"] == "E1"
    assert "POSIZIONE APERTA NON GESTITA" in db.alerts[0]["message"]
    kinds = [k for _e, k, _p in db.attivita]
    assert kinds == [SS.KIND_FLUSSO_INTERROTTO]
    assert db.attivita[0][2]["critical"] is True
    assert db.attivita[0][2]["posizione_non_gestita"].startswith("1.200/11")
    d = SS.sorveglia_flusso_sessione(db, "E1", None, sv, adesso_s=130.0, stato=vivo)
    assert d["interrotto"] is False
    assert [k for _e, k, _p in db.attivita] == [SS.KIND_FLUSSO_INTERROTTO, SS.KIND_FLUSSO_RIPRESO]
    assert db.alerts[-1]["level"] == "INFO"


def test_scalper_il_battito_scrive_la_dichiarazione_nelle_stats():
    """Il battito della sessione (``run_session``) chiama la sorveglianza PRIMA
    di scrivere la riga e mette la dichiarazione in ``stats.flusso``."""
    from Betfair.stream.scalper import scalper_session as SS

    src = inspect.getsource(SS.run_session)
    i_sorv = src.index("sorveglia_flusso_sessione(db, ev, framework, sorv_flusso)")
    i_riga = src.index('stats={**_stats(), "flusso": _flusso}')
    assert i_sorv < i_riga


# ===========================================================================
# runner calcio
# ===========================================================================
def test_runner_calcio_alert_una_volta_canale_a_ogni_battito(monkeypatch):
    from Betfair.stream import runner as R

    alert: List[tuple] = []
    canale: List[tuple] = []
    monkeypatch.setattr(R.db, "insert_alert", lambda *a, **k: alert.append(a))
    monkeypatch.setattr(R._cb, "pubblica_stato_processo", lambda t, p: canale.append((t, p)) or True)
    s, li = _frammento()
    _hb(li)
    ordine = SimpleNamespace()
    mercato = SimpleNamespace(market_id="1.200",
                              blotter=SimpleNamespace(live_orders=[ordine]))
    fw = SimpleNamespace(streams=[s], markets=[mercato])
    sess = SimpleNamespace()
    t0 = li.ultimo_msg_mono
    R._sorveglia_flusso_runner(sess, fw, adesso_s=1000.0, adesso_mono=t0 + 1)
    assert alert == [] and sess.flusso_runner["interrotto"] is False
    for k in range(3):
        R._sorveglia_flusso_runner(sess, fw, adesso_s=1030.0 + 10 * k,
                                   adesso_mono=t0 + 30 + 10 * k)
    assert len(alert) == 1
    livello, codice, testo = alert[0][:3]
    assert livello == "CRITICAL" and codice == "RUNNER_" + SM.CODICE_INIZIO
    assert "1 ordini vivi su 1.200" in testo
    assert sess.flusso_runner["interrotto"] is True
    assert len(canale) == 4 and all(t == "flusso_stream" for t, _p in canale)
    assert canale[-1][1]["interrotto"] is True and canale[-1][1]["mercati_fermi"] == ["1.200"]
    _hb(li)
    R._sorveglia_flusso_runner(sess, fw, adesso_s=1100.0, adesso_mono=li.ultimo_msg_mono + 1)
    assert alert[-1][0] == "INFO" and sess.flusso_runner["interrotto"] is False


def test_runner_calcio_il_battito_chiama_la_sorveglianza():
    from Betfair.stream import runner as R

    src = inspect.getsource(R.heartbeat_worker)
    assert "_sorveglia_flusso_runner(session, flumine)" in src


# ===========================================================================
# runner tennis (bot tennis)
# ===========================================================================
def test_tennis_attivita_di_ogni_bot_e_stats(monkeypatch):
    from Betfair.stream import db as DB
    from Betfair.stream.tennis_live import tennis_runner as TR

    alert: List[tuple] = []
    attivita: List[tuple] = []
    monkeypatch.setattr(DB, "insert_alert", lambda *a, **k: alert.append(a))
    monkeypatch.setattr(TR.tennis_db, "write_tennis_bot_activity",
                        lambda ev, bk, kind, p: attivita.append((ev, bk, kind, p)))
    monkeypatch.setattr(TR, "_hosted_not_flat", lambda fw, s: [("E1", "scalper", None)])
    ora = 1_800_000_000_000.0
    monkeypatch.setattr(TR.RAW_TEE, "last_heartbeat_ms", int(ora - 3000))
    monkeypatch.setattr(TR.RAW_TEE, "last_data_ms", 0)
    sess = TR.TennisLiveSession(trading=None)
    sess.market_meta = {"E1": {"market_id": "1.5"}}
    sess.hosted = {("E1", "scalper"): object(), ("E1", "pro"): object()}
    TR._sorveglia_flusso_tennis(None, sess, adesso_ms=ora)
    assert alert == [] and sess.flusso_runner["interrotto"] is False
    TR._sorveglia_flusso_tennis(None, sess, adesso_ms=ora + 20000)
    TR._sorveglia_flusso_tennis(None, sess, adesso_ms=ora + 30000)
    assert len(alert) == 1 and alert[0][0] == "CRITICAL"
    assert alert[0][1] == "TENNIS_" + SM.CODICE_INIZIO and "scalper@E1" in alert[0][2]
    assert sorted((ev, bk, k) for ev, bk, k, _p in attivita) == [
        ("E1", "pro", TR.KIND_FLUSSO_INTERROTTO), ("E1", "scalper", TR.KIND_FLUSSO_INTERROTTO)]
    assert sess.flusso_runner["interrotto"] is True
    monkeypatch.setattr(TR.RAW_TEE, "last_heartbeat_ms", int(ora + 40000))
    TR._sorveglia_flusso_tennis(None, sess, adesso_ms=ora + 41000)
    assert alert[-1][0] == "INFO" and sess.flusso_runner["interrotto"] is False
    assert [k for _e, _b, k, _p in attivita].count(TR.KIND_FLUSSO_RIPRESO) == 2


def test_tennis_lo_stall_worker_sorveglia_e_il_battito_dei_bot_dichiara():
    from Betfair.stream.tennis_live import tennis_runner as TR

    assert "_sorveglia_flusso_tennis(flumine, session)" in inspect.getsource(TR.stall_worker)
    src = inspect.getsource(TR.bot_control_worker)
    assert 'battito["flusso"] = dict(_fl)' in src
