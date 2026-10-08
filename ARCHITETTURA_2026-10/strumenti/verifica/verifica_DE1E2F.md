# Verifica schede D, E1, E2, F (08/10/2026)

Metodo: campione di 25 citazioni per scheda (`estrai_campione.py <scheda> 25`, seme fisso), file risolto con `git ls-files`, righe lette con `sed -n`. Esiti: CONFERMATA / SPOSTATA (entro +-15 righe) / FALSA. Alcune righe del campione ripetono la stessa citazione: contate come estratte. Quando una riga del documento contiene piu' riferimenti, ho letto anche i vicini (segnati con «+»).

## Riepilogo

| Scheda | Estratte | CONFERMATE | SPOSTATE | FALSE |
|---|---|---|---|---|
| D_RUNTIME_BOT_CONTRATTO | 25 | 25 | 0 | 0 |
| E1_MIKE | 25 | 25 | 0 | 0 |
| E2_OMEGA | 25 | 24 | 0 | 1 (minore, UI) |
| F_MONEY_MANAGEMENT_REGOLAMENTO | 25 | 24 | 1 | 0 |

Nessuna FALSA tocca un difetto, un numero o una decisione per l'utente. Verifiche in sola lettura; le uniche scritture sono 3 Edit alle schede (in coda).

## D_RUNTIME_BOT_CONTRATTO

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 307 | scalper/tools/replay_registrazioni.py:135-146 | Betfair/stream/scalper/tools/replay_registrazioni.py | CONFERMATA | costanti SCENARIO_SNIPER, media-under 135-146 |
| 175 | mike/db.py:71-85 | Betfair/mike/db.py | CONFERMATA | `log()` da 71; 83-85 e' il commento successivo |
| 131 | bot_db.py:62 | Betfair/safe_strategy/bot_db.py | CONFERMATA | `read_control` su `safe_strategy_control` (+ `set_control` :70, `log` :77) |
| 32 | tennis_runner.py:126-131 | Betfair/stream/tennis_live/tennis_runner.py | CONFERMATA | `_BOT_REGISTRY` con i 4 bot |
| 181 | bot_service.py:139 | Betfair/safe_strategy/bot_service.py | CONFERMATA | `_SINGLE_INSTANCE_PORT = 47318` |
| 461 | scalper_session.py:1845 | Betfair/stream/scalper/scalper_session.py | CONFERMATA | `threading.Thread(target=framework.run)`; watcher 1734-1915 confermato |
| 468 | mike/db.py:32-37 | Betfair/mike/db.py | CONFERMATA | le 5 costanti T_* |
| 118 | scalper_session.py:1756 (+1891, 1911) | scalper_session.py | CONFERMATA | tutte e tre leggono `live_now` |
| 151 | tennis_scalper_bot.py:312 | Betfair/stream/tennis_scalper/tennis_scalper_bot.py | CONFERMATA | `uscite_automatiche: bool = False` |
| 203 | tennis_runner.py:3121-3463 | tennis_runner.py | CONFERMATA | `setup_and_run` 3121, fine a 3462 |
| 266 | scalper_session.py:2276-2300 | scalper_session.py | CONFERMATA | `_al_segnale` e installazione segnali |
| 106 | scalper_service.py:880-903 | Betfair/stream/scalper/scalper_service.py | CONFERMATA | `_habitat_loop`; `giro_auto` 350 confermato |
| 199 | safe_strategy/bot_service.py:10902-11034 | bot_service.py | CONFERMATA | `main()` 10902-11034; `_ciclo_persistente` 10877 confermato |
| 539 | bot_service.py:9912 | bot_service.py | CONFERMATA | `run_giro_veloce` |
| 129 | service.py:3679 | Betfair/mike/service.py | CONFERMATA | ramo `approva_uscita` in `process_requests` |
| 306 | scalper_session.py:1525 | scalper_session.py | CONFERMATA | `SniperStrategy(`; theta 1620, MediaUnder 1673 confermati |
| 281 | registro_bot.py:22-26 | Betfair/stream/backtest/registro_bot.py | CONFERMATA | il test di contratto e' citato a :26-27 |
| 175 | omega_db.py:61-72 | Betfair/omega/omega_db.py | CONFERMATA | `log` su `omega_activity` |
| 140 | service.py:3964-3995 | Betfair/mike/service.py | CONFERMATA | `ferma_al_nuovo_avvio`; `uscite_bot="mike"` a 3991 |
| 215 | scalper_session.py:1734-1915 | scalper_session.py | CONFERMATA | watcher intervallo/punteggio da `live_now` |
| 148 | scalper_session.py:1185-1206 | scalper_session.py | CONFERMATA | `applica_uscite_automatiche`; chiamate 2097/2101 (cit. 2090-2101) |
| 151 | tennis_db.py:209-214 | Betfair/stream/tennis_live/tennis_db.py | CONFERMATA | colonna `tennis_bot_control.uscite_automatiche` |
| 89 | mike/db.py:59 (+64,71; omega_db 49,55,61; bot_db 62,70,77) | tre moduli | CONFERMATA | tutte le 9 firme alle righe indicate |
| 467 | avvio_app.py:173-215 | Betfair/stream/avvio_app.py | CONFERMATA | `uscite_a_manuali`, ramo `mike` a 190 |
| 115 | mike/db.py:553 | Betfair/mike/db.py | CONFERMATA | `fetch_scan_rows` |

## E1_MIKE

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 195 | lib/interruttori.ts:1258 (+InterruttoreUscite.tsx:28-47) | frontend/src/lib/interruttori.ts | CONFERMATA | commento «Mike `params.uscite_automatiche`»; InterruttoreUscite 28-47 testi/stato uscite |
| 159 | service.py:4120-4130 | Betfair/mike/service.py | CONFERMATA | `daily_loss_stop`, log una volta/giorno |
| 40 | service.py:739 | Mike service.py | CONFERMATA | `execute_place` |
| 191 | mike.ts:1331 | frontend/src/lib/mike.ts | CONFERMATA | `MIKE_ACTIVITY_KINDS` |
| 187 | service.py:2198-2204 (+2190) | Mike service.py | CONFERMATA | `_piazza_resting_live`: scrivere 'pending' prima di piazzare |
| 416 | regolato_conto.py:242-263 | Betfair/mike/regolato_conto.py | CONFERMATA | riga utente da `listCurrentOrders` / topic conto |
| 320 | engine.py:3175 (+avvio_app 180-191, sql:42) | Betfair/mike/engine.py | CONFERMATA | `params.get("uscite_automatiche", False)`; `mike_request` a sql:42 |
| 192 | engine.py:3430 | engine.py | CONFERMATA | `has_unknown_orders` -> «regolamento sospeso: un ordine ha esito ignoto» |
| 179 | config.py:32 | Betfair/mike/config.py | CONFERMATA | `LOCK_PORT_DEFAULT = 47319` |
| 334 | engine.py:3549-3555 | engine.py | CONFERMATA | `VETO_U35_NODI` 5 nodi |
| 514 | engine.py:3877-3879 | engine.py | CONFERMATA | `last_entry_ticks_above` letto dal motore |
| 327 | service.py:4739, 3998, 739 | Mike service.py | CONFERMATA | `_run_event`, `run_once`, `execute_place`; lunghezze 778/374/341 (doc: 339, trascurabile) |
| 475 | service.py:4116-4211 | Mike service.py | CONFERMATA | stop giornaliero, tetto partite per modalita' |
| 192 | Mike.tsx:430 | frontend/src/pages/Mike.tsx | CONFERMATA | `ServiceHealthChip` |
| 319 | engine.py:3549-3555 (+3574-3578; config.py:263) | engine.py / config.py | CONFERMATA | default di ripiego a 3574-3578; `uscite_automatiche` False a config:263 |
| 315 | config.py:76-390 | config.py | CONFERMATA | `PARAM_SPEC` (apertura e chiusura 390) |
| 320 | uscite_automatiche_mike_2026-09-25.sql:42 | migrations/ | CONFERMATA | `CREATE OR REPLACE FUNCTION mike_request` |
| 366 | feed.py:493 (+engine 3089, 5304) | Betfair/mike/feed.py | CONFERMATA | `snapshot_from_row`, `decide`, `apply_decision` |
| 41 | service.py:103-128 | Mike service.py | CONFERMATA | `mike_live_abilitato` |
| 79 | service.py:4259-4264 (4255-4258) | Mike service.py | CONFERMATA | `c_e_fretta` + commento |
| 94 | safe_strategy/db.py:307 | Betfair/safe_strategy/db.py | CONFERMATA | `sb.table("mike_events")` |
| 364 | avvio_app.py:180-191 | Betfair/stream/avvio_app.py | CONFERMATA | elenco bot -> `uscite_automatiche` |
| 43 | service.py:3636 | Mike service.py | CONFERMATA | `process_requests`; `approva_uscita` 3679 |
| 196 | certifica.py:5 | Betfair/stream/backtest/certifica.py | CONFERMATA | riga 5 = `certifica mike --scenari tutti` |
| 196 | registro_bot.py:219-243 | registro_bot.py | CONFERMATA | `nome="mike"` a 219 |

## E2_OMEGA

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 243 | interruttori.ts:1257 | frontend/src/lib/interruttori.ts | CONFERMATA | `Omega params.uscite_protezione` |
| 303 | certificazione.py:283-1709 | Betfair/omega/certificazione.py | CONFERMATA | primo controllo `_a1` 283, `verifica` 1709, `elenco_controlli` 1734 |
| 129 | mike/db.py:629-631 | Betfair/mike/db.py | CONFERMATA | `omega_db.fixture_analysis` |
| 300 | registro_bot.py:244-253 | registro_bot.py | CONFERMATA | voce `omega` |
| 125 | mike/service.py:131-302 | Betfair/mike/service.py | CONFERMATA | `_RealMarket` 131, `_real_market` 302 |
| 432 | bot_db.py:926-942 | Betfair/safe_strategy/bot_db.py | CONFERMATA | delega a `omega_db` |
| 135 | mike/service.py:142-143 | Mike service.py | CONFERMATA | riassegnazione a :143 (:159 `strategy_ref=` confermato) |
| 433 | avvio_app.py:182 | Betfair/stream/avvio_app.py | CONFERMATA | `omega -> uscite_protezione`; :199 `if b == "omega"` |
| 331 | safe_strategy/execution.py:221-229 | Betfair/safe_strategy/execution.py | CONFERMATA | `_omega_service()` import pigro |
| 432 | mike/db.py:629 | Mike db.py | CONFERMATA | idem riga 129 |
| 292 | interruttori.ts:490 | interruttori.ts | CONFERMATA | `omega_activate` `coalesce` SOVRASCRIVE |
| 481 | interruttori.ts:490 | interruttori.ts | CONFERMATA | idem |
| 304 | certificazione.py:1817-1845 | omega/certificazione.py | CONFERMATA | `RIPETIZIONI_SOSPETTE=5`, `SKIP_SOSPETTI=200`, `difetti_di_progettazione` |
| 309 | pages/Omega.tsx:899-912 | frontend/src/pages/Omega.tsx | CONFERMATA | gruppo «Obiettivo» `__daily_goal` |
| 292 | pages/Omega.tsx:899-912 | Omega.tsx | CONFERMATA | idem |
| 155 | pages/Omega.tsx:899-912 (+OS:1890-1900, OC:13,33) | Omega.tsx / omega_service.py / omega_config.py | CONFERMATA | `daily_goal` default 250 (OC:13), `stop_on_goal` (OC:33), stop a OS:1898-1900 |
| 246 | omegaProposte.ts:210 | frontend/src/lib/omegaProposte.ts | CONFERMATA | `esitoUscitaAlPrezzo` |
| 256 | omegaMissions.ts:147-213 | frontend/src/lib/omegaMissions.ts | CONFERMATA | `activateMission` ... `subscribeOmegaMissions` |
| 249 | MatchTradesTable.tsx:493 | frontend/src/components/omega/MatchTradesTable.tsx | **FALSA (minore)** | :493 e' il bottone «live» (`onGoLive`); il `CashOutButton` e' a 538-568 (45 righe piu' sotto). Corretto. |
| 125 | execution.py:40 | safe_strategy/execution.py | CONFERMATA | `from Betfair.omega.omega_market import PlaceRifiutato` |
| 38 | desktop/main.js:450 | desktop/main.js | CONFERMATA | `spawnRunner('omega-service', ...watchdog... omega_service)` |
| 295 | pages/Omega.tsx:86 (+569) | Omega.tsx | CONFERMATA | `REALTIME_DEBOUNCE_MS = 1200`; :569 canale locale 47334 |
| 433 | registro_bot.py:156-162 | registro_bot.py | CONFERMATA | `_MODULI_OMEGA` |
| 433 | desktop/main.js:446-450 (+249-294) | desktop/main.js | CONFERMATA | spawn omega + `arrestoCartella`/`shutdownGraceMs` |
| 129 | safe_strategy/bot_db.py:926-942 | bot_db.py | CONFERMATA | duplicato della riga 432 |

## F_MONEY_MANAGEMENT_REGOLAMENTO

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 193 | replayOperazioni.ts:185 (+659) | frontend/src/lib/replayOperazioni.ts | CONFERMATA | `pnlSeVince`, `nettoPerSelezione`; `cicliOperativi` a 568 |
| 133 | liveOrders.ts:981 | frontend/src/lib/liveOrders.ts | CONFERMATA | `.from('betfair_live_account')` |
| 174 | omega_db.py:1041 (+omega_service 5321) | Betfair/omega/omega_db.py | CONFERMATA | `upsert_daily_goal`; `_snapshot_daily_goal` |
| 212 | aggiorna_solo_fogli.py:20 (+aggiorna_mm_sheets.py:37, MatchesList.tsx:278) | radice repo | CONFERMATA | import `SlotManager`; commissione di default; testo UI su aggiorna_report.bat |
| 147 | reconcile_worker.py:140-231 | Betfair/stream/reconcile_worker.py | CONFERMATA | `_sync_account` fino al run del manual PnL |
| 171 | service.py:4120 (+config.py:318, service.py:54) | Betfair/mike/service.py | CONFERMATA | `daily_loss_stop` (config 318, default 50), `_DAILY_STOP_LOGGED` a :54 |
| 200 | mike.ts:1057 | frontend/src/lib/mike.ts | CONFERMATA | `lockedPnlTotal` (1313 `pnlByTotalCells`) |
| 200 | omega.ts:745 | frontend/src/lib/omega.ts | CONFERMATA | `commissionPctOf` (752 `hasOwnCommission`) |
| 93 | safeBot.ts:1063 | frontend/src/lib/safeBot.ts | CONFERMATA | `tradeCommission` |
| 200 | safeBot.ts:1063 | safeBot.ts | CONFERMATA | idem |
| 93 | (riga U7) safeBot.ts:1063 | safeBot.ts | CONFERMATA | duplicato |
| 221 | daily_stop_worker.py:250 (+daily_pnl.py:49) | Betfair/stream/daily_stop_worker.py | CONFERMATA | legge `betfair_live_settled`; `realized_pnl` somma `profit` |
| 75 | omega_market.py:1599-1769 | Betfair/omega/omega_market.py | CONFERMATA | `_riga_regolata` ... `market_profit_and_loss` (+ settle_pnl omega_engine:815, `_netto_di_conto` OS:4588) |
| 159 | db.py:1011 | Betfair/stream/db.py | CONFERMATA | `upsert_live_account_manual_pnl` |
| 194 | controlRoom.ts:1073 | frontend/src/lib/controlRoom.ts | CONFERMATA | `realizzatoGiornata` |
| 126 | daily_stop_worker.py:424 | daily_stop_worker.py | **SPOSTATA (+11)** | :424 e' `day = now_local...`; la chiamata `daily_pnl.day_window_utc` e' a :435. Corretto. (reconcile_worker 495 e 696 e daily_pnl.py:129 confermati) |
| 172 | omega_service.py:1890 (+2502, 7846, 8388) | omega_service.py | CONFERMATA | `goal = control.get("daily_goal") or DEFAULT_DAILY_GOAL` in tutti e 4 |
| 137 | omega_db.py:1045 | omega_db.py | CONFERMATA | upsert su `omega_daily_goal` |
| 220 | CashOutButton.tsx:78 (+exits.py:193, omega_engine.py:265, omega_v3.py:949, media_under_bot.py:561) | frontend/.../CashOutButton.tsx e backend | CONFERMATA | `netAfterCommission` e le 4 funzioni di commissione per valore |
| 102 | stream/trading/greenup.py:118 | Betfair/stream/trading/greenup.py | CONFERMATA (rilievo di formulazione) | `compute_greenup` a :118; «249 righe» e' la lunghezza del FILE, la funzione ne ha 132. Corretto il testo. |
| 134 | db.py:963 (+425) | stream/db.py | CONFERMATA | upsert `betfair_live_settled`; lettura a 425 |
| 181 | media_under_bot.py:544-566 | Betfair/stream/scalper/media_under_bot.py | CONFERMATA | `profitto_lordo_con_banca` ... `obiettivo_automatico`; `residuo_netto` scalper_session:373 confermato |
| 189 | cashOutPartita.ts:463 | frontend/src/lib/cashOutPartita.ts | CONFERMATA | `cashOutPartita()` |
| 103 | tennis_live_order_worker.py:992 | Betfair/stream/tennis_live/tennis_live_order_worker.py | CONFERMATA | `compute_greenup(`; live_order_worker 2330, 2627 confermati |
| 209 | money_management.py:263 (+45-56, 199) | Betfair/money_management.py | CONFERMATA | `SlotManager` 263, costanti 45-56, `CALIBRATION_TABLE` 199 |
| 77 | tennis_live_order_worker.py:462 (+1249; daily_stop_worker 151) | tennis_live_order_worker.py | CONFERMATA | `_pnl_ordine`, `_commissioni_per_ordine`, `_simulated_profit` |

## Correzioni fatte alle schede

1. `E2_OMEGA.md` E2-069: `MatchTradesTable.tsx:493` -> `538-568` (`CashOutButton`), nota «[corretto dal verificatore 08/10]».
2. `F_MONEY_MANAGEMENT_REGOLAMENTO.md` riga 126: `daily_stop_worker.py:424` -> `:435`, nota «[corretto dal verificatore 08/10]».
3. `F_MONEY_MANAGEMENT_REGOLAMENTO.md` riga 102: `compute_greenup (249 righe)` -> `(132 righe, 118-249; il file ne ha 249)`, nota «[corretto dal verificatore 08/10]».

## Non verificato

Le citazioni fuori campione (D 116, E1 123, E2 42, F 201 in totale) non sono state lette, salvo quelle vicine nelle stesse righe (segnate con «+», tutte confermate). Non ho ricontato i numeri aggregati (righe dei 5 adattatori di replay, 7.499 righe frontend Omega, 107 chiavi PARAM_SPEC, 52 controlli Omega).
