"""dutching.py — matematica PURA del dutching/bookmaking (Fase 5).

Per chi: il worker (azione ``dutch``) e la UI usano queste funzioni per ripartire uno stake
totale su N selezioni in modo che il PROFITTO sia UGUALE qualunque selezione vinca (back
dutching) o per fare il "bookmaker" layando N selezioni a liability/profitto uguale.

Logica pura, nessun I/O: testabile a unità. Standard di settore (Bet Angel / Fairbot):
  * BACK dutching, profitto uguale:  s_i = T · (1/p_i) / Σ(1/p_j)
        profitto (qualunque vinca) = T · (1 − B)/B   con B = Σ(1/p_i) = "book" (in frazione)
        → profitto > 0  ⟺  book B < 1 (cioè < 100%).
  * LAY dutching (bookmaking):        l_i = T · (1/p_i) / Σ(1/p_j)   (stessa forma)
        qui T è il totale degli stake LAY incassati; si è in profitto quando B > 1.
  * Target profit: si risolve il totale T per centrare un profitto voluto.
  * Variable dutching: profitto/target PER selezione (pesi), non uguale.

Prezzi sempre snappati al tick valido Betfair (get_nearest_price) prima del calcolo, così i
numeri combaciano con ciò che verrà effettivamente piazzato.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from flumine.utils import get_nearest_price

_EPS = 1e-9
# size minima operabile: sotto 1 cent non ha senso (arrotondamento Betfair al centesimo).
MIN_SIZE = 0.01


@dataclass(frozen=True)
class DutchLeg:
    """Una gamba del dutching: selezione, prezzo (al tick) e stake calcolato."""

    selection_id: int
    price: float
    size: float           # stake back (o stake lay per il bookmaking), 2 decimali
    profit_if_wins: float  # P&L se QUESTA selezione è quella che vince (back) / l'unica che vince (lay)


@dataclass(frozen=True)
class DutchPlan:
    legs: Tuple[DutchLeg, ...]
    side: str              # 'back' | 'lay'
    total_stake: float     # somma degli stake
    book_pct: float        # Σ(1/p)·100
    worst_profit: float     # profitto minimo tra gli esiti (garanzia)
    best_profit: float
    note: str

    @property
    def actionable(self) -> bool:
        return len(self.legs) > 0 and self.total_stake > 0.0


def _clean_selections(selections: Sequence[Tuple[int, float]]) -> List[Tuple[int, float]]:
    """Snap dei prezzi + validazione. Scarta prezzi non validi (<=1.0 o non finiti)."""
    out: List[Tuple[int, float]] = []
    for sel_id, price in selections:
        if price is None or not math.isfinite(float(price)) or float(price) <= 1.0:
            continue
        out.append((int(sel_id), get_nearest_price(float(price))))
    return out


def book_percentage(selections: Sequence[Tuple[int, float]]) -> float:
    """Book Σ(1/p)·100 sulle selezioni valide (prezzi snappati). 0.0 se nessuna valida."""
    cleaned = _clean_selections(selections)
    if not cleaned:
        return 0.0
    return round(sum(1.0 / p for _, p in cleaned) * 100.0, 2)


def _back_profit_if_wins(legs_prices: List[Tuple[int, float, float]], idx: int, total: float) -> float:
    """P&L se vince la selezione ``idx`` (back dutching): s_i·p_i − T (il resto perde lo stake)."""
    _, p_i, s_i = legs_prices[idx]
    return round(s_i * p_i - total, 2)


def dutch_back(
    selections: Sequence[Tuple[int, float]],
    total_stake: float,
) -> DutchPlan:
    """BACK dutching a PROFITTO UGUALE con stake totale ``total_stake``.

    s_i = T·(1/p_i)/Σ(1/p_j). Ogni gamba, se vince, rende s_i·p_i − T (uguale per tutte a meno
    dell'arrotondamento a 2 decimali). Se il book ≥ 100% il profitto è ≤ 0 (lo si segnala ma il
    piano resta calcolato: sta al chiamante/UI decidere). Selezioni con prezzo non valido scartate.
    """
    if total_stake is None or total_stake <= 0:
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "total_stake non valido")
    cleaned = _clean_selections(selections)
    if not cleaned:
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "nessuna selezione valida")
    inv_sum = sum(1.0 / p for _, p in cleaned)
    if inv_sum <= 0:  # pragma: no cover - prezzi>1 garantiscono inv_sum>0
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "book nullo")

    legs_prices: List[Tuple[int, float, float]] = []
    for sel_id, p in cleaned:
        s = round(total_stake * (1.0 / p) / inv_sum, 2)
        legs_prices.append((sel_id, p, s))

    total = round(sum(s for _, _, s in legs_prices), 2)
    legs: List[DutchLeg] = []
    for i, (sel_id, p, s) in enumerate(legs_prices):
        profit = _back_profit_if_wins(legs_prices, i, total)
        legs.append(DutchLeg(selection_id=sel_id, price=p, size=s, profit_if_wins=profit))
    profits = [leg.profit_if_wins for leg in legs]
    book = round(inv_sum * 100.0, 2)
    return DutchPlan(
        legs=tuple(legs), side="back", total_stake=total, book_pct=book,
        worst_profit=round(min(profits), 2), best_profit=round(max(profits), 2),
        note=f"back dutching {len(legs)} selezioni, book {book:.2f}%",
    )


def dutch_back_for_target(
    selections: Sequence[Tuple[int, float]],
    target_profit: float,
) -> DutchPlan:
    """BACK dutching che centra un PROFITTO TOTALE ``target_profit`` (qualunque selezione vinca).

    profitto = T·(1−B)/B ⟹ T = target·B/(1−B), con B = Σ(1/p) in frazione (book). Richiede
    book < 100% (altrimenti il dutching non può dare profitto: piano vuoto con motivo).
    """
    cleaned = _clean_selections(selections)
    if not cleaned:
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "nessuna selezione valida")
    b = sum(1.0 / p for _, p in cleaned)  # book in frazione
    if b >= 1.0 - _EPS:
        return DutchPlan(
            legs=(), side="back", total_stake=0.0, book_pct=round(b * 100.0, 2),
            worst_profit=0.0, best_profit=0.0,
            note=f"book {b*100:.2f}% ≥ 100%: nessun profitto possibile col dutching",
        )
    if target_profit is None or target_profit <= 0:
        return DutchPlan(
            legs=(), side="back", total_stake=0.0, book_pct=round(b * 100.0, 2),
            worst_profit=0.0, best_profit=0.0, note="target_profit non valido",
        )
    total = target_profit * b / (1.0 - b)
    return dutch_back(cleaned, round(total, 2))


def dutch_lay(
    selections: Sequence[Tuple[int, float]],
    total_lay_stake: float,
) -> DutchPlan:
    """LAY dutching / bookmaking a liability ripartita: l_i = T·(1/p_i)/Σ(1/p_j).

    T = somma degli stake LAY (backer stake incassato). Se vince la selezione k si paga la sua
    liability l_k·(p_k−1) e si tengono gli stake delle altre: P_k = T − l_k·p_k (uguale per tutte
    a meno dell'arrotondamento). In profitto quando il book Σ(1/p) > 100%.
    """
    if total_lay_stake is None or total_lay_stake <= 0:
        return DutchPlan((), "lay", 0.0, 0.0, 0.0, 0.0, "total_lay_stake non valido")
    cleaned = _clean_selections(selections)
    if not cleaned:
        return DutchPlan((), "lay", 0.0, 0.0, 0.0, 0.0, "nessuna selezione valida")
    inv_sum = sum(1.0 / p for _, p in cleaned)

    legs_prices: List[Tuple[int, float, float]] = []
    for sel_id, p in cleaned:
        l = round(total_lay_stake * (1.0 / p) / inv_sum, 2)
        legs_prices.append((sel_id, p, l))
    total = round(sum(l for _, _, l in legs_prices), 2)

    legs: List[DutchLeg] = []
    for sel_id, p, l in legs_prices:
        # profitto se vince QUESTA selezione (l'unica che vince, le altre lose → si tiene il loro stake)
        profit = round(total - l * p, 2)
        legs.append(DutchLeg(selection_id=sel_id, price=p, size=l, profit_if_wins=profit))
    profits = [leg.profit_if_wins for leg in legs]
    book = round(inv_sum * 100.0, 2)
    return DutchPlan(
        legs=tuple(legs), side="lay", total_stake=total, book_pct=book,
        worst_profit=round(min(profits), 2), best_profit=round(max(profits), 2),
        note=f"lay dutching {len(legs)} selezioni, book {book:.2f}%",
    )


def dutch_variable(
    selections: Sequence[Tuple[int, float, float]],
    total_stake: float,
) -> DutchPlan:
    """BACK dutching VARIABILE: ogni selezione ha un PESO di profitto relativo ``w_i`` (>0).

    Generalizza il profitto-uguale (tutti i pesi = 1). Si impone profit_i ∝ w_i:
        s_i·p_i − T = k·w_i,   Σ s_i = T.
    Da cui s_i = (T + k·w_i)/p_i e, sommando, k = T·(1 − Σ(1/p))/Σ(w/p). ``selections`` è una
    lista di (selection_id, price, weight). Utile per "più profitto sul favorito".
    """
    if total_stake is None or total_stake <= 0:
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "total_stake non valido")
    cleaned: List[Tuple[int, float, float]] = []
    for sel_id, price, weight in selections:
        if price is None or not math.isfinite(float(price)) or float(price) <= 1.0:
            continue
        w = float(weight)
        if not math.isfinite(w) or w <= 0:
            continue
        cleaned.append((int(sel_id), get_nearest_price(float(price)), w))
    if not cleaned:
        return DutchPlan((), "back", 0.0, 0.0, 0.0, 0.0, "nessuna selezione valida")

    inv_sum = sum(1.0 / p for _, p, _ in cleaned)
    wp_sum = sum(w / p for _, p, w in cleaned)
    if wp_sum <= 0:  # pragma: no cover
        return dutch_back([(s, p) for s, p, _ in cleaned], total_stake)
    k = total_stake * (1.0 - inv_sum) / wp_sum

    legs_prices: List[Tuple[int, float, float]] = []
    for sel_id, p, w in cleaned:
        s = round((total_stake + k * w) / p, 2)
        # Stake NEGATIVO su una gamba = pesi IRREALIZZABILI con questo book (succede con
        # book > 100% e peso forte su una quota alta): clamparlo a 0 romperebbe Σs = T
        # (si spenderebbe PIÙ del total_stake richiesto) e la proporzionalità dei profitti
        # ai pesi. Rifiuto onesto: piano NON azionabile con motivo, nessun ordine.
        if s < 0.0:
            book = round(inv_sum * 100.0, 2)
            return DutchPlan(
                legs=(), side="back", total_stake=0.0, book_pct=book,
                worst_profit=0.0, best_profit=0.0,
                note=(f"pesi irrealizzabili con book {book:.2f}%: stake negativo sulla "
                      f"selezione {sel_id} — ridurre i pesi o usare profitto uguale"),
            )
        legs_prices.append((sel_id, p, s))
    total = round(sum(s for _, _, s in legs_prices), 2)

    legs: List[DutchLeg] = []
    for i, (sel_id, p, s) in enumerate(legs_prices):
        profit = round(s * p - total, 2)
        legs.append(DutchLeg(selection_id=sel_id, price=p, size=s, profit_if_wins=profit))
    profits = [leg.profit_if_wins for leg in legs]
    book = round(inv_sum * 100.0, 2)
    return DutchPlan(
        legs=tuple(legs), side="back", total_stake=total, book_pct=book,
        worst_profit=round(min(profits), 2), best_profit=round(max(profits), 2),
        note=f"back dutching variabile {len(legs)} selezioni, book {book:.2f}%",
    )
