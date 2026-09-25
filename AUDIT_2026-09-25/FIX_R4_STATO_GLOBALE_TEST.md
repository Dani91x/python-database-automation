# FIX R-4 — stato globale di flumine.config che si trascina fra test (25/09/2026)

Riferimento: `AUDIT_2026-09-25/TENNIS_UNIFICAZIONE_E_SAFE_CANALE.md`, reperto R-4.
Perimetro: SOLO test (`Betfair/conftest.py`). Nessun codice di produzione toccato.

## 1. Causa, con file:riga

`flumine.config` e' un **modulo Python**, cioe' uno stato globale DI PROCESSO (non
per istanza di `Flumine`/`Framework`). In produzione questo non e' mai un problema:
un processo porta un solo bot in una sola modalita' per tutta la sua vita. Nei test,
nella STESSA sessione pytest, diversi test fanno girare codice di produzione che
scrive su `flumine.config` senza mai ripristinarlo:

- `Betfair/stream/tennis_live/tennis_runner.py:159` — `build_order_client(mode="PAPER")`
  esegue `flumine_config.place_latency = max(0.0, lat) / 1000.0` (default
  `TENNIS_PAPER_LATENCY_MS_DEFAULT` = 600 ms).
- `Betfair/stream/tennis_live/guardie_tennis.py:178` — stessa scrittura sullo stesso
  campo, dalle guardie a caldo (riarmo di un bot mentre il runner gira).
- `Betfair/stream/runner.py:1537` e `:1580` — la stessa cosa per il runner calcio
  (`PAPER_SIMULATED_LATENCY_MS`).

Il test che ha innescato il reperto,
`Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py:163`
(`client, _on = TR.build_order_client(api, mode)`), chiama `build_order_client` di
produzione VERO (giusto: e' li' che si certifica il comportamento) ma non salva ne'
ripristina `flumine.config.place_latency` intorno alla chiamata — il test non ha
motivo di saperlo, e' un dettaglio del codice che sta esercitando. Il risultato:
`flumine.config.place_latency` resta a `0.6` per TUTTO il resto del processo pytest.

Il test successivo,
`Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::
test_profilo_rapido_verde_sulla_registrazione_vera[omega]`, passa dal profilo
rapido del banco comune (`Betfair/stream/backtest/trasporto_rapido.py::esegui_scenari`),
che confronta i tempi attesi degli scenari (R1-R9 + R2b) contro
`place_latency + betDelay` COSI' COM'E' in quel momento — con `place_latency = 0.12`
(default di flumine) lo scenario R3 (parziale) e' verde, con `0.6` (ereditato dal
tennis) il fill parziale non arriva in tempo entro la finestra attesa dello scenario
e lo scenario cade con `PAPER senza FOK: abbinato in parte, residuo vivo` /
`evento intermedio (non terminale)`. Da solo il test e' verde perche' nessun altro
test ha ancora toccato `flumine.config` in quella sessione.

## 2. Test che inquinano stato globale (o env) senza ripristino — mappa completa

Cercato con `grep` su `flumine.config.`, `flumine_config.`, `fconf.`,
`_flumine_config.` e su scritture dirette di `os.environ[...]` in tutti i
`test_*.py` sotto `Betfair/`.

**Il colpevole del reperto (nessun ripristino, ne' diretto ne' via `monkeypatch`):**

- `Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py:163`
  — chiama `TR.build_order_client(api, "PAPER")` di produzione, che scrive
  `flumine_config.place_latency`, senza salvare/ripristinare il valore precedente.

**Altri test che scrivono su `flumine.config` ma GIA' si ripristinano da soli**
(verificato riga per riga: o `try/finally` con `prima = fconf.X; ...; finally:
fconf.X = prima`, o `monkeypatch.setattr`, che pytest disfa da solo a fine test —
questi NON sono la causa del reperto, ma restano documentati qui perche' la fixture
nuova li rende ridondanti come rete di sicurezza, non perche' siano rotti):

- `Betfair/stream/tennis_live/tests/test_modalita_e_guardie_tennis_2026_09_24.py:61`
  (`monkeypatch.setattr`)
- `Betfair/stream/tennis_live/tests/test_motore_ordini_tennis_2026_09_25.py:98-100`
  (`prima = fconf.place_latency` / ripristinato)
- `Betfair/stream/tennis_live/tests/test_paper_execution_gap5.py` (sola lettura,
  nessuna scrittura)
- `Betfair/stream/tennis_live/tests/test_tennis_audit_runner.py:255-275`
  (`orig = ...` / ripristinato)
- `Betfair/stream/tennis_live/tests/test_tennis_hardening.py:39`
  (`monkeypatch.setattr`)
- `Betfair/stream/tests/test_banco_comune_2026_09_16.py` (piu' punti: `prima =
  fconf.simulated; ...; finally: fconf.simulated = prima`, sempre ripristinato)
- `Betfair/stream/tests/test_banco_identita_2026_09_16.py:530` (sola lettura)
- `Betfair/stream/tests/test_paper_live_stesso_processo_2026_09_16.py:386-394`
  (`latenza_prima = ...` / ripristinato)
- `Betfair/stream/tests/test_runner_live_strategy.py:84-104` (`prev = ...` /
  ripristinato in entrambi i casi)

**Env di processo**: cercato `os.environ[...] = ` senza `monkeypatch` nei test:
nessuna scrittura diretta non ripristinata trovata (solo letture/asserzioni, es.
`test_strada_unica_banco_2026_09_25.py:348-352`, e una stringa dentro un sorgente
per sottoprocesso). `test_misura_punto8.py:13` fa
`os.environ.update({"SUPABASE_URL": ..., "SUPABASE_SERVICE_ROLE_KEY": "x", ...})`
a livello di modulo, ma con GLI STESSI valori gia' imposti dalla sandbox — innocuo,
fuori perimetro (non e' env che altri test possano leggere di diverso).

Conclusione: l'UNICA fonte di inquinamento reale per R-4 e' `flumine.config`
scritto da codice di produzione (tennis e calcio) senza che il chiamante-test lo
sappia. La fixture nuova copre esattamente questo, e in piu' fa da rete di
sicurezza per qualunque test futuro che dimentichi il proprio `try/finally`.

## 3. Fix

`Betfair/conftest.py` — nuova fixture autouse `_ripristina_flumine_config` (prima
di `_kill_switch_del_db_senza_rete`, gia' presente). Fotografa **tutti** gli
attributi pubblici di `flumine.config` (`place_latency`, `cancel_latency`,
`replace_latency`, `update_latency`, `simulated`, `simulation_available_prices`,
`simulated_strategy_isolation`, `current_time`, `async_place_orders`,
`customer_strategy_ref`, `execution_retry_attempts`, `max_execution_workers`,
`order_sep`, `process_id`, `raise_errors`, `os`) PRIMA di ogni test e li ripristina
DOPO, con `setattr` diretto — non serve whitelist perche' e' un module-namespace
dump/restore generico, resiste anche a un futuro campo nuovo aggiunto a monte da
flumine. E' in `Betfair/conftest.py` (radice della cartella `Betfair/`, non in uno
dei conftest di sottocartella) perche' deve valere sia per `Betfair/stream/tests/`
sia per `Betfair/stream/tennis_live/tests/`: sono cartelle sorelle, un conftest in
una delle due non avrebbe protetto l'altra. Verificato che non esiste gia' un
conftest in `Betfair/stream/tennis_live/tests/` (nessun file trovato) ne' un
meccanismo equivalente altrove.

## 4. Prova — prima/dopo, comando riproducibile

Ambiente sandbox usato in tutte le esecuzioni:
`SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x`

Comando di riproduzione (identico a quello del reperto):

```
python -m pytest \
  Betfair/stream/tennis_live/tests/test_tennis_iscrizione_a_caldo_2026_09_25.py \
  "Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera[omega]" \
  -q -p no:cacheprovider
```

**Prima del fix** (verificato di nuovo oggi, stessa causa, per riconfermare il
reperto prima di intervenire): ROSSO, con lo stesso identico errore del reperto R-4
(`R3 parziale`, `PAPER senza FOK: abbinato in parte, residuo vivo` /
`evento intermedio (non terminale)`).

**Dopo il fix** (con `_ripristina_flumine_config` attiva in `Betfair/conftest.py`):

```
...............................................                          [100%]
47 passed in 10.53s
```

`test_profilo_rapido_verde_sulla_registrazione_vera[omega]` risulta **PASSED**
(confermato con `-v`, non SKIPPED: la registrazione `35760084` e' presente su
questa macchina e lo scenario e' stato eseguito davvero), tutti i 46 test tennis
restano verdi.

## 5. Falsificazione (obbligatoria)

Fixture disattivata temporaneamente (`@pytest.fixture(autouse=False)` sulla stessa
definizione, nessun'altra modifica), stesso comando di riproduzione:

```
..............................................F                          [100%]
FAILED Betfair/stream/tests/test_strada_unica_banco_2026_09_25.py::test_profilo_rapido_verde_sulla_registrazione_vera[omega]
AssertionError: [('R3 parziale', [('PAPER senza FOK: abbinato in parte, residuo vivo', False, "('inviato', 0.0, 70.67)"),
                                   ('evento intermedio (non terminale)', False, 'inviato')], None)]
1 failed, 46 passed in 10.05s
```

Torna ROSSO, con lo stesso scenario (`R3 parziale`) e lo stesso motivo del reperto
originale: la fixture e' davvero la causa della guarigione, non una coincidenza.
Fixture poi riattivata (`autouse=True`) e riconfermata verde (§4).

## 6. Suite completa — nessuna regressione dal fix

`python -m pytest Betfair/ -q -p no:cacheprovider` (SUPABASE_URL sandbox):

```
3 failed, 7061 passed, 31 skipped, 1 xfailed, 4 warnings in 225.43s
```

I 3 fallimenti sono **preesistenti e indipendenti dal fix** — verificato mettendo
da parte la modifica (`git stash` sul solo `Betfair/conftest.py`, poi
`git stash apply`/`drop`, mai `git stash pop` nudo, come da regola del worktree
condiviso) e rilanciandoli SENZA la fixture: falliscono allo stesso modo, stesso
messaggio:

- `Betfair/stream/tests/test_live_market_types_2026_09_25.py::
  test_whitelist_proposta_non_e_vuota_e_non_tocca_il_default` — `CS.LIVE_MARKET_TYPES`
  non e' vuoto come il test si aspetta (fuori perimetro: whitelist di produzione,
  non stato di flumine).
- `Betfair/stream/tests/test_motore_ordini_2026_09_24.py::
  test_latenza_logica_comando_place_sotto_20_ms` — soglia di prestazione (`p95 < 20
  ms`) misurata a 28 ms; e' un test di performance sensibile al carico della
  macchina/della sessione (7000+ test in corso), non uno stato di flumine che si
  trascina.
- `Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py::
  test_nessun_chiamante_nuovo_non_registrato` — `esecutore_tennis.py` non e'
  ancora registrato nel contratto dei chiamanti del place-and-trim
  (`Betfair/stream/trading/INTERFACES.md`); e' un difetto di registrazione di
  produzione, non di stato globale nei test, e va fuori dal perimetro di questo
  fix (test, non codice).

Nessuno dei tre ha a che fare con `flumine.config`, ne' e' passato da rosso a
verde o viceversa per effetto della fixture nuova: sono note per il coordinatore,
non toccate qui.

## 7. Consegna

- `Betfair/conftest.py` — unico file di produzione/test toccato (fixture nuova,
  nessuna riga esistente modificata o rimossa).
- `AUDIT_2026-09-25/fix_r4.patch` — `git diff` del punto precedente.
- Nessun commit, nessun `git add`, nessun push, nessun DB toccato.
