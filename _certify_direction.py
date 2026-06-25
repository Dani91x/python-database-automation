"""
_certify_direction.py — CERTIFICAZIONE money-critical della RPC get_direction.

Oracolo Python INDIPENDENTE che legge i motori dai json di fixture_predictions usando
le STESSE funzioni di normalizzazione della produzione (extract_poisson/ml/tacticai da
build_analytics_signals.py) + pagella + API (advice/under_over_line), e confronta
campo-per-campo con l'output della RPC, su un campione di partite CON e SENZA Poisson.

Mercati:
  - LEADER con fallback Poisson -> ML -> TacticAI -> API.
  - calibrated/poisson_missing: l'affidabilita' (e wilson/n/base/lift/scope) esiste SOLO
    quando c'e' Poisson + pagella; altrimenti NULL e calibrated=false.
  - API: 1x2 da advice ("Winner : <team>" -> H/A ; "Double chance ..." -> 1X/X2);
    over_1_5/2_5/3_5 da under_over_line ("+X.5"->Over, "-X.5"->Under, linea coincidente).

Zero mismatch tollerati. Uso: python _certify_direction.py
"""
import sys, math, re
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


def _coalesce(*xs):
    for x in xs:
        if x is not None: return x
    return None


# ---- API: advice (1x2) + under_over_line (over) — specchio della RPC ----
def parse_advice_1x2(advice, home, away):
    if not advice: return None
    main = re.sub(r'^Combo\s+', '', advice)
    main = re.sub(r'\s+and\s+[+-][0-9.]+\s+goals\s*$', '', main).strip()
    m = re.match(r'^Winner : (.*)$', main)
    if m:
        t = m.group(1).strip()
        return 'H' if t == home else 'A' if t == away else None
    m = re.match(r'^Double chance : (.*)$', main)
    if m:
        parts = m.group(1).split(' or ')
        a = parts[0].strip() if len(parts) > 0 else ''
        b = parts[1].strip() if len(parts) > 1 else ''
        if a == 'draw' and b == home: return '1X'
        if a == 'draw' and b == away: return 'X2'
        if b == 'draw' and a == home: return '1X'
        if b == 'draw' and a == away: return 'X2'
    return None


def parse_uol(uol):
    if not uol: return (None, None)
    s = uol.strip()
    d = 'Over' if s[:1] == '+' else 'Under' if s[:1] == '-' else None
    num = re.sub(r'[^0-9.]', '', s)
    return (d, float(num) if num else None)


def api_dir_for(mk, api1x2, uo_dir, uo_line):
    if mk == '1x2': return api1x2
    if mk == 'over_1_5': return uo_dir if uo_line == 1.5 else None
    if mk == 'over_2_5': return uo_dir if uo_line == 2.5 else None
    if mk == 'over_3_5': return uo_dir if uo_line == 3.5 else None
    return None


def oracle(fid, pag):
    fp = sb.table("fixture_predictions").select(
        "league_id,db_json_analisi,model_predictions_json,tactical_engine_json,flat_summary,"
        "home_team_name,away_team_name,advice,under_over_line"
    ).eq("fixture_id", fid).single().execute().data
    league = fp["league_id"]
    dj = fp["db_json_analisi"] or {}
    mp = fp["model_predictions_json"] or {}
    tj = fp["tactical_engine_json"] or {}
    home, away = fp.get("home_team_name"), fp.get("away_team_name")

    pois = engine_probs(extract_poisson(dj)) if (dj.get("markets_calibrated") or dj.get("markets")) else {}
    ml = engine_probs(extract_ml(mp)[0]) if mp.get("targets") else {}
    tac = engine_probs(extract_tacticai(tj)) if tj.get("markets") else {}

    api1x2 = parse_advice_1x2(fp.get("advice"), home, away)
    uo_dir, uo_line = parse_uol(fp.get("under_over_line"))

    out = {}
    for mk in PAG_MARKETS:
        pois_dir = amax(pois.get(mk))
        ml_dir = amax(ml.get(mk))
        tac_dir = amax(tac.get(mk))
        api_d = api_dir_for(mk, api1x2, uo_dir, uo_line)
        leader = _coalesce(pois_dir, ml_dir, tac_dir, api_d)
        if leader is None:
            continue  # nessun motore -> mercato assente

        has_pois, has_ml, has_tac = mk in pois, mk in ml, mk in tac

        # calibrazione: SOLO con Poisson + pagella per la direzione Poisson (=pois_dir).
        # Specchio ESATTO del CTE wil della RPC: calibrato sse affid e eff_n validi
        # (affid IS NOT NULL AND eff_n IS NOT NULL AND eff_n > 0).
        affid = wl = wh = base = lift = scope = None
        eff_n = None
        calibrated = False
        if pois_dir is not None:
            p = pois[mk][pois_dir]; bkt = bucket(p)
            pg = pag.get(("poisson", mk, pois_dir, 0, bkt))
            if pg and pg.get("hit_rate") is not None:
                hr_g = float(pg["hit_rate"])
                pl = pag.get(("poisson", mk, pois_dir, league, bkt)) if league is not None else None
                # ramo "lega" solo se la riga-lega ha n e hit_rate validi (come n_l IS NOT NULL)
                if pl and pl.get("n") is not None and pl.get("hit_rate") is not None:
                    n_l, hr_l = pl["n"], float(pl["hit_rate"])
                    affid = (n_l*hr_l + K*hr_g)/(n_l+K); eff_n = n_l + K; scope = "lega"
                else:
                    affid = hr_g; eff_n = pg.get("n"); scope = "globale"
                if affid is not None and eff_n is not None and eff_n > 0:
                    calibrated = True
                    wl, wh = wilson(affid, eff_n)
                    base = float(pg["base_rate"]) if pg.get("base_rate") is not None else None
                    lift = affid - base if base is not None else None
                else:
                    affid = eff_n = scope = None   # non calibrato -> campi null (come w.* NULL)

        conc = []
        if pois_dir == leader: conc.append("poisson")
        if ml_dir == leader: conc.append("ml")
        if tac_dir == leader: conc.append("tacticai")
        if api_d == leader: conc.append("api")
        tot = int(has_pois) + int(has_ml) + int(has_tac) + int(api_d is not None)

        ab = sb.table("analytics_bets").select("odds_betfair,odds_book").eq("fixture_id", fid).eq("market", mk).eq("selection", leader).limit(1).execute().data
        odds = None
        if ab:
            odds = ab[0]["odds_betfair"] if ab[0]["odds_betfair"] is not None else ab[0]["odds_book"]
            odds = float(odds) if odds is not None else None

        out[mk] = {
            "direction": leader, "calibrated": calibrated, "poisson_missing": not has_pois,
            "affidabilita": round(affid, 4) if affid is not None else None,
            "wilson_low": round(wl, 4) if wl is not None else None,
            "wilson_high": round(wh, 4) if wh is not None else None,
            "n": round(eff_n) if eff_n is not None else None,
            "base": round(base, 4) if base is not None else None,
            "lift": round(lift, 4) if lift is not None else None,
            "scope": scope, "odds": odds, "concordi": sorted(conc), "motori_totali": tot,
            "api_dir": api_d,
        }
    return out


def main():
    pag = load_pagella()
    # campione MISTO: con Poisson (db_json_analisi non-null) + senza Poisson (ML presente)
    with_p = sb.table("fixture_predictions").select("fixture_id").not_.is_("db_json_analisi","null") \
        .order("fixture_id", desc=True).limit(40).execute().data
    no_p = sb.table("fixture_predictions").select("fixture_id").is_("db_json_analisi","null") \
        .not_.is_("model_predictions_json","null").order("fixture_id", desc=True).limit(20).execute().data
    fids = list(dict.fromkeys([r["fixture_id"] for r in with_p] + [r["fixture_id"] for r in no_p]))[:50]

    CAL_FIELDS = ["affidabilita","wilson_low","wilson_high","n","base","lift","scope"]
    ALWAYS = ["direction","calibrated","poisson_missing","motori_totali"]
    total_mk, mism, n_deg = 0, 0, 0
    for fid in fids:
        rpc = sb.rpc("get_direction", {"p_fixture_id": fid}).execute().data
        rpc_mk = {m["market"]: m for m in rpc.get("markets", [])}
        ora = oracle(fid, pag)
        for mk, o in ora.items():
            total_mk += 1
            if not o["calibrated"]: n_deg += 1
            r = rpc_mk.get(mk)
            if not r:
                print(f"[{fid}] {mk}: oracolo SI, RPC NO"); mism += 1; continue
            for f in ALWAYS:
                if o[f] != r[f]:
                    print(f"[{fid}] {mk}.{f}: oracolo {o[f]} vs RPC {r[f]}"); mism += 1
            # campi calibrati: confronto solo se calibrato; altrimenti entrambi devono essere null
            for f in CAL_FIELDS:
                ov, rv = o[f], r.get(f)
                if ov is None or rv is None:
                    if (ov is None) != (rv is None):
                        print(f"[{fid}] {mk}.{f}: oracolo {ov} vs RPC {rv}"); mism += 1
                elif isinstance(ov, float) and isinstance(rv, (int, float)):
                    if abs(ov - rv) > 1.5e-3:
                        print(f"[{fid}] {mk}.{f}: oracolo {ov} vs RPC {rv}"); mism += 1
                elif ov != rv:
                    print(f"[{fid}] {mk}.{f}: oracolo {ov} vs RPC {rv}"); mism += 1
            if sorted(r["concordi"]) != o["concordi"]:
                print(f"[{fid}] {mk}.concordi: oracolo {o['concordi']} vs RPC {sorted(r['concordi'])}"); mism += 1
            # API dir
            r_api = (r.get("engines") or {}).get("api")
            r_api_dir = r_api.get("dir") if r_api else None
            if r_api_dir != o["api_dir"]:
                print(f"[{fid}] {mk}.api_dir: oracolo {o['api_dir']} vs RPC {r_api_dir}"); mism += 1
            oo, ro = o["odds"], r["odds"]
            if (oo is None) != (ro is None) or (oo is not None and abs(oo-ro) > 1e-6):
                print(f"[{fid}] {mk}.odds: oracolo {oo} vs RPC {ro}"); mism += 1
        for mk in rpc_mk:
            if mk not in ora: print(f"[{fid}] {mk}: RPC SI, oracolo NO"); mism += 1

    print(f"\nCERTIFICAZIONE: {len(fids)} partite, {total_mk} mercati ({n_deg} degradati/non-calibrati), {mism} mismatch.")
    print("ESITO:", "✅ CERTIFICATA — oracolo == RPC" if mism == 0 else "❌ MISMATCH presenti")


if __name__ == "__main__":
    main()
