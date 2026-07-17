# Delay nella simulazione PAPER di flumine (2.13.11) — studio dalla sorgente

Studio letto DIRETTAMENTE da `.venv/Lib/site-packages/` (flumine 2.13.11 +
betfairlightweight). Riferimenti file:linea del sorgente installato.
Certificato runtime: `Betfair/stream/tests/test_flumine_paper_fidelity_2026_07_16.py`.

## Le 5 righe chiave

1. **Da dove viene il betDelay**: dal `marketDefinition` STREAMATO per mercato
   (`betfairlightweight/streaming/cache.py:241,319` → `MarketBook.bet_delay`,
   `resources/bettingresources.py:600`). Pre-match `betDelay=0` (nessun delay);
   in-play `>0` e **deciso dall'exchange per sport/mercato** (calcio ~5-8s,
   tennis tipicamente 1-3s): flumine non hardcoda MAI un valore — segue l'evento.
2. **Quando viene letto (GAP-5)**: SNAPSHOTTATO alla creazione del package,
   `bet_delay=self.market.market_book.bet_delay` (`execution/transaction.py:266`,
   congelato in `order/orderpackage.py:56`). Se il mercato cambia regime
   (pre-off→in-play, o betDelay diverso post-sospensione) tra decisione ed
   esecuzione, il paper dorme il delay VECCHIO (spesso 0) → fill più veloce del
   reale, proprio negli scenari post-gol/post-sospensione. **OTTIMISTICO**.
3. **Come viene applicato**: in paper `execute_place` fa
   `time.sleep(order_package.bet_delay + config.place_latency)` REALE e SOLO
   DOPO legge il market book CORRENTE e matcha
   (`execution/simulatedexecution.py:35-37`): durante il delay il prezzo può
   scappare, come dal vivo. Idem replace (righe 109-112); cancel/update dormono
   solo le rispettive latenze. Lo sleep gira nel thread-pool (handler:27-28),
   non blocca il loop strategie.
4. **Cosa rappresenta `place_latency`**: SOLO la NOSTRA latenza rete/processing
   (default flumine 0.120s, `config.py:21-24`), **ADDITIVA** al betDelay
   (`orderpackage.py:77`: `simulated_delay = place_latency + bet_delay`).
   NON è il bet delay: metterci dentro il delay in-play = DOPPIO CONTEGGIO.
5. **GAP-6 (affidabilità)**: in paper il place riesce SEMPRE se mercato OPEN e
   runner ACTIVE — niente rifiuti API, niente timeout, niente ordini persi →
   il paper è **più affidabile del reale** (ottimistico), non conservativo.

## Fix GAP-5 nel nostro codice (nessuna modifica a site-packages)

`Betfair/stream/tennis_live/paper_execution.py` —
`FreshDelaySimulatedExecution(SimulatedExecution)`: prima di `execute_place`/
`execute_replace` RI-LEGGE `market_book.bet_delay` corrente dal framework
(`flumine.markets.markets[market_id]`) e aggiorna `order_package.bet_delay`
(+ `simulated_delay` per coerenza). Il `market_book` è sempre aggiornato dallo
stream (`cache.py:241` processa ogni marketDefinition change), quindi al momento
dell'esecuzione il delay è quello che l'exchange applicherebbe DAVVERO all'arrivo
dell'ordine. Wiring: `install_fresh_delay_execution(framework)` sostituisce
`framework.simulated_execution` e ri-aggancia i client paper (così `__exit__`
di flumine spegne il thread-pool giusto ad ogni restart — un `execution_cls`
custom sul client NON verrebbe mai shutdownato, `baseflumine.py:525-527`).

- **Tennis**: cablato in `tennis_runner.setup_and_run` (mode PAPER/OFF).
- **Scalper calcio**: cablato (17/07) in `scalper_session.py` subito dopo la
  costruzione del framework, solo in sessione paper (`if session_paper:`),
  con lo stesso `install_fresh_delay_execution`.

⚠️ NOTA ARCHITETTURALE (terza review 17/07): `flumine.config.place_latency` è
uno stato GLOBALE di processo, riletto "live" a ogni sleep — oggi è sicuro solo
perché scalper (processo per evento), tennis e runner girano in processi OS
separati. MAI colocare due `Flumine.run()` con latenze diverse nello stesso
processo Python (la latenza dell'uno leakerebbe sull'altro).

## Calibrazione latenza paper tennis

Il vecchio `TENNIS_PAPER_LATENCY_MS=3000` metteva il "bet delay tennis ~3s"
dentro `place_latency`: **doppio conteggio** (flumine dorme già il betDelay
streamato) e comunque non calibrato. Nessuna misura reale di latenza del runner
tennis trovata in log/DB (nessuna colonna/metrica di round-trip place).

Nuovo default: **`TENNIS_PAPER_LATENCY_MS=600`** = SOLO rete/processing, scelto
per principio con margine conservativo: flumine modella 120ms (setup co-locato);
un place REST da fibra domestica IT verso l'exchange sta tipicamente in
150-400ms round-trip + processing del runner → 600ms ≈ il caso peggiore
osservabile, senza gonfiare. Configurabile via env; da RICALIBRARE appena
esistono timestamp reali decision→ack dal LIVE (TODO strumentazione).

Delay totale simulato in-play = `betDelay(marketDefinition, fresco)` +
`0.6s` di latenza nostra — specchio della realtà, niente doppio conteggio.
