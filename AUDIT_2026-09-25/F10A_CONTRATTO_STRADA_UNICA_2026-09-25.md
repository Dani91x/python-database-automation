# F10a - Test di contratto "strada unica" (25/09/2026)

Delegato Sonnet del coordinatore. Worktree su base `fcc99e7` (master). Nessun
file di produzione toccato: solo il test nuovo e il documento breve. Nessun
commit, nessun `git add -A`, nessuna scrittura sul DB vero, nessun processo
avviato.

Obiettivo (audit 24/09 par.4.6 punto 6, piano par.5 riga F10a): un test STATICO
che elenca per nome i moduli autorizzati a chiamare l'Exchange per un ordine e
diventa ROSSO se ne compare uno nuovo.

## 0. Sorprese in cima (da decidere con l'utente, NON toccate)

La scansione `ast` (vedi par.1) ha trovato **4 chiamanti a `market.place_order`
che l'audit del 24/09 non elenca e che NESSUN runner di produzione importa**:

| Modulo | Cosa dice di se' | Verifica fatta |
|---|---|---|
| `Betfair/stream/scalper_lab/grid_strategy.py` | docstring: "GridStrategy — LAB separato (NON tocca lo scalper)" | `grep -rln "scalper_lab\." Betfair --include=*.py \| grep -v /scalper_lab/` -> 0 risultati; non e' in `desktop/main.js` ne' in `scalper_service.py` |
| `Betfair/stream/scalper_lab/scalper_bot_base.py` | base di scalper_lab | stesso risultato |
| `Betfair/stream/scalper_lab/theta_strategy.py` | docstring: "ThetaStrategy — LAB separato (NON tocca lo scalper)" | stesso risultato |
| `Betfair/stream/tennis_scalper/tennis_lab.py` | `TennisLabStrategy`, "motore configurabile per lo SWEEP MASSIVO (centinaia di combo)" di backtest | `_BOT_REGISTRY` di `tennis_runner.py:102-107` ha SOLO `tennis_scalper`, `tennis_pro`, `tennis_flb`, `tennis_swing`: `tennis_lab` non c'e' |

Non li ho toccati (fuori perimetro di questa consegna: "nessun file di
produzione modificato"). Li ho messi nel contratto con motivo letterale
"trovato da F10a, da decidere", strada `NON_PRODUZIONE?`, cosi' il test resta
verde SENZA nasconderli: compaiono nella mappa chiamante->strada che il test
stampa. Decisione da chiedere all'utente: chiuderli (codice morto mai
collegato), spostarli fuori da `Betfair/`, o lasciarli e basta.

Non ho trovato altre sorprese: nessuna chiamata diretta a
`SportsAPING/v1.0/placeOrders` fuori dal client REST unico (`Betfair/client.py`)
e da `omega/omega_market.py`, nessun `replace_orders`/`cancel_orders` fuori dai
moduli gia' citati nell'audit.

## 1. Come ho cercato (ast, non regex sola)

Ho scandito ogni `.py` sotto `Betfair/` (esclusi `tests/`, `tools/`, i file
`test_*.py`) cercando, con il modulo `ast`:
- chiamate (`ast.Call`) il cui nome (attributo o funzione) e' `place_order`,
  `place_orders`, `cancel_orders` o `replace_orders`, qualunque sia l'oggetto
  (`market.`, `client.`, `trading.betting.`, o una funzione importata);
- costanti stringa (`ast.Constant`) che iniziano per
  `SportsAPING/v1.0/placeOrders`, `.../cancelOrders`, `.../replaceOrders`.

Perche' non basta un grep sulla stringa "placeOrders": `"replaceOrders"`
CONTIENE la sottostringa `"placeOrders"` (re + placeOrders). Un grep testuale
grezzo su `Betfair/stream/risk_engine_worker.py` restituiva un falso positivo
per questo motivo (un commento su `replaceOrders`, nessuna chiamata vera); con
`ast` sulle stringhe letterali e sui nodi `Call` il falso positivo sparisce.
Ho anche distinto le DEFINIZIONI (`ast.FunctionDef`, es. `def place_order(` in
`order_exec.py`, `def place_orders(` in `client.py`) dalle CHIAMATE (`ast.Call`):
solo le seconde contano.

## 2. Chiamanti trovati (modulo, funzione, riga, strada)

18 moduli di produzione/banco + 4 sorprese (sopra). Codici di strada dalla
tabella par.1.0 dell'audit del 24/09.

| Modulo | Funzione | Riga | Nome chiamata | Strada |
|---|---|---|---|---|
| `Betfair/client.py` | `place_orders` | 358 | `JSONRPC:placeOrders` | S3a (client REST unico) |
| `Betfair/omega/omega_market.py` | `place_order_live` | 750 | `place_orders` | S3a |
| `Betfair/omega/omega_market.py` | `_submin_cancel` | 858 | `JSONRPC:cancelOrders` | S3a |
| `Betfair/omega/omega_market.py` | `place_submin_live` | 1009 | `place_orders` | S3a |
| `Betfair/omega/omega_market.py` | `place_submin_live` | 1130 | `JSONRPC:replaceOrders` | S3a |
| `Betfair/omega/omega_market.py` | `cancel_order_live` | 1253 | `JSONRPC:cancelOrders` | S3a |
| `Betfair/order_exec.py` | `place_order` | 315 | `place_orders` | S4b |
| `Betfair/order_worker.py` | `_process_once` | 86 | `place_order` (chiama `order_exec.place_order`) | S4b |
| `Betfair/stream/odds_http.py` | `_handle_place_order` | 188 | `place_order` (chiama `order_exec.place_order`) | S4b |
| `Betfair/stream/live_order_worker.py` | `_place_or_raise` | 1195 | `place_order` | S1, S2 |
| `Betfair/stream/tennis_live/tennis_live_order_worker.py` | `_do_place` | 540 | `place_order` | S2t |
| `Betfair/stream/tennis_live/tennis_live_order_worker.py` | `_do_greenup` | 798 | `place_order` | S2t |
| `Betfair/stream/tennis_live/guardie_tennis.py` | `place_order` (metodo di `MercatoConClient`) | 125 | `place_order` | S3b (wrapper, inoltra al Market vero) |
| `Betfair/stream/tennis_scalper/tennis_scalper_bot.py` | `_place` | 2329 | `place_order` | S3b |
| `Betfair/stream/tennis_scalper/tennis_pro_bot.py` | `_place` | 413 | `place_order` | S3b |
| `Betfair/stream/tennis_scalper/tennis_flb_bot.py` | `_place` | 216 | `place_order` | S3b |
| `Betfair/stream/tennis_scalper/tennis_swing_bot.py` | `_place` | 228 | `place_order` | S3b |
| `Betfair/stream/scalper/scalper_bot.py` | `_esegui_place` | 2236 | `place_order` | S4a |
| `Betfair/stream/scalper/sniper_bot.py` | `_place` | 775 | `place_order` | S4a |
| `Betfair/stream/scalper/scalper_session.py` | `_sweep_cancel` | 252, 260 | `cancel_orders` | S4a (REST di emergenza, bypassa flumine) |
| `Betfair/stream/trading/submin.py` | `place` (in `FlumineSubminOps`) | 219, 222 | `place_order` | S1, S2, S2t, S3a, S4a (nucleo unico place-and-trim) |
| `Betfair/stream/backtest/banco_comune.py` | `place_order_live` | 588 | `place_order` | BANCO |
| `Betfair/stream/backtest/banco_comune.py` | `place_order_utente` | 946 | `place_order` | BANCO |
| `Betfair/stream/backtest/sim_strategy.py` | `_place` | 225 | `place_order` | BANCO |
| `Betfair/stream/scalper_lab/grid_strategy.py` | `_place` | 453 | `place_order` | NON_PRODUZIONE? |
| `Betfair/stream/scalper_lab/scalper_bot_base.py` | `_place` | 1838 | `place_order` | NON_PRODUZIONE? |
| `Betfair/stream/scalper_lab/theta_strategy.py` | `_place` | 371 | `place_order` | NON_PRODUZIONE? |
| `Betfair/stream/tennis_scalper/tennis_lab.py` | `_place` | 145 | `place_order` | NON_PRODUZIONE? |

Nota su `motore_ordini.py` (il motore del canale calcio, entrato in produzione
il 25/09 secondo `STRADA_UNICA_BANCO_E_PAPER.md`): NON compare in tabella
perche' non chiama `place_order`/`place_orders` direttamente. Verificato:
`grep -n "_dispatch\|live_order_worker" Betfair/stream/motore_ordini.py` mostra
`from . import live_order_worker as LOW` e `LOW._dispatch(lsb, self._flumine,
riga, mode, self._strategie)` (riga 944): richiama la funzione GIA'
registrata in `live_order_worker.py`, non duplica la chiamata. Stessa verifica
per `Betfair/stream/backtest/porta_banco.py`, `trasporto.py`, `trasporto_rapido.py`
(0 occorrenze di `place_order` diretto).

Verifica indipendente: `mike/service.py`, `safe_strategy/execution.py` e
`omega/omega_service.py` chiamano `market.place_order_live(...)` (un NOME
diverso, con underscore extra), che a sua volta chiama
`omega_market.place_order_live` — gia' in tabella. Per questo Mike, Omega e
Safe NON compaiono come chiamanti diretti: passano tutti dal REST unico
(`omega_market.py`) o dal canale (`live_order_worker.py`/`motore_ordini.py`).
E' esattamente il modello dell'audit (par.1.4).

## 3. Test scritti e numeri

File: `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`, **27 test**:
- `test_la_scansione_vede_qualcosa` (sonda: la scansione non e' vuota);
- `test_nessun_chiamante_nuovo_non_registrato` (direzione a: chiamante nuovo);
- `test_elenco_non_stantio` (direzione b: autorizzato che non chiama piu');
- `test_ogni_autorizzazione_ha_un_motivo_non_vuoto`;
- `test_mappa_chiamante_strada_coerente_con_tabella_1_0_audit` (punto 3 della
  consegna: stampa la mappa, verifica che le strade coperte siano esattamente
  le 7 di par.1.0 dell'audit, ne' di piu' ne' di meno);
- `test_ogni_modulo_autorizzato_esiste_davvero`, parametrizzato su 22 moduli
  (22 voci nel dizionario `_CHIAMANTI_AUTORIZZATI`, 18 "vere" + 4 sorprese).

```
$ export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
$ timeout 600 python -m pytest Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py -q -p no:cacheprovider
...........................
27 passed in 4.31s (rilanciato dopo il ripristino: 27 passed in 9.60s)
```

Nessuna regressione sul contratto gia' esistente:
```
$ timeout 600 python -m pytest Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py -q -p no:cacheprovider
......
6 passed in 1.82s
```

## 4. Falsificazione (obbligatoria)

**F1 - chiamante nuovo non registrato.** Creato un file finto con le stesse
chiavi/tipi di una vera funzione di piazzamento (una `def` che chiama
`market.place_order(order)`), in una cartella nuova `Betfair/stream/_finto_f10a/`:

```python
# Betfair/stream/_finto_f10a/canale_ombra.py
def piazza_ombra(market, order):
    return market.place_order(order)
```

```
$ timeout 600 python -m pytest Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py -q -p no:cacheprovider -k test_nessun_chiamante_nuovo_non_registrato
F
AssertionError: chiamanti NUOVI verso l'Exchange, NON registrati nel contratto
strada unica: ['Betfair/stream/_finto_f10a/canale_ombra.py']. [...]
Dettaglio (file: [(riga, nome)]): {'Betfair/stream/_finto_f10a/canale_ombra.py': [(6, 'place_order')]}
1 failed, 26 deselected in 3.91s
```
ROSSO come atteso. Rimosso `Betfair/stream/_finto_f10a/` (`rm -rf`), verificato
`git status --porcelain` pulito (solo i due file di questa consegna restano).

**F2 - autorizzato tolto dall'elenco.** Rimossa temporaneamente (con `Edit`,
non a mano nel file) la voce `"Betfair/omega/omega_market.py"` da
`_CHIAMANTI_AUTORIZZATI`, lasciando un commento al suo posto:

```
$ timeout 600 python -m pytest Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py -q -p no:cacheprovider -k "test_nessun_chiamante_nuovo_non_registrato or test_mappa_chiamante"
F.
AssertionError: chiamanti NUOVI verso l'Exchange, NON registrati nel contratto
strada unica: ['Betfair/omega/omega_market.py']. [...]
Dettaglio: {'Betfair/omega/omega_market.py': [(750, 'place_orders'), (1009, 'place_orders'),
(858, 'JSONRPC:SportsAPING/v1.0/cancelOrders'), (1253, 'JSONRPC:SportsAPING/v1.0/cancelOrders'),
(1130, 'JSONRPC:SportsAPING/v1.0/replaceOrders')]}
1 failed, 1 passed, 24 deselected in 8.41s
```
ROSSO come atteso (cade nella stessa direzione "chiamante non registrato": la
riga tolta fa si' che il modulo, che chiama davvero, non sia piu' nell'elenco).
Il test `test_mappa_chiamante_strada...` resta verde in questo caso preciso
perche' la strada S3a e' ancora coperta da `client.py` e `submin.py`: NON e' un
difetto del contratto, e' la prova che quel test verifica la COPERTURA delle
strade, non l'identita' di ogni singolo modulo (di cui si occupa
`test_nessun_chiamante_nuovo_non_registrato`, gia' rosso). Ripristinato con
`Edit` la voce esatta.

**Ripristino verificato byte per byte:**
```
$ sha1sum Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py
316b2555abceefe6a73a28c86c247d92894ee88a   # PRIMA della falsificazione F2
316b2555abceefe6a73a28c86c247d92894ee88a   # DOPO il ripristino
```
Identico. Rilancio finale della suite intera: `27 passed in 9.60s`.

## 5. Non verificato

- Non ho provato una falsificazione per `test_elenco_non_stantio` (direzione
  "autorizzato che non chiama piu'" con un file rimosso davvero, non solo la
  voce nel dizionario): la F2 sopra copre lo stesso sintomo per un'altra via
  (la voce sparisce dal dizionario mentre la chiamata vera resta nel sorgente,
  che e' il caso piu' realistico — un refuso nel contratto, non un file
  cancellato). Se serve, si ripete su richiesta rimuovendo per davvero una
  chiamata da un modulo autorizzato (per esempio commentando la riga 1195 di
  `live_order_worker.py` in una copia locale, mai su master).
- Non ho verificato se `ast` perde chiamate dietro `getattr` dinamico o
  `eval`/`exec`: non ne ho trovate nel repo scandito, ma non ho cercato questo
  pattern specifico.
- Non ho chiesto conferma all'utente sulle 4 sorprese (par.0): la decisione
  (chiudere/spostare/lasciare) resta aperta.
- Non ho rieseguito l'intera suite `Betfair/` (fuori perimetro: solo i file
  toccati e il contratto submin, come da consegna "niente suite intere").

## 6. File toccati e comandi

File nuovi (nessun file di produzione modificato):
- `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`
- `Betfair/stream/CONTRATTO_STRADA_UNICA_2026-09-25.md`
- `AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md` (questo file)

Comandi eseguiti, con esito:
```
git fetch origin                                                  # OK, worktree gia' su fcc99e7 (master)
git status / git log --oneline -5                                 # working tree pulito, base fcc99e7
python -m pytest test_contratto_strada_unica...  -q                # 27 passed
python -m pytest test_contratto_strada_unica... -k F1 (finto)      # 1 failed (ROSSO atteso)
rm -rf Betfair/stream/_finto_f10a                                  # ripristino F1
python -m pytest test_contratto_strada_unica... -k F2 (voce tolta) # 1 failed, 1 passed (ROSSO atteso)
Edit (ripristino voce omega_market.py)                             # sha1 identico a prima
python -m pytest test_contratto_strada_unica...  -q                # 27 passed (finale)
python -m pytest test_submin_contratto_chiamanti_2026_09_17.py -q  # 6 passed (nessuna regressione)
git status --porcelain                                             # solo i 3 file elencati sopra
```
