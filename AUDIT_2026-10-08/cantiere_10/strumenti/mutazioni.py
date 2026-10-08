"""Falsificazione del cantiere 10: ogni mutazione reintroduce un difetto, i test
nuovi devono diventare ROSSI; poi ripristino e verifica dello sha del file."""
import hashlib
import os
import re
import subprocess
import sys

WT = "/home/user/python-database-automation/.claude/worktrees/agent-a6c264c7010c81043"
FE = os.path.join(WT, "frontend")
TEST_TS = ["src/lib/replayRegistroFasi.test.ts", "src/components/replay/RegistroFasi.test.tsx"]
TEST_PY = "Betfair/stream/tests/test_contratto_cicli_bot_ts_2026_10_08.py"

OPS = "frontend/src/lib/replayOperazioni.ts"
FASI = "frontend/src/lib/replayFasi.ts"
HOOK = "frontend/src/lib/useOperativitaBot.ts"
REG = "frontend/src/components/replay/RegistroOperazioniBot.tsx"
RIE = "frontend/src/components/replay/RiepilogoPnlBot.tsx"
TIPO = "frontend/src/lib/replayBot.ts"

MUT = [
    ("M1 il registro ignora cicli_bot (sempre «da piatto a piatto»)", OPS,
     "    if (dichiarati == null) {\n        return {\n            fonte: 'ordini'",
     "    if (true || dichiarati == null) { // MUTAZIONE\n        return {\n            fonte: 'ordini'"),
    ("M2 i cicli del rientro automatico spariscono (fusi nel ciclo prima)", OPS,
     "    const out: CicloRegistro[] = dichiarati.map(d => {",
     "    const out: CicloRegistro[] = dichiarati.filter(d => d.origine !== 'rientro_automatico').map(d => { // MUTAZIONE"),
    ("M3 istanti del ciclo dagli ordini invece che dal bot", OPS,
     "            daMs: d.inizio_ms ?? oo[0]?.primoMs ?? 0,",
     "            daMs: oo[0]?.primoMs ?? d.inizio_ms ?? 0, // MUTAZIONE"),
    ("M4 nessun intervallo (fine del 1T ignorata)", FASI,
     "    if (c.finePrimo != null && ms >= c.finePrimo) return FASE_INTERVALLO;",
     "    if (c.finePrimo != null && ms >= c.finePrimo) return FASE_1T; // MUTAZIONE"),
    ("M5 il KickOff ri-emesso sposta il calcio d'inizio (ultimo invece del primo)", FASI,
     "        if (ko == null && norma(r.event_type) === 'kickoff') ko = ms;",
     "        if (norma(r.event_type) === 'kickoff') ko = ms; // MUTAZIONE"),
    ("M6 fase inventata dal minuto quando mancano gli stati dei tempi", FASI,
     "    if (c.finePrimo == null && c.ripresa == null) return FASE_GIOCO_CALCIO;\n",
     "    // MUTAZIONE\n"),
    ("M7 il ciclo nella fase in cui si chiude invece di quella in cui nasce", OPS,
     "    for (const c of reg.cicli) prendi(faseAl(c.daMs)).cicli.push(c);",
     "    for (const c of reg.cicli) prendi(faseAl(c.aMs ?? c.daMs)).cicli.push(c); // MUTAZIONE"),
    ("M8 P&L di sezione sempre a regolamento (non col metodo del bot)", OPS,
     "        if (metodo === 'cicli') {\n            const c = contoCicli(s.cicli, aliquota);",
     "        if (metodo === 'cicli' && false) { // MUTAZIONE\n            const c = contoCicli(s.cicli, aliquota);"),
    ("M9 ordini fuori dai cicli del bot persi", OPS,
     "    return { fonte: 'bot', cicli: out, fuoriCiclo: ordini.filter(o => !presi.has(o.chiave)).map(o => o.chiave), mancanti };",
     "    return { fonte: 'bot', cicli: out, fuoriCiclo: [], mancanti }; // MUTAZIONE"),
    ("M10 vista cronologica con le chiusure ricavate (non quelle del bot)", OPS,
     "    if (reg.fonte === 'ordini') return [...eventi];",
     "    if (reg.fonte === 'ordini' || true) return [...eventi]; // MUTAZIONE"),
    ("M11 clic rifiutato col numero ricavato, non quello del bot", HOOK,
     "            esito.cicli_bot ? numeroDelBot(esito.cicli_bot) : undefined),",
     "            undefined), // MUTAZIONE numeroDelBot"),
    ("M12 nessuna indicazione «chiuso al» per il ciclo che attraversa due fasi", REG,
     "        const attraversa = faseFine != null && faseIstante != null && faseFine.id !== faseIstante(c.daMs).id;",
     "        const attraversa = false && faseFine != null && faseIstante != null; // MUTAZIONE"),
    ("M13 riquadro: la riga per fase non mostra l'intervallo anche se ha operazioni", RIE,
     ".filter(s => s.fase.id !== 'int' || s.ordini > 0)",
     ".filter(s => s.fase.id !== 'int') /* MUTAZIONE */"),
    ("M15 vista cronologica senza le testate di fase", REG,
     "        return fasi.map((f, i) => (i === 0 || fasi[i - 1].id !== f.id ? f : null));",
     "        return fasi.map(() => null); // MUTAZIONE"),
    ("M16 il ripiego non lo dice (fonte dei cicli sempre «del bot»)", REG,
     "            <div className=\"text-white/55\" data-testid=\"registro-fonte-cicli\" data-fonte={reg.fonte}>\n                {reg.fonte === 'bot'",
     "            <div className=\"text-white/55\" data-testid=\"registro-fonte-cicli\" data-fonte={'bot'}>\n                {true /* MUTAZIONE */"),
    ("M14 tipo TS senza la chiave banca (contratto Python<->TS)", TIPO,
     "    /** la banca finale; {} se il ciclo non ne ha */\n    banca: BancaDichiarata | Record<string, never>;\n",
     "    // MUTAZIONE banca tolta\n"),
]


def sha(p):
    return hashlib.sha256(open(os.path.join(WT, p), "rb").read()).hexdigest()


def vitest():
    r = subprocess.run(["npx", "vitest", "run", *TEST_TS], cwd=FE, capture_output=True, text=True, timeout=900)
    out = r.stdout + r.stderr
    m = re.search(r"Tests\s+(.*)", out)
    rossi = re.findall(r"^\s+× (.*)$", out, re.M)
    return (m.group(1).strip() if m else "?"), rossi


def pytest():
    r = subprocess.run([sys.executable, "-m", "pytest", TEST_PY, "-q", "-p", "no:cacheprovider"], cwd=WT,
                       capture_output=True, text=True, timeout=900)
    return r.stdout.strip().splitlines()[-1]


def main(sel):
    for nome, f, da, a in MUT:
        if sel and not any(nome.startswith(s + " ") for s in sel):
            continue
        p = os.path.join(WT, f)
        orig = open(p, encoding="utf-8").read()
        h0 = sha(f)
        assert orig.count(da) == 1, (nome, orig.count(da))
        open(p, "w", encoding="utf-8").write(orig.replace(da, a))
        try:
            esito, rossi = vitest()
            py = pytest() if f == TIPO else "-"
        finally:
            open(p, "w", encoding="utf-8").write(orig)
        h1 = sha(f)
        print("== %s  [%s]" % (nome, f))
        print("   vitest: %s | pytest contratto: %s" % (esito, py))
        for x in rossi:
            print("   ROSSO: %s" % x)
        print("   ripristino: sha256 %s %s" % (h1, "IDENTICO" if h0 == h1 else "DIVERSO!"))
        assert "MUTAZIONE" not in open(p, encoding="utf-8").read()
        sys.stdout.flush()


if __name__ == "__main__":
    main(sys.argv[1:])
