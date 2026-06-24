"""
_stack_eval.py — TEST ONESTO: lo stacking migliora davvero?

Confronto out-of-sample (split TEMPORALE, niente leak):
  A) Poisson grezzo          (la prob del motore, cosi' com'e')
  B) Poisson calibrato       ("metodo di oggi": 1 motore, ricalibrato)
  C) Stack Poisson + ML      (i due motori combinati con logistica)

Metriche (piu' BASSO = meglio): Brier score e log-loss.
Se C non batte B fuori campione -> lo stacking NON serve, si butta.

Uso: python _stack_eval.py
"""
import sys, json
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression

EPS = 1e-4
CAL_MARKETS = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def load():
    from db_client import get_supabase_client
    sb = get_supabase_client()
    rows, start = [], 0
    while True:
        d = (sb.table("bet_features")
             .select("fixture_id,kickoff,market,selection,poisson_prob,ml_prob,hit")
             .eq("settled", True).in_("market", CAL_MARKETS)
             .not_.is_("poisson_prob", "null").not_.is_("ml_prob", "null")
             .order("kickoff").range(start, start + 999).execute().data)
        rows.extend(d)
        if len(d) < 1000:
            break
        start += 1000
    return pd.DataFrame(rows)


def evaluate(df, label):
    df = df.dropna(subset=["poisson_prob", "ml_prob", "hit", "kickoff"]).copy()
    df["hit"] = df["hit"].astype(bool).astype(int)
    df = df.sort_values("kickoff")
    n = len(df)
    if n < 200:
        return None
    cut = int(n * 0.70)
    tr, te = df.iloc[:cut], df.iloc[cut:]
    ytr, yte = tr["hit"].values, te["hit"].values

    pois_tr, pois_te = tr["poisson_prob"].values.astype(float), te["poisson_prob"].values.astype(float)
    ml_tr, ml_te = tr["ml_prob"].values.astype(float), te["ml_prob"].values.astype(float)

    # A) Poisson grezzo
    a = {"brier": brier(pois_te, yte), "logloss": logloss(pois_te, yte)}

    # B) Poisson calibrato (1 feature: logit poisson)
    mb = LogisticRegression().fit(logit(pois_tr).reshape(-1, 1), ytr)
    pb = mb.predict_proba(logit(pois_te).reshape(-1, 1))[:, 1]
    b = {"brier": brier(pb, yte), "logloss": logloss(pb, yte)}

    # C) Stack Poisson + ML (2 feature)
    Xtr = np.column_stack([logit(pois_tr), logit(ml_tr)])
    Xte = np.column_stack([logit(pois_te), logit(ml_te)])
    mc = LogisticRegression().fit(Xtr, ytr)
    pc = mc.predict_proba(Xte)[:, 1]
    c = {"brier": brier(pc, yte), "logloss": logloss(pc, yte)}

    imp_brier = (b["brier"] - c["brier"]) / b["brier"] * 100
    imp_logloss = (b["logloss"] - c["logloss"]) / b["logloss"] * 100
    return {"label": label, "n_train": cut, "n_test": n - cut,
            "A_poisson_grezzo": a, "B_poisson_calibrato": b, "C_stack_poisson_ml": c,
            "stack_vs_solo_poisson": {"brier_%": round(imp_brier, 1), "logloss_%": round(imp_logloss, 1),
                                      "pesi_stack": [round(float(w), 3) for w in mc.coef_[0]]}}


def main():
    df = load()
    df = df.dropna(subset=["kickoff"])
    ks = df["kickoff"].astype(str)
    print(f"Dati: {len(df)} righe, {df['fixture_id'].nunique()} partite, "
          f"da {ks.min()[:10]} a {ks.max()[:10]}\n")

    results = {"POOLED (tutti i mercati)": evaluate(df, "pooled")}
    for mk in ["1x2", "over_2_5", "btts"]:
        r = evaluate(df[df.market == mk], mk)
        if r:
            results[mk] = r

    for name, r in results.items():
        if not r:
            continue
        print(f"=== {name}  (train {r['n_train']} / test {r['n_test']}) ===")
        print(f"  {'metodo':24} {'Brier':>8} {'logloss':>9}")
        for k in ["A_poisson_grezzo", "B_poisson_calibrato", "C_stack_poisson_ml"]:
            print(f"  {k:24} {r[k]['brier']:8.4f} {r[k]['logloss']:9.4f}")
        s = r["stack_vs_solo_poisson"]
        verdetto = "MEGLIO ✅" if s["brier_%"] > 0 and s["logloss_%"] > 0 else "NON migliora ❌"
        print(f"  -> stack vs solo-Poisson: Brier {s['brier_%']:+}%  logloss {s['logloss_%']:+}%  {verdetto}")
        print(f"     pesi [poisson, ml] = {s['pesi_stack']}\n")


if __name__ == "__main__":
    main()
