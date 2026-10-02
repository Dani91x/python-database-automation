# REPLAY VELOCE (02/10) - banco di certificazione, PROCESSO_STANDARD_BOT par. 6.9

Ramo `replay-veloce`, worktree `agent-a3973176466e94888`. Lavoro fatto su master `4220397`,
poi RIBASATO su master `9a3a42e` (master era andato avanti: banco ottimista, minimi .it).
Patch: `AUDIT_2026-10-02/REPLAY_VELOCE.patch` (`git diff 9a3a42e`, la base del ramo).

STATO AL 16:20: FINITO. Tre correzioni nel solo banco (`banco_comune.py`), referti identici
su 9 confronti (5 sulla base vecchia, 4 sulla nuova), test e falsificazione come attesi.
`mike tutti` sotto il TETTO a PC non saturo (530,7 s) ma NON sotto l'obiettivo di 300 s:
il resto del tempo sta in flumine e nel codice di produzione (sezione 6), fuori perimetro.

## 0. Ribasatura su master `9a3a42e` (dopo le misure delle sezioni 1-5)

- Un solo conflitto, in `simulazione_flumine` (la riga `with`): master aggiungeva
  `minimi_it_su_flumine()` (che sostituisce solo `SimulatedExecution.execute_place/replace`,
  nessuna sovrapposizione), io `chiusura_flumine_senza_resoconti_muti()`: tenute tutte e due.
- Sulla base nuova, rilanciati: test del banco 617 verdi / 25 saltati (registrazioni assenti
  nel worktree), falsificazione 9 ROSSE su 9, e i quattro replay PRIMA3 (banco di `9a3a42e`)
  / DOPO3 (ramo), tutti a confronto con 0 righe diverse tolti i tempi:

| confronto (base `9a3a42e`) | righe | diverse | tempo PRIMA3 -> DOPO3 |
|---|---|---|---|
| `mike tutti` | 726 / 726 | 0 | 749,9 -> 665,0 s (carico 38 % -> 99 % all'avvio) |
| `mike base,riavvio,feed-stantio` | 152 / 152 | 0 | 113,8 -> 93,7 s |
| `safe_base rapidi entrambi` | 94 / 94 | 0 | 119,8 -> 120,9 s |
| `omega base` | 130 / 130 | 0 | 45,8 -> 46,6 s |

  Il KO `lettura-dati-ko` (sezione 7) c'e' anche sulla base nuova, PRIMA3 e DOPO3 uguali.

## 1. In breve

| | PRIMA (banco di master) | DOPO | |
|---|---|---|---|
| `mike tutti`, PC carico (prima coppia) | 903,7 s (somma scenari 2568 s) | 788,0 s (2110 s) | -12,8 % parete |
| `mike tutti`, PC meno carico (seconda coppia) | **708,8 s** (2061 s) | **530,7 s** (1538 s) | **-25,1 %**, sotto il tetto 600 |
| A/B stesso processo, `mike base`, tempo CPU (2+2 giri alternati) | 53,7 s | 41,5 s | **-22,7 %** |
| `mike base,riavvio,feed-stantio` | 107,5 s | 66,1 s | -38 % (carico diverso) |
| `safe_base --scenari rapidi --trasporto entrambi` | 116,4 s | 77,7 s | -33 % (carico diverso) |
| `omega base` | 29,2 s | 30,5 s | = (Omega non passa dai punti corretti) |

Il PC era condiviso con altre sessioni (carico 40-100 %): i tempi di parete fra coppie
diverse NON sono confrontabili; il numero solido e' l'A/B in CPU nello stesso processo
(`replay/misura_ab_base_tutte.txt`) e la seconda coppia PRIMA2/DOPO2 lanciata a carico simile.

Referti: nessuna differenza tolte le righe dei tempi (sezione 4). Tutti i numeri di
condotta (tick, decisioni, azioni, P&L, violazioni, coperture dei controlli) uguali.

## 2. Misura di base: i 10 punti caldi (cProfile, `mike 35760084 --scenari base`)

Profilo nello stesso processo con la strada di `certifica` (`profila_scenario.py`):
`replay/mike_base_PRIMA.prof` (+ `_profilo.txt`), 204,9 s con profilo (~80-90 s senza).
Il profilo di `mike tutti` con la pool non e' misurabile dal padre (`--worker 0` = 3 processi
figli): si e' profilato lo scenario rappresentativo, tutti gli scenari hanno la stessa catena.

| # | funzione (file:riga) | cumulato | chiamate | di chi |
|---|---|---|---|---|
| 1 | `process_market_book` (`mike/tools/replay_registrazioni.py:641`) | 101,4 s | 464.213 | contenitore (banco + produzione) |
| 2 | `MotoreReplay._a_flumine` (`stream/backtest/banco_comune.py:1741`) | 83,5 s | 643.713 | banco |
| 3 | `service._run_event` (`mike/service.py:4588`) | 48,7 s | 5.847 | PRODUZIONE Mike |
| 4 | `BaseFlumine._process_close_market` (`flumine/baseflumine.py:353`) | 36,7 s | 139.142 | flumine, chiamato dal banco |
| 5 | middleware di flumine (`flumine/utils.py:289`): `valuta.__call__` 15,6 + `SimulatedMiddleware` 13,1 | 30,5 s | 1.009.142 | produzione / flumine |
| 6 | `ScannerReplay.applica_book` (`banco_comune.py:2276`) -> `Scanner._apply_market_book` 14,9 | 24,9 s | 504.571 | banco -> scanner di produzione |
| 7 | `ScannerReplay.pubblica` (`banco_comune.py:2334`) -> `build_rows` 16,2 -> `payload_signature` 9,8 | 16,8 s | 5.847 | scanner di produzione |
| 8 | `GeneratoreLibri.veloce` (`banco_comune.py:1601`): parse + cache betfairlightweight | 13,0 s | 30.654 righe | banco/betfairlightweight |
| 9 | `process_closed_market` (`replay_registrazioni.py:612`) -> `registra_libro_chiuso` (`banco_comune.py:1217`) 10,0 | 11,5 s | 139.142 | banco |
| 10 | `MotoreReplay.consuma_tempo` (`banco_comune.py:1977`) | 9,3 s | 1.860 | banco (tempo di mercato delle letture: legittimo) |

La radice dei punti 4 e 9: flumine riemette a OGNI riga della registrazione il book di
OGNI mercato attivo (30.654 righe -> 643.713 book), compreso il book CLOSED dei mercati
gia' chiusi (139.142 riconsegne, il 22 % dei book). Il banco lo fa di proposito (fedelta' a
`FlumineSimulation`, `GeneratoreLibri`), e NON va cambiato: e' il ritmo con cui flumine
controlla i pacchetti in bet delay. Si e' tolto il lavoro ripetuto SU quei book, non i book.

## 3. Le correzioni (solo `Betfair/stream/backtest/banco_comune.py`)

Ognuna ha un interruttore di modulo (la via lenta resta, per i test e la falsificazione).

**C1 - libro finale del mercato chiuso riusato** (`MercatoFlumine.registra_libro_chiuso`,
righe 1226-1250 e 1283; interruttore `RIUSA_LIBRO_CHIUSO`, riga 1678). Il replay di Mike la
chiama a ogni riconsegna del book CLOSED e la rifaceva ogni volta. Ora si riusa SOLO se:
stesso oggetto (`is`, tenuto referenziato), stesso stato di conversione EUR
(`size_gbp_convertite`), e in `libri_chiusi` c'e' ancora quel libro. Profilo:
`registra_libro_chiuso` 10,0 -> 2,7 s; `process_closed_market` 11,5 -> 3,8 s.

**C2 - regole di lapse non ricalcolate sullo stesso book** (`MotoreReplay._a_flumine`, righe
1934-1952; `_ultimo_book_lapse` in `__init__`; interruttore `RIUSA_LAPSE`, riga 1684). Se
l'ultimo book passato per quel mercato e' lo STESSO oggetto, `_lapse_al_fischio` e
`_lapse_alla_sospensione` tornerebbero 0 riscrivendo gli stessi valori: si salta il calcolo,
non il book (`market(market_book)`, middleware, strategia restano). Profilo: 4,5 -> 0,7 s
(504.571 -> 65.424 chiamate).

**C3 - chiusura del mercato senza i resoconti simulati che nessuno ascolta**
(`_chiudi_mercato_senza_resoconti`, righe 1520-1592; `chiusura_flumine_senza_resoconti_muti`,
righe 1595-1619, montata in `simulazione_flumine` riga 1642; interruttore
`CHIUSURA_SENZA_RESOCONTI_MUTI`, riga 1502). Stesso schema gia' accettato il 30/09 per
`info_flumine_solo_se_loggata`. `BaseFlumine._process_close_market` in simulazione fabbrica a
ogni chiamata un `ClearedOrdersEvent` VUOTO e un `ClearedMarketsEvent` per client: li legge
solo un logging control (`log_control`) o il log INFO di flumine; il blotter con la lista vuota
non assegna nulla (`blotter.py:176-184`). La copia e' riga per riga quella di flumine 2.13.11
meno quel blocco; si usa SOLO se nessun logging control e' montato, l'INFO di flumine e' spento
e l'impronta sha256 del sorgente di flumine e' quella copiata (altrimenti la funzione vera).
Restano: `market(market_book)`, `blotter.process_closed_market`, `strategy.process_closed_market`
di ogni strategia, `log_control`, `_remove_market`. Profilo: 36,7 -> 11,2 s; costruzioni di
risorse betfairlightweight 635.275 -> 217.849.

Totale profilo `mike base`: 204,9 -> 159,1 s (`replay/mike_base_DOPO.prof`,
`profilo_prima_dopo.py` per il confronto funzione per funzione). Misura senza profilo (A/B,
`misura_ab.py`): C1+C2 da sole -3,8 % CPU (`replay/misura_ab_base.txt`, PC carico); C1+C2+C3
-22,7 % CPU (`replay/misura_ab_base_tutte.txt`), numeri di condotta identici in tutti i giri.

## 4. Prova di identita' dei referti

`confronta_referti.py` (quello del 01/10, copiato in `AUDIT_2026-10-02/`) con DUE regole in
piu', entrambe di tempo e documentate nel file: la riga `LENTO:` (e' fra
`certifica.PREFISSI_RIGHE_TEMPI`) e gli id di 18 cifre `'1xxxxxxxxxxxxxxxxx'`, che sono
`str(uuid.uuid1().time)` di flumine (`flumine/order/order.py:78`) = l'ora del PC: compaiono
nell'esito di un ordine void di `cashout-dopo-copertura` e cambiano a OGNI esecuzione anche
dello stesso codice (diversi anche fra i referti del 01/10). Prima di quella regola l'unica
riga diversa era quella, nel solo pezzo dell'id (`diff_righe.py`).

| confronto | righe | diverse |
|---|---|---|
| `mike_tutti_PRIMA` vs `mike_tutti_DOPO` | 724 / 724 | 0 (`replay/confronto_mike_tutti_PRIMA_DOPO.txt`) |
| `mike_tutti_PRIMA` vs `mike_tutti_DOPO2` | 724 / 723 | 0 (manca solo la riga `LENTO:`: sotto il tetto non si stampa) |
| `mike_tutti_PRIMA` vs `mike_tutti_PRIMA2` (stesso codice) | 724 / 724 | 0 |
| `mike_base_riavvio_stantio` PRIMA vs DOPO | 149 / 149 | 0 |
| `safe_base_rapidi_entrambi` PRIMA vs DOPO | 94 / 94 | 0 |
| `omega_base` PRIMA vs DOPO | 130 / 130 | 0 |

I PRIMA sono stati girati col `banco_comune.py` di master rimesso nel worktree
(`git checkout master -- ...`) e poi ripristinato (verificato: `git status` pulito).
I referti dei tre replay piccoli `powershell.exe` li salva in UTF-16: convertiti in UTF-8
con `in_utf8.py` (contenuto invariato) prima del confronto.

## 5. Test e falsificazione

- Nuovo `Betfair/stream/tests/test_banco_replay_veloce_2026_10_02.py`: 12 test, oggetti
  VERI (`MarketBook`/`MarketDefinition` di betfairlightweight, `FlumineSimulation`,
  `Trade`/`LimitOrder`, `LoggingControl` di flumine, `valuta.converti_libro` col cambio del
  banco). Equivalenza veloce = lenta per C1, C2, C3; casi stantii.
- Falsificazione (`falsifica_replay_veloce.py`, uscita `falsifica_replay_veloce_out.txt`):
  9 mutazioni, **9 ROSSE su 9**, sorgente ripristinato e md5 verificato dopo ognuna:
  M1 memoria del libro per market_id; M2 ignora la conversione EUR; M3 ignora chi ha
  sostituito il libro; M4 lapse per market_id; M5 lapse che non si aggiorna; M6 muta anche
  con un logging control; M7 muta anche con INFO acceso; M8 la copia non consegna la
  chiusura alla strategia; M9 la copia non regola gli ordini del blotter.
- Test del banco (`Betfair/stream/tests` che importano il banco + `Betfair/stream/backtest`):
  603 verdi, 25 saltati per registrazioni assenti nel worktree; quei 25 (identita' via
  veloce/lenta, lapse sulla registrazione vera, campioni `certifica` di mike, omega,
  safe_base/esatto/punta, scalper) rilanciati con una COPIA (non un collegamento) di
  `35833626`, `35823616`, `_synth_safe_tennis_prezzo_migliore` nel worktree: **54 verdi, 0
  saltati**; copia poi rimossa, originali verificati.
- Test di Mike/Omega/Safe/tennis che importano il banco (16 file): 491 verdi, 3 saltati
  (registrazioni assenti nel worktree).

## 6. Punti caldi lasciati (fuori perimetro) e cosa servirebbe per i 300 s

Dopo le correzioni (`mike_base_DOPO.prof`, 159 s con profilo):

| punto | cumulato | dove | stima del guadagno se si toccasse |
|---|---|---|---|
| `service._run_event` | 43,4 s | PRODUZIONE Mike: `dossier.live_frame` 7,6, `_sorveglia_posizione_di_conto` 4,9, `decide` ~4,8, `feed.snapshot_from_row` ~3,4, `_persist` ~2,4 | nessuno e' spreco puro; strutture ricalcolate a ogni giro (live_frame, snapshot) memoizzabili per riga invariata: stima 5-8 % |
| `scanner.payload_signature` (`safe_strategy/scanner.py:577`) | 9,1 s | PRODUZIONE scanner: ricorsione `_senza_campi_rumorosi` + `json.dumps` a ogni giro | firma incrementale o confronto senza serializzare: stima 4-5 % |
| middleware: `valuta.__call__` + `SimulatedMiddleware` | 28,1 s | produzione / flumine, su ogni book riemesso | non toccabile senza cambiare la fedelta' a flumine |
| `Scanner._apply_market_book` | ~15 s | produzione: il banco gli riconsegna anche i book IDENTICI (lo scanner aggiorna gli orari di freschezza: NON idempotente, non saltabile) | 0 senza cambiare il referto |
| `GeneratoreLibri.veloce` + conversione EUR dei book nuovi | ~12 + ~10 s | banco/betfairlightweight, rifatti per OGNI scenario sulla stessa registrazione | riuso dei book fra scenari nello stesso processo: stima 10-12 % sugli scenari dopo il primo di ogni worker; NON fatto: memoria (65.445 book per scenario) e rischio di contaminazione fra scenari che modificano i book; da decidere |
| pool `--worker 0` = 3 processi | - | `certifica.quanti_processi`: tetto `core_fisici - 1` | 4 processi: stima -20/-25 % di parete; NON fatto: ordine dell'utente del 24/09 sul carico del PC |

Conclusione onesta: col solo banco il traguardo dei 300 s per `mike tutti` (26 scenari) non
si raggiunge; si e' rientrati sotto il tetto di 600 s a PC non saturo. Per scendere a 300 s
servono, insieme, almeno due fra: ritocchi di produzione (Mike + scanner, ~10-13 %), riuso
dei book fra scenari (~10 %), un processo in piu' (~20 %). Tutti richiedono una decisione.
Lo standard 6.9 scritto parla di `--worker 1`: 26 scenari x ~60 s = ~26 minuti, irraggiungibile
senza cambiare l'architettura del banco (scenari che condividono il tratto comune).

## 7. Reperti (non miei, trovati misurando)

- **KO preesistente su master**: `mike 35760084 --scenari tutti` (trasporto coda di default)
  esce con exit 1 per `lettura-dati-ko`: P1 x1 «under_green lay 10.12 @ 1.69 riproposta 373
  volte di fila», P2 x1 (stesse violazioni PRIMA e DOPO; sul canale il 01/10 era OK). Da
  guardare a parte: e' condotta di Mike, non del banco.
- Il referto contiene un id di ordine flumine basato sull'ora del PC (`uuid1().time`): il
  referto non e' rifacibile identico byte per byte (par. 6.8). Proposta: stampare il
  `customer_order_ref` del banco o normalizzare quell'id nel referto.
- `powershell.exe` 5.1 salva i referti con `>` in UTF-16: chi confronta deve convertire.

## 8. NON VERIFICATO

- Tempi di parete su PC libero: le misure sono state fatte con altre sessioni attive.
- `--trasporto canale` e `--worker 1` di `mike tutti` non rilanciati (C3 vale su ogni via;
  le prove di identita' sono sul trasporto di default, sui tre piccoli e su safe entrambi).
- Bot tennis e scalper: solo i campioni della suite (`test_cert_banco`), nessun `tutti`.
- Profilo `mike tutti` dentro i figli della pool: profilato lo scenario base nello stesso processo.
