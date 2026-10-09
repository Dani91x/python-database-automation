"""Falsificazione: ogni mutazione reintroduce un difetto nel codice NUOVO e
deve far diventare ROSSO almeno un test nuovo. Ripristina sempre il file."""
import subprocess
import sys

W = "/home/user/python-database-automation/.claude/worktrees/agent-abb4efd85c1b43214"
T_B = "Betfair/stream/tests/test_board_programma_2026_10_09.py"
T_O = "Betfair/stream/tests/test_board_ordini_aggancio_2026_10_09.py"

MUT = [
    ("M21 errore del giro risponde anche ai parcheggiati", "Betfair/stream/motore_ordini.py",
     "        try:\n            self._servi_order_pronti(reqs)\n        except Exception as ex:  # noqa: BLE001\n            logger.exception(\"[motore] /order KO\")",
     "        if True:\n            self._servi_order_pronti(reqs)\n        if False:", T_O),
    ("M1 volume REST non integrato", "Betfair/stream/board_worker.py",
     'if rest_row is not None and rest_row.get("total_matched") is not None:',
     'if False:', T_B),
    ("M2 correct score non escluso", "Betfair/stream/board_worker.py",
     'return "CORRECT_SCORE" in mt or mt == "HALF_TIME_SCORE"',
     'return mt == "CORRECT_SCORE"', T_B),
    ("M3 score anche fuori gioco", "Betfair/stream/board_worker.py",
     'if row.get("inplay") and isinstance(payload, dict):',
     'if isinstance(payload, dict):', T_B),
    ("M4 tetto tipi oltre il limite", "Betfair/stream/board_worker.py",
     'len(vivi) >= TETTO_TIPI_RICHIESTI', 'len(vivi) > TETTO_TIPI_RICHIESTI', T_B),
    ("M5 TTL mai scaduto", "Betfair/stream/board_worker.py",
     'if ora - ts > TTL_RICHIESTA_S]', 'if False]', T_B),
    ("M6 board_mercato in coda comandi", "Betfair/stream/local_channel.py",
     'if method == METODO_BOARD_MERCATO:', 'if False:', T_B),
    ("M7 giro senza lucchetto", "Betfair/stream/board_worker.py",
     'if not _LOCK_GIRO.acquire(blocking=False):\n        return',
     'if not (_LOCK_GIRO.acquire(blocking=False) or True):\n        return', T_B),
    ("M8 REST a ogni giro", "Betfair/stream/board_worker.py",
     'if metas and now_mono - float(_STATE.get("rest_ts", 0.0)) >= _REST_FALLBACK_PERIOD_SEC:',
     'if metas:', T_B),
    ("M9 calcio parcheggiato senza board", "Betfair/stream/runner.py",
     '                    _attesa_board_e_canale(session)\n                    time.sleep(IDLE_FOLLOW_POLL_SEC)',
     '                    time.sleep(IDLE_FOLLOW_POLL_SEC)', T_B),
    ("M10 tennis parcheggiato senza board", "Betfair/stream/tennis_live/tennis_runner.py",
     '_attesa_board_e_canale(session)   # 09/10: board + canale da parcheggiati\n                    time.sleep(_idle_s)',
     'time.sleep(_idle_s)', T_B),
    ("M11 ht invertito", "Betfair/stream/board_worker.py",
     'return any(k in st for k in _STATI_INTERVALLO)',
     'return not any(k in st for k in _STATI_INTERVALLO)', T_B),
    ("M12 tennis punti p1/p2 scambiati", "Betfair/stream/board_worker.py",
     'server = {"home": "p1", "away": "p2"}.get(ts.server or "")',
     'server = {"home": "p2", "away": "p1"}.get(ts.server or "")', T_B),
    ("M13 /order mai agganciato", "Betfair/stream/motore_ordini.py",
     'AZIONI_ORDER_CON_AGGANCIO = frozenset({"place"})',
     'AZIONI_ORDER_CON_AGGANCIO = frozenset()', T_O),
    ("M14 /order mai scaduto", "Betfair/stream/motore_ordini.py",
     'elif ora > int(o["scadenza_ms"]):', 'elif False:', T_O),
    ("M15 attesa oltre il timeout della pagina", "Betfair/stream/motore_ordini.py",
     'else min(v, AGGANCIO_ORDER_MAX_MS_TETTO))', 'else v)', T_O),
    ("M16 FIFO ignorata", "Betfair/stream/motore_ordini.py",
     'if self._flumine is not None and not in_fila and ag.servibile(mid):',
     'if self._flumine is not None and ag.servibile(mid):', T_O),
    ("M17 guardia non rifatta all'uscita", "Betfair/stream/motore_ordini.py",
     'self._servi_order([o["req"]], aggancio=False)',
     'self._servi_order_pronti([o["req"]])', T_O),
    ("M18 parcheggiato senza motore non risponde", "Betfair/stream/runner.py",
     '            ch.respond(req, False, error=_MOTIVO_PARCHEGGIATO_SENZA_MOTORE)',
     '            ch._requests.put_nowait(req); return gestite', T_O),
    ("M19 tennis /order mai agganciato", "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     '_AZIONI_LOCALI_CON_AGGANCIO = frozenset({"place"})',
     '_AZIONI_LOCALI_CON_AGGANCIO = frozenset()', T_O),
    ("M20 tennis parcheggiato tetto/regole saltate (live su PAPER)",
     "Betfair/stream/tennis_live/tennis_live_order_worker.py",
     "                if mode_req not in _servibili(runner_mode.lower()):",
     "                if False:", T_O),
]

esiti = []
for nome, rel, vecchio, nuovo, test in MUT:
    path = f"{W}/{rel}"
    src = open(path, encoding="utf-8").read()
    if src.count(vecchio) != 1:
        esiti.append((nome, f"MUTAZIONE NON APPLICABILE ({src.count(vecchio)} occorrenze)"))
        continue
    open(path, "w", encoding="utf-8").write(src.replace(vecchio, nuovo))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider",
                            "-x", "--timeout=120"] if False else
                           [sys.executable, "-m", "pytest", test, "-q", "-p", "no:cacheprovider"],
                           cwd=W, capture_output=True, text=True, timeout=600)
        coda = [l for l in r.stdout.splitlines() if l.startswith("FAILED")]
        riass = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
        esiti.append((nome, f"{'ROSSO' if r.returncode else 'VERDE (!)'} - {riass} - "
                            + "; ".join(c.split('::')[-1] for c in coda[:3])))
    finally:
        open(path, "w", encoding="utf-8").write(src)
for n, e in esiti:
    print(f"{n}: {e}")
