# CERT_5 - sonda mia: importa le funzioni di PRODUZIONE e rifa' gli esempi numerici di 03. Nessuna rete, nessun DB.
import sys, math, dataclasses
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")


def T(s):
    print("\n=== " + s)


T("E1 green-up (greenup.compute_greenup)")
from Betfair.stream.trading.greenup import compute_greenup as cg
for nome, w, l, lay in (("back 10@3 chiudi lay@2.80", 20.0, -10.0, 2.8), ("back 10@3 chiudi lay@3.50", 20.0, -10.0, 3.5)):
    p = cg(matched_if_win=w, matched_if_lose=l, best_back_price=lay, best_lay_price=lay)
    print(nome, "->", p.side, p.size, p.price, "W/L dopo", p.expected_if_win, p.expected_if_lose, "| a mano S*B/L =", round(10 * 3 / lay, 4))
p = cg(matched_if_win=-20.0, matched_if_lose=10.0, best_back_price=3.2, best_lay_price=3.2)
print("lay 10@3 chiudi back@3.20 ->", p.side, p.size, p.expected_if_win, p.expected_if_lose, "| a mano", 30 / 3.2)

T("E2 Mike locked_pnl_back / cover_size / cover_residual_lay")
import Betfair.mike.engine as ME
print("locked_pnl_back(10,3,2.8) =", ME.locked_pnl_back(10, 3, 2.8), " (doc 0.714286)")
print("cover_size(10,4.0,.05,1.2) =", ME.cover_size(10, 4.0, .05, 1.2), " (doc 4.2105; a mano", 12 / (3 * .95), ")")
print("cover_residual_lay(10,.05,1.2,0) =", ME.cover_residual_lay(10, .05, 1.2, 0), " (doc 12.6316; a mano", 12 / .95, ")")

T("E3 Omega liability / settle_pnl / lay_size_from_target / apply_liability_cap")
import Betfair.omega.omega_engine as OE
print("liability_from_lay(10,1.01)=", OE.liability_from_lay(10, 1.01), " (10,1000)=", OE.liability_from_lay(10, 1000), " (doc 0.10 / 9990.00)")
print("settle_pnl lay 10@3 selezione perde:", OE.settle_pnl(our_selection_id=1, winner_selection_id=2, size=10, price=3, commission=0.05), "(doc +9.50)")
print("settle_pnl lay 10@3 selezione vince:", OE.settle_pnl(our_selection_id=1, winner_selection_id=1, size=10, price=3, commission=0.05), "(doc -20.00)")
print("settle_pnl back 10@3 vince:", OE.settle_pnl(our_selection_id=1, winner_selection_id=1, size=10, price=3, commission=0.05, side="back"), "(doc +19.00)")
print("lay_size_from_target(1.0,c=.05,min=2.0)=", OE.lay_size_from_target(1.0, commission=0.05, min_stake=2.0), " (doc 2.00, a mano 1.05)")
print("lay_size_from_target(0.10,c=.05,min=1.0)=", OE.lay_size_from_target(0.10, commission=0.05, min_stake=1.0), " (doc 1.00)")
for cap, price, size in ((20.0, 1000.0, 5.0), (20.0, 1.01, 5000.0), (20.0, 3.0, 10.01)):
    s = OE.apply_liability_cap(size, price, cap)
    print("apply_liability_cap size=%s price=%s cap=%s -> %s liab=%s" % (size, price, cap, s, OE.liability_from_lay(s, price)), "(doc 0.02/19.98; 1999.99/20.00; 10.00)")

T("E4 Kelly K2 (live_engine_pro) e K1 (money_management.SlotManager)")
import Betfair.stream.engine.live_engine_pro as LE
print("_kelly_back(.55,2.0,1,100,.05)=", LE._kelly_back(.55, 2.0, 1.0, 100.0, 0.05), "(doc 7.6316)")
kl = LE._kelly_lay(.30, 3.0, 1.0, 100.0, 0.05)
print("_kelly_lay(.30,3.0,1,100,.05)=", kl, "liability=", kl * 2, "(doc 3.421 / 6.84)")
print("_kelly_lay(.10,10,...)=", LE._kelly_lay(.10, 10.0, 1.0, 100.0, 0.05), " _kelly_lay(.45,2.5,...)=", LE._kelly_lay(.45, 2.5, 1.0, 100.0, 0.05), "(doc 0, 0)")
import Betfair.money_management as MM
sm = MM.SlotManager.__new__(MM.SlotManager)
sm.config = {"bankroll": 1000.0, "kelly_fraction": 0.10, "max_stake_pct": 2.0, "commission_pct": 5.0}
sm.state = {"bankroll": 1000.0}
print("K1 bank1000 p.55@2.0 k.10 ->", sm.calculate_kelly_stake(0.55, 2.0), "(doc 7.63)")
print("K1 bank1000 p.515@2.0 ->", sm.calculate_kelly_stake(0.515, 2.0), "(doc 1.00 per floor)")
sm.state = {"bankroll": 30.0}
print("K1 bank30 p.6@2.0 ->", sm.calculate_kelly_stake(0.6, 2.0), "(doc 1.00 > tetto 0.60)")

T("E5 EV e quote di pareggio (a mano + value_engine.pricing)")
c = 0.05; p = .55; b = 2.0
print("EV back p.55 q2.0 c.05 =", p * (b - 1) * (1 - c) - (1 - p), "(doc 0.0725)")
import value_engine.pricing as PR
print("pricing.price(p=.5,c=.05):", PR.price("X", 0.5, 0.05))
print("a mano minBack=1+(1-p)/(p(1-c))=", 1 + 0.5 / (0.5 * 0.95), " maxLay=1+(1-p)(1-c)/p=", 1 + 0.5 * 0.95 / 0.5, "(doc 2.0526 / 1.95)")

T("E6 tick: order_exec.round_to_tick vs flumine.get_nearest_price")
import Betfair.order_exec as OX
from flumine.utils import get_nearest_price
print("round_to_tick(nan)=", OX.round_to_tick(float('nan')), " inf=", OX.round_to_tick(float('inf')), " -inf=", OX.round_to_tick(float('-inf')), "(doc 1000.0)")
for x in (1.015, 2.01, 10.25, 52.5):
    print(x, "OX", OX.round_to_tick(x), "flumine", get_nearest_price(x), "(doc 1.01/1.02; 2.0/2.02; 10.0/10.5; 50/55)")
nd = 0
ex = []
for i in range(400000):
    x = round(1.0 + i * 0.0025, 4)
    a = OX.round_to_tick(x)
    try:
        bb = float(get_nearest_price(x))
    except Exception:
        continue
    if abs(a - bb) > 1e-9:
        nd += 1
        if len(ex) < 3:
            ex.append((x, a, bb))
print("divergenze su 400000 prezzi passo 0.0025 (1.0..1001):", nd, "(doc 263)", ex)

T("E7 commissione: arrotondamento Safe settle_group vs Mike settle_legs_by_market (funzioni vere)")
import Betfair.safe_strategy.execution as SE
from decimal import Decimal, ROUND_HALF_UP
tot, _ = SE.settle_group({"side": "back", "size": 1.0, "price": 1.10}, [], True, 0.05)
print("Safe settle_group lordo 0.10 c5% -> netto", tot, "(doc 0.10)")
L = ME.Leg


def mkleg(g):
    return L(role="a", market="M", selection="S", side="back", price=2.0, size=g, matched=g, avg_price=2.0, ref="r", status="open", archived=False)


res = ME.settle_legs_by_market([L(role="a", market="M", selection="S", side="back", price=1.10, size=1.0, matched=1.0, avg_price=1.10, ref="r", status="open", archived=False)], {"M": "S"}, 0.05)
print("Mike settle_legs_by_market lordo 0.10 c5% -> net", getattr(res, "net", res), "(doc 0.09)")
ns = nm = nsm = 0
for cents in range(1, 3001):
    g = cents / 100.0
    s_net, _ = SE.settle_group({"side": "back", "size": g, "price": 2.0}, [], True, 0.05)
    m_net = ME.settle_legs_by_market([mkleg(g)], {"M": "S"}, 0.05).net
    comm = (Decimal(str(g)) * Decimal("0.05")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    h_net = float(Decimal(str(g)) - comm)
    ns += abs(s_net - h_net) > 1e-9
    nm += abs(m_net - h_net) > 1e-9
    nsm += abs(s_net - m_net) > 1e-9
print("lordi 0.01..30.00 (n=3000): Safe != half-up in %d, Mike != half-up in %d, Safe != Mike in %d (doc 75 / 31 / 92-96)" % (ns, nm, nsm))

T("E8 tennis")
from Betfair.stream.tennis_scalper.tennis_winprob import p_match, p_set, estimate_holds
import Betfair.safe_strategy.tennis_opportunity as TO
print("hold_from_serve_point(0.65)=", TO.hold_from_serve_point(0.65), "(doc 0.8296)")
print("estimate_holds(0,0,0,0)=", estimate_holds(0, 0, 0, 0), "(doc 0.7917,0.7917)")
print("p_set(6,6,True,.9,.6)=", p_set(6, 6, True, .9, .6), "(doc 0.5)")
r1 = p_match(1, 0, 4, 2, True, .75, .75, 3)
r2 = p_match(1, 0, 3, 1, True, .75, .75, 3)
print("p_match 1 set + 4-2 hold .75:", r1, " ritiro 2% ->", r1 - 0.02, "(doc raw .9238 adj .9038)")
print("p_match 1 set + 3-1 hold .75:", r2, " ritiro 2% ->", r2 - 0.02, "(doc raw .9039 adj .8839)")
hh = estimate_holds(0, 0, 0, 0)
rb = p_match(1, 0, 4, 2, True, hh[0], hh[1], 3)
print("ripiego estimate_holds(0,0,0,0) 1 set + 4-2:", rb, "adj", rb - 0.02, "(doc 0.9311 vs 0.9038)")

T("E9 dutching (formule lato server) - dutching.py")
import Betfair.stream.trading.dutching as DU


def show(nome, pl):
    print(nome, "| side", pl.side, "total", pl.total_stake, "book%", round(pl.book_pct, 3), "worst/best", pl.worst_profit, pl.best_profit, "|", pl.note)
    for l in pl.legs:
        print("     ", l)


q = [(1, 2.5), (2, 3.0), (3, 4.0)]
show("equal 2.5/3/4 T100", DU.dutch_back(q, 100.0))
show("equal 2.0/3.5/4.2 T100", DU.dutch_back([(1, 2.0), (2, 3.5), (3, 4.2)], 100.0))
show("target 5.00 (2.5/3/4)", DU.dutch_back_for_target(q, 5.0))
show("target 5.00 book 102%", DU.dutch_back_for_target([(1, 2.0), (2, 3.5), (3, 4.2)], 5.0))
show("variable 2.5/3/4 pesi 1/2/1 T100", DU.dutch_variable([(1, 2.5, 1.0), (2, 3.0, 2.0), (3, 4.0, 1.0)], 100.0))
qs = [2.5, 3.0, 4.0]
ws = [1.0, 2.0, 1.0]
w = [(1 / qq) * pp for qq, pp in zip(qs, ws)]
st = [100 * x / sum(w) for x in w]
print("UI variable (formula DutchingPanel.tsx:194-209 trascritta): stake", [round(x, 2) for x in st], "profitti", [round(s * qq - 100, 2) for s, qq in zip(st, qs)], "(doc 30.38/50.63/18.99; -24.05/+51.89/-24.04)")

T("E10 devig (value_engine.devig) + Shin/power (codice MIO, non di produzione)")
import value_engine.devig as DV
d = DV.devig_multiplicative({"H": 1.5, "D": 4.2, "A": 7.0})
print("moltiplicativo:", {k: round(v, 5) for k, v in d.items()}, "sum 1/q =", round(1 / 1.5 + 1 / 4.2 + 1 / 7.0, 4), "(doc .63636/.22727/.13636; 1.0476)")
q3 = [1.5, 4.2, 7.0]
imp = [1 / x for x in q3]
S = sum(imp)
lo, hi = 0.5, 3.0
for _ in range(200):
    k = (lo + hi) / 2
    if sum(i ** (1 / k) for i in imp) > 1:
        lo = k
    else:
        hi = k
print("power (mio, p=i^(1/k)):", [round(i ** (1 / k), 4) for i in imp], "(doc .6519/.2199/.1283)")


def shin(z):
    return [(math.sqrt(z * z + 4 * (1 - z) * i * i / S) - z) / (2 * (1 - z)) for i in imp]


lo, hi = 0.0, 0.4
for _ in range(200):
    z = (lo + hi) / 2
    if sum(shin(z)) > 1:
        lo = z
    else:
        hi = z
print("Shin (mio):", [round(x, 4) for x in shin(z)], "(doc .6471/.2234/.1295)")

T("E11 Wilson vs Wald (market_intelligence.calibration._wilson_ci) e drawdown")
import market_intelligence.calibration as MC
hw0 = MC._wilson_ci(0.9, 30)
print("_wilson_ci(.9,30)=", hw0, "-> intervallo", (round(0.9 - hw0, 3), round(0.9 + hw0, 3)), "(doc Wald 0.793,1.007)")
print("_wilson_ci(1.0,30)=", MC._wilson_ci(1.0, 30), "(doc 0)")
z = 1.96
n = 30
ph = 0.9
den = 1 + z * z / n
cen = (ph + z * z / (2 * n)) / den
hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
print("Wilson vero (mio):", (round(cen - hw, 3), round(cen + hw, 3)), "(doc 0.744,0.965)")
eq = [-10, -30]
sql_peak = -math.inf
sql_dd = 0
for e in eq:
    sql_peak = max(sql_peak, e)
    sql_dd = min(sql_dd, e - sql_peak)
ts_peak = 0
ts_dd = 0
for e in eq:
    ts_peak = max(ts_peak, e)
    ts_dd = max(ts_dd, ts_peak - e)
print("drawdown pnl giornalieri [-10,-20]: SQL", sql_dd, "TS", ts_dd, "(doc 20 vs 30; logica trascritta, SQL non eseguito)")

T("E12 tau DC in-play: live_engine_pro.effective_rho vs value_engine.bivariate.conditional_markets")
from value_engine.bivariate import conditional_markets as CM
for gh, ga, mn in ((1, 1, 60), (1, 0, 60), (0, 0, 30)):
    a = CM(1.5, 1.2, -0.13, mn, gh, ga)
    re_ = LE.effective_rho(-0.13, 1.5, 1.2, gh, ga)
    b = CM(1.5, 1.2, re_, mn, gh, ga)
    print((gh, ga, mn), "sempre-tau D=%.4f H=%.4f O25=%.4f | rho_eff=%.4f D=%.4f H=%.4f O25=%.4f" % (a["D"], a["H"], a["O25"], re_, b["D"], b["H"], b["O25"]), "(doc 1-1 60': D .5132 vs .4920, H .2781 vs .2887, O25 .5829 vs .5934)")
