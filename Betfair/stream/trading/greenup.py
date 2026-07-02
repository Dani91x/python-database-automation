"""greenup.py — calcolo green-up / cash-out (hedge) per il runner live (Fase 2).

Per chi: il ``live_order_worker`` (azione ``greenup``) chiama ``compute_greenup`` per
trasformare le ESPOSIZIONI MATCHED correnti di una selezione — prese SEMPRE da flumine
(``blotter.get_exposures`` → ``matched_profit_if_win`` / ``matched_profit_if_lose``,
MAI ricalcolate a mano) — nell'UNICO ordine opposto che pareggia profit-se-vince/perde
(green-up TOTALE) o ne chiude una frazione (cash-out PARZIALE con slider %).

Logica pura, nessun I/O: testabile a unità. È il chiamante (worker) a leggere le
esposizioni fresche e il best price corrente dal book; qui si fa solo l'aritmetica.

Matematica dell'hedge (standard di settore — Bet Angel / Geeks Toy / Betfair Cash Out):
    diff = W - L                       con W = profit se la selezione VINCE
                                            L = profit se la selezione PERDE
    diff > 0  → si LAYa  @ p_lay  (best disponibile al LAY),  size = f * diff / p
    diff < 0  → si BACKa @ p_back (best disponibile al BACK), size = f * (-diff) / p
    |diff| ~ 0 → niente da fare (posizione già piatta)

Per il green-up TOTALE (f = 1) il nuovo profit-se-vince e profit-se-perde coincidono
(profitto BLOCCATO identico su ogni esito):
    locked = L + (W - L) / p_lay        (ramo lay)
           = W + (L - W) / p_back       (ramo back)
È la STESSA formula del display ``lockedPnlAt`` del ladder frontend (lose + (win-lose)/p);
i test verificano l'azzeramento di W'−L' entro 1 cent (residuo solo da arrotondamento size).

Perché il prezzo del lato OPPOSTO best: per chiudere SUBITO si attraversa lo spread sul
miglior prezzo immediatamente abbinabile — best available-to-lay quando si laya, best
available-to-back quando si backa (i prezzi "taker" che matchano contro la liquidità in book).

Sotto-minimo: il green-up RIDUCE la liability → ``reduces_liability=True`` lato build_order
consente size sotto i minimi .it (€2 back / €0,50 lay), soggetta alla guardia Betfair
INVALID_PROFIT_RATIO. L'hedge è SELF-BOUNDED: la sua liability è < |W−L| (≤ esposizione
già aperta), quindi non può mai aprire rischio nuovo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from flumine.utils import get_nearest_price, price_ticks_away

# Soglia "posizione già piatta": sotto 1 cent di sbilancio non si piazza nulla (il più
# piccolo movimento di denaro su Betfair è il centesimo → niente ordini-fantasma a €0,00).
FLAT_EPS = 0.01


def _place_through(side: str, best_price: float, place_at_ticks: int) -> float:
    """Sposta il prezzo di ``place_at_ticks`` PIÙ A FONDO nel book per un fill più sicuro
    (stop a 2 parametri, stile Bet Angel: chiudi al best ma "place at" N tick oltre).

    LAY  → prezzo PIÙ ALTO (offri odds migliori ai backer → match più probabile).
    BACK → prezzo PIÙ BASSO (offri odds migliori ai layer → match più probabile).
    Peggiora leggermente il P&L bloccato ma garantisce l'uscita in un mercato veloce.
    place_at_ticks<=0 → nessuno spostamento (chiude esattamente al best).
    """
    if not place_at_ticks or place_at_ticks <= 0:
        return best_price
    snapped = get_nearest_price(float(best_price))
    n = int(place_at_ticks) if side == "lay" else -int(place_at_ticks)
    moved = price_ticks_away(snapped, n)
    return get_nearest_price(float(moved))


@dataclass(frozen=True)
class GreenupPlan:
    """Esito del calcolo. ``side``/``price``/``size`` valorizzati solo se c'è da operare."""

    side: Optional[str]              # 'back' | 'lay' | None (niente da fare)
    price: Optional[float]           # prezzo di esecuzione (best opposto), None se nessun ordine
    size: Optional[float]            # stake dell'ordine (>0), None se nessun ordine
    expected_if_win: float           # profit-se-vince DOPO l'hedge (preview)
    expected_if_lose: float          # profit-se-perde DOPO l'hedge (preview)
    note: str                        # tracciabilità / motivo del no-op

    @property
    def actionable(self) -> bool:
        return (
            self.side is not None
            and self.price is not None
            and self.size is not None
            and self.size > 0
        )


def _clamp_fraction(fraction: Optional[float]) -> float:
    """Frazione di chiusura in [0, 1]. None/NaN → 1.0 (green-up totale)."""
    if fraction is None or not math.isfinite(fraction):
        return 1.0
    return max(0.0, min(1.0, float(fraction)))


def compute_greenup(
    *,
    matched_if_win: float,
    matched_if_lose: float,
    best_back_price: Optional[float],
    best_lay_price: Optional[float],
    fraction: float = 1.0,
    place_at_ticks: int = 0,
) -> GreenupPlan:
    """Calcola l'UNICO ordine di green-up/cash-out per una selezione.

    Argomenti:
      matched_if_win / matched_if_lose: esposizioni MATCHED da flumine (W, L).
      best_back_price: miglior prezzo disponibile al BACK (per l'hedge BACK quando L > W).
      best_lay_price:  miglior prezzo disponibile al LAY  (per l'hedge LAY  quando W > L).
      fraction: quota di chiusura ∈ (0,1] (1 = totale; 0.5 = metà). Clampata in [0,1].

    Ritorna un ``GreenupPlan``: se ``actionable`` è False non c'è nulla da piazzare
    (posizione piatta, frazione nulla, prezzo lato richiesto assente o size→0).
    """
    f = _clamp_fraction(fraction)
    w = float(matched_if_win)
    l = float(matched_if_lose)
    # Esposizioni non finite (NaN/inf): con NaN ogni confronto è False → si cadrebbe nel ramo
    # BACK con size=NaN, violando il contratto "side/price/size valorizzati solo se operabile".
    if not (math.isfinite(w) and math.isfinite(l)):
        return GreenupPlan(
            side=None, price=None, size=None, expected_if_win=0.0, expected_if_lose=0.0,
            note=f"esposizioni non finite (W={matched_if_win!r}, L={matched_if_lose!r}): nessun ordine",
        )
    diff = w - l

    if f <= 0.0 or abs(diff) < FLAT_EPS:
        return GreenupPlan(
            side=None, price=None, size=None,
            expected_if_win=round(w, 2), expected_if_lose=round(l, 2),
            note="posizione già piatta o frazione nulla: nessun ordine",
        )

    if diff > 0.0:
        # Profitto sbilanciato sul VINCE → LAYa per spostare denaro sul PERDE.
        p = best_lay_price
        if p is None or not math.isfinite(p) or p <= 1.0:
            return GreenupPlan(
                None, None, None, round(w, 2), round(l, 2),
                "prezzo LAY non disponibile per il green-up",
            )
        p = _place_through("lay", p, place_at_ticks)  # stop a 2 parametri: fill più sicuro
        size = round(f * diff / p, 2)
        if size <= 0.0:
            return GreenupPlan(
                None, None, None, round(w, 2), round(l, 2),
                "size LAY → 0 dopo arrotondamento: nessun ordine",
            )
        # esposizioni risultanti: LAY size@p → −size*(p−1) sul vince, +size sul perde.
        w2 = w - size * (p - 1.0)
        l2 = l + size
        return GreenupPlan(
            side="lay", price=p, size=size,
            expected_if_win=round(w2, 2), expected_if_lose=round(l2, 2),
            note=f"LAY {size:.2f}@{p} (f={f:.2f})",
        )

    # diff < 0 → profitto sbilanciato sul PERDE → BACKa per spostare denaro sul VINCE.
    p = best_back_price
    if p is None or not math.isfinite(p) or p <= 1.0:
        return GreenupPlan(
            None, None, None, round(w, 2), round(l, 2),
            "prezzo BACK non disponibile per il green-up",
        )
    p = _place_through("back", p, place_at_ticks)  # stop a 2 parametri: fill più sicuro
    size = round(f * (-diff) / p, 2)
    if size <= 0.0:
        return GreenupPlan(
            None, None, None, round(w, 2), round(l, 2),
            "size BACK → 0 dopo arrotondamento: nessun ordine",
        )
    # BACK size@p → +size*(p−1) sul vince, −size sul perde.
    w2 = w + size * (p - 1.0)
    l2 = l - size
    return GreenupPlan(
        side="back", price=p, size=size,
        expected_if_win=round(w2, 2), expected_if_lose=round(l2, 2),
        note=f"BACK {size:.2f}@{p} (f={f:.2f})",
    )
