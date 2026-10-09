"""E2 sonda 2: dutching (server vs anteprima UI), tennis p_win, combos._best_split, hold prior. Sola lettura, senza rete."""
import sys, os, math
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)
from Betfair.stream.trading.dutching import dutch_back, dutch_variable, dutch_lay, dutch_back_for_target
# --- 1) variable: server (profitto ~ peso) vs anteprima UI (stake ~ (1/q)*peso)
sel = [(1, 2.5, 1.0), (2, 3.0, 2.0), (3, 4.0, 1.0)]
T = 100.0
plan = dutch_variable(sel, T)
print("SERVER variable:", [(l.selection_id, l.size, l.profit_if_wins) for l in plan.legs], "tot", plan.total_stake)
w = [(1 / p) * wt for _, p, wt in sel]; sw = sum(w)
ui = [(sid, round(T * wi / sw, 2), round(round(T * wi / sw, 2) * p - T, 2)) for (sid, p, _), wi in zip(sel, w)]
print("UI anteprima variable:", ui)
# --- equal: server vs UI
pe = dutch_back([(s, p) for s, p, _ in sel], T)
print("SERVER equal:", [(l.selection_id, l.size, l.profit_if_wins) for l in pe.legs])
# --- target gross vs net commission
pt = dutch_back_for_target([(s, p) for s, p, _ in sel], 5.0)
print("target 5.00 lordo -> totale %.2f, worst lordo %.2f, netto 5%% = %.2f" % (pt.total_stake, pt.worst_profit, pt.worst_profit * 0.95))
# --- 2) hold prior e p_win tennis
from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds, p_match
print("estimate_holds(0,0,0,0)=", estimate_holds(0, 0, 0, 0))
from Betfair.safe_strategy.tennis_opportunity import TennisOpportunityModel, hold_from_serve_point
m = TennisOpportunityModel()
for sets, games, srv in (((1, 0), (3, 1), None), ((1, 0), (4, 2), None), ((0, 0), (0, 0), None)):
    pl = {"sets": {"p1": sets[0], "p2": sets[1]}, "games": {"p1": games[0], "p2": games[1]}, "competition": "ATP Test"}
    st = m._state(pl)
    ha, hb = m._holds(pl)
    raw = m._p_raw_p1(st, ha, hb) if st else None
    print("sets", sets, "games", games, "holds", (ha, hb), "p_raw_p1=%.4f" % raw, "p_adj=%.4f" % m.p_win(pl, "p1"))
print("hold_from_serve_point(0.65)=%.4f (formula chiusa a mano: 0.8300 circa)" % hold_from_serve_point(0.65))
# --- 3) combos._best_split: concavita' numerica (stesso mercato e mercati diversi)
from Betfair.safe_strategy import combos as C
def leg(mkt, sel, side, price, win):
    return C.Leg(market_type="X", market_name="X", line=None, market_id=mkt, runner={"selection_id": sel, "name": str(sel), "back": price, "lay": price, "back_size": 1e4, "lay_size": 1e4}, side=side, win=win, prob_key=None)
outs = [(h, a) for h in range(0, 8) for a in range(0, 8)]
cases = {
 "stesso mercato O2.5 back@2.2 + U2.5 back@2.1 (book<1?)": (leg("m1", 1, "back", 2.2, C._win_over(2.5)), leg("m1", 2, "back", 2.1, C._win_under(2.5))),
 "mercati diversi O2.5 back@2.2 + lay U3.5@1.5": (leg("m1", 1, "back", 2.2, C._win_over(2.5)), leg("m2", 3, "lay", 1.5, C._win_under(3.5))),
}
for name, (a, b) in cases.items():
    units = C._unit_profits((a, b), outs)
    f = lambda x: min(C._net_from_units((a, b), units, (x, 1 - x), 0.05))
    grid = [(f(i / 1000.0), i / 1000.0) for i in range(0, 1001)]
    best = max(grid)
    tern = C._best_split((a, b), outs, 0.05, 60)
    print(name, "| max griglia %.5f @ b=%.3f | ternaria b=%.4f val %.5f" % (best[0], best[1], tern, f(tern)))
