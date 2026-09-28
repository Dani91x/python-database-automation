# CANTIERE B - CAPACITA' DEI MERCATI (28/09/2026)

Delegato, worktree `agent-af1ef180da338e7f9` (base `2eb3c1d`). Lavoro NON committato. Nessuna chiamata
Betfair, nessuna scrittura sul DB (una sola `SELECT` su `safe_strategy_status`), nessun processo nuovo.

Ordine dell'utente: «questo va risolto, informati sulla documentazione e sulle migliori pratiche, non
possiamo lasciare eventi "fuori", noi lavoriamo sul volume.»

---

## PARTE 1 - DOCUMENTAZIONE E BILANCIO (consegnabile da sola)

### 1.1 Limiti VERI della Exchange Stream API

| Limite | Valore | Fonte | Grado di certezza |
|---|---|---|---|
| Mercati per sottoscrizione | **200 di serie**. Oltre: `SUBSCRIPTION_LIMIT_EXCEEDED` («Thrown when subscribed to more markets than allowed to - set to 200 markets by default») | [Exchange Stream API (docs ufficiali)](https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687396/Exchange+Stream+API); [forum BDP 2017](https://forum.developer.betfair.com/forum/sports-exchange-api/exchange-api/3477-stream-api-subscription-limit): «the count is evaluated at the time of subscription» | ufficiale |
| Sottoscrizioni per connessione | **una**: «It is possible to subscribe multiple times - each replaces the previous (each will send a new initial image and deltas) - they are not additive» | docs ufficiali (sopra) | ufficiale. Quindi 200 mercati = 200 **per connessione**; piu' capacita' = piu' connessioni |
| Connessioni contemporanee | **10 di serie** per conto (o app key), alzabili dal BDP su richiesta | docs: esiste `MAX_CONNECTION_LIMIT_EXCEEDED` («Failure code returned when a client tries to create more connections than allowed to») ma il numero NON e' scritto; il 10 viene da [Bet Angel forum 2018](https://forum.betangel.com/viewtopic.php?t=17547) («manage this limit across up to 10 separate connections», BDP che alza a 1000 mercati) e [2022](https://forum.betangel.com/viewtopic.php?t=25605) («10 by default ... a simple setting per BF user account ... 200 subscribed markets ... per connection») | NON ufficiale sul numero; il meccanismo e' ufficiale |
| Quante connessioni restano | `connectionsAvailable` nello `status` di risposta all'autenticazione: «The number of additional connections you can open» | docs ufficiali; [annuncio BDP connection throttling, 26/02/2020](https://forum.developer.betfair.com/forum/developer-program/announcements/30597-exchange-stream-api-release-connection-throttling-26th-february) | ufficiale |
| Aperture troppo rapide | `TOO_MANY_REQUESTS` («too many requests within a short time period») | docs + annuncio 2020 | ufficiale; soglia non pubblicata |
| Mercati CHIUSI nel conteggio | esclusi alla ri-sottoscrizione; job ogni 5', eliminazione dopo 1 h dalla chiusura | [support BDP](https://support.developer.betfair.com/hc/en-us/articles/11741143435932-Are-closed-markets-auto-removed-from-the-Stream-API-subscription) | ufficiale |
| `marketFilter` | `marketIds`, `bettingTypes`, `eventTypeIds`, `eventIds`, `turnInPlayEnabled`, `marketTypes`, `venues`, `countryCodes`, `raceTypes`; filtro vuoto = tutto l'exchange | docs ufficiali | ufficiale |
| `conflateMs` | di serie 0 (nessuna conflazione; 180000 con app key Delayed) | docs ufficiali | runner calcio: `LIVE_STREAM_CONFLATE_MS=0` -> `None`; scanner 1000 ms |
| `heartbeatMs` | 500..5000 ms; messaggio vuoto (`ct=HEARTBEAT`) se non ci sono dati | docs ufficiali | flumine non lo passa -> valore di Betfair; scanner 5000 |
| `segmentationEnabled` | di serie true (messaggi grandi a segmenti) | docs; betfairlightweight `subscribe_to_markets(segmentation_enabled=True)` | ufficiale |
| `initialClk`/`clk` | riconnessione veloce senza immagine piena | docs; flumine `MarketStream.run` li passa | ufficiale |
| Socket muto | betfairlightweight chiude il socket dopo **64 s** senza byte (`create_stream(timeout=64)`) -> `SocketError` -> flumine ritenta | codice `.venv` (`betfairlightweight/endpoints/streaming.py`, `betfairstream.py:246-252`) | codice installato |
| Exchange italiano | lo stream e' lo stesso host per tutti (`stream-api.betfair.com`, `betfairstream.py:24-28`), cambia solo la sessione (`identitysso.betfair.it`, `auth.py:63`). **Nessun limite diverso documentato per il .it** | codice installato; nessuna fonte ufficiale trovata | NON VERIFICATO |

**Difetto di betfairlightweight 2.23.2** (`streaming/listener.py:175-177`): `if connections_available:` salva il
valore solo se vero, quindi `connectionsAvailable: 0` (il caso che conta) si perde. Aggirato nel nostro listener
(test `test_riserva_di_connessioni_per_gli_altri_processi`).

**Come flumine 2.13.11 gestisce piu' stream** (codice del `.venv`):
- `Streams.add_stream` (`flumine/streams/streams.py:108-148`): una strategia RIUSA uno stream esistente SOLO se
  coincidono classe (isinstance), `market_filter`, `market_data_filter`, `streaming_timeout`, `conflate_ms`;
  `market_filter` puo' essere una LISTA di filtri = uno stream (una connessione) per filtro.
- Instradamento: `market_book.streaming_unique_id in strategy.stream_ids` (`baseflumine.py:169`, chiusure `:379`);
  `stream_ids` e' calcolato a ogni lettura dalla lista `strategy.streams` (`strategy/strategy.py:238-242`), quindi
  uno stream aggiunto a caldo alla lista viene servito subito.
- `Streams.start()` (`streams.py:303-311`) all'avvio ASPETTA che ogni stream sia connesso: una connessione
  rifiutata all'avvio bloccherebbe il framework intero -> i frammenti in piu' vanno aperti DOPO, a caldo.
- `MarketStream.run` (`marketstream.py:15-50`) e' decorata `@retry(wait_exponential(min=2,max=60))` SENZA stop:
  una stream in errore ritenta per sempre, anche dopo `stop()` (una connessione fantasma che occupa il limite).
- Sottoscrizione a caldo sulla stessa connessione: gia' in uso (`sottoscrizione_a_caldo.sottoscrivi`, 25/09).

**Migliori pratiche** (docs + strumenti professionali citati nel repo, `safe_strategy/stream.py:4-12`): stream
solo sui mercati monitorati (per `marketIds`), piu' connessioni quando si supera il limite per connessione,
riuso della stessa connessione per cambiare sottoscrizione, niente sottoscrizioni/aperture a raffica (backoff),
`connectionsAvailable` per non superare il tetto di connessioni.

### 1.2 Bilancio delle connessioni (dal codice)

Processi avviati dall'app (`desktop/main.js:365-399`). Solo 4 aprono connessioni stream (grep `create_stream`,
`Flumine(`, `MarketStreamPool(` fuori da test/tools): omega, mike, safe-bot, tennis-bot-service = **0**.

| Processo | Connessioni di MERCATO | Connessioni ORDINI | Mercati per connessione | Fonte |
|---|---|---|---|---|
| Scanner Safe (feed unico) | `ceil(mercati/180)`, max `SAFE_STRATEGY_STREAM_CONNS` = **4**. Misurato 26/09 17:40Z: **2** (96+91 mercati, 187 coperti) | 0 | <= 180 | `safe_strategy/stream.py:95-115,441`; `safe_strategy_status.payload` (SELECT) |
| Runner calcio PRIMA (tetto `.env` `LIVE_ORDER_MODE=LIVE`) | **2** (!) con gli STESSI mercati: recorder + `LiveTradingStrategy` | 1 in LIVE (OrderStream vero); 0 in PAPER (simulato) | <= 180 | sonda `AUDIT_2026-09-28/sonda_stream_runner.py`: `MarketStream aperte: 2` |
| Runner calcio DOPO | **1..3** frammenti (1 fino a 180 mercati, 2 fino a 360, 3 fino a 540) | invariato | <= 180 | `frammenti_mercato.py` |
| Runner tennis | 1 | 0 (`TENNIS_LIVE_ORDER_MODE` assente = OFF -> simulato); 1 se LIVE | 200 max | `tennis_runner.py:137,2760` |
| Scalper | 1 per sessione (processo) in paper, 2 in live; sessioni di serie 2, max 4 | (incluse) | 4-12 | `scalper/auto_mode.py:28-38`, `scalper_session.py:1098` |

**Reperto R-B1 (connessione duplicata)**: `runner.py` creava `LiveTradingStrategy(market_filter=...)` senza
`market_data_filter`: flumine le dava il filtro dati di serie (`{"fields":[...]}` senza `ladderLevels`) diverso da
quello del recorder (`ladderLevels: 10`) e apriva una SECONDA connessione di mercato con gli stessi mercati. Il
commento del codice diceva il contrario («Stesso market_filter -> flumine RIUSA lo stream esistente: zero
connessioni e zero mercati in piu'»). Conseguenze: una connessione sprecata; e la risottoscrizione a caldo
dell'auto-follow toccava solo lo stream del recorder, quindi **i mercati agganciati a caldo non arrivavano mai
alla strategia degli ordini**: `process_closed_market` non scattava per loro -> in PAPER il P&L realizzato di quei
mercati non finiva in `betfair_live_settled` (`live_trading_strategy.py:193-208`, unico scrittore paper). Inoltre
per i mercati presenti su entrambe le connessioni flumine riceveva DUE chiusure (`_process_close_market` due
volte, `blotter.process_closed_market` due volte).

Somma (limite 10 di serie):
- 26/09 reale: scanner 2 + runner calcio 2+1 + tennis 1 + scalper 2 (paper) = **8**.
- Dopo, stesso giorno (67 partite -> ~270 mercati -> 2 frammenti): 2 + 2+1 + 1 + 2 = **8** (la connessione tolta
  al duplicato paga il frammento in piu').
- Picco realistico: scanner 3 + calcio 3+1 + tennis 1 + scalper 2 = **10**: al limite. La riserva (sotto) evita
  che il runner prenda l'ultima connessione.
- Peggior caso teorico (gia' oltre prima): scanner 4 + calcio 3+1 + tennis 2 + scalper 4x2 = 18 (prima 17).
  Il commento di `scalper/auto_mode.py:28-38` conta il runner calcio a 1 (+1): era 2 (+1). Fuori perimetro, non
  toccato.

---

## PARTE 2 - PROGETTO

Scelta: **piu' connessioni di mercato a frammenti nello STESSO framework flumine del runner** (nessun processo
nuovo, nessun riavvio, stessi worker/blotter/strategie). Scartati: riuso del pool dello scanner (altro processo:
book diversi, livello 1; il motore ordini ha bisogno dei book nel framework flumine che piazza); priorita' come
unica difesa (lascerebbe fuori partite).

1. **Una connessione in meno** (R-B1): le strategie degli ordini prendono gli stessi parametri di stream del
   recorder (`kwargs_stream_condiviso`) -> una sola `MarketStream` per frammento, servita a tutte le strategie.
2. **Frammento 0** alla costruzione del framework: <= 180 mercati, prima le partite seguite a mano
   (`primo_frammento`). Gli altri li apre l'auto-follow A CALDO appena lo stream gira (flumine all'avvio
   aspetterebbe ogni stream: un rifiuto bloccherebbe il runner).
3. **Piano stabile** (`pianifica`, puro): un mercato gia' sottoscritto non cambia MAI frammento; i nuovi riempiono i
   frammenti esistenti, poi se ne apre uno nuovo; si risottoscrive SOLO il frammento che cambia; un frammento in
   piu' rimasto vuoto si chiude (connessione restituita); il frammento 0 non resta mai vuoto (filtro vuoto =
   tutto l'exchange).
4. **Guardie money-critical invariate**: le priorita' e le protezioni restano quelle di `PianoFollow`
   (posizioni vive mai espulse, comandi, candidate); lo spostamento di un mercato avviene solo se il suo
   frammento e' chiuso (rifiutato o muto), e `servibile` aspetta un book NUOVO prima di far partire un comando.
5. **Capacita' vera**: tetto del piano = connessioni concesse x 180. Si apre un frammento solo se Betfair,
   all'ultima autenticazione, ha dichiarato piu' di `RUNNER_CALCIO_STREAM_RISERVA` (1) connessioni libere. Rifiuto
   (`MAX_CONNECTION_LIMIT_EXCEEDED`/`TOO_MANY_REQUESTS`/`SUBSCRIPTION_LIMIT_EXCEEDED`, o nessuna autenticazione in 60 s
   con la rete viva) -> frammento chiuso, mercati ripiazzati, capacita' ridotta per 5', poi si riprova.
6. **Resilienza per frammento** (26/09, `67c3ad4`/`2220288`): ogni frammento ha il SUO battito (listener
   `FrammentoListener`: qualunque messaggio, heartbeat compresi; dati; status; errore). Riconnessione del singolo
   frammento: stesso backoff di flumine con `initialClk`/`clk`, ma un frammento chiuso non si riconnette piu'. Un
   frammento MUTO da 180 s mentre un altro e' vivo -> chiuso e i suoi mercati su una connessione nuova. Tutti muti =
   rete/sessione: decide il controllo di stallo del runner (`RAW_STATE`, invariato; il massimo sui frammenti) e il
   custode della sessione. La ricostruzione intera del framework ricrea tutto da zero come prima.
7. **Fuori = dichiarato** (punto 4 del brief): ogni partita idonea non seguita va in `AutoFollow.fuori` con nome,
   motivo, da quando; nello stato pubblicato (`auto_follow` e `hello.auto_follow` sul 47331) con
   `partite_fuori_n`, `partite_fuori`, `criterio_fuori`, `frammenti.motivo_limite`; WARNING nel log a ogni
   cambio; riga «Mercati» nella Control Room con numeri, elenco e motivo. Criterio: posizioni vive, poi comandi
   dei bot, poi partite del feed in gioco e per orario d'inizio (quello gia' esistente di `partite_dal_feed`).

Configurazione (env, facoltative): `RUNNER_CALCIO_STREAM_CONNS` (1..10, di serie **3** = 540 mercati ~ 150
partite a 3,6 mercati/partita del 26/09), `RUNNER_CALCIO_STREAM_RISERVA` (0..9, di serie 1). Mercati per
connessione = `tetto_mercati()` di sempre (`LIVE_HARD_MARKET_CAP` 180 / `AUTO_FOLLOW_TETTO_MERCATI`, mai > 200).

---

## PARTE 3 - CODICE

### File toccati (modificati)
- `Betfair/stream/runner.py`: import `frammenti_mercato as _FR` (101); `_costruisci_auto_follow` con
  `GestoreFrammenti.da_ambiente()` e piano sulla sua capacita' + `_capacita_mercati()` (1902-1919);
  `_catalog_events` budget sulla capacita' dei frammenti, soglia d'allerta in proporzione (1617-1629);
  `setup_and_run`: frammento 0 (`mercati_frammento0`), `stream_class=_FR.FrammentoMarketStream`, le due
  `LiveTradingStrategy` con `**_FR.kwargs_stream_condiviso(recorder)`, `auto.aggancia(framework,
  mercati_frammento0)` (2291-2313, 2374-2395, 2510-2512). `session.stream_market_count = len(market_ids)`
  invariato (tutti i mercati).
- `Betfair/stream/auto_follow.py` (modifiche piccole e localizzate, lontane dalla chiusura dei follow di cantiere A):
  `self.fuori` (581); `_segna_fuori` + registrazione in `_dopo_espulsioni` (717-727); `giro()` chiama
  `_frammenti()` prima di `_applica` (753); `_frammenti()` nuovo (758-789: persi, capacita', rientro);
  `_giro_feed`: `fuori.clear()` senza bot, rifiuto dichiarato e pulizia (915, 956-966); `stato()`: connessioni
  dal sottoscrittore, `frammenti`, `partite_fuori_n/_fuori`, `criterio_fuori` (977-997); `_annuncia`: firma
  estesa + WARNING delle partite fuori (1016-1025). `SottoscrittoreStream` e `PianoFollow` invariati.
- `frontend/src/pages/ControlRoom.tsx`: import e `<RigaCapacitaMercati />` sotto il Freno (58, 613).

### File nuovi
- `Betfair/stream/frammenti_mercato.py`: `FrammentoListener`, `FrammentoMarketStream`, `pianifica`,
  `primo_frammento`, `kwargs_stream_condiviso`, `CapacitaInsufficiente`, `GestoreFrammenti`.
- `Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py` (37 test) e
  `Betfair/stream/tests/test_frammenti_tcp_2026_09_28.py` (3 test, finto server TLS locale).
- Riesame (punti 1-3): `runner.py` anche `_STATI_ORDINE_CHIUSI`, `_mercati_con_soldi_dallo_specchio`,
  `_mercati_con_soldi`, `_frammento0`, `mercati_con_ordini_prec` (init prima del ciclo, letto nel `finally`),
  `auto.imposta_con_soldi` prima di `rientra_nel_tetto`, import `Set`; `auto_follow.py` anche
  `_con_soldi_esterni`/`_protetti_allo_sgancio`, `imposta_con_soldi`, `mercati_da_proteggere`, snapshot in
  `sgancia`, voci con soldi protette in `_protetti`; `frammenti_mercato.py` anche `primo_frammento(con_soldi)`,
  `mercati_con_ordini`, `segna_costruzione`/`costruzione` nello stato, copia-e-sostituzione in `_apri`/`_chiudi`.
- `frontend/src/lib/capacitaMercati.ts`, `frontend/src/components/controlroom/RigaCapacitaMercati.tsx`,
  `RigaCapacitaMercati.test.tsx` (5 test), `frontend/src/lib/__fixtures__/autoFollowFinti.json` (stato VERO).
- `AUDIT_2026-09-28/sonda_stream_runner.py`, `falsifica_cantiere_b.py`, `genera_fixture_auto_follow.py`, questo referto.

Nessuna migrazione SQL.

---

## PARTE 4 - TEST E FALSIFICAZIONE

Finti: `Flumine` + `BetfairClient` VERI (costruiti senza rete), `MarketRecorderStrategy` e `LiveTradingStrategy`
VERE, `BetfairStream` VERO di betfairlightweight su un socket che registra gli invii, messaggi `status`/`mcm` nel
formato Betfair (camelCase: `connectionsAvailable`, `statusCode`, `errorCode`). Nei test unitari l'avvio del
thread di un frammento nuovo collega lo stream al `BetfairStream` su socket finto; nei 3 test TCP (parte 4-bis,
punto 2) l'avvio e' quello VERO contro un finto server TLS locale.
Fixture UI generata dallo stato vero e confrontata chiave per chiave (tipi compresi) da un test Python.

Comandi (dalla radice del worktree, PowerShell):
```
$env:SUPABASE_URL="http://127.0.0.1:9"; $env:SUPABASE_SERVICE_ROLE_KEY="x"; $env:SUPABASE_KEY="x"
python -m pytest Betfair/stream/tests/test_frammenti_mercato_2026_09_28.py Betfair/stream/tests/test_frammenti_tcp_2026_09_28.py -q -p no:cacheprovider   # 40 passed, ~7 s
python -m pytest <16 file: i due sopra, auto_follow, sottoscrizione_a_caldo, stream_stallo, runner_live_strategy,
  paper_live_stesso_processo, review_finale, runner_modo_e_guardia, sync_account_worker_wiring, annuncio_modo,
  tennis iscrizione_a_caldo, valuta_k1, custode_sessione_runner, motore_ordini> -q -p no:cacheprovider            # 309 passed + 1 latenza instabile, 41 s
python AUDIT_2026-09-28/falsifica_cantiere_b.py                                                          # 31 mutazioni, ~8 min (vedi sotto)
cd frontend; npx vitest run src/components/controlroom/RigaCapacitaMercati.test.tsx src/components/controlroom/RigaFreno.test.tsx   # 18 passed
npx vitest run src/pages/ControlRoom.test.tsx                                                           # 112 passed
npx tsc -p tsconfig.app.json --noEmit                                                                   # 0 errori
```

Falsificazioni (file VERI, ripristino sha256 verificato, `MUTAZIONE` = 0 dopo):

| # | Mutazione (difetto reintrodotto) | Esito | Test che scatta |
|---|---|---|---|
| M1 | `kwargs_stream_condiviso` senza `market_data_filter` (seconda connessione) | ROSSA | test_strategie_ordini_riusano_lo_stream_del_recorder |
| M2 | runner: `LiveTradingStrategy` col solo `market_filter` | ROSSA | test_cablaggio_runner |
| M3 | piano: mercati esistenti non restano nel loro frammento | ROSSA | test_pianifica_mai_spostare_un_mercato |
| M4 | frammento 0 lasciato vuoto | ROSSA | test_pianifica_capacita_esaurita_e_frammenti_vuoti |
| M5 | frammento nuovo non agganciato alle strategie | ROSSA | test_oltre_il_tetto_si_apre_un_frammento... |
| M6 | risottoscritti anche i frammenti che non cambiano | ROSSA | idem |
| M7 | capacita' esaurita applicata lo stesso | ROSSA | test_capacita_esaurita_eccezione_dichiarata_nulla_cambia |
| M8 | frammenti muti chiusi anche a rete giu' | ROSSA | test_rete_giu_nessun_frammento_si_chiude |
| M9 | pausa dopo rifiuto ignorata | ROSSA | test_rifiuto_betfair_chiude_il_frammento... |
| M10 | `connectionsAvailable=0` perso (come bflw) | ROSSA | test_riserva_di_connessioni... |
| M11 | riserva ignorata | ROSSA | idem |
| M12 | frammento chiuso che si riconnette (retry infinito) | ROSSA | test_frammento_chiuso_non_si_riconnette |
| M13 | rifiuto Betfair non riconosciuto | ROSSA | test_rifiuto_betfair_chiude_il_frammento... |
| M14 | auto-follow: persi non tolti dagli applicati | ROSSA | test_auto_follow_frammento_muto_i_suoi_mercati_tornano... |
| M15 | auto-follow: manutenzione non chiamata nel giro | ROSSA | test_auto_follow_rifiuto_betfair_rientra_e_dichiara |
| M16 | partite fuori in silenzio | ROSSA | test_auto_follow_capacita_esaurita_fuori_dichiarate_col_motivo |
| M17 | capacita' ridotta senza rientro | ROSSA | test_auto_follow_rifiuto_betfair_rientra_e_dichiara |
| M18 | budget del catalogo sul tetto di UNA connessione | ROSSA | test_cablaggio_runner |
| M19 | auto-follow col sottoscrittore di sempre (una connessione, il difetto del 26/09) | ROSSA | test_cablaggio_runner |
| M20 | frammento 0: i mercati con soldi non vanno davanti | ROSSA | test_ricostruzione_mercati_con_soldi_davanti_nel_frammento0 |
| M21 | runner: frammento 0 senza i mercati con soldi | ROSSA | idem |
| M22 | auto-follow: voci con soldi noti al runner non protette | ROSSA (dopo aver reso sensibile il test, vedi sotto) | idem |
| M23 | sgancio senza ricordare le voci con ordini | ROSSA | test_sgancio_ricorda_le_voci_con_ordini |
| M24 | blotter precedente non letto alla fine del framework | ROSSA | test_cablaggio_ricostruzione_con_soldi |
| M25 | specchio: ordine eseguito (abbinato) non conta | ROSSA | test_specchio_ordini_e_posizioni |
| M26 | soldi dichiarati DOPO il rientro nel tetto | ROSSA | test_cablaggio_ricostruzione_con_soldi |
| M27 | soldi oltre il frammento 0 in silenzio | ROSSA | test_soldi_oltre_un_frammento_dichiarati |
| M28 | chiusura: `remove` sul posto nella lista delle strategie | ROSSA | test_chiusura_di_un_frammento_non_rompe_chi_sta_leggendo |
| M29 | chiusura: `remove` sul posto in `Streams._streams` | ROSSA | idem |
| M30 | run del frammento = run di flumine con `@retry` infinito | ROSSA | test_frammento_chiuso_non_si_riconnette (e il test TCP del rifiuto) |
| M31 | listener che non misura la sua connessione | ROSSA | test_rifiuto_betfair_chiude_il_frammento... |
| UI1 | parser che perde l'elenco delle partite fuori | ROSSA (2 test) | RigaCapacitaMercati.test.tsx |
| UI2 | riga che dice sempre «nessuna partita fuori» | ROSSA (1 test) | RigaCapacitaMercati.test.tsx |

Esito dello script (`AUDIT_2026-09-28/falsifica_cantiere_b_esito.txt`): 30/31 al primo giro; M22 era VERDE
perche' il test espelleva le voci in ordine di chiave e si fermava prima di arrivare a quelle con soldi (test a
vuoto, catalogo §7 n. 29). Corretto il test (event_id che si espellerebbero per primi, capacita' = manuali +
soldi, e controllo dell'insieme finale); M22 rieseguita a mano con lo stesso protocollo (hash del file
ripristinato uguale): ROSSA. Totale **31/31**.

Nota sul ROSSO prima del verde: il test `test_il_vecchio_modo_apriva_due_connessioni` e' il controllo negativo
(riproduce R-B1 con flumine vero); M19 riproduce il difetto del 26/09 (una connessione a 180).

Test preesistente instabile (non mio): `test_auto_follow_2026_09_25.py::test_latenza_logica_aggancio_sotto_i_20_ms`
fallisce 8/8 lanciato da solo **anche con `auto_follow.py` di HEAD** (misurato con il protocollo patch/checkout/
apply: 44 ms contro il limite di 20 a processo freddo); dentro il file intero passa quasi sempre.
Stessa natura `test_motore_ordini_2026_09_24.py::test_latenza_logica_comando_place_sotto_20_ms`: 1 rosso su 5 giri
del file intero sotto carico; da solo 6/6 verde col mio codice e 4/4 con `auto_follow.py` di HEAD.

---

## PARTE 4-bis - RIESAME DEL COORDINATORE (tre punti, chiusi)

### Punto 1 (money-critical): i mercati con soldi dentro nel frammento 0 alla ricostruzione

Difetto (coordinatore): `primo_frammento` metteva davanti solo i manuali; una partita AUTOMATICA con posizione o
ordine vivo e market_id alto poteva finire oltre il frammento 0 e restare senza dati finche' l'auto-follow non
apriva la connessione in piu'. Con una connessione sola il buco non esisteva.

Correzione. Ordine del frammento 0: **con soldi -> manuali -> resto** (`frammenti_mercato.primo_frammento`,
parametro `con_soldi`). Fonti, tutte gia' del runner, nessuna chiamata Betfair (`runner._mercati_con_soldi`):
1. blotter del framework PRECEDENTE, stesso processo (ricostruzione per stallo, relogin, nuove partite): letto
   nel `finally` del giro, prima che si perda (`_FR.mercati_con_ordini(framework)` -> `mercati_con_ordini_prec`);
   qualunque ordine, vivo o eseguito (un eseguito e' una posizione);
2. auto-follow: voci con ordini allo sgancio del framework (`AutoFollow.sgancia` le ricorda), voci di COMANDO
   (un bot ci ha mandato un ordine; i comandi parcheggiati del motore passano da qui), mercati gia' fissati;
3. specchio che il runner stesso scrive, per il riavvio del PROCESSO (blotter perso):
   `betfair_live_orders` (ordine non chiuso o con abbinato > 0) e `betfair_live_positions` (esposizione != 0),
   paper e live, sola lettura a blocchi di 150 id, solo fra i mercati che si stanno sottoscrivendo
   (`_mercati_con_soldi_dallo_specchio`). DB illeggibile = avviso, restano le fonti 1-2.
I soldi si dichiarano all'auto-follow PRIMA del rientro nel tetto (`auto.imposta_con_soldi`): le loro voci sono
protette (`_protetti`), una capacita' che scende non le espelle.
Se i mercati con soldi superano da soli un frammento (180): i primi 180 nel frammento 0, gli altri vanno sui
frammenti aperti a caldo appena lo stream gira (pochi secondi; i comandi su quei mercati aspettano un book NUOVO,
`servibile`, o sono rifiutati DICHIARATI `in_aggancio` oltre `MOTORE_AGGANCIO_MAX_MS`). Dichiarato: stato
`frammenti.costruzione` (`con_soldi`, `oltre_frammento0`, elenco, fonti), log ERROR, alert CRITICAL
`SOLDI_OLTRE_FRAMMENTO0`.
Limite residuo: dopo un riavvio del PROCESSO le posizioni PAPER non esistono piu' (lo specchio paper viene
pulito all'avvio, scelta A6 di sempre); una posizione LIVE su una partita non piu' nel feed ne' seguita a mano
non rientra nei candidati (comportamento di prima, non peggiorato).

Test (RED sul codice precedente, falsificati M20-M27): `test_ricostruzione_mercati_con_soldi_davanti_nel_frammento0`
(220 mercati; tre automatici con market_id alto e soldi da tre fonti diverse -> `ids0[:3]`, poi i 60 manuali; e
una capacita' che scende non li espelle), `test_soldi_oltre_un_frammento_dichiarati`,
`test_specchio_ordini_e_posizioni`, `test_sgancio_ricorda_le_voci_con_ordini`,
`test_cablaggio_ricostruzione_con_soldi`.

### Punto 2: il frammento aperto a caldo ESEGUITO DAVVERO

betfairlightweight non permette un host locale da parametro: `BetfairStream.HOSTS` e' un `defaultdict` che manda
ogni host sconosciuto a `stream-api.betfair.com` (`betfairlightweight/streaming/betfairstream.py:24-28`) e la
porta e' la costante `__port = 443` (`:20`). Alternativa piu' vicina al vero: il test sostituisce solo
`HOSTS[None]` e `_BetfairStream__port`; TUTTO il resto e' vero: TLS (certificato autofirmato generato al volo;
bflw non verifica, `:216-218`), `GestoreFrammenti` con avvio vero (`Thread.start`), `FrammentoMarketStream.run`
-> `MarketStream.run` di flumine -> `create_stream` -> autenticazione, `marketSubscription`, lettura a CRLF, il
`FrammentoListener`, la coda di output di flumine (`handle_output` -> `handler_queue`) e
`Flumine._process_market_books` fino a `process_market_book` di una strategia.
Finto server (`Betfair/stream/tests/test_frammenti_tcp_2026_09_28.py`): messaggi con le chiavi della
documentazione (`connection`/`connectionId`; `status` con `statusCode`, `connectionClosed`,
`connectionsAvailable`, `errorCode`, `errorMessage`; `mcm` con `initialClk`, `clk`, `conflateMs`, `heartbeatMs`,
`pt`, `ct`, `mc`/`marketDefinition`/`rc`/`img`), `marketDefinition` copiata dalla registrazione raw
`_live_raw/35784105/35784105.raw.jsonl` (exchange .it, `regulators: ["MR_ITA"]`).
Tre test, tutti verdi:
- `test_frammento_aperto_a_caldo_arriva_a_process_market_book`: il book arriva alla strategia con
  `streaming_unique_id` del frammento nuovo e il prezzo della registrazione; Betfair (il finto) riceve
  `appKey`, `session`, `marketFilter` del solo frammento, lo stesso `marketDataFilter` del frammento 0,
  `segmentationEnabled`; il listener legge `connectionsAvailable=7`; dopo `stop()` il thread termina;
- `test_rifiuto_max_connection_limit_chiude_e_non_ritenta`: `MAX_CONNECTION_LIMIT_EXCEEDED` all'autenticazione
  -> `manutenzione` chiude, mercato ritornato fra i persi, capacita' 180, thread fermo, **nessuna nuova
  connessione** oltre il primo backoff;
- `test_connessione_che_cade_si_riconnette_con_initialclk_e_clk`: il server chiude dopo l'immagine; il frammento
  si riconnette (seconda connessione) con `initialClk="INIT-1"`, `clk="CLK-1"` e il delta successivo arriva alla
  strategia.
Falsificati da M30 (run con il `@retry` infinito di flumine: il frammento rifiutato continua a riconnettersi) e
M31 (listener che non misura).

### Punto 3: concorrenza e R-B1 sulle chiusure

Chi legge le liste degli stream in flumine 2.13.11, dal thread principale o da altri:
`baseflumine.py:169, 205, 256, 284, 379` (`strategy.stream_ids`), `strategy/strategy.py:229-232`
(`market_cached` itera `self.streams`), `strategy/strategy.py:238-242` (`stream_ids` = list comprehension su
`self.streams`), `streams/streams.py:313-315` (`stop` itera), `:321-322` (`__iter__ = iter(self._streams)`),
`baseflumine.py:483` (`info`). Tutte iterano la lista SENZA copia. Un `remove` sul posto durante una di queste
letture fa saltare l'elemento successivo (un book o una CHIUSURA di un frammento sano persi per quella
strategia): era il caso del mio `_chiudi`. **Corretto**: copia e sostituzione del riferimento in `_apri` e
`_chiudi` (`st.streams = [...]`, `streams._streams = [...]`): l'assegnazione di un attributo e' atomica, chi
sta iterando finisce sulla lista vecchia intera, chi legge dopo vede la nuova intera. Scrittore unico a
framework avviato: il thread dell'auto-follow (flumine scrive quelle liste solo in `add_strategy`/`add_client`,
prima di `run`). `market_filter` delle strategie: assegnazione atomica; letto a `baseflumine.py:379` solo per
`== {}`. Test `test_chiusura_di_un_frammento_non_rompe_chi_sta_leggendo` (lettura a meta', frammento chiuso,
nessun elemento perso), falsificato da M28/M29 (remove sul posto).

R-B1 confermato su flumine vero (`test_rb1_chiusura_di_un_mercato_agganciato_a_caldo_arriva_una_volta`, live e
paper): la chiusura (`marketDefinition.status=CLOSED`) di un mercato su un frammento aperto a caldo produce
UNA `CloseMarketEvent`, UNA chiamata a `LiveTradingStrategy.process_closed_market`; in paper UNA scrittura in
`betfair_live_settled` (upsert su `(mode, market_id)`, `db.py:733-745`: anche due chiamate darebbero una riga);
in live nessuna scrittura da li' (il realizzato live viene dai cleared orders di `daily_stop_worker`, upsert
sulla stessa chiave). Controllo negativo `test_rb1_il_vecchio_modo_non_vedeva_la_chiusura`: con la strategia
degli ordini sulla seconda connessione (il modo di prima) la chiusura del mercato agganciato a caldo non le
arriva mai.

## PARTE 4-ter - SU MASTER (dopo il cantiere A, `7a83206`; master `512db64`)

Procedura (autorizzata dal coordinatore): commit LOCALE di lavoro sul ramo del worktree (`4fd3286`, solo i miei
file, elencati uno per uno), `git fetch`, `git merge origin/master`. Conflitti: 2, entrambi in `runner.py`
(import `_FR`/`_AO`: tenuti entrambi; ricostruzione: `market_ids = mercati_manuali_da_sottoscrivere(session)` di A
+ `con_soldi`/`fonti_soldi` di B). `auto_follow.py` fuso da git senza conflitti. Nessun push.

Le sei note di A (`CANTIERE_A_FINE_EVENTO.md` §9.5), una per una:
1. **Ricostruzione**: si parte da `mercati_manuali_da_sottoscrivere(session)` (A); i mercati con soldi si calcolano
   sull'unione con `auto.mercati_da_sottoscrivere()` dopo `imposta_manuali` (senza le partite finite, codice di
   A) e prima di `rientra_nel_tetto`; il frammento 0 riceve come «manuali» quelli VIVI
   (`_frammento0(market_ids, mercati_manuali_da_sottoscrivere(session), ...)`, prima era
   `session.all_market_ids()`). Falsificati X1, X6.
2. **A caldo**: `_rilascia_mercati_finiti` -> `auto.imposta_manuali(mercati_manuali_vivi(session))` alimenta lo
   STESSO piano/tetto del gestore dei frammenti: al giro dopo dell'auto-follow i mercati escono dal loro frammento
   e un frammento in piu' rimasto vuoto si CHIUDE. Test `test_partita_finita_su_frammento_a_caldo_rilasciata_e_frammento_chiuso`.
3. **`AutoFollow.aggancia`**: l'azzeramento di `_inviato_ts` di A e' rimasto (git l'ha fuso); agganciamo i
   mercati del frammento 0, gli altri ricevono l'orario alla risottoscrizione a caldo (`_applica`). Falsificato X7
   (lo coglie il test di A `test_dopo_la_ricostruzione_i_mercati_automatici_non_sono_mai_arrivati`).
4. **Recorder**: e' UNO solo, condiviso: il gestore aggiunge ogni frammento aperto a caldo alla lista `streams` di
   TUTTE le strategie del frammento 0, recorder compreso, quindi le chiusure di qualunque frammento arrivano al suo
   `process_closed_market`. Test `test_partita_su_frammenti_diversi_finita_una_volta_sola`: MATCH_ODDS sul frammento
   aperto a caldo, un altro mercato sul frammento 0 -> `mercati_chiusi` li vede entrambi, `drain_finished` = [evento]
   una volta sola. (Il recorder conosce solo le partite seguite a mano, `market_to_event`: come prima.)
5. **Uscita ordinata**: `arresto_worker` resta registrato (verificato sul sorgente). All'uscita
   `Flumine.__exit__` chiama `streams.stop()` (`baseflumine.py:523`), che itera la lista che il gestore mantiene
   (copia e sostituzione): TUTTE le connessioni, anche quelle aperte a caldo, si chiudono; `FrammentoMarketStream`
   non si riconnette. Nuovo: il gestore NON apre mai una connessione se non c'e' un frammento vivo (framework non
   ancora nato o gia' fermato): prima, un giro dell'auto-follow fra `streams.stop()` e `auto.sgancia()` avrebbe
   potuto aprire un thread orfano. Test TCP `test_uscita_ordinata_chiude_tutte_le_connessioni_a_caldo` (thread
   VERO connesso al finto server: dopo lo stop il thread termina, nessuna riconnessione) e
   `test_arresto_ordinato_registrato_e_nessuna_apertura_su_framework_fermo`. Falsificato X3.
6. **Una regola sola per i «soldi dentro»**: in `db.py` la regola «posizione aperta non regolata» e' ora UNA
   funzione (`_posizioni_aperte_non_regolate`) usata sia da `soldi_sull_evento` (A, stesso comportamento: stessa
   query, stessa `esposizione_aperta`, stessa esclusione dei regolati, stesso ordine dei controlli) sia dalla
   nuova `db.mercati_con_soldi` (B), che per gli ordini usa gli stessi `STATI_ORDINE_VIVO`/`_stato_ordine` di A.
   Il lettore dello specchio del runner (`_mercati_con_soldi_dallo_specchio`) delega a `db.mercati_con_soldi`.
   Cambia (in meglio, dichiarato) la MIA lettura di prima: un ordine eseguito o una posizione PAREGGIATA o gia'
   REGOLATA non contano piu' come «soldi dentro» (prima: abbinato > 0 o `worst_if_*` != 0); per A nulla cambia.
   Differenza che resta, voluta: A solleva su errore (guardia: soldi presunti), B ritorna vuoto (e' una priorita':
   la costruzione prosegue con le altre fonti). Test `test_specchio_ordini_e_posizioni` (righe con le colonne vere
   di A: `matched_if_win`, `unmatched_*_exposure`, `betfair_live_settled`) e `test_una_regola_sola_per_i_soldi_a_e_b`.
   Falsificato X5.

File toccati in piu' su master: `Betfair/stream/db.py` (fuori dal perimetro originale, su richiesta del
coordinatore, nota 6), `Betfair/stream/tests/test_frammenti_fine_evento_2026_09_28.py` (nuovo, 4 test),
+1 test TCP, `_Socket` finto con `shutdown`/`close` come il socket vero.

Numeri su master (dopo il merge):
- cantiere B: 46 test (`test_frammenti_mercato` 38, `test_frammenti_tcp` 4, `test_frammenti_fine_evento` 4): verdi;
- cantiere A (46) + file collegati a `runner.py`/`auto_follow.py` (17 file, 338 test): 337 verdi + la latenza
  instabile `test_latenza_logica_aggancio_sotto_i_20_ms` (preesistente, rossa anche su HEAD a processo freddo);
- falsificazione dell'incrocio `--solo-merge` (sui test di B + quelli di A): X1-X7 **7/7 ROSSE**; lo script
  completo (M1-M31 + X1-X7) rilanciato su master (`AUDIT_2026-09-28/falsifica_cantiere_b_esito_su_master.txt`):
  36/38 ROSSE, le due restanti spiegate: M25 NON APPLICABILE (la lettura dello specchio e' stata sostituita dalla
  regola unica, la sua mutazione e' X5, ROSSA); X7 VERDE sui soli test di B perche' la coglie il test di A (in
  quel giro i test di A non erano inclusi; nel giro `--solo-merge` si', ROSSA). Lo script ora include sempre i
  test di A e non ha piu' M25. In piu', a mano sul solo file dell'incrocio: X2 e X3 ROSSE su
  `test_partita_finita_su_frammento_a_caldo...` e `test_arresto_ordinato_registrato...`.

Consegna: `AUDIT_2026-09-28/CANTIERE_B_su_master.patch` (232 KB) = `git diff origin/master` (`512db64`) dei soli
18 file di B; `git diff --name-only origin/master` sul ramo fuso elenca ESATTAMENTE quei 18 file (nessun file
altrui). Verifica: `git apply -R --check` sul ramo fuso OK (la patch porta master esattamente allo stato
provato). Il `git apply --check` su un indice temporaneo di `512db64` non l'ho potuto lanciare (il worktree
isolato rifiuta i comandi git con variabili d'ambiente): da rifare dal coordinatore, `git apply --check` sul
checkout principale a `512db64`. Ramo locale: `4fd3286` (lavoro) + `203fc56` (merge), NON pushati.
Frontend dopo il merge: `tsc` 0 errori.

## PARTE 5 - PARITA' PAPER/LIVE

Il trasporto dei dati di mercato e' lo stesso in paper e in live (stesse connessioni, stessi frammenti, stesse
strategie). Cambia per entrambe allo stesso modo: una connessione in meno (R-B1) e la chiusura dei mercati
agganciati a caldo che ora arriva alla strategia degli ordini. Effetto solo in paper: `process_closed_market` della
strategia paper ora scrive in `betfair_live_settled` anche il P&L dei mercati agganciati a caldo (prima mancava);
in live quel metodo e' un no-op (il realizzato viene dai cleared orders di Betfair, gia' completi). E' il paper
che si allinea al live (il P&L di giornata paper, e quindi lo stop giornaliero paper, ora conta anche quei
mercati). Nessuna soglia, stake o cancello toccato.

## PARTE 6 - COSA NON HO FATTO / NON HO POTUTO VERIFICARE

Non fatto:
- Consolidamento dei frammenti quando i mercati calano (3 frammenti con 60 mercati restano 3 connessioni finche'
  uno non si svuota): spostare mercati di un frammento sano e' escluso per regola.
- Runner SENZA auto-follow (`MOTORE_ORDINI_CANALE` spento o `RUNNER_AUTO_FOLLOW=0`): resta a una connessione e 180
  mercati (budget `HARD_MARKET_CAP` come prima).
- Runner tennis e scanner: invariati (scanner gia' a frammenti; tennis ha un tetto suo).
- Commento del bilancio in `scalper/auto_mode.py:28-38` (dice runner calcio 1 connessione): fuori perimetro.
- `npm run build` del frontend: non lanciato (lo fa chi integra, dopo il merge).
- Nessun replay del banco (vietato ai delegati; il banco non usa `setup_and_run`).

Non verificato:
- Nessuna connessione vera: il comportamento di Betfair su una connessione in piu' rifiutata, il valore reale di
  `connectionsAvailable` e il numero massimo di connessioni del conto dell'utente sono dalla documentazione e dai
  forum, non misurati. Il 10 non e' scritto nelle docs ufficiali.
- Limiti specifici del .it: nessuna fonte trovata.
- Il thread vero di un frammento aperto a caldo ora E' eseguito (parte 4-bis, punto 2) contro un finto server
  TLS locale; resta non verificato solo cio' che dipende da Betfair vero (tempi di risposta, `TOO_MANY_REQUESTS`
  su aperture ravvicinate, comportamento su `initialClk` scaduto).
- Il doppio `_process_close_market` di prima (due connessioni) e i suoi effetti sul settled simulato: dedotto dal
  codice di flumine, non riprodotto.

## PARTE 7 - DECISIONI PER L'UTENTE

**(a) Quante partite si possono seguire.** Ogni connessione con Betfair porta al massimo 180 mercati (Betfair ne
ammette 200, teniamo 20 di margine). Una partita dei bot calcio usa in media 3-4 mercati (26/09: 3,6). Con **3
connessioni** (la mia proposta di serie) si seguono **circa 150 partite contemporaneamente** (540 mercati); il
26/09 ne servivano 67, cioe' 2 connessioni. Il conto Betfair ha di serie **10 connessioni in tutto** per tutta
l'app (scanner, runner calcio, runner tennis, scalper); nei momenti di punta l'app ne usa 8-10. Per andare oltre
150 partite serve una di queste due cose: (1) **chiedere a Betfair** (bdp@betfair.com) di alzare il limite del
conto: piu' mercati per connessione (ad altri utenti l'hanno portato a 1000) o piu' connessioni. E' la via
ufficiale; poi basta cambiare un numero nel `.env` (`LIVE_HARD_MARKET_CAP` o `RUNNER_CALCIO_STREAM_CONNS`); (2)
alzare `RUNNER_CALCIO_STREAM_CONNS` a 4, sapendo che nei momenti di punta si toglie una connessione a scanner o
scalper. Proposta: la (1). Se comunque la capacita' finisce, le partite fuori sono elencate nella riga «Mercati»
della Control Room con il motivo; quelle con soldi dentro non escono mai.

**(b) Il P&L paper delle partite agganciate da sole.** Prima della correzione, quando una partita agganciata
automaticamente durante la giornata finiva, il suo risultato in PAPER **non veniva registrato** (mancava la riga
in `betfair_live_settled`): il P&L paper di giornata era piu' basso o piu' alto del vero, e lo **stop giornaliero
paper** poteva non scattare quando doveva (o scattare tardi). Ora quel risultato viene registrato, una volta sola
per mercato, come in live. Effetto pratico: i numeri paper di giornata cambieranno rispetto a prima e lo stop
giornaliero paper potra' scattare prima. Nessuna soglia e' cambiata; in live non cambia niente (il risultato
arriva da Betfair come sempre). Proposta: tenerla (e' il paper che diventa specchio del live).

## PARTE 8 - CONTROLLI DAL VIVO IN PAPER AL PROSSIMO AVVIO

| Controllo | Dato atteso | Dove |
|---|---|---|
| Una sola connessione di mercato all'avvio | nel log flumine una sola riga `Creating new <class 'FrammentoMarketStream'>` e `Using ... for strategy LiveTradingStrategy` | `_logs/runner-calcio_*.log` |
| Feed con N partite idonee -> N seguite, 0 fuori | `auto_follow.feed.partite = N`, `eventi_auto + (partite manuali) = N`, `partite_fuori_n = 0` | canale 47331 (`hello.auto_follow`), riga «Mercati» Control Room |
| Connessioni = ceil(mercati/180) | `connessioni_di_mercato = ceil(mercati_seguiti/180)`, ogni `frammenti.frammenti[i].connesso = true`, `eta_msg_s < 10` | `hello.auto_follow.frammenti` |
| Frammento in piu' aperto a caldo | `[frammenti] APERTO frammento ...` quando i mercati superano 180, nessun `MAX_CONNECTION_LIMIT_EXCEEDED` | log runner |
| Gli altri processi non restano senza connessioni | scanner: `safe_strategy_status.payload.stream_shards[*].ultimo_errore = null`; scalper: sessioni armate senza errore | DB (sola lettura), Control Room |
| Ordini sui mercati del frammento 1 | un comando Omega/Safe su un mercato oltre i primi 180 parte (nessun «non sottoscritto», nessun `in_aggancio` scaduto) | diario motore, `*_activity` |
| Settled paper dei mercati agganciati a caldo | a fine partita riga `betfair_live_settled` mode paper per quei mercati | DB (sola lettura) |
| Ricostruzione con posizioni aperte (se capita: stallo, relogin, nuova partita a mano) | log `[runner] frammento 0: N mercati con soldi dentro davanti a tutti ({fonti})`; `frammenti.costruzione.oltre_frammento0 = 0`; nessun alert `SOLDI_OLTRE_FRAMMENTO0` | log runner, `hello.auto_follow.frammenti.costruzione`, `live_alerts` |
| Capacita' esaurita dichiarata (solo se capita) | `partite_fuori_n > 0` con nomi e motivo, WARNING `[auto-follow] N partite idonee NON seguite` | riga «Mercati», log |
