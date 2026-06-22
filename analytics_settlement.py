"""analytics_settlement.py — logica PURA di settlement + hit per la tabella
analytics_signals. Isolata e testabile (vedi test_analytics_settlement.py).

⚠️ SOLDI IN GIOCO: la correttezza qui determina hit/miss → certificata su casi reali.
Coerente con il settlement di market_frequency_rpc.sql:
  - punteggio 90' (FT): fulltime_* PRIMARIO; fallback goals_* SOLO per status 'FT'.
    AET/PEN senza fulltime_* → 90' SCONOSCIUTO → None (riga non settlabile).
  - punteggio 1°T (HT): halftime_*; se mancante → None (mercati HT non settlabili).
"""
from __future__ import annotations

from typing import Optional, Tuple

FINISHED = ("FT", "AET", "PEN")  # whitelist insieme settlato

# Selezioni "valore numerico al rialzo" per i mercati binari Over/BTTS.
Score = Tuple[int, int]


def ft_score_90(match: dict) -> Optional[Score]:
    """Punteggio a 90' (casa, trasferta) per il settlement, o None se sconosciuto.

    fulltime_* è la fonte primaria (= 90' anche per AET/PEN). Se mancante, si
    accetta goals_* SOLO per status 'FT' (dove goals=90', 0 divergenze verificate).
    Per AET/PEN senza fulltime il 90' è ignoto → None.
    """
    status = match.get("status_short")
    if status not in FINISHED:
        return None
    fh, fa = match.get("fulltime_home"), match.get("fulltime_away")
    if fh is not None and fa is not None:
        return int(fh), int(fa)
    if status == "FT":
        gh, ga = match.get("goals_home"), match.get("goals_away")
        if gh is not None and ga is not None:
            return int(gh), int(ga)
    return None  # AET/PEN senza fulltime → 90' sconosciuto


def ht_score(match: dict) -> Optional[Score]:
    """Punteggio 1° tempo (casa, trasferta), o None se mancante."""
    hh, ha = match.get("halftime_home"), match.get("halftime_away")
    if hh is None or ha is None:
        return None
    return int(hh), int(ha)


def _outcome_1x2(h: int, a: int) -> str:
    return "H" if h > a else ("A" if a > h else "D")


def hit(market: str, selection: str, ft: Optional[Score], ht: Optional[Score]) -> Optional[bool]:
    """Direzione del motore azzeccata? True/False, oppure None se non settlabile
    (es. mercato FT senza punteggio 90', o mercato HT senza punteggio 1°T).

    `selection` è il valore canonico salvato in tabella:
      1x2/ht_1x2 → 'H'|'D'|'A' ; over_* → 'Over'|'Under' ; btts → 'Yes'|'No' ;
      first_half_over_0_5 → 'Over'|'Under'.
    """
    # --- mercati FULL-TIME (90') ---
    if market == "1x2":
        if ft is None:
            return None
        return _outcome_1x2(*ft) == selection
    if market in ("over_1_5", "over_2_5", "over_3_5"):
        if ft is None:
            return None
        line = {"over_1_5": 1.5, "over_2_5": 2.5, "over_3_5": 3.5}[market]
        over = (ft[0] + ft[1]) > line
        return over if selection == "Over" else (not over)
    if market == "btts":
        if ft is None:
            return None
        both = ft[0] >= 1 and ft[1] >= 1
        return both if selection == "Yes" else (not both)
    # --- mercati HALF-TIME (1°T) ---
    if market == "ht_1x2":
        if ht is None:
            return None
        return _outcome_1x2(*ht) == selection
    if market == "first_half_over_0_5":
        if ht is None:
            return None
        over = (ht[0] + ht[1]) > 0.5
        return over if selection == "Over" else (not over)
    # mercato non gestito → non settlabile (mai indovinare)
    return None
