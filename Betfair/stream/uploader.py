"""Uploader post-match: file locali → Supabase (idempotente).

Flusso:
  1. legge il file punteggi locale (scores JSONL) → righe timeline + minute-map
  2. cura il file mercati locale (JSONL) → snapshot curati (con minuto stimato)
  3. upload idempotente di snapshot + timeline (delete+insert per evento)
  4. scrive live_run_log e porta live_follow a status='UPLOADED'

Eseguibile standalone per ri-curare una partita:
    python -m Betfair.stream.uploader <event_id>
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from . import db
from .config_stream import DATA_DIR, UPLOAD_CADENCE_SEC
from .curator import curate_event

logger = logging.getLogger(__name__)

# Lock PER-EVENTO: serializza upload_event sullo stesso event_id nello stesso
# processo. Chiude la race finalize_worker <-> sweep periodico (entrambi fanno
# delete+insert su live_market_snapshots: concorrenti = righe duplicate/parziali
# nel Replay). NB: e' intra-processo — con UN SOLO runner (stato voluto) basta.
_UPLOAD_LOCKS_GUARD = threading.Lock()
_UPLOAD_LOCKS: Dict[str, threading.Lock] = {}


def _event_lock(event_id: str) -> threading.Lock:
    with _UPLOAD_LOCKS_GUARD:
        lk = _UPLOAD_LOCKS.get(event_id)
        if lk is None:
            lk = threading.Lock()
            _UPLOAD_LOCKS[event_id] = lk
        return lk


def market_file(event_id: str) -> str:
    return os.path.join(DATA_DIR, event_id, f"{event_id}.jsonl")


def scores_file(event_id: str) -> str:
    return os.path.join(DATA_DIR, event_id, f"{event_id}.scores.jsonl")


def timeline_file(event_id: str) -> str:
    return os.path.join(DATA_DIR, event_id, f"{event_id}.timeline.jsonl")


def _read_timeline_events(event_id: str) -> List[Dict[str, Any]]:
    """Eventi cronologia (gol/cartellini/...) → righe live_score_timeline."""
    path = timeline_file(event_id)
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(
                {
                    "event_id": event_id,
                    "ts": ev.get("ts"),
                    "source": "betfair",
                    "minute": ev.get("minute"),
                    "score_home": None,
                    "score_away": None,
                    "event_type": ev.get("type"),
                    "payload": ev,
                }
            )
    return rows


def _read_scores(event_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Ritorna (timeline_rows_per_DB, minute_map_per_curator)."""
    path = scores_file(event_id)
    timeline_rows: List[Dict[str, Any]] = []
    minute_map: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return timeline_rows, minute_map
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            timeline_rows.append(
                {
                    "event_id": event_id,
                    "ts": rec.get("ts"),
                    "source": rec.get("source") or "betfair",
                    "minute": rec.get("minute"),
                    "score_home": rec.get("score_home"),
                    "score_away": rec.get("score_away"),
                    "event_type": rec.get("event_type"),
                    "payload": rec.get("payload"),
                }
            )
            if rec.get("ts_ms") is not None:
                minute_map.append({"ts_ms": rec["ts_ms"], "minute": rec.get("minute")})
    minute_map.sort(key=lambda x: x["ts_ms"])
    return timeline_rows, minute_map


def upload_event(event_id: str, raw_file: Optional[str] = None) -> Dict[str, Any]:
    """Cura e carica una partita. Idempotente e SERIALIZZATA per evento.

    Il lock per-evento impedisce a finalize_worker e allo sweep periodico di
    curare/caricare lo stesso event_id in parallelo (delete+insert concorrenti
    corromperebbero gli snapshot nel Replay). Vedi _event_lock.
    """
    with _event_lock(str(event_id)):
        return _upload_event_impl(event_id, raw_file)


def _upload_event_impl(event_id: str, raw_file: Optional[str] = None) -> Dict[str, Any]:
    raw = raw_file or market_file(event_id)
    if not os.path.exists(raw):
        raise FileNotFoundError(f"File grezzo mancante per {event_id}: {raw}")

    timeline_rows, minute_map = _read_scores(event_id)
    # aggiunge gli eventi cronologia (gol/cartellini) catturati da get_event_timeline
    timeline_rows = timeline_rows + _read_timeline_events(event_id)
    snapshots = curate_event(
        raw, event_id, cadence_sec=UPLOAD_CADENCE_SEC, timeline=minute_map or None
    )

    n_snap = db.upload_snapshots(event_id, snapshots)
    n_tl = db.upload_timeline(event_id, timeline_rows)

    n_markets = len({s["market_id"] for s in snapshots})
    raw_bytes = os.path.getsize(raw) if os.path.exists(raw) else None
    score_source = timeline_rows[-1]["source"] if timeline_rows else None

    db.write_run_log(
        event_id,
        {
            "raw_file_path": raw,
            "raw_bytes": raw_bytes,
            "n_markets": n_markets,
            "n_snapshots": n_snap,
            "score_source": score_source,
        },
    )
    db.set_follow_status(event_id, "UPLOADED")

    summary = {
        "event_id": event_id,
        "n_snapshots": n_snap,
        "n_timeline": n_tl,
        "n_markets": n_markets,
        "raw_bytes": raw_bytes,
    }
    logger.info("[uploader] %s caricato: %s", event_id, summary)
    return summary


def sweep_pending(min_idle_min: float = 30.0) -> List[Dict[str, Any]]:
    """RECUPERO: carica nel Replay le partite finite rimaste indietro.

    Il 02/07 due partite registrate NON sono arrivate nella sezione Replay:
    lo stream del runner era andato in ERROR (WinError 10035) e il finalize
    non e' mai scattato. Questo sweep e' la rete di sicurezza: qualunque
    live_follow non-UPLOADED con file grezzo locale FERMO da almeno
    ``min_idle_min`` minuti (= partita finita) viene curato e caricato.
    Idempotente (upload_event fa delete+insert per evento). Chiamato
    all'avvio del runner; a mano: ``python -m Betfair.stream.uploader --sweep``.
    """
    from datetime import datetime, timezone

    from db_client import get_supabase_client

    out: List[Dict[str, Any]] = []
    rows = (
        get_supabase_client().table("live_follow")
        .select("event_id,status,open_date").neq("status", "UPLOADED")
        .execute().data or []
    )
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()
    # GUARDIA (incidente 17/07): il solo "file fermo da N minuti" NON prova che
    # la partita sia finita — dopo una finestra di riavvii dell'exe il raw di un
    # match VIVO era fermo da 14', lo sweep l'ha marcato UPLOADED mentre il
    # runner lo stava ri-streamando e la UI ("In attesa dello stream…") si è
    # bloccata per sempre. Un match iniziato da meno della soglia stantia può
    # essere ancora in corso: MAI toccarlo (il recupero delle finite-presto
    # avviene comunque, solo dopo la soglia).
    stale_s = float(os.getenv("LIVE_FOLLOW_STALE_HOURS", "3")) * 3600.0
    for r in rows:
        ev = str(r["event_id"])
        od = r.get("open_date")
        if od:
            try:
                dt = datetime.fromisoformat(str(od).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if (now_dt - dt).total_seconds() < stale_s:
                    continue  # match potenzialmente ANCORA VIVO: mai lo sweep
            except ValueError:
                pass  # open_date illeggibile: si ricade sul criterio idle
        raw = market_file(ev)
        if not os.path.exists(raw):
            continue
        idle_min = (now_ts - os.path.getmtime(raw)) / 60.0
        if idle_min < min_idle_min:
            continue  # partita (forse) ancora in corso: non toccare
        try:
            summary = upload_event(ev)
            summary["recovered_from"] = r.get("status")
            out.append(summary)
            logger.info("[uploader] SWEEP: recuperato %s (era %s)", ev, r.get("status"))
        except Exception as e:  # noqa: BLE001 - un evento rotto non blocca gli altri
            logger.exception("[uploader] SWEEP: %s KO: %s", ev, e)
    return out


def _main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("uso: python -m Betfair.stream.uploader <event_id> | --sweep")
        raise SystemExit(2)
    if sys.argv[1] == "--sweep":
        print(json.dumps(sweep_pending(), indent=2))
        return
    print(json.dumps(upload_event(sys.argv[1]), indent=2))


if __name__ == "__main__":
    _main()
