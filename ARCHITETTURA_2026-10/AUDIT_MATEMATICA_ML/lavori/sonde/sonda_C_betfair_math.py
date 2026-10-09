# -*- coding: ascii -*-
"""Sonda C (audit matematica 09/10/2026): importa le funzioni di PRODUZIONE e le confronta
con calcoli a mano. SOLA LETTURA: nessuna rete, nessun ordine, nessun servizio, nessuna scrittura.
Uso: R/.venv/Scripts/python.exe -I sonda_C_betfair_math.py [sezione]
"""
import sys, math, os
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN

R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R)
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

sez = sys.argv[1] if len(sys.argv) > 1 else "tutte"


def titolo(t):
    print("\n==== " + t + " ====")


def tenta(nome, fn):
    try:
        return fn()
    except Exception as e:  # noqa
        return "ERR %s: %s" % (type(e).__name__, str(e)[:80])


# ---------------------------------------------------------------- 1. TICK
if sez in ("tutte", "tick"):
    titolo("1. TICK: copie a confronto")
    from flumine.utils import get_nearest_price, price_ticks_away
    import Betfair.order_exec as OX
    import Betfair.omega.omega_engine as OE
    import Betfair.stream.live_order_build as LB
    import Betfair.stream.trading.risk_engine as RE
    cand = {
        "order_exec.round_to_tick": OX.round_to_tick,
        "omega.round_to_tick": OE.round_to_tick,
        "live_order_build.round_to_tick": LB.round_to_tick,
        "risk_engine.snap": RE.snap,
        "flumine.get_nearest_price": get_nearest_price,
    }
    prezzi = [1.0, 1.005, 1.01, 1.015, 1.014, 1.995, 2.0, 2.01, 2.03, 2.99, 3.025, 3.975, 4.05, 5.95,
              6.1, 9.9, 9.95, 10.25, 10.3, 19.75, 20.5, 29.5, 31.0, 49.9, 52.5, 99.0, 102.5, 997.5,
              999.99, 1000.0, 1000.4, 1500.0]
    print("%-9s" % "prezzo" + "".join("%-20s" % k[:19] for k in cand))
    div = []
    for p in prezzi:
        riga = []
        for k, f in cand.items():
            riga.append(tenta(k, lambda f=f, p=p: f(p)))
        print("%-9s" % p + "".join("%-20s" % str(r)[:19] for r in riga))
        if len(set(map(str, riga))) > 1:
            div.append((p, riga))
    print("PREZZI CON DIVERGENZA fra copie:", [d[0] for d in div])
    # scansione fine: ogni mezzo-tick e quarti
    import itertools
    n_div = {k: 0 for k in cand}
    ref = get_nearest_price
    esempi = {k: [] for k in cand}
    p = 1.0
    tot = 0
    while p < 1001:
        for k, f in cand.items():
            if k == "flumine.get_nearest_price":
                continue
            a = tenta(k, lambda f=f, p=p: f(p))
            b = ref(p)
            if a != b:
                n_div[k] += 1
                if len(esempi[k]) < 6:
                    esempi[k].append((round(p, 4), a, b))
        tot += 1
        p = round(p + 0.0025, 4)
    print("scansione passo 0.0025: punti=%d" % tot)
    for k in n_div:
        print("  %-34s divergenze da flumine: %d  es: %s" % (k, n_div[k], esempi[k]))
    # tick_up/down omega
    print("omega tick_up/down: 2.001 ->", OE.tick_up(2.001), OE.tick_down(2.001), "| 1000.5 ->", tenta("u", lambda: OE.tick_up(1000.5)))
    print("omega nan ->", tenta("nan", lambda: OE.round_to_tick(float('nan'))))
    print("OX nan ->", tenta("nan", lambda: OX.round_to_tick(float('nan'))))
    print("LB nan ->", tenta("nan", lambda: LB.round_to_tick(float('nan'))))
    print("RE nan ->", tenta("nan", lambda: RE.snap(float('nan'))))
    print("flumine ticks_away off-ladder 2.01 +1:", tenta("a", lambda: price_ticks_away(2.01, 1)))
    print("flumine ticks_away 1000 +1:", price_ticks_away(1000.0, 1), " 1.01 -1:", price_ticks_away(1.01, -1), " 999 +200:", price_ticks_away(990.0, 200))
    # half-up vs half-even sul punto di mezzo: 1.015 (half tra 1.01 e 1.02), 3.025
    for pm in (1.015, 2.01, 3.025, 4.05, 6.1, 10.25, 20.5, 30.0 + 1, 52.5):
        print("  mezzo tick %-7s order_exec=%s omega=%s flumine=%s" % (pm, OX.round_to_tick(pm), OE.round_to_tick(pm), get_nearest_price(pm)))

# ---------------------------------------------------------------- 2. COMMISSIONE per mercato / arrotondamento
if sez in ("tutte", "comm"):
    titolo("2. COMMISSIONE: Mike vs Safe vs Betfair half-up sul centesimo")
    import Betfair.mike.engine as ME
    import Betfair.safe_strategy.execution as SE
    from Betfair.mike.engine import Leg
    # Safe settle_group su un singolo trade back
    def safe_net(g, c=0.05):
        tr = {"side": "back", "size": 1.0, "price": 1.0 + g}  # vince -> +g
        a, cl = SE.settle_group(tr, [], True, c)
        return a
    def betfair_half_up(g, c=0.05):
        gd = Decimal(str(round(g, 2)))
        comm = (gd * Decimal(str(c))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return float(gd - comm)
    def mike_net(g, c=0.05):
        import inspect
        # stessa riga di settle_legs_by_market: comm = round(v*c, 2); net = round(v - comm, 2)
        v = round(g, 2)
        comm = round(max(0.0, v) * c, 2) if v > 0 else 0.0
        return round(v - comm, 2)
    dif_safe = []; dif_mike = []
    for cent in range(1, 3001):
        g = cent / 100.0
        bf = betfair_half_up(g)
        s = safe_net(g); m = mike_net(g)
        if abs(s - bf) > 0.0049: dif_safe.append((g, s, bf))
        if abs(m - bf) > 0.0049: dif_mike.append((g, m, bf))
    print("lordo 0.01..30.00 step 1c, aliquota 5%%: Safe settle_group != half-up: %d casi, es %s" % (len(dif_safe), dif_safe[:6]))
    print("                                        Mike round(v*c,2)  != half-up: %d casi, es %s" % (len(dif_mike), dif_mike[:6]))
    # Mike vero (settle_legs_by_market) su una singola gamba
    def mike_real(g, c=0.05):
        leg = Leg(ref="x", market=ME.MARKET_OU35, selection=ME.SEL_UNDER, side="back", size=1.0, price=1.0 + g, matched=1.0, matched_price=1.0 + g, status="matched", role="entry") if False else None
        return None
    print("(commissione 0): Safe", safe_net(1.0, 0.0), "Mike", mike_net(1.0, 0.0), "| piena 1.0:", safe_net(1.0, 1.0), mike_net(1.0, 1.0))
    # Divergenza Safe vs Mike diretta
    dsm = [(c / 100.0, safe_net(c / 100.0), mike_net(c / 100.0)) for c in range(1, 3001) if abs(safe_net(c / 100.0) - mike_net(c / 100.0)) > 0.0049]
    print("Safe vs Mike divergono su %d lordi di 3000; es %s" % (len(dsm), dsm[:8]))

# ---------------------------------------------------------------- 3. GREEN-UP
if sez in ("tutte", "green"):
    titolo("3. GREEN-UP / HEDGE: S*B/L")
    from Betfair.stream.trading.greenup import compute_greenup
    def esempio(nome, S, B, L, side="back"):
        if side == "back":
            w, l = S * (B - 1), -S
        else:
            w, l = -S * (B - 1), S
        pl = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=L, best_lay_price=L)
        a_mano = S * B / L
        print("%-34s W=%.2f L=%.2f -> %s %s@%s | a mano S*B/L=%.4f | att win/lose %s/%s" % (
            nome, w, l, pl.side, pl.size, pl.price, a_mano, pl.expected_if_win, pl.expected_if_lose))
        return pl
    esempio("back 10@3.00 chiudi lay@2.80", 10, 3.0, 2.8)
    esempio("back 10@3.00 chiudi lay@3.50 (perdita)", 10, 3.0, 3.5)
    esempio("lay 10@3.00 chiudi back@3.20", 10, 3.0, 3.2, "lay")
    esempio("back 2@1.01 chiudi lay@1.01", 2, 1.01, 1.01)
    esempio("back 100@1000 chiudi lay@990", 100, 1000, 990)
    esempio("back 1.00@1.50 chiudi lay@1.49", 1, 1.5, 1.49)
    pl = compute_greenup(matched_if_win=5.0, matched_if_lose=-5.0, best_back_price=None, best_lay_price=1.0)
    print("lay price 1.0 ->", pl.note)
    pl = compute_greenup(matched_if_win=float('nan'), matched_if_lose=1.0, best_back_price=2.0, best_lay_price=2.0)
    print("W=NaN ->", pl.note)
    pl = compute_greenup(matched_if_win=0.004, matched_if_lose=0.0, best_back_price=2.0, best_lay_price=2.0)
    print("diff < FLAT_EPS ->", pl.note)
    # commissione: green-up con commissione 5%: i due esiti netti coincidono?
    pl = esempio("back 10@3.00 lay@2.80 (netto 5%)", 10, 3.0, 2.8)
    lk = min(pl.expected_if_win, pl.expected_if_lose)
    print("  locked lordo %.2f netto 5%% = %.2f (identico su entrambi gli esiti perche' lordo uguale)" % (lk, lk * 0.95))
    # Mike
    import Betfair.mike.engine as ME
    print("Mike locked_pnl_back(10,3.0,2.8)=", ME.locked_pnl_back(10, 3.0, 2.8), " a mano 10*(3/2.8-1)=", 10 * (3 / 2.8 - 1))
    print("Mike cover_size(stake=10 U35, over@4.0, c=.05, f=1.2) =", ME.cover_size(10, 4.0, 0.05, 1.2), " a mano 12/(3*.95)=", 12 / (3 * .95))
    print("Mike cover_residual_lay(10, .05, 1.2, 0)=", ME.cover_residual_lay(10, 0.05, 1.2, 0), " a mano 12/.95 =", 12 / .95)
    print("Mike green_target(3.0, 2 tick)=", ME.green_target(3.0, 2), "  (1.01,1)=", tenta("g", lambda: ME.green_target(1.01, 1)), " (1000,-1)=", tenta("g", lambda: ME.green_target(1000, -1)))
    # omega v3
    import Betfair.omega.omega_v3 as V3
    pos = V3.Posizione(periodo="1t", selection_name="1 - 0", lay_price=20.0, size=2.0)
    for B in (22.0, 20.0, 18.0, 1.0):
        b = V3.profitto_bloccabile(pos, back_price=B, back_size=100, commissione=0.05)
        print("omega profitto_bloccabile lay 2@20 -> back@%s: %s" % (B, None if b is None else (b.profitto, b.back_size)))
    print("  a mano B=22: sb=2*20/22=1.8182 lordo=0.1818 netto*0.95=%.4f" % (0.1818181818 * 0.95))
    print("omega ev_gamba(p=.03, L=20, s=2, c=.05)=", V3.ev_gamba(0.03, 20.0, 2.0, 0.05), " a mano 0.97*2*.95 - .03*2*19 =", 0.97 * 2 * .95 - .03 * 2 * 19)

# ---------------------------------------------------------------- 4. P&L / liability / sizing omega
if sez in ("tutte", "sizing"):
    titolo("4. LAY liability, sizing omega, cap")
    import Betfair.omega.omega_engine as OE
    import Betfair.stream.live_order_build as LB
    print("liability_from_lay(10, 1.01)=", OE.liability_from_lay(10, 1.01), "(1000)=", OE.liability_from_lay(10, 1000))
    print("settle_pnl lay 10@3 perde selezione (won):", OE.settle_pnl(our_selection_id=1, winner_selection_id=2, size=10, price=3, commission=0.05))
    print("settle_pnl lay 10@3 selezione vince (lost):", OE.settle_pnl(our_selection_id=1, winner_selection_id=1, size=10, price=3, commission=0.05))
    print("settle_pnl back 10@3 vince:", OE.settle_pnl(our_selection_id=1, winner_selection_id=1, size=10, price=3, commission=0.05, side="back"))
    print("settle_pnl commissione 1.0 (piena):", OE.settle_pnl(our_selection_id=1, winner_selection_id=2, size=10, price=3, commission=1.0))
    for tgt, c, mn in ((1.0, 0.05, 2.0), (0.10, 0.05, 1.0), (5.0, 0.0, 1.0), (5.0, 1.0, 1.0), (5.0, 0.20, 1.0), (0.0, 0.05, 1.0)):
        print("lay_size_from_target(t=%s,c=%s,min=%s) = %s  (a mano %s)" % (tgt, c, mn, OE.lay_size_from_target(tgt, commission=c, min_stake=mn), None if tgt <= 0 else round(tgt / max(1 - c, 1e-6), 2)))
    for cap, price, size in ((20.0, 1000.0, 5.0), (20.0, 1.01, 5000.0), (20.0, 3.0, 20.0), (20.0, 3.0, 10.01), (20.0, 4.33, 100.0), (0, 3, 9)):
        print("apply_liability_cap size=%s price=%s cap=%s -> %s  liab=%s" % (size, price, cap, OE.apply_liability_cap(size, price, cap), OE.liability_from_lay(OE.apply_liability_cap(size, price, cap), price)))
    # round half even vs half up
    print("round(0.285,2)=%s Decimal HALF_UP=%s ; round(2.675,2)=%s ; round(0.125,2)=%s" % (round(0.285, 2), Decimal("0.285").quantize(Decimal("0.01"), ROUND_HALF_UP), round(2.675, 2), round(0.125, 2)))
    print("lay_size_from_liability(10, 1.01)=", LB.lay_size_from_liability(10, 1.01), " (10,1000)=", LB.lay_size_from_liability(10, 1000))
    print("lay_size_from_liability(10, 1.0)=", tenta("l", lambda: LB.lay_size_from_liability(10, 1.0)))
    titolo("4b. MINIMI .it")
    for side, size in (("back", 0.49), ("back", 0.50), ("back", 0.99), ("back", 1.0), ("back", 1.24), ("back", 1.25), ("back", 1.49), ("back", 7.27), ("lay", 0.5), ("lay", 0.99), ("lay", 1.0), ("lay", 1.234), ("lay", 1.235)):
        v = LB.min_stake_rules("it", side, 3.0, size)
        print("  .it %s %-6s -> valid=%s size=%s residuo=%s %s" % (side, size, v.valid, v.legalized_size, getattr(v, "residuo", None), (v.reason or "")[:50]))
    for side, size, price in (("back", 1.99, 2.0), ("back", 2.0, 2.0), ("lay", 1.0, 20.0)):
        v = LB.min_stake_rules("com", side, price, size)
        print("  .com %s %s@%s -> valid=%s %s" % (side, size, price, v.valid, (v.reason or "")[:60]))

# ---------------------------------------------------------------- 5. Kelly / EV / edge
if sez in ("tutte", "kelly"):
    titolo("5. KELLY / EV / EDGE")
    import Betfair.stream.engine.live_engine_pro as LE
    import Betfair.money_management as MM
    # Kelly back netto: p=.55, odds 2.0, c=.05 (a mano: b=.95 -> f = .55 - .45/.95 = .0763)
    print("_kelly_back(.55,2.0,frac=1,bank=100,c=.05)=", LE._kelly_back(.55, 2.0, 1.0, 100.0, 0.05), " a mano", 100 * (0.55 - 0.45 / 0.95))
    print("_kelly_back(.55,2.0,frac=1,c=0)  =", LE._kelly_back(.55, 2.0, 1.0, 100.0, 0.0), " a mano 10.0")
    print("_kelly_back p=.5 odds 2.0 (EV<0) =", LE._kelly_back(.5, 2.0, 1.0, 100.0, 0.05))
    print("_kelly_back odds=1.01 p=.995     =", LE._kelly_back(.995, 1.01, 1.0, 100.0, 0.05), "  odds=1000 p=.002 =", LE._kelly_back(.002, 1000, 1.0, 100.0, 0.05))
    # Kelly lay: p=.30 lay@3.0 c=.05. f_liab = (1-p) - p(L-1)/(1-c) = .7 - .3*2/.95 = .0684 ; stake = f_liab/(L-1)*bank
    fl = 0.7 - 0.3 * 2 / 0.95
    print("_kelly_lay(.30,3.0,1,100,.05) =", LE._kelly_lay(.30, 3.0, 1.0, 100.0, 0.05), " a mano stake=f_liab/(L-1)*100 =", fl / 2 * 100, " (liability = ", fl * 100, ")")
    print("   -> il valore ritornato e' lo STAKE del lay (backer), non la liability; liability reale =", LE._kelly_lay(.30, 3.0, 1.0, 100.0, 0.05) * 2)
    # SlotManager.calculate_kelly_stake senza costruttore (niente Google Sheets)
    sm = MM.SlotManager.__new__(MM.SlotManager)
    sm.config = {"bankroll": 1000.0, "kelly_fraction": 0.10, "max_stake_pct": 2.0, "commission_pct": 5.0}
    sm.state = {"bankroll": 1000.0}
    for p, o in ((0.60, 2.0), (0.55, 2.0), (0.52, 2.0), (0.505, 2.0), (0.30, 4.0), (0.95, 1.05)):
        print("SlotManager.calculate_kelly_stake(p=%s, odds=%s) = %s" % (p, o, sm.calculate_kelly_stake(p, o)))
    sm.state = {"bankroll": 30.0}
    print("bankroll=30 (cap 2%% = 0.60): stake con p=.6 odds 2.0 =", sm.calculate_kelly_stake(0.6, 2.0), "  <- il minimo forzato a 1.0 supera il cap 2%")
    sm.state = {"bankroll": 1000.0}
    sm.config["commission_pct"] = 0.0
    print("commissione 0: p=.6 odds 2.0 ->", sm.calculate_kelly_stake(0.6, 2.0))
    sm.config["commission_pct"] = 100.0
    print("commissione 100%: p=.6 odds 2.0 ->", sm.calculate_kelly_stake(0.6, 2.0))
    sm.config["commission_pct"] = 5.0
    print("odds 1.0 ->", tenta("k", lambda: sm.calculate_kelly_stake(0.6, 1.0)), " prob=1 ->", tenta("k", lambda: sm.calculate_kelly_stake(1.0, 2.0)))
    # BSS shrink
    print("con brier_score=0.20 (2 classi, random=.5, BSS=.6): stake =", sm.calculate_kelly_stake(0.60, 2.0, brier_score=0.20), " (senza:", sm.calculate_kelly_stake(0.60, 2.0), ")")
    # Edge: money_management (lordo/netto) vs safe
    print("MM edge netto: p=.55 quota 2.0 c=.05:", 0.55 * ((2.0 - 1) * 0.95 + 1) - 1, " safe _ev: ", end="")
    import Betfair.safe_strategy.anomaly as AN
    print(AN._ev("back", 2.0, 0.55, 0.05), " | edge lordo AN._edge:", AN._edge("back", 2.0, 0.55))
    print("lay: _ev(lay,3.0,.30,.05)=", AN._ev("lay", 3.0, .30, .05), " a mano .7*.95-.3*2 =", .7 * .95 - .6)
    import Betfair.safe_strategy.opportunity as OP
    for prm in ({}, {"commission_pct": 7.0}, {"commission": 0.02, "commission_pct": 9}, {"commission_pct": 150}, {"commission_pct": float("nan")}, {"commission_pct": None}):
        print("resolve_commission(%s) = %s" % (prm, OP.resolve_commission(prm)))

# ---------------------------------------------------------------- 6. DEVIG
if sez in ("tutte", "devig"):
    titolo("6. DEVIG")
    import Betfair.omega.omega_model as OM
    import Betfair.safe_strategy.anomaly as AN
    # 1X2 con overround 1.05; favorito netto
    q = (1.50, 4.20, 7.00)
    inv = [1 / x for x in q]; s = sum(inv)
    print("quote", q, "somma 1/q =", round(s, 5))
    print("omega devig_1x2 (moltiplicativo) =", [round(x, 5) for x in OM.devig_1x2(*q)])
    # Shin (iterativo) e potenza: a confronto (non e' codice di produzione, riferimento)
    def shin(inv):
        S = sum(inv)
        lo, hi = 0.0, 0.4
        def f(z):
            return sum((math.sqrt(z * z + 4 * (1 - z) * (p * p) / S) - z) / (2 * (1 - z)) for p in inv) - 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) > 0: lo = mid
            else: hi = mid
        z = (lo + hi) / 2
        return [(math.sqrt(z * z + 4 * (1 - z) * (p * p) / S) - z) / (2 * (1 - z)) for p in inv], z
    ps, z = shin(inv)
    print("Shin (riferimento)               =", [round(x, 5) for x in ps], "z=%.4f" % z)
    # potenza
    lo, hi = 0.5, 1.5
    for _ in range(80):
        k = (lo + hi) / 2
        if sum(p ** k for p in inv) > 1: lo = k
        else: hi = k
    print("potenza (riferimento)            =", [round(p ** k, 5) for p in inv], "k=%.4f" % k)
    print("differenza longshot (7.00): molt=%.5f Shin=%.5f potenza=%.5f" % (inv[2] / s, ps[2], inv[2] ** k))
    print("devig_1x2 con quota 0 ->", OM.devig_1x2(0, 3, 3), " quota None ->", OM.devig_1x2(None, 3, 3), " quota 1.0 ->", OM.devig_1x2(1.0, 3, 3), " nan ->", OM.devig_1x2(float('nan'), 3, 3))
    class R_:  # runner finto con chiavi del vero (name/back_price/lay_price)
        def __init__(s, n, b, l): s.name, s.back_price, s.lay_price = n, b, l
    rs = [{"back": {"price": b}} for b in (1.5, 4.2, 7.0)]
    print("anomaly._devig 3 runner:", sorted(round(v, 5) for v in AN._devig([{"back": [[1.5, 10]]}, {"back": [[4.2, 10]]}, {"back": [[7.0, 10]]}]).values()) if False else "(vedi codice: usa _price(r.get('back')))")
    import Betfair.money_management as MM
    print("money_management OVERROUND_CORRECTION =", MM.OVERROUND_CORRECTION, " -> implied=(1/odds)*0.975: odds 2.0 ->", 0.5 * MM.OVERROUND_CORRECTION, "  vs devig vero dipende dal mercato (1X2 reale ~1.02-1.05)")
    import Betfair.omega.omega_v3 as V3
    rr = [R_("%d - %d" % (h, a), 20.0 + h * 5 + a * 7, 21.0 + h * 5 + a * 7) for h in range(3) for a in range(3)]
    f = V3.p_mercato_devigata(rr)
    print("omega_v3.p_mercato_devigata 9 runner: somma P =", round(sum(f(r.name) for r in rr), 6) if f else None, "(<6 runner -> None):", V3.p_mercato_devigata(rr[:5]))

print("\nFINE SONDA")


# ---------------------------------------------------------------- 7. media_under, copie commissione, tool tick
if sez in ("tutte", "media"):
    titolo("7. media_under_bot (rientro, tick sotto la media)")
    import Betfair.stream.scalper.media_under_bot as MU
    pos = MU.posizione_da_importi([(10.0, 3.0)])      # back 10@3 -> se_vince 20, se_perde -10
    print("pos:", pos.se_vince, pos.se_perde, "quota_media", pos.quota_media)
    print("banca_esatta(c=2.8)=", MU.banca_esatta(pos, 2.8), " a mano (20+10)/2.8=", 30 / 2.8)
    # rientro_esatto: puntare X a q per chiudere a c con profitto lordo T
    q, c, T = 3.2, 2.8, 1.0
    X = MU.rientro_esatto(pos, q, c, T)
    # verifica: dopo X@q la banca a c da lordo T?
    pos2 = MU.posizione_da_importi([(10.0, 3.0), (X, q)])
    L = MU.banca_esatta(pos2, c)
    w, l = MU.profitto_lordo_con_banca(pos2, L, c)
    print("rientro X=%.4f -> dopo banca a %.2f lordo bloccato = %.4f / %.4f (atteso T=%.2f)" % (X, c, w, l, T))
    print("lordo_da_netto(0.95,.05)=", MU.lordo_da_netto(0.95, 0.05), " netto_da_lordo(1,.05)=", MU.netto_da_lordo(1.0, 0.05), " c=1.0 lordo_da_netto:", tenta("x", lambda: MU.lordo_da_netto(1.0, 1.0)))
    print("al_centesimo(0.285)=", MU.al_centesimo(0.285), " (python round ->", round(0.285, 2), ")  al_centesimo(2.675)=", MU.al_centesimo(2.675), " al_centesimo(0.125)=", MU.al_centesimo(0.125))
    for m in (2.2074, 2.20, 2.18, 1.0, 1.01, 1.02, 1000.0, 1.5):
        print("tick_sotto_la_media(%s) = %s | tick_sotto(%s,1) = %s" % (m, MU.tick_sotto_la_media(m), m, MU.tick_sotto(m, 1)))
    print("obiettivo_automatico(10,3.0,2.8)=", MU.obiettivo_automatico(10, 3.0, 2.8))

    titolo("7b. copie della commissione PER MERCATO ripartita sugli ordini")
    import Betfair.stream.reconcile_worker as RW
    from types import SimpleNamespace as NS
    ordini = [NS(bet_id="a", market_id="m", profit=10.00), NS(bet_id="b", market_id="m", profit=-9.00), NS(bet_id="c", market_id="m", profit=0.10)]
    # reconcile: la commissione e' quella di Betfair (listClearedOrders) per mercato
    out = RW.commissioni_per_ordine(ordini, [NS(market_id="m", commission=0.05)])
    print("reconcile.commissioni_per_ordine (comm 0.05 reale su netto 1.10):", out, "somma=", round(sum(v for v in out.values() if v is not None), 2))
    import Betfair.stream.tennis_live.tennis_live_order_worker as TW
    print("tennis paper _commissioni_per_ordine exists:", hasattr(TW, "_commissioni_per_ordine"))

    titolo("7c. copie tick nei tool")
    import Betfair.omega.tools.superficie_liability as SL
    print("superficie tick_di: 1.005->%s 1.01->%s 999->%s 1000->%s 2000->%s 0.5->%s" % tuple(SL.tick_di(x) for x in (1.005, 1.01, 999, 1000, 2000, 0.5)))
    import Betfair.stream.tennis_scalper.tennis_swing_bot as SW
    from flumine.utils import PRICES_FLOAT
    print("swing _LAD uguale a flumine PRICES_FLOAT:", SW._LAD == [float(p) for p in PRICES_FLOAT], len(SW._LAD), len(PRICES_FLOAT))
    import Betfair.stream.scalper.tools.mcm as MC
    print("mcm.frac_tick(2.0)=", MC.frac_tick(2.0), "(1.01)=", MC.frac_tick(1.01), "(1000)=", MC.frac_tick(1000.0), "(3.0)=", MC.frac_tick(3.0))
    import Betfair.stream.scalper.scalper_bot as SB
    print("scalper ticks_between(2.0,2.1)=", SB.ticks_between(2.0, 2.1), " (1.01,1000)=", SB.ticks_between(1.01, 1000.0), " max 200 default ->", SB.ticks_between(1.01, 5.0), " (2.1,2.0)=", SB.ticks_between(2.1, 2.0))
    import Betfair.stream.trading.risk_engine as RE
    print("risk ticks_between(1.01,5.0)=", RE.ticks_between(1.01, 5.0), " (1.01,1000)=", RE.ticks_between(1.01, 1000.0))
    print("risk pct_price(2.0, .02, +1)=", RE.pct_price(2.0, 0.02, 1), " (1.01, .5, -1)=", RE.pct_price(1.01, 0.5, -1))
