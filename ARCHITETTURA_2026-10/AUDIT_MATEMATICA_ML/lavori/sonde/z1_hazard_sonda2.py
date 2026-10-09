"""z1_hazard_sonda2.py - forza v4: lambda neutro vs gol_medi di riferimento; docstring shrunk_upper; atlante in sola lettura."""
import json, math, os, sys, statistics as st
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)
from Betfair.stream.scalper import atlante_v4 as V4
from Betfair.omega import omega_empirical as EM
with open(os.path.join(R, "Betfair", "omega", "data", "hazard_atlas_live.json"), encoding="utf-8") as fh:
    A = json.load(fh)
v4 = A["v4"]
print("docstring shrunk_upper(0,10,0,200) =", round(EM.shrunk_upper(0, 10, 0, 200), 5), "(attesa 0.0126)")
rat = []
tot_n = 0
for lid, L in v4["by_league"].items():
    fz = L.get("forza")
    if not isinstance(fz, dict) or not L.get("gol_medi") or (L["n_fixtures"] or 0) < 300:
        continue
    mu = fz["mu"]
    neutro = (mu[0] + mu[1]) / L["gol_medi"]          # mult con due squadre a rating 0
    # media dei lt su tutte le coppie possibili = mu_sum * E[exp(att+dif)]
    sq = fz["squadre"]
    rat.append((neutro, lid, L["n_fixtures"], mu, L["gol_medi"], len(sq)))
rat.sort()
vals = [r[0] for r in rat]
print("leghe affidabili con forza:", len(vals), "mult neutro (mu_sum/gol_medi): min %.3f p10 %.3f mediana %.3f p90 %.3f max %.3f" % (
    vals[0], vals[len(vals)//10], st.median(vals), vals[9*len(vals)//10], vals[-1]))
print("quota leghe con |mult-1|>5%%: %.2f ; con >10%%: %.2f" % (sum(abs(v-1) > .05 for v in vals)/len(vals), sum(abs(v-1) > .10 for v in vals)/len(vals)))
for r in rat[:3] + rat[-3:]:
    print("  lega", r[1], "n", r[2], "mu", [round(x, 3) for x in r[3]], "gol_medi", r[4], "mult_neutro", round(r[0], 3), "-> p fattore (mult^0.627) =", round(r[0] ** 0.627, 3))
# media ponderata su coppie reali: rating medi
import itertools
L = max(v4["by_league"].items(), key=lambda kv: kv[1]["n_fixtures"])[1]
sq = L["forza"]["squadre"]
vals_att = [v[0] for v in sq.values()]; vals_dif = [v[1] for v in sq.values()]
print("lega piu' grande: n squadre", len(sq), "media att %.3f media dif %.3f sd att %.3f sd dif %.3f" % (st.mean(vals_att), st.mean(vals_dif), st.pstdev(vals_att), st.pstdev(vals_dif)))
print("   E[exp(att+dif)] ~", round(math.exp(st.mean(vals_att)+st.mean(vals_dif) + 0.5*(st.pvariance(vals_att)+st.pvariance(vals_dif))), 4), "(Jensen, >1 se sd>0)")
print("   mu", L["forza"]["mu"], "gol_medi", L["gol_medi"], " rientro", L["forza"].get("rientro"), "stagione", L["forza"].get("stagione"))
# distribuzione quota di squadre by_team v3 con n<30
bt = A["by_team"]
ns = sorted(t["n_matches"] for t in bt.values())
print("by_team v3: n squadre", len(ns), "n_matches mediana", ns[len(ns)//2], "p10", ns[len(ns)//10], "p90", ns[9*len(ns)//10])
