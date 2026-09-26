p = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\.claude\worktrees\agent-a1bc87b400bbc7d7c\AUDIT_2026-09-25\E2E_FASE2_BOT_PAPER_2026-09-26.md"
s = open(p, encoding="utf8").read()
SEZ = """## ★★ RIAVVIO 2 (l'utente ha riavviato l'app con la console su file e le porte via canale accese)

**Accensione** (`frontend/e2e_fase2/accensione_r2.e2e.test.tsx`, stessa guardia anti-live; orari in
`ACCENSIONE_ORA.txt` sezione «RIAVVIO 2»; foto `e2e_fase2/accensione_r2/`)
| passo | esito | UTC |
|---|---|---|
| G0 guardia (falsificazione) | verde | 15:13Z |
| A0: 9 bot stopped, order_mode paper (R2 verificato) | verde | 15:13Z |
| A1 Omega paper | running/paper | 15:16:04Z |
| A2 Mike paper | running/paper | 15:16:56Z |
| A3 Safe: tennis dalla scheda tennis | running, variants [tennis]; poi **rosso** sul clic base dalla scheda calcio: «pulsante assente a video: cr-avvia-paper-safe-base» | 15:23Z |
| A3b base/esatto/punta dalla scheda calcio | variants [tennis, base, esatto, punta], 6/6 paper | 15:26:45Z |
| A4 4 tennis stake 2 | running/paper | 15:30:54-15:31:06Z |
| A5 scalper maker 25 | running/paper | 15:33:12Z |

- **R-F2-17 (uso UI, stesso meccanismo di R-E2E-1)**: subito dopo l'avvio «solo tennis», la scheda calcio NON
  offre «avvia» su Safe base perché la plancia legge gli effettivi del servizio, ancora quelli della sessione
  precedente. Pochi minuti dopo, con gli effettivi aggiornati a [tennis], il pulsante c'è e funziona.
- Processi miei: `ascolto_leggero.py` (canali, file `canali_r2/`, memoria costante) e verifiche a comandi brevi.
  Il registratore pesante del feed resta SPENTO per decisione del coordinatore: il ricalcolo B di Omega nel
  riavvio 2 è senza la P fusa.

**Z0 dopo il riavvio**: scanner `source=stream`, 2 connessioni, 251 mercati (15:34Z); `order_mode` paper,
tetto live, freno false, boot nuovo; alert 510 crash del runner TENNIS 15:04:20Z (uptime 611 s), prima delle
accensioni; alert 511 alle 15:26:53Z **JOURNAL KO** «violates check constraint betfair_live_journal_side_check
(ordini NON impattati)» (R-F2-18). Canali (admin-26, 15:36Z): auto-follow vivo, 179 mercati seguiti (153 auto),
attori collegati.

**Z4 via canale (porte accese)**
| controllo | evidenza | esito |
|---|---|---|
| 7.2.3/7.2.6 Safe e Omega passano dal canale | `canale_inviato` Omega 5, Safe 3 (15:15-15:34Z); `flumine_fill` Omega 4, Safe 3 | **OK** |
| 7.2.4 marcature sul trade | Omega 124-128 e Safe 347-349: `canale_ref`, `canale_ack_seq`, `canale_ack_ms` valorizzati; `canale_fase` a volte NULL (124, 125, 349) | OK con riserva |
| 7.2.7 nessuna riga sulla coda DB | `betfair_live_order_requests` 0 righe dopo le 15:10Z | **OK** |
| specchio | `betfair_live_orders` 6 righe paper EXECUTION_COMPLETE `awlq9000000001-6` con **source='runner'** (R-F2-16: gli ordini di Omega/Safe finiscono nello specchio sotto la voce del runner, non del bot) | reperto |
| rifiuti all'avvio | Omega 124 (15:21Z) e Safe tennis 346 (15:24Z) `canale_rifiutato runner_non_agganciato: nessun framework flumine attivo`; Safe riprova (347 OK); Omega 124 `flumine_no_fill attempt 1/3` dopo 112 s | coerente (dichiarato) |
| unicità della sequenza | `canale_ack_seq` 1790434467069 su DUE comandi diversi: omega-t124 (rifiutato) e safe-t348 (R-F2-19) | reperto |

**B Omega 124-128** (`B_omega_r2_124_128.json`, funzioni di produzione, senza P fusa): p_imp, P storica, P
nostra, margine, EV e liability = scritti, cancello vero. Il 127 risulta «KO» nello script solo perché
`omega_trades.price` dopo il fill è il MEDIO ABBINATO (60), mentre la decisione e l'ordine sono a 65 (audit
`price 65`, specchio `price 65 avg 60`): ricalcolato a 65, tutto coincide → **OK**. Da sapere: in paper flumine ha
dato un prezzo migliore del limite (60 contro 65 su un lay).

**Mike 5070-5075** (`verifica_mike_aperti.py`, `mike_aperti/`): regolati TUTTI alle 14:54:40-41Z, prima della
chiusura dell'app, coi totali gol del risultato (36111764: 3 gol → Under vinto +2.85, Over 4.5 perso −1.34, netto
1.51; 36111770: 5 gol → Under −5.00 e −2.50, Over +4.40 e +4.49, netto 1.39). Commissione per mercato (0.15 e
0.47) = 5% del vinto netto del mercato. `settled_pnl` = somma delle gambe. Nessuna riga nuova, nessuna chiusura,
nessun doppio ordine dopo il riavvio → **OK**. Il `mike_events.live` era fermo al minuto ~40 (feed cieco dalle
10:41Z): il primo «KO» dello script sul P&L era un falso rosso (usava quel punteggio fermo).

"""
anchor = "## ★ CRASH DEL RUNNER CALCIO 10:00:46Z"
assert anchor in s
s = s.replace(anchor, SEZ + anchor, 1)
s = s.replace("**Stato del referto: AGGIORNAMENTO 3 — 16:50 locali (14:50Z).**",
              "**Stato del referto: AGGIORNAMENTO 4 — RIAVVIO 2, 17:45 locali (15:45Z).**")
open(p, "w", encoding="utf8").write(s)
print("ok")
