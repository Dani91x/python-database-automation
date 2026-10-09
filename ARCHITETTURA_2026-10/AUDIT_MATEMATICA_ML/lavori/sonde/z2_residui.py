"""z2_residui.py - sonda in SOLA LETTURA (audit 09/10/2026). Nessuna rete/scrittura."""
import sys
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)

from Betfair.safe_strategy.tennis_opportunity import (
    TennisOpportunityModel, hold_from_serve_point, devig_pair)
from Betfair.stream.tennis_scalper.tennis_winprob import p_set, p_match, estimate_holds
from Betfair.stream.trading import daily_pnl as D
from Betfair.stream.trading.risk_engine import mark_to_market
from Betfair.stream.trading.submin import rendimento_in_banda
from Betfair.stream.scalper.theta_bot import theta_pair
from Betfair.stream.trading.esposizione_fuori_bot import netto_size, esposizione_abbinata


def h(t):
    print("\n=== " + t)


h("1. hold_from_serve_point vs DP esatto sui punti")
def hold_dp(p):
    q = 1 - p
    from functools import lru_cache
    @lru_cache(None)
    def g(a, b):  # punti servitore a, ricevitore b
        if a >= 4 and a - b >= 2: return 1.0
        if b >= 4 and b - a >= 2: return 0.0
        if a >= 3 and b >= 3:  # deuce/vantaggio: equivalente a stato (3,3) con differenza
            d = a - b
            if d == 0:
                return p * p / (p * p + q * q)
        return p * g(a + 1, b) + q * g(a, b + 1)
    return g(0, 0)
for p in (0.5, 0.55, 0.6, 0.65, 0.7):
    print(p, round(hold_from_serve_point(p), 6), round(hold_dp(p), 6))

h("2. estimate_holds")
print("zero dati:", estimate_holds(0, 0, 0, 0))
print("tennis_runner con serviceBreaks=0 (sidecar vero) al crescere dei game:")
for gh, ga in [(1, 0), (2, 1), (3, 3), (4, 4), (6, 6), (7, 5)]:
    print((gh, ga), estimate_holds(0, 0, gh, ga))
print("break (1,0) a 3-3:", estimate_holds(1, 0, 3, 3))

h("3. P(vittoria) p1 (servizio ignoto) modello Safe, prior 0.75 sim. - e variazioni")
def pw(sets, games, params=None, comp="ATP Challenger"):
    m = TennisOpportunityModel(params)
    pl = {"sets": {"p1": sets[0], "p2": sets[1]}, "games": {"p1": games[0], "p2": games[1]},
          "competition": comp}
    return m.p_win(pl, "p1"), m._probs(pl, m._state(pl))["p1"]["raw"]
for s, g in [((1, 0), (3, 1)), ((1, 0), (4, 2)), ((1, 0), (5, 2)), ((1, 0), (5, 3)), ((0, 0), (5, 1)), ((1, 0), (2, 0))]:
    print(s, g, "adj/raw prior .75:", [round(x, 4) for x in pw(s, g)])
print("hold prior .85 (ATP-like):", [round(x, 4) for x in pw((1, 0), (3, 1), {"hold_prior": 0.85})])
print("hold prior .65 (WTA-like):", [round(x, 4) for x in pw((1, 0), (3, 1), {"hold_prior": 0.65})])
print("p_set(0,0,True,.75,.75)=", round(p_set(0, 0, True, .75, .75), 5), " serve B:", round(p_set(0, 0, False, .75, .75), 5))

h("4. Giocatori asimmetrici: stesso punteggio 1-0 set + 3-1, p1 = underdog che conduce")
for ha, hb in [(0.75, 0.75), (0.70, 0.85), (0.85, 0.70), (0.65, 0.65), (0.85, 0.85)]:
    pm = 0.5 * (p_match(1, 0, 3, 1, True, ha, hb) + p_match(1, 0, 3, 1, False, ha, hb))
    print((ha, hb), round(pm, 4))

h("5. Gate: cosa serve per P>=0.90 e EV")
for p in (0.90, 0.93):
    for q in (1.05, 1.08, 1.10):
        ev = p * (q - 1) * 0.95 - (1 - p)
        print("p", p, "back", q, "edge", round(p - 1 / q, 4), "EV/1EUR netto", round(ev, 4))
print("devig 1.10/8.0:", devig_pair(1.10, 8.0), " somma implicite:", round(1/1.10 + 1/8.0, 4))

h("6. daily_pnl")
print("back 10@3 (W=+20,L=-10), best_lay 3.0:", mark_to_market(20, -10, 3.2, 3.0))
print("  lay 3.2:", mark_to_market(20, -10, 3.2, 3.2), " lay 2.5:", mark_to_market(20, -10, 3.2, 2.5))
print("  prezzi mancanti worst-case:", D.open_mtm([D.OpenPosition(20, -10, None, None, 20, -10)]))
print("  prezzo lay=1.01 (book sottile):", mark_to_market(20, -10, 3.2, 1.01))
print("  FLAT:", mark_to_market(0.004, -0.004, None, None))
r = D.evaluate_daily_stop(-49.995, 0.0, 50.0); print("limite -50, tot -49.995:", r.fire, r.reason)
r = D.evaluate_daily_stop(-49.99999999, 0.0, 50.0); print("tot -49.99999999:", r.fire)
r = D.evaluate_daily_stop(-49.9999999, 0.0, 50.0); print("tot -49.9999999 (1e-7 sopra):", r.fire)
try: D.realized_pnl([{"profit": float('nan')}])
except ValueError as e: print("NaN ->", e)
# commissione: giornata 5%
gross = 200.0; comm = 10.0
print("realized lordo +200 (comm 10): lo stop vede", gross, "il netto reale", gross - comm,
      "-> scatta a lordo -50 = netto -60 se tutti i profitti sono su mercati commissionati")

h("7. theta_pair: locked>0 lordo ma dopo size a 2 decimali?")
import itertools
bad = []; tot = 0
from Betfair.stream.trading.risk_engine import PRICES_FLOAT  # noqa
prices = [p for p in PRICES_FLOAT if 1.5 <= p <= 6.0]
for stake in (2.0, 2.5, 3.0, 5.0, 10.0, 20.0):
    for pe in prices[::3]:
        t = theta_pair(stake, pe, 1)
        if not t: continue
        tot += 1
        s, x, px = stake, t["exit_size"], t["exit_price"]
        win = s * (pe - 1) - x * (px - 1)   # back vince, lay perde
        lose = -s + x
        comm = lambda v: v * 0.95 if v > 0 else v
        netto = min(comm(win), comm(lose))
        if min(win, lose) <= 0 or netto <= 0:
            bad.append((stake, pe, px, x, round(win, 4), round(lose, 4), t["locked"]))
print("coppie costruibili:", tot, " con min(win,lose)<=0 dopo arrotondamento:", len(bad))
print(bad[:6])
t = theta_pair(10, 2.0, 1); print("esempio 10@2.00 ->1.99:", t)
t = theta_pair(10, 1.50, 1); print("esempio 10@1.50 ->1.49:", t)

h("8. esposizione_fuori_bot: netto in size vs esposizione vera")
ordini = [{"sizeMatched": 10, "averagePriceMatched": 2.0, "side": "BACK", "betId": 1},
          {"sizeMatched": 10, "averagePriceMatched": 5.0, "side": "LAY", "betId": 2}]
print("netto_size:", netto_size(ordini), " esposizione (if_win, if_lose):", esposizione_abbinata(ordini))

h("9. liability: round float vs Decimal (HALF_UP / HALF_EVEN) sui prezzi di scala")
diff_up = diff_even = n = 0; ex = []
for cents in range(1, 501):
    size = cents / 100
    for p in PRICES_FLOAT:
        if p > 30: break
        n += 1
        a = round(size * (p - 1.0), 2)
        e = Decimal(str(size)) * (Decimal(str(p)) - 1)
        up = float(e.quantize(Decimal("0.01"), ROUND_HALF_UP)); ev = float(e.quantize(Decimal("0.01"), ROUND_HALF_EVEN))
        if abs(a - up) > 1e-9: diff_up += 1; ex.append((size, p, a, up, ev))
        if abs(a - ev) > 1e-9: diff_even += 1
print("casi", n, "float!=HALF_UP", diff_up, "float!=HALF_EVEN", diff_even, ex[:5])
print("rendimento_in_banda(0.70,1.02)", rendimento_in_banda(0.70, 1.02), " (0.80,1.01)", rendimento_in_banda(0.80, 1.01),
      " (2.0,1.01)", rendimento_in_banda(2.0, 1.01))

h("10. valuta: arrotondamento size GBP->EUR")
r = round(1 / 0.8586, 6)
for g in (0.003, 0.004, 0.005, 0.01, 1.00, 2.00, 17.43):
    print(g, "GBP ->", round(g * r, 2), "EUR (esatto", round(g * r, 5), ")")
mx = max(abs(round(g / 100 * r, 2) - g / 100 * r) for g in range(1, 100000))
print("errore massimo per livello (EUR):", round(mx, 5))
