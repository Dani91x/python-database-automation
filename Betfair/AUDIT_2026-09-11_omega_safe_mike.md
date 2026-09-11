# Indagine 11/09/2026 (sera) — OMEGA · SAFE STRATEGY · MIKE

Solo indagine, nessuna modifica al codice. Fonti: quattro revisioni indipendenti
(Mike completo; residui Omega+Safe frontend/backend/storico; contratti servizio↔UI;
uniformità di design) più verifiche dirette sui dati reali del DB.

Legenda gravità: CRITICAL = soldi/posizioni a rischio o funzione che non funziona;
HIGH = numeri o stati sbagliati visibili all'utente, o rischio in live; MEDIUM = incoerenze;
LOW = dettagli.

---------------------------------------------------------------------------------------------
## 0. Verificato SUI DATI REALI (oggi)

| # | Sezione | Gravità | Cosa | Dove |
|---|---|---|---|---|
| R1 | Safe | HIGH | I trade manuali sui mercati Over/Under (#39, #40, piazzati dalle Opportunità) NON hanno il cash out in tabella ("n/d") anche se il feed ha il mercato con quote fresche (età 2,4 s): la UI prezza il cash out solo per Match Odds, Correct Score e Half Time Score (`safeTradeBook`), non legge il blocco `ou` (né `btts`, `ht` 1X2). Il servizio invece sa chiudere (legge i mercati gol dal feed). | `frontend/src/lib/safeBot.ts:938-960` |
| R2 | Mike | HIGH | Storico Mike ROTTO nel DB: `get_mike_daily` e `get_mike_day_trades` falliscono ("function trading_daily_history(...) is not unique"): `mike_history.sql` ricrea le versioni a 7/3 argomenti delle funzioni condivise che `omega_daily_v2.sql` aveva sostituito con quelle a 8/4 (Omega e Safe funzionano perché passano tutti gli argomenti). Inoltre la versione a 8 argomenti (v4) non ammette `mike_trades`. | `migrations/mike_history.sql:11,198`, `migrations/omega_models_v4.sql:378` |
| R3 | Omega | HIGH (mia regressione di oggi) | `omega_db.upsert_daily_goal` fallisce SEMPRE con NameError inghiottito: nella modifica di oggi (`updated_at`) manca l'import di `datetime` a livello di modulo (gli altri metodi lo importano localmente). Effetto: lo snapshot dell'obiettivo giornaliero non viene scritto dal servizio (resta solo quello scritto dalle RPC di attivazione/parametri) → lo storico usa l'obiettivo corrente per i giorni senza snapshot. Fix di una riga. | `Betfair/omega/omega_db.py:553` |
| R4 | Safe | ok | Feed in tempo reale: righe delle partite in gioco aggiornate ogni 2–3 s (verificato su 5 posizioni vive). Il "non vedo cash out" è R1, non il feed. | — |
| R5 | Mike | INFO | Servizio vivo: 26 posizioni aperte in paper, liability 231 €, 64 eventi nel feed, 26 seguiti. | `mike_control.stats` |

---------------------------------------------------------------------------------------------
## 1. MIKE — errori e incongruenze

### CRITICAL
- **C1** In gioco le linee O/U della partita Mike non sono garantite nel feed: lo scanner tiene al massimo 20 eventi (quelli col minuto più alto) per i blocchi opportunità; una partita Mike al 3′ può restare senza blocco `ou` → nessuna copertura Over 4.5, nessun cash out, nessuna uscita; il cash out manuale risponde `feed_assente`. `scanner.py:52`, `service.py:690-702,819-826`, `mike/feed.py:41-46`, `mike/service.py:616`.
- **C2** Dopo il 4° gol la partita si congela: la linea 3.5 viene potata dal feed (non più "live") → `complete=False` → nessuna decisione, card ferma, cash out rifiutato; anche l'engine richiede il prezzo di ogni selezione, comprese quelle già decise. `scanner.py:465-470`, `mike/engine.py:374-399`.
- **C3 (live)** Esito REST ignoto "cancellato" dal TTL prima del check fail-closed: la gamba viene marcata `cancelled`/`error` a 60 s, esce dall'unico e dagli aggregati, il bot rientra → doppia posizione reale invisibile. `mike/service.py:658-672,719-727,811-825`, `engine.py:835-839`.

### HIGH
- **H1** Cash out manuale ignora i `cancel` (resting lay resta viva → posizione netta lay scoperta) e azzera il contesto (`ctx`) → uscite HT→FT mute; pre-KO viene letto come ciclo chiuso e il bot RIENTRA. `mike/service.py:359-382`, `engine.py:1309-1311`.
- **H2** Nessuna riconciliazione `mike_trades` ↔ `mike_events.positions`: persistenza fallita/crash dopo l'ordine = riga zombie (paper) o posizione reale orfana (live). `mike/service.py:851-857,199-235`.
- **H3 (live latente)** Gambe "resting" mai inviate all'exchange ma simulate anche in live con `MIKE_USE_FLUMINE_QUEUE=1`. `mike/service.py:280-293,732-749,676-692`.
- **H4** P&L per riga LORDO, `settled_pnl` NETTO, nessun `closes_trade_id`: KPI/stop/storico in lordo, card in netto; storico conta V/P per gamba (un ciclo greenato = 1V + 1P), chiusure non sotto l'apertura. `engine.py:607-629`, `service.py:828-848`, `mike_history.sql:91-105`.
- **H5** Log `state` a ogni tick (motivi con numeri che cambiano) + lettura integrale di `mike_trades` ogni secondo + heartbeat ogni ciclo che fa ricaricare la UI a ogni evento: rischio IO exhaustion Supabase. `service.py:770-772,409,492,507,882`, `useMike.ts:115`.
- **H6** Card ERROR e SKIPPED invisibili in UI ("Riprendi" irraggiungibile). `Mike.tsx:189-190`, `MikeMatchCard.tsx:350-358`.

### MEDIUM
- **M1** Esito delle richieste UI mai mostrato (`posizione_aperta`, `feed_assente`…). `useMike.ts:144-156`.
- **M2** `fail_stale_processing` mai chiamato: un crash blocca per sempre il cash out di quell'evento. `db.py:127`, `service.py:319`.
- **M3** 7 parametri in UI senza effetto (`max_matches`, `catalogue_refresh_s`, `min_total_matched`, `settle_confirm_s`, `skip_log_interval_s`, `stream_extra_lines`, `cover_max_overshoot_pct`); `catalogue.py` codice morto.
- **M4** "Capitale a rischio" gonfiato: somma back di apertura + lay di chiusura + cicli archiviati. Dipende da H4.
- **M5** "Se chiudo ora" mescola lordo (servizio) e netto (fallback UI). `MikeMatchCard.tsx:232-234`, `engine.py:395`.
- **M6** Giornata vs storico: "Regolate" = ultime 24 h rolling, "Trade" = ultime 200 righe all-time; solo il KPI P&L oggi è per giornata Rome.
- **M7** Fedeltà paper: coperture/chiusure senza controllo freschezza feed (fill a prezzi fantasma a scanner fermo). `engine.py:768,1181`, `service.py:156-235,365`.
- **M8** Nessun controllo `entry_hours_before_ko` ≤ `SAFE_PRE_KO_OU_HOURS`: a ramo spento il bot vede 0 candidate senza dirlo.
- **M9** Mercato VOID/abbandonato non gestito → ERROR dopo 2 h, righe `open` per sempre. `service.py:587-600`.
- **M10** `mike_history.sql` ridefinisce le funzioni condivise (vedi R2).

### LOW
- L1 `_STRATEGY_REF` inutilizzato (ordini live con `customerStrategyRef` di Omega). L2 `_DAILY_STOP_LOGGED` con giorno UTC. L3 stop giornaliero solo sul regolato, non sul bloccato. L4 partite già in gioco armate inutilmente (IDLE_LIVE → SETTLED "nessuna operazione"). L5 kind attività non mappati (`fill_resting`, `place_resting`, `settling_reverted`, `settle_fallback`, `daily_stop`).

### Test mancanti (Mike)
cash out/flatten manuale, esito ignoto + TTL, crash dopo l'ordine, in-play senza linea 3.5 dopo 4 gol, mercato void, `fail_stale_processing`, selezione decisa nel cash-out, netto vs somma righe; frontend: Trade/Attività/Regolate/Storico, cash out spento da feed stantio, ERROR/Riprendi.

**Giudizio:** paper NON ancora (prima C1, C2, H1, H5); live lontano (C3, H2, H3, H4, H6, strategy ref, poi ≥40 partite paper complete).

---------------------------------------------------------------------------------------------
## 2. SAFE STRATEGY — errori e incongruenze residue

### CRITICAL
- **C-01** KPI "P&L oggi"/Storico per giorno di REGOLAZIONE, tab Trade per giorno di PIAZZAMENTO: tre numeri diversi per la stessa giornata; anche il pannello Rischio usa due giorni (`loss_stop_active` per settled, `daily_liability` per placed). `SafeStrategy.tsx:379,752,349`, `safe_strategy_bot.sql:278-279`, `bot_db.py:196-227`.
- **C-02** Cash out PARZIALE manuale: qualunque chiusura non in errore marca il cash out "in volo" → residuo inchiudibile dalla UI (in live metà liability scoperta). `safeBot.ts:504`, `SafeTradesTable.tsx:261`.
- **C-03 (backend, live)** `cancel` dalla UI cancella una riserva in riconciliazione (`place_exception_reconciling`) → ordine reale forse vivo e non più tracciato. `bot_service.py:718-724`.
- **C-04 (backend)** `niente_da_chiudere` è TERMINALE: un'uscita (anche in perdita) senza prezzo opposto viene "inviata" e mai eseguita, liability piena fino al settlement. `bot_service.py:1308-1312`, `execution.py:575-576`. (Corretto oggi su Omega, non su Safe.)

### HIGH
- **H-01 (entrambe)** `exit_kind:'greenup'` non esiste nei backend (scrivono profit/loss): badge "CHIUSO IN GREEN-UP" e sotto-riga "Green-up" sono codice morto; i test certificano un contratto inventato. `omega_service.py:3037,3092`, `exits.py:103-104`, `MatchTradesTable.tsx:52,177,197`, `SafeTradesTable.tsx:125-130`.
- **H-03** `stats.open_liability` conta i pending in riconciliazione, la RPC `get_safe_state` no → KPI ≠ pannello Rischio. `bot_db.py:231-236`, `safe_strategy_bot.sql:280-287`.
- **H-05** Uscita automatica FALLITA definitivamente = normale "APERTO" (nessun badge). `bot_service.py:1319-1331`.
- **H-11** DayDetail somma trade attribuiti dal calendario a un altro giorno (`settled_in_day` ignorato). `DayDetail.tsx:85-86`.
- **H-14** `variants: []` sul DB → il bot non trada nulla, la UI mostra 4 strategie attive e "Salva" le riattiva in silenzio. `BotParamsSheet.tsx:253-258`, `safeBot.ts:452`.
- **H-15** Parametri rischio/uscite senza clamp in UI; il servizio clampa in memoria (es. `daily_loss_stop=50` → 0 = spento) mentre la UI mostra 50. `risk.py:83`, `BotParamsSheet.tsx:228-235`.
- **H-16** Activity log del servizio invisibile: nessun componente legge `safe_strategy_activity` (skip, risk_block, exit, settle…).
- **H-17 (backend)** `exit_failed` terminale dopo 3 tentativi (6 s in live) e `residual_exhausted`: liability viva mai più coperta. `bot_service.py:1322-1329`.
- **H-18 (backend)** Posizione viva senza riga feed: silenzio totale (Omega ha `greenup_blind`). `bot_service.py:879-880`.
- **H-19 (backend)** Una `listMarketBook` REST per posizione aperta ogni 2 s. `bot_service.py:466`.
- **H-20 (backend)** COMBO "tutte o nessuna" vale solo per le riserve: gamba fillata + gamba in errore = posizione nuda; uscite a modello rompono il lock. `bot_service.py:2383-2393`, `exits.py:689-721`.
- **H-21 (backend)** Nessun budget di ritentativi sul piazzamento automatico rifiutato → un FOK reale ogni 2 s. `bot_service.py:1471`.

### MEDIUM
- M-04 (entrambe) settlement per gamba: apertura di un green-up in utile appare "PERSO" + doppio toast. M-05 (entrambe) gamba `error` contata e "in corso per sempre". M-06 (entrambe) copertura parziale senza via manuale; anteprima cash out sull'esposizione piena. M-15 KPI "Trade aperti" conta le chiusure e ignora le `hedged`. M-16 `won/lost` della RPC per status grezzo (contratto dormiente). M-17 storico > 400 giorni → errore. M-18 header DayDetail conta righe escluse dal calendario. M-21 pannello Rischio conta opportunità, i tab contano eventi filtrati; "Investi" spento a 60 s ma riga "attuale" 30′; nessuna azione "Annulla" per le riserve pending. M-23 `market_open` legge `mo_status` per O/U, BTTS, HT. M-24 freschezza feed senza tetto duro nelle uscite/cash out. M-25 mercato sparito nel settlement: silenzio o flood. M-26 liability `hedged` contata piena. M-27 decisione a modello al lordo della commissione. M-28 `exit_hold` riscritto ogni ciclo (motivo con numeri). M-29 `aggregates()` legge tutta la tabella ogni 2 s. M-30 modelli costruiti una volta: "Salva" non li aggiorna. M-31 size minima Betfair 2 € non gestita nel REST live. M-32 `opps_min_confidence/edge` senza clamp (valore non numerico = bot "morto" per la UI). M-33 chiusura orfana senza sorelle.

### LOW
L-01 `meta.hedging` letto ma mai scritto. L-02 ore senza fuso in tabella; commissione della tabella dal parametro corrente e non dal trade. L-04 "prec." fuorviante in "mostra tutte"; `hedged` contate come vive; oltre 200 righe le chiusure diventano orfane. L-07 badge inglesi in `SignalCard`, errori senza dettaglio, hold con chiavi mai scritte, step stake senza minimo 2 €. L-09…L-15 backend (meta sovrascritto negli errori, reconcile paper che conferma qualunque pending, `locked_pnl` sul parziale, bo5 tennis, dedup log, TTL cache λ, chiavi Omega usate dal codice condiviso, manuale senza check SUSPENDED/freschezza).

---------------------------------------------------------------------------------------------
## 3. OMEGA — errori e incongruenze residue

### HIGH
- **H-02** `pending` in riconciliazione (ordine live a esito ignoto) è un normale "IN CORSO" e sparisce dalla liability della RPC (`is_placed=false`): KPI ignora un lay reale forse vivo, la tabella lo conta. `omega_models_v4.sql:341,354-366`, `MatchTradesTable.tsx:56`.
- **H-04** Green-up FALLITO (cooldown), CIECO, residuo abbandonato, TENGO: invisibili sulla riga (`meta.greenup.failed`, `greenup_hold`, `residual_dropped` mai letti). `omega_service.py:3021-3031,3155,3204,2947-2961`.
- **H-06** "Liability aperta" conta come rischio una PERDITA BLOCCATA a copertura completa (`greatest(0,−if_win)` senza distinguere `complete`). `omega_engine.py:387-397`, v4 `:337-340`.
- **H-07** Default UI ≠ servizio: `model_calibration:'auto'` (UI) vs `'off'`; `greenup_risk_cap 0.10` vs `0.15`; "Salva" scrive l'intero oggetto → riaccende il calibratore. `omega.ts:252,258`, `Omega.tsx:158,275`.
- **H-08** Due "operazioni oggi" e due V/P nella stessa card (KPI dalla RPC, riepilogo dal client che conta `error`, riserve, orfane, partite vive di ieri); `won_today/lost_today` della RPC mai letti; equity "giornata" include regolati ieri. `Omega.tsx:452,471,325`, `omegaMatches.ts:151-176,238`.
- **H-09** `upsert_daily_goal` non funziona mai (vedi R3). **H-10** `goal_snapshot=false` perso dal client: obiettivo di fallback giudicato come storico (calendario ●/○ e "centrato" falsi). `dailyHistory.ts:137-168`, `DailyCalendar.tsx:62-64`.
- **H-12 (backend)** Paper via coda flumine: errore della coda = FILL PIENO al prezzo della riserva (paper ≠ live, "a risultato noto"). `omega_service.py:1508-1510,1464-1482`.
- **H-13 (backend)** Il retry di gamba (3×/30 s) NON copre il percorso flumine (default): un FOK ucciso brucia la gamba per tutta la partita. `omega_service.py:1453-1462`.

### MEDIUM
- M-01 30+ kind di attività non mappati (badge grigio con chiave inglese, anche se `critical`). M-02 `activityLine` legge chiavi che il backend non scrive (`msg`, `wait`, `attempts`). M-03 etichette green-up scambiate ("conferma" vs prezzi non disponibili; "attesa" vs TENGO). M-07 MissionCard: `hedged`/`error` come "in gioco" con badge inglese. M-08 MissionPanel: giorno locale vs Rome, seconda barra con formula diversa, `dayGoal` mai salvato. M-09 clamp/unità UI ↔ `_SPEC` divergenti (`greenup_ev_margin` in EUR etichettato 0-1, `max_attempts` min 1 vs 0…). M-10 19 chiavi della whitelist senza UI; `model_use_yellow_cards` inerte. M-11 se `delete_trade` fallisce, in paper la riserva senza fill viene confermata dal reconcile. M-12 λ di ripiego persistiti annullano il TTL. M-13 posizione `open` con mercato mai CLOSED: nessun allarme. M-14 `reconcile_pending` azione `error` sovrascrive il meta. M-19 cash out manuale: la chiusura dice "Chiusura", mai "Cash out". M-22 attività "di oggi" = ultime 60 righe filtrate.

### LOW
L-01 `meta.hedging` mai scritto. L-02 ore senza fuso; commissione della tabella dal form. L-03 "Eventi oggi"/"Target" da `stats` stantii a bot fermo. L-05/L-06 backend: gialli assenti nel green-up, cache `None`, `_LEG_RETRY` senza spurgo, log mancanti (conferma paper, `residual_dropped`, `open→hedged`), `list_trades` non paginata, fasi 2-3 di `run_once` non protette, motore v1 senza dedup.

---------------------------------------------------------------------------------------------
## 4. STORICO (condiviso)
M-17 finestra > 400 giorni → errore. M-18/H-11 DayDetail vs calendario. M-20/R2 overload delle funzioni condivise (Mike). L-08 testi obsoleti, `hedged_closed` conta pending, `commission_paid` mai scritto, obiettivo "ultimo vince".

---------------------------------------------------------------------------------------------
## 5. DESIGN — matrice e mancanze (uniformità)

Vedi la matrice completa nel rapporto dell'agente design (allegata sotto). Sintesi delle 20
mancanze per impatto:
1. Formati monetari misti nella stessa vista (`+€12.50` vs `+12,50 €`), 38 formatter duplicati.
2. Quote con punto vs virgola.
3. Stati in inglese sotto gli occhi del trader (SignalCard, MissionCard, ManualPanel, toast).
4. Etichette stato divergenti ("CHIUSO A MERCATO" vs "CHIUSO"; "Liability aperta" vs "Capitale a rischio" vs "responsabilità"; "Cash out" vs "Cash-out").
5. Omega senza banner modalità né salute scanner/servizio.
6. Attività del servizio: assente in Safe, non filtrata in Mike, stili diversi.
7. Tab Trade di Mike povero (niente chiusure, cash out, live, uscite, toggle oggi/tutte).
8. KPI e giornata operativa non allineati (obiettivo/barra solo Omega; KPI Omega nascosti nel tab Automatico).
9. Tab: naming, ordine, sticky, emoji diversi.
10. Tabella Safe senza risultato reale, bordo esito, "prec."; ora senza fuso.
11. Equity curve duplicata; Mike senza curva; semantiche diverse.
12. Tre pannelli parametri con tre UI (Default solo Safe, validazione solo radar).
13. Cash out Mike fuori standard (nessun dialog/parziale/conferma LIVE).
14. Toast di regolazione con tre formati.
15. Colori d'accento incoerenti (verde/oro/teal).
16. Loading/empty diversi.
17. Accessibilità (toggle senza aria-pressed, tab con emoji).
18. Performance (poll per card, 2000 trade a ogni evento, raggruppamenti ripetuti, nessun memo).
19. Mappe etichette triplicate.
20. Copertura test disomogenea (Mike quasi senza test di pagina).

Architettura proposta: `lib/format.ts` + `lib/tradeStatus.ts` + `lib/equity.ts` (fondamenta pure),
componenti condivisi in `components/trading/`: `PageShell`, `BotHeader` (+ `ServiceHealthChip`,
`ModeToggle`), `ModeBanner`, `LiveConfirmDialog`, `StatTile/KpiRow`, `DayBar`, `PositionsTable`
(primitive da `MatchTradesTable`, layout 'match' per Omega/Mike e 'list' per Safe),
`CashOutButton` + `EventCashOutButton` (Mike), `ServiceActivityFeed`, `EquityCard`,
`ParamsSheetBase` spec-driven, `EmptyState`, `TradingHistory` esteso. Struttura di pagina unica:
Shell → Header → Banner → Giornata → KPI → Tab (Oggi · specifici · Storico). Ordine dei passi:
formatter e mappe → shell/header/KPI (Mike → Safe → Omega) → DayBar → PositionsTable →
ActivityFeed → cash out Mike → ParamsSheetBase → terminologia/tab/a11y → performance → test.

---------------------------------------------------------------------------------------------
## 6. Priorità consigliata (prima di qualsiasi live)
1. R3 (import mancante, una riga), R1 (cash out O/U in UI), R2 (storico Mike / funzioni condivise).
2. Safe C-02, C-03, C-04, H-17, H-21; Omega H-02, H-12, H-13; Mike C1, C2, C3, H1.
3. Coerenza dei numeri: Safe C-01/H-03/M-15, Omega H-06/H-08/H-07, Mike H4/M4.
4. Visibilità degli stati critici: H-01 (green-up), H-04/H-05 (fallimenti), H-16/M-01 (attività), Mike H6.
5. Uniformazione design (piano §5).
