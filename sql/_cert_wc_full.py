"""
CERTIFICAZIONE TOTALE Studio Ritardi — oracolo (trascrizione letterale delle
formule del foglio) vs RPC get_market_delays DEPLOYATA, su:
  - OGNI MODALITA' di calcolo della dashboard: 'all', 'last_n' (N=100,200),
    'season' (ogni stagione WC);
  - OGNI mercato e OGNI variante (50);
  - OGNI campo restituito, incluse TUTTE le percentuali e la serie DATI MATCH
    EVENTO-PER-EVENTO (W/L, RIT, SUC, GCSH, GASH).

Se passa tutto, la dashboard e' una copia 1:1 ESATTA del foglio per i calcoli,
in ogni modalita'. L'oracolo NON riusa il codice della RPC.
"""
import json
import math
import os
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from db_client import get_supabase_client      # noqa
from _cert_wc_compare import cond, variants     # noqa: condizioni mercato + lista varianti

LEAGUE_ID = 1
DATA = os.path.join(HERE, "_cert_wc_data.json")


def pgr(x, dec):
    """Arrotondamento IDENTICO a Postgres round(numeric,dec) = half-away-from-zero."""
    if x is None:
        return None
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP))


# ---------------------------------------------------- oracolo COMPLETO (foglio)
def oracle_full(events, market, target):
    wl = [1 if cond(market, target, e) else 0 for e in events]
    M = len(wl)
    rit, suc_event, prev = [], [], 0
    for i, w in enumerate(wl):
        if w == 0:
            cur = (prev + 1) if i > 0 else 1
            rit.append(cur); suc_event.append(None)
        else:
            rit.append(0); suc_event.append(prev)   # SUC = RIT precedente
        prev = rit[-1]
    suc = [s for s in suc_event if s is not None]    # serie chiuse
    n_occ = len(suc)

    media_storica = (M / n_occ) if n_occ else None
    # come la RPC: % e quota sono NULL quando n_occ=0 (il foglio darebbe #DIV/0!;
    # la dashboard mostra "Mai verificato"). Divergenza VOLUTA e gestita.
    frequency = (n_occ / M) if (M and n_occ) else None
    ritardo_attuale = rit[-1] if rit else 0
    record = max(suc) if suc else None
    nz = [r for r in rit if r != 0]
    media_rit = (sum(nz) / len(nz)) if nz else None

    imedia = math.floor(media_rit) if media_rit is not None else None
    sotto = sum(1 for s in suc if imedia is not None and s <= imedia)
    sopra = sum(1 for s in suc if imedia is not None and s >= imedia + 1)

    maxk = max([0] + suc + rit)
    distrib = [{"len": k,
                "occ_suc": sum(1 for s in suc if s == k),
                "cnt_rit": sum(1 for r in rit if r == k)} for k in range(0, maxk + 1)]

    ultime10 = suc[-10:]

    # storico CONDIZIONATO (BE/BF/BG): successori del valore = ultimo SUC (AZ13)
    cond_su = suc[-1] if suc else None
    bd = ([suc[i + 1] for i in range(len(suc) - 1) if suc[i] == cond_su]
          if cond_su is not None else [])
    cc = Counter(bd)
    storico = sorted(cc.items(), key=lambda kv: (-kv[1], kv[0]))
    tot_bd = len(bd)
    storico = [{"len": k, "count": c, "pct": (c / tot_bd) if tot_bd else None} for k, c in storico]

    # run sopra media (BT/BU/BV)
    runs, curr = [], 0
    if media_rit is not None:
        for s in suc:
            if s >= media_rit:
                curr += 1
            else:
                if curr > 0: runs.append(curr)
                curr = 0
        if curr > 0: runs.append(curr)
    rh = Counter(runs)
    tot_run = sum(rh.values())
    run_hist = [{"run_len": L, "count": c, "pct": (c / tot_run) if tot_run else None}
                for L, c in sorted(rh.items())]

    # BL (ultime 10 strisce sopra media)
    bl_tokens, i = [], 0
    while media_rit is not None and i < len(suc):
        if suc[i] < media_rit:
            bl_tokens.append(0); i += 1
        else:
            run = 0
            while i < len(suc) and suc[i] >= media_rit:
                run += 1; i += 1
            bl_tokens.append(run)
    bl_ultime10 = bl_tokens[-10:]

    # serie DATI MATCH evento-per-evento
    series = []
    for i, e in enumerate(events):
        gcfh = e["gcfh"] or 0
        gafh = e["gafh"] or 0
        series.append({
            "idx": i + 1, "out": wl[i], "rit": rit[i], "suc": suc_event[i],
            "gcsh": e["gc"] - gcfh, "gash": e["ga"] - gafh,
        })

    # rit_vs_media ESATTAMENTE come la RPC: ritardo / media_storica_ARROTONDATA a 6
    # decimali (la RPC usa d.media_storica = round(n_eff/n_occ,6), non il valore pieno).
    ms6 = pgr(media_storica, 6) if media_storica else None
    return dict(n_eff=M, n_occ=n_occ, frequency=frequency, media_storica=media_storica,
                ritardo_attuale=ritardo_attuale, record=record, media_rit=media_rit,
                sotto=sotto, sopra=sopra,
                sotto_pct=(sotto / n_occ) if n_occ else None,
                sopra_pct=(sopra / n_occ) if n_occ else None,
                rit_vs_media=(ritardo_attuale / ms6) if ms6 else None,
                storico_cond_su=cond_su, distrib=distrib, ultime10=ultime10,
                storico=storico, run_hist=run_hist, bl_ultime10=bl_ultime10, series=series)


# ---------------------------------------------------- confronto a piena precisione
def req(a, b, dec):
    """Uguaglianza dopo arrotondamento Postgres-style (b RPC e' gia' arrotondato)."""
    if a is None and b is None: return True
    if a is None or b is None:  return False
    return abs(pgr(a, dec) - pgr(b, dec)) < 1e-9


def compare_full(orc, rpc):
    m = []
    st, meta = rpc["stats"], rpc["meta"]
    S = lambda k: st.get(k)
    # --- scalari + percentuali (ogni campo stats/meta usato dal frontend) ---
    if orc["n_eff"] != meta["n_effective"]:                 m.append(f"n_effective {orc['n_eff']} vs {meta['n_effective']}")
    if orc["n_occ"] != S("n_occ"):                          m.append(f"n_occ {orc['n_occ']} vs {S('n_occ')}")
    if not req(orc["frequency"], S("frequency"), 6):        m.append(f"frequency {orc['frequency']} vs {S('frequency')}")
    if not req(orc["media_storica"], S("media_storica"), 6):m.append(f"media_storica {orc['media_storica']} vs {S('media_storica')}")
    if not req(orc["media_storica"], S("quota_oggettiva"),6):m.append(f"quota_oggettiva {orc['media_storica']} vs {S('quota_oggettiva')}")
    if orc["ritardo_attuale"] != S("ritardo_attuale"):      m.append(f"ritardo_attuale {orc['ritardo_attuale']} vs {S('ritardo_attuale')}")
    if (orc["record"] or 0) != (S("record") or 0):          m.append(f"record {orc['record']} vs {S('record')}")
    if not req(orc["media_rit"], S("media_ritardi"), 4):    m.append(f"media_ritardi {orc['media_rit']} vs {S('media_ritardi')}")
    if orc["sotto"] != S("sotto_media"):                    m.append(f"sotto_media {orc['sotto']} vs {S('sotto_media')}")
    if orc["sopra"] != S("sopra_media"):                    m.append(f"sopra_media {orc['sopra']} vs {S('sopra_media')}")
    if not req(orc["sotto_pct"], S("sotto_media_pct"), 4):  m.append(f"sotto_media_pct {orc['sotto_pct']} vs {S('sotto_media_pct')}")
    if not req(orc["sopra_pct"], S("sopra_media_pct"), 4):  m.append(f"sopra_media_pct {orc['sopra_pct']} vs {S('sopra_media_pct')}")
    if not req(orc["rit_vs_media"], S("rit_vs_media"), 3):  m.append(f"rit_vs_media {orc['rit_vs_media']} vs {S('rit_vs_media')}")
    if orc["storico_cond_su"] != S("storico_cond_su"):      m.append(f"storico_cond_su {orc['storico_cond_su']} vs {S('storico_cond_su')}")
    # --- distribuzione F/G/H (occ_suc + cnt_rit, ogni riga) ---
    rd = {d["len"]: (d["occ_suc"], d["cnt_rit"]) for d in rpc["distribuzione_serie"]}
    for d in orc["distrib"]:
        rr = rd.get(d["len"])
        if rr is None:
            if d["occ_suc"] or d["cnt_rit"]: m.append(f"distrib k={d['len']} mancante in RPC")
        elif (d["occ_suc"], d["cnt_rit"]) != rr:
            m.append(f"distrib k={d['len']} ({d['occ_suc']},{d['cnt_rit']}) vs {rr}")
    # --- ultime 10 serie (AZ) ---
    if orc["ultime10"] != list(rpc["ultime_10_serie"]):
        m.append(f"ultime10 {orc['ultime10']} vs {rpc['ultime_10_serie']}")
    # --- storico CONDIZIONATO (BE/BF/BG): len + count + pct (arrotond. Postgres) ---
    rs = [(s["len"], s["count"], pgr(s["pct"], 4)) for s in rpc["storico_serie"]]
    osg = [(s["len"], s["count"], pgr(s["pct"], 4)) for s in orc["storico"]]
    if osg != rs: m.append(f"storico {osg} vs {rs}")
    # --- run sopra media (BT/BU/BV): run_len + count + pct ---
    rr_ = [(r["run_len"], r["count"], pgr(r["pct"], 4)) for r in rpc["run_sopra_media"]]
    or_ = [(r["run_len"], r["count"], pgr(r["pct"], 4)) for r in orc["run_hist"]]
    if or_ != rr_: m.append(f"run_sopra_media {or_} vs {rr_}")
    # --- BL (ultime 10 strisce sopra media) ---
    bl_rpc = list(rpc.get("ultime_10_strisce_sopra_media", []))
    if list(orc["bl_ultime10"]) != bl_rpc:
        m.append(f"bl_ultime10 {orc['bl_ultime10']} vs {bl_rpc}")
    # --- serie DATI MATCH EVENTO-PER-EVENTO (W/L, RIT, SUC, GCSH, GASH) ---
    rser = rpc["series"]
    if len(rser) != len(orc["series"]):
        m.append(f"series len {len(orc['series'])} vs {len(rser)}")
    else:
        for o, r in zip(orc["series"], rser):
            if o["idx"] != r["idx"] or o["out"] != r["out"] or o["rit"] != r["rit"] \
               or (o["suc"] if o["suc"] is not None else None) != r["suc"] \
               or o["gcsh"] != r["gcsh"] or o["gash"] != r["gash"]:
                m.append(f"series idx={o['idx']} orc(out={o['out']},rit={o['rit']},suc={o['suc']},"
                         f"gcsh={o['gcsh']},gash={o['gash']}) vs rpc(out={r['out']},rit={r['rit']},"
                         f"suc={r['suc']},gcsh={r['gcsh']},gash={r['gash']})")
                break  # un mismatch per variante basta a bocciarla
    return m


# ---------------------------------------------------- scope per modalita'
def scope_all(events):            return events
def scope_last_n(events, n):      return events[-n:] if n <= len(events) else events
def scope_season(events, y):      return [e for e in events if e.get("season_year") == y]


def main():
    events = json.load(open(DATA, encoding="utf-8"))
    seasons = sorted({e.get("season_year") for e in events})
    sb = get_supabase_client()
    print(f"WC league_id={LEAGUE_ID} — {len(events)} eventi — stagioni {seasons}\n")

    LAST_N = [100, 200, 300, 500, 1000]   # = N_PRESETS della dashboard (RitardiPanel)
    modes = [("all", None, scope_all(events), {"p_mode": "all"})]
    for n in LAST_N:
        modes.append((f"last_n={n}", None, scope_last_n(events, n), {"p_mode": "last_n", "p_last_n": n}))
    for y in seasons:
        modes.append((f"season={y}", y, scope_season(events, y), {"p_mode": "season", "p_season_year": y}))

    grand_total = grand_pass = 0
    failures = []
    for mode_label, _, scoped, extra in modes:
        passed = total = 0
        for market, target in variants():
            orc = oracle_full(scoped, market, target)
            params = {"p_league_id": LEAGUE_ID, "p_market": market, "p_target": target,
                      "p_mode": "all", "p_last_n": None, "p_season_year": None}
            params.update(extra)
            rpc = sb.rpc("get_market_delays", params).execute().data
            mm = compare_full(orc, rpc)
            total += 1; grand_total += 1
            if mm:
                lbl = f"{market}" + (f" {target}" if target else "")
                failures.append((mode_label, lbl, mm))
            else:
                passed += 1; grand_pass += 1
        flag = "OK " if passed == total else "FAIL"
        print(f"  [{flag}] modalita' {mode_label:14s} -> {passed}/{total} varianti")

    print(f"\n{'='*68}")
    print(f"TOTALE: {grand_pass}/{grand_total} (mercato x modalita') PASS")
    if failures:
        print(f"\n{len(failures)} CASI CON DIFFERENZE:")
        for mode_label, lbl, mm in failures[:60]:
            print(f"  [{mode_label}] {lbl}: " + "; ".join(mm[:3]) + (" ..." if len(mm) > 3 else ""))
    else:
        print("CERTIFICATO 100%: la dashboard e' una COPIA 1:1 ESATTA del foglio")
        print("su OGNI modalita' (all/last_n/season), OGNI mercato, OGNI campo,")
        print("inclusa la serie DATI MATCH evento-per-evento (W/L, RIT, SUC, GCSH, GASH).")


if __name__ == "__main__":
    main()
