"""
Value Betting module: Expected Value (EV), Kelly Criterion staking,
and bet signal generation.

This is the core engine for deciding WHAT to bet and HOW MUCH.
Without positive expected value, no bet should be placed regardless
of model confidence.
"""
from __future__ import annotations

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


# ── Configuration ───────────────────────────────────────────────────

# Minimum EV (expected profit per 1 unit wagered) to recommend a bet
MIN_EDGE: float = 0.03              # 3% edge minimum
MIN_PROB: float = 0.52              # model probability minimum
MAX_KELLY: float = 0.05             # never stake more than 5% of bankroll
KELLY_FRACTION: float = 0.25        # quarter-Kelly (reduces variance)
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


def expected_value(model_prob: float, decimal_odds: float) -> float:
    """
    Calculate Expected Value per 1 unit staked.

    EV = (prob * (odds - 1)) - (1 - prob)

    Positive EV means profitable in the long run.
    """
    if decimal_odds <= 1.0 or model_prob <= 0.0 or model_prob >= 1.0:
        return -1.0
    return (model_prob * (decimal_odds - 1.0)) - (1.0 - model_prob)


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
) -> float:
    """
    Fractional Kelly Criterion.

    Full Kelly: f* = (p * (b + 1) - 1) / b
    where p = model probability, b = odds - 1

    We use fraction * f* (quarter-Kelly by default) to reduce variance.
    Capped at max_kelly to prevent over-betting on single events.
    """
    if decimal_odds <= 1.0 or model_prob <= 0.0 or model_prob >= 1.0:
        return 0.0

    b = decimal_odds - 1.0
    f_star = (model_prob * (b + 1.0) - 1.0) / b

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

        # Get best predicted class
        best_class = max(probs, key=probs.get)  # type: ignore
        best_prob = float(probs[best_class])

        # Check minimum probability
        market_min = MARKET_MIN_PROB.get(target, min_prob)
        if best_prob < market_min:
            no_bet_reasons.append({
                "target": target,
                "reason": f"prob {best_prob:.3f} < min {market_min:.2f}",
            })
            continue

        # Look for odds for this target+class
        odds_key = f"{target}_{best_class}"
        if odds_key not in odds_mapping:
            # Try alternative keys
            for key, odds_val in odds_mapping.items():
                if key.startswith(target):
                    odds_key = key
                    break
            else:
                no_bet_reasons.append({
                    "target": target,
                    "reason": "no odds available",
                })
                continue

        decimal_odds = odds_mapping[odds_key]
        if decimal_odds <= 1.0:
            no_bet_reasons.append({
                "target": target,
                "reason": f"invalid odds {decimal_odds}",
            })
            continue

        ev = expected_value(best_prob, decimal_odds)
        impl_prob = implied_probability(decimal_odds)
        edge = best_prob - impl_prob

        if ev < min_edge:
            no_bet_reasons.append({
                "target": target,
                "reason": f"EV {ev:.3f} < min_edge {min_edge:.3f} "
                          f"(model={best_prob:.3f}, implied={impl_prob:.3f})",
            })
            continue

        kelly = kelly_criterion(best_prob, decimal_odds)
        kelly_stake = round(kelly * bankroll, 2)

        # Confidence grade
        if best_prob >= 0.70 and ev >= 0.10:
            grade = "high"
        elif best_prob >= 0.55 and ev >= 0.05:
            grade = "medium"
        else:
            grade = "low"

        bet_signals.append(BetSignal(
            market=target,
            action=best_class,
            model_prob=round(best_prob, 4),
            implied_prob=round(impl_prob, 4),
            decimal_odds=decimal_odds,
            expected_value=round(ev, 4),
            kelly_fraction=round(kelly, 6),
            kelly_stake=kelly_stake,
            confidence_grade=grade,
            edge=round(edge, 4),
        ))

    # Sort by EV descending
    bet_signals.sort(key=lambda s: s.expected_value, reverse=True)

    return bet_signals, no_bet_reasons


def build_odds_mapping(
    raw_odds: dict,
    targets_probs: Dict[str, Dict[str, float]],
) -> Dict[str, float]:
    """
    Build a flat {target_class_key: decimal_odds} mapping from raw_json_odds.

    Maps bookmaker market names to our target names and extracts
    the best (highest) odds for each outcome.
    """
    if not isinstance(raw_odds, dict):
        return {}

    # Extract all odds by market name
    market_odds: Dict[str, Dict[str, List[float]]] = {}
    for bm in raw_odds.get("bookmakers", []) or []:
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
