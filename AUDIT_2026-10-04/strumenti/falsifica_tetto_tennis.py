"""Falsificazione dei test nuovi (cantiere TETTO_TENNIS, 04/10).

Ogni mutazione reintroduce il difetto nel codice di produzione; il test DEVE
diventare rosso. Ripristino: ``git checkout -- <file>`` (il lavoro e' committato
nel ramo del worktree), poi verifica ``git status`` pulito e zero "MUTAZIONE".
Mai interrompere a meta'. Uso: python falsifica_tetto_tennis.py <gruppo> [M1 M2 ...]
"""
import subprocess
import sys

WT = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a07fd1ab50fc74bfe"
PY = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.venv\Scripts\python.exe"
TL = "Betfair/stream/tennis_live/"
RU = TL + "tennis_runner.py"
WK = TL + "tennis_live_order_worker.py"
EX = TL + "esecutore_tennis.py"
GTF = TL + "guardie_tennis.py"
MO = "Betfair/stream/modo_ordini.py"
SVC = TL + "tennis_bot_service.py"


def _pytest(*files):
    return [PY, "-m", "pytest", *files, "-q", "-p", "no:cacheprovider"]


GRUPPI = {
    "b2": {
        "cmd": _pytest(TL + "tests/test_paper_live_separati_tennis_2026_10_04.py"),
        "mutazioni": [
            ("F1 _capture_strategy ignora la modalita'", WK,
             "            if mode is not None and isinstance(per_modo, dict) and per_modo:",
             "            if False:  # MUTAZIONE"),
            ("F2 nessuna strategia live dedicata", RU,
             "        out[\"live\"] = cap_live",
             "        out[\"live\"] = shared_cap  # MUTAZIONE"),
            ("F3 posizioni senza le strategie degli ordini", WK,
             "            if altra is not None and altra is not strat:",
             "            if False:  # MUTAZIONE"),
            ("F4 motore: esposizioni senza modalita'", EX,
             "    if isinstance(session, CaptureDiModo):",
             "    if False:  # MUTAZIONE"),
            ("F5 capture senza modalita' dichiarata", RU,
             "        cap_live._tennis_modalita_esecuzione = \"LIVE\"",
             "        pass  # MUTAZIONE"),
            ("F6 strategia assente non rifiutata", EX,
             "    if isinstance(per_modo, dict) and per_modo and per_modo.get(m) is None:",
             "    if False:  # MUTAZIONE"),
        ],
    },
    "b3": {
        "cmd": _pytest(TL + "tests/test_modo_effettivo_tennis_2026_10_04.py"),
        "mutazioni": [
            ("E1 scelta di un altro avvio valida", MO,
             "        if not AA.stesso_avvio({AA.CHIAVE_BOOT_ID: _STATO[\"boot\"]}, boot):\n"
             "            return None\n        return _STATO[\"modo\"]",
             "        return _STATO[\"modo\"]  # MUTAZIONE"),
            ("E2 scelta non valida = LIVE (ottimista)", MO,
             "    return modo_effettivo(tetto, scelta_per_questo_avvio(boot_id) or MODO_ALL_AVVIO)",
             "    return modo_effettivo(tetto, scelta_per_questo_avvio(boot_id) or \"LIVE\")  # MUTAZIONE"),
            ("E3 effettivo = solo tetto (Ordini reali ignorato)", WK,
             "    return _mo.modo_effettivo_tennis(_runner_mode())",
             "    return _runner_mode()  # MUTAZIONE"),
            ("E4 chiusure frenate", WK,
             "    if _gt.is_riga_di_chiusura(action, params):\n        return None\n    row_m",
             "    row_m"),
            ("E5 canale locale senza blocco aperture", WK,
             "            blocco = _blocco_apertura_modo(mode_req, action, cmd.get(\"params\"))",
             "            blocco = None  # MUTAZIONE"),
            ("E6 coda DB senza blocco aperture", WK,
             "        _blocco = _blocco_apertura_modo(_declared_mode(row), _declared_action(row),",
             "        _blocco = None and _blocco_apertura_modo(_declared_mode(row), _declared_action(row),"),
            ("E7 canale locale: solo mode == tetto (prima)", WK,
             "            if mode_req not in _servibili(runner_mode_l):",
             "            if mode_req != runner_mode_l:  # MUTAZIONE"),
            ("E8 motore senza blocco (com'era)", EX,
             "    return _TW._blocco_apertura_modo(row_mode, action, params)",
             "    return None  # MUTAZIONE"),
            ("E9 terza rete assente", GTF,
             "        motivo = motivo_reale_fermo()\n        if motivo is None:",
             "        motivo = None  # MUTAZIONE\n        if motivo is None:"),
            ("E10 terza rete ferma anche le chiusure", GTF,
             "        if ordine_riduce_il_rischio(self.flumine, order):\n            return\n        msg",
             "        msg"),
            ("E11 terza rete fail-open col tetto riletto", GTF,
             "    return (_TW._blocco_apertura_modo(\"live\", \"place\", {})\n            or f\"",
             "    return (_TW._blocco_apertura_modo(\"live\", \"place\", {})\n            or None and f\""),
            ("E13 terza rete non registrata nel runner", RU,
             "    framework.add_trading_control(_gt.ControlloModoOrdiniTennis)",
             "    pass  # MUTAZIONE"),
            ("E12 specchio canale con la modalita' del runner", WK,
             "                _mirror_order(mode_req, _event_id_of(session, cmd.get(\"market_id\")),",
             "                _mirror_order(runner_mode_l, _event_id_of(session, cmd.get(\"market_id\")),"),
        ],
    },
    "b4": {
        "cmd": _pytest(TL + "tests/test_ladder_modo_effettivo_tennis_2026_10_04.py"),
        "mutazioni": [
            ("L1 stato del Terminal col tetto (com'era)", RU,
             "        \"order_mode\": modo[\"effettivo\"],",
             "        \"order_mode\": live_order_mode(),  # MUTAZIONE"),
            ("L2 scelta di ieri valida per il Terminal", MO,
             "        if not AA.stesso_avvio({AA.CHIAVE_BOOT_ID: _STATO[\"boot\"]}, boot):\n"
             "            return None\n        return _STATO[\"modo\"]",
             "        return _STATO[\"modo\"]  # MUTAZIONE"),
        ],
    },
    "b5": {
        "cmd": "node --test desktop/ambiente_runner.test.js",
        "shell": True,
        "mutazioni": [
            ("T1 tennis sempre PAPER (com'era)", "desktop/ambiente_runner.js",
             "    return calcio === 'LIVE' ? 'LIVE' : 'PAPER';",
             "    return 'PAPER';  // MUTAZIONE"),
            ("T2 tetto calcio copiato (OFF/sconosciuto passano)", "desktop/ambiente_runner.js",
             "    return calcio === 'LIVE' ? 'LIVE' : 'PAPER';",
             "    return calcio ?? 'LIVE';  // MUTAZIONE"),
            ("T3 valore illeggibile = LIVE", "desktop/ambiente_runner.js",
             "        return m ?? 'PAPER';",
             "        return m ?? 'LIVE';  // MUTAZIONE"),
            ("T4 .env che vince sull'ambiente", "desktop/ambiente_runner.js",
             "    const p = processEnv && processEnv[chiave];",
             "    const p = null;  // MUTAZIONE"),
            ("T5 main.js che forza ancora PAPER", "desktop/main.js",
             "        envFile: readEnvFile(path.join(repoRoot, '.env')),",
             "        envFile: {},  // MUTAZIONE"),
        ],
    },
    "b6": {
        "cmd": _pytest(TL + "tests/test_modo_effettivo_tennis_2026_10_04.py"),
        "mutazioni": [
            ("C1 canale tennis con lo stato del CALCIO", GTF,
             "        stato = _mo.stato_tennis(_TW._runner_mode())",
             "        stato = _mo.stato_corrente()  # MUTAZIONE"),
            ("C2 pubblicazione mai chiamata dalla rilettura", GTF,
             "        # 04/10: il modo ordini VERO del tennis sul suo canale, al cambio\n"
             "        pubblica_modo_ordini_se_cambiato()",
             "        pass  # MUTAZIONE"),
            ("C3 nessun hello", GTF,
             "            ch.set_hello(modo_ordini=msg)",
             "            pass  # MUTAZIONE"),
            ("C4 pubblica a ogni giro (niente firma)", GTF,
             "        if firma == _MODO_CANALE[\"firma\"]:\n            return False",
             "        if False:  # MUTAZIONE\n            return False"),
        ],
    },
    "b7": {
        "cmd": _pytest(TL + "tests/test_soldi_veri_bot_tennis_2026_10_04.py",
                       TL + "tests/test_tennis_auto_mode_2026_09_25.py",
                       TL + "tests/test_ponte_interruttori_2026_09_17.py"),
        "mutazioni": [
            ("S1 ponte: live armato in dry-run (com'era)", SVC,
             "        \"dry_run\": False,",
             "        \"dry_run\": d[\"mode\"] == \"live\",  # MUTAZIONE"),
            ("S2 terza rete assente (Ordini reali ignorato dai bot)", GTF,
             "        motivo = motivo_reale_fermo()\n        if motivo is None:",
             "        motivo = None  # MUTAZIONE\n        if motivo is None:"),
            ("S3 live_in_dry_run = «il bot e' in live» (com'era)", SVC,
             "        \"live_in_dry_run\": any(",
             "        \"live_in_dry_run\": d.get(\"mode\") == \"live\" or any("),
            ("S4 motore senza blocco: Safe tennis live col solo tetto", EX,
             "    return _TW._blocco_apertura_modo(row_mode, action, params)",
             "    return None  # MUTAZIONE"),
            ("S5 Safe tennis live sotto la capture paper", RU,
             "        out[\"live\"] = cap_live",
             "        out[\"live\"] = shared_cap  # MUTAZIONE"),
        ],
    },
    "b8": {   # banco: replay rapido di Safe tennis (canale), ~10 s per mutazione
        "cmd": [PY, "-m", "Betfair.stream.backtest.certifica", "safe_tennis", "35795993",
                "--scenari", "rapidi", "--trasporto", "canale"],
        "mutazioni": [
            ("R1 motore senza «Ordini reali» (com'era)", EX,
             "    return _TW._blocco_apertura_modo(row_mode, action, params)",
             "    return None  # MUTAZIONE"),
            ("R2 scelta di un altro avvio valida", MO,
             "        if not AA.stesso_avvio({AA.CHIAVE_BOOT_ID: _STATO[\"boot\"]}, boot):\n"
             "            return None\n        return _STATO[\"modo\"]",
             "        return _STATO[\"modo\"]  # MUTAZIONE"),
            ("R3 terza rete assente", GTF,
             "        motivo = motivo_reale_fermo()\n        if motivo is None:",
             "        motivo = None  # MUTAZIONE\n        if motivo is None:"),
            ("R4 effettivo = solo tetto", WK,
             "    return _mo.modo_effettivo_tennis(_runner_mode())",
             "    return _runner_mode()  # MUTAZIONE"),
            ("R5 chiusure del ladder frenate", WK,
             "    if _gt.is_riga_di_chiusura(action, params):\n        return None\n    row_m",
             "    row_m"),
        ],
    },
    "ui6": {
        "cmd": "npx vitest run src/lib/soldiVeriCatena.test.ts",
        "cwd": WT + r"\frontend",
        "shell": True,
        "mutazioni": [
            ("G1 tennis: Ordini reali ignorato (com'era)", "frontend/src/lib/interruttori.ts",
             "        if (o.scelto !== 'LIVE') {",
             "        if (false) {  // MUTAZIONE"),
            ("G2 tennis: Ordini reali non letto = via libera", "frontend/src/lib/interruttori.ts",
             "        const o = c.ordiniReali;\n        if (o == null || !o.letto) {",
             "        const o = c.ordiniReali;\n        if (false) {  // MUTAZIONE"),
            ("G3 tennis: conta il tetto del calcio", "frontend/src/lib/interruttori.ts",
             "        if (o.scelto !== 'LIVE') {",
             "        if (o.effettivo !== 'LIVE') {  // MUTAZIONE"),
        ],
    },
    "ui4": {
        "cmd": "npx vitest run src/components/tennis/TennisBotPanel.test.tsx",
        "cwd": WT + r"\frontend",
        "shell": True,
        "mutazioni": [
            ("U1 scheda LIVE: dry-run forzato come in OFF (com'era)", "frontend/src/components/tennis/TennisBotPanel.tsx",
             "        if (orderMode === 'OFF') { setDryRun(true); setDryRunTouched(false); return; }",
             "        if (orderMode === 'LIVE' || orderMode === 'OFF') { setDryRun(true); setDryRunTouched(false); return; }  // MUTAZIONE"),
            ("U2 scheda LIVE: annuncia ORDINI REALI (com'era)", "frontend/src/components/tennis/TennisBotPanel.tsx",
             "                        <Power className=\"h-4 w-4 mr-2\" /> ARMA {dryRun ? '(dry-run)' : 'SIMULATO'}",
             "                        <Power className=\"h-4 w-4 mr-2\" /> ARMA {dryRun ? '(dry-run)' : "
             "orderMode === 'LIVE' ? 'ORDINI REALI' : 'SIMULATO'}  {/* MUTAZIONE */}"),
            ("U3 scheda LIVE: niente avviso dove sono i soldi veri", "frontend/src/components/tennis/TennisBotPanel.tsx",
             "                {!active && orderMode === 'LIVE' && (",
             "                {false && (  // MUTAZIONE"),
        ],
    },
}


def run(args, **kw):
    return subprocess.run(args, cwd=WT, capture_output=True, text=True, **kw)


def main(gruppo):
    g = GRUPPI[gruppo]
    esiti = []
    solo = sys.argv[2:]
    for nome, f, vecchio, nuovo in g["mutazioni"]:
        if solo and nome.split()[0] not in solo:
            continue
        path = WT + "\\" + f.replace("/", "\\")
        testo = open(path, encoding="utf-8", newline="").read()
        if "\r\n" in testo:
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
            fallito = [x for x in righe if "FAILED" in x or " failed" in x][:3]
            esiti.append((nome, ("ROSSO " if r.returncode != 0 else "VERDE(!) ")
                          + " | ".join(fallito or righe[-1:])))
        finally:
            run(["git", "checkout", "--", f])
    for n, e in esiti:
        riga = "%-48s %s" % (n, e[:400])
        print(riga.encode("ascii", "replace").decode("ascii"))
    print("git status dopo il ripristino:", repr(run(["git", "status", "--short"]).stdout))
    print("MUTAZIONE nel codice:", repr(run(["git", "grep", "-c", "MUTAZIONE", "--",
                                              "Betfair", "frontend/src", "desktop"]).stdout))


if __name__ == "__main__":
    main(sys.argv[1])
