"""Falsificazione dei componenti (ladder, registro, riquadro): ogni mutazione
deve far diventare ROSSO almeno un test. Applica, lancia vitest, ripristina."""
import subprocess
import sys

R = sys.argv[1] + "/frontend/"
MUT = [
    ("src/components/live/LadderView.tsx", "LadderView: colonne del bot allargate anche fuori dal replay",
     "(botAttivo && (k === 'my_lay' || k === 'my_back')", "((k === 'my_lay' || k === 'my_back')",
     "src/components/live/LadderView.botReplay.test.tsx"),
    ("src/components/live/LadderView.tsx", "LadderView: quote del bot fuori dal range del ladder",
     "    for (const p of prezziExtra) rng.push(roundToTick(p));", "",
     "src/components/live/LadderView.botReplay.test.tsx"),
    ("src/components/live/LadderView.tsx", "LadderView: abbinato del bot non disegnato",
     "            {l.abbinato > 0 && (", "            {l.abbinato > 1e9 && (",
     "src/components/live/LadderView.botReplay.test.tsx"),
    ("src/components/replay/RegistroOperazioniBot.tsx", "Registro: seek all'inizio del passo invece che all'istante esatto",
     "onClick={() => onSeek({ ms: e.ms, marketId: e.marketId, selectionId: e.selectionId })}",
     "onClick={() => onSeek({ ms: Math.floor(e.ms / 10000) * 10000, marketId: e.marketId, selectionId: e.selectionId })}",
     "src/components/replay/RegistroOperazioniBot.test.tsx"),
    ("src/components/replay/RegistroOperazioniBot.tsx", "Registro: filtro per mercato ignorato",
     "() => analisi.eventi.filter(e => !mercato || e.marketId === mercato),", "() => analisi.eventi,",
     "src/components/replay/RegistroOperazioniBot.test.tsx"),
    ("src/components/replay/ApplicaBotPanel.tsx", "Attiva adesso: clic solo accodato (il difetto del caso vero)",
     "        if (!applica.inCorso) avvia(nuovi,", "        if (false) avvia(nuovi,",
     "src/components/replay/ApplicaBotPanel.test.tsx"),
    ("src/components/replay/ApplicaBotPanel.tsx", "Attiva adesso: clic in attesa mai mandati alla fine del ricalcolo",
     "        if (!applica.inCorso && modificheClic && pronto && applica.inviato != null)",
     "        if (false && !applica.inCorso && modificheClic && pronto && applica.inviato != null)",
     "src/components/replay/ApplicaBotPanel.test.tsx"),
    ("src/lib/avvisiBanco.ts", "Avviso: accensione non ricevuta taciuta",
     "        if (esito.dal_ms == null || (esito.richiesta && esito.richiesta.dal_ms == null)) {",
     "        if (false) {",
     "src/components/replay/ApplicaBotPanel.test.tsx"),
    ("src/lib/avvisiBanco.ts", "Avviso: clic persi taciuti",
     "        if (persi.length > 0) {", "        if (persi.length > 99) {",
     "src/components/replay/RegistroOperazioniBot.test.tsx"),
]
out = []
for f, nome, a, b, test in MUT:
    p = R + f
    orig = open(p, encoding="utf-8").read()
    if orig.count(a) != 1:
        out.append("%-70s NON APPLICABILE" % nome)
        continue
    try:
        open(p, "w", encoding="utf-8").write(orig.replace(a, b))
        r = subprocess.run(["npx", "vitest", "run", test], cwd=R, capture_output=True, text=True, timeout=600)
        riga = [x for x in (r.stdout + r.stderr).splitlines() if "Tests" in x and ("failed" in x or "passed" in x)]
        out.append("%-70s %s %s" % (nome, "ROSSO" if r.returncode else "VERDE (!)", riga[-1].strip() if riga else ""))
    finally:
        open(p, "w", encoding="utf-8").write(orig)
print("\n".join(out))
