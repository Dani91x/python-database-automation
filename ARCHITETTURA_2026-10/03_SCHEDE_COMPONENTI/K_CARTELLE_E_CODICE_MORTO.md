# SCHEDA K - Cartelle fuori da `Betfair/` e `frontend/`, e codice morto

Perimetro: `Prediction/` (3.911 righe py), `value_engine/` (729), `tactical_engine/` (1.515), `Ai Engine/` (8.845), `market_intelligence/` (2.513 + 25.009 di JSON di cache),
`Telegram bot/` (3.071), i `*.py` di radice avviati da `.github/workflows/*.yml` e dai `.bat` (88 py di radice, 54 vivi), `laboratorio/`, `football_data_scraper/`, `sql/`, `tools/`,
piu' il codice morto dentro `Betfair/` che le schede E segnalano. Righe da `00_INVENTARIO.md` §7.1 e da `wc -l` sui file tracciati (`seasons_catchup.py` oggi 1.144 righe su disco; l'inventario
ne contava 1.022: il file e' stato modificato dal commit `d60fa53c`).
Data: 08/10/2026. Autore: delegato Sonnet. Prefisso funzionalita': `K-`.
Strumenti nuovi di questa scheda: `strumenti/k_funzioni_mai_riferite.py` -> `strumenti/inventario/uscite/k_funzioni_mai_riferite.txt` (solo lettura, nessun import del codice).

Nessuna riga di codice e' stata toccata. Nessun file e' stato spostato: questa e' una scheda di progetto.

---

## 1. Oggi

Le tabelle complete sono in `00_INVENTARIO.md`: cartelle di radice §7.1 (riga per riga, classe VIVA/ARCHIVIO/MORTA), file di radice §7.2, candidati morti §2.5 (gruppi A-D), import dinamici §2.5 e
`uscite/k02_import_dinamici.txt` (502 voci), duplicati §4, lanciatori §5.1. Non le copio. Cio' che aggiungo qui e' la lettura funzionale e la prova.

**La fotografia in dieci righe (tutte con la fonte):**

1. Fuori da `Betfair/` e `frontend/` ci sono due mondi: (a) il **cloud dei dati** (calcolo Poisson/ML/TacticAI, pagelle, segnali, recupero buchi), che gira su GitHub Actions: 10 workflow in
   `.github/workflows/` (`ls`), 9 con un lanciatore Python di radice; (b) il **relitto del primo software** (report Google Sheets e `money_management`), richiamato solo da `.bat` manuali.
2. `value_engine/` e `tactical_engine/` NON sono laboratori: stanno nel percorso dei bot. `Betfair/omega/omega_model.py:261,720-721,893` importa `value_engine.goal_timing/devig/poisson_total`;
   `Betfair/stream/engine/live_engine_pro.py:26,274-275` importa `tactical_engine.dixon_coles` e `value_engine.*`; `Betfair/safe_strategy/opportunity.py:484` e `Betfair/stream/engine/live_engine.py:57`
   importano `value_engine.goal_timing`. Di `value_engine/` sono vivi solo 3 moduli su 9 (`goal_timing`, `devig`, `poisson_total`; sezione 3).
3. `Ai Engine/` e' viva per DUE strade: il retrain cloud (`retrain_models.yml:281` -> `cloud_retrain_shard.py` -> `retrain_all_leagues.py`) e il servizio giornaliero
   (`Prediction/today_predictions_backfill.py:2730` -> `ai_engine.serving_batch.run_for_date`, `Ai Engine/ai_engine/serving_batch.py:43`).
4. `tactical_engine/` e' viva solo perche' `Prediction/today_predictions_backfill.py:2742,2752` la richiama (`serving.run_for_date`, `run_esiti_reali`) e perche' la UI legge la sua colonna
   (`frontend/src/lib/tacticalEngine.ts:61` -> `fixture_predictions.tactical_engine_json`; pannello `TacticalEnginePanel.tsx`).
5. `market_intelligence/` e' viva per UN solo import in un `try`: `Ai Engine/ai_engine/predict_fixture.py:986` (`EdgeScorer`), non-fatale. Nessun workflow la lancia (`grep -c market_intelligence .github/workflows/*` = 0);
   la sua cache JSON (`market_intelligence/cache/league_registry.json` 17.099 righe, `calibration_tables.json` 7.732, `signal_weights.json` 178) va costruita a mano con `pipeline.py --all`
   (commento in `predict_fixture.py:975-977`, `pipeline.py` 239 righe).
6. `Telegram bot/` (3.071 righe, 12 file) e' Deno/TypeScript: due Edge Functions Supabase. Nessun codice Python la usa; non si vede dal repo se e' deployata (non verificabile).
7. **Il relitto Sheets e' tenuto in vita da un workflow**: `weekly_poisson_calibration.yml:43` lancia `update_poisson_calibration.py --apply` che RISCRIVE `Betfair/money_management.py` (3.397 righe) e il
   workflow lo committa (`:60` `git add dynamic_cal.json Betfair/money_management.py dc_rho_by_league.json`). `git log --format=... -- Betfair/money_management.py`: 8 commit del bot da 17/08 a 05/10, 15 dal 01/07.
   Chi importa `money_management` in produzione? Solo `aggiorna_mm_sheets.py:37` e `aggiorna_solo_fogli.py:20` (`git grep money_management`): nessun bot, nessun servizio dell'app.
8. Documenti citati come riferimento e MAI committati: `ESECUZIONE_LIVE.md` (131 righe, 8.175 byte, citato da `CLAUDE.md`, `STATO_PRODUZIONE.md`, `Betfair/stream/tempi_ordine.py`), `SPEC_STRATEGIA_S.md` (183 righe, citato da
   `CLAUDE.md` e dai CHECKPOINT/COSTITUZIONE di `Betfair/safe_strategy/`), `TENNIS_BOT_DOSSIER.md` (655 righe, 49.504 byte, citato anche da `Betfair/stream/backtest/registro_bot.py`), `SAFE_STRATEGY_DOSSIER.md`
   (342 righe, citato da `MATRICE_CONSAPEVOLEZZA_ORDINI_2026-09-16.md`). `git ls-files <nome> | wc -l` = 0 per tutti e quattro; esistono sul disco.
9. Codice morto con prova: 23 moduli (3.419 righe) a zero citazioni (00 §2.5) + 3 moduli di Ai Engine/radice senza importatori (191 righe) = gruppo A, 26 moduli, 3.610 righe; 41 script a riga di
   comando senza alcuna citazione (6.486 righe); 1.164 righe di ricerca tennis; 5.722 righe del relitto Sheets; 45 funzioni mai riferite (318 righe, strumento nuovo).
10. Non c'e' alcun import dinamico che raggiunga i moduli di questa scheda tranne i punti noti (`registro_bot.py:66,133`; `omega_service.py:8815`; `bot_service.py:285`; `replay_registrazioni.py:914`):
    `git grep -nE "runpy|importlib|__import__|spec_from_file_location"` sui `.py` di produzione non cita nessun modulo di radice o delle cartelle K.

---

## 2. Funzionalita' (NON si perdono)

Chi le avvia e' scritto accanto. Il cloud gira da GitHub Actions; il locale da `.bat` o da `desktop/main.js`.

### 2.1 Il cloud dei dati (workflow -> script)

- K-001 **Recupero «ieri» ogni notte**: `daily_yesterday_backfill.yml:5` (cron `12 1 * * *` UTC) -> `daily_yesterday_backfill.py:36` (396 righe): riempie fixture/partite/statistiche del giorno prima usando i mattoni
  `season_gaps.py`/`per_fixture_backfill.py`. [cloud]
- K-002 **Pronostici del giorno** (3 motori in un job): `today_predictions_backfill.yml:5` (cron `18 2 * * *`; `:44,46` `python -m Prediction.today_predictions_backfill`) -> `run_for_date` `Prediction/today_predictions_backfill.py:2399`:
  motore Poisson/Dixon-Coles `compute_db_json_analisi` `:1418` (rho per lega `get_league_rho` `:1162`, fiducia lega `get_league_trust_scores` `:528`, leghe tossiche `get_toxic_leagues` `:709`),
  motore ML `:2730` (`ai_engine.serving_batch`), motore TacticAI `:2742`, esiti reali TacticAI `:2752`; scrittura differita `_DeferredWriter` `:1988`, copertura `predictions_coverage_true` `:731`. Scrive
  `fixture_predictions` (`db_json_analisi`, `model_predictions_json`, `tactical_engine_json`). [UI: Dashboard, `TacticalEnginePanel.tsx`]
- K-003 **Esito reale dei pronostici**: `predictions_results_backfill.yml:6` (cron `23 3 * * *`, `:78,80`) -> `Prediction/predictions_results_backfill.py:743` `run`: `evaluate` `:434` confronta pronostico e risultato,
  `bulk_update_predictions` `:632` con ripiego riga per riga `:547`. [cloud]
- K-004 **Catena a valle dello stesso workflow** (stessa notte): `build_analytics_signals.py` `:96` (tabella `analytics_signals`, 452 righe), `merge_engine_signals.py` `:108` (engine_signals -> centro di controllo, 280),
  `enrich_analytics_snapshots.py` `:131,133` (frequenze/ritardi point-in-time, 583), `refresh_analytics_bets.py` `:148` (`analytics_bets`, un giorno alla volta, 281), `build_direzione.py` `:163`
  (pagella `direction_pagella` per motore poisson/ml/tacticai, 238). Moduli puri condivisi: `analytics_market_stats.py` (307), `analytics_settlement.py` (125). [UI: pagine Analytics/Direzione]
- K-005 **Calibrazione Poisson settimanale** (lunedi' 03:27 UTC, `weekly_poisson_calibration.yml:5`): Step 1 `generate_dynamic_cal.py:36` scrive `dynamic_cal.json` (26.304 righe) E la tabella DB `poisson_calibration`
  (`generate_dynamic_cal.py:438-461`, upsert); Step 2 `update_poisson_calibration.py --apply` `:43` riscrive `CALIBRATION_TABLE` dentro `Betfair/money_management.py:199` (nessuna scrittura DB: solo letture,
  `update_poisson_calibration.py:146,183`); Step 3 `generate_dc_rho.py` (riga `:54` del workflow `weekly_poisson_calibration.yml`; [chiarito dal verificatore 08/10]) scrive `dc_rho_by_league.json` (182 righe). Commit automatico `:60`. Letture a valle: `live_engine_pro.py:37-38` (`_RHO_PATH`, `_CAL_PATH`),
  `Prediction/today_predictions_backfill.py:1169` (rho), `poisson_calibrator.py:60` (DB-first, JSON come ripiego). [Bot: Omega/Safe via motore; Step 2 nessun consumatore vivo]
- K-006 **Post-calibrazione ML**: `ml_calibration.yml:28` (cron `14 5 * * *` + `workflow_run` dopo il retrain, `:23`) -> `compute_ml_post_calibration.py:78` -> tabella `ml_post_calibration`, letta da
  `Ai Engine/ai_engine/predict_fixture.py:373` (`_load_post_calibration`). [cloud]
- K-007 **Retrain ML cloud a shard**: `retrain_models.yml:55` (cron `19 8 * * *`) -> `cloud_retrain_shard.py:281` (373 righe: shard round-robin, ritentativi) con `training_planner.py` (293: sceglie quali leghe riaddestrare
  con poche query) e `retrain_all_leagues.py` (631); cache Optuna `Ai Engine/models_cache/**/optuna_params_*.json` (`retrain_models.yml:25-28`). [cloud]
- K-008 **Recupero buchi di dati**: `seasons_catchup.yml:36` (cron `47 13 * * *`, `:102`) -> `seasons_catchup.py` (1.144) sopra i mattoni `season_gaps.py` (679: «cosa manca» derivato dai dati),
  `season_backfill.py` (240), `season_aggregates.py` (282), `fixtures_backfill.py` (210), `standings_backfill.py` (381), `injuries_backfill.py` (354), `top_scorers/assists/cards_backfill.py` (380/380/404),
  `per_fixture_backfill.py` (1.216); quota API in `api_quota.py` (345). A mano: `league_orchestrator.py` (262, stessi mattoni). [cloud]
- K-009 **Mappatura leghe** mensile: `leagues_mapper.yml:13` (giorno 1, 00:12 UTC; `:47`) -> `leagues_mapper.py` (406). [cloud]
- K-010 **Validazione walk-forward dei modelli** (manuale, sola lettura): `validate_models.yml:16,91` -> `validate_walkforward.py` (138). [cloud, a richiesta]
- K-011 **Atlante hazard dello scalper** (notturno dopo il Daily): `hazard_atlas.yml:109` -> `python -m Betfair.stream.scalper.genera_atlante` (dominio scheda E4; qui solo l'elenco). Lancia anche
  `migrations/` python da `hazard_atlas.yml:91`.
- K-012 **Librerie condivise del cloud**: `db_client.py` (410, importato da 108 file: l'unico accesso al DB), `api_client.py` (137, 14 importatori, incluso `Betfair/stream/scores/api_football.py`), `config.py` (58, 17),
  `logger.py` (100, 9), `db_delete_retry.py` (53, 6), `master_backtest.py` (1.660: importato da `generate_dc_rho.py` e altri 2), `poisson_calibrator.py` (215), `ventaglio_segnali.py` (350; vedi D-K08).

### 2.2 Locale: avviato da `desktop/main.js` o da `.bat`

- K-013 **Quote tennis «Partite del Giorno»**: `desktop/main.js:480` -> `betfair_tennis_odds.py` (322): tutti i mercati tennis di oggi, back+lay+volume, in tabella `tennis_markets`. [UI: pagina tennis]
- K-014 **Quote complete calcio**: `aggiorna_report.bat:30` e UI (`BetfairOddsPanel.tsx:110`) -> `betfair_full_odds.py` (300) -> tabella `betfair_market_odds`. [UI: `BetfairOddsPanel.tsx`]
- K-015 **Import operazioni Betfair nel Report Personale**: `aggiorna_report_betfair.bat:21`, `importa_ultimi_15_giorni.bat:19` -> `import_betfair_operations.py` (428) -> `personal_trades`. [UI: Report Personale]
- K-016 **Server HTTP quote+ordini pre-match a mano**: `aggiorna_quote_betfair.bat:9` -> `start_order_server.py` (56, `127.0.0.1:8787 /place-order`); la UI lo cita come istruzione (`frontend/src/lib/betfair.ts:102`). [UI: istruzione]
- K-017 **Retrain manuale**: `aggiorna_modelli.bat:28` -> `retrain_all_leagues.py` (631). [a mano]
- K-018 **Pipeline Google Sheets / report** (relitto; vedi D-K05): `aggiorna_report.bat:21,25` -> `Betfair/betfair_report_manager.py` (1.737) e `aggiorna_mm_sheets.py` (542); `aggiorna_solo_fogli.bat:10` ->
  `aggiorna_solo_fogli.py` (46) -> `Betfair/money_management.py` `SlotManager` `:263`. La UI mostra il comando come istruzione (`frontend/src/components/dashboard/MatchesList.tsx:278`).
- K-019 **Avviatori di servizio citati dalla UI**: `avvia_omega_service.bat` (`ManualPanel.tsx:362`), `avvia_scalper_service.bat` (`HabitatCard.tsx:66`), `start_backtest_worker.bat`, `stream_api.bat`,
  `install_worker_autostart.ps1`, `fetch_logs.ps1`, `fetch_summary.ps1`: tutti ARCHIVIO per l'inventario (nessun lanciatore automatico), ma sono istruzioni mostrate all'utente.

### 2.3 `Prediction/` (3.911 righe py: 2.789 + 875 + 247)

- K-020 `today_predictions_backfill.py` (2.789): vedi K-002. Anche: retry/backoff DB `_db_execute` `:236`, `_is_transient_db_error` `:204`; costruzione griglia punteggi e `_dc_tau` `:1131,1193`; finestre 5/10/15 gare
  `_window_stats`/`_blend_windows` `:1359,1398`; promozione dei segnali `build_promoted_and_summary` `:1821`; quote Betfair per lega-stagione `fetch_odds_for_league_season` `:823`.
- K-021 `predictions_results_backfill.py` (875): vedi K-003. Anche `fetch_predictions_ok_for_date` `:223`, `fetch_matches_map` `:355`, riconoscimento di RPC assente `_is_rpc_missing_error` `:530`.
- K-022 `AGGIORNA_CAMPO_db_json_analisi.py:49` (radice, 404) e `Prediction/backfill_historical_analysis.py:20` (146) richiamano `compute_db_json_analisi`: ricalcolo storico a mano (script manuali, vedi D-K03).
- K-023 `Prediction/analyze_sweet_spot.py` (101): analisi a mano, nessun chiamante.

### 2.4 `value_engine/` (729 righe py)

- K-024 `goal_timing.py` (61): quota di gol del primo tempo `first_half_share` `:37` e frazione residua `remaining_frac` `:44`, dalla CDF `value_engine/data/goal_time_cdf.json`. Usata da Omega (`omega_model.py:261`),
  Safe (`opportunity.py:484`), motore live (`live_engine.py:57`). **Cambia le decisioni dei bot: intoccabile.**
- K-025 `devig.py` (29): `devig_pair` `:22` toglie il margine a una coppia di quote; usata da `omega_model.py:720,893` e `live_engine_pro.py:274`. Intoccabile.
- K-026 `poisson_total.py` (81): `lam_from_prematch` `:46` (lambda dal prematch, bisezione `brentq` `:15`), `cond_prob_total` `:64`; usata da `omega_model.py:721` e `live_engine_pro.py:275`. Intoccabile.
- K-027 `calibrate.py` (103): rigenera la CDF dei minuti dei gol dal DB (`fetch_goal_minutes` `:26`, `build_cdf` `:63`): e' il PRODUTTORE del file che K-024 legge; script a mano, nessun lanciatore.
- K-028 `bivariate.py` (210), `markets.py` (60), `pricing.py` (38), `cli.py` (55), `generate_battery.py` (78), `test_bivariate_mc.py` (130): NESSUN importatore di produzione
  (`git grep "value_engine\.(bivariate|markets|pricing)"` -> solo `generate_battery.py:10-13`, `markets.py:57`, `test_bivariate_mc.py:11`). Sono il «calcolatore» a mano del Telegram bot e la sua batteria di validazione.

### 2.5 `tactical_engine/` (1.515 righe py)

- K-029 `serving.py` (369): `run_for_date` `:192` (adatta il modello alle partite del giorno per lega, `_load_prior` `:108`, `_build_payload` `:159`) e `run_esiti_reali` `:315` (esito reale a 90' sui payload delle finite).
  Avviato da `Prediction/today_predictions_backfill.py:2742,2752`. [UI: `TacticalEnginePanel.tsx`, `tacticalEngine.ts:61`]
- K-030 `model.py` (282): `DixonColesModel` `:86` (`fit` `:103`, `predict` `:239`, tabella forza `:259`, limiti di rho `_rho_limits_all_pairs` `:59`).
- K-031 `dixon_coles.py` (144): `dc_tau` `:23`, `score_matrix` `:61`, `markets_from_matrix` `:83`, `rho_bounds` `:40`. **`score_matrix` e' importata dal motore live** (`live_engine_pro.py:26`): intoccabile.
- K-032 `data_loader.py` (84) e `report.py` (105): usati solo dagli script a mano `run_worldcup.py` (161) e `_verify_data_worldcup.py` (87).
- K-033 `tools/verifica_payload_tacticai.py` (233): verifica a mano del payload (test: `tests/test_verifica_payload.py` 176). Test della cartella: 4 file `tactical_engine/tests/` (`test_serving.py` 349, `test_math.py` 167, ...).

### 2.6 `Ai Engine/` (8.845 righe py di produzione, 54 file tracciati)

- K-034 `ensemble_trainer.py` (1.519) addestramento ensemble; `seriea_model_export.py` (734) `train_and_save_all`/`upload_and_register` (usate da `retrain_all_leagues.py:42`, `betfair_report_manager.py:27`);
  `feature_pipeline.py` (869); `db_adapter.py` (442); `targets.py` (205); `model_suite.py` (189); preprocessing/ (4 file, 568 righe).
- K-035 `predict_fixture.py` (1.124): `predict_fixture` `:667` (modelli dal bucket `_download_model` `:78`, registro `:502`, post-calibrazione `:373`, edge di Market Intelligence `:986`); `serving_batch.py` (109) `run_for_date` `:43`
  lo applica a tutte le partite del giorno (K-002). Scrive `fixture_predictions.model_predictions_json`.
- K-036 `confidence_gate.py` (283: 4 cancelli `gate_data_sufficiency` `:44`, `gate_model_agreement` `:98`, `gate_value_present` `:129`, `gate_calibration_quality` `:170`, `apply_all_gates` `:239`), `value_betting.py`
  (386: EV, Kelly, `evaluate_bet_opportunities` `:148`; allineato per commento a `money_management.py`, `value_betting.py:35,54-55`). **Chi li chiama non e' stato verificato** (vedi sezione «non verificato»).
- K-037 Test: `Ai Engine/ai_engine/tests/` (3 file, 1.538 righe). Documentazione: 6 `.md` in `Ai Engine/`.

### 2.7 `market_intelligence/` (2.513 righe py)

- K-038 `edge_scorer.py` (540): `EdgeScorer` `:434`, `score_fixture_from_row` `:282` (edge composito per segnale: bias di calibrazione, divergenza ML, direzione xG). Unica funzione viva: chiamata da `predict_fixture.py:986`.
- K-039 `audit.py` (235) `run_audit` `:93`, `calibration.py` (303) `run_calibration` `:245`, `signals.py` (460) `run_signals` `:353`, `pipeline.py` (239): producono la cache JSON letta da K-038 (a mano, `pipeline.py --all`).
  `backtest.py` (361) e `backtest_audit.py` (283): solo a mano.

### 2.8 `Telegram bot/` (Deno, 3.071 righe)

- K-040 `supabase/functions/telegram-bot/index.ts` (811): comandi `/start` `:157`, `/calc` `:154` (`handleCalcTotal` `:105`), `/scalc` `:155` (`handleCalcScore` `:129`), `/partite` `:163`, bottoni `callback_query` `:170`,
  `Deno.serve` `:799`; `calc.ts` (219) replica in TypeScript `value_engine` (`bivariate`/`pricing`): la parita' con Python e' provata da `_calc_validation/battery.json` (1.249 righe) + `validate.mts` (33).
- K-041 `supabase/functions/make-daily-post/index.ts` (317): legge `fixture_predictions` `:29`, compone il post del giorno e carica immagini nel bucket Storage `Loghi` `:253,263`. Stato di deploy: non verificabile.

### 2.9 Altre cartelle

- K-042 `laboratorio/` (20 file, 5.356 righe py): copia di lavoro dello scalper (`scalper_lab/scalper_bot_base.py`, `grid_strategy.py` 485, `theta`...) e `tennis_lab/`; NESSUN import da `Betfair/` (test
  `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py:356` `test_laboratorio_non_importato_da_betfair_ne_da_desktop`). Ordine dell'utente del 25/09 (`AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md`).
- K-043 `football_data_scraper/` (7 file, 1.392 righe, ultimo commit 13/03/2026): scraper storico, nessun importatore, nessun lanciatore.
- K-044 `tools/` (5 file): `omega_validate_models.py`, `omega_watch.py`, `replay_barra_fixture.py` (citato dai fixture frontend `replayBarraTutte.ts:8,44`), `test_replay_barra_fixture.py`, `review/review-control-room.js`.
- K-045 `sql/` (9 file: SQL + 4 script py `_build_wc_xlsx_2013.py` ...) e `migrations/` (175 file, 33.835 righe SQL; le applica l'utente).
- K-046 Tipi di lancio `.github/workflows` verso `Betfair/`: `hazard_atlas.yml` (K-011) e il test `Betfair/conftest.py`. Non ce ne sono altri in `.github/` (`grep -n "python " .github/workflows/*.yml`).

---

## 3. Difetti strutturali

### 3.1 Codice morto con PROVA

**Controprova di persona su 8 dei 23 moduli (oltre i 5 chiesti)** con `git grep -nIw <stem>` su TUTTO il repo (py, js, ts, yml, bat, ps1, md; escluso solo `ARCHITETTURA_2026-10`):

| modulo | righe | esito di `git grep -w` | giudizio |
|---|---:|---|---|
| `analyze_recovery.py` | 283 | 0 righe | morto: nessuna citazione, nessun `__main__` |
| `simulate_recovery_forward.py` | 287 | 0 righe | morto |
| `report_mm.py` | 202 | 0 righe | morto |
| `calibration_analysis.py` | 622 | solo `POISSON_AUDIT.md:44,77` (documento di audit) | morto per il codice; il documento lo cita come diagnostica |
| `tmp_smoke_stack.py` | 138 | `Ai Engine/ML_TRAINING_AND_STACK.md:63,97,111` come comando di verifica («deve stampare STACK SMOKE PASSED») | morto per il codice, **documentato come runbook**: decisione |
| `laboratorio/scalper_lab/grid_strategy.py` | 485 | solo documenti AUDIT del 25/09 e il docstring del test di contratto `test_contratto_strada_unica_2026_09_25.py:44,277` (commenti sul vecchio percorso) | morto; non e' un import |
| `refresh_dashboard.py` / `update_dashboard_only.py` | 20 / 31 | solo `INVENTARIO_COMPONENTI_2026-09-25.md:574` | morti (usavano `money_management.SlotManager`, relitto Sheets) |
| `Betfair/cleanup_reset.py` | 32 | solo `MANUALE_OPERATIVO.md:343` (`python Betfair/cleanup_reset.py`) | morto per il codice, **documentato nel manuale**: decisione |

Altri 15 del gruppo A: `_certify_betfair_full.py` 37, `check_gh.py` 13, `analyze_threshold.py` 308, `tmp_analysis.py` 188, `tmp_analysis2.py` 139, `tmp_predict_today.py` 117, `tmp_today_predictions.py` 141,
`tmp_validate_league.py` 66, `tmp_validate_predict.py` 76, `tactical_engine/_check_fixpred.py` 24, `tactical_engine/_inspect_mismatch.py` 21, `value_engine/generate_battery.py` 78 (importa `value_engine.*`
ma nessuno importa lui), `Ai Engine/ai_engine/analysis/advanced.py` 90, `models/voting.py` 21: prova nell'inventario (`s08_morti_verifica.tsv`, esito ZERO), invariata dalla rilettura a campione.
**Gruppo A = 26 moduli, 3.610 righe** (`s02_morti.txt`); i 3 «citati per parola generica» (`analysis/summary.py` 25, `models/trainer.py` 154, `parse.py` 12): rilevo di persona che
`git grep -nE "analysis.summary|models.trainer|import parse|from parse"` non trova alcun import (l'unico `from .advanced_validation` di `Ai Engine/ai_engine/runner.py:13` e' un altro modulo).
**Correzione al brief**: il brief dice «23 moduli ~3.400 righe»; sono 23 a ZERO citazioni (3.419) piu' 3 con stem generico senza importatori (191).

- D-K01 **Gruppo A, 24 moduli, 3.440 righe, prova piena di morte** (i 26 meno `tmp_smoke_stack.py` e `cleanup_reset.py`, per i due runbook). Ultimo commit tra 18/02 e 24/06/2026 (22 su 23 dei morti certi; `grid_strategy.py` 25/09).
- D-K02 **Due moduli morti ma documentati come comando** (170 righe: `tmp_smoke_stack.py`, `Betfair/cleanup_reset.py`): vedi sopra, decisione dell'utente.
- D-K03 **41 script a riga di comando senza alcuna citazione, 6.486 righe** (elenco in `00_INVENTARIO.md` §2.5 «Gruppo B senza alcuna citazione»; ricalcolato di persona: 41 voci, 6.486 righe). Non sono dimostrabilmente morti:
  si lanciano a mano. Per sottogruppo: certificazioni di giugno in radice `_certify_*`/`_league_eval`/`_stack_eval`/`certify_backtest_strategy` 1.464; manutenzione calibrazione/modelli
  (`backfill_poisson_calibrated`, `load_poisson_calibration_to_db`, `cleanup_models`, `compress_models`, `reset_ai_models`, `missing_fixtures_backfill`, `sanity_check`, `admin_reset_password`) 1.165;
  `tmp_smoke_*`/`tmp_train_today`/`valida_*` 765; `Ai Engine` 1.037; `Prediction` 247; `tennis_scalper/{record_tennis,tune_tennis}` 232; `laboratorio` 329; `sql/*.py` 651; `football_data_scraper/fix_snapshot_time.py` 65;
  `market_intelligence/backtest_audit.py` 283; `tactical_engine` 248. Somma 6.486.
- D-K04 **Funzioni mai riferite nei moduli di produzione: 45, 318 righe** (strumento nuovo: nome presente UNA sola volta in tutto il corpus di `.py`/`yml`/`js`/`ts`/`bat`, test inclusi: limite per difetto, un test che lo cita lo
  salva). Le piu' grosse nei bot: `Betfair/stream/scalper/validazione_hazard/parita.py:18` `confronta_v3` 40 (modulo D, solo audit), `Betfair/stream/runner.py:1864` `_is_finished_stale` 17,
  `Betfair/omega/omega_model.py:1167` `rank_by_cover_cost` 16 (selezione v2), `Betfair/omega/omega_engine.py:1190` `cap_di_gamba_v3` 6, `Betfair/safe_strategy/bot_db.py:368` `open_trades_auto` 6,
  `Betfair/stream/tennis_live/guardie_tennis.py:155` `client_paper_del_framework` 6, `Betfair/client.py:159` `logout_local` 6, `Betfair/stream/saldo_evento.py:243` `_process_order` 5,
  nel cloud `per_fixture_backfill.py:203` `delete_existing_for_fixture` 32, `Prediction/today_predictions_backfill.py:901` `upsert_odds_row` 14, `:1895` `upsert_prediction_row` 6.
  **Falsi positivi certi**: `Betfair/stream/odds_http.py:103,108,217` (`do_OPTIONS`, `do_POST`, `log_message`: sovrascritture di `BaseHTTPRequestHandler`, chiamate dal framework). Il resto da confermare
  una per una (decoratori, `getattr` per stringa, hook di flumine) prima di toccarlo: **decisione/azione per le schede E, non per K**.
- D-K05 **Relitto Sheets**: `Betfair/money_management.py` 3.397 + `Betfair/betfair_report_manager.py` 1.737 + `aggiorna_mm_sheets.py` 542 + `aggiorna_solo_fogli.py` 46 = **5.722 righe**, piu'
  `update_poisson_calibration.py` 606 (il cui solo scopo e' riscrivere `money_management.py`: docstring `:13-20`; nessuna scrittura DB, `:146,183`) e le `.bat` `aggiorna_report.bat`, `aggiorna_report_veloce.bat`, `aggiorna_solo_fogli.bat`.
  Prova: importatori di `money_management` = `aggiorna_mm_sheets.py:37`, `aggiorna_solo_fogli.py:20`; di `betfair_report_manager` = `aggiorna_report.bat:21`, `aggiorna_report_veloce.bat:17`. **Effetto collaterale**: il workflow
  committa sul ramo principale una riscrittura settimanale di un file di 3.397 righe che nessun bot legge (15 commit `github-actions[bot]` dal 01/07). Duplicati: `master_backtest.py:124-131`
  «copia esatta» di `CALIBRATION_TABLE` (`money_management.py:199`), costanti allineate «a mano» in `Ai Engine/ai_engine/value_betting.py:54-55`, `master_backtest.py:48,54-58`, `generate_dynamic_cal.py:57,188`;
  `Betfair/betfair_match.py:16-28` ricopia `normalize_name` di `betfair_report_manager` (se il report manager esce, `betfair_match.py` diventa la copia unica).
  **Non e' dimostrabile che l'utente non usi piu' i fogli**: per questo e' una decisione.
- D-K06 **Ricerca tennis in produzione: 1.164 righe** in 7 file di `Betfair/stream/tennis_scalper/` (`record_multi` 333, `backtest_pro` 169, `tune_tennis` 161, `run_tennis_pro` 159, `flb_backtest` 141, `research_data` 130,
  `record_tennis` 71; `wc -l` = 1.164). Nessun importatore: le citazioni sono commenti (`tennis_recorder.py:4,7,10,20,56`, `tennis_runner.py:627,1674`, `tennis_opportunity.py:128`: «non importato»,
  `tennis_pro_bot.py:133`) e la mappa di classificazione del test `Betfair/stream/tests/test_valuta_k1_2026_09_26.py:442-450` (che li nomina per stringa: va aggiornata se si spostano). Scheda E5 gia' lo riporta.
- D-K07 **Motori legacy Omega: 1.023 righe** (v1 207 + `_model_select` 107 + green-up v2 709: `E2_OMEGA.md` righe 81-98), raggiungibili solo con `strategy_version=2` (default 3: `Betfair/omega/omega_config.py:221`).
  **Non e' codice morto**: e' strategia selezionabile e coperta dagli scenari del banco. Riportato qui per completezza: decide l'utente (E2).
- D-K08 **Morti per transitivita'**: `ventaglio_segnali.py` (350) e' importato da UN solo file di produzione, `valida_ventaglio.py` (archiviabile in D-K03); `analytics_settlement.py` e' importato anche da `_certify_direction_report.py`
  (B con citazione dalla UI) ma resta vivo per `build_analytics_signals.py`. Se D-K03 passa, `ventaglio_segnali.py` perde l'ultimo importatore.
- D-K09 **Parametri morti Mike (E1 §D7)**: `ko_green_retry_s` (`Betfair/mike/config.py:173`, commento `:165-172` «NON HA PIU' EFFETTO», letto da nessun ramo) e `event_loss_cap_pct` (`config.py:320`, citato in
  `engine.py:5019` ma non applicato; la UI lo dichiara «NON ATTIVO» `frontend/src/lib/mike.ts:557`). Presenti in 5 posti (config, `mike.ts:482,557,585,603`, `replay_registrazioni.py:2216`, `replayBotCatalogo.ts` x5, test). Togliere
  le chiavi romperebbe i parametri salvati nel DB: **non si propone**; resta la decisione E1 sul «cap perdita per partita» (cambierebbe la strategia).
- D-K10 **Documenti citati e non tracciati**: 4 file, 1.311 righe, ~96 KB, mai committati (sezione 1, punto 8). Una clonazione pulita perde le istruzioni a cui `CLAUDE.md` rimanda.

### 3.2 Duplicazioni (con le righe gemelle)

- **DC tau / griglia di punteggi / Poisson in 3 posti**: `value_engine/bivariate.py:39` `dc_tau`, `:52` `score_matrix`, `:30` `pois`; `tactical_engine/dixon_coles.py:23` `dc_tau`, `:61` `score_matrix`, `:18` `poisson_pmf`;
  `Prediction/today_predictions_backfill.py:1193` `_dc_tau`, `:1131` `_build_score_grid`, `:1120` `_poisson_prob`; piu' `value_engine/poisson_total.py:37` `p_le`. Il motore live importa la versione di `tactical_engine` (`live_engine_pro.py:26`):
  le altre due sono copie di calcolo. **Non si unificano di iniziativa**: i numeri devono coincidere al bit prima (sezione 5).
- **Market Intelligence**: `_find_betfair_bm` x3 (`edge_scorer.py:108`, `signals.py:51`, `calibration.py:52`), `_parse_bookie_odd` x2 (`edge_scorer.py:122`, `signals.py:66`; variante `calibration.py:62`),
  `_compute_outcome` x2 (`signals.py:88`, `calibration.py:84`), `_get_ml_prob` x2 (`edge_scorer.py:192`, `signals.py:32`).
- **Tactical**: `_reg_goals`/`_ht_goals` in `serving.py:65,75` e `data_loader.py:23,34` (identici per nome e funzione).
- **Ritentativo DB in 2 dialetti**: `Prediction/predictions_results_backfill.py:88,109` (`_is_transient_error`, `_exec_with_retry`) contro `Prediction/today_predictions_backfill.py:204,236` (`_is_transient_db_error`,
  `_db_execute`); in piu' `db_delete_retry.py` (53) e `db_client.py`.
- **Allineamenti «a mano»** (rischio di deriva): `CALIBRATION_TABLE` `money_management.py:199` / `master_backtest.py:131`; Kelly/stake in `value_betting.py:54-55` e `master_backtest.py:48`.
- **Inversione di dipendenza**: `Ai Engine/ai_engine/predict_fixture.py:983-986` aggiunge `market_intelligence` a `sys.path` a runtime; `Prediction/today_predictions_backfill.py:2726-2730` aggiunge `Ai Engine` a `sys.path`
  (nessun pacchetto installabile): per questo l'AST dell'inventario non vede alcuni legami (limiti noti §2.5).

### 3.3 Accoppiamenti

- Un modulo grande fa tutto: `Prediction/today_predictions_backfill.py` 2.789 righe (retry DB, Poisson, quote, scrittura differita, orchestrazione di 3 motori); `master_backtest.py` 1.660 usato come libreria da `generate_dc_rho.py`.
- Un solo workflow (`predictions_results_backfill.yml`) fa 7 passi in sequenza (`:78-163`): un passo rosso ferma i successivi? Non verificato (richiede leggere i `continue-on-error`).
- I bot dipendono da `value_engine/` e `tactical_engine/` per importazione di funzioni di matematica (K-024..K-026, K-031): se si tocca il layout di cartella, si toccano 4 file di produzione dei bot: `omega_model.py`, `opportunity.py`, `live_engine.py`, `live_engine_pro.py` (sezione 4).

---

## 4. Domani

**Principio**: archiviare = `git mv` in `archivio/` con `archivio/INDICE.md` (modulo, righe, ultimo commit, perche', chi l'ha deciso, come ripristinarlo). Mai cancellare senza decisione dell'utente.
Niente cambia ne' nei bot ne' nelle strategie.

### 4.1 Struttura nuova per questa fetta

| oggi | domani | tipo |
|---|---|---|
| `Prediction/` + py di radice del cloud + `.github/workflows/` | `cloud/` (UN componente: `cloud/COSA_FA.md`, `cloud/contratto.md` = elenco workflow -> script -> tabelle scritte) | spostamento (non in questa scheda; il numero di py di radice del cloud e' in 00 §7.2) |
| `value_engine/` (3 moduli vivi) + `tactical_engine/dixon_coles.py` | `matematica_condivisa/` (`goal_timing`, `devig`, `poisson_total`, `dixon_coles`) importata da Omega, Safe, motore live | accorpamento, solo dopo la parita' di sezione 5 |
| `Ai Engine/`, `tactical_engine/`, `market_intelligence/` | restano sotto `cloud/motori/` | spostamento |
| `Telegram bot/` | resta; `COSA_FA.md` | nessuno |
| codice morto (D-K01..D-K08) | `archivio/` con indice | archiviazione |

Contratto proposto (solo i punti di contatto con i bot, con i tipi): `goal_timing.first_half_share() -> float`, `goal_timing.remaining_frac(t: float, T: float = 90.0) -> float`,
`devig.devig_pair(o: float, o_opp: float) -> float`, `poisson_total.lam_from_prematch(side: str, k: int, prob: float) -> float`,
`dixon_coles.score_matrix(lambda_home: float, lambda_away: float, rho: float, ...) -> np.ndarray`: firme lette da `value_engine/goal_timing.py:37,44`, `devig.py:22`, `poisson_total.py:46`, `tactical_engine/dixon_coles.py:61`.
Nessuna firma cambia.

### 4.2 Lotti di archiviazione, ordine e righe (incrementali, nessuna sovrapposizione)

| lotto | contenuto | file | righe | stato della prova |
|---|---|---:|---:|---|
| **L1** | D-K01: gruppo A meno i 2 con runbook | 24 | **3.440** | **prova piena** (0 importatori, 0 lanciatori, 0 stringhe, 0 `__main__`) |
| L2 | D-K02: `tmp_smoke_stack.py`, `Betfair/cleanup_reset.py` | 2 | 170 | morti per il codice; **decisione per l'utente** (documento li cita) |
| L3 | D-K03 (41 script manuali senza citazioni) + `ventaglio_segnali.py` (D-K08) | 42 | 6.836 | **decisione per l'utente** (si lanciano a mano) |
| L4 | D-K05: relitto Sheets (`money_management`, `betfair_report_manager`, `aggiorna_mm_sheets`, `aggiorna_solo_fogli`, `update_poisson_calibration`) + 3 `.bat` + Step 2 del workflow | 5 py (+3 bat) | 6.328 | **decisione per l'utente** (non e' provabile che i fogli non servano) |
| L5 | D-K06: i 5 file di `tennis_scalper/` non gia' in L3 | 5 | 932 | **decisione per l'utente** (scheda E5; aggiornare `test_valuta_k1...:442-450`) |
| L6 | cartelle gia' ARCHIVIO: resto di `laboratorio/` (4.542), `football_data_scraper/` (1.327), `sql/*.py` (258) | ~30 | 6.127 | **decisione per l'utente** (ordine del 25/09 sul laboratorio) |
| - | D-K04 funzioni mai riferite | 45 fn | <= 294 netti | schede E: una per una, **non qui** |

Totale che esce dal codice vivo: **L1 3.440 con prova piena**; con tutte le decisioni accolte **23.833 righe** (3.440 + 170 + 6.836 + 6.328 + 932 + 6.127; le sovrapposizioni tra gli elenchi sono gia' tolte). Piu' i `.bat`/`.ps1`, che non hanno righe py. **Cosa NON esce mai**: i 4 documenti non tracciati vanno committati, non archiviati (D-K10).

Ordine: L1 -> (utente decide) L2/L3 -> L5 -> L4 con le sue 3 modifiche collegate -> L6. Un commit per lotto (reversibile con `git revert`).

Modifiche collegate (necessarie, una per lotto, tutte da fare con permesso):
- L4: togliere dal workflow `weekly_poisson_calibration.yml` lo Step 2 (`:36-43`) e `Betfair/money_management.py` dal `git add` (`:60`); cambiare i commenti `Ai Engine/ai_engine/value_betting.py:35,54-55`
  e `master_backtest.py:124`. Se i fogli servono ancora, L4 salta e basta (nulla va rotto).
- L5/L3: aggiornare la mappa `Betfair/stream/tests/test_valuta_k1_2026_09_26.py:442-450` e il test di contratto `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py:356` (resta vero se `laboratorio/` sparisce: nessun import).
- L2: aggiornare `MANUALE_OPERATIVO.md:343` e `Ai Engine/ML_TRAINING_AND_STACK.md:63,97,111`.
- Frontend: `DirezioniReport.tsx` e `lib/reportistiche.ts` citano `_certify_direction_report.py` (641 righe, B con citazione: **NON compreso in nessun lotto**); `MatchesList.tsx:278`, `betfair.ts:102`, `ManualPanel.tsx:362`, `HabitatCard.tsx:66`
  mostrano comandi `.bat`: se un `.bat` sparisce, va corretta la stringa della UI (con `npm run build`).

### 4.3 Rischi (import dinamici e simili)

1. `registro_bot.py:66,133` (`import_module` dei `certificazione.py`), `omega_service.py:8815`, `bot_service.py:285`, `replay_registrazioni.py:914` e le 502 voci di `k02_import_dinamici.txt`: nessuna cita un modulo dei lotti
   (da riconfermare con lo script della sezione 5 prima di ogni `git mv`).
2. `sys.path.insert` a runtime (K-035, `Prediction:2726`): un modulo in `Ai Engine/` o `market_intelligence/` e' raggiunto per percorso, non per import; non muovere queste cartelle senza lo script di chiusura (sezione 5).
3. Script manuali che l'utente usa a mano e che il repo non vede: la classificazione «dice cosa il REPO collega, non cosa l'utente lancia a mano sul suo PC» (00 §7). Per questo L2-L6 sono decisioni.
4. Il workflow e' lanciato sul ramo principale: ogni modifica a `.github/workflows/` si prova con `workflow_dispatch` PRIMA del cron della notte (K-002..K-008 girano tra 00:12 e 13:47 UTC).
5. `Ai Engine/models_cache/` e `Ai Engine/reports/` sono dati locali e non vanno toccati.

### 4.4 Confronto «per sostituire OGGI / DOMANI»

- Oggi: per cambiare la matematica Poisson serve toccare `value_engine/*`, `tactical_engine/dixon_coles.py`, `Prediction/today_predictions_backfill.py:1120-1210` e, per i fogli, `Betfair/money_management.py`
  (4 posti, 3 cartelle). Domani: `matematica_condivisa/` + test di contratto.
- Oggi per spegnere i fogli Google si toccano workflow, 2 `.bat` UI-citati, `betfair_match.py:16` e 4 moduli. Domani: una riga di indice in `archivio/INDICE.md` e il workflow senza Step 2.

**Cosa e' gia' in una libreria matura e oggi e' riscritto**: il Poisson/`pois`/`poisson_pmf` (3 copie) esiste in `scipy.stats.poisson`; il Kelly in `value_betting.py:111`; la ricerca di zero `brentq`
(`value_engine/poisson_total.py:15`, `bivariate.py:110` `_bisect`) esiste in `scipy.optimize.brentq`. **Non si sostituiscono di iniziativa**: i numeri dei bot devono restare identici al bit (richiede la sezione 5), e `scipy` non e' tra le
dipendenze del servizio dei bot (non verificato).

---

## 5. Parita' (come si prova che l'archiviazione non rompe nulla)

Per L1-L6 il codice che ESCE non e' raggiunto da nulla di vivo; la prova e' quindi **di non-raggiungibilita'**, non di uguaglianza di numeri. Va fatta in un worktree con le giunzioni di `PROCESSO_STANDARD_BOT.md`/`CLAUDE.md`
(rmdir delle junction PRIMA di rimuovere il worktree; MAI `--force`).

1. **Chiusura di raggiungibilita' prima/dopo** (script da scrivere in `strumenti/`, AST + stringhe): insieme dei moduli raggiunti a partire da (a) i comandi `run:` di ogni workflow, (b) gli `spawn` di `desktop/main.js:419,427,469,480`,
   (c) `Betfair/stream/avvio_app.py`/`watchdog.py`, (d) la lista di `registro_bot.py:66,133`, (e) ogni `.bat` richiamato da altro. Deve essere IDENTICA prima e dopo (stesse stringhe, stesso insieme di file), sottratti i soli file archiviati.
2. **Suite**: `python -m pytest Betfair/ -q -p no:cacheprovider` (stesso numero di passati/saltati di prima), piu' i test fuori da `Betfair/`: i 20 `test_*.py` di radice (`00 §7.2`), `Prediction/test_*.py`,
   `tactical_engine/tests/`, `Ai Engine/ai_engine/tests/`, `value_engine/test_bivariate_mc.py`. Un test che citava un file archiviato deve restare verde dopo l'aggiornamento della sua mappa (L5, L6).
3. **Avvio dei servizi**: per ogni voce `spawn` di `desktop/main.js` e per ogni comando `python <file>` dei workflow, verifica che il file esista (`test -f`) e che `python -c "import ast; ast.parse(open(f).read())"` passi; `python -m compileall` sui
   pacchetti. NON eseguire i servizi, non chiamare Betfair/API/DB (condizione del brief).
4. **Workflow**: `workflow_dispatch` dei workflow toccati in un ramo di prova, in sola lettura quando possibile (`validate_models.yml` e' gia' sola lettura); confronto del commit generato prima/dopo (`dynamic_cal.json`,
   `dc_rho_by_league.json` identici byte per byte con gli stessi dati).
5. **Matematica condivisa** (solo se si accorpa `value_engine`/`dixon_coles`): confronto bit a bit su una griglia di input (stesse `lam`, `mu`, `rho`) tra la copia vecchia e la nuova per `dc_tau`, `score_matrix`, `lam_from_prematch`, `devig_pair`,
   `goal_timing.*` + i replay `base`/`apertura` di Omega, Safe, Mike dal punto d'ingresso unico `python -m Betfair.stream.backtest.certifica <bot> ...` (durata da dichiarare: certificazione completa 5 min, tetto 10, `PROCESSO_STANDARD_BOT.md` §6.9)
   con referto IDENTICO numero per numero a quello di oggi.
6. **UI**: `npx tsc -p tsconfig.app.json --noEmit` a 0 errori e `npx vitest run` se si cambia una stringa del frontend (L4/L5).
7. **Voci di `PROCESSO_STANDARD_BOT.md`**: §6 (copertura del banco: scenari, referto riproducibile) e §7 (catalogo dei 35 errori) si applicano solo ai lotti che toccano codice dei bot (L5 e le funzioni di D-K04, schede E); per L1-L4 e L6 le voci
   sono ⊘ con causa «nessun codice di bot toccato, provato dalla chiusura di raggiungibilita' (punto 1)». Falsificazione: spostare di proposito un modulo VIVO (p.es. `value_engine/devig.py`) deve rendere rosso lo script del punto 1 e `pytest`.

---

## 6. Migrazione

1. **Prima di tutto**: committare i 4 documenti non tracciati (D-K10) se l'utente lo vuole; senza di loro `CLAUDE.md` rimanda a file che un clone non ha.
2. **L1** da solo (prova piena): `git mv` in `archivio/` + `archivio/INDICE.md` (generato da `s02_morti.txt`), sezione 5 punti 1-3. Nessun interruttore, nessun periodo ombra: i moduli non sono raggiunti da nulla.
3. **L2-L6**: solo dopo decisione scritta dell'utente, un lotto alla volta (L5 con la scheda E5, L4 con la decisione sui fogli); periodo «ombra» = un ciclo completo dei workflow (una notte: 00:12-13:47 UTC) con il confronto automatico del punto 4.
4. **Matematica condivisa**: ultimo passo e solo con parita' bit a bit (sezione 5 punto 5); dopo la Fase 1 dei bot, mai insieme.
5. **Ritorno indietro**: `git revert` del commit di lotto; i file stanno in `archivio/` con la storia (`git mv` conserva la cronologia).
6. Mai: `git add -A` (log da 3 GB), `npm install` nel checkout principale con l'app viva, processi nuovi, ricompilare l'exe.

---

## 7. Misure (righe prima -> dopo)

| voce | prima | dopo (se le decisioni passano) | fonte |
|---|---:|---:|---|
| gruppo A (morti con prova) | 3.610 (26 moduli) | 0 nel vivo (L1 3.440 + L2 170) | `s02_morti.txt` |
| script a mano senza citazioni | 6.486 (41) + 350 transitivi | 0 | 00 §2.5, sezione 3 D-K03/D-K08 |
| relitto Sheets | 5.722 + 606 + 3 `.bat` | 0 | `wc -l`, D-K05 |
| ricerca tennis | 1.164 (di cui 232 gia' in L3) | 0 | D-K06 |
| cartelle gia' ARCHIVIO | `laboratorio` 5.356, `football_data_scraper` 1.392, `sql` py 909 | 0 nel vivo | 00 §7.1 |
| funzioni mai riferite | 318 righe in 45 funzioni | <= 24 dopo la conferma (falsi positivi `odds_http.py`) | `k_funzioni_mai_riferite.txt` |
| commit automatici sul ramo principale per il relitto | 15 (da 01/07: file `money_management.py`) | 0 | `git log -- Betfair/money_management.py` |
| **totale archiviato** | | **3.440 con prova piena; 23.833 con tutte le decisioni** (3.440 + 170 + 6.836 + 6.328 + 932 + 6.127) | sezione 4.2 |
| righe Python di produzione fuori da `Betfair/` nelle cartelle K | 8.845 + 3.911 + 2.513 + 1.515 + 729 + 5.356 + 1.392 + 909 = 25.170 | 25.170 - (quota di L1..L6 in queste cartelle) | 00 §7.1 |

Obiettivo di velocita' dei controlli: chiusura di raggiungibilita' < 1 minuto (sola lettura AST); `pytest Betfair/` come oggi (non misurato qui: «niente suite intere»).
Numeri che NON esistono e lo strumento che li misurerebbe: tempo di esecuzione dei workflow notte per notte (`gh run list --workflow <nome> --json` per ognuno dei 10); peso del repo prima/dopo (`git count-objects -vH`).

---

## Decisioni per l'utente

1. **L1** (24 moduli, 3.440 righe, prova piena): posso archiviarli in `archivio/` con indice? (Reversibile.)
2. **L2**: `tmp_smoke_stack.py` e `Betfair/cleanup_reset.py` sono documentati come comando in `ML_TRAINING_AND_STACK.md` e `MANUALE_OPERATIVO.md`: li lanci ancora a mano?
3. **L3**: i 41 script manuali (certificazioni di giugno, manutenzione modelli, `sanity_check`, `admin_reset_password`, ...): archiviare, tenere, o scegliere uno per uno? (`admin_reset_password.py` e `reset_ai_models.py` sono attrezzi di emergenza.)
4. **L4, i fogli Google**: «Report Ven Dom», «Analytics», «MM Dashboard» (`aggiorna_report.bat`) li usi ancora? Se no, si togliono dal workflow lo Step 2 e il file `money_management.py` dal commit settimanale e si archivia il relitto.
   Se si', si lasciano ma si decide se il workflow deve continuare a committare ogni lunedi'.
5. **L5**: la ricerca tennis (1.164 righe) esce dal pacchetto di produzione verso `laboratorio/`? (Aggiorna il test `test_valuta_k1...:442-450`.)
6. **Documenti non committati** (`ESECUZIONE_LIVE.md`, `SPEC_STRATEGIA_S.md`, `TENNIS_BOT_DOSSIER.md`, `SAFE_STRATEGY_DOSSIER.md`): li committo (il coordinatore committa su tuo ordine)? Cosi' `CLAUDE.md` e `registro_bot.py` non puntano a file assenti.
7. **Motori legacy Omega** (1.023 righe, `strategy_version=2`) e **parametri morti Mike** (`ko_green_retry_s`, `event_loss_cap_pct`): non sono codice morto, sono strategia o compatibilita' dei salvataggi: restano alla scheda E1/E2, decide l'utente.
8. `Telegram bot/`: le due Edge Functions sono deployate? Se no, si archivia la cartella (3.071 righe; il suo calcolatore e' `value_engine/bivariate.py`, `pricing.py`, `markets.py`).
9. `market_intelligence/`: l'unico uso vivo e' l'arricchimento non-fatale `predict_fixture.py:986` e la cache va costruita a mano: la tieni (con un lanciatore) o la archivi (2.513 righe + 25.009 di JSON)?

## Cosa ho verificato di persona

- `git grep -nIw` su tutto il repo per `analyze_recovery`, `calibration_analysis`, `report_mm`, `tmp_smoke_stack`, `grid_strategy`, `update_dashboard_only`, `simulate_recovery_forward`, `refresh_dashboard`, `advanced`, `voting`,
  `cleanup_reset`, `_certify_betfair_full`, `check_gh`, `_check_fixpred`, `_inspect_mismatch`, `generate_battery`; importatori di `money_management`/`betfair_report_manager`/`value_engine.*`/`market_intelligence`/`tactical_engine`;
  lettori di `dynamic_cal.json`/`dc_rho_by_league.json`; commit del bot su `money_management.py` e `dynamic_cal.json` (`git log`).
- Lettura dei 10 workflow (cron e comandi `python`), degli indici di funzioni di `Prediction/`, `value_engine/`, `tactical_engine/`, `market_intelligence/`, `Ai Engine/predict_fixture.py`, delle docstring dei 41 script di radice vivi.
- Somme di righe del gruppo B (41 voci = 6.486) ricalcolate da `s02_morti.txt`; strumento nuovo `k_funzioni_mai_riferite.py` eseguito (solo lettura).
- Parametri morti di Mike (`config.py:173,320`) e catalogo UI (`mike.ts:482,557`); 4 documenti non tracciati (`git ls-files` = 0, `wc -l` sul disco).

## NON ho potuto verificare

- Se l'utente usa ancora i fogli Google, i 41 script manuali, il Telegram bot (deploy) o la cache di Market Intelligence: non e' scritto nel repo.
- Chi chiama `confidence_gate.py` e `value_betting.py` in `Ai Engine/` (non ho eseguito la grep; vanno controllate prima di qualunque archiviazione).
- Se un passo rosso di `predictions_results_backfill.yml` ferma i successivi (`continue-on-error` non letti riga per riga).
- Che `scipy` sia disponibile nell'ambiente dei bot (per le sostituzioni con librerie mature).
- Le 45 funzioni mai riferite: solo 3 falsi positivi certi (`odds_http.py`); le altre non sono state lette una per una.
- Il numero esatto di test passati prima/dopo (nessuna suite lanciata, per la regola del brief).
