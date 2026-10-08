# SCHEDA DI COMPONENTE A - Connessione Betfair e cache dei mercati

Data: 08/10/2026. Autore: delegato Sonnet (piano di architettura). Prefisso funzionalita': `A-`.
Regola di lettura: ogni affermazione porta `file:riga`, un numero misurato con lo strumento citato, o una
riga di documentazione di libreria nel `.venv` (flumine 2.13.11, betfairlightweight 2.23.2). Dove non ho potuto
verificare lo scrivo (ultima sezione). Le ipotesi di §4 del brief del piano NON sono prese per vere: sono
confrontate col codice in §1.9 e §4.1.

Strumenti miei (rieseguibili, sola lettura, in `ARCHITETTURA_2026-10/strumenti/`):
`a_gemelle_connessione.py` -> `a_gemelle_connessione_output.txt` (difflib runner calcio vs tennis e recorder);
`a_gemelle_canali.py` -> `a_gemelle_canali_output.txt` (difflib fra i moduli dei canali). Riusano la
normalizzazione di `e4_gemelli_tennis.py` (righe di codice = senza vuote, commenti `#`, docstring).
Fonti di partenza usate: `inventario/uscite/s02_archi.tsv` (grafo import), `s04_dettaglio_copie.tsv`
(funzioni duplicate), `misure/uscite/m01_feed_raw.txt` (40 registrazioni), `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`.

## Perimetro (righe `wc -l` su file tracciati, 08/10/2026)

Perimetro del brief (19 file): `Betfair/client.py` 426, `Betfair/stream/auth.py` 294, `runner.py` 3.171,
`raw_listener.py` 325, `recorder.py` 249, `tennis_live/tennis_runner.py` 3.483, `tennis_live/tennis_recorder.py` 384,
`tennis_live/mercati_registrati.py` 95, `config_stream.py` 339, `board_worker.py` 230, `canale_bot.py` 426,
`ladder_canale.py` 169, `esiti_ordini_canale.py` 850, `sveglia_canale.py` 390, `tennis_live/canale_bot_tennis.py` 357,
`scores/scan_feed.py` 540, `safe_strategy/stream.py` 567, `Betfair/refresh_worker.py` 99, `Betfair/odds_refresh.py` 263
= **12.657 righe** (`wc -l` della lista).
Aggiunti seguendo gli import e il codice (8 file): `local_channel.py` 767, `frammenti_mercato.py` 665,
`sottoscrizione_a_caldo.py` 113, `tennis_live/iscrizione_a_caldo.py` 322, `stream_muto.py` 292, `flusso_prezzi.py` 345,
`runner_lifecycle.py` 291, `valuta.py` 349 = **3.144 righe**. Confini con altre schede (citati, non contati):
`safe_strategy/canale_scan.py` 529, `auto_follow.py` 1.111 (D), `safe_strategy/service.py` 3.444 (scanner: B/E),
`omega/omega_market.py` (C).
Totale perimetro scheda: 15.801 righe, ma **non e' tutto A**: `runner.py` e `tennis_runner.py` contengono anche
ordini, punteggi, ciclo di vita e processi. Quota A stimata per intervalli di righe (conto in §4.3).

---

## 1. Oggi

### 1.1 Responsabilita' reali (lette dal codice)

1. **Sessione Betfair** (login certificato .it, keepAlive, rifacimento): due implementazioni parallele,
   `betfairlightweight.APIClient` costruito da `auth.py:31-80` e un client JSON-RPC nostro `client.py:34-257`.
2. **Connessioni Stream API di mercato**: calcio (`runner.py` + `frammenti_mercato.py`), tennis
   (`tennis_runner.py`), scanner (`safe_strategy/stream.py`), sessioni scalper (`scalper_session.py:1786`).
3. **Connessione order stream** (solo per i fill reali/simulati, flumine) - confine con C.
4. **Cache dei mercati**: la tiene flumine/betfairlightweight; sopra, copie nostre (§1.5).
5. **Registrazione raw** nativa (`raw_listener.py`, `tennis_recorder.py`) e curata (`recorder.py`).
6. **Ladder verso la UI** (`ladder_worker` x2, `ladder_canale.py`, `local_channel.py`).
7. **Feed unico** `safe_strategy_scan` (lo scrive lo scanner, lo leggono i bot): `scan_feed.py`, `board_worker.py`.
8. **Salute del flusso** (battiti, stallo, ricostruzione) in 4 implementazioni (§3, D9).
9. **Ripieghi REST** (listMarketBook/listMarketCatalogue) in 5 punti (§1.8).

### 1.2 Dipendenze in entrata (grafo `s02_archi.tsv`, colonna importatore -> importato)

| Modulo | Importato da (produzione) |
|---|---|
| `Betfair/client.py` | `betfair_report_manager.py`, `odds_refresh.py`, `stream/runner.py`, `betfair_full_odds.py`, `betfair_tennis_odds.py`, `import_betfair_operations.py` |
| `stream/auth.py` | `safe_strategy/service.py`, `runner.py`, `scalper/{habitat_scan,run_scalper_live,scalper_service,scalper_session}.py`, `tennis_live/tennis_runner.py`, 5 script `tennis_scalper/*` |
| `stream/recorder.py` | `runner.py`, `tennis_live/tennis_runner.py` (importa `serialize_book`, `tennis_runner.py:56`), `tennis_replay/convertitore.py`, `tennis_scalper/record_tennis.py` |
| `stream/raw_listener.py` | `frammenti_mercato.py`, `runner.py`, `tennis_scalper/run_tennis_{pro,scalper}.py` |
| `stream/local_channel.py` | 9 servizi/bot (mike, omega, safe bot, safe scanner, scalper, tennis bot) + runner + `db.py` + `live_trading_strategy.py` + `live_order_worker.py` + `reconcile_worker.py` + banco (`porta_banco.py`) |
| `stream/config_stream.py` | 20+ moduli (runner, db, live_order_worker, risk_engine, scalper_session, backtest/registro_bot, ...) |
| `safe_strategy/stream.py` | `safe_strategy/service.py`, `stream_muto.py` |
| `scores/scan_feed.py` | `mike/feed.py`, `omega/omega_service.py`, `board_worker.py`, `riserva_prezzi.py`, `runner.py`, `tennis_runner.py` |
| `stream/runner.py` | nessuno (entry point); `tennis_runner.py` e` tennis_bot_service.py`/`guardie_tennis.py` importano `tennis_runner` |

Dipendenze in uscita principali: `flumine` (`Flumine`, `BaseStrategy`, `BackgroundWorker`, `MarketStream`,
`HistoricalStream`), `betfairlightweight` (`APIClient`, `StreamListener`, `filters`), `websockets` (canale),
`requests`, Supabase (`db.py`, `tennis_db.py`, `safe_strategy/db.py`).

### 1.3 Quante connessioni Stream API esistono e dove si aprono

Limiti Betfair come li scrive il codice: 200 mercati per sottoscrizione, una sottoscrizione per connessione,
10 connessioni per app key (`frammenti_mercato.py:5-16`, `:85`; `safe_strategy/stream.py:3-8`, `:90-93`).

| # | Connessione | Dove si apre | Quante | Fonte |
|---|---|---|---|---|
| 1 | Mercato calcio, "frammenti" (frammento 0 + a caldo) | `Flumine.add_strategy(recorder)` -> `FrammentoMarketStream`; altri frammenti in `GestoreFrammenti._apri` | fino a `RUNNER_CALCIO_STREAM_CONNS` = **3** di serie, riserva 1 | `runner.py:2858-2867`, `frammenti_mercato.py:88,90`, `:477-506` |
| 2 | Order stream calcio | `BetfairClient(order_stream=True)` in `build_order_client` (LIVE: reale; PAPER: `SimulatedOrderStream`, nessuna connessione) | 1 (solo LIVE) | `runner.py:2123-2208`; `flumine/streams/simulatedorderstream.py:17-29` |
| 3 | Mercato tennis (UN solo stream cross-evento, filtro = tutti i Match Odds + mercati REC) | `framework.add_strategy(shared_cap)` | 1 (tetto 180 mercati) | `tennis_runner.py:3292-3294`, `iscrizione_a_caldo.py:65,89-102` |
| 4 | Order stream tennis | `build_order_client` tennis | 1 (solo LIVE) | `tennis_runner.py:144-183` |
| 5 | Scanner: pool di shard (`create_stream` di betfairlightweight diretto, senza flumine) | `StreamShard._run` | fino a `SAFE_STRATEGY_STREAM_CONNS` = **4** x 180 mercati | `safe_strategy/stream.py:81,407-421,461-492` |
| 6 | Scalper calcio: UNA SESSIONE-PROCESSO PER PARTITA con login e `Flumine` propri (market stream + order stream, `order_stream: True` anche in paper) | `scalper_service._spawn` -> `scalper_session.run_session` | N = partite con scalper acceso | `scalper_service.py:702-712`, `scalper_session.py:1324,1404,1786`, `:786-801` |
| 7 | Script `tennis_scalper/run_tennis_{pro,scalper}.py`, `record_*.py`: un login e un `Flumine` ciascuno, lanciati a mano | CLI | variabile | `run_tennis_pro.py:88,119`, `run_tennis_scalper.py:219,273` |

**Caso peggiore del solo codice a regime LIVE senza nessuna sessione scalper: 3 (calcio) + 1 (order calcio) + 1 (tennis)
+ 1 (order tennis) + 4 (scanner) = 10 = esattamente il limite per app key** (`frammenti_mercato.py:85`).
Ogni sessione scalper in piu' porta altre 1-2 connessioni. La difesa e' la riserva di 1 (`frammenti_mercato.py:90`)
e il valore `connectionsAvailable` letto dalla risposta di autenticazione (`frammenti_mercato.py:136-168,417-428`):
protegge solo il calcio, non scanner/scalper/tennis (che non lo leggono: non trovato in `safe_strategy/stream.py`,
`scalper_session.py`, `tennis_runner.py`). Misura reale sulla sessione del 02/10 (51 min): nel log del runner calcio
54 righe `MarketStream ...: SUCCESS`, 48 `sottoscrizione a caldo`, 4 `OrderStream ...: SUCCESS`; scanner 14 `MarketStream
SUCCESS` (`MISURE_2026-10-02.md:216-233`). Non distinguo da qui nuove connessioni da nuove sottoscrizioni sullo stesso
socket (lo `SUCCESS` e' la risposta a ogni subscribe): **non verificato**.

### 1.4 Parametri di sottoscrizione (conflateMs, heartbeatMs, filtri, segmentazione)

| Parametro | Runner calcio | Runner tennis | Scanner | Scalper sessione |
|---|---|---|---|---|
| `conflateMs` | `STREAM_CONFLATE_MS` = env `LIVE_STREAM_CONFLATE_MS`, default **0** -> `None` (`config_stream.py:87`, `runner.py:2864`) | **non passato**: la `_Capture` non imposta `conflate_ms`; `TENNIS_STREAM_CONFLATE_MS` (`tennis_runner.py:116`) e' **codice morto** (un solo riferimento in tutto il file: `grep -n STREAM_CONFLATE_MS`) | **1000** (`stream.py:66`, `:276`) | default flumine (None) |
| `heartbeatMs` | NON passato: `subscribe_to_markets` di flumine non lo accetta (`flumine/streams/marketstream.py:36-42`); decide Betfair, il listener legge il valore rimandato (`frammenti_mercato.py:141,157`) | NON passato | **5000** (`stream.py:65`, `:277`) | NON passato |
| Campi (`market_data_filter`) | `STREAM_FIELDS` = EX_ALL_OFFERS, EX_TRADED, EX_TRADED_VOL, EX_LTP, EX_MARKET_DEF, SP_TRADED, SP_PROJECTED; `ladder_levels=LADDER_DEPTH`=10 (`config_stream.py:47,90-98`) | `STREAM_FIELDS` **diversi**: EX_BEST_OFFERS, EX_LTP, EX_TRADED, EX_TRADED_VOL, EX_MARKET_DEF; depth 10 (`tennis_runner.py:103,119`, `:3248-3250`) | EX_BEST_OFFERS + EX_MARKET_DEF, `ladder_levels=1` (`stream.py:271-275`) | da `scalper_session.py` (filtro `marketIds`, `:1510`) |
| Filtro mercati | `streaming_market_filter(market_ids=<frammento0>)`; MAI filtri per evento/sport (un filtro vuoto = tutto l'exchange: avvertito in `scalper_session.py:1506-1508`) | `market_ids` = Match Odds seguiti + mercati delle partite REC, ordinati, sotto il tetto 180 (`tennis_runner.py:3292`, `mercati_registrati.py:73`) | `market_ids` dello shard (`plan_shards`) | `market_ids` della partita |
| Segmentazione | frammenti: <= 180 mercati/connessione (`auto_follow.tetto_mercati` -> `HARD_MARKET_CAP` 180, `config_stream.py:164`; `frammenti_mercato.py:357-376`), un mercato non cambia mai frammento finche' vivo (`:237-266`) | 1 connessione, 180 mercati (`iscrizione_a_caldo.py:65`) | shard stabili per `id mod N` (`stream.py:95-123`) | 1 connessione per partita |
| `streaming_timeout` | `None` in tutto il repo (flumine non ripete i book vecchi: `stream_muto.py:17-22`) | idem | n/a (non usa flumine) | idem |
| Latenza | `MAX_LATENCY = None` (warning silenziato: `raw_listener.py:315-325`); `tennis_recorder.py:329-340` idem | idem | `max_latency=None` (`stream.py:157`) | non verificato (default flumine `MAX_LATENCY = 0.5`, `basestream.py:13`, se non sovrascritto) |

Whitelist opzionale dei market type: `LIVE_MARKET_TYPES` (vuota = tutti, `config_stream.py:198-200`); la proposta a 14 tipi
(-39% mercati/evento, misura del 25/09: 19,8 -> 12,0 mercati/evento) e' dichiarata solo documentazione (`:193-197`), la
decisione e' dell'utente (`config_stream.py:170-192`).

### 1.5 Chi tiene la cache e quante copie dello stesso book esistono

Strati, dal socket in avanti, per UN aggiornamento di mercato nel runner calcio:

| # | Copia | Dove | Costo/natura | Fonte |
|---|---|---|---|---|
| 1 | Testo grezzo `mcm` | callback `on_data` del listener | stringa | `raw_listener.py:307-312` |
| 2 | Cache betfairlightweight `MarketBookCache` (dict per runner/prezzo) | dentro lo stream (`_caches`) | libreria | `betfairlightweight/streaming/stream.py:32,175-203` |
| 3 | Oggetto `MarketBook` completo (con tutti i runner/ladder) ricostruito A OGNI aggiornamento (`create_resource`) | consegnato a flumine, tenuto in `market.market_book` | libreria, non `lightweight` | `betfairlightweight/streaming/cache.py:360-380,604-620`; `flumine/baseflumine.py:133-178` |
| 4 | Tee raw: `json.loads` del messaggio + riserializzazione per evento + `flush()` per messaggio, nel thread del listener | file `<ev>.raw.jsonl` | disco sincrono | `raw_listener.py:151-241` (`:167`, `:221-222`) |
| 5 | `serialize_book`: dict compatto per mercato `{b,l,ltp,tv,trd}`, depth 10 e `trd` FULL, per OGNI mercato di OGNI aggiornamento, anche con registrazione spenta | `MarketRecorderStrategy._latest` | copia python | `recorder.py:50-88`, `:189-200` |
| 6 | jsonl curato per evento (opt-in, `json.dumps` + `write` + `flush` sotto lock, nel thread di flumine) | `<ev>.jsonl` | disco sincrono | `recorder.py:200-207` |
| 7 | `latest_books()` = `dict(self._latest)` (copia superficiale della mappa) per ogni consumatore | worker | copia leggera | `recorder.py:171-174` |
| 8 | `build_ladder_payload` ricostruisce selezioni con livelli normalizzati + WOM + firma SHA-1 | `ladder_worker` | copia python + hash | `runner.py:573-685` |
| 9 | JSON del push (`json.dumps({"t","d"})`) UNA volta per topic, poi invio a ogni client | `LocalChannel.publish` | stringa | `local_channel.py:620-672` (`:643`) |
| 10 | Riga `live_ladder` su Supabase (write-on-change, firma separata) | DB | rete | `runner.py:743-755`, `ladder_canale.py:130-160` |
| 11 | Frontend: ultimo push per mercato in `store.ladder` | browser | Map | `frontend/src/lib/localTransport.ts:34-38,93-96` |

Nel tennis le copie 5-8 esistono con codice gemello: `_Capture._latest` (`tennis_runner.py:408-492`) usa lo STESSO
`serialize_book` (`:56`, `:430`) e funzioni ladder duplicate (`:200-275`, §3 D3). Lo scanner ha una cache sua
(copia 2-3 dentro betfairlightweight direttamente, senza flumine), la converte GBP->EUR in `drain`
(`stream.py:384-405`), la trasforma in riga di scan (`service.py:1395-1513`) e la scrive.
**Consumatori veri di `latest_books`/`latest_for` in produzione (grep `git grep`): 8 punti** (`runner.py:282,327,356,477,709`,
`tennis_runner.py:1468,1526`, `xhedge_worker.py:57,60`): nessuno richiede il dict e non l'oggetto `MarketBook`
(non ho letto ogni uso: verifica da fare prima di eliminare la copia 5, vedi §6).

### 1.6 Come il book arriva ai bot e alla ladder della UI

- **Bot in-process flumine** (scalper maker/sniper/theta/media, 4 bot tennis, `LiveTradingStrategy`): ricevono il
  `MarketBook` direttamente da flumine, nello STESSO thread `handler_queue` che esegue anche la registrazione
  (`process_market_book` delle strategie e' chiamato in sequenza: `flumine/baseflumine.py:168-178`). Quindi
  `serialize_book` + `json.dumps` + `write/flush` del recorder (`recorder.py:189-207`) stanno nello stesso thread
  delle decisioni dei bot tennis (`_Capture` + bot nello stesso `Flumine`, `tennis_runner.py:3301-3336`).
- **Mike, Safe bot, Omega**: NON leggono lo stream. Leggono il feed unico `safe_strategy_scan`, scritto dallo scanner
  (upsert, freno 2,5 s: `service.py:159,2839-2855`; misura: 68 POST/min, `MISURE_2026-10-02.md:162`). Lettura: Mike
  `mike/db.py:560`, Safe `safe_strategy/bot_db.py:961`, Omega via `scan_feed`/`omega_service`, `auto_follow.py:474`,
  `scalper_service.py:110`, `scan_feed.py:417`. In parallelo esiste un canale locale dello scanner (porta **47336**, topic
  `scan_calcio`, `scan_tennis`, `scanner_stato`: `service.py:91-94,2441-2518`) con lettori `canale_scan.py` per Safe
  (`SAFE_BOT_LEGGE_CANALE`), `MIKE_LEGGE_CANALE` (mike/service.py:7030, "SPENTO di serie" `:6998`), `OMEGA_LEGGE_CANALE`
  (omega_service.py:564), `PUNTEGGI_CANALE` (`scan_feed.py:102`). Lo stato effettivo di questi interruttori nel `.env` NON
  e' stato letto (vincolo del brief): nel codice sono spenti di serie o attivabili per processo.
- **Ladder della UI**: `ladder_worker` (BackgroundWorker) gira ogni `max(20 ms, min(LADDER_CANALE_MS=200 ms, LADDER_PUBLISH_SEC=2 s))`
  = **200 ms di serie** (`ladder_canale.py:46,103-105`, `config_stream.py:60,74`, `runner.py:3011-3016`); a ogni giro costruisce il
  payload dei mercati la cui firma e' cambiata (`runner.py:733-742`) e fa `_lc.publish("ladder", row)` verso
  `127.0.0.1:47331` (calcio) / `47332` (tennis), WebSocket JSON `{"t":"ladder","d":{event_id,market_id,market_type,market_name,status,ladder:{updated_ms,selections[]}}}`
  (`local_channel.py:6-17,620-672`, `localTransport.ts:177-184`). Nessuna rete verso il DB nel push; il DB (`live_ladder`,
  `tennis_live_ladder`) riceve la stessa riga ogni 2 s write-on-change DALLO STESSO THREAD (`runner.py:748-755`,
  `tennis_runner.py:1495-1500`). Il frontend usa il canale come via principale e il realtime DB come ripiego
  (`localTransport.ts:172-176`), scarta righe con `updated_ms` non piu' fresco (`piuFresca`).
- **Protocollo/porte** (tabella unica, `grep` dei `start_channel`/`_PORTA`): 47330 UI statica (`desktop/main.js:27`),
  **47331 calcio** (`runner.py:2640`), **47332 tennis** (`tennis_runner.py:3157`), 47333 Mike (`mike/service.py:6784`),
  47334 Omega (`omega_service.py:8587`), 47335 Safe bot (`bot_service.py:10569`), 47336 scanner (`service.py:91`),
  47337 4 bot tennis / ponte (`canale_bot.py:135`), 47338 scalper (`canale_bot.py:142`). Otto server WebSocket in otto
  processi; solo 47331/47332 accettano comandi `order` (con token di sessione + origine: `local_channel.py:36-72,305-330,451-500`).
  Backpressure per client: tetto 64 invii in volo, il giro si salta (non si accumula): `local_channel.py:176,636-672`.

### 1.7 Riconnessione, sessione che scade, keepAlive

- **Riconnessione stream**: flumine `MarketStream.run` con `@retry(wait_exponential(2..60))` ripassa `initial_clk` e `clk` del
  listener (`flumine/streams/marketstream.py:15,36-42` [corretto dal verificatore 08/10: il `@retry` e' a `:15`, non `:12`]; `basestream.py:14`), cioe' ripresa dalla posizione. Il calcio la
  replica a mano in `FrammentoMarketStream.run` (backoff `2**n` limitato a 60 s, nessuna riconnessione dopo `stop`:
  `frammenti_mercato.py:185-226`). **Lo scanner NON usa questo meccanismo**: a ogni riconnessione fa `create_stream` +
  `subscribe_to_markets` senza `initial_clk`/`clk` (`safe_strategy/stream.py:418-427`), cioe' ricostruisce l'immagine
  piena; backoff (2, 5, 10, 30 s) `:63,448-460`.
- **Subscription a caldo** (nuove partite senza abbattere la connessione): calcio `sottoscrizione_a_caldo.py:75-113`
  (nuova `marketSubscription` sullo stesso socket, cambia `stream.market_filter` perche' la riconnessione di flumine lo riusi),
  tennis `iscrizione_a_caldo.py` + `tennis_runner.py:2488-2750`, scanner `stream.py:229-309` (throttle 30 s, tolleranza 25 mercati
  usciti). Soft restart = **ricostruzione dell'intero `Flumine`** (nuovo framework, nuovo blotter): `runner.py:1194-1266`,
  rinviata se ci sono ordini vivi (`_lifecycle_blockers`, `:1267-1335`).
- **Stallo**: soglia 3x heartbeat (calcio: valore rimandato da Betfair; altrove 3 x 5000 ms: `stream_muto.py:35-45`); frammento
  MUTO > 180 s chiuso e ripiazzato (`frammenti_mercato.py:97,577-627`); ricostruzione del framework, poi se ancora muto uscita del
  processo e rilancio dal watchdog (`runner.py:1361-1432`, `LIVE_STALL_POST_REBUILD_SEC=180`: `:1325`); tennis `tennis_runner.py:2182-2352`.
- **Sessione** (.it: 1200 s, `auth.py:98-101`; per Betfair solo keepAlive/login la prolungano, `auth.py:100-101`):
  `CustodeSessione` (`auth.py:156-286`, keepAlive ogni 480 s calcio/tennis `runner.py:1319`, 600 s scalper, 900 s scanner
  `service.py:173`; backoff 15/30/60; login dopo errore di sessione o al 90% di vita). Dopo un relogin, il runner ricostruisce lo
  stream (`runner.py:1443-1460`). In piu' **flumine ha il suo `keep_alive` di default** (`flumine/flumine.py:68-79`,
  `worker.py:99-116`: periodo = min(timeout/2, 1200) = 600 s) che fa `client.login()` se la keepAlive fallisce: tre
  meccanismi di keepAlive sullo stesso `APIClient` nel runner (flumine, custode, ramo idle `runner.py:2788-2806`).
- **REPERTO**: la sessione JSON-RPC `rest` del runner calcio (`BetfairClient`, `runner.py:2618-2619`) e' loggata UNA volta e
  non ha ne' keepAlive ne' re-login (`client.py` non ha alcun percorso di re-login; unico `login_cert` nel runner `:2619`;
  `git grep` conferma). Il commento `runner.py:2802-2803` dice che la tiene viva `resolve_and_register` ogni 15 s, mentre
  `auth.py:100-101` dice che le chiamate API non prolungano la sessione: i due commenti si contraddicono. Rischio da provare
  dal vivo (non fatto: nessuna chiamata a Betfair).
- Percorso ordini REST di Omega/Mike/Safe: sessione condivisa `odds_refresh.get_shared_client()` con `_reset_client` e un
  solo re-login su errore (`odds_refresh.py:60-102`; `omega_market.py:68-112`): terza famiglia di gestione sessione.

### 1.8 Ripieghi REST (listMarketBook / catalogo) e quando scattano

| Dove | Cosa | Quando | Fonte |
|---|---|---|---|
| Scanner | `listMarketBook` EX_BEST_OFFERS a chunk di 25 con pausa 0,35 s, per i mercati "non coperti" dallo stream | per sport, a cadenza `books_period_calcio/tennis` quando `now - books_ts > periodo` e il mercato non e' servito dallo stream (`serving()` 20 s) | `safe_strategy/service.py:1672-1689,3070-3092,174,176`; `scanner.py:535-544`; `stream.py:318-330` |
| Board del giorno | `listMarketBook` di ripiego per eventi NON coperti dallo scanner | ogni 60 s (KO lontano); catalogo del giorno 1 chiamata / 300 s; a costo zero senza client desktop | `board_worker.py:1-28,165-212` |
| Runner calcio | `listMarketCatalogue` per evento (`fetch_event_markets`, maxResults 1000) | `_catalog_events` a ogni ricostruzione/aggancio nuovo (non c'e' un poll periodico nostro) | `runner.py:136-171,2047-2122` |
| flumine (default) | `poll_market_catalogue` ogni 60 s, `poll_account_balance` 120 s, `poll_market_closure` 60 s | sempre, per tutti i mercati sottoscritti | `flumine/flumine.py:80-110`; nel log 02/10: 343 `Updated marketCatalogue` + 168 `Created` in 51 min (`MISURE:217-218`) |
| Runner tennis | `list_market_catalogue` per evento e REC | alla risoluzione del follow / ricostruzione | `tennis_runner.py:744-833`, `mercati_registrati.py:42-66` |
| Prodotto | "Aggiorna quote" per fixture (REST, tabella `betfair_market_odds`) | su richiesta da coda `betfair_refresh_requests` (poll 2 s) | `refresh_worker.py:31-99`, `odds_refresh.py:206-263` |

I ripieghi dello scanner portano un segnale `FEED_RIPIEGO_REST`/`FEED_RIENTRO_STREAM` (nel log: 2 + 2 in 51 min, `MISURE:232-233`).
Il segnale "il prezzo e' vivo" per mercato (`flusso`) e' prodotto solo dallo scanner (`flusso_prezzi.py:1-60`).

### 1.9 Verifica delle ipotesi di §4 del brief del piano contro il codice

| Ipotesi (§4) | Esito sul codice |
|---|---|
| «una sola connessione stream per sport (calcio e tennis con lo stesso codice)» | **Smentita per il calcio**: la sottoscrizione e' limitata a 200 mercati (`sottoscrizione_a_caldo.py:40`) e il runner calcio e' gia' a frammenti (fino a 3 connessioni, `frammenti_mercato.py:88`) perche' il 26/09 una connessione da 180 mercati era satura 179/180 e 24 partite idonee restavano fuori (`:1-9`). Il tennis e' gia' a 1 connessione. Vedi §4.1. |
| «cache in memoria = il `MarketBook` di betfairlightweight/flumine, senza copie» | **Parzialmente vera**: flumine/bfl gia' tengono il `MarketBook` (copie 2-3 della §1.5). Le copie 4-10 sono nostre. Eliminabili 5 e 7-8 solo dopo aver verificato che i consumatori non dipendano dal formato dict. |
| «ladder servito ai consumatori locali senza rete» | **Gia' vera dal 23/09** per il push (canale 127.0.0.1, 200 ms: `config_stream.py:60-74`); resta rete (Supabase) nello stesso thread dei push (D5). |
| «nessuna chiamata di rete fra il messaggio di Betfair e la decisione del bot» | **Vera per i bot in-process** (nessuna rete in `process_market_book` del recorder/capture: `recorder.py:189-207`, `tennis_runner.py:428-431`); **falsa per Mike/Safe/Omega** che decidono su righe lette dal DB (`mike/db.py:560`) con eta' = freno 2,5 s dello scanner + poll (se il canale 47336 e' spento). |

---

## 1.10 Tabelle del DB lette/scritte dal componente (con misura)

Fonte misura: `MISURE_2026-10-02.md` (finestra 60 s fino alle 15:16:40 UTC del 02/10; totale app 1.309 chiamate/min).
Chiamate dal `chiamate_py.tsv` (`dati_g1/uscite`).

| Tabella | Scrive/legge | Dove | Frequenza misurata |
|---|---|---|---|
| `safe_strategy_scan` | scrive (upsert) | `safe_strategy/db.py:198` via `service.py:2839-2855` | **68 POST/min** (scanner) |
| `safe_strategy_scan` | legge | `scan_feed.py:417` (runner), `mike/db.py:560`, `bot_db.py:961`, `auto_follow.py:474`, `scalper_service.py:110` | runner calcio 8 GET/min; scanner 1/min |
| `safe_strategy_status` | scrive/legge | `service.py:2856+`, `scan_feed.py:407` | 5 POST/min; runner 2 GET/min |
| `live_ladder` / `tennis_live_ladder` | scrive (upsert, write-on-change, 2 s) | `runner.py:752`, `tennis_runner.py:1498` | non misurata (finestra senza partite seguite: **non verificato**) |
| `live_follow` / `tennis_live_follow` | legge (poll 2 s) | `subscription_worker` `runner.py:982` | **29 GET/min** calcio, **28 GET/min** tennis |
| `betfair_live_heartbeat` | scrive | `heartbeat_worker` `runner.py:1583` | 8 POST/min |
| `betfair_market_odds`, `fixture_predictions` | scrive/legge | `odds_refresh.py:178,224,254,257` | a richiesta |
| `betfair_refresh_requests` | legge/aggiorna (poll 2 s) | `refresh_worker.py:38,59,66,73` | non nella finestra |

Il percorso messaggio -> decisione dei bot in-process **non tocca nessuna tabella**. Sul percorso ladder->UI il DB e' toccato
nello stesso thread (D5).

### 1.11 Orologi, thread, processi, stato condiviso

- Thread per stream (calcio e tennis): listener (socket) + `_output_thread` per stream + handler di flumine + un
  `BackgroundWorker` per worker. Calcio: 14 worker nostri (`runner.py:2970-3058`: live_order 1,0 s; risk_engine 1,0;
  xhedge 5; daily_stop 5; reconcile 30; score 5; **ladder 0,2**; finalize 10; board 10; heartbeat 10; sync_account 10;
  lifecycle 60; arresto 1,0; subscription 2,0) + 4 default di flumine (keep_alive 600, catalogue 60, balance 120, closure 60) +
  thread `uploader-sweep` 300 s (`runner.py:2606-2616`) + `local-ws-47331` (`local_channel.py:279`).
- Processi (A): runner calcio, runner tennis, scanner (`safe-strategy-service`), N sessioni scalper; 4 servizi bot leggono.
- Stato condiviso: `LiveSession` (`runner.py:174-250`), `RAW_STATE` singleton (`raw_listener.py:300-301`), `RAW_TEE` tennis,
  singleton `_CHANNEL` per processo (`local_channel.py:717-740`), cache `ScanRowCache` per processo (`scan_feed.py:430`).
- Misura del feed (40 registrazioni reali, 1.071.944 messaggi, 4.928 min, 277,5 MB): intervallo fra messaggi in-play
  p50 105 ms, p95 425 ms, p99 971 ms; per-mercato in-play p50 306 ms, p95 3.518 ms (`m01_feed_raw.txt`, ultime righe);
  4-5 msg/s per partita; betDelay osservato in-play 5 s.

---

## 2. Funzionalita'

Legenda: **[UI]** visibile nella UI (file); **[P]** parametro (tutti i parametri di A sono ENV del `.env`/processo: nessuno e'
editabile dalla UI, `getenv` in `config_stream.py`); **[$]** money-critical; **[conf.]** confine con altra scheda.

### 2.1 Sessione e REST
- A-001 Login certificato .it con `APIClient` (locale `italy`, `requests.Session` riusata: 1 handshake invece di 1 per chiamata, misura 09/09 nel commento) - `auth.py:31-80`.
- A-002 `keep_alive` best-effort senza token nei log - `auth.py:83-93`.
- A-003 Riconoscere errore di sessione (INVALID_SESSION_INFORMATION/NO_SESSION) risalendo le cause - `auth.py:116-134`.
- A-004 Descrizione errore senza mai il token - `auth.py:136-153`.
- A-005 **CustodeSessione**: keepAlive per periodo, backoff 15/30/60 s, login se sessione morta o al 90% della vita (1200 s), contatori `stato()` - `auth.py:156-286` [$ indiretto].
- A-006 `safe_logout` - `auth.py:288-294`.
- A-007 Login cert JSON-RPC nostro, 3 tentativi, `sleep 2**n` bloccante - `client.py:95-157`.
- A-008 `_rpc`/`betting_rpc`/`account_rpc`: retry 3 con sleep fino a 8 s bloccanti nel thread chiamante - `client.py:180-257`.
- A-009 `list_events` (ora o `from_date` indietro per eventi gia' iniziati) - `client.py:259-280`.
- A-010 `list_market_catalogue` (proiezioni di default) - `client.py:282-304`.
- A-011 `list_market_book` (EX_BEST_OFFERS, virtualise) - `client.py:306-327`.
- A-012 `place_orders` [$] - `client.py:329-359` (usato da Omega/Mike: `omega_market.py:788,1131`).
- A-013 `list_current_orders` / A-014 `list_cleared_orders` - `client.py:361-425`.
- A-015 Account API (saldo ecc.) - `client.py:193-201`, `omega_market.py:126`.
- A-016 Sessione REST condivisa per processo con re-login su errore e stop pulito al limite (`BetfairLimitHit`) - `odds_refresh.py:48-102`.
- A-017 `refresh_fixture_odds`: quote complete per UNA fixture (percorso A: market_id gia' associati; B: abbinamento 1:1 money-safe), delete+insert per fixture/giorno, lock di processo - `odds_refresh.py:105-263` [UI: pulsante "Aggiorna quote" della watchlist, `odds_refresh.py:3-5`; il file del pannello NON verificato].
- A-018 Worker coda `betfair_refresh_requests` (poll `LIVE_REFRESH_QUEUE_POLL_SEC` 2 s, batch 5) - `refresh_worker.py:35-99` [P].
- A-019 Cambio GBP->EUR delle size dello stream, UN punto (`MiddlewareValutaEur` primo middleware flumine; `converti_libro` per lo scanner), cache su disco, rinfresco orario - `valuta.py:1-349`, `runner.py:2623,2896`, `stream.py:398-401` [$].

### 2.2 Stream calcio
- A-020 Stato di sessione condiviso (mapping `market_to_event`, `event_markets`, nomi selezione, lambda pre-match, eventi finiti) - `runner.py:174-250`.
- A-021 Catalogo REST di tutti i mercati dell'evento con whitelist opzionale - `runner.py:136-171`, `config_stream.py:198-200` [P `LIVE_MARKET_TYPES`].
- A-022 `_catalog_events`: scarica il catalogo per i follow, rilettura per fine partita e catalogo vuoto - `runner.py:1883-2122`.
- A-023 Elenco mercati manuali vivi da sottoscrivere; rilascio dei mercati finiti - `runner.py:838-905`.
- A-024 Piano del frammento 0 (prima i mercati con soldi, poi i manuali, tetto per connessione) - `runner.py:2375-2452`, `frammenti_mercato.py:268-291`.
- A-025 Costruzione del `MarketRecorderStrategy` con `FrammentoMarketStream`, `STREAM_FIELDS`, depth, conflate - `runner.py:2858-2880` [P `LIVE_STREAM_CONFLATE_MS`, `LIVE_LADDER_DEPTH`].
- A-026 Client flumine per modo OFF/PAPER/LIVE (`order_stream`, `paper_trade`, `min_bet_validation=False`, `transaction_limit`) - `runner.py:2123-2208` [$, conf. C].
- A-027 Client PAPER affiancato al reale (stesso stream, nessuna connessione in piu') - `runner.py:2210-2228`, `client_paper_affiancato.py:1-53` [$].
- A-028 Stream condiviso fra recorder e strategie ordini (`kwargs_stream_condiviso`: stesso filtro/data_filter, o flumine aprirebbe un'altra connessione) - `frammenti_mercato.py:312-332`, `runner.py:2930-2939`.
- A-029 **GestoreFrammenti**: apre/chiude frammenti a caldo, riserva di connessioni, pausa 300 s dopo rifiuto, attesa apertura 60 s, chiusura se vuoto, `stato()` - `frammenti_mercato.py:346-665` [UI: capacita' mercati `RigaCapacitaMercati.tsx:9` dal canale 47331] [P `RUNNER_CALCIO_STREAM_CONNS`, `RUNNER_CALCIO_STREAM_RISERVA`].
- A-030 Piano puro dei frammenti: un mercato non cambia frammento finche' il frammento e' vivo - `frammenti_mercato.py:237-266`.
- A-031 Battito per connessione (qualunque messaggio, heartbeat inclusi), `heartbeatMs` e `connectionsAvailable` letti dalla risposta - `frammenti_mercato.py:120-183`.
- A-032 Riconnessione `FrammentoMarketStream` con ripresa `initialClk/clk`, mai dopo `stop` - `frammenti_mercato.py:185-226`.
- A-033 Frammento muto > 180 s chiuso e mercati ripiazzati; mercati con ordini protetti - `frammenti_mercato.py:293-310,577-627`.
- A-034 Sottoscrizione a caldo (nuova subscription sullo stesso socket, id previsto, filtro canonico) - `sottoscrizione_a_caldo.py:60-113`.
- A-035 `subscription_worker`: poll `live_follow` ogni 2 s, debounce 20 s, intervallo minimo 60 s fra ricostruzioni, aggancio a caldo e follow manuali nuovi - `runner.py:982-1193` [P `LIVE_SUB_WORKER_POLL_SEC`, `LIVE_RESUBSCRIBE_DEBOUNCE_SEC`, `LIVE_MIN_RESUBSCRIBE_INTERVAL_SEC`].
- A-036 Soft restart con ri-verifica dei blocker (ordini vivi, regole armate) e stop reale del framework - `runner.py:1194-1335`.
- A-037 Attesa su errore di rete (non crash) - `runner.py:1336-1348`.
- A-038 Sorveglianza del flusso: battito dati/heartbeat, stallo, ricostruzione, escalation a riavvio processo con alert CRITICAL - `runner.py:1361-1432,1513-1582`, `stream_muto.py`, `runner_lifecycle.py:87-224` [$].
- A-039 `heartbeat_worker`: battito del runner su `betfair_live_heartbeat`, keepAlive del custode, relogin -> ricostruzione - `runner.py:1583-1767`, `:1433-1460`.
- A-040 keepAlive nel ramo idle (nessun evento) ogni 480 s - `runner.py:2788-2806`.
- A-041 Auto-spegnimento e arresto ordinato (conf. I) - `runner.py:1768-1846`.
- A-042 Mercati con soldi dallo specchio e dal blotter nel frammento 0 - `runner.py:2384-2422`, `frammenti_mercato.py:293-310`.
- A-043 Canale locale 47331 con `hello` del modo ordini - `runner.py:2640-2642`.

### 2.3 Registrazione e cache
- A-044 `serialize_book` (compatto `b,l,ltp,tv,trd` + `valuta`) - `recorder.py:50-88`.
- A-045 `MarketRecorderStrategy`: cache `_latest`, jsonl curato opt-in per evento (`record_events`), contatori - `recorder.py:89-208`.
- A-046 Rilevamento fine partita (`process_closed_market`: MATCH_ODDS chiuso o tutti chiusi) e coda `drain_finished` - `recorder.py:209-240`.
- A-047 Tee raw nativo `mcm` per evento con gating opt-in, sidecar `.recmeta.jsonl` (open/close/resubscribe/record_toggle), self-heal della scrittura, salute - `raw_listener.py:29-290` [UI: opt-in "Segui live" -> registra; conf. G].
- A-048 Contatori di salute del tee (heartbeat, ultimo dato) anche a registrazione spenta - `raw_listener.py:151-165,139-149`.
- A-049 `RawTeeStreamListener`/`RawTeeMarketStream` (`MAX_LATENCY=None`) - `raw_listener.py:304-325`.
- A-050 Tee tennis `TennisRawTee`: raw + sidecar punteggio (`write_score`) + programmazione replay - `tennis_recorder.py:68-317`.
- A-051 `TennisRecMarketStream`/listener, `sync_record_flags` - `tennis_recorder.py:318-384`.

### 2.4 Ladder, board, canali
- A-052 Ladder helper: livelli normalizzati, WOM (Weight of Money rosa/blu), selezione, firma SHA-1, payload - `runner.py:573-685` (e gemelli `tennis_runner.py:200-275`) [UI: ladder, WOM] [P `LIVE_LADDER_MAX_LEVELS`, `LIVE_LADDER_WOM_LEVELS`].
- A-053 `ladder_worker` a due cadenze: canale a `LADDER_CANALE_MS`, DB a `LADDER_PUBLISH_SEC`, firme separate, status nella firma, salta il giro senza client - `runner.py:687-757` [P `LIVE_LADDER_CANALE_MS`, `LIVE_LADDER_PUBLISH_SEC`].
- A-054 `StatoLadder` (cadenza, versione per identita' dell'oggetto book, `updated_ms` strettamente crescente) - `ladder_canale.py:73-168`.
- A-055 `build_live_state` (live_now: back/lay/ltp per mercato + modo ordini) e `ladder_by_market` - `runner.py:280-342` [conf. B/J].
- A-056 `board_worker`: board del giorno sul canale, prezzi dal feed, ripiego REST a 60 s, costo zero senza client - `board_worker.py:49-230` [UI: board].
- A-057 Server WebSocket locale: bind 127.0.0.1, origine e token, topic per lettori, hello, comandi `order`/`snapshot` -> coda drenata dal thread ordini, backpressure per client - `local_channel.py:203-767` [UI: tutta la Control Room].
- A-058 `canale_bot`: righe dei bot (dopo la scrittura DB riuscita) su canale, interruttore per processo - `canale_bot.py:1-426`, porte `:135,:142` [UI: Control Room, `useControlRoom.ts:151,675`].
- A-059 `canale_bot_tennis`: inoltro posizioni runner->ponte (47337) e sveglia del `bot_control_worker` - `canale_bot_tennis.py:1-357`.
- A-060 `esiti_ordini_canale`: esiti TERMINALI degli ordini dal canale 47331, mai piu' vecchi - `esiti_ordini_canale.py:1-850` [$ indiretto, conf. C].
- A-061 `sveglia_canale`: sveglia i cicli di Mike/Omega/tennis con pavimento (le letture al minuto non crescono) - `sveglia_canale.py:1-390`.
- A-062 Parametri di stream/ladder/limiti in `config_stream.py` (tetto 180/150, whitelist, backoff) - `config_stream.py:24-339`.

### 2.5 Stream tennis
- A-063 Sessione tennis (follow, catalogo, `market_meta`, capture) - `tennis_runner.py:520-628`.
- A-064 Risoluzione mercato per follow via `list_market_catalogue`; `MercatoNonInCatalogo` - `tennis_runner.py:629-846`.
- A-065 Client ordini tennis OFF/PAPER/LIVE e latenza paper `TENNIS_PAPER_LATENCY_MS` (default 600) - `tennis_runner.py:119-183`, `paper_execution.py:1-113` [$].
- A-066 `_make_capture`: UNA capture per tutti gli eventi (stream unico cross-evento), `latest_for`, chiusura CLOSED - `tennis_runner.py:408-492`.
- A-067 Capture ordini per modalita' (paper/live mai sommati, stesso stream) - `tennis_runner.py:493-518` [$].
- A-068 Costruzione framework: `data_filter`, `shared_cap`, verifica `STREAM DUPLICATO` dei bot - `tennis_runner.py:3247-3336`.
- A-069 `ladder_worker` tennis (canale + `tennis_live_ladder`) - `tennis_runner.py:1455-1507`.
- A-070 `now` tennis (`tennis_live_now`, punteggio+book) - `tennis_runner.py:1523-1570` [conf. B].
- A-071 keepAlive del custode nel runner tennis - `tennis_runner.py:1580-1610`.
- A-072 Sorveglianza flusso tennis, stall_worker, escalation - `tennis_runner.py:2182-2352` [$].
- A-073 Iscrizione e armamento a caldo (nuova partita senza ricostruire; bot armati nel framework vivo) - `tennis_runner.py:2353-2750`, `iscrizione_a_caldo.py:80-322` [P `TENNIS_ISCRIZIONE_A_CALDO`, `TENNIS_TETTO_MERCATI`].
- A-074 Mercati registrati (REC): tutti i mercati dell'evento nella STESSA sottoscrizione, i Match Odds mai espulsi - `mercati_registrati.py:42-95`, `tennis_runner.py:2751-2857` [UI: interruttore REC].
- A-075 Canale locale 47332 - `tennis_runner.py:3157`.

### 2.6 Scanner e feed unico
- A-076 Pool di shard con piano stabile, resubscribe a caldo (30 s), backoff, salute `healthy()` e `serving()` - `safe_strategy/stream.py:95-123,161-567`.
- A-077 Conferma del flusso per mercato (503 = latenza, heartbeat, REST) - `stream.py:343-361,541-557`, `flusso_prezzi.py`, `service.py:909-1087`.
- A-078 Ripiego REST `poll_books` con cadenze per sport - `service.py:1672-1689,3070-3092`.
- A-079 Pubblicazione `safe_strategy_scan` (write-on-change, freno 2,5 s) e `safe_strategy_status` - `service.py:2531-2723,2839-2932` [UI: stato scanner `useControlRoom.ts:971`].
- A-080 Canale dello scanner 47336 (topic `scan_*`, `scanner_stato`) - `service.py:2441-2530`.
- A-081 Custode dello scanner e catena `FEED_RIPIEGO_REST` - `service.py:555`, `:173`.
- A-082 Lettore del feed per i runner: cache per processo (TTL 1 s), una SELECT per ciclo, freschezza 15 s / 180 s, fusione col canale - `scan_feed.py:35-476`.
- A-083 Provider punteggi da feed (conf. B) - `scan_feed.py:478-540`.

### 2.7 UI e desktop (consumatori)
- A-084 Sorgente ladder composita canale+DB, cache per mercato, `piuFresca`, invalidazione alla disconnessione - `localTransport.ts:9-38,93-150,223-250,311-375`.
- A-085 Canali per bot in Control Room (47333-47338) con overlay sul giro di 30 s - `useControlRoom.ts:7,151,675,962-971`.
- A-086 Token e origine del canale generati da `desktop/main.js` (porta UI 47330) - `main.js:27,50`, `local_channel.py:36-72`.

Totale funzionalita' elencate: **86**.

---

## 3. Difetti strutturali

Per ogni difetto: evidenza e conteggio con lo strumento.

**D1. Tre stack di stream, tre politiche di riconnessione.** (a) flumine `MarketStream` (runner, tennis, scalper): ripresa con `initialClk/clk` (`marketstream.py:36-42`); (b) il calcio riscrive la `run` per i frammenti (`frammenti_mercato.py:185-226`); (c) lo scanner usa `create_stream` diretto e a ogni riconnessione riparte da immagine piena (`stream.py:418-427`). Tre posti dove cambiare backoff e salute.

**D2. Calcio e tennis: righe gemelle misurate (difflib, `a_gemelle_connessione_output.txt`).**
- File: `runner.py` (1.965 righe di codice) vs `tennis_runner.py` (2.345): **9,1% / 7,6%** uguali a blocchi. Il file intero e' poco gemello; lo sono le funzioni:

| Funzione | Calcio | Tennis | Righe cod. | ratio |
|---|---|---|---|---|
| `_as_levels` | `runner.py:573` | `tennis_runner.py:200` | 14 / 14 | 0,93 |
| `compute_wom` | `runner.py:594` | `tennis_runner.py:216` | 13 / 10 | 0,70 |
| `build_ladder_selection` | `runner.py:617` | `tennis_runner.py:229` | 19 / 15 | 0,76 |
| `ladder_signature` | `runner.py:643` | `tennis_runner.py:260` | 12 / 11 | 0,78 |
| `build_ladder_payload` | `runner.py:667` | `tennis_runner.py:247` | 13 / 10 | 0,70 |
| `ladder_worker` | `runner.py:687` | `tennis_runner.py:1455` | 49 / 43 | 0,54 |
| `_stop_framework` | `runner.py:1224` | `tennis_runner.py:3015` | 7 / 7 | 0,71 |
| `arresto_worker` | `runner.py:1768` | `tennis_runner.py:2074` | 7 / 8 | 0,80 |
| `lifecycle_worker` | `runner.py:1783` | `tennis_runner.py:2125` | 40 / 29 | 0,43 |
| `_stato_fine` / `_fine_dimentica` | `runner.py:1927,1940` | `tennis_runner.py:676,687` | 9 / 9, 4 / 4 | **1,00 / 1,00** |
| `build_order_client` | `runner.py:2123` | `tennis_runner.py:144` | 31 / 15 | 0,17 |
| `setup_and_run` | `runner.py:2599` | `tennis_runner.py:3121` | 313 / 261 | 0,20 |
| `_main` | `runner.py:3149` | `tennis_runner.py:3465` | 14 / 14 | 0,50 |

  Con stesso nome ma NON gemelli per testo (ratio < 0,25) e' lo scheletro `setup_and_run` (login -> catalogo -> stream -> worker -> `framework.run` -> restart): stessa sequenza, 574 righe di codice in due copie.
- `raw_listener.py:29` (`_RawState`) vs `tennis_recorder.py:68` (`TennisRawTee`): **35,6% / 29,0%** uguali; `write_message` 69 / 64 righe, ratio 0,60 (`raw_listener.py:151`, `tennis_recorder.py:148`).
- Altri nomi-gemelli per concetto, senza funzioni omonime: `sottoscrizione_a_caldo.py` (113) / `iscrizione_a_caldo.py` (322); `watchlist.py` / `mercati_registrati.py`; `canale_bot.py` / `canale_bot_tennis.py` (6,8% di testo uguale, `a_gemelle_connessione_output.txt`).
- Stream diversi per volonta' (non gemelli): campi (EX_ALL_OFFERS+SP_* calcio vs EX_BEST_OFFERS tennis, §1.4).

**D3. Canali: cinque moduli con la stessa disciplina, poco testo comune.** `canale_bot` 426 righe (190 di codice), `esiti_ordini_canale` 850 (556), `sveglia_canale` 390 (243), `canale_scan` 529 (303), `canale_bot_tennis` 357 (210) = 1.502 righe di codice; testo uguale a coppie fra 3,6% e 29,5% (`a_gemelle_canali_output.txt`). Il comune e' il COSTRUTTO (interruttore per processo spento di serie, "database resta registro", mai piu' vecchio, canale muto non ha effetto - docstring di tutti e cinque), non il codice: non e' un taglio testuale facile.

**D4. Fino a 11 copie dello stesso book** (§1.5), di cui 6 nostre in memoria/JSON e 2 su disco, due delle quali (4 e 6) con `flush()` per messaggio in thread di decisione (4: thread del listener; 6: thread di flumine, lo stesso dei bot). `serialize_book` e' eseguito per OGNI mercato di OGNI aggiornamento anche a registrazione spenta (`recorder.py:189-200`: `record = serialize_book(...)` prima di `_is_recording`). Costo CPU: non misurato (strumento proposto in §7).

**D5. Ladder: canale e DB nello stesso thread.** `ladder_worker` pubblica sul canale e poi fa `db.upsert_live_ladder` sincrono sullo stesso loop dei mercati (`runner.py:743-755`; tennis `:1495-1500`): un upsert Supabase lento ritarda il push degli altri mercati dello stesso giro. Inoltre il push e' a polling (200 ms), non guidato dall'evento; la sorgente e' una ricostruzione completa del payload con `trd` FULL (`runner.py:604-606`) a ogni cambio di firma.

**D6. Due sessioni Betfair nello stesso processo calcio** (`BetfairClient` + `APIClient`, `runner.py:2618-2620`), con politiche di sessione diverse (la prima senza keepAlive/re-login: §1.7 REPERTO). Conteggio dei punti di login nel codice di produzione: `build_client(login=True)` **12 punti** (`git grep`: safe_strategy/service.py:3367, runner.py:2620, scalper/{habitat_scan:89, run_scalper_live:230, scalper_service:887, scalper_session:1404}, tennis_runner.py:3122, tennis_scalper/{backtest_pro:81, record_multi:280, record_tennis:41, run_tennis_pro:88, run_tennis_scalper:219}; piu' 1 in `laboratorio/`) + `BetfairClient()` **6 punti** (`betfair_report_manager.py:68`, `odds_refresh.py:66`, `runner.py:2618`, 3 script di radice). Ogni sessione scalper = un login in piu' (`scalper_session.py:1404`).

**D7. Quota connessioni al limite per costruzione** (§1.3): 10/10 nel caso peggiore senza scalper; la riserva e `connectionsAvailable` sono letti solo dal calcio.

**D8. Parametri morti o impliciti.** `TENNIS_STREAM_CONFLATE_MS` mai usato (`tennis_runner.py:116`); `heartbeatMs` non richiesto su 3 dei 4 stack (decide Betfair, `stream_muto.py:20-31` [corretto dal verificatore 08/10: era `:35-45`, dove c'e' la soglia di stallo, non la richiesta dell'heartbeat]); `STREAM_FIELDS` duplicato e diverso (`config_stream.py:90`, `tennis_runner.py:119`); `LADDER_DEPTH` letto da due env diverse (`config_stream.py:47`, `tennis_runner.py:103`).

**D9. "Lo stream e' muto?" in 4 implementazioni:** `runner.py:1513-1582` (`_sorveglia_flusso_runner`), `tennis_runner.py:2219-2280`, `stream_muto.py` (292 righe: duck typing), `frammenti_mercato.py:577-627` (battito per frammento) e, per lo scanner, `stream.py:310-361` + `flusso_prezzi.py`. Stesse soglie (3 x heartbeat, 180 s) ripetute come costanti.

**D10. Ricostruzione del framework come rimedio unico** a stallo e relogin (`runner.py:1194-1266,1443-1460`): un relogin con ordini vivi viene rinviato (`:1267-1335`) mentre la sessione dello stream puo' essere scaduta. Il codice lo dichiara come finestra accettata ("finestra residua DICHIARATA", `:1202-1203`).

**D11. Catalogo duplicato.** flumine rilegge il catalogo ogni 60 s per tutti i mercati (`flumine.py:80-86`; 343+168 righe di log in 51 min) e noi teniamo un catalogo nostro (`LiveSession.markets_by_event`, `selection_names`, `runner.py:174-250`, `_catalog_events`).

**D12. Metodi `process_market_book`/`check_market_book` duplicati** (`s04_dettaglio_copie.tsv`): 20 copie / 19 copie di produzione e laboratorio. **In A**: `MarketRecorderStrategy` (`recorder.py:184,189`; 4 + 19 righe) e `_Capture` del tennis (`tennis_runner.py:425,428`; 2 + 3 righe, in una classe interna ricreata a ogni `_make_capture`). Gruppi `rapporto_con_riferimento` 1,00: i due sono "gruppi" diversi (corpi diversi), cioe' NON identici. Le altre 18 copie sono strategie (scheda E: scalper 4 classi `scalper_bot.py:817`, `sniper_bot.py:377`, `theta_bot.py:612`, `media_under_bot.py:1116`; tennis 4 bot; `LiveTradingStrategy` `engine/live_trading_strategy.py:188`; banco `banco_comune.py:2970`, `sim_strategy.py:235`; `backtest_pro.py:43`, `record_multi.py:141`; laboratorio 5). Le 19 copie di `check_market_book` hanno 15 corpi distinti su 153 righe totali: 2-22 righe ciascuna (`s04_riepilogo.txt`); la logica di filtro "mercato mio / stato / inplay" e' riscritta in ognuna.

**D13. Otto server WebSocket in otto processi** (§1.6): la UI apre fino a 8 connessioni locali e deve conoscere porte e topic (`useControlRoom.ts:7,151,675,962-971`, `RigaFreno.tsx:13`, `RigaOrdiniReali.tsx:21`). `local_channel.py` (767 righe) e' un modulo solo, ma ogni processo lo istanzia con la propria porta e il proprio token.

**D14. DB nel percorso stream -> UI.** Nessuna chiamata di rete nel percorso stream -> decisione dei bot flumine; i bot Mike/Safe/Omega leggono il feed da DB con eta' del feed di 2,5 s + poll (§1.6). Poll di controllo nel runner: `live_follow` 29/min (`MISURE:103`); intero runner calcio 552 chiamate/min (`MISURE:99-110`), di cui quasi nessuna A (A = `live_follow` 29, `safe_strategy_scan` 8, `heartbeat` 8, `live_ladder` non misurata).

---

## 4. Domani

### 4.1 Dove vive ogni funzionalita' (UNA cartella, UN contratto, UN `COSA_FA.md`)

Struttura proposta (nomi indicativi, cartella `nucleo_betfair/`; tutto il resto del piano la usa come "porta" di A):

| File | Contiene (funzionalita' A-) | Sostituisce oggi |
|---|---|---|
| `COSA_FA.md` | scopo, entrate, uscite, come si sostituisce, come si prova da solo | (nuovo) |
| `sessione.py` | A-001..A-006, A-016, A-019 (UNA sessione per processo, custode unico, REST di libreria) | `auth.py`, `client.py` (sessione/RPC), parte di `odds_refresh.py`, 3 keepAlive |
| `rest.py` | A-009..A-015, A-021, A-022, ripiego `listMarketBook` a chunk con limiti | `client.py` metodi, `_poll_books_rest`, `poll_books`, `fetch_event_markets` |
| `flusso.py` | `GestoreFlussi(profilo: ProfiloSport)`: A-024..A-034, A-063, A-066..A-068, A-073, A-076 | frammenti, sottoscrizione/iscrizione a caldo, parte setup runner calcio/tennis, pool dello scanner |
| `salute.py` | A-031, A-033, A-038, A-072, A-077 | 4 implementazioni di "muto" |
| `registro_raw.py` | A-047..A-051 | `raw_listener.py`, `tennis_recorder.py` |
| `ladder.py` | A-052..A-054, A-069 | helper gemelli + 2 `ladder_worker` + `ladder_canale.py` |
| `canale.py` | A-057, A-084..A-086 | `local_channel.py` |
| `lettori_canale.py` | A-058..A-061, A-080, A-082 | 5 moduli di canale |
| `profili.py` | `ProfiloSport` calcio/tennis/scanner (campi, depth, tetti, filtro, conflate) | `config_stream.py` + costanti tennis |
| `tests_contratto/` | parita' (§5) | test dispersi |

Contratto proposto (Python, tipi). Ogni stream e' una **connessione con un profilo**; il bot non vede mai la connessione:

```python
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Literal, Optional, Protocol, Set
from betfairlightweight.resources import MarketBook   # nessuna copia nostra del book

Sport = Literal["calcio", "tennis"]

@dataclass(frozen=True)
class ProfiloFlusso:                      # UN profilo = una politica di sottoscrizione
    nome: str                             # "runner_calcio" | "runner_tennis" | "scansione"
    campi: tuple[str, ...]                # EX_ALL_OFFERS... / EX_BEST_OFFERS
    ladder_levels: int                    # 10 | 1
    conflate_ms: Optional[int]            # None | 1000   (oggi: runner.py:2864, stream.py:276)
    heartbeat_ms: Optional[int]           # oggi None (decide Betfair) | 5000
    mercati_per_connessione: int          # 180 (tetto), mai > 200
    connessioni_max: int                  # 3 | 1 | 4
    riserva_connessioni: int              # 1
    registra_raw: bool

class FlussoMercato(Protocol):
    def imposta_mercati(self, mercati: Iterable[str]) -> Set[str]: ...      # restituisce i "persi" (oggi manutenzione())
    def aggiungi_consumatore(self, cb: Callable[[MarketBook], None], *, mercati: Optional[Set[str]] = None) -> None: ...
    def book(self, market_id: str) -> Optional[MarketBook]: ...             # ultimo book, nessuna copia
    def stato(self) -> Dict[str, object]: ...                               # battito, connessioni, motivo_limite
    def stato_flusso(self, market_id: str) -> Literal["vivo", "muto", "assente"]: ...

class Ladder(Protocol):                   # servita localmente
    def push_a_ogni_cambio(self, market_id: str) -> None: ...               # event-driven, non polling a 200 ms
    def snapshot(self, market_id: str) -> dict: ...                         # stesso schema `ladder` di oggi
```
Eventi esposti: `book_aggiornato(MarketBook)`, `flusso_muto(market_id|connessione)`, `sessione_rifatta()`, `capacita_cambiata(n)`,
`mercato_chiuso(market_id)`. Consumati: `imposta_mercati` (da auto-follow / follow manuali, D), `ordini_vivi() -> Set[str]`
(da C, per proteggere i mercati con soldi: oggi `frammenti_mercato.py:293-310`).

**Verifica delle ipotesi, risposta alla domanda «nucleo unico con sport come parametro, cache unica, ladder servita localmente»:**
1. *Sport come parametro*: **dimostrata in parte dal codice**. Le differenze fra calcio e tennis sono dati (campi, depth, tetto, mercati REC, ordini
   `paper latency`), non logica: `STREAM_FIELDS` (`config_stream.py:90`, `tennis_runner.py:119`), tetto 180 identico
   (`config_stream.py:164`, `iscrizione_a_caldo.py:65`), stesse funzioni ladder (D2 ratio 0,70-0,93), stesso tee, stessa sorveglianza.
   Le differenze vere: calcio a frammenti (>180 mercati) e `auto_follow`; tennis a UN solo stream e armamento bot a caldo. Entrambe
   si esprimono come `mercati_per_connessione`/`connessioni_max` di `ProfiloFlusso`.
2. *Una sola connessione per sport*: **smentita**. 200 mercati/sottoscrizione (`sottoscrizione_a_caldo.py:40`) e il caso 26/09
   (`frammenti_mercato.py:1-9`) impongono N connessioni. Lo scanner non puo' fondersi con il runner perche' flumine fonde due
   strategie solo se coincidono `market_filter`, `market_data_filter`, `streaming_timeout` e `conflate_ms`
   (`flumine/streams/streams.py:110-121`) e lo scanner chiede conflate 1000, depth 1, EX_BEST_OFFERS contro conflate 0, depth 10,
   EX_ALL_OFFERS: sono due sottoscrizioni diverse per natura. Quello che si puo' unire e' il CODICE (un `GestoreFlussi`, due profili).
3. *Cache unica*: **vera per il runner, falsa se si volesse unire con lo scanner**. In un processo basta la cache di bfl/flumine
   (`market.market_book`); le copie 5-8 si eliminano se i consumatori leggono il `MarketBook` (verifica su `latest_books`: 8 punti, §1.5).
   Lo scanner, processo diverso, resta un produttore di righe (`safe_strategy_scan`): e' lui il bus per Mike/Safe/Omega.
4. *Ladder servita localmente*: **gia' vera dal 23/09**; resta da rendere event-driven e da togliere il DB dal thread (D5).

**Alternativa piu' radicale (non obbligatoria): processo unico "nucleo" per sport** che ospiti runner e scanner per la stessa connessione
non e' sostenuta dal codice per le ragioni al punto 2; la riduzione dei processi e' materia della scheda I.

### 4.2 Cosa e' gia' in una libreria matura e oggi riscriviamo

| Nostro | Riferimento di libreria |
|---|---|
| `client.py` JSON-RPC (`list_events`, `list_market_catalogue`, `list_market_book`, `place_orders`, `list_current_orders`, `list_cleared_orders`, `account_rpc`; 426 righe) | `betfairlightweight.endpoints.betting`: `list_events:103`, `list_market_catalogue:206`, `list_market_book:241`, `list_current_orders:342`, `list_cleared_orders:387`, `place_orders:471`; `endpoints.account.get_account_funds:18` (con login/keepAlive/`session_timeout` gia' gestiti) |
| `CustodeSessione` keepAlive/relogin (`auth.py:156-286`) | `flumine/worker.py:99-116` (keepAlive + login se fallisce, periodo min(timeout/2, 1200)); il custode aggiunge backoff e rilevamento errore: il valore e' nel backoff, non nel ciclo |
| `FrammentoMarketStream.run` retry con `initialClk/clk` (`frammenti_mercato.py:185-226`) | `flumine/streams/marketstream.py:12-52` (stesso `@retry(wait_exponential(2..60))`): scritto a mano solo per "mai riconnettere dopo stop" |
| Ripresa/riconnessione dello stream dello scanner (`stream.py:407-460`) | `MarketStream.run` di flumine / `BetfairStream.subscribe_to_markets(initial_clk, clk)` (`betfairstream.py:102-141`) |
| `serialize_book`/`_latest` (`recorder.py:50-88`) | `market.market_book` gia' tenuto da flumine; cache bfl `MarketBookCache` |
| Conversione/elenco catalogo (`runner.py:136-171`) | `flumine.worker.poll_market_catalogue` (60 s) gia' attivo |
| Registrazione raw (`raw_listener.py`) | `flumine` ha `market_recording_mode` e `DataStream` (`flumine/streams/datastream.py:158-209`); il commento `runner.py:2887-2889` spiega perche' non si usa: sopprimerebbe `process_market_book`. Lo scrivere il tee e' quindi giustificato, ma ripetuto due volte. |
| Retry delle chiamate REST (`client.py:203-257`) | `betfairlightweight` solleva eccezioni tipizzate; la politica di retry resta nostra (money: `call_mutating` non ritenta, `omega_market.py:89-112`) |

### 4.3 Stima delle righe DOPO (con il calcolo)

Quota A di `runner.py` e `tennis_runner.py`: stima per intervalli di righe (somma delle funzioni A elencate in §2):
runner.py = 185 (ladder 573-757) + 212 (subscription 982-1193) + 574 (sessione/stallo/heartbeat 1194-1767) + 108 (client 2123-2230) + 78 (frammento0
2375-2452) + 250 (parte A di `setup_and_run` 2599-2850 circa) = **~1.400**; tennis_runner.py = 200 (testata/config 1-200) + 76 (ladder 200-275) +
115 (capture 405-519) + 109 (sessione 520-628) + 91 (risoluzione 744-834) + 53 (ladder_worker 1455-1507) + 36 (keepalive 1583-1618) + 171 (stallo 2182-2352) +
400 (a caldo 2353-2750) + 107 (REC 2751-2857) + 150 (parte A di `setup_and_run`) = **~1.500**. Sono stime per intervalli, non una misura per riga.

| Gruppo | Oggi (righe, quota A) | Cosa diventa condiviso / sparisce | Dopo (stima prudente) |
|---|---|---|---|
| Sessione + REST (`auth.py` 294, `client.py` 426, `odds_refresh.py` sessione 43, `refresh_worker.py` 99, `odds_refresh.py` prodotto 220) | 1.082 | `client.py` 426 -> 120 di sottile involucro su endpoint di libreria (-306); sessione REST di `odds_refresh` -> custode unico (-43) | **733** |
| Stream (calcio ~1.400 + tennis ~1.500 + `frammenti_mercato` 665 + a caldo 113+322 + `stream_muto` 292 + `runner_lifecycle` 291 + `recorder` 249 + `raw_listener` 325 + `tennis_recorder` 384 + `mercati_registrati` 95 + `ladder_canale` 169 + `config_stream` 339 + scanner `stream.py` 567) | 6.711 | helper ladder gemelli -74 (113+76 -> 115); `ladder_worker` -44 (71+53 -> 80); tee raw -289 (709 -> 420: 29-36% testo uguale, il resto tennis-specifico resta); stallo runner/tennis -163 (393 -> 230); scheletro `setup_and_run` -250 (574 -> ~324) | **5.891** |
| Canali (`local_channel` 767 + 5 moduli 2.552) | 3.319 | solo il costrutto comune di lettore/interruttore/freschezza: -300 (20% del testo di codice di 1.502, stima alta: uguale a coppie fino al 29,5%) | **3.019** |
| Feed e board (`scan_feed` 540, `board_worker` 230, `flusso_prezzi` 345, `valuta` 349) | 1.464 | nessuna riduzione dimostrata | **1.464** |
| **Totale quota A** | **12.576** | **-1.469** | **11.107 (-11,7%)** |

**Onesta'**: l'obiettivo del brief («80% di righe in meno») NON e' dimostrabile per A. Ragioni misurate: (1) il testo uguale fra calcio e
tennis e' 8-9% a livello di file e 35% nel raw tee; (2) il 38% delle righe di `runner.py` e' commento (3.171 - 1.965 di codice) e il 33% in `tennis_runner.py`
(3.483 - 2.345): sono motivazioni di incidenti datati (16/07, 09/09, 26/09, 28/09); (3) il peso e' nelle guardie e nei casi limite, che la
regola 5 del brief vieta di tagliare. Scenario condizionato (NON provato, da misurare con un prototipo): portare lo scanner sullo stesso
`GestoreFlussi` (-567 + ~250 di profilo = -317) e unificare i due client di sessione e le copie del ladder in un solo percorso
event-driven potrebbe valere altri ~800-1.200 righe, cioe' un totale del 21-24% (11.107 - 317 - 800/1.200 = 9.990/9.590). Il guadagno vero di A e' strutturale e di risorse:
una politica di riconnessione, una di salute, una sessione, meno copie, meno connessioni.

### 4.4 «Per sostituire questo componente OGGI tocco / DOMANI tocco»

- Oggi, per cambiare (per esempio) la profondita' del ladder o la politica di riconnessione: `config_stream.py`, `runner.py`,
  `tennis_runner.py`, `frammenti_mercato.py`, `raw_listener.py`, `tennis_recorder.py`, `safe_strategy/stream.py`, `stream_muto.py`, `ladder_canale.py`,
  e i test di 6 moduli (almeno 9 file); per cambiare librerie di sessione: `auth.py`, `client.py`, `odds_refresh.py`, `runner.py`, `tennis_runner.py`,
  `scalper_session.py`, `safe_strategy/service.py`, `omega_market.py` (almeno 8 file).
- Domani: solo `nucleo_betfair/` (profilo in `profili.py`, o `flusso.py`/`sessione.py` per la politica) e `nucleo_betfair/tests_contratto/`.
  I consumatori (bot, ordini, UI) vedono `FlussoMercato`, `Ladder`, `MarketBook` e il canale con lo STESSO schema JSON di oggi.

---

## 5. Parita'

Criterio: **stessa registrazione -> stessi book consegnati, stessi eventi di salute, stesso payload ladder, stessi fotogrammi UI, stessi numeri nei replay dei bot**.

1. **Contratto del feed** (voce §6.1): le 40 registrazioni `_live_raw/*` (`m01_feed_raw.txt`: 1.071.944 messaggi) lette dal NUOVO `GestoreFlussi` via
   `HistoricalStream` (flumine) producono per ogni mercato gli STESSI `MarketBook` (`publish_time_epoch`, `status`, `inplay`, runner, `ex.available_to_back/lay`, `traded_volume`)
   del vecchio recorder: confronto campo per campo di `serialize_book` vecchio vs nuovo `snapshot()`. Qualita' COMPLETE/PARTIAL/NO_RAW dichiarata come oggi (§7.32).
2. **Parita' del ladder** (§6.5, §7.9 "ladder letto con getattr su dict", §7.33 costante duplicata): per ogni registrazione, sequenza dei payload `ladder` (`updated_ms`, selezioni,
   `wom`, `trd`) vecchia vs nuova: identica (firma SHA-1 `ladder_signature` uguale a ogni passo) e `updated_ms` strettamente crescente. Fotografie della UI: `localTransport.test.ts`,
   `canaleRunner.test.ts`, `localChannel.test.ts` esistenti restano verdi senza modifica; aggiungere il test del topic `ladder` con le 3 registrazioni piu' lunghe.
3. **Replay professionale dei bot sul banco** (§6.2, §6.3, §6.4, §6.7, §6.8): `python -m Betfair.stream.backtest.certifica <bot> ...` per Mike, Omega, Safe base/esatto/punta, scalper
   (maker/sniper/media/theta), tennis pro/FLB/swing/scalper su una registrazione per bot (`registrazioni_banco/`); i numeri che DEVONO coincidere col referto precedente
   (cronostoria/referto del banco): decisioni, ordini, importi, istanti, P&L, scenari sollecitati. Il nuovo flusso e' trasparente per il banco: `HistoricalStream` non attraversa
   `GestoreFlussi` (la parita' del banco prova che A non ha cambiato i `MarketBook`; la parita' di A prova che il percorso live produce gli stessi).
4. **Riconnessione e salute** (§6.6, §7.17 sospeso/chiuso, §7.19 stato in RAM perso, §7.20 battito vivo != utilizzabile): scenari sul banco con registrazione interrotta e ripresa
   (`recmeta.jsonl`: `resubscribe`, `record_toggle`), frammento muto >180 s, relogin con ordini vivi (rinvio), `status:503`: stessa uscita (`stato()` e alert) per vecchio/nuovo.
   I test esistenti da portare: `Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py` (citato in `frammenti_mercato.py:22`) e `test_stream_muto_cantiere_j_2026_09_28.py`, `test_stream_muto_cablato_cantiere_j2_2026_09_28.py`, `test_runner_lifecycle.py` (esistenti; un test di `flusso_prezzi` non verificato).
5. **Valuta** (K1, §6.1): il middleware GBP->EUR produce le stesse size (`size_gbp_convertite`, `valuta`: `recorder.py:82-85`) con cambio fisso nel banco.
6. **Falsificazione obbligatoria** (§6.7, §7.35): ogni test nuovo di parita' si prova con mutazione: (a) togliere l'ordinamento per `selection_id` in `ladder_signature` -> deve diventare rosso;
   (b) togliere `initialClk/clk` dalla ripresa -> deve diventare rosso; (c) alterare la conversione GBP->EUR -> rosso; (d) spegnere `connectionsAvailable` -> il test della riserva rosso.
   Finti con chiavi e tipi identici al vero (§7.27): gli `Fake*` usano le classi vere di bfl/flumine, mai dizionari ad hoc.
7. Voci di `PROCESSO_STANDARD_BOT.md` coperte: §6.1 (dati), §6.2 (scanner/feed), §6.3 (servizio intero a cadenza reale), §6.5 (persistenza e UI), §6.6 (concorrenza e limiti),
   §6.7 (scenari e falsificazione), §6.8 (referto), §6.9 (velocita' del banco: il banco deve restare entro 5 min / tetto 10); catalogo §7: 9, 15 (scan costruito a mano), 17, 19, 20, 27, 30, 32, 33, 35, 37.

Replay: nessuno lanciato da me (vincolo del brief: nessun replay del banco). Durata attesa per una certificazione di bot con A invariato per il banco: quella del referto vigente
(<= 5 min, §6.9).

---

## 6. Migrazione

Ordine: A viene PRIMA di D/E (i bot non cambiano) e dopo la **scheda G** solo per la parte "DB fuori dal thread del ladder". Ogni passo ha interruttore e ombra.

1. **P0 - misure** (§7): scrivere gli strumenti, fissare i numeri di partenza. Nessun cambio di codice.
2. **P1 - `sessione.py` in ombra**: un `CustodeSessione` per processo che e' GIA' `auth.py`; collega `rest` del runner calcio al custode (rimedio al REPERTO §1.7) dietro interruttore
   `SESSIONE_UNICA`; ombra: contare per un giorno `keepAlive`/`relogin` del vecchio vs nuovo e confrontare i `stato()`. Ritorno indietro: interruttore.
3. **P2 - `rest.py`**: sostituisce i 5 ripieghi con un solo punto (chunk, pause, limiti); confronto automatico: stesse righe in `safe_strategy_scan` e `board` per le stesse
   partite (le due fonti in parallelo per 1 ora, differenza = 0 sui campi `best back/lay`).
4. **P3 - `ladder.py` event-driven + DB fuori dal thread**: il DB `live_ladder` va a un thread di scrittura separato con coda (stessa riga, stessa cadenza write-on-change); il canale
   pubblica a ogni cambio (min 20 ms). Ombra: due publisher, confronto delle firme per 1 giornata; taglio del vecchio solo con firma identica al 100% e latenza canale <= quella di oggi.
5. **P4 - `flusso.py` con profili**: prima il tennis (1 connessione, costruzione piu' semplice), poi il calcio (frammenti), poi lo scanner (profilo `scansione`) con ripresa `initialClk/clk`.
   Ombra: nessuna connessione doppia (il limite e' 10): il periodo ombra e' SUL BANCO (registrazioni), non sul live; taglio con replay identici sulle 40 registrazioni.
6. **P5 - `registro_raw.py`**: un solo tee per i due sport (parita' sui `.raw.jsonl` byte per byte + sidecar `recmeta`).
7. **P6 - canali**: `lettori_canale.py` dopo che la scheda D ha fissato il contratto dei bot. Ordine dei 5 moduli: sveglia -> scan -> bot -> tennis -> esiti (dal piu' semplice al piu' money).

Rischi: (a) la `serialize_book` e' usata da 8 punti con il suo formato dict: eliminarla richiede la verifica per ognuno (non fatta); (b) cambiare `heartbeatMs` o `conflateMs` in
una sottoscrizione cambia la frequenza dei messaggi: e' un cambiamento di dati per i bot, NON si fa senza decisione dell'utente (§Decisioni); (c) la ricostruzione del framework resta il
rimedio unico finche' A non espone un modo per rinnovare la sessione senza perdere il blotter: non verificato che flumine lo permetta (non ho trovato un'API di re-auth dello stream in `flumine/streams/`).
Ritorno indietro: interruttore per passo e vecchio codice intatto fino al taglio; mai due connessioni di mercato identiche in parallelo sul live.

---

## 7. Misure

Numeri di OGGI (con fonte) e obiettivo DOPO. "NM" = non misurato; lo strumento che lo misurerebbe e' scritto.

| Grandezza | Oggi | Fonte / strumento | Obiettivo dopo |
|---|---|---|---|
| Messaggi mercato in-play (intervallo p50 / p95 / p99) | 105 / 425 / 971 ms | `misure/uscite/m01_feed_raw.txt` (40 eventi, 1.071.944 msg) | invariato (e' il feed) |
| Aggiornamento per mercato in-play p50 / p95 | 306 / 3.518 ms | idem | invariato |
| Byte raw per partita | 277,5 MB / 4.928 min (circa 56 KB/min/evento) | idem | invariato (registrazione opt-in) |
| Connessioni Stream: caso peggiore del codice | 10 su 10 (senza scalper) | §1.3 | <= 7 con scanner su stesso gestore e riserva 3 (da confermare) |
| Chiamate DB/min del runner calcio | 552 (A: 45 = 29+8+8) | `MISURE:98-110` | A -> <= 10 (follow letto da canale/locale: scheda G) |
| Chiamate DB/min dello scanner | 86 (68 POST scan) | `MISURE:155-165` | invariato (e' il feed per i bot) |
| Ladder: latenza da `publish_time` al push | NM | strumento: replay di una registrazione con `a_latenza_ladder.py` (leggere `pt`, orologio di consegna al canale; esegue SOLO nel banco, non importa il runner) | <= 1 intervallo di conflazione (cioe' push guidato dall'evento, non 200 ms di polling) |
| CPU di `serialize_book`+`json.dumps` per aggiornamento | NM | strumento: `cProfile` su `process_market_book` in un replay del banco su una registrazione da 77.354 messaggi (evento 35764745) | -50% togliendo la copia 5 |
| RAM del runner dopo 24 h | NM | `psutil` ogni 60 s nel processo (scheda I) | piatta (nessuna crescita) |
| Righe quota A | 12.576 | §4.3 | 11.107 (prudente) / ~9.600-10.000 (condizionato, non provato) |
| Funzionalita' | 86 | §2 | 86 (nessuna persa) |
| Punti di login | 12 `build_client` + 6 `BetfairClient()` | §3 D6 | 1 per processo (custode unico) |
| Copie del book in memoria/JSON nostre | 6 (+2 su disco) | §1.5 | 2 (cache bfl/flumine + payload del canale) |

---

## Decisioni per l'utente

1. **`heartbeatMs` e `conflateMs`**: oggi il runner calcio e tennis non chiedono `heartbeatMs` (decide Betfair); lo scanner chiede 5.000 ms. Chiederlo esplicito su tutti uniformerebbe
   la soglia di "stream muto", ma cambia la frequenza dei messaggi: non lo faccio senza ordine.
2. **`TENNIS_STREAM_CONFLATE_MS`** e' codice morto (`tennis_runner.py:116`): rimuoverlo o collegarlo davvero? Collegarlo cambia i dati dei bot tennis.
3. **Limite per connessione**: il codice scrive che Betfair (BDP) puo' alzare i 200 mercati a 1.000 su richiesta (`safe_strategy/stream.py:3-6,92-93`): chiedere l'innalzamento ridurrebbe
   le connessioni (e il rischio D7). Decisione commerciale/amministrativa dell'utente.
4. **Whitelist `LIVE_MARKET_TYPES`**: -39% di mercati per evento ma riduce la registrazione (`config_stream.py:170-192`): decisione gia' rinviata all'utente; il piano non la cambia.
5. **Sessione `rest` del runner calcio** (REPERTO §1.7): prova dal vivo che si invalida dopo 20 min senza keepAlive? Da fare solo con il permesso dell'utente (nessun processo nuovo).
6. **Unificare il scanner sul gestore comune**: costo di migrazione medio, benefici su riconnessione `initialClk`; non cambia nessuna strategia.

## Cosa ho verificato di persona / cosa non ho potuto verificare

Verificato leggendo il codice (citazioni `file:riga` controllate con `sed -n`/`grep -n` durante la scrittura): parametri di sottoscrizione (§1.4), numero e posizione delle connessioni (§1.3), copie
del book (§1.5), cadenze del ladder (`ladder_canale.py:46,103-105`, `config_stream.py:60,74`), protocollo e porte (`local_channel.py`, `start_channel`), logica di riconnessione di flumine e bfl
nel `.venv`, difflib calcio/tennis e canali (strumenti miei, output salvato), conteggi login (`git grep`), 8 punti di consumo di `latest_books`, numeri del feed (`m01_feed_raw.txt`
letto, non rigenerato) e delle chiamate DB (`MISURE_2026-10-02.md` letto, non rigenerato).

NON verificato:
- Stato degli interruttori dei canali nel `.env` (non letto: contiene segreti). Quindi quali bot leggono oggi dal canale 47336 e dal 47331 non e' noto, solo il default del codice.
- Se i `MarketStream ...: SUCCESS` del log sono connessioni nuove o sottoscrizioni sullo stesso socket.
- Sessione `rest` del calcio dopo 20 min (nessuna chiamata a Betfair consentita).
- Frequenza di `live_ladder`/`tennis_live_ladder` (la finestra di misura del 02/10 non conteneva partite seguite).
- CPU/RAM per processo, latenza stream -> push, costo di `serialize_book`: nessuno strumento esistente; proposti in §7. Non ho eseguito codice di produzione ne' replay del banco.
- La quota A di `runner.py` e `tennis_runner.py` e' una stima per intervalli di funzioni, non una misura per riga.
- Che tutti gli 8 consumatori di `latest_books` possano passare a `MarketBook` senza cambiare l'uscita (non letti uno per uno).
- Quali file dei pannelli UI mostrano ladder/board oltre a `localTransport.ts` e alle righe citate (es. il componente ladder e il pulsante "Aggiorna quote" non sono stati aperti).
