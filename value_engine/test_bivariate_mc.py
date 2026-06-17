"""
test_bivariate_mc.py — VERIFICA INDIPENDENTE di ogni formula del calcolatore via Monte Carlo.
Le formule analitiche vengono confrontate con simulazioni (centinaia di migliaia di partite) e
con cross-check tra moduli. Nessuna dipendenza dai vecchi file. Esegui:
    python -m value_engine.test_bivariate_mc
"""
import random
import math
from bisect import bisect_left

from value_engine.bivariate import (pois, dc_tau, score_matrix, _markets_from_matrix,
                                     derive_lambdas, conditional_markets)
from value_engine.poisson_total import p_le, cond_prob_total
import value_engine.devig as dv

random.seed(12345)
N = 300_000
checks = []


def check(name, analytic, ref, tol):
    ok = abs(analytic - ref) <= tol
    checks.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name:42s} analytic={analytic:.4f}  ref={ref:.4f}  (tol {tol})")


def poisson_sample(lam):
    """Knuth — campiona Poisson(lam) senza librerie (verifica indipendente)."""
    L = math.exp(-lam); k = 0; p = 1.0
    while True:
        k += 1; p *= random.random()
        if p <= L:
            return k - 1


print("=" * 80)
print("  VERIFICA FORMULE — Monte Carlo & cross-check (N =", N, "simulazioni)")
print("=" * 80)

# 1) Dixon-Coles tau: a rho=0 deve valere 1 ovunque (si riduce a Poisson indipendenti)
for (x, y) in ((0, 0), (0, 1), (1, 0), (1, 1)):
    check(f"tau{(x,y)} a rho=0 == 1", dc_tau(x, y, 1.5, 1.2, 0.0), 1.0, 1e-12)

# 2) la matrice somma a 1
M = score_matrix(1.6, 1.1, -0.13)
check("score_matrix somma = 1", sum(sum(r) for r in M), 1.0, 1e-9)

# 3) a rho=0 la marginale == Poisson (tol 1e-5: la matrice e' troncata+normalizzata a 12 gol)
M0 = score_matrix(1.6, 1.1, 0.0)
check("rho0: P(casa=2) == Poisson(1.6,2)", sum(M0[2]), pois(1.6, 2), 1e-5)

# 4) cross-check totali: O25 bivariato (rho0) == 1 - P_le(2) Poisson(lam+mu)  [somma di Poisson]
mk0 = _markets_from_matrix(M0)
check("O25 bivariato == univariato (rho0)", mk0["O25"], 1 - p_le(2, 1.6 + 1.1), 1e-6)

# 5) cross-check col modulo univariato cond_prob_total (totali in-play, rho0)
#    Under 3.5 a meta' partita 1-0: bivariato deve ~= univariato con lam_full=lam+mu
lam, mu = 1.7, 1.0
an_u35_bivar = conditional_markets(lam, mu, 0.0, 45, 1, 0)["U35"]
# univariato: under 3.5 (k=3), gia' 1 gol, lam_full=lam+mu, frac=(90-45)/90
u_u35 = cond_prob_total("under", 3, lam + mu, 45, 1, T=90)
check("U35 in-play bivar==univar (rho0)", an_u35_bivar, u_u35, 1e-6)

# --- MONTE CARLO -------------------------------------------------------------------------
rho = -0.13
minute, gh, ga, T = 20, 1, 0, 90
frac = (T - minute) / T

# 6) MC campionando dalla matrice DC dei gol rimanenti (verifica shift + lettura mercati)
an = conditional_markets(lam, mu, rho, minute, gh, ga)
R = score_matrix(lam * frac, mu * frac, rho)
flat, cum = [], 0.0
cells = []
for i in range(len(R)):
    for j in range(len(R)):
        cum += R[i][j]; flat.append(cum); cells.append((i, j))
cH = cBTTS = cO25 = cA = 0
for _ in range(N):
    i, j = cells[min(bisect_left(flat, random.random()), len(cells) - 1)]
    fh, fa = gh + i, ga + j
    if fh > fa: cH += 1
    elif fh < fa: cA += 1
    if fh >= 1 and fa >= 1: cBTTS += 1
    if fh + fa >= 3: cO25 += 1
check("cond H   (MC da matrice DC)", an["H"], cH / N, 0.005)
check("cond A   (MC da matrice DC)", an["A"], cA / N, 0.005)
check("cond BTTS(MC da matrice DC)", an["BTTS"], cBTTS / N, 0.005)
check("cond O25 (MC da matrice DC)", an["O25"], cO25 / N, 0.005)

# 7) MC con vero processo di Poisson INDIPENDENTE (rho=0): verifica il cuore Poisson+tempo
an0 = conditional_markets(lam, mu, 0.0, minute, gh, ga)
cH = cBTTS = cO25 = 0
for _ in range(N):
    rh = poisson_sample(lam * frac); ra = poisson_sample(mu * frac)
    fh, fa = gh + rh, ga + ra
    if fh > fa: cH += 1
    if fh >= 1 and fa >= 1: cBTTS += 1
    if fh + fa >= 3: cO25 += 1
check("cond H   rho0 (MC Poisson vero)", an0["H"], cH / N, 0.005)
check("cond BTTS rho0 (MC Poisson vero)", an0["BTTS"], cBTTS / N, 0.005)
check("cond O25 rho0 (MC Poisson vero)", an0["O25"], cO25 / N, 0.005)

# 8) derive_lambdas: round-trip dalle quote -> ricostruisce le prob de-viggate
p = dv.devig_multiplicative({"H": 2.10, "D": 3.40, "A": 3.60})
pO25 = dv.devig_pair(1.90, 2.00)
lam_d, mu_d = derive_lambdas(p["H"], pO25)
mkd = _markets_from_matrix(score_matrix(lam_d, mu_d, -0.13))
check("round-trip H", mkd["H"], p["H"], 0.01)
check("round-trip O25", mkd["O25"], pO25, 0.01)
print(f"      derive -> lambda_casa={lam_d:.3f} mu_trasf={mu_d:.3f} | implied H={mkd['H']:.3f} "
      f"D={mkd['D']:.3f} A={mkd['A']:.3f} (mercato de-vig H={p['H']:.3f} D={p['D']:.3f} A={p['A']:.3f})")

print("=" * 80)
print("  RISULTATO:", "TUTTI I TEST PASSANO ✅" if all(checks) else "❌ CI SONO FALLIMENTI")
print("=" * 80)
