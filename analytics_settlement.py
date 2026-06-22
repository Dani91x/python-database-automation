"""analytics_settlement.py — logica PURA di settlement + hit per analytics_signals.
Isolata e testabile (vedi test_analytics_settlement.py).

⚠️ SOLDI IN GIOCO: la correttezza qui determina hit/miss → certificata su casi reali.
Settlement coerente con market_frequency_rpc.sql:
  - punteggio 90' (FT): fulltime_* PRIMARIO; fallback goals_* SOLO per status 'FT'.
    AET/PEN senza fulltime_* → 90' SCONOSCIUTO → None (riga non settlabile).
  - punteggio 1°T (HT): halftime_*; se mancante → None (mercati HT non settlabili).

MERCATI canonici gestiti (selezioni canoniche tra parentesi):
  1x2 / ht_1x2                         (H|D|A)
  over_{0..9}_5                        (Over|Under)   — totale FT
  first_half_over_{0..9}_5             (Over|Under)   — totale HT
  home_over_{0..9}_5 / away_over_{0..9}_5 (Over|Under) — gol casa/trasferta FT
  btts / first_half_btts               (Yes|No)
  double_chance / first_half_double_chance (1X|X2|12)
  clean_sheet_home / clean_sheet_away  (Yes|No)
  ht_ft                                ("{HT}_{FT}", es 'H_A')
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

FINISHED = ("FT", "AET", "PEN")
Score = Tuple[int, int]

_OVER_RE = re.compile(r"(home_|away_|first_half_)?over_(\d)_5$")


def ft_score_90(match: dict) -> Optional[Score]:
    """Punteggio a 90' (casa, trasferta), o None se sconosciuto."""
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
    return None


def ht_score(match: dict) -> Optional[Score]:
    hh, ha = match.get("halftime_home"), match.get("halftime_away")
    if hh is None or ha is None:
        return None
    return int(hh), int(ha)


def _outcome_1x2(h: int, a: int) -> str:
    return "H" if h > a else ("A" if a > h else "D")


def _over(value: int, line: float, selection: str) -> Optional[bool]:
    over = value > line
    if selection == "Over":
        return over
    if selection == "Under":
        return not over
    return None


_DC = {"1X": ("H", "D"), "X2": ("D", "A"), "12": ("H", "A")}


def hit(market: str, selection: str, ft: Optional[Score], ht: Optional[Score]) -> Optional[bool]:
    """Direzione azzeccata? True/False, oppure None se non settlabile."""
    # --- 1X2 (FT / HT) ---
    if market == "1x2":
        return None if ft is None else (_outcome_1x2(*ft) == selection)
    if market == "ht_1x2":
        return None if ht is None else (_outcome_1x2(*ht) == selection)

    # --- Over/Under: totale FT/HT, oppure gol casa/trasferta FT ---
    mo = _OVER_RE.fullmatch(market)
    if mo:
        prefix, n = mo.group(1), int(mo.group(2))
        line = n + 0.5
        if prefix == "first_half_":
            return None if ht is None else _over(ht[0] + ht[1], line, selection)
        if ft is None:
            return None
        if prefix == "home_":
            return _over(ft[0], line, selection)
        if prefix == "away_":
            return _over(ft[1], line, selection)
        return _over(ft[0] + ft[1], line, selection)  # totale FT

    # --- BTTS (FT / HT) ---
    if market in ("btts", "first_half_btts"):
        sc = ft if market == "btts" else ht
        if sc is None:
            return None
        both = sc[0] >= 1 and sc[1] >= 1
        return both if selection == "Yes" else (not both if selection == "No" else None)

    # --- Doppia chance (FT / HT) ---
    if market in ("double_chance", "first_half_double_chance"):
        sc = ft if market == "double_chance" else ht
        if sc is None or selection not in _DC:
            return None
        return _outcome_1x2(*sc) in _DC[selection]

    # --- Clean sheet (FT): casa = trasferta non segna; trasferta = casa non segna ---
    if market == "clean_sheet_home":
        if ft is None:
            return None
        cs = ft[1] == 0
        return cs if selection == "Yes" else (not cs if selection == "No" else None)
    if market == "clean_sheet_away":
        if ft is None:
            return None
        cs = ft[0] == 0
        return cs if selection == "Yes" else (not cs if selection == "No" else None)

    # --- HT/FT combo: selezione "{HT}_{FT}" (es 'H_A') ---
    if market == "ht_ft":
        if ft is None or ht is None:
            return None
        return selection == f"{_outcome_1x2(*ht)}_{_outcome_1x2(*ft)}"

    return None  # mercato non gestito → mai indovinare
