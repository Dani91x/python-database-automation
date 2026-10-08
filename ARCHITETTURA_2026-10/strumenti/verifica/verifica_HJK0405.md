# Verifica indipendente H, J, K, 04, 05 (08/10/2026)

Verificatore: Sonnet 5.5, sola lettura del codice. Campione estratto con `estrai_campione.py` (seme fisso): 25 citazioni per H, J, K; 20 per 04 e 05.
Metodo: per ogni citazione ho risolto il file (`git ls-files`), letto le righe citate e giudicato se il codice dice quello che il documento afferma.
Esiti: CONF = confermata, SPOS = spostata (entro +-15 righe), FALSA.

## Conteggi

| Documento | CONFERMATE | SPOSTATE | FALSE |
|---|---:|---:|---:|
| H_BANCO_REPLAY | 25 | 0 | 0 |
| J_FRONTEND | 25 | 0 | 0 |
| K_CARTELLE_E_CODICE_MORTO | 25 | 0 | 0 |
| 04_ARCHITETTURA_OBIETTIVO | 20 | 0 | 0 |
| 05_PIANO_DI_MIGRAZIONE | 20 | 0 | 0 |

Nessuna FALSA e nessuna SPOSTATA nel campione. Una citazione ambigua (K riga 66) e' stata chiarita nel testo; due note di precisione (J riga 363, 05 riga 604) sono in coda.

## H_BANCO_REPLAY.md

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 141 | certifica.py:576 | Betfair/stream/backtest/certifica.py | CONF | `quanti_processi` a 576, `_esegui_compiti` a 616, `_prepara_figlio` a 551: tutti esatti |
| 193 | replayBot.ts:228-236 | frontend/src/lib/replayBot.ts | CONF | `request_backtest` (228) e `get_replay_bot_esito` (236) |
| 469 | banco_comune.py:1844 | Betfair/stream/backtest/banco_comune.py | CONF | `LATENZA_LETTURA_S = 0.120` |
| 365 | flumine/streams/historicalstream.py:259-275 | .venv/Lib/site-packages/flumine/streams/historicalstream.py | CONF | `FlumineHistoricalGeneratorStream._read_loop` a 259-275; `GeneratoreLibri` a 1847 |
| 217 | banco_comune.py:390 | banco_comune.py | CONF | `__getattr__` che registra il metodo mancante |
| 429 | replay_tennis.py:589 | Betfair/safe_strategy/tools/replay_tennis.py | CONF | chiamata `replay_evento(...)`; 17 scenari in `SCENARI_DESCRITTI` (riga 352) |
| 219 | sim_strategy.py:100 | Betfair/stream/backtest/sim_strategy.py | CONF | `class SimStrategy`; `run_backtest.py:405` e' `FlumineSimulation(...)` |
| 124 | worker.py:41-58 | Betfair/stream/backtest/worker.py | CONF | ramo `applica_bot`, poi `run_backtest(params)`; `db.py:710` `claim_backtest_request` |
| 67 | safe_strategy/tools/replay_registrazioni.py:940-1377 | idem | CONF | `_crea_strategia` a 940; la funzione successiva e' a 1380. Mike 485-1283 (poi 1286), Omega 1210-1760 (poi 1766) confermati |
| 301 | banco_comune.py:1642 | banco_comune.py | CONF | `_IMPRONTA_CHIUSURA_FLUMINE = "43ee8df0...e57c"`, identico al testo |
| 361 | applica_bot.py:67 | Betfair/stream/backtest/applica_bot.py | CONF | `SCENARI_APPLICABILI`; `:155` `SCENARI_SCARTATI` |
| 69 | banco_comune.py:2954-3030 | banco_comune.py | CONF | `class _Ponte(BaseStrategy)` a 2954; il blocco arriva a ~3031 (77 righe come dichiarato) |
| 479 | applica_bot.py:365 | applica_bot.py | CONF | `catalogo_ts`, testata "GENERATO"; `:875-892` e' `main()` con `--catalogo-ts` |
| 361 | registro_bot.py:219-243 | Betfair/stream/backtest/registro_bot.py | CONF | `BotRegistrato(nome="mike", ...)` |
| 86 | replay_tennis.py:589 | replay_tennis.py | CONF | `_replay_evento` usato solo da `safe_tennis` e dagli strumenti omega (`misura_ingresso_passivo.py`) e safe (`sonda_righe_scan`): `git grep` conferma |
| 102 | certifica.py:472-479 | certifica.py | CONF | obiettivo 300 s, tetto 600 s |
| 132 | applica_bot.py:365 | applica_bot.py | CONF | `frontend/src/lib/replayBotCatalogo.ts` = 11.099 righe |
| 41 | stream/scalper/tools/replay_registrazioni.py:1789 | Betfair/stream/scalper/tools/replay_registrazioni.py | CONF | `FlumineSimulation(client=BC.cliente_simulato())`. Le 9 costruzioni del perimetro del banco sono confermate da `git grep` |
| 41 | omega/tools/replay_registrazioni.py:2066 | Betfair/omega/tools/replay_registrazioni.py | CONF | |
| 41 | stream/tennis_live/tools/replay_bot.py:1375 | Betfair/stream/tennis_live/tools/replay_bot.py | CONF | |
| 486 | db.py:710-747 | Betfair/stream/db.py | CONF | `claim_backtest_request` a 710, `write_replay_bot_esito` a 746 |
| 282 | banco_comune.py:2954-3030 | banco_comune.py | CONF | come sopra (`_Ponte._giro`) |
| 217 | omega/tools/replay_registrazioni.py:609 | Betfair/omega/tools/replay_registrazioni.py | CONF | `aggregates(self, day_start=None)` 609, `aggregates_coppia` 615; il vero `omega_db.aggregates(day_start=None, mode=None)` e' a `omega_db.py:777` (il documento scrive `omega/db.py`, abbreviazione, vedi 04 riga 964) |
| 456 | banco_comune.py:1844 | banco_comune.py | CONF | come sopra |
| 97 | tennis_live/tools/replay_bot.py:139 | replay_bot.py | CONF | `SCENARI_DESCRITTI`, 17 chiavi contate con AST |

CONF 25, SPOS 0, FALSE 0.

## J_FRONTEND.md

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 140 | pages/ControlRoom.tsx:173 | frontend/src/pages/ControlRoom.tsx | CONF | `export default function ControlRoom()` |
| 165 | ControlRoom.tsx:871 | idem | CONF | `<details data-testid="cr-catena-dettagli">` con "Da Betfair al tuo schermo" |
| 363 | safeBot.ts:688-810 | frontend/src/lib/safeBot.ts | CONF | `SAFE_RISK_DEFAULTS` 688, `SAFE_BOT_DEFAULTS` 701, `strategyParamsOf` 805-810 |
| 244 | BotOrdersPanel.tsx:13 | frontend/src/components/replay/BotOrdersPanel.tsx | CONF | |
| 160 | useCashOutPartita.ts:1 | frontend/src/components/controlroom/useCashOutPartita.ts | CONF | intestazione "il cash out della partita con i prezzi AL MS" |
| 144 | FasciaStop.tsx:70 | frontend/src/components/controlroom/testata/FasciaStop.tsx | CONF | `CONFERMA_SCADE_MS = 10_000` a 70 |
| 207 | pages/Mike.tsx:74 | frontend/src/pages/Mike.tsx | CONF | `export default function Mike()` |
| 244 | ParametriBotPanel.tsx:131 | frontend/src/components/replay/ParametriBotPanel.tsx | CONF | |
| 166 | tennisAuto.ts:1 | frontend/src/components/controlroom/tennisAuto.ts | CONF | "AUTO-MODE DEI 4 BOT TENNIS" |
| 174 | EquityCard.tsx:31 | frontend/src/components/trading/EquityCard.tsx | CONF | |
| 106 | watchlist.ts:110 | frontend/src/lib/watchlist.ts | CONF | `addToWatchlist` -> rpc `add_to_watchlist` |
| 158 | controlroom/SchedaPartita.tsx:278 | frontend/src/components/controlroom/SchedaPartita.tsx | CONF | |
| 310 | TennisMatchStats.tsx:314 | frontend/src/components/tennis/TennisMatchStats.tsx | CONF | |
| 157 | EsitoAbbinamentoStriscia.tsx:24 | frontend/src/components/controlroom/EsitoAbbinamentoStriscia.tsx | CONF | |
| 174 | StoricoLink.tsx:51 | frontend/src/components/trading/StoricoLink.tsx | CONF | |
| 363 | tennis.ts:719-848 | frontend/src/lib/tennis.ts | CONF | `TENNIS_BOT_REGISTRY` inizia a 719 e chiude a 833 (115 righe, il documento ne conta 130: la coda 834-848 e' commento + `subscribeTennisBots`). Nota di precisione, non correzione |
| 78 | desktop/preload.js:21 | desktop/preload.js | CONF | token di sessione esposto con `contextBridge` |
| 415 | lib/uiShell.ts:44 | frontend/src/lib/uiShell.ts | CONF | `leggiUiShell()` |
| 90 | SafeStrategy.tsx:138 | frontend/src/pages/SafeStrategy.tsx | CONF | `setInterval(load, 15_000)` |
| 150 | safestrategy/BotParamsSheet.tsx:527 | frontend/src/components/safestrategy/BotParamsSheet.tsx | CONF | |
| 363 | omega.ts:959-1250 | frontend/src/lib/omega.ts | CONF | `OMEGA_PARAM_DEFAULTS` 959, gruppi fino a ~1250 |
| 74 | ResetPassword.tsx:28 | frontend/src/pages/ResetPassword.tsx | CONF | |
| 156 | controlroom/UsciteColonna.tsx:33 | frontend/src/components/controlroom/UsciteColonna.tsx | CONF | |
| 174 | PerformancePanel.tsx:119 | frontend/src/components/trading/PerformancePanel.tsx | CONF | |
| 242 | TradeForm.tsx:67 | frontend/src/components/watchlist/TradeForm.tsx | CONF | |

CONF 25, SPOS 0, FALSE 0. Riscontri a margine: `DayBar.tsx` ha 19 `data-testid` come scritto; `cashOutPartita.ts` e `esitoAbbinamento.ts` hanno `wc -l` 706 e 707 (il documento dice 707 e 708: scarto di 1, conteggio con riga finale).

## K_CARTELLE_E_CODICE_MORTO.md

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 189 | Prediction/today_predictions_backfill.py:901 | idem | CONF | `upsert_odds_row`; `:1895` `upsert_prediction_row` e `per_fixture_backfill.py:203` `delete_existing_for_fixture` confermati |
| 167 | test_contratto_strada_unica_2026_09_25.py:44 | Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py | CONF | docstring a 44 e commento a 277 citano `grid_strategy`; il file vero e' `laboratorio/scalper_lab/grid_strategy.py` (485 righe) |
| 214 | live_engine_pro.py:26 | Betfair/stream/engine/live_engine_pro.py | CONF | `from tactical_engine.dixon_coles import dc_tau, score_matrix`; `_dc_tau` 1193, `_build_score_grid` 1131, `_poisson_prob` 1120, `p_le` 37 tutti esatti |
| 133 | predict_fixture.py:986 | Ai Engine/ai_engine/predict_fixture.py | CONF | `from market_intelligence.edge_scorer import EdgeScorer`; `edge_scorer.py` 540 righe, `EdgeScorer` 434, `score_fixture_from_row` 282 |
| 72 | seasons_catchup.yml:36 | .github/workflows/seasons_catchup.yml | CONF | cron `47 13 * * *`; `:102` e' `run: python seasons_catchup.py` |
| 66 | live_engine_pro.py:37-38 | live_engine_pro.py | CONF | `_RHO_PATH`, `_CAL_PATH` |
| 250 | value_engine/goal_timing.py:37 | value_engine/goal_timing.py | CONF | `first_half_share` 37, `remaining_frac` 44; `poisson_total.py:46` `lam_from_prematch`, `tactical_engine/dixon_coles.py:61` `score_matrix`, `devig.py:22` `devig_pair` |
| 202 | Betfair/omega/omega_config.py:221 | Betfair/omega/omega_config.py | CONF | `"strategy_version": (3, int, 2, 3)` default 3 |
| 303 | desktop/main.js:419 | desktop/main.js | CONF | `spawnRunner('runner-calcio', ...)`; 427 scalper, 469 backtest-worker, 480 tennis-odds esatti |
| 66 | update_poisson_calibration.py:146 | update_poisson_calibration.py (radice) | CONF | lettura `fixture_predictions`; 183 lettura `matches`; nessuna scrittura DB nel file |
| 293 | bivariate.py:110 | value_engine/bivariate.py | CONF | `_bisect` |
| 293 | value_engine/poisson_total.py:15 | value_engine/poisson_total.py | CONF | `brentq` (bisezione pura) |
| 67 | poisson_calibrator.py:60 | poisson_calibrator.py (radice) | CONF | `_DYNAMIC_CAL_PATH` |
| 222 | Prediction/today_predictions_backfill.py:2726-2730 | idem | CONF | aggiunge `Ai Engine` a `sys.path`; `predict_fixture.py:983-986` aggiunge `market_intelligence` |
| 110 | generate_battery.py:10-13 | value_engine/generate_battery.py | CONF | `git grep` conferma: solo `generate_battery.py:13`, `markets.py:57`, `test_bivariate_mc.py:11` |
| 250 | devig.py:22 | value_engine/devig.py | CONF | `devig_pair` (file di 29 righe come scritto) |
| 59 | predictions_results_backfill.yml:6 | .github/workflows/predictions_results_backfill.yml | CONF | cron `23 3 * * *`; `predictions_results_backfill.py:743` `run`, `:434` `evaluate` |
| 279 | omega_service.py:8815 | Betfair/omega/omega_service.py | CONF | import dinamico `__import__("db_client")`; `registro_bot.py:66,133`, `bot_service.py:285`, `replay_registrazioni.py:914` sono tutti `importlib.import_module` |
| 26 | retrain_models.yml:281 | .github/workflows/retrain_models.yml | CONF | `python cloud_retrain_shard.py` |
| 66 | generate_dc_rho.py:54 | .github/workflows/weekly_poisson_calibration.yml | CONF (chiarita) | `:54` e' la riga `run: python generate_dc_rho.py` del WORKFLOW, non del .py (nel .py la riga 54 e' un import). Stessa convenzione di `:43` (Step 2) e `:60` (git add). Testo chiarito, vedi correzioni |
| 106 | omega_model.py:720 | Betfair/omega/omega_model.py | CONF | `from value_engine.devig import devig_pair`; `:893` e `live_engine_pro.py:274` idem |
| 110 | test_bivariate_mc.py:11 | value_engine/test_bivariate_mc.py | CONF | |
| 221 | value_betting.py:54-55 | Ai Engine/ai_engine/value_betting.py | CONF | `MAX_KELLY`, `KELLY_FRACTION`; `master_backtest.py:48` e `:131`, `money_management.py:199` esatti |
| 99 | Prediction/backfill_historical_analysis.py:20 | idem | CONF | import di `compute_db_json_analisi`; file di 146 righe, `AGGIORNA_CAMPO_db_json_analisi.py` 404 righe |
| 274 | betfair.ts:102 | frontend/src/lib/betfair.ts | CONF | stringa "aggiorna_quote_betfair.bat" |

CONF 25, SPOS 0, FALSE 0. Numeri a margine confermati: `dc_rho_by_league.json` 182 righe, `dynamic_cal.json` 26.304, `_certify_direction_report.py` 641.

## 04_ARCHITETTURA_OBIETTIVO.md

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 959 | exits.py:431-440 | Betfair/safe_strategy/exits.py | CONF | freschezza della riga del feed per le uscite, due soglie diverse |
| 706 | main.js:937 | desktop/main.js | CONF | `app.on('window-all-closed', ... shutdownAndQuit())` |
| 795 | omega_service.py:1432 | Betfair/omega/omega_service.py | CONF | chiamata `_minute_table(db, ...)`, funzione a 1319 che usa `db.minute_transitions` (RPC); 1444 `_empirical_table` |
| 880 | avvio_app.py:173-215 | Betfair/stream/avvio_app.py | CONF | `uscite_a_manuali` 172-214 |
| 59 | service.py:4159 | Betfair/mike/service.py | CONF | `D.build_prematch(eid, db)` (dossier all'armamento) |
| 883 | bot_db.py:951 | Betfair/safe_strategy/bot_db.py | CONF | `fetch_scan_rows` |
| 883 | mike/db.py:553 | Betfair/mike/db.py | CONF | `fetch_scan_rows` |
| 793 | mike/dossier.py:66-111 | Betfair/mike/dossier.py | CONF | `build_prematch` 66-111 |
| 879 | avvio_app.py:173-215 | avvio_app.py | CONF | |
| 88 | main.js:229-575 | desktop/main.js | CONF | blocco di log figli, spawn e spegnimento ordinato (chiude a 574) |
| 700 | main.js:401-410 | desktop/main.js | CONF | `child.on('exit')` si limita a loggare: nessun riavvio, "nessuno sorveglia i watchdog"; `:419-469` sono gli `spawnRunner` |
| 829 | ambiente_runner.js:75 | desktop/ambiente_runner.js | CONF | `LIVE_RISK_ENGINE_POLL_SEC: '0.15'`; `config_stream.py:311` default `"1.0"` |
| 847 | safe_strategy/stream.py:418-427 | Betfair/safe_strategy/stream.py | CONF | nuova subscription senza ripresa `initialClk/clk` |
| 643 | stream/db.py:26-37 | Betfair/stream/db.py | CONF | `_is_statement_timeout` (57014) |
| 643 | motore_ordini.py:20-30 | Betfair/stream/motore_ordini.py | CONF | diario write-ahead JSONL con flush e fsync |
| 177 | mike/service.py:146-149 | Betfair/mike/service.py | CONF | `read_book` -> `omega_market.read_book` (Mike importa Omega); `bot_service.py:302` `_omega_service`; `mike/engine.py:33` importa `ticks_between` dallo scalper |
| 877 | omega_service.py:900-935 | Betfair/omega/omega_service.py | CONF | `score_from_payload` e feed punteggio |
| 964 | Betfair/omega/omega_db.py:777 | Betfair/omega/omega_db.py | CONF | `aggregates(day_start=None, mode=None)` a 777; il finto di Omega senza `mode` a `replay_registrazioni.py:609,615` |
| 846 | flumine/streams/streams.py:110-121 | .venv/Lib/site-packages/flumine/streams/streams.py | CONF | `add_stream`: fonde solo sottoscrizioni con filtri identici |
| 959 | mike/feed.py:458-478 | Betfair/mike/feed.py | CONF | `order_fresh` 458 |

CONF 20, SPOS 0, FALSE 0.

Controllo numerico su 5 affermazioni del riepilogo "In una pagina":

| Affermazione in 04 | Fonte | Esito |
|---|---|---|
| codice vivo 381.554 righe, -10,4% (-39.645) e -17,5% (-66.922) | riga 900: 219.378 + 35.486 + 125.573 + 1.117 = 381.554; 39.645/381.554 = 10,39%; 66.922/381.554 = 17,54%; addendi di riga 922 = 27.277 = 66.922 - 39.645 | CONF |
| coda DB p50 492 / p99 26.636 ms (07 §3.2) | `07_MISURE_OGGI.md` righe 31 e 159 | CONF |
| da 18 processi Python permanenti + 1 job a 8 (I §4.1) | scheda I riga 284 | CONF |
| per cambiare la strada di un ordine almeno 24 file Python (C §4.7); 7 strade e 9 riconciliazioni | scheda C riga 442 ("almeno 24 file Python"), riga 264 ("Sette strade"), riga 258 (9 riconciliazioni) | CONF |
| connessioni 10/10 nel caso peggiore (A §1.3) | scheda A righe 401 e 603 | CONF |

Non verificato: "per sostituire Omega 12 aree (E2 §4.5)": la scheda E2 riga 433 elenca le aree ma la cifra 12 non compare letteralmente; non l'ho ricontata una per una.

## 05_PIANO_DI_MIGRAZIONE.md

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 264 | omega_service.py:8541 | Betfair/omega/omega_service.py | CONF | `_maybe_keepalive` -> `market.keep_alive()`: punto di sessione Betfair, coerente con la lista dei punti di login (`safe_strategy/service.py:3367` `build_client(login=True)`, `tennis_runner.py:3122`, `runner.py:2618`) |
| 311 | stream/db.py:644 | Betfair/stream/db.py | CONF | upsert `live_run_log`; 697 insert `live_alerts`; 988 insert `betfair_live_journal` |
| 932 | runner.py:1267 | Betfair/stream/runner.py | CONF | `_lifecycle_blockers`: guardia "non e' sicuro spegnersi" |
| 505 | pages/Omega.tsx:274-301 | frontend/src/pages/Omega.tsx | CONF | due `setInterval(..., 15_000)` a 274 e 301 |
| 603 | applica_bot.py:67 | Betfair/stream/backtest/applica_bot.py | CONF | `SCENARI_APPLICABILI`; `:155` `SCENARI_SCARTATI` |
| 387 | omega_service.py:1-1137 | omega_service.py | CONF | intestazione modulo a 1; 1137 inizio `_entry_marks`; 7752 dopo `EVENTS_REFRESH_EVERY_S`; 8936 `main()` finale |
| 621 | desktop/main.js:937 | desktop/main.js | CONF | |
| 463 | mike.ts:175-330 | frontend/src/lib/mike.ts | CONF | interfaccia `MikeLive` a 175, tipi fino a 330 |
| 294 | omega_db.py:1040-1081 | Betfair/omega/omega_db.py | CONF | `upsert_daily_goal`... `minute_transitions` (KO a 1079); 736-776 sezione "CONSULENTE DATI (advisor)" |
| 634 | opportunity.py:484 | Betfair/safe_strategy/opportunity.py | CONF | `from value_engine.goal_timing import first_half_share, remaining_frac` |
| 634 | live_engine.py:57 | Betfair/stream/engine/live_engine.py | CONF | import `remaining_frac` |
| 269 | omega_market.py:89-112 | Betfair/omega/omega_market.py | CONF | `call_mutating`: mai ritentata su errore generico |
| 525 | tennis_runner.py:3121-3400 | Betfair/stream/tennis_live/tennis_runner.py | CONF | `setup_and_run` a 3121, corpo fino a oltre 3400 |
| 310 | mike/db.py:71-81 | Betfair/mike/db.py | CONF | `log(kind, payload, event_id)` insert in `T_ACTIVITY` |
| 293 | omega_service.py:1305-1380 | omega_service.py | CONF | `_minute_table` 1319, `_rho_for` 1378 |
| 463 | mike/engine.py:33 | Betfair/mike/engine.py | CONF | `from Betfair.stream.scalper.scalper_bot import ticks_between` |
| 278 | tennis_runner.py:200-275 | tennis_runner.py | CONF | helper dei livelli (`_as_levels`) e stato punteggio; coerente con l'ambito ladder |
| 220 | tennis_db.py:54-77 | Betfair/stream/tennis_live/tennis_db.py | CONF | `get_tennis_client` |
| 585 | desktop/main.js:229-575 | desktop/main.js | CONF | |
| 432 | omega_db.py:75-280 | omega_db.py | CONF | `insert_trade` 75 ... `pending_manual_requests` 281 |

CONF 20, SPOS 0, FALSE 0.

Controllo numerico su 5 affermazioni di 05:

| Affermazione in 05 | Fonte | Esito |
|---|---|---|
| 29 tappe | T0A, T0B, T0C + T1..T26 = 29 | CONF |
| 79 decisioni dell'utente | 79 righe `\| U-nn` nella sezione 8 | CONF |
| adattatori 14.114 -> ~10.655 righe (riga 603) | scheda H riga 350 | CONF |
| tempi per bot 728 / 433 / 254 s (riga 605) | scheda H §1.5: 728,4 / 432,7 / 254,1 s | CONF |
| tennis pro ~19 s su 17 replay (riga 572) | scheda E5 riga 411: 18,9 s su 17 replay | CONF |

Nota non verificata: 05 righe 604-605 dice "pilota `safe_tennis` (17 scenari, 8,5 s)"; la tabella H §1.5 riporta 8,5 s per `rapidi` (non `tutti`). I 17 scenari sono confermati (`replay_tennis.py:352`), ma non ho misurato se 8,5 s riguarda tutti e 17. Non c'e' un reperto da correggere, solo da non citare come "tutti in 8,5 s" senza misura.

## Correzioni fatte

1. `ARCHITETTURA_2026-10/03_SCHEDE_COMPONENTI/K_CARTELLE_E_CODICE_MORTO.md` riga 66: la citazione `generate_dc_rho.py:54` era ambigua (la riga 54 e' del workflow `weekly_poisson_calibration.yml`, non dello script). Riscritta come "`generate_dc_rho.py` (riga `:54` del workflow `weekly_poisson_calibration.yml`; [chiarito dal verificatore 08/10])". Il contenuto era giusto: nessun cambio di sostanza.

Nessun'altra correzione necessaria: nessuna FALSA, nessuna SPOSTATA.

## Cose che ho lasciato

- J riga 363: `tennis.ts:719-848` (130 righe): il registro vero e' 719-833 (115 righe). Il resto del campo e' `subscribeTennisBots`. La voce e' un sottoinsieme dichiarato "non sommare", quindi non altera i totali; segnalato, non modificato.
- Scarto di 1 riga nei conteggi di `cashOutPartita.ts` (707 vs 706) e `esitoAbbinamento.ts` (708 vs 707): conteggio con/senza riga finale.
- `MatchesList.tsx:278` (K 274, 05 634): non e' in `frontend/src/components/`; non risolto, non e' nel campione.
