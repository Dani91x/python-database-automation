"""
Confidence Gates: 3-level filtering system that decides whether to bet.

A bet is only recommended if ALL three gates pass:
  1. Data Sufficiency  — enough features and match history
  2. Model Agreement   — ensemble models agree (consensus)
  3. Value Present     — positive expected value above threshold

If any gate fails, the signal is "NO BET" with an explanation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .value_betting import BetSignal


@dataclass
class GateResult:
    """Result of applying all confidence gates."""
    passed: bool
    gate_failed: Optional[str]  # which gate failed, if any
    reason: str
    details: Dict[str, Any]


# ── Thresholds ──────────────────────────────────────────────────────

MIN_COVERAGE_PCT: float = 0.50        # minimum feature coverage
MIN_MATCHES_PER_TEAM: int = 8         # minimum historical matches
MIN_AGREEMENT_RATIO: float = 0.66     # at least 2/3 models must agree
MIN_RELIABILITY_SCORE: float = 0.40   # from reliability calculation


def gate_data_sufficiency(
    coverage_pct: float,
    matches_home: int,
    matches_away: int,
    reliability_score: float = 0.0,
) -> GateResult:
    """
    Gate 1: Check if we have enough data to make reliable predictions.

    Fails if:
    - Feature coverage is below 50%
    - Either team has fewer than 8 historical matches
    - Reliability score is below 0.40
    """
    details = {
        "coverage_pct": round(coverage_pct, 3),
        "matches_home": matches_home,
        "matches_away": matches_away,
        "reliability_score": round(reliability_score, 3),
    }

    if coverage_pct < MIN_COVERAGE_PCT:
        return GateResult(
            passed=False,
            gate_failed="data_sufficiency",
            reason=f"Coverage {coverage_pct:.1%} < {MIN_COVERAGE_PCT:.0%} minimum",
            details=details,
        )

    min_matches = min(matches_home, matches_away)
    if min_matches < MIN_MATCHES_PER_TEAM:
        return GateResult(
            passed=False,
            gate_failed="data_sufficiency",
            reason=f"Only {min_matches} matches for one team (need {MIN_MATCHES_PER_TEAM}+)",
            details=details,
        )

    if reliability_score < MIN_RELIABILITY_SCORE:
        return GateResult(
            passed=False,
            gate_failed="data_sufficiency",
            reason=f"Reliability {reliability_score:.2f} < {MIN_RELIABILITY_SCORE:.2f} minimum",
            details=details,
        )

    return GateResult(
        passed=True,
        gate_failed=None,
        reason="Data sufficiency OK",
        details=details,
    )


def gate_model_agreement(
    agreement_ratio: float,
    votes: Dict[str, str],
) -> GateResult:
    """
    Gate 2: Check if ensemble models agree on the prediction.

    Fails if:
    - Less than 2/3 of base models predict the same class
    """
    details = {
        "agreement_ratio": round(agreement_ratio, 3),
        "votes": votes,
    }

    if agreement_ratio < MIN_AGREEMENT_RATIO:
        return GateResult(
            passed=False,
            gate_failed="model_agreement",
            reason=f"Models disagree: agreement {agreement_ratio:.0%} < {MIN_AGREEMENT_RATIO:.0%}",
            details=details,
        )

    return GateResult(
        passed=True,
        gate_failed=None,
        reason=f"Model agreement OK ({agreement_ratio:.0%})",
        details=details,
    )


def gate_value_present(
    bet_signal: Optional[BetSignal],
) -> GateResult:
    """
    Gate 3: Check if there's positive expected value.

    Fails if:
    - No bet signal generated (EV too low or odds unavailable)
    """
    if bet_signal is None:
        return GateResult(
            passed=False,
            gate_failed="value_present",
            reason="No positive EV found for this market",
            details={},
        )

    details = {
        "ev": bet_signal.expected_value,
        "model_prob": bet_signal.model_prob,
        "implied_prob": bet_signal.implied_prob,
        "edge": bet_signal.edge,
        "kelly_fraction": bet_signal.kelly_fraction,
    }

    if bet_signal.expected_value <= 0:
        return GateResult(
            passed=False,
            gate_failed="value_present",
            reason=f"Negative EV: {bet_signal.expected_value:.3f}",
            details=details,
        )

    return GateResult(
        passed=True,
        gate_failed=None,
        reason=f"Value present: EV={bet_signal.expected_value:.3f}, edge={bet_signal.edge:.3f}",
        details=details,
    )


def apply_all_gates(
    coverage_pct: float,
    matches_home: int,
    matches_away: int,
    reliability_score: float,
    agreement_ratio: float,
    votes: Dict[str, str],
    bet_signal: Optional[BetSignal],
) -> Tuple[bool, List[GateResult]]:
    """
    Apply all 3 gates sequentially.

    Returns (all_passed, list_of_gate_results).
    """
    gates = [
        gate_data_sufficiency(coverage_pct, matches_home, matches_away, reliability_score),
        gate_model_agreement(agreement_ratio, votes),
        gate_value_present(bet_signal),
    ]

    all_passed = all(g.passed for g in gates)
    return all_passed, gates


def summarize_gates(gates: List[GateResult]) -> Dict[str, Any]:
    """Convert gate results to a JSON-serializable summary."""
    return {
        "all_passed": all(g.passed for g in gates),
        "gates": [
            {
                "passed": g.passed,
                "gate_failed": g.gate_failed,
                "reason": g.reason,
            }
            for g in gates
        ],
    }
