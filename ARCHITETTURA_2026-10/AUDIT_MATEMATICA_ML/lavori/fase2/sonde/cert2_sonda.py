import sys, math
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
out = {}
def tr(name, fn):
    try: print(name, "->", fn())
    except Exception as e: print(name, "EXC", type(e).__name__, str(e)[:100])
# B1
from Betfair.order_exec import round_to_tick
tr("B1 round_to_tick(nan)", lambda: round_to_tick(float("nan")))
tr("B1 round_to_tick(inf)", lambda: round_to_tick(float("inf")))
tr("B1 round_to_tick(-inf)", lambda: round_to_tick(float("-inf")))
# B17/B18/M23
from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds, p_match, p_set
tr("B18 estimate_holds(0,0,0,0)", lambda: estimate_holds(0,0,0,0))
tr("B17 p_set 6-6 tb", lambda: p_set(6,6,True,0.9,0.5))
tr("B17 p_set 6-6 tb (hold A .5 B .9)", lambda: p_set(6,6,True,0.5,0.9))
tr("B17 p_match 0-0 ha=.9 hb=.6 A serve", lambda: p_match(0,0,0,0,True,0.9,0.6,3))
tr("B17 p_match 0-0 ha=.9 hb=.6 B serve", lambda: p_match(0,0,0,0,False,0.9,0.6,3))
tr("M23 bo3 vs bo5 stesso stato (1-0 set, 2-1 giochi)", lambda: (p_match(1,0,2,1,True,0.8,0.7,3), p_match(1,0,2,1,True,0.8,0.7,5)))
# M23: stesso stato, ha=hb=.75 (breaks=0) vs stima con 1 break subito
tr("M23 holds con 0 break a 4-1", lambda: estimate_holds(0,0,4,1))
# B27
from value_engine.poisson_total import lam_from_prematch
tr("B27 lam_from_prematch(nan)", lambda: lam_from_prematch(float("nan")))
from value_engine.devig import devig_pair
tr("B27 devig_pair(2.0,1.0)", lambda: devig_pair(2.0, 1.0))
tr("B27 devig_pair(2.0,0.9)", lambda: devig_pair(2.0, 0.9))
# B14 devig multiplicative
# M14 wald vs wilson
def wald(p,n,z=1.96): return z*math.sqrt(p*(1-p)/n)
def wilson_hw(p,n,z=1.96):
    d=1+z*z/n; return z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
for p,n in ((1.0,30),(0.97,30),(0.5,30)):
    print("M14 wald", p, n, round(wald(p,n),4), "wilson half-width", round(wilson_hw(p,n),4), "p+wald>1:", p+wald(p,n)>1)
# M18
eq=[-10,-30]; peak0=0; dd_ts=max(max(peak0,*eq[:i+1])-eq[i] for i in range(len(eq)))
dd_sql=max(max(eq[:i+1])-eq[i] for i in range(len(eq)))
print("M18 TS",dd_ts,"SQL",dd_sql)
# M21: ratio residuo (90+inj-m_bucket)/(90+inj-m) per ingresso <=80/85
for inj in (3,):
    for m in (79,84,89):
        b=(m//5)*5
        print("M21 m",m,"bucket",b,"ratio residual time",round((90+inj-b)/(90+inj-m),2))
