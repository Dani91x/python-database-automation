"""
Generate the model's signals for today's fixtures (out-of-sample: today's matches
have no result in the DB so they were excluded from training), and verify the
already-FINISHED ones against the live result.
"""
from __future__ import annotations

import os
import sys
import json
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))
os.environ["MODEL_CACHE_TTL_HOURS"] = "0"  # force fresh download of the just-uploaded models

rows = json.load(open(os.path.join(ROOT, "tmp_today_fixtures.json")))
leagues = sorted({r["league_id"] for r in rows if r.get("league_id")})

# Clear the prediction download cache for these leagues so the freshly uploaded
# (retrained, leakage-free, full-stack) models are used.
dl = os.path.join(ROOT, "Ai Engine", "models_cache", "downloaded")
for lid in leagues:
    d = os.path.join(dl, f"league_{lid}")
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)

from ai_engine.predict_fixture import predict_fixture

PR = ["target_1x2", "target_over_2_5", "target_over_1_5", "target_over_0_5", "target_btts", "target_ht_over_0_5"]
FIN = {"FT", "AET", "PEN"}


def fmt_probs(t: dict) -> str:
    parts = []
    if "target_1x2" in t:
        p = t["target_1x2"]
        parts.append(f"1x2 H{p.get('H',0)*100:.0f}/D{p.get('D',0)*100:.0f}/A{p.get('A',0)*100:.0f}")
    for key, lbl in [("target_over_1_5", "O1.5"), ("target_over_2_5", "O2.5"), ("target_btts", "BTTS"), ("target_ht_over_0_5", "HTO0.5")]:
        if key in t:
            parts.append(f"{lbl} {t[key].get('True',0)*100:.0f}%")
    return " | ".join(parts)


report = []
for r in rows:
    fid = r["fid"]
    rec = {"fid": fid, "home": r.get("home") or "?", "away": r.get("away") or "?",
           "league_id": r.get("league_id"), "status": r.get("live_status"),
           "finished": r.get("finished"), "gh": r.get("live_gh"), "ga": r.get("live_ga")}
    try:
        out = predict_fixture(fid, store=False)
        rec["targets"] = {k: out["targets"][k] for k in PR if k in out.get("targets", {})}
        rec["n_signals"] = len(out.get("bet_signals", []))
        rec["signals"] = [
            {"market": s.get("market"), "action": s.get("action"), "prob": s.get("model_prob"),
             "ev": s.get("ev"), "grade": s.get("confidence_grade")}
            for s in out.get("bet_signals", [])
        ]
        rec["not_reliable"] = [x.get("target") for x in out.get("targets_not_reliable", [])]
    except Exception as e:
        rec["error"] = str(e)[:200]
    report.append(rec)

json.dump(report, open(os.path.join(ROOT, "tmp_predict_today_result.json"), "w"), indent=2, default=str)

# ---- Per-match signals ----
print("\n" + "=" * 100)
print("SEGNALI DEL MODELLO — partite di oggi (out-of-sample)")
print("=" * 100)
ok = [x for x in report if "error" not in x and x.get("targets")]
err = [x for x in report if "error" in x]
for x in report:
    if "error" in x:
        print(f"  fid {x['fid']} ({x['league_id']}): NO MODEL/ERR — {x['error'][:80]}")
        continue
    tag = "FINITA" if x["finished"] else (x["status"] or "?")
    res = f" [{x['gh']}-{x['ga']}]" if x["finished"] else ""
    probs = fmt_probs(x.get("targets", {}))
    sig = f" | SEGNALI GATE: {x['n_signals']}" if x.get("n_signals") else " | nessun segnale (gate)"
    print(f"  [{tag:6}] {str(x['home'])[:16]:16} v {str(x['away'])[:16]:16}{res} (lega {x['league_id']}) -> {probs}{sig}")
    for s in x.get("signals", []):
        print(f"             >> BET {s['market']} {s['action']} p={s['prob']} EV={s['ev']} ({s['grade']})")

# ---- Verification on finished ----
print("\n" + "=" * 100)
print("VERIFICA sulle partite FINITE (segnale vs risultato reale)")
print("=" * 100)
fin = [x for x in report if x.get("finished") and "error" not in x and x.get("targets")]
if not fin:
    print("  Nessuna partita finita con modello disponibile.")
n1x2_ok = n1x2 = 0
for x in fin:
    gh, ga = int(x["gh"]), int(x["ga"])
    t = x["targets"]
    line = []
    if "target_1x2" in t:
        p = t["target_1x2"]
        pick = max(p, key=p.get)
        actual = "H" if gh > ga else ("A" if gh < ga else "D")
        n1x2 += 1
        n1x2_ok += int(pick == actual)
        line.append(f"1x2 pick {pick} (p{p[pick]*100:.0f}) real {actual} {'OK' if pick==actual else 'X'}")
    for key, lbl, line_val in [("target_over_1_5", "O1.5", 1), ("target_over_2_5", "O2.5", 2)]:
        if key in t:
            pover = t[key].get("True", 0)
            actual_over = (gh + ga) > line_val
            said_over = pover >= 0.5
            line.append(f"{lbl} p{pover*100:.0f}% real {'O' if actual_over else 'U'} {'OK' if said_over==actual_over else 'X'}")
    print(f"  {str(x['home'])[:16]:16} {gh}-{ga} {str(x['away'])[:16]:16} | " + " | ".join(line))
print("-" * 100)
print(f"Partite finite verificate: {len(fin)} | 1x2 top-pick corretti: {n1x2_ok}/{n1x2}")
print(f"Partite con modello: {len(ok)}/{len(report)} | senza modello/errore: {len(err)}")
tot_sig = sum(x.get("n_signals", 0) for x in ok)
print(f"Segnali totali passati ai gate su tutta la card: {tot_sig}")
print("\nNOTA: campione finite minuscolo -> sanity, non significativita statistica.")
