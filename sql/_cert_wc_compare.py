"""
Certificazione Studio Ritardi — STEP 2: oracolo (trascrizione LETTERALE delle
formule del foglio Excel) vs RPC deployata get_market_delays, su tutto lo
storico WC (league_id=1), per OGNI mercato e OGNI variante.

L'oracolo NON riusa il codice della RPC: re-implementa le formule del foglio
cella per cella. Se oracolo e RPC concordano su ogni campo, e l'oracolo e' una
trascrizione fedele del foglio, allora RPC == foglio.

Formule del foglio riprodotte (verificate sui dump del workbook):
  W/L[i] = condizione mercato (1/0)
  RIT[i] = IF(WL=0, RIT[i-1]+1, 0)   (RIT[0] = IF(WL=0,1,0))
  SUC    = RIT[i-1] per ogni i con WL=1   (lista serie chiuse)
  C2 QUOTA OGGETTIVA = 100%/BI6 = B2/n_occ           (B2 = MAX(EVENTO) = M)
  C5 % MERCATO       = BI6 = n_occ/B2
  C4 RITARDO ATTUALE = ultimo RIT
  RECORD             = MAX(SUC)
  C6 MEDIA RIT.      = AVERAGEIF(RIT, "<>0")
  F/G/H              = k ; COUNTIF(SUC,k) ; COUNTIF(RIT,k)
  ULTIME 10 SERIE    = ultimi 10 SUC (cronologici)
  STORICO SERIE      = SUC distinti ord. per COUNTIF desc (tie: valore asc); % = cnt/n_occ
  < / > MEDIA RIT    = COUNTIF(SUC,"<="&INT(C6)) ; COUNTIF(SUC,">="&INT(C6)+1)
  RUN SOPRA MEDIA    = run consecutivi di SUC>=C6 ; istogramma lunghezze ; % = cnt/tot_run
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db_client import get_supabase_client

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "_cert_wc_data.json")
LEAGUE_ID = 1


# ----------------------------------------------------- condizioni mercato (= foglio/RPC)
def hh0(e): return e["gcfh"] or 0
def ha0(e): return e["gafh"] or 0

def cond(market, target, e):
    h, a = e["gc"], e["ga"]
    if market == "re":
        H, A = (int(x) for x in target.split("-"));  return h == H and a == A
    if market == "sge":   return (h + a) == int(target)
    if market == "over":  return (h + a) > float(target)
    if market == "under": return (h + a) < float(target)
    if market == "ovpt":  return (hh0(e) + ha0(e)) > float(target)
    if market == "ggpt":  return hh0(e) > 0 and ha0(e) > 0
    if market == "ggst":  return (h - hh0(e)) > 0 and (a - ha0(e)) > 0
    if market == "pf1x":  return hh0(e) > ha0(e) and h == a
    if market == "pf2x":  return hh0(e) < ha0(e) and h == a
    if market == "pfx1":  return hh0(e) == ha0(e) and h > a
    if market == "pfx2":  return hh0(e) == ha0(e) and h < a
    if market == "x":     return h == a
    if market == "ggov25":return h > 0 and a > 0 and (h + a) > 2
    raise ValueError(market)


# ----------------------------------------------------- oracolo (formule foglio)
def oracle(events, market, target):
    wl = [1 if cond(market, target, e) else 0 for e in events]
    M = len(wl)
    rit, suc = [], []
    prev = 0
    for i, w in enumerate(wl):
        if w == 0:
            cur = (prev + 1) if i > 0 else 1
            rit.append(cur)
        else:
            rit.append(0)
            suc.append(prev)
        prev = rit[-1]
    n_occ = len(suc)

    media_storica = (M / n_occ) if n_occ else None
    frequency = (n_occ / M) if M else None
    ritardo_attuale = rit[-1] if rit else 0
    record = max(suc) if suc else None
    nz = [r for r in rit if r != 0]
    media_rit = (sum(nz) / len(nz)) if nz else None

    imedia = math.floor(media_rit) if media_rit is not None else None
    sotto = sum(1 for s in suc if imedia is not None and s <= imedia)
    sopra = sum(1 for s in suc if imedia is not None and s >= imedia + 1)

    # distribuzione F/G/H su 0..max(SUC,RIT)
    maxk = max([0] + suc + rit)
    distrib = [{"len": k,
                "occ_suc": sum(1 for s in suc if s == k),
                "cnt_rit": sum(1 for r in rit if r == k)} for k in range(0, maxk + 1)]

    ultime10 = suc[-10:]  # cronologici

    # storico serie: distinti ord. per count desc, tie valore asc
    cnts = {}
    for s in suc:
        cnts[s] = cnts.get(s, 0) + 1
    storico = sorted(cnts.items(), key=lambda kv: (-kv[1], kv[0]))
    storico = [{"len": k, "count": c, "pct": (c / n_occ) if n_occ else None} for k, c in storico]

    # run sopra media: run consecutivi di SUC>=media_rit
    runs, cur = [], 0
    if media_rit is not None:
        for s in suc:
            if s >= media_rit:
                cur += 1
            else:
                if cur > 0: runs.append(cur)
                cur = 0
        if cur > 0: runs.append(cur)
    rh = {}
    for L in runs:
        rh[L] = rh.get(L, 0) + 1
    tot_run = sum(rh.values())
    run_hist = [{"run_len": L, "count": c, "pct": (c / tot_run) if tot_run else None}
                for L, c in sorted(rh.items())]

    # colonna BL: token-stream cronologico (0 = serie chiusa SOTTO media;
    # N = striscia di N serie consecutive SOPRA media), ultime 10 voci.
    # Se media_rit è None (nessun ritardo: hit-rate 100%), BL è indefinita ->
    # lista vuota, identico al SQL dove "suc < NULL" è sempre falso.
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

    return dict(n_occ=n_occ, n_eff=M, frequency=frequency, media_storica=media_storica,
                ritardo_attuale=ritardo_attuale, record=record, media_rit=media_rit,
                sotto=sotto, sopra=sopra, distrib=distrib, ultime10=ultime10,
                storico=storico, run_hist=run_hist, bl_ultime10=bl_ultime10)


# ----------------------------------------------------- confronto helpers
def req(a, b, dec):
    """uguaglianza su numeri arrotondati a 'dec' decimali (None==None)."""
    if a is None and b is None: return True
    if a is None or b is None:  return False
    return round(float(a), dec) == round(float(b), dec)

def compare(market, target, orc, rpc):
    """ritorna lista di mismatch (vuota = PASS)."""
    m = []
    st = rpc["stats"]; meta = rpc["meta"]
    # scalari
    if orc["n_occ"]        != st["n_occ"]:                         m.append(f"n_occ {orc['n_occ']} vs {st['n_occ']}")
    if orc["n_eff"]        != meta["n_effective"]:                 m.append(f"n_eff {orc['n_eff']} vs {meta['n_effective']}")
    if orc["ritardo_attuale"] != st["ritardo_attuale"]:           m.append(f"ritardo_attuale {orc['ritardo_attuale']} vs {st['ritardo_attuale']}")
    if (orc["record"] or 0) != (st["record"] or 0):               m.append(f"record {orc['record']} vs {st['record']}")
    if not req(orc["frequency"], st["frequency"], 6):             m.append(f"frequency {orc['frequency']} vs {st['frequency']}")
    if not req(orc["media_storica"], st["media_storica"], 6):     m.append(f"media_storica {orc['media_storica']} vs {st['media_storica']}")
    if not req(orc["media_rit"], st["media_ritardi"], 4):         m.append(f"media_rit {orc['media_rit']} vs {st['media_ritardi']}")
    if orc["sotto"]        != st["sotto_media"]:                   m.append(f"sotto {orc['sotto']} vs {st['sotto_media']}")
    if orc["sopra"]        != st["sopra_media"]:                   m.append(f"sopra {orc['sopra']} vs {st['sopra_media']}")
    # distribuzione F/G/H
    rd = {d["len"]: (d["occ_suc"], d["cnt_rit"]) for d in rpc["distribuzione_serie"]}
    for d in orc["distrib"]:
        rr = rd.get(d["len"])
        if rr is None:
            if d["occ_suc"] or d["cnt_rit"]: m.append(f"distrib k={d['len']} mancante in RPC")
        elif (d["occ_suc"], d["cnt_rit"]) != rr:
            m.append(f"distrib k={d['len']} ({d['occ_suc']},{d['cnt_rit']}) vs {rr}")
    # ultime 10
    if orc["ultime10"] != list(rpc["ultime_10_serie"]):
        m.append(f"ultime10 {orc['ultime10']} vs {rpc['ultime_10_serie']}")
    # storico serie
    rs = [(s["len"], s["count"]) for s in rpc["storico_serie"]]
    os_ = [(s["len"], s["count"]) for s in orc["storico"]]
    if os_ != rs:
        m.append(f"storico {os_} vs {rs}")
    # run sopra media
    rr_ = [(r["run_len"], r["count"]) for r in rpc["run_sopra_media"]]
    or_ = [(r["run_len"], r["count"]) for r in orc["run_hist"]]
    if or_ != rr_:
        m.append(f"run_sopra_media {or_} vs {rr_}")
    # colonna BL: ultime 10 strisce sopra media
    bl_rpc = list(rpc.get("ultime_10_strisce_sopra_media", []))
    if list(orc["bl_ultime10"]) != bl_rpc:
        m.append(f"bl_ultime10 {orc['bl_ultime10']} vs {bl_rpc}")
    return m


# ----------------------------------------------------- varianti da certificare
def variants():
    v = []
    for s in ['0-0','1-0','0-1','1-1','2-0','0-2','2-1','1-2','2-2','3-0','0-3','3-1','1-3','3-2','2-3','3-3']:
        v.append(("re", s))
    for n in range(0, 9):
        v.append(("sge", str(n)))
    for L in ['0.5','1.5','2.5','3.5','4.5','5.5','6.5']:
        v.append(("over", L)); v.append(("under", L))
    for L in ['0.5','1.5','2.5']:
        v.append(("ovpt", L))
    for mk in ['ggpt','ggst','pf1x','pf2x','pfx1','pfx2','x','ggov25']:
        v.append((mk, None))
    return v


def main():
    events = json.load(open(DATA, encoding="utf-8"))
    sb = get_supabase_client()
    print(f"WC league_id={LEAGUE_ID} — {len(events)} eventi\n")

    total = 0; passed = 0; fields = 0
    failures = []
    for market, target in variants():
        orc = oracle(events, market, target)
        rpc = sb.rpc("get_market_delays", {
            "p_league_id": LEAGUE_ID, "p_market": market, "p_target": target,
            "p_mode": "all", "p_last_n": None, "p_season_year": None,
        }).execute().data
        mm = compare(market, target, orc, rpc)
        total += 1
        # conteggio campi confrontati (per il report)
        fields += 9 + len(orc["distrib"]) + 1 + 1 + 1
        label = f"{market}" + (f" {target}" if target else "")
        if mm:
            failures.append((label, mm, orc, rpc))
            print(f"  [FAIL] {label:14s}  ->  " + "; ".join(mm[:4]) + (" ..." if len(mm) > 4 else ""))
        else:
            passed += 1
            print(f"  [OK]   {label:14s}  n_occ={orc['n_occ']:>3}  "
                  f"q.ogg={orc['media_storica']:.2f}  rit={orc['ritardo_attuale']:>2}  "
                  f"rec={orc['record']}  media={orc['media_rit']:.2f}")

    print(f"\n{'='*64}")
    print(f"VARIANTI: {passed}/{total} PASS   (~{fields} campi confrontati)")
    if failures:
        print(f"\n{len(failures)} VARIANTI CON DIFFERENZE — dettaglio:")
        for label, mm, orc, rpc in failures:
            print(f"\n--- {label} ---")
            for x in mm:
                print(f"    {x}")
    else:
        print("CERTIFICATO: RPC IDENTICA AL FOGLIO su ogni sezione e ogni variante.")


if __name__ == "__main__":
    main()
