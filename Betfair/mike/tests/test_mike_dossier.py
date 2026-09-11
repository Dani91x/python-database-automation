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


class _FakeEmp:
    """Tabella empirica finta: counts(league, ht) -> ({ft: n}, tot)."""

    def __init__(self, glob, league):
        self._g, self._l = glob, league
        self.empty = False

    def counts(self, league_id, ht):
        src = self._g if league_id is None or league_id == 0 else self._l
        rows = src.get(ht, {})
        return rows, sum(rows.values())


def test_p_total_from_grid_is_normalised_and_matches_p4():
    grid = {(0, 0): 0.1, (1, 1): 0.3, (2, 2): 0.2, (3, 2): 0.25, (5, 4): 0.15}
    pt = D.p_total_from_grid(grid)
    assert sum(pt.values()) == pytest.approx(1.0)
    assert pt[4] == pytest.approx(0.2) and pt[8] == pytest.approx(0.15)   # 9 gol -> bucket 8+
    assert pt[4] == pytest.approx(D._p_total(grid, 4))


def test_p_total_empirical_shrinks_league_towards_global():
    glob = {(1, 1): {"1-1": 200, "2-1": 150, "2-2": 100, "3-0": 30, "3-2": 20}}   # tot 500: P(4)=0.20
    league = {(1, 1): {"2-2": 40, "1-1": 10}}                                       # tot 50: P(4)=0.80
    t = _FakeEmp(glob, league)
    g = D.p_total_empirical(t, (1, 1), None, min_n=200)
    assert g[2] == pytest.approx(0.40) and g[4] == pytest.approx(0.20) and sum(g.values()) == pytest.approx(1.0)
    l = D.p_total_empirical(t, (1, 1), 7, min_n=200, shrink_k=50.0)
    assert l[4] == pytest.approx(0.5 * 0.80 + 0.5 * 0.20)      # w = 50/(50+50)
    assert D.p_total_empirical(t, (1, 1), None, min_n=1000) is None        # 1T troppo raro
    assert D.p_total_empirical(None, (1, 1), None) is None


def test_live_frame_uses_empirical_only_while_score_is_the_ht_score():
    glob = {(1, 1): {"1-1": 200, "2-1": 150, "2-2": 100, "3-0": 30, "3-2": 20}}
    t = _FakeEmp(glob, {})
    dossier = {"lambda_home": 1.4, "lambda_away": 1.1, "rho": -0.13, "league_id": None}
    out = D.live_frame(dossier, minute=46, score_home=1, score_away=1, atlas=None, ht_score=(1, 1), empirical=t)
    assert out["p_total_emp"] is not None and out["p_total_emp"][4] == pytest.approx(0.20)
    assert out["p_total_model"] is not None and sum(out["p_total_model"].values()) == pytest.approx(1.0, abs=1e-4)
    # gol nel 2T: il punteggio non e' piu' quello dell'intervallo -> l'empirico tace, il modello parla
    out2 = D.live_frame(dossier, minute=60, score_home=2, score_away=1, atlas=None, ht_score=(1, 1), empirical=t)
    assert out2["p_total_emp"] is None and out2["p_total_model"] is not None


def test_get_empirical_caches_and_retries_on_failure():
    class Db:
        calls = 0

        def ht_ft_rows(self, league_id):
            self.calls += 1
            if league_id == 9:
                return None                        # errore RPC
            return [{"league_id": None, "ht": "1-1", "ft": "2-2", "n": 300}]

    D._EMPIRICAL_CACHE.clear()
    D._EMPIRICAL_FAILED.clear()
    db = Db()
    t = D.get_empirical(None, db, now_ts=1000.0)
    assert t is not None and D.get_empirical(None, db, now_ts=1001.0) is t and db.calls == 1
    assert D.get_empirical(9, db, now_ts=1000.0) is None
    assert D.get_empirical(9, db, now_ts=1010.0) is None and db.calls == 2      # non ritenta subito
    assert D.get_empirical(9, db, now_ts=1000.0 + D._EMPIRICAL_RETRY_S + 1) is None and db.calls == 3
    D._EMPIRICAL_CACHE.clear()
    D._EMPIRICAL_FAILED.clear()
