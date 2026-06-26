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
from typing import Any, Dict, List, Optional, Tuple

from . import db
from .config_stream import DATA_DIR, UPLOAD_CADENCE_SEC
from .curator import curate_event

logger = logging.getLogger(__name__)


def market_file(event_id: str) -> str:
    return os.path.join(DATA_DIR, event_id, f"{event_id}.jsonl")


def scores_file(event_id: str) -> str:
    return os.path.join(DATA_DIR, event_id, f"{event_id}.scores.jsonl")


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
    """Cura e carica una partita. Idempotente. Ritorna un riepilogo."""
    raw = raw_file or market_file(event_id)
    if not os.path.exists(raw):
        raise FileNotFoundError(f"File grezzo mancante per {event_id}: {raw}")

    timeline_rows, minute_map = _read_scores(event_id)
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


def _main() -> None:
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("uso: python -m Betfair.stream.uploader <event_id>")
        raise SystemExit(2)
    print(json.dumps(upload_event(sys.argv[1]), indent=2))


if __name__ == "__main__":
    _main()
