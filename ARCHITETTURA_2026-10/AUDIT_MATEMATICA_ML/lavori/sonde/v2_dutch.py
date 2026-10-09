"""V2: dutching - (a) UI vs server in modo variable, (b) variable+lay piazza BACK, (c) target lordo.
Importa il codice di produzione (trading/dutching.py) in sola lettura; la formula UI e' la copia
letterale di DutchingPanel.tsx:194-209 (stake = total * (1/p * w) / sum(1/p * w))."""
import sys
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.trading.dutching import dutch_variable, dutch_back, dutch_lay, dutch_back_for_target

q = [2.5, 3.0, 4.0]; w = [1.0, 2.0, 1.0]; T = 100.0
# UI (anteprima)
ws = [(1 / p) * ww for p, ww in zip(q, w)]
ui = [round(T * x / sum(ws), 2) for x in ws]
ui_prof = [round(s * p - T, 2) for s, p in zip(ui, q)]
print("UI   stake", ui, "profitto se vince", ui_prof)
pl = dutch_variable([(i, p, ww) for i, (p, ww) in enumerate(zip(q, w))], T)
print("SERV stake", [l.size for l in pl.legs], "profitto", [l.profit_if_wins for l in pl.legs], "side", pl.side)

# (b) variable + lay: il worker (live_order_worker.py:2916-2919) chiama dutch_variable ignorando side
print("\n(b) side richiesto lay, mode variable -> piano del server: side =", pl.side,
      "(il worker usa plan.side per build_order: live_order_worker.py:~2960)")
lay = dutch_lay([(i, p) for i, p in enumerate(q)], T)
print("    se fosse lay equal: side", lay.side, "stake", [l.size for l in lay.legs])
# rischio: BACK T totale vs lay con liability
print("    BACK variable rischio = sum stake =", round(sum(l.size for l in pl.legs), 2),
      "| lay equal liability massima =", max(round(l.size * (l.price - 1), 2) for l in lay.legs))

# (c) target lordo
for c in (0.05, 0.02):
    tp = dutch_back_for_target([(0, 2.5), (1, 3.0), (2, 4.0)], 5.0)
    print(f"\n(c) target 5.00: profitti lordi {[l.profit_if_wins for l in tp.legs]}; netto c={c}: {round(5.0*(1-c),2)}")
