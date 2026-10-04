"""Falsificazione dei test nuovi (cantiere TENNIS_SOLDI_VERI_COERENTE, 04/10).

Ogni mutazione reintroduce il difetto nel codice di produzione; il test DEVE
diventare rosso. Ripristino: ``git checkout -- <file>`` (il lavoro e' committato
nel ramo del worktree), poi verifica ``git status`` pulito e zero "MUTAZIONE".
Mai interrompere a meta'. Uso: python falsifica.py <gruppo>  (safe | ui)
"""
import subprocess
import sys

WT = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a2fd2012b8a292274"
PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
EX = "Betfair/safe_strategy/execution.py"
BS = "Betfair/safe_strategy/bot_service.py"

GRUPPI = {
    "safe": {
        "cmd": [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_soldi_veri_catena_2026_10_04.py",
                "-q", "-p", "no:cacheprovider", "-x"],
        "mutazioni": [
            ("M1 catena mai riconosciuta (tentativi bruciati)", EX,
             "    return any(n.startswith(p) for p in PREFISSI_CATENA)",
             "    return False  # MUTAZIONE"),
            ("M2 CRITICAL a ogni tentativo (niente episodio)", EX,
             "            critico = critico and primo\n        _log(db, \"canale_rifiutato\"",
             "            critico = critico  # MUTAZIONE\n        _log(db, \"canale_rifiutato\""),
            ("M3 episodio mai chiuso all'accettazione", EX,
             "        chiudi_episodi_catena(db, porta.attore, mode)   # 04/10",
             "        pass  # MUTAZIONE"),
            ("M4 nessun blocco: raffica di aperture", BS,
             "    if now_ts >= float(voce.get(\"prossima_prova\") or 0.0):",
             "    if True:  # MUTAZIONE"),
            ("M5 motivo_blocco non pubblicato", BS,
             "    _BLOCCO[\"motivo\"] = _motivo_catena()",
             "    pass  # MUTAZIONE"),
            ("M6 blocco mai chiuso dopo un'apertura", BS,
             "        _catena_ripristinata(db, _sport_di(row), mode)",
             "        pass  # MUTAZIONE"),
            ("M7 tentativi consumati anche sul blocco", BS,
             "    st[\"final\"] = bool(st.get(\"final\"))        # un final VERO di prima resta, "
             "mai creato qui\n    st[\"next_ts\"] = now.timestamp() + X.CATENA_PROVA_S",
             "    st[\"attempts\"] = int(st.get(\"attempts\") or 0) + 1  # MUTAZIONE\n"
             "    st[\"final\"] = bool(st.get(\"final\"))\n"
             "    st[\"next_ts\"] = now.timestamp() + X.CATENA_PROVA_S"),
        ],
    },
    "banco": {
        "cmd": [PY, "-m", "Betfair.stream.backtest.certifica", "safe_tennis", "35795993",
                "--scenari", "rapidi", "--trasporto", "canale"],
        "mutazioni": [
            ("B1 catena mai riconosciuta (servizio)", EX,
             "    return any(n.startswith(p) for p in PREFISSI_CATENA)",
             "    return False  # MUTAZIONE"),
            ("B2 CRITICAL a ogni tentativo", EX,
             "            critico = critico and primo\n        _log(db, \"canale_rifiutato\"",
             "            critico = critico  # MUTAZIONE\n        _log(db, \"canale_rifiutato\""),
            ("B3 runner PAPER che serve il live (motore)", "Betfair/stream/motore_ordini.py",
             "        if mode not in LOW._servable_modes(proc):",
             "        if False:  # MUTAZIONE"),
        ],
    },
    "aggancio": {
        "cmd": ('"%s" -m pytest Betfair/safe_strategy/tests/test_soldi_veri_catena_aggancio_2026_10_04.py '
                'Betfair/safe_strategy/tests/test_soldi_veri_catena_2026_10_04.py -q -p no:cacheprovider '
                '&& "%s" -m Betfair.stream.backtest.certifica safe_tennis 35795993 --scenari rapidi '
                '--trasporto canale' % (PY, PY)),
        "shell": True,
        "mutazioni": [
            ("A1 un pending qualunque ripristina la catena", BS,
             "    if out.status == \"open\" or out.catena_servita:",
             "    if out.status in (\"pending\", \"open\"):  # MUTAZIONE"),
            ("A2 ack in_aggancio chiude l'episodio", EX,
             "    elif not is_closing and not ack.motivo:",
             "    elif not is_closing:  # MUTAZIONE"),
            ("A3 rifiuto asincrono non classificato", EX,
             "    nota = f\"canale_rifiutato:{errore}\"\n    if not blocco_di_catena(nota):",
             "    nota = f\"canale_rifiutato:{errore}\"\n    if True:  # MUTAZIONE"),
            ("A4 ordine di prima del blocco lo chiude", BS,
             "    if inviato_ts is not None and dal is not None and inviato_ts < dal:",
             "    if False:  # MUTAZIONE"),
            ("A5 anche un evento 'rifiutato' ripristina", BS,
             "        if fase_ev not in _FASI_RIFIUTO:",
             "        if True:  # MUTAZIONE"),
        ],
    },
    "aggancio_test": {          # solo i test unitari, senza -x: tutti i rossi
        "cmd": [PY, "-m", "pytest",
                "Betfair/safe_strategy/tests/test_soldi_veri_catena_aggancio_2026_10_04.py",
                "-q", "-p", "no:cacheprovider"],
        "mutazioni": [],        # riempite sotto
    },
    "aggancio_banco": {         # solo il banco (R11c)
        "cmd": [PY, "-m", "Betfair.stream.backtest.certifica", "safe_tennis", "35795993",
                "--scenari", "rapidi", "--trasporto", "canale"],
        "mutazioni": [],
    },
    "apertura": {
        "cmd": [PY, "-m", "pytest",
                "Betfair/safe_strategy/tests/test_soldi_veri_catena_aggancio_2026_10_04.py",
                "-q", "-p", "no:cacheprovider"],
        "mutazioni": [
            ("P1 _apertura sempre True (mutazione del coordinatore)", BS,
             "    return (tr.get(\"closes_trade_id\") is None\n"
             "            and (tr.get(\"meta\") or {}).get(\"closes_trade_id\") is None)",
             "    return True  # MUTAZIONE"),
            ("P2 _apertura guarda solo la colonna", BS,
             "    return (tr.get(\"closes_trade_id\") is None\n"
             "            and (tr.get(\"meta\") or {}).get(\"closes_trade_id\") is None)",
             "    return tr.get(\"closes_trade_id\") is None  # MUTAZIONE"),
            ("P3 _apertura guarda solo il meta", BS,
             "    return (tr.get(\"closes_trade_id\") is None\n"
             "            and (tr.get(\"meta\") or {}).get(\"closes_trade_id\") is None)",
             "    return (tr.get(\"meta\") or {}).get(\"closes_trade_id\") is None  # MUTAZIONE"),
        ],
    },
    "omega": {
        "cmd": [PY, "-m", "pytest", "Betfair/omega/tests/test_omega_soldi_veri_catena_2026_10_04.py",
                "-q", "-p", "no:cacheprovider"],
        "mutazioni": [
            ("O1 mode_non_servibile consuma la gamba", "Betfair/omega/omega_service.py",
             "                              \"mode_non_servibile\")",
             "                              )  # MUTAZIONE"),
            ("O2 nessuna sonda rada (raffica)", "Betfair/omega/omega_service.py",
             "    if now_ts >= float(voce.get(\"prossima_prova\") or 0.0):\n"
             "        voce[\"prossima_prova\"] = now_ts + X.CATENA_PROVA_S\n        return False\n"
             "    return True",
             "    return False  # MUTAZIONE"),
            ("O3 REST live senza modo effettivo", "Betfair/omega/omega_service.py",
             "        return X._live_brake()\n    except Exception as ex:  # noqa: BLE001 - freni non valutabili: si ferma",
             "        return None  # MUTAZIONE\n    except Exception as ex:  # noqa: BLE001 - freni non valutabili: si ferma"),
            ("O4 motivo_blocco non pubblicato", "Betfair/omega/omega_service.py",
             "    if _motivo:\n        stats[\"motivo_blocco\"] = _motivo",
             "    if False:  # MUTAZIONE\n        stats[\"motivo_blocco\"] = _motivo"),
            ("O5 asincrono non classificato", "Betfair/omega/omega_service.py",
             "    elif apertura and str(ev.get(\"fase\") or \"\") == \"rifiutato\":",
             "    elif False:  # MUTAZIONE"),
            ("O6 CRITICAL a ogni tentativo REST", "Betfair/omega/omega_service.py",
             "            (logger.critical if nuovo else logger.warning)(",
             "            (logger.critical)(  # MUTAZIONE"),
            ("O7 chiusura trattata come apertura", "Betfair/omega/omega_service.py",
             "    apertura = (tr.get(\"closes_trade_id\") is None\n"
             "                and (tr.get(\"meta\") or {}).get(\"closes_trade_id\") is None)",
             "    apertura = True  # MUTAZIONE"),
        ],
    },
    "mike": {
        "cmd": [PY, "-m", "pytest", "Betfair/mike/tests/test_mike_motivo_blocco_catena_2026_10_04.py",
                "-q", "-p", "no:cacheprovider"],
        "mutazioni": [
            ("C1 stats senza le aperture ferme", "Betfair/mike/service.py",
             "            motivo_aperture_ferme(tracked)),",
             "            None),  # MUTAZIONE"),
            ("C2 motivo mai calcolato", "Betfair/mike/service.py",
             "    if not conti:\n        return None\n    parti = []",
             "    return None  # MUTAZIONE\n    parti = []"),
            ("C3 il tetto nasconde le aperture ferme", "Betfair/mike/service.py",
             "    vivi = [m for m in motivi if m]",
             "    vivi = [m for m in motivi if m][:1]  # MUTAZIONE"),
        ],
    },
    "ui_b": {
        "cmd": "npx vitest run src/lib/soldiVeriCatena.test.ts src/lib/soldiVeriPuntiIngresso.test.ts",
        "cwd": WT + r"\frontend",
        "shell": True,
        "mutazioni": [
            ("V1 Safe tennis diretta guardata col runner tennis", "frontend/src/lib/interruttori.ts",
             "        if (c.stradaSafeTennis === 'diretta') return motivoOrdiniReali(c);\n",
             "        // MUTAZIONE\n"),
            ("V2 strada non dichiarata = via libera", "frontend/src/lib/interruttori.ts",
             "        return m == null ? null\n",
             "        return true ? null  // MUTAZIONE\n"),
            ("V3 Safe a pagina: nessuna strategia verificata", "frontend/src/lib/interruttori.ts",
             "    if (!live.length) return;\n",
             "    if (live.length >= 0) return;  // MUTAZIONE\n"),
            ("V4 Avvia di Mike senza verifica", "frontend/src/components/mike/useMike.ts",
             "            await verificaSoldiVeri(interruttoreDi('mike'), desiredMode, () => leggiCatenaLive());\n",
             "            // MUTAZIONE\n"),
            ("V5 Avvia di Omega senza verifica", "frontend/src/pages/Omega.tsx",
             "            await verificaSoldiVeri(interruttoreDi('omega'), mode, () => leggiCatenaLive());\n",
             "            // MUTAZIONE\n"),
            ("V6 Avvia di Safe senza verifica", "frontend/src/components/safestrategy/useSafeBot.ts",
             "            await verificaSoldiVeriSafe(\n",
             "            void (\n"),
            ("V7 pagina Safe senza catenaLive", "frontend/src/pages/SafeStrategy.tsx",
             "            catenaLive: () => leggiCatenaLive({\n                stradaSafeTennis: () => leggiStradaOrdini(bot.control?.stats, 'tennis') }),\n",
             "            // MUTAZIONE\n"),
            ("V8 Control Room: strada di Safe non passata", "frontend/src/pages/ControlRoom.tsx",
             "                stradaSafeTennis: () => vm.bots.find((x) => x.bot === 'safe')?.stradaTennis ?? null,\n",
             "                // MUTAZIONE\n"),
            ("V9 useControlRoom non legge la strada", "frontend/src/components/controlroom/useControlRoom.ts",
             "                stradaTennis: bot === 'safe' ? leggiStradaOrdini(stats, 'tennis') : null,\n",
             "                stradaTennis: null,  // MUTAZIONE\n"),
        ],
    },
    "scalper": {
        "cmd": [PY, "-m", "pytest", "Betfair/stream/tests/test_scalper_auto_mode_2026_09_25.py",
                "-q", "-p", "no:cacheprovider"],
        "mutazioni": [
            ("D1 soldi veri nasce ancora in dry-run (D3)", "Betfair/stream/scalper/auto_mode.py",
             "    return str(modalita or \"\").strip().lower() != \"live\"",
             "    return True  # MUTAZIONE"),
            ("D2 conflitto di nuovo asimmetrico", "Betfair/stream/scalper/auto_mode.py",
             "    ``motivo_blocco`` lo dice (come gia' con l'interruttore in prova).\"\"\"\n    for r in",
             "    ``motivo_blocco`` lo dice (come gia' con l'interruttore in prova).\"\"\"\n"
             "    if modalita == \"live\":  # MUTAZIONE\n        return None\n    for r in"),
            ("D3 fail-open: modalita' ignota = soldi veri", "Betfair/stream/scalper/auto_mode.py",
             "    return str(modalita or \"\").strip().lower() != \"live\"",
             "    return str(modalita or \"\").strip().lower() == \"paper\"  # MUTAZIONE"),
        ],
    },
    "scalper_banco": {
        "cmd": [PY, "-m", "Betfair.stream.backtest.certifica", "scalper_calcio", "35797769",
                "--scenari", "auto-live", "--worker", "1", "--data-dir",
                r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\_live_raw"],
        "mutazioni": [
            ("D1b banco: soldi veri nasce in dry-run", "Betfair/stream/scalper/auto_mode.py",
             "    return str(modalita or \"\").strip().lower() != \"live\"",
             "    return True  # MUTAZIONE"),
        ],
    },
    "ui_d": {
        "cmd": "npx vitest run src/lib/scalperAuto.test.ts",
        "cwd": WT + r"\frontend",
        "shell": True,
        "mutazioni": [
            ("D4 UI: frase D3 fissa in live", "frontend/src/lib/scalperControlRoom.ts",
             "        if (auto.nasconoInDryRun === false) {",
             "        if (false) {  // MUTAZIONE"),
            ("D5 UI: conflitto non detto", "frontend/src/lib/scalperControlRoom.ts",
             "    if (auto.conflitto) {",
             "    if (false) {  // MUTAZIONE"),
        ],
    },
    "diretta": {
        "cmd": [PY, "-m", "pytest", "Betfair/safe_strategy/tests/test_soldi_veri_catena_2026_10_04.py",
                "-q", "-p", "no:cacheprovider", "-k", "strada_diretta or dichiara_la_strada"],
        "mutazioni": [
            ("S1 strada diretta: Ordini reali ignorato", EX,
             "        eff = _mo.modo_effettivo(tetto, _mo.valore_db())\n        if eff != \"LIVE\":",
             "        eff = \"LIVE\"  # MUTAZIONE\n        if eff != \"LIVE\":"),
            ("S2 strada diretta: soldi veri mai inviati", EX,
             "    blocco = None if is_closing else _live_brake()\n",
             "    blocco = None if is_closing else \"live_order_mode_non_live:OFF\"  # MUTAZIONE\n"),
            ("S3 strada dichiarata sbagliata", BS,
             "        \"tennis\": STRADA_RUNNER_TENNIS if _PO._config_di(\"tennis\") else STRADA_DIRETTA,",
             "        \"tennis\": STRADA_RUNNER_TENNIS,  # MUTAZIONE"),
        ],
    },
    "ui": {
        "cmd": "npx vitest run src/lib/soldiVeriCatena.test.ts",
        "cwd": WT + r"\frontend",
        "shell": True,
        "mutazioni": [
            ("U1 tennis: tetto del runner ignorato", "frontend/src/lib/interruttori.ts",
             "        if (!m.split('+').includes('LIVE')) {",
             "        if (false) {  // MUTAZIONE"),
            ("U2 calcio: Ordini reali ignorato", "frontend/src/lib/interruttori.ts",
             "    if (o.effettivo !== 'LIVE') {",
             "    if (false) {  // MUTAZIONE"),
            ("U3 runner muto = via libera", "frontend/src/lib/interruttori.ts",
             "        if (!m) {\n            return 'il runner tennis non risponde",
             "        if (false) {  // MUTAZIONE\n            return 'il runner tennis non risponde"),
            ("U4 accendi senza guardia", "frontend/src/lib/interruttori.ts",
             "        await assicuraSoldiVeriServiti(sorgente, i, modalita);   // 04/10, prima di scrivere",
             "        // MUTAZIONE"),
            ("U5 cambiaModalita senza guardia", "frontend/src/lib/interruttori.ts",
             "        if (i.strategia != null) await assicuraSoldiVeriServiti(sorgente, i, modalita);",
             "        // MUTAZIONE"),
            ("U6 cambiaModalitaServizio senza guardia", "frontend/src/lib/interruttori.ts",
             "        if (unico) await assicuraSoldiVeriServiti(sorgente, unico, modalita);",
             "        // MUTAZIONE"),
            ("U7 scheda tennis senza guardia", "frontend/src/components/controlroom/comandiBot.ts",
             "        await assicuraSoldiVeriServiti(sorgenteConRilettura, interruttoreDi('safe-tennis'), modalita);",
             "        // MUTAZIONE"),
            ("U8 guardia anche in prova (rompe la prova)", "frontend/src/lib/interruttori.ts",
             "    if (modalita !== 'live' || !sorgente.catenaLive) return;",
             "    if (!sorgente.catenaLive) return;  // MUTAZIONE"),
        ],
    },
}


GRUPPI["aggancio_test"]["mutazioni"] = GRUPPI["aggancio"]["mutazioni"]
GRUPPI["aggancio_banco"]["mutazioni"] = GRUPPI["aggancio"]["mutazioni"]


def run(args, **kw):
    return subprocess.run(args, cwd=WT, capture_output=True, text=True, **kw)


def main(gruppo):
    g = GRUPPI[gruppo]
    esiti = []
    solo = sys.argv[2:]                          # facoltativo: solo queste (M2 M7 ...)
    for nome, f, vecchio, nuovo in g["mutazioni"]:
        if solo and nome.split()[0] not in solo:
            continue
        path = WT + "\\" + f.replace("/", "\\")
        testo = open(path, encoding="utf-8", newline="").read()
        if "\r\n" in testo:                      # copie di lavoro con CRLF
            vecchio, nuovo = vecchio.replace("\n", "\r\n"), nuovo.replace("\n", "\r\n")
        if testo.count(vecchio) != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE (%d)" % testo.count(vecchio)))
            continue
        open(path, "w", encoding="utf-8", newline="").write(testo.replace(vecchio, nuovo))
        try:
            r = subprocess.run(g["cmd"], cwd=g.get("cwd", WT), capture_output=True, text=True,
                               timeout=900, shell=g.get("shell", False),
                               encoding="utf-8", errors="replace")
            righe = (r.stdout + r.stderr).strip().splitlines() or ["?"]
            fallito = [x for x in righe if "FAILED" in x or " failed" in x or "Error" in x][:2]
            esiti.append((nome, ("ROSSO " if r.returncode != 0 else "VERDE(!) ")
                          + " | ".join(fallito or righe[-1:])))
        finally:
            run(["git", "checkout", "--", f])
    for n, e in esiti:
        print("%-52s %s" % (n, e[:300]))
    print("git status dopo il ripristino:", repr(run(["git", "status", "--short"]).stdout))
    print("MUTAZIONE nel codice:", repr(run(["git", "grep", "-c", "MUTAZIONE", "--",
                                              "Betfair", "frontend/src", "desktop"]).stdout))


if __name__ == "__main__":
    main(sys.argv[1])
