# Safe e la catena lambda di Omega (O1): numeri PRIMA (file di HEAD) e falsificazione.
# Ogni file toccato si ripristina byte per byte in finally.
import hashlib
import os
import re
import subprocess
import sys

BS = "Betfair/safe_strategy/bot_service.py"
TB = "Betfair/safe_strategy/tests/test_bot_service.py"
NUOVO = "Betfair/safe_strategy/tests/test_safe_lambda_quote_prima_2026_09_25.py"
ESISTENTI = [TB, "Betfair/safe_strategy/tests/test_audit_2026_09_11.py",
             "Betfair/stream/tests/test_atlante_v4_forza_id_squadra_2026_09_25.py"]
ENV = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")


def h(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def pytest(files):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"] + files,
                       capture_output=True, text=True, env=ENV, timeout=900)
    coda = [x for x in r.stdout.splitlines() if re.search(r"passed|failed|error", x)]
    return coda[-1].strip() if coda else r.stdout[-200:]


def con_file(sostituzioni, files):
    orig = {p: open(p, "rb").read() for p in sostituzioni}
    try:
        for p, nuovo in sostituzioni.items():
            open(p, "wb").write(nuovo)
        return pytest(files)
    finally:
        for p, b in orig.items():
            open(p, "wb").write(b)


def main():
    prima = {p: h(p) for p in (BS, TB)}
    head = {p: subprocess.run(["git", "show", "HEAD:" + p], capture_output=True,
                              check=True).stdout for p in (BS, TB)}
    print("PRIMA (bot_service e test_bot_service di HEAD), esistenti:", con_file(head, ESISTENTI))
    print("DOPO, esistenti:", pytest(ESISTENTI))
    testo = open(BS, "rb").read().decode("utf-8")
    old = "fn(db, event_id, payload, params=_omega_params_catena_lambda())"
    assert testo.count(old) == 1
    mut = {BS: testo.replace(old, "fn(db, event_id, payload)").encode("utf-8")}
    print("S1 params tolti dalla chiamata di Safe:", con_file(mut, [NUOVO]))
    old2 = "return _oc.resolve_params({})"
    assert testo.count(old2) == 1
    mut2 = {BS: testo.replace(old2, 'return {"lambda_quote_prima": False}').encode("utf-8")}
    print("S2 Safe passa lo SPENTO invece dei params risolti:", con_file(mut2, [NUOVO]))
    dopo = {p: h(p) for p in (BS, TB)}
    print("ripristino byte per byte:", "OK" if prima == dopo else "DIVERSO")


if __name__ == "__main__":
    main()
