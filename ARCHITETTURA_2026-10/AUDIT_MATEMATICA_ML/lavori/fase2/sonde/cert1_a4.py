import sys
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.tennis_scalper.tennis_winprob import p_match
import inspect
print("firma p_match:", inspect.signature(p_match))
for ha,hb in ((0.75,0.75),(0.70,0.85),(0.85,0.70),(0.80,0.80),(0.70,0.70)):
    print("holds A/B", ha, hb, "P leader (1 set, 4-2, serve A) = %.4f"%p_match(1,0,4,2,True,ha,hb,3), " serve B = %.4f"%p_match(1,0,4,2,False,ha,hb,3))
