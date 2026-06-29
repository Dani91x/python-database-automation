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

from .live_engine import (
    estimate_prematch_lambdas,
    inplay_residual_rates,
)

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


# mappa la chiave-mercato del motore → cal_key reale di dynamic_cal.json
_CAL_KEY_MAP = {
    "home": "H", "draw": "D", "away": "A",
    "over_1_5": "O15", "under_1_5": "U15",
    "over_2_5": "O25", "under_2_5": "U25",
    "over_3_5": "O35", "under_3_5": "U35",
    "btts_yes": "BTTS", "btts_no": "BTTS_NO",
}


def _prob_bin(prob: float) -> str:
    """Fascia di probabilità (decile 0..9) — STESSA convenzione del builder della
    calibrazione (update_poisson_calibration.py)."""
    return str(max(0, min(9, int(max(0.0, min(0.999999, prob)) * 10))))


# La calibrazione è SPENTA di default: va validata su prob IN-PLAY prima di attivarla
# (dynamic_cal è costruita su prob pre-match). Spenta → identità = comportamento
# dell'originale. Si attiva solo dopo verifica che NON peggiora i segnali.
_CALIBRATION_ENABLED = False


def calibrate(prob: float, market_key: str, league_id: Optional[int]) -> float:
    """Calibrazione PER-LEGA × MERCATO × FASCIA dai dati reali (dynamic_cal.json).

    Struttura reale: ``dynamic_cal[by_league|global][cal_key][bin] = fattore`` dove
    ``cal_key`` ∈ {H,D,A,O15,U15,O25,U25,O35,U35,BTTS,BTTS_NO,...} e ``bin`` è il
    decile di probabilità. Catena lega → globale → identità. Mercati non mappati o
    senza dato passano invariati (meglio non calibrare che calibrare a caso).
    """
    if not _CALIBRATION_ENABLED or not isinstance(_CAL_DATA, dict):
        return prob
    cal_key = _CAL_KEY_MAP.get(market_key)
    if cal_key is None:
        return prob
    node = None
    by_league = _CAL_DATA.get("by_league")
    if league_id is not None and isinstance(by_league, dict):
        lg = by_league.get(str(league_id))
        if isinstance(lg, dict) and isinstance(lg.get(cal_key), dict):
            node = lg[cal_key]
    if node is None:
        glob = _CAL_DATA.get("global")
        if isinstance(glob, dict) and isinstance(glob.get(cal_key), dict):
            node = glob[cal_key]
    if not isinstance(node, dict):
        return prob
    factor = node.get(_prob_bin(prob))
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
    lay_levels = (ladder_sel or {}).get("lay") or []
    return lay_levels[0][0] if lay_levels else None


def _ladder_sel(ladder: Dict[str, Any], sel_id: Any) -> Dict[str, Any]:
    return ladder.get(str(sel_id)) or ladder.get(sel_id) or {}


def total_goals_from_ou(
    markets: List[Dict[str, Any]], ladder_by_market: Dict[str, Any]
) -> Optional[float]:
    """Stima λ_TOTALE atteso invertendo il mercato Over/Under più vicino a 2.5.

    Il mercato O/U PREZZA direttamente i gol totali: dalle quote back de-viggate di
    Over/Under si ricava la prob di Over e si inverte il λ del periodo (Poisson).
    DATA-DRIVEN: niente costante 2.6. Ritorna None se nessun O/U utilizzabile.
    """
    try:
        from value_engine.devig import devig_pair
        from value_engine.poisson_total import lam_from_prematch
    except Exception:  # pragma: no cover
        return None
    best: Optional[Tuple[float, float, float]] = None  # (dist_da_2.5, line, p_over)
    for m in markets:
        line = _line_from_market_type(m.get("market_type"))
        if line is None:
            continue
        ladder = ladder_by_market.get(m.get("market_id")) or {}
        over_back = under_back = None
        for s in (m.get("selections") or []):
            side = _name_side(s.get("name"))
            bb = _best_back(_ladder_sel(ladder, s.get("selection_id")))
            if side == "over":
                over_back = bb
            elif side == "under":
                under_back = bb
        if over_back and under_back and over_back > 1 and under_back > 1:
            p_over = devig_pair(over_back, under_back)
            dist = abs(line - 2.5)
            if best is None or dist < best[0]:
                best = (dist, line, p_over)
    if best is None:
        return None
    _, line, p_over = best
    try:
        return lam_from_prematch("over", int(line - 0.5), p_over)
    except Exception:  # pragma: no cover - inversione non riuscita
        return None


def get_prematch_lambdas(
    event_id: str,
    fixture_id: Optional[int],
    match_odds_market: Optional[Dict[str, Any]] = None,
    ladder: Optional[Dict[str, Any]] = None,
    league_id: Optional[int] = None,
    expected_total_goals: Optional[float] = None,
) -> Tuple[float, float, Optional[int]]:
    """Ritorna (λ_casa, λ_trasferta, league_id).

    Il TOTALE gol atteso è DATA-DRIVEN: ``expected_total_goals`` quando fornito
    (dalle forze per-squadra del DB o dall'inversione del mercato O/U); la costante
    2.6 resta solo come ultima spiaggia. Lo SPLIT casa/trasferta viene dalle quote
    1X2 (per sort_priority: 1=casa, 2=trasferta — non per probabilità).
    """
    total = expected_total_goals if (expected_total_goals and expected_total_goals > 0) else None
    if match_odds_market and ladder:
        sels = match_odds_market.get("selections") or []
        non_draw = [s for s in sels if not _name_is_draw(s.get("name"))]
        non_draw.sort(key=lambda s: s.get("sort_priority") or 0)
        if len(non_draw) >= 2:
            home_id, away_id = non_draw[0]["selection_id"], non_draw[1]["selection_id"]
            bh = _best_back(_ladder_sel(ladder, home_id))
            ba = _best_back(_ladder_sel(ladder, away_id))
            if bh and ba and bh > 1 and ba > 1:
                if total is not None:
                    lam_h, lam_a = estimate_prematch_lambdas(
                        1.0 / bh, 1.0 / ba, expected_total_goals=total
                    )
                else:
                    lam_h, lam_a = estimate_prematch_lambdas(1.0 / bh, 1.0 / ba)
                return lam_h, lam_a, league_id
    # nessun 1X2 utilizzabile: se ho il totale, split neutro (lieve vantaggio casa)
    if total is not None:
        return total * 0.54, total * 0.46, league_id
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
def _kelly_back(prob: float, odds: float, fraction: float, bankroll: float,
                commission: float = 0.0) -> float:
    # Kelly per il back AL NETTO della commissione (prelevata sul profitto):
    # vincita netta per unità b = (odds-1)*(1-commission) ; f* = prob - (1-prob)/b.
    if not odds or odds <= 1:
        return 0.0
    b = (odds - 1.0) * (1.0 - commission)
    if b <= 0:
        return 0.0
    f = prob - (1.0 - prob) / b
    return max(0.0, f) * fraction * bankroll


def _kelly_lay(prob: float, lay_odds: float, fraction: float, bankroll: float,
               commission: float = 0.0) -> float:
    # Kelly per il lay AL NETTO della commissione: vinci stake*(1-commission) con
    # prob (1-prob), perdi stake*(odds-1) con prob.
    # f* = (1-prob)/(odds-1) - prob/(1-commission)  (a quota equa lorda torna ≤0 → 0).
    if not lay_odds or lay_odds <= 1:
        return 0.0
    b = lay_odds - 1.0
    w = 1.0 - commission
    if b <= 0 or w <= 0:
        return 0.0
    f = (1.0 - prob) / b - prob / w
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
    commission: float = 0.05,
    red_home: int = 0,
    red_away: int = 0,
    pressure_home: float = 1.0,
    pressure_away: float = 1.0,
) -> List[MarketSignal]:
    sh = int(score_home or 0)
    sa = int(score_away or 0)
    # tassi gol RESIDUI adattati allo stato LIVE: tempo (hazard non lineare) ×
    # stato di gioco (chi insegue/è avanti) × cartellini rossi × pressione.
    lam_h, lam_a = inplay_residual_rates(
        prematch_lambda_home, prematch_lambda_away, minute, sh, sa,
        red_home=red_home, red_away=red_away, league_id=league_id,
        pressure_home=pressure_home, pressure_away=pressure_away,
    )
    rho = rho_for_league(league_id)
    grid = score_matrix(max(0.01, lam_h), max(0.01, lam_a), rho)

    # calcola TUTTE le linee O/U realmente presenti (non solo 0.5–3.5), così le
    # linee alte non ricevono prob=0.0 di default → niente segnali falsi.
    lines = {0.5, 1.5, 2.5, 3.5}
    for m in markets:
        ln = _line_from_market_type(m.get("market_type"))
        if ln is not None:
            lines.add(ln)
    lines = sorted(lines)
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
                prob_for[int(draw_sel["selection_id"])] = (probs["draw"], "draw")
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
        # calibrazione PER-LEGA + RINORMALIZZAZIONE per mercato: le selezioni di un
        # mercato sono mutuamente esclusive ed esaustive (1X2 / Over+Under / BTTS),
        # quindi dopo la calibrazione le prob devono tornare a sommare 1 (coerenza).
        _cal = {sid: calibrate(rp, mk, league_id) for sid, (rp, mk) in prob_for.items()}
        _z = sum(_cal.values())
        if _z > 0:
            _cal = {sid: v / _z for sid, v in _cal.items()}
        else:  # corner case: tutte le prob calibrate nulle → usa le grezze
            _cal = {sid: rp for sid, (rp, _mk) in prob_for.items()}
        for sel_id, (raw_prob, mkey) in prob_for.items():
            prob = _cal.get(sel_id, raw_prob)
            ladder_sel = _ladder_sel(ladder, sel_id)
            back = _best_back(ladder_sel)
            lay = _best_lay(ladder_sel)
            fair = (1.0 / prob) if prob > 0 else None
            c = commission

            # EV per £1 di stake, AL NETTO della commissione (prelevata sulle vincite):
            #   BACK: vinci (back-1)*(1-c) con prob ; perdi 1 con (1-prob)
            #   LAY : vinci 1*(1-c) con (1-prob)    ; perdi (lay-1) con prob
            # Ogni lato è valutato sul PROPRIO prezzo (il lay NON usa più il back).
            back_ev = (prob * (back - 1.0) * (1.0 - c) - (1.0 - prob)) if (back and back > 1) else None
            lay_ev = ((1.0 - prob) * (1.0 - c) - prob * (lay - 1.0)) if (lay and lay > 1) else None

            # scegli il lato col miglior EV; segnala solo se supera la soglia (min_edge = EV minimo).
            direction = "HOLD"
            kelly = 0.0
            edge = None
            cands = [x for x in (("BACK", back_ev), ("LAY", lay_ev)) if x[1] is not None]
            if cands:
                best_side, best_ev = max(cands, key=lambda x: x[1])
                edge = best_ev
                if best_ev >= min_edge:
                    direction = best_side
                    if best_side == "BACK":
                        kelly = _kelly_back(prob, back, kelly_fraction, bankroll, c)
                    else:
                        kelly = _kelly_lay(prob, lay, kelly_fraction, bankroll, c)

            # confidenza: ampiezza edge (EV) saturata, pesata dalla liquidità disponibile
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
