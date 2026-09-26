p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
C = [
    ("R3-acc", "accensione in paper (Omega 17:20:51, Mike 17:21:04, Safe 17:22:39 4 varianti 6/6 paper, tennis 17:22:53-17:23:03, scalper 17:23:20 UTC)", "OK", "A3 al primo clic ancora «pulsante assente» (R-F2-17), A3b ok"),
    ("R3-Z0a", "alert ORDER_MODE col modo effettivo (518: «PAPER … tetto LIVE, effettivo PAPER»)", "OK", "R-F2-C2 risolto"),
    ("R3-Z0b", "scanner su stream, chiavi nuove `fonte`/`sessione`/`avvisi_in_attesa` presenti", "OK", "207 mercati; 2 ripieghi REST di 31 s con rientro (alert 521-524)"),
    ("R3-Z0c", "runner: ripresa con specchio paper ripulito, riconciliazione", "OK", "alert 519/520"),
    ("R3-Safe", "Safe esatto apre via canale+flumine", "OK", "canale_inviato → flumine_fill (17:23Z)"),
    ("R3-spec", "specchio `betfair_live_orders` con `source` = nome del bot", "KO", "ordine Safe `awlq1790442472668000` con source='runner' (R-F2-16 ancora aperto)"),
    ("R3-coda", "nessun doppio invio (canale + coda DB)", "OK", "1 riga in coda (118, `local…668000`, done) = diario del comando canale; 1 sola riga nello specchio"),
    ("R3-journal", "nessun alert JOURNAL KO", "OK", "nessun alert JOURNAL dopo il riavvio 3"),
    ("R3-Mike", "Mike apre (5082 Under 1.48, 5 €) e propone l'uscita", "OK", ""),
    ("R3-Mike-log", "attività di Mike senza ripetizioni a ogni giro", "KO", "R-F2-21: `loss_exit_deciso` ~1/s (666 righe in 12 min su 36109477)"),
    ("R3-freno-C", "freno: scalper force-flat e NESSUN armamento a freno tirato", "OK", "17:27:10-16Z force-flat, sessioni stopped pulite, 0 `auto_armata` nei 4 min (R-F2-10 non riprodotto); nessun «NON flat» (R-F2-11 non riprodotto)"),
    ("R3-freno-altri", "freno: rifiuti di Omega/Safe/Mike/tennis", "NON CERTIFICATO", "nessun tentativo di apertura nei 4 min (17:27:09-17:31:14Z)"),
    ("R3-freno-R", "rilascio con doppia conferma", "OK", "17:31:14Z"),
    ("R3-tennis", "tennis: ordini vecchi chiusi alla ripresa", "OK", "24 ordini paper dei bot `VOIDED` alla ripresa del runner"),
    ("R3-Z5", "F0 dai log `_logs/`", "NON CERTIFICATO", "non analizzato da me nel tempo disponibile"),
]
tot = len(C); ok = sum(c[2] == "OK" for c in C); ko = sum(c[2] == "KO" for c in C); nc = tot - ok - ko
righe = "\n".join(f"| {a} | {b} | **{e}** | {n} |" for a, b, e, n in C)
SEZ = f"""# ▶▶ RIAVVIO 3 (app con i fix delle due sessioni, riavviata alle 17:06:59Z) — 17:40Z (19:40 ora PC)

**{tot} controlli · OK {ok} ({ok*100/tot:.0f}%) · KO {ko} ({ko*100/tot:.0f}%) · NON CERTIFICATI {nc} ({nc*100/tot:.0f}%)** — dati vivi in paper, nessun replay.

| id | controllo | esito | evidenza / nota |
|---|---|---|---|
{righe}

3° freno: TIRATO alle 17:27:09Z, RILASCIATO alle 17:31:14Z (evidenze `e2e_fase2/freno_r3/`). Nella finestra: 0 righe
nuove in trade, ordini e coda di qualunque bot. Orari in `ACCENSIONE_ORA.txt`, sezione «RIAVVIO 3»; foto in
`e2e_fase2/accensione_r3/`.
**Stato dei KO della giornata dopo il riavvio 3**:
- R-F2-C2 (alert LIVE): **risolto**.
- R-F2-10 (scalper arma a freno tirato): **non riprodotto** nel 3° ciclo (4 min, 0 armamenti; nel 1° e nel 2° ciclo aveva armato).
- R-F2-11: non riprodotto.
- R-F2-16 (specchio con `source='runner'`): **aperto**.
- R-F2-21 (log di Mike ripetuto circa ogni secondo): **nuovo, aperto**.
- R-F2-6, R-F2-9, R-F2-C1, R-F2-18: non riesaminati nei 20 minuti.

---

"""
i = s.index("# ▶ SINTESI FINALE")
s = s[:i] + SEZ + s[i:]
open(p, "w", encoding="utf8").write(s)
print("ok", tot, ok, ko, nc)
