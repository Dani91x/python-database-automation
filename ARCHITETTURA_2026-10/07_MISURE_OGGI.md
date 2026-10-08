# 07 - MISURE DI OGGI (08/10/2026)

Autore: delegato Sonnet (misure). Sola lettura su log, registrazioni e cloud; nessun replay del banco, nessun processo in
background, nessuna scrittura su Betfair o Supabase. Ogni numero ha lo strumento che lo ha prodotto (cartella
`ARCHITETTURA_2026-10/strumenti/misure/`, uscite in `.../misure/uscite/`). Ora di riferimento: 08/10/2026 ~14:36-14:55 ora locale
(12:36-12:55 UTC). Un delegato precedente, interrotto, aveva gia' scritto `m00_esplora_log.py` e `m01_feed_raw.py`: li ho riusati.

**Fatto di contesto che cambia il significato di molti numeri.** L'app NON e' accesa: l'ultima riga dei log e' delle 07:21 UTC
(`_logs/runner-calcio_2026-10-08T06-03-49-625Z.log`, sessione 06:03-07:21 UTC, 78 minuti, quasi tutta in «nessun evento da
streammare», 86 righe `[runner] nessun evento da streammare: attendo`). Il Postgres del cloud e' stato riavviato alle
07:28:19 UTC (`pg_postmaster_start_time`) e `pg_stat_statements` e' stato azzerato in quell'istante: i contatori del cloud
descrivono solo lavori batch del mattino, non i bot. Per i bot valgono i log. L'ultima sessione con stream attivo e ordini
in coda e' quella del 04/10 14:18 UTC (92 minuti).

---

## 0. Tabella riassuntiva

| # | Misura | Valore oggi | Fonte / strumento | Cosa manca per misurarla meglio |
|---|---|---|---|---|
| 1a | Intervallo fra messaggi dello stream, calcio in-play (39 partite registrate, 1.071.934 messaggi, 277,4 MB raw) | p50 105 ms, p95 425, p99 971, max 2.626.782 ms | `m01b_feed_per_sport.py` su `_live_raw/*/*.raw.jsonl` | Istante di ricezione locale non registrato (sez. 1.3) |
| 1b | Intervallo per mercato in-play | p50 306 ms, p95 3.518, p99 11.289, max 6.035.657 ms (n=2.179.799) | idem | idem |
| 1c | Buchi nel flusso in-play | >5 s: 486; >10 s: 230; >30 s: 106 su 3.037 min in-play = 9,6 buchi >5 s per ora in-play | idem | distinguere buco dello stream da registratore spento (solo 5 partite hanno `.recmeta.jsonl`) |
| 1d | Eta' del messaggio al ricevimento (orologio locale - `pt` Betfair) | NON misurabile dalle registrazioni; il solo segnale e' l'allarme di flumine `latency > 2 s`: 1.912 avvisi nella sessione del 04/10 14:18 in 18 secondi distinti, tutti in coincidenza di una «sottoscrizione a caldo»; 0 avvisi fuori dai 4 minuti 14:19, 14:22, 14:31, 15:32 | `grep -c "High latency"` sui log; sez. 1.3 | Registrare `rx_ms` in `raw_listener.py:211`; stampare il valore di latenza (oggi perso dal formato del log) |
| 1e | Scarto orologio del PC contro NTP | PC AVANTI di 844 ms (3 server, 5 prove, scarto 826-846 ms, RTT 13-66 ms); servizio Ora di Windows `Stopped` | `m00b_ntp_offset.py`, `Get-Service w32time` | - |
| 1f | Ritardo di scommessa (betDelay) osservato in-play, calcio | 5 s (6.388 definizioni), 8 s (30), 12 s (246) | `m01b_feed_per_sport.py` | Tennis: nessuna registrazione raw in `_live_raw` (solo file `_synth_*`) |
| 2a | Messaggio -> canale locale (cadenza strutturale del ladder) | attesa 0-200 ms per progetto (poll a 200 ms), DB ladder a 2,0 s; NON c'e' nessuna riga di log con istanti | `config_stream.py:60,74`, `runner.py:3010-3016`, sez. 2 | timestamp `ts_pub_ms` e `ricevuto_ms` (sez. 2.3) |
| 2b | Giro `send -> recv` su WebSocket loopback (laboratorio, stesso processo) | p50 0,635 ms, p95 1,96, p99 4,12, max 10,2 (n=2.000) | `m07_lab_rete.py` (A) | misura sul canale vero 127.0.0.1:47331/47333 con carico reale |
| 2c | `json.dumps` di un ladder di 1.332 byte | p50 167 us, p95 542, p99 1.827, max 7.030 | `m07_lab_rete.py` (A) | idem |
| 3a | Decisione -> arrivo sul motore ordini (canale `/comando`, bot Safe tennis) | 84, 108, 194 ms (n=3, tutte con esito errore `mode_non_servibile`) | log `runner-tennis_2026-10-04T09-21-06-363Z.log`, righe `tempi_ordine` | nessun ordine reale e' mai passato dal modulo di misura (sez. 3) |
| 3b | Coda DB -> elaborazione, `place` paper (n=38) | p50 492 ms, p95 2.481, p99 26.636, max 36.524 | cloud Q6 (`betfair_live_order_requests`) | orologi DB/PC diversi |
| 3c | cancel (n=8) / replace (n=3) / greenup (n=13), paper | cancel p50 406 p95 874 max 938; replace p50 307 p95 643 max 681; greenup p50 365 p95 1.227 max 1.232 ms | cloud Q6 | idem |
| 3d | Risposta di Betfair a `placeOrders`, abbinamento, ordini LIVE | NON misurabile oggi: 1 richiesta live in tutta la storia (2026-07-10, esito -100 ms = orologi misti); 4 ordini live del runner, 2 abbinati (place->match 17,2 s e 24,2 s) | cloud Q6 | un ciclo paper/live acceso con `LIVE_TEMPI_ORDINE=1` e lettura con `leggi_tempi_ordine.py` |
| 4a | Richieste al DB, totale app | sessione 08/10: 707,5/min in media (p50 575, p95 1.032, max 1.034); sessione 04/10 (stream attivo): 1.309,0/min (p50 1.343, p95 1.494, max 1.563); sessione 02/10: 1.268,2/min | `m04_chiamate_db.py` | latenza HTTP per richiesta: httpx non la scrive |
| 4b | Latenza HTTP verso il cloud (laboratorio, senza chiave) | DNS 23 ms, TCP 15 ms, TLS 50 ms; richiesta su connessione calda p50 21,3 ms, p95 26,1, p99 35,5 (n=39); prima richiesta 79 ms | `m07_lab_rete.py` (B) | misura su query vera con la chiave dell'app (non fatta: segreti) |
| 5a | Processi dell'app | nessuno acceso (nessun electron, nessun `python -m Betfair...`) | `Get-Process` 14:36 | `m05b_campiona_processi.ps1` ad app accesa |
| 5b | Log su disco | 1.428 MB in 21 sessioni (01-08/10); backtest-worker 1.138 MB (80%); senza backtest-worker 290 MB; senza backtest-worker per giorno-sessione: 94, 28, 80, 58, 15, 14 MB (01, 02, 04, 06, 07, 08/10) | `m05_risorse_disco.py` | - |
| 5c | Registrazioni | `_live_raw` 4.260 MB per 67 partite: `<ev>.jsonl` (snapshot) 3.976 MB (93%), `raw.jsonl` 277,5 MB; per partita p50 9,0 MB, p95 404 MB, max 448 MB; solo raw per partita p50 5,4 / p95 22,0 / max 25,0 MB | `m05_risorse_disco.py`, `m01_feed_raw.py` | - |
| 6 | Persistenza stato vivo: SQLite WAL / log append / memoria | sez. 6, tabella completa | `m06_lab_persistenza.py` | disco di produzione sotto carico concorrente |
| 7 | Cloud | 52 GB, 173 tabelle; 20 GB solo `match_odds` (92,5 M righe); tabelle dei bot: 1-93.068 righe, 0,2-19 MB | MCP SELECT, Q1-Q6 | `pg_stat_statements` ripartito alle 07:28 UTC: ripetere a bot accesi |

---

## 1. Eta' del feed e buchi

### 1.1 Sorgente e formato (verificato nel codice)
- Una riga di `_live_raw/<evento>/<evento>.raw.jsonl` = un messaggio `mcm` con le sole chiavi `op, clk, pt, ct, mc`
  (`Betfair/stream/raw_listener.py:211`: `out = {k: msg[k] for k in ("op","clk","pt","ct")}`), scritta con `fh.write` + `fh.flush()`
  (`raw_listener.py:221-222`). `pt` = publish time di Betfair in ms.
- NON c'e' l'istante di ricezione locale. I battiti `ct=HEARTBEAT` NON sono scritti (`raw_listener.py:177-181`: aggiornano
  solo `last_heartbeat_ms`). Quindi in un'ora di mercato fermo si vede un buco anche se la connessione e' viva.
- Il file `<evento>.jsonl` (snapshot per mercato: `pt`, `status`, `inplay`, `runners.{b,l,ltp,tv,trd}`) ha anch'esso solo `pt`.
  Il solo orologio locale e' nel file `scores.jsonl` (`ts_ms`), ma e' dei punteggi API-Football, non di Betfair.
- Il runner calcio sottoscrive con `STREAM_CONFLATE_MS = 0` (`Betfair/stream/config_stream.py:87`), lo scanner Safe con
  conflate 1000 ms (`Betfair/safe_strategy/stream.py:66,275`). Il raw descrive quindi il passo nativo di Betfair per il set
  sottoscritto, non un passo scelto da noi.

### 1.2 Risultati (`m01b_feed_per_sport.py`, 34 s di lettura; per partita: `uscite/m01_feed_raw.txt`)
Campione: 40 file raw, 39 di calcio (eventTypeId 1) + 1 senza `marketDefinition`; 3.037 minuti in-play (somma degli intervalli).
Tennis: nessun raw nella cartella (solo `_synth_safe_tennis*`), quindi NESSUNA misura del feed tennis registrato.

| Misura | n | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| intervallo fra messaggi, in-play | 866.666 | 105 ms | 425 | 971 | 2.626.782 |
| intervallo fra messaggi, tutti (pre-partita inclusi) | 1.071.904 | 106 ms | 613 | 1.809 | 4.873.575 |
| intervallo per mercato, in-play | 2.179.799 | 306 ms | 3.518 | 11.289 | 6.035.657 |

Buchi: in-play >5 s 486, >10 s 230, >30 s 106 (9,6 per ora in-play); su tutto il file >5 s 2.530, >10 s 875, >30 s 225
(`uscite/m01_feed_raw.txt`, riga `# TOTALE`). I massimi (43 e 100 minuti) sono intervalli di registratore spento, intervallo fra
tempi o mercato sospeso: nei file con `.recmeta.jsonl` (5 su 67) il toggle e' scritto (`raw_listener.py:90-137`), negli altri non
si distingue. Il valore robusto e' la coda p99: 971 ms in-play. Per partita il p99 in-play va da 515 ms (35764745) a 3.189 ms
(35760084, `m01_feed_raw.txt`).
Peso: 43.776-113.652 byte/min per partita (da 3,0 a 6,2 messaggi/s), 241-307 byte/messaggio.

### 1.3 Eta' del messaggio (`pt` contro orologio locale): cosa si puo' dire
- Dalle registrazioni: nulla (manca `rx_ms`). Cosa manca e dove andrebbe: in `Betfair/stream/raw_listener.py:211`, aggiungere a `out`
  la chiave `rx` con `int(time.time()*1000)` presa all'ingresso di `write_message` (`raw_listener.py:151`), prima del `json.loads`.
  Effetto sul peso: +16 byte per riga (~6%).
- Dai log del runner: flumine scrive `High latency between current time and MarketBook publish time` quando
  `time.time() - publish_time > 2 s` (`.venv/Lib/site-packages/flumine/baseflumine.py:137-145`, flumine 2.13.11) con `extra={"latency":..}`,
  ma il formato del log del runner e' `"%(asctime)s %(levelname)s %(message)s"` (`Betfair/stream/runner.py:3150`): il valore
  NON viene stampato. Si conta solo il superamento della soglia.
- Conteggio per sessione del runner calcio (`grep -c`): 01/10 13:09 = 113; 02/10 = 44; 04/10 09:21 = 61; **04/10 14:18 = 1.912**;
  06/10 12:42 = 28; 06/10 13:45 = 66; 06/10 15:14 = 92; 06/10 15:38 = 428; 07/10 15:57 = 50; 08/10 = 0.
  Nella sessione del 04/10 14:18 (92 minuti, 5.400 secondi) gli avvisi cadono in 18 secondi distinti, con 1.292 al minuto 14:19, 450 al
  14:22, 134 al 14:31, 36 al 15:32: in tutti e quattro i minuti c'e' una riga `[auto-follow] sottoscrizione a caldo`
  (101 in 92 minuti, fino a 9 in un minuto). Il flusso di regime non ha mai superato la soglia di 2 s nel campione; i superamenti
  sono rimbalzi alla risottoscrizione (immagine `SUB_IMAGE` con `pt` vecchio).
- Errore di orologio: il PC e' AVANTI di 844 ms (`m00b_ntp_offset.py`: -826/-846/-844/-844/-844 ms con time.windows.com, e
  -833...-845 ms con pool.ntp.org, -835...-843 con time.cloudflare.com). Il misurato `locale - pt` sovrastima l'eta' vera di circa
  0,84 s: la soglia 2 s di flumine equivale oggi a ~1,16 s veri. Il 17/09 l'errore era l'opposto (PC indietro di 2,07 s,
  `Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md:31`). `Get-Service w32time` = `Stopped`: l'orologio deriva e nessuno lo corregge.
  Questo numero e' un difetto da correggere prima di qualsiasi misura di latenza verso Betfair.
- Altri segni dello stream nel log del 04/10 14:18: 106 righe `SUCCESS` di connessione stream, 317 `Unwanted data received from uniqueId`
  (messaggi di stream sostituiti dopo la risottoscrizione), 102 `stream already registered, replacing data`.

---

## 2. Messaggio -> canale -> bot

### 2.1 Cosa dicono i log
Nessun log dell'app contiene un istante per messaggio sul percorso stream -> canale locale -> bot. Ho censito le righe non-HTTP di tutti
i log (esclusi i backtest-worker): i tag piu' frequenti sono `[safe-scan]` 74.070, `[tennis-runner]` 24.267, `[risk]` 8.530,
`[tennis-ladder]` 6.362, `[db]` 5.780, `[ladder-worker]` 2.307, `[live-order]` 1.104; `[local-ws]` ha 103 righe e dicono solo «canale attivo»
o «N invii in volo, salto i push» (`local_channel.py:642-650`). Nessuno riporta ms.

### 2.2 Cosa si sa dal codice (cadenze strutturali)
- Il ladder va al canale locale dal `ladder_worker`, un `BackgroundWorker` a intervallo
  `min(db_sec, max(canale_sec, 0.02))` (`Betfair/stream/ladder_canale.py:103-105`; creazione `runner.py:3010-3016`). Con
  `LIVE_LADDER_CANALE_MS=200` (`config_stream.py:74`) il worker gira ogni 200 ms: un cambio di prezzo aspetta fra 0 e 200 ms
  (in media ~100 ms) prima di essere serializzato (`local_channel.py:653`) e pubblicato (`runner.py:745`).
- Il ladder va al DB (`live_ladder`) ogni `LIVE_LADDER_PUBLISH_SEC=2.0` s (`config_stream.py:60`), solo se cambia (`runner.py:733`).
- La pubblicazione e' `loop.call_soon_threadsafe(_broadcast)` (`local_channel.py:669`): salta il giro quando un client ha piu'
  di 64 invii in volo (`local_channel.py:176`, `:664-667`).
- La coda ordini del DB viene letta ogni `LIVE_ORDER_QUEUE_POLL_SEC=1.0` s (`config_stream.py:229`): coerente col p50 di ~0,5 s
  del tratto coda->elaborazione misurato sul cloud (sez. 3.2), ma non e' una misura del legame causale.
- Lo scanner Safe legge Betfair con conflate 1.000 ms (`safe_strategy/stream.py:66`), quindi un prezzo puo' arrivare
  fino a 1 s dopo il fatto prima ancora di toccare il nostro codice.

### 2.3 Laboratorio (`m07_lab_rete.py`, parte A)
Server e client `websockets` 15.0.1 nello stesso processo, loopback, ladder-like di 1.332 byte (3 selezioni x 10 livelli back/lay),
2.000 messaggi a cadenza 5 ms: **giro `send -> recv` p50 0,635 ms, p95 1,958, p99 4,119, max 10,244 ms**;
`json.dumps` del messaggio p50 167 us, p95 542, p99 1.827, max 7.030 us (processo freddo, pause di 5 ms fra i messaggi).
Il 17/09 era stato misurato 0,59 ms p50 (`LATENZA_TENNIS_2026-09-17.md`, riga 20-30 della sezione di sintesi): stesso ordine.
E' un LIMITE INFERIORE (nessun altro carico, nessun altro client, nessuna GIL contesa): non e' la misura del canale vero.

### 2.4 Cosa manca e dove metterlo
1. `Betfair/stream/raw_listener.py:211` - aggiungere `rx` (ricezione locale, ms) al raw: da' `rx - pt` su ogni messaggio registrato.
2. `Betfair/stream/runner.py:3150` - il formato del log non stampa `extra`: usare `%(message)s %(latency).0f` non basta (non tutte le
   righe hanno `latency`); alternativa: un handler su `flumine.baseflumine` che scriva `latency` nel messaggio.
3. `Betfair/stream/runner.py:745` (prima di `_lc.publish("ladder", row)`) - aggiungere `row["ts_pub_ms"]` e, in `build_ladder_payload`, il
   `pt` del book: da' `ts_pub - pt` (eta' del dato al momento della pubblicazione).
4. `Betfair/stream/local_channel.py:180` - `LocalRequest` non ha `ricevuto_ms` (e' scritto cosi' anche in
   `AUDIT_2026-09-25/F0_TEMPI_ORDINE_2026-09-25.md`, sez. 3): aggiungerlo al drenaggio (`pop_requests`, `local_channel.py:673`).
5. Lato bot (`Betfair/stream/canale_bot.py:219`, `safe_strategy/canale_scan.py`, `mike/service.py:7274`): stampare `ricevuto_ms - ts_pub_ms`
   a campione (1 riga ogni N secondi, non per messaggio) per non gonfiare i log.

---

## 3. Decisione -> `placeOrders` -> risposta, cancel/replace, bet delay

### 3.1 Cosa esiste
Il modulo di misura F0 (`Betfair/stream/tempi_ordine.py`, 455 righe; lettore `Betfair/stream/tools/leggi_tempi_ordine.py`, 148 righe)
scrive UNA riga `tempi_ordine ...` per ordine con i tratti `decisione_ms, ricezione_ms, presa_ms, place_ms, risposta_ms, abbinato_ms,
interno_ms, risposta_bf_ms` (descrizione `tempi_ordine.py:1-50`; agganci in `live_order_worker.py:1271,2938,3481,3688,3864` e `motore_ordini.py:950,1014,1516`, righe verificate sul checkout principale; la descrizione F0 `AUDIT_2026-09-25/F0_TEMPI_ORDINE_2026-09-25.md` cita le righe del worktree, che differiscono).
E' acceso di serie (`LIVE_TEMPI_ORDINE`, `tempi_ordine.py:64`).

### 3.2 Cosa e' stato misurato davvero
- **Log dell'app**: in tutti i 197 file di `_logs/` ci sono 3 righe `tempi_ordine`, tutte in
  `runner-tennis_2026-10-04T09-21-06-363Z.log`, tutte `esito=errore errore=mode_non_servibile:_mode_'live'_non_servibile_dal_runner_in_PAPER`
  (rif `safe_tennis-t364`, `-t368`, `-t378`): `decisione_ms` = 108, 194, 84; `ricezione_ms` = 0, 1, 1; gli altri tratti `na` perche'
  l'ordine non e' arrivato a `place_order`. Nessuna riga in nessuna delle sessioni del calcio (0 in `runner-calcio_*`).
  Sono quindi misure di «Safe tennis -> motore ordini sul canale `/comando`»: 84-194 ms, n=3, da non generalizzare.
- **Cloud, orologio del DB** (Q6 in `uscite/m07_cloud_sola_lettura.txt`): coda `betfair_live_order_requests`, `processed_at - requested_at`,
  tutte paper tranne una: 

| Azione (paper, status done) | n | p50 ms | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| place | 38 | 492 | 2.481 | 26.636 | 36.524 |
| greenup | 13 | 365 | 1.227 | 1.231 | 1.232 |
| cancel | 8 | 406 | 874 | 925 | 938 |
| cashout_all | 4 | 910 | 1.050 | 1.063 | 1.066 |
| cashout_event | 4 | 133 | 948 | 987 | 996 |
| dutch | 3 | 560 | 1.188 | 1.243 | 1.257 |
| replace | 3 | 307 | 643 | 673 | 681 |
| place_submin (attesa voluta) | 3 | 8.464 | 8.880 | 8.917 | 8.926 |
| place (status error) | 13 | 486 | 1.175 | 1.255 | 1.276 |

  Tennis `tennis_live_order_queue`: done n=17 p50 220 p95 2.325 max 6.478 ms; error n=11 p50 406 p95 1.283 max 1.326 ms.
  Periodo dei dati: 30/06-26/09/2026. `requested_at` e' scritto dal DB e `processed_at` dal PC: sono due orologi, con
  errore sistematico pari allo scarto fra loro; l'unica riga live ha esito -100 ms (processata PRIMA di essere richiesta).
- **Ordini live veri**: `betfair_live_orders` ha 102 righe: 98 con `source=account` (specchio dell'account, nessuna con `matched_at`) e
  4 con `source=runner` (2026-07-10..2026-09-01), di cui 2 con `matched_at`: `matched_at - placed_at` = 17,2 s e 24,2 s (n=2: nessuna statistica).
- **Bet delay osservato** (dalle `marketDefinition` in-play dei raw): 5 s per 6.388 definizioni, 8 s per 30, 12 s per 246
  (`uscite/m01b_feed_per_sport.txt`). Non dipende da noi.

### 3.3 Cosa manca
Nessun ordine reale con tutti i tratti: `decisione_ms` richiede che il bot scriva `emesso_ms` nei `params` di Omega e Safe
(`omega_service.py:2838,2879` chiamano `_flumine_enqueue_place`; `safe_strategy/execution.py:1810` ha `"params": {"source": "safe", "trade_id": ...}`; vedi `F0_TEMPI_ORDINE_2026-09-25.md` sez. 3) e il desktop nel comando
(`frontend/src/lib/localTransport.ts:443-447`, `client_ref` senza istante del clic). Per avere p50/p95/p99 veri servono almeno 30 ordini in un ciclo paper con l'app accesa; poi
`python -m Betfair.stream.tools.leggi_tempi_ordine <log>` (non l'ho lanciato: legge solo log, ma i log non hanno ordini).

### 3.4 Costo del diario write-ahead nel percorso dell'ordine
`motore_ordini.py:20-22` scrive una riga con flush e fsync PRIMA di ogni `place_order` (diario `_diario_ordini/<data>.jsonl`; la cartella non esiste
sul disco: il motore non ha mai scritto un ordine su questo PC). Il laboratorio sez. 6 misura cosa costa un fsync per record su
questo disco: p50 0,43-0,47 ms, p95 7,4-23,3 ms, p99 9,7-37,2 ms, max 0,24-0,89 s.

---

## 4. Richieste al DB per servizio e tabella

Strumento: `m04_chiamate_db.py` (stesso metodo di `SCHEMI_BOT/sistema/strumenti/misura_chiamate_db.py`: conta le righe
`HTTP Request: <METODO> https://<host>/rest/v1/<tabella>`; qui sull'INTERA sessione, minuti vuoti inclusi). Sessioni intere
(solo righe di servizio, backtest-worker escluso; `uscite/m04_chiamate_db.txt`). Riproduce il 02/10: 106.526 richieste in 84 min =
1.268/min medi, p50 1.306/min (la finestra del 02/10 aveva dato 1.309/min, `SCHEMI_BOT/sistema/MISURE_2026-10-02.md`).

### 4.1 Totale app (richieste/minuto)

| Sessione (UTC) | minuti | richieste | media/min | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 02/10 14:25 (stream attivo) | 84 | 106.526 | 1.268,2 | 1.306 | 1.363 | 1.377 | 1.413 |
| 04/10 14:18 (stream attivo) | 92 | 120.428 | 1.309,0 | 1.343 | 1.494 | 1.502 | 1.563 |
| 06/10 15:38 | 36 | 18.391 | 510,9 | 0 | 1.633 | 1.656 | 1.656 |
| 07/10 14:23 | 33 | 31.585 | 957,1 | 1.019 | 1.030 | 1.044 | 1.044 |
| 07/10 15:57 | 29 | 28.043 | 967,0 | 1.023 | 1.033 | 1.033 | 1.033 |
| 08/10 06:03 (quasi sempre «nessun evento») | 79 | 55.895 | 707,5 | 575 | 1.032 | 1.033 | 1.034 |

### 4.2 Per servizio, media al minuto (e p95 al minuto)

| Servizio | 02/10 | 04/10 | 08/10 (p95) | Tabelle principali 08/10 (richieste/min) |
|---|---:|---:|---:|---|
| runner-calcio | 537,2 | 557,6 | 210,5 (p50 45, p95 489) | `betfair_live_risk_rules` 63,8 GET; `betfair_live_order_requests` 48,9 GET; `rpc/get_live_settings` 46,0; `live_follow` 26,9; heartbeat 7,4 POST |
| safe-strategy-bot | 254,6 | 265,8 | 232,3 (p95 259) | `safe_strategy_trades` 82,0 GET; `safe_strategy_requests` 44,6 GET + 19,1 PATCH; `safe_strategy_control` 37,9 GET + 19,0 PATCH; `rpc/get_safe_aggregates` 17,9 |
| mike-service | 251,9 | 256,1 | 48,0 (p95 54) | `mike_control`, `mike_requests`, `safe_strategy_scan`, `mike_trades`: 10,4/min ciascuna; PATCH `mike_control` 2,7; `rpc/get_mike_aggregates` 2,6 |
| safe-strategy-service | 85,1 | 88,9 | 81,7 (p95 94) | `safe_strategy_scan` POST 65,4; `mike_events` GET 5,5; `rpc/list_bot_exposures` 5,5; `safe_strategy_status` POST 4,7 |
| scalper-service | 54,3 | 55,0 | 52,5 (p95 57) | `scalper_control` 17,5; `rpc/get_live_settings` 17,5; `scalper_service_control` 17,5 |
| tennis-bot-service | 44,0 | 44,4 | 43,0 (p95 48) | `tennis_bot_control` 21,5 GET; `tennis_bot_service_control` PATCH 14,3 + GET 3,6; `tennis_live_follow` 3,6 |
| runner-tennis | 28,2 | 28,4 | 27,2 (p95 29) | `tennis_live_follow` 27,1 GET |
| omega-service | 12,7 | 12,7 | 12,2 (p95 13) | `omega_trades` 5,6 GET; altre 0,9 ciascuna |
| tennis-odds | 0,1 | 0,1 | 0,1 | `tennis_markets` POST/DELETE (3+3 in 63 min) |

Osservazioni (tutte lette dai numeri sopra):
- Il runner calcio e' bimodale: p50 45 e p95 489 richieste/min il 08/10 (nessun evento da streammare vs stream attivo); con stream
  attivo il 04/10 fa 557,6/min, di cui 202,3 su `betfair_live_order_requests` GET, 164,7 su `betfair_live_risk_rules` GET e 119,9 su
  `rpc/get_live_settings`: tre tabelle di 98, 14 e 1 riga (cloud Q4) lette ~486 volte al minuto.
- Mike e' passato da 252-256/min (02/10, 04/10) a 46-48/min (07-08/10): `mike_trades` da 107,8/min a 10,4/min. Non ho verificato
  nel codice quale cambiamento l'ha prodotto.
- La somma dei soli servizi di controllo/coda (`*_control`, `*_requests`, `rpc/get_*_settings`, `*_service_control`) e' la parte maggiore
  del traffico: 08/10 = runner-calcio (`risk_rules`+`order_requests`+`get_live_settings`) 158,7 + safe-bot (`requests`+`control`)
  ~120 + mike (`control`+`requests`) 20,8 + scalper 52,5 + tennis-bot 39,4 = ~391 su 707,5/min. Il calcolo e' indicativo (somma a mano
  delle righe della tabella 4.2).
- Proiezione grezza al giorno (richieste/min x 1.440, NON misura di un giorno intero): 08/10 = 1,02 M; 04/10 = 1,88 M.
  Nessun log copre 24 ore consecutive: la sessione piu' lunga e' di 92 minuti.

### 4.3 Latenza HTTP
httpx non scrive la durata: dai log NON si ricava. Misure sostitutive:
- Rete e gateway (`m07_lab_rete.py`, parte B, host `dqbwaocvlzbxfrpacsac.supabase.co` -> 172.64.149.246): DNS 23,4 ms, TCP 15,4 ms, TLS 50,5 ms;
  `GET /rest/v1/` senza chiave (401) su connessione riusata: p50 21,3 ms, p95 26,1, p99 35,5, max 35,5 (n=39); prima richiesta 79,0 ms.
  E' il giro di rete + gateway senza query: una query vera costa questo piu' il tempo in Postgres.
- Tempo in Postgres (`pg_stat_statements`, finestra 07:28-12:44 UTC, solo lavori batch): SELECT di PostgREST su `analytics_signals`
  media 13,2 ms (6.927 chiamate, max 58,8); INSERT `analytics_snap_staging` media 6,3 ms (1.244 chiamate); SELECT `matches` media 8,0 e 30,0 ms; RPC con
  `p_league_id` media 276,1 ms max 4.820 ms (1.244 chiamate); `set_config` di PostgREST 0,03 ms (13.196 chiamate). Nessuna query
  delle tabelle dei bot e' in finestra (app spenta).
- Misura storica citata, NON di oggi: «una chiamata PostgREST costa 92-307 ms» (`Betfair/safe_strategy/LATENZA_TENNIS_2026-09-17.md`,
  riga 20-30); la rete oggi da' ~21 ms di giro minimo, quindi il 92-307 del 17/09 era dominato da altro (non verificato da me).

---

## 5. Risorse

### 5.1 Processi (14:36, `Get-Process`, sola lettura)
L'app non e' accesa: nessun processo electron, nessun `python -m Betfair.*`. Processi vivi: `node` 31608 (58 MB, avviato 03:54), `python`
21160 (75,8 MB, avviato alle 14:33, non attribuibile all'app), `WhatsApp.Root`, `LockApp`. Quindi CPU e RAM dell'app: NON misurabili oggi.
Pronto per quando l'app e' accesa: `strumenti/misure/m05b_campiona_processi.ps1 -Campioni 30 -Secondi 10` (foreground, finito, CPU in % di un core,
working set, private, thread, handle per pid; mediana/p95/max). Non l'ho lanciato (niente processi da misurare).
Macchina: AMD Ryzen 7 3750H, 4 core/8 thread, 15,8 GB di RAM; disco del repository (`C:`): Intel SSDPEKNW512G8 NVMe 512 GB
(`Get-Partition -DriveLetter C | Get-Disk`); secondo disco Toshiba MQ04ABF100 HDD SATA 1 TB.

### 5.2 Log (`m05_risorse_disco.py`, `uscite/m05_risorse_disco.txt`)
Totale `_logs/`: 1.428,1 MB in 197 file (21 sessioni dal 01/10 al 08/10).
| Servizio | MB totali | MB/ora di sessione |
|---|---:|---:|
| backtest-worker (8 file) | 1.138,1 | 356 (stima da mtime) |
| runner-calcio | 129,2 | 8,3 |
| safe-strategy-bot | 52,4 | 3,4 |
| mike-service | 35,1 | 2,3 |
| safe-strategy-service | 33,2 | 2,1 |
| runner-tennis | 14,5 | 0,9 |
| scalper-service | 13,7 | 0,9 |
| tennis-bot-service | 8,8 | 0,6 |
| omega-service | 2,8 | 0,2 |
| tennis-odds | 0,3 | 0,03 |

Per giorno (data di avvio sessione, MB, totale / senza backtest-worker / solo backtest-worker): 01/10 94,3/94,3/0; 02/10 27,8/27,8/0;
04/10 80,3/80,3/0; 06/10 573,7/58,5/515,2; 07/10 184,2/15,0/169,2; 08/10 467,8/14,2/453,7. I MB/ora usano l'ora di avvio nel nome del
file e l'mtime: sono stime (le sessioni hanno ore morte). Il log da 3 GB di cui parla il CLAUDE.md non e' in `_logs/` oggi
(il piu' grande e' un backtest-worker da 475 MB, 08/10).
I log dei servizi in `_logs/` non hanno rotazione per dimensione: l'unico `RotatingFileHandler` nel codice tracciato e' in `Betfair/betfair_report_manager.py:6,35-42` (`git grep -n RotatingFileHandler -- '*.py'`: 1 file di produzione).

### 5.3 Registrazioni (`_live_raw/`, 67 partite)
Totale 4.260,6 MB: `<ev>.jsonl` 3.976,2 MB (93%), `raw.jsonl` 277,5 MB (6,5%), `scores.jsonl` 6,8 MB, `timeline.jsonl` 0,1 MB.
Per partita (tutti i file): p50 9,0 MB, p95 404,3 MB, max 447,9 MB (una partita pre-partita lunga come 35797769 pesa 440 MB di snapshot
+ 23 MB di raw). Solo raw (40 partite): p50 5,4 MB, p95 22,0 MB, max 25,0 MB. `registrazioni_banco/` (copia compressa per i replay): 4,9 MB, 2 partite.

---

## 6. Prova di laboratorio §9.3: SQLite WAL, log append-only, solo memoria

Strumento: `m06_lab_persistenza.py <tmp> 3000 3` (cartella `strumenti/misure/tmp/`, cancellata a fine lavoro). Macchina e disco di sez. 5.1
(SQLite 3.49.1, Python 3.13.3, Windows 11). Record di ~190 byte (JSON). N = 3.000 record per ripetizione, 3 ripetizioni; latenza per record
(per COMMIT da 100 record nei modi `lotti`); CPU = tempo CPU del processo / tempo di muro. Uscita grezza: `uscite/m06_lab_persistenza.txt`.

| Modo | rip. | p50 us | p95 us | p99 us | max us | record/s | CPU/muro | disco MB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| solo memoria (lista) | 1 / 2 / 3 | 14,7 / 14,9 / 15,0 | 34,6 / 54,6 / 28,3 | 96 / 199 / 84 | 10.200 / 12.711 / 5.836 | 40.813 / 32.225 / 45.754 | 85 / 50 / 95% | 0 |
| log, write senza flush | 1 / 2 / 3 | 0,6 / 0,6 / 0,6 | 1,9 / 2,3 / 2,6 | 104 / 88 / 98 | 8.225 / 3.484 / 864 | 21.316 / 38.025 / 32.079 | 44 / 79 / 84% | 0,76 |
| log, write + flush | 1 / 2 / 3 | 11,3 / 10,9 / 10,9 | 24,5 / 23,8 / 23,3 | 113 / 119 / 108 | 59.995 / 14.762 / 15.639 | 15.179 / 15.635 / 22.888 | 55 / 49 / 83% | 0,76 |
| log, write + flush + fsync | 1 / 2 / 3 | 434 / 449 / 472 | 8.367 / 7.404 / 23.263 | 12.719 / 9.679 / 37.236 | 244.048 / 239.679 / 894.185 | 624 / 711 / 293 | 23 / 27 / 12,5% | 0,76 |
| SQLite WAL, NORMAL, 1 commit/record | 1 / 2 / 3 | 53,0 / 52,2 / 54,0 | 138 / 148 / 156 | 460 / 655 / 659 | 700.078 / 777.777 / 957.873 | 1.228 / 1.144 / 1.086 | 11,5 / 10,7 / 11,3% | 0,85 |
| SQLite WAL, FULL, 1 commit/record | 1 / 2 / 3 | 607 / 629 / 593 | 22.766 / 22.530 / 22.803 | 29.253 / 27.831 / 29.146 | 68.018 / 180.384 / 66.602 | 393 / 370 / 411 | 23 / 21 / 23% | 0,85 |
| SQLite WAL, NORMAL, 100 record/commit | 1 / 2 / 3 | 932 / 787 / 783 | 2.366 / 5.714 / 2.309 | 3.090 / 6.109 / 6.427 | 3.090 / 6.109 / 6.427 | 4.330 / 4.155 / 5.361 | 11 / 11 / 17% | 0,85 |
| SQLite WAL, FULL, 100 record/commit | 1 / 2 / 3 | 6.352 / 4.903 / 2.551 | 40.086 / 61.670 / 38.220 | 46.180 / 184.376 / 39.932 | 46.180 / 184.376 / 39.932 | 3.693 / 3.504 / 4.535 | 19 / 11 / 19% | 0,85 |

Come leggere (solo cio' che i numeri dicono):
- Il costo tipico per record: log con flush 11 us, SQLite NORMAL 53 us, SQLite FULL e log con fsync 0,43-0,63 ms. Throughput di un thread:
  da ~15.000 record/s (flush) a ~300-700 (fsync/FULL con commit singolo); a lotti da 100 SQLite NORMAL arriva a 4.155-5.361 record/s.
- Le code lunghe sono il costo vero: con fsync/FULL il p95 va da 7,4 a 23,3 ms e il massimo da 67 ms a 0,89 s. SQLite NORMAL ha p99 0,46-0,66 ms ma massimi
  di 0,70-0,96 s: sono i checkpoint. La documentazione dice: «By default, SQLite does a checkpoint automatically when the WAL file reaches a
  threshold size of 1000 pages ... most COMMIT operations to be very fast but an occasional COMMIT (those that trigger a checkpoint) to be much
  slower» e «with PRAGMA synchronous set to NORMAL, the checkpoint is the only operation to issue an I/O barrier or sync operation»
  (https://www.sqlite.org/wal.html, sezioni «Performance Considerations»). Non ho provato a spostare il checkpoint su un thread/finestra a parte
  ne' a cambiare `wal_autocheckpoint`: il numero oggi misura il default.
- CPU: SQLite 11-23% del tempo di muro (su un thread), log con flush 49-83%, memoria 50-95%: il collo della memoria e' la costruzione del JSON
  (python), non il contenitore.
- Disco: 0,76 MB (log) e 0,85 MB (SQLite: DB + WAL) per 3.000 record: 253 byte/record su log, 283 su SQLite (+12%).

### 6.1 Cosa si perde in un crash (prova eseguita + documentazione)
Prova eseguita (un processo figlio scrive 500 record, dichiara «ack k» dopo ogni scrittura, poi muore con `os._exit(1)`: crash del
PROCESSO, non spegnimento del PC), conteggio dei record ritrovati:

| Modo | scritti e confermati | recuperati | persi |
|---|---:|---:|---:|
| solo memoria | 500 | 0 | 500 |
| log senza flush | 500 | 490 | 10 (il buffer di Python non ancora scritto) |
| log con flush | 500 | 500 | 0 |
| log con flush + fsync | 500 | 500 | 0 |
| SQLite WAL NORMAL | 500 | 500 | 0 |
| SQLite WAL FULL | 500 | 500 | 0 |

Spegnimento del PC / crash del sistema operativo: NON provato (richiede togliere corrente); valgono le fonti:
- SQLite, `PRAGMA synchronous` (https://www.sqlite.org/pragma.html#pragma_synchronous): «WAL mode is always consistent with synchronous=NORMAL,
  but WAL mode does lose durability. A transaction committed in WAL mode with synchronous=NORMAL might roll back following a power loss or system
  crash. Transactions are durable across application crashes regardless of the synchronous setting or journal mode.» E per FULL: «This ensures that an
  operating system crash or power failure will not corrupt the database ... FULL is atomic, consistent, isolated, and durable (ACID) in WAL mode».
- SQLite, WAL (https://www.sqlite.org/wal.html): «Writers sync the WAL on every transaction commit if PRAGMA synchronous is set to FULL but omit this sync if
  PRAGMA synchronous is set to NORMAL»; «All processes using a database must be on the same host computer; WAL does not work over a network filesystem».
- Dal laboratorio, per analogia (non da fonte): il log con flush lascia i dati nella cache del sistema operativo (sopravvive al crash del
  processo, come la prova dimostra) ma NON e' garantito sul disco dopo uno spegnimento; il log con fsync si'. Il log senza flush perde il buffer del
  processo (10 record su 500 nella prova).
- Stato di oggi nel nostro codice: il raw dello stream e' scritto in modo «write + flush» (`raw_listener.py:221-222`); il diario degli ordini e' progettato
  «con flush e fsync» (`motore_ordini.py:20-22`).

---

## 7. Cloud in sola lettura (MCP supabase, solo SELECT; `uscite/m07_cloud_sola_lettura.txt`)

- Progetto `dqbwaocvlzbxfrpacsac` (eu-north-1, Postgres 17.6, ACTIVE_HEALTHY). Dimensione 52 GB, 173 tabelle, `max_connections` 60 (5 aperte, 1 attiva).
- Tabelle piu' grandi (righe da `pg_class.reltuples`, stima; heap + indici): `match_odds` 92.477.800 righe 20 GB (17 GB heap + 3,8 GB indici);
  `match_lineups` 24.269.508 righe 7,6 GB; `match_player_stats` 5.407.244 righe 6,8 GB; `match_events` 9.849.575 righe 5,6 GB; `matches` 1.494.534
  righe 3,0 GB; `live_market_snapshots` 1.288.493 righe 2,4 GB; `match_team_stats` 6.402.814 righe 1,35 GB; `analytics_signals` 1.252.609 righe 1,1 GB;
  `fixture_predictions` 121.881 righe 1,06 GB; `api_call_log` 2.751.992 righe 515 MB.
- Tabelle dello stato vivo dei bot: 1-93.068 righe, 0,14-19 MB: `scalper_activity` 93.068 righe 19 MB; `mike_activity` 14.931 / 7 MB; `safe_strategy_activity`
  4.034 / 3,5 MB; `live_ladder` 889 / 2,6 MB; `mike_trades` 1.127 / 1,1 MB; `safe_strategy_trades` 349 / 0,9 MB; `betfair_live_order_requests` 101 righe;
  `betfair_live_risk_rules` 14 righe (80 kB); tabelle `*_control`: 1-105 righe. Le tabelle lette dai bot ogni secondo stanno in pagine da kB.
- I contatori `n_tup_ins/upd/del` e `pg_stat_statements` ripartono da 07:28:19 UTC (riavvio): per le tabelle dei bot valgono 0; i dati disponibili sono di soli lavori batch
  (analytics): 47.485 chiamate totali in 5 h 16 min (~150/min), 153 statement distinti. Non c'e' una misura cloud-side delle richieste dei bot oggi.
- `n_live_tup` in `pg_stat_user_tables` vale 0 per quasi tutte le tabelle (statistiche azzerate dal riavvio): ho usato `reltuples`.
- Statistica utile per il piano: la tabella con piu' righe aggiornate e' `analytics_signals` (1,25 M righe, 730.319 UPDATE e 8.062 INSERT dal 07:28 UTC),
  non una tabella dei bot.

---

## Come rieseguire (tutto da `ARCHITETTURA_2026-10/strumenti/misure/`, con la `.venv`: `../../../.venv/Scripts/python.exe -I`)

| Misura | Comando | Durata |
|---|---|---|
| 1 per partita | `m01_feed_raw.py ../../../_live_raw` | 41 s |
| 1 per sport | `m01b_feed_per_sport.py ../../../_live_raw` | 34 s |
| 1e orologio | `m00b_ntp_offset.py` (5 pacchetti UDP/123 per server) | 5 s |
| 4 richieste DB | `m04_chiamate_db.py ../../../_logs <id_sessione>...` (es. `2026-10-08T06-03-49-625Z`) | 5 s |
| 5 risorse disco | `m05_risorse_disco.py ../../../_logs ../../../_live_raw` | 2 s |
| 5 risorse processi (app accesa) | `powershell -NoProfile -File m05b_campiona_processi.ps1 -Campioni 30 -Secondi 10` | 5 min |
| 6 persistenza | `m06_lab_persistenza.py tmp 3000 3` poi cancellare `tmp/` | 61 s |
| 2 e 4 laboratorio rete | `m07_lab_rete.py dqbwaocvlzbxfrpacsac.supabase.co` | 6 s |
| 7 cloud | le query in `uscite/m07_cloud_sola_lettura.txt` (solo SELECT) | secondi |
| 3 ordini (a ordini fatti) | `python -m Betfair.stream.tools.leggi_tempi_ordine <log>...` | secondi |

Per non gonfiare le misure: nessuno script importa codice dell'app (solo stdlib e `websockets` della `.venv`); `m07_lab_rete.py` apre un server
WebSocket su 127.0.0.1 per ~15 s nello stesso processo e fa 40 richieste senza chiave al gateway Supabase (risposta 401); `m00b_ntp_offset.py` apre socket UDP verso NTP.

## Cosa non ho potuto misurare, e perche'

1. **Eta' del feed in ricezione (`pt` contro orologio locale)**: il raw non registra la ricezione (`raw_listener.py:211`); il log di flumine non stampa il valore
   (`runner.py:3150`). Rimedio in sez. 2.4. L'orologio del PC e' sfasato di 844 ms (avanti) e il servizio Ora e' fermo.
2. **Feed del tennis**: nessun raw di tennis reale in `_live_raw` (solo `_synth_*`); il tennis non e' coperto da M1.
3. **Tempo messaggio -> canale -> bot sul canale vero**: nessun timestamp nei log (sez. 2.4); solo cadenza strutturale e laboratorio loopback.
4. **Ordini live (`placeOrders` -> risposta, cancel/replace reali, abbinamento)**: nessun ordine con `tempi_ordine` completo nei log; il cloud ha 1 richiesta live in tutta la
   storia e 4 ordini live del runner. I numeri di sez. 3.2 sono paper (orologi DB/PC) e non descrivono Betfair.
5. **Latenza HTTP per richiesta dell'app**: httpx non la scrive; misurati il giro di rete senza chiave e il tempo in Postgres a parte (sez. 4.3), non una query vera con la chiave
   (la chiave e' un segreto del `.env`: non l'ho letta).
6. **CPU e RAM dell'app e crescita nelle 24 ore**: app spenta; nessun log di risorse in alcun file. Pronto `m05b_campiona_processi.ps1`; serve un'ora di app accesa.
7. **Giorno intero**: la sessione piu' lunga nei log e' di 92 minuti: richieste/giorno solo come proiezione grezza (sez. 4.2).
8. **Cloud: richieste dei bot lato Postgres e n_tup_* della giornata**: azzerati dal riavvio delle 07:28 UTC (sez. 7); da rimisurare a bot accesi.
9. **Spegnimento del PC durante la scrittura** (durabilita' reale di NORMAL contro FULL e del log con/senza fsync): non provato, serve togliere corrente; riportate le fonti SQLite.
10. **Checkpoint di SQLite spostato fuori dal percorso critico**: non provato; il lab misura il default (checkpoint a 1.000 pagine, spike 0,70-0,96 s in NORMAL).
11. **Perche' Mike e' sceso da ~255 a ~48 richieste/min fra il 04/10 e il 06/10**: non verificato nel codice (non era nel perimetro).
12. **Causa dei buchi del feed (stream, registratore, mercato fermo)**: indistinguibili dal solo raw; vale il conteggio in-play come stima conservativa.
