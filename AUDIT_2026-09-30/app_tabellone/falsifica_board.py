# Falsificazione (30/09): rimette in board_worker._best il codice VECCHIO
# (levels[0].price) e lancia i test nuovi: devono diventare ROSSI quelli con
# flumine. Ripristino dal testo salvato in memoria, sempre (finally).
import pathlib, subprocess, sys

P = pathlib.Path("Betfair/stream/board_worker.py")
orig = P.read_bytes()
NUOVO = b"""    from Betfair.safe_strategy.scanner import best_price

    return best_price(levels)"""
VECCHIO = b"""    try:
        return float(levels[0].price) if levels else None
    except Exception:  # noqa: BLE001
        return None"""
testo = orig.replace(b"\r\n", b"\n")
assert NUOVO in testo, "punto di mutazione non trovato"
try:
    P.write_bytes(testo.replace(NUOVO, VECCHIO))
    import os
    env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
               SUPABASE_KEY="x", PUNTEGGI_CANALE="0")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "Betfair/stream/tests/test_board_quote_flumine_2026_09_30.py"],
                       capture_output=True, text=True, env=env)
    print(r.stdout[-900:])
finally:
    P.write_bytes(orig)
print("ripristinato:", P.read_bytes() == orig)
