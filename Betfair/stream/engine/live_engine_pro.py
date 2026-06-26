"""Motore Poisson Live "definitivo" (F2) — decisione in-play per ogni partita.

Combina:
  - λ pre-match (da quote 1X2 di apertura o forniti) → λ residuo = scoring-rate ×
    tempo rimanente;
  - Dixon-Coles `score_matrix` (correzione bassi punteggi via ρ per-lega) sui gol
    RESIDUI, aggregata tenendo conto del PUNTEGGIO CORRENTE → prob coerenti dei
    mercati (1X2 / Over-Under / BTTS);
  - calibrazione difensiva (hook su dynamic_cal.json; identità se forma ignota);
  - microstruttura mercato (best back/lay, liquidità) → edge, direzione, confidenza;
  - Kelly frazionato (suggerimento di stake, trasparente).

PURO e testabile (nessuna rete/DB). Lo STESSO modulo è usato dal runner live e dal
backtest flumine → coerenza totale live==backtest.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from tactical_engine.dixon_coles import score_matrix

from .live_engine import estimate_prematch_lambdas, implied_prob, remaining_rate

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_RHO_PATH = os.path.join(_ROOT, "dc_rho_by_league.json")
_CAL_PATH = os.path.join(_ROOT, "dynamic_cal.json")

_DEFAULT_RHO = -0.13


# ----------------------------------------------------------------------------
# Caricamenti difensivi (rho per-lega, calibrazione)
# ----------------------------------------------------------------------------
def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


_RHO_DATA = _load_json(_RHO_PATH)
_CAL_DATA = _load_json(_CAL_PATH)


def rho_for_league(league_id: Optional[int]) -> float:
    by = _RHO_DATA.get("rho_by_league", {}) if isinstance(_RHO_DATA, dict) else {}
    fallback = _RHO_DATA.get("global_fallback", _DEFAULT_RHO) if isinstance(_RHO_DATA, dict) else _DEFAULT_RHO
    if league_id is not None and str(league_id) in by:
        return float(by[str(league_id)])
    return float(fallback)


def calibrate(prob: float, market_key: str, league_id: Optional[int]) -> float:
    """Hook di calibrazione. Difensivo: se la struttura non è riconosciuta o assente,
    ritorna la probabilità invariata (meglio non calibrare che calibrare a caso).
    Struttura attesa (se presente): dynamic_cal[by_league|global][market_key] = fattore.
    """
    if not isinstance(_CAL_DATA, dict):
        return prob
    node = None
    by_league = _CAL_DATA.get("by_league")
    if league_id is not None and isinstance(by_league, dict):
        node = by_league.get(str(league_id))
    if node is None:
        node = _CAL_DATA.get("global")
    if isinstance(node, dict):
        factor = node.get(market_key)
        if isinstance(factor, (int, float)) and 0 < factor < 5:
            return max(0.0, min(1.0, prob * float(factor)))
    return prob


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class MarketSignal:
    market_id: str
    market_type: Optional[str]
    selection_id: int
    selection_name: Optional[str]
    model_prob: float
    market_back: Optional[float]
    market_lay: Optional[float]
    fair_back: Optional[float]
    fair_lay: Optional[float]
    edge: Optional[float]
    direction: str          # BACK | LAY | HOLD
    confidence: float       # 0..1
    kelly_stake: float


def signals_to_json(signals: List[MarketSignal]) -> Dict[str, Any]:
    return {"signals": [asdict(s) for s in signals], "updated_ms": None}


# ----------------------------------------------------------------------------
# λ pre-match
# ----------------------------------------------------------------------------
def _best_back(ladder_sel: Dict[str, Any]) -> Optional[float]:
    b = (ladder_sel or {}).get("back") or []
    return b[0][0] if b else None


def _best_lay(ladder_sel: Dict[str, Any]) -> Optional[float]:
    l = (ladder_sel or {}).get("lay") or []
    return l[0][0] if l else None


def get_prematch_lambdas(
    event_id: str,
    fixture_id: Optional[int],
    match_odds_ladder: Optional[Dict[str, Any]] = None,
    league_id: Optional[int] = None,
) -> Tuple[float, float, Optional[int]]:
    """Ritorna (λ_casa, λ_trasferta, league_id).

    Preferenza: λ da predizioni/DC esterne per fixture_id (non caricate qui per
    restare puri — il chiamante può passarle pre-calcolate). Fallback: stima dalle
    quote 1X2 di apertura (best back di home/away nel ladder MATCH_ODDS).
    """
    if match_odds_ladder:
        backs = []
        for sel in match_odds_ladder.values():
            bb = _best_back(sel)
            if bb:
                backs.append(bb)
        # MATCH_ODDS: 3 selezioni; prob implicite normalizzate
        if len(backs) >= 2:
            probs = [1.0 / b for b in backs if b and b > 1]
            # ordinamento per selezione non garantito qui → usa la più probabile come "casa"
            probs_sorted = sorted(probs, reverse=True)
            p_home = probs_sorted[0]
            p_away = probs_sorted[1] if len(probs_sorted) > 1 else probs_sorted[0]
            lam_h, lam_a = estimate_prematch_lambdas(p_home, p_away)
            return lam_h, lam_a, league_id
    # default neutro
    return 1.35, 1.15, league_id


# ----------------------------------------------------------------------------
# Aggregazione mercati dalla griglia DC RESIDUA + punteggio corrente
# ----------------------------------------------------------------------------
def _markets_from_residual(
    grid: Any, score_home: int, score_away: int, lines: List[float]
) -> Dict[str, float]:
    """Probabilità finali dei mercati partendo dalla griglia dei gol RESIDUI
    (DC) e sommando il punteggio corrente. grid[rh][ra] = P(rh, ra residui)."""
    n = grid.shape[0]
    p_home = p_draw = p_away = 0.0
    p_over = {ln: 0.0 for ln in lines}
    btts_yes = 0.0
    for rh in range(n):
        for ra in range(n):
            p = float(grid[rh, ra])
            if p <= 0.0:
                continue
            fh, fa = score_home + rh, score_away + ra
            if fh > fa:
                p_home += p
            elif fh == fa:
                p_draw += p
            else:
                p_away += p
            total = fh + fa
            for ln in lines:
                if total > ln:
                    p_over[ln] += p
            if fh >= 1 and fa >= 1:
                btts_yes += p
    z = p_home + p_draw + p_away
    if z > 0:
        p_home, p_draw, p_away = p_home / z, p_draw / z, p_away / z
    out = {"home": p_home, "draw": p_draw, "away": p_away, "btts_yes": min(1.0, btts_yes)}
    out["btts_no"] = max(0.0, 1.0 - out["btts_yes"])
    for ln in lines:
        key = str(ln).replace(".", "_")
        out[f"over_{key}"] = p_over[ln]
        out[f"under_{key}"] = max(0.0, 1.0 - p_over[ln])
    return out


# ----------------------------------------------------------------------------
# Kelly + confidenza
# ----------------------------------------------------------------------------
def _kelly_back(prob: float, odds: float, fraction: float, bankroll: float) -> float:
    if not odds or odds <= 1:
        return 0.0
    b = odds - 1.0
    f = prob - (1.0 - prob) / b   # Kelly classico per back
    return max(0.0, f) * fraction * bankroll


def _kelly_lay(prob: float, lay_odds: float, fraction: float, bankroll: float) -> float:
    # heuristica simmetrica: lay = back dell'esito complementare alla quota lay
    if not lay_odds or lay_odds <= 1:
        return 0.0
    b = lay_odds - 1.0
    p_comp = 1.0 - prob
    f = p_comp - prob / b
    return max(0.0, f) * fraction * bankroll


_OU_LINE_RE = re.compile(r"(\d+)_?(\d)$")


def _line_from_market_type(market_type: Optional[str]) -> Optional[float]:
    """OVER_UNDER_25 -> 2.5, OVER_UNDER_05 -> 0.5."""
    if not market_type or "OVER_UNDER" not in market_type.upper():
        return None
    m = _OU_LINE_RE.search(market_type)
    if m:
        return float(f"{int(m.group(1))}.{m.group(2)}")
    return None


def _name_is_draw(name: Optional[str]) -> bool:
    return bool(name) and ("draw" in name.lower() or "pareggio" in name.lower())


def _name_side(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    n = name.lower()
    if n.startswith("over") or "over" in n:
        return "over"
    if n.startswith("under") or "under" in n:
        return "under"
    if n in ("yes", "si", "sì"):
        return "yes"
    if n == "no":
        return "no"
    return None


# ----------------------------------------------------------------------------
# Valutazione di un evento
# ----------------------------------------------------------------------------
def evaluate_event(
    *,
    score_home: Optional[int],
    score_away: Optional[int],
    minute: Optional[int],
    prematch_lambda_home: float,
    prematch_lambda_away: float,
    league_id: Optional[int],
    markets: List[Dict[str, Any]],
    ladder_by_market: Dict[str, Any],
    bankroll: float = 100.0,
    min_edge: float = 0.03,
    kelly_fraction: float = 0.25,
) -> List[MarketSignal]:
    sh = int(score_home or 0)
    sa = int(score_away or 0)
    lam_h = remaining_rate(prematch_lambda_home, minute)
    lam_a = remaining_rate(prematch_lambda_away, minute)
    rho = rho_for_league(league_id)
    grid = score_matrix(max(0.01, lam_h), max(0.01, lam_a), rho)

    lines = [0.5, 1.5, 2.5, 3.5]
    probs = _markets_from_residual(grid, sh, sa, lines)

    signals: List[MarketSignal] = []
    for m in markets:
        mtype = (m.get("market_type") or "").upper()
        mid = m["market_id"]
        ladder = ladder_by_market.get(mid) or {}
        sels = m.get("selections") or []

        # mappa selezione → probabilità modello
        prob_for: Dict[int, Tuple[float, str]] = {}
        if mtype == "MATCH_ODDS":
            draw_sel = next((s for s in sels if _name_is_draw(s.get("name"))), None)
            non_draw = [s for s in sels if not _name_is_draw(s.get("name"))]
            non_draw.sort(key=lambda s: s.get("sort_priority") or 0)
            if draw_sel:
                prob_for[int(draw_sel["selection_id"])] = (probs["draw"], "1x2_draw")
            if len(non_draw) >= 1:
                prob_for[int(non_draw[0]["selection_id"])] = (probs["home"], "home")
            if len(non_draw) >= 2:
                prob_for[int(non_draw[1]["selection_id"])] = (probs["away"], "away")
        elif "OVER_UNDER" in mtype:
            line = _line_from_market_type(mtype)
            if line is not None:
                key = str(line).replace(".", "_")
                for s in sels:
                    side = _name_side(s.get("name"))
                    if side == "over":
                        prob_for[int(s["selection_id"])] = (probs.get(f"over_{key}", 0.0), f"over_{key}")
                    elif side == "under":
                        prob_for[int(s["selection_id"])] = (probs.get(f"under_{key}", 0.0), f"under_{key}")
        elif "BOTH_TEAMS_TO_SCORE" in mtype or mtype == "BTTS":
            for s in sels:
                side = _name_side(s.get("name"))
                if side == "yes":
                    prob_for[int(s["selection_id"])] = (probs["btts_yes"], "btts_yes")
                elif side == "no":
                    prob_for[int(s["selection_id"])] = (probs["btts_no"], "btts_no")
        else:
            continue  # mercato non modellato → nessun segnale

        names = {int(s["selection_id"]): s.get("name") for s in sels}
        for sel_id, (raw_prob, mkey) in prob_for.items():
            prob = calibrate(raw_prob, mkey, league_id)
            ladder_sel = ladder.get(str(sel_id)) or ladder.get(sel_id) or {}
            back = _best_back(ladder_sel)
            lay = _best_lay(ladder_sel)
            imp = implied_prob(back)
            edge = (prob - imp) if imp is not None else None
            fair = (1.0 / prob) if prob > 0 else None

            direction = "HOLD"
            kelly = 0.0
            if edge is not None and edge >= min_edge and back:
                direction = "BACK"
                kelly = _kelly_back(prob, back, kelly_fraction, bankroll)
            elif edge is not None and edge <= -min_edge and lay:
                direction = "LAY"
                kelly = _kelly_lay(prob, lay, kelly_fraction, bankroll)

            # confidenza: ampiezza edge (saturata) pesata dalla liquidità disponibile
            liq = float(ladder_sel.get("tv") or 0.0)
            liq_factor = min(1.0, liq / 500.0) if liq else 0.5
            conf = 0.0
            if edge is not None:
                conf = max(0.0, min(1.0, (abs(edge) / 0.15) * (0.6 + 0.4 * liq_factor)))

            signals.append(MarketSignal(
                market_id=mid, market_type=m.get("market_type"),
                selection_id=sel_id, selection_name=names.get(sel_id),
                model_prob=round(prob, 4), market_back=back, market_lay=lay,
                fair_back=round(fair, 3) if fair else None,
                fair_lay=round(fair, 3) if fair else None,
                edge=round(edge, 4) if edge is not None else None,
                direction=direction, confidence=round(conf, 3),
                kelly_stake=round(kelly, 2),
            ))
    return signals
