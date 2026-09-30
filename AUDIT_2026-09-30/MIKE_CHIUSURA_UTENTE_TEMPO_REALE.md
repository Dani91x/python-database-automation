# MIKE - la chiusura dell'utente vista dallo STREAM ORDINI (30/09/2026)

Delegato di costruzione, worktree `agent-a47e8dcf61e775916` (base `15f0a33`). Niente commit.
Patch: `AUDIT_2026-09-30/MIKE_CHIUSURA_UTENTE_TEMPO_REALE.patch` (file modificati + file nuovi).
Non dichiaro "certificato": va rieseguito e firmato dal coordinatore.

## 1. Il fatto e la causa radice

Live 36130526: l'utente chiude dal sito verso le 15:30:45-15:31, Mike scrive
`chiuso_dall_utente` alle 15:32:13 (log `_logs/mike-service_2026-09-30T12-40-59-719Z.log:13760`).
Causa: `service._sorveglia_posizione_di_conto` leggeva la posizione di conto SOLO via REST
(`list_account_orders` + `list_account_cleared_orders`) al piu' ogni `reconcile_every_s` = 30 s.

## 2. Cosa riceve davvero il runner dallo stream ordini (prova)

* Il runner calcio oggi e' in LIVE con lo stream ordini REALE aperto:
  `_logs/runner-calcio_2026-09-30T12-40-59-719Z.log` righe 60 ("F0: client PAPER affiancato
  al client REALE") e 120 ("Starting OrderStream 10000").
* L'iscrizione e' SENZA filtro di strategia: flumine 2.13.11 `streams/orderstream.py`
  `customer_strategy_refs=[config.customer_strategy_ref] if config.customer_strategy_ref else None`
  e `flumine/config.py:8` `customer_strategy_ref = None`; nessun punto del repo lo imposta.
  Quindi Betfair spinge al runner OGNI ordine del conto (anche dal sito, anche quelli REST di Mike).
* Flumine poi li SCARTA: `flumine/order/process.py` `process_current_orders` salta gli ordini con
  `customer_order_ref is None` (sito) e per gli altri, se il ref non e' di una sua strategia,
  scrive "Order X not present in blotter" / "Strategy not available to create order" e li butta.
  Nel log del runner di oggi ci sono 28 righe cosi' (es. 15:30:31, 15:30:40, 15:31:13, 15:32:06:
  ordini arrivati in push e scartati). Nessuna strategia li vede in `process_orders`, quindi lo
  specchio (`betfair_live_orders`, topic `order`) non li porta.
* Test con oggetti VERI che lo dimostrano: `test_flumine_scarta_lordine_dal_sito_e_nessuna_strategia_lo_vede`.
* Nota a margine (fuori perimetro, NON toccato): nello stesso log il `reconcile_worker` prova a
  scrivere questi ordini "esterni" e il DB li rifiuta a ogni giro (`betfair_live_orders_source_check`,
  23514, es. riga 29087). E' un reperto da aprire a parte.

## 3. Cosa ho cambiato (file:riga nel worktree)

1. `Betfair/stream/esiti_ordini_canale.py` (modulo puro, nessun import flumine/bflw):
   * `ClientEsiti(..., topic=TOPIC)` (r. ~238): stesso client, topic scelto; di serie `order`,
     URL/nome thread/filtro identici per Omega e Safe.
   * sezione nuova in coda (r. ~627-839): `TOPIC_CONTO="conto"`, `ordine_del_conto` (un
     `CurrentOrder` dello stream -> dict camelCase con le chiavi di `listCurrentOrders`),
     `payload_conto`, `pubblica_conto_da_evento` (solo client con `paper_trade is False`),
     `osserva_conto_su_flumine` (avvolge `Flumine._process_current_orders` DOPO flumine,
     idempotente, mai solleva, mai su framework simulato), `MemoriaConto` (ultima fotografia per
     mercato con `versione`).
2. `Betfair/stream/engine/live_trading_strategy.py` r. ~163-179: `start(flumine)` monta
   l'osservatore SOLO se `mode == "live"` e pubblica con `local_channel.publish`.
   Runner PAPER e strategia paper affiancata: nulla.
3. `Betfair/mike/service.py`:
   * stato (r. ~2759-2783): `ENV_MIKE_CONTO_CANALE`, `_CONTO_CANALE`, `_CONTO_VISTO`,
     `_CONTO_SEGNALE`, `_CONTO_FIRMA` (le ultime tre nelle cache di processo del banco; la memoria
     del canale si svuota in `azzera_cache_di_processo`).
   * `_verdetto_di_conto` (r. ~2946): l'aritmetica di prima, estratta SENZA cambiarla (atteso,
     refs di Mike, `_netto_su_selezione`, gambe non ritrovate, chiusa/ridotta). La usano sia la
     REST sia il canale: una sola aritmetica.
   * `_segnale_conto_dal_canale` (r. ~3000): se c'e' una fotografia NUOVA di un mercato con
     posizione di Mike, normalizza le righe con `omega_market._riga_corrente` (la stessa della
     REST) e chiama `_verdetto_di_conto`. Segnale se chiusa / ridotta / gambe di Mike assenti ma
     ordine altrui abbinato; firma anti-ripetizione (gli snap di flumine ogni 3 s non
     rigenerano il segnale se la situazione e' la stessa).
   * `_sorveglia_posizione_di_conto`: con un segnale la REST si rilegge in QUESTO giro (fuori
     cadenza) e decide lei; se conferma: `chiuso_dall_utente` con
     `dove: "fuori dall'app (stream ordini)"`, `conferma`, `segnale`, `latenza_ms`
     {`dal_runner`, `da_betfair`}; stesse conseguenze di prima (annullo gambe vive, `no_reentry`,
     niente ordini nuovi). Se la REST NON conferma: `posizione_di_conto` con verdetto
     `canale_non_confermato` e Mike continua. REST giu': nessun verdetto, il segnale resta,
     riprova al giro dopo. Senza segnale: identico a prima (cadenza, righe, `dove`).
   * `installa_conto_canale`, `avvia_conto_dal_canale` (lettore `/lettore/conto` su
     `LIVE_LOCAL_WS_PORT`/47331, ACCESO di serie, `MIKE_CONTO_CANALE=0` lo spegne, senza
     `websockets` o senza runner = REST come prima), chiamato in `main()` (non in `--once`).
4. Banco: `Betfair/stream/backtest/banco_comune.py` `ordini_conto_come_stream` (gli ordini del
   mercato, bot e utente, nella grafia `uo` dello stream); `Betfair/mike/tools/replay_registrazioni.py`:
   nello scenario `chiuso-fuori-app` (solo in live/coda) la chiusura dell'utente passa ANCHE per
   `OrderBookCache` VERA -> `pubblica_conto_da_evento` VERO -> JSON -> `ClientEsiti` VERO di Mike;
   nota di referto con la latenza e controllo `R3-CANALE` (verdetto dallo stream al PRIMO giro
   del servizio dopo il canale, tolleranza 1 s per le due letture REST).

File nuovi: `Betfair/stream/tests/test_conto_ordini_canale_2026_09_30.py` (11 test),
`Betfair/mike/tests/test_mike_conto_dal_canale_2026_09_30.py` (13 test),
`AUDIT_2026-09-30/replay_conto/mike_chiuso_fuori_app_dopo.txt`.

## 4. Vincolo "non spammare Betfair" (aggiunto dall'utente)

* La rilevazione viene dallo stream ordini che il runner ha GIA' aperto: zero connessioni e zero
  chiamate nuove lato runner; il canale e' locale (127.0.0.1).
* La REST a cadenza NON diventa piu' frequente. Unica lettura fuori cadenza: UNA coppia
  `listCurrentOrders`+`listClearedOrders` quando il canale segnala che la posizione non e' piu'
  intera (cioe' quando l'utente interviene su un mercato di Mike); quella lettura azzera
  l'orologio della cadenza (`_CONTO_LETTO_A`), quindi sostituisce la lettura successiva invece di
  aggiungersi; dopo `chiuso_dall_utente` Mike non legge piu' il conto di quella partita. Gli snap
  ripetuti dello stream non fanno rileggere (test `test_lo_snap_ripetuto...`), un ordine del bot
  sullo stream non fa rileggere (test `test_un_ordine_del_bot...`).
* Misura sul banco (scenario `chiuso-fuori-app`, coda): chiamate di LETTURA a Betfair per partita
  **7 prima** (`AUDIT_2026-09-30/replay/mike_tutti_FINALE.txt`) e **7 dopo**.
* La conferma REST la tengo apposta: lo stream conosce solo gli ordini visti dalla sua
  iscrizione (cache di `betfairlightweight`); un back dell'utente di prima farebbe sembrare
  "chiusa" dal solo canale una posizione ancora viva (test `test_il_canale_dice_chiusa_ma_il_conto_no...`).
  Decidere dal solo canale risparmierebbe 2 chiamate per intervento ma spegnerebbe Mike su una
  posizione vera: non lo faccio senza una decisione dell'utente.

## 5. Latenza attesa in produzione

stream Betfair -> runner (push, ms) -> canale locale (ms, misurato < 1 s nel capo-coda, in
pratica decine di ms) -> Mike al giro successivo (in gioco con posizione il giro e'
`max(1 s, decide_min_interval_ms*2)`, cioe' circa 1 s) -> conferma REST (2 chiamate, qualche
centinaio di ms). Attesa: **circa 1-2 s** invece di fino a 30 s (oggi 60-90 s). Non ho agganciato
la sveglia del ciclo (`_SVEGLIA`, spenta di serie): accesa toglierebbe fino a 1 s.

## 6. Test

Ambiente neutro (`SUPABASE_URL=http://127.0.0.1:9`), python del `.venv` principale:
* nuovi: 11 + 13 verdi.
* `Betfair/mike`: **1364 passed** (80 s) = 1351 di riferimento + 13 nuovi.
* `Betfair/omega` + `Betfair/safe_strategy`: **3433 passed, 6 skipped, 1 xfailed** (256 s)
  = 3440 raccolti (riferimento 3439 + nessuno mio: invariati). Esiti di Omega/Safe
  (`test_esiti_ordini_canale_2026_09_23.py`) verdi: il topic in piu' non li tocca.
* `Betfair/stream/tests`: **3177 passed, 25 skipped** (330 s) = 3202 = 3191 di riferimento + 11 nuovi.

## 7. Falsificazioni (mutazione -> rosso, ripristino dal contenuto salvato, 0 `MUTAZIONE` residue, diff --stat identico)

| # | Mutazione | Esito |
|---|---|---|
| M1 | il runner pubblica il client paper e salta il reale | ROSSO |
| M2 | la cadenza ignora il segnale del canale (comportamento di ieri) | ROSSO |
| M3 | si decide sul solo canale senza conferma del conto | ROSSO |
| M4 | il client ignora il topic chiesto | ROSSO |
| M5 | anche la strategia PAPER monta il conto | ROSSO |
| M6 | la versione della fotografia non si ricorda | ROSSO |
| M7 | ordine altrui con gambe di Mike fuori fotografia: nessun segnale | ROSSO |
| M8 | la memoria accetta fotografie piu' vecchie | ROSSO |
| M9 | il runner non pubblica l'ordine senza ref (dal sito) | ROSSO |
| M10 | firma anti-ripetizione tolta (snap ogni 3 s) | ROSSO |

Sul banco: prima del fix della soglia il controllo `R3-CANALE` e' diventato rosso sul trasporto
canale (paper, dove il conto non si legge): corretto limitando il canale del conto al live.

## 8. Replay

`certifica mike 35760084 --scenari chiuso-fuori-app --trasporto entrambi --worker 0`, ambiente
neutro di `replay_mike.sh`: 169,7 s totali.
* `<coda>` (live): **OK**, R3 sollecitato **5836** volte (come FINALE), verdetto
  `fuori dall'app (stream ordini)`, **latenza 2707 ms tutta di attesa del primo giro** (nel banco
  il giro lo danno i book delle linee di Mike: il primo book dopo la chiusura arriva a +2707 ms,
  verificato sulla registrazione), letture REST 7 (= prima).
* `<canale>` (paper): "NON ESERCITATO" (R3 x0) ed exit 1 per parita' coda/canale: e' il limite
  gia' scritto in `TRASPORTO_OBBLIGATO` (in paper il conto non si legge), non un effetto di questa
  modifica; con `--scenari tutti --trasporto canale` lo scenario va sulla coda come prima.

## 9. Parita' paper/live

Paper: identico a prima (`_sorveglia_posizione_di_conto` esce subito; la strategia paper non
monta l'osservatore; il client paper affiancato non pubblica). Live: cambia solo QUANDO si
rilegge la REST, la decisione e l'aritmetica sono quelle di prima.

## 10. Cosa NON ho fatto / NON ho potuto verificare

* Nessuna prova con lo stream ordini VERO di Betfair (vietato): non ho verificato sul filo come
  arriva un ordine dal SITO (se Betfair manda `rfo` assente, `null` o vuoto). Se `rfo` mancasse
  del tutto, `betfairlightweight.UnmatchedOrder` lo richiede come argomento: sarebbe un problema
  gia' esistente del runner (non mio), da osservare nel log al prossimo intervento manuale.
* Non verificato cosa contiene l'immagine iniziale dello stream dopo una riconnessione (ordini
  EXECUTION_COMPLETE vecchi presenti o no): per questo il canale non decide da solo.
* Il banco pubblica sul canale solo l'evento della chiusura dell'utente, non ogni ordine di Mike.
* Sveglia del ciclo non agganciata; `--trasporto entrambi` esce 1 per la parte canale (vedi §8).
* Suite intere lanciate a pezzi; nessun replay degli altri scenari.

## 11. Da controllare dal vivo (live, app accesa)

* Log runner calcio: una riga `[conto-ws] ordini del conto dallo stream pubblicati sul canale`.
* Log Mike all'avvio: `[mike] posizione di conto dallo stream ordini del runner: ws://127.0.0.1:47331/lettore/conto`.
* Alla prossima chiusura manuale su una partita di Mike: attivita' `chiuso_dall_utente` con
  `dove = "fuori dall'app (stream ordini)"` e `latenza_ms.dal_runner` di 1-2 s.

## 12. Decisioni per l'utente

Nessuna regola di strategia toccata. Una scelta da fargli vedere: oggi il canale SVEGLIA e la
REST CONFERMA (2 chiamate solo quando lui interviene). Decidere dal solo stream eviterebbe quelle
2 chiamate ma, con uno stream che non conosce i suoi ordini piu' vecchi, rischierebbe di far
smettere Mike di proteggere una posizione ancora viva. Proposta: tenere la conferma.
