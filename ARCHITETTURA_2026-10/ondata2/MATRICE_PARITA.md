# MATRICE DI PARITA' CON I COMPETITOR (ondata 2, primo lavoro) - 10/10/2026

Principio dell'utente, vincolante (`AVANZAMENTO.md`, 10/10): «Tutto deve essere come i competitor! Voglio un prodotto
professionale!». Questa matrice e' il metro di accettazione di ogni tappa dell'ondata 2: una tappa e' chiusa solo se la sua
voce e' «uguale o meglio» del competitor migliore, PROVATO con la misura scritta nell'ultima colonna.

Autore: delegato (sola lettura del codice). Ramo `ondata2/matrice-parita` da `d073ddcb`. Nessun file di produzione toccato.

## 0. Metodo, fonti e limiti

- **Competitor**: le dichiarazioni vengono da `ARCHITETTURA_2026-10/02_COMPETITOR.md` (sezioni 1-2, sigle delle fonti nella
  sua sezione 9: `BA-PDF r.N` = riga del testo estratto dal manuale ufficiale di Bet Angel 2025; `CY-*` Cymatic; `GT-*` Geeks
  Toy; `FB-*` Fairbot; `BX-*` Bfexplorer; `TL-*` Traderline; `GR-*` Gruss). Non le ho rilette sui siti: **da questo ambiente
  i siti dei competitor non rispondono** (10/10, ore 08:39 UTC): `www.betangel.com` -> il proxy risponde 403 al CONNECT (anche
  con `curl`); `www.cymatic.co.uk`, `www.geekstoy.co.uk`, `fairbot.com` -> `getaddrinfo ENOTFOUND` da WebFetch. Le ricerche
  web (WebSearch) per completare le voci n.d. (Geeks Toy e streaming, refresh di Fairbot, drag-and-drop e «cancel all» di
  Bet Angel, API Monitor di Cymatic) non hanno restituito pagine dei produttori. Unico frammento nuovo: l'indice di una copia
  su Scribd della guida di Gruss Betting Assistant (https://www.scribd.com/document/694149845/User-Guide) elenca un
  «Price Streaming Indicator (PS)» e un «Actual Refresh (AR)»: *deduzione*, Gruss distingue prezzi in streaming da prezzi
  rinfrescati; la pagina NON e' stata letta (solo lo snippet del motore), quindi la voce resta n.d.
- **Oggi** = il codice del checkout a `d073ddcb`, letto di persona con `sed -n`/`grep -n` il 10/10. Ogni `file:riga` qui sotto
  e' stato riaperto. Dove una funzione non c'e' scrivo «non trovata» con i termini cercati e la cartella.
- **Nucleo** = `Betfair/nucleo/` (ondata 1, integrato, NON agganciato all'app).
- **Libreria**: flumine 2.13.11 e betfairlightweight 2.23.2 (pin in `requirements.txt:28-29`), sorgenti letti in
  `/usr/local/lib/python3.13/dist-packages/flumine/`.
- **Tappe**: quelle di `05_PIANO_DI_MIGRAZIONE.md` §2 (T1-T26). Dove nessuna tappa copre la voce ne propongo una nuova
  (sezione 3, sigla `TP-n`), da approvare col coordinatore (il piano non si rimette in discussione: le TP si AGGIUNGONO).
- **Misure L1-L19**: tabella di `04_ARCHITETTURA_OBIETTIVO.md` §7 (righe 885-904), riusate con lo stesso nome.
- Legenda GAP: **manca** (non c'e'), **parziale** (c'e' ma sotto il competitor migliore o solo in un caso), **uguale**,
  **meglio** (oltre cio' che i competitor dichiarano), **n.d.** (nessun competitor dichiara nulla: non e' un gap di parita').

## 1. La matrice

Colonne: Voce | Competitor migliore e cosa dichiara (fonte) | OGGI (file:riga) | NUCLEO ondata 1 (file:riga) | GAP | Tappa
dell'ondata 2 | Misura con cui si dichiara «uguale o meglio».

### 1.1 Dati e velocita'

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-01 | Stream dei prezzi su OGNI mercato seguito | Cymatic: streaming di serie (CY-POLL); Bet Angel streaming opzionale (BA-PDF r.8908-8916); Fairbot «Stream API mode» (FB-NEW) | Si', ma una connessione per processo: runner calcio `Betfair/stream/runner.py:2958-2960` (campi `config_stream.py:90-94`); tennis una capture per match seguito `tennis_live/tennis_runner.py:478-492`; scanner a shard `safe_strategy/stream.py:276-279` (180 mercati/connessione, `:83`); lo scanner ha il ripiego REST `poll_books` (01 A-078) | `GestoreFlussi` per profilo `nucleo/betfair/flusso.py:486`; mai oltre 200 per sottoscrizione `flusso.py:510`; profili con i valori di oggi `nucleo/betfair/profili.py:58,115-169` | parziale | T19 (decisione utente n.8: UN gestore dei flussi per l'app) | 100% dei mercati seguiti in stream, 0 mercati su REST salvo guasto (contatore nel monitor); caso peggiore live <= 10 connessioni; `MarketBook` identici campo per campo sulle 40 registrazioni (ombra di T19) |
| MP-02 | Refresh del ladder (20 ms) | Bet Angel: in streaming refresh fino a **20 ms**, «Update» = a ogni messaggio (BA-PDF r.9956-9966, r.1231-1236) | Canale locale ogni **200 ms** di serie: `config_stream.py:74` (`LIVE_LADDER_CANALE_MS`), `ladder_canale.py:60`; worker mai sotto 20 ms `ladder_canale.py:41-45`; DB `live_ladder` a 0,3 s dall'app (`desktop/ambiente_runner.js:69`), 2 s di serie (`config_stream.py:60`); tennis idem `tennis_runner.py:107-109`; UI dal canale `frontend/src/lib/localTransport.ts:126,418`, ripiego DB realtime `lib/live.ts:619-632` | Ladder a OGNI cambio, coalescenza 20 ms per mercato, DB in un thread suo: `nucleo/betfair/ladder.py:1-9,54`; payload e firma identici (`ladder.py:11-21`) | manca (10 volte piu' lento) | T6 (decisione utente n.12: massima velocita', 20 ms) | M1 (sezione 2): `rx -> pixel` p95 <= 20 ms e, a monitor acceso, nessun cambio di firma saltato a schermo oltre la coalescenza di 20 ms; CPU del processo misurata in ombra |
| MP-03 | Conflation | Cymatic: `conflateMs` impostabile, **0 ms** = ogni variazione subito (CY-STREAM) | runner calcio 0 (`config_stream.py:87`); stream ordini 0 (`config_stream.py:235`); scanner **1000 ms fisso** (`safe_strategy/stream.py:67`, nessun env); tennis non passato = default Betfair (`profili.py:137-138`) | `profili.py:17` («conflateMs e heartbeatMs restano quelli di oggi»), scanner 1000 `profili.py:152` | parziale (solo lo scanner, che alimenta Mike/Safe/Omega) | T19 + decisione U-01 (`05` riga 984: «1000 ms come oggi» finche' l'utente non decide, replay prima) | ladder e ordini a 0; scanner: solo con decisione U-01 e banco con impronta della strategia invariata |
| MP-04 | Ripresa dello stream (`initialClk`/`clk`) | nessun competitor la dichiara (02 §2); Betfair: `RESUB_DELTA` (B-STREAM) | dalla libreria: `frammenti_mercato.py:49,190`; scanner con resubscribe a caldo (01 A-076); flumine `OrderStream` con `@retry` (`flumine/streams/orderstream.py:19`) | ripresa con `initialClk/clk`, backoff 2-60 s azzerato solo dopo connessione rimasta su: `flusso.py:26-32`, `flusso_ordini_conto.py:55-60` | n.d. (nostro dichiarato e testato) | T19 | scenari di caduta del banco (resubscribe, frammento muto > 180 s, `status:503`, relogin con ordini vivi) con `MarketBook` identici e ripresa in `RESUB_DELTA` dove Betfair la concede (falsificazione: togliere `initialClk` -> rosso) |
| MP-05 | Stream degli ordini del CONTO | Geeks Toy legge le «External Bets» (gruppo di chiamate, GT-API); Bet Angel: scommesse spinte da Betfair (BA-PDF r.2137, 02 P-05) | uno stream ordini flumine PER PROCESSO: `runner.py:2250-2256` (LIVE), `:2268-2278` (PAPER, simulato), `:2312-2318` (paper affiancato); filtro di strategia assente (`flumine/config.py:8` `customer_strategy_ref = None`, `flumine/streams/orderstream.py:41-47`) MA flumine scarta gli ordini senza `customerOrderRef` (`flumine/order/process.py:39-40`) e quelli di strategie che il processo non ha (`process.py:101-114`): gli ordini dal sito e degli altri processi NON arrivano allo specchio | stream ordini del conto senza filtro, `include_overall_position=True`, sola lettura: `nucleo/betfair/flusso_ordini_conto.py:1-27`, classe `FlussoOrdiniContoBetfair` `:490` | parziale | T11 (parte A, aggancio) + T19; decisione utente n.13: SOSTITUISCE quelli di flumine, mai aggiunto | 1 sola connessione ordini per l'app (contatore `stream_avvii` del monitor); ordine piazzato dal sito Betfair visibile sul ladder; tempo `ocm rx -> ladder` come M1 |
| MP-06 | Mercati monitorabili (capacita') | Bet Angel «1000 mercati in streaming» (BA-PDF r.5281); Betfair 200 per sottoscrizione (B-STREAM) | 180 per connessione, shard fino a 10 (`safe_strategy/stream.py:35,83`); tennis 1 connessione per match (`tennis_runner.py:478-479`) | 180 di serie, mai > 200 (`flusso.py:12,510`) | parziale oggi, uguale con T19 (10 connessioni x 200 = 2.000) | T19 | mercati in stream senza ripiego REST col carico vero di una domenica (referto Salute 24 h) |
| MP-07 | Sessione unica e keepAlive (.it 20 min) | flumine: keepAlive ogni 1200 s (02 §4.2); competitor n.d. | keepAlive in piu' punti: `stream/auth.py:88-94` e gli altri di 02 P-07; login per processo (decisione utente n.1) | custode unico `nucleo/betfair/sessione.py:230` (`SessioneBetfair`), freno dei login `:104` | parziale | T5 | 1 login e 1 keepAlive per l'app (contatori `betfair_sessione` di `nucleo/betfair/salute.py`), 0 `INVALID_SESSION` in 24 h |
| MP-08 | Orologio sincronizzato col server | Betfair raccomanda NTP (B-ADDINFO); competitor n.d. | U-62 fatta sul PC (w32time attivo, `AVANZAMENTO.md` tabella, riga U-62); il codice dichiara lo scarto (`Betfair/stream/orologio.py`, 02 P-08) | - | uguale (dopo U-62) | T0A (referto) | scarto <= 100 ms (L19) nel referto Salute |

### 1.2 Ladder

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-09 | TUTTI gli ordini del conto sul ladder, con AUTORE | Geeks Toy: «External Bets» (GT-API); nessun competitor dichiara l'autore (bot/utente/sito) | Il ladder mostra solo i «tuoi» ordini dello specchio: `get_live_orders` (`frontend/src/lib/liveOrders.ts:530-536`) o push `order` del canale (`localTransport.ts:519-546`), colonne `my_lay`/`my_back` (`components/live/LadderView.tsx:9-12`); ordini del sito e di altri processi esclusi (vedi MP-05); colonna autore: **non trovata** (grep `author|autore|.source|origine` in `LadderView.tsx`: solo commenti alle righe 702, 2025, 2191) | libro ordini del conto con autore, abbinato, residuo, prezzo medio, stato: `nucleo/ordini/libro_conto.py:1-8,244`; attribuzione `nucleo/ordini/attribuzione.py:262` (`attribuisci_riferimenti`); comandi permessi per autore `libro_conto.py:844` (`comandi_ammessi`, «da confermare» = decisione utente n.6) | manca (sito/altri processi) | T11 + aggancio UI (TP-1) | 100% degli ordini EXECUTABLE del conto (confronto con `listCurrentOrders` a campione) sul ladder; 0 ordini senza autore salvo «da confermare»; ordine dal sito visibile entro M1 |
| MP-10 | P&L «se vince» per selezione su OGNI mercato | Bet Angel P&L locale in streaming (BA-PDF r.8932-8942); Traderline P&L in tempo reale (TL-EDU); Fairbot profitto per selezione (FB-HOME) | per selezione DA SOLA (se vince/se perde della selezione, dallo specchio posizioni): `GridView.tsx:589-596`, `TerminalPositionsRail.tsx:189-190`; nel ladder solo P&L per livello e cash-out (`LadderView.tsx:764-768,964`, `lib/ladderMath.ts:10-13`); P&L «se vince» del MERCATO solo nel replay col bot sovrapposto (`LadderView.tsx:128-132,888-889`, `lib/replayOperazioni.ts:353`); ordini fuori specchio non contati | P&L di mercato su TUTTI gli abbinati, per autore, prezzo medio, esposizione: `nucleo/ordini/pnl_mercato.py:1-8`; oggi solo mercati a vincitore unico (`pnl_mercato.py:26-37,81`) | parziale | inizio ondata 2: modifica W1-C2 (decisione utente n.5: tutti i mercati; quelli a piu' vincitori con l'indicazione «per selezione») + T11 + TP-1 | cifra uguale al centesimo (lorda) a `listMarketProfitAndLoss` di Betfair su N mercati veri; aggiornata a ogni `ocm` (tempo come M1) |
| MP-11 | Volume scambiato per prezzo | Fairbot volume per prezzo (FB-HOME); Bet Angel, Geeks Toy ladder a profondita' completa | `EX_TRADED` (`config_stream.py:92`), colonna `trd` (`LadderView.tsx:11,329`) | stesso payload (`ladder.py:11-21`) | uguale | T6 | firma del payload identica (ombra di T6) |
| MP-12 | Ultimo prezzo scambiato (LTP) | tutti | `EX_LTP` (`config_stream.py:94`); evidenziato e lampeggiante per direzione `LadderView.tsx:552-578,1035-1047`; auto-centratura sull'LTP `:532,819-820` | idem | uguale | T6 | idem |
| MP-13 | WOM (weight of money) | Fairbot WoM e indicatori (FB-HOME) | `compute_wom` `runner.py:596-641`; barra `LadderView.tsx:375-385`; WOM esteso a tutto il book e delta del flusso `DepthPanel.tsx:1-10` | `compute_wom` gemello unico (`ladder.py:12-14`) | meglio (WOM esteso + delta) | T6 | firma identica |
| MP-14 | Posizione in coda (PIQ/EPIQ) | Cymatic «primi a mostrarla» (CY-FEAT); Bet Angel EPIQ (BA-PDF r.9082-9084) | stima per livello `piqAhead` (`lib/ladderMath.ts:22`) raffinata col volume scambiato `refineQueue` (`LadderView.tsx:443-451,966-974`); solo sui nostri ordini dello specchio | nessuna (grep `piq` in `Betfair/nucleo`: 0 righe) | uguale (stima, come EPIQ) | T11 (ordini del conto -> PIQ anche sugli ordini esterni) | errore della stima contro la coda del simulatore di flumine (`flumine/simulation/simulatedorder.py:235`) sulle registrazioni del banco |
| MP-15 | Colonne personalizzabili | Cymatic «layout illimitati» (02 L-09); Bet Angel finestre staccabili (BA-PDF r.1285-1286) | mostra/nascondi e riordina per sport: `lib/ladderConfig.ts:54,167,216,228`; popout `pages/LadderPopout.tsx` | - | uguale | T18 (conserva) | fotografie identiche (`fotografia.test.tsx`) |
| MP-16 | One-click | tutti (BA, GT, CY, FB) | conferma di serie, «1-click» armato `LadderView.tsx:1673,2111` (banner rosso LIVE / ambra PAPER, `:26-28`); dal ladder al runner sul canale locale `localTransport.ts:439-455` -> `local_channel.py:1-17` (ripiego coda DB `liveOrders.ts:125-160`) | porta unica `nucleo/ordini/porta.py:1-30` | uguale (funzione); latenza da misurare | T10 | M2 (sezione 2): clic -> `placeOrders` inviato p95 <= 20 ms sul canale; 0 chiamate al cloud nel percorso |
| MP-17 | Drag-and-drop degli ordini | Fairbot drag&drop (FB-HOME) | trascinamento dei tuoi ordini `LadderView.tsx:987-997`, `onMoveOrder` `:2191-2200`; implementato come cancel POI place (`:2023-2026`: «MAI un singolo replaceOrders»), persistenza dell'ordine trascinato `:701-707` | la porta conosce `replace` (`porta.py:570`) | uguale (funzione); scelta prudente: 2 transazioni e coda persa | T10 | ordine spostato senza duplicati (banco); tempo clic -> nuovo ordine accettato (M2) |
| MP-18 | Tasti rapidi | Cymatic «rapid keyboard betting» (CY-FEAT); Geeks Toy Shortcut Key Manager (GT-MAN) | `DEFAULT_KEYBINDINGS` `lib/workspace.ts:201-216` (B/L/C/G/X, frecce, +/-, Spazio, PagSu/PagGiu, Esc = kill-switch), `resolveHotkey` `:239`; macro «servants» richiamate coi tasti 1-9 `lib/servants.ts:1-30` | - | uguale (rimappatura dall'utente: non verificata nella UI) | T18 (conserva) | test dei tasti invariati |
| MP-19 | Bet delay a schermo | competitor n.d.; Betfair `betDelay` nella MarketDefinition (02 §3.4) | **non trovato** a schermo (grep `bet_delay|betDelay` in `frontend/src/components/live/*.tsx` e `lib/live.ts`: 0 righe); letto da Mike (02 P-10) | - | n.d. (miglioria) | TP-1 | campo nel payload del ladder e a schermo |
| MP-20 | Contatore transazioni/ora a schermo | Bet Angel: contatore in basso (BA-PDF r.9905-9913) | tetto per PROCESSO `config_stream.py:256-262` (1000/h); contato dalla Salute (`monitor/sonde.py:452-462`, obiettivo 5000 `frontend/src/lib/salute.ts:23`) ma solo a monitor acceso e non sul ladder | contatore UNO PER CONTO `nucleo/ordini/controlli.py:5-17` | parziale | T10 + TP-1 | contatore per conto a schermo, uguale al conteggio Betfair (02 §3.2 S-TXN) |

### 1.3 Ordini

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-21 | Fill or Kill | Bet Angel e Geeks Toy: timer SOFTWARE (BA-PDF r.1897-1925; GT-STAKING); Betfair nativo `FILL_OR_KILL` (B-PLACE) | software `fok_ttl_sec` `live_order_worker.py:1480-1484,1532-1569`; nativo `live_order_build.py:111,771-772`; nel ladder `LadderView.tsx:1257,1265` solo calcio (`supportsFok` `:174`); **tennis senza** (`components/tennis/TennisLadderColumn.tsx:59-78`: nessun `supportsFok`) | `time_in_force` nel contratto `nucleo/ordini/contratto.py:46` | uguale calcio, manca tennis | T10 (+T21 tennis) | ritardo fra scadenza del timer e `cancelOrders` p95 <= 20 ms (oggi legato al giro del worker, `live_order_worker.py:4270`); FOK nativo escluso dagli ordini PASSIVE (02 §3.4) |
| MP-22 | Tick offset | Bet Angel offset a tick/% e offset a batch (BA-PDF r.1895, r.2151-2162) | `offset_order` `stream/trading/risk_engine.py:189-266`; armato al clic `LadderView.tsx:1254-1268`; regole sulla tabella cloud `betfair_live_risk_rules` (`liveOrders.ts:435-512`) ANCHE col canale locale (`localTransport.ts:554`: «risk rules RESTANO su path DB»); offset a batch: non trovato (02 O-03); tennis: nessun `armRule` (`TennisLadderColumn.tsx:59-78`) | nessuno (grep `offset|risk` in `Betfair/nucleo/ordini`: solo testi del contratto) | parziale | TP-2 (risk engine locale a evento; decisione U-24) | offset sul book entro p95 <= 20 ms dall'`ocm` del fill; 0 letture del cloud nel percorso; parita' delle regole sul banco |
| MP-23 | Stop loss | Bet Angel, Geeks Toy, Cymatic (02 §2) | `stop_trigger_price`/`stop_should_fire`/`stop_close_order` `risk_engine.py:268-352`; giro del worker 0,15 s dall'app (`desktop/ambiente_runner.js:75`), 1,0 s di serie (`config_stream.py:311`); regole rilette dal DB a ogni giro con regole armate (`risk_engine_worker.py:1155-1180`); «se il processo cade NON esistono» (`risk_engine.py:21-23`) | nessuno | parziale | TP-2 (U-24) | stop valutato a OGNI book (non a giro), invio p95 <= 20 ms dal book che lo innesca (L10); banco: stessi scatti dello stop a ciclo o migliori |
| MP-24 | Trailing stop | Bet Angel, Cymatic, Bfexplorer (02 §2) | `update_trailing_extreme`/`trailing_stop_price` `risk_engine.py:355-401`, valutazione `:525-545` | nessuno | parziale (stessa cadenza di MP-23) | TP-2 | come MP-23 |
| MP-25 | OCO / bracket | Geeks Toy OCO con riduzione dello stop all'uscita parziale (GT-OCO) | regola `bracket` (`liveOrders.ts:350-354`), `on_fill` (`:365`); caso parziale: da verificare (02 O-08) | nessuno | parziale | TP-2 | scenario «uscita parziale» sul banco: lo stop si riduce della parte uscita |
| MP-26 | Greening / cash-out per selezione | Bet Angel, Cymatic, Fairbot (FB-HOME: ripartizione libera del profitto) | `sendGreenup` `liveOrders.ts:202`; calcolo `trading/greenup.py:118`; parziale (slider) `LadderView.tsx:849-874`; «greening column» a un prezzo `:86-96`; completo con annullo dei non abbinati (`liveOrders.ts:175-200`); tennis si' (`TennisLadderColumn.tsx:66-77`) | formula `lockedPnlAt` ripresa e testata `pnl_mercato.py:19-20` | uguale; ripartizione libera fra esiti: non trovata | T10 | P&L bloccato uguale al previsto al centesimo; M2 sul comando |
| MP-27 | Greening / cash-out per MERCATO | Geeks Toy hedge del mercato con un clic (GT-STATUS); Fairbot cash-out mercato (FB-HOME) | `sendCashoutAll` (anche «pareggiato» su ogni esito) `liveOrders.ts:307-325`; per EVENTO `:330-345`; `MarketWatch.tsx:1-7` (cash-out evento solo calcio) | - | meglio calcio (anche evento), parziale tennis | T10 (+T21) | come MP-26 |
| MP-28 | Dutching / bookmaking | Bet Angel, Geeks Toy, Fairbot, Gruss (02 §2) | `trading/dutching.py:81,119,147,184`; `DutchingPanel.tsx:331,370,609` (lay = bookmaking: **correzione** di 02 O-06, che lo dava assente) | - | uguale | T10 | anteprima = esito sul banco al centesimo |
| MP-29 | Keep / Take SP in-play | Geeks Toy Cancel/Keep/Take SP anche per ordine (GT-LADDER); Bet Angel (BA-PDF r.1784-1800) | `PERSISTENCE_OPTIONS` `LadderView.tsx:186-191`; persistenza conservata nel trascinamento `:701-707` | `Persistenza` nel contratto `contratto.py:19,45` | uguale | T10 | stessa `persistenceType` su Betfair (specchio vs conto) |
| MP-30 | Persistenza oltre un crash (ordini, stop, regole) | Betfair Heartbeat API: cancella i LIMIT se manca il battito (B-HBAPI); Bet Angel: gli stop non passano dal pre-gara all'in-play (BA-PDF r.2051) | diario write-ahead con fsync prima del place (01 C-055; misurato in `motore_ordini.py:1477`); regole armate salvate nel DB cloud (`liveOrders.ts:435`) con comportamento all'in-play keep/cancel/rebaseline (`liveOrders.ts:368`); Heartbeat API **non trovata** (grep `HeartbeatAPING|exchange/heartbeat` in `Betfair/`: 0 righe) | dedup per `ref` che sopravvive al riavvio `porta.py:12-21`; archivio locale (W1-G1) | parziale (meglio sul diario, manca il battito) | T24 (U-17) - proposto anticipo in TP-3 | scenario «processo ucciso con ordini e stop armati»: 0 ordini doppi, regole riprese al riavvio; con U-17, LIMIT cancellati da Betfair entro il timeout |
| MP-31 | Ordini a «punta minima» .it | competitor n.d.; flumine NON conosce le regole .it (02 §4.2) | `trading/minimi_it.py:45-56` (1,00 EUR, passo 0,50, pavimento 0,50); place-and-trim `trading/submin.py:299,444` | `nucleo/ordini/minimi.py:173` (`verdetto_porta`), `:221` (`verdetto_desktop`: rifiuto, decisione utente n.3) | meglio | T10 | 0 `INVALID_BET_SIZE` in esercizio; parita' delle 5 definizioni di oggi con quella unica (test di T10). Nota: `minimi_it.py:30` cita la «Nota informativa betfair.it» per 1,00 EUR, 02 §3.4 riporta 2,00 EUR dalla documentazione sviluppatori: divergenza documentale da tenere presente, non toccata qui |
| MP-32 | Annulla tutti | Bfexplorer: chiusura di posizione singola, mercato, tutte (BX-SEARCH); Betfair `cancelOrders` senza istruzioni = tutti gli ordini del mercato (B-PLACE, pagina cancelOrders) | per LATO della selezione: clic sull'intestazione `LadderView.tsx:907-920`; eseguito come N `cancel` in sequenza (`:2007-2016`); macro `cancel_side both` `servants.ts:20`; annullo dei non abbinati dentro il cash-out completo (`liveOrders.ts:175-200`); annulla tutto il MERCATO o tutti i mercati: **non trovato** (grep `annulla tutt|cancella tutt|cancel all` in `frontend/src/components` e `pages`; azioni del canale `live_order_worker.py:3645-3647` senza `cancel_all`); il kill-switch NON annulla: blocca solo le aperture (`live_order_worker.py:3961`) | nessuna azione «annulla tutto» (porta: `place|cancel|replace`, `porta.py:570`) | manca | TP-1 (UI) + T10 (azione della porta) | UNA chiamata `cancelOrders` per mercato; 0 ordini residui verificati sullo stream ordini del conto; tempo clic -> conferma (M2) |
| MP-33 | Scala di ordini, stop-entry, chase | Bet Angel offset a batch (BA-PDF r.2151-2162); Bfexplorer drip feeding, «essere primi in coda» (BX-SEARCH) | scala `LadderView.tsx:1258,1280`; `stop_entry` e `chase` `liveOrders.ts:355-358` | nessuno | uguale | TP-2 | come MP-22 |
| MP-34 | Repeat on Success | Fairbot (FB-HOME) | **non trovata** (02 O-09: grep `ripeti|repeat` in `frontend/src`) | - | manca (bassa priorita') | decisione utente (nuova funzione) | - |
| MP-35 | Stake in responsabilita' / preset / Kelly | Geeks Toy stake per liquidita' o % del bank (GT-STAKING) | modo `stake`/`liability` `LadderView.tsx:487,1065,1226`; preset e passi (`lib/ladderMath` `stepStake`/`nextPreset`, import `LadderView.tsx:41`); suggerimento Kelly a un clic `:781-797`; stake in % del saldo: non cercato a fondo (grep `bankPct|% del saldo` in `LadderView.tsx`: 0) | - | uguale (% del bank: non verificato) | T18 (conserva) | - |
| MP-36 | Nessun DB remoto nel percorso decisione -> ordine | i competitor desktop non hanno DB remoto (02 N-03) | ladder -> runner sul canale locale (`local_channel.py:1-12`), MA: regole di rischio sul cloud (MP-22), kill-switch e settings letti dal cloud (`trading/controls.py:81-143`), ripiego ordini sulla coda del cloud (`liveOrders.ts:120-160`), bot via coda (p50 492 ms, p99 26,6 s in paper: 07 §0 riga 3b) | porta + archivio locale (`porta.py:12-21`, `nucleo/dati/archivio.py`) | parziale | T10, T14, T22, TP-2 | 0 richieste al cloud fra decisione e `placeOrders` (contatore `db_ms` del monitor nel thread degli ordini = 0) |

### 1.4 Automazione

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-37 | Regole e bot | Bet Angel Automation/Servants/Guardian, «centinaia di modelli» (BA-HOME, BA-PRO); Bfexplorer > 30 trigger (BX-SDK); Fairbot Advanced Automation (FB-NEW) | bot in codice (Mike, Omega, Safe, scalper, tennis) certificati sul banco (`backtest/certifica.py:1-12`), parametri editabili (01 E3-028); macro utente a vocabolario fisso, 9 macro x 6 passi (`lib/servants.ts:1-30`); editor generico di regole: **non trovato** (02 A-01) | runtime comune: tappa T12 (non in ondata 1) | parziale per scelta (strategie intoccabili) | T12, T15-T21; editor = decisione utente nuova | bot: certificazione sul banco; editor: n/a finche' l'utente non lo chiede |
| MP-38 | API locale per il codice | Bet Angel API JSON su porta locale (BA-PDF r.9749-9760) | canale 127.0.0.1 con token, protocollo `order`/`snapshot` e `/comando/<attore>`: `local_channel.py:1-17,143-166` | contratto della porta `nucleo/ordini/contratto.py`, `porta.py:1-30` | parziale (non documentata come API) | T10 (+ documento del contratto) | contratto pubblicato + test di contratto verdi |
| MP-39 | Excel | Bet Angel, Cymatic, Gruss (02 §2) | **non trovata** (grep `excel|xlsx|openpyxl` in `Betfair/` e `frontend/src`: solo commenti, es. `lib/marketDelays.ts:2`, `safe_strategy/engine.py`) | - | manca (nessun requisito dell'utente) | nessuna (decisione utente) | - |

### 1.5 Rischio e sicurezza

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-40 | Monitor dell'API con PAUSA automatica del trading | Cymatic API Monitor: round-trip a schermo, avviso a schermo ed e-mail, **sospende il trading** oltre soglia (3500 ms in polling, timeout 30.000) (CY-APIREF, CY-FEAT); Geeks Toy soglia 500-2000 ms (GT-STATUS) | la Salute MISURA (REST per metodo `monitor/sonde.py:368-383`, place/cancel di flumine `:429-462`) ma non agisce, ed e' accesa solo con `MONITOR_SALUTE=1` (`sonde.py:59-61`); banner «stream muto» `FlussoStreamBanner.tsx:1-4`; a stream muto le protezioni usano i prezzi di riserva o non agiscono (`live_order_worker.py:1731-1741`); pausa per latenza: **non trovata** | contatori REST p50/p99 `nucleo/betfair/salute.py:1-12`; eta' dell'ultimo messaggio per connessione `flusso.py:607-618` | manca | TP-3 (guardia di latenza nella porta) | latenza iniettata oltre soglia -> aperture bloccate entro 1 s, chiusure ammesse, avviso a schermo; falsificazione: guardia tolta -> rosso |
| MP-41 | Avvisi | Geeks Toy Audio Alerts Manager (GT-MAN); Cymatic e-mail (CY-FEAT) | banner `LiveAlertBanner.tsx:1-6` (tabella `live_alerts`), Telegram al crash `stream/watchdog.py:26`; allarmi sonori **non trovati** (grep `new Audio|AudioContext|beep|.play()` in `frontend/src`: 0) | - | parziale | TP-1 (UI) | avviso sonoro + visivo entro 1 s dall'evento |
| MP-42 | Limiti di esposizione | flumine `StrategyExposure` (02 §4.2); Geeks Toy stake % del bank (GT-STAKING) | per selezione e ordini/min `trading/controls.py:147-153`; per evento e campionato `:367-372`; stake massimo opzionale `config_stream.py:241-251`; stop giornaliero `trading/daily_pnl.py:1-15`; tetto transazioni per processo `config_stream.py:256-262` | contatore transazioni per CONTO `controlli.py:5-17`; freni della porta `controlli.py:18-24` | meglio | T10 | test di contratto con somma su piu' attori (05 T10, revisione critica) |
| MP-43 | Kill-switch | competitor: non dichiarato come tale; Cymatic sospende il trading (CY-FEAT) | tasto Esc `workspace.ts:215`; `setKillSwitch` `liveOrders.ts:704`; worker: env + DB (`live_order_worker.py:454-465,581-582`), blocca le APERTURE, mai le uscite (`:3961`); letto dal cloud con cache ~2 s (`trading/controls.py:107-143`) | kill-switch nei freni della porta, iniettato (`controlli.py:20-24`) | uguale; dipende dal cloud | T22 | dal clic al blocco <= 1 s anche a cloud giu' (comando locale, G §4.3 T05 in 05 T22) |

### 1.6 Prova e analisi

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-44 | Practice / paper con matching realistico | Bet Angel: matching LOCALE, simula il cross-matching, Take SP e Keep (BA-PDF r.816-830) | paper nello STESSO processo e stream del live (`runner.py:2263-2280`, `client_paper_affiancato.py:16-25`); latenza simulata 120 ms (`config_stream.py:238`) + bet delay (`flumine/execution/simulatedexecution.py:36`); coda stimata (`flumine/simulation/simulatedorder.py:235`); tennis 600 ms (01 A-065) | sorgente paper del libro ordini `libro_conto.py:14-17,86` | meglio (bet delay e coda; regola paper = live) | T10 (ombra paper/banco), T15+ | stessa sequenza di `EventoOrdine` su `EsecutorePaper` e `EsecutoreBanco` (05 T10) |
| MP-45 | Replay storico | Gruss: Market Replay degli ultimi 5 anni, a pagamento (GR-PAGE) | banco con codice di produzione `backtest/certifica.py:1-12`; `pages/MatchReplay.tsx:1-6`, `pages/TennisReplay.tsx`; bot sovrapposto al ladder del replay `LadderView.tsx:113-139`; profondita' = partite registrate da noi (07 §5.3: 67 partite) | - | meglio per la certificazione; parziale per profondita' storica | T23 | tempo di certificazione <= 300 s (L14); storico Betfair (dati PRO): decisione utente |
| MP-46 | Storico delle operazioni e P&L | Cymatic accounting (CY-FEAT) | `pages/TradeJournal.tsx:1-6`, `pages/LivePnl.tsx:1-8`, `fetchLiveSettled` `liveOrders.ts:789` | archivio locale (W1-G1) | uguale | T13, T14, T18 | P&L di giornata uguale a `listClearedOrders` al centesimo |
| MP-47 | Grafici dei prezzi | Bet Angel grafici avanzati in streaming (BA-PDF r.1526); Cymatic trendline magnetiche; Fairbot candele, RSI, Stochastic (FB-HOME) | candele LTP, volume, VWAP `SelectionChartPanel.tsx:1-10`, campionati SOLO da quando il pannello e' aperto (`:4-5`); mini-chart `MiniPriceChart.tsx`, `lib/ladderChart.ts:1-5`; indicatori/trendline: non trovati (02 L-05) | - | parziale | TP-1 (storia della giornata dal recorder) | grafico con la storia dall'apertura del mercato; indicatori se l'utente li chiede |

### 1.7 Multi-mercato

| # | Voce | Competitor migliore (fonte) | OGGI | NUCLEO | GAP | Tappa | Misura «uguale o meglio» |
|---|---|---|---|---|---|---|---|
| MP-48 | Griglia di piu' mercati | Bet Angel Guardian, «regole su 50 mercati al secondo a 20 ms» (BA-PDF r.4732-4734); Fairbot Market Watch List (FB-HOME) | fino a **8** ladder affiancati `pages/MultiLadder.tsx:1-7`, `lib/multiLadder.ts:21`; griglia one-click `GridView.tsx:1-8`; Market Watch multi-evento `pages/MarketWatch.tsx:1-7` | ladder a ogni cambio per tutti i mercati del gestore (`ladder.py`) | parziale (8 contro Guardian) | T6 + T18 | N ladder aperti senza perdere cadenza (M1 con 8 e con 20 mercati), CPU nel referto |
| MP-49 | Lista dei mercati seguiti | Fairbot watch list (FB-HOME) | `get_live_follows` `lib/live.ts:37`, `segui_live_apri_partita` `:51`; pagina `pages/SeguiLive.tsx` | gestore dei flussi (`flusso.py:486`) | uguale | T19 | - |
| MP-50 | Auto-follow | competitor n.d. | il runner segue da solo i mercati su cui i bot mandano ordini, senza ricostruire flumine: `stream/auto_follow.py:1-25` | gestore dei flussi con risottoscrizione (`flusso.py:322`, `risottoscrivi`) | meglio | T19 | ordine di un bot su mercato nuovo partito entro `MOTORE_AGGANCIO_MAX_MS` (scenario R10 del banco) |
| MP-51 | Parita' calcio/tennis sul ladder | (requisito nostro: i competitor non distinguono gli sport) | ladder tennis senza regole di rischio ne' FOK (`TennisLadderColumn.tsx:59-78`); cash-out evento solo calcio (`MarketWatch.tsx:3-5`) | - | parziale | T21 + TP-2 | stesse voci MP-21..MP-27 verdi anche sul tennis |

Totale: **51 voci**.

## 2. Le due misure di riferimento

I competitor non pubblicano latenze misurate (02 §2: solo «20 ms» di refresh di Bet Angel, «0 ms» di conflation di Cymatic,
150-200 ms di polling). Le due misure sotto sono il nostro metro, con la STESSA definizione per ogni tappa.

### M1 - messaggio Betfair -> ladder a schermo

Tratti (L1, L3, L4 di 04 §7) e cosa li misura oggi:

| Tratto | Orologi | Misurato oggi? | Dove |
|---|---|---|---|
| a. `pt` di Betfair -> arrivo nel processo (`rx`) | Betfair contro PC: include lo scarto dell'orologio (U-62) | SI' a monitor acceso, calcio e scanner: `feed_rx_pt_ms.<sorgente>` (`monitor/sonde.py:239-266`, aggancio `stream/raw_listener.py:316`, `safe_strategy/stream.py:156`) | referto `monitor/referto.py:558` (L1) |
| b. arrivo -> ladder pubblicato sul canale | oggi misurato come `ts_pub_ms - pt` (ANCORA contro l'orologio di Betfair) | SI' a monitor acceso, SOLO calcio: `marca_ladder` `sonde.py:198-216`, aggancio `runner.py:750`; tennis: aggancio **non trovato** (grep `marca_ladder` in `tennis_live/`: 0); nucleo `ladder.py`: nessun aggancio (grep `ts_pub_ms|_mon|monitor`: 0) | referto `referto.py:559` (L3) |
| c. canale -> pagina (arrivo del push nel renderer) | stesso PC | **NO**: la UI non legge `ts_pub_ms` (grep `ts_pub_ms` in `frontend/src/lib`: 0) | - |
| d. arrivo nel renderer -> pixel (commit React + frame) | stesso PC | **NO** (nessun `performance.now`/`requestAnimationFrame` in `LadderView.tsx`/`localTransport.ts`; grep: solo `useControlRoom.ts`, `lib/tennis.ts`) | - |

Metodo proposto (TP-1, da fare PRIMA di dichiarare chiusa T6):
1. il processo mette nel payload del ladder anche `rx_ms` (arrivo del messaggio che ha prodotto il book, stesso orologio del PC)
   accanto a `ts_pub_ms`, a monitor acceso, come campo additivo (regola di T0A: nessuno lo legge per decidere);
2. la UI registra `t_arrivo` (`performance.timeOrigin + performance.now()`) all'arrivo del push e `t_pixel` nel primo
   `requestAnimationFrame` dopo il commit della riga; Electron e Python girano sulla STESSA macchina e leggono lo stesso orologio
   di sistema, quindi `t_pixel - rx_ms` non dipende dallo scarto con Betfair;
3. istogramma a secchi fissi come `monitor/registro.py:40` (`Istogramma`), riassunto p50/p95/p99/max ogni 30 s inviato al
   processo e scritto nella riga di `monitor_metrics`;
4. separatamente, il tratto a. con lo scarto dichiarato (L19 <= 100 ms dopo U-62);
5. criterio di parita' con Bet Angel: `rx -> pixel` p95 <= **20 ms** e intervallo fra due aggiornamenti a schermo dello stesso
   mercato pari a quello dei messaggi (coalescenza massima 20 ms), misurato con 1, 8 e 20 ladder aperti.

### M2 - decisione -> risposta di `placeOrders`

Tratti (L6, L6b, L7 di 04 §7) e cosa li misura oggi:

| Tratto | Misurato oggi? | Dove |
|---|---|---|
| decisione del bot -> invio | SOLO Omega e Safe marcano `emesso_ms` (`omega/omega_service.py:3596`, `safe_strategy/execution.py:1816`; grep `marca_emesso` in `Betfair/`: nessun altro servizio); Mike, scalper, tennis: **no**; clic del desktop: **no** (il comando porta solo `client_ref`, `localTransport.ts:443-447`) | `stream/tempi_ordine.py:22-24,72` (`decisione_ms`) |
| invio -> presa del worker (coda del canale) | SI' a monitor acceso: `canale_coda_ms` (`sonde.py:183-195`, aggancio `local_channel.py:453`) | referto L6 |
| presa -> `place_order` | SI' (`interno_ms`, monotonic), con `LIVE_TEMPI_ORDINE` acceso di serie (`tempi_ordine.py:47,64`) | `tempi_ordine.py:25-31`; lettore `stream/tools/leggi_tempi_ordine.py` |
| diario write-ahead (fsync) | SI' a monitor acceso: `diario_fsync_ms` (`motore_ordini.py:1477`) | referto L6b |
| `placeOrders` -> risposta di Betfair | SI' a monitor acceso, solo Betfair vero: `betfair_place_ms` dal log di `flumine.execution` (`sonde.py:429-456`) | referto L7 (`referto.py:562`) |
| risposta -> primo abbinamento | SI' (`abbinato_ms`, `tempi_ordine.py:31-34`) | - |
| porta del nucleo | **NO**: nessun aggancio in `nucleo/ordini/porta.py` (grep `perf_counter|tratto|_mon`: 0); la latenza p95 0,96 ms di W1-C1 e' di laboratorio (`AVANZAMENTO.md`, riga W1-C1) | - |

Numeri di oggi gia' scritti: coda DB paper p50 492 / p95 2.481 / p99 26.636 ms (07 §0 riga 3b); canale 84-194 ms (n=3, 04 §7 L6);
comando -> place sul PC scarico p95 1,92-3,12 ms (`AVANZAMENTO.md`, registro 09/10 22:10); `placeOrders` vero: non misurabile
(1 richiesta live in tutta la storia, 04 §7 L7).

Metodo proposto: (1) `emesso_ms` anche per Mike, scalper, tennis e per il CLIC del desktop (istante del clic nel comando,
campo additivo); (2) la porta del nucleo emette gli stessi tratti nel registro della Salute; (3) 30 ordini paper con l'app
accesa (gia' previsto in T0A) e, su decisione dell'utente, ordini live minimi per L7. Criterio: clic/decisione -> `placeOrders`
INVIATO p95 <= 20 ms sul canale (stesso ordine del refresh di Bet Angel), 0 rete verso il cloud nel percorso; la risposta di
Betfair (L7) si dichiara, non si confronta (nessun competitor la pubblica).

### Cosa misura gia' la Salute (T0A) e cosa manca, in sintesi

- Misura (a monitor acceso, `MONITOR_SALUTE=1`, oggi SPENTO su master: `AVANZAMENTO.md` riga T0A): eta' del messaggio
  all'arrivo (calcio, scanner), `pt -> ladder pubblicato` (solo calcio), coda del canale, fsync del diario, place/cancel/replace
  di Betfair, REST per metodo, transazioni, connessioni disponibili, CPU/RAM, richieste al cloud (`sonde.py`, `processo.py`).
- Manca: canale -> pagina e pagina -> pixel (M1 c, d); il tennis per il ladder; la decisione di Mike/scalper/tennis e il clic del
  desktop (M2); qualunque aggancio nel nucleo (`ladder.py`, `porta.py`); qualunque AZIONE sulle misure (MP-40: pausa automatica).

## 3. Tappe nuove proposte (si aggiungono al piano, non lo cambiano)

- **TP-1 - Ladder professionale a schermo** (dopo T6 e T11): aggancio del libro ordini del conto al ladder (tutti gli ordini, autore,
  «se vince» di mercato), annulla tutto mercato/tutti i mercati, bet delay, contatore transazioni per conto, allarmi sonori, storia
  del grafico dalla registrazione, marche M1 c-d nella UI. Voci: MP-09, MP-10, MP-19, MP-20, MP-32, MP-41, MP-47.
- **TP-2 - Risk engine locale a evento** (dopo T10; decisione U-24): offset, stop, trailing, bracket, chase, stop-entry valutati a ogni
  book e a ogni `ocm`, regole nell'archivio locale (il cloud solo copia), stessi comandi per il tennis. Voci: MP-22..MP-25, MP-33,
  MP-36, MP-51.
- **TP-3 - Guardia di latenza e battito** (dopo T10 e T19): soglie di latenza REST/stream che sospendono le APERTURE (le chiusure
  passano), avviso a schermo; Heartbeat API in ombra con timeout lunghissimo anticipando U-17 di T24. Voci: MP-30, MP-40.

## 4. PRIORITA' (valore per l'utente: trading manuale professionale sul ladder + bot)

Stima: S <= 2 giorni, M 3-5 giorni, L > 5 giorni (codice + test + ombra; la verifica del PC e' a parte).

| # | GAP | Voci | Perche' prima | Tappa | Stima |
|---|---|---|---|---|---|
| 1 | Tutti gli ordini del conto sul ladder, con autore e P&L «se vince» di mercato | MP-09, MP-10, MP-05 | e' la priorita' dichiarata dall'utente («ogni ordine, mio o dei bot, da app o dal sito»); il nucleo e' pronto, manca l'aggancio e il «se vince» su tutti i mercati (decisione n.5) | W1-C2 (modifica), T11, TP-1 | M |
| 2 | Ladder a 20 ms (oggi 200 ms) | MP-02, MP-11..MP-13 | il refresh e' l'unico numero pubblico di Bet Angel; il nucleo (`ladder.py`) lo fa gia' | T6 | S-M |
| 3 | Le due misure di riferimento complete (M1 c-d, M2 per tutti gli attori e per il clic) | sezione 2 | senza, nessuna tappa puo' dirsi «uguale o meglio» PROVATO | TP-1 (marche) + T0A | S |
| 4 | Stop, trailing, offset locali e a evento (oggi giro 0,15-1 s e regole sul cloud; tennis senza) | MP-22..MP-25, MP-33, MP-51 | e' la protezione dei soldi sul ladder; oggi un'operazione manuale con stop dipende dal cloud | TP-2 (U-24) | L |
| 5 | Annulla tutto (mercato, tutti i mercati) in una chiamata | MP-32 | strumento base di ogni ladder professionale; oggi N annulli in sequenza per lato | TP-1 + T10 | S |
| 6 | Monitor dell'API con pausa automatica delle aperture | MP-40 | Cymatic lo fa; noi misuriamo ma non agiamo | TP-3 | M |
| 7 | Un solo stream ordini e un gestore dei flussi unico | MP-01, MP-05, MP-06 | decisioni n.8 e n.13; base di 1 e di 4 | T11 (parte A), T19 | L |
| 8 | Nessun DB cloud nel percorso degli ordini (kill-switch, settings, regole, coda dei bot) | MP-36, MP-43 | obiettivo dell'architettura («esattamente come i competitor»: nessun DB remoto) | T10, T14, T22 | L |
| 9 | Heartbeat API (ordini cancellati da Betfair se l'app cade) | MP-30 | stop e offset sono software come per tutti i competitor; il battito e' l'unica rete di sicurezza lato Betfair | TP-3 / T24 (U-17, decisione utente) | S-M |
| 10 | Scanner a conflate 1000 ms | MP-03 | 50 volte il refresh di Bet Angel sull'ingresso di Mike/Safe/Omega; cambia l'input dei bot: SOLO con decisione U-01 e replay | T19 + U-01 | S (codice) / L (banco) |

Poi, minori: contatore transazioni a schermo (MP-20, S), bet delay a schermo (MP-19, S), allarmi sonori (MP-41, S), storia del
grafico e indicatori (MP-47, M), griglia oltre 8 ladder (MP-48, M), API locale documentata (MP-38, S), FOK/cash-out tennis (MP-21,
MP-27, M con T21), ripartizione libera del cash-out (MP-26, S), OCO con uscita parziale (MP-25, S), Repeat on Success (MP-34) ed
Excel (MP-39) solo se l'utente li chiede.

Punti in cui siamo gia' MEGLIO (da non perdere nelle tappe): minimi .it e place-and-trim (MP-31), WOM esteso (MP-13), cash-out
per evento (MP-27), limiti per evento/campionato e stop giornaliero (MP-42), paper nello stesso processo con bet delay e coda
(MP-44), certificazione sul banco col codice di produzione (MP-45), auto-follow (MP-50).

## 5. Cosa non ho potuto verificare

- **Siti dei competitor**: non raggiungibili da questo ambiente (sezione 0); tutte le dichiarazioni dei competitor sono quelle
  gia' raccolte in 02, non rilette. Restano n.d.: Geeks Toy e lo Stream API, frequenze di Fairbot, streaming di Gruss (solo
  l'indice Scribd non letto), drag-and-drop e «annulla tutto» di Bet Angel, dettagli dell'API Monitor di Cymatic oltre 02.
- **Rimappatura dei tasti** dalla UI e **stake in % del saldo**: non verificate a fondo (MP-18, MP-35).
- **Caso parziale dell'OCO** (stop che si riduce con l'uscita parziale, MP-25): non provato sul banco.
- **Minimo .it 1,00 contro 2,00 EUR** (MP-31): divergenza fra `minimi_it.py:30` e 02 §3.4 riportata, non indagata.
- **Numeri di latenza**: nessuna misura nuova eseguita qui (lavoro di sola lettura); i numeri citati sono di 07, 04 e
  `AVANZAMENTO.md`.
- Nessun test, replay o app eseguiti: la matrice e' un documento.
