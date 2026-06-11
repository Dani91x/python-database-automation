import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

with open('Betfair/mm_history.json', 'r', encoding='utf-8') as f:
    history = json.load(f)

ht05 = []
for day in history:
    date = day.get('date', '')
    for s in day.get('slots', []):
        if s.get('market') == 'HT05':
            ht05.append({'date': date, **s})
    for s in day.get('ml_slots', []):
        if s.get('market') == 'HT05':
            ht05.append({'date': date, **s})
ht05.sort(key=lambda x: x['date'])

COMMISSION = 0.95

def simulate(signals, k_factor):
    debt = 0.0
    total_pnl = 0.0
    pnl_curve = []
    stake_curve = []
    debt_curve = []
    max_stake = 0.0
    max_debt = 0.0

    for s in signals:
        odds = s.get('odds', 0)
        is_win = 'VINTO' in str(s.get('result', ''))
        is_loss = 'PERSO' in str(s.get('result', ''))
        base_stake = s.get('stake', 20.0)

        if debt <= 0.0001:
            stake = base_stake
        else:
            full_recovery_stake = debt / ((odds - 1) * COMMISSION)
            if k_factor is None:
                stake = full_recovery_stake
            else:
                cap = base_stake * k_factor
                stake = min(full_recovery_stake, cap)

        max_stake = max(max_stake, stake)

        if is_win:
            bet_pnl = stake * (odds - 1) * COMMISSION
            debt = max(0.0, debt - bet_pnl)
        elif is_loss:
            bet_pnl = -stake
            debt += stake
        else:
            bet_pnl = 0.0

        max_debt = max(max_debt, debt)
        total_pnl += bet_pnl
        pnl_curve.append(total_pnl)
        stake_curve.append(stake)
        debt_curve.append(debt)

    return {
        'pnl_curve': pnl_curve,
        'stake_curve': stake_curve,
        'debt_curve': debt_curve,
        'total_pnl': total_pnl,
        'max_stake': max_stake,
        'max_debt': max_debt,
        'final_debt': debt,
    }

scenarios = {
    'No cap (originale)': None,
    'Cap K=3 (max €60)': 3,
    'Cap K=5 (max €100)': 5,
    'Cap K=10 (max €200)': 10,
}

results = {name: simulate(ht05, k) for name, k in scenarios.items()}

COLORS = {
    'No cap (originale)':  '#e74c3c',
    'Cap K=3 (max €60)':   '#3498db',
    'Cap K=5 (max €100)':  '#2ecc71',
    'Cap K=10 (max €200)': '#f39c12',
}

x = list(range(1, len(ht05) + 1))
axes_bg   = '#1a1a2e'
grid_col  = '#2a2a4a'
txt_col   = '#e0e0e0'
fig_bg    = '#0f0f1a'

fig = plt.figure(figsize=(20, 22), facecolor=fig_bg)
fig.suptitle('Over 0.5 HT  —  Analisi Scenari Recovery', fontsize=20,
             fontweight='bold', color='white', y=0.98)

# ── 1. P&L cumulativo ────────────────────────────────────────────────
ax1 = fig.add_subplot(4, 2, (1, 2))
ax1.set_facecolor(axes_bg)
for name, res in results.items():
    lw = 1.5 if 'originale' in name else 2.5
    ls = '--'  if 'originale' in name else '-'
    ax1.plot(x, res['pnl_curve'], color=COLORS[name], linewidth=lw,
             linestyle=ls, label=name, alpha=0.9)
ax1.axhline(0, color='white', linewidth=0.8, linestyle=':', alpha=0.5)
ax1.fill_between(x, 0,
    [min(0, v) for v in results['No cap (originale)']['pnl_curve']],
    alpha=0.08, color='#e74c3c')
# Annota minimo scenario originale
orig_curve = results['No cap (originale)']['pnl_curve']
w_idx = orig_curve.index(min(orig_curve))
w_val = orig_curve[w_idx]
ax1.annotate(f'Min: \u20ac{w_val:.0f}\n(seg. {w_idx+1})',
             xy=(w_idx+1, w_val), xytext=(w_idx+8, w_val - 120),
             color='#e74c3c', fontsize=9,
             arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5))
ax1.set_title('Curva P&L Cumulativo', color=txt_col, fontsize=13, fontweight='bold', pad=10)
ax1.set_xlabel('Segnale #', color=txt_col)
ax1.set_ylabel('P&L (EUR)', color=txt_col)
ax1.tick_params(colors=txt_col)
ax1.legend(loc='upper left', facecolor=axes_bg, edgecolor='#444',
           labelcolor=txt_col, fontsize=10)
ax1.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax1.spines.values():
    sp.set_edgecolor(grid_col)

# ── 2. Stake per segnale (log scale) ─────────────────────────────────
ax2 = fig.add_subplot(4, 2, 3)
ax2.set_facecolor(axes_bg)
for name, res in results.items():
    ax2.plot(x, res['stake_curve'], color=COLORS[name], linewidth=1.2,
             label=name, alpha=0.85)
ax2.set_title('Stake per Segnale (scala log)', color=txt_col, fontsize=12,
              fontweight='bold', pad=8)
ax2.set_xlabel('Segnale #', color=txt_col)
ax2.set_ylabel('Stake (EUR)', color=txt_col)
ax2.set_yscale('log')
ax2.tick_params(colors=txt_col)
ax2.legend(loc='upper left', facecolor=axes_bg, edgecolor='#444',
           labelcolor=txt_col, fontsize=8)
ax2.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax2.spines.values():
    sp.set_edgecolor(grid_col)

# ── 3. Debito residuo nel tempo ───────────────────────────────────────
ax3 = fig.add_subplot(4, 2, 4)
ax3.set_facecolor(axes_bg)
for name, res in results.items():
    ax3.plot(x, res['debt_curve'], color=COLORS[name], linewidth=1.2,
             label=name, alpha=0.85)
ax3.set_title('Debito Residuo nel Tempo', color=txt_col, fontsize=12,
              fontweight='bold', pad=8)
ax3.set_xlabel('Segnale #', color=txt_col)
ax3.set_ylabel('Debito (EUR)', color=txt_col)
ax3.tick_params(colors=txt_col)
ax3.legend(loc='upper right', facecolor=axes_bg, edgecolor='#444',
           labelcolor=txt_col, fontsize=8)
ax3.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax3.spines.values():
    sp.set_edgecolor(grid_col)

# ── 4. Bar: Max stake ─────────────────────────────────────────────────
ax4 = fig.add_subplot(4, 2, 5)
ax4.set_facecolor(axes_bg)
names = list(results.keys())
max_stakes = [results[n]['max_stake'] for n in names]
bars4 = ax4.bar(range(len(names)), max_stakes,
                color=[COLORS[n] for n in names],
                edgecolor='white', linewidth=0.5, alpha=0.85, width=0.6)
for bar, val in zip(bars4, max_stakes):
    ax4.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
             f'\u20ac{val:,.0f}', ha='center', va='bottom',
             color=txt_col, fontsize=9, fontweight='bold')
ax4.set_title('Massima Stake Singola', color=txt_col, fontsize=12,
              fontweight='bold', pad=8)
ax4.set_xticks(range(len(names)))
ax4.set_xticklabels([n.split('(')[0].strip() for n in names],
                    color=txt_col, fontsize=9)
ax4.tick_params(colors=txt_col)
ax4.set_ylabel('EUR', color=txt_col)
ax4.grid(True, axis='y', color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax4.spines.values():
    sp.set_edgecolor(grid_col)

# ── 5. Bar: Profitto totale ───────────────────────────────────────────
ax5 = fig.add_subplot(4, 2, 6)
ax5.set_facecolor(axes_bg)
profits = [results[n]['total_pnl'] for n in names]
bars5 = ax5.bar(range(len(names)), profits,
                color=[COLORS[n] for n in names],
                edgecolor='white', linewidth=0.5, alpha=0.85, width=0.6)
for bar, val in zip(bars5, profits):
    offset = 8 if val >= 0 else -30
    ax5.text(bar.get_x() + bar.get_width() / 2, val + offset,
             f'\u20ac{val:+,.0f}', ha='center', va='bottom',
             color=txt_col, fontsize=9, fontweight='bold')
ax5.set_title('Profitto Totale (183 segnali)', color=txt_col, fontsize=12,
              fontweight='bold', pad=8)
ax5.set_xticks(range(len(names)))
ax5.set_xticklabels([n.split('(')[0].strip() for n in names],
                    color=txt_col, fontsize=9)
ax5.tick_params(colors=txt_col)
ax5.set_ylabel('EUR', color=txt_col)
ax5.axhline(0, color='white', linewidth=0.8, linestyle=':', alpha=0.5)
ax5.grid(True, axis='y', color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax5.spines.values():
    sp.set_edgecolor(grid_col)

# ── 6. Zoom sequenza peggiore (28 mar) ───────────────────────────────
ax6 = fig.add_subplot(4, 2, 7)
ax6.set_facecolor(axes_bg)
zoom = range(143, 158)  # intorno al worst case 28 marzo
for name, res in results.items():
    lw = 1.5 if 'originale' in name else 2.5
    ls = '--'  if 'originale' in name else '-'
    ax6.plot([i + 1 for i in zoom],
             [res['stake_curve'][i] for i in zoom],
             color=COLORS[name], linewidth=lw, linestyle=ls,
             label=name, alpha=0.9, marker='o', markersize=4)
ax6.set_title('Zoom Stake — Sequenza Critica (28 mar, 5 loss)', color=txt_col,
              fontsize=11, fontweight='bold', pad=8)
ax6.set_xlabel('Segnale #', color=txt_col)
ax6.set_ylabel('Stake (EUR)', color=txt_col)
ax6.tick_params(colors=txt_col)
ax6.legend(loc='upper left', facecolor=axes_bg, edgecolor='#444',
           labelcolor=txt_col, fontsize=8)
ax6.grid(True, color=grid_col, linewidth=0.5, alpha=0.7)
for sp in ax6.spines.values():
    sp.set_edgecolor(grid_col)

# ── 7. Tabella riepilogo ──────────────────────────────────────────────
ax7 = fig.add_subplot(4, 2, 8)
ax7.set_facecolor(axes_bg)
ax7.axis('off')

headers = ['Scenario', 'Profitto', 'Max Stake', 'Max Debito', 'Debito\nfinale']
col_x   = [0.02, 0.30, 0.47, 0.64, 0.82]
col_w   = [0.28, 0.17, 0.17, 0.18, 0.18]

for j, (h, cx, cw) in enumerate(zip(headers, col_x, col_w)):
    ax7.text(cx + cw / 2, 0.92, h, transform=ax7.transAxes,
             ha='center', va='center', color='white', fontsize=9,
             fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#2a2a5a',
                       edgecolor='#555'))

row_colors_t = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12']
for i, (name, rc) in enumerate(zip(names, row_colors_t)):
    res = results[name]
    row = [
        name.split('(')[0].strip(),
        f"\u20ac{res['total_pnl']:+,.0f}",
        f"\u20ac{res['max_stake']:,.0f}",
        f"\u20ac{res['max_debt']:,.0f}",
        f"\u20ac{res['final_debt']:,.0f}",
    ]
    y = 0.72 - i * 0.17
    for j, (cell, cx, cw) in enumerate(zip(row, col_x, col_w)):
        color = rc if j == 0 else txt_col
        fw = 'bold' if j == 0 else 'normal'
        ax7.text(cx + cw / 2, y, cell, transform=ax7.transAxes,
                 ha='center', va='center', color=color,
                 fontsize=9, fontweight=fw)

ax7.set_title('Riepilogo Scenari', color=txt_col, fontsize=12,
              fontweight='bold', pad=8)

plt.tight_layout(rect=[0, 0, 1, 0.97])
out_path = r'C:/Users/Admin/Desktop/recovery_analysis.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=fig_bg)
plt.close()
print('Salvato:', out_path)
print()
for name, res in results.items():
    print(f"{name}:")
    print(f"  Profitto totale  : EUR {res['total_pnl']:+.2f}")
    print(f"  Max stake singola: EUR {res['max_stake']:,.2f}")
    print(f"  Max debito       : EUR {res['max_debt']:,.2f}")
    print(f"  Debito finale    : EUR {res['final_debt']:,.2f}")
    print()
