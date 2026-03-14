"""
calibration.py ? Phase 2: Calibration Tables

Per ogni lega qualificata + ogni mercato + ogni fascia di quota:
  implied_prob (bookie) vs actual_win_rate (storico) -> bias

Output: cache/calibration_tables.json

Uso:
    python pipeline.py --calibration
"""
import sys, json, os, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_supabase_client
from market_intelligence.mi_config import (
    CACHE_DIR, REGISTRY_FILE, CALIBRATION_FILE,
    MARKETS, ODDS_BRACKETS, MIN_BRACKET_SAMPLES
)

CACHE_DIR.mkdir(exist_ok=True)


# -- Helpers odds ------------------------------------------------------------

def _find_betfair_bm(bookmakers: list):
    """Find Betfair sportsbook. Name match → index 2 (bookmaker #3) → index 0."""
    for bm in bookmakers:
        if "betfair" in str(bm.get("name", "")).lower():
            return bm
    if len(bookmakers) > 2:
        return bookmakers[2]
    return bookmakers[0] if bookmakers else None


def _parse_odds_for_market(raw_json_odds: dict, market_cfg: dict) -> float | None:
    """Estrae la quota Betfair sportsbook per uno specifico mercato/valore."""
    if not isinstance(raw_json_odds, dict):
        return None
    bookmakers = raw_json_odds.get("bookmakers", [])
    if not bookmakers:
        return None
    bm = _find_betfair_bm(bookmakers)
    if bm is None:
        return None
    for bet in bm.get("bets", []):
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
    """Ritorna 1 se l'esito si e verificato, 0 altrimenti, None se dati mancanti."""
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


def _bracket_label(lo: float, hi: float) -> str:
    hi_str = "inf" if hi >= 15.0 else f"{hi:.2f}"
    return f"{lo:.2f}-{hi_str}"


def _find_bracket(odd: float) -> str | None:
    for lo, hi in ODDS_BRACKETS:
        if lo <= odd < hi:
            return _bracket_label(lo, hi)
    return None


def _wilson_ci(p: float, n: int, z: float = 1.96) -> float:
    """Wilson score confidence interval half-width (95%)."""
    if n == 0:
        return 0.0
    return z * math.sqrt(p * (1 - p) / n)


# -- Core calibration --------------------------------------------------------

def _build_calibration_table(rows: list) -> dict:
    """
    Costruisce la tabella di calibrazione da una lista di row.
    Ritorna: {market_key: {bracket_label: {n, implied_mean, real_rate, bias, ...}}}
    """
    # Accumulator: {market: {bracket: {n, implied_sum, outcome_sum}}}
    acc = {
        mkey: defaultdict(lambda: {"n": 0, "implied_sum": 0.0, "outcome_sum": 0})
        for mkey in MARKETS
    }

    for row in rows:
        raw_odds = row.get("raw_json_odds") or {}
        gh = row.get("result_home_goals")
        ga = row.get("result_away_goals")
        if gh is None or ga is None:
            continue
        gh, ga = int(gh), int(ga)

        for mkey, mcfg in MARKETS.items():
            odd = _parse_odds_for_market(raw_odds, mcfg)
            if odd is None:
                continue
            outcome = _compute_outcome(gh, ga, mcfg["result_fn"])
            if outcome is None:
                continue
            brk = _find_bracket(odd)
            if brk is None:
                continue
            cell = acc[mkey][brk]
            cell["n"] += 1
            cell["implied_sum"] += 1.0 / odd
            cell["outcome_sum"] += outcome

    # Finalize
    result = {}
    for mkey, brackets in acc.items():
        result[mkey] = {}
        for brk, cell in brackets.items():
            n = cell["n"]
            if n < MIN_BRACKET_SAMPLES:
                continue
            implied_mean = cell["implied_sum"] / n
            real_rate    = cell["outcome_sum"] / n
            bias         = real_rate - implied_mean
            ci           = _wilson_ci(real_rate, n)
            # correction_factor: quanto moltiplicare implied_prob per avvicinarsi alla realta
            # clamped per evitare valori estremi con n basso
            corr = real_rate / implied_mean if implied_mean > 0 else 1.0
            corr = max(0.50, min(2.00, corr))
            result[mkey][brk] = {
                "n":                 n,
                "implied_mean":      round(implied_mean, 4),
                "real_rate":         round(real_rate, 4),
                "bias":              round(bias, 4),
                "bias_pct":          round(bias * 100, 2),
                "correction_factor": round(corr, 4),
                "ci_95":             round(ci, 4),
                "significant":       abs(bias) > ci,
            }
    return result


def _print_summary(name: str, table: dict):
    """Stampa i bias significativi trovati."""
    sig = []
    for mkey, brackets in table.items():
        for brk, cell in brackets.items():
            if cell.get("significant") and abs(cell["bias"]) >= 0.03:
                sig.append((mkey, brk, cell))
    if sig:
        sig.sort(key=lambda x: -abs(x[2]["bias"]))
        print(f"    Bias significativi ({name}): {len(sig)}")
        for mkey, brk, cell in sig[:6]:
            arrow = "?" if cell["bias"] > 0 else "?"
            print(f"      {mkey:<12} [{brk}]  "
                  f"implied={cell['implied_mean']:.1%}  "
                  f"reale={cell['real_rate']:.1%}  "
                  f"bias={cell['bias']:+.1%} {arrow}  (n={cell['n']})")
    else:
        print(f"    {name}: nessun bias significativo con campione sufficiente")


# -- Fetch --------------------------------------------------------------------

def _fetch_league_rows(sb, league_id: int) -> list:
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, raw_json_odds, result_home_goals, result_away_goals"
        ).eq("league_id", league_id).in_(
            "result_status_short", ["FT", "AET", "PEN"]
        ).range(offset, offset + page_size - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _fetch_all_rows(sb) -> list:
    """Fetch globale per la calibrazione globale (fallback)."""
    rows = []
    page_size = 1000
    offset = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, league_id, raw_json_odds, result_home_goals, result_away_goals"
        ).in_("result_status_short", ["FT", "AET", "PEN"]).range(
            offset, offset + page_size - 1
        ).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


# -- Main ---------------------------------------------------------------------

def run_calibration() -> dict:
    print("=" * 62)
    print("  MARKET INTELLIGENCE ? Phase 2: Calibration Tables")
    print("=" * 62)

    if not REGISTRY_FILE.exists():
        print("\n  ERRORE: league_registry.json non trovato.")
        print("  Esegui prima: python pipeline.py --audit")
        sys.exit(1)

    with open(REGISTRY_FILE, encoding="utf-8") as f:
        registry = json.load(f)

    qualified = registry.get("qualified_leagues", [])
    print(f"\n  Leghe qualificate: {len(qualified)}")

    sb = get_supabase_client()
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leagues":      {},
        "global":       {},
    }

    # -- Calibrazione globale (fallback per leghe non qualificate) --
    print("\n  Building calibrazione GLOBALE...")
    all_rows = _fetch_all_rows(sb)
    print(f"  Totale righe: {len(all_rows)}")
    global_table = _build_calibration_table(all_rows)
    output["global"] = global_table
    _print_summary("GLOBAL", global_table)

    # -- Calibrazione per lega --
    for league in qualified:
        lid  = league["league_id"]
        name = league["league_name"]
        print(f"\n  Building: {name} (ID {lid}, {league['n_with_odds']} odds)...")
        rows = _fetch_league_rows(sb, lid)
        table = _build_calibration_table(rows)
        output["leagues"][str(lid)] = table
        _print_summary(name, table)

    # -- Salva --
    tmp_path = CALIBRATION_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, CALIBRATION_FILE)
    print(f"\n  Salvato -> {CALIBRATION_FILE}")

    # -- Statistiche finali --
    total_sig = 0
    for mkey, brackets in output["global"].items():
        total_sig += sum(1 for c in brackets.values() if c.get("significant"))
    print(f"  Bias significativi globali trovati: {total_sig}")

    return output


if __name__ == "__main__":
    run_calibration()
