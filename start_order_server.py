"""
start_order_server.py — avvia SOLO il server HTTP locale (quote + ordini) per
uso/test PRE-MATCH, indipendente dallo stream live.

Fa DUE cose:
  1) HTTP locale http://127.0.0.1:8787 — POST /place-order (ORDINE REALE) e
     POST /refresh-odds (refresh diretto), usati quando la web-app gira in locale.
  2) Worker della CODA "Aggiorna quote" (betfair_refresh_requests): processa le
     richieste messe dal frontend via DB → le quote si aggiornano ANCHE dal sito
     online, come lo stream, senza chiamate dirette browser→PC.

Tieni questa finestra APERTA mentre usi "Aggiorna quote" / "Invia Giocate".
Ctrl+C per fermare.

NB: NON ospita lo stream. Il runner (`python -m Betfair.stream.runner`,
stream_api.bat) è un processo separato e i due possono girare INSIEME (non si
contendono la porta).
"""
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from Betfair.stream.odds_http import start_odds_http_server
from Betfair.refresh_worker import start_refresh_worker
from Betfair.order_worker import start_order_worker


def main() -> None:
    srv = start_odds_http_server()
    if srv is None:
        raise SystemExit("Server non avviato: porta 8787 occupata? (forse il runner è già attivo)")

    # Worker delle code DB-mediated ("Aggiorna quote" e "Invia Giocate"): rendono
    # quelle azioni utilizzabili anche dal sito online. Best-effort: un loro errore
    # non deve impedire l'uso del server HTTP locale.
    log = logging.getLogger(__name__)
    try:
        start_refresh_worker()
    except Exception as e:  # noqa: BLE001
        log.warning("worker coda refresh non avviato: %s", e)
    try:
        start_order_worker()
    except Exception as e:  # noqa: BLE001
        log.warning("worker coda ordini non avviato: %s", e)

    print("Server quote/ordini ATTIVO su http://127.0.0.1:8787 (+ worker code quote/ordini) — Ctrl+C per fermare.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nArresto richiesto.")


if __name__ == "__main__":
    main()
