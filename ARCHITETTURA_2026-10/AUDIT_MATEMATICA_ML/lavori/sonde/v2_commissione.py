"""V2 C4: arrotondamento commissione. Safe settle_group vs Mike settle_legs_by_market vs half-up
Decimal vs paper tennis _commissioni_per_ordine (somma quote vs commissione mercato). Sola lettura."""
import sys, random
from decimal import Decimal, ROUND_HALF_UP
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.safe_strategy.execution import settle_group
from Betfair.mike import engine as ME

c = 0.05
def hu(x): return float(Decimal(str(round(x, 10))).quantize(Decimal("0.01"), ROUND_HALF_UP))
# 1) lordo singolo mercato a passo 1c (come C-R2), tre metodi
n = 0; ds = dm = dsm = 0; tot_s = tot_m = tot_h = 0.0
for cents in range(1, 3001):
    g = cents / 100.0
    h = round(g - hu(g * c), 2)
    # Safe: trade con win=g (lose=0): uso la formula interna net - net*c arrotondata
    s = round(g - g * c, 2)
    m = round(g - round(g * c, 2), 2)           # Mike: comm = round(v*c,2)
    n += 1; ds += (s != h); dm += (m != h); dsm += (s != m)
    tot_s += s; tot_m += m; tot_h += h
print(f"lordi 0.01..30.00 (n={n}): Safe!=halfup {ds}, Mike!=halfup {dm}, Safe!=Mike {dsm}")
print(f"somma netti: Safe {tot_s:.2f} Mike {tot_m:.2f} halfup {tot_h:.2f}  -> scarto medio per mercato Safe-halfup {(tot_s-tot_h)/n*100:+.4f} cent, Mike-halfup {(tot_m-tot_h)/n*100:+.4f} cent")
# lordi realistici (stake 10 EUR, back a quote tick, vincente): 
random.seed(1); nn=20000; d=0; tot=0.0
for _ in range(nn):
    stake = random.choice([1,1.5,2,5,7,10,15,25]); q = random.choice([1.2,1.5,1.8,2.0,2.5,3.2,4.5,7.0])
    g = round(stake*(q-1), 2)
    h = round(g - hu(g*c), 2); s = round(g - g*c, 2); m = round(g - round(g*c,2),2)
    d += (s != h) + 0*(m!=h); tot += (s-h)
print(f"mercati realistici {nn}: Safe!=halfup in {d} casi ({d/nn*100:.2f}%), deriva netta {tot*100/nn:+.4f} cent/mercato")
# 2) paper tennis: somma quote vs commissione mercato
from types import SimpleNamespace
import Betfair.stream.tennis_live.tennis_live_order_worker as TW
diff = 0; maxd = 0.0
random.seed(2)
for _ in range(5000):
    k = random.randint(2, 6)
    pnls = [round(random.uniform(-15, 15), 2) for _ in range(k)]
    orders = [SimpleNamespace(i=i) for i in range(k)]
    orig_t, orig_p = TW._is_terminal, TW._pnl_ordine
    TW._is_terminal = lambda o: True
    TW._pnl_ordine = lambda o, P=pnls: P[o.i]
    q = TW._commissioni_per_ordine(orders, c)
    TW._is_terminal, TW._pnl_ordine = orig_t, orig_p
    tot = max(0.0, sum(pnls)) * c
    dd = round(sum(q.values()) - round(tot, 2), 2)
    if dd: diff += 1; maxd = max(maxd, abs(dd))
print(f"paper tennis: su 5000 mercati sintetici la somma delle quote != commissione mercato in {diff} casi, scarto max {maxd:.2f} EUR")
