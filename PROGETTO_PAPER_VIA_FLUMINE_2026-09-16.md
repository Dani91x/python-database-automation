# PROGETTO — IL PAPER PASSA DA FLUMINE, PER TUTTI I BOT (C.8)

> Architetto: Opus 5, 16/09/2026. **Documento di progetto, nessuna riga di codice toccata.**
> Ordine dell'utente: «il paper deve essere lo specchio della realta', quindi utilizziamo
> flumine per tutto» (`PIANO_CERTIFICAZIONE_DEFINITIVA_2026-09-16.md` §5.3).
> Perimetro: `PIANO_...:§5.8` (Omega, Safe base/esatto/punta/tennis, Mike, scalper calcio,
> 4 bot tennis). **Le strategie non si toccano**: cambia solo COME un ordine paper si abbina.

---

## 1. Mappa dei percorsi ordine, oggi

| Bot / modalita' | Ingresso | Dove avviene il fill | Bet delay | FOK | Minimo .it / place-and-trim | Riconciliazione | Settlement |
|---|---|---|---|---|---|---|---|
| **Omega paper** | `omega_service.py:1461` `_place_one`, ramo `:1531` | `omega_engine.py:280` `paper_fill` — cammina la ladder dello **snapshot del feed**, mai il volume scambiato | **NO** (P4) | **NO in apertura**: il parziale e' accettato (`omega_service.py:1556-1563`) | no (`min_stake` 0,5 copre il lay .it) | `reconcile_pending` `:2263`, ogni ciclo 20 s | `settle_open` `:2447`, REST `read_market` |
| **Omega live** | `_place_one` `:1566` | gate `:1678` aperto → coda; altrimenti REST `omega_market.py:521`, `timeInForce` a `:567` | Betfair | **SI** REST | `place_submin_live` esiste (`omega_market.py:672`) ma **Omega non lo usa** | idem + `_poll_one_flumine_live_trade` `:2082` | idem |
| **Omega, ramo coda (paper e live)** | `_flumine_enqueue_place` `:1743` | `live_order_worker` nel runner → flumine | **SI** (flumine) | SI live; in paper quasi-FOK software `paper_fill_ttl_s` `:1966` | `action="place"` fisso `:1776` | `poll_flumine_pending` `:2204` | idem |
| **Safe paper (4 strategie)** | `execution.py:234` `place`, ramo `:347` | `omega_engine.paper_fill` sulla ladder a **un livello** costruita da `bot_service.py:3299` `_paper_ladder` | **NO** | **SI**: parziale = errore (`execution.py:368-370`) | `_min_size_live` `:69-88` (back 2,00 / lay 0,50); submin **non** raggiunto in paper legacy | `reconcile_pending` `bot_service.py:674`, ogni ciclo 2 s | `settle_open` `bot_service.py:888` |
| **Safe live** | `execution.py:409-419` | REST `place_order_live` / `place_submin_live` | Betfair | SI (`order_exec.py:292`) | SI | idem | idem |
| **Safe, ramo coda** | `execution.py:311` gate → `enqueue_place` `:556` | worker + flumine | SI | **SI in entrambe le modalita'** (`execution.py:632`); `place_submin` senza FOK in entrambe `:609-616` | `action="place_submin"` `:317` | `poll_flumine` `bot_service.py:644` | idem |
| **Mike paper** | `service.py:2456-2496` | taker: gate prezzo `service.py:538-552` + `paper_fill`; lay appoggiata: `_resting_filled` `service.py:1292-1298` (proxy sul best back, **non** sul volume) | **SI, in casa**: differimento del piazzamento `service.py:2456-2490` + `:2393-2427` | SI sul taker (`execution.py:368`) | `exact_sizes=True` di default → centesimo | `_reconcile_trades` `:2697` (30 s), `_reconcile_unknown` `:2798` | `_settle_trades` `:2979`, 2 `listMarketBook`/partita |
| **Mike live** | `service.py:481` / `_piazza_resting_live` `:900` | REST `omega_market.place_order_live`; resting con `fill_or_kill=False` `service.py:954-958` | Betfair | SI sul taker, NO sul resting | `place_submin_live` `service.py:143-155` | `_segui_resting_live` `:1246` | idem |
| **Mike, ramo coda** | `execution.py:311` | **spento**: `service.py:575` forza `execution_mode='rest'` salvo `MIKE_USE_FLUMINE_QUEUE=1` | — | — | la **lay appoggiata non passa mai** da `execution.place` (`service.py:790-792`): non e' accodabile | — | — |
| **Scalper calcio (scalper/sniper/theta)** | `scalper_bot.py:2056-2066` `market.place_order` | **DENTRO flumine**: `Flumine(clients.BetfairClient(..., paper_trade=session_paper))` `scalper_session.py:815-817`, kwargs `:244-259` | **SI**, e con betDelay rinfrescato: `install_fresh_delay_execution` `scalper_session.py:818-824` | **NO** (nessun `timeInForce` in tutto `Betfair/stream/`) | no (LAPSE resting per disegno) | `_order_mirror_loop` `scalper_session.py:330-353` | settlement simulato flumine, `scalper_bot.py:837-854` |
| **4 bot tennis** | `tennis_*_bot.py` `market.place_order` (LimitOrder LAPSE) | **DENTRO flumine**: `tennis_runner.py:109-147` `build_order_client`, PAPER a `:138-142` | **SI** + `_wire_paper_execution` `:150-159` | **NO** | in paper `size_step=0`, `live_min_bet=0` (`tennis_runner.py:592-596`) | `_reconcile_bots` `tennis_live_order_worker.py:821-860` | `tennis_live_positions` |

**Conseguenza in una riga:** i cinque bot che girano dentro flumine (scalper + tennis) hanno
gia' il paper che l'utente chiede; i tre che leggono `safe_strategy_scan` (Omega, Safe, Mike)
hanno **tre motori di fill diversi e scritti in casa** — snapshot istantaneo (Omega, Safe),
snapshot + differimento (Mike taker), proxy sul best back (Mike resting).

---

## 2. Il percorso «coda flumine» oggi: com'e' fatto e perche' e' fermo

**Chi lo alimenta.** Tre produttori scrivono in `betfair_live_order_requests` (schema
`migrations/betfair_live_order_queue.sql:33-39`, `mode IN ('paper','live')`, `client_ref` UNIQUE):
`omega_service._flumine_enqueue_place:1743`, `safe_strategy.execution.enqueue_place:556`
(usato anche dalle chiusure di Omega via `close_trade` → `place`), `stream/risk_engine_worker.py:942`,
piu' la UI via RPC `request_betfair_live_order`. Il gate unico e' `omega_service._flumine_gate:1678-1722`:
`execution_mode='auto'` + evento in `live_follow` con status `STREAMING` + heartbeat runner
≤ 90 s **e della modalita' giusta** + metodi coda presenti. Fail-closed: ogni dubbio → percorso legacy.

**Chi lo consuma.** `Betfair/stream/live_order_worker.py`, `BackgroundWorker` registrato dal runner
solo se `LIVE_ORDER_MODE ∈ {PAPER,LIVE}` (`runner.py:1712-1714`). Passi: claim atomico
`pending→processing` (`:582`), `_resolve_market` (`:364-376`), `build_order` (`live_order_build.py:199`,
ultima barriera money-critical, minimi per giurisdizione a `:135`), API native del `Market`.
In PAPER il client e' `BetfairClient(paper_trade=True)` (`runner.py:1442-1451`), che flumine
instrada su `SimulatedExecution` (`flumine/clients/baseclient.py:83-84`).

**Perche' e' rimasto giu' — tre cause distinte, non una.**
1. **Non ha niente da sottoscrivere.** Il runner aggancia **solo** gli eventi di `live_follow`,
   che nascono da `personal_watchlist` con `status=GIOCATA` o `follow_live=true`
   (`watchlist.py:24-31`, `runner.py:1326-1381`). Nessuna partita seguita = nessun mercato = coda inerte.
   I tre bot invece lavorano su **tutte** le partite in-play dello scanner.
2. **Autospegnimento e watchdog.** `runner_lifecycle.py` spegne per vita massima e per inattivita';
   con `LIVE_RUNNER_KEEP_ALIVE=1` (`desktop/main.js:214`) l'uscita a 18 h e' `EXIT_PLANNED_RESTART=75`
   (`runner_lifecycle.py:72`) e il watchdog riavvia. L'app lo lancia (`main.js:254`), quindi
   «fermo dal 2/09» significa **vivo ma con codice vecchio e zero follow `STREAMING`**
   (`STATO_PRODUZIONE.md` P8), non processo assente.
3. **Serve una sola modalita' per volta.** `_process_once:3016` legge `LIVE_ORDER_MODE` globale e
   processa solo le righe di quella `mode`; `_fail_cross_mode:2968` marca **`error`** tutte le righe
   pending della modalita' opposta. Nel `.env:22` c'e' `LIVE_ORDER_MODE=LIVE` → **oggi un ordine
   paper accodato verrebbe ucciso**, ed e' anche il motivo per cui il gate paper di Omega
   (`omega_service.py:1691-1692`, richiede `hb.mode == 'PAPER'`) e' sempre chiuso.

**Un ordine simulato si abbina solo se il mercato e' nello stream.** Al place,
`flumine/execution/simulatedexecution.py:37` fa `self.flumine.markets.markets[market_id]`
(KeyError se assente) e valuta il match sul `market_book` **corrente**; se il book non e' `OPEN`
il place fallisce (`simulation/simulatedorder.py:69-75`). Dopo il place il matching progressivo
avviene **solo** dentro `SimulatedMiddleware.__call__` (`flumine/markets/middleware.py:49-78`),
invocata unicamente dal ciclo dei book in arrivo (`flumine/baseflumine.py:133-166`):
**nessun aggiornamento di quel mercato = nessun fill, il tempo da solo non abbina nulla**.
Il fill passivo consuma il volume **realmente scambiato** (delta di `traded_volume`,
`middleware.py:256-274`), dimezzato e messo dietro la coda `_piq` (`simulatedorder.py:33`,
`:232-238`, `:478-497`); `simulation_available_prices` e' `False` di default.

**Implicazioni sui limiti Betfair.** Il runner ha **una sola** subscription
(`runner.py:1641-1656`) con budget `LIVE_SAFE_MARKET_THRESHOLD=150` / `LIVE_HARD_MARKET_CAP=180`
(`config_stream.py:149-150`) e campi completi `EX_ALL_OFFERS + EX_TRADED + EX_MARKET_DEF`
(`config_stream.py:76-84`) — cioe' **tutto cio' che serve al matching simulato e al bet delay**.
Lo scanner invece ha gia' un **pool shardato** (`safe_strategy/stream.py:248`, default 4 conn × 180,
tetto 10 conn `:52`) su tutti i mercati rilevanti, ma sottoscrive
`fields=["EX_BEST_OFFERS","EX_MARKET_DEF"], ladder_levels=1` (`stream.py:221-228`):
**senza `EX_TRADED` il matching passivo di flumine non potrebbe mai abbinare un ordine a riposo.**
Betfair: 200 mercati/connessione, 10 connessioni per app key.

---

## 3. Architetture candidate

### A — Un secondo runner flumine in modalita' PAPER, accanto a quello LIVE
Due processi `Betfair.stream.runner` con lock e canale distinti, `LIVE_ORDER_MODE=PAPER`/`LIVE`;
i bot accodano con il `mode` del trade (lo fanno gia'), ciascun runner serve la propria `mode`.

* **Cosa cambia nei bot**: Omega e Safe **niente** (gate e enqueue esistono); Mike: togliere il
  `execution_mode='rest'` cablato (`service.py:575`) e portare la lay appoggiata dentro
  `execution.place` (oggi non ci passa, `service.py:790-792`); scalper e tennis: niente.
* **Latenza segnale→fill**: ciclo bot (2 s Safe/Mike, 20 s Omega) + scrittura in coda + claim
  (poll DB 1 s, `live_order_worker.py:3016` con `local_channel` attivo) + `bet_delay + place_latency`
  reali (`simulatedexecution.py:36`, 120 ms da `LIVE_PAPER_SIMULATED_LATENCY_MS`) + primo book utile.
* **Carico DB**: **+~180 letture/min per runner a vuoto** (tre SELECT al secondo: pending, submin
  in corso, cross-mode) piu' 3 scritture per ordine. Contro i 198 letture/min di Mike e 71 di Omega
  del 13/09 e' un aumento sensibile e **costante anche senza ordini**.
* **Carico Betfair**: **+1 connessione stream e +180 mercati** duplicati rispetto al pool dello
  scanner → viola la regola del feed unico (`project_ottimizzazione_processi_feed_unico`).
* **Copertura**: 180 mercati contro i ~720 del pool. I bot lavorano su piu' partite di quante il
  runner ne possa tenere → la maggioranza degli ordini paper resterebbe sul percorso legacy.
* **Se il runner cade**: `enqueue` fallisce o la riga resta `pending` → il gate si richiude e si
  torna al legacy. Fail-closed rispettato **solo** se si toglie il fallback (vedi §5.2).
* **Costo**: 1 processo nuovo + 1 connessione. Lavoro basso su Omega/Safe, medio su Mike.

### B — Un processo «esecutore simulato» dedicato, che sottoscrive solo i mercati con ordini vivi
Processo nuovo con `Flumine` + `BetfairClient(paper_trade=True)`; riusa `live_order_worker` e la
coda; sottoscrive su richiesta i soli mercati con un ordine paper pending/vivo (poche decine).

* **Cosa cambia nei bot**: come A. In piu' serve un canale «sottoscrivi questo mercato» **prima**
  del place (senza book non c'e' match) e una finestra di riscaldamento.
* **Latenza**: A + **1-3 s di sottoscrizione a freddo** sul primo ordine di ogni mercato. Per una
  strategia taker che entra al best e' una divergenza vera: il paper entrerebbe piu' tardi del live.
  Sottoscrivere in anticipo i mercati «candidati» = rifare la lista dei rilevanti dello scanner.
* **Carico DB**: come A. **Carico Betfair**: +1 connessione, pochi mercati (rispettoso dei limiti)
  ma **duplicati** rispetto al pool dello scanner sugli stessi mercati.
* **Se cade**: come A. **Costo**: 1 processo nuovo, ~1 settimana di lavoro, e resta il riscaldamento.

### C — Il motore simulato ospitato dal FEED UNICO (nessun processo nuovo, nessuna connessione nuova)
Il pool dello scanner (`safe_strategy/stream.py`) gia' riceve i book di **tutti** i mercati rilevanti.
Si aggiunge, in un **thread dedicato** del processo scanner (precedente: `ScoreFeedWorker`), un
«banco paper» che tiene `Markets`/`blotter`/`SimulatedMiddleware` di flumine, alimentato dagli
stessi `MarketBook` gia' in arrivo, e serve le richieste `mode='paper'` con **lo stesso**
`live_order_worker` (che dipende solo da `flumine.markets.markets` e da `market.place_order`).

* **Cosa cambia nei bot**: Omega e Safe **niente** (stessa coda, stesso gate, il gate deve solo
  accettare l'heartbeat del banco paper al posto di quello del runner); Mike come in A; scalper e
  tennis: niente, restano dove sono. Il **live** non si tocca: resta REST o coda del runner.
* **Cosa cambia fuori dai bot**: `stream.py:221-228` deve aggiungere `EX_TRADED` (+`EX_ALL_OFFERS`,
  `ladder_levels` 3-5) — **zero connessioni in piu', zero chiamate in piu'**, solo piu' byte sullo
  stesso socket. E `banco.py:8-22` avverte che importare flumine **ritocca betfairlightweight**
  (`RunnerBookEX`): il banco paper **non puo' vivere nello stesso processo dello scanner** senza
  rompere `scanner.best_price`. → si ospita nel **processo del runner calcio, gia' esistente e gia'
  con `EX_TRADED`**, alimentato dal pool: ma allora il pool va spostato o duplicato. **Variante C2,
  quella praticabile: il pool shardato viene portato DENTRO il runner** (sostituisce la sua unica
  subscription da 180) e il runner diventa l'unico che parla con i mercati; lo scanner legge i book
  dal runner via il canale locale **47331, che esiste gia'** (`runner.py:1523`, `local_channel.py:239`).
* **Latenza**: ciclo bot + claim (0,15 s sul canale locale, `main.js:202`) + `bet_delay + place_latency`.
  La piu' bassa delle tre, e senza il riscaldamento di B.
* **Carico DB**: **il piu' basso**, se il percorso caldo usa il **canale locale** invece della coda DB:
  `_process_local_requests:2827` esegue e risponde subito e scrive **una sola riga di audit**
  (`_record_local_request`), contro le ~180 letture/min del polling. ⚠️ `place_submin` e' escluso dal
  canale locale (`_LOCAL_ACTIONS:2660`) e resta sulla coda DB.
* **Carico Betfair**: **zero aggiunto** — un solo processo parla con i mercati, regola del feed unico
  rispettata alla lettera. Capienza 4×180 → 8×200 = 1.600 slot su 2.000 consentiti.
* **Se cade**: nessun esito → nessun fill. Fail-closed per costruzione.
* **Costo**: **0 processi nuovi, 0 connessioni nuove**, ma e' la rifusione piu' invasiva (il feed
  unico e il runner diventano un solo processo) e rende il runner money-critical per tutti.

### C3 — Il pool RITRASMETTE il raw; il runner paper consuma il raw invece di sottoscrivere
*(variante chiesta dal coordinatore il 16/09, verificata riga per riga — risolve l'obiezione «A copre
180 mercati su 720»: qui la copertura del paper e' quella del pool, non quella del runner)*

**1) Esiste gia' quasi tutto.** Il tee sul raw e' un pattern **gia' in produzione due volte**:
`Betfair/stream/raw_listener.py:1-11` (sottoclasse di `StreamListener` che intercetta `on_data`
e scrive il nativo `mcm` **dalla stessa subscription**, «niente seconda connessione») e, nel pool
dello scanner, `safe_strategy/stream.py:109-112` `_HealthListener._Listener.on_data`, che gia'
riceve la stringa grezza prima di delegare al listener vero: **il punto di innesto del relay e' una
riga li'**. Il trasporto esiste: `local_channel.py` (WS su 127.0.0.1, `publish` a `:169`,
`start_channel` a `:239`), gia' usato dal runner sulla 47331 (`runner.py:1523`) e dal tennis sulla
47332. `recorder.py` e `RawTeeMarketStream` (`runner.py:1656`) sono l'altra meta' dello stesso
schema. **Niente da inventare: si aggiunge un topic al canale e un consumatore.**

**2) Il driver si scrive in ~30 righe e diventa LO STESSO del replay.**
`flumine/streams/historicalstream.py:257-272` `FlumineHistoricalGeneratorStream._read_loop` legge
righe raw da file e per ognuna chiama `listener.on_data(update)`, poi produce i `MarketBook` dalle
cache; `HistoricListener.on_data` (`:245-258`) fa solo `json.loads` + `stream._process(mc, pt)`,
senza controlli di operazione, e `create_generator` (`:288-298`) mette `update_clk = False`.
Sostituire `smart_open.open(file_path).readlines()` con un **iteratore su coda alimentata dal socket**
lascia intatto tutto il resto: **raw mcm → stesso listener → stesso `MarketBookCache` → stessi
`MarketBook` → stessa `SimulatedMiddleware`**. Produzione e replay condividono il driver, non solo
il motore. In piu' `FlumineSimulation.run` entra in `with self.simulated_datetime`
(`simulation/simulation.py:35`, classe a `simulation/utils.py:17-41`) che rimpiazza
`datetime.datetime` con un orologio ancorato al `publish_time`: **in un relay in tempo reale
l'orologio virtuale coincide con quello vero**, quindi `elapsed_seconds > simulated_delay`
(`simulation/simulation.py:190`) fa scattare il bet delay **correttamente e senza codice nuovo**.
Il conflitto `RunnerBookEX` denunciato in `mike/tools/banco.py:8-22` sparisce: flumine resta in un
processo diverso dallo scanner.

**3) Volume misurato, non stimato.** Su `_live_raw/35759636/35759636.raw.jsonl` (21 mercati,
1h49m, campi pieni `EX_ALL_OFFERS+EX_TRADED`, ladder 10, conflate 0): 30.568 messaggi, 7,9 MB →
**4,7 msg/s e 1,2 KB/s per evento**, cioe' **0,22 msg/s e 57 B/s per mercato**; picco 1 s = 31 KB,
p99 1 s = 5 KB, p50 = 1 KB. Scalando a **720 mercati: ~161 msg/s e ~40 KB/s** di media, con punte
aggregate stimabili in poche centinaia di KB/s. Un WebSocket su 127.0.0.1 regge ordini di grandezza
piu' di cosi': **il canale non e' il collo di bottiglia**. ⚠️ Ma `publish` **scarta** i push oltre
`_MAX_INVII_IN_VOLO=64` (`local_channel.py:36-38`, `:191-199`): per la ladder va bene (si pubblica
lo stato, non un differenziale), per il raw **no** — un delta perso corrompe la cache del book per
sempre. Il relay vuole una disciplina diversa: o consegna garantita, o disconnessione + nuova
immagine. E il consumatore che si collega a meta' stream **non ha la `SUB_IMAGE`**: serve una cache
dell'ultima immagine per mercato (il pool ne riemette una a ogni resubscribe, `stream.py:180`).

**4) Latenza aggiunta dal relay**: una `queue.put` + una `send` su loopback = **sotto i 5 ms**,
contro un bet delay di 1.000-5.000 ms. Irrilevante. Nessun riscaldamento come in B: i mercati sono
gia' sottoscritti dal pool prima che il bot decida.

**5) Se cade.** Runner paper giu' → nessun esito → **nessun fill** (fail-closed) e il gate si chiude.
Scanner giu' → niente book e niente righe di scan: i bot non decidono nemmeno (guardie di freschezza
gia' in vigore, `bot_service.py:4788`, `mike/feed.py:265-297`). In nessuno dei due casi si inventa
un abbinamento.

**6) Cosa cambia nei bot e nel gate.** Nei bot: **niente** per Omega e Safe; per Mike quello gia'
detto in F4. Nel gate `_flumine_gate` (`omega_service.py:1678-1722`) cambiano due condizioni:
`live_follow.status == 'STREAMING'` (`:1711`) diventa «mercato **coperto dal pool**»
(`safe_strategy/stream.py:308` `covered_ids`, gia' esistente e gia' usata per il badge STREAM/REST)
— **ed e' questa riga che porta la copertura del paper da 180 a ~720 mercati**; e
`hb.mode == 'PAPER'` (`:1715`) va letto da una riga di heartbeat **del runner paper**, oggi
impossibile perche' `betfair_live_heartbeat` ha una sola `mode` (migrazione gia' elencata in §4).

**7) Carico DB**: identico a C2 e **piu' basso di A** — percorso caldo sul canale locale
(`live_order_worker._process_local_requests:2827`, una sola riga di audit per ordine) invece delle
~180 letture/min del polling; `place_submin` resta sulla coda DB (`_LOCAL_ACTIONS:2660`).

**8) Serve un secondo runner? No.** `baseflumine.py:85-97` `add_client` ammette **piu' client** nello
stesso framework, e `markets/market.py:84-96` `place_order(..., client=...)` instrada per **ordine**
(`Transaction(client=...)`, `execution/transaction.py:41-46`); `order.simulated` e' deciso per ordine
(`simulation/simulatedorder.py:658-661`) e la `SimulatedMiddleware` salta gli ordini non simulati
(`markets/middleware.py:196`). **Un solo processo puo' servire paper-da-relay e live**: cio' che lo
impedisce oggi non e' flumine ma il nostro `LIVE_ORDER_MODE` globale (`live_order_worker._process_once:3016`)
e `_fail_cross_mode:2968` che uccide le righe dell'altra modalita'. E' la stessa F0 di A, quindi non
e' un costo aggiuntivo di C3. **Rischi**: relay senza perdite e immagine all'aggancio (il piu' serio);
gestione di piu' shard con `clk` indipendenti; il runner diventa money-critical per tutti i bot.
**Costo**: ~6-9 giorni (relay 2-3, driver da socket 1-2, gate + heartbeat 1-2, certificazione 2).

---

## 4. Raccomandazione

**Raccomandazione aggiornata dopo l'obiezione del coordinatore: si raccomanda C3.**

| | copertura paper | conn. Betfair nuove | processi nuovi | letture DB a vuoto | latenza aggiunta | costo |
|---|---|---|---|---|---|---|
| **A** (runner paper) | **180 mercati su ~720** | +1 | +1 | ~180/min | 0 | 4-6 gg |
| **C2** (pool dentro il runner) | ~720 | 0 | 0 | ~0 (canale locale) | 0 | 2-3 settimane |
| **C3** (relay del raw) | **~720** | **0** | **0** | **~0** | **<5 ms** | **6-9 gg** |

L'obiezione e' fondata e si accoglie: con A e il ripiego vietato (§5.2) la maggioranza degli ordini
paper finirebbe in `no_fill` perche' il runner non tiene i mercati dei bot, e si costruirebbe due
volte. **C3 domina A su ogni colonna** e raggiunge l'obiettivo di C2 senza spostare il pool: il
feed resta unico, flumine resta in un processo separato (quindi niente conflitto `RunnerBookEX`), e
**produzione e replay condividono anche il driver**, non solo il motore. B resta scartata (processo
nuovo *e* riscaldamento della sottoscrizione). C2 non e' piu' una destinazione necessaria: diventa
una semplificazione opzionale, da valutare solo se il relay si rivelasse fragile.
**F0 resta il primo passo in ogni caso** — e' un prerequisito comune ad A e a C3.

Il motore di matching e' **lo stesso in tutte e tre**: `SimulatedOrder`/`SimulatedMiddleware` di
flumine. Cambia solo il driver — stream vivo in produzione (`Flumine` + `paper_trade=True`),
`HistoricalStream` nel replay (`FlumineSimulation` + `SimulatedClient`,
`backtest/run_backtest.py:394-399`). **Questa e' la definizione operativa di «un solo motore».**

### Fasi

| # | Contenuto | Prova di uscita | Lavoro |
|---|---|---|---|
| **F0** | Runner paper: rendere `LIVE_ORDER_MODE` **per riga** invece che per processo, oppure ammettere due runner. Oggi `_fail_cross_mode:2968` **uccide** le righe dell'altra modalita': va reso «ignora» quando esiste un runner dell'altra modalita' (money-critical, serve un contratto, non una riga). | test che accoda paper e live insieme e verifica che nessuna delle due muoia | 1-2 gg |
| **F1** | **C3**: tee del raw nel pool (`safe_strategy/stream.py:109-112`) → topic nuovo sul canale locale (consegna garantita + immagine all'aggancio) → driver da socket derivato da `FlumineHistoricalGeneratorStream._read_loop` (`flumine/streams/historicalstream.py:257-272`). Il gate passa da `live_follow STREAMING` a `covered_ids()` (`stream.py:308`). Un ordine su mercato **non coperto** deve essere `error`, mai un fill. | replay + conta dei mercati scoperti + prova di perdita di un delta | 4-6 gg |
| **F2** | **Safe**: accendere il ramo coda in paper (`execution_mode='auto'` gia' default, `bot_service.py:110`). Nessuna riga di strategia. | `test_execution.py:201` gia' verde + nuovo test «paper via coda vs live via coda» sui **fill**, non solo sulle richieste | 1 gg |
| **F3** | **Omega**: togliere `paper_fill` dal percorso paper quando il gate passa (gia' previsto, `omega_service.py:1644-1666`). Il bet delay compare: **cambia i numeri storici di Omega** (P4) → l'utente lo sa e lo ha ordinato (§5.3). | replay Omega con e senza delay, differenza misurata | 1-2 gg |
| **F4** | **Mike**: `MIKE_USE_FLUMINE_QUEUE` acceso e, soprattutto, la **lay appoggiata** portata dentro `execution.place` (oggi `service.py:790-792` la esclude). Sparisce `_resting_filled:1292-1298`, sostituito dal `_piq` vero. Il differimento in casa (`service.py:2456-2490`) va **rimosso**, non sommato al delay di flumine. | test che riproduce le 535 riproposizioni e il doppio-delay | 3-5 gg |
| **F5** | **Parita' campo per campo per ogni bot**, sul modello di `Betfair/safe_strategy/tests/test_execution.py:201` (`test_paper_e_live_accodano_lo_STESSO_ordine`): confronto sull'**unione delle chiavi**, whitelist di differenze ammesse `{mode, client_ref}`. Da replicare su Omega, Mike, scalper, tennis. | 1 test per bot, ciascuno falsificato | 2-3 gg |
| **F6** | **Replay = produzione sul bet delay.** ⚠️ *Correzione alla prima stesura*: l'orologio virtuale **esiste gia'** — `FlumineSimulation.run` entra in `with self.simulated_datetime` (`simulation/simulation.py:35`) e `SimulatedDateTime.__enter__` (`simulation/utils.py:34-38`) sostituisce `datetime.datetime` con un orologio ancorato al `publish_time`, quindi `elapsed_seconds` (`events/events.py:47`) **e' gia' tempo di mercato** dentro un replay. Il delay manca per un'altra ragione, piu' semplice da togliere: `banco_comune._esegui_subito:445-474` forza l'esecuzione dei pacchetti **saltando** `elapsed_seconds > simulated_delay` (limite 4 dichiarato a `:60-65`). Basta smettere di bypassarlo. | replay che rifiuta un ingresso che il delay avrebbe mancato | **1 gg** |
| **F7** | **Scalper e 4 bot tennis**: nessuna migrazione di percorso, solo certificazione (C.9) che il backtest usa il codice di produzione. Verificato: `scalper/run_scalper.py:26` e `run_theta.py:34` usano la produzione; **`scalper_lab/` e' una copia dichiarata** (`bt_lab.py:35-36`, `theta_strategy.py:1`) e non certifica niente. | referto | 1 gg |
| **F8** | *(opzionale)* **C2**: pool shardato dentro il runner, scanner alimentato dal canale 47331. Da fare **solo** se il relay di C3 si rivelasse fragile. | misura di carico prima/dopo | 2-3 settimane |

**Migrazioni necessarie (da elencare, non scrivere):** (1) colonna/indice per la nuova sorgente di
follow «richiesto da bot» su `live_follow` (o tabella dedicata) con `requested_by`; (2) allargamento
di `betfair_live_heartbeat` a **piu' righe** (una per runner/modalita': oggi e' una sola `mode`);
(3) chiave di modalita' sugli storici che oggi sommano paper e live (`get_mike_daily`,
`get_mike_day_trades` — gia' noto dal 13/09); (4) eventuale `execution_mode` per Mike in
`mike_control.params`, oggi solo env.

---

## 5. Le cinque cose che solo l'utente puo' decidere

1. **Due runner o due modalita' nello stesso runner?** Verificato che flumine regge piu' client nello
   stesso processo e instrada per ordine (`baseflumine.py:85-97`, `market.py:84-96`): l'ostacolo e'
   solo nostro (`LIVE_ORDER_MODE` globale, `_fail_cross_mode:2968`). Due processi isolano meglio i
   soldi veri ma con C3 costano zero connessioni in piu'. *Proposta: un solo processo, `mode` per
   riga (F0), e soldi veri separati dal `client` dell'ordine, non dal processo.*
2. **Quando il banco simulato non c'e', il paper si ferma o ripiega sul fill a snapshot?** Oggi tutti
   i gate ripiegano sul legacy (`omega_service.py:1687-1688`). Ripiegare significa avere **due**
   motori di paper e numeri non confrontabili; fermarsi significa perdere righe di paper.
   *Proposta: ripiego **vietato** e ordine marcato `no_fill` con motivo, cosi' il paper non mente mai.*
3. **Il bet delay di Omega cambia i numeri storici** (P4, `STATO_PRODUZIONE.md:16`). La §5.3 ordina di
   uniformare. *Proposta: si uniforma e si dichiara una discontinuita' datata negli storici Omega —
   i numeri prima e dopo non si sommano.*
4. **Mike: quale ritardo resta?** Oggi Mike differisce il piazzamento di `bet_delay` in casa; flumine
   invece ritarda **l'esecuzione** e abbina sul book di allora. Sommarli sarebbe il doppio del vero.
   *Proposta: si toglie quello di Mike e vale solo quello di flumine — e' il comportamento di Betfair.*
5. **Scalper e bot tennis restano fuori dalla coda?** Girano gia' dentro flumine con lo stesso motore,
   ma senza FOK e con una coda ordini propria (`tennis_live_order_queue`, `tennis_db.py:28`).
   *Proposta: restano dove sono — spostarli sarebbe un rischio senza guadagno; si certifica la
   parita' (F5) e basta. Il FOK non si aggiunge: quelle strategie vogliono l'ordine a riposo, e
   metterlo sarebbe alterare la strategia.*

---

### Nota finale — quello che questo progetto **non** promette
Non promette che i numeri del paper miglioreranno: con il bet delay, il FOK e la coda `_piq`
**il paper diventera' piu' severo**, e alcune operazioni che oggi risultano riempite non lo saranno
piu'. E' esattamente lo scopo. Nessuna stima di rendimento e' contenuta in questo documento.
