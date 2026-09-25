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
    top_correct_scores, expected_goals, rho_bounds,
)

LN2 = log(2.0)

# Box storico di rho (invariato): |rho| <= 0.2.
RHO_BOX = 0.2
# Margine minimo della correzione tau sulle celle basse (25/09/2026, P(0-0) negativa):
# ogni tau(x,y) della griglia di QUALSIASI coppia prevedibile resta >= TAU_MIN, cioe'
# la cella corretta vale almeno lo 0,1 % del suo valore Poisson indipendente.
TAU_MIN = 1e-3


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
    # rho del primo stadio (vincolato solo sulle celle OSSERVATE, come prima del
    # 25/09) e se e' servito il secondo stadio vincolato su TUTTE le coppie.
    rho_unconstrained: Optional[float] = None
    rho_constraint_active: bool = False


def _rho_limits_all_pairs(attack: np.ndarray, defense: np.ndarray, const: float,
                          g_eff: float, tau_min: float = TAU_MIN) -> Tuple[float, float]:
    """Dominio di rho valido per OGNI coppia ordinata (i casa, j trasferta), i != j.

    E' l'intersezione dei domini di Dixon-Coles (dixon_coles.rho_bounds) su tutte le
    partite che il modello puo' prevedere, non solo su quelle osservate col 0-0:
      log(lh*la) = 2c + g + (a_i - d_i) + (a_j - d_j)  -> massimo sulla coppia con le
                   due s = a - d piu' alte;
      log(lh)    = c + g + a_i - d_j                   -> massimo su i != j.
    g_eff = max(gamma, 0): copre anche predict(neutral=True) su un modello col campo.
    Box storico |rho| <= RHO_BOX incluso.
    """
    n = attack.shape[0]
    k = 1.0 - float(tau_min)
    if n < 2:
        return -RHO_BOX, RHO_BOX
    s = attack - defense
    top2 = np.sort(s)[-2:]
    log_prod_max = 2.0 * const + g_eff + float(top2.sum())
    diff = attack.reshape(-1, 1) - defense.reshape(1, -1)
    np.fill_diagonal(diff, -np.inf)
    log_lam_max = const + g_eff + float(diff.max())
    hi = min(RHO_BOX, k * float(np.exp(-log_prod_max)), k)
    lo = max(-RHO_BOX, -k * float(np.exp(-log_lam_max)))
    return lo, hi


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
                  [(-2.0, 2.0), (-1.0, 1.0) if fit_home_adv else (0.0, 0.0), (-RHO_BOX, RHO_BOX)])
        opts = {"maxiter": 20000, "maxfun": 80000, "ftol": 1e-8, "gtol": 1e-6}
        # STADIO 1 (invariato rispetto a prima del 25/09): tau vincolata > 0 solo
        # sulle partite osservate 0-0/0-1/1-0/1-1.
        res = minimize(neg_loglik, p0, method="L-BFGS-B", bounds=bounds, options=opts)
        sol = res.x
        rho1 = float(sol[2 * n + 2])

        def _limits(p: np.ndarray) -> Tuple[float, float]:
            g_eff = max(float(p[2 * n + 1]), 0.0) if fit_home_adv else 0.0
            return _rho_limits_all_pairs(p[:n], p[n:2 * n], float(p[2 * n]), g_eff)

        # Il vincolo di Dixon-Coles va rispettato su TUTTE le coppie che il modello
        # prevedera', non solo sulle celle osservate: una coppia forte-contro-debole
        # che non ha mai fatto 0-0 nello storico non vincola rho nello stadio 1, e in
        # previsione tau(0,0) = 1 - lh*la*rho puo' diventare negativa (P(0-0) < 0).
        lo1, hi1 = _limits(sol)
        active = not (lo1 <= rho1 <= hi1)
        if active:
            # STADIO 2 (solo se lo stadio 1 viola il dominio): MLE VINCOLATA.
            # Riparametrizzazione rho = t * hi(p) per t >= 0, t * |lo(p)| per t < 0,
            # con t in [-1, 1]: copre esattamente il dominio ammissibile per ogni p.
            # Se lo stadio 1 e' gia' nel dominio e' anche l'ottimo vincolato (il
            # dominio e' un sottoinsieme di quello dello stadio 1): per questo lo
            # stadio 2 gira solo quando serve e le partite "normali" restano identiche.
            def _rho_of(q: np.ndarray) -> float:
                lo, hi = _limits(q)
                t = float(q[2 * n + 2])
                return t * hi if t >= 0.0 else t * (-lo)

            def neg_loglik_t(q: np.ndarray) -> float:
                p = q.copy()
                p[2 * n + 2] = _rho_of(q)
                return neg_loglik(p)

            t0 = min(1.0, rho1 / hi1) if rho1 >= 0.0 else max(-1.0, rho1 / (-lo1))
            q0 = sol.copy()
            q0[2 * n + 2] = t0
            bounds_t = bounds[:-1] + [(-1.0, 1.0)]
            res = minimize(neg_loglik_t, q0, method="L-BFGS-B", bounds=bounds_t, options=opts)
            sol = res.x.copy()
            sol[2 * n + 2] = _rho_of(res.x)

        attack = sol[:n]; defense = sol[n:2 * n]
        # centra esplicitamente (identificabilita'): mean(attack)=mean(defense)=0,
        # il livello assorbito dal const.
        c = sol[2 * n]
        attack = attack - attack.mean()
        defense = defense - defense.mean()
        c = c + (sol[:n].mean()) - (sol[n:2 * n].mean())  # mantiene i lambda invariati

        self._idx = idx
        self.fit_ = FitResult(
            teams=teams, attack=attack, defense=defense, const=float(c),
            home_adv=float(sol[2 * n + 1] if fit_home_adv else 0.0),
            rho=float(sol[2 * n + 2]), n_matches=len(matches), eff_matches=eff,
            converged=bool(res.success), neg_loglik=float(res.fun),
            rho_unconstrained=rho1, rho_constraint_active=active,
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
        # tau >= TAU_MIN per costruzione: rho nel dominio di Dixon-Coles della coppia.
        # Dopo il fit vincolato su tutte le coppie e' un'identita' (rho gia' dentro, a
        # meno dell'arrotondamento in virgola mobile sulla coppia estrema); resta come
        # garanzia per ogni FitResult (es. costruito a mano). score_matrix rinormalizza.
        lo, hi = rho_bounds(lh, la, TAU_MIN)
        rho_eff = min(max(f.rho, lo), hi)
        grid = score_matrix(lh, la, rho_eff, self.max_goals)
        exg = expected_goals(grid)
        return {
            "home_id": home_id, "away_id": away_id, "neutral": neutral,
            "lambda_home": lh, "lambda_away": la, "rho_effective": rho_eff,
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
