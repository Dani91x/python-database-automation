
### Safe (`bot_service.resolve_params({}, engine)`) (64 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `poll_interval_s` | 2.0 | `Betfair/safe_strategy/bot_service.py:344` | OK |
| `commission_pct` | 5.0 | `Betfair/safe_strategy/bot_service.py:345` | OK |
| `max_open_trades` | 20 | `Betfair/safe_strategy/bot_service.py:346` | OK |
| `max_liability_per_trade` | 300.0 | `Betfair/safe_strategy/bot_service.py:347` | OK |
| `min_size_available_factor` | 1.0 | `Betfair/safe_strategy/bot_service.py:348` | OK |
| `min_stake` | 2.0 | `Betfair/safe_strategy/bot_service.py:360` | OK |
| `max_spread_ratio` | 1.6 | `Betfair/safe_strategy/bot_service.py:352` | OK |
| `place_max_attempts` | 3 | `Betfair/safe_strategy/bot_service.py:353` | OK |
| `paper_fill_ttl_s` | 45 | `Betfair/safe_strategy/bot_service.py:358` | OK |
| `live_fill_deadline_s` | 20 | `Betfair/safe_strategy/bot_service.py:359` | OK |
| `stake.laySize` | 2.0 | `Betfair/safe_strategy/engine.py:447` | OK |
| `stake.backSize` | 2.0 | `Betfair/safe_strategy/engine.py:448` | OK |
| `risk.daily_liability_cap` | 500.0 | `Betfair/safe_strategy/risk.py:38` | OK |
| `risk.per_event_liability_cap` | 150.0 | `Betfair/safe_strategy/risk.py:39` | OK |
| `risk.per_event_max_trades` | 3 | `Betfair/safe_strategy/risk.py:40` | OK |
| `risk.correlated_cap` | 0.7 | `Betfair/safe_strategy/risk.py:42` | OK |
| `risk.daily_loss_stop` | -50.0 | `Betfair/safe_strategy/risk.py:43` | OK |
| `risk.model_daily_liability_cap` | 150.0 | `Betfair/safe_strategy/risk.py:45` | OK |
| `risk.max_open_trades` | None | `Betfair/safe_strategy/risk.py:41` | OK (None = tetto del bot) |
| `opps_interval_s` | 10.0 | `Betfair/safe_strategy/bot_service.py:349` | OK |
| `opps_min_confidence` | 0.7 | `Betfair/safe_strategy/bot_service.py:363` | OK |
| `opps_min_edge` | 0.03 | `Betfair/safe_strategy/bot_service.py:364` | OK |
| `risk.model_stake` | 5.0 | `Betfair/safe_strategy/risk.py:44` | OK |
| `opps_stake` | 5.0 | `Betfair/safe_strategy/bot_service.py:350` | OK |
| `exits.hold_max_risk` | 0.02 | `Betfair/safe_strategy/exits.py:117` | OK |
| `exits.risk_cap` | 0.1 | `Betfair/safe_strategy/exits.py:118` | OK |
| `exits.risk_premium_pct` | 0.05 | `Betfair/safe_strategy/exits.py:120` | OK |
| `exits.ev_margin` | 0.1 | `Betfair/safe_strategy/exits.py:119` | OK |
| `exits.model_exit_p_lose` | 0.1 | `Betfair/safe_strategy/exits.py:124` | OK |
| `exits.model_take_profit_frac` | 0.8 | `Betfair/safe_strategy/exits.py:125` | OK |
| `exits.model_free_cashout_p_lose` | 0.005 | `Betfair/safe_strategy/exits.py:126` | OK |
| `exits.residual_retry_s` | 20.0 | `Betfair/safe_strategy/exits.py:105` | OK |
| `exits.residual_max_attempts` | 15 | `Betfair/safe_strategy/exits.py:106` | OK |
| `exits.base_exit_minute` | 80 | `Betfair/safe_strategy/exits.py:71` | OK |
| `exits.esatto_exit_minute` | 72 | `Betfair/safe_strategy/exits.py:72` | OK |
| `exits.punta_exit_minute` | 83 | `Betfair/safe_strategy/exits.py:73` | OK |
| `exits.loss_settle_delay_s` | 30.0 | `Betfair/safe_strategy/exits.py:74` | OK |
| `exits.exit_max_retries` | 3 | `Betfair/safe_strategy/exits.py:101` | OK |
| `exits.tennis_take_profit_min_odds` | 1.03 | `Betfair/safe_strategy/exits.py:93` | OK |
| `exits.tennis_take_profit_min_eur` | 0.01 | `Betfair/safe_strategy/exits.py:99` | OK |
| `exits.base_control_exit_max` | -0.2 | `Betfair/safe_strategy/exits.py:81` | OK |
| `base.minuteMin` | 55 | `Betfair/safe_strategy/engine.py:386` | OK |
| `base.dogLayMin` | 20 | `Betfair/safe_strategy/engine.py:395` | OK |
| `base.dogLayMax` | 34 | `Betfair/safe_strategy/engine.py:396` | OK |
| `base.scoreConfirmSec` | 30 | `Betfair/safe_strategy/engine.py:397` | OK |
| `esatto.minuteMin` | 48 | `Betfair/safe_strategy/engine.py:401` | OK |
| `esatto.entryMin` | 30 | `Betfair/safe_strategy/engine.py:406` | OK |
| `esatto.entryMax` | 70 | `Betfair/safe_strategy/engine.py:407` | OK |
| `esatto.maxGoalsLaySide` | 1 | `Betfair/safe_strategy/engine.py:405` | OK |
| `esatto.scoreConfirmSec` | 30 | `Betfair/safe_strategy/engine.py:408` | OK |
| `punta.minuteMin` | 66 | `Betfair/safe_strategy/engine.py:419` | OK |
| `punta.entryMin` | 1.03 | `Betfair/safe_strategy/engine.py:423` | OK |
| `punta.entryMax` | 1.1 | `Betfair/safe_strategy/engine.py:424` | OK |
| `punta.minMinutesAfterGoal` | 3 | `Betfair/safe_strategy/engine.py:426` | OK |
| `tennis.setsLeadMin` | 1 | `Betfair/safe_strategy/engine.py:431` | OK |
| `tennis.gamesLeadMin` | 2 | `Betfair/safe_strategy/engine.py:432` | OK |
| `tennis.backMin` | 1.02 | `Betfair/safe_strategy/engine.py:433` | OK |
| `tennis.backMax` | 1.1 | `Betfair/safe_strategy/engine.py:434` | OK |
| `tennis.scoreConfirmSec` | 15 | `Betfair/safe_strategy/engine.py:441` | OK |
| `tennis.setsPlayedMax` | 1 | `Betfair/safe_strategy/engine.py:437` | OK |
| `tennis.favSuperMax` | 1.2 | `Betfair/safe_strategy/engine.py:443` | OK |
| `base.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:388` | OK |
| `esatto.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:403` | OK |
| `punta.controlMin` | 0.1 | `Betfair/safe_strategy/engine.py:421` | OK |

### Mike (`Betfair/mike/config.py` `merge_params({})`) (83 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `stake` | 10.0 | `Betfair/mike/config.py:77` | OK |
| `commission_pct` | 5.0 | `Betfair/mike/config.py:78` | OK |
| `entry_hours_before_ko` | 1.0 | `Betfair/mike/config.py:85` | OK |
| `decide_min_interval_ms` | 500 | `Betfair/mike/config.py:87` | OK |
| `feed_max_age_s` | 45.0 | `Betfair/mike/config.py:95` | OK |
| `scanner_alive_max_s` | 75.0 | `Betfair/mike/config.py:101` | OK |
| `book_seen_max_s` | 90.0 | `Betfair/mike/config.py:114` | OK |
| `order_max_age_s` | 20.0 | `Betfair/mike/config.py:115` | OK |
| `order_scanner_max_s` | 30.0 | `Betfair/mike/config.py:116` | OK |
| `pre_entry_price_min` | 1.3 | `Betfair/mike/config.py:119` | OK |
| `pre_entry_price_max` | 3.0 | `Betfair/mike/config.py:120` | OK |
| `pre_min_back_size_factor` | 1.0 | `Betfair/mike/config.py:121` | OK |
| `pre_max_spread_ticks` | 6 | `Betfair/mike/config.py:124` | OK |
| `pre_green_ticks` | 2 | `Betfair/mike/config.py:125` | OK |
| `pre_entry_ttl_s` | 60 | `Betfair/mike/config.py:138` | OK |
| `pre_max_cycles` | 10 | `Betfair/mike/config.py:139` | OK |
| `pre_reentry_cooldown_s` | 60 | `Betfair/mike/config.py:140` | OK |
| `pre_last_entry_min` | 10 | `Betfair/mike/config.py:141` | OK |
| `last_entry_ticks_above` | 0 | `Betfair/mike/config.py:143` | OK |
| `veto_p_under35_soglia_130` | 0.807 | `Betfair/mike/config.py:153` | OK |
| `veto_p_under35_soglia_150` | 0.684 | `Betfair/mike/config.py:154` | OK |
| `veto_p_under35_soglia_200` | 0.514 | `Betfair/mike/config.py:155` | OK |
| `veto_p_under35_soglia_250` | 0.385 | `Betfair/mike/config.py:156` | OK |
| `veto_p_under35_soglia_300` | 0.275 | `Betfair/mike/config.py:157` | OK |
| `cancel_unmatched_after_ko_s` | 120 | `Betfair/mike/config.py:158` | OK |
| `ko_green_ticks` | 2 | `Betfair/mike/config.py:164` | OK |
| `ko_green_window_s` | 180 | `Betfair/mike/config.py:165` | OK |
| `ko_green_retry_s` | 5 | `Betfair/mike/config.py:173` | OK |
| `second_entry_stake_pct` | 50.0 | `Betfair/mike/config.py:178` | OK |
| `early_goal_cover_delay_s` | 120 | `Betfair/mike/config.py:183` | OK |
| `early_goal_cover_pct` | 50.0 | `Betfair/mike/config.py:184` | OK |
| `early_goal_cover2_delay_s` | 180 | `Betfair/mike/config.py:185` | OK |
| `cover_profit_factor` | 1.2 | `Betfair/mike/config.py:188` | OK |
| `cover_wait_hazard_max` | 0.06 | `Betfair/mike/config.py:194` | OK |
| `cover_wait_max_min` | 10 | `Betfair/mike/config.py:195` | OK |
| `cover_wait_p4_max` | 0.16 | `Betfair/mike/config.py:196` | OK |
| `cover_good_price` | 7.0 | `Betfair/mike/config.py:197` | OK |
| `cover_wait_min_gain_pct` | 8.0 | `Betfair/mike/config.py:198` | OK |
| `cover_wait_step_min` | 5 | `Betfair/mike/config.py:199` | OK |
| `cover_postgoal_delay_s` | 45 | `Betfair/mike/config.py:200` | OK |
| `cover_max_goals` | 2 | `Betfair/mike/config.py:201` | OK |
| `cover_max_overshoot_pct` | 30.0 | `Betfair/mike/config.py:203` | OK |
| `cover_rifiuti_max` | 3 | `Betfair/mike/config.py:235` | OK |
| `cover_retry_min_s` | 15 | `Betfair/mike/config.py:236` | OK |
| `cashout_profit_pct` | 5.0 | `Betfair/mike/config.py:238` | OK |
| `cashout_place_at_ticks` | 0 | `Betfair/mike/config.py:240` | OK |
| `cover_place_at_ticks` | 2 | `Betfair/mike/config.py:249` | OK |
| `cashout_smart_min_pct` | 2.0 | `Betfair/mike/config.py:264` | OK |
| `cashout_smart_tolerance_pct` | 2.0 | `Betfair/mike/config.py:265` | OK |
| `cashout_smart_hazard_hot` | 0.1 | `Betfair/mike/config.py:266` | OK |
| `cashout_smart_pressure_hot` | 1.15 | `Betfair/mike/config.py:267` | OK |
| `cashout_smart_goals_hot` | 3 | `Betfair/mike/config.py:268` | OK |
| `cashout_smart_ev_margin_pct` | 1.0 | `Betfair/mike/config.py:269` | OK |
| `close_retry_s` | 10 | `Betfair/mike/config.py:270` | OK |
| `close_max_attempts` | 20 | `Betfair/mike/config.py:271` | OK |
| `ht_loss_pct` | 25.0 | `Betfair/mike/config.py:292` | OK |
| `loss_exit_risk_premium_pct` | 10.0 | `Betfair/mike/config.py:287` | OK |
| `loss_exit_max_pct` | 0.0 | `Betfair/mike/config.py:289` | OK |
| `loss_exit_emp_min_n` | 200 | `Betfair/mike/config.py:290` | OK |
| `ht_loss_goals_min` | 3 | `Betfair/mike/config.py:296` | OK |
| `ht_loss_goals_max` | 4 | `Betfair/mike/config.py:297` | OK |
| `h2_loss_pct` | 25.0 | `Betfair/mike/config.py:299` | OK |
| `h2_loss_from_min` | 46 | `Betfair/mike/config.py:300` | OK |
| `h2_loss_to_min` | 85 | `Betfair/mike/config.py:301` | OK |
| `reentry_green_ticks` | 2 | `Betfair/mike/config.py:304` | OK |
| `reentry_max_goals` | 2 | `Betfair/mike/config.py:307` | OK |
| `reentry_until_min` | 45 | `Betfair/mike/config.py:308` | OK |
| `reentry_exit_until_min` | 0 | `Betfair/mike/config.py:310` | OK |
| `settle_confirm_s` | 60 | `Betfair/mike/config.py:316` | OK |
| `max_open_matches` | 10 | `Betfair/mike/config.py:317` | OK |
| `daily_loss_stop` | 50.0 | `Betfair/mike/config.py:318` | OK |
| `max_liability_per_match` | 0.0 | `Betfair/mike/config.py:319` | OK |
| `event_loss_cap_pct` | 100.0 | `Betfair/mike/config.py:320` | OK |
| `skip_log_interval_s` | 300 | `Betfair/mike/config.py:323` | OK |
| `feed_cache_s` | 4.0 | `Betfair/mike/config.py:338` | OK |
| `events_reload_s` | 60.0 | `Betfair/mike/config.py:342` | OK |
| `aggregates_cache_s` | 20.0 | `Betfair/mike/config.py:344` | OK |
| `reconcile_every_s` | 30.0 | `Betfair/mike/config.py:347` | OK |
| `idle_cycle_s` | 5.0 | `Betfair/mike/config.py:350` | OK |
| `publish_heartbeat_s` | 5.0 | `Betfair/mike/config.py:373` | OK |
| `publish_idle_heartbeat_s` | 60.0 | `Betfair/mike/config.py:378` | OK |
| `stats_min_s` | 10.0 | `Betfair/mike/config.py:388` | OK |
| `heartbeat_min_s` | 20.0 | `Betfair/mike/config.py:389` | OK |

### Omega (`Betfair/omega/omega_config.py` `resolve_params({})`) (66 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `price_min` | 20.0 | `Betfair/omega/omega_config.py:24` | OK |
| `price_max` | 120.0 | `Betfair/omega/omega_config.py:25` | OK |
| `ht_entry_min` | 20 | `Betfair/omega/omega_config.py:60` | OK |
| `ht_entry_max` | 40 | `Betfair/omega/omega_config.py:61` | OK |
| `ft_entry_min` | 50 | `Betfair/omega/omega_config.py:62` | OK |
| `ft_entry_max` | 80 | `Betfair/omega/omega_config.py:63` | OK |
| `model_p_max_pct` | 2.0 | `Betfair/omega/omega_config.py:64` | OK |
| `model_min_goal_distance` | 2 | `Betfair/omega/omega_config.py:65` | OK |
| `max_events` | 0 | `Betfair/omega/omega_config.py:28` | OK |
| `min_lay_liquidity` | 5.0 | `Betfair/omega/omega_config.py:30` | OK |
| `min_stake` | 0.5 | `Betfair/omega/omega_config.py:31` | OK |
| `entry_minute_min` | 30 | `Betfair/omega/omega_config.py:26` | OK |
| `entry_minute_max` | 60 | `Betfair/omega/omega_config.py:27` | OK |
| `model_empirical_max_minute` | 60 | `Betfair/omega/omega_config.py:82` | OK |
| `model_tail_factor` | 1.3 | `Betfair/omega/omega_config.py:96` | OK |
| `model_lambda_cv` | 0.3 | `Betfair/omega/omega_config.py:110` | OK |
| `select_p_band_ratio` | 2.0 | `Betfair/omega/omega_config.py:90` | OK |
| `select_k_se` | 0.0 | `Betfair/omega/omega_config.py:113` | OK |
| `select_p_hedge` | 0.5 | `Betfair/omega/omega_config.py:115` | OK |
| `select_ev_kappa` | 1.0 | `Betfair/omega/omega_config.py:116` | OK |
| `greenup_trigger_distance` | 1 | `Betfair/omega/omega_config.py:120` | OK |
| `greenup_price_trigger_ratio` | 0.5 | `Betfair/omega/omega_config.py:121` | OK |
| `greenup_settle_delay_s` | 30 | `Betfair/omega/omega_config.py:122` | OK |
| `greenup_hold_max_risk` | 0.02 | `Betfair/omega/omega_config.py:123` | OK |
| `greenup_risk_cap` | 0.15 | `Betfair/omega/omega_config.py:124` | OK |
| `greenup_risk_premium_pct` | 0.05 | `Betfair/omega/omega_config.py:129` | OK |
| `greenup_ev_margin` | 0.1 | `Betfair/omega/omega_config.py:125` | OK |
| `greenup_take_profit_frac` | 0.9 | `Betfair/omega/omega_config.py:130` | OK |
| `greenup_take_profit_minute` | 80 | `Betfair/omega/omega_config.py:131` | OK |
| `greenup_retry_s` | 20 | `Betfair/omega/omega_config.py:132` | OK |
| `greenup_max_attempts` | 15 | `Betfair/omega/omega_config.py:133` | OK |
| `greenup_market_floor_max_ratio` | 3.0 | `Betfair/omega/omega_config.py:139` | OK |
| `commission_pct` | 5.0 | `Betfair/omega/omega_config.py:29` | OK |
| `max_liability_per_match` | 0.0 | `Betfair/omega/omega_config.py:36` | OK |
| `daily_loss_cap` | 0.0 | `Betfair/omega/omega_config.py:37` | OK |
| `max_open_liability` | 0.0 | `Betfair/omega/omega_config.py:38` | OK |
| `poll_interval_s` | 20 | `Betfair/omega/omega_config.py:35` | OK |
| `paper_fill_ttl_s` | 45 | `Betfair/omega/omega_config.py:46` | OK |
| `live_fill_deadline_s` | 20 | `Betfair/omega/omega_config.py:55` | OK |
| `feed_cache_s` | 2.0 | `Betfair/omega/omega_config.py:161` | OK |
| `scanner_status_cache_s` | 10.0 | `Betfair/omega/omega_config.py:168` | OK |
| `aggregates_cache_s` | 20.0 | `Betfair/omega/omega_config.py:174` | OK |
| `sets_cache_s` | 30.0 | `Betfair/omega/omega_config.py:180` | OK |
| `results_every_s` | 60.0 | `Betfair/omega/omega_config.py:185` | OK |
| `missions_every_s` | 5.0 | `Betfair/omega/omega_config.py:190` | OK |
| `events_refresh_s` | 1800.0 | `Betfair/omega/omega_config.py:201` | OK |
| `idle_stats_s` | 60.0 | `Betfair/omega/omega_config.py:204` | OK |
| `idle_cycle_s` | 60.0 | `Betfair/omega/omega_config.py:211` | OK |
| `conto_every_s` | 120.0 | `Betfair/omega/omega_config.py:198` | OK |
| `strategy_version` | 3 | `Betfair/omega/omega_config.py:221` | OK |
| `v3_stake_eur` | 1.0 | `Betfair/omega/omega_config.py:225` | OK |
| `v3_k_minimo` | 1.11 | `Betfair/omega/omega_config.py:237` | OK |
| `v3_p_max_pct` | 2.0 | `Betfair/omega/omega_config.py:282` | OK |
| `v3_p_min_pct` | 1.0 | `Betfair/omega/omega_config.py:283` | OK |
| `v3_distanza_minima_gol` | 2 | `Betfair/omega/omega_config.py:268` | OK |
| `v3_empirical_min_n` | 200 | `Betfair/omega/omega_config.py:239` | OK |
| `v3_ht_entry_min` | 1 | `Betfair/omega/omega_config.py:250` | OK |
| `v3_ht_entry_max` | 44 | `Betfair/omega/omega_config.py:251` | OK |
| `v3_ft_entry_min` | 46 | `Betfair/omega/omega_config.py:252` | OK |
| `v3_ft_entry_max` | 85 | `Betfair/omega/omega_config.py:253` | OK |
| `v3_min_lay_liquidity` | 1.0 | `Betfair/omega/omega_config.py:264` | OK |
| `v3_max_liability_per_leg` | 95.0 | `Betfair/omega/omega_config.py:259` | OK |
| `v3_max_liability_per_match` | 190.0 | `Betfair/omega/omega_config.py:260` | OK |
| `v3_max_open_liability` | 1000.0 | `Betfair/omega/omega_config.py:261` | OK |
| `v3_daily_loss_cap` | 300.0 | `Betfair/omega/omega_config.py:262` | OK |
| `proposta_p_lose_max_pct` | 0.0 | `Betfair/omega/omega_config.py:302` | OK |

### Bot tennis (`c.get(chiave, default)` del bot; scalper: preset del runner) (22 campi numerici)

| campo | valore di serie nel Python (chiave assente) | file:riga | esito |
|---|---|---|---|
| `tennis_scalper.scalp_ticks` | 1 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:43 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:317` | OK |
| `tennis_scalper.stop_ticks` | 3 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:44 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:318` | OK |
| `tennis_scalper.signal_ticks` | 1.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:51 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:361` | OK |
| `tennis_scalper.min_flow` | 2.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:58 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:385` | OK |
| `tennis_scalper.min_size` | 5.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:54 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:352` | OK |
| `tennis_scalper.price_min` | 1.20 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:56 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:356` | OK |
| `tennis_scalper.price_max` | 6.0 | `Betfair/stream/tennis_scalper/run_tennis_scalper.py:57 (preset del runner, setdefault) e Betfair/stream/tennis_scalper/tennis_scalper_bot.py:357` | OK |
| `tennis_pro.bp_target_ticks` | 5 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:181` | OK |
| `tennis_pro.bp_stop_ticks` | 3 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:182` | OK |
| `tennis_pro.fade_target_ticks` | 4 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:186` | OK |
| `tennis_pro.min_matched` | 50_000.0 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:152` | OK |
| `tennis_pro.price_max` | 3.6 | `Betfair/stream/tennis_scalper/tennis_pro_bot.py:155` | OK |
| `tennis_flb.lay_max` | 1.10 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:80` | OK |
| `tennis_flb.green_ticks` | 8 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:85` | OK |
| `tennis_flb.green_frac` | 0.5 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:86` | OK |
| `tennis_flb.rearm_mult` | 1.10 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:82` | OK |
| `tennis_flb.min_matched` | 10_000.0 | `Betfair/stream/tennis_scalper/tennis_flb_bot.py:87` | OK |
| `tennis_swing.N` | 40 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:77` | OK |
| `tennis_swing.zin` | 2.0 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:78` | OK |
| `tennis_swing.er_max` | 0.4 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:79` | OK |
| `tennis_swing.stop_ticks` | 8 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:82` | OK |
| `tennis_swing.tmax` | 90 | `Betfair/stream/tennis_scalper/tennis_swing_bot.py:86` | OK |

chiavi senza valore di serie numerico: 0
