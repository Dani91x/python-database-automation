import gzip, pickle, os, sys, json, collections
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, os.path.join(R, "Ai Engine"))
d = json.load(open(os.path.join(R, "ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML", "lavori", "sonde", "b_ml_metriche_out.json")))
low = [x for x in d if x.get("brier") is not None and x["brier"] < 0.15]
print("brier<0.15:", len(low), [(x["league"], x["target"], x["brier"]) for x in low[:8]])
big = [x for x in d if x["target"] == "1x2" and x.get("brier") is not None and x["brier"] > 0.9]
print("brier 1x2 >0.9 (peggio di casuale 0.667):", len(big), [(x["league"], x["brier"]) for x in big[:6]])
cnt = collections.Counter(); n = 0
for lid in ["135", "39", "140", "78", "61"]:
    p = os.path.join(R, "Ai Engine", "models_cache", f"league_{lid}", "ensemble_v2_target_1x2.pkl.gz")
    if not os.path.exists(p): continue
    pl = pickle.load(gzip.open(p, "rb"))
    f = pl["features"]; n += 1
    print(lid, pl["trained_at"][:10], "n_feat", len(f), pl["calibration_metrics"], "models", [m[0] for m in pl["base_models"]], "meta", type(pl["meta_model"]).__name__, "bw", {k: round(v, 2) for k, v in pl["base_weights"].items()}, "cal", list((pl["isotonic_calibrators"] or {}).keys())[:3], (pl["isotonic_calibrators"] or {}).get("__temperature_scaling__"))
    print("   feat:", [c for c in f][:30])
    for c in f: cnt[c] += 1
print(cnt.most_common(40))
odds_like = [c for c in cnt if "odds" in c or "fair_prob" in c or "implied" in c]
print("feature quote usate:", odds_like)
