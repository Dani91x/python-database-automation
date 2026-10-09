"""Soglia di rumore dell'ECE (implementazione di seriea_model_export._ece_score, 10 bin) per un modello
PERFETTAMENTE calibrato, al variare della dimensione dell'holdout. Gate di produzione: ECE <= 0.10."""
import sys, numpy as np
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Ai Engine")
import importlib.util
src = open(r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation\Ai Engine\ai_engine\seriea_model_export.py", encoding="utf-8").read()
i = src.index("def _ece_score"); j = src.index("def _compute_calibration_cells")
ns = {"np": np}; exec(src[i:j], ns); ece = ns["_ece_score"]
rng = np.random.default_rng(1)
for n in (40, 100, 170, 400, 1000):
    for nome, (a, b) in {"1x2-like (p in .15-.6)": (0.15, 0.6), "binario (p in .3-.7)": (0.3, 0.7)}.items():
        v = []
        for _ in range(1500):
            if "1x2" in nome:
                P = rng.dirichlet([6, 3.5, 4.5], n)
                u = rng.random(n); cum = P.cumsum(1); y = (u[:, None] > cum).sum(1).clip(0, 2)
                classes = np.array([0, 1, 2]); pr = P; yy = y
            else:
                p = rng.uniform(a, b, n); yy = (rng.random(n) < p).astype(int)
                classes = np.array([0, 1]); pr = np.c_[1 - p, p]
            v.append(ece(yy, pr, classes))
        v = np.array(v)
        print(f"n={n:5d} {nome:24s} ECE medio (calibrato!) {v.mean():.3f}  p95 {np.percentile(v,95):.3f}  quota che FALLISCE gate 0.10: {100*(v>0.10).mean():5.1f}%")
