"""h_: legge SOLO calibration_metrics dai pkl locali (nessun DB)."""
import gzip, pickle, os, glob, statistics as st
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
for t in ["over_1_5", "over_3_5", "btts", "over_2_5"]:
    v = []
    for p in glob.glob(os.path.join(R, "Ai Engine", "models_cache", "league_*", f"ensemble_v2_target_{t}.pkl.gz")):
        try:
            with gzip.open(p, "rb") as f: pl = pickle.load(f)
            cm = pl.get("calibration_metrics") or {}
            if cm.get("brier") is not None: v.append((cm["brier"], os.path.basename(os.path.dirname(p)), pl.get("trained_at")))
        except Exception as e: pass
    v.sort()
    print(t, "n", len(v), "med", round(st.median([x[0] for x in v]), 4) if v else None, "lowest3", v[:3], ">0.5:", sum(x[0] > .5 for x in v))
