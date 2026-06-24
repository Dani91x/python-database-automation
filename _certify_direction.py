"""
_certify_direction.py — CERTIFICAZIONE money-critical della RPC get_direction.

Oracolo Python INDIPENDENTE che legge i motori dai json di fixture_predictions usando
le STESSE funzioni di normalizzazione della produzione (extract_poisson/ml/tacticai da
build_analytics_signals.py) + pagella + flat_summary per l'API, e confronta campo-per-campo
con l'output della RPC, su un campione di partite (in programma + giocate).
Zero mismatch tollerati: affidabilita, wilson, n, base, lift, scope, concordanza, odds, motori.

Uso: python _certify_direction.py
"""
import sys, math
sys.stdout.reconfigure(encoding="utf-8")
from db_client import get_supabase_client
from build_analytics_signals import extract_poisson, extract_ml, extract_tacticai

K, Z = 50.0, 1.96
PAG_MARKETS = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]
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


def engine_probs(extracted):
    """{market: {selection: prob}} per i soli PAG_MARKETS, scartando prob None."""
    out = {}
    for mk in PAG_MARKETS:
        sels = extracted.get(mk)
        if not sels: continue
        clean = {s: float(p) for s, (p, _) in sels.items() if p is not None}
        if clean: out[mk] = clean
    return out


def amax(d):  # argmax: prob piu' alta, tiebreak selezione ASC (come la RPC)
    if not d: return None
    return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def oracle(fid, pag):
    fp = sb.table("fixture_predictions").select(
        "league_id,db_json_analisi,model_predictions_json,tactical_engine_json,flat_summary"
    ).eq("fixture_id", fid).single().execute().data
    league = fp["league_id"]
    dj = fp["db_json_analisi"] or {}
    mp = fp["model_predictions_json"] or {}
    tj = fp["tactical_engine_json"] or {}
    fs = fp["flat_summary"] or {}

    pois = engine_probs(extract_poisson(dj)) if (dj.get("markets_calibrated") or dj.get("markets")) else {}
    ml = engine_probs(extract_ml(mp)[0]) if mp.get("targets") else {}
    tac = engine_probs(extract_tacticai(tj)) if tj.get("markets") else {}
    ph = fs.get("percent_home"); pd_ = fs.get("percent_draw"); pa = fs.get("percent_away")
    ph = float(ph) if ph is not None else None
    pd_ = float(pd_) if pd_ is not None else None
    pa = float(pa) if pa is not None else None

    out = {}
    for mk in PAG_MARKETS:
        if mk not in pois: continue
        d = amax(pois[mk]); p = pois[mk][d]
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
        api_dir, has_api = None, False
        if mk == "1x2":  # API = solo 1x2 a tempo pieno (flat_summary.percent_*); niente HT
            vals = {"H": ph, "D": pd_, "A": pa}
            present = {k: v for k, v in vals.items() if v is not None}
            has_api = len(present) > 0
            if present:
                mx = max(present.values())
                win = [k for k, v in present.items() if v == mx]
                api_dir = win[0] if len(win) == 1 else None
        conc = []
        if amax(pois.get(mk)) == d: conc.append("poisson")
        if amax(ml.get(mk)) == d: conc.append("ml")
        if amax(tac.get(mk)) == d: conc.append("tacticai")
        if api_dir == d: conc.append("api")
        tot = 1 + int(mk in ml) + int(mk in tac) + int(has_api)
        # odds best-effort da analytics_bets
        ab = sb.table("analytics_bets").select("odds_betfair,odds_book").eq("fixture_id", fid).eq("market", mk).eq("selection", d).limit(1).execute().data
        odds = None
        if ab:
            odds = ab[0]["odds_betfair"] if ab[0]["odds_betfair"] is not None else ab[0]["odds_book"]
            odds = float(odds) if odds is not None else None
        out[mk] = {"direction": d, "affidabilita": round(affid,4), "wilson_low": round(wl,4),
                   "wilson_high": round(wh,4), "n": round(eff_n), "base": round(base,4),
                   "lift": round(affid-base,4), "odds": odds, "scope": scope,
                   "concordi": sorted(conc), "motori_totali": tot}
    return out


def main():
    pag = load_pagella()
    sched = sb.table("fixture_predictions").select("fixture_id").not_.is_("db_json_analisi","null").order("fixture_id", desc=True).limit(60).execute().data
    fids = list(dict.fromkeys(r["fixture_id"] for r in sched))[:40]

    total_mk, mism = 0, 0
    for fid in fids:
        rpc = sb.rpc("get_direction", {"p_fixture_id": fid}).execute().data
        rpc_mk = {m["market"]: m for m in rpc.get("markets", [])}
        ora = oracle(fid, pag)
        for mk, o in ora.items():
            total_mk += 1
            r = rpc_mk.get(mk)
            if not r:
                print(f"[{fid}] {mk}: oracolo SI, RPC NO"); mism += 1; continue
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
        for mk in rpc_mk:
            if mk not in ora: print(f"[{fid}] {mk}: RPC SI, oracolo NO"); mism += 1

    print(f"\nCERTIFICAZIONE: {len(fids)} partite, {total_mk} mercati confrontati, {mism} mismatch.")
    print("ESITO:", "✅ CERTIFICATA — oracolo == RPC" if mism == 0 else "❌ MISMATCH presenti")


if __name__ == "__main__":
    main()
