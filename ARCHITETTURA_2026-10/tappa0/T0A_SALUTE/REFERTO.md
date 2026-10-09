# T0A - Modulo "Salute": referto del delegato (cloud, 09/10/2026)

Mandato: `ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md` par. 1 T0A (con le "Misure aggiunte" della revisione critica
dell'08/10), solo la parte del cloud. Ramo `tappa0-salute` da `0aa76dfa` (commit del coordinatore), NON pushato:
`e44032a9` (Python, migrazione, test), `6d02e578` (pagina e fotografie), poi questo referto.
Ambiente: cloud (niente DB vero, niente app, nessuna registrazione tennis). Python 3.13, flumine 2.13.11,
betfairlightweight 2.23.2, psutil 7.2.2 (gia' in `requirements.txt`: nessuna dipendenza aggiunta).

## 1. Che cosa c'e'

| Pezzo | File |
|---|---|
| Interruttore, agganci, handler di log | `Betfair/monitor/sonde.py` |
| Contatori in memoria, istogrammi a secchi fissi (sommabili fra finestre e processi) | `Betfair/monitor/registro.py` |
| CPU/RAM/thread/handle (psutil; senza: os.times + /proc, dichiarato nella riga), versioni, Windows | `Betfair/monitor/processo.py` |
| Thread `monitor-salute`: una riga ogni 30 s -> `monitor_metrics` + copia locale `_logs/monitor/<giorno>/<servizio>.jsonl` | `Betfair/monitor/scrittore.py` |
| Referto giornaliero riproducibile -> `AUDIT_MONITOR/REFERTO_SALUTE_<giorno>.md/.json` | `Betfair/monitor/referto.py` |
| Scheda del componente (schema 04 par. 2.4) | `Betfair/monitor/COSA_FA.md` |
| Migrazione (la applica l'utente): tabella + RLS owner-only + 3 RPC | `migrations/monitor_metrics_2026-10-09.sql` |
| Pagina "Salute" (design system: PageShell, KpiRow/StatTile, SectionCard, EmptyState) + voce di menu' | `frontend/src/pages/Salute.tsx`, `frontend/src/lib/salute.ts`, `frontend/src/App.tsx`, `frontend/src/components/shell/navigazione.ts` |
| Test | `Betfair/monitor/tests/*` (3 file + conftest), `frontend/src/lib/salute.test.ts`, `frontend/src/pages/Salute.test.tsx`, `frontend/src/components/shell/navigazione.salute.test.ts`; aggiornati `AppShell.test.tsx`, `fotografia.test.tsx` (+ fotografie) |
| Ambiente neutro dei test (`MONITOR_SALUTE=0` in ogni test) | `Betfair/conftest.py` (fixture `_monitor_salute_spento`, in coda) |

Interruttore `MONITOR_SALUTE=0|1`, DI SERIE 0. Acceso solo se `=1` E il `main` del servizio chiama `_mon.avvia(...)` E nel
processo non e' caricato il banco (`Betfair.stream.backtest*`) E non gira pytest. Spento: ogni aggancio e' un `if _mon.ATTIVO`
falso -> nessun campo, nessuna scrittura, nessun thread, nessun handler di log. Nel banco e' spento PER COSTRUZIONE due volte:
il banco non chiama mai un `main` di servizio (verificato: `grep "\.main("` fuori dai test = 0), e `avvia` rifiuta se un
modulo del banco e' caricato. `MONITOR_SALUTE_SEC` cambia l'intervallo (30 di serie).

## 2. Gli agganci (file:riga sul commit consegnato) e cosa misurano

Tutti ADDITIVI e sotto `if _mon.ATTIVO`. Le marche nessuno le legge per decidere (solo `tempi_ordine.py` legge `emesso_ms`,
che e' una misura: F0, `_CHIAVI_DECISIONE`).

| Aggancio | file:riga | Cosa misura | Tratta |
|---|---|---|---|
| `rx` nel raw registrato | `Betfair/stream/raw_listener.py:156` (marca), `:217-218` (campo) | istante di ricezione locale su ogni riga del raw: `rx - pt` per partita, offline | L1 |
| messaggi, `rx - pt`, status/`connectionsAvailable` (anche lo 0) - calcio | `Betfair/stream/raw_listener.py:315-316` | conteggio mcm, istogramma `feed_rx_pt_ms.calcio`, minimo = limite superiore dello scarto dell'orologio | L1, L19 |
| idem scanner | `Betfair/safe_strategy/stream.py:155-156` | `connectionsAvailable` dello scanner (A D7) | L1 |
| idem tennis | `Betfair/stream/tennis_live/tennis_recorder.py:455-456` | `connectionsAvailable` del tennis | L1 |
| idem scalper (ripiego dal log) | handler su `betfairlightweight.streaming.listener` (`sonde.py`, `_GestoreStatoStream`) | `connectionsAvailable` delle sessioni scalper (flumine di serie, nessun listener nostro): lo 0 NON e' salvabile da qui (betfairlightweight lo scarta), dichiarato | - |
| `ts_pub_ms` + `pt` nel ladder del CANALE | `Betfair/stream/runner.py:750` | eta' del dato alla pubblicazione: `ladder_pub_pt_ms`. La riga di `live_ladder` resta identica (copia solo per il canale: un campo in piu' avrebbe rotto l'upsert) | L3 |
| `ricevuto_ms` del canale | `Betfair/stream/local_channel.py:198` (campo, di serie 0), `:453` (marca), `:724-725` (drenaggio) | attesa in coda arrivo -> drenaggio del worker: `canale_coda_ms` | L6 |
| `emesso_ms` nei `params` di Omega | `Betfair/omega/omega_service.py:3593-3596` | istante d'emissione del bot -> `tempi_ordine` calcola `decisione_ms` | L6 |
| `emesso_ms` nei `params` di Safe | `Betfair/safe_strategy/execution.py:1813-1816` | idem | L6 |
| marca prima/dopo il fsync del diario | `Betfair/stream/motore_ordini.py:1470-1477` | `diario_fsync_ms` (flush + fsync prima di ogni `place_order`) | L6b |
| client DB (supabase-py, per thread) | `db_client.py:110,114-123` | richieste PostgREST per metodo e tabella/RPC, errori HTTP, tempo alla risposta (`db_ms`) | L17 |
| client DB del tennis | `Betfair/stream/tennis_live/tennis_db.py:60-61` | idem | L17 |
| APIClient Betfair (sessione requests) | `Betfair/stream/auth.py:69-71` | certlogin, keepAlive, metodi JSON-RPC (listMarketBook, ...), tempi per metodo | L18 (re-login) |
| latency di flumine oggi persa | handler su `flumine.baseflumine` (`sonde.py`, `_GestoreLatenzaFlumine`) | i book con latenza > 2 s: valore che il formato del log (`runner.py:3246`) non stampava | L1 |
| esecuzione e transazioni | handler su `flumine.execution` (`_GestoreEsecuzione`) | `execute_place/replace/cancel` con `elapsed_time` (L7, Betfair vero), PAPER e LIVE in gruppi separati (dal logger: `betfairexecution` vs simulata), transazioni = place+replace+fallite SOLO sul Betfair vero; il referto le somma per ora su TUTTI i processi (il limite e' del conto) | L7, R13 |
| (ri)connessioni dello stream | handler su `flumine.streams` | "Starting MarketStream/OrderStream" | L18 |
| errori di log | handler di radice, livello ERROR | ERROR/CRITICAL per logger | - |
| processo e sistema | `processo.py` (thread dello scrittore) | CPU % di un core, RSS, VMS, thread, handle (Windows)/fd, CPU e RAM di sistema, disco libero; ogni 10 min versioni (Python, flumine, betfairlightweight, supabase, postgrest, httpx, requests, websockets, psutil, python-dotenv), registro di Windows in SOLA LETTURA (servizio W32Time Start/Type, ore attive e pausa di Windows Update, riavvio pendente) | L15, L16, L19, R14 |
| avvio per servizio | `runner.py:3256` (+ `ferma` `:3261`), `tennis_runner.py:3557` (+ `:3559`), `tennis_bot_service.py:1140`, `scalper_service.py:858`, `scalper_session.py:2440` (una riga per sessione: `scalper-sessione-<evento>`), `safe_strategy/service.py:3356` (scanner), `omega_service.py:9150`, `safe_strategy/bot_service.py:11223`, `mike/service.py:7756` | una riga ogni 30 s per servizio | tutte |

Agganci: 7 file del piano + `db_client.py`, `tennis_db.py`, `auth.py`, `safe_strategy/stream.py`, `tennis_recorder.py` (client e
listener esistenti) + una riga di `avvia` in 9 `main`. Diff sui 19 file Python esistenti (compreso `Betfair/conftest.py`):
112 righe aggiunte, 2 sostituite (la chiamata `LocalRequest(...)` e `_lc.publish("ladder", ...)`), nessuna riga di strategia.

## 3. Cosa si misura dal PC e cosa NON si puo' misurare (ne' dal cloud ne' con questo codice)

Si misura (con l'app accesa e `MONITOR_SALUTE=1`): tutto il par. 2, per servizio, ogni 30 s; nel referto: processi e vite
(pid), riavvii (pid cambiati; NON pianificati da `live_alerts` `RUNNER CRASHATO [modulo]` del watchdog), CPU media/p95/max,
RSS e crescita fra 2a e ultima ora di VITA di ogni processo, richieste al cloud per tabella e al minuto, log del giorno
(`--log-dir`), re-login (login oltre il primo di ogni vita), eta' del feed per partita dalle registrazioni con `rx`
(`--raw-dir`, buchi > 5 s, `rx - pt` p50/p99) con "soldi" paper/live SEPARATI da `betfair_live_orders`, scarto
dell'orologio (limite superiore), transazioni/ora del conto, tempi d'ordine (`tempi_ordine` dei log, lettore esistente),
vitalita' dei raccoglitori (RPC), versioni contro i pin di `requirements*.txt`.

NON si puo' (dichiarato):
- dal cloud: niente DB, niente app, niente PC -> nessun numero vero in questo referto; solo codice, test e banco.
- scarto dell'orologio vero: dal processo si ha solo `min(rx - pt)` = scarto + latenza minima (limite superiore); sopra 100 ms
  il referto dice "NON MISURATO" e rimanda a `ARCHITETTURA_2026-10/strumenti/misure/m00b_ntp_offset.py` (nessuna rete nuova
  dal monitor).
- `connectionsAvailable = 0` nelle sessioni dello scalper (flumine di serie: betfairlightweight non salva lo 0; si legge il
  valore precedente). Per renderlo esatto servirebbe un listener nostro nello scalper (fuori mandato: tocca la sessione).
- versione di Node (il renderer non la vede): la pagina legge Electron e Chromium dall'user agent; Electron e' anche in
  `desktop/package.json` (^33.0.0).
- transazioni/ora: contate dai log INFO di `flumine.execution`; se un servizio alzasse il livello di log di flumine, il
  conteggio di quel servizio sparirebbe (oggi tutti i servizi sono a INFO: `basicConfig(level=INFO)` nei 9 main). Lo stesso
  vale per U-65: non abbassare i log di flumine/httpx PRIMA di avere una baseline col monitor.
- processi senza `avvia`: `backtest-worker` (dominio del banco, e il monitor ci si rifiuta per costruzione), `tennis-odds`
  (job breve ogni 30 min, `betfair_tennis_odds.py`: i suoi certlogin NON sono contati), i 9 watchdog (i riavvii si leggono da
  `live_alerts` e dai pid), Electron.
- eta' del feed "per partita con soldi" per il TENNIS: il referto incrocia solo `betfair_live_orders` (calcio); il tennis va
  aggiunto quando ci saranno le registrazioni tennis (U-44).
- L5 lato bot (`ricevuto_ms - ts_pub_ms` nei lettori dei bot, 07 par. 2.4 punto 5) e L13 (istante del clic in
  `localTransport.ts`): NON fatti, toccherebbero i lettori dei bot e la UI dei comandi (fuori dall'elenco dei file di T0A).

## 4. Prove

### 4.1 Test Python (nuovi): `python -m pytest Betfair/monitor -q -p no:cacheprovider`

- `test_monitor_salute_2026_10_09.py`: interruttore (spento di serie: nessun thread, nessun handler; solo "1" accende; nel
  banco spento; sotto pytest spento senza permesso; `avvia` SOLO dentro `main`/`_main` dei 9 file, AST), registro (azzera,
  tetto delle chiavi, quantili, somma dei secchi ESATTA fra finestre), `osserva_stream` (mcm, status, lo 0, garbage),
  marche spente = identita', handler di log (live/paper separati, transazioni solo live), riga dello scrittore contro le
  COLONNE E I TIPI della migrazione (letta dal file SQL), DB giu' (un avviso ogni 10 min, copia locale), psutil assente.
- `test_monitor_agganci_2026_10_09.py`: per ogni aggancio, spento = identico e acceso = marca: raw (riga identica salvo `rx`),
  3 listener veri, ladder con LiveSession e recorder VERI (riga del DB pulita, canale con `ts_pub_ms`/`pt`), canale locale
  VERO mai avviato (`ricevuto_ms`), `_flumine_enqueue_place` di Omega e `enqueue_place` di Safe (params identici salvo
  `emesso_ms`), `MotoreOrdini._pre_invio` con Diario VERO (riga del diario identica), client supabase-py VERO con trasporto
  httpx finto (conteggio per tabella/RPC, errore 503), `db_client.get_supabase_client` e `tennis_db.get_tennis_client`,
  `auth.build_client` con APIClient betfairlightweight VERO e adattatore requests finto (certlogin, listMarketBook, keepAlive).
- `test_monitor_referto_2026_10_09.py`: giornata Europe/Rome, referto sano (tutti OK) e fuori obiettivo (CPU, crescita RSS,
  richieste bot, re-login, crash, transazioni, versione fuori pin), riavvii dai pid senza DB, paper e live mai sommati,
  STESSE RIGHE = STESSI BYTE (md e json), righe locali dello scrittore rilette, feed per partita (buchi, `rx - pt`, soldi),
  log del giorno, pin letti da `requirements.txt`.

Esito: **58 passati, 0 rossi**.

### 4.2 Falsificazione (mutazione -> rosso -> ripristino con sha256 verificato)

Script: mutazione sul file, test indicati, conteggio dei rossi, ripristino del testo originale e controllo dello sha256.

| # | Mutazione | Rossi |
|---|---|---:|
| M1 | `marca_ladder` scrive sulla riga originale (rompe `live_ladder`) | 2 |
| M2 | `marca_emesso` ignora l'interruttore | 1 |
| M3 | `ricevuto_ms` anche a monitor spento | 1 |
| M4 | `nel_banco` sempre falso | 1 |
| M5 | `avvia` sotto pytest senza permesso | 1 |
| M6 | interruttore accetta "true" | 1 |
| M7 | transazioni contano anche il paper | 1 |
| M8 | `connectionsAvailable = 0` perso | 2 |
| M9 | somma dei riassunti senza sommare i secchi | 1 |
| M10 | nessun tetto alle chiavi | 1 |
| M11 | `rx` nel raw anche a monitor spento | 1 |
| M12 | riga del DB del ladder marcata | 1 |
| M13 | canale: attesa in coda non misurata | 1 |
| M14 | diario: fsync non misurato | 1 |
| M15 | Omega: `emesso_ms` anche a monitor spento | 1 |
| M16 | Safe: `emesso_ms` mai scritto | 1 |
| M17 | `db_client` non aggancia | 2 |
| M18 | `tennis_db` aggancia a monitor spento | 1 |
| M19 | `auth` non aggancia | 1 |
| M20 | scanner non osserva lo stream | 1 |
| M21 | riga: colonna rinominata (`rest_richieste` -> `rest`) | 1 |
| M22 | avviso "DB giu'" a raffica | 1 |
| M23 | re-login = tutti i login | 2 |
| M24 | crescita RSS misurata dalla PRIMA ora | 1 (al primo giro SOPRAVVISSUTA: la giornata di prova aveva la stessa RSS nella 1a e nella 2a ora; test rinforzato con un riscaldamento a 90 MB, poi rossa) |
| M25 | `avvia` all'import di un modulo (non nel main) | 1 |
| F1 | soglia "vivo" 90 -> 120 s | 1 |
| F2 | i servizi muti entrano nei totali | 1 |
| F3 | pagina: lo stato vuoto non dice cosa manca | 1 |
| F4 | rotta `/salute` fuori dal guscio | 2 |
| F5 | soglia del frontend diversa dal Python | 1 |
| F6 | la pagina apre un canale locale | 1 |

Python 25/25 rosse (M24 dopo il rinforzo), frontend 6/6 rosse. Ogni file ripristinato con lo sha di partenza.

### 4.3 Banco IDENTICO con il monitor spento (PRIMA = `0aa76dfa`, DOPO = codice consegnato)

Registrazione `35760084` scompattata da `registrazioni_banco/` in `_live_raw/` (come da `LEGGIMI.md`). Durate dichiarate e
misurate: Mike ~1 min, Safe ~10 s (tetto 10 min mai vicino).

| Comando | PRIMA | DOPO |
|---|---|---|
| `python -m Betfair.stream.backtest.certifica mike 35760084 --scenari base` | `OK  35760084  tick= 52082 decisioni= 5246 azioni=   6 ...` / `ESITO: 1 partite senza violazioni, 0 con violazioni, 0 senza decisioni` (54,1 s) | identiche (55,6 s) |
| `python -m Betfair.stream.backtest.certifica safe_base 35760084 --scenari rapidi` | 18 scenari di trasporto, KO 0, `ESITO: OK` | identiche |

Confronto riga per riga dell'intera uscita, tempi esclusi: Safe 132/132 righe uguali; Mike 104 righe, 2 diverse: il tick/s
(tempo) e `codice bot da8e7d9eb005 -> 1db476391a03`, cioe' l'impronta dei 9 file del bot, cambiata perche' `mike/service.py`
ha la riga di `avvia` nel `main` (una delle tre tolleranze dichiarate, U-59: "hash del codice"). Impronta della STRATEGIA di
Mike (`ARCHITETTURA_2026-10/strumenti/e1/e1_impronta_strategia.py confronta`): **0 differenze** (`differenze: 0 []`, rc 0).

### 4.4 Suite e frontend

- `python -m pytest Betfair/ -q -p no:cacheprovider`: **11533 passati, 65 saltati, 6 xfailed, 0 rossi** (496,7 s).
- `frontend/`: `npx vitest run`: **375 file e 5551 test passati, 10 file e 51 test saltati, 0 rossi** (534,9 s); `npx tsc -p tsconfig.app.json --noEmit`: **0 errori**; `npm run build`:
  **fatta** (`index-DxQOaDga.js`) (nel worktree; la dist del PC si rifa' sul PC).
- Fotografie (`src/fotografia`): la voce di menu' nuova cambia le 23 fotografie `*.v2.guscio.json` (in ognuna +7 righe: il
  testo "Salute", il testid `shell-voce-salute`, il link `/salute`; nient'altro, diff riletto); nessuna `*.off.json` delle
  pagine esistenti e' cambiata; nuove `salute.off.json`, `salute.v2.json` (identiche fra loro: la pagina e' la stessa nei
  due gusci), `salute.off.guscio.json`, `salute.v2.guscio.json`. Aggiornate con `FOTOGRAFIA_AGGIORNA=1`.

### 4.5 Migrazione provata su un PostgreSQL 16 usa-e-getta (nel container del cloud, MAI il DB vero)

Ruoli `anon`/`authenticated`/`service_role` (BYPASSRLS come su Supabase) e `betfair_live_is_owner()` copiata dalla migrazione
`betfair_live_order_queue.sql`: migrazione applicata DUE volte (idempotente); RLS attiva; `anon` -> permission denied;
authenticated non owner -> 0 righe; owner -> legge; service_role inserisce una riga VERA dello scrittore (`costruisci_riga`);
`monitor_salute_stato(6)` owner -> 1 ultimo, 1 secchio di serie, 1 sistema; non owner -> "non autorizzato (owner-only)";
`monitor_vitalita_raccoglitori()` -> una voce per tabella, le tabelle assenti con l'errore nella loro voce (nessun errore
generale); `monitor_metrics_pulizia(1)` rifiutata (minimo 2 giorni). Server fermato e cartella cancellata a fine prova.

## 5. Istruzioni ESATTE per il PC (in quest'ordine)

1. Prima di tutto (U-62, R16): accendere l'Ora di Windows con l'app ferma o con tutti i bot flat (salto di ~0,84 s
   all'indietro), poi `python -I ARCHITETTURA_2026-10/strumenti/misure/m00b_ntp_offset.py` e annotare lo scarto.
2. Migrazione (la applica l'utente): SQL Editor di Supabase, ruolo postgres, incollare per intero
   `migrations/monitor_metrics_2026-10-09.sql`. Verifica: `SELECT count(*) FROM public.monitor_metrics;` = 0;
   `SELECT public.monitor_vitalita_raccoglitori();` restituisce le 15 tabelle.
3. `.env` del checkout principale: aggiungere la riga `MONITOR_SALUTE=1` (togliere la riga o metterla a 0 = ritorno).
4. L'utente riavvia l'app (mai con posizioni aperte). Entro 1 minuto: pagina "Salute" (menu' Analisi nel guscio v2, o
   `/salute`): tutti i servizi VIVI; nel log di ogni servizio una riga `[monitor] Salute ACCESO per <servizio>`; in
   `_logs/monitor/<giorno>/` un file per servizio.
5. 24 h con l'app accesa (U-62: PC sveglio). Durante le 24 h, 30 ordini PAPER con `LIVE_TEMPI_ORDINE=1` (di serie gia'
   acceso: `tempi_ordine.py:64`) passando dai bot Omega e Safe (che ora scrivono `emesso_ms`) e dalla Control Room.
6. Tempi d'ordine: `python -m Betfair.stream.tools.leggi_tempi_ordine _logs\runner-calcio_*.log` (anche `--per-via`):
   p50/p95/max per strada e tratto, `decisione_ms` non piu' `na` per Omega e Safe.
7. Referto (giornata Europe/Rome appena chiusa, es. 10/10):
   `python -m Betfair.monitor.referto --giorno 2026-10-10 --da-db --log-dir _logs --raw-dir _live_raw --salva-righe AUDIT_MONITOR/righe_2026-10-10.json`
   -> `AUDIT_MONITOR/REFERTO_SALUTE_2026-10-10.md` e `.json`. Riproduzione senza DB:
   `python -m Betfair.monitor.referto --giorno 2026-10-10 --righe AUDIT_MONITOR/righe_2026-10-10.json --log-dir _logs --raw-dir _live_raw`
   (stesse righe = stessi byte). Senza DB, dalle sole copie locali: `python -m Betfair.monitor.referto --giorno 2026-10-10`.
8. Conservazione (quando l'utente vuole): `SELECT public.monitor_metrics_pulizia(14);`.
9. Ritorno: `MONITOR_SALUTE=0` (o riga tolta) e riavvio: nessun campo, nessuna scrittura (provato dai test e dal banco).

## 6. Divergenze dal piano e decisioni aperte (da portare all'utente)

1. **`avvia` in 9 `main`** (runner calcio/tennis, ponte tennis, scalper-service e sessioni, scanner, Omega, Safe bot, Mike):
   il piano diceva "~40 righe in 7 file"; per avere "una riga ogni 30 s per servizio" ogni servizio deve accendere il suo
   monitor. Sono righe di plumbing, non di strategia; cambiano l'hash del codice del bot nel banco (tolleranza U-59), non
   l'impronta della strategia.
2. **Latenza di flumine**: invece di riscrivere il formato del log del runner (`runner.py:3246`) la si raccoglie con un
   handler nel monitor: il log resta identico.
3. **Transazioni/ora**: contate dai log di `flumine.execution` (zero agganci nel percorso degli ordini), non dalla porta
   (che arrivera' in T10). Dipendono dal livello INFO di flumine (par. 3).
4. **`ts_pub_ms`/`pt` solo sul CANALE**: la riga di `live_ladder` resta identica (l'upsert avrebbe rifiutato il campo).
   Il ladder del TENNIS (runner tennis) non e' marcato: non era nell'elenco.
5. **Copia locale delle righe** (`_logs/monitor/`): non chiesta esplicitamente; serve al referto senza DB e a non perdere
   le righe se la tabella non c'e'. Volume: ~1-2 KB per riga.
6. **Volume nel DB**: ~29.000 righe/giorno (~30-55 MB/giorno) + 2 richieste/min per servizio (~20/min in tutto, contro i
   707,5/min dell'08/10). Conservazione: funzione pronta, nessun pg_cron creato (decisione dell'utente).
7. Non fatti (fuori dall'elenco di T0A): L5 lato bot, L13 (clic della UI), `rx` nel raw del tennis, listener nostro nello
   scalper per lo 0 di `connectionsAvailable`.
8. **Postgres usa-e-getta** acceso e spento nel container del cloud per validare la migrazione (par. 4.5): nessun processo
   dell'app, nessun DB vero.

## 7. PSB par. 6 e par. 7 per questa tappa

- 6.1-6.7 (dati di mercato, scanner, servizio a cadenza reale, ciclo dell'ordine, persistenza/UI, concorrenza, scenari):
  ⊘ per T0A (nessuna logica di bot toccata; il banco e' rilanciato identico, par. 4.3); la concorrenza del monitor e'
  coperta dal lucchetto del registro e dai client per thread.
- 6.8 referto riproducibile: SI' (stesse righe = stessi byte, test; `--salva-righe`/`--righe`).
- 6.9 durate dichiarate: SI' (par. 4.3).
- 7 n.27 finti con chiavi e tipi del vero: SI' (client supabase-py e APIClient veri, LiveSession/recorder/canale/Diario veri,
  riga controllata contro le colonne e i tipi della migrazione, RPC del frontend contro il file SQL).
- falsificazione: SI' (31 mutazioni, tutte rosse; una sopravvissuta al primo giro, test rinforzato).
- paper e live mai sommati: SI' (`esecuzione_live`/`esecuzione_paper`, transazioni solo dal vero, soldi per modalita').
- calcio e tennis mai mischiati: SI' (colonna `sport` per riga e per servizio).
- nessuna strategia toccata: SI' (impronta della strategia di Mike, par. 4.3; Omega e Safe: solo un campo in `params`).
