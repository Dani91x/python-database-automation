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


_MIKE_TERMINAL_STATES = ("SETTLED", "ERROR", "SKIPPED")


_MIKE_IDLE_STATES = ("WATCH", "IDLE_LIVE")
# stati delle gambe che rappresentano un IMPEGNO reale (ordine vivo o posizione)
_MIKE_LIVE_LEG_STATUS = ("pending", "pending_reconcile", "open")


def _mike_has_exposure(row: dict) -> bool:
    """True se la partita ha DAVVERO qualcosa da proteggere: uno stato operativo
    (non WATCH/IDLE_LIVE) oppure almeno una gamba con un ordine vivo o una
    posizione abbinata. H4 (review): esentare anche le partite in sola
    osservazione regalava le quote di ~10 mercati a testa a partite senza un
    euro sopra."""
    state = str(row.get("state") or "")
    if state in _MIKE_TERMINAL_STATES:
        return False
    for leg in row.get("positions") or []:
        if not isinstance(leg, dict):
            continue
        if str(leg.get("status") or "") in _MIKE_LIVE_LEG_STATUS and not leg.get("archived"):
            return True
        try:
            if float(leg.get("matched") or 0.0) > 0 and not leg.get("archived"):
                return True
        except (TypeError, ValueError):
            continue
    return state not in _MIKE_IDLE_STATES


def list_mike_followed_event_ids() -> Optional[List[str]]:
    """event_id delle partite di Mike con ESPOSIZIONE (ordini vivi o posizione).

    Servono allo scanner per esentarle dal tetto dei 20 eventi del motore
    opportunità (audit 11/09 C1): una posizione aperta senza le sue linee O/U nel
    feed è senza copertura, senza cash out e senza uscita. Le partite in sola
    osservazione (WATCH/IDLE_LIVE senza gambe) NON sono esenti: non hanno nulla
    da proteggere e peserebbero sul pool stream per niente (H4).
    None se la lettura fallisce (tabella assente = Mike mai installato)."""
    try:
        sb = get_supabase_client()
        res = (
            sb.table("mike_events")
            .select("event_id,state,positions")
            .not_.in_("state", list(_MIKE_TERMINAL_STATES))
            .execute()
        )
        return [str(r["event_id"]) for r in (getattr(res, "data", None) or [])
                if r.get("event_id") and _mike_has_exposure(r)]
    except Exception as e:  # noqa: BLE001 - best effort, mai fatale
        if not _is_missing_table(e):
            logger.warning("[safe-scan] lettura mike_events KO: %s", str(e)[:160])
        return None
