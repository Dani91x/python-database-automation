"""
Dixon-Coles model (point-in-time safe).

Stima forze attacco/difesa + vantaggio campo via regressione di Poisson
(sklearn PoissonRegressor) con time-decay weighting, poi applica la correzione
Dixon-Coles tau sulle 4 celle a basso punteggio per costruire la matrice dei
punteggi e i mercati derivati (1X2, Over/Under, BTTS).

Tutte le funzioni ricevono SOLO partite passate (date < ref_date): nessun leak.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor


@dataclass
class DCModel:
    teams: list
    attack: dict      # team_id -> log attack coef
    defense: dict     # team_id -> log defense coef
    home_adv: float   # log home advantage
    intercept: float
    rho: float
    league_home_avg: float
    league_away_avg: float


def fit_dc(past: pd.DataFrame, ref_date: pd.Timestamp,
           half_life_days: float = 180.0, l2_alpha: float = 1e-4,
           rho: float = -0.13, max_teams_lookback: int | None = None) -> DCModel | None:
    """
    Fit team strengths su partite con fixture_date < ref_date.
    past deve avere: home_team_id, away_team_id, goals_home, goals_away, fixture_date.
    """
    if past is None or len(past) < 40:
        return None
    teams = sorted(set(past["home_team_id"]) | set(past["away_team_id"]))
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    if n < 4:
        return None

    # design "long": 2 righe per match (prospettiva attaccante)
    age_days = (ref_date - past["fixture_date"]).dt.total_seconds().values / 86400.0
    w = np.exp(-np.log(2) * age_days / half_life_days)  # half-life decay

    rows_X = []
    rows_y = []
    rows_w = []
    hi = past["home_team_id"].map(tidx).values
    ai = past["away_team_id"].map(tidx).values
    gh = past["goals_home"].values.astype(float)
    ga = past["goals_away"].values.astype(float)
    # feature layout: [attack(n)] + [defense(n)] + [home(1)]
    for k in range(len(past)):
        # home attacking vs away defending, is_home=1
        xh = np.zeros(2 * n + 1)
        xh[hi[k]] = 1.0
        xh[n + ai[k]] = 1.0
        xh[2 * n] = 1.0
        rows_X.append(xh); rows_y.append(gh[k]); rows_w.append(w[k])
        # away attacking vs home defending, is_home=0
        xa = np.zeros(2 * n + 1)
        xa[ai[k]] = 1.0
        xa[n + hi[k]] = 1.0
        rows_X.append(xa); rows_y.append(ga[k]); rows_w.append(w[k])

    X = np.asarray(rows_X)
    y = np.asarray(rows_y)
    sw = np.asarray(rows_w)

    model = PoissonRegressor(alpha=l2_alpha, max_iter=500, fit_intercept=True)
    try:
        model.fit(X, y, sample_weight=sw)
    except Exception:
        return None

    coef = model.coef_
    attack = {t: float(coef[tidx[t]]) for t in teams}
    defense = {t: float(coef[n + tidx[t]]) for t in teams}
    home_adv = float(coef[2 * n])
    intercept = float(model.intercept_)

    # medie di lega (per riferimento / fallback)
    lh = float(np.average(gh, weights=w)) if len(gh) else 1.4
    la = float(np.average(ga, weights=w)) if len(ga) else 1.1

    return DCModel(teams, attack, defense, home_adv, intercept, rho, lh, la)


def predict_lambdas(m: DCModel, home_id: int, away_id: int) -> tuple[float, float] | None:
    """Lambda attesi. None se una squadra non è nel modello (no storico)."""
    if home_id not in m.attack or away_id not in m.attack:
        return None
    log_lh = m.intercept + m.attack[home_id] + m.defense[away_id] + m.home_adv
    log_la = m.intercept + m.attack[away_id] + m.defense[home_id]
    lh = math.exp(min(log_lh, 2.5))   # cap log per stabilità (λ<~12)
    la = math.exp(min(log_la, 2.5))
    return max(0.05, lh), max(0.05, la)


def _pois(lmbda: float, k: int) -> float:
    return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)


def _dc_tau(hg: int, ag: int, lh: float, la: float, rho: float) -> float:
    if hg == 0 and ag == 0:
        return 1.0 - lh * la * rho
    if hg == 1 and ag == 0:
        return max(1e-6, 1.0 + la * rho)
    if hg == 0 and ag == 1:
        return max(1e-6, 1.0 + lh * rho)
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lh: float, la: float, rho: float = -0.13, max_goals: int = 10) -> np.ndarray:
    ph = np.array([_pois(lh, i) for i in range(max_goals + 1)])
    pa = np.array([_pois(la, j) for j in range(max_goals + 1)])
    M = np.outer(ph, pa)
    # correzione DC sulle 4 celle basse
    for hg, ag in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        M[hg, ag] *= _dc_tau(hg, ag, lh, la, rho)
    M /= M.sum()
    return M


def markets_from_matrix(M: np.ndarray) -> dict:
    """Probabilità dei mercati principali dalla matrice dei punteggi."""
    n = M.shape[0]
    idx = np.arange(n)
    H = float(M[np.greater.outer(idx, idx)].sum())
    D = float(np.trace(M))
    A = float(M[np.less.outer(idx, idx)].sum())
    tot = np.add.outer(idx, idx)
    over25 = float(M[tot >= 3].sum())
    over15 = float(M[tot >= 2].sum())
    over35 = float(M[tot >= 4].sum())
    btts = float(M[1:, 1:].sum())
    return {
        "H": H, "D": D, "A": A,
        "O25": over25, "U25": 1 - over25,
        "O15": over15, "U15": 1 - over15,
        "O35": over35, "U35": 1 - over35,
        "BTTS": btts, "BTTS_NO": 1 - btts,
    }


def predict_markets(m: DCModel, home_id: int, away_id: int) -> dict | None:
    lam = predict_lambdas(m, home_id, away_id)
    if lam is None:
        return None
    lh, la = lam
    M = score_matrix(lh, la, m.rho)
    out = markets_from_matrix(M)
    out["lambda_home"] = lh
    out["lambda_away"] = la
    return out
