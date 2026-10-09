"""h_: C1 round_to_tick(NaN) e C3 floor Kelly. Importa codice di produzione, nessuna scrittura."""
import sys, math, os
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)
from Betfair.order_exec import round_to_tick
print("round_to_tick(nan) =", round_to_tick(float("nan")), "| inf =", round_to_tick(float("inf")), "| -inf =", round_to_tick(float("-inf")), "| 'nan' via float() =", round_to_tick(float("nan")))
from Betfair.stream.live_order_build import JURISDICTION_IT, min_stake_rules
v = min_stake_rules(JURISDICTION_IT, "lay", 1000.0, 2.0); print("min_stake_rules(lay,1000,2.0).valid =", v.valid)
# C3: stessa formula di calculate_kelly_stake (money_management.py:795-812) con config reali
import Betfair.money_management as mm
def kelly(bank, p, odds, frac, cap_pct, comm=0.05):
    b = (odds-1)*(1-comm); k = (b*p-(1-p))/b
    if k <= 0: return 0.0
    s = min(bank*k*frac, bank*cap_pct/100); return max(round(s,2),1.0), bank*k*frac
for bank in (1000, 100, 30):
    for p, o in ((0.55, 2.0), (0.52, 2.0), (0.76, 1.35)):
        print("bank", bank, "p", p, "odds", o, "-> (stake dopo floor, kelly grezzo)", kelly(bank, p, o, mm.DEFAULT_KELLY_FRACTION, mm.DEFAULT_MAX_STAKE_PCT))
print("DEFAULTS", mm.DEFAULT_BANKROLL, mm.DEFAULT_KELLY_FRACTION, mm.DEFAULT_MAX_STAKE_PCT)
