"""
Simulazione completa di tutti i fogli MM sui dati reali mm_history.json.
Bankroll=100, Target=20 per tutti.
"""
import json, sys, statistics
from math import comb
sys.stdout.reconfigure(encoding='utf-8')

with open('C:/Users/Admin/Desktop/PYTHON DATABASE/python-database-automation/Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# ───────────────────────────────────────────────
MIN_SIGNALS = 3
BANKROLL    = 100.0
TARGET      = 20.0

def binom_cdf(k, n, p):
    if k < 0: return 0.0
    if k >= n: return 1.0
    return sum(comb(n, i)*(p**i)*((1-p)**(n-i)) for i in range(k+1))

def find_pvirt_norm(W, N, q, p, iters=70):
    def prof(PV):
        bank=0.0; wins=0
        for i in range(N):
            won=i>=(N-W); ra=N-i-1; wn=W-wins
            if wn<=0 or wn>(ra+1): continue
            cl=PV*binom_cdf(wn-1,ra,p); cw=PV*binom_cdf(wn-2,ra,p)
            stk=max(1e-12,(cl-cw)/q)
            bank+=stk*(q-1) if won else -stk
            if won: wins+=1
        return bank
    lo,hi=1e-9,1e9
    for _ in range(iters):
        mid=(lo+hi)/2
        if prof(mid)<1.0: lo=mid
        else: hi=mid
    return (lo+hi)/2

def extract(day, key):
    return [{'odds': max(s.get('odds',1.01),1.01),
             'won': 'VINTO' in str(s.get('result','')),
             'pending': s.get('result')=='PENDING'}
            for s in day.get(key,[]) if s.get('result')!='PENDING']

# ───── Strategie ────────────────────────────────
def sim_puro(sigs, pvirt_norm, bankroll, avg_q, p, W, cap=0.35):
    N=len(sigs); bank=bankroll; wins=0
    PV=pvirt_norm*TARGET
    for i,s in enumerate(sigs):
        ra=N-i-1; wn=W-wins
        if wn<=0 or wn>(ra+1): continue
        cl=PV*binom_cdf(wn-1,ra,p); cw=PV*binom_cdf(wn-2,ra,p)
        stk=max(0.01, min(bank*cap, (cl-cw)/avg_q))
        bank+=stk*(avg_q-1) if s['won'] else -stk
        if s['won']: wins+=1
    return round(bank-bankroll, 2)

def sim_linear(sigs, bankroll, avg_q, W, cap=0.20):
    N=len(sigs); bank=bankroll; wins=0; tgt=bankroll+TARGET
    for i,s in enumerate(sigs):
        rem=N-i; wn=W-wins
        if wn<=0 or bank<=0.5 or bank>=tgt: continue
        raw=((tgt-bank)*wn/rem)/(avg_q-1) if avg_q>1 else 0.01
        stk=min(bank*cap, max(0.01, round(raw,2)))
        bank+=stk*(avg_q-1) if s['won'] else -stk
        if s['won']: wins+=1
    return round(bank-bankroll, 2)

def sim_sl(sigs, bankroll, avg_q, W, sl_pct=0.50, max_cap=0.20):
    N=len(sigs); bank=bankroll; wins=0
    tgt=bankroll+TARGET; floor=bankroll*(1-sl_pct)
    for i,s in enumerate(sigs):
        rem=N-i; wn=W-wins
        if wn<=0 or bank<=floor or (tgt-bank)<=0.01: continue
        raw=((tgt-bank)*wn/rem)/(avg_q-1) if avg_q>1 else 0.01
        floor_cap=max(0.01, bank-floor)
        stk=min(bank*max_cap, floor_cap, max(0.01, round(raw,2)))
        bank+=stk*(avg_q-1) if s['won'] else -stk
        if s['won']: wins+=1
    return round(bank-bankroll, 2)

def sim_flat(sigs, bankroll, avg_q, stake_pct=0.03):
    bank=bankroll; tgt=bankroll+TARGET; sl=bankroll*0.70
    for s in sigs:
        if bank>=tgt or bank<=sl: continue
        stk=round(bank*stake_pct, 2)
        bank+=stk*(avg_q-1) if s['won'] else -stk
    return round(bank-bankroll, 2)

# ───── Raccolta sessioni ─────────────────────────
sessions = []
for day in sorted(data, key=lambda d: d['date']):
    for key, side in [('slots','POI'),('ml_slots','ML')]:
        sigs = extract(day, key)
        if len(sigs) < MIN_SIGNALS: continue
        N   = len(sigs)
        W   = max(1, int(N*50/100))
        q   = max(sum(s['odds'] for s in sigs)/N, 1.05)
        p   = 1.0/q
        pvn = find_pvirt_norm(W, N, q, p)
        actual_wins = sum(1 for s in sigs if s['won'])
        sessions.append({
            'date': day['date'], 'side': side, 'N': N, 'W': W,
            'wins': actual_wins, 'q': q,
            'puro':   sim_puro(sigs, pvn, BANKROLL, q, p, W),
            'linear': sim_linear(sigs, BANKROLL, q, W),
            'sl':     sim_sl(sigs, BANKROLL, q, W),
            'flat':   sim_flat(sigs, BANKROLL, q),
        })

STRATS = ['puro','linear','sl','flat']
LABELS = {
    'puro':   'Masaniello Puro (CORRETTO)',
    'linear': 'Masaniello Lineare',
    'sl':     'Masaniello + SL (CORRETTO)',
    'flat':   'Flat Stake 3%',
}

def report(sess_list, title):
    if not sess_list: return
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"  Sessioni: {len(sess_list)} | Periodo: {sess_list[0]['date']} → {sess_list[-1]['date']}")
    print(f"{'='*72}")

    # Tabella giornaliera
    print(f"\n  {'Data':<12} {'N':>3} {'W_ok':>5} {'WR%':>6} {'AvgQ':>6} | {'Puro':>7} {'Linear':>8} {'SL':>7} {'Flat':>7}")
    print(f"  {'-'*12} {'-'*3} {'-'*5} {'-'*6} {'-'*6} | {'-'*7} {'-'*8} {'-'*7} {'-'*7}")
    cum = {k:0.0 for k in STRATS}
    for s in sess_list:
        wr = s['wins']/s['N']*100
        wins_str = f"{s['wins']}/{s['W']}"
        print(f"  {s['date']:<12} {s['N']:>3} {wins_str:>5} {wr:>6.1f}% {s['q']:>6.2f} | "
              f"{s['puro']:>7.2f} {s['linear']:>8.2f} {s['sl']:>7.2f} {s['flat']:>7.2f}")
        for k in STRATS: cum[k] += s[k]

    # Totali cumulativi
    print(f"  {'─'*70}")
    print(f"  {'TOTALE P&L':>35}      | {cum['puro']:>7.2f} {cum['linear']:>8.2f} {cum['sl']:>7.2f} {cum['flat']:>7.2f}")

    # Statistiche per strategia
    print(f"\n  {'Strategia':<30} {'P&L':>8} {'Media':>7} {'Win%':>7} {'MaxDD':>8} {'Worst':>8} {'Sharpe':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*8}")
    for k in STRATS:
        pnls = [s[k] for s in sess_list]
        total = sum(pnls); avg = total/len(pnls)
        wr = sum(1 for x in pnls if x>0)/len(pnls)*100
        worst = min(pnls)
        dd=0; peak=0; cum2=0
        for v in pnls:
            cum2+=v
            if cum2>peak: peak=cum2
            if peak-cum2>dd: dd=peak-cum2
        std = statistics.stdev(pnls) if len(pnls)>1 else 0
        sharpe = avg/std if std>0 else 0
        print(f"  {LABELS[k]:<30} {total:>8.2f} {avg:>7.2f} {wr:>7.1f}% {-dd:>8.2f} {worst:>8.2f} {sharpe:>8.3f}")

# ───── Report per side ───────────────────────────
poi_sess = [s for s in sessions if s['side']=='POI']
ml_sess  = [s for s in sessions if s['side']=='ML']

report(poi_sess,  "LATO POISSON — simulazione su dati reali")
report(ml_sess,   "LATO ML — simulazione su dati reali")
report(sessions,  "TOTALE (Poisson + ML combinati)")

# ───── Analisi per numero di segnali ────────────
print(f"\n{'='*72}")
print("  PROFITTO MEDIO PER NUMERO DI SEGNALI N (Masaniello Puro Corretto)")
print(f"{'='*72}")
print(f"  {'N segnali':>10} {'Sessioni':>9} {'P&L medio':>10} {'WR sess%':>10} {'Note'}")
from collections import defaultdict
n_groups = defaultdict(list)
for s in sessions:
    n_groups[s['N']].append(s['puro'])
for n in sorted(n_groups):
    pnls = n_groups[n]
    avg  = sum(pnls)/len(pnls)
    wr   = sum(1 for x in pnls if x>0)/len(pnls)*100
    note = '⚠ N piccolo, garanzia a rischio' if n<10 else ''
    print(f"  {n:>10} {len(pnls):>9} {avg:>10.2f} {wr:>10.1f}%  {note}")

# ───── Migliori mercati per strategia Puro ──────
print(f"\n{'='*72}")
print("  MERCATI MIGLIORI (Poisson) — ROI reale sui raw bet")
print(f"{'='*72}")
mkt = {}
for day in data:
    for s in day.get('slots',[]):
        if s.get('result')=='PENDING': continue
        m = s.get('market_label','')
        won = 'VINTO' in str(s.get('result',''))
        if m not in mkt: mkt[m]={'n':0,'w':0,'pnl':0,'stk':0,'odds':0}
        mkt[m]['n']+=1; mkt[m]['w']+=won; mkt[m]['pnl']+=s.get('pnl',0)
        mkt[m]['stk']+=s.get('stake',0); mkt[m]['odds']+=s.get('odds',0)
print(f"  {'Mercato':<22} {'N':>4} {'WR%':>6} {'AvgQ':>6} {'ROI%':>7} {'P&L':>8}")
for m,st in sorted(mkt.items(), key=lambda x: x[1]['pnl'], reverse=True):
    if st['n']<5: continue
    wr=st['w']/st['n']*100; roi=st['pnl']/st['stk']*100 if st['stk'] else 0
    avgq=st['odds']/st['n']
    flag = ' ✅' if roi>0 else ' ❌'
    print(f"  {m:<22} {st['n']:>4} {wr:>6.1f}% {avgq:>6.2f} {roi:>7.2f}%{st['pnl']:>8.2f}{flag}")
