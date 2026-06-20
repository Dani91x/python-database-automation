"""Certificazione matematica del motore tactical_engine.

Eseguibile con pytest oppure direttamente:  python tactical_engine/tests/test_math.py
Copre: pmf Poisson, correzione DC, normalizzazione griglia, coerenza mercati,
riduzione al Poisson indipendente (rho=0), e RECUPERO di forze sintetiche note
via massima verosimiglianza (prova che il fit inferisce correttamente).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tactical_engine.dixon_coles import (  # noqa: E402
    poisson_pmf, dc_tau, score_matrix, markets_from_matrix,
    expected_goals, MatchScoreline,
)
from tactical_engine.model import DixonColesModel  # noqa: E402

TOL = 1e-9


def test_poisson_pmf():
    # P(0; lambda)=e^-lambda ; P(k;1)=e^-1/k!
    assert abs(poisson_pmf(2.0, 0) - math.exp(-2.0)) < TOL
    assert abs(poisson_pmf(1.0, 1) - math.exp(-1.0)) < TOL
    assert abs(poisson_pmf(3.0, 2) - (math.exp(-3.0) * 9 / 2)) < 1e-12
    # somma su k -> 1
    assert abs(sum(poisson_pmf(2.3, k) for k in range(40)) - 1.0) < 1e-9


def test_dc_tau_corners():
    lh, la, rho = 1.5, 1.2, 0.1
    assert abs(dc_tau(0, 0, lh, la, rho) - (1 - lh * la * rho)) < TOL
    assert abs(dc_tau(0, 1, lh, la, rho) - (1 + lh * rho)) < TOL
    assert abs(dc_tau(1, 0, lh, la, rho) - (1 + la * rho)) < TOL
    assert abs(dc_tau(1, 1, lh, la, rho) - (1 - rho)) < TOL
    assert dc_tau(2, 3, lh, la, rho) == 1.0  # nessuna correzione altrove
    # rho=0 -> tau identicamente 1
    for x in range(3):
        for y in range(3):
            assert dc_tau(x, y, lh, la, 0.0) == 1.0


def test_score_matrix_normalized():
    grid = score_matrix(1.7, 1.1, -0.05, max_goals=10)
    assert grid.shape == (11, 11)
    assert np.all(grid >= 0)
    assert abs(grid.sum() - 1.0) < 1e-12


def test_markets_coherence():
    grid = score_matrix(1.4, 1.0, 0.08, max_goals=12)
    m = markets_from_matrix(grid)
    assert abs(m["home"] + m["draw"] + m["away"] - 1.0) < 1e-9
    assert abs(m["over_2_5"] + m["under_2_5"] - 1.0) < 1e-9
    assert abs(m["over_1_5"] + m["under_1_5"] - 1.0) < 1e-9
    assert abs(m["btts_yes"] + m["btts_no"] - 1.0) < 1e-9
    assert abs(m["double_1x"] - (m["home"] + m["draw"])) < 1e-9
    assert abs(m["double_12"] - (m["home"] + m["away"])) < 1e-9
    # monotonia: Over 0.5 >= Over 1.5 >= Over 2.5 >= Over 3.5
    assert m["over_0_5"] >= m["over_1_5"] >= m["over_2_5"] >= m["over_3_5"]
    for v in m.values():
        assert -1e-9 <= v <= 1 + 1e-9


def test_reduces_to_independent_poisson():
    # con rho=0 la griglia e' il prodotto esterno dei due Poisson:
    lh, la = 1.6, 0.9
    grid = score_matrix(lh, la, 0.0, max_goals=15)
    # P(0-0) = e^-lh * e^-la  (a meno della rinormalizzazione di coda, trascurabile)
    assert abs(grid[0, 0] - poisson_pmf(lh, 0) * poisson_pmf(la, 0)) < 1e-4
    exg = expected_goals(grid)
    assert abs(exg[0] - lh) < 1e-3 and abs(exg[1] - la) < 1e-3


def _simulate(rng, teams, attack, defense, const, gamma, rho, games_per_pair, max_goals=10):
    matches = []
    flat_cache = {}
    for hi, h in enumerate(teams):
        for ai, a in enumerate(teams):
            if h == a:
                continue
            lh = math.exp(const + attack[hi] - defense[ai] + gamma)
            la = math.exp(const + attack[ai] - defense[hi])
            key = (round(lh, 6), round(la, 6))
            if key not in flat_cache:
                grid = score_matrix(lh, la, rho, max_goals)
                flat_cache[key] = (grid.ravel(), grid.shape[1])
            probs, ncol = flat_cache[key]
            for _ in range(games_per_pair):
                k = rng.choice(len(probs), p=probs)
                matches.append(MatchScoreline(h, a, int(k // ncol), int(k % ncol)))
    return matches


def test_recovery_synthetic():
    """Genera partite da forze NOTE e verifica che il fit le recuperi."""
    rng = np.random.default_rng(42)
    n = 18
    teams = list(range(1, n + 1))
    attack = rng.normal(0, 0.35, n); attack -= attack.mean()
    defense = rng.normal(0, 0.30, n); defense -= defense.mean()
    const, gamma, rho = 0.0, 0.26, -0.04

    matches = _simulate(rng, teams, attack, defense, const, gamma, rho, games_per_pair=12)
    model = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=0.001)
    fit = model.fit(matches, dates=None, fit_home_adv=True)
    assert fit.converged

    order = {t: i for i, t in enumerate(fit.teams)}
    fa = np.array([fit.attack[order[t]] for t in teams])
    fd = np.array([fit.defense[order[t]] for t in teams])

    corr_att = float(np.corrcoef(fa, attack)[0, 1])
    corr_def = float(np.corrcoef(fd, defense)[0, 1])
    print(f"  recovery: corr_attack={corr_att:.3f} corr_defense={corr_def:.3f} "
          f"gamma={fit.home_adv:.3f}(true {gamma}) rho={fit.rho:.3f}(true {rho})")
    assert corr_att > 0.90, f"correlazione attacco troppo bassa: {corr_att}"
    assert corr_def > 0.90, f"correlazione difesa troppo bassa: {corr_def}"
    assert abs(fit.home_adv - gamma) < 0.08, f"gamma non recuperato: {fit.home_adv}"
    assert abs(fit.rho - rho) < 0.05, f"rho non recuperato: {fit.rho}"


def test_neutral_symmetry():
    """A campo neutro, scambiare le squadre scambia i lambda (equivarianza Z2)."""
    rng = np.random.default_rng(7)
    n = 10
    teams = list(range(1, n + 1))
    attack = rng.normal(0, 0.3, n); attack -= attack.mean()
    defense = rng.normal(0, 0.3, n); defense -= defense.mean()
    matches = _simulate(rng, teams, attack, defense, 0.0, 0.2, -0.03, games_per_pair=10)
    model = DixonColesModel(max_goals=10, half_life_days=0.0, ridge=0.01)
    model.fit(matches, dates=None, fit_home_adv=True)

    p_ab = model.predict(2, 5, neutral=True)
    p_ba = model.predict(5, 2, neutral=True)
    # lambda_home(A vs B) == lambda_away(B vs A) e viceversa
    assert abs(p_ab["lambda_home"] - p_ba["lambda_away"]) < 1e-9
    assert abs(p_ab["lambda_away"] - p_ba["lambda_home"]) < 1e-9
    # P(A batte B) neutro == P(B perde con A) neutro
    assert abs(p_ab["markets"]["home"] - p_ba["markets"]["away"]) < 1e-9


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"[OK ] {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"[ERR ] {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} test passati")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
