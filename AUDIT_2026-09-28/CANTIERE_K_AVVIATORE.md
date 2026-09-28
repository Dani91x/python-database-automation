# CANTIERE K — avviatore dell'app: watchdog per tutti i figli e spegnimento ordinato

28/09/2026. Checkout: worktree `agent-a5fd58f2bfd692331`. Lavoro **NON committato su master**
(committato solo sul ramo locale del worktree, `8b5649b` + merge `68738d5` con `origin/master`
`6433516`). Consegna: `AUDIT_2026-09-28/CANTIERE_K_su_master.patch` (`git diff origin/master`
dei soli file elencati sotto).

## 0. Nota di percorso (a meta' lavoro il piano e' cambiato)

Ho iniziato progettando un meccanismo di stop PER FIGLIO in `watchdog.py` (file per watchdog +
Ctrl+C sulla console condivisa, verificato riga per riga sulla documentazione Microsoft
GenerateConsoleCtrlEvent/os.kill). A meta' lavoro il coordinatore mi ha segnalato che il cantiere A
aveva nel frattempo messo su master un meccanismo **piu' semplice e gia' pronto lato Python**:
un **unico file condiviso** `ARRESTO` (`Betfair/stream/arresto_ordinato.py`,
`AUDIT_2026-09-28/SPEC_SPEGNIMENTO_ORDINATO.md`) che i runner calcio/tennis leggono gia' da soli.
Ho **buttato via la parte Ctrl+C** (mai arrivata su master, resta solo nella cronologia locale del
worktree) e riallineato tutto al meccanismo del cantiere A, estendendolo ai servizi bot. Lo dico
perche' il referto qui sotto descrive SOLO il risultato finale, non il tentativo abbandonato.

## 1. Causa radice, con prova

| # | Difetto | Prova |
|---|---|---|
| K1 | `scalper-service` e `tennis-bot-service --bridge-only` senza watchdog | `desktop/main.js` (prima del cantiere): righe 369/375, spawn diretto senza `-m Betfair.stream.watchdog`. Specifica gia' scritta: `AUDIT_2026-09-25/SPEC_WATCHDOG_SCALPER_PONTE_2026-09-26.md` (verificata ancora valida su master: stessi numeri di riga, stesso lato figlio) |
| K2 | `desktop/main.js` chiudeva TUTTI i figli con `taskkill /PID <pid> /T /F` (TerminateProcess): nessun `finally` Python gira | referto 28/09 del cantiere A (R-28-3): ad app spenta 29 righe `live_follow` + 4 `tennis_live_follow` STREAMING, posizioni paper `open` mai regolate |
| K3 | Solo i due runner leggevano il file `ARRESTO` (cantiere A): i servizi bot (Omega, Safe scanner+bot, Mike, ponte tennis, scalper-service) restavano chiusi SOLO dal taskkill, stesso difetto K2 per loro | `SPEC_SPEGNIMENTO_ORDINATO.md` §1: «Gli altri figli... NON leggono il file» (fotografia di prima del mio intervento) |
| K4 | Battito del watchdog (`betfair_live_heartbeat.watchdog_ts/pid`) condiviso da OGNI istanza: con scalper e ponte ora sotto watchdog la riga smette di dire qualcosa sul runner calcio | `SPEC_WATCHDOG_SCALPER_PONTE_2026-09-26.md` §5 |
| K5 | `net_retry.is_transient` non riconosceva un `socket.gaierror` nudo (DNS fallito: primo sintomo di una caduta di rete) | `AUDIT_2026-09-25/FIX_C_RESILIENZA_RETE_2026-09-26.md` §7 punto 8 |

## 2. Cosa ho cambiato e perche'

### `desktop/main.js`
- **K1**: righe 435 e 445 — `scalper-service` e `tennis-bot-service` ora spawnati con
  `['-m', 'Betfair.stream.watchdog', '--', <target> [--bridge-only]]`, come da spec.
- **K2/K3**: nuove funzioni `arrestoCartella`/`arrestoPercorso` (righe 252-260, STESSA
  risoluzione di `arresto_ordinato.cartella()`: env `APP_ARRESTO_DIR`, altrimenti
  `<LIVE_STREAM_DATA_DIR o <repo>/_live_raw>/_arresto/ARRESTO`), `cancellaArrestoAllAvvio` (265,
  chiamata riga 919 in `app.whenReady()`, PRIMA di `startRunners()`), `ARRESTO_ORDINATO_LABELS`
  (277: gli 8 figli che leggono il file) e `shutdownGraceMs` (283: 70s per `scalper-service`,
  25s per tutti gli altri della lista). `orderedShutdown()` (527) scrive il file UNA volta,
  aspetta ciascun figlio consapevole per il suo tempo massimo (`waitForExit`, 504), logga chi e'
  uscito da solo e chi no, poi chiama `killChildren()` (invariata: tree-kill sui superstiti).
  `shutdownAndQuit()` (563) e' il punto d'uscita unico e idempotente: `window-all-closed` e
  `before-quit` (quest'ultimo con `event.preventDefault()` per non farsi scavalcare da un
  `app.quit()` immediato) lo richiamano entrambi; usa `app.exit(0)` (mai `app.quit()`, che
  rilancerebbe `before-quit` in loop).

### `Betfair/stream/watchdog.py`
- **K4**: nuova funzione pura `deve_scrivere_battito(target, override)` — di default True SOLO
  per `Betfair.stream.runner`; env `WATCHDOG_BATTITO` (1/0/true/false/si/no/on/off) forza
  esplicitamente. Il battito nel loop principale ora e' `if scrive_battito: _safe(heartbeat, ...)`
  invece di una chiamata incondizionata.
- L'arresto ordinato NON tocca piu' questo file: ogni figlio esce da solo con `exit 0` leggendo
  `arresto_ordinato.richiesto()`, e `classify_exit` (INVARIATA) tratta gia' rc=0 come `'clean'`
  (nessun riavvio) — zero righe nuove necessarie per la propagazione.

### Servizi bot (riga minima e ADDITIVA nel solo ciclo esterno di ciascuno; MAI una soglia, uno
stake, un tetto o un cancello decisionale toccato)
| file | riga import | riga del controllo | come si ferma |
|---|---|---|---|
| `Betfair/omega/omega_service.py` | 28 | 8043 (`if _AO.richiesto(): break`, in cima al `while True:` di `main()`) | come un `KeyboardInterrupt` gia' esistente: stesso `finally` (`lock.close()`), exit 0 |
| `Betfair/mike/service.py` | 32 | 5316 (`if not args.once and _AO.richiesto(): break`) | idem; MAI in `--once` (giro singolo di collaudo, non il servizio) |
| `Betfair/safe_strategy/service.py` (scanner) | 57 | 2467 (`if _AO.richiesto(): break`, unico `while True:` del ciclo persistente) | idem (`finally`: ferma `score_worker`); QUESTO file non aveva un `except KeyboardInterrupt` prima: ora ha lo STESSO percorso pulito che gli altri avevano gia' |
| `Betfair/safe_strategy/bot_service.py` | 60 | 10072 (`if _AO.richiesto(): break`) | idem |
| `Betfair/stream/tennis_live/tennis_bot_service.py` (ponte, `--bridge-only`) | 31 | 1022, dentro `_ensure_loop()` (`while not stop.is_set():`) | idem; nessun ordine e nessuna sessione Betfair nel ponte (SPEC_WATCHDOG §4): niente da chiudere |
| `Betfair/stream/scalper/scalper_service.py` | 37 | 772: `if os.path.isfile(KILL_FILE) or _AO.richiesto():` | **STESSO** kill-switch STOP_SCALPER esistente (attende fino a 60s la chiusura flat delle sessioni figlie, poi `terminate()` sui superstiti, poi `return`): il file di arresto e' un SECONDO modo di accenderlo, non lo scavalca |

**Scalper-service e le sue sessioni** (`scalper_session.py`): NON ho toccato
`scalper_session.py`. Le sessioni sono processi Popen INDIPENDENTI (nessun kill a cascata dal
supervisore, per design: sopravvivono a un crash del supervisore) e sono GIA' protette da due
meccanismi esistenti e non toccati: (a) il kill-switch del supervisore le aspetta fino a 60s
poi le termina; (b) `taskkill /PID <watchdog> /T /F` (il `/T`, invariato) le raggiunge comunque
come discendenti del processo. Non ho scritto una terza via su un file di gestione posizioni
live: il rischio di un intervento affrettato su codice che chiude posizioni reali mi e' parso
maggiore del beneficio, a fronte di una protezione che gia' c'e'. Lo dichiaro come "non fatto"
al punto 6.

### `Betfair/stream/net_retry.py`
- **K5**: riga ~64, il controllo sul nome della classe ora include `or "gaierror" in name`
  (oltre a "timeout"/"connecterror"/"connectionerror" gia' esistenti).

## 3. Test

Comando esatto e numeri (Python):
```
.venv/Scripts/python.exe -m pytest \
  Betfair/stream/tests/test_watchdog.py \
  Betfair/stream/tests/test_watchdog_nome_modulo_2026_09_26.py \
  Betfair/stream/tests/test_spegnimento_ordinato_2026_09_28.py \
  Betfair/stream/tests/test_net_retry.py \
  Betfair/stream/tests/test_arresto_ordinato_servizi_bot_2026_09_28.py \
  Betfair/stream/tests/test_fine_evento_2026_09_28.py \
  Betfair/stream/tennis_live/tests/test_fine_evento_tennis_2026_09_28.py \
  -q -p no:cacheprovider
```
→ **115 passed in ~3 s** (gli ultimi due file sono del cantiere A, ri-eseguiti per verificare che
il merge non li abbia toccati). In piu', campione dei servizi toccati (rilanciato dopo OGNI
merge con `origin/master`, compreso il cantiere D1 che ha riscritto meta' di `mike/service.py`
e `safe_strategy/bot_service.py` nel frattempo): `Betfair/omega/test_omega_chiuso_dall_utente_
2026_09_16.py`, `Betfair/mike/tests/test_mike_veto_p_under35_2026_09_25.py`,
`Betfair/safe_strategy/tests/test_uscite_automatiche_2026_09_25.py`,
`Betfair/safe_strategy/tests/test_svuota_le_cache_d2_2026_09_24.py`,
`Betfair/stream/tests/test_sveglia_bot_f5_f6_2026_09_18.py`,
`Betfair/stream/tests/test_scalper_freno_origine_2026_09_26.py`,
`Betfair/stream/tests/test_r3_freno_unico_2026_09_25.py` → **187 passed**; tutti i test D1 nuovi
(`test_mike_d1_*`, `test_d1_*`) → **62 passed**. `py_compile` pulito sui 7 file Python toccati.

Node (nessun Electron, processi VERI — node al posto del python del venv, come
`AUDIT_2026-09-26/verifica_log_figli.js`):
```
node AUDIT_2026-09-28/verifica_spegnimento_ordinato.js   → ESITO: TUTTO VERDE (32 controlli)
node AUDIT_2026-09-26/verifica_log_figli.js               → ESITO: TUTTO VERDE (invariato)
```
Copre: risoluzione di `ARRESTO` (APP_ARRESTO_DIR / LIVE_STREAM_DATA_DIR / default),
`cancellaArrestoAllAvvio`, gli 8 figli consapevoli e i loro tempi, `spawnRunner`, un figlio VERO
che vede il file e esce da solo (nessun taskkill, ~0.5s invece di 25s), un figlio VERO che lo
ignora e viene forzato entro il tempo dichiarato (grace abbreviata SOLO nella copia in memoria
del sorgente, mai nel file vero, per non aspettare 25-70s in un test), un figlio NON consapevole
(tennis-odds) forzato subito senza attesa, `waitForExit`/`killChildren` isolati. Nessun processo
lasciato vivo (verificato).

**Falsificazione** (obbligatoria, fatta su OGNI test nuovo):
- `net_retry.py`: rimossa la clausola `gaierror` → 2 test rossi (`test_socket_gaierror_*`);
  ripristinato (`git diff --stat` identico, 0 marcatori `MUTAZIONE`).
- `watchdog.py`: `deve_scrivere_battito` forzata a `True` sempre → 3 test rossi; ripristinato.
- Servizi bot: i 6 file riportati a `git checkout --` (nessun `_AO`, nessun controllo) → le 6
  righe dedicate del nuovo test Python (`test_arresto_ordinato_servizi_bot_2026_09_28.py`)
  diventano rosse una per una; ripristinato con `git apply` della patch salvata prima.
- `main.js`: scrittura del file `ARRESTO` disattivata in `orderedShutdown()` → 3 controlli rossi
  nel test node (il figlio "bene" non vede piu' il file, aspetta 25s pieni e viene forzato
  invece di uscire da solo); ripristinato, `git diff --stat` e sintassi verificati identici.

Ogni ripristino verificato con `grep -c MUTAZIONE` = 0 e `git diff --stat` invariato prima di
proseguire.

## 4. Migrazioni SQL

Nessuna. Questo cantiere non tocca lo schema.

## 5. Parita' paper/live

Nessuna differenza introdotta: l'arresto ordinato e il watchdog agiscono sul PROCESSO, prima e
allo stesso modo per paper e per live (nessun ramo `if modo == 'live'` in nessuna delle righe
aggiunte). La prova e' nel codice: ogni controllo aggiunto e' in cima al ciclo, PRIMA di
qualunque lettura di `order_mode`/`kill_switch`.

## 6. Cosa NON ho fatto e cosa NON ho potuto verificare

**Non fatto** (dichiarato al punto 2): `scalper_session.py` (le sessioni del figlio scalper) non
legge il file `ARRESTO` — resta protetto SOLO dal kill-switch del supervisore (fino a 60s) e dal
`taskkill /T` finale, come prima di oggi. Se l'utente vuole che ANCHE le sessioni leggano il file
da sole (chiusura piu' rapida a rete viva, senza aspettare il giro del supervisore), serve un
cantiere dedicato su codice che gestisce posizioni live — fuori da quanto ho ritenuto prudente
fare qui senza un permesso esplicito su quel file specifico.

**Non verificato dal vivo** (vietato lanciare processi di produzione veri per ordine del brief):
- un vero avvio dell'app con i nuovi watchdog su scalper-service e ponte tennis (`tasklist` con
  due `python -m Betfair.stream.watchdog -- ...` in piu');
- il tempo REALE di chiusura con bot armati e mercati vivi (i 25s/70s sono dichiarati dalla
  documentazione del cantiere A e dal codice esistente del kill-switch scalper, non misurati da
  un'app vera);
- che i 6 servizi bot, chiamati per davvero, arrivino a scrivere/leggere il file `ARRESTO` nella
  STESSA cartella che risolve `main.js` (la risoluzione e' identica riga per riga a
  `arresto_ordinato.cartella()`, ma non ho potuto far girare i due lati insieme);
- l'effetto di `event.preventDefault()` su `before-quit` con l'app VERA (Electron): la logica e'
  testata a livello di funzione estratta (node puro), non nel runtime Electron.

## 7. Decisioni per l'utente

Nessuna decisione di strategia. Un solo numero dichiarato da me, non nella specifica originale:
**25 secondi** di attesa per i 6 servizi bot (Omega, Safe scanner, Safe bot, Mike, ponte tennis)
prima di forzarli — la specifica del cantiere A dichiara 25s SOLO per i due runner (con una
giustificazione precisa: 15s del ramo "nessun mercato" + chiusura follow + flush + logout). Per i
servizi bot ho scelto lo STESSO tetto per uniformita' e margine di sicurezza (i loro giri sono
tipicamente 2-20s), ma non e' una misura come quella dei runner: se l'utente preferisce un tempo
diverso per loro, e' `shutdownGraceMs()` in `desktop/main.js` riga 283.

## 8. Controllo dal vivo al prossimo avvio dell'app (con permesso dell'utente)

1. **Watchdog nuovi**: dopo l'avvio, `tasklist` deve mostrare 8 processi
   `python -m Betfair.stream.watchdog -- ...` (calcio, tennis, scalper, ponte tennis, safe-scanner,
   omega, safe-bot, mike) invece dei 6 di prima — 2 in piu' per `scalper_service` e
   `tennis_bot_service --bridge-only`.
2. **Chiusura con bot fermi**: chiudere la finestra; entro ~5s (nessun mercato vivo) i log in
   `_logs/<label>_*.log` di TUTTI gli 8 devono contenere «ARRESTO ORDINATO richiesto dall'app» (o
   «kill-switch» per lo scalper) e il processo watchdog deve sparire da `tasklist` SENZA un
   `taskkill` (cercare «uscito da solo» nella console/nei log, non «forzo»).
3. **Chiusura con 2-3 bot accesi in paper e partite vive**: accendere Omega/Safe/Mike in paper su
   1-2 partite reali, chiudere l'app. Entro 25s (70s se anche lo scalper e' armato su una
   partita): stesso controllo del punto 2; a DB, `select count(*) from live_follow where
   status='STREAMING'` e l'equivalente tennis devono essere 0 (query gia' nella
   `SPEC_SPEGNIMENTO_ORDINATO.md` del cantiere A); le posizioni paper aperte NON devono sparire
   (l'arresto ordinato non le tocca: le regola il riavvio successivo, gia' certificato dal
   cantiere A/D1).
4. **File `ARRESTO`**: durante la chiusura deve comparire (e poi restare, cancellato al PROSSIMO
   avvio) un file in `<LIVE_STREAM_DATA_DIR o repo/_live_raw>/_arresto/ARRESTO` (o nella cartella
   di `APP_ARRESTO_DIR` se l'utente la valorizza).
5. **Nessun alert falso**: dopo una chiusura ordinata, NESSUN alert `RUNNER_WATCHDOG` di livello
   CRITICAL deve comparire in `live_alerts` per nessuno degli 8 (solo eventuali INFO «terminato
   in modo pulito»); al riavvio successivo nessun alert «RUNNER CRASHATO».

## Elenco esatto dei file toccati/nuovi

Modificati: `desktop/main.js`, `Betfair/stream/watchdog.py`, `Betfair/stream/net_retry.py`,
`Betfair/omega/omega_service.py`, `Betfair/mike/service.py`, `Betfair/safe_strategy/service.py`,
`Betfair/safe_strategy/bot_service.py`, `Betfair/stream/tennis_live/tennis_bot_service.py`,
`Betfair/stream/scalper/scalper_service.py`, `Betfair/stream/tests/test_watchdog.py`,
`Betfair/stream/tests/test_net_retry.py`.
Nuovi: `Betfair/stream/tests/test_spegnimento_ordinato_2026_09_28.py` (riscritto durante il
riallineamento: ora prova solo `deve_scrivere_battito`),
`Betfair/stream/tests/test_arresto_ordinato_servizi_bot_2026_09_28.py`,
`AUDIT_2026-09-28/verifica_spegnimento_ordinato.js`, questo referto,
`AUDIT_2026-09-28/CANTIERE_K_su_master.patch`.
