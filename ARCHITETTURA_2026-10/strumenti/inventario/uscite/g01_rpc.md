| RPC | definita | prod (n) | primo file prod | FE (n) | primo file FE | frequenza misurata |
|---|---|---|---|---|---|---|
| `ack_alert` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:691` | - |
| `add_personal_trade` | migrations | 1 | `_certify_personal_report.py:359` | 1 | `frontend/src/lib/personalReport.ts:325` | - |
| `add_to_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:110` | - |
| `add_trade_leg` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:333` | - |
| `backtest_strategy` | migrations | 1 | `certify_backtest_strategy.py:171` | 1 | `frontend/src/lib/analytics.ts:328` | - |
| `betfair_live_is_owner` | migrations | 0 | - | 1 | `frontend/src/certification/realClient.ts:146` | - |
| `bulk_update_prediction_results` | migrations | 1 | `Prediction/predictions_results_backfill.py:671` | 0 | - | - |
| `cancel_live_risk_rule` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:494` | - |
| `delete_from_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:126` | - |
| `delete_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:346` | - |
| `fetch_missing_fixture_coverage` | NON nei .sql | 1 | `missing_fixtures_backfill.py:47` | 0 | - | - |
| `flush_analytics_snap_staging` | migrations | 1 | `enrich_analytics_snapshots.py:312` | 0 | - | - |
| `get_analytics` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:106` | - |
| `get_analytics_filters` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:81` | - |
| `get_analytics_rows` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:115` | - |
| `get_betfair_direction_odds` | migrations | 1 | `_certify_betfair_full.py:28` | 1 | `frontend/src/lib/betfair.ts:53` | - |
| `get_betfair_fixtures` | migrations | 1 | `_certify_betfair.py:42` | 1 | `frontend/src/lib/betfair.ts:23` | - |
| `get_betfair_full_odds` | migrations | 1 | `_certify_betfair_full.py:21` | 1 | `frontend/src/lib/betfair.ts:44` | - |
| `get_betfair_live_order` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:143` | - |
| `get_betfair_odds` | migrations | 1 | `_certify_betfair.py:59` | 1 | `frontend/src/lib/betfair.ts:32` | - |
| `get_betfair_order_request` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:177` | - |
| `get_betfair_orders` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:238` | - |
| `get_betfair_refresh_request` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:90` | - |
| `get_cash_movements` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:370` | - |
| `get_decisions` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:180` | - |
| `get_decisions_filters` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:175` | - |
| `get_direction` | migrations | 3 | `_certify_direction.py:207` (+2) | 1 | `frontend/src/lib/direzione.ts:50` | - |
| `get_direction_eta` | migrations | 0 | - | 1 | `frontend/src/lib/direzione.ts:73` | - |
| `get_direction_report` | migrations | 1 | `_certify_direction_report.py:509` | 1 | `frontend/src/lib/reportistiche.ts:140` | - |
| `get_direction_report_fixture` | migrations | 1 | `_certify_direction_report.py:480` | 1 | `frontend/src/lib/reportistiche.ts:180` | - |
| `get_direction_report_matches` | migrations | 1 | `_certify_direction_report.py:518` | 1 | `frontend/src/lib/reportistiche.ts:147` | - |
| `get_league_seasons` | sql | 0 | - | 1 | `frontend/src/lib/marketFrequency.ts:168` | - |
| `get_live_alerts` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:668` | - |
| `get_live_audit` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:712` | - |
| `get_live_follows` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:37` | - |
| `get_live_journal` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:915` | - |
| `get_live_orders` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:510` | - |
| `get_live_orders_account_open` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:851` | - |
| `get_live_positions` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:518` | - |
| `get_live_positions_all` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:862` | - |
| `get_live_positions_event` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:869` | - |
| `get_live_risk_rules` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:501` | - |
| `get_live_settings` | migrations | 4 | `Betfair/stream/live_order_worker.py:498` (+3) | 1 | `frontend/src/lib/liveOrders.ts:676` | runner-calcio 123/min (MISURE:102), scalper 18/min (MISURE:180) |
| `get_live_settled` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:769` | - |
| `get_live_xhedge` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:615` | - |
| `get_market_delays` | migrations | 4 | `_certify_signal_context.py:77` (+3) | 1 | `frontend/src/lib/marketDelays.ts:134` | - |
| `get_market_frequency` | sql | 4 | `Betfair/omega/omega_db.py:767` (+3) | 1 | `frontend/src/lib/marketFrequency.ts:154` | - |
| `get_mike_aggregates` | migrations | 1 | `Betfair/mike/db.py:409` | 0 | - | mike 3/min (MISURE:68) |
| `get_mike_daily` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:412` | - |
| `get_mike_day_trades` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:420` | - |
| `get_mike_state` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2248` | - |
| `get_mike_trades` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2268` | - |
| `get_omega_aggregates` | migrations | 1 | `Betfair/omega/omega_db.py:875` | 0 | - | - |
| `get_omega_aggregates_modalita` | migrations | 1 | `Betfair/omega/omega_db.py:823` | 0 | - | omega 4 in 5 min (MISURE:95) |
| `get_omega_daily` | migrations | 0 | - | 3 | `frontend/src/lib/dailyHistory.ts:270` (+2) | - |
| `get_omega_day_trades` | migrations | 0 | - | 3 | `frontend/src/lib/dailyHistory.ts:301` (+2) | - |
| `get_omega_events` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1507` | - |
| `get_omega_ht_ft` | migrations | 1 | `Betfair/omega/omega_db.py:1060` | 0 | - | - |
| `get_omega_manual_requests` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1568` | - |
| `get_omega_market` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1562` | - |
| `get_omega_minute_ft` | migrations | 1 | `Betfair/omega/omega_db.py:1073` | 0 | - | - |
| `get_omega_missions` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:198` | - |
| `get_omega_proposte` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:292` | - |
| `get_omega_state` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1343` | - |
| `get_omega_trades` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1362` | - |
| `get_personal_report` | migrations | 2 | `_certify_personal_report.py:387` (+1) | 1 | `frontend/src/lib/personalReport.ts:388` | - |
| `get_personal_trades` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:410` | - |
| `get_poisson_calibration_eta` | migrations | 0 | - | 1 | `frontend/src/lib/fixtureModels.ts:89` | - |
| `get_replay` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:339` | - |
| `get_replay_bot_esito` | migrations | 0 | - | 1 | `frontend/src/lib/replayBot.ts:236` | - |
| `get_replay_meta` | migrations | 0 | - | 2 | `frontend/src/lib/live.ts:433` (+1) | - |
| `get_replay_tennis_meta` | migrations | 0 | - | 1 | `frontend/src/lib/tennisReplay.ts:124` | - |
| `get_safe_activity` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1201` | - |
| `get_safe_aggregates` | migrations | 1 | `Betfair/safe_strategy/bot_db.py:336` | 1 | `frontend/src/lib/safeBot.ts:369` | safe-bot 19/min (MISURE:136) |
| `get_safe_daily` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:293` | - |
| `get_safe_day_trades` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:397` | - |
| `get_safe_state` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1177` | - |
| `get_safe_trades` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1215` | - |
| `get_scalper_control_room` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:140` | - |
| `get_scalper_state` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:168` | - |
| `get_storico_stake` | migrations | 0 | - | 1 | `frontend/src/lib/dailyHistory.ts:371` | - |
| `get_tennis_bot_daily` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1080` | - |
| `get_tennis_bot_orders_today` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1124` | - |
| `get_tennis_bot_services` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:981` | - |
| `get_tennis_bots_state` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:837` | - |
| `get_tennis_fixtures` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:82` | - |
| `get_tennis_follows` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:168` | - |
| `get_tennis_full_odds` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:108` | - |
| `get_tennis_live_order` | migrations | 0 | - | 2 | `frontend/src/lib/tennis.ts:437` (+1) | - |
| `get_tennis_live_orders` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:506` | - |
| `get_tennis_live_positions` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:517` | - |
| `get_tennis_live_positions_all` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:571` | - |
| `get_tennis_refresh_request` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:129` | - |
| `get_watchlist` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:117` | - |
| `leagues_needing_retrain` | sql | 1 | `training_planner.py:152` | 0 | - | - |
| `list_backtest_results` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:473` | - |
| `list_backtest_runs` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:463` | - |
| `list_bot_exposures` | migrations | 1 | `Betfair/safe_strategy/db.py:432` | 0 | - | scanner 6/min (MISURE:164) |
| `list_replays` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:193` | - |
| `list_replays_tennis` | migrations | 0 | - | 1 | `frontend/src/lib/tennisReplay.ts:114` | - |
| `list_strategies` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:334` | - |
| `live_order_mode_avvio` | migrations | 1 | `Betfair/stream/modo_ordini.py:391` | 0 | - | - |
| `mike_activate` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2228` | - |
| `mike_request` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2274` | - |
| `mike_stop` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2234` | - |
| `mike_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/mike.ts:2240` | - |
| `omega_activate` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1317` | - |
| `omega_eventi_chiusi_dall_utente` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1398` | - |
| `omega_evento_riprendi` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1421` | - |
| `omega_mission_activate` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:150` | - |
| `omega_mission_follow` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:174` | - |
| `omega_mission_stop` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:162` | - |
| `omega_request` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1501` | - |
| `omega_request_approve` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:338` | - |
| `omega_request_ignore` | migrations | 0 | - | 1 | `frontend/src/lib/omegaProposte.ts:348` | - |
| `omega_stop` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1325` | - |
| `omega_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/omega.ts:1333` | - |
| `record_fixture_detail_checks` | migrations | 1 | `season_gaps.py:455` | 0 | - | - |
| `refresh_analytics_bets_range` | migrations | 1 | `refresh_analytics_bets.py:197` | 0 | - | - |
| `request_backtest` | migrations | 0 | - | 2 | `frontend/src/lib/analytics.ts:456` (+1) | - |
| `request_betfair_live_order` | migrations | 5 | `Betfair/mike/db.py:663` (+4) | 1 | `frontend/src/lib/liveOrders.ts:133` | - |
| `request_betfair_order` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:167` | - |
| `request_betfair_refresh` | migrations | 0 | - | 1 | `frontend/src/lib/betfair.ts:81` | - |
| `request_live_risk_rule` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:483` | - |
| `request_tennis_live_order` | migrations | 0 | - | 2 | `frontend/src/lib/tennis.ts:422` (+1) | - |
| `request_tennis_refresh` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:123` | - |
| `reset_personal_report` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:403` | - |
| `rpc` | NON nei .sql | 1 | `ventaglio_segnali.py:66` | 0 | - | - |
| `run_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:351` | - |
| `run_strategy_rows` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:385` | - |
| `safe_activate` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1147` | - |
| `safe_request` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1224` | - |
| `safe_request_approve` | migrations | 0 | - | 2 | `frontend/src/lib/controlRoomProposte.ts:400` (+1) | - |
| `safe_request_ignore` | migrations | 0 | - | 1 | `frontend/src/lib/controlRoomProposte.ts:409` | - |
| `safe_stop` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1155` | - |
| `safe_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/safeBot.ts:1161` | - |
| `save_strategy` | migrations | 0 | - | 1 | `frontend/src/lib/analytics.ts:340` | - |
| `scalper_activate` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:148` | - |
| `scalper_approva_uscita` | migrations | 0 | - | 1 | `frontend/src/lib/proposteUscite.ts:90` | - |
| `scalper_auto_activate` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:166` | - |
| `scalper_auto_stop` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:177` | - |
| `scalper_auto_update` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:188` | - |
| `scalper_media_attiva_adesso` | migrations | 0 | - | 1 | `frontend/src/lib/mediaUnderAttiva.ts:17` | - |
| `scalper_stop` | migrations | 0 | - | 1 | `frontend/src/lib/scalper.ts:160` | - |
| `scalper_stop_sessione` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:298` | - |
| `scalper_uscite_automatiche` | migrations | 0 | - | 1 | `frontend/src/lib/scalperControlRoom.ts:313` | - |
| `season_aggregates_summary` | migrations | 1 | `season_aggregates.py:151` | 0 | - | - |
| `season_detail_gaps` | migrations | 1 | `season_gaps.py:228` | 0 | - | - |
| `season_gaps_summary` | migrations | 1 | `season_gaps.py:345` | 0 | - | - |
| `segui_live_apri_partita` | migrations | 0 | - | 1 | `frontend/src/lib/live.ts:51` | - |
| `set_follow_record` | migrations | 0 | - | 1 | `frontend/src/lib/omegaMissions.ts:190` | - |
| `set_live_journal_note` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:932` | - |
| `set_live_kill_switch` | migrations | 1 | `Betfair/stream/daily_stop_worker.py:363` | 1 | `frontend/src/lib/liveOrders.ts:684` | - |
| `set_live_order_mode` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:693` | - |
| `set_live_settings` | migrations | 0 | - | 1 | `frontend/src/lib/liveOrders.ts:705` | - |
| `set_trade_time_operative` | migrations | 0 | - | 1 | `frontend/src/lib/personalReport.ts:378` | - |
| `set_watchlist_decision` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:144` | - |
| `set_watchlist_follow_live` | migrations | 0 | - | 1 | `frontend/src/lib/watchlist.ts:134` | - |
| `settle_personal_trade` | migrations | 1 | `_certify_personal_report.py:361` | 1 | `frontend/src/lib/personalReport.ts:340` | - |
| `tennis_bot_approva_uscita` | migrations | 0 | - | 1 | `frontend/src/lib/proposteUscite.ts:91` | - |
| `tennis_bot_arm` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:876` | - |
| `tennis_bot_disarm` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:889` | - |
| `tennis_bot_service_activate` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:997` | - |
| `tennis_bot_service_set_uscite` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:966` | - |
| `tennis_bot_service_stop` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1008` | - |
| `tennis_bot_service_update_params` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:1022` | - |
| `tennis_follow_event` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:180` | - |
| `tennis_set_follow_record` | migrations | 0 | - | 1 | `frontend/src/lib/tennis.ts:198` | - |
| `upsert_cash_movement` | migrations | 1 | `import_betfair_operations.py:194` | 0 | - | - |
| `upsert_imported_trade` | migrations | 1 | `import_betfair_operations.py:358` | 0 | - | - |
