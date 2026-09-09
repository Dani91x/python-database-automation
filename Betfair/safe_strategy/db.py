"""db.py — scritture Supabase dello scanner Safe Strategy (service_role).

Pattern del repo (Betfair/stream/db.py): upsert IDEMPOTENTI, best-effort con
log; se la migrazione safe_strategy_scan.sql non è applicata il servizio NON
muore — warning una-tantum e si continua (modalità di fatto dry).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

logger = logging.getLogger(__name__)

_MISSING_TABLE_WARNED = False


def _warn_missing_table(exc: Exception) -> None:
    global _MISSING_TABLE_WARNED  # noqa: PLW0603 - log una-tantum
    if not _MISSING_TABLE_WARNED:
        _MISSING_TABLE_WARNED = True
        logger.warning(
            "[safe-scan] tabella safe_strategy_scan non disponibile: migrazione "
            "migrations/safe_strategy_scan.sql non applicata? Lo scanner continua "
            "senza scrivere (il frontend non vedrà nulla finché non la applichi). "
            "Dettaglio: %s",
            str(exc)[:160],
        )


def _is_missing_table(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "does not exist" in msg or "42p01" in msg or "pgrst205" in msg or "could not find" in msg


def list_scan_event_ids() -> Optional[List[str]]:
    """event_id presenti in tabella (per la pulizia delle righe orfane di
    istanze precedenti); None se la lettura fallisce."""
    sb = get_supabase_client()
    try:
        res = sb.table("safe_strategy_scan").select("event_id").execute()
        return [str(r["event_id"]) for r in (getattr(res, "data", None) or []) if r.get("event_id")]
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] lettura event_id KO: %s", str(e)[:160])
        return None


def upsert_scan_rows(rows: List[Dict[str, Any]]) -> bool:
    """Upsert delle righe evento (on_conflict event_id). True se scritte."""
    if not rows:
        return True
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").upsert(rows, on_conflict="event_id").execute()
        return True
    except Exception as e:  # noqa: BLE001 - best-effort, mai uccidere lo scanner
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert righe KO: %s", str(e)[:160])
        return False


def delete_scan_rows(event_ids: List[str]) -> None:
    if not event_ids:
        return
    sb = get_supabase_client()
    try:
        sb.table("safe_strategy_scan").delete().in_("event_id", event_ids).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] delete righe KO: %s", str(e)[:160])


def upsert_status(payload: Dict[str, Any]) -> None:
    sb = get_supabase_client()
    try:
        # updated_at ESPLICITO (bug visto dal vivo 09/09): il DEFAULT now() vale
        # solo all'INSERT — l'upsert aggiornava il payload ma lasciava la data
        # della prima riga (02/09) → la UI diceva "scanner non attivo, heartbeat
        # 575530s fa" con lo scanner vivo.
        sb.table("safe_strategy_status").upsert(
            {"id": "scanner", "payload": payload, "updated_at": _now_iso()}, on_conflict="id"
        ).execute()
    except Exception as e:  # noqa: BLE001
        if _is_missing_table(e):
            _warn_missing_table(e)
        else:
            logger.warning("[safe-scan] upsert status KO: %s", str(e)[:160])
