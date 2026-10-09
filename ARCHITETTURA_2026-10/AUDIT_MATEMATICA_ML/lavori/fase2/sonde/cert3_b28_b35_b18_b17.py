import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
# --- B18 + B17
from Betfair.stream.tennis_scalper.tennis_winprob import estimate_holds, p_match, p_set
print("B18 estimate_holds(0,0,0,0) =", estimate_holds(0,0,0,0))
# B17: effetto di p_tb fisso 0.5 e del 'serve A' iniziale del set successivo con hold asimmetrici
for ha, hb in [(0.75,0.75),(0.85,0.70)]:
    a = p_match(0,0,0,0,True,ha,hb,3); b = p_match(0,0,0,0,False,ha,hb,3)
    print("B17 hold",ha,hb,"p_match A serve primo:",round(a,4),"B serve primo:",round(b,4))
# set decisivo: 1-1 nei set, 0-0, entrambi i casi di chi serve
print("B17 1-1 set bo3 hold .85/.70 serveA/serveB:", round(p_match(1,1,0,0,True,.85,.70,3),4), round(p_match(1,1,0,0,False,.85,.70,3),4))
# --- B28: tau in-play su griglia dei gol RESIDUI, partita non 0-0 (value_engine) vs rho=0
from value_engine.bivariate import conditional_markets
import inspect
print(inspect.signature(conditional_markets))
for gh, ga, minute in [(0,0,60),(1,1,60),(1,0,70)]:
    for rho in (-0.13, 0.0):
        mk = conditional_markets(1.5, 1.2, rho, minute, gh, ga)
        print("B28", (gh,ga,minute), "rho", rho, {k: round(v,4) for k,v in mk.items() if k in ("H","D","A","O25","U35","O35")})
# --- B35: cashout_value vs settle (archived e arrotondamento commissione)
from Betfair.mike import engine as E
L = E.Leg
def leg(role, mk, sel, side, price, size, archived=False, ref=""):
    return L(role=role, market=mk, selection=sel, side=side, price=price, size=size, matched=size, avg_price=price, ref=ref, status="open", archived=archived)
mk = "OU35" if hasattr(E, "SEL_UNDER") else "OU35"
print("SEL", E.SEL_UNDER, E.SEL_OVER)
c = 0.05
# ciclo pre-match chiuso in green, archiviato: utile +10 netto di mercato; ciclo live: back under 100@1.30 aperto
legs = [leg("a","OU35",E.SEL_UNDER,"back",2.00,50,True,"a1"), leg("b","OU35",E.SEL_UNDER,"lay",1.60,62.5,True,"a2"),
        leg("c","OU35",E.SEL_UNDER,"back",1.30,100,False,"c1")]
res = E.settle_legs_by_market(legs, {"OU35": E.SEL_UNDER}, c)
print("B35 settle (Under vince) net:", res.net if hasattr(res,'net') else res)
print("B35 settle per_leg:", getattr(res,'per_leg',None))
books = {("OU35",E.SEL_UNDER): E.Book(best_back=1.25, back_size=500, best_lay=1.26, lay_size=500), ("OU35",E.SEL_OVER): E.Book(best_back=4.8, back_size=500, best_lay=5.0, lay_size=500)}
cv = E.cashout_value(legs, books, c)
print("B35 cashout net/gross:", cv.net, cv.gross, cv.per_selection, "complete", cv.complete)
# solo gambe vive (senza archiviate): stesso valore?
cv2 = E.cashout_value([legs[2]], books, c)
print("B35 cashout solo vive net/gross:", cv2.net, cv2.gross)
# arrotondamento: gross non multiplo del cent
legs3 = [leg("c","OU35",E.SEL_UNDER,"back",1.37,33.33,False,"c1")]
cv3 = E.cashout_value(legs3, books, c)
print("B35 arrotondamento cashout:", cv3.net, " gross", cv3.gross, " netto non arrotondato", cv3.gross*(1-c) if cv3.gross>0 else cv3.gross)
