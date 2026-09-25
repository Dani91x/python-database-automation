# laboratorio/ — codice sperimentale, MAI collegato a un runner di produzione

Spostato fuori da `Betfair/` il 25/09/2026 (decisione dell'utente), dopo che il
test di contratto F10a (`Betfair/stream/tests/test_contratto_strada_unica_2026_09_25.py`,
riferimento `AUDIT_2026-09-25/F10A_CONTRATTO_STRADA_UNICA_2026-09-25.md`) aveva
trovato 4 moduli capaci di piazzare ordini flumine veri (`market.place_order`)
ma non richiamati da nessun runner registrato:

- `laboratorio/scalper_lab/grid_strategy.py` (`GridStrategy`)
- `laboratorio/scalper_lab/scalper_bot_base.py` (`ScalperStrategy`, copia base)
- `laboratorio/scalper_lab/theta_strategy.py` (`ThetaStrategy`)
- `laboratorio/tennis_lab/tennis_lab.py` (`TennisLabStrategy`)

Con loro sono stati spostati (perche' ne dipendono, per non lasciare sotto
`Betfair/` un modulo che importa da qui — vedi `AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md`
per la mappa completa delle dipendenze) tutti gli altri file delle due
cartelle di laboratorio originali (`scalper_lab/` intera, e da
`tennis_scalper/`: `tennis_lab_score.py`, `lab_grid.py`, `lab_grid_score.py`,
`validate.py`, `tests/test_harness_golden.py`).

## Regola prima di riusare QUALSIASI cosa qui dentro

**Nessun runner la importa.** Prima di ricollegare un modulo di questa
cartella a un servizio vero: (1) va **registrato** nel registro del banco
comune (servizio di produzione + controlli di condotta — un bot in produzione
non registrato viene rifiutato dal test di contratto, vedi
`Betfair/stream/backtest/registro_bot.py`); (2) va **certificato** sul replay
tramite il punto d'ingresso unico `python -m Betfair.stream.backtest.certifica`
(mai un replay "a parte", mai queste classi di laboratorio spacciate per
produzione). Percorso completo: `PROCESSO_STANDARD_BOT.md` (radice del repo).
`test_laboratorio_non_importato_da_betfair_ne_da_desktop` (nel contratto F10a)
sorveglia che nessun modulo sotto `Betfair/` o `desktop/` importi da qui: se
un giorno si vuole ricollegare uno di questi moduli, quel test va prima
aggiornato consapevolmente (decisione dell'utente), non aggirato.

---

## `laboratorio/scalper_lab/` — sandbox scalper calcio (loop RD-Agent-style)

Dichiarata "sandbox sperimentale" dalla propria docstring (`__init__.py`):
copia isolata per mutare liberamente senza toccare `Betfair/stream/scalper/`
(lo scalper vero). Import di produzione ammessi (direzione consentita:
laboratorio -> produzione): `Betfair.stream.scalper.scalper_bot`
(`compute_green`/`micro_price`/`ticks_between`, matematica testata riusata),
`Betfair.stream.live_order_build`, `Betfair.stream.trading.submin` (nucleo
place-and-trim, chiamato da `scalper_bot_base.py`).

### `scalper_bot_base.py` — `ScalperStrategy` (105 KB, il piu' grande)
**Cosa sa fare**: micro-scalping mean-reversion pre-match/in-play a basso
rischio. Macchina a stati per selezione: `IDLE -> QUOTING` (entry maker
resting) `-> LOCKING` (close maker a +scalp_ticks) `-> DONE` (profitto
bloccato o flatten a mercato), poi nuovo ciclo fino a `max_cycles`. Nessun
look-ahead (solo book corrente + deque del passato). Gestisce anche il
place-and-trim sotto il minimo di giurisdizione via `FlumineSubminOps`/
`advance_submin` (nucleo unico `Betfair/stream/trading/submin.py`).
**Dichiarata "COPIA" stantia** dalla propria `__init__.py` ("la logica vive
nella COPIA... adattata solo nel lab"): non e' garantita identica allo
scalper vero oggi.
**Come si lanciava**: nessun comando diretto proprio — e' la base importata da
`bt_lab.py` (vedi sotto); non esiste un runner che la instanzi da sola.
**Ultima modifica**: 2026-07-08 (`0faf529`, "min_size default 300 validato +
sandbox scalper_lab"). **Mai certificato sul banco.**

### `grid_strategy.py` — `GridStrategy`
**Cosa sa fare**: ladder/griglia MAKER attorno a un centro (statico o EMA).
Ogni livello e' un seed resting (BACK sopra il centro, LAY sotto); al fill
piazza il take-profit uno step verso il centro e ri-arma. Cap di inventario
netto come controllo rischio, force-flat pre-KO e su rottura di banda. Ha
un'opzione `under_only` pensata per operare selettivamente su Over/Under
(competenza theta). Parametri principali: `step_ticks`, `levels`, `stake`,
`center_mode` (ema|static), `inv_cap_units`, `side_bias`, `price_min/max`,
`allow_inplay`, `regime_break_ticks`, `flatten_before_s`.
**Come si lanciava**: nessun harness proprio nel lab (nessun `bt_*` la
richiama); si importava e instanziava a mano.
**Ultima modifica**: 2026-07-08 (`0faf529`). La propria docstring si
autodichiara "LAB separato (NON tocca lo scalper)". **Mai certificato sul
banco.**

### `theta_strategy.py` — `ThetaStrategy`
**Cosa sa fare**: cattura DIREZIONALE del time-decay su Under in-play
(mentre 0-0 la quota Under scende): BACK Under maker, tieni mentre scende,
GREEN al target, TAGLIA se sale di `stop_ticks` (proxy di un gol, mai letto
dal punteggio — niente look-ahead). Supporta pyramiding (`max_units`,
`add_step_ticks`). Mercati: `lines` (default `OVER_UNDER_25`,
`OVER_UNDER_35`). Finestra default 5'-40' (`inplay_from_s`/`to_s`).
**Come si lanciava**: `python -m laboratorio.scalper_lab.bt_theta [k=v ...]`
(harness dedicato `bt_theta.py`, sotto).
**Ultima modifica**: 2026-07-10 (`5fe1e8e`, "missione 2-tick scalper
calcio+tennis, lab theta, tooling quote/replay"). Docstring: "LAB separato
(NON tocca lo scalper)". **Mai certificato sul banco.**

### File di supporto (harness/tooling del lab, spostati perche' dipendono dai 3 sopra)
- `bt_lab.py` — harness di backtest per `ScalperStrategy` via `FlumineSimulation`
  (delay 0s pre-match / 8s in-play, commissione 5%, output JSON ->
  knowledge_store). Uso: `python -m laboratorio.scalper_lab.bt_lab --mode
  prematch --stake 25`.
- `bt_theta.py` — harness equivalente per `ThetaStrategy`. Uso:
  `python -m laboratorio.scalper_lab.bt_theta [k=v ...]`.
- `exp_families.py` — esperimento che confronta famiglie di strategia
  (round 0 del loop RD-Agent), chiama `bt_lab.run_config`. Uso:
  `python -m laboratorio.scalper_lab.exp_families`.
- `rdloop.py` — loop evolutivo stile RD-Agent (ipotesi -> config -> backtest
  -> feedback -> evoluzione) sopra `bt_lab`. Uso: `python -m
  laboratorio.scalper_lab.rdloop --mode prematch --rounds 4 --topk 5`.
- `synth_raw.py` — generatore di stream Betfair sintetici (mcm) a risultato
  NOTO (scenari `paradise`/`reversion`/`dead`) per validare l'harness stesso.
  Uso: `python -m laboratorio.scalper_lab.synth_raw --scenario paradise --out <path>`.
- `validate_synth.py` — gira `bt_lab` sugli scenari sintetici di `synth_raw`
  e verifica che l'harness registri il P&L atteso (controllo di onesta' del
  backtest, non della strategia). Uso: `python -m
  laboratorio.scalper_lab.validate_synth`.

---

## `laboratorio/tennis_lab/` — motore di ricerca sweep per il tennis

Import di produzione ammessi: `Betfair.stream.tennis_scalper.tennis_scalper_bot`
(`compute_green`/`ticks_between`), `.tennis_score`, `.tennis_winprob`,
`.tennis_swing_bot` (solo per confronto, vedi `validate.py`),
`Betfair.stream.tools.validate_recordings`, `Betfair.stream.auth`.

### `tennis_lab.py` — `TennisLabStrategy`
**Cosa sa fare**: "motore configurabile per lo SWEEP MASSIVO (centinaia di
combo)" (docstring propria). Copre le 4 famiglie direzionali fondate su edge
noti del tennis-trading (lay favorito estremo/FLB, back favorito, lay
sfavorito, back sfavorito), con delay in-play modellato a livello strategia
(3s in-play / 0 pre-match, perche' il backtest puro di flumine non applica il
bet delay) e motore di uscita con blindatura (`hold`/`green`/`lock_trail`).
Price-driven, niente nomi/punteggio (quello e' nello strato successivo,
`tennis_lab_score.py`). **Bug noti (bibbia `tennis_scalper/BIBBIA_SCALPER_TENNIS.md:39`)**:
`bet_delay_ms="auto"` produce un DOPPIO delay con flumine (che il betDelay lo
applica gia' dal `marketDefinition`); usarlo solo con `bet_delay_ms=0`.
Etichette maker/taker invertite (righe ~271-279 all'epoca dell'audit) — non
fidarsi senza rileggerle.
**Come si lanciava**: mai da sola — via `lab_grid.py`, `validate.py`, o il
test `tests/test_harness_golden.py`.
**Ultima modifica**: 2026-07-10 (`5fe1e8e`). **NON e' in `_BOT_REGISTRY` di
`tennis_runner.py`** (che ha solo tennis_scalper/tennis_pro/tennis_flb/
tennis_swing): non e' mai stata uno dei 4 bot armabili. **Mai certificato sul
banco** — `Betfair/stream/backtest/registro_bot.py:207` lo dice esplicitamente
("Mai una copia di laboratorio (`tennis_lab*` resta fuori dalla produzione)").

### `tennis_lab_score.py` — `ScoreConditionedLab(TennisLabStrategy)`
**Cosa sa fare**: FASE 2 del lab — inietta la timeline dei punteggi
registrati (`.score.jsonl`, sincronizzata sul `publish_time` del book) e
filtra gli ingressi su condizioni di stato di gioco: side-agnostic (`any`,
`set1`, `set2plus`, `pressure`, `calm`, `setlead`, `early`) e side-aware
(richiede `side_map` sel->home/away; fail-safe: lato ignoto = non entra) —
`serving`, `receiving`, `broke`, `gotbroken`. Price-driven + score-gated.
**Ultima modifica**: 2026-07-07 (`40eb205`). **Mai certificato sul banco.**

### `lab_grid.py`
**Cosa sa fare**: grid runner MASSIVO per `TennisLabStrategy` — carica
centinaia di config come strategie separate in UNA sola `FlumineSimulation`
per match (blotter isolato per strategia -> coda/PIQ indipendente) e
aggrega il P&L di settlement su tutti i match conclusi. Classifica per P&L
totale poi per numero di match verdi. Griglia: 4 archetipi (layfav, backfav,
laydog, backdog) x bande di prezzo x gate x maker x uscita.
**Come si lanciava**: `python -m laboratorio.tennis_lab.lab_grid --data DIR
[--smoke] [--top 40]`.
**Ultima modifica**: 2026-09-16 (`f562fff`). **Mai certificato sul banco.**

### `lab_grid_score.py`
**Cosa sa fare**: equivalente di `lab_grid.py` per `ScoreConditionedLab`
(FASE 2) — inietta la timeline dei punteggi, costruisce il `side_map` e gira
la griglia score-gated per match.
**Come si lanciava**: `python -m laboratorio.tennis_lab.lab_grid_score --data
DIR [--top 50]`.
**Ultima modifica**: 2026-09-16 (`f562fff`). **Mai certificato sul banco.**

### `validate.py`
**Cosa sa fare**: validazione train/test su TUTTE le combo (544 price grid +
264 score-cond grid): tiene solo i match ATTIVI (almeno una config ha
tradato), split deterministico train/test per event-id, classifica sul
train, riporta la resa sul test. Il verdetto = config verde su ENTRAMBI
train e test con alto win-rate su test (generalizza, non overfitting).
Include anche una griglia `SWING_GRID` che rigioca `TennisSwingStrategy`
(quella vera, produzione) per confronto — **ma solo la colonna "SW:" usa la
classe di produzione**: le colonne "P:"/"S:" usano `TennisLabStrategy`/
`ScoreConditionedLab` del lab. Per questo, per il proprio referto
storico (`FASE_C9_BACKTEST_SCALPER_TENNIS_2026-09-16.md`), **questo
validatore non certifica nessuno dei 4 bot di produzione**: e' un motore di
ricerca, non il banco.
**Come si lanciava**: `python -m laboratorio.tennis_lab.validate --data DIR
[--min-active 6]`.
**Ultima modifica**: 2026-09-16 (`f562fff`). **Mai certificato sul banco.**

### `tests/test_harness_golden.py`
Suite GOLDEN-RULE (8 test) che valida l'harness di backtest per
`TennisLabStrategy` con scenari sintetici a risultato noto (CRASH/HOLD/
DEAD/SCALP) piu' 4 test "locked" sulla matematica del round-trip verde
(`TennisLabStrategy._locked_from_orders`). Protegge dal bug piu' pericoloso
(P&L rotto = falso "no edge"). Verificata verde dalla nuova posizione (25/09,
8 passed) — vedi `AUDIT_2026-09-25/LABORATORIO_SPOSTAMENTO_2026-09-25.md`.

---

## Struttura file

```
laboratorio/
  __init__.py
  README.md                        (questo file)
  scalper_lab/
    __init__.py
    scalper_bot_base.py             ScalperStrategy (copia base)
    grid_strategy.py                GridStrategy
    theta_strategy.py               ThetaStrategy
    bt_lab.py                       harness backtest ScalperStrategy
    bt_theta.py                     harness backtest ThetaStrategy
    exp_families.py                 esperimento famiglie (round 0)
    rdloop.py                       loop evolutivo RD-Agent-style
    synth_raw.py                    generatore stream sintetici
    validate_synth.py               validazione harness su sintetici
  tennis_lab/
    __init__.py
    tennis_lab.py                   TennisLabStrategy
    tennis_lab_score.py             ScoreConditionedLab (fase 2, score-gated)
    lab_grid.py                     grid runner price-driven
    lab_grid_score.py               grid runner score-conditioned
    validate.py                     validazione train/test 808 combo
    tests/
      __init__.py
      test_harness_golden.py        8 test, harness golden-rule
```
