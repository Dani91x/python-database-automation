"""Worker locale del Backtest Automatico.

Consuma la coda ``live_backtest_requests`` UNA richiesta alla volta:
  1. ``db.claim_backtest_request()``  -> riga PENDING portata a RUNNING
  2. ``run_backtest(req['params'])``   -> esegue la FlumineSimulation
  3. ``db.write_backtest_results(...)`` + ``db.set_backtest_status(..., 'DONE')``
  4. su eccezione: ``db.set_backtest_status(..., 'ERROR', str(e))``

Avvio:  ``python -m Betfair.stream.backtest.worker``
"""
from __future__ import annotations

import argparse
import logging
import time
from typing import Optional

from .. import db
from .run_backtest import run_backtest

logger = logging.getLogger(__name__)

DEFAULT_POLL_SEC: float = 5.0


def process_one() -> bool:
    """Elabora UNA richiesta se disponibile. Ritorna True se ha lavorato."""
    req = db.claim_backtest_request()
    if not req:
        return False

    request_id = req["id"]
    params = req.get("params") or {}
    logger.info("[backtest-worker] presa richiesta %s: %s", request_id, params)
    try:
        rows = run_backtest(params)
        written = db.write_backtest_results(request_id, rows)
        db.set_backtest_status(request_id, "DONE")
        logger.info(
            "[backtest-worker] richiesta %s DONE (%d righe risultato)",
            request_id,
            written,
        )
    except Exception as e:  # noqa: BLE001 - errore isolato per richiesta
        logger.exception("[backtest-worker] richiesta %s ERROR", request_id)
        db.set_backtest_status(request_id, "ERROR", str(e))
    return True


def run_forever(poll_sec: float = DEFAULT_POLL_SEC, once: bool = False) -> None:
    logger.info("[backtest-worker] avvio (poll=%.1fs, once=%s)", poll_sec, once)
    while True:
        worked = process_one()
        if once:
            break
        if not worked:
            time.sleep(poll_sec)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest Automatico worker (locale).")
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=DEFAULT_POLL_SEC,
        help="intervallo di polling quando la coda e' vuota",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="processa al piu' una richiesta e termina",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="livello di logging (DEBUG/INFO/WARNING/...)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        run_forever(poll_sec=args.poll_sec, once=args.once)
    except KeyboardInterrupt:
        logger.info("[backtest-worker] interruzione richiesta, esco.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
