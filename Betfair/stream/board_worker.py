"""board_worker.py — BOARD del giorno per l'app desktop (quote standard realtime).

Pubblica sul CANALE LOCALE l'elenco degli eventi in programma OGGI (calcio o
tennis) con le quote principali del MATCH_ODDS (best back/lay + LTP). NESSUNA
scrittura DB, NESSUNA subscription stream propria: è la vista "panoramica" — la
profondità piena e la registrazione partono SOLO con "Segui live".

FONTE DEI PREZZI (audit 09/09 — "nessuna chiamata duplicata"): lo scanner
Safe Strategy tiene già in push (Exchange Stream API, conflate 1s) il MATCH_ODDS
di OGNI evento in-play o a ridosso del kickoff e lo pubblica su
``safe_strategy_scan`` con selection_id, best back/lay, LTP, volume e stato.
Prima questo worker rifaceva per conto suo 3 ``listMarketBook`` ogni 10s (18
chiamate REST/min per sport) sugli STESSI mercati. Ora:
  · eventi coperti dallo scanner (riga fresca) → prezzi dal feed, freschi al secondo;
  · eventi NON coperti (KO lontano, scanner giù) → ``listMarketBook`` di fallback
    a cadenza LENTA (60s: pre-match lontano dal KO, i prezzi si muovono poco).
Il catalogo del giorno resta il proprio (1 chiamata / 300s: elenco + nomi).

COSTO ZERO quando il desktop non è collegato: senza client locali il worker
esce subito (nessuna chiamata REST, nessuna lettura DB).

09/10/2026 (programma del giorno, contratto ``AUDIT_2026-10-09/programma_del_giorno/
CONTRATTO.md`` par. 1-par. 3, ordine dell'utente):
  - il board si pubblica ANCHE col runner PARCHEGGIATO (nessuna partita seguita,
    framework flumine non ancora nato): ``giro_da_parcheggiato`` e' chiamato dal
    ciclo d'attesa dei due runner, con la STESSA cadenza (``LIVE_BOARD_POLL_SEC``)
    e lo STESSO stato di questo modulo. Nessun thread nuovo: un giro alla volta
    (``_LOCK_GIRO``), chiunque lo chiami (worker di flumine o ciclo d'attesa).
    Prima il tennis senza follow non pubblicava MAI il tabellone;
  - righe estese (campi ADDITIVI, assente = non noto, mai 0): ``score`` (solo in
    gioco, dal feed dello scanner), ``fixture_id``, ``bet_delay``, ``updated_ms``,
    ``back_size``/``lay_size`` per selezione; ``total_matched`` integrato dalla
    STESSA REST di ripiego (stesso blocco da 25, stessa cadenza massima 60 s):
    lo stream dello scanner non porta il volume (``tv`` assente) e il feed lo
    lascia None o fermo all'ultima lettura REST dello scanner;
  - ``market_types`` nel push ``board`` (``listMarketTypes`` sugli eventi del
    programma, cache 300 s; calcio senza nessun correct score; MATCH_ODDS primo);
  - ``board_mercato``: richiesta di SOLA LETTURA dal canale (``richiedi_mercato``,
    thread del canale, zero I/O) e push ``board_mercato`` a ogni giro per ogni
    tipo richiesto e non scaduto (TTL 75 s, al massimo ``TETTO_TIPI_RICHIESTI``
    tipi contemporanei per sport). Prezzi dal feed dove copre quel mercato
    (calcio: blocchi ``ou``/``btts``/``ht_result``), altrimenti la stessa REST a
    blocchi da 25 con cadenza massima 60 s per tipo.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import local_channel
from .scores.scan_feed import DEFAULT_MAX_AGE_SEC, fresh_payload, shared_cache

logger = logging.getLogger(__name__)

_CATALOGUE_TTL_SEC = 300.0   # refresh elenco eventi del giorno
_MAX_MARKETS = 60            # cap difensivo (peso API)
_BOOK_CHUNK = 25             # mercati per singola list_market_book
# poll REST di FALLBACK per i mercati non coperti dal feed dello scanner
_REST_FALLBACK_PERIOD_SEC = 60.0
# riga del feed più vecchia di così → si preferisce il fallback REST
_FEED_MAX_AGE_SEC = DEFAULT_MAX_AGE_SEC
# 09/10: tipi di mercato del programma (``listMarketTypes``), stessa cache del catalogo
_TYPES_TTL_SEC = _CATALOGUE_TTL_SEC
# 09/10: un tipo richiesto dal frontend e non rinnovato da tanto si dimentica
# (il frontend rinnova ogni 30 s finche' la scelta resta: contratto par. 3)
TTL_RICHIESTA_S = 75.0
# 09/10: al massimo tanti tipi richiesti contemporanei per sport (= per processo).
# Ogni tipo costa al piu' un catalogo ogni 300 s e ceil(60/25) = 3
# ``listMarketBook`` ogni 60 s: il tetto tiene il peso REST limitato anche con
# piu' finestre aperte. Un tipo in piu' oltre il tetto e' RIFIUTATO (motivo
# leggibile), mai espulso un tipo gia' richiesto da un'altra finestra.
TETTO_TIPI_RICHIESTI = 3

ET_CALCIO = "1"
ET_TENNIS = "2"
MATCH_ODDS = "MATCH_ODDS"

# stato per-processo (un solo giro alla volta: ``_LOCK_GIRO``)
_STATE: Dict[str, Any] = {
    "catalogue_ts": 0.0, "markets": [],
    "rest_ts": 0.0, "rest_rows": {},   # market_id → riga (ultimo poll REST)
    # 09/10
    "types_ts": 0.0, "market_types": None,   # None = mai letti (!= lista vuota)
    "giro_ts": 0.0,                          # ultimo giro VERO (cadenza condivisa)
    "event_type_id": None,
}
# 09/10: tipo richiesto -> monotonic dell'ultimo rinnovo (scritto dal thread del
# canale, letto dal giro): protetto da ``_LOCK_RICHIESTE``
_RICHIESTE: Dict[str, float] = {}
_LOCK_RICHIESTE = threading.Lock()
# 09/10: stato per tipo richiesto: {"catalogue_ts", "metas": {mid: meta},
# "rest_ts", "rest_rows": {mid: riga}}. Solo dal giro (sotto ``_LOCK_GIRO``).
_MERCATI: Dict[str, Dict[str, Any]] = {}
# 09/10: un giro alla volta, chiunque lo chiami (worker di flumine o ciclo
# d'attesa del runner): acquisizione NON bloccante, chi arriva secondo salta
_LOCK_GIRO = threading.Lock()

# nomi leggibili dei tipi piu' comuni (``listMarketTypes`` non porta i nomi);
# gli altri si leggono dal codice (``nome_tipo``)
_NOMI_TIPO_CALCIO = {
    MATCH_ODDS: "Esito finale (1X2)",
    "BOTH_TEAMS_TO_SCORE": "Goal / No goal",
    "HALF_TIME": "Primo tempo (1X2)",
    "DOUBLE_CHANCE": "Doppia chance",
    "DRAW_NO_BET": "Draw no bet",
    "ASIAN_HANDICAP": "Handicap asiatico",
    "ALT_TOTAL_GOALS": "Totale gol (linee asiatiche)",
    "HALF_TIME_FULL_TIME": "Parziale / Finale",
    "TOTAL_GOALS": "Totale gol",
    "ODD_OR_EVEN": "Pari / Dispari",
    "TEAM_TOTAL_GOALS": "Gol della squadra",
}
_NOMI_TIPO_TENNIS = {
    MATCH_ODDS: "Vincente incontro",
    "SET_BETTING": "Risultato in set",
    "SET_WINNER": "Vincente del set",
    "NUMBER_OF_SETS": "Numero di set",
    "HANDICAP": "Handicap game",
    "TOTAL_GAMES": "Totale game",
}


def _ora_ms() -> int:
    return int(time.time() * 1000)


def _today_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=8)          # include i LIVE anche lunghi (start nel passato)
    end = now.replace(hour=23, minute=59, second=59)
    if end <= start:
        end = start + timedelta(hours=24)
    return start.isoformat(), end.isoformat()


def _open_date(c: Any) -> Any:
    v = getattr(c, "market_start_time", None)
    return (v or "").isoformat() if hasattr(v, "isoformat") else v


def _refresh_catalogue(api_client: Any, event_type_id: str) -> None:
    from betfairlightweight import filters

    frm, to = _today_window_iso()
    cats = api_client.betting.list_market_catalogue(
        filter=filters.market_filter(
            event_type_ids=[event_type_id],
            market_type_codes=[MATCH_ODDS],
            market_start_time={"from": frm, "to": to},
        ),
        market_projection=["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        sort="FIRST_TO_START",
        max_results=_MAX_MARKETS,
    )
    markets: List[Dict[str, Any]] = []
    for c in cats or []:
        event = getattr(c, "event", None)
        runners = {
            int(r.selection_id): getattr(r, "runner_name", None)
            for r in (getattr(c, "runners", None) or [])
            if getattr(r, "selection_id", None) is not None
        }
        markets.append({
            "market_id": getattr(c, "market_id", None),
            "event_id": getattr(event, "id", None),
            "event_name": getattr(event, "name", None),
            "open_date": _open_date(c),
            "runners": runners,
        })
    _STATE["markets"] = [m for m in markets if m["market_id"]]
    _STATE["catalogue_ts"] = time.monotonic()
    logger.info("[board] catalogo aggiornato: %d eventi", len(_STATE["markets"]))


def _best(levels: Any) -> Optional[float]:
    # 30/09: nel processo del runner flumine e' importato e SOSTITUISCE
    # ``bettingresources.RunnerBookEX`` con la sua classe "pigra"
    # (flumine/__init__.py), che lascia i livelli come DIZIONARI
    # {"price", "size"}: ``levels[0].price`` sollevava e il board mostrava
    # quote vuote su ogni mercato letto via REST. Si legge con la funzione
    # dello scanner che tollera ENTRAMBE le forme (oggetto PriceSize o dict).
    from Betfair.safe_strategy.scanner import best_price

    return best_price(levels)


def _best_size(levels: Any) -> Optional[float]:
    """09/10: importo disponibile al MIGLIOR prezzo (stessa funzione dello
    scanner, che tollera oggetti PriceSize e dizionari di flumine)."""
    from Betfair.safe_strategy.scanner import best_size

    return best_size(levels)


def _int_o_none(v: Any) -> Optional[int]:
    if isinstance(v, bool):
        return None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _num_o_none(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _selezione_da_runner(r: Any, nome: Any, handicap: bool = False) -> Dict[str, Any]:
    ex = getattr(r, "ex", None)
    atb = getattr(ex, "available_to_back", None) if ex else None
    atl = getattr(ex, "available_to_lay", None) if ex else None
    sel: Dict[str, Any] = {
        "selection_id": getattr(r, "selection_id", None),
        "name": nome,
    }
    if handicap:
        sel["handicap"] = _num_o_none(getattr(r, "handicap", None))
    sel.update({
        "back": _best(atb) if ex else None,
        "lay": _best(atl) if ex else None,
        "ltp": getattr(r, "last_price_traded", None),
        "back_size": _best_size(atb) if ex else None,
        "lay_size": _best_size(atl) if ex else None,
    })
    return sel


def _row_from_book(meta: Dict[str, Any], b: Any) -> Dict[str, Any]:
    selections = [
        _selezione_da_runner(r, meta["runners"].get(getattr(r, "selection_id", None)))
        for r in getattr(b, "runners", None) or []
    ]
    return {
        "event_id": meta["event_id"],
        "event_name": meta["event_name"],
        "open_date": meta["open_date"],
        "market_id": meta["market_id"],
        "status": getattr(b, "status", None),
        "inplay": bool(getattr(b, "inplay", False)),
        "total_matched": getattr(b, "total_matched", None),
        "selections": selections,
        # 09/10: il betDelay del book REST (0 pre-match, 5 s in gioco calcio)
        "bet_delay": _int_o_none(getattr(b, "bet_delay", None)),
    }


def row_from_scan_payload(meta: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Riga board dal payload dello scanner (PURA). None se il payload non ha
    il MATCH_ODDS dell'evento o i selection_id (righe di scanner vecchi)."""
    odds = payload.get("odds")
    if not isinstance(odds, dict) or str(payload.get("mo_market_id") or "") != str(meta["market_id"]):
        return None
    # ordine come sul sito: casa/p1, trasferta/p2, pareggio
    selections: List[Dict[str, Any]] = []
    for side in ("home", "p1", "away", "p2", "draw"):
        pair = odds.get(side)
        if not isinstance(pair, dict):
            continue
        sid = pair.get("selection_id")
        if sid is None:
            return None  # scanner senza selection_id: fallback REST
        selections.append({
            "selection_id": int(sid),
            "name": meta["runners"].get(int(sid)),
            "back": pair.get("back"),
            "lay": pair.get("lay"),
            "ltp": pair.get("ltp"),
            # 09/10: importo al miglior prezzo (``scanner.price_pair``); assente = None
            "back_size": pair.get("back_size"),
            "lay_size": pair.get("lay_size"),
        })
    if not selections:
        return None
    return {
        "event_id": meta["event_id"],
        "event_name": meta["event_name"],
        "open_date": meta["open_date"],
        "market_id": meta["market_id"],
        "status": payload.get("mo_status"),
        "inplay": bool(payload.get("inplay")),
        "total_matched": payload.get("mo_total_matched"),
        "selections": selections,
        "bet_delay": _int_o_none(payload.get("bet_delay")),
    }


# ---------------------------------------------------------------------------
# 09/10: punteggio, fixture e campi del feed (PURI)
# ---------------------------------------------------------------------------
def intervallo_da_stato_ips(raw: Any) -> Optional[bool]:
    """True all'intervallo, False se lo stato IPS c'e' e non e' l'intervallo,
    None se lo stato manca (non noto, mai un False inventato). Stessa lista di
    stati della fonte unica ``atlante_v4.tempo_da_stato_ips``."""
    if not isinstance(raw, dict):
        return None
    st = "".join(ch for ch in str(raw.get("matchStatus") or raw.get("status") or "").lower()
                 if ch.isalpha())
    if not st:
        return None
    from Betfair.stream.scalper.atlante_v4 import _STATI_INTERVALLO

    return any(k in st for k in _STATI_INTERVALLO)


def score_calcio(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Blocco ``score`` CALCIO del contratto dal payload dello scanner."""
    return {
        "sport": "calcio",
        "minute": _int_o_none(payload.get("minute")),
        "home": _int_o_none(payload.get("score_home")),
        "away": _int_o_none(payload.get("score_away")),
        "red_home": _int_o_none(payload.get("red_home")),
        "red_away": _int_o_none(payload.get("red_away")),
        "ht": intervallo_da_stato_ips(payload.get("score_raw")),
    }


def _coppia_int(v: Any) -> Optional[Dict[str, int]]:
    if not isinstance(v, dict):
        return None
    p1, p2 = _int_o_none(v.get("p1")), _int_o_none(v.get("p2"))
    return {"p1": p1, "p2": p2} if p1 is not None and p2 is not None else None


def score_tennis(payload: Dict[str, Any], event_id: Any) -> Dict[str, Any]:
    """Blocco ``score`` TENNIS: set e game dal payload (gia' parsati dallo
    scanner), punti e battuta dallo stato IPS grezzo con il parser di sempre
    (``tennis_score.parse_tennis_scores``). p1 = casa = primo nome dell'evento."""
    from Betfair.stream.tennis_scalper.tennis_score import parse_tennis_scores

    raw = payload.get("score_raw")
    ts = parse_tennis_scores([raw], event_id) if isinstance(raw, dict) else None
    points = None
    server = None
    if ts is not None:
        if ts.point_home is not None and ts.point_away is not None:
            points = {"p1": str(ts.point_home), "p2": str(ts.point_away)}
        server = {"home": "p1", "away": "p2"}.get(ts.server or "")
    return {
        "sport": "tennis",
        "sets": _coppia_int(payload.get("sets")),
        "games": _coppia_int(payload.get("games")),
        "points": points,
        "server": server,
    }


def fixture_da_payload(payload: Optional[Dict[str, Any]]) -> Optional[int]:
    """``selection_hint.fixture_id`` della riga calcio dello scanner (Statistiche)."""
    hint = payload.get("selection_hint") if isinstance(payload, dict) else None
    return _int_o_none(hint.get("fixture_id")) if isinstance(hint, dict) else None


def arricchisci_riga(row: Dict[str, Any], payload: Optional[Dict[str, Any]],
                     event_type_id: str, rest_row: Optional[Dict[str, Any]],
                     ora_ms: int) -> Dict[str, Any]:
    """I campi del contratto par. 1 su una riga gia' costruita (feed o REST). PURA.

    ``payload`` = riga FRESCA del feed per l'evento (None se assente/stantia):
    punteggio e fixture vengono SOLO da li' (il bet delay dal book, se la riga
    e' REST, altrimenti dal feed). ``rest_row`` = riga
    dell'ultimo poll REST dello stesso mercato: il suo ``total_matched`` (vero,
    REST) vince su quello del feed (lo stream dello scanner non porta il volume).
    """
    if rest_row is not None and rest_row.get("total_matched") is not None:
        row["total_matched"] = rest_row["total_matched"]
    if row.get("bet_delay") is None and isinstance(payload, dict):
        row["bet_delay"] = _int_o_none(payload.get("bet_delay"))
    row.setdefault("bet_delay", None)
    score = None
    if row.get("inplay") and isinstance(payload, dict):
        score = (score_calcio(payload) if str(event_type_id) == ET_CALCIO
                 else score_tennis(payload, row.get("event_id")))
    row["score"] = score
    row["fixture_id"] = fixture_da_payload(payload) if str(event_type_id) == ET_CALCIO else None
    row["updated_ms"] = int(ora_ms)
    return row


# ---------------------------------------------------------------------------
# REST di ripiego (stessa per MATCH_ODDS e per i tipi richiesti)
# ---------------------------------------------------------------------------
def _poll_books_rest(api_client: Any, metas: Dict[str, Dict[str, Any]],
                     costruisci: Any = None) -> Dict[str, Dict[str, Any]]:
    """listMarketBook (EX_BEST_OFFERS) SOLO dei mercati indicati -> {market_id: riga}.
    A blocchi da ``_BOOK_CHUNK``. ``costruisci(meta, book)`` = la riga (default:
    riga MATCH_ODDS del board)."""
    from betfairlightweight import filters

    costruisci = costruisci or _row_from_book
    rows: Dict[str, Dict[str, Any]] = {}
    ids = list(metas.keys())
    for i in range(0, len(ids), _BOOK_CHUNK):
        chunk = ids[i:i + _BOOK_CHUNK]
        books = api_client.betting.list_market_book(
            market_ids=chunk,
            price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
        )
        for b in books or []:
            meta = metas.get(getattr(b, "market_id", None))
            if meta is not None:
                rows[meta["market_id"]] = costruisci(meta, b)
    return rows


def _payload_freschi(event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """{event_id: payload} delle righe FRESCHE del feed (una lettura della cache
    condivisa del processo, come prima)."""
    if not event_ids:
        return {}
    cache = shared_cache()
    scan_rows = cache.rows_for(list(event_ids))
    if not scan_rows:
        return {}
    scanner_age = cache.scanner_age_sec()
    out: Dict[str, Dict[str, Any]] = {}
    for eid, row in scan_rows.items():
        payload = fresh_payload(row, _FEED_MAX_AGE_SEC, scanner_age_sec=scanner_age)
        if payload is not None:
            out[str(eid)] = payload
    return out


def _collect_rows(api_client: Any, payloads: Optional[Dict[str, Dict[str, Any]]] = None,
                  event_type_id: Optional[str] = None) -> List[Dict[str, Any]]:
    metas = {m["market_id"]: m for m in _STATE["markets"]}
    et = str(event_type_id or _STATE.get("event_type_id") or ET_CALCIO)
    # 1) prezzi dal feed dello scanner (una SELECT, cache condivisa del processo)
    by_event = {str(m["event_id"]): m for m in metas.values() if m.get("event_id") is not None}
    if payloads is None:
        payloads = _payload_freschi(list(by_event.keys()))
    rows: Dict[str, Dict[str, Any]] = {}
    for eid, payload in payloads.items():
        meta = by_event.get(eid)
        if meta is None:
            continue
        built = row_from_scan_payload(meta, payload)
        if built is not None:
            rows[meta["market_id"]] = built
    # 2) REST LENTO (60 s, blocchi da 25): i prezzi dei mercati non coperti dal
    # feed E (09/10) il volume di TUTTI. Lo stream dello scanner non porta il
    # volume (``tv`` assente): il ``mo_total_matched`` del feed e' None o fermo
    # all'ultima lettura REST dello scanner, che a mercato coperto dallo stream
    # non rilegge piu'. Lo stesso giro REST di sempre, sugli stessi blocchi: al
    # piu' ceil(60/25) = 3 chiamate ogni 60 s, nessuna chiamata in piu' per riga.
    now_mono = time.monotonic()
    if metas and now_mono - float(_STATE.get("rest_ts", 0.0)) >= _REST_FALLBACK_PERIOD_SEC:
        _STATE["rest_ts"] = now_mono
        _STATE["rest_rows"] = _poll_books_rest(api_client, metas)
    rest_rows = _STATE["rest_rows"]
    for mid in metas:
        if mid not in rows and rest_rows.get(mid) is not None:
            rows[mid] = dict(rest_rows[mid])
    ora = _ora_ms()
    out: List[Dict[str, Any]] = []
    # ordine del catalogo (per orario KO)
    for mid, meta in metas.items():
        if mid not in rows:
            continue
        out.append(arricchisci_riga(rows[mid], payloads.get(str(meta.get("event_id"))), et,
                                    rest_rows.get(mid), ora))
    return out


# ---------------------------------------------------------------------------
# 09/10: tipi di mercato del programma (contratto par. 2)
# ---------------------------------------------------------------------------
def tipo_escluso(market_type: Any, event_type_id: Any) -> bool:
    """Sul CALCIO nessun correct score: ``CORRECT_SCORE``, ``CORRECT_SCORE2*``,
    ``HALF_TIME_SCORE`` e ogni tipo che contiene ``CORRECT_SCORE``. Il tennis
    non ha esclusioni (contratto par. 2)."""
    mt = str(market_type or "").upper()
    if str(event_type_id) != ET_CALCIO:
        return False
    return "CORRECT_SCORE" in mt or mt == "HALF_TIME_SCORE"


def nome_tipo(market_type: str, event_type_id: Any) -> str:
    """Nome leggibile del tipo (``listMarketTypes`` non porta i nomi)."""
    mt = str(market_type or "").upper()
    tab = _NOMI_TIPO_CALCIO if str(event_type_id) == ET_CALCIO else _NOMI_TIPO_TENNIS
    if mt in tab:
        return tab[mt]
    from Betfair.safe_strategy.scanner import ou_line_from_market_type

    linea = ou_line_from_market_type(mt)
    if linea is not None:
        return f"Under/Over {linea:g}" + (" gol" if str(event_type_id) == ET_CALCIO else "")
    if mt.startswith("FIRST_HALF_GOALS_") and len(mt) == len("FIRST_HALF_GOALS_") + 2 \
            and mt[-2:].isdigit():
        return f"Under/Over {mt[-2]}.{mt[-1]} gol 1T"
    return mt.replace("_", " ").title()


def tipi_da_risultato(risultati: Any, event_type_id: str) -> List[Dict[str, Any]]:
    """``listMarketTypes`` -> lista del contratto par. 2 (PURA): esclusi i correct
    score sul calcio, MATCH_ODDS sempre primo, poi per numero di mercati."""
    tipi: Dict[str, int] = {}
    for r in risultati or []:
        mt = str(getattr(r, "market_type", None) or "").upper()
        if not mt or tipo_escluso(mt, event_type_id):
            continue
        n = _int_o_none(getattr(r, "market_count", None)) or 0
        tipi[mt] = tipi.get(mt, 0) + n
    altri = sorted((mt for mt in tipi if mt != MATCH_ODDS), key=lambda m: (-tipi[m], m))
    ordine = ([MATCH_ODDS] if MATCH_ODDS in tipi else []) + altri
    return [{"market_type": mt, "name": nome_tipo(mt, event_type_id), "count": tipi[mt]}
            for mt in ordine]


def _refresh_market_types(api_client: Any, event_type_id: str) -> None:
    from betfairlightweight import filters

    eventi = sorted({str(m["event_id"]) for m in _STATE["markets"] if m.get("event_id")})
    _STATE["types_ts"] = time.monotonic()
    if not eventi:
        _STATE["market_types"] = []
        return
    res = api_client.betting.list_market_types(
        filter=filters.market_filter(event_type_ids=[event_type_id], event_ids=eventi))
    _STATE["market_types"] = tipi_da_risultato(res, event_type_id)
    logger.info("[board] tipi di mercato aggiornati: %d tipi su %d eventi",
                len(_STATE["market_types"]), len(eventi))


# ---------------------------------------------------------------------------
# 09/10: mercato scelto (contratto par. 3)
# ---------------------------------------------------------------------------
def richiedi_mercato(params: Any) -> Tuple[bool, Optional[str]]:
    """Richiesta ``board_mercato`` dal canale (THREAD DEL CANALE: zero I/O, solo
    RAM). ``(True, None)`` = tipo registrato o rinnovato; ``(False, motivo)``
    altrimenti. Il tipo deve essere fra i ``market_types`` gia' pubblicati."""
    p = params if isinstance(params, dict) else {}
    mt = str(p.get("market_type") or "").strip().upper()
    et = str(_STATE.get("event_type_id") or "")
    if not mt:
        return False, "market_type mancante"
    if mt == MATCH_ODDS:
        return False, "MATCH_ODDS e' il board di sempre: non si chiede"
    if tipo_escluso(mt, et):
        return False, f"tipo {mt} escluso dal programma del calcio (correct score)"
    tipi = _STATE.get("market_types")
    if tipi is None:
        return False, "tipi di mercato non ancora caricati: riprova fra qualche secondo"
    if mt not in {t.get("market_type") for t in tipi}:
        return False, f"tipo sconosciuto: {mt} (nessun mercato negli eventi del programma)"
    ora = time.monotonic()
    with _LOCK_RICHIESTE:
        vivi = {k for k, ts in _RICHIESTE.items() if ora - ts <= TTL_RICHIESTA_S}
        if mt not in vivi and len(vivi) >= TETTO_TIPI_RICHIESTI:
            return False, (f"tetto di {TETTO_TIPI_RICHIESTI} tipi di mercato contemporanei "
                           f"raggiunto ({', '.join(sorted(vivi))}): riprova quando una "
                           f"scelta scade ({int(TTL_RICHIESTA_S)} s senza rinnovo)")
        _RICHIESTE[mt] = ora
    return True, None


def tipi_richiesti(ora: Optional[float] = None) -> List[str]:
    """I tipi richiesti e non scaduti; dimentica gli scaduti (e il loro stato)."""
    ora = time.monotonic() if ora is None else ora
    with _LOCK_RICHIESTE:
        for k in [k for k, ts in _RICHIESTE.items() if ora - ts > TTL_RICHIESTA_S]:
            _RICHIESTE.pop(k, None)
        vivi = sorted(_RICHIESTE)
    for k in [k for k in _MERCATI if k not in vivi]:
        _MERCATI.pop(k, None)
    return vivi


def _refresh_catalogo_tipo(api_client: Any, event_type_id: str, mt: str) -> Dict[str, Any]:
    from betfairlightweight import filters

    eventi = sorted({str(m["event_id"]) for m in _STATE["markets"] if m.get("event_id")})
    stato = _MERCATI.setdefault(mt, {"catalogue_ts": 0.0, "metas": {}, "rest_ts": 0.0,
                                     "rest_rows": {}})
    stato["catalogue_ts"] = time.monotonic()
    if not eventi:
        stato["metas"] = {}
        return stato
    cats = api_client.betting.list_market_catalogue(
        filter=filters.market_filter(event_type_ids=[event_type_id], event_ids=eventi,
                                     market_type_codes=[mt]),
        market_projection=["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
        sort="FIRST_TO_START",
        max_results=_MAX_MARKETS,
    )
    metas: Dict[str, Dict[str, Any]] = {}
    for c in cats or []:
        mid = getattr(c, "market_id", None)
        if not mid:
            continue
        event = getattr(c, "event", None)
        runners: Dict[Tuple[int, float], Dict[str, Any]] = {}
        for r in getattr(c, "runners", None) or []:
            sid = getattr(r, "selection_id", None)
            if sid is None:
                continue
            hc = _num_o_none(getattr(r, "handicap", None)) or 0.0
            runners[(int(sid), hc)] = {"name": getattr(r, "runner_name", None),
                                       "ord": getattr(r, "sort_priority", None)}
        metas[str(mid)] = {"market_id": str(mid), "event_id": getattr(event, "id", None),
                           "market_name": getattr(c, "market_name", None),
                           "open_date": _open_date(c), "runners": runners}
    stato["metas"] = metas
    logger.info("[board] catalogo %s aggiornato: %d mercati", mt, len(metas))
    return stato


def _sel_ordinate(meta: Dict[str, Any], sels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _chiave(s: Dict[str, Any]) -> Any:
        info = meta["runners"].get((s.get("selection_id"), s.get("handicap") or 0.0)) or {}
        o = info.get("ord")
        return (o if isinstance(o, int) else 10 ** 6, s.get("handicap") or 0.0)
    return sorted(sels, key=_chiave)


def _riga_tipo_da_book(meta: Dict[str, Any], b: Any) -> Dict[str, Any]:
    sels = []
    for r in getattr(b, "runners", None) or []:
        sid = getattr(r, "selection_id", None)
        hc = _num_o_none(getattr(r, "handicap", None)) or 0.0
        info = meta["runners"].get((sid, hc)) or {}
        s = _selezione_da_runner(r, info.get("name"), handicap=True)
        s["handicap"] = hc
        sels.append(s)
    return {"event_id": meta["event_id"], "market_id": meta["market_id"],
            "market_name": meta["market_name"], "status": getattr(b, "status", None),
            "inplay": bool(getattr(b, "inplay", False)),
            "total_matched": getattr(b, "total_matched", None),
            "selections": _sel_ordinate(meta, sels)}


def blocchi_del_feed(payload: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """{market_id: blocco} dei mercati NON Match Odds che il feed dello scanner
    porta per l'evento (calcio: ``ou``, ``btts``, ``ht_result``; stessa ricerca
    di ``riserva_prezzi.prezzi_dalla_riga``). PURA."""
    if not isinstance(payload, dict):
        return {}
    blocchi = [payload.get(k) for k in ("btts", "ht_result")] + list(payload.get("ou") or [])
    return {str(b["market_id"]): b for b in blocchi
            if isinstance(b, dict) and b.get("market_id")}


def riga_tipo_da_blocco(meta: Dict[str, Any], blk: Dict[str, Any],
                        payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Riga ``board_mercato`` dal blocco del feed (PURA). None se il blocco non
    ha selection_id. Il feed non porta l'LTP: ``ltp`` None (non noto)."""
    sels = []
    for s in blk.get("selections") or []:
        if not isinstance(s, dict) or s.get("selection_id") is None:
            continue
        sid = int(s["selection_id"])
        info = meta["runners"].get((sid, 0.0)) or {}
        sels.append({"selection_id": sid, "name": info.get("name") or s.get("name"),
                     "handicap": 0.0, "back": s.get("back"), "lay": s.get("lay"),
                     "ltp": None, "back_size": s.get("back_size"),
                     "lay_size": s.get("lay_size")})
    if not sels:
        return None
    inplay = blk.get("inplay")
    return {"event_id": meta["event_id"], "market_id": meta["market_id"],
            "market_name": meta["market_name"], "status": blk.get("status"),
            "inplay": bool(inplay if inplay is not None else payload.get("inplay")),
            "total_matched": blk.get("total_matched"),
            "selections": _sel_ordinate(meta, sels)}


def _righe_tipo(api_client: Any, event_type_id: str, mt: str,
                payloads: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    stato = _MERCATI.get(mt)
    if stato is None or time.monotonic() - float(stato.get("catalogue_ts", 0.0)) > _CATALOGUE_TTL_SEC:
        stato = _refresh_catalogo_tipo(api_client, event_type_id, mt)
    metas: Dict[str, Dict[str, Any]] = stato["metas"]
    righe: Dict[str, Dict[str, Any]] = {}
    for mid, meta in metas.items():
        payload = payloads.get(str(meta.get("event_id")))
        blk = blocchi_del_feed(payload).get(mid)
        if blk is not None and payload is not None:
            r = riga_tipo_da_blocco(meta, blk, payload)
            if r is not None:
                righe[mid] = r
    # stessa regola del MATCH_ODDS: REST a blocchi da 25 al piu' ogni 60 s per
    # tipo (prezzi dei non coperti, volume di tutti)
    ora = time.monotonic()
    if metas and ora - float(stato.get("rest_ts", 0.0)) >= _REST_FALLBACK_PERIOD_SEC:
        stato["rest_ts"] = ora
        stato["rest_rows"] = _poll_books_rest(api_client, metas, _riga_tipo_da_book)
    rest = stato["rest_rows"]
    out: List[Dict[str, Any]] = []
    for mid in metas:
        r = righe.get(mid)
        if r is None:
            r = dict(rest[mid]) if mid in rest else None
        elif rest.get(mid) is not None and rest[mid].get("total_matched") is not None:
            r["total_matched"] = rest[mid]["total_matched"]
        if r is not None:
            out.append(r)
    return out


def _pubblica_mercati(ch: Any, api_client: Any, event_type_id: str,
                      payloads: Dict[str, Dict[str, Any]]) -> None:
    for mt in tipi_richiesti():
        try:
            righe = _righe_tipo(api_client, event_type_id, mt, payloads)
        except Exception as ex:  # noqa: BLE001 - un tipo KO non ferma gli altri
            logger.warning("[board] board_mercato %s KO: %s", mt, str(ex)[:160])
            continue
        ch.publish("board_mercato", {"market_type": mt, "rows": righe,
                                     "updated_ms": _ora_ms()})


# ---------------------------------------------------------------------------
# il giro
# ---------------------------------------------------------------------------
def intervallo_giro_s() -> float:
    """La cadenza del board (``LIVE_BOARD_POLL_SEC``, default 10 s): la stessa
    del BackgroundWorker dei due runner."""
    try:
        v = float(os.getenv("LIVE_BOARD_POLL_SEC", "10.0") or 10.0)
    except ValueError:
        v = 10.0
    return v if v > 0 else 10.0


def _giro(ch: Any, api_client: Any, event_type_id: str) -> None:
    _STATE["event_type_id"] = str(event_type_id)
    # 09/10: il canale instrada qui la richiesta di sola lettura ``board_mercato``
    setter = getattr(ch, "set_board_mercato", None)
    if setter is not None:
        setter(richiedi_mercato)
    if time.monotonic() - float(_STATE.get("catalogue_ts", 0.0)) > _CATALOGUE_TTL_SEC:
        _refresh_catalogue(api_client, event_type_id)
    if not _STATE["markets"]:
        return
    if (_STATE.get("market_types") is None
            or time.monotonic() - float(_STATE.get("types_ts", 0.0)) > _TYPES_TTL_SEC):
        try:
            _refresh_market_types(api_client, event_type_id)
        except Exception as ex:  # noqa: BLE001 - senza tipi il board resta quello di sempre
            logger.warning("[board] tipi di mercato KO: %s", str(ex)[:160])
    eventi = [str(m["event_id"]) for m in _STATE["markets"] if m.get("event_id") is not None]
    payloads = _payload_freschi(eventi)
    rows = _collect_rows(api_client, payloads, event_type_id)
    payload: Dict[str, Any] = {"rows": rows}
    tipi = _STATE.get("market_types")
    if tipi is not None:
        # mai letti (``listMarketTypes`` KO) = chiave ASSENTE (non noto), mai []
        payload["market_types"] = list(tipi)
    ch.publish("board", payload)
    _pubblica_mercati(ch, api_client, event_type_id, payloads)


def board_worker(context: dict, flumine: Any, session: Any = None, event_type_id: str = "1") -> None:
    """Entry BackgroundWorker. Mai solleva; zero costo senza desktop collegato."""
    ch = local_channel.get_channel()
    if ch is None or not ch.is_active():
        return
    api_client = getattr(session, "context_api_client", None)
    if api_client is None:
        return
    if not _LOCK_GIRO.acquire(blocking=False):
        return   # 09/10: un giro e' gia' in corso (worker di flumine o ciclo d'attesa)
    try:
        _STATE["giro_ts"] = time.monotonic()
        _giro(ch, api_client, event_type_id)
    except Exception as ex:  # noqa: BLE001 - board best-effort, riprova al giro dopo
        logger.warning("[board] poll KO: %s", str(ex)[:160])
    finally:
        _LOCK_GIRO.release()


def giro_da_parcheggiato(session: Any, event_type_id: str,
                         intervallo_s: Optional[float] = None) -> bool:
    """09/10 - il board dal CICLO D'ATTESA del runner (nessuna partita seguita:
    il framework flumine, e con lui il BackgroundWorker del board, non esiste).

    Stessa funzione, stesso stato, stessa cadenza del worker: un giro solo se
    l'ultimo giro VERO e' piu' vecchio di ``intervallo_s`` (default
    ``LIVE_BOARD_POLL_SEC``). Zero costo senza desktop collegato (``board_worker``
    esce subito). True se ha chiamato il giro. Mai solleva."""
    try:
        passo = intervallo_giro_s() if intervallo_s is None else float(intervallo_s)
        if time.monotonic() - float(_STATE.get("giro_ts", 0.0)) < passo:
            return False
        board_worker({}, None, session=session, event_type_id=event_type_id)
        return True
    except Exception as ex:  # noqa: BLE001 - il ciclo d'attesa non cade mai per il board
        logger.warning("[board] giro da parcheggiato KO: %s", str(ex)[:160])
        return False
