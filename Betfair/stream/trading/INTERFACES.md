# Fase 1 — CONTRATTO DI INTERFACCIA (foundation live trading)

> Questo documento fissa **firme, schemi e nomi ESATTI** della Fase 1 del piano
> `LIVE_TRADING_SOFTWARE_PLAN.md` (foundation: toggle + client, `LiveTradingStrategy`,
> coda comandi + RPC, worker nel runner, build/validazione, place/cancel/replace +
> place-and-trim, specchio ordini + posizioni, UI minima).
>
> NON è codice di logica: è il contratto a cui devono aderire l'implementazione e i test.
> Money-critical. Convenzioni replicate da: `betfair_order_queue.sql`, `live_stream_rpc.sql`,
> `order_worker.py`, `runner.py`, `config_stream.py`, `frontend/src/lib/betfair.ts`.
>
> Vincoli giurisdizione conto = **.it** (Italian Exchange): back min €2,00 / incrementi €0,50;
> lay size può scendere a €0,50; NO Minimum Bet Payout; max vincita €10.000; placeOrders ≤ 50;
> vietato back+lay misti nello stesso ordine.

---

## 1. Tabelle DB

Tutto in una sola migrazione idempotente: **`migrations/betfair_live_order_queue.sql`**
(`CREATE TABLE/INDEX/FUNCTION IF NOT EXISTS / OR REPLACE`). RLS attivo, REVOKE ALL da
`anon, authenticated`; l'accesso passa solo dalle RPC SECURITY DEFINER (service_role).

### 1.1 `public.betfair_live_order_requests` — coda comandi (place/cancel/replace/place_submin)

Money-critical: stesso pattern di `betfair_order_requests` (client_ref UNIQUE per
idempotenza enqueue, claim atomico pending→processing nel worker, customerRef Betfair
deterministico per de-dup 60s).

| Colonna         | Tipo / vincolo                                                                                                | Note |
|-----------------|---------------------------------------------------------------------------------------------------------------|------|
| `id`            | `BIGSERIAL PRIMARY KEY`                                                                                        | |
| `client_ref`    | `TEXT NOT NULL UNIQUE`                                                                                         | idempotency key (UUID dal frontend) |
| `action`        | `TEXT NOT NULL CHECK (action IN ('place','cancel','replace','place_submin'))`                                 | |
| `mode`          | `TEXT NOT NULL CHECK (mode IN ('paper','live'))`                                                              | deve combaciare con `LIVE_ORDER_MODE` del runner |
| `market_id`     | `TEXT`                                                                                                         | Betfair market_id (es. `1.234567890`); obblig. per place/place_submin |
| `selection_id`  | `BIGINT`                                                                                                       | obblig. per place/place_submin |
| `handicap`      | `NUMERIC NOT NULL DEFAULT 0`                                                                                   | |
| `side`          | `TEXT CHECK (side IN ('back','lay'))`                                                                         | obblig. per place/place_submin |
| `order_type`    | `TEXT NOT NULL DEFAULT 'LIMIT' CHECK (order_type IN ('LIMIT','LIMIT_ON_CLOSE','MARKET_ON_CLOSE'))`            | |
| `price`         | `NUMERIC CHECK (price IS NULL OR price BETWEEN 1.01 AND 1000)`                                                | quota richiesta (il server arrotonda al tick) |
| `size`          | `NUMERIC`                                                                                                     | stake € (back) o size lay; alternativo a `liability` |
| `liability`     | `NUMERIC`                                                                                                     | solo lay: size derivata = `liability/(price-1)` |
| `persistence`   | `TEXT NOT NULL DEFAULT 'LAPSE' CHECK (persistence IN ('LAPSE','PERSIST','MARKET_ON_CLOSE'))`                  | |
| `time_in_force` | `TEXT CHECK (time_in_force IS NULL OR time_in_force IN ('FILL_OR_KILL'))`                                     | NULL = nessuno |
| `min_fill_size` | `NUMERIC`                                                                                                     | usato con FILL_OR_KILL |
| `bet_id`        | `TEXT`                                                                                                         | obblig. per cancel/replace |
| `new_price`     | `NUMERIC CHECK (new_price IS NULL OR new_price BETWEEN 1.01 AND 1000)`                                        | obblig. per replace |
| `size_reduction`| `NUMERIC`                                                                                                     | per cancel parziale e step-2 place_submin |
| `params`        | `JSONB`                                                                                                        | extra (target_size submin, max_stake cap, offset, ecc.) |
| `status`        | `TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','error'))`                  | |
| `result`        | `JSONB`                                                                                                        | esito (vedi shape §3.3 `LiveOrderResult`) |
| `error`         | `TEXT`                                                                                                         | |
| `requested_at`  | `TIMESTAMPTZ NOT NULL DEFAULT now()`                                                                          | |
| `processed_at`  | `TIMESTAMPTZ`                                                                                                  | |

Indice: `idx_blor_pending ON public.betfair_live_order_requests (id) WHERE status = 'pending'`.

> Validazioni di forma (NOT NULL condizionali per `action`) sono enforced nella RPC
> `request_betfair_live_order` (non come CHECK cross-column), come in `request_betfair_order`.

### 1.2 `public.betfair_live_orders` — specchio ordini (write-on-change da `process_orders`)

Scritta dal backend come service_role (bypassa RLS). Sola lettura per la UI via RPC.

| Colonna             | Tipo / vincolo                                  | Note |
|---------------------|-------------------------------------------------|------|
| `id`                | `BIGSERIAL PRIMARY KEY`                          | |
| `bet_id`            | `TEXT`                                            | NULL finché PENDING (non ancora assegnato) |
| `client_order_ref`  | `TEXT`                                            | customer_order_ref flumine (`awlq<req_id>` / strategy ref) |
| `request_id`        | `BIGINT`                                           | FK logica → `betfair_live_order_requests.id` |
| `mode`              | `TEXT NOT NULL CHECK (mode IN ('paper','live'))` | |
| `event_id`          | `TEXT`                                             | |
| `market_id`         | `TEXT NOT NULL`                                   | |
| `selection_id`      | `BIGINT NOT NULL`                                 | |
| `handicap`          | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `side`              | `TEXT NOT NULL CHECK (side IN ('back','lay'))`   | (BACK/LAY mappati lower-case) |
| `order_type`        | `TEXT NOT NULL DEFAULT 'LIMIT'`                   | |
| `price`             | `NUMERIC`                                          | prezzo richiesto |
| `size`              | `NUMERIC`                                          | size richiesta |
| `size_matched`      | `NUMERIC NOT NULL DEFAULT 0`                       | dallo stream/SimulatedExecution |
| `size_remaining`    | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `size_cancelled`    | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `size_lapsed`       | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `size_voided`       | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `average_price_matched` | `NUMERIC NOT NULL DEFAULT 0`                  | avg fill |
| `status`            | `TEXT NOT NULL`                                    | flumine OrderStatus: `PENDING/EXECUTABLE/EXECUTION_COMPLETE/EXPIRED/VIOLATION` |
| `persistence`       | `TEXT`                                             | |
| `placed_at`         | `TIMESTAMPTZ`                                       | |
| `matched_at`        | `TIMESTAMPTZ`                                       | |
| `updated_at`        | `TIMESTAMPTZ NOT NULL DEFAULT now()`              | write-on-change |

Vincolo: `UNIQUE (mode, bet_id)` quando `bet_id IS NOT NULL` (upsert per bet_id);
indice `idx_blo_market ON (market_id)` per la UI. Upsert chiave fallback su
`(mode, client_order_ref)` finché `bet_id` è NULL.

### 1.3 `public.betfair_live_positions` — esposizioni per selezione (da `blotter.get_exposures`)

Una riga per `(mode, market_id, selection_id)`. Numeri presi da
`flumine.markets.blotter.Blotter.get_exposures` / `selection_exposure` (mai ricalcolati a mano).

| Colonna                  | Tipo / vincolo                                   | Note |
|--------------------------|--------------------------------------------------|------|
| `id`                     | `BIGSERIAL PRIMARY KEY`                           | |
| `mode`                   | `TEXT NOT NULL CHECK (mode IN ('paper','live'))` | |
| `event_id`               | `TEXT`                                            | |
| `market_id`              | `TEXT NOT NULL`                                   | |
| `selection_id`           | `BIGINT NOT NULL`                                 | |
| `handicap`               | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `matched_if_win`         | `NUMERIC NOT NULL DEFAULT 0`                       | profit-se-vince da ordini matched |
| `matched_if_lose`        | `NUMERIC NOT NULL DEFAULT 0`                       | profit-se-perde da ordini matched |
| `worst_if_win`           | `NUMERIC NOT NULL DEFAULT 0`                       | worst_possible_profit_on_win (matched+unmatched) |
| `worst_if_lose`          | `NUMERIC NOT NULL DEFAULT 0`                       | worst_possible_profit_on_lose |
| `selection_exposure`     | `NUMERIC NOT NULL DEFAULT 0`                       | `max(0, -min(win,lose))` |
| `unmatched_back_exposure`| `NUMERIC NOT NULL DEFAULT 0`                       | |
| `unmatched_lay_exposure` | `NUMERIC NOT NULL DEFAULT 0`                       | |
| `net_position`           | `NUMERIC NOT NULL DEFAULT 0`                       | size netta (back − lay) matched |
| `updated_at`             | `TIMESTAMPTZ NOT NULL DEFAULT now()`              | |

Vincolo: `UNIQUE (mode, market_id, selection_id, handicap)` (upsert);
indice `idx_blp_market ON (market_id)`.

---

## 2. RPC (tutte SECURITY DEFINER, `SET search_path = public, pg_temp`)

Grant pattern identico alle altre code:
`REVOKE ALL FROM public, anon; GRANT EXECUTE TO authenticated, service_role`.

### 2.1 Scrittura coda (frontend)

```sql
-- accoda UN comando. Idempotente su client_ref (retry sicuro). VOLATILE.
public.request_betfair_live_order(p jsonb) RETURNS bigint
```
Validazioni minime (RAISE EXCEPTION):
- `client_ref` obbligatorio (nullif vuoto).
- `action ∈ {place,cancel,replace,place_submin}` obbligatorio; `mode ∈ {paper,live}` obbligatorio.
- `action='place'|'place_submin'` → `market_id`, `selection_id`, `side`, `price` obbligatori.
- `action='cancel'` → `bet_id` obbligatorio.
- `action='replace'` → `bet_id` + `new_price` obbligatori; `new_price ∈ [1.01,1000]`.
- `price`/`new_price` (se presenti) ∈ `[1.01,1000]`.
- Idempotenza: SELECT id WHERE client_ref → se esiste ritorna; altrimenti INSERT
  `ON CONFLICT (client_ref) DO NOTHING` + fallback SELECT (race-safe).

```sql
-- stato/esito di un comando in coda (poll). STABLE.
public.get_betfair_live_order(p_id bigint) RETURNS jsonb   -- to_jsonb(riga)
```

### 2.2 Letture per la UI (frontend)

```sql
-- specchio ordini di un mercato. STABLE. { rows: [ ...betfair_live_orders ] }
public.get_live_orders(p_market_id text) RETURNS jsonb

-- esposizioni/posizioni di un mercato. STABLE. { rows: [ ...betfair_live_positions ] }
public.get_live_positions(p_market_id text) RETURNS jsonb
```
Forma: come `get_live_follows` (`jsonb_build_object('rows', jsonb_agg(...))`,
`coalesce(...,'[]')`). Validano `p_market_id NOT NULL` e `length <= 32`.
Filtrano opzionalmente per `mode` se presente in `params`? No: ritornano entrambe le
mode con colonna `mode` (la UI filtra in base al badge attivo).

> Nessuna RPC di scrittura per `betfair_live_orders`/`betfair_live_positions`: le scrive
> il backend come service_role (mirror del commento in `live_stream_rpc.sql`).

---

## 3. Firme Python

### 3.1 `Betfair/stream/live_order_build.py` (build + validazione, blindato)

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
from flumine.order.order import BetfairOrder

JURISDICTION_IT = "it"
JURISDICTION_COM = "com"

@dataclass(frozen=True)
class MinStakeVerdict:
    valid: bool
    legalized_size: Optional[float]   # size arrotondata alla regola di giurisdizione
    reason: Optional[str]             # motivo se non valido

def round_to_tick(price: float) -> float:
    """utils.get_nearest_price(price): snap al tick Betfair valido (clamp 1.01..1000)."""

def ticks_away(price: float, n_ticks: int) -> float:
    """utils.price_ticks_away dopo round_to_tick (evita ValueError su prezzo non-ladder)."""

def lay_size_from_liability(liability: float, price: float) -> float:
    """size = liability/(price-1), arrotondata a 2 decimali."""

def liability_from_lay_size(size: float, price: float) -> float:
    """liability = size*(price-1), 2 decimali."""

def min_stake_rules(
    jurisdiction: str,      # 'it' | 'com'  (config BETFAIR_JURISDICTION)
    side: str,              # 'back' | 'lay'
    price: float,
    size: float,
    reduces_liability: bool = False,
) -> MinStakeVerdict:
    """.it: back min €2,00 + floor a €0,50; lay size floor €0,50; no Min Bet Payout.
    .com: min €2 oppure Min Bet Payout (size*price >= 20). reduces_liability=True →
    consente sotto-minimo (green-up/hedge) soggetto a anti-rounding §1bis."""

@dataclass(frozen=True)
class BuiltOrder:
    order: BetfairOrder        # Trade+BetfairOrder pronti per market.place_order
    side: str                  # 'BACK' | 'LAY' (Betfair)
    price: float               # già al tick
    size: float                # già legalizzata
    liability: Optional[float]
    persistence: str
    time_in_force: Optional[str]
    min_fill_size: Optional[float]
    note: str                  # tracciabilità (es. "lay size da liability")

def build_order(
    market: Any,               # flumine Market (per market_id + runner lookup)
    *,
    selection_id: int,
    handicap: float,
    side: str,                 # 'back' | 'lay'
    order_type: str,           # 'LIMIT' | 'LIMIT_ON_CLOSE' | 'MARKET_ON_CLOSE'
    price: Optional[float],
    size: Optional[float],
    liability: Optional[float],
    persistence: str,
    time_in_force: Optional[str],
    min_fill_size: Optional[float],
    jurisdiction: str,
    max_stake: Optional[float],         # cap anti-errore
    customer_order_ref: str,            # 'awlq<req_id>'
) -> BuiltOrder:
    """Valida (side, tick, min_stake_rules, FoK vs persistenza, cap max_stake, payout)
    e costruisce LimitOrder/LimitOnClose/MarketOnClose + BetfairOrder. Solleva
    ValueError con motivo su input non valido (il worker scrive 'error', nessun ordine)."""
```

### 3.2 `Betfair/stream/trading/submin.py` (place-and-trim, macchina a stati idempotente)

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

class SubminStep(str, Enum):
    INIT = "init"
    PLACED = "placed"        # step1: place min @ quota non abbinabile, LAPSE
    TRIMMED = "trimmed"      # step2: cancel size_reduction → resta target
    REPRICED = "repriced"    # step3: replace new_price = quota target
    DONE = "done"
    ABORTED = "aborted"      # guardia rischio: step1 abbinato → STOP+alert

@dataclass
class SubminState:
    step: SubminStep
    bet_id: Optional[str]
    target_size: float
    target_price: float          # già al tick
    placed_size: float           # = minimo giurisdizione (€2 .it)
    side: str                    # 'back' | 'lay'
    note: str

def initial_place_price(side: str) -> float:
    """Quota non abbinabile: BACK→1000.0, LAY→1.01 (match quasi impossibile)."""

def advance_submin(
    market: Any,                 # flumine Market
    state: SubminState,
    *,
    order: Any = None,           # BetfairOrder corrente (status/size_remaining)
    jurisdiction: str,
    customer_order_ref: str,
) -> SubminState:
    """Avanza UNO step in base allo stato dell'ordine (PENDING/EXECUTABLE/...).
    Guardia rischio: se step1 risulta size_matched>0 → SubminStep.ABORTED (mai ripetere).
    Idempotente: ri-eseguibile dallo stesso state senza doppi place."""
```

### 3.3 `Betfair/stream/live_order_worker.py` (BackgroundWorker nel runner)

```python
from __future__ import annotations
from typing import Any, Dict, Optional
from flumine import Flumine

_TABLE = "betfair_live_order_requests"

# Esito scritto in betfair_live_order_requests.result (shape stabile, letto dal frontend)
# LiveOrderResult = {
#   "ok": bool, "action": str, "mode": str,
#   "bet_id": str|None, "status": str|None,           # OrderStatus flumine
#   "size_matched": float|None, "average_price_matched": float|None,
#   "size_remaining": float|None,
#   "market_id": str|None, "selection_id": int|None, "side": str|None,
#   "price": float|None, "size": float|None, "customer_order_ref": str|None,
#   "submin_step": str|None,                            # per action place_submin
#   "error": str|None, "detail": str|None,
# }

def live_order_worker(context: dict, flumine: Flumine, session: Any) -> None:
    """BackgroundWorker (firma flumine: context, flumine, **func_kwargs).
    Aggiunto al framework SOLO se LIVE_ORDER_MODE in {PAPER,LIVE}.
    - claim atomico pending→processing (mode deve combaciare con LIVE_ORDER_MODE);
    - risolve Market = flumine.markets.markets[market_id];
    - place/place_submin: build_order()/advance_submin() → market.place_order(order,
      market_version=..., customer_strategy_ref='live');
    - cancel: market.cancel_order(order, size_reduction); replace: market.replace_order(order, new_price);
    - trova l'ordine per bet_id nel blotter (market.blotter);
    - scrive result/error; NON ri-processa processing/done/error (crash → riconciliazione manuale).
    Il fill (size_matched/avg_price) arriva async: LIVE via order_stream, PAPER via
    SimulatedExecution → riflesso nello specchio da LiveTradingStrategy.process_orders (§3.4)."""

def _claim(sb: Any, rid: int) -> bool: ...
def _find_order_by_bet_id(flumine: Flumine, market_id: str, bet_id: str) -> Optional[Any]: ...
def _process_once(sb: Any, flumine: Flumine, session: Any) -> int: ...
```

### 3.4 `Betfair/stream/engine/live_trading_strategy.py` (specchio, NO auto-trade)

```python
from __future__ import annotations
from typing import Any
from flumine import BaseStrategy

class LiveTradingStrategy(BaseStrategy):
    """Strategia advisory: NON piazza ordini in automatico. Specchia ordini e
    posizioni nel DB. Convive con MarketRecorderStrategy (stessi market_id)."""

    def __init__(self, *args: Any, session: Any = None, mode: str = "paper", **kwargs: Any) -> None: ...

    def process_market_book(self, market: Any, market_book: Any) -> None:
        """NO-OP (nessun ordine automatico)."""

    def process_orders(self, market: Any, orders: list) -> None:
        """Hook fill: write-on-change → betfair_live_orders (bet_id, size_matched,
        avg_price, status, ...) + ricalcolo betfair_live_positions da
        market.blotter.get_exposures(self, lookup) per ogni selezione toccata."""
```

Funzioni di scrittura DB (in `Betfair/stream/db.py`, mirror dello stile esistente):

```python
def upsert_live_order(row: Dict[str, Any]) -> None: ...        # write-on-change specchio
def upsert_live_position(row: Dict[str, Any]) -> None: ...     # da get_exposures
def claim_live_order_request(rid: int) -> bool: ...            # opzionale (o inline nel worker)
```

### 3.5 Modifiche a `Betfair/stream/runner.py`

```python
def build_order_client(api_client, mode: str):
    """Costruisce clients.BetfairClient per modalità:
    OFF   -> BetfairClient(api_client, order_stream=False)        # comportamento attuale
    PAPER -> BetfairClient(api_client, paper_trade=True)          # SimulatedExecution
    LIVE  -> BetfairClient(api_client, order_stream=True)         # fill reali
    Ritorna anche un flag 'orders_enabled' = mode in {PAPER,LIVE}."""
```
In `setup_and_run`:
- sostituire `client = clients.BetfairClient(api_client, order_stream=False)` con
  `build_order_client(api_client, LIVE_ORDER_MODE)`;
- se `orders_enabled`: `framework.add_strategy(LiveTradingStrategy(market_filter=..., session=session, mode=...))`
  e `framework.add_worker(BackgroundWorker(framework, function=live_order_worker,
  interval=int(LIVE_ORDER_QUEUE_POLL_SEC), func_kwargs={"session": session}, name="live_order_worker"))`;
- log cubitale modalità all'avvio + scrittura badge (live_now/alert): `OFF` / `PAPER` / `🔴 LIVE REALE`.

### 3.6 Aggiunte a `Betfair/stream/config_stream.py`

```python
# Toggle modalità ordini (default OFF = zero regressioni)
LIVE_ORDER_MODE: str = os.getenv("LIVE_ORDER_MODE", "OFF").upper()        # OFF|PAPER|LIVE
BETFAIR_JURISDICTION: str = os.getenv("LIVE_BETFAIR_JURISDICTION", "it")  # it|com

# Velocità per-modalità (LIVE veloce, PAPER rilassato)
LIVE_ORDER_QUEUE_POLL_SEC: float = float(os.getenv("LIVE_ORDER_QUEUE_POLL_SEC", "1"))
LIVE_ORDER_QUEUE_BATCH: int = int(os.getenv("LIVE_ORDER_QUEUE_BATCH", "5"))
ORDER_STREAM_CONFLATE_MS: int = int(os.getenv("LIVE_ORDER_STREAM_CONFLATE_MS", "0"))
PAPER_SIMULATED_LATENCY_MS: int = int(os.getenv("LIVE_PAPER_SIMULATED_LATENCY_MS", "120"))

# Cap di sicurezza Fase 1 (kill-switch + limiti)
LIVE_MAX_STAKE_PER_ORDER: float = float(os.getenv("LIVE_MAX_STAKE_PER_ORDER", "10"))
LIVE_KILL_SWITCH: bool = os.getenv("LIVE_KILL_SWITCH", "false").lower() == "true"
```

---

## 4. API frontend

### 4.1 `frontend/src/lib/liveOrders.ts` (chiamate RPC, no UI)

Stile mirror di `betfair.ts` (`supabase.rpc`, polling con deadline, idempotenza UUID).

```ts
export type LiveOrderMode = 'paper' | 'live';
export type LiveOrderAction = 'place' | 'cancel' | 'replace' | 'place_submin';

export interface LiveOrderCommand {
  action: LiveOrderAction;
  mode: LiveOrderMode;
  market_id?: string;
  selection_id?: number;
  handicap?: number;
  side?: 'back' | 'lay';
  order_type?: 'LIMIT' | 'LIMIT_ON_CLOSE' | 'MARKET_ON_CLOSE';
  price?: number;
  size?: number | null;
  liability?: number | null;
  persistence?: 'LAPSE' | 'PERSIST' | 'MARKET_ON_CLOSE';
  time_in_force?: 'FILL_OR_KILL' | null;
  min_fill_size?: number | null;
  bet_id?: string;
  new_price?: number;
  size_reduction?: number;
  params?: Record<string, unknown>;
}

export interface LiveOrderResult {           // = betfair_live_order_requests.result (§3.3)
  ok: boolean; action: string; mode: string;
  bet_id?: string | null; status?: string | null;
  size_matched?: number | null; average_price_matched?: number | null;
  size_remaining?: number | null;
  market_id?: string | null; selection_id?: number | null; side?: string | null;
  price?: number | null; size?: number | null; customer_order_ref?: string | null;
  submin_step?: string | null; error?: string | null; detail?: string | null;
}

export interface LiveOrderRow { /* mirror betfair_live_orders */ }
export interface LivePositionRow { /* mirror betfair_live_positions */ }

// enqueue idempotente (client_ref UUID) + polling get_betfair_live_order (done/error/timeout)
export async function sendLiveOrderCommand(cmd: LiveOrderCommand): Promise<LiveOrderResult>;

// letture per i pannelli
export async function fetchLiveOrders(marketId: string): Promise<LiveOrderRow[]>;
export async function fetchLivePositions(marketId: string): Promise<LivePositionRow[]>;
```

Costanti polling: `LIVE_ORDER_POLL_MS = 1000`, `LIVE_ORDER_TIMEOUT_MS = 90_000`.
Su timeout: throw "NON reinviare" (l'ordine potrebbe essere stato piazzato).

### 4.2 Componente pannello

`frontend/src/components/live/LiveTradingPanel.tsx` — UI minima Fase 1:
order entry (back/lay, prezzo, size/liability, persistence, cap), badge modalità
(`PAPER` / `🔴 LIVE REALE` / `OFF`), lista ordini (`fetchLiveOrders`) con cancel/replace
inline, tabella posizioni/P&L (`fetchLivePositions`). Kill-switch visibile.

---

## 5. File da creare / modificare

### Da creare
- `migrations/betfair_live_order_queue.sql` — 3 tabelle + 4 RPC + grant/RLS (§1, §2).
- `Betfair/stream/live_order_build.py` — build + validazione (§3.1).
- `Betfair/stream/trading/__init__.py` — package marker.
- `Betfair/stream/trading/submin.py` — place-and-trim (§3.2).
- `Betfair/stream/live_order_worker.py` — BackgroundWorker coda (§3.3).
- `Betfair/stream/engine/live_trading_strategy.py` — specchio, NO auto (§3.4).
- `frontend/src/lib/liveOrders.ts` — API RPC (§4.1).
- `frontend/src/components/live/LiveTradingPanel.tsx` — pannello UI (§4.2).
- Test: `Betfair/stream/tests/test_live_order_build.py`, `test_submin.py`,
  `test_live_order_worker.py` (mock client Betfair, nessuna rete);
  `frontend/src/lib/liveOrders.test.ts` (logica pura) se applicabile.

### Da modificare
- `Betfair/stream/runner.py` — `build_order_client`, add_strategy/add_worker condizionali, badge (§3.5).
- `Betfair/stream/config_stream.py` — toggle + velocità + cap (§3.6).
- `Betfair/stream/db.py` — `upsert_live_order`, `upsert_live_position` (+ eventuale claim) (§3.4).
- (NON toccare `Betfair/order_exec.py` — path PRE-MATCH invariato.)

### Note money-critical / vincoli
- `LIVE_ORDER_MODE=OFF` di default → zero regressioni sul runner attuale (`order_stream=False`).
- Worker: claim atomico, `mode` riga == `LIVE_ORDER_MODE`, mai ri-processare processing/done/error.
- `.it`: build_order rifiuta back < €2,00 e floor a €0,50; lay size floor €0,50; nessun
  Min Bet Payout; cap `max_stake`/`LIVE_MAX_STAKE_PER_ORDER`; vietato back+lay nello stesso ordine.
- Esposizioni SEMPRE da `blotter.get_exposures` (mai ricalcolo a mano); fill da
  order_stream (LIVE) o SimulatedExecution (PAPER), riflessi via `process_orders`.
- Place-and-trim su `.it` = da verificare empiricamente (cert LIVE minimale, §protocollo piano).
</content>
</invoke>
