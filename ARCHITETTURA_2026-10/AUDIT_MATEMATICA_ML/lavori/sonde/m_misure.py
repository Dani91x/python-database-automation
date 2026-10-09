"""Sonda M2: misure (logloss, Brier, RPS, ECE, affidabilita', bootstrap) su m_dati.json (nessun accesso al DB).
Confronta: quote de-viggate (molt., power, Shin), Poisson grezzo, Poisson calibrato, ML servito, climatologia,
miscele 50/50 quote+ML e quote+Poisson. Bootstrap 1000 ricampionamenti sulle differenze vs quote (molt.)."""
import json, os
import datetime as dt
import numpy as np
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "m_dati.json")))
RNG = np.random.default_rng(20261009)
NB = 1000
EPS = 1e-12


# ---------- de-vig ----------
def dv_mult(o):
    p = 1.0 / np.asarray(o, float)
    return p / p.sum()


def dv_power(o):
    p = 1.0 / np.asarray(o, float)
    if p.sum() <= 1.0:
        return p / p.sum()
    lo, hi = 1.0, 20.0
    for _ in range(80):
        k = (lo + hi) / 2
        if (p ** k).sum() > 1:
            lo = k
        else:
            hi = k
    q = p ** ((lo + hi) / 2)
    return q / q.sum()


def dv_shin(o):
    pi = 1.0 / np.asarray(o, float)
    S = pi.sum()
    if S <= 1.0:
        return pi / S

    def comp(z):
        return (np.sqrt(z * z + 4 * (1 - z) * pi * pi / S) - z) / (2 * (1 - z))

    lo, hi = 0.0, 0.999
    for _ in range(80):
        z = (lo + hi) / 2
        if comp(z).sum() > 1:
            lo = z
        else:
            hi = z
    q = comp((lo + hi) / 2)
    return q / q.sum()


def okodds(d, names):
    if not d:
        return None
    v = [d.get(n) for n in names]
    return v if all(x and x > 1.0 for x in v) else None


def vec(dct, keys):
    if not isinstance(dct, dict):
        return None
    try:
        v = [float(dct[k]) for k in keys]
    except (KeyError, TypeError, ValueError):
        return None
    s = sum(v)
    if not (0.5 < s < 1.5):
        return None
    return np.array(v) / s


MK = {
    "1X2": dict(keys=["H", "D", "A"], pm="1x2", ml="ml1", odds=lambda r: okodds(r.get("o1x2"), ["Home", "Draw", "Away"]),
                y=lambda h, a: [h > a, h == a, h < a]),
    "O25": dict(keys=["True", "False"], pm="over_2_5", ml="mlo", odds=lambda r: okodds(r.get("oou"), ["Over 2.5", "Under 2.5"]),
                y=lambda h, a: [h + a > 2.5, h + a < 2.5]),
    "BTTS": dict(keys=["True", "False"], pm="btts", ml="mlb", odds=lambda r: okodds(r.get("obt"), ["Yes", "No"]),
                 y=lambda h, a: [h > 0 and a > 0, not (h > 0 and a > 0)]),
}


def parse(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None


def hrs(a, b):
    """ore tra a e b (b - a); None se manca uno dei due."""
    return (parse(b) - parse(a)).total_seconds() / 3600 if a and b else None


def build(mname):
    c = MK[mname]
    rows = []
    sk = Counter()
    for r in D:
        h, a = r["result_home_goals"], r["result_away_goals"]
        if h is None or a is None:
            sk["senza_risultato"] += 1
            continue
        o = c["odds"](r)
        pr = vec((r.get("m") or {}).get(c["pm"]), c["keys"])
        pc = vec((r.get("mc") or {}).get(c["pm"]), c["keys"])
        ml = None
        if r.get(c["ml"]) is not None:
            ml = vec(r[c["ml"]], c["keys"])
            if ml is None:
                sk["ml_scala_o_chiavi_anomali"] += 1
        if o is None:
            sk["senza_quote_mercato"] += 1
            continue
        if pr is None or pc is None:
            sk["senza_poisson"] += 1
            continue
        rows.append(dict(fid=r["fixture_id"], o=np.array(o, float), pr=pr, pc=pc, ml=ml, y=np.array(c["y"](h, a), float),
                         kick=r["fixture_date"], p_gen=r.get("p_gen"), p_cal=r.get("p_cal"), ml_gen=r.get("ml_gen")))
    return rows, sk


def per_match(P, Y):
    ll = -np.log(np.clip((P * Y).sum(1), EPS, 1))
    if P.shape[1] == 3:
        br = ((P - Y) ** 2).sum(1)
        c = np.cumsum(P, 1) - np.cumsum(Y, 1)
        rp = (c[:, :-1] ** 2).sum(1) / 2
    else:
        br = (P[:, 0] - Y[:, 0]) ** 2
        rp = np.full(len(P), np.nan)
    return ll, br, rp


def ece(P, Y, idx=None):
    """ECE a 10 bin equidistanti; 1X2: media sulle 3 classi one-vs-rest; binario: classe positiva."""
    if idx is not None:
        P, Y = P[idx], Y[idx]
    ks = list(range(P.shape[1])) if P.shape[1] == 3 else [0]
    tot = 0.0
    for k in ks:
        p, y = P[:, k], Y[:, k]
        b = np.minimum((p * 10).astype(int), 9)
        n = np.bincount(b, minlength=10)
        sp = np.bincount(b, p, 10)
        sy = np.bincount(b, y, 10)
        m = n > 0
        tot += np.abs(sp[m] - sy[m]).sum() / len(p)
    return tot / len(ks)


def reliab(P, Y):
    if P.shape[1] == 3:
        p, y = P.ravel(), Y.ravel()
    else:
        p, y = P[:, 0], Y[:, 0]
    b = np.minimum((p * 10).astype(int), 9)
    out = []
    for i in range(10):
        m = b == i
        out.append((int(m.sum()), float(p[m].mean()) if m.any() else float("nan"), float(y[m].mean()) if m.any() else float("nan")))
    return out


def fmt_rel(rel):
    return " ".join(f"[{i/10:.1f}]{pm:.2f}>{ym:.2f}({n})" if n else f"[{i/10:.1f}]-" for i, (n, pm, ym) in enumerate(rel))


def ci(x):
    return np.percentile(x, [2.5, 97.5])


def report(mname, rows, out, label):
    k = len(MK[mname]["keys"])
    n = len(rows)
    Y = np.array([r["y"] for r in rows])
    O = np.array([r["o"] for r in rows])
    models = {}
    models["Q molt."] = np.array([dv_mult(o) for o in O])
    models["Q power"] = np.array([dv_power(o) for o in O])
    models["Q Shin"] = np.array([dv_shin(o) for o in O])
    models["Poisson grezzo"] = np.array([r["pr"] for r in rows])
    models["Poisson calibr."] = np.array([r["pc"] for r in rows])
    has_ml = all(r["ml"] is not None for r in rows)
    if has_ml:
        models["ML servito"] = np.array([r["ml"] for r in rows])
    base = Y.mean(0)
    models["Climatologia"] = np.tile(base, (n, 1))
    if has_ml:
        models["50/50 Q+ML"] = 0.5 * models["Q molt."] + 0.5 * models["ML servito"]
    models["50/50 Q+Poisson calibr."] = 0.5 * models["Q molt."] + 0.5 * models["Poisson calibr."]
    models["50/50 Q+Poisson grezzo"] = 0.5 * models["Q molt."] + 0.5 * models["Poisson grezzo"]
    if has_ml:
        models["1/3 Q+ML+Pcal"] = (models["Q molt."] + models["ML servito"] + models["Poisson calibr."]) / 3
    out.append(f"\n### {mname} - campione {label} - n={n} - tassi base {MK[mname]['keys']}: {np.round(base, 4).tolist()}")
    L = {m: per_match(P, Y) for m, P in models.items()}
    E = {m: ece(P, Y) for m, P in models.items()}
    ref = "Q molt."
    idx = RNG.integers(0, n, (NB, n))
    out.append(f"{'modello':24s} {'logloss':>8s} {'Brier':>8s} {'RPS':>8s} {'ECE10':>7s} | d_logloss vs Q [IC95] | d_Brier vs Q [IC95] | d_RPS vs Q [IC95] | d_ECE vs Q [IC95]")
    for m, P in models.items():
        ll, br, rp = L[m]
        rps_s = f"{np.nanmean(rp):8.4f}" if k == 3 else f"{'-':>8s}"
        row = f"{m:24s} {ll.mean():8.4f} {br.mean():8.4f} {rps_s} {E[m]:7.4f} |"
        if m != ref:
            for j, (arr, rarr) in enumerate(((ll, L[ref][0]), (br, L[ref][1]), (rp, L[ref][2]))):
                if j == 2 and k != 3:
                    continue
                d = arr - rarr
                lo, hi = ci(d[idx].mean(1))
                sig = "*" if (lo > 0 or hi < 0) else " "
                row += f" {d.mean():+.4f} [{lo:+.4f},{hi:+.4f}]{sig} |"
            be = np.array([ece(P, Y, ix) - ece(models[ref], Y, ix) for ix in idx])
            lo, hi = ci(be)
            sig = "*" if (lo > 0 or hi < 0) else " "
            row += f" {E[m]-E[ref]:+.4f} [{lo:+.4f},{hi:+.4f}]{sig}"
        out.append(row)
    out.append("(* = IC95 bootstrap esclude lo zero; d>0 = peggio delle quote molt.; bootstrap iid su partite, 1000 ricampionamenti, seed 20261009)")
    out.append("curva di affidabilita' [bin]pred>osservato(n):")
    for m in ["Q molt.", "Poisson grezzo", "Poisson calibr.", "ML servito"]:
        if m in models:
            out.append(f"  {m:16s} " + fmt_rel(reliab(models[m], Y)))
    ws = np.linspace(0, 1, 11)
    for other in (["ML servito"] if has_ml else []) + ["Poisson calibr."]:
        Po, Q = models[other], models["Q molt."]
        curve = [per_match(w * Po + (1 - w) * Q, Y)[0].mean() for w in ws]
        wb = ws[int(np.argmin(curve))]
        perm = RNG.permutation(n)
        folds = np.array_split(perm, 5)
        cvll = np.zeros(n)
        for f in folds:
            tr = np.setdiff1d(perm, f)
            cv = [per_match(w * Po[tr] + (1 - w) * Q[tr], Y[tr])[0].mean() for w in ws]
            w_ = ws[int(np.argmin(cv))]
            cvll[f] = per_match(w_ * Po[f] + (1 - w_) * Q[f], Y[f])[0]
        d = cvll - L[ref][0]
        lo, hi = ci(d[idx].mean(1))
        out.append(f"miscela Q+{other}: logloss per w={{0..1 passo .1}} (w=peso di {other}): {np.round(curve, 4).tolist()} w*={wb:.1f} (in-sample); "
                   f"CV5 logloss={cvll.mean():.4f} d_vs_Q={d.mean():+.4f} [{lo:+.4f},{hi:+.4f}]")
    return models


out = []
out.append("# m_misure.py - output (partite FT 21/09-07/10/2026 con db_json_analisi e raw_json_odds, da m_dati.json)")
out.append(f"righe totali estratte: {len(D)}")
out.append("\n## Leakage temporale (kickoff = fixture_date)")
for lab, key in (("Poisson db_json_analisi.generated_at", "p_gen"), ("Poisson calibrato calibrated_at", "p_cal"),
                 ("ML model_predictions_json.generated_at", "ml_gen"), ("riga created_at", "created_at"), ("riga updated_at", "updated_at")):
    v = np.array([hrs(r.get(key), r["fixture_date"]) for r in D if r.get(key)])
    nn = sum(1 for r in D if not r.get(key))
    out.append(f"{lab:40s} n={len(v)} mancanti={nn} ore PRIMA del kickoff: min={v.min():.2f} p5={np.percentile(v, 5):.2f} p25={np.percentile(v, 25):.2f} "
               f"med={np.median(v):.2f} p75={np.percentile(v, 75):.2f} max={v.max():.2f}; DOPO il kickoff: {(v < 0).sum()} ({100 * (v < 0).mean():.1f}%); entro 1h prima: {((v >= 0) & (v < 1)).sum()}")
bad = [r for r in D if r.get("ml_gen") and hrs(r["ml_gen"], r["fixture_date"]) < 0]
out.append(f"ML generato dopo il kickoff: {len(bad)} partite; esempi (fid, kickoff, ml_gen): " + str([(r['fixture_id'], r['fixture_date'], r['ml_gen']) for r in bad[:4]]))
out.append(f"Poisson (generated_at) dopo il kickoff: {sum(1 for r in D if r.get('p_gen') and hrs(r['p_gen'], r['fixture_date']) < 0)}; "
           f"calibrato dopo il kickoff: {sum(1 for r in D if r.get('p_cal') and hrs(r['p_cal'], r['fixture_date']) < 0)}")
out.append(f"Partite senza ML (targets assente): {sum(1 for r in D if r.get('ml1') is None)} su {len(D)}")
out.append(f"Modello Poisson: {dict(Counter(r.get('p_model') for r in D))}; bookmaker usato per le quote: {dict(Counter(r.get('book') for r in D))}")
out.append("Quote: raw_json_odds ha la chiave 'update' ma NON e' stata estratta (budget 8 query esaurito): timestamp delle quote NON VERIFICATO.")
mlo = [r["mlo"]["True"] for r in D if r.get("mlo")]
mlb = [r["mlb"]["True"] for r in D if r.get("mlb")]
out.append(f"Diagnostica ML: P(Over2.5) distinti={len(set(round(x, 4) for x in mlo))}/{len(mlo)} std={np.std(mlo):.4f} top={Counter(round(x, 4) for x in mlo).most_common(3)}; "
           f"P(BTTS) distinti={len(set(round(x, 4) for x in mlb))}/{len(mlb)} std={np.std(mlb):.4f} top={Counter(round(x, 4) for x in mlb).most_common(3)}")

for mname in MK:
    rows, sk = build(mname)
    out.append(f"\n## {mname}: righe valide (quote+Poisson grezzo+calibrato)={len(rows)}; scartate/anomalie={dict(sk)}")
    report(mname, [dict(r, ml=None) for r in rows], out, "A: tutte con quote+Poisson (ML non richiesto)")
    rml = [r for r in rows if r["ml"] is not None]
    out.append(f"partite senza ML (escluse dal campione B, non riempite): {len(rows) - len(rml)}")
    report(mname, rml, out, "B: campione comune con ML")

    def pre(r, h=0.0):
        return all((hrs(r[k], r["kick"]) is not None and hrs(r[k], r["kick"]) > h) for k in ("ml_gen", "p_gen", "p_cal"))

    clean = [r for r in rml if pre(r)]
    out.append(f"di B con ML, Poisson e calibrato tutti generati prima del kickoff: {len(clean)} su {len(rml)}")
    if len(clean) != len(rml) and len(clean) > 100:
        report(mname, clean, out, "C: solo previsioni pre-kickoff")
    c3 = [r for r in clean if pre(r, 3.0)]
    out.append(f"di cui generate >=3h prima del kickoff: {len(c3)}")
    if len(c3) > 100 and len(c3) != len(clean):
        report(mname, c3, out, "D: previsioni generate >=3h prima del kickoff")
txt = "\n".join(out)
print(txt)
open(os.path.join(HERE, "m_misure_output.txt"), "w", encoding="utf-8").write(txt)
