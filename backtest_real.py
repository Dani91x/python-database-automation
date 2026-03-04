"""
BACKTEST REALE v2 — Parse odds da API-Football (raw_json_odds.bookmakers[0].bets)
"""
import sys, os, json, math
sys.path.insert(0, '.')
from db_client import get_supabase_client
from collections import defaultdict

sb = get_supabase_client()

# ======================================================================
# 1. FETCH
# ======================================================================
print("Fetching dati storici...")
all_data = []
for offset in range(0, 30000, 1000):
    resp = sb.table("fixture_predictions").select(
        "fixture_id, fixture_date, db_json_analisi, raw_json_odds, "
        "result_status_short, result_home_goals, result_away_goals"
    ).in_("result_status_short", ["FT", "AET", "PEN"]).range(offset, offset + 999).execute()
    batch = resp.data or []
    all_data.extend(batch)
    if len(batch) < 1000: break
print(f"  Total: {len(all_data)}")

print("Fetching HT...")
fids = [r["fixture_id"] for r in all_data]
ht_map = {}
for i in range(0, len(fids), 200):
    resp = sb.table("matches").select("fixture_id, halftime_home, halftime_away").in_("fixture_id", fids[i:i+200]).execute()
    for r in (resp.data or []): ht_map[r["fixture_id"]] = (r.get("halftime_home"), r.get("halftime_away"))

# ======================================================================
# 2. PARSE ODDS DA API-FOOTBALL
# ======================================================================
def parse_apifootball_odds(raw):
    """Estrae le quote dalla struttura API-Football: bookmakers[0].bets"""
    if not isinstance(raw, dict): return None
    bookmakers = raw.get("bookmakers", [])
    if not bookmakers: return None
    bets = bookmakers[0].get("bets", [])
    
    odds = {}
    for bet in bets:
        name = bet.get("name", "")
        vals = {v["value"]: float(v["odd"]) for v in bet.get("values", []) if v.get("odd")}
        
        if name == "Match Winner":
            odds["H"] = vals.get("Home")
            odds["D"] = vals.get("Draw")
            odds["A"] = vals.get("Away")
        elif name == "Goals Over/Under":
            odds["O25"] = vals.get("Over 2.5")
            odds["U25"] = vals.get("Under 2.5")
            odds["O15"] = vals.get("Over 1.5")
            odds["U15"] = vals.get("Under 1.5")
            odds["O35"] = vals.get("Over 3.5")
            odds["U35"] = vals.get("Under 3.5")
        elif name == "Both Teams Score":
            odds["BTTS"] = vals.get("Yes")
            odds["BTTS_NO"] = vals.get("No")
        elif name == "Goals Over/Under First Half":
            odds["HT05"] = vals.get("Over 0.5")
            odds["HT_U05"] = vals.get("Under 0.5")
    return odds

rows = []
no_odds = 0
for r in all_data:
    analysis = r.get("db_json_analisi")
    if not analysis or not isinstance(analysis, dict): continue
    markets = analysis.get("markets")
    if not markets: continue
    
    odds = parse_apifootball_odds(r.get("raw_json_odds"))
    if not odds:
        no_odds += 1
        continue
    
    gh = r.get("result_home_goals")
    ga = r.get("result_away_goals")
    if gh is None or ga is None: continue
    
    ht = ht_map.get(r["fixture_id"], (None, None))
    rows.append({
        "fixture_id": r["fixture_id"],
        "date": str(r.get("fixture_date", ""))[:10],
        "markets": markets, "odds": odds,
        "gh": int(gh), "ga": int(ga),
        "hth": int(ht[0]) if ht[0] is not None else None,
        "hta": int(ht[1]) if ht[1] is not None else None,
    })

print(f"Match con analisi + odds: {len(rows)} (senza odds: {no_odds})")
dates = sorted(set(r["date"] for r in rows))
print(f"Range: {dates[0]} → {dates[-1]}")

# ======================================================================
# 3. CALIBRATION
# ======================================================================
cal = json.load(open("calibration_results.json", "r", encoding="utf-8"))

def get_correction(label, prob):
    if label not in cal: return 1.0
    bins = cal[label].get("bins", {})
    bi = min(int(prob * 10), 9)
    bl = f"{bi*10}-{bi*10+10}%"
    if bl in bins and bins[bl]["n"] >= 20:
        return bins[bl]["correction"]
    return cal[label].get("global_correction", 1.0)

# ======================================================================
# 4. HELPERS
# ======================================================================
def get_prob(markets, mk, sk):
    val = (markets.get(mk) or {}).get(sk)
    if val is None: return None
    return val / 100.0 if val > 1 else val

def check_result(gh, ga, hth, hta, ct):
    if ct == "home_win": return gh > ga
    if ct == "draw": return gh == ga
    if ct == "away_win": return gh < ga
    if ct == "over25": return (gh + ga) >= 3
    if ct == "under25": return (gh + ga) < 3
    if ct == "btts_yes": return gh >= 1 and ga >= 1
    if ct == "btts_no": return gh == 0 or ga == 0
    if ct == "ht_over05":
        if hth is None or hta is None: return None
        return (hth + hta) >= 1
    if ct == "ht_under05":
        if hth is None or hta is None: return None
        return (hth + hta) == 0
    return None

MARKETS = [
    #(label,          mk,                    sk,     odds_code, check_type, min_odds)
    ("1x2 Home",      "1x2",                 "H",    "H",       "home_win",   None),
    ("1x2 Draw",      "1x2",                 "D",    "D",       "draw",       None),
    ("1x2 Away",      "1x2",                 "A",    "A",       "away_win",   None),
    ("Over 2.5",      "over_2_5",            "True", "O25",     "over25",     None),
    ("Under 2.5",     "over_2_5",            "False","U25",     "under25",    None),
    ("BTTS Sì",       "btts",                "True", "BTTS",    "btts_yes",   None),
    ("BTTS No",       "btts",                "False","BTTS_NO", "btts_no",    None),
    ("1H Over 0.5",   "first_half_over_0_5", "True", "HT05",   "ht_over05",  None),
    ("1H Under 0.5",  "first_half_over_0_5", "False","HT_U05", "ht_under05", None),
]

# ======================================================================
# 5. BACKTEST ENGINE
# ======================================================================  
def run_bt(rows, min_edge, min_prob, kelly_frac, max_stake_pct, bankroll, comm,
           use_cal=False, markets_enabled=None):
    pnl = staked = bets = wins = 0
    ms = defaultdict(lambda: {"b": 0, "w": 0, "pnl": 0.0, "st": 0.0})
    
    for r in rows:
        best = None
        for label, mk, sk, oc, ct, min_o in MARKETS:
            if markets_enabled and label not in markets_enabled: continue
            
            p = get_prob(r["markets"], mk, sk)
            if p is None or p < min_prob: continue
            
            if use_cal:
                p = min(p * get_correction(label, p), 0.99)
                if p < min_prob: continue
            
            q = r["odds"].get(oc)
            if not q or q <= 1.01: continue
            if min_o and q < min_o: continue
            
            on = (q - 1.0) * (1.0 - comm) + 1.0
            edge = (p * on) - 1.0
            if edge < min_edge: continue
            
            score = edge * math.sqrt(p)
            if best is None or score > best["score"]:
                best = {"label": label, "prob": p, "odds": q, "edge": edge, "score": score, "ct": ct}
        
        if best is None: continue
        
        b = (best["odds"] - 1.0) * (1.0 - comm)
        k = (b * best["prob"] - (1 - best["prob"])) / b if b > 0 else 0
        if k <= 0: continue
        
        stake = min(bankroll * k * kelly_frac, bankroll * max_stake_pct)
        stake = max(round(stake, 2), 1.0)
        
        won = check_result(r["gh"], r["ga"], r["hth"], r["hta"], best["ct"])
        if won is None: continue
        
        profit = stake * (best["odds"] - 1) * (1.0 - comm) if won else -stake
        pnl += profit
        staked += stake
        bets += 1
        if won: wins += 1
        ms[best["label"]]["b"] += 1
        if won: ms[best["label"]]["w"] += 1
        ms[best["label"]]["pnl"] += profit
        ms[best["label"]]["st"] += stake
    
    return {"bets": bets, "wins": wins, "pnl": round(pnl, 2), "staked": round(staked, 2),
            "wr": round(wins/bets*100, 1) if bets > 0 else 0,
            "yield": round(pnl/staked*100, 2) if staked > 0 else 0,
            "ms": dict(ms)}

# ======================================================================
# 6. SCENARIOS
# ======================================================================
L = []
def out(s=""): L.append(s); print(s)

existing = {"1x2 Home", "1x2 Draw", "1x2 Away", "Over 2.5", "BTTS Sì", "1H Over 0.5"}
all_mkt = {m[0] for m in MARKETS}
no_ht = {"1x2 Home", "1x2 Draw", "1x2 Away", "Over 2.5", "Under 2.5", "BTTS Sì", "BTTS No"}

out("=" * 90)
out(f"  BACKTEST REALE — {len(rows)} match con quote API-Football ({dates[0]} → {dates[-1]})")
out("=" * 90)

scenarios = [
    ("A) ATTUALI: 6mkt, edge≥5%, prob≥55%, kelly=0.25, max3%",
     0.05, 0.55, 0.25, 0.03, False, existing),
    ("B) SEVERI: 6mkt, edge≥10%, prob≥60%, kelly=0.15, max2%",
     0.10, 0.60, 0.15, 0.02, False, existing),
    ("C) CALIBRATI: 6mkt, edge≥10%, prob≥60%, kelly=0.15, max2%",
     0.10, 0.60, 0.15, 0.02, True, existing),
    ("D) 9MKT+CAL: tutti, edge≥10%, prob≥60%",
     0.10, 0.60, 0.15, 0.02, True, all_mkt),
    ("E) 7MKT+CAL (no HT): edge≥10%, prob≥60%",
     0.10, 0.60, 0.15, 0.02, True, no_ht),
    ("F) SOLO 1X2+CAL: edge≥10%, prob≥55%",
     0.10, 0.55, 0.15, 0.02, True, {"1x2 Home", "1x2 Draw", "1x2 Away"}),
    ("G) 7MKT+CAL: edge≥15%, prob≥60% (ultra)",
     0.15, 0.60, 0.15, 0.02, True, no_ht),
    ("H) 7MKT+CAL: edge≥8%, prob≥58%",
     0.08, 0.58, 0.15, 0.02, True, no_ht),
]

for name, me, mp, kf, ms_pct, uc, mkts in scenarios:
    r = run_bt(rows, me, mp, kf, ms_pct, 1000, 0.05, uc, mkts)
    out(f"\n  {name}")
    out(f"     Bets: {r['bets']:5d} | WR: {r['wr']:5.1f}% | P&L: {r['pnl']:+10.2f}€ | Yield: {r['yield']:+6.2f}% | Staked: {r['staked']:,.0f}€")
    for mk, s in sorted(r["ms"].items(), key=lambda x: x[1]["pnl"], reverse=True):
        wr = s["w"]/s["b"]*100 if s["b"]>0 else 0
        y = s["pnl"]/s["st"]*100 if s["st"]>0 else 0
        out(f"       {mk:18s}: {s['b']:5d} bets | WR {wr:5.1f}% | P&L {s['pnl']:+9.2f}€ | Yield {y:+5.1f}%")

with open("backtest_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(L))

print(f"\n✅ backtest_results.txt")
