import sys, math; sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.trading import dutching as D
from Betfair.stream.trading import xhedge as X
from Betfair.stream.trading import hedging as H
sel = [(1,2.0),(2,3.5),(3,4.2)]
p = D.dutch_back(sel, 100.0); print("dutch_back book", p.book_pct, [ (l.size,l.profit_if_wins) for l in p.legs], "worst", p.worst_profit)
q = D.dutch_back_for_target(sel, 5.0); print("target5 -> total", q.total_stake, "worst", q.worst_profit, "best", q.best_profit)
l = D.dutch_lay([(1,2.0),(2,3.5),(3,4.2),(4,9.0)], 100.0); print("dutch_lay book", l.book_pct, [(x.size,x.profit_if_wins) for x in l.legs])
# xhedge: back 10@3 sul 1-0 CS + lay 5@2 sull'over
pos = [X.XPosition(market_type="CORRECT_SCORE", selection="1-0", side="back", size=10.0, odds=3.0, line=None)] if hasattr(X,"XPosition") else []
try:
    g = X.pnl_by_scoreline(pos); s = X.exposure_summary(g); print("xhedge worst/best/mean", s.worst, s.best, round(s.mean,3))
    h = X.suggest_cs_hedge(g, {(0,0):9.0,(1,0):6.0,(0,1):10.0,(1,1):7.0}); print("hedge", h.actionable, h.note[:110])
except Exception as e: print("xhedge probe errore:", type(e).__name__, str(e)[:100])
# hedging: payoffs e equalize 3 runner (somma stake netta 0)
import inspect
print("hedging.PositionInput campi:", [f for f in getattr(H.PositionInput,'__dataclass_fields__',{})])
