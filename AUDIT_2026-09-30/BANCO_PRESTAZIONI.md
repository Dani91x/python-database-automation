# BANCO PRESTAZIONI - replay di Mike piu' veloce a referto identico (30/09/2026)

Delegato: worktree `agent-ab0f9fd7f9a36a0a8`, base `fc0428f`. Niente commit. Patch:
`AUDIT_2026-09-30/BANCO_PRESTAZIONI.patch` (diff dei 4 file modificati + il test nuovo).

## 1. Esito in breve

| misura (scenario `base`, `--worker 1`, trasporto canale, ambiente neutro) | PRIMA | DOPO |
|---|---|---|
| riga `tempo:` del referto, minimo di 3 giri alternati | **77,9 s** | **52,0 s** (-33 %) |
| CPU del processo, minimo di 3 | 78,7 s | 54,2 s (-31 %) |
| righe del referto diverse (tolte le righe dei tempi) | - | **0 su 89**, in 6 giri su 6 |

Stima per `certifica mike 35760084 --scenari tutti --trasporto canale --worker 0`
(21 scenari, 3 processi): il referto del 29/09 (`AUDIT_2026-09-29/replay/mike_tutti_P5_4C.txt`)
da' 520,6 s con somma dei 21 scenari 1495 s, pool gia' bilanciata (1495/3 = 498 s). Con il
rapporto misurato 52,0/77,9 = 0,67 -> **circa 350 s (fascia 330-370 s) a PC libero**: sotto il
tetto di 600 s, ancora SOPRA l'obiettivo di 300 s. Il 30/09 il PC era carico (carico CPU
14-100 % durante le misure: replay completi e suite di altri delegati), percio' ho alternato
PRIMA/DOPO nello stesso worktree e preso il minimo. Il replay completo NON l'ho lanciato.

## 2. Profilo (cProfile, scenario `base`, un processo)

Nota: con Python 3.13 cProfile somma i thread (il trasporto canale ne usa piu' d'uno), quindi i
cumulati dei thread in attesa (`recv`, `queue.get`) superano il totale: si leggono le quote, non
i secondi. I due profili sono stati presi con carichi del PC diversi (il PRIMA sotto carico
pesante): il confronto vero e' la tabella del par. 1.

### PRIMA (`_perf/prima.prof`, 381 s profilati) - primi 20 per cumulato (codice Betfair/flumine)

| # | funzione | chiamate | proprio s | cumulato s |
|---|---|---|---|---|
| 1 | `stream/backtest/porta_banco.py:185(recv)` | 376 | 2.1 | 1053.4 (thread in attesa) |
| 2-6 | `certifica.py` main / `_esegui_compiti` / `_lavora` | 1-2 | 0.0 | 367.0 |
| 7 | `flumine/utils.py:261(call_strategy_error_handling)` | 1004267 | 1.5 | 200.2 |
| 8 | `stream/backtest/trasporto.py:226(_process_market_book)` | 502123 | 4.4 | 198.5 |
| 9 | `mike/tools/replay_registrazioni.py:523(process_market_book)` | 502123 | 5.4 | 176.5 |
| 10 | `stream/backtest/banco_comune.py:1422(_a_flumine)` | 643713 | 11.2 | 147.1 |
| 11 | `mike/tools/replay_registrazioni.py:567(_un_giro)` | 5824 | 0.7 | 119.6 |
| 12 | `mike/service.py:4229(_run_event)` | 5824 | 2.4 | 93.6 |
| 13 | `flumine/baseflumine.py:353(_process_close_market)` | 139142 | 8.2 | 82.0 |
| 14 | `mike/dossier.py:298(live_frame)` | 4800 | 0.8 | 51.4 |
| 15 | `stream/backtest/banco_comune.py:1931(applica_book)` | 504571 | 2.9 | 43.5 |
| 16 | **`flumine/baseflumine.py:475(info)`** | 417428 | 3.4 | **43.4** |
| 17 | `mike/dossier.py:241(lambdas_con_ripiego)` | 4732 | 0.1 | 41.7 |
| 18 | **`omega/omega_model.py:131(lambdas_from_pre_ko)`** | 4732 | 0.1 | **41.5** |
| 19 | `omega/omega_model.py:188(split_lambdas_1x2)` | 156156 | 7.2 | 40.4 |
| 20 | `omega/omega_model.py:155(total_goals_from_1x2)` | 4732 | 0.3 | 40.0 |

Altri punti caldi: `banco_comune.libro_di_produzione` 59724 chiamate, 22,3 s (5,8 %), di cui
`_livelli_di_produzione` 768495 chiamate (un terzo per il traded volume che lo scanner non
legge mai); `porta_banco._specchio` 13,3 s con un import relativo a ogni book (515763
`importlib._bootstrap.parent`).

### DOPO (`_perf/dopo_finale.prof`, 105 s profilati)

| # | funzione | chiamate | proprio s | cumulato s |
|---|---|---|---|---|
| 1-8 | `certifica.py` / `replay_registrazioni.certifica_*` | 1-2 | 0.0 | 100.1 |
| 9 | `porta_banco.py:187(recv)` | 122 | 1.4 | 96.6 |
| 10 | `flumine/utils.py:261(call_strategy_error_handling)` | 1004267 | 0.5 | 57.8 |
| 11 | `trasporto.py:226(_process_market_book)` | 502123 | 1.5 | 57.2 |
| 12 | `mike/tools/replay_registrazioni.py:523(process_market_book)` | 502123 | 1.9 | 50.9 |
| 13 | `mike/tools/replay_registrazioni.py:567(_un_giro)` | 5824 | 0.3 | 33.8 |
| 14 | `banco_comune.py:1479(_a_flumine)` | 643713 | 3.6 | 33.6 |
| 15 | `mike/service.py:4229(_run_event)` | 5824 | 0.8 | 22.9 |
| 16 | `flumine/utils.py:289(call_middleware_error_handling)` | 1009142 | 0.8 | 14.9 |
| 17 | `banco_comune.py:1990(applica_book)` | 504571 | 1.3 | 12.3 |
| 18 | `flumine/baseflumine.py:353(_process_close_market)` | 139142 | 2.1 | 10.8 |
| 19 | `banco_comune.py:2048(pubblica)` | 5824 | 0.1 | 8.7 |
| 20 | `safe_strategy/service.py:1858(build_rows)` | 5824 | 0.2 | 8.4 |

`lambdas_from_pre_ko` e `BaseFlumine.info` sono spariti dalla classifica.

## 3. Cosa ho cambiato e perche' (solo tempo, nessun numero cambia)

1. **`Betfair/omega/omega_model.py:131-162`** - `lambdas_from_pre_ko` delega a
   `_lambdas_da_quote_1x2` (`:147`), `functools.lru_cache(maxsize=CACHE_GRIGLIE, typed=True)`
   con chiave `(home, draw, away, total_goals, rho)` cosi' come arrivano. Funzione PURA (solo
   costanti di modulo), risultato tupla immutabile o None; le quote pre-KO sono congelate dallo
   scanner, quindi Mike la chiedeva 4.732 volte con lo stesso ingresso (doppia bisezione:
   ~11 % del replay). Quota non hashabile -> calcolo senza cache. Stesso schema delle tre cache
   pure del 16/09 nello stesso file. Vale anche per Omega/Safe (stessa funzione, stessi numeri).
   Ritocco a `Betfair/omega/test_omega_cache_pura_2026_09_16.py:51-53`: l'helper che spia il
   fondo della catena svuota anche la cache nuova (altrimenti la seconda raccolta non arrivava
   al fondo e 6 test fallivano a vuoto; con lo svuotamento tornano 13/13).
2. **`Betfair/stream/backtest/banco_comune.py:1176-1210`** - `info_flumine_solo_se_loggata()`,
   montata dentro `simulazione_flumine()` (`:1231`, accanto a `orologio_monotono`) e smontata
   all'uscita. `BaseFlumine.info` (417.428 chiamate, ~11 %) serve solo come `extra=` dei
   `logger.info` di chiusura/rimozione mercato, e Python la valutava anche a livello INFO
   spento. Log INFO di flumine acceso -> la `info` vera; spento (il banco gira a WARNING,
   `certifica.py:416,618`) -> `{}`. Nessun codice la legge fuori dai log. Unico record che
   nasce comunque: il WARNING "Market ... not present when closing/clearing", testo identico
   (provato), perde solo gli attributi extra, che il formato del banco non stampa.
3. **`banco_comune.py:384-415`** - `_VistaEx.traded_volume` diventa una property: la scala si
   converte solo se qualcuno la legge (lo scanner vero non la legge: `grep traded_volume` in
   `safe_strategy/` = solo test), presa all'istante della vista (non si rilegge `ex`), con
   setter che si comporta come il campo di prima (anche `None`).
4. **`banco_comune.py:1838, 2010, 2013-2040`** - `ScannerReplay._vista_di`: `GeneratoreLibri`
   riemette lo STESSO oggetto `MarketBook` finche' il mercato non cambia; la vista per lo
   scanner si riusa solo se (a) e' lo stesso oggetto (`is`, e il book resta referenziato:
   l'id non puo' passare ad altri) e (b) il book e' gia' convertito in EUR
   (`size_gbp_convertite is True`). La conversione e' l'unica mutazione di un book dopo la
   nascita (grep di assegnazioni a campi di book/runner/ex fuori dai test: solo `valuta.py`);
   un book non convertito si rifa' sempre. Lo scanner legge la vista e non la trattiene.
5. **`Betfair/stream/backtest/porta_banco.py:84, 707-714`** - `_specchio` prende
   `LiveTradingStrategy` una volta sola (global `_LTS`) invece dell'import relativo a ogni
   book (502.129 volte). Stessa classe.

Punti che altri delegati toccano oggi: non ho toccato `mike/feed.py`, `service.py`,
`engine.py`, `certificazione.py`, `tools/replay_registrazioni.py`, ne' il ramo CLOSED di
`_a_flumine`/la leva di rifiuto in `banco_comune.py`. I miei blocchi in `banco_comune.py`
sono aggiunte in zone separate (classe `_VistaEx`, `simulazione_flumine`, `ScannerReplay`).

## 4. Prova: referto `base` prima e dopo

Confronto con `_perf/confronta.py` (tolte le righe `tempo:` / `TEMPO TOTALE` / cronometro):

- `base_prima_2` (worktree PRIMA di ogni modifica) vs `base_dopo_1`, `base_dopo_2`,
  `base_prof_finale` (DOPO, anche sotto cProfile): **0 righe diverse su 89**.
- misura alternata (`_perf/misura_alternata.ps1`: i 3 file di HEAD rimessi nel worktree, poi i
  miei, 3 giri): `alt2_prima_1..3` e `alt2_dopo_1..3` tutti **identici** a `base_prima_2`.
  Stesse righe: `tick= 56098 decisioni= 5804 azioni= 6`, stati, `ordini reali piazzati: 5`,
  attivita' del servizio (`uscita_proposta x17`, `uscita_proposta_decaduta x15`, ...), righe per
  stato `{'open': 2, 'error': 3}`, fill `2 abbinamenti ... 14.0 EUR (prezzi [1.71, 4.0])`,
  P&L `NETTO -14.00`, bet delay/book in ritardo `560388`, letture `150`, righe di scan `2464`,
  motivi (`tengo x2433` ...), copertura controlli (A1 x5804 ... K4 x5795), 15 mai sollecitati.
- Tempi dei 6 giri alternati: PRIMA 100,0 / 77,9 / 82,7 s; DOPO 85,6 / 59,0 / 52,0 s.

Avvertenza metodologica: un primo tentativo di "prima" da un albero estratto con `git archive`
in `_perf/prima_tree` dava un referto DIVERSO (`uscita_proposta x11`, `tengo x2253`, G3 x2267)
anche col codice di HEAD: qualche risorsa si trova per percorso relativo al file e da quella
cartella non si trovava. Scartato; i confronti validi sono tutti nello stesso worktree.

## 5. Test

- Nuovo: `Betfair/stream/tests/test_banco_prestazioni_2026_09_30.py`, 15 test (equivalenza
  cache/senza cache dei lambda su 8 forme di pre-KO, chiave che usa ognuno dei 5 argomenti,
  `info` vera con INFO acceso, vuota e ripristinata a INFO spento, testo del WARNING uguale,
  traded volume pigro = eager / preso all'istante / assegnabile, vista riusata solo per lo
  stesso book convertito, book non convertito rifatto e conversione visibile). Finti veri:
  `MarketBook` di betfairlightweight (scale dict di flumine), `FlumineSimulation`,
  `ClearedOrders`, `valuta.converti_libro`. 15 passed.
- Falsificazione (`_perf/falsifica.py`, file salvato in memoria e rimesso nel finally, hash
  verificato uguale alla copia DOPO): M1 chiave senza `rho` ROSSO; M2 `info` sempre vuota ROSSO;
  M3 `info` non ripristinata ROSSO; M4 vista in cache anche non convertita ROSSO; M5 vista
  riusata per un book diverso ROSSO; M6 traded volume perso ROSSO; dopo il ripristino 15 passed.
- Suite (ambiente neutro, a pezzi): `Betfair/stream/backtest` 52 passed; `Betfair/mike` 1222
  passed; `Betfair/omega` 1418 passed, 3 skipped; 17 file `Betfair/stream/tests/*`
  (banco/porta_banco/valuta/trasporto/certifica) 298 passed, 25 skipped; altri 8 file di
  `safe_strategy/tests` e `stream/tests` che usano `lambdas_from_pre_ko`/`banco_comune`/
  `porta_banco`/`simulazione_flumine` 181 passed.

## 6. Parita' paper/live

Nessun cambiamento di comportamento: le modifiche 2-5 esistono solo nel banco; la 1 e' una
memoizzazione pura usata da Mike, Omega e Safe in paper E live allo stesso modo (stesso
numero, provato), niente rami paper/live.

## 7. Cosa resta caro (non toccato, fuori perimetro o codice di produzione)

- **Mercati CLOSED rielaborati a ogni aggiornamento**: `_process_close_market` 139.142 chiamate
  per pochi mercati chiusi (dopo la chiusura `GeneratoreLibri` riemette lo stesso book CLOSED a
  ogni riga, e flumine lo richiude: blotter, cleared orders, `_remove_market`). Oggi ~10 % del
  profilo. Lo fa anche `FlumineSimulation._process_market_books` originale, quindi saltarlo e'
  un cambio di semantica da decidere, ed e' la zona del delegato "mercato CLOSED": non toccata.
  E' il prossimo candidato (con test di equivalenza del referto).
- `valuta.converti_libro` (~6 %), `scanner.payload_signature` (json + `_senza_campi_rumorosi`,
  ~5 %), il motore di Mike, il `SimulatedMiddleware` di flumine: codice di produzione/libreria.
- `replay_registrazioni.process_market_book` (per-book, `datetime.timestamp` 502k volte): file
  toccato oggi da un altro delegato.

## 8. COSA NON HO POTUTO VERIFICARE

- **Il replay completo dei 21 scenari** (non lanciato, come da brief): la stima ~350 s e'
  un'estrapolazione dal solo `base`; gli altri scenari potrebbero guadagnare di piu' o di meno
  (es. `bot-fermo`/`feed-stantio` hanno 1006 decisioni: meno peso dei lambda, stesso peso di
  `info`). Referto identico provato SOLO su `base`: gli altri 20 scenari vanno confrontati dal
  coordinatore con `certifica.righe_senza_tempi` contro `mike_tutti_P5_4C.txt` (o un referto
  PRIMA rifatto oggi, visto che nel frattempo il codice di Mike puo' essere cambiato).
- Tempi assoluti a PC libero: il PC era carico per tutta la sessione; i numeri sono minimi di
  3 giri alternati, non misure a macchina ferma.
- Il trasporto `coda`/`entrambi` e gli altri bot (Omega, Safe, scalper, tennis) che usano lo
  stesso banco: solo test di suite, nessun loro replay.
- L'invarianza "un book convertito non cambia piu'" (base della cache delle viste) e' provata
  per ispezione (grep delle assegnazioni, cache di betfairlightweight che crea oggetti nuovi) e
  dal referto identico, non da un controllo a runtime.
- I file di lavoro sono in `_perf/` (non tracciato): script di misura, profili, referti.
