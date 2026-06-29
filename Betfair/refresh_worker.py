"""
refresh_worker.py — worker che processa la coda ``betfair_refresh_requests``.

Rende "Aggiorna quote" mediato dal DATABASE (come lo stream): il frontend mette una
richiesta in coda (RPC request_betfair_refresh) e questo worker — che gira sul PC
dentro start_order_server.py (aggiorna_quote_betfair.bat) — la esegue chiamando
``refresh_fixture_odds`` e scrive l'esito nella riga. Così le quote si aggiornano da
QUALUNQUE origine (anche dal sito online) senza chiamate dirette browser→PC.

NESSUN ordine reale qui: solo aggiornamento quote.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# intervallo di polling della coda (secondi)
QUEUE_POLL_SEC: float = float(os.getenv("LIVE_REFRESH_QUEUE_POLL_SEC", "2"))
# quante richieste processare al massimo per ciclo
QUEUE_BATCH: int = int(os.getenv("LIVE_REFRESH_QUEUE_BATCH", "5"))

_TABLE = "betfair_refresh_requests"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _process_once(sb: Any) -> int:
    """Processa fino a QUEUE_BATCH richieste 'pending'. Ritorna quante ne ha gestite."""
    rows = (
        sb.table(_TABLE)
        .select("id, fixture_id")
        .eq("status", "pending")
        .order("id")
        .limit(QUEUE_BATCH)
        .execute()
        .data
        or []
    )
    if not rows:
        return 0

    # import lazy: il piazzamento/refresh tirano dentro il client Betfair solo qui.
    from Betfair.odds_refresh import refresh_fixture_odds, BetfairLimitHit

    handled = 0
    for r in rows:
        rid = r["id"]
        fid = r.get("fixture_id")
        try:
            result = refresh_fixture_odds(int(fid))
            sb.table(_TABLE).update({
                "status": "done",
                "result": result,
                "error": None,
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        except BetfairLimitHit as ex:
            sb.table(_TABLE).update({
                "status": "error",
                "error": ("limite Betfair: " + str(ex))[:300],
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        except Exception as ex:  # noqa: BLE001 - l'errore va scritto nella riga, worker vivo
            logger.exception("[refresh-queue] richiesta %s (fixture %s) fallita", rid, fid)
            sb.table(_TABLE).update({
                "status": "error",
                "error": str(ex)[:300],
                "processed_at": _now_iso(),
            }).eq("id", rid).execute()
        handled += 1
    return handled


def _loop() -> None:
    from db_client import get_supabase_client
    sb = get_supabase_client()
    logger.info("[refresh-queue] worker avviato (poll %.1fs, batch %d).", QUEUE_POLL_SEC, QUEUE_BATCH)
    while True:
        try:
            _process_once(sb)
        except Exception as ex:  # noqa: BLE001 - errore di coda (es. DB momentaneo): non morire
            logger.warning("[refresh-queue] ciclo KO: %s", str(ex)[:160])
        time.sleep(QUEUE_POLL_SEC)


def start_refresh_worker():
    """Avvia il worker della coda in un thread daemon. Best-effort: non deve mai
    far cadere il processo che lo ospita."""
    thread = threading.Thread(target=_loop, name="refresh-queue", daemon=True)
    thread.start()
    return thread
