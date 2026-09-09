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
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

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

# stato per-processo (un solo thread board_worker per runner)
_STATE: Dict[str, Any] = {
    "catalogue_ts": 0.0, "markets": [],
    "rest_ts": 0.0, "rest_rows": {},   # market_id → riga (ultimo poll REST)
}


def _today_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=8)          # include i LIVE anche lunghi (start nel passato)
    end = now.replace(hour=23, minute=59, second=59)
    if end <= start:
        end = start + timedelta(hours=24)
    return start.isoformat(), end.isoformat()


def _refresh_catalogue(api_client: Any, event_type_id: str) -> None:
    from betfairlightweight import filters

    frm, to = _today_window_iso()
    cats = api_client.betting.list_market_catalogue(
        filter=filters.market_filter(
            event_type_ids=[event_type_id],
            market_type_codes=["MATCH_ODDS"],
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
            "open_date": (getattr(c, "market_start_time", None) or "").isoformat()
            if hasattr(getattr(c, "market_start_time", None), "isoformat")
            else getattr(c, "market_start_time", None),
            "runners": runners,
        })
    _STATE["markets"] = [m for m in markets if m["market_id"]]
    _STATE["catalogue_ts"] = time.monotonic()
    logger.info("[board] catalogo aggiornato: %d eventi", len(_STATE["markets"]))


def _best(levels: Any) -> Optional[float]:
    try:
        return float(levels[0].price) if levels else None
    except Exception:  # noqa: BLE001
        return None


def _row_from_book(meta: Dict[str, Any], b: Any) -> Dict[str, Any]:
    selections = []
    for r in getattr(b, "runners", None) or []:
        ex = getattr(r, "ex", None)
        selections.append({
            "selection_id": getattr(r, "selection_id", None),
            "name": meta["runners"].get(getattr(r, "selection_id", None)),
            "back": _best(getattr(ex, "available_to_back", None)) if ex else None,
            "lay": _best(getattr(ex, "available_to_lay", None)) if ex else None,
            "ltp": getattr(r, "last_price_traded", None),
        })
    return {
        "event_id": meta["event_id"],
        "event_name": meta["event_name"],
        "open_date": meta["open_date"],
        "market_id": meta["market_id"],
        "status": getattr(b, "status", None),
        "inplay": bool(getattr(b, "inplay", False)),
        "total_matched": getattr(b, "total_matched", None),
        "selections": selections,
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
    }


def _poll_books_rest(api_client: Any, metas: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """listMarketBook (EX_BEST_OFFERS) SOLO dei mercati indicati → {market_id: riga}."""
    from betfairlightweight import filters

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
                rows[meta["market_id"]] = _row_from_book(meta, b)
    return rows


def _collect_rows(api_client: Any) -> List[Dict[str, Any]]:
    metas = {m["market_id"]: m for m in _STATE["markets"]}
    # 1) prezzi dal feed dello scanner (una SELECT, cache condivisa del processo)
    by_event = {str(m["event_id"]): m for m in metas.values() if m.get("event_id") is not None}
    cache = shared_cache()
    scan_rows = cache.rows_for(list(by_event.keys())) if by_event else {}
    scanner_age = cache.scanner_age_sec() if scan_rows else None
    rows: Dict[str, Dict[str, Any]] = {}
    for eid, row in scan_rows.items():
        payload = fresh_payload(row, _FEED_MAX_AGE_SEC, scanner_age_sec=scanner_age)
        meta = by_event.get(eid)
        if payload is None or meta is None:
            continue
        built = row_from_scan_payload(meta, payload)
        if built is not None:
            rows[meta["market_id"]] = built
    # 2) fallback REST LENTO per i mercati non coperti
    uncovered = {mid: m for mid, m in metas.items() if mid not in rows}
    now_mono = time.monotonic()
    if uncovered and now_mono - float(_STATE.get("rest_ts", 0.0)) >= _REST_FALLBACK_PERIOD_SEC:
        _STATE["rest_ts"] = now_mono
        _STATE["rest_rows"] = _poll_books_rest(api_client, uncovered)
    for mid in uncovered:
        cached = _STATE["rest_rows"].get(mid)
        if cached is not None:
            rows[mid] = cached
    # ordine del catalogo (per orario KO)
    return [rows[mid] for mid in metas if mid in rows]


def board_worker(context: dict, flumine: Any, session: Any = None, event_type_id: str = "1") -> None:
    """Entry BackgroundWorker. Mai solleva; zero costo senza desktop collegato."""
    ch = local_channel.get_channel()
    if ch is None or not ch.is_active():
        return
    api_client = getattr(session, "context_api_client", None)
    if api_client is None:
        return
    try:
        if time.monotonic() - float(_STATE.get("catalogue_ts", 0.0)) > _CATALOGUE_TTL_SEC:
            _refresh_catalogue(api_client, event_type_id)
        if not _STATE["markets"]:
            return
        rows = _collect_rows(api_client)
        ch.publish("board", {"rows": rows})
    except Exception as ex:  # noqa: BLE001 - board best-effort, riprova al giro dopo
        logger.warning("[board] poll KO: %s", str(ex)[:160])
