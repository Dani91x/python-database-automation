"""SERVIZIO SCALPER — supervisore locale (processo SEPARATO dal runner).

ARCHITETTURA: UN PROCESSO PER PARTITA. Il supervisore polla
``scalper_control`` e per ogni riga 'requested' spawna
``python -m Betfair.stream.scalper.scalper_session <event_id>`` (che ha il
PROPRIO login Betfair e la PROPRIA istanza flumine). Due framework flumine
nello stesso processo con client condiviso producevano WinError 10035 sui
socket dello stream (visto live il 02/07): mai piu' sessioni in-process.

Il supervisore inoltre:
  * marca 'error' le righe 'running' orfane (heartbeat fermo e nessun figlio);
  * gestisce 'stopping' per sessioni senza processo (righe zombie);
  * kill-switch globale: file ``STOP_SCALPER`` nella cwd.

Avvio:  python -m Betfair.stream.scalper.scalper_service
        (oppure avvia_scalper_service.bat)
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KILL_FILE = "STOP_SCALPER"
POLL_S = 3.0
ORPHAN_HEARTBEAT_S = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self) -> None:
        from db_client import get_supabase_client
        self.sb = get_supabase_client()

    def controls(self) -> List[Dict[str, Any]]:
        r = self.sb.table("scalper_control").select("*").in_(
            "status", ["requested", "arming", "running", "stopping"]).execute()
        return r.data or []

    def set_control(self, event_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now_iso()
        self.sb.table("scalper_control").update(fields) \
            .eq("event_id", event_id).execute()


def _spawn(event_id: str) -> subprocess.Popen:
    repo_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", ".."))
    return subprocess.Popen(
        [sys.executable, "-m", "Betfair.stream.scalper.scalper_session",
         str(event_id)],
        cwd=repo_root,
    )


def _hb_age_s(row: Dict[str, Any]) -> Optional[float]:
    hb = row.get("heartbeat_at") or row.get("started_at")
    if not hb:
        return None
    try:
        t = datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds()
    except ValueError:
        return None


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    sys.path.insert(0, os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..")))
    db = Db()
    children: Dict[str, subprocess.Popen] = {}
    logger.info("[scalper-svc] supervisore avviato (un processo per partita). "
                "Kill-switch: file %s", KILL_FILE)

    while True:
        if os.path.isfile(KILL_FILE):
            logger.warning("[scalper-svc] kill-switch: attendo la chiusura "
                           "flat delle sessioni figlie e esco")
            # i figli vedono il kill-file da soli (stessa cwd) e chiudono flat
            deadline = time.time() + 60
            while children and time.time() < deadline:
                for ev in [e for e, p in children.items() if p.poll() is not None]:
                    children.pop(ev, None)
                time.sleep(2)
            for p in children.values():
                p.terminate()
            return
        try:
            # figli terminati → rimuovi dal registro
            for ev in [e for e, p in children.items() if p.poll() is not None]:
                code = children.pop(ev).returncode
                logger.info("[scalper-svc] sessione %s terminata (exit=%s)",
                            ev, code)

            for row in db.controls():
                ev = str(row["event_id"])
                status = row["status"]
                alive = ev in children and children[ev].poll() is None
                if status == "requested" and not alive:
                    children[ev] = _spawn(ev)
                    logger.info("[scalper-svc] avviata sessione %s (pid=%s, "
                                "mode=%s dry=%s stake=%s)", ev,
                                children[ev].pid, row.get("mode"),
                                row.get("dry_run"), row.get("stake"))
                elif status == "stopping" and not alive:
                    # nessun processo vivo: chiudi la riga zombie
                    db.set_control(ev, status="stopped",
                                   stopped_at=_now_iso())
                elif status in ("running", "arming") and not alive:
                    age = _hb_age_s(row)
                    if age is not None and age > ORPHAN_HEARTBEAT_S:
                        logger.warning("[scalper-svc] %s orfana (hb %.0fs, "
                                       "nessun figlio): error", ev, age)
                        db.set_control(ev, status="error",
                                       error="sessione orfana (processo morto)",
                                       stopped_at=_now_iso())
        except Exception:  # noqa: BLE001
            logger.exception("[scalper-svc] errore nel loop di polling")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
