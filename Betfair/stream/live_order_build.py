"""Costruzione + validazione ordine flumine per il runner live (Fase 1).

Per chi: il `live_order_worker` (coda comandi) chiama `build_order()` per trasformare
una riga di `betfair_live_order_requests` in un `BetfairOrder` flumine pronto per
`market.place_order(...)`. Money-critical: la validazione qui è l'ultima barriera prima
di un ordine REALE, quindi qualunque input ambiguo solleva `ValueError` (il worker
scrive `error` e NON piazza nulla).

Tutto è logica pura + uso NATIVO di `flumine.utils` (get_nearest_price / price_ticks_away)
e delle classi ordine flumine (LimitOrder / LimitOnCloseOrder / MarketOnCloseOrder /
Trade / BetfairOrder). Nessuna rete, nessun login: testabile a unità con mock del Market.

Giurisdizione conto = .it (Italian Exchange):
  - BACK: stake minimo €2,00, incrementi €0,50 (floor);
  - LAY : size minima €0,50 (no incrementi fissi);
  - NESSUN Minimum Bet Payout;
  - max vincita €10.000; vietato back+lay misti nello stesso ordine (ogni BuiltOrder = 1 lato).
Eccezione sotto-minimo: `reduces_liability=True` (green-up / hedge) consente size sotto
il minimo, soggetta alla guardia profit-ratio INVALID_PROFIT_RATIO (-20% / +25%).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Optional

from flumine.order.order import BetfairOrder
from flumine.order.ordertype import LimitOnCloseOrder, LimitOrder, MarketOnCloseOrder
from flumine.order.trade import Trade
from flumine.strategy.strategy import BaseStrategy
from flumine.utils import MAX_PRICE, MIN_PRICE, get_nearest_price, price_ticks_away

# ---------------------------------------------------------------------------
# Costanti giurisdizione / guardie money-critical
# ---------------------------------------------------------------------------
JURISDICTION_IT = "it"
JURISDICTION_COM = "com"

IT_BACK_MIN_STAKE = 2.00       # stake minimo BACK (€)
IT_BACK_STEP = 0.50            # incremento BACK (€)
IT_LAY_MIN_SIZE = 0.50         # size minima LAY (€)

COM_MIN_STAKE = 2.00           # stake minimo generico .com (€)
COM_MIN_BET_PAYOUT = 20.0      # Min Bet Payout .com: ammesso sotto-minimo se size*price >= 20

MAX_PAYOUT_IT = 10000.0        # max vincita consentita (€)

# Guardia Betfair per ordini sotto-minimo che riducono la liability (green-up/hedge):
# il profit-ratio implicito deve restare nella banda [-20%, +25%].
INVALID_PROFIT_RATIO_MIN = -0.20
INVALID_PROFIT_RATIO_MAX = 0.25

_EPS = 1e-9

_VALID_SIDES = ("back", "lay")
_VALID_ORDER_TYPES = ("LIMIT", "LIMIT_ON_CLOSE", "MARKET_ON_CLOSE")
_VALID_PERSISTENCE = ("LAPSE", "PERSIST", "MARKET_ON_CLOSE")
_VALID_TIF = (None, "FILL_OR_KILL")


# ---------------------------------------------------------------------------
# Dataclass di output
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MinStakeVerdict:
    valid: bool
    legalized_size: Optional[float]   # size arrotondata alla regola di giurisdizione
    reason: Optional[str]             # motivo se non valido


@dataclass(frozen=True)
class BuiltOrder:
    order: BetfairOrder               # Trade+BetfairOrder pronti per market.place_order
    side: str                         # 'BACK' | 'LAY' (convenzione Betfair)
    price: Optional[float]            # già al tick (None per MARKET_ON_CLOSE)
    size: Optional[float]             # già legalizzata (None per MARKET_ON_CLOSE)
    liability: Optional[float]
    persistence: str
    time_in_force: Optional[str]
    min_fill_size: Optional[float]
    note: str                         # tracciabilità


# ---------------------------------------------------------------------------
# Prezzo / tick
# ---------------------------------------------------------------------------
def round_to_tick(price: float) -> float:
    """Snap al tick Betfair valido più vicino (ROUND_HALF_UP, clamp 1.01..1000)."""
    if price is None:
        raise ValueError("price is None")
    return get_nearest_price(float(price))


def ticks_away(price: float, n_ticks: int) -> float:
    """Sposta `n_ticks` lungo la scala Betfair.

    Passa SEMPRE per round_to_tick prima: price_ticks_away usa PRICES_FLOAT.index(price)
    e su un prezzo non-ladder solleverebbe ValueError (non gestito dalla libreria).
    """
    valid = round_to_tick(price)
    return price_ticks_away(valid, int(n_ticks))


# ---------------------------------------------------------------------------
# Lay: size <-> liability
# ---------------------------------------------------------------------------
def lay_size_from_liability(liability: float, price: float) -> float:
    """size = liability / (price - 1), arrotondata a 2 decimali."""
    if price is None or price <= 1.0:
        raise ValueError(f"price {price!r} non valido per conversione lay")
    if liability is None or liability < 0:
        raise ValueError(f"liability {liability!r} non valida")
    return round(float(liability) / (float(price) - 1.0), 2)


def liability_from_lay_size(size: float, price: float) -> float:
    """liability = size * (price - 1), arrotondata a 2 decimali."""
    if price is None or price <= 1.0:
        raise ValueError(f"price {price!r} non valido per conversione lay")
    if size is None or size < 0:
        raise ValueError(f"size {size!r} non valida")
    return round(float(size) * (float(price) - 1.0), 2)


def _floor_to_step(size: float, step: float) -> float:
    """Arrotonda PER DIFETTO al multiplo di `step` (Decimal: niente errori float)."""
    q = (Decimal(str(size)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
    return float(q * Decimal(str(step)))


# ---------------------------------------------------------------------------
# Regole stake minimo per giurisdizione
# ---------------------------------------------------------------------------
def min_stake_rules(
    jurisdiction: str,
    side: str,
    price: float,
    size: float,
    reduces_liability: bool = False,
) -> MinStakeVerdict:
    """Verifica/legalizza la size secondo la giurisdizione.

    .it  -> BACK: min €2,00 + floor a €0,50; LAY: size floor €0,50; NO Min Bet Payout.
    .com -> min €2,00 oppure Min Bet Payout (size*price >= 20).
    `reduces_liability=True` (green-up/hedge) consente size sotto-minimo: in tal caso la
    size è accettata (round 2 decimali) e la guardia profit-ratio resta a carico del
    chiamante (banda INVALID_PROFIT_RATIO_MIN..MAX).
    """
    j = (jurisdiction or "").lower()
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        return MinStakeVerdict(False, None, f"side non valido: {side!r}")
    if size is None or not math.isfinite(size) or size <= 0:
        return MinStakeVerdict(False, None, f"size non valida: {size!r}")

    # Sotto-minimo consentito quando si riduce la liability (hedge / green-up).
    if reduces_liability:
        return MinStakeVerdict(True, round(float(size), 2), None)

    if j == JURISDICTION_IT:
        if s == "back":
            if size < IT_BACK_MIN_STAKE - _EPS:
                return MinStakeVerdict(
                    False, None,
                    f"BACK size {size:.2f} < minimo €{IT_BACK_MIN_STAKE:.2f} (.it)",
                )
            legal = _floor_to_step(size, IT_BACK_STEP)
            if legal < IT_BACK_MIN_STAKE - _EPS:
                return MinStakeVerdict(
                    False, None,
                    f"BACK size legalizzata {legal:.2f} < minimo €{IT_BACK_MIN_STAKE:.2f} (.it)",
                )
            return MinStakeVerdict(True, legal, None)
        # lay
        if size < IT_LAY_MIN_SIZE - _EPS:
            return MinStakeVerdict(
                False, None,
                f"LAY size {size:.2f} < minimo €{IT_LAY_MIN_SIZE:.2f} (.it)",
            )
        return MinStakeVerdict(True, round(float(size), 2), None)

    if j == JURISDICTION_COM:
        payout = float(size) * float(price) if price else 0.0
        if size >= COM_MIN_STAKE - _EPS or payout >= COM_MIN_BET_PAYOUT - _EPS:
            return MinStakeVerdict(True, round(float(size), 2), None)
        return MinStakeVerdict(
            False, None,
            f"{side.upper()} size {size:.2f} < €{COM_MIN_STAKE:.2f} e payout {payout:.2f} "
            f"< Min Bet Payout €{COM_MIN_BET_PAYOUT:.2f} (.com)",
        )

    return MinStakeVerdict(False, None, f"giurisdizione sconosciuta: {jurisdiction!r}")


# ---------------------------------------------------------------------------
# Costruzione ordine
# ---------------------------------------------------------------------------
def build_order(
    market: Any,
    *,
    strategy: BaseStrategy,
    selection_id: int,
    handicap: float,
    side: str,
    order_type: str,
    price: Optional[float],
    size: Optional[float],
    liability: Optional[float],
    persistence: str,
    time_in_force: Optional[str],
    min_fill_size: Optional[float],
    jurisdiction: str,
    max_stake: Optional[float],
    customer_order_ref: str,
    reduces_liability: bool = False,
) -> BuiltOrder:
    """Valida e costruisce un BetfairOrder flumine pronto per `market.place_order`.

    Validazioni: side, tick (get_nearest_price), conversione lay liability<->size,
    min_stake_rules per giurisdizione, FILL_OR_KILL vs persistenza/min_fill_size,
    cap `max_stake`, payout massimo. Solleva `ValueError` con motivo su input invalido.

    ``reduces_liability=True`` (green-up / hedge / cash-out): l'ordine CHIUDE/riduce una
    posizione esistente → ``min_stake_rules`` consente la size SOTTO il minimo di
    giurisdizione (€2 back / €0,50 lay su .it), soggetta solo alla guardia Betfair
    INVALID_PROFIT_RATIO lato Exchange. Usato dall'azione ``greenup`` del worker.

    MONEY-CRITICAL: ``strategy`` DEVE essere l'istanza ``LiveTradingStrategy`` registrata
    nel framework via ``add_strategy``. Il Trade viene creato sotto questa istanza così che
    flumine instradi ``process_orders`` (specchio ordini/posizioni) alla nostra strategia —
    altrimenti l'ordine resta orfano e lo specchio DB non si popola mai.
    """
    if strategy is None:
        raise ValueError("build_order richiede la strategy registrata (LiveTradingStrategy)")
    # --- side -------------------------------------------------------------
    side_l = (side or "").lower()
    if side_l not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    side_bf = "BACK" if side_l == "back" else "LAY"

    # --- order_type -------------------------------------------------------
    ot = (order_type or "").upper()
    if ot not in _VALID_ORDER_TYPES:
        raise ValueError(f"order_type non valido: {order_type!r}")

    # --- persistence ------------------------------------------------------
    pers = (persistence or "LAPSE").upper()
    if pers not in _VALID_PERSISTENCE:
        raise ValueError(f"persistence non valida: {persistence!r}")

    # --- time_in_force / min_fill_size ------------------------------------
    tif = time_in_force if time_in_force in (None, "") else str(time_in_force).upper()
    if tif == "":
        tif = None
    if tif not in _VALID_TIF:
        raise ValueError(f"time_in_force non valido: {time_in_force!r}")
    if tif == "FILL_OR_KILL" and ot != "LIMIT":
        raise ValueError("FILL_OR_KILL ammesso solo su order_type LIMIT")
    if min_fill_size is not None and tif != "FILL_OR_KILL":
        raise ValueError("min_fill_size richiede time_in_force=FILL_OR_KILL")

    market_id = getattr(market, "market_id", None)
    if not market_id:
        raise ValueError("market privo di market_id")

    # =====================================================================
    # Ramo SP (LIMIT_ON_CLOSE / MARKET_ON_CLOSE): si ragiona a liability
    # =====================================================================
    if ot in ("LIMIT_ON_CLOSE", "MARKET_ON_CLOSE"):
        liab = liability if liability is not None else size
        if liab is None or liab <= 0:
            raise ValueError(f"{ot} richiede liability/size > 0")
        liab = round(float(liab), 2)
        if max_stake is not None and liab > float(max_stake) + _EPS:
            raise ValueError(f"liability {liab:.2f} oltre cap max_stake €{float(max_stake):.2f}")
        if ot == "LIMIT_ON_CLOSE":
            if price is None:
                raise ValueError("LIMIT_ON_CLOSE richiede price")
            sp_price = round_to_tick(price)
            order_obj = LimitOnCloseOrder(liability=liab, price=sp_price)
            built_price: Optional[float] = sp_price
        else:
            order_obj = MarketOnCloseOrder(liability=liab)
            built_price = None
        order = _create_order(
            strategy, market_id, selection_id, handicap, side_bf, order_obj, customer_order_ref
        )
        return BuiltOrder(
            order=order, side=side_bf, price=built_price, size=None, liability=liab,
            persistence=pers, time_in_force=tif, min_fill_size=min_fill_size,
            note=f"{ot} liability={liab:.2f}",
        )

    # =====================================================================
    # Ramo LIMIT
    # =====================================================================
    if price is None:
        raise ValueError("order_type LIMIT richiede price")
    if not (MIN_PRICE - _EPS <= float(price) <= MAX_PRICE + _EPS):
        raise ValueError(f"price {price!r} fuori range [{MIN_PRICE}, {MAX_PRICE}]")
    tick_price = round_to_tick(price)

    note_bits = []
    if reduces_liability:
        note_bits.append("reduces_liability (green-up/hedge: sotto-minimo consentito)")

    # Derivazione size per LAY da liability
    if side_l == "lay":
        if size is None and liability is None:
            raise ValueError("LAY richiede size oppure liability")
        if size is None:
            size = lay_size_from_liability(liability, tick_price)
            note_bits.append("lay size da liability")
    else:  # back
        if size is None:
            raise ValueError("BACK richiede size")
    raw_size = round(float(size), 2)

    # Regole stake minimo
    verdict = min_stake_rules(jurisdiction, side_l, tick_price, raw_size, reduces_liability)
    if not verdict.valid:
        raise ValueError(verdict.reason or "size non valida per la giurisdizione")
    legal_size = verdict.legalized_size
    if legal_size is None or legal_size <= 0:
        raise ValueError("size legalizzata non valida")
    if abs(legal_size - raw_size) > _EPS:
        note_bits.append(f"size {raw_size:.2f}->{legal_size:.2f} (legalize)")

    # min_fill_size coerente con la size finale
    if min_fill_size is not None and float(min_fill_size) > legal_size + _EPS:
        raise ValueError(
            f"min_fill_size {float(min_fill_size):.2f} > size {legal_size:.2f}"
        )

    # liability finale (LAY)
    final_liability: Optional[float] = None
    if side_l == "lay":
        final_liability = liability_from_lay_size(legal_size, tick_price)

    # Cap max_stake: rischio = size (BACK) / liability (LAY)
    risk = legal_size if side_l == "back" else (final_liability or 0.0)
    if max_stake is not None and risk > float(max_stake) + _EPS:
        raise ValueError(
            f"rischio €{risk:.2f} oltre cap max_stake €{float(max_stake):.2f}"
        )

    # Payout massimo (.it €10.000): BACK win = size*(price-1); LAY win = size matched
    if side_l == "back":
        profit_if_win = legal_size * (tick_price - 1.0)
    else:
        profit_if_win = legal_size
    if profit_if_win > MAX_PAYOUT_IT + _EPS:
        raise ValueError(
            f"vincita potenziale €{profit_if_win:.2f} oltre il massimo €{MAX_PAYOUT_IT:.2f}"
        )

    limit = LimitOrder(
        price=tick_price,
        size=legal_size,
        persistence_type=pers,
        time_in_force=tif,
        min_fill_size=min_fill_size,
    )
    order = _create_order(
        strategy, market_id, selection_id, handicap, side_bf, limit, customer_order_ref
    )
    if reduces_liability:
        # Marca l'ordine come CHIUSURA (green-up/hedge/cash-out): i control che limitano il
        # FLUSSO (LiveRateControl) devono lasciarlo SEMPRE passare — bloccare un'uscita
        # d'emergenza per rate-limit sarebbe l'opposto della protezione.
        order.context["reduces_liability"] = True

    note = "; ".join(note_bits) if note_bits else "ok"
    return BuiltOrder(
        order=order, side=side_bf, price=tick_price, size=legal_size,
        liability=final_liability, persistence=pers, time_in_force=tif,
        min_fill_size=min_fill_size, note=note,
    )


def _create_order(
    strategy: BaseStrategy,
    market_id: str,
    selection_id: int,
    handicap: float,
    side_bf: str,
    order_type_obj: Any,
    customer_order_ref: str,
) -> BetfairOrder:
    """Crea Trade + BetfairOrder flumine SOTTO la strategia registrata e annota il
    customer_order_ref per il DB.

    Il Trade è legato a ``strategy`` (l'istanza LiveTradingStrategy del framework): è questo
    legame che fa instradare ``process_orders`` alla nostra strategia (lo specchio DB).
    """
    trade = Trade(
        market_id=market_id,
        selection_id=int(selection_id),
        handicap=float(handicap or 0),
        strategy=strategy,
    )
    order = trade.create_order(side=side_bf, order_type=order_type_obj)
    # tracciabilità: il NOSTRO ref INTERNO awlq<id> (correlazione richiesta↔ordine) va in
    # notes E context. NON è il customerRef Betfair: l'attributo flumine inviato all'Exchange
    # è `order.customer_order_ref` = name_hash+sep+order.id (order.id = uuid1, non
    # deterministico). process_orders rilegge il nostro ref da context/notes per ricostruire
    # request_id ↔ ordine nello specchio DB; non fa alcun de-dup lato Betfair.
    if customer_order_ref:
        order.notes["customer_order_ref"] = customer_order_ref
        order.context["customer_order_ref"] = customer_order_ref
    return order
