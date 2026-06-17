"""
devig.py — rimozione del margine del banco (overround) dalle quote.

La prob implicita grezza 1/quota somma a >1 (il margine). Le funzioni qui normalizzano
per ottenere prob "vere" con cui calibrare il modello (es. lambda da quote de-viggate).
Metodo di default: proporzionale (multiplicative). Disponibile anche la coppia 2-vie.
"""
from __future__ import annotations
from typing import Dict


def devig_multiplicative(odds: Dict[str, float]) -> Dict[str, float]:
    """Normalizza un mercato completo (es. {'H':..,'D':..,'A':..}) a prob che sommano a 1.
    Solleva se una quota e' <= 1.0 (input invalido) invece di scartarla in silenzio."""
    if any((not o or o <= 1.0) for o in odds.values()):
        raise ValueError(f"Tutte le quote devono essere > 1.0, ricevuto: {odds}")
    raw = {k: 1.0 / o for k, o in odds.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


def devig_pair(o: float, o_opp: float) -> float:
    """Prob de-viggata del primo esito data la sua quota e quella dell'esito opposto."""
    if not o or o <= 1.0:
        return 0.0
    if not o_opp or o_opp <= 1.0:
        return 1.0 / o
    imp, imp_o = 1.0 / o, 1.0 / o_opp
    return imp / (imp + imp_o)
