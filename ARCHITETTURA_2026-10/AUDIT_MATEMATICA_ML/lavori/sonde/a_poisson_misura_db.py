"""Sonda A2: misura di qualita' fuori campione delle probabilita' Poisson memorizzate (grezze vs calibrate),
con Brier, log-loss e RPS (1X2). SOLO SELECT, LIMIT stretto (<=1500 righe, una sola query a finestra di date)."""
import sys, math, json
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
import numpy as np
from db_client import get_supabase_client

DA, A = sys.argv[1], sys.argv[2]
LIM = 1500
sb = get_supabase_client()
rows = (sb.table("fixture_predictions")
        .select("fixture_id,league_id,result_home_goals,result_away_goals,m:db_json_analisi->markets,"
                "mc:db_json_analisi->markets_calibrated,inp:db_json_analisi->inputs,model:db_json_analisi->>model")
        .in_("result_status_short", ["FT"])
        .gte("fixture_date", DA).lt("fixture_date", A)
        .not_.is_("db_json_analisi", "null")
        .limit(LIM).execute().data or [])
print("righe lette:", len(rows), "(limite", LIM, ")")
rows = [r for r in rows if r.get("model") == "poisson_xg_hybrid_dc" and r.get("result_home_goals") is not None]
print("righe modello poisson_xg_hybrid_dc con esito:", len(rows))


def rps(p, o):
    c = np.cumsum(p) - np.cumsum(o)
    return float(np.sum(c[:-1] ** 2) / (len(p) - 1))


def score_1x2(key):
    B = L = R = 0.0
    n = 0
    for r in rows:
        mk = r.get(key) or {}
        x = mk.get("1x2")
        if not x:
            continue
        p = np.array([x["H"], x["D"], x["A"]], float)
        h, a = int(r["result_home_goals"]), int(r["result_away_goals"])
        o = np.array([h > a, h == a, h < a], float)
        B += float(np.sum((p - o) ** 2))
        L += -math.log(max(float(p[o.argmax()]), 1e-12))
        R += rps(p, o)
        n += 1
    return n, B / n, L / n, R / n


def score_bin(key, mkt, test):
    B = L = 0.0
    n = 0
    for r in rows:
        mk = r.get(key) or {}
        x = mk.get(mkt)
        if not x or "True" not in x:
            continue
        p = float(x["True"])
        h, a = int(r["result_home_goals"]), int(r["result_away_goals"])
        y = 1.0 if test(h, a) else 0.0
        pc = min(max(p, 1e-12), 1 - 1e-12)
        B += (p - y) ** 2
        L += -(y * math.log(pc) + (1 - y) * math.log(1 - pc))
        n += 1
    return n, B / n, L / n


print("\nBaseline climatologica (frequenze del campione) per riferimento:")
hs = [(int(r['result_home_goals']), int(r['result_away_goals'])) for r in rows]
fH = np.mean([h > a for h, a in hs]); fD = np.mean([h == a for h, a in hs]); fA = np.mean([h < a for h, a in hs])
base = np.array([fH, fD, fA])
Bb = np.mean([np.sum((base - np.array([h > a, h == a, h < a], float)) ** 2) for h, a in hs])
Lb = np.mean([-math.log(base[[h > a, h == a, h < a].index(True)]) for h, a in hs])
Rb = np.mean([rps(base, np.array([h > a, h == a, h < a], float)) for h, a in hs])
print(f" 1X2 frequenze campione H/D/A = {fH:.3f}/{fD:.3f}/{fA:.3f}  Brier={Bb:.4f} logloss={Lb:.4f} RPS={Rb:.4f}")

for key, lab in (("m", "GREZZE"), ("mc", "CALIBRATE")):
    n, B, L, R = score_1x2(key)
    print(f"\n[{lab}] 1X2: n={n} Brier(3 classi)={B:.4f} logloss={L:.4f} RPS={R:.4f}")
    for mkt, thr, lab2 in (("over_1_5", lambda h, a: h + a >= 2, "O1.5"), ("over_2_5", lambda h, a: h + a >= 3, "O2.5"),
                           ("over_3_5", lambda h, a: h + a >= 4, "O3.5"), ("btts", lambda h, a: h > 0 and a > 0, "BTTS")):
        n2, B2, L2 = score_bin(key, mkt, thr)
        print(f"   {lab2}: n={n2} Brier={B2:.4f} logloss={L2:.4f}")

# reliability O2.5 e 1X2-casa per decili (grezze)
for key, lab in (("m", "GREZZE"), ("mc", "CALIBRATE")):
    bins = {i: [0, 0.0, 0] for i in range(10)}
    for r in rows:
        x = (r.get(key) or {}).get("over_2_5")
        if not x:
            continue
        p = float(x["True"])
        h, a = int(r["result_home_goals"]), int(r["result_away_goals"])
        b = min(int(p * 10), 9)
        bins[b][0] += 1; bins[b][1] += p; bins[b][2] += (h + a >= 3)
    print(f"\n[{lab}] reliability O2.5 (bin: n, p media, freq):",
          [(b, v[0], round(v[1] / v[0], 3), round(v[2] / v[0], 3)) for b, v in bins.items() if v[0] >= 10])
# lambda totale atteso vs gol reali
tl = [(float(r['inp']['lambda_home']) + float(r['inp']['lambda_away']), int(r['result_home_goals']) + int(r['result_away_goals']))
      for r in rows if r.get('inp') and r['inp'].get('lambda_home') is not None]
print(f"\nlambda totale medio={np.mean([t for t, _ in tl]):.3f}  gol reali medi={np.mean([g for _, g in tl]):.3f}  (n={len(tl)});"
      f" casa: lambda={np.mean([float(r['inp']['lambda_home']) for r in rows if r.get('inp')]):.3f} reali={np.mean([int(r['result_home_goals']) for r in rows]):.3f}")
# sovradispersione: varianza dei gol totali vs media attesa condizionata
res = np.array([g - t for t, g in tl])
print(f"residuo medio (gol - lambda)={res.mean():+.3f}; var(gol)/media(gol)={np.var([g for _, g in tl]) / np.mean([g for _, g in tl]):.3f} "
      f"(Poisson puro = 1 condizionatamente; qui marginale)")
# indice dispersione condizionato (Pearson): sum (g-t)^2/t / n
disp = np.mean([(g - t) ** 2 / t for t, g in tl])
print(f"dispersione di Pearson condizionata E[(g-lambda)^2/lambda] = {disp:.3f} (1.00 = Poisson perfetto)")
