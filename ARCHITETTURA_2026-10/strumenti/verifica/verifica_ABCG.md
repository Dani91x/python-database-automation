# Verifica indipendente delle schede A, B, C, G (08/10/2026)

Metodo: per ogni scheda, campione di 25 citazioni (`estrai_campione.py <scheda> 25`, seme fisso); percorsi abbreviati risolti con `git ls-files`
(flumine: `.venv/Lib/site-packages/flumine/...`); lette le righe citate; dove la citazione stava in una frase con altre citazioni, ho letto anche
quelle adiacenti (elencate come «extra»). Solo lettura del codice; unica scrittura: correzioni alle schede e questo referto.

Esiti sul campione di 25:

| Scheda | CONFERMATE | SPOSTATE | FALSE |
|---|---|---|---|
| A_CONNESSIONE_BETFAIR | 23 | 2 | 0 |
| B_PUNTEGGI_STATO_PARTITA | 24 | 1 (+1 extra) | 0 |
| C_PORTA_ORDINI | 24 | 1 | 0 |
| G_DATI_E_ALGORITMI_DEL_CLOUD | 23 | 0 | 2 |

## Scheda A

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 288 | runner.py:2210-2228 | Betfair/stream/runner.py | CONFERMATA | `build_paper_companion_client`; `client_paper_affiancato.py` ha 53 righe, docstring a :1-10 |
| 216 | recorder.py:189-207 | Betfair/stream/recorder.py | CONFERMATA | `process_market_book` senza rete; `tennis_runner.py:428-431` idem |
| 351 | scan_feed.py:35-476 | Betfair/stream/scores/scan_feed.py | CONFERMATA | costanti da :35, cache/righe fino a :476; TTL 1 s (:69), freschezza 15 s (:43) e 180 s (:63) |
| 175 | tennis_runner.py:2488-2750 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `_allinea_follow_a_caldo` (:2488) ... "armati A CALDO" (:2745-2748); `safe_strategy/stream.py:229-309` throttle 30 s (:54) e tolleranza 25 (:64) confermati |
| 276 | odds_refresh.py:3-5 | Betfair/odds_refresh.py | CONFERMATA | docstring del pulsante "Aggiorna quote"; `refresh_fixture_odds` a :206 dentro 105-263 |
| 213 | frammenti_mercato.py:88 | Betfair/stream/frammenti_mercato.py | CONFERMATA | `DEFAULT_MAX_CONNESSIONI = 3`; docstring :1-9 con 179/180 e 24 partite |
| 75 | runner.py:2858-2867 | Betfair/stream/runner.py | CONFERMATA | `MarketRecorderStrategy(... stream_class=_FR.FrammentoMarketStream)`; `frammenti_mercato.py:90` riserva = 1 |
| 325 | esiti_ordini_canale.py:1-850 | Betfair/stream/esiti_ordini_canale.py | CONFERMATA | file di 850 righe; docstring: canale 47331, Omega 20 s, Safe 2 s |
| 384 | runner.py:2123 | Betfair/stream/runner.py | CONFERMATA | `def build_order_client` (e `tennis_runner.py:144`) |
| 303 | frammenti_mercato.py:293-310 | Betfair/stream/frammenti_mercato.py | CONFERMATA | `mercati_con_ordini` (blotter); `runner.py:2384-2422` `_mercati_con_soldi_dallo_specchio` |
| 403 | stream_muto.py:35-45 | Betfair/stream/stream_muto.py | SPOSTATA | l'affermazione «heartbeatMs non richiesto su 3 dei 4 stack (decide Betfair)» sta a :20-31; a :35-45 c'e' la soglia di stallo. CORRETTA la scheda. Gli altri parametri di D8 (`tennis_runner.py:116,119,103`, `config_stream.py:90,47`) confermati; `TENNIS_STREAM_CONFLATE_MS` ha davvero la sola definizione (:116) |
| 294 | frammenti_mercato.py:293-310,577-627 | Betfair/stream/frammenti_mercato.py | CONFERMATA | `MUTO_S = 180.0` (:97); `_vivo` (:577) e `persi` (:625) |
| 377 | tennis_runner.py:260 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `ladder_signature`; `runner.py:643` idem |
| 168 | flumine/streams/marketstream.py:12 | .venv/.../flumine/streams/marketstream.py | SPOSTATA | :12 e' riga vuota; `RETRY_WAIT` a :11, `@retry(wait=RETRY_WAIT)` a :15; `initial_clk`/`clk` a :40-41 (36-42 confermato); `basestream.py:14` `wait_exponential(2..60)` confermato. CORRETTA (:15) |
| 213 | sottoscrizione_a_caldo.py:40 | Betfair/stream/sottoscrizione_a_caldo.py | CONFERMATA | `LIMITE_BETFAIR_MERCATI = 200` |
| 300 | runner.py:1583-1767 | Betfair/stream/runner.py | CONFERMATA | `heartbeat_worker` (:1583) fino a prima di `arresto_worker` (:1768); custode :1433-1460 |
| 478 | iscrizione_a_caldo.py:65 | Betfair/stream/tennis_live/iscrizione_a_caldo.py | CONFERMATA | `TETTO_DEFAULT = 180`; `config_stream.py:164` `HARD_MARKET_CAP` 180 |
| 178 | stream_muto.py:35-45 | Betfair/stream/stream_muto.py | CONFERMATA | :33-36 «3 volte QUEL valore; altrove 3 volte 5000 ms» |
| 275 | odds_refresh.py:48-102 | Betfair/odds_refresh.py | CONFERMATA | `BetfairLimitHit` (:48), `_get_client` (:60), `reset_shared_client` (:100) |
| 160 | omega_service.py:8587 | Betfair/omega/omega_service.py | CONFERMATA | `_PORTA_CANALE = 47334`; `bot_service.py:10569` = 47335; `safe_strategy/service.py:91` = 47336 |
| 413 | RigaOrdiniReali.tsx:21 | frontend/src/components/controlroom/RigaOrdiniReali.tsx | CONFERMATA | commento sul canale 47331; `RigaFreno.tsx:13` e `useControlRoom.ts:7,151` idem (porte 47333-5, 47338) |
| 75 | frammenti_mercato.py:88 | idem | CONFERMATA | vedi sopra |
| 503 | runner.py:136-171 | Betfair/stream/runner.py | CONFERMATA | `fetch_event_markets` (:136-168) |
| 377 | runner.py:643 | Betfair/stream/runner.py | CONFERMATA | `ladder_signature` |
| 338 | tennis_runner.py:1580-1610 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `_STREAM_KEEPALIVE_SEC` (:1580), `_maybe_keepalive` (:1583), relogin custode (:1606) |

Conteggio A: 23 CONFERMATE / 2 SPOSTATE / 0 FALSE.

## Scheda B

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 253 | runner.py:376 | Betfair/stream/runner.py | CONFERMATA | `db.update_live_now(...)` incondizionato (dentro `if snap is not None`); `service.py:2686` (safe_strategy) conferma il write-on-change dello scanner |
| 173 | runner.py:344-413 | Betfair/stream/runner.py | CONFERMATA | `score_worker` da :344 |
| 177 | uploader.py:120-160 | Betfair/stream/uploader.py | CONFERMATA | upload idempotente per evento; `stream/db.py:629-635` `upload_timeline` e snapshots |
| 404 | runner.py:457 | Betfair/stream/runner.py | CONFERMATA | `_signals_write_due(... keepalive_sec)` |
| 377 | atlante_v4.py:550 | Betfair/stream/scalper/atlante_v4.py | CONFERMATA | `tempo_da_stato_ips` |
| 217 | feed.py:148 | Betfair/mike/feed.py | CONFERMATA | `flusso_esito`; `exits.py:401` `flusso_esito`; `omega_service.py:959-1010` `_flusso_della_riga`; `flusso_prezzi.py:218` `valuta` |
| 94 | scan_feed.py:296-309 | Betfair/stream/scores/scan_feed.py | CONFERMATA | `rows_for`: `_wanted`, `_pending`, TTL |
| 164 | scan_feed.py:478-540 | Betfair/stream/scores/scan_feed.py | CONFERMATA | `class ScanFeedScoreProvider` (:478) ... `healthcheck` (:539) |
| 200 | riserva_prezzi.py:148-155 | Betfair/stream/riserva_prezzi.py | CONFERMATA | `shared_cache()` + esito "nessuna riserva" |
| 98 | api_client.py:33-50 | api_client.py (radice) | CONFERMATA | `call(... max_retries)` con retry, backoff, 429, `api_call_log` |
| 139 | tennis_opportunity.py:45 | Betfair/safe_strategy/tennis_opportunity.py | CONFERMATA | import `tennis_scalper.tennis_score`; `safe_strategy/service.py:64` e `tennis_runner.py:77` idem |
| 151 | base.py:45-57 | Betfair/stream/scores/base.py | CONFERMATA | `ScoreProvider(Protocol)` |
| 57 | tennis_runner.py:111 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `SCORE_POLL_SEC` 2.0; `:3355` `interval=SCORE_POLL_SEC` |
| 157 | api_football.py:57-89 | Betfair/stream/scores/api_football.py | CONFERMATA | `ApiFootballProvider` ... `healthcheck` (:88) |
| 185 | flusso_prezzi.py:84-240 | Betfair/stream/flusso_prezzi.py | CONFERMATA | `SOGLIA_INPLAY_S` calcio 45 / tennis 25 (:92), `SOGLIA_PRE_S` 125 (:93), `SOCKET_MAX_S` 15 (:96), `_TESTI` :98-107 |
| 89 | scan_feed.py:430-437 | Betfair/stream/scores/scan_feed.py | CONFERMATA | `shared_cache()` singleton |
| 118 | poller.py:30 | Betfair/stream/scores/poller.py | CONFERMATA | `retry_primary_sec` 120 (:30), half-open (:85) |
| 11 | mike/feed.py:76-176 | Betfair/mike/feed.py | CONFERMATA | e `:425-475` `feed_fresh`/`order_fresh`; `exits.py:401-455`; `bot_service.py:8502-8514` `_row_is_fresh` |
| 362 | betfair_inplay.py:164 | Betfair/stream/scores/betfair_inplay.py | CONFERMATA | `get_scores` (:164), `get_event_timeline` (:187); `safe_strategy/service.py:1731,1846` idem |
| 248 | sniper_bot.py:295-310 | Betfair/stream/scalper/sniper_bot.py | CONFERMATA | cache per market_id; `media_under_bot.py:1020-1032` un solo valore; `scalper_bot.py:788-818` vs `tennis_scalper_bot.py:802-832`: `diff` vuoto, identiche (nota: il blocco include le prime 3 righe della def successiva) |
| 231 | exits.py:431-440 | Betfair/safe_strategy/exits.py | CONFERMATA | docstring `feed_is_fresh`, soglie diverse di proposito; `mike/feed.py:458-478` `order_fresh` |
| 347 | omega_service.py:62-81 | Betfair/omega/omega_service.py | CONFERMATA | `_is_fresh` (:62-72) + intestazione FEED UNICO (:75-81) |
| 139 | tennis_runner.py:77 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `from ..tennis_scalper.tennis_score import (` |
| 262 | scan_feed.py:5-7 | Betfair/stream/scores/scan_feed.py | SPOSTATA | «chunk da 20, ogni 3s» e' a :3-5. CORRETTA. `service.py:132` (2.0 s), `:175` (chunk 50), `:123-131` confermati |
| 32 | scan_feed.py:64-67 | Betfair/stream/scores/scan_feed.py | CONFERMATA | `IPS_SCORE_LAG_SEC`; `scan_feed.py:69` TTL 1 s; `service.py:159` 2,5 s; `config_stream.py:32` 5 s; `scalper_session.py:1746` sleep 20 e `:1923` sleep 15; `tennis_runner.py:111` |

Extra (fuori campione ma sulla stessa riga): `tennis_runner.py:1688` (righe 35, 69, 101, 253 di B) -> SPOSTATA di 3 righe: :1688 e' il `continue` dopo l'except,
la chiamata `upsert_tennis_now` e' a :1685. CORRETTE tutte e 4 le occorrenze.

Conteggio B: 24 CONFERMATE / 1 SPOSTATA (+1 extra spostata, 4 occorrenze) / 0 FALSE.

## Scheda C

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 509 | execution.py:1382 | Betfair/safe_strategy/execution.py | SPOSTATA | :1382 e' solo la variante «equivalente» del sotto-minimo (`tradotto_rest`); il percorso legacy/REST e' dichiarato a :1299-1301 e le chiamate REST sono a :1382, :1389 (`place_submin_live`), :1394 (`place_order_live`); `paper_senza_runner` a :1334 confermato. CORRETTA. La sostanza di D-C2 (live va a Betfair, paper no) e' confermata |
| 457 | banco_comune.py:1024-1028 | Betfair/stream/backtest/banco_comune.py | CONFERMATA | `list_current_orders`/`list_cleared_orders` del finto, righe `_riga` |
| 192 | localTransport.ts:441 | frontend/src/lib/localTransport.ts | CONFERMATA | percorso `dbApi.send` quando il canale non e' collegato; `motore_ordini.py:2264` `_servi_order` confermato |
| 270 | tennis_scalper_bot.py:2739 | Betfair/stream/tennis_scalper/tennis_scalper_bot.py | CONFERMATA | `def place`; anche `execution.py:1061`, `live_order_worker.py:2931`, `scalper_bot.py:3118` |
| 106 | reconcile_worker.py:29 | Betfair/stream/reconcile_worker.py | CONFERMATA | docstring (specchio `betfair_live_orders`); `:472` select sulla tabella; `stream/db.py:447,474` select ordini |
| 218 | live_order_worker.py:3008-3180 | Betfair/stream/live_order_worker.py | CONFERMATA | `_start_submin`/`_advance_submin_row`/`_persist_submin_step`; `submin.py:144,195` `place`; `motore_ordini.py:1678-1890`; `omega_market.py:858` "nucleo unico" |
| 272 | chiusura_parziale.py:461 | Betfair/stream/backtest/chiusura_parziale.py | CONFERMATA | `def _place`; `trasporto.py:308` idem |
| 48 | order_exec.py:215 | Betfair/order_exec.py | CONFERMATA | `place_order`; `:340` `c.place_orders`, `:342` `customer_strategy_ref="watchlist"` |
| 136 | omega_service.py:8044 | Betfair/omega/omega_service.py | CONFERMATA | `reconcile_pending(...)`; `:8131` idem; `:4337` def; `:4108` `poll_flumine_pending` |
| 211 | live_order_worker.py:529 | Betfair/stream/live_order_worker.py | CONFERMATA | `_pubblica_modo_ordini_se_cambiato` |
| 49 | tennis_pro_bot.py:533 | Betfair/stream/tennis_scalper/tennis_pro_bot.py | CONFERMATA | `market.place_order(order)`; `scalper_session.py:798-802` (`order_stream`, `paper_trade`); `run_tennis_scalper.py:266-271` |
| 115 | omega_config.py:19 | Betfair/omega/omega_config.py | CONFERMATA | `CUSTOMER_STRATEGY_REF = "omega"` |
| 413 | betfairexecution.py:14 | .venv/.../flumine/execution/betfairexecution.py | CONFERMATA | `execute_place/cancel/update/replace` a :17, 64, 122, 157; `simulatedexecution.py:11` |
| 102 | db.py:907 | Betfair/stream/db.py | CONFERMATA | select `betfair_live_orders` per ref; `:1139` delete mode paper; `reconcile_worker.py:472` |
| 240 | live_order_worker.py:1271 | Betfair/stream/live_order_worker.py | CONFERMATA | `_TEMPI.place(order)` |
| 48 | odds_http.py:185 | Betfair/stream/odds_http.py | CONFERMATA | import `place_order`; `order_worker.py:73` idem |
| 225 | live_order_worker.py:1240-1312 | Betfair/stream/live_order_worker.py | CONFERMATA | `_place_or_raise` (:1240), `_cancel_or_raise` (:1282), `size_reduction` (:1284) |
| 163 | run_tennis_scalper.py:9 | Betfair/stream/tennis_scalper/run_tennis_scalper.py | CONFERMATA | `--paper (DEFAULT)`; `:264-272` client live/paper |
| 272 | trasporto.py:308 | Betfair/stream/backtest/trasporto.py | CONFERMATA | `def _place` |
| 171 | scalper_session.py:800 | Betfair/stream/scalper/scalper_session.py | CONFERMATA | `"order_stream": True`; `run_tennis_scalper.py:266-267` |
| 102 | db.py:1139 | Betfair/stream/db.py | CONFERMATA | `delete().eq("mode","paper")` |
| 152 | motore_ordini.py:2404 | Betfair/stream/motore_ordini.py | CONFERMATA | `"perso_paper"` |
| 178 | order_worker.py:26 | Betfair/order_worker.py | CONFERMATA | `LIVE_ORDER_QUEUE_POLL_SEC` default "2"; `config_stream.py:229` default "1.0": i due default esistono |
| 494 | esiti_ordini_canale.py:1-12 | Betfair/stream/esiti_ordini_canale.py | CONFERMATA | «fino a 20 s Omega, 2 s Safe» |
| 57 | omega_market.py:951 | Betfair/omega/omega_market.py | CONFERMATA | `cancelOrders`; `:1252` `replaceOrders`; `:1375` `cancelOrders`; `scalper_session.py:532,540` `cancel_orders` |

Conteggio C: 24 CONFERMATE / 1 SPOSTATA / 0 FALSE.

## Scheda G

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 190 | mike/dossier.py:138-171 | Betfair/mike/dossier.py | CONFERMATA | `_EMPIRICAL_RETRY_S = 600` (:138), cache senza scadenza (:147-148), errore/vuota -> riprova (:150-165); `mike/db.py:637`, `omega_db.py:1055`, `omega_service.py:106` (6 h) confermati |
| 102 | scalper_session.py:962 | Betfair/stream/scalper/scalper_session.py | FALSA | :962 e' una SELECT su `MU.TABELLA_ORDINI_CONTO` (betfair_live_orders), non tocca `scalper_control`/`scalper_service_control`/`scalper_activity`; le scritture di `scalper_activity` sono a :1270 e :1281 (confermate); in `scalper_session.py` `scalper_control` compare solo in commenti. CORRETTA (tolto :962 dalla riga T12; resta valido nella riga 109 «nomi dinamici») |
| 391 | live_order_worker.py:498 | Betfair/stream/live_order_worker.py | CONFERMATA (posizione) + NOTA | :498 e' `sb.rpc("get_live_settings")`. Il comportamento in errore, che la scheda dichiara non letto, e' questo: `except Exception: pass` (:508-509); `_SETTINGS` (:479, inizio `{}`) resta l'ultimo valore letto; `_db_kill_switch()` (:581-582) legge `_SETTINGS.get("kill_switch")`. Quindi «ultimo valore noto in memoria» esiste GIA' (silenzioso) e al primo giro fallito il kill switch risulta spento. NOTA aggiunta alla scheda |
| 402 | bot_db.py:1029 | Betfair/safe_strategy/bot_db.py | FALSA | la scheda dice che `mike/db.py:683`, `omega_db.py:674`, `bot_db.py:1029` sono `enqueue_live_order: confermati`. Sono in `revoke_live_order_request` (UPDATE `status='error'`, `error='revocata ...'` su `betfair_live_order_requests`). `enqueue_live_order` sta a `mike/db.py:662`, `omega_db.py:634`, `bot_db.py:1003`. Stessa tabella, funzione sbagliata. CORRETTA. Nella riga T01 (91) gli stessi numeri come scrittori della tabella restano validi |
| 97 | safeBot.ts:2195 | frontend/src/lib/safeBot.ts | CONFERMATA | `.from('live_follow')`; `mike/db.py:651`, `omega_db.py:618`, `bot_db.py:989`, `stream/db.py:164`, `auto_follow.py:402`, `watchlist.py:29` confermati; `config_stream.py:129` `WATCHLIST_POLL_SEC` 120 |
| 264 | betfair_live_order_queue.sql:35 | migrations/betfair_live_order_queue.sql | CONFERMATA | `client_ref ... UNIQUE`; `live_stream.sql:85` UNIQUE (event_id, market_id); `live_ladder.sql:56` indice unico |
| 307 | stream/db.py:231-262 | Betfair/stream/db.py | CONFERMATA | `get_fixture_prematch_lambdas`; `omega_db.py:756` `fixture_analysis` |
| 191 | omega_service.py:1397 | Betfair/omega/omega_service.py | CONFERMATA | `_model_select`; `_minute_table` (:1432, :1556), `_empirical_table` (:1444, :1565), `_v3_p_empirica` (:1543); cache 2000/500 chiavi, TTL `EMPIRICAL_CACHE_TTL_S` 6 h; `omega_empirical.py:168-176` bucket 5, max 85/40 |
| 92 | mike/db.py:233 | Betfair/mike/db.py | CONFERMATA | select `betfair_live_orders`; `:691`, `omega_db.py:687`, `bot_db.py:1040`; `stream/db.py:773-835` `upsert_live_order`, `on_conflict="mode,client_order_ref"` a :820 e :829 |
| 215 | omega_service.py:1340 | Betfair/omega/omega_service.py | CONFERMATA | `mike/db.py:637-647` torna `[]` in errore; `omega_db.py:1055-1065` torna `None`; Omega non mette in cache l'errore (:1339-1340 minute, :1364-1368 empirical) |
| 194 | frontend/src/lib/analytics.ts:81-346 | frontend/src/lib/analytics.ts | CONFERMATA | RPC `get_analytics_filters` (:81) ... `delete_strategy` (:346); `build_analytics_signals.py:402` upsert; `enrich_analytics_snapshots.py:265,485` |
| 109 | omega_db.py:181 | Betfair/omega/omega_db.py | CONFERMATA | `_sb().table(table)`; `stream/db.py:564-596`; `season_aggregates.py:229-238` |
| 101 | safe_strategy/db.py:198 | Betfair/safe_strategy/db.py | CONFERMATA | `safe_strategy_scan` upsert; `:213` delete; `:228` `safe_strategy_status` |
| 200 | mike/service.py:6144-6171 | Betfair/mike/service.py | CONFERMATA | `_leggi_regolato_conto`; `regolato_conto.py` 359 righe |
| 175 | bot_db.py:91-264 | Betfair/safe_strategy/bot_db.py | CONFERMATA | `insert_trade` ... `trade_by_idempotency_key` (:245); `mike/db.py:175-288`, `omega_db.py:75-280` idem |
| 135 | logger.py:86 | logger.py (radice) | CONFERMATA | insert `api_call_log` (:86, :91); `api_quota.py:144-169` legge `api_call_log` |
| 105 | tennis_replay/caricamento.py:75-108 | Betfair/stream/tennis_replay/caricamento.py | CONFERMATA | upsert/update `T_EVENTI`; `:97` select `T_MERCATI`; `stream/db.py:714,726,741,752,758,762`; `curator.py:104` produce le righe |
| 199 | dossier.py:25-37 | Betfair/mike/dossier.py | CONFERMATA (nome corretto) | la funzione in dossier si chiama `load_atlas` (:25), involucro di `hazard_atlas.py:130` `load_hazard_atlas` (:130-144 confermato). Nome corretto nella scheda |
| 214 | dossier.py:147 | Betfair/mike/dossier.py | CONFERMATA | `if key in _EMPIRICAL_CACHE: return` senza scadenza |
| 173 | bot_db.py:62 | Betfair/safe_strategy/bot_db.py | CONFERMATA | `read_control`; `mike/db.py:59`, `omega_db.py:49` gemelle |
| 176 | mike/db.py:289-461 | Betfair/mike/db.py | CONFERMATA | `aggregate_rows` (:289) fino alla sezione Requests (:460); `_TOTALS_TTL_S = 300` (:44-45); `omega_db.py:777-960`, `bot_db.py:315-600` idem |
| 104 | refresh_worker.py:59-73 | Betfair/refresh_worker.py | CONFERMATA | update `_TABLE` done/error; `:38` select; `order_worker.py:61,106-120,136`; `odds_refresh.py:224,254,257`; `betfair_full_odds.py:73`; `order_exec.py:161` |
| 98 | config_stream.py:60 | Betfair/stream/config_stream.py | CONFERMATA | `LADDER_PUBLISH_SEC` 2.0; `stream/db.py:314,348,362,528,662,682` confermati |
| 93 | daily_stop_worker.py:250 | Betfair/stream/daily_stop_worker.py | CONFERMATA | select `_SETTLED_TABLE`; `xhedge_worker.py:119`, `risk_engine_worker.py:1001`, `stream/db.py:925-1127`, `liveOrders.ts:795,981,1034`, `safeBot.ts:2183`, `mike/db.py:657` confermati |
| 97 | config_stream.py:129 | Betfair/stream/config_stream.py | CONFERMATA | `WATCHLIST_POLL_SEC` default 120 |

Conteggio G: 23 CONFERMATE / 0 SPOSTATE / 2 FALSE.

## Correzioni fatte nelle schede (tutte marcate «[corretto dal verificatore 08/10]»)

- A riga 403 (D8): `stream_muto.py:35-45` -> `:20-31`.
- A riga 168: `marketstream.py:12` -> `:15` (`@retry`).
- B righe 35, 69, 101, 253: `tennis_runner.py:1688` -> `:1685`.
- B riga 262: `scan_feed.py:5-7` -> `:3-5`.
- C riga 509 (D-C2): `execution.py:1382` -> percorso legacy `:1299-1301`, chiamate REST a `:1382/:1389/:1394`.
- G riga 402: le tre righe `mike/db.py:683`, `omega_db.py:674`, `bot_db.py:1029` sono `revoke_live_order_request`, non `enqueue_live_order` (`mike/db.py:662`, `omega_db.py:634`, `bot_db.py:1003`).
- G riga 102 (T12): tolto `scalper_session.py:962`.
- G riga 391: aggiunta la lettura del codice di `live_order_worker.py:496-509` (kill switch con `get_live_settings` fallito).
- G riga 199: `load_hazard_atlas` -> `load_atlas` in `dossier.py`.

## Reperti importanti da portare all'utente

1. **G riga 391 (kill switch con cloud irraggiungibile)**: la scheda dice che il comportamento non e' letto e propone «ultimo valore noto in memoria + allarme».
   Il codice fa gia' la prima parte, in silenzio: `live_order_worker.py:496-509`, `except Exception: pass`, `_SETTINGS` resta l'ultimo valore. Resta scoperto il caso
   «mai letto» (`_SETTINGS = {}` -> `_db_kill_switch()` False, freno spento) e manca ogni allarme. La decisione (fail-closed all'avvio?) resta dell'utente.
2. **G riga 402**: la nota di controllo a campione dichiarava «confermati» tre righe come `enqueue_live_order`; sono `revoke_live_order_request`. Il controllo a campione
   dell'inventario 00 §3.2 va quindi riletto (la tabella e' giusta, la funzione no): non cambia numeri ne' decisioni, ma la frase «confermati» era stata scritta senza leggere le righe.
3. Nessuna delle schede A, B, C ha FALSE: le uniche discrepanze sono righe spostate di 2-13 posizioni che non cambiano nessun numero, difetto o decisione.

Non verificato: i numeri di traffico/righe del cloud (G, colonne «GET/min», righe e MB) e le citazioni a documenti esterni (`INVENTARIO_COMPONENTI_2026-09-25.md:813`, `desktop/main.js:233`, `s04_dettaglio_copie.tsv`, `07 §4.2`): fuori dal campione di codice.
