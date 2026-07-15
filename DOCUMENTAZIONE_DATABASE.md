# Documentazione Database — python-database-automation

**Data censimento: 2026-07-15** (sostituisce integralmente la versione precedente che documentava solo 12 tabelle).

**Metodo di censimento:**
- Enumerazione completa tabelle/colonne via endpoint OpenAPI PostgREST (`{SUPABASE_URL}/rest/v1/` con service key) → **90 tabelle/viste esposte + 115 RPC**.
- Scala righe stimata con `Prefer: count=estimated` (fallback `count=planned` per le tabelle che vanno in timeout). Le cifre sono **stime dal planner Postgres**, non count esatti.
- Campione `select * limit 1` sulle tabelle non ovvie per verificare il contenuto reale.
- Incrocio con `migrations/*.sql` (RLS, realtime, definizioni viste) e grep dei riferimenti nel codice per capire chi scrive/legge.
- Fonti non-DB: bucket Storage Supabase, directory dati locali, GitHub Actions (sezione finale).

Legenda scala: k = migliaia, M = milioni. "Scrive/Legge" indica i moduli principali trovati nel codice (non esaustivo per il frontend, che legge quasi tutto via RPC).

---

## 1. Dati calcio storici (ingestion API-Football)

Il nucleo storico. Scritto dagli script di backfill in radice (`league_orchestrator.py`, `per_fixture_backfill.py`, `daily_yesterday_backfill.py`, `leagues_mapper.py`, `*_backfill.py`) e dalle GitHub Actions giornaliere. Letto da: Ai Engine (training ML), Prediction, tactical_engine, market_intelligence, strategy_no4, frontend.

| Tabella | Scopo | Colonne chiave | Righe (stima) |
|---|---|---|---|
| `matches` | Anagrafica partite: risultato FT/HT/ET/rigori, stato, venue | `fixture_id` (PK), `league_id`, `season_year`, `fixture_date`, `status_short`, `goals_home/away`, `halftime_home/away`, `raw_json` | **1.47M** (~1.38M con status FT) |
| `match_events` | Eventi match: gol, cartellini, sostituzioni, VAR — **con minuto** | `fixture_id`, `team_id`, `player_id`, `event_type`, `detail`, `minute`, `minute_extra` | **9.8M** (~2.69M eventi `Goal`) |
| `match_lineups` | Formazioni: titolari, panchina, allenatori, griglia tattica | `fixture_id`, `team_id`, `player_id`, `position`, `grid`, `is_starter` | **25.8M** |
| `match_odds` | Quote bookmaker pre-match da API-Football | `fixture_id`, `bookmaker_id`, `market_key`, `label`, `odd_value`, `snapshot_time` | **82.4M** (la tabella più grande) |
| `match_player_stats` | Statistiche individuali per giocatore/match (tiri, passaggi, duelli, rating) | `fixture_id`, `player_id`, `minutes`, `rating`, `shots_*`, `goals_total` | **5.6M** |
| `match_team_stats` | Statistiche squadra per match in formato long (possesso, xG, tiri) | `fixture_id`, `team_id`, `stat_type`, `value_text`, `value_numeric` | **6.5M** |
| `standings` | Classifiche per lega/stagione/girone | `league_id`, `season_year`, `rank`, `team_id`, `points`, `form` | **98k** |
| `injuries` | Infortuni/squalifiche per fixture | `fixture_id`, `player_id`, `team_id`, `type`, `reason` | **157k** |
| `top_scorers` | Capocannonieri per lega/stagione (con minuti giocati, rigori) | `league_id`, `season_year`, `player_id`, `goals_total`, `games_minutes`, `penalties_*` | **86k** |
| `top_assists` | Migliori assist-man per lega/stagione | come sopra + `goals_assists` | **28.5k** |
| `top_cards` | Più sanzionati per lega/stagione | come sopra + `card_type`, `yellow_cards`, `red_cards` | **216k** |
| `fixture_predictions` | Pronostici API-Football + output motori interni. Molto più ricca di quanto documentato in passato: contiene `model_predictions_json` (ML), `db_json_analisi`, `ht_predictions`, `tactical_engine_json`, `raw_json_odds` e i campi risultato/hit (`result_*`, `hit_winner`, `hit_under_over`, `evaluated_at`) | `fixture_id` (PK), `percent_home/draw/away`, `advice`, `under_over_line`, `goals_home_line/away_line` | **91.7k** |

Scrive: backfill radice + Actions. Legge: `Ai Engine/` (feature building), `Prediction/`, `tactical_engine/`, `market_intelligence/`, `strategy_no4/`, `frontend/`, `Betfair/` (matching fixture↔evento Betfair).

---

## 2. Copertura, orchestrazione e log ingestion

| Tabella | Scopo | Colonne chiave | Righe | Chi scrive / chi legge |
|---|---|---|---|---|
| `api_coverage_by_season` | Copertura dichiarata dall'API per lega/stagione (flag events/lineups/stats/odds/predictions) | `league_id`, `season_year`, flag booleani | 8.3k | Scrive `leagues_mapper.py`; legge `league_orchestrator.py`, `per_fixture_backfill.py` |
| `api_coverage_by_season_v2_mv` | **Materialized view**: copertura REALE misurata contando le righe in DB (events_fixtures, lineups_fixtures, ecc.) — più affidabile della v1 | `league_id`, `season_year`, `matches_count`, `*_fixtures`, `ok_*` | 726 | Refresh via RPC `refresh_api_coverage_by_season_v2_mv` |
| `league_season_riepilogo_popolamento` | Vista riepilogo: copertura + stato backfill (`season_status`, `season_last_run_at`, `fixtures_in_matches`) | come api_coverage + stato | 8.3k | Solo lettura (vista su api_coverage_by_season) |
| `season_backfill_state` | Stato di avanzamento del backfill per lega/stagione con `stats_json` dettagliato | `league_id`, `season_year`, `status`, `stats_json` | 8.2k | Scrive `league_orchestrator.py`; legge `training_planner.py`, `retrain_all_leagues.py` |
| `missing_fixture_coverage` | Vista: fixture con dati mancanti (events/lineups/stats/odds) | `fixture_id`, `missing_*` | ~8.3k (planned) | RPC `fetch_missing_fixture_coverage` |
| `missing_fixture_coverage_mat` | Versione materializzata della precedente | idem | 135 | idem |
| `api_call_log` | Log di ogni chiamata API-Football (endpoint, durata, esito, retry) | `endpoint`, `status`, `duration_ms`, `created_at` | **3.0M** | Scrive `logger.py`; diagnostica |

---

## 3. Motori, segnali e analytics (pipeline pronostici → scommesse)

Il cuore del sistema di valutazione motori (poisson, ml, tacticai, google_sheets…).

| Tabella | Scopo | Colonne chiave | Righe | Chi scrive / chi legge |
|---|---|---|---|---|
| `engine_signals` | **Tabella unificata segnali emessi/scartati** per motore×fixture×mercato: prob calibrata, edge, score, odds, status PLACED/REJECTED, esito, PnL, CLV, concordanza tra motori | `signal_uid` (PK), `engine`, `fixture_id`, `market`, `prob_calibrated`, `edge`, `status`, `reject_filter`, `result`, `pnl`, `clv`, `concordant` | 66.5k | Scrive pipeline giornaliera + `migrations/backfill_engine_signals.py`, `merge_engine_signals.py`; legge `/analytics` frontend, script `_certify_*` |
| `analytics_decisions` | Decisioni storiche per decision_logic (google_sheets ecc.): sorgente originaria confluita in engine_signals | `decision_uid`, `decision_logic`, `engine`, `status`, `pnl` | 66.5k | Scrive pipeline storica; letto da merge/certify |
| `analytics_signals` | Segnali grezzi per motore con contesto frequenza/ritardo (freq_baseline, delay_current) + esito e **first_goal_minute** | `signal_uid`, `engine`, `market`, `prob`, `freq_*`, `delay_*`, `hit`, `ht_home/away`, `first_goal_minute` | **300k** | Scrive pipeline; arricchito da `enrich_analytics_snapshots.py`, `_enrich_storico_all.py` |
| `analytics_bets` | **Tabella performance** (ex-vista, materializzata come tabella per scala): una riga per fixture×mercato×selezione con prob dei 3 motori, consenso, esito, `first_goal_minute`, quote betfair/book | `fixture_id`, `market`, `selection`, `poisson_prob`, `ml_prob`, `tacticai_prob`, `consensus_prob`, `hit`, `total_goals`, `ht_*`, `first_goal_minute` | **201k** (~90k con first_goal_minute valorizzato) | Rebuild via RPC `refresh_analytics_bets(_range)`; legge motore strategie `/analytics` |
| `bet_features` | **Vista** su analytics_bets arricchita con feature Poisson: `lambda_home/away/tot`, `lambda_1h_tot`, `dc_rho`, `ht_ratio_home/away`, `league_total_avg`, forma squadre | come analytics_bets + λ | 201k | Definita in `migrations/analytics_features.sql`; letta da `_engine_grid.py`, `_scorer.py`, `_segment_miner.py`, `_stack_eval.py` |
| `book_odds_cache` | Quota bookmaker canonica per fixture×mercato×selezione (cache per join veloci) | `fixture_id`, `market`, `selection`, `odd` | **308k** | Rebuild con analytics_bets |
| `analytics_prob_staging` | Staging upsert probabilità (flush via RPC `flush_analytics_prob_staging`) | `signal_uid`, `prob` | 0 (transiente) | Pipeline |
| `analytics_snap_staging` | Staging snapshot frequenza/ritardo (flush via RPC) | `fixture_id`, `market`, `freq_*` | 0 (transiente) | `enrich_analytics_snapshots.py` |
| `signal_history` | Storico segnali "track" legacy (poisson/ml) con PnL e CLV | `signal_id`, `track`, `market`, `result`, `pnl`, `clv` | 5.2k | Scrive Betfair report manager |
| `strategies` | Strategie salvate dall'utente nel motore strategie (filtri JSON) | `id`, `name`, `filters` | 2 | RPC `save_strategy`/`run_strategy`; frontend |
| `direction_pagella` | Pagella direzionale: hit-rate per motore×mercato×selezione×lega×bucket di probabilità vs base rate | `engine`, `market`, `selection`, `league_id`, `prob_bucket`, `hit_rate`, `base_rate` | 5.7k | Scrive `build_direzione.py`; RPC `get_direction*` |
| `v_es_emission_by_engine_market` | Vista: emissioni placed/rejected per motore×mercato | — | 32 | Definita in `engine_signals.sql` |
| `v_es_reject_funnel` | Vista: funnel dei motivi di scarto per motore | — | 8 | idem |
| `v_es_concordance_roi` | Vista: ROI per concordanza tra motori | — | 6 | idem |
| `v_roi_by_track`, `v_roi_by_market`, `v_clv_summary` | Viste ROI/CLV su signal_history (legacy) | — | ~0 | `signal_history.sql` |

Note: `analytics_*`, `engine_signals`, `strategies` hanno RLS con lockdown anon (`security_lockdown.sql`: RPC revocate ad anon → 401).

---

## 4. ML e calibrazione

| Tabella | Scopo | Colonne chiave | Righe | Chi scrive / chi legge |
|---|---|---|---|---|
| `ai_model_registry` | Registro modelli ML per lega×target: puntatore al bucket Storage, metriche (accuracy, logloss, brier), `calibration_cells` | `league_id`, `target`, `model_name`, `storage_bucket`, `storage_path`, `brier` | 20.5k | Scrive `retrain_all_leagues.py` (Action `retrain_models.yml`); legge Ai Engine serving |
| `model_performance` | Metriche di validazione per lega×target (brier, BSS, ECE, righe train/val) | `league_id`, `target`, `brier`, `bss`, `ece` | 20.5k | idem; legge `validate_models.yml` |
| `ml_post_calibration` | Correzioni post-calibrazione ML per lega (JSON `corrections`) | `league_id`, `corrections`, `min_n` | 934 | Scrive `compute_ml_post_calibration.py` (Action `ml_calibration.yml`) |
| `poisson_calibration` | Correzioni calibrazione Poisson per lega (JSON per selezione×bucket) | `league_id`, `corrections`, `min_n` | 495 | Scrive `poisson_calibrator.py` / `load_poisson_calibration_to_db.py` (Action `weekly_poisson_calibration.yml`); legge `generate_dynamic_cal.py` |

---

## 5. Quote Betfair pre-match (calcio + tennis)

| Tabella | Scopo | Colonne chiave | Righe | Chi scrive / chi legge |
|---|---|---|---|---|
| `betfair_market_odds` | Snapshot quote Betfair full-depth per fixture×mercato×selezione (ladder back/lay JSON) | `fixture_id`, `market_name`, `selection`, `back`, `lay`, `market_id`, `run_date` | **73k** | Scrive `betfair_full_odds.py` + worker `Betfair/odds_refresh.py`; legge strategy_no4, watchlist, RPC `get_betfair_full_odds` |
| `betfair_order_requests` | Coda ordini pre-live (legacy, sostituita dalla coda live) | `client_ref`, `fixture_id`, `side`, `price`, `size`, `status` | 2 | `Betfair/order_worker.py` |
| `betfair_refresh_requests` | Coda richieste refresh quote per fixture | `fixture_id`, `status` | 6 | `Betfair/refresh_worker.py`; RPC `request_betfair_refresh` |
| `tennis_markets` | Quote tennis pre-match: match odds + full_odds multi-mercato per evento | `event_id`, `market_id`, `competition_name`, `player1/2` (ladder JSON), `full_odds`, `run_date` | 192 | Scrive `betfair_tennis_odds.py`; RPC `get_tennis_fixtures/full_odds` |

---

## 6. Live stream calcio (registrazione + follow in-play)

Migrazione: `live_stream.sql` (+ `live_ladder.sql`, `live_signals.sql`, `live_alerts.sql`, `live_backtest.sql`). Scrittori: workers in `Betfair/stream/` (`raw_listener.py`, `recorder.py`, `curator.py`, `board_worker.py`). Realtime abilitato su quasi tutte (publication `supabase_realtime`); lettore principale: frontend (terminal live).

| Tabella | Scopo | Colonne chiave | Righe |
|---|---|---|---|
| `live_follow` | Eventi calcio seguiti live (pilotata da watchlist, `watchlist_follow_live.sql`) | `event_id`, `fixture_id`, `watchlist_id`, `status`, `error_detail` | 28 |
| `live_now` | Stato corrente per evento: minuto, punteggio, board mercati (JSON `state`) | `event_id`, `minute`, `score_home/away`, `state` | 26 |
| `live_markets` | Catalogo mercati per evento seguito | `event_id`, `market_id`, `market_type`, `selections` | 533 |
| `live_market_snapshots` | **Snapshot ladder full-depth con timestamp e minuto** (replay/backtest) | `event_id`, `market_id`, `ts`, `minute`, `inplay`, `ladder` (JSON per selection) | **1.07M** |
| `live_ladder` | Ultimo ladder per mercato (vista corrente, non storico) | `event_id`, `market_id`, `ladder`, `status` | 405 |
| `live_score_timeline` | Timeline punteggio con timestamp (fonte betfair/api) — **minuti-gol osservati live** | `event_id`, `ts`, `minute`, `score_home/away`, `event_type`, `payload` | 2.7k |
| `live_signals` | Segnali del modello live per evento (JSON `signals` con fair/direction) | `event_id`, `signals`, `model_meta` | 26 |
| `live_run_log` | Log di ogni registrazione: file raw locale, bytes, n. snapshot, fallback | `event_id`, `raw_file_path`, `raw_bytes`, `n_snapshots` | 26 |
| `live_alerts` | Alert operativi (kill-switch, modalità ordini, errori) con ack | `level`, `code`, `message`, `acknowledged` | 281 |
| `live_backtest_requests` / `live_backtest_results` | Coda backtest sul registrato + risultati aggregati (ROI, drawdown) | `params` / `scope`, `n_bets`, `roi`, `total_pnl` | 2 / 24 |

Nota: i tick grezzi completi NON sono in DB — stanno in `_live_raw/` locale (vedi Fonti non-DB); `live_market_snapshots` è la versione curata caricata da `curator.py`.

---

## 7. Live trading Betfair (denaro reale/paper) — `betfair_live_*`

Migrazioni: `betfair_live_controls.sql`, `betfair_live_order_queue.sql`, `betfair_live_pnl_journal.sql`, `betfair_live_risk_rules*.sql`, `betfair_live_account_heartbeat.sql`, `betfair_live_xhedge.sql`, `betfair_live_dutch_cashout.sql`, `betfair_live_greenup.sql`. Tutte con RLS owner-only (`betfair_live_is_owner`). Scrittore: `Betfair/live_order_worker.py` + `reconcile_worker.py` + `daily_stop_worker.py`; frontend opera via RPC (`request_betfair_live_order`, `set_live_kill_switch`, …).

| Tabella | Scopo | Righe |
|---|---|---|
| `betfair_live_settings` | Impostazioni globali: kill_switch, limiti esposizione, daily loss limit | 1 |
| `betfair_live_account` | Saldo disponibile + esposizione (heartbeat account) | 1 |
| `betfair_live_heartbeat` | Heartbeat worker + watchdog (pid, ts) | 1 |
| `betfair_live_order_requests` | Coda comandi ordini (place/cancel/replace) con esito | 99 |
| `betfair_live_orders` | Ordini reali/paper: bet_id, matched/remaining/voided, prezzo medio | 88 |
| `betfair_live_positions` | Posizioni per selezione: worst/matched if win/lose, esposizione | 1 |
| `betfair_live_risk_rules` | Regole di rischio armate (stop-loss, trailing, cash-out, green-up, dutch) | 14 |
| `betfair_live_risk_state` | Stato limite perdita giornaliera (realized + open MTM vs limit) | 1 |
| `betfair_live_settled` | Mercati liquidati con profit | 8 |
| `betfair_live_journal` | Giornale operativo: ogni azione con contesto (minuto, score, ltp, book) | 45 |
| `betfair_live_audit` | Audit trail API (azione, esito, errori) | 96 |
| `betfair_live_xhedge` | Analisi cross-hedge per evento (JSON) | 7 |

---

## 8. Scalper calcio

Migrazione `scalper_bot.sql`. Scrittore: bot scalper in `Betfair/`; frontend via RPC `scalper_activate`/`scalper_stop`/`get_scalper_state`.

| Tabella | Scopo | Righe |
|---|---|---|
| `scalper_control` | Controllo per evento: status, mode (maker/taker), stake, params JSON (ht_mode, min_flow, price_max…), stats (scalps, flattens, pnl), heartbeat | 6 |
| `scalper_activity` | Log attività ad alta frequenza (info/tick/ordini) per evento | **102k** |

---

## 9. Tennis (follow live, ordini, bot)

Migrazioni: `tennis_live.sql`, `tennis_markets.sql`, `tennis_orders.sql`, `tennis_bots.sql` (+ `tennis_bots_arm_guard.sql` — **da applicare** secondo le note di progetto). RLS owner-only (`tennis_is_owner`), realtime su tennis_live. Scrittori: worker tennis in `Betfair/`; frontend via RPC (`tennis_follow_event`, `tennis_bot_arm/disarm`, `request_tennis_live_order`).

| Tabella | Scopo | Righe |
|---|---|---|
| `tennis_live_follow` | Match tennis seguiti live (competition, player1/2, stato) | 9 |
| `tennis_live_now` | Stato corrente: board mercati, score, punti (JSON) | 8 |
| `tennis_live_ladder` | Ultimo ladder per mercato | 7 |
| `tennis_live_order_queue` | Coda comandi ordini tennis (payload JSON) | 12 |
| `tennis_live_orders` | Ordini tennis (schema identico a betfair_live_orders) | 6 |
| `tennis_live_positions` | Posizioni per selezione | 1 |
| `tennis_refresh_requests` | Coda refresh quote per evento | 0 |
| `tennis_bot_control` | Controllo bot per evento×bot_key (armed/disarmed, stake, params, heartbeat) | 1 |
| `tennis_bot_activity` | Log attività bot | 2 |

---

## 10. Omega (bot Correct Score / missioni €250)

Migrazioni: `omega_bot.sql`, `omega_manual.sql`, `omega_missions.sql`. Scrittore: `Betfair/omega/` (`omega_service.py`, `omega_db.py`, `omega_engine.py`); frontend via RPC (`omega_activate`, `omega_mission_*`, `get_omega_*`). Realtime abilitato. Tabelle quasi vuote: bot in fase paper/appena avviato.

| Tabella | Scopo | Righe |
|---|---|---|
| `omega_control` | Controllo globale: status, mode (paper/live), daily_goal (250), params, heartbeat | 1 |
| `omega_events` | Eventi candidati con mercati censiti | 11 |
| `omega_market_snapshot` | Snapshot mercato corrente (runners JSON, minuto) | 2 |
| `omega_trades` | Trade omega: lay CS, prezzo, liability, pnl, fase | 0 |
| `omega_missions` | Missioni per evento: target, fase, score, suggerimenti HT/FT/scalp | 0 |
| `omega_manual_requests` | Coda richieste manuali (kind+payload) | 4 |
| `omega_activity` | Log attività | 0 |

---

## 11. Tracking personale (watchlist + report operazioni)

Migrazioni: `personal_tracking.sql`, `personal_tracking_import.sql`, `personal_tracking_manual_entry.sql`, `personal_cash_movements.sql`, `watchlist_follow_live.sql`. Accesso quasi esclusivamente via RPC dal frontend (`add_personal_trade`, `settle_personal_trade`, `get_personal_report`, `set_watchlist_*`, `upsert_imported_trade`, `upsert_cash_movement`). RLS owner-only.

| Tabella | Scopo | Colonne chiave | Righe |
|---|---|---|---|
| `personal_watchlist` | Partite in valutazione: snapshot quote/edge al momento dell'aggiunta, decisione (DA_VALUTARE/…), flag `follow_live` che pilota `live_follow` | `fixture_id`, `status`, `snapshot` (JSON), `consigli`, `follow_live` | 28 |
| `personal_trades` | Operazioni reali dell'utente (anche importate da Betfair): strategia, entry/exit, PnL netto, ROI, hourly_yield, contesto motori | `fixture_id`, `strategia`, `side`, `market`, `entry_odds`, `stake`, `net_pnl`, `betfair_bet_id`, `tags` | 59 |
| `personal_trade_legs` | Gambe aggiuntive di un trade (hedge/uscite parziali) | `trade_id`, `leg_type`, `odds`, `stake`, `net_pnl` | 0 |
| `personal_cash_movements` | Movimenti cassa Betfair (depositi/prelievi/saldo) | `transaction_id`, `type`, `amount`, `balance` | 9 |

---

## 12. Altro

| Tabella | Scopo | Righe | Note |
|---|---|---|---|
| `leads` | Lead dalla landing page (nome, email, trial) | 1 | Estranea al dominio betting; scritta dal frontend |

---

## RPC (115 funzioni)

Gruppi principali (elenco completo ottenibile dall'OpenAPI):
- **Analytics/strategie**: `get_analytics*`, `get_decisions*`, `run_strategy*`, `backtest_strategy*`, `save/delete/list_strategies`, `refresh_analytics_bets(_range)`, `flush_analytics_*_staging`, `analyze_by_league`, `analyze_feature`, `get_market_frequency`, `get_market_delays`, `get_direction*`, `bulk_update_prediction_results`
- **Betfair pre-match**: `get_betfair_fixtures/odds/full_odds/direction_odds`, `request_betfair_order/refresh`, `book_odds`
- **Live trading**: `request_betfair_live_order`, `get_live_orders/positions(_all/_event)/settled/journal/audit/xhedge/settings/alerts`, `set_live_kill_switch/settings/journal_note`, `request/cancel_live_risk_rule`, `ack_alert`, `betfair_live_is_owner`
- **Live stream/backtest**: `get_live_follows`, `get_replay`, `list_replays`, `request_backtest`, `list_backtest_runs/results`
- **Tennis**: `get_tennis_*`, `tennis_follow_event`, `tennis_bot_arm/disarm`, `request_tennis_live_order/refresh`, `tennis_is_owner`
- **Omega**: `omega_activate/stop/request/update_params`, `omega_mission_*`, `get_omega_*`
- **Scalper**: `scalper_activate/stop`, `get_scalper_state`
- **Personale**: `add_personal_trade`, `add_trade_leg`, `settle/recompute_personal_trade`, `get_personal_trades/report`, `upsert_imported_trade`, `upsert_cash_movement`, `get_cash_movements`, `add_to/delete_from_watchlist`, `get_watchlist`, `set_watchlist_decision/follow_live`, `set_trade_time_operative`, `reset_personal_report`
- **Coverage/ML**: `fetch_missing_fixture_coverage`, `refresh_api_coverage_by_season_v2_mv`, `leagues_needing_retrain`, `get_league_seasons`

Sicurezza: `security_lockdown.sql` revoca l'EXECUTE ad `anon` sulle RPC sensibili (accesso solo owner autenticato o service key).

---

## FONTI NON-DB

### Storage Supabase (bucket)

| Bucket | Contenuto | Note |
|---|---|---|
| `ai-models-league-{id}` × **1028 bucket** | Modelli ML per lega: `ensemble_v2_target_*.pkl.gz` (1x2, btts, over/under home/away…) | Privati; indicizzati da `ai_model_registry` (storage_bucket + storage_path) |
| `ai-models` | Bucket legacy (league_135, league_2, seriea) | Privato, superato dai bucket per-lega |
| `Loghi` | Loghi/immagini brand (AlphaScore) | **Pubblico** |

### Directory dati locali (repo)

| Percorso | Dimensione | Contenuto |
|---|---|---|
| `_live_raw/` | **3.8 GB**, 29 directory evento | Registrazioni tick grezze full-depth dello stream Betfair (una dir per event_id, es. `35674515/`). Fonte per replay/backtest; indicizzate da `live_run_log.raw_file_path` |
| `Ai Engine/models_cache/` | **1.4 GB**, 409 voci | Cache locale modelli ML per lega (`league_{id}/` + `downloaded/`) scaricati dai bucket Storage |
| `Betfair/stream/` | 9 MB | Codice worker stream + backtest (non dati) |
| `dynamic_cal.json` | 344 KB | Calibrazione dinamica per lega (generata da `generate_dynamic_cal.py` da poisson_calibration) |
| `dc_rho_by_league.json` | 4 KB | Parametro rho Dixon-Coles per lega |
| `inplay_intensity_by_league.json` | 12 KB | Intensità gol in-play per lega (utile per modelli sui minuti) |
| `league_trust_scores.json` | 8 KB | Trust score per lega |
| `_fid2goals.json`, `_fid2league.json` | — | Mappe fixture→gol / fixture→lega usate dagli script di certificazione |
| `_LEAGUE_DATA_MAP.json`, `_league_played_by_season.json`, `_api_leagues_coverage.json` | — | Mappe copertura leghe |
| `calibration_update_*.json`, `final_retrain.json`, `retrain_targets.json` | — | Artefatti storici di calibrazione/retrain |

Nota: `Betfair/omega/data/` NON esiste (il bot omega scrive solo su DB).

### GitHub Actions (`.github/workflows/`) — producono/aggiornano dati

| Workflow | Effetto sul DB |
|---|---|
| `daily_yesterday_backfill.yml` | Backfill quotidiano match di ieri → matches, match_events, lineups, stats, top_*, injuries |
| `today_predictions_backfill.yml` | Pronostici del giorno → fixture_predictions |
| `predictions_results_backfill.yml` | Valuta esiti pronostici → fixture_predictions (result_*, hit_*) via `bulk_update_prediction_results` |
| `leagues_mapper.yml` | Aggiorna leghe/coperture → api_coverage_by_season |
| `retrain_models.yml` | Retrain ML per lega → ai_model_registry, model_performance + bucket Storage |
| `validate_models.yml` | Validazione modelli → model_performance |
| `ml_calibration.yml` | Post-calibrazione ML → ml_post_calibration |
| `weekly_poisson_calibration.yml` | Calibrazione Poisson settimanale → poisson_calibration |
