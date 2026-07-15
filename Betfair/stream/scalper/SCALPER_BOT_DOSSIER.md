# Scalper Bot v2 — Dossier tecnico completo

> Documento di handoff per un **altro agente** (o sviluppatore): **cosa è**,
> **cosa fa**, **come è costruito**, **su quali mercati opera** e **come è
> stato validato** su flumine con partite reali. I riferimenti puntano a file
> e riga dove serve.

- **Costruzione v1:** 2026-06-30 (review + test lo stesso giorno).
- **Riprogettazione v2:** 2026-07-02 — sessione di analisi dati profonda,
  5 bug strutturali trovati e corretti, strategia d'ingresso/uscita rifatta,
  validazione con decomposizione onesta del P&L.
- **Stato:** componente **SEPARATO** da `live_engine_pro`/`live_order_worker`
  (decisione utente 30/06: NON fondere).
- **Percorso codice:** `Betfair/stream/scalper/`
- **Stack:** Python, `flumine` 2.13.11 su `betfairlightweight` 2.23.2.
- **Risultato chiave v2 (anticipato):** dopo i fix, il P&L viene al 100% da
  **scalp chiusi flat** (zero gambe nude, zero rischio settlement) ed è
  **positivo su tutta la regione di parametri testata** nella partita liquida;
  **zero operazioni** nelle partite illiquide (by design: il gate di flusso le
  esclude). Vedi §9. Il profitto è PICCOLO e scala con liquidità/numero di
  partite: il bot va puntato su partite liquide vicino al kickoff.

---

## 1. Struttura dei file

```
Betfair/stream/scalper/
├── __init__.py            # espone ScalperStrategy
├── scalper_bot.py         # LA STRATEGIA (flumine BaseStrategy) — cuore del bot
│                          #   + bias {sid:BACK|LAY}, only_bias, dry_run,
│                          #   force_flat, event_sink (telemetria), stats
├── bias_resolver.py       # CONNETTORE motori→bias: consenso ML+Poisson,
│                          #   dominio, edge moderato, mapping runner PER NOME
├── scalper_service.py     # SERVIZIO supervisore: polla scalper_control,
│                          #   arma una sessione flumine live per evento,
│                          #   scrive stato/statistiche/log (scalper_activity)
├── run_scalper.py         # RUNNER di backtest su FlumineSimulation
├── run_scalper_live.py    # RUNNER LIVE manuale da CLI (alternativa al servizio)
└── (test) Betfair/stream/tests/test_scalper_bot.py (19) +
           test_bias_resolver.py (11) — 30 test unitari

Integrazione prodotto:
├── migrations/scalper_bot.sql          # tabelle scalper_control/activity +
│                                       #   RPC owner-only (activate/stop/state)
├── avvia_scalper_service.bat           # avvio del servizio locale
├── frontend/src/lib/scalper.ts         # client RPC + default validati editabili
└── frontend/src/components/live/ScalperPanel.tsx  # pannello in Segui Live:
    "Attiva Scalper Bot" → modalità (Tradizionale/Direzionale/Entrambe),
    stake+parametri (default validati), ARMATO/dry-run di default,
    stato+consenso motori+statistiche+feed attività, stop (chiude flat)
```

Riuso interno: aggregazione P&L da `Betfair/stream/backtest/run_backtest.py`
(`aggregate_results`); dati replay da `_live_raw/<event_id>/<event_id>.raw.jsonl`
(firehose nativo Betfair registrato live da `recorder.py`).

---

## 2. Filosofia (v2)

> **Fare il maker SOLO dove il mercato paga i maker.** Micro-profitti costanti
> da cattura dello spread nei mercati con flusso bidirezionale reale; ZERO
> presenza nei mercati morti; ogni ciclo finisce PIATTO (green garantito):
> il profitto non dipende MAI dall'esito della partita.

### 2.1 La lezione dei dati (perché la v1 perdeva)

L'analisi tick-per-tick delle partite registrate (spread, code, flusso `trd`
per lato) ha mostrato che:

1. il pre-match è scalpabile SOLO in partite ad alta liquidità vicino al KO
   (es. evento 35674745: MATCH_ODDS con spread ≈1 tick, 2.000€+ ai best,
   ~200k€ di prints nel pre-match). Le altre partite registrate hanno flusso
   quasi nullo: il maker vi riempie UNA gamba sola → scommessa nuda = lotteria;
2. le uscite a mercato (crossare lo spread per un timeout) sono un'emorragia
   sistematica: −1 tick a ciclo;
3. le quote basse (<1.5) hanno code enormi e tick piccoli: cicli lentissimi
   che finiscono trascinati nel gap del kickoff.

### 2.2 Nessun look-ahead

Tutte le decisioni usano **solo il book corrente + finestre del passato**
(deque per-runner). Niente punteggi, esiti o dati futuri. Il replay flumine è
forward-only: il backtest è OOS-onesto.

---

## 3. Le modalità operative

`mode` ∈ `auto` (default) | `join` | `maker` | `reversion`.

### 3.1 `join` — il cuore dello scalping (spread 1-2 tick)

Due gambe **in coda ai touch**: BACK al best lay + LAY al best back. Se
entrambe si riempiono si cattura lo spread. Con spread ≥2 e `improve_inside`
si migliora di 1 tick il lato con la coda più lunga (dentro lo spread la
priorità è immediata). Punti chiave:

- **Gate di flusso** (`min_flow`): si quota solo se negli ultimi
  `flow_window_ms` il mercato ha stampato ≥ `min_flow` € **su entrambi i
  lati** (delta della ladder `trd`, classificati col best del tick precedente:
  `_update_flow`, `scalper_bot.py`). È il filtro che elimina i mercati morti.
- **Requote**: se il book incrocia una nostra quota (fill imminente E avverso)
  o si allontana di ≥ `reprice_ticks`, si cancella e si riquota.
- **Gamba opposta = chiusura**: quando una gamba si riempie, l'altra NON si
  cancella: È già la chiusura al prezzo di profitto, con la priorità di coda
  maturata da quando abbiamo quotato. (La v1 la cancellava e ripiazzava una
  close nuova in fondo alla coda: uccideva la probabilità di uscire in profitto.)
- **Scratch**: se il touch raggiunge il prezzo d'ingresso, la chiusura si
  ripiazza A PARI (profitto 0) una sola volta; se il mercato va oltre di
  `stop_ticks`, chiusura garantita a mercato (stop).
- **Niente uscite a orologio**: TTL lunghissimi; si esce per profitto, scratch,
  stop o finestra KO — mai per timeout che paga lo spread.
- **PIPELINE** (`pipeline`, default **False**): mentre la chiusura riposa in
  coda, pre-piazza l'ingresso del ciclo successivo allo stesso prezzo DIETRO
  di lei (mai doppia esposizione, adozione al riciclo). **A/B sui dati reali:
  NEGATIVO** (−0,99 vs +0,67 a stake 25): il next_entry si riempie quando il
  prezzo attraversa quel livello con slancio → ingressi avversamente
  selezionati. Implementata, misurata, tenuta OFF. Non attivarla senza un
  nuovo A/B su più dati.

### 3.2 `maker` — spread larghi (3-12 tick)

Due gambe DENTRO lo spread (`inside_ticks`), stessi gate e stessa gestione.

### 3.3 `reversion` — una gamba, fade del micro-movimento

Storica v1 (micro-price + WoM). Non usata da `auto` (in v1 perdeva −51/−92€
in-play): attivabile solo esplicitamente.

### 3.4 `auto`

`join` se spread ≤ `join_max_spread`, altrimenti `maker` se lo spread è nella
banda `capture_min/max_ticks`. Mai reversion implicita.

---

## 4. La macchina a stati (per market_id × selection_id)

```
IDLE ──(gate+flusso)──▶ QUOTING2 (join/maker: 2 gambe resting)
QUOTING2 ──(1 gamba piena, size pari)──▶ LOCKING (l'ALTRA gamba è la close)
QUOTING2 ──(book incrocia/si allontana o TTL)──▶ CANCELLING ──▶ IDLE
QUOTING2 ──(2 gambe piene)──▶ DONE se piatto, altrimenti FLATTENING (green)
LOCKING ──(close piena)──▶ DONE se piatto, altrimenti FLATTENING (green residuo)
LOCKING ──(touch = prezzo ingresso)──▶ scratch: close ripiazzata a pari
LOCKING ──(avverso ≥ stop_ticks o lock_ttl)──▶ FLATTENING (+cooldown)
FLATTENING ──(netto piatto)──▶ DONE     [reprice se il flatten è stantio;
                                         MAI arrendersi con un book vivo]
DONE ──(esposizione≠0? ordine orfano vivo?)──▶ sorveglianza: cancel/flatten
DONE ──(tutto risolto, cycles<max)──▶ IDLE (o adozione next_entry → QUOTING2)
```

**Garanzie di sicurezza (tutte verificate sui dati reali):**

- **Gestione in-play SEMPRE attiva**: `check_market_book` NON filtra i book
  in-play nemmeno con `allow_inplay=False` — servono per CHIUDERE le posizioni
  rimaste aperte al KO. Il flag vieta solo i NUOVI ingressi. (Bug v1: il bot
  era cieco in-play → gambe nude a settlement, −73€ in un solo evento.)
- **Finestre kickoff**: `entry_stop_before_s` (default 420s) stop nuovi
  ingressi e cancel degli ingressi resting; `flatten_before_s` (default 180s)
  chiusura forzata di tutto. Il tempo al KO deriva dal `market_time` del
  market_definition vs `publish_time` del book — MAI wall-clock
  (`market.seconds_to_start` usa `datetime.now()`: in replay è privo di senso).
- **⚠️ Bug datetime doppio (py3.13)**: nel processo possono convivere DUE
  classi `datetime` (C e pura). `isinstance(market_time, datetime)` può dare
  False su un datetime valido → in v2 si usa duck-typing su `timestamp()`
  (`_ko_epoch_ms`). Questo bug disattivava TUTTE le protezioni KO in silenzio.
- **Nessun ordine abbandonato**: lo stato DONE sorveglia esposizione e ordini
  vivi (cancel falliti su ordini PENDING vengono ritentati ad ogni book);
  il flatten non si arrende mai finché esiste un book.

---

## 5. La matematica del profitto (invariata dalla v1)

Con back matchato `SB @ OB` e lay `SL @ OL`:

```
net_win  = SB*(OB-1) − SL*(OL-1)     net_lose = SL − SB
compute_green(nw, nl, P) → (side, size, locked): equalizza i due esiti a P.
```

Ogni ciclo termina con `|net_win − net_lose| ≤ 2 cent`: il locked è cassa
certa, indipendente dall'esito. Helper puri (`micro_price`, `wom_imbalance`,
`ticks_between`, `compute_green`) tutti coperti da test.

---

## 6. Parametri (default = configurazione VALIDATA)

**Esecuzione / rischio**
| Param | Default | Note |
|---|---|---|
| `stake` | 25.0 | anche 50 regge, ma il P&L non scala linearmente (code) |
| `scalp_ticks` | 1 | target di profitto |
| `stop_ticks` | 1 | stop dopo lo scratch; 1 ≥ 2 in grid |
| `entry_ttl_ms` | 600000 | TTL lungo: escono i reprice, non l'orologio |
| `lock_ttl_ms` | 3600000 | idem |
| `max_cycles` | 500 | |
| `allow_inplay` | False | le posizioni si GESTISCONO comunque in-play |
| `flatten_before_s` | 180 | chiusura forzata pre-KO |
| `entry_stop_before_s` | 420 | stop+cancel ingressi pre-KO |
| `pipeline` | False | pre-piazza il ciclo successivo dietro la close |

**Gate mercato**
| Param | Default | Note |
|---|---|---|
| `min_flow` | 10.0 | € per LATO in `flow_window_ms`; 10 > 30 in grid |
| `flow_window_ms` / `warmup_ms` | 90000 / 60000 | |
| `min_size` | 150.0 | size minima ai best |
| `price_min` / `price_max` | 1.50 / 4.6 | <1.5 = code lente + KO-risk |
| `join_max_spread` | 2 | join per spread 1-2 tick |
| `capture_min/max_ticks` | 3 / 10 | banda maker inside |
| `improve_inside` | True | migliora 1 tick il lato con coda peggiore |
| `reprice_ticks` | 2 | requote se il book si sposta |
| `max_signal_ticks` | 4 | guardia anti-gap (rottura di regime → cooldown) |
| `cooldown_ms` | 30000 | pausa dopo gap/stop |
| `wom_block` | 0.90 | non quotare con pressione a senso unico |

---

## 7. Storia dei bug (v1 → v2) — da leggere prima di toccare il codice

Review 30/06 (v1): 1 CRIT (floor MIN_STAKE su hedge parziale) + 4 HIGH, corretti.

Sessione 02/07 (v2), trovati con backtest diagnostici su dati reali:

1. **Cecità in-play** — `allow_inplay=False` filtrava i book live: posizioni
   aperte al KO → settlement nudo (−73€). Fix: book sempre accettati, flag
   solo sugli ingressi.
2. **Perdita di coda sulla chiusura** — a gamba riempita si cancellava l'altra
   e si piazzava una close nuova (piq azzerato). Fix: la gamba opposta È la
   chiusura.
3. **Uscite a orologio** — `lock_ttl` 20s crossava lo spread a ogni mancato
   fill (−1 tick a ciclo, sistematico). Fix: TTL lunghi + scratch/stop.
4. **Ordini orfani** — cancel su ordini PENDING falliva in silenzio
   (`cancel_order` lancia; eccezione ingoiata); l'ordine si riempiva minuti
   dopo (KO+252s) riaprendo l'esposizione in uno slot DONE che nessuno
   guardava. Fix: sorveglianza esposizione/ordini in DONE + retry cancel.
5. **`isinstance(datetime)` False su datetime validi** (doppia classe datetime,
   py3.13 + betfairlightweight) → `ko=None` → protezioni KO disattivate.
   Fix: duck-typing su `timestamp()`; il None non si cachea.

---

## 8. Backtest su flumine (invariato nel principio, §8 v1)

`run_scalper.run_scalper(params)`: FlumineSimulation su
`<event>.raw.jsonl`, fill CONSERVATIVI (`simulation_available_prices=False`:
fill solo su volume realmente scambiato, con coda `piq` = size davanti al
nostro prezzo al piazzamento e volume dimezzato), latenze simulate, commissione
5% per-mercato sul netto vincente applicata UNA volta in `aggregate_results`.

**Fedeltà in-play**: flumine non modella il bet-delay → nelle run in-play si
imposta `place_latency≈5.5s`. I risultati in-play restano da leggere con
scetticismo (nessun void degli inmatchati sui gol oltre al lapse su SUSPENDED).

**Decomposizione onesta** (driver di sessione, `bt_one.py`): P&L separato per
selezione FLAT (|esposizione|<5 cent = vero scalp) vs NAKED (residuo a
settlement = fortuna). La v2 chiude TUTTE le selezioni flat.

---

## 9. Validazione v2 (2026-07-02, dati reali, commissione 5%)

### 9.1 Baseline v1 riprodotta (stake 2€)

Scalp veri = **−1,22/−1,65€**; il "+" apparente era solo gambe nude (fortuna).
Conferma il dossier v1 §9.

### 9.2 v2 pre-match — tutte e 4 le partite con pre-match (stake 25€)

| Evento | Ordini | FLAT (scalp veri) | NAKED | Note |
|---|---|---|---|---|
| 35674515 (14min pre, morto) | 0 | 0 | 0 | gate di flusso: correttamente fuori |
| 35760084 (55min pre, morto) | 0 | 0 | 0 | idem |
| 35764745 (114min pre, LIQUIDO) | 37 | **+0,84€** | **0,00** | ~15-20 cicli |
| 35774000 (39min pre, morto) | 0 | 0 | 0 | idem |

### 9.3 Robustezza (grid 16 combinazioni su 35764745)

stake {25,50} × stop {1,2} × improve_inside {on,off} × min_flow {10,30}:

- **naked = 0,00 in 16/16** (il controllo del rischio non dipende dai parametri);
- con `min_flow=10`: **8/8 positive** (+0,44…+0,77 flat);
- con `min_flow=30`: quasi tutte negative (filtra troppo) → default 10;
- stop 1 ≥ stop 2; stake 50 ≈ stake 25 in € (le code limitano i fill).

### 9.4 Ordine di grandezza operativo

- Partita liquida: **~15-20 cicli** nel pre-match (~8-12/ora), 6-9 selezioni
  attive, 2-4 cicli/ora per selezione (collo di bottiglia = coda al touch).
- Cattura tipica ~1 tick ≈ 0,20-0,35€ con stake 25; scratch = 0; stop raro
  −1/−2 tick.
- Partite morte: 0 operazioni (by design).
- Pipeline (§3.1): A/B concluso, peggiorativa → resta OFF.

### 9.5 In-play (round dedicato, place_latency 5,5s ≈ bet-delay)

| Evento | Ordini | FLAT | NAKED |
|---|---|---|---|
| 35674515 | 9 | −6,80€ | 0,00 |
| 35764745 (liquido) | 49 | −4,46€ | 0,00 |
| altri 4 (sottili) | 0 | 0 | 0 |

**Verdetto: in-play il maker meccanico PERDE** (−11,26€ totali) anche con gap
guard, cooldown e scratch: l'adverse selection sui trend in-play (drift
deterministico O/U, gol) domina la cattura dello spread. Il controllo del
rischio regge (0 gambe nude anche attraverso i gap). **Raccomandazione:
produzione SOLO pre-match (`allow_inplay=False`, default)**; l'in-play ha
senso solo sotto una vista direzionale (i modelli), non da solo.

### 9.6 Feature "adattive" testate (A/B su 35764745, base = +0,67€)

| Variante | Net | Verdetto |
|---|---|---|
| gate coda (`max_queue_wait_s` 240/480) | +0,15/+0,18 | ❌ taglia proprio i join che poi pagano |
| filtro deriva (`max_drift_ticks` 3/5) | +0,67 | ≈ neutro (mai scattato) — disponibile, OFF |
| stake dinamico (`stake_max=50`) | +0,64 | ❌ neutro-peggio, OFF |
| stop adattivo sul tempo al KO (`stop_ticks_far=5`) | +0,67 | ≈ neutro — disponibile, OFF |
| profilo "loose" (min_size 50, tutto on) | −0,74 | ❌ i runner sottili ammessi perdono |
| pipeline (§3.1) | −0,99 | ❌ adverse selection |

**Conclusione:** la config validata resta la migliore; l'adattività che paga è
GIÀ dentro (gate di flusso, requote, scratch, finestre KO, gestione in-play).
I parametri sperimentali restano nel codice (default off) da ri-testare quando
ci saranno più partite liquide registrate: con UNA sola partita liquida, ogni
"vittoria" parametrica in più sarebbe probabilmente rumore.

### 9.7 Arbitraggio cross-market: MISURATO, non conviene (02/07)

Analisi dedicata su tutte e 6 le partite (pre-match E in-play), relazioni:
dutch di partizione intra-mercato (MO, O/U, BTTS, HT, CS), MO↔DOUBLE_CHANCE,
monotonia della scala O/U. Margini NETTI dopo commissione 5% per-mercato
(il mercato vincente paga commissione piena, il perdente non compensa),
episodi eseguibili = durata ≥1s pre-match / ≥7s in-play (bet-delay).

**Risultato: pre-match ZERO dislocazioni nette su tutte le partite** (il
cross-matcher Betfair tiene coerenti MO/DC/O/U). In-play solo briciole:
20 episodi su O/U 7.5-8.5 (mercati vuoti, size ~2€) e 4 flash su MO↔DC
post-gol (margine fino a 17% ma durata < 7s: MUOIONO dentro il bet-delay).
**Totale teorico su 6 partite intere: 0,12€.** Il modulo arb NON si
costruisce: evidenza chiara, costo evitato.

### 9.8 Motori statistici vs mercato (test 02/07 sulle partite registrate)

Fonti DB: `fixture_predictions` (ML `model_predictions_json.targets` 21 target;
Poisson `db_json_analisi.markets`; TacticsAI `tactical_engine_json.markets`;
API `percent_*`; frequenze dentro `ht_predictions.details.freq`).
"Frequenze Mercati" dashboard = RPC `get_market_frequency` su tabella `matches`
(per LEGA); "Studio Ritardi" = RPC `get_market_delays` (per LEGA).
Runner Betfair mappati per NOME via `live_markets.selections` (⚠️ MAI per
sortPriority: su 35764745 Betfair aveva casa/ospite INVERTITI vs API).
Anti-leakage verificato: predizioni create 5-7h prima del KO.

**Test 1 — value-taking assoluto ai prezzi registrati (KO−10'): PERDE.**
82 bets (soglia 3%, stake 10, comm 5%) → **−259€**. Pattern chiave: banda
edge 3-10% ≈ pari (−9€); edge 25-50% → −114€. **Un edge dichiarato enorme
contro un mercato liquido è un errore del modello, non valore** (code/dominio).
API percent (quantizzato 45/45/10): 0/6. Freq-lega come prob: 0/6. ML il
migliore: escluso il match fuori dominio (femminile), ≈pari.

**Test 3 — concordanza direzionale 1X2:** ML+Poisson CONCORDI → **4/4
direzioni giuste**; discordi o fuori dominio → errori. La regola del modulo
bias: attivo SOLO con consenso ML+Poisson su lega coperta, e l'ampiezza
dell'edge NON aumenta la size (semmai un edge estremo la azzera).

**Test 2 — bias scalper nel CASO PEGGIORE (35764745, segnale ML sbagliato
su match fuori dominio):** neutro +0,67€ vs bias sbagliato **−0,31€**
(0 gambe nude). La disciplina maker (touch, scratch, stop) limita il danno
di un segnale errato a centesimi — contro i −60/−90€ del value-taking dello
stesso segnale. **Downside del modulo bias: minuscolo. Upside: direzione
giusta nei 4/4 casi di consenso.** Param: `bias={selection_id: BACK|LAY}`.

### 9.9 Sessione 03/07 — regimi di mercato e la regola dell'EQUILIBRIO

Dataset esteso a 8 partite (2 WC iper-liquide registrate live il 02/07).
Certificazione multi-config (stake 25, comm 5%, naked=0 SEMPRE):

- **Ivory-Norway (media, oscillante): +0,67** — l'habitat del maker
- **WC elite: negative** con ogni variante meccanica testata (base −0,21/−1,08;
  trend-surf BOCCIATO: peggiora a −2,24 → default off, codice parcheggiato)
- Partite morte: 0,00 (gate corretti)

**La diagnosi decisiva (analisi dei flussi 5-min per finestra):** il pre-match
elite NON e' in trend: e' CONGELATO con flusso a SENSO UNICO (POR-CRO: lay-
aggressione 10-40x il lato back a prezzo fermo). Il maker simmetrico e' l'unica
controparte di quel fiume → solo fill avversi. Ivory alternava i lati → i
roundtrip si chiudono. **Il discriminante e' l'EQUILIBRIO del flusso, non la
liquidita'**: `flow_balance_min` (min(fb,fl)/max ≥ soglia su finestra 300s)
e' il gate che separa i regimi (sweep soglia in corso al momento della stesura).

**Protezioni di reddito per evento (nuove, nei default):** `event_profit_target`
(1€) con CRICCHETTO (`event_target_giveback` 0,30) e `event_loss_cap` (1,5€)
che al tocco scatena il FORCE-FLAT totale.

**Esito della campagna filtri (onesto):** equilibrio-flusso, oscillazione
richiesta e prints-interni SEPARANO male i regimi al test congiunto (ognuno
o lascia sanguinare l'elite o taglia le catture dell'habitat). Restano nel
codice come parametri OFF. La difesa certificata sull'elite e' il TETTO
(-1,5€ worst case incluse le uscite), non un filtro magico.

**Scaling: il profitto e' limitato dalla CODA, non dallo stake** — stake
25/30/35 su Ivory: +0,67/+0,70/+0,70. Il +1€/match si raggiunge con FINESTRA
piu' lunga (la registrazione copriva ~2h di pre-match; operando 4-6h i cicli
scalano ~linearmente) e col bias motori, non alzando la puntata.

**Tabella finale (stake 25, comm 5%, naked=0 ovunque):**
Ivory (habitat) +0,67..0,70 · elite WC bounded dal cap (peggiore −1,5) ·
morte 0,00. Regola operativa: puntarlo su partite liquide di fascia media;
elite solo con bias motori o non armarlo.

### 9.10 Come scalare l'incasso

1. **Più partite liquide**: il bot è per-evento; N processi = N× opportunità.
   Registrare/puntare top league vicino al KO (il tipo 35764745).
2. **In-play**: flusso 3-10x il pre-match (validazione con scetticismo per i
   limiti del simulatore).
3. Stake: 25→50 regge; oltre, le code diluiscono i cicli.

---

## 10. Test

`Betfair/stream/tests/test_scalper_bot.py` — **19 test**: matematica pura v1
(micro_price, wom, ticks, green) + v2: classificazione del flusso per lato,
finestra del flusso, pricing del join (spread 1/2/3, scelta del lato da
migliorare). Runtime flumine validato end-to-end dai backtest su partite reali.

---

## 10.1 Attivazione da UI (prodotto)

Flusso completo (02/07 sera):

1. **Prerequisiti**: applicare `migrations/scalper_bot.sql` (SQL editor
   Supabase) e avviare `avvia_scalper_service.bat` (resta aperto).
2. In **Segui Live**, seguendo una partita, il pannello **Scalper Bot**
   (chip "Scalper") mostra "Attiva Scalper Bot": scelta modalità
   (Tradizionale = maker validato / Direzionale = solo lato motori /
   Entrambe), stake, parametri modificabili precompilati coi DEFAULT
   VALIDATI, e l'interruttore **"Solo ARMATO (nessun ordine reale)"**
   attivo di default (dry-run: il bot lavora e logga le quote che avrebbe
   piazzato — cablaggio verificabile a rischio zero).
3. Il servizio arma la sessione: risolve il bias (il pannello mostra
   consenso/direzione/edge/motivi), va in OPERATIVO, scrive heartbeat,
   statistiche (cicli, catture, scratch, stop, P&L bloccato) e il feed
   attività in `scalper_activity` (debug/analisi veloci).
4. **Stop**: pulsante "Ferma" (chiude flat) oppure automatico al kickoff
   (finestre KO validate) → stato `done`. Kill-switch di emergenza:
   file `STOP_SCALPER` nella cartella del servizio.

Sicurezza: RPC owner-only (pattern risk-rules/xhedge), tabelle non esposte,
`allow_inplay` forzato False lato servizio, cap esposizione da stake,
whitelist dei parametri modificabili da UI.

## 11. Note per chi riprende il lavoro

- Tenere SEPARATO da `live_engine_pro` (decisione utente).
- **Live**: `run_scalper_live.py` (pre-match only, kill-switch = file
  `STOP_SCALPER`, stake default prudente 5 — la config validata usa 25).
  Prima di alzare lo stake: girare qualche sessione a stake minimo e
  confrontare i fill reali con quelli simulati.
- **La leva n.1 è la LIQUIDITÀ, non i parametri**: registrare più partite di
  top league nell'ultima ora pre-KO (tipo 35764745) e girare il bot in
  parallelo su ciascuna. Il campione attuale è 1 liquida + 5 illiquide.
- In-play: NON attivare da solo (perde, §9.5); ha senso solo sotto una vista
  direzionale dei modelli. Sessione dedicata.
- MAI riportare `isinstance(x, datetime)` nel percorso KO (vedi §7.5).
