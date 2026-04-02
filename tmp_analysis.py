import json, sys, statistics
from math import comb
sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

MIN_SIGNALS = 3

def binom_cdf(k, n, p):
    if k < 0: return 0.0
    if k >= n: return 1.0
    return sum(comb(n, i) * (p**i) * ((1-p)**(n-i)) for i in range(k+1))

def find_pvirt(target, W_tot, N, avg_q, p, n_iters=80):
    """Ricerca binaria del P_virt corretto per il target dato."""
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
        out.append({
            'odds': max(s.get('odds', 1.01), 1.01),
            'won': won,
            'pending': pending,
            'market': s.get('market_label',''),
        })
    return out

def sim_puro(valid, PV, bankroll, avg_q, p, W_tot, cap_pct=0.95):
    N = len(valid); bank = bankroll; wins = 0
    for i, s in enumerate(valid):
        rem_after = N - i - 1
        wn = W_tot - wins
        if wn <= 0 or wn > (rem_after+1): continue
        c_lose = PV * binom_cdf(wn-1, rem_after, p)
        c_win  = PV * binom_cdf(wn-2, rem_after, p)
        stake_raw = max(0.01, (c_lose-c_win)/avg_q)
        stake = min(bank*cap_pct, stake_raw)
        stake = max(0.01, round(stake, 2))
        bank += stake*(avg_q-1) if s['won'] else -stake
        if s['won']: wins += 1
    return round(bank - bankroll, 2)

def sim_linear(valid, bankroll, target, avg_q, W_tot, cap_pct=0.95):
    N = len(valid); bank = bankroll; wins = 0; tgt = bankroll+target
    for i, s in enumerate(valid):
        rem = N - i; wn = W_tot - wins
        if wn<=0 or bank<=0.5 or bank>=tgt: continue
        raw = ((tgt-bank)*wn/rem)/(avg_q-1) if avg_q>1 else 0.01
        stake = min(bank*cap_pct, max(0.01, round(raw,2)))
        bank += stake*(avg_q-1) if s['won'] else -stake
        if s['won']: wins += 1
    return round(bank - bankroll, 2)

def sim_sl(valid, bankroll, target, avg_q, W_tot, sl_pct=0.5, max_pct=0.5):
    N = len(valid); bank = bankroll; wins = 0
    tgt = bankroll+target; floor = bankroll*(1-sl_pct)
    for i, s in enumerate(valid):
        rem = N - i; wn = W_tot - wins
        if wn<=0 or bank<=floor or (tgt-bank)<=0.01: continue
        raw = ((tgt-bank)*wn/rem)/(avg_q-1) if avg_q>1 else 0.01
        stake = min(bank*max_pct, max(0.01, round(raw,2)))
        bank += stake*(avg_q-1) if s['won'] else -stake
        if s['won']: wins += 1
    return round(bank - bankroll, 2)

def sim_flat(valid, bankroll, target, avg_q, stake_pct=0.03):
    bank = bankroll; tgt = bankroll+target; sl = bankroll*0.7
    for s in valid:
        if bank >= tgt or bank <= sl: continue
        stake = round(bank*stake_pct, 2)
        bank += stake*(avg_q-1) if s['won'] else -stake
    return round(bank - bankroll, 2)

# Raccogli risultati per tutte le sessioni
results = {k: [] for k in ['puro_corretto','puro_buggy','linear','sl','flat']}
sessions = []

bankroll = 100.0; target = 20.0

for day in sorted(data, key=lambda d: d['date']):
    for (key, side) in [('slots','POI'), ('ml_slots','ML')]:
        sigs = extract(day, key)
        valid = [s for s in sigs if not s['pending']]
        if len(valid) < MIN_SIGNALS: continue

        N = len(valid)
        W_tot = max(1, int(N * 50 / 100))
        avg_q = max(sum(s['odds'] for s in valid) / N, 1.05)
        p = 1.0 / avg_q
        M_init = binom_cdf(W_tot-1, N, p)

        PV_buggy = bankroll / M_init if M_init > 0 else bankroll*100
        PV_corretto = find_pvirt(target, W_tot, N, avg_q, p) if M_init < 1.0 else target

        actual_wins = sum(1 for s in valid if s['won'])
        pnl_pc = sim_puro(valid, PV_corretto, bankroll, avg_q, p, W_tot)
        pnl_pb = sim_puro(valid, PV_buggy, bankroll, avg_q, p, W_tot)
        pnl_li = sim_linear(valid, bankroll, target, avg_q, W_tot)
        pnl_sl = sim_sl(valid, bankroll, target, avg_q, W_tot)
        pnl_fl = sim_flat(valid, bankroll, target, avg_q)

        results['puro_corretto'].append(pnl_pc)
        results['puro_buggy'].append(pnl_pb)
        results['linear'].append(pnl_li)
        results['sl'].append(pnl_sl)
        results['flat'].append(pnl_fl)
        sessions.append({'date': day['date'], 'side': side, 'N': N, 'W': W_tot,
                         'wins': actual_wins, 'avg_q': avg_q,
                         'puro_c': pnl_pc, 'puro_b': pnl_pb,
                         'linear': pnl_li, 'sl': pnl_sl, 'flat': pnl_fl})

print("=== SIMULAZIONE STRATEGIE SUI DATI REALI (bankroll=100, target=20) ===")
print(f"  Sessioni totali (POI+ML con >=3 segnali): {len(sessions)}")
print()
print(f"  {'Strategia':<26} {'P&L Tot':>9} {'P&L/sess':>9} {'Win%sess':>9} {'MaxDD':>8} {'Sharpe':>8} {'Worst':>8}")

def stats(pnls):
    if not pnls: return {}
    total = sum(pnls)
    avg = total/len(pnls)
    wins = sum(1 for x in pnls if x > 0)
    wr = wins/len(pnls)*100
    dd = 0; peak = 0; cum = 0
    for p2 in pnls:
        cum += p2
        if cum > peak: peak = cum
        if peak - cum > dd: dd = peak - cum
    std = statistics.stdev(pnls) if len(pnls) > 1 else 0
    sharpe = avg/std if std > 0 else 0
    worst = min(pnls)
    return {'total': total, 'avg': avg, 'wr': wr, 'dd': dd, 'sharpe': sharpe, 'worst': worst}

labels = {
    'puro_corretto': 'Masaniello Puro (FISSO)',
    'puro_buggy':    'Masaniello Puro (BUGGY)',
    'linear':        'Masaniello Linear',
    'sl':            'Masaniello SL',
    'flat':          'Flat Stake 3%',
}
for k, label in labels.items():
    st = stats(results[k])
    print(f"  {label:<26} {st['total']:>9.2f} {st['avg']:>9.2f} {st['wr']:>9.1f}% {-st['dd']:>8.2f} {st['sharpe']:>8.3f} {st['worst']:>8.2f}")

print()
print("=== ANDAMENTO CUMULATIVO GIORNALIERO — Puro Corretto vs Flat ===")
print(f"  {'Data':<12} {'Side':>5} {'N':>3} {'W/Ott':>5} {'AvgQ':>6} {'PuroC':>7} {'Flat':>7} {'CumPC':>8} {'CumFlat':>8}")
cum_pc = 0; cum_fl = 0
for s in sessions:
    cum_pc += s['puro_c']
    cum_fl += s['flat']
    wins_str = f"{s['wins']}/{s['W']}"
    print(f"  {s['date']:<12} {s['side']:>5} {s['N']:>3} {wins_str:>5} {s['avg_q']:>6.2f} {s['puro_c']:>7.2f} {s['flat']:>7.2f} {cum_pc:>8.2f} {cum_fl:>8.2f}")

print()
print("=== ANALISI PER NUMERO DI SEGNALI (N) — Puro Corretto ===")
n_groups = {}
for s in sessions:
    n = s['N']
    if n not in n_groups: n_groups[n] = []
    n_groups[n].append(s['puro_c'])
print(f"  {'N segnali':>10} {'Sessioni':>9} {'P&L/sess':>9} {'WR%':>7}")
for n in sorted(n_groups):
    pnls = n_groups[n]
    avg = sum(pnls)/len(pnls)
    wr = sum(1 for x in pnls if x > 0)/len(pnls)*100
    print(f"  {n:>10} {len(pnls):>9} {avg:>9.2f} {wr:>7.1f}%")
