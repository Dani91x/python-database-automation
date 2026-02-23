# Prediction/backfill_historical_analysis.py

import logging
import sys
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_client import get_supabase_client

# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==============================
# Poisson/xG Logic (Identical to today_predictions_backfill.py)
# ==============================

def _poisson_prob(lmbda: float, k: int) -> float:
    if lmbda <= 0: return 0.0
    return math.exp(-lmbda) * (lmbda ** k) / math.factorial(k)

def _fetch_all_table(
    table: str,
    columns: str,
    filters: Optional[List[Tuple[str, str, Any]]] = None,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    sb = get_supabase_client()
    offset = 0
    results: List[Dict[str, Any]] = []

    while True:
        query = sb.table(table).select(columns)
        if filters:
            for op, col, val in filters:
                if op == "eq":
                    query = query.eq(col, val)
                elif op == "gte":
                    query = query.gte(col, val)
                elif op == "lt":
                    query = query.lt(col, val)
                elif op == "in":
                    query = query.in_(col, val)
                elif op == "is":
                    query = query.is_(col, val)
                else:
                    raise ValueError(f"Unsupported filter op: {op}")

        resp = query.range(offset, offset + page_size - 1).execute()
        data = getattr(resp, "data", None) or []
        results.extend(data)
        if len(data) < page_size:
            break
        offset += page_size

    return results

def _build_match_cache(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], Dict[str, Any]],
) -> Dict[str, Any]:
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    cols = (
        "fixture_id,fixture_date,home_team_id,away_team_id,"
        "goals_home,goals_away,halftime_home,halftime_away,status_short"
    )
    filters = [("eq", "league_id", league_id), ("eq", "season_year", season_year)]
    rows = _fetch_all_table("matches", cols, filters, page_size=1000)

    played = []
    for r in rows:
        if str(r.get("status_short") or "").upper() in {"FT", "AET", "PEN"}:
            played.append(r)

    team_hist: Dict[int, List[Dict[str, Any]]] = {}
    for m in played:
        fixture_date = m.get("fixture_date")
        home_id = m.get("home_team_id")
        away_id = m.get("away_team_id")
        goals_home = m.get("goals_home") or 0
        goals_away = m.get("goals_away") or 0
        ht_home = m.get("halftime_home")
        ht_away = m.get("halftime_away")

        if home_id is not None:
            team_hist.setdefault(int(home_id), []).append(
                {
                    "fixture_id": m.get("fixture_id"),
                    "fixture_date": fixture_date,
                    "team_id": int(home_id),
                    "goals_for": goals_home,
                    "goals_against": goals_away,
                    "halftime_for": ht_home,
                }
            )
        if away_id is not None:
            team_hist.setdefault(int(away_id), []).append(
                {
                    "fixture_id": m.get("fixture_id"),
                    "fixture_date": fixture_date,
                    "team_id": int(away_id),
                    "goals_for": goals_away,
                    "goals_against": goals_home,
                    "halftime_for": ht_away,
                }
            )

    for team_id, lst in team_hist.items():
        lst.sort(key=lambda x: x.get("fixture_date") or "")

    total_matches = len(played)
    if total_matches > 0:
        league_home_avg = sum((m.get("goals_home") or 0) for m in played) / total_matches
        league_away_avg = sum((m.get("goals_away") or 0) for m in played) / total_matches
        league_total_avg = league_home_avg + league_away_avg
    else:
        league_home_avg = 1.2
        league_away_avg = 1.0
        league_total_avg = 2.2

    cache[key] = {
        "played": played,
        "team_hist": team_hist,
        "league_home_avg": league_home_avg,
        "league_away_avg": league_away_avg,
        "league_total_avg": league_total_avg,
    }
    return cache[key]

def _build_xg_cache(
    league_id: int,
    season_year: int,
    cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]],
    fixture_ids: List[int],
) -> Dict[Tuple[int, int], float]:
    key = (league_id, season_year)
    if key in cache:
        return cache[key]

    xg_map: Dict[Tuple[int, int], float] = {}
    if not fixture_ids:
        cache[key] = xg_map
        return xg_map

    for i in range(0, len(fixture_ids), 500):
        chunk = fixture_ids[i : i + 500]
        rows = _fetch_all_table(
            "match_team_stats",
            "fixture_id,team_id,stat_type,value_numeric",
            filters=[("eq", "league_id", league_id), ("eq", "season_year", season_year), ("in", "fixture_id", chunk)],
            page_size=1000,
        )
        for r in rows:
            st = str(r.get("stat_type") or "").lower()
            if "expected" in st or "xg" in st:
                key2 = (int(r.get("fixture_id")), int(r.get("team_id")))
                val = r.get("value_numeric")
                try:
                    val_f = float(val)
                except Exception:
                    continue
                prev = xg_map.get(key2)
                if prev is None or val_f > prev:
                    xg_map[key2] = val_f

    cache[key] = xg_map
    return xg_map

def _window_stats(team_matches: List[Dict[str, Any]], n: int, xg_map: Dict[Tuple[int, int], float]) -> Dict[str, Optional[float]]:
    if not team_matches:
        return {"gf_avg": None, "ga_avg": None, "xg_avg": None, "n_used": 0}

    recent = team_matches[-n:]
    gf = [m.get("goals_for", 0) for m in recent]
    ga = [m.get("goals_against", 0) for m in recent]
    xg_vals = []
    for m in recent:
        fx_id = m.get("fixture_id")
        team_id = m.get("team_id")
        if fx_id is None or team_id is None:
            continue
        val = xg_map.get((int(fx_id), int(team_id)))
        if val is not None:
            xg_vals.append(val)

    return {
        "gf_avg": sum(gf) / len(gf) if gf else None,
        "ga_avg": sum(ga) / len(ga) if ga else None,
        "xg_avg": sum(xg_vals) / len(xg_vals) if xg_vals else None,
        "n_used": len(recent),
        "xg_used": len(xg_vals),
    }

def _blend_windows(stats5: Dict[str, Any], stats10: Dict[str, Any], stats15: Dict[str, Any], weights: Dict[int, float]) -> Dict[str, Any]:
    def _blend(key: str) -> Optional[float]:
        parts = []
        for n, st in [(5, stats5), (10, stats10), (15, stats15)]:
            val = st.get(key)
            if val is not None:
                parts.append((weights[n], val))
        if not parts:
            return None
        return sum(w * v for w, v in parts)

    return {
        "gf_blend": _blend("gf_avg"),
        "ga_blend": _blend("ga_avg"),
        "xg_blend": _blend("xg_avg"),
    }

def compute_db_json_analisi(
    ctx: Dict[str, Any],
    match_cache: Dict[Tuple[int, int], Dict[str, Any]],
    xg_cache: Dict[Tuple[int, int], Dict[Tuple[int, int], float]],
) -> Optional[Dict[str, Any]]:
    fixture_id = ctx.get("fixture_id")
    league_id = ctx.get("league_id")
    season_year = ctx.get("season_year")
    fixture_date = ctx.get("fixture_date")
    home_team_id = ctx.get("home_team_id")
    away_team_id = ctx.get("away_team_id")

    if not all([fixture_id, league_id, season_year, fixture_date, home_team_id, away_team_id]):
        return None

    cache = _build_match_cache(int(league_id), int(season_year), match_cache)
    team_hist = cache["team_hist"]
    league_home_avg = cache["league_home_avg"]
    league_away_avg = cache["league_away_avg"]
    league_total_avg = cache["league_total_avg"]

    fixture_ids = [m.get("fixture_id") for m in cache["played"] if m.get("fixture_id") is not None]
    xg_map = _build_xg_cache(int(league_id), int(season_year), xg_cache, fixture_ids)

    def _before_date(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [m for m in matches if m.get("fixture_date") and m["fixture_date"] < fixture_date]

    home_matches = _before_date(team_hist.get(int(home_team_id), []))
    away_matches = _before_date(team_hist.get(int(away_team_id), []))

    stats5_h = _window_stats(home_matches, 5, xg_map)
    stats10_h = _window_stats(home_matches, 10, xg_map)
    stats15_h = _window_stats(home_matches, 15, xg_map)
    stats5_a = _window_stats(away_matches, 5, xg_map)
    stats10_a = _window_stats(away_matches, 10, xg_map)
    stats15_a = _window_stats(away_matches, 15, xg_map)

    weights = {5: 0.5, 10: 0.3, 15: 0.2}
    blend_h = _blend_windows(stats5_h, stats10_h, stats15_h, weights)
    blend_a = _blend_windows(stats5_a, stats10_a, stats15_a, weights)

    k_shrink = 8.0
    eta_goals = 0.6
    league_half = max(0.1, league_total_avg / 2.0)

    def _shrink(raw: Optional[float], n_used: int) -> float:
        base = league_half if raw is None else raw
        return ((k_shrink * league_half) + (base * max(n_used, 1))) / (k_shrink + max(n_used, 1))

    home_n_used = stats15_h.get("n_used", 0)
    away_n_used = stats15_a.get("n_used", 0)

    gf_h = _shrink(blend_h.get("gf_blend"), home_n_used)
    ga_h = _shrink(blend_h.get("ga_blend"), home_n_used)
    gf_a = _shrink(blend_a.get("gf_blend"), away_n_used)
    ga_a = _shrink(blend_a.get("ga_blend"), away_n_used)

    xg_h = _shrink(blend_h.get("xg_blend"), home_n_used)
    xg_a = _shrink(blend_a.get("xg_blend"), away_n_used)

    home_attack = ((eta_goals * gf_h) + ((1 - eta_goals) * xg_h)) / league_half
    away_attack = ((eta_goals * gf_a) + ((1 - eta_goals) * xg_a)) / league_half
    home_def = ga_h / league_half
    away_def = ga_a / league_half

    lambda_home = max(0.05, league_home_avg * home_attack * away_def)
    lambda_away = max(0.05, league_away_avg * away_attack * home_def)

    max_goals = 6
    probs = []
    for hg in range(0, max_goals + 1):
        p_h = _poisson_prob(lambda_home, hg)
        for ag in range(0, max_goals + 1):
            p = p_h * _poisson_prob(lambda_away, ag)
            probs.append((hg, ag, p))

    total_p = sum(p for _, _, p in probs) or 1.0
    probs = [(hg, ag, p / total_p) for hg, ag, p in probs]

    p_home = sum(p for hg, ag, p in probs if hg > ag)
    p_draw = sum(p for hg, ag, p in probs if hg == ag)
    p_away = sum(p for hg, ag, p in probs if hg < ag)
    p_over25 = sum(p for hg, ag, p in probs if (hg + ag) >= 3)
    p_under25 = 1.0 - p_over25
    p_btts = sum(p for hg, ag, p in probs if hg > 0 and ag > 0)
    p_btts_no = 1.0 - p_btts

    def _team_p_goal_1h(matches: List[Dict[str, Any]]) -> float:
        if not matches:
            return 0.5
        recent = matches[-15:]
        flags = []
        for m in recent:
            ht = m.get("halftime_for")
            if ht is None:
                continue
            flags.append(1 if ht > 0 else 0)
        if not flags:
            return 0.5
        return sum(flags) / len(flags)

    p_home_1h = _team_p_goal_1h(home_matches)
    p_away_1h = _team_p_goal_1h(away_matches)
    p_goal_1h_freq = 1.0 - ((1 - p_home_1h) * (1 - p_away_1h))

    # --- HYBRID HT MODEL ---
    lambda_1h = (lambda_home + lambda_away) * 0.45
    p_goal_1h_poisson = 1.0 - math.exp(-lambda_1h)
    p_hybrid_1h = (p_goal_1h_freq + p_goal_1h_poisson) / 2.0
    # -----------------------

    analysis = {
        "model": "poisson_xg_hybrid",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": int(league_id),
        "season_year": int(season_year),
        "fixture_id": int(fixture_id),
        "inputs": {
            "lambda_home": round(lambda_home, 4),
            "lambda_away": round(lambda_away, 4),
            "lambda_1h_tot": round(lambda_1h, 4),
            "league_home_avg": round(league_home_avg, 4),
            "league_away_avg": round(league_away_avg, 4),
            "league_total_avg": round(league_total_avg, 4),
            "home_matches_used": int(home_n_used),
            "away_matches_used": int(away_n_used),
            "home_xg_covered": int(stats15_h.get("xg_used", 0)),
            "away_xg_covered": int(stats15_a.get("xg_used", 0)),
        },
        "markets": {
            "1x2": {"H": round(p_home, 4), "D": round(p_draw, 4), "A": round(p_away, 4)},
            "over_2_5": {"True": round(p_over25, 4), "False": round(p_under25, 4)},
            "btts": {"True": round(p_btts, 4), "False": round(p_btts_no, 4)},
            "first_half_over_0_5": {
                "True": round(p_hybrid_1h, 4), 
                "False": round(1.0 - p_hybrid_1h, 4),
                "details": {
                    "freq": round(p_goal_1h_freq, 4),
                    "poisson": round(p_goal_1h_poisson, 4)
                }
            },
        },
        "coverage": {
            "windows_used": {
                "home": {"5": int(stats5_h.get("n_used", 0)), "10": int(stats10_h.get("n_used", 0)), "15": int(stats15_h.get("n_used", 0))},
                "away": {"5": int(stats5_a.get("n_used", 0)), "10": int(stats10_a.get("n_used", 0)), "15": int(stats15_a.get("n_used", 0))},
            },
            "xg_used": {"home": int(stats15_h.get("xg_used", 0)), "away": int(stats15_a.get("xg_used", 0))},
        },
    }
    
    # --- DYNAMIC BLACKLIST CHECK ---
    toxic_leagues = [667, 56, 331, 57, 675, 140, 1080, 383, 205, 190, 305, 144, 730, 322, 622]
    
    is_elite = False
    if int(league_id) not in toxic_leagues:
        is_elite = (p_goal_1h_freq >= 0.75 and 
                    p_goal_1h_poisson >= 0.75 and 
                    (lambda_home + lambda_away) >= 2.70)
    
    ht_pred = {
        "hybrid_prob": round(p_hybrid_1h, 4),
        "lambda_1h": round(lambda_1h, 4),
        "is_elite": is_elite,
        "details": {
            "freq": round(p_goal_1h_freq, 4),
            "poisson": round(p_goal_1h_poisson, 4)
        }
    }
    
    return analysis, ht_pred

# ==============================
# Backfill Logic
# ==============================

def run_backfill(limit: Optional[int] = None, league_id_filter: Optional[int] = None):
    sb = get_supabase_client()
    
    # Cerchiamo raggruppamenti dove mancano i dati o le nuove predizioni HT
    # Usiamo un filtro OR logico (se possibile dalla libreria) o semplicemente cerchiamo dove ht_predictions è NULL
    # dato che è la colonna più recente.
    filters = [("is", "ht_predictions", "null")]
    if league_id_filter:
        filters.append(("eq", "league_id", league_id_filter))
        
    cols = "fixture_id,league_id,season_year,fixture_date,home_team_id,away_team_id"
    rows = _fetch_all_table("fixture_predictions", cols, filters=filters, page_size=1000)
    
    if limit:
        rows = rows[:limit]
        
    if not rows:
        logger.info("✅ Nessuna fixture da aggiornare. Fine.")
        return

    logger.info(f"📊 Trovate {len(rows)} fixture da processare.")

    # Raggruppamento per league/season
    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (int(r["league_id"]), int(r["season_year"]))
        groups.setdefault(key, []).append(r)

    match_cache = {}
    xg_cache = {}

    total_processed = 0
    for (l_id, s_year), group in groups.items():
        logger.info(f"🚀 Inizio raggruppamento: Lega {l_id} | Stagione {s_year} ({len(group)} fixture)")
        
        batch_to_update = []
        for fixture_row in group:
            try:
                # Costruiamo ctx
                ctx = {
                    "fixture_id": int(fixture_row["fixture_id"]),
                    "league_id": int(fixture_row["league_id"]),
                    "season_year": int(fixture_row["season_year"]),
                    "fixture_date": fixture_row["fixture_date"],
                    "home_team_id": int(fixture_row["home_team_id"]) if fixture_row["home_team_id"] else None,
                    "away_team_id": int(fixture_row["away_team_id"]) if fixture_row["away_team_id"] else None,
                }
                
                res_data = compute_db_json_analisi(ctx, match_cache, xg_cache)
                if res_data:
                    analysis, ht_pred = res_data
                    # Usiamo update invece di upsert per singola riga per isolare l'errore
                    res = sb.table("fixture_predictions").update({
                        "ht_predictions": ht_pred,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("fixture_id", ctx["fixture_id"]).execute()
                    
                    total_processed += 1
                    if total_processed % 10 == 0:
                        logger.info(f"✅ Processate {total_processed} fixture...")

            except Exception as e:
                logger.error(f"❌ Errore critico fixture_id {fixture_row.get('fixture_id')}: {e}")
                if hasattr(e, 'details'):
                    logger.error(f"Dettagli: {e.details}")
                if hasattr(e, 'message'):
                    logger.error(f"Messaggio: {e.message}")

    logger.info(f"🏁 Backfill completato! Totale fixture elaborate: {total_processed}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill storico db_json_analisi")
    parser.add_argument("--limit", type=int, help="Limita il numero totale di fixture da processare")
    parser.add_argument("--league", type=int, help="Filtra per una specifica league_id")
    args = parser.parse_args()

    run_backfill(limit=args.limit, league_id_filter=args.league)
