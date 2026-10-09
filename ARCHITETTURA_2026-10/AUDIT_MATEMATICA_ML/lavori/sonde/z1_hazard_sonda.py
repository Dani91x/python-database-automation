"""z1_hazard_sonda.py - sonda in SOLA LETTURA sulla catena hazard (audit 09/10/2026).
Importa il codice di produzione, legge l'atlante live da disco. Nessuna rete, nessun DB."""
import json
import math
import os
import sys

R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)
from Betfair.stream.scalper import hazard_atlas as HA          # noqa: E402
from Betfair.stream.scalper import atlante_v4 as V4            # noqa: E402
from Betfair.omega import omega_empirical as EM                # noqa: E402
from Betfair.mike.dossier import combine_hazard                # noqa: E402
from value_engine import goal_timing as GT                     # noqa: E402

P = os.path.join(R, "Betfair", "omega", "data", "hazard_atlas_live.json")
with open(P, "r", encoding="utf-8") as fh:
    A = json.load(fh)
print("== chiavi atlante live:", list(A.keys()))
print("meta:", {k: A["meta"][k] for k in list(A["meta"])[:12]})
v4 = A.get("v4")
print("v4 presente:", isinstance(v4, dict))
if v4:
    print("v4.meta:", {k: v4["meta"][k] for k in v4["meta"] if k not in ("etichette_tc", "metodo")})
    print("n leghe v3:", len(A["by_league"]), " n leghe v4:", len(v4["by_league"]), " by_team:", len(A.get("by_team", {})))

# ---------- 1) v3 globale vs Poisson-CDF -------------------------------------
print("\n== 1) v3 globale p(3min) per bucket (media pesata n sui gol) vs Poisson con CDF residua (gol medi 2.70)")
cdf = GT._load()
print("CDF caricata:", cdf is not None, "cdf[45]=", cdf and round(cdf[45], 4), "cdf[90]=", cdf and cdf[90])
g = A["global"]
righe = []
for b in HA.hazard_bucket(0), "10-15", "30-35", "40-45", "45-50", "60-65", "75-80", "85-90":
    tot_n = sum((g[b][k]["n"] or 0) for k in ("0", "1", "2", "3+"))
    pv3 = sum(((g[b][k]["p_goal_next_3min"] or 0) * (g[b][k]["n"] or 0)) for k in ("0", "1", "2", "3+")) / max(tot_n, 1)
    m0 = int(b.split("-")[0]) + 2          # minuto centrale del bucket
    lam_tot = 2.70
    share = (cdf[min(90, m0 + 3)] - cdf[m0]) if cdf else 3 / 90
    pm = 1 - math.exp(-lam_tot * share)
    print(f"  {b:6s} n={tot_n:8d} v3={pv3:.4f}  Poisson(CDF,2.7 gol)={pm:.4f}  rapporto v3/Poisson={pv3 / pm:.3f}")

# ---------- 2) cella v3: totale gol, non differenza reti ----------------------
print("\n== 2) v3 globale 60-65: p3 per gol totali")
for k in ("0", "1", "2", "3+"):
    c = g["60-65"][k]
    print("  gol", k, c)

# ---------- 3) consulta_atlante v3: moltiplicatore squadra con numeri ---------
print("\n== 3) mult squadra: esempio numerico (atlante sintetico minimo, formula di produzione)")
sr = 0.030
def atl(att_a, def_a, att_b, def_b, pcell=0.10):
    return {"meta": {"shrinkage": {"K_league_fixture_minutes": 1500.0}, "min_fixtures_league": 300},
            "by_league": {"1": {"meta": {"n_fixtures": 5000, "affidabile": True, "confidenza": "alta",
                                         "side_rate_per_bucket": {"60-65": sr}},
                                "grid": {"60-65": {"1": {"p_goal_next_3min": pcell, "n": 40000}}}}},
            "by_team": {"10": {"team_name": "A", "league_id": 1, "n_matches": 30,
                               "att_goals_per_match_by_bucket": {"60-65": att_a},
                               "def_goals_per_match_by_bucket": {"60-65": def_a}},
                        "20": {"team_name": "B", "league_id": 1, "n_matches": 30,
                               "att_goals_per_match_by_bucket": {"60-65": att_b},
                               "def_goals_per_match_by_bucket": {"60-65": def_b}}},
            "global": {}}
for nome, args in {"neutre": (sr, sr, sr, sr), "A att 2x": (2 * sr, sr, sr, sr),
                   "entrambe forti att x2/def x1": (2 * sr, sr, 2 * sr, sr),
                   "A forte att x2, B debole def x2": (2 * sr, sr, sr, 2 * sr)}.items():
    r = HA.consulta_atlante(atl(*args), 62, 1, 1, home_id=10, away_id=20, home_team="A", away_team="B")
    print(f"  {nome:36s} p={r['p']:.4f} fonte={r['fonte']} conf={r['confidenza']}")

# rumore del profilo squadra per bucket: n=30 partite, K_TEAM=12
print("  -- rumore profilo squadra (n=30, K_TEAM=12, sr=0.030 gol/partita/bucket):")
for gol in (0, 1, 2, 3):
    att = (gol + 12 * 0.030) / (30 + 12)
    print(f"     {gol} gol in bucket -> att={att:.4f}  rapporto att/sr={att / 0.030:.2f}")
print("     P(>=3 gol in 30 partite | tasso vero 0.030) = %.4f" % (1 - sum(math.exp(-0.9) * 0.9 ** i / math.factorial(i) for i in range(3))))

# ---------- 4) v4: _p_recupero2, forza, coerenza con v3 ----------------------
print("\n== 4) _p_recupero2 (formula di produzione)")
pi = [0.0, 0.0, 0.05, 0.15, 0.25, 0.25, 0.15, 0.10, 0.05]   # durata del recupero (esempio)
for (r, j, k) in [(0.03, 0, 3), (0.03, 2, 3), (0.03, 4, 3), (0.03, 7, 3)]:
    p, att = V4._p_recupero2(r, pi, j, k)
    print(f"  r={r} j={j} k={k}: P={p:.4f}  atteso residuo={att}")
print("  fallback senza pi: k=2:", V4._p_recupero2(0.03, None, 0, 2), " k=3:", V4._p_recupero2(0.03, None, 0, 3),
      " (identici: k ignorato)")
# integrale esatto: j=0,k=3 -> controllo manuale
j, k, r = 0, 3, 0.03
massa = sum(pi[d] for d in range(len(pi)) if d > j)
sopr = sum(pi[d] * math.exp(-r * min(k, d - j)) for d in range(len(pi)) if d > j)
print("  controllo manuale j=0 k=3:", round(1 - sopr / massa, 6))
if v4:
    L = v4["by_league"]
    big = sorted(L.items(), key=lambda kv: -(kv[1]["n_fixtures"] or 0))[:3]
    print("  leghe v4 piu' grandi:", [(k, v["league_name"], v["n_fixtures"], v["gol_medi"], v.get("durata_media")) for k, v in big])
    lid = big[0][0]
    gm = v4["global"]["gol_medi"]
    print("  gol medi globali v4:", gm, " beta:", v4["meta"]["beta"], " emivita", v4["meta"]["emivita"],
          " k_durata", v4["meta"].get("k_durata"), " ripieghi", v4["meta"].get("ripieghi"))
    print("  global r_rec2 per gol key:", [round(x, 4) for x in v4["global"]["r_rec2"]])
    # v3 vs v4 stessa lega, bucket regolari
    print("  confronto v3 vs v4 (lega %s, p3) per bucket regolari, gol=1:" % lid)
    for b in range(0, 18, 3):
        v3c = A["by_league"][lid]["grid"][f"{5 * b}-{5 * b + 5}"]["1"]["p_goal_next_3min"]
        v4c = L[lid]["p3"][b][1]
        print(f"     {5 * b:2d}-{5 * b + 5:2d}: v3={v3c} v4={round(v4c, 4)}")
    print("  celle del recupero 2T v4 (lega %s), p3 per J_BIN, gol=1:" % lid, [round(L[lid]["p3"][b][1], 4) for b in range(19, 27)])
    # consulta_atlante_v4 con e senza forza
    teams = (L[lid].get("forza") or {}).get("squadre") or {}
    ids = list(teams)[:2]
    print("  squadre con rating nella lega:", len(teams), ids)
    for kw in ({}, {"home_id": ids[0], "away_id": ids[1]} if len(ids) == 2 else {}):
        c = V4.consulta_atlante_v4(A, 62, 1, int(lid), tempo=2, **kw)
        print("   v4 62' 1 gol", kw, "-> p3=%.4f" % c["p"], c["forza"].get("moltiplicatore"), c["fonte"], c["confidenza"], "n=", c["n"])
    for mn in (90, 92, 94, 96):
        c = V4.consulta_atlante_v4(A, mn, 1, int(lid), tempo=2, horizon="p_goal_next_3min")
        c2 = V4.consulta_atlante_v4(A, mn, 1, int(lid), tempo=2, horizon="p_goal_next_2min")
        print(f"   v4 {mn}' tempo2 1 gol: p3={c['p']:.4f} p2={c2['p']:.4f} atteso rec={c['recupero_atteso_min']}")
    # forza: estremi
    c = V4.consulta_atlante_v4(A, 62, 1, int(lid), tempo=2, lambda_home=3.0, lambda_away=2.5)
    print("   lambda esplicito 3.0+2.5 ->", c["forza"].get("moltiplicatore"), "p=%.4f" % c["p"])
    # globale vs v3 globale
    gp = v4["global"]["p3"]
    print("  v4 globale p3 bucket 60-65:", [round(x, 4) for x in gp[12]], " v3:", [g["60-65"][k]["p_goal_next_3min"] for k in ("0", "1", "2", "3+")])

# ---------- 5) Wilson upper / shrunk_upper -----------------------------------
print("\n== 5) p_upper / shrunk_upper (produzione): gonfiaggio rispetto alla frequenza")
for (k, n) in [(0, 200), (0, 1000), (0, 10000), (1, 200), (5, 1000), (50, 5000), (500, 50000), (5000, 500000)]:
    pu = EM.p_upper(k, n)
    print(f"  k={k:6d} n={n:7d}  MLE={k / n:.5f}  upper={pu:.5f}  rapporto={pu / (k / n) if k else float('inf'):.2f}")
print("  shrunk_upper lega k=0/n=10, globale k=2/n=200 (docstring: 1,26%):", round(EM.shrunk_upper(0, 10, 2, 200), 5))
print("  shrunk_upper lega k=3/n=300, globale k=3000/n=300000:", round(EM.shrunk_upper(3, 300, 3000, 300000), 5), " MLE lega=0.01 glob=0.01")
print("  shrunk_upper lega k=60/n=3000 (2%), globale 1% su 300000:", round(EM.shrunk_upper(60, 3000, 3000, 300000), 5))
# n_eff quando K=500 e n_l grande
nl, ng = 3000.0, 300000.0
ke = 500.0
wl, wg = nl / (nl + ke), ke / (nl + ke)
print("  n_eff =", round(1 / (wl * wl / nl + wg * wg / ng), 1), "(vs n_l =", nl, ", n_l+K =", nl + ke, ")")
# nota: il prior globale NON e' un binomiale indipendente da n_l; si trascura la varianza fra leghe (tau2)
# max(P_model, P_emp) come stima puntuale: bias da max di due stime rumorose
import random
random.seed(1)
def sim(p, s1, s2, N=200000):
    acc = 0.0
    for _ in range(N):
        a = random.gauss(p, s1)
        b = random.gauss(p, s2)
        acc += max(a, b)
    return acc / N
for (p, s) in [(0.08, 0.02), (0.08, 0.01), (0.002, 0.001)]:
    print(f"  E[max(N({p},{s}),N({p},{s}))]={sim(p, s, s):.5f} (teoria p+s/sqrt(pi)={p + s / math.sqrt(math.pi):.5f}) -> bias relativo {(sim(p, s, s) / p - 1) * 100:.1f}%")
print("  combine_hazard(0.08, 0.10, 1.25) =", combine_hazard(0.08, 0.10, 1.25), " (0.10*1.25=0.125 domina)")
print("  combine_hazard(0.12, 0.08, 1.25) =", combine_hazard(0.12, 0.08, 1.25))
print("  combine_hazard(None, 0.08, 1.0) =", combine_hazard(None, 0.08, 1.0), " combine(None,None) =", combine_hazard(None, None))

# ---------- 6) tabella per minuto: bucket b per minuti b..b+4 ------------------
print("\n== 6) tabella omega_minute: stato a minuto esatto b, usata per b..b+4 (CDF reale)")
for b in (60, 80, 85):
    for m in (b, b + 2, b + 4):
        fr_b = 1 - cdf[min(b, 90)]
        fr_m = 1 - cdf[min(m, 90)]
        print(f"  bucket {b} usato a minuto {m}: gol residui attesi tabella ~{fr_b:.3f} vs reali {fr_m:.3f} della partita (rapporto {fr_b / fr_m:.2f})")
print("  minute_bucket(89,half=False)=", EM.minute_bucket(89, half=False), " minute_bucket(93,half=False)=", EM.minute_bucket(93, half=False))

# ---------- 7) v3: celle 85-90 e M_MAX=87, gol del recupero clampati -----------
print("\n== 7) v3: M_MAX=87 e clamp dei gol: finestra (m, m+3] per m=85..87 arriva a 90; per m=88,89 la cella 85-90 e' consultata ma non contata")
from Betfair.stream.scalper import genera_atlante as G
print("  G.M_MAX =", G.M_MAX, " bucket(87)=", G._bucket(87), " _bucket_gol(90)=", G._bucket_gol(90), " _bucket_gol(45)=", G._bucket_gol(45), " _bucket_gol(46)=", G._bucket_gol(46))
st = G.stato_lega_vuoto(1)
seq = {"fixture_id": 1, "home_id": 1, "away_id": 2, "home_name": "a", "away_name": "b", "goals": [[90, "h"]], "ft": [1, 0], "ht": [0, 0], "season": 2025, "date": "2025-01-01"}
G.aggiungi_partita(st, seq)
print("  partita con gol al 90' (anche 90+5): celle 85-90 gk=0 [n,s3,s2] =", st["cells"]["85-90"]["0"], " (conta solo per m=87: m<x<=m+3 -> 87<90<=90)")
print("  stessa partita, gol 45+4 (minute=45): cella 40-45 gk=0:", None)
st2 = G.stato_lega_vuoto(1)
seq2 = dict(seq, goals=[[45, "h"]])
G.aggiungi_partita(st2, seq2)
print("   40-45 gk=0:", st2["cells"]["40-45"]["0"], " 45-50 gk=0:", st2["cells"]["45-50"]["0"], " 45-50 gk=1:", st2["cells"]["45-50"]["1"],
      "(il gol del recupero 1T al 45' e' 'segnato' gia' a m=45: nel 2T parte da 1 gol)")
