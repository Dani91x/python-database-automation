"""pressure — indice di PRESSIONE di gioco dalle statistiche IPS del feed.

Modulo PURO. ``pressure_from_payload(payload) -> (mult_home, mult_away)``:
moltiplicatori dei tassi di gol residui (λ) che il modello opportunità applica
per squadra; 1.0 = neutro. Dati usati (tutti opzionali, ogni assenza = neutro):

  payload.score_raw.score.{home,away}.numberOfCorners      corner totali
  payload.score_raw.score.{home,away}.numberOfYellowCards  gialli
  payload.score_raw.score.{home,away}.bookingPoints        punti disciplinari (riserva
                                                           dei gialli quando mancano)
  payload.timeline[]  {type, team, minute}                 eventi IPS (corner col minuto)
  payload.minute                                           minuto di gioco

FORMULA (documentata, simmetrica):
  corner_h, corner_a = corner degli ultimi ``WINDOW_MIN`` (10) minuti dalla timeline
                       (se la timeline porta corner); altrimenti i totali IPS
                       (la normalizzazione al minuto si elide nel rapporto: il
                       confronto fra le due squadre è già scale-free)
  corner_edge = (corner_h − corner_a) / max(corner_h + corner_a, MIN_VOLUME)     ∈ [−1, 1]
  card_edge   = (gialli_a − gialli_h) / max(gialli_h + gialli_a, MIN_VOLUME)     ∈ [−1, 1]
                (i gialli li prende chi DIFENDE sotto pressione: gialli avversari
                 = pressione della squadra)
  idx_home = W_CORNER · corner_edge + W_CARD · card_edge ;  idx_away = −idx_home
  mult     = clip(1 + GAIN · idx, MULT_MIN, MULT_MAX) = clip(1 + 0.25·idx, 0.85, 1.25)

Guardie: prima del minuto ``MIN_MINUTE`` (5) o senza alcun dato → (1.0, 1.0).
Il denominatore minimo (MIN_VOLUME = 2) smorza i campioni piccoli (1 corner
a 0 non è dominio). Gli eventi della timeline senza minuto o senza squadra
riconoscibile sono ignorati.
"""
from __future__ import annotations

import re
from typing import Any, Optional

WINDOW_MIN = 10          # finestra mobile dei corner (minuti di gioco)
MIN_MINUTE = 5           # prima: nessun segnale
MIN_VOLUME = 2.0         # denominatore minimo dei rapporti
W_CORNER = 0.75
W_CARD = 0.25
GAIN = 0.25
MULT_MIN = 0.85
MULT_MAX = 1.25

_CORNER_RE = re.compile(r"corner", re.IGNORECASE)
_HOME_RE = re.compile(r"^(home|casa|h)$", re.IGNORECASE)
_AWAY_RE = re.compile(r"^(away|ospite|a)$", re.IGNORECASE)


def _int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _side_stats(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = payload.get("score_raw")
    score = raw.get("score") if isinstance(raw, dict) else None
    if not isinstance(score, dict):
        return {}, {}
    h = score.get("home") if isinstance(score.get("home"), dict) else {}
    a = score.get("away") if isinstance(score.get("away"), dict) else {}
    return h, a


def _team_of(ev: dict[str, Any]) -> Optional[str]:
    t = str(ev.get("team") or "").strip()
    if _HOME_RE.match(t):
        return "home"
    if _AWAY_RE.match(t):
        return "away"
    return None


def rolling_corners(timeline: Any, minute: int, window: int = WINDOW_MIN
                    ) -> Optional[tuple[int, int]]:
    """(corner casa, corner ospite) negli ultimi ``window`` minuti dalla
    timeline; None se la timeline non porta NESSUN corner attribuibile."""
    if not isinstance(timeline, list):
        return None
    found = False
    h = a = 0
    lo = minute - window
    for ev in timeline:
        if not isinstance(ev, dict) or not _CORNER_RE.search(str(ev.get("type") or "")):
            continue
        team = _team_of(ev)
        m = _int(ev.get("minute"))
        if team is None or m is None:
            continue
        found = True
        if lo < m <= minute:
            if team == "home":
                h += 1
            else:
                a += 1
    return (h, a) if found else None


def _edge(x: Optional[float], y: Optional[float]) -> Optional[float]:
    if x is None or y is None:
        return None
    return (x - y) / max(x + y, MIN_VOLUME)


def _clip(m: float) -> float:
    return round(min(MULT_MAX, max(MULT_MIN, m)), 4)


def pressure_index(payload: Any) -> Optional[float]:
    """Indice di pressione della squadra di CASA in [−1, 1] (negativo = pressione
    ospite); None quando non c'è alcun dato utilizzabile."""
    if not isinstance(payload, dict):
        return None
    minute = _int(payload.get("minute"))
    if minute is None or minute < MIN_MINUTE:
        return None
    h, a = _side_stats(payload)
    roll = rolling_corners(payload.get("timeline"), minute)
    if roll is not None:
        c_h, c_a = float(roll[0]), float(roll[1])
    else:
        ch, ca = _int(h.get("numberOfCorners")), _int(a.get("numberOfCorners"))
        c_h = None if ch is None else float(ch)
        c_a = None if ca is None else float(ca)
    y_h = _int(h.get("numberOfYellowCards"))
    y_a = _int(a.get("numberOfYellowCards"))
    if y_h is None or y_a is None:
        bp_h, bp_a = _int(h.get("bookingPoints")), _int(a.get("bookingPoints"))
        if bp_h is not None and bp_a is not None:
            y_h, y_a = bp_h / 10.0, bp_a / 10.0   # 10 punti = un giallo
    corner_edge = _edge(c_h, c_a)
    card_edge = _edge(None if y_a is None else float(y_a),
                      None if y_h is None else float(y_h))
    if corner_edge is None and card_edge is None:
        return None
    idx = W_CORNER * (corner_edge or 0.0) + W_CARD * (card_edge or 0.0)
    return round(max(-1.0, min(1.0, idx)), 4)


def pressure_from_payload(payload: Any) -> tuple[float, float]:
    """(mult_home, mult_away) in [0.85, 1.25]; (1.0, 1.0) senza dati."""
    idx = pressure_index(payload)
    if idx is None:
        return 1.0, 1.0
    return _clip(1.0 + GAIN * idx), _clip(1.0 - GAIN * idx)
