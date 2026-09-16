# FLUMINE — CHE COSA SA FARE DAVVERO, E COSA DEVE FARE IL BANCO

> Opus 5, 16/09/2026, delegato in **sola lettura**. Nessuna riga del repo toccata.
> Versione installata: **flumine 2.13.11** (`flumine/__version__.py:5`) + **betfairlightweight 2.23.2**.
> Due installazioni identiche (`diff` verificato): `.venv/Lib/site-packages/` (con `orjson 3.11.7`
> e `ciso8601 2.3.3`) e `%APPDATA%/Python/Python313/site-packages/` (**senza**). I percorsi dei
> sorgenti sono relativi a `site-packages/`; i percorsi del repo sono relativi alla radice.
> Requisiti: `PROCESSO_STANDARD_BOT.md` §6. Misure di §I fatte su registrazioni vere del repo.
> **Ultima versione pubblicata: 3.2.2 del 07/09/2026** — si veda §H.9, è la notizia più grossa.

Legenda verdetti: **✓** nativo · **⚠** con condizioni/config · **✗** assente, va costruito · **⊘** non applicabile.

---

## A. REPLAY DEI DATI

| Requisito | Cosa fa flumine (file:riga) | | Come lo usa il banco |
|---|---|---|---|
| Formato accettato | `FlumineHistoricalGeneratorStream._read_loop` apre con **`smart_open`** e fa `f.readlines()` (**tutto il file in RAM**), poi `listener.on_data(riga)` — `flumine/streams/historicalstream.py:259-275`. `HistoricListener.on_data` fa solo `json.loads` + `stream._process(data["mc"], data["pt"])`, **niente controllo di `op`/errori** (`:245-256`). Accetta quindi qualunque riga con `pt` e `mc`: nativo `mcm` registrato o scaricato. | ✓ | `banco_comune.py:1291` `market_filter={"markets":[raw]}` su `_live_raw/<id>/<id>.raw.jsonl`; `run_backtest.py:365,407` idem |
| `update_clk` | `HistoricalStream.create_generator` forza `self._listener.update_clk = False` (`historicalstream.py:288-291`). `MAX_LATENCY = None` (`:280`) → nessun warning di latenza. | ✓ | ereditato, mai toccato |
| `_process` | `FlumineMarketStream._process` (`historicalstream.py:35-125`): crea/aggiorna `MarketBookCache`, applica i filtri del listener, chiama `update_cache(..., active=active)`, **ritorna l'`active` dell'ULTIMO mercato del messaggio** (`:125`) — se un messaggio contiene più mercati e l'ultimo è filtrato fuori, l'intero messaggio non produce yield. | ⚠ | non usato direttamente; conta solo perché il filtro non è mai attivo (§I) |
| `marketDefinition` | `MarketBookCache._process_market_definition` (bflw `streaming/cache.py:314-348`): estrae `betDelay`, `version`, `status`, `bspReconciled`, `inPlay`, `numberOfWinners`, `numberOfActiveRunners`, `priceLadderDefinition`, runner con `status`/`adjustmentFactor`/`removalDate`. Se manca, warning esplicito (`historicalstream.py:47-55`). | ✓ | `ScannerReplay.registra_mercato` ricostruisce il **catalogo** dai `marketDefinition` (`banco_comune.py:988-1055`) — limite 1 dichiarato in testa al file |
| Runner rimossi | `SimulatedMiddleware.__call__` intercetta `runner.status == "REMOVED"` (`markets/middleware.py:56-73`) → `_process_runner_removal` (`:86-175`): l'ordine **sulla** selezione rimossa viene **azzerato e voidato**; gli ordini sulle altre selezioni subiscono il **reduction factor** se `adjustmentFactor >= 2.5` (`:159-175`), con trattamento speciale WIN/PLACE per i `MARKET_ON_CLOSE` lay. | ✓ | attivo (middleware montato). Mai sollecitato nelle registrazioni calcio → **⊘ da dichiarare nel referto** |
| `inPlay` | in `MarketBook.inplay` da `_definition_in_play` (bflw `cache.py:326,406`). | ✓ | letto da `_VistaBook.inplay` (`banco_comune.py:312`) e dal `freeze_pre_ko` dello scanner vero |
| `betDelay` | `MarketBook.bet_delay` da `marketDefinition.betDelay`; **usato davvero**: `Transaction._create_order_package` passa `bet_delay=self.market.market_book.bet_delay` (`execution/transaction.py:266`) → `calc_simulated_delay = place_latency + bet_delay` (`order/orderpackage.py:74-83`). Pre-match `betDelay=0`, in-play 1/5 s: la distinzione è **automatica e per tick**. | ✓ | `MotoreReplay.attendi_esecuzione` fa scorrere il tempo finché `elapsed_seconds > simulated_delay` (`banco_comune.py:816-844`) |
| `status` OPEN/SUSPENDED/CLOSED | `place` rifiuta se `market_book.status != "OPEN"` (`simulation/simulatedorder.py:69-75`, `ERROR_IN_ORDER`, e **`size_voided += size_remaining`**). `__call__` lapsa il residuo su `SUSPENDED` **solo al cambio di `version`** e **solo se `LAPSE`** (`:57-62`). `CLOSED` → `_process_close_market`. | ⚠ | il banco arriva a `CLOSED` (`banco_comune.py:788-790`). `SUSPENDED`: il percorso c'è, ma va **sollecitato** in uno scenario |
| `INACTIVE` | **nessuna occorrenza** in tutto il sorgente flumine. Un `marketDefinition.status="INACTIVE"` cade nel ramo `!= "OPEN"` → si comporta come sospeso. | ⚠ | non distinto: da dichiarare |
| `bsp` | `_process_sp` (`simulatedorder.py:408-455`) alla prima `bsp_reconciled=True`: LIMIT con `MARKET_ON_CLOSE`, `LIMIT_ON_CLOSE`, `MARKET_ON_CLOSE`. Richiede `actualSP` nel dato (`utils.get_sp`). | ✓ | ⊘ calcio/tennis exchange: `bspMarket:false` nelle registrazioni |
| Conflazione | **nessuna**: il replay applica ogni riga registrata. `conflate_ms` esiste solo per lo stream vivo (`streams/basestream.py:41`). Il recorder registra a conflate 0. | ✗ | costruita nel banco: `ScannerReplay.applica_book` conflata a 1000 ms per mercato (`banco_comune.py:1067-1073`), **come il pool di produzione** |
| Più file/mercati insieme, ordine per `publish_time` | `FlumineSimulation.run` ha due rami (`simulation/simulation.py:44-103`): **event group** (`event_processing=True`) che multiplexa N stream ordinando per `publish_time_epoch` con `cycles.sort()` (`:59-82`), e **singolo** che li fa uno per volta (`:87-103`). Dentro UN file i mercati sono già cronologici. | ⚠ | il banco usa **solo il ramo singolo** (`banco_comune.py:847-872`, limite 10 dichiarato): per un file = un evento è equivalente |
| `simulated_datetime` / orologio virtuale | `SimulatedDateTime.__enter__` **sostituisce `datetime.datetime`** con `NewDateTime` il cui `now()` ritorna `config.current_time` (`simulation/utils.py:7-43`); `run` entra nel context (`simulation.py:35`) e `_process_market_books` fa `self.simulated_datetime(market_book.publish_time)` a ogni book (`:110`). Da lì `BaseEvent.elapsed_seconds` (`events/events.py:47-51`) è **tempo di mercato**. `reset_real_datetime()` a inizio di ogni stream (`:57,94`). | ✓ | `MotoreReplay.esegui` riproduce il context (`banco_comune.py:850-855`) e `_a_flumine` chiama `simulated_datetime(adesso)` (`:785`) |
| `event_processing` / `process_market_book` / ordine degli handler | Ordine per book, in `simulation.py:106-151`: (1) `simulated_datetime`; (2) `_check_pending_packages(market_id)` — **esecuzione ordini in attesa**; (3) se `CLOSED` → `_process_close_market` e **continue**; (4) `market(market_book)`; (5) **middleware** (matching passivo); (6) `_process_simulated_orders` (chiude i completi + `strategy.process_orders`); (7) `process_new_market` / `check_market_book` → `process_market_book`. | ✓ | `MotoreReplay._a_flumine` ≡ `banco_comune.py:772-803` riga per riga, meno la strategia, che sta in `esegui` (`:856-871`) |

---

## B. PIAZZAMENTO SIMULATO

| Requisito | Cosa fa flumine (file:riga) | | Banco |
|---|---|---|---|
| `place_latency` + bet delay | `calc_simulated_delay()` = `place_latency (0.120) + bet_delay` per PLACE, `replace_latency (0.280) + bet_delay` per REPLACE, **solo `cancel_latency`/`update_latency`** per CANCEL/UPDATE (`order/orderpackage.py:74-83`). Rilascio: `elapsed_seconds > simulated_delay` in `_check_pending_packages` (`simulation/simulation.py:185-195`). In **paper live** è invece un `time.sleep()` vero (`execution/simulatedexecution.py:36,59,85,112`). | ✓ | riprodotto con attesa sincrona (`banco_comune.py:448-478`); latenze mai modificate → **0,120 s** |
| FOK / `minFillSize` | `place` legge `instruction["limitOrder"]["timeInForce"]` e **`minFillSize or size`** (`simulatedorder.py:116-118`): senza `minFillSize`, Betfair/flumine assumono la size intera. `min_fill_size > size` → `INVALID_MIN_FILL_SIZE` (`:126-138`). BACK: prezzo > best back → tutto cancellato; prezzo = best back → match solo se `available_size >= min_fill_size`; prezzo < best back → `_process_price_matched_vwap` (`:151-175`), simmetrico LAY (`:197-221`). **Il residuo va sempre in `size_cancelled`, mai lasciato vivo.** | ✓ | `place_order_live(fill_or_kill=True)` passa `time_in_force="FILL_OR_KILL"` senza `minFillSize`, **identico a `omega_market`** (`banco_comune.py:399-409`) |
| `persistenceType` LAPSE/PERSIST/MOC | Su `SUSPENDED` **con cambio di `version`**: `LAPSE` → `size_lapsed += size_remaining` (`simulatedorder.py:57-62`); `PERSIST` → resta vivo. `MARKET_ON_CLOSE` su LIMIT: validato al place contro `bsp_market`/`bsp_reconciled`/`inplay` (`:101-112`) e poi trattato come SP (`take_sp`, `:530-537`). **Transizione a in-play: nessuna cancellazione dei LAPSE** — flumine non la modella. | ⚠ | sempre `LAPSE` (`banco_comune.py:403`). La morte del LAPSE al passaggio in-play **non esiste**: il banco deve dichiararlo (§6.4 «l'ordine appoggiato scade alla sospensione se Betfair lo farebbe») |
| Ordine sul book corrente vs coda `_piq` | Se attraversa lo spread → `_process_price_matched` cammina i livelli (`:348-368`). Altrimenti `_piq = avail["size"]` al proprio prezzo **sul lato opposto** (`:232-238`): la size già in coda davanti a noi. | ✓ | usato come in produzione |
| `simulation_available_prices` | `False` di default (`config.py:5`). Se `True`, `_process_available` abbina anche contro i prezzi **disponibili**, azzerando `_piq` (`simulatedorder.py:52-55,499-528`) — commento nel sorgente: `# todo prevent double counting`. La doc lo dice: *"note this will double count liquidity"*. | ⚠ | banco: **mai acceso** (corretto). `run_backtest.py:385-386` lo espone come parametro — **da non usare in certificazione** |
| Dimezzamento del volume scambiato | `_calculate_process_traded`: `_traded_size = traded_size / 2`, poi `_matched = (piq + size) * 2` (`simulatedorder.py:478-497`). È **cablato, nessuna configurazione**: modella il fatto che `trd` conta ogni scambio due volte (back+lay) e assume che **metà** sia dal nostro lato. | ⚠ | subìto. Assunzione non falsificata su dati reali → da dichiarare |
| Matching progressivo con `traded_volume` | `RunnerAnalytics._calculate_traded` calcola il **delta per prezzo** fra due book (`markets/middleware.py:274-288`); `SimulatedMiddleware._process_simulated_orders` passa una **copia** del delta a ogni ordine, ordinati lay-desc/back-asc/MOC (`:182-243`); `_process_traded` consuma solo i prezzi favorevoli (`simulatedorder.py:457-476`). | ✓ | ✓ — ma vedi il **difetto del doppio middleware** in §G.1 |
| Fill parziali | `_update_matched` appende `[publish_time, price, size]` e ricalcola `size_matched`/`average_price_matched` con `wap` (`simulatedorder.py:543-546`, `utils.py:248-258`). `size_remaining = size - matched - cancelled - lapsed - voided` (`:549-561`). `BetfairOrder.size_matched` legge `current_order` che **è `self.simulated`** quando simulato (`order/order.py:199-206,460-464`). | ✓ | riletti in `_riga`/`_numeri` (`banco_comune.py:554-561,614-641`) |
| Prezzo migliore | `_process_price_matched` abbina ai **livelli migliori disponibili**, non al prezzo chiesto (`:356-366`) → `average_price_matched` può essere migliore. `best_price_execution=False` invece **fa fallire** l'ordine con `BET_LAPSED_PRICE_IMPROVEMENT_TOO_LARGE` (`:141-150,187-196`). | ✓ | default `True`: il prezzo migliore c'è. Cella «prezzo migliore» della matrice ordini **sollecitabile** |
| BSP / `LIMIT_ON_CLOSE` / `MARKET_ON_CLOSE` | Tutti implementati (`simulatedorder.py:240-253,428-448`); place rifiutato con `MARKET_NOT_OPEN_FOR_BSP_BETTING` se non BSP, già riconciliato o in-play. | ✓ | ⊘ |
| Mercato SUSPENDED al place | **Non un'eccezione**: `SimulatedPlaceResponse(status="FAILURE", error_code="ERROR_IN_ORDER")` e `size_voided += size_remaining` (`:69-75`); `execute_place` chiama `order.execution_complete()` (`execution/simulatedexecution.py:49-50`). **Prima** però interviene il control `MarketValidation` che blocca con `"Market is not open"` (`controls/tradingcontrols.py:156-163`) → `place_order` torna **`False`**. | ✓ | `place_order_live` legge il `False` e ritorna `PlaceResult(ok=False)` (`banco_comune.py:421-432`) — corretto |
| Selezione REMOVED al place | `RUNNER_REMOVED` + `size_voided` (`simulatedorder.py:92-98`) | ✓ | idem |
| `min_bet_size` / `min_bet_payout` / valuta | `SimulatedClient.CURRENCY_CODE = "GBP"` **cablata** (`clients/simulatedclient.py:17`) → `min_bet_size=1`, `min_bet_payout=10`, `min_bsp_liability=10` da `bflw.metadata.currency_parameters`. In EUR sarebbero 1 / **20** / 10. | ⚠ | il banco **apre i tetti** con `_ClienteSenzaTetti` (0/0/0, `banco_comune.py:657-687`) — scelta giusta e documentata |
| `min_bet_validation` | `client.min_bet_validation=False` salta il controllo (`tradingcontrols.py:88-91`) — alternativa più pulita alla sottoclasse. | ✓ | non usato (si usa la sottoclasse) |
| `transaction_limit` | `MaxTransactionCount`: 5000/ora (`bflw.metadata.transaction_limit`), conteggio **su ora di mercato** perché `datetime.now` è patchato (`controls/clientcontrols.py:58-86`). Rifiuta a `current_total > limit`. | ⚠ | **NON aperto**: `_ClienteSenzaTetti()` è costruito senza argomenti → resta 5000/h. §6.6 chiede tetti di flumine aperti: **buco da chiudere** (`transaction_limit=None`) |
| `trading_controls` | Di default ne girano **tre** (`baseflumine.py:75-77`) — `OrderValidation`, **`MarketValidation`**, `StrategyExposure` — più `MaxTransactionCount` per client (`:96`). Esiste un quarto, `ExecutionValidation`, **non registrato** e comunque inerte in simulazione (`tradingcontrols.py:211-213`). | ✓ | tutti attivi |
| Come si legge il rifiuto | `BaseControl._on_error` → `order.violation(msg)` → `order.status = OrderStatus.VIOLATION` + **`order.violation_msg`**, poi solleva `ControlError` catturata da `Transaction._validate_controls` che ritorna **`False`** (`controls/__init__.py:21-29`, `execution/transaction.py:230-242`). Il valore di ritorno di `place_order` è quindi l'unico segnale; `violation_msg` è la causa. | ✓ | letto correttamente (`banco_comune.py:421-432,542-544`) |
| `max_order_exposure` / `max_selection_exposure` / `max_market_exposure` | `StrategyExposure` (`tradingcontrols.py:218-333`): esposizione per ordine, per selezione (via `blotter.get_exposures`, `exclusion` sul replace) e per mercato. Default strategia: **10 / 100 / None** (`strategy/strategy.py:49-51`). | ✓ | aperti a `1e9` (`banco_comune.py:1291`, `run_backtest.py:408-409`) |
| `max_trade_count` / `max_live_trade_count` | `strategy.validate_order` (`strategy/strategy.py:156-206`): default **1e6 / 1** — con `max_live_trade_count=1` un secondo trade vivo sulla stessa selezione è **rifiutato**. Usa `reset_elapsed_seconds`/`placed_elapsed_seconds`, quindi **tempo di mercato**. | ✓ | aperti a `1e9` (`banco_comune.py:1292`) |

---

## C. CANCEL / REPLACE / UPDATE SIMULATI

| Requisito | Cosa fa flumine (file:riga) | | Banco |
|---|---|---|---|
| `cancel_order` | `Transaction.cancel_order` valida i controlli, chiama `order.cancel(size_reduction)` → stato `CANCELLING`, accoda pacchetto (`execution/transaction.py:104-122`). `BetfairOrder.cancel` **solleva `OrderUpdateError`** se manca il `bet_id`, se `size_remaining - size_reduction < 0` o se lo stato non è `EXECUTABLE` (`order/order.py:360-373`). Simulato: `market_book.status != "OPEN"` → `FAILURE/ERROR_IN_ORDER`; altrimenti `size_cancelled += min(size_reduction or size_remaining, size_remaining)` — **non è mai un errore cancellare più del residuo** (`simulatedorder.py:286-310`). | ✓ | `cancel_order_live` (`banco_comune.py:491-546`): cattura l'eccezione come **esito noto**, legge il **delta** di `size_cancelled` per decidere `ok` (`:563-584`) |
| Latenza del cancel | `cancel_latency = 0.170`, **senza bet delay** (`orderpackage.py:78-79`): Betfair non trattiene un annullo. | ✓ | stesso motore d'attesa (`banco_comune.py:448-459`) |
| `replace_order` | `execute_replace` (`execution/simulatedexecution.py:106-164`): **cancella** l'ordine, poi crea un ordine NUOVO con `trade.create_order_replacement`, gli assegna **un `bet_id` nuovo** (`self._bet_id += 1`) e lo inserisce nel blotter con `market.place_order(..., execute=False)`. Il nuovo ordine **riparte in fondo alla coda** (`_piq` ricalcolato al nuovo prezzo): la posizione si perde, come dal vero. Attesa `replace_latency + bet_delay`. | ✓ | **mai usato**: `MercatoFlumine` non espone replace. Se un bot lo userà, va aggiunto |
| `update_order` | Solo `persistenceType` su Betfair (`transaction.py:151-152`, `order/order.py:375-386`). Simulato: rifiuta se mercato non OPEN, se `persistence_enabled is False` (`INVALID_PERSISTENCE_TYPE`) o se `size_remaining == 0` (`simulatedorder.py:312-339`). | ✓ | non usato |
| `OrderStatus` | Enum a 8 valori: `PENDING`, `CANCELLING`, `UPDATING`, `REPLACING`, `EXECUTABLE`, `EXECUTION_COMPLETE`, `EXPIRED`, `VIOLATION` (`order/order.py:36-46`). `str(status)` dà `"OrderStatus.EXECUTABLE"`, `status.value` dà `"Executable"`. | ✓ | `_stato_betfair` traduce in parole Betfair (`banco_comune.py:594-609`) — difetto 10 del catalogo §7 già chiuso |
| Cancel su ordine già abbinato/parziale | Se `EXECUTION_COMPLETE` → `OrderUpdateError` **prima** di arrivare a flumine (`order/order.py:366-367`). Se parziale: cancella solo il residuo, `size_cancelled` cresce del residuo. | ✓ | gestito (`banco_comune.py:535-541`) |

---

## D. SETTLEMENT

| Requisito | Cosa fa flumine (file:riga) | | Banco |
|---|---|---|---|
| `process_closed_market` | `BaseFlumine._process_close_market` (`baseflumine.py:353-414`): `market.close_market()`, `market(market_book)`, `blotter.process_closed_market` che scrive su **ogni ordine** `runner_status`, `market_type`, `each_way_divisor`, `number_of_dead_heat_winners` (`markets/blotter.py:143-174`); poi chiama `strategy.process_closed_market`. | ✓ | **agganciato**: `banco_comune.py:788-790` chiama `_process_close_market`. Il limite 8 in testa a `banco_comune.py` riguarda il settlement **del servizio del bot**, non quello di flumine |
| `simulated.profit` | `SimulatedOrder.profit` (`simulatedorder.py:564-635`): WINNER/LOSER/PLACED, dead heat, EACH_WAY, `LINE_RANGE`. **È il lordo**: nessuna commissione. | ✓ | `run_backtest.order_profit` lo legge (`run_backtest.py:50-63`) |
| Commissione | `client.commission_base` è marcato **`# not implemented`** nel sorgente (`clients/baseclient.py:45`), default `0.05`. Unico uso: `Market.cleared()` → `round(max(profit * commission_base, 0), 2)` (`markets/market.py:239-254`), una **flat sul profitto positivo per mercato**, senza net market profit né discount rate (`SimulatedClient.DISCOUNT_RATE = 0`). Il risultato finisce solo in un log (`baseflumine.py:459-470`). | ⚠ | `run_backtest` la **ricalcola in casa**, per mercato, sul netto positivo (`run_backtest.py:156-162`) — approccio corretto e indipendente da flumine. Il banco comune **non calcola commissione**: §6.4 la richiede → **✗ da aggiungere** |
| Vincitori / void | `runner.status` WINNER/LOSER/REMOVED/PLACED da `marketDefinition` finale. `profit` ritorna **0.0** per ogni stato diverso da WINNER/LOSER/PLACED (`:634-635`): un mercato **VOID** dà quindi profitto zero, che è corretto, ma **indistinguibile** da «non regolato». | ⚠ | va distinto nel referto |
| `blotter.selection_exposure` / `market_exposure` | `markets/blotter.py:188-235` + `get_exposures` (`:237-301`), calcolati sull'**abbinato** (`mb`/`ml`) più il **residuo peggiore** (`ub`/`ul`). | ✓ | non usato: l'esposizione la calcola il bot |
| Cleared orders simulati | `_process_close_market` fabbrica una `ClearedOrders` **vuota** e una `ClearedMarkets` con `market.cleared(client)` (`baseflumine.py:382-397`). `blotter.process_cleared_orders` non trova nulla → `order.cleared_order` resta `None`. | ⚠ | irrilevante: in simulazione `order.profit` passa da `simulated.profit` (`order/order.py:276-284`) |
| `order.simulated.matched` | Lista di `[publish_time_epoch (int, ms), price, size]` (`simulatedorder.py:28,543-546`). **Il publish time c'è**: è la traccia forense di ogni fill. | ✓ | **non letta**: `_riga` espone solo gli aggregati (`banco_comune.py:614-641`). §6.8 chiede i fill → **✗ da esporre** |

---

## E. PIÙ CLIENT E STRATEGIE NELLO STESSO FRAMEWORK

| Requisito | Cosa fa flumine (file:riga) | | Banco |
|---|---|---|---|
| `add_client` | Accetta N client (`baseflumine.py:85-96`); il primo è il default. Aggiunge **automaticamente** `SimulatedMiddleware` se c'è un client simulato o paper (`:91-94`) e registra `MaxTransactionCount` per client (`:96`). | ✓ | un solo client (`banco_comune.py:1297`) |
| `place_order(client=)` | Instrada per **ordine**: `Market.place_order(..., client=...)` → `Transaction(client=...)` → `client.execution.handler` (`markets/market.py:84-98`, `execution/transaction.py:41-60`). | ✓ | non usato |
| `order.simulated` per ordine | `SimulatedOrder.__bool__` = `config.simulated or order.client.paper_trade` (`simulatedorder.py:658-661`), cachato in `order._simulated` e **ricalcolato a `update_client`** (`order/order.py:104,185-187`). Quindi paper e live **convivono nello stesso processo**, ordine per ordine. | ✓ | ⊘ (tutto simulato) |
| `SimulatedMiddleware` salta i non simulati | `if o.simulated` nel filtro degli ordini vivi (`markets/middleware.py:196,215`) e `if order.simulated` nel runner removal (`:94`). | ✓ | ⊘ |
| `Clients` e vincoli | `add_client` solleva `ClientError` su client duplicato o **stesso `username` nello stesso venue** (`clients/clients.py:31-46`). `SimulatedClient` senza `username` genera un uuid corto (`baseclient.py:41`) → due client simulati convivono. `clients.simulated` è True se **almeno uno** è simulato o paper (`:80-86`). | ⚠ | ⊘ |
| `client.paper_trade` | `add_execution` instrada su `flumine.simulated_execution` (`baseclient.py:83-84`). In paper le latenze diventano `time.sleep` reali e il lavoro passa dal **thread pool** (`execution/simulatedexecution.py:14-31`). | ✓ | ⊘ replay; è la base di `PROGETTO_PAPER_VIA_FLUMINE` §2 |
| `SimulatedOrderStream` | Thread che ogni `streaming_timeout` (0,25 s) rilegge il blotter e sintetizza un `CurrentOrdersEvent` (`streams/simulatedorderstream.py:17-43`). Creato **solo per `paper_trade`** (`streams/streams.py:92-94`). | ✓ | ⊘ (`FlumineSimulation` non avvia gli stream, `streams.py:303-311`) |
| `keep_alive` / `update_account_details` | `SimulatedClient` li rende no-op e fabbrica `AccountDetails(discountRate=0, currencyCode="GBP")` (`clients/simulatedclient.py:18-30`). `FlumineSimulation` non registra worker (`_add_default_workers` non sovrascritto → `baseflumine.py:130-131` ritorna). | ✓ | ⊘ |

---

## F. LIVE / PAPER IN PRODUZIONE

| Requisito | Cosa fa flumine (file:riga) | | Repo |
|---|---|---|---|
| `BetfairClient(paper_trade=True)` | Cambia **solo l'esecuzione**: `SimulatedExecution` invece di `BetfairExecution` (`baseclient.py:83-84`) e `SimulatedOrderStream` al posto di `OrderStream` (`streams/streams.py:92-94`). **Lo stream di mercato resta vero**, login/keep-alive/account veri. `config.simulated` **resta `False`** (`baseflumine.py:492-496`): la discriminante è `order.client.paper_trade`. | ✓ | `runner.py:1442-1451` (`PROGETTO_PAPER_VIA_FLUMINE` §2) |
| `simulated` vs `paper_trade` | `config.simulated` è **di processo** e lo mette `BaseFlumine.__enter__` in base a `SIMULATED` (`baseflumine.py:493-496`); `paper_trade` è **per client**. Il primo usa il tempo virtuale, il secondo il tempo vero. | ⚠ | `banco_comune.simulazione_flumine` salva/ripristina `simulated`, `place_latency`, `cancel_latency` (`banco_comune.py:690-712`) ma **non `simulation_available_prices`** né `simulated_strategy_isolation`: `run_backtest.py:376-378,417` ripristina anche il primo → **allineare** |
| `config.*` | `simulated=False`, `simulated_strategy_isolation=True`, `simulation_available_prices=False`, `place/cancel/update/replace_latency = 0.120/0.170/0.150/0.280`, `order_sep="-"`, `max_execution_workers=32`, `async_place_orders=False` (`config.py:3-28`). `simulated_strategy_isolation=True` = ogni **strategia** riceve una copia del delta scambiato → **N strategie sullo stesso runner contano N volte la stessa liquidità** (`markets/middleware.py:193-206`). | ⚠ | banco: una sola strategia → nessun doppio conteggio **fra strategie** (ma vedi §G.1) |
| `Flumine` vs `FlumineSimulation` | `Flumine.run` è un loop su `handler_queue` (`flumine.py:23-66`) con 4 worker di default (`:68-113`: `keep_alive`, `poll_market_catalogue` 60 s, `poll_account_balance` 120 s, `poll_market_closure` 60 s). `FlumineSimulation` è **monothread**, senza worker, senza `MarketCatalogue`, e `handler_queue` è una **lista** non una `Queue` (`simulation/simulation.py:27,153-155`). `_process_end_flumine` chiama solo `strategies.finish` (`baseflumine.py:472-473`). | ✓ | il banco usa `FlumineSimulation` e itera la lista a mano (`banco_comune.py:786,821-834`) |
| `market.closed` / rimozione mercati | In live i mercati chiusi da >3600 s vengono rimossi; **in simulazione no** (`_remove_market(market, clear=False)`, `baseflumine.py:401-414`) → in un replay lungo i mercati chiusi **restano in memoria**. | ⚠ | nessun impatto su un evento per volta |
| Cosa NON è simulabile con stream vivo | `listMarketCatalogue` (nomi runner, competizione), `listCurrentOrders` reale, fondi, minimi di giurisdizione .it, `INVALID_PROFIT_RATIO`, `BET_TAKEN_OR_LAPSED` da market version reale, cancellazioni altrui in coda, e **il fatto che un ordine simulato si abbina solo se quel mercato riceve aggiornamenti**. | ✗ | limiti 1/3/6 dichiarati in `banco_comune.py:49-96` |

---

## G. LIMITI NOTI E TRAPPOLE

**G.1 — DIFETTO ATTIVO E MISURATO: `SimulatedMiddleware` montato DUE VOLTE.**
`BaseFlumine.add_client` ne aggiunge già uno quando il client è simulato (`baseflumine.py:91-94`); il repo ne aggiunge un **secondo** a mano in **21 punti** (13 fuori dalle copie di laboratorio), fra cui `banco_comune.py:1298`, `run_backtest.py:400`, `Betfair/mike/tools/replay_registrazioni.py:587`, `scalper/run_scalper.py:78`, `scalper/run_theta.py:116`, `tennis_scalper/*`. Nella 2.13.11 **non c'è de-duplicazione** (aggiunta in flumine 3.1.0). Ogni middleware tiene la propria `RunnerAnalytics` e passa il proprio delta di `traded_volume`: **la coda viene consumata due volte per ogni book.**
Prova eseguita nello scratchpad su `_live_raw/36006953` (LAY appoggiata 3.000 € al best back, tutto il resto identico):

| | `size_matched` | n. fill |
|---|---|---|
| **1 middleware** (solo quello automatico) | **85,72 €** | 6 |
| **2 middleware** (automatico + `add_market_middleware`) | **200,34 €** | 13 |

**+134 % di riempimento passivo fantasma.** È il difetto 8 e 13 del catalogo §7 in forma nuova: il fill non è scritto a mano, è **contato due volte**. **Azione: togliere `add_market_middleware(SimulatedMiddleware())` ovunque** (flumine lo monta da sé) e aggiungere al banco un'asserzione `len(quadro._market_middleware) == 1`. Falsificazione: rimetterlo e il referto deve diventare rosso.

| Trappola | Dettaglio (file:riga) | | Banco |
|---|---|---|---|
| `flumine/__init__.py` ritocca bflw | `bettingresources.RunnerBookEX = EX` / `RunnerBookSP = SP` (`flumine/__init__.py:12-14`): i livelli diventano **`dict {'price','size'}`** invece di `PriceSize`, **per tutto il processo**, live compreso. | ⚠ | risolto: `_Livello`/`_VistaEx` ritraducono in `.price/.size` (`banco_comune.py:246-330`), con l'avviso in testa. È la ragione per cui il banco paper **non può** vivere nel processo dello scanner |
| Ladder come `dict` | vedi sopra; `get_price`/`get_size` di flumine leggono `data[level]["price"]` (`utils.py:163-182`). | ⚠ | `_offer_price`/`_offer_size` leggono dict, tupla e oggetto |
| `order.status` Enum | `str(status)` ≠ parola Betfair (`order/order.py:36-46`). | ✓ | `_stato_betfair` (`banco_comune.py:594-609`) |
| `elapsed_seconds` sull'orologio | `BaseEvent._time_created` è preso con `datetime.now()` **patchato** (`events/events.py:42-51`): è tempo di mercato. Ma il `publish_time` fra mercati diversi **non è monotono** — il banco ha misurato 47,3 % di book all'indietro, fino a −182 s (`banco_comune.py:749-762`). Con tempo che torna indietro `elapsed_seconds` diventa **negativo**, `StrategyExposure`/`validate_order` rifiutano ordini legittimi e il bet delay perde senso. **flumine non se ne difende** (`simulation.py:110` passa il valore così com'è). | ✗ | **coperto dal banco**: orologio monotono in `_a_flumine` (`banco_comune.py:779-785`) con contatore `book_in_ritardo`. `run_backtest.py` (che usa `framework.run()`) **NON è protetto** |
| `simulated_datetime` reset | `reset_real_datetime()` a inizio di ogni stream/gruppo (`simulation.py:57,94`): fra due eventi il tempo torna a **ora reale**, non all'ultimo publish time. | ⚠ | il banco fa un evento per volta |
| `market_book.streaming_unique_id` | `Streams._increment_stream_id` avanza di **10.000** (`streams/streams.py:317-319`); `strategy.stream_ids` usa `historic_stream_ids` quando ci sono (`strategy/strategy.py:237-242`). Un book con id non appartenente alla strategia viene **saltato in silenzio** (`simulation.py:141`). | ⚠ | filtro esplicito in `banco_comune.py:863` |
| Thread safety | `FlumineSimulation` è **monothread**; `SimulatedExecution.handler` usa il thread pool **solo in paper** (`execution/simulatedexecution.py:27-30`). `MaxTransactionCount` ha un lock (`clientcontrols.py:37`). `Blotter` **non è thread-safe**. | ✓ | ⊘ |
| Memoria su registrazioni lunghe | `_read_loop` fa `f.readlines()`: **tutto il file in RAM** (`historicalstream.py:267-268`) — 26 MB di raw ≈ 26 MB di stringhe, più le cache. La doc consiglia 8 mercati per processo *«prevents memory leaks»*. In simulazione i mercati chiusi non vengono rimossi (`baseflumine.py:413-414`). | ⚠ | un evento per volta: ok. Con `event_processing` su molti eventi: da sorvegliare |
| `smart_open` e `.gz` | `smart_open.open` in `_read_loop` e in `get_file_md`/`file_line_count` (`historicalstream.py:267`, `utils.py:77,85`): **`.gz`, `.bz2`, `s3://` funzionano già**, senza codice nuovo. | ✓ | non sfruttato: i raw sono in chiaro (6,5 MB → 26 MB per evento) |
| Timezone | Tutto UTC: `publish_time` da `utcfromtimestamp(pt/1e3)`, `strip_datetime` con `lru_cache` (bflw `baseresource.py:23-36`). `create_time` per le corse usa l'ora locale del nome file (`utils.py:389-395`) — ⊘ calcio. | ✓ | `banco_comune.py:940` usa `timezone.utc` |
| `market_types` / `country_codes` | Filtrano il **FILE**, leggendo il `marketDefinition` della **prima riga** (`streams/streams.py:44-65`, `utils.py:81-96`). Su un file che contiene 21 mercati di tipi diversi giudicano l'intero evento dal primo mercato trovato: **inutilizzabili e pericolosi**. | ✗ | non usati (bene). Il filtro per tipo, se serve, va fatto **a monte** (§I.4) |

---

## H. COSA DICE LA DOCUMENTAZIONE E COSA FA IL CODICE

Premessa: **`flumine.readthedocs.io` e `betfairlightweight.readthedocs.io` restituiscono 404**. La doc ufficiale è su `betcode-org.github.io/flumine/` e descrive la **3.x**, non la 2.13.11 installata.

1. **Quickstart inutilizzabile sulla nostra versione.** Oggi il sito mostra `BetfairHistoricalStream(file_path=..., listener_kwargs=...)` passato a `ExampleStrategy(stream=...)`; sulla 2.13.11 la firma è `BetfairHistoricalStream(framework, market_filter=..., output_queue=False)` + `streams=[...]`. Copiare dal sito dà `TypeError`. La forma usata dal repo (`market_filter={"markets":[path]}`) **non è documentata da nessuna parte**: è quella dei test d'integrazione della libreria.
2. **`SimulatedMiddleware`: la doc non dice mai di aggiungerlo, il codice lo aggiunge da sé** (`baseflumine.py:91-94`). Il repo lo aggiunge lo stesso, in 21 punti → §G.1. L'unica cosa che la doc dice di fare a mano è **toglierlo** per andare più veloce.
3. **Trading controls: la doc ne elenca 2** (`OrderValidation`, `StrategyExposure`), **il codice ne registra 3** (c'è anche `MarketValidation`) e ne definisce 4 (`ExecutionValidation`, mai registrato). `violation_msg` non è documentato.
4. **`commission_base`**: la doc lo elenca come *"default commission"*; il codice lo marca **`# not implemented`** (`baseclient.py:45`) e lo usa solo in `Market.cleared` come flat sul profitto positivo.
5. **`SimulatedClient.CURRENCY_CODE = "GBP"` cablata**: mai menzionata dalla doc. In EUR `min_bet_payout` sarebbe 20, non 10.
6. **Latenze**: la doc nomina `place_latency` & co. ma **non pubblica i valori** (0,120 / 0,170 / 0,150 / 0,280 s). Chi legge solo la doc non sa che una latenza è già applicata.
7. **`_piq` e il `traded/2` non sono documentati.** La doc dice solo *"Queue positioning based on liquidity available"*. L'assunzione «metà del volume è dal mio lato» è invisibile.
8. **Limiti che la doc AMMETTE** (issue #192, ancora aperta): *"Queue cancellations"*, *"Double counting of liquidity (active)"*, *"Currency fluctuations"* — più, fra i TODO: validare il mercato aperto, validare il runner attivo, validare `marketVersion`, cancellare i LAPSE al market version update, applicare gli aggiustamenti non-runner agli ordini pendenti.
9. **Versione: siamo indietro di una major.** 2.13.11 = 05/05/2026; **3.2.2 = 07/09/2026**. Voci rilevanti uscite dopo:
   - **3.2.0** — *«Dynamic passive matching added to simulation engine»* (tocca esattamente la coda passiva), *«Prevent infinite loop on cancel»*, *«#777 Add `event_type_ids` market filter for simulation»*, bflw a 2.24.0.
   - **3.1.0** — de-duplicazione di middleware/worker/controls (**eliminerebbe §G.1 alla radice**); *«confirm runner has an adjustment factor before executing»*.
   - **3.0.0** — **breaking**: stream per strategia, `file_path` al posto di `market_filter`, Python 3.9 droppato.
   *Guadagno dell'aggiornamento*: matching passivo migliorato, niente doppio middleware, filtro per sport. *Rischi*: la 3.0.0 rompe l'inizializzazione in **21 punti** (13 fuori dalle copie di laboratorio) del repo e **cambierebbe i numeri** di ogni certificazione già firmata. **Raccomandazione: non aggiornare ora**; chiudere §G.1 a mano, e valutare la 3.x come lavoro a sé, con ri-certificazione completa e confronto prima/dopo sugli stessi eventi.
10. **`event_type_ids` nei `listener_kwargs` è documentato ma NON esiste nella 2.13.11** (zero occorrenze nel sorgente).
11. **`lightweight=True`**: la doc bflw lo consiglia per il backtest, flumine lo **vieta** con un `assert` (`baseclient.py:37`). Vale solo per un listener costruito a mano (§I.3).
12. **Errore nella doc `markets.md`** (v2 e master): l'esempio di middleware custom chiude con `framework.add_logging_control(CustomMiddleware())` invece di `add_market_middleware`.
13. **Mercati PLACE / dead heat**: la doc (`known_issues`, solo 3.x) dichiara che il profitto simulato **ignora i dead heat**. ⊘ per calcio e tennis.

---

## I. PRESTAZIONI — MISURE REALI, PRIMA E DOPO

Tutte le misure sono fatte con `.venv/Scripts/python.exe` (**con** `orjson` e `ciso8601`), logging disattivato, GC disattivato, su registrazioni vere del repo. Script nello scratchpad, nulla scritto nel repo.

**I.1 — La scoperta principale: il replay crea 7,6 volte i MarketBook che servono.**
`_read_loop` emette, **per ogni riga del file**, un `MarketBook` per **ogni cache attiva**, anche per i mercati che quel messaggio non ha toccato (`historicalstream.py:269-275`).

| `_live_raw/36006953` (6,5 MB, 21.356 righe, **21 mercati**) | tempo | MarketBook creati |
|---|---|---|
| Baseline (3 esecuzioni) | **13,8 / 14,2 / 15,1 s** | **448.476** |
| Aggiornamenti di mercato realmente presenti nel file | — | **58.801** |
| `FlumineSimulation.run()` completo, strategia no-op | **36,4 s** | 413.128 `process_market_book` |

Profilo (`cProfile`, ordinato per `tottime`): `MarketBook.__init__` **10,26 s** su 30,2 s totali, `create_resource` 4,54 s, `RunnerBookCache.serialise` 2,19 s, `dict.get` 4,25 s su 11,0 M chiamate. **`json.loads` vale 0,52 s (stdlib) / 0,24 s (orjson): il 2-3 % del totale.**

**I.2 — Emettere solo i mercati cambiati: 3,8×-5,5×.** Sovrascrivendo `_read_loop` per creare le risorse solo delle cache toccate dal messaggio corrente (≈10 righe, gli `id` sono già nel messaggio):

| | baseline | solo cambiati | guadagno |
|---|---|---|---|
| `36006953` (6,5 MB, 21 mercati) | 14,2 s / 448.476 mb | **4,5 s / 58.801 mb** | **3,2×** |
| `35768297` (26 MB, 103.431 righe) | **79,4 s** / 2.378.913 mb | **14,5 s** / 231.790 mb | **5,5×** |

⚠️ **Non è gratis, e va dichiarato**: oggi un tick di *qualunque* mercato fa avanzare l'orologio e quindi può rilasciare il bet delay di un ordine su *un altro* mercato (`_check_pending_packages` è chiamato per `market_id`, ma il tempo avanza sempre). Con l'emissione selettiva il rilascio richiede un aggiornamento **di quel** mercato. Il comportamento vero di Betfair è il primo (la REST risponde dopo `betDelay` a prescindere): se si adotta l'ottimizzazione, l'orologio va fatto avanzare comunque **prima** del filtro. È un dettaglio money-critical: va implementato e falsificato, non copiato.

**I.3 — `orjson` / `ciso8601`: già installati nel `.venv`, irrilevanti qui.** `pip install flumine[speed]` porta `orjson` (Rust) e `ciso8601` (C). Misurato: `json.loads` di tutto il file 0,52 s → **0,24 s**, cioè **~1,5 % del replay**. `strip_datetime` è già `lru_cache`. **Da fare comunque** (l'installazione `%APPDATA%` ne è priva: chi lancia con quel Python è più lento e usa un secondo motore JSON — due ambienti che non danno gli stessi tempi né gli stessi warning). `lightweight=True` dimezzerebbe i tempi (**3,98 s vs 20,5 s**) ma flumine **rifiuta di partire** con un client lightweight (`baseclient.py:37`) e il banco legge attributi, non dict: **non praticabile**.

**I.4 — Pre-filtro dei mercati.** Riscrivendo il raw con i soli 8 tipi che i bot calcio usano (MATCH_ODDS, O/U 1.5-4.5, CORRECT_SCORE, HALF_TIME_SCORE, BTTS): filtro 1,5 s, poi replay **5,3 s** (143.568 mb) contro 14,2 s. **Ma**: cambia il dato di ingresso e `PROCESSO_STANDARD_BOT.md` §6.1 esige lo stream registrato tale e quale. Utilizzabile **solo** come cache derivata, con l'elenco dei tipi esclusi nel referto. `market_types` di flumine **non** serve (§G: filtra il file, non i mercati).

**I.5 — Middleware.** La doc: *«se non ti serve il middleware di simulazione toglilo da `framework._market_middleware`, può migliorare drasticamente i tempi»*. Misurato: `sim` 36,4 s con middleware, **36,5 s senza** → su questa registrazione, **zero ordini = zero guadagno**. Il costo del middleware è proporzionale agli ordini vivi, non ai book. Vale invece il contrario: **il secondo middleware di troppo (§G.1) costa un giro completo di `RunnerAnalytics` per ogni book**.

**I.6 — `simulation_available_prices=True`: 30,2 s contro 36,4 s.** È più veloce perché riempie prima gli ordini (`_piq` azzerato). **Non è un'ottimizzazione: è un cambio di risultato** e raddoppia la liquidità. Mai in certificazione.

**I.7 — `listener_kwargs`.** `inplay=True` su questa registrazione: 17,6 s contro 18,1 s, MarketBook 394.802 contro 448.476 (−12 %). Poco, perché la registrazione è quasi tutta in-play. Su registrazioni con lungo pre-match `seconds_to_start` taglia molto di più. **Attenzione**: filtrare fa perdere il `pre_ko` e le linee O/U pre-KO che il banco usa (`banco_comune.py:947`). **Non usarlo senza rileggere la strategia.**

**I.8 — Multiprocessing per evento.** `run_backtest.run_backtest` cicla gli eventi **in serie** (`run_backtest.py:469-470`); `certifica.py` idem. La simulazione è **CPU-bound** e il GIL rende i thread inutili (doc). Un `ProcessPoolExecutor` con un evento per processo è la leva più grande e **non cambia nessun numero** (gli eventi sono indipendenti; `flumine.config` è per processo, quindi l'isolamento migliora invece di peggiorare). Su 54 registrazioni e 8 core: da ~1 h a ~10 min. **Costo: una funzione modulo-livello e `if __name__ == "__main__"`.** Unica cautela: il referto deve restare deterministico → raccogliere i risultati e ordinarli per `event_id` prima di aggregare.

**I.9 — Logging.** `certifica.py:170` fa `logging.basicConfig(level=logging.WARNING)`: già ragionevole. Il sorgente flumine è pieno di `logger.info(..., extra={...})` con dizionari costruiti **prima** della chiamata (es. `execution/baseexecution.py:43-55`, `markets/market.py:52-56`): a `INFO` si paga la costruzione degli `extra` per ogni ordine e ogni mercato. La doc consiglia `logger.setLevel(logging.CRITICAL)`. **Raccomandazione: `CRITICAL` sui logger `flumine` e `betfairlightweight` durante il replay**, lasciando `WARNING` sui logger del repo.

**I.10 — `smart_open` e i `.gz`.** `_read_loop` passa da `smart_open`: comprimere le registrazioni con gzip **funziona senza toccare nulla** e riduce 26 MB a ~3 MB per evento. Costo: decompressione in RAM, ~+10 % di tempo. Da valutare per l'archivio, non per il percorso caldo.

**Ordine di attacco consigliato:** (1) chiudere §G.1 — *corregge i numeri*, non i tempi; (2) multiprocessing per evento (**8×**, nessun rischio sui numeri); (3) logging a `CRITICAL` (gratis); (4) `flumine[speed]` anche su `%APPDATA%` (allinea i due ambienti); (5) emissione selettiva dei MarketBook (**3-5×**) solo dopo aver risolto e falsificato il rilascio del bet delay.

---

## LE 10 COSE CHE FLUMINE **NON** FA

| # | Cosa manca | Il banco oggi |
|---|---|---|
| 1 | **Cancellazioni altrui in coda**: `_piq` scende **solo** col volume scambiato, mai perché qualcuno davanti ritira (limite ammesso, issue #192, `simulatedorder.py:47` `# todo estimated piq cancellations`) | ✗ non modellato → **⊘ da dichiarare**: la coda simulata è più lenta del vero |
| 2 | **Minimi di giurisdizione .it** (BACK 2,00 / LAY 0,50), place-and-trim, `INVALID_PROFIT_RATIO`, fondi insufficienti | ✗ — limite 3 dichiarato (`banco_comune.py:66-72`); `place_submin_live` piazza diretto (`:586-590`) |
| 3 | **Cancellazione dei LAPSE al passaggio in-play** (flumine lapsa solo su `SUSPENDED` + cambio versione) | ✗ **da costruire o dichiarare**: §6.4 lo chiede |
| 4 | **Commissione**: `commission_base` è `# not implemented`, flat 5 % sul profitto positivo, discount rate 0 | ⚠ `run_backtest.py:156-162` la calcola in casa; **il banco comune no** → ✗ da aggiungere |
| 5 | **Catalogo di mercato** (nomi runner, competizione): `MarketCatalogue` non esiste in simulazione | ✗ ricostruito da `marketDefinition` + sidecar (`banco_comune.py:988-1055`); CORRECT_SCORE/HALF_TIME_SCORE restano senza nome |
| 6 | **Conflazione**: il replay applica ogni riga; la produzione conflata a 1000 ms | ✗ costruita: `ScannerReplay.applica_book` (`banco_comune.py:1067-1073`) |
| 7 | **Orologio monotono**: `publish_time` fra mercati diversi torna indietro nel 47 % dei book | ✗ costruito in `banco_comune.py:779-785`; **`run_backtest.py` NON è protetto** |
| 8 | **Stato `INACTIVE`** distinto da `SUSPENDED` | ✗ indistinto → ⊘ |
| 9 | **De-duplicazione dei middleware** (arrivata in 3.1.0) | ✗ **difetto attivo**, §G.1 |
| 10 | **Attesa sincrona del bet delay dentro il piazzamento**: flumine rilascia al giro dopo, quando la funzione del bot ha già restituito | ✗ costruito: `MotoreReplay.attendi_esecuzione` (`banco_comune.py:816-844`) |

Da dichiarare **⊘** nei referti calcio/tennis exchange: BSP / `LIMIT_ON_CLOSE` / `MARKET_ON_CLOSE`, dead heat e mercati PLACE, `EACH_WAY`, `LINE_RANGE`, runner rimossi con reduction factor, BETDAQ, `event_processing` multi-mercato, `SimulatedOrderStream`, worker e `MarketCatalogue`.

## LE 5 IMPOSTAZIONI DEL BANCO CHE DIVERGONO DAL COMPORTAMENTO REALE

| # | Divergenza | Effetto | Raccomandazione |
|---|---|---|---|
| 1 | **Doppio `SimulatedMiddleware`** (`banco_comune.py:1298`, `run_backtest.py:400`, +14 altri) | **+134 % di riempimento passivo misurato** (85,72 € → 200,34 €). Ogni numero di fill passivo mai prodotto da questo banco è **sovrastimato** | **Togliere la chiamata ovunque** (flumine lo monta da sé), asserire `len(_market_middleware) == 1`, falsificare rimettendolo, e **rifare** le certificazioni che contengono ordini appoggiati |
| 2 | **Valuta GBP** del `SimulatedClient` (`clients/simulatedclient.py:17`) | i minimi sono sterlina (1 / 10 / 10) invece di euro (1 / **20** / 10) | Il banco li azzera già (`_ClienteSenzaTetti`, `banco_comune.py:674-687`): **giusto**, perché il minimo vero è quello di giurisdizione .it e lo gestisce il place-and-trim. **Da dichiarare nel referto**, non da cambiare. Alternativa più pulita: `min_bet_validation=False` sul client |
| 3 | **`transaction_limit` non aperto**: `_ClienteSenzaTetti()` eredita 5000/ora su **ora di mercato** | uno scenario ad alta frequenza verrebbe frenato **da flumine**, non dal bot — esattamente il difetto 11 del catalogo §7 | **Passare `transaction_limit=None`** e, se serve misurare il limite vero, farlo in uno scenario dedicato (§6.6) |
| 4 | **Dimezzamento del volume (`traded/2`) e `_piq` senza cancellazioni** (`simulatedorder.py:479`, `:47`) | non configurabile; assume che metà del `trd` sia dal nostro lato e che nessuno davanti ritiri. Direzionalità del flusso ignorata | **Non toccare il motore.** Misurare l'errore: confrontare i fill simulati con gli ordini **veri** già eseguiti in produzione sugli stessi mercati, e scrivere lo scarto nel referto. Finché non è misurato, i fill passivi vanno letti come **stima**, non come fatto |
| 5 | **Latenza di piazzamento 120 ms fissa** (`config.py:21`) e `simulation_available_prices` non ripristinato da `simulazione_flumine` (`banco_comune.py:702-706`) | 120 ms è il default della libreria, non una misura nostra; il flag non ripristinato può far mentire ciò che gira dopo nello stesso processo (è il difetto che `simulazione_flumine` nasce per evitare) | **Misurare** la latenza REST vera dai log di produzione e metterla in `config.place_latency`; **aggiungere `simulation_available_prices` e `simulated_strategy_isolation`** alla lista di salvataggio/ripristino, come fa già `run_backtest.py:376-378,417` |

**Terza riga di conflate**: il banco conflata a 1000 ms **solo verso lo scanner** (`banco_comune.py:1067-1073`), mentre a **flumine** arrivano tutti i tick. È corretto — in produzione lo scanner riceve conflato e il motore ordini riceve tutto — ma va scritto nel referto, perché è la ragione per cui il numero di book visti dal bot e quelli visti dal matching **non coincidono**.
