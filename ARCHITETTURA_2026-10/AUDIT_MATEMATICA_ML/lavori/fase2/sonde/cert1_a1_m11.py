import sys
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.trading.dutching import dutch_variable
# A1: lato richiesto lay (prezzi lay), il piano e' sempre back
p = dutch_variable([(1, 2.2, 1.0), (2, 3.5, 1.0), (3, 5.0, 1.0)], 100.0)
print("A1 side del piano:", p.side, "book", p.book_pct, "worst", p.worst_profit)
# M11: anteprima UI (stake = T*w/sumW con w=(1/p)*uw) vs server
def ui(sel, T):
    w = [(1/pr)*uw for _, pr, uw in sel]; sw = sum(w)
    st = [round(T*x/sw, 2) for x in w]
    return st, [round(s*pr - T, 2) for s, (_, pr, _) in zip(st, sel)]
for sel in ([(1,2.0,1.0),(2,4.0,3.0),(3,5.0,1.0)], [(1,3.0,1.0),(2,3.0,3.0),(3,3.0,1.0)], [(1,2.5,1.0),(2,3.5,2.0),(3,6.0,1.0)]):
    st, pf = ui(sel, 100.0)
    sv = dutch_variable(sel, 100.0)
    print("sel", sel)
    print(" UI    stake", st, "profit", pf)
    print(" SERVER stake", [l.size for l in sv.legs], "profit", [l.profit_if_wins for l in sv.legs], sv.note)
