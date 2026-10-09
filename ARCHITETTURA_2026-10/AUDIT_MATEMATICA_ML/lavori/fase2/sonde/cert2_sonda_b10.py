import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from Betfair.order_exec import round_to_tick
from flumine.utils import get_nearest_price
n=0; diff=0; ex=[]
for i in range(101, 100001):
    p = i/100.0   # 1.01 .. 1000.00 al centesimo
    a = round_to_tick(p); b = get_nearest_price(p)
    n+=1
    if abs(a-b) > 1e-9:
        diff+=1
        if len(ex)<4: ex.append((p,a,b))
print("B10 punti", n, "diversi", diff, ex)
# mezzo tick: punti a meta' fra due tick
import itertools
