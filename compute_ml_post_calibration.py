"""
compute_ml_post_calibration.py
-------------------------------
Calcola fattori di correzione post-hoc per i target ML con bias sistematico.

Usa le predizioni REALI gia' salvate in model_predictions_json + i risultati
effettivi per calcolare, per ogni target x classe x bin, il fattore correttivo:

    correction[bin] = actual_hit_rate / avg_predicted_prob

Output: ml_post_calibration.json nella root del progetto.
predict_fixture.py lo carica automaticamente e corregge le probabilita' in uscita.

Uso:
    python compute_ml_post_calibration.py
    python compute_ml_post_calibration.py --min-n 20   # bin con N<20 restano a 1.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

MIN_N_DEFAULT = 20  # campioni minimi per bin per applicare correzione

# Target binari (True/False): corregge "True", poi False = 1 - True
BINARY_TARGETS = {
    "target_over_2_5":  ("True", "False"),
    "target_over_1_5":  ("True", "False"),
    "target_over_3_5":  ("True", "False"),
    "target_over_4_5":  ("True", "False"),
    "target_btts":      ("True", "False"),
}

# Target multi-classe: corregge ogni classe indipendentemente poi rinormalizza
MULTICLASS_TARGETS = {
    "target_1x2":    ["H", "D", "A"],
    "target_ft_1x2": ["H", "D", "A"],
    "target_ht_1x2": ["H", "D", "A"],
}

ALL_TARGETS = {**{k: list(v) for k, v in BINARY_TARGETS.items()}, **MULTICLASS_TARGETS}


def check_outcome(target: str, cls: str, h: int, a: int,
                  hh: Optional[int], ha: Optional[int]) -> Optional[bool]:
    """Ritorna True/False/None per la combinazione target+classe."""
    if target in ("target_1x2", "target_ft_1x2"):
        if cls == "H": return h > a
        if cls == "D": return h == a
        if cls == "A": return h < a
    if target == "target_ht_1x2":
        if hh is None or ha is None: return None
        if cls == "H": return hh > ha
        if cls == "D": return hh == ha
        if cls == "A": return hh < ha
    if target in ("target_over_2_5", "target_over_1_5",
                  "target_over_3_5", "target_over_4_5"):
        thr = {"target_over_0_5": 0, "target_over_1_5": 1,
               "target_over_2_5": 2, "target_over_3_5": 3, "target_over_4_5": 4}
        limit = thr.get(target, 2)
        if cls == "True":  return h + a > limit
        if cls == "False": return h + a <= limit
    if target == "target_btts":
        if cls == "True":  return h > 0 and a > 0
        if cls == "False": return not (h > 0 and a > 0)
    return None


def fetch_data() -> Tuple[List[dict], Dict[int, Tuple[int, int]]]:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()

    rows: List[dict] = []
    page_size = 1000
    offset = 0
    print("Fetching model_predictions_json + risultati...")
    while True:
        resp = (
            sb.table("fixture_predictions")
            .select("fixture_id,result_home_goals,result_away_goals,model_predictions_json,league_id")
            .in_("result_status_short", ["FT", "AET", "PEN"])
            .not_.is_("model_predictions_json", "null")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        print(f"  {len(rows)} righe...", end="\r")
        if len(batch) < page_size:
            break
        offset += page_size
    print(f"\n  Totale: {len(rows)}")

    fids = [r["fixture_id"] for r in rows if r.get("fixture_id")]
    ht_map: Dict[int, Tuple[int, int]] = {}
    print("Fetching halftime data...")
    for i in range(0, len(fids), 300):
        resp2 = sb.table("matches").select("fixture_id,halftime_home,halftime_away").in_(
            "fixture_id", fids[i:i+300]).execute()
        for row in (resp2.data or []):
            hh = row.get("halftime_home")
            ha = row.get("halftime_away")
            if hh is not None and ha is not None:
                try:
                    ht_map[row["fixture_id"]] = (int(hh), int(ha))
                except (ValueError, TypeError):
                    pass
    print(f"  HT: {len(ht_map)} fixture\n")
    return rows, ht_map


def compute_corrections(
    rows: List[dict],
    ht_map: Dict[int, Tuple[int, int]],
    min_n: int,
) -> Dict[str, Dict[str, Dict[int, float]]]:
    """
    Ritorna {target: {cls: {bin_idx: correction_factor}}}
    """
    # stats[target][cls][bin] = {n, sum_prob, hits}
    stats: Dict[str, Dict[str, Dict[int, dict]]] = {}
    for target, classes in ALL_TARGETS.items():
        stats[target] = {}
        for cls in classes:
            stats[target][cls] = {b: {"n": 0, "sum_prob": 0.0, "hits": 0} for b in range(10)}

    skipped = 0
    for row in rows:
        ml = row.get("model_predictions_json")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")
        if not ml or not isinstance(ml, dict) or h is None or a is None:
            skipped += 1
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            skipped += 1
            continue

        fid = row.get("fixture_id")
        hh, ha = ht_map.get(fid, (None, None))

        # Supporta formato con/senza wrapper "targets"
        targets_data = ml.get("targets", ml)

        for target, classes in ALL_TARGETS.items():
            target_probs = targets_data.get(target)
            if not isinstance(target_probs, dict):
                continue
            for cls in classes:
                prob = target_probs.get(cls) or target_probs.get(str(cls))
                if prob is None:
                    continue
                try:
                    prob = float(prob)
                except (ValueError, TypeError):
                    continue
                if not (0.0 < prob < 1.0):
                    continue

                outcome = check_outcome(target, cls, h, a, hh, ha)
                if outcome is None:
                    continue

                bin_idx = min(int(prob * 10), 9)
                s = stats[target][cls][bin_idx]
                s["n"] += 1
                s["sum_prob"] += prob
                if outcome:
                    s["hits"] += 1

    print(f"  Skipped: {skipped}")

    # Costruisce tabella correzioni
    corrections: Dict[str, Dict[str, Dict[int, float]]] = {}
    for target, cls_bins in stats.items():
        corrections[target] = {}
        for cls, bins in cls_bins.items():
            corrections[target][cls] = {}
            for bin_idx, s in bins.items():
                n = s["n"]
                if n < min_n:
                    corrections[target][cls][bin_idx] = 1.0
                else:
                    avg_prob = s["sum_prob"] / n
                    hit_rate = s["hits"] / n
                    if avg_prob > 0:
                        cf = round(hit_rate / avg_prob, 3)
                        cf = max(0.3, min(cf, 3.0))  # cap piu' conservativo per ML
                    else:
                        cf = 1.0
                    corrections[target][cls][bin_idx] = cf

    return corrections, stats


def print_report(stats, corrections, min_n):
    print("\n" + "=" * 80)
    print("  CORREZIONI POST-HOC ML")
    print(f"  Bin con N < {min_n} -> cf=1.0 (nessuna correzione)")
    print("=" * 80)
    for target in sorted(ALL_TARGETS.keys()):
        classes = ALL_TARGETS[target]
        has_bias = False
        lines = []
        for cls in classes:
            bins = stats[target][cls]
            for bin_idx in range(10):
                s = bins[bin_idx]
                n = s["n"]
                if n == 0:
                    continue
                avg = s["sum_prob"] / n
                hr = s["hits"] / n
                bias = hr - avg
                cf = corrections[target][cls].get(bin_idx, 1.0)
                if abs(bias) > 0.05 and n >= min_n:
                    has_bias = True
                lines.append((cls, bin_idx, n, avg, hr, bias, cf))

        if has_bias or any(abs(x[5]) > 0.05 for x in lines if x[2] >= min_n):
            print(f"\n  {target}")
            print(f"  {'Cls':>6} {'Bin':>4} {'N':>5} {'Pred%':>6} {'Real%':>6} {'Bias':>7} {'CF':>6}")
            for cls, b, n, avg, hr, bias, cf in lines:
                flag = " <-- BIAS" if abs(bias) > 0.07 and n >= min_n else ""
                print(f"  {cls:>6} {b:>4} {n:>5} {avg*100:>5.1f}% {hr*100:>5.1f}% {bias*100:>+6.1f}% {cf:>6.3f}{flag}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-n", type=int, default=MIN_N_DEFAULT)
    args = parser.parse_args()

    rows, ht_map = fetch_data()
    print("Calcolando correzioni...")
    corrections, stats = compute_corrections(rows, ht_map, min_n=args.min_n)

    print_report(stats, corrections, min_n=args.min_n)

    # Conta quante correzioni significative (cf != 1.0)
    n_active = sum(
        1 for t in corrections.values()
        for c in t.values()
        for cf in c.values()
        if cf != 1.0
    )

    # Salva
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(rows),
        "min_n": args.min_n,
        "n_active_corrections": n_active,
        "corrections": corrections,
    }
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ml_post_calibration.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"\n  Salvato: {path}")
    print(f"  Correzioni attive (cf != 1.0): {n_active}")
    print(f"  predict_fixture.py le applica automaticamente al prossimo run.")


if __name__ == "__main__":
    main()
