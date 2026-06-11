import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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

fig_bg  = '#0f0f1a'
axes_bg = '#1a1a2e'
grid_c  = '#2a2a4a'
txt_c   = '#e0e0e0'

fig, axes = plt.subplots(2, 3, figsize=(20, 12), facecolor=fig_bg)
fig.suptitle('HT05 — Analisi Soglie Ottimali (prob + odds)', fontsize=16,
             fontweight='bold', color='white', y=0.98)

# ── 1. Scan min_prob: volume, WR, yield ──────────────────────────────
ax = axes[0, 0]
ax.set_facecolor(axes_bg)

thresholds = [x / 100 for x in range(60, 94, 2)]
ns, wrs, yields, pnls, margins = [], [], [], [], []

for thr in thresholds:
    sg = [s for s in played if s.get('prob', 0) >= thr]
    if len(sg) < 5:
        ns.append(0); wrs.append(0); yields.append(0)
        pnls.append(0); margins.append(0)
        continue
    w   = sum(1 for s in sg if 'VINTO' in str(s.get('result', '')))
    pnl = sum(s.get('pnl', 0) for s in sg)
    stk = sum(s.get('stake', 0) for s in sg)
    ao  = sum(s['odds'] for s in sg) / len(sg)
    be  = 1 / ((ao - 1) * 0.95 + 1)
    ns.append(len(sg))
    wrs.append(w / len(sg) * 100)
    yields.append(pnl / stk * 100 if stk else 0)
    pnls.append(pnl)
    margins.append((w / len(sg) - be) * 100)

ax2 = ax.twinx()
color_n   = '#3498db'
color_wr  = '#2ecc71'
color_yld = '#f39c12'

ax.bar(range(len(thresholds)), ns, color=color_n, alpha=0.4, label='N segnali')
ax2.plot(range(len(thresholds)), yields, color=color_yld, linewidth=2.5,
         marker='o', markersize=5, label='Yield %')
ax2.plot(range(len(thresholds)), wrs, color=color_wr, linewidth=2,
         marker='s', markersize=4, linestyle='--', label='WR %')
ax2.axhline(0, color='white', linewidth=0.8, linestyle=':', alpha=0.5)

# Evidenzia zona positiva
pos_idxs = [i for i, y in enumerate(yields) if y > 0]
for i in pos_idxs:
    ax.axvspan(i - 0.5, i + 0.5, alpha=0.12, color='#2ecc71')

ax.set_xticks(range(len(thresholds)))
ax.set_xticklabels([f'{t:.2f}' for t in thresholds], rotation=45, fontsize=7, color=txt_c)
ax.set_ylabel('N segnali', color=color_n, fontsize=9)
ax2.set_ylabel('WR / Yield %', color=txt_c, fontsize=9)
ax.tick_params(colors=txt_c)
ax2.tick_params(colors=txt_c)
ax.set_title('Scan min_prob (solo soglia prob)', color=txt_c, fontsize=11, fontweight='bold')

lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, facecolor=axes_bg,
          edgecolor='#444', labelcolor=txt_c, fontsize=8, loc='upper right')
ax.grid(True, color=grid_c, linewidth=0.5, alpha=0.7, axis='x')
for sp in ax.spines.values():  sp.set_edgecolor(grid_c)
for sp in ax2.spines.values(): sp.set_edgecolor(grid_c)

# ── 2. Heatmap yield: prob x odds ────────────────────────────────────
ax = axes[0, 1]
ax.set_facecolor(axes_bg)

prob_thr  = [0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90]
odds_thr  = [1.25, 1.30, 1.35, 1.40, 1.45]
hmap_yield = np.full((len(prob_thr), len(odds_thr)), np.nan)
hmap_n     = np.full((len(prob_thr), len(odds_thr)), 0)

for i, mp in enumerate(prob_thr):
    for j, mo in enumerate(odds_thr):
        sg = [s for s in played if s.get('prob', 0) >= mp and s['odds'] >= mo]
        if len(sg) < 6:
            continue
        stk = sum(s.get('stake', 0) for s in sg)
        pnl = sum(s.get('pnl', 0) for s in sg)
        hmap_yield[i, j] = pnl / stk * 100 if stk else np.nan
        hmap_n[i, j]     = len(sg)

im = ax.imshow(hmap_yield, cmap='RdYlGn', aspect='auto', vmin=-20, vmax=20)
plt.colorbar(im, ax=ax, label='Yield %').ax.yaxis.label.set_color(txt_c)

for i in range(len(prob_thr)):
    for j in range(len(odds_thr)):
        if not np.isnan(hmap_yield[i, j]):
            txt = f'{hmap_yield[i,j]:+.1f}%\nn={hmap_n[i,j]}'
            color = 'black' if -10 < hmap_yield[i, j] < 10 else 'white'
            ax.text(j, i, txt, ha='center', va='center',
                    fontsize=7.5, color=color, fontweight='bold')

ax.set_xticks(range(len(odds_thr)))
ax.set_xticklabels([f'≥{o:.2f}' for o in odds_thr], color=txt_c, fontsize=9)
ax.set_yticks(range(len(prob_thr)))
ax.set_yticklabels([f'≥{p:.2f}' for p in prob_thr], color=txt_c, fontsize=9)
ax.set_xlabel('Min odds', color=txt_c)
ax.set_ylabel('Min prob', color=txt_c)
ax.set_title('Heatmap Yield% (prob × odds)', color=txt_c, fontsize=11, fontweight='bold')
ax.tick_params(colors=txt_c)
for sp in ax.spines.values(): sp.set_edgecolor(grid_c)

# ── 3. Heatmap N segnali ─────────────────────────────────────────────
ax = axes[0, 2]
ax.set_facecolor(axes_bg)

im2 = ax.imshow(hmap_n.astype(float), cmap='Blues', aspect='auto', vmin=0, vmax=50)
plt.colorbar(im2, ax=ax, label='N segnali').ax.yaxis.label.set_color(txt_c)

for i in range(len(prob_thr)):
    for j in range(len(odds_thr)):
        if hmap_n[i, j] >= 6:
            w_sg = [s for s in played if s.get('prob',0) >= prob_thr[i] and s['odds'] >= odds_thr[j]]
            w_c  = sum(1 for s in w_sg if 'VINTO' in str(s.get('result','')))
            wr_v = w_c / len(w_sg) * 100 if w_sg else 0
            ax.text(j, i, f'n={hmap_n[i,j]}\nWR={wr_v:.0f}%',
                    ha='center', va='center', fontsize=7.5, color='white', fontweight='bold')

ax.set_xticks(range(len(odds_thr)))
ax.set_xticklabels([f'≥{o:.2f}' for o in odds_thr], color=txt_c, fontsize=9)
ax.set_yticks(range(len(prob_thr)))
ax.set_yticklabels([f'≥{p:.2f}' for p in prob_thr], color=txt_c, fontsize=9)
ax.set_xlabel('Min odds', color=txt_c)
ax.set_ylabel('Min prob', color=txt_c)
ax.set_title('Heatmap N segnali + WR%', color=txt_c, fontsize=11, fontweight='bold')
ax.tick_params(colors=txt_c)
for sp in ax.spines.values(): sp.set_edgecolor(grid_c)

# ── 4. Curva volume vs yield (frontier) ──────────────────────────────
ax = axes[1, 0]
ax.set_facecolor(axes_bg)

points = []
for mp in [x/100 for x in range(60, 94, 1)]:
    for mo in [1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50]:
        sg = [s for s in played if s.get('prob',0) >= mp and s['odds'] >= mo]
        if len(sg) < 8:
            continue
        stk = sum(s.get('stake',0) for s in sg)
        pnl = sum(s.get('pnl',0) for s in sg)
        yld = pnl/stk*100 if stk else 0
        points.append({'n': len(sg), 'yield': yld, 'mp': mp, 'mo': mo, 'pnl': pnl})

xs = [p['n']     for p in points]
ys = [p['yield'] for p in points]
cs = ['#2ecc71' if p['yield'] > 0 else '#e74c3c' for p in points]

ax.scatter(xs, ys, c=cs, alpha=0.5, s=20)
ax.axhline(0, color='white', linewidth=1, linestyle='--', alpha=0.7)
ax.set_xlabel('N segnali', color=txt_c)
ax.set_ylabel('Yield %', color=txt_c)
ax.set_title('Volume vs Yield (ogni combinazione prob+odds)', color=txt_c,
             fontsize=11, fontweight='bold')
ax.tick_params(colors=txt_c)
ax.grid(True, color=grid_c, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_c)

# Annota i candidati migliori
candidates = [p for p in points if p['yield'] > 3 and p['n'] >= 15]
for p in sorted(candidates, key=lambda x: -x['yield'])[:5]:
    ax.annotate(f"p≥{p['mp']:.2f}\no≥{p['mo']:.2f}\nn={p['n']}",
                xy=(p['n'], p['yield']),
                xytext=(p['n'] + 4, p['yield'] + 0.5),
                color='#2ecc71', fontsize=7.5,
                arrowprops=dict(arrowstyle='->', color='#2ecc71', lw=1))

# ── 5. Distribuzione WR per fascia prob (boxplot stile) ──────────────
ax = axes[1, 1]
ax.set_facecolor(axes_bg)

# Simula errore standard sul WR (intervallo di confidenza 95%)
thresh_list  = [0.78, 0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92]
wr_vals, ci_low, ci_high, n_vals = [], [], [], []

for thr in thresh_list:
    sg = [s for s in played if s.get('prob', 0) >= thr]
    if len(sg) < 5:
        wr_vals.append(None); ci_low.append(None)
        ci_high.append(None); n_vals.append(0)
        continue
    w  = sum(1 for s in sg if 'VINTO' in str(s.get('result', '')))
    wr = w / len(sg)
    se = math.sqrt(wr * (1 - wr) / len(sg))
    ao = sum(s['odds'] for s in sg) / len(sg)
    be = 1 / ((ao - 1) * 0.95 + 1)
    wr_vals.append(wr * 100)
    ci_low.append((wr - 1.96 * se) * 100)
    ci_high.append((wr + 1.96 * se) * 100)
    n_vals.append(len(sg))

valid = [(i, thr, wr, lo, hi, n)
         for i, (thr, wr, lo, hi, n)
         in enumerate(zip(thresh_list, wr_vals, ci_low, ci_high, n_vals))
         if wr is not None]

xs_v  = [v[0] for v in valid]
wrs_v = [v[2] for v in valid]
los_v = [v[3] for v in valid]
his_v = [v[4] for v in valid]
ns_v  = [v[5] for v in valid]

ax.errorbar(xs_v, wrs_v,
            yerr=[[w - l for w, l in zip(wrs_v, los_v)],
                  [h - w for h, w in zip(his_v, wrs_v)]],
            fmt='o-', color='#3498db', linewidth=2, markersize=6,
            capsize=5, capthick=1.5, label='WR ± 1.96σ (95% CI)')

# Linea BE media
for i, (_, thr, _, _, _, _) in enumerate(valid):
    sg = [s for s in played if s.get('prob', 0) >= thr]
    ao = sum(s['odds'] for s in sg) / len(sg)
    be = 1 / ((ao - 1) * 0.95 + 1) * 100
    ax.plot(i, be, 'x', color='#e74c3c', markersize=8, markeredgewidth=2)

ax.plot([], [], 'x', color='#e74c3c', markersize=8, markeredgewidth=2, label='Breakeven')
ax.axhline(62.3, color='#f39c12', linewidth=1.5, linestyle='--',
           alpha=0.8, label='WR globale 62.3%')

for i, n in enumerate(ns_v):
    ax.text(i, los_v[i] - 1.5, f'n={n}', ha='center', color=txt_c, fontsize=7.5)

ax.set_xticks(xs_v)
ax.set_xticklabels([f'≥{t:.2f}' for _, t, *_ in valid], color=txt_c, fontsize=9)
ax.set_ylabel('Win Rate %', color=txt_c)
ax.set_title('WR con Intervallo di Confidenza 95%\n(x = breakeven per quella soglia)',
             color=txt_c, fontsize=10, fontweight='bold')
ax.tick_params(colors=txt_c)
ax.legend(facecolor=axes_bg, edgecolor='#444', labelcolor=txt_c, fontsize=8)
ax.grid(True, color=grid_c, linewidth=0.5, alpha=0.7)
for sp in ax.spines.values(): sp.set_edgecolor(grid_c)

# ── 6. Riepilogo candidati ────────────────────────────────────────────
ax = axes[1, 2]
ax.set_facecolor(axes_bg)
ax.axis('off')

candidates_final = [
    ('Solo prob ≥ 0.90',        18, 77.8, 73.3, 16.35,  4.58),
    ('prob ≥ 0.84 + odds ≥ 1.45', 13, 76.9, 73.1, 33.10, 12.73),
    ('prob ≥ 0.84 + odds ≥ 1.35', 22, 72.7, 72.7, 14.92,  3.42),
    ('prob ≥ 0.82 + odds ≥ 1.45', 17, 70.6, 72.4, 14.38,  4.18),
    ('prob ≥ 0.82 + odds ≥ 1.35', 27, 66.7, 73.0, -23.80, -4.40),
    ('Attuale (nessun filtro)',  183, 62.3, 67.3, -296.79, -8.68),
]

headers = ['Filtro', 'N', 'WR%', 'BE%', 'P&L', 'Yield']
col_x   = [0.01, 0.50, 0.58, 0.66, 0.75, 0.88]
col_w   = [0.48, 0.08, 0.08, 0.08, 0.13, 0.12]

ax.text(0.5, 0.97, 'Candidati Ottimali', transform=ax.transAxes,
        ha='center', color='#f39c12', fontsize=12, fontweight='bold', va='top')

for j, (h, cx, cw) in enumerate(zip(headers, col_x, col_w)):
    ax.text(cx + cw / 2, 0.88, h, transform=ax.transAxes,
            ha='center', va='center', color='white', fontsize=8, fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='#2a2a5a', edgecolor='#555'))

for i, (name, n, wr, be, pnl, yld) in enumerate(candidates_final):
    y    = 0.74 - i * 0.115
    prof = pnl > 0
    bg   = '#1a3a1a' if prof else '#3a1a1a'
    ax.add_patch(plt.Rectangle((0.0, y - 0.04), 1.0, 0.10,
                                transform=ax.transAxes, color=bg, alpha=0.5))
    row  = [name, str(n), f'{wr:.1f}', f'{be:.1f}',
            f'€{pnl:+.0f}', f'{yld:+.1f}%']
    for j, (cell, cx, cw) in enumerate(zip(row, col_x, col_w)):
        color = ('#2ecc71' if prof else '#e74c3c') if j == 0 else txt_c
        fw    = 'bold' if j == 0 else 'normal'
        ax.text(cx + cw / 2, y + 0.01, cell, transform=ax.transAxes,
                ha='center', va='center', color=color, fontsize=7.5, fontweight=fw)

ax.text(0.5, 0.02,
        '* Campione limitato (13-27 segnali): CI ampi.\nAumento volume prima di applicare in produzione.',
        transform=ax.transAxes, ha='center', color='#f39c12',
        fontsize=7.5, style='italic')
ax.set_title('Riepilogo', color=txt_c, fontsize=11, fontweight='bold')
for sp in ax.spines.values(): sp.set_edgecolor(grid_c)

plt.tight_layout(rect=[0, 0, 1, 0.96])
out = r'C:/Users/Admin/Desktop/threshold_analysis.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=fig_bg)
plt.close()
print(f'Salvato: {out}')
