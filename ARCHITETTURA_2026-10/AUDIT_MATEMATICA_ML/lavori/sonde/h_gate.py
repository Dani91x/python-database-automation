"""h_: verifica indipendente R1 (B). Forecaster 'tasso base esatto q' con Brier a somma-classi.
Importa il gate di produzione (confidence_gate.gate_calibration_quality) e lo interroga."""
import sys, os
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, os.path.join(R, "Ai Engine"))
import numpy as np
from ai_engine.confidence_gate import gate_calibration_quality
rng = np.random.default_rng(7)
print("q    Brier_atteso  BSS_unif  gate_prod_passa  | MC holdout n=110 (stima q da train 825): P(passa)")
for q in [0.50, 0.55, 0.60, 0.65, 0.70, 0.74, 0.80, 0.30, 0.29]:
    br = 2 * q * (1 - q)
    g = gate_calibration_quality(brier=br, ece=0.0, n_classes=2)
    ph = np.clip(rng.binomial(825, q, 20000) / 825, .01, .99)
    yb = rng.binomial(110, q, 20000) / 110
    b = 2 * (ph**2 - 2*ph*yb + yb)
    print(f"{q:.2f}  {br:.3f}        {1-br/0.5:+.3f}    {g.passed}              | {100*np.mean(1-b/0.5>=0.12):5.1f}%")
# 1x2: tasso base 44.5/26.5/29.0 predetto costante
p = np.array([.445, .265, .29]); br3 = float(np.sum(p*(1-p)*1) + 0)  # E[sum (p-y)^2] = sum p(1-p)
print("1x2 climatologia Brier", round(1 - np.sum(p**2), 4), "BSS vs uniforme 2/3:", round(1 - (1-np.sum(p**2))/(2/3), 4))
