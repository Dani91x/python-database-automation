# AUDIT - le strade verso l'ordine reale su Betfair (24/09/2026)

Audit di architettura, in sola lettura. Nessun codice modificato, nessun processo avviato,
nessun accesso al DB o a Betfair. Base: master `3f65b2f`. Autore: delegato Opus del
coordinatore. Una parte della mappa (Mike; Omega/Safe/Safe tennis; bot tennis e ingressi
REST) l'hanno raccolta tre delegati Explore in sola lettura. Ogni loro affermazione
money-critical citata qui l'ho ricontrollata a campione sul codice (sezione 8).

Convenzioni usate nel documento:
- i file sono relativi a `Betfair/`, salvo dove indicato;
- "RTT DB" = una chiamata PostgREST, misurata a 92-307 ms (`safe_strategy/LATENZA_TENNIS_2026-09-17.md:23`);
- "WS" = un giro sul canale locale 127.0.0.1, misurato a 0,59 ms p50 (stesso documento);
- "RTT Betfair" = HTTPS verso api.betfair.com dall'Italia. Non l'ho misurato: assumo 30-80 ms;
- il bet delay in-play (in genere ~5 s nel calcio) e' di Betfair: vale uguale per tutti i
  percorsi, noi compresi, e non entra nei confronti.

---

## 0. IL RISULTATO IN DIECI RIGHE

1. Oggi non ci sono quattro strade ma **sette modi concreti di arrivare a `placeOrders`**
   (tabella 1.0). Nel calcio nessun bot usa una strada sola: Omega e Safe usano la coda
   del runner se un controllo lo permette, altrimenti ripiegano in silenzio sul REST FOK.
2. **La strada del canale 47331 non e' veloce.** Il comando del desktop arriva al runner
   in meno di 1 ms, poi aspetta il `BackgroundWorker` a 1,0 s e l'IO sul DB del suo giro.
   Dal clic a `place_order` passano 0,6-2,2 s. Il runner tennis, con lo stesso codice a
   0,15 s, sta a 0,08-0,3 s.
3. La strada piu' veloce che abbiamo e' quella dei 4 bot tennis: flumine nello stesso
   processo, meno di 1 ms fra decisione e `place_order`. E' il modello da seguire.
4. Dalla decisione a `placeOrders`, Omega e Safe calcio sulla coda DB impiegano 1,3-3,5 s,
   bet delay escluso. Mike in REST 0,1-0,5 s, ma in gioco il suo unico thread resta fermo
   per tutto il bet delay.
5. I competitor (Bet Angel, Geeks Toy, Fairbot, Gruss) hanno un unico processo locale che
   chiama l'API direttamente, prezzi e ordini in streaming, nessun database fra clic e
   ordine. Stimo 40-150 ms dal clic a Betfair: siamo 10-40 volte piu' lenti.
6. **Proposta (la tua ipotesi regge, con quattro condizioni).** Esecutore unico = il runner
   dello sport (flumine nello stesso processo). Tutti gli attori, desktop e bot, ci arrivano
   dal canale. Il DB resta diario e ripiego. Le condizioni:
   (a) svuotamento del canale a evento, senza sonno da 1 s;
   (b) nessun IO sul DB nel percorso dell'ordine, ne' sul thread principale di flumine;
   (c) diario locale scritto PRIMA dell'invio, cosi' nessun ordine resta senza diario;
   (d) protocollo dei comandi con identita', ref deterministico, esito in due tempi e
   limite d'eta'.
   Latenza attesa dalla decisione a Betfair: 35-100 ms, alla pari dei competitor.
7. **Mike per primo? Si' come obiettivo, no come primo passaggio.** Prima si rinforza il
   runner (condizioni a-c, che servono a tutti), poi si prova il trasporto nuovo sul caso
   piu' piccolo (Safe calcio: cambia solo il trasporto, l'esecutore e' gia' il runner).
   Poi Omega, poi Mike, che e' il cambio piu' grande: REST, submin sincrono, appoggiate,
   bet delay simulato in casa, e il ramo coda che oggi e' rotto.
8. Reperti gravi fuori dal tema velocita', da portare subito all'utente (sezione 2.3):
   - T1: nel tennis un bot acceso come "paper" con runner LIVE piazza soldi veri;
   - T2: nel tennis mancano kill-switch e stop giornaliero;
   - C1: i canali di comando 47331/47332 non controllano l'Origin, quindi una pagina web
     locale puo' inviare ordini;
   - M1: con il ramo coda acceso, Mike perderebbe l'esito e dichiarerebbe `error` ordini
     vivi.
9. Il banco oggi certifica i bot sul REST (`omega_market.place_order_live` servito da
   `MercatoFlumine`). **Il worker del runner non e' sul banco.** Con la strada unica, il
   banco deve eseguire il `_dispatch` vero del runner (sezione 4.6).
10. Ogni fase del piano (sezione 5) si certifica per bot e per scenario, una registrazione
    alla volta, in minuti: non servono test di giorni.

---

## 1. LA MAPPA

### 1.0 Le strade reali, in una tabella

| # | Strada | Chi la usa | Dalla decisione a placeOrders (stima) | Come si sa l'esito |
|---|---|---|---|---|
| S1 | Coda DB `betfair_live_order_requests`, worker del runner calcio | Omega e Safe calcio (se il controllo e' aperto); desktop calcio se il canale e' giu'; risk_engine | 1,3-3,5 s | specchio `betfair_live_orders` + topic `order`; bot: poll a 2 s (Safe) o 20-60 s (Omega); terminali dal canale se `ESITI_ORDINI_CANALE=1` |
| S2 | Canale 47331, poi `_process_local_requests` nello stesso worker | desktop calcio (ladder, green-up, cash-out) | 0,6-2,2 s | risposta WS (dopo `_audit`) + topic `order` |
| S2t | Canale 47332, poi worker ordini del runner tennis | desktop tennis | 0,08-0,3 s | risposta WS + topic `order` |
| S3a | REST diretto JSON-RPC (`omega_market.place_order_live`, FOK) | Mike (sempre); Omega e Safe se il controllo e' chiuso; Safe tennis (sempre) | 0,1-0,5 s (thread del bot fermo per il bet delay) | risposta sincrona; appoggiate con `listCurrentOrders` a ogni giro |
| S3b | flumine nello stesso processo del runner tennis | 4 bot tennis | < 1 ms | oggetti Order in memoria, aggiornati dallo stream ordini, letti al book successivo |
| S4a | Servizio scalper calcio (processo per evento, flumine proprio) | UI (`scalper_activate`) | < 1 ms nel processo | flumine in memoria + specchio |
| S4b | Strumenti REST e CLI: `odds_http /place-order` (8787), `order_worker` (pre-match), `run_scalper_live.py`, `run_tennis_scalper/pro` | CLI o `start_order_server.py` | variabile | risposta HTTP o log |

### 1.1 S1 - Coda DB (Omega e Safe calcio), passo per passo

**Lato bot, Omega** (`omega/omega_service.py`):
1. `run_once` -> `scan_and_place_legs` (:6853) -> `_size_and_place` (:1908) -> `_place_one` (:2249).
2. Riserva `db.insert_trade` (:2310). 1 RTT DB.
3. Controllo `_flumine_gate` (:2535-2579), che fa altre 2 letture:
   - `live_follow_status` deve valere `STREAMING`;
   - battito del runner con eta' <= 90 s.
4. `_flumine_enqueue_place` (:2600-2694):
   - pre-marcatura `flumine_client_ref` (1 RTT);
   - RPC `request_betfair_live_order` (1 RTT);
   - FOK solo in live (:2644-2647).

**Lato bot, Safe**: stessa catena.
1. `bot_service.py:4765 _execute` -> `execution.py:353 X.place` -> `_gate` (:430) -> `enqueue_place` (:759-871).
2. FOK anche in paper (:835).
3. Ref `safe-t<id>`.

**Lato runner** (`stream/runner.py`, `stream/live_order_worker.py`):
1. `BackgroundWorker(_live_order_worker_guardato, interval=LIVE_ORDER_QUEUE_POLL_SEC or 1.0)` (runner.py:1975-1979). Il default e' 1,0 s (config_stream.py:198) e il `.env` non lo cambia.
2. Il flumine installato (2.13.11) esegue la funzione e POI dorme `interval` (`flumine/worker.py:56-80`). Il periodo vero e' quindi 1,0 s + il lavoro del giro.
3. Ogni giro di `_process_once` (live_order_worker.py:3214) fa, in serie:
   - `_refresh_settings`: RPC `get_live_settings`, limitata a 1 al secondo (:3228), quindi di fatto a ogni giro (1 RTT);
   - svuotamento del canale (:3231);
   - `_advance_inflight_submins` per ciascuna modalita' servibile, live e paper (2 RTT);
   - lettura delle righe pending (:3268-3278, 1 RTT);
   - per ogni riga: `_claim` (:727, 1 RTT) -> `_dispatch` (:3113) -> `_do_place` (:1184) -> `build_order` -> `_place_or_raise` (:1022) -> `market.place_order(..., client=<client della modalita' della riga>)`;
   - poi `_write_done` (UPDATE + INSERT in `betfair_live_audit`, 2 RTT) e `_journal_done` (3 SELECT + 1 INSERT, 4 RTT; :844-953).
4. Il periodo tipico del giro e' ~1,4-2,2 s. Con 5 righe in un giro, l'ultima aspetta l'IO delle prime quattro, cioe' altri 4 x 7 RTT, ~2,5-8 s.
5. `market.place_order` in flumine valida i controlli nativi in modo sincrono e affida il pacchetto al pool di thread dell'esecuzione (`flumine/execution/baseexecution.py:27-42`, 32 worker, sessione `requests` riusata). La POST `placeOrders` parte da quel pool, con `async_place_orders=False`: in gioco quel thread resta fermo per il bet delay, il worker no.

**Stima dalla decisione a `placeOrders`:**
- bot: 5 RTT, 0,5-1,5 s;
- attesa del giro: in media ~0,7-1,1 s, al peggio ~2,2 s;
- claim: 0,1-0,3 s;
- piazzamento: pochi ms, poi RTT Betfair.
- **Totale 1,3-3,5 s.**

**Esito:**
1. Lo stream ordini chiama `LiveTradingStrategy.process_orders` (engine/live_trading_strategy.py:169). Gira sul thread PRINCIPALE di flumine.
2. `db.upsert_live_order` (db.py:535-556) pubblica `order` sul canale e subito dopo fa un upsert DB sincrono con retry (fino a 3 tentativi, `_exec_retry` db.py:44-58). Poi c'e' anche l'upsert della posizione.
3. Il bot lo sa in due modi:
   - dal canale, solo stati terminali (`esiti_ordini_canale.py`, `.env ESITI_ORDINI_CANALE=1`): pochi ms, piu' la fine del `run_once` in corso, piu' 2-4 RTT;
   - altrimenti, e sempre per i parziali e per gli stati intermedi, dal poll del giro dopo: 2 s Safe, 20-60 s Omega.

**Ripiego silenzioso.**
- Se `live_follow` non e' STREAMING, o il battito ha piu' di 90 s, Omega e Safe vanno in REST FOK (S3a).
- Per Omega il log `live_fok_fallback` esiste (omega_service.py:2403-2405).
- Quale strada abbia preso l'ordine si capisce solo dal log.

### 1.2 S2 - Canale 47331 dal desktop

**Frontend.**
- `frontend/src/lib/localTransport.ts:434-450`: se il canale e' `connected` usa `channel.request('order', {...cmd, client_ref: randomUUID})`, altrimenti la coda DB.
- Su timeout (10 s, `localChannel.ts:69`) o caduta del canale: rifiuto "NON reinviare", e nessun ripiego automatico sul DB. Questo e' corretto: evita il doppio invio.

**Runner.**
1. `local_channel.py:195-233`: il thread asyncio mette in una `queue.Queue` (massimo 200 comandi).
2. Il comando resta li' fino al giro del worker (S1, punto 3). `_process_local_requests` (live_order_worker.py:3018-3107) viene chiamato dopo `_refresh_settings` (1 RTT).
3. `_dispatch` con un `sb` finto per la tabella della coda. Pero' `_audit` scrive DAVVERO su `betfair_live_audit` PRIMA della risposta: `_write_done` -> `_audit`, :955-965, con `_LocalSb` che lascia passare le altre tabelle (:2929-2943).
4. `ch.respond` (:3096).
5. POI, in serie e sullo stesso thread, prima del comando successivo:
   - `_record_local_request`: INSERT con backoff (:2976-3015);
   - `_journal_done`: 4 RTT.

**Stima.**
- Dal clic a `place_order`: in media 0,6-1,1 s, al peggio ~2,2 s.
- Risposta al desktop: +0,1-0,3 s.
- Un secondo comando nello stesso giro (per esempio annullo + green-up) aspetta altri ~0,6-1,5 s.

**Buchi.**
- **Dedup solo in RAM** per `client_ref` (:2863-2890), TTL 300 s, perso al riavvio. Il frontend genera comunque un UUID nuovo per ogni comando, quindi il dedup protegge solo il reinvio identico dello stesso messaggio.
- **Nessun limite d'eta'** sui comandi del canale (`LocalRequest` non porta l'istante).
  - A runner fermo senza partite (idle, runner.py:1799-1859) il framework e il worker non esistono: i comandi restano in coda senza risposta. Il desktop va in timeout a 10 s, ma il comando verra' eseguito all'aggancio successivo, se il mercato e' sottoscritto.
  - Stesso discorso durante il riavvio morbido della sottoscrizione.
  - Solo la guardia d'avvio svuota e rifiuta (runner.py:1658-1695).
- **Ordine senza diario**:
  - con DB giu', l'ordine parte lo stesso;
  - la registrazione fallisce con un solo WARNING (:2998-2999);
  - per green-up e cash-out c'e' un alert CRITICAL (:3002-3014), ma anche quell'alert passa dal DB.

### 1.3 S2t - Canale 47332 dal desktop tennis

- Stesso modello. Worker `tennis_orders` a `TENNIS_ORDER_POLL_SEC`, che l'app porta a 0,15 s (`desktop/main.js:211`).
- Coda DB `tennis_live_order_queue` letta al massimo ogni 1,0 s.
- `_do_place` con `customer_strategy_ref="tennis"` (`stream/tennis_live/tennis_live_order_worker.py:469-515`).
- Mancano:
  - kill-switch e stop giornaliero;
  - limite d'eta' sulle righe pending.
- Numero da ricordare: **lo stesso disegno a 0,15 s e' ~7 volte piu' reattivo del calcio**. Il collo e' la cadenza, non il canale.

### 1.4 S3a - REST diretto (Mike; ripiego di Omega e Safe; Safe tennis)

**Mike** (`mike/service.py`, verificato a campione):
1. `main` (:4716) fa girare `run_once` ogni 1 s, oppure 5 s in idle (:4765-4772).
2. `_run_event` -> `E.decide` (:3371) -> `execute_place` (:551):
   - freni (:586-620);
   - riserva in `mike_trades` (:671-677), 1 RTT DB;
   - `execution_mode='rest'` salvo `MIKE_USE_FLUMINE_QUEUE` (:679), che manca nel `.env`.
3. `X.place` (safe_strategy/execution.py:353), poi `_RealMarket.place_order_live` (service.py:115-222: `_pretendi_live_abilitato`, poi strategy ref "mike"), poi `omega_market.place_order_live` (omega/omega_market.py:659-715):
   - LIMIT, LAPSE, FILL_OR_KILL;
   - `customerOrderRef = customerRef = "mike-t<id>"`.
4. `client.py:329-359` fa la POST JSON-RPC su `requests.Session`, timeout 30 s, `max_retries=2` con pausa di 2 s. Il de-dup dei ritenti e' affidato al `customerRef`, che Betfair usa su una finestra di 60 s.
5. Lay appoggiata: `_piazza_resting_live` (:1159-1165), `fill_or_kill=False`. NON passa da `_live_brake` e non ha submin.

**Latenze.**
- Dalla decisione alla POST: 0,1-0,5 s.
- La chiamata e' sincrona: in gioco il thread UNICO di Mike resta fermo per tutto il bet delay (~5 s). Tutte le altre partite sono ferme con lui.
- Esito:
  - FOK: nella risposta;
  - appoggiata: `listCurrentOrders` REST a ogni giro, per ogni gamba viva, senza limite di cadenza (:1507-1590, :3299-3310);
  - esito ignoto: `_reconcile_unknown`, limitato a 60 s, con grazia di 120 s.

**Omega e Safe in ripiego.**
- Stessa funzione `omega_market.place_order_live` (Omega :2409, :4608; Safe execution.py:540-545).
- Gli ordini REST di Safe portano `customerStrategyRef="omega"` (omega_market.py:713).

**Safe tennis.** Il controllo guarda `live_follow`, che e' la tabella del runner CALCIO. Per un evento tennis non e' mai STREAMING, quindi Safe tennis va SEMPRE in REST: e' misurato (trade 297/298 `percorso: "rest"`, LATENZA_TENNIS:396-398).

### 1.5 S3b - I 4 bot tennis (flumine nello stesso processo)

1. `tennis_runner.setup_and_run` (:1510) crea un solo `Flumine` (:1584) e registra i bot con `framework.add_strategy(bot)` (:1614), sullo stesso stream della cattura.
2. `process_market_book` -> `_place` -> `market.place_order(order)` (scalper :2268, pro :388, flb :190, swing :203), sul thread principale di flumine.
3. Nessun `customer_order_ref` e nessuna strategy ref propria (reconcile_worker.py:559-564: finiscono nel bucket "manual").
4. Esito: dallo stream ordini negli oggetti Order. Nessuno dei 4 definisce `process_orders`: lo leggono al book successivo.

E' il percorso piu' veloce che abbiamo. Le sue guardie sono le piu' deboli (tabella 2.1).

### 1.6 S4 - Altri ingressi

| Ingresso | Chi lo accende | Live di default | Guardie che mancano |
|---|---|---|---|
| `stream/odds_http.py:122-214` `/place-order` (127.0.0.1:8787) -> `order_exec.py:204-365` | `start_order_server.py` / `.bat` (non l'app) | SI' | kill-switch, mode, avvio_app, dedup (`customer_ref` = uuid casuale, :309), audit su DB; Origin assente accettato (:113-116) |
| `order_worker.py:59-126` (coda pre-match `betfair_order_requests`) | UI "Invia Giocate" (se il processo e' acceso) | SI' | RPC aperta a tutti gli `authenticated` senza controllo di owner; kill-switch, mode, avvio_app, limite d'eta' |
| `stream/scalper/scalper_service.py` -> `scalper_session.run_session` | UI (`scalper_activate`, owner-only) | NO (`dry_run` true) | kill-switch globale, stop giornaliero, strategy ref; flumine e stream PROPRI per evento (connessioni e login in piu') |
| `stream/scalper/run_scalper_live.py:227-241` | solo CLI | SI', sempre | kill-switch, mode, avvio_app, ref, audit su DB, paper |
| `stream/tennis_scalper/run_tennis_scalper.py`, `run_tennis_pro.py` | solo CLI | NO (`--live` esplicito) | kill-switch, avvio_app, audit su DB |
| `stream/trading/tools/test_pat_dal_vivo.py` | - | - | NON ESISTE piu' in nessun checkout (la voce B20 del riepilogo e' superata) |

Il desktop non espone IPC (`desktop/preload.js` e' vuoto). Nessuno script d'ordine parte a richiesta dall'app.

---

## 2. DIVERGENZE

### 2.1 Stessa cosa, regole diverse

| Regola | Worker calcio (S1/S2) | Mike REST | Omega (coda/REST) | Safe calcio | Safe tennis | Bot tennis | Desktop tennis |
|---|---|---|---|---|---|---|---|
| Modalita' | per riga (`_dispatch` :3113); client per modalita' (F0) | `mike_control.mode`, congelata per partita | `control.mode`; il manuale si fida del payload (:4434) | `strategy_modes` per variante | `strategy_modes`; le proposte prendono `model` | **env di processo** `TENNIS_LIVE_ORDER_MODE`; la modalita' per bot diventa solo `dry_run` e **al contrario** (tennis_bot_service.py:397) | per riga, controllo cross-mode |
| Kill-switch env | si', riletto per riga (:352-365) | `_live_brake`, solo aperture `X.place`, **non** sulle appoggiate; fail-open se l'import fallisce (execution.py:101-106) | **nessuno** sul REST (:2406-2413, :4603-4613) | `_live_brake` sulle aperture REST | `_live_brake` | **nessuno** | **nessuno** |
| Kill-switch DB (`betfair_live_settings`) | si' | no | no (solo tramite il worker) | no (solo tramite il worker) | no | no | no |
| Guardia d'avvio | `Guardia("runner_calcio")` blocca la coda (runner.py:1624-1711) | `Guardia("mike")` | `Guardia("omega")` | `Guardia("safe")` | idem Safe | `Guardia("tennis")` **mai armata**; il ponte non ferma gli interruttori (`--bridge-only`) | nessuna |
| Ref verso Betfair | `customer_order_ref` flumine = name_hash + uuid (non deterministico); strategy ref `live`; ref interno `awlq<rid>` | `mike-t<id>` + customerRef (de-dup 60 s); strategy `mike` | `omega-t<id>`; strategy `omega` | `safe-t<id>`; strategy **`omega`** sul REST | idem | default flumine | strategy `tennis` |
| Dedup | `client_ref` UNIQUE + claim (DB); canale: RAM con TTL 300 s | riga di riserva + customerRef | indice unico `uq_omega_trades_auto_leg` | `(event_id, signal_key)` unico | idem | nessuno proprio | UNIQUE (DB) / RAM (canale) |
| Minimo .it / place-and-trim | `place_submin` (solo coda DB, escluso dal canale :2850-2852); submin sincrono per green-up e cash-out | `place_submin_live` sincrono; size fuori passo 0,50 spedite dirette | niente: sotto 0,5 si salta | submin fino a 0,01 | idem | submin SPENTO; coperture portate al minimo | `min_stake_rules` |
| FOK in paper | secondo la riga | `paper_fill` FOK (parziale = rifiuto) | coda: niente FOK (TTL 45 s); controllo chiuso: parziale **accettato** | FOK sempre; parziale ucciso | idem | SimulatedExecution | - |
| Bet delay in paper | SimulatedExecution | simulato da Mike (:3431) | SimulatedExecution / nessuno sul ripiego | idem | idem | `FreshDelaySimulatedExecution` | - |
| Controlli nativi (esposizione per selezione, ordini/min, esposizione per evento) | SI' (runner.py:1965-1969) | **NO** | solo sulla coda | solo sulla coda | **NO** | quelli del runner tennis | parziali |
| Tetto per ordine | `LIVE_MAX_STAKE_PER_ORDER` (opt-in) | no | no | no | no | tetto di esposizione per bot | `TENNIS_LIVE_MAX_STAKE_PER_ORDER` (assente) |
| Audit | `betfair_live_audit` + journal + riga di coda | `mike_trades`/`mike_activity` | `omega_trades`/attivita' | `safe_*` | `safe_*` | `tennis_live_orders` (solo se il worker e' registrato) | `tennis_live_order_queue` |
| Specchio `betfair_live_orders` | SI' | **NO** | solo se in coda | solo se in coda | **NO** | tennis_live_orders | tennis_live_orders |
| Esito | stream ordini -> specchio -> `order` | risposta + `listCurrentOrders` | poll specchio (20-60 s) / canale terminali | poll 2 s / canale terminali | risposta REST | Order in memoria | WS + `order` |
| Limite d'eta' del comando | 120 s solo all'avvio (runner.py:1766-1769); proposte 120 s (`approved_at`) | - | - | `_request_age_s` | idem | - | nessuno |

### 2.2 Divergenze con conseguenze sui soldi (ordinate per gravita')

1. **T1 - Bot tennis "paper" con runner LIVE = soldi veri.**
   - Dove: `tennis_bot_service.py:397` scrive `"dry_run": d["mode"] == "live"`; `tennis_runner.py:581-587` in LIVE rispetta quel `dry_run` sul client reale (senza client paper affiancato, :115-153).
   - Condizione: oggi l'env vale PAPER per default (`main.js:220`), quindi il rischio e' latente. Diventa reale il giorno in cui l'env passa a LIVE.
   - E' la voce par.7.25 del catalogo (modalita' ereditata dal servizio).
2. **M1 - Ramo coda di Mike rotto.**
   - Con `MIKE_USE_FLUMINE_QUEUE=1` nessuno legge l'esito della coda: dopo 120 s la gamba viene marcata `error` senza annullare nulla (service.py:3599-3613, 3873-3928).
   - Se il worker aveva piazzato, e' una posizione doppia.
   - Il flag oggi e' spento: non accenderlo prima di F7.
3. **C1 - Canali di comando senza controllo dell'Origin.**
   - `local_channel.py:145` fa `serve(self._handler, "127.0.0.1", port)` senza `origins`.
   - Un WebSocket del browser non e' soggetto a CORS: qualunque pagina aperta sulla macchina puo' collegarsi a `ws://127.0.0.1:47331` e mandare `{"m":"order"}`.
   - Oggi l'unica difesa e' che bisogna conoscere il protocollo.
4. **Ripiego silenzioso Omega/Safe coda -> REST FOK.** Lo stesso ordine prende due strade con garanzie diverse (controlli nativi, specchio, kill-switch del DB) a seconda di un battito di 90 s.
5. **Omega REST senza kill-switch.** `LIVE_KILL_SWITCH=true` ferma il worker ma non Omega in ripiego.
6. **Mike e Safe tennis fuori da specchio, controlli nativi e topic `order`.** La Control Room non vede i loro ordini in tempo reale (CRONOSTORIA:2366).
7. **Strategy ref "omega" sugli ordini REST di Safe.** `listCurrentOrders("omega")` di Omega vede anche gli ordini di Safe. Il rischio di attribuzione sbagliata e' mitigato dai ref `safe-t` / `omega-t`, ma non in modo pulito.
8. **Esiti del canale solo terminali.** Parziali e intermedi restano sul poll DB (scelta voluta: un fotogramma perso non deve dare un falso "nessun abbinamento"). Con un numero di sequenza per ordine (proposta 4.3) il vincolo cade.
9. **Specchio sul thread principale di flumine.** Upsert DB sincroni con retry dentro `process_orders`:
   - ogni cambio d'ordine costa 2 RTT (ordine + posizione) al thread che processa i book e lo stream ordini;
   - con una raffica di ordini, il `publish` dell'ordine N aspetta l'IO dei precedenti;
   - con il DB giu', fino a ~1 s di retry per scrittura.
10. **Controlli di flumine senza lucchetti.** Il worker ordini piazza da un thread del `BackgroundWorker` mentre il thread principale muta il blotter: nel flumine installato ho trovato un solo lock (controls/clientcontrols.py:37). E' un rischio di corsa latente, non osservato. La via ufficiale per arrivare al thread principale e' `CustomEvent` (flumine/events/events.py:108-114, gestita in flumine.py:39-40).

### 2.3 Da portare all'utente come decisioni (oltre a B10 e B31)

| Id | Tema | Opzioni |
|---|---|---|
| D1 (T1) | Modalita' per bot tennis | allineare paper->client simulato affiancato come nel calcio (F0), oppure bloccare "paper" a runner LIVE |
| D2 (T2) | Tennis senza kill-switch e stop giornaliero | stesso freno del calcio |
| D3 (C1) | Controllo dell'Origin + token sui comandi | vedi 4.3 |
| D4 | S4 (8787, order_worker, run_scalper_live) | chiudere, oppure far passare dall'esecutore unico |
| D5 | Ripiego REST per le USCITE a runner giu' | regola gemella "niente che protegge impedisce di chiudere": proposta in 4.4 |
| D6 | `_live_exit_override` di Mike | resta finche' l'utente non decide; la strada unica rende possibile l'appoggiata live, ma toglierlo e' una scelta di strategia |

---

## 3. I COMPETITOR (dalla mia conoscenza: dove non sono sicuro lo scrivo)

| Tool | Architettura d'invio | Prezzi e ordini | Note |
|---|---|---|---|
| **Bet Angel Professional** | app Windows (.NET), processo unico sul PC dell'utente; chiama API-NG direttamente (HTTPS keep-alive) | Exchange Stream API per i prezzi, con aggiornamento configurabile fino a ~20 ms; conferme dalla risposta di `placeOrders` e dallo stream ordini (che lo usi per gli ordini: *probabile, non certo*) | ladder one-click; offset, stop e green-up tenuti dal client (Betfair non ha stop lato server); automazione "Guardian" con regole in memoria; esegue ordini sotto il minimo con il place-and-trim (documentato da loro) |
| **Geeks Toy** | app .NET, processo unico, chiamate dirette | stream per i prezzi; esiti dalla risposta e dagli aggiornamenti ordini (*stream o poll ad alta frequenza: incerto*) | famoso per la reattivita' della ladder; "fill or kill" e offset lato client |
| **Fairbot** | app .NET, processo unico | stream (*incerto se anche per gli ordini*) | ladder, dutching, automazione |
| **Gruss Betting Assistant** | app Windows con ponte verso Excel | poll ad alta frequenza (20-200 ms) e stream nelle versioni recenti (*incerto*) | le automazioni in Excel scrivono celle, e il client invia |
| **Betting Toolkit / Cymatic** | client desktop simili (*non ho dati affidabili sull'interno*) | - | - |

Cosa hanno in comune (con sicurezza):
- **un solo processo** tiene la sessione, il book in memoria e chiama `placeOrders`;
- nessun database fra clic e ordine;
- le regole automatiche girano nello stesso processo dei prezzi.

Latenze tipiche (stima, non misura): dal clic a Betfair ~RTT + elaborazione, cioe' 40-150 ms dall'Europa. La conferma pre-match arriva con la risposta; in gioco arriva dopo il bet delay.

Cosa **non** possiamo replicare, e non replica nessuno:
- il **bet delay in-play**, strutturale;
- le regole di Betfair sul modello di ritardo. Betfair ha introdotto modelli di ritardo "PASSIVE"/"DYNAMIC" (`marketDefinition.betDelayModels`) che su alcuni mercati tolgono il ritardo agli ordini non subito abbinabili. **Da verificare sulle nostre registrazioni** (il campo e' nel `marketDefinition`): se c'e', un ordine appoggiato in gioco evita il ritardo per tutti allo stesso modo;
- i limiti di transazioni per ora (soglia oltre la quale Betfair addebita: *il numero esatto non lo ricordo con certezza*).

Dove possiamo essere **migliori** dei competitor:
- un solo esecutore per desktop E bot, con controlli di rischio di conto (esposizione per selezione e per evento, ordini al minuto) applicati a TUTTI gli ordini. I tool desktop li applicano per regola o per scheda;
- diario completo di ogni decisione (journal E37);
- certificazione su replay delle registrazioni reali con il codice di produzione.

---

## 4. PROPOSTA: LA STRADA UNICA

### 4.1 La tesi (la tua ipotesi, precisata)

> **Un esecutore per sport: il runner, con flumine nello stesso processo. Ogni attore gli arriva
> con UN protocollo di comando sul canale del runner (47331 calcio, 47332 tennis). Il DB e' il
> diario e il ripiego del solo trasporto, mai un secondo esecutore. I bot che vivono dentro il
> runner (4 bot tennis) chiamano l'esecutore in-process con la stessa interfaccia.**

Tre alternative scartate, con i numeri:
- **Ogni bot con il suo flumine** (come lo scalper per evento): risparmia ~1 ms di WS, ma moltiplica login, stream e order stream, spezza il blotter e i controlli di conto, e viola la regola "nessuna chiamata Betfair duplicata" (feed unico).
- **Omega, Safe e Mike DENTRO il runner calcio**: risparmia ~1 ms, ma i loro giri fanno IO DB da 100-300 ms e codice grosso; bloccherebbero il thread dei soldi, e un loro crash abbatterebbe stream e ordini di tutti.
- **Coda DB come strada unica** (la proposta di B10 del 23/09): 1,3-3,5 s per ordine e 5-7 RTT per comando, e contraddice la regola "le letture del DB possono solo diminuire" e "tutto dai canali".

### 4.2 Le quattro condizioni perche' sia VELOCE

1. **Svuotamento a evento.** Il comando del canale sveglia l'esecutore subito. Due modi:
   - (a) un thread "ordini" dedicato che si blocca su `queue.get(timeout=periodo_DB)`: sveglia immediata sul canale, poll DB invariato a 1 s come ripiego;
   - (b) `CustomEvent` nella `handler_queue` di flumine, eseguito sul thread principale: e' il modello di flumine, sicuro sui thread, ma richiede prima la condizione 2.

   Proposta: partire da (a), perche' conserva l'invariante di oggi "un solo thread ordini". Misurare (b) in F0. Obiettivo: p95 fra ricezione WS e `market.place_order` sotto 10 ms.
2. **Nessun IO DB sul percorso dell'ordine.**
   - `_refresh_settings` va su un thread suo; kill-switch e limiti restano letti a caldo, ma da RAM.
   - `_audit`, `_record_local_request`, `_journal_done` e specchio (`upsert_live_order` / `upsert_live_position`) vanno in un **writer asincrono** con coda.
   - Il `publish` sul canale resta immediato.
   - Il thread principale di flumine non fa piu' IO DB.
3. **Diario prima dell'invio (write-ahead).**
   - Una riga JSONL per comando su disco locale (`fsync`, ~1 ms), scritta PRIMA di `place_order`: identita' dell'attore, ref, modalita', parametri, istante.
   - Se la scrittura fallisce, l'ordine non parte (fail-closed per le aperture; per le chiusure: vedi D5).
   - Il writer asincrono ribalta il file sul DB. Con il DB giu' accumula e recupera.
   - Cosi' "ordine senza diario" non puo' piu' accadere, e al riavvio il runner sa cosa aveva in volo.
4. **Esito in due tempi, dal canale.**
   - `ack` (accettato o rifiutato dal runner, in ms, con motivo);
   - poi gli eventi `order` (bet_id, stato, abbinato, residuo, prezzo medio) con un **numero di sequenza per ordine**, piu' `snapshot` su richiesta alla (ri)connessione. Il client capisce se ha perso un fotogramma e chiede lo stato: gli esiti intermedi (parziali) diventano usabili senza poll DB.

**Latenza attesa (stima):**
- decisione del bot -> WS: 0,6 ms;
- esecutore: 1-10 ms;
- write-ahead: ~1 ms;
- `placeOrders`: RTT 30-80 ms.
- **Totale 35-100 ms**, contro 1,3-3,5 s di oggi (S1) e 0,6-2,2 s (S2).
- L'esito arriva quando Betfair lo pubblica sullo stream ordini, piu' ~1 ms: il bot lo sa nello stesso istante del runner.

### 4.3 Il protocollo di comando (una sola forma per tutti)

- **Percorso** `/comando/<attore>` (desktop, mike, omega, safe, safe_tennis, risk_engine), con token letto da un file locale generato all'avvio dall'app.
- **Origin** consentita solo quella dell'app. Senza token: chiusura della connessione.
- I lettori (`/lettore/...`) restano come oggi.
- **Campi obbligatori**:
  - `ref` deterministico dell'attore (`mike-t<id>`, `omega-t<id>`, `safe-t<id>`, UUID del desktop);
  - `mode`;
  - `emesso_ms`, con limite d'eta': per esempio aperture rifiutate oltre 2 s dal momento dell'emissione, chiusure accettate sempre;
  - `strategy_ref` dell'attore. Serve a tenere validi `listCurrentOrders` per strategia e le riconciliazioni di Mike, Omega e Safe. L'esecutore deve passare il `customer_strategy_ref` dell'attore, non "live".
- **Dedup**: sul `ref`, tenuto nel diario write-ahead, quindi sopravvive al riavvio. Un secondo comando con lo stesso ref restituisce l'esito del primo.
- **Azioni**: quelle di oggi (place, cancel, replace, greenup, dutch, cashout_*), piu' `place_submin` anche dal canale. Oggi e' escluso (:2850-2852), ma Safe e Mike ne hanno bisogno; il submin sincrono esiste gia' (`_place_sub_minimum`).
- Il `customerOrderRef` Betfair uguale al ref dell'attore permetterebbe la riconciliazione anche via REST. Flumine lo costruisce da name_hash e id: **da verificare** se si puo' impostare senza sottoclassare l'ordine.

### 4.4 Rischi e come si chiudono

| Rischio | Oggi | Con la strada unica |
|---|---|---|
| Doppio invio | canale: UUID nuovo per comando, dedup in RAM; REST: ritenti coperti dal customerRef 60 s | ref deterministico + dedup nel diario write-ahead; mai ripiego sul DB dopo un invio (solo se il canale era gia' giu' PRIMA dell'invio: regola gia' in `localTransport.ts:438`) |
| Perdita dell'ordine se il runner cade | comando nella `queue.Queue` in RAM perso; il desktop vede "NON reinviare" dopo 10 s | nessun ack = "esito ignoto" nell'attore; al riavvio il runner rilegge il diario e lo stream ordini (immagine iniziale degli ordini correnti) e pubblica lo stato per ref; l'attore riconcilia per ref, mercato e selezione (par.7.6) |
| Ordine senza diario | possibile (DB giu', solo WARNING) | impossibile per costruzione (write-ahead prima di `place_order`) |
| Runner giu' e posizione aperta | Omega e Safe ripiegano sul REST FOK | aperture: nessun ordine (fail-closed, allarme). **Uscite: D5**. Proposta: ripiego REST FOK SOLO per le chiusure, dopo N secondi di runner muto, con attivita' `uscita_via_rest` e ref deterministico. E' l'unica seconda via, e solo per ridurre il rischio |
| Guardie | sparse e diverse (2.1) | tutte nell'esecutore: modalita' per comando (F0), kill-switch env+DB (da RAM), guardia d'avvio, tetti, controlli nativi di flumine per TUTTI gli ordini, limite d'eta', minimo .it e submin. Le guardie di strategia (freni di Mike, budget tentativi, tetti per partita) restano nei bot: non si toccano |
| Paper e live | runner LIVE serve anche paper (client affiancato); tennis no | stesso F0 anche nel runner tennis (chiude T1) |
| Bet delay simulato due volte | Mike in paper lo simula da se' | sul percorso del runner il ritardo lo simula SOLO SimulatedExecution; il ritardo in casa di Mike va spento sul nuovo percorso (par.7.12, par.7.14) |
| Blocco del thread di Mike | la REST sincrona lo ferma per il bet delay | il comando ritorna subito con l'ack; l'esito arriva sullo stream |

### 4.5 Cosa cambia per ogni bot (strategie intoccabili: cambia solo il COME)

| Bot | Oggi | Dopo | Cosa tocca |
|---|---|---|---|
| Desktop calcio | S2 (1 s) / S1 | protocollo 4.3 su 47331 | nessun cambio di UI; stesse azioni |
| Safe calcio | S1 o S3a | comando su 47331; esito dal topic | `execution.enqueue_place` diventa `invia_comando`; il poll resta come riconciliazione |
| Omega | S1 o S3a | idem | `_flumine_enqueue_place` e il manuale; il REST automatico sparisce (resta solo D5) |
| Mike | S3a (REST) | idem, con appoggiate e submin | `execute_place`, `_piazza_resting_live`, `_segui_resting_live` (niente `listCurrentOrders` a ogni giro), ritardo paper in casa. `_live_exit_override` resta (D6) |
| Safe tennis | S3a | comando su **47332** | controllo su `tennis_live_follow`; il runner tennis accetta comandi da bot |
| 4 bot tennis | S3b | invariati come trasporto (in-process); in piu' le guardie dell'esecutore | modalita' per bot (T1), kill-switch (T2), guardia d'avvio |
| Scalper calcio / CLI / 8787 | S4 | D4 | - |

### 4.6 Come si certifica sul banco comune (senza test di giorni)

1. **Una sola interfaccia `PortaOrdini`** nei bot: `invia(cmd) -> ack` piu' un flusso di esiti. Tre implementazioni:
   - produzione: client WS verso il runner;
   - banco: esegue il **`_dispatch` vero del runner** (`live_order_worker`) sul `Market` di `FlumineSimulation`, con la coda di flumine e il bet delay che il banco gia' fa scorrere (`MotoreReplay.attendi_esecuzione`);
   - test: un finto con chiavi e tipi identici al messaggio vero (par.7.27), generato dallo STESSO encoder.

   Cosi' il codice del runner entra finalmente nel banco. Oggi non c'e': i bot sono certificati su `MercatoFlumine.place_order_live`.
2. **Parita' di traccia per bot.** Stessa registrazione, stesso scenario: la sequenza di comandi (lato, prezzo, size, persistenza, tipo, istante di mercato) con il percorso vecchio e con il nuovo deve essere identica, riga per riga. Cambia solo il trasporto; la strategia no.
3. **Scenari nuovi di trasporto**, uno per guasto, una registrazione ciascuno:
   - canale giu' prima dell'invio;
   - canale giu' dopo l'invio senza ack (esito ignoto);
   - runner riavviato a meta' con un ordine in volo;
   - ack perso ed esito arrivato;
   - evento `order` con sequenza saltata;
   - comando troppo vecchio;
   - kill-switch attivato a meta';
   - DB giu' (diario accumulato e poi ribaltato);
   - doppio comando con lo stesso ref.
4. **Spezzettato.** Ogni fase si certifica su: Mike x 15 scenari, Omega x 57, Safe x 21, Safe tennis x 36, 4 bot tennis x 22. Si rilanciano solo i bot toccati; ogni replay dura minuti.
5. **Falsificazione.** Almeno:
   - dedup tolto: doppio ordine, rosso;
   - write-ahead dopo il place;
   - limite d'eta' tolto;
   - sequenza ignorata;
   - `strategy_ref` "live" al posto di quello dell'attore: la riconciliazione di Mike diventa cieca, rosso;
   - ripiego REST anche per le aperture.
6. **Test di contratto "strada unica".** Un test statico elenca i moduli autorizzati a chiamare `placeOrders`, `place_orders` e `market.place_order`: esecutore del runner calcio, esecutore del runner tennis, bot tennis in-process, ripiego D5. Diventa rosso se ne compare un altro (stesso schema di `test_registro_bot`).

---

## 5. PIANO DI LAVORO (fasi piccole, ognuna con test, falsificazione e replay)

Ordine per rischio: prima cio' che non cambia il comportamento, poi il runner (serve a
tutti), poi i bot dal piu' piccolo al piu' grande.

| Fase | Contenuto | Verifica | Parallelo con |
|---|---|---|---|
| **F0 Misura** | i 5 tempi di ESECUZIONE_LIVE par.4 (decisione, invio, presa in carico, risposta Betfair, fill) in log, su tutte le strade; `time.monotonic` nel processo + `placedDate`/`matchedDate` di Betfair. ATTENZIONE: l'orologio del PC e' fuori di ~2 s (servizio Ora di Windows spento, LATENZA_TENNIS:31) | traccia identica a strumentazione spenta; prova a secco in PAPER | F9, F10a |
| **F9 Tennis: guardie** | T1 (client paper affiancato come F0 calcio, oppure rifiuto), T2 kill-switch e stop, ponte che ferma gli interruttori all'avvio, `Guardia("tennis")` armata | test rosso->verde; replay dei 4 bot tennis 22/22 invariati; falsificazione della mappatura invertita | F0 |
| **F10a Contratto strada unica** | test statico degli ingressi (4.6.6) con le eccezioni di oggi elencate per nome | rosso aggiungendo una chiamata finta | F0 |
| **F1 Runner: diario asincrono + write-ahead** | writer con coda per audit, journal, record e specchio; file JSONL prima del place; `publish` immediato | test di ordine degli eventi; DB giu' simulato -> ordini eseguiti e diario ribaltato; falsificazione (write-ahead dopo il place) | F4 (disegno) |
| **F2 Runner: svuotamento a evento** | thread ordini su `queue.get`; settings su thread suo; poll DB 1 s invariato | p95 ricezione -> place < 10 ms (sonda); coda DB invariata (traccia); falsificazione (sonno reintrodotto -> sonda rossa) | - |
| **F3 Protocollo** | `/comando/<attore>`, token + Origin, ref deterministico, limite d'eta', ack, `order` con sequenza + snapshot, dedup persistente, `place_submin` dal canale, strategy ref per attore | test di contratto con l'encoder vero dai due lati; mutazioni su ognuna delle regole | F4 |
| **F4 Banco** | `PortaOrdini` + `_dispatch` del runner sul banco + scenari di trasporto | parita' di traccia sui replay attuali (Mike 15, Omega 57, Safe 21, Safe tennis 36) | F1, F3 |
| **F5 Safe calcio** | `enqueue_place` -> comando; ripiego REST solo per le uscite (D5) | Safe x3 19+2 identici (PM6/T13 noti) + scenari di trasporto | - |
| **F6 Omega** | idem + manuale; `_live_brake` non serve piu' (il freno lo fa l'esecutore) | Omega 57/57 identici | - |
| **F7 Mike** | place, appoggiate, submin, `_segui_resting_live` dagli esiti; ritardo paper in casa spento sul nuovo percorso; ramo `MIKE_USE_FLUMINE_QUEUE` rimosso | Mike 15/15 identici + CP1 severo + falsificazioni par.7.1-7.7 | - |
| **F8 Safe tennis** | comandi su 47332, controllo su `tennis_live_follow` | Safe tennis 34+2 identici (T7 noti) | dopo F9 |
| **F10b Chiusura S4** | secondo D4 | contratto verde senza eccezioni | - |

Si puo' fare subito e in parallelo: F0, F9, F10a (nessuno cambia il percorso dell'ordine
nel calcio). Poi F1 e F4 in parallelo. F2 e F3 in serie. F5, F6, F7 uno alla volta, ciascuno
con un giorno di paper osservato (C7) prima del successivo.

Vincoli rispettati:
- strategie intoccabili (cambia il trasporto; la parita' di traccia lo prova);
- paper e live separati per comando (F0 esteso al tennis);
- nessun processo nuovo (thread dentro il runner, non processi);
- tutto dai canali; letture DB in calo: via le ~5 RTT per ordine dei bot, via il poll dello specchio.

---

## 6. NUMERI CHIAVE

| Misura | Valore | Fonte |
|---|---|---|
| RTT PostgREST | 92-307 ms | LATENZA_TENNIS:23 (misura) |
| Giro WS locale | 0,59 ms p50 | idem (misura) |
| Periodo del worker calcio | 1,0 s + IO del giro (~0,4-1,2 s) | config_stream.py:198, flumine/worker.py (stima dal codice) |
| Periodo del worker tennis | 0,15 s | desktop/main.js:211 |
| IO DB per comando dal canale calcio | 1 (settings) + 1 (audit, prima della risposta) + 1 (record) + 4 (journal) | live_order_worker.py |
| IO DB per ordine di un bot sulla coda | 5 (bot) + 1 (claim) + 2 (done + audit) + 4 (journal) + ~2 per cambio (specchio) | stima dal codice |
| Dalla decisione a placeOrders | S1 1,3-3,5 s; S2 0,6-2,2 s; S2t 0,08-0,3 s; S3a 0,1-0,5 s; S3b < 1 ms; proposta 35-100 ms | stima |
| Esito al bot | Omega 20-60 s (poll) / ms + fine giro (canale, solo terminali); Safe 2 s; Mike REST sincrono, appoggiate 1-5 s; proposta: ms dopo lo stream ordini | stima |
| Competitor, dal clic a Betfair | 40-150 ms | stima, non misurata |

## 7. COSA NON HO POTUTO VERIFICARE

- Nessuna misura dal vivo: tutte le latenze sono stime dal codice, tranne RTT DB e WS (misurati il 17/09 da altri).
- L'RTT verso Betfair (assunto 30-80 ms).
- Se flumine permette di impostare il `customerOrderRef` Betfair (4.3).
- Se i nostri mercati hanno `betDelayModels` PASSIVE/DYNAMIC (va letto nelle registrazioni).
- I dettagli interni dei competitor (stream per gli ordini o poll): dichiarati incerti.
- La sicurezza della concorrenza flumine worker/thread principale: rischio dedotto dall'assenza di lock, non osservato.
- Alcune righe citate dai delegati non le ho ricontrollate una per una (ho ricontrollato quelle della sezione 8).
- `ESECUZIONE_LIVE.md` esiste solo nel checkout principale (non tracciato in git).

## 8. VERIFICHE A CAMPIONE FATTE DA ME SUI RAPPORTI DEI DELEGATI

- Mike:
  - `service.py:679` `execution_mode` "rest" salvo flag;
  - `service.py:1159-1165` appoggiata REST `fill_or_kill=False` con `mike-t<id>`;
  - `client.py:329-359` `max_retries=2` e `customerRef`.
- Omega:
  - `omega_service.py:2546-2579` controllo (live_follow STREAMING, battito, fail-closed);
  - `:2644-2647` FOK solo in live;
  - `:2404-2412` ripiego `place_lay_live`.
- Safe: `execution.py:830-835` FOK anche in paper.
- Tennis:
  - `tennis_bot_service.py:397` `dry_run = mode == "live"`;
  - `tennis_runner.py:578-588` dry_run dal control in PAPER e in LIVE, forzato in OFF;
  - `:115-153` in LIVE solo client reale;
  - test che fissano la mappatura (`test_ponte_interruttori_2026_09_17.py:122-135`);
  - `main.js:211` (0,15 s) e `:220` (PAPER per default).
- Runner e worker calcio: tutto letto di persona (sezioni 1.1-1.2).
- flumine 2.13.11 nel `.venv`:
  - `worker.py`: esegue, poi dorme;
  - `baseexecution.handler`: pool di thread;
  - `config.async_place_orders=False`;
  - `CustomEvent` presente;
  - un solo lock nel pacchetto.
