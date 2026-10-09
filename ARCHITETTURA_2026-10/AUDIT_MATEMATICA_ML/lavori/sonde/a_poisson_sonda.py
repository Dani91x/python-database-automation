"""Sonda A (audit matematica 09/10/2026): confronta le funzioni di produzione della catena Poisson
con un calcolo indipendente numpy/scipy. SOLA LETTURA: nessun DB, nessuna scrittura."""
import sys, math, io, contextlib
sys.path.insert(0, r"C:\Users\Admin\Desktop\PYTHON DATABASE\python-database-automation")
import numpy as np
from scipy.stats import poisson
from scipy.optimize import brentq as sp_brentq

import value_engine.bivariate as bv
import value_engine.poisson_total as pt
import tactical_engine.dixon_coles as dc
import tactical_engine.model as tm
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    import Prediction.today_predictions_backfill as tp


def indep(lam, mu, rho, N=200):
    """Riferimento indipendente: griglia ampia (N=200), tau esatta DC 1997, SENZA rinormalizzazione."""
    ks = np.arange(N + 1)
    g = np.outer(poisson.pmf(ks, lam), poisson.pmf(ks, mu))
    g[0, 0] *= 1 - lam * mu * rho
    g[0, 1] *= 1 + lam * rho
    g[1, 0] *= 1 + mu * rho
    g[1, 1] *= 1 - rho
    i = ks.reshape(-1, 1)
    j = ks.reshape(1, -1)
    return dict(H=g[i > j].sum(), D=g[i == j].sum(), A=g[i < j].sum(),
                O25=g[i + j >= 3].sum(), BTTS=g[(i > 0) & (j > 0)].sum(), total=g.sum(), minval=g.min())


def prod_value_engine(lam, mu, rho):
    M = bv.score_matrix(lam, mu, rho)
    return bv._markets_from_matrix(M)


def prod_tactical(lam, mu, rho, mg=10):
    m = dc.markets_from_matrix(dc.score_matrix(lam, mu, rho, mg))
    return dict(H=m["home"], D=m["draw"], A=m["away"], O25=m["over_2_5"], BTTS=m["btts_yes"])


def prod_today(lam, mu, rho, mg=10):
    grid = tp._build_score_grid(lam, mu, mg)
    for a in (0, 1):
        for b in (0, 1):
            grid[a, b] *= tp._dc_tau(a, b, lam, mu, rho=rho)
    grid = grid / grid.sum()
    i = np.arange(mg + 1).reshape(-1, 1)
    j = np.arange(mg + 1).reshape(1, -1)
    return dict(H=grid[i > j].sum(), D=grid[i == j].sum(), A=grid[i < j].sum(),
                O25=grid[i + j >= 3].sum(), BTTS=grid[(i > 0) & (j > 0)].sum())


print("=== 1) Probabilita' 1X2/O2.5/BTTS: produzione vs riferimento indipendente (N=200, no rinormalizz.) ===")
for lam, mu, rho in [(1.4, 1.1, -0.1), (1.4, 1.1, -0.13), (2.2, 0.8, -0.13), (0.9, 0.7, 0.05)]:
    ref = indep(lam, mu, rho)
    print(f"\n lam={lam} mu={mu} rho={rho}  | massa totale riferimento={ref['total']:.12f}")
    for nome, fn in (("value_engine.bivariate (MAX 15)", prod_value_engine),
                     ("tactical_engine.dixon_coles (10)", prod_tactical),
                     ("today_predictions_backfill (10)", prod_today)):
        out = fn(lam, mu, rho)
        d = {k: out[k] - ref[k] for k in ("H", "D", "A", "O25", "BTTS")}
        print(f"  {nome:36s} H={out['H']:.6f} D={out['D']:.6f} A={out['A']:.6f} O25={out['O25']:.6f} BTTS={out['BTTS']:.6f}"
              f"  maxabsdiff={max(abs(v) for v in d.values()):.2e}")
    print(f"  riferimento                          H={ref['H']:.6f} D={ref['D']:.6f} A={ref['A']:.6f} O25={ref['O25']:.6f} BTTS={ref['BTTS']:.6f}")

print("\n=== 2) Massa persa dal troncamento (Poisson indipendente, prima della rinormalizzazione) ===")
for lam, mu in [(1.4, 1.1), (2.5, 2.0), (3.5, 3.0), (5.0, 4.0)]:
    for mg in (4, 8, 10, 15):
        m = poisson.cdf(mg, lam) * poisson.cdf(mg, mu)
        print(f" lam={lam} mu={mu} max_goals={mg:2d}: massa tenuta={m:.8f} persa={1-m:.2e}")

print("\n=== 3) Non-negativita' con rho (celle DC) ===")
for lam, mu, rho in [(1.4, 1.1, -0.13), (1.4, 1.1, -0.25), (1.4, 1.1, 0.5), (3.0, 3.0, 0.15), (5.0, 4.0, -0.25), (9.0, 1.0, -0.13)]:
    taus = {c: dc.dc_tau(c[0], c[1], lam, mu, rho) for c in ((0, 0), (0, 1), (1, 0), (1, 1))}
    neg = [c for c, t in taus.items() if t < 0]
    lo = hi = None
    try:
        lo, hi = dc.rho_bounds(lam, mu, 0.0)
    except Exception:
        pass
    try:
        M = dc.score_matrix(lam, mu, rho, 10)
        r1 = f"min={M.min():.3e}"
    except Exception as e:
        r1 = f"ECCEZIONE {e}"
    try:
        M = np.array(bv.score_matrix(lam, mu, rho))
        r2 = f"min={M.min():.3e} (clamp tau>=0)"
    except Exception as e:
        r2 = f"ECCEZIONE {e}"
    g = tp._build_score_grid(lam, mu, 10)
    for a in (0, 1):
        for b in (0, 1):
            g[a, b] *= tp._dc_tau(a, b, lam, mu, rho=rho)
    r3 = f"min_prima_norm={g.min():.3e} sum={g.sum():.4f}"
    print(f" lam={lam} mu={mu} rho={rho}: tau<0 in {neg or 'nessuna'}; dominio rho=({None if lo is None else round(lo, 4)},{None if hi is None else round(hi, 4)})"
          f"\n    dixon_coles.score_matrix: {r1}\n    bivariate.score_matrix : {r2}\n    today._dc_tau griglia  : {r3}")

print("\n=== 4) Casi limite ===")


def tryit(label, f):
    try:
        v = f()
        print(f" {label}: {v}")
    except Exception as e:
        print(f" {label}: ECCEZIONE {type(e).__name__}: {e}")


import value_engine.devig as dv
tryit("dixon_coles.score_matrix(0,1.2,-0.1)", lambda: dc.score_matrix(0, 1.2, -0.1))
tryit("bivariate.score_matrix(0,1.2,-0.1)[0][0] (lam clamp 1e-6)", lambda: bv.score_matrix(0, 1.2, -0.1)[0][0])
tryit("today._build_score_grid(0,1.2,10).sum() (lambda=0 -> riga zero)", lambda: tp._build_score_grid(0, 1.2, 10).sum())
tryit("dixon_coles.score_matrix(nan,1.2,-0.1).sum()", lambda: dc.score_matrix(float('nan'), 1.2, -0.1).sum())
tryit("bivariate.score_matrix(nan,1.2,-0.1) somma", lambda: sum(map(sum, bv.score_matrix(float('nan'), 1.2, -0.1))))
tryit("bivariate.score_matrix(60,60,-0.13) somma (MAX 15)", lambda: sum(map(sum, bv.score_matrix(60, 60, -0.13))))
tryit("bivariate.pois(800,200)", lambda: bv.pois(800, 200))
tryit("dixon_coles.score_matrix(60,60,-0.13).sum()", lambda: dc.score_matrix(60, 60, -0.13).sum())
tryit("bivariate.score_matrix(900,900,-0.13) somma", lambda: sum(map(sum, bv.score_matrix(900, 900, -0.13))))
tryit("pt.p_le(3,0.0)", lambda: pt.p_le(3, 0.0))
tryit("pt.lam_from_prematch('over',2,0.0)", lambda: pt.lam_from_prematch('over', 2, 0.0))
tryit("pt.lam_from_prematch('over',2,nan)", lambda: pt.lam_from_prematch('over', 2, float('nan')))
tryit("pt.lam_from_prematch('under',0,0.5)", lambda: pt.lam_from_prematch('under', 0, 0.5))
tryit("pt.p_le(200, 150.0) (factorial)", lambda: pt.p_le(200, 150.0))
tryit("pt.p_le(180, 100.0)", lambda: pt.p_le(180, 100.0))
tryit("bv.derive_lambdas(0.5,0.5)", lambda: bv.derive_lambdas(0.5, 0.5))
tryit("bv.derive_lambdas(0.9,0.95)", lambda: bv.derive_lambdas(0.9, 0.95))
tryit("bv.derive_lambdas(0.5,0.5,rho=-0.5)", lambda: bv.derive_lambdas(0.5, 0.5, rho=-0.5))
tryit("devig_multiplicative({'H':1.0,'D':3.0,'A':5.0})", lambda: dv.devig_multiplicative({'H': 1.0, 'D': 3.0, 'A': 5.0}))
tryit("devig_pair(2.0, 2.0)", lambda: dv.devig_pair(2.0, 2.0))
tryit("devig_pair(1.9, 1.0 sospeso)", lambda: dv.devig_pair(1.9, 1.0))
tryit("devig_pair(nan, 2.0)", lambda: dv.devig_pair(float('nan'), 2.0))

print("\n=== 5) Roundtrip derive_lambdas (p_home, p_over25) -> (lam, mu) -> mercati ===")
for ph, po in [(0.45, 0.55), (0.60, 0.50), (0.25, 0.45)]:
    lam, mu = bv.derive_lambdas(ph, po, -0.13)
    mk = prod_value_engine(lam, mu, -0.13)
    ref = indep(lam, mu, -0.13)
    print(f" p_home={ph} p_over25={po} -> lam={lam:.4f} mu={mu:.4f}; round-trip H={mk['H']:.4f} O25={mk['O25']:.4f}; "
          f"riferimento(N=200) H={ref['H']:.4f} O25={ref['O25']:.4f}")

print("\n=== 6) De-vig: proporzionale vs potenza vs Shin su 1X2 tipico (quote 2.10/3.40/3.60) ===")
odds = np.array([2.10, 3.40, 3.60])
raw = 1 / odds
s = raw.sum()
prop = raw / s
k = sp_brentq(lambda k: (raw ** k).sum() - 1, 0.5, 5.0)
powr = raw ** k


def shin_p(z):
    return (np.sqrt(z ** 2 + 4 * (1 - z) * raw ** 2 / s) - z) / (2 * (1 - z))


z = sp_brentq(lambda z: shin_p(z).sum() - 1, 1e-9, 0.4)
print(f" overround={s:.4f}  proporzionale={np.round(prop, 4)}  potenza(k={k:.3f})={np.round(powr, 4)}  Shin(z={z:.4f})={np.round(shin_p(z), 4)}")

print("\n=== 7) Tempo rimanente: lineare vs CDF empirica (value_engine.goal_timing) ===")
import value_engine.goal_timing as gt
for t in (0, 30, 45, 60, 75, 85, 89):
    print(f" minuto {t:2d}: frazione rimasta FT lineare={(90 - t) / 90:.4f} CDF={gt.remaining_frac(t, 90):.4f}")
print(" quota gol primo tempo (cdf[45]) =", round(gt.first_half_share(), 4))

print("\n=== 8) Fit DixonColesModel su dati sintetici (recupero dei parametri) ===")
rng = np.random.default_rng(7)
nT = 12
att = rng.normal(0, 0.25, nT)
dfn = rng.normal(0, 0.25, nT)
c0, g0, r0 = 0.15, 0.25, -0.08
ms = []
ds = []
import datetime as dtm
base = dtm.datetime(2024, 1, 1, tzinfo=dtm.timezone.utc)
for day in range(0, 700, 1):
    h, a = rng.choice(nT, 2, replace=False)
    lh = math.exp(c0 + att[h] - dfn[a] + g0)
    la = math.exp(c0 + att[a] - dfn[h])
    M = dc.score_matrix(lh, la, r0, 12).ravel()
    kk = rng.choice(M.size, p=M / M.sum())
    x, y = divmod(kk, 13)
    ms.append(dc.MatchScoreline(int(h), int(a), int(x), int(y)))
    ds.append(base + dtm.timedelta(days=day))
mod = tm.DixonColesModel(max_goals=10, half_life_days=420.0, ridge=0.08)
fit = mod.fit(ms, dates=ds, ref_date=base + dtm.timedelta(days=701))
print(f" n={len(ms)} partite, {nT} squadre. home_adv vero={g0} stimato={fit.home_adv:.3f}; rho vero={r0} stimato={fit.rho:.3f}; converged={fit.converged}")
att_c = att - att.mean()
print(f" corr(attacco vero, stimato)={np.corrcoef(att_c, fit.attack)[0, 1]:.3f}; pendenza stima/vero={np.polyfit(att_c, fit.attack, 1)[0]:.3f} (ridge=0.08 + decadimento -> restringimento)")
