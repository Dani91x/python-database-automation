"""xhedge_worker.py — BackgroundWorker del RUNNER: calcola l'analisi hedging CROSS-MARKET
per ogni evento attivo (trading/xhedge) e la scrive in ``betfair_live_xhedge`` per la UI.

Per ogni evento: costruisce i metadati mercato dal catalogo (session.markets_by_event),
legge le posizioni MATCHED dallo specchio ``betfair_live_orders``, ricava le quote back del
Correct Score dai book in cache (recorder) e produce { sintesi P&L per-scoreline, suggerimento
di copertura }. SOLA LETTURA lato Betfair (nessun ordine). Best-effort: un errore su un evento
non ferma il runner. Testabile a unità: session/recorder/coda mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from . import live_order_worker as low
from .trading import xhedge

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_meta_and_cs(markets: list) -> "Tuple[Dict[str, Any], str, Dict[int, Tuple[int, int]]]":
    """(market_meta, cs_market_id, {cs_selection_id: (h,a)}) dal catalogo dell'evento."""
    meta: Dict[str, Any] = {}
    cs_market_id = ""
    cs_map: Dict[int, Tuple[int, int]] = {}
    for m in markets:
        mid = m["market_id"]
        sels = {
            int(s["selection_id"]): {"name": s.get("name"), "sort_priority": s.get("sort_priority")}
            for s in m.get("selections", [])
        }
        meta[mid] = {"market_type": m.get("market_type"), "selections": sels}
        if m.get("market_type") == "CORRECT_SCORE":
            cs_market_id = mid
            for s in m.get("selections", []):
                canon = xhedge.canonical_selection("CORRECT_SCORE", s.get("name"), s.get("sort_priority"))
                if canon:
                    try:
                        h, a = (int(v) for v in canon.split("-"))
                        cs_map[int(s["selection_id"])] = (h, a)
                    except (ValueError, TypeError):
                        pass
    return meta, cs_market_id, cs_map


def _cs_back_odds(session: Any, cs_market_id: str, cs_map: Dict[int, Tuple[int, int]]) -> Dict[Tuple[int, int], float]:
    """Miglior quota BACK per scoreline dal book Correct Score in cache (recorder)."""
    odds: Dict[Tuple[int, int], float] = {}
    if not cs_market_id or getattr(session, "recorder", None) is None:
        return odds
    book = (session.recorder.latest_books() or {}).get(cs_market_id)
    if not book:
        return odds
    runners = book.get("runners") or {}
    for sel, score in cs_map.items():
        r = runners.get(str(sel)) or runners.get(sel)
        if not r:
            continue
        b = r.get("b") or []
        if b and b[0] and b[0][0]:
            try:
                odds[score] = float(b[0][0])
            except (TypeError, ValueError):
                pass
    return odds


def _process_once(sb: Any, session: Any) -> int:
    mode = low._live_order_mode().lower()
    if mode not in ("paper", "live"):
        return 0
    handled = 0
    finished = getattr(session, "finished_events", set()) or set()
    for event_id, markets in list(getattr(session, "markets_by_event", {}).items()):
        if event_id in finished:
            continue
        try:
            meta, cs_mid, cs_map = _market_meta_and_cs(markets)
            rows = (
                sb.table("betfair_live_orders").select("*")
                .eq("event_id", event_id).eq("mode", mode).execute().data or []
            )
            orders = [r for r in rows if float(r.get("size_matched") or 0) > 0]
            if not orders:
                continue
            cs_odds = _cs_back_odds(session, cs_mid, cs_map)
            analysis = xhedge.compute_xhedge(orders, meta, cs_odds)
            sb.table("betfair_live_xhedge").upsert(
                {"event_id": event_id, "mode": mode, "analysis": analysis, "updated_at": _now_iso()},
                on_conflict="event_id,mode",
            ).execute()
            handled += 1
        except Exception as ex:  # noqa: BLE001 - un evento KO non ferma gli altri né il runner
            logger.warning("[xhedge] evento %s KO: %s", event_id, str(ex)[:160])
    return handled


def xhedge_worker(context: dict, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """BackgroundWorker flumine. Aggiunto SOLO in PAPER/LIVE (vedi runner). Non solleva MAI."""
    if session is None:
        return
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[xhedge] supabase non disponibile: %s", str(ex)[:160])
        return
    try:
        _process_once(sb, session)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[xhedge] ciclo KO: %s", str(ex)[:200])
