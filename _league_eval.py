"""
_league_eval.py — TEST ONESTO: il PER-LEGA migliora, o e' rumore?

Confronto out-of-sample (split temporale):
  GLOBAL  = hit-rate della fascia Poisson calcolato su TUTTE le leghe
  LEAGUE  = hit-rate per-lega con shrinkage empirical-Bayes verso il globale
            (lega con pochi dati -> conta il globale; con molti -> conta la lega)

Metriche (piu' basso = meglio): Brier e log-loss sul periodo di TEST.
Se LEAGUE non batte GLOBAL -> il per-lega e' rumore, si usa solo il globale.

Uso: python _league_eval.py
"""
import sys, math
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd

EPS = 1e-4
K = 50  # forza dello shrinkage (peso del prior globale, in "partite equivalenti")
BINS = [0, .30, .40, .50, .60, .70, 1.01]
LBL = ["<.30", ".30-.40", ".40-.50", ".50-.60", ".60-.70", ">.70"]
CAL_MARKETS = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]


def bucket(p):
    for lo, hi, l in zip(BINS, BINS[1:], LBL):
        if lo <= p < hi or (l == LBL[-1] and p >= lo):
            return l
    return None


def brier(p, y): return float(np.mean((np.array(p) - np.array(y)) ** 2))
def logloss(p, y):
    p = np.clip(np.array(p), EPS, 1 - EPS); y = np.array(y)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def load():
    from db_client import get_supabase_client
    sb = get_supabase_client()
    rows, start = [], 0
    while True:
        d = (sb.table("bet_features")
             .select("kickoff,league_id,market,selection,poisson_prob,hit")
             .eq("settled", True).in_("market", CAL_MARKETS)
             .not_.is_("poisson_prob", "null").not_.is_("league_id", "null")
             .order("kickoff").range(start, start + 999).execute().data)
        rows.extend(d)
        if len(d) < 1000:
            break
        start += 1000
    return pd.DataFrame(rows)


def main():
    df = load()
    df = df.dropna(subset=["poisson_prob", "hit", "kickoff", "league_id"]).copy()
    df["hit"] = df["hit"].astype(bool).astype(int)
    df["bucket"] = df["poisson_prob"].astype(float).map(bucket)
    df["key"] = df["market"] + "|" + df["selection"].astype(str) + "|" + df["bucket"].astype(str)
    df = df.sort_values("kickoff")
    cut = int(len(df) * 0.70)
    tr, te = df.iloc[:cut], df.iloc[cut:]

    # TABELLE su TRAIN
    g = tr.groupby("key")["hit"].agg(["mean", "count"]).rename(columns={"mean": "p", "count": "n"})
    glob = g["p"].to_dict()
    lk = tr.groupby(["key", "league_id"])["hit"].agg(["mean", "count"])

    pred_g, pred_l, y = [], [], []
    skipped = 0
    for _, r in te.iterrows():
        k = r["key"]
        if k not in glob:
            skipped += 1
            continue
        pg = glob[k]
        # per-lega con shrinkage verso il globale
        if (k, r["league_id"]) in lk.index:
            row = lk.loc[(k, r["league_id"])]
            nl, pl = row["count"], row["mean"]
        else:
            nl, pl = 0, pg
        pl_shrunk = (nl * pl + K * pg) / (nl + K)
        pred_g.append(pg); pred_l.append(pl_shrunk); y.append(r["hit"])

    print(f"Dati: {len(df)} righe | train {cut} / test {len(te)} | usate {len(y)} (skip {skipped} fasce nuove)\n")
    bg, bl = brier(pred_g, y), brier(pred_l, y)
    lg, ll = logloss(pred_g, y), logloss(pred_l, y)
    print(f"{'metodo':18}{'Brier':>10}{'logloss':>10}")
    print(f"{'GLOBAL':18}{bg:>10.4f}{lg:>10.4f}")
    print(f"{'LEAGUE+shrink':18}{bl:>10.4f}{ll:>10.4f}")
    imp_b = (bg - bl) / bg * 100
    imp_l = (lg - ll) / lg * 100
    verdetto = "MEGLIO ✅ -> USARE per-lega" if (imp_b > 0.3 and imp_l > 0.3) else "rumore ❌ -> SOLO globale"
    print(f"\nper-lega vs globale:  Brier {imp_b:+.1f}%   logloss {imp_l:+.1f}%   => {verdetto}")


if __name__ == "__main__":
    main()
