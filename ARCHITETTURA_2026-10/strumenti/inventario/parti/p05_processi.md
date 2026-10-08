## 5. Processi e canali locali

Fonti: lettura diretta di `desktop/main.js`, `desktop/ambiente_runner.js`, `desktop/preload.js`, `Betfair/stream/{watchdog,avvio_app,single_instance,
local_channel,canale_bot,ladder_canale,esiti_ordini_canale,sveglia_canale}.py`, `Betfair/stream/tennis_live/canale_bot_tennis.py`,
`Betfair/safe_strategy/{canale_scan,porta_ordini}.py`, `Betfair/{omega,mike}/porta_ordini.py` e le righe di avvio di ogni servizio; porte e
costanti raccolte da `p01_porte.py` (`uscite/p01_porte.tsv`: ogni riga con `47xxx` in codice di produzione/desktop/frontend, con `file:riga` e
tipo definizione/citazione; `p01_porte_riepilogo.txt`); workflow da `.github/workflows/*.yml`. Non ho lanciato nessun processo e non ho
interrogato il sistema operativo: i processi sotto sono quelli che il CODICE avvia, non quelli che oggi girano sul PC.

### 5.1 Chi avvia cosa

**Avvio dell'app** (`desktop/package.json:6` `"main": "bootstrap.js"`; `bootstrap.js` carica sempre `desktop/main.js` del repo; `npm start` = `electron .`).
In `main.js`, nell'ordine di `app.whenReady` (`:899`): `resolveRepoRoot` -> cartella dei registri dei figli (`prepareChildLogs`, `:307`) -> cancella il file
`ARRESTO` di un precedente spegnimento -> `ensureFreshUi()` (`:160`, esegue `npm run build` se `frontend/dist` e' piu' vecchio dei sorgenti) ->
`startStaticServer()` (`:191`, HTTP su `127.0.0.1:47330`, `UI_PORT` `:27`) -> `startRunners()` (`:413`) -> `startBetfairWebSso()` (`:759`) -> `createWindow()`
(`:886`, carica `http://127.0.0.1:47330/board`, `:895`).

Due identificativi nascono UNA volta per avvio dell'app e viaggiano nell'ambiente di tutti i figli (`ambiente_runner.js`, funzione pura
`costruisciEnvRunner`, test `ambiente_runner.test.js`): `APP_BOOT_ID` (`main.js:46`; i servizi si fermano da soli se l'id cambia: «all'avvio nessun bot opera»,
`Betfair/stream/avvio_app.py:54-100`) e `LOCAL_CHANNEL_TOKEN` (`main.js:61`, 32 byte casuali; abilita i comandi `order` sui canali 47331/47332;
alla pagina arriva dal preload, `desktop/preload.js:21`). Cadenze impostate dall'app: `LIVE_ORDER_QUEUE_POLL_SEC=0.15`, `LIVE_LADDER_PUBLISH_SEC=0.3`,
`TENNIS_LADDER_PUBLISH_SEC=0.3`, `TENNIS_ORDER_POLL_SEC=0.15`, `LIVE_RISK_ENGINE_POLL_SEC=0.15` (`ambiente_runner.js:69-75`).

**Processi avviati da `startRunners()`** (`main.js:413-484`; ognuno con `cwd` = radice del repo e il Python di `.venv`, `main.js:353-395`; registro
console + file per figlio, `main.js:307-352`):

| Etichetta | `main.js` | Comando (dopo `python -m Betfair.stream.watchdog`) | Modulo bersaglio (righe) | Lock (socket in ascolto su 127.0.0.1) | Canale WS | Note |
|---|---:|---|---|---|---|---|
| `runner-calcio` | :419 | (nessun argomento: bersaglio di serie `watchdog.py:65`) | `Betfair/stream/runner.py` (3.171) | **47311** (`runner.py:1254`, env `LIVE_RUNNER_LOCK_PORT`) | **47331** (`runner.py:2640`; accetta `order`, `snapshot`) | stream mercati e ordini via flumine; thread: ladder, punteggi, ordini, rischio, xhedge, stop giornaliero, riconciliazione |
| `runner-tennis` | :420 | `-- Betfair.stream.tennis_live.tennis_runner` | `tennis_runner.py` (3.483) | **47312** (`tennis_runner.py:2049`, env `TENNIS_RUNNER_LOCK_PORT`) | **47332** (`tennis_runner.py:3157`) | ospita i 4 bot tennis |
| `scalper-service` | :427 | `-- Betfair.stream.scalper.scalper_service` | `scalper_service.py` (982) | **47314** (`scalper_service.py:855`, env `SCALPER_SVC_LOCK_PORT`) | **47338** sola lettura (`scalper_service.py:607`) | un processo figlio per partita: `scalper_service.py:702-713` (`python -m Betfair.stream.scalper.scalper_session <event_id>`, gruppo di processi proprio) |
| `tennis-bot-service` | :437 | `-- Betfair.stream.tennis_live.tennis_bot_service --bridge-only` | `tennis_bot_service.py` (1.183) | nessuno in modalita' ponte (`:1138`; il ramo con lock 47312 e' `:1104`, solo senza `--bridge-only`) | **47337** sola lettura (`tennis_bot_service.py:258`, `canale_bot.py:135`) | ponte: righe dei 4 bot tennis, nessun login Betfair (`:1138-1160`) |
| `safe-strategy-service` | :443 | `-- Betfair.safe_strategy.service` | `safe_strategy/service.py` (3.444) | **47315** (`service.py:74`, env `SAFE_STRATEGY_LOCK_PORT`) | **47336** sola lettura (`service.py:91`, `:2457`) | lo SCANNER: feed unico quote/punteggi per Mike, Safe, Omega e per il runner calcio |
| `omega-service` | :450 | `-- Betfair.omega.omega_service` | `omega_service.py` (8.936) | **47313** (`omega_service.py:8520`) | **47334** sola lettura (`:8587`) | |
| `safe-strategy-bot` | :456 | `-- Betfair.safe_strategy.bot_service` | `bot_service.py` (11.136) | **47318** (`bot_service.py:139`) | **47335** sola lettura (`:10569`) | |
| `mike-service` | :461 | `-- Betfair.mike.service` | `mike/service.py` (7.551) | **47319** (`mike/config.py:32`, env `MIKE_LOCK_PORT`, `service.py:48`) | **47333** sola lettura (`service.py:6784`) | |
| `backtest-worker` | :469 | `-- Betfair.stream.backtest.worker` | `worker.py` (102) | nessuno (verificato: nessuna `acquire_single_instance_lock` in `worker.py`) | - | legge la coda `live_backtest_requests` ogni 5 s (`worker.py:23`, `DEFAULT_POLL_SEC`); esegue il banco e «Applica bot» di Match Replay |
| `tennis-odds` | :480 (e `setInterval` :483, 30 min) | `betfair_tennis_odds.py` (SENZA watchdog) | `betfair_tennis_odds.py` (322) | **47316** (`betfair_tennis_odds.py:305`) | - | processo breve; se la run precedente e' viva, salta il giro (`main.js:476-478`) |

Sono quindi **9 watchdog + 9 figli** (18 processi Python) piu' i processi brevi e le sessioni scalper, piu' i processi di Electron (main, renderer, GPU:
non contati dal codice). La porta di lock **47317 non e' usata** da nessun modulo; la **47312 compare come default in due moduli** (`tennis_runner.py:2049`
la acquisisce, `tennis_bot_service.py:1104` la prova solo fuori da `--bridge-only`).

**Altri avvii (non fatti dall'app)**:

| Cosa | Dove | Comando | Note |
|---|---|---|---|
| `avvia_omega_service.bat`, `avvia_scalper_service.bat`, `start_backtest_worker.bat`, `stream_api.bat` (runner), `aggiorna_quote_betfair.bat` (HTTP 8787 ordini a mano vecchi), `aggiorna_*.bat`, `importa_ultimi_15_giorni.bat` | radice | `.venv\Scripts\python.exe -m ...` | lancio manuale; il lock di istanza impedisce il doppio avvio con quelli dell'app (`main.js:446-449`). `avvia_omega_service.bat` e `avvia_scalper_service.bat` sono citati come istruzione dalla UI (`frontend/src/components/omega/ManualPanel.tsx:362`, `components/live/HabitatCard.tsx:66`) |
| `start_order_server.py` | radice (56 righe) | `python start_order_server.py` | HTTP `127.0.0.1:8787` (`Betfair/stream/odds_http.py:28`, `ThreadingHTTPServer`, `POST /place-order`) + `order_worker` (coda `betfair_order_requests`) + `refresh_worker`: la strada «ordini a mano vecchi»; non e' avviata dall'app; il runner non ospita l'endpoint (`runner.py:3159`) |
| 10 workflow GitHub Actions | `.github/workflows/*.yml` | cron e `workflow_dispatch` | cloud, non sul PC: vedi sotto |
| `python -m Betfair.stream.backtest.certifica <bot>` | banco | riga di comando | certificazione; non e' un servizio |
| `tools/*.py`, `Betfair/*/tools/*.py` | repo | riga di comando | replay e misure; 76 file, 35.486 righe (sezione 1) |

**I 10 workflow cloud** (cron in UTC; script lanciati; da `grep` di `cron:`/`python`):
`daily_yesterday_backfill.yml` (01:12, `daily_yesterday_backfill.py`), `today_predictions_backfill.yml` (02:18, `-m Prediction.today_predictions_backfill`),
`predictions_results_backfill.yml` (03:23; `-m Prediction.predictions_results_backfill`, `build_analytics_signals.py`, `merge_engine_signals.py`,
`enrich_analytics_snapshots.py`, `refresh_analytics_bets.py`, `build_direzione.py`), `weekly_poisson_calibration.yml` (lunedi' 03:27; `generate_dynamic_cal.py`,
`update_poisson_calibration.py --apply`, `generate_dc_rho.py`), `ml_calibration.yml` (05:14; `compute_ml_post_calibration.py`), `retrain_models.yml` (08:19;
`cloud_retrain_shard.py`, a shard), `seasons_catchup.yml` (13:47; `seasons_catchup.py`), `leagues_mapper.yml` (giorno 1 del mese 00:12; `leagues_mapper.py`),
`hazard_atlas.yml` (dopo il Daily; `-m Betfair.stream.scalper.genera_atlante`), `validate_models.yml` (solo manuale; `validate_walkforward.py`).
Questi lavorano sul DB cloud e producono i dati letti dai bot (previsioni, calibrazioni, atlante hazard): sono la parte del software che gira SENZA il PC.

### 5.2 Supervisione, arresto, riavvio

- **Watchdog** (`Betfair/stream/watchdog.py`, 337 righe): classifica l'uscita del figlio (`classify_exit`, `:73`): codice 0 = pulita (non riaccende), codice 75
  (`runner_lifecycle.py:72`, `EXIT_PLANNED_RESTART`) = ricambio pianificato, riavvio immediato; uscita entro 5 s (`WATCHDOG_LOCK_GRACE_SEC`, `:251`) = un'altra copia e' attiva (lock
  di istanza): il watchdog si ferma (`:307-313`); qualsiasi altro codice = caduta: alert `CRITICAL` in `live_alerts` + Telegram, riavvio con backoff
  `next_backoff` 10 s, 20 s, 40 s ... tetto 300 s (`:93`, `WATCHDOG_BACKOFF_BASE_SEC`/`CAP_SEC` `:249-250`), massimo 5 riavvii/ora (`WATCHDOG_MAX_RESTARTS_PER_HOUR`, `:248`) poi
  «SERVE INTERVENTO MANUALE» e si ferma (`:318-322`). Battito `WATCHDOG_HEARTBEAT_SEC` 30 s (`:252`), scritto solo dal watchdog del runner calcio (`deve_scrivere_battito`, `:122`).
  Il figlio e' lanciato SENZA `env`: eredita l'ambiente (stesso `APP_BOOT_ID` e token dopo un riavvio) (`main.js:36-42` commento; `watchdog.py` `popen(cmd, cwd=...)`).
- **Lock di istanza** (`Betfair/stream/single_instance.py:18`): `bind`+`listen` su `127.0.0.1:<porta>`; porta occupata = `SystemExit` immediato. Sono 8 porte
  (47311-47316, 47318, 47319), una per servizio.
- **Chiusura dell'app** (`main.js:527-575`): scrive il file `ARRESTO` (cartella `APP_ARRESTO_DIR` o `<dati>/_arresto`, `main.js:255-262`; modulo Python
  `Betfair/stream/arresto_ordinato.py:31`), aspetta ciascun servizio in elenco (`ARRESTO_ORDINATO_LABELS`, `:279`: i due runner, omega, safe-service, safe-bot, mike, tennis-bot, scalper) per un tempo
  massimo (`shutdownGraceMs`, `:292-296`: scalper 150 s, omega e safe-bot 45 s, gli altri 25 s), poi `taskkill /PID <pid> /T /F` sui rimasti (`:493`); `app.exit(0)` (`:572`). `tennis-odds` e
  `backtest-worker` non sono attesi. Safe e Omega annullano i loro ordini vivi all'arresto (tetto 10 s dopo il giro: commento `main.js:289-291`, `Betfair/safe_strategy/arresto_bot.py:34`).
- **Orologio e cambio di giorno**: non c'e' un processo «di giornata»; ogni servizio calcola la propria giornata (non verificato in questo inventario: appartiene alle schede dei componenti).

### 5.3 Le linee verso Betfair (chi si autentica e con quale libreria)

Ogni processo fa il proprio accesso (nessuna sessione condivisa tra processi: `INVENTARIO_ARCHITETTURA.md` B-3, confermato dal 02/10 nei registri `MISURE:210-238`: `certlogin SUCCESS`/`cert login .it OK` in
runner-calcio, runner-tennis, safe-service, scalper, mike, omega, tennis-odds). Percorsi di accesso nel codice di OGGI:
(1) `betfairlightweight` per lo stream e il runner flumine (`Betfair/stream/auth.py:13`; 27 file di produzione, sezione 2.2);
(2) client JSON-RPC proprio con `requests` (`Betfair/client.py:10`, usato da `runner.py`, `odds_refresh.py`, `betfair_report_manager.py`, `betfair_tennis_odds.py`) e
`omega_market.py:508` (Mike/Safe/Omega «a domanda»: ordini veri, saldo, quote di ripiego);
(3) **un terzo login nel processo Electron** (`desktop/main.js:759`, SSO web: `certlogin` con le credenziali del `.env`, cookie `ssoid` per le finestre Video/Stats; keep-alive `BETFAIR_KEEPALIVE_MS` 15 min `:589`, ritentativi 30/60/120/300 s `:590`): sola navigazione, nessun ordine.
Flusso stream: il runner calcio, il runner tennis, ogni sessione scalper e lo scanner (fino a 4 linee, `Betfair/safe_strategy/stream.py`) aprono ciascuno il proprio stream (`INVENTARIO_ARCHITETTURA.md` B-4...B-9, non rimisurato).

### 5.4 Canali locali (WebSocket JSON su 127.0.0.1)

Protocollo e sicurezza (`Betfair/stream/local_channel.py`, 767 righe): server `websockets.asyncio.server.serve` (`:292`); messaggi JSON una riga: push
`{"t": topic, "d": payload}`, richieste `{"id", "m": "order"|"snapshot"|"sveglia", "p"}`, risposte `{"id","ok","d"|"e"}` (`:14-18`; il metodo `sveglia` e' gestito a `:404`, prima della coda dei comandi,
e la usa il frontend: `frontend/src/lib/localChannel.ts:338-345`). Bind solo 127.0.0.1; origini ammesse: la UI dell'app (`ORIGINI_APP`, `:68`) piu' `LOCAL_CHANNEL_ORIGINS`;
i comandi che ESEGUONO (`order`) richiedono `?t=<token>` (`:65`, `ENV_TOKEN`); i canali dei bot sono `solo_lettura=True` (`start_channel(porta, sport, solo_lettura)`, `:717`);
i lettori Python si presentano su `/lettore/<topic>` (non contano come desktop collegato, non possono mandare comandi: `esiti_ordini_canale.py` docstring regola 7). I nomi dei
topic stanno in un solo posto (`canale_bot.py:82` `TOPIC`).

| Porta | Produttore (processo, `file:riga`) | Topic principali | Modo | Consumatori (`file:riga`) |
|---|---|---|---|---|
| **47330** | `desktop/main.js:215` (HTTP statico, serve `frontend/dist`) | pagine | HTTP | BrowserWindow `main.js:895`; origine ammessa `local_channel.py:68` |
| **47331** runner calcio | `runner.py:2640` `start_channel(.., "calcio")` | `hello`, `ladder`, `now`, `order`, `position`, `board` (`local_channel.py:14-18`); `battito`, `modo_ordini`, `flusso_stream`, `betfair_live_xhedge`, `account`/`conto` (`canale_bot.py:82-135`, `esiti_ordini_canale.py` `TOPIC_CONTO`); cadenza ladder `LIVE_LADDER_CANALE_MS` 200 ms (`config_stream.py:74`, `ladder_canale.py:60`) | lettura + COMANDI ordine | UI: `frontend/src/lib/localChannel.ts:63` (`calcio`); Safe/Omega/Mike per gli ordini (`safe_strategy/porta_ordini.py:75`, `omega/porta_ordini.py`, `mike/porta_ordini.py`, classe `PortaCanale` `safe_strategy/porta_ordini.py:541`, `/comando/<attore>`); esiti: `ClientEsiti` `esiti_ordini_canale.py:234` (classe `EsitiOrdini` `esiti_ordini_canale.py:421`, creata da Omega `omega_service.py:800`, ciclo di Safe `bot_service.py:10645-10647`, e `ClientEsiti` diretto da Mike `mike/service.py:6818` per il conto, `/lettore/conto`) |
| **47332** runner tennis | `tennis_runner.py:3157` | come sopra per il tennis (`ladder_canale` condiviso: `tennis_runner.py:1461`, `TENNIS_LADDER_CANALE_MS` `:110`) | lettura + COMANDI | UI (`tennis`); Safe tennis (`safe_strategy/porta_ordini.py:76`); il ponte come lettore (`canale_bot_tennis.py:127` `InoltroPosizioni`, `:84` `porta_runner`) |
| **47333** Mike | `mike/service.py:6784`, avvio `:6840` | `mike_posizioni`, `mike_attivita` | solo lettura + `sveglia` | UI `getLocalChannel('mike')` (`components/mike/useMike.ts:292`, `useMikeEventoAlMs.ts:31`) |
| **47334** Omega | `omega_service.py:8587`, avvio `:8599` | `omega_posizioni`, `omega_attivita`, `omega_proposta` | solo lettura + `sveglia` | UI `getLocalChannel('omega')` (`pages/Omega.tsx:233`) |
| **47335** Safe (bot) | `bot_service.py:10569`, avvio `:10583` | `safe_posizioni_calcio`, `safe_posizioni_tennis`, `safe_attivita`, `safe_proposta` | solo lettura + `sveglia` | UI `getLocalChannel('safe')` (`components/safestrategy/useSafeBot.ts:387`) |
| **47336** scanner | `safe_strategy/service.py:91`, avvio `:2457` (`start_channel(.., "safe-scan", solo_lettura=True)`) | `scan_calcio`, `scan_tennis`, `scanner_stato` | solo lettura | `ClientScan` (`safe_strategy/canale_scan.py:312`) in `mike/service.py:7072`, `omega_service.py:760`, `bot_service.py:9541`, `stream/scores/scan_feed.py:138` (runner calcio: punteggi); `AscoltoScan` (sveglia, `sveglia_canale.py:255`) in `mike/service.py:6943`, `omega_service.py:8686`, `canale_bot_tennis.py:351`; UI (`useControlRoom.ts:1514`, `getLocalChannel('scanner')`) |
| **47337** ponte tennis | `tennis_bot_service.py:258` (`canale_bot.py:135`) | `tennis_bot_stato`, `tennis_bot_posizioni`, `tennis_bot_armamento` | solo lettura + `sveglia` | UI `getLocalChannel('tennis_bot')` (`useControlRoom.ts:1750`); il runner tennis ascolta l'armamento (`tennis_runner.py:1723`, `canale_bot_tennis.py:332`) |
| **47338** scalper | `scalper_service.py:607` (`canale_bot.py:142`) | `scalper_stato`, `scalper_sessioni` | solo lettura | UI `getLocalChannel('scalper')` (`useControlRoom.ts:1795`) |

Frontend: i canali sono 8 (`localChannel.ts:50-67`, `LocalSport`), URL `ws://127.0.0.1:<porta>` (`:96`); il client **non ritenta mai** una richiesta (`localChannel.ts` intestazione: «NON reinviare»,
money-critical). `svegliaBot()` (`:338`) manda `sveglia` dopo ogni scrittura riuscita sul DB (Mike 47333, Omega 47334, Safe 47335, bot tennis 47337; lo scalper non ha sveglia, `:326-330`).

Interruttori: i canali dei bot sono accesi/spenti da **variabili d'ambiente** (almeno 23 nomi distinti in produzione: `MIKE_CANALE_POSIZIONI`, `OMEGA_CANALE_POSIZIONI`, `SAFE_CANALE_POSIZIONI`, `SAFE_SCAN_CANALE`,
`TENNIS_BOT_CANALE`, `SCALPER_CANALE`, `ESITI_ORDINI_CANALE`, `PUNTEGGI_CANALE`, `MIKE_LEGGE_CANALE`, `OMEGA_LEGGE_CANALE`, `SAFE_BOT_LEGGE_CANALE`, `*_SVEGLIA_CANALE` x5, `*_ORDINI_VIA_CANALE` x4
(`SAFE_`, `SAFE_TENNIS_`, `OMEGA_`, `MIKE_`), `MOTORE_ORDINI_CANALE`, `CONTROL_SUL_CANALE`, `INTERRUTTORI_CANALE`, `MIKE_CONTO_CANALE`; conteggio da `git grep` sui nomi `*CANALE*`).
Il verso di default NON e' uniforme: `canale_bot.acceso` vale spento se non scritto (`canale_bot.py:159-166`), ma il conto di Mike e' acceso di serie (`mike/service.py:6797-6800`).
Quali siano accesi sul PC dell'utente **non e' stato verificato** (il `.env` non e' stato letto); l'inventario del 02/10 riporta «tutti accesi» (`INVENTARIO_ARCHITETTURA.md` C-21).

Altri canali non WebSocket: **Supabase** (RPC/REST, sezione 3); **file `ARRESTO`** (`arresto_ordinato.py`); **registri dei figli** su file (`prepareChildLogs`, `main.js:307`);
**il DB come coda** (`betfair_live_order_requests`, `live_backtest_requests`, richieste dei bot); nessun `multiprocessing` nel codice di produzione (verificato con `git grep -l "multiprocessing\|Process("` su `*.py` fuori da audit, test e tools: 0 file); le sessioni scalper sono `subprocess.Popen` (`scalper_service.py:702`).

