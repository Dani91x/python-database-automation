import json
import random
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

with open('Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    history = json.load(f)

ht05 = []
for day in history:
    for s in day.get('slots', []):
        if s.get('market') == 'HT05':
            ht05.append({'track': 'Poisson', **s})
    for s in day.get('ml_slots', []):
        if s.get('market') == 'HT05':
            ht05.append({'track': 'ML', **s})

played = [s for s in ht05 if s.get('result') != 'PENDING']

COMMISSION   = 0.95
STARTING_DEBT = 310.0
N_SIMS        = 10_000
K_FACTOR      = 5          # cap = base_stake * K
MAX_SIGNALS   = 300        # finestra simulazione

random.seed(42)

def run_sim(signals, k, debt_start, n_signals):
    debt       = debt_start
    pnl_curve  = [0.0]
    max_exp    = 0.0
    recovered_at = None

    for i in range(n_signals):
        s = random.choice(signals)
        odds       = s['odds']
        base_stake = s.get('stake', 20.0)
        is_win     = random.random() < (sum(1 for x in played if 'VINTO' in str(x.get('result',''))) / len(played))

        if debt <= 0.0001:
            stake = base_stake
        else:
            full_stake = debt / ((odds - 1) * COMMISSION)
            stake      = min(full_stake, base_stake * k)

        max_exp = max(max_exp, stake)

        if is_win:
            bet_pnl = stake * (odds - 1) * COMMISSION
            debt    = max(0.0, debt - bet_pnl)
        else:
            bet_pnl = -stake
            debt   += stake

        pnl_curve.append(pnl_curve[-1] + bet_pnl)

        if recovered_at is None and debt <= 0.0001:
            recovered_at = i + 1

    return pnl_curve, max_exp, recovered_at, debt

# ---------- Monte Carlo ----------
recovered_at_list = []
max_exp_list      = []
final_debt_list   = []
final_pnl_list    = []
all_curves        = []

for _ in range(N_SIMS):
    curve, mx, rec_at, final_debt = run_sim(played, K_FACTOR, STARTING_DEBT, MAX_SIGNALS)
    recovered_at_list.append(rec_at if rec_at is not None else MAX_SIGNALS + 1)
    max_exp_list.append(mx)
    final_debt_list.append(final_debt)
    final_pnl_list.append(curve[-1])
    if len(all_curves) < 200:
        all_curves.append(curve)

recovered    = [x for x in recovered_at_list if x <= MAX_SIGNALS]
not_recovered = [x for x in recovered_at_list if x > MAX_SIGNALS]
pct_recovered = len(recovered) / N_SIMS * 100

print(f"=== SIMULAZIONE RECOVERY K=5 (cap €100) ===")
print(f"Debito iniziale    : EUR {STARTING_DEBT:.0f}")
print(f"Simulazioni        : {N_SIMS:,}")
print(f"Finestra segnali   : {MAX_SIGNALS}")
print()
print(f"Recupero entro {MAX_SIGNALS} segnali: {pct_recovered:.1f}%")
print()
print(f"Segnali al recupero (mediana): {int(np.median(recovered))}" if recovered else "")
print(f"Segnali al recupero (p25-p75): {int(np.percentile(recovered,25))} - {int(np.percentile(recovered,75))}" if recovered else "")
print(f"Segnali al recupero (p90)    : {int(np.percentile(recovered,90))}" if recovered else "")
print()
print(f"Max stake mediana  : EUR {np.median(max_exp_list):.0f}")
print(f"Max stake p95      : EUR {np.percentile(max_exp_list,95):.0f}")
print(f"Max stake p99      : EUR {np.percentile(max_exp_list,99):.0f}")
print()
print(f"P&L finale mediana : EUR {np.median(final_pnl_list):+.0f}")
print(f"P&L finale p10     : EUR {np.percentile(final_pnl_list,10):+.0f}")
print(f"P&L finale p90     : EUR {np.percentile(final_pnl_list,90):+.0f}")

# ── GRAFICI ──────────────────────────────────────────────────────────
fig_bg   = '#0f0f1a'
axes_bg  = '#1a1a2e'
grid_col = '#2a2a4a'
txt_col  = '#e0e0e0'

fig, axes = plt.subplots(2, 3, figsize=(20, 12), facecolor=fig_bg)
fig.suptitle(f'Recovery Simulazione Monte Carlo — K=5 (cap €100) | Debito iniziale €{STARTING_DEBT:.0f}',
             fontsize=16, fontweight='bold', color='white', y=0.98)

# ── 1. Fan chart curve P&L ───────────────────────────────────────────
ax = axes[0, 0]
ax.set_facecolor(axes_bg)
xs = list(range(MAX_SIGNALS + 1))
p10 = [np.percentile([c[i] for c in all_curves], 10) for i in xs]
p25 = [np.percentile([c[i] for c in all_curves], 25) for i in xs]
p50 = [np.percentile([c[i] for c in all_curves], 50) for i in xs]
p75 = [np.percentile([c[i] for c in all_curves], 75) for i in xs]
p90 = [np.percentile([c[i] for c in all_curves], 90) for i in xs]

ax.fill_between(xs, p10, p90, alpha=0.15, color='#3498db', label='p10-p90')
ax.fill_between(xs, p25, p75, alpha=0.25, color='#3498db', label='p25-p75')
ax.plot(xs, p50, color='#3498db', linewidth=2.5, label='Mediana')
ax.axhline(0, color='white', linewidth=0.8, linestyle=':', alpha=0.6)
ax.axhline(-STARTING_DEBT, color='#e74c3c', linewidth=1.2, linestyle='--',
           alpha=0.7, label=f'Debito iniziale -€{STARTING_DEBT:.0f}')
ax.set_title('P&L Cumulativo (fan chart)', color=txt_col, fontsize=11, fontweight='bold')
ax.set_xlabel('Segnale #', color=txt_col)
ax.set_ylabel('P&L (EUR)', color=txt_col)
ax.tick_params(colors=txt_col)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_col, fontsize=8)
ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

# ── 2. Distribuzione segnali al recupero ────────────────────────────
ax = axes[0, 1]
ax.set_facecolor(axes_bg)
if recovered:
    bins = range(0, min(MAX_SIGNALS + 1, max(recovered) + 20), 5)
    n, b, patches = ax.hist(recovered, bins=bins, color='#2ecc71', alpha=0.8, edgecolor='white', lw=0.4)
    med = int(np.median(recovered))
    ax.axvline(med, color='#f39c12', linewidth=2, linestyle='--', label=f'Mediana: {med} segnali')
    p25v = int(np.percentile(recovered, 25))
    p75v = int(np.percentile(recovered, 75))
    ax.axvspan(p25v, p75v, alpha=0.15, color='#f39c12', label=f'IQR: {p25v}-{p75v}')
ax.set_title(f'Segnali Necessari al Recupero\n({pct_recovered:.1f}% recupera entro {MAX_SIGNALS} segnali)',
             color=txt_col, fontsize=11, fontweight='bold')
ax.set_xlabel('Segnali al recupero', color=txt_col)
ax.set_ylabel('Frequenza', color=txt_col)
ax.tick_params(colors=txt_col)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_col, fontsize=9)
ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

# ── 3. Distribuzione max stake ───────────────────────────────────────
ax = axes[0, 2]
ax.set_facecolor(axes_bg)
ax.hist(max_exp_list, bins=50, color='#e74c3c', alpha=0.8, edgecolor='white', lw=0.4)
p95v = np.percentile(max_exp_list, 95)
p99v = np.percentile(max_exp_list, 99)
ax.axvline(np.median(max_exp_list), color='#f39c12', linewidth=2,
           linestyle='--', label=f'Mediana: €{np.median(max_exp_list):.0f}')
ax.axvline(p95v, color='#e74c3c', linewidth=1.5,
           linestyle=':', label=f'p95: €{p95v:.0f}')
ax.axvline(p99v, color='#c0392b', linewidth=1.5,
           linestyle=':', label=f'p99: €{p99v:.0f}')
ax.set_title('Distribuzione Max Stake Singola', color=txt_col, fontsize=11, fontweight='bold')
ax.set_xlabel('Max stake (EUR)', color=txt_col)
ax.set_ylabel('Frequenza', color=txt_col)
ax.tick_params(colors=txt_col)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_col, fontsize=9)
ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

# ── 4. Debito residuo nel tempo (percentili) ─────────────────────────
ax = axes[1, 0]
ax.set_facecolor(axes_bg)

# Calcola debito residuo per ogni passo
debt_curves = []
for _ in range(2000):
    debt = STARTING_DEBT
    dcurve = [debt]
    for i in range(MAX_SIGNALS):
        s = random.choice(played)
        odds = s['odds']
        base_stake = s.get('stake', 20.0)
        is_win = random.random() < (sum(1 for x in played if 'VINTO' in str(x.get('result',''))) / len(played))
        if debt <= 0.0001:
            stake = base_stake
        else:
            full_stake = debt / ((odds - 1) * COMMISSION)
            stake = min(full_stake, base_stake * K_FACTOR)
        if is_win:
            debt = max(0.0, debt - stake * (odds - 1) * COMMISSION)
        else:
            debt += stake
        dcurve.append(debt)
    debt_curves.append(dcurve)

d_p25 = [np.percentile([c[i] for c in debt_curves], 25) for i in range(MAX_SIGNALS + 1)]
d_p50 = [np.percentile([c[i] for c in debt_curves], 50) for i in range(MAX_SIGNALS + 1)]
d_p75 = [np.percentile([c[i] for c in debt_curves], 75) for i in range(MAX_SIGNALS + 1)]
d_p90 = [np.percentile([c[i] for c in debt_curves], 90) for i in range(MAX_SIGNALS + 1)]

ax.fill_between(xs, d_p25, d_p75, alpha=0.25, color='#f39c12')
ax.fill_between(xs, d_p75, d_p90, alpha=0.12, color='#e74c3c')
ax.plot(xs, d_p50, color='#f39c12', linewidth=2.5, label='Mediana debito')
ax.plot(xs, d_p90, color='#e74c3c', linewidth=1.5, linestyle='--', label='p90 debito')
ax.axhline(0, color='#2ecc71', linewidth=1.2, linestyle='--', alpha=0.8, label='Debito = 0')
ax.set_title('Evoluzione Debito Residuo', color=txt_col, fontsize=11, fontweight='bold')
ax.set_xlabel('Segnale #', color=txt_col)
ax.set_ylabel('Debito (EUR)', color=txt_col)
ax.tick_params(colors=txt_col)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_col, fontsize=9)
ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

# ── 5. P&L finale distribuzione ──────────────────────────────────────
ax = axes[1, 1]
ax.set_facecolor(axes_bg)
ax.hist(final_pnl_list, bins=60, color='#9b59b6', alpha=0.8, edgecolor='white', lw=0.4)
ax.axvline(np.median(final_pnl_list), color='#f39c12', linewidth=2,
           linestyle='--', label=f'Mediana: €{np.median(final_pnl_list):+.0f}')
ax.axvline(0, color='white', linewidth=1, linestyle=':', alpha=0.7)
p10v_pnl = np.percentile(final_pnl_list, 10)
p90v_pnl = np.percentile(final_pnl_list, 90)
ax.axvline(p10v_pnl, color='#e74c3c', linewidth=1.5,
           linestyle=':', label=f'p10: €{p10v_pnl:+.0f}')
ax.axvline(p90v_pnl, color='#2ecc71', linewidth=1.5,
           linestyle=':', label=f'p90: €{p90v_pnl:+.0f}')
pct_pos = sum(1 for x in final_pnl_list if x > 0) / N_SIMS * 100
ax.set_title(f'P&L Finale dopo {MAX_SIGNALS} segnali\n({pct_pos:.1f}% scenari in profitto)',
             color=txt_col, fontsize=11, fontweight='bold')
ax.set_xlabel('P&L finale (EUR)', color=txt_col)
ax.set_ylabel('Frequenza', color=txt_col)
ax.tick_params(colors=txt_col)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_col, fontsize=9)
ax.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

# ── 6. Riepilogo testuale ─────────────────────────────────────────────
ax = axes[1, 2]
ax.set_facecolor(axes_bg)
ax.axis('off')

lines = [
    ("PARAMETRI", '#f39c12', 13, True),
    (f"Debito iniziale:  €{STARTING_DEBT:.0f}", txt_col, 11, False),
    (f"Cap per bet:       K=5 (max €100)", txt_col, 11, False),
    (f"WR storico:        62.3%", txt_col, 11, False),
    (f"Simulazioni:       {N_SIMS:,}", txt_col, 11, False),
    ("", txt_col, 8, False),
    ("RECUPERO", '#2ecc71', 13, True),
    (f"Prob recupero:     {pct_recovered:.1f}%", txt_col, 11, False),
    (f"Mediana segnali:   {int(np.median(recovered)) if recovered else 'N/A'}", txt_col, 11, False),
    (f"IQR segnali:       {int(np.percentile(recovered,25)) if recovered else 'N/A'} - {int(np.percentile(recovered,75)) if recovered else 'N/A'}", txt_col, 11, False),
    ("", txt_col, 8, False),
    ("ESPOSIZIONE", '#e74c3c', 13, True),
    (f"Max stake mediana: €{np.median(max_exp_list):.0f}", txt_col, 11, False),
    (f"Max stake p95:     €{np.percentile(max_exp_list,95):.0f}", txt_col, 11, False),
    (f"Max stake p99:     €{np.percentile(max_exp_list,99):.0f}", txt_col, 11, False),
    ("", txt_col, 8, False),
    ("PROFITTO ATTESO", '#3498db', 13, True),
    (f"P&L mediana:       €{np.median(final_pnl_list):+.0f}", txt_col, 11, False),
    (f"P&L p10:           €{np.percentile(final_pnl_list,10):+.0f}", txt_col, 11, False),
    (f"P&L p90:           €{np.percentile(final_pnl_list,90):+.0f}", txt_col, 11, False),
    (f"Scenari positivi:  {pct_pos:.1f}%", txt_col, 11, False),
]

y_pos = 0.97
for text, color, size, bold in lines:
    ax.text(0.05, y_pos, text, transform=ax.transAxes,
            color=color, fontsize=size, fontweight='bold' if bold else 'normal',
            va='top')
    y_pos -= 0.047

ax.set_title('Riepilogo Statistiche', color=txt_col, fontsize=11, fontweight='bold')
for sp in ax.spines.values(): sp.set_edgecolor(grid_col)

plt.tight_layout(rect=[0, 0, 1, 0.96])
out = r'C:/Users/Admin/Desktop/recovery_montecarlo.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig_bg)
plt.close()
print(f"\nSalvato: {out}")
