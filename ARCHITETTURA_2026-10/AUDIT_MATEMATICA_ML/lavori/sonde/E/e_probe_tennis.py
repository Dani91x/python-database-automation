import sys; sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.tennis_scalper.tennis_winprob import p_set, p_match, estimate_holds
# 1) simmetria: stessi hold, parita' di tutto: p_match(0,0,0,0,True) deve valere 0.5 se ha==hb
print("sim 0-0 ha=hb=.75 serve A / serve B:", round(p_match(0,0,0,0,True,.75,.75),6), round(p_match(0,0,0,0,False,.75,.75),6))
# 2) nuovo set: il codice ricomincia sempre con serve=True (A). Caso: A vince il set 1 (sa=1) -> p con il vero servente alterno?
print("sa=1,sb=0 g0-0 serve A:", round(p_match(1,0,0,0,True,.8,.7),6), "serve B:", round(p_match(1,0,0,0,False,.8,.7),6))
# 3) tie-break fisso 0.5 con ha!=hb: set 6-6
print("set 6-6 ha=.9 hb=.6:", p_set(6,6,True,.9,.6))
# 4) differenza media dal punteggio set 6-5 serve A / B
print("6-5 A serve:", round(p_set(6,5,True,.8,.8),4), "B serve:", round(p_set(6,5,False,.8,.8),4))
# 5) estimate_holds (0,0,0,0) -> prior? e con break
print("estimate_holds(0,0,0,0):", estimate_holds(0,0,0,0), " (1,0,3,2):", estimate_holds(1,0,3,2))
# 6) monotonia vs hold, e P(A) con hold .9 vs .6 su match fresco
print("0-0 ha=.9 hb=.6:", round(p_match(0,0,0,0,True,.9,.6),4))
# 7) un caso dove sa/sb best_of 5 oltre 3 set
print("bo5 2-2:", round(p_match(2,2,0,0,True,.75,.75,5),4))
