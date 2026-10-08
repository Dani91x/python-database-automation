# SCHEDA COMPONENTE I - Desktop, processi e h24 (calcio + tennis)

Data: 08/10/2026. Autore: delegato Sonnet 5.5 (piano di architettura). Prefisso funzionalita': `I-`.
Solo lettura del codice e dei log in `_logs/`; nessun processo avviato, nessuna chiamata a Betfair/API-Football, nessun codice toccato.

## Perimetro (righe `wc -l`, file tracciati `git ls-files desktop`)

| File | Righe | Ruolo |
|---|---:|---|
| `desktop/main.js` | 951 | processo principale Electron: UI, supervisione dei figli, arresto, log, SSO web Betfair, finestre |
| `desktop/ambiente_runner.js` | 86 | ambiente dei runner Python (funzione pura) |
| `desktop/ambiente_runner.test.js` | 66 | test `node --test` della funzione pura |
| `desktop/bootstrap.js` | 56 | entry dell'exe: carica sempre il `main.js` vivo del repo |
| `desktop/preload.js` | 24 | passa il token dei canali locali alla pagina |
| `desktop/package.json` | 36 | `main: bootstrap.js` (`:6`), electron 33, electron-builder |
| `Betfair/stream/watchdog.py` | 337 | supervisore di UN figlio: classifica l'uscita, backoff, tetto riavvii |
| `Betfair/stream/avvio_app.py` | 336 | guardia «all'avvio dell'app nessun bot opera» (`APP_BOOT_ID`) |
| `Betfair/stream/single_instance.py` | 36 | lock di istanza = socket su `127.0.0.1:<porta>` |
| `Betfair/stream/arresto_ordinato.py` | 77 | file `ARRESTO` letto dai figli |
| `Betfair/stream/runner_lifecycle.py` | 291 | vita massima 18 h, stallo, codice 75 (parte condivisa dei due runner) |
| `Betfair/stream/backtest/worker.py` | 102 | worker del banco, figlio h24 sotto watchdog |
| `betfair_tennis_odds.py` | 322 | job «Partite del Giorno» tennis, lanciato ogni 30 min |
| `Betfair/safe_strategy/arresto_bot.py` | 198 | annullo ordini vivi di Safe/Omega all'arresto |
| Totale perimetro | 2.918 | (le righe dei servizi che il supervisore avvia sono nelle schede dei bot, non qui) |

Fonti gia' pronte e usate (non rifatte): `00_INVENTARIO.md` §5 (9 servizi sotto watchdog, 18 processi Python, lock 47311-47316/47318/47319, canali 47330-47338),
`07_MISURE_OGGI.md` (§0 righe 1e, 5b; §5.2 log; §6 persistenza; §4 richieste DB), `02_COMPETITOR.md` §3 (limiti API, sessione, keepAlive),
`A_CONNESSIONE_BETFAIR.md` (connessioni 10/10 `:72-92`, sessioni e keepAlive `§1.7`). Citate con il loro numero di sezione.

---

## 1. Oggi

### 1.1 Chi avvia e sorveglia cosa (letto dal codice)

Catena di avvio: exe -> `bootstrap.js:36-56` (`require` del `desktop/main.js` del repo) -> `app.whenReady` (`main.js:899`) ->
`resolveRepoRoot` (`:89`) -> `prepareChildLogs` (`:307`) -> `cancellaArrestoAllAvvio` (`:267`) -> `ensureFreshUi` (`:160`, puo' lanciare `npm run build`
con tetto 10 min, `:176-180`) -> `startStaticServer` (`:191`, 127.0.0.1:47330) -> `startRunners` (`:413`) -> `startBetfairWebSso` (`:759`) -> `createWindow` (`:886`).

Supervisione a DUE livelli, entrambi senza memoria condivisa:

| Livello | Chi | Cosa fa a un crash del figlio | Fonte |
|---|---|---|---|
| 1 | `watchdog.py` (uno per servizio: 9 processi) | riavvia il figlio con backoff 10-20-40-...-300 s, tetto 5 riavvii/ora, poi si ferma con alert CRITICAL | `watchdog.py:93-110, 222-328` |
| 2 | `desktop/main.js` sul watchdog | **niente**: `child.on('exit')` scrive una riga di log e toglie il figlio dal registro | `main.js:401-410` |

Il livello 2 non ha riavvio: se un watchdog esce (tetto riavvii esaurito `watchdog.py:318-322`, spawn fallito `:270-276`, uscita «clean» `:289-296`,
uscita «lock» `:307-312`) il servizio resta spento fino al riavvio dell'intera app. Nessuno controlla il watchdog.

### 1.2 Per ogni processo: cosa succede a un crash (codice alla mano)

Regole comuni del watchdog (`watchdog.py`): `classify_exit` (`:73-90`): rc=0 -> `clean` (il watchdog SI FERMA, alert INFO, `:289-296`);
rc=75 (`EXIT_PLANNED_RESTART`, `runner_lifecycle.py:72`) -> `planned` (riavvio immediato, non consuma il tetto, `:298-305`); rc!=0 con vita < 5 s
(`WATCHDOG_LOCK_GRACE_SEC`, `:251`) -> `lock` (il watchdog SI FERMA con alert WARN «Runner gia' attivo», `:307-312`); altro rc!=0 -> `crash`:
alert `CRITICAL` in `live_alerts` + Telegram (solo se `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in ambiente, `:158-177`), `sleep(backoff)`, riavvio (`:314-328`).
Il figlio e' lanciato senza `env` (`:270`): eredita ambiente, quindi stesso `APP_BOOT_ID` e stesso `LOCAL_CHANNEL_TOKEN` (`main.js:36-58`).
Il battito `watchdog_ts` e' scritto solo dal watchdog del runner calcio (`:122`, `:151`).

| Processo (label `main.js`) | Riga | Crash: riavvio? | Stato perso | Rischio ordini doppi / mancati | Fonti |
|---|---:|---|---|---|---|
| `runner-calcio` | :419 | si, backoff 10 s... tetto 5/h | blotter flumine in RAM; follow `STREAMING` in DB | Ripresa A6 prima del framework: specchio paper pulito, richieste `pending` > 120 s marcate `error`, guardia d'avvio armata finche' la ripresa non riesce (coda ordini ferma, solo cancel); le righe LIVE non si toccano, la ricostruzione dal conto e' del `reconcile_worker` (30 s). Motore ordini (se `MOTORE_ORDINI_CANALE=1`, spento di serie): ripresa dal diario con `listCurrentOrders` per `customerOrderRef` | `runner.py:2501-2530, 2688-2700, 2341-2345, 2453-2459`; `config_stream.py:332`; `runner.py:3000` |
| `runner-tennis` | :420 | si | blotter, 4 bot tennis ospitati | idem per il tennis (ripresa, riconciliazione col conto); i 4 bot tennis rileggono le loro righe | `tennis_runner.py:3473-3479`; Inventario §5.1 |
| `scalper-service` | :427 | si (dal 28/09) | mappa `children` dei figli; le sessioni-processo sopravvivono (gruppo di processi proprio) e vengono riagganciate dalla riga DB (`stopping zombie`, `alive`) | un figlio per partita: il supervisore riavviato non lo doppia (controllo `alive` prima dello `_spawn`) | `scalper_service.py:702-713, 814, 851, 922-974` |
| `tennis-bot-service` (ponte) | :437 | si | nessuno (ponte, solo lettura) | nessun ordine, nessun login | Inventario §5.1 |
| `safe-strategy-service` (scanner) | :443 | si | cache scanner, ripresa da immagine piena sui 4 stream | nessun ordine; alla ripartenza il feed unico manca per il tempo del backoff + riconnessione: Mike/Safe/Omega «ciechi» in quel intervallo | `A_CONNESSIONE_BETFAIR.md §1.7` (scanner: `create_stream` + immagine piena) |
| `omega-service` | :450 | si | ~28 dict/set globali di cache (§1.6) | ordini vivi riconciliati da `reconcile_pending` (`omega_service.py:4337`) | Inventario §5.1 |
| `safe-strategy-bot` | :456 | si | ~19 dict globali | `reconcile_pending` `bot_service.py:1117` | idem |
| `mike-service` | :461 | si | ~16 dict globali | `_reconcile_trades` `mike/service.py:5713` | idem |
| `backtest-worker` | :469 | si | richiesta in corso (la riga resta `RUNNING` nel DB: nessun codice di recupero in `worker.py:1-102`) | nessun ordine (banco simulato) | `worker.py:23-60` |
| `tennis-odds` | :480 | **no** (job breve, rilanciato dal timer) | niente | nessuno | `main.js:471-484` |

**Crash alla partenza (< 5 s).** `classify_exit` tratta ogni rc!=0 con vita sotto 5 s come «lock» (`watchdog.py:73-90`): un errore di import o di configurazione
che uccide il servizio subito (esempio costruito: `SyntaxError` dopo un deploy) fa FERMARE il watchdog con un alert di livello WARN anziche' CRITICAL e SENZA
riavvio; il servizio resta morto in silenzio fino al riavvio dell'app. Caso visto nei log: un servizio impiega ~13 s per partire (`_logs/backtest-worker_2026-10-08T06-03-49-625Z.log`:
spawn 06:03:50, «avvio» 06:04:03), quindi il caso < 5 s e' solo l'errore fulmineo. **Non provato dal vivo** (vietato avviare processi): e' una lettura del codice.

**Crash di Electron.** `killChildren` e l'arresto ordinato girano solo su `window-all-closed` (`:937`), `before-quit` (`:946`) e `process.on('exit')` (`:951`).
`grep` su `desktop/main.js` per `uncaughtException|render-process-gone|powerSaveBlocker|setLoginItemSettings|suspend` = 0 occorrenze: nessun gestore di
eccezioni, nessun recupero del renderer, nessun blocco della sospensione, nessun avvio automatico al login. Se il processo principale muore di colpo
(TerminateProcess, crash nativo) i watchdog e i servizi non sono legati a un oggetto Job di Windows (`spawn` senza `detached`/job, `:374-379`): restano vivi da
orfani, con lo stesso `APP_BOOT_ID`; un nuovo avvio dell'app trova i lock di porta occupati (`single_instance.py:18-36`), i nuovi watchdog escono con «lock» e
l'app nuova parla con servizi del vecchio avvio. Non provato.

### 1.3 Arresto ordinato (cosa succede quando l'utente chiude)

`window-all-closed` (`:937`) -> `shutdownAndQuit` (`:563`, idempotente) -> `orderedShutdown` (`:527`): scrive il file `ARRESTO`
(`<_live_raw>/_arresto/ARRESTO`, `:254-265`), aspetta ogni figlio in elenco per `shutdownGraceMs` (scalper 150 s, omega e safe-bot 45 s, gli altri 25 s, `:292-296`),
poi `taskkill /PID <pid> /T /F` sui rimasti (`killChildren`, `:489-501`), poi `app.exit(0)` (`:572`). `tennis-odds` e `backtest-worker` non sono attesi (`:279-282`).
Tempo massimo teorico di chiusura = max(150, 45, 25) = **150 s** (i figli sono attesi in parallelo, `Promise.all` `:538`).
Conseguenza per l'h24: **chiudere la finestra spegne l'intero sistema** (`:937-939`): la UI e i servizi di trading hanno lo stesso ciclo di vita.

### 1.4 Giorno nuovo (mezzanotte)

Non esiste un processo ne' un evento «di giornata»: ogni modulo calcola la giornata da se' a ogni giro.
- Stop giornaliero e P&L: `daily_stop_worker.py:424` `day = now_local.date().isoformat()` ad ogni tick, fuso pinnato a `Europe/Rome` (`:47-51`),
  finestra `day_window_utc` (`trading/daily_pnl.py:129`, usata anche da `reconcile_worker.py:495, 696`). Cambio di giorno = automatico, senza riavvio.
- Mike: `_DAILY_STOP_LOGGED` per giorno di Roma (`mike/service.py:54`). Omega: obiettivo giornaliero in `_DAILY_GOAL_WRITTEN` (`omega_service.py:5318`), tabella `omega_daily_goal` (`omega_db.py:1041`).
- Finestra «oggi» di Omega per il conto: `omega_market.today_window_utc(now, lookback_hours=12)` (`omega_market.py:257`): definizione di «oggi» DIVERSA dalla precedente (finestra mobile 12 h, non il giorno di Roma). Duplicazione di definizione, non verificato l'effetto.
- `betfair_tennis_odds.py:311` `dt.date.today()` [corretto dal verificatore 08/10: era 310] ad ogni run (data locale del PC, non Roma); ogni run cancella e riscrive le righe di `run_date=oggi` (docstring `:285-300`).
- Cosa richiede un riavvio: **niente di dichiarato**; ma due cose NON si resettano da sole: (a) i dict globali delle cache (§1.6) senza chiave di giorno; (b) i runner si ricambiano solo dopo 18 h di vita (`runner.py:1252`) e solo senza ordini vivi/regole armate (`:1267-1290`), quindi con posizioni aperte il ricambio slitta senza limite.
- **Riavvio dell'app = bot spenti**: `avvio_app.py:9-40,54-100` (`APP_BOOT_ID` nuovo -> `status='stopped'`, `mode='paper'`, uscite a manuale). Un riavvio notturno
  dell'app (fase 2 del piano) spegnerebbe anche i bot che l'utente aveva acceso: per regola dell'utente e' voluto, ma incompatibile con «h24 senza intervento».

### 1.5 Sessione Betfair e keepAlive per processo

Sessione .it: 20 minuti, prolungata solo da keepAlive/login (`02_COMPETITOR.md` §3.3; `auth.py:98-101` in `A_CONNESSIONE_BETFAIR.md §1.7`). Login limite: 100/min, ban 20 min (`02_COMPETITOR.md` §3.2).

| Processo | Sessione propria | keepAlive | Fonte |
|---|---|---|---|
| runner calcio | `APIClient` (custode) + `BetfairClient` JSON-RPC `rest` | custode 480 s (`runner.py:1319`) + ramo idle 480 s (`:2788-2806`) + flumine `keep_alive` 600 s; il `rest` NON ha ne' keepAlive ne' re-login (REPERTO, `A_CONNESSIONE_BETFAIR.md §1.7`, non provato dal vivo) | `runner.py:1319, 2618-2620` |
| runner tennis | custode | `tennis_runner.py:1583-1610` | idem |
| scanner | custode | 900 s (`safe_strategy/service.py:173, 551-555, 2984`) | idem |
| scalper (per sessione) | login proprio per partita | 600 s, thread `keepalive-<ev>` (`scalper_session.py:810-818, 1852-1859`) | idem |
| omega | sessione condivisa `odds_refresh.get_shared_client` | proattivo ~600 s (`omega_service.py:8522-8557, 8839-8855`) | `omega_market.py:140` |
| safe-bot, mike | stessa funzione `omega_market` (client condiviso del processo) | **nessuno**: `grep keep_alive` in `mike/service.py` e `safe_strategy/bot_service.py` = 0 righe; solo re-login REATTIVO su errore di sessione (`omega_market.py:76-130`: `call` e `call_mutating`) | `omega_market.py:81-110` |
| tennis-odds | `BetfairClient().login_cert()` ad ogni run (`betfair_tennis_odds.py:308`) | nessuno (vive pochi minuti) | **48 certlogin/giorno** (30 min `main.js:483`) |
| Electron (finestre Video/Stats) | login interattivo + fallback certlogin (`main.js:694-717, 647-680`) | 15 min (`:589, 796-805`), retry 30/60/120/300 s (`:590`) | sola navigazione, nessun ordine |

Quindi **non esiste una sessione condivisa**: le sessioni vive sono almeno 9 (due runner, scanner, omega, mike, safe-bot, scalper-service + N scalper + Electron) piu' i job brevi
(Inventario §5.3). Per mike e safe-bot il primo ordine dopo una pausa > 20 min passa dal ramo reattivo: `call_mutating` ritenta SOLO su errore di sessione esplicito
(`omega_market.py:92-108`, corretto per non duplicare ordini) ma l'ordine in quel momento ha gia' perso la prima chiamata (latenza = una richiesta fallita + login).
Misura: non esiste (nessun contatore di re-login per processo); strumento in §7.

### 1.6 Riconnessione dello stream e crescita di memoria

Riconnessione stream: tre politiche diverse (flumine `MarketStream.run` con backoff 2-60 s e `initialClk/clk`; riscrittura per i frammenti calcio `frammenti_mercato.py:185-226`;
scanner con `create_stream` e immagine piena `stream.py:407-460`): `A_CONNESSIONE_BETFAIR.md D1`. Stallo: 600 s di silenzio -> ricostruzione, hard-cap 1800 s, dopo 180 s di muto dopo la ricostruzione -> `exit 75`
(`runner.py:1330-1348, 1368-1424`), bloccato da ordini vivi/regole armate (`:1267`). Orologio: PC avanti di 844 ms e servizio Ora di Windows fermo (`07_MISURE_OGGI.md §0 1e`); buchi del feed > 5 s: 9,6 per ora in-play (`§0 1c`).

Memoria (analisi per grep sui servizi, **euristica**: conta i `dict/set` globali di modulo vuoti alla definizione e i tetti `len(...) >= N`; il consumo reale in MB non e' stato misurato perche' l'app era spenta, `07_MISURE_OGGI.md §5.1`):

| Servizio | Dict/set globali (`grep -cE "^_[A-Z_]+ ... = ({}|[]|dict()|set()|defaultdict)"`) | Tetti espliciti trovati | Senza alcuna rimozione trovata |
|---|---:|---|---|
| `omega_service.py` | 28 (`:104-8011`) | `_LAMBDA_CACHE` `:1291`, `_MINUTE_CACHE` 2000 `:1344`, `_EMPIRICAL_CACHE` 500 `:1372`, `_MARKET_FIT_CACHE` 4000 `:1765`, `_SKIP_SEEN` 5000 `:1868`, `_LEG_RETRY` 2000/5000 `:2162-2166`, `_ORDINI_PAPER_SIMULATI` 2000 `:4290`, `_REALLY_OVER_CACHE` 500 `:7659` | `_IDLE_STATS_AT`, `_EVENTS_REFRESH_AT`, `_BLIND_CYCLES` (chiave = evento/mercato: crescita lenta) |
| `mike/service.py` | 16 | `_RIPIEGO_REST_ULTIMO` 2000 `:1326` | `_MALFORMED_LOGGED` `:460,492`, `_SENZA_RUNNER_LOGGATO` `:1640,1677`, `_CONTO_LETTO_A` `:2951,3313`: solo inserimenti nel file |
| `safe_strategy/bot_service.py` | 19 | `_EVENT_NAMES` `:6554`, `_FLUSSO_ANNUNCIATO` 5000 `:9297` | non classificato |
| `runner.py`, `tennis_runner.py`, `scalper_service.py` | 0 globali del tipo cercato (lo stato e' nell'oggetto sessione) | 0-1 | stato di sessione: `finished_events`, `_timeline_ts` `runner.py:230` (per evento) |

Politica dominante dei tetti: `if len(X) >= N: X.clear()` (`omega_service.py:1372-1373, 1765-1766, 1868-1869`): svuota tutto invece di espellere i piu' vecchi; dopo lo svuotamento ogni chiave
si ricalcola insieme (picco di lavoro e, per `_EMPIRICAL_CACHE`/`_MINUTE_CACHE`, di letture dal DB cloud). **Nessun servizio tranne i due runner ha una vita massima**:
`grep -nE "MAX_UPTIME|vita massima|_MAX_HOURS"` su omega, mike, safe-bot, scanner, scalper-service, tennis-bot = 0 righe; i due runner si ricambiano a 18 h (`runner.py:1252`, `tennis_runner.py:2047`). I 6 servizi restano vivi per settimane senza ricambio igienico.

### 1.7 Log: chi scrive 1,1 GB e perche'

Percorso: ogni riga stdout/stderr di ogni figlio passa dal processo principale di Electron (`main.js:386-399`: `console.log` + `fs.createWriteStream` per figlio, append, un file per figlio
e PER AVVIO DELL'APP, `:229-232, 326-352`). Pulizia solo all'avvio dell'app: file `.log` piu' vecchi di 7 giorni per mtime (`:229, 307-322`). **Nessuna rotazione per dimensione e nessuna
pulizia mentre l'app e' accesa**; `RotatingFileHandler` esiste solo in `betfair_report_manager.py:6,35-42` (`07_MISURE_OGGI.md §5.2`).

Numeri (`07_MISURE_OGGI.md §5.2`, `m05_risorse_disco.py`): `_logs/` 1.428,1 MB in 197 file (21 sessioni dal 01/10 all'08/10); `backtest-worker` 1.138,1 MB (80%); senza di lui 290 MB in 8 giorni.

Mia misura sul file piu' grande, `_logs/backtest-worker_2026-10-08T06-03-49-625Z.log` (475.688.289 byte, 4.117.457 righe, dal 06:03:50Z al 07:21:57Z = 78 min, `awk` per logger):
| Logger | Righe | MB |
|---|---:|---:|
| `flumine.baseflumine` (INFO) | 4.115.389 | 453,3 (95%) |
| `httpx` (INFO) | 619 | 0,1 |
| tutto il resto | ~1.450 | <0,3 |

Le 4.115.389 righe sono 1.028.799 mercati x 4 messaggi identici («Removing market N», «Market level cleared», «Market closed», «Market cleared»; `sort | uniq -c`).
Causa: `worker.py:87-90` fa `logging.basicConfig(level=INFO)` (root a INFO), e flumine registra a INFO ogni rimozione di mercato (`.venv/Lib/site-packages/flumine/baseflumine.py:230`
`logger.info("Removing market %s", ...)`): durante il replay di una registrazione con migliaia di mercati il banco rimuove ~220 mercati/s (1.028.799 / 4.687 s) = ~880 righe/s, cioe' ~348 MB/h:
coincide con la stima 356 MB/h di `07_MISURE_OGGI.md §5.2`. Il worker gira SEMPRE (watchdog, h24) e, a riposo, interroga la coda `live_backtest_requests` ogni ~5,1 s (log: 06:04:05,113 / 10,228 / 15,341):
**~16.900 richieste/giorno** (86.400 / 5,11) al cloud e ~4,1 MB/giorno di log (`httpx`, media 246 B/riga su 604 righe misurate): poco per il disco, 11,7/min per le richieste.

Secondo fatto: nel log del runner calcio (`_logs/runner-calcio_2026-10-01T13-09-12-740Z.log`, 38,8 MB) 142.204 righe `INFO HTTP Request` (httpx, una per chiamata REST a Supabase) pesano 34,2 MB = **88% del file**.
Quelle righe sono ANCHE lo strumento di misura delle richieste al DB (`ARCHITETTURA_2026-10/strumenti/misure/m04_chiamate_db.py:1-8`: conta le righe `HTTP Request` di httpx): abbassare il livello di `httpx` senza prima avere i contatori
della fase 0 «Salute» cancellerebbe l'unica misura che oggi esiste. (Safe-bot e Mike: 14,2 e 13,7 MB di righe con formato diverso, non classificate.)

### 1.8 Finestre Video/Stats e login web (`main.js:759`)

`startBetfairWebSso` (`:759`; il brief cita `:756`, che e' la fine della funzione precedente) legge il `.env` (`:601`), fa login interattivo (token web pieno, il player video lo richiede, `:694-717`) con fallback `certlogin` (`:647-680`),
imposta il cookie `ssoid` su `.betfair.it` e `.betfair.com` (`:734-756`), poi `setInterval` 15 min: keepAlive su `identitysso.betfair.it` (`:718-732`), re-login se scaduto, retry con backoff 30/60/120/300 s (`:590`). Il primo click su 📺/📊 aspetta fino a 8 s l'esito del primo login (`:594, 836`).
Una finestra per `frameName` (`betfairWindows`, `:826-861`), link esterni al browser di sistema (`:863-884`). Costi: un login Betfair in piu' (login .it non interattivo = pesa sul limite 100/min solo all'avvio e dopo scadenza), credenziali e certificato letti dal `.env` nel processo UI (superficie di sicurezza in un processo che renderizza pagine web).

### 1.9 Dipendenze

In entrata: nessuno importa `main.js` (e' l'entry); `avvio_app.py` e' importato da `omega_service`, `mike/service`, `bot_service`, `scalper_service`, `tennis_bot_service` (Inventario §5.1). `watchdog.py` e' lanciato solo da `main.js` e dagli script `.bat` di radice.
In uscita: Electron -> Node `http/https/child_process/crypto/fs`; Python watchdog -> `db.insert_alert`, `db.upsert_live_heartbeat` (`watchdog.py:144-155`), Telegram opzionale.
Tabelle DB scritte dal livello processi: `live_alerts` (alert del watchdog, `watchdog.py:144`), `betfair_live_heartbeat` (battito watchdog, `:151`), righe `*_control` (guardia `avvio_app.py`).
Canali: lock su 8 porte e 8 canali WS (Inventario §5.4); file `ARRESTO`. Orologi: monotonic per backoff e tetto (`watchdog.py:93-110`), epoch per ARRESTO.

---

## 2. Funzionalita'

(Visibile in UI = la UI mostra l'effetto; parametro editabile = variabile d'ambiente o costante dichiarata.)

### Electron (`desktop/`)
- **I-001** Avviatore dell'exe: carica sempre il `main.js` vivo del repo, ripiega sul bundle se il repo non c'e' - `bootstrap.js:36-56`. Per l'utente: nessuna ricompilazione dell'exe.
- **I-002** Ricerca della radice del repo (env `ALPHASCORE_REPO`, cartella dell'exe, dev) e finestra d'errore se manca `.venv` - `main.js:82-105, 899-912`.
- **I-003** `APP_BOOT_ID` unico per avvio (impronta che fa spegnere i bot a un nuovo avvio) - `main.js:46`; uso in `avvio_app.py:54-100`.
- **I-004** `LOCAL_CHANNEL_TOKEN` (32 byte) per i comandi `order` dei canali 47331/47332; mai nei log - `main.js:61`, `preload.js:21`, `local_channel.py:65`.
- **I-005** `webPreferences` della UI con preload e token, riusate dalle finestre popout della UI - `main.js:67-80, 863-884`.
- **I-006** Ricostruzione automatica della UI (`npm run build`) se i sorgenti sono piu' nuovi della build; se fallisce serve la precedente con finestra d'errore - `main.js:140-189`.
- **I-007** Server HTTP statico su 127.0.0.1:47330 con fallback SPA e protezione dal path traversal - `main.js:191-232`.
- **I-008** Registro su file di ogni figlio (`_logs/<label>_<avvio>.log`, timestamp ISO, ritenzione 7 giorni all'avvio) - `main.js:229-352`.
- **I-009** `spawnRunner`: ambiente, pipe stdout/stderr, `windowsHide`, registro dei figli vivi, riga all'uscita - `main.js:353-411`.
- **I-010** Ambiente dei runner come funzione pura: cadenze (`LIVE_ORDER_QUEUE_POLL_SEC=0.15`, ladder 0.3 s, tennis 0.15 s), `LIVE_RUNNER_KEEP_ALIVE=1`, tetto ordini tennis (`TENNIS_LIVE_ORDER_MODE`), `PYTHONUNBUFFERED`, UTF-8 - `ambiente_runner.js:51-83`, test `ambiente_runner.test.js` (66 righe).
- **I-011** Avvio dei 9 servizi sotto watchdog nell'ordine runner-calcio, runner-tennis, scalper, ponte tennis, scanner, omega, safe-bot, mike, backtest-worker - `main.js:413-470`. Parametri non editabili (fissi nel codice).
- **I-012** Job tennis-odds all'avvio e ogni 30 min, mai sovrapposto - `main.js:471-484`.
- **I-013** `killChildren`: `taskkill /T /F` sull'albero dei figli vivi - `main.js:489-501`.
- **I-014** Arresto ordinato: file `ARRESTO`, attesa per figlio (`shutdownGraceMs`), log di chi e' uscito da solo, poi forzatura - `main.js:235-296, 504-561`.
- **I-015** Cancellazione di un `ARRESTO` rimasto da una chiusura precedente all'avvio - `main.js:267-269`.
- **I-016** Punto d'uscita unico idempotente (`window-all-closed`, `before-quit`, `process.on('exit')`) - `main.js:563-576, 937-951`.
- **I-017** Login web Betfair interattivo + fallback `certlogin` per le finestre Video/Stats - `main.js:647-717, 759-794`.
- **I-018** Cookie `ssoid` su betfair.it e betfair.com - `main.js:734-756`.
- **I-019** keepAlive web 15 min, re-login, retry con backoff 30/60/120/300 s - `main.js:589-594, 796-805`.
- **I-020** Finestre popout Betfair (una per nome, 640x780, attesa SSO max 8 s) - `main.js:826-861`. Visibili: bottoni 📺/📊 (`frontend/src/components` BetfairMediaButtons, citato in `main.js:808-815`).
- **I-021** Gestione `window.open`: rotte UI come finestre Electron con le stesse preferenze, host Betfair come popout loggato, altri link al browser di sistema - `main.js:863-884`.
- **I-022** Finestra principale 1600x900 su `/board` - `main.js:886-897`.
- **I-023** `preload.js`: espone alla pagina il token dei canali - `preload.js:1-24`.
- **I-024** Pacchetto exe (electron-builder, `bootstrap.js` come main) - `desktop/package.json:6-36`.

### Supervisione e ciclo di vita (Python)
- **I-030** Classificazione dell'uscita: clean / planned (75) / lock (< 5 s) / crash - `watchdog.py:73-90`. Parametro: `WATCHDOG_LOCK_GRACE_SEC`.
- **I-031** Backoff esponenziale 10 s -> 300 s - `watchdog.py:93-102`. Parametri: `WATCHDOG_BACKOFF_BASE_SEC`, `WATCHDOG_BACKOFF_CAP_SEC`.
- **I-032** Tetto riavvii/ora (finestra scorrevole) e arresto con «SERVE INTERVENTO MANUALE» - `watchdog.py:105-110, 314-322`. Parametro: `WATCHDOG_MAX_RESTARTS_PER_HOUR` (5).
- **I-033** Alert `CRITICAL` in `live_alerts` + messaggio Telegram con il nome del modulo - `watchdog.py:112-119, 144-177`. Visibile in UI come allarme live.
- **I-034** Battito del watchdog (30 s), solo per il runner calcio salvo `WATCHDOG_BATTITO` - `watchdog.py:122-141, 151, 283-286`.
- **I-035** Lock di istanza per socket (rilasciato dal sistema alla morte del processo) - `single_instance.py:18-36`; 8 porte.
- **I-036** Ricambio igienico a 18 h con codice 75 e riavvio immediato - `runner.py:1252, 1796-1801, 3160-3167`; `tennis_runner.py:2047, 2136, 3478`. Parametri: `LIVE_RUNNER_MAX_HOURS`, `TENNIS_RUNNER_MAX_HOURS`.
- **I-037** Uscita 75 per stream muto dopo la ricostruzione (blocco se ordini vivi) - `runner.py:1368-1424`; `tennis_runner.py:2169-2342`. Parametri: `LIVE_STALL_POST_REBUILD_SEC` (180), `LIVE_RAW_STALL_RESTART_SEC` (600), `LIVE_RAW_STALL_HARD_CAP_SEC` (1800).
- **I-038** Guardia di sicurezza di ogni spegnimento: ordini vivi e regole di rischio armate bloccano - `runner.py:1267-1303`.
- **I-039** Ripresa dopo crash del runner: pulizia specchio paper, richieste stantie, guardia d'avvio, diario del motore ordini - `runner.py:2501-2530, 2688-2700, 877-890`.
- **I-040** Uscita ordinata del runner: partite finite chiuse, le altre tornano `PENDING` per il processo successivo - `runner.py:906-950`.
- **I-041** Guardia «all'avvio dell'app nessun bot opera»: timbro `boot_id` in `stats`, fermata dei bot a un nuovo avvio, uscite a manuale - `avvio_app.py:54-336`.
- **I-042** File `ARRESTO`: cartella e percorso condivisi con `main.js` - `arresto_ordinato.py:1-77`.
- **I-043** Arresto di Safe e Omega con annullo degli ordini vivi (tetto 10 s) - `arresto_bot.py:27-34, 144-195`; Mike `mike/service.py:7299-7316`.
- **I-044** Supervisore scalper: un processo per partita in gruppo di processi proprio, battito, zombie - `scalper_service.py:702-713, 814-974`.
- **I-045** Worker del banco: coda `live_backtest_requests` ogni 5 s, «Applica bot» - `worker.py:1-102`. Parametro: `--poll-sec`, `--log-level`.
- **I-046** Job quote tennis (`tennis_markets`) con lock 47316 e login proprio - `betfair_tennis_odds.py:285-318`.
- **I-047** Stop giornaliero e riconciliazione col conto a cadenza, giornata di Roma - `daily_stop_worker.py:47-51, 424-435`; `reconcile_worker.py:495, 696, 1329`; `config_stream.py:332` (`LIVE_RECONCILE_POLL_SEC` 30 s).
- **I-048** keepAlive per processo (§1.5) - citato sopra, una voce per famiglia: `auth.py:156-286`, `omega_service.py:8541`, `scalper_session.py:810`, `tennis_runner.py:1583`, `safe_strategy/service.py:551`.

Totale: **48 voci** (I-001..I-024 Electron, I-030..I-048 Python). Parametri editabili in UI: nessuno nel perimetro (tutti env o costanti).

---

## 3. Difetti strutturali

| # | Difetto | Prova |
|---|---|---|
| D1 | **Nessun supervisore del supervisore.** Un watchdog fermo (tetto 5/h, «lock» a < 5 s, spawn fallito) lascia il servizio spento fino al riavvio dell'app; `main.js` registra solo `exit` | `main.js:401-410`; `watchdog.py:270-276, 307-312, 318-322` |
| D2 | **Crash fulmineo classificato come «lock»**: niente riavvio, alert WARN anziche' CRITICAL | `watchdog.py:73-90, 307-312` |
| D3 | **9 watchdog = 9 processi Python in piu'** che fanno la stessa cosa (stesso codice, stessa configurazione, 337 righe istanziate 9 volte), e battito scritto solo dal primo | `main.js:419-469`; `watchdog.py:122-141` |
| D4 | **UI e servizi di trading con lo stesso ciclo di vita**: chiudere la finestra = arresto di tutto, fino a 150 s | `main.js:937-939, 292-296` |
| D5 | **Tutti i log dei figli passano dal processo Electron** (stesso processo che serve la UI): ~880 righe/s dal worker del banco nel caso peggiore misurato (4.115.389 righe / 4.687 s) caricano il main di Electron; `WriteStream` senza gestione della contropressione (`ws.write` ignorato) | `main.js:386-399, 345-351` |
| D6 | **Log senza rotazione per dimensione**, pulizia solo all'avvio dell'app; 1.428 MB in 8 giorni, 80% dal worker del banco, per un `INFO` di flumine a 1.028.799 mercati | §1.7; `07_MISURE_OGGI.md §5.2` |
| D7 | **Il log di httpx e' sia 88% del volume sia l'unica misura delle richieste al DB** | §1.7; `m04_chiamate_db.py:1-8` |
| D8 | **Worker del banco acceso h24** dentro l'app di produzione: ~16.900 richieste/giorno al cloud a riposo; quando lavora esegue replay con codice di produzione sulla stessa macchina dei bot (CPU in competizione con lo stream; non misurata) | `worker.py:23`; log 06:04:05-06:04:15 |
| D9 | **Sessioni Betfair non condivise, tre famiglie di keepAlive, 48 certlogin/giorno da tennis-odds, nessun keepAlive per mike e safe-bot** | §1.5 |
| D10 | **Nessuna difesa «h24» a livello PC**: niente blocco della sospensione, niente avvio al login, servizio Ora di Windows fermo (+844 ms), nessun gestore di crash del renderer/processo principale; orfani se Electron muore | grep `main.js` = 0; `07_MISURE_OGGI.md §0 1e`; §1.2 |
| D11 | **6 servizi senza vita massima ne' limite di memoria**, cache svuotate in blocco (`clear()`), dict senza rimozione nel Mike | §1.6 |
| D12 | **Stato in piu' posti**: `APP_BOOT_ID` vive in `stats` di 5 tabelle di controllo (`avvio_app.py` docstring), il battito del watchdog in una sola riga condivisa, il file `ARRESTO` su disco, i lock su socket: quattro meccanismi di coordinamento fra processi | `avvio_app.py:9-40`; `watchdog.py:122`; `arresto_ordinato.py:1-77`; `single_instance.py` |
| D13 | **«Oggi» definito in tre modi** (giorno di Roma `daily_stop_worker.py:47`; finestra mobile 12 h `omega_market.py:257`; `date.today()` locale `betfair_tennis_odds.py:311` [corretto dal verificatore 08/10: era 310]) | citati |
| D14 | **Il job tennis-odds non e' sotto watchdog e non ha stato**: se fallisce il giro dopo 30 min e' l'unico riavvio; nessun alert | `main.js:471-484` |

Conteggi: `git grep -l "Europe/Rome" -- 'Betfair/*.py'` (esclusi test/tools) = 11 file che ridefiniscono la giornata; 8 porte di lock, 8 canali WS, 9 watchdog, 9 figli, 1 job breve.

---

## 4. Domani

### 4.1 Quanti processi servono davvero (con la motivazione)

Due costi diversi, che oggi si confondono:
1. **Connessioni stream Betfair** (limite 10 per app key, `frammenti_mercato.py:85`; caso peggiore del solo codice a regime LIVE = 3+1+1+1+4 = 10, `A_CONNESSIONE_BETFAIR.md:72-92`). Dipendono dagli **stream aperti**, non dal numero di processi: i bot (omega, safe-bot, mike, ponte) non aprono stream, leggono lo scanner dal canale 47336 e passano gli ordini dal runner (Inventario §5.4).
2. **Isolamento del guasto sui soldi**: un loop bloccato in un bot non deve fermare le protezioni degli altri. Questo dipende dal numero di processi.

Quindi i processi si contano per isolamento, le connessioni per stream (scheda A). Proposta, con calcolo:

| Processo domani | Perche' resta separato | Sostituisce |
|---|---|---|
| 1 `supervisore` (stdlib, ~420 righe) | unico punto che avvia/riavvia/arresta, vive oltre la UI | 9 watchdog + la logica di `main.js:229-575` |
| 2 `runner-calcio` | stream + ordini + flumine: crash/riavvio con ripresa dal conto | uguale |
| 3 `runner-tennis` | idem, 4 bot ospitati | uguale |
| 4 `scanner` | feed unico per tutti; i suoi 4 stream sono il costo maggiore di connessioni | uguale |
| 5 `mike` | bot indipendente (isolamento del guasto) | uguale |
| 6 `safe-bot` | idem | uguale |
| 7 `omega` | idem | uguale |
| 8 `scalper-service` (+ sessioni a richiesta) | una sessione per partita con stream propri: la sola ragione di aprire processi nuovi on demand | uguale |
| 9 `Electron UI` (solo finestra, server statico, SSO) | chiudibile senza spegnere i servizi | oggi 951 righe che fanno anche supervisione |

Fuori dal giro h24 (a richiesta o dentro un altro): `backtest-worker` -> lanciato dal supervisore solo quando c'e' una richiesta (oggi 16.900 SELECT/giorno a vuoto); `tennis-bot-service` (ponte `--bridge-only`, 1.183 righe, nessun login) -> da assorbire nel runner tennis o nello scanner (decisione utente, vedi sotto);
`tennis-odds` -> thread periodico dello scanner (che gia' interroga il tennis) con sessione unica (-48 certlogin/giorno) o job del supervisore con sessione riusata. Risultato: da **18 processi Python permanenti + 1 job ogni 30 min** a **8 processi Python permanenti** (-10), senza toccare nessuna strategia.
Calcolo: 9 watchdog + 9 figli = 18 (`main.js:419-469`; `backtest-worker` conta fra i figli) -> supervisore 1 + 7 servizi = 8 (+ scalper on demand come oggi). Non propongo di fondere mike/safe-bot/omega in un processo: 8.936 + 11.136 + 7.551 righe con ~63 dict globali di cache condividerebbero un GIL e perderebbero l'isolamento, per un risparmio di RAM non misurato (cifra per processo: 75,8 MB di un python non attribuibile, `07_MISURE_OGGI.md §5.1` - non utilizzabile come stima).

### 4.2 Supervisore unico

Contratto (Python, solo libreria standard):
```python
@dataclass(frozen=True)
class Servizio:
    nome: str                      # 'runner-calcio'
    modulo: str                    # 'Betfair.stream.runner'
    argv: tuple[str, ...] = ()
    lock_porta: int | None = None
    arresto_s: float = 25.0        # tempo massimo dichiarato (oggi shutdownGraceMs)
    a_richiesta: bool = False      # backtest-worker
    battito_tabella: str | None = None

class Supervisore:
    def avvia(self, servizi: list[Servizio]) -> None
    def stato(self) -> dict[str, StatoServizio]      # pid, uptime, riavvii/h, ultimo rc, esito
    def arresto_ordinato(self, nome: str | None) -> dict[str, EsitoArresto]
    def riavvia(self, nome: str, *, solo_se_flat: bool = True) -> bool
# eventi: servizio_caduto(nome, rc, uptime), servizio_riavviato(nome, n), tetto_esaurito(nome)
```
Regole prese dal codice di oggi (non cambiano): `classify_exit` e `next_backoff` (pure, `watchdog.py:73-102`) restano IDENTICHE; il tetto 5 riavvii/ora resta (`:105`);
l'arresto usa lo stesso file `ARRESTO` e gli stessi tempi (`main.js:292-296`); l'ambiente resta `costruisciEnvRunner` portato in Python (`ambiente_runner.js:51-83`) con lo stesso test di contratto.
Correzioni (non toccano la strategia): (a) il supervisore NON ferma mai un servizio per «tetto esaurito» senza alert e senza ritentare ogni 15 min con alert CRITICAL ripetuto; (b) l'uscita rapida con rc != 0 si distingue dal lock leggendo l'errore di `bind` (porta occupata) invece del tempo: se il lock e' libero e il servizio e' morto in < 5 s e' un crash; (c) nessun orfano: oggetto Job di Windows (`CREATE_BREAKAWAY_FROM_JOB` no, `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` si) o file di pid; (d) un solo battito del supervisore, la UI lo legge.

Il supervisore e' a sua volta sorvegliato da un secondo livello minimo: Electron lo rilancia se esce e Windows lo avvia al login (pianificazione attivita'): e' quello che oggi manca (`main.js:401-410`).

### 4.3 Riavvio senza perdita

Regola da rendere comune (oggi vale solo per il runner calcio, `runner.py:2501-2530`): **prima di decidere si ricostruisce**: archivio locale (posizioni, ordini in volo con `customerOrderRef`, diario write-ahead con fsync: provato 0 persi su 500, `07_MISURE_OGGI.md §6.1`) + `listCurrentOrders`/`listClearedOrders` di Betfair; finche' la ricostruzione non e' completa il servizio puo' solo annullare (come la guardia d'avvio `runner.py:2688-2700`). Per i bot oggi la ricostruzione dal DB cloud e' lenta (cloud: p50 21,3 ms su connessione calda, ma 11 chiamate di partenza in sequenza: non misurato) e dipende dalla rete; l'archivio locale (SQLite WAL o diario) la rende indipendente dal cloud: decisione e numeri nel piano generale (§6 di `07_MISURE_OGGI.md`), qui e' il requisito: **un servizio killato con posizioni aperte riparte, ricostruisce e non emette ordini doppi** (prova obbligatoria del piano, fase 1 blocco 1).

### 4.4 Ciclo della giornata h24

| Ora (Roma) | Evento | Chi | Senza riavvio |
|---|---|---|---|
| continuo | feed calcio e tennis, stallo -> ricostruzione | runner, scanner | si |
| 00:00 | cambio giornata: stop giornaliero, obiettivo, P&L, finestre conto, chiavi di cache per giorno | `daily_stop_worker`, `reconcile_worker`, bot | si (gia' oggi per il P&L; da portare uguale a Omega/tennis-odds, una sola funzione `giornata()` condivisa invece di 3 definizioni) |
| notte, finestra senza partite in corso | regolamento notturno: `listClearedOrders` contro le righe chiuse, chiusura follow, compattazione log, ricambio igienico dei servizi **solo se flat** (nessun ordine vivo, nessuna regola armata: `runner.py:1267`) | supervisore + `reconcile_worker` | si, con `riavvia(solo_se_flat=True)` |
| ogni 30 s | riconciliazione col conto (esiste: `RECONCILE_POLL_SEC`) | `reconcile_worker.py:1329` | si |
| ogni 18 h | ricambio igienico (esiste per i due runner, manca per gli altri 5 servizi) | supervisore | si |
| mattina | prossime partite: sottoscrizione a caldo | scanner/runner | si |

Il ricambio igienico dei servizi senza vita massima non cambia nessuna decisione: e' lo stesso meccanismo di `runner.py:1796-1801` esteso, con la stessa guardia dei soldi.

### 4.5 Limiti API rispettati

- Stream: max 10 connessioni (`frammenti_mercato.py:85`), riserva 1 (`:90`); oggi protegge solo il calcio. Il supervisore deve leggere `connectionsAvailable` (`02_COMPETITOR.md §3.1`) e rifiutare di avviare una sessione scalper se non c'e' margine (oggi la riserva e' fissa e solo nel codice calcio).
- Login: 100/min con ban di 20 min (`02_COMPETITOR.md §3.2`): con 9 servizi + 48 job/giorno siamo lontani (9 login all'avvio), ma una tempesta di riavvii (9 watchdog x 5/h = 45/h) non lo supera; il supervisore deve avere un tetto GLOBALE di login/minuto oggi inesistente.
- keepAlive: una famiglia sola (custode, `auth.py:156-286`) per tutti i processi, periodo < 20 min per .it (480-900 s oggi).
- REST: `TOO_MANY_REQUESTS` a 3 richieste concorrenti su `listCurrentOrders`/`listMarketBook` con proiezione ordini, per CONTO non per sessione (`02_COMPETITOR.md §3.2`): i processi che oggi chiamano in parallelo (runner x2, omega, mike, safe-bot) si contendono questo tetto: va contato, non ora assegnato (non misurato).

### 4.6 Struttura (una cartella per componente)

```
supervisore/             COSA_FA.md, contratto.py (Servizio, Supervisore), registro.py (9 -> 8 servizi), ambiente.py, arresto.py, log.py (rotazione), salute.py (battito, risorse)
desktop/                 COSA_FA.md, main.js (finestra, server statico, SSO, popout, avvio supervisore), preload.js
  tests_contratto/       ambiente (da node a pytest), classify_exit, backoff, tetto, arresto
```
Per sostituire il supervisore DOMANI tocco solo `supervisore/` e i suoi test; OGGI tocco `desktop/main.js` (951), `ambiente_runner.js` (86), `Betfair/stream/watchdog.py` (337), `avvio_app.py` (336, solo il tempo di vita del boot id), e le righe di avvio in 8 servizi (`single_instance.py`, `arresto_ordinato.py`): >= 12 file.

### 4.7 Stima delle righe

| | Oggi | Domani | Calcolo |
|---|---:|---:|---|
| `desktop/main.js` | 951 | ~330 | tengono: UI+server 99 (`:191-232` 42 + `:886-897` 12 + `:899-935` 37 + preferenze 14), SSO 207 (`:589-805`), popout 59 (`:826-884`), bootstrap lancio supervisore ~25 = ~390 meno commenti ridondanti (~60) |
| (di cui in `main.js`: supervisione, log, arresto) | ~344 (`:229-352` 124, `:353-484` 132, `:489-576` 88), GIA' comprese nelle 951 | 0 | passano al supervisore |
| `ambiente_runner.js` + test | 152 | 0 (poi in Python) | spostati |
| `watchdog.py` | 337 | 0 | assorbito |
| `supervisore/` | 0 | ~420 | `classify/backoff/tetto` 60 (riuso identico) + loop multi-figlio 150 + arresto 70 + log con rotazione 60 + ambiente 40 + salute 40 |
| test di contratto supervisore | 66 (`ambiente_runner.test.js`) | ~250 | classify, backoff, tetto, arresto, orfani, rotazione |
| **Totale perimetro** (main.js + ambiente_runner.js + watchdog.py = 951 + 86 + 337) | **1.374 + 66 test = 1.440** | **~330 + ~420 = ~750 + ~250 test = ~1.000** | -45% al netto dei test (750 contro 1.374), -31% con i test; il file piu' grande scende da 951 a ~330 |

Cio' che resta perche' e' strategia o contratto: nulla del perimetro e' strategia; `avvio_app.py` (336), `single_instance.py` (36), `arresto_ordinato.py` (77), `runner_lifecycle.py` (291) restano (sono libreria dei servizi).

Gia' in una libreria matura e riscritto oggi: backoff esponenziale (`watchdog.py:93-102`; `betfairlightweight` ha `wait_exponential` via `tenacity` nello stream, `A_CONNESSIONE_BETFAIR.md D1`), riconnessione stream e keepAlive (flumine `worker.py:99-116`), rotazione dei log (`logging.handlers.RotatingFileHandler` della libreria standard Python: oggi usato in 1 file). Per la supervisione di processi generica esistono strumenti esterni (NSSM, servizi Windows): non valutati qui, fuori perimetro; il supervisore proposto e' deliberatamente piccolo per poter essere letto per intero.

---

## 5. Parita'

Il perimetro non contiene decisioni di trading: la parita' e' di CONDOTTA e di NUMERI DI VITA, non di ordini.

| Prova | Cosa deve coincidere | Come |
|---|---|---|
| Test di contratto Python sulle funzioni pure `classify_exit`, `next_backoff`, `should_restart`, `messaggio_crash` | stessi valori di oggi per gli stessi ingressi (tabella con 5 rc x 4 uptime) | portare i test di `watchdog` esistenti, falsificare cambiando `lock_grace_sec` |
| `ambiente_runner.test.js` portato in Python | stesso dizionario d'ambiente (chiavi e valori) per gli stessi `processEnv`/`.env` | confronto chiave per chiave contro l'uscita del JS |
| Scenario di arresto | stessi tempi massimi (`shutdownGraceMs`), stessi figli attesi, `ARRESTO` scritto una volta | test con figli finti con chiavi identiche al vero |
| Scenario «crash con posizioni aperte» (kill del runner paper) | stessi ordini dopo la ripresa, 0 doppi | banco comune `python -m Betfair.stream.backtest.certifica <bot> ...` scenario `riavvio` (`scalper_service.py:659`: scenario S7 del banco) |
| Fotografie UI | pagina Board e Control Room identiche prima/dopo (nessun cambio UI nel perimetro) | `frontend` invariato |
| Referto numerico a 24 h (stessa macchina) | stesse partite seguite, stessi bot accesi, stesse allarmi | strumento della fase 0 «Salute» |

Voci di `PROCESSO_STANDARD_BOT.md` coperte: §6 «concorrenza» e «ciclo di vita dell'ordine» (riavvio con ordini in volo), «persistenza e UI» (stato dopo il riavvio), «falsificazione» (ogni test nuovo rosso se tolgo la regola), «referto riproducibile»; §7 il catalogo degli errori sui riavvii e sulla sessione scaduta (i numeri esatti dei 35 errori non sono stati riletti in questa scheda: **da incrociare dal coordinatore**, non ho il testo di §7 davanti).

---

## 6. Migrazione

1. **Ombra, senza spegnere nulla**: `supervisore/` parte in sola osservazione (legge pid e stato dei 9 watchdog senza gestirli) e scrive il confronto con la realta' per 24 ore. Interruttore: variabile `SUPERVISORE_ATTIVO=0` (default).
2. **Log** (indipendente e a rischio zero): rotazione per dimensione e livello `flumine`/`httpx` -> `WARNING` nel solo `backtest-worker` (nessuna logica toccata); PRIMA i contatori della fase 0 devono esistere, altrimenti `m04_chiamate_db.py` perde la fonte (D7). Ritorno: ripristinare il livello.
3. **Worker del banco a richiesta**: il supervisore lo lancia quando `live_backtest_requests` ha una riga `PENDING` (un solo controllo ogni 30 s dal supervisore invece di 5 s dal worker). Richiede permesso: «nessun processo nuovo senza permesso».
4. **Taglio dei watchdog**: un servizio alla volta, a partire da `backtest-worker` (nessun ordine), poi scanner, poi i bot senza posizioni aperte, per ultimi i due runner (con il runner calcio in finestra senza posizioni). Per ogni passo: replay di tutti i bot identici, referto di 24 h uguale o migliore. Ritorno: reinserire il `spawnRunner` nel `main.js` (resta nel repo fino al taglio finale).
5. **UI separata dai servizi**: `window-all-closed` smette di spegnere il supervisore (decisione utente, vedi sotto).
6. **Hardening h24 del PC**: blocco della sospensione, avvio al login, servizio Ora di Windows (decisioni utente).

Rischi: il supervisore unico e' un punto singolo (mitigato dal secondo livello, §4.2); il comportamento «riavvio dell'app = bot spenti» cambia se il supervisore sopravvive (decisione); nessuna prova dal vivo e' consentita in questa fase.

---

## 7. Misure

Numeri di oggi con fonte, obiettivi PROPOSTI (non fatti: sono target da confermare dopo una baseline di 24 h) e strumento.

| Misura | Oggi | Obiettivo 24 h | Strumento |
|---|---|---|---|
| Processi Python permanenti | 18 (9 watchdog + 9 figli, `00_INVENTARIO.md §5.1`) + 1 job/30 min | 8 | `Get-Process` / `m05b_campiona_processi.ps1 -Campioni 30 -Secondi 10` (esiste, mai lanciato: app spenta) |
| Riavvii NON pianificati / 24 h | non misurati (nessun contatore; alert in `live_alerts`) | 0, alert CRITICAL per ognuno | fase 0: `monitor_metrics` riga ogni 30 s per servizio (`PIANO_OTTIMIZZAZIONE_GLOBALE_2026-10-02.md` Fase 0) |
| Riavvii pianificati (75) | 2 runner x 24/18 = 2,7/giorno (calcolo da `runner.py:1252`) | 2,7 + 5 servizi x 1,3 = 9,3, tutti con posizioni flat | contatore `rc=75` nel supervisore |
| CPU media (% di un core, 8 thread, Ryzen 7 3750H) | non misurata (app spenta, `07 §5.1`) | da fissare dopo baseline; target provvisorio: app totale <= 100% di un core mediano, nessun servizio > 30% p95 a riposo | `m05b_campiona_processi.ps1`, poi `psutil` in fase 0 |
| RAM (working set per processo) | non misurata | crescita <= 5% fra la 2a e la 24a ora per ogni servizio; totale app <= 25% dei 15,8 GB (target provvisorio) | idem + `monitor_metrics.rss` |
| Richieste al cloud / giorno | 707,5/min (08/10) = 1.018.800/giorno; 1.309/min (04/10, stream attivo) = 1.884.960/giorno (`07 §0 4a`, calcolo x1.440) | dal piano dei dati (schede dei bot); in questo perimetro: `backtest-worker` a riposo da 16.900 a 0 | `m04_chiamate_db.py`; poi contatore per servizio in fase 0 |
| Log / giorno | 94, 28, 80, 58, 15, 14 MB nei giorni senza backtest-worker; con backtest-worker fino a 468 MB (08/10) (`07 §0 5b`) | <= 50 MB/giorno totale a riposo, <= 5 MB per job del banco, nessun file > 100 MB | `m05_risorse_disco.py` + dimensione di `_logs/` nel referto giornaliero |
| Log del banco | 348 MB/h durante un replay (mia misura, §1.7) | <= 1 MB per replay (livello WARNING di flumine) | `awk` sul file, stesso conteggio |
| Re-login Betfair / giorno | non misurati; tennis-odds 48 certlogin (`main.js:483`) | <= 1 per servizio ogni 12 h, 0 da tennis-odds | contatore in `auth.py` (fase 0) |
| Eta' del feed per partita con soldi | buchi >5 s: 9,6 per ora in-play (`07 §0 1c`) | misura di partenza, nessun peggioramento | `m01b_feed_per_sport.py` |
| Scarto orologio PC | +844 ms, w32time fermo (`07 §0 1e`) | <= 100 ms, controllo orario del supervisore | `m00b_ntp_offset.py` |

---

## Decisioni per l'utente

1. **UI separata dai servizi**: oggi chiudere la finestra spegne tutto (`main.js:937`). Per l'h24 la finestra dovrebbe nascondersi in tray e i servizi restare vivi. Cambia pero' il significato di «riavvio dell'app = bot spenti» (`avvio_app.py`): proposta: l'`APP_BOOT_ID` nasce all'avvio del SUPERVISORE (non della finestra) e un pulsante esplicito «Ferma tutto e riparti da zero» lo rinnova. Serve la tua decisione perche' tocca «all'avvio nessun bot opera».
2. **Blocco della sospensione, avvio al login e servizio Ora di Windows** (richiede privilegi di amministratore per w32time): senza questi l'h24 dipende dal PC acceso e sveglio. Nessuno e' presente oggi nel codice.
3. **`backtest-worker` a richiesta** invece che sempre acceso (processo con regola «nessun processo nuovo senza permesso»: qui si toglie un ciclo, non se ne aggiunge, ma cambia chi lo lancia).
4. **Assorbire `tennis-bot-service` (ponte) e `tennis-odds`** dentro runner tennis/scanner: -2 processi, -48 login/giorno; richiede un lavoro di integrazione sui componenti dei bot tennis (altre schede).
5. **Livello di log di flumine/httpx** (WARNING): prima va fatta la fase 0 «Salute» altrimenti si perde l'unica misura delle richieste al DB.
6. **Riavvio notturno**: si fa solo con tutti i servizi flat (nessun ordine vivo, nessuna regola armata, stessa guardia di `runner.py:1267`)? E' compatibile con la regola «mai con posizioni aperte» del piano, ma richiede conferma per i bot paper con posizioni simulate aperte.

---

## Cosa ho verificato di persona / cosa non ho potuto verificare

**Verificato leggendo il codice e i log** (comandi: `sed -n`, `grep -n`, `awk` sui log, `wc -l`, `git ls-files`): flusso di avvio e di arresto di `main.js`, classificazione e backoff di `watchdog.py`, assenza di riavvio dei watchdog in `main.js:401-410`, assenza di gestori di crash/sospensione/avvio al login (0 occorrenze), vita massima 18 h solo nei due runner, ripresa del runner calcio, lock di istanza, composizione del log del worker del banco (4.115.389 righe di `flumine.baseflumine` su 4.117.457; 1.028.799 mercati), 88% di righe `httpx` nel log del runner calcio, cadenza di 5,1 s del poll del worker, assenza di keepAlive in mike e safe-bot, elenco dei dict globali con i tetti trovati.

**Non verificato**:
- CPU e RAM dei processi: l'app era spenta (`07_MISURE_OGGI.md §5.1`); nessuna cifra mia.
- Il comportamento dal vivo di un crash con posizioni aperte, di un crash di Electron con orfani, del crash fulmineo (< 5 s) e della sessione `rest` del runner calcio dopo 20 min: lettura del codice, non provati (vietato avviare processi/chiamare Betfair).
- Se Telegram e' configurato nel `.env` (non letto): senza, gli alert CRITICAL restano solo in `live_alerts`.
- L'analisi dei dict globali e' per `grep` (euristica): i conteggi di «rimozioni» possono sottostimare le espulsioni scritte con altri nomi; non ho misurato crescita di memoria.
- Mike/Safe-bot: 14,2 e 13,7 MB di righe di log di formato diverso non classificate.
- I numeri dei 35 errori di `PROCESSO_STANDARD_BOT.md §7` non sono stati riletti qui: la sezione Parita' li cita per categoria, non per numero.
- API Electron `powerSaveBlocker` e Job Object di Windows come rimedi: non verificati su fonte pubblica in questa sessione (nessuna ricerca web eseguita).
