# Falsificazione D-4 / D-6 (08/10 sera): ogni mutazione deve far diventare ROSSO
# almeno un test; ripristino con verifica sha256. Lanciato dalla radice del worktree.
import hashlib
import os
import subprocess
import sys

R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\wt-ui"
PY = os.path.join(R, ".venv", "Scripts", "python.exe")
FE = os.path.join(R, "frontend")
NPX = "npx.cmd"

RB = "Betfair/stream/tennis_live/tools/replay_bot.py"
TS = "frontend/src/lib/tennis.ts"
CAT = "frontend/src/lib/replayBotCatalogo.ts"
CP = "frontend/src/components/controlroom/aperte/cashOutPagina.ts"
CO = "frontend/src/pages/CashOut.tsx"
SC = "frontend/src/components/controlroom/aperte/ScatolaCashOut.tsx"
BC = "frontend/src/components/controlroom/BottoneChiudiRiga.tsx"
CG = "frontend/src/components/controlroom/CashOutGlobale.tsx"
CPA = "frontend/src/components/controlroom/CashOutPartita.tsx"

PYT = [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-x",
       "Betfair/stream/tennis_live/tests/test_d4_gate_aperto_esposti_2026_10_08.py",
       "Betfair/stream/tennis_live/tests/test_cantiere6_nomi_setup_gate_2026_10_08.py",
       "Betfair/stream/tests/test_applica_bot_tutti_2026_10_07.py"]
VT_TENNIS = [NPX, "vitest", "run", "src/lib/tennisSchedaCatalogo.test.ts"]
VT_CO = [NPX, "vitest", "run", "src/components/controlroom/aperte/cashOutPagina.test.ts",
         "src/pages/CashOut.test.tsx"]

# (nome, file, vecchio, nuovo, comando, cartella)
M = [
    ("D4-M1 warmup_ms tolto dal catalogo Python", RB,
     '        ("warmup_ms", "Osservazione prima di quotare", "Tempi", "int", 0, 120000, 1000, "ms"),\r\n', "",
     PYT, R),
    ("D4-M2 price_min del pro di nuovo fuori catalogo", RB,
     '    "tennis_pro": {\r\n        "min_total_matched": _NON_LETTA,\r\n    },',
     '    "tennis_pro": {\r\n        "min_total_matched": _NON_LETTA,\r\n        "price_min": "x",\r\n    },',
     PYT, R),
    ("D4-M3 gate-aperto cambia un valore (swing conf_ticks 1->2)", RB,
     '"zin": 1.0, "er_max": 1.0, "conf_ticks": 1}', '"zin": 1.0, "er_max": 1.0, "conf_ticks": 2}',
     PYT, R),
    ("D4-M4 nota senza le chiavi fuori scheda", RB,
     "    if fuori_ui:\r\n        dalla_ui +=", "    if False:\r\n        dalla_ui +=",
     PYT, R),
    ("D4-M5 catalogo TS non rigenerato (default warmup_ms 0)", CAT,
     '"chiave": "warmup_ms",\r\n            "etichetta": "Osservazione prima di quotare",\r\n            "tipo": "int",\r\n            "default": 30000,',
     '"chiave": "warmup_ms",\r\n            "etichetta": "Osservazione prima di quotare",\r\n            "tipo": "int",\r\n            "default": 0,',
     PYT, R),
    ("D4-M6 scheda TS: min_total_matched a schermo (flb)", TS,
     "            min_lay_size: 5, exit_mode: 'hybrid' },",
     "            min_lay_size: 5, min_total_matched: 0, exit_mode: 'hybrid' },",
     VT_TENNIS, FE),
    ("D4-M6b scheda TS: campo min_total_matched nella flb", TS,
     "            { key: 'min_lay_size', label:",
     "            { key: 'min_total_matched', label: 'x', step: 1, min: 0, max: 9, hint: 'x' },\r\n            { key: 'min_lay_size', label:",
     VT_TENNIS, FE),
    ("D4-M7 scheda TS: default swing conf_ticks 3", TS,
     "conf_ticks: 2, min_matched: 10000, price_min: 1.08, price_max: 8 },",
     "conf_ticks: 3, min_matched: 10000, price_min: 1.08, price_max: 8 },",
     VT_TENNIS, FE),
    ("D4-M8 scheda TS: quota min del pro non arriva a 1,01", TS,
     "{ key: 'price_min', label: 'Quota min', step: 0.01, min: 1.01, max: 5, hint: 'non entrare sotto questa quota' },",
     "{ key: 'price_min', label: 'Quota min', step: 0.01, min: 1.05, max: 5, hint: 'non entrare sotto questa quota' },",
     VT_TENNIS, FE),
    ("D4-M9 scheda TS: warmup_ms tolto", TS,
     "            { key: 'warmup_ms', label:", "            { key: 'warmup_msX', label:",
     VT_TENNIS, FE),
    ("D6-N1 CLOSED dopo live (ordine di prima)", CP,
     "        if (partita.statoMercato === 'CLOSED') return { fase: 'gioco', nota: 'conclusa', koMs: partita.koMs, fonte: 'scanner' };\r\n        if (partita.stato === 'live')",
     "        if (partita.stato === 'live') return { fase: 'gioco', nota: 'in-gioco', koMs: partita.koMs, fonte: 'scanner' };\r\n        if (partita.statoMercato === 'CLOSED') return { fase: 'gioco', nota: 'conclusa', koMs: partita.koMs, fonte: 'scanner' };\r\n        if (partita.stato === 'live')",
     VT_CO, FE),
    ("D6-N2 sezioneScatola ignora la conclusa", CP,
     "    if (s.fase.nota === 'conclusa') return 'concluse';", "",
     VT_CO, FE),
    ("D6-N3 pagina: In gioco per fase (doppione con Concluse)", CO,
     "visibili.filter((s) => sezioneScatola(s) === 'gioco')", "visibili.filter((s) => s.fase.fase === 'gioco')",
     VT_CO, FE),
    ("D6-N4 Concluse anche col filtro Pre-match", CO,
     "{fase !== 'pre' && concluse.length > 0 && (", "{concluse.length > 0 && (",
     VT_CO, FE),
    ("D6-N5 testata: StatoPill al posto del testo della conclusa", SC,
     "                {conclusa != null ? (", "                {false ? (",
     VT_CO, FE),
    ("D6-N6 gamba: motivo non passato al pulsante", SC,
     "spentoPerche: o.bot === 'scalper' ? null : conclusa,", "spentoPerche: null,",
     VT_CO, FE),
    ("D6-N7 BottoneChiudiRiga ignora spentoPerche", BC,
     "cBase != null && cBase.ok && spentoPerche ?", "cBase != null && cBase.ok && false ?",
     VT_CO, FE),
    ("D6-N8 scalper spento anche lui", SC,
     "spentoPerche: o.bot === 'scalper' ? null : conclusa,", "spentoPerche: conclusa,",
     VT_CO, FE),
    ("D6-N9 fuori dai bot: cash out acceso sulla conclusa", SC,
     "eventId={s.eventId} eventName={s.nome} spentoConclusa={conclusa} />", "eventId={s.eventId} eventName={s.nome} />",
     VT_CO, FE),
    ("D6-N10 posizione col conto: cash out acceso sulla conclusa", SC,
     "const spento = motivoCashOutConclusa(s) ?? (!api", "const spento = null ?? (!api",
     VT_CO, FE),
    ("D6-N11 Chiudi tutte le gambe ignora il motivo esterno", CG,
     "const spentoPerche = spentoEsterno ?? motivoPrezziFermi(r)", "const spentoPerche = motivoPrezziFermi(r)",
     VT_CO, FE),
    ("D6-N12 Safe: cash out acceso sulla conclusa", CPA,
     "const bloccoCashout = spentoPerche ?? motivoCashoutSpento({", "const bloccoCashout = motivoCashoutSpento({",
     VT_CO, FE),
    ("D6-N13 riepilogo senza le concluse", CO,
     "{inGioco.length} in gioco · {pre.length} pre-match · {concluse.length} {concluse.length === 1 ? 'conclusa' : 'concluse'}",
     "{inGioco.length} in gioco · {pre.length} pre-match",
     VT_CO, FE),
]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    righe = []
    for nome, f, vecchio, nuovo, cmd, cwd in M:
        p = os.path.join(R, f)
        orig = open(p, "rb").read()
        h0 = sha(p)
        s = orig.decode("utf-8")
        n = s.count(vecchio)
        if n != 1:
            righe.append("%s: ANCORA NON UNICA (%d) - NON ESEGUITA" % (nome, n))
            continue
        open(p, "wb").write(s.replace(vecchio, nuovo).encode("utf-8"))
        try:
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", shell=False)
            out = (r.stdout or "") + (r.stderr or "")
            esito = "ROSSO" if r.returncode != 0 else "VERDE (SOPRAVVISSUTA)"
            coda = [l for l in out.splitlines() if ("failed" in l or "passed" in l)][-2:]
            righe.append("%s: %s | %s" % (nome, esito, " / ".join(x.strip() for x in coda)))
        finally:
            open(p, "wb").write(orig)
            assert sha(p) == h0, "RIPRISTINO FALLITO %s" % f
        print(righe[-1], flush=True)
    print("\n".join(["", "RIEPILOGO"] + righe))


if __name__ == "__main__":
    main()
