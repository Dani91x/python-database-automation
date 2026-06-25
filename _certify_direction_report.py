# -*- coding: utf-8 -*-
"""
_certify_direction_report.py — CERTIFICAZIONE money-critical del RENDICONTO DIREZIONI
(RPC get_direction_report / get_direction_report_matches).

⚠️ SOLDI IN GIOCO: gli utenti decidono in base a questi hit-rate. Zero errori tollerati.

Cosa valida (oracolo Python INDIPENDENTE == RPC, tol 1e-9, su dati reali):
  (a) Per ogni scenario di filtri (giorno singolo / range / lega / mercato / solo-buone):
      legge le righe grezze di analytics_signals (engine='poisson', settled) nella stessa
      finestra kickoff (fuso Europe/Rome) della RPC, calcola la DIREZIONE = argmax Poisson
      per (fixture, mercato) con lo STESSO tie-break (prob desc nulls-last, selection asc),
      e ricompone KPI + daily + by_market + by_market_day + by_league + meta.leagues.
      Confronto campo-per-campo con la RPC. Denominatore = direzioni con hit IS NOT NULL.
  (b) get_direction_report_matches: scorecard per partita (dir_ok/dir_tot, good_ok/good_tot)
      ricomposto dall'oracolo == RPC.
  (c) RI-DERIVAZIONE INDIPENDENTE di hit: per ogni direzione, ricalcola l'esito con
      analytics_settlement.hit() dai gol/HT salvati nella riga e lo confronta con la
      colonna `hit` di produzione. Zero mismatch = la verità su cui si fonda il report è sana.

Uso:  python _certify_direction_report.py
Exit code != 0 se un qualsiasi confronto fallisce.
"""
from __future__ import annotations
import sys
import math
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from db_client import get_supabase_client
from analytics_settlement import hit as settle_hit

TOL = 1e-9
Z = 1.96
ROME = ZoneInfo("Europe/Rome")
CANON_MARKETS = ["1x2", "ht_1x2", "over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"]

sb = get_supabase_client()
_fails: list[str] = []


def fail(msg: str) -> None:
    _fails.append(msg)
    print(f"  ✗ {msg}")


def approx(a, b) -> bool:
    """Uguaglianza robusta: None==None, numerici a tol, resto ==."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= TOL
    return a == b


def cmp_field(tag: str, got, exp) -> None:
    if not approx(got, exp):
        fail(f"{tag}: RPC={got!r} oracolo={exp!r}")


# --------------------------------------------------------------------------- pull
def rome_window(d_from: date, d_to: date) -> tuple[str, str]:
    """[mezzanotte Roma di d_from, mezzanotte Roma di d_to+1) in ISO con offset."""
    f = datetime.combine(d_from, time(0, 0), tzinfo=ROME)
    t = datetime.combine(d_to + timedelta(days=1), time(0, 0), tzinfo=ROME)
    return f.isoformat(), t.isoformat()


def pull_rows(d_from: date, d_to: date, market: str | None):
    """Righe poisson settled nella finestra kickoff (Roma), opz. filtrate per mercato."""
    f_iso, t_iso = rome_window(d_from, d_to)
    cols = ("fixture_id,market,selection,prob,hit,n_engines_agree,league_id,league_name,"
            "home_team,away_team,kickoff,goals_home,goals_away,ht_home,ht_away")
    rows, start = [], 0
    while True:
        q = (sb.table("analytics_signals").select(cols)
             .eq("engine", "poisson").eq("settled", True)
             .gte("kickoff", f_iso).lt("kickoff", t_iso))
        if market:
            q = q.eq("market", market)
        d = q.range(start, start + 999).execute().data
        rows += d
        if len(d) < 1000:
            break
        start += 1000
    return rows


def load_betfair_fixtures() -> set:
    """Insieme dei fixture_id presenti in engine_signals (= partite su Betfair),
    stesso criterio di get_betfair_fixtures e del filtro p_betfair_only."""
    ids, start = set(), 0
    while True:
        d = sb.table("engine_signals").select("fixture_id").range(start, start + 999).execute().data
        for r in d:
            if r["fixture_id"] is not None:
                ids.add(r["fixture_id"])
        if len(d) < 1000:
            break
        start += 1000
    return ids


_BF: set | None = None
def betfair_set() -> set:
    global _BF
    if _BF is None:
        _BF = load_betfair_fixtures()
    return _BF


# mappa codici engine_signals → (mercato canonico, selezione) — STESSA di get_betfair_odds
DECODE = {
    "H": ("1x2", "H"), "D": ("1x2", "D"), "A": ("1x2", "A"),
    "HT_H": ("ht_1x2", "H"), "HT_D": ("ht_1x2", "D"), "HT_A": ("ht_1x2", "A"),
    "O15": ("over_1_5", "Over"), "U15": ("over_1_5", "Under"),
    "O25": ("over_2_5", "Over"), "U25": ("over_2_5", "Under"),
    "O35": ("over_3_5", "Over"), "U35": ("over_3_5", "Under"),
    "BTTS": ("btts", "Yes"), "BTTS_NO": ("btts", "No"),
    "HT05": ("first_half_over_0_5", "Over"), "HT_U05": ("first_half_over_0_5", "Under"),
}
DEFAULT_COMM = 0.05


def load_betfair_odds() -> dict:
    """{(fixture_id, mercato, selezione): max(odds)} da engine_signals (== get_betfair_odds)."""
    odds: dict = {}
    start = 0
    while True:
        d = sb.table("engine_signals").select("fixture_id,market,odds").range(start, start + 999).execute().data
        for r in d:
            o = r.get("odds")
            code = r.get("market")
            if o is None or code not in DECODE:
                continue
            mk, sel = DECODE[code]
            key = (r["fixture_id"], mk, sel)
            of = float(o)
            odds[key] = of if key not in odds else max(odds[key], of)
        if len(d) < 1000:
            break
        start += 1000
    return odds


_ODDS: dict | None = None
def odds_map() -> dict:
    global _ODDS
    if _ODDS is None:
        _ODDS = load_betfair_odds()
    return _ODDS


def odds_band(o):
    """(ord, band) come la RPC. None se quota assente."""
    if o is None:
        return None, None
    if o < 1.5:  return 1, "1.01-1.50"
    if o < 2.0:  return 2, "1.50-2.00"
    if o < 3.0:  return 3, "2.00-3.00"
    if o < 5.0:  return 4, "3.00-5.00"
    return 5, "5.00+"


def attach_pnl(directions, comm):
    """Aggancia quota Betfair + P&L back (stake=1) a ogni direzione."""
    om = odds_map()
    for r in directions:
        o = om.get((r["fixture_id"], r["market"], r["selection"]))
        r["odds"] = o
        if r["hit"] is None or o is None:
            r["pnl"] = None
        elif r["hit"]:
            r["pnl"] = (o - 1) * (1 - comm)
        else:
            r["pnl"] = -1.0
        r["ord"], r["band"] = odds_band(o)
    return directions


def giorno_of(kickoff_iso: str) -> date:
    return datetime.fromisoformat(kickoff_iso).astimezone(ROME).date()


def argmax_directions(rows):
    """1 direzione per (fixture, market): argmax prob (nulls-last), tie-break selection asc."""
    groups: dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["fixture_id"], r["market"]), []).append(r)
    out = []
    for _, cand in groups.items():
        cand.sort(key=lambda r: (r["prob"] is None, -(r["prob"] or 0.0), r["selection"]))
        out.append(cand[0])
    return out


def is_good(r) -> bool:
    na = r.get("n_engines_agree")
    return na is not None and na >= 2


def wilson(hits: int, n: int):
    if n <= 0:
        return None, None
    p = hits / n
    lo = ((p + Z*Z/(2*n)) - Z*math.sqrt((p*(1-p) + Z*Z/(4*n))/n)) / (1 + Z*Z/n)
    hi = ((p + Z*Z/(2*n)) + Z*math.sqrt((p*(1-p) + Z*Z/(4*n))/n)) / (1 + Z*Z/n)
    return max(0.0, lo), min(1.0, hi)   # clamp [0,1] come la RPC (greatest/least)


def rate(hits: int, n: int):
    return hits / n if n > 0 else None


def roi_of(profit, priced_n):
    return (profit / priced_n) if priced_n and priced_n > 0 else None


def block(items):
    """Metriche complete su una lista di direzioni (con odds/pnl già agganciati)."""
    valid = [r for r in items if r["hit"] is not None]
    n = len(valid)
    hits = sum(1 for r in valid if r["hit"])
    avg_prob = (sum(float(r["prob"]) for r in valid) / n) if n else None
    good_valid = [r for r in valid if is_good(r)]
    good_n = len(good_valid)
    good_hits = sum(1 for r in good_valid if r["hit"])
    priced = [r for r in items if r["pnl"] is not None]
    priced_n = len(priced)
    profit = sum(r["pnl"] for r in priced) if priced_n else None
    avg_odds = (sum(r["odds"] for r in priced) / priced_n) if priced_n else None
    good_priced = [r for r in priced if is_good(r)]
    good_priced_n = len(good_priced)
    good_profit = sum(r["pnl"] for r in good_priced) if good_priced_n else None
    return {"n": n, "hits": hits, "avg_prob": avg_prob, "good_n": good_n, "good_hits": good_hits,
            "priced_n": priced_n, "profit": profit, "avg_odds": avg_odds,
            "good_priced_n": good_priced_n, "good_profit": good_profit}


# --------------------------------------------------------------------------- oracolo
def oracle_report(rows, league_id, only_good, comm=DEFAULT_COMM):
    base_all = attach_pnl(argmax_directions(rows), comm)
    b = [r for r in base_all
         if (league_id is None or r["league_id"] == league_id)
         and (not only_good or is_good(r))]

    # KPI
    m = block(b)
    lo, hi = wilson(m["hits"], m["n"])
    kpi = {
        "n": m["n"], "hits": m["hits"], "hit_rate": rate(m["hits"], m["n"]), "avg_prob": m["avg_prob"],
        "calib_gap": (rate(m["hits"], m["n"]) - m["avg_prob"]) if m["n"] > 0 else None,
        "wilson_low": lo, "wilson_high": hi,
        "good_n": m["good_n"], "good_hits": m["good_hits"], "good_hit_rate": rate(m["good_hits"], m["good_n"]),
        "priced_n": m["priced_n"], "profit": m["profit"], "roi": roi_of(m["profit"], m["priced_n"]),
        "avg_odds": m["avg_odds"],
        "good_priced_n": m["good_priced_n"], "good_roi": roi_of(m["good_profit"], m["good_priced_n"]),
    }

    # daily
    by_day: dict[date, list] = {}
    for r in b:
        by_day.setdefault(giorno_of(r["kickoff"]), []).append(r)
    daily = []
    for g in sorted(by_day):
        d = block(by_day[g])
        daily.append({"giorno": g.isoformat(), "n": d["n"], "hits": d["hits"], "hit_rate": rate(d["hits"], d["n"]),
                      "avg_prob": d["avg_prob"], "good_n": d["good_n"], "good_hit_rate": rate(d["good_hits"], d["good_n"]),
                      "priced_n": d["priced_n"], "roi": roi_of(d["profit"], d["priced_n"])})

    # by_market
    by_mkt: dict[str, list] = {}
    for r in b:
        by_mkt.setdefault(r["market"], []).append(r)
    by_market = []
    for mk in sorted(by_mkt):
        d = block(by_mkt[mk])
        by_market.append({"market": mk, "n": d["n"], "hits": d["hits"], "hit_rate": rate(d["hits"], d["n"]),
                          "avg_prob": d["avg_prob"], "good_n": d["good_n"], "good_hit_rate": rate(d["good_hits"], d["good_n"]),
                          "priced_n": d["priced_n"], "roi": roi_of(d["profit"], d["priced_n"]), "avg_odds": d["avg_odds"]})

    # by_market_day (heatmap) — solo hit, niente pnl
    by_md: dict[tuple, list] = {}
    for r in b:
        by_md.setdefault((r["market"], giorno_of(r["kickoff"])), []).append(r)
    by_market_day = []
    for (mk, g) in sorted(by_md, key=lambda k: (k[0], k[1])):
        valid = [r for r in by_md[(mk, g)] if r["hit"] is not None]
        n_ = len(valid); h_ = sum(1 for r in valid if r["hit"])
        by_market_day.append({"market": mk, "giorno": g.isoformat(), "n": n_, "hit_rate": rate(h_, n_)})

    # by_league
    by_lg: dict = {}
    for r in b:
        by_lg.setdefault(r["league_id"], []).append(r)
    by_league = []
    for lid in sorted(by_lg, key=lambda x: (x is None, x if x is not None else 0)):
        items = by_lg[lid]
        d = block(items)
        lname = next((r["league_name"] for r in items if r["league_name"] is not None), None)
        by_league.append({"league_id": lid, "league_name": lname, "n": d["n"], "hits": d["hits"],
                          "hit_rate": rate(d["hits"], d["n"]), "avg_prob": d["avg_prob"], "good_n": d["good_n"],
                          "good_hit_rate": rate(d["good_hits"], d["good_n"]),
                          "priced_n": d["priced_n"], "roi": roi_of(d["profit"], d["priced_n"]), "avg_odds": d["avg_odds"]})

    # by_concordance
    by_conc: dict = {}
    for r in b:
        by_conc.setdefault(r["n_engines_agree"], []).append(r)
    by_concordance = []
    for ag in sorted(by_conc, key=lambda x: (x is None, x if x is not None else 0)):
        d = block(by_conc[ag])
        by_concordance.append({"agree": ag, "n": d["n"], "hits": d["hits"], "hit_rate": rate(d["hits"], d["n"]),
                               "priced_n": d["priced_n"], "roi": roi_of(d["profit"], d["priced_n"]), "avg_odds": d["avg_odds"]})

    # by_odds_band — solo direzioni prezzabili (pnl not null)
    by_band: dict = {}
    for r in b:
        if r["pnl"] is not None:
            by_band.setdefault(r["ord"], []).append(r)
    by_odds_band = []
    for ordv in sorted(by_band):
        items = by_band[ordv]
        priced_n = len(items)
        h_ = sum(1 for r in items if r["hit"])
        profit = sum(r["pnl"] for r in items)
        avg_o = sum(r["odds"] for r in items) / priced_n
        by_odds_band.append({"band": items[0]["band"], "ord": ordv, "priced_n": priced_n, "hits": h_,
                             "hit_rate": rate(h_, priced_n), "roi": roi_of(profit, priced_n), "avg_odds": avg_o})

    # meta.leagues (su base_all: NON filtrato per lega/only_good)
    lg_meta: dict = {}
    for r in base_all:
        lg_meta.setdefault(r["league_id"], []).append(r)
    leagues = []
    for lid, items in lg_meta.items():
        n_ = sum(1 for r in items if r["hit"] is not None)
        if n_ > 0:
            lname = next((r["league_name"] for r in items if r["league_name"] is not None), None)
            leagues.append({"id": lid, "name": lname, "n": n_})
    leagues.sort(key=lambda x: (x["id"] is None, x["id"]))

    return {"kpi": kpi, "daily": daily, "by_market": by_market, "by_market_day": by_market_day,
            "by_league": by_league, "by_concordance": by_concordance, "by_odds_band": by_odds_band,
            "leagues": leagues}


def oracle_matches(rows, league_id, only_good, comm=DEFAULT_COMM):
    base_all = attach_pnl(argmax_directions(rows), comm)
    b = [r for r in base_all
         if (league_id is None or r["league_id"] == league_id)
         and (not only_good or is_good(r))]
    by_fix: dict = {}
    for r in b:
        by_fix.setdefault(r["fixture_id"], []).append(r)
    res = []
    for fid, items in by_fix.items():
        valid = [r for r in items if r["hit"] is not None]
        if not valid:
            continue
        good_valid = [r for r in valid if is_good(r)]
        priced = [r for r in items if r["pnl"] is not None]
        priced_n = len(priced)
        profit = sum(r["pnl"] for r in priced) if priced_n else None
        # max() NULL-safe come SQL max(): ignora i None, None se tutti None
        def maxnn(vals):
            v = [x for x in vals if x is not None]
            return max(v) if v else None
        any_r = items[0]
        res.append({
            "fixture_id": fid,
            "giorno": giorno_of(any_r["kickoff"]).isoformat(),
            "league_id": maxnn([r["league_id"] for r in items]),
            "home_team": maxnn([r["home_team"] for r in items]),
            "away_team": maxnn([r["away_team"] for r in items]),
            "dir_tot": len(valid), "dir_ok": sum(1 for r in valid if r["hit"]),
            "good_tot": len(good_valid), "good_ok": sum(1 for r in good_valid if r["hit"]),
            "priced_n": priced_n, "profit": profit, "roi": roi_of(profit, priced_n),
        })
    return {r["fixture_id"]: r for r in res}


# --------------------------------------------------------------------------- compare
def cmp_report(label, rpc, ora):
    print(f"\n=== (a) get_direction_report — {label} ===")
    if rpc is None or not isinstance(rpc, dict) or "kpi" not in rpc:
        fail(f"{label}: RPC ha restituito una forma inattesa (atteso jsonb con kpi): {type(rpc).__name__}")
        return
    # KPI (incl. rendimento)
    for k in ("n", "hits", "hit_rate", "avg_prob", "calib_gap", "wilson_low",
              "wilson_high", "good_n", "good_hits", "good_hit_rate",
              "priced_n", "profit", "roi", "avg_odds", "good_priced_n", "good_roi"):
        cmp_field(f"kpi.{k}", rpc["kpi"].get(k), ora["kpi"][k])
    # array allineati (confronta TUTTI i campi di ogni elemento, inclusi roi/priced_n/avg_odds)
    for arr, key in (("daily", "giorno"), ("by_market", "market"),
                     ("by_league", "league_id"), ("by_concordance", "agree"),
                     ("by_odds_band", "ord")):
        r_list, o_list = rpc.get(arr, []), ora[arr]
        if len(r_list) != len(o_list):
            fail(f"{arr}: lunghezza RPC={len(r_list)} oracolo={len(o_list)}")
            continue
        for rr, oo in zip(r_list, o_list):
            cmp_field(f"{arr}[{oo[key]}].{key}", rr.get(key), oo[key])
            for f in oo:
                cmp_field(f"{arr}[{oo[key]}].{f}", rr.get(f), oo[f])
    # by_market_day
    rmd, omd = rpc.get("by_market_day", []), ora["by_market_day"]
    if len(rmd) != len(omd):
        fail(f"by_market_day: lunghezza RPC={len(rmd)} oracolo={len(omd)}")
    else:
        for rr, oo in zip(rmd, omd):
            for f in ("market", "giorno", "n", "hit_rate"):
                cmp_field(f"by_market_day[{oo['market']}/{oo['giorno']}].{f}", rr.get(f), oo[f])
    # meta.leagues
    rlg = (rpc.get("meta", {}) or {}).get("leagues", []) or []
    olg = ora["leagues"]
    if len(rlg) != len(olg):
        fail(f"meta.leagues: lunghezza RPC={len(rlg)} oracolo={len(olg)}")
    else:
        for rr, oo in zip(rlg, olg):
            for f in ("id", "name", "n"):
                cmp_field(f"meta.leagues[{oo['id']}].{f}", rr.get(f), oo[f])
    n_before = len(_fails)
    print(f"  KPI N={ora['kpi']['n']} hit={ora['kpi']['hits']} "
          f"hit_rate={ora['kpi']['hit_rate']} · daily={len(ora['daily'])} "
          f"market={len(ora['by_market'])} mkt_day={len(ora['by_market_day'])} "
          f"leghe={len(ora['by_league'])}")
    print("  --> 0 mismatch" if n_before == len(_fails) else f"  --> {len(_fails)-n_before} MISMATCH")


def cmp_matches(label, rpc_rows, ora_map):
    print(f"\n=== (b) get_direction_report_matches — {label} ===")
    if len(rpc_rows) != len(ora_map):
        fail(f"matches: righe RPC={len(rpc_rows)} oracolo={len(ora_map)}")
    n_before = len(_fails)
    for rr in rpc_rows:
        oo = ora_map.get(rr["fixture_id"])
        if oo is None:
            fail(f"matches: fixture {rr['fixture_id']} assente nell'oracolo"); continue
        for f in ("dir_tot", "dir_ok", "good_tot", "good_ok", "giorno", "home_team", "away_team",
                  "priced_n", "profit", "roi"):
            cmp_field(f"match[{rr['fixture_id']}].{f}", rr.get(f), oo[f])
    print(f"  {len(rpc_rows)} partite confrontate")
    print("  --> 0 mismatch" if n_before == len(_fails) else f"  --> {len(_fails)-n_before} MISMATCH")


def cmp_hit_rederive(label, rows):
    """(c) ri-deriva hit con analytics_settlement.hit() dai gol/HT salvati."""
    print(f"\n=== (c) ri-derivazione hit indipendente — {label} ===")
    n_before = len(_fails)
    checked = 0
    for r in argmax_directions(rows):
        gh, ga = r.get("goals_home"), r.get("goals_away")
        hh, ha = r.get("ht_home"), r.get("ht_away")
        ft = (int(gh), int(ga)) if gh is not None and ga is not None else None
        ht = (int(hh), int(ha)) if hh is not None and ha is not None else None
        expected = settle_hit(r["market"], r["selection"], ft, ht)
        stored = r["hit"]
        # confronto solo dove la colonna ha un valore booleano (esito noto)
        if stored is not None:
            checked += 1
            if expected != stored:
                fail(f"hit[{r['fixture_id']}/{r['market']}/{r['selection']}] "
                     f"stored={stored} ricalcolo={expected} (ft={ft} ht={ht})")
    print(f"  {checked} direzioni ri-derivate dai gol salvati")
    print("  --> 0 mismatch" if n_before == len(_fails) else f"  --> {len(_fails)-n_before} MISMATCH")


def cmp_fixture(fid, rows, comm=DEFAULT_COMM):
    """(d) get_direction_report_fixture: argmax per mercato di UNA partita + hit + quota + pnl."""
    rpc = sb.rpc("get_direction_report_fixture", {"p_fixture_id": fid}).execute().data
    om = odds_map()
    frows = [r for r in rows if r["fixture_id"] == fid]
    by_mkt: dict = {}
    for r in frows:
        by_mkt.setdefault(r["market"], []).append(r)
    ora = []
    for m in sorted(by_mkt):
        cand = sorted(by_mkt[m], key=lambda r: (r["prob"] is None, -(r["prob"] or 0.0), r["selection"]))[0]
        o = om.get((fid, m, cand["selection"]))
        if cand["hit"] is None or o is None:
            pnl = None
        elif cand["hit"]:
            pnl = (o - 1) * (1 - comm)
        else:
            pnl = -1.0
        ora.append({"market": m, "selection": cand["selection"], "prob": cand["prob"],
                    "n_engines_agree": cand["n_engines_agree"], "hit": cand["hit"],
                    "odds": o, "pnl": pnl})
    rpc_rows = rpc.get("rows", [])
    if len(rpc_rows) != len(ora):
        fail(f"fixture[{fid}]: righe RPC={len(rpc_rows)} oracolo={len(ora)}")
        return
    for rr, oo in zip(rpc_rows, ora):
        for f in ("market", "selection", "prob", "n_engines_agree", "hit", "odds", "pnl"):
            cmp_field(f"fixture[{fid}].{oo['market']}.{f}", rr.get(f), oo[f])


def call_report(d_from, d_to, league_id, market, only_good, betfair_only=False, commission=DEFAULT_COMM):
    return sb.rpc("get_direction_report", {
        "p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
        "p_league_id": league_id, "p_market": market, "p_only_good": only_good,
        "p_betfair_only": betfair_only, "p_commission": commission,
    }).execute().data


def call_matches(d_from, d_to, league_id, market, only_good, limit=2000, offset=0,
                 betfair_only=False, commission=DEFAULT_COMM):
    return sb.rpc("get_direction_report_matches", {
        "p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
        "p_league_id": league_id, "p_market": market, "p_only_good": only_good,
        "p_betfair_only": betfair_only, "p_commission": commission, "p_limit": limit, "p_offset": offset,
    }).execute().data


def run_scenario(label, d_from, d_to, league_id=None, market=None, only_good=False,
                 do_matches=False, betfair_only=False, commission=DEFAULT_COMM):
    rows = pull_rows(d_from, d_to, market)
    if betfair_only:   # filtro fixture-level == p_betfair_only nel base_all della RPC
        bf = betfair_set()
        rows = [r for r in rows if r["fixture_id"] in bf]
    ora = oracle_report(rows, league_id, only_good, commission)
    rpc = call_report(d_from, d_to, league_id, market, only_good, betfair_only, commission)
    cmp_report(label, rpc, ora)
    cmp_hit_rederive(label, rows)
    if do_matches:
        resp = call_matches(d_from, d_to, league_id, market, only_good,
                            betfair_only=betfair_only, commission=commission)
        ora_m = oracle_matches(rows, league_id, only_good, commission)
        cmp_matches(label, resp["rows"], ora_m)
        cmp_field(f"matches.total ({label})", resp["total"], len(ora_m))


def main():
    print("=" * 74)
    print("CERTIFICAZIONE RENDICONTO DIREZIONI — oracolo Python == RPC (tol 1e-9)")
    print("=" * 74)

    d24 = date(2026, 6, 24)
    d18 = date(2026, 6, 18)

    # scenario 1: giorno singolo, nessun filtro
    run_scenario("giorno 24/06, nessun filtro", d24, d24, do_matches=True)

    # scenario 2: range 18-24/06, nessun filtro
    run_scenario("range 18-24/06, nessun filtro", d18, d24)

    # scenario 3: range + lega (la lega con più direzioni nel range)
    rows = pull_rows(d18, d24, None)
    dirs = argmax_directions(rows)
    cnt: dict = {}
    for r in dirs:
        if r["hit"] is not None:
            cnt[r["league_id"]] = cnt.get(r["league_id"], 0) + 1
    top_league = max(cnt, key=cnt.get) if cnt else None
    if top_league is not None:
        run_scenario(f"range 18-24/06, lega={top_league}", d18, d24,
                     league_id=top_league, do_matches=True)

    # scenario 4: range + mercato over_1_5
    run_scenario("range 18-24/06, mercato=over_1_5", d18, d24, market="over_1_5")

    # scenario 5: range + solo buone
    run_scenario("range 18-24/06, solo buone (conc.>=2)", d18, d24, only_good=True, do_matches=True)

    # scenario 6: range + mercato HT (denominatore con hit NULL) — anche matches
    run_scenario("range 18-24/06, mercato=ht_1x2 (test hit NULL)", d18, d24, market="ht_1x2", do_matches=True)

    # scenario 6b: combinazione mercato + solo buone
    run_scenario("range 18-24/06, over_2_5 + solo buone", d18, d24, market="over_2_5", only_good=True)

    # scenario 6c: range vuoto (futuro, 0 direzioni settlate → denominatore 0)
    run_scenario("range vuoto 01-02/01/2030 (denominatore 0)", date(2030, 1, 1), date(2030, 1, 2))

    # scenario 6d: SOLO Betfair (fixture in engine_signals) — anche matches
    run_scenario("range 18-24/06, SOLO Betfair", d18, d24, betfair_only=True, do_matches=True)

    # scenario 6e: SOLO Betfair + mercato + solo buone (filtri combinati) + matches
    run_scenario("range 18-24/06, Betfair + over_2_5 + buone", d18, d24,
                 market="over_2_5", only_good=True, betfair_only=True, do_matches=True)

    # scenario 6f: commissione personalizzata 2% (verifica p_commission nel P&L)
    run_scenario("range 18-24/06, commissione 0.02", d18, d24, commission=0.02, do_matches=True)

    # scenario 7: drill fine per partita (3 fixtures del 24/06)
    print("\n=== (d) get_direction_report_fixture — drill 3 partite del 24/06 ===")
    rows24 = pull_rows(d24, d24, None)
    fids = sorted({r["fixture_id"] for r in rows24})[:3]
    nb = len(_fails)
    for fid in fids:
        cmp_fixture(fid, rows24)
    print(f"  {len(fids)} partite (7 direzioni cad.) confrontate")
    print("  --> 0 mismatch" if nb == len(_fails) else f"  --> {len(_fails)-nb} MISMATCH")

    # scenario 8: PAGINAZIONE completa — pagine piccole, nessun buco/duplicato,
    # unione == insieme intero, total coerente. (range 18-24/06, molte partite)
    print("\n=== (e) paginazione matches — range 18-24/06 (pagine da 40) ===")
    nb = len(_fails)
    full_rows = pull_rows(d18, d24, None)
    ora_full = oracle_matches(full_rows, None, False)
    page_sz, off, seen, totals = 40, 0, [], set()
    while True:
        resp = call_matches(d18, d24, None, None, False, limit=page_sz, offset=off)
        totals.add(resp["total"])
        ids = [r["fixture_id"] for r in resp["rows"]]
        seen += ids
        if len(resp["rows"]) < page_sz:
            break
        off += page_sz
    if len(totals) != 1:
        fail(f"paginazione: 'total' incoerente tra le pagine: {totals}")
    cmp_field("paginazione.total==oracolo", next(iter(totals)), len(ora_full))
    if len(seen) != len(set(seen)):
        fail(f"paginazione: {len(seen)-len(set(seen))} fixture DUPLICATE tra le pagine")
    if set(seen) != set(ora_full.keys()):
        miss = set(ora_full.keys()) - set(seen)
        extra = set(seen) - set(ora_full.keys())
        fail(f"paginazione: insieme != oracolo (mancanti={len(miss)} extra={len(extra)})")
    print(f"  {len(seen)} partite raccolte in {off//page_sz + 1} pagine · total={next(iter(totals))}")
    print("  --> 0 mismatch" if nb == len(_fails) else f"  --> {len(_fails)-nb} MISMATCH")

    print("\n" + "=" * 74)
    if _fails:
        print(f"ESITO: ❌ {len(_fails)} MISMATCH — NON certificato")
        for m in _fails[:40]:
            print("   -", m)
        sys.exit(1)
    print("ESITO: ✅ CERTIFICATO — oracolo == RPC, hit ri-derivata coerente (0 mismatch)")


if __name__ == "__main__":
    main()
