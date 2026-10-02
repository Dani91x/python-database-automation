# Inventario dell'architettura attuale (02/10/2026)

Ogni scatola e ogni freccia degli schemi in `SCHEMI_BOT/sistema/schemi/` ha qui la sua prova nel
codice (`file:riga`, percorsi relativi alla radice del repo, codice alla base `22d19cc` di master).
Le misure vengono dai registri dell'app del 02/10/2026 (vedi `MISURE_2026-10-02.md`).

Controllo delle prove: `python SCHEMI_BOT/sistema/strumenti/mostra_righe.py --inventario
SCHEMI_BOT/sistema/INVENTARIO_ARCHITETTURA.md` stampa la riga citata di ogni riferimento e segnala
quelli che puntano a un file o a una riga inesistente.

Legenda dei colori, uguale in tutti gli schemi: grigio = Betfair; verde = programma Python;
viola = database Supabase; azzurro = app desktop; lilla = canale locale; arancio chiaro =
guardiano; rosso chiaro = banco di prova. Freccia piena = a ritmo fisso; tratteggiata = solo
quando serve o di ripiego; spessa = tante chiamate.

---

## A. I processi (capitoli 1 e 2)

| N. | Fatto | Prova |
|---|---|---|
| A-1 | L'app (guscio Electron) lancia i programmi con `spawnRunner`, cartella di lavoro = radice del repo, ambiente arricchito (chiave dei canali, ritmi 0,15 s) | `desktop/main.js:351`, `desktop/main.js:357`, `desktop/main.js:390` |
| A-2 | Runner calcio: `-m Betfair.stream.watchdog` senza argomenti, il bersaglio di serie e' `Betfair.stream.runner` | `desktop/main.js:435`, `Betfair/stream/watchdog.py:65` |
| A-3 | Runner tennis sotto guardiano | `desktop/main.js:436` |
| A-4 | Scalper (capo delle sessioni) sotto guardiano | `desktop/main.js:443` |
| A-5 | Ponte tennis `--bridge-only` sotto guardiano | `desktop/main.js:453` |
| A-6 | Scanner (`Betfair.safe_strategy.service`) sotto guardiano | `desktop/main.js:459` |
| A-7 | Omega sotto guardiano | `desktop/main.js:466` |
| A-8 | Bot Safe (`Betfair.safe_strategy.bot_service`) sotto guardiano | `desktop/main.js:472` |
| A-9 | Mike sotto guardiano | `desktop/main.js:477` |
| A-10 | Quote tennis (`betfair_tennis_odds.py`) SENZA guardiano: all'avvio e ogni 30 minuti; salta il giro se il precedente e' ancora vivo | `desktop/main.js:484`, `desktop/main.js:488`, `desktop/main.js:490`, `desktop/main.js:491` |
| A-11 | Guardiano: uscita con codice 0 = pulita, non riaccende | `Betfair/stream/watchdog.py:82`, `Betfair/stream/watchdog.py:289` |
| A-12 | Guardiano: uscita entro 5 s = un'altra copia e' gia' accesa (porta di guardia), si ferma | `Betfair/stream/watchdog.py:88`, `Betfair/stream/watchdog.py:307` |
| A-13 | Guardiano: caduta = avviso grave + Telegram, riaccende dopo 10, 20, 40 ... fino a 300 s | `Betfair/stream/watchdog.py:93`, `Betfair/stream/watchdog.py:314`, `Betfair/stream/watchdog.py:249` |
| A-14 | Guardiano: al massimo 5 riaccensioni in un'ora, poi «SERVE INTERVENTO MANUALE» | `Betfair/stream/watchdog.py:105`, `Betfair/stream/watchdog.py:248`, `Betfair/stream/watchdog.py:317` |
| A-15 | Guardiano: ricambio pianificato (codice 75) = riaccensione immediata, non e' una caduta | `Betfair/stream/watchdog.py:84`, `Betfair/stream/watchdog.py:298` |
| A-16 | Avvisi del guardiano nella tabella `live_alerts` | `Betfair/stream/watchdog.py:144`, `Betfair/stream/watchdog.py:148` |
| A-17 | Battito del guardiano ogni 30 s, scritto solo per il runner calcio | `Betfair/stream/watchdog.py:252`, `Betfair/stream/watchdog.py:122` |
| A-18 | Chiusura dell'app: file ARRESTO, attesa di ognuno, poi spegnimento forzato dell'albero dei processi (`taskkill /T /F`) | `desktop/main.js:535`, `desktop/main.js:540`, `desktop/main.js:497` |
| A-19 | Porte di guardia (una copia sola): runner 47311, tennis 47312, Omega 47313, scalper 47314, scanner 47315, quote tennis 47316, Safe 47318, Mike 47319 | `Betfair/stream/runner.py:1203`, `Betfair/stream/tennis_live/tennis_runner.py:1975`, `Betfair/omega/omega_service.py:8293`, `Betfair/stream/scalper/scalper_service.py:813`, `Betfair/safe_strategy/service.py:74`, `betfair_tennis_odds.py:304`, `Betfair/safe_strategy/bot_service.py:139`, `Betfair/mike/config.py:32` |
| A-20 | Ritmi dei giri: Mike 1 s (5 s a vuoto), Safe 2 s, Omega 20 s (60 s a vuoto), scalper 3 s, ponte 15 s, scanner 0,5 s | `Betfair/mike/service.py:7432`, `Betfair/safe_strategy/bot_service.py:10677`, `Betfair/omega/omega_service.py:8621`, `Betfair/stream/scalper/scalper_service.py:43`, `Betfair/stream/tennis_live/tennis_bot_service.py:46`, `Betfair/safe_strategy/service.py:3338` |
| A-21 | Ponte tennis in `--bridge-only`: nessun accesso a Betfair, solo database | `Betfair/stream/tennis_live/tennis_bot_service.py:1128` |
| A-22 | Scalper: una sessione = un processo figlio per partita (`scalper_session`) | `Betfair/stream/scalper/scalper_service.py:663` |

## B. Le linee con Betfair (capitolo 3)

| N. | Fatto | Prova |
|---|---|---|
| B-1 | Accesso con certificato .it, libreria betfairlightweight | `Betfair/stream/auth.py:59`, `Betfair/stream/auth.py:70` |
| B-2 | Accesso con certificato .it, client proprio (JSON-RPC), sessione solo in memoria | `Betfair/client.py:95`, `Betfair/client.py:148` |
| B-3 | Nessuna sessione condivisa fra processi: ogni processo fa il suo accesso. Nei registri del 02/10: accessi in runner calcio, runner tennis, scanner, scalper, Mike, Omega, quote tennis | `MISURE_2026-10-02.md` sezione B |
| B-4 | Runner calcio: linea continua mercati (flumine) e linea ordini vera in LIVE | `Betfair/stream/runner.py:2805`, `Betfair/stream/runner.py:2106` |
| B-5 | Runner calcio: saldo ogni 20 s; in LIVE rilettura ordini ogni 30 s (`list_current_orders`, `list_cleared_orders`) | `Betfair/stream/reconcile_worker.py:96`, `Betfair/stream/reconcile_worker.py:287`, `Betfair/stream/config_stream.py:332`, `Betfair/stream/runner.py:2944` |
| B-6 | Runner calcio: punteggi da Betfair solo se la riga dello scanner manca o e' vecchia di oltre 15 s | `Betfair/stream/scores/scan_feed.py:43`, `Betfair/stream/scores/scan_feed.py:524` |
| B-7 | Runner tennis: una linea continua per le partite tennis seguite; sessione rinfrescata ogni 480 s (8 minuti) | `Betfair/stream/tennis_live/tennis_runner.py:469`, `Betfair/stream/tennis_live/tennis_runner.py:157`, `Betfair/stream/tennis_live/tennis_runner.py:1506` |
| B-8 | Sessioni scalper: accesso proprio, linea continua dei mercati della partita, annullo ordini all'arresto | `Betfair/stream/scalper/scalper_session.py:1085`, `Betfair/stream/scalper/scalper_session.py:1187`, `Betfair/stream/scalper/scalper_session.py:448` |
| B-9 | Scanner: fino a 4 linee da 180 mercati (aggiornamenti raggruppati a 1 s) | `Betfair/safe_strategy/stream.py:81`, `Betfair/safe_strategy/stream.py:82`, `Betfair/safe_strategy/stream.py:265`, `Betfair/safe_strategy/stream.py:418` |
| B-10 | Scanner: elenco partite (catalogo) ogni 300 s; punteggi ogni 2 s; cronologia ogni 30 s | `Betfair/safe_strategy/service.py:120`, `Betfair/safe_strategy/service.py:132`, `Betfair/safe_strategy/service.py:136` |
| B-11 | Scanner: ripiego a domanda (`listMarketBook`) per i mercati senza quote da 20 s, ogni 10-60 s | `Betfair/safe_strategy/service.py:223`, `Betfair/safe_strategy/service.py:1672`, `Betfair/safe_strategy/scanner.py:535` |
| B-12 | Mike, Safe, Omega: nessuna linea continua; usano il client a domanda di `omega_market` | `Betfair/omega/omega_market.py:68`, `Betfair/safe_strategy/bot_service.py:96`, `Betfair/mike/service.py:149` |
| B-13 | Omega: elenco partite a ogni giro con il bot acceso; sessione rinfrescata ogni 600 s | `Betfair/omega/omega_service.py:8031`, `Betfair/omega/omega_market.py:140` |
| B-14 | Safe: quote a domanda solo se il feed non le ha (max ogni 10 s per mercato, 8 per giro) | `Betfair/safe_strategy/bot_service.py:759`, `Betfair/safe_strategy/bot_service.py:789` |
| B-15 | Mike: quote a domanda delle linee col flusso fermo (max ogni 10 s per mercato) | `Betfair/mike/service.py:1267` |
| B-16 | Quote tennis: elenco, catalogo e quote del giorno, poi esce | `betfair_tennis_odds.py:204`, `betfair_tennis_odds.py:53`, `betfair_tennis_odds.py:244` |
| B-17 | Nessun contatore delle chiamate a Betfair nei registri (solo contatori parziali: chiamate punteggi dello scanner nello stato nel database; regolato di Mike) | `Betfair/safe_strategy/service.py:2920`, `Betfair/mike/service.py:6132` |

## C. I canali locali (capitolo 4)

| N. | Fatto | Prova |
|---|---|---|
| C-1 | Canale = WebSocket solo su 127.0.0.1; ammesse solo le pagine servite su 47330 | `Betfair/stream/local_channel.py:68`, `Betfair/stream/local_channel.py:296` |
| C-2 | Chiave segreta: generata dall'app, passata ai programmi e alla pagina (preload) | `desktop/main.js:59`, `desktop/preload.js:21`, `Betfair/stream/local_channel.py:325` |
| C-3 | Ordine senza chiave: rifiutato e collegamento chiuso | `Betfair/stream/local_channel.py:425` |
| C-4 | 47331 runner calcio (accetta ordini `/comando/<bot>`) | `Betfair/stream/runner.py:2585`, `Betfair/stream/local_channel.py:143` |
| C-5 | 47332 runner tennis (accetta ordini) | `Betfair/stream/tennis_live/tennis_runner.py:2986` |
| C-6 | 47333 Mike, sola lettura | `Betfair/mike/service.py:6729`, `Betfair/mike/service.py:6785` |
| C-7 | 47334 Omega, sola lettura | `Betfair/omega/omega_service.py:8360`, `Betfair/omega/omega_service.py:8372` |
| C-8 | 47335 Safe, sola lettura | `Betfair/safe_strategy/bot_service.py:10310` |
| C-9 | 47336 scanner, sola lettura: righe `scan_calcio`/`scan_tennis` al massimo ogni 2,5 s, stato ogni 10 s | `Betfair/safe_strategy/canale_scan.py:69`, `Betfair/safe_strategy/service.py:2457`, `Betfair/safe_strategy/service.py:159` |
| C-10 | 47337 ponte tennis, sola lettura | `Betfair/stream/canale_bot.py:135`, `Betfair/stream/tennis_live/tennis_bot_service.py:258` |
| C-11 | 47338 scalper, sola lettura (sessioni ogni 3 s) | `Betfair/stream/canale_bot.py:142`, `Betfair/stream/scalper/scalper_service.py:597` |
| C-12 | Nomi dei messaggi (topic) in un posto solo | `Betfair/stream/canale_bot.py:82` |
| C-13 | Ladder del runner calcio sul canale ogni 0,3 s (impostato dall'app) | `desktop/main.js:366`, `Betfair/stream/runner.py:745` |
| C-14 | Lo schermo si collega direttamente ai canali (non passa dal guscio) | `frontend/src/lib/localChannel.ts:62`, `frontend/src/lib/localChannel.ts:83` |
| C-15 | Mike, Safe, Omega leggono le righe dello scanner dal 47336 (un client per fonte) | `Betfair/safe_strategy/canale_scan.py:312`, `Betfair/mike/service.py:7017`, `Betfair/safe_strategy/bot_service.py:9273`, `Betfair/omega/omega_service.py:759` |
| C-16 | Il runner calcio legge i punteggi dello scanner dal 47336 (`PUNTEGGI_CANALE`) | `Betfair/stream/scores/scan_feed.py:138` |
| C-17 | Safe, Omega, Mike mandano ordini al 47331 con `/comando/<attore>` | `Betfair/safe_strategy/porta_ordini.py:75`, `Betfair/omega/porta_ordini.py:48`, `Betfair/mike/porta_ordini.py:36` |
| C-18 | Esiti degli ordini letti dal 47331 (`/lettore/order`) da Omega e Safe; conto da Mike (`/lettore/conto`) | `Betfair/stream/esiti_ordini_canale.py:82`, `Betfair/omega/omega_service.py:790`, `Betfair/safe_strategy/bot_service.py:10355`, `Betfair/mike/service.py:6763` |
| C-19 | Safe tennis manda ordini al 47332 | `Betfair/safe_strategy/porta_ordini.py:76` |
| C-20 | Il ponte rilegge dal 47332 le posizioni dei bot tennis e le rilancia sul 47337 | `Betfair/stream/tennis_live/canale_bot_tennis.py:107` |
| C-21 | Interruttori nel `.env` del principale tutti accesi (letti solo i nomi elencati, il 02/10): `SAFE_SCAN_CANALE`, `MIKE_CANALE_POSIZIONI`, `OMEGA_CANALE_POSIZIONI`, `SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`, `MIKE_LEGGE_CANALE`, `PUNTEGGI_CANALE`, `MOTORE_ORDINI_CANALE`, `SCALPER_CANALE`, `SAFE_ORDINI_VIA_CANALE`, `OMEGA_ORDINI_VIA_CANALE`, `SAFE_TENNIS_ORDINI_VIA_CANALE` = 1 | `.env` del checkout principale (non nel repo) |

## D. Il database come postino (capitolo 5)

| N. | Fatto | Prova |
|---|---|---|
| D-1 | Client comune del database, uno per thread; profilo bot con attese di 5 s e 20 s acceso da Safe, Omega, Mike | `db_client.py:74`, `db_client.py:60`, `Betfair/mike/service.py:7380` |
| D-2 | Runner calcio: legge la coda ordini ogni 1 s (impostato 0,15 s dall'app, ma la lettura del database e' limitata a circa 1 s) | `Betfair/stream/live_order_worker.py:3846`, `Betfair/stream/live_order_worker.py:3811`, `Betfair/stream/config_stream.py:229` |
| D-3 | Runner calcio: legge le sequenze «sotto il minimo» in corso ogni 1 s per modo (live e paper) | `Betfair/stream/live_order_worker.py:3720` |
| D-4 | Runner calcio: legge le regole di rischio armate, scattate e annullate ogni 1 s | `Betfair/stream/risk_engine_worker.py:1173`, `Betfair/stream/risk_engine_worker.py:557`, `Betfair/stream/risk_engine_worker.py:1096` |
| D-5 | Runner calcio: impostazioni ordini (`get_live_settings`) dal worker ordini, dal rischio e dallo stop giornaliero | `Betfair/stream/live_order_worker.py:498`, `Betfair/stream/risk_engine_worker.py:1192`, `Betfair/stream/daily_stop_worker.py:421` |
| D-6 | Runner calcio: battito ogni 10 s; partite seguite ogni 2 s | `Betfair/stream/runner.py:1539`, `Betfair/stream/runner.py:1001` |
| D-7 | Runner calcio: legge le righe dello scanner (memoria di 1 s; 10 s se il canale e' vivo) | `Betfair/stream/scores/scan_feed.py:407`, `Betfair/stream/scores/scan_feed.py:69` |
| D-8 | Scanner: scrive `safe_strategy_scan` (solo righe cambiate, quote al massimo ogni 2,5 s per partita) e `safe_strategy_status` ogni 10 s | `Betfair/safe_strategy/service.py:2847`, `Betfair/safe_strategy/db.py:198`, `Betfair/safe_strategy/service.py:2930` |
| D-9 | Scanner: legge `mike_events` ogni 10 s | `Betfair/safe_strategy/service.py:1945` |
| D-10 | Mike: legge comandi, richieste e operazioni aperte a ogni giro; scrive gli eventi in blocco | `Betfair/mike/service.py:3953`, `Betfair/mike/service.py:3984`, `Betfair/mike/service.py:4087`, `Betfair/mike/service.py:6636` |
| D-11 | Mike: righe dello scanner con memoria di 4 s (10 s se il canale copre tutto) | `Betfair/mike/service.py:7145`, `Betfair/mike/config.py:338` |
| D-12 | Safe: legge i comandi due volte per giro; richieste due volte per giro e ogni 0,25 s con posizioni aperte | `Betfair/safe_strategy/bot_service.py:10581`, `Betfair/safe_strategy/bot_service.py:9864`, `Betfair/safe_strategy/bot_service.py:10481` |
| D-13 | Safe: aggregati (`get_safe_aggregates`) una o due volte per giro | `Betfair/safe_strategy/bot_db.py:336` |
| D-14 | Omega: comandi, operazioni, richieste manuali, missioni a ogni giro (20 s) | `Betfair/omega/omega_service.py:7809`, `Betfair/omega/omega_service.py:5252`, `Betfair/omega/omega_service.py:7496` |
| D-15 | Runner tennis: senza partite rilegge la lista ogni 2 s | `Betfair/stream/tennis_live/tennis_runner.py:3012` |
| D-16 | Ponte tennis: comandi dei bot, servizio, partite seguite, a ogni giro di 15 s | `Betfair/stream/tennis_live/tennis_bot_service.py:170`, `Betfair/stream/tennis_live/tennis_bot_service.py:436`, `Betfair/stream/tennis_live/tennis_bot_service.py:676` |
| D-17 | Scalper: `scalper_control` e `scalper_service_control` ogni 3 s; freno (`get_live_settings`) | `Betfair/stream/scalper/scalper_service.py:75`, `Betfair/stream/scalper/scalper_service.py:94`, `Betfair/stream/trading/controls.py:96` |
| D-18 | Quote tennis: cancella e riscrive `tennis_markets` del giorno | `betfair_tennis_odds.py:274`, `betfair_tennis_odds.py:278` |
| D-19 | Nessun contatore delle chiamate al database nei servizi: la misura si fa contando le righe `HTTP Request:` dei registri | `MISURE_2026-10-02.md` metodo |

### D-M. Tabella delle chiamate al database per servizio (misurate)

Metodo: righe `HTTP Request: <METODO> .../rest/v1/<tabella>` nei registri dell'app (copia del
02/10 alle 15:16:55 UTC); finestra 60 s dalle 15:15:40 alle 15:16:40 UTC (17:15:40-17:16:40 ora
italiana); controllo sulla finestra di 5 minuti 15:11:40-15:16:40 UTC. Script:
`SCHEMI_BOT/sistema/strumenti/misura_chiamate_db.py`. Grezzi in `MISURE_2026-10-02.md`.

| Servizio | 60 s | media su 5 min | Tabelle principali (60 s) | RPC (60 s) |
|---|---:|---:|---|---|
| runner-calcio | 552 | 549/min | `betfair_live_order_requests` GET 189, `betfair_live_risk_rules` GET 168, `live_follow` 29, `betfair_live_orders` 11, `betfair_live_settled` 11, `safe_strategy_scan` 8, `betfair_live_heartbeat` POST 8, `safe_strategy_status` 2, `betfair_live_account` POST 2, `personal_watchlist` 1 | `get_live_settings` 123 |
| mike-service | 279 | 268/min | `mike_trades` GET 116, `mike_control` GET 58 + PATCH 2, `mike_requests` GET 58, `mike_events` POST 25 + GET 1, `safe_strategy_scan` 14, `mike_activity` POST 2 | `get_mike_aggregates` 3 |
| safe-strategy-bot | 269 | 263/min | `safe_strategy_trades` GET 81, `safe_strategy_requests` PATCH 53 + GET 44, `safe_strategy_control` GET 36 + PATCH 19, `safe_strategy_status` 5, `safe_strategy_scan` 5, `safe_strategy_opportunities` POST 4 + DELETE 1, `omega_events` 1, `fixture_predictions` 1 | `get_safe_aggregates` 19 |
| safe-strategy-service (scanner) | 86 | 87/min | `safe_strategy_scan` POST 68 + GET 1, `mike_events` GET 6, `safe_strategy_status` POST 5 | `list_bot_exposures` 6 |
| scalper-service | 54 | 55/min | `scalper_control` 18, `scalper_service_control` 18 | `get_live_settings` 18 |
| tennis-bot-service (ponte) | 36 | 43/min | `tennis_bot_control` GET 18, `tennis_bot_service_control` PATCH 12 + GET 3, `tennis_live_follow` 3 | - |
| runner-tennis | 28 | 29/min | `tennis_live_follow` GET 28 | - |
| omega-service | 5 | 11/min | `omega_trades` GET 4, `omega_control` GET 1 | (5 min: `get_omega_aggregates_modalita` 4) |
| tennis-odds | 0 | 0 | terminato alle 14:55 UTC; 4 chiamate in tutta la vita (`tennis_markets` DELETE 2 + POST 2) | - |
| **Totale** | **1.309** | | | |

Riepilogo usato negli schemi (capitolo 5a): runner calcio 480/min sulla coda ordini, le regole e le
impostazioni (189 + 168 + 123), 62/min su partite seguite, ordini, regolati, battito e conto, 10/min
sulle righe dello scanner (8 + 2); Mike 265/min sulle sue tabelle e 14/min sulle righe dello
scanner; Safe 259/min sulle sue tabelle (257 Safe + 1 `omega_events` + 1 `fixture_predictions`) e
10/min sulle righe e lo stato dello scanner; scanner 74/min sulle sue righe e sul suo stato
(68 + 1 + 5) e 12/min sulle posizioni dei bot (`mike_events` 6 + `list_bot_exposures` 6).

### D-B. Chiamate a Betfair per servizio (dal codice; i registri ne mostrano solo i segni)

| Servizio | Continuo | Solo quando serve | Ripiego | Segni nei registri del 02/10 (14:25-15:16 UTC) |
|---|---|---|---|---|
| Runner calcio | linea mercati + ordini; saldo 20 s; ordini 30 s in LIVE (B-5); catalogo flumine 60 s | catalogo dei mercati nuovi; ordini | punteggi se il feed manca (B-6) | 343 aggiornamenti di catalogo, 54 connessioni mercati riuscite, 48 sottoscrizioni a caldo, 41 letture regolati, 33 saldi riletti |
| Runner tennis | linea partite; sessione 480 s | catalogo partite nuove | punteggi se il feed manca | 6 rinfreschi di sessione, nessuna partita |
| Scanner | 4 linee; catalogo 300 s; punteggi 2 s | cataloghi dei mercati a gol e risultato esatto (max ogni 20 s) | quote a domanda (B-11) | 14 connessioni riuscite; 2 passaggi al ripiego e 2 rientri |
| Sessioni scalper | linea della partita | avvio e arresto | - | nessuna sessione accesa |
| Mike | - | ordini veri, saldo, regolato | quote linee ferme (B-15) | 12 saldi riletti dopo ordine |
| Safe | - | ordini veri se canale e coda falliscono | quote se il feed manca (B-14) | - |
| Omega | sessione 600 s; elenco partite a ogni giro col bot acceso | ordini | risultato esatto se manca nel feed | 1 accesso |
| Quote tennis | ogni 30 min, poi esce | - | - | 2 accessi (2 giri) |

## E. Lo scanner (capitolo 6)

| N. | Fatto | Prova |
|---|---|---|
| E-1 | La classe `Scanner` vive dentro il programma `safe_strategy/service.py` | `Betfair/safe_strategy/service.py:431` |
| E-2 | Giro ogni 0,5 s | `Betfair/safe_strategy/service.py:3338` |
| E-3 | Mercati base: esito finale di calcio e tennis, finestra da -6 h a +14 h, fino a 1000 mercati | `Betfair/safe_strategy/service.py:189`, `Betfair/safe_strategy/service.py:183` |
| E-4 | Linee continue (B-9), ripiego a domanda (B-11), punteggi e cronologia (B-10) | vedi B-9, B-10, B-11 |
| E-5 | Scrive le righe e lo stato (D-8); avvisi in `live_alerts` | `Betfair/safe_strategy/service.py:2933` |
| E-6 | Posizioni dei bot: `list_bot_exposures` (funzione del database, ripiego a 6 letture), memoria di 10 s, chiamata solo dallo scanner | `Betfair/safe_strategy/db.py:416`, `Betfair/safe_strategy/db.py:432`, `Betfair/safe_strategy/service.py:1951` |
| E-7 | Le posizioni servono a seguire per primi i mercati dove ci sono soldi | `Betfair/safe_strategy/service.py:2015`, `Betfair/safe_strategy/service.py:715` |
| E-8 | Pubblica sul 47336 (C-9) | vedi C-9 |
| E-9 | Lettori dal database: runner calcio (D-7), scalper ogni 15 s, ponte tennis | `Betfair/stream/scalper/scalper_service.py:110`, `Betfair/stream/tennis_live/tennis_db.py:152` |
| E-10 | Nel registro del 02/10 (5 minuti): 1 passaggio al ripiego REST e 1 rientro, 151 avvisi «quote assenti»; 40 partite seguite | `MISURE_2026-10-02.md` sezione B; riga `[safe-scan] pubblicate ... (monitorati 40)` del registro |

## F. La porta degli ordini (capitolo 7)

| N. | Fatto | Prova |
|---|---|---|
| F-1 | Elenco ufficiale delle strade verso Betfair, vincolato da un test (strade S1, S2, S2t, S3a, S3b, S4a, S4b, BANCO) | `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py:163`, `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py:278` |
| F-2 | Punto comune nel runner: `_dispatch` -> `_do_place` -> `build_order` -> `market.place_order` (flumine) | `Betfair/stream/live_order_worker.py:3673`, `Betfair/stream/live_order_worker.py:1423`, `Betfair/stream/live_order_worker.py:1273` |
| F-3 | Prova (paper) o vero dipende dal modo della riga; la prova la simula flumine nel runner | `Betfair/stream/live_order_worker.py:276`, `Betfair/stream/live_order_worker.py:250`, `Betfair/stream/runner.py:2850` |
| F-4 | Strada del filo (S2): motore ordini nel runner, sveglia a ogni comando, controlli (modo, freno, minimi) e piazzamento sotto lucchetto | `Betfair/stream/runner.py:2408`, `Betfair/stream/motore_ordini.py:801`, `Betfair/stream/motore_ordini.py:1071`, `Betfair/stream/motore_ordini.py:1489` |
| F-5 | Strada della coda (S1): tabella `betfair_live_order_requests`, scritta con la funzione `request_betfair_live_order` | `Betfair/stream/live_order_worker.py:61`, `Betfair/omega/omega_db.py:634`, `Betfair/safe_strategy/bot_db.py:1003`, `Betfair/mike/db.py:662` |
| F-6 | Safe: filo, poi coda, poi (in prova) rifiuto, poi (live) domanda diretta | `Betfair/safe_strategy/execution.py:871`, `Betfair/safe_strategy/execution.py:1003`, `Betfair/safe_strategy/execution.py:1070`, `Betfair/safe_strategy/execution.py:1095`, `Betfair/safe_strategy/execution.py:1163` |
| F-7 | Omega: filo o coda; in live domanda diretta se gate/coda falliscono; in prova senza runner nessun riempimento | `Betfair/omega/omega_service.py:2751`, `Betfair/omega/omega_service.py:2877`, `Betfair/omega/omega_service.py:2707` |
| F-8 | Mike in prova: filo `/comando/mike`; Mike vero: domanda diretta (`omega_market`) | `Betfair/mike/porta_ordini.py:9`, `Betfair/mike/porta_ordini.py:11`, `Betfair/mike/service.py:152`, `Betfair/mike/service.py:2208` |
| F-9 | Domanda diretta: `place_order_live` / `place_submin_live` -> `place_orders` | `Betfair/omega/omega_market.py:696`, `Betfair/omega/omega_market.py:763`, `Betfair/omega/omega_market.py:1018` |
| F-10 | Ordini a mano dallo schermo: filo con la chiave, coda se il filo e' giu' | `frontend/src/lib/localTransport.ts:441`, `frontend/src/lib/localTransport.ts:445`, `frontend/src/lib/liveOrders.ts:133` |
| F-11 | Ordini a mano vecchi (`order_exec.py`, porta 8787, coda `betfair_order_requests`): NON accesi dall'app, partono da `start_order_server.py` | `Betfair/order_exec.py:207`, `Betfair/order_exec.py:322`, `Betfair/stream/odds_http.py:28`, `Betfair/order_worker.py:29`, `start_order_server.py:24` |
| F-12 | Minimi .it: 1,00 EUR per punta e per banca al centesimo, pavimento di legge 0,50 | `Betfair/stream/trading/minimi_it.py:30`, `Betfair/stream/trading/minimi_it.py:32`, `Betfair/stream/trading/minimi_it.py:34` |
| F-13 | Controllo del minimo (`min_stake_rules`) su ogni strada calcio: runner, domanda diretta, ordini vecchi | `Betfair/stream/live_order_build.py:179`, `Betfair/stream/live_order_build.py:813`, `Betfair/omega/omega_market.py:731`, `Betfair/order_exec.py:269` |
| F-14 | Verdetto completo (`verdetto_minimi`) nel motore del filo e nella coda; la «traduzione» sull'altra selezione e' spenta per tutti (insieme vuoto) | `Betfair/stream/live_order_build.py:594`, `Betfair/stream/motore_ordini.py:1312`, `Betfair/stream/trading/minimi_it.py:56` |
| F-15 | Bot tennis (dentro il runner tennis) e sessioni scalper piazzano nel proprio processo (flumine) | `Betfair/stream/tennis_live/guardie_tennis.py:109`, `Betfair/stream/scalper/scalper_bot.py:2462` |
| F-16 | Scalper e sniper calcio usano un minimo proprio di 2,00 EUR | `Betfair/stream/scalper/scalper_bot.py:69` |

## G. L'app (capitolo 8)

| N. | Fatto | Prova |
|---|---|---|
| G-1 | Il guscio serve la pagina su 127.0.0.1:47330 e apre la finestra su `/board` | `desktop/main.js:25`, `desktop/main.js:213`, `desktop/main.js:903` |
| G-2 | Il guscio passa allo schermo SOLO la chiave dei canali (nessun altro collegamento interno) | `desktop/preload.js:21` |
| G-3 | Comandi: solo funzioni del database (es. `mike_activate`, `safe_activate`, `omega_activate`, `scalper_activate`, `tennis_bot_arm`) | `frontend/src/lib/mike.ts:2228`, `frontend/src/lib/safeBot.ts:1147`, `frontend/src/lib/omega.ts:1311`, `frontend/src/lib/scalper.ts:145`, `frontend/src/lib/tennis.ts:876` |
| G-4 | Letture di stato: funzioni `get_*_state` e aggiornamenti istantanei del database (realtime) | `frontend/src/lib/mike.ts:2248`, `frontend/src/lib/mike.ts:2345`, `frontend/src/lib/safeBot.ts:1177` |
| G-5 | Ritmi dello schermo: Mike e Safe 15 s, Omega 15 s, scalper 4 s, bot tennis 30 s, Control Room 30 s | `frontend/src/components/mike/useMike.ts:31`, `frontend/src/components/safestrategy/useSafeBot.ts:26`, `frontend/src/pages/Omega.tsx:272`, `frontend/src/components/live/ScalperPanel.tsx:57`, `frontend/src/components/controlroom/useControlRoom.ts:208` |
| G-6 | Dopo un pulsante lo schermo sveglia il bot sul suo canale | `frontend/src/lib/localChannel.ts:338` |
| G-7 | Le tabelle di comando lette dai bot: `mike_control`, `safe_strategy_control`, `omega_control`, `scalper_control`, `tennis_bot_control` | `Betfair/mike/service.py:3953`, `Betfair/safe_strategy/bot_service.py:9864`, `Betfair/omega/omega_service.py:7809`, `Betfair/stream/scalper/scalper_service.py:75`, `Betfair/stream/tennis_live/tennis_bot_service.py:170` |

## H. Il banco di prova (capitolo 9)

| N. | Fatto | Prova |
|---|---|---|
| H-1 | Ingresso unico `python -m Betfair.stream.backtest.certifica <bot>`; il referto misura la condotta, non il profitto | `Betfair/stream/backtest/certifica.py:1`, `Betfair/stream/backtest/certifica.py:15` |
| H-2 | Registro: 11 bot (mike, omega, safe_base, safe_esatto, safe_punta, safe_tennis, scalper_calcio, tennis_scalper, tennis_pro, tennis_flb, tennis_swing) | `Betfair/stream/backtest/registro_bot.py:188`, `Betfair/stream/backtest/registro_bot.py:352` |
| H-3 | Betfair simulata: `FlumineSimulation` che rilegge il flusso registrato in `_live_raw/<id>/<id>.raw.jsonl` | `Betfair/stream/backtest/banco_comune.py:6`, `Betfair/stream/backtest/banco_comune.py:2828` |
| H-4 | Il tempo di mercato scorre anche durante il piazzamento (ritardo delle scommesse) | `Betfair/stream/backtest/banco_comune.py:1905` |
| H-5 | Al posto della domanda diretta: `MercatoFlumine` con `place_order_live` / `place_submin_live` | `Betfair/stream/backtest/banco_comune.py:499`, `Betfair/stream/backtest/banco_comune.py:620` |
| H-6 | Database in memoria `DbMemoria` (nessun Supabase) | `Betfair/stream/backtest/banco_comune.py:217` |
| H-7 | Strada del filo nel banco: client vero sul canale di prova, dall'altra parte il `MotoreOrdini` vero | `Betfair/stream/backtest/trasporto.py:1`, `Betfair/stream/backtest/porta_banco.py:446` |

## I. Dove e' il peso (capitolo 10)

| N. | Fatto | Prova |
|---|---|---|
| I-1 | Righe dei file piu' grandi: `safe_strategy/bot_service.py` 10.862; `omega/omega_service.py` 8.709; `mike/service.py` 7.496; `mike/engine.py` 5.097; `stream/live_order_worker.py` 3.991; `safe_strategy/service.py` 3.444; `stream/runner.py` 3.116; `stream/motore_ordini.py` 2.417; `desktop/main.js` 959 | `wc -l` alla base `22d19cc` |
| I-2 | Rilettura degli ordini per bot: runner (30 s), Safe, Omega, Mike, scalper; tre scritture a domanda diverse di «ordini aperti / regolati» | `Betfair/stream/reconcile_worker.py:287`, `Betfair/safe_strategy/bot_service.py:1085`, `Betfair/omega/omega_service.py:4155`, `Betfair/mike/service.py:5761`, `Betfair/omega/omega_market.py:1540`, `Betfair/client.py:361` |
| I-3 | La decisione di riconciliazione esiste due volte (Safe/Mike e Omega) | `Betfair/safe_strategy/execution.py:1381`, `Betfair/omega/omega_service.py:4215` |
| I-4 | La scrittura in coda ordini e' copiata tre volte (Omega, Safe, Mike) | `Betfair/omega/omega_db.py:634`, `Betfair/safe_strategy/bot_db.py:1003`, `Betfair/mike/db.py:662` |
| I-5 | Quattro strade per gli ordini calcio (filo, coda, domanda diretta, ordini a mano vecchi) | F-4, F-5, F-9, F-11 |
| I-6 | Lo scanner (feed di tutti) vive nel programma del Safe | E-1 |

---

## Mappa: ogni scatola e ogni freccia con la sua prova

### Capitolo 1 - vista d'insieme (`01_vista_insieme`)
| Elemento | Prova |
|---|---|
| Scatole Betfair, Runner calcio, Scanner, Runner tennis, Scalper, Mike, Safe, Omega, Ponte, App | A-1 ... A-9, G-1 |
| Scatola Database Supabase (1.309/min) | D-M |
| Frecce Betfair -> runner calcio, scanner, runner tennis, scalper (linea continua) | B-4, B-9, B-7, B-8 |
| Frecce verso il database con i numeri (552, 86, 28, 54, 279, 269, 5, 36) | D-M |
| Freccia App -> database (legge e comanda) | G-3, G-4 |

### Capitolo 2 - processi e guardiani (`02_processi_e_guardiani`)
| Elemento | Prova |
|---|---|
| App -> Guardiani (accende 8) | A-1 ... A-9 |
| App -> Quote tennis (ogni 30 min, senza guardiano) | A-10 |
| Guardiani -> 8 programmi | A-2 ... A-9 |
| Guardiani -> Avvisi (se cade) | A-13, A-16 |
| Riquadri sotto lo schema (uscita pulita, caduta, chiusura) | A-11 ... A-15, A-18 |

### Capitolo 3 - linee con Betfair (`03_linee_con_betfair`)
| Elemento | Prova |
|---|---|
| Linea continua -> runner calcio, scanner, runner tennis, sessioni scalper | B-4, B-9, B-7, B-8 |
| Runner calcio -> domande (saldo 20 s, ordini 30 s) | B-5 |
| Scanner -> domande (punteggi 2 s, elenco 5 min) | B-10, B-11 |
| Runner tennis -> domande (sessione 8 min) | B-7 |
| Sessioni scalper -> domande (avvio e arresto) | B-8 |
| Mike -> domande (ordini veri, se serve) | F-8, B-15 |
| Safe -> domande (se serve o manca il feed) | F-6, B-14 |
| Omega -> domande (elenco partite ogni giro) | B-13 |
| Quote tennis -> domande | B-16 |
| Riquadro «accesso» | B-1, B-2, B-3 |

### Capitolo 4a - canali verso lo schermo (`04a_canali_verso_lo_schermo`)
| Elemento | Prova |
|---|---|
| 8 programmi con la loro porta | C-4 ... C-11 |
| Frecce verso l'app e cosa passa | C-9, C-11, C-12, C-13, C-14 |
| Chiave segreta -> app | C-2, C-3 |
| Riquadri sotto lo schema | C-1, C-21, F-10 |

### Capitolo 4b - canali fra programmi (`04b_canali_fra_programmi`)
| Elemento | Prova |
|---|---|
| Scanner -> Mike, Safe, Omega (righe ogni 2,5 s) | C-9, C-15 |
| Scanner -> runner calcio (punteggi) | C-16 |
| Mike -> runner calcio (ordini in prova, conto) | C-17, C-18, F-8 |
| Safe, Omega -> runner calcio (ordini ed esiti) | C-17, C-18 |
| Safe -> runner tennis (ordini Safe tennis) | C-19 |
| Runner tennis -> ponte (posizioni bot tennis) | C-20 |
| Porte di sola guardia | A-19 |

### Capitolo 5a - database calcio (`05a_database_calcio`)
| Elemento | Prova |
|---|---|
| Runner calcio -> coda ordini e regole (480/min) | D-2, D-3, D-4, D-5, D-M |
| Runner calcio -> partite seguite e conto (62/min) | D-6, D-M |
| Runner, Mike, Safe -> righe dello scanner (10, 14, 10/min) | D-7, D-11, D-M |
| Scanner -> righe dello scanner (74/min) | D-8, D-M |
| Mike -> tabelle di Mike (265/min) | D-10, D-M |
| Safe -> tabelle di Safe (259/min) | D-12, D-13, D-M |
| Omega -> tabelle di Omega (5/min) | D-14, D-M |

### Capitolo 5b - database tennis e scalper (`05b_database_tennis_scalper`)
| Elemento | Prova |
|---|---|
| Runner tennis -> partite tennis seguite (28/min) | D-15, D-M |
| Ponte -> partite seguite (3/min) e comandi bot tennis (33/min) | D-16, D-M |
| Scalper -> comandi scalper (36/min) e impostazioni (18/min) | D-17, D-M |
| Quote tennis -> partite tennis del giorno | D-18, D-M |

### Capitolo 6 - scanner (`06_scanner_feed_unico`)
| Elemento | Prova |
|---|---|
| Linea continua -> scanner (quote ogni 1 s) | B-9 |
| Domande -> scanner (punteggi ogni 2 s) | B-10 |
| Scanner -> filo 47336 (ogni 2,5 s) | C-9 |
| Scanner -> righe (68/min), stato (ogni 10 s) | D-8, D-M |
| Scanner -> posizioni dei bot (ogni 10 s) | E-6 |
| Filo -> Mike, Safe, Omega | C-15 |
| Righe -> altri lettori | E-9, D-7 |
| Riquadri | B-11, E-7, E-10 |

### Capitolo 7 - porta degli ordini (`07_porta_degli_ordini`)
| Elemento | Prova |
|---|---|
| App -> filo (con la chiave) | F-10, C-3 |
| Safe e Omega -> filo (prima scelta) | F-6, F-7, C-17 |
| Mike in prova -> filo | F-8 |
| Filo giu' -> coda | F-6, F-7, F-10 |
| Coda fallita, solo live -> domanda diretta | F-6, F-7 |
| Mike vero -> domanda diretta (sempre) | F-8 |
| Filo -> runner (subito) | F-4 |
| Coda -> runner (riletta ogni 1 s) | D-2, F-5 |
| Runner -> Betfair (vero o simulato) | F-2, F-3 |
| Domanda diretta -> Betfair | F-9 |
| Ordini a mano vecchi -> Betfair | F-11 |
| Riquadri | F-12, F-13, F-14, F-3, F-15 |

### Capitolo 8 - app (`08_app_letture_e_comandi`)
| Elemento | Prova |
|---|---|
| Guscio -> schermo (pagina e chiave) | G-1, G-2 |
| Schermo -> funzioni di comando (pulsante) | G-3 |
| Funzioni -> tabelle di comando (scrive) | G-3, G-7 |
| Tabelle di comando -> bot con il loro ritmo | G-7, A-20 |
| Letture di stato -> schermo | G-4, G-5 |
| Fili -> schermo | C-14, G-6 |

### Capitolo 9 - banco (`09_banco_di_prova`)
| Elemento | Prova |
|---|---|
| Comando certifica, referto | H-1 |
| Registro -> servizio del bot (codice vero) | H-2 |
| Partite registrate -> Betfair simulata | H-3 |
| Betfair simulata -> bot; porta di prova -> Betfair simulata | H-3, H-4, H-5 |
| Bot -> porta di prova (coda o filo) | H-5, H-7 |
| Bot -> database in memoria | H-6 |

### Capitolo 10 - peso (`10_dove_e_il_peso`)
| Elemento | Prova |
|---|---|
| 5 frecce con i numeri | D-M |
| Riquadro file piu' grandi | I-1 |
| Riquadro doppioni | I-2 ... I-6 |

---

## Punti non chiariti (non disegnati o non verificati)

1. Le chiamate a Betfair non sono contate una per una: nei registri non c'e' un contatore. I numeri
   «ogni N s» del capitolo 3 vengono dal codice, non da una misura.
2. Mike: un commento di `desktop/main.js:474` dice «nessun login/stream proprio», ma il registro di
   Mike del 02/10 mostra un accesso a Betfair (`certlogin SUCCESS`): e' il client a domanda di
   `omega_market` usato da Mike per gli ordini veri e il saldo. Lo stream proprio, invece, non c'e'.
3. Omega nel minuto misurato era fermo (registro di avvio: «il bot era gia' fermo in prova»): i suoi
   5/min non rappresentano Omega acceso (giro di 20 s).
4. Nessuna partita tennis seguita e nessuna sessione scalper accesa nel minuto misurato: i numeri del
   tennis e dello scalper sono quelli «a vuoto».
5. Un commento del runner (`Betfair/stream/runner.py:2747`) dice che la sessione a domanda resta viva
   grazie all'elenco partite ogni 15 s; un altro (`Betfair/stream/auth.py:100`) dice che le chiamate
   non prolungano la sessione. Non verificato quale sia vero.
6. Il registro di Omega e del Safe all'avvio mostra «canale di comando ... non disponibile»: al primo
   giro il runner non era ancora pronto; non verificato quanto duri il ripiego sulla coda.
