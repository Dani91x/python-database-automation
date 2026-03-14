"""
backtest.py - Backtest calibrazione bookmaker

Per ogni mercato principale (1X2, Over/Under, BTTS):
  - Raggruppa per fascia di quota (odds bracket)
  - Calcola: implied_prob (bookie) vs real_rate (storico)
  - Simula flat-stake betting: scommetti 1 unita su ogni partita dove bias > soglia
  - Riporta ROI, profitto, numero scommesse, hit rate

Uso:
    python -m market_intelligence.backtest
"""
import sys, json, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_client import get_supabase_client


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STAKE = 1.0  # unita per scommessa

# Fascie di quota (lo, hi)
BRACKETS = [
    (1.01, 1.20),
    (1.20, 1.40),
    (1.40, 1.60),
    (1.60, 1.80),
    (1.80, 2.00),
    (2.00, 2.25),
    (2.25, 2.50),
    (2.50, 3.00),
    (3.00, 3.50),
    (3.50, 4.50),
    (4.50, 6.00),
    (6.00, 10.0),
    (10.0, 20.0),
    (20.0, 100.0),
]

# Mercati da testare: {nome: (bet_name, value, result_fn)}
MARKETS_TO_TEST = {
    "1X2 - Casa":     ("Match Winner",        "Home",    "home_win"),
    "1X2 - Pareggio": ("Match Winner",        "Draw",    "draw"),
    "1X2 - Trasferta":("Match Winner",        "Away",    "away_win"),
    "Over 2.5":       ("Goals Over/Under",    "Over 2.5","over25"),
    "Under 2.5":      ("Goals Over/Under",    "Under 2.5","under25"),
    "Over 1.5":       ("Goals Over/Under",    "Over 1.5","over15"),
    "Under 3.5":      ("Goals Over/Under",    "Under 3.5","under35"),
    "Over 3.5":       ("Goals Over/Under",    "Over 3.5","over35"),
    "BTTS Si":        ("Both Teams Score",    "Yes",     "btts_yes"),
    "BTTS No":        ("Both Teams Score",    "No",      "btts_no"),
    "DC Casa/X":      ("Double Chance",       "Home/Draw","dc_hd"),
    "DC Tra/X":       ("Double Chance",       "Draw/Away","dc_da"),
    "1T - Over 0.5":  ("Goals Over/Under First Half","Over 0.5","ht_over05"),
    "1T - Over 1.5":  ("Goals Over/Under First Half","Over 1.5","ht_over15"),
}

# Result functions
def _outcome(gh, ga, fn):
    if gh is None or ga is None:
        return None
    t = gh + ga
    return {
        "home_win":  1 if gh > ga else 0,
        "draw":      1 if gh == ga else 0,
        "away_win":  1 if gh < ga else 0,
        "over25":    1 if t > 2.5 else 0,
        "under25":   1 if t < 2.5 else 0,
        "over15":    1 if t > 1.5 else 0,
        "under15":   1 if t < 1.5 else 0,
        "over35":    1 if t > 3.5 else 0,
        "under35":   1 if t < 3.5 else 0,
        "btts_yes":  1 if gh > 0 and ga > 0 else 0,
        "btts_no":   1 if not (gh > 0 and ga > 0) else 0,
        "dc_hd":     1 if gh >= ga else 0,   # Casa o Pareggio
        "dc_da":     1 if gh <= ga else 0,   # Trasferta o Pareggio
        "ht_over05": None,  # Non abbiamo risultato primo tempo -> skip
        "ht_over15": None,
    }.get(fn)


def _get_odd(raw_json_odds, bet_name, value):
    if not isinstance(raw_json_odds, dict):
        return None
    bms = raw_json_odds.get("bookmakers", [])
    if not bms:
        return None
    for bet in bms[0].get("bets", []):
        if bet.get("name") == bet_name:
            for v in bet.get("values", []):
                if v.get("value") == value:
                    try:
                        o = float(v["odd"])
                        return o if o > 1.0 else None
                    except (TypeError, ValueError):
                        return None
    return None


def _bracket_label(lo, hi):
    return f"{lo:.2f}-{'inf' if hi >= 100 else f'{hi:.2f}'}"


def _find_bracket(odd):
    for lo, hi in BRACKETS:
        if lo <= odd < hi:
            return (lo, hi, _bracket_label(lo, hi))
    return None


def _wilson_ci(p, n, z=1.96):
    if n == 0:
        return 0.0
    return z * math.sqrt(p * (1 - p) / n)


def _safe(s):
    return str(s).encode('ascii', 'replace').decode('ascii')


# ---------------------------------------------------------------------------
# Fetch data
# ---------------------------------------------------------------------------

def fetch_all_finished(sb):
    print("  Fetching partite finite con quote...")
    rows = []
    page = 1000
    off = 0
    while True:
        resp = sb.table("fixture_predictions").select(
            "fixture_id, raw_json_odds, result_home_goals, result_away_goals"
        ).in_(
            "result_status_short", ["FT", "AET", "PEN"]
        ).not_.is_("raw_json_odds", "null").range(off, off + page - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        off += page
    print(f"  Totale: {len(rows)} partite\n")
    return rows


# ---------------------------------------------------------------------------
# Core backtest per un mercato
# ---------------------------------------------------------------------------

def backtest_market(rows, market_name, bet_name, value, result_fn):
    """
    Ritorna lista di bracket results:
    {bracket, n, implied_mean, real_rate, bias, bias_pct, significant,
     roi_flat, profit_flat, n_bets, ci_95}
    """
    acc = defaultdict(lambda: {
        "n": 0, "implied_sum": 0.0, "outcome_sum": 0,
        "bets": [],  # list of (odd, outcome) per calcolo ROI esatto
    })

    for row in rows:
        raw = row.get("raw_json_odds") or {}
        gh = row.get("result_home_goals")
        ga = row.get("result_away_goals")

        odd = _get_odd(raw, bet_name, value)
        if odd is None:
            continue

        outcome = _outcome(gh, ga, result_fn)
        if outcome is None:
            continue  # first half results not available

        brk = _find_bracket(odd)
        if brk is None:
            continue

        lo, hi, label = brk
        cell = acc[label]
        cell["n"] += 1
        cell["implied_sum"] += 1.0 / odd
        cell["outcome_sum"] += outcome
        cell["bets"].append((odd, outcome))

    results = []
    for label, cell in sorted(acc.items(), key=lambda x: float(x[0].split("-")[0])):
        n = cell["n"]
        if n < 10:
            continue

        implied_mean = cell["implied_sum"] / n
        real_rate = cell["outcome_sum"] / n
        bias = real_rate - implied_mean
        ci = _wilson_ci(real_rate, n)
        significant = abs(bias) > ci

        # Flat stake backtest: profitto esatto usando la quota reale di ogni scommessa
        # profit = sum(odd_i * outcome_i - 1) per ogni bet
        profit = sum(odd * outcome - 1.0 for odd, outcome in cell["bets"])
        avg_odd = sum(o for o, _ in cell["bets"]) / n
        roi = (profit / n) * 100  # % sul capitale investito

        results.append({
            "bracket":      label,
            "n":            n,
            "implied_mean": round(implied_mean, 4),
            "real_rate":    round(real_rate, 4),
            "bias":         round(bias, 4),
            "bias_pct":     round(bias * 100, 2),
            "ci_95":        round(ci, 4),
            "significant":  significant,
            "avg_odd":      round(avg_odd, 3),
            "profit":       round(profit, 2),
            "roi":          round(roi, 2),
        })

    return results


# ---------------------------------------------------------------------------
# Print risultati
# ---------------------------------------------------------------------------

def print_market_results(market_name, results):
    if not results:
        print(f"  {market_name}: nessun dato sufficiente")
        return

    print(f"\n  {'='*70}")
    print(f"  MERCATO: {_safe(market_name)}")
    print(f"  {'='*70}")
    print(f"  {'Fascia':<16} {'N':>5} {'Implied':>8} {'Reale':>8} "
          f"{'Bias':>7} {'Sig':>4} {'AvgOdd':>7} {'Profit':>8} {'ROI%':>7}")
    print(f"  {'-'*70}")

    total_n = 0
    total_profit = 0.0
    n_sig_positive = 0
    n_sig_negative = 0

    for r in results:
        sig_mark = "*" if r["significant"] else " "
        bias_arrow = "+" if r["bias"] > 0 else ""
        profit_str = f"{r['profit']:+.1f}"
        roi_str = f"{r['roi']:+.1f}%"

        # Color-code with markers
        edge_mark = ""
        if r["significant"] and r["bias"] > 0.03:
            edge_mark = " <<EDGE"
        elif r["significant"] and r["bias"] < -0.03:
            edge_mark = " [trap]"

        print(f"  {r['bracket']:<16} {r['n']:>5} "
              f"{r['implied_mean']:>7.1%} {r['real_rate']:>7.1%} "
              f"{bias_arrow}{r['bias_pct']:>5.1f}%{sig_mark} "
              f"{r['avg_odd']:>7.2f} {profit_str:>8} {roi_str:>7}"
              f"{_safe(edge_mark)}")

        total_n += r["n"]
        total_profit += r["profit"]
        if r["significant"] and r["bias"] > 0:
            n_sig_positive += 1
        elif r["significant"] and r["bias"] < 0:
            n_sig_negative += 1

    total_roi = (total_profit / total_n * 100) if total_n > 0 else 0
    print(f"  {'-'*70}")
    print(f"  {'TOTALE':<16} {total_n:>5} {'':>8} {'':>8} {'':>7} {'':>4} "
          f"{'':>7} {total_profit:>+8.1f} {total_roi:>+7.1f}%")
    print(f"  Brackets con edge positivo significativo: {n_sig_positive}")
    print(f"  Brackets con trap (bookie avvantaggiato): {n_sig_negative}")


# ---------------------------------------------------------------------------
# Summary complessivo
# ---------------------------------------------------------------------------

def print_global_summary(all_results):
    print(f"\n\n  {'='*70}")
    print("  RIEPILOGO GLOBALE - Migliori opportunita' (edge significativo)")
    print(f"  {'='*70}")
    print(f"  {'Mercato':<20} {'Fascia':<16} {'N':>5} {'Bias':>7} "
          f"{'ROI%':>7} {'AvgOdd':>7}")
    print(f"  {'-'*70}")

    edges = []
    for mname, results in all_results.items():
        for r in results:
            if r["significant"] and r["bias"] > 0.03 and r["n"] >= 30:
                edges.append((mname, r))

    if not edges:
        print("  Nessun edge significativo trovato (bias > 3%, n >= 30).")
    else:
        edges.sort(key=lambda x: -x[1]["roi"])
        for mname, r in edges:
            print(f"  {_safe(mname):<20} {r['bracket']:<16} {r['n']:>5} "
                  f"{r['bias_pct']:>+6.1f}% {r['roi']:>+7.1f}% {r['avg_odd']:>7.2f}")

    print(f"\n  TRAPPOLE (bookie sistematicamente avvantaggiato, n>=30):")
    traps = []
    for mname, results in all_results.items():
        for r in results:
            if r["significant"] and r["bias"] < -0.03 and r["n"] >= 30:
                traps.append((mname, r))

    if not traps:
        print("  Nessuna trappola significativa trovata.")
    else:
        traps.sort(key=lambda x: x[1]["roi"])
        for mname, r in traps[:10]:
            print(f"  {_safe(mname):<20} {r['bracket']:<16} {r['n']:>5} "
                  f"{r['bias_pct']:>+6.1f}% {r['roi']:>+7.1f}% {r['avg_odd']:>7.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 70)
    print("  MARKET INTELLIGENCE - Backtest Calibrazione Bookmaker")
    print(f"  Generato: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)
    print()

    sb = get_supabase_client()
    rows = fetch_all_finished(sb)

    if not rows:
        print("  Nessun dato trovato.")
        return

    all_results = {}

    for market_name, (bet_name, value, result_fn) in MARKETS_TO_TEST.items():
        results = backtest_market(rows, market_name, bet_name, value, result_fn)
        all_results[market_name] = results
        print_market_results(market_name, results)

    print_global_summary(all_results)

    print(f"\n\n  NOTE:")
    print(f"  - 'Implied' = probabilita' implicita bookmaker (1/quota)")
    print(f"  - 'Reale'   = tasso vittoria storico nel nostro DB")
    print(f"  - 'Bias'    = Reale - Implied (positivo = bookie sottovaluta)")
    print(f"  - '*'       = statisticamente significativo (fuori CI 95%%)")
    print(f"  - 'ROI'     = ritorno su investimento flat-stake (1 unita/scommessa)")
    print(f"  - <<EDGE    = opportunita' da sfruttare (bias+sig+ROI positivo)")
    print(f"  - [trap]    = evitare (bookie paga meno del dovuto)")
    print()


if __name__ == "__main__":
    main()
