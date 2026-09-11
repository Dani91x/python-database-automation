# COSTITUZIONE MIKE — bot Under 3.5 / Over 4.5

Documento normativo del bot Mike (sezione "Mike" dell'app). Come le costituzioni di
Omega e Safe Strategy: ciò che è scritto qui vale più di ogni parametro.

## §0 Verdetto di partenza e gate

- La struttura STATICA (back Under 3.5 + back Over 4.5 tenuti fino al 90') è **NO-GO** su
  18.441 partite reali (ROI −9,67%; con i parametri del bot legacy MIKE2 −6,36%; P(4 gol)
  reale 14,7% prezzata correttamente dal mercato). Mike NON è quella scommessa: è un
  bot di TRADING (green-up pre-match a tick, copertura e cash-out in-play).
- Il green-up in-play simulato dell'Under resta negativo (−9,4% → −3,4%); il back Under
  in-play (theta) è EV− in tutte le varianti testate; O/U 3.5 a 0-0 decade ~0,5 tick/min.
- Quindi: **paper-first**. GO/NO-GO al live solo dopo n≥40 partite paper complete + backtest
  sulle registrazioni REC, con haircut −1 tick sui fill taker. Il verdetto va scritto QUI.

## §1 Sorgenti (regola dei processi: nessuna chiamata Betfair duplicata)

- Quote/stato: SOLO il feed unico `safe_strategy_scan` (scanner Safe) con il ramo pre-KO
  O/U acceso (`SAFE_PRE_KO_OU_HOURS`, es. 3): blocchi `ou` delle linee 3.5/4.5 con
  back/lay/size/status/inplay/`bet_delay`, riga pubblicata già pre-match. Una SELECT per ciclo.
- Punteggi/minuto/rossi/intervallo: stesso feed (`score_raw`, `timeline`).
- Dossier: `fixture_predictions` (λ, ρ, calibrati) via `live_follow`, Atlante hazard,
  transizioni HT→FT — letture DB, zero Betfair.
- Settlement: REST `listMarketBook` (2 chiamate per partita, a mercato chiuso).
- Nessun login nuovo, nessuna connessione stream nuova, nessun catalogo proprio.

## §2 Macchina a stati (engine.py, pura)

WATCH → PRE_ENTRY_PENDING → PRE_OPEN → PRE_GREEN_PENDING → WATCH (ciclo+1) …
Ultimo ingresso (KO − `pre_last_entry_min`): in profitto → green + BACK PERSIST → LIVE;
in perdita → HOLD → LIVE_UNCOVERED. LIVE_UNCOVERED → (cover_timing) → LIVE_COVER_PENDING →
LIVE_COVERED → (cash-out ≥ % / perdita tollerata HT-2T / cap) → LIVE_CLOSING → FLAT →
(1 gol, U4.5 > ingresso) → REENTRY_* → FLAT. Mercato CLOSED → SETTLING → SETTLED.

Invarianti money-critical:
1. Esposizioni SOLO dai fill (`Leg.matched`/`avg_price`), mai dalla size chiesta.
2. Green-up/cash-out con `compute_greenup` (stessa aritmetica del ladder).
3. Commissione per MERCATO sul netto positivo (come `execution.settle_group`).
4. Prezzo mancante → nessuna azione (`cashout_value.complete=False`), mai numeri inventati.
5. Cicli pre-match chiusi = `Leg.archived`: contabilità sì, capitale a rischio no.
6. Riprezzo di una chiusura parzialmente abbinata = SOLO il residuo.
7. `max_liability_per_match` è un clamp DENTRO l'engine (vale anche a UI mal configurata).
8. Mode (paper|live) SOLO da `mike_control.mode`; mai promozione automatica.

## §3 Parametri

Tutti in `config.PARAM_SPEC` (default, cast, min, max, scelte), specchiati in
`frontend/src/lib/mike.ts`. Coppie min/max invertite → default. `mode` non è un parametro.
Importi LIBERI (`stake` ≥ 0,50, `exact_sizes=True`): sotto-minimo / fuori passo via
place-and-trim (`Betfair/stream/trading/submin.py`), come i tool pro. In paper la size esatta
passa direttamente; la legalizzazione .it è solo il ripiego (`exact_sizes=False`).

## §4 Esecuzione e fedeltà paper

- Ordini via `safe_strategy/execution.place` (reserve-first su `mike_trades`, `client_ref
  mike-t<id>`): paper = fill sul feed al prezzo richiesto SOLO se ancora disponibile, size
  cappata al best; live = REST FOK con la sessione condivisa (`omega_market.place_order_live`).
- In paper e in-play il fill è DIFFERITO di `bet_delay` (dal feed) e rieseguito al prezzo
  allora disponibile: mai più ottimista del live.
- Coda flumine (evento seguito dal runner): opt-in `MIKE_USE_FLUMINE_QUEUE=1` (F6).
- Live: PERSIST sull'ultimo ingresso e sub-minimo REST richiedono `persistence` su
  `place_order_live` e `cancel/replaceOrders` sul client REST (F6, non ancora cablati).

## §5 Budget risorse

+1 processo (`mike-service` sotto watchdog, lock 47319). +2 mercati per partita in finestra
sul pool stream dello scanner (tier 2: mai davanti ai mercati in-play; capacità 720, ~100 usati).
Nessun'altra risorsa. Overlap con il blocco opportunità in-play: ≤40 mercati, documentato.

## §6 Cosa Mike NON fa

- Non apre posizioni a bot fermo (protezioni e uscite restano attive).
- Non chiude in perdita fuori dalle regole HT/2T e dal cap di perdita evento.
- Non opera linee non presenti nel feed (re-ingresso solo con 1 gol → Under 4.5).
- Non fa chiamate Betfair per dati; non ha un login proprio.
