# Spostamento del laboratorio fuori da Betfair/ (25/09/2026, sera)

Delegato Sonnet del coordinatore (sessione B). Worktree su base
`43e1468` (master, `git fetch` eseguito). Nessun commit, nessun `git add -A`,
nessuna scrittura sul DB vero, nessun processo avviato.

Decisione testuale dell'utente eseguita: "Spostali in una cartella, sono test
che riprenderemo piu' avanti, documenta cosa sanno fare e la loro struttura in
un file .md all'interno della stessa cartella, li riprenderemo piu' avanti
quando faremo pulizia di tutta la codebase."

Punto di partenza: i 4 moduli trovati dal test di contratto F10a
(`AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md`) — sanno
piazzare ordini flumine veri ma nessun runner li importa:
`Betfair/stream/scalper_lab/{grid_strategy,scalper_bot_base,theta_strategy}.py`,
`Betfair/stream/tennis_scalper/tennis_lab.py`.

## 1. Mappa delle dipendenze (prima di spostare niente)

Grep su tutto il repo (`*.py`, `*.md`, `*.bat`, `*.yml`/`*.yaml`, incluso
`desktop/`) per ciascuno dei 4 moduli e per l'intera cartella `scalper_lab/`:
**nessun file sotto `Betfair/` (fuori dalla cartella stessa) importa mai
`scalper_lab.*`**; solo doc/test lo NOMINANO come stringa (audit, contratto
F10a, bibbie). Non e' in `desktop/main.js` ne' in `scalper_service.py`.

### Isola `scalper_lab/` — TUTTA la cartella e' un unico grafo di dipendenze interne
```
bt_lab.py          -> scalper_bot_base.py (ScalperStrategy)
bt_theta.py         -> theta_strategy.py (ThetaStrategy) [+ produzione: scalper.scalper_bot]
exp_families.py     -> bt_lab.py (run_config)
rdloop.py           -> bt_lab.py (COMPLETE, run_config)
validate_synth.py   -> bt_lab.py, synth_raw.py (GENERATORS)
grid_strategy.py    -> [+ produzione: scalper.scalper_bot]
theta_strategy.py   -> [+ produzione: scalper.scalper_bot]
scalper_bot_base.py -> [+ produzione (lazy, dentro funzioni): live_order_build,
                        trading.submin (FlumineSubminOps/SubminStep/advance_submin)]
synth_raw.py         (nessuna dipendenza interna)
```
Conclusione: i 10 file di `scalper_lab/` (incluso `__init__.py`) formano
un'unica isola autosufficiente, mai importata da fuori. **Spostata TUTTA**,
non solo i 3 moduli trovati da F10a.

### Isola `tennis_lab` dentro `tennis_scalper/` — 5 moduli + 1 test
Grep mirato (`tennis_lab\b`, `lab_grid\b`, `lab_grid_score`, `tennis_lab_score`,
`validate.py` di `tennis_scalper/`) ha trovato, OLTRE a `tennis_lab.py`:
```
lab_grid.py               -> tennis_lab.py (TennisLabStrategy)
tennis_lab_score.py       -> tennis_lab.py (TennisLabStrategy)
                           -> [+ produzione: tennis_score.TennisScore,
                              tennis_winprob.p_match/estimate_holds]
lab_grid_score.py         -> tennis_lab_score.py (ScoreConditionedLab, SIDE_*)
                           -> [+ produzione: tennis_score.TennisScore, ...]
validate.py                -> lab_grid.py, lab_grid_score.py, tennis_lab.py
                           -> [+ produzione: tennis_swing_bot.TennisSwingStrategy]
tests/test_harness_golden.py -> tennis_lab.py (TennisLabStrategy, unico test
                                 della cartella tests/ che li tocca — verificato
                                 con grep su tutti i 17 file di tests/)
```
Nessuno di questi 5 file (ne' il test) e' importato da nessun modulo di
produzione fuori da questa isola: `validate.py` non e' importato da nessuno
(e' uno script standalone, `python -m ...`), stesso per `lab_grid*.py`.
`tennis_lab.py` non e' in `_BOT_REGISTRY` di `tennis_runner.py` (gia' accertato
da F10a). **Spostata l'isola intera** (5 moduli + il test), lasciando in
`Betfair/stream/tennis_scalper/` tutto il resto (i 4 bot di produzione veri —
`tennis_scalper_bot.py`, `tennis_pro_bot.py`, `tennis_flb_bot.py`,
`tennis_swing_bot.py` — e i moduli condivisi `tennis_score.py`,
`tennis_winprob.py`, `tennis_scalper_bot.py`, `tennis_serve_data.py`, ecc.,
che restano produzione/condivisi e che il lab spostato continua a importare
in ASSOLUTO da `Betfair.stream.tennis_scalper.*`).

Nessun `.bat`/`.yml`/CI, nessun `conftest.py`, nessun file sotto `desktop/`
referenzia questi moduli per nome modulo (solo doc in prosa). Confermato con
grep dedicati (vedi comandi in fondo).

## 2. File spostati (`git mv`, storia conservata)

| Da | A |
|---|---|
| `Betfair/stream/scalper_lab/__init__.py` | `laboratorio/scalper_lab/__init__.py` |
| `Betfair/stream/scalper_lab/bt_lab.py` | `laboratorio/scalper_lab/bt_lab.py` |
| `Betfair/stream/scalper_lab/bt_theta.py` | `laboratorio/scalper_lab/bt_theta.py` |
| `Betfair/stream/scalper_lab/exp_families.py` | `laboratorio/scalper_lab/exp_families.py` |
| `Betfair/stream/scalper_lab/grid_strategy.py` | `laboratorio/scalper_lab/grid_strategy.py` |
| `Betfair/stream/scalper_lab/rdloop.py` | `laboratorio/scalper_lab/rdloop.py` |
| `Betfair/stream/scalper_lab/scalper_bot_base.py` | `laboratorio/scalper_lab/scalper_bot_base.py` |
| `Betfair/stream/scalper_lab/synth_raw.py` | `laboratorio/scalper_lab/synth_raw.py` |
| `Betfair/stream/scalper_lab/theta_strategy.py` | `laboratorio/scalper_lab/theta_strategy.py` |
| `Betfair/stream/scalper_lab/validate_synth.py` | `laboratorio/scalper_lab/validate_synth.py` |
| `Betfair/stream/tennis_scalper/tennis_lab.py` | `laboratorio/tennis_lab/tennis_lab.py` |
| `Betfair/stream/tennis_scalper/tennis_lab_score.py` | `laboratorio/tennis_lab/tennis_lab_score.py` |
| `Betfair/stream/tennis_scalper/lab_grid.py` | `laboratorio/tennis_lab/lab_grid.py` |
| `Betfair/stream/tennis_scalper/lab_grid_score.py` | `laboratorio/tennis_lab/lab_grid_score.py` |
| `Betfair/stream/tennis_scalper/validate.py` | `laboratorio/tennis_lab/validate.py` |
| `Betfair/stream/tennis_scalper/tests/test_harness_golden.py` | `laboratorio/tennis_lab/tests/test_harness_golden.py` |

Tutti i 16 spostamenti risultano `R` (rename) in `git status --porcelain`,
storia preservata (`git log --follow` sul nuovo percorso ritrova i commit
precedenti). File nuovi creati (non esistevano prima): `laboratorio/__init__.py`,
`laboratorio/tennis_lab/__init__.py`, `laboratorio/tennis_lab/tests/__init__.py`,
`laboratorio/README.md`, questo referto.

Nulla e' rimasto sotto `Betfair/stream/scalper_lab/` (cartella sparita) ne'
sotto `Betfair/stream/tennis_scalper/{tennis_lab*.py,lab_grid*.py,validate.py}`
ne' `Betfair/stream/tennis_scalper/tests/test_harness_golden.py`.

## 3. Import aggiustati

Direzione **laboratorio -> produzione (Betfair...)**: sempre assoluta, MAI
toccata dove gia' lo era; **corretta dove era relativa** (si sarebbe rotta
dopo lo spostamento, perche' il modulo di produzione bersaglio non vive piu'
nello stesso package):

- `laboratorio/scalper_lab/scalper_bot_base.py` (2 punti, import lazy dentro
  funzioni): `from ..live_order_build import round_to_tick` ->
  `from Betfair.stream.live_order_build import round_to_tick`;
  `from ..trading.submin import FlumineSubminOps, SubminState, SubminStep` /
  `from ..trading.submin import SubminStep, advance_submin` ->
  `from Betfair.stream.trading.submin import ...` (x2, righe diverse). Questi
  erano import relativi RISALENTI a `Betfair.stream` (2 punti da dentro
  `scalper_lab/`): dopo lo spostamento in `laboratorio/scalper_lab/`, 2 punti
  risalgono a `laboratorio/`, che non ha ne' `live_order_build` ne'
  `trading/submin` — si sarebbero rotti in silenzio al primo uso (import
  lazy, dentro un metodo: nessun errore all'`import` del modulo, solo alla
  chiamata). Sono le uniche righe con questo rischio trovate nella scansione.
- `laboratorio/tennis_lab/tennis_lab.py`: `.tennis_scalper_bot` ->
  `Betfair.stream.tennis_scalper.tennis_scalper_bot`.
- `laboratorio/tennis_lab/tennis_lab_score.py`: `.tennis_score` ->
  `Betfair.stream.tennis_scalper.tennis_score`; `.tennis_winprob` ->
  `Betfair.stream.tennis_scalper.tennis_winprob`.
- `laboratorio/tennis_lab/lab_grid_score.py`: `.tennis_score` ->
  `Betfair.stream.tennis_scalper.tennis_score`; import lazy
  `from ..auth import build_client` -> `from Betfair.stream.auth import
  build_client` (stesso rischio "si rompe solo alla chiamata" di cui sopra).
- `laboratorio/tennis_lab/validate.py`: `.tennis_swing_bot` ->
  `Betfair.stream.tennis_scalper.tennis_swing_bot`; import lazy
  `from ..tools.validate_recordings import check_raw_paths_for_backtest` ->
  `Betfair.stream.tools.validate_recordings...` (stesso rischio).
- `laboratorio/tennis_lab/lab_grid.py`: stesso import lazy
  `..tools.validate_recordings` -> assoluto.

Direzione **interna al laboratorio** (moduli che restano insieme): lasciata
RELATIVA dove gia' lo era (`from .scalper_bot_base import ...`,
`from .tennis_lab import ...`, `from . import lab_grid as PG`, ecc.) — resta
valida perche' la struttura interna della cartella non cambia. Confermato
identico anche per `tests/test_harness_golden.py`: `from ..tennis_lab import
TennisLabStrategy` risolveva prima a `tennis_scalper.tennis_lab` (package
`tennis_scalper`, submodulo `tennis_lab`) e ora risolve a
`laboratorio.tennis_lab.tennis_lab` (package `tennis_lab`, submodulo
`tennis_lab` — stesso nome per coincidenza voluta dalla struttura chiesta
dall'utente: sottocartella `tennis_lab/` con dentro `tennis_lab.py`), quindi
NESSUNA modifica necessaria li'.

Direzione **assoluta gia' corretta, invariata**: import gia'
`Betfair.stream.tools.validate_recordings` (non lazy, in `bt_lab.py`/
`bt_theta.py`) e `Betfair.stream.scalper.scalper_bot` (in `bt_theta.py`,
`grid_strategy.py`, `theta_strategy.py`) — nessun cambiamento, restano
assoluti verso la produzione.

Docstring "Uso: python -m Betfair.stream...." aggiornate a
"python -m laboratorio...." in tutti i moduli che le avevano (8 righe, in
`bt_lab.py`, `bt_theta.py`, `exp_families.py`, `rdloop.py`, `synth_raw.py`,
`validate_synth.py`, `lab_grid.py`, `lab_grid_score.py`, `validate.py`).

Verifica di completezza: grep finale su tutta `laboratorio/` per
`Betfair.stream.scalper_lab`, `Betfair.stream.tennis_scalper.{tennis_lab,
lab_grid,validate}` (i vecchi percorsi assoluti) e per import relativi
(`from \.\.`/`from \.[a-zA-Z_]`) rimasti: **zero riferimenti stantii**, tutti
gli import relativi residui puntano dentro il pacchetto spostato (corretto).

## 4. Test spostato e contratto F10a aggiornato

`tests/test_harness_golden.py` spostato con il resto dell'isola tennis (8
test, nessuna modifica al contenuto: l'import relativo restava valido).

`Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`:
- tolte le 4 voci `"...NON_PRODUZIONE?"` (`scalper_lab/{grid_strategy,
  scalper_bot_base,theta_strategy}.py`, `tennis_scalper/tennis_lab.py`) da
  `_CHIAMANTI_AUTORIZZATI` (la scansione copre solo `Betfair/`: se restavano,
  `test_elenco_non_stantio` e `test_ogni_modulo_autorizzato_esiste_davvero`
  sarebbero diventati rossi, perche' i file non esistono piu' li');
- docstring di modulo aggiornata (la sezione "TROVATO DA F10A... da decidere"
  ora dice "risolto lo stesso giorno", con puntatore a questo referto);
- **test nuovo** `test_laboratorio_non_importato_da_betfair_ne_da_desktop`:
  scandisce con `ast` ogni `.py` sotto `Betfair/` (test/tools INCLUSI, zero
  eccezioni) cercando `import laboratorio`/`import laboratorio.x`/
  `from laboratorio...`, e cerca la stringa letterale `"laboratorio"` in ogni
  file sotto `desktop/` (JS/Electron: niente `ast` Python, un percorso
  passato a un processo figlio sarebbe una stringa).

`Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py`: tolta
la riga `"Betfair/stream/scalper_lab/scalper_bot_base.py"` da
`_CHIAMANTI_ATTESI` (non esiste piu' sotto `Betfair/`, quindi la scansione di
quel test — limitata a `Betfair/` — non la trovera' piu'; lasciarla non
avrebbe rotto il test, che controlla solo i chiamanti NUOVI non registrati,
ma sarebbe rimasta una riga stantia/fuorviante), sostituita da un commento
che spiega lo spostamento e punta a questo referto.

`Betfair/stream/CONTRATTO_STRADA_UNICA_2026-09-25.md` aggiornato: la sezione
"Stato al 25/09/2026" ora descrive lo spostamento avvenuto (non piu' "da
decidere"), con puntatori a `laboratorio/README.md` e a questo referto.

## 5. Verifica

```
$ export SUPABASE_URL=http://127.0.0.1:9 SUPABASE_SERVICE_ROLE_KEY=x SUPABASE_KEY=x
$ python -m pytest Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py \
                    Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py \
                    -q -p no:cacheprovider
..............................                                           [100%]
30 passed in 18.55-22.54s
```
(24 test nel contratto F10a: 27 originali - 4 parametrizzazioni sparite con le
righe tolte da `_CHIAMANTI_AUTORIZZATI` + 1 test nuovo = 24; + 6 del contratto
submin = 30.)

```
$ python -c "import laboratorio.scalper_lab.grid_strategy, \
             laboratorio.scalper_lab.theta_strategy, \
             laboratorio.tennis_lab.tennis_lab"
(nessun errore)
```
Esteso anche agli altri 8 moduli spostati (`scalper_bot_base`, `bt_lab`,
`bt_theta`, `exp_families`, `rdloop`, `synth_raw`, `validate_synth`,
`tennis_lab_score`, `lab_grid`, `lab_grid_score`, `validate`): tutti
importano senza errori con le stesse env fasulle.

```
$ python -m pytest laboratorio/tennis_lab/tests/test_harness_golden.py -q -p no:cacheprovider
........                                                                 [100%]
8 passed in 7.41s

$ python -m pytest Betfair/stream/tennis_scalper/tests/ -q -p no:cacheprovider
......(154).............................................................
154 passed in 6.54s   # nessuna regressione sulla suite tennis_scalper rimasta
```

Grep finale:
```
$ grep -rn "import laboratorio\|from laboratorio" Betfair/ --include=*.py
(solo la riga di docstring nel test che DESCRIVE il controllo — zero import veri)
$ grep -rln "laboratorio" desktop/
(vuoto)
```

## 6. Falsificazione (obbligatoria)

**F1 — import finto da sotto `Betfair/` verso `laboratorio/`.** Creato
`Betfair/stream/_finto_laboratorio/canale_ombra.py`:
```python
"""Finto per falsificazione: import verso laboratorio/ da sotto Betfair/."""
from laboratorio.scalper_lab.grid_strategy import GridStrategy  # noqa: F401
```
```
$ python -m pytest .../test_contratto_strada_unica_2026_09_25.py -q -p no:cacheprovider \
    -k test_laboratorio_non_importato_da_betfair_ne_da_desktop
F
AssertionError: modulo sotto Betfair/ che importa da laboratorio/ [...]:
['Betfair/stream/_finto_laboratorio/canale_ombra.py:2']
1 failed, 23 deselected
```
ROSSO come atteso. Rimosso `rm -rf Betfair/stream/_finto_laboratorio`,
verificato `git status --porcelain` pulito (nessun residuo).

**F2 — riferimento finto sotto `desktop/`.** Aggiunta temporaneamente una
riga a `desktop/main.js` (`// spawn python -m laboratorio.tennis_lab.validate
--data x`):
```
$ python -m pytest ... -k test_laboratorio_non_importato_da_betfair_ne_da_desktop
F
AssertionError: file sotto desktop/ che nomina 'laboratorio' [...]: ['desktop/main.js']
1 failed, 23 deselected
```
ROSSO come atteso (copre il ramo desktop, non solo il ramo `ast` Python).
Ripristinato con `git checkout -- desktop/main.js`; `git status --porcelain
-- desktop/` pulito.

**Rilancio finale dopo i due ripristini**: `30 passed` (contratto F10a +
contratto submin), come al punto 5.

## 7. Non verificato

- Non ho lanciato l'intera suite `Betfair/` (fuori perimetro dichiarato:
  "niente suite intere" non e' scritto qui esplicitamente ma il compito
  elenca solo i due file di contratto + l'import diretto + il test spostato;
  ho comunque rilanciato l'intera `Betfair/stream/tennis_scalper/tests/`
  (154 test) come controllo aggiuntivo di regressione, verde). Se l'utente
  vuole la suite completa `Betfair/` la lancio su richiesta (e' lunga).
- Non ho verificato comportamento a runtime di nessuno dei moduli spostati
  oltre all'import (nessun replay, nessun avvio processo — fuori perimetro:
  sono moduli di laboratorio mai certificati, la consegna e' spostarli e
  documentarli, non validarli).
- Non ho toccato `AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md`
  (referto storico della consegna precedente): resta come fu scritto il
  25/09 mattina, con un puntatore aggiunto da questo referto e dal contratto
  aggiornato. Non l'ho riscritto per non falsificare la cronaca di quella
  consegna.
- Non ho verificato se altri repo/script fuori da questo checkout (per
  esempio automazioni esterne, cron, scorciatoie della shell dell'utente)
  invocassero `python -m Betfair.stream.scalper_lab...`/`Betfair.stream.
  tennis_scalper.{tennis_lab,lab_grid,validate}...`: fuori dalla mia
  visibilita' (worktree locale). Se esistono, vanno aggiornati a
  `python -m laboratorio...`.

## 8. File toccati/spostati — elenco esatto e comandi con esito

**Spostati** (`git mv`, 16 file, storia conservata — tabella completa al
punto 2).

**Nuovi**:
- `laboratorio/__init__.py`
- `laboratorio/tennis_lab/__init__.py`
- `laboratorio/tennis_lab/tests/__init__.py`
- `laboratorio/README.md`
- `AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md` (questo file)

**Modificati** (contenuto, non spostati):
- `laboratorio/scalper_lab/bt_lab.py` (import + docstring uso)
- `laboratorio/scalper_lab/bt_theta.py` (import + docstring uso)
- `laboratorio/scalper_lab/exp_families.py` (import + docstring uso)
- `laboratorio/scalper_lab/rdloop.py` (import + docstring uso)
- `laboratorio/scalper_lab/synth_raw.py` (docstring uso)
- `laboratorio/scalper_lab/validate_synth.py` (import + docstring uso)
- `laboratorio/scalper_lab/scalper_bot_base.py` (3 import lazy assolutizzati)
- `laboratorio/tennis_lab/tennis_lab.py` (1 import assolutizzato)
- `laboratorio/tennis_lab/tennis_lab_score.py` (2 import assolutizzati)
- `laboratorio/tennis_lab/lab_grid.py` (1 import lazy assolutizzato + docstring)
- `laboratorio/tennis_lab/lab_grid_score.py` (2 import assolutizzati, 1 lazy + docstring)
- `laboratorio/tennis_lab/validate.py` (2 import assolutizzati, 1 lazy + docstring)
- `Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py` (4 voci
  tolte, docstring aggiornata, 1 test nuovo)
- `Betfair/stream/tests/test_submin_contratto_chiamanti_2026_09_17.py` (1
  voce tolta, commento aggiunto)
- `Betfair/stream/CONTRATTO_STRADA_UNICA_2026-09-25.md` (sezione stato
  aggiornata)

**Comandi eseguiti, con esito** (in ordine):
```
git fetch origin                                                     # OK, worktree su 43e1468 (master)
git status / git log -1 --oneline                                    # pulito, base 43e1468
grep dipendenze (vedi par.1)                                          # mappa completa, 0 sorprese fuori dall'isola
mkdir -p laboratorio/tennis_lab/tests
git mv Betfair/stream/scalper_lab laboratorio/scalper_lab             # OK (10 file, R)
git mv (6x) tennis_scalper/{tennis_lab,tennis_lab_score,lab_grid,
        lab_grid_score,validate}.py + tests/test_harness_golden.py    # OK (6 file, R)
Edit import/docstring nei 16 file spostati (vedi par.3)                # applicati
Write laboratorio/{__init__.py, tennis_lab/__init__.py,
      tennis_lab/tests/__init__.py, README.md}                        # creati
Edit test_contratto_strada_unica (4 voci tolte + test nuovo)           # applicato
Edit test_submin_contratto_chiamanti (1 voce tolta)                    # applicato
Edit CONTRATTO_STRADA_UNICA_2026-09-25.md                              # applicato
pytest test_contratto_strada_unica + test_submin_contratto_chiamanti   # 30 passed
python -c "import laboratorio...." (11 moduli)                        # nessun errore
pytest laboratorio/tennis_lab/tests/test_harness_golden.py             # 8 passed
pytest Betfair/stream/tennis_scalper/tests/                            # 154 passed
grep finale "import laboratorio" sotto Betfair/ e "laboratorio" sotto desktop/  # puliti
F1: file finto Betfair/stream/_finto_laboratorio/canale_ombra.py       # 1 failed (ROSSO atteso)
rm -rf Betfair/stream/_finto_laboratorio                               # ripristino, git status pulito
F2: riga finta in desktop/main.js                                      # 1 failed (ROSSO atteso)
git checkout -- desktop/main.js                                        # ripristino, git status -- desktop/ pulito
pytest finale (contratto F10a + contratto submin)                      # 30 passed
```
