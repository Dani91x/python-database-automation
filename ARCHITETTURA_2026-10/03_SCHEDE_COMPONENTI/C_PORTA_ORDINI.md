# SCHEDA DI COMPONENTE C - Porta degli ordini e riconciliazione

Data: 08/10/2026. Autore: delegato Sonnet (piano di architettura). Prefisso funzionalita': `C-`.
Regola di lettura: ogni affermazione porta `file:riga` (checkout principale, 08/10/2026), un numero misurato con lo strumento
citato, un'altra scheda gia' verificata (`00_INVENTARIO.md`, `07_MISURE_OGGI.md`, `02_COMPETITOR.md`, `A_CONNESSIONE_BETFAIR.md`)
o una riga di libreria nel `.venv` (flumine 2.13.11, betfairlightweight 2.23.2). Dove non ho potuto verificare lo scrivo
(ultima sezione). La logica di quando/quanto piazzare e' strategia dei bot e NON e' trattata qui: qui si tratta la porta.

Fonti usate (non rifatte): `strumenti/inventario/uscite/s04_dettaglio_copie.tsv` e `s04_riepilogo.txt` (funzioni duplicate),
`07_MISURE_OGGI.md` sez. 2-3 (tempi, richieste DB), `02_COMPETITOR.md` sez. 3.3 e P-09 (Heartbeat API),
`SCHEMI_BOT/sistema/schemi/07_porta_degli_ordini.schede.md` (mappa del 02/10, ricontrollata riga per riga qui sotto),
`AUDIT_2026-09-24/AUDIT_STRADE_ORDINE_2026-09-24.md` (non riletto: solo l'indice), `BRIEF_STANDARD_DELEGATI.md:22` (condizione 2).

## Perimetro (righe `wc -l`, 08/10/2026)

| Gruppo | File | Righe |
|---|---|---|
| Esecutore nel runner | `stream/motore_ordini.py` 2.434, `live_order_worker.py` 3.997, `live_order_build.py` 942, `modo_ordini.py` 406, `arresto_ordinato.py` 77, `client_paper_affiancato.py` 53, `tempi_ordine.py` 455, `engine/live_trading_strategy.py` 424 | 8.788 |
| Riconciliazione e lettura esiti | `stream/reconcile_worker.py` 1.355, `esiti_ordini_canale.py` 850 | 2.205 |
| Controlli e place-and-trim | `stream/trading/` (submin 1.167, controls 524, risk_engine 684, hedging 377, xhedge 372, stato_mercato 267, greenup 249, dutching 242, minimi_it 147, daily_pnl 142, freno_rifiuti 124, init 6) = 4.301; `risk_engine_worker.py` 1.237 | 5.538 |
| Porte lato bot | `safe_strategy/porta_ordini.py` 784, `omega/porta_ordini.py` 237, `mike/porta_ordini.py` 224 | 1.245 |
| REST diretti e terminale vecchio | `omega/omega_market.py:610-1443` (ordini, 834) e `:1445-1794` (letture del conto, 350), `order_exec.py` 390, `order_worker.py` 165 | 1.739 |
| Punti di invio dentro i bot calcio | `safe_strategy/execution.py:440-487, 795-1027, 1061-1515, 1766-1900` (871), `omega_service.py:3039-3113, 3535-3636` (162), `mike/service.py:2190-2379` (189) | 1.222 |
| Riconciliazioni nei bot | `bot_service.py:1117-1341` (224), `execution.py:1607-1700` (93), `omega_service.py:4108-4195, 4337-4465` (215), `mike/service.py:5713-5916` (203), `mike/regolato_conto.py` 359 | 1.094 |
| Tennis | `tennis_live/tennis_live_order_worker.py` 1.831, `esecutore_tennis.py` 618, `guardie_tennis.py` 487, `tennis_scalper/condotta_ordini.py` 867 | 3.803 |
| `_place` dei bot in-process (7 di produzione) | `scalper_bot.py:2743` (171), `tennis_scalper_bot.py:2413` (162), `tennis_pro_bot.py:467` (82), `tennis_flb_bot.py:188` (81), `sniper_bot.py:1083` (74), `tennis_swing_bot.py:244` (69), `mike/engine.py:1876` (17) | 656 |
| **Totale perimetro** | | **26.290** |

Confini con altre schede (citati, non contati): connessione/sessione e order stream = A; `omega_market.py:1-609` (letture mercato) = A/B;
sezioni di `reconcile_worker.py` che non sono ordini (saldo `:140-280`, regolati e P&L `:517-1250`, ~740 righe) restano nel perimetro
perche' stanno nello stesso file, ma sono P&L/conto (scheda di chi tratta il conto): lo dichiaro nel calcolo di par. 4.4.

---

## 1. Oggi

### 1.1 Le strade che portano un ordine a Betfair: SETTE, non una

Decisione dell'utente del 24/09: "la strada UNICA verso gli ordini reali e' il runner con flumine nello stesso processo"
(`motore_ordini.py:3-6`). Il codice di oggi non la realizza: l'ho verificato strada per strada.

| # | Strada | Chi la usa | Dove parte e dove tocca Betfair | Interruttore / stato |
|---|---|---|---|---|
| S1 | **Motore del runner sul canale locale** (`/comando/<attore>`, WebSocket 47331 calcio, 47332 tennis) | desktop (`/order`), Safe, Omega, **Mike in paper** | `motore_ordini.py:948` `_gestisci` -> `:1447` `_esegui` -> `live_order_worker.py:1240-1280` `_place_or_raise` -> `market.place_order` (`:1273`) | desktop sempre (`localTransport.ts:441-447`); Safe `SAFE_ORDINI_VIA_CANALE` e `SAFE_TENNIS_ORDINI_VIA_CANALE` "SPENTI di serie" (`safe_strategy/porta_ordini.py:18-25`); Omega `OMEGA_ORDINI_VIA_CANALE` "SPENTO di serie" (`omega/porta_ordini.py:17`); Mike paper: nessun interruttore, sempre qui (`mike/porta_ordini.py:21`); tennis: `MOTORE_ORDINI_CANALE_TENNIS=1`, "SPENTO di serie" (`tennis_runner.py:2898`) |
| S2 | **Coda nel DB** `betfair_live_order_requests` | desktop se il canale e' giu' o senza chiave (`localTransport.ts:441-442`; `liveOrders.ts:133` RPC `request_betfair_live_order`), Safe (`execution.py:1286-1296` `enqueue_place` `:1766`), Omega (`omega_service.py:3535` `_flumine_enqueue_place`), risk engine (`risk_engine_worker.py:1-3`, accoda le chiusure), follow-through manuale (`live_order_worker.py:1846` `_ft_enqueue_rehedge`) | `live_order_worker.py:3788` `_process_once` -> `:3679` `_dispatch` -> stesso `market.place_order`; la dispatch serve 8 azioni (`:3698-3715`: place, cancel, replace, place_submin, greenup, dutch, cashout_all, cashout_event) | sempre acceso nel runner; riletta ogni 1,0 s (`config_stream.py:229`) |
| S3 | **REST diretto** `omega_market.place_order_live` | **Mike live: sempre** (`mike/porta_ordini.py:5-14` "il live NON cambia (REST)"; `mike/service.py:152-160, 2259`); Safe live se canale e coda non servono (`execution.py:1382, 1394`); Omega live manuale (`omega_service.py:5749`) | `omega_market.py:704` -> `call_mutating` (`:89`) -> bfl `c.place_orders` (`:788`) | "ripiego" di Safe/Omega, via unica di Mike |
| S4 | **REST place-and-trim** `omega_market.place_submin_live` + `cancelOrders`/`replaceOrders` diretti | Safe/Omega/Mike quando l'importo e' sotto il minimo e la strada e' REST | `omega_market.py:1043` (parcheggio `place_orders` `:1131`, `cancelOrders` `:951`, `replaceOrders` `:1252`); annullo `cancel_order_live` `:1327` (`cancelOrders` `:1375`) | idem S3 |
| S5 | **Terminale vecchio** `order_exec.place_order` | pannello "multi trade" della watchlist: HTTP 8787 (`stream/odds_http.py:185`) e coda `betfair_order_requests` (`order_worker.py:73`) | `order_exec.py:215` -> bfl `c.place_orders` (`:340`, `customer_strategy_ref="watchlist"` `:342`) | NON acceso dall'app: parte solo da `start_order_server.py` (56 righe; `SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md` F-11) |
| S6 | **Bot dentro il proprio flumine** (`market.place_order` nativo) | scalper/sniper/media-under calcio e i 4 bot tennis (flb, pro, scalper, swing); worker tennis con coda propria `tennis_live_order_queue` | `scalper_bot.py:2924`, `sniper_bot.py:1150`, `media_under_bot.py:2181`, `tennis_flb_bot.py:253`, `tennis_pro_bot.py:533`, `tennis_scalper_bot.py:2557`, `tennis_swing_bot.py:298`, `tennis_live_order_worker.py:717, 1080`; client proprio: `scalper_session.py:1786` (`order_stream: True`, `paper_trade` secondo la sessione `:800-801`), `run_tennis_scalper.py:266-271` | acceso dall'utente per sessione; NESSUN passaggio dal motore (`git grep MotoreOrdini` trova solo `runner.py:99,2466` e `esecutore_tennis.py:611-613`) |
| S7 | **Annullo REST di arresto** | sessione scalper allo spegnimento | `scalper_session.py:532` (`cancel_orders` per betId noti) e `:540` (`cancel_orders(market_id=mid)` market-wide se il blotter e' illeggibile) | fallback di emergenza |

Conto dei siti che chiamano davvero Betfair, con `git grep` sul codice tracciato escluso test, banco e laboratorio:
- flumine `market.place_order(`: **12** siti (`live_order_worker.py:1273`; `submin.py:234, 237`; `tennis_live_order_worker.py:717, 1080`;
  `media_under_bot.py:2181`; `scalper_bot.py:2924`; `sniper_bot.py:1150`; 4 bot tennis);
- REST `place_orders` (bfl): **3** siti (`omega_market.py:788, 1131`; `order_exec.py:340`); `Betfair/client.py:329` definisce un `place_orders`
  JSON-RPC nostro che NESSUN file di produzione chiama (il grep `\.place_orders(` non lo trova fra i chiamanti: candidato a codice morto, 98 righe `:329-426` con le letture);
- REST `cancelOrders`/`replaceOrders`: `omega_market.py:951, 1252, 1375`; `scalper_session.py:532, 540`.

**Safe da solo usa tre strade** a seconda di interruttori e gate: canale (`execution.py:1219-1233`), coda (`:1286-1296`), REST (`:1382-1399`).
Il codice che sceglie fra le tre sta DENTRO ogni bot (`execution.place` 455 righe `:1061-1515`; omega `omega_service.py:5690-5830`; Mike `service.py:2195-2379`),
non in un punto solo.

### 1.2 Cosa fa il percorso del runner (S1 + S2), nell'ordine

1. **Ricezione** (S1): il canale sveglia il thread "motore-ordini-<sport>" (`motore_ordini.py:841` `_ciclo`, `:878` `drena`); ack immediato o rifiuto con motivo
   (`:935`, `:940`), dedup per `ref` che sopravvive al riavvio (`:2342` `_carica_visti`), `seq` per attore, `da_seq` con memoria degli ultimi 500 (`:2245`).
2. **Controlli** (`_controlla` `:1035`): modo per comando e client per modalita' (`live_order_worker.py:276` `_client_for_mode`, `:317` `_assert_order_mode`),
   kill-switch ENV+DB (`:454`, `:581`) con eccezione delle chiusure (`_is_closing_row` `:113`, `_CLOSING_ACTIONS`), guardia d'avvio (solo `cancel`),
   settings in RAM con eta' dichiarata (`:486` `_refresh_settings`, `:575` `eta_settings_s`), stake massimo/minimo (`:370, :393`), esposizione per selezione (`:585, :635`),
   ordini al minuto (`:589, :624`).
3. **Minimi .it** (`_applica_minimi` `:1265`): ordine sotto il minimo -> equivalente sull'altra selezione di un mercato a due esiti (`altro_runner_due_esiti` `:494`),
   oppure place-and-trim (`_avvia_submin` `:1678`), oppure rifiuto `SOTTO_MINIMO_NON_PIAZZABILE`; ripiego unico `ripiego_050` (docstring `:46-50`).
4. **Diario write-ahead** su disco con flush+fsync PRIMA di ogni `place_order` (`Diario` `:183-254`, `_pre_invio` `:1424`); il DB lo scrive uno scrittore asincrono
   (`ScrittoreAsincrono` `:256-353`), mai il percorso dell'ordine.
5. **Piazzamento**: `build_order` (`live_order_build.py`, ultima barriera) e `market.place_order` di flumine; la `customerStrategyRef` e' quella dell'attore
   (`live_order_worker.py:93` `_strategy_ref_corrente`; usata a `:1274, :1362, :3060, :3123`).
6. **Esito e specchio**: `LiveTradingStrategy` scrive la riga con `db.upsert_live_order` (`engine/live_trading_strategy.py:284` -> `stream/db.py:773`): pubblica su canale
   (`db.py:790`), avvisa gli osservatori del motore (`:791`), poi accoda all'asincrono (`:796-800`). Il motore emette l'evento `order` con fase (`_emetti` `:1892`, `fase_da_riga` `:524`).
7. **Sorveglianza** di FOK non abbinati e riprezzi (`avanza_sorvegliati` `:1992`, `avanza_riprezzi` `:2048`, TTL FOK `live_order_worker.py:1532-1612`).

La coda DB (S2) fa gli stessi passi ma parte da una riga: `_claim` atomico `pending->processing` (`:904`), `_audit` (`:918`), `_journal_scrivi` (`:1079`), `_write_done/_write_error`
(`:1168, :1181`), poi lo stesso `_do_place` (`:1423`).

### 1.3 Dove sta il DB nel percorso decisione -> placeOrders -> specchio

| Tratto | DB nel percorso? | Fonte |
|---|---|---|
| Bot: decisione -> riserva della riga (`safe_strategy_trades`, `omega_trades`, `mike_trades`) | **SI, prima dell'invio** (scelta di sicurezza: "prima si scrive la riga di riserva, poi si piazza") | `mike/service.py:2198-2204` e `:2254-2257`; Safe `execution.aggiorna_trade` `:417`; Omega `_flumine_enqueue_place` `:3535-3636` |
| S1: ricezione -> `_dispatch` | NO: "fra ricezione e `_dispatch` non c'e' IO DB" (settings in RAM) | `motore_ordini.py:13-17` |
| S2: bot -> riga di coda -> worker | **SI**: insert, poi lettura ogni 1,0 s (`config_stream.py:229`), claim, audit, journal, done: ~3 scritture per ordine (`PROGETTO_PAPER_VIA_FLUMINE_2026-09-16.md:103-104`) | `live_order_worker.py:904-1215` |
| Betfair -> specchio | DB **dopo**, in asincrono (S1); sincrono nel worker (S2) | `motore_ordini.py:20-22`; `db.py:790-800` |
| Esito -> bot | Il runner pubblica l'esito sul canale (topic `order`), ma Omega e Safe lo leggono ancora dallo specchio nel DB (`poll_flumine_pending`: fino a 20 s Omega, 2 s Safe) a meno di `ESITI_ORDINI_CANALE`, "SPENTO di serie" | `esiti_ordini_canale.py:1-25`, `omega_service.py:4108`, `bot_service.py` (poll di Safe) |

Misure (da `07_MISURE_OGGI.md` sez. 3, NON ricalcolate; sono paper, orologi DB/PC diversi): `place` via coda DB n=38 **p50 492 ms, p95 2.481, p99 26.636, max 36.524**;
`cancel` n=8 p50 406 p95 874; `replace` n=3 p50 307; `place_submin` p50 8.464 (attesa voluta). Strada canale: 84/108/194 ms, n=3, tutte con esito errore: non e' una misura.
Lettura della coda: `betfair_live_order_requests` GET 202,3/min, `betfair_live_risk_rules` 164,7/min, `rpc/get_live_settings` 119,9/min a stream attivo il 04/10
(`07_MISURE_OGGI.md:224`). Risposta di Betfair a `placeOrders`: **non misurabile oggi** (1 richiesta live in tutta la storia; 4 ordini live del runner, place->match 17,2 s e 24,2 s, n=2: `07:172-173`).

### 1.4 Specchio `betfair_live_orders`: chi scrive, chi legge

- **Scrive**: `stream/db.py:773` `upsert_live_order` (chiave `(mode, client_order_ref)`, `on_conflict` su indice non parziale `db.py:774-785`), chiamata da UNA sola riga
  (`live_trading_strategy.py:284`); `reconcile_worker.py:472` (righe `source='account'`, `ext<bet_id>`); `db.py:1139` (cancella il paper); `db.py:907` lettura per bet_id.
  Il tennis NON usa questa tabella: ha il gemello `tennis_live_orders` con `tennis_db.py:593` `upsert_tennis_order` e `tennis_live_order_worker.py:543` `_mirror_order` (righe `:565`).
  Le sessioni scalper scrivono nello specchio calcio tramite una sottoclasse di `LiveTradingStrategy` (`scalper_session.py:1095-1130`).
- **Legge** (grep `betfair_live_orders`, produzione): `mike/db.py:233, 691`; `omega/omega_db.py:684-687`; `safe_strategy/bot_db.py:1040`; `safe_strategy/db.py:495`;
  `stream/db.py:447, 474` (stato vivo per evento); `stream/xhedge_worker.py:95`; `scalper/media_under_bot.py:58, 200` (`TABELLA_ORDINI_CONTO`); `reconcile_worker.py:29, 472`;
  frontend: `useControlRoom.ts` (2), `liveOrders.ts` (4), `ordiniCanale.ts` (1) (`git grep -c`). **9 file Python di produzione + 3 del frontend** leggono la stessa tabella con proprie query.
- Colonna `source`: 98 righe `account` e 4 `runner` su 102 totali (`07:172-173`); vincolo `betfair_live_orders_source_check` (`db.py:811`) che elenca i bot (mike, omega, safe...).

### 1.5 customerStrategyRef e customerOrderRef (consapevolezza degli ordini)

| Attore | `customerStrategyRef` | Fonte |
|---|---|---|
| runner (UI e coda) | `live` (default), poi quello dell'attore del comando | `live_order_worker.py:64, 93` |
| Omega | `omega` | `omega/omega_config.py:19` |
| Safe calcio / tennis | `safe` / `safe_tennis` (prefissi ref `safe-t`, `safe_tennis-t`) | `bot_service.py:80`; `safe_strategy/porta_ordini.py:177-178` |
| Mike | `mike` | `mike/config.py:30` |
| terminale vecchio | `watchlist` | `order_exec.py:342` |
| tennis (app) | `tennis` | `stream/db.py:1027-1030` |
| scalper | l'`event_id` (max 15 caratteri: limite di Betfair `omega_market.py:32`) | `scalper_session.py:892` |

`customerOrderRef`: i bot calcio usano un ref deterministico dalla riga (`safe-t<id>`, `omega-t<id>`, `mike-t<id>`, troncato a 32: `omega_market.py:760`, `execution.py:1386`);
il runner usa `awlq<rid>` (`order_worker.py:11`, `db.py:777`) e `risk<id>` per il risk engine (`risk_engine_worker.py:18-20`); **ma il `customerOrderRef` che flumine invia a Betfair
e' il suo**: "customerOrderRef = ref del comando: NON fattibile senza rompere il riconoscimento degli ordini di flumine" (`motore_ordini.py:60-62`). Per questo il diario lega ogni ref
al `customerOrderRef` vero (riga `ordine`). Dopo un riavvio un ordine ricostruito dall'order stream perde il ref interno `awlq<rid>`: serve `find_live_order_ref` (`db.py:897`)
per non creare una seconda riga che xhedge conterebbe due volte. `reconcile_worker.py:674` ammette che `customerStrategyRef` "oggi mente per Safe".

### 1.6 Riconciliazioni: NOVE implementazioni distinte

| # | Dove | Righe | Cosa confronta | Quando |
|---|---|---|---|---|
| R1 | runner `reconcile_worker.py:359` `_reconcile_orders` (+ `_fetch_current_orders` `:281`) | ~110 (ordini; il resto del file e' saldo/P&L) | `listCurrentOrders` paginato vs specchio; ordini esterni -> `source='account'`; divergenze: vince il conto | solo LIVE (`:55`) |
| R2 | motore `motore_ordini.py:2354` `riprendi_da_diario` | 80 | comandi `inviato` senza `esito` nel diario -> `listCurrentOrders` per customerOrderRef; guardia d'avvio ARMATA se Betfair KO (`:2386-2398`) | all'avvio |
| R3 | `live_trading_strategy.py:305` `_reconcile_ref_by_bet` + `db.py:897` `find_live_order_ref` | ~25 | bet_id ricostruito dall'order stream vs riga specchiata | post-riavvio |
| R4 | Safe `bot_service.py:1117` `reconcile_pending` (224) + `execution.py:1607` `reconcile_decision` + `bot_service.py:1647, :1678` | ~410 | riga `reconciling` vs `list_current_orders`/`list_cleared_orders`/posizione di conto | ogni ciclo del bot (`bot_service.py:10190`) |
| R5 | Omega `omega_service.py:4337` `reconcile_pending` (128) + `omega_engine.py:718` `reconcile_decision` + `omega_service.py:4108` `poll_flumine_pending` (87) | ~330 | idem, con grazia 20 s | `omega_service.py:8044, 8131` |
| R6 | Mike `service.py:5713` `_reconcile_trades` (103) + `:5816` `_reconcile_unknown` (100) + `regolato_conto.py` (359) | ~560 | idem, "mai un'ipotesi: senza accesso a `listCurrentOrders` si RESTA in riconciliazione" (`:5825`) | ogni ciclo |
| R7 | tennis `tennis_live_order_worker.py:1167` `_reconcile_tracked`, `:1277` `_reconcile_bots` | ~175 | blotter flumine -> `tennis_live_orders` | positions_worker (`:1396`) |
| R8 | follow-through manuale `live_order_worker.py:1914` `_check_manual_followthrough` | 160 | uscita manuale non abbinata -> re-hedge in coda | worker |
| R9 | scalper `scalper_session.py:2065` (`SCALPER_RECON`) + `media_under_bot.py:58, 200` (posizione dal conto) | n.d. | ordini della sessione vs conto | sessione |

In piu': `omega_market.py:1445-1794` (`order_state_by_bet_id` `:1462`, `list_current_orders*` `:1565-1591`, `list_cleared_*` `:1633-1706`, `posizione_di_conto` `:1733`) sono le
**letture del conto** che R4, R5, R6 usano ciascuna a modo suo, e il banco ha un suo finto (`backtest/banco_comune.py:1024-1028`). Difetti gia' scritti nella cronostoria
(non riverificati da me): Omega `omega_service.py:3131-3221` ripiego > 20 s puo' marcare fallita una chiusura tradotta abbinata -> doppia chiusura; Safe `bot_service.py:1473-1503`
scrive sulla riga Over i numeri dell'ordine vero (`CRONOSTORIA.md:4833`).

### 1.7 Ripresa dopo riavvio: doppi ordini?

Protezioni che ho trovato: `customerOrderRef` deterministico e dedup di Betfair su 60 s (`order_exec.py:8-9`; `omega_market.py:760`); `call_mutating` NON ritenta un errore generico
(un timeout puo' nascondere un ordine accettato; ritenta solo `INVALID_SESSION`: `omega_market.py:89-112`); esito IGNOTO = `RuntimeError` -> riconciliazione, mai un secondo invio
(`omega_market.py:801-803`; `execution.py` regola 2 `safe_strategy/porta_ordini.py:29-31`); diario e `riprendi_da_diario` (R2); dedup dei ref visti che sopravvive (`_carica_visti`).
Buchi: (a) un ordine **paper** in volo e' "perso_paper" al riavvio (`motore_ordini.py:2404`: il blotter simulato non sopravvive); (b) il diario esiste solo da quando il motore e' montato:
la cartella `_diario_ordini/` non esiste su questo PC (`07:184-185`): **nessun ordine reale e' mai passato dal motore su questa macchina**; (c) Mike live (S3) non usa ne' diario ne' motore:
la sua protezione e' la riga di riserva + riconciliazione (`mike/service.py:2198-2216`), Omega/Safe REST idem; (d) due riconciliatori diversi (R4/R5/R6) possono decidere in modo diverso sullo stesso ordine ignoto (par. 3).

### 1.8 Paper vs live: lo stesso percorso? (condizione 2, `BRIEF_STANDARD_DELEGATI.md:22`)

- **Si**, dove l'ordine passa dal runner: Safe/Omega/Mike-paper sul canale o sulla coda usano lo stesso `_dispatch`; la differenza e' il client scelto per modalita'
  (`live_order_worker.py:276, 3679-3687`; `runner.py:2129-2181`: LIVE `order_stream=True` reale, PAPER `order_stream=True` con `SimulatedOrderStream`, OFF nessuno) e il bet delay
  e i parziali sono quelli del simulatore di flumine (`simulatedexecution.py:11`).
- **No**, dove l'ordine NON passa dal runner: **Mike live = REST (S3), Mike paper = runner (S1)**: sono due percorsi diversi (`mike/porta_ordini.py:5-15` lo dichiara: "cambia solo CHI esegue in paper");
  Safe/Omega live possono cadere sul REST (S3) mentre il paper non puo' ("paper_senza_runner", `execution.py:1317-1334`); scalper e tennis in-process: in paper `paper_trade=True`
  (`scalper_session.py:790-801`, `run_tennis_scalper.py:9, 270-271`), in live il client reale, senza il motore (nessun diario, nessuna dedup per ref, nessun kill-switch del runner:
  hanno le loro guardie `condotta_ordini.py`, `guardie_tennis.py`).
- Il documento `ESECUZIONE_LIVE.md` (14/09) e' in parte superato: dice runner fermo dal 2/09 e FILL_OR_KILL forzato su REST (`mike/feed.py:284`); oggi quel commento sta a `mike/feed.py:477`
  e il REST sa piazzare l'ordine appoggiato con `fill_or_kill=False` (`omega_market.py:704-707`, usato da `mike/service.py:2259-2262`). Il principio ("stessi ordini in paper e live") resta valido.

### 1.9 Order Stream

Lo apre flumine, non noi: `BetfairClient(..., order_stream=True)` nel runner (`runner.py:2161-2162`, conflate `ORDER_STREAM_CONFLATE_MS` `config_stream.py:235`, default 0 -> `None`), nelle sessioni scalper
(`scalper_session.py:800`) e nel tennis scalper live (`run_tennis_scalper.py:266-267`). Lo consumiamo solo indirettamente: i fill arrivano alle `Order` di flumine e noi leggiamo l'ordine
(`_order_snapshot` `live_order_worker.py:834`). Nessun consumatore nostro dell'order stream fuori da flumine (grep `OrderStream` nei runner: solo i commenti `runner.py:2129-2181`).

### 1.10 Chiamate di rete e orologi nel percorso critico

REST nel percorso: S1/S2 nessuna (flumine `place_order` esegue `placeOrders` in un thread del pool di esecuzione; l'attesa e' quella di Betfair); S3/S4 sincrone nel thread del bot
(`call_mutating`); place-and-trim REST fa 3 chiamate sincrone (`execution.py:1352-1356` "tre chiamate REST sincrone"). Orologi: `LIVE_ORDER_QUEUE_POLL_SEC` 1,0 s e **un secondo default 2 s** in
`order_worker.py:26` (stessa variabile, due default: `INVENTARIO_COMPONENTI_2026-09-25.md:813`); l'app forza 0,15 (`desktop/main.js:233` secondo lo stesso documento, non riverificato).
Thread: motore (1 a sport), scrittore asincrono (1), worker flumine; processi: runner calcio, runner tennis, scalper (1 per sessione), bot Safe/Omega/Mike (processi separati: `reconcile_worker.py:9`).

---

## 2. Funzionalita'

Legenda: **[UI]** visibile nella UI (file del pannello), **[PAR]** parametro editabile. Ordine: porta (C-001..), controlli, minimi, esecuzione, esiti, riconciliazione, tennis/scalper, strumenti.

**Porte e protocollo**
- C-001 `motore_ordini.py:692-840` Motore per sport (calcio oggi; tennis con esecutore proprio): thread a evento, `avvia/ferma/aggancia/sgancia`.
- C-002 `motore_ordini.py:391` `valida_comando`: schema del comando (`CHIAVI_COMANDO`), interi/float/testo con rifiuto esplicito, `creato_ms` intero.
- C-003 `motore_ordini.py:935-946, 2245` Ack immediato (accettato/rifiutato + motivo + `seq`), `da_seq` con memoria degli ultimi 500, un contatore `seq` per attore.
- C-004 `motore_ordini.py:2342` Dedup per ref che sopravvive al riavvio (`MOTIVO_REF_GIA_VISTO`).
- C-005 `motore_ordini.py:2264` `_servi_order`: il `/order` del desktop servito dallo stesso motore [UI: `localTransport.ts:441`, `liveOrders.ts`].
- C-006 `safe_strategy/porta_ordini.py` `PortaCanale`/`MemoriaComandi`/`Ack`: client WebSocket persistente, header `X-Canale-Token`, ack entro `max_eta_ms`, eventi con `seq`.
- C-007 `safe_strategy/porta_ordini.py` `PortaOggi`: il trasporto di oggi (coda se il gate e' aperto, REST FOK altrimenti), byte per byte, per dare un nome al ripiego e ai test di parita'.
- C-008 `omega/porta_ordini.py` `VistaOmega`: adatta il comando di Safe (`strategy_ref=omega`, tabella `omega_trades`, ref annullo `omega-c<bet_id>`, FOK, `reduces_liability`).
- C-009 `mike/porta_ordini.py` `VistaMike`: idem per Mike (`mike_trades`, `mike-c<bet_id>`), tipo d'ordine uguale al live (FOK sui taker, lay appoggiata `LAPSE`), runner giu' = `paper_senza_runner`.
- C-010 `safe_strategy/execution.py:795` `_place_via_canale`, `:975` `_annulla_via_canale`: costruzione del comando e interpretazione dell'ack/eventi; `:953` `rifiuto_catena_asincrono`.
- C-011 `safe_strategy/execution.py:1766` `enqueue_place`: riga di coda con `place`/`place_submin`, `equivalente_ammesso`; `:1741` gate.
- C-012 `omega_service.py:3039` `_flumine_gate`, `:3098` `_flumine_paper_gate` (fail-closed), `:3535` `_flumine_enqueue_place`.
- C-013 `live_order_worker.py:3457` `_process_local_requests`, `:3945` `esegui_richieste_locali_scelte`: i comandi locali passano da `_dispatch` con shim `_LocalSb`/`_SbDifferito` (`:3277, :3404`) perche' il worker scriva sul DB "finto" differito.

**Controlli e freni**
- C-020 `live_order_worker.py:454` kill-switch ENV + `:581` DB; blocca le aperture, mai le uscite (`:113`, `ESECUZIONE_LIVE.md:122-125`). [PAR: `LIVE_KILL_SWITCH`; UI Control Room]
- C-021 `live_order_worker.py:168, 184, 235` `LIVE_ORDER_MODE` (OFF/PAPER/LIVE) e blocco per modalita' della riga. [PAR: "Ordini reali" della Control Room, `07_MISURE_OGGI.md:235`]
- C-022 `live_order_worker.py:370, 393, 585, 589` stake massimo/minimo, esposizione massima per selezione, ordini al minuto (`_rate_guard` `:624`). [PAR: settings DB `get_live_settings`]
- C-023 `live_order_worker.py:1216` cap effettivo per riga; `:635` guardia di esposizione per selezione.
- C-024 `trading/freno_rifiuti.py` freno dopo rifiuti di Betfair (124 righe); `tennis_scalper/condotta_ordini.py` `FrenoRifiuti` (gemello per i 4 bot tennis, misura 17/09: 8.132 e 20.534 ritentativi in una partita, docstring `:30-37`).
- C-025 `trading/controls.py` (524) controlli nativi: stake, esposizione, rate. `trading/stato_mercato.py` (267) stato mercato (sospeso/chiuso).
- C-026 `mike/service.py:2210-2224` kill-switch condiviso sulla strada REST di Mike (solo aperture); `execution.py:138, 199` `_live_brake`, `_freno_aperture`.
- C-027 `tennis_live/guardie_tennis.py` (487): un bot PAPER dentro un runner LIVE non puo' piazzare con soldi veri (`:16-20, :123`).
- C-028 `stream/modo_ordini.py` (406): modo effettivo del processo (tetto env x scelta app); `arresto_ordinato.py` (77): arresto ordinato; `live_order_worker.py:529` pubblica il modo.
- C-029 `live_order_worker.py:1532-1612` TTL dei FOK non abbinati con allarme.

**Minimi, tick, punte**
- C-030 `live_order_build.py` `build_order`, `min_stake_rules` (JURISDICTION_IT): BACK minimo 1,00 e multipli di 0,50, LAY 1,00, nessuna eccezione per le chiusure (`:12-25`).
- C-031 `trading/minimi_it.py` (147) costanti .it (`IT_MIN_BACK`, `IT_PASSO_PUNTA_DIRETTA`, `SOTTO_MINIMO_NON_PIAZZABILE`); importate da `order_exec.py:34-37`, `omega_market.py:867`.
- C-032 `motore_ordini.py:1265` `_applica_minimi`, `:494` equivalente sull'altra selezione di un mercato a due esiti, `:1381` ripristino.
- C-033 `trading/submin.py:144, 195` `SubminOps`/`FlumineSubminOps` (1.167): place-and-trim a macchina a stati, usata dal motore (`motore_ordini.py:1678-1890`), dal worker (`live_order_worker.py:3008-3180`) e dal REST (`omega_market.py:858` "nucleo unico").
- C-034 `omega_market.py:1008` `piano_submin_live`: piano di trim estratto per usarlo anche in paper (D1-ter).
- C-035 `execution.py:1028` `_dichiara_punta_050`; `omega_market.py:754` punta .it a multipli di 0,50 per difetto con `punta_050` {chiesto, piazzato, residuo, motivo}; `live_order_worker.py` ripiego unico a 0,50 (`motore_ordini.py:46-50`).
- C-036 `execution.py:113` `_porta_al_minimo_tennis`; `tennis_scalper/condotta_ordini.py` `size_legale` (ingressi portati al minimo, uscite bumpate): **seconda definizione** delle regole di taglia (par. 3).
- C-037 `execution.py:562-665` `_equivalente_possibile/_equivalente_rest`: equivalente sul REST (stesso verdetto del canale).

**Esecuzione e ciclo di vita dell'ordine**
- C-040 `live_order_worker.py:1240-1312` `_place_or_raise/_cancel_or_raise/_replace_or_raise` (`size_reduction` per annullo parziale `:1284`).
- C-041 `live_order_worker.py:1423, 1613, 1639` `_do_place/_do_cancel/_do_replace`; `:2220` `_do_greenup`, `:2414` `_do_dutch`, `:2818/:2858` `_do_cashout_all/_event` (chiusure composte; `trading/greenup.py`, `dutching.py`, `hedging.py`).
- C-042 `motore_ordini.py:1175` `_traduci_annullo` (cancel/replace su ordine tradotto), `:1395` `_riduzione_verificata` (`reduces_liability` verificata sulle esposizioni abbinate, mai dai params).
- C-043 `motore_ordini.py:1576-1665` aggancio/parcheggio comandi su mercato non ancora sottoscritto (`avanza_aggancio`).
- C-044 `motore_ordini.py:1981-2244` sorveglianza FOK e riprezzi (`_ripiega`), rifiuto per taglia non ritentata identica (`:650, :2178`).
- C-045 `omega_market.py:704` `place_order_live`: validazione prima della rete, minimi, punta, `customerOrderRef` (max 32), `customerStrategyRef`, esito IGNOTO; `:1327` `cancel_order_live` rilegge l'esito da Betfair (`CancelResult` `:675`); `:1429` `place_lay_live`.
- C-046 `omega_market.py:89` `call_mutating`: mai ritenta, relogin solo su sessione non valida, rilettura del saldo in thread a parte (`_segnala_saldo`).
- C-047 `order_exec.py:215` terminale vecchio: marcatura fixture -> market -> selezione blindata, `customerRef` deterministico, minimo, tick (`round_to_tick` `:115`), coda `betfair_order_requests` (`order_worker.py:45-128`, claim atomico, mai ripiazza una riga `processing`, `_alert_stuck` `:129`).
- C-048 `risk_engine_worker.py` + `trading/risk_engine.py`: regole risk su `betfair_live_risk_rules` (offset immediate/on_fill, bracket OCO, stop a due parametri, policy `on_inplay`), accodano le chiusure con ref deterministici `risk<id>`, `risk<id>o`, `risk<id>oc`, `risk<id>s`. [UI: pannello risk del trading]
- C-049 `trading/xhedge.py` + `stream/xhedge_worker.py`: hedge incrociato dalle posizioni MATCHED dello specchio (`xhedge_worker.py:95`).

**Esiti, specchio, eventi**
- C-050 `motore_ordini.py:524` `fase_da_riga`, `:553` `riga_specchio_da_esito`, `:1892` `_emetti`: fasi (parcheggiato, ridotto, scaduto, annullato, abbinato...) con `esito_ms`; `seq` mai indietro.
- C-051 `stream/db.py:773` `upsert_live_order` (idempotente, write-on-change, publish A7 sul canale, osservatori F3). [UI: `liveOrders.ts`, `ordiniCanale.ts`, Control Room]
- C-052 `esiti_ordini_canale.py` (850): lettore degli esiti terminali dal canale al posto di `get_live_order_mirror`; solo terminali, interruttore `ESITI_ORDINI_CANALE` spento.
- C-053 `tempi_ordine.py` (455): una riga `tempi_ordine` per ordine (decisione, ricezione, presa, place, risposta, abbinato); agganci `live_order_worker.py:1271, 2938, 3481, 3688, 3864`, `motore_ordini.py:950, 1014, 1516` (`07:145`).
- C-054 `live_order_worker.py:834` `_order_snapshot` e `_journal_scrivi:1079` (journal di ogni richiesta con book e segnale `:972-1020`).
- C-055 Diario write-ahead su disco (`motore_ordini.py:183-254`): `inviato`, `ordine` (con customerOrderRef vero), `esito`, `ripresa`.

**Riconciliazione**: C-060..C-069 = R1..R9 della tabella par. 1.6 (stessi file:riga), piu' C-069b `reconcile_worker.py:1249` rapporto di ripresa A6 (INFO con riepilogo conto/specchio; regole armate senza `entry_bet_id`).

**Tennis e scalper**
- C-070 `tennis_live_order_worker.py:1699` `tennis_live_order_worker`: worker del runner tennis con coda `tennis_live_order_queue`, `_do_place:645`, `_do_cancel:784`, `_do_replace:797`, `_do_greenup:911`, `_dispatch:1111`, cross-mode `:1506`.
- C-071 `esecutore_tennis.py` (618): adattatore che fa chiamare al motore del calcio i nomi di `LOW.*` con l'esecutore tennis (spento di serie).
- C-072 `tennis_scalper/condotta_ordini.py` (867): taglia legale, freno rifiuti, cancellazioni dei 4 bot tennis (`:483, :497`), `_OpsCattura` `:619`.
- C-073 `scalper_session.py:532-545` annullo di arresto; `:613-650` annullo ordini vivi allo stop; `:1095` specchio della sessione.
- C-074 `submin.py:234-253` `FlumineSubminOps.place/cancel/replace` chiamano il `Market`.

**Strumenti e certificazione**
- C-080 `backtest/banco_comune.py:651, 833, 1244` `place_order_live`/`cancel_order_live`/`place_order_utente` del banco: il finto con le stesse chiavi del vero.
- C-081 `safe_strategy/certificazione.py:1320-1342, 1764`, `omega/certificazione.py:682`, `scalper/certificazione.py:1222` (controllo P1: ogni ordine arriva allo specchio): controlli di condotta sugli ordini.
- C-082 `mike/regolato_conto.py:242-263` regolato dal conto (`listCurrentOrders` o topic `conto`); `mike/service.py:2598-2800` letture correnti.

Totale: **55 voci numerate (C-001..C-082, non contigue) + 9 riconciliazioni (C-060..C-069)** (le voci C-0xx non sono contigue; la numerazione resta aperta per i gruppi).

---

## 3. Difetti strutturali

1. **Sette strade, tre dentro lo stesso bot, scelta spalmata nei bot** (par. 1.1). Il motore e' "strada unica" solo per la UI e (con interruttori spenti di serie) per Safe/Omega;
   Mike live, scalper, tennis, terminale vecchio, annulli di arresto non lo attraversano. Mike live non ha diario, dedup per ref ne' kill-switch del runner (ha il suo `mike/service.py:2210`).
2. **Codice gemello fra le strade** (misurato):
   - `live_order_worker.py` vs `tennis_live/tennis_live_order_worker.py`: **22 funzioni di primo livello con lo stesso nome** (`comm -12` sui `def`): `_best_prices, _blocco_apertura_modo, _cust_ref, _dispatch,
     _do_cancel, _do_greenup, _do_place, _do_replace, _f, _find_order_by_bet_id, _int, _jurisdiction, _level_price, _now_iso, _order_snapshot, _process_local_requests, _read_matched_exposures,
     _resolve_market, _result, _status_name, _tempi_on, _val` (righe: LOW `:1423`, tennis `:645` per `_do_place`; `:1613`/`:784`; `:2220`/`:911`; `:1684`/`:855`; `:1725`/`:832`; `:834`/`:345`).
   - `place` in `s04_dettaglio_copie.tsv`: **10 copie** (`execution.py:1061` 449 righe, `live_order_worker.py:2931`, `scalper_bot.py:3118`, `sniper_bot.py:1222`, `tennis_scalper_bot.py:2739`,
     `condotta_ordini.py:619`, `submin.py:144, 195`, `tempi_ordine.py:184`, `laboratorio/scalper_lab/scalper_bot_base.py:1953`); `_place` **16 copie** (829 righe): 7 di produzione (tabella perimetro),
     5 del banco (`chiusura_parziale.py:461`, `minimi_banco.py:147, 219`, `sim_strategy.py:208`, `trasporto.py:308`), 4 del laboratorio. Le 7 di produzione non sono identiche (`s04`: 16 gruppi diversi, rapporto minimo 1,00), ma risolvono lo stesso problema:
     taglia legale, freno rifiuti, scrivere `customerOrderRef`, `market.place_order`, registrare l'esito. Il comune e' parzialmente in `condotta_ordini.py` (solo tennis): lo scalper calcio ha una definizione propria del minimo (2,00 EUR) diversa dall'1,00 delle altre strade (`07_porta_degli_ordini.schede.md` "Punti da decidere" 3).
   - Place-and-trim implementato come **macchina a stati dentro il runner** (`submin.py` 1.167, usata da motore e worker) e come **REST sincrono** (`omega_market.py:1043-1326`, 284 righe) che riusa il nucleo ma ricostruisce il giro; piu' `omega_market.py:1008` `piano_submin_live`.
   - Minimi/taglie: `live_order_build.min_stake_rules`, `minimi_it.py`, `execution._min_size_live:71`, `_porta_al_minimo_tennis:113`, `condotta_ordini.size_legale`, minimo scalper: cinque posti (`git grep -c` su `min_stake_rules|size_legale|IT_MIN_BACK|live_min_bet|_min_size_live|SCALPER_MIN`: 28 file di produzione).
   - Tre `porta_ordini.py` (1.245 righe): Omega e Mike importano `safe_strategy/porta_ordini` e lo ADATTANO (`omega/porta_ordini.py:7-20`: "spostarla in `Betfair/stream` voleva dire toccare Safe").
   - Tre riconciliatori nei bot (R4/R5/R6: ~1.300 righe) + R1/R2/R3/R7/R8/R9: nove nel complesso (par. 1.6).
3. **DB nel percorso dell'ordine** (par. 1.3): coda S2 (p50 492 / p95 2.481 / p99 26.636 ms paper, 202 letture/min della sola coda), riga di riserva prima dell'invio, esito riletto dallo specchio con latenza 2-20 s,
   tre shim (`_LocalSb`, `_SbDifferito`, `_CatenaDifferita`: `live_order_worker.py:3240-3450`, ~210 righe) solo per far scrivere al worker "sul DB" un ordine che nasce dal canale.
4. **Due tabelle specchio gemelle** (`betfair_live_orders` e `tennis_live_orders`) con due scrittori (`db.py:773`, `tennis_db.py:593`) e **9+3 lettori** della prima con query proprie (par. 1.4).
5. **Il ref non e' unico**: quattro schemi (`awlq<rid>`, `<bot>-t<id>`, `risk<id>`, quello di flumine) e `customerStrategyRef` che "mente per Safe" (`reconcile_worker.py:674`); il ref interno si perde al riavvio e serve una ricostruzione (R3).
6. **Il diario write-ahead non e' mai stato esercitato su ordini reali su questa macchina** (`07:184-185`): le garanzie di ripresa (R2) sono provate dai test, non dal campo.
7. **Reperti seri aperti sulla riconciliazione** (`CRONOSTORIA.md:4833`, non riverificati): Omega doppia chiusura sul ripiego > 20 s; Safe scrive i numeri dell'ordine vero sulla riga Over.
8. **`Betfair/client.py:329-426`: `place_orders` e letture senza chiamanti di produzione per `place_orders`** (98 righe, da confermare per le letture: `client.py:361, :395`).
9. **Nessuna Heartbeat API** (par. 4.6): se il processo cade, gli ordini LIMIT a riposo restano sul book (`02_COMPETITOR.md:310`, `risk_engine_worker.py:22`: "se il runner cade, stop/offset NON esistono").
10. **Documentazione che mente**: due `LIVE_ORDER_QUEUE_POLL_SEC` (1,0 e 2), `ESECUZIONE_LIVE.md` superato (par. 1.8).

---

## 4. Domani

### 4.1 Struttura nuova: UNA cartella `ordini/` con UN contratto

```
ordini/
  COSA_FA.md            funzionalita' C-001... una per una, con il test che la copre
  contratto.py          i tipi (sotto): RichiestaOrdine, Ack, EventoOrdine, StatoOrdine, PosizioneConto, Rifiuto
  porta.py              Protocol PortaOrdini + client WebSocket persistente (UNA, le 3 viste diventano 3 costanti)
  motore.py             state machine dell'ordine, dedup, seq, diario, sorveglianza, ripresa (da motore_ordini.py)
  controlli.py          kill-switch, modo, stake, esposizione, rate, freno rifiuti (flumine TradingControl)
  minimi.py             UNA definizione delle taglie .it (BACK/LAY, passo 0,50, 0,50 floor, equivalente, place-and-trim)
  esecutori/            betfair.py (flumine BetfairExecution)  paper.py (SimulatedExecution)  banco.py (finto del replay)
  riconciliazione.py    UN riconciliatore: diario + blotter + order stream vs conto -> StatoOrdine, PosizioneConto
  specchio.py           UN writer asincrono (betfair_live_orders + tennis) e UNA vista di lettura
  heartbeat.py          Heartbeat API (vedi par. 4.6, decisione)
  adattatori_sport/     calcio.py, tennis.py: solo cio' che e' davvero diverso (client, catalogo, positions)
  tests/                contratto: stessi test su Betfair/Paper/Banco
```

### 4.2 Contratto tipato (proposta)

```python
from dataclasses import dataclass
from typing import Literal, Optional, Protocol, Iterator

Modo = Literal["paper", "live"]
Azione = Literal["place", "cancel", "replace"]       # greenup/dutch/cashout = compositori sopra la porta
Persistenza = Literal["LAPSE", "PERSIST", "MARKET_ON_CLOSE"]
Fase = Literal["accettato", "parcheggiato", "ridotto", "parziale", "abbinato",
               "scaduto", "annullato", "rifiutato", "ignoto"]

@dataclass(frozen=True)
class RichiestaOrdine:
    ref: str                  # deterministico dalla riga del bot: "<attore>-t<id>", <= 32 caratteri
    attore: str               # "safe" | "safe_tennis" | "omega" | "mike" | "desktop" | "risk" | "scalper" | ...
    sport: Literal["calcio", "tennis"]
    modo: Modo                # quello della riga, mai quello del servizio
    azione: Azione
    market_id: str
    selection_id: int
    handicap: float = 0.0
    lato: Optional[Literal["back", "lay"]] = None
    prezzo: Optional[float] = None
    importo: Optional[float] = None
    persistenza: Persistenza = "LAPSE"
    time_in_force: Optional[Literal["FILL_OR_KILL"]] = None
    riduce_esposizione: bool = False       # verificata dal motore, mai creduta
    bet_id: Optional[str] = None           # cancel / replace
    riduzione: Optional[float] = None      # cancel parziale
    nuovo_prezzo: Optional[float] = None   # replace
    creato_ms: int = 0                     # intero: il rifiuto di float resta
    origine: Optional[dict] = None         # {"tabella": ..., "id": ...}

@dataclass(frozen=True)
class Ack:
    ref: str; accettato: bool; seq: Optional[int]; motivo: Optional[str]

@dataclass(frozen=True)
class EventoOrdine:
    ref: str; seq: int; fase: Fase; bet_id: Optional[str]
    abbinato: float; residuo: float; prezzo_medio: Optional[float]
    codice_errore: Optional[str]; esito_ms: Optional[int]
    punta_050: Optional[dict]; portata_al_minimo: Optional[dict]; tradotto: Optional[dict]

class PortaOrdini(Protocol):
    def invia(self, r: RichiestaOrdine) -> Ack: ...
    def eventi(self, attore: str, da_seq: int = 0) -> Iterator[EventoOrdine]: ...
    def stato(self, ref: str) -> Optional["StatoOrdine"]: ...        # dal diario/blotter, idempotente
    def posizione(self, market_id: str, selection_id: Optional[int] = None) -> "PosizioneConto": ...

class Esecutore(Protocol):                                          # dietro la porta
    def place(self, r: RichiestaOrdine) -> EventoOrdine: ...
    def cancel(self, r: RichiestaOrdine) -> EventoOrdine: ...
    def replace(self, r: RichiestaOrdine) -> EventoOrdine: ...
# implementazioni: EsecutoreBetfair (flumine live), EsecutorePaper (SimulatedExecution), EsecutoreBanco (replay)
```
I campi sono quelli che `valida_comando` (`motore_ordini.py:391-475`) e `CHIAVI_COMANDO` (`safe_strategy/porta_ordini.py`) accettano oggi, piu' le due estensioni (`time_in_force`, `riduce_esposizione`):
nessun campo nuovo di strategia. **Eventi consumati**: `order` (fase), `conto`; **esposti**: `ordine` (RichiestaOrdine accettata), `esito` (EventoOrdine), `posizione`.

### 4.3 Dove vive ogni funzionalita'

| Oggi | Domani |
|---|---|
| C-001..C-005, C-050, C-055 (motore, ack, seq, dedup, diario) | `ordini/motore.py` |
| C-006..C-010 (tre porte + viste) | `ordini/porta.py` (una classe `PortaCanale(attore)`; `VistaOmega/VistaMike` spariscono: l'attore e' un parametro) |
| C-011, C-012, C-013 (coda DB, gate, shim) | spariscono come strada di esecuzione (vedi D-C1); la coda DB resta solo come trasporto per il sito online |
| C-020..C-029 | `ordini/controlli.py` (flumine `TradingControl` + client control dove coincidono, par. 4.5) |
| C-030..C-037 | `ordini/minimi.py` (una sola definizione, usata da paper/live/tennis/scalper) |
| C-040..C-049 | `ordini/esecutori/` + compositori (greenup/dutch/hedging/risk restano come helper di strategia) |
| C-052, C-053, C-054 | eventi `esito` della porta (il bot non rilegge piu' il DB) + misura come middleware |
| R1..R9 | `ordini/riconciliazione.py` (un solo confronto); le **decisioni** dei bot su un ordine ignoto (grazia 20 s, ecc.) restano per bot come parametri, valori copiati identici |
| C-070..C-072 (tennis) | `adattatori_sport/tennis.py` con lo stesso motore (`esecutore_tennis.py` e' gia' il primo passo, spento di serie) |
| C-045..C-047 (REST diretti, terminale) | `esecutori/betfair.py`; REST di emergenza = stessa classe con trasporto REST (decisione D-C2); terminale vecchio = attore `desktop` sulla porta |

### 4.4 Stima delle righe DOPO (calcolo)

| Voce | Oggi | Dopo | Come |
|---|---|---|---|
| Contratto e tipi (nuovo) | 0 (disperso in `valida_comando` 85, `Ack` e `CHIAVI_COMANDO` in Safe) | 450 | tipi sopra + errori + `valida_comando` portato (85) |
| Porte lato bot | 1.245 | 740 | `PortaCanale` generica ~650 (la parte generica di Safe, 784, meno i punti di invio); 3 costanti di attore al posto di 3 viste (237+224 -> 3x30) |
| Esecutore nel runner (motore 2.434, modo 406, arresto 77, tempi 455) | 3.372 | 3.372 | e' logica: si sposta, non si riduce |
| `live_order_worker.py` | 3.997 | 3.346 | meno la parte "riga DB" che sparisce con la coda come strada di esecuzione: claim/audit 904-946 (43), journal/write 1021-1215 (195), persist submin 3139-3184 (46), shim 3240-3450 (210), `_process_once` 3788-3944 (157) = 651 |
| `live_order_build.py`, `trading/` (4.301), `risk_engine_worker` | 6.480 | 6.000 | `controls.py` 524 e parte di `freno_rifiuti` 124 coperti da `TradingControl`/client control di flumine: ~480 meno, solo se i test di contratto provano l'equivalenza (par. 4.5) |
| REST diretti `omega_market.py:610-1443` | 834 | 450 | un solo adattatore REST; `place_submin_live` 284 riusa `submin.py` (oggi ricostruisce il giro) |
| Letture del conto `omega_market.py:1445-1794` | 350 | 0 | spostate in `riconciliazione.py` |
| Terminale vecchio (`order_exec` 390, `order_worker` 165) | 555 | 0 | attore `desktop` sulla porta (D-C3) |
| Punti di invio nei bot (`execution`, `omega_service`, `mike/service`) | 1.222 | 360 | ognuno passa a `porta.invia(...)`; restano solo i dati di riga e la decisione (3 x ~120) |
| Resto di `reconcile_worker.py` (loop, avvio, cache) e `client_paper_affiancato.py` | 478 | 478 | invariati |
| Riconciliazioni | 1.094 + `reconcile_worker` ordini (~190) | 700 | un riconciliatore ~450 + tre politiche per bot ~80 ciascuna (10 ore di grazia, ecc., invariate) |
| `reconcile_worker.py` non-ordini (saldo/P&L ~740) + `esiti_ordini_canale` 850 | 1.590 | 740 | P&L/conto restano (altra scheda); `esiti_ordini_canale` assorbito dal flusso eventi |
| Tennis (worker 1.831 + esecutore 618 + guardie 487 + condotta 867) | 3.803 | 2.000 | 22 funzioni gemelle col calcio -> una; tennis tiene positions, catalogo, guardie paper/live |
| `_place` dei bot in-process (7) | 656 | 656 | restano (strategia), ma chiamano i controlli condivisi (D-C4) |
| `engine/live_trading_strategy.py` + specchio unico | 424 | 420 | un writer, una tabella con colonna `sport` (richiede migrazione SQL dell'utente: D-C5) |
| **Totale** | **26.290** (perimetro; somma delle righe sopra) | **~19.710** | **~-6.580 (-25 %)** |

Sono stime: il numero esatto dipende dalle decisioni D-C1..D-C5 (D-C1 da solo vale ~650, D-C5 poche decine di righe). Nessuna riga di strategia e' toccata: le righe in meno stanno nel trasporto, nelle copie, nei
riconciliatori ripetuti e nel codice che il DB imponeva nel percorso.

### 4.5 Cosa flumine gia' offre e noi riscriviamo (`.venv/Lib/site-packages/flumine`, v2.13.11)

| Nostro | Libreria |
|---|---|
| Esecuzione `market.place_order/cancel/replace`, simulazione, bet delay, parziali | `execution/betfairexecution.py:14` (`execute_place/cancel/update/replace` `:17, 64, 122, 157`), `execution/simulatedexecution.py:11`: gia' usate. Non riscritte. |
| Order stream reale e simulato | `streams/orderstream.py:18`: gia' usato (par. 1.9) |
| `_find_order_by_bet_id` (`live_order_worker.py:700`, tennis `:323`), `_find_order_by_cust_ref` (`:744`) | `markets/blotter.py:57` `get_order_bet_id`, `:308` `has_order(customer_order_ref)`, `:335` `__getitem__` |
| `_read_matched_exposures` (`:1684`, tennis `:855`), `esposizione_eur`, `_check_exposure_guard` (`:635`) | `blotter.py:188` `market_exposure`, `:224` `selection_exposure`, `:237` `get_exposures`; control `StrategyExposure` (`controls/tradingcontrols.py:218`) |
| `_max_orders_per_min` + `_rate_guard` (`:589, :624`) | `controls/clientcontrols.py:13` `MaxTransactionCount` (conteggio transazioni per ora; da leggere contro i limiti di `02_COMPETITOR.md`) |
| Validazione prezzo/taglia (`build_order`, `min_stake_rules`) | `controls/tradingcontrols.py:13` `OrderValidation` (`_validate_betfair_price :62`, `_validate_betfair_min_size :88`): le regole .it **non** coincidono con le sue (il tennis spegne `min_bet_validation`, `run_tennis_scalper.py:267`): il controllo si tiene come `TradingControl` nostro, non si butta |
| Stato mercato (`trading/stato_mercato.py`) | `MarketValidation` (`tradingcontrols.py:144`), `ExecutionValidation` (`:166`, controlla anche che l'order stream sia connesso `:174`) |
| `customer_strategy_ref` | `order/orderpackage.py:40` (campo del pacchetto) e `order/order.py:291` `customer_order_ref`; `is_valid_customer_order_ref_character` `order.py:224` |
| Middleware/worker periodici (reconcile, sorveglianza) | `worker.py` `BackgroundWorker`: gia' usato dal runner |
| Pulizia ordini chiusi/regolati | `blotter.py:143, 176` `process_closed_market`, `process_cleared_orders` |

Quello che flumine NON ha e resta nostro: place-and-trim sotto minimo .it, equivalente sull'altra selezione, diario write-ahead su disco, canale locale con `seq/da_seq`, specchio nel DB,
riconciliazione col conto del tipo "il conto vince" (flumine ricarica gli ordini dal conto all'avvio ma non produce lo specchio), Heartbeat API (nemmeno bfl, `betfairlightweight/endpoints/`
non ha un modulo heartbeat: elenco verificato: account, betting, historic, inplayservice, keepalive, login, logininteractive, logout, navigation, racecard, scores, streaming).

### 4.6 Heartbeat API (oggi non usata)

`HeartbeatAPING/v1.0/heartbeat(preferredTimeoutSeconds)`: se Betfair non riceve un battito entro il tempo, **tenta** di cancellare tutte le scommesse LIMIT del cliente su quell'exchange
(senza garanzia); endpoint dedicato per l'Italia `api.betfair.it/exchange/heartbeat/json-rpc/v1` (`02_COMPETITOR.md:207`). Oggi: nessun file lo chiama (`grep` di `HeartbeatAPING|exchange/heartbeat` = 0,
`02:310`; il "heartbeat" del codice e' quello dello stream di mercato e la tabella `betfair_live_heartbeat`, cose diverse).
Il rischio che chiude: processo morto con ordini appoggiati (lay appoggiata di Mike `LAPSE`, uscite a riposo, offset del risk engine) che restano vivi sul book senza nessuno che li gestisca
(`risk_engine_worker.py:22`). Il rischio che apre: **e' per conto, non per processo**; il conto e' uno solo con piu' processi e con gli ordini manuali dell'utente dal sito
(`reconcile_worker.py:30-32`): se UN processo smette di battere, Betfair puo' cancellare anche gli ordini degli altri. Per questo il battito deve avere UN proprietario (la porta) che batte
finche' almeno un componente e' vivo, ed e' comunque una **decisione per l'utente** (cambia il comportamento degli ordini a riposo e delle posizioni "in attesa"): D-C6.

### 4.7 Confronto "per sostituire questo componente"

- **OGGI**: per cambiare il modo in cui un ordine arriva a Betfair tocco `motore_ordini.py`, `live_order_worker.py`, `tennis_live_order_worker.py`, `esecutore_tennis.py`,
  `omega_market.py`, `order_exec.py`, tre `porta_ordini.py`, tre punti di invio (`execution.py`, `omega_service.py`, `mike/service.py`), 7 `_place` di bot, `scalper_session.py`,
  `reconcile_worker.py` e tre riconciliatori: **almeno 24 file Python** e 3 lati del frontend per i lettori dello specchio.
- **DOMANI**: tocco solo `ordini/` (un esecutore o un trasporto) e i suoi test di contratto (gli stessi su `EsecutoreBetfair`, `EsecutorePaper`, `EsecutoreBanco`).

---

## 5. Parita'

Che cosa deve restare identico numero per numero (stessa partita, stessi scenari -> stesso esito):
ordini piazzati (lato, prezzo, importo, persistenza, FOK), importi dopo minimi/punta 0,50, istanti per `ref`, `bet_id` simulato, abbinati/parziali, esito di ogni `ref`, P&L; fasi ed eventi `order` per `seq`.

- **Banco comune** (`python -m Betfair.stream.backtest.certifica <bot> ...`; `Betfair/stream/backtest/`): registrazioni `registrazioni_banco/` e `_live_raw/` (le stesse dei referti del 04/10 in
  `AUDIT_2026-10-04/replay/coord_safe_omega/`: `safe_base 35760084 rapidi entrambi` OK 62 s, `omega 35760084` 44 s, `safe_tennis 35795993` 12 s, `safe_base tutti` 22/22, `omega tutti` 20/20; tempi dichiarati
  dalla cronostoria, non rilanciati da me). Il referto di oggi si confronta con quello del 04/10 riga per riga.
- **Parita' coda/canale/REST**: oggi il banco prova "PARITA' coda/canale RAGGIUNTA" (`CRONOSTORIA.md:4964`); il test di migrazione (par. 6) estende la parita' a `EsecutoreBetfair` vs `EsecutorePaper` vs `EsecutoreBanco`
  sullo stesso `RichiestaOrdine`.
- **Test di contratto** (nuovi): (1) una `RichiestaOrdine` -> la stessa sequenza di `EventoOrdine` (fasi, `seq`) su Paper e Banco; (2) il finto di Betfair con chiavi e tipi del vero (`banco_comune.py:1024-1028`);
  (3) dedup per ref dopo riavvio; (4) riconciliazione: scenari "esito ignoto", "ordine esterno dal sito", "ordine sul conto non nello specchio", "specchio senza conto", "riavvio con ordine in volo" (R2).
- **Falsificazione obbligatoria**: ogni test nuovo va reso rosso a mano (togliere dedup, togliere `da_seq`, far restituire `ok` all'esito ignoto, ritentare in `call_mutating`).
- **Voci di `PROCESSO_STANDARD_BOT.md` coperte**: par. 6 (ciclo di vita dell'ordine con parziali e bet delay; persistenza e UI; concorrenza; scenari; falsificazione; referto riproducibile);
  par. 7 catalogo: errori su ref/identificativi scritti in un modo e letti in un altro (storia 15/09 in `mike/service.py:2229-2247`), rifiuto non ritentato identico, doppio ordine dopo riavvio, paper!=live,
  costante duplicata (n. 33, citato in `condotta_ordini.py:5-8`). **Non ho riletto par. 6/par. 7 per numero**: il coordinatore deve riportare i numeri esatti (vedi ultima sezione).
- **UI**: fotografie delle pagine ordini (`posizioniCanale.pannelli.test.tsx`, Control Room) e dei pannelli che leggono lo specchio (3 file del frontend, par. 1.4): invariate con la stessa riga `betfair_live_orders`.

---

## 6. Migrazione (nel guscio, nessun taglio senza ombra)

1. **Prima il contratto**: `ordini/contratto.py` con i tipi e un adattatore da/verso `valida_comando` (nessun cambio di comportamento); i tre `porta_ordini.py` ereditano da `PortaCanale` generica
   (aggiungere, non togliere: i test di Safe sostituiscono variabili di modulo, `omega/porta_ordini.py:7-12`).
2. **Ombra del riconciliatore**: `riconciliazione.py` gira accanto a R4/R5/R6 SENZA scrivere; confronto automatico per `ref` e per `StatoOrdine`; ogni divergenza e' un reperto (si parte dai due gia' scritti, par. 3.7).
   Tagliare R4/R5/R6 solo quando il confronto e' vuoto su almeno N giornate con ordini reali (oggi la base reale e' quasi nulla: 4 ordini live del runner, `07:172-173`).
3. **Mike live sul motore** (S3 -> S1): e' il passo piu' delicato (cambia la strada degli ordini reali di un bot; stessa strategia, stesso ordine, stessa persistenza: `ESECUZIONE_LIVE.md:57-62`)
   e richiede: replay certificato di Mike con ordini appoggiati sul motore, paper -> live come ordina il processo. **Prima di toccare `paper`/`live` si ricorda all'utente se il bot e' certificato sul replay.**
4. **Interruttori**: portare `SAFE_ORDINI_VIA_CANALE`, `SAFE_TENNIS_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`, `MOTORE_ORDINI_CANALE_TENNIS`, `ESITI_ORDINI_CANALE` da "spenti di serie" ad acceso, UNO alla volta,
   solo dall'utente, con replay verde e un periodo paper di prova; il vecchio resta spento ma presente.
5. **Tennis**: un solo motore con l'esecutore tennis (`esecutore_tennis.py`): le 22 funzioni gemelle si fondono dietro i test di contratto.
6. **Specchio unico** (D-C5, migrazione SQL che applica l'utente) e **tolta la coda DB come strada di esecuzione** (D-C1) per ultimi.
7. **Heartbeat** per ultimo e solo se D-C6 lo approva: prima in modo "ombra" (lo si invia ma con un timeout molto lungo), poi il valore vero.
- **Rischi**: Mike live sul motore (un bug = ordini reali sbagliati), doppio ordine in finestra di passaggio (due strade attive sullo stesso `ref`: il dedup per ref e' la protezione, va falsificato),
  rifacimento dei lettori dello specchio (9 file + 3 frontend).
- **Ritorno indietro**: ogni passo e' un interruttore; il codice vecchio resta fino a un periodo di ombra senza divergenze; nessuna cancellazione prima.
- **Ordine rispetto agli altri componenti**: dopo A (sessione e order stream: la porta usa la sua sessione), prima di I (risk/stop, che accodano ordini) e dei bot (D/E/B), che passano a `porta.invia`.

---

## 7. Misure

| Misura | Oggi (fonte) | Obiettivo dopo |
|---|---|---|
| `place` decisione -> abbinato/ack, strada coda DB | p50 492, p95 2.481, p99 26.636, max 36.524 ms (n=38, paper; `07:159`) | p50 sotto 150 ms sul canale, **da misurare** (strumento: 30 ordini in paper con `LIVE_TEMPI_ORDINE=1` e `python -m Betfair.stream.tools.leggi_tempi_ordine <log>`) |
| `cancel` / `replace` (coda DB) | p50 406 / 307 ms (n=8 / 3; `07:161-165`) | idem, dal canale |
| `placeOrders` -> risposta Betfair, live | non misurabile oggi (`07:172-173, :387-388`) | misura con ordini reali minimi (decisione dell'utente) |
| Esito -> bot | fino a 20 s Omega, 2 s Safe (`esiti_ordini_canale.py:1-12`) | evento del canale, ms |
| Richieste DB al minuto dalla sola coda ordini | 202,3 GET/min (`07:224`), + risk_rules 164,7 e settings 119,9 | 0 sul percorso dell'ordine (settings/risk_rules restano scheda H/I) |
| Strade verso Betfair | 7 (par. 1.1) | 1 porta (+ REST di emergenza dietro lo stesso contratto) |
| Riconciliazioni | 9 | 1 + 3 politiche per bot |
| Funzioni gemelle LOW/tennis | 22 (`comm -12`) | 0 |
| Siti `market.place_order` | 12 | 12 (strategia), dietro controlli comuni |
| Righe | 26.290 | ~19.710 (stima par. 4.4) |
| Memoria/CPU della porta | n.d. | strumento: profilo del runner calcio con 20 ordini/min simulati (non esiste) |

---

## Decisioni per l'utente

- **D-C1** La coda DB `betfair_live_order_requests` come strada di esecuzione: tenerla (serve al sito online, che raggiunge il PC solo via DB: `liveOrders.ts:122-125`) o ridurla a trasporto
  del solo sito, con il canale come unica strada dal PC? Valore ~650 righe + 202 letture/min.
- **D-C2** REST di emergenza per Safe/Omega live quando il runner e' giu' (`execution.py:1382`): tenerlo (come ripiego dichiarato) o fermarsi come in paper ("paper_senza_runner")? Oggi il live
  si comporta diversamente dal paper qui (condizione 2 dell'utente).
- **D-C3** Terminale vecchio `order_exec` + coda `betfair_order_requests` (pannello "multi trade" della watchlist): ancora usato? (`07_porta_degli_ordini.schede.md` "punti non chiariti" 2.)
  Se no, eliminare 555 righe; se si, farlo passare dalla porta con attore `desktop`.
- **D-C4** Scalper e tennis: restare nel loro flumine con controlli comuni (proposta, meno rischio) o far passare anche loro dalla porta (piu' parita', piu' latenza e lavoro)?
- **D-C5** Specchio unico (`betfair_live_orders` + `tennis_live_orders` con colonna `sport`): richiede migrazione SQL che applica l'utente.
- **D-C6** Heartbeat API: abilitarla (preferredTimeoutSeconds da decidere) sapendo che cancella gli ordini LIMIT del conto, anche di altri processi e dal sito, se il battito manca? Il valore del timeout non e' una soglia di strategia ma cambia la vita degli ordini a riposo.
- **D-C7** Mike live sul motore: e' il vero obiettivo di `ESECUZIONE_LIVE.md`; si fa dopo la certificazione sul replay (condizione dell'utente), quando lo ordina lui.

## Cosa ho verificato di persona / cosa non ho potuto verificare

Verificato di persona (comandi letti e righe lette): conteggi `wc -l` dei file del perimetro; elenco dei siti `place_order(`/`place_orders(`/`cancelOrders`/`replaceOrders` con `git grep`; indici di funzioni di
`motore_ordini.py`, `live_order_worker.py`, `tennis_live_order_worker.py`, `omega_market.py`, `execution.py`, `reconcile_worker.py`; testa dei tre `porta_ordini.py`, di `order_exec.py`, `order_worker.py`,
`condotta_ordini.py`, `esiti_ordini_canale.py`, `risk_engine_worker.py`, `live_order_build.py`; `place_order_live` (`omega_market.py:704-830`), `call_mutating` (`:89-112`); percorso di scelta in `execution.place`
(`:1219-1400`); `riprendi_da_diario` (`motore_ordini.py:2354-2434`); `_dispatch` (`live_order_worker.py:3679-3717`); flumine: elenco di `controls/`, `execution/`, `order/`, `streams/orderstream.py`, `markets/blotter.py`;
assenza di un modulo heartbeat in bfl e di `HeartbeatAPING` nel codice; 22 nomi in comune LOW/tennis (`comm -12`); conteggi di `s04` (`_place` 16, `place` 10).

NON verificato:
1. Il valore reale degli interruttori `*_ORDINI_VIA_CANALE`, `MOTORE_ORDINI_CANALE_TENNIS`, `ESITI_ORDINI_CANALE` nel `.env` e nell'avvio dell'app: nel codice sono "spenti di serie"; `desktop/` non li imposta
   (`git grep` in `desktop/` = 0), ma non ho letto `.env` (regola del brief). Perimetro delle strade effettivamente attive su questa macchina: da confermare.
2. Righe esatte di `live_order_build.py` (`build_order`, `min_stake_rules`) e dei campi di `CHIAVI_COMANDO`: citate per file, non per riga.
3. Tutte le righe dei reperti di `CRONOSTORIA.md:4833` (Omega doppia chiusura, Safe riga Over): riportati dalla cronostoria, NON riverificati nel codice di oggi.
4. `desktop/main.js:233` (0,15 s) e `start_order_server.py:24`: citati da `INVENTARIO_COMPONENTI_2026-09-25.md` e `SCHEMI_BOT/.../INVENTARIO_ARCHITETTURA.md`, non riaperti.
5. I numeri di `PROCESSO_STANDARD_BOT.md` par. 6/par. 7: non riletti (nessun accesso nel budget di chiamate); la sezione Parita' li cita per contenuto, il coordinatore deve metterci i numeri.
6. Chi chiama le letture di `Betfair/client.py:361-426` (`list_current_orders`, `list_cleared_orders`): solo `place_orders` risulta senza chiamanti.
7. Le tempistiche live di Betfair (`placeOrders`): non misurabili con i dati esistenti (`07:172-173`).
8. Le stime di righe dopo (par. 4.4): sono calcoli sulle righe elencate, non un progetto scritto; le percentuali sono indicative.
