"""
Test EXCHANGE: prendi il miglior prezzo all'APERTURA (Maximum), tieni solo dove
batte la fair di CHIUSURA sharp (Pinnacle) -> il prezzo si muovera' a tuo favore.
Su exchange = green-up = profitto bloccabile a prescindere dal risultato.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
HOLD = pd.Timestamp("2020-07-01", tz="UTC")

df = pd.read_pickle(os.path.join(CACHE, "pred_ALL.pkl")).dropna(subset=["odd_Maximum", "fair_pin"]).copy()
df["back_open"] = df["odd_Maximum"]
df["fair_close"] = 1.0 / df["fair_pin"]
df["drift"] = df["back_open"] / df["fair_close"] - 1.0   # >0 = prezzo accorciato (CLV+)

print("SEGNALE OPEN->CLOSE: best price apertura che batte la chiusura sharp")
print(f"% scommesse che si muovono a favore (drift>0): {100*(df['drift']>0).mean():.1f}%\n")
print(f"{'soglia':<10}{'n':>8}{'green-up%':>11}{'let-run ROI':>13}{'holdout ROI':>13}")
for thr in [0.0, 0.03, 0.06, 0.10]:
    s = df[df["drift"] >= thr]
    if len(s) == 0:
        print(f"{thr:<10}vuoto"); continue
    locked = ((s["back_open"] - s["fair_close"]) / s["fair_close"]).mean()  # green-up frazionario
    let_run = np.where(s["y"] == 1, s["back_open"] - 1.0, -1.0).mean()
    h = s[s["date"] >= HOLD]
    lr_h = np.where(h["y"] == 1, h["back_open"] - 1.0, -1.0).mean() if len(h) else float("nan")
    print(f"{('>=%.2f'%thr):<10}{len(s):>8}{100*locked:>10.2f}%{100*let_run:>12.2f}%{100*lr_h:>12.2f}%")

print("\nNB: 'green-up%' = profitto medio bloccabile su exchange (banco apertura, copro a chiusura),")
print("    indipendente dal risultato. 'let-run' = se lasci correre la scommessa (varianza).")
