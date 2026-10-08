# SCHEDA G - DATI E ALGORITMI DEL CLOUD (strato dati operativo + algoritmi alimentati dal DB)

Componente: **G** (prefisso funzionalita' `G-`). Data: 08/10/2026. Autore: delegato Sonnet (scheda G).
Metodo: solo documenti, DB Supabase in sola lettura (SELECT, `execute_sql`), nessuna chiamata Betfair/API-Football, nessun codice di
produzione eseguito, nessun commit. Fonti gia' pronte e citate (non rifatte): `00_INVENTARIO.md` §3 (matrice 89 tabelle), `07_MISURE_OGGI.md`
(§4 richieste/min, §6 laboratorio persistenza, §7 cloud), `strumenti/dati_g1/uscite/{gemelle,chiamate_py,sql_*}.tsv`,
`strumenti/inventario/uscite/s03_*`. `02_COMPETITOR.md` (r.357) dice che per il diario degli ordini a prova di crash i competitor sono «n.d.»:
nessun competitor dichiara il proprio motore di persistenza, quindi la scelta qui sotto si confronta con i NUMERI MISURATI, non con una dichiarazione.

**Perimetro, PARTE 1 (strato dati operativo)** - righe con `wc -l` il 08/10:

| File | righe | `.table(`(prod, 00 §3.1) | `.execute()` nudi | via `_exec_retry` |
|---|---:|---:|---:|---:|
| `Betfair/stream/db.py` | 1.189 | 53 | 40 | 12 (`grep -c '_exec_retry('` = 13 incl. `def`) |
| `Betfair/safe_strategy/bot_db.py` | 1.044 | 46 | 45 | 0 |
| `Betfair/omega/omega_db.py` | 1.081 | 44 | 50 | 0 |
| `Betfair/stream/tennis_live/tennis_db.py` | 869 | 39 | 31 | 8 (9 incl. `def`) |
| `Betfair/mike/db.py` | 693 | 32 | 34 | 0 |
| `Betfair/safe_strategy/db.py` (scanner) | 502 | 12 | 13 | 0 |
| `db_client.py` (client + resilienza, modificato nell'albero di lavoro) | 410 | - | - | - |
| **Totale 7 moduli** | **5.788** | 226 | 213 | 20 |

Chiamate sparse FUORI dai moduli ma in codice di runtime dei bot (00 §3.1 tabella A, somma a mano): `scalper_session.py` 20, `live_order_worker.py` 17,
`scalper_service.py` 16, `order_worker.py` 7, `auto_follow.py` 7, `reconcile_worker.py` 7, `risk_engine_worker.py` 7, `money_management.py` 7,
`betfair_report_manager.py` 7, `odds_refresh.py` 4, `refresh_worker.py` 4, `tennis_replay/caricamento.py` 4 = **107** chiamate `.table(` in 12 file.

**Perimetro, PARTE 2 (algoritmi alimentati dal cloud)**: `Betfair/mike/dossier.py` (411), `Betfair/omega/omega_empirical.py` (249),
`Betfair/omega/omega_service.py` (8.936, solo `:1305-1380` e `:1397-1565`), `Betfair/omega/omega_model.py` (1.182), `Betfair/stream/engine/live_engine_pro.py`,
`Betfair/safe_strategy/service.py` (scanner), `Prediction/` (6.983 righe totali), `value_engine/`, `tactical_engine/`, `Ai Engine/ai_engine/`,
raccoglitori radice (`*_backfill.py`, `season_*.py`, `seasons_catchup.py`), `football_data_scraper/` (3.129), `.github/workflows/` (10 file), pg_cron (2 job), Edge Functions (2).

---

## 1. OGGI

### 1.1 PARTE 1 - Come il codice parla col cloud

**Implementazioni del client (domanda del brief: «8 `get_supabase`: quante implementazioni?»).** Risposta dal codice: **UNA** implementazione vera
(`db_client.py:75` `get_supabase_client`, client `supabase-py` per THREAD tramite `threading.local`, `db_client.py:14`) **piu' UNA parallela**
(`tennis_db.py:54-60` `get_tennis_client`, `create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)` senza opzioni, TLS propria `tennis_db.py:52`).
Gli **8 `get_supabase()`** sono wrapper, non client: `daily_yesterday_backfill.py:31`, `injuries_backfill.py:47`, `standings_backfill.py:47`,
`top_assists_backfill.py:47`, `top_cards_backfill.py:47`, `top_scorers_backfill.py:47` (variabile di modulo memoizzata alla prima chiamata: dopo un
rinnovo del client restano sul VECCHIO, come dice il commento di `per_fixture_backfill.py:83-88`), `league_orchestrator.py:41` (import locale + memoizzazione), `per_fixture_backfill.py:83`
(accessore senza memo, corretto l'08/10 per il rinnovo). `create_client(` diretto fuori da questi: `Betfair/tools/{scostamento_fischio_2026_09_13,
verifica_75_condizioni_2026_09_13,verifica_margine_2026_09_12,verifica_pnl_2026_09_12}.py` (4 strumenti), `football_data_scraper/fix_snapshot_time.py:58`.
`git grep -c get_supabase_client` (prod, senza test/audit): **118 file** usano il client unico.
Una terza via a rete esiste per l'atlante: `genera_atlante.py:1012` parla REST (`POST hazard_atlas_leghe?on_conflict=league_id`) con il suo `_Scrittore`
(ritenta 5xx/rete con attese 5/30/120/300 s, commento di `.github/workflows/hazard_atlas.yml`).

**Timeout (`db_client.py:14-70`).** Di serie il default della libreria: **120 s** per fase (`db_client.py:25-28`). Il profilo «bot» (`BOT_CONNECT_S=5`,
`BOT_LETTURA_S=20`, override `SUPABASE_BOT_CONNECT_S/LETTURA_S`, `db_client.py:33-34,49-56`) si accende SOLO con `usa_timeout_bot()` chiamato nei `main`
di 4 processi: `mike/service.py:7435`, `omega/omega_service.py:8815`, `safe_strategy/bot_service.py:10871`, `safe_strategy/service.py:3363`.
Restano a **120 s**: runner calcio e tennis, scalper, bot tennis (nessuna chiamata), backfill, e il client parallelo `tennis_db.py`. Il database stesso uccide
ogni query PostgREST oltre 8 s (`statement_timeout=8s` sul ruolo `authenticator`, verificato il 28/09: `db_client.py:21-24`).

**Ritenti: TRE meccanismi + nessuno.**
1. `Betfair/stream/net_retry.py:78-108` `with_backoff`: 3 tentativi, base 0,15 s, tetto 1,0 s, solo errori transitori. Usato da `_exec_retry` di
   `stream/db.py:44` (12 punti) e `tennis_db.py:63` (8 punti, copia con 96% di similarita': `gemelle.tsv`, riga `_exec_retry`).
2. `db_client.py:114-404` `con_ritentativi`/`esegui_con_retry`/`ClientResiliente`: 1+5 tentativi (2,4,8,16,32 s, ~62 s), interruttore dopo 2 guasti
   persistenti (`:117-118`), rinnovo client ogni 5.000 richieste (`:121`, GOAWAY HTTP/2 a 10.000). Usato da 12 file della catena backfill
   (`git grep -ln`): `db_client.py, db_delete_retry.py, injuries_backfill.py, leagues_mapper.py, per_fixture_backfill.py, season_aggregates.py, season_gaps.py,
   seasons_catchup.py, standings_backfill.py, top_assists/cards/scorers_backfill.py`. Nessun bot, nessun runner.
3. Nessuno: **142 `.execute()` nudi** in `bot_db.py` 45 + `omega_db.py` 50 + `mike/db.py` 34 + `safe_strategy/db.py` 13, piu' 40 in `stream/db.py` e 31
   in `tennis_db.py`. Una scrittura fallita in un bot sale come eccezione e (nei `log()`) viene inghiottita con un warning (`mike/db.py:71-81`): e' la forma del
   difetto 18 di `PROCESSO_STANDARD_BOT.md` §7 («scrittura fallita declassata a warning»).

**Idempotenza oggi.** Le scritture di STATO sono upsert con `on_conflict` (elenco con `file:riga`: `stream/db.py:164,170,315,348,644,662,683,753,820,829,941,946,
964,978,1007,1070,1088,1127`; `mike/db.py:141,164`; `omega_db.py:303,442,446,482,1047`; `bot_db.py:880`; `safe_strategy/db.py:198,229`;
`tennis_db.py:118,260,292,314,605,628,765,778`; `scalper_service.py:185,196` `ignore_duplicates`; `auto_follow.py:426`). Le scritture di LOG sono `insert` semplici su
tabelle con `BIGSERIAL id` e **nessuna chiave naturale**: `mike_activity` (`migrations/mike_bot.sql:124-130`), `omega_activity` (`omega_bot.sql:73`),
`safe_strategy_activity` (`safe_strategy_bot.sql:95`), `scalper_activity` (`scalper_bot.sql:53-59`), `tennis_bot_activity` (`tennis_bots.sql:75`), `live_alerts`
(`live_alerts.sql:22-30`), `betfair_live_journal` (`betfair_live_pnl_journal.sql:89`), `betfair_live_audit` (`betfair_live_controls.sql:38`). Un RITENTATIVO di queste
SCRIVE DUE VOLTE. Le tabelle dei trade sono `insert` con id generato dal cloud e **RESTITUITO al bot** (`mike/db.py:175-181` ritorna `rows[0].get("id")`,
`omega_db.py:75`, `bot_db.py:91`), usato poi come `eq("id", ...)` nelle `update_trade` (`mike/db.py:183-188`) e come `closes_trade_id`: oggi senza il cloud un bot
NON puo' aprire una posizione.

### 1.2 PARTE 1 - Quanto traffico fa (da `07_MISURE_OGGI.md` §4, non rimisurato)
Totale app: **1.309 richieste/min** con stream attivo (04/10, 92 min), 1.268 (02/10), 707,5 (08/10 «nessun evento da streammare»); ~22 al secondo (07 §4.1, 00 §3.5).
Per servizio 04/10: runner-calcio 557,6; safe-bot 265,8; mike 256,1; scanner 88,9; scalper 55,0; tennis-bot 44,4; runner-tennis 28,4; omega 12,7 (07 §4.2).
**Traffico di sola coda/controllo** (letture ripetute di tabelle da 1 a 445 righe: `*_control`, `*_requests`, `risk_rules`, `get_live_settings`) ~391 su 707,5/min l'08/10 (07 §4.2).
Con stream attivo il runner legge ~486 volte al minuto 3 tabelle di 98, 14 e 1 riga (07 §4.2). Latenza di rete misurata: giro minimo gateway **21,3 ms p50**, 26,1 p95
(connessione calda, senza query); TLS 50 ms, TCP 15 ms, DNS 23 ms; prima richiesta 79 ms (07 §4.3). La latenza di UNA query vera dell'app NON e' misurata (httpx non la scrive, 07 §4.3).
Dimensioni cloud: 52 GB, 173 tabelle, `max_connections` 60; tabelle dei bot 1-93.068 righe, 0,14-19 MB (07 §7).

### 1.3 PARTE 1 - Tabella per tabella: chi scrive, chi legge, quanto, di che natura (89 tabelle di 00 §3.2, raggruppate in famiglie T01-T17; ogni nome e' citato)
Natura: **SV** stato vivo; **CMD** comando fra processi (coda/richiesta); **ARC** archivio append-only; **STA** statistica/derivato; **CFG** configurazione.
Frequenza = chiamate/min. `MISURE:NN` = `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`. «n.m.» = non misurata (lo strumento che la misurerebbe: `m04_chiamate_db.py` ad app accesa).

| Fam. | Tabelle | Scrive oggi (`file:riga`) | Legge oggi | Frequenza | Natura |
|---|---|---|---|---|---|
| T01 | `betfair_live_order_requests` | `mike/db.py:683`, `omega_db.py:674`, `bot_db.py:1029` (+9, tra cui `live_order_worker.py:3343` e `stream/db.py:1146` `fail_stale_pending_requests`) | runner: `live_order_worker` a `LIVE_ORDER_QUEUE_POLL_SEC=1,0` (`config_stream.py:229`); bot per ref `mike/db.py:669,676`, `omega_db.py:648` | GET 202,3/min runner 04/10 (07 §4.2); 189 (MISURE:100) | CMD (101 righe, 07 §7) |
| T02 | `betfair_live_orders` | `stream/db.py:773-835` (upsert `mode,client_order_ref` `:820,:829`), `:1139` | `mike/db.py:233,691`, `omega_db.py:687`, `bot_db.py:1040` (+7) | GET 11 runner (MISURE:104) | SV (specchio ordini; 102 righe) |
| T03 | `betfair_live_positions`, `betfair_live_settled`, `betfair_live_risk_state`, `betfair_live_account`, `betfair_live_heartbeat`, `betfair_live_xhedge` | `stream/db.py:925-1127`, `xhedge_worker.py:119` | `stream/db.py:425,451,481`, `daily_stop_worker.py:250`, `risk_engine_worker.py:1001`, bot `mike/db.py:657`, UI `liveOrders.ts:795,981,1034`, `safeBot.ts:2183` | heartbeat POST 7,4/min (07 §4.2); settled GET 11; account POST 2 (MISURE:109) | SV |
| T04 | `betfair_live_risk_rules` | `risk_engine_worker.py:189` (da UI `cancel_live_risk_rule`, `liveOrders.ts:494`) | `reconcile_worker.py:1264`, `risk_engine_worker.py:1096,1173` (+3) a `RISK_ENGINE_POLL_SEC=1,0` (`config_stream.py:311`) | GET 164,7/min 04/10; 63,8 08/10 (07 §4.2) | CFG/CMD (14 righe) |
| T05 | RPC `get_live_settings` (tabella `betfair_live_settings`, definita ma senza `.table()`) | scritta da RPC UI `set_live_kill_switch`, `live_order_mode_avvio` | `live_order_worker.py:498`, scalper | 119,9/min runner 04/10; 17,5 scalper (07 §4.2) | CFG (kill switch, modo ordini) |
| T06 | `betfair_live_journal`, `betfair_live_audit`, `live_alerts`, `live_run_log`, `signal_history`, `omega_events` (log), `theta_confirm_requests` | `stream/db.py:988,697,644`, `live_order_worker.py:922,1071,1134`, `daily_stop_worker.py:391`, `motore_ordini.py:2431`, `scalper_session.py:709,859,1075,1699,1936,2064`, `money_management.py:2434,2471` | nessun lettore Python (matrice 00 §3.2: «-»); `live_alerts` letta dalla UI (banner), `theta_confirm_requests` `scalper_session.py:1947` | n.m. | ARC |
| T07 | `live_follow`, `personal_watchlist` | `auto_follow.py:402,426,429` (+5), `stream/db.py:164,170` | `mike/db.py:651`, `omega_db.py:618`, `bot_db.py:989` (+12), `watchlist.py:29`, UI `safeBot.ts:2195` | GET 26,9-29/min runner (07 §4.2, MISURE:103); watchlist poll `LIVE_WATCHLIST_POLL_SEC=120` (`config_stream.py:129`) | SV/CMD |
| T08 | `live_now`, `live_markets`, `live_ladder`, `live_signals` | `stream/db.py:348,362,528` (now), `:314` (markets), `:682` (ladder, write-on-change a `LADDER_PUBLISH_SEC=2,0`, `config_stream.py:60`), `:662` | `omega_db.py:595`, `stream/db.py:404,513`, `live_order_worker.py:999,1105`, UI `live.ts:140,560,621` | ladder 889 righe 2,6 MB (07 §7); n.m. | SV (solo display remoto) |
| T09 | `mike_control`, `mike_requests`, `mike_trades`, `mike_events`, `mike_activity` | `mike/db.py:68,509,516` (control/requests), `:176,186` (trades), `:141,164` (events), `:76` (activity) | `mike/db.py:60,463,490,533,192-211,108,117` + `safe_strategy/db.py:307` + UI `mike.ts:2301` | 04/10: trades GET 107,8/min, control 58, requests 58, events POST 25 (MISURE:63-66); 08/10 trades 10,4/min (07 §4.2, causa NON verificata) | CFG, CMD, SV, SV, ARC |
| T10 | `omega_control`, `omega_trades`, `omega_events`, `omega_manual_requests`, `omega_missions`, `omega_market_snapshot`, `omega_daily_goal`, `omega_activity` | `omega_db.py:58,76-94,303,442,297,323,394,717,482,1047,63` | `omega_db.py:50,253,722,486-564,283,373,699,708` | omega 12,7/min (omega_trades GET 5,6, 07 §4.2); omega fermo il 02/10 | CFG, SV, SV, CMD, SV, SV, SV, ARC |
| T11 | `safe_strategy_control`, `_requests`, `_trades`, `_opportunities`, `_activity`, `_status`, `_scan` | `bot_db.py:74,651-678,92-110,879-903,79`, `safe_strategy/db.py:198,213,228` | `bot_db.py:64,606-632,122-172,436,961,973`, `mike/db.py:560,569`, `auto_follow.py:466` | trades GET 82/min, requests GET 44,6 + PATCH 19,1, control GET 37,9 + PATCH 19,0, `get_safe_aggregates` 17,9 (07 §4.2); scan POST 65,4/min | CFG, CMD, SV, SV, ARC, SV, SV |
| T12 | `scalper_control`, `scalper_service_control`, `scalper_activity` | `scalper_service.py:86,185-214,890`, `scalper_session.py:962,1270,1281` | `scalper_service.py:75,94,147,214` | control 17,5 + service_control 17,5 + `get_live_settings` 17,5 /min (07 §4.2); `scalper_activity` 93.068 righe 19 MB (07 §7) | CFG, CFG, ARC |
| T13 | `tennis_live_follow`, `tennis_live_now`, `tennis_live_ladder`, `tennis_markets`, `tennis_live_orders`, `tennis_live_positions`, `tennis_live_order_queue`, `tennis_bot_control`, `tennis_bot_service_control`, `tennis_bot_activity` | `tennis_db.py:118,231,260,292,306,518,549-604,627,710,444-451`, `esecutore_tennis.py:266`, `betfair_tennis_odds.py:274,278` | `tennis_db.py:198,240,335-377,399,662`, `tennis_bot_service.py:151`, `tennis_replay/importa.py:78,82` | `tennis_live_follow` GET 27,1/min runner-tennis; `tennis_bot_control` GET 21,5; `*_service_control` PATCH 14,3 + GET 3,6 (07 §4.2) | SV, SV, SV, SV, SV, SV, CMD, CFG, CFG, ARC |
| T14 | `betfair_order_requests`, `betfair_refresh_requests`, `betfair_market_odds`, `betfair_live_order_requests` (vecchia via `order_worker`) | `order_worker.py:106-120`, `refresh_worker.py:59-73`, `odds_refresh.py:254,257`, `betfair_full_odds.py:73` | `order_worker.py:61,136`, `refresh_worker.py:38`, `odds_refresh.py:224`, `order_exec.py:161` | n.m. (percorso manuale/report) | CMD, CMD, SV |
| T15 | `live_backtest_requests`, `live_backtest_results`, `replay_bot_esiti`, `live_market_snapshots`, `live_score_timeline`, `tennis_replay_eventi/_mercati/_snapshots/_punteggio` | `stream/db.py:726,741,752,758,762`, `curator.py:104`, `tennis_replay/caricamento.py:75-108` | `stream/db.py:714`, `caricamento.py:97` | `live_market_snapshots` 1.288.493 righe 2,4 GB, ultimo `ts` 2026-09-01 16:44 UTC (SELECT 08/10); `tennis_replay_snapshots` 137.171 righe 257 MB (07 §7) | ARC |
| T16 | `personal_trades`, `bet_features`, `direction_pagella`, `engine_signals`, `analytics_bets`, `analytics_decisions`, `analytics_snap_staging`, `analytics_signals`, `poisson_calibration`, `ml_post_calibration`, `ai_model_registry`, `model_performance` | script di radice (vedi §1.5) | bot: nessuno (matrice 00 §3.2); UI via RPC `get_analytics*`, `get_direction*` | `analytics_signals` 730.319 UPDATE dal riavvio 07:28 (07 §7) | STA |
| T17 | `matches`, `match_odds`, `match_events`, `match_lineups`, `match_player_stats`, `match_team_stats`, `fixture_predictions`, `standings`, `injuries`, `top_scorers`, `top_assists`, `top_cards`, `api_coverage_by_season`, `api_call_log`, `season_backfill_state`, `fixture_detail_checks`, `leads` | raccoglitori (§1.5) | vedi PARTE 2 | vedi §1.5 | STA/ARC |

Nomi dinamici (6): `stream/db.py:564-596` helper generico `insert_rows_resilient`, `omega_db.py:181` `_select_all`, `season_aggregates.py:229-238`, `scalper_session.py:962`
(`MU.TABELLA_ORDINI_CONTO`), `live_order_worker.py:3288`, `per_fixture_backfill.py:219` (00 §3 intestazione). Tabelle definite nei `.sql` e senza `.table()`: 32; 21 senza alcun riferimento
(00 §3.4: `omega_*` e `personal_*` sono «mondo SQL» alimentato da funzioni/job del DB, non verificabile dal repo).

### 1.4 PARTE 1 - Canali locali gia' esistenti (non si riscrivono)
Canale WebSocket 127.0.0.1 per runner calcio 47331, tennis 47332, Mike 47333, Omega 47334, Safe 47335, scanner 47336, ponte tennis 47337, scalper 47338
(00 §5.4; `local_channel.py:14-18,292,404`). I bot pubblicano DOPO la scrittura riuscita sul DB (`mike/db.py:177-179`, `tennis_db.py:22-35`); i comandi ordine hanno la via
canale `*_ORDINI_VIA_CANALE` (`porta_ordini.py`) con ripiego sulla coda DB. Oggi il DB e' ancora il REGISTRO: il canale e' un derivato pubblicato dopo.
Cadenza canale ladder 200 ms (`config_stream.py:74`) contro 2,0 s del DB ladder (`:60`).

### 1.5 PARTE 2 - Chi popola l'archivio (verificato con SELECT di `max(data)`, 08/10 ~15:00 UTC, solo lettura)

| Raccoglitore | Lancio (prova) | Scrive | Ultimo aggiornamento letto dal DB | Vivo? |
|---|---|---|---|---|
| `daily_yesterday_backfill.py` (396) | `.github/workflows/daily_yesterday_backfill.yml` cron `12 1 * * *` | `matches` (`:75`) | `matches.updated_at` 2026-10-08 07:16:56 UTC | SI (la tabella e' viva; non attribuisco il minuto al job singolo) |
| `Prediction/today_predictions_backfill.py` (2.789) | `today_predictions_backfill.yml` cron `18 2 * * *`; invoca `ai_engine.serving_batch` (`:2730`) e `tactical_engine.serving` (`:2742,2752`) | `fixture_predictions` | `updated_at` 2026-10-08 09:43:44; `fixture_date` massima 2026-10-08 23:05 (solo la giornata di oggi e' popolata) | SI |
| `Prediction/predictions_results_backfill.py` (875) + `build_analytics_signals.py` + `merge_engine_signals.py` + `enrich_analytics_snapshots.py` | `predictions_results_backfill.yml` cron `23 3 * * *` (step a `:78,96,108,131`) | `fixture_predictions` (esiti), `analytics_signals` | `analytics_signals.updated_at` 2026-10-08 12:02:32; `generated_at` 09:43:47 | SI |
| `seasons_catchup.py` (1.144) + `season_gaps.py` (679) + `per_fixture_backfill.py` (1.216) + `season_aggregates.py` | `seasons_catchup.yml` cron `47 13 * * *` e `workflow_run` dopo «Leagues Mapping» | `match_events/lineups/player_stats/team_stats`, `season_backfill_state`, `fixture_detail_checks`; per `standings/injuries/top_*` via `season_aggregates.py:194-198,229-238` che importa i 4 `*_backfill.py` | `season_backfill_state.last_run_at` 2026-10-07 19:58:41; `standings` 19:58:40, `injuries` 19:39:45, `top_scorers/assists/cards` 19:56:24-25 (07/10); `match_*` grandi: `max(updated_at)` ANDATA IN TIMEOUT 2 volte (statement 8 s su 6-24 M righe): NON misurato | SI per `standings/injuries/top_*`; `match_*`: non misurato |
| `leagues_mapper.py` | `leagues_mapper.yml` cron `12 0 1 * *` + `workflow_run` dopo il Daily | `api_coverage_by_season` | `updated_at` 2026-10-08 07:22:34 | SI |
| `generate_dynamic_cal.py`, `update_poisson_calibration.py`, `generate_dc_rho.py` | `weekly_poisson_calibration.yml` cron `27 3 * * 1` | `poisson_calibration` | `generated_at` 2026-10-05 10:48:10 (lunedi', coerente col cron settimanale) | SI |
| `compute_ml_post_calibration.py` | `ml_calibration.yml` cron `14 5 * * *` + `workflow_run` dopo il retrain | `ml_post_calibration` | `generated_at` 2026-10-08 13:27:26 | SI |
| `cloud_retrain_shard.py`, `retrain_all_leagues.py` | `retrain_models.yml` cron `19 8 * * *` + `workflow_run` dopo il Daily (`:46-47`) | `ai_model_registry`, storage modelli (`seriea_model_export.py:679`) | `trained_at` 2026-10-08 13:25:55 | SI |
| `genera_atlante.py` (hazard atlas) | `hazard_atlas.yml` `workflow_run` dopo il Daily (`:39-40`); `atlante_a_domanda.py` sul PC | `hazard_atlas`, `hazard_atlas_leghe`, file atlante locale (`hazard_atlas.py:130-144`) | `generated_at` 2026-10-08 07:21:48 | SI |
| pg_cron `omega_transitions_nightly` | `cron.job`: `0 4 * * *`, `active=true`, comando `SET statement_timeout='20min'; SELECT public.omega_transitions_nightly(600);` | `omega_minute_transitions` (1.078.211 righe), `omega_ht_ft_transitions` | `built_at` 2026-10-08 04:00:00.17 (entrambe) | SI |
| pg_cron `make-daily-post-job` + Edge Function `make-daily-post` | `cron.job` `00 09 * * *`, `active=true`, `net.http_post` alla function; sorgente `Telegram bot/supabase/functions/make-daily-post/index.ts:18-19,99` (`SICUREZZA_DB_2026-09-24.md:70`) | post Telegram; legge `fixture_predictions` | n/a (nessuna tabella dedicata) | SI (cron attivo; esito dell'invio NON verificato) |
| Edge Function `telegram-bot` | chiave `anon` (`SICUREZZA_DB_2026-09-24.md:71`, `Telegram bot/supabase/functions/telegram-bot/index.ts:35,328,440`) | - | - | non verificato |
| `logger.py:86,91` / `api_quota.py:144-169` | usato da `api_client.py`, 14 punti in `api_quota.py` | `api_call_log` (2.751.992 righe) | `created_at` 2026-10-08 09:54:38 | SI |
| `football_data_scraper/` (3.129) | nessun workflow, nessun chiamante fuori dalla cartella (`git grep`: 0): manuale | `match_odds` (92.477.800 righe, 20 GB, `fix_snapshot_time.py:45`) | `max(snapshot_time)` in TIMEOUT (8 s) | NON misurabile; senza lancio automatico |
| `Prediction/backfill_historical_analysis.py`, `AGGIORNA_CAMPO_db_json_analisi.py`, `compute_*` | manuali | `fixture_predictions` | - | manuali |
| `betfair_report_manager.py` (1.737) | `aggiorna_report.bat:21`, `aggiorna_report_veloce.bat:17` (manuale; Google Sheets; `RotatingFileHandler` `:6,35-42`) | `betfair_market_odds` e `matches`/`ai_model_registry` in lettura | n.m. | manuale |
| `regolato_conto.py` (359) | importato da `mike/service.py:44` | NESSUNA scrittura DB: «Funzioni PURE (nessuna rete, nessun DB)» (`regolato_conto.py:6`) | - | si', ma non e' cloud |

Cloud: `analytics_signals` ha piu' UPDATE (730.319 dal riavvio) di qualunque tabella dei bot (07 §7). L'app NON era accesa l'08/10 (07 intestazione): le tabelle dei bot non hanno una «ultima data» significativa oggi.

---

## 2. FUNZIONALITA' (prefisso `G-`)

Visibili in UI: le tabelle di T07-T13 alimentano i pannelli (`frontend/src/lib/{safeBot,mike,omega,live,liveOrders,tennis,scalperControlRoom}.ts`, `controlRoomProposte.ts`, `safeStrategyScan.ts`);
parametri editabili: `*_control.params` e `betfair_live_settings` (via RPC `*_activate`, `set_live_*`); le funzioni dati sono invisibili ma le loro righe no.

### 2.1 PARTE 1 - Cliente e resilienza
- **G-001** `db_client.py:75-110` client Supabase per thread, ricreato quando cambia il profilo di timeout o dopo `rinnova_client()`; marca `_db_client_prod`. Fa: isola le connessioni httpx dei worker del runner (fix WinError 10035, `:8-13`).
- **G-002** `db_client.py:33-70` profilo timeout bot (5 s connect, 20 s lettura, override da ambiente). Fa: un giro di bot non resta appeso 120 s.
- **G-003** `db_client.py:243-270` `rinnova_client`/`attiva_rinnovo_connessioni` (ogni 5.000 richieste): evita il GOAWAY HTTP/2.
- **G-004** `db_client.py:187-243` `_classe_di`/`classifica_guasto_rete`/`descrivi_errore`/`GuastoRete`: classifica guasti transitori (5xx, HTML Cloudflare, `PGRST000-003`, `08xxx`, `53300`, `57P01/57P03`); mai 4xx ne' 57014.
- **G-005** `db_client.py:280-404` `con_ritentativi`, `esegui_con_retry`, `_Catena`, `ClientResiliente`, `riepilogo_rete`: ritenti 2-32 s con interruttore dopo 2 guasti; statistiche `STATISTICHE_RETE`.
- **G-006** `Betfair/stream/net_retry.py:78-108` `with_backoff` (3 x 0,15-1,0 s) + `is_transient` (usato da `stream/db.py:44`, `tennis_db.py:63`, `live_order_worker.py:3343`).
- **G-007** `tennis_db.py:54-60` secondo client Supabase del tennis (senza profilo timeout, senza rinnovo).
- **G-008** `db_delete_retry.py` cancellazioni con ritenti (catena backfill).

### 2.2 PARTE 1 - `Betfair/stream/db.py` (1.189 righe, indice delle funzioni)
- **G-009** `:81-231` `register_follow`, `get_follow_record`, `set_follow_status`, `list_pending_follows`: iscrizione partite a `live_follow` (upsert `event_id`), flag `record` non degradato mai (`:93-107`), fallback colonna assente (`:69-80`).
- **G-010** `:231-296` `get_fixture_prematch_lambdas`: lambda Dixon-Coles per squadra da `fixture_predictions` (`tactical_engine_json` poi `db_json_analisi.inputs`) - PRIOR del motore live.
- **G-011** `:296-384` `upsert_markets`, `update_live_now`, `chiudi_live_now`: `live_markets`/`live_now` per la UI.
- **G-012** `:384-537` `_stato_ordine`, `esposizione_aperta`, `mercati_evento`, `_posizioni_aperte_non_regolate`, `mercati_con_soldi`, `soldi_sull_evento`, `chiudi_live_now_orfani`: «ci sono soldi su questo evento?» (guardia di chiusura/pulizia).
- **G-013** `:537-641` `delete_event_rows`, `insert_rows_resilient`, `upload_snapshots`, `upload_timeline`, `write_run_log`: curatore snapshot (chunk adattivo su 57014, `:26-37,579-628`).
- **G-014** `:650-710` `upsert_live_signals`, `upsert_live_ladder` (indice UNIQUE non parziale, `:675`), `insert_alert`.
- **G-015** `:710-773` coda backtest: `claim_backtest_request`, `set_backtest_status`, `write_replay_bot_esito`, `write_backtest_results`.
- **G-016** `:773-935` specchio ordini: `upsert_live_order` (+ `_upsert_specchio` con fallback senza colonna, `:814-835`), osservatori/scrittore (`:835-897`), `find_live_order_ref`.
- **G-017** `:925-1118` `upsert_live_position`, `upsert_live_settled`, `upsert_live_risk_state`, `insert_live_journal`, `upsert_live_account`, `..._manual_pnl`, `..._pnl_reale`, `update_pnl_betfair`.
- **G-018** `:1118-1189` `upsert_live_heartbeat`, `cleanup_paper_mirror`, `fail_stale_pending_requests` (richieste vecchie 120 s -> `error`).

### 2.3 PARTE 1 - Moduli per bot (stesse operazioni, 5 copie: `gemelle.tsv` 90 coppie, 36 nomi)
- **G-019** `mike/db.py:59-90` `read_control`/`set_control`/`log` (+ `omega_db.py:49-72`, `bot_db.py:62-90`): riga `*_control` singleton `id=1` e attivita'; copie con righe gemelle `mike/db.py:59` ~ `omega_db.py:49` ~ `bot_db.py:62`.
- **G-020** `mike/db.py:91-170` eventi (`filtro_finestra_eventi`, `list_events`, `get_event`, `upsert_event(s)`, `delete_events`); `omega_db.py:300-312,436-510` (`upsert_events`, `replace_events`, `update_event_markets`, `upsert_market_snapshot`, `get_event`); `bot_db.py:875-925` (`upsert/purge/delete_opportunities`, `get_event`).
- **G-021** `mike/db.py:175-288`, `omega_db.py:75-280`, `bot_db.py:91-264`: trade (`insert_trade` con id restituito, `update_trade`, `delete_trade`, `get_trade`, `open_trades`, `trades_for_event`, `closing_trades_for`, `live_trades`, `all_trades`, `proprietari_bet`, `traded_*`, `failed_legs`, `trade_by_idempotency_key` `bot_db.py:245`).
- **G-022** `mike/db.py:289-461`, `omega_db.py:777-960`, `bot_db.py:315-600`: aggregati P&L per modalita' (RPC `get_mike_aggregates`, `get_omega_aggregates(_modalita)`, `get_safe_aggregates`, con ripiego a calcolo da righe `_aggrega`, memo `_AGG_RPC`, cache `_TOTALS` 300 s `mike/db.py:44-47`).
- **G-023** `mike/db.py:462-552`, `omega_db.py:281-360`, `bot_db.py:604-875`: richieste dell'utente (`pending_requests`, `set_request_status`, `fail_stale_processing`) + proposte di chiusura/opportunita' (`bot_db.py:625-835`, `omega_db.py:366-432`).
- **G-024** `mike/db.py:553-649`, `omega_db.py:742-776`, `bot_db.py:925-1000`: letture di contorno: `fetch_scan_rows`, `scanner_status`, `fixture_id_for_event`, `fixture_lambdas`, `fixture_analysis`, `fixtures_for_window`, `market_frequency`, `ht_ft_rows`.
- **G-025** `mike/db.py:650-693`, `omega_db.py:586-696`, `bot_db.py:987-1044`: CODA FLUMINE copiata 1:1 («copia 1:1 di bot_db», `mike/db.py:~645`): `live_follow_status`, `runner_heartbeat`, `enqueue_live_order`, `get_live_order_request(_by_ref)`, `revoke_live_order_request`, `get_live_order_mirror` (righe gemelle al 99-100%).
- **G-026** `omega_db.py:697-740,1011-1081`: missioni, `event_lambda_hint`, `save_event_model`, `positions_for_results`, `upsert_daily_goal`, `ht_ft_transitions`, `minute_transitions` (RPC).
- **G-027** `safe_strategy/db.py:45-246`: lettura/scrittura dello scanner (`list_scan_event_ids`, `load_scan_pre_ko`, `is_usable_pre_ko(_tennis)`, `fixtures_window`, `load_schede_fixture`, `load_round_fixture`, `upsert/delete_scan_rows`, `upsert_status`); `:246-502` esposizioni dei bot (`list_bot_exposures` RPC `list_bot_exposures` con ripiego a 3 fonti).
- **G-028** `tennis_db.py:86-393`: follow/now/ladder/feed tennis (`register_tennis_follow`, `list_tennis_feed_rows`, `scanner_heartbeat`, `upsert_tennis_ladder/now`, `chiudi_tennis_now(_orfani)`, `soldi_sull_evento_tennis`).
- **G-029** `tennis_db.py:393-540,643-785`: controlli e servizi bot tennis (`list/set_tennis_bot_*`, `upsert_tennis_bot_control`, `_upsert_control` su `event_id,bot_key`, `write_tennis_bot_activity`).
- **G-030** `tennis_db.py:532-640,807-869`: coda ordini tennis (`claim_tennis_order`, `write_tennis_order_done/error`, `upsert_tennis_order/position`, `fail_stale_pending_tennis_orders`, `chiudi_specchio_paper_orfano`).
- **G-031** Chiamate sparse runtime (107, §perimetro): scalper (`scalper_service.py`, `scalper_session.py`), coda manuale (`order_worker.py`, `refresh_worker.py`), `auto_follow.py` (`live_follow` upsert), `reconcile_worker.py`, `risk_engine_worker.py`, `daily_stop_worker.py:250,391`, `xhedge_worker.py:119`, `money_management.py:2434,2471`, `odds_refresh.py`.
- **G-032** RPC di produzione (53 chiamate prod, 00 §3.1 B): `request_betfair_live_order` x5, `get_live_settings` x4, `set_live_kill_switch`, `live_order_mode_avvio`, `get_*_aggregates`, `list_bot_exposures`, `get_omega_ht_ft`, `get_omega_minute_ft`, `get_market_frequency`.

### 2.4 PARTE 2 - Algoritmi alimentati dal cloud (DEVONO restare)
- **G-033** **Modello di Mike, pre-match**: `mike/dossier.py:66-111` `build_prematch`: ponte evento->fixture (`db.fixture_id_for_event`, `mike/db.py:580`), lambda (`fixture_lambdas` -> `stream/db.py:231`, tabella `fixture_predictions`: `league_id, tactical_engine_json, db_json_analisi, home_team_id, away_team_id`), `rho` (`db_json_analisi.inputs.dc_rho`), `p_under35_cal` (da `markets_calibrated` o `markets`), `p4_pre` (griglia residua `omega_model.residual_grid`). Frequenza: **una volta per evento** al primo aggancio (`dossier.py:3-5`), 3 letture (`mike/db.py:580,609,625`). Latenza tollerata: secondi PRIMA del KO. Consumatore: `mike/engine` (veto M1) e il servizio.
- **G-034** **Tabella empirica HT->FT di Mike**: `mike/dossier.py:138-171` `get_empirical`: RPC `get_omega_ht_ft` via `mike/db.py:637` -> `omega_db.py:1055`; cache per processo **senza scadenza** (`:147-148`), errore o tabella vuota = riprova dopo 600 s (`:138,152-166`). Tabella `omega_ht_ft_transitions` ricostruita ogni notte alle 04:00 UTC (pg_cron). **Divergenza da riportare, non toccata**: la copia di Omega scade ogni 6 h (`omega_service.py:106`), quella di Mike mai nella vita del processo.
- **G-035** **Cache empiriche di Omega**: `omega_service.py:1313-1374`: `_EMPIRICAL_CACHE` (tetto 500 chiavi, TTL 6 h, `:1356-1374`) per RPC `get_omega_ht_ft(league_id)`; `_MINUTE_CACHE` (tetto 2.000, TTL 6 h, `:1319-1346`) per RPC `get_omega_minute_ft(league_id, bucket, target)`; bucket da 5' (`omega_empirical.py:168-176`: massimo 85 FT, 40 HT); errori NON in cache (`:1340-1342,1364-1366`). Chiamate da `_model_select` (`omega_service.py:1397`, righe `1432,1444`) e `_v3_p_empirica` (`:1543`, righe `1556,1565`): **sono nel ciclo di decisione**: ogni cambio di bucket (ogni 5') per (lega, target) senza voce valida e' una RPC SINCRONA nel percorso del bot (latenza di `get_omega_minute_ft`: NON misurata; il giro minimo e' 21 ms, il profilo bot da' tetto 20 s). Tabella `omega_minute_transitions` 1.078.211 righe 270 MB, ricostruita alle 04:00 UTC.
- **G-036** **Letture di contorno di Omega**: `omega_db.py:742` `fixtures_for_window` (limit 2000 su `fixture_predictions`), `:756` `fixture_analysis` (`db_json_analisi`), `:765` `market_frequency` (RPC `get_market_frequency`, ultime 300 settlate per lega; consumatore `omega_advisor.py:375`), `omega_service.py:1215-1240` catena lambda (`pre_ko` -> `get_fixture_prematch_lambdas` -> saved).
- **G-037** **Segnali e previsioni**: `fixture_predictions` (121.881 righe, 1,06 GB) scritta da `today_predictions_backfill` (02:18 UTC) e dai due motori `ai_engine.serving_batch` (`Ai Engine/ai_engine/serving_batch.py:1`, gemello di `tactical_engine/serving.py`); letta da UI (`FixtureSelector.tsx:30`, `MatchesList.tsx:157`), bot (lambda), scanner (`safe_strategy/db.py:167` `raw_json` per le schede), Edge `make-daily-post`.
- **G-038** `analytics_signals` (1.252.609 righe, 1,1 GB): `build_analytics_signals.py:402` + `enrich_analytics_snapshots.py` (`:265,485`); consumatori: UI via RPC `get_analytics*`/`backtest_strategy`/`get_decisions*` (`frontend/src/lib/analytics.ts:81-346`), certificazioni. Nessuna lettura da un bot (matrice 00 §3.2).
- **G-039** **`value_engine/` e `tactical_engine/` nel percorso live**: solo moduli PURI senza DB (`grep -c "supabase|get_supabase|.table("` = 0 in `value_engine/goal_timing.py`, `devig.py`, `poisson_total.py`, `tactical_engine/dixon_coles.py`): `goal_timing` (`omega_model.py:261`, `opportunity.py:484`, `live_engine.py:57`), `devig_pair`/`lam_from_prematch` (`omega_model.py:720-721,893`, `live_engine_pro.py:274-275`), `dc_tau`/`score_matrix` (`live_engine_pro.py:26`); dato locale `value_engine/data/goal_time_cdf.json` (`goal_timing.py:14`). Le parti con DB (`value_engine/calibrate.py:37` legge `match_events`; `tactical_engine/serving.py` 7 chiamate) girano nei raccoglitori notturni.
- **G-040** **Scanner `safe_strategy_scan`**: scrittore `safe_strategy/service.py:2847,3409` (`upsert_scan_rows`, 65,4 POST/min 08/10), `:2930` (`upsert_status`); lettori Mike (14/min, `mike/db.py:553,560`), runner (8/min), safe-bot (5/min), UI (`safeStrategyScan.ts:343`); gia' dal canale 47336 (`ClientScan`, `canale_scan.py:312`). Input dello scanner: schede da `fixture_predictions.raw_json` e round da `matches.raw_json` (`safe_strategy/db.py:167-189`).
- **G-041** **Statistiche di contorno** `standings`, `injuries`, `top_scorers`, `top_assists`, `top_cards`: scritte da `*_backfill.py` via `season_aggregates.py`; **nessun lettore Python in repo** (matrice 00 §3.2: «-») e nessun lettore frontend; vive (aggiornate il 07/10 ~19:40-19:58 UTC). Lettori eventuali in funzioni SQL: non verificabile dal repo.
- **G-042** **Storico `match_*`** (`match_odds` 92,5 M righe 20 GB, `match_lineups` 24,3 M 7,6 GB, `match_player_stats` 5,4 M 6,8 GB, `match_events` 9,8 M 5,6 GB, `match_team_stats` 6,4 M 1,35 GB, `matches` 1,49 M 3,0 GB): lettori `build_analytics_signals.py:376`, `build_inplay_intensity.py:88`, `value_engine/calibrate.py:37`, `market_intelligence/{backtest_audit,audit,edge_scorer}.py`, `football_data_scraper/backfill.py:102,147`; `matches` alimenta le transizioni di Omega/Mike (pg_cron 04:00 UTC).
- **G-043** **Atlante hazard** (`hazard_atlas`, `hazard_atlas_leghe`): scritto da `genera_atlante.py`, letto da Mike come FILE (`dossier.py:25-37` `load_hazard_atlas`, ricaricato se il file cambia, `hazard_atlas.py:130-144`): nessuna lettura cloud a runtime.
- **G-044** **P&L reale del conto**: `mike/regolato_conto.py:1-359`: funzioni pure su `listClearedOrders` Betfair; il servizio scrive `mike_trades` (righe «utente» `signal_key=utente-<bet_id>`); NON legge il cloud (le letture REST a ritmo sono in `mike/service.py:6144-6171`).
- **G-045** **Raccoglitori** (tab. 1.5): 10 workflow GitHub, 2 job pg_cron, 2 Edge Functions; quota API-Football in `api_quota.py` (14 riferimenti) + `api_call_log`.

(45 funzionalita'. Le 8 voci di §2.1 sono la parte di rete; G-009...G-032 sono le funzioni di accesso; G-033...G-045 gli algoritmi.)

---

## 3. DIFETTI STRUTTURALI

1. **Rete nel percorso critico del bot** (non nel percorso dell'ordine Betfair, che e' sul runner): (a) `insert_trade` sincrono con id restituito dal cloud (`mike/db.py:175-181`, `omega_db.py:75`, `bot_db.py:91`): senza rete non si apre/chiude una posizione; (b) `_minute_table`/`_empirical_table` RPC sincrone nel ciclo (`omega_service.py:1432,1444,1556,1565`) a ogni nuovo bucket di 5'; (c) letture di `*_control`/`requests`/`risk_rules`/`get_live_settings` a 1-2 s: 391 su 707,5 richieste/min (07 §4.2); (d) runner a timeout 120 s (`db_client.py:25-28`; `usa_timeout_bot` solo in 4 `main`).
2. **Cinque copie dello stesso accesso**: 90 coppie di funzioni gemelle fra 6 moduli, 36 nomi (`gemelle.tsv`); `enqueue_live_order`, `get_live_order_request(_by_ref)`, `get_live_order_mirror` al 99-100% (`mike/db.py:662-693` ~ `omega_db.py:634-697` ~ `bot_db.py:1003-1044`), `_now_iso` x15 coppie (`gemelle.tsv`), `_exec_retry` stream/tennis al 96% (`stream/db.py:44` ~ `tennis_db.py:63`), `fail_stale_processing` x3, `chiudi_proposta` 97% (`omega_db.py:411` ~ `bot_db.py:668`).
3. **Due client e quattro politiche di ritento** (§1.1): 142 + 71 `.execute()` senza ritento; il ritento «che sa riprovare» (`db_client.py:280`) non e' usato da nessun bot.
4. **Scritture non idempotenti**: 8 tabelle di log + trade con id del cloud (§1.1): un ritento duplica; `insert_trade` non e' ritentabile in sicurezza.
5. **Il DB come bus fra processi con polling**: ordini `betfair_live_order_requests` GET 202,3/min su 101 righe (07 §4.2, §7); `risk_rules` 164,7/min su 14 righe; esiste gia' il canale 127.0.0.1 (00 §5.4): il cloud e' ancora il REGISTRO e il canale un derivato.
6. **Cache gemelle con regole diverse**: Mike senza scadenza (`dossier.py:147`) contro Omega 6 h (`omega_service.py:106`) per la STESSA tabella `omega_ht_ft_transitions`; 2 cache, 2 punti di rilettura.
7. **Non sono distinguibili «dato non c'e'» e «cloud irraggiungibile»**: `ht_ft_rows` torna `[]` in errore (`mike/db.py:637-647`) mentre `omega_db.ht_ft_transitions` torna `None` (`:1055-1065`) e la cache di Omega lo distingue (`omega_service.py:1340,1364`): la copia di Mike perde la distinzione.
8. **Tabelle senza lettore o non definite**: 17 usate e non definite nei `.sql` tracciati (00 §3.4: `fixture_predictions`, `matches`, `match_*`, `standings`...: lo schema vive fuori dal repo, non ricostruibile); 32 definite e senza `.table()`; 21 senza riferimenti.
9. **`football_data_scraper` senza lancio automatico** e `match_odds` 20 GB (38% del cloud) senza liveness misurabile.
10. **Log append-only che crescono senza politica**: `scalper_activity` 93.068 righe/19 MB, `mike_activity` 14.931, `api_call_log` 2,75 M righe 515 MB; nessun `RotatingFileHandler` per i servizi (07 §5.2).

---

## 4. DOMANI

### 4.1 Principio e archivio locale (motivato con i numeri di `07` §6, §6.1)

Regola: il percorso stream -> cache -> decisione -> ordine -> specchio -> ladder **non attraversa mai la rete verso il DB**; lo stato vivo sta in memoria
e viene reso durevole su disco in locale; il cloud lo riceve dal POSTINO. Le letture del cloud per gli algoritmi restano (PARTE 2) ma FUORI dal ciclo di decisione.

**Scelta dell'archivio (misurata, 3.000 record da ~190 B, 3 ripetizioni, SSD NVMe, SQLite 3.49.1; `07` §6):**

| Modo | p50 | p99 | max | record/s | Crash del PROCESSO (500 scritti) | Spegnimento del PC |
|---|---:|---:|---:|---:|---|---|
| solo memoria | 15 us | 84-199 us | 5,8-12,7 ms | 33-46 k | 500 persi | tutto perso |
| log write+flush | 11 us | 108-119 us | 15-60 ms | 15-23 k | 0 persi | non garantito (cache SO) |
| log write+flush+fsync | 434-472 us | 9,7-37 ms | 0,24-0,89 s | 293-711 | 0 persi | garantito |
| SQLite WAL NORMAL, 1 commit/record | 52-54 us | 460-659 us | 0,70-0,96 s (checkpoint) | 1.086-1.228 | 0 persi | l'ultima transazione puo' sparire, DB integro (doc. SQLite) |
| SQLite WAL FULL, 1 commit/record | 593-629 us | 27,8-29,3 ms | 67-180 ms | 370-411 | 0 persi | durevole (ACID) |
| SQLite WAL NORMAL, 100/commit | 783-932 us per commit | 3-6,4 ms | 3-6,4 ms | 4.155-5.361 | 0 persi | come NORMAL |

Decisione proposta (la sceglie la misura, non la notorieta'): **due archivi, due regole**, ENTRAMBI scritti da UN thread di scrittura con coda in memoria, cosi' il
ciclo di decisione paga solo l'accodamento (~15 us, riga «solo memoria») e mai il disco:
1. **`stato_denaro` = SQLite WAL, `synchronous=FULL`** per le tabelle con transizioni di stato del denaro (T01 richieste ordini, T02 specchio, T03 posizioni/regolati,
   trade dei 4 bot, `risk_rules`, `betfair_live_settings`): sono pochi eventi (cloud: 101 richieste ordini in tutta la storia, 07 §7), FULL costa 0,6 ms p50 e 22,8 ms p95 sul THREAD DI SCRITTURA (fuori dal ciclo), e da' durabilita' anche allo spegnimento del PC. Il diario ordini esiste gia' con JSONL e fsync (`motore_ordini.py:20-30`, `02_COMPETITOR.md` r.357): si RIUSA, non si riscrive.
2. **`stato_vivo` = SQLite WAL, `synchronous=NORMAL`, commit a lotti** per le tabelle chiave-aggiornabili ad alta cadenza (ladder, `live_now`, heartbeat, `*_control` status, scanner): 53 us p50, 4-5 mila record/s a lotti da 100; il rischio di NORMAL (ultima transazione persa allo spegnimento) e' accettabile perche' ogni riga e' ri-derivabile dallo stream/dal prossimo giro.
3. **Log append-only con `write+flush`** (JSONL per giorno) per le tabelle ARC senza chiave (`*_activity`, `live_alerts`, `betfair_live_journal`, `betfair_live_audit`): 11 us, 15-23 mila record/s, nessuna perdita al crash del processo (prova 500/500); il POSTINO li legge con un OFFSET (il file E' la coda: niente doppia scrittura).
Non provato (dichiaro): spegnimento del PC; checkpoint di SQLite spostato su finestra a parte (il massimo 0,70-0,96 s di NORMAL e' il default, `07` §6, §«non misurato» 9-10); **due file separati** invece di uno per evitare che i checkpoint dell'uno blocchino l'altro. Misura che manca: `m06_lab_persistenza.py` con `wal_autocheckpoint` e due file concorrenti, e su disco sotto carico. WAL non funziona su filesystem di rete (doc. SQLite citata in `07` §6.1): il file va su disco locale (NVMe `C:`).
Rimane valido il confronto: «memoria + log» vince per velocita' e SQLite per interrogabilita'/ripresa: la scelta divisa sopra assegna a ciascuno la parte in cui vince.

### 4.2 Il POSTINO (asincrono, durevole, idempotente)

Contratto (`dati/postino.py`, UNA cartella `dati/` con `COSA_FA.md`):
```python
class Postino(Protocol):
    def accoda(self, tabella: str, op: Literal["upsert","insert","patch","delete"], chiave: str|None,
               riga: Mapping[str, Any], *, coalesce: bool = False) -> int: ...   # seq locale, stessa transazione dello stato
    def stato(self) -> StatoPostino: ...      # in_coda, eta_max_s, per_tabella, ultimo_errore, offline_da
    def drena(self, max_righe: int = 200) -> EsitoDrenaggio: ...   # un giro (thread dedicato)
    def riconcilia(self, tabella: str, da_ts: datetime) -> RapportoRiconciliazione: ...
```
- **Coda persistente**: tabella `outbox(seq PK AUTOINCREMENT, tabella, op, chiave, payload JSON, creato_ms, tentativi, prossimo_ms, stato)` NELLO STESSO SQLite dello stato e **nella stessa transazione** (outbox transazionale: stato e messaggio nascono insieme o non nascono). Per i log: offset del file JSONL.
- **Ripresa dopo rete assente**: backoff 2/4/8/16/32 s, tetto 60 s, **riuso** di `classifica_guasto_rete` (`db_client.py:228`) e dell'interruttore dopo 2 guasti (`:117`); in offline la coda cresce sul disco (`outbox` ~ 253-283 B/record, 07 §6) e `stato().offline_da` alimenta un allarme; al ritorno si drena in ordine di `seq`, per tabella a blocchi `UPLOAD_CHUNK` (`config_stream.py`), con riduzione del blocco su 57014 (`stream/db.py:26-37,579-628` gia' lo fa). Un errore NON transitorio (es. `CHECK` rifiutato, difetto 18 di `PROCESSO_STANDARD_BOT.md` §7) NON si ritenta in eterno: va in `dead_letter` con allarme visibile e conteggio (mai «warning»).
- **Coalescenza**: per le tabelle SV (`live_now`, `live_ladder`, heartbeat, `*_control` stato) la coda tiene SOLO l'ultima versione per chiave: meno scritture del cloud di oggi (heartbeat 7,4/min, ladder write-on-change a 2,0 s).
- **Idempotenza, tabella per tabella** (chiavi naturali gia' nel DB, `file:riga` delle migrazioni):
  - GIA' IDEMPOTENTI: `live_follow` `event_id` (`live_stream.sql`/`stream/db.py:164`); `live_markets` `(event_id,market_id)` (`live_stream.sql:85`); `live_ladder` `(event_id,market_id)` (`live_ladder.sql:56`); `live_now`, `live_signals`, `live_run_log` `event_id`; `betfair_live_order_requests` `client_ref UNIQUE` (`betfair_live_order_queue.sql:35`); `betfair_live_orders` `(mode,client_order_ref)` (`:116`); `betfair_live_positions` `(mode,market_id,selection_id,handicap)` (`:149`); `betfair_live_settled` `(mode,market_id)` (`betfair_live_pnl_journal.sql:38`); `betfair_live_risk_rules` `client_ref UNIQUE` (`betfair_live_risk_rules.sql:30`); `betfair_live_xhedge` event/mode (`betfair_live_xhedge.sql:17`); `betfair_live_heartbeat`/`risk_state`/`account` `id`; `omega_events`, `mike_events`, `safe_strategy_scan` `event_id`; `omega_market_snapshot` `market_id`; `omega_daily_goal` `day`; `tennis_live_*` (`tennis_live.sql:89`, `tennis_orders.sql:51` `client_ref UNIQUE`, `tennis_db.py:605,628,765,778`).
  - **Trade**: `mike_trades` unique parziale `(event_id, coalesce(signal_key,''))` solo per `origin='auto'` (`mike_bot.sql:114-116`); `omega_trades` unique parziali (`omega_models_v5.sql:223,233`); `safe_strategy_trades` `uq_safe_trades_signal_mode` (`safe_strategy_paper_live_2026-09-13.sql:195`) e `trade_by_idempotency_key` (`bot_db.py:245`). Le gambe MANUALI/di chiusura e l'id restituito NON hanno chiave: **serve un `trade_uid`** (decisione 1).
  - **MANCA LA CHIAVE** (insert su BIGSERIAL): `mike_activity`, `omega_activity`, `safe_strategy_activity`, `scalper_activity`, `tennis_bot_activity`, `live_alerts`, `betfair_live_journal`, `betfair_live_audit`, `signal_history`, `theta_confirm_requests`: serve una colonna `uid` (UUID generato nel punto di scrittura) con indice UNIQUE e `INSERT ... ON CONFLICT DO NOTHING` (migrazione che scrive il coordinatore e applica l'utente, `CLAUDE.md`).
- **Ritorno ai trade con id**: l'id locale (`trade_uid`) e' l'identita' del bot; l'`id` serial del cloud diventa un attributo di archivio.
- **Ripartenza/disaster**: se il disco locale e' perso, lo stato vivo si ricostruisce dal cloud (le tabelle SV/CMD restano mirror complete), con la finestra non drenata come unica perdita; per questo il ritardo massimo e' per-tabella (§4.3).

### 4.3 Tabella per tabella (§9.5 del brief del piano): proposta, ritardo massimo, verifica «non manca nulla»

Legenda proposta: **L+P** = memoria + archivio locale (denaro/vivo/log) + postino; **CMD-L** = comando sul canale locale + riga locale, cloud come mirror; **CACHE** = letto dal cloud con cache e precalcolo FUORI dal ciclo; **CLOUD** = resta solo cloud.
Verifica comune V1 = (a) `outbox` svuotata: `in_coda==0` e `eta_max_s` entro il ritardo; (b) controllo notturno `riconcilia(tabella, ieri)`: per ogni tabella confronto `count(*)` e `sum(hash(chiave||updated_at))` locale contro cloud sull'ultimo giorno; (c) watermark `seq` confermato senza buchi.

| Fam. | Proposta | Ritardo max cloud (proposta, da validare con l'utente) | Come si verifica che non manca nulla |
|---|---|---|---|
| T01 `betfair_live_order_requests` | **CMD-L** (canale `*_ORDINI_VIA_CANALE` + `stato_denaro` FULL); la coda cloud solo come mirror e come via della UI remota `request_betfair_live_order` | 0 ms in locale; mirror <= 5 s | V1 + `client_ref` unico: per ogni `client_ref` locale esiste una riga cloud con lo stesso stato finale; richieste cloud-only (UI remota) importate dal poll del postino (1/s, 1 query invece di 202/min) |
| T02 `betfair_live_orders` | **L+P** (`stato_denaro`), upsert `(mode,client_order_ref)` | <= 5 s | V1 + riconciliazione con `listCurrentOrders`/specchio (gia' `reconcile_worker`) |
| T03 positions/settled/risk_state/account/heartbeat/xhedge | **L+P**; heartbeat e account coalescenti | positions/settled <= 5 s; heartbeat/account <= 15 s | V1 + P&L reale (`regolato_conto`) giornaliero contro `betfair_live_settled` |
| T04 `betfair_live_risk_rules` | **L+P**: autorita' = locale (le regole nascono dalla UI desktop sul canale); mirror cloud | 0 ms; mirror <= 5 s | V1; decisione 2 per la modifica remota |
| T05 `get_live_settings` | **CACHE a 1 s FUORI dal ciclo** (poll di UNA riga in un thread, memoria nel bot) + «sveglia» locale: stesso ritardo d'oggi (<= ~1 s), 0 rete nella decisione | cloud->locale <= 1 s | test: kill switch dalla UI -> bot lo vede entro 1 s; cloud irraggiungibile: comportamento da decidere (decisione 3) |
| T06 `*_journal`, `*_audit`, `live_alerts`, `live_run_log`, `signal_history`, `theta_confirm_requests` | **L+P** log append-only con `uid` | <= 60 s | V1 + `uid` unico: conteggio per giorno e per `kind` |
| T07 `live_follow`, `personal_watchlist` | **L+P** (follow); watchlist **CLOUD+CACHE** (poll 120 s resta, `config_stream.py:129`) | follow <= 5 s | V1 |
| T08 `live_now`, `live_markets`, `live_ladder`, `live_signals` | **L+P coalescente** (display remoto): ladder 2,0 s come oggi; la UI desktop legge dal canale a 200 ms | 2,0 s (= `LADDER_PUBLISH_SEC`) | V1 (solo ultima versione: confronto della firma back/lay) |
| T09 Mike `mike_control`, `mike_requests` | **CACHE in memoria** aggiornata da «sveglia» (`svegliaBot`, `localChannel.ts:338`) + 1 poll/s di backstop (oggi 58+58/min a 1 s) | UI->bot <= 1 s | V1 + test: la richiesta scritta dalla UI e' lavorata una sola volta |
| T09 `mike_trades`, `mike_events` | **L+P** (`stato_denaro`/`stato_vivo`), `trade_uid` | <= 5 s | V1 + conteggio trade per modalita', P&L per giorno contro `get_mike_aggregates` |
| T09 `mike_activity` | **L+P** log con `uid` | <= 60 s | V1 |
| T10 Omega: `omega_control`, `omega_manual_requests`, `omega_missions` | come T09 (CACHE+sveglia) | <= 1 s | V1 |
| T10 `omega_trades`, `omega_events`, `omega_market_snapshot`, `omega_daily_goal` | **L+P** | <= 5 s | V1 + `get_omega_aggregates` |
| T10 `omega_activity` | **L+P** log | <= 60 s | V1 |
| T11 Safe: `safe_strategy_control`, `safe_strategy_requests`, `safe_strategy_status` | CACHE+sveglia; `requests` PATCH 19/min diventa transizione locale + mirror | <= 1 s | V1 |
| T11 `safe_strategy_trades`, `safe_strategy_opportunities`, `safe_strategy_scan` | **L+P**; `scan` coalescente per `event_id` (canale 47336 gia' attivo) | trades <= 5 s; scan <= 5 s | V1 + `get_safe_aggregates` |
| T11 `safe_strategy_activity` | **L+P** log | <= 60 s | V1 |
| T12 scalper | `*_control` CACHE+poll 3 s (`scalper_service.py:43` `POLL_S=3.0`); `scalper_activity` **L+P** log (+ politica di conservazione) | control <= 3 s; activity <= 60 s | V1 |
| T13 tennis | `tennis_live_*`, `tennis_live_order_queue`/`orders`/`positions`: come T01-T03 (**CMD-L**/**L+P**); `*_control`, `*_service_control`: CACHE+sveglia (47337); `tennis_bot_activity` log; `tennis_markets` **CLOUD** (tennis-odds, 0,1/min) | queue 0 ms; stato <= 5 s; log <= 60 s | V1 |
| T14 code manuali legacy (`betfair_order_requests`, `refresh_requests`, `betfair_market_odds`) | **CLOUD** (percorso manuale a bassissima frequenza, fuori dal ciclo; si valuta l'assorbimento quando i componenti A/E sostituiscono `order_worker`) | n/a | invariato |
| T15 backtest/replay/snapshot | **CLOUD** archivio (`live_market_snapshots` 2,4 GB, `tennis_replay_*`); scritti dal curatore in lotti (`insert_rows_resilient`) | n/a (lotti a fine partita) | conteggi per evento |
| T16 STA (`analytics_*`, `poisson_calibration`, `ml_post_calibration`, `ai_model_registry`, `bet_features`, `direction_pagella`, `engine_signals`, `personal_trades`) | **CLOUD** (calcolati dai workflow e serviti da RPC alla UI) | n/a | invariato; ultimo aggiornamento monitorato (§7) |
| T17 storico e statistiche (`matches`, `match_*`, `fixture_predictions`, `standings`, `injuries`, `top_*`, `api_*`, `season_backfill_state`) | **CLOUD** + CACHE locale per i soli algoritmi (§4.4) | n/a | invariato |

Le tabelle con `leads` (landing, `AuthSection.tsx:74`) e `fixture_detail_checks` restano CLOUD (nessun bot le tocca).

### 4.4 PARTE 2 - Gli algoritmi: dove vivono, con che cache, mai degradati

| Algoritmo | Proposta | Perche' (numeri) | Dato che deve restare IDENTICO |
|---|---|---|---|
| Modello di Mike pre-match (G-033) | **CACHE + precalcolo mattutino**: all'avvio dell'app e ogni ora (dopo `today_predictions_backfill` 02:18 UTC e `updated_at` fino alle 09:43) UNA query `fixtures_for_window` + `db_json_analisi`/`tactical_engine_json` per le partite delle prossime 24 h nella tabella locale `fixture_prematch`; `build_prematch` legge dalla tabella locale, con ripiego al cloud se manca la riga | oggi 3 letture a evento al primo aggancio; il precalcolo le toglie dal ciclo senza cambiare un valore | stesse colonne di `stream/db.py:231-262` e `omega_db.py:756`; parita' di `lambda_home/lambda_away/rho/p4_pre/p_under35_cal` per evento |
| `ht_ft_rows` Mike (G-034) e `_EMPIRICAL_CACHE` Omega (G-035) | **REPLICA LOCALE** di `omega_ht_ft_transitions`, rinfrescata dopo le 04:00 UTC (`built_at`); entrambe le cache leggono la replica; **si mantengono le regole attuali di scadenza per bot** (Mike mai, Omega 6 h): non si uniformano (strategia) -> decisione 4 | ricostruzione notturna unica: leggere piu' spesso non cambia i numeri se non dopo le 04:00 | righe `{league_id, ht, ft, n}` = quelle dell'RPC `get_omega_ht_ft` |
| `_MINUTE_CACHE` Omega (G-035) | **PREFETCH in background per lega** quando la partita entra nel perimetro del bot: tutti i bucket (FT 0..85 step 5 = 18, HT 0..40 = 9) x target; `_minute_table` legge SEMPRE dalla memoria -> **zero RPC sincrone nel ciclo**; la stessa TTL 6 h e la regola «errore non in cache» restano | il bucket cambia ogni 5' e oggi ogni cambio senza voce e' una RPC sincrona; `omega_minute_transitions` 1,08 M righe 270 MB: la replica completa e' possibile ma non necessaria (per lega sono poche righe) | righe `{league_id,bucket,score,target,result,n}` di `get_omega_minute_ft` |
| Omega: `market_frequency`, `fixtures_for_window`, `fixture_analysis` (G-036) | CACHE per giornata/evento, stessa query | letture rare | identico |
| `fixture_predictions` / `Prediction/` / `ai_engine` / `tactical_engine/serving` (G-037) | **CLOUD** (resta il motore notturno su GitHub Actions); il PC legge e mette in cache; i motori NON si portano in locale | 121.881 righe 1,06 GB, scritte alle 02:18-09:43 UTC | identico |
| `analytics_signals` (G-038) | **CLOUD** + RPC alla UI | 1,25 M righe, 730.319 UPDATE dal riavvio | identico |
| `value_engine`/`tactical_engine` live (G-039) | **gia' locali** (puri); nel modulo `modello/` condiviso | nessun accesso DB | identico |
| Scanner (G-040) | **L+P coalescente** + canale 47336 (gia' esistente) come via principale; la riga cloud serve a UI remota/archivio; schede e round letti con la stessa SELECT ma in cache giornaliera | 65,4 POST/min oggi | `scan_calcio`/`scan_tennis` identici per evento |
| `standings`, `injuries`, `top_*` (G-041), `match_*` (G-042) | **CLOUD**, raccoglitori invariati | 45 GB di storico; nessun lettore live | invariato |
| Atlante hazard (G-043) | file locale gia' cosi' | `load_hazard_atlas` | invariato |
| Raccoglitori (G-045) | **CLOUD/GitHub Actions**, invariati; **da aggiungere**: un controllo di liveness (max data per tabella, §7) e il lancio di `football_data_scraper` documentato | 10 workflow, 2 pg_cron | invariato |

Mai degradato: ogni riga della tabella mantiene le stesse colonne e le stesse scadenze; la replica e il prefetch sono equivalenti per costruzione e si dimostrano con il confronto riga per riga (§5).

### 4.5 Contratto unico del componente (`dati/`, UNA cartella)
```python
# dati/contratto.py (tipi)
Modo = Literal["paper", "live"]
class Archivio(Protocol):                                   # memoria + SQLite/log, mai la rete
    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Mapping[str, Any] | None: ...
    def scrivi(self, tabella: str, riga: Mapping[str, Any]) -> None: ...      # accoda al thread di scrittura + outbox, stessa transazione
    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool: ...  # claim atomico (richieste/ordini)
class Cloud(Protocol):                                      # UN solo client, UN timeout, UNA politica di ritento
    def leggi(self, tabella: str, filtri: Mapping[str, Any], *, cache_s: float = 0.0) -> list[Mapping]: ...
    def rpc(self, nome: str, args: Mapping[str, Any], *, cache_s: float = 0.0) -> Any: ...
class RegistroTabelle:                                      # dichiarativo: nome, chiave naturale, natura, modo, ritardo, coalesce
    def spec(self, tabella: str) -> SpecTabella: ...
```
Eventi esposti: `dati.postino_offline(da)`, `dati.dead_letter(tabella, riga, errore)`, `dati.riconciliazione(rapporto)`. Consumati: «sveglia» dal canale locale per le tabelle CFG.
La **registrazione di una tabella** e' UNA riga del registro (nome, chiave, natura, ritardo): la nuova tabella di un bot nuovo non richiede un nuovo modulo `*_db.py`.

### 4.6 Stima delle righe (calcolo)
Oggi: 7 moduli = 5.788 righe + 107 chiamate sparse (~6 righe ciascuna ~ 640) = **~6.430**.
Domani (stima, non misurata): `db_client.py` unificato (client unico, timeout unico, retry unico: assorbe `net_retry` 108 + `tennis_db.get_tennis_client`) ~450; `dati/archivio.py` (SQLite + log + thread di scrittura) ~450;
`dati/postino.py` ~400; `dati/registro.py` (spec di ~75 tabelle, 1 riga ognuna + intestazione) ~250; `dati/riconcilia.py` ~200; `dati/cache_cloud.py` (cache e precalcolo/prefetch di §4.4) ~300;
residui per dominio (RPC specifiche: aggregati `get_*_aggregates`, proposte, matcher) 6 x ~60 = ~360. **Totale ~2.400 righe**, cioe' **-63%**, non -80%: il -80% non e' raggiungibile nello strato dati perche' postino e archivio sono codice NUOVO (la riduzione viene dalle 5 copie: 90 coppie gemelle -> 1).
Cosa sparisce perche' ripetuto: `enqueue_live_order`/`get_live_order_*`/`runner_heartbeat`/`live_follow_status`/`_now_iso`/`_sb`/`fail_stale_processing`/`chiudi_proposta`. Cosa resta perche' e' strategia: nessuna regola di trading vive qui (le query di aggregato sono lettura).
Sostituire OGGI il cloud (es. con un altro Postgres) tocca: 6 moduli + 107 punti sparsi + `db_client.py` (118 file importano `get_supabase_client`); DOMANI: solo `dati/cloud.py` e i suoi test di contratto.
Cosa e' gia' in una libreria matura e oggi e' riscritto: ritento con backoff (`stream/net_retry.py:78`, `db_client.py:280`) -> `tenacity`/`httpx` transports retry; coda persistente -> SQLite con tabella outbox (gia' in stdlib, nessuna dipendenza nuova); client PostgREST -> `supabase-py` gia' usato (resta).

---

## 5. PARITA'

- **Dati identici (PARTE 2)**: per ogni algoritmo un test di contratto «replica = RPC»: stesso `league_id` -> stesse righe `get_omega_ht_ft` / `get_omega_minute_ft` (confronto riga per riga contro il cloud), stesso `fixture_id` -> stessi `lambda_home/away`, `rho`, `p4_pre`, `p_under35_cal` (`mike/dossier.py:66-111`).
- **Replay del banco**: `python -m Betfair.stream.backtest.certifica <bot> ...` con il DB finto delle certificazioni gia' esistente (`Betfair/omega/tools/replay_registrazioni.py:252,634-643` finge `ht_ft_transitions`/`minute_transitions`): il test e' che il finto alimentato dalla REPLICA locale produca lo STESSO referto, numero per numero (decisioni, ordini, importi, istanti, P&L), sulle registrazioni `registrazioni_banco/` (2 partite, 4,9 MB) e `_live_raw/` (67 partite, 4,26 GB; 39 con raw per il calcio).
- **Scritture identiche (PARTE 1)**: periodo «ombra»: la vecchia scrittura diretta resta; il postino scrive le STESSE righe sulle stesse chiavi; confronto automatico notturno per tabella (`riconcilia`): `count`, hash `(chiave, updated_at)`. Per le tabelle senza chiave (log): conteggio per `(giorno, kind, event_id)` +/- 0.
- **Falsificazione obbligatoria (`CLAUDE.md`)**: ogni test nuovo va reso rosso: (1) togliere il flush -> il test di crash (processo ucciso a meta') ritrova meno record; (2) rimuovere il `uid` -> il ritento duplica una riga di `mike_activity` e il test lo vede; (3) cache senza scadenza -> il test del cambio di notte alle 04:00 UTC fallisce; (4) cloud fermo -> `insert_trade` locale riesce e la coda cresce; (5) riga rifiutata da un `CHECK` -> finisce in `dead_letter` e non in un warning.
- **Voci coperte di `PROCESSO_STANDARD_BOT.md`**: §6.5 «Persistenza e UI» (colonne vere delle migrazioni, attivita' scritte per decisione; i finti del postino hanno le identiche chiavi e tipi del vero: §7 difetto 27), §6.6 «Concorrenza e limiti» (piu' partite insieme: scrittore unico con coda), §6.3 «Il servizio intero» (riavvio con stato su disco: difetto 19 «stato in RAM perso al riavvio»; difetto 22 «bot che riparte da solo»), §6.8 «Referto e riproducibilita'». §7 difetti toccati: 18 (scrittura fallita declassata a warning), 19, 21 (paper e live non si sommano mai: `mode` e' parte della chiave in ogni tabella locale), 23 (stats riscritte per intero), 24 (RPC `*_activate` con `coalesce`), 27-30 (finti e falsificazione).
- Fotografie UI: pannelli Control Room (`useControlRoom.ts:1514,1750,1795`), Mike/Omega/Safe (`useMike.ts:292`, `Omega.tsx:233`, `useSafeBot.ts:387`) identici con cloud acceso, spento e riacceso (la UI legge dal canale locale; i numeri devono coincidere dopo il drenaggio).

---

## 6. MIGRAZIONE

Ordine: (0) **misure prima** (§7: `m04_chiamate_db.py` ad app accesa; latenza di UNA query vera e delle RPC `get_omega_*`; `m06` con due file e checkpoint) - perche' diversi numeri di §4 sono stime; (1) **client unico** (`db_client.py` con timeout/retry per profilo): cambia SOLO la politica di errore, nessun dato; (2) **registro delle tabelle + `riconcilia` in sola lettura** (nessuna scrittura nuova: misura quanto oggi «manca» fra cloud e le fonti); (3) **cache/prefetch di Omega/Mike** (§4.4: l'unico passo che tocca letture nel ciclo; interruttore per bot, ombra: la replica risponde e CONFRONTA con l'RPC, serve ancora l'RPC); (4) **postino + `stato_vivo`** per le tabelle ARC/log (rischio minimo: nessuna decisione le legge); (5) **`stato_denaro` + postino** per T01-T04 e trade, un bot per volta (Mike, poi Omega, Safe, tennis), con il banco `certifica` verde prima e dopo; (6) **poll di controllo -> sveglia + cache** (T05, `*_control`); (7) taglio delle vecchie scritture dirette, ultimo.
Prerequisiti dell'utente: migrazione `uid` per 10 tabelle di log e `trade_uid` per le 3 tabelle di trade (decisione 1); nessun processo nuovo senza permesso (il thread di scrittura e il postino stanno DENTRO i processi esistenti: nessun processo aggiunto).
Rischi: (a) divergenza locale/cloud: mitigata da `riconcilia` notturno e dal watermark; (b) crescita della coda in offline lungo: allarme e tetto di disco; (c) config cloud->locale che ritarda un kill switch: decisione 3; (d) due file SQLite: da misurare; (e) dipendenza dalla notte alle 04:00 UTC: il prefetch deve rileggere dopo `built_at`.
Ritorno indietro: ogni passo dietro un interruttore per bot (come `*_CANALE`, 00 §5.4); la vecchia scrittura diretta resta fino al passo 7; il cloud e' sempre completo grazie al periodo ombra.
Rispetto agli altri componenti: dipende da A (connessione) solo per il canale; PRECEDE i componenti dei bot (Mike, Omega, Safe, tennis: contratto `stato`/`ordini`) perche' sono loro a usare `Archivio`.

---

## 7. MISURE

| Cosa | Prima (fonte) | Obiettivo dopo | Strumento |
|---|---|---|---|
| Richieste al cloud, totale | 1.309/min stream attivo (04/10); 707,5/min 08/10 (07 §4.1) | controllo/coda: 391 -> ~60 (1 poll/s per kill switch + ~4 poll di backstop); archivio in lotti: -60% scritture per coalescenza (stima, da misurare) | `m04_chiamate_db.py ../../../_logs <sessione>` |
| Richieste coda ordini | 202,3/min GET su 101 righe (07 §4.2, §7) | 60/min (1/s, solo UI remota) o 0 con canale | idem |
| Cloud nel ciclo del bot | RPC sincrona a ogni bucket (G-035); `insert_trade` sincrono | **0** richieste di rete nel ciclo di decisione/ordine | test: server di rete finto che rifiuta tutto; il banco deve restare identico |
| Latenza scrittura stato denaro nel ciclo | `insert_trade` = giro di rete (>= 21,3 ms p50 senza query, 07 §4.3; 92-307 ms storico NON di oggi) | accodamento ~15 us (07 §6 «solo memoria»); durabilita' FULL sul thread di scrittura (p50 0,6 ms, p95 22,8 ms) | `m06_lab_persistenza.py` esteso |
| Perdita in crash del processo | uno stato in RAM (difetto 19) | 0 record (prova 500/500) | prova `os._exit` |
| Righe dello strato dati | ~6.430 | ~2.400 (-63%) | `wc -l`, `git ls-files` |
| Ritardo cloud, ordini | 0 (sincrono) | <= 5 s | `stato().eta_max_s` |
| Liveness raccoglitori | solo a mano | max data per tabella controllata ogni giorno (query di §1.5) | SELECT `max(updated_at)` per tabella (esclusi i 6 giganti: usare indice o `pg_stat`) |
| Memoria della coda | non esiste | outbox <= 253-283 B/record x dimensione di una notte offline | `m05b_campiona_processi.ps1` |
| Cloud h24: richieste/giorno | proiezione grezza 1,02 M (08/10) - 1,88 M (04/10), NON misura di un giorno (07 §4.2) | da misurare; obiettivo -80% sul traffico di coda/controllo | un giorno intero con `m04` |

---

## DECISIONI PER L'UTENTE

1. **Migrazione per l'idempotenza**: aggiungere una colonna `uid UUID UNIQUE` a 10 tabelle di log (`mike_activity`, `omega_activity`, `safe_strategy_activity`, `scalper_activity`, `tennis_bot_activity`, `live_alerts`, `betfair_live_journal`, `betfair_live_audit`, `signal_history`, `theta_confirm_requests`) e `trade_uid` alle 3 tabelle di trade, con `ON CONFLICT DO NOTHING`. Senza, il postino non puo' ritentare senza duplicare. (La migrazione la scrive il coordinatore e la applica l'utente.)
2. **Autorita' della configurazione**: oggi la UI scrive le `*_control` sul cloud (RPC `*_activate`, 164 chiamate RPC dal frontend) e i bot la rileggono. Proposta: locale = autorita' per le modifiche dalla UI desktop (sveglia sul canale), cloud = mirror. Serve sapere se l'utente modifica MAI i bot da un dispositivo senza il PC (se si', il cloud deve restare autorita' e il poll di backstop a 1 s e' obbligatorio).
3. **Kill switch con cloud irraggiungibile**: oggi `get_live_settings` fallito -> comportamento in `live_order_worker.py:498` (non letto riga per riga per questo caso). Proposta: ultimo valore noto in memoria + allarme dopo N secondi; e' una scelta di sicurezza, non la prendo io.
4. **Scadenze delle cache gemelle** (Mike mai, Omega 6 h sulla STESSA tabella): le tengo diverse (strategia intoccabile). Se l'utente vuole uniformarle e' una decisione sua.
5. **Conservazione**: `scalper_activity` 93.068 righe, `api_call_log` 2,75 M righe, `live_market_snapshots` 2,4 GB senza politica di scarto: decidere se archiviare/ruotare (nessuna tabella persa).
6. **Due file SQLite** (denaro FULL / vivo NORMAL): scelta da confermare dopo la misura mancante.

## COSA HO VERIFICATO DI PERSONA

- Lette per intero `db_client.py:1-200` e indice `:200-410`; `net_retry.py:78-108`; i `get_supabase`/`create_client` con `git grep` e `sed`; indici delle funzioni dei 6 moduli (`grep -n "^def "`);
  `omega_service.py:1305-1380, 1426-1434` e `omega_db.py:1040-1081, 736-776`; `mike/dossier.py:1-175`, `mike/db.py:618-650`; `stream/db.py:1-110, 231-262`; `safe_strategy/db.py:159-190`;
  i `unique`/`create table` delle migrazioni citate (`grep -n`, `sed`); i workflow (`grep cron`/`workflow_run`).
- SELECT in sola lettura (08/10): colonne data di 24 tabelle da `information_schema`; `max(data)` di 21 tabelle (tab. 1.5); `cron.job` (2 job attivi). Nessuna scrittura.
- Controllato a campione contro il codice 3 righe di `00_INVENTARIO.md` §3.2 (`mike/db.py:683`, `omega_db.py:674`, `bot_db.py:1029` -> `enqueue_live_order`: confermati) e i numeri di `07` §6 (tabella del laboratorio ripresa cosi' com'e').

## COSA NON HO POTUTO VERIFICARE

- `max(updated_at)` di `match_odds`, `match_events`, `match_lineups`, `match_team_stats`, `match_player_stats`: **timeout** (statement 8 s) in 2 tentativi: la liveness dei raccoglitori che li scrivono e' dedotta dal workflow e dalle altre tabelle, non misurata.
- Latenza di UNA query vera dell'app (chiave in `.env`, segreto) e delle RPC `get_omega_ht_ft`/`get_omega_minute_ft`: non misurate (07 §4.3).
- Spegnimento del PC, checkpoint di SQLite spostato, due file concorrenti (07 §6, punti 9-10): non provati.
- Se i 7 workflow GitHub sono ATTIVI sul repository remoto (non ho usato `gh`): uso l'evidenza delle date nelle tabelle.
- L'esito dell'invio Telegram di `make-daily-post` e i lettori SQL di `standings/injuries/top_*` (funzioni del DB non nel repo).
- Il comportamento del runner con `get_live_settings` fallito (`live_order_worker.py:498`) non letto per intero; la causa del calo di Mike 04/10->06/10 (07 §4.2) non verificata.
- Le stime di §4.6 e §7 («obiettivo dopo») sono proiezioni di progetto, non misure.
