"""Falsificazione dei test della seconda ondata di Mike (30/09). Ogni mutazione:
copia del file in memoria, sostituzione (esattamente 1 occorrenza), pytest sui
file collegati, ripristino dalla copia e verifica sha256. Base verde nello
stesso script, prima e dopo. Uso (dalla radice del worktree):
    <python del .venv> AUDIT_2026-09-30/falsifica_mike_ondata2.py
"""
import hashlib
import os
import subprocess
import sys

W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ENV = dict(os.environ)
ENV.update({"SUPABASE_URL": "http://127.0.0.1:9", "SUPABASE_SERVICE_ROLE_KEY": "x",
            "SUPABASE_KEY": "x", "LIVE_ORDER_MODE": "LIVE", "LIVE_KILL_SWITCH": "false",
            "LIVE_RECONCILE_POLL_SEC": "5", "SAFE_PRE_KO_OU_HOURS": "1",
            "MIKE_LIVE_ENABLED": "1",
            "LIVE_MARKET_TYPES": "MATCH_ODDS,CORRECT_SCORE,HALF_TIME_SCORE"})
for v in ("SAFE_SCAN_CANALE MIKE_CANALE_POSIZIONI OMEGA_CANALE_POSIZIONI SAFE_CANALE_POSIZIONI "
          "TENNIS_BOT_CANALE SAFE_BOT_LEGGE_CANALE SAFE_BOT_SVEGLIA_CANALE OMEGA_SVEGLIA_CANALE "
          "MIKE_SVEGLIA_CANALE TENNIS_BOT_SVEGLIA_CANALE MIKE_LEGGE_CANALE OMEGA_LEGGE_CANALE "
          "PUNTEGGI_CANALE ESITI_ORDINI_CANALE MOTORE_ORDINI_CANALE SCALPER_CANALE "
          "SAFE_ORDINI_VIA_CANALE OMEGA_ORDINI_VIA_CANALE MOTORE_ORDINI_CANALE_TENNIS "
          "SAFE_TENNIS_ORDINI_VIA_CANALE").split():
    ENV[v] = "0"

T = "Betfair/mike/tests/"
FILES = [T + "test_mike_ondata2_2026_09_30.py", T + "test_mike_engine.py",
         T + "test_mike_p2_prepartita_2026_09_29.py", T + "test_mike_resting_live_2026_09_14.py",
         T + "test_mike_p1_cancello_uscite_2026_09_29.py"]

SV, EN, CE = "Betfair/mike/service.py", "Betfair/mike/engine.py", "Betfair/mike/certificazione.py"
MUT = [
    ("M1a regolamento: annulli decisi NON eseguiti", SV,
     "actions=E._cancel_live(ctx), cache=cache)", "actions=[], cache=cache)"),
    ("M1b regolamento: nessuna attesa degli esiti prima di regolare", SV,
     "        if any(l.is_live or l.needs_reconcile for l in ctx.legs):\n            if ctx.state != \"SETTLING\":",
     "        if False:\n            if ctx.state != \"SETTLING\":"),
    ("M1c regolamento: nessuna sorveglianza degli ordini", SV,
     "        if any(l.is_live or l.needs_reconcile for l in ctx.legs):\n            _sorveglia_senza_dati(",
     "        if False:\n            _sorveglia_senza_dati("),
    ("M2a fischio: la banca LAPSE si annulla di nuovo", EN,
     "            if leg.role == \"under_green\" and leg.persistence != \"PERSIST\":",
     "            if False:"),
    ("M2b fischio: anche la banca PERSIST non si annulla", EN,
     "            if leg.role == \"under_green\" and leg.persistence != \"PERSIST\":",
     "            if leg.role == \"under_green\":"),
    ("M3a reentry_time sempre in perdita", EN,
     "            return float(t[\"bloccato\"]) < 0.0", "            return True"),
    ("M3b reentry_time sempre in profitto", EN,
     "            return float(t[\"bloccato\"]) < 0.0", "            return False"),
    ("M3c G3 muto su reentry_time", CE,
     "        if bloccato is None or bloccato < 0:", "        if True:"),
    ("M4a resti non scritti nel registro", SV,
     "        _registra_resti(db, extra, d, ctx, ev[\"event_id\"])", "        pass"),
    ("M4b resti scritti a ogni emissione", SV,
     "        if firma in scritti:\n            continue", "        if False:\n            continue"),
    ("M5a B-6 esito ABBINATO non applicato", SV,
     "letto[0] in (_ESITO_SCADUTO, _ESITO_ABBINATO, _ESITO_PARZIALE)",
     "letto[0] in (_ESITO_SCADUTO, _ESITO_PARZIALE)"),
    ("M5b B-10 tetto sul rischio al miglior prezzo", EN,
     "    rischio = size * (float(q_lim) - 1.0)\n    if rischio > room + _EPS:\n        # il tetto conta il RISCHIO al prezzo limite (peggior caso), non l'importo\n        size = math.floor(room / (float(q_lim) - 1.0) * 100.0 + _EPS) / 100.0",
     "    rischio = size * (float(q_best) - 1.0)\n    if rischio > room + _EPS:\n        # il tetto conta il RISCHIO al prezzo limite (peggior caso), non l'importo\n        size = math.floor(room / (float(q_best) - 1.0) * 100.0 + _EPS) / 100.0"),
    ("M6 size = abbinato anche a 0 (live)", SV,
     "    if leg.status == \"open\":\n        # 30/09 (parita' coda/canale",
     "    if True:\n        # 30/09 (parita' coda/canale"),
]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pytest_run():
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "ignore",
                        "-o", "addopts=", "-rf", *FILES], cwd=W, env=ENV,
                       capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    falliti = sorted({ln.split("FAILED ")[1].split(" - ")[0].split("::", 1)[1]
                      for ln in out.splitlines() if ln.startswith("FAILED ")})
    riass = [ln for ln in out.splitlines() if " passed" in ln or " failed" in ln]
    return r.returncode, falliti, (riass[-1] if riass else out[-400:])


def main():
    rc, f, s = pytest_run()
    print("BASE:", rc, s, f)
    if rc != 0:
        print("BASE NON VERDE: stop")
        sys.exit(2)
    for nome, rel, old, new in MUT:
        p = os.path.join(W, rel)
        with open(p, "r", encoding="utf-8", newline="") as fh:
            src = fh.read()
        h0 = sha(p)
        if "\r\n" in src:                  # file con fine riga CRLF
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        n = src.count(old)
        if n != 1:
            print(f"{nome}: occorrenze {n} != 1, SALTATA")
            continue
        try:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src.replace(old, new))
            rc, f, s = pytest_run()
        finally:
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(src)
        assert sha(p) == h0, f"ripristino fallito su {rel}"
        esito = "ROSSA" if rc != 0 else "VERDE (sopravvissuta)"
        print(f"{nome}: {esito} | {s}")
        for x in f:
            print("     ", x)
    rc, f, s = pytest_run()
    print("BASE DOPO:", rc, s, f)


if __name__ == "__main__":
    main()
