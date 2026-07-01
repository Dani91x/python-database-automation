"""hedging.py — planner PURO di copertura/flatten multi-posizione (Fase 5).

Per chi: l'azione ``cashout_all`` (global cash-out, benchmark Betting Toolkit) e la UI usano
``plan_flatten`` per chiudere IN UN COLPO tutte le posizioni aperte — di un mercato o
dell'INTERO evento (più mercati) — riusando ESATTAMENTE la matematica di trading/greenup
(``compute_greenup``, che pareggia W e L al best opposto). Nessun ordine viene piazzato qui:
si producono i piani (uno per selezione con esposizione ≠ 0) che il worker accoderà.

⚠️ Copertura cross-market "correlata" (es. Over 2.5 vs Correct Score): NON è offerta come
netting automatico — nessun tool la fa in modo affidabile e mescolare esposizioni di mercati
diversi senza un modello di correlazione è pericoloso. Qui il "global cash-out" chiude ogni
mercato PER CONTO SUO (flatten indipendente), che è il comportamento corretto e sicuro.

Logica pura: testabile a unità. È il worker a leggere W/L e best price freschi da flumine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .greenup import GreenupPlan, compute_greenup


@dataclass(frozen=True)
class PositionInput:
    """Esposizione MATCHED di una selezione + best price opposti (dal book), da flumine."""

    market_id: str
    selection_id: int
    handicap: float
    matched_if_win: float
    matched_if_lose: float
    best_back_price: Optional[float]
    best_lay_price: Optional[float]


@dataclass(frozen=True)
class FlattenLeg:
    market_id: str
    selection_id: int
    handicap: float
    plan: GreenupPlan          # actionable=False se la selezione è già piatta / prezzo assente


@dataclass(frozen=True)
class FlattenPlan:
    legs: Tuple[FlattenLeg, ...]
    note: str

    @property
    def actionable_legs(self) -> Tuple[FlattenLeg, ...]:
        """Solo le gambe che generano davvero un ordine (esposizione ≠ 0 e prezzo disponibile)."""
        return tuple(leg for leg in self.legs if leg.plan.actionable)

    @property
    def actionable(self) -> bool:
        return len(self.actionable_legs) > 0


def plan_flatten(
    positions: Sequence[PositionInput],
    fraction: float = 1.0,
) -> FlattenPlan:
    """Piano di chiusura (green-up) per OGNI posizione fornita, alla frazione ``fraction``.

    Una gamba per posizione: usa ``compute_greenup`` (identica alla cash-out di una singola
    selezione) sulle esposizioni e sul best opposto. Le posizioni già piatte o senza prezzo
    utile restano con ``plan.actionable=False`` (nessun ordine). ``fraction`` in (0,1] per un
    cash-out globale PARZIALE (clampata dentro compute_greenup).
    """
    legs: List[FlattenLeg] = []
    for pos in positions:
        plan = compute_greenup(
            matched_if_win=pos.matched_if_win,
            matched_if_lose=pos.matched_if_lose,
            best_back_price=pos.best_back_price,
            best_lay_price=pos.best_lay_price,
            fraction=fraction,
        )
        legs.append(
            FlattenLeg(
                market_id=pos.market_id,
                selection_id=pos.selection_id,
                handicap=pos.handicap,
                plan=plan,
            )
        )
    n_act = sum(1 for leg in legs if leg.plan.actionable)
    return FlattenPlan(
        legs=tuple(legs),
        note=f"flatten {n_act}/{len(legs)} posizioni (frazione {max(0.0, min(1.0, fraction)):.2f})",
    )


def net_open_pnl(
    positions: Sequence[PositionInput],
) -> Tuple[float, float]:
    """(worst_case, best_case) del P&L complessivo se si greenasse ORA tutto.

    Somma, su tutte le posizioni, il P&L bloccato dal green-up al best opposto (expected_if_win
    == expected_if_lose per selezione, entro arrotondamento). Utile per il display "P&L globale"
    del pulsante cash-out-all prima del commit. Le posizioni non chiudibili contribuiscono col
    loro W/L attuale non coperto (worst = min(W,L)).
    """
    worst = 0.0
    best = 0.0
    for pos in positions:
        plan = compute_greenup(
            matched_if_win=pos.matched_if_win,
            matched_if_lose=pos.matched_if_lose,
            best_back_price=pos.best_back_price,
            best_lay_price=pos.best_lay_price,
            fraction=1.0,
        )
        if plan.actionable:
            worst += min(plan.expected_if_win, plan.expected_if_lose)
            best += max(plan.expected_if_win, plan.expected_if_lose)
        else:
            # non chiudibile: resta esposto → worst = peggior esito, best = migliore
            worst += min(pos.matched_if_win, pos.matched_if_lose)
            best += max(pos.matched_if_win, pos.matched_if_lose)
    return round(worst, 2), round(best, 2)
