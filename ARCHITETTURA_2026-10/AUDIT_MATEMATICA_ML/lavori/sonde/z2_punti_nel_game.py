"""z2: effetto dei PUNTI nel game corrente (ignorati da tennis_opportunity._probs). Sola lettura."""
import sys
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
from functools import lru_cache
from Betfair.stream.tennis_scalper.tennis_winprob import p_match
from Betfair.safe_strategy.tennis_opportunity import hold_from_serve_point

def game_from(a, b, p):
    q = 1 - p
    @lru_cache(None)
    def g(a, b):
        if a >= 4 and a - b >= 2: return 1.0
        if b >= 4 and b - a >= 2: return 0.0
        if a >= 3 and b >= 3 and a == b: return p*p/(p*p+q*q)
        if a >= 3 and b >= 3 and a - b == 1: return p + q*g(3, 3)
        if a >= 3 and b >= 3 and b - a == 1: return p*g(3, 3)
        return p*g(a+1, b) + q*g(a, b+1)
    return g(a, b)

# p punto servizio tale che hold=0.75 (bisezione)
lo, hi = .5, .8
for _ in range(60):
    m = (lo+hi)/2
    if hold_from_serve_point(m) < .75: lo = m
    else: hi = m
p = lo; print("p servizio per hold=0.75:", round(p, 4))
h = 0.75
# stato: 1 set a 0, 4-2 nel 2o set, il LEADER (A) serve il game 7: A tiene -> 5-2 (serve B), A perde -> 4-3 (serve B)
pa_hold = p_match(1, 0, 5, 2, False, h, h); pa_break = p_match(1, 0, 4, 3, False, h, h)
print("P match se A tiene:", round(pa_hold, 4), " se A subisce break:", round(pa_break, 4))
for (a, b, lab) in [(0, 0, "0-0"), (1, 0, "15-0"), (0, 1, "0-15"), (0, 2, "0-30"), (0, 3, "0-40"), (3, 3, "40-40"), (3, 0, "40-0")]:
    ph = game_from(a, b, p)
    print(lab, "P(servitore tiene)=", round(ph, 4), " P match A (con punteggio nel game)=", round(ph*pa_hold + (1-ph)*pa_break, 4))
print("modello Safe usa sempre lo stato a inizio game (0-0):", round(p_match(1, 0, 4, 2, True, h, h), 4))
