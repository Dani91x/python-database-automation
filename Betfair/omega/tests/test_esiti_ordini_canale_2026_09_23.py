"""Esiti degli ordini in coda dal canale del runner (23/09, ``ESITI_ORDINI_CANALE``).

Ogni test e' stato FALSIFICATO (mutazione del codice -> rosso, ripristino ->
verde): l'elenco delle mutazioni e' nel referto del delegato.

I finti parlano come il vero:
  * la riga del canale e' costruita dal PRODUTTORE VERO
    (``LiveTradingStrategy._order_row`` + ``db.upsert_live_order``), non a mano;
  * il ``db`` del bot e' ``FakeQueueDB`` dei test di Omega (contratto di
    ``omega_db``: ``get_live_order_request``/``get_live_order_mirror``/...);
  * il canale e' il ``LocalChannel`` vero su una porta libera, con un client
    ``websockets`` vero.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

import Betfair.stream.engine.live_trading_strategy as strat
from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_flumine_paper import FakeQueueDB
from Betfair.omega.test_omega_service import (
    NOW,
    FakeMarket,
    _control,
    _cs,
    _event,
    _open_snapshot,
)
from Betfair.stream import esiti_ordini_canale as EO
from Betfair.stream import local_channel as LC

RADICE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


# ---------------------------------------------------------------------------
# attrezzi
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    """Ogni test parte senza istanza registrata e con l'interruttore SPENTO."""
    monkeypatch.delenv(EO.ENV_ESITI, raising=False)
    S.ferma_esiti_ordini()
    yield
    S.ferma_esiti_ordini()


def _accendi(monkeypatch) -> EO.EsitiOrdini:
    """Interruttore acceso + istanza registrata SENZA thread (i test pilotano
    l'applicatore con ``applica_ora``) e SENZA socket."""
    monkeypatch.setenv(EO.ENV_ESITI, "1")
    esiti = EO.EsitiOrdini(S._applica_esiti_dal_canale)
    EO.registra(esiti)
    return esiti


def _fake_order(*, rid: int, status: str, size_matched: float, size: float,
                avg: float, remaining: float, bet_id: str = "sim1",
                aggiornato: str = "2026-07-12T15:42:05+00:00") -> Any:
    """Un ordine flumine come lo legge ``LiveTradingStrategy`` (stessi campi
    del fake di ``test_live_trading_strategy``)."""
    ot = SimpleNamespace(ORDER_TYPE=SimpleNamespace(name="LIMIT"), price=110.0,
                         size=size, persistence_type="LAPSE")
    return SimpleNamespace(
        id="OID-%d" % rid, bet_id=bet_id, market_id="m-1.100", selection_id=4,
        handicap=0.0, side="LAY", status=SimpleNamespace(name=status), order_type=ot,
        size_matched=size_matched, size_remaining=remaining, size_cancelled=0.0,
        size_lapsed=0.0, size_voided=0.0, average_price_matched=avg,
        customer_order_ref="awlq%d" % rid,
        responses=SimpleNamespace(date_time_placed="2026-07-12T15:42:00+00:00"),
        date_time_status_update=aggiornato)


def _riga_vera(*, rid: int, mode: str = "paper", status: str = "EXECUTION_COMPLETE",
               size_matched: float, size: float, avg: float = 112.0,
               remaining: float = 0.0, updated_at: str = "2026-07-12T15:42:06+00:00",
               aggiornato: str = "2026-07-12T15:42:05+00:00") -> Dict[str, Any]:
    """La riga che il runner PUBBLICA: ``_order_row`` vero + ``updated_at``
    (quello che aggiunge ``db.upsert_live_order`` prima del publish)."""
    s = strat.LiveTradingStrategy(market_filter={"marketIds": ["m-1.100"]},
                                  session=None, mode=mode)
    riga = s._order_row(_fake_order(rid=rid, status=status, size_matched=size_matched,
                                    size=size, avg=avg, remaining=remaining,
                                    aggiornato=aggiornato),
                        event_id="1.100", market_id="m-1.100")
    riga["updated_at"] = updated_at
    return riga


def _messaggio(riga: Dict[str, Any]) -> str:
    """Il messaggio ESATTO che ``LocalChannel.publish`` manda sul socket."""
    return json.dumps({"t": "order", "d": riga}, default=str)


def _piazza_in_coda(db: FakeQueueDB, market: Any) -> "tuple[dict, int]":
    S.run_once(market=market, db=db, now=NOW)
    t = db.trades[0]
    rid = int(t["meta"]["flumine_request_id"])
    db.queue[rid]["status"] = "done"
    return t, rid


class _Traccia:
    """Registra OGNI chiamata al ``db`` (nome + argomenti), in ordine."""

    def __init__(self, db: Any) -> None:
        object.__setattr__(self, "_db", db)
        object.__setattr__(self, "chiamate", [])

    def __getattr__(self, nome: str) -> Any:
        valore = getattr(self._db, nome)
        if not callable(valore):
            return valore

        def _registrata(*a: Any, **k: Any) -> Any:
            self.chiamate.append((nome, a, tuple(sorted(k))))
            return valore(*a, **k)
        return _registrata

    def __setattr__(self, nome: str, valore: Any) -> None:
        setattr(self._db, nome, valore)


def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _aspetta(cond, secondi: float = 5.0) -> bool:
    fine = time.time() + secondi
    while time.time() < fine:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


# ===========================================================================
# 1. PRODUTTORE: pubblica la riga esatta dello specchio a ogni cambio
# ===========================================================================
class _FakeSupabase:
    def __init__(self) -> None:
        self.upsert: List[Dict[str, Any]] = []

    def table(self, nome: str) -> Any:
        fuori = self

        class _Q:
            def upsert(self, payload, on_conflict=None):  # noqa: ANN001
                assert nome == "betfair_live_orders"
                assert on_conflict == "mode,client_order_ref"
                fuori.upsert.append(dict(payload))
                return SimpleNamespace(execute=lambda: SimpleNamespace(data=[payload]))
        return _Q()


def test_produttore_pubblica_la_riga_esatta_a_ogni_cambio(monkeypatch):
    from Betfair.stream import db as dbm

    sb = _FakeSupabase()
    pubblicati: List[tuple] = []
    monkeypatch.setattr(dbm, "get_supabase_client", lambda: sb)
    monkeypatch.setattr(LC, "publish", lambda t, p: pubblicati.append((t, dict(p))))
    monkeypatch.setattr(strat, "_db", lambda: dbm)
    s = strat.LiveTradingStrategy(market_filter={"marketIds": ["m-1.100"]},
                                  session=None, mode="paper")
    s._position_row = lambda *a, **k: None          # posizioni: fuori da questo test
    mercato = SimpleNamespace(market_id="m-1.100", event_id="1.100", blotter=None)
    passi = [
        _fake_order(rid=7, status="EXECUTABLE", size_matched=0.0, size=5.0, avg=0.0,
                    remaining=5.0),
        _fake_order(rid=7, status="EXECUTABLE", size_matched=0.0, size=5.0, avg=0.0,
                    remaining=5.0),                    # invariato: niente
        _fake_order(rid=7, status="EXECUTABLE", size_matched=2.0, size=5.0, avg=111.0,
                    remaining=3.0),                    # parziale
        _fake_order(rid=7, status="EXECUTION_COMPLETE", size_matched=5.0, size=5.0,
                    avg=112.0, remaining=0.0),         # completo
    ]
    for o in passi:
        s.process_orders(mercato, [o])
    ordini = [p for t, p in pubblicati if t == "order"]
    assert len(ordini) == 3 == len(sb.upsert), "un publish per OGNI cambio, uno solo"
    assert ordini == sb.upsert, "il canale porta la STESSA riga scritta sul database"
    for chiave in ("client_order_ref", "request_id", "bet_id", "mode", "status",
                   "size_matched", "size_remaining", "average_price_matched",
                   "matched_at", "updated_at"):
        assert chiave in ordini[-1], chiave
    assert ordini[-1]["client_order_ref"] == "awlq7" and ordini[-1]["request_id"] == 7
    assert [o["size_matched"] for o in ordini] == [0.0, 2.0, 5.0]
    assert ordini[-1]["status"] == "EXECUTION_COMPLETE"


# ===========================================================================
# 2. IL CANALE: il lettore riceve solo 'order', non e' un desktop, non comanda
# ===========================================================================
def test_topic_del_lettore():
    assert LC.topic_del_lettore("/lettore/order") == frozenset({"order"})
    assert LC.topic_del_lettore("/lettore/order,position?x=1") == frozenset({"order", "position"})
    assert LC.topic_del_lettore("/lettore/") == frozenset()
    assert LC.topic_del_lettore("/") is None
    assert LC.topic_del_lettore(None) is None


def test_lettore_non_accende_il_desktop_e_riceve_solo_order():
    from websockets.sync.client import connect

    porta = _porta_libera()
    ch = LC.LocalChannel(porta, "calcio")
    assert ch.start()
    with connect("ws://127.0.0.1:%d%s" % (porta, EO.PERCORSO), open_timeout=5) as lettore:
        assert json.loads(lettore.recv(timeout=5))["t"] == "hello"
        assert _aspetta(lambda: ch._n_clients == 1)
        assert ch.is_active() is False, "un lettore NON e' un desktop collegato"
        ch.publish("ladder", {"market_id": "1.1"})
        ch.publish("order", {"client_order_ref": "awlq1"})
        msg = json.loads(lettore.recv(timeout=5))
        assert msg["t"] == "order", "il lettore riceve SOLO il suo topic"
        with connect("ws://127.0.0.1:%d/" % porta, open_timeout=5) as desktop:
            assert json.loads(desktop.recv(timeout=5))["t"] == "hello"
            assert _aspetta(lambda: ch.is_active() is True)
            ch.publish("ladder", {"market_id": "1.2"})
            ch.publish("order", {"client_order_ref": "awlq2"})
            assert json.loads(desktop.recv(timeout=5))["t"] == "ladder"
            assert json.loads(desktop.recv(timeout=5))["t"] == "order"
            # con un desktop collegato il ladder viaggia: al lettore NO
            msg = json.loads(lettore.recv(timeout=5))
            assert msg["t"] == "order" and msg["d"]["client_order_ref"] == "awlq2"
        assert _aspetta(lambda: ch.is_active() is False)


def test_lettore_non_puo_mandare_comandi_ne_sveglie():
    from websockets.sync.client import connect

    porta = _porta_libera()
    ch = LC.LocalChannel(porta, "calcio")
    svegliato: List[Any] = []
    ch.set_sveglia(lambda p: svegliato.append(p))
    assert ch.start()
    with connect("ws://127.0.0.1:%d%s" % (porta, EO.PERCORSO), open_timeout=5) as lettore:
        lettore.recv(timeout=5)                       # hello
        lettore.send(json.dumps({"id": 1, "m": "order", "p": {"action": "place"}}))
        r1 = json.loads(lettore.recv(timeout=5))
        lettore.send(json.dumps({"id": 2, "m": "sveglia", "p": {"motivo": "comando"}}))
        r2 = json.loads(lettore.recv(timeout=5))
    assert r1["ok"] is False and r2["ok"] is False
    assert ch.pop_requests() == [], "nessun comando entra dalla porta del lettore"
    assert svegliato == []


# ===========================================================================
# 3. LA MEMORIA: mai piu' vecchia, mai indietro da un esito definitivo
# ===========================================================================
def test_memoria_tiene_la_piu_fresca_e_ignora_le_vecchie():
    m = EO.MemoriaEsiti()
    nuova = _riga_vera(rid=1, size_matched=5.0, size=5.0,
                       updated_at="2026-07-12T15:42:06+00:00")
    vecchia = _riga_vera(rid=1, status="EXECUTABLE", size_matched=0.0, size=5.0,
                         remaining=5.0, updated_at="2026-07-12T15:42:01+00:00")
    assert m.ricevi(nuova) is True
    assert m.ricevi(vecchia) is False, "un evento piu' vecchio non sovrascrive"
    assert m.ricevi(dict(nuova)) is False, "a parita' di istante non si sostituisce"
    tardiva = dict(vecchia, updated_at="2026-07-12T15:42:09+00:00")
    assert m.ricevi(tardiva) is False, "un esito terminale non torna indietro"
    esito = m.esito_terminale("awlq1", "paper")
    assert esito is not None and esito["size_matched"] == 5.0
    assert "_istante" not in esito
    assert m.esito_terminale("awlq1", "live") is None, "mai letture cross-mode"


def test_memoria_scarta_righe_senza_chiave_o_istante():
    m = EO.MemoriaEsiti()
    riga = _riga_vera(rid=2, size_matched=1.0, size=1.0)
    assert m.ricevi(dict(riga, updated_at=None)) is False
    assert m.ricevi(dict(riga, client_order_ref=None)) is False
    assert m.ricevi(dict(riga, mode="demo")) is False
    assert m.ricevi("non un dict") is False


def test_memoria_restituisce_solo_esiti_terminali():
    m = EO.MemoriaEsiti()
    m.ricevi(_riga_vera(rid=3, status="EXECUTABLE", size_matched=2.0, size=5.0,
                        remaining=3.0))
    assert m.esito_terminale("awlq3", "paper") is None


# ===========================================================================
# 4. IL CONSUMATORE (Omega/Safe: poll_flumine_pending)
# ===========================================================================
def test_evento_terminale_fresco_conferma_subito_senza_leggere_lo_specchio(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    assert db.trades[0]["status"] == "pending"
    assert esiti.e_nostra(rid), "la richiesta appena accodata e' riconosciuta come nostra"
    # il database NON ha lo specchio: se il poll lo leggesse, la riga resterebbe pending
    letture: List[str] = []
    orig = db.get_live_order_mirror
    db.get_live_order_mirror = lambda ref, mode="paper": (letture.append(ref), orig(ref, mode))[1]
    monkeypatch.setattr(S, "_now", lambda: NOW + timedelta(seconds=3))
    assert esiti.client.incassa(_messaggio(_riga_vera(rid=rid, size_matched=t["size"],
                                                      size=t["size"])))
    assert esiti._evento.is_set(), "l'esito di un ordine nostro sveglia l'applicatore"
    assert esiti.applica_ora() == 1
    tr = db.trades[0]
    assert tr["status"] == "open", "esito applicato SUBITO, senza aspettare il ciclo"
    assert tr["price"] == 112.0 and tr["size"] == t["size"] and tr["bet_id"] == "sim1"
    assert tr["meta"]["fill"] == "flumine_paper"
    assert tr["meta"]["betfair_updated_at"] == "2026-07-12T15:42:05+00:00"
    assert letture == [], "specchio dal canale: nessuna lettura di betfair_live_orders"


def test_evento_terminale_live_conferma_dal_canale(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    assert db.queue[rid]["payload"]["mode"] == "live"
    monkeypatch.setattr(S, "_now", lambda: NOW + timedelta(seconds=2))
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, mode="live",
                                               size_matched=t["size"], size=t["size"],
                                               avg=111.0)))
    esiti.applica_ora()
    tr = db.trades[0]
    assert tr["status"] == "open" and tr["price"] == 111.0
    assert tr["meta"]["fill"] == "flumine_live"


def test_fok_ucciso_senza_abbinato_chiude_la_riga_in_errore(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control(mode="live"), hb_mode="LIVE")
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    monkeypatch.setattr(S, "_now", lambda: NOW + timedelta(seconds=2))
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, mode="live", status="EXPIRED",
                                               size_matched=0.0, size=t["size"],
                                               avg=0.0, remaining=0.0)))
    esiti.applica_ora()
    tr = db.trades[0]
    assert tr["status"] == "error"
    assert tr["meta"]["reason"] == "flumine_live_fok_expired"


def test_evento_piu_vecchio_della_riga_del_bot_non_la_sovrascrive(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    # la riga del bot sa gia' di un istante Betfair PIU' RECENTE dell'evento
    db.trades[0]["meta"]["betfair_updated_at"] = "2026-07-12T15:50:00+00:00"
    db.mirrors["awlq%d" % rid] = {"size_matched": t["size"], "average_price_matched": 120.0,
                                  "status": "EXECUTION_COMPLETE", "size_remaining": 0.0,
                                  "bet_id": "dal-db", "mode": "paper",
                                  "matched_at": "2026-07-12T15:50:00+00:00"}
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, size_matched=t["size"],
                                               size=t["size"], avg=112.0)))
    S.poll_flumine_pending(db=db, params=S.omega_config.resolve_params(None),
                           now=NOW + timedelta(seconds=3), market=market)
    tr = db.trades[0]
    assert tr["status"] == "open"
    assert tr["price"] == 120.0 and tr["bet_id"] == "dal-db", "vince il database"
    assert esiti.conti["canale_piu_vecchio"] == 1


def test_evento_non_terminale_non_decide_legge_il_database(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, status="EXECUTABLE",
                                               size_matched=1.0, size=t["size"],
                                               remaining=t["size"] - 1.0)))
    assert not esiti._evento.is_set(), "una riga intermedia non sveglia nessuno"
    traccia = _Traccia(db)
    S.poll_flumine_pending(db=traccia, params=S.omega_config.resolve_params(None),
                           now=NOW + timedelta(seconds=3), market=market)
    assert ("get_live_order_mirror", ("awlq%d" % rid, "paper"), ()) in traccia.chiamate
    assert db.trades[0]["status"] == "pending"


def test_esito_di_un_altro_bot_non_sveglia_e_non_legge(monkeypatch):
    esiti = _accendi(monkeypatch)
    esiti.aggiorna_nostri([{"meta": {"flumine_request_id": 5}}])
    assert esiti.client.incassa(_messaggio(_riga_vera(rid=999, size_matched=1.0, size=1.0)))
    assert not esiti._evento.is_set()
    chiamate: List[Any] = []
    esiti._applica = lambda rids: chiamate.append(rids)
    assert esiti.applica_ora() == 0 and chiamate == []


def test_esito_arrivato_prima_della_risposta_dell_enqueue_non_si_perde(monkeypatch):
    esiti = _accendi(monkeypatch)
    esiti.client.incassa(_messaggio(_riga_vera(rid=41, size_matched=2.0, size=2.0)))
    assert not esiti._evento.is_set()
    EO.ricorda_richiesta(41)
    assert esiti._evento.is_set() and 41 in esiti._da_applicare


def test_solo_rid_fa_avanzare_solo_le_richieste_arrivate(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control(params={"max_events": 5}))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    # una seconda riga pending di un'altra richiesta, col TTL SCADUTO: il poll
    # di ciclo accoderebbe il cancel; l'applicatore NON deve toccarla.
    altra = dict(db.trades[0], id=99, meta=dict(db.trades[0]["meta"],
                                                   flumine_request_id=77))
    db.trades.append(altra)
    db.queue[77] = {"id": 77, "status": "done", "result": None, "error": None,
                    "bet_id": None, "payload": {"client_ref": "omega-t99"}}
    db.mirrors["awlq77"] = {"size_matched": 0.0, "average_price_matched": 0.0,
                            "status": "EXECUTABLE", "size_remaining": 1.0,
                            "bet_id": "b77", "mode": "paper"}
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, size_matched=t["size"],
                                               size=t["size"])))
    traccia = _Traccia(db)
    S.poll_flumine_pending(db=traccia, params=S.omega_config.resolve_params(None),
                           now=NOW + timedelta(seconds=600), market=market,
                           solo_rid=frozenset({rid}))
    lette = [a for n, a, _ in traccia.chiamate if n == "get_live_order_request"]
    assert lette == [(rid,)], "letta SOLO la richiesta arrivata dal canale"
    assert db.trades[0]["status"] == "open"
    assert db.trades[1]["status"] == "pending"
    assert set(db.queue) == {rid, 77}, "nessun cancel accodato per l'altra riga"


def test_applicatore_salta_se_il_ciclo_ha_gia_risolto(monkeypatch):
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, size_matched=t["size"],
                                               size=t["size"])))
    # il giro arriva PRIMA dell'applicatore e risolve lui (specchio dal canale)
    S.run_once(market=market, db=db, now=NOW + timedelta(seconds=3))
    assert db.trades[0]["status"] == "open"
    traccia = _Traccia(db)
    esiti.ricorda_contesto(db=traccia, params=None, market=market)
    assert esiti.applica_ora() == 0
    assert traccia.chiamate == [], "nessuna lettura se non c'e' piu' niente da fare"


def test_applicatore_non_lavora_mai_dentro_un_giro(monkeypatch):
    esiti = _accendi(monkeypatch)
    esiti.aggiorna_nostri([{"meta": {"flumine_request_id": 3}}])
    fatti: List[Any] = []
    esiti._applica = lambda rids: fatti.append(sorted(rids))
    esiti.avvia(client=False)
    try:
        with EO.ciclo():                      # il bot e' dentro run_once
            esiti.client.incassa(_messaggio(_riga_vera(rid=3, size_matched=1.0,
                                                       size=1.0)))
            time.sleep(0.3)
            assert fatti == [], "l'applicatore aspetta la fine del giro"
        assert _aspetta(lambda: fatti == [[3]], 3.0)
    finally:
        esiti.ferma()


# ===========================================================================
# 5. INTERRUTTORE SPENTO e CANALE MUTO: la traccia di oggi
# ===========================================================================
def _traccia_del_poll(stato: str, monkeypatch) -> List[tuple]:
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    db.mirrors["awlq%d" % rid] = {"size_matched": t["size"], "average_price_matched": 112.0,
                                  "status": "EXECUTION_COMPLETE", "size_remaining": 0.0,
                                  "bet_id": "sim1", "mode": "paper",
                                  "matched_at": "2026-07-12T15:42:05+00:00"}
    if stato == "istanza_ma_spento":
        EO.registra(EO.EsitiOrdini(S._applica_esiti_dal_canale))
        monkeypatch.delenv(EO.ENV_ESITI, raising=False)
    elif stato == "acceso_canale_muto":
        _accendi(monkeypatch)
    traccia = _Traccia(db)
    S.poll_flumine_pending(db=traccia, params=S.omega_config.resolve_params(None),
                           now=NOW + timedelta(seconds=3), market=market)
    assert db.trades[0]["status"] == "open"
    S.ferma_esiti_ordini()
    monkeypatch.delenv(EO.ENV_ESITI, raising=False)
    return [(n, a) for n, a, _ in traccia.chiamate]


def test_interruttore_spento_traccia_identica_a_oggi(monkeypatch):
    oggi = _traccia_del_poll("nessuna_istanza", monkeypatch)
    assert oggi[:3] == [("list_trades", ("pending",)), ("get_live_order_request", (1,)),
                        ("get_live_order_mirror", ("awlq1", "paper"))]
    assert _traccia_del_poll("istanza_ma_spento", monkeypatch) == oggi


def test_canale_muto_il_poll_fa_il_lavoro_come_oggi(monkeypatch):
    oggi = _traccia_del_poll("nessuna_istanza", monkeypatch)
    assert _traccia_del_poll("acceso_canale_muto", monkeypatch) == oggi


def test_interruttore_spento_ignora_anche_una_memoria_piena(monkeypatch):
    """Istanza registrata E riga terminale in memoria, ma interruttore spento:
    il poll legge il database come oggi e non usa il canale."""
    esiti = _accendi(monkeypatch)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    esiti.client.incassa(_messaggio(_riga_vera(rid=rid, size_matched=t["size"],
                                               size=t["size"])))
    monkeypatch.delenv(EO.ENV_ESITI, raising=False)
    traccia = _Traccia(db)
    S.poll_flumine_pending(db=traccia, params=S.omega_config.resolve_params(None),
                           now=NOW + timedelta(seconds=3), market=market)
    assert ("get_live_order_mirror", ("awlq%d" % rid, "paper"), ()) in traccia.chiamate
    assert db.trades[0]["status"] == "pending", "specchio vuoto sul DB: si aspetta"
    assert EO.ciclo() is not esiti.ciclo()


def test_interruttore_spento_nessun_thread_nessuna_porta(monkeypatch):
    monkeypatch.delenv(EO.ENV_ESITI, raising=False)
    prima = {t.name for t in threading.enumerate()}
    assert S.avvia_esiti_ordini() is False
    assert EO.istanza() is None
    assert {t.name for t in threading.enumerate()} == prima
    assert type(S.esiti_ciclo()).__name__ == "nullcontext"
    EO.ricorda_richiesta(5)                    # no-op, non solleva
    for spento in ("", "0", "no", "false", "acceso"):
        monkeypatch.setenv(EO.ENV_ESITI, spento)
        assert S.avvia_esiti_ordini() is False, spento


# ===========================================================================
# 6. DAL CAPO ALLA CODA: canale vero, client vero, applicatore in thread
# ===========================================================================
def test_capo_coda_canale_vero_esito_applicato_dal_thread(monkeypatch):
    porta = _porta_libera()
    ch = LC.LocalChannel(porta, "calcio")
    assert ch.start()
    monkeypatch.setenv(EO.ENV_ESITI, "1")
    esiti = EO.EsitiOrdini(S._applica_esiti_dal_canale, porta_ws=porta)
    EO.registra(esiti)
    db = FakeQueueDB(_control())
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    t, rid = _piazza_in_coda(db, market)
    monkeypatch.setattr(S, "_now", lambda: NOW + timedelta(seconds=3))
    assert esiti.avvia()
    try:
        assert _aspetta(lambda: ch._n_clients == 1 and esiti.client.collegato)
        assert ch.is_active() is False
        ch.publish("ladder", {"market_id": "m-1.100"})     # ignorato dal lettore
        ch.publish("order", _riga_vera(rid=rid, size_matched=t["size"], size=t["size"]))
        assert _aspetta(lambda: db.trades[0]["status"] == "open", 5.0), \
            "l'esito pubblicato dal runner arriva sulla riga del bot senza giro"
        assert esiti.memoria.stato()["terminali"] == 1
    finally:
        esiti.ferma()


# ===========================================================================
# 7. CONTRATTI
# ===========================================================================
def test_stati_terminali_uguali_a_quelli_del_poll():
    assert EO.STATI_TERMINALI == S._FLUMINE_TERMINAL


def test_percorso_e_porta_uguali_a_quelli_del_runner():
    assert EO.PERCORSO.startswith(LC.PREFISSO_LETTORE)
    assert LC.topic_del_lettore(EO.PERCORSO) == frozenset({EO.TOPIC})
    sorgente = open(os.path.join(RADICE, "Betfair", "stream", "runner.py"),
                    encoding="utf-8").read()
    assert 'os.getenv("%s", "%d")' % (EO.ENV_PORTA, EO.PORTA) in sorgente
    db_src = open(os.path.join(RADICE, "Betfair", "stream", "db.py"),
                  encoding="utf-8").read()
    assert '_lpub("%s", payload)' % EO.TOPIC in db_src


def test_esiti_ordini_canale_e_un_modulo_puro():
    codice = ("import sys; import Betfair.stream.esiti_ordini_canale; "
              "bad=[m for m in ('flumine','betfairlightweight','supabase','websockets') "
              "if m in sys.modules]; print(','.join(bad))")
    out = subprocess.run([sys.executable, "-c", codice], cwd=RADICE, capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ""


def test_safe_accoda_e_ricorda_la_richiesta(monkeypatch):
    from Betfair.safe_strategy import execution as X

    esiti = _accendi(monkeypatch)

    class _Db:
        def update_trade(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            return None

        def enqueue_live_order(self, payload):  # noqa: ANN001
            return 314

        def log(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            return None

    rid = X.enqueue_place(db=_Db(), trade_id=9, client_ref="safe-t9", event_id="1.1",
                          market_id="1.2", selection_id=3, side="back", price=2.0,
                          size=2.0, base_meta={}, now=NOW, mode="paper")
    assert rid == 314 and esiti.e_nostra(314)


def test_safe_usa_il_lucchetto_e_lo_stesso_lettore(monkeypatch):
    from Betfair.safe_strategy import bot_service as B

    assert B._avvia_esiti_ordini() is False            # spento
    assert type(B._esiti_ciclo()).__name__ == "nullcontext"
    esiti = _accendi(monkeypatch)
    assert B._esiti_ciclo() is esiti.ciclo()
