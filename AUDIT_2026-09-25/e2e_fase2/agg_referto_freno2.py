p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
SEZ = """**Z13.4 FRENO, 2° ciclo (riavvio 2)** (`frontend/e2e_fase2/freno_r2.e2e.test.tsx`, guardia: solo
`set_live_kill_switch`, F0 verde; evidenze `e2e_fase2/freno_r2/`: F1/F2 prima-dopo-esito, `conta_freno_tirato.json`,
`conta_dopo_rilascio.json`, strumento `conta_freno.py`). Annunciato al coordinatore e ad admin-26 10 minuti prima.
TIRATO alle 16:10:59Z (1 clic); RILASCIATO alle 16:22:12Z (3 clic, dopo 2 ancora tirato); `order_mode` paper per
tutto il tempo.
| bot | freno tirato (16:10:59-16:22:12Z) | dopo il rilascio (16:22-16:37Z) | esito |
|---|---|---|---|
| tennis_swing | **3 aperture RIFIUTATE**: `place_rejected` «TENNIS_KILL_SWITCH … apertura RIFIUTATA (passano solo le chiusure)» 16:11:33 / 16:12:04 / 16:19:20Z, riprova con attesa crescente 5→10→20 s | 3 `entry`, 2 `exit`, posizioni pari | **OK** |
| scalper | force-flat entro 2 s (16:11:01/04Z, `freno db_kill_switch_attivo`), sessioni stopped; **l'auto-mode ARMA 2 sessioni nuove** (36111427, 36109062, `requested`) | le 2 sessioni partono, `sniper_fire`, ordine nello specchio con `source='scalper'` | OK + **R-F2-10 confermato** |
| Safe | nessun tentativo (skip: `pre_ko_assente` 3, book senza back 1, spread anomalo 1; 7 proposte opportunità = proposte, non piazzamenti) | trade 354 esatto: `canale_inviato` → `flumine_fill` | freno **NON CERTIFICATO** (nessun tentativo); ripresa OK |
| Omega | nessun tentativo (40 skip: nessun_candidato 20, no_market 8, no_live_state 7, sospeso 3, …) | nessun ingresso nei 15 min | **NON CERTIFICATO** |
| Mike | nessun tentativo: `motivo_blocco` «tetto partite raggiunto: 2 su 2 in paper» | idem | **NON CERTIFICATO** |
| tennis flb/pro/scalper | nessun tentativo | — | **NON CERTIFICATO** |
Nessuna riga nuova in `omega/safe/mike_trades`, `tennis_live_orders`, `betfair_live_orders` e nella coda DB
durante il freno: nessuna apertura passata su nessun bot.

**Mike, mancati ingressi dopo il riavvio (C)**: dopo il riavvio ha aperto 2 partite (San Marino–Finlandia,
Lettonia U21–Germania U21, KO 16:00Z, `LIVE_COVERED`, 6 trade aperti, 28.15 € di esposizione paper). Da lì
`stats.motivo_blocco` = «tetto partite raggiunto: 2 su 2 in paper» e `aperture_bloccate` = 6: il mancato
ingresso sulle partite delle 16:30-17:00Z è motivato dal tetto (condizione del servizio falsa) → OK
documentato, non KO.

"""
anchor = "**B Omega 124-128**"
assert anchor in s
s = s.replace(anchor, SEZ + anchor, 1)
s = s.replace("**Stato del referto: AGGIORNAMENTO 4 — RIAVVIO 2, 17:45 locali (15:45Z).**",
              "**Stato del referto: AGGIORNAMENTO 5 — RIAVVIO 2, 18:40 locali (16:40Z).**")
open(p, "w", encoding="utf8").write(s)
print("ok")
