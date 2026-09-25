"""Stampa le tabelle del referto da risultati_test.json (nessun calcolo nuovo)."""
import json
import sys

R = json.load(open(sys.argv[1] if len(sys.argv) > 1 else
                   "AUDIT_2026-09-25/validazione_hazard/risultati_test.json", encoding="utf-8"))
SEG = ("tutti", "regolare_0_74", "tardo_75_89", "recupero_2T", "recupero_1T")


def f(t, n=5):
    return f"{t[0]:.{n}f} [{t[1]:.{n}f}, {t[2]:.{n}f}]"


def tabella(M, k):
    print(f"\n#### log-loss per stato, orizzonte {k}' (IC 95% per partita)")
    print("| candidato | " + " | ".join(SEG) + " |")
    print("|---" * (len(SEG) + 1) + "|")
    for n, c in M["candidati"].items():
        print(f"| {n} | " + " | ".join(f"{c[s + '|' + str(k)]['logloss'][0]:.5f}" if s + '|' + str(k) in c else "-"
                                       for s in SEG) + " |")
    print(f"\n#### Brier e ECE, orizzonte {k}'")
    print("| candidato | Brier tutti | Brier 75-89 | Brier rec2T | ECE tutti | ECE 75-89 | ECE rec2T | AUC tutti | AUC 75-89 | AUC rec2T |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for n, c in M["candidati"].items():
        def a(s):
            v = c.get(f"{s}|{k}", {}).get("auc")
            if v is None:
                return "-"
            return f"{v[0]:.4f} [{v[1]:.4f}, {v[2]:.4f}]" if isinstance(v, list) else f"{v:.4f}"
        def b_(s, campo):
            v = c.get(f"{s}|{k}")
            if v is None:
                return "-"
            return f"{v[campo][0]:.5f}" if campo == "brier" else f"{v[campo]:.5f}"
        print(f"| {n} | " + " | ".join(b_(s, "brier") for s in ("tutti", "tardo_75_89", "recupero_2T"))
              + " | " + " | ".join(b_(s, "ece") for s in ("tutti", "tardo_75_89", "recupero_2T"))
              + " | " + " | ".join(a(s) for s in ("tutti", "tardo_75_89", "recupero_2T")) + " |")
    print(f"\n#### differenze di log-loss contro A0, orizzonte {k}' (negativo = meglio; IC 95% per partita)")
    print("| candidato | " + " | ".join(SEG) + " |")
    print("|---" * (len(SEG) + 1) + "|")
    for n, d in M["differenze"].items():
        cel = []
        for s in SEG:
            x = d.get(f"{s}|{k}")
            if not x:
                cel.append("-")
                continue
            t = x["d_logloss"]
            seg = "**" if t[2] < 0 else ("~~" if t[1] > 0 else "")
            cel.append(f"{seg}{f(t)}{seg}")
        print(f"| {n.replace('-vs-A0', '')} | " + " | ".join(cel) + " |")


M = R["metriche"]
print("INSIEMI", R.get("insiemi"), "B1 da cache", R.get("B1_da_cache"))
print("partite", M["n_partite"], "stati", M["n_stati"])
for k in (3, 2):
    tabella(M, k)
print("\n#### B1 contro A* (differenze)")
for n, d in R["metriche_vs_Astar"]["differenze"].items():
    for s in SEG:
        for k in (3, 2):
            x = d.get(f"{s}|{k}")
            if x:
                print(n, s, k, f(x["d_logloss"]), "brier", f(x["d_brier"], 6))
print("\n#### AUC differenze")
for n, v in R["auc_differenze"].items():
    print(n, f(v, 4))
print("\nB1", R["B1"])
print("V4", {k: v for k, v in R["V4_modulo"].items() if k != "meta"})
print("A* info", {k: v for k, v in R["info_A"]["A*"].items() if k in ("beta", "k_durata", "durata_media_pool",
                                                                      "r_globale_per_gk", "durata_media_per_lega")})
if "metriche_regolari_sicuri" in R:
    print("\n## REGOLARI SICURI (tutto il 2025, t <= 41)")
    MS = R["metriche_regolari_sicuri"]
    print("partite", MS["n_partite"], "stati", MS["n_stati"])
    for k in (3, 2):
        tabella(MS, k)
if "metriche_intero_verita_falsata" in R:
    print("\n## INTERO (verita' falsata a fine tempo nel 2025 europeo)")
    for n, c in R["metriche_intero_verita_falsata"]["candidati"].items():
        print(n, {s: round(c[s + "|3"]["logloss"][0], 5) for s in SEG if s + "|3" in c})
for nome_sub in ("sottoinsieme_lambda_veri_regolari_sicuri",):
    if nome_sub in R:
        sub2 = R[nome_sub]
        print("\n###", nome_sub, sub2["n_partite"], sub2["n_stati"])
        for k in (3, 2):
            tabella(sub2["metriche"], k)
        for atl, r in sub2["divergenza_spuria"].items():
            for s_, v in r.items():
                if isinstance(v, dict):
                    print(atl, s_, {kk: (round(vv, 5) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "decili"})
sub = R["sottoinsieme_lambda_veri"]
print("\n### sottoinsieme lambda veri", sub["n_partite"], sub["n_stati"], sub.get("stati_senza_modello_live"),
      sub.get("stati_senza_modello_live_recupero2T"))
print(sub["lambda"])
for k in (3, 2):
    tabella(sub["metriche"], k)
print("\n### divergenza spuria")
for atl, r in sub["divergenza_spuria"].items():
    for s, v in r.items():
        if isinstance(v, dict):
            print(atl, s, {kk: (round(vv, 5) if isinstance(vv, float) else vv) for kk, vv in v.items() if kk != "decili"})
    print(atl, "decili >30%", [(b["n"], round(b["p_modello"], 4), round(b["p_atlante"], 4), round(b["osservata"], 4),
                                b["ragione"]) for b in r.get(">30%", {}).get("decili", [])])
print("\n### calibrazione per minuto 3' (A0 | A* | B1 | osservata)")
C = R["calibrazione"]
for i, row in enumerate(C["A0|3"]["per_minuto"]):
    a = C["A*|3"]["per_minuto"][i]
    b = C["B1|3"]["per_minuto"][i]
    print(f"| {row['cella']} | {row['n']} | {row['prevista']:.4f} | {a['prevista']:.4f} | {b['prevista']:.4f} | {row['osservata']:.4f} |")
print("\n### calibrazione per decili 3'")
for n in ("A0", "A*", "B1"):
    print(n, [(round(r['prevista'], 4), round(r['osservata'], 4)) for r in C[f"{n}|3"]["decili"]])
