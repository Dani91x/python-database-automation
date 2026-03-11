"""
signals.py ? Phase 3: Signal Validation

Valida storicamente due segnali:
  1. ML Divergence: quando ML diverge dal bookie, chi ha ragione?
  2. xG Residual:   il xG delle squadre correla con il risultato finale?

Output: cache/signal_weights.json

Uso:
    python pipeline.py --signals
"""
import sys, json, os, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_supabase_client
from market_intelligence.mi_config import (
    CACHE_DIR, REGISTRY_FILE, SIGNAL_WEIGHTS_FILE,
    MARKETS, ML_DIV_MIN_EDGE, ML_DIV_MIN_SAMPLE,
    XG_MIN_COVERAGE, XG_MIN_SAMPLE,
    DEFAULT_WEIGHT_ML_DIV, DEFAULT_WEIGHT_XG
)

CACHE_DIR.mkdir(exist_ok=True)


# -- Helpers ----------------------------------------------------------------

def _get_ml_prob(db_json_analisi: dict, ml_market: str, ml_key: str) -> float | None:
    """
    Estrae probabilita ML da db_json_analisi.markets.
    Gestisce sia formato 0-1 che formato percentuale (>1 -> divide per 100).
    """
    if not isinstance(db_json_analisi, dict):
        return None
    markets = db_json_analisi.get("markets") or {}
    sub = markets.get(ml_market) or {}
    val = sub.get(ml_key)
    if val is None:
        return None
    try:
        v = float(val)
        return v / 100.0 if v > 1.0 else v
    except (TypeError, ValueError):
        return None


def _parse_bookie_odd(raw_json_odds: dict, market_cfg: dict) -> float | None:
    """Estrae la quota decimale per un mercato specifico."""
    if not isinstance(raw_json_odds, dict):
        return None
    bookmakers = raw_json_odds.get("bookmakers", [])
    if not bookmakers:
        return None
    for bet in bookmakers[0].get("bets", []):
        if bet.get("name") == market_cfg["bet_name"]:
            for v in bet.get("values", []):
                if v.get("value") == market_cfg["value"]:
                    try:
                        odd = float(v["odd"])
                        return odd if odd > 1.0 else None
                    except (KeyError, ValueError, TypeError):
                        return None
    return None


def _compute_outcome(gh: int, ga: int, result_fn: str) -> int | None:
    if gh is None or ga is None:
        return None
    total = gh + ga
    return {
        "home_win": 1 if gh > ga else 0,
        "draw":     1 if gh == ga else 0,
        "away_win": 1 if gh < ga else 0,
        "over25":   1 if total > 2.5 else 0,
        "under25":  1 if total < 2.5 else 0,
        "btts_yes": 1 if gh > 0 and ga > 0 else 0,
        "btts_no":  1 if not (gh > 0 and ga > 0) else 0,
    }.get(result_fn)


def _spearman_r(x: list, y: list) -> float:
    """Spearman rank correlation (no scipy). Ritorna 0.0 se n < 3."""
    n = len(x)
    if n < 3:
        return 0.0

    def _rank(arr):
        sorted_idx = sorted(range(n), key=lambda i: arr[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j < n - 1 and arr[sorted_idx[j + 1]] == arr[sorted_idx[j]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = _rank(x), _rank(y)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num   = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


# -- Fetch --------------------------------------------------------------------

def _fetch_rows(sb, league_ids: list) -> list:
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, league_id, home_team_id, away_team_id, "
            "raw_json_odds, db_json_analisi, "
            "result_status_short, result_home_goals, result_away_goals"
        ).in_("league_id", league_ids).in_(
            "result_status_short", ["FT", "AET", "PEN"]
        ).range(offset, offset + page_size - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _fetch_xg_map(sb, fixture_ids: list) -> dict:
    """
    Ritorna {fixture_id: {"home_xg": float, "away_xg": float}}.
    Usa home_team_id / away_team_id per distinguere casa/trasferta.
    """
    # Prima: team_id -> home/away mapping da fixture_predictions
    match_map = {}
    for i in range(0, len(fixture_ids), 200):
        chunk = fixture_ids[i:i + 200]
        resp = sb.table("fixture_predictions").select(
            "fixture_id, home_team_id, away_team_id"
        ).in_("fixture_id", chunk).execute()
        for r in (resp.data or []):
            match_map[r["fixture_id"]] = {
                "home_tid": r.get("home_team_id"),
                "away_tid": r.get("away_team_id"),
            }

    # Poi: xG da match_team_stats
    xg_raw = defaultdict(list)
    for i in range(0, len(fixture_ids), 200):
        chunk = fixture_ids[i:i + 200]
        resp = sb.table("match_team_stats").select(
            "fixture_id, team_id, value_numeric"
        ).eq("stat_type", "Expected Goals").in_("fixture_id", chunk).execute()
        for r in (resp.data or []):
            xg_raw[r["fixture_id"]].append(r)

    # Combina
    xg_map = {}
    for fid, entries in xg_raw.items():
        mm = match_map.get(fid, {})
        home_tid = mm.get("home_tid")
        away_tid = mm.get("away_tid")
        entry = {}
        for e in entries:
            val = e.get("value_numeric")
            if val is None:
                continue
            if e.get("team_id") == home_tid:
                entry["home_xg"] = float(val)
            elif e.get("team_id") == away_tid:
                entry["away_xg"] = float(val)
        if entry:
            xg_map[fid] = entry
    return xg_map


# -- Signal 1: ML Divergence -------------------------------------------------

def _validate_ml_divergence(rows: list) -> dict:
    """
    Per ogni mercato: quando |ML - implied| > soglia, il ML aveva ragione?
    Confronta win rate con segnale vs win rate base.
    """
    results = {}

    for mkey, mcfg in MARKETS.items():
        base_n = base_wins = 0
        sig_n  = sig_wins  = 0
        divergences = []

        for row in rows:
            gh = row.get("result_home_goals")
            ga = row.get("result_away_goals")
            if gh is None or ga is None:
                continue
            gh, ga = int(gh), int(ga)

            odd = _parse_bookie_odd(row.get("raw_json_odds") or {}, mcfg)
            if odd is None:
                continue
            ml_prob = _get_ml_prob(
                row.get("db_json_analisi") or {},
                mcfg["ml_market"],
                mcfg["ml_key"]
            )
            if ml_prob is None:
                continue

            outcome = _compute_outcome(gh, ga, mcfg["result_fn"])
            if outcome is None:
                continue

            implied = 1.0 / odd
            div = ml_prob - implied  # positivo = ML ottimista rispetto al bookie

            base_n    += 1
            base_wins += outcome
            divergences.append((div, outcome))

            if abs(div) >= ML_DIV_MIN_EDGE:
                sig_n    += 1
                sig_wins += outcome

        if base_n < 10:
            continue

        base_rate = base_wins / base_n
        sig_rate  = sig_wins / sig_n if sig_n > 0 else None

        # Spearman: divergenza vs outcome
        divs    = [d[0] for d in divergences]
        outcomes = [d[1] for d in divergences]
        spearman = _spearman_r(divs, outcomes)

        lift    = (sig_rate - base_rate) if sig_rate is not None else None
        trusted = (
            sig_n >= ML_DIV_MIN_SAMPLE and
            lift is not None and
            abs(lift) >= 0.03
        )

        results[mkey] = {
            "n_total":     base_n,
            "base_rate":   round(base_rate, 4),
            "n_signals":   sig_n,
            "signal_rate": round(sig_rate, 4) if sig_rate else None,
            "lift":        round(lift, 4) if lift is not None else None,
            "spearman_r":  round(spearman, 4),
            "trusted":     trusted,
        }

    return results


# -- Signal 2: xG Residual ---------------------------------------------------

def _validate_xg_signal(rows: list, xg_map: dict) -> dict:
    """
    xg_diff = home_xg - away_xg
    goal_diff = gh - ga
    Spearman(xg_diff, goal_diff) -> correlazione xG vs risultato
    """
    n_total = len(rows)
    xg_diffs   = []
    goal_diffs = []
    home_win_by_xg_bucket = defaultdict(lambda: {"n": 0, "wins": 0})

    for row in rows:
        fid = row.get("fixture_id")
        xg  = xg_map.get(fid)
        if not xg:
            continue
        gh = row.get("result_home_goals")
        ga = row.get("result_away_goals")
        if gh is None or ga is None:
            continue
        gh, ga = int(gh), int(ga)

        home_xg = xg.get("home_xg", 0.0)
        away_xg = xg.get("away_xg", 0.0)
        xg_diff   = home_xg - away_xg
        goal_diff = gh - ga

        xg_diffs.append(xg_diff)
        goal_diffs.append(goal_diff)

        # Bucket per leggibilita
        if xg_diff >= 1.0:    bucket = "xG_home_dominant (>=1.0)"
        elif xg_diff >= 0.4:  bucket = "xG_home_advantage (0.4-1.0)"
        elif xg_diff >= -0.4: bucket = "xG_balanced (+-0.4)"
        elif xg_diff >= -1.0: bucket = "xG_away_advantage (-1.0 / -0.4)"
        else:                 bucket = "xG_away_dominant (<-1.0)"

        home_win_by_xg_bucket[bucket]["n"] += 1
        home_win_by_xg_bucket[bucket]["wins"] += (1 if gh > ga else 0)

    n_with_xg  = len(xg_diffs)
    coverage   = n_with_xg / n_total if n_total > 0 else 0.0
    spearman   = _spearman_r(xg_diffs, goal_diffs) if n_with_xg >= 3 else 0.0
    mean_abs_r = (sum(abs(xg_diffs[i] - goal_diffs[i]) for i in range(n_with_xg)) / n_with_xg
                  if n_with_xg > 0 else 0.0)

    trusted = (coverage >= XG_MIN_COVERAGE and n_with_xg >= XG_MIN_SAMPLE)

    buckets_out = {}
    for bname, b in sorted(home_win_by_xg_bucket.items()):
        n = b["n"]
        buckets_out[bname] = {
            "n":            n,
            "home_win_rate": round(b["wins"] / n, 4) if n > 0 else None,
        }

    return {
        "n_total":         n_total,
        "n_with_xg":       n_with_xg,
        "coverage":        round(coverage, 4),
        "spearman_r":      round(spearman, 4),
        "mean_abs_residual": round(mean_abs_r, 4),
        "trusted":         trusted,
        "buckets":         buckets_out,
    }


# -- Main ---------------------------------------------------------------------

def run_signals() -> dict:
    print("=" * 62)
    print("  MARKET INTELLIGENCE ? Phase 3: Signal Validation")
    print("=" * 62)

    if not REGISTRY_FILE.exists():
        print("\n  ERRORE: league_registry.json non trovato.")
        print("  Esegui prima: python pipeline.py --audit")
        sys.exit(1)

    with open(REGISTRY_FILE, encoding="utf-8") as f:
        registry = json.load(f)

    qualified = registry.get("qualified_leagues", [])
    if not qualified:
        print("\n  Nessuna lega qualificata. Aumenta il database e riprova.")
        sys.exit(1)

    league_ids = [l["league_id"] for l in qualified]
    print(f"\n  Leghe qualificate: {len(league_ids)}")

    sb = get_supabase_client()

    # Fetch rows
    print("  Fetching righe qualificate...")
    rows = _fetch_rows(sb, league_ids)
    print(f"  Totale righe: {len(rows)}")

    # Fetch xG
    print("  Fetching dati xG...")
    fids = [r["fixture_id"] for r in rows]
    xg_map = _fetch_xg_map(sb, fids)
    print(f"  Partite con xG: {len(xg_map)}")

    # -- Signal 1: ML Divergence --
    print("\n  Validating ML Divergence signal...")
    ml_div_results = _validate_ml_divergence(rows)

    print(f"\n  {'Mercato':<12} {'N':>6} {'Base%':>7} {'Sig_N':>6} {'Sig%':>7} {'Lift':>7} {'Spr':>6} {'Trust':>6}")
    print(f"  {'-'*60}")
    for mkey, r in ml_div_results.items():
        sig_pct = f"{r['signal_rate']:.1%}" if r["signal_rate"] else "  N/A "
        lift    = f"{r['lift']:+.1%}" if r["lift"] is not None else "   N/A"
        trust   = "OK" if r["trusted"] else "?"
        print(f"  {mkey:<12} {r['n_total']:>6} {r['base_rate']:>6.1%} "
              f"{r['n_signals']:>6} {sig_pct:>7} {lift:>7} "
              f"{r['spearman_r']:>6.3f}  {trust}")

    # -- Signal 2: xG --
    print("\n  Validating xG Residual signal...")
    xg_result = _validate_xg_signal(rows, xg_map)

    print(f"\n  xG Coverage: {xg_result['coverage']:.1%} ({xg_result['n_with_xg']} su {xg_result['n_total']})")
    print(f"  Spearman(xG_diff, goal_diff): {xg_result['spearman_r']:.4f}")
    print(f"  Mean |residual|: {xg_result['mean_abs_residual']:.4f}")
    print(f"  Trusted: {'OK' if xg_result['trusted'] else 'X'}")
    if xg_result["buckets"]:
        print(f"\n  {'Bucket xG':<40} {'N':>5} {'Home Win%':>10}")
        print(f"  {'-'*57}")
        for bname, b in xg_result["buckets"].items():
            wr = f"{b['home_win_rate']:.1%}" if b["home_win_rate"] is not None else "N/A"
            print(f"  {bname:<40} {b['n']:>5} {wr:>10}")

    # -- Calcola pesi finali --
    # ML: usa il mercato 1x2_H come riferimento principale per il peso
    ml_ref = ml_div_results.get("1x2_H", {})
    ml_trusted = ml_ref.get("trusted", False)
    xg_trusted = xg_result["trusted"]

    if ml_trusted and xg_trusted:
        w_ml = DEFAULT_WEIGHT_ML_DIV
        w_xg = DEFAULT_WEIGHT_XG
    elif ml_trusted:
        w_ml, w_xg = 1.0, 0.0
    elif xg_trusted:
        w_ml, w_xg = 0.0, 1.0
    else:
        # Nessun segnale trusted: usa ML divergenza grezza come fallback (peso 1.0)
        w_ml, w_xg = 1.0, 0.0

    output = {
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "leagues_used":  league_ids,
        "ml_divergence": {
            **ml_div_results,
            "weight": w_ml,
        },
        "xg_residual": {
            **xg_result,
            "weight": w_xg,
        },
        "weight_sum": round(w_ml + w_xg, 4),
        "fallback_mode": not (ml_trusted or xg_trusted),
    }

    tmp = SIGNAL_WEIGHTS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    os.replace(tmp, SIGNAL_WEIGHTS_FILE)
    print(f"\n  Salvato -> {SIGNAL_WEIGHTS_FILE}")
    print(f"  Pesi finali: ML={w_ml:.2f}  xG={w_xg:.2f}  "
          f"{'[FALLBACK]' if output['fallback_mode'] else ''}")

    return output


if __name__ == "__main__":
    run_signals()
