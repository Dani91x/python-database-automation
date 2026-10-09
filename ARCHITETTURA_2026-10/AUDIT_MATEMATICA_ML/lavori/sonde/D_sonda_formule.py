"""Sonda D: esempi numerici a mano per formule frontend/SQL (sola lettura, nessun import di produzione)."""
# 1) hedgeLayStake (tier0_arb.ts:123) vs stake che pareggia con commissione PER MERCATO (stesso mercato)
O, lo, S, c = 2.2, 2.0, 100.0, 0.05
L_ts = S * ((O - 1) * (1 - c) + 1) / (lo - c)
def net(x): return x * (1 - c) if x > 0 else x
def prof_same_market(L):
    win = net(S * (O - 1) - L * (lo - 1))
    lose = net(L - S)
    return win, lose, min(win, lose)
L_opt = S * O / lo
print("hedge stesso mercato: L_ts=%.3f -> %s ; L_opt=%.3f -> %s" % (L_ts, prof_same_market(L_ts), L_opt, prof_same_market(L_opt)))
def prof_cross_market(L):
    win = net(S * (O - 1)) - L * (lo - 1)
    lose = -S + net(L)
    return win, lose, min(win, lose)
print("hedge mercati diversi: L_ts=%.3f -> %s" % (L_ts, prof_cross_market(L_ts)))
# 2) drawdown: SQL get_personal_report (peak = max equity delle righe, senza punto 0) vs frontend drawdown() (peak parte da 0)
pnl = [-10.0, -20.0]
eq, cum = [], 0
for p in pnl:
    cum += p; eq.append(cum)
peak_sql = [max(eq[:i + 1]) for i in range(len(eq))]
dd_sql = min(e - p for e, p in zip(eq, peak_sql))
peak_fe, mx, cum = 0, 0, 0
for p in pnl:
    cum += p; peak_fe = max(peak_fe, cum); mx = max(mx, peak_fe - cum)
print("drawdown SQL=%.2f frontend=%.2f" % (dd_sql, mx))
# 3) ROI lay: net/stake (backer) vs net/liability
stake, odds = 10.0, 5.0
liab = stake * (odds - 1)
print("lay 10@5: se perde net=%.2f roi_su_stake=%.0f%% roi_su_liability=%.0f%%" % (-liab, -liab / stake * 100, -liab / liab * 100))
print("lay 10@5: se vince net=%.2f roi_su_stake=%.1f%% roi_su_liability=%.2f%%" % (stake * .95, .95 * 100, stake * .95 / liab * 100))
# aggregato: 4 vinte + 1 persa (EV ~ pari): somma net / somma stake vs somma net / somma liability
nets = [stake * .95] * 4 + [-liab]
print("aggregato 4W1L: sum_net=%.2f roi_stake=%.1f%% roi_liab=%.1f%%" % (sum(nets), sum(nets) / (5 * stake) * 100, sum(nets) / (5 * liab) * 100))
# 4) CLV (money_management.py:2508): differenza di implicite RAW vs rapporto di quote vs closing devig
entry, close = 2.10, 2.00
print("CLV punti prob=%.4f ; entry/close-1=%.4f" % (1/close - 1/entry, entry/close - 1))
# margine non si cancella: ingresso con overround 1.04 e close con 1.02 (stesso mercato 2 vie)
pe_fair, pc_fair = 0.50, 0.50
entry_raw = 1/(pe_fair*1.04)  # quota con margine 4%
close_raw = 1/(pc_fair*1.02)
print("stessa prob fair 0.50: clv_raw=%.4f (dovrebbe essere 0) " % (1/close_raw - 1/entry_raw))
# 5) bias calibrazione su implicita RAW sommato a implicita DEVIG (edge_scorer.py:330/calibration.py:152)
raw, fair, real = 0.40, 0.385, 0.40   # mercato calibrato: hit rate reale = implicita raw
print("true_prob = fair + (real - raw_mean) = %.3f vs real %.3f -> sottostima %.3f" % (fair + (real - raw), real, real - (fair + (real - raw))))
# 6) Wald vs Wilson per p=0.9, n=30 e p=1 n=30
import math
def wald(p, n, z=1.96): return z * math.sqrt(p*(1-p)/n)
def wilson(p, n, z=1.96):
    c = (p + z*z/(2*n))/(1+z*z/n); h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1+z*z/n); return c-h, c+h
print("Wald n=30 p=1.0 half=%.3f ; Wilson=%s" % (wald(1.0, 30), wilson(1.0, 30)))
print("Wald n=30 p=0.9 half=%.3f -> (%.3f,%.3f) ; Wilson=%s" % (wald(.9,30), .9-wald(.9,30), .9+wald(.9,30), wilson(.9,30)))
# 7) lockedPnlAt (ladderMath.ts:10): back 10@3 chiuso lay @2
W, L_, p = 20.0, -10.0, 2.0
print("lockedPnlAt = %.2f" % (L_ + (W - L_) / p))
