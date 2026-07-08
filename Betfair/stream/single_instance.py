"""single_instance.py — lock di SINGOLA ISTANZA per i runner (calcio/tennis).

Perché una PORTA localhost e non un lock-file: il bind TCP è ATOMICO e il sistema
operativo lo rilascia DA SOLO alla morte del processo (crash incluso) → niente lock
stale da ripulire e niente check di PID (``os.kill(pid, 0)`` su Windows è pericoloso:
può terminare il processo). Fix incidente 2026-07-08: DUE ``Betfair.stream.runner``
attivi da un giorno = doppie connessioni Betfair + doppio processing della coda ordini.
La seconda istanza DEVE uscire subito, con un messaggio chiaro.
"""
from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)


def acquire_single_instance_lock(port: int, name: str) -> socket.socket:
    """Acquisisce il lock di istanza legando ``127.0.0.1:port``.

    Ritorna il socket (da tenere REFERENZIATO per tutta la vita del processo:
    chiuderlo o perderlo rilascia il lock). Se la porta è occupata, un'altra
    istanza è attiva → ``SystemExit`` immediato con messaggio esplicito.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", int(port)))
        s.listen(1)
    except OSError as e:
        s.close()
        raise SystemExit(
            f"[{name}] ISTANZA GIA' ATTIVA (lock 127.0.0.1:{port} occupato): esco subito. "
            f"Chiudi l'altro processo prima di rilanciare (o cambia porta via env). ({e})"
        ) from e
    logger.info("[%s] lock di singola istanza acquisito su 127.0.0.1:%d", name, port)
    return s
