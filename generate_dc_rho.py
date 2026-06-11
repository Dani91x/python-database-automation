#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate_dc_rho.py — Per-league Dixon-Coles ρ estimator (#11).

Estimates a league-specific Dixon-Coles correlation parameter ρ via a
1-parameter **profile maximum-likelihood**: the score marginals are held fixed
at the engine's own per-fixture λ (read from the stored
`fixture_predictions.db_json_analisi.inputs`), and ρ is the only free parameter.
Only the four low-scoring cells (0-0, 1-0, 0-1, 1-1) are affected by ρ, so the
likelihood and its normaliser have a closed form (no score grid needed).

Robustness:
  * Leagues with fewer than MIN_MATCHES_RHO usable fixtures are skipped entirely
    (they transparently fall back to the global DC_RHO in the engine).
  * The MLE is shrunk toward the global DC_RHO with strength K_RHO (empirical
    Bayes): a league needs a lot of data to move ρ meaningfully — exactly the
    behaviour we want for a subtle 2nd-order parameter.
  * The final value is clamped to [DC_RHO_MIN, DC_RHO_MAX]; the engine clamps
    again on read, so a corrupt file can never destabilise τ.

Output: dc_rho_by_league.json (atomic write) consumed by get_league_rho().

NOTE: ρ is a 2nd-order parameter and robust to small λ shifts, so estimating it
on the currently-stored λ is fine. Re-run this AFTER a full resync regenerates
db_json_analisi with refreshed λ to tighten the estimate (calibration cadence,
like dynamic_cal).
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile as _tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scipy.optimize import minimize_scalar
from scipy.stats import poisson

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Windows consoles default to cp1252 and crash on non-ASCII prints (rho, arrows).
# Force UTF-8 with a safe fallback so diagnostics never abort the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — older/loggless streams
        pass

from Prediction.today_predictions_backfill import (  # noqa: E402
    DC_RHO,
    DC_RHO_MIN,
    DC_RHO_MAX,
    _dc_tau,
)

# ── Tunables ────────────────────────────────────────────────────────────────
MIN_MATCHES_RHO = 300   # below this a league keeps the global DC_RHO
K_RHO = 300.0           # empirical-Bayes shrinkage strength (in matches)
PROB_FLOOR = 1e-12      # guard against log(0)


def _coerce_analisi(raw: Any) -> Optional[Dict[str, Any]]:
    """db_json_analisi may arrive as a dict (jsonb) or a JSON string."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None
    return None


def _extract_samples(rows: List[Dict[str, Any]]) -> Dict[int, List[Tuple[float, float, int, int]]]:
    """Group usable (lambda_home, lambda_away, goals_home, goals_away) per league."""
    by_league: Dict[int, List[Tuple[float, float, int, int]]] = {}
    skipped = 0
    for r in rows:
        league_id = r.get("league_id")
        analisi = _coerce_analisi(r.get("db_json_analisi"))
        if league_id is None or not analisi:
            skipped += 1
            continue
        inputs = analisi.get("inputs") or {}
        lh = inputs.get("lambda_home")
        la = inputs.get("lambda_away")
        gh = r.get("result_home_goals")
        ga = r.get("result_away_goals")
        if lh is None or la is None or gh is None or ga is None:
            skipped += 1
            continue
        try:
            lh_f = float(lh); la_f = float(la)
            gh_i = int(gh); ga_i = int(ga)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if lh_f <= 0 or la_f <= 0 or gh_i < 0 or ga_i < 0:
            skipped += 1
            continue
        by_league.setdefault(int(league_id), []).append((lh_f, la_f, gh_i, ga_i))
    if skipped:
        print(f"  (skipped {skipped} rows without usable lambda/result)")
    return by_league


def _neg_log_likelihood(rho: float, samples: List[Tuple[float, float, int, int]]) -> float:
    """Profile NLL of ρ given fixed per-fixture λ marginals.

    Independent Poisson sums to 1 over the infinite support, and τ deviates from
    1 only on the four low cells, so the per-fixture normaliser is exactly:
        Z = 1 + Σ_{4 cells} pmf_h·pmf_a·(τ−1)
    """
    total = 0.0
    for lh, la, gh, ga in samples:
        ph0 = poisson.pmf(0, lh); ph1 = poisson.pmf(1, lh)
        pa0 = poisson.pmf(0, la); pa1 = poisson.pmf(1, la)
        z = 1.0
        z += ph0 * pa0 * (_dc_tau(0, 0, lh, la, rho) - 1.0)
        z += ph1 * pa0 * (_dc_tau(1, 0, lh, la, rho) - 1.0)
        z += ph0 * pa1 * (_dc_tau(0, 1, lh, la, rho) - 1.0)
        z += ph1 * pa1 * (_dc_tau(1, 1, lh, la, rho) - 1.0)
        if z <= 0:
            return float("inf")  # degenerate ρ — reject
        base = poisson.pmf(gh, lh) * poisson.pmf(ga, la)
        # Near ρ=DC_RHO_MIN (−0.25), τ(1,0)/τ(0,1) are floored to 0 by _dc_tau for
        # fixtures with λ>4 (1/0.25). An observed (1,0)/(0,1) there hits PROB_FLOOR:
        # this is EXPECTED (it creates a steep penalty that pushes the MLE off the
        # bound toward a softer ρ), not a data-quality issue.
        p = base * _dc_tau(gh, ga, lh, la, rho) / z
        if p < PROB_FLOOR:
            p = PROB_FLOOR
        total -= math.log(p)
    return total


def estimate_league_rho(samples: List[Tuple[float, float, int, int]]) -> Tuple[float, float, int]:
    """Return (rho_final_shrunk_clamped, rho_mle_raw, n_matches)."""
    n = len(samples)
    res = minimize_scalar(
        _neg_log_likelihood,
        bounds=(DC_RHO_MIN, DC_RHO_MAX),
        args=(samples,),
        method="bounded",
        options={"xatol": 1e-4},
    )
    rho_mle = float(res.x)
    # Empirical-Bayes shrinkage toward the global prior. NB: if the bounded
    # optimiser returns a value at DC_RHO_MIN/MAX the true MLE is censored at the
    # bound; feeding the censored value into the shrinkage is intentionally
    # CONSERVATIVE (the result is pulled toward the prior, never past the bound).
    rho_shrunk = (n * rho_mle + K_RHO * DC_RHO) / (n + K_RHO)
    rho_final = max(DC_RHO_MIN, min(DC_RHO_MAX, rho_shrunk))
    return rho_final, rho_mle, n


def main() -> None:
    from master_backtest import fetch_completed_fixtures

    print("=== generate_dc_rho.py — per-league Dixon-Coles ρ ===")
    rows = fetch_completed_fixtures()
    by_league = _extract_samples(rows)
    print(f"Leagues with data: {len(by_league)}")

    rho_by_league: Dict[str, float] = {}
    diagnostics: List[Dict[str, Any]] = []
    estimated = 0
    skipped_low_n = 0
    for league_id, samples in sorted(by_league.items()):
        if len(samples) < MIN_MATCHES_RHO:
            # Visible per-league reason: avoids confusing "league has rows but was
            # not estimated" with "league had no data at all".
            print(f"  league {league_id:>6}: n={len(samples):>5}  < {MIN_MATCHES_RHO} → global ρ fallback")
            skipped_low_n += 1
            continue
        rho_final, rho_mle, n = estimate_league_rho(samples)
        rho_by_league[str(league_id)] = round(rho_final, 4)
        diagnostics.append({
            "league_id": league_id, "n": n,
            "rho_mle": round(rho_mle, 4), "rho_final": round(rho_final, 4),
        })
        estimated += 1
        print(f"  league {league_id:>6}: n={n:>5}  ρ_mle={rho_mle:+.4f}  ρ_final={rho_final:+.4f}")

    output = {
        "rho_by_league": rho_by_league,
        "global_fallback": DC_RHO,
        "band": [DC_RHO_MIN, DC_RHO_MAX],
        "min_matches": MIN_MATCHES_RHO,
        "shrink_k": K_RHO,
        "leagues_estimated": estimated,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostics": diagnostics,
    }

    target_path = PROJECT_ROOT / "dc_rho_by_league.json"
    tmp_path = None
    try:
        fd, tmp_path = _tempfile.mkstemp(suffix=".tmp", dir=str(PROJECT_ROOT))
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            json.dump(output, tmp_f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, str(target_path))
        print(f"\n✅ dc_rho_by_league.json written ({estimated} leagues estimated, "
              f"{skipped_low_n} below {MIN_MATCHES_RHO} matches → global ρ={DC_RHO}).")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error writing dc_rho_by_league.json: {e}")
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
