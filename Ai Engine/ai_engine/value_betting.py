"""
Value Betting module: Expected Value (EV), Kelly Criterion staking,
and bet signal generation.

This is the core engine for deciding WHAT to bet and HOW MUCH.
Without positive expected value, no bet should be placed regardless
of model confidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class BetSignal:
    """A single recommended bet with all decision data."""
    market: str
    action: str          # e.g. "over", "H", "True"
    model_prob: float    # model's predicted probability
    implied_prob: float  # implied probability from odds (1/odds)
    decimal_odds: float  # bookmaker odds
    expected_value: float  # EV per unit staked
    kelly_fraction: float  # recommended fraction of bankroll
    kelly_stake: float     # recommended units (given bankroll)
    confidence_grade: str  # "high" / "medium" / "low"
    edge: float            # model_prob - implied_prob
    ml_score: float = 0.0  # edge × √prob — signal quality metric (ML_SCORE_TIERS)


# ── Configuration ───────────────────────────────────────────────────

# ML Score tiers: score = edge × √prob  (quantifica qualità del segnale).
# Le stesse soglie usate da money_management.scan_best_market_ml per coerenza.
# Tiered thresholds: (max_odds_exclusive, min_score)
ML_SCORE_TIERS: List[tuple] = [
    (2.5,  0.025),   # odds < 2.5  → score ≥ 0.025
    (4.0,  0.040),   # odds 2.5–4  → score ≥ 0.040
    (6.0,  0.055),   # odds 4–6    → score ≥ 0.055
    (999., 0.075),   # odds > 6    → score ≥ 0.075 (solo occasioni eccezionali)
]

# Betfair exchange commission applied to NET winnings (not stake).
# Standard UK rate is 5%.  This is deducted from the winning profit.
BETFAIR_COMMISSION: float = 0.05

# Minimum EV AFTER Betfair commission to recommend a bet.
# At 5% commission, any EV (pre-commission) below ~5.26% yields negative
# expected profit.  We set the bar at 3% POST-commission, meaning the
# model must show an EV of at least 3% after deducting Betfair's cut.
MIN_EDGE: float = 0.05              # 5% post-commission edge minimum (raised from 3% → 5% for win rate target)
MIN_PROB: float = 0.54              # model probability minimum (raised from 0.52 → 0.54)
MAX_KELLY: float = 0.02             # FIX: allineato a money_management.py DEFAULT_MAX_STAKE_PCT=2%
KELLY_FRACTION: float = 0.10        # FIX: allineato a money_management.py DEFAULT_KELLY_FRACTION=0.10
DEFAULT_BANKROLL: float = 1000.0    # base bankroll for stake calculation

# Market-specific minimum probabilities (some markets need higher confidence)
MARKET_MIN_PROB: Dict[str, float] = {
    "target_1x2": 0.45,              # 3-way market needs lower threshold
    "target_btts": 0.55,
    "target_over_2_5": 0.55,
    "target_over_1_5": 0.60,
    "target_over_0_5": 0.65,         # almost always over 0.5, need high conf
    "target_over_3_5": 0.55,
    "target_over_4_5": 0.55,
    "target_ht_1x2": 0.45,
    "target_ft_1x2": 0.45,
    "target_clean_sheet_home": 0.55,
    "target_clean_sheet_away": 0.55,
    "target_home_over_0_5": 0.60,
    "target_away_over_0_5": 0.60,
    "target_home_over_1_5": 0.55,
    "target_away_over_1_5": 0.55,
    "target_first_goal_before_30": 0.55,
    "target_goal_in_2h": 0.55,
}

# ── Core Functions ──────────────────────────────────────────────────


def expected_value(
    model_prob: float,
    decimal_odds: float,
    commission: float = BETFAIR_COMMISSION,
) -> float:
    """
    Calculate Expected Value per 1 unit staked, net of Betfair commission.

    EV = (prob * (odds - 1) * (1 - commission)) - (1 - prob)

    The commission is deducted from the NET PROFIT on winning bets.
    A positive EV means profitable in the long run after Betfair's cut.

    Example: prob=0.55, odds=2.00, commission=5%
      EV = (0.55 * 1.0 * 0.95) - 0.45 = 0.5225 - 0.45 = +0.0725 (7.25% edge)
    """
    if decimal_odds <= 1.0 or model_prob <= 0.0 or model_prob >= 1.0:
        return -1.0
    net_profit_per_unit = (decimal_odds - 1.0) * (1.0 - commission)
    return (model_prob * net_profit_per_unit) - (1.0 - model_prob)


def implied_probability(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 1.0:
        return 1.0
    return 1.0 / decimal_odds


def kelly_criterion(
    model_prob: float,
    decimal_odds: float,
    fraction: float = KELLY_FRACTION,
    max_kelly: float = MAX_KELLY,
    commission: float = BETFAIR_COMMISSION,
) -> float:
    """
    Fractional Kelly Criterion with Betfair commission.

    Full Kelly (with commission): f* = (p * b_net - (1-p)) / b_net
    where b_net = (odds - 1) * (1 - commission) = net profit per unit staked

    The commission reduces the effective win amount, shrinking the Kelly
    fraction vs the naive formula.  This is the correct Kelly for exchange
    betting with per-win commission.

    We use fraction * f* (quarter-Kelly by default) to reduce variance.
    Capped at max_kelly to prevent over-betting on single events.
    """
    if decimal_odds <= 1.0 or model_prob <= 0.0 or model_prob >= 1.0:
        return 0.0

    # Net win per unit staked after commission
    b_net = (decimal_odds - 1.0) * (1.0 - commission)
    if b_net <= 0:
        return 0.0

    f_star = (model_prob * b_net - (1.0 - model_prob)) / b_net

    if f_star <= 0:
        return 0.0  # No bet — negative Kelly means no edge

    # Apply fractional Kelly and cap
    return min(fraction * f_star, max_kelly)


def evaluate_bet_opportunities(
    targets_probs: Dict[str, Dict[str, float]],
    odds_mapping: Dict[str, float],
    bankroll: float = DEFAULT_BANKROLL,
    min_edge: float = MIN_EDGE,
    min_prob: float = MIN_PROB,
) -> Tuple[List[BetSignal], List[Dict[str, str]]]:
    """
    Evaluate all predicted targets against available odds.

    Args:
        targets_probs: {target_name: {class_label: probability}}
        odds_mapping: {target_class_key: decimal_odds}
            e.g. {"target_1x2_H": 2.10, "target_btts_True": 1.85, ...}
        bankroll: current bankroll for stake calculation
        min_edge: minimum acceptable EV
        min_prob: minimum model probability

    Returns:
        (bet_signals, no_bet_reasons)
    """
    bet_signals: List[BetSignal] = []
    no_bet_reasons: List[Dict[str, str]] = []

    for target, probs in targets_probs.items():
        if not probs:
            continue

        market_min = MARKET_MIN_PROB.get(target, min_prob)
        target_has_signal = False

        # Evaluate ALL classes with sufficient probability — not just the
        # best class.  For 1X2 markets, the Draw can have value even when
        # it is not the most probable outcome.
        for cls, cls_prob in probs.items():
            cls_prob = float(cls_prob)
            if cls_prob < 0.15:
                continue  # skip negligible classes

            odds_key = f"{target}_{cls}"
            if odds_key not in odds_mapping:
                continue

            decimal_odds = odds_mapping[odds_key]
            if decimal_odds <= 1.0:
                continue

            ev = expected_value(cls_prob, decimal_odds)
            impl_prob = implied_probability(decimal_odds)
            edge = cls_prob - impl_prob

            if ev < min_edge:
                continue

            if edge <= 0:
                continue  # nessun edge positivo → non scommettere

            if cls_prob < market_min:
                continue

            # ML Score tier filter: score = edge × √prob
            # Filtra segnali deboli in base alla fascia di quota.
            ml_score = edge * math.sqrt(cls_prob)
            min_score_for_odds = ML_SCORE_TIERS[-1][1]  # fallback: ultimo tier
            for _max_odds, _min_score in ML_SCORE_TIERS:
                if decimal_odds < _max_odds:
                    min_score_for_odds = _min_score
                    break
            if ml_score < min_score_for_odds:
                continue

            kelly = kelly_criterion(cls_prob, decimal_odds)
            kelly_stake = round(kelly * bankroll, 2)

            if cls_prob >= 0.70 and ev >= 0.10:
                grade = "high"
            elif cls_prob >= 0.55 and ev >= 0.05:
                grade = "medium"
            else:
                grade = "low"

            bet_signals.append(BetSignal(
                market=target,
                action=cls,
                model_prob=round(cls_prob, 4),
                implied_prob=round(impl_prob, 4),
                decimal_odds=decimal_odds,
                expected_value=round(ev, 4),
                kelly_fraction=round(kelly, 6),
                kelly_stake=kelly_stake,
                confidence_grade=grade,
                edge=round(edge, 4),
                ml_score=round(ml_score, 5),
            ))
            target_has_signal = True

        if not target_has_signal:
            best_class = max(probs, key=probs.get)  # type: ignore
            best_prob = float(probs[best_class])
            odds_key = f"{target}_{best_class}"
            if odds_key not in odds_mapping:
                no_bet_reasons.append({
                    "target": target,
                    "reason": "no odds available",
                })
            elif best_prob < market_min:
                no_bet_reasons.append({
                    "target": target,
                    "reason": f"prob {best_prob:.3f} < min {market_min:.2f}",
                })
            else:
                impl = implied_probability(odds_mapping.get(odds_key, 1.0))
                no_bet_reasons.append({
                    "target": target,
                    "reason": f"no class with positive EV (best: {best_class} "
                              f"prob={best_prob:.3f}, implied={impl:.3f})",
                })

    # Sort by EV descending
    bet_signals.sort(key=lambda s: s.expected_value, reverse=True)

    return bet_signals, no_bet_reasons


def _find_betfair_bookmaker(raw_odds: dict) -> Optional[dict]:
    """Find Betfair sportsbook bookmaker from raw_json_odds.
    Strategy: name match → index 2 (bookmaker #3 in API-Football) → index 0.
    Betfair sportsbook is used for edge calculation. Exchange odds are higher,
    so any edge on sportsbook is amplified when betting on the exchange.
    """
    bookmakers = raw_odds.get("bookmakers", []) or []
    if not bookmakers:
        return None
    for bm in bookmakers:
        if "betfair" in str(bm.get("name", "")).lower():
            return bm
    if len(bookmakers) > 2:
        return bookmakers[2]
    return bookmakers[0]


def build_odds_mapping(
    raw_odds: dict,
    targets_probs: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """
    Build a flat {target_class_key: decimal_odds} mapping from raw_json_odds.

    Uses Betfair sportsbook odds specifically (bookmaker #3 in API-Football).
    Edge calculated on sportsbook is amplified on the exchange.
    """
    if not isinstance(raw_odds, dict):
        return {}

    # Use Betfair sportsbook bookmaker only
    market_odds: Dict[str, Dict[str, List[float]]] = {}
    _bf_bm = _find_betfair_bookmaker(raw_odds)
    for bm in ([_bf_bm] if _bf_bm else []):
        for bet in bm.get("bets", []) or []:
            bet_name = str(bet.get("name", "")).strip()
            for v in bet.get("values", []) or []:
                val_name = str(v.get("value", "")).strip()
                try:
                    odd = float(v.get("odd", 0))
                except (TypeError, ValueError):
                    continue
                if odd <= 1.0:
                    continue
                if bet_name not in market_odds:
                    market_odds[bet_name] = {}
                if val_name not in market_odds[bet_name]:
                    market_odds[bet_name][val_name] = []
                market_odds[bet_name][val_name].append(odd)

    # Map to our target names
    mapping: Dict[str, float] = {}

    # 1X2 / Match Winner
    for name in ["Match Winner", "1X2", "Fulltime Result"]:
        if name in market_odds:
            m = market_odds[name]
            if "Home" in m:
                mapping["target_1x2_H"] = max(m["Home"])
            if "Draw" in m:
                mapping["target_1x2_D"] = max(m["Draw"])
            if "Away" in m:
                mapping["target_1x2_A"] = max(m["Away"])
            break

    # Over/Under 2.5
    for name in ["Goals Over/Under", "Over/Under", "Goals Over Under"]:
        if name in market_odds:
            m = market_odds[name]
            for val_name, odds_list in m.items():
                if "over" in val_name.lower() and "2.5" in val_name:
                    mapping["target_over_2_5_True"] = max(odds_list)
                elif "under" in val_name.lower() and "2.5" in val_name:
                    mapping["target_over_2_5_False"] = max(odds_list)
                elif "over" in val_name.lower() and "1.5" in val_name:
                    mapping["target_over_1_5_True"] = max(odds_list)
                elif "under" in val_name.lower() and "1.5" in val_name:
                    mapping["target_over_1_5_False"] = max(odds_list)
                elif "over" in val_name.lower() and "3.5" in val_name:
                    mapping["target_over_3_5_True"] = max(odds_list)
                elif "under" in val_name.lower() and "3.5" in val_name:
                    mapping["target_over_3_5_False"] = max(odds_list)
                elif "over" in val_name.lower() and "0.5" in val_name:
                    mapping["target_over_0_5_True"] = max(odds_list)
                elif "under" in val_name.lower() and "0.5" in val_name:
                    mapping["target_over_0_5_False"] = max(odds_list)
                elif "over" in val_name.lower() and "4.5" in val_name:
                    mapping["target_over_4_5_True"] = max(odds_list)
                elif "under" in val_name.lower() and "4.5" in val_name:
                    mapping["target_over_4_5_False"] = max(odds_list)
            break

    # BTTS
    for name in ["Both Teams Score", "BTTS", "Both Teams to Score"]:
        if name in market_odds:
            m = market_odds[name]
            if "Yes" in m:
                mapping["target_btts_True"] = max(m["Yes"])
            if "No" in m:
                mapping["target_btts_False"] = max(m["No"])
            break

    # HT 1X2
    for name in ["First Half Winner", "HT 1X2"]:
        if name in market_odds:
            m = market_odds[name]
            if "Home" in m:
                mapping["target_ht_1x2_H"] = max(m["Home"])
            if "Draw" in m:
                mapping["target_ht_1x2_D"] = max(m["Draw"])
            if "Away" in m:
                mapping["target_ht_1x2_A"] = max(m["Away"])
            break

    return mapping
