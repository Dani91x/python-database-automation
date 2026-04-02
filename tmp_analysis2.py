"""Analisi approfondita: perché Linear segna +578? Verifica coerenza simulazione."""
import json, sys, statistics
from math import comb
sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

def binom_cdf(k, n, p):
    if k < 0: return 0.0
    if k >= n: return 1.0
    return sum(comb(n, i) * (p**i) * ((1-p)**(n-i)) for i in range(k+1))

def find_pvirt(target, W_tot, N, avg_q, p, n_iters=80):
    def simulate_profit(PV):
        bank = 0.0; wins = 0
        pat = [False]*(N-W_tot) + [True]*W_tot
        for i, won in enumerate(pat):
            rem_after = N - i - 1
            wn = W_tot - wins
            if wn <= 0 or wn > (rem_after+1): continue
            c_lose = PV * binom_cdf(wn-1, rem_after, p)
            c_win  = PV * binom_cdf(wn-2, rem_after, p)
            stake  = max(1e-9, (c_lose-c_win)/avg_q)
            bank += stake*(avg_q-1) if won else -stake
            if won: wins += 1
        return bank
    lo, hi = 1e-6, 1e8
    for _ in range(n_iters):
        mid = (lo+hi)/2
        if simulate_profit(mid) < target: lo = mid
        else: hi = mid
    return (lo+hi)/2

def extract(day, key):
    out = []
    for s in day.get(key, []):
        won = 'VINTO' in str(s.get('result', ''))
        pending = s.get('result') == 'PENDING'
        out.append({'odds': max(s.get('odds', 1.01), 1.01), 'won': won, 'pending': pending})
    return out

bankroll = 100.0; target = 20.0; MIN_SIGNALS = 3

# Analisi dettagliata sessione per sessione con stake medio/massimo
print("=== ANALISI DETTAGLIATA STAKES PER STRATEGIA ===")
print(f"  {'Data':<12} {'Side':>5} {'N':>4} {'W':>3} {'Wins':>4} {'WR%':>6} {'Avg_q':>6} | {'PuroC_s1':>9} {'PuroB_s1':>9} {'Lin_s1':>9} | {'PuroC_pnl':>10} {'Lin_pnl':>10} {'Flat_pnl':>10}")

total_pc = 0; total_pb = 0; total_lin = 0; total_fl = 0

for day in sorted(data, key=lambda d: d['date']):
    for (key, side) in [('slots','POI'), ('ml_slots','ML')]:
        sigs = extract(day, key)
        valid = [s for s in sigs if not s['pending']]
        if len(valid) < MIN_SIGNALS: continue

        N = len(valid)
        W_tot = max(1, int(N * 50 / 100))
        avg_q = max(sum(s['odds'] for s in valid) / N, 1.05)
        p = 1.0 / avg_q
        actual_wins = sum(1 for s in valid if s['won'])
        actual_wr = actual_wins / N * 100

        M_init = binom_cdf(W_tot-1, N, p)
        PV_buggy = bankroll / M_init if M_init > 0 else bankroll*100
        PV_corretto = find_pvirt(target, W_tot, N, avg_q, p) if M_init < 1.0 else target

        # Stake bet 1 per ogni strategia
        rem_after = N - 1
        wn = W_tot
        c_lose_c = PV_corretto * binom_cdf(wn-1, rem_after, p)
        c_win_c  = PV_corretto * binom_cdf(wn-2, rem_after, p)
        s1_pc = min(bankroll*0.95, max(0.01, (c_lose_c - c_win_c)/avg_q))

        c_lose_b = PV_buggy * binom_cdf(wn-1, rem_after, p)
        c_win_b  = PV_buggy * binom_cdf(wn-2, rem_after, p)
        s1_pb = min(bankroll*0.95, max(0.01, (c_lose_b - c_win_b)/avg_q))

        tgt_val = bankroll + target
        raw_lin = ((tgt_val - bankroll) * wn/N) / (avg_q-1) if avg_q>1 else 0.01
        s1_lin = min(bankroll*0.95, max(0.01, raw_lin))

        # Simulazioni P&L
        def sim_puro(PV, cap=0.95):
            bank = bankroll; wins = 0
            for i, s in enumerate(valid):
                ra = N-i-1; wn2 = W_tot-wins
                if wn2<=0 or wn2>(ra+1): continue
                cl = PV*binom_cdf(wn2-1,ra,p); cw = PV*binom_cdf(wn2-2,ra,p)
                stk = min(bank*cap, max(0.01, (cl-cw)/avg_q))
                bank += stk*(avg_q-1) if s['won'] else -stk
                if s['won']: wins += 1
            return round(bank-bankroll, 2)

        def sim_lin(cap=0.95):
            bank = bankroll; wins = 0; tgt = bankroll+target
            for i, s in enumerate(valid):
                rem = N-i; wn2 = W_tot-wins
                if wn2<=0 or bank<=0.5 or bank>=tgt: continue
                raw = ((tgt-bank)*wn2/rem)/(avg_q-1) if avg_q>1 else 0.01
                stk = min(bank*cap, max(0.01, round(raw,2)))
                bank += stk*(avg_q-1) if s['won'] else -stk
                if s['won']: wins += 1
            return round(bank-bankroll, 2)

        def sim_flat(pct=0.03):
            bank = bankroll; tgt = bankroll+target; sl = bankroll*0.7
            for s in valid:
                if bank>=tgt or bank<=sl: continue
                stk = round(bank*pct, 2)
                bank += stk*(avg_q-1) if s['won'] else -stk
            return round(bank-bankroll, 2)

        pnl_pc = sim_puro(PV_corretto)
        pnl_pb = sim_puro(PV_buggy)
        pnl_li = sim_lin()
        pnl_fl = sim_flat()
        total_pc += pnl_pc; total_pb += pnl_pb; total_lin += pnl_li; total_fl += pnl_fl

        print(f"  {day['date']:<12} {side:>5} {N:>4} {W_tot:>3} {actual_wins:>4} {actual_wr:>6.1f}% {avg_q:>6.2f} | {s1_pc:>9.2f} {s1_pb:>9.2f} {s1_lin:>9.2f} | {pnl_pc:>10.2f} {pnl_li:>10.2f} {pnl_fl:>10.2f}")

print()
print(f"  TOTALI: PuroC={total_pc:.2f}  PuroB={total_pb:.2f}  Linear={total_lin:.2f}  Flat={total_fl:.2f}")

# Verifica: perché Linear è cosi positivo?
print()
print("=== ANALISI WIN RATE EFFETTIVO PER SIDE ===")
for key, side in [('slots','POI'), ('ml_slots','ML')]:
    total_bets = 0; total_wins = 0; total_pnl = 0; total_stk = 0
    for day in data:
        for s in day.get(key, []):
            if s.get('result') == 'PENDING': continue
            total_bets += 1
            total_pnl += s.get('pnl', 0)
            total_stk += s.get('stake', 0)
            if 'VINTO' in str(s.get('result','')): total_wins += 1
    wr = total_wins/total_bets*100 if total_bets else 0
    roi = total_pnl/total_stk*100 if total_stk else 0
    print(f"  {side}: {total_bets} bet | WR={wr:.1f}% | ROI={roi:.2f}% | PnL_raw={total_pnl:.2f}")
