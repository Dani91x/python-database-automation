# CRONOSTORIA — punto d'ingresso unico del lavoro (ordine dell'utente, 17/09/2026)

> **Regola.** Una sezione per giornata, in ordine cronologico. Ogni sessione LEGGE l'ultima
> sezione all'avvio, VERIFICA di persona lo stato dichiarato (git, DB in sola lettura, suite,
> app) e riparte dal «punto di ripresa». A ogni task certificata dal coordinatore si aggiunge un
> checkpoint qui, non a fine giornata. Un lavoro non scritto qui non è finito. Metodo: il
> coordinatore (sessione principale) delega a Opus 5 (costruzione complessa) e Sonnet 5
> (revisioni, fix piccoli, audit) e verifica di persona: diff, test, replay, falsificazione in
> entrambe le direzioni. Standard completo: `~/.claude/rules/sessione-coordinatore-cronostoria.md`
> e `CLAUDE.md` §«Cronostoria e metodo di sessione». I documenti di dettaglio (HANDOFF_*,
> PIANO_*, CHECKPOINT_*) restano: questa cronostoria li indicizza.

---

## 2026-09-16 — Certificazione definitiva (giornata intensiva)

Cronaca completa e certificata: `HANDOFF_2026-09-16_SERA.md` (punto di ripresa, migrazioni,
procedura) e gli «Esito …» di `PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md`. Standard dei bot:
`PROCESSO_STANDARD_BOT.md` (§6 copertura, §7 catalogo errori, 37 voci).

- Consegnato e certificato dal coordinatore: Fase 0, Fase A (avvio senza bot), Fase B-1
  (interruttori, stake per strategia), F0 (runner paper+live per riga), banco comune C.0/C.0-bis/
  C.0-perf, consapevolezza ordini C.12a/b/c, Mike (taker, ko_green appoggiata, mai due lay, mai
  sovracopertura, cash-out globale, chiusura fuori app, famiglia K), Safe calcio e tennis (S1, S2,
  K), Omega (O1, O1-bis, V3 in ombra), E.1, C.8 progetto, C.9, C.10, C.11.
- Chiusura: commit `1ee7624` pushato (23:44). Suite backend 3908 verdi, frontend 2503, tsc 13
  preesistenti. Registro banco: 6 bot certificabili su 11.
- Aperti: 6 migrazioni da applicare (utente); reperti §6 dell'handoff; decisioni pendenti
  (soglie selezione aggiuntiva ESATTO, bande BASE/PUNTA, Omega paper v3 in ombra + ingresso
  passivo = modifica di strategia, serve ordine).

## 2026-09-17 — Ripresa: verifica dello stato, referti di oggi, migrazioni corrette

### Stato di partenza (verificato di persona alle 09:30)
- Git: master = origin/master = `1ee7624`; niente da pushare. App desktop chiusa.
- DB (sonda in sola lettura, PostgREST): NESSUNA delle 6 migrazioni del 16/09 applicata.
  Mike ancora `running/live` nel DB (stake 5, tetto 2); Omega e Safe `paper/stopped`; cap Omega
  tutti a zero; Safe `max_open_trades`=0 e `daily_liability_cap`=0.
- Suite backend: 4173 verdi (con `-x` un rosso instabile, vedi checkpoint 3).

### Checkpoint certificati dal coordinatore
1. **Referto Mike di oggi = ieri** (replay `certifica mike`, pool 3): 35760084 tutti i 13
   scenari 0 violazioni (33 controlli, mai sollecitato solo A2 con causa provata); 35674515
   base+taker 0 violazioni (J2 ×7, J4 ×5, J5 ×283); 35777617 gol-precoce+base 0 violazioni;
   `_synth_mike_reingresso` 0 violazioni, H1 e H2 ×1 verdi. Referti in scratchpad della sessione.
2. **Referto Safe tennis di oggi = ieri** (terna): 35792939 15/15 pulite (34 controlli, 4 mai
   sollecitati T7/T7-APPROVAZIONE/T10/L2); 35795560 15/15 pulite, T7 ×70; 35790650 15/15
   pulite (10 mai sollecitati: uscite in profitto).
3. **Banco comune, difetto corretto** (Sonnet 5, verificato e falsificato dal coordinatore):
   `certifica.py` sommava nel totale e nell'exit code anche le voci `-DICHIARATA`/
   `-APPROVAZIONE` (35795560: «69 violazioni totali», exit 1, con 15/15 pulite). Ora
   `violazioni_effettive` + `esito_del_banco` (calcolo unico per riga ESITO e `return`); test
   `Betfair/stream/tests/test_certifica_esito_dichiarate_2026_09_17.py` (7, di cui 2 che
   chiamano `main` vero). Falsificazione del coordinatore: funzione senza esclusione → 4 rossi;
   `main` che ricalcola a mano → 1 rosso. Replay tennis 35795560 rieseguito: exit 0, 0 totali.
   Stesso delegato: `test_stall_restart_rinviato_con_ordini_vivi` falliva se il PC era acceso da
   meno di 15 min (`_RAW_STALL_LAST_RESTART=0.0` contro `monotonic()` vero); ancorato al clock,
   verificato con uptime finto 100 s. Suite backend dopo: vedi «Numeri di chiusura».
4. **Revisione statica delle 6 migrazioni** (Sonnet 5, `migrations/APPLY_ORDER_2026-09-16.md`,
   verificata dal coordinatore sul punto critico): **regressione reale nella migrazione 3**
   (`safe_cash_out_globale_e_cap_automatico`): la nuova `safe_request` perdeva la barriera di
   modalità del 13/09 (`v_req_mode`/`v_ctrl_mode`, RAISE «modalità non corrispondente»).
   Corretta (Sonnet 5) copiando il corpo del 13/09 e aggiungendo SOLO i due kind nuovi
   (`cashout_event`, `riprendi_evento`, controllo `mode` opzionale); diff riga per riga
   confermato dal coordinatore. Migrazione 5: aggiunto `ENABLE ROW LEVEL SECURITY` su
   `omega_requests` come le sorelle Safe. Test di contratto
   `Betfair/tests/test_contratto_safe_request_barriera_2026_09_17.py` (5, rossi prima, verdi
   dopo). Le altre quattro: OK; ordine 1→6 confermato, tutte indipendenti.
5. **Standard di sessione reso permanente**: regola globale
   `~/.claude/rules/sessione-coordinatore-cronostoria.md`, memoria
   `feedback_standard_sessione_coordinatore_cronostoria.md`, `CLAUDE.md` §cronostoria, questo file.

6. **Le 6 migrazioni sono APPLICATE dall'utente** (h ~12). Sonda in sola lettura del coordinatore:
   M2 colonne presenti sulle tre tabelle trade; M4 `omega_eventi_chiusi_dall_utente()` risponde,
   `omega_events.stato_utente` esiste, `get_omega_aggregates()` ha la chiave `auto`; M5
   `get_omega_proposte()` e `omega_requests` rispondono; M6 stake Safe =
   `per_strategia {base 2, esatto 2, punta 3, tennis 3}` (valori invariati). M1 e M3 (corpo di
   `omega_activate` e barriera di `safe_request`) non leggibili via PostgREST: verifica con le
   due SELECT su `pg_proc` chieste all'utente.

7. **App riavviata dall'utente (h10:14)**: Fase A ha fermato da sola Mike (era `live/running`
   dal 15/09) e Safe, attività `avvio_app_bot_fermato` con boot id. L'utente ha acceso **Mike
   LIVE** (stake 5, tetto partite 2 — NON 1 come concordato, segnalato) e **Safe tennis LIVE**
   (3 €/segnale, altre varianti paper spente). Runner `LIVE+PAPER`, battito fresco. Monitor in
   sola lettura armato dal coordinatore (`scratchpad/monitor_bot_live.py`, poll 30 s).
8. **Prima operazione LIVE reale di Safe tennis (h10:40:41)**: trade #297, back 1,03 × 3 € su
   Bar Biryukov v Honda (set 1-0, game 4-2, quota 1,02 chiesta, abbinata a 1,03: un tick
   meglio), percorso REST, `EXECUTION_COMPLETE`, bet_id 443177803518, abbinato 3/3, residuo 0.
   **Reperto**: le cinque colonne di consapevolezza sulla riga sono NULL (i numeri stanno solo
   in `meta.esecuzione`): la conferma dell'apertura di Safe (`bot_service.py:4349`) usa
   `update_trade` diretto invece di `aggiorna_trade` con `consapevolezza` come Omega e Mike.
   **Fix CERTIFICATO dal coordinatore** (Sonnet 5): `_conferma_apertura` passa da
   `X.aggiorna_trade` con `consapevolezza`; C1 di `certificazione_tennis.py` ora pretende le
   COLONNE valorizzate (prima guardava solo `meta.esecuzione`: replay KO senza fix, OK con fix);
   test nuovo, falsificazione mia (`consapevolezza=None` → 2 rossi). Richiede riavvio app.
9. **Seconda posizione live** #298 (h10:42): back Mi Leong 1,06 × 3 €, abbinato 3/3 a 1,0603.
   Osservazioni live certificate come CONFORMI (non difetti): 297 take profit trattenuto
   perché bloccherebbe +0,00 € (< min 0,01, T5); proposta #12 (profit, +0,03 €) creata h10:49:42
   e **ignorata dall'utente** h10:50:39; 298 nessuna proposta con un game perso perché
   `tennis_exit_on_lost_game=false` (parametro dell'utente), l'oscillazione a lay 1,33 era
   dentro un game (punteggio 3-2 per Leong). **Reperto**: `exit_hold` identico scritto in
   attività ogni 15-30 s (righe 2097-2102): rumore e scritture DB (lezione 13/09) → fix
   delegato (stesso agente). Monitor esteso con controlli di coerenza per ogni stato
   (feed, prezzo di chiusura, tracciamento vs feed, proposte in attesa, richieste fallite).

10. **Prima sessione LIVE chiusa (h10:40-11:00)**: #297 regolata `won` +0,09 € dal mercato
    chiuso (T8 dal vivo OK, 5 s dopo la chiusura); #298 chiusa dall'utente via proposta #14
    (firma 20 s dopo, lay 3,09 a 1,03, lock +0,09); l'utente ha fermato i bot (10:58) e poi
    l'app (~11:00). Betfair (listClearedOrders, sola lettura): 297 req 1,02/matched 1,03 +0,09;
    298 matched 1,06 (DB 1,0602666: media di due livelli) +0,19; 299 lay 1,03 −0,09 → netto
    coppia +0,10 (bot pianificava +0,09). 298/299 non ancora regolate nel DB (app ferma).
    **Ordini dell'utente**: (a) latenza: «nel tennis tutto al ms», stream invece di REST →
    analisi Opus 5 (`LATENZA_TENNIS_2026-09-17.md`); misure di oggi: scanner +1 ms, bot +2-2,9 s
    (poll 2 s), decisione +0,9-1,7 s, invio +0,2 s, Betfair +3,2-4,5 s (bet delay), clic→invio
    4,3 s; (b) prezzo in dashboard = quello di Betfair (2 decimali, chiesto/abbinato) → Sonnet 5
    frontend; P&L al regolamento dal `profit` di Betfair → stesso agente Safe (terza task).
    Monitor fermato.

11. **Latenza tennis, referto Opus 5** (`Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md`),
    reperti chiave verificati dal coordinatore: (a) **l'orologio del PC è indietro di ~2,08 s**
    (NTP: +2164/+2080/+2081 ms su tre server; servizio W32Time fermo) → le misure «invio→
    placedDate» contengono 2 s di errore; `stream.py:114` zittiva già il warning di latenza
    per questo; da sincronizzare (utente); (b) lo scanner è già su Stream API: il collo è il
    DB come bus (PostgREST 92-307 ms a chiamata, canale WS locale 0,6 ms) + poll 2 s + 8-12
    letture per giro nelle fasi di protezione; (c) Betfair: bet delay in-play tennis **3 s**
    (dal `marketDefinition` raw: 52 mercati a 3 s, 7 a 5 s), il bot Safe non lo legge;
    (d) progetto «al ms» DENTRO C3-F1: topic `safe_scan` sul canale locale, client nel bot,
    riuso del contesto con età massima fail-closed, approvazioni via Supabase Realtime
    (4,3 s → ~0,5-1 s), +7-10 giorni su C3. Non tocca il bet delay di Betfair. Decisioni
    utente: invio con riserva prima (a) o dopo (b); orologio; via a L0-L7.
12. **Tesi del coordinatore per Omega v4** scritta
    (`Betfair/omega/VISIONE_OMEGA_V4_COORDINATORE_2026-09-17.md`): market making con prezzo di
    riserva `L*(t)=(1−c)/(p_sup·k)+c`, «due strade» come regola unica, difese da selezione
    avversa, celle impossibili, EV per liability, Kelly frazionario, paniere mutuamente
    esclusivo (opzione), target giornaliero → metrica (opzione), modello Dixon-Robinson/
    Titman + NegBin + fusione per fascia e tempo dall'evento + calibrazione coda + CUSUM.
    Inviata come vincolo ai delegati v4 e M2.

13. **M1 ingresso passivo Omega — misurata** (Opus 5, verificata dal coordinatore: 19 test,
    falsificazione della coda di flumine rossa/verde; referto
    `Betfair/omega/INGRESSO_PASSIVO_MISURA_2026-09-17.md`, tool `tools/misura_ingresso_passivo.py`,
    39 registrazioni, 1.069 candidati, matching = `SimulatedOrder` vero di flumine): fill
    11,3 % (1 tick), 10,2 % (mid), 1,7 % (best back); guadagno di p_impl +6/+17/+43 % contro
    +25 % per il pareggio e +150 % per k=2; ordini morti per sospensione 35-42 %, fine finestra
    37-39 %; book sottile (spread mediano 6 tick, coda davanti quasi nulla); in gioco al tocco
    k 0,49 (IC 0,25-1,62, 12 uscite su 293 celle); selezione avversa 2,5×. **Verdetto: il
    passivo statico non recupera il bias; l'unica strada è la VITA dell'ordine** (quota viva,
    rientro dopo sospensione, finestre lunghe, presto, paniere) → M1-bis lanciata sulla
    politica v4. Nota: esiste anche `tools/misura_prezzo_appaiata.py` di altra sessione (da
    riconciliare).

14. **PROGETTO OMEGA V4 consegnato** (Opus 5, `Betfair/omega/PROGETTO_OMEGA_V4_2026-09-17.md`,
    1.131 righe; verificato dal coordinatore: reperto R-C1 confermato con grep — un solo
    scrittore della consapevolezza in `omega_service.py:1490`, undici `update_trade` diretti;
    `strategy_version` assente dal servizio). Misure nuove: **M0** prezzo APPAIATO (48.280
    selezioni): k prudente al miglior back 2,03 (CS 0,5-1 %), 1,74 (CS 1-2 %), 2,53 (HT 1-2 %)
    contro 0,54/0,81/0,79 al tocco; **M3** superficie per minuto (7.144 osservazioni): senza gol
    la quota sale ×1,07-1,20/5' (CS) e ×1,30-1,44 (HT) — osservazione dell'utente confermata;
    CS quotabile dal 1' (10,7 celle vs 2,4 all'86'); margine CS migliora ~+14 %/5' senza gol,
    HT piatto; EV/€ di liability massimo in fascia 1-2 % (+0,90 % CS, +1,34 % HT), negativo
    sotto 0,2 % e sopra 10 %. Riconciliazione con M1: leva di prezzo concorde (×1,52 vs ×1,44);
    restano da misurare k in gioco (IC 0,25-1,62) e selezione avversa (2,5× su 8 uscite):
    **criterio di arresto scritto** (se avversa×k resta <1 in ogni fascia, v4 non si costruisce).
    Piano: M1-bis, M6, M4, M5 (bloccanti) → Fase 0 reperti → 1 modello → 2 quotazione viva →
    3 proposte → 4 finestre/cap/liability fissa/paniere → 5 UI → C replay/paper/live; 58-74 h.
    Sei decisioni per l'utente (§8.3). Lanciati: R-C1 (Sonnet 5), M6/M4/M5 (stesso architetto).

15. **Safe: fix live certificati dal coordinatore** (Sonnet 5, tre task + UI): (a) colonne di
    consapevolezza all'apertura (`_conferma_apertura`); (b) `exit_hold` scritto solo se cambia
    la sostanza (`_hold_firma`: reason, kind, codice, locked al centesimo, source); (c) P&L al
    regolamento dal `profit` di Betfair (listClearedOrders, una lettura per mercato chiuso,
    ripiego intero sul calcolo se manca una gamba, `meta.pnl_source` dichiarato) e backfill
    delle colonne su righe già `open/hedged` (`_completa_consapevolezza_mancante`, 3/ciclo);
    (d) UI: `fmtQuotaAbbinata` — quota a 2 decimali come Betfair, «abbinato 1,06 (chiesto 1,02)»,
    medio preciso nel tooltip (Safe, Omega, watchlist). Falsificazioni del coordinatore: tre
    mutazioni diverse dal delegato → rossi; suite backend **4216 verdi**; vitest 2606 verdi.
16. **Storico tennis e calcio + chiuse di giornata** (Opus 5 in worktree, portato su master
    dal coordinatore con patch + 8 file nuovi): rotte `/storico/calcio` e `/storico/tennis`
    (`pages/StoricoSport.tsx`, `lib/storicoSport.ts`), riuso di `TradingHistory`/`dailyHistory`/
    design system, barre giornaliere SVG, curva cumulata, calendario, filtri periodo/bot/modo;
    paper e live MAI sommati (`totaleModo` lancia); Omega esclusa dai totali finché
    `get_omega_daily` non separa la modalità → migrazione `migrations/storico_sport_2026-09-17.sql`
    (DA APPLICARE, in revisione statica Sonnet 5; cambia il tab Storico di Omega: solo la
    modalità corrente). Control Room «Posizioni chiuse» = solo la giornata (piazzamento,
    Europe/Rome) con «Oggi · N chiuse» e pulsante Storico; pulsante `StoricoLink` in ogni
    `BotHeader`. Reperto: i 4 bot tennis e lo scalper calcio non hanno P&L regolato nel DB
    (`tennis_live_orders` senza pnl/settled_at) → esclusi con motivo in pagina. Falsificazione
    del coordinatore (filtro di giornata disattivato → 10 rossi). Vitest/tsc/build su master in
    corso.

17. **Omega, consapevolezza sul percorso della coda flumine — certificato** (Sonnet 5): il
    reperto R-C1 del progetto v4 era in parte sbagliato (`_flumine_confirm` passava GIÀ da
    `aggiorna_trade` dal 16/09); il difetto vero: `_mirror_fill` non leggeva `size_remaining`
    né `matched_at` dallo specchio → `size_remaining`/`betfair_updated_at` NULL su ogni riga
    confermata dalla coda (paper e live). Corretto (5 valori, 6 punti di chiamata), controllo
    **K7** (colonna NULL con meta valorizzato → accusa), 10 test; falsificazione del
    coordinatore (residuo mai propagato → 3 rossi). Omega **939 verdi**. Restano: stesso buco
    in `reconcile_pending` (REST legacy, segnalato); `CHECK omega_trades.status` senza
    `cancelled`/`lapsed` (oggi ripiegano su `error`+`meta.reason`): migrazione solo se v4 li
    vuole dichiarati.

### Decisioni dell'utente (17/09)
- Da oggi: coordinatore + Opus 5/Sonnet 5, cronostoria e checkpoint sempre, si riparte dal punto
  di arresto senza che l'utente lo ricordi.
- **OMEGA (h11:30, ordini, non proposte)**: M2 sì («sfruttare la potenza dei dati che si
  aggiornano partita dopo partita; non ci sono tutti i dati per tutte le partite: studia o simula
  su una partita per tarare i pesi»). B1 sì, «intelligente»: in live il punteggio cambia e il
  tempo è dalla nostra parte → algoritmo predittivo avanzato per stimare il risultato a nostro
  vantaggio; il bot gestisce le SOSPENSIONI (ordine annullato) e i risultati IMPOSSIBILI
  (non più realizzabili) e ricalcola continuamente la miglior selezione. B2 sì. C sì «ma veloce».
  Omega deve portare in profitto nel lungo periodo: «estremamente avanzato, intelligente,
  adattato al live». **Massività**: autorizzato a cambiare i parametri attuali (finestre d'ingresso
  e tetto alle quote) dopo studio documentato dell'algoritmo migliore, per fare più ingressi
  possibili con la maggior probabilità di profitto. Restano: due ingressi per partita.

### Numeri di chiusura del giro (aggiornare a ogni checkpoint)
- Suite backend dopo i fix: 4185 verdi (era 4173 + 12 test nuovi), frontend non toccato (2503).
- Modifiche non committate: `Betfair/stream/backtest/certifica.py`,
  `Betfair/stream/tests/test_raw_recmeta_stall.py`, 2 test nuovi, 2 migrazioni corrette,
  `migrations/APPLY_ORDER_2026-09-16.md`, `CLAUDE.md`, `CRONOSTORIA.md`.

18. **Migrazione 7 applicata dall'utente** (h12:50; sonda: `get_omega_daily` con `p_mode`
    risponde, `get_storico_stake` risponde). **Commit locale `38b0043`** (57 file); il push
    lo fa l'utente (`git push origin master`: bloccato al coordinatore dal classificatore).
19. **tsc a ZERO** (Sonnet 5, verificato: 0 errori, vitest 2674 verdi, build OK): 13 errori
    chiusi con correzioni di tipo; `vite-env.d.ts` mancava dal progetto; una correzione è un
    bug latente vero: `SeguiLive.tsx` chiamava `fetchOrders(id)` senza `mode` (conteggio
    LAPSE non filtrato per modalità); duplicazione `phaseFromMinute` in `tier0_arb`/
    `tier1_quasi` segnalata, non toccata (strategia). Regola in `CLAUDE.md`: 0 errori.

20. **M4/M5/M6 Omega consegnate** (Opus 5, `Betfair/omega/M4M5M6_2026-09-17.md`, 18 test verdi
    rieseguiti dal coordinatore; 10 falsificazioni del delegato con md5): **criterio di
    arresto = selezione avversa 1,27** (Monte Carlo: 1,00 → +169 €/mese; 1,27 → 0; 2,5 di M1 →
    −758 €, 100 % mesi negativi). **M6** (34.069 osservazioni, esito dal WINNER): bias in gioco
    al netto della geometria del book: CS 0,5-1 % 2,46 (prudente 1,11), CS 1-2 % 2,52 (1,11),
    **CS 2-5 % 0,71 (EV negativo)**, HT 2-5 % 2,37 (0,92); placebo calibrato/permutato OK.
    **M4** smentisce il «+14 %/5'»: +8,5 % solo nella coda profonda CS, ~0 dal 2 % in su,
    negativo su tutto l'HT. **M5**: 1 cella +170 €/mese (10,7 % mesi negativi), paniere 5 celle
    +835 €/mese (0 % mesi negativi, drawdown mediano 144 €). **M1-bis**: 10 fill su 12.486
    quotazioni a L* del modello → a quel prezzo non si abbina niente. **Sintesi**: l'edge sta nel
    PREZZO (bias di fascia al miglior back: 1,31-1,71× contro requisito 1,11), non nel modello;
    prezzo di riserva riscritto `L*_fascia = (1−c)/(p_equa·k_fascia)+c`; il modello si riduce
    ad ammissibilità, fascia, veto, proposte. **Misura bloccante ora: M1-ter** (quota viva al
    miglior back con bias di fascia, selezione avversa vs 1,27) → lanciata.

21. **M2 dati e pesi Omega — consegnata** (Opus 5, `Betfair/omega/M2_DATI_E_PESI_2026-09-17.md`,
    22 test): **risultato negativo e onesto**: nessuna fonte storica del DB (fixture, tattico,
    API, forza, forma, h2h) migliora le λ fuori campione (657 partite mai viste) con IC che
    esclude 0 → **peso zero dichiarato; le λ pre-partita = quote devigate del mercato**. Reperto
    sul motore: `_prematch_lambdas` usa PRIMA la fixture (fonte peggiore) e DOPO le quote:
    invertire l'ordine è un miglioramento misurato (HT IC esclude 0). Incertezza che cresce
    quando manca il mercato (cv 0,20 → 0,52, L* da 186 a 104: la partita senza mercato non
    apre da sola). Copertura: quote Betfair pre-match solo 3,0 % delle partite e ferme
    all'11/09 (job manuale); transizioni ferme all'11/09 ma incrementale già esistente
    (catch-up 1-2 s). Hazard di gol per stato (358 stati): profilo ×1,53 dal 0-5' all'80-85'.
    Difetto latente: paginazione PostgREST con ordine non totale salta righe in silenzio.

22. **M1-bis e M1-ter chiuse — CRITERIO DI ARRESTO RAGGIUNTO sulla variante meglio misurata**
    (Opus 5, verificato dal coordinatore: 30 test, JSON coerenti; `M1TER_QUOTA_VIVA_BEST_BACK_
    2026-09-17.md`, 36.118 quotazioni, 39 registrazioni). M1-bis (riscritta): quota viva al
    prezzo del modello → 11 fill su 13.281 (0,08 %); k al tocco secondo v3 mediana 0,70. M1-ter:
    il prezzo di riserva dal bias di fascia cade ESATTAMENTE sul miglior back (0 tick di
    margine, mediana su 14.131 osservazioni; il «1,31-1,71» di M4M5M6 §6-bis.3 era un rapporto
    di medie, per cella la mediana è 1,14 e solo il 61 % delle celle arriva a 1,11); a quel
    prezzo fill 0,09 %; +1/+3 tick → fill 1,2/3,5 % ma solo 43/32 % delle quote sopra soglia e
    247 fill su 352 sono PRESE AL TOCCO (k 0,45-0,53); k realizzato sui fill passivi 0,20-0,26
    (EV −2,7/−3,7 € per euro); P&L −38 €/−21 € su 36 gambe; selezione avversa 1,77/2,50 (IC
    largo), 1,62 con IC 1,36-2,02 sull'ammissibilità p_equa → sopra 1,27. **Verdetto del
    coordinatore: il market making passivo sulle scoreline di coda, con i dati di oggi, non
    porta in profitto; v4 come progettata NON si costruisce.** Sei misure indipendenti
    concordano (K_MISURATO, M1, M1-bis, M1-ter, M6 al tocco, M2 modello senza edge). Limiti:
    2 uscite fra i fill, 11 giorni di calendario, quote pre-match al 3 % delle partite.
    Commit locali `bd1b428`, `c894ca3`.

### DECISIONI APERTE DELL'UTENTE — da ricordargli nel pomeriggio del 17/09 (ordine suo)
Omega/M2: (10) job giornaliero per le quote Betfair pre-match (`betfair_full_odds.py`, ferme
dall'11/09, fonte più forte e meno automatica); (11) catch-up delle transizioni + pg_cron
04:00 UTC (migrazione); (12) invertire l'ordine della catena λ (quote prima della fixture:
tocca il motore).
Omega: (1) obiettivo giornaliero da motore a metrica; (2) paniere di 3-5 celle per gamba a
caso peggiore sotto cap; (3) cassa di riferimento, liability per gamba (proposta 30 €), per
partita (60 €), stop giornaliero (10 perdite); (4) tetto di quota → fascia di probabilità
0,3-5 % + cap di liability; (5) «1T/2T» = due mercati (gamba FT quotabile dal 1'); (6) aggregati
Any Unquoted/Any Other bancabili. Latenza tennis: (7) riserva DB prima (consigliato) o dopo
l'invio; (8) via al percorso «al ms» dentro C3-F1 (+7-10 gg). Tennis: (9) `tennis_exit_on_lost_game`
spento nei parametri: accenderlo o no (scelta di rischio dell'utente). Più: orologio del PC
da sincronizzare; push del commit.

- **SAFE TENNIS (h14:30, decisioni dell'utente)**: (1) uscita al singolo game perso: resta SPENTA; (2) NESSUN alert sul prezzo: strategia come da manuale, eventualmente in futuro; (11) replay con competizione dichiarata: va bene così; (7) bet delay per mercato dal betDelay: ok;
  (3) riserva DB PRIMA dell'invio; (4) SÌ al percorso «al ms» dentro C3-F1 → costruzione lanciata
  (Opus 5, worktree: L0/L1/F1/L3/L4/L6 + F2 paper Safe via coda + F5 parità); (12) allinea paper
  e live (stessa costruzione); (13) i 4 bot tennis: audit maniacale + allineamento al banco come
  Safe, su una partita → lanciato (Opus 5, worktree); (9) attese e buchi del book visibili al
  trader → lanciato (Sonnet 5, UI); (7) bet delay Betfair: doc ufficiale «1-12 s per mercato,
  valore nel campo betDelay del marketDefinition/listMarketBook»; nelle registrazioni tennis 3 s
  (52 mercati) e 5 s (7): il valore vero è quello per mercato, il bot lo leggerà (L1). NON
  verificabile da qui (geoblock ADM) la newsletter Betfair 08/2025 sui «passive bet delays»
  (ordini make senza ritardo al 100 % dei tornei tennis): da confermare dal vivo.
  **PROMEMORIA per l'utente**: (5) prova dal vivo del cash-out globale con stake minimo;
  (8) sincronizzare l'orologio del PC. Sentinella live FERMATA su ordine dell'utente (h14:35):
  avvisa lui.

- **OMEGA — MANDATO DELL'UTENTE (h15, ordini)**: «Omega è un asset e dobbiamo usarlo; prodotto
  rivoluzionario per piccoli profitti costanti». Due ingressi a partita (1T e 2T); **stake FISSO
  1 € in lay a qualunque quota**; range di quota e finestre di tempo: tolti se peggiorativi (lo
  sono, misurato); obiettivo = tutto il palinsesto di giornata con un target per partita, come
  metrica (altri bot concorrono all'obiettivo); **NON NEGOZIABILI**: massività («più posizioni
  possibili», «una loss lo compromette totalmente») e **SCHEDA IN UI DOVE L'UTENTE APPROVA LE
  USCITE in profit e in loss** come Safe tennis, chiusura dalla scheda. **Omega passa alla
  sessione dedicata `admin-b1`** (coordinatore Fable 5.1 + Opus 5/Sonnet 5): mandato completo in
  `Betfair/omega/MANDATO_OMEGA_V4_2026-09-17.md` (metodo, stato, programma a 30 punti, decisioni,
  documenti, prima ora). `admin-6d` resta su Safe/Mike/UI/banco e sui file condivisi.

- **INCIDENTE QUOTE (h14:47 locali = 12:47Z)**: TUTTE le righe in gioco di `safe_strategy_scan`
  (4 calcio, 11 tennis) hanno quote nulle e `mo_total_matched` 0 dalle 12:47-12:48Z (4 doppi tennis
  dal riavvio 12:17Z); punteggi freschi; scanner dichiara stream sano (heartbeat) e `last_error`
  null. Betfair HA i prezzi (REST 13:03Z: Barrena 1,04/1,05, matched 5.877 €). Nessun file di
  produzione dello scanner (`safe_strategy/service.py`, `stream.py`) toccato oggi: difetto
  preesistente scatenato dal cambio del set di mercati (risottoscrizione) o dal ripiego REST.
  Effetto: Safe tennis non entra e non può chiudere; Mike senza quote sulle sue partite.
  Mitigazione: riavvio dell'app (utente). Diagnosi Opus 5 in corso (`INCIDENTE_QUOTE_TENNIS_
  2026-09-17.md`) con patch proposta: mai sovrascrivere quote valide con un book vuoto, status
  per shard, test falsificati. Reperto collaterale del coordinatore: `git worktree remove
  --force` ha svuotato `frontend/node_modules` del checkout principale (junction): lezione in
  memoria; reinstallato da un delegato.

- **4 BOT TENNIS (h17:50, ordine dell'utente)**: «stessa trafila degli altri bot validati:
  backtest reali, gestione di ogni possibile casistica, DEVONO ESSERE PERFETTI; i bug di
  progettazione vanno risolti; voglio vederli in UI, indipendenti come gli altri». Audit
  consegnato (`Betfair/stream/tennis_live/AUDIT_4_BOT_TENNIS_2026-09-17.md`, worktree
  `agent-ab70cb4cf8bd9f258`): backtest di luglio su una COPIA di laboratorio (verdetto «no edge»
  da rifare); 4 bot registrati e certificabili sul banco con il codice di produzione (18
  controlli, replay Sinner-Struff: pro 0, flb 0, scalper 159 K5, swing 1.168 K5); 6 bug
  corretti e falsificati; 3 reperti money-critical (swing 7,57 € abbandonati, scalper residuo
  accumulato, flb/scalper senza freno dopo rifiuto: 8.132/20.534 tentativi); 6 divergenze di
  strategia → decise dal delegato nel senso del DOSSIER con motivo (ordine utente: niente
  domande); storico P&L (migrazione scritta), ref specchio stabile, Control Room per bot
  (interruttore paper/live, stake, stato, storico). Fasi F1-F4 lanciate (Opus 5, worktree).

- **INCIDENTE QUOTE — CAUSA VERA E FIX CERTIFICATO (h19:05)**: `service.py:1226` importava
  pigramente l'atlante hazard da `stream/scalper/theta_bot` → `scalper/__init__` → `scalper_bot`
  → `flumine`, che riscrive `RunnerBookEX` in forma a dizionari → `scanner.best_price` (attributo
  `.price` in `except → None`) restituiva None su OGNI runner, stream e REST, per la vita del
  processo. Scattava alla prima valutazione delle opportunità calcio in gioco (oggi h14:47; in
  repo dal 10/09 `99fbff8`; scalper→flumine dal 02/07): senza calcio in gioco (mattina) mai.
  FIX (Opus 5, verificato dal coordinatore): (1) radice: `Betfair/stream/scalper/hazard_atlas.py`
  modulo puro, `theta_bot` riesporta, package scalper con import pigro PEP 562, chiamanti
  ripuntati (service, selezione, opportunity, `mike/dossier.py`); (2) difesa: `livello_campo` →
  `best_price/best_size` leggono oggetti e dict; test del banco riscritto («lo scanner LEGGE
  anche il ladder di flumine»); (3) guardia runtime `flumine_caricato` in status + `last_error`;
  più i 5 punti precedenti: book senza prezzi mai applicato, copertura per MERCATO con REST
  entro 20 s, risottoscrizione A CALDO senza abbattere la connessione, stato onesto (allarme solo
  sui mercati core, elenco completo nello status, `source` rest/stream), `skip quote_assenti` e
  `exit_wait` riloggato. 46 test nuovi + 19 falsificazioni del delegato + 2 del coordinatore
  (guardia disattivata → 6 rossi; package eager → rosso). Prove dal vivo (dry, lock alternativo):
  delegato 120 s allarme 0/quote su 20/20 eventi/flumine false; coordinatore 190 s 442 righe con
  quote 0 senza, risottoscrizione a caldo a +36 s con 83 mercati senza ammutolire, un mercato in
  allarme per 30 s dichiarato e rientrato. Suite intera **4390 verdi** (+1 test Mike sistemato:
  contratto UI multi-riga), replay safe_tennis 15/15, mike 2/2, omega 1/1 → 0 violazioni.
  Build frontend 19:06. **Riavvio 1 = feed** (utente); riavvio 2 con Omega T2 (~20:00).

### Omega — sessione dedicata (coordinatore: admin-b1) — da compilare dalla sessione Omega

**Stato di partenza verificato dal coordinatore admin-b1 (h15:40)**: master `3733f17`, 5 commit
avanti a origin (push dell'utente); suite Omega **976 verdi** (il mandato dice 960: i 16 in più
sono i test M1-bis/M1-ter dei commit `bd1b428`/`c894ca3`); `certifica --elenco`: `omega` OK,
registrato con `omega_service`/`certificazione`. Non committato sul checkout (di admin-6d):
`CRONOSTORIA.md`, `SafeTradesTable.tsx`, `SafeStrategy.tsx`, `data/pesi_m2_2026-09-17.json`.
Letti: mandato, VISIONE (+§9), PROGETTO V4 §2-§9, M4M5M6, M1-ter §0/§1/§7-9, K_MISURATO,
REFERTO_V3, PROCESSO §6-7, COSTITUZIONE §0-1, Mike CHECKPOINT §1-2, PAPER §C3, CHECKPOINT_O1.

**Reperti del coordinatore (prima di ogni delega)**:
- **O-1 (money-critical)**: la migrazione `omega_proposte_uscita_2026-09-16.sql` (applicata) ha
  CREATO la tabella `omega_requests`, ma la coda che il servizio drena è `omega_manual_requests`
  (`omega_db.pending_manual_requests:257`, `process_manual:3519`); RPC `omega_request_approve`/
  `ignore`/`get_omega_proposte` e la UI (`omegaProposte.ts:143,191`) puntano a `omega_requests`
  → una proposta APPROVATA (`proposed→pending`) non verrebbe MAI eseguita. Il commento della
  migrazione («non è una tabella nuova») è falso. Da chiudere nel task 22 (una coda sola).
- **O-2**: v3 NON è collegata al servizio (0 occorrenze di `omega_v3`/`strategy_version` in
  `omega_service.py`); il replay la fa girare solo in ombra (`replay_registrazioni._ombra_v3`).
- **O-3**: `_manual_cashout:3933` + `_dopo_il_cashout:4055` marcano OGNI `cashout` come chiusura
  dell'utente (`exit_kind='manual'`, evento «chiuso dall'utente»): una proposta approvata
  (`payload.approved_at`) spegnerebbe il bot sulla partita — stesso difetto Safe del 14/09
  (`bot_service._uscita_del_bot_approvata:2568`).
- **O-4**: `omega_v3.proposta_uscita:877` rifiuta con `bloccabile_non_positivo`: oggi nessuna
  proposta in LOSS; il mandato la esige (protezione con EV tengo / bloccabile / p_lose / liability).
- **O-5**: `reconcile_pending:2457` conferma con `_confirm_open_trade(price,size)` senza
  `size_requested`/`size_remaining`/`betfair_updated_at` dall'ordine vero (stesso buco di
  `_mirror_fill`, K7); `reconcile_decision` (`omega_engine.py:687`) non li restituisce.

**Task lanciate (worktree, h15:45)**: T1 Opus 5 = produttore delle proposte (punto 22) + coda
unica + proposte in loss + riconoscimento dell'approvazione (O-1, O-3, O-4); T2 Opus 5 =
raccordo v3→servizio (O-2; infrastruttura: strategia e switch `strategy_version=2` invariati);
T3 Sonnet 5 = consapevolezza (punto 23: O-5, R-J3, R-J6, migrazione `CHECK` cancelled/lapsed).
Fase 2 (quota viva) NON lanciata: M1-ter dice che la politica non ha un punto di lavoro
(fill 0,09 % al prezzo di riserva = miglior back): decisione dell'utente con i numeri.

**DECISIONI DEL COORDINATORE admin-b1 (h16:40) — ordine dell'utente h16:30 via admin-6d: «deve
trovare lui la soluzione migliore: 1 € a lay, cella per probabilità, minuti decisi dal bot;
nessuna domanda». Ogni voce ha il numero che la motiva; diventano DEFAULT del pannello.**
- (a) Stake: `v3_stake_eur=1.0` lay fisso (ordine).
- (b) Mercato e fascia: SOLO Correct Score. Bias prudente in gioco (M6 §2.3) ≥ 1 solo nelle
  fasce CS 0,5-1 % (1,11) e 1-2 % (1,11) per p_implicita al tocco; CS 0,2-0,5 % 0,97 e 2-5 %
  0,71 (EV negativo) escluse; HT 2-5 % 0,92 esclusa, HT < 2 % zero uscite su 1.888 celle: non
  misurabile → gamba sull'HALF_TIME_SCORE FUORI con motivo scritto. Fra le due fasce buone l'EV
  per euro di liability (stake 1 €: liability = quota−1) è 0,15 %/€ (0,5-1 %, quote 95-190)
  contro 0,87 %/€ (1-2 %, quote 47-95) → fascia operativa **p_impl 1-2 %** = quote **47,5-95**:
  `v3_p_max_pct=2.0`, P minima 1,0 % (parametro `v3_p_min_pct` se banale, altrimenti tetto di
  quota 95 con lo stesso significato). Distanza minima 2 gol (`v3_distanza_minima_gol=2`): è la
  popolazione su cui il bias è misurato. Aggregati Any Unquoted/Other ammessi (v3 li prezza,
  K_MISURATO li valuta). Ordinamento: v3 sceglie la P più bassa che passa il cancello; l'EV per
  euro di liability è quasi costante dentro la fascia: non si cambia stasera.
- (b-cap) Cap derivati: liability per gamba **95 €** (= quota 96, bordo della fascia), per
  partita **190 €** (due gambe), aperta insieme **1.000 €** (~10 gambe), perdita giornaliera
  **300 €** (~3 perdite di gamba: con premio 0,95 € e p_reale 1,3-1,9 % una perdita ogni 60-75
  gambe è il ritmo atteso; tre in un giorno è il segnale di fermarsi ad aprire). Paniere: NO
  stasera (lavoro di motore, Fase 3; M5 dice ×4,9 sul P&L: resta in coda).
- (c) Minuti: due ingressi = due celle del Correct Score in due momenti: gamba A finestra
  **1'-44'**, gamba B **46'-85'** (M3: 10,7 celle al 1' contro 2,4 all'86', liability metà per
  la stessa cella; M4: nella 1-2 % aspettare vale 0; oltre l'85' il CS resta spesso senza
  controparte). Se il motore non regge due gambe sullo stesso mercato entro sera: gamba HT
  resta sull'HALF_TIME_SCORE ma chiusa dai dati (motivo scritto), gamba FT dal 1'. **Quotazione
  continua (quota viva) NON stasera**: M1-ter misura fill 0,09 % al prezzo di riserva (= miglior
  back), nessun punto di lavoro, 12-16 h di costruzione non certificabili entro sera → si prende
  al tocco (FOK, percorso di produzione esistente). Divergenza dichiarata dall'ordine (c).
- (d) Cancello: `v3_k_minimo=1.11` = bias prudente misurato delle fasce buone (era 2 = «bias non
  dimostrato», che sulle registrazioni non apre mai). Sulla P v3 (gamma-Poisson fusa col
  mercato, calibrata prudente 0,87-0,93 sulla coda) è un doppio margine. CUSUM online: NON
  stasera (il paper misura il k realizzato per fascia; CUSUM in Fase 2).
- (e) Uscite: proposte in profit e in loss con firma (T1); nessuna chiusura automatica.
- (f) Job quote pre-partita e catch-up transizioni: in checklist come «da lanciare», non bloccano.
- Paper di stasera, differenze dichiarate rispetto al live: bet delay NON applicato in paper
  (§7.14), percorso via runner solo per le partite seguite, ripiego locale per le altre.

**Checkpoint O-A (h17:10) — riferimento su master `3733f17` PRIMA di ogni merge**, eseguito dal
coordinatore: `certifica omega 35760084 --scenari tutti --worker 3` → 14 scenari, **13 puliti,
1 con 2 violazioni** (J3 ×2 in `rifiuti-betfair`: «ref omega-t1 non riconducibile a nessuna
riga»: la riga di riserva viene cancellata da `_leg_certain_failure` dopo un rifiuto CERTO di
Betfair e J3 la cerca dopo → falso positivo del controllo, già noto da `CHECKPOINT_V3:329`; in
chiusura a T3). Mai sollecitati 17/50: A6, C3, D1-D6, E2, J6, J7, A9-A12, C5, G2 (A9-A12/C5
arrivano con T2, G2 con T1, J6/J7 richiedono lo scenario «parziali» ⊘ stasera). K1-K7 ×1466,
E3 ×576, E4 ×110, E5 ×108: identici a CHECKPOINT_O1. Referto:
`scratchpad/baseline_master_35760084_tutti.txt`.
**T3 verificata dal coordinatore (codice)**: diff riga per riga ok (4 correzioni circoscritte:
`reconcile_decision` restituisce residuo 0,0 e istante; `reconcile_pending` LIVE/PAPER li passa;
`candidate_customer_refs` senza ref storico per le righe con `phase`; `place_parziale` in
`_flumine_confirm` e nel paper legacy); suite nel worktree 985 verdi; falsificazioni MIE
(regolato senza `size_remaining` → 1 rosso; `place_parziale` flumine spento → 1 rosso), md5
ripristinati. Replay del delegato: 4 scenari = riferimento (stesse 2 J3). Merge su master
DOPO la chiusura di J3 (follow-up a T3, scadenza 17:45).

**Checkpoint O-1 (h17:40) — T3 CERTIFICATA e SU MASTER (non committata)**. J3 chiuso come
falso positivo del controllo: `_j3` non accusa una riga assente SOLO se il ref ha il formato
per gamba `omega-t<int>` E il BANCO (`m.esito`, `PlaceResult` vero, mai le attività del bot)
dice rifiuto certo (`ok=False`, nessun `bet_id`); esito ignoto resta accusato;
`_leg_certain_failure` intatta. 4 test nuovi in `test_omega_replay_2026_09_16.py` (verde/rosso
nelle due direzioni); falsificazione MIA (formato del ref ignorato → 1 rosso), md5 ripristinato.
Suite: worktree 989 verdi, **master 992 verdi**. Replay `certifica omega 35760084 --scenari
tutti --worker 3`: worktree **14/14 puliti, 0 violazioni**; **master dopo la patch 14/14
puliti, 0 violazioni**, copertura IDENTICA al riferimento O-A (K1-K7 ×1466, E3 ×576, J3 ×11,
B4 ×459; nel worktree B4 ×447: differenza d'ambiente, su master non c'è). Mai sollecitati
restano 17/50 (attesi da T1/T2 e dallo scenario «parziali» ⊘). Applicazione su master: patch
`git apply` + 3 file nuovi, md5 identici al worktree per tutti i file; nessun file di admin-6d
toccato. Referto del delegato: `Betfair/omega/CHECKPOINT_T3_CONSAPEVOLEZZA_2026-09-17.md`;
referti miei: `scratchpad/t3_35760084_tutti.txt`, `master_post_t3_35760084_tutti.txt`.
Migrazione `migrations/omega_trades_status_cancelled_lapsed_2026-09-17.sql` scritta, da
applicare (checklist). Reperti aperti dichiarati da T3: `_leg_certain_failure` con abbinato 0
(solo segnalato); `_manual_place` probabile stesso buco R-C1 (passato a T1).

**Checkpoint O-2 (h18:55) — T1 PROPOSTE DI USCITA CERTIFICATA e SU MASTER (non committata)**.
Costruito (Opus 5): `Betfair/omega/omega_proposte.py` (produttore, modello Safe copiato, fase
1-bis di `run_once` al posto del green-up quando l'automatico è spento: `greenup_mode='off'` o
`strategy_version>=3`; nessun default cambiato da T1); `omega_db` con le tre funzioni della coda
SU `omega_manual_requests`; **O-1 chiuso** con `migrations/omega_proposte_coda_unica_2026-09-17.sql`
(DA APPLICARE: `updated_at`, CHECK status/kind superset, indice unico proposta viva, tre RPC
ripuntate a firma identica, `get_omega_manual_requests` filtra proposed/rejected, drop di
`omega_requests` solo se vuota); **O-3 chiuso** (`_uscita_del_bot_approvata`, firma su
`meta.chiusura_proposta`, attività `uscita_approvata`, `_dopo_il_cashout` NON chiamato,
cancelletto fail-closed `proposta_non_firmata`); **O-4 chiuso** (`proposta_uscita` con motivi
`protezione` = ev_tenere < bloccabile anche sotto zero, `cap`, `rischio` con
`proposta_p_lose_max_pct` default 0 = spento); controlli G2 riscritto, **G3/G4 nuovi**, G1(c) su
attività di chiusura umana (⊘ dipende dall'attività `uscita_approvata` con `firmata`: da
rafforzare col banco); scenario `proposta-approvata` nel banco; UI: scheda con «Chiudi in
perdita», elenco manuali etichettato, realtime su `omega_manual_requests`. Un test del 16/09
(«in perdita non si propone mai») sostituito per ordine del 17/09.
Verifica MIA: diff riga per riga (servizio, v3, db, migrazione, produttore intero, controlli,
replay, frontend); suite worktree 1002 verdi; falsificazioni mie (cancelletto firma tolto → 1
rosso; cap mai proposto → 10 rossi), md5 ripristinati; **master dopo la patch: 1021 verdi, tsc 0,
vitest 165 verdi (ControlRoom/omegaProposte/ManualPanel/omega)**; replay **35760084 tutti i 15
scenari puliti, 0 violazioni** (copertura ⊇ O-1: A8 ×132, G1 ×936, K ×1577; G3/G4 ×0 qui perché
nessuna proposta è possibile su quella partita); **35777617 5/5 puliti, 0 violazioni**, ciclo
completo: proposta `cap` al 74' (blocchi −0,48 € vs EV +2,36 €) → firma → drenata → eseguita in 1
giro, `exit_kind=loss`, partita NON chiusa dall'utente; **G2 ×87, G3 ×86, G4 ×46** sollecitati.
Reperti del delegato corretti: churn delle proposte sui motivi transitori (9 proposte/8
decadenze → 1), memoria G2 per richiesta. Limiti ⊘: RPC vere non provate contro Supabase;
`betfair_updated_at` vuoto sulla gamba di chiusura nel banco (specchio dell'order stream
assente): da riguardare in paper; sul banco escono solo `cap` e `controparte_insufficiente`
(`blocca_il_profitto`/`protezione`/`rischio` provati dai test). Junction dichiarate da T1 nel
suo worktree (`.venv`, `frontend/node_modules`): da togliere con `rmdir` prima di rimuoverlo.
Referti: `CHECKPOINT_T1_PROPOSTE_2026-09-17.md`; miei `scratchpad/t1_*.txt`,
`master_post_t1_*.txt`.


### Punto di ripresa (aggiornato h13:20)
0. **Omega**: verdetto negativo delle misure (checkpoint 22) da discutere con l'utente nel
   pomeriggio; opzioni: fermare lo sviluppo di v4 e riallocare su Mike/Safe; oppure una NUOVA
   ipotesi misurabile (non «più modello»: M2 dice zero) con criterio di arresto scritto prima.
   Le 12 decisioni aperte restano elencate sopra. Push dei 4 commit locali: utente.
1. **Utente (fatto)**: applicare le 6 migrazioni nell'ordine 1→6 di `migrations/APPLY_ORDER_2026-09-16.md`
   (la 3 e la 5 sono le versioni CORRETTE del 17/09), poi le verifiche SELECT del file; riavviare
   l'app.
2. Con l'utente dal vivo: Fase A (tutti i bot fermi «all'avvio dell'app»), interruttori, cash out
   globale e Riprendi, rischio conto/bot; poi Mike LIVE (stake 5, tetto 1, `pre_exit_mode`
   resting, referto forense ordine per ordine), Safe tennis LIVE (3 €), Safe calcio PAPER, Omega
   PAPER (decisione pendente su v3 in ombra + ingresso passivo).
3. Poi: paper via flumine F1 (Opus 5, worktree separato), scalper/sniper/4 tennis sul banco,
   Fase D carico DB, massivi.
