"""Caricamento del Replay Tennis su Supabase (service_role), IDEMPOTENTE.

Regola: una partita si puo' caricare quante volte si vuole, mai righe doppie.
  * evento e mercati: upsert sulle chiavi (``event_id``; ``event_id,market_id``);
  * snapshot: per OGNI mercato portato dal caricamento, delete di quel mercato
    dell'evento + insert (un import che porta il SET_BETTING non cancella il
    MATCH_ODDS caricato prima da un'altra cartella);
  * punteggio: delete+insert dell'evento SOLO se il caricamento porta un
    punteggio (una cartella senza sidecar non cancella quello gia' caricato);
  * conteggi dell'evento ricalcolati dai mercati che stanno DAVVERO nel DB.
Le funzioni di scrittura a blocchi sono quelle del calcio (``db.delete_event_rows``,
``db.insert_rows_resilient``: delete per PK a blocchi, insert che si riduce sul
57014), sulle tabelle del TENNIS: nessuna riga tennis nelle tabelle del calcio.

Lock per evento nello stesso processo (come ``uploader._event_lock``): import a
mano e caricamento a fine partita del runner non si sovrappongono sulla stessa
partita nello stesso processo.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db_client import get_supabase_client

from .. import db
from .convertitore import ReplayTennis

logger = logging.getLogger(__name__)

T_EVENTI = "tennis_replay_eventi"
T_MERCATI = "tennis_replay_mercati"
T_SNAPSHOT = "tennis_replay_snapshots"
T_PUNTEGGIO = "tennis_replay_punteggio"

_GUARDIA = threading.Lock()
_LOCKS: Dict[str, threading.Lock] = {}


def _lock(event_id: str) -> threading.Lock:
    with _GUARDIA:
        lk = _LOCKS.get(event_id)
        if lk is None:
            lk = threading.Lock()
            _LOCKS[event_id] = lk
        return lk


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def carica_replay(rt: ReplayTennis, *, fonte: str = "import",
                  raw_files: Optional[List[str]] = None, raw_bytes: Optional[int] = None) -> Dict[str, Any]:
    """Scrive una partita convertita. Ritorna il riepilogo (conteggi nel DB)."""
    if fonte not in ("import", "runner"):
        raise ValueError(f"fonte non valida: {fonte}")
    ev = str(rt.evento["event_id"])
    with _lock(ev):
        return _carica(rt, ev, fonte, raw_files or [], raw_bytes)


def _carica(rt: ReplayTennis, ev: str, fonte: str, raw_files: List[str],
            raw_bytes: Optional[int]) -> Dict[str, Any]:
    sb = get_supabase_client()
    # 1) evento PRIMA dei figli (chiavi esterne); anagrafica vuota non sovrascrive
    riga_ev: Dict[str, Any] = {"event_id": ev, "fonte": fonte, "valuta": "GBP",
                               "raw_files": raw_files, "raw_bytes": raw_bytes,
                               "diagnostica": rt.diagnostica, "updated_at": _ora()}
    for k in ("competition_name", "player1_name", "player2_name", "open_date"):
        if rt.evento.get(k):
            riga_ev[k] = rt.evento[k]
    db._exec_retry(sb.table(T_EVENTI).upsert(riga_ev, on_conflict="event_id"))

    # 2) catalogo dei mercati portati da questo caricamento
    if rt.mercati:
        db._exec_retry(sb.table(T_MERCATI).upsert(
            [dict(m, event_id=ev) for m in rt.mercati], on_conflict="event_id,market_id"))

    # 3) snapshot, mercato per mercato
    n_snap = 0
    for m in rt.mercati:
        mid = m["market_id"]
        righe = [r for r in rt.snapshot if r["market_id"] == mid]
        db.delete_event_rows(T_SNAPSHOT, ev, market_id=mid)
        n_snap += db.insert_rows_resilient(T_SNAPSHOT, righe)

    # 4) punteggio (solo se portato)
    n_score: Optional[int] = None
    if rt.punteggio:
        db.delete_event_rows(T_PUNTEGGIO, ev)
        n_score = db.insert_rows_resilient(T_PUNTEGGIO, rt.punteggio)

    # 5) conteggi dell'evento dai mercati nel DB (anche quelli di import precedenti)
    nel_db = (sb.table(T_MERCATI).select("market_id,n_updates,ts_min,ts_max")
              .eq("event_id", ev).execute().data or [])
    agg: Dict[str, Any] = {
        "n_markets": len(nel_db),
        "n_snapshots": sum(int(r.get("n_updates") or 0) for r in nel_db),
        "ts_min": min((r["ts_min"] for r in nel_db if r.get("ts_min")), default=None),
        "ts_max": max((r["ts_max"] for r in nel_db if r.get("ts_max")), default=None),
        "updated_at": _ora(),
    }
    if n_score is not None:
        agg["n_score"] = n_score
    db._exec_retry(sb.table(T_EVENTI).update(agg).eq("event_id", ev))
    riepilogo = {"event_id": ev, "fonte": fonte, "snapshot_scritti": n_snap,
                 "punteggi_scritti": n_score or 0, **{k: agg[k] for k in ("n_markets", "n_snapshots")}}
    logger.info("[replay-tennis] %s caricato: %s", ev, riepilogo)
    return riepilogo
