"""09/10/2026 - PROGRAMMA DEL GIORNO (/board): contratto backend
(``AUDIT_2026-10-09/programma_del_giorno/CONTRATTO.md`` par. 1-par. 3).

Cosa certifica:
  * par. 1 righe ``board`` estese: ``score`` calcio (minuto, gol, rossi, intervallo
    dallo stato IPS) e tennis (set, game, punti, battuta) SOLO in gioco e SOLO dal
    feed fresco; ``fixture_id`` dal ``selection_hint``; ``bet_delay``;
    ``updated_ms``; ``back_size``/``lay_size``; ``total_matched`` VERO dalla REST
    anche per le righe del feed (lo stream dello scanner non porta il volume),
    con la stessa REST di sempre: blocchi da 25, al piu' ogni 60 s;
  * par. 2 ``market_types``: calcio senza NESSUN correct score, MATCH_ODDS primo,
    tennis senza esclusioni, chiave ASSENTE se ``listMarketTypes`` non e' mai
    riuscito (non noto, mai una lista vuota inventata);
  * par. 3 ``board_mercato``: richiesta di sola lettura (tipo sconosciuto/escluso/
    MATCH_ODDS/non caricato -> rifiuto col motivo; tetto di 3 tipi; TTL 75 s) e
    push con prezzi dal feed dove copre (blocchi ``ou``) e REST altrove, una
    riga per mercato con l'handicap per selezione (ASIAN_HANDICAP);
  * il canale: ``board_mercato`` su un WebSocket VERO, senza token, mai in coda
    comandi, mai sul canale di un bot;
  * il tabellone parte ANCHE col runner PARCHEGGIATO: ``setup_and_run`` VERO
    (calcio e tennis) fermato al primo sonno del ciclo d'attesa pubblica il push
    ``board`` (prima: tennis senza follow MAI un board);
  * un giro alla volta (worker di flumine e ciclo d'attesa) e cadenza condivisa.

Finti con le chiavi e i tipi del vero: catalogo, book e tipi di mercato sono
oggetti VERI di betfairlightweight costruiti dalle risposte grezze (stesse
chiavi dell'API Betfair); il payload dello scanner ha le chiavi di
``safe_strategy/service.py::build_rows`` (verificate qui sotto sul sorgente),
i suoi campi di punteggio vengono dai parser VERI (``parse_score_dict``,
``parse_tennis_scores``), le quote da ``scanner.price_pair`` e i blocchi a gol
da ``scanner.build_market_block``. Nessuna rete, nessun DB.
"""
from __future__ import annotations

import inspect
import json
import os
import socket
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest
from betfairlightweight.resources import bettingresources as BR

from Betfair.safe_strategy import scanner as SC
from Betfair.stream import board_worker as bw
from Betfair.stream import local_channel as LC
from Betfair.stream.scores import scan_feed as sf
from Betfair.stream.scores.betfair_inplay import parse_score_dict
from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

E1, E2 = "35000001", "35000002"          # calcio: E1 in gioco (feed), E2 pre-partita (REST)
T1 = "35790084"                          # tennis in gioco


# ---------------------------------------------------------------------------
# stato del modulo pulito a ogni test (cache di processo, elenco esplicito)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _stato_pulito(monkeypatch):
    monkeypatch.setattr(bw, "_STATE", {
        "catalogue_ts": 0.0, "markets": [], "rest_ts": 0.0, "rest_rows": {},
        "types_ts": 0.0, "market_types": None, "giro_ts": 0.0, "event_type_id": None})
    # raising=False: la falsificazione gira questi test anche sul codice di prima
    monkeypatch.setattr(bw, "_RICHIESTE", {}, raising=False)
    monkeypatch.setattr(bw, "_MERCATI", {}, raising=False)
    yield


# ---------------------------------------------------------------------------
# risposte grezze dell'API Betfair -> oggetti VERI di betfairlightweight
# ---------------------------------------------------------------------------
def _evento(eid: str, nome: str) -> Dict[str, Any]:
    return {"id": eid, "name": nome, "countryCode": "IT", "timezone": "GMT",
            "openDate": "2026-10-09T18:00:00.000Z"}


def _cat(mid: str, eid: str, nome_ev: str, nome_mercato: str,
         runners: List[Tuple[int, str, float, int]]) -> Dict[str, Any]:
    return {"marketId": mid, "marketName": nome_mercato,
            "marketStartTime": "2026-10-09T18:00:00.000Z", "totalMatched": 0.0,
            "event": _evento(eid, nome_ev),
            "runners": [{"selectionId": s, "runnerName": n, "handicap": h, "sortPriority": o}
                        for s, n, h, o in runners]}


def _book(mid: str, *, inplay: bool, tm: float, bet_delay: int,
          runners: List[Tuple[int, float, Optional[float], Optional[float], float, float]],
          status: str = "OPEN") -> Dict[str, Any]:
    """runners: (selection_id, handicap, back, lay, back_size, lay_size)."""
    return {
        "marketId": mid, "isMarketDataDelayed": False, "status": status,
        "betDelay": bet_delay, "bspReconciled": False, "complete": True, "inplay": inplay,
        "numberOfWinners": 1, "numberOfRunners": len(runners),
        "numberOfActiveRunners": len(runners), "lastMatchTime": "2026-10-09T18:30:00.000Z",
        "totalMatched": tm, "totalAvailable": 1000.0, "crossMatching": True,
        "runnersVoidable": False, "version": 1,
        "runners": [{"selectionId": s, "handicap": h, "status": "ACTIVE",
                     "lastPriceTraded": b, "totalMatched": 1.0,
                     "ex": {"availableToBack": ([{"price": b, "size": bs}] if b else []),
                            "availableToLay": ([{"price": la, "size": ls}] if la else []),
                            "tradedVolume": []}}
                    for s, h, b, la, bs, ls in runners],
    }


_CAT_CALCIO = {
    "MATCH_ODDS": [
        _cat("1.101", E1, "Casa v Ospite", "Match Odds",
             [(11, "Casa", 0.0, 1), (22, "Ospite", 0.0, 2), (58805, "The Draw", 0.0, 3)]),
        _cat("1.102", E2, "Nord v Sud", "Match Odds",
             [(33, "Nord", 0.0, 1), (44, "Sud", 0.0, 2), (58805, "The Draw", 0.0, 3)]),
    ],
    "OVER_UNDER_25": [
        _cat("1.201", E1, "Casa v Ospite", "Over/Under 2.5 Goals",
             [(47972, "Under 2.5 Goals", 0.0, 1), (47973, "Over 2.5 Goals", 0.0, 2)]),
        _cat("1.202", E2, "Nord v Sud", "Over/Under 2.5 Goals",
             [(47972, "Under 2.5 Goals", 0.0, 1), (47973, "Over 2.5 Goals", 0.0, 2)]),
    ],
    "ASIAN_HANDICAP": [
        _cat("1.301", E1, "Casa v Ospite", "Asian Handicap",
             [(11, "Casa", -0.5, 1), (22, "Ospite", 0.5, 2),
              (11, "Casa", -1.0, 3), (22, "Ospite", 1.0, 4)]),
    ],
}
_BOOKS = {
    "1.101": _book("1.101", inplay=True, tm=15234.5, bet_delay=5,
                   runners=[(11, 0.0, 1.5, 1.52, 100.0, 50.0), (22, 0.0, 7.0, 7.4, 9.0, 3.0),
                            (58805, 0.0, 4.0, 4.2, 20.0, 10.0)]),
    "1.102": _book("1.102", inplay=False, tm=288.8, bet_delay=0,
                   runners=[(33, 0.0, 3.05, 3.2, 96.59, 15.0), (44, 0.0, 2.46, 2.56, 5.0, 17.0),
                            (58805, 0.0, 3.4, 3.6, 56.76, 3.0)]),
    "1.201": _book("1.201", inplay=True, tm=5000.0, bet_delay=5,
                   runners=[(47972, 0.0, 1.9, 1.95, 1.0, 1.0), (47973, 0.0, 2.0, 2.1, 1.0, 1.0)]),
    "1.202": _book("1.202", inplay=False, tm=77.0, bet_delay=0,
                   runners=[(47972, 0.0, 2.2, 2.3, 30.0, 12.0), (47973, 0.0, 1.7, 1.8, 8.0, 4.0)]),
    "1.301": _book("1.301", inplay=True, tm=900.0, bet_delay=5,
                   runners=[(11, -0.5, 1.8, 1.85, 40.0, 20.0), (22, 0.5, 2.1, 2.2, 15.0, 6.0),
                            (11, -1.0, 2.4, 2.5, 7.0, 2.0), (22, 1.0, 1.6, 1.65, 11.0, 5.0)]),
}
_TIPI_CALCIO = [("MATCH_ODDS", 2), ("OVER_UNDER_25", 2), ("CORRECT_SCORE", 2),
                ("CORRECT_SCORE2_A", 1), ("HALF_TIME_SCORE", 2), ("FIRST_HALF_CORRECT_SCORE", 1),
                ("ASIAN_HANDICAP", 1), ("BOTH_TEAMS_TO_SCORE", 5)]


class _Betting:
    """``client.betting`` con le firme vere; restituisce oggetti VERI."""

    def __init__(self, cataloghi: Dict[str, List[Dict[str, Any]]],
                 books: Dict[str, Dict[str, Any]], tipi: List[Tuple[str, int]]) -> None:
        self.cataloghi, self.books, self.tipi = cataloghi, books, tipi
        self.chiamate: List[Tuple[str, Any]] = []
        self.tipi_ko = False

    def list_market_catalogue(self, filter=None, market_projection=None, sort=None,
                              max_results=None, **_k):
        codici = (filter or {}).get("marketTypeCodes") or []
        self.chiamate.append(("catalogo", list(codici)))
        out = []
        for c in codici:
            out += [BR.MarketCatalogue(**r) for r in self.cataloghi.get(c, [])]
        return out[:max_results] if max_results else out

    def list_market_types(self, filter=None, **_k):
        self.chiamate.append(("tipi", sorted((filter or {}).get("eventIds") or [])))
        if self.tipi_ko:
            raise RuntimeError("TOO_MUCH_DATA")
        return [BR.MarketTypeResult(marketType=t, marketCount=n) for t, n in self.tipi]

    def list_market_book(self, market_ids=None, price_projection=None, **_k):
        self.chiamate.append(("book", list(market_ids)))
        assert len(market_ids) <= 25, "blocco oltre 25 mercati"
        assert price_projection["priceData"] == ["EX_BEST_OFFERS"]
        return [BR.MarketBook(**self.books[m]) for m in market_ids if m in self.books]


def _api(cataloghi=None, books=None, tipi=None) -> SimpleNamespace:
    return SimpleNamespace(betting=_Betting(cataloghi or _CAT_CALCIO, books or _BOOKS,
                                            tipi if tipi is not None else _TIPI_CALCIO))


# ---------------------------------------------------------------------------
# il feed dello scanner: chiavi di build_rows, valori dai parser veri
# ---------------------------------------------------------------------------
def _pair_vero(book_raw: Dict[str, Any], sid: int) -> Dict[str, Any]:
    """Come ``Scanner._apply_market_book``: ``{**price_pair(ex), selection_id, ltp}``."""
    libro = BR.MarketBook(**book_raw)
    r = next(x for x in libro.runners if x.selection_id == sid)
    return {**SC.price_pair(r.ex), "selection_id": int(sid),
            "ltp": SC.num_or_none(r.last_price_traded)}


def _ips_calcio(stato: str = "SecondHalf", minuto: int = 67) -> Dict[str, Any]:
    return {"eventId": int(E1), "timeElapsed": minuto, "elapsedRegularTime": minuto,
            "matchStatus": stato,
            "score": {"home": {"name": "Casa", "score": "2", "numberOfRedCards": 0,
                               "numberOfYellowCards": 1, "numberOfCorners": 4},
                      "away": {"name": "Ospite", "score": "1", "numberOfRedCards": 1,
                               "numberOfYellowCards": 2, "numberOfCorners": 2}}}


def _payload_calcio(stato_ips: str = "SecondHalf", inplay: bool = True,
                    con_ou: bool = True) -> Dict[str, Any]:
    raw = _ips_calcio(stato_ips)
    snap = parse_score_dict(E1, raw)          # come Scanner (service.py ~1797)
    ou = SC.build_market_block(
        "1.201", "OPEN",
        [{"selection_id": 47972, "name": "Under 2.5 Goals", "runner_status": "ACTIVE",
          "back": 1.91, "lay": 1.93, "back_size": 250.0, "lay_size": 120.0},
         {"selection_id": 47973, "name": "Over 2.5 Goals", "runner_status": "ACTIVE",
          "back": 2.08, "lay": 2.12, "back_size": 80.0, "lay_size": 60.0}],
        inplay, None, market_type="OVER_UNDER_25", line=2.5, bet_delay=5)
    return {
        "event_name": "Casa v Ospite", "home": "Casa", "away": "Ospite",
        "competition": "Serie A", "open_date": "2026-10-09T18:00:00.000Z",
        "inplay": inplay, "mo_market_id": "1.101", "mo_status": "OPEN",
        "odds": {"home": _pair_vero(_BOOKS["1.101"], 11),
                 "away": _pair_vero(_BOOKS["1.101"], 22),
                 "draw": _pair_vero(_BOOKS["1.101"], 58805)},
        "minute": snap.minute, "score_home": snap.score_home, "score_away": snap.score_away,
        "red_home": snap.red_home, "red_away": snap.red_away,
        "pre_ko": None, "cs": None, "ht": None, "media": None,
        "score_raw": SC.strip_volatile_state(raw), "timeline": None,
        # lo STREAM dello scanner non porta il volume: None (service.py ~1440)
        "mo_total_matched": None, "valuta": "EUR", "odds_ts_ms": 1, "odds_pt_ms": 1,
        "bet_delay": 5, "odds_seen_ms": 1,
        **SC.split_opportunity_blocks({"1.201": ou} if con_ou else {}),
        "pressure_index": None,
        "selection_hint": {"fonte": "fixture_predictions.raw_json", "fixture_id": 1234567,
                           "h2h_meetings": 8, "h2h_many_goals": 2,
                           "conceded": {"home": 0.8, "away": 1.6}, "forze": None},
        "fixture_round": "Regular Season - 7",
    }


def _ips_tennis() -> Dict[str, Any]:
    return {"eventId": T1, "status": "InPlay", "matchStatus": "InPlay", "currentSet": 2,
            "currentGame": 6,
            "score": {"home": {"name": "Barrios Vera", "score": "40", "games": 3, "sets": 1,
                               "isServing": False, "serviceBreaks": 0, "gameSequence": ["6"]},
                      "away": {"name": "Simakin", "score": "AD", "games": 2, "sets": 0,
                               "isServing": True, "serviceBreaks": 0, "gameSequence": ["4"]}}}


def _payload_tennis(inplay: bool = True) -> Dict[str, Any]:
    raw = _ips_tennis()
    ts = parse_tennis_scores([raw], T1)       # come Scanner (service.py ~1803)
    return {
        "event_name": "Barrios Vera v Simakin", "p1": "Barrios Vera", "p2": "Simakin",
        "competition": "ATP", "open_date": "2026-10-09T12:00:00.000Z", "inplay": inplay,
        "mo_market_id": "1.401", "mo_status": "OPEN",
        "odds": {"p1": {"back": 1.8, "lay": 1.82, "back_size": 300.0, "lay_size": 90.0,
                        "selection_id": 9633138, "ltp": 1.81},
                 "p2": {"back": 2.2, "lay": 2.24, "back_size": 70.0, "lay_size": 40.0,
                        "selection_id": 35635727, "ltp": 2.22}},
        "sets": {"p1": ts.sets_home, "p2": ts.sets_away},
        "games": {"p1": ts.games_home, "p2": ts.games_away},
        "media": None, "score_raw": SC.strip_volatile_state(raw),
        "mo_total_matched": None, "valuta": "EUR", "odds_ts_ms": 1, "odds_pt_ms": 1,
        "bet_delay": 3, "odds_seen_ms": 1, "pre_ko": None,
    }


def _iso_adesso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feed(monkeypatch, righe: Dict[str, Tuple[str, Dict[str, Any]]]) -> None:
    """La cache VERA del feed (``ScanRowCache``) con la lettura iniettata."""
    rows = [{"event_id": eid, "sport": sport, "updated_at": _iso_adesso(), "payload": p}
            for eid, (sport, p) in righe.items()]
    cache = sf.ScanRowCache(ttl_sec=0.0, fetch=lambda ids: [r for r in rows if r["event_id"] in ids],
                            fetch_status=lambda: {"id": "scanner", "updated_at": _iso_adesso(),
                                                  "payload": {}})
    monkeypatch.setattr(bw, "shared_cache", lambda: cache)


class _Canale(LC.LocalChannel):
    """Canale VERO con il publish registrato e un desktop collegato."""

    def __init__(self, sport: str = "calcio", porta: int = 59981) -> None:
        super().__init__(porta, sport, token="x" * 64)
        self.usciti: List[Tuple[str, Any]] = []
        self.risposte: List[Tuple[Any, bool, Any, Optional[str]]] = []
        self.attivo = True

    def respond(self, req: Any, ok: bool, data: Any = None,  # type: ignore[override]
                error: Optional[str] = None) -> None:
        self.risposte.append((req.msg_id, ok, data, error))

    def is_active(self) -> bool:  # type: ignore[override]
        return self.attivo

    def publish(self, topic: str, payload: Any) -> None:  # type: ignore[override]
        json.dumps({"t": topic, "d": payload})          # serializzabile come il vero
        self.usciti.append((topic, json.loads(json.dumps(payload))))

    def ultimo(self, topic: str) -> Any:
        v = [d for t, d in self.usciti if t == topic]
        return v[-1] if v else None


def _giro(monkeypatch, api, et: str = "1", ch: Optional[_Canale] = None) -> _Canale:
    ch = ch or _Canale("calcio" if et == "1" else "tennis")
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    bw.board_worker({}, None, session=SimpleNamespace(context_api_client=api), event_type_id=et)
    return ch


class _Orologio:
    """``time`` del modulo con ``monotonic`` manovrabile (il resto e' quello vero)."""

    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def monotonic(self) -> float:
        return self.t

    def time(self) -> float:
        return time.time()


# ===========================================================================
# 0. le chiavi lette dal board sono quelle che lo scanner SCRIVE (difetto par. 7.1)
# ===========================================================================
def test_chiavi_lette_sono_quelle_scritte_dallo_scanner():
    from Betfair.safe_strategy import service as SV

    src = inspect.getsource(SV.Scanner.build_rows) if hasattr(SV, "Scanner") else \
        inspect.getsource(SV)
    for k in ("minute", "score_home", "score_away", "red_home", "red_away",
              "mo_total_matched", "bet_delay", "odds", "mo_status", "sets", "games"):
        assert f'"{k}": ev.get("{k}")' in src, k
    assert '"score_raw": ev.get("score_raw")' in src
    assert '"mo_market_id": meta.get("market_id")' in src
    assert '"inplay": inplay' in src
    assert 'payload["selection_hint"] = self.schede.hint(eid)' in src
    assert "split_opportunity_blocks" in src
    # i blocchi a gol e i pair hanno le chiavi lette da board_mercato / righe
    assert {"back_size", "lay_size", "back", "lay"} <= set(SC.price_pair(None))
    blk = SC.build_market_block("1.9", "OPEN", [{"selection_id": 1}], True, None,
                                market_type="OVER_UNDER_25", line=2.5)
    assert {"market_id", "status", "inplay", "total_matched", "selections"} <= set(blk)
    assert set(SC.split_opportunity_blocks({"1.9": blk})) == {"ou", "btts", "ht_result"}


# ===========================================================================
# 1. par. 1 righe board estese
# ===========================================================================
def test_riga_calcio_dal_feed_score_fixture_size_betdelay_e_volume_rest(monkeypatch):
    _feed(monkeypatch, {E1: ("calcio", _payload_calcio())})
    ch = _giro(monkeypatch, _api())
    board = ch.ultimo("board")
    assert board is not None, ch.usciti
    righe = {r["event_id"]: r for r in board["rows"]}
    r1 = righe[E1]
    # dal FEED: prezzi e size come lo scanner li ha scritti
    assert [s["selection_id"] for s in r1["selections"]] == [11, 22, 58805]
    assert r1["selections"][0] == {"selection_id": 11, "name": "Casa", "back": 1.5,
                                   "lay": 1.52, "ltp": 1.5, "back_size": 100.0,
                                   "lay_size": 50.0}
    assert r1["score"] == {"sport": "calcio", "minute": 67, "home": 2, "away": 1,
                           "red_home": 0, "red_away": 1, "ht": False}
    assert r1["fixture_id"] == 1234567 and isinstance(r1["fixture_id"], int)
    assert r1["bet_delay"] == 5
    # il feed dice None (stream senza volume): il VERO dalla REST dello stesso giro
    assert r1["total_matched"] == 15234.5
    assert isinstance(r1["updated_ms"], int) and abs(r1["updated_ms"] - time.time() * 1000) < 5000
    # E2 senza feed: tutto dalla REST, score e fixture NON noti (None, mai 0)
    r2 = righe[E2]
    assert r2["score"] is None and r2["fixture_id"] is None
    assert r2["bet_delay"] == 0 and r2["total_matched"] == 288.8
    assert r2["selections"][0]["back_size"] == 96.59 and r2["selections"][0]["lay_size"] == 15.0
    assert set(r1) == set(r2) == {"event_id", "event_name", "open_date", "market_id", "status",
                                  "inplay", "total_matched", "selections", "bet_delay",
                                  "score", "fixture_id", "updated_ms"}


@pytest.mark.parametrize("stato,atteso", [("FirstHalfEnd", True), ("HalfTime", True),
                                          ("SecondHalf", False), ("KickOff", False),
                                          ("FirstHalf", False), ("", None)])
def test_intervallo_dallo_stato_ips(stato, atteso):
    p = _payload_calcio(stato)
    if not stato:
        p["score_raw"] = {k: v for k, v in p["score_raw"].items() if k != "matchStatus"}
    assert bw.score_calcio(p)["ht"] is atteso
    p["score_raw"] = None
    assert bw.score_calcio(p)["ht"] is None          # stato assente = non noto


def test_score_solo_in_gioco(monkeypatch):
    p = _payload_calcio(inplay=False)
    _feed(monkeypatch, {E1: ("calcio", p)})
    books = dict(_BOOKS)
    books["1.101"] = dict(_BOOKS["1.101"], inplay=False)
    ch = _giro(monkeypatch, _api(books=books))
    r1 = {r["event_id"]: r for r in ch.ultimo("board")["rows"]}[E1]
    assert r1["inplay"] is False and r1["score"] is None
    assert r1["fixture_id"] == 1234567                 # le Statistiche servono anche prima


def test_riga_tennis_set_game_punti_battuta(monkeypatch):
    cat = {"MATCH_ODDS": [_cat("1.401", T1, "Barrios Vera v Simakin", "Match Odds",
                               [(9633138, "Barrios Vera", 0.0, 1),
                                (35635727, "Simakin", 0.0, 2)])]}
    books = {"1.401": _book("1.401", inplay=True, tm=43210.0, bet_delay=3,
                            runners=[(9633138, 0.0, 1.8, 1.82, 1.0, 1.0),
                                     (35635727, 0.0, 2.2, 2.24, 1.0, 1.0)])}
    _feed(monkeypatch, {T1: ("tennis", _payload_tennis())})
    ch = _giro(monkeypatch, _api(cat, books, [("MATCH_ODDS", 1), ("SET_BETTING", 1)]), et="2")
    r = ch.ultimo("board")["rows"][0]
    assert r["score"] == {"sport": "tennis", "sets": {"p1": 1, "p2": 0},
                          "games": {"p1": 3, "p2": 2}, "points": {"p1": "40", "p2": "AD"},
                          "server": "p2"}
    assert r["fixture_id"] is None and r["bet_delay"] == 3 and r["total_matched"] == 43210.0
    assert r["selections"][0]["back_size"] == 300.0


def test_volume_rest_blocchi_da_25_al_piu_ogni_60_s(monkeypatch):
    ore = _Orologio()
    monkeypatch.setattr(bw, "time", ore)
    eventi = [f"3600{i:04d}" for i in range(60)]
    cat = {"MATCH_ODDS": [_cat(f"1.9{i:03d}", e, f"A{i} v B{i}", "Match Odds",
                               [(1, "A", 0.0, 1), (2, "B", 0.0, 2)])
                          for i, e in enumerate(eventi)]}
    books = {f"1.9{i:03d}": _book(f"1.9{i:03d}", inplay=False, tm=float(i), bet_delay=0,
                                  runners=[(1, 0.0, 2.0, 2.1, 5.0, 5.0)]) for i in range(60)}
    _feed(monkeypatch, {})
    api = _api(cat, books, [("MATCH_ODDS", 60)])
    _giro(monkeypatch, api)
    libri = [c for c in api.betting.chiamate if c[0] == "book"]
    assert [len(c[1]) for c in libri] == [25, 25, 10]
    ore.t += 10.0                                       # giro dopo: nessuna REST
    _giro(monkeypatch, api)
    assert len([c for c in api.betting.chiamate if c[0] == "book"]) == 3
    ore.t += 50.5                                       # oltre i 60 s: di nuovo, uguale
    ch = _giro(monkeypatch, api)
    assert len([c for c in api.betting.chiamate if c[0] == "book"]) == 6
    assert {r["total_matched"] for r in ch.ultimo("board")["rows"]} == {float(i) for i in range(60)}


# ===========================================================================
# 2. par. 2 tipi di mercato
# ===========================================================================
def test_market_types_calcio_senza_correct_score_match_odds_primo(monkeypatch):
    _feed(monkeypatch, {})
    api = _api()
    ch = _giro(monkeypatch, api)
    tipi = ch.ultimo("board")["market_types"]
    assert [t["market_type"] for t in tipi] == ["MATCH_ODDS", "BOTH_TEAMS_TO_SCORE",
                                                "OVER_UNDER_25", "ASIAN_HANDICAP"]
    assert all(set(t) == {"market_type", "name", "count"} for t in tipi)
    assert tipi[0] == {"market_type": "MATCH_ODDS", "name": "Esito finale (1X2)", "count": 2}
    assert not [t for t in tipi if "CORRECT_SCORE" in t["market_type"]
                or t["market_type"] == "HALF_TIME_SCORE"]
    # sugli eventi del PROGRAMMA, una sola chiamata; cache 300 s
    assert [c for c in api.betting.chiamate if c[0] == "tipi"] == [("tipi", sorted([E1, E2]))]
    _giro(monkeypatch, api)
    assert len([c for c in api.betting.chiamate if c[0] == "tipi"]) == 1


def test_market_types_tennis_nessuna_esclusione():
    tipi = bw.tipi_da_risultato([BR.MarketTypeResult(marketType=t, marketCount=n) for t, n in
                                 [("SET_BETTING", 4), ("MATCH_ODDS", 1), ("CORRECT_SCORE", 1)]],
                                "2")
    assert [t["market_type"] for t in tipi] == ["MATCH_ODDS", "SET_BETTING", "CORRECT_SCORE"]


def test_market_types_ko_chiave_assente_mai_lista_vuota(monkeypatch):
    _feed(monkeypatch, {})
    api = _api()
    api.betting.tipi_ko = True
    ch = _giro(monkeypatch, api)
    board = ch.ultimo("board")
    assert "market_types" not in board and len(board["rows"]) == 2   # il board resta


# ===========================================================================
# 3. par. 3 board_mercato
# ===========================================================================
def _con_tipi(et: str = "1") -> None:
    bw._STATE["event_type_id"] = et
    bw._STATE["market_types"] = bw.tipi_da_risultato(
        [BR.MarketTypeResult(marketType=t, marketCount=n) for t, n in _TIPI_CALCIO], et)


def test_richiesta_board_mercato_validazioni_tetto_e_ttl(monkeypatch):
    ore = _Orologio()
    monkeypatch.setattr(bw, "time", ore)
    bw._STATE["event_type_id"] = "1"
    assert bw.richiedi_mercato({"market_type": "OVER_UNDER_25"})[0] is False   # tipi non caricati
    _con_tipi()
    assert bw.richiedi_mercato({}) == (False, "market_type mancante")
    ok, e = bw.richiedi_mercato({"market_type": "MATCH_ODDS"})
    assert not ok and "board di sempre" in e
    for escluso in ("CORRECT_SCORE", "correct_score2_a", "HALF_TIME_SCORE",
                    "FIRST_HALF_CORRECT_SCORE"):
        ok, e = bw.richiedi_mercato({"market_type": escluso})
        assert not ok and "escluso" in e, escluso
    ok, e = bw.richiedi_mercato({"market_type": "DOUBLE_CHANCE"})
    assert not ok and "sconosciuto" in e
    for mt in ("over_under_25", "ASIAN_HANDICAP", "BOTH_TEAMS_TO_SCORE"):
        assert bw.richiedi_mercato({"market_type": mt}) == (True, None)
    ok, e = bw.richiedi_mercato({"market_type": "DRAW_NO_BET"})
    assert not ok                                         # non nei tipi
    # un quarto tipo valido oltre il tetto: rifiutato, nessuno espulso
    bw._STATE["market_types"].append({"market_type": "DRAW_NO_BET", "name": "x", "count": 1})
    ok, e = bw.richiedi_mercato({"market_type": "DRAW_NO_BET"})
    assert not ok and "tetto di 3" in e
    assert bw.tipi_richiesti() == ["ASIAN_HANDICAP", "BOTH_TEAMS_TO_SCORE", "OVER_UNDER_25"]
    # il rinnovo di un tipo gia' richiesto passa sempre
    ore.t += 60.0
    assert bw.richiedi_mercato({"market_type": "OVER_UNDER_25"}) == (True, None)
    ore.t += 16.0                                         # gli altri due: 76 s senza rinnovo
    assert bw.tipi_richiesti() == ["OVER_UNDER_25"]
    assert bw.richiedi_mercato({"market_type": "DRAW_NO_BET"}) == (True, None)


def test_push_board_mercato_feed_dove_copre_rest_altrove_e_handicap(monkeypatch):
    _feed(monkeypatch, {E1: ("calcio", _payload_calcio())})
    api = _api()
    ch = _giro(monkeypatch, api)                           # carica i tipi
    assert ch.ultimo("board_mercato") is None              # nessun tipo richiesto
    assert bw.richiedi_mercato({"market_type": "OVER_UNDER_25"}) == (True, None)
    assert bw.richiedi_mercato({"market_type": "ASIAN_HANDICAP"}) == (True, None)
    ch.usciti.clear()
    bw._STATE["giro_ts"] = 0.0
    _giro(monkeypatch, api, ch=ch)
    pm = {d["market_type"]: d for t, d in ch.usciti if t == "board_mercato"}
    assert set(pm) == {"OVER_UNDER_25", "ASIAN_HANDICAP"}
    ou = pm["OVER_UNDER_25"]
    assert set(ou) == {"market_type", "rows", "updated_ms"}
    righe = {r["market_id"]: r for r in ou["rows"]}
    assert set(righe) == {"1.201", "1.202"}
    feed = righe["1.201"]
    # prezzi dal FEED (1.91, non i 1.9 della REST), volume dalla REST
    assert feed["selections"][0] == {"selection_id": 47972, "name": "Under 2.5 Goals",
                                     "handicap": 0.0, "back": 1.91, "lay": 1.93, "ltp": None,
                                     "back_size": 250.0, "lay_size": 120.0}
    assert feed["total_matched"] == 5000.0 and feed["inplay"] is True
    assert feed["market_name"] == "Over/Under 2.5 Goals" and feed["event_id"] == E1
    rest = righe["1.202"]
    assert rest["selections"][0]["back"] == 2.2 and rest["selections"][0]["ltp"] == 2.2
    assert set(rest) == set(feed) == {"event_id", "market_id", "market_name", "status",
                                      "inplay", "total_matched", "selections"}
    ah = pm["ASIAN_HANDICAP"]["rows"]
    assert len(ah) == 1
    assert [(s["selection_id"], s["handicap"], s["back"]) for s in ah[0]["selections"]] == [
        (11, -0.5, 1.8), (22, 0.5, 2.1), (11, -1.0, 2.4), (22, 1.0, 1.6)]
    # i tipi si caricano una volta (catalogo per tipo, cache 300 s) e la REST e' a blocchi
    cats = [c for c in api.betting.chiamate if c[0] == "catalogo"]
    assert cats.count(("catalogo", ["OVER_UNDER_25"])) == 1
    assert cats.count(("catalogo", ["ASIAN_HANDICAP"])) == 1
    _scrivi_esempio("calcio", ch.ultimo("board"), pm["OVER_UNDER_25"])


def test_tipo_scaduto_niente_piu_push_ne_rest(monkeypatch):
    ore = _Orologio()
    monkeypatch.setattr(bw, "time", ore)
    _feed(monkeypatch, {})
    api = _api()
    ch = _giro(monkeypatch, api)
    assert bw.richiedi_mercato({"market_type": "OVER_UNDER_25"}) == (True, None)
    _giro(monkeypatch, api, ch=ch)
    assert ch.ultimo("board_mercato")["market_type"] == "OVER_UNDER_25"
    ore.t += bw.TTL_RICHIESTA_S + 1.0
    ch.usciti.clear()
    n = len(api.betting.chiamate)
    _giro(monkeypatch, api, ch=ch)
    assert ch.ultimo("board_mercato") is None and "OVER_UNDER_25" not in bw._MERCATI
    assert not [c for c in api.betting.chiamate[n:] if c == ("catalogo", ["OVER_UNDER_25"])]


# ===========================================================================
# 4. il canale: board_mercato di sola lettura su un WebSocket VERO
# ===========================================================================
def _porta_libera() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _richiesta(ws, msg: Dict[str, Any]) -> Dict[str, Any]:
    ws.send(json.dumps(msg))
    while True:
        r = json.loads(ws.recv(timeout=5))
        if r.get("id") == msg["id"]:
            return r


def test_canale_board_mercato_senza_token_risposta_subito_mai_in_coda():
    from websockets.sync.client import connect

    ch = LC.LocalChannel(_porta_libera(), sport="calcio", token="t" * 64)
    assert ch.start() is True
    with connect(f"ws://127.0.0.1:{ch.port}", origin="http://127.0.0.1:47330") as ws:
        assert json.loads(ws.recv(timeout=5))["t"] == "hello"
        # nessun board registrato nel processo: rifiuto dichiarato
        r = _richiesta(ws, {"id": 1, "m": "board_mercato", "p": {"market_type": "X"}})
        assert r == {"id": 1, "ok": False, "e": "board non attivo su questo canale"}
        visti: List[Any] = []

        def _cb(p):
            visti.append(p)
            return (True, None) if p.get("market_type") == "OVER_UNDER_25" else (False, "no")
        ch.set_board_mercato(_cb)
        assert _richiesta(ws, {"id": 2, "m": "board_mercato",
                               "p": {"market_type": "OVER_UNDER_25"}}) == {"id": 2, "ok": True}
        assert _richiesta(ws, {"id": 3, "m": "board_mercato", "p": {"market_type": "Z"}}) == \
            {"id": 3, "ok": False, "e": "no"}
        # SENZA token la connessione resta aperta (non e' un comando che esegue)
        assert _richiesta(ws, {"id": 4, "m": "board_mercato", "p": None})["ok"] is False
    assert visti[:2] == [{"market_type": "OVER_UNDER_25"}, {"market_type": "Z"}]
    assert visti[2] == {}
    assert ch.pop_requests() == [] and ch.statistiche()["rifiutati_token"] == 0
    assert "board_mercato" not in LC._METODI_CHE_ESEGUONO


def test_canale_di_un_bot_e_lettore_rifiutano_board_mercato():
    from websockets.sync.client import connect

    bot = LC.LocalChannel(_porta_libera(), sport="omega", token="t" * 64, solo_lettura=True)
    assert bot.start() is True
    bot.set_board_mercato(lambda p: (True, None))
    with connect(f"ws://127.0.0.1:{bot.port}") as ws:
        json.loads(ws.recv(timeout=5))
        r = _richiesta(ws, {"id": 1, "m": "board_mercato", "p": {"market_type": "A"}})
        assert r["ok"] is False and "sola lettura" in r["e"]
    ch = LC.LocalChannel(_porta_libera(), sport="calcio", token="t" * 64)
    assert ch.start() is True
    ch.set_board_mercato(lambda p: (True, None))
    with connect(f"ws://127.0.0.1:{ch.port}/lettore/board") as ws:
        json.loads(ws.recv(timeout=5))
        r = _richiesta(ws, {"id": 1, "m": "board_mercato", "p": {"market_type": "A"}})
        assert r["ok"] is False and "lettore" in r["e"]


# ===========================================================================
# 5. un giro alla volta, cadenza condivisa
# ===========================================================================
def test_un_giro_alla_volta_e_zero_costo_senza_desktop(monkeypatch):
    _feed(monkeypatch, {})
    api = _api()
    ch = _Canale()
    ch.attivo = False
    _giro(monkeypatch, api, ch=ch)
    assert api.betting.chiamate == [] and ch.usciti == []          # nessun desktop
    ch.attivo = True
    assert bw._LOCK_GIRO.acquire(blocking=False)
    try:
        _giro(monkeypatch, api, ch=ch)                               # giro gia' in corso
    finally:
        bw._LOCK_GIRO.release()
    assert api.betting.chiamate == [] and ch.usciti == []
    _giro(monkeypatch, api, ch=ch)
    assert ch.ultimo("board") is not None


def test_giro_da_parcheggiato_rispetta_la_cadenza_del_worker(monkeypatch):
    ore = _Orologio()
    monkeypatch.setattr(bw, "time", ore)
    _feed(monkeypatch, {})
    ch = _Canale()
    monkeypatch.setattr(LC, "_CHANNEL", ch)
    s = SimpleNamespace(context_api_client=_api())
    assert bw.giro_da_parcheggiato(s, "1", 10.0) is True
    ore.t += 9.0
    assert bw.giro_da_parcheggiato(s, "1", 10.0) is False           # troppo presto
    ore.t += 1.5
    assert bw.giro_da_parcheggiato(s, "1", 10.0) is True
    assert len([t for t, _ in ch.usciti if t == "board"]) == 2
    # un giro del worker di flumine conta anche per il ciclo d'attesa
    ore.t += 10.0
    bw.board_worker({}, None, session=s, event_type_id="1")
    assert bw.giro_da_parcheggiato(s, "1", 10.0) is False
    # mai solleva, anche con un client rotto
    ore.t += 20.0
    assert bw.giro_da_parcheggiato(SimpleNamespace(context_api_client=None), "1", 10.0) is True


# ===========================================================================
# 6. il RUNNER parcheggiato pubblica il board (setup_and_run VERO)
# ===========================================================================
class _Fermo(Exception):
    """Ferma ``setup_and_run`` al primo sonno del ciclo d'attesa."""


def _sonno_che_ferma(sonni: List[float]):
    import threading

    def _sonno(s):
        if threading.current_thread() is threading.main_thread():
            sonni.append(s)
            raise _Fermo()
        threading.Event().wait()          # thread di servizio: fermo per sempre
    return _sonno


def test_runner_tennis_parcheggiato_pubblica_il_board(monkeypatch):
    from Betfair.stream.tennis_live import tennis_bot_service as TBS
    from Betfair.stream.tennis_live import tennis_runner as TR

    cat = {"MATCH_ODDS": [_cat("1.401", T1, "Barrios Vera v Simakin", "Match Odds",
                               [(9633138, "Barrios Vera", 0.0, 1),
                                (35635727, "Simakin", 0.0, 2)])]}
    books = {"1.401": _book("1.401", inplay=True, tm=43210.0, bet_delay=3,
                            runners=[(9633138, 0.0, 1.8, 1.82, 1.0, 1.0),
                                     (35635727, 0.0, 2.2, 2.24, 1.0, 1.0)])}
    api = _api(cat, books, [("MATCH_ODDS", 1)])
    _feed(monkeypatch, {T1: ("tennis", _payload_tennis())})
    ch = _Canale("tennis", 47332)

    def _start(port, sport, solo_lettura=False):
        assert (port, sport) == (47332, "tennis")
        monkeypatch.setattr(LC, "_CHANNEL", ch)
        return ch
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "OFF")
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setattr(TR, "build_client", lambda login=True: api)
    monkeypatch.setattr(TR._valuta.CAMBIO, "avvia", lambda *_a, **_k: None)
    monkeypatch.setattr(TBS, "ferma_bot_al_nuovo_avvio", lambda *a, **k: None)
    monkeypatch.setattr(TR, "_cleanup_orphan_bot_controls", lambda: None)
    monkeypatch.setattr(TR.tennis_db, "chiudi_tennis_now_orfani", lambda: 0)
    monkeypatch.setattr(TR, "_avvia_sveglia_armamento", lambda s: None)
    monkeypatch.setattr(TR, "_announce_order_mode", lambda m: None)
    monkeypatch.setattr(TR, "safe_logout", lambda t: None)
    monkeypatch.setattr(TR.tennis_db, "list_pending_tennis_follows", lambda: [])
    monkeypatch.setattr(LC, "start_channel", _start)
    # un clic del desktop arrivato a runner parcheggiato: deve avere risposta
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=7, method="order", params={
        "action": "place", "mode": "paper", "market_id": "1.401", "selection_id": 9633138,
        "side": "BACK", "price": 1.8, "size": 2.0, "client_ref": "cr-7"}))
    sonni: List[float] = []
    monkeypatch.setattr(TR.time, "sleep", _sonno_che_ferma(sonni))
    with pytest.raises(_Fermo):
        TR.setup_and_run()
    assert sonni, "ciclo d'attesa non raggiunto"
    board = ch.ultimo("board")
    assert board is not None, "runner tennis parcheggiato: nessun board pubblicato"
    assert board["rows"][0]["event_id"] == T1
    assert board["rows"][0]["score"]["points"] == {"p1": "40", "p2": "AD"}
    assert board["market_types"][0]["market_type"] == "MATCH_ODDS"
    # processo in OFF: rifiuto immediato e dichiarato, mai una richiesta appesa
    assert ch.risposte == [(7, False, None, "modalita' ordini OFF: comando NON eseguito")]
    assert ch._requests.qsize() == 0


def test_runner_calcio_parcheggiato_pubblica_il_board(monkeypatch, tmp_path):
    from Betfair.stream import runner as R

    api = _api()
    _feed(monkeypatch, {E1: ("calcio", _payload_calcio())})
    ch = _Canale("calcio", 47331)

    def _start(port, sport, solo_lettura=False):
        assert (port, sport) == (47331, "calcio")
        monkeypatch.setattr(LC, "_CHANNEL", ch)
        return ch

    class _Rest:
        def login_cert(self):
            return None

    monkeypatch.setenv("LIVE_ORDER_MODE", "OFF")
    monkeypatch.setenv("LIVE_RUNNER_KEEP_ALIVE", "1")
    monkeypatch.setattr(R, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(R, "uploader", SimpleNamespace(sweep_pending=lambda **k: None))
    monkeypatch.setattr(R, "BetfairClient", _Rest)
    monkeypatch.setattr(R, "build_client", lambda login=True: api)
    monkeypatch.setattr(R._valuta.CAMBIO, "avvia", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_chiudi_live_now_orfani_all_avvio", lambda: None)
    monkeypatch.setattr(R, "live_order_mode", lambda: "OFF")
    monkeypatch.setattr(R._MO, "richiedi_avvio", lambda: None)
    monkeypatch.setattr(R._MO, "valore_db", lambda *a, **k: None)
    monkeypatch.setattr(R, "_dichiara_modo_ordini_all_avvio", lambda **k: None)
    monkeypatch.setattr(R, "_announce_order_mode", lambda *a, **k: None)
    monkeypatch.setattr(R._AO, "richiesto", lambda: False)
    monkeypatch.setattr(R, "resolve_and_register", lambda rest: None)
    monkeypatch.setattr(R.db, "list_pending_follows", lambda: [])
    monkeypatch.setattr(R, "_sync_record_events", lambda s, f: None)
    monkeypatch.setattr(R, "_battito_in_attesa", lambda s, t: None)
    monkeypatch.setattr(R, "run_account_sync_if_due", lambda s: None)
    monkeypatch.setattr(R, "_MOTORE", {"motore": None, "api": None, "auto": None})
    monkeypatch.setattr(LC, "start_channel", _start)
    ch._requests.put_nowait(LC.LocalRequest(ws=None, msg_id=9, method="order", params={
        "action": "place", "mode": "paper", "market_id": "1.101", "selection_id": 11,
        "side": "BACK", "price": 1.5, "size": 2.0, "client_ref": "cr-9"}))
    sonni: List[float] = []
    monkeypatch.setattr(R.time, "sleep", _sonno_che_ferma(sonni))
    with pytest.raises(_Fermo):
        R.setup_and_run()
    assert sonni, "ciclo d'attesa non raggiunto"
    board = ch.ultimo("board")
    assert board is not None, "runner calcio parcheggiato: nessun board pubblicato"
    r1 = {r["event_id"]: r for r in board["rows"]}[E1]
    assert r1["score"]["minute"] == 67 and r1["fixture_id"] == 1234567
    # senza motore ordini (qui OFF): rifiuto SUBITO col motivo, mai appesa in RAM
    assert ch.risposte == [(9, False, None, R._MOTIVO_PARCHEGGIATO_SENZA_MOTORE)]
    assert ch._requests.qsize() == 0


def test_esempio_tennis_per_il_referto(monkeypatch):
    """Il payload VERO del tennis (generato dal codice) per il referto."""
    cat = {"MATCH_ODDS": [_cat("1.401", T1, "Barrios Vera v Simakin", "Match Odds",
                               [(9633138, "Barrios Vera", 0.0, 1),
                                (35635727, "Simakin", 0.0, 2)])],
           "SET_BETTING": [_cat("1.402", T1, "Barrios Vera v Simakin", "Set Betting",
                                [(1, "2 - 0", 0.0, 1), (2, "2 - 1", 0.0, 2)])]}
    books = {"1.401": _book("1.401", inplay=True, tm=43210.0, bet_delay=3,
                            runners=[(9633138, 0.0, 1.8, 1.82, 1.0, 1.0),
                                     (35635727, 0.0, 2.2, 2.24, 1.0, 1.0)]),
             "1.402": _book("1.402", inplay=True, tm=900.0, bet_delay=3,
                            runners=[(1, 0.0, 3.1, 3.3, 12.0, 4.0), (2, 0.0, 4.5, 4.9, 6.0, 2.0)])}
    _feed(monkeypatch, {T1: ("tennis", _payload_tennis())})
    api = _api(cat, books, [("MATCH_ODDS", 1), ("SET_BETTING", 1)])
    ch = _giro(monkeypatch, api, et="2")
    assert bw.richiedi_mercato({"market_type": "SET_BETTING"}) == (True, None)
    bw._STATE["giro_ts"] = 0.0
    _giro(monkeypatch, api, et="2", ch=ch)
    pm = ch.ultimo("board_mercato")
    assert pm["market_type"] == "SET_BETTING" and pm["rows"][0]["market_id"] == "1.402"
    _scrivi_esempio("tennis", ch.ultimo("board"), pm)


def _scrivi_esempio(sport: str, board: Any, mercato: Any = None) -> None:
    """Con ``BOARD_ESEMPIO_DIR`` impostata scrive il payload prodotto (referto)."""
    cartella = os.getenv("BOARD_ESEMPIO_DIR", "").strip()
    if not cartella:
        return
    with open(os.path.join(cartella, f"board_{sport}.json"), "w", encoding="utf-8") as fh:
        json.dump({"board": board, "board_mercato": mercato}, fh, indent=1, ensure_ascii=True)
