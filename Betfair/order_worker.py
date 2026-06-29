"""
order_worker.py — worker che processa la coda ``betfair_order_requests``
PIAZZANDO ORDINI REALI (soldi veri). Rende "Invia Giocate" mediato dal DATABASE
(come lo stream): il frontend accoda l'ordine, questo worker — sul PC, dentro
start_order_server.py (aggiorna_quote_betfair.bat) — lo esegue e scrive l'esito.

MONEY-CRITICAL. Garanzie anti-doppio-ordine:
  * CLAIM atomico pending→processing: ogni riga è eseguita UNA sola volta.
  * customerRef Betfair DETERMINISTICO (awlq<id>): un eventuale retry interno usa
    lo stesso ref → de-dup 60s lato Betfair.
  * NON ri-processa righe 'processing'/'done'/'error': in caso di crash a metà,
    la riga resta 'processing' (ordine forse piazzato) e va riconciliata a mano —
    MAI ripiazzata in automatico (no doppio addebito).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

QUEUE_POLL_SEC: float = float(os.getenv("LIVE_ORDER_QUEUE_POLL_SEC", "2"))
QUEUE_BATCH: int = int(os.getenv("LIVE_ORDER_QUEUE_BATCH", "3"))

_TABLE = "betfair_order_requests"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _claim(sb: Any, rid: int) -> bool:
    """CLAIM atomico: pending → processing. True se questa chiamata l'ha preso."""
    claimed = (
        sb.table(_TABLE)
        .update({"status": "processing"})
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
        .data
        or []
    )
    return len(claimed) > 0


def _process_once(sb: Any) -> int:
    rows = (
        sb.table(_TABLE)
        .select("*")
        .eq("status", "pending")
        .order("id")
        .limit(QUEUE_BATCH)
        .execute()
        .data
        or []
    )
    if not rows:
        return 0

    from Betfair.order_exec import place_order, OrderBusy
    from Betfair.odds_refresh import BetfairLimitHit

    handled = 0
    for r in rows:
        rid = r["id"]
        # claim: se un altro l'ha già preso (o non è più pending), salta.
        if not _claim(sb, rid):
            continue

        # customerRef DETERMINISTICO legato alla richiesta → de-dup Betfair su retry.
        cust_ref = ("awlq" + str(rid))[:32]
        try:
            result = place_order(
                int(r["fixture_id"]),
                str(r["market"]), str(r["selection"]), str(r["side"]),
                float(r["price"]),
                size=_f(r.get("size")),
                liability=_f(r.get("liability")),
                persistence=str(r.get("persistence") or "LAPSE"),
                fill_or_kill=bool(r.get("fill_or_kill")),
                min_fill_size=_f(r.get("min_fill_size")),
                max_stake=_f(r.get("max_stake")),
                customer_ref=cust_ref,
                sb=sb,
            )
            sb.table(_TABLE).update({
                "status": "done",
                "result": result,
                "error": None,
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        except (BetfairLimitHit, OrderBusy) as ex:
            sb.table(_TABLE).update({
                "status": "error",
                "error": str(ex)[:300],
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        except ValueError as ex:
            # validazione (stake/tick/mercato non disponibile, ...): nessun ordine piazzato.
            sb.table(_TABLE).update({
                "status": "error",
                "error": str(ex)[:300],
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        except Exception as ex:  # noqa: BLE001 - l'errore va scritto nella riga, worker vivo
            logger.exception("[order-queue] richiesta %s fallita", rid)
            sb.table(_TABLE).update({
                "status": "error",
                "error": str(ex)[:300],
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        handled += 1
    return handled


def _alert_stuck(sb: Any) -> None:
    """Segnala (ERROR nel log) ordini rimasti in 'processing' da troppo tempo: forse
    piazzati ma non confermati (crash worker) → vanno riconciliati A MANO, mai
    ripiazzati. Solo allerta, nessuna azione automatica."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        stuck = (
            sb.table(_TABLE).select("id, fixture_id")
            .eq("status", "processing").lt("requested_at", cutoff)
            .execute().data or []
        )
        if stuck:
            logger.error("[order-queue] ATTENZIONE: %d ordini in 'processing' da >5min "
                         "(forse piazzati ma non confermati, riconciliare a mano): %s",
                         len(stuck), [r["id"] for r in stuck])
    except Exception:  # noqa: BLE001 - allerta best-effort
        pass


def _loop() -> None:
    from db_client import get_supabase_client
    sb = get_supabase_client()
    logger.info("[order-queue] worker avviato (poll %.1fs, batch %d).", QUEUE_POLL_SEC, QUEUE_BATCH)
    _alert_stuck(sb)
    while True:
        try:
            _process_once(sb)
        except Exception as ex:  # noqa: BLE001 - errore di coda momentaneo: non morire
            logger.warning("[order-queue] ciclo KO: %s", str(ex)[:160])
        time.sleep(QUEUE_POLL_SEC)


def start_order_worker():
    """Avvia il worker degli ordini in un thread daemon. Best-effort."""
    thread = threading.Thread(target=_loop, name="order-queue", daemon=True)
    thread.start()
    return thread
