"""
generate_dynamic_cal.py — Genera dynamic_cal.json per calibrazione Poisson per-lega.

La calibrazione dinamica aggiunge un livello di correzione PER LEGA sopra la tabella
statica globale. money_management.py usa la chain:
  1. by_league[league_id][cal_key][bin]   ← per-league (questo script)
  2. global[cal_key][bin]                 ← globale (questo script, = CALIBRATION_TABLE)
  3. CALIBRATION_TABLE statica            ← fallback

Output:  dynamic_cal.json  (nella root del progetto)

Uso:
  python generate_dynamic_cal.py
  python generate_dynamic_cal.py --min-n 15     # bin per-lega con N < 15 esclusi
  python generate_dynamic_cal.py --min-global 30 # bin globali con N < 30 esclusi
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# MAPPA MERCATI POISSON (identica a update_poisson_calibration.py)
# ---------------------------------------------------------------------------
MARKET_CONFIG = {
    "H":       ("1x2",                  "H",     "Victoria casa"),
    "D":       ("1x2",                  "D",     "Pareggio"),
    "A":       ("1x2",                  "A",     "Victoria trasferta"),
    "O25":     ("over_2_5",             "True",  "Over 2.5"),
    "U25":     ("over_2_5",             "False", "Under 2.5"),
    "BTTS":    ("btts",                 "True",  "BTTS Si"),
    "BTTS_NO": ("btts",                 "False", "BTTS No"),
    "HT05":    ("first_half_over_0_5",  "True",  "1T Over 0.5"),
}

DEFAULT_DIVERGENCE_STD = 0.30  # fallback se non calcolabile da odds


# ---------------------------------------------------------------------------
# UTILITÀ RISULTATO
# ---------------------------------------------------------------------------
def check_result(cal_key: str, h: int, a: int,
                 hh: Optional[int], ha: Optional[int]) -> Optional[bool]:
    if cal_key == "H":       return h > a
    if cal_key == "D":       return h == a
    if cal_key == "A":       return h < a
    if cal_key == "O25":     return h + a > 2
    if cal_key == "U25":     return h + a <= 2
    if cal_key == "BTTS":    return h > 0 and a > 0
    if cal_key == "BTTS_NO": return not (h > 0 and a > 0)
    if cal_key == "HT05":
        if hh is None or ha is None:
            return None
        return hh + ha > 0
    return None


# ---------------------------------------------------------------------------
# FETCH DB
# ---------------------------------------------------------------------------
def fetch_data() -> Tuple[List[dict], Dict[int, Tuple[int, int]]]:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from db_client import get_supabase_client
    sb = get_supabase_client()

    rows: List[dict] = []
    page_size = 1000
    offset = 0

    print("Fetching fixture_predictions con db_json_analisi...")
    while True:
        resp = (
            sb.table("fixture_predictions")
            .select("fixture_id,result_home_goals,result_away_goals,db_json_analisi,league_id,raw_json_odds")
            .in_("result_status_short", ["FT", "AET", "PEN"])
            .not_.is_("db_json_analisi", "null")
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

    # HT data
    print("Fetching halftime data...")
    fids = [r["fixture_id"] for r in rows if r.get("fixture_id")]
    ht_map: Dict[int, Tuple[int, int]] = {}
    for i in range(0, len(fids), 300):
        resp2 = sb.table("matches").select("fixture_id,halftime_home,halftime_away").in_(
            "fixture_id", fids[i:i + 300]
        ).execute()
        for row in (resp2.data or []):
            hh = row.get("halftime_home")
            ha = row.get("halftime_away")
            if hh is not None and ha is not None:
                try:
                    ht_map[row["fixture_id"]] = (int(hh), int(ha))
                except (ValueError, TypeError):
                    pass
    print(f"  HT data: {len(ht_map)} fixture\n")
    return rows, ht_map


# ---------------------------------------------------------------------------
# ESTRAI IMPLIED PROB DA ODDS (per calcolo divergenza σ)
# ---------------------------------------------------------------------------
_OVERROUND_CORRECTION = 0.975  # identico a money_management.py


def _extract_implied_1x2(raw_odds: Optional[dict]) -> Optional[Tuple[float, float, float]]:
    """Ritorna (p_H, p_D, p_A) implied da odds, con correzione overround, o None."""
    if not isinstance(raw_odds, dict):
        return None
    bookmakers = raw_odds.get("bookmakers") or []
    if not bookmakers:
        return None
    # Cerca Betfair sportsbook, altrimenti primo
    bm = None
    for b in bookmakers:
        if "betfair" in str(b.get("name", "")).lower():
            bm = b
            break
    if bm is None:
        bm = bookmakers[0]

    for bet in (bm.get("bets") or []):
        bet_name = str(bet.get("name", ""))
        if bet_name not in ("Match Winner", "1X2", "Fulltime Result"):
            continue
        odds_map: dict = {}
        for v in (bet.get("values") or []):
            val = str(v.get("value", ""))
            try:
                odd = float(v.get("odd", 0))
            except (TypeError, ValueError):
                continue
            if odd > 1.0:
                odds_map[val] = odd
        ph = odds_map.get("Home")
        pd = odds_map.get("Draw")
        pa = odds_map.get("Away")
        if ph and pd and pa:
            overround = (1 / ph + 1 / pd + 1 / pa)
            adj = overround * _OVERROUND_CORRECTION
            return (1 / ph / adj, 1 / pd / adj, 1 / pa / adj)
    return None


# ---------------------------------------------------------------------------
# ACCUMULA STATISTICHE
# ---------------------------------------------------------------------------
def accumulate_stats(
    rows: List[dict],
    ht_map: Dict[int, Tuple[int, int]],
) -> Tuple[
    Dict[str, Dict[int, dict]],                    # global_stats
    Dict[str, Dict[str, Dict[int, dict]]],         # league_stats[league_id][cal_key][bin]
    List[float],                                   # divergences (for σ)
]:
    """
    Accumula statistiche globali e per-lega.
    Ritorna anche le divergenze Poisson->Market per calcolare σ.
    """
    global_stats: Dict[str, Dict[int, dict]] = {
        k: {b: {"n": 0, "sum_prob": 0.0, "hits": 0} for b in range(10)}
        for k in MARKET_CONFIG
    }
    # league_stats[str(league_id)][cal_key][bin_idx] = {"n", "sum_prob", "hits"}
    league_stats: Dict[str, Dict[str, Dict[int, dict]]] = {}
    divergences: List[float] = []

    skipped = 0
    for row in rows:
        analisi = row.get("db_json_analisi")
        h = row.get("result_home_goals")
        a = row.get("result_away_goals")
        if not analisi or not isinstance(analisi, dict) or h is None or a is None:
            skipped += 1
            continue
        try:
            h, a = int(h), int(a)
        except (ValueError, TypeError):
            skipped += 1
            continue

        fid = row.get("fixture_id")
        league_id = str(row.get("league_id") or "")
        hh, ha = ht_map.get(fid, (None, None))
        markets = analisi.get("markets", {})
        raw_odds = row.get("raw_json_odds")

        # Divergenza per σ (usa solo 1x2_H come proxy)
        implied = _extract_implied_1x2(raw_odds)
        if implied is not None:
            m_1x2 = markets.get("1x2", {})
            ph_model = m_1x2.get("H")
            if ph_model:
                try:
                    divergence = (float(ph_model) / implied[0]) - 1.0
                    if abs(divergence) < 2.0:  # esclude outlier estremi
                        divergences.append(divergence)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass

        # Inizializza league se necessario
        if league_id and league_id not in league_stats:
            league_stats[league_id] = {
                k: {b: {"n": 0, "sum_prob": 0.0, "hits": 0} for b in range(10)}
                for k in MARKET_CONFIG
            }

        for cal_key, (json_market, json_class, _) in MARKET_CONFIG.items():
            market_data = markets.get(json_market)
            if not isinstance(market_data, dict):
                continue
            raw_prob = market_data.get(json_class)
            if raw_prob is None:
                continue
            try:
                prob = float(raw_prob)
            except (ValueError, TypeError):
                continue
            if not (0.0 < prob < 1.0):
                continue

            outcome = check_result(cal_key, h, a, hh, ha)
            if outcome is None:
                continue

            bin_idx = min(int(prob * 10), 9)

            # Global
            s = global_stats[cal_key][bin_idx]
            s["n"] += 1
            s["sum_prob"] += prob
            if outcome:
                s["hits"] += 1

            # Per-league
            if league_id:
                s2 = league_stats[league_id][cal_key][bin_idx]
                s2["n"] += 1
                s2["sum_prob"] += prob
                if outcome:
                    s2["hits"] += 1

    print(f"  Skipped (dati mancanti): {skipped}")
    return global_stats, league_stats, divergences


# ---------------------------------------------------------------------------
# COSTRUISCI TABELLA DI CORREZIONE
# ---------------------------------------------------------------------------
def build_correction(
    stats: Dict[str, Dict[int, dict]],
    min_n: int,
) -> Dict[str, Dict[int, float]]:
    """Costruisce {cal_key: {bin_idx: correction_factor}} dalla stats dict."""
    table: Dict[str, Dict[int, float]] = {}
    for cal_key, bins in stats.items():
        table[cal_key] = {}
        for bin_idx, s in bins.items():
            n = s["n"]
            if n < min_n:
                table[cal_key][bin_idx] = 1.0
            else:
                avg_prob = s["sum_prob"] / n
                hit_rate = s["hits"] / n
                if avg_prob > 0:
                    cf = round(hit_rate / avg_prob, 3)
                    cf = max(0.1, min(cf, 10.0))
                else:
                    cf = 1.0
                table[cal_key][bin_idx] = cf
    return table


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera dynamic_cal.json per calibrazione Poisson per-lega"
    )
    parser.add_argument("--min-n", type=int, default=15,
                        help="Min campioni per bin PER LEGA (default: 15)")
    parser.add_argument("--min-global", type=int, default=30,
                        help="Min campioni per bin GLOBALE (default: 30)")
    args = parser.parse_args()

    # 1. Fetch
    rows, ht_map = fetch_data()
    total = len(rows)

    # 2. Accumula
    print("Calcolando statistiche per bin (globale + per-lega)...")
    global_stats, league_stats, divergences = accumulate_stats(rows, ht_map)

    # 3. Tabella globale
    print("\nCalibrazione globale (fallback layer 2)...")
    global_table = build_correction(global_stats, min_n=args.min_global)
    n_global_bins = sum(
        1 for bins in global_stats.values() for s in bins.values() if s["n"] >= args.min_global
    )
    print(f"  Bin globali con N >= {args.min_global}: {n_global_bins}")

    # 4. Tabelle per-lega
    print(f"\nCalibrazione per-lega (layer 1, min_n={args.min_n})...")
    by_league_cal: Dict[str, Dict[str, Dict[int, float]]] = {}
    leagues_with_data = 0
    for league_id, lg_stats in league_stats.items():
        lg_table = build_correction(lg_stats, min_n=args.min_n)
        # Controlla se almeno un bin ha correzione reale (N >= min_n)
        has_real_data = any(
            s["n"] >= args.min_n
            for bins in lg_stats.values()
            for s in bins.values()
        )
        if has_real_data:
            by_league_cal[league_id] = lg_table
            leagues_with_data += 1

    print(f"  Leghe con dati sufficienti: {leagues_with_data}")

    # 5. Divergence σ
    if len(divergences) >= 30:
        mean_div = sum(divergences) / len(divergences)
        var = sum((d - mean_div) ** 2 for d in divergences) / len(divergences)
        std_div = var ** 0.5
        print(f"\n  Divergence std = {std_div:.4f} (da {len(divergences)} campioni)")
    else:
        std_div = DEFAULT_DIVERGENCE_STD
        print(f"\n  Divergence std = {std_div:.4f} (default, campioni insufficienti: {len(divergences)})")

    divergence_stats = {
        "std": round(std_div, 4),
        "n_samples": len(divergences),
        "mean": round(sum(divergences) / len(divergences), 4) if divergences else 0.0,
    }

    # 6. Costruisce dynamic_cal.json
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": total,
        "leagues_covered": leagues_with_data,
        "min_n_per_league": args.min_n,
        "min_n_global": args.min_global,
        "divergence_stats": divergence_stats,
        "global": global_table,
        "by_league": by_league_cal,
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dynamic_cal.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Salvato: {out_path}")

    # 7. Riepilogo
    print("\n" + "=" * 70)
    print("  RIEPILOGO dynamic_cal.json")
    print("=" * 70)
    print(f"  Fixture totali        : {total}")
    print(f"  Leghe con calibrazione: {leagues_with_data}")
    print(f"  Bin globali attivi    : {n_global_bins}")
    print(f"  Divergence std        : {std_div:.4f}")
    print()

    # Top leghe per numero di fixture
    league_totals = {}
    for lid, lg_stats in league_stats.items():
        total_n = sum(s["n"] for bins in lg_stats.values() for s in bins.values())
        league_totals[lid] = total_n
    top10 = sorted(league_totals.items(), key=lambda x: x[1], reverse=True)[:10]
    print("  Top 10 leghe per campioni:")
    for lid, n_total in top10:
        # Conta bin con dati reali
        real_bins = sum(
            1 for bins in league_stats[lid].values()
            for s in bins.values() if s["n"] >= args.min_n
        )
        print(f"    lega {lid:>6}: {n_total:>6} campioni, {real_bins} bin calibrati")

    print(f"\n  use_dynamic_cal e' True in EDGE_ENGINE_FLAGS -> attivo automaticamente.")
    print(f"  Rigenera periodicamente con: python generate_dynamic_cal.py")


if __name__ == "__main__":
    main()
