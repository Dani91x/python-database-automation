# AUDIT TEMPO REALE - bot e Control Room (24/09/2026)

Delegato Opus del coordinatore. SOLA LETTURA: nessun codice toccato, nessun processo avviato,
nessun accesso al DB. Base: master `20a913a` (fast-forward nel worktree, 16 integrazioni del
24/09 incluse). File relativi alla radice del repo salvo indicazione. `.env` letto SOLO per i nomi
degli interruttori (checkout principale, righe 22 e 39-55).

Legenda: [VERDE] passa dal canale al tick/ms; [GIALLO] canale presente ma con un collo che non e'
il canale (cadenza del ciclo, conflate, poll di ripiego che resta la via per un pezzo del dato);
[ROSSO] NON passa dal canale (DB/REST/poll) oppure il canale c'e' ma nessuno lo ascolta.

Domanda dell'utente: "Tutti i bot ora passano dal canale unico e quindi sono in tempo reale? La
Control Room mostra al trader tutti i dati al ms?"

---

## 0. RISPOSTA IN BREVE

1. **Bot: PARZIALE.** Il TRASPORTO dei dati d'ingresso e' sul canale per Omega, Mike e Safe
   (righe dello scanner da 47336, `OMEGA/MIKE/SAFE_BOT_LEGGE_CANALE=1`), per i punteggi di runner
   e board (`PUNTEGGI_CANALE=1`) e per gli esiti terminali degli ordini in coda di Omega/Safe
   (`ESITI_ORDINI_CANALE=1`). MA:
   - il dato che viaggia al ms e' gia' **conflato a 1 s da Betfair e al solo miglior livello**
     (`Betfair/safe_strategy/stream.py:22,64` `_CONFLATE_MS = 1000`, `ladder_levels=1`): il feed
     unico di Omega/Mike/Safe/Control Room non e' al tick, e' al secondo;
   - i punteggi vengono da un POLL IPS ogni 2 s (`Betfair/safe_strategy/service.py:128`), non da uno
     stream: nessuno puo' averli al ms (vale anche per i competitor che usano la stessa fonte);
   - le DECISIONI di Omega girano a `poll_interval_s` = 20 s (60 s a vuoto)
     (`Betfair/omega/omega_config.py:35`, `omega_service.py:7383-7411`): la sveglia dal canale
     anticipa il giro SOLO per le partite con posizione viva, col pavimento di 5 s
     (`omega_service.py:513-541,577-584`);
   - l'INVIO degli ordini NON passa dal canale per nessun bot calcio: Omega e Safe usano la coda DB
     (o il REST FOK in ripiego silenzioso), Mike e Safe tennis il REST diretto; il motore ordini a
     evento e la porta di Safe esistono ma sono SPENTI (`MOTORE_ORDINI_CANALE`,
     `SAFE_ORDINI_VIA_CANALE` assenti dal `.env`);
   - gli esiti di Mike (REST + `listCurrentOrders` a ogni giro) e dei bot tennis (in memoria flumine)
     non passano dal canale; scalper calcio e xhedge stanno fuori dal canale.
   Solo i 4 bot tennis (flumine nello stesso processo, conflate 0) sono davvero al tick, ma per
   costruzione (in-process), non grazie al canale.
2. **Control Room: PARZIALE (piu' NO che SI per le righe dei bot).** Al ms arrivano: righe dello
   scanner (prezzi di best level, minuto/punteggio) da 47336, colonne di righe GIA' NOTE di
   Omega/Safe/Mike da 47333-47335, saldo e P&L reale del conto da `account`. MA:
   - **una posizione NUOVA di un bot compare solo al poll dei 30 s** (`RICARICA_MS = 30_000`,
     `frontend/src/components/controlroom/useControlRoom.ts:151,1064`): il canale "non puo' mai
     aggiungere una riga" (`frontend/src/lib/righeCanale.ts:18-20,168-169`) e la Control Room non ha
     realtime Supabase sulle tabelle dei trade (nessun `subscribeSafeBot/subscribeOmega/
     subscribeMike` in `useControlRoom.ts`: solo 1073, 1105, 1127-1128, 1154, 1176, 1184, 1205,
     1211, 1222, 1247);
   - i 4 bot tennis (stato, P&L, ordini) sono SOLO a poll 30 s (`useControlRoom.ts:984-987`);
     il canale 47337 non ha NESSUN sottoscrittore in tutto il frontend (grep `tennis_bot_stato|
     tennis_bot_posizioni|getLocalChannel('tennis_bot')` = solo commenti in `lib/localChannel.ts`);
   - stato/modalita'/parametri dei bot, stato runner, "Ordini reali OFF/PAPER/LIVE" a poll 30 s;
   - tennis nella scheda partita: realtime Supabase `tennis_live_now`, non il canale
     (`frontend/src/components/controlroom/useTennisVivo.ts:60-63`);
   - la scheda delle proposte mostra il prezzo vivo dello scanner ma NON ricalcola EV/semaforo al
     prezzo (voci A-G del delegato, NON fatte: `.claude/worktrees/agent-a5d6a648b59d268f2/
     STATO_RIPRESA.md:41-75`).
   Eta' e fonte sono DICHIARATE a video quasi ovunque (dettagli in 2.2).

---

## 1. MATRICE LATO BOT

Interruttori letti nel `.env` del checkout principale (sola lettura dei nomi): `LIVE_ORDER_MODE=LIVE`
(r.22), `SAFE_SCAN_CANALE`, `MIKE/OMEGA/SAFE_CANALE_POSIZIONI`, `TENNIS_BOT_CANALE`,
`SAFE_BOT_LEGGE_CANALE`, `SAFE_BOT_SVEGLIA_CANALE`, `OMEGA/MIKE/TENNIS_BOT_SVEGLIA_CANALE`,
`SAFE_BOT_GIRO_VELOCE`, `MIKE_LEGGE_CANALE`, `OMEGA_LEGGE_CANALE`, `PUNTEGGI_CANALE`,
`ESITI_ORDINI_CANALE` = 1; `LIVE/TENNIS_LADDER_CANALE_MS=200` (r.39-55). ASSENTI (= spenti):
`MOTORE_ORDINI_CANALE` (`Betfair/stream/runner.py:1609`), `SAFE_ORDINI_VIA_CANALE`,
`SAFE_TENNIS_ORDINI_VIA_CANALE` (`Betfair/safe_strategy/porta_ordini.py:54-55`),
`MIKE_USE_FLUMINE_QUEUE` (`Betfair/mike/service.py:683`). Tutti gli interruttori: default SPENTO
se assenti (`Betfair/stream/canale_bot.py:117-124`).
L'app passa inoltre ai processi (vince sul `.env`: `load_dotenv()` senza override,
`Betfair/stream/config_stream.py:16-17`): `LIVE_ORDER_QUEUE_POLL_SEC=0.15`,
`TENNIS_ORDER_POLL_SEC=0.15`, `LIVE_RISK_ENGINE_POLL_SEC=0.15`, `LIVE_LADDER_PUBLISH_SEC=0.3`,
`TENNIS_LIVE_ORDER_MODE=PAPER` di serie (`desktop/main.js:233-250`).

### 1.0 La fonte comune: lo scanner (47336)

| voce | fatto | prova |
|---|---|---|
| prezzi | Exchange Stream, **conflate 1000 ms**, **best offers ladder_levels=1**, max 4 connessioni x 180 mercati, il resto a poll REST | `Betfair/safe_strategy/stream.py:18-22,64` |
| pubblicazione sul canale | a OGNI cambiamento, prima del freno DB 2,5 s | `Betfair/safe_strategy/service.py:1465-1494,1636-1646` |
| punteggi | poll IPS `scoresAndBroadcast` ogni 2 s, thread dedicato | `service.py:14,128,1014` |
| misura 23/09 | eta' della riga sul canale p50 9 ms / p95 36 ms; ritardo da Betfair (`odds_pt_ms`) p50 2,06 s / p95 17 s calcio | `CRONOSTORIA.md` checkpoint C5-F1 23/09 h19:30 (sezione 23/09, righe ~2254-2262) |
| [GIALLO] | il trasporto e' al ms, la MATERIA PRIMA e' al secondo e al primo livello; il runner calcio invece usa conflate 0 (`Betfair/stream/config_stream.py:87`, `runner.py:1942`) ma pubblica solo i mercati SEGUITI | - |

### 1.1 Omega (servizio `Betfair/omega/omega_service.py`, canale 47334)

| I/O | fonte | cadenza reale | interruttore (default) | ripiego se il canale cade | prova |
|---|---|---|---|---|---|
| quote/book per decidere | riga scanner da 47336 fusa col DB (`fondi`: vince la piu' recente con `odds_ts_ms`), eta' max 5 s; DB riletto ogni 10 s | trasporto ms, dato conflato 1 s | `OMEGA_LEGGE_CANALE` (spento) = 1 | DB `safe_strategy_scan` ogni `feed_cache_s` | `omega_service.py:384-435,513-516,594-633` |
| [GIALLO] giro delle decisioni | `run_once` a `poll_interval_s` 20 s (min 5), `idle_cycle_s` 60 s a vuoto; sveglia dal canale SOLO per partite con posizione viva, pavimento 5 s | **5-60 s** | `OMEGA_SVEGLIA_CANALE`=1, `OMEGA_CANALE_GIRO_MINIMO_S` (5) | sonno pieno | `omega_config.py:35`; `omega_service.py:519-541,577-584,7315-7321,7375-7411` |
| [ROSSO] book REST | `read_book` REST per manuale, cash-out se feed non fresco, missioni scalp | a richiesta | - | - | `omega_service.py:4454,4531,4820,6276` |
| punteggi | riga scanner (canale) + `scan_feed` canale-first | IPS 2 s | `PUNTEGGI_CANALE`=1 | DB | `omega_service.py:7420-7425`; `Betfair/stream/scores/scan_feed.py:102-141,284` |
| stato scanner | `safe_strategy_status` via cache, TTL `scanner_status_cache_s` | ~10 s | - | - | `omega_service.py:438-456` |
| [GIALLO] esiti dei propri ordini | canale 47331 `/lettore/order` SOLO terminali, applicati sotto il lucchetto del ciclo; parziali/intermedi al `poll_flumine_pending` del giro | terminali: ms + fine giro; parziali: 20-60 s | `ESITI_ORDINI_CANALE`=1 | poll specchio `betfair_live_orders` al giro | `omega_service.py:726-760,3194`; `Betfair/stream/esiti_ordini_canale.py:74,82` |
| saldo | rilettura `getAccountFunds` su evento d'ordine, publish `account` sul canale del processo | evento | sempre | - | `omega_service.py:7348-7350`; `Betfair/stream/saldo_evento.py:120-126` |
| comandi utente | riga DB (`process_manual` dentro `run_once`) + sveglia UI su 47334, pavimento 1 s | ~1 s + giro | `OMEGA_SVEGLIA_CANALE`=1 | cadenza del ciclo (20-60 s) | `omega_service.py:4397-4406,6807,7247-7259`; `Betfair/stream/sveglia_canale.py:84`; `frontend/src/lib/localChannel.ts:330-334` |
| [ROSSO] invio ordini | coda DB `betfair_live_order_requests` (worker runner) se `_flumine_gate` ok, altrimenti REST FOK (ripiego silenzioso) | coda: 5 RTT bot + giro worker (DB letto al piu' 1/s con desktop collegato) | nessuno sul canale per Omega | REST | `omega_service.py:2305,2476,2602-2694`; `Betfair/stream/live_order_worker.py:3509-3522,537-540`; `Betfair/stream/local_channel.py:536-542,746-748` |
| pubblicazione per la UI | `omega_posizioni`, `omega_attivita`, `omega_proposta` dopo la scrittura DB; `omega_stato` a fine giro | a scrittura / a giro | `OMEGA_CANALE_POSIZIONI`=1 | la UI resta sul DB | `Betfair/omega/omega_db.py:67-99,397-427`; `omega_service.py:7104,7324-7333` |

### 1.2 Mike (`Betfair/mike/service.py`, canale 47333)

| I/O | fonte | cadenza | interruttore | ripiego | prova |
|---|---|---|---|---|---|
| quote O/U | riga scanner da 47336 fusa col DB, eta' max 5 s, DB lento solo se il canale copre OGNI partita | trasporto ms, dato 1 s | `MIKE_LEGGE_CANALE`=1 | DB (`feed_cache_s` 4 s) | `service.py:4592,4696`; `Betfair/mike/config.py:303`; `CRONOSTORIA.md` 23/09 h19:50 e fix M-1 |
| giro delle decisioni | ~1 s attivo (`decide_min_interval_ms` 500 x 2), 5 s a vuoto; sveglia dal canale | 1-5 s | `MIKE_SVEGLIA_CANALE`=1 | sonno | `service.py:4845-4878`; `mike/config.py:87,315` |
| punteggi | riga scanner | IPS 2 s | come sopra | DB | idem |
| [ROSSO] esiti dei propri ordini | risposta REST sincrona (FOK); appoggiate: `listCurrentOrders` REST a ogni giro; ignoti: `_reconcile_unknown` | 1-5 s; thread fermo per il bet delay | nessuno (Mike fuori dal blotter del runner) | - | `service.py:555,683,1129,1545-1560,1710,3841-3873` |
| saldo | su evento | evento | sempre | - | `service.py:4830` |
| comandi utente | `process_requests` da DB a ogni giro + sveglia UI 47333 | ~1 s | `MIKE_SVEGLIA_CANALE`=1 | giro | `service.py:2272,4473-4520` |
| [ROSSO] invio ordini | REST JSON-RPC diretto (`execution_mode="rest"`), coda flumine SPENTA e rotta (M1) | 0,1-0,5 s + bet delay bloccante | `MIKE_USE_FLUMINE_QUEUE` assente | - | `service.py:683`; `AUDIT_STRADE_ORDINE_2026-09-24.md` par. 1.4 e 2.2 M1 |
| pubblicazione UI | `mike_posizioni`, `mike_attivita` dopo scrittura; `mike_event`, `mike_stato` a giro | a scrittura / a giro | `MIKE_CANALE_POSIZIONI`=1 | DB | `Betfair/mike/db.py:78,159,169`; `service.py:4794,4803` |

### 1.3 Safe calcio e Safe tennis (`Betfair/safe_strategy/bot_service.py`, canale 47335; stesso processo)

| I/O | fonte | cadenza | interruttore | ripiego | prova |
|---|---|---|---|---|---|
| quote/punteggi | `ClientScan` 47336 + riallineamento DB ogni 10 s; senza righe fresche DB a ogni giro | trasporto ms, dato 1 s | `SAFE_BOT_LEGGE_CANALE`=1 | DB ogni `poll_interval_s` | `bot_service.py:7937,7957-7962,8039-8060` |
| giro delle decisioni | `poll_interval_s` 2 s + giro veloce in memoria (max 4/s, max 6 anticipi/min) solo su posizioni vive; opportunita'/anomalie ogni `opps_interval_s` 10 s | 2 s (0,25 s per le uscite anticipate) | `SAFE_BOT_GIRO_VELOCE`=1 | 2 s | `bot_service.py:127,153,6396,8139-8143,8415,9237` |
| controllo/parametri | `read_control` dal DB a ogni giro | 2 s | - | - | `bot_service.py:9232-9237` |
| [GIALLO] esiti ordini calcio in coda | come Omega (`poll_flumine` delega a Omega) + canale terminali | terminali ms, parziali 2 s | `ESITI_ORDINI_CANALE`=1 | poll 2 s | `bot_service.py:738-746` |
| [ROSSO] esiti Safe tennis | risposta REST (Safe tennis va SEMPRE in REST: il gate guarda `live_follow`, tabella del runner CALCIO) | sincrono | - | - | `Betfair/safe_strategy/execution.py:970-980`; `omega_service.py:2602`; `AUDIT_STRADE_ORDINE` par. 1.4 |
| saldo | su evento | evento | sempre | - | `bot_service.py:9202` |
| comandi utente | riga DB `safe_strategy_requests` + sveglia 47335 | giro successivo (<= 2 s) | `SAFE_BOT_SVEGLIA_CANALE`=1 | 2 s | `bot_service.py:7999,9205-9208`; `frontend/src/components/controlroom/useControlRoom.ts:1972-1991` |
| [ROSSO] invio ordini | coda DB (o REST FOK in ripiego); la porta sul canale F5 esiste ma e' SPENTA; tennis sempre REST | coda: vedi Omega | `SAFE_ORDINI_VIA_CANALE` / `SAFE_TENNIS_ORDINI_VIA_CANALE` assenti | REST | `bot_service.py:768-799,9211-9215`; `porta_ordini.py:54-55` |
| pubblicazione UI | `safe_posizioni_calcio/tennis`, `safe_attivita`, `safe_proposta`; `safe_stato` a giro | a scrittura / 2 s | `SAFE_CANALE_POSIZIONI`=1 | DB | `Betfair/safe_strategy/bot_db.py:83-117,651-756`; `bot_service.py:8973` |

### 1.4 I 4 bot tennis (scalper/pro/flb/swing, ospitati in `Betfair/stream/tennis_live/tennis_runner.py`)

| I/O | fonte | cadenza | interruttore | ripiego | prova |
|---|---|---|---|---|---|
| [VERDE] quote/book | callback flumine nello stesso processo, conflate di default (nessuno) | tick | - | - | `AUDIT_TUTTO_AL_MS` D2; `tennis_runner.py:600-601` |
| punteggi | `ScanFeedScoreProvider` (canale-first) nel `score_and_now_worker` | 2 s | `PUNTEGGI_CANALE`=1 | DB | `tennis_runner.py:64,83,1131-1142,1753-1754` |
| [VERDE] esiti ordini | oggetti Order in memoria dallo stream ordini | tick | - | - | `AUDIT_STRADE_ORDINE` par. 1.5 |
| [ROSSO] armamento/stop per partita | `bot_control_worker` legge `tennis_bot_control` dal DB | 3 s, nessuna sveglia sul runner | - | - | `tennis_runner.py:84,1756-1757` |
| comandi di servizio | `tennis_bot_service` (ponte) a 15 s, sveglia da 47337 | ~1 s con sveglia | `TENNIS_BOT_SVEGLIA_CANALE`=1 | 15-30 s | `tennis_bot_service.py:40,43,277-320` |
| saldo | su evento d'ordine (`saldo_evento`) | evento | sempre | - | `tennis_runner.py:1568-1575,1693` |
| [VERDE] invio ordini | `market.place_order` in-process | < 1 ms | - | - | `AUDIT_STRADE_ORDINE` par. 1.5 |
| [ROSSO] pubblicazione UI | `tennis_bot_stato` (servizio) su 47337; `tennis_bot_posizioni` = righe di ARMAMENTO (`tennis_bot_control`), non posizioni; quando le scrive il RUNNER finiscono sul canale del processo runner (47332), non su 47337. Nessun sottoscrittore nel frontend | - | `TENNIS_BOT_CANALE`=1 | la UI legge il DB | `Betfair/stream/tennis_live/tennis_db.py:40,192-221,451,486`; `Betfair/stream/canale_bot.py:127-139`; `tennis_runner.py:1244,1335-1353` (deduzione dal codice, non osservata) |

### 1.5 Runner calcio (47331) e worker ospitati

| I/O | fonte | cadenza | prova |
|---|---|---|---|
| [VERDE] ladder | RAM flumine (conflate 0), canale a `LIVE_LADDER_CANALE_MS` 200 ms, DB 2 s; SOLO mercati seguiti | 200 ms | `CRONOSTORIA.md` 23/09 h21:20; `config_stream.py:60,87` |
| [GIALLO] `now` (minuto/punteggio) | `score_worker` da `scan_feed` canale-first | 5 s | `config_stream.py:32` |
| [VERDE] `order`/`position` | publish PRIMA dell'upsert DB | evento | `AUDIT_STRADE_ORDINE` par. 1.1 (Esito) |
| `account` | `getAccountFunds` ogni 20 s + su evento; P&L reale del conto (`listClearedOrders`) al giro di riconciliazione | 20 s / 30 s | `Betfair/stream/reconcile_worker.py:96,182-212,959-1050`; `config_stream.py:301` |
| [GIALLO] `board` | `board_worker` da `scan_feed` canale-first | 10 s | `config_stream.py:308` |
| [GIALLO] comandi del desktop (47331) | drenati a ogni giro del worker (0,15 s dall'app) con IO DB nel giro; coda DB dei bot letta al piu' ogni 1 s quando un desktop e' collegato | 0,15 s + IO | `desktop/main.js:233`; `live_order_worker.py:3509-3522`. NOTA: `AUDIT_STRADE_ORDINE` par. 1.1 punto 1 dice 1,0 s "e il .env non lo cambia": vero per il `.env`, ma l'app passa 0,15 s, quindi le stime 0,6-2,2 s sono pessimiste per l'avvio dall'app (da misurare, F0) |
| motore ordini a evento (F1-F3) | opt-in, SPENTO | p95 1,6-4 ms misurato dal delegato | `runner.py:1609`; `CRONOSTORIA.md` 24/09 h16:40 |

### 1.6 Scalper calcio e xhedge

| bot | I/O | fonte | cadenza | prova |
|---|---|---|---|---|
| [ROSSO] scalper calcio | quote | flumine proprio per partita (stream suo) | tick | `AUDIT_STRADE_ORDINE` par. 1.6 |
| | punteggi / intervallo | `live_now` dal DB (watcher) | 15-20 s | `Betfair/stream/scalper/scalper_session.py:763-785,884-917` |
| | comandi | `scalper_control` dal DB | 3 s (supervisore) | `scalper_service.py:34,52,268` |
| | UI | `scalper_activity` solo DB, nessun canale | - | `scalper_service.py:62-63`; `scalper_session.py:417-428` |
| [ROSSO] xhedge | book CS | RAM del recorder (tick) | letto ogni 5 s | `Betfair/stream/xhedge_worker.py:56-60`; `config_stream.py:289` |
| | posizioni | SELECT `betfair_live_orders` | 5 s | `xhedge_worker.py:94` |
| | uscita per la UI | upsert `betfair_live_xhedge` SOLO DB | 5 s; la UI (`XHedgePanel`, in SeguiLive) poll 5 s | `xhedge_worker.py:118`; `frontend/src/components/live/XHedgePanel.tsx:157,181` |

---

## 2. MATRICE LATO CONTROL ROOM (`frontend/src/pages/ControlRoom.tsx`)

Meccanica generale:
- UNA ricarica di 18 letture DB ogni 30 s (`useControlRoom.ts:151,963-988,1062-1066`), con overlay
  dei canali "mai unione" (`frontend/src/lib/righeCanale.ts:10-20,159-181`).
- Canali sottoscritti dalla Control Room: 47336 `scan_calcio`/`scan_tennis` (`useControlRoom.ts:
  1119-1128`), 47333-47335 `*_stato` e topic per riga (`:1140-1192`, lista `:546-555`), 47331
  `account` (`:1211`) e `account` anche su 47332-47335 (`SaldoBetfairCard.tsx:31,89,108`).
  NON sottoscritti: 47331 `ladder/now/order/position/board`, 47332 tutto tranne `account`, 47336
  `scanner_stato`, 47337 tutto.
- Realtime Supabase: `safe_strategy_scan` righe (`:1105`), `safe_strategy_status` (`:1073`),
  `betfair_live_account` (`:1205`), proposte Safe/Omega (`:1222-1248`, con rilettura RPC).
- Orologio delle eta' 1 s (`:172,1251-1253`).

### 2.1 Matrice per zona

| zona (file:riga) | da dove arriva | cadenza | eta'/fonte a video | se il canale cade | giudizio |
|---|---|---|---|---|---|
| Banner modalita' (`ControlRoom.tsx:445`) | control dei bot (poll) | 30 s | no eta' | - | [ROSSO] |
| Obiettivo / barra di giornata (`ControlRoom.tsx:472-500`, `ObiettivoHero`) | P&L reale del conto: canale `account` (`pnl_reale_oggi`) o realtime `betfair_live_account`; senza conto: righe dei bot (poll+overlay); obiettivo da control Omega | P&L reale al giro reconcile 30 s (Betfair regolati); righe 30 s | fonte SI (nota "conto Betfair" / "dalle righe dei bot", `ControlRoom.tsx:488-492`); eta' no | realtime DB, poi 30 s | [GIALLO] (il realizzato dipende dal regolamento Betfair: non puo' essere al ms) |
| Saldo / esposizione (`ControlRoom.tsx:506`, `SaldoBetfairCard.tsx:89-120`) | canale `account` su 5 porte + realtime DB | 20 s runner + su evento | eta' SI (`fmtAge`), fonte implicita | realtime | [VERDE] per il trasporto |
| Esposizione/"con posizione" in testata (`ControlRoom.tsx:~878-890`) | derivati dalle righe dei bot | righe note: ms; righe nuove: 30 s | `-` finche' non letto | poll | [ROSSO] per le posizioni nuove |
| Chip bot (Omega/Safe/Mike) (`ControlRoom.tsx:917,1053-1066`) | `*_stato` (solo l'istante; il contenuto solo per Omega `:1154-1160`) + heartbeat DB | a giro del bot (Safe 2 s, Mike 1-5 s, Omega 20-60 s) | eta' SI, cadenza dichiarata dal servizio (`lib/controlRoom.ts:125-134`) | "senza spinta" arancione (`:1065`) | [GIALLO] |
| Chip dei 4 bot tennis | `fetchTennisBotServices` (poll) | 30 s | eta' del battito DB | - | [ROSSO] (47337 non ascoltato) |
| Fonte/eta' feed (`ControlRoom.tsx:~920-946`) | calcolo pagina | 1 s | SI: "canale locale"/"database" e per bot "canale/db + eta'" (`:930-944`) | dichiarato | [VERDE] (commento stantio `:928-929` "oggi i canali sono muti") |
| Runner calcio/tennis (`ControlRoom.tsx:970-1000`) | `betfair_live_heartbeat` (poll, `lib/safeBot.ts:2026-2029`) | 30 s | eta' del battito SI | - | [ROSSO] |
| Interruttori (`PannelloBot`, `ControlRoom.tsx:560`) | control dei bot (poll) + scrittura RPC + `svegliaBot` | lettura 30 s | no eta' | - | [ROSSO] per la lettura |
| "Ordini reali OFF/PAPER/LIVE" (`RigaOrdiniReali.tsx:32,79-83`) | RPC `betfair_live_settings` | 30 s | no | - | [ROSSO] |
| Righe per bot / Posizioni aperte (`ControlRoom.tsx:~1320-1400`) | poll 30 s + overlay colonne da 47333-47335 | colonne di righe note: ms; righe NUOVE o sparite: 30 s | SI per bot (`cr-fonte-righe`) | overlay scartato, torna il DB | [ROSSO] per ingresso/uscita delle righe |
| "Se chiudo ora" (Posizioni aperte `ControlRoom.tsx:1400`; schede `DettaglioRigaView.tsx`) | `chiusuraViva`/`prezzoVivo` sul payload dello scanner (47336 + realtime + poll) | dato 1 s conflato, best level | eta' quote SI (`etaQuoteS`), fonte solo a livello pagina | realtime DB scan | [GIALLO] |
| Scheda partita calcio (`SchedaPartita.tsx:309-360,493-497`) | riga scanner: minuto/punteggio/quote | quote 1 s, punteggi 2 s | eta' punteggio e latenza quote SI | realtime DB | [GIALLO] |
| Scheda partita tennis (`SchedaPartita.tsx:139-206`, `useTennisVivo.ts:60-63`) | realtime Supabase `tennis_live_now` | ~2 s (scrittura runner) | eta' SI (`cr-tennis-vivo-eta`) | - | [ROSSO] (47332 `now` e 47336 `scan_tennis` non usati per il punto) |
| Ladder | NON presente in Control Room (solo best level dello scanner) | - | - | - | n/a (la ladder al ms e' in SeguiLive/TennisTerminal) |
| Uscite / proposte di chiusura (`UsciteColonna`, `SchedaChiusura*`) | realtime DB proposte (rilettura RPC) + overlay 47334/47335; prezzo vivo dallo scanner | sub-secondo + RTT; prezzo 1 s | eta' quote SI | realtime DB | [GIALLO]; la tolleranza "prezzo cambiato" blocca ancora (voce C, `SchedaChiusura.tsx:90`, `lib/controlRoomProposte.ts:317`) |
| Opportunita'/anomalie (`OpportunitaColonna`, `SchedaPropostaOpportunita.tsx:83-106`) | idem; prezzo vivo e abbinabile dallo scanner (`useControlRoom.ts:1900-1932`) | prezzo 1 s | eta' SI, fonte no | realtime DB | [ROSSO] per i VALORI: EV/edge/semaforo non ricalcolati al prezzo (voci A-B non fatte) |
| Esito del "Chiudi" (`useControlRoom.ts:2272-2300`) | coda del bot riletta per id | 2 s (ripiego) | stato a video SI | - | [GIALLO] |
| Posizioni chiuse (`ControlRoom.tsx:705`, `PosizioniChiuse.tsx:79-89`) | derivate dalle righe (poll + overlay); P&L netto Betfair dalle colonne `pnl_betfair` | 30 s | certezza di chiusura SI, eta' no | - | [ROSSO] |
| Attivita' dei bot | NON presente in Control Room (solo nelle pagine Omega/Safe/Mike) | - | - | - | n/a |
| "Da Betfair al tuo schermo" (`ControlRoom.tsx:723-808`) | diagnostica, include il tratto "lettura database" | - | SI | - | [VERDE] diagnostica |

### 2.2 Eta' e fonte dichiarate
SI: feed (fonte canale/database + eta', `ControlRoom.tsx:925-944`), righe per bot (`cr-fonte-righe`),
chip bot (eta' push/battito), runner (eta' battito), saldo (eta'), quote in scheda e proposte
(`etaQuoteS`), tennis vivo (eta'), fonte del P&L di giornata (conto/righe).
NO: stato/modalita'/parametri dei bot, interruttori, "Ordini reali", posizioni chiuse, P&L
realizzato di giornata (eta'), fonte per SINGOLA quota ("canale" vs "database" e' solo di pagina).

### 2.3 Brief da correggere (attinenza)
`TennisBotPanel`, `LiveTradingPanel`, `TerminalPositionsRail`, `HabitatCard`, `RiskRulesPanel`,
`XHedgePanel` NON sono nella Control Room: sono importati solo da `pages/TennisTerminal.tsx`
(TennisBotPanel) e `pages/SeguiLive.tsx` (gli altri). Restano fuori dal canale (tabella 2.4).

### 2.4 Pagine fuori dalla Control Room

| pagina | canale usato | resta su DB | prova |
|---|---|---|---|
| SeguiLive | ladder al ms (`sorgenteLadderAlMs`), `now` 47331, posizioni 47331 overlay | follows 15 s; risk state/segnali/heartbeat realtime; LiveTradingPanel 3 s, TerminalPositionsRail 4 s, RiskRulesPanel 4 s, XHedgePanel 5 s, HabitatCard 60 s | `pages/SeguiLive.tsx:184,201-282,964,1038`; `components/live/*.tsx` (righe in 2.1) |
| MarketWatch | `now` 47331/47332, posizioni 47331/47332 overlay | follows 30 s, posizioni 10 s, `live_now`/`tennis_now` realtime | `pages/MarketWatch.tsx:142-194,249-294` |
| TennisTerminal | ladder 47332 al ms | `tennis_live_now` realtime; TennisBotPanel realtime + 30 s | `pages/TennisTerminal.tsx:62,264-269`; `components/tennis/TennisBotPanel.tsx:52,471-475` |
| Omega.tsx | `omega_stato` 47334 | poll 15 s + realtime | `pages/Omega.tsx:210-251,278` |
| SafeStrategy.tsx | via `useSafeBot` (47335) | poll 15 s | `pages/SafeStrategy.tsx:137,585`; `components/safestrategy/useSafeBot.ts` |
| Mike | `mike_event`/`mike_stato` 47333 | poll 15 s + realtime | `components/mike/useMike.ts:31,179-180,262-302` |
| LivePnl | nessuno | poll 15-30 s | `pages/LivePnl.tsx:213,236,249` |

---

## 3. VERDETTO E COSE DA FARE (senza implementare)

**Domanda 1 - "tutti i bot passano dal canale unico e sono in tempo reale?" -> PARZIALE.**
Gli INGRESSI di Omega/Mike/Safe passano dal canale, ma (a) il dato e' conflato a 1 s e al primo
livello dallo scanner, (b) i punteggi sono un poll a 2 s all'origine, (c) Omega decide ogni 20-60 s,
(d) nessun ORDINE calcio passa dal canale (coda DB / REST), (e) esiti di Mike, Safe tennis,
scalper, xhedge fuori dal canale. Solo i 4 bot tennis sono al tick (in-process).

**Domanda 2 - "la Control Room mostra tutti i dati al ms?" -> PARZIALE.** Al ms: prezzi/punteggi
dello scanner (con il limite di 1 s della fonte), colonne delle righe gia' note di Omega/Safe/Mike,
saldo. A 30 s: posizioni NUOVE, tutto il tennis bot, stato/modalita'/interruttori, runner, chiuse.
Eta' e fonte sono dichiarate nelle zone principali.

Lista ordinata (prima cio' che il trader vede sbagliato o in ritardo sui soldi):

1. **(S) Posizioni nuove dal canale senza aspettare 30 s**: alla ricezione su 47333-47335 di un id
   sconosciuto, far partire subito UNA rilettura del blocco di quel bot (come gia' fa
   `subscribeProposte`), mantenendo "mai unione". File: `useControlRoom.ts` (~1172-1192),
   `lib/righeCanale.ts` (segnale "id sconosciuto"). In alternativa realtime Supabase sulle 3
   tabelle dei trade.
2. **(M) Bot tennis in Control Room da 47337** e correzione del produttore: `tennis_bot_posizioni`
   oggi porta righe di armamento e, dal runner, finisce su 47332. Serve un topic delle posizioni/
   ordini dei bot tennis pubblicato dal processo giusto e sottoscritto in `useControlRoom.ts`
   (+ `lib/righeCanale.ts` per bot tennis). File: `Betfair/stream/tennis_live/tennis_db.py`,
   `tennis_runner.py`, `canale_bot.py`, `useControlRoom.ts`.
3. **(M) Schede proposte al ms (voci A-G)**: hook `usePrezzoAlMs`, EV/semaforo con
   `valutaAlPrezzo`, tolleranza come avvertimento, scheda Omega con `esitoUscitaAlPrezzo`, esito
   dell'approvazione. File in `STATO_RIPRESA.md` del delegato `agent-a5d6a648b59d268f2` righe 41-75.
4. **(S) Stato/modalita' dei bot dal push `*_stato`**: oggi Safe/Mike usano il push solo come
   orologio; usare il contenuto (come Omega, `useControlRoom.ts:1154-1160`) per modalita'/stato/
   interruttori. File: `useControlRoom.ts`.
5. **(S) Tennis in scheda partita dal canale**: `useTennisVivo` su 47332 `now` (partite seguite) o
   47336 `scan_tennis`, realtime come ripiego. File: `components/controlroom/useTennisVivo.ts`.
6. **(S) Runner e "Ordini reali" in push**: `hello`/battito sul canale 47331/47332 invece del poll
   30 s. File: `ControlRoom.tsx:970-1000`, `RigaOrdiniReali.tsx`, runner (hello gia' esistente).
7. **(M, decisione utente) Conflate dello scanner**: 1000 ms -> 0/100-200 ms su TUTTI i mercati
   costa banda/CPU (misura C5-F1 a 19,8 msg/s col conflate 1 s); alternativa: prezzi al tick dal
   runner (47331, conflate 0) per le partite con posizione. File: `Betfair/safe_strategy/stream.py:64`
   (o `sorgenteLadderAlMs` nelle schede, gia' previsto nella voce A).
8. **(L, piano F5-F8 approvato) Ordini dal canale**: accendere il motore a evento
   (`MOTORE_ORDINI_CANALE`) e la porta Safe (`SAFE_ORDINI_VIA_CANALE`) dopo F4 banco e giornata
   paper; poi F6 Omega, F7 Mike (REST -> comando + esiti dallo stream, chiude anche il buco esiti
   Mike), F8 Safe tennis su 47332. File: `AUDIT_STRADE_ORDINE_2026-09-24.md` par. 5.
9. **(M, strategia: decisione utente) Giro di Omega**: oggi 20-60 s; la sveglia sulle candidate e'
   stata tolta di proposito (B-2). Senza toccare la strategia si puo' solo portare la decisione
   all'utente con i numeri di letture DB.
10. **(M) Esiti parziali dal canale**: sequenza per ordine + snapshot (protocollo F3 gia' scritto
    nel motore) per smettere di aspettare il poll sui parziali. File: `esiti_ordini_canale.py`,
    `omega_service.py:3194`, `bot_service.py:738`.
11. **(S) Armamento bot tennis**: sveglia anche sul `bot_control_worker` del runner (oggi 3 s).
    File: `tennis_runner.py:1756`.
12. **(S) xhedge e scalper**: pubblicare `betfair_live_xhedge` sul canale 47331 (topic nuovo) e
    `scalper_activity`/punteggi dello scalper dal canale 47336. File: `xhedge_worker.py:118`,
    `scalper_session.py:763-917`.
13. **(S) Pagine fuori CR**: SeguiLive follows/pannelli a poll 3-60 s, LivePnl, Omega/Safe/Mike
    poll 15 s (hanno gia' l'overlay: e' la rete, va bene), MarketWatch follows.
14. **(S) Igiene**: commento stantio `ControlRoom.tsx:928-929`; `scanner_stato` non sottoscritto
    (lo stato scanner arriva dal realtime `safe_strategy_status`, `useControlRoom.ts:1073`).

---

## 4. COSA NON HO POTUTO VERIFICARE

- L'app viva: nessun processo avviato, nessuna pagina vista; cadenze e fonti sono dal CODICE,
  tranne le misure gia' in `CRONOSTORIA.md` (C5-F1 del 23/09) e nei referti citati.
- Che l'ambiente dei processi reali sia quello del `.env` + `main.js` (non ho letto variabili di
  sistema).
- Che `tennis_bot_posizioni` pubblicato dal runner finisca davvero su 47332: dedotto da
  `canale_bot._canale()` = canale del processo (`canale_bot.py:127-139`), non osservato.
- La latenza vera dal clic a `placeOrders` con `LIVE_ORDER_QUEUE_POLL_SEC=0.15` dall'app (le stime
  di `AUDIT_STRADE_ORDINE` assumono 1,0 s).
- Se lo scanner copre sempre i mercati CS/OU delle posizioni sullo stream o se alcuni vanno al poll
  REST di ripiego (dipende dal numero di mercati, `stream.py:18-21`).
- Non ho letto riga per riga `SchedaChiusura*.tsx`, `SchedaMike.tsx`, `PannelloBot.tsx`,
  `interruttori.ts` (coperti via grep).
