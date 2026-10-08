# Verifica indipendente delle schede E3, E4, E5, I (08/10/2026)

Metodo: campione di 25 citazioni per scheda con `estrai_campione.py <scheda> 25` (seme fisso 20261008). Ogni citazione e' stata risolta sul file vero (`git ls-files`, scelta col contesto) e le righe lette. In piu', per ogni riga di scheda campionata sono state controllate con `grep` le citazioni secondarie presenti nella stessa riga (funzioni "NNN" nominate, costanti, porte).
Sola lettura del codice. Unici file scritti: questo referto e le correzioni puntuali alle schede.

## Conteggi

| Scheda | CONFERMATE | SPOSTATE | FALSE |
|---|---|---|---|
| E3_SAFE | 25 | 0 | 0 |
| E4_SCALPER_CALCIO | 24 | 1 | 0 |
| E5_TENNIS | 22 | 3 | 0 |
| I_DESKTOP_PROCESSI_H24 | 24 | 1 | 0 |
| Totale | 95 | 5 | 0 |

Nessuna FALSA. Nessuna delle 5 SPOSTATE tocca un reperto importante (difetto, numero, decisione): le affermazioni sono vere, cambia di 1-3 righe (o 5-9 per il checkbox HT) il punto citato.

## E3_SAFE (25/25 confermate)

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 219 | execution.py:1061-1515 | safe_strategy/execution.py | CONFERMATA | `def place(` a 1061; 1514-1515 vuote dopo il corpo. `_place_via_canale` 795, `enqueue_place` 1766 verificati |
| 182 | service.py:2979 | safe_strategy/service.py | CONFERMATA | `def tick(self)` |
| 270 | service.py:2441 | safe_strategy/service.py | CONFERMATA | `_avvia_canale`; porta 47336 = `_PORTA_CANALE_SCAN` (riga 91) |
| 312 | safeBot.ts:1094-1102 | frontend/src/lib/safeBot.ts | CONFERMATA | `FEED_ROW_STALE_MS` 20_000 ... `SCANNER_STALE_MS` 45_000; `exits.py` 231/234/245 = 20/120/45 s |
| 178 | engine.py:196-320 | safe_strategy/engine.py | CONFERMATA | tabella dei valori di serie (`"base": {` a 196, `favSuperMax` 320). `merge_params` 381, `DEFAULT_PARAMS`/`mergeParams` in safeStrategy.ts 218/312 verificati |
| 178 | safeBot.ts:751 | frontend/src/lib/safeBot.ts | CONFERMATA | `mergeRiskParams`; `mergeBotParams` 760 |
| 182 | mike/db.py:553 | mike/db.py | CONFERMATA | `fetch_scan_rows`; `publish_status` 2856 |
| 160 | exits.py:748-906 | safe_strategy/exits.py | CONFERMATA | `track` 748; `_track_calcio` 772, `_track_tennis` 833, `feed_is_fresh` 424 |
| 164 | bot_service.py:437 | safe_strategy/bot_service.py | CONFERMATA | `STRATEGIE_CON_USCITE` |
| 101 | bot_db.py:77 | safe_strategy/bot_db.py | CONFERMATA | `def log` su `safe_strategy_activity` |
| 217 | bot_service.py:477-505 | safe_strategy/bot_service.py | CONFERMATA | `modalita_di_strategia`; `normalize_strategy_modes` 412, `_avvisa_ereditarieta` 6826 |
| 192 | service.py:2742 | safe_strategy/service.py | CONFERMATA | `hydrate_pre_ko`; `hydrate_schede` 2724, `freeze_pre_ko` scanner.py 482 / `_tennis` 509 |
| 178 | safeBot.ts:688-696 | frontend/src/lib/safeBot.ts | CONFERMATA | `SAFE_RISK_DEFAULTS` |
| 306 | bot_db.py:925 | safe_strategy/bot_db.py | CONFERMATA | `fixtures_for_window`; `fixtures_window` db.py 159, `fetch_scan_rows` 951, `scanner_status` 969 |
| 185 | service.py:1315 | safe_strategy/service.py | CONFERMATA | `refresh_stream_set`; `_diario_pool_stream` 1345; `stream.py` 567 righe, `healthy` 310/`serving` 318 |
| 381 | registro_bot.py:255-290 | backtest/registro_bot.py | CONFERMATA | `BotRegistrato(nome="safe_base"` 255 ... `mercati=` 290 |
| 217 | safeBot.ts:152 | frontend/src/lib/safeBot.ts | CONFERMATA | `liveStrategies`; `modalitaOrdineAMano` 181 |
| 219 | execution.py:1286 | safe_strategy/execution.py | CONFERMATA | `_gate(...)` 1286, `enqueue_place(` chiamata 1288 |
| 371 | stream.py:418-427 | safe_strategy/stream.py | CONFERMATA | `create_stream` 418, `_subscribe` 426 |
| 347 | service.py:2531-2723 | safe_strategy/service.py | CONFERMATA | `build_rows` 2531-2722 |
| 275 | db.py:295-500 | safe_strategy/db.py | CONFERMATA | da `list_mike_followed_event_ids` 295 a `_leggi_fonte` ordini tennis ~500 |
| 111 | db.py:295 | safe_strategy/db.py | CONFERMATA | idem; `list_bot_exposures` 416, upsert status 228 (dentro 221-236) |
| 263 | bot_db.py:70 | safe_strategy/bot_db.py | CONFERMATA | `set_control`; la chiamata a fine `run_once` e' a bot_service.py:10437 (verificato) |
| 126 | stream.py:66 | safe_strategy/stream.py | CONFERMATA | `_CONFLATE_MS = 1000` |
| 171 | safeBot.ts:423 | frontend/src/lib/safeBot.ts | CONFERMATA | `SafeComboType` con le 5 famiglie; `combos.py` 620 righe, `_proponi_combo` 8560, `_esegui_combo_riservata` 8710 |

## E4_SCALPER_CALCIO (24 confermate, 1 spostata)

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 371 | ScalperPanel.tsx:67 | components/live/ScalperPanel.tsx | CONFERMATA | `pollMs = 4000` |
| 317 | tennis_scalper_bot.py:274 | stream/tennis_scalper/tennis_scalper_bot.py | CONFERMATA | docstring "COPIA di `scalper_bot.ScalperStrategy`..." |
| 241 | sniper_bot.py:770-1363 | stream/scalper/sniper_bot.py | CONFERMATA | `_begin_flatten` 770 ... cancel 1362 |
| 58 | XHedgePanel.tsx:220 | components/live/XHedgePanel.tsx | CONFERMATA | commento "Pattern ScalperPanel" |
| 46 | omega/omega_advisor.py:215 | omega/omega_advisor.py | CONFERMATA | import da `scalper.hazard_atlas`; `mike/dossier.py` 30 e 324 verificati (import da scalper) |
| 362 | scalper_session.py:72-105 | stream/scalper/scalper_session.py | CONFERMATA | `UI_PARAM_WHITELIST` |
| 263 | ScalperPanel.tsx:696-701 | components/live/ScalperPanel.tsx | CONFERMATA | bottone "Attiva adesso" da fermo |
| 35 | sniper_bot.py:90 | stream/scalper/sniper_bot.py | CONFERMATA | `class SniperStrategy`; `ScalperStrategy` scalper_bot.py:390 verificato |
| 210 | scalper_bot.py:88-122 | stream/scalper/scalper_bot.py | CONFERMATA | `spezza_uscita` |
| 342 | sniper_bot.py:295 | stream/scalper/sniper_bot.py | CONFERMATA | `_ko_epoch_ms`; anche scalper_bot.py:788 e media_under_bot.py:1020 |
| 256 | mediaUnder.ts:41-85 | frontend/src/lib/mediaUnder.ts | CONFERMATA | `MEDIA_UNDER_DEFAULTS` 41 ... `mediaUnderDefaults` 85; `MEDIA_UNDER_CAMPI` 66 |
| 431 | scalper_bot.py:2924 | stream/scalper/scalper_bot.py | CONFERMATA | `market.place_order(order)` |
| 67 | scalper_session.py:230-247 | stream/scalper/scalper_session.py | CONFERMATA | `freno_soldi_veri` |
| 142 | safe_strategy/execution.py:138-168 | safe_strategy/execution.py | CONFERMATA | `_live_brake`; `ETA_RILETTURA_BOT_S` citato a 151 |
| 239 | scalper_session.py:112 | stream/scalper/scalper_session.py | CONFERMATA | `SNIPER_MARKET_TYPES` OVER_UNDER_05..85 |
| 351 | scalper_session.py:42-70 | stream/scalper/scalper_session.py | CONFERMATA | `VALIDATED_PARAMS` |
| 262 | mediaUnder.ts:278-313 | frontend/src/lib/mediaUnder.ts | CONFERMATA | `MediaBanca` ... `MediaUnderStato` |
| 457 | scalper.ts:106-117 | frontend/src/lib/scalper.ts | CONFERMATA | `SCALPER_PARAM_DEFAULTS`; `SCALPER_PARAM_FIELDS` 128-139 verificato |
| 485 | tools/replay_registrazioni.py:767 | stream/scalper/tools/replay_registrazioni.py | CONFERMATA | `SCENARI_DESCRITTI` a 767 (scelto il file dello scalper fra 4 omonimi) |
| 342 | media_under_bot.py:1020 | stream/scalper/media_under_bot.py | CONFERMATA | `_ko_epoch_ms` |
| 134 | scalper_bot.py:769 | stream/scalper/scalper_bot.py | CONFERMATA | `check_market_book`; `process_market_book` 817 |
| 58 | DutchingPanel.tsx:153 | components/live/DutchingPanel.tsx | CONFERMATA | commento "Pattern ScalperPanel" |
| 204 | ScalperPanel.tsx:430-440 | components/live/ScalperPanel.tsx | SPOSTATA | il checkbox `htMode` e' a 439-447 (430-433 e' `missionTwoTicks`). Corretta nella scheda |
| 371 | MissionCard.tsx:212-222 | components/omega/MissionCard.tsx | CONFERMATA | commento "§18: il poll e' UNO SOLO" |
| 256 | ScalperPanel.tsx:555-660 | components/live/ScalperPanel.tsx | CONFERMATA | blocco Media Under (`mediaMode`, `SCALPER_PARAM_FIELDS.map`) |

Extra E4-017 (riga 204): `max_inplay_slots` `:455`, `inplay_close_now` `:832` confermati in scalper_bot.py.

## E5_TENNIS (22 confermate, 3 spostate)

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 134 | service.py:134 | safe_strategy/service.py | SPOSTATA | `_SCORES_PERIOD_SEC = 2.0` e' a 132; 134 e' `_IPS_REQ_DELAY = 0.1`. Il valore dichiarato (2,0 s) e' giusto. Corretta |
| 71 | chiusura_manuale.py:52 | stream/tennis_live/chiusura_manuale.py | CONFERMATA | `from . import tennis_db` |
| 170 | registro_bot.py:55 | stream/backtest/registro_bot.py | SPOSTATA | `d.isdigit()` e' a 56. Corretta |
| 459 | tennis_runner.py:124-140 | stream/tennis_live/tennis_runner.py | CONFERMATA | latenza paper, `_BOT_REGISTRY`, `live_order_mode` |
| 459 | desktop/main.js:470-500 | desktop/main.js | CONFERMATA | job quote tennis |
| 459 | tennis_flb_bot.py:1-143 | stream/tennis_scalper/tennis_flb_bot.py | CONFERMATA | |
| 87 | tennis_bot_service.py:46 | stream/tennis_live/tennis_bot_service.py | CONFERMATA | `ENSURE_POLL_SEC = 15.0` |
| 330 | TennisMatchStats.tsx:38 | components/tennis/TennisMatchStats.tsx | CONFERMATA | `STALE_MS = 15_000` |
| 71 | tennis_bot_service.py:41 | stream/tennis_live/tennis_bot_service.py | CONFERMATA | `from . import tennis_db` |
| 329 | tennis_pro_bot.py:157 | stream/tennis_scalper/tennis_pro_bot.py | CONFERMATA | `50_000.0` |
| 359 | lib/tennis.ts:719-848 | frontend/src/lib/tennis.ts | CONFERMATA | `TENNIS_BOT_REGISTRY` |
| 400 | registro_bot.py:374 | stream/backtest/registro_bot.py | CONFERMATA | `nome="tennis_flb"` |
| 334 | desktop/main.js:481 | desktop/main.js | SPOSTATA | 481 e' una `};`; spawn del job a 480, `setInterval` 30 min a 483. Nella stessa riga `betfair_tennis_odds.py:311-312` e' `today=`/`try:`: il login (`c.login_cert()`) e' a 308, una volta per processo, e il processo e' rilanciato ogni 30 min = 48/giorno (affermazione VERA). delete 274 e upsert 278 confermati. Corretta |
| 84 | tennis_runner.py:111 | stream/tennis_live/tennis_runner.py | CONFERMATA | `SCORE_POLL_SEC` 2.0; `BOT_CONTROL_POLL_SEC` 3.0 a 112; 3355 conferma `interval=SCORE_POLL_SEC or 2.0` |
| 330 | lib/tennis.ts:122 | frontend/src/lib/tennis.ts | CONFERMATA | `timeoutMs = 60_000` |
| 73 | registro_bot.py:190-211 | stream/backtest/registro_bot.py | CONFERMATA | `_MODULI_TENNIS` |
| 459 | betfair_tennis_odds.py:1-38 | betfair_tennis_odds.py (radice) | CONFERMATA | |
| 282 | registro_bot.py:340-346 | stream/backtest/registro_bot.py | CONFERMATA | commento `_instantiate_bot` |
| 400 | tennis_runner.py:126-131 | stream/tennis_live/tennis_runner.py | CONFERMATA | `_BOT_REGISTRY`; `_BOT_KEYS` tennis_bot_service.py:220 confermato |
| 274 | tennis_runner.py:124 | stream/tennis_live/tennis_runner.py | CONFERMATA | `TENNIS_PAPER_LATENCY_MS_DEFAULT = 600` |
| 133 | scan_feed.py:44-51 | stream/scores/scan_feed.py | CONFERMATA | tetto eta' e "throttle 2.5 s"; `get_scores(..., lightweight=True)` service.py:1731 confermato |
| 36 | frontend/src/lib/tennis.ts:719-848 | frontend/src/lib/tennis.ts | CONFERMATA | |
| 240 | tennis_runner.py:72 | stream/tennis_live/tennis_runner.py | CONFERMATA | import `TENNIS_PARAMS as SCALPER_TENNIS_PARAMS` |
| 208 | TennisBotPanel.tsx:238 | components/tennis/TennisBotPanel.tsx | CONFERMATA | `data-testid="tennis-pro-superficie"` |
| 158 | tennis_bot_service.py:147 | stream/tennis_live/tennis_bot_service.py | CONFERMATA | `_market_row_for` |

Nota non corretta (conteggio, non citazione): la scheda dice "147 `c.get(`"; `grep -c "c\.get("` sui 4 file `tennis_*_bot.py` da 148 (72+45+13+18). Differenza di 1, probabilmente una occorrenza in commento: da ricontare se il numero 29/147 = 19,7 % entra in una decisione.

## I_DESKTOP_PROCESSI_H24 (24 confermate, 1 spostata)

| riga_doc | citazione | file risolto | esito | nota |
|---|---|---|---|---|
| 374 | scalper_service.py:659 | stream/scalper/scalper_service.py | CONFERMATA | docstring di `marca_orfana`: scenario `riavvio` S7 |
| 244 | main.js:419-469 | desktop/main.js | CONFERMATA | contati 9 `spawnRunner` sotto `Betfair.stream.watchdog` (calcio, tennis, scalper, tennis-bot, safe-service, omega, safe-bot, mike, backtest-worker); `watchdog.py:122-141` = `deve_scrivere_battito` |
| 409 | main.js:483 | desktop/main.js | CONFERMATA | `setInterval(runTennisOdds, 30*60*1000)` = 48/giorno |
| 114 | omega_service.py:8522-8557 | omega/omega_service.py | CONFERMATA | keepAlive proattivo ~600 s; `omega_market.py:140` = `keep_alive` |
| 178 | watchdog.py:144 | stream/watchdog.py | CONFERMATA | `_db_alert`; `_db_heartbeat` 151 |
| 111 | tennis_runner.py:1583-1610 | stream/tennis_live/tennis_runner.py | CONFERMATA | `_maybe_keepalive` |
| 207 | main.js:808-815 | desktop/main.js | CONFERMATA | commento BetfairMediaButtons, 640x780; `openBetfairWindow` 826-861 confermato |
| 242 | watchdog.py:270-276 | stream/watchdog.py | CONFERMATA | spawn fallito; 307 (`lock`), 312, 318-322 confermati; `main.js:401` `child.on('exit'` |
| 195 | main.js:229-352 | desktop/main.js | CONFERMATA | `CHILD_LOG_RETENTION_MS` 7 giorni |
| 266 | frammenti_mercato.py:85 | stream/frammenti_mercato.py | CONFERMATA | `LIMITE_BETFAIR_CONNESSIONI = 10` |
| 147 | betfair_report_manager.py:6 | Betfair/betfair_report_manager.py | CONFERMATA | import `RotatingFileHandler`; uso a 42; nessun altro file lo usa (grep) |
| 403 | runner.py:1252 | stream/runner.py | CONFERMATA | `LIVE_RUNNER_MAX_HOURS` 18; 2x24/18 = 2,67 |
| 168 | main.js:759 | desktop/main.js | CONFERMATA | `startBetfairWebSso` |
| 285 | main.js:419-469 | desktop/main.js | CONFERMATA | 9 watchdog + 9 figli |
| 309 | main.js:292-296 | desktop/main.js | CONFERMATA | `shutdownGraceMs` |
| 95 | daily_stop_worker.py:424 | stream/daily_stop_worker.py | CONFERMATA | `day = now_local.date().isoformat()`; `_TZ_DEFAULT = "Europe/Rome"` a 51 |
| 141 | tennis_runner.py:2047 | stream/tennis_live/tennis_runner.py | CONFERMATA | `_TENNIS_MAX_HOURS` 18 |
| 249 | worker.py:23 | stream/backtest/worker.py | CONFERMATA | `DEFAULT_POLL_SEC = 5.0` |
| 417 | main.js:937 | desktop/main.js | CONFERMATA | `window-all-closed` -> `shutdownAndQuit()` |
| 201 | main.js:235-296 | desktop/main.js | CONFERMATA | arresto ordinato; 504 `waitForExit`, 561 confermati |
| 225 | avvio_app.py:54-336 | stream/avvio_app.py | CONFERMATA | file di 337 righe |
| 203 | main.js:563-576 | desktop/main.js | CONFERMATA | `shutdownAndQuit`; 937 e 951 (`process.on('exit')`) confermati |
| 335 | auth.py:156-286 | stream/auth.py | CONFERMATA | `CustodeSessione` |
| 325 | reconcile_worker.py:1329 | stream/reconcile_worker.py | CONFERMATA | `def reconcile_worker`; `interval=RECONCILE_POLL_SEC or 30.0` (runner.py:3000) |
| 99 | betfair_tennis_odds.py:310 | betfair_tennis_odds.py (radice) | SPOSTATA | `dt.date.today()` e' a 311 (310 e' `while True:`). Stessa citazione nel difetto D13 (riga 254 della scheda). Corrette entrambe |

## Correzioni fatte alle schede (nota «[corretto dal verificatore 08/10]»)

1. `E4_SCALPER_CALCIO.md` riga 204 (E4-017): `ScalperPanel.tsx:430-440` -> `439-447`.
2. `E5_TENNIS.md` riga 134: `service.py:134` -> `service.py:132` (`_SCORES_PERIOD_SEC = 2.0`).
3. `E5_TENNIS.md` riga 170: `registro_bot.py:55` -> `:56`.
4. `E5_TENNIS.md` riga 334: `betfair_tennis_odds.py:311-312` -> `:308` (`login_cert`) e `desktop/main.js:481` -> `:480,483`.
5. `I_DESKTOP_PROCESSI_H24.md` righe 99 e 254: `betfair_tennis_odds.py:310` -> `:311`.

Fuori perimetro, da correggere dal proprietario: `03_SCHEDE_COMPONENTI/F_MONEY_MANAGEMENT_REGOLAMENTO.md` riga 127 cita `betfair_tennis_odds.py:310` (dovrebbe essere 311). Non toccata.

## Non verificato

- Il campione e' di 25 citazioni per scheda su 192/84/76/153: gli esiti sono una stima, non una copertura totale. Le citazioni secondarie controllate (circa 60 in piu') sono tutte esatte tranne quelle corrette sopra.
- I numeri di misura (richieste/giorno, 81,7/min, 16.900/giorno) non sono stati ricalcolati: nessun accesso ai dati misurati.
