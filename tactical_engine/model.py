"""DixonColesModel - forze attacco/difesa INFERITE per massima verosimiglianza.

Differenza chiave dal motore Poisson esistente (che usa medie mobili per squadra
isolata): qui le forze sono stimate CONGIUNTAMENTE su tutte le partite, quindi
tengono conto della forza degli avversari affrontati (strength-of-schedule).

Simmetria casa/trasferta (Z2) STRUTTURALE: una sola coppia (attack_i, defense_i)
per squadra, valida su entrambi i lati, + un UNICO vantaggio-campo gamma condiviso.
Predizione a campo neutro = gamma azzerato (per definizione simmetrica/equivariante:
scambiando le due squadre, i lambda si scambiano).

Ridge L2 su attack/defense: (1) risolve l'indeterminatezza di livello (mean->0),
(2) e' lo shrinkage verso la media-lega che evita l'overfit con poche partite.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from .dixon_coles import (
    MatchScoreline, score_matrix, markets_from_matrix,
    top_correct_scores, expected_goals,
)

LN2 = log(2.0)


@dataclass(frozen=True)
class FitResult:
    teams: List[int]
    attack: np.ndarray      # log-attacco centrato (mean~0)
    defense: np.ndarray     # log-difesa centrato (mean~0, alto = difesa solida)
    const: float            # livello base di scoring (log)
    home_adv: float         # vantaggio campo (log); ~0 atteso a campo neutro
    rho: float              # correzione Dixon-Coles
    n_matches: int
    eff_matches: float      # somma dei pesi time-decay (n "effettivo")
    converged: bool
    neg_loglik: float


class DixonColesModel:
    def __init__(self, max_goals: int = 10, half_life_days: float = 1800.0,
                 ridge: float = 0.05):
        self.max_goals = int(max_goals)
        self.half_life_days = float(half_life_days)
        self.ridge = float(ridge)
        self.fit_: Optional[FitResult] = None
        self._idx: Dict[int, int] = {}

    # ---------- pesi time-decay ----------
    def _weights(self, days_ago: np.ndarray) -> np.ndarray:
        if self.half_life_days <= 0:
            return np.ones_like(days_ago, dtype=float)
        xi = LN2 / self.half_life_days
        return np.exp(-xi * np.clip(days_ago, 0, None))

    # ---------- fit ----------
    def fit(self, matches: Sequence[MatchScoreline],
            dates: Optional[Sequence[datetime]] = None,
            ref_date: Optional[datetime] = None,
            fit_home_adv: bool = True) -> FitResult:
        if not matches:
            raise ValueError("nessuna partita per il fit")

        teams = sorted({m.home_id for m in matches} | {m.away_id for m in matches})
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        h = np.array([idx[m.home_id] for m in matches])
        a = np.array([idx[m.away_id] for m in matches])
        x = np.array([m.home_goals for m in matches], dtype=int)
        y = np.array([m.away_goals for m in matches], dtype=int)

        # pesi: time-decay se ho le date, altrimenti i pesi gia' nelle scoreline
        if dates is not None:
            ref = ref_date or max(dates)
            days = np.array([(ref - d).total_seconds() / 86400.0 for d in dates])
            w = self._weights(days)
        else:
            w = np.array([m.weight for m in matches], dtype=float)
        eff = float(w.sum())

        # vettore parametri: [attack(n), defense(n), const, gamma, rho]
        p0 = np.concatenate([np.zeros(n), np.zeros(n), [0.0, 0.1 if fit_home_adv else 0.0, 0.0]])

        # maschere per la correzione tau (4 angoli bassi)
        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)

        def neg_loglik(p: np.ndarray) -> float:
            attack = p[:n]; defense = p[n:2 * n]
            c = p[2 * n]; gamma = p[2 * n + 1]; rho = p[2 * n + 2]
            g = gamma if fit_home_adv else 0.0

            log_lh = c + attack[h] - defense[a] + g
            log_la = c + attack[a] - defense[h]
            lh = np.exp(log_lh); la = np.exp(log_la)

            # log Poisson dei due marginali
            ll = poisson.logpmf(x, lh) + poisson.logpmf(y, la)

            # correzione tau (deve restare > 0)
            tau = np.ones_like(lh)
            tau[m00] = 1.0 - lh[m00] * la[m00] * rho
            tau[m01] = 1.0 + lh[m01] * rho
            tau[m10] = 1.0 + la[m10] * rho
            tau[m11] = 1.0 - rho
            if np.any(tau <= 1e-9):
                return 1e12  # parametri non ammissibili
            ll = ll + np.log(tau)

            wll = float(np.sum(w * ll))
            penalty = self.ridge * float(np.sum(attack ** 2) + np.sum(defense ** 2))
            return -wll + penalty

        bounds = ([(-3.0, 3.0)] * n + [(-3.0, 3.0)] * n +
                  [(-2.0, 2.0), (-1.0, 1.0) if fit_home_adv else (0.0, 0.0), (-0.2, 0.2)])
        res = minimize(neg_loglik, p0, method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": 20000, "maxfun": 80000,
                                "ftol": 1e-8, "gtol": 1e-6})

        attack = res.x[:n]; defense = res.x[n:2 * n]
        # centra esplicitamente (identificabilita'): mean(attack)=mean(defense)=0,
        # il livello assorbito dal const.
        c = res.x[2 * n]
        attack = attack - attack.mean()
        defense = defense - defense.mean()
        c = c + (res.x[:n].mean()) - (res.x[n:2 * n].mean())  # mantiene i lambda invariati

        self._idx = idx
        self.fit_ = FitResult(
            teams=teams, attack=attack, defense=defense, const=float(c),
            home_adv=float(res.x[2 * n + 1] if fit_home_adv else 0.0),
            rho=float(res.x[2 * n + 2]), n_matches=len(matches), eff_matches=eff,
            converged=bool(res.success), neg_loglik=float(res.fun),
        )
        return self.fit_

    # ---------- lambda ----------
    def _lambdas(self, home_id: int, away_id: int, neutral: bool) -> Tuple[float, float]:
        f = self.fit_
        if f is None:
            raise RuntimeError("modello non ancora addestrato")
        if home_id not in self._idx or away_id not in self._idx:
            raise KeyError("squadra non vista in fase di fit")
        ih = self._idx[home_id]; ia = self._idx[away_id]
        g = 0.0 if neutral else f.home_adv
        lh = float(np.exp(f.const + f.attack[ih] - f.defense[ia] + g))
        la = float(np.exp(f.const + f.attack[ia] - f.defense[ih]))
        return lh, la

    # ---------- predict ----------
    def predict(self, home_id: int, away_id: int, neutral: bool = False) -> Dict:
        f = self.fit_
        lh, la = self._lambdas(home_id, away_id, neutral)
        grid = score_matrix(lh, la, f.rho, self.max_goals)
        exg = expected_goals(grid)
        return {
            "home_id": home_id, "away_id": away_id, "neutral": neutral,
            "lambda_home": lh, "lambda_away": la,
            "exp_goals_home": exg[0], "exp_goals_away": exg[1],
            "markets": markets_from_matrix(grid),
            "top_scores": top_correct_scores(grid, 5),
            "grid": grid,
        }

    def strength_table(self) -> List[Dict]:
        """Forze per squadra in scala moltiplicativa intuitiva.
        att > 1 = segna piu' della media; def < 1 = subisce meno della media."""
        f = self.fit_
        rows = []
        for i, t in enumerate(f.teams):
            rows.append({
                "team_id": t,
                "att": float(np.exp(f.attack[i])),       # >1 attacco forte
                "def_factor": float(np.exp(-f.defense[i])),  # <1 difesa solida
                "attack_log": float(f.attack[i]),
                "defense_log": float(f.defense[i]),
            })
        rows.sort(key=lambda r: r["att"], reverse=True)
        return rows


def parse_iso(d: str) -> datetime:
    """Parsa una data ISO (con o senza Z) in datetime tz-aware UTC."""
    s = d.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
