"""Test del modello Poisson in-play."""
from __future__ import annotations

from Betfair.stream.engine.live_engine import (
    compute_inplay_probs,
    direction,
    estimate_prematch_lambdas,
    game_state_multipliers,
    implied_prob,
    inplay_residual_rates,
    red_card_multipliers,
    remaining_fraction,
    residual_time_weight,
)


def test_remaining_fraction_clamped():
    assert remaining_fraction(0) == 1.0
    assert remaining_fraction(90) == 0.0
    assert remaining_fraction(95) == 0.0  # recupero → 0, mai negativo
    assert abs(remaining_fraction(45) - 0.5) < 1e-9
    assert remaining_fraction(None) == 1.0


def test_probs_sum_to_one():
    p = compute_inplay_probs(0, 0, 0, 1.4, 1.2)
    assert abs((p.home + p.draw + p.away) - 1.0) < 1e-6
    for ln in p.over:
        assert abs((p.over[ln] + p.under[ln]) - 1.0) < 1e-6
    assert abs((p.btts_yes + p.btts_no) - 1.0) < 1e-6


def test_late_lead_is_strong_favourite():
    # 1-0 all'85': la casa deve essere nettamente favorita vs inizio 0-0
    start = compute_inplay_probs(0, 0, 0, 1.3, 1.3)
    late = compute_inplay_probs(1, 0, 85, 1.3, 1.3)
    assert late.home > start.home
    assert late.home > 0.8  # quasi certa con poco tempo residuo


def test_over_decreases_as_time_passes_without_goals():
    early = compute_inplay_probs(0, 0, 10, 1.5, 1.5)
    late = compute_inplay_probs(0, 0, 80, 1.5, 1.5)
    # con 0-0 e poco tempo, P(Over 2.5) crolla
    assert late.over[2.5] < early.over[2.5]


def test_already_over_line_is_certain():
    # 2-1 = 3 gol → Over 2.5 già avvenuto, prob = 1
    p = compute_inplay_probs(2, 1, 70, 1.0, 1.0)
    assert abs(p.over[2.5] - 1.0) < 1e-9
    assert abs(p.under[2.5] - 0.0) < 1e-9


def test_implied_and_direction():
    assert implied_prob(2.0) == 0.5
    assert implied_prob(None) is None
    assert implied_prob(1.0) is None
    # modello 0.6 vs mercato implicito 0.5 (quota 2.0) → edge +0.1 → BACK
    assert direction(0.6, 2.0, min_edge=0.03) == "BACK"
    assert direction(0.4, 2.0, min_edge=0.03) == "LAY"
    assert direction(0.51, 2.0, min_edge=0.03) == "NEUTRAL"


def test_estimate_lambdas_reasonable():
    lam_h, lam_a = estimate_prematch_lambdas(0.5, 0.3, expected_total_goals=2.6)
    assert lam_h > lam_a  # casa più forte → più gol attesi
    assert 0.2 <= lam_a
    assert abs((lam_h + lam_a) - 2.6) < 1e-9
