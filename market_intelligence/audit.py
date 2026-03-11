"""
audit.py — Phase 1: Data Audit & League Registry

Scansiona il database e determina quali leghe hanno dati storici
sufficienti per la calibrazione. Salva league_registry.json.

Uso:
    python pipeline.py --audit
    python -m market_intelligence.audit
"""
import sys, json, os
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_supabase_client
from market_intelligence.mi_config import (
    CACHE_DIR, REGISTRY_FILE, MIN_MATCHES_CALIBRATION,
    MIN_MATCHES_SIGNAL, MARKETS
)

CACHE_DIR.mkdir(exist_ok=True)


# -- Helpers ----------------------------------------------------------------

def _parse_bookmaker_odds(raw_json_odds: dict) -> dict:
    """
    Estrae le quote dalla struttura API-Football:
      raw_json_odds["bookmakers"][0]["bets"]
    Ritorna {market_key: float} per i mercati in MARKETS.
    """
    if not isinstance(raw_json_odds, dict):
        return {}
    bookmakers = raw_json_odds.get("bookmakers", [])
    if not bookmakers:
        return {}
    bets = bookmakers[0].get("bets", [])
    extracted = {}
    for bet in bets:
        bet_name = bet.get("name", "")
        values_map = {}
        for v in bet.get("values", []):
            try:
                values_map[v["value"]] = float(v["odd"])
            except (KeyError, ValueError, TypeError):
                pass
        for mkey, mcfg in MARKETS.items():
            if mcfg["bet_name"] == bet_name:
                val = values_map.get(mcfg["value"])
                if val and val > 1.0:
                    extracted[mkey] = val
    return extracted


def _fetch_all_finished(sb) -> list:
    """Fetch tutte le partite finite con i campi necessari per l'audit."""
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, league_id, league_name, season_year, fixture_date, "
            "raw_json_odds, db_json_analisi, "
            "result_status_short, result_home_goals, result_away_goals"
        ).in_("result_status_short", ["FT", "AET", "PEN"]).range(
            offset, offset + page_size - 1
        ).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _count_xg_fixtures(sb, fixture_ids: list) -> set:
    """Ritorna l'insieme di fixture_id che hanno dati xG in match_team_stats."""
    xg_set = set()
    for i in range(0, len(fixture_ids), 200):
        chunk = fixture_ids[i:i + 200]
        resp = sb.table("match_team_stats").select("fixture_id").eq(
            "stat_type", "Expected Goals"
        ).in_("fixture_id", chunk).execute()
        for r in (resp.data or []):
            xg_set.add(r["fixture_id"])
    return xg_set


# -- Main -------------------------------------------------------------------

def run_audit() -> dict:
    """
    Esegue l'audit completo. Salva e ritorna il registry.
    """
    print("=" * 62)
    print("  MARKET INTELLIGENCE — Phase 1: Data Audit")
    print("=" * 62)

    sb = get_supabase_client()

    # 1. Fetch tutte le partite finite
    print("\n  Fetching partite finite...")
    all_rows = _fetch_all_finished(sb)
    print(f"  Totale partite finite trovate: {len(all_rows)}")

    if not all_rows:
        print("  ATTENZIONE: nessuna partita finita nel database.")
        return {}

    # 2. Fetch copertura xG
    print("  Fetching copertura xG...")
    all_fids = [r["fixture_id"] for r in all_rows]
    xg_fixtures = _count_xg_fixtures(sb, all_fids)
    print(f"  Partite con xG: {len(xg_fixtures)}")

    # 3. Aggregazione per lega
    league_data = defaultdict(lambda: {
        "league_name": "",
        "seasons": set(),
        "dates": [],
        "n_total": 0,
        "n_with_result": 0,
        "n_with_odds": 0,
        "n_with_ml": 0,
        "n_with_xg": 0,
        "market_counts": defaultdict(int),
    })

    for row in all_rows:
        lid = row.get("league_id")
        if not lid:
            continue
        d = league_data[lid]
        d["league_name"] = row.get("league_name") or d["league_name"]
        if row.get("season_year"):
            d["seasons"].add(row["season_year"])
        if row.get("fixture_date"):
            d["dates"].append(str(row["fixture_date"])[:10])
        d["n_total"] += 1

        gh = row.get("result_home_goals")
        ga = row.get("result_away_goals")
        if gh is not None and ga is not None:
            d["n_with_result"] += 1

        odds = _parse_bookmaker_odds(row.get("raw_json_odds") or {})
        if odds:
            d["n_with_odds"] += 1
            for mkey in odds:
                d["market_counts"][mkey] += 1

        db_json = row.get("db_json_analisi")
        if isinstance(db_json, dict) and db_json.get("markets", {}).get("1x2"):
            d["n_with_ml"] += 1

        if row["fixture_id"] in xg_fixtures:
            d["n_with_xg"] += 1

    # 4. Costruzione registry
    qualified = []
    unqualified = []

    for lid, d in sorted(league_data.items(), key=lambda x: -x[1]["n_with_odds"]):
        dates = sorted(d["dates"])
        seasons = sorted(d["seasons"])
        n_odds = d["n_with_odds"]
        n_result = d["n_with_result"]
        # Partite "qualificate" = hanno sia odds che risultato
        n_qualified = min(n_odds, n_result)  # approssimazione conservativa

        markets_cov = {}
        for mkey in MARKETS:
            cnt = d["market_counts"].get(mkey, 0)
            markets_cov[mkey] = round(cnt / max(n_odds, 1), 3)

        entry = {
            "league_id":            lid,
            "league_name":          d["league_name"],
            "n_total":              d["n_total"],
            "n_with_result":        n_result,
            "n_with_odds":          n_odds,
            "n_with_ml":            d["n_with_ml"],
            "n_with_xg":            d["n_with_xg"],
            "n_qualified":          n_qualified,
            "qualifies_calibration": n_qualified >= MIN_MATCHES_CALIBRATION,
            "qualifies_signal":      n_qualified >= MIN_MATCHES_SIGNAL,
            "markets_coverage":     markets_cov,
            "season_range":         [seasons[0], seasons[-1]] if seasons else [],
            "first_match":          dates[0] if dates else None,
            "last_match":           dates[-1] if dates else None,
        }

        if entry["qualifies_calibration"]:
            qualified.append(entry)
        else:
            unqualified.append(entry)

    # 5. Stampa tabella (ascii-safe per Windows cp1252)
    def _safe(s): return s.encode('ascii', 'replace').decode('ascii')
    print(f"\n  {'Lega':<36} {'Tot':>5} {'Odds':>5} {'ML':>5} {'xG':>5} {'Cal':>4} {'Sig':>4}")
    print(f"  {'-'*62}")
    for e in qualified + unqualified:
        fc = "OK" if e["qualifies_calibration"] else "-"
        fs = "OK" if e["qualifies_signal"] else "-"
        name = _safe(e["league_name"])[:35]
        print(f"  {name:<36} {e['n_total']:>5} {e['n_with_odds']:>5} "
              f"{e['n_with_ml']:>5} {e['n_with_xg']:>5}    {fc}    {fs}")

    print(f"\n  Leghe qualificate calibrazione (>={MIN_MATCHES_CALIBRATION}): {len(qualified)}")
    print(f"  Leghe qualificate segnale      (>={MIN_MATCHES_SIGNAL}):  "
          f"{sum(1 for e in qualified + unqualified if e['qualifies_signal'])}")

    # 6. Salva registry
    registry = {
        "generated_at":          datetime.now(timezone.utc).isoformat(),
        "total_finished":        len(all_rows),
        "total_leagues_scanned": len(league_data),
        "qualified_leagues":     qualified,
        "unqualified_leagues":   unqualified,
    }

    # Scrittura atomica
    tmp_path = REGISTRY_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, REGISTRY_FILE)
    print(f"\n  Salvato -> {REGISTRY_FILE}")

    return registry


if __name__ == "__main__":
    run_audit()
