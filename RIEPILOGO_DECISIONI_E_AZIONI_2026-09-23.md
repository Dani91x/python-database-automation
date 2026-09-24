# RIEPILOGO PER L'UTENTE — decisioni da prendere e azioni da eseguire (23/09/2026, VERSIONE DI FINE GIORNATA)

## A. AZIONI TUE (nell'ordine)
1. **Migrazione action (SQL, Supabase → SQL editor)**: `migrations/actions_57014_2026-09-21_DA_APPLICARE_DALL_UTENTE.sql`
   - blocco A `DELETE FROM analytics_snap_staging` (oggi 67.244 righe): INDISPENSABILE al flush a fette;
   - blocco B `ALTER FUNCTION ... SET statement_timeout='120s'` su `flush_analytics_snap_staging`,
     `bulk_update_prediction_results`, `leagues_needing_retrain`: CONSIGLIATO (oggi 2 leghe non scritte per 57014 sul flush);
   - blocco C (drop di 4 indici inutilizzati su `fixture_predictions`): CONSIGLIATO, riduce ~0,2 s/riga in scrittura;
     prima verifica che nessuna query rara di UI usi i GIN;
   - blocco D `ANALYZE match_odds`: leggero, a DB scarico; blocco E (indice composito): solo dopo EXPLAIN.
2. **Riavvio dell'app desktop** (le 14 migrazioni bot del 16-18/09 sono già applicate; il codice su master è nuovo).
3. **Verifica A VIDEO con me (cancello C2)**: bot in PAPER, canali spenti, le zone della Control Room contro i tuoi 10 ordini
   del 18/09 + i 3 fix di oggi (saldo, P&L chiuse a netto di ciclo, «se chiudo ora» colorato).
4. **Prova a secco C5 (il classificatore mi ha negato di avviare il processo)**: nel repo, da PowerShell, con l'app spenta:
   ```
   $env:SAFE_STRATEGY_LOCK_PORT="47415"; $env:SAFE_STRATEGY_STREAM_CONNS="1"; Remove-Item Env:SAFE_SCAN_CANALE -ErrorAction SilentlyContinue
   .venv\Scripts\python.exe -m Betfair.safe_strategy.service --dry > prova_f0.log 2>&1      # 20 minuti, poi Ctrl+C
   $env:SAFE_SCAN_CANALE="1"; $env:SAFE_SCAN_WS_PORT="47436"
   .venv\Scripts\python.exe -m Betfair.safe_strategy.service --dry > prova_f1.log 2>&1      # 30 minuti; dopo 15 min, in un'altra finestra:
   .venv\Scripts\python.exe -m Betfair.safe_strategy.tools.sonda_canale_scan_2026_09_18 --porta 47436 --minuti 15 --ogni 60 > sonda_f1.log
   ```
   poi mi dai i tre log e io li leggo contro i criteri (§9 di `Betfair/safe_strategy/CHECKPOINT_AL_MS_F0_F1_2026-09-18.md`).
5. **Accensione dei canali «al ms»** (dopo C5, uno per volta, nel `.env`): `SAFE_SCAN_CANALE=1` → riavvio → `MIKE_CANALE_POSIZIONI=1`,
   `OMEGA_CANALE_POSIZIONI=1`, `SAFE_CANALE_POSIZIONI=1`, `TENNIS_BOT_CANALE=1` → `SAFE_BOT_LEGGE_CANALE=1` → `*_SVEGLIA_CANALE=1`
   → `SAFE_BOT_GIRO_VELOCE=1`. Rollback = togliere la variabile.
6. **Recupero dati action** (da GitHub → Actions → Run workflow, uno alla volta, MAI insieme):
   `Today Predictions Backfill` con `date=2026-09-19` (ancora ~41 fixture senza ML) e `2026-09-20` (in corso ora);
   `Predictions Results Backfill` con `date=2026-09-18 … 2026-09-22`.
7. **Giornata paper intera (C7)** con tutto acceso: la fai partire tu dalla UI; io produco il referto forense il giorno dopo.

## B. DECISIONI (ognuna con la mia proposta)
Action/DB
- B1 Blocchi B/C/D/E della migrazione: proposta = A+B+C subito, D a DB scarico, E dopo EXPLAIN.
- B2 Fan-out delle classifiche anche nel TRAINING (cambia i modelli): proposta = sì, su un ramo, con confronto BSS prima/dopo.
- B3 Supabase 30/10: da ora ogni migrazione che crea una tabella porta `GRANT ... TO service_role` (+ sequenza) e
  `GRANT SELECT TO authenticated` se la UI la legge: proposta = regola scritta in CLAUDE.md + template di migrazione.
- B4 Sicurezza inversa: 13 tabelle storiche senza RLS con `anon` a pieni poteri e chiave anon pubblica; viste `v_*`
  senza `security_invoker`; bot Telegram cieco su `fixture_predictions`: proposta = REVOKE a `anon` su quelle tabelle
  (bozze nel referto `IMPATTO_SUPABASE_GRANT_2026-10-30.md`) dopo aver verificato chi le legge.
- B5 `omega_activity` senza realtime (mai funzionato dal 12/09): proposta = `GRANT SELECT TO authenticated` + policy.
Bot
- B6 Omega: cash-out globale ucciso → il bot riapre (ft_cs al 74'): tenere o bloccare la partita come «chiusa dall'utente»?
- B7 Mike copertura Over 4.5 sotto minimo .it: 2 € pieni / passiva al primo tick / fail-closed.
- B8 Place-and-trim al centesimo sulle punte .it: misurato solo multipli di 0,50 €; `consenti_replace=True` di default
  contro INTERFACES.md: allineare il documento o il codice?
- B9 Scalper calcio: non certificato dal banco ma può piazzare; `run_scalper_live.py:227` senza guardie: bloccare l'ingresso,
  certificarlo, o dichiararlo fuori perimetro.
- B10 Quattro strade verso ordini reali (coda DB, canale 47331, runner calcio senza `avvio_app`, strumenti REST):
  proposta = una sola (coda DB) e le altre chiuse o guardate allo stesso modo.
- B11 `LIVE_ORDER_MODE` congelato all'import in `runner.py` (worker ordini registrati una volta): accettare o correggere.
- B12 P&L di giornata dei 4 bot tennis sul canale: A (RPC unica a 15 s, +4 letture/min) / B (+16) / C (nulla) / D (RAM + semina).
- B13 I 4 bot tennis non legano ingresso↔uscita (`tennis_live_orders`): colonna di catena scritta dal servizio, o raggruppare
  per (bot, market_id, selection_id)?
- B14 Commissione nel P&L mostrato: oggi LORDO; Betfair applica il 5 % sul netto di mercato (+0,20 → +0,19).
- B15 `get_safe_state` a 200 righe paper+live: filtro `p_mode` o limite più alto (evita chiusure «orfane» nei giorni pieni).
- B16 Bottone «Chiudi» della Control Room = RPC Safe per qualunque bot (Omega/Mike): cablare per bot o nascondere.
- B17 «Prezzo visto al clic» solo per le opportunità, mai per le chiusure Safe; assente in `omega_request_approve`.
- B18 Runner calcio/tennis che pubblicano prima della scrittura (A7); `nan` sul percorso manuale storico di `_request_place`;
  proposte da anomalie effimere; tolleranza 2 % sul prezzo delle proposte; barra di giornata con i 4 bot tennis.
- B19 Safe tennis è stato LIVE dal 14 al 22/09 (righe `mode=live` nel DB) mentre la regola del 18/09 diceva «LIVE niente»:
  scelta tua, la registro; il codice di oggi è a parità sul banco ma la certificazione globale (C8) non è ancora firmata.
- B20 Codice non tracciato: `strategy_no4/` e `Betfair/stream/trading/tools/test_pat_dal_vivo.py` (piazza ordini reali):
  archiviare/committare/lasciare.
- B21 CI settimanale che riscrive `Betfair/money_management.py` e lo committa su master: accettare o portarlo fuori dai bot.
- B23 Proposte: una proposta approvata dopo 120 s dalla creazione viene rifiutata come «richiesta vecchia» anche con clic
  fresco (`_request_age_s` guarda `created_at`, che l'approvazione non aggiorna): proposta = misurare l'età dal CLIC
  (`approved_at`), non dalla creazione; il tetto di 120 s resta.
- B24 Anomalia sparita ma approvata col prezzo visto: oggi l'ordine parte se il prezzo è in tolleranza (coerente con
  «prendiamo il numero che vedo»): confermare o ricontrollare `detect` al clic.
- B25 Combo approvata con una gamba FOK uccisa: `_unwind_combo` apre una chiusura `origin='auto'` sulla gamba
  `manual` del trader (tutto-o-niente contro «il bot non tocca le righe del trader»): quale delle due regole vince?
- B26 P&L mostrato: lordo (oggi) o netto della commissione Betfair (5 % sul netto di mercato)? [= B14]
- B27 `get_safe_state` 200 righe paper+live insieme [= B15]; realtime `omega_activity` muto [= B5].
- B28 Omega, sveglia dal canale (B-2 del revisore B): ora sveglia SOLO le partite con posizione VIVA (open/pending),
  le candidate solo valutate restano a `poll_interval_s` (20 s); prima ogni riga di partita seguita faceva fino a 12
  `run_once`/min con letture DB. Proposta = tenere così (l'ingresso di Omega è a probabilità, non al tick; le USCITE
  restano al ms); alternativa = pavimento 10 s per le candidate.
- B29 Banco CP1 severo (B-3): residuo/prezzo medio NON scritti = violazione; il CHIESTO accettato è `order_type.size`
  OPPURE abbinato+residuo (place-and-trim) e `size_requested` entra nelle credenze del banco e di Mike: scelte del
  delegato, ratificate da me sul replay (Mike 15/15, 0 violazioni). Da confermare tu.
- B30 Today: paracadute assoluto `_DB_MAX_FAILED_REQUESTS_TOTALE=300` (50 fixture × 6 tentativi, ~26 min di attese al
  peggio) sopra i freni a finestra scorrevole: il valore NON è misurato sui volumi veri; proposta = tenerlo e leggerlo
  nei 7 giorni di monitoraggio (A4).
- B31 Mike esiti ordini dal canale: Mike esegue in REST (`MIKE_USE_FLUMINE_QUEUE` spento) e i suoi ordini non entrano
  nel blotter 47331: coda flumine anche per Mike (una sola strada, = B10) o sottoscrizione ordini lato runner?
- B32 GitHub Actions: «un dispatch alla volta» (il DB si è saturato con job manuali concorrenti): regola scritta nel
  README delle action o `concurrency` di gruppo unico fra workflow diversi?
- B33 Ancora sulla vecchia via (DB a 2 s, non canale): `SelectionChartPanel`, `MultiLadder`, `StandaloneLadder`;
  `subscribeLive*` di altre pagine; doppio client Omega su scan_feed; `now` come battito: portarli sul canale (Sonnet,
  piccoli) o lasciarli finché non servono in live?
- B34 `.env`: `LIVE_ORDER_MODE=LIVE` è presente (tua scelta): resta? Con «LIVE niente» del 18/09 sarebbe `PAPER`.
- B22 Pulizia dei 20+ worktree (rmdir delle junction, poi remove) e rami tecnici: quando.

## C. STATO DI CERTIFICAZIONE (fine giornata 23/09)
- **Codice**: master locale `9874b33` (sopra `a130274`), push a fine serata dopo `git fetch`. Suite: pytest `Betfair/`
  5426 verdi + 1 xfail; Prediction+pipeline 151; tsc 0; vitest 3173 verdi / 30 saltati. `frontend/dist` ricostruito.
- **Revisioni del diff di oggi**: REVISORE A (action/UI/canale UI) e REVISORE B (bot/banco/canale): 0 bloccanti;
  3 GRAVI di B (guardia runner con comandi accumulati; sveglia Omega 12 giri/min; CP1 falso verde) CORRETTI e
  falsificati (13 mutazioni mie rosse); 5 fix di A integrati (P1 con paracadute, P2, F1, F2, F3).
- **Banco (C3/C4)**: parità con i referti precedenti, scenario `chiusura-abbinata-in-parte` con CP1 SEVERO: numeri
  finali in `CRONOSTORIA.md` (Mike 15/15, 0 violazioni; Omega, Safe ×3, Safe tennis: vedi ultimo checkpoint).
- **C5 F0/F1** fatti (criteri rispettati); F3-F6 a secco NON fatti (serve l'app viva e il tuo permesso: azione A4).
- **NON certificato**: C2 a video, C7 giornata paper, C8 firma globale. **Niente live** finché C8 non è firmata.
- **Voto e aspettative**: nel messaggio di chiusura.

---
# AGGIORNAMENTO 24/09/2026 (fine giornata)

## A. AZIONI TUE, nell'ordine (tutte nello SQL Editor di Supabase, un file alla volta, poi riavvio dell'app)
1. `migrations/live_order_mode_control_2026-09-24.sql` — INDISPENSABILE PRIMA del riavvio: senza, il modo ordini vale
   OFF (nessuna apertura, nemmeno paper; le chiusure passano). Poi l'interruttore «Ordini reali OFF/PAPER/LIVE» in Control Room.
2. `migrations/tennis_bot_control_mode_2026-09-24.sql` — colonna `mode` (default paper) per i 4 bot tennis: un bot in
   paper non piazza mai ordini reali qualunque sia il runner.
3. `migrations/safe_request_modalita_manuale_2026-09-24.sql` — barriera SQL allineata: senza, con Safe in LIVE e «a
   mano» in paper l'ordine a mano viene rifiutato (blocco sicuro, ma non funziona).
4. `migrations/pnl_betfair_reale_2026-09-24.sql` — colonne del P&L reale da Betfair + totale di giornata + RPC tennis.
5. Sicurezza DB: `migrations/sicurezza_db_2026-09-24_BLOCCO_1_zero_rischio.sql` (subito), poi BLOCCO_2 e BLOCCO_3 dopo
   la verifica a video, con `SELECT * FROM sicurezza_bk.verifica_bN()` e la checklist di `SICUREZZA_DB_2026-09-24.md`.
6. Riavvio dell'app → verifica a video (C2) → prova a secco C5 → recuperi action → giornata paper (C7) → firma C8.
   Interruttori nuovi nel `.env` (tutti SPENTI di serie, accendere solo dopo C2): `MOTORE_ORDINI_CANALE=1` (motore ordini
   a evento nel runner calcio), `SAFE_ORDINI_VIA_CANALE=1` (Safe sul canale di comando: NON accendere finché il motore
   non serve il sotto-minimo), `LOCAL_CHANNEL_ORIGINS` (solo se usi il dev da browser).

## B. DECISIONI NUOVE (24/09)
- D1 `customerOrderRef` uguale al ref del comando: SCONSIGLIATO dal motore (flumine riconosce i suoi ordini da
  name_hash+id; il ref vive nel diario locale e negli eventi). Proposta = lasciare così.
- D2 Scalper: dopo un rifiuto lo slot torna IDLE e può ritentare al book dopo (prima il TTL di 600 s frenava per
  sbaglio). Serve un freno ai ritentativi come il `_freno` dei bot tennis? Tocca la strategia: decidi tu.
- D3 I 4 bot tennis non hanno un percorso di chiusura manuale: il «Chiudi» è disattivato con motivo. Costruirlo tocca
  le loro macchine a stati: decidi tu.
- D4 Place-and-trim dal canale di comando: oggi un place sotto il minimo è rifiutato (`submin_non_percorribile`), anche
  in paper. Da costruire come macchina a stati in RAM nel motore (F-successiva).
- D5 Gamba LAY lasciata dalla combo: con «avvisa e proponi» resta la responsabilità (quota−1)×stake finché non
  approvi la copertura proposta. Con «automatico» la chiude il bot come prima.
- D6 «Avvisa e proponi / automatico» per Omega (uscite di protezione: oggi SOLO proposte, ordine del 17/09) e Mike
  (coperture/green-up): in coda, stesso schema di Safe. Confermi che lo estendo?
- D7 Tennis: il gate live per partita ha UN solo confirm (non due): basta o ne vuoi due?
- D8 Telegram con chiave di servizio + webhook protetto; MFA sul login owner; lead della landing (tenere/chiudere).
- D9 Reperti del motore aperti: place-and-trim (D4), `_start_submin` con ref fisso, latenze/concorrenza dal vivo.
- D10 Proposte al ms: la parte React (hook sul ladder, semaforo, scheda chiusure senza blocco «prezzo cambiato», scheda
  Omega) NON è fatta: è il primo lavoro di domani (STATO_RIPRESA del delegato, voci A-G).

## C. PROMEMORIA (richiesto da te)
- Applicare i blocchi di sicurezza DB (B1 subito, B2/B3 dopo C2) e decidere D8.

## D. ACTION «Predictions Results Backfill» (24/09 pomeriggio): cosa applicare e come rilanciare
Cause trovate sul DB vero: (1) `enrich` leggeva `analytics_signals` per lega con OFFSET e il piano scorreva TUTTO
l'indice primario (945 mila righe) → 57014 anche a blocchi di 25; (2) `bets`: la funzione `refresh_analytics_bets_range`
aveva `statement_timeout = 0`, quindi dopo il timeout del client (600 s) continuava sul server (media 439 s per giorno,
massimo 49 minuti) e i giorni successivi si accodavano; in più ricostruiva le quote bookmaker con un triplo unnest JSON
per tutti i fixture del giorno e ripeteva 3 volte lo stesso sottoselect.
1. Applica, nello SQL Editor, in quest'ordine, un file alla volta:
   - `migrations/analytics_signals_idx_league_id_2026-09-24.sql` (CREATE INDEX CONCURRENTLY: fuori da una transazione;
     dura qualche minuto su 945 mila righe; nessun dato cambia).
   - `migrations/refresh_analytics_bets_range_v2_2026-09-24.sql` (nuova funzione con stessa firma, tabella di controllo
     `book_odds_cache_fonte`, timeout server 600 s, funzione `_diag` per fase). Poi verifica di sola lettura:
     `select * from refresh_analytics_bets_range_diag('2026-09-20','2026-09-21');` dentro `begin; ... rollback;`
     (deve finire in pochi minuti e mostrare i tempi per fase) — la faccio io se preferisci.
   - `migrations/fixture_predictions_drop_idx_doppione_2026-09-24.sql` (indice doppione della pkey, fuori transazione).
2. Rilancia a mano da GitHub → Actions → «Predictions Results Backfill» → Run workflow, UNA volta, con `date` vuota
   (finestra di 4 giorni) e `leagues` vuoto; se vuoi recuperare SOLO le 10 leghe saltate ieri: `leagues=292,293,653,251,401,164,253,489,650,243`.
   Atteso: step `enrich` e `bets` verdi, gate verde, zero 57014 nel log. Poi io rileggo il log e i tempi in
   `pg_stat_statements` (massimo sotto 600 s).
3. Se `bets` dovesse ancora fallire con la v2: il log dice la fase (fixture_finestra / quote / delete / insert) e il
   tempo: da lì si decide, senza indovinare.
- D11 Scalper, reperto S3 del banco (verificato sul replay della partita 35797769): a fine sessione il bot chiude
  'done' con un residuo accettato dall'anti-churn (−0,20/+0,40) SENZA dichiarare «posizione NON flat» (gli eventi
  `flatten_residual*` non portano il messaggio; `_strategy_flat` guarda solo lo stato dello slot, non l'esposizione).
  Correzione minima proposta: aggiungere il messaggio di dichiarazione ai due `_emit` (`scalper_bot.py:1871,1891`); più
  robusta: calcolare l'esposizione dal blotter prima dello stato finale in `scalper_session.py:~1121`. Decidi tu.
