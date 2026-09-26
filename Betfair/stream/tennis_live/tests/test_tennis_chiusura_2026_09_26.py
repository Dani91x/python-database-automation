# -*- coding: utf-8 -*-
"""R-FA-1 (e2e 26/09, FAIL 7.7.8 / 7.9.6.B / 7.9.6.E1): una partita tennis
AUTOMATICA finita non si chiudeva mai.

Il reperto (``AUDIT_2026-09-25/e2e_fase2/ADMIN26_AUTOMODE_SAFE.md`` §B):
- flumine non passa MAI un book CLOSED a ``process_market_book``
  (``baseflumine._process_market_books``: ``CloseMarketEvent`` + ``continue``)
  e la capture del runner teneva l'ultimo book (SUSPENDED): ``tennis_live_now``
  non arrivava mai a CLOSED (0 righe su tutta la tabella) e veniva riscritta
  ogni 2 s per ore;
- il ponte fermava le partite automatiche uscite dal feed SOLO su CLOSED;
- il tetto contava solo le armate ancora nel feed: 12 armate per bot col tetto 5.

Classi VERE dove conta: ``Flumine`` + ``BetfairClient`` paper, la MarketStream
e il listener di betfairlightweight (messaggi ``mcm`` come quelli di Betfair),
``_make_capture`` e ``score_and_now_worker`` del runner, ``riconcilia_interruttori``
e ``ferma_bot_al_nuovo_avvio`` del ponte. I finti del database hanno le firme
e le chiavi di ``tennis_db`` e delle tabelle vere.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import json
import types
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import betfairlightweight
import pytest
from betfairlightweight.filters import streaming_market_data_filter
from flumine import Flumine
from flumine.events.events import CloseMarketEvent, MarketBookEvent

from Betfair.stream.tennis_live import auto_mode as AM
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_runner as TR

EV = "36118619"
MID = "1.262933523"
T0 = 1_790_000_000.0          # orologio finto del ponte (epoch)


# ===========================================================================
# A. RUNNER: il CLOSED arriva a tennis_live_now (flumine VERO)
# ===========================================================================
def _mcm(uid: int, status: str, inplay: bool, img: bool, pt: int) -> str:
    """Messaggio ``mcm`` di Betfair per il MATCH_ODDS della partita."""
    runners = [{"status": "ACTIVE", "sortPriority": 1, "id": 11},
               {"status": "ACTIVE", "sortPriority": 2, "id": 22}]
    if status == "CLOSED":
        runners = [{"status": "WINNER", "sortPriority": 1, "id": 11},
                   {"status": "LOSER", "sortPriority": 2, "id": 22}]
    mc: Dict[str, Any] = {"id": MID, "marketDefinition": {
        "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
        "marketBaseRate": 5.0, "eventId": EV, "eventTypeId": "2",
        "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
        "marketTime": "2026-09-26T08:00:00.000Z", "suspendTime": "2026-09-26T08:00:00.000Z",
        "bspReconciled": False, "complete": True, "inPlay": inplay, "crossMatching": True,
        "runnersVoidable": False, "numberOfActiveRunners": 2, "betDelay": 3,
        "status": status, "runners": runners, "regulators": ["MR_INT"],
        "countryCode": "GB", "discountAllowed": True, "timezone": "GMT",
        "openDate": "2026-09-26T08:00:00.000Z", "version": pt}}
    if img:
        mc["img"] = True
        mc["rc"] = [{"id": 11, "batb": [[0, 1.02, 10]], "batl": [[0, 1.03, 10]]}]
    msg: Dict[str, Any] = {"op": "mcm", "id": uid, "clk": "C%d" % pt, "pt": pt, "mc": [mc]}
    if img:
        msg["initialClk"] = "I"
        msg["ct"] = "SUB_IMAGE"
    return json.dumps(msg)


class _Banco:
    """Framework e capture come li costruisce ``setup_and_run`` (paper)."""

    def __init__(self) -> None:
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        client, _on = TR.build_order_client(api, "PAPER")
        self.fw = Flumine(client=client)
        self.cap = TR._make_capture(MID, EV, market_ids=[MID])
        self.cap.market_data_filter = streaming_market_data_filter(
            fields=list(TR.STREAM_FIELDS), ladder_levels=TR.LADDER_DEPTH)
        self.fw.add_strategy(self.cap)
        self.stream = self.cap.streams[0]
        # come ``subscribe_to_markets``: il listener registra la MarketStream
        self.stream._listener.register_stream(self.stream.stream_id, "marketSubscription")
        self.session = TR.TennisLiveSession(trading=api)
        self.session.market_meta[EV] = {
            "market_id": MID, "market_type": "MATCH_ODDS", "market_name": "Match Odds",
            "name_to_sel": {"Bondar": 11, "Birrell": 22},
            "selection_names": {"11": "Bondar", "22": "Birrell"}}
        self.session.capture[EV] = self.cap

    def arriva(self, status: str, inplay: bool, img: bool, pt: int) -> None:
        """Un messaggio dello stream, processato dal ciclo VERO di flumine
        (``_process_market_books`` e, se Betfair chiude, ``_process_close_market``)."""
        self.stream._listener.on_data(_mcm(self.stream.stream_id, status, inplay, img, pt))
        books = self.stream._output_queue.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))
        while not self.fw.handler_queue.empty():
            ev = self.fw.handler_queue.get_nowait()
            if isinstance(ev, CloseMarketEvent):
                self.fw._process_close_market(ev)


def test_flumine_vero_il_book_closed_arriva_alla_capture_e_a_tennis_live_now():
    b = _Banco()
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    assert TR._build_now_state(b.session, EV)[1:] == (True, "OPEN")
    b.arriva("SUSPENDED", True, False, 1_790_000_001_000)
    assert TR._build_now_state(b.session, EV)[1:] == (True, "SUSPENDED")
    b.arriva("CLOSED", True, False, 1_790_000_002_000)
    state, inplay, status = TR._build_now_state(b.session, EV)
    # IL REPERTO: prima restava SUSPENDED e in gioco per ore
    assert status == "CLOSED"
    assert inplay is False, "un mercato chiuso non e' in gioco (la UI scriveva LIVE)"
    assert state["markets"][0]["status"] == "CLOSED"
    assert state["markets"][0]["market_id"] == MID


def test_flumine_vero_non_passa_il_closed_a_process_market_book():
    """La causa, documentata: se flumine un giorno passasse il CLOSED a
    ``process_market_book`` questo test lo direbbe (e la correzione
    ``process_closed_market`` resterebbe comunque giusta)."""
    b = _Banco()
    visti: List[str] = []
    orig = b.cap.process_market_book
    b.cap.process_market_book = lambda m, mb: (visti.append(mb.status), orig(m, mb))
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    b.arriva("CLOSED", True, False, 1_790_000_002_000)
    assert visti == ["OPEN"]


class _Feed:
    """``ScanFeedScoreProvider`` senza riga (punteggio dal REST diretto)."""

    def __init__(self) -> None:
        self.direct_calls = 0

    def get_raw_state(self, event_id: str) -> None:  # noqa: ARG002
        return None


def _worker_banco(monkeypatch: Any) -> tuple:
    b = _Banco()
    scritte: List[tuple] = []
    monkeypatch.setattr(TR.tennis_db, "upsert_tennis_now",
                        lambda ev, inplay, status, state, score=None, points=None:
                        scritte.append((ev, inplay, status)))
    chiamate_ips: List[Any] = []
    b.session.trading = types.SimpleNamespace(in_play_service=types.SimpleNamespace(
        get_scores=lambda **kw: (chiamate_ips.append(kw), [])[1]))
    b.session._scan_feed = _Feed()
    b.session._stream_ka_ts = 1e18          # nessun keepAlive nel test
    return b, scritte, chiamate_ips


def test_score_worker_scrive_closed_una_volta_poi_smette(monkeypatch):
    b, scritte, ips = _worker_banco(monkeypatch)
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    b.arriva("CLOSED", True, False, 1_790_000_002_000)
    for _ in range(4):
        TR.score_and_now_worker({}, None, b.session)
    assert scritte == [(EV, False, "CLOSED")], \
        "CLOSED scritto UNA volta: prima la riga morta si riscriveva ogni 2 s"
    assert len(ips) == 1, "nessun punteggio chiesto per una partita finita"


def test_score_worker_partita_sospesa_si_riscrive_come_prima(monkeypatch):
    """Il contrario: un mercato SUSPENDED (partita viva, pioggia) si scrive a
    ogni giro come sempre."""
    b, scritte, ips = _worker_banco(monkeypatch)
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    b.arriva("SUSPENDED", True, False, 1_790_000_001_000)
    for _ in range(3):
        TR.score_and_now_worker({}, None, b.session)
    assert scritte == [(EV, True, "SUSPENDED")] * 3
    assert len(ips) == 3


def test_score_worker_closed_non_scritto_si_riprova(monkeypatch):
    b, scritte, _ips = _worker_banco(monkeypatch)
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    b.arriva("CLOSED", True, False, 1_790_000_002_000)
    giri = {"n": 0}

    def _upsert(ev, inplay, status, state, score=None, points=None):
        giri["n"] += 1
        if giri["n"] == 1:
            raise RuntimeError("DB KO")
        scritte.append((ev, inplay, status))

    monkeypatch.setattr(TR.tennis_db, "upsert_tennis_now", _upsert)
    for _ in range(3):
        TR.score_and_now_worker({}, None, b.session)
    assert scritte == [(EV, False, "CLOSED")] and giri["n"] == 2


def test_closed_scritto_sopravvive_al_reset_degli_stream(monkeypatch):
    """Dopo un rebuild il book vuoto direbbe SUSPENDED (default): la riga
    CLOSED gia' scritta non torna indietro."""
    b, scritte, _ips = _worker_banco(monkeypatch)
    b.arriva("OPEN", True, True, 1_790_000_000_000)
    b.arriva("CLOSED", True, False, 1_790_000_002_000)
    TR.score_and_now_worker({}, None, b.session)
    b.session.reset_streams()
    b.session.capture[EV] = TR._make_capture(MID, EV, market_ids=[MID])
    TR.score_and_now_worker({}, None, b.session)
    assert scritte == [(EV, False, "CLOSED")]


# ===========================================================================
# B. PONTE: la partita automatica finita si chiude, il tetto conta le vive
# ===========================================================================
def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _servizio(bot: str = "tennis_flb", status: str = "running",
              params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Riga VERA di ``tennis_bot_service_control``."""
    return {"bot_key": bot, "status": status, "mode": "paper", "stake": 3,
            "params": params if params is not None else {}, "stats": None,
            "error": None, "started_at": None, "stopped_at": None,
            "heartbeat_at": None, "updated_at": None}


def _control(ev: str, bot: str = "tennis_flb", status: str = "running",
             boot: Optional[str] = None) -> Dict[str, Any]:
    """Riga VERA di ``tennis_bot_control``."""
    return {"event_id": ev, "bot_key": bot, "status": status, "dry_run": True,
            "stake": 3, "params": {}, "stats": {"boot_id": boot} if boot else None,
            "error": None, "mode": "paper", "heartbeat_at": None, "started_at": None,
            "stopped_at": None, "updated_at": None}


def _follow(ev: str, origine: Optional[str] = "auto") -> Dict[str, Any]:
    """Riga VERA di ``tennis_live_follow``."""
    f = {"event_id": ev, "market_id": "1.%s" % ev, "competition_name": "ATP",
         "player1_name": "A", "player2_name": "B", "open_date": _iso(T0),
         "status": "STREAMING", "error_detail": None, "inplay": True, "score": None,
         "live_status": None, "created_at": _iso(T0), "updated_at": _iso(T0),
         "record": False}
    if origine is not None:
        f["origine"] = origine
    return f


class _Db:
    """Parla come ``tennis_db`` (stesse firme, stessi ritorni); orologio finto."""

    def __init__(self, servizi, *, controls=None, follows=None, feed_ev=None,
                 now_status=None, clock=None) -> None:
        self._servizi = servizi
        self.controls: List[Dict[str, Any]] = list(controls or [])
        self.follows: List[Dict[str, Any]] = list(follows or [])
        self.feed_ev: Optional[List[str]] = feed_ev
        self.now: Dict[str, str] = dict(now_status or {})
        self.clock = clock
        self.scanner_vivo = True
        self.armati: List[Dict[str, Any]] = []
        self.stati: List[tuple] = []
        self.servizio: List[Dict[str, Any]] = []
        self.follow_status: List[tuple] = []
        self.attivita: List[tuple] = []

    def list_tennis_bot_services(self):
        return [dict(r) for r in self._servizi]

    def set_tennis_bot_service_state(self, bot_key, *, status=None, stats=None,
                                     error=None, heartbeat=False, stopped=False, mode=None):
        self.servizio.append({"bot_key": bot_key, "status": status, "stats": stats})
        for r in self._servizi:
            if r["bot_key"] == bot_key and status is not None:
                r["status"] = status
        return True

    def list_tennis_bot_controls(self, event_id=None, statuses=None):
        out = [dict(r) for r in self.controls]
        if event_id is not None:
            out = [r for r in out if r["event_id"] == event_id]
        if statuses:
            out = [r for r in out if r["status"] in statuses]
        return out

    def upsert_tennis_bot_control(self, row):
        self.armati.append(dict(row))
        self.controls = [r for r in self.controls
                         if not (r["event_id"] == row["event_id"]
                                 and r["bot_key"] == row["bot_key"])]
        self.controls.append({**_control(row["event_id"], row["bot_key"]),
                              "status": row.get("status", "requested")})

    def set_tennis_bot_status(self, event_id, bot_key, status, *, error=None, stats=None,
                              heartbeat=False, started=False, stopped=False,
                              mode=None, dry_run=None):
        self.stati.append((event_id, bot_key, status))
        for r in self.controls:
            if r["event_id"] == event_id and r["bot_key"] == bot_key:
                r["status"] = status

    def set_tennis_bot_uscite(self, event_id, bot_key, automatiche):
        return True

    def write_tennis_bot_activity(self, event_id, bot_key, kind, payload):
        self.attivita.append((event_id, bot_key, kind))

    def list_pending_tennis_follows(self):
        return [dict(f) for f in self.follows if f["status"] in ("PENDING", "STREAMING")]

    def register_tennis_follow(self, event_id, market_id, player1_name, player2_name,
                               open_date=None, competition_name=None, status="PENDING",
                               origine=None):
        self.follows.append({**_follow(event_id, origine), "status": status})

    def set_tennis_follow_status(self, event_id, status, error_detail=None):
        self.follow_status.append((event_id, status))
        for f in self.follows:
            if f["event_id"] == event_id:
                f["status"] = status

    def list_tennis_feed_rows(self):
        """Righe di ``safe_strategy_scan`` sport tennis (``build_rows``)."""
        if self.feed_ev is None:
            return None
        return [{"event_id": ev, "sport": "tennis", "updated_at": _iso(self.clock()),
                 "payload": {"event_name": "A v B", "p1": "A", "p2": "B",
                             "competition": "ATP Test",
                             "open_date": _iso(T0 - 3600 + i), "inplay": True,
                             "mo_market_id": "1.%s" % ev, "mo_status": "OPEN",
                             "odds": None, "sets": None, "games": None, "media": None,
                             "score_raw": None, "mo_total_matched": 1000.0,
                             "odds_ts_ms": 1, "odds_pt_ms": 1, "bet_delay": 3}}
                for i, ev in enumerate(self.feed_ev)]

    def scanner_heartbeat(self):
        eta = 2.0 if self.scanner_vivo else 300.0
        return {"payload": {"cycle": 1}, "updated_at": _iso(self.clock() - eta)}

    def list_tennis_now_status(self, event_ids):
        return {e: self.now[e] for e in event_ids if e in self.now}


class _Orologio:
    def __init__(self) -> None:
        self.t = T0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def orologio(monkeypatch):
    o = _Orologio()
    monkeypatch.setattr(S.time, "time", o)
    monkeypatch.setattr(S._GUARDIA_AVVIO, "attiva", False)
    monkeypatch.delenv(AM.ENV_TETTO, raising=False)
    monkeypatch.delenv("TENNIS_AUTO_FINE_FUORI_FEED_S", raising=False)
    S._ORIGINE_ASSENTE["dal"] = None
    S._FUORI_FEED_DAL.clear()
    yield o
    S._FUORI_FEED_DAL.clear()
    S._ORIGINE_ASSENTE["dal"] = None


def _stats(db, bot="tennis_flb"):
    return [w for w in db.servizio if w["bot_key"] == bot][-1]["stats"]


def test_ponte_chiude_su_closed_scritto_dal_runner(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert (EV, "tennis_flb", "stopping") in db.stati


def test_ponte_rete_fuori_dal_feed_oltre_soglia_a_mercato_sospeso(orologio):
    """IL REPERTO: 36118619 uscita dal feed alle 09:26, SUSPENDED per ore."""
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "SUSPENDED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.stati == [], "appena uscita: potrebbe essere un buco del feed"
    orologio.t += 599
    S.riconcilia_interruttori(db)
    assert db.stati == [], "sotto la soglia di 600 s nessuna chiusura"
    orologio.t += 1
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]
    # il runner porta la riga a stopped (flat verificato): il follow si chiude
    for r in db.controls:
        r["status"] = "stopped"
    orologio.t += 15
    S.riconcilia_interruttori(db)
    assert (EV, "CLOSED") in db.follow_status


def test_ponte_rete_riga_now_assente_oltre_soglia(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={}, clock=orologio)
    S.riconcilia_interruttori(db)
    orologio.t += 600
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]


def test_ponte_rete_mercato_OPEN_fuori_dal_feed_non_si_chiude_mai(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "OPEN"}, clock=orologio)
    for _ in range(10):
        S.riconcilia_interruttori(db)
        orologio.t += 3600
    assert db.stati == [] and db.follow_status == []


def test_ponte_rete_rientrata_nel_feed_l_orologio_riparte(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "SUSPENDED"}, clock=orologio)
    S.riconcilia_interruttori(db)          # esce: T0
    orologio.t += 400
    db.feed_ev = [EV]
    S.riconcilia_interruttori(db)          # rientra: T0+400
    db.feed_ev = []
    orologio.t += 400
    S.riconcilia_interruttori(db)          # riesce: T0+800
    assert db.stati == [], "800 s dalla PRIMA uscita, ma 0 dall'ultima"
    orologio.t += 500
    S.riconcilia_interruttori(db)
    assert db.stati == [], "500 s dall'ultima uscita"
    orologio.t += 100
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]


def test_ponte_rete_scanner_fermo_l_orologio_riparte(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "SUSPENDED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    orologio.t += 400
    db.scanner_vivo = False
    S.riconcilia_interruttori(db)
    db.scanner_vivo = True
    orologio.t += 300
    S.riconcilia_interruttori(db)
    assert db.stati == [], "a scanner fermo l'assenza non si misura"


def test_ponte_rete_soglia_da_env(orologio, monkeypatch):
    monkeypatch.setenv("TENNIS_AUTO_FINE_FUORI_FEED_S", "60")
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV)],
             feed_ev=[], now_status={EV: "SUSPENDED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    orologio.t += 60
    S.riconcilia_interruttori(db)
    assert db.stati == [(EV, "tennis_flb", "stopping")]


def test_ponte_la_seguita_a_mano_non_si_chiude(orologio):
    db = _Db([_servizio()], controls=[_control(EV)], follows=[_follow(EV, "manuale")],
             feed_ev=[], now_status={EV: "CLOSED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    orologio.t += 3600
    S.riconcilia_interruttori(db)
    assert db.stati == [] and db.follow_status == []


def test_tetto_conta_le_armate_vive_fuori_dal_feed(orologio):
    """Tetto 2: una armata appena uscita dal feed (ancora viva) + 3 nel feed:
    si arma UNA sola partita nuova (prima due)."""
    db = _Db([_servizio(params={AM.CHIAVE_TETTO: 2})], controls=[_control("9")],
             follows=[_follow("9")], feed_ev=["1", "2", "3"],
             now_status={"9": "SUSPENDED"}, clock=orologio)
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["1"]


def test_scegli_partite_altre_vive():
    no = lambda ev: False  # noqa: E731
    assert AM.scegli_partite(["1", "2", "3"], [], no, 2)["nuove"] == ["1", "2"]
    assert AM.scegli_partite(["1", "2", "3"], ["9"], no, 2, altre_vive=1)["nuove"] == ["1"]
    assert AM.scegli_partite(["1", "2", "3"], ["8", "9"], no, 2, altre_vive=2)["nuove"] == []


def test_il_reperto_7_morte_e_5_vive_col_tetto_5(orologio):
    """14:39 UTC del 26/09: 7 partite finite SUSPENDED fuori dal feed + 5 nel
    feed, tetto 5, 12 armate per bot. Dopo la soglia: 7 in chiusura, nessuna
    nuova armata, 5 armate nel conto."""
    morte = ["36112100", "36117297", "36117278", "36116525", "36116721",
             "36116084", "36118619"]
    vive = ["1", "2", "3", "4", "5"]
    nuove = ["6", "7"]
    db = _Db([_servizio(params={AM.CHIAVE_TETTO: 5})],
             controls=[_control(e) for e in morte + vive],
             follows=[_follow(e) for e in morte + vive],
             feed_ev=vive + nuove, now_status={e: "SUSPENDED" for e in morte},
             clock=orologio)
    S.riconcilia_interruttori(db)
    assert db.armati == [], "12 armate col tetto 5: niente di nuovo"
    orologio.t += 600
    S.riconcilia_interruttori(db)
    assert sorted(e for e, _b, s in db.stati if s == "stopping") == sorted(morte)
    assert db.armati == [], "le 5 vive riempiono il tetto"
    st = _stats(db)["auto"]
    assert st["armate_feed"] == 5


# ===========================================================================
# C. RIAVVIO DELL'APP: le righe stantie si chiudono, non si riprendono
# ===========================================================================
def test_riavvio_righe_stantie_fermate_e_follow_automatici_chiusi(orologio):
    morte = ["36112100", "36117297", "36118619"]
    controls = [_control(e, bot=b, boot="avvio-di-ieri")
                for e in morte for b in ("tennis_flb", "tennis_scalper")]
    db = _Db([_servizio(status="stopped"), _servizio(bot="tennis_scalper", status="stopped")],
             controls=controls, follows=[_follow(e) for e in morte],
             feed_ev=["1"], now_status={e: "SUSPENDED" for e in morte}, clock=orologio)
    fermate = S.ferma_bot_al_nuovo_avvio(boot_id="avvio-di-oggi", db=db)
    assert len(fermate) == 6
    assert {r["status"] for r in db.controls} == {"stopped"}
    S.riconcilia_interruttori(db)
    assert sorted(e for e, s in db.follow_status if s == "CLOSED") == sorted(morte)
    assert db.armati == []


def test_riavvio_bot_riacceso_non_riprende_le_partite_di_ieri(orologio):
    morte = ["36112100", "36118619"]
    db = _Db([_servizio()],
             controls=[_control(e, boot="avvio-di-ieri") for e in morte],
             follows=[_follow(e) for e in morte],
             feed_ev=["1"], now_status={e: "SUSPENDED" for e in morte}, clock=orologio)
    S.ferma_bot_al_nuovo_avvio(boot_id="avvio-di-oggi", db=db)
    S.riconcilia_interruttori(db)
    assert [r["event_id"] for r in db.armati] == ["1"]
    assert sorted(e for e, s in db.follow_status if s == "CLOSED") == sorted(morte)
