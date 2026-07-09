"""board_worker.py — BOARD del giorno per l'app desktop (quote standard realtime).

Pubblica sul CANALE LOCALE l'elenco degli eventi in programma OGGI (calcio o
tennis) con le quote principali del MATCH_ODDS (best back/lay + LTP), via REST
betfairlightweight a peso leggero (EX_BEST_OFFERS). NESSUNA scrittura DB,
NESSUNA subscription stream: è la vista "panoramica" — la profondità piena e la
registrazione partono SOLO con "Segui live" (scelta esplicita, come sempre).

COSTO ZERO quando il desktop non è collegato: senza client locali il worker
esce subito (nessuna chiamata REST).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import local_channel

logger = logging.getLogger(__name__)

_CATALOGUE_TTL_SEC = 300.0   # refresh elenco eventi del giorno
_MAX_MARKETS = 60            # cap difensivo (peso API)
_BOOK_CHUNK = 25             # mercati per singola list_market_book

# stato per-processo (un solo thread board_worker per runner)
_STATE: Dict[str, Any] = {"catalogue_ts": 0.0, "markets": []}


def _today_window_iso() -> "tuple[str, str]":
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=2)          # include gli appena iniziati
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


def _poll_books(api_client: Any) -> List[Dict[str, Any]]:
    from betfairlightweight import filters

    rows: List[Dict[str, Any]] = []
    metas = {m["market_id"]: m for m in _STATE["markets"]}
    ids = list(metas.keys())
    for i in range(0, len(ids), _BOOK_CHUNK):
        chunk = ids[i:i + _BOOK_CHUNK]
        books = api_client.betting.list_market_book(
            market_ids=chunk,
            price_projection=filters.price_projection(price_data=["EX_BEST_OFFERS"]),
        )
        for b in books or []:
            meta = metas.get(getattr(b, "market_id", None))
            if meta is None:
                continue
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
            rows.append({
                "event_id": meta["event_id"],
                "event_name": meta["event_name"],
                "open_date": meta["open_date"],
                "market_id": meta["market_id"],
                "status": getattr(b, "status", None),
                "inplay": bool(getattr(b, "inplay", False)),
                "total_matched": getattr(b, "total_matched", None),
                "selections": selections,
            })
    return rows


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
        rows = _poll_books(api_client)
        ch.publish("board", {"rows": rows})
    except Exception as ex:  # noqa: BLE001 - board best-effort, riprova al giro dopo
        logger.warning("[board] poll KO: %s", str(ex)[:160])
