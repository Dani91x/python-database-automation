"""V2 sonda E-1: effetto del tie-break fisso 0.5 in tennis_winprob (produzione, in sola lettura).
Il tie-break e' modellato punto per punto con P(punto al servizio) derivata dagli hold
(inversione di hold_from_serve_point di produzione). Nessuna scrittura, nessun DB."""
import sys, itertools
sys.path.insert(0, r"C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation")
from Betfair.stream.tennis_scalper.tennis_winprob import p_set as p_set_prod, p_match as p_match_prod
from Betfair.safe_strategy.tennis_opportunity import hold_from_serve_point
from functools import lru_cache

def serve_from_hold(h):
    lo, hi = 0.0, 1.0
    for _ in range(80):
        m = (lo + hi) / 2
        if hold_from_serve_point(m) < h: lo = m
        else: hi = m
    return (lo + hi) / 2

def tb_prob(pa, pb, a_first):
    """P(A vince il tie-break a 7 con scarto 2). pa=P(A vince punto al proprio servizio),
    pb=P(B vince punto al proprio servizio). Servizio: 1 punto a chi apre, poi 2 e 2."""
    def server_is_A(k):
        blocco = (k + 1) // 2
        return (blocco % 2 == 0) if a_first else (blocco % 2 == 1)
    @lru_cache(maxsize=None)
    def f(a, b):
        if a >= 7 and a - b >= 2: return 1.0
        if b >= 7 and b - a >= 2: return 0.0
        if a + b > 80: return 0.5
        k = a + b
        pw = pa if server_is_A(k) else 1.0 - pb   # P(A vince il punto k)
        return pw * f(a + 1, b) + (1 - pw) * f(a, b + 1)
    return f(0, 0)

def p_set2(ga, gb, a_serves, ha, hb, tbA, tbB):
    if ga >= 6 and ga - gb >= 2: return 1.0
    if gb >= 6 and gb - ga >= 2: return 0.0
    if ga == 7: return 1.0
    if gb == 7: return 0.0
    if ga == 6 and gb == 6: return tbA if a_serves else tbB
    if a_serves:
        return ha * p_set2(ga + 1, gb, False, ha, hb, tbA, tbB) + (1 - ha) * p_set2(ga, gb + 1, False, ha, hb, tbA, tbB)
    return hb * p_set2(ga, gb + 1, True, ha, hb, tbA, tbB) + (1 - hb) * p_set2(ga + 1, gb, True, ha, hb, tbA, tbB)

def p_match2(sa, sb, ga, gb, a_serves, ha, hb, bo, tbA, tbB):
    need = bo // 2 + 1
    if sa >= need: return 1.0
    if sb >= need: return 0.0
    ps = p_set2(ga, gb, a_serves, ha, hb, tbA, tbB)
    return ps * p_match2(sa + 1, sb, 0, 0, True, ha, hb, bo, tbA, tbB) + (1 - ps) * p_match2(sa, sb + 1, 0, 0, True, ha, hb, bo, tbA, tbB)

def run(ha, hb):
    pa, pb = serve_from_hold(ha), serve_from_hold(hb)
    tbA, tbB = tb_prob(pa, pb, True), tb_prob(pa, pb, False)
    return pa, pb, tbA, tbB

print("=== CASO RICHIESTO: hold A=0.85, B=0.65, set 6-6 ===")
ha, hb = 0.85, 0.65
pa, pb, tbA, tbB = run(ha, hb)
print(f"P(punto al servizio) A={pa:.4f} B={pb:.4f}  (hold ricontrollato {hold_from_serve_point(pa):.4f}/{hold_from_serve_point(pb):.4f})")
print(f"P(A vince TB) apre A={tbA:.4f}  apre B={tbB:.4f}   (produzione: 0.5000 fisso)")
print("produzione p_set(6,6,True)  =", p_set_prod(6, 6, True, ha, hb), " p_set(6,6,False)=", p_set_prod(6, 6, False, ha, hb))
print(f"P(A vince match) bo3 al 6-6 del 1o set (0-0 set): prod={p_match_prod(0,0,6,6,True,ha,hb,3):.4f} modello={p_match2(0,0,6,6,True,ha,hb,3,tbA,tbB):.4f}")
print(f"P(A vince match) bo3 sa=1,sb=0 al 6-6: prod={p_match_prod(1,0,6,6,True,ha,hb,3):.4f} modello={p_match2(1,0,6,6,True,ha,hb,3,tbA,tbB):.4f}")
print(f"P(A vince match) bo3 da 0-0 (tutto il match): prod={p_match_prod(0,0,0,0,True,ha,hb,3):.4f} modello={p_match2(0,0,0,0,True,ha,hb,3,tbA,tbB):.4f}")
print(f"P(A vince match) bo5 da 0-0: prod={p_match_prod(0,0,0,0,True,ha,hb,5):.4f} modello={p_match2(0,0,0,0,True,ha,hb,5,tbA,tbB):.4f}")

print("\n=== GRIGLIA GATE (P raw >= 0.90 per il BACK del leader), best_of 3 e 5 ===")
pairs = [(0.85, 0.65), (0.80, 0.70), (0.90, 0.60), (0.75, 0.75), (0.70, 0.85), (0.65, 0.85), (0.85, 0.80)]
for bo in (3, 5):
    need = bo // 2 + 1
    for ha, hb in pairs:
        pa, pb, tbA, tbB = run(ha, hb)
        flips = 0; tot = 0; maxd = 0.0; ex = None; flips_unsafe = 0
        for sa in range(need):
            for sb in range(need):
                for ga in range(0, 8):
                    for gb in range(0, 8):
                        if (ga >= 6 and ga - gb >= 2) or (gb >= 6 and gb - ga >= 2) or ga == 7 or gb == 7:
                            if not (ga == 7 or gb == 7): continue
                        if ga == 7 or gb == 7: continue
                        for srv in (True, False):
                            p0 = p_match_prod(sa, sb, ga, gb, srv, ha, hb, bo)
                            p1 = p_match2(sa, sb, ga, gb, srv, ha, hb, bo, tbA, tbB)
                            d = p1 - p0
                            tot += 1
                            for (x, y, who) in ((p0, p1, "A"), (1 - p0, 1 - p1, "B")):
                                if (x >= 0.90) != (y >= 0.90):
                                    flips += 1
                                    if x >= 0.90 and y < 0.90: flips_unsafe += 1
                                    if ex is None or abs(d) > abs(ex[0]): ex = (d, who, (sa, sb, ga, gb, srv), x, y)
                            if abs(d) > abs(maxd): maxd = d
        print(f"bo{bo} hold A={ha} B={hb}: stati={tot} max|dP|={maxd:+.4f} stati con gate0.90 diverso (conta A e B)={flips} di cui NON prudenti (prod>=.90, modello<.90)={flips_unsafe}" + (f" es.{ex}" if ex else ""))
