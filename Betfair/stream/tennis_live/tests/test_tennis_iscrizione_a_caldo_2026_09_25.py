"""ISCRIZIONE E ARMAMENTO A CALDO del runner tennis (25/09).

Ordine dell'utente: «TUTTI I BOT UNA VOLTA ARMATI DEVONO OPERARE SU TUTTE LE
PARTITE IDONEE DA SOLI». Prima: un follow nuovo voleva la RICOSTRUZIONE del
framework, rinviata finche' un qualunque bot era in posizione. Ora la partita
entra sulla STESSA connessione (nuovo ``marketSubscription``) e i suoi bot si
armano nel framework vivo.

Classi VERE dove conta: ``Flumine`` (con ``BetfairClient`` paper/live di
``build_order_client``), capture ``_make_capture``, bot ``_instantiate_bot``,
``TennisRecMarketStream`` e il suo listener, ``BetfairStream`` di
betfairlightweight (solo il socket e' finto: registra i messaggi), mcm Betfair
col market definition completo, ``Trade``/``LimitOrder``/``Blotter`` di
flumine per le posizioni. Il DB e' un finto che parla come ``tennis_db``
(stesse firme, righe con le chiavi di ``tennis_live_follow`` e
``tennis_bot_control``). Il ciclo di flumine e' una pompa che passa gli
eventi della ``handler_queue`` VERA a ``_process_custom_event`` VERO.
"""
from __future__ import annotations

import json
import queue
import threading
import types
from typing import Any, Dict, List, Optional

import betfairlightweight
import pytest
from betfairlightweight.filters import streaming_market_data_filter
from betfairlightweight.streaming.betfairstream import BetfairStream
from flumine import Flumine
from flumine.events.events import CustomEvent, MarketBookEvent
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.stream.tennis_live import guardie_tennis as GT
from Betfair.stream.tennis_live import iscrizione_a_caldo as IAC
from Betfair.stream.tennis_live import tennis_runner as TR

ORA_ISO = "2026-09-25T10:00:00+00:00"


# ===========================================================================
# righe con le chiavi del vero
# ===========================================================================
def _follow(ev: str, origine: Optional[str] = "auto", status: str = "STREAMING") -> Dict[str, Any]:
    f = {"event_id": ev, "market_id": "1.%s" % ev, "competition_name": "ATP",
         "player1_name": "A", "player2_name": "B", "open_date": ORA_ISO,
         "status": status, "error_detail": None, "inplay": True, "score": None,
         "live_status": None, "created_at": ORA_ISO, "updated_at": ORA_ISO,
         "record": False}
    if origine is not None:
        f["origine"] = origine
    return f


def _control(ev: str, bot: str = "tennis_flb", status: str = "requested",
             mode: str = "paper", dry_run: Any = False) -> Dict[str, Any]:
    return {"event_id": ev, "bot_key": bot, "status": status, "dry_run": dry_run,
            "stake": 3, "params": {}, "stats": None, "error": None,
            "mode": mode, "heartbeat_at": None, "started_at": None,
            "stopped_at": None, "updated_at": None, "uscite_automatiche": True}


class _Db:
    """Parla come ``tennis_db`` (stesse firme, stessi ritorni)."""

    def __init__(self) -> None:
        self.follows: List[Dict[str, Any]] = []
        self.controls: List[Dict[str, Any]] = []
        self.stati: List[tuple] = []
        self.follow_stati: List[tuple] = []
        self.attivita: List[tuple] = []

    def list_pending_tennis_follows(self) -> List[Dict[str, Any]]:
        return [dict(f) for f in self.follows if f["status"] in ("PENDING", "STREAMING")]

    def list_tennis_bot_controls(self, event_id: Optional[str] = None,
                                 statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        out = []
        for r in self.controls:
            if event_id is not None and r["event_id"] != event_id:
                continue
            if statuses and r["status"] not in statuses:
                continue
            out.append(dict(r))
        return out

    def set_tennis_bot_status(self, event_id: str, bot_key: str, status: str, *,
                              error: Optional[str] = None, stats: Optional[Dict[str, Any]] = None,
                              heartbeat: bool = False, started: bool = False,
                              stopped: bool = False) -> None:
        self.stati.append((event_id, bot_key, status, error))
        for r in self.controls:
            if r["event_id"] == event_id and r["bot_key"] == bot_key:
                r["status"] = status
                r["error"] = error

    def write_tennis_bot_activity(self, event_id: str, bot_key: str, kind: str,
                                  payload: Dict[str, Any]) -> None:
        self.attivita.append((event_id, bot_key, kind, payload))

    def set_tennis_follow_status(self, event_id: str, status: str,
                                 error_detail: Optional[str] = None) -> None:
        self.follow_stati.append((event_id, status, error_detail))
        for f in self.follows:
            if f["event_id"] == event_id:
                f["status"] = status
                f["error_detail"] = error_detail

    def set_tennis_bot_wait_reason(self, event_id: str, bot_key: str,
                                   reason: Optional[str]) -> None:
        pass

    def _now_iso(self) -> str:
        return ORA_ISO


# ===========================================================================
# il banco: framework VERO come lo costruisce setup_and_run
# ===========================================================================
class _Socket:
    def __init__(self) -> None:
        self.inviati: List[Dict[str, Any]] = []

    def sendall(self, b: bytes) -> None:
        self.inviati.append(json.loads(b.decode("utf-8").strip()))


def _mcm(uid: int, market_id: str, event_id: str) -> str:
    return json.dumps({
        "op": "mcm", "id": uid, "clk": "AAA", "pt": 1758794400000,
        "initialClk": "BBB", "ct": "SUB_IMAGE",
        "mc": [{"id": market_id, "img": True, "marketDefinition": {
            "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
            "marketBaseRate": 5.0, "eventId": event_id, "eventTypeId": "2",
            "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
            "marketTime": "2026-09-25T10:00:00.000Z", "suspendTime": "2026-09-25T10:00:00.000Z",
            "bspReconciled": False, "complete": True, "inPlay": False, "crossMatching": True,
            "runnersVoidable": False, "numberOfActiveRunners": 2, "betDelay": 0,
            "status": "OPEN",
            "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": 11},
                        {"status": "ACTIVE", "sortPriority": 2, "id": 22}],
            "regulators": ["MR_INT"], "countryCode": "GB", "discountAllowed": True,
            "timezone": "GMT", "openDate": "2026-09-25T10:00:00.000Z", "version": 1},
            "rc": [{"id": 11, "batb": [[0, 2.0, 10]], "batl": [[0, 2.1, 10]]}]}]})


def _meta(ev: str) -> Dict[str, Any]:
    return {"market_id": "1.%s" % ev, "event_id": ev, "market_type": "MATCH_ODDS",
            "market_name": "Match Odds", "name_to_sel": {"A": 11, "B": 22},
            "selection_names": {"11": "A", "22": "B"}}


class Banco:
    """Framework, sessione e connessione come dopo ``setup_and_run``."""

    def __init__(self, db: _Db, follows: List[Dict[str, Any]], mode: str = "PAPER") -> None:
        self.db = db
        db.follows = follows
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        self.session = TR.TennisLiveSession(trading=api)
        client, _on = TR.build_order_client(api, mode)
        self.fw = Flumine(client=client)
        self.client = client
        self.client_paper = None
        if mode == "LIVE":
            self.client_paper = GT.build_client_paper_affiancato(api)
            self.fw.add_client(self.client_paper)
        self.session.order_mode = mode
        self.df = streaming_market_data_filter(fields=list(TR.STREAM_FIELDS),
                                               ladder_levels=TR.LADDER_DEPTH)
        for f in follows:
            TR._catalog_follow(self.session, f)
        mids = sorted(m["market_id"] for m in self.session.market_meta.values())
        self.cap = TR._make_capture(mids[0], "*", market_ids=mids)
        self.cap.market_data_filter = self.df
        self.fw.add_strategy(self.cap)
        for ev, meta in self.session.market_meta.items():
            self.session.capture[ev] = self.cap
            for bk, ctrl in TR._desired_controls(ev).items():
                bot = TR._instantiate_bot(bk, ctrl, meta["market_id"], meta["name_to_sel"],
                                          TR._make_sink(ev, bk), self.df, mode,
                                          market_ids=mids, client_paper=self.client_paper)
                self.fw.add_strategy(bot)
                self.session.hosted[(ev, bk)] = bot
                db.set_tennis_bot_status(ev, bk, "running", started=True)
        self.session.caldo = TR.ContestoCaldo(self.fw, self.cap, self.df, mode,
                                              self.client_paper)
        self.stream = self.cap.streams[0]
        self.socket = _Socket()
        self.bs = BetfairStream(self.stream.stream_id, self.stream._listener, "k", "t",
                                1.0, 1024, None)
        self.bs._socket = self.socket
        self.bs._running = True
        self.stream._stream = self.bs
        # come MarketStream.run: la prima sottoscrizione
        self.stream.stream_id = self.bs.subscribe_to_markets(
            market_filter=self.stream.market_filter,
            market_data_filter=self.stream.market_data_filter,
            conflate_ms=self.stream.conflate_ms)
        self.terminazioni = 0
        self._stop = False
        self._pompa = threading.Thread(target=self._gira, daemon=True)
        self._pompa.start()

    # il ciclo di flumine: CustomEvent -> _process_custom_event VERO
    def _gira(self) -> None:
        while not self._stop:
            try:
                ev = self.fw.handler_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if isinstance(ev, CustomEvent):
                self.fw._process_custom_event(ev)
            elif ev.EVENT_TYPE.name == "TERMINATOR":
                self.terminazioni += 1

    def chiudi(self) -> None:
        self._stop = True
        self._pompa.join(timeout=2)

    def book(self, ev: str) -> None:
        """Un SUB_IMAGE del mercato della partita sulla sottoscrizione CORRENTE,
        processato da flumine (crea il Market e il suo blotter)."""
        self.stream._listener.on_data(_mcm(self.stream.stream_id, "1.%s" % ev, ev))
        books = self.stream._output_queue.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))

    def posizione(self, ev: str, bot_key: str, lato: str = "BACK", prezzo: float = 2.0,
                  size: float = 10.0) -> Any:
        """Un ordine ABBINATO (simulato) del bot nel blotter VERO del mercato."""
        strat = self.session.hosted[(ev, bot_key)]
        market = self.fw.markets.markets["1.%s" % ev]
        trade = Trade("1.%s" % ev, 11, 0, strat)
        o = trade.create_order(lato, LimitOrder(prezzo, size))
        o.update_client(self.client)
        o.simulated.matched = [[0, prezzo, size]]
        o.simulated.size_matched = size
        o.simulated.average_price_matched = prezzo
        o.execution_complete()
        market.blotter[o.id] = o
        return o

    def mercati_sottoscritti(self) -> List[str]:
        return list(self.socket.inviati[-1]["marketFilter"]["marketIds"])

    def market_stream(self) -> List[Any]:
        from flumine.streams.marketstream import MarketStream
        return [s for s in self.fw.streams if isinstance(s, MarketStream)]


@pytest.fixture
def db(monkeypatch):
    d = _Db()
    monkeypatch.setattr(TR, "tennis_db", d)
    monkeypatch.setattr(TR._cm, "tennis_db", d, raising=False)
    monkeypatch.setattr(TR, "_resolve_market", lambda trading, mid, ev: _meta(ev))
    monkeypatch.setattr(TR, "_CANCELLO_BOT_CONTROL", None)
    monkeypatch.delenv(IAC.ENV_INTERRUTTORE, raising=False)
    monkeypatch.delenv(IAC.ENV_TETTO, raising=False)
    monkeypatch.setenv(IAC.ENV_GRAZIA_USCITA, "0")
    GT.azzera_per_i_test()
    yield d
    GT.azzera_per_i_test()


@pytest.fixture
def banchi():
    fatti: List[Banco] = []
    yield fatti
    for b in fatti:
        b.chiudi()


def _banco(db: _Db, banchi: List[Banco], follows: List[Dict[str, Any]],
           mode: str = "PAPER") -> Banco:
    b = Banco(db, follows, mode)
    banchi.append(b)
    return b


# ===========================================================================
# 1. IL CASO DELL'UTENTE: bot in posizione, partita nuova -> entra e si arma
# ===========================================================================
def test_follow_nuovo_con_bot_in_posizione_entra_e_si_arma_senza_ricostruire(db, banchi):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    ordine = b.posizione("101", "tennis_flb")
    flb = b.session.hosted[("101", "tennis_flb")]
    esp_prima = b.fw.markets.markets["1.101"].blotter.get_exposures(flb, ("1.101", 11, 0.0))
    assert TR._mercato_con_posizioni(b.fw, "1.101") is True
    id_prima, gen_prima = b.stream.stream_id, b.session.framework_gen

    db.follows.append(_follow("102"))
    db.controls.append(_control("102", "tennis_pro"))
    TR.follow_worker({}, b.fw, b.session)

    # nessuna ricostruzione
    assert not b.session.restart_requested.is_set()
    assert b.terminazioni == 0
    assert b.session.framework_gen == gen_prima
    # risottoscrizione a caldo sulla STESSA connessione, filtro canonico
    ultimo = b.socket.inviati[-1]
    assert ultimo["op"] == "marketSubscription"
    assert ultimo["marketFilter"]["marketIds"] == ["1.101", "1.102"]
    assert ultimo["id"] == id_prima + 1 == b.stream.stream_id
    assert len(b.market_stream()) == 1
    # la partita e' seguita e il bot e' armato NELLO STESSO stream
    assert "102" in b.session.market_meta
    pro = b.session.hosted[("102", "tennis_pro")]
    assert pro.streams == [b.stream]
    for s in b.fw.strategies:
        assert list(s.stream_ids) == [b.stream.stream_id]
        assert s.market_filter == b.stream.market_filter
    assert ("102", "STREAMING", None) in db.follow_stati
    assert [s[2] for s in db.stati if s[:2] == ("102", "tennis_pro")] == ["arming", "running"]
    # il bot in posizione e le sue posizioni NON sono stati toccati
    assert b.session.hosted[("101", "tennis_flb")] is flb
    assert not getattr(flb, "_tennis_disabled", False)
    assert getattr(flb, "force_flat", False) is False
    blotter = b.fw.markets.markets["1.101"].blotter
    assert ordine.id in [o.id for o in blotter]
    assert blotter.get_exposures(flb, ("1.101", 11, 0.0)) == esp_prima
    # il book della partita nuova arriva col nuovo id e crea il suo mercato
    b.book("102")
    assert "1.102" in b.fw.markets.markets


def test_interruttore_spento_come_prima_rinvia_la_ricostruzione(db, banchi, monkeypatch):
    """Il PRIMA, per contrasto: interruttore spento = ricostruzione rinviata
    finche' il bot e' in posizione, la partita nuova non entra."""
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    b.posizione("101", "tennis_flb")
    monkeypatch.setenv(IAC.ENV_INTERRUTTORE, "0")
    n_inviati = len(b.socket.inviati)
    db.follows.append(_follow("102"))
    db.controls.append(_control("102", "tennis_pro"))
    TR.follow_worker({}, b.fw, b.session)
    assert "102" not in b.session.market_meta
    assert len(b.socket.inviati) == n_inviati
    assert not b.session.restart_requested.is_set()


def test_bot_nuovo_su_partita_seguita_si_arma_a_caldo_senza_sottoscrivere(db, banchi):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    b.posizione("101", "tennis_flb")
    n_inviati = len(b.socket.inviati)
    db.controls.append(_control("101", "tennis_swing"))
    TR.bot_control_worker({}, b.fw, b.session)
    sw = b.session.hosted[("101", "tennis_swing")]
    assert sw.streams == [b.stream]
    assert len(b.market_stream()) == 1
    assert len(b.socket.inviati) == n_inviati, "nessuna sottoscrizione per un bot"
    assert b.terminazioni == 0 and not b.session.restart_requested.is_set()
    assert ("101", "tennis_swing", "running", None) in db.stati


def test_disarmo_a_caldo_non_chiede_ricostruzioni(db, banchi):
    db.controls = [_control("101", "tennis_flb", status="running"),
                   _control("101", "tennis_pro", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    db.controls[1]["status"] = "stopping"      # la UI disarma il pro
    TR.bot_control_worker({}, b.fw, b.session)
    pro = b.session.hosted[("101", "tennis_pro")]
    assert getattr(pro, "_tennis_disabled", False) is True
    assert ("101", "tennis_pro", "stopped", None) in db.stati
    assert b.terminazioni == 0 and not b.session.restart_requested.is_set()


def test_riarmo_dopo_lo_stop_si_arma_a_caldo_coi_parametri_nuovi(db, banchi):
    db.controls = [_control("101", "tennis_pro", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    db.controls[0]["status"] = "stopping"
    TR.bot_control_worker({}, b.fw, b.session)
    vecchio = b.session.hosted[("101", "tennis_pro")]
    assert vecchio._tennis_disabled is True
    db.controls[0].update({"status": "requested", "stake": 5})
    TR.bot_control_worker({}, b.fw, b.session)
    nuovo = b.session.hosted[("101", "tennis_pro")]
    assert nuovo is not vecchio and not getattr(nuovo, "_tennis_disabled", False)
    assert nuovo.streams == [b.stream]
    assert b.terminazioni == 0


# ===========================================================================
# 2. TETTO E PRIORITA'
# ===========================================================================
def test_tetto_pieno_la_armata_espelle_la_candidata_e_mai_oltre_il_tetto(db, banchi, monkeypatch):
    monkeypatch.setenv(IAC.ENV_TETTO, "2")
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101", origine="manuale"), _follow("102")])
    db.follows.append(_follow("103"))
    db.controls.append(_control("103", "tennis_pro"))
    TR.follow_worker({}, b.fw, b.session)
    assert sorted(b.session.market_meta) == ["101", "103"]
    assert b.mercati_sottoscritti() == ["1.101", "1.103"]
    assert ("102", "PENDING", "in attesa: tolta per far posto (tetto 2 mercati)") in db.follow_stati
    # una quarta armata non espelle una pari: rifiutata e dichiarata
    n_inviati = len(b.socket.inviati)
    db.follows.append(_follow("104"))
    db.controls.append(_control("104", "tennis_pro"))
    TR.follow_worker({}, b.fw, b.session)
    assert "104" not in b.session.market_meta
    assert len(b.socket.inviati) == n_inviati
    assert any(e == "104" and "tetto di 2" in (d or "") for e, _s, d in db.follow_stati)
    assert all(len(m["marketFilter"]["marketIds"]) <= 2 for m in b.socket.inviati[1:])


def test_mai_espulse_la_partita_con_posizioni_ne_quella_a_mano(db, banchi, monkeypatch):
    monkeypatch.setenv(IAC.ENV_TETTO, "2")
    db.controls = [_control("102", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101", origine="manuale"), _follow("102")])
    b.book("102")
    b.posizione("102", "tennis_flb")
    db.follows.append(_follow("103", origine="manuale"))
    TR.follow_worker({}, b.fw, b.session)
    assert sorted(b.session.market_meta) == ["101", "102"]
    assert not getattr(b.session.hosted[("102", "tennis_flb")], "_tennis_disabled", False)


def test_la_partita_a_mano_espelle_una_armata_flat(db, banchi, monkeypatch):
    monkeypatch.setenv(IAC.ENV_TETTO, "2")
    db.controls = [_control("102", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101", origine="manuale"), _follow("102")])
    flb = b.session.hosted[("102", "tennis_flb")]
    db.follows.append(_follow("103", origine="manuale"))
    TR.follow_worker({}, b.fw, b.session)
    assert sorted(b.session.market_meta) == ["101", "103"]
    assert flb._tennis_disabled is True and ("102", "tennis_flb") not in b.session.hosted
    motivo = [e for (ev, bk, st, e) in db.stati if (ev, bk, st) == ("102", "tennis_flb", "stopped")]
    assert motivo and "far posto" in motivo[0]


# ===========================================================================
# 3. USCITA: follow chiuso -> fuori a flat, mai con posizioni
# ===========================================================================
def test_follow_chiuso_esce_e_disarma_a_flat(db, banchi):
    db.controls = [_control("102", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101"), _follow("102")])
    flb = b.session.hosted[("102", "tennis_flb")]
    db.follows[1]["status"] = "CLOSED"
    TR.follow_worker({}, b.fw, b.session)
    assert list(b.session.market_meta) == ["101"]
    assert b.mercati_sottoscritti() == ["1.101"]
    assert flb._tennis_disabled is True
    assert ("102", "tennis_flb") not in b.session.hosted
    assert any(s[:3] == ("102", "tennis_flb", "stopped") and "follow chiuso" in s[3]
               for s in db.stati)


def test_follow_chiuso_con_posizione_resta_finche_non_e_flat(db, banchi):
    db.controls = [_control("102", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101"), _follow("102")])
    b.book("102")
    b.posizione("102", "tennis_flb", "BACK", 2.0, 10.0)
    flb = b.session.hosted[("102", "tennis_flb")]
    db.follows[1]["status"] = "CLOSED"
    n_inviati = len(b.socket.inviati)
    TR.follow_worker({}, b.fw, b.session)
    assert "102" in b.session.market_meta
    assert not getattr(flb, "_tennis_disabled", False)
    assert len(b.socket.inviati) == n_inviati
    # la posizione si chiude (lay che pareggia): al giro dopo esce
    b.posizione("102", "tennis_flb", "LAY", 2.0, 10.0)
    TR.follow_worker({}, b.fw, b.session)
    assert "102" not in b.session.market_meta
    assert flb._tennis_disabled is True


def test_grazia_d_uscita_una_lettura_a_vuoto_non_toglie_niente(db, banchi, monkeypatch):
    monkeypatch.setenv(IAC.ENV_GRAZIA_USCITA, "3600")
    b = _banco(db, banchi, [_follow("101"), _follow("102")])
    db.follows[1]["status"] = "CLOSED"
    TR.follow_worker({}, b.fw, b.session)
    assert sorted(b.session.market_meta) == ["101", "102"]


def test_nessuna_partita_resta_ricostruzione_verso_l_attesa_mai_filtro_vuoto(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    n_inviati = len(b.socket.inviati)
    db.follows[0]["status"] = "CLOSED"
    TR.follow_worker({}, b.fw, b.session)
    assert len(b.socket.inviati) == n_inviati, "mai un marketSubscription vuoto"
    assert b.session.restart_requested.is_set()


# ===========================================================================
# 4. PAPER / LIVE separati anche a caldo
# ===========================================================================
@pytest.mark.parametrize("mode,dry,esec,dry_atteso,instradato", [
    ("paper", False, "PAPER", False, True),
    ("live", False, "LIVE", False, False),
    ("live", None, "LIVE", True, False),
])
def test_live_runner_a_caldo_stessa_guardia_della_build(db, banchi, mode, dry, esec,
                                                       dry_atteso, instradato):
    b = _banco(db, banchi, [_follow("101")], mode="LIVE")
    db.follows.append(_follow("102"))
    db.controls.append(_control("102", "tennis_flb", mode=mode, dry_run=dry))
    TR.follow_worker({}, b.fw, b.session)
    bot = b.session.hosted[("102", "tennis_flb")]
    assert bot._tennis_modalita_esecuzione == esec
    assert bool(bot.dry_run) is dry_atteso
    assert (getattr(bot, "_tennis_client_ordini", None) is b.client_paper) is instradato
    # identico a un bot della build con la stessa riga
    gemello = TR._instantiate_bot("tennis_flb", _control("102", "tennis_flb", mode=mode,
                                                         dry_run=dry),
                                  "1.102", {"A": 11, "B": 22}, None, b.df, "LIVE",
                                  market_ids=["1.101", "1.102"],
                                  client_paper=b.client_paper)
    def _impronta(s: Any) -> tuple:
        return (s.dry_run, s._tennis_modalita_esecuzione, s._tennis_modalita_riga,
                getattr(s, "size_step", None), getattr(s, "live_min_bet", None),
                s.max_selection_exposure, s.max_order_exposure, s.stake,
                getattr(s, "_tennis_client_ordini", None) is not None)
    assert _impronta(bot) == _impronta(gemello)


def test_runner_paper_a_caldo_mai_reale(db, banchi):
    b = _banco(db, banchi, [_follow("101")], mode="PAPER")
    db.follows.append(_follow("102"))
    db.controls.append(_control("102", "tennis_flb", mode="live", dry_run=False))
    TR.follow_worker({}, b.fw, b.session)
    bot = b.session.hosted[("102", "tennis_flb")]
    assert bot._tennis_modalita_esecuzione == "PAPER"
    assert b.client.paper_trade is True


def test_guardia_d_avvio_armata_la_partita_entra_ma_nessun_bot(db, banchi, monkeypatch):
    b = _banco(db, banchi, [_follow("101")])
    monkeypatch.setattr(GT, "ripresa_all_avvio", lambda db=None: False)
    GT.arma_guardia_runner()
    try:
        db.follows.append(_follow("102"))
        db.controls.append(_control("102", "tennis_flb"))
        TR.follow_worker({}, b.fw, b.session)
        assert "102" in b.session.market_meta
        assert ("102", "tennis_flb") not in b.session.hosted
        TR.bot_control_worker({}, b.fw, b.session)
        assert ("102", "tennis_flb") not in b.session.hosted
    finally:
        GT.azzera_per_i_test()


# ===========================================================================
# 5. connessione non pronta, lavoro non eseguito, bot fuori dallo stream
# ===========================================================================
def test_stream_non_connesso_niente_cambia_e_si_riprova(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    b.bs._running = False
    db.follows.append(_follow("102"))
    TR.follow_worker({}, b.fw, b.session)
    assert "102" not in b.session.market_meta
    assert not b.session.restart_requested.is_set()
    b.bs._running = True
    TR.follow_worker({}, b.fw, b.session)
    assert "102" in b.session.market_meta


def test_ciclo_di_flumine_fermo_lavoro_annullato_mai_eseguito_dopo():
    coda: "queue.Queue[Any]" = queue.Queue()
    fw = types.SimpleNamespace(handler_queue=coda)
    fatto: List[int] = []
    with pytest.raises(IAC.TempoScaduto):
        IAC.esegui_nel_thread_di_flumine(fw, lambda f: fatto.append(1), timeout=0.05)
    ev = coda.get_nowait()
    ev.callback(fw, ev)                  # il ciclo riparte: il lavoro NON gira
    assert fatto == []


def test_bot_con_data_filter_diverso_non_entra_e_non_lascia_stream(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    altro_df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=1)
    bot = TR._instantiate_bot("tennis_flb", _control("101"), "1.101", {"A": 11, "B": 22},
                              None, altro_df, "PAPER", market_ids=["1.101"])
    n_stream, n_strat = len(list(b.fw.streams)), len(list(b.fw.strategies))
    with pytest.raises(ValueError):
        IAC.aggiungi_strategia_sullo_stream(b.fw, b.stream, bot)
    assert len(list(b.fw.streams)) == n_stream and len(list(b.fw.strategies)) == n_strat


def test_bot_che_flumine_metterebbe_su_uno_stream_nuovo_non_entra(db, banchi):
    """conflate diverso: flumine creerebbe una MarketStream NUOVA (mai avviata:
    bot cieco). Si toglie lo stream spurio e il bot, e si solleva."""
    b = _banco(db, banchi, [_follow("101")])
    bot = TR._instantiate_bot("tennis_flb", _control("101"), "1.101", {"A": 11, "B": 22},
                              None, b.df, "PAPER", market_ids=["1.101"])
    bot.conflate_ms = 100
    n_stream, n_strat = len(list(b.fw.streams)), len(list(b.fw.strategies))
    with pytest.raises(RuntimeError):
        IAC.aggiungi_strategia_sullo_stream(b.fw, b.stream, bot)
    assert len(list(b.fw.streams)) == n_stream and len(list(b.fw.strategies)) == n_strat


def test_filtro_canonico_ordinato_anche_se_la_nuova_viene_prima(db, banchi):
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    db.follows.append(_follow("099"))
    db.controls.append(_control("099", "tennis_pro"))
    TR.follow_worker({}, b.fw, b.session)
    assert b.mercati_sottoscritti() == ["1.099", "1.101"]
    assert b.session.hosted[("099", "tennis_pro")].streams == [b.stream]
    assert len(b.market_stream()) == 1


def test_posizione_aperta_durante_il_catalogo_la_partita_non_esce(db, banchi, monkeypatch):
    """Il piano espelle la 102 (armata, flat) per la 103 a mano; mentre si legge
    il catalogo della 103 il bot della 102 viene abbinato. Nel ciclo di flumine
    le posizioni si RICONTROLLANO: la 102 resta, la 103 non entra (tetto)."""
    monkeypatch.setenv(IAC.ENV_TETTO, "2")
    db.controls = [_control("102", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101", origine="manuale"), _follow("102")])
    b.book("102")
    vero = TR._risolvi_follow

    def _catalogo_lento(session: Any, follow: Dict[str, Any]) -> Any:
        b.posizione("102", "tennis_flb")
        return vero(session, follow)
    monkeypatch.setattr(TR, "_risolvi_follow", _catalogo_lento)
    db.follows.append(_follow("103", origine="manuale"))
    TR.follow_worker({}, b.fw, b.session)
    assert sorted(b.session.market_meta) == ["101", "102"]
    assert not getattr(b.session.hosted[("102", "tennis_flb")], "_tennis_disabled", False)
    assert all(len(m["marketFilter"]["marketIds"]) <= 2 for m in b.socket.inviati)


def test_sottoscrizione_vuota_o_oltre_200_rifiutata(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    with pytest.raises(ValueError):
        IAC.sottoscrivi(b.fw, b.stream, [])
    with pytest.raises(ValueError):
        IAC.sottoscrivi(b.fw, b.stream, ["1.%d" % i for i in range(201)])


def test_book_della_sottoscrizione_vecchia_scartato(db, banchi):
    b = _banco(db, banchi, [_follow("101")])
    vecchio = b.stream.stream_id
    db.follows.append(_follow("102"))
    TR.follow_worker({}, b.fw, b.session)
    b.stream._listener.on_data(_mcm(vecchio, "1.101", "101"))
    assert b.stream._output_queue.empty()


# ===========================================================================
# 6. il piano (puro) e i tetti
# ===========================================================================
E = IAC.Evento


def test_piano_entra_se_c_e_posto():
    p = IAC.pianifica([E("1")], [E("1"), E("2", armata=True)], 5)
    assert p.aggiungi == ["2"] and not p.espulsi and not p.rifiutati


def test_piano_priorita_fra_le_nuove_a_mano_poi_armate_poi_candidate():
    p = IAC.pianifica([], [E("c"), E("a", armata=True), E("m", manuale=True)], 2)
    assert p.aggiungi == ["m", "a"] and p.rifiutati == ["c"]


def test_piano_espelle_la_meno_prioritaria_e_piu_vecchia():
    seguiti = [E("x", armata=True), E("c1"), E("c2")]
    p = IAC.pianifica(seguiti, seguiti + [E("n", armata=True)], 3)
    assert p.espulsi == ["c1"] and p.aggiungi == ["n"]


def test_piano_niente_giostra_fra_pari():
    seguiti = [E("a", armata=True)]
    p = IAC.pianifica(seguiti, seguiti + [E("b", armata=True)], 1)
    assert p.rifiutati == ["b"] and not p.espulsi


def test_piano_mai_posizioni_mai_a_mano():
    # difesa doppia: la manuale ha la priorita' piu' alta E non e' espellibile
    assert E("m", manuale=True).espellibile is False
    assert E("p", armata=True, posizioni=True).espellibile is False
    assert E("m", manuale=True, in_uscita=True).espellibile is True
    seguiti = [E("m", manuale=True), E("p", armata=True, posizioni=True)]
    p = IAC.pianifica(seguiti, seguiti + [E("n", manuale=True)], 2)
    assert p.rifiutati == ["n"] and not p.espulsi and not p.togli


def test_piano_uscita_grazia_e_posizioni():
    seguiti = [E("a"), E("b"), E("p", posizioni=True)]
    p = IAC.pianifica(seguiti, [], 5, pronti_a_uscire={"a", "p"})
    assert p.togli == ["a"] and p.tenuti_per_posizioni == ["p"]


def test_piano_l_uscente_in_grazia_cede_il_posto_per_primo():
    seguiti = [E("c"), E("g", armata=True)]
    p = IAC.pianifica(seguiti, [E("c"), E("n")], 2)
    assert p.togli == ["g"] and p.aggiungi == ["n"] and not p.espulsi


def test_piano_tetto_abbassato_non_espelle_i_seguiti():
    seguiti = [E("1"), E("2"), E("3")]
    p = IAC.pianifica(seguiti, seguiti + [E("4")], 2)
    assert not p.espulsi and p.rifiutati == ["4"]


@pytest.mark.parametrize("raw,atteso", [("", 180), ("50", 50), ("500", 200), ("0", 1),
                                        ("abc", 180), ("-3", 1)])
def test_tetto_mercati(raw, atteso):
    assert IAC.tetto_mercati({IAC.ENV_TETTO: raw}) == atteso


@pytest.mark.parametrize("raw,atteso", [("", True), ("1", True), ("0", False),
                                        ("off", False), ("no", False)])
def test_interruttore(raw, atteso):
    assert IAC.acceso({IAC.ENV_INTERRUTTORE: raw}) is atteso


def test_build_rientra_nel_tetto_a_mano_e_armate_prima(db, monkeypatch):
    monkeypatch.setenv(IAC.ENV_TETTO, "2")
    db.controls = [_control("2", "tennis_flb", status="requested")]
    follows = [_follow("1"), _follow("2"), _follow("3", origine="manuale")]
    tenuti = TR._entro_il_tetto_al_build(follows)
    assert [f["event_id"] for f in tenuti] == ["2", "3"]
    assert any(e == "1" and s == "PENDING" for e, s, _d in db.follow_stati)


def test_build_sotto_il_tetto_nessuna_lettura(db):
    letture: List[int] = []
    db.list_tennis_bot_controls = lambda *a, **k: letture.append(1) or []  # type: ignore
    follows = [_follow("1"), _follow("2")]
    assert TR._entro_il_tetto_al_build(follows) == follows
    assert letture == []
