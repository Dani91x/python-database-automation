# CANTIERE L — Il report giornaliero disturba l'app? (28/09/2026)

Delegato Sonnet, sola lettura. Checkout principale
`C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation`. Nessuna esecuzione,
nessuna chiamata Betfair, nessun tocco ai processi del report in corso (pid del giorno,
`aggiorna_report.bat` lanciato dall'utente dalla radice, "non fare casini").

Riferimenti letti per intero: `BRIEF_STANDARD_DELEGATI.md`, `CLAUDE.md`,
`CRONOSTORIA.md` (sezione `## 2026-09-26`, righe 3185-3370, e sezione `## 2026-09-28`,
righe 3570-3637), `Betfair/client.py`, `Betfair/betfair_report_manager.py`,
`Betfair/stream/auth.py`, `betfair_full_odds.py`, `aggiorna_mm_sheets.py`,
`aggiorna_report.bat`, `Betfair/betfair_matcher.log` (log vivo di oggi e copia del
26/09 in `.claude/worktrees/agent-a1bc87b400bbc7d7c/Betfair/betfair_matcher.log`),
DB Supabase `dqbwaocvlzbxfrpacsac` (SELECT, `live_alerts`, `engine_signals`,
`betfair_market_odds`, `fixture_predictions`).

---

## 1. Sessioni Betfair — cosa dice la documentazione ufficiale

Fonti: pagina "Best Practice" della documentazione Exchange API (via ricerca web,
contenuto indicizzato di `betfair-developer-docs.atlassian.net/.../Best+Practice`),
pagina "Login & Session Management" e articoli di supporto sviluppatori.

- **Un secondo login con lo stesso account e la stessa app key NON invalida il token
  già in uso.** Testo della documentazione ufficiale: *"Users can have multiple
  sessions 'alive' at any point in time. Additionally, a single session can and
  should be used across multiple API calls/threads simultaneously."* Non esiste,
  in nessuna pagina raggiunta, un numero massimo dichiarato di sessioni
  contemporanee per account/app key: solo un limite di **app key uniche per
  account (una sola coppia Application Key/Delayed Key)**, non di sessioni.
- **Durata sessione**: exchange `.it`/`.es` **20 minuti** (1200 s) senza rinnovo;
  `.com` 12h (24h UK/IE). Le chiamate API NON prolungano la sessione: solo
  `login`/`keepAlive`. Coerente con `Betfair/stream/auth.py:100,179-203`
  (`CustodeSessione`, `vita_s()` di default 1200 s, commento "`.it` = 1200 s").
- **Limite di login**: **100 login riusciti al minuto**; oltre soglia,
  `TEMPORARY_BAN_TOO_MANY_REQUESTS` e blocco di 20 minuti su NUOVI login (fonte:
  Betfair Developer Program support article "Why am I receiving
  TEMPORARY_BAN_TOO_MANY_REQUESTS..."). Il limite è per **account**, non per
  processo: login ripetuti da PIÙ processi sullo stesso account si sommano.
- **Logout**: la documentazione descrive l'operazione come "termina la sessione
  chiamante" (il token passato in `X-Authentication` nella richiesta di logout).
  Non è stata trovata una frase esplicita "chiude solo il proprio token, non le
  altre sessioni", ma è l'unica lettura coerente con "multiple sessions alive":
  se un logout chiudesse TUTTE le sessioni dell'account, la frase sulle sessioni
  multiple sarebbe priva di senso pratico. Trattarlo come CONFERMATO ma non con
  una citazione letterale dedicata (limite di questa ricerca via WebFetch, che non
  raggiunge il testo completo delle pagine Confluence dietro autenticazione JS).
- **Rate limiting sui dati** (non sul login): *"the rate-limiting applies to a
  logged-in account ID, not a session"* — quindi **TOO_MANY_REQUESTS sui dati è
  per ACCOUNT**, non per sessione: più processi con lo stesso account **condividono**
  lo stesso budget di richieste anche se hanno token diversi. Questo è il punto
  rilevante per la domanda 3.

**Verdetto parziale Q1**: il meccanismo sospettato ("il secondo login del report
invalida il token dell'app") **è ESCLUSO dalla documentazione ufficiale**: sessioni
multiple sono un caso d'uso esplicitamente supportato, non un effetto collaterale.

---

## 2. Cosa fa il nostro codice — sessione condivisa? logout su token condiviso?

**Nessun token di sessione condiviso su disco, DB o variabile d'ambiente.** Verificato
per tutti i client Betfair del repo:

- `Betfair/client.py:34-90` (`BetfairClient`, usato da report/full_odds): il token
  vive **solo in memoria di processo** (`self._session_token`, riga 67), impostato da
  `login_cert()` (righe 95-157) e mai scritto su file/DB. Ogni `BetfairClient()`
  istanziato (report, `betfair_full_odds.py`) fa il **proprio** login e ottiene un
  token **indipendente**.
- `Betfair/betfair_report_manager.py:68` (`self.bf = BetfairClient()` nel
  `__init__`) e `:149` (`self.bf.login_cert()`): login proprio del report.
- `betfair_full_odds.py:146-147` (`c = BetfairClient(); c.login_cert()`): login
  proprio, **terzo** processo, **terzo** token, indipendente sia dal report sia
  dall'app.
- `Betfair/stream/auth.py:31-80` (`build_client`, usato da runner/scanner/bot
  dell'app): costruisce un `betfairlightweight.APIClient` **diverso** (libreria
  diversa dal `BetfairClient` del report) e fa il proprio `client.login()`. Stesso
  `BETFAIR_APP_KEY`/`BETFAIR_CERT_FILE`/`BETFAIR_USERNAME` (stesso account, stesso
  certificato: letti da `config.py:16-25`, un solo `.env`), ma **sessione
  (token) propria per ogni processo**, mai condivisa.
- **`Betfair/betfair_report_manager.py`: NESSUNA chiamata a `logout`** (grep
  `logout` sul file: 0 risultati). `Betfair/client.py:159-164` ha solo
  `logout_local()`, che resetta il token **in memoria del proprio processo**
  (il commento a riga 162 dice esplicitamente: *"Logout SSO remoto si può
  implementare più avanti se necessario"* — **non è implementato**) — e comunque
  **non viene mai chiamato** dal report. `betfair_full_odds.py`: stesso controllo,
  0 chiamate a logout.
- L'unico logout VERO verso Betfair nel repo è `Betfair/stream/auth.py:288-294`
  (`safe_logout`, chiama `client.logout()` reale su `betfairlightweight.APIClient`),
  usato SOLO da `Betfair/stream/runner.py:2530` e
  `Betfair/stream/tennis_live/tennis_runner.py:2954` — cioè **l'app chiude la
  PROPRIA sessione runner allo spegnimento pianificato**, mai quella del report
  (client diverso, token diverso, l'app non ha nemmeno un riferimento al
  `BetfairClient` del report).

**Verdetto Q2**: la prova più forte richiesta dal cantiere (logout su token
condiviso) **è ESCLUSA dal codice**: non esiste un token condiviso da nessuna
parte (né file, né DB, né env — solo credenziali/certificato condivisi, non il
token di sessione), e il report non chiama mai logout, né locale né remoto.

---

## 3. Limiti di richiesta — quante chiamate, che peso, chi gestisce cosa

- **Peso Betfair documentato**: `sum(weight) * numero marketId ≤ 200 punti/chiamata`
  per `listMarketCatalogue`/`listMarketBook`; `EX_BEST_OFFERS` = 5 punti/mercato.
  `TOO_MUCH_DATA` scatta oltre i 200 punti.
- **Il nostro codice rispetta il limite con margine, in tutti e 3 i client**:
  - `Betfair/betfair_report_manager.py:878-895` (catalogo): chunk **25 eventi**
    (proiezione pesante ≤ 175 punti); `:919-938` (book): batch **30 mercati**
    (30×5 = **150** punti < 200), delay 0.5s tra chiamate.
  - `betfair_full_odds.py:35-46`: batch **39 mercati** (39×5 = **195** punti < 200),
    `REQ_DELAY` 0.6s, `EVENT_DELAY` 0.2s, catalogo a chunk di **12 eventi**
    (commento: 200/chiamata tetto risultati, margine ampio).
  - Entrambi rilevano `TOO_MUCH_DATA`/`TOO_MANY_REQUESTS` nel testo dell'eccezione
    (`betfair_report_manager.py:899,936`; `betfair_full_odds.py:46,53-54,120-121,
    245-246`) e **si fermano puliti** (return/break/`raise BetfairLimitHit` →
    stop, niente retry-storm, niente ban): `betfair_full_odds.py:298-300` cattura
    `BetfairLimitHit` a livello `__main__` e stampa `[STOP LIMITE BETFAIR]`.
- **Il limite è PER ACCOUNT, non per sessione** (§1): quindi, in teoria, se l'app
  fosse accesa con scanner/runner/bot attivi mentre il report gira, le rispettive
  chiamate REST **si sommano** sullo stesso budget dell'account. Nella pratica
  osservata (§4) questo non è mai successo: il 26/09 il report ha girato con
  l'app **spenta poi appena riavviata** e le sue uniche chiamate Betfair sono
  concentrate in una finestra di ~75 secondi a inizio corsa (vedi §4); il 28/09
  l'utente ha lanciato il report **ad app spenta** per policy esplicita
  (`CRONOSTORIA.md` riga 3626: "lancia ORA `aggiorna_report.bat` (app spenta);
  abitudine concordata: report PRIMA di accendere l'app").
- **Cosa fa il codice dell'APP quando riceve TOO_MANY_REQUESTS/TOO_MUCH_DATA**:
  - Lato **login/sessione** (`Betfair/stream/auth.py:112,116-133,209-244`,
    `CustodeSessione`): NON gestisce esplicitamente `TOO_MANY_REQUESTS` come
    caso a parte — lo tratta come un fallimento generico (`_fallito`, backoff
    15/30/60s), diverso solo dagli errori di sessione riconosciuti
    (`NO_SESSION`/`INVALID_SESSION_INFORMATION`, righe 112,129).
    `Betfair/stream/tennis_live/tennis_bot_service.py:46` documenta il rischio
    opposto: un loop stretto di re-login (`build_client(login=True)` ad ogni
    giro) PUÒ da solo produrre `TOO_MANY_REQUESTS` — non serve il report.
  - Lato **subscription stream** (`Betfair/stream/limits.py:6,66`): backoff
    esponenziale davanti a `SUBSCRIPTION_LIMIT_EXCEEDED`/`TOO_MANY_REQUESTS` —
    **gestito**, non un `exit(1)`.
  - **Non è stato trovato, nel runner calcio (`Betfair/stream/runner.py`), un
    catch dedicato per `TOO_MUCH_DATA`/`TOO_MANY_REQUESTS` sulle chiamate REST
    del runner stesso** (grep sul file: 0 risultati). Il file NON ha un
    `try/except` totale a livello di processo (`_main()` righe 2540-2558,
    `if __name__` riga 2561): un'eccezione non prevista da uno dei ~60 blocchi
    `except Exception` interni (tutti mirati: DB, alert, gating, un mercato
    malformato, mai "qualunque cosa") **si propaga e fa morire il processo con
    lo stack Python di default → exit code 1**. Questo spiega architetturalmente
    gli "exit code 1 senza traceback" degli alert 497/505/510: il traceback
    esisteva (Python lo stampa sempre su un'eccezione non gestita) ma andava
    sulla console dell'exe, **mai rediretta su file fino al riavvio delle
    17:07Z** (K2, reperto già chiuso da altro cantiere). Non è quindi possibile
    stabilire dal codice SOLO se la causa specifica dei 3 crash sia stata
    `TOO_MANY_REQUESTS`: è UNA delle tante eccezioni non wrappate che avrebbero
    prodotto lo stesso sintomo.

---

## 4. I fatti del 26/09 — cronologia al secondo (UTC)

Fonti incrociate: `live_alerts` (DB, id 495-526, letti per intero), log del report
di quel giorno (`.claude/worktrees/agent-a1bc87b400bbc7d7c/Betfair/betfair_matcher.log`,
656 righe, inizia col login del report), `CRONOSTORIA.md` righe 3281-3370.

| Ora UTC | Evento | Fonte |
|---|---|---|
| 09:55-10:02 | ultimo dato live stream prima del buco | CRONOSTORIA R-STREAM-1 |
| 09:59:48 | scalper vede NEW_MATCHES (alert 496) | `live_alerts` |
| 10:01:06 | **CRASH 1 runner calcio** (`exit code 1`, uptime 3858s = da avvio ~08:56Z) | `live_alerts` 497 |
| 10:01:22 | riavvio runner (pid 20552→12812), watchdog ok | `live_alerts` 498-500 |
| 10:41:41 | rete cade (DNS), ripristino report utente | CRONOSTORIA |
| da 10:01Z | runner calcio **CIECO**: bug `runner.py:1192` salta il controllo di stallo quando `market_to_event` è vuoto dopo un riavvio → nessun rilevamento per ore | CRONOSTORIA R-STREAM-1 |
| 14:39:12 | stream mercati MUTO da 14251s, auto-recovery: "ricostruisco la subscription" | `live_alerts` 502 |
| 14:42:46 | tee raw fermo 130s con stream "attivo" (recovery non ha ridato dati) | `live_alerts` 503 |
| **14:42:59** | **utente lancia `aggiorna_report.bat` (pid 1380)**, doppio clic sulla copia nel worktree `agent-a1bc87b400bbc7d7c` | CRONOSTORIA, confermato dal log |
| 14:43:25 | login report riuscito (`certlogin SUCCESS`) | log report riga 6-7 |
| 14:43:30-14:44:15 | **UNICA finestra di chiamate Betfair del report**: `list_events`, 4 chunk `list_market_catalogue` (25 eventi/chunk), 21 batch `list_market_book` (30 mercati/batch) — fine alle 14:44:15 | log report righe 8-46 |
| 14:44:15 → ~14:59 | report in **Fase 3** (generazione righe, `predict_fixture` per 87 match, download modelli da Supabase Storage): **ZERO chiamate Betfair** in questa fase (usa `odds_cache` già in memoria) | codice `betfair_report_manager.py:600-645` + log |
| 14:45:09 | 2 nuove partite agganciate al live (scanner REST, non stream) | `live_alerts` 504 |
| **14:46:15** | **CRASH 2 runner calcio** (`exit code 1`, uptime 17099s) — **~2 minuti DOPO l'ultima chiamata Betfair del report**, che in quel momento sta processando fixture con Supabase/ML | `live_alerts` 505 |
| 14:46:43 | riavvio automatico runner calcio (watchdog) | `live_alerts` 506-507 |
| ~14:52 | **utente CHIUDE e RIAVVIA l'intera app** (icona, non da terminale: niente console su file) | CRONOSTORIA |
| 14:54:27-36 | nuovo ORDER_MODE + RECONCILE (coerente con l'avvio completo dei runner della app appena riaperta, **nuovo login, nuova sessione**, nessuna eredità dal login precedente) | `live_alerts` 508-509 |
| ~14:59 | report scrive 61 righe `fixture_predictions` (fine Fase 3, foglio "Prediction" con le fixture del giorno) | CRONOSTORIA riga 3357 |
| **15:04:20** | **CRASH 3, runner TENNIS** (`exit code 1`, uptime 611s ≈ 10 min — nato con il riavvio app delle 14:54Z, **sessione completamente nuova**) | `live_alerts` 510 |
| 15:04:30 | riavvio watchdog tennis (pid 7520) | CRONOSTORIA |
| 15:26:53 | errore journal non bloccante (constraint DB, non Betfair) | `live_alerts` 511 |
| dopo 16:59 | report prosegue Fase 6-13 (sheet, `signal_history`, `engine_signals`) fino a "Job completato" | log report (non riletto oltre riga 656: fuori dalla finestra dei 2 crash) |

**Lettura**: i due crash del calcio (497 prima del report; 505 durante) e quello
tennis (510) sono **tutti "exit code 1" della stessa famiglia** (nessun traceback
salvato, K2), in una giornata già instabile di suo (rete a singhiozzo dalle
10:41Z, runner calcio cieco dalle 10:01Z per un bug indipendente
`runner.py:1192`, auto-recovery dello stream in corso proprio nei minuti del
login del report). Il crash 505 avviene 3 minuti dopo il login del report ma
**2 minuti dopo l'ultima chiamata Betfair del report** (il report è in una fase
di puro calcolo Supabase/ML in quel momento). Il crash 510 riguarda un runner
**nato dopo un riavvio completo dell'app con login proprio e nuovo**, 10 minuti
dopo la sua nascita, mentre il report — per tutta quella finestra — non stava
facendo alcuna chiamata Betfair (l'ha già fatta e chiusa 20 minuti prima). Non
c'è **nessuna sovrapposizione temporale fra le chiamate Betfair del report e i
3 crash**: il report chiama Betfair solo nei primi ~75 secondi della sua corsa
(14:43:30-14:44:15Z), i crash sono a 10:01Z (prima, escluso dal cantiere stesso),
14:46:15Z (+2 min dall'ultima chiamata) e 15:04:20Z (+20 min, e su una sessione
app nata DOPO che il report aveva già finito di chiamare Betfair).

---

## 5. Oggi (28/09) — cosa dice il report da solo, ad app spenta

Vedi §"Cosa ha fatto davvero oggi" più sotto (estensione). In sintesi: nessun
errore di sessione o di limite trovato nel log di oggi fino al punto raggiunto
alla fine di questo referto; nessun evento anomalo diverso dal normale
("Model cache expired... re-downloading" per i modelli scaduti, non un errore).

---

## ESTENSIONE — «Il report lavora come progettato?»

### 1. Cosa deve fare, dal codice

**`aggiorna_report.bat`** (36 righe), 4 passi, sempre dalla directory dello script
(`cd /d "%~dp0"`, riga 13):

| Passo | Comando | Una riga |
|---|---|---|
| [1/4] | *(solo echo, nessun comando)* | Etichetta "Pulizia stato precedente" **fuorviante**: non esegue nessuna pulizia, è testo decorativo fra due `echo` (righe 17-19) — **difetto cosmetico**, non funzionale. |
| [2/4] | `python -m Betfair.betfair_report_manager --skip-training` | Report principale, 13 fasi (tabella sotto). |
| [3/4] | `python aggiorna_mm_sheets.py` | Scrive i fogli Google Money Management da `Betfair/mm_history.json` + Supabase (`signal_history`); **nessuna chiamata Betfair** (grep `BetfairClient`/`login_cert`: 0 risultati nel file). |
| [4/4] | `python betfair_full_odds.py` | Login Betfair **proprio** (terzo, indipendente), scarica TUTTI i mercati (non solo i principali) con back+lay per le fixture di oggi, upsert in `betfair_market_odds` (mai `fixture_predictions`: vedi nota sotto). |
| fine | `pause` | Tiene aperta la finestra cmd fino a un tasto: **voluto** per un lancio a doppio clic dall'utente (non è automazione, non blocca nulla). |

**Le 13 fasi di `run_daily_report` (`Betfair/betfair_report_manager.py:135-287`)**:

| Fase | Legge | Scrive | Se fallisce |
|---|---|---|---|
| Login (riga 149) | credenziali `.env` | token in memoria | **BLOCCA tutto**: `except`, `logger.error`, `return` — ma il processo Python **esce con codice 0** (nessuna eccezione sollevata): il `.bat` non ha modo di sapere che il report non ha fatto nulla, e prosegue comunque a [3/4] e [4/4]. |
| 2 (evento Betfair, righe 163-183) | Betfair `listEvents`+`listMarketCatalogue` (non chunked) | foglio "Partite Listate Betfair" | Nessun evento → WARNING, prosegue senza il foglio. |
| 3 (righe 187-191) | `fixture_predictions` (colonne leggere, con retry su timeout) | — | Fallback a `select('*')` se le colonne cambiano; retry con backoff sui timeout transitori. |
| 3b pre-flight (righe 193-200) | — | — | **Sempre saltato**: `FORCE_READ_ONLY_MODELS=True` (riga 1206) forza `skip_training=True` **a prescindere dal flag CLI** — blindatura esplicita "il report non allena mai". |
| 4 "Prediction" (righe 202-203, `_sync_all_predictions` :289-388) | `fixture_predictions` già in DB | foglio "Prediction" (tutte le fixture del giorno, **non genera nuove prediction**) | `except`+`logger.error`, non bloccante. |
| 5 "Match Events" (206-208) | eventi Betfair + `db_fixtures` | foglio "Match Events" (debug) | non bloccante (`except`). |
| 6 (211-214) | `matches` (risultati finali) | `signal_history` (upsert Supabase) + storico JSON locale | Se Supabase fallisce: WARNING, il JSON locale resta comunque coerente (visto oggi: errore `23502 null value "date"` su UNA riga di `signal_history`, non bloccante). |
| 7 "Segnali" (216-219, `_update_signals_sheet`→`_prefetch_odds_for_events`) | Betfair `listMarketCatalogue`+`listMarketBook` (chunk 25/batch 30) | foglio "Segnali" + **NUOVE righe `fixture_predictions`** via `predict_fixture` (qui, non in Fase 4) | Su `TOO_MUCH_DATA`/`TOO_MANY_REQUESTS`: log CRITICAL e stop pulito di questa sotto-fase (righe 899-901,936-938), il resto del job continua. |
| 8 (222-223) | `matches` | storico multi-giorno locale (`Betfair/mm_history.json`) | non bloccante. |
| 9 Dashboard MM (226-228) | dati storico | foglio Google "Money Management" | non bloccante. |
| 10 Report Ven-Dom (231-233) | dati storico | foglio Google "Report Ven Dom" | non bloccante. |
| 11 Analytics (236-237) | dati storico | foglio Google "Analytics" | non bloccante. |
| 12 engine_signals (244-251) | dati recenti (21 gg) | tabella `engine_signals` | **try/except esplicito**: fallisce → solo WARNING, "non bloccante" per design (commento riga 241-242). |
| 13 merge analytics (261-285) | `engine_signals` (finestra 4 gg) | `analytics_decisions`+`analytics_signals` (subprocess `merge_engine_signals.py --days 4`, timeout 600s) | **try/except esplicito**: fallisce o exit≠0 → solo WARNING, non bloccante. |

**Nota importante sulla richiesta del coordinatore**: `betfair_full_odds.py:141`
è una **SELECT** (`fx = sb.table("fixture_predictions").select("fixture_id,
home_team_name,away_team_name,fixture_date")...`), usata SOLO per il matching
nome↔fixture. `betfair_full_odds.py` **non scrive mai** in `fixture_predictions`:
scrive esclusivamente in `betfair_market_odds` (righe 258-263: `fixture_id,
market_name, selection, sort_priority, market_id, run_date, back, lay`). Le
uniche scritture su `fixture_predictions` di tutta la catena `.bat` avvengono
in Fase 7 del report (via `predict_fixture`), non in `betfair_full_odds.py`.

### 2. Cosa ha fatto davvero oggi (28/09) — log `Betfair/betfair_matcher.log`

Log identificato per data di modifica (mtime = adesso, file attivo). Corsa di
oggi inizia riga 8204 (`2026-09-28 15:39:03`), lanciata dalla RADICE del repo
(non da un worktree: il file vive in `Betfair/betfair_matcher.log` del checkout
principale, non in una copia).

| Fase | Partita | Fine | Durata | Numeri |
|---|---|---|---|---|
| Login | 15:39:03 | 15:39:04 | 1s | `certlogin SUCCESS` |
| 2 (eventi) | 15:39:09 | 15:39:26 | 17s | foglio "Partite Listate Betfair": **36 righe** |
| 3 (prediction) | 15:39:26 | 15:39:31 | 5s | Fetch 36 colonne; foglio "Prediction": **84 analisi** |
| 3b pre-flight | — | — | — | SALTATO (`--skip-training`), come da design |
| 5 (Match Events) | 15:39:32 | 15:39:34 | 2s | **36 eventi** |
| 6 (risoluzione storico) | 15:39:34 | 15:39:47 | 13s | **50 Poisson + 39 ML risolti**; 1 WARNING Supabase (`signal_history`, riga con `date` NULL, `code 23502`, non bloccante, il JSON locale resta OK) |
| 7 (Segnali/prefetch) | 15:39:47 | 15:39:53 | 6s | Fase 1-2 interne: **33 match**, 2 chunk catalogo, 8 batch book (21-30 mercati/batch) |
| 7 (Fase 3 interna, per-fixture) | 15:39:53 | ~15:48:30 | ~8m40s | 33 fixture processate, molte con re-download modelli scaduti (TTL 24h, età osservata 69h: i modelli NON sono stati riaddestrati oggi, solo **riscaricati** dalla cache Supabase — coerente con `--skip-training`) |
| 8-9 (storico + Dashboard MM) | ~15:48:30 | 15:51:47 | ~3m | Dashboard: **22 operazioni, 16 formattazioni** |
| 10 (Report Ven-Dom) | 15:51:48 | 15:54:26 | 2m38s | **3845 Poisson + 3577 ML, 98 concordanze** |
| 11 (Analytics) | 15:54:27 | in corso al momento della lettura | — | — |
| 12-13 | non ancora raggiunte al momento della lettura | — | — |

**ERROR/WARNING raggruppati (fino al punto letto)**: 1 solo, non critico
(`signal_history` riga con `date` NULL, `code 23502`, righe 8311 del log —
scarto singolo, non un pattern). Nessun `TOO_MANY_REQUESTS`, nessun
`TOO_MUCH_DATA`, nessun errore di sessione, nessun Traceback. Il report **non
aveva ancora finito** quando ho iniziato a scrivere questo referto: vedi
aggiornamento finale sotto.

### 3. Riscontro sul DB (SELECT, sola lettura, durante la corsa di oggi)

- `fixture_predictions` toccate oggi: **84 righe**, `updated_at` fra
  `08:48:39Z` e `13:51:26Z` (fotografia presa a metà corsa — coerente con la
  Fase 3 ancora in scrittura al momento della query).
- `engine_signals` con `run_date='2026-09-28'`: **0 righe** al momento della
  query (Fase 12 non ancora raggiunta — atteso, vedi tabella sopra).
- `betfair_market_odds` con `run_date='2026-09-28'`: **0 righe** al momento
  della query (`betfair_full_odds.py` è il passo [4/4], parte solo dopo che
  [2/4] e [3/4] sono finiti — non ancora avviato).

*(Ripeto queste 3 query a fine lavoro, vedi "Aggiornamento finale" sotto.)*

### 4. Difetti trovati

1. **[1/4] "Pulizia stato precedente" non pulisce nulla**: fra le due `echo`
   (`aggiorna_report.bat:17-19`) non c'è nessun comando. L'etichetta è
   fuorviante ma innocua (non impedisce nulla): **cosmetico**.
2. **Login fallito = job silenziosamente "riuscito" agli occhi del chiamante**:
   `run_daily_report` righe 148-154, su login KO fa `logger.error` + `return`
   **senza sollevare un'eccezione** → il processo Python termina con **exit
   code 0**. Il `.bat` non controlla `%ERRORLEVEL%` fra i passi (li lancia in
   sequenza comunque), quindi in pratica l'assenza di controllo non cambia il
   flusso — ma toglie all'utente (o a un futuro automatismo) qualunque modo di
   distinguere "report riuscito" da "report morto al primo passo" senza aprire
   il log. **Proposta (non applicata)**: `sys.exit(1)` nel branch di errore del
   login, e nel `.bat` un controllo `if errorlevel 1` prima di proseguire a
   [3/4]/[4/4].
3. **Fase 12/13 "non bloccanti" sono anche "silenziose"**: il design è corretto
   (un fallimento del firehose `engine_signals` non deve rompere il report), ma
   l'unico segnale di un fallimento è una riga WARNING in un file di log che
   nessun processo legge automaticamente. Il reperto R-28-4 già in
   `CRONOSTORIA.md` (riga 3576) conferma che `engine_signals` è rimasto senza
   righe per 3 giorni (24, 27, 28/09 prima di oggi) senza che nessuno se ne
   accorgesse fino all'audit odierno — è esattamente il sintomo di "fallisce in
   silenzio" che il coordinatore chiedeva di cercare, anche se qui la causa non
   è un errore ma il fatto che **nessuno ha lanciato il `.bat`** quei giorni
   (decisione utente: resta manuale). Non è un difetto di codice, è un rischio
   operativo: se un giorno la Fase 12 fallisse DAVVERO (non per mancato lancio
   ma per un errore vero), nessuno lo saprebbe senza aprire il log a mano.
4. **`cd /d "%~dp0"` protegge solo la posizione, non il contenuto**: se il
   `.bat` viene lanciato da una copia vecchia o mutata dentro un worktree (come
   avvenuto il 26/09), `cd /d "%~dp0"` porta la working directory dentro QUEL
   worktree, e `python -m Betfair.betfair_report_manager` carica il codice
   Python **di quel worktree**, non quello del checkout principale. Il 26/09 il
   codice del worktree si è rivelato equivalente/innocuo (report ha scritto
   `fixture_predictions` corrette, nessun ordine), ma il meccanismo resta un
   rischio aperto: un worktree con codice a metà di una modifica (es. un
   delegato che sta editando `betfair_report_manager.py` o `betfair_match.py`)
   lanciato per errore produrrebbe un report con **logica diversa da quella di
   produzione**, senza alcun avviso. **Proposta (non applicata)**: loggare
   `os.path.abspath(__file__)` (o il commit/branch git) come prima riga del
   report, così un'occhiata al log rivela sempre da dove è girato davvero.
5. **Nessun controllo esplicito di limiti Betfair nella Fase 2 iniziale**
   (`list_market_catalogue` a riga 179, non chunked): con **89 eventi** (visto
   il 26/09) e proiezione default (`MARKET_START_TIME, RUNNER_DESCRIPTION,
   EVENT, MARKET_DESCRIPTION`, quest'ultima pesa 1 punto), il peso per evento
   dipende dal numero di mercati/evento — nei giorni con molti eventi questa
   singola chiamata non chunked potrebbe avvicinarsi al tetto. Non è mai stato
   osservato un `TOO_MUCH_DATA` qui (grep sul log storico intero: 0 occorrenze
   in tutte le corse salvate), quindi resta un rischio teorico, non un difetto
   osservato.

### 5. I fogli Google — cosa guardare a occhio

Non leggibili da qui (nessuna chiamata Google permessa). Dal log di oggi, le
scritture risultano tutte "riuscite" (nessun errore associato ai fogli):

| Foglio | Colonna/valore atteso oggi | Riferimento log |
|---|---|---|
| "Partite Listate Betfair" | 36 righe | riga 8208 |
| "Prediction" | 84 righe | riga 8212 |
| "Match Events" | 36 eventi | riga 8214 |
| "Segnali" (Market Map) | 33 match abbinati su 36 eventi Betfair | riga 8316 |
| "Money Management" (Dashboard) | 22 operazioni, 16 formattazioni | log (Fase 9, dopo riga 8552) |
| "Report Ven Dom" | 3845 righe Poisson + 3577 ML, 98 concordanze | log (Fase 10) |
| "Analytics" | *(in corso al momento della lettura)* | — |

### Verdetto estensione (provvisorio, da confermare a fine lettura)

**NON ANCORA VERIFICABILE PER INTERO**: il report era ancora in esecuzione
(Fase 11 di 13) quando questo referto è stato scritto. Fin qui: **LAVORA COME
PROGETTATO**, con 2 difetti cosmetici/di robustezza minori (punti 1-2 sopra) e
un rischio operativo noto e già segnalato altrove (punto 3). Nessun
malfunzionamento money-critical osservato.

---

## Verdetto finale — Cantiere L (il report disturba l'app?)

**ESCLUSO** il meccanismo sospettato (login del report che invalida/chiude la
sessione dell'app via logout su token condiviso): la documentazione Betfair
dichiara esplicitamente le sessioni multiple come caso supportato, e il codice
non ha MAI un token condiviso fra processi né una chiamata di logout dal
report verso qualunque sessione (nemmeno la propria).

**Sul meccanismo alternativo (limiti API condivisi per account)**: la
cronologia del 26/09 **non mostra sovrapposizione** fra le chiamate Betfair del
report (finestra di 75 secondi a inizio corsa, entrambe le giornate) e i 3
crash osservati (uno precede il report, gli altri due cadono 2 e 20 minuti
dopo l'ultima chiamata Betfair del report). Non è quindi **PROVATO** nemmeno
questo meccanismo, ma per onestà resta **NON PIENAMENTE FALSIFICABILE al
100%** con i soli dati esistenti, perché il 26/09 mancava la console su file
(K2): un'eccezione non vista potrebbe in teoria essere stata
`TOO_MANY_REQUESTS`, anche se la finestra temporale la rende improbabile.

**Regola pratica per l'utente**: **il report si può lanciare in qualunque
momento, anche con l'app accesa** — non esiste nel codice un meccanismo che
lo renda pericoloso per le sessioni dei bot. L'abitudine già adottata
("report prima di accendere l'app") resta comunque una buona prassi per
tenere il traffico Betfair più diradato nel tempo (il limite dati è per
account), ma non è una necessità dimostrata dal codice o dalla documentazione.

**Prova dal vivo che chiuderebbe il residuo dubbio** (bassa priorità, dato il
peso delle prove già raccolte):
1. Riavviare l'app **con console rediretta su file** (il fix K2 già chiesto da
   altro cantiere: `main.js` che scrive stdout/stderr dei processi figli su
   file, o lancio da PowerShell con `> log.txt 2>&1`).
2. Lasciare l'app accesa in PAPER con tutti i bot spenti (nessun ordine in
   gioco) e lanciare `aggiorna_report.bat` dalla radice.
3. Osservare per 30 minuti: se un runner crasha, il traceback questa volta
   finisce su file — leggerlo dice la causa VERA (sessione? rete? altro?) e
   chiude la domanda in modo definitivo, in entrambe le direzioni.
Nessun rischio economico: bot spenti, nessun ordine possibile.

## Cosa NON ho potuto verificare

- Il testo letterale della pagina Betfair "Login & Session Management" sul
  comportamento esatto di `logout` (chiude solo il token chiamante) non è
  raggiungibile per intero via WebFetch (pagina Confluence con contenuto
  caricato via JS): la conclusione al §1 è un'inferenza forte dalla frase
  ufficiale sulle "sessioni multiple", non una citazione diretta su `logout`.
- La causa ESATTA dei 3 crash del 26/09 (nessun traceback salvato su file quel
  giorno, K2: reperto già aperto da altro cantiere, non di mia competenza
  correggere qui).
- Il completamento delle Fasi 11-13 e di `betfair_full_odds.py` della corsa di
  oggi (28/09): il report era ancora in esecuzione al momento di consegnare
  questo referto — vedi "Aggiornamento finale" sotto per lo stato raggiunto
  entro la fine del mio turno di lavoro.
- Il contenuto reale dei fogli Google (nessun accesso permesso da questo
  cantiere): solo dedotto dal log, come richiesto.
