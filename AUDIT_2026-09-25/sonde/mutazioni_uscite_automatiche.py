"""25/09 - FALSIFICAZIONE dell'interruttore "uscite automatiche" (Safe, Mike, scalper).

Applica UNA mutazione alla volta al codice di produzione, lancia i test nuovi
indicati, RIPRISTINA il file dalla copia in memoria (mai git checkout) e
verifica il ripristino byte per byte. Una mutazione che lascia VERDE e' un
test che non certifica.

Uso (dalla radice del repo):
    python AUDIT_2026-09-25/sonde/mutazioni_uscite_automatiche.py [prefisso ...]
"""
import os
import subprocess
import sys

WT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

MUT = [
    ("S1 Safe: il cancelletto non propone mai",
     "Betfair/safe_strategy/bot_service.py",
     "        if (not automatiche\n                and _proponi_chiusura(",
     "        if (False\n                and _proponi_chiusura(",
     "Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py"),
    ("S2 Safe: riaccese senza decadenza della proposta",
     "Betfair/safe_strategy/bot_service.py",
     "        if automatiche and isinstance(meta.get(PROPOSTA_KEY), dict):",
     "        if False and isinstance(meta.get(PROPOSTA_KEY), dict):",
     "Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py"),
    ("S3 Safe: la mappa non vince sul cancelletto storico",
     "Betfair/safe_strategy/bot_service.py",
     "        if isinstance(v, bool):\n            out[k] = v\n        elif k == \"tennis\":",
     "        if False:\n            out[k] = v\n        elif k == \"tennis\":",
     "Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py"),
    ("M1 Mike: gate sempre aperto",
     "Betfair/mike/engine.py",
     "    if uscite_automatiche(params):\n        return _decadi(",
     "    if True:\n        return _decadi(",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M2 Mike: il cap perdita partita non e' protezione",
     "Betfair/mike/engine.py",
     "MOTIVI_PROTEZIONE = (\"loss_cap\",)",
     "MOTIVI_PROTEZIONE = ()",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M3 Mike: uscita in corso non riconosciuta",
     "Betfair/mike/engine.py",
     "    if ctx.state in STATI_USCITA_IN_CORSO:\n        return True\n    ruoli",
     "    if False:\n        return True\n    ruoli",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M4 Mike: approvazione ignorata",
     "Betfair/mike/engine.py",
     "    if _approvazione_valida(ctx, chiave, snap.now):",
     "    if False:",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M5 Mike: la proposta non si persiste (campi ctx)",
     "Betfair/mike/service.py",
     "               \"uscita_proposta\", \"uscita_approvata\")",
     "               )",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M6 Mike: lo stato di chiusura resta anche bloccato",
     "Betfair/mike/engine.py",
     "        stato = ctx.state\n        upd.pop(\"close_reason\", None)",
     "        upd.pop(\"close_reason\", None)",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M7 Mike: i timer non avanzano (updates buttati)",
     "Betfair/mike/engine.py",
     "    upd = dict(d.updates)\n    stato = d.state",
     "    upd = {}\n    stato = d.state",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("M8 Mike: approvazione su chiave sbagliata accettata",
     "Betfair/mike/service.py",
     "    if not chiave or str(viva.get(\"chiave\") or \"\") != chiave:",
     "    if not chiave:",
     "Betfair/mike/tests/test_mike_uscite_automatiche_2026_09_25.py"),
    ("C1 Scalper: il target parte comunque",
     "Betfair/stream/scalper/scalper_bot.py",
     "        if not self.uscite_automatiche:\n            # 25/09 - uscite MANUALI: la chiusura a target",
     "        if False:\n            # 25/09 - uscite MANUALI: la chiusura a target",
     "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"),
    ("C2 Scalper: il maker usa la gamba opposta anche spento",
     "Betfair/stream/scalper/scalper_bot.py",
     "            if done and el is not None and self.uscite_automatiche and abs(mb - float(",
     "            if done and el is not None and abs(mb - float(",
     "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"),
    ("C3 Scalper: lo scratch parte comunque",
     "Betfair/stream/scalper/scalper_bot.py",
     "                and entry_p is not None\n                and not self.uscite_automatiche\n            ):",
     "                and entry_p is not None\n                and False\n            ):",
     "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"),
    ("C4 Scalper: la sessione non applica il valore",
     "Betfair/stream/scalper/scalper_session.py",
     "    strategy.uscite_automatiche = nuovo\n",
     "    pass\n",
     "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"),
    ("C5 Scalper: riaccendere non rimette la chiusura",
     "Betfair/stream/scalper/scalper_bot.py",
     "                    and self.uscite_automatiche and slot.entry is not None):",
     "                    and False and slot.entry is not None):",
     "Betfair/stream/tests/test_scalper_uscite_automatiche_2026_09_25.py"),
]

env = dict(os.environ, SUPABASE_URL="http://127.0.0.1:9", SUPABASE_SERVICE_ROLE_KEY="x",
           SUPABASE_KEY="x")
sel = sys.argv[1:]
for nome, rel, prima, dopo, test in MUT:
    if sel and not any(nome.startswith(s) for s in sel):
        continue
    path = os.path.join(WT, rel)
    with open(path, encoding="utf-8", newline="") as f:
        orig = f.read()
    if "\r\n" in orig:          # file con fine riga Windows: stesse ancore
        prima, dopo = prima.replace("\n", "\r\n"), dopo.replace("\n", "\r\n")
    if orig.count(prima) != 1:
        print(f"{nome}: ANCORA NON TROVATA ({orig.count(prima)})")
        continue
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig.replace(prima, dopo))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", test],
                           cwd=WT, env=env, capture_output=True, text=True, timeout=600)
        ultima = [l for l in r.stdout.splitlines() if "passed" in l or "failed" in l]
        print(f"{nome}: {'ROSSO' if r.returncode else 'VERDE (!)'} -> "
              f"{ultima[-1] if ultima else r.stdout[-200:]}")
    finally:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(orig)
    with open(path, encoding="utf-8", newline="") as f:
        assert f.read() == orig, f"RIPRISTINO FALLITO: {rel}"
print("ripristino verificato byte per byte")
