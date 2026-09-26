# ▶▶ RIAVVIO 3 (app con i fix delle due sessioni, riavviata alle 17:06:59Z) — 17:40Z (19:40 ora PC)

**15 controlli · OK 11 (73%) · KO 2 (13%) · NON CERTIFICATI 2 (13%)** — dati vivi in paper, nessun replay.

| id | controllo | esito | evidenza / nota |
|---|---|---|---|
| R3-acc | accensione in paper (Omega 17:20:51, Mike 17:21:04, Safe 17:22:39 4 varianti 6/6 paper, tennis 17:22:53-17:23:03, scalper 17:23:20 UTC) | **OK** | A3 al primo clic ancora «pulsante assente» (R-F2-17), A3b ok |
| R3-Z0a | alert ORDER_MODE col modo effettivo (518: «PAPER … tetto LIVE, effettivo PAPER») | **OK** | R-F2-C2 risolto |
| R3-Z0b | scanner su stream, chiavi nuove `fonte`/`sessione`/`avvisi_in_attesa` presenti | **OK** | 207 mercati; 2 ripieghi REST di 31 s con rientro (alert 521-524) |
| R3-Z0c | runner: ripresa con specchio paper ripulito, riconciliazione | **OK** | alert 519/520 |
| R3-Safe | Safe esatto apre via canale+flumine | **OK** | canale_inviato → flumine_fill (17:23Z) |
| R3-spec | specchio `betfair_live_orders` con `source` = nome del bot | **KO** | ordine Safe `awlq1790442472668000` con source='runner' (R-F2-16 ancora aperto) |
| R3-coda | nessun doppio invio (canale + coda DB) | **OK** | 1 riga in coda (118, `local…668000`, done) = diario del comando canale; 1 sola riga nello specchio |
| R3-journal | nessun alert JOURNAL KO | **OK** | nessun alert JOURNAL dopo il riavvio 3 |
| R3-Mike | Mike apre (5082 Under 1.48, 5 €) e propone l'uscita | **OK** |  |
| R3-Mike-log | attività di Mike senza ripetizioni a ogni giro | **KO** | R-F2-21: `loss_exit_deciso` ~1/s (666 righe in 12 min su 36109477) |
| R3-freno-C | freno: scalper force-flat e NESSUN armamento a freno tirato | **OK** | 17:27:10-16Z force-flat, sessioni stopped pulite, 0 `auto_armata` nei 4 min (R-F2-10 non riprodotto); nessun «NON flat» (R-F2-11 non riprodotto) |
| R3-freno-altri | freno: rifiuti di Omega/Safe/Mike/tennis | **NON CERTIFICATO** | nessun tentativo di apertura nei 4 min (17:27:09-17:31:14Z) |
| R3-freno-R | rilascio con doppia conferma | **OK** | 17:31:14Z |
| R3-tennis | tennis: ordini vecchi chiusi alla ripresa | **OK** | 24 ordini paper dei bot `VOIDED` alla ripresa del runner |
| R3-Z5 | F0 dai log `_logs/` | **NON CERTIFICATO** | non analizzato da me nel tempo disponibile |

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

# ▶ SINTESI FINALE (fase 2, delegato sessione B) — aggiornata alle 18:55 locali (16:55Z)

**Esito dei controlli: 50 controlli · OK 34 (68%) · KO 7 (14%) · NON CERTIFICATI 9 (18%)**

| id | controllo | esito | evidenza / nota |
|---|---|---|---|
| Z0/Z3 | accensione in paper dalla UI vera (mattino, riavvio 2), guardia anti-live falsificata | **OK** | ACCENSIONE_ORA.txt, accensione/, accensione_r2/ |
| Z13.2 | paper e live mai insieme (ogni riga di trade/ordini di oggi `mode=paper`, effettivo PAPER) | **OK** | sentinella + query di fine giornata |
| Z4.O1 | Omega: stato sul canale con `control`, battito | **OK** | canali/, omega_control.stats |
| Z4.O2 | Omega decide dal feed (audit V3 completo, skip motivati) | **OK** | omega_activity |
| Z4.O3 | Omega ordini paper via canale+flumine, nessun doppio sulla coda (riavvio 2) | **OK** | canale_inviato, specchio awlq900…, coda 0 |
| Z4.O4 | Omega uscite manuali: nessuna uscita discrezionale eseguita | **OK** | omega_activity |
| Z4.O5 | Omega nessun ingresso su mercato sospeso | **OK** | skip market_suspended |
| B-Omega | ricalcolo di 10 decisioni (117-120, 124-128) con le funzioni di produzione | **OK** | B_omega_*.json (P fusa ricalcolata solo sul 120) |
| Z4.M1 | Mike: stato sul canale | **OK** | mike_stato |
| Z4.M2 | Mike: hazard atlante v4 dichiarato nel frame | **NON CERTIFICATO** | chiave `hazard_versione` assente; ci sono solo hazard/hazard_atlas numerici |
| Z4.M3 | Mike: paper REST, fuori dallo specchio | **OK** | mike_trades paper_fill:execution_mode_rest |
| Z4.M4 | Mike: uscite proposte e non eseguite, protezioni (copertura Over 4.5) automatiche | **OK** | uscita_proposta ×17, cover |
| C-Mike | ingressi pre-match (banda, stake, finestra) e mancati ingressi (tetto 2/2) | **OK** | C_mike.json, mike_control.stats |
| B-Mike | stake delle coperture Over 4.5 (`cover_residual`) | **OK** | B_mike_cover.json |
| Mike-PT | place-and-trim del sotto-minimo in paper | **NON CERTIFICATO** | R-F2-13: in paper fill simulato diretto |
| Mike-Reg | regolazione dei 6 trade 5070-5075, nessun doppio ordine, P&L | **OK** | mike_aperti/ |
| Z4.S1 | Safe: stato sul canale, effettivi | **OK** | safe_stato |
| Z4.S2 | Safe base banda 20-34 e veto campionati su ingressi reali | **NON CERTIFICATO** | nessun ingresso base oggi (pre_ko_assente al mattino) |
| Z4.S3 | Safe tennis backMin 1.02 | **OK** | ingressi a 1.02-1.11 |
| Z4.S4 | Safe: nota atlante v4 nelle attività | **NON CERTIFICATO** | 0 attività con «atlante v» |
| Z4.S5 | Safe ordini paper via canale+flumine (riavvio 2) | **OK** | canale_inviato + flumine_fill |
| Z4.S6 | Safe uscite manuali = proposte (cashout proposed, exit_hold in attesa) | **OK** | safe_strategy_requests 265 |
| Z4.S7 | Safe proposte modello/anomalie NON piazzate | **OK** | 46 proposte, 0 trade model/manual |
| C-Safe | rigioco del feed registrato nel `SafeEngine` di produzione | **OK** | C_safe_*.json |
| Z4.T1 | tennis auto-mode dal feed (origine auto) | **OK** | tennis_bot_control, tennis_live_follow |
| Z4.T2 | righe per partita paper, dry_run false | **OK** |  |
| Z4.T3 | ordini tennis nello specchio `tennis_live_orders` paper | **OK** | con R-F2-7 |
| Z4.T4 | uscite tennis: solo stop/protezioni, nessun target a uscite manuali | **OK** | swing `exit kind=stop` |
| Z4.T-fine | partita finita → righe in chiusura, tetto rispettato | **KO** | R-F2-6 |
| Z4.C1 | scalper auto-mode, sessioni dry-run | **OK** |  |
| Z4.C2 | specchio scalper con `source='scalper'` (riavvio 2) | **OK** | betfair_live_orders 43709 |
| Z4.C3 | scalper sul canale 47338 | **OK** | scalper_stato |
| Z4.C-exit | scalper: nessuna chiusura da solo a uscite manuali | **KO** | R-F2-9 (sniper) |
| Z5 | tempi degli ordini F0 dal log | **NON CERTIFICATO** | mattino senza log; riavvio 2 non analizzato da me |
| Z6 | striscia d'esito a video | **NON CERTIFICATO** | nessun browser |
| Z7 | transizioni Omega pubblicate e giro notturno | **OK** | omega_transitions_status: published 25/09 13:57Z, cron 04:00Z succeeded |
| Z13.4-O | freno: Omega rifiuta le aperture | **OK** | 3 rifiuti (1° ciclo) |
| Z13.4-T | freno: tennis rifiuta le aperture | **OK** | tennis_swing 3 rifiuti (2° ciclo) |
| Z13.4-C | freno: scalper force-flat e NESSUN armamento | **KO** | R-F2-10 (arma a freno tirato, 2 cicli su 2); R-F2-11 |
| Z13.4-S | freno: Safe rifiuta le aperture | **NON CERTIFICATO** | nessun tentativo nei 2 cicli |
| Z13.4-M | freno: Mike rifiuta le aperture | **NON CERTIFICATO** | nessun tentativo (tetto 2/2) |
| Z13.4-R | rilascio con doppia conferma e aperture che riprendono | **OK** | 2 cicli; Safe 354, swing, scalper dopo il rilascio |
| 3-bis A | feed vs libro Betfair vero vs IPS | **OK** | con riserva: 3/6 prezzi uguali, 3/6 a 1-2 tick su righe di 0.8-2.9 s |
| D | view-model vero della Control Room vs DB | **OK** | con reperti R-F2-14/15 |
| Z14.2 | P&L paper ricalcolato per posizione | **OK** | verifica_pnl.py, 0 KO |
| Run-1 | runner calcio stabile | **KO** | R-F2-C1: 2 crash (10:00:46Z, 14:46:15Z) |
| Run-2 | runner calcio si riaggancia dopo un'interruzione | **KO** | cieco 10:41:41Z → riavvio |
| Alert | alert ORDER_MODE col modo effettivo | **KO** | R-F2-C2 |
| Journal | journal degli ordini senza errori | **KO** | R-F2-18 (alert 511) |
| UI | campi a video (U…) | **NON CERTIFICATO** | nessun browser collegato |

**NON CERTIFICATI (motivo)**: Z4.M2 (versione dell'atlante non dichiarata nel frame di Mike) · Mike place-and-trim
(in paper non si esercita, R-F2-13) · Z4.S2 (nessun ingresso Safe base oggi) · Z4.S4 (nessuna nota atlante nelle
attività di Safe) · Z5 F0 (mattino senza log su file; il log del riavvio 2 non l'ho analizzato) · Z6 e tutti i campi
«a video» (nessun browser collegato) · freno su Safe e Mike (nessun tentativo di apertura in 2 cicli) · tutto ciò che
dipende dal runner fra le 10:41:41Z e il riavvio 2 («runner cieco»).

**KO (con file:riga; stato: APERTO salvo diversa indicazione del coordinatore — non ho verificato fix di altri)**
| KO | dove | stato |
|---|---|---|
| R-F2-6 tennis: partita finita con righe `running`, tetto 5 superato (armate 6-10) | `tennis_bot_service.py:492-500` (`_mercato_chiuso` legge `tennis_live_now.status`, che resta SUSPENDED) + `auto_mode.py:177-200` (`scegli_partite` conta solo le armate nel feed) | aperto |
| R-F2-9 sniper chiude da solo a uscite manuali | gate solo su `ScalperStrategy` (`scalper_bot.py:446`), non su `sniper_bot`; `USCITE_AUTOMATICHE_PER_BOT.md:263-264` | aperto |
| R-F2-10 scalper: l'auto-mode arma a freno tirato, `motivo_blocco` null | `scalper_service.py:745` (`giro_auto` prima del freno a `:750`), armamento `:455-490`, `motivo_blocco` `:494` | aperto (confermato nei 2 cicli) |
| R-F2-11 force-flat non appiattisce il residuo sotto il minimo | `scalper_session.py:1312-1321` | aperto |
| R-F2-C1 crash del runner calcio (exit 1) ×2, poi cieco dalle 10:41:41Z senza rilevamento per ~4 h | causa senza traceback; ipotesi di admin-26 `runner.py:1192` | aperto (fix delle sessioni in arrivo col riavvio 3: da verificare) |
| R-F2-C2 alert ORDER_MODE «*** LIVE *** SOLDI VERI» con effettivo PAPER | alert all'avvio del runner (live_alerts 498, 506) | aperto |
| R-F2-C3 console dell'app non su file | `runner.py:2325` basicConfig su console | mitigato: dal riavvio 2 la console va su `%TEMP%\alphascore_console.log` |
| R-F2-18 journal: `betfair_live_journal_side_check` violato | alert 511 (15:26:53Z) | aperto |
| Uniformità a porte spente (R-F2-2): paper di Omega/Safe senza flumine | `omega_service.py:2527-2547`, `auto_follow.py:857-865` | risolto dalla configurazione: con le porte accese passano da canale+flumine |

Reperti non-KO da decidere: R-F2-1/17 (scheda tennis «solo tennis» e pulsanti Safe dagli effettivi vecchi), R-F2-3/4
(audit Omega: `p_modello` = P fusa, book non salvato), R-F2-5 (Mike entra senza dossier), R-F2-7 (ordine tennis
riscritto ogni secondo, `placed_at` NULL), R-F2-8 (Pula = cemento per default), R-F2-12 (freno consuma i tentativi
di Omega), R-F2-14/15 (due liability, definizione di «oggi»), R-F2-16/20 (specchio `source='runner'` per
Omega/Safe calcio, `source='manual'` per Safe tennis), R-F2-19 (`canale_ack_seq` ripetuto).

**Cosa ho visto fare ai bot (tutto PAPER, piazzati dalle 09:00Z, dati al 16:50Z)**
| bot | decisioni | ordini paper | regolati (V/P) | aperti | P&L netto regolato |
|---|---|---|---|---|---|
| Omega | 705 valutazioni (686 skip motivati) | 12 lay CS 1 € (2 in errore: rifiuto canale e freno) | 9 (9/0) | 1 | **+8.55** |
| Mike | 17 proposte d'uscita (nessuna eseguita), 4 partite | 12 (entrate Under, seconde entrate, coperture Over 4.5) | 6 (3/3) | 6 | **+2.90** |
| Safe esatto | 469 skip, 46 proposte opportunità non piazzate | 6 lay CS 2 € | 4 (4/0) | 1 | **+7.60** |
| Safe tennis | — | 8 back 3 € (1.02-1.11) | 5 (4/1) | 1 | **−2.76** (una back a 1.02 persa −3.00) |
| tennis_swing | 24 ingressi fra i 4 bot | 40 ordini | 7 (1/1) | 33 | **+0.15** |
| tennis_pro | | 12 | 6 (2/2) | 6 | **−0.12** |
| tennis_flb | | 11 | 4 (0/1) | 7 | **−0.04** |
| tennis_scalper | blocca in gioco (configurazione) | 0 | — | — | 0 |
| scalper calcio | 19 armamenti automatici, 4 sniper_fire | simulati (dry-run) + 1 nello specchio | — | — | solo lordo dichiarato (non nel realizzato) |

---

# E2E REALE — FASE 2 — BOT ACCESI IN PAPER — REFERTO INCREMENTALE — 26/09/2026

Delegato Opus del coordinatore (sessione B). Worktree `agent-a1bc87b400bbc7d7c`, base `origin/master` `34a8d92`.
Nessun commit. App accesa dalle 10:56 locali (exe pid 15624): mai chiusa né riavviata. LIVE escluso.
**Stato del referto: AGGIORNAMENTO 5 — RIAVVIO 2, 18:40 locali (16:40Z).** Il file viene riscritto a ogni aggiornamento.

---

## ★★ RIAVVIO 2 (l'utente ha riavviato l'app con la console su file e le porte via canale accese)

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

**Z13.4 FRENO, 2° ciclo (riavvio 2)** (`frontend/e2e_fase2/freno_r2.e2e.test.tsx`, guardia: solo
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

## ★ CRASH DEL RUNNER CALCIO 10:00:46Z (reperto grave di admin-26, analisi in SOLA LETTURA)

Evidenze: `e2e_fase2/crash_runner_canali_0958_1003.txt` (ascoltatore dei canali, estratto con
`finestra_canali.py 09:58:00 10:03:30 runner_calcio,scanner`), `live_alerts` 496-501, righe dei trade/attività.
**Lo stdout/stderr dell'app NON è stato catturato da nessun mio processo**: l'exe è stato avviato senza
redirezione e i miei ascoltatori leggono solo i websocket. Non c'è il traceback.

**Cronologia (UTC)**
| ora | fonte | fatto |
|---|---|---|
| 09:42:44 | `scalper_activity` | l'auto-mode dello scalper arma 36090936/37 (a freno tirato, R-F2-10) |
| 09:43:30 → 09:43:35 | 47331 `auto_follow` | `mercati_sottoscritti` 17 → **0** → 32 (`mercati_manuali` 17 → 32): risottoscrizione dopo il `segui` |
| 09:57:40-09:59:40 | conteggi 47331 | `ladder` al minuto 174 → 87 → 14 (fine delle partite J-League) |
| 09:59:48 | `scalper_activity` | auto-mode arma 36090941 (Imabari–Shonan, a fine partita) → `db.segui` |
| 09:59:49 | `live_alerts` 496 | `NEW_MATCHES` «1 nuove partite agganciate al live» |
| 09:59:58 | 47331 `battito` | ultimo battito prima del crash (`mode LIVE+PAPER`) |
| 10:00:30 | 47331 `auto_follow` | `mercati_seguiti` 32, **`mercati_sottoscritti` 0**, `ultimo_errore` null |
| **10:00:46** | ascoltatore | **47331 chiuso** (`ConnectionClosedError`), poi `ConnectionRefused` ogni 5 s fino alle 10:01:21 |
| 10:01:06 | `live_alerts` 497 | `RUNNER_WATCHDOG` «RUNNER CRASHATO: exit code 1, uptime 3858s. Riavvio n. 1 tra 10s» |
| 10:01:22 | `live_alerts` 498 | `ORDER_MODE` «Live trading: modalità LIVE attiva. *** LIVE *** ORDINI REALI (SOLDI VERI) attivi» |
| 10:01:22 | `live_alerts` 499 | `RUNNER_RESUME` «specchio paper pulito (10 ordini, 0 posizioni), 0 richieste stantie scartate» |
| 10:01:24 | 47331 | di nuovo in ascolto: `hello mode=LIVE`, `modo_ordini` 10:01:26 **effettivo PAPER**, tetto LIVE, kill false |
| 10:01:28 | `live_alerts` 500 | `RECONCILE` «ripresa LIVE: 0 ordini correnti sul conto, 0 esterni, 91 righe specchio» |
| 10:04:31-32 | scalper + alert 501 | l'auto-mode arma 36111770 → `NEW_MATCHES` |
| 10:05:17-20 | 47331 `auto_follow` | seguiti 32 → 20 → 25, `ultimo_errore` «stream di mercato non ancora connesso», `risottoscrizioni` 1 |

Canale muto per **38 s** (10:00:46-10:01:24). `betfair_live_heartbeat`: 0 righe fra 09:59 e 10:03 (tabella non
usata oggi come battito del runner: il battito è sul canale).

**Esito per bot**
- **Omega**: non ha perso il feed. Il feed unico è un processo a parte (47336): i conteggi `scan_calcio` al minuto
  sono continui (229, 267, 210) e `omega_stato` esce 12 volte al minuto anche durante il buco. Dalle 10:00 alle
  10:02 fa solo 3 `skip` (10:01:22-47Z). Posizione aperta al crash: **118** (lay AOHW 36090941), regolata `won`
  +0.95 alle 10:02:54Z, una volta sola, nessuna riga doppia. I suoi ordini paper non passano dal runner (R-F2-2),
  quindi non c'era niente da perdere nello specchio.
- **Mike**: non ha perso il feed. Posizioni aperte al crash: 5070 e 5071 (partite femminili al fischio delle
  10:00Z). Transizioni `LIVE_KO_GREEN` e `uscita_proposta` alle 10:00:10-20Z, poi `under_second` 5072 alle
  10:02:45Z e coperture 5073-5075: tutte REST paper, non dipendono dal runner. Nessuna riga doppia.
- **Safe**: nessuna posizione calcio aperta (342 e 343 regolate alle 09:55-09:56Z); Safe tennis 344 alle
  10:04:01Z (REST). Nessuna attività anomala nella finestra.
- **Scalper**: le sessioni sono processi a parte con un loro stream: 36090936 si ferma alle 10:00:41-43Z
  (`stop richiesto: force-flat`, fine partita), 36111764 si arma alle 10:01:04Z durante il buco del runner. Nessun
  errore di sessione.
- **Tennis**: runner tennis (47332) non toccato (conteggi continui).
- **Specchio paper del runner**: «pulito 10 ordini, 0 posizioni» alla ripresa. `betfair_live_orders` non ha
  righe dal 25/09, quindi quei 10 ordini erano nel blotter in memoria del runner: NON so quali (nessun log).

**Reperti del crash (nessuna correzione)**
- **R-F2-C1 (KO, grave)**: il runner calcio va in crash (exit 1) dopo 3858 s. Il watchdog lo riavvia in 36 s.
  Causa NON verificabile senza log. Correlazione osservata: il crash cade 57 s dopo un `NEW_MATCHES` provocato
  dal `segui` dell'auto-mode dello scalper (09:59:48-49Z), mentre `auto_follow` segnava `mercati_sottoscritti = 0`
  con 32 seguiti (10:00:30Z). Lo stesso schema (seguiti che salgono, sottoscritti a 0) si era già visto alle
  09:43:30Z senza crash, e alle 10:05:17Z con «stream di mercato non ancora connesso». Ipotesi da verificare col
  traceback: risottoscrizione dello stream a caldo durante un `segui` a fine partita.
- **R-F2-C2 (KO di comunicazione, grave per il trader)**: a ogni avvio del runner l'alert `ORDER_MODE` dice
  «*** LIVE *** ORDINI REALI (SOLDI VERI) attivi» (498, 10:01:22Z), mentre l'effettivo è PAPER (`modo_ordini`
  10:01:26Z, effettivo PAPER, `scelto_ui` PAPER). L'alert racconta il TETTO del `.env`, non la modalità effettiva.
- **R-F2-C3**: la console dell'app non finisce in un file (`runner.py:2325` fa `basicConfig` sulla console,
  l'exe non la redirige): un crash in produzione non lascia traceback.
- **Doppi ordini / righe orfane dopo la ripresa**: nessuno sulle tabelle dei bot (verificate `omega_trades`,
  `mike_trades`, `safe_strategy_trades`, `betfair_live_orders`, `betfair_live_order_requests`: nessuna riga nuova
  nella finestra oltre a quelle elencate sopra).

## ★ RUNNER CALCIO «CIECO» 10:01Z → riavvio: riscontro dalle MIE registrazioni (14:50Z)

Richiesta del coordinatore (ipotesi di admin-26: runner cieco dal riavvio post-crash delle 10:01Z fino
all'alert 502 delle 14:39Z). Evidenze: `e2e_fase2/ladder_fasce.txt` (script `ladder_fasce.py`: conteggi al
minuto e campioni interi del 47331/47332, un campione per topic al minuto), query in sola lettura su
`live_now`, `tennis_live_now`, `tennis_bot_activity`, `tennis_bot_control`, `safe_strategy_scan`, `live_alerts`.

**(2) «zero tick di mercato dalle 10:01Z»: per la finestra 10:01-10:42Z le mie registrazioni lo SMENTISCONO.**

| fascia UTC | ladder 47331 (calcio) | payload distinti nei campioni | eventi | ladder 47332 (tennis) |
|---|---|---|---|---|
| 09:50 | 2842 | 9/9 | 36090788, 36090854, 36090936 (J-League, finiscono) | 858 |
| 10:00 (crash 10:00:46, ripresa 10:01:24) | 4390 | 9/9 | 36090941, 36111764, 36111770 | 1072 |
| 10:10 | 6090 | 10/10 | 36111764, 36111770 (femminili) | 1036 |
| 10:20 | 6055 | 10/10 | idem | 1075 |
| 10:30 | 6176 | 10/10 | idem | 1634 |
| 10:40 | 1198 (ultimo minuto pieno 10:41:40 = 557; 10:42:40 = 14) | 3/3 | idem | 261 |
| 10:50 | **0** | — | — | **0** |

Dopo il crash il runner pubblica ladder VIVE (prezzi e `updated_ms` che cambiano; es. 10:42:36Z HT Score
36111770 `updated_ms` 10:41:39Z) sulle due partite seguite. `live_now` dei due eventi femminili si aggiorna
(ora 14:45Z). Quelli fermi a 09:55-10:02Z sono le partite J-League FINITE (36090854/36/37/41), quindi non
sono una prova di cecità. **Tutto si ferma alle 10:42Z, INSIEME:** ladder calcio e tennis, `scan_calcio`
dello scanner (259 → 7 al minuto), il `battito` del runner (6 → 1). Nello stesso minuto le mie sonde verso
Supabase hanno iniziato a fallire con `getaddrinfo failed` / `ConnectionAborted` (sentinella, 10:41-10:48Z):
**interruzione di rete / DNS del PC alle ~10:42Z**. La cecità nasce lì, non alle 10:01Z. Gli alert 502
(14:39:12Z, «stream mercati MUTO da 14251 s»: 14:39:12 − 14251 s = **10:41:41Z**) e 503 (14:42:46Z) lo
confermano. Nuovo **crash del runner calcio alle 14:46:15Z** (alert 505, uptime 17099 s = avviato alle
10:01:16Z), riavvio n. 2, di nuovo `ORDER_MODE` «*** LIVE ***» (506) con effettivo PAPER (R-F2-C2).

**Il momento della morte della subscription (10:39:30-10:44:00Z, `morte_subscription_1040_1044.txt`, 5008
messaggi):** nessun `auto_follow`, nessun `NEW_MATCHES`, nessun errore di stream né variazione di
`mercati_sottoscritti` sul 47331 nella finestra. Il fatto è un altro: **alle 10:41:41Z TUTTI i canali tacciono
insieme**. Ultimi messaggi: safe_attivita 10:41:41, tennis_bot_stato 10:41:38-39, runner battito 10:41:30. Il
messaggio successivo arriva alle 10:42:09 (scanner_stato), poi `modo_ordini` 10:42:27 (ripubblicato), `mike_stato`
10:42:35, battito del runner 10:42:36. Quindi ~28-55 s di silenzio su processi DIVERSI (runner calcio, tennis,
Omega, Mike, Safe, scanner) nello stesso istante. È una sospensione di tutta la macchina o della rete, non un
difetto del singolo runner. Due indizi concordanti: le mie sonde verso Supabase hanno fallito con
`getaddrinfo failed` subito dopo, e Claude Code ha fermato i miei processi di registrazione «per memoria del
sistema criticamente bassa». Dopo la ripresa i battiti tornano, ma ladder/raw del runner calcio e tennis e le
decisioni dei bot tennis non ripartono più: la subscription non si è riconnessa e nessun controllo di stallo
l'ha rilevata per ~4 h (vedi l'ipotesi di admin-26 su `runner.py:1192`, non verificata da me). Numeri del
coordinatore sulle stesse registrazioni, ladder per 5 min: 10:00 1707, 10:05 2880, …, 10:35 3024, 10:40 998,
poi zero con battito vivo fino alle 10:58Z; prezzi che cambiano su 1.262887882 (3,0 → 2,66 → 2,44 → 2,42 →
2,10). **Finestra NON CERTIFICATA «runner cieco»: 10:41:41Z → riavvio dell'app. Fra le 10:01 e le 10:41Z i
controlli restano validi.**

**(3) Runner tennis / bot tennis: NON sani dalle 10:42Z.** `tennis_live_now` si aggiorna (14:48Z), ma:
nessuna riga in `tennis_bot_activity` dopo le 10:41:35Z per nessuno dei 4 bot (ultime: flb/pro 10:40:18,
scalper 10:40:21, swing 10:41:35); `tennis_bot_control` fermo alle 10:40:00Z con **12 righe attive per bot**
(tetto 5, vedi R-F2-6); ladder 47332 a zero dalle 10:42Z; `safe_strategy_scan` tennis più recente alle
14:34:51Z (14 min prima). I battiti dei servizi sono freschi (`heartbeat_at` 14:48:05Z), quindi vivi ma
senza decisioni: stesso quadro «battito fresco, dati morti». Gli ordini tennis già eseguiti
(`tennis_live_orders` flb 1, swing 7) vengono ancora riscritti ogni secondo (R-F2-7).

**(4) Effetto sulle righe già scritte del referto**
- Fino alle 10:42Z il runner calcio e il tennis erano vivi: restano validi Z4.T1-T3, R-F2-6/7, la sezione
  crash, 3-bis A (10:07Z), B Omega 120 e C Safe/Mike, P&L, D (09:34/09:59Z), freno (09:42-09:56Z).
- **Dalle 10:42Z: NON CERTIFICATO «runner cieco / rete caduta»** tutto ciò che passa dal runner calcio
  (ladder, fill flumine, specchio, registrazioni, F0 via runner), dal runner tennis e dai 4 bot tennis.
  Omega, Safe e Mike girano sul feed dello scanner (attività fino alle 14:47Z): le loro decisioni dopo le
  10:42Z restano valutabili solo con quella nota. Nel buco di rete lo scanner stesso si è fermato.
- **I miei strumenti si sono fermati**: `raccolta_db.py` ultimo giro alle 10:38Z; `ascolto_scanner.py`
  ultimo file alle 10:41Z; `ascolto_canali.py` ultimo messaggio alle 10:58:16Z. Dopo li ha fermati Claude
  Code per memoria bassa del PC. Non li ho riavviati. Dalle 10:42Z non ho registrazioni proprie.

**(5) Reperti di admin-26 riscontrati**
- «nessun ordine passato dalla coda DB»: **CONFERMATO** (R-F2-2). 0 righe in `betfair_live_order_requests`
  e `betfair_live_orders` oggi; Omega/Safe `paper_fill*:follow_assente`, Mike `paper_fill:execution_mode_rest`.
- Mike riempie in paper al prezzo limite: coerente con quello che ho visto. 5070-5075 hanno
  `avg_price_matched` = `price` richiesto e `size_matched` = size. Non l'ho confrontato col best del feed
  dell'istante: NON verificato da me.
- scalper `live_follow` senza origine: NON verificato da me.

**(1) Secondo ciclo del freno: SOSPESO**, come ordinato. Si rifà solo dopo il riavvio dell'app da parte
dell'utente.

## 0. Come si è acceso (dichiarazione obbligatoria)

- **Strumento**: il banco della fase 1, cioè il componente VERO `PannelloBot` montato in jsdom con i comandi VERI
  `creaComandiControlRoom` (come in `pages/ControlRoom.tsx`), le fetch VERE della plancia e il client Supabase VERO
  `frontend/e2e_fase1/clientVero.ts` (service role). File: `frontend/e2e_fase2/accensione.e2e.test.tsx` +
  `frontend/e2e_fase2/vitest.e2e.config.ts` (worktree). Un test per bot, lanciato UNO alla volta con `-t`.
- **Guardia in più (fase 2)**: prima del DB ogni RPC passa da un controllo. Sono ammesse SOLO `omega_activate`,
  `mike_activate`, `safe_activate`, `safe_update_params`, `tennis_bot_service_activate`, `scalper_auto_activate`
  e le letture `get_*`. Qualunque argomento di modalità `live` (`p_mode`, `mode`, `strategy_modes.*`) BLOCCA
  la chiamata PRIMA dell'invio. **Falsificazione** (test G0): `omega_activate{p_mode:live}` e
  `safe_update_params{strategy_modes.base:live}` → bloccate; `set_live_order_mode` e `omega_update_params` →
  bloccate; 0 chiamate inviate.
- **Fotografie PRIMA/DOPO** di ogni riga (select * delle 6 tabelle di controllo):
  `AUDIT_2026-09-25/e2e_fase2/accensione/A*_prima.json`, `A*_dopo*.json`, esiti `A*_esito.json` (RPC con argomenti).
- **Orari**: `AUDIT_2026-09-25/e2e_fase2/ACCENSIONE_ORA.txt`.

| bot | clic (data-testid) | RPC | DB dopo | locale / UTC | 1° ciclo del servizio / push `*_stato` running |
|---|---|---|---|---|---|
| Omega | `cr-avvia-paper-omega` | `omega_activate(p_mode=paper, goal, params interi)` | running/paper | 11:10:26 / 09:10:26Z | attività dalle 09:10:56Z; `omega_stato` con `control` running/paper 09:11:07Z |
| Mike | `cr-avvia-paper-mike` | `mike_activate(p_mode=paper)` | running/paper | 11:11:56 / 09:11:56Z | `armed` 09:12:02Z; `mike_stato` running/paper 09:12:04Z |
| Safe | `cr-avvia-paper-safe-base`, `-esatto`, `-punta` (scheda calcio), `-tennis` (scheda tennis) | `safe_activate` + 3× `safe_update_params` (strategy_modes 6/6 paper) | running/paper | 11:13:20 / 09:13:20Z | `safe_stato` running/paper 09:13:06Z |
| Safe (riaccese base/esatto/punta) | `cr-avvia-paper-safe-base/esatto/punta` (scheda CALCIO) | 3× `safe_update_params` | variants [tennis, base, esatto, punta], 6/6 paper | 11:16:16 / 09:16:16Z | vedi R-F2-1 |
| tennis_scalper / pro / flb / swing | `cr-avvia-paper-<bot>` (scheda tennis) | `tennis_bot_service_activate` ×4 | running/paper, stake 2 | 11:16:50-11:16:58 / 09:16:50-58Z | `tennis_bot_stato` running/paper 09:17:02-04Z |
| scalper calcio | `cr-avvia-paper-scalper` | `scalper_auto_activate(paper)`: strategia della riga = **maker**, stake 25 (default della UI = valori della riga, non cambiati) | running/paper | 11:17:58 / 09:17:58Z | `scalper_stato` 09:18:00Z, `auto_armata` ×2 09:18:00-01Z |

Dopo ogni accensione: `order_mode=paper`, tetto `live` (dal `.env` `LIVE_ORDER_MODE=LIVE`), `kill_switch=false`.
Tennis: `TENNIS_LIVE_ORDER_MODE` assente dal `.env` → `desktop/main.js:250` passa `PAPER`. **Nessun ordine reale
possibile**: calcio effettivo = min(tetto LIVE, scelta paper) = PAPER; ogni bot con `mode=paper`; tennis tetto PAPER.
Verificato a ogni giro della raccolta DB (nessuna riga `live` in nessuna tabella di trade/ordini: §3).

## 1. Strumenti di osservazione (SOLA LETTURA), processi avviati da me

| processo | cosa fa | uscita |
|---|---|---|
| `ascolto_canali.py 600` (python, 10 h) | websocket SENZA token su 47331-47338, non invia nulla; stati ogni 30 s e ai cambi, righe tutte, conteggi al minuto | `e2e_fase2/canali/messaggi_*.jsonl`, `conteggi_*.jsonl` |
| `ascolto_scanner.py 600` (python, 10 h) | 47336: riga intera del feed per evento ogni 4 s (gzip) → serve al ricalcolo B dallo stesso istante | `e2e_fase2/canali/scanner/scan_*Z.jsonl.gz` |
| `raccolta_db.py 600 300` (python, 10 h) | ogni 5 min: GET PostgREST (metodo fisso GET) di control, attività nuove (cursore id), trade/ordini/code/righe per partita del giorno | `e2e_fase2/db/giro_NNNN.json`, `indice.jsonl` |

Strumenti di verifica: `verifica_omega_b.py` (ricalcolo B/C Omega con le funzioni di produzione), `sintesi_b.py`,
`diff_foto.py`, `riassunto_canali.py`, `topic_canale.py`, `isp_safe.py`. Tutti in `AUDIT_2026-09-25/e2e_fase2/`.
Browser: **estensione Chrome NON collegata** («Browser extension is not connected»): nessuna lettura a video.

## 2. Tabella dei controlli (id C/U del piano/inventario)

| id | controllo | evidenza | esito |
|---|---|---|---|
| Z4.O1 | Omega: fonte e battito | `omega_stato` sul 47334 porta `control` (running/paper); `stats.last_cycle` avanza, `cadenza_battito_s=60` a riposo, `fonte_scan='canale'` (09:30Z) | OK |
| Z4.O2 | Omega legge il feed e decide | 3 ingressi (trade 117, 118, 119) con audit V3 completo; 40+ `skip` con scarto per runner | OK |
| Z4.O3 | Omega: ordini paper | righe `omega_trades` mode=paper; **nessuna** riga in `betfair_live_order_requests`/`betfair_live_orders`: fill `paper_fill_fallback reason=follow_assente` | vedi R-F2-2 (strada non uniforme) |
| 3-bis B/C Omega 117-119 | ricalcolo con `omega_v3`/`omega_service._v3_p_empirica` dagli input del DB | `B_omega_117_119.json`: p_imp, P storica e n, P_nostra, margine, EV, liability = scritti; cancello tutto vero | **OK** (+ R-F2-3, R-F2-4) |
| Z4.O-lambda | `lambda_source` | `fixture` su 117-119: il feed ha `payload.pre_ko = null` (partite J-League già iniziate all'avvio dell'app, 08:56Z) → la catena O1 ricade correttamente sulla fixture | OK (C) |
| Z4.M1 | Mike: stato sul canale | `mike_stato` con `control` running/paper; heartbeat 09:29:57Z | OK |
| Z4.M3 | Mike paper REST | trade 5070, 5071 `back Under 3.5` 5 € a 1.51/1.60, `note=paper_fill:execution_mode_rest`, `mode=paper` | OK |
| Z4.M4 | Mike uscite manuali | `uscita_proposta` green_pre (lay 5.07 a 1.49 / 5.06 a 1.58) e stato `PRE_OPEN` «uscita proposta all'utente (uscite manuali)»: nessuna lay eseguita | OK |
| Z4.M-dossier | Mike armato senza modello | 2 partite femminili (Badalona W–Granada W, Real Sociedad W–Real Madrid W): dossier `source=none`, lambda/league/`p_under35_cal` NULL. L'ingresso di Mike NON richiede il dossier (`engine.py:_entry_guard` 2435-2490); il veto M1 agisce solo all'ultimo ingresso (`valuta_veto_under35`, «non_valutabile» con P assente) | coerente col codice; vedi R-F2-5 |
| Z4.S1 | Safe stato | `safe_stato` con `control` running/paper; heartbeat 09:30:09Z | OK |
| Z4.S-esatto | Safe esatto: 2 ingressi | 342 (Iwata–Hachinohe, lay «Altro risultato Casa» 50, 2 €), 343 (Ryukyu–Ehime, lay «Altro risultato Ospite» 55, 2 €): 9/9 condizioni del manuale vere nel `meta.checks`; `fill=paper_fill:follow_assente` | OK (C dal meta; ricalcolo dal feed dello stesso istante: il registratore è partito alle 09:22Z, verifica al prossimo aggiornamento) |
| Z4.T1 | tennis auto-mode | 4 bot × 5 partite armate dal feed alle 09:17Z (`origine='auto'`, `tennis_live_follow` STREAMING) | OK; vedi R-F2-6 |
| Z4.T2 | righe per partita | tutte `mode=paper`, `dry_run=false` | OK |
| Z4.T3 | ordini tennis | `tennis_live_orders` 4001 `tennis_flb` lay 2 € a 1.02, paper, abbinato in 32 s (09:17:21→09:17:53Z), regolato −0.04 alle 09:25:02Z | OK; vedi R-F2-7 |
| Z4.T-superficie | tennis_pro superficie e fonte | attività `superficie` per partita con fonte (`mappa`/`default`) | OK nella forma; vedi R-F2-8 |
| Z4.T-scalper | tennis_scalper in gioco | `missione_blocca` «partita GIÀ IN GIOCO e gamba in-play disattivata» su 6 partite | OK (configurazione dichiarata) |
| Z4.C1 | scalper auto-mode | 2 sessioni `origine=auto`, `dry_run=true`, paper, maker, tetto 2; `stats.auto.nascono_in_dry_run=true` | OK |
| Z4.C-sniper | sniper acceso | `sniper armato (S16)` stake 10; `sniper_fire` 10 a 1.30 (min 59); `submin` a riposo; `sniper_timeout pos_s 300` → `sniper_flat_residual locked 0.5` → nuovo `sniper_fire` a 1.22 (min 64) | vedi R-F2-9 (chiusura automatica con uscite manuali) |
| Z13.2 | paper/live mai insieme | ogni riga di oggi in omega/mike/safe_trades, tennis_live_orders, tennis/scalper_control: `mode=paper` | OK (fino alle 09:35Z) |
| Z5 | tempi degli ordini F0 | la console dell'exe non è salvata in nessun file (exe lanciato senza redirezione); non si può riavviare l'app | **NON CERTIFICATO** (log assente) |
| Z6 | striscia d'esito a video | nessun browser | **NON CERTIFICATO** (a video); righe DB coerenti (fill completi) |
| Z13.4 | FRENO (1° ciclo) | `RigaFreno` VERA, guardia: solo `set_live_kill_switch` (falsificazione F0: p_on sbagliato e altre RPC bloccate). Tirato 09:42:00Z (1 clic), rilasciato 09:56:28Z (3 clic; dopo 2 ancora tirato). `e2e_fase2/freno/F1_*`, `F2_*`, `attesa.log` | Omega **OK** (3 tentativi rifiutati `kill_switch/db_kill_switch_attivo`, riserve cancellate); scalper force-flat **OK** ma R-F2-10/11; Safe/Mike/tennis **NON CERTIFICATO** (nessun tentativo nei 14 min). 2° ciclo autorizzato dal coordinatore dopo le 13:30Z |
| Z13.5 | uscite manuali = proposte | Omega: nessuna uscita discrezionale eseguita (sulle selezioni aggregate non c'è proposta: `skip proposta_uscita selezione_aggregata`); Safe: `cashout` 265 `proposed` + `exit_hold in_attesa_di_approvazione` fino al fischio; Mike: `uscita_proposta` green_pre / ko_green / `chiusura` «profit smart» mai eseguite, protezione copertura Over 4.5 ESEGUITA (automatica, come da classificazione); tennis flb: nessuna chiusura; scalper: lo sniper chiude da solo (R-F2-9) | OK salvo R-F2-9 |
| 3-bis A | feed vs libro Betfair VERO vs IPS | `sonda_libro_a.py` (login cert della sonda, `listMarketBook` EX_BEST_OFFERS ×6, IPS `get_scores` ×6, logout: chiamate elencate in `A_libro_1007Z.json`), 2 partite in gioco × 3 istanti | prezzi 3/6 identici, 3/6 con 1-2 tick di differenza su età riga 0.8-2.9 s nei primi minuti (mercato mobile; lo scanner usa la STESSA proiezione EX_BEST_OFFERS conflate 1 s, `safe_strategy/stream.py:235`); punteggio 6/6 = IPS, minuto = IPS ±1. **OK con riserva** (da ripetere su una partita calma) |
| 3-bis B Omega 120 | ricalcolo INTERO, P fusa compresa, dal book registrato (dt 0.9 s) | `B_omega_120.json`: p_mercato devigata dal `cs` registrato → `fondi_col_mercato` = 0.0176777 = p_fusa scritta; p_imp, margine 1.1208, EV, liability 47 = scritti; cancello vero | **OK** |
| 3-bis C Safe | rigioco del feed registrato nel motore di produzione `SafeEngine` (`verifica_safe_c.py`) | 09:24-09:40Z: 3516 righe; il trade 343 è preceduto dal segnale ricalcolato (09:24:48 e 09:24:53, trade 09:25:04); l'unico segnale senza ingresso (36090940 esatto Casa) è sulla partita dove Safe era già dentro (trade 342, 09:23:38). 09:40-10:10Z: 4272 righe, 0 segnali, 0 ingressi calcio (skip `pre_ko_assente`) | **OK** |
| 3-bis C Mike | parametri EFFETTIVI (`mike.config.merge_params`) e ingressi pre-match | `C_mike.json`: 5070/5071 banda 1.30-3.00, stake 5, 47-48 min prima del KO (finestra 10-60), paper | **OK** |
| Z14.2 P&L | ricalcolo indipendente di ogni posizione regolata (`verifica_pnl.py`) | Omega 117/118/119/120 +0.95 ciascuno (lay 1 € vinto, 5%), Safe 342/343 +1.90; tennis flb −0.04; 0 KO | **OK** |
| D (plancia) | hook VERO `useControlRoom` montato col client vero, guardia solo letture (`plancia.e2e.test.tsx`), confronto `confronto_d.py` | 09:34Z e 09:59Z: righe bot 9/9 = DB (stato/modalità), `cr-bot-pnl-tennis_*` = somma DB, `realizzatoOggi.paper` 6.61 = 2.85+3.80−0.04 (DB, giornata del piazzamento), posizioni a video = righe aperte DB (+ tennis e scalper) | OK; reperti R-F2-14/15 |

## 3. Cosa hanno fatto i bot (fino alle 09:35Z)

Aggiornamento 2 (10:12Z):

| bot | decisioni | ordini paper | aperti | P&L netto regolato (paper) |
|---|---|---|---|---|
| Omega | 4 ingressi (117-120), 3 tentativi rifiutati dal freno, decine di skip motivati | 4 lay CS 1 € | 0 | **+3.80** (4 vinti) |
| Mike | 2 ingressi pre-match (5070/5071), 2° Under dopo gol precoce (5072), coperture Over 4.5 (5073 1.34 € sotto il minimo, 5074 2.52 €, 5075 5.37 €), proposte d'uscita non eseguite | 6 | 6 | 0 (partite in corso) |
| Safe calcio | 2 ingressi esatto, ~10 proposte opportunità NON piazzate (`valutazione.valida=false` quando il prezzo sparisce, `opportunita_decaduta` a fine partita) | 2 lay CS 2 € | 0 | **+3.80** |
| Safe tennis | 2 ingressi (344, 345) back a 1.02 (= backMin 1.02, Q5) | 2 back 3 € | 2 | 0 |
| tennis_flb | 1 ingresso | 1 lay 2 € a 1.02 | 0 | −0.04 |
| tennis_swing | 1 ingresso (4350 back 1.78), 1 ordine PENDING | 2 | 1 | 0 |
| tennis_pro | superficie dichiarata, nessun ingresso | 0 | 0 | 0 |
| tennis_scalper | blocca in gioco (configurazione) | 0 | 0 | 0 |
| scalper | 2 sessioni fermate dal freno, poi 4-5 nuove dal feed (dry-run) | simulati | — | solo lordo dichiarato (non entra nel realizzato, per costruzione) |

## 4. KO candidati e reperti (NESSUNA correzione)

- **R-F2-1 (uso UI, da sapere): «avvia in prova Safe tennis» dalla scheda TENNIS con Safe calcio già acceso
  SPEGNE base/esatto/punta.** Riscrive `variants=["tennis"]` (A3: da `[base,esatto,punta]` a `["tennis"]` alle
  09:13:19Z; `A3_safe_dopo_punta.json` → `A3_safe_dopo_tennis.json`, cambia SOLO `params.variants`). È il
  significato dichiarato «solo tennis» (`components/controlroom/comandiBot.ts:89-99`, P15 della fase 1), non un
  difetto del codice, ma dalla scheda tennis un clic spegne il calcio senza toccarlo. Safe calcio è rimasto spento
  dalle 09:13:19Z alle 09:16:16Z; riacceso dalla scheda calcio (`A3b_*`).
- **R-F2-2 (KO candidato di UNIFORMITÀ, money-critical per la parità paper/live)**: gli ordini paper di Omega e
  di Safe calcio sulle partite NON seguite dal runner non passano da flumine. `paper_fill_fallback
  reason=follow_assente` (Omega), `fill=paper_fill:follow_assente` (Safe), `omega_service.py:2527-2547`,
  `_flumine_gate` `:2753-2791` (richiede follow `STREAMING`). L'auto-follow proattivo del runner parte solo con un
  bot collegato al canale di comando (`auto_follow.py:41-48, 857-865`); con `OMEGA/SAFE_ORDINI_VIA_CANALE`
  spenti il push `auto_follow` del 47331 dice `attori: []`, `mercati_auto: 0`, `mercati_manuali: 17`. Effetto:
  fill paper istantaneo dallo snapshot (niente bet delay, niente coda, niente specchio `betfair_live_orders`):
  il paper di quei due bot NON è lo specchio del live.
- **R-F2-3 (audit Omega)**: la chiave `meta.model.p_modello` è la P FUSA, non quella del modello:
  `omega_engine.py:1225-1229` sostituisce `probabilita` coi valori fusi prima di `omega_v3._seleziona`, che la
  scrive come `p_modello`. Trade 119: modello grezzo 0.5483% (ricalcolato) contro «p_modello» 0.6703% (= p_fusa).
  La P del modello grezzo non viene scritta da nessuna parte.
- **R-F2-4 (tracciabilità Omega)**: `p_mercato` e il book CS dell'istante non vengono salvati. La P fusa non si
  ricalcola dal DB; per 117 e 118 la p_mercato che si ricava invertendo è 1.25% e 1.67% (peso 0.65). Da ora il
  feed viene registrato (ricalcolo intero per le decisioni nuove).
- **R-F2-5 (strategia, da portare all'utente, NON un KO del codice)**: Mike entra pre-match anche senza
  dossier/modello (partite femminili, `source=none`). Il veto M1 non lo impedisce (agisce solo all'ultimo
  ingresso). 36111770: `feed_line_missing critical OU35|UNDER` ripetuto (6 volte 09:16-09:26Z) in `PRE_OPEN`
  con posizione aperta: la linea dell'Under è sparita dal feed, quindi Mike non può né valutare né chiudere
  (caso E, da seguire).
- **R-F2-6 (KO candidato tennis auto-mode)**: partita 36118619 finita (IPS `Finished` 1-2, `mercato_chiuso` di
  flb alle 09:25:02Z, riga uscita dal feed), ma alle 09:31Z `tennis_live_now.status='SUSPENDED'` (non `CLOSED`):
  `_mercato_chiuso` (`tennis_bot_service.py:492-500`) resta falso e le 4 righe restano `running`, il follow
  `STREAMING`. Intanto l'auto-mode ha armato una sesta partita (36111518, 09:25:29Z), perché `scegli_partite`
  conta solo le armate ancora nel feed: `stats.auto.armate_feed = 6` con `tetto = 5`. Da confermare al prossimo
  aggiornamento (se Betfair porta il mercato a CLOSED più tardi, si chiude da solo).
- **R-F2-7 (IO/specchio tennis)**: l'ordine 4001, già `EXECUTION_COMPLETE` dalle 09:17:53Z, viene ripubblicato e
  riscritto circa ogni 1 s (`updated_at` che cambia, 48-51 messaggi `order` al minuto sul 47332) fino alla
  chiusura del mercato. Inoltre `tennis_live_orders.placed_at` è NULL per l'ordine paper (la Z4.T3 del piano usa
  `coalesce`).
- **R-F2-8 (dato, tennis_pro)**: «ITF W35 Santa Margherita di Pula ITA» → `superficie=hard`, `fonte=default`
  («torneo sconosciuto»). Il default è dichiarato, ma Pula è un torneo su terra: la mappa non lo conosce.
- **R-F2-9 (KO candidato, noto nel referto uscite)**: lo scalper con uscite manuali CHIUDE da solo la posizione
  dello sniper (`sniper_timeout pos_s=300.1` → `min_bet_skip` ×2 → `sniper_flat_residual locked 0.5`, evento
  36090854, 09:27:43-53Z). Il gate delle uscite manuali copre solo `ScalperStrategy`, non `sniper_bot`
  (`USCITE_AUTOMATICHE_PER_BOT.md` righe 263-264). Regola del brief: «se un bot chiude da solo è KO».

- **R-F2-10 (KO candidato R3, scalper)**: a freno TIRATO l'auto-mode del supervisore ARMA sessioni nuove:
  `auto_armata` 36090936 e 36090937 alle 09:42:44Z (righe `requested`, dry_run), e `stats.auto.motivo_blocco`
  resta `null` (il freno non viene dichiarato). `scalper_service.py:745` chiama `giro_auto` (armamento
  `:455-490`, `motivo_blocco` a `:494` non riceve il freno) PRIMA di leggere il freno (`:750`); il freno ferma
  solo l'avvio del processo (`sessione_da_avviare`, `:623-627`). Nessun ordine partito; al rilascio le righe si
  sono avviate.
- **R-F2-11 (KO candidato, scalper force-flat)**: `stop: posizione NON flat dopo 30s` su entrambe le sessioni
  (`scalper_session.py:1312-1321`): il residuo dello sniper sotto il minimo (nl 0.5 / nw 0.585, `min_bet_skip`
  0.40 e 0.06) non viene appiattito (il force-flat non usa il place-and-trim) e la sessione va `stopped` con la
  posizione paper orfana.
- **R-F2-12 (design Omega)**: i rifiuti del freno consumano il budget dei tentativi della gamba (skip
  `kill_switch attempt 1..3 di max 3`, 36090944): dopo il rilascio quella gamba non si riprova più.
- **R-F2-13 (paper diverso dal live, Mike)**: la copertura Over 4.5 da 1.34 € (sotto il minimo di 2 €) viene
  riempita in paper con un fill simulato diretto (`mike/service.py:705-709`: «in paper dal fill simulato, in live
  dal place-and-trim»). Il place-and-trim di Mike non si esercita in paper: **NON CERTIFICATO** per costruzione.
- **R-F2-14 (D, due numeri per la stessa cosa)**: nello stesso view-model `totali.liabilityPaper` = 66 e
  `soldiGiornata.liability` = 64 (09:59Z): il primo conta anche il tennis_swing aperto (2 €), il secondo no. Sulla
  stessa pagina ci sono due verità per «liability paper aperta».
- **R-F2-15 (D, definizione di «oggi»)**: la plancia conta il realizzato paper per giornata del PIAZZAMENTO
  (`useControlRoom.ts:1987-2016`, «Paper invariato»). I trade piazzati ieri e regolati stamattina alle 08:57Z,
  all'avvio (Omega 116 +0.95, Mike 5063/5065/5067/5069 = +0.79, Safe 341 +0.03), non compaiono in nessun totale di
  oggi. Il piano (Z14.2) parla di «righe regolate di oggi»: la definizione va fatta scegliere all'utente.
- **R-F2-6 confermato**: alle 09:57Z la partita 36118619 (finita verso le 09:25Z) ha ancora 4 righe `running`,
  `tennis_live_now.status='SUSPENDED'`, `armate_feed=7` con tetto 5, 28 righe attive (7×4).
- **Proposta di Safe nata a bot fermo** (informativo): `safe_strategy_requests` 258 (anomaly) è stata scritta alle
  08:57:20Z, quando Safe era `stopped` (l'accensione è delle 09:13Z). Non è un'apertura.

## 5. NON CERTIFICATO (motivo)

- Tutto ciò che è «a video» (U…, `cr-*` con i numeri): estensione Chrome non collegata. Ripiego in corso: fetch e
  calcoli VERI della plancia contro il DB (passo D).
- Z5 (F0): log della console assente.
- Controlli via canale (porte di comando): spente per decisione → NON CERTIFICATO, non KO.

## 6. Orari

Accensioni: §0. Freno: tirato 09:42:00Z, rilasciato 09:56:28Z. Aggiornamento 1: 09:35Z. Aggiornamento 2: 10:15Z.
