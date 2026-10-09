"""h_: A6 - effetto di rho (-0.13 fallback vs -0.081 medie delle 24 leghe stimate) su D/BTTS/O2.5, matrice DC scritta da me (tau standard DC 1997)."""
import numpy as np
from scipy.stats import poisson
def mat(lh, la, rho, N=12):
    i = np.arange(N); M = np.outer(poisson.pmf(i, lh), poisson.pmf(i, la))
    M[0,0] *= 1 - lh*la*rho; M[0,1] *= 1 + lh*rho; M[1,0] *= 1 + la*rho; M[1,1] *= 1 - rho
    return M / M.sum()
def mk(M):
    N = M.shape[0]; i = np.arange(N); I, J = np.meshgrid(i, i, indexing="ij")
    return dict(H=M[I>J].sum(), D=M[I==J].sum(), A=M[I<J].sum(), BTTS=M[(I>0)&(J>0)].sum(), O25=M[I+J>=3].sum(), O15=M[I+J>=2].sum())
for lh, la in [(1.4,1.1),(1.1,0.9),(1.8,1.2),(1.0,1.0)]:
    a, b = mk(mat(lh, la, -0.13)), mk(mat(lh, la, -0.081))
    print(f"lam {lh}/{la}: " + " ".join(f"{k} {100*(a[k]-b[k]):+.2f}pp" for k in a), "(rho -0.13 meno -0.081)")
# RPS: verifica della definizione usata dal delegato (sum cumul diff^2 / (K-1)) con un caso a mano
p = np.array([.5,.3,.2]); o = np.array([1,0,0.])
c = np.cumsum(p-o); print("RPS a mano p=(.5,.3,.2) esito H:", round(float((c[:-1]**2).sum()/2), 4), "atteso (0.5^2+0.2^2)/2 =", (0.25+0.04)/2)
