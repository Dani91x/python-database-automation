"""falsifica_stallo.py - falsificazione dei test R-STREAM-1 / F-9 / watchdog (26/09).

Per ogni mutazione: rimette il bug (o una variante) nel file VERO, lancia i
test indicati, RIPRISTINA il file dal contenuto letto prima (try/finally) e
verifica lo sha256. Atteso: ogni mutazione ROSSA. In coda: tutti i file con lo
sha di partenza. NON interrompere lo script (lascerebbe una mutazione): nessun
timeout, lo si lascia finire.

Uso (dalla radice del worktree/repo):
    SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x \
        python AUDIT_2026-09-26/falsifica_stallo.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
T_STALLO = "Betfair/stream/tests/test_stream_stallo_2026_09_26.py"
T_MODO = "Betfair/stream/tests/test_annuncio_modo_2026_09_26.py"
T_WD = "Betfair/stream/tests/test_watchdog_nome_modulo_2026_09_26.py"

RUNNER = "Betfair/stream/runner.py"
LIFE = "Betfair/stream/runner_lifecycle.py"
RAWL = "Betfair/stream/raw_listener.py"
TREC = "Betfair/stream/tennis_live/tennis_recorder.py"
TRUN = "Betfair/stream/tennis_live/tennis_runner.py"
WD = "Betfair/stream/watchdog.py"

# (nome, file, vecchio, nuovo, test)
MUTAZIONI = [
    ("M1 cancello storico enabled+market_to_event", RUNNER,
     "        if _mercati_sottoscritti(session) > 0:",
     '        if h.get("enabled") and session.market_to_event:', T_STALLO),
    ("M2 battito calcio solo a tee acceso", RAWL,
     "            tipo = classifica_messaggio_stream(raw_data)\n            if tipo is not None:",
     "            tipo = None\n            if tipo is not None:", T_STALLO),
    ("M3 battito tennis solo con registrazioni", TREC,
     "        tipo = classifica_messaggio_stream(raw_data)",
     "        tipo = None", T_STALLO),
    ("M4 escalation calcio mai chiamata", RUNNER,
     "                               and _escalation_stallo(flumine, session,",
     "                               and False and _escalation_stallo(flumine, session,",
     T_STALLO),
    ("M5 escalation calcio ignora i blocker", RUNNER,
     "    if blocker is not None:\n        if (now_mono - float(getattr(session, \"stallo_escala_alert_mono\"",
     "    if False:\n        if (now_mono - float(getattr(session, \"stallo_escala_alert_mono\"",
     T_STALLO),
    ("M6 verdetto senza 'nessun dato dopo il rebuild'", LIFE,
     "    if not dati_dopo_rebuild:\n        return VERDETTO_ESCALA\n", "", T_STALLO),
    ("M7 verdetto senza finestra d'attesa", LIFE,
     "    if secondi_dal_rebuild < finestra_s:\n        return VERDETTO_ATTENDI\n", "", T_STALLO),
    ("M8 verdetto ignora lo stallo effettivo", LIFE,
     "    if stall_s is not None and stall_s >= finestra_s:\n        return VERDETTO_ESCALA\n",
     "", T_STALLO),
    ("M9 tennis non escala", TRUN,
     "                _escala_stallo_tennis(flumine, session, stall_s, now_mono)\n",
     "", T_STALLO),
    ("M10 tennis esce anche con bot non flat", TRUN,
     "    blocker = _tennis_blocker_uscita_stallo(flumine, session)\n",
     "    blocker = None\n", T_STALLO),
    ("M11 tennis nessuna ricostruzione per stallo", TRUN,
     "        if not stall_restart_due(stall_s, _T_STALL_RESTART_SEC, session.stall_last_restart,",
     "        if True or not stall_restart_due(stall_s, _T_STALL_RESTART_SEC, session.stall_last_restart,",
     T_STALLO),
    ("M12 rete = ogni OSError", LIFE,
     "    tipi: tuple = (ConnectionError, TimeoutError, socket.gaierror, socket.herror)",
     "    tipi: tuple = (OSError,)", T_STALLO),
    ("M13 _attendi_se_rete maschera tutto", RUNNER,
     "    if not e_errore_di_rete(exc):\n        raise exc",
     "    if False:\n        raise exc", T_STALLO),
    ("M14 calcio: finally chiude i follow anche su riavvio per stallo", RUNNER,
     '        _eventi_da_chiudere = ([] if getattr(session, "riavvio_per_stallo", False)',
     '        _eventi_da_chiudere = ([] if False', T_STALLO),
    ("M15 tennis: lettura follow senza guardia di rete", TRUN,
     "                if not e_errore_di_rete(e):\n                    raise",
     "                if True:\n                    raise", T_STALLO),
    ("M16 F-9 annuncia il tetto", RUNNER,
     "    eff = (effettivo or tetto).strip().upper()",
     "    eff = tetto", T_MODO),
    ("M17 F-9 CRITICAL sul tetto", RUNNER,
     '    level = "CRITICAL" if eff == "LIVE" else "INFO"',
     '    level = "CRITICAL" if tetto == "LIVE" else "INFO"', T_MODO),
    ("M18 F-9 chiamante senza effettivo", RUNNER,
     "_MO.modo_effettivo(modo_avvio, _MO.valore_db())",
     "modo_avvio", T_MODO),
    ("M19 watchdog senza nome del modulo", WD,
     "        base_msg = messaggio_crash(target, rc, uptime)",
     '        base_msg = f"RUNNER CRASHATO: exit code {rc}, uptime {uptime:.0f}s."', T_WD),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pytest(test: str) -> int:
    env = dict(os.environ)
    env.setdefault("SUPABASE_URL", "http://127.0.0.1:9")
    env.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")
    env.setdefault("SUPABASE_KEY", "x")
    return subprocess.run(
        [sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider", "-x"],
        cwd=str(RADICE), env=env, capture_output=True, text=True).returncode


def main() -> int:
    file_toccati = sorted({m[1] for m in MUTAZIONI})
    sha0 = {f: sha(RADICE / f) for f in file_toccati}
    male = 0
    for nome, rel, vecchio, nuovo, test in MUTAZIONI:
        p = RADICE / rel
        originale = p.read_bytes()
        testo = originale.decode("utf-8")
        if "\r\n" in testo:  # file con fine riga Windows: ancore multiriga coerenti
            vecchio = vecchio.replace("\n", "\r\n")
            nuovo = nuovo.replace("\n", "\r\n")
        n = testo.count(vecchio)
        if n != 1:
            print(f"{nome}: ANCORA trovata {n} volte -> mutazione NON applicata")
            male += 1
            continue
        try:
            p.write_bytes(testo.replace(vecchio, nuovo).encode("utf-8"))
            rc = pytest(test)
        finally:
            p.write_bytes(originale)
        ok = rc != 0
        print(f"{nome}: {'ROSSO (atteso)' if ok else 'VERDE (!!! il test non la vede)'}")
        male += 0 if ok else 1
    intatti = all(sha(RADICE / f) == sha0[f] for f in file_toccati)
    print(f"file ripristinati (sha256 identico): {intatti}")
    for t in (T_STALLO, T_MODO, T_WD):
        rc = pytest(t)
        print(f"a codice intatto {t}: {'VERDE' if rc == 0 else 'ROSSO (!!!)'}")
        male += 0 if rc == 0 else 1
    return 0 if (male == 0 and intatti) else 1


if __name__ == "__main__":
    sys.exit(main())
