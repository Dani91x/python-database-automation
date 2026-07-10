"""tennis_bot_service.py — supervisore che tiene COERENTI i bot col runner tennis.

Il runner (``tennis_runner``) OSPITA i bot armati sullo stream unico e li
arma/disarma via ``bot_control_worker`` (restart del framework). Perché un bot possa
essere ospitato, però, il suo evento deve essere SEGUITO (riga in ``tennis_live_follow``,
così la subscription viene aperta). Questo servizio è il ponte:

  * poll di ``tennis_bot_control`` per righe ``requested``/``arming``/``armed``/``running``
    (bot da attivare) e ``stopping`` (da fermare);
  * per ogni evento con un bot attivo ma SENZA follow, registra il follow risolvendo
    market_id + giocatori da ``tennis_markets`` (nessun REST Betfair extra) → il runner
    lo prende in carico e aggancia il bot allo STESSO stream;
  * infine avvia/riavvia il runner (che fa l'hosting vero).

Scrive SOLO tabelle ``tennis_*``. Consistente con l'hosting in-process del runner.

Uso:
  python -m Betfair.stream.tennis_live.tennis_bot_service
  python -m Betfair.stream.tennis_live.tennis_bot_service --once   # solo ensure-follows
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
import time
from typing import Any, Dict, List

from ..single_instance import acquire_single_instance_lock
from . import tennis_db

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ["requested", "arming", "armed", "running"]
ENSURE_POLL_SEC = 15.0
# Backoff quando il runner torna senza streammare nulla (nessun follow/mercato): evita un
# loop stretto di re-login Betfair (build_client(login=True) ad ogni giro → TOO_MANY_REQUESTS).
IDLE_BACKOFF_SEC = float(os.getenv("TENNIS_BOT_SVC_IDLE_BACKOFF_SEC", "30.0"))


def _followed_event_ids() -> set:
    return {f["event_id"] for f in tennis_db.list_pending_tennis_follows()}


def _market_row_for(sb: Any, event_id: str) -> Dict[str, Any] | None:
    """Riga tennis_markets più recente dell'evento (per market_id + giocatori)."""
    try:
        resp = (
            sb.table("tennis_markets")
            .select("event_id,market_id,player1,player2,competition_name,open_date")
            .eq("event_id", event_id)
            .order("run_date", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("[tennis-bot-svc] tennis_markets KO %s: %s", event_id, e)
        return None
    rows = getattr(resp, "data", None) or []
    return rows[0] if rows else None


def ensure_follows_for_bots() -> List[str]:
    """Registra un follow per ogni evento con bot attivo ma non ancora seguito.

    Ritorna gli event_id per cui è stato creato un nuovo follow.
    """
    controls = tennis_db.list_tennis_bot_controls(statuses=_ACTIVE_STATUSES)
    if not controls:
        return []
    followed = _followed_event_ids()
    sb = tennis_db.get_tennis_client()
    created: List[str] = []
    for c in controls:
        event_id = c.get("event_id")
        if not event_id or event_id in followed:
            continue
        mrow = _market_row_for(sb, event_id)
        if not mrow or not mrow.get("market_id"):
            logger.warning("[tennis-bot-svc] bot su %s ma nessun market noto (aggiorna quote).", event_id)
            continue
        p1 = (mrow.get("player1") or {})
        p2 = (mrow.get("player2") or {})
        tennis_db.register_tennis_follow(
            event_id=event_id,
            market_id=mrow["market_id"],
            player1_name=str(p1.get("name") or "P1"),
            player2_name=str(p2.get("name") or "P2"),
            open_date=mrow.get("open_date"),
            competition_name=mrow.get("competition_name"),
            status="PENDING",
        )
        followed.add(event_id)
        created.append(event_id)
        logger.info("[tennis-bot-svc] follow creato per evento con bot: %s", event_id)
    return created


def _ensure_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            ensure_follows_for_bots()
        except Exception as e:  # noqa: BLE001
            logger.warning("[tennis-bot-svc] ensure loop KO: %s", e)
        stop.wait(ENSURE_POLL_SEC)


def run() -> None:
    """Avvia il ponte follow + il runner tennis (che ospita i bot).

    FIX CRITICAL doppio runner (2026-07-10): l'app desktop avvia SIA il watchdog
    (→ ``tennis_runner``) SIA questo servizio, e ``setup_and_run()`` ospita i bot
    in-process → due framework con GLI STESSI bot = stake DOPPIO. Prima di
    ospitare si acquisisce il lock di SINGOLA ISTANZA del runner (stessa porta di
    ``tennis_runner``): se è occupato, un runner è già attivo e ospita lui i bot
    → in questo ciclo si fa SOLO ensure_follows_for_bots() e si riprova al giro
    dopo. Se acquisito, il lock resta vivo per tutta la durata dell'hosting.
    """
    from .tennis_runner import setup_and_run

    ensure_follows_for_bots()
    lock_port = int(os.getenv("TENNIS_RUNNER_LOCK_PORT", "47312"))
    try:
        lock = acquire_single_instance_lock(lock_port, "tennis-runner")
    except SystemExit:
        logger.info(
            "[tennis-bot-svc] runner tennis GIÀ attivo (lock 127.0.0.1:%d): "
            "hosting saltato in questo ciclo (solo ensure-follows), riprovo al giro dopo.",
            lock_port,
        )
        return
    stop = threading.Event()
    t = threading.Thread(target=_ensure_loop, args=(stop,), daemon=True, name="tennis-ensure-follows")
    t.start()
    try:
        setup_and_run()
    finally:
        stop.set()
        try:
            lock.close()  # rilascia il lock: il runner watchdog può subentrare
        except OSError:
            pass


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Supervisore bot tennis (follow + hosting)")
    ap.add_argument("--once", action="store_true", help="solo ensure-follows, poi esci")
    args = ap.parse_args()
    if args.once:
        created = ensure_follows_for_bots()
        logger.info("[tennis-bot-svc] follow creati: %s", created)
        return
    while True:
        try:
            run()
        except KeyboardInterrupt:
            logger.info("[tennis-bot-svc] interrotto.")
            break
        except Exception as e:  # noqa: BLE001
            logger.exception("[tennis-bot-svc] runner caduto: %s — riparto tra 10s", e)
            time.sleep(10.0)
            continue
        # run() è tornato SENZA streammare (nessun follow/mercato): backoff prima di ritentare
        # per non re-loggarsi a Betfair in un loop stretto (#11).
        logger.info("[tennis-bot-svc] runner tornato senza stream: attendo %ss.", IDLE_BACKOFF_SEC)
        time.sleep(IDLE_BACKOFF_SEC)


if __name__ == "__main__":
    _main()
