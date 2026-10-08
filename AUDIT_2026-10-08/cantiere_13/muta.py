"""Falsificazione del cantiere 13: ogni mutazione rimette il difetto, i test devono diventare ROSSI;
poi ripristino dalla copia con verifica dello sha256. Anche la misura PRIMA/DOPO del verificatore
(con le versioni di HEAD rimesse temporaneamente). Uso: python3 muta.py <worktree> <uscita.txt> [bench|mut|tutto]"""
import hashlib
import os
import re
import subprocess
import sys
import time

WT = sys.argv[1]
OUT = sys.argv[2]
COSA = sys.argv[3] if len(sys.argv) > 3 else "tutto"
FE = os.path.join(WT, "frontend")
SCR = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(FE, "src/lib/replayVerificaBarra.ts")
CAL = os.path.join(FE, "src/lib/replayVerificaBarraCalcio.ts")
PY = os.path.join(WT, "tools/replay_barra_fixture.py")
CUR = os.path.join(WT, "Betfair/stream/curator.py")

log = open(OUT, "a", encoding="utf-8")


def scrivi(s):
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def esegui(cmd, cwd, timeout=1500):
    t = time.time()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr, time.time() - t


def vitest(files, filtro=None):
    cmd = ["npx", "vitest", "run", *files]
    if filtro:
        cmd += ["-t", filtro]
    out, dt = esegui(cmd, FE)
    m = re.search(r"Tests\s+(.*)", out)
    rossi = re.findall(r"^\s+(?:×|FAIL)\s+(.*)$", out, re.M)
    return (m.group(1).strip() if m else "?? " + out[-400:]), dt, rossi


def pytest(k):
    out, dt = esegui([sys.executable, "-m", "pytest", "tools/test_replay_barra_fixture.py", "-q", "-p", "no:cacheprovider", "-k", k], WT)
    righe = [l for l in out.splitlines() if re.search(r"passed|failed", l)]
    rossi = re.findall(r"^FAILED (.*)$", out, re.M)
    return (righe[-1] if righe else "?? " + out[-400:]), dt, rossi


def muta(nome, file, vecchio, nuovo, prova):
    originale = open(file, "rb").read()
    h0 = sha(file)
    testo = originale.decode("utf-8")
    assert testo.count(vecchio) == 1, f"{nome}: testo da mutare trovato {testo.count(vecchio)} volte"
    open(file, "wb").write(testo.replace(vecchio, nuovo).encode("utf-8"))
    try:
        esito, dt, rossi = prova()
    finally:
        open(file, "wb").write(originale)
    h1 = sha(file)
    assert h0 == h1, f"{nome}: ripristino NON riuscito"
    scrivi(f"{nome}: {esito}  ({dt:.0f} s)  ripristino sha {h1[:16]} == prima {h0[:16]}")
    for r in rossi[:12]:
        scrivi(f"    rosso: {r[:200]}")


def bench(etichetta):
    out, _ = esegui(["npx", "vite-node", os.path.join(SCR, "bench_verificatore.ts"), etichetta], FE, 600)
    for l in out.splitlines():
        if l.startswith(etichetta):
            scrivi("  " + l)


if COSA in ("bench", "tutto"):
    scrivi("== misura del verificatore (stesse fixture, codice PRIMA = HEAD, DOPO = worktree), alternata")
    copie = {GEN: open(GEN, "rb").read(), CAL: open(CAL, "rb").read()}
    hs = {p: sha(p) for p in copie}
    for giro in range(2):
        bench("DOPO")
        try:
            open(GEN, "wb").write(open(os.path.join(SCR, "HEAD_replayVerificaBarra.ts"), "rb").read())
            open(CAL, "wb").write(open(os.path.join(SCR, "HEAD_replayVerificaBarraCalcio.ts"), "rb").read())
            bench("PRIMA")
        finally:
            for p, b in copie.items():
                open(p, "wb").write(b)
        assert all(sha(p) == hs[p] for p in copie), "ripristino del banco di misura NON riuscito"
    scrivi("  ripristino dopo la misura: sha identici")

if COSA in ("mut", "tutto"):
    C = ["src/lib/replayVerificaBarra.classi.test.ts"]
    scrivi("== mutazioni (ogni riga: esito dei test con la mutazione, poi ripristino verificato)")
    muta("M1 risalita/aumento fuori barra NON giustifica il simbolo (difetto di partenza)", CAL,
         "            if (best >= 0) {\n                nonAttesi[best].preso = true;\n            } else {",
         "            if (best >= 0 && false) { // MUTAZIONE\n                nonAttesi[best].preso = true;\n            } else {",
         lambda: vitest(C + ["src/lib/replayVerificaBarraFixture.test.ts"], "A1|A2|gol annullato"))
    muta("M2 la discesa fra DUE fonti abbassa il livello come un VAR", CAL,
         "            if (prev && prev.source === r.source) {",
         "            if (prev) { // MUTAZIONE",
         lambda: vitest(C, "A1"))
    muta("M3 la risalita di una squadra giustifica il Goal dell'altra", CAL,
         "                if (a.preso || a.team !== lato(g.s.team)) return;",
         "                if (a.preso) return; // MUTAZIONE",
         lambda: vitest(C, "A1"))
    muta("M4 una risalita giustifica piu' simboli (non uno a uno)", CAL,
         "                nonAttesi[best].preso = true;",
         "                nonAttesi[best].preso = false; // MUTAZIONE",
         lambda: vitest(C, "A1"))
    muta("M5 nessun limite di 3 minuti fra aumento e simbolo", CAL,
         "                if (d <= FINESTRA_ABBINAMENTO_GOL_MS && d < bestD) { best = j; bestD = d; }\n            });\n            if (best >= 0) {",
         "                if (d < bestD) { best = j; bestD = d; } // MUTAZIONE\n            });\n            if (best >= 0) {",
         lambda: vitest(C, "A2"))
    muta("M6 l'aumento prima del primo frame non conta", CAL,
         "                for (let k2 = ch; k2 < r.home; k2++) nonAttesi.push({ team: 'home', ms: r.ms, preso: false });\n                for (let k2 = ca; k2 < r.away; k2++) nonAttesi.push({ team: 'away', ms: r.ms, preso: false });",
         "                // MUTAZIONE: niente aumenti fuori registrazione",
         lambda: vitest(C, "A2"))
    muta("M7 KICKOFF_DISCORDANTE senza il motivo dei dati", GEN,
         "{ istante: b.inizioDichiarato, perDati: motivoKickoffDiscordante(validi, d, kickoffAtteso) });",
         "{ istante: b.inizioDichiarato, perDati: undefined && motivoKickoffDiscordante(validi, d, kickoffAtteso) }); // MUTAZIONE",
         lambda: vitest(C + ["src/lib/replayVerificaBarraDb.test.ts", "src/components/replay/AvvisoCoerenzaBarra.test.tsx",
                             "src/lib/replayVerificaBarraFixture.test.ts", "src/lib/replayVerificaBarraScript.test.ts"]))
    muta("M8 CARTELLINI_DIVERSI sempre per dati (anche se la pagina perde o aggiunge un cartellino)", CAL,
         "                if (nellaTimeline === visti) {",
         "                if (nellaTimeline === visti || true) { // MUTAZIONE",
         lambda: vitest(C, "C2"))
    muta("M9 partita 'solo per dati' se UNA incoerenza e' per dati (some invece di every)", GEN,
         "    return e.incoerenze.length > 0 && e.incoerenze.every(r => !!r.perDati);",
         "    return e.incoerenze.length > 0 && e.incoerenze.some(r => !!r.perDati); // MUTAZIONE",
         lambda: vitest(C + ["src/lib/replayVerificaBarraDb.test.ts"]))
    muta("M10 il buco della registrazione descritto come flag discorde", GEN,
         "        if (fra.length === 0) {",
         "        if (fra.length === -1) { // MUTAZIONE",
         lambda: vitest(C, "C1"))
    muta("M11 il generatore ignora --registrazioni per i punteggi e la timeline", PY,
         "    base = os.path.join(cartella or CARTELLA_REGISTRAZIONI, event_id, event_id)",
         "    base = os.path.join(CARTELLA_REGISTRAZIONI, event_id, event_id)  # MUTAZIONE",
         lambda: pytest("registrazioni_e_uscita"))
    muta("M12 il generatore ignora --uscita", PY,
         "    return os.path.join(cartella or CARTELLA_FIXTURE, f\"replay_barra_{event_id}.json\")",
         "    return os.path.join(CARTELLA_FIXTURE, f\"replay_barra_{event_id}.json\")  # MUTAZIONE",
         lambda: pytest("registrazioni_e_uscita or cartelle"))
    muta("M13 curator senza la regola (d) del 07/10 (la causa del rosso della fixture rimessa)", CUR,
         "        stato_cambiato = seen and last_stato.get(market_id) != stato",
         "        stato_cambiato = False  # MUTAZIONE",
         lambda: pytest("riproducibile"))
scrivi("== fine")
