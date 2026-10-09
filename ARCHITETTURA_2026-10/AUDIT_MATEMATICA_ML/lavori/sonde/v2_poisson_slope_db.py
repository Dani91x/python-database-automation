"""V2 A3: replica indipendente su un'altra finestra: pendenza di calibrazione O2.5 grezza.
UNA sola SELECT, LIMIT 500, sola lettura."""
import sys, numpy as np
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from db_client import get_supabase_client
DA, A = sys.argv[1], sys.argv[2]
sb = get_supabase_client()
rows = (sb.table("fixture_predictions")
        .select("fixture_id,fixture_date,result_home_goals,result_away_goals,m:db_json_analisi->markets,mc:db_json_analisi->markets_calibrated,model:db_json_analisi->>model")
        .eq("result_status_short", "FT").gte("fixture_date", DA).lt("fixture_date", A)
        .not_.is_("db_json_analisi", "null").order("fixture_id", desc=True).limit(500).execute().data or [])
print("righe", len(rows), "date", min(r["fixture_date"] for r in rows)[:10] if rows else None, max(r["fixture_date"] for r in rows)[:10] if rows else None)
for key, lab in (("m", "GREZZE"), ("mc", "CALIBRATE")):
    P=[];Y=[]
    for r in rows:
        x=((r.get(key) or {}).get("over_2_5") or {}).get("True")
        if x is None or r.get("result_home_goals") is None: continue
        P.append(float(x)); Y.append(1.0 if r["result_home_goals"]+r["result_away_goals"]>=3 else 0.0)
    P=np.array(P);Y=np.array(Y)
    if len(P)<50: print(lab,"troppo pochi",len(P)); continue
    # regressione logistica freq ~ sigmoid(a+b*logit p) via Newton
    z=np.log(P/(1-P)); X=np.vstack([np.ones_like(z),z]).T; b=np.array([0.,1.])
    for _ in range(50):
        mu=1/(1+np.exp(-X@b)); W=mu*(1-mu); g=X.T@(Y-mu); H=X.T@(W[:,None]*X); b=b+np.linalg.solve(H,g)
    se=np.sqrt(np.diag(np.linalg.inv(H)))
    print(f"{lab}: n={len(P)} p media={P.mean():.3f} freq={Y.mean():.3f} Brier={np.mean((P-Y)**2):.4f} pendenza logistica={b[1]:.3f}+-{se[1]:.3f} (1=calibrato) intercetta={b[0]:+.3f}")
