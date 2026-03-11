"""
backtest_audit.py - Audit delle quote disponibili per backtest

Analizza:
1. fixture_predictions.raw_json_odds (struttura API-Football)
2. match_odds table (Betano)

Per ogni mercato: conta record con quota + risultato disponibili.
"""
import sys, json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_supabase_client


# -- Helpers ------------------------------------------------------------------

def _safe(s):
    return str(s).encode('ascii', 'replace').decode('ascii')


def _parse_api_football_odds(raw_json_odds):
    """
    Estrae mercati da struttura API-Football:
    {"bookmakers": [{"bets": [{"name": "Match Winner", "values": [...]}]}]}
    Ritorna dict {market_label: float}
    """
    if not isinstance(raw_json_odds, dict):
        return {}
    bookmakers = raw_json_odds.get("bookmakers", [])
    if not bookmakers:
        return {}
    result = {}
    for bet in bookmakers[0].get("bets", []):
        name = bet.get("name", "")
        for v in bet.get("values", []):
            val = v.get("value", "")
            try:
                odd = float(v.get("odd", 0))
                if odd > 1.0:
                    key = f"{name} | {val}"
                    result[key] = odd
            except (TypeError, ValueError):
                pass
    return result


# -- Phase 1: raw_json_odds in fixture_predictions ----------------------------

def audit_raw_json_odds(sb):
    print("\n" + "=" * 62)
    print("  SOURCE 1: fixture_predictions.raw_json_odds (API-Football)")
    print("=" * 62)

    # Fetch finished fixtures with odds
    print("\n  Fetching finished fixtures con raw_json_odds...")
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, raw_json_odds, result_home_goals, result_away_goals, result_status_short"
        ).in_(
            "result_status_short", ["FT", "AET", "PEN"]
        ).not_.is_("raw_json_odds", "null").range(
            offset, offset + page_size - 1
        ).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    print(f"  Fixtures finite con raw_json_odds non-null: {len(rows)}")

    # Count per market
    market_stats = defaultdict(lambda: {"total": 0, "with_result": 0})

    for row in rows:
        raw = row.get("raw_json_odds") or {}
        gh = row.get("result_home_goals")
        ga = row.get("result_away_goals")
        has_result = gh is not None and ga is not None

        if not isinstance(raw, dict) or not raw.get("bookmakers"):
            continue

        markets = _parse_api_football_odds(raw)
        for mkey in markets:
            market_stats[mkey]["total"] += 1
            if has_result:
                market_stats[mkey]["with_result"] += 1

    # Print sorted by count
    print(f"\n  {'Mercato':<50} {'Totale':>8} {'Con risultato':>14} {'Backtest OK':>12}")
    print(f"  {'-'*86}")

    sorted_markets = sorted(market_stats.items(), key=lambda x: -x[1]["with_result"])
    for mkey, stats in sorted_markets:
        ok = "YES" if stats["with_result"] >= 200 else ("~" if stats["with_result"] >= 50 else "NO")
        mkey_safe = _safe(mkey[:49])
        print(f"  {mkey_safe:<50} {stats['total']:>8} {stats['with_result']:>14} {ok:>12}")

    n_200 = sum(1 for s in market_stats.values() if s["with_result"] >= 200)
    n_50  = sum(1 for s in market_stats.values() if s["with_result"] >= 50)
    print(f"\n  Mercati con >= 200 quote+risultato: {n_200}")
    print(f"  Mercati con >=  50 quote+risultato: {n_50}")

    return market_stats


# -- Phase 2: match_odds table ------------------------------------------------

def audit_match_odds(sb):
    print("\n" + "=" * 62)
    print("  SOURCE 2: match_odds table (Betano)")
    print("=" * 62)

    # Check table structure - get a sample first
    print("\n  Fetching sample da match_odds...")
    try:
        resp = sb.table("match_odds").select("*").limit(3).execute()
        sample = resp.data or []
        if not sample:
            print("  Tabella match_odds vuota o non accessibile.")
            return {}
        print(f"  Colonne: {list(sample[0].keys())}")
        print(f"  Esempio row: {json.dumps(sample[0], indent=2, default=str)[:500]}")
    except Exception as e:
        print(f"  Errore accesso match_odds: {e}")
        return {}

    # Count total rows
    print("\n  Contando righe totali in match_odds...")
    try:
        resp = sb.table("match_odds").select("fixture_id", count="exact").execute()
        total = resp.count if hasattr(resp, 'count') else len(resp.data or [])
        print(f"  Totale righe: {total}")
    except Exception as e:
        print(f"  Errore count: {e}")

    # Fetch all rows (assuming small table ~16 rows)
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("match_odds").select("*").range(
            offset, offset + page_size - 1
        ).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    print(f"  Righe totali fetched: {len(rows)}")

    if not rows:
        return {}

    # Analyze structure
    # Find columns that look like odds or market names
    col_names = list(rows[0].keys()) if rows else []
    print(f"\n  Struttura colonne ({len(col_names)} totali):")

    # Look for market/bet type columns
    non_meta = [c for c in col_names if c not in
                ("id", "fixture_id", "created_at", "updated_at", "bookmaker_id",
                 "bookmaker_name", "fixture_date", "league_id", "home_team_id", "away_team_id")]

    # Count distinct market types if there's a market_name/bet_name column
    market_col = None
    for cand in ("market_name", "bet_name", "bet_type", "market_type", "type"):
        if cand in col_names:
            market_col = cand
            break

    if market_col:
        market_counts = defaultdict(int)
        for row in rows:
            market_counts[row.get(market_col, "unknown")] += 1
        print(f"\n  Distribuzione per {market_col}:")
        for m, cnt in sorted(market_counts.items(), key=lambda x: -x[1]):
            print(f"    {_safe(str(m)):<40} {cnt:>6}")
    else:
        print(f"\n  Colonne non-meta: {non_meta[:20]}")
        # Print unique values for small sets
        for col in non_meta[:5]:
            vals = set(str(r.get(col, ""))[:30] for r in rows[:20])
            print(f"    {col}: {list(vals)[:5]}")

    return {"rows": len(rows), "columns": col_names}


# -- Phase 3: Check fixture_predictions for all odds types --------------------

def audit_fixture_predictions_all(sb):
    print("\n" + "=" * 62)
    print("  SOURCE 3: fixture_predictions - tutti i record (sample)")
    print("=" * 62)

    # Get a sample including unfinished to see what odds look like
    print("\n  Fetching sample con raw_json_odds non-null (any status)...")
    resp = sb.table("fixture_predictions").select(
        "fixture_id, result_status_short, raw_json_odds"
    ).not_.is_("raw_json_odds", "null").limit(5).execute()

    samples = resp.data or []
    print(f"  Sample fetched: {len(samples)}")

    bookmaker_counts = defaultdict(int)
    for row in samples:
        raw = row.get("raw_json_odds") or {}
        if isinstance(raw, dict):
            for bm in raw.get("bookmakers", []):
                bookmaker_counts[bm.get("name", "unknown")] += 1
                for bet in bm.get("bets", []):
                    print(f"    Fixture {row['fixture_id']} | Status: {row['result_status_short']} | Bet: {_safe(bet.get('name',''))}")

    # Total count with odds (any status)
    print("\n  Contando tutti i fixture con raw_json_odds (any status)...")
    rows_any = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, result_status_short"
        ).not_.is_("raw_json_odds", "null").range(
            offset, offset + page_size - 1
        ).execute()
        batch = resp.data or []
        rows_any.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    status_counts = defaultdict(int)
    for r in rows_any:
        status_counts[r.get("result_status_short", "null")] += 1

    print(f"  Totale con raw_json_odds: {len(rows_any)}")
    print("  Per status:")
    for s, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"    {_safe(str(s)):<20} {cnt:>6}")


# -- Main ---------------------------------------------------------------------

def main():
    print("=" * 62)
    print("  MARKET INTELLIGENCE - Backtest Data Audit")
    print("=" * 62)

    sb = get_supabase_client()

    # Source 1: raw_json_odds
    market_stats = audit_raw_json_odds(sb)

    # Source 2: match_odds table
    audit_match_odds(sb)

    # Source 3: overall fixture_predictions odds coverage
    audit_fixture_predictions_all(sb)

    print("\n" + "=" * 62)
    print("  CONCLUSIONE")
    print("=" * 62)
    n_200 = sum(1 for s in market_stats.values() if s["with_result"] >= 200)
    n_any = sum(1 for s in market_stats.values() if s["with_result"] > 0)
    print(f"  Mercati in raw_json_odds con risultato: {n_any}")
    print(f"  Mercati con >= 200 coppie (quota+risultato): {n_200}")
    if n_200 == 0:
        print("\n  CONCLUSIONE: Dati insufficienti per backtest significativo.")
        print("  Con < 200 coppie per mercato, i risultati sarebbero rumore statistico.")
        print("  Suggerimento: popolare piu' quote nel database prima di fare backtest.")
    else:
        print("\n  Backtest possibile sui mercati con >= 200 coppie.")


if __name__ == "__main__":
    main()
