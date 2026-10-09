# Verifica del PC delle tre consegne del cloud (tappa 0) - 09/10/2026

Delegato verificatore del coordinatore (PC dell'utente, Windows 11, Python 3.13, flumine 2.13.11, betfairlightweight 2.23.2).
Worktree `pda-architettura`, ramo `claude/architettura-tappa0`. Oggetto della verifica: il CODICE di `ee965e26`, confrontato con
`0aa76dfa` (PRIMA). Nessun commit, nessun `git add`, nessuna migrazione applicata, nessun congelamento, nessun bot toccato.

Nota di contesto: durante la verifica un'ALTRA sessione lavorava nello stesso worktree (B1-B5 del PC) e ha aggiunto 5 commit
(`143a60d6`, `7c92904c`, `695a62cd`, `e7eee8bd`, `be660b93`). Ho controllato: nessuno tocca `Betfair/`, `db_client.py`,
`migrations/`; l'unico file di codice/test toccato e' `frontend/src/lib/salute.test.ts` (`be660b93`, vedi R-1). La suite pytest
e i replay sono quindi sul codice Python di `ee965e26`; vitest/tsc/build sul frontend di `be660b93` (= `ee965e26` + quel test).

## 1. Tabella per cantiere

| | T0B4 finto di Omega (`07115d13`) | T0C strumenti (`cd41b2f1`) | T0A Salute (`e44032a9`, `6d02e578`) |
|---|---|---|---|
| Diff letto riga per riga | si' (`omega/tools/replay_registrazioni.py` +24 -5; test nuovo) | si' (`certifica.py` +56 -1; `cassetta.py`, `ombra.py`, `congela.py` nuovi; 1 riga d'elenco in `test_submin_contratto_chiamanti`) | si' (19 file Python esistenti, `Betfair/monitor/*`, migrazione, frontend) |
| Strategie/soglie/stake/gambe toccate | NO | NO | NO (unica riga in `mike/service.py` e' l'`avvia` nel `main`) |
| Additivo a flag spento | si': il vero `omega_db.py`/`omega_service.py`/`omega_engine.py` intatti fra `0aa76dfa` e `07115d13`; `inspect.signature` di `aggregates`/`aggregates_coppia` del finto = vero (nome, tipo, default; `self` escluso): **identici** (rifatto da me) | si': senza `--cassetta/--ombra/--congela/--verifica-congelati` `main` -> `_certifica(a)` (corpo di prima, nessun nome libero: controllato con AST) e `_lavora` -> `_lavora_di_sempre` (unico costo: import di `cassetta.py`, solo libreria standard, nessun effetto) | si': ogni aggancio e' `if _mon.ATTIVO` (oppure `avvia` che torna False senza `MONITOR_SALUTE=1`); `motore_ordini` spento = `scrivi(rec); return` come prima; `runner.py`/`tennis_runner.py` chiamano `_mon.ferma()` sempre, ma a monitor spento e' un no-op. Sonda mia: importati i 14 moduli agganciati (runner, omega_service, safe execution/stream/service/bot_service, mike service, local_channel, motore_ordini, raw_listener, auth, tennis_db, tennis_recorder, db_client) con `MONITOR_SALUTE` vuota E con `=1`: `ATTIVO=False`, 0 handler di log, 0 thread `monitor*`, `scrittore` mai importato |
| Test nuovi verdi | **28/28** | **32/32** (+7 del contratto submin = i 39 dell'AVANZAMENTO) | **58/58** |
| Mutazione MIA | il finto filtra sempre `paper` anche se chiesto `live` (`E.righe_della_modalita(righe, "paper")`) | tolleranza 3 allargata: `"prezzo", "size"` in `ombra.CAMPI_ID_OROLOGIO` | monitor ACCESO DI SERIE (`interruttore_acceso`: default `"1"` invece di `"0"`) |
| Esito | **ROSSA: 8 rossi** (`test_aggregates_coppia_coincide_col_vero[*-live]`, ...) | **ROSSA: 2 rossi** (`..._soglia_di_un_tick`, `..._importo_di_un_centesimo`) | **ROSSA: 2 rossi** (`test_di_serie_spento_nessun_thread_nessun_handler`, `test_solo_1_accende[]`) |
| Ripristino verificato | sha256 del file uguale prima/dopo (`9f40f22f...`), `git status` pulito su `Betfair/` | idem (`7b05c29b...`) | idem (`c2231b76...`) |
| Verdetto | **FIRMABILE** | **FIRMABILE** (con R-3 da portare all'utente prima del congelamento) | **FIRMABILE** per l'ingresso su master SPENTO (con R-1, R-4, R-5, R-6 scritti) |

## 2. Numeri

| Prova | Esito | Durata |
|---|---|---|
| `python -m pytest Betfair/ -q -p no:cacheprovider` (`MONITOR_SALUTE` non impostata) | **11606 passed, 52 skipped, 6 xfailed, 0 failed** (26 warning: thread dei test di battito tennis, deprecazioni ssl/supabase, gia' presenti) | 1044,5 s (macchina condivisa con l'altra sessione) |
| `npx vitest run` | **5551 passed, 18 failed, 51 skipped** (385 file: 374 ok, 1 rosso, 10 saltati). I 18 rossi sono TUTTI in `src/lib/replayVerificaBarra.partite.test.ts`, 3 per ciascuna delle 6 registrazioni NUOVE del commit `695a62cd` (altra sessione, T0B 5: 35768365, 35774000, 35777617, 35790089, 35794049, 35795993): "manca la fixture `replay_barra_<id>.json`". Causa: registrazioni aggiunte senza fixture, NON il codice della tappa 0 (su `ee965e26` quelle cartelle non esistevano). `replayVerificaBarraScript.test.ts` (5 test): **verde** | 632 s |
| `npx tsc -p tsconfig.app.json --noEmit` | **0 errori** (rc 0) | 82 s |
| `npm run build` (nel worktree, `frontend/dist` ignorato da git) | **fatta**, rc 0 (`index-D-BBvYkY.js`; solo l'avviso solito dei chunk > 1600 kB) | 89 s |

Differenza col cloud (11571 / 65 saltati): sul PC 35 test verdi in piu' e 13 saltati in meno (22 raccolti in piu'); spiegazione
probabile: test parametrizzati sulle registrazioni presenti (`_live_raw/35760084` scompattato e cartelle nuove di
`registrazioni_banco/`) e dipendenze presenti solo sul PC. Non indagato oltre (nessun rosso).

## 3. Mike PRIMA/DOPO con il monitor spento (punto d'ingresso unico, uno alla volta)

Registrazione: `registrazioni_banco/35760084` scompattata in `_live_raw/35760084` come da `LEGGIMI.md`; sha256 del raw
`8037bac2504ed1ef3c58147bbcd216c5628c36725f81672b03a098b0f96dcda8` (= H par. 4.4 e referto T0B4), scores `6910bcab...`.
PRIMA in un worktree temporaneo a `0aa76dfa` (junction del solo `.venv`, stessa copia di `_live_raw`), poi junction tolta con
`rmdir` (il `python.exe` del checkout principale esiste ancora) e worktree rimosso senza `--force`.
Durata dichiarata prima del lancio: circa 1 minuto ciascuno.

| `certifica mike 35760084 --scenari base` | PRIMA (`0aa76dfa`) | DOPO (`ee965e26`) |
|---|---|---|
| tick / decisioni / azioni | 52082 / 5246 / 6 | 52082 / 5246 / 6 |
| stati | WATCH ... SETTLED [COMPLETE] | identici |
| ESITO | 1 senza violazioni, 0 con violazioni | identico |
| stderr | 0 righe | 0 righe |
| durata (TEMPO TOTALE / orologio) | 53,6 s / 58 s | 47,1 s / 53 s |
| impronta `codice bot (9 file)` | `bdfc54be93f3` | `12afa48401a8` |

`confronta_referti PRIMA DOPO`: 102 | 102 righe, **4 diverse**: percorso di `_live_raw` (due worktree), impronta del codice,
due righe di tempo. Nient'altro (`diff` grezzo riletto).

L'impronta: dei 9 file di Mike (`service, engine, config, db, dossier, feed, porta_ordini, regolato_conto, certificazione`)
solo `mike/service.py` cambia fra i due commit (+4 righe: `avvia` nel `main`, dentro `if not args.once`). Prova mia: ricalcolata
l'impronta con i file del DOPO e il SOLO `service.py` del PRIMA -> `bdfc54be93f3` = impronta del PRIMA. La spiegazione del
referto T0A par. 4.3 regge; l'aggancio e' sotto flag a tempo di esecuzione (`avvia` torna False senza `MONITOR_SALUTE=1`) e il
banco non chiama mai il `main`. Le impronte del PC sono diverse da quelle del cloud (`da8e7d9eb005 -> 1db476391a03`) perche' si
calcolano sui byte della copia di lavoro (CRLF/LF): attese, vanno confrontate solo sulla stessa macchina (decisione (b)/(c)).

Safe (`certifica safe_base 35760084 --scenari rapidi`), PRIMA e DOPO: **18 scenari di trasporto, KO 0, ESITO: OK** entrambi
(come T0A par. 4.3); 126 | 126 righe, diverse SOLO le durate per scenario e totale; durata 10 s e 9 s. (Il cloud scrive 132 righe:
non ho indagato la differenza di conteggio; il contenuto PRIMA/DOPO sul PC coincide.)

Referti salvati in questa cartella: `PRIMA_mike_base.txt` (`6101f534...`), `DOPO_mike_base.txt` (`9433c919...`),
`PRIMA_safe_rapidi.txt` (`86f7559b...`), `DOPO_safe_rapidi.txt` (`499b2ad5...`).

## 4. Attinenza

`git log --oneline 979aac18..ee965e26`: `0aa76dfa`, `07115d13`, `e86fd27e`, `cd41b2f1`, `c73b52f0` (merge), `e44032a9`,
`6d02e578`, `bd9e37cc`, `3cf32b91` (merge), `66c19c7d`, `5bf92b90`, `ee965e26`: solo architettura + i tre cantieri.
`git diff --stat 0aa76dfa..ee965e26` fuori da `ARCHITETTURA_2026-10`: 75 file, tutti dei tre cantieri (monitor, agganci,
banco T0C, finto Omega, pagina Salute, fotografie del guscio, migrazione, `Betfair/conftest.py`, contratto submin). **Nessun file
fuori perimetro.** Nota: il ramo parte da `a7cf9fdd` ed e' indietro rispetto a master `979aac18` (dutching, enrich,
`replayVerificaBarraScript`): i file di master successivi non si sovrappongono a quelli della tappa 0 (controllato l'elenco).

## 5. Reperti (nessuno corretto qui; da portare all'utente)

- **R-1 (MEDIO, gia' corretto da un'altra sessione) - `frontend/src/lib/salute.test.ts` rosso su Windows a `ee965e26`.** Il test
  "parita' col Python" spezzava `referto.py` su `'\n)\n'`: con la copia di lavoro CRLF contava 13 prefissi invece di 11. Verde nel
  cloud (LF), rosso sul PC. Corretto nel solo test da `be660b93` (normalizza a LF); la mia vitest gira con la correzione ed e'
  verde. Non l'ho rieseguito su `ee965e26` (riporterei il file vecchio nel worktree condiviso): mi fido del commit, che e' un solo
  test. Lezione: i test che leggono sorgenti devono normalizzare i fine riga (vale anche per future parita' Python/TS).
- **R-2 (BASSO, fuori dalla tappa 0) - 18 rossi vitest** in `replayVerificaBarra.partite.test.ts` per le 6 registrazioni nuove di
  `695a62cd` senza fixture `replay_barra_<id>.json` (comando suggerito dal test: `python3 tools/replay_barra_fixture.py <id>`).
  Durante la verifica l'altra sessione stava gia' generando le fixture (`replay_barra_35768365.json`, `..._35774000.json` non
  tracciati, 18:50). Da chiudere prima di dichiarare la suite verde sul ramo.
- **R-3 (MEDIO, T0C, prima del congelamento) - la lista della tolleranza 3 non e' bloccata dai test.** Mutazione mia (prima
  prova): aggiungere `"price"` a `ombra.CAMPI_ID_OROLOGIO` (`Betfair/stream/backtest/ombra.py:75-78`) lascia **32/32 verdi**: la
  cassetta sintetica dei test usa solo `prezzo`, mentre nelle cassette VERE `price` compare (righe dello specchio
  `betfair_live_orders`, argomenti di `place_order_live`, righe del DB). Un allargamento silenzioso della tolleranza agli importi o
  ai prezzi di quelle voci passerebbe i test (resterebbe rossa solo l'ombra sul replay vero, se la stessa divergenza tocca anche
  `prezzo` del livello transazione). Proposta: un test che fissa `CAMPI_ID_OROLOGIO` all'elenco esatto di `TOLLERANZE.md` e una
  voce `specchio`/`riga_db` con `price` nella cassetta sintetica. Con `"prezzo","size"` la mutazione e' rossa (tabella par. 1).
- **R-4 (BASSO, T0A) - conservazione: la funzione dice 14, la decisione dice 7.** `migrations/monitor_metrics_2026-10-09.sql:184`
  `monitor_metrics_pulizia(p_giorni integer DEFAULT 14)` e il referto T0A par. 5 passo 8 `monitor_metrics_pulizia(14)`; la decisione
  del coordinatore (AVANZAMENTO, punto (2)) e' 7 giorni. Allineare istruzioni/default prima dell'applicazione.
- **R-5 (BASSO, T0A) - la voce di menu' "Salute" e' visibile anche a `MONITOR_SALUTE=0`** (`navigazione.ts:92-96`, `App.tsx`
  rotte `/salute`): non e' sotto interruttore. All'ingresso su master "spento" l'utente vedra' la pagina con lo stato vuoto
  ("serve la migrazione... e MONITOR_SALUTE=1") e la pagina chiamera' RPC che non esistono finche' la migrazione non e' applicata
  (`salute.ts:231,237`: l'errore e' gestito e mostrato, nessun crash nei test). Coerente con "la pagina arriva spenta"? Da
  confermare con l'utente.
- **R-6 (BASSO, T0A, n.27) - finto `_DbBot.update_trade(self, trade_id, meta)`** (`Betfair/monitor/tests/test_monitor_agganci_2026_10_09.py:189`)
  contro il vero `update_trade(trade_id, **fields)` (`omega_db.py:83`, `bot_db.py:109`): firma piu' stretta del vero (accetta solo
  `meta`). Oggi non nasconde nulla (l'enqueue passa solo `meta`), ma non e' "la firma del vero".
- **R-7 (INFO, T0A) - a monitor acceso il raw registrato cambia** (`raw_listener.py:217-218`, campo `rx`): le registrazioni fatte
  con `MONITOR_SALUTE=1` non saranno byte per byte quelle di prima; il replay lo ignora (referto). Gli sha256 delle registrazioni
  future vanno presi sapendolo.
- **R-8 (INFO, ambiente) - file di stato sporco dopo la mia vitest:** `frontend/src/components/live/__snapshots__/LadderView.botReplay.test.tsx.snap`
  risulta ` M` (riscritto da vitest alle 18:45), ma il contenuto e' IDENTICO al blob di HEAD (`git hash-object` =
  `git rev-parse HEAD:...` = `54d86a76...`; `git diff` vuoto): e' solo la marca di stato. Non l'ho toccato oltre.
- **R-9 (INFO) - worktree condiviso**: l'altra sessione ha modificato/committato nello stesso worktree durante la mia verifica
  (`AVANZAMENTO.md` modificato non committato, U-60, registrazioni, fixture). Non ho toccato nulla di suo. Le durate (suite 17 min
  contro 8 del cloud) risentono del carico.

## 6. Cosa NON ho potuto verificare

- T0A con il monitor ACCESO in un servizio vero (riga ogni 30 s in `monitor_metrics`, handler, carico): richiede la migrazione
  (da NON applicare) e l'app; fuori perimetro. Il monitor acceso l'ho visto solo nei test (e la mia mutazione ha mostrato che lo
  scrittore tenta davvero il DB: `ConnectError getaddrinfo` in ambiente neutro).
- La migrazione su un DB (non applicata per ordine); letta: RLS owner-only, `REVOKE` da `public/anon`, `SECURITY DEFINER` con
  `search_path` fissato e controllo d'owner, pulizia con minimo 2 giorni.
- `salute.test.ts` alla versione di `ee965e26` su Windows (R-1): non rieseguito.
- Omega `tutti` PRIMA/DOPO del referto T0B4 (242-1466 s) e le prove T0C su Omega/Safe/scalper con cassetta e determinismo:
  non rifatte (fuori dall'elenco dei replay del mandato); tennis (n/a) anche qui (nessun replay tennis lanciato).
- La parita' RPC/in casa di `get_omega_aggregates_modalita` (R4 del T0B4): serve il DB in sola lettura, non fatta.
- Il percorso RPC del vero `omega_db.aggregates_coppia(mode)` (il test del cloud esegue solo il percorso in casa).
- Pagina `/salute` nell'app vera e fotografie a schermo: solo vitest/tsc/build.

## Addendum del coordinatore (PC, 09/10 ore 19:05) - verifiche rifatte di persona

Non ho firmato sul referto del delegato: ho rifatto e aggiunto quanto segue.

| Verifica | Esito del coordinatore |
|---|---|
| Mike `base` 35760084 PRIMA (0aa76dfa) / DOPO (ramo), monitor spento | identici a meno di percorso, tempo (53,6 s / 47,1 s) e impronta «codice bot» (aggancio sotto flag in `mike/service.py`): tick 52082, decisioni 5246, azioni 6, 0 violazioni (diff rifatto da me sui due referti) |
| Safe `safe_base` rapidi PRIMA/DOPO | 18 scenari, KO 0, ESITO OK; differiscono solo le durate (3,4 s / 3,5 s) |
| pytest Betfair/ (ramo, MONITOR_SALUTE non impostata) | 11.606 verdi, 52 saltati, 6 xfailed, 0 rossi (1044 s), dal file del delegato |
| vitest (ramo) | i 18 rossi di `replayVerificaBarra.partite.test.ts` sono stati risolti dal coordinatore (fixture delle 3 partite calcio nuove, tennis in `registrazioni_banco/tennis/`, ri-emissioni del feed: commit 6247fbd0); `salute.test.ts` corretto in be660b93; rilancio completo in corso, numero finale in AVANZAMENTO |
| Mutazione del coordinatore su T0A | `Betfair/monitor/sonde.py:46` `ATTIVO = False` -> `True` a livello di modulo: i 58 test di `Betfair/monitor` restano VERDI. Non e' un difetto del prodotto (`avvia` rimette `ATTIVO = False` senza `MONITOR_SALUTE=1` e nessun servizio avvia da solo), ma e' un BUCO del test: nessun test afferma `sonde.ATTIVO is False` all'import. Reperto R-9 (BASSO), da chiudere nel cloud con un test di una riga. Ripristino verificato (`git diff` vuoto) |
| Perimetro dei file di T0A | elenco dei 67 file dei commit e44032a9 + 6d02e578: nessuna intersezione con i file di 07115d13 (T0B4) e cd41b2f1 (T0C); cherry-pick dei due commit su origin/master 979aac18 pulito, senza conflitti |
| Ramo «Salute su master» (cherry-pick di e44032a9, 6d02e578 + correzione del test) | `git diff origin/master`: SOLO i file di T0A (nessun file del banco, del finto di Omega, di `ARCHITETTURA_2026-10/`); tsc 0; vitest 5565 verdi / 1 rosso (il `salute.test.ts` CRLF, poi corretto: 11/11); pytest 11.533 verdi, 0 rossi (634 s); build ok (27 s) |
| R-5 (voce di menu «Salute») | confermato: `navigazione.ts:92-96` aggiunge la voce SEMPRE, senza interruttore; a monitor spento la pagina spiega che il monitor e' spento o la migrazione non e' applicata. Con MONITOR_SALUTE=0 l'app NON e' identica a prima: c'e' una voce di menu in piu'. Portato all'utente prima dell'ingresso su master |

Verdetto del coordinatore: T0B4 FIRMATA; T0C strumenti FIRMATA (R-3 da chiudere prima del congelamento); T0A FIRMATA per l'ingresso
su master SPENTA, con R-4 (14 giorni nella migrazione contro i 7 decisi) da correggere PRIMA di applicare la migrazione e R-5 da decidere dall'utente.
