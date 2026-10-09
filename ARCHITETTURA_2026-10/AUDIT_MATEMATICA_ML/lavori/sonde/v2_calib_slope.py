"""V2 A3: pendenza di calibrazione O2.5 grezze dalle 8 celle gia' misurate (a_poisson_misura_db_output.txt r.19)
+ z-test per cella. Nessun DB."""
import numpy as np
cells = [(18,0.166,0.333),(50,0.261,0.42),(146,0.358,0.507),(228,0.454,0.513),(349,0.552,0.579),(372,0.65,0.629),(240,0.745,0.671),(87,0.835,0.747)]
n = np.array([c[0] for c in cells], float); p = np.array([c[1] for c in cells]); f = np.array([c[2] for c in cells])
for c in cells:
    se = (c[1]*(1-c[1])/c[0])**0.5
    print(f"n={c[0]:4d} p={c[1]:.3f} freq={c[2]:.3f} diff={c[2]-c[1]:+.3f} z={(c[2]-c[1])/se:+.2f}")
# regressione pesata freq ~ a + b*p
W = n/(p*(1-p)); X = np.vstack([np.ones_like(p), p]).T
beta = np.linalg.solve(X.T@(W[:,None]*X), X.T@(W*f)); cov = np.linalg.inv(X.T@(W[:,None]*X))
print(f"freq = {beta[0]:.3f} + {beta[1]:.3f}*p ; pendenza {beta[1]:.3f} +- {cov[1,1]**0.5:.3f} (1.00 = calibrato) -> z vs 1: {(beta[1]-1)/cov[1,1]**0.5:.2f}")
print("n totale", int(n.sum()))
