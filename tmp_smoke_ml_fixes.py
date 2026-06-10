"""
Standalone smoke test for the ML-audit fixes (no DB required).

Validates:
  A) targets.py  — H1 (target_ht_ft None when a half is missing) and the
     unplayed-match label problem + the C2 filter that removes them.
  B) build_ensemble + predict_ensemble on MEDIUM-tier synthetic multiclass data
     — temperature-scaling calibration present, probabilities sum to 1.
  C) _train_one_target full refactored flow (no-impute _build_features,
     train-only medians, holdout metrics via predict_ensemble) for a multiclass
     and a binary target — returns a result, metrics sane, model saved.

Run: .venv/Scripts/python.exe tmp_smoke_ml_fixes.py
"""
from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "Ai Engine"))

from ai_engine import targets as T
from ai_engine.ensemble_trainer import build_ensemble, predict_ensemble
from ai_engine.seriea_model_export import _train_one_target

RNG = np.random.default_rng(42)
_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    status = "OK  " if cond else "FAIL"
    print(f"  [{status}] {msg}")
    if not cond:
        _failures.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
# A) targets.py
# ─────────────────────────────────────────────────────────────────────────────
def test_targets() -> None:
    print("\n== A) targets.py ==")
    df = pd.DataFrame(
        {
            "goals_home": [2, 1, np.nan, 0],   # row 2 = unplayed (NULL goals)
            "goals_away": [1, 1, np.nan, 0],
            "halftime_home": [1, np.nan, np.nan, 0],  # row 1 = HT missing, FT present
            "halftime_away": [0, np.nan, np.nan, 0],
            "fulltime_home": [2, 1, np.nan, 0],
            "fulltime_away": [1, 1, np.nan, 0],
        }
    )
    out = T.add_targets_from_matches(df)

    # H1: row 0 has both halves -> "H_H"; row 1 HT missing -> None; row 2 unplayed -> None
    htft = out["target_ht_ft"].tolist()
    check(htft[0] == "H_H", f"ht_ft row0 == 'H_H' (got {htft[0]!r})")
    # NaN or None both satisfy H1: dropna(subset=['target_ht_ft']) removes either.
    check(pd.isna(htft[1]), f"ht_ft row1 (HT missing) is null (got {htft[1]!r})")
    check(pd.isna(htft[2]), f"ht_ft row2 (unplayed) is null (got {htft[2]!r})")
    check(
        not any(isinstance(v, str) and v.startswith("_") for v in htft if v is not None),
        "no spurious '_X' classes in target_ht_ft",
    )

    # C2: the unplayed row (NaN goals) yields a non-null False label for btts/over.
    # The fix lives in train_and_save_all; here we confirm the filter mask removes it.
    played = (
        pd.to_numeric(out["goals_home"], errors="coerce").notna()
        & pd.to_numeric(out["goals_away"], errors="coerce").notna()
    )
    check(bool(played.tolist() == [True, True, False, True]), "played mask flags unplayed row only")
    # Before filter: unplayed row has btts==False (the bug). After filter: removed.
    check(out.loc[2, "target_btts"] == False, "unplayed row produces spurious btts=False (pre-filter)")  # noqa: E712
    kept = out[played]
    check(len(kept) == 3 and 2 not in kept.index, "C2 filter removes the unplayed row")


# ─────────────────────────────────────────────────────────────────────────────
# synthetic feature/target frame
# ─────────────────────────────────────────────────────────────────────────────
def _make_dataset(n: int, start: str = "2022-08-01") -> pd.DataFrame:
    """Build a synthetic pre-match-style dataframe with signal."""
    dates = pd.date_range(start, periods=n, freq="D")
    # Two informative features + noise + a high-NaN column to exercise the drop.
    f_strength = RNG.normal(0, 1, n)        # home strength
    f_form = RNG.normal(0, 1, n)
    noise = RNG.normal(0, 1, (n, 4))
    sparse = np.where(RNG.random(n) < 0.7, np.nan, RNG.normal(0, 1, n))  # >50% NaN

    # Outcome driven by strength+form (so models can learn something).
    logit = 0.9 * f_strength + 0.6 * f_form + RNG.normal(0, 0.7, n)
    gh = np.clip(np.round(1.4 + 0.8 * logit + RNG.normal(0, 0.6, n)), 0, 6).astype(int)
    ga = np.clip(np.round(1.3 - 0.5 * logit + RNG.normal(0, 0.6, n)), 0, 6).astype(int)

    df = pd.DataFrame(
        {
            "fixture_date": dates,
            "feat_strength": f_strength,
            "feat_form": f_form,
            "feat_n0": noise[:, 0],
            "feat_n1": noise[:, 1],
            "feat_n2": noise[:, 2],
            "feat_n3": noise[:, 3],
            "feat_sparse": sparse,
            "goals_home": gh,
            "goals_away": ga,
            "halftime_home": np.clip(gh - RNG.integers(0, 2, n), 0, None),
            "halftime_away": np.clip(ga - RNG.integers(0, 2, n), 0, None),
            "fulltime_home": gh,
            "fulltime_away": ga,
        }
    )
    return T.add_targets_from_matches(df)


def _drop_cols(df: pd.DataFrame) -> list[str]:
    base = [
        "fixture_date", "goals_home", "goals_away",
        "halftime_home", "halftime_away", "fulltime_home", "fulltime_away",
        "target_total_goals", "target_exact_score",
    ]
    base += [c for c in df.columns if c.startswith("target_")]
    return base


# ─────────────────────────────────────────────────────────────────────────────
# B) build_ensemble + predict_ensemble (MEDIUM tier, no optuna)
# ─────────────────────────────────────────────────────────────────────────────
def test_build_predict() -> None:
    print("\n== B) build_ensemble + predict_ensemble (MEDIUM multiclass) ==")
    df = _make_dataset(480)
    feats = ["feat_strength", "feat_form", "feat_n0", "feat_n1", "feat_n2", "feat_n3"]
    y = df["target_1x2"]
    mask = y.notna()
    df, y = df[mask], y[mask]
    cut = int(len(df) * 0.8)
    Xtr, ytr = df[feats].iloc[:cut], y.iloc[:cut]
    Xva, yva = df[feats].iloc[cut:], y.iloc[cut:]

    payload = build_ensemble(
        Xtr, ytr, Xva, yva,
        feature_cols=feats,
        feature_medians={c: 0.0 for c in feats},
        train_dates=df["fixture_date"].iloc[:cut],
        optuna_params={}, tier="MEDIUM", n_jobs=1,
    )
    check(payload is not None, "build_ensemble returned a payload")
    check(len(payload.base_models) >= 2, f">=2 base models (got {[n for n,_ in payload.base_models]})")

    probs = predict_ensemble(payload, Xva.iloc[[0]])
    s = sum(probs.values())
    check(abs(s - 1.0) < 1e-6, f"predict_ensemble probabilities sum to 1 (got {s:.6f})")
    check(all(0.0 <= v <= 1.0 for v in probs.values()), "all probabilities in [0,1]")
    cals = payload.isotonic_calibrators or {}
    check("__temperature_scaling__" in cals, f"multiclass uses temperature scaling (keys={list(cals)})")


# ─────────────────────────────────────────────────────────────────────────────
# C) _train_one_target full refactored flow (TINY tier, no optuna)
# ─────────────────────────────────────────────────────────────────────────────
def test_train_one_target() -> None:
    print("\n== C) _train_one_target full flow (TINY, no optuna) ==")
    df = _make_dataset(180)  # train ~135 -> TINY -> optuna disabled
    drop = _drop_cols(df)
    with tempfile.TemporaryDirectory() as tmp:
        for target, kind in [("target_1x2", "multiclass"), ("target_over_2_5", "binary")]:
            res = _train_one_target(target, df.copy(), drop, 999, [2022, 2023], tmp, n_jobs=1)
            check(res is not None, f"[{target}] _train_one_target returned a result ({kind})")
            if res is None:
                continue
            brier = res.get("brier")
            ece = res.get("ece")
            check(brier is None or (0.0 <= brier <= 2.0), f"[{target}] brier sane (got {brier})")
            check(ece is None or (0.0 <= ece <= 1.0), f"[{target}] ece sane (got {ece})")
            check(os.path.exists(res["model_path"]), f"[{target}] model file written")
            check(res["feature_count"] >= 1, f"[{target}] >=1 selected feature")
            # 'feat_sparse' (>50% NaN) must be droppable train-only without crashing
            check(res["train_rows"] > 0, f"[{target}] train_rows > 0")


if __name__ == "__main__":
    test_targets()
    test_build_predict()
    test_train_one_target()
    print("\n" + "=" * 60)
    if _failures:
        print(f"SMOKE TEST FAILED — {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"   - {f}")
        sys.exit(1)
    print("SMOKE TEST PASSED — all checks green.")
