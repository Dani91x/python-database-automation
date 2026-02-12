# Betfair/tests/test_login.py
from __future__ import annotations

from Betfair.client import BetfairClient, BetfairAuthError


def main() -> None:
    try:
        c = BetfairClient()

        # 1) Login cert (Italia)
        s = c.login_cert()
        print("✅ Login Betfair OK")
        print("loginStatus:", s.login_status)
        print("sessionToken (prime 12):", s.session_token[:12] + "...")

        # 2) Verifica reale sessione su Betting API (JSON-RPC)
        res = c.list_event_types()

        if not isinstance(res, list) or len(res) == 0:
            raise RuntimeError("Risposta listEventTypes vuota o non valida.")

        first = res[0]
        if not isinstance(first, dict) or "eventType" not in first:
            raise RuntimeError("Struttura listEventTypes inattesa (manca 'eventType').")

        print("✅ Betting API OK (listEventTypes)")
        print("eventTypes trovati:", len(res))

    except BetfairAuthError as e:
        print("❌ BetfairAuthError:", e)
        raise
    except Exception as e:
        print("❌ Errore:", e)
        raise


if __name__ == "__main__":
    main()
