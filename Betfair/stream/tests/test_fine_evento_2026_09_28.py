# -*- coding: utf-8 -*-
"""CANTIERE A "FINE EVENTO" (28/09/2026) - calcio e scalper.

Ordine dell'utente (testuale): "le partite TERMINATE sia calcio che tennis non
devono piu' essere seguite ovviamente, cercate il modo di farlo! Solitamente
quando i mercati per quella partita sono tutti chiusi l'evento e' terminato".

Regola (documentazione Betfair): MarketStatus CLOSED = "The market has been
settled and is no longer available for betting"; listMarketCatalogue "does not
return markets that are CLOSED". Cosa certifica:
  * RUNNER, a caldo (flumine VERO, messaggi ``mcm`` come quelli di Betfair):
    MATCH_ODDS chiuso -> follow CLOSED, ``live_now`` CLOSED, i mercati CHIUSI
    della partita escono dal tetto dell'auto-follow (quelli ancora aperti no);
  * RUNNER, catalogo: partita iniziata e catalogo vuoto = finita SUBITO (prima
    3 ore dopo il via); partita futura senza mercati = resta in attesa;
  * RUNNER, ricostruzione: i mercati delle partite finite non si
    risottoscrivono;
  * RUNNER, uscita ordinata: finite CLOSED, vive PENDING (prima tutte CLOSED);
  * DB: ``live_now`` orfane (follow non attivo) chiuse all'avvio, quelle dei
    follow attivi no; la chiusura e' un UPDATE (punteggio conservato);
  * AUTO-FOLLOW: dopo una ricostruzione i mercati automatici non vengono
    dichiarati "mai arrivati" (prima: partite vive buttate fuori); all'uscita
    le sue righe si chiudono (R-28-3), non quelle di altri;
  * SCALPER: la sessione riconosce la partita finita (MATCH_ODDS CLOSED) e
    chiude (prima: fino a KO+130' o per sempre senza KO).

Finti con le chiavi vere: righe ``live_follow``/``live_now`` con le colonne
della migrazione ``live_stream.sql``; client supabase con la catena di
PostgREST (``table/select/or_/in_/eq/update/upsert/execute``). Nessuna rete,
nessun DB, nessun ordine.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import betfairlightweight
import pytest
from betfairlightweight.filters import streaming_market_data_filter, streaming_market_filter
from flumine import Flumine
from flumine.events.events import CloseMarketEvent, MarketBookEvent


from Betfair.stream import auto_follow as AF
from Betfair.stream import db as DB
from Betfair.stream import runner as R
from Betfair.stream.recorder import MarketRecorderStrategy
from Betfair.stream.scalper import scalper_session as SS

EV = "35800001"
EV2 = "35800002"
MO, CS, TQ, MO2 = "1.301", "1.302", "1.303", "1.401"


# ===========================================================================
# banco: flumine VERO + recorder VERO del runner, messaggi mcm di Betfair
# ===========================================================================
def _md(mid_type: str, status: str, inplay: bool, ev: str) -> Dict[str, Any]:
    return {"bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
            "marketBaseRate": 5.0, "eventId": ev, "eventTypeId": "1",
            "numberOfWinners": 1, "bettingType": "ODDS", "marketType": mid_type,
            "marketTime": "2026-09-28T13:00:00.000Z",
            "suspendTime": "2026-09-28T13:00:00.000Z", "bspReconciled": False,
            "complete": True, "inPlay": inplay, "crossMatching": True,
            "runnersVoidable": False, "numberOfActiveRunners": 2, "betDelay": 5,
            "status": status,
            "runners": ([{"status": "WINNER", "sortPriority": 1, "id": 11},
                         {"status": "LOSER", "sortPriority": 2, "id": 22}]
                        if status == "CLOSED" else
                        [{"status": "ACTIVE", "sortPriority": 1, "id": 11},
                         {"status": "ACTIVE", "sortPriority": 2, "id": 22}]),
            "regulators": ["MR_INT"], "countryCode": "IT", "discountAllowed": True,
            "timezone": "GMT", "openDate": "2026-09-28T13:00:00.000Z", "version": 1}


_TIPI = {MO: "MATCH_ODDS", CS: "CORRECT_SCORE", TQ: "TO_QUALIFY", MO2: "MATCH_ODDS"}
_EVENTO = {MO: EV, CS: EV, TQ: EV, MO2: EV2}


class _Banco:
    """Framework paper, recorder e sessione come li costruisce ``setup_and_run``."""

    def __init__(self) -> None:
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        client, _on = R.build_order_client(api, "PAPER")
        self.fw = Flumine(client=client)
        self.session = R.LiveSession()
        for mid, ev in _EVENTO.items():
            self.session.market_to_event[mid] = ev
            self.session.market_type_by_id[mid] = _TIPI[mid]
            self.session.event_markets.setdefault(ev, set()).add(mid)
            self.session.cataloged_events.add(ev)
        self.rec = MarketRecorderStrategy(
            market_filter=streaming_market_filter(market_ids=sorted(_EVENTO)),
            market_data_filter=streaming_market_data_filter(fields=["EX_BEST_OFFERS"]),
            context={"data_dir": "", "market_to_event": self.session.market_to_event,
                     "market_type_by_id": self.session.market_type_by_id,
                     "event_markets": self.session.event_markets, "depth": 3,
                     "record_events": lambda: set()})
        self.fw.add_strategy(self.rec)
        self.session.recorder = self.rec
        self.stream = self.rec.streams[0]
        self.stream._listener.register_stream(self.stream.stream_id, "marketSubscription")
        self.pt = 1_790_000_000_000

    def arriva(self, stati: Dict[str, str], img: bool = False) -> None:
        self.pt += 1000
        mc = []
        for mid, st in stati.items():
            m: Dict[str, Any] = {"id": mid, "marketDefinition": _md(
                _TIPI[mid], st, True, _EVENTO[mid])}
            if img:
                m["img"] = True
                m["rc"] = [{"id": 11, "batb": [[0, 2.0, 10]], "batl": [[0, 2.02, 10]]}]
            mc.append(m)
        msg: Dict[str, Any] = {"op": "mcm", "id": self.stream.stream_id,
                               "clk": "C%d" % self.pt, "pt": self.pt, "mc": mc}
        if img:
            msg["initialClk"] = "I"
            msg["ct"] = "SUB_IMAGE"
        self.stream._listener.on_data(json.dumps(msg))
        books = self.stream._output_queue.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))
        while not self.fw.handler_queue.empty():
            e = self.fw.handler_queue.get_nowait()
            if isinstance(e, CloseMarketEvent):
                self.fw._process_close_market(e)


class _SottoscrittoreFinto:
    """Stessa firma di ``auto_follow.SottoscrittoreStream.applica``."""

    def __init__(self) -> None:
        self.chiamate: List[List[str]] = []

    def applica(self, framework: Any, market_ids: List[str]) -> int:
        if not market_ids:
            raise ValueError("sottoscrizione vuota rifiutata")
        self.chiamate.append(list(market_ids))
        return len(self.chiamate)


@pytest.fixture
def db_finto(monkeypatch):
    """Le scritture del runner sul DB, registrate (firme di ``db``)."""
    reg: Dict[str, Any] = {"status": [], "now": [], "upload": [], "alert": [],
                           "soldi": None, "soldi_letti": []}
    monkeypatch.setattr(R.db, "set_follow_status",
                        lambda ev, st, detail=None: reg["status"].append((ev, st)))
    monkeypatch.setattr(R.db, "get_follow_record", lambda ev: False)
    monkeypatch.setattr(R.db, "chiudi_live_now", lambda ev: reg["now"].append(ev) or None)
    monkeypatch.setattr(R.uploader, "upload_event",
                        lambda ev: reg["upload"].append(ev) or {"event_id": ev})
    monkeypatch.setattr(R, "FINALIZE_SPACING_SEC", 0.0)
    # guardia SOLDI DENTRO: di serie nessun denaro (i test che lo vogliono lo mettono)
    monkeypatch.setattr(R.db, "mercati_evento", lambda ev: [MO, CS])

    def _soldi(ev, mercati=None):
        reg["soldi_letti"].append(ev)
        if isinstance(reg["soldi"], Exception):
            raise reg["soldi"]
        return reg["soldi"]
    monkeypatch.setattr(R.db, "soldi_sull_evento", _soldi)
    monkeypatch.setattr(R.db, "insert_alert",
                        lambda lv, code, msg, ev=None: reg["alert"].append((lv, code, ev)))
    return reg


def _scorri(s: Any, ev: str, secondi: float) -> None:
    """Fa passare ``secondi`` per la memoria di fine partita dell'evento (gli
    orari sono monotonic: si arretrano quelli annotati)."""
    st = R._stato_fine(s)
    for k in ("vuoto_dal", "trattenute"):
        if ev in st[k]:
            st[k][ev] -= secondi


@pytest.fixture
def auto_follow(monkeypatch):
    auto = AF.AutoFollow(piano=AF.PianoFollow(180), sottoscrittore=_SottoscrittoreFinto(),
                         min_intervallo_s=0.0)
    monkeypatch.setitem(R._MOTORE, "auto", auto)
    return auto


# ===========================================================================
# 1. RUNNER a caldo: MATCH_ODDS CLOSED -> follow, live_now e tetto
# ===========================================================================
def test_match_odds_chiuso_follow_e_live_now_closed_e_mercati_chiusi_fuori_dal_tetto(
        db_finto, auto_follow):
    b = _Banco()
    auto_follow.imposta_manuali(R.mercati_manuali_vivi(b.session))
    assert auto_follow.piano.mercati_manuali() == {MO, CS, TQ, MO2}
    b.arriva({MO: "OPEN", CS: "OPEN", TQ: "OPEN", MO2: "OPEN"}, img=True)
    b.arriva({MO: "SUSPENDED"})
    R.finalize_worker({}, b.fw, b.session)
    assert db_finto["status"] == [], "SOSPESO non e' finito (gol, VAR)"
    b.arriva({MO: "CLOSED", CS: "CLOSED"})
    R.finalize_worker({}, b.fw, b.session)
    assert (EV, "CLOSED") in db_finto["status"]
    assert db_finto["now"] == [EV], "live_now della finita a CLOSED (48 righe del 26/09)"
    # i mercati CHIUSI escono dal tetto; "To Qualify" (supplementari) resta
    assert auto_follow.piano.mercati_manuali() == {TQ, MO2}
    b.arriva({TQ: "CLOSED"})
    R.finalize_worker({}, b.fw, b.session)
    assert auto_follow.piano.mercati_manuali() == {MO2}
    assert EV2 not in b.session.finished_events
    # la risottoscrizione a caldo toglie davvero i mercati dallo stream
    auto_follow.aggancia(b.fw, [MO, CS, TQ, MO2])
    auto_follow.giro()
    assert auto_follow.sottoscrittore.chiamate[-1] == [MO2]


class _PollerFinto:
    """``ScorePoller``: ``primary`` e ``poll(event_id)`` (None = nessun dato)."""

    primary = None

    def poll(self, event_id: str) -> None:  # noqa: ARG002
        return None


def test_score_worker_mercati_chiusi_non_in_gioco_e_mai_sopra_la_finalizzata(monkeypatch):
    b = _Banco()
    scritte: List[tuple] = []
    monkeypatch.setattr(R.db, "update_live_now",
                        lambda ev, state, inplay=False, minute=None, score_home=None,
                        score_away=None, status="OPEN", score_source=None:
                        scritte.append((ev, inplay, status)))
    monkeypatch.setattr(R, "SIGNALS_ENABLED", False)
    b.session.markets_by_event[EV] = [{"market_id": m} for m in (MO, CS)]
    b.session.pollers[EV] = _PollerFinto()
    b.arriva({MO: "OPEN", CS: "OPEN"}, img=True)
    R.score_worker({}, b.fw, b.session)
    assert scritte[-1][:2] == (EV, True)
    b.arriva({MO: "CLOSED", CS: "CLOSED"})
    R.score_worker({}, b.fw, b.session)
    assert scritte[-1][:2] == (EV, False), \
        "l'ultimo book porta inplay=true: un mercato chiuso non e' in gioco"
    n = len(scritte)
    # la finalize_worker (altro thread) finalizza MENTRE questo giro legge il
    # punteggio: il giro non deve riscrivere sopra la riga CLOSED
    poller = _PollerFinto()
    poller.poll = lambda ev: b.session.finished_events.add(ev)  # type: ignore[method-assign]
    b.session.pollers[EV] = poller
    R.score_worker({}, b.fw, b.session)
    assert len(scritte) == n


def test_ricostruzione_non_risottoscrive_le_partite_finite():
    s = R.LiveSession()
    for mid, ev in _EVENTO.items():
        s.market_to_event[mid] = ev
    s.finished_events.add(EV)
    assert R.mercati_manuali_da_sottoscrivere(s) == [MO2]
    s.finished_events.clear()
    assert R.mercati_manuali_da_sottoscrivere(s) == sorted(_EVENTO)


# ===========================================================================
# 2. RUNNER, catalogo: partita iniziata e senza mercati = finita subito
# ===========================================================================
class _RestFinto:
    """``BetfairClient.betting_rpc``: il ``result`` di listMarketCatalogue."""

    def __init__(self, risultato: List[Dict[str, Any]]) -> None:
        self.risultato = risultato
        self.chiamate: List[tuple] = []

    def betting_rpc(self, method: str, params: Dict[str, Any], **_kw: Any) -> Any:
        self.chiamate.append((method, params))
        return self.risultato


def _follow(ev: str, open_date: Optional[str]) -> Dict[str, Any]:
    """Riga di ``list_pending_follows`` (colonne ``_FOLLOW_COLS``)."""
    return {"event_id": ev, "status": "STREAMING", "record": False,
            "open_date": open_date, "fixture_id": None}


def _iso(delta_min: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_min)).isoformat()


def test_catalogo_vuoto_a_partita_iniziata_finita_alla_seconda_lettura(db_finto):
    """Guardia di CONFERMA: mai alla prima lettura vuota; alla seconda, fatta
    almeno FINE_CONFERMA_S dopo, la partita e' finita (prima: 3 ore)."""
    s = R.LiveSession()
    rest = _RestFinto([])
    f = _follow(EV, _iso(-20))
    R._catalog_events(rest, s, [f])
    assert db_finto["status"] == [] and EV not in s.finished_events, \
        "alla PRIMA lettura vuota non si ritira niente"
    R._catalog_events(rest, s, [f])
    assert len(rest.chiamate) == 1, "prima di FINE_CONFERMA_S non si rilegge"
    assert R.FINE_CONFERMA_S >= 60
    _scorri(s, EV, R.FINE_CONFERMA_S + 1)
    R._catalog_events(rest, s, [f])
    assert len(rest.chiamate) == 2
    assert (EV, "CLOSED") in db_finto["status"]
    assert EV in s.finished_events and db_finto["now"] == [EV]
    assert rest.chiamate[0][0] == "SportsAPING/v1.0/listMarketCatalogue"
    assert R._stato_fine(s) == {"vuoto_dal": {}, "trattenute": {}}


def test_catalogo_di_nuovo_pieno_annulla_la_conferma(db_finto):
    s = R.LiveSession()
    f = _follow(EV, _iso(-20))
    R._catalog_events(_RestFinto([]), s, [f])
    assert EV in R._stato_fine(s)["vuoto_dal"]
    R._ricontrolla_fine(_RestFinto([{"marketId": MO, "description": {"marketType": "MATCH_ODDS"},
                                     "marketName": "Match Odds", "runners": []}]), s, [f])
    assert EV in R._stato_fine(s)["vuoto_dal"], "sotto la soglia non si rilegge"
    _scorri(s, EV, R.FINE_CONFERMA_S + 1)
    R._ricontrolla_fine(_RestFinto([{"marketId": MO, "description": {"marketType": "MATCH_ODDS"},
                                     "marketName": "Match Odds", "runners": []}]), s, [f])
    assert R._stato_fine(s)["vuoto_dal"] == {} and db_finto["status"] == []


def test_in_conferma_niente_ricostruzioni_la_rilegge_il_sub_worker(db_finto):
    """Durante la conferma il sub-worker NON conta la partita come nuova
    (niente ricostruzione dello stream a ogni giro): la rilegge lui al momento."""
    s = R.LiveSession()
    f = _follow(EV, _iso(-20))
    R._catalog_events(_RestFinto([]), s, [f])
    assert R._nuovi_follow_manuali([f], s, None) == []
    rest = _RestFinto([])
    R._ricontrolla_fine(rest, s, [f])
    assert rest.chiamate == [], "prima del momento nessuna lettura"
    _scorri(s, EV, R.FINE_CONFERMA_S + 1)
    R._ricontrolla_fine(rest, s, [f])
    assert len(rest.chiamate) == 1 and EV in s.finished_events


def test_soldi_dentro_la_partita_non_si_ritira(db_finto):
    """Guardia SOLDI DENTRO: catalogo vuoto confermato ma posizione aperta ->
    resta seguita, alert CRITICAL UNA volta, ricontrollo periodico; a posizione
    regolata la partita si ritira."""
    s = R.LiveSession()
    f = _follow(EV, _iso(-20))
    db_finto["soldi"] = "1 posizioni aperte non regolate sull'evento (live)"
    rest = _RestFinto([])
    R._catalog_events(rest, s, [f])
    _scorri(s, EV, R.FINE_CONFERMA_S + 1)
    R._catalog_events(rest, s, [f])
    assert db_finto["status"] == [] and EV not in s.finished_events
    assert db_finto["alert"] == [("CRITICAL", "FINE_PARTITA_CON_SOLDI", EV)]
    assert R._nuovi_follow_manuali([f], s, None) == [], "niente ricostruzioni in loop"
    _scorri(s, EV, R.FINE_RIVERIFICA_SOLDI_S + 1)
    R._ricontrolla_fine(rest, s, [f])
    assert len(db_finto["alert"]) == 1, "l'alert non si ripete a ogni controllo"
    assert EV not in s.finished_events
    db_finto["soldi"] = None                 # posizione regolata
    R._ricontrolla_fine(rest, s, [f])
    assert EV not in s.finished_events, "prima del ricontrollo successivo nulla"
    _scorri(s, EV, R.FINE_RIVERIFICA_SOLDI_S + 1)
    R._ricontrolla_fine(rest, s, [f])
    assert (EV, "CLOSED") in db_finto["status"] and EV in s.finished_events


def test_soldi_non_verificabili_valgono_soldi_dentro(db_finto):
    s = R.LiveSession()
    db_finto["soldi"] = RuntimeError("DB KO")
    assert R._valuta_catalogo_vuoto(s, EV, 1000.0) == "in_conferma"
    assert R._valuta_catalogo_vuoto(s, EV, 1000.0 + R.FINE_CONFERMA_S) == "trattenuta"
    assert db_finto["status"] == []


def test_comando_in_volo_nel_motore_vale_soldi_dentro(db_finto, monkeypatch):
    s = R.LiveSession()
    motore = SimpleNamespace(_in_aggancio={"r1": {"attore": "safe", "ref": "r1",
                                                  "market_id": CS, "piano": {}}})
    monkeypatch.setitem(R._MOTORE, "motore", motore)
    assert R._soldi_sull_evento(s, EV) == "1 comandi in volo nel motore sull'evento"
    motore._in_aggancio["r1"]["market_id"] = "1.999"
    assert R._soldi_sull_evento(s, EV) is None


def test_catalogo_vuoto_a_partita_futura_resta_in_attesa(db_finto):
    s = R.LiveSession()
    R._catalog_events(_RestFinto([]), s, [_follow(EV, _iso(+60)), _follow(EV2, None)])
    assert db_finto["status"] == [] and not s.finished_events


def test_finito_senza_mercati_bordi():
    assert R._finito_senza_mercati({"open_date": _iso(-1)}) is True
    assert R._finito_senza_mercati({"open_date": _iso(+1)}) is False
    assert R._finito_senza_mercati({"open_date": None}) is False
    assert R._finito_senza_mercati({"open_date": "illeggibile"}) is False
    assert R._finito_senza_mercati({"open_date": "2026-09-28T10:00:00Z"}) is True


# ===========================================================================
# 3. RUNNER, uscita ordinata: finite CLOSED, vive PENDING
# ===========================================================================
def test_uscita_ordinata_chiude_le_finite_e_rimette_in_attesa_le_vive(db_finto):
    b = _Banco()
    b.arriva({MO: "OPEN", CS: "OPEN", TQ: "OPEN", MO2: "OPEN"}, img=True)
    b.arriva({MO: "CLOSED"})        # finita, NON ancora drenata dal finalize_worker
    esito = R.chiudi_alla_uscita(b.session)
    assert esito == {"finalizzati": [EV], "in_attesa": [EV2]}
    assert (EV, "CLOSED") in db_finto["status"]
    assert (EV2, "PENDING") in db_finto["status"]
    assert (EV2, "CLOSED") not in db_finto["status"], \
        "IL REPERTO: il finally chiudeva anche le partite vive dell'utente"
    assert db_finto["now"] == [EV] and db_finto["upload"] == []


def test_uscita_ordinata_non_tocca_le_gia_finite(db_finto):
    s = R.LiveSession()
    s.cataloged_events.update({EV, EV2})
    s.finished_events.add(EV)
    assert R.chiudi_alla_uscita(s) == {"finalizzati": [], "in_attesa": [EV2]}
    assert db_finto["status"] == [(EV2, "PENDING")]


def test_uscita_ordinata_rimette_in_attesa_le_partite_in_conferma(db_finto):
    """Una partita col catalogo vuoto in conferma (o trattenuta per soldi) non
    e' catalogata ma la sua riga puo' essere STREAMING da un processo prima:
    all'uscita torna PENDING, mai STREAMING senza chi la segue."""
    s = R.LiveSession()
    R._stato_fine(s)["vuoto_dal"]["E-conf"] = 1.0
    R._stato_fine(s)["trattenute"]["E-soldi"] = 1.0
    assert R.chiudi_alla_uscita(s)["in_attesa"] == ["E-conf", "E-soldi"]
    assert db_finto["status"] == [("E-conf", "PENDING"), ("E-soldi", "PENDING")]


# ===========================================================================
# 4. DB: live_now chiusa con UPDATE, orfane chiuse all'avvio
# ===========================================================================
class _SbFinto:
    """Catena PostgREST di supabase-py; le tabelle sono liste di righe vere."""

    def __init__(self, tabelle: Dict[str, List[Dict[str, Any]]]) -> None:
        self.tabelle = tabelle
        self.scritture: List[tuple] = []

    def table(self, nome: str) -> "_Q":
        return _Q(self, nome)


class _Q:
    def __init__(self, sb: _SbFinto, nome: str) -> None:
        self.sb, self.nome = sb, nome
        self.filtri: List[Any] = []
        self.op: Optional[tuple] = None

    def select(self, _s: str) -> "_Q":
        self.op = ("select",)
        return self

    def update(self, campi: Dict[str, Any]) -> "_Q":
        self.op = ("update", campi)
        return self

    def upsert(self, riga: Dict[str, Any], **kw: Any) -> "_Q":
        self.op = ("upsert", riga, kw)
        return self

    def eq(self, k: str, v: Any) -> "_Q":
        self.filtri.append(lambda r, k=k, v=v: str(r.get(k)) == str(v))
        return self

    def in_(self, k: str, vs: List[Any]) -> "_Q":
        self.filtri.append(lambda r, k=k, vs=vs: str(r.get(k)) in {str(x) for x in vs})
        return self

    def or_(self, expr: str) -> "_Q":
        assert expr == "inplay.eq.true,status.neq.CLOSED"
        self.filtri.append(lambda r: r.get("inplay") is True or r.get("status") != "CLOSED")
        return self

    def execute(self) -> Any:
        righe = [r for r in self.sb.tabelle.get(self.nome, [])
                 if all(f(r) for f in self.filtri)]
        if self.op and self.op[0] == "update":
            for r in righe:
                r.update(self.op[1])
            self.sb.scritture.append((self.nome, "update", sorted(r["event_id"] for r in righe)))
        elif self.op and self.op[0] == "upsert":
            # PostgREST: con ignore_duplicates una riga gia' presente non torna
            riga, kw = self.op[1], self.op[2]
            self.sb.scritture.append((self.nome, "upsert", riga["event_id"]))
            tab = self.sb.tabelle.setdefault(self.nome, [])
            if any(r["event_id"] == riga["event_id"] for r in tab):
                if kw.get("ignore_duplicates"):
                    return SimpleNamespace(data=[])
                tab[:] = [r for r in tab if r["event_id"] != riga["event_id"]]
            tab.append(dict(riga))
            return SimpleNamespace(data=[dict(riga)])
        return SimpleNamespace(data=[dict(r) for r in righe])


def _now_row(ev: str, inplay: bool, status: str) -> Dict[str, Any]:
    """Riga di ``live_now`` (colonne di live_stream.sql)."""
    return {"event_id": ev, "inplay": inplay, "minute": 93, "score_home": 2,
            "score_away": 1, "status": status, "score_source": "betfair",
            "state": {"markets": []}, "updated_at": "2026-06-26T20:00:00+00:00"}


def test_chiudi_live_now_e_un_update_che_conserva_il_punteggio(monkeypatch):
    sb = _SbFinto({"live_now": [_now_row(EV, True, "SUSPENDED")]})
    pubblicati: List[tuple] = []
    monkeypatch.setattr(DB, "get_supabase_client", lambda: sb)
    import Betfair.stream.local_channel as LC
    monkeypatch.setattr(LC, "publish", lambda t, d: pubblicati.append((t, d)))
    riga = DB.chiudi_live_now(EV)
    assert riga["inplay"] is False and riga["status"] == "CLOSED"
    assert riga["score_home"] == 2 and riga["minute"] == 93, "risultato conservato"
    assert sb.scritture == [("live_now", "update", [EV])], "mai un upsert"
    assert pubblicati and pubblicati[0][0] == "now" and pubblicati[0][1]["status"] == "CLOSED"
    assert DB.chiudi_live_now("mai-scritta") is None


def test_live_now_orfane_chiuse_all_avvio_solo_se_il_follow_e_terminale(monkeypatch):
    now = [_now_row("A", True, "OPEN"), _now_row("B", True, "SUSPENDED"),
           _now_row("C", False, "SUSPENDED"), _now_row("D", False, "CLOSED"),
           _now_row("E", True, "OPEN"), _now_row("F", True, "OPEN"),
           _now_row("Z", True, "OPEN")]
    follow = [{"event_id": "A", "status": "CLOSED"}, {"event_id": "B", "status": "STREAMING"},
              {"event_id": "C", "status": "UPLOADED"}, {"event_id": "D", "status": "CLOSED"},
              {"event_id": "E", "status": "PENDING"}, {"event_id": "F", "status": "ERROR"}]
    # "Z": nessuna riga di follow LETTA (in produzione impossibile: FK
    # live_now -> live_follow; qui = lettura parziale). Non si tocca.
    sb = _SbFinto({"live_now": now, "live_follow": follow})
    monkeypatch.setattr(DB, "get_supabase_client", lambda: sb)
    assert DB.chiudi_live_now_orfani() == 3
    assert sb.scritture == [("live_now", "update", ["A", "C", "F"])]
    stato = {r["event_id"]: (r["inplay"], r["status"]) for r in now}
    assert stato["A"] == (False, "CLOSED") and stato["C"] == (False, "CLOSED")
    assert stato["B"] == (True, "SUSPENDED") and stato["E"] == (True, "OPEN"), \
        "i follow attivi li segue (o li finalizza) il runner"
    assert stato["Z"] == (True, "OPEN"), "senza follow terminale letto non si tocca"


# ===========================================================================
# 4b. DB: la guardia SOLDI DENTRO sulle tabelle vere dello specchio
# ===========================================================================
def _ordine(stato: str, mode: str = "live") -> Dict[str, Any]:
    """Riga di ``betfair_live_orders`` (chiavi della migrazione)."""
    return {"event_id": EV, "mode": mode, "market_id": MO, "status": stato,
            "size_remaining": 2.0, "client_order_ref": "awlq1"}


def _posizione(win: float, lose: float, mode: str = "paper", ub: float = 0.0) -> Dict[str, Any]:
    """Riga di ``betfair_live_positions`` (chiavi della migrazione)."""
    return {"event_id": EV, "mode": mode, "market_id": MO, "selection_id": 11,
            "handicap": 0, "matched_if_win": win, "matched_if_lose": lose,
            "worst_if_win": win, "worst_if_lose": lose, "selection_exposure": 0,
            "unmatched_back_exposure": ub, "unmatched_lay_exposure": 0.0,
            "net_position": 0}


def _db_soldi(monkeypatch, **tab: List[Dict[str, Any]]) -> _SbFinto:
    base = {"betfair_live_orders": [], "betfair_live_positions": [],
            "betfair_live_settled": [], "betfair_live_order_requests": [],
            "live_markets": [{"event_id": EV, "market_id": MO}]}
    base.update(tab)
    sb = _SbFinto(base)
    monkeypatch.setattr(DB, "get_supabase_client", lambda: sb)
    return sb


def test_soldi_sull_evento_fonti_vere(monkeypatch):
    _db_soldi(monkeypatch)
    assert DB.soldi_sull_evento(EV) is None
    _db_soldi(monkeypatch, betfair_live_orders=[_ordine("EXECUTABLE")])
    assert DB.soldi_sull_evento(EV) == "1 ordini vivi sull'evento (live)"
    _db_soldi(monkeypatch, betfair_live_orders=[_ordine("EXECUTION_COMPLETE")])
    assert DB.soldi_sull_evento(EV) is None, "ordine eseguito: non e' vivo"
    _db_soldi(monkeypatch, betfair_live_positions=[_posizione(5.0, -3.0)])
    assert DB.soldi_sull_evento(EV) == "1 posizioni aperte non regolate sull'evento (paper)"
    _db_soldi(monkeypatch, betfair_live_positions=[_posizione(1.2, 1.2)])
    assert DB.soldi_sull_evento(EV) is None, "green-up: niente in gioco"
    _db_soldi(monkeypatch, betfair_live_positions=[_posizione(0, 0, ub=2.0)])
    assert DB.soldi_sull_evento(EV) is not None, "esposizione non abbinata"
    _db_soldi(monkeypatch, betfair_live_positions=[_posizione(5.0, -3.0)],
              betfair_live_settled=[{"mode": "paper", "market_id": MO, "event_id": EV}])
    assert DB.soldi_sull_evento(EV) is None, "mercato regolato nella stessa modalita'"
    _db_soldi(monkeypatch, betfair_live_positions=[_posizione(5.0, -3.0)],
              betfair_live_settled=[{"mode": "live", "market_id": MO, "event_id": EV}])
    assert DB.soldi_sull_evento(EV) is not None, "regolato in live NON regola il paper"
    _db_soldi(monkeypatch, betfair_live_order_requests=[
        {"id": 7, "market_id": MO, "status": "pending"}])
    assert DB.soldi_sull_evento(EV) == "1 comandi in coda sull'evento"
    _db_soldi(monkeypatch, betfair_live_order_requests=[
        {"id": 7, "market_id": MO, "status": "done"}])
    assert DB.soldi_sull_evento(EV) is None


# ===========================================================================
# 4c. RUNNER: recorder illeggibile = nessun mercato rilasciato
# ===========================================================================
def test_recorder_illeggibile_non_rilascia_niente():
    s = R.LiveSession()
    s.event_markets = {EV: {MO, CS}, EV2: {MO2}}
    s.finished_events.add(EV)

    class _RecRotto:
        def mercati_chiusi(self, event_id: str) -> set:
            raise RuntimeError("stato interno illeggibile")

    s.recorder = _RecRotto()
    assert R.mercati_manuali_vivi(s) == {EV: {MO, CS}, EV2: {MO2}}
    s.recorder = SimpleNamespace(mercati_chiusi=lambda ev: {MO})
    assert R.mercati_manuali_vivi(s) == {EV: {CS}, EV2: {MO2}}
    s.recorder = None
    assert R.mercati_manuali_vivi(s) == {EV: {MO, CS}, EV2: {MO2}}


# ===========================================================================
# 4d. ARRESTO ORDINATO dell'app (file d'arresto)
# ===========================================================================
def test_arresto_ordinato_file_e_worker(monkeypatch, tmp_path):
    from Betfair.stream import arresto_ordinato as AO
    monkeypatch.setenv("APP_ARRESTO_DIR", str(tmp_path))
    assert AO.richiesto() is False
    fermati: List[Any] = []
    monkeypatch.setattr(R, "_stop_framework", lambda fw: fermati.append(fw))
    s = R.LiveSession()
    s.planned_restart = True
    R.arresto_worker({}, "FW", s)
    assert fermati == [] and not s.shutdown_requested.is_set()
    AO.richiedi()
    assert AO.richiesto() is True
    R.arresto_worker({}, "FW", s)
    assert fermati == ["FW"] and s.shutdown_requested.is_set()
    assert s.planned_restart is False, "exit 0: il watchdog NON rilancia"
    R.arresto_worker({}, "FW", s)
    assert fermati == ["FW"], "una volta sola"
    # un file di uno spegnimento PRECEDENTE (piu' vecchio dell'avvio) non conta
    import os as _os
    vecchio = AO.AVVIO_PROCESSO - 3600
    _os.utime(AO.percorso(), (vecchio, vecchio))
    assert AO.richiesto() is False
    AO.cancella()
    assert not _os.path.exists(AO.percorso())


def test_setup_and_run_controlla_l_arresto_in_cima_al_ciclo():
    import inspect
    src = inspect.getsource(R.setup_and_run)
    i = src.index("while not interrupted:")
    assert "if _AO.richiesto():" in src[i:i + 600]
    assert "function=arresto_worker" in src


# ===========================================================================
# 5. AUTO-FOLLOW: ricostruzione e uscita
# ===========================================================================
def test_dopo_la_ricostruzione_i_mercati_automatici_non_sono_mai_arrivati(monkeypatch):
    """IL REPERTO: mercato sottoscritto a caldo 10 minuti prima; il framework
    si ricostruisce; flumine non ha ancora l'immagine. Prima ``_pulisci`` lo
    dichiarava "mai arrivato" (orario d'invio vecchio) e la partita viva
    usciva, col follow CLOSED."""
    ora = [1000.0]
    chiusi: List[str] = []
    fdb = SimpleNamespace(chiudi=lambda ev: chiusi.append(ev) or True,
                          segui=lambda ev, info: True, colonna_origine=True)
    auto = AF.AutoFollow(piano=AF.PianoFollow(180), sottoscrittore=_SottoscrittoreFinto(),
                         min_intervallo_s=0.0, orologio=lambda: ora[0], follow_db=fdb)
    fw1 = SimpleNamespace(markets=SimpleNamespace(markets={}))
    auto.aggancia(fw1, [])
    assert auto.richiedi("1.900", event_id="E-auto") is None
    auto.giro()                                        # sottoscritto a caldo a t=1000
    fw1.markets.markets["1.900"] = SimpleNamespace(
        market_book=SimpleNamespace(status="OPEN"), closed=False, blotter=[])
    auto._scritti.add("E-auto")
    ora[0] += 600.0                                    # 10 minuti dopo: ricostruzione
    fw2 = SimpleNamespace(markets=SimpleNamespace(markets={}))
    auto.aggancia(fw2, auto.mercati_da_sottoscrivere())
    auto.giro()                                        # immagine non ancora arrivata
    assert "1.900" in auto.piano.mercati(), "partita viva buttata fuori dopo il rebuild"
    assert chiusi == []
    # un mercato della build che non arriva MAI (chiuso da ore) esce comunque
    ora[0] += AF.MAI_ARRIVATO_S + 1
    auto.giro()
    assert "1.900" not in auto.piano.mercati() and chiusi == ["E-auto"]


def test_uscita_ordinata_chiude_solo_le_righe_dell_auto_follow():
    chiusi: List[str] = []
    fdb = SimpleNamespace(chiudi=lambda ev: chiusi.append(ev) or True)
    auto = AF.AutoFollow(piano=AF.PianoFollow(180), sottoscrittore=_SottoscrittoreFinto(),
                         follow_db=fdb)
    auto._scritti.update({"E1", "E2"})
    assert auto.chiudi_righe() == 2
    assert chiusi == ["E1", "E2"] and auto._scritti == set()
    assert AF.AutoFollow(piano=AF.PianoFollow(1)).chiudi_righe() == 0   # senza DB


def test_finally_del_runner_chiude_le_righe_auto_e_non_finalizza_le_vive():
    import inspect
    src = inspect.getsource(R.setup_and_run).split("    finally:")[-1]
    assert "chiudi_alla_uscita(session)" in src
    assert "auto.chiudi_righe()" in src
    assert "_finalize_event(" not in src


# ===========================================================================
# 6. SCALPER: la sessione riconosce la partita finita
# ===========================================================================
def test_scalper_partita_finita_regola_su_flumine_vero():
    """Mercati e book VERI di flumine (``_process_market_books`` e
    ``_process_close_market``), come nella sessione scalper."""
    ids = [MO, CS]
    b = _Banco()
    assert SS.partita_finita(b.fw, MO, ids) is False, "niente arrivato: niente da dire"
    b.arriva({MO: "OPEN", CS: "OPEN"}, img=True)
    assert SS.partita_finita(b.fw, MO, ids) is False
    b.arriva({MO: "SUSPENDED", CS: "SUSPENDED"})
    assert SS.partita_finita(b.fw, MO, ids) is False, "sospeso (gol/VAR) non e' finito"
    b.arriva({MO: "CLOSED"})
    assert b.fw.markets.markets[MO].closed is True
    assert SS.partita_finita(b.fw, MO, ids) is True, "MATCH_ODDS chiuso = finita"
    assert SS.partita_finita(b.fw, None, ids) is False, "CS ancora sospeso"
    b.arriva({CS: "CLOSED"})
    # senza MATCH_ODDS noto: tutti i mercati arrivati e chiusi
    assert SS.partita_finita(b.fw, None, ids) is True
    assert SS.partita_finita(b.fw, None, ids + [TQ]) is False, \
        "un mercato mai arrivato non dice niente"
    assert SS.partita_finita(object(), MO, ids) is False
    # un solo mercato chiuso che NON e' il MATCH_ODDS: non finita
    b2 = _Banco()
    b2.arriva({MO: "OPEN", CS: "OPEN"}, img=True)
    b2.arriva({CS: "CLOSED"})
    assert b2.fw.markets.markets[CS].closed is True
    assert SS.partita_finita(b2.fw, MO, ids) is False


def test_scalper_sessione_usa_la_regola_nel_battito():
    import inspect
    src = inspect.getsource(SS.run_session)
    i = src.index("partita_finita(framework")
    j = src.index("if ko_ts is not None and time.time() > ko_ts + _life_s")
    assert i < j, "la fine partita va controllata a ogni battito, prima della vita"
    blocco = src[i:j]
    assert "_force_flat_all()" in blocco and "clean_break = True" in blocco
