"""
_certify_direction.py — CERTIFICAZIONE money-critical della RPC get_direction.

Oracolo Python INDIPENDENTE (ricalcola da pagella + bet_features) confrontato campo-per-campo
con l'output della RPC, su un campione di partite (in programma + giocate).
Zero mismatch tollerati su: affidabilita, wilson, n, base, lift, odds, scope, concordanza.

Uso: python _certify_direction.py
"""
import sys, math
sys.stdout.reconfigure(encoding="utf-8")
import pandas as pd
from db_client import get_supabase_client

K, Z = 50.0, 1.96
MK = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]
sb = get_supabase_client()


def bucket(p):
    if p is None: return None
    for lo, hi, l in zip([0,.3,.4,.5,.6,.7], [.3,.4,.5,.6,.7,1.01],
                         ['<.30','.30-.40','.40-.50','.50-.60','.60-.70','>.70']):
        if lo <= p < hi: return l
    return '>.70' if p >= .7 else None


def load_pagella():
    rows, start = [], 0
    while True:
        d = sb.table("direction_pagella").select("*").order("engine").range(start, start+999).execute().data
        rows += d
        if len(d) < 1000: break
        start += 1000
    return {(r["engine"], r["market"], r["selection"], r["league_id"], r["prob_bucket"]): r for r in rows}


def wilson(p, n):
    wc = (p + Z*Z/(2*n)) / (1 + Z*Z/n)
    wh = Z*math.sqrt(p*(1-p)/n + Z*Z/(4*n*n)) / (1 + Z*Z/n)
    return max(0, wc-wh), min(1, wc+wh)


def oracle(fid, pag):
    league = sb.table("fixture_predictions").select("league_id").eq("fixture_id", fid).limit(1).execute().data
    league = league[0]["league_id"] if league else None
    bf = sb.table("bet_features").select(
        "market,selection,poisson_prob,ml_prob,tacticai_prob,api_home,api_draw,api_away,api_over_line,odds"
    ).eq("fixture_id", fid).in_("market", MK).execute().data
    df = pd.DataFrame(bf)
    if df.empty: return {}
    for c in ["poisson_prob","ml_prob","tacticai_prob","api_home","api_draw","api_away","api_over_line","odds"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    out = {}
    for mk, g in df.groupby("market"):
        gp = g[g.poisson_prob.notna()]
        if gp.empty: continue
        # rispecchia la RPC: ORDER BY pp DESC, selection
        drow = gp.sort_values(["poisson_prob", "selection"], ascending=[False, True]).iloc[0]
        d, p = drow.selection, float(drow.poisson_prob)
        bkt = bucket(p)
        pg = pag.get(("poisson", mk, d, 0, bkt))
        if not pg: continue
        pl = pag.get(("poisson", mk, d, league, bkt)) if league is not None else None
        if pl:
            n_l, hr_l, hr_g = pl["n"], float(pl["hit_rate"]), float(pg["hit_rate"])
            affid = (n_l*hr_l + K*hr_g)/(n_l+K); eff_n = n_l + K; scope = "lega"
        else:
            affid = float(pg["hit_rate"]); eff_n = pg["n"]; scope = "globale"
        wl, wh = wilson(affid, eff_n)
        base = float(pg["base_rate"])
        # concordanza
        def amax(col):
            s = g[g[col].notna()]
            return s.loc[s[col].idxmax()].selection if not s.empty else None
        api_dir = None
        if mk in ("1x2","ht_1x2"):
            av = {"H": g.api_home.dropna(), "D": g.api_draw.dropna(), "A": g.api_away.dropna()}
            av = {k: float(v.iloc[0]) for k, v in av.items() if len(v)}
            if av:  # solo vincitore NETTO; pareggio -> None (come la RPC)
                mx = max(av.values())
                winners = [k for k, v in av.items() if v == mx]
                api_dir = winners[0] if len(winners) == 1 else None
        else:
            ol = g.api_over_line.dropna()
            if len(ol): api_dir = "Over" if float(ol.iloc[0]) > 50 else "Under"
        conc = []
        if amax("poisson_prob") == d: conc.append("poisson")
        if amax("ml_prob") == d: conc.append("ml")
        if amax("tacticai_prob") == d: conc.append("tacticai")
        if api_dir == d: conc.append("api")
        tot = 1 + int(g.ml_prob.notna().any()) + int(g.tacticai_prob.notna().any()) + int((g.api_home.notna()|g.api_over_line.notna()).any())
        odds = drow.odds
        out[mk] = {"direction": d, "affidabilita": round(affid,4), "wilson_low": round(wl,4),
                   "wilson_high": round(wh,4), "n": round(eff_n), "base": round(base,4),
                   "lift": round(affid-base,4), "odds": None if pd.isna(odds) else float(odds),
                   "scope": scope, "concordi": sorted(conc), "motori_totali": tot}
    return out


def main():
    pag = load_pagella()
    # campione: partite in programma + giocate
    sched = sb.table("bet_features").select("fixture_id").eq("settled", False).not_.is_("poisson_prob","null").limit(800).execute().data
    setl  = sb.table("bet_features").select("fixture_id").eq("settled", True).not_.is_("poisson_prob","null").order("fixture_id", desc=True).limit(800).execute().data
    fids = list(dict.fromkeys([r["fixture_id"] for r in sched] + [r["fixture_id"] for r in setl]))[:35]

    total_mk, mism = 0, 0
    for fid in fids:
        rpc = sb.rpc("get_direction", {"p_fixture_id": fid}).execute().data
        rpc_mk = {m["market"]: m for m in rpc.get("markets", [])}
        ora = oracle(fid, pag)
        for mk, o in ora.items():
            total_mk += 1
            r = rpc_mk.get(mk)
            if not r:
                print(f"[{fid}] {mk}: presente nell'oracolo ma NON nella RPC"); mism += 1; continue
            for f in ["direction","affidabilita","wilson_low","wilson_high","n","base","lift","scope","motori_totali"]:
                ov, rv = o[f], r[f]
                if isinstance(ov, float) and isinstance(rv, (int,float)):
                    if abs(ov - rv) > 1.5e-3: print(f"[{fid}] {mk}.{f}: oracolo {ov} vs RPC {rv}"); mism += 1
                elif ov != rv:
                    print(f"[{fid}] {mk}.{f}: oracolo {ov} vs RPC {rv}"); mism += 1
            if sorted(r["concordi"]) != o["concordi"]:
                print(f"[{fid}] {mk}.concordi: oracolo {o['concordi']} vs RPC {sorted(r['concordi'])}"); mism += 1
            oo, ro = o["odds"], r["odds"]
            if (oo is None) != (ro is None) or (oo is not None and abs(oo-ro) > 1e-6):
                print(f"[{fid}] {mk}.odds: oracolo {oo} vs RPC {ro}"); mism += 1
        # mercati nella RPC ma non nell'oracolo
        for mk in rpc_mk:
            if mk not in ora: print(f"[{fid}] {mk}: nella RPC ma NON nell'oracolo"); mism += 1

    print(f"\nCERTIFICAZIONE: {len(fids)} partite, {total_mk} mercati confrontati, {mism} mismatch.")
    print("ESITO:", "✅ CERTIFICATA — oracolo == RPC" if mism == 0 else "❌ MISMATCH presenti")


if __name__ == "__main__":
    main()
