from __future__ import annotations

from typing import Dict, List, Tuple


TARGET_TO_MARKET = {
    "target_1x2": "1X2",
    "target_btts": "BTTS",
    "target_over_0_5": "Over 0.5",
    "target_over_1_5": "Over 1.5",
    "target_over_2_5": "Over 2.5",
    "target_over_3_5": "Over 3.5",
    "target_over_4_5": "Over 4.5",
    "target_clean_sheet_home": "Home Clean Sheet",
    "target_clean_sheet_away": "Away Clean Sheet",
    "target_home_over_0_5": "Home Over 0.5",
    "target_home_over_1_5": "Home Over 1.5",
    "target_home_over_2_5": "Home Over 2.5",
    "target_away_over_0_5": "Away Over 0.5",
    "target_away_over_1_5": "Away Over 1.5",
    "target_away_over_2_5": "Away Over 2.5",
    "target_ht_1x2": "HT 1X2",
    "target_ft_1x2": "FT 1X2",
    "target_ht_ft": "HT/FT",
    "target_exact_score": "Exact Score",
    "target_corners_total": "Total Corners",
    "target_sot_total": "Total Shots on Target",
    "target_cards_total": "Total Cards",
    "target_home_cards": "Home Cards",
    "target_away_cards": "Away Cards",
}


def reliability_score(consensus_val: float | None, entropy_val: float | None) -> float:
    """
    Higher is better. Consensus in [0,1], entropy >= 0.
    We map to a 0..1-ish score.
    """
    if consensus_val is None:
        consensus_val = 0.0
    if entropy_val is None:
        entropy_val = 0.0
    # normalize entropy roughly by log2(3) for multi-class
    ent_norm = min(entropy_val / 1.6, 1.0)
    return max(0.0, min(1.0, (consensus_val * 0.7) + ((1.0 - ent_norm) * 0.3)))


def build_ranked_markets(row: Dict[str, float]) -> List[Tuple[str, float, str]]:
    ranked: List[Tuple[str, float, str]] = []
    for target, market in TARGET_TO_MARKET.items():
        consensus = row.get(f"{target}_consensus")
        entropy = row.get(f"{target}_entropy")
        label = row.get(f"{target}_ensemble")
        score = reliability_score(consensus, entropy)
        ranked.append((market, score, str(label) if label is not None else ""))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked

