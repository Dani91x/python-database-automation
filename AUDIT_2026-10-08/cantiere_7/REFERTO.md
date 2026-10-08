# CANTIERE 7 — Banco di Omega: reperti RB-1 … RB-5 (referto del delegato, 08/10/2026)

Delegato di costruzione (cloud). Worktree: `/home/user/python-database-automation/.claude/worktrees/agent-adb756da0c06e837d`.
Nessun commit, nessun `git add`. `omega_v3.py`, `omega_engine.py`, `omega_service.py`: NON toccati.

## 0. In breve

| reperto | causa vera (verificata sul raw) | correzione | effetto sul replay |
|---|---|---|---|
| RB-1 | NON la conflazione: flumine non passa MAI i book `CLOSED` a `process_market_book` (`MotoreReplay._a_flumine` come `FlumineSimulation`), e il replay di Omega non aveva `process_closed_market` (Mike lo ha dal 30/09). La conflazione pero' poteva davvero perdere un `CLOSED` nello stesso secondo di un altro book | `OmegaCert.process_closed_market` -> `applica_book`; in `applica_book` lo stato terminale non passa dalla conflazione ed e' consegnato una volta sola | MO e CS chiusi arrivano allo scanner (nota nuova nel referto) |
| RB-2 | `applica_book` consegnava ogni mercato a catalogo dal primo all'ultimo book | finestre di sottoscrizione della produzione: `Scanner.relevant_market_ids` (funzione VERA) ricalcolata ogni 0,5 s di mercato, esposizioni di Omega nella forma di `list_bot_exposures`, conferma del flusso solo per i mercati sottoscritti. Interruttore per istanza, acceso SOLO dal replay di Omega | numeri spiegati in §4; tre comportamenti di PRODUZIONE emersi (§8) |
| RB-3 | `flusso_prezzi._ora_ms` = orologio del PC contro `dal_ms` di mercato | `AmbienteOmega` aggancia `_ora_ms` all'orologio di mercato (come `_mono`) e lo rimette a posto | «da 2941 s» al posto di «da ~8,5 milioni di s» |
| RB-4 | lo scenario `paper` girava senza runner: 5 x `paper_runner_non_disponibile` | `certifica_scenario` aggancia la porta del runner del banco (`trasporto.contesto("omega","canale")`) al solo paper senza trasporto gia' scelto | 35760084 `paper`: 438/0 -> **467/2**, lay '3 - 3' @300 5,26 vinto +5,00 = live |
| RB-5 | elenco del banco senza `_EMPIRICAL_CACHE`/`_MINUTE_CACHE` **e** (scoperto qui, con prova) senza tutte le cache del riavvio fra uno scenario e l'altro: `_LEG_RETRY` cambiava le DECISIONI degli scenari successivi | un elenco esplicito unico (`CACHE_DI_PROCESSO_DEL_BANCO`: quello del riavvio + le due tabelle) azzerato da `AmbienteOmega` a ogni ingresso/uscita e dal riavvio | 35797769: `chiuso-fuori-app` e `chiusura-abbinata-in-parte` dentro `tutti` aprivano '3 - 2' @50 al 23' invece di '3 - 3' @80 al 1' (lo scenario da solo apre '3 - 3') |

ATTESO del brief: 35760084 `apertura` 467/2 **invariato** (identico riga per riga salvo le note nuove); `tutti` **20/20 OK,
0 violazioni** su entrambe; paper che apre il '3 - 3' come il live: **dimostrato**. «HT ora CLOSED»: **no, e non deve**:
con le finestre di produzione l'HT esce dalla sottoscrizione al 45' e lo scanner vero il suo CLOSED non lo vede (§2.3).

## 1. Basi, registrazioni, ambiente

- PRIMA: cima `3b8ce19` (ramo integrato al via del cantiere, contiene b5547eb, C5, C12, C14, C15, W2), albero estratto con
  `git archive` in scratchpad. Poi, su ordine del coordinatore, worktree portato con `merge --ff-only` su `16d6c67`, su
  `1ac69d0` e infine sulla cima integrata `31fa6433` (contiene `d0cf8b94`; nessun file `Betfair/` cambiato da 1ac69d0) (fra `3b8ce19` e `1ac69d0` cambiano solo tennis, scalper, certifica per il tennis, frontend: nessun file di Omega,
  di `banco_comune.py` ne' del suo scanner).
  **Il mio PRIMA e' su `3b8ce19`** (lo dichiaro come chiesto). Prova che per Omega le basi sono equivalenti:
  `PRIMA16_35760084_apertura` (16d6c67) = `PRIMA_35760084_apertura` (3b8ce19) IDENTICI; `PRIMA16_35760084_tutti` diverso SOLO
  per una riga `skip x1 no_live_state` in `v4-riavvio`, che e' proprio la contaminazione di `_SKIP_SEEN` di RB-5 (dedup a 600 s
  di orologio del PC: dipende da quanto corre la macchina, §5.3). Il PRIMA del coordinatore su `1ac69d0`
  (`claude/blissful-sagan-hri7o6-rif-omega`) al momento del referto non era ancora sul remoto (`couldn't find remote ref`):
  confronto da fare sul PC/coordinatore (comandi §11).
- DOPO: `FINALE_*` = codice finale su `3b8ce19`/`16d6c67`; `DOPO1AC_*` = codice finale su `1ac69d0` (vedi §4.4).
  `DOPO_*` (senza suffisso) = versione intermedia SENZA l'elenco completo di RB-5, tenuta perche' prova l'effetto di `_LEG_RETRY`.
- Registrazioni: solo calcio `registrazioni_banco/35760084`, `35797769`, decompresse in `_live_raw/` del worktree (ignorata).
- Macchina: 4 CPU condivise con altri cantieri, carico 4-18 durante le misure (scritto accanto a ogni tempo in `tempi.log`).

## 2. RB-1 — lo stato terminale

### 2.1 Causa vera
Sonda sul raw (`sonda_raw_ht` nel test `test_raw_ht_sospeso_alle_16_47_53_e_chiuso_alle_16_47_58`): l'HT 1.259475535 ha due soli
messaggi dopo le 16:47:00, SUSPENDED alle 16:47:53.765 e CLOSED alle 16:47:58.751 — **5 s di distanza, non lo stesso secondo**.
La sonda del 07/10 vedeva «applicato SUSPENDED alle 16:47:58» perche' `GeneratoreLibri` riemette a OGNI riga il book corrente di
ogni mercato (quindi la conflazione del banco, che tiene il primo book dopo la finestra, consegna gia' lo stato piu' recente),
ma il CLOSED delle 16:47:58.751 non entrava MAI in `applica_book`: `MotoreReplay._a_flumine` (`banco_comune.py`, ramo
`if market_book.status == "CLOSED"`) lo passa a `_process_close_market` e torna `None`, quindi ne' `process_market_book` ne'
`su_book` lo vedono. Flumine lo consegna solo a `strategy.process_closed_market` (a ogni riga successiva), che Omega non aveva.
Il difetto della conflazione esiste comunque in forma piu' stretta: un CLOSED nello stesso secondo di un altro book, se
arrivasse ad `applica_book`, verrebbe scartato e dopo la chiusura non arriva piu' niente.

### 2.2 Correzione
- `Betfair/stream/backtest/banco_comune.py:2869` `applica_book` (blocco dopo `nel_buco`): `terminale = status == "CLOSED"`;
  un terminale gia' consegnato non si riconsegna (flumine lo ripete a ogni riga); un terminale NON passa dalla conflazione;
  `_ultimo_stato[mid]` scritto a ogni consegna. Costanti `STATO_TERMINALE` (`:2606`). Gli stati non terminali: regola di sempre.
- `Betfair/omega/tools/replay_registrazioni.py:1364` `OmegaCert.process_closed_market`: registra, porta l'orologio al
  `publish_time`, `banco.applica_book(book)`; conta in `chiusure_allo_scanner` (nota nuova «chiusure di Betfair consegnate allo
  scanner»). Stesso rimedio del replay di Mike del 30/09 (che chiama `_apply_market_book` direttamente: non toccato).
- Mike e Safe NON passano mai un CLOSED ad `applica_book`: per loro nulla cambia (provato, §6).

### 2.3 «HT ora CLOSED»?
No. Con RB-2 l'HT esce dalla sottoscrizione al 45' (16:45:48, `is_ht_candidate` falso) e nessuna gamba di Omega lo espone:
lo scanner di produzione non e' piu' iscritto e il CLOSED non lo riceve. Il test
`test_rb2_un_esposizione_di_omega_tiene_l_ht_oltre_il_45` mostra che con una gamba viva sull'HT il CLOSED arriva.
Chiusure consegnate sulla 35760084: O/U 6,5/5,5/7,5/4,5, MATCH_ODDS 17:54:13, CORRECT_SCORE 17:54:16 (solo dove Omega ha la
gamba sul CS). Sulla 35797769: MATCH_ODDS 21:01:26 (+ CORRECT_SCORE 21:02:30 dove c'e' una gamba).

## 3. RB-2 — le finestre di sottoscrizione della produzione

`banco_comune.py`: `GIRO_SCANNER_S = 0.5` (`:2602`, il `time.sleep(0.5)` di `safe_strategy/service.py::_ciclo_persistente`);
`ScannerReplay.finestre_di_produzione` (`:2709`, di serie False) e `fonte_esposizioni` (`:2714`); `_ricalcola_voluti`
(`:2723`): esposizioni rilette ogni `Scanner._ESPOSIZIONI_TTL_S` (10 s) di mercato e messe in `scan._esposizioni_fonti`
(lettura completa, come `Scanner._esposizioni`), poi `scan.relevant_market_ids(sport, adesso)`; `sottoscritto` (`:2740`)
ricalcola ogni 0,5 s di mercato; `applica_book` scarta e conta (`book_fuori_finestra`) il book di un mercato non voluto, PRIMA
della conflazione; `pubblica` (`:2964`) conferma il flusso solo dei mercati sottoscritti (gli heartbeat di produzione
confermano le sottoscrizioni della connessione). A interruttore spento tutto e' come prima (Mike/Safe identici, §6).
`replay_registrazioni.py` (Omega): `FINESTRE_DI_PRODUZIONE = True` (`:1192`), `esposizioni_omega` (`:1195`: righe
`omega_trades` pending/open/hedged -> `safe_strategy.db._righe_esposte`, la funzione vera), aggancio in `certifica_evento`
(`:2151`), nota nel referto con i book non consegnati per tipo di mercato (`:2319`).
Perche' solo Omega: il brief nomina il banco di Omega; Safe non ha ancora la sua fonte di esposizioni nel banco (senza, una
posizione Safe fuori finestra perderebbe le quote che in produzione tiene). Vedi «Decisioni / punti aperti».

## 4. Replay prima/dopo (`--worker 1`, uno alla volta), diff esclusi tempi e hash

File in `AUDIT_2026-10-08/cantiere_7/replay/`; confronto per scenario con `strumenti/per_scenario.py`, totale con
`strumenti/confronta.py`; diff salvati in `replay/diff_*`.

### 4.1 35760084 `apertura` — 467/2 INVARIATO
PRIMA e DOPO: 467 decisioni / 2 azioni, tick 482034, lay '3 - 3' @300 5,26, vinto, netto +5,00, read_market x108. Righe diverse:
1. `attivita'`: + `flusso_interrotto x1` — alle 16:29:21 (28', dopo il gol del 2-0) il book HT e' senza prezzi (16:28:12-16:29:35,
   sonda `sonda_flusso_ht`). PRIMA il CS, consegnato anche prima del 30', era fermo e Omega usciva da `_flusso_feed` con
   `no_live_state` gia' scritto alle 15:55 (dedup muto); DOPO il CS a quel minuto non e' sottoscritto (finestra dal 30'), il
   verdetto MO+CS e' vivo e la gamba HT dichiara l'HT fermo. Nessuna apertura in entrambi. Testo: «...(1.259475535); da 2941 s»
   (RB-3: eta' in tempo di mercato).
2. `righe di scan 463 -> 374`, `giri senza riga 1 -> 4`: meno mercati consegnati = meno riscritture; prima del KO-20' il MATCH_ODDS
   non e' sottoscritto (`RELEVANT_PRE_KO_SEC`), la riga nasce piu' tardi.
3. nota nuova finestre (138.004 book non consegnati, per tipo) e nota nuova chiusure.
4. `B4 x1 -> x88`: TUTTI pre-partita (15:07-15:40, `inplay` False, sonda `sonda_eta`): la riga esiste per il ramo pre-KO O/U e non
   si riscrive (MO non ancora sottoscritto). Omega non opera pre-partita: nessun effetto.
Sulla 35797769 `apertura`: 686/0 invariato; `righe 681 -> 373`, `giri senza riga 6`, `B4 x5 -> x306` (tutti pre-partita, sonda),
note nuove. Nessun'altra riga.

### 4.2 35760084 `--scenari tutti` — 20/20 OK, 0 violazioni, mai sollecitati 38/52 in entrambi
| scenari | PRIMA | DOPO | perche' |
|---|---|---|---|
| tutti | note | + nota finestre, + nota chiusure, righe di scan 434/463 -> 345/374, giri senza riga 1 -> 4 | RB-1/RB-2 (sopra) |
| base, giornata-reale | 438/0, `ft_cs:no_runner_by_model x75` | 438/0, x38 | dal 63' (17:25:19, 4-0) il CS esce dalla sottoscrizione (`is_cs_candidate`: max 3 gol per lato, sonda `sonda_finestre`) e il flusso della riga lo dichiara fermo: la gamba 2T non si valuta piu' (§8, punto P1) |
| apertura | 467/2 | 467/2, + `skip x3, flusso_interrotto x1` | come §4.1; `skip`: RB-5 (`_SKIP_SEEN` azzerato, ora ogni scenario scrive i propri skip come da solo) |
| **paper** | 438/0, `paper_runner_non_disponibile x5` | **467/2, lay '3 - 3' @300 5,26 won +5,00**, `canale_inviato x1, flumine_fill x1` | RB-4 (§5.4) |
| 13 scenari V3/V4 | `ht_cs` x121, `ft_cs` x56, 177 occasioni | `ht_cs` x123, `ft_cs` x51, 174 occasioni, `get_event_market_by_type x83, read_market x83` | prima del 30' il CS non e' nel feed di produzione: la V3 legge il CS dal REST (`_leg_market`), 83 letture; dopo il 4-0 il CS esce (come sopra). Nessuna gamba in entrambi |
| v3 legacy | 109 occasioni, `ft_cs` x56 | 80 occasioni, `ft_cs` x26 | idem (finestra 2T 55'-85': taglio dal 63') |
| tutti tranne il primo | `[NON ESERCITABILE]` solo dove la tabella era letta per prima | in ogni scenario | RB-5 |
| quasi tutti | `attivita'` vuota o ridotta | `skip x3/x4` con i loro motivi | RB-5 (`_SKIP_SEEN`): il dedup di 600 s di orologio del PC passava da uno scenario all'altro |
Copertura: A1 456->322 (base -37, giornata -37, paper -60: meno valutazioni, misurato per scenario con
`strumenti/sollecitati.py`), A2/A3/A4/A7/B1 6->2 (paper: 5 tentativi rifiutati -> 1 apertura; nessun altro), B2/J5 +29 (paper
438->467 giri), B3 3->6, E1 108->216, K1-K7 577->688, F1 6->9 (il paper ora opera e regola), B4 456->2106 (19 scenari x 88
giri pre-partita + feed-stantio), A5/A8 -72/-68 (meno occasioni V3). Tutto spiegato dalle righe sopra.

### 4.3 35797769 `--scenari tutti` — 20/20 OK, 0 violazioni, mai sollecitati 29/52 in entrambi
| scenari | PRIMA | DOPO | perche' |
|---|---|---|---|
| tutti | note | + note finestre/chiusure, righe 681-728 -> 373-422, giri senza riga 6-7 | RB-1/RB-2 |
| V3/V4 (cap-stretto, bot-fermo, riavvio, cashout-globale, proposta-approvata, uscite-automatiche, v4, v4-riavvio, v4-bot-fermo, rifiuti-betfair) | gamba 1T '3 - 3' @80 alle 19:02:13 (1') | stessa gamba, stesso prezzo, alle **19:01:53** (P_nostra 1,068% -> 1,063%) | al 1' il CS non e' nel feed di produzione: la V3 decide sul book REST (`_leg_market`). Sonda `sonda_sel`: PRIMA alle 19:01:53 il blocco CS della riga diceva '3 - 3' lay 110 (riga vecchia) -> nessun candidato; DOPO il REST dice 80 / 1,98 -> candidato. Tick e bet delay cambiano di conseguenza |
| cashout-globale | back '3 - 3' @75 alle 19:02:34 | back @70 alle 19:02:14 | la chiusura dell'utente segue l'apertura: 20 s prima, prezzo 70 (sonda `sonda_trade`) |
| **chiuso-fuori-app, chiusura-abbinata-in-parte** | 1T '3 - 2' @50 al **23'** | '3 - 3' @80 al **1'** | **RB-5, `_LEG_RETRY`**: i rifiuti di `rifiuti-betfair` (scenario precedente) restavano in memoria e tenevano ferma la gamba 1T. Prova: lo stesso scenario DA SOLO sul codice di partenza apre '3 - 3' @80 al 1' (`PRIMA_35797769_chiuso-fuori-app_DA_SOLO.txt`); la versione intermedia senza `_LEG_RETRY` nell'elenco (`DOPO_35797769_tutti.txt`) ha ancora il '3 - 2' al 23' |
| **esiti-ignoti** | 736/6: 1T '3 - 3' esito ignoto, 1T '3 - 2' esito ignoto, '3 - 2' @50 aperto 19:27:58, 2T 'Any Unquoted Home' @50 | **690/2**: 1T '3 - 3' esito ignoto (19:01:53), 2T 'Any Unquoted Home' esito ignoto (75'), nessuna gamba | il primo esito ignoto espone il CS (riga pending) -> sottoscritto 19:01:55; riconciliato libero alle 19:03:59 -> esposizione finita, minuto 3 < 30 -> CS fuori (sonda `sonda_finestre`). Il blocco CS resta nella riga col flusso fermo e Omega non valuta piu' la 1T fino al 30' (`sonda_leg`); dal 30' nessun candidato; il secondo guasto colpisce la 2T. 690 giri: senza posizioni aperte Omega gira alla cadenza a vuoto (60 s). Comportamento di PRODUZIONE (§8, P2) |
| v3, rifiuti, giornata-reale, apertura, base | note, skip | come sopra | RB-5 (`_SKIP_SEEN`, tabelle), REST prima del 30' (v3: 15 letture, rifiuti: 70) |
| paper | 686/0, nota `paper_fill` | 686/0, nota della porta del runner | il motore v2 su questa partita non trova candidati (come il 07/10): parita' non esercitabile qui |
Copertura: variazioni coerenti con le righe sopra (esiti-ignoti senza gambe: A9 48->44, A10/A11/J3 26->24, C5 52->48; due scenari
che aprono 22' prima: E5 291->362, CP1/CP3/CP4 283->354, J4 652->724; E3/E4/C4 +72/+1/+2; B4 795->6494 pre-partita).

### 4.4 Sulla cima 1ac69d0 e sulla cima integrata 31fa6433 (contiene d0cf8b94)
`DOPO1AC_*` = codice finale sul worktree portato su `1ac69d0`, contro `FINALE_*` (16d6c67): 35760084 `apertura`, 35797769
`apertura`, 35760084 `apertura --trasporto canale`, 35760084 `tutti`: **IDENTICI** (esclusi tempi e hash).
`DOPO1AC_35797769_tutti`: **FERMATO a meta' su ordine del coordinatore** (non e' nei referti; il `tutti` della 35797769 sul
codice finale e' `FINALE_35797769_tutti.txt`, base 16d6c67, che per Omega non differisce da 1ac69d0).
Worktree poi portato (ff-only) su `31fa6433` = cima del ramo integrato, che contiene `d0cf8b94`: fra `1ac69d0` e `31fa6433`
nessun file sotto `Betfair/` cambia; ripassati su questa cima i 23 test nuovi + il contratto del catalogo (162 passed, 3 skipped).

## 5. RB-3, RB-4, RB-5 nel dettaglio

### 5.1 RB-3
`replay_registrazioni.py:2071` (`AmbienteOmega.__enter__`): `FP._ora_ms = lambda: banco.ora*1000`, ripristinato in `__exit__`.
Solo testo e `secondi_fermo` senza `adesso_ms` (Omega passa gia' `now_ts` dove serve); `valuta_stato` nel banco non arriva mai al
confronto (lo stato del feed del banco non ha il blocco `flusso`). Nessun file di produzione toccato.

### 5.2 RB-4
`replay_registrazioni.py:2630` `_porta_del_runner_per_il_paper` + `with` in `certifica_scenario` (`:2677`): per `mode == "paper"`
e nessun trasporto attivo -> `trasporto.contesto("omega", "canale")` (stessa porta di `--trasporto canale`: `PortaCanaleOmega`
vera -> `WsBanco` -> `MotoreOrdini` -> `_dispatch` del runner sul flumine del banco). Con `--trasporto coda|canale|entrambi` si
rispetta il trasporto scelto (in `coda` il paper resta senza runner e la nota lo dice). Note aggiornate: descrizione dello
scenario (`:1105`, rigenerato `frontend/src/lib/replayBotCatalogo.ts`, una riga), testa del modulo, nota «PAPER» (`:2476`).

### 5.3 RB-5
`replay_registrazioni.py:1173-1218`: `CACHE_TABELLE_STORICHE`, `CACHE_DI_PROCESSO_DEL_BANCO` (= l'elenco di sempre di
`_riavvia_processo`: `_LEG_RETRY, _SKIP_SEEN, _BLIND_CYCLES, _MARKET_FIT_CACHE, _LAMBDA_CACHE, _IDLE_STATS_AT, _CATENA_OMEGA` +
le due tabelle), `_azzera_cache_di_processo`, usata da `_riavvia_processo` e da `AmbienteOmega` (ingresso e uscita).
**Oltre il brief, con prova**: il brief nominava le due tabelle; ho esteso l'azzeramento fra scenari all'elenco del riavvio
perche' `_LEG_RETRY` cambiava le decisioni (35760084: `apertura` dopo `paper` sul codice di partenza = 438/0 invece di 467/2,
`strumenti/contagio.py`: azzerando solo `_LEG_RETRY` torna 467/2; 35797769: §4.3) e `_SKIP_SEEN` rendeva i referti dipendenti
dalla velocita' della macchina (§1). E' separabile: togliere `_azzera_cache_di_processo()` da `AmbienteOmega` e lasciare le sole
tabelle rimette il comportamento del brief letterale. **Residui NON corretti** (fuori elenco, solo testi/contatori misurati):
`flusso_prezzi._NON_NOTO_AVVISATO` (`flusso_non_dichiarato` scritto solo dal primo scenario), `_EVENTS_REFRESH_AT`
(`list_today_football_events` 467 dentro `tutti` contro 473 da solo), la cache delle fixture (`fixtures_for_window` dichiarata
solo dal primo scenario); non toccati: `_LEG_RETRY_DB`, `_REALLY_OVER_CACHE`, `_DAILY_GOAL_WRITTEN`,
`_ULTIMO_STATO_SCANNER_OMEGA`. Scenario dentro `tutti` contro scenario da solo (35760084 `apertura`): DOPO differiscono solo
queste tre righe; PRIMA anche `skip`/`motivi`.

### 5.4 Parita' paper/live (35760084)
| | apertura (live, coda) | apertura `--trasporto canale` (live) | paper (porta del runner) |
|---|---|---|---|
| decisioni/azioni | 467/2 | 467/2 | 467/2 |
| ordine | lay '3 - 3' 5,26 @300 | lay '3 - 3' 5,26 @300 | lay '3 - 3' 5,26 @300 |
| esito | won, +5,00 netto | won, +5,00 | won, +5,00 |
| attivita' | `live_fok_fallback, place` | `canale_inviato, flumine_fill` | `canale_inviato, flumine_fill` |
| tick | 482034 | 482333 | 482983 |
Differenze ammesse e spiegate: il trasporto (coda: attesa sincrona del bet delay; canale: ack ed esito dagli eventi, tick
diversi). Fra live e paper SULLO STESSO trasporto (canale) cambia solo la modalita'. 35797769: nessuna apertura v2 in
nessuna modalita' (non esercitabile).

## 6. Non regressione degli altri bot (stesso `banco_comune.py`)
`certifica mike 35760084 --scenari base,cap-stretto` e `certifica safe_base 35760084 --scenari base,riavvio`, PRIMA (16d6c67) e
DOPO: **IDENTICI** (esclusi tempi e hash). Lo scalper non usa `ScannerReplay`.

## 7. Test, falsificazione, suite
Nuovi: `Betfair/stream/tests/test_banco_scanner_reperti_rb_2026_10_08.py` (9 test: book VERI dalla cache di betfairlightweight
sul raw `registrazioni_banco/35760084`, punteggi veri da `carica_punteggi`) e
`Betfair/omega/tests/test_banco_omega_reperti_rb_2026_10_08.py` (14 test: `OmegaCert` dal suo costruttore, `DbMemoriaOmega`,
funzioni di produzione `_empirical_table`, `_minute_table`, `_leg_note_rifiuto_senza_tentativo`, `_leg_retry_allowed`).
`python3 -m pytest <i due file> -q -p no:cacheprovider`: **23 passed**.
Falsificazione (`strumenti/falsifica.py`, file ripristinati da copia, sha verificato identico, `MUTAZIONE` residue 0) — 15 mutazioni,
15 rosse (`replay/falsificazione.txt`): M1 CLOSED sotto conflazione (1 rosso), M2 CLOSED a ogni riga (2), M3 Omega non passa la
chiusura (1), M4 finestre ignorate (3), M5 esposizioni non dette (1), M6 conferma anche fuori finestra (1), M7 voluti a ogni book
(1), M8 nessun aggancio orologio (1), M9 paper senza runner (1), M10 elenco tabelle vuoto (5), M11 nessun azzeramento
all'ingresso (1), M12 esposizioni con righe regolate (1), M13 finestre spente in Omega (1), M14 `_LEG_RETRY` fuori elenco (2),
M15 azzeramento nullo (5). Sha finali: `banco_comune.py 2a367b40…`, `replay_registrazioni.py 1a287054…`.
Suite: `python3 -m pytest Betfair/ -q -p no:cacheprovider` (worktree su 3b8ce19 + modifiche): **10974 passed, 64 skipped,
6 xfailed, 0 failed** (672 s). Un primo giro aveva 1 rosso (`test_il_file_ts_del_catalogo_e_allineato_al_registro`): la
descrizione dello scenario `paper` e' anche nel catalogo del frontend, rigenerato con
`python -m Betfair.stream.backtest.applica_bot --catalogo-ts` (verificato allineato anche dopo i merge su 16d6c67 e 1ac69d0).
Frontend: `npx tsc -p tsconfig.app.json --noEmit` 0 errori; `npx vitest run src/components/replay/ApplicaBotPanel.test.tsx
src/lib/applicaBot.test.ts` 30/30. `npx vitest run` intero e `npm run build`: NON eseguiti (una stringa in un file di dati).
Omega intera: `pytest Betfair/omega` 1566 passed, 2 skipped.

## 8. Decisioni per l'utente (comportamenti di PRODUZIONE che il banco ora mostra; nessuna strategia toccata)
- **P1 — Correct Score oltre i 3 gol per lato.** Lo scanner (`scanner.is_cs_candidate`, `CS_MAX_GOALS_SIDE = 3`) smette di seguire
  il CS quando una squadra ne segna 4, e il blocco resta nella riga col flusso fermo: Omega (V2 e V4) da li' NON valuta piu' la
  gamba 2T su quella partita (35760084: dal 63', 43 valutazioni V3 in meno). Proprio i risultati «Any Unquoted …» vivono li'.
  Proposta: valutare se tenere il CS sottoscritto per le partite seguite da Omega (decisione dello scanner, non di Omega).
- **P2 — Mercato uscito dalla sottoscrizione = bot fermo.** Un blocco CS/HT rimasto nella riga dopo che lo scanner smette di
  seguirlo (fine esposizione, fine finestra) rende fermo il verdetto del flusso MO+CS di Omega: niente decisioni finche' lo
  scanner non lo riprende (35797769 `esiti-ignoti`: dal 3' al 30'). E' l'ordine «mai ciechi» del 01/10 visto da un'altra parte.
  Proposta: lo scanner tolga dalla riga (o marchi «non seguito») il blocco di un mercato non piu' sottoscritto, oppure Omega
  ignori nel verdetto un mercato non seguito. Da decidere: tocca scanner/Omega, fuori dal mio perimetro.
- **P3 — Prima del 30' la gamba 1T V4 decide sul REST.** Il CS non e' nel feed prima del 30': ogni giro della 1T e' una
  `get_event_market_by_type` + `read_market` (35760084: 83 coppie). Se il volume REST conta, e' una scelta da fare.

## 9. NON fatto / NON verificato
- Tennis e DB: non servono a questo cantiere. Registrazioni tennis non presenti: nessun bot tennis toccato.
- Il PRIMA del coordinatore su `1ac69d0` non era sul remoto: confronto da rifare (§11).
- `DOPO1AC_35797769_tutti` fermato a meta' su ordine del coordinatore (§4.4); nessun replay sulla cima 31fa6433 (solo test).
- Mike e Safe girano col banco di sempre (finestre spente): per accenderle a Safe serve la fonte delle sue esposizioni
  (`safe_strategy_trades`), a Mike basta quella che ha (`_mike_followed_ids`); NON fatto (perimetro).
- Residui di RB-5 elencati in §5.3 non corretti.
- `npx vitest run` intero, `npm run build`: non eseguiti.
- Tempi: misurati su macchina carica e condivisa (vedi §10), non confrontabili con quelli del PC.

## 10. Tempi (secondi, `--worker 1`; carico fra parentesi, da `replay/tempi.log`)
| replay | PRIMA | DOPO |
|---|---|---|
| 35760084 apertura | 40 (14) | 40 (8) / 21-23 a carico 3 |
| 35797769 apertura | 176 (14) | 166 (8) |
| 35760084 tutti | 880 (18) / 441 su 16d6c67 a carico 4-5 | 674 (6-9) |
| 35797769 tutti | 3471 (14) | 1764 (2-4) |
Nessun rallentamento attribuibile alle modifiche: lo scanner riceve meno book (138.004 in meno su 35760084, 462-478 mila su
35797769) e la sottoscrizione costa una `relevant_market_ids` ogni 0,5 s di mercato. Il `tutti` della 35797769 resta sopra il
tetto (cantiere 11).

## 11. Comandi per il DOPO (dalla radice del worktree, `_live_raw` con le due partite, uno per macchina)
Elenco ESATTO da confrontare col PRIMA della sessione rif-omega (`AUDIT_2026-10-08/riferimenti_cloud/omega_*`):
```
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --worker 1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari apertura --worker 1
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti --worker 1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --trasporto canale --worker 1   # parita' paper/live
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,cap-stretto --worker 1                # deve restare identico
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari base,riavvio --worker 1               # deve restare identico
```
Atteso (misurato qui): righe diverse SOLO quelle di §4 (vedi `replay/per_scenario_*`, `FINALE_*`, `DOPO1AC_*`).
Prova della contaminazione sul codice di PARTENZA (facoltativa, ~3 min):
`python -m Betfair.stream.backtest.certifica omega 35797769 --scenari chiuso-fuori-app --worker 1` -> 1T '3 - 3' @80 al 1'
(dentro `tutti` lo stesso codice dava '3 - 2' @50 al 23').

Comandi completi per il PC:
```
python -m pytest Betfair/stream/tests/test_banco_scanner_reperti_rb_2026_10_08.py Betfair/omega/tests/test_banco_omega_reperti_rb_2026_10_08.py -q -p no:cacheprovider   # 23 passed
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --worker 1            # 467/2, nota chiusure con CORRECT_SCORE 17:54:16
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari paper --worker 1               # 467/2, lay '3 - 3' @300 won +5,00, canale_inviato x1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari apertura --trasporto canale --worker 1
python -m Betfair.stream.backtest.certifica omega 35760084 --scenari tutti --worker 1              # 20/20, 0 violazioni, 38/52 mai sollecitati
python -m Betfair.stream.backtest.certifica omega 35797769 --scenari tutti --worker 1              # 20/20, 0 violazioni, 29/52; chiuso-fuori-app 1T '3 - 3' @80 al 1'
python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base,cap-stretto --worker 1    # identico al PRIMA
python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari base,riavvio --worker 1   # identico al PRIMA
```
Confronto: `python AUDIT_2026-10-08/cantiere_7/strumenti/per_scenario.py PRIMA.txt DOPO.txt`.

## 12. File
- MODIFICATI: `Betfair/stream/backtest/banco_comune.py` (+92/-2), `Betfair/omega/tools/replay_registrazioni.py` (+188/-34),
  `frontend/src/lib/replayBotCatalogo.ts` (1 riga, generato).
- NUOVI: i due test (§7); `AUDIT_2026-10-08/cantiere_7/REFERTO.md`, `replay/*`, `strumenti/*` (sonde in sola lettura).

## Blocco per la cronostoria
```
### Cantiere 7 (delegato cloud, 08/10) — banco di Omega, RB-1..RB-5
- RB-1: il CLOSED non arrivava allo scanner perche' flumine lo passa solo a process_closed_market (Omega non l'aveva), non
  per la conflazione; ora OmegaCert.process_closed_market -> applica_book, terminale fuori conflazione e consegnato una volta.
- RB-2: finestre di sottoscrizione della produzione (Scanner.relevant_market_ids ogni 0,5 s, esposizioni di Omega,
  conferma solo dei sottoscritti), accese solo nel banco di Omega; Mike/Safe identici.
- RB-3: eta' del flusso in tempo di mercato. RB-4: paper con la porta del runner: 35760084 paper 467/2 = live.
- RB-5: elenco esplicito unico delle cache di processo azzerato fra scenari; trovato e provato _LEG_RETRY che cambiava le
  decisioni (35797769 chiuso-fuori-app/chiusura-abbinata-in-parte '3 - 2' al 23' -> '3 - 3' al 1').
- 35760084 apertura 467/2 invariato; tutti 20/20 su entrambe, 0 violazioni; ogni riga diversa spiegata nel referto.
- Test: 23 nuovi, 15 mutazioni tutte rosse; suite Betfair/ 10974 passed 0 failed.
- Decisioni per l'utente: P1 CS oltre 3 gol non seguito (Omega cieco sul 2T), P2 blocco non piu' sottoscritto = flusso
  fermo = bot fermo, P3 1T V4 su REST prima del 30'.
- Ripresa: confronto col PRIMA del coordinatore su 1ac69d0; residui RB-5 (§5.3); finestre per Safe/Mike.
```

## Verifica del coordinatore cloud (08/10)
- Diff riletto (banco: CLOSED via `process_closed_market` e finestre di sottoscrizione con la funzione di produzione, interruttore
  per istanza spento di serie; Omega: porta del runner per `paper`, orologio di mercato per i testi, cache azzerate fra scenari).
  `omega_service.py`/`omega_v3.py`/`omega_engine.py` NON toccati.
- Test nuovi 23/23 nel checkout integrato. MIE MUTAZIONI: cache storiche non azzerate fra scenari -> 5 rossi; orologio di sistema nei
  testi dell'eta' -> 1 rosso. Ripristino verificato.
- MIO REPLAY (`verifica_coordinatore_35760084.txt`): `apertura` OK 467/2 e `paper` OK 467/2 (prima 438/0): IDENTICI al delegato;
  la parita' paper/live di Omega sul banco e' dimostrata.
- Decisioni per l'utente (P1-P3 del referto): comportamenti di produzione che il banco ora mostra, nessuna strategia toccata.
