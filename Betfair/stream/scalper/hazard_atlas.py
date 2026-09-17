"""hazard_atlas.py — ATLANTE HAZARD: caricamento e lookup, PURI.

Perche' questo modulo esiste (INCIDENTE 17/09/2026, causa vera del blackout
delle quote su tutto il feed):

``safe_strategy/service.py``, ``selezione.py`` e ``opportunity.py`` caricano
l'Atlante con un import PIGRO. Finche' viveva in ``theta_bot``, quell'import
tirava dentro ``Betfair.stream.scalper.__init__`` -> ``scalper_bot`` ->
``from flumine import BaseStrategy``. E ``flumine/__init__.py:13`` fa::

    bettingresources.RunnerBookEX = EX     # flumine/patching.py

cioe' SOSTITUISCE, per tutto il processo, la classe che betfairlightweight usa
per il ladder con una che lascia i livelli come DIZIONARI. Da quell'istante
``scanner.best_price`` (``levels[0].price``, dentro un ``except`` che ritorna
None) leggeva ``None`` su OGNI runner, da stream E da REST: il feed scriveva
quote nulle su tutti i mercati mentre Betfair mandava i prezzi (misurato:
``{'price': 3.2, 'size': 821.19}`` letto come ``None``). L'import e' pigro, e
scattava al primo giro che serviva l'Atlante: per questo la mattina - senza
calcio in gioco - il feed stava bene, e per questo il riavvio non risolveva.

Qui dentro NON si importa flumine, e non si deve mai. Il processo del feed
carica l'Atlante da questo modulo; ``theta_bot`` (che flumine lo usa davvero)
riesporta gli stessi nomi, cosi' i chiamanti storici non cambiano.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# percorso di default dell'Atlante Hazard (repo-relative, v1 15/07)
ATLAS_DEFAULT_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "omega", "data",
    "hazard_atlas_v1.json"))


# ---------------------------------------------------------------------------
# ATLANTE HAZARD — lookup PURO (testabile senza file/flumine)
# ---------------------------------------------------------------------------
def load_hazard_atlas(path: Optional[str] = None) -> Dict[str, Any]:
    """Carica l'Atlante Hazard dal JSON (2.8MB, una volta per processo)."""
    p = path or ATLAS_DEFAULT_PATH
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def hazard_bucket(minute: float) -> str:
    """Bucket 5' dell'Atlante ('0-5' .. '85-90') dal minuto reale."""
    m = max(0, min(89, int(minute)))
    lo = (m // 5) * 5
    return f"{lo}-{lo + 5}"


def hazard_goals_key(goals: int) -> str:
    """Chiave gol dell'Atlante: '0' | '1' | '2' | '3+'."""
    g = max(0, int(goals))
    return "3+" if g >= 3 else str(g)


def _find_team(by_team: Dict[str, Any], name: Optional[str]) -> Optional[dict]:
    """Cerca la squadra PER NOME (case-insensitive). None = fallback lega."""
    if not name:
        return None
    n = str(name).strip().lower()
    for t in by_team.values():
        if str(t.get("team_name", "")).strip().lower() == n:
            return t
    return None


def hazard_lookup(
    atlas: Optional[Dict[str, Any]],
    minute: float,
    goals: int,
    league_id: Optional[Any] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    horizon: str = "p_goal_next_3min",
) -> Tuple[Optional[float], str]:
    """P(gol nei prossimi 3') per lo stato (minuto, gol) — catena meta.lookup.

    1) SQUADRE: entrambe in by_team + lega in by_league →
       f_att(T,b)=att_rate(T,b)/side_rate(lega,b), f_def analogo;
       M(b)=0.5*[fA_att*fB_def + fB_att*fA_def];
       P = 1 - (1 - P_lega(b,g))^M.
    2) LEGA: by_league[league_id].grid (gia' shrinkata).
    3) GLOBALE: atlas['global'].
    Ritorna (p, fonte) con fonte in {'team','league','global','none'};
    (None, 'none') = semaforo ROSSO (fail-closed).
    """
    if not atlas:
        return None, "none"
    b = hazard_bucket(minute)
    gk = hazard_goals_key(goals)
    by_league = atlas.get("by_league") or {}
    lg = by_league.get(str(league_id)) if league_id is not None else None

    # 1) livello SQUADRE (blend moltiplicativo sull'hazard di lega)
    if lg is not None:
        by_team = atlas.get("by_team") or {}
        ta = _find_team(by_team, home_team)
        tb = _find_team(by_team, away_team)
        cell = ((lg.get("grid") or {}).get(b) or {}).get(gk)
        sr = ((lg.get("meta") or {}).get("side_rate_per_bucket") or {}).get(b)
        if ta and tb and cell and sr:
            p_lega = cell.get(horizon)
            if p_lega is not None:
                try:
                    fa_att = float(ta["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fa_def = float(ta["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_att = float(tb["att_goals_per_match_by_bucket"].get(b, sr)) / sr
                    fb_def = float(tb["def_goals_per_match_by_bucket"].get(b, sr)) / sr
                    mult = 0.5 * (fa_att * fb_def + fb_att * fa_def)
                    p = 1.0 - (1.0 - float(p_lega)) ** max(0.0, mult)
                    return p, "team"
                except (KeyError, TypeError, ValueError, ZeroDivisionError):
                    pass  # fallback dichiarato: lega
        # 2) livello LEGA
        if cell is not None and cell.get(horizon) is not None:
            return float(cell[horizon]), "league"

    # 3) livello GLOBALE
    cell = ((atlas.get("global") or {}).get(b) or {}).get(gk)
    if cell is not None and cell.get(horizon) is not None:
        return float(cell[horizon]), "global"
    return None, "none"
