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

**CHIUSURA DELLA SESSIONE OMEGA (h17:45 orologio PC; ordine dell'utente via admin-6d: crediti
in esaurimento, nessun lavoro nuovo).** Nota: gli orari dei checkpoint O-A/O-1/O-2 sopra sono
stimati e sballati di ~1,5 h; l'ordine cronologico è corretto (O-A ≈16:25, O-1 ≈16:50,
O-2 ≈17:15 dell'orologio del PC).

*Stato di T2 (raccordo v3, Opus 5, worktree `agent-af84954150e351fc6`, base `3733f17` con
T3+T1 fusi dentro, 26 file modificati/nuovi, NON su master, NON certificata)*: consegna
letta da me riga per riga (servizio `_v3_select`/`_size_and_place(v3=)`, config con i default
decisi, `omega_v3` fascia/escludi/`p_mercato_devigata`, engine, conftest con pin v2, replay con
`_v3_select` sondato e ombra tolta, pannello). Numeri del delegato: suite 1056 (Omega) +
1443 (stream); replay 35760084 18/18 puliti; 35797769/35777617/_synth: 15/18, 6 violazioni
J3×3+J6×3 = falsi positivi dei controlli su FOK ucciso a zero (ok=True, size_matched=0);
falsificazione md5 A9 ×4, A10 ×2, pavimento ×83. **Reperti MIEI aperti, rimandati a T2 e NON
ancora chiusi**: (1) fascia [1 %, 2 %] applicata alla P NOSTRA invece che alla p_implicita al
tocco (M6 definisce le fasce su p_impl): fa passare `3-2 @40` (p_impl 2,4 %, fascia a EV
negativo) → correggere in `omega_v3._seleziona` (motivi `p_impl_sotto_fascia`/
`p_impl_oltre_fascia`), tetto `p_nostra ≤ p_max` resta, A11/A15 su `p_implied`; (2) `_j3`
secondo ramo (ok=True, size_matched=0, stato TERMINALE dal banco) e `_j6` `quando` solo con
size_matched>0, con falsificazione nelle due direzioni; (3) pannello `omega.ts`: label/note del
gruppo v3 dicono ancora «IN OMBRA»; (4) scenari legacy del replay (`base`, `giornata-reale`,
`apertura`, `paper`) girano ora col v3 per default: vanno pinnati a `strategy_version=2` con
descrizione «legacy», `v4*`/`proposta-approvata` espliciti a 3, descrizioni di condotta neutre.
Decisioni mie già date a T2: tabella k del 16/09 non più passata (era pre-match; 1,11 è M6 in
gioco); pin v2 in conftest accettato come DEBITO (126 test v2 da riscrivere per v3);
`n_min_empirico` morto e controparte persa in `selezione_da_v3`: solo segnalati.
*Referto del delegato*: `Betfair/omega/CHECKPOINT_T2_RACCORDO_V3_2026-09-17.md` (nel worktree).
Patch fusa T3+T1+T2 pronta in `scratchpad/t3_t1_t2_fusi.patch` (base 3733f17): per portarla su
master prendere i FILE INTERI di `omega_service.py` e `tools/replay_registrazioni.py` dal
worktree T2 (contengono già T3+T1) e la patch per il resto.

*Su master NON committato (Omega)*: T3 e T1 certificate (checkpoint O-1, O-2): 30 file fra
`Betfair/omega/**`, `frontend/src/lib/omega*.ts`, `SchedaChiusuraOmega.tsx`, `ManualPanel*`,
`migrations/omega_*_2026-09-17.sql`, `CRONOSTORIA.md`. Suite Omega 1021, tsc 0, replay
35760084 15/15 e 35777617 5/5 puliti. Il commit lo fa l'utente; in stage SOLO questi file
(admin-6d ha i suoi non committati sullo stesso master: `safe_strategy/*`, `CLAUDE.md`,
`Betfair/mike/dossier.py`, frontend Safe).

*Migrazioni da applicare (utente, in quest'ordine)*: 1) `migrations/omega_proposte_coda_unica_
2026-09-17.sql` (coda unica proposte); 2) `migrations/omega_trades_status_cancelled_lapsed_
2026-09-17.sql` (stati). Entrambe idempotenti, scritte, non applicate, non provate contro
Supabase (⊘).

*Riavvio 2 (NON fatto)*: dopo T2 su master: `cd frontend && npm run build` dal principale
(T1 tocca `omega.ts`/`omegaProposte.ts`/scheda/`ManualPanel`; T2 `omega.ts`), migrazioni
applicate, riavvio app dall'utente. Checklist paper (solo dopo T2 certificata e 0 violazioni):
pannello Omega → `strategy_version` 3 (default), green-up spento per costruzione, finestre
1-44 / 46-85, k 1,11, fascia 1-2 %, cap 95/190/1000/300; modalità PAPER; avvio dal pulsante
dell'utente. Differenze paper/live dichiarate: bet delay NON applicato in paper (§7.14);
percorso via runner solo per le partite seguite («Segui live»), ripiego locale per le altre.
Job quote pre-partita e catch-up transizioni: «da lanciare» con permesso, non bloccanti.

*Worktree vivi (rimozione MANUALE: prima `cmd /c rmdir <wt>\.venv` e `cmd /c rmdir
<wt>\frontend\node_modules` dove c'è junction, poi `git worktree remove` senza --force, poi
verificare `.venv/Scripts/python.exe` e `frontend/node_modules` del principale)*:
`agent-a0af86bc55e604bb2` (T3, nessuna junction, già su master: rimovibile);
`agent-a5f04bb13d31c4d17` (T1, **JUNCTION `.venv` e `frontend/node_modules`**, già su master:
rmdir poi remove); `agent-af84954150e351fc6` (T2, nessuna junction, **lavoro NON ancora su
master: NON rimuovere**).

*Aggiornamento al parcheggio (h17:55, referto del delegato §9, NON verificato da me)*: i
quattro reperti (1)-(4) risultano FATTI nel worktree T2 (J3/J6 con `STATI_TERMINALI` e 6 test,
mutazione md5 rossa; fascia su `p_imp` con motivi `p_impl_*_fascia` e A11 sui due bordi;
pannello senza «ombra»; scenari legacy pinnati a 2, v4/v3/proposta-approvata a 3); suite
`Betfair/omega Betfair/stream` 2503 verdi. **Manca SOLO la battuta finale di replay**
(fermata prima del primo referto: i numeri di replay nel referto sono PRE-correzioni) e la
mia certificazione. Worktree T2: HEAD 3733f17, indice e stash vuoti, nessuna junction.

**Checkpoint O-3 (h20:20) — RIPRESA su ordine dell'utente («finisci entro 2 ore, poi paper»):
T2 CERTIFICATA e SU MASTER (non committata). OMEGA PRONTO PER IL PAPER.**
Fatto da me: battuta finale di T2 dal suo worktree (35797769 17/18, 35777617 17/18, sintetica
4/4: le uniche accuse erano due FALSI POSITIVI dei controlli in `cashout-globale`, trovati e
chiusi da me: **A9** giudicava anche il BACK di chiusura del cash-out (solo aperture lay ora)
e **B2** chiamava «fuori scala» la barra sotto zero dopo una perdita realizzata (ora ammessa
solo con realizzato < 0); test `test_a9_solo_aperture_lay_2026_09_17.py` (6), falsificazione
mia rossa su entrambi, md5 ripristinati). File di T2 (T3+T1+T2 fusi) copiati a file interi su
master con md5 identici; tre mutazioni mie su master (fascia riportata su p_nostra → 26 rossi;
`escludi` ignorato → 2 rossi; default k 1,0 → 4 rossi), ripristinate. Test di contratto UI
aggiornati ai default del 17/09 (`chiusuraUtente.contratto.test.ts`: versione 3, non più «in
ombra»). **Numeri su master**: suite Omega **1069 verdi**; `tsc` 0; vitest `src/lib` 1531/1531;
replay **35760084 18/18 puliti, 35797769 18/18, 35777617 18/18, sintetica 4/4: 0 violazioni**.
Gambe v4 sulle registrazioni vere: 35797769 `Any Unquoted Draw @80` (gamba A, liab 79 €) +
`Any Unquoted Home @50` (gamba B, liab 49 €); 35777617 `Any Unquoted Draw @65` (64 €) +
`2-2 @50` (49 €); 35760084 nessuna (margine max 0,65×); tutte 1,00 € e tutte vinte
(+0,95 € l'una: due partite NON sono un campione). Controlli v3 sollecitati: A8, A9, A10, A11,
C5, K1-K7, E3-E5, J3; mai sollecitati e dichiarati ⊘: A12 (tabelle storiche non stanno in una
registrazione), G2/G3/G4 sotto v3 (nessuna proposta è nata sulle tre partite con liability < cap;
G2-G4 esercitati sotto v2 nel checkpoint O-2), J6/J7 (scenario «parziali» assente). Debito
dichiarato: 126 test v2 pinnati in `conftest` a `strategy_version=2`; suite con 5 rossi
transitori una volta sotto carico CPU (ripetuta: 1069 verdi).
Referti: `CHECKPOINT_T2_RACCORDO_V3_2026-09-17.md`, `scratchpad/master_final_*.txt`,
`t2_*.txt`. Build del frontend: la fa admin-6d (una sola, riavvio 2) con i miei 7 file:
`lib/omega.ts`, `lib/omegaProposte.ts`, `lib/omegaProposte.test.ts`,
`lib/chiusuraUtente.contratto.test.ts`, `components/controlroom/SchedaChiusuraOmega.tsx`,
`components/omega/ManualPanel.tsx`, `components/omega/ManualPanel.cert.12set.test.tsx`.

*Punto esatto di ripresa (aggiornato h20:20)*: 1) utente: applica le 2 migrazioni Omega
(`omega_proposte_coda_unica`, poi `omega_trades_status_cancelled_lapsed`), riavvio 2 con la
build di admin-6d, pannello Omega (default già v3: verificare a video strategy_version 3, k 1,11,
fascia 1-2 %, finestre 1-44/46-85, cap 95/190/1000/300), modalità PAPER, avvio dal pulsante;
2) domani: referto forense del primo paper (gambe aperte per partita, p_impl, liability,
proposte scritte/firmate/ignorate, `schema_warn` assenti, differenze paper/live dichiarate);
3) poi Fase 0 permessi, debito test v2, scenario «parziali», Fase 3 paniere/CUSUM.
[Storico della prima chiusura h17:45, superato dal checkpoint O-3:] 1) T2: battuta
`35760084`/`35797769`/`35777617 --scenari tutti` + `_synth` → 0 violazioni; 2) verifica
del coordinatore (diff, suite ≥1056, mutazioni proprie: k 1,10 → A10 rosso; fascia su p_nostra
→ test rosso; seconda gamba sulla stessa cella → `cella_gia_bancata`), replay su master;
3) file interi + patch su master, `npm run build`, checkpoint O-3; 4) migrazioni, riavvio 2,
paper acceso dall'utente; 5) il giorno dopo: referto forense del paper (fill, k realizzato,
proposte firmate/ignorate), poi Fase 0 permessi (job quote, catch-up), debito dei 126 test v2,
scenario «parziali» sul banco, Fase 3 paniere/CUSUM, Fase 2 quota viva solo con dati nuovi.


### Sera del 17/09 — riavvio 19:08, reperto «tre righe su una partita», crediti in esaurimento (h19:55)

**Checkpoint 23 (h19:40) — FALSO ALLARME SU MERCATO CHIUSO, certificato.** Un Half Time Score
CLOSED al 45' (partita OPEN) restava per sempre in `mercati_allarme` → `source: rest` e
`last_error` fisso. Causa: `_aggiorna_copertura` guardava `ev["mo_status"]` (il MATCH_ODDS)
invece dello stato del BLOCCO (`ev["ht"]["status"]`/`ev["cs"]["status"]`). Fix (Sonnet 5, su
master, NON committato): `Scanner._mercato_attivo(market_id, now)` + esclusione immediata dalle
liste e dalle mappe (`stream_price_mono`, `price_mono`, `rilevante_da_mono`) in
`Betfair/safe_strategy/service.py`; 4 test nuovi nella sezione 6 di
`tests/test_incidente_quote_2026_09_17.py` (50 verdi), falsificazione sul codice vero fatta dal
delegato (guardia disattivata → rosso). Verifica MIA: diff riletto; confermato che la produzione
scrive `status` del blocco a ogni book, anche vuoto (`_apply_cs_book` riga ~817 e
`build_cs_block`), quindi la guardia lavora su un dato vivo; suite safe_strategy 1095 verdi
(delegato). Serve il riavvio dell'app per andare in produzione.

**Reperto (h17:26-17:36, Pieczonka v Trungelliti, evento 36077210) — verificato da me sul DB e
contro Betfair.** Su Betfair UNA sola posizione vera: #307 back Pieczonka 1.12 × 3 € (Strategia S
tennis, `strategy='tennis'`, live, bet 443223141303, abbinata 3/3), chiusa dal cash-out
dell'utente #317 (lay 1.08 × 3,11 €, +0,11 € bloccati). Le altre due righe sotto la stessa
partita sono PAPER del SECONDO motore tennis: #300 back Pieczonka 1.14 e #309 lay Trungelliti
7.4, `strategy='model'`, `meta.kind='tennis'`, prodotte da `tennis_opportunity.py` e piazzate da
`_auto_trade_opps` (paper perché `strategy_modes.model=paper`). Quel motore è acceso da
`params.auto_trade_tennis` (bot_service.py righe 92/264/361/6796) che NON governa la Strategia S
(governata solo da `variants`); la scheda «Solo tennis» della Control Room lo forza a `true` a
ogni avvio per un equivoco del 14/09 (`SESSIONE_LIVE_TENNIS_2026-09-14.md` riga 18). Il motore
modello ha aperto la stessa direzione due volte (back leader + lay sfavorito): difetto di disegno,
in paper. Attività: 126 righe `exit_hold` in 12 minuti (74 su #300, 52 su #309), 107 etichettate
LIVE su righe PAPER: (a) `_write_model_hold` e il gate a riga ~3514 non scrivono il `mode` della
riga e `_log` timbra quello del servizio; (b) `_hold_firma` include `locked` al centesimo → una
riga a quasi ogni tick. L'utente ha fermato il bot alle ~17:39.

**In corso (delegato Sonnet 5, id a64ecb19f51a9f71a, avviato h19:45)**: `mode` della riga in
tutti i log per-trade; firma dell'ATTIVITÀ `exit_hold` senza il centesimo (solo cambio di
sostanza o di SEGNO del locked; `meta.exit_hold` invariato); test nuovi falsificati
(`test_exit_hold_dedup_2026_09_17.py` aggiornato, `test_due_motori_tennis_2026_09_17.py`);
frontend: `soloTennis.ts` non forza più `auto_trade_tennis`, etichetta chiara in
`BotParamsSheet.tsx`, tooltip righe modello in `SafeTradesTable.tsx`; nota nel documento del
14/09. Da verificare da me al rientro: diff, suite safe (attesa ≥1095 verdi), vitest sui file
toccati, tsc 0; poi `npm run build` al riavvio 2. DECISIONE UTENTE PENDENTE: spegnere il motore
modello tennis (`auto_trade_tennis`) dai parametri di Safe; io non tocco i parametri.

**Altri lavori vivi**: delegato ab70cb4cf8bd9f258 (4 bot tennis, worktree
`agent-ab70cb4cf8bd9f258`, F1-F4 in corso: referto atteso; poi verifica mia e porto su master);
worktree `agent-a321205292fc29b45` (tennis «al ms», parcheggiato; junction: rmdir prima).
Commit locali non pushati: 6 (fino a 37e681d) + master sporco (fix CLOSED, fix in corso, T3/T1 di
admin-b1). Promemoria all'utente: test live cash-out globale (stake minimo), sincronizzazione
orologio (W32Time, −2,08 s), push dei commit, riavvio 2 Omega con le due migrazioni
(`omega_proposte_coda_unica_2026-09-17.sql`, `omega_trades_status_cancelled_lapsed_2026-09-17.sql`).

**Checkpoint 24 (h20:20) — RIGHE PAPER DEL MODELLO TENNIS ETICHETTATE LIVE + RUMORE exit_hold +
SCHEDA «SOLO TENNIS», certificato da me (su master, NON committato, serve riavvio app +
`npm run build`).** Costruito (Sonnet 5): `mode` della riga su TUTTI i log per-trade di
`bot_service.py` (exit_hold ×3 compresa la proposta in attesa di approvazione, exit_wait,
exit_retry, exit_failed, feed_blind, skip); nuova `_hold_firma_attivita` (motivo, tipo, codice,
fonte, SEGNO del locked) per l'attività, `meta.exit_hold` invariato al centesimo;
`soloTennis.ts` non forza più `auto_trade_tennis` e non annuncia «entrate automatiche»;
etichetta «Secondo motore: opportunità di MODELLO tennis in automatico» in `BotParamsSheet.tsx`;
tooltip «trade di modello (secondo motore)» in `SafeTradesTable.tsx`; nota 17/09 in
`SESSIONE_LIVE_TENNIS_2026-09-14.md`. Test: `test_exit_hold_dedup_2026_09_17.py` (+0,00→−0,03
scrive, −0,03→−0,05 no, −0,05→+0,02 scrive; mode paper anche con servizio live; 2
falsificazioni), `test_due_motori_tennis_2026_09_17.py` (Strategia S piazza con
`auto_trade_tennis=False`; il modello piazza solo con il suo interruttore, `strategy='model'`,
`meta.kind='tennis'`). Verifica MIA: diff riletto; **suite safe_strategy 1105 verdi** (da 1095);
falsificazione mia (firma dell'attività riportata al centesimo → 2 test rossi, file ripristinato
md5 identico); **vitest 127 verdi** (controlroom + BotParamsSheet), **tsc 0**. Non toccato (è
strategia): `tennis_opportunity.evaluate` produce back leader + lay sfavorito sulla stessa partita
(stessa direzione due volte) — da portare all'utente. DECISIONE UTENTE PENDENTE: spegnere
`auto_trade_tennis` (motore modello tennis) dai parametri di Safe.

**4 bot tennis — consegna del delegato ab70 (h20:05), NON ancora verificata da me.** Worktree
`agent-ab70cb4cf8bd9f258` (branch `worktree-agent-ab70cb4cf8bd9f258`), checkpoint del delegato:
`Betfair/stream/tennis_live/CHECKPOINT_4_BOT_TENNIS_2026-09-17.md`. F1 dichiarata completa
(3 reperti money-critical, 6 divergenze decise nel senso del dossier, 2 reperti nuovi, 1 buco:
`_instantiate_bot` dava i minimi .it solo allo scalper); F2/F3/F4 NON iniziate. Numeri dichiarati:
suite `Betfair/` 4206 verdi / 28 skip nel worktree; replay `certifica <bot> 35794049 35790089
--data-dir C:/Users/Admin/Desktop/tennis_rec/20260707 --scenari tutti` → 4 bot × 20 partite,
0 violazioni; esposizioni orfane SWING 7,57 € e PRO 3,52 € → 0; rifiuti a raffica 20.534/8.132
→ 40 veri. REPERTO APERTO dichiarato: scenario `live` con minimi attivi, scalper lascia 0,31 €
di sbilancio contro tolleranza 0,30 (bump al multiplo di 0,50), da misurare su più partite;
12.398 azioni di quel giro da ricontare. File condivisi toccati nel worktree: `registro_bot.py`
(4 schede tennis), `test_registro_bot_2026_09_16.py`, `test_cert_banco_2026_09_16.py`,
`tennis_runner.py` (`_instantiate_bot`). Da fare al rientro: verifica mia (diff, suite, replay
rieseguiti da me con `live` esercitabile, falsificazioni), chiusura del reperto 0,31/0,30, poi
porto su master (junction: rmdir prima di rimuovere il worktree), poi F2-F4.

**Reperto 25 (h20:15, Mike LIVE, Bnei Yehuda v Maccabi Herzliya, evento 36077571) — COPERTURA
SOTTO MINIMO MAI PIAZZATA + RITENTATIVI SENZA FRENO.** Under 3.5 back 5 € a 1.44 abbinata
(#4886, bet 443221432246, 17:16:03). Copertura Over 4.5 da 1,21-1,37 € a 5.4-5.9: 104 righe
`over_cover` in `error` con `live_rifiutato:CANCELLED_NOT_PLACED`, una ogni ~5 s dalle 17:16
alle 18:13 (leg_ref fino a 99+), stato `LIVE_UNCOVERED`. Il place-and-trim live
(`omega_market.place_submin_live`: parcheggio 2 € a 1000 → cancel parziale → replace alla
quota reale) fallisce al gradino 3: betfairlightweight descrive il codice come «Bet cancelled
but replacement bet was not placed». Storico DB: ZERO coperture sotto minimo riuscite in live
(Mike e Omega), 111 rifiuti oggi. Mike non ha freno sui rifiuti ripetuti della copertura
(`_place_fail`/`place_rifiutato` in `Betfair/mike/service.py` ~735: riga in error, `skip`, e il
ciclo dopo riserva una riga nuova). Parametro esistente `exact_sizes` (`Betfair/mike/config.py`
~191): `False` = copertura arrotondata al minimo .it (decisione dell'utente, non presa).
DA FARE (domani, Opus 5): freno fail-closed sui rifiuti identici ripetuti (N tentativi poi stop
gamba + avviso critico in UI), scenario nel banco che sollecita il rifiuto ripetuto; place-and-trim
LIVE marcato NON certificato in-play finché non provato con 0,01 € su ordine dell'utente;
riguardare la regola (memoria `feedback_place_and_trim_importi_al_centesimo`) alla luce dei fatti.
Utente avvisato alle 20:20 con le tre opzioni (copertura manuale 2 €, fermare Mike,
`exact_sizes=false`).

**ORDINI DELL'UTENTE su Mike (h20:25, testuali, da eseguire alla ripresa di STASERA).**
Contesto: l'utente ha chiuso a mano la posizione Under 3.5 e ha FERMATO TUTTI I BOT.
1. **Mike in pre-match NON deve operare su Over 4.5**: perché lo ha fatto? Viola la strategia.
   Da accertare sul DB/attività (righe `over_cover` con `minute_at_entry` 4-11 e stato
   pre-match → live) e sul codice (`Betfair/mike/engine.py`, fasi della copertura) contro
   `Betfair/mike/COSTITUZIONE_MIKE.md`; referto con le righe esatte.
2. **Il place-and-trim funziona alla perfezione su tutti i competitor** (Bet Angel, Fairbot):
   va risolto UNA VOLTA PER TUTTE. Trovare il gradino sbagliato nella nostra sequenza
   (`omega_market.place_submin_live`: parcheggio 2 € a 1000 → cancel parziale → replace;
   Betfair risponde `CANCELLED_NOT_PLACED` al replace, 111/111 oggi, 0 successi storici) e
   confrontarla con la sequenza dei competitor (docs Betfair replaceOrders/cancelOrders in-play,
   bet delay, ordine dei gradini, size del replace). Poi **test dedicato dal vivo su una partita
   qualsiasi, con l'utente**, per validarlo una volta per tutte.
3. **Fixare OGNI cosa**: rispettare i limiti Betfair (niente 104 tentativi in un'ora: freno
   fail-closed sui rifiuti ripetuti, rispetto dei limiti di chiamate) e il bot deve essere
   INFORMATO DI OGNI COSA (esito di ogni ordine, stato del mercato, sospensioni).
4. Posizione chiusa a mano dall'utente; tutti i bot fermi (h20:25).
5. **La copertura Over 4.5 deve essere come da strategia**, e il bot deve essere informato dei
   cambi di stato del mercato (SOSPENSIONI, riaperture, ecc.). La fase pre-match → live è
   andata bene; il pasticcio è iniziato con la copertura Over 4.5.
6. **Mike deve funzionare come da strategia in TUTTE le fasi**: la copertura è DIVISA IN DUE
   FASI IN BASE AL TEMPO (due tranche) e va rispettata così. Risolvere la copertura per intero.
Metodo alla ripresa: replay banco comune sulle registrazioni con scenario «rifiuto ripetuto della
copertura» e «mercato sospeso durante la copertura»; Opus 5 costruisce, io verifico; niente live
finché il test dedicato del punto 2 non è fatto con l'utente.


### Ripresa serale (h20:40) — tre flussi in parallelo, due ore (ordine dell'utente)
Ordine testuale: «1) Finisci il lavoro sul tennis; le opportunità modello (SIA CALCIO CHE
TENNIS) devono apparirmi come la card della chiusura (sotto, card dedicata) CON TUTTE LE
INFORMAZIONI E I DUE TASTI: "PIAZZA" parte l'ordine, "RIFIUTA" la scheda viene rifiutata.
2) Occupati di Mike e indaga a fondo il place-and-trim, documentati davvero. 3) Entro stasera:
tutti i bot tennis finiti e in UI come da istruzioni, Mike corretto, place-and-trim corretto a
livello globale (lo usiamo anche altrove). Due ore, dritti al punto.»
Delegati (Opus 5): A = Mike + place-and-trim (`Betfair/mike/**`, `omega_market.place_submin_live`,
`submin.py`, banco Mike; referto `Betfair/mike/CHECKPOINT_2026-09-17_SERA.md`); B = proposte di
opportunità con card PIAZZA/RIFIUTA (`safe_strategy/**` tranne scanner/service/stream, frontend
safestrategy+controlroom+safeBot.ts+SafeStrategy.tsx, migrazione nuova se serve; referto
`Betfair/safe_strategy/CHECKPOINT_PROPOSTE_OPPORTUNITA_2026-09-17.md`); C = ab70 ripreso nel suo
worktree (reperto 0,31, replay `live`, F2, F3, F4; referto `CHECKPOINT_4_BOT_TENNIS_2026-09-17.md`).
Io: verifica indipendente di ciascuno + indagine mia sul place-and-trim (docs Betfair) per
incrociare A; `npm run build` alla fine; tutti i bot fermi, app da riavviare dopo.

ORDINE (h20:55, testuale): «il place-and-trim DEVE ESSERE AGGIUSTATO E RESO UNIVERSALE PER OGNI
CASO CHE CI SERVE PRESENTE E FUTURO» → un solo modulo (nucleo puro + adattatori REST e flumine),
back/lay, pre-match e in-play, .it/.com, sospensioni, parziali, report Betfair completo a ogni
gradino, test di contratto sui chiamanti; passato al delegato A. Reperto mio: `CANCELLED_NOT_PLACED`
è il codice esterno del ReplaceInstructionReport («bet cancelled but replacement bet was not
placed»); la causa vera è in `placeInstructionReport.errorCode`, che il nostro codice scartava.

4 bot tennis, seconda consegna di ab70 (h21:05, non verificata da me): reperto 0,31 chiuso
(causa = skip sotto minimo di lato in live → flatten che ritenta a ogni book: 12.249 skip →
4, azioni 12.398 → 142, violazioni 4.087 → 0; residuo < 0,25 € accettato UNA volta e dichiarato,
soglia K5 non alzata); replay 2 eventi × 10 scenari con `live` esercitabile: scalper/pro/flb 0,
SWING 2×K4 su 35790089 live (CLOSING senza nulla a mercato, aperto); minimi .it portati a tutti e
4 nel runner; suite Betfair/ 4206 verdi. F4 INVALIDO (id con `
`: NO_RAW ×17, 0 tick) da rifare
con 17 id espliciti (ore); F2 NO (writer di pnl/commission/settled_at e ref stabile mancanti); F3
non iniziata, scritta solo `migrations/tennis_bot_service_control_2026-09-17.sql` (non applicata).
Place-and-trim nel banco tennis: violazioni salgono perché i controlli non distinguono TRIMMATO da
sotto-minimo → passato al delegato A per il modulo unico. Ora: ab70 → F2 + K4 swing + F4 corretto
in background; delegato D (Opus 5, stesso worktree, solo frontend) → F3 Control Room.

**Checkpoint 26 (h21:40) — PLACE-AND-TRIM UNIVERSALE, nucleo certificato da me; Mike B/D/E in
corso.** Delegato A (Opus 5): indagine con fonti in
`Betfair/stream/trading/PLACE_AND_TRIM_INDAGINE_2026-09-17.md`; diagnosi dai nostri dati: gradini
1 (parcheggio) e 2 (`sizeReduction`) passati 171/171 → Betfair ACCETTA l'ordine ridotto sotto
minimo a riposo; fallisce SOLO il `replaceOrders` (cancel+place, il place ripassa la validazione;
cancellazione non annullata). Bet Angel usa la stessa sequenza e non garantisce nulla in-play.
Modulo UNICO: nucleo puro `pianifica_submin`/`quota_non_abbinabile`/`esito_istruzione`/
`codice_rifiuto`/`marca_submin` in `Betfair/stream/trading/submin.py`; adattatori REST
(`omega_market.place_submin_live`) e flumine (`start_submin`/`advance_submin`), firme compatibili
(`best_back`/`best_lay` kwargs opzionali → nessun chiamante toccato). Percorso A (2 chiamate,
parcheggio ALLA quota target se non abbinabile, nessun replace; opt-in: solo con book passato e
non FOK); percorso B (3 chiamate, un solo tentativo). Codice di rifiuto ora `ESTERNO:INTERNO`
(`placeInstructionReport.errorCode`) + log critical col report intero; rilettura dell'ordine da
Betfair dopo il taglio (fail-closed); marca `submin` per il banco. Contratto in
`Betfair/stream/trading/INTERFACES.md`; test `test_submin_nucleo_2026_09_17.py` (19),
`test_submin_contratto_chiamanti_2026_09_17.py` (6, censisce 15 chiamanti). Verifica MIA: 95 test
submin/place-and-trim/contratto verdi; percorso A confermato opt-in; RICHIESTA MIA in corso:
guardia cap sul parcheggio LAY del percorso A (liability minimo×(quota−1) alla quota target).
Ordine 1 dell'utente («Over 4.5 in pre-match») accertato da A sul DB: NON è successo (LIVE dalle
18:00:59, prima `over_cover` alle 18:03:52, `minute_at_entry` 2..17, mai null; 171 righe totali);
divergenza: `COSTITUZIONE_MIKE.md` riga 11 dice ancora «live BLOCCATO». Decisione strategica da
portare all'utente sulla copertura sotto minimo: (1) `exact_sizes=false` → 2 € con place normale;
(2) copertura passiva sotto minimo (percorso A, ≥ best back); (3) fail-closed dichiarato. In corso
da A: B (freno rifiuti ripetuti, sub-delegato), D (SUSPENDED/OPEN/CLOSED), E (scenario banco +
replay Mike). Diff proposto da applicare (io) a `live_order_worker.py:2621-2645`: serializzare
`park_price`/`serve_replace`.

**4 bot tennis, terza consegna di ab70 (h21:35, verifica mia in corso in background)**: F2 fatto
(ref stabile ancorato al `bet_id`, altrimenti impronta deterministica; `pnl`/`commission`/
`settled_at` scritti a `market.closed`; in LIVE `pnl` resta None perché `simulated.profit` non
vale: prossimo passo = cleared orders REST); SWING 2×K4 chiuso (uscite anticipate di
`_manage_trade` su book monco lasciavano il trade in memoria; ora `_puo_dimenticare`), replay
35790089 live 0; F4 VALIDO lanciato in background (17 COMPLETE × 10 scenari × 4 bot, esito in
`Betfair/stream/tennis_live/REFERTO_F4_2026-09-17/`, testata «COMPLETE x17»); suite Betfair/ 4224
verdi. Delegato D (F3 Control Room, frontend nel worktree) in corso.

**Checkpoint 27 (h22:15) — PROPOSTE DI OPPORTUNITÀ (calcio+tennis) con card PIAZZA/RIFIUTA,
certificate da me (su master, NON committato); 4 BOT TENNIS: backend PORTATO su master, F4 a
zero.** Delegato B (Opus 5): nessuna tabella/RPC nuova: proposta = riga `safe_strategy_requests`
`kind='place'`, `status='proposed'`, `payload.opp_key` = `event_id|kind:market_type:selection_id:side`
(senza prezzo, così il rifiuto tiene); PIAZZA = `safe_request_approve` → `pending` →
`_request_place` (strada manuale, consapevolezza da `_execute`); RIFIUTA = `safe_request_ignore` →
`rejected`; DECADUTA quando sparisce dal feed/partita non in gioco; modalità da
`modalita_di_strategia("model")` alla proposta e ricalcolata all'approvazione (senza, PIAZZA con
servizio live e model=paper sarebbe stato sempre rifiutato); attività `proposta_opportunita`/
`opportunita_piazzata`/`opportunita_rifiutata`/`opportunita_decaduta` col `mode` della riga; card
`SchedaPropostaOpportunita.tsx` sotto le chiusure con tutte le informazioni, PIAZZA (doppia
conferma in LIVE) e RIFIUTA. `auto_trade_opportunities` e `auto_trade_tennis` non piazzano più
nulla; `auto_trade_combos`/`auto_trade_anomalies` NON convertiti (motore proprio; oggi spenti):
DECISIONE UTENTE. Migrazione `migrations/safe_proposte_opportunita_2026-09-17.sql` (2 indici).
Verifica MIA: suite safe_strategy 1119 verdi; falsificazione mia (`_proponi_opps` neutralizzata →
12/14 rossi, file ripristinato md5 identico); vitest controlroom+safestrategy 311 verdi; tsc 0
(prima del porto tennis). NON certificata sul banco (nessun replay `certifica safe`): da fare prima
di paper/live delle proposte. Referto `Betfair/safe_strategy/CHECKPOINT_PROPOSTE_OPPORTUNITA_2026-09-17.md`.

4 bot tennis: F4 finito (ab70): 680 repliche (17 COMPLETE × 10 scenari × 4 bot), 0 violazioni
per tutti; K6 corretto nel controllo (non accusa più `Cancelling`, test parametrizzato che
l'esenzione non mangia il controllo); suite worktree 4229 verdi. Verifica MIA: suite tennis_live+
banco nel worktree 1366 verdi; replay swing 35790089 live rieseguito da me 0 violazioni (K4 ×2726).
PORTO su master: patch applicata (`git apply`, 27 file) + 12 file/cartelle nuovi copiati (audit,
checkpoint, REFERTO_F4, certificazione_bot.py, tools/, condotta_ordini.py, test, 2 migrazioni);
suite tennis_live+tennis_scalper+stream/tests su master **1582 verdi**. Conflitti in
`useControlRoom.ts` (6 blocchi) e `pages/ControlRoom.tsx` (3) fra card opportunità e righe tennis:
risoluzione delegata (Opus 5), poi tsc 0 + vitest + build. F3 (delegato D, frontend): 4 righe
indipendenti in Control Room (`controlRoom.ts` Bot = calcio|tennis, `tennis.ts` sez. 6,
`interruttori.ts` 4 interruttori + fix `fermaBot`/`cambiaImporto`/`cambiaModalitaServizio` che con
`else` finivano su Omega, `useControlRoom.ts`, `righeBot.ts`, `PannelloBot.tsx`, `SchedaPartita.tsx`,
`pages/ControlRoom.tsx`); migrazione `tennis_bot_service_control_2026-09-17.sql` estesa
(`tennis_bot_service_update_params`, `get_tennis_bot_orders_today`); vitest 370 verdi nel
worktree. NON verificato: RPC contro DB vero; writer del runner su `tennis_bot_service_control`
(heartbeat/stats) — da confermare; in LIVE `pnl` tennis resta None (cleared orders REST: prossimo
passo). Il worktree ab70 resta (junction: rmdir prima di rimuoverlo).

**Checkpoint 28 (h22:50) — MIKE: freno sui rifiuti ripetuti, stato del mercato sulla copertura,
scenario nel banco, guardia cap sul parcheggio: verificati da me; UN BUCO nel controllo trovato
dalla mia mutazione (in chiusura).** Delegato A (Opus 5, sub-delegato per B/D riletto e
falsificato da A): `cover_rifiuti_max` (3) e `cover_retry_min_s` (15) in `config.py`;
`registra_rifiuto_copertura` conta PER CODICE (esterno:interno), `copertura_bloccata`,
`_freno_copertura` in `decide()` PRIMA di `_mai_sovracopertura`; stato `LIVE_COVER_BLOCKED` nel
ctx (non in `E.STATES`: niente migrazione), attività `error` critical allo scatto, «Riprendi»
sblocca; il freno filtra solo `role == "over_cover"` (mai le uscite). Stato mercato: due buchi
chiusi (`_decide_cover_pending` non guardava il mercato; `_sorveglia_sospensione` guardava solo
OU35 con lay vive) → gate espliciti + `_sorveglia_mercato_copertura` (una riga per transizione
`mercato_sospeso`/`mercato_riaperto`); IGNOTO = non aperto. Banco: scenario `copertura-rifiutata`
(finto Betfair rifiuta SEMPRE gli ordini sotto minimo con `CANCELLED_NOT_PLACED` +
`placeInstructionReport.errorCode=INVALID_BET_SIZE`, `banco_comune.py` `guasti["place_rifiuto"]=-1`
additivo), controlli S1 (a freno scattato nessuna riproposta) e S2 (nessun place/cancel di
copertura con Over 4.5 non OPEN); tarature dichiarate `cover_rifiuti_max=1`, `stake=3` (con stake
10 la copertura supera il minimo e S1 resta ×0). Guardia cap sul parcheggio: `liability_parcheggio`,
`guardia_cap_parcheggio`, `pianifica_submin(max_stake=)` ripiega su B o rifiuta
`SUBMIN_CAP_PARCHEGGIO`; regola in INTERFACES.md. Diff `live_order_worker.py` (park_price/
serve_replace) applicato da me. Verifica MIA: suite mike+omega+stream/tests **3096 verdi**; replay
`certifica mike 35760084 --scenari copertura-rifiutata` **0 violazioni, S1 ×4578, S2 ×21**;
mutazione mia `registra_rifiuto_copertura → return None` (rifiuti non contati, freno mai
scattato): **0 violazioni, S1 ×0** → il banco NON vede il loop di oggi se il conteggio si rompe:
S3 (contato dagli ESITI delle gambe `over_cover` rifiutate, non dal contatore del bot) e S4
(ritmo minimo di mercato) aggiunti in `certificazione.py`; VERIFICA MIA (h23:00): stessa
mutazione → **17 violazioni, S3 ×17**; ripristino cmp identico; replay pulito **0 violazioni,
S1 ×4578, S3 ×4578, S4 ×1**; suite Mike 763 verdi; contratto UI/backend 40 verdi
(`BACKEND_ONLY_PARAMS` vuota, `frontend/src/lib/mike.ts` con i 2 parametri e riga attività
`mercato_sospeso`/`mercato_riaperto` per la copertura, vitest mike 58 + 142 verdi). CHECKPOINT
28 CHIUSO. Aperti (referto A §6): scenario «sospensione forzata»
non creato (S2 ×21-44 solo dalle registrazioni); replay su 2 registrazioni non 4; controlli del
banco sulla marca `submin` non implementati; Betfair in-play non verificato (test dal vivo con
l'utente, procedura in `Betfair/mike/CHECKPOINT_2026-09-17_SERA.md` §5, rischio max 2 € per
tentativo); frontend Mike (2 parametri + riga attività `mercato_sospeso` per la copertura) in corso
(Sonnet 5); DIVERGENZE per l'utente: `COSTITUZIONE_MIKE.md` riga 11 «live BLOCCATO»; N=3/15 s non
misurati; scelta sulla copertura sotto minimo (exact_sizes=false / passiva A / fail-closed).

**Checkpoint 29 (h23:20) — CHIUSURA DELLA FINESTRA SERALE: tutto su master, NON committato,
build fatta (20:48, `frontend/dist`), pronto per il riavvio 2.** Numeri finali verificati da me:
suite Python intera `Betfair/` **4643 verdi** (dopo il fix del ritiro non confermato:
`omega_market._submin_ritira` ora tratta un `FAILURE` di Betfair come IGNOTO → `pending`, mai
rifiuto certo: buco money-critical trovato dal delegato A sotto i 2 test rossi di
`test_consapevolezza_ordine_2026_09_16.py`, il cui finto è stato completato con
`list_market_book`/`current`; 3 test nuovi, falsificati; decisione mia: guardia lasciata
GLOBALE, direzione sicura); frontend **tsc 0, vitest 2739 verdi, build ok** (dopo 2 fix del
delegato B: percentuali via `fmtPct`/`fmtNum`, contratto `fetchSafeRequests` ripristinato con
proposte filtrate dopo la lettura). Control Room: reperti 1 e 3 chiusi (`FONTI_RICARICA` a 18
nomi; chiusi dei 4 bot tennis in `chiuse` con netto = pnl − commission, mai paper+live, riga
senza pnl non entra); reperto 2 (barra di giornata senza i 4 bot tennis) → DECISIONE UTENTE.
MIGRAZIONI DA APPLICARE PRIMA DEL RIAVVIO 2 (ordine): 1) `omega_proposte_coda_unica_2026-09-17.sql`,
2) `omega_trades_status_cancelled_lapsed_2026-09-17.sql`, 3) `safe_proposte_opportunita_2026-09-17.sql`,
4) `tennis_bot_pnl_2026-09-17.sql`, 5) `tennis_bot_service_control_2026-09-17.sql`.
NON certificato / da fare domani: proposte di opportunità sul banco (`certifica safe_*`);
test dal vivo del place-and-trim con l'utente (procedura `Betfair/mike/CHECKPOINT_2026-09-17_SERA.md`
§5); RPC tennis contro il DB vero; `pnl` tennis in LIVE (cleared orders REST); controlli del banco
sulla marca `submin`; scenario «sospensione forzata» Mike; replay Mike su 4 registrazioni;
worktree `agent-ab70cb4cf8bd9f258` da rimuovere (rmdir junction prima). DECISIONI UTENTE aperte:
copertura Mike sotto minimo (exact_sizes=false / passiva A / fail-closed); `auto_trade_tennis`
(motore modello tennis: ora propone soltanto); `auto_trade_combos`/`auto_trade_anomalies` restano
automatici se accesi; barra di giornata col tennis; COSTITUZIONE_MIKE riga 11 «live BLOCCATO».

### Punto di ripresa (aggiornato h23:20)
1. Leggere i checkpoint 23-29 e il blocco Omega (admin-b1, O-3). Master sporco = lavoro certificato
   di stasera, da committare su ordine dell'utente (mai `git add -A`; file per file).
2. Se il riavvio 2 non è avvenuto: 5 migrazioni sopra → riavvio app → verifica a video con
   admin-b1 (Omega) e con l'utente (card opportunità, 4 righe tennis, Mike).
3. Domani: test dal vivo place-and-trim (0,05 €) con l'utente; banco sulle proposte; decisioni
   utente sopra; poi worktree «al ms» (a321).
