"""
pricing.py — da una probabilita' vera a fair odds e soglie d'ingresso (back/lay), con commissione.

BACK: EV>0 se quota_live >= 1 + (1-p)/(p(1-c))  -> min_back
LAY : EV>0 se quota_lay <= 1 + (1-p)(1-c)/p      -> max_lay  (rischio sulla liability)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketPrice:
    market: str
    prob: float
    fair_odds: float
    min_back: float      # quota minima per profitto backando
    max_lay: float       # quota massima per profitto layando


def price(market: str, prob: float, commission: float = 0.05) -> MarketPrice:
    p = min(max(prob, 1e-9), 1 - 1e-9)
    fair = 1.0 / p
    min_back = 1.0 + (1.0 - p) / (p * (1.0 - commission))
    max_lay = 1.0 + (1.0 - p) * (1.0 - commission) / p
    return MarketPrice(market=market, prob=prob, fair_odds=round(fair, 3),
                       min_back=round(min_back, 3), max_lay=round(max_lay, 3))


def value_flags(mp: MarketPrice, live_back: Optional[float] = None,
                live_lay: Optional[float] = None) -> dict:
    """Dato il prezzo equo e le quote live, dice se c'e' valore. None = quota non fornita."""
    out = {"value_back": None, "value_lay": None}
    if live_back is not None:
        out["value_back"] = live_back >= mp.min_back
    if live_lay is not None:
        out["value_lay"] = live_lay <= mp.max_lay
    return out
