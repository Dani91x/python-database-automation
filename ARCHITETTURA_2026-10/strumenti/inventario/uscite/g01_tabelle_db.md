| tabella | definita in | chiamate prod / FE | scrive (prod) | legge (prod) | FE legge / scrive | frequenza misurata 02/10 (finestra 60 s) |
|---|---|---|---|---|---|---|
| `fixture_predictions` | NON nei .sql tracciati | 72 / 6 | `AGGIORNA_CAMPO_db_json_analisi.py:178`, `Ai Engine/ai_engine/predict_fixture.py:1087`, `Prediction/backfill_historical_analysis.py:120` (+17) | `AGGIORNA_CAMPO_db_json_analisi.py:134`, `Ai Engine/ai_engine/db_adapter.py:432`, `Ai Engine/ai_engine/serving_batch.py:60` (+49) | `frontend/src/components/dashboard/FixtureSelector.tsx:30`, `frontend/src/components/dashboard/MatchesList.tsx:157` (+4) / - | safe-bot GET 1 (MISURE:142) |
| `matches` | NON nei .sql tracciati | 40 / 0 | `daily_yesterday_backfill.py:75`, `fixtures_backfill.py:135` | `Ai Engine/ai_engine/db_adapter.py:418`, `Betfair/betfair_report_manager.py:1246`, `Betfair/money_management.py:1399` (+35) | - / - | - |
| `betfair_live_order_requests` | migrations | 24 / 0 | `Betfair/mike/db.py:683`, `Betfair/omega/omega_db.py:674`, `Betfair/safe_strategy/bot_db.py:1029` (+9) | `Betfair/mike/db.py:669`, `Betfair/mike/db.py:676`, `Betfair/omega/omega_db.py:648` (+9) | - / - | runner-calcio GET 189 (MISURE:100) |
| `live_follow` | migrations | 23 / 1 | `Betfair/stream/auto_follow.py:402`, `Betfair/stream/auto_follow.py:426`, `Betfair/stream/auto_follow.py:429` (+5) | `Betfair/mike/db.py:651`, `Betfair/omega/omega_db.py:618`, `Betfair/safe_strategy/bot_db.py:989` (+12) | `frontend/src/lib/safeBot.ts:2195` / - | runner-calcio GET 29 (MISURE:103) |
| `safe_strategy_requests` | migrations | 17 / 4 | `Betfair/safe_strategy/bot_db.py:651`, `Betfair/safe_strategy/bot_db.py:659`, `Betfair/safe_strategy/bot_db.py:678` (+9) | `Betfair/safe_strategy/bot_db.py:606`, `Betfair/safe_strategy/bot_db.py:619`, `Betfair/safe_strategy/bot_db.py:632` (+2) | `frontend/src/lib/controlRoomProposte.ts:371`, `frontend/src/lib/safeBot.ts:1418` (+2) / - | safe-bot PATCH 53 (MISURE:133); safe-bot GET 44 (MISURE:134) |
| `betfair_live_orders` | migrations | 15 / 0 | `Betfair/stream/db.py:1139`, `Betfair/stream/db.py:819`, `Betfair/stream/db.py:828` (+2) | `Betfair/mike/db.py:233`, `Betfair/mike/db.py:691`, `Betfair/omega/omega_db.py:687` (+7) | - / - | runner-calcio GET 11 (MISURE:104) |
| `<dinamico:table>` | NON nei .sql tracciati | 14 / 0 | `Betfair/stream/db.py:572`, `Betfair/stream/db.py:596`, `football_data_scraper/backfill.py:342` (+3) | `Ai Engine/ai_engine/db_adapter.py:231`, `Betfair/omega/omega_db.py:181`, `Betfair/stream/db.py:564` (+5) | - / - | - |
| `safe_strategy_trades` | migrations | 14 / 0 | `Betfair/safe_strategy/bot_db.py:102`, `Betfair/safe_strategy/bot_db.py:110`, `Betfair/safe_strategy/bot_db.py:92` | `Betfair/safe_strategy/bot_db.py:122`, `Betfair/safe_strategy/bot_db.py:129`, `Betfair/safe_strategy/bot_db.py:172` (+8) | - / - | safe-bot GET 81 (MISURE:132) |
| `ai_model_registry` | NON nei .sql tracciati | 12 / 0 | `Ai Engine/ai_engine/seriea_model_export.py:686`, `Ai Engine/ai_engine/seriea_model_export.py:689`, `Betfair/betfair_report_manager.py:1299` (+2) ; op?: `cloud_retrain_shard.py:77` | `Ai Engine/ai_engine/predict_fixture.py:512`, `Betfair/betfair_report_manager.py:1224`, `Betfair/betfair_report_manager.py:1319` (+4) | - / - | - |
| `omega_events` | migrations | 11 / 0 | `Betfair/omega/omega_db.py:1017`, `Betfair/omega/omega_db.py:303`, `Betfair/omega/omega_db.py:442` (+4) | `Betfair/omega/omega_db.py:486`, `Betfair/omega/omega_db.py:526`, `Betfair/omega/omega_db.py:564` (+1) | - / - | safe-bot GET 1 (MISURE:141) |
| `safe_strategy_scan` | migrations | 10 / 1 | `Betfair/safe_strategy/db.py:198`, `Betfair/safe_strategy/db.py:213` | `Betfair/mike/db.py:560`, `Betfair/safe_strategy/bot_db.py:961`, `Betfair/safe_strategy/db.py:50` (+5) | `frontend/src/lib/safeStrategyScan.ts:343` / - | scanner POST 68 (MISURE:162); mike GET 14 (MISURE:67); runner-calcio GET 8 (MISURE:106); safe-bot GET 5 (MISURE:139); scanner GET 1 (MISURE:166) |
| `scalper_control` | migrations | 11 / 0 | `Betfair/stream/scalper/scalper_service.py:195`, `Betfair/stream/scalper/scalper_service.py:197`, `Betfair/stream/scalper/scalper_service.py:208` (+2) | `Betfair/stream/scalper/scalper_service.py:147`, `Betfair/stream/scalper/scalper_service.py:214`, `Betfair/stream/scalper/scalper_service.py:75` (+3) | - / - | scalper GET 18 (MISURE:179) |
| `live_now` | migrations | 9 / 1 | `Betfair/stream/db.py:348`, `Betfair/stream/db.py:362`, `Betfair/stream/db.py:528` | `Betfair/omega/omega_db.py:595`, `Betfair/stream/db.py:513`, `Betfair/stream/live_order_worker.py:1105` (+3) | `frontend/src/lib/live.ts:140` / - | - |
| `omega_trades` | migrations | 10 / 0 | `Betfair/omega/omega_db.py:76`, `Betfair/omega/omega_db.py:86`, `Betfair/omega/omega_db.py:94` | `Betfair/omega/omega_db.py:1031`, `Betfair/omega/omega_db.py:253`, `Betfair/omega/omega_db.py:722` (+4) | - / - | omega GET 4 (MISURE:86) |
| `season_backfill_state` | NON nei .sql tracciati | 10 / 0 | `season_gaps.py:522`, `season_gaps.py:531`, `season_gaps.py:559` (+2) | `retrain_all_leagues.py:125`, `season_gaps.py:546`, `season_gaps.py:595` (+2) | - / - | - |
| `tennis_bot_control` | migrations | 10 / 0 | `Betfair/stream/tennis_live/tennis_db.py:214`, `Betfair/stream/tennis_live/tennis_db.py:444`, `Betfair/stream/tennis_live/tennis_db.py:451` (+6) | `Betfair/stream/tennis_live/tennis_db.py:399` | - / - | tennis-bot-svc GET 18 (MISURE:189) |
| `live_alerts` | migrations | 9 / 0 | `Betfair/stream/db.py:697`, `Betfair/stream/live_order_worker.py:1071`, `Betfair/stream/motore_ordini.py:2431` (+6) | - | - / - | - |
| `tennis_live_order_queue` | migrations | 9 / 0 | `Betfair/stream/tennis_live/esecutore_tennis.py:266`, `Betfair/stream/tennis_live/tennis_db.py:549`, `Betfair/stream/tennis_live/tennis_db.py:568` (+4) | `Betfair/stream/tennis_live/tennis_db.py:351`, `Betfair/stream/tennis_live/tennis_db.py:535` | - / - | - |
| `mike_trades` | migrations | 8 / 0 | `Betfair/mike/db.py:176`, `Betfair/mike/db.py:186` | `Betfair/mike/db.py:192`, `Betfair/mike/db.py:202`, `Betfair/mike/db.py:211` (+3) | - / - | mike GET 116 (MISURE:63) |
| `safe_strategy_status` | migrations | 7 / 1 | `Betfair/safe_strategy/db.py:228` | `Betfair/mike/db.py:569`, `Betfair/safe_strategy/bot_db.py:973`, `Betfair/stream/auto_follow.py:466` (+3) | `frontend/src/lib/safeStrategyScan.ts:350` / - | scanner POST 5 (MISURE:165); safe-bot GET 5 (MISURE:138); runner-calcio GET 2 (MISURE:108) |
| `<dinamico:tabella>` | NON nei .sql tracciati | 7 / 0 | `Betfair/stream/db.py:1114` | `Betfair/mike/db.py:230`, `Betfair/mike/db.py:599`, `Betfair/safe_strategy/db.py:473` (+3) | - / - | - |
| `api_coverage_by_season` | NON nei .sql tracciati | 7 / 0 | `leagues_mapper.py:325`, `leagues_mapper.py:350` | `Prediction/today_predictions_backfill.py:754`, `Prediction/today_predictions_backfill.py:796`, `leagues_mapper.py:96` (+2) | - / - | - |
| `betfair_live_risk_rules` | migrations | 7 / 0 | `Betfair/stream/risk_engine_worker.py:189` | `Betfair/stream/reconcile_worker.py:1264`, `Betfair/stream/risk_engine_worker.py:1096`, `Betfair/stream/risk_engine_worker.py:1173` (+3) | - / - | runner-calcio GET 168 (MISURE:101) |
| `betfair_market_odds` | migrations | 7 / 0 | `Betfair/odds_refresh.py:254`, `Betfair/odds_refresh.py:257`, `betfair_full_odds.py:73` (+1) | `Betfair/odds_refresh.py:224`, `Betfair/order_exec.py:161`, `_certify_betfair_full.py:13` | - / - | - |
| `betfair_order_requests` | migrations | 7 / 0 | `Betfair/order_worker.py:106`, `Betfair/order_worker.py:113`, `Betfair/order_worker.py:120` (+2) | `Betfair/order_worker.py:136`, `Betfair/order_worker.py:61` | - / - | - |
| `omega_manual_requests` | migrations | 7 / 0 | `Betfair/omega/omega_db.py:297`, `Betfair/omega/omega_db.py:323`, `Betfair/omega/omega_db.py:394` (+2) | `Betfair/omega/omega_db.py:283`, `Betfair/omega/omega_db.py:373` | - / - | - |
| `tennis_live_now` | migrations | 6 / 1 | `Betfair/stream/tennis_live/tennis_db.py:292`, `Betfair/stream/tennis_live/tennis_db.py:306`, `Betfair/stream/tennis_live/tennis_db.py:313` (+1) | `Betfair/stream/tennis_live/tennis_db.py:198`, `Betfair/stream/tennis_live/tennis_db.py:369` | `frontend/src/lib/tennis.ts:209` / - | - |
| `analytics_signals` | migrations | 6 / 0 | `build_analytics_signals.py:402`, `fix_storico_prob.py:59` | `_certify_direction_report.py:85`, `enrich_analytics_snapshots.py:265`, `enrich_analytics_snapshots.py:485` (+1) | - / - | - |
| `api_call_log` | NON nei .sql tracciati | 6 / 0 | `logger.py:86`, `logger.py:91` | `api_quota.py:144`, `api_quota.py:149`, `api_quota.py:169` (+1) | - / - | - |
| `betfair_live_heartbeat` | migrations | 4 / 2 | `Betfair/stream/db.py:1127` | `Betfair/mike/db.py:657`, `Betfair/omega/omega_db.py:628`, `Betfair/safe_strategy/bot_db.py:997` | `frontend/src/lib/liveOrders.ts:1034`, `frontend/src/lib/safeBot.ts:2183` / - | runner-calcio POST 8 (MISURE:107) |
| `mike_events` | migrations | 6 / 0 | `Betfair/mike/db.py:141`, `Betfair/mike/db.py:164`, `Betfair/mike/db.py:169` | `Betfair/mike/db.py:108`, `Betfair/mike/db.py:117`, `Betfair/safe_strategy/db.py:307` | - / - | mike POST 25 (MISURE:66); scanner GET 6 (MISURE:163); mike GET 1 (MISURE:71) |
| `mike_requests` | migrations | 5 / 1 | `Betfair/mike/db.py:509`, `Betfair/mike/db.py:516` | `Betfair/mike/db.py:463`, `Betfair/mike/db.py:490`, `Betfair/mike/db.py:533` | `frontend/src/lib/mike.ts:2301` / - | mike GET 58 (MISURE:65) |
| `betfair_live_positions` | migrations | 5 / 0 | `Betfair/stream/db.py:1140`, `Betfair/stream/db.py:940`, `Betfair/stream/db.py:945` | `Betfair/stream/db.py:451`, `Betfair/stream/db.py:481` | - / - | - |
| `engine_signals` | migrations | 5 / 0 | `migrations/backfill_engine_signals.py:278` | `_certify_betfair.py:24`, `_certify_direction_report.py:103`, `_certify_direction_report.py:139` (+1) | - / - | - |
| `match_odds` | NON nei .sql tracciati | 5 / 0 | `football_data_scraper/fix_snapshot_time.py:45` | `football_data_scraper/backfill.py:102`, `market_intelligence/backtest_audit.py:124`, `market_intelligence/backtest_audit.py:138` (+1) | - / - | - |
| `ml_post_calibration` | NON nei .sql tracciati | 5 / 0 | `compute_ml_post_calibration.py:244`, `compute_ml_post_calibration.py:259` | `Ai Engine/ai_engine/predict_fixture.py:386`, `compute_ml_post_calibration.py:123`, `compute_ml_post_calibration.py:256` | - / - | - |
| `tennis_live_follow` | migrations | 5 / 0 | `Betfair/stream/tennis_live/tennis_db.py:118`, `Betfair/stream/tennis_live/tennis_db.py:231` | `Betfair/stream/tennis_live/tennis_db.py:240`, `Betfair/stream/tennis_live/tennis_db.py:377`, `Betfair/stream/tennis_replay/importa.py:78` | - / - | runner-tennis GET 28 (MISURE:126); tennis-bot-svc GET 3 (MISURE:192) |
| `bet_features` | migrations | 4 / 0 | - | `_league_eval.py:43`, `_stack_eval.py:42`, `build_direzione.py:79` (+1) | - / - | - |
| `betfair_live_account` | migrations | 3 / 1 | `Betfair/stream/db.py:1004`, `Betfair/stream/db.py:1055`, `Betfair/stream/db.py:1086` | - | `frontend/src/lib/liveOrders.ts:981` / - | runner-calcio POST 2 (MISURE:109) |
| `betfair_refresh_requests` | migrations | 4 / 0 | `Betfair/refresh_worker.py:59`, `Betfair/refresh_worker.py:66`, `Betfair/refresh_worker.py:73` | `Betfair/refresh_worker.py:38` | - / - | - |
| `direction_pagella` | migrations | 4 / 0 | `build_direzione.py:226`, `build_direzione.py:230` | `_certify_direction.py:39`, `build_direzione.py:232` | - / - | - |
| `match_team_stats` | NON nei .sql tracciati | 4 / 0 | - | `football_data_scraper/backfill.py:147`, `market_intelligence/audit.py:83`, `market_intelligence/edge_scorer.py:472` (+1) | - / - | - |
| `safe_strategy_opportunities` | migrations | 3 / 1 | `Betfair/safe_strategy/bot_db.py:879`, `Betfair/safe_strategy/bot_db.py:891`, `Betfair/safe_strategy/bot_db.py:903` | - | `frontend/src/lib/safeBot.ts:1544` / - | safe-bot POST 4 (MISURE:140); safe-bot DELETE 1 (MISURE:143) |
| `scalper_activity` | migrations | 4 / 0 | `Betfair/stream/scalper/scalper_service.py:86`, `Betfair/stream/scalper/scalper_service.py:890`, `Betfair/stream/scalper/scalper_session.py:1270` (+1) | - | - / - | - |
| `tennis_markets` | migrations | 4 / 0 | `betfair_tennis_odds.py:274`, `betfair_tennis_odds.py:278` | `Betfair/stream/tennis_live/tennis_bot_service.py:151`, `Betfair/stream/tennis_replay/importa.py:82` | - / - | tennis-odds DELETE+POST 2+2 in 29,8 min (MISURE:203) |
| `betfair_live_settled` | migrations | 3 / 0 | `Betfair/stream/db.py:963` | `Betfair/stream/daily_stop_worker.py:250`, `Betfair/stream/db.py:425` | - / - | runner-calcio GET 11 (MISURE:105) |
| `live_backtest_requests` | migrations | 3 / 0 | `Betfair/stream/db.py:726`, `Betfair/stream/db.py:741` | `Betfair/stream/db.py:714` | - / - | - |
| `live_signals` | migrations | 2 / 1 | `Betfair/stream/db.py:662` | `Betfair/stream/live_order_worker.py:999` | `frontend/src/lib/live.ts:560` / - | - |
| `match_events` | NON nei .sql tracciati | 3 / 0 | - | `build_analytics_signals.py:376`, `build_inplay_intensity.py:88`, `value_engine/calibrate.py:37` | - / - | - |
| `omega_missions` | migrations | 3 / 0 | `Betfair/omega/omega_db.py:717` | `Betfair/omega/omega_db.py:699`, `Betfair/omega/omega_db.py:708` | - / - | - |
| `poisson_calibration` | migrations | 3 / 0 | `generate_dynamic_cal.py:459`, `load_poisson_calibration_to_db.py:65` | `poisson_calibrator.py:100` | - / - | - |
| `safe_strategy_activity` | migrations | 2 / 1 | `Betfair/safe_strategy/bot_db.py:79` | `Betfair/safe_strategy/bot_db.py:436` | `frontend/src/lib/safeBot.ts:1206` / - | - |
| `tennis_live_orders` | migrations | 3 / 0 | `Betfair/stream/tennis_live/tennis_db.py:604`, `Betfair/stream/tennis_live/tennis_db.py:854` | `Betfair/stream/tennis_live/tennis_db.py:335` | - / - | - |
| `tennis_live_positions` | migrations | 3 / 0 | `Betfair/stream/tennis_live/tennis_db.py:627`, `Betfair/stream/tennis_live/tennis_db.py:863` | `Betfair/stream/tennis_live/tennis_db.py:342` | - / - | - |
| `theta_confirm_requests` | migrations | 3 / 0 | `Betfair/stream/scalper/scalper_session.py:1936`, `Betfair/stream/scalper/scalper_session.py:1958` | `Betfair/stream/scalper/scalper_session.py:1947` | - / - | - |
| `<dinamico:nome>` | NON nei .sql tracciati | 2 / 0 | `season_aggregates.py:229`, `season_aggregates.py:238` | - | - / - | - |
| `analytics_snap_staging` | migrations | 2 / 0 | `enrich_analytics_snapshots.py:293`, `enrich_analytics_snapshots.py:336` | - | - / - | - |
| `betfair_live_audit` | migrations | 2 / 0 | `Betfair/stream/daily_stop_worker.py:391`, `Betfair/stream/live_order_worker.py:922` | - | - / - | - |
| `betfair_live_journal` | migrations | 2 / 0 | `Betfair/stream/db.py:988`, `Betfair/stream/live_order_worker.py:1134` | - | - / - | - |
| `betfair_live_risk_state` | migrations | 1 / 1 | `Betfair/stream/db.py:978` | - | `frontend/src/lib/liveOrders.ts:795` / - | - |
| `betfair_live_xhedge` | migrations | 2 / 0 | `Betfair/stream/xhedge_worker.py:119` | `Betfair/stream/risk_engine_worker.py:1001` | - / - | - |
| `injuries` | NON nei .sql tracciati | 2 / 0 | `injuries_backfill.py:209`, `injuries_backfill.py:259` | - | - / - | - |
| `live_backtest_results` | migrations | 2 / 0 | `Betfair/stream/db.py:758`, `Betfair/stream/db.py:762` | - | - / - | - |
| `live_ladder` | migrations | 1 / 1 | `Betfair/stream/db.py:682` | - | `frontend/src/lib/live.ts:621` / - | - |
| `live_markets` | migrations | 2 / 0 | `Betfair/stream/db.py:314` | `Betfair/stream/db.py:404` | - / - | - |
| `mike_control` | migrations | 2 / 0 | `Betfair/mike/db.py:68` | `Betfair/mike/db.py:60` | - / - | mike GET 58 (MISURE:64); mike PATCH 2 (MISURE:69) |
| `omega_control` | migrations | 2 / 0 | `Betfair/omega/omega_db.py:58` | `Betfair/omega/omega_db.py:50` | - / - | omega GET 1 (MISURE:87) |
| `personal_watchlist` | migrations | 2 / 0 | - | `Betfair/stream/db.py:114`, `Betfair/stream/watchlist.py:29` | - / - | runner-calcio GET 1 (MISURE:110) |
| `safe_strategy_control` | migrations | 2 / 0 | `Betfair/safe_strategy/bot_db.py:74` | `Betfair/safe_strategy/bot_db.py:64` | - / - | safe-bot GET 36 (MISURE:135); safe-bot PATCH 19 (MISURE:137) |
| `scalper_service_control` | migrations | 2 / 0 | `Betfair/stream/scalper/scalper_service.py:102` | `Betfair/stream/scalper/scalper_service.py:94` | - / - | scalper GET 18 (MISURE:181) |
| `signal_history` | migrations | 2 / 0 | `Betfair/money_management.py:2434`, `Betfair/money_management.py:2471` | - | - / - | - |
| `standings` | NON nei .sql tracciati | 2 / 0 | `standings_backfill.py:239`, `standings_backfill.py:289` | - | - / - | - |
| `tennis_bot_service_control` | migrations | 2 / 0 | `Betfair/stream/tennis_live/tennis_db.py:710` | `Betfair/stream/tennis_live/tennis_db.py:662` | - / - | tennis-bot-svc PATCH 12 (MISURE:190); tennis-bot-svc GET 3 (MISURE:191) |
| `tennis_live_ladder` | migrations | 1 / 1 | `Betfair/stream/tennis_live/tennis_db.py:260` | - | `frontend/src/lib/tennis.ts:263` / - | - |
| `tennis_replay_eventi` | migrations | 2 / 0 | `Betfair/stream/tennis_replay/caricamento.py:108`, `Betfair/stream/tennis_replay/caricamento.py:75` | - | - / - | - |
| `tennis_replay_mercati` | migrations | 2 / 0 | `Betfair/stream/tennis_replay/caricamento.py:79` | `Betfair/stream/tennis_replay/caricamento.py:97` | - / - | - |
| `top_assists` | NON nei .sql tracciati | 2 / 0 | `top_assists_backfill.py:235`, `top_assists_backfill.py:285` | - | - / - | - |
| `top_cards` | NON nei .sql tracciati | 2 / 0 | `top_cards_backfill.py:244`, `top_cards_backfill.py:294` | - | - / - | - |
| `top_scorers` | NON nei .sql tracciati | 2 / 0 | `top_scorers_backfill.py:235`, `top_scorers_backfill.py:285` | - | - / - | - |
| `<dinamico:MU.TABELLA_ORDINI_CONTO>` | NON nei .sql tracciati | 1 / 0 | - | `Betfair/stream/scalper/scalper_session.py:962` | - / - | - |
| `<dinamico:name>` | NON nei .sql tracciati | 1 / 0 | - ; op?: `Betfair/stream/live_order_worker.py:3288` | - | - / - | - |
| `<dinamico:t>` | NON nei .sql tracciati | 1 / 0 | `per_fixture_backfill.py:219` | - | - / - | - |
| `analytics_bets` | migrations | 1 / 0 | - | `_certify_direction.py:174` | - / - | - |
| `analytics_decisions` | migrations | 1 / 0 | - | `certify_backtest_strategy.py:103` | - / - | - |
| `fixture_detail_checks` | migrations | 1 / 0 | - | `season_gaps.py:445` | - / - | - |
| `leads` | NON nei .sql tracciati | 0 / 1 | - | - | - / `frontend/src/components/landing/AuthSection.tsx:74` | - |
| `live_run_log` | migrations | 1 / 0 | `Betfair/stream/db.py:644` | - | - / - | - |
| `mike_activity` | migrations | 1 / 0 | `Betfair/mike/db.py:76` | - | - / - | mike POST 2 (MISURE:70) |
| `model_performance` | NON nei .sql tracciati | 1 / 0 | `retrain_all_leagues.py:363` | - | - / - | - |
| `omega_activity` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:63` | - | - / - | - |
| `omega_daily_goal` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:1045` | - | - / - | - |
| `omega_market_snapshot` | migrations | 1 / 0 | `Betfair/omega/omega_db.py:482` | - | - / - | - |
| `personal_trades` | migrations | 1 / 0 | `_certify_personal_report.py:325` | - | - / - | - |
| `replay_bot_esiti` | migrations | 1 / 0 | `Betfair/stream/db.py:752` | - | - / - | - |
| `tennis_bot_activity` | migrations | 1 / 0 | `Betfair/stream/tennis_live/tennis_db.py:518` | - | - / - | - |
