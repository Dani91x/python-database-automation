"""Test dossier: hazard combinato (prudente) e risparmio atteso della copertura. ASCII-only."""
from __future__ import annotations

import pytest

from Betfair.mike import dossier as D


def test_combine_hazard_takes_the_most_prudent_source():
    assert D.combine_hazard(0.05, 0.03) == 0.05
    assert D.combine_hazard(0.05, 0.08) == 0.08
    assert D.combine_hazard(None, 0.04) == 0.04
    assert D.combine_hazard(0.04, None) == 0.04
    assert D.combine_hazard(None, None) is None
    # pressione (corner/cartellini) amplifica SOLO il modello, mai lo riduce
    assert D.combine_hazard(0.05, 0.05, pressure_mult=1.25) == pytest.approx(0.0625)
    assert D.combine_hazard(0.05, 0.05, pressure_mult=0.9) == 0.05


def test_cover_gain_pct_from_over_probabilities():
    # P(Over 4.5) 0.20 ora -> quota equa 5.0, X ∝ 1/4 ; fra 5' 0.17 -> quota 5.88, X ∝ 1/4.88
    g = D.cover_gain_pct(0.20, 0.17)
    assert g == pytest.approx((1 - (1 / 4.882) / (1 / 4.0)) * 100, abs=0.2)
    assert D.cover_gain_pct(0.20, 0.20) == 0.0
    assert D.cover_gain_pct(0.20, 0.25) == 0.0            # mai negativo: non "guadagno" aspettando
    assert D.cover_gain_pct(None, 0.2) is None and D.cover_gain_pct(0.2, None) is None


def test_live_frame_without_lambdas_is_fail_safe():
    out = D.live_frame({}, minute=10, score_home=0, score_away=0, atlas=None)
    assert out["hazard"] is None and out["p4_model"] is None and out["cover_gain_pct"] is None


def test_live_frame_with_lambdas_gives_model_hazard_and_gain():
    dossier = {"lambda_home": 1.4, "lambda_away": 1.1, "rho": -0.13, "league_id": None}
    out = D.live_frame(dossier, minute=5, score_home=0, score_away=0, atlas=None, wait_step_min=5)
    assert out["hazard_model"] is not None and 0.0 < out["hazard_model"] < 0.3
    assert out["hazard"] == out["hazard_model"]            # senza atlante comanda il modello
    assert out["p4_model"] is not None and 0.05 < out["p4_model"] < 0.25
    assert out["cover_gain_pct"] is not None and out["cover_gain_pct"] > 0.0
    # con l'Atlante piu' prudente del modello, vince l'Atlante
    out2 = D.live_frame(dossier, minute=5, score_home=0, score_away=0, atlas={"global": {}}, wait_step_min=5)
    assert out2["hazard"] is not None


def test_model_probs_three_scenarios_are_coherent():
    dossier = {"lambda_home": 1.4, "lambda_away": 1.1, "rho": -0.13, "league_id": None}
    out = D.live_frame(dossier, minute=30, score_home=0, score_away=0, atlas=None, wait_step_min=5)
    mp = out["model_probs"]
    assert mp is not None
    for k in ("u35", "o45", "u45"):
        for sc in ("now", "goal", "later"):
            assert 0.0 <= mp[f"{k}_{sc}"] <= 1.0
        assert mp[f"u45_{sc}"] == pytest.approx(1 - mp[f"o45_{sc}"], abs=1e-4)
    # un gol adesso abbassa l'Under 3.5 e alza l'Over 4.5; 5' senza gol fanno il contrario
    assert mp["u35_goal"] < mp["u35_now"] < mp["u35_later"]
    assert mp["o45_goal"] > mp["o45_now"] > mp["o45_later"]


def test_model_probs_from_grids_weights_home_and_away_goal():
    now = {(0, 0): 1.0}
    later = {(0, 0): 1.0}
    gh = {(4, 0): 1.0}      # gol casa -> 4 gol totali: Under 3.5 morto
    ga = {(1, 0): 1.0}      # gol trasferta -> 1 gol
    mp = D.model_probs_from_grids(now, later, gh, ga, w_home=0.25)
    assert mp["u35_now"] == 1.0 and mp["u35_goal"] == pytest.approx(0.75)
    assert mp["o45_goal"] == 0.0 and mp["u45_goal"] == 1.0


def test_live_frame_without_lambdas_has_no_model_probs():
    assert D.live_frame({}, minute=10, score_home=0, score_away=0, atlas=None)["model_probs"] is None
