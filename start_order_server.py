"""
start_order_server.py — avvia SOLO il server HTTP locale (quote + ordini) per
uso/test PRE-MATCH, indipendente dallo stream live.

Espone su http://127.0.0.1:8787:
  POST /refresh-odds  → aggiorna le quote Betfair di una fixture
  POST /place-order   → piazza un ORDINE REALE (soldi veri)

Tieni questa finestra APERTA mentre usi i pulsanti "Aggiorna quote" / "Invia
Giocate" nella web-app. Ctrl+C per fermare.

È l'UNICO host dell'endpoint quote/ordini (8787): il runner stream
(`python -m Betfair.stream.runner`, stream_api.bat) NON lo ospita, così i due
possono girare INSIEME senza contendersi la porta. Per operare serve sempre questo
server attivo; lo stream è un processo separato e opzionale.
"""
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from Betfair.stream.odds_http import start_odds_http_server


def main() -> None:
    srv = start_odds_http_server()
    if srv is None:
        raise SystemExit("Server non avviato: porta 8787 occupata? (forse il runner è già attivo)")
    print("Server quote/ordini ATTIVO su http://127.0.0.1:8787 — Ctrl+C per fermare.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nArresto richiesto.")


if __name__ == "__main__":
    main()
