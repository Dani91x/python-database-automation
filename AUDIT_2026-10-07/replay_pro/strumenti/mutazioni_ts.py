"""Falsificazione della lib replayOperazioni: ogni mutazione deve far diventare
ROSSO almeno un test. Applica, lancia vitest, ripristina (sempre)."""
import subprocess
import sys

RADICE = sys.argv[1]
FILE = RADICE + "/frontend/src/lib/replayOperazioni.ts"
TEST = sys.argv[2] if len(sys.argv) > 2 else "src/lib/replayOperazioni.test.ts"
MUTAZIONI = [
    ("profitto arrotondato sul totale invece che per ordine",
     "        perMercato[o.marketId] = round2((perMercato[o.marketId] ?? 0) + round2(p));",
     "        perMercato[o.marketId] = (perMercato[o.marketId] ?? 0) + profittoGrezzo(o, r, stati);"),
    ("identita' dell'ordine solo dal ref (riprezzo di flumine fuso)",
     "        if (r._ordine) return `o:${r._ordine}`;",
     "        if (r._ordine && false) return `o:${r._ordine}`;"),
    ("ordine in volo mostrato come appoggiato",
     "            ordine: o, riga: r, vivo: v, inVolo: v && r.status === 'PENDING',",
     "            ordine: o, riga: r, vivo: v, inVolo: false,"),
    ("arrotondamento JS (per eccesso) invece di quello di Python",
     "        const pari = cent % 2 === 0 ? cent : cent + 1;",
     "        const pari = cent + 1;"),
    ("ladder dallo stato FINALE invece che dalla cronologia",
     "        if (r._ms > ms) break;\n        u = r;",
     "        u = r;"),
    ("tolleranza di copertura diversa dal banco",
     "    return Math.max(...valori) - Math.min(...valori) <= 0.02 + 0.005 * c + 1e-9;",
     "    return Math.max(...valori) - Math.min(...valori) <= 0.001;"),
    ("commissione sul lordo anche negativo",
     "    for (const [m, v] of Object.entries(perMercato)) comm[m] = v > 0 ? round2(v * aliq(m)) : 0;",
     "    for (const [m, v] of Object.entries(perMercato)) comm[m] = round2(Math.abs(v) * aliq(m));"),
    ("nessun legame annulla-e-ripiazza",
     "        if (nuovo) {\n            nuovo.sostituisce = vecchio.chiave;",
     "        if (nuovo && false) {\n            nuovo.sostituisce = vecchio.chiave;"),
    ("rifiuto del clic senza spiegazione",
     "        if (/posizione aperta|ordine vivo/i.test(motivo)) {",
     "        if (/MAI/.test(motivo)) {"),
    ("abbinato parziale chiamato totale",
     "            const totale = m + EPS >= num(r.size ?? o.importo);",
     "            const totale = true;"),
    ("quote spostate insieme lette come rientro",
     "    const rientro = ordini.find(o => o !== nuovo && o !== vecchio && !o.sostituisce && o.marketId === nuovo.marketId",
     "    const rientro = ordini.find(o => o !== nuovo && o !== vecchio && o.marketId === nuovo.marketId"),
    ("integrazione non riconosciuta",
     "        if (gia) n.integra = gia.chiave;",
     "        if (gia && false) n.integra = gia.chiave;"),
    ("banca spostata legata all'ordine sbagliato (non lo stesso trade)",
     "        const nuovo = candidati.find(n => n.tradeId != null && n.tradeId === vecchio.tradeId && Math.abs(num(n.importo) - tolto) < EPS)",
     "        const nuovo = candidati[0] ?? candidati.find(n => n.tradeId != null && n.tradeId === vecchio.tradeId && Math.abs(num(n.importo) - tolto) < EPS)"),
    ("cursore esatto ignorato",
     "    if (esatto && esatto.index === indice) return",
     "    if (esatto && esatto.index === -99) return"),
]
originale = open(FILE, encoding="utf-8").read()
esiti = []
try:
    for nome, a, b in MUTAZIONI:
        if originale.count(a) != 1:
            esiti.append((nome, "MUTAZIONE NON APPLICABILE"))
            continue
        mutato = originale.replace(a, b)
        if "profittoGrezzo" in b:
            mutato += ("\nfunction profittoGrezzo(o: OrdineBot, r: RigaBot, stati: Record<string, string>): number {\n"
                       "    const m = num(r.size_matched); const p = num(r.average_price_matched);\n"
                       "    const st = stati[String(o.selectionId)] ?? '';\n"
                       "    if (st === 'WINNER') return (o.lato === 'back' ? 1 : -1) * m * (p - 1);\n"
                       "    if (st === 'LOSER') return o.lato === 'back' ? -m : m;\n    return 0;\n}\n")
            mutato = mutato.replace("    const lordo = round2(Object.values(perMercato)", "    for (const k of Object.keys(perMercato)) perMercato[k] = round2(perMercato[k]);\n    const lordo = round2(Object.values(perMercato)")
        open(FILE, "w", encoding="utf-8").write(mutato)
        p = subprocess.run(["npx", "vitest", "run", TEST], cwd=RADICE + "/frontend",
                           capture_output=True, text=True, timeout=600)
        out = p.stdout + p.stderr
        riga = [x for x in out.splitlines() if "Tests" in x and ("failed" in x or "passed" in x)]
        esiti.append((nome, ("ROSSO " if p.returncode != 0 else "VERDE (!) ") + (riga[-1].strip() if riga else "")))
finally:
    open(FILE, "w", encoding="utf-8").write(originale)
for nome, e in esiti:
    print("%-60s %s" % (nome, e))
