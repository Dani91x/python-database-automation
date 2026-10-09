"""E2 sonda 1: Kelly live_engine_pro + tau DC in-play (live_engine_pro vs bivariate.conditional_markets). Sola lettura, senza rete."""
import sys, os, math
R = r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation"
sys.path.insert(0, R); sys.path.insert(0, os.path.join(R, "Betfair")); sys.path.insert(0, os.path.join(R, "Betfair", "stream"))
from Betfair.stream.engine import live_engine_pro as L
from value_engine import bivariate as bv
# Kelly back / lay
print("kelly_back p=.55 odds=2 c=.05 k=1 bank=100:", L._kelly_back(.55, 2.0, 1.0, 100, .05), "a mano f=(.55-.45/.95)=%.5f" % (.55 - .45 / .95))
# verifica Kelly lay per massimizzazione numerica del log-growth (stake s del backer, liability s*(L-1))
def growth_lay(p, Lo, c, s, bank=100.0):
    return (1 - p) * math.log(1 + s * (1 - c) / bank) + p * math.log(1 - s * (Lo - 1) / bank)
def growth_back(p, o, c, s, bank=100.0):
    return p * math.log(1 + s * (o - 1) * (1 - c) / bank) + (1 - p) * math.log(1 - s / bank)
for (p, Lo) in ((.30, 3.0), (.10, 10.0), (.45, 2.5)):
    k = L._kelly_lay(p, Lo, 1.0, 100, .05)
    best = max((growth_lay(p, Lo, .05, s / 100.0), s / 100.0) for s in range(0, int(100 / (Lo - 1)) * 100 - 1))
    print("lay p=%.2f L=%.1f kelly stake=%.3f ; max numerico stake=%.3f (liab=%.2f)" % (p, Lo, k, best[1], k * (Lo - 1)))
for (p, o) in ((.55, 2.0), (.30, 5.0)):
    k = L._kelly_back(p, o, 1.0, 100, .05)
    best = max((growth_back(p, o, .05, s / 100.0), s / 100.0) for s in range(0, 9999))
    print("back p=%.2f o=%.1f kelly=%.3f ; max numerico=%.3f" % (p, o, k, best[1]))
# tau in-play: 1-1 al 60', lambda pre 1.5/1.2, rho -0.13 ; confronto
lam_h, lam_a, rho = 1.5, 1.2, -0.13
for (gh, ga, minute) in ((0, 0, 30), (1, 0, 60), (1, 1, 60), (0, 1, 70), (2, 1, 75)):
    frac = (90 - minute) / 90
    # variante produzione live_engine_pro: effective_rho -> 0 se non 0-0
    rho_eff = L.effective_rho(rho, lam_h * frac, lam_a * frac, gh, ga)
    g_lep = L.score_matrix(lam_h * frac, lam_a * frac, rho_eff)
    lines = [0.5, 1.5, 2.5, 3.5]
    a = L._markets_from_residual(g_lep, gh, ga, lines)
    b = bv.conditional_markets(lam_h, lam_a, rho, minute, gh, ga)
    print("score %d-%d min %d rho_eff=%.2f | H %.4f/%.4f D %.4f/%.4f A %.4f/%.4f O2.5 %.4f/%.4f BTTS %.4f/%.4f  (lep / cond_markets)" % (
        gh, ga, minute, rho_eff, a["home"], b["H"], a["draw"], b["D"], a["away"], b["A"], a["over_2_5"], b["O25"], a["btts_yes"], b["BTTS"]))
