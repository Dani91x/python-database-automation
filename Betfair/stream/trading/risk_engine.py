"""risk_engine.py — matematica PURA del risk engine live (Fase 3).

Per chi: il ``risk_engine_worker`` (BackgroundWorker del runner) chiama queste funzioni
per decidere, a fronte del prezzo corrente e delle esposizioni MATCHED di una selezione,
SE e COME chiudere/coprire una posizione. Tutta la logica qui è pura (nessun I/O, nessuna
rete, nessun ordine): è il worker a leggere prezzi/esposizioni fresche e ad ACCODARE
l'ordine risultante nella coda ``betfair_live_order_requests`` (stesso path audited/mirror).

Replica la semantica dei tool professionali (Bet Angel / Cymatic / Fairbot):
  * OFFSET / bracket   : al fill dell'ingresso, ordine OPPOSTO di chiusura a target profit,
                         a N tick (o %) dal prezzo d'ingresso. Back-first → LAY più BASSO;
                         Lay-first → BACK più ALTO. Variante "greening" = size che pareggia.
  * STOP-LOSS          : due parametri (Bet Angel) — ``trigger`` (quanto contro prima che
                         scatti) e ``place_at`` (dove si invia). Ma la CHIUSURA avviene al
                         BEST disponibile opposto (attraversa lo spread → match garantito),
                         NON letteralmente a N tick. Ticks o %.
  * TAKE-PROFIT        : soglia su P&L mark-to-market (o = l'offset stesso).
  * TRAILING STOP      : lo stop cricchetta di 1 tick (o %) verso la posizione per ogni tick
                         favorevole; blocca progressivamente un'uscita migliore.

⚠️ SOFTWARE-SIDE: come tutti gli incumbent, questi stop/offset sono innescati DAL SOFTWARE
(non ordini "resting" sull'Exchange). Se il processo/connessione cade, NON esistono. Il
worker/UI lo dichiara esplicitamente. La matematica qui è solo il "quando" e il "quanto".

Convenzioni prezzo/tick (flumine.utils, verificate):
  * ``price_ticks_away(p, +n)`` = quota PIÙ ALTA (odds lunghe); ``-n`` = più bassa.
  * back-first è in PROFITTO quando la quota SCENDE; in PERDITA quando SALE. Lay-first è
    l'opposto (profitto quando la quota SALE).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from flumine.utils import (
    MAX_PRICE,
    MIN_PRICE,
    PRICES_FLOAT,
    get_nearest_price,
    price_ticks_away,
)

# Soglia "posizione già piatta"/importi trascurabili: sotto 1 cent non si opera (il minimo
# movimento di denaro su Betfair è il centesimo → niente ordini-fantasma a €0,00).
FLAT_EPS = 0.01
_EPS = 1e-9

_VALID_SIDES = ("back", "lay")

# Indice O(1) prezzo→posizione nella ladder Betfair, per contare i tick tra due prezzi.
_PRICE_INDEX = {round(p, 2): i for i, p in enumerate(PRICES_FLOAT)}


# ---------------------------------------------------------------------------
# Helper tick / prezzo
# ---------------------------------------------------------------------------
def snap(price: float) -> float:
    """Snap al tick Betfair valido più vicino (clamp 1.01..1000)."""
    if price is None or not math.isfinite(float(price)):
        raise ValueError(f"price non valido: {price!r}")
    return get_nearest_price(float(price))


def move_ticks(price: float, n_ticks: int) -> float:
    """Sposta ``n_ticks`` lungo la ladder (n>0 = quota più alta). Snap difensivo a monte
    (price_ticks_away richiede un prezzo GIÀ sulla ladder, altrimenti solleva)."""
    valid = snap(price)
    moved = price_ticks_away(valid, int(n_ticks))
    # clamp ai limiti della ladder (price_ticks_away può uscire ai bordi)
    if moved < MIN_PRICE:
        return MIN_PRICE
    if moved > MAX_PRICE:
        return MAX_PRICE
    return moved


def ticks_between(p_from: float, p_to: float) -> int:
    """Numero di tick (con segno) da ``p_from`` a ``p_to`` sulla ladder Betfair.

    Positivo se ``p_to`` è più in alto (quota più lunga). Entrambi i prezzi sono snappati
    al tick valido più vicino prima del confronto.
    """
    i_from = _PRICE_INDEX.get(round(snap(p_from), 2))
    i_to = _PRICE_INDEX.get(round(snap(p_to), 2))
    if i_from is None or i_to is None:  # pragma: no cover - snap garantisce l'appartenenza
        raise ValueError(f"prezzo fuori ladder: {p_from!r}->{p_to!r}")
    return i_to - i_from


def pct_price(price: float, pct: float, direction: int) -> float:
    """Prezzo spostato di una FRAZIONE ``pct`` (es. 0.02 = 2%) in ``direction`` (+1 su, -1 giù),
    poi snappato al tick valido. Usato per offset/stop espressi in percentuale."""
    if pct is None or pct < 0:
        raise ValueError(f"pct non valida: {pct!r}")
    raw = float(price) * (1.0 + (1 if direction >= 0 else -1) * float(pct))
    return snap(raw)


def _opp_side(side: str) -> str:
    return "lay" if side == "back" else "back"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RiskOrder:
    """Ordine di chiusura/copertura calcolato. ``actionable`` False = niente da fare."""

    side: Optional[str]        # 'back' | 'lay' | None
    price: Optional[float]     # prezzo (già al tick)
    size: Optional[float]      # stake (>0), arrotondato a 2 decimali
    note: str

    @property
    def actionable(self) -> bool:
        return (
            self.side in _VALID_SIDES
            and self.price is not None
            and self.size is not None
            and self.size > 0.0
        )


def _norm(side: Optional[str], price: Optional[float], size: Optional[float], note: str) -> RiskOrder:
    if side is None or price is None or size is None:
        return RiskOrder(None, None, None, note)
    s = round(float(size), 2)
    if s <= 0.0:
        return RiskOrder(None, None, None, f"{note}; size→0 dopo arrotondamento")
    return RiskOrder(side=side, price=snap(price), size=s, note=note)


# ---------------------------------------------------------------------------
# Hedge sizing a un PREZZO SPECIFICO (base di greening/flatten). Coerente con
# trading/greenup.compute_greenup ma al prezzo dato invece del best.
# ---------------------------------------------------------------------------
def hedge_size_at(matched_if_win: float, matched_if_lose: float, price: float) -> "tuple[Optional[str], float]":
    """(side, size) dell'UNICO ordine che PAREGGIA W e L se abbinato a ``price``.

    diff = W − L. diff>0 → LAY size = diff/price. diff<0 → BACK size = -diff/price.
    |diff|<FLAT_EPS → (None, 0). È la stessa aritmetica di compute_greenup, esposta per
    l'offset-con-greening e per il flatten dello stop a un prezzo scelto (best opposto).
    """
    if price is None or not math.isfinite(price) or price <= 1.0:
        return None, 0.0
    w = float(matched_if_win)
    l = float(matched_if_lose)
    diff = w - l
    if abs(diff) < FLAT_EPS:
        return None, 0.0
    if diff > 0.0:
        return "lay", round(diff / price, 2)
    return "back", round(-diff / price, 2)


def mark_to_market(
    matched_if_win: float,
    matched_if_lose: float,
    best_back_price: Optional[float],
    best_lay_price: Optional[float],
) -> Optional[float]:
    """P&L BLOCCATO se si chiudesse (green-up) ORA al best opposto. None se non calcolabile.

    diff>0 (sbilancio sul vince) → si LAYa al best_lay → locked = L + diff/best_lay.
    diff<0 (sbilancio sul perde) → si BACKa al best_back → locked = W + (−diff)/best_back...
      in forma simmetrica: locked = W + (L−W)/best_back.
    |diff|<FLAT_EPS → posizione già piatta → locked = W (≈ L).
    """
    w = float(matched_if_win)
    l = float(matched_if_lose)
    diff = w - l
    if abs(diff) < FLAT_EPS:
        return round((w + l) / 2.0, 2)
    # locked = L + (W−L)/p  (UNIFICATA per entrambi i rami; p = best_lay se sbilancio sul
    # vince, best_back se sul perde). È la stessa aritmetica di greenup.compute_greenup:
    #   diff>0 → LAY al best_lay, size=diff/p → esiti pareggiati a L + diff/p;
    #   diff<0 → BACK al best_back, size=(−diff)/p → esiti pareggiati a L + diff/p (diff<0).
    p = best_lay_price if diff > 0.0 else best_back_price
    if p is None or not math.isfinite(p) or p <= 1.0:
        return None
    return round(l + diff / p, 2)


# ---------------------------------------------------------------------------
# OFFSET (bracket / take-profit a distanza fissa)
# ---------------------------------------------------------------------------
def offset_target_price(
    entry_side: str,
    entry_price: float,
    *,
    offset_ticks: Optional[int] = None,
    offset_pct: Optional[float] = None,
) -> float:
    """Prezzo dell'ordine di chiusura in PROFITTO (l'offset).

    back-first → chiude LAY a quota PIÙ BASSA (odds accorciate): −offset.
    lay-first  → chiude BACK a quota PIÙ ALTA (odds allungate):  +offset.
    Esattamente uno tra offset_ticks / offset_pct.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    if (offset_ticks is None) == (offset_pct is None):
        raise ValueError("specificare ESATTAMENTE uno tra offset_ticks e offset_pct")
    direction = -1 if side == "back" else +1  # back → più basso, lay → più alto
    if offset_ticks is not None:
        if int(offset_ticks) <= 0:
            raise ValueError("offset_ticks deve essere > 0")
        return move_ticks(entry_price, direction * int(offset_ticks))
    return pct_price(entry_price, float(offset_pct), direction)


def offset_order(
    entry_side: str,
    entry_price: float,
    entry_size: float,
    *,
    offset_ticks: Optional[int] = None,
    offset_pct: Optional[float] = None,
    greening: bool = False,
    matched_if_win: Optional[float] = None,
    matched_if_lose: Optional[float] = None,
) -> RiskOrder:
    """Ordine OPPOSTO di chiusura (offset/take-profit) al prezzo target.

    NON greening: size = ``entry_size`` (chiude lo stesso stake tradato → profitto fisso in
    tick sulla selezione). Greening: size che PAREGGIA gli esiti al prezzo target. In greening,
    se ``matched_if_win/lose`` sono forniti si usano quelli (robusto a fill parziali); altrimenti
    si derivano dall'ingresso pieno (W=size*(price−1), L=−size per un back; simmetrico per lay).
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        return _norm(None, None, None, f"entry_side non valido: {entry_side!r}")
    if entry_size is None or entry_size <= 0:
        return _norm(None, None, None, "entry_size non valido")
    close_side = _opp_side(side)
    target = offset_target_price(side, entry_price, offset_ticks=offset_ticks, offset_pct=offset_pct)

    if not greening:
        return _norm(
            close_side, target, entry_size,
            f"offset {close_side} {entry_size:.2f}@{target} (chiude {entry_size:.2f})",
        )

    # greening: size che pareggia W/L al prezzo target.
    if matched_if_win is None or matched_if_lose is None:
        pe = snap(entry_price)
        if side == "back":
            w, l = entry_size * (pe - 1.0), -float(entry_size)
        else:  # lay
            w, l = -entry_size * (pe - 1.0), float(entry_size)
    else:
        w, l = float(matched_if_win), float(matched_if_lose)
    hedge_side, size = hedge_size_at(w, l, target)
    if hedge_side is None:
        return _norm(None, None, None, "offset greening: posizione già piatta")
    # coerenza: l'hedge che pareggia DEVE essere sul lato opposto all'ingresso.
    if hedge_side != close_side:  # pragma: no cover - guardia di sanità
        return _norm(None, None, None, f"offset greening: lato incoerente {hedge_side}!={close_side}")
    return _norm(close_side, target, size, f"offset+greening {close_side} {size:.2f}@{target}")


# ---------------------------------------------------------------------------
# STOP-LOSS (trigger vs place-at; chiusura al best opposto)
# ---------------------------------------------------------------------------
def stop_trigger_price(
    entry_side: str,
    entry_price: float,
    *,
    trigger_ticks: Optional[int] = None,
    trigger_pct: Optional[float] = None,
) -> float:
    """Prezzo-soglia AVVERSO oltre cui lo stop scatta.

    back-first → avverso è quota PIÙ ALTA: +trigger. lay-first → più BASSA: −trigger.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    if (trigger_ticks is None) == (trigger_pct is None):
        raise ValueError("specificare ESATTAMENTE uno tra trigger_ticks e trigger_pct")
    direction = +1 if side == "back" else -1  # back → avverso in alto, lay → in basso
    if trigger_ticks is not None:
        if int(trigger_ticks) <= 0:
            raise ValueError("trigger_ticks deve essere > 0")
        return move_ticks(entry_price, direction * int(trigger_ticks))
    return pct_price(entry_price, float(trigger_pct), direction)


def stop_should_fire(
    entry_side: str,
    trigger_price: float,
    current_price: float,
) -> bool:
    """True se il prezzo corrente ha raggiunto/superato la soglia AVVERSA.

    back-first: scatta se current >= trigger (quota salita = perdita).
    lay-first : scatta se current <= trigger (quota scesa  = perdita).
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    if current_price is None or not math.isfinite(current_price):
        return False
    cur = snap(current_price)
    trg = snap(trigger_price)
    if side == "back":
        return cur >= trg - _EPS
    return cur <= trg + _EPS


def stop_close_order(
    entry_side: str,
    entry_size: float,
    *,
    best_back_price: Optional[float],
    best_lay_price: Optional[float],
    greening: bool = True,
    matched_if_win: Optional[float] = None,
    matched_if_lose: Optional[float] = None,
) -> RiskOrder:
    """Ordine di CHIUSURA dello stop, al BEST opposto (attraversa lo spread → match garantito).

    back-first → LAY al best_lay; lay-first → BACK al best_back. Di default ``greening=True``
    (flatten: si pareggia la posizione sulle esposizioni correnti); se ``greening=False`` si
    chiude lo stesso stake d'ingresso. Il prezzo NON è "trigger+place_at ticks": il ``place_at``
    dei tool serve solo a garantire il match — qui si va direttamente al best abbinabile.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        return _norm(None, None, None, f"entry_side non valido: {entry_side!r}")
    close_side = _opp_side(side)
    close_price = best_lay_price if close_side == "lay" else best_back_price
    if close_price is None or not math.isfinite(close_price) or close_price <= 1.0:
        return _norm(None, None, None, f"stop: best {close_side} non disponibile")

    if greening and matched_if_win is not None and matched_if_lose is not None:
        hedge_side, size = hedge_size_at(float(matched_if_win), float(matched_if_lose), snap(close_price))
        if hedge_side is None:
            return _norm(None, None, None, "stop: posizione già piatta")
        if hedge_side != close_side:  # pragma: no cover - guardia di sanità
            return _norm(None, None, None, f"stop: lato incoerente {hedge_side}!={close_side}")
        return _norm(close_side, close_price, size, f"stop-loss flatten {close_side} {size:.2f}@{close_price}")

    if entry_size is None or entry_size <= 0:
        return _norm(None, None, None, "stop: entry_size non valido")
    return _norm(close_side, close_price, entry_size, f"stop-loss {close_side} {entry_size:.2f}@{close_price}")


# ---------------------------------------------------------------------------
# TRAILING STOP (cricchetto verso la posizione)
# ---------------------------------------------------------------------------
def update_trailing_extreme(entry_side: str, prev_extreme: Optional[float], current_price: float) -> float:
    """Aggiorna l'estremo FAVOREVOLE osservato (cricchetto).

    back-first: estremo = prezzo PIÙ BASSO visto (min). lay-first: PIÙ ALTO (max).
    ``prev_extreme`` None → inizializza al prezzo corrente.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    cur = snap(current_price)
    if prev_extreme is None:
        return cur
    prev = snap(prev_extreme)
    return min(prev, cur) if side == "back" else max(prev, cur)


def trailing_stop_price(
    entry_side: str,
    extreme_price: float,
    *,
    trail_ticks: Optional[int] = None,
    trail_pct: Optional[float] = None,
) -> float:
    """Prezzo dello stop trailing dato l'estremo favorevole.

    back-first: lo stop sta ``trail`` tick SOPRA l'estremo minimo. lay-first: SOTTO l'estremo massimo.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    if (trail_ticks is None) == (trail_pct is None):
        raise ValueError("specificare ESATTAMENTE uno tra trail_ticks e trail_pct")
    direction = +1 if side == "back" else -1  # back → stop sopra l'estremo, lay → sotto
    if trail_ticks is not None:
        if int(trail_ticks) <= 0:
            raise ValueError("trail_ticks deve essere > 0")
        return move_ticks(extreme_price, direction * int(trail_ticks))
    return pct_price(extreme_price, float(trail_pct), direction)


def trailing_should_fire(entry_side: str, stop_price: float, current_price: float) -> bool:
    """True se il prezzo corrente ha toccato lo stop trailing (stessa direzione dello stop-loss)."""
    return stop_should_fire(entry_side, stop_price, current_price)


# ---------------------------------------------------------------------------
# TAKE-PROFIT / STOP su P&L (mark-to-market)
# ---------------------------------------------------------------------------
def pnl_threshold_fires(
    mtm: Optional[float],
    *,
    stop_amount: Optional[float] = None,
    target_amount: Optional[float] = None,
) -> Optional[str]:
    """Confronta il P&L mark-to-market con soglie di stop/target. Ritorna 'stop' | 'target' | None.

    ``stop_amount`` è una PERDITA (valore positivo = si chiude se mtm <= −stop_amount).
    ``target_amount`` è un PROFITTO (si chiude se mtm >= target_amount). None = soglia inattiva.
    Se scattano entrambe nello stesso istante, prevale lo STOP (protezione capitale prima).
    """
    if mtm is None:
        return None
    if stop_amount is not None and stop_amount > 0 and mtm <= -abs(float(stop_amount)) + _EPS:
        return "stop"
    if target_amount is not None and target_amount > 0 and mtm >= abs(float(target_amount)) - _EPS:
        return "target"
    return None


def favorable_reached(entry_side: str, target_price: float, current_price: float) -> bool:
    """True se il prezzo corrente ha raggiunto il target FAVOREVOLE (take-profit di prezzo).

    back-first: favorevole è quota PIÙ BASSA → raggiunto se current <= target.
    lay-first : favorevole è quota PIÙ ALTA → raggiunto se current >= target.
    """
    side = (entry_side or "").lower()
    if side not in _VALID_SIDES:
        raise ValueError(f"entry_side non valido: {entry_side!r}")
    if current_price is None or not math.isfinite(current_price):
        return False
    cur = snap(current_price)
    tgt = snap(target_price)
    return cur <= tgt + _EPS if side == "back" else cur >= tgt - _EPS


# ---------------------------------------------------------------------------
# Valutazione di UNA regola armata (pura): decide se SCATTARE, per il worker.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleDecision:
    """Esito della valutazione di una regola monitorata (stop_loss/take_profit/trailing_stop)."""

    fire: bool
    reason: str
    trail_extreme: Optional[float] = None   # nuovo estremo da persistere (solo trailing)


def _num(params: dict, key: str) -> Optional[float]:
    v = params.get(key) if isinstance(params, dict) else None
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _int_param(params: dict, key: str) -> Optional[int]:
    f = _num(params, key)
    return int(f) if f is not None else None


def evaluate_rule(
    *,
    rule_type: str,
    entry_side: str,
    entry_price: Optional[float],
    params: dict,
    current_price: Optional[float],
    matched_if_win: float,
    matched_if_lose: float,
    best_back_price: Optional[float],
    best_lay_price: Optional[float],
    trail_extreme: Optional[float],
) -> RuleDecision:
    """Decide se una regola MONITORATA deve scattare, dato lo stato di mercato corrente.

    Supporta stop_loss / take_profit / trailing_stop. Ogni tipo può innescarsi per PREZZO
    (tick/%) e/o per P&L mark-to-market (stop_amount/target_amount). Il trailing aggiorna e
    ritorna l'estremo favorevole da persistere. (L'``offset`` NON passa di qui: è un ordine
    resting piazzato una volta sola dal worker.)
    """
    params = params or {}
    rt = (rule_type or "").lower()
    mtm = mark_to_market(matched_if_win, matched_if_lose, best_back_price, best_lay_price)

    # --- trailing: aggiorna sempre l'estremo, poi valuta lo stop mobile ---------------
    if rt == "trailing_stop":
        new_ext = trail_extreme
        if current_price is not None and math.isfinite(current_price):
            new_ext = update_trailing_extreme(entry_side, trail_extreme, current_price)
        trail_ticks = _int_param(params, "trail_ticks")
        trail_pct = _num(params, "trail_pct")
        if new_ext is not None and (trail_ticks is not None or trail_pct is not None) \
           and current_price is not None:
            stop_px = trailing_stop_price(
                entry_side, new_ext, trail_ticks=trail_ticks, trail_pct=trail_pct
            )
            if trailing_should_fire(entry_side, stop_px, current_price):
                return RuleDecision(True, f"trailing stop @ {stop_px} (estremo {new_ext})", new_ext)
        # anche il trailing rispetta un eventuale stop su P&L
        hit = pnl_threshold_fires(mtm, stop_amount=_num(params, "stop_amount"))
        if hit == "stop":
            return RuleDecision(True, f"trailing stop su P&L {mtm}", new_ext)
        return RuleDecision(False, "trailing: nessuno scatto", new_ext)

    # --- stop_loss ---------------------------------------------------------------------
    if rt == "stop_loss":
        trg_ticks = _int_param(params, "trigger_ticks")
        trg_pct = _num(params, "trigger_pct")
        if entry_price is not None and (trg_ticks is not None or trg_pct is not None) \
           and current_price is not None:
            trg_px = stop_trigger_price(entry_side, entry_price, trigger_ticks=trg_ticks, trigger_pct=trg_pct)
            if stop_should_fire(entry_side, trg_px, current_price):
                return RuleDecision(True, f"stop-loss prezzo @ {trg_px}")
        if pnl_threshold_fires(mtm, stop_amount=_num(params, "stop_amount")) == "stop":
            return RuleDecision(True, f"stop-loss P&L {mtm}")
        return RuleDecision(False, "stop-loss: nessuno scatto")

    # --- take_profit -------------------------------------------------------------------
    if rt == "take_profit":
        off_ticks = _int_param(params, "offset_ticks")
        off_pct = _num(params, "offset_pct")
        if entry_price is not None and (off_ticks is not None or off_pct is not None) \
           and current_price is not None:
            tgt_px = offset_target_price(entry_side, entry_price, offset_ticks=off_ticks, offset_pct=off_pct)
            if favorable_reached(entry_side, tgt_px, current_price):
                return RuleDecision(True, f"take-profit prezzo @ {tgt_px}")
        if pnl_threshold_fires(mtm, target_amount=_num(params, "target_amount")) == "target":
            return RuleDecision(True, f"take-profit P&L {mtm}")
        return RuleDecision(False, "take-profit: nessuno scatto")

    return RuleDecision(False, f"rule_type non monitorato: {rule_type!r}")
