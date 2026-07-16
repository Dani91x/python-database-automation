# Betfair Best Practices — Audit 2026-07

> Ricerca sulle best practices UFFICIALI Betfair (developer.betfair.com) e del betcode-stack
> (betfairlightweight 2.23.2 / flumine 2.13.11), confrontate con l'uso attuale nel repo.
> SOLO ricerca + assessment: nessuna modifica al codice. Base per i quick-win futuri.
>
> Architettura attuale di riferimento: runner stream calcio (flumine, eventi seguiti),
> runner tennis, sessioni scalper per-evento (1 processo flumine + 1 login per evento),
> Omega REST-polling 20s, coda ordini `betfair_live_order_requests`, mirror Supabase.

---

## 1. Regole e limiti ufficiali (con fonti)

### 1.1 Stream API — mercati per subscription e connessioni

| Regola | Valore | Fonte |
|---|---|---|
| Mercati raccomandati per singola streaming connection | **≤ 200** ("no more than 200 markets per connection; for broader coverage open multiple connections") | [Exchange Stream API docs](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API) |
| Connessioni stream concorrenti per app key | **10** (aumentabile su richiesta per clienti high-value; il campo `connectionsAvailable` nella StatusMessage di autenticazione dice quante nuove connessioni puoi aprire) | [Forum ufficiale — Max concurrent connections](https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/3420-streaming-api-max-concurrent-connections), [Exchange Stream API docs](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API) |
| Errori legati | `MAX_CONNECTION_LIMIT_EXCEEDED` (troppe connessioni / connessioni non chiuse), `TOO_MANY_REQUESTS` (apertura/chiusura connessioni troppo frequente) | [Perché ricevo TOO_MANY_REQUESTS](https://support.developer.betfair.com/hc/en-us/articles/360000406111-Why-am-I-receiving-the-TOO-MANY-REQUESTS-error) |

### 1.2 Stream API — heartbeat, conflation, riconnessione

| Regola | Valore | Fonte |
|---|---|---|
| `heartbeatMs` | bounds **500–5000 ms**, default 5000; heartbeat inviato SOLO se nessun altro traffico nell'intervallo; contiene sempre un `clk` (da salvare), mai dati mercato (`"ct":"HEARTBEAT"`) | [Market Streaming — Heartbeat & Conflation](https://support.developer.betfair.com/hc/en-us/articles/360000402611-Market-Streaming-How-do-the-Heartbeat-and-Conflation-requests-work) |
| `conflateMs` | conflazione forzata lato server; **180000 ms imposti** con Delayed App Key o account delay | idem |
| Slow consumer | se il client NON legge (svuota) il socket buffer, il ciclo corrente viene saltato e accorpato al successivo con **`con=true`** — il client DEVE leggere il buffer velocemente | idem |
| Riconnessione | nessun messaggio per **2 × heartbeat** → considerarsi disconnessi: nuova connessione + **re-subscribe con `initialClk`/`clk`** per riprendere da dove si era | [Exchange Stream API docs](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API) |
| Uso stream vs polling | Betfair raccomanda lo Stream API al posto del polling REST per dati di mercato continuativi (il polling pesa sui Data Request Limits) | [Exchange API FAQ](https://developer.betfair.com/en/exchange-api/faq/) |

### 1.3 REST — Market Data Request Limits (listMarketBook & co.)

| Regola | Valore | Fonte |
|---|---|---|
| Peso massimo per richiesta | **sum(Weight) × n. marketIds ≤ 200 punti**, oltre → errore `TOO_MUCH_DATA` | [Market Data Request Limits](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687478/Market+Data+Request+Limits) |
| Pesi PriceProjection | null=2, SP_AVAILABLE=3, SP_TRADED=7, **EX_BEST_OFFERS=5**, **EX_ALL_OFFERS=17**, **EX_TRADED=17**; combinati: BEST+TRADED=**20**, ALL+TRADED=**32** | idem |
| `exBestOffersOverrides` | il peso diventa **weight × (requestedDepth/3)** | idem |
| Frequenza listMarketBook | max **5 chiamate/secondo verso lo stesso marketId** | [What data/request limits exist](https://support.developer.betfair.com/hc/en-us/articles/115003864671-What-data-request-limits-exist-on-the-Exchange-API) |
| Rate limiting condizionale | `listMarketBook`, `listCurrentOrders`, `listMarketProfitAndLoss` contendono tra loro: oltre ~3 richieste accodate → throttling | idem |
| listMarketCatalogue | pesa poco (MARKET_DESCRIPTION=1, RUNNER_METADATA=1, altri 0) ma la best practice ufficiale è **cacheare il catalogo**, non richiederlo in loop | [Market Data Request Limits](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687478/Market+Data+Request+Limits) |

### 1.4 Transaction charges

| Regola | Valore | Fonte |
|---|---|---|
| Soglia gratuita | **5000 transazioni qualificanti / ora** (ora = 60 minuti sull'orologio 24h) | [Transaction Charge — how are transactions counted](https://support.developer.betfair.com/hc/en-us/articles/20029343399836-Transaction-Charge-how-are-transactions-counted) |
| Costo oltre soglia | **£0.002 (0.2p) per transazione** eccedente | [Betfair Charges](https://www.betfair.com/aboutUs/Betfair.Charges/) |
| Cosa conta | bet piazzate (matched/unmatched/lapsed) = 1 txn; **cancel riuscito = 0 txn**; cancel FALLITO = 1 txn; place+cancel = 1 txn totale | [Transaction Charge — how are transactions counted](https://support.developer.betfair.com/hc/en-us/articles/20029343399836-Transaction-Charge-how-are-transactions-counted) |
| Offset commissioni | la charge è compensata da (Commission Paid + Implied Commission)/2, Implied = perdite mercato × 3% | [Betfair Charges](https://www.betfair.com/aboutUs/Betfair.Charges/) |

### 1.5 Login, sessione, keep-alive

| Regola | Valore | Fonte |
|---|---|---|
| Scadenza sessione **Italian Exchange (.it)** | **20 minuti** (la più corta; Spagna uguale; .com 12h, UK/IE 24h) | [Login & Session Management](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687869/Login+Session+Management) |
| keepAlive | va chiamato **entro la scadenza**; l'attività API ordinaria NON estende la sessione — serve la chiamata esplicita a `keepAlive` (endpoint per giurisdizione, `.it` incluso) | [How do I keep my API session alive](https://support.developer.betfair.com/hc/en-us/articles/360002773032-How-do-I-keep-my-API-session-alive) |
| Bot non presidiati | usare il **cert login (non-interactive)**; interactive solo con utente presente | [Login & Session Management](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687869/Login+Session+Management) |
| Riuso sessione | il session token va **riusato** finché valido; loop di re-login frequenti → `TOO_MANY_REQUESTS` / blocco temporaneo del login | [Perché ricevo TOO_MANY_REQUESTS](https://support.developer.betfair.com/hc/en-us/articles/360000406111-Why-am-I-receiving-the-TOO-MANY-REQUESTS-error), [INVALID_SESSION_INFORMATION](https://support.developer.betfair.com/hc/en-us/articles/11775498092701-Why-I-am-received-the-error-INVALID-SESSION-INFORMATION) |

### 1.6 placeOrders — riferimenti cliente e batch

| Regola | Valore | Fonte |
|---|---|---|
| Istruzioni per singolo placeOrders | 200 (UK/AUS) ma **50 sull'Italian Exchange** | [placeOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders) |
| `customerRef` | ≤ 32 char, de-dup delle risottomissioni per errore | idem |
| `customerStrategyRef` | ≤ 15 char; identifica la STRATEGIA; ritorna in listCurrentOrders/listClearedOrders/listMarketBook e **filtra l'Order Stream** (`customerStrategyRefs` nella order subscription) | idem |
| `customerOrderRef` | ≤ 32 char; identifica la singola istruzione; tracciabile via Stream API e API-NG | idem |

### 1.7 betcode-stack (flumine / betfairlightweight) — performance ufficiali

Fonte: [flumine Performance docs](https://betcode-org.github.io/flumine/performance/), [flumine Advanced](https://betcode-org.github.io/flumine/advanced/).

- **`listener_kwargs`** nel market_filter della strategia (`seconds_to_start`, `inplay`) per scartare a monte gli update non necessari.
- **`betfairlightweight[speed]`** (librerie C/Rust per JSON e datetime) → grande impatto sulla velocità di parsing dello stream.
- **Logging**: disattivare/ridurre il logging in produzione (ogni update può generare molte chiamate di log).
- **Ordini**: il collo di bottiglia in live è il numero di ordini processati → minimizzare place/cancel/replace ridondanti (vale anche per la transaction charge).
- **Stream fusion**: flumine (`Streams.add_stream`) fonde due strategie nella stessa MarketStream SOLO se coincidono market_filter + market_data_filter + streaming_timeout + conflate_ms; ogni combinazione diversa = una subscription/connessione in più.
- flumine registra di default il control **`MaxTransactionCount`** pilotato da `transaction_limit` del client (guardia client-side sulla soglia 5000/h).

---

## 2. Assessment del repo (com'è OGGI)

### 2.1 Login / sessioni — ⚠️ PROLIFERAZIONE

Dove creiamo login:

- Client REST proprietario (JSON-RPC, cert login .it, retry): `Betfair/client.py:95` (`login_cert`).
- Client betfairlightweight (cert .it, `locale="italy"`): `Betfair/stream/auth.py:28-70` (`build_client`), con wrapper `keep_alive` (`auth.py:73`) e `safe_logout` (`auth.py:83`).
- **Runner calcio**: 2 sessioni all'avvio — REST `rest.login_cert()` + blw `build_client(login=True)` (`Betfair/stream/runner.py:1098-1100`). keepAlive periodico (~8 min) SOLO nel ramo idle desktop `LIVE_RUNNER_KEEP_ALIVE=1` (`runner.py:1159-1174`); durante lo streaming attivo nessun keepAlive esplicito.
- **Runner tennis**: 1 login (`tennis_runner.py:1151`) + keepAlive idle (`tennis_runner.py:1176-1177`); gestione `INVALID_SESSION` con UN relogin+retry sul catalogo (`tennis_runner.py:461-471`).
- **Scalper calcio**: 1 login DEDICATO per OGNI sessione-evento (`Betfair/stream/scalper/scalper_session.py:461-462`, commento esplicito "nessuna condivisione tra sessioni") + 1 login del thread habitat-scan del supervisore (`scalper_service.py:113`), ricostruito a ogni errore (`scalper_service.py:125`).
- **Tennis scalper standalone**: login per processo (`run_tennis_pro.py:88`, `run_tennis_scalper.py:219`, `record_multi.py:280`, `record_tennis.py:41`).
- **Omega**: NESSUN login proprio — riusa la sessione condivisa di `odds_refresh.get_shared_client()` con re-login+retry singolo su errore (`Betfair/omega/omega_market.py:23-38`) ✅ pattern corretto.
- Script batch REST: login per run (`betfair_full_odds.py:147`, `betfair_tennis_odds.py:300`, `odds_refresh.py:67`, `betfair_report_manager.py:140`, `import_betfair_operations.py:394`).
- Lezione già appresa nel repo: loop stretto di `build_client(login=True)` → `TOO_MANY_REQUESTS` (`tennis_live/tennis_bot_service.py:38`).

**Giudizio**: cert login ✅, riuso in Omega ✅, MA: (a) ogni scalper-evento è un login (a 10-20 eventi simultanei = 10-20 sessioni; a 1000 eventi non scala e rischia il blocco login); (b) keepAlive NON sistematico nei processi lunghi (sessione .it = 20 min): il runner lo fa solo in idle, le sessioni scalper mai (si affidano al retry/relogin implicito), `record_multi.py:242` lo chiama una volta sola.

### 2.2 Connessioni e subscription stream — ⚠️ CAP SOPRA LA RACCOMANDAZIONE + 1 CONN/EVENTO

- **Runner calcio**: UNA subscription unica con tutti i market_ids degli eventi seguiti (`runner.py:1189-1194`) ✅ efficiente. MA i tetti interni sono `SAFE_MARKET_THRESHOLD=250` (WARN) e `HARD_MARKET_CAP=400` (`config_stream.py:126-127`): **sopra la raccomandazione ufficiale di 200 mercati/connessione** — oltre 200 andrebbe segmentato su più connessioni, non alzato il cap sulla singola.
- **Data filter calcio**: `EX_ALL_OFFERS` + EX_TRADED + EX_TRADED_VOL + EX_LTP + EX_MARKET_DEF + SP (`config_stream.py:76-84`), `ladder_levels=LADDER_DEPTH=10`. Scelta consapevole (recorder full-depth per il Replay), ma è il filtro più pesante possibile: a 1000 eventi va differenziato (full solo dove serve il replay).
- **Runner tennis**: 1 subscription PER EVENTO (`market_ids=[market_id]`); capture e bot dello stesso evento condividono la stream grazie al filtro identico (`tennis_runner.py:490-497`) ✅ ottimizzazione corretta e testata (`tests/test_tennis_hardening.py:124`). MA in flumine ogni MarketStream distinta = una connessione TCP allo stream endpoint → **N eventi tennis = N connessioni**, contro il limite di ~10 connessioni per app key (sommate a: market stream calcio + order stream + stream scalper).
- **Scalper per-evento**: ogni processo apre la propria Flumine (`scalper_session.py:761-763`) → 1 market stream (+ order stream reale in LIVE) per evento, ognuna su login proprio. Stesso problema del tennis, aggravato dal processo/login dedicato.
- **Conflation**: market stream `STREAM_CONFLATE_MS=0` di default (`config_stream.py:73`), order stream `ORDER_STREAM_CONFLATE_MS=0` (`config_stream.py:161`, passato come `None` → `runner.py:1010,1033`; test `tests/test_build_order_client.py:80-84`). Legittimo per scalping (serve il tick grezzo), ma è una leva di riduzione carico documentata e già cablata via env ✅ (basta settare l'env, zero codice).
- **Heartbeat/riconnessione**: gestita da betfairlightweight/flumine (timeout nativi); watchdog di processo proprietario (`Betfair/stream/watchdog.py`) ✅.

### 2.3 REST polling / listMarketBook — ✅ pesi rispettati, ⚠️ Omega non batcha

- `betfair_full_odds.py:33-35`: batch 39 × EX_BEST_OFFERS(5) = **peso 195 < 200** ✅ (commento esplicito del limite).
- `betfair_tennis_odds.py:30`: batch 8 × (EX_BEST_OFFERS 5 + EX_TRADED 17 = 22) = 176 < 200 ✅.
- `odds_refresh.py:35,137-141`: batch 20 = peso 100, con delay anti-throttle ✅.
- `board_worker.py:25,91`: chunk 25 × 5 = 125 < 200 ✅ (commento "peso leggero, EX_BEST_OFFERS").
- `betfair_report_manager.py:918`: batch con gestione errori per chunk ✅.
- **Omega**: `list_market_book([market.market_id])` UN mercato per chiamata (`omega/omega_market.py:196,361`), ciclo ogni `poll_interval_s` default 20s (`omega/omega_config.py:34`, loop `omega_service.py:1337-1355`). A pochi eventi va bene; a decine di mercati = decine di round-trip REST per giro invece di 1-2 chiamate batched (peso EX_ALL? verificare la projection usata — comunque batchabile fino a peso 200). Migrazione a flumine già in roadmap ✅.

### 2.4 Transaction limit — ✅ GIÀ CONFIGURATO

- `LIVE_TRANSACTION_LIMIT=1000` default (`config_stream.py:188`, commento corretto sulla soglia Betfair 5000/h), passato a `clients.BetfairClient(transaction_limit=...)` in tutte e tre le modalità (`runner.py:1016,1037,1047`) → control nativo flumine `MaxTransactionCount`. Test di coerenza: `tests/test_build_order_client.py:59-65` (asserisce 0 < limite ≤ 5000) ✅.
- Budget transazioni/ora anti-charge anche a livello bot (`scalper/scalper_bot.py:420`, `scalper_lab/scalper_bot_base.py:427`, `tennis_scalper/tennis_scalper_bot.py:432`) ✅ difesa in profondità.
- Nota: il conteggio ufficiale è per CONTO (non per processo) — con molte sessioni scalper parallele i limiti per-processo non si sommano in un tetto globale. Oggi non è un problema (stake piccoli); a volumi alti serve un contatore condiviso.

### 2.5 customerStrategyRef / customerOrderRef — ✅ usati, parzialmente standardizzati

- `Betfair/client.py:334-354`: `customer_strategy_ref` supportato (≤15 char documentato), filtri `customerStrategyRefs`/`customerOrderRefs` su listCurrentOrders/listClearedOrders (`client.py:363-415`) ✅.
- `order_exec.py:197,297-317`: `customerOrderRef` deterministico per fixture+mercato, `customer_strategy_ref="watchlist"` ✅.
- Omega: `customerOrderRef omega-m<id>` come chiave di riconciliazione forte (`omega/omega_market.py:419`, `omega_service.py:858-872`) ✅ best practice da manuale.
- Flumine: ref proprio `name_hash+sep+id` — divergenza nota e documentata (`stream/engine/live_trading_strategy.py:107-127`).
- ⚠️ Non tutti i flussi hanno uno `customerStrategyRef` univoco per strategia (es. scalper/theta/sniper condividono il default flumine): a volumi alti è LO strumento ufficiale per filtrare l'order stream per strategia e riconciliare senza listCurrentOrders.

### 2.6 betcode-stack — versioni e performance

- Pin: `flumine==2.13.11`, `betfairlightweight==2.23.2` (`requirements.txt:28-29`, pin NON negoziabile per interni privati usati da `tennis_runner._stop_framework`) — vincolo noto.
- ⚠️ `betfairlightweight` installato SENZA extra `[speed]` (`requirements.txt:29`): parsing stream in puro Python. È il quick-win ufficiale n.1 dei docs flumine.
- `listener_kwargs` non usati (i filtri sono già stretti per market_ids, quindi impatto limitato oggi; utile a 1000 eventi con `inplay`/`seconds_to_start`).

---

## 3. Raccomandazioni prioritizzate (con rischio di applicazione)

Ordinate per rapporto beneficio/rischio. "Rischio" = rischio di regressione nell'applicarla.

### R1 — `betfairlightweight[speed]` — **ZERO-RISK (config/deps)**
Installare l'extra `[speed]` (C/Rust JSON+datetime) mantenendo il pin 2.23.2: `betfairlightweight[speed]==2.23.2` in `requirements.txt:29`. Riduce la CPU di parsing di ogni update stream (il carico principale del runner full-depth). Nessun cambio di codice; verificare solo l'installazione su Windows (wheel disponibili).
Fonte: [flumine Performance](https://betcode-org.github.io/flumine/performance/).

### R2 — keepAlive sistematico nei processi lunghi — **ZERO-RISK → LOW**
La sessione .it scade in 20 minuti e NON si estende con le normali chiamate API. Oggi il keepAlive gira solo nel ramo idle dei runner (`runner.py:1159-1174`, `tennis_runner.py:1168-1177`); le sessioni scalper e i worker non lo chiamano mai e si affidano a relogin-on-error. Aggiungere un timer keepAlive ogni ~10 min su OGNI client vivo (helper già pronto: `stream/auth.py:73`). Elimina i relogin (che consumano il budget login) e i primi-comandi falliti con INVALID_SESSION.
Fonte: [keep session alive](https://support.developer.betfair.com/hc/en-us/articles/360002773032-How-do-I-keep-my-API-session-alive).

### R3 — Cap mercati/subscription a 200 — **ZERO-RISK (config), MEDIUM per la segmentazione**
Abbassare `LIVE_SAFE_MARKET_THRESHOLD` da 250 a ~180 e `LIVE_HARD_MARKET_CAP` da 400 a 200 (`config_stream.py:126-127`) per stare nella raccomandazione ufficiale — oggi con pochi eventi seguiti non cambia nulla (zero risk). La vera capienza oltre 200 va ottenuta SEGMENTANDO su più subscription/connessioni (MEDIUM-refactor: sharding dei market_ids per subscription nel runner), non alzando il cap singolo.
Fonte: [Exchange Stream API](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API).

### R4 — Omega: batch listMarketBook (e completare la migrazione a flumine) — **LOW**
Sostituire le chiamate 1-mercato (`omega_market.py:196,361`) con batch weight-aware come `betfair_full_odds.py:33-35` (fino a peso 195/chiamata) dentro lo stesso giro di poll: da N round-trip a 1-2. Riduce latenza e pressione sul rate limiting condizionale (listMarketBook contende con listCurrentOrders). La migrazione paper→flumine già pianificata risolve alla radice (stream al posto del polling, come raccomandato da Betfair).
Fonte: [Market Data Request Limits](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687478/Market+Data+Request+Limits).

### R5 — Conflation come leva d'emergenza documentata — **ZERO-RISK (già cablata)**
`LIVE_STREAM_CONFLATE_MS` / `LIVE_ORDER_STREAM_CONFLATE_MS` esistono già (`config_stream.py:73,161`) e arrivano fino al client (`runner.py:1010,1033`, testato). Tenere 0 per lo scalping è corretto; documentare nel runbook che a carico alto (molti eventi, CPU satura, `con=true` nel raw) impostare es. 250-500ms sul market stream del recorder è il primo intervento senza deploy. Il flag `con=true` negli mcm registrati è il segnale che il consumer è lento.
Fonte: [Heartbeat & Conflation](https://support.developer.betfair.com/hc/en-us/articles/360000402611-Market-Streaming-How-do-the-Heartbeat-and-Conflation-requests-work).

### R6 — Consolidare le sessioni scalper per-evento — **MEDIUM-refactor (il più importante per settembre)**
Il modello attuale "1 evento = 1 processo + 1 cert login + 1 Flumine (+1 market stream, +1 order stream)" (`scalper_service.py:60-67`, `scalper_session.py:461-462,761`) è il collo di bottiglia strutturale: a 10+ eventi simultanei si avvicina al tetto di **10 connessioni stream** e moltiplica login e overhead. Direzione: UN framework flumine multi-evento con N strategie (pattern già usato dal tennis_runner), UNA sessione condivisa (token riusabile anche cross-process via `session_token`), UN order stream filtrato per `customerStrategyRefs`. L'isolamento per-evento (crash-safety) si conserva a livello di strategia + watchdog, non di processo.
Fonte: [Max concurrent connections](https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/3420-streaming-api-max-concurrent-connections).

### R7 — Tennis runner: fondere le subscription per-evento — **MEDIUM-refactor**
Oggi 1 subscription (= 1 connessione) per evento (`tennis_runner.py:490-497`). Con pochi match va bene; il consolidamento in una subscription multi-evento (market_ids aggregati, stesso data_filter) libera connessioni per gli scalper. Attenzione al vincolo flumine: la fusione richiede filtri IDENTICI tra strategie (già sfruttato correttamente per capture+bot).

### R8 — `customerStrategyRef` univoco per strategia — **LOW**
Standardizzare un ref ≤15 char per ogni strategia (es. `theta`, `sniper`, `maker`, `omega`, `watchlist` — gli ultimi due già ci sono: `order_exec.py:317`, omega). Benefici: order stream filtrabile per strategia, riconciliazione senza listCurrentOrders full-scan, P&L per strategia da listClearedOrders. Flumine supporta il passaggio dal client/strategia.
Fonte: [placeOrders](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687496/placeOrders).

### R9 — Contatore transazioni GLOBALE (per conto, non per processo) — **LOW**
`MaxTransactionCount` e i budget bot sono per-processo (`config_stream.py:188`, `scalper_bot.py:420`): con M sessioni parallele il tetto effettivo è M×limite. Aggiungere un contatore condiviso (tabella/Redis) con soglia conto 5000/h e allarme a 3500. Ricordare: cancel riuscite = 0 txn → i cicli place+cancel dello scalper contano 1, non 2 (il budget attuale potrebbe essere più permissivo del necessario).
Fonte: [Transaction Charge counting](https://support.developer.betfair.com/hc/en-us/articles/20029343399836-Transaction-Charge-how-are-transactions-counted).

### R10 — Data filter a due livelli (full-depth solo dove serve) — **MEDIUM**
`EX_ALL_OFFERS`+tutto con ladder 10 (`config_stream.py:76-84`) è giusto per il Replay/recorder, ma non per ogni evento a scala: prevedere un profilo "light" (EX_BEST_OFFERS + EX_LTP + EX_MARKET_DEF, ladder 3) per gli eventi solo-monitor. NB: filtri diversi = subscription diverse in flumine → progettare gli shard di conseguenza (si integra con R3/R7).

---

## 4. Piano scala 1000 eventi/giorno (fuori scope oggi — direzione)

1. **Budget connessioni**: 10 stream/app key. Con ~200 mercati/connessione = ~2000 mercati streammabili simultanei; 1000 eventi/giorno ≠ 1000 simultanei — dimensionare sul PICCO simultaneo (stimarlo dai dati Atlante) e chiedere a Betfair l'innalzamento del limite connessioni se il picco supera ~8 connessioni utili.
2. **Architettura hub-and-spoke**: pochi processi "stream hub" (sharding mercati per subscription, ~180/shard) che pubblicano su un bus locale (WS locale già esistente: `_lc.start_channel`), e i bot come consumer — mai più 1 connessione Betfair per bot/evento.
3. **UNA sessione per app key** (o due: REST + stream), token condiviso cross-process con keepAlive centralizzato ogni 10 min e rotazione su INVALID_SESSION.
4. **Ciclo di vita subscription**: subscribe on-kickoff / unsubscribe on-final (già c'è il finalize F4) con re-subscribe via `initialClk/clk` sui restart, per non rifare full-snapshot di centinaia di mercati.
5. **Profili data filter**: full-depth (recorder/replay) solo sugli eventi tradati; light per il monitoraggio massivo; conflation 250-500ms sul monitoraggio, 0 solo dove si esegue.
6. **REST solo per catalogo e riconciliazione**: listMarketCatalogue cacheato per finestra oraria (peso ~0-1), listCurrentOrders filtrato per `customerStrategyRefs`; MAI polling book su larga scala (lo stream è la fonte).
7. **Transaction governance**: contatore globale per conto (R9), tetto dinamico per strategia, allarme a 70% della soglia 5000/h; a 1000 eventi anche il place/cancel "di igiene" va contingentato.
8. **Backpressure**: monitorare `con=true` e la latenza publish (pt vs clock) come SLO; se il consumer rallenta, prima conflation, poi shedding dei mercati light — mai accumulo buffer.
9. **Secondo app key / conto** solo come ultima leva (implicazioni contrattuali): prima esaurire segmentazione, conflation e profili.
10. **Test di carico in paper**: riusare FlumineSimulation con le registrazioni raw multi-evento per validare hub, sharding e contatori PRIMA di settembre.

---

*Documento generato il 2026-07-16. Fonti verificate a questa data; i limiti Betfair possono cambiare — ricontrollare [developer.betfair.com](https://developer.betfair.com/en/exchange-api/faq/) prima di applicare i refactor MEDIUM.*
