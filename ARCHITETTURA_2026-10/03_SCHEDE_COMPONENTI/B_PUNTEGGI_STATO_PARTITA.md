# SCHEDA B - PUNTEGGI E STATO DELLA PARTITA, CALCIO E TENNIS (prefisso `B-`)

Data: 08/10/2026. Autore: delegato Sonnet (piano di architettura). Solo documento, nessuna modifica al codice.

Perimetro (righe da `wc -l` sui file tracciati):
`Betfair/stream/scores/` 989 righe (`api_football.py` 89, `base.py` 57, `betfair_inplay.py` 198, `poller.py` 104,
`scan_feed.py` 540, `__init__.py` 1) · parte punteggi dello scanner `Betfair/safe_strategy/service.py` (poll IPS
`:1698-1905`, `apply_score_state` `:1780-1830`, `ScoreFeedWorker` `:3258-3320`) · tennis `Betfair/stream/tennis_scalper/tennis_score.py` 265 ·
flusso dei prezzi `Betfair/stream/flusso_prezzi.py` 345 · lavoratori di punteggio dei runner
(`Betfair/stream/runner.py:344-465`, `Betfair/stream/tennis_live/tennis_runner.py:1611-1694`) · colla dei bot
(Omega `omega_service.py:44-75,895-960,2428-2455,8905-8935`; Mike `mike/feed.py:76-176,425-475`; Safe `safe_strategy/exits.py:401-455`,
`bot_service.py:8502-8514`; scalper `scalper_session.py:1734-1925`) · `atlante_v4.py` 848 (solo `tempo_da_stato_ips` `:550-593`
appartiene a B; il resto e' modello, vedi sez. 1.9) · `curator.py` 186 (offline, sez. 1.9) · `api_client.py` 137 e `api_quota.py` 345
(fornitore esterno, sez. 1.8).

Fonti gia' pronte e usate (non rifatte): `00_INVENTARIO.md` (§ canali righe 1611-1619), `07_MISURE_OGGI.md` (righe 53, 212-218),
`D_RUNTIME_BOT_CONTRATTO.md` (§1.5 righe 111-119, D-017 riga 215, `Quadro` riga 365), `A_CONNESSIONE_BETFAIR.md`,
`G_DATI_E_ALGORITMI_DEL_CLOUD.md`, `strumenti/inventario/uscite/s04_dettaglio_copie.tsv:584-590`.

---

## 1. OGGI

### 1.1 Risposta in una pagina (le domande del compito)

| Domanda | Risposta letta dal codice |
|---|---|
| Quante fonti di punteggio **a monte** | **2 fornitori**: (a) IPS Betfair, endpoint non ufficiale (`https://ips.betfair.it/inplayservice/v1.1/scoresAndBroadcast`, `service.py:196`; stessa famiglia di `betfairlightweight.in_play_service.get_scores/get_event_timeline(s)`); (b) API-Football `/fixtures?id=` (`api_football.py:80`), solo ripiego del calcio. |
| Quanti **punti di chiamata** a IPS | **6**: scanner batch `service.py:1706-1731` (chunk 50, ogni 2 s), scanner timeline batch `:1893` (30 s) e "finestra del fischio" `:1846`, runner calcio diretto `betfair_inplay.py:164,187` (ripiego), runner tennis diretto `tennis_runner.py:1645` (ripiego), `tennis_score.py:193,240` (pollatori dei vecchi `run_tennis_scalper.py:33` / `run_tennis_pro.py:27`), registratore campagne `record_multi.py:215`. |
| Quanti **relay** (copie dello stesso stato) | **5**: riga `safe_strategy_scan` (DB, `scan_feed.py:49`), canale locale 47336 `scan_calcio/scan_tennis` (`00_INVENTARIO.md:1611`), riga `live_now` (`db.py:322-348`, calcio), riga `tennis_live_now` (`tennis_db.py:266-292`), canale 47332 topic `now` (`db.py:344`, `tennis_db.py:289-291`). Piu' i file `.scores.jsonl`/`.score.jsonl` delle registrazioni (`runner.py:420-430`, `tennis_runner.py:1673-1680`). |
| Come arriva lo stato ai bot | **Non c'e' un canale unico.** Mike, Omega, Safe: riga dello scanner (canale 47336, ripiego SELECT `safe_strategy_scan`). Omega ha anche il ripiego `live_now` (`omega_service.py:8921`) e il ripiego a orologio (`omega_engine.py:932`). Scalper calcio: SELECT di `live_now` da 3 thread osservatori (`scalper_session.py:1756,1891,1911`). Bot tennis del runner: assegnazione in memoria `strat.score = ts` (`tennis_runner.py:1656-1664`). Safe tennis: parser sul `score_raw` della riga scanner (`tennis_opportunity.py:45`). UI: canale 47336 e 47332 + Realtime su `live_now`/`tennis_live_now`. |
| Ritardo | Costanti di codice (non misurato, vedi sez. 7): IPS 2-3 s dopo il fatto (`scan_feed.py:64-67`) + poll scanner 2 s (`service.py:132`) + freno di scrittura 2,5 s (`service.py:159`) + cache SELECT 1 s (`scan_feed.py:69`) = **fino a ~8,6 s** sul percorso Mike/Omega/Safe; **+5 s** worker runner calcio (`config_stream.py:32`) e **+15-20 s** del watcher dello scalper (`scalper_session.py:1741,1905,1925`): **fino a ~29-34 s** per lo scalper calcio. Tennis: +2 s del worker (`tennis_runner.py:111`) = fino a ~10,6 s. |
| Regola cond. 11 (prezzo fermo vs punteggio che si aggiorna) | Implementata **UNA volta** nel nucleo `flusso_prezzi.py` (345 righe) piu' **4 involucri** + **6 regole di freschezza gemelle con soglie diverse** (sez. 3.2). Scalper e tennis non importano `flusso_prezzi` (`git grep` su `stream/scalper`, `stream/tennis_live`: 0 righe): usano lo stream flumine del proprio processo. |
| Ogni bot ricalcola minuto/fase? | **Si'**: almeno 9 punti (sez. 3.3). `_ko_epoch_ms` ha 7 definizioni (`s04_dettaglio_copie.tsv:584-590`): **4 in produzione** (`scalper_bot.py:788`, `sniper_bot.py:295`, `media_under_bot.py:1020`, `tennis_scalper_bot.py:802`) e 3 nel laboratorio (`laboratorio/scalper_lab/...`). |
| Chiamate di rete nel percorso critico | Si': SELECT `safe_strategy_scan` (cache 1 s), upsert Supabase `live_now`/`tennis_live_now` **nello stesso ciclo** del punteggio (`runner.py:376`, `tennis_runner.py:1688`), HTTP diretto a IPS e ad API-Football come ripiego, SELECT `live_now` dai watcher dello scalper. Dettaglio sez. 1.6. |

### 1.2 Catena del dato (calcio)

```
campo -> IPS Betfair (+2-3 s)
   -> Scanner Safe: ScoreFeedWorker (thread) poll_scores ogni 2 s, chunk 50, pausa 0,1 s fra lotti  [service.py:132,134,175,3258-3320]
        apply_score_state: payload.score_raw (stato IPS grezzo senza campi al secondo) + minute/score/red  [service.py:1780-1830]
        tick 0,5 s pubblica la riga se cambiata, freno 2,5 s, i cambi di punteggio FUORI freno  [service.py:155,159,2479-2480,2686]
   -> riga safe_strategy_scan (DB)  E  canale 47336 `scan_calcio`  (battito `scanner_stato` ogni 10 s [service.py:160])
   -> ScanRowCache.rows_for (SELECT ogni 1 s per processo; con PUNTEGGI_CANALE=1 fusione col canale e SELECT ogni 10 s)  [scan_feed.py:284-322]
        -> runner calcio: ScorePoller(ScanFeedScoreProvider(BetfairInPlayProvider), ApiFootballProvider)  [runner.py:2111-2115]
             score_worker ogni 5 s  -> db.update_live_now (SEMPRE, non write-on-change) + .scores.jsonl (write-on-change)  [runner.py:344-405]
        -> Omega: _feed_row/score_from_payload (feed) poi db.read_live_now poi orologio  [omega_service.py:8905-8932]
        -> Mike: ClientScan (canale) + feed.py  [mike/service.py:7072]
        -> Safe: bot_service legge payload (canale/DB)  [bot_service.py:3214,3409]
        -> Scalper: thread osservatori leggono live_now ogni 15-20 s  [scalper_session.py:1756,1891,1911]
```

### 1.3 Catena del dato (tennis)

Scanner come sopra (stesso `apply_score_state`, ramo `parse_tennis_scores`, `service.py:1798-1812`). Il runner tennis ha UN lavoratore
`score_and_now_worker` ogni `TENNIS_SCORE_POLL_SEC`=2,0 s (`tennis_runner.py:111,3355`): per ogni evento legge `feed.get_raw_state` (riga
scanner) o, se assente/stantia, **chiama `get_scores` diretto** (`:1636-1650`), parsa con `parse_tennis_scores`, **assegna `strat.score` e
`strat.point_pressure` ai bot ospitati** (`:1656-1664`), aggiorna il deque punto-per-punto (`:1666-1671`), scrive il tee `.score.jsonl` se
`record=true` (`:1675-1680`) e **sempre** `tennis_db.upsert_tennis_now` (`:1688`, anche canale `now` `tennis_db.py:289-291`).

### 1.4 Tabelle del DB e frequenze

| Tabella | Scritta da (`file:riga`) | Letta da | Frequenza |
|---|---|---|---|
| `safe_strategy_scan` | scanner `service.py` (riga per evento, tick 0,5 s, freno 2,5 s) | `scan_feed.py:412-428`, `board_worker.py:188-193`, `riserva_prezzi.py:149-150`, Mike/Omega/Safe/UI | POST scanner **65,4/min** (`07_MISURE_OGGI.md:215`); GET mike-service 10,4/min (`:214`) |
| `safe_strategy_status` | `service.py` (battito 10 s, `:160`) | `scan_feed.py:403-410` | POST 4,7/min (`07_MISURE_OGGI.md:215`) |
| `live_now` | `db.py:322-348` da `runner.py:376` | Omega `omega_db.py:586-602`; scalper `scalper_session.py:1756,1891,1911`; `live_order_worker.py:1105` (contesto ordine); UI Realtime | 1 upsert ogni 5 s **per evento seguito** (12/min/evento) + chiusure (`runner.py:794`) |
| `tennis_live_now` | `tennis_db.py:266-292` da `tennis_runner.py:1688` | UI `useTennisVivo.ts`, `SchedaPartita.tsx:112-240`, ponte (`modo_ordini.py:259`) | 1 upsert ogni 2 s **per evento** (30/min/evento) |
| `live_score_timeline` | `db.py:634-635` (delete + insert) da `uploader.py:136-150` a fine partita | Replay UI | 1 volta per partita |
| `live_market_snapshots` | `db.py:629-631` da `curator.py` via `uploader.py` | Replay UI | 1 volta per partita |
| `api_call_log` | `api_client.py` a ogni tentativo (docstring `:30-37`) | `api_quota.py:127-186` | solo quando il ripiego API-Football scatta |

Frequenze di `live_now` e `tennis_live_now` **non misurate oggi**: nella sessione misurata i runner non seguivano eventi
(`07_MISURE_OGGI.md:218`: runner-tennis 28,2 richieste/min, tutte `tennis_live_follow`). Le cifre della tabella derivano dal periodo di
codice (5 s, 2 s) e dalla scrittura incondizionata; strumento che le misura: `strumenti/misure/` con una sessione a eventi in corso.

### 1.5 Canali locali, processi, orologi, thread

- Canali: 47336 (scanner; `scan_calcio`, `scan_tennis`, `scanner_stato`), 47332 (runner tennis topic `now`), `PUNTEGGI_CANALE` (interruttore,
  default SPENTO, `scan_feed.py:90-107`; 47337 e' il ponte armamento, non punteggi). Dipendenze: `inventario 1611-1619`.
- Processi: scanner (`safe-strategy-service`, `00_INVENTARIO.md:1538`) e' l'UNICO che interroga IPS in batch; runner calcio, runner tennis, Omega,
  Mike, Safe bot sono lettori.
- Thread: `safe-scan-scores` (`service.py:3262`), `score_worker` e `score_and_now_worker` (flumine worker), 3 watcher dello scalper
  (`scalper_session.py:1741,1890,1906`), thread dello scanner Atlante in `hazard_atlas_sync` (`atlante_a_domanda.py:1-14`).
- Orologi: `time.monotonic` nel poller (`poller.py:31`), `updated_at` ISO del DB (`scan_feed.py:178-189,440-444`), `time.time()` negli osservatori
  dello scalper (`scalper_session.py:1743`), `publish_time` di Betfair per i book. Il punteggio ha **solo** `updated_at` (ora di scrittura dello
  scanner), non l'ora dell'evento: `ScoreSnapshot.ts` e' `_now_iso()` locale (`betfair_inplay.py:23,110`).
- Stato condiviso: `shared_cache()` per processo (`scan_feed.py:430-437`), `session.pollers`/`_last_score_sig`/`_seen_events` nel runner calcio
  (`runner.py:185-204`), `session.last_score`/`points_deque` nel runner tennis.

### 1.6 Chiamate di rete nel percorso critico

1. `ScanFeedScoreProvider.get_score` -> `ScanRowCache.rows_for` -> SELECT Supabase (`scan_feed.py:296-309`), dentro `score_worker` (thread flumine). Con
   `PUNTEGGI_CANALE` spento: 1 SELECT/s per processo (non per evento: `rows_for` unisce gli eventi richiesti).
2. Riga assente o stantia: **HTTP diretto a IPS dentro lo stesso worker** (`scan_feed.py:524-529`; `tennis_runner.py:1645`).
3. Ripiego API-Football: `poller.py:81-82` prova il ripiego **a ogni tick anche prima che il circuito si apra** (soglia 3 fallimenti, `poller.py:29,65`);
   `ApiFootballProvider.get_score` e' una richiesta HTTP sincrona con retry/backoff (`api_client.py:33-50`) e scrittura su `api_call_log`; nessun
   controllo di quota (`api_football.py:77-86`; `api_quota` e' importato solo da `league_orchestrator.py:32` e `seasons_catchup.py:66`).
4. `db.update_live_now` (upsert Supabase con retry, `db.py:348`) dentro il ciclo `for event_id` di `score_worker` (`runner.py:345`): N eventi = N
   upsert **in serie** nello stesso thread; idem tennis (`tennis_runner.py:1688`, con `continue` su errore).
5. Scalper: 3 SELECT `live_now` periodiche da thread propri (nessuna rete nel callback del book).

### 1.7 Cos'e' dentro `scores/` (responsabilita' reali)

- `base.py`: contratto `ScoreSnapshot` (21 campi, immutabile) e `ScoreProvider` (Protocol: `get_score`, `healthcheck`). **Esiste gia'** il
  contratto di sostituzione dei provider; ma e' solo calcio e non porta fase/tempo/rossi per fase.
- `betfair_inplay.py`: `parse_score_dict` (calcio, `:50-126`), `normalize_timeline` (`:129-151`), provider diretto.
- `api_football.py`: `parse_fixture_response` (`:34-54`) + provider.
- `poller.py`: circuito primario/ripiego per evento (`ScorePoller`).
- `scan_feed.py`: cache per processo, fusione canale+DB, freschezza (`fresh_payload`), provider "dal feed".

### 1.8 Fornitore esterno API-Football e quota

Nel percorso **live** API-Football e' chiamato **solo** da `ApiFootballProvider.get_score` (`api_football.py:77-86`), costruito per ogni evento a
`runner.py:2113` con `fixture_id` dal catalogo (`runner.py:2099`); `fixture_id` assente = nessuna chiamata (`api_football.py:78`). Frequenza = quella del
`score_worker` (5 s per evento) **per tutto il tempo in cui il circuito e' aperto** (primario muto 3 volte di fila; ritenta il primario ogni 120 s,
`poller.py:30,85`). `api_quota.py` (345 righe: `GestoreQuota`, `leggi_status_api`, `conta_log_oggi`) serve solo ai lavori in batch dei dati
(`G_DATI_E_ALGORITMI_DEL_CLOUD.md`); il ripiego live non lo consulta. Il tennis non ha ripiego esterno: senza IPS `ts=None` e la gap-guard resta invariata
(`tennis_runner.py:1659-1661`, fail-safe).

### 1.9 Atlante, curatore, timeline

- `atlante_v4.py` (848 righe) e' un **modello** (hazard per lega, `consulta_atlante_v4` `:676`, forza squadre `:225-300`): lo costruiscono
  `genera_atlante.py` (1.289) e `atlante_a_domanda.py` (532) dentro il thread `hazard_atlas_sync` (213) dello scanner; lo consultano Mike
  (`dossier.py:324-339`), Safe (`opportunity.py:656-694`) e il motore (`engine.py:52,796`). Dallo stato partita prende **tempo e minuto**
  (`tempo_da_stato_ips` `:550-586`, `tempo_da_payload` `:588-593`): questo pezzo e' B, il resto e' dati/modelli (scheda G e schede dei bot).
- `curator.py` (186) e `uploader.py` (274): **offline**, a fine partita, trasformano `.raw.jsonl` + `.scores.jsonl` + `.timeline.jsonl` in
  `live_market_snapshots` e `live_score_timeline` (`uploader.py:136-150`). `_minute_at` (`curator.py:82-96`) ricostruisce il minuto a un istante con la
  timeline: e' una quarta stima del minuto, usata solo per le righe del replay. Appartiene alla registrazione/replay; qui conta perche' deve leggere
  lo stesso `StatoPartita`.
- Timeline eventi dal vivo: `normalize_timeline` (`betfair_inplay.py:129`), cattura per update_id nel runner (`runner.py:422-460`, throttle 30 s
  `LIVE_TIMELINE_POLL_SEC`, `:419`) e nello scanner (30 s `_TIMELINE_PERIOD_SEC` `service.py:136`; "finestra del fischio" 300 s `:150`).

### 1.10 Tennis: stato game/set/servizio

`TennisScore` (`tennis_score.py:49-61`): `sets`, `games`, `point_home/away`, `server`, nomi, `raw`; `key()` (`:63`), `pressures()` (`:75-111`:
break point / set point / game point) e `point_pressure` (`:113`). `parse_tennis_scores` (`:131`). Nel nome del file il tennis dipende dal
pacchetto `tennis_scalper` (il vecchio bot): lo importano `safe_strategy/service.py:64`, `tennis_opportunity.py:45`, `tennis_runner.py:77`,
`tennis_replay/convertitore.py:45`, `record_multi.py:36`, `tennis_pro_bot.py:63`, `replay_bot.py:746`.

---

## 2. FUNZIONALITA' (tutte, lette riga per riga)

UI = visibile nel pannello indicato. P = parametro editabile.

| ID | Cosa fa | `file:riga` | UI / P |
|---|---|---|---|
| B-001 | `ScoreSnapshot`: fotografia immutabile (minuto, punteggio, stato, corner, cartellini, booking, stats, payload grezzo) | `scores/base.py:13-42` | - |
| B-002 | `ScoreProvider` Protocol (sostituibilita' dei provider) | `base.py:45-57` | - |
| B-003 | Parser IPS calcio con minuto 0 valido (`timeElapsed`/`elapsedRegularTime`/`timeElapsedSeconds`) | `betfair_inplay.py:50-62` | - |
| B-004 | Punteggio, forma alternativa `fullTime`/`current` | `betfair_inplay.py:64-78` | - |
| B-005 | Statistiche live: corner (anche per tempo), gialli, rossi, booking points, `elapsedAddedTime`, nomi squadre | `betfair_inplay.py:80-106` | UI: schede partita |
| B-006 | `normalize_timeline` (gol/cartellini/kickoff col minuto) pura, usata dallo scanner e dal runner | `betfair_inplay.py:129-151` | UI: elenco eventi in `live_now.state.events` |
| B-007 | Provider IPS diretto: `get_score`, `get_timeline`, `healthcheck` | `betfair_inplay.py:154-198` | - |
| B-008 | Provider API-Football (`/fixtures?id=`), `set_fixture_id` | `api_football.py:57-89` | - |
| B-009 | Parser risposta API-Football in `ScoreSnapshot` | `api_football.py:34-54` | - |
| B-010 | Circuito primario/ripiego (soglia 3, riprova primario 120 s, `fallback_count`, `current_source`) | `poller.py:24-104` | P: `FALLBACK_THRESHOLD`, `FALLBACK_RETRY_PRIMARY_SEC` (`config_stream.py`) |
| B-011 | Cache per processo delle righe scanner, TTL 1 s, un solo SELECT per tutti gli eventi, prune 120 s | `scan_feed.py:192-322,430-437` | - |
| B-012 | Fusione riga canale + riga DB (`piu_recente`), rilettura DB ogni 10 s se il canale copre tutto | `scan_feed.py:246-282,385-400` | P: env `PUNTEGGI_CANALE` |
| B-013 | Eta' dello scanner (battito) con SELECT o canale | `scan_feed.py:324-369` | - |
| B-014 | `fresh_payload`: riga fresca (15 s) o scanner vivo (30 s) con tetto 180 s | `scan_feed.py:447-475` | P: env `SCAN_FEED_HARD_MAX_AGE_SEC` (`:52-63`) |
| B-015 | `ScanFeedScoreProvider`: `get_raw_state`, `get_score`, `get_timeline` con ripiego diretto, contatori `feed_hits`/`direct_calls` | `scan_feed.py:478-540` | - |
| B-016 | Eta' onesta del punteggio = eta' riga + 3 s di ritardo IPS | `scan_feed.py:506-512,64-67` | UI (eta' del dato) |
| B-017 | Poll IPS in batch `scoresAndBroadcast` (punteggi + disponibilita' media), chunk 50, ripiego `get_scores` | `service.py:1698-1772` | - |
| B-018 | `apply_score_state`: stato grezzo -> evento (calcio minuto/punteggio/rossi; tennis set/game), aggiornamento atomico | `service.py:1780-1830` | - |
| B-019 | Timeline calcio in batch ogni 30 s | `service.py:1882-1905,3099` | - |
| B-020 | Finestra del fischio (300 s): timeline al posto dei punteggi per chi non ha ancora punteggio | `service.py:138-150,1740-1750,1830-1870` | - |
| B-021 | Sveglia dallo stream (gol/in gioco) del giro punteggi, pavimento 0,5 s | `service.py:155,3277-3320` | - |
| B-022 | `ScoreFeedWorker` thread + battito dello scanner ogni 10 s | `service.py:3258-3320,160` | UI: stato scanner |
| B-023 | `strip_volatile_state` (toglie i campi al secondo dal `score_raw`) | `scanner.py:637-641` | - |
| B-024 | `score_worker` calcio: poll, `live_now`, tee `.scores.jsonl` write-on-change, segnali | `runner.py:344-413` | UI: tabellone live, pannello segnali |
| B-025 | Cattura timeline Betfair per `update_id` su `.timeline.jsonl` + ultimi 8 eventi in `live_now.state.events` | `runner.py:416-460` | UI: eventi |
| B-026 | Chiusura `live_now` a fine evento e pulizia orfane all'avvio | `runner.py:790-835,877-890`; `db.py:351,500` | UI |
| B-027 | `update_live_now` con push canale `now` prima del cloud | `db.py:322-348` | UI: Realtime/canale |
| B-028 | Upload a fine partita: `live_score_timeline` + `live_market_snapshots` | `uploader.py:120-160`; `db.py:629-635` | UI: Replay |
| B-029 | Curatore write-on-change con throttle e cambio di stato mercato; `_minute_at` | `curator.py:48-130,82-96` | - |
| B-030 | `TennisScore` e chiave di stato per rilevare i cambi punto | `tennis_score.py:49-66` | - |
| B-031 | Pressioni: break point, set point, game point; `point_pressure` | `tennis_score.py:75-121` | UI: stato tennis |
| B-032 | `parse_tennis_scores` (server, game/set, nomi, `raw`) | `tennis_score.py:123-176` | - |
| B-033 | Pollatori tennis legacy (`tennis_score_poll`, `_full` con log `.jsonl`) | `tennis_score.py:178-265` | - (bot vecchi `run_tennis_*`) |
| B-034 | `score_and_now_worker` tennis: feed o diretto, assegna `strat.score`/`point_pressure`, deque punti, tee, `upsert_tennis_now`, chiusi non riscritti | `tennis_runner.py:1611-1694` | UI tennis |
| B-035 | `upsert_tennis_now` + canale `now`; `chiudi_tennis_now` | `tennis_db.py:266-325` | UI `useTennisVivo.ts` |
| B-036 | Flusso dei prezzi: valuta riga/stato/mercati, motivi, soglie in-play (calcio 45 s, tennis 25 s), pre 125 s, socket 15 s | `flusso_prezzi.py:84-240` | UI (motivo testuale, `_TESTI` `:98-110`) |
| B-037 | Avviso "scanner vecchio senza flusso", promemoria critico ogni 60 s, ripiego REST dichiarato | `flusso_prezzi.py:240-345` | UI (avvisi) |
| B-038 | Involucro Mike del flusso (linee O/U 3,5/4,5, testo per linea) | `mike/feed.py:148-176,176-250` | UI Mike |
| B-039 | Involucro Safe del flusso + `feed_is_fresh` (20 s / 120 s / 45 s) | `exits.py:231-245,401-455` | - |
| B-040 | Involucro Omega del flusso (`_flusso_feed`, `_flusso_feed_ht`, MATCH_ODDS + Correct Score + HT) | `omega_service.py:959-1010` | UI Omega |
| B-041 | Freschezza Mike: `feed_fresh` (45 s, scanner 75 s, tetto 180 s), `order_fresh` (20 s / 30 s) | `mike/feed.py:435-478`; `mike/config.py:95,101,115-116` | **P** Mike (`feed_max_age_s`, `scanner_alive_max_s`, `order_max_age_s`, `order_scanner_max_s`) |
| B-042 | Freschezza Omega: `FEED_MAX_AGE_S` 15, decisione 25, green-up 90, cash-out 20; `_is_fresh` 180 s | `omega_service.py:48,62-81,85-99,1080-1110` | UI cash-out spento a 20 s (`MatchTradesTable.FEED_STALE_S`, citato `:96`) |
| B-043 | Punteggio Omega: `_feed_row` -> `score_from_payload` -> `read_live_now` -> orologio | `omega_service.py:900-935,8905-8932,2428-2455`; `omega_db.py:586-602`; `omega_engine.py:932-940` | **P** Omega `entry_window_source` ('score'/'clock', `omega_config.py:34`) |
| B-044 | (vedi B-045: voce unica) | - | - |
| B-045 | Fase da stato IPS (`tempo_da_stato_ips`, `_fase_da_scan` Safe, `mission_phase` Omega) | `atlante_v4.py:550-593`; `engine.py:789-796`; `omega_service.py:~1000-1010` | - |
| B-046 | Osservatori dello scalper: intervallo (HT start/end), linea sniper, punteggio/minuto theta | `scalper_session.py:1734-1925` | - |
| B-047 | Orario d'inizio `_ko_epoch_ms` da `market_definition` (4 copie in produzione) | vedi sez. 3.3 | - |
| B-048 | Minuto reale per telemetria sniper/theta | `sniper_bot.py:632-640`; `theta_bot.py:498-545` | - |
| B-049 | Tee punteggio tennis `.score.jsonl` / calcio `.scores.jsonl` per le registrazioni | `tennis_recorder.py:221`; `runner.py:405-413` | - |
| B-050 | Parita' paper/live del punteggio: stesso feed, nessuna ramificazione per modo | `runner.py:2111`; `tennis_runner.py:1611` | - |
| B-051 | Riserva dei prezzi dalla stessa cache (ripiego REST dichiarato) | `riserva_prezzi.py:148-155` | UI (fonte prezzi) |
| B-052 | Tabellone mercati leggono la riga scanner con la stessa freschezza | `board_worker.py:188-193` | UI |
| B-053 | Quota API-Football (batch dei dati, non live) | `api_quota.py:50-345` | - (azioni GitHub) |


---

## 3. DIFETTI STRUTTURALI

### 3.1 Non c'e' UN servizio di stato partita
L'unico poll (scanner) e' unico; il resto sono **cinque relay** (DB, canale 47336, `live_now`, `tennis_live_now`, canale 47332) e **tre
percorsi di ripiego a monte**: IPS diretto nel runner calcio (`betfair_inplay.py:164`), IPS diretto nel runner tennis (`tennis_runner.py:1645`),
API-Football (`api_football.py:80`). Lo stato vive in memoria di 5 processi, cache per processo (`scan_feed.py:430`) piu' dizionari di sessione
(`runner.py:185-204`). Il calcio ha `ScoreSnapshot`; il tennis ha `TennisScore` in un altro pacchetto (`tennis_scalper`); i due non condividono tipo.

### 3.2 La regola cond. 11 e la freschezza: 1 nucleo + 4 involucri + 6 gemelle con soglie divergenti

Nucleo: `flusso_prezzi.valuta` (`flusso_prezzi.py:218`). Involucri: Mike `feed.py:148`, Safe `exits.py:401`, Omega `omega_service.py:959-1010`,
`riserva_prezzi.py` (`import` `:35`). Regole di **eta' della riga** (ognuna con soglie sue):

| Copia | Soglia riga | Soglia scanner vivo | Tetto duro |
|---|---|---|---|
| `scan_feed.fresh_payload` `:447` | 15 s (`DEFAULT_MAX_AGE_SEC` `:43`) | 30 s (`:39`) | 180 s (`:63`) |
| Mike `feed_fresh` `:435` | 45 s (`config.py:95`) | 75 s (`config.py:101`) | 180 s (importa `scan_feed.HARD_MAX_AGE_SEC`, `feed.py:430`) |
| Mike `order_fresh` `:458` | 20 s (`config.py:115`) | 30 s (`config.py:116`) | 180 s |
| Safe `feed_is_fresh` `exits.py:424` | 20 s (`:231`) | 45 s (`:245`) | 120 s (`:234`) |
| Omega `_feed_row` `:913` + costanti | 15 s (`:85`), decisione 25 s (`:89`), green-up 90 s (`:91`), cash-out 20 s (`:99`) | usa `scanner_age_sec` di `scan_feed` | 25/20 s di decisione |
| Omega `_is_fresh` `:62` (punteggio) | 180 s (`:48`) e **timestamp assente = fresco** (`:64-65`) | - | - |
| Safe `_row_is_fresh` `bot_service.py:8502` | rimanda a `feed_is_fresh` | - | - |

Sono soglie **diverse** per lo stesso concetto ("quanto e' vecchia la riga dello scanner"); i commenti dichiarano che sono state tarate caso per caso
(es. `mike/feed.py:458-478`, `exits.py:431-440`). Qui non si propone di cambiarle (condizione 5 del brief comune): si propone di **ospitarle in UN
posto** con i valori attuali per bot (sez. 4). Il tennis e lo scalper non applicano cond. 11 tramite questo nucleo: usano lo stream del proprio
processo (`D_RUNTIME_BOT_CONTRATTO.md:118-119`) e la soglia in-play del tennis (25 s) vive in `flusso_prezzi.py:92`.

### 3.3 Il minuto e la fase vengono ricalcolati in 9 punti

1. `scan_feed`/`parse_score_dict` `betfair_inplay.py:54-61` (minuto da 3 chiavi IPS);
2. `omega_engine.minute_from_clock` `:932-940` (orologio da `marketStartTime`; `matches_remaining` `:2455+` lo usa);
3. `omega_service.estimate_minute` `:2428-2455`;
4. `atlante_v4.tempo_da_stato_ips` `:550-586` e `_fase` `:596`;
5. Safe `engine._fase_da_scan` `:789-796` (usa 4);
6. Omega `_ht_ancora_in_gioco` + `E.mission_phase` (`omega_service.py:~1000-1010`);
7. `sniper_bot._minute` `:632-640`, `theta_bot._match_minute` `:535-545`;
8. osservatori scalper (HT: finestra 44'-70' dal KO, minuto fermo 300 s, `scalper_session.py:1741-1760`);
9. `curator._minute_at` `:82-96`.

`_ko_epoch_ms` (calcolo del KO in ms da `market_definition.market_time`): `scalper_bot.py:788-818` (31 righe) e
`tennis_scalper_bot.py:802-832` sono **identiche** (stesso corpo, stesso docstring); `sniper_bot.py:295-310` e `media_under_bot.py:1020-1032`
hanno lo stesso algoritmo con cache diversa (per market_id / un solo valore). Fonte dei conteggi: `s04_dettaglio_copie.tsv:584-590`
(7 definizioni = 4 in `Betfair/stream/` + 3 in `laboratorio/scalper_lab/`). Righe duplicate in produzione: 31+31+16+13 = **91**.

### 3.4 Scrittura incondizionata e rete nel ciclo
`update_live_now` e `upsert_tennis_now` scrivono a ogni giro anche se nulla e' cambiato (`runner.py:376`; `tennis_runner.py:1688`), mentre lo scanner
a monte e' write-on-change (`service.py:2686`). Il "write-on-change" del runner calcio vale solo per il file `.scores.jsonl` (`runner.py:384-413`).
Upsert sincroni in serie nel worker (sez. 1.6 punto 4).

### 3.5 Il punteggio dello scalper e' il piu' vecchio
Passa da due relay (scanner -> runner -> `live_now`) e poi da un SELECT periodico del proprio thread (15-20 s) (`scalper_session.py:1741,1756,1905,1925`).
Il resto dei bot legge la riga scanner. Il numero e' un tetto da costanti, non misurato.

### 3.6 Documentazione e costanti stantie
Il docstring di `scan_feed.py:5-7` dice chunk da 20 ogni 3 s; il codice ha chunk 50 ogni 2 s (`service.py:132,175`; commento `service.py:123-131`).
`IPS_SCORE_LAG_SEC=3,0` e' un valore unico per "2-3 s" (`scan_feed.py:67`). `scan_feed.py:5-17` cita "~231 chiamate/min di cui l'84%
ridondanti" (audit 09/09, non rimisurato oggi).

### 3.7 `ScoreSnapshot.source` non dice la verita'
Anche quando la riga arriva dallo scanner `parse_score_dict` scrive `source="betfair"` (`betfair_inplay.py:111`) e `live_now.score_source`
(`runner.py:378`) non distingue "feed", "diretto" e "api_football" a monte del poller.

### 3.8 Il ripiego di API-Football parte prima del circuito
`poller.py:81-82`: dopo UN solo fallimento del primario si chiama gia' API-Football; nessun controllo di quota nel percorso live.

### 3.9 Tennis in un pacchetto sbagliato
`tennis_score.py` sta in `tennis_scalper/` (bot legacy) ma serve scanner, runner, replay, Safe (7 importatori, sez. 1.10).

### 3.10 `_is_fresh(None)` = fresco
`omega_service.py:64-65`: un `updated_at` mancante rende il dato "fresco", con tetto 180 s sul resto (`:48`). E' una scelta dichiarata ("best-effort"),
ma e' piu' permissiva delle altre cinque regole.

Conteggi: importatori di `scores.*` in produzione 13 file (`git grep -n "stream.scores"`); chiamate `in_play_service` in produzione 6 punti (`git grep`, sez. 1.1).

---

## 4. DOMANI

### 4.1 Struttura
`Betfair/nucleo/stato_partita/` (UNA cartella, UN contratto, UN `COSA_FA.md`):
- `contratto.py` - `StatoPartita` (sotto), `Fonte`, `Eta`;
- `servizio.py` - UN servizio per sport (`StatoCalcio`, `StatoTennis`): tiene lo stato in memoria, applica la freschezza, pubblica sul canale;
- `adattatori/ips.py` (parser + poll batch + timeline), `adattatori/api_football.py`, `adattatori/registrazione.py` (sidecar `.scores.jsonl`/`.score.jsonl`
  per banco e replay), `adattatori/canale.py` (lettore del canale 47336 per i processi lettori);
- `freschezza.py` - UNA funzione con la tabella dei **valori attuali per bot** (identici a quelli di oggi, sez. 3.2);
- `COSA_FA.md`, `test_contratto.py`.

### 4.2 Contratto proposto (allineato a `Quadro` di `D_RUNTIME_BOT_CONTRATTO.md:365`, che lo contiene)

```python
Sport = Literal["calcio", "tennis"]
Fase  = Literal["pre", "1t", "intervallo", "2t", "supplementari", "finita", "sconosciuta"]

@dataclass(frozen=True)
class Eta:                                    # le tre eta' che oggi si confondono
    riga_s: float | None                      # da quanto la riga e' stata (ri)scritta
    punteggio_s: float | None                 # riga + ritardo IPS (scan_feed.py:506)
    scanner_s: float | None                   # battito dello scanner

@dataclass(frozen=True)
class StatoPartita:
    event_id: str; sport: Sport
    in_gioco: bool; fase: Fase
    minuto: int | None; tempo: int | None     # tempo = 1/2 (atlante_v4.py:550)
    gol: tuple[int, int] | None; rossi: tuple[int, int] | None
    corner: tuple[int, int] | None; gialli: tuple[int, int] | None
    set_game: TennisSet | None                # sets, games, punto, servizio, break/set point
    fonte: Literal["ips_scanner", "ips_diretto", "api_football", "registrazione"]
    eta: Eta
    prezzi_vivi: Esito                        # flusso_prezzi.Esito, cond. 11 NON separabile dallo stato
    grezzo: Mapping[str, Any]                 # score_raw invariato (audit)

class StatoPartitaService(Protocol):
    def stato(self, event_id: str) -> StatoPartita | None: ...
    def segui(self, event_ids: Iterable[str]) -> None: ...
    def iscrivi(self, cb: Callable[[StatoPartita], None]) -> Callable[[], None]: ...   # sveglia, niente SELECT
class FonteStato(Protocol):                   # adattatore sostituibile (oggi ScoreProvider, base.py:46)
    nome: str
    def leggi(self, event_ids: Sequence[str]) -> Mapping[str, Mapping[str, Any]]: ...
```
Eventi esposti: `StatoCambiato(event_id, prima, dopo)`, `GolSegnato`, `FaseCambiata`, `FlussoInterrotto/Ripreso` (la cond. 11 diventa un
evento, non una funzione in 4 involucri). Eventi consumati: `BookRicevuto` (per il flusso prezzi, dal nucleo Betfair A).

### 4.3 Dove vive ogni funzionalita'
B-001/002 -> `contratto.py`; B-003..007, B-017..023 -> `adattatori/ips.py`; B-008/009/053 -> `adattatori/api_football.py` (la quota resta in
`dati/` come lavoro in batch); B-010 -> `servizio.py` (circuito, con regola "ripiego dopo soglia" invariata); B-011..016 -> `servizio.py` + `canale.py`;
B-024..027, B-034/035 -> `servizio.py` (pubblica `live_now`/`tennis_live_now` **da qui**, write-on-change, fuori dal worker del runner); B-028/029 -> registrazione
(`registrazione/`), che legge `StatoPartita`; B-030..033 -> `adattatori/ips_tennis.py` (+ `StatoTennis`); B-036..043, B-051 -> `freschezza.py` + `flusso.py`;
B-045..048 -> **calcolati una volta** nello stato (`fase`, `tempo`, `minuto`, `ko`); `_ko_epoch_ms` -> funzione unica del nucleo A su `MarketBook`.

### 4.4 Stima delle righe (calcolo)

| Voce | Oggi | Domani | Perche' |
|---|---|---|---|
| `scores/` (989) | 989 | 330 | `scan_feed.py` 540 -> `servizio.py`+`canale.py` ~200 (cache, fusione, freschezza in una funzione); `poller.py` 104 -> 70; provider 287 -> 60 (tipi gia' in `contratto.py` ~60) |
| Lato scanner (poll IPS + `apply_score_state` + worker) | ~330 (`service.py:1698-1905,3258-3320` meno commenti) | 230 | resta il poll batch (strategia di caricamento), sparisce la ripetizione del parser |
| `tennis_score.py` | 265 | 190 | niente pollatori legacy (`:178-265`, ~88) -> -88 + 13 di adattamento |
| `flusso_prezzi.py` | 345 | 345 | nucleo invariato (e' gia' la regola unica) |
| 4 involucri flusso (Mike, Safe, Omega, riserva) | ~130 (`feed.py:148-250`, `exits.py:401-455`, `omega_service.py:959-1010`, `riserva_prezzi.py`) | 30 | sono 4 variazioni sull'argomento di `valuta` |
| 6 regole di freschezza gemelle | ~190 (`feed.py:435-478`, `exits.py:424-455`, `omega_service.py:62-81,913-935,1080-1110`, `bot_service.py:8502-8514`) | 70 | una tabella dei valori attuali per bot + una funzione |
| Minuto/fase ricalcolati (9 punti) | ~280 (`minute_from_clock` 9, `estimate_minute` 28, `tempo_da_stato_ips` 37, `_fase_da_scan` 8, `_ht_ancora_in_gioco` 16, watcher scalper ~190) | 60 | `fase/minuto/tempo` nello stato; i bot leggono; i watcher spariscono (`iscrivi`) |
| `_ko_epoch_ms` x4 | 91 | 20 | una funzione condivisa, un test |
| Lavoratori nei runner (calcio ~120 + tennis ~85) | 205 | 50 | `score_worker`/`score_and_now_worker` diventano "applica `StatoPartita`" |
| **Totale** | **~2.755** | **~1.325** | -1.430 righe (**-52%**). La strategia di nessun bot si tocca: cambia solo da dove arriva il numero. |

Resta come strategia (non toccato): `pressures()` (soglie di break/set point, `tennis_score.py:75-111`), i valori attuali di ogni soglia di freschezza,
la finestra del fischio (300 s) e le soglie del flusso (`flusso_prezzi.py:84-96`), perche' decisioni dell'utente (28/09, 30/09).

### 4.5 «Per sostituire questo componente»
- **Oggi** per sostituire IPS con un'altra fonte tocco: `betfair_inplay.py`, `scan_feed.py`, `poller.py`, `service.py` (3 punti), `tennis_runner.py:1645`,
  `tennis_score.py`, `runner.py:2111`, `omega_service.py:900-935`, `mike/feed.py`, `exits.py`, `bot_service.py:3214,3409` (**>= 11 file**).
- **Domani** tocco solo `nucleo/stato_partita/adattatori/` e il suo `test_contratto.py`.

### 4.6 Gia' in una libreria matura
`betfairlightweight.in_play_service` (`get_scores`, `get_event_timeline(s)`) e' gia' usata (`betfair_inplay.py:164,187`; `service.py:1731,1846`), mentre
`scoresAndBroadcast` e' chiamata con `requests` a mano (`service.py:196,1706`): l'URL non e' nella libreria. Il flusso dei prezzi non esiste in flumine
(solo `market_book.publish_time_epoch` e `status`): l'oggetto `Esito` resta nostro. API-Football: nessuna libreria matura nota nel repo; resta `api_client.py`.

---

## 5. PARITA'

Il test e' quello gia' certificato dal banco comune, rieseguito con il nuovo servizio dietro un interruttore:
- Registrazioni: `registrazioni_banco/35760084`, `35797769` (calcio, con sidecar `.scores.jsonl.gz`, `00_INVENTARIO.md:1848`); `_live_raw/<id>/<id>.raw.jsonl`
  (`PROCESSO_STANDARD_BOT.md:36,102`). Nel repo **non c'e' un raw di tennis** per il flusso (`07_MISURE_OGGI.md:58`): per il tennis servono le registrazioni
  `.score.jsonl` del recorder (`tennis_recorder.py:221`) o `tennis_replay`.
- Scenari: `python -m Betfair.stream.backtest.certifica <bot> ...` per Mike, Omega, Safe, scalper calcio, tennis; coppie vecchio/nuovo sulla stessa
  registrazione: stessi decisioni, ordini, importi, istanti.
- Numeri che devono coincidere: per OGNI riga del sidecar, `StatoPartita.minuto/gol/rossi/fase` uguale a `parse_score_dict` (`betfair_inplay.py:50`) e a
  `tempo_da_stato_ips` (`atlante_v4.py:550`); `TennisScore.key()` uguale a `parse_tennis_scores`; `Esito.vivo/motivo` uguale a `flusso_prezzi.valuta` per ogni tick; `eta.punteggio_s`
  uguale a `score_age_sec` (`scan_feed.py:506`). Test differenziale vecchio-nuovo sul parser: 100% di righe identiche.
- Copertura `PROCESSO_STANDARD_BOT.md`: §6.1 (punteggi/minuto/timeline dal sidecar **con il ritardo di produzione** IPS 2-3 s, riga 102), §6.2 (scanner vero e
  freschezza, righe 111-114), §6.7 (scenari: feed stantio, riga 170), §6.9 (replay veloci). §7: le voci sul feed stantio e sul punteggio non sono state
  rilette per numero in questa scheda (vedi "non verificato").
- Falsificazione obbligatoria: (1) rendere `Eta.riga_s` sempre 0 -> il test del feed stantio deve diventare rosso; (2) togliere il ritardo IPS -> il test di
  `punteggio_s` rosso; (3) togliere `scanner vivo` dalla regola -> gli scenari "0-0 fermo" rossi; (4) far tornare `_is_fresh(None)=True` -> rosso nel test di
  Omega. UI: fotografie del tabellone, del pannello segnali e della `SchedaPartita` (eta' del dato) prima/dopo.

## 6. MIGRAZIONE

1. **Interruttore** `STATO_PARTITA_SERVIZIO` (spento = codice di oggi riga per riga, come `PUNTEGGI_CANALE`, `scan_feed.py:90-107`).
2. **Ombra**: il servizio nuovo gira in sola lettura accanto a quello vecchio e confronta ogni stato (minuto, gol, fase, eta') con la riga di `live_now`/`tennis_live_now`;
   discrepanze scritte nel referto, mai usate per decidere. Calcio prima, tennis dopo.
3. Ordine: dopo il nucleo A (`MarketBook` e orologio unico) e prima dei plugin dei bot (D); i bot leggono `stato()` al posto di `_feed_row`, `read_live_now`,
   osservatori dello scalper. Il lato scanner (poll IPS) si sposta per ultimo.
4. Taglio del vecchio: dopo il referto uguale su tutte le registrazioni del banco e un periodo di paper; poi si tolgono i 3 osservatori e `minute_from_clock` solo come ripiego dichiarato.
5. Rischi: (a) lo scanner e' un processo condiviso da 4 bot: un errore qui ferma tutti; (b) la regola cond. 11 non puo' essere indebolita; (c) le tabelle `live_now`/`tennis_live_now`
   hanno consumatori UI che non vanno rotti (stessa forma di riga). Ritorno indietro: interruttore.

## 7. MISURE

| Cosa | Oggi (fonte) | Obiettivo |
|---|---|---|
| Ritardo punteggio calcio (Mike/Omega/Safe) | tetto da costanti ~8,6 s (`scan_feed.py:67`, `service.py:132,159`, `scan_feed.py:69`); **non misurato** | misurato <= tetto di oggi, con `eta.punteggio_s` in ogni referto |
| Ritardo punteggio scalper | tetto da costanti ~29-34 s (sez. 1.1); non misurato | <= 8,6 s (legge `stato()` come gli altri; **cambia solo la fonte**) |
| Ritardo punteggio tennis | tetto ~10,6 s (`tennis_runner.py:111`) | <= 8,6 s |
| Upsert `live_now`/`tennis_live_now` per evento | 12/min e 30/min (periodo di codice, scrittura incondizionata) | write-on-change + keepalive di `flusso_prezzi` (`runner.py:457` ha gia' il pattern del keepalive per `live_signals`) |
| Righe (area B) | ~2.755 | ~1.325 |
| Punti di chiamata a IPS | 6 | 1 (adattatore) |
| Copie freschezza | 6 con 5 soglie diverse | 1 con la tabella dei valori attuali |
| Copie `_ko_epoch_ms` / minuto | 4 (+3 lab) / 9 | 1 / 1 |
| Richieste DB per punteggio, per processo | 1 SELECT/s (canale spento) | 0 sul percorso critico (sveglia dal canale, DB solo ripiego) |

Strumenti per i numeri che mancano: una sessione a eventi in corso con `strumenti/misure/m04_chiamate_db.py` (richieste per tabella) e uno script che confronti l'`updated_at` della riga
`safe_strategy_scan` con il `ts_ms` del gol nel sidecar (ritardo reale scanner -> bot).

---

## DECISIONI PER L'UTENTE

1. Le soglie di freschezza di cui sopra sono **6 valori diversi** per concetti simili (15, 20, 25, 45, 90, 120, 180 s): il piano le porta tutte invariate in una tabella. Vuole
   che si **allineino** (decisione sulla strategia di rischio) o restano come sono? Finche' non risponde: invariate.
2. `omega_service._is_fresh(None)=True` (`:64-65`) e' piu' permissivo delle altre regole: e' voluto?
3. Il ripiego API-Football parte dopo UN fallimento (`poller.py:81-82`) e senza quota: si vuole che parta solo a circuito aperto? (cambia il comportamento del ripiego, non la strategia).
4. Lo scalper calcio legge il punteggio dopo due relay (fino a ~29-34 s): si accetta che domani legga come gli altri bot (stesso numero, meno ritardo)?

## COSA HO VERIFICATO DI PERSONA / NON HO POTUTO VERIFICARE

Verificato leggendo il codice (`sed -n`/`grep`): tutti i `file:riga` citati nelle sezioni 1-3; corpi di `_ko_epoch_ms` (le copie di `scalper_bot.py` e `tennis_scalper_bot.py`
sono identiche riga per riga); costanti di freschezza (Omega, Safe, Mike); catena scanner -> runner; assenza di `flusso_prezzi` in `stream/scalper` e `stream/tennis_live` (`git grep`).
Non verificato: (1) frequenze reali di `live_now` e `tennis_live_now` e ritardo reale del punteggio (nessun evento seguito nelle misure di oggi); (2) se `PUNTEGGI_CANALE` e' acceso nel
`.env` di produzione (default spento nel codice); (3) i numeri delle voci del catalogo §7 collegati a feed stantio/punteggio (non riletti per numero); (4) le righe esatte delle funzioni
`mission_phase` di Omega e di `_ht_ancora_in_gioco` (indicate con `~`); (5) le righe di `matches_remaining` e il suo uso; (6) i valori delle righe `s04` per il laboratorio (3 copie) non riaperti; (7) lo scalper
calcio in produzione potrebbe non usare tutti e 3 gli osservatori (dipende dai modi attivi): non ho mappato quali modi li avviano.
