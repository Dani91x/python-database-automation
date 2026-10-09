"""Sonda M3: analisi aggiuntive su m_dati.json (nessun DB): ML vs Poisson calibrato appaiati, firma di leakage
(partite con previsione generata DOPO il kickoff vs PRIMA), estremi dell'ML, perdita per lega-orario non disponibile."""
import os
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "m_misure.py"), encoding="utf-8").read()
exec(src.split("\nout = []\n")[0])  # importa solo helper e dati (nessun side effect di scrittura)
out = []


def bs_ci(d, idx):
    lo, hi = ci(d[idx].mean(1))
    return f"{d.mean():+.4f} [{lo:+.4f},{hi:+.4f}]{'*' if (lo > 0 or hi < 0) else ' '}"


def arrs(rows, which):
    return np.array([r[which] for r in rows])


out.append("# m_extra.py - output")
for mname in MK:
    rows, _ = build(mname)
    rml = [r for r in rows if r["ml"] is not None]
    Y = np.array([r["y"] for r in rml])
    n = len(rml)
    idx = RNG.integers(0, n, (NB, n))
    Q = np.array([dv_mult(r["o"]) for r in rml])
    PC, PR, ML = arrs(rml, "pc"), arrs(rml, "pr"), arrs(rml, "ml")
    L = {k: per_match(P, Y) for k, P in (("Q", Q), ("PC", PC), ("PR", PR), ("ML", ML))}
    out.append(f"\n## {mname} campione B n={n}: differenze APPAIATE (negativo = il primo e' meglio) [IC95 bootstrap 1000]")
    for a, b in (("ML", "PC"), ("ML", "PR"), ("PC", "PR")):
        s = f"{a} - {b}: logloss {bs_ci(L[a][0] - L[b][0], idx)}  Brier {bs_ci(L[a][1] - L[b][1], idx)}"
        if mname == "1X2":
            s += f"  RPS {bs_ci(L[a][2] - L[b][2], idx)}"
        out.append("  " + s)
    # estremi ML
    mlp = ML[:, 0]
    out.append(f"  ML estremi (classe 0): P<0.05: {(mlp < 0.05).sum()}  P>0.95: {(mlp > 0.95).sum()}  min={mlp.min():.4f} max={mlp.max():.4f} ; "
               f"Poisson cal min={PC[:, 0].min():.4f} max={PC[:, 0].max():.4f}; quote min={Q[:, 0].min():.4f} max={Q[:, 0].max():.4f}")
    ll_ml = L["ML"][0]
    top = np.argsort(-ll_ml)[:10]
    out.append(f"  10 peggiori logloss ML: somma={ll_ml[top].sum():.2f} su totale={ll_ml.sum():.2f} ({100 * ll_ml[top].sum() / ll_ml.sum():.1f}%); stessa quota per Q: "
               f"{100 * np.sort(L['Q'][0])[-10:].sum() / L['Q'][0].sum():.1f}%")
    # correlazione ML-Q e Poisson-Q (la previsione e' indipendente dalle quote?)
    out.append(f"  corr(classe0): ML-Q={np.corrcoef(ML[:, 0], Q[:, 0])[0, 1]:.3f} Pcal-Q={np.corrcoef(PC[:, 0], Q[:, 0])[0, 1]:.3f} ML-Pcal={np.corrcoef(ML[:, 0], PC[:, 0])[0, 1]:.3f} "
               f"Pgrezzo-Q={np.corrcoef(PR[:, 0], Q[:, 0])[0, 1]:.3f}")
    # firma leakage: previsioni generate dopo il kickoff vs prima
    post = np.array([(hrs(r["ml_gen"], r["kick"]) < 0) or (hrs(r["p_gen"], r["kick"]) < 0) for r in rml])
    out.append(f"  partite con ML o Poisson generato DOPO il kickoff: {post.sum()} su {n}; prima: {(~post).sum()}")
    for k in ("PC", "ML", "Q"):
        pass
    for k in ("PC", "ML"):
        dpost = (L[k][0] - L["Q"][0])[post]
        dpre = (L[k][0] - L["Q"][0])[~post]
        ipost = RNG.integers(0, len(dpost), (NB, len(dpost)))
        ipre = RNG.integers(0, len(dpre), (NB, len(dpre)))
        did = dpost[ipost].mean(1) - dpre[ipre].mean(1)
        lo, hi = ci(did)
        out.append(f"  {k}: d_logloss_vs_Q  post-kickoff={dpost.mean():+.4f} (n={post.sum()})  pre-kickoff={dpre.mean():+.4f} (n={(~post).sum()})  "
                   f"diff-in-diff={did.mean():+.4f} [{lo:+.4f},{hi:+.4f}] (negativo marcato = firma di leakage)")
    # ritardo di generazione: ore dal kickoff, sottogruppi: ML-vs-Q per classi di anticipo
    lead = np.array([hrs(r["ml_gen"], r["kick"]) for r in rml])
    for lo_, hi_ in ((-99, 0), (0, 3), (3, 8), (8, 99)):
        m = (lead >= lo_) & (lead < hi_)
        if m.sum() >= 30:
            out.append(f"  anticipo ML [{lo_},{hi_})h n={m.sum()}: logloss Q={L['Q'][0][m].mean():.4f} PC={L['PC'][0][m].mean():.4f} ML={L['ML'][0][m].mean():.4f}")
txt = "\n".join(out)
print(txt)
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "m_extra_output.txt"), "w", encoding="utf-8").write(txt)
