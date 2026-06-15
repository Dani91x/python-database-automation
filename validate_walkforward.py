"""validate_walkforward.py — VALIDAZIONE (sola lettura, nessuna scrittura DB/storage).

Confronta, per ogni lega, la config VECCHIA (3 stagioni, modello libero) vs NUOVA
(storico pieno + regolarizzazione) in walk-forward: per ogni stagione di test S si
allena su quanto disponibile PRIMA di S e si testa su S (partite mai viste).

Metriche: accuratezza, Brier (classe positiva), RPS (1x2 ordinale), confronto con la
base rate. Serve a CERTIFICARE che usare lo storico pieno ripara l'overfitting prima
di lanciare il retrain di massa. NON tocca il DB in scrittura, NON carica modelli.

Uso:  python validate_walkforward.py --leagues 39,140 --test-seasons 3
"""
from __future__ import annotations
import argparse, sys, warnings, os
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))
sys.path.insert(0, ROOT)
from ai_engine.training_dataset import build_training_dataset
from ai_engine.db_adapter import fetch_seasons_for_league
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, brier_score_loss

TARGETS = ["target_over_2_5", "target_btts", "target_1x2"]
DROP_PREFIX = ("home_standings_", "away_standings_", "home_events_", "away_events_",
               "home_stats_", "away_stats_", "home_players_", "away_players_")
DROP_FIXED = ["fixture_id", "league_id", "league_name", "season_year", "fixture_date",
              "home_team_name", "away_team_name", "status", "goals_home", "goals_away",
              "halftime_home", "halftime_away", "fulltime_home", "fulltime_away",
              "winner_name", "advice"]


def _feat_cols(df):
    drop = [c for c in df.columns if c.startswith("target_") or c.endswith("_team_id")
            or c.endswith("_fixture_id") or c.startswith(DROP_PREFIX)] + DROP_FIXED
    return [c for c in df.columns if c not in drop]


def _rps_1x2(proba, y_true, classes):
    # ordine ordinale H, D, A
    order = [c for c in ["H", "D", "A"] if c in classes]
    idx = [classes.index(c) for c in order]
    P = proba[:, idx]
    O = np.zeros_like(P)
    cls_to_pos = {c: i for i, c in enumerate(order)}
    for r, yt in enumerate(y_true):
        if yt in cls_to_pos:
            O[r, cls_to_pos[yt]] = 1.0
    cumP = np.cumsum(P, axis=1); cumO = np.cumsum(O, axis=1)
    return float(np.mean(np.sum((cumP - cumO) ** 2, axis=1) / (len(order) - 1)))


def _make_model(reg):
    if reg:
        return GradientBoostingClassifier(random_state=0, max_depth=2, n_estimators=120,
                                          learning_rate=0.03, subsample=0.7, min_samples_leaf=40)
    return GradientBoostingClassifier(random_state=0)


def _fit_eval(df_tr, df_te, tcol, reg):
    feats = _feat_cols(df_tr)
    Xtr = df_tr[feats].select_dtypes(include=["number", "bool"]).copy()
    feats = list(Xtr.columns)
    med = Xtr.median()
    Xtr = Xtr.fillna(med).fillna(0)
    Xte = df_te[feats].fillna(med).fillna(0)
    sc = StandardScaler().fit(Xtr)
    ytr = df_tr[tcol].astype(str); yte = df_te[tcol].astype(str)
    if ytr.nunique() < 2 or len(df_te) < 10:
        return None
    m = _make_model(reg).fit(sc.transform(Xtr), ytr)
    classes = list(m.classes_)
    proba = m.predict_proba(sc.transform(Xte))
    acc = accuracy_score(yte, m.predict(sc.transform(Xte)))
    base = yte.value_counts(normalize=True).max()
    out = {"n_test": len(df_te), "acc": acc, "base": base}
    if tcol == "target_1x2":
        out["rps"] = _rps_1x2(proba, list(yte), classes)
    else:
        pos = "True"
        if pos in classes:
            p = proba[:, classes.index(pos)]
            out["brier"] = brier_score_loss((yte == pos).astype(int), p)
    return out


def validate_league(lid, test_seasons):
    seasons = fetch_seasons_for_league(lid)
    if len(seasons) < 4:
        print(f"[{lid}] solo {len(seasons)} stagioni, salto"); return
    print(f"\n========== LEGA {lid} — {len(seasons)} stagioni {seasons[0]}..{seasons[-1]} ==========", flush=True)
    df = build_training_dataset([(lid, s) for s in seasons])
    df = df[pd.to_numeric(df.get("goals_home"), errors="coerce").notna()
            & pd.to_numeric(df.get("goals_away"), errors="coerce").notna()].copy()
    df["season_year"] = df["season_year"].astype(int)
    print(f"[{lid}] partite giocate totali: {len(df)}", flush=True)
    test_yrs = sorted(df["season_year"].unique())[-test_seasons:]
    for tcol in TARGETS:
        agg = {"OLD(3 stag)": [], "NEW(pieno+reg)": []}
        for S in test_yrs:
            te = df[df["season_year"] == S]
            old_tr = df[(df["season_year"] < S) & (df["season_year"] >= S - 3)]
            new_tr = df[df["season_year"] < S]
            if len(old_tr) < 100 or len(new_tr) < 100:
                continue
            r_old = _fit_eval(old_tr, te, tcol, reg=False)
            r_new = _fit_eval(new_tr, te, tcol, reg=True)
            if r_old: agg["OLD(3 stag)"].append(r_old)
            if r_new: agg["NEW(pieno+reg)"].append(r_new)
        print(f"\n  --- {tcol} (walk-forward su {test_yrs}) ---", flush=True)
        for cfg, runs in agg.items():
            if not runs: continue
            acc = np.mean([r["acc"] for r in runs]); base = np.mean([r["base"] for r in runs])
            extra = ""
            if "brier" in runs[0]: extra = f" | Brier {np.mean([r['brier'] for r in runs]):.3f}"
            if "rps" in runs[0]: extra = f" | RPS {np.mean([r['rps'] for r in runs]):.4f}"
            print(f"    {cfg:16}: acc test {acc:.1%} (base {base:.1%}, edge {acc-base:+.1%}){extra}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", required=True)
    ap.add_argument("--test-seasons", type=int, default=3)
    a = ap.parse_args()
    ids = [int(x) for x in a.leagues.split(",") if x.strip().isdigit()]
    print(f"VALIDAZIONE walk-forward — leghe {ids}, test-seasons {a.test_seasons}", flush=True)
    for lid in ids:
        try:
            validate_league(lid, a.test_seasons)
        except Exception as e:
            print(f"[{lid}] ERRORE: {e}", flush=True)
    print("\nVALIDAZIONE COMPLETATA", flush=True)


if __name__ == "__main__":
    main()
