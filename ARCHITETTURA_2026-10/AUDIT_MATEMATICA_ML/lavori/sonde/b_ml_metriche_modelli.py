"""Sonda SOLA LETTURA: legge calibration_metrics dai .pkl.gz in Ai Engine/models_cache.
Stampa JSON con brier/ece/trained_at/n_classes per target scelti. Nessuna scrittura."""
import gzip, pickle, os, sys, json, glob
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, os.path.join(R, "Ai Engine"))
targets = sys.argv[1].split(",")
out = []
for d in sorted(glob.glob(os.path.join(R, "Ai Engine", "models_cache", "league_*"))):
    lid = os.path.basename(d).split("_")[1]
    for t in targets:
        p = os.path.join(d, f"ensemble_v2_target_{t}.pkl.gz")
        if not os.path.exists(p):
            continue
        try:
            with gzip.open(p, "rb") as f:
                pl = pickle.load(f)
            cm = pl.get("calibration_metrics") or {}
            out.append({"league": lid, "target": t, "brier": cm.get("brier"), "ece": cm.get("ece"),
                        "trained_at": pl.get("trained_at"), "n_cls": len(pl.get("class_labels") or []),
                        "n_feat": len(pl.get("features") or []), "has_cal": bool(pl.get("isotonic_calibrators")),
                        "mtime": os.path.getmtime(p), "keys": sorted(pl.keys()) if len(out) == 0 else None,
                        "ts": (pl.get("isotonic_calibrators") or {}).get("__temperature_scaling__")})
        except Exception as e:
            out.append({"league": lid, "target": t, "err": str(e)[:80]})
json.dump(out, open(os.path.join(R, "ARCHITETTURA_2026-10/AUDIT_MATEMATICA_ML", "lavori", "sonde", "b_ml_metriche_out.json"), "w"), default=str)
print(len(out))
