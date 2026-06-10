"""Carica e cacha (read-only) matches + odds 1X2 e OU2.5 per le leghe principali."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataload import get_league_data

LEAGUES = {39: "Premier", 40: "Championship", 135: "SerieA", 140: "LaLiga",
           78: "Bundesliga", 61: "Ligue1", 88: "Eredivisie", 144: "Jupiler",
           94: "Primeira", 197: "GreeceSL", 203: "SuperLig", 71: "Brasileirao"}

print(f"{'lega':<14}{'matches':>9}{'1x2_fx':>9}{'PinC_H':>9}{'Max_H':>9}{'OU_fx':>8}{'PinCO25':>9}")
for lid, name in LEAGUES.items():
    try:
        m, odds = get_league_data(lid, market_keys=("1", "5"))
        w1 = odds.get("1")
        w5 = odds.get("5")
        pinc = w1["Pinnacle_closing__Home"].notna().sum() if (w1 is not None and not w1.empty and "Pinnacle_closing__Home" in w1) else 0
        maxh = w1["Maximum__Home"].notna().sum() if (w1 is not None and not w1.empty and "Maximum__Home" in w1) else 0
        n1 = 0 if (w1 is None or w1.empty) else len(w1)
        n5 = 0 if (w5 is None or w5.empty) else len(w5)
        pinco = w5["Pinnacle_closing__Over 2.5"].notna().sum() if (w5 is not None and not w5.empty and "Pinnacle_closing__Over 2.5" in w5) else 0
        print(f"{name:<14}{len(m):>9}{n1:>9}{pinc:>9}{maxh:>9}{n5:>8}{pinco:>9}", flush=True)
    except Exception as e:
        print(f"{name:<14} ERR {e}", flush=True)
print("DONE")
