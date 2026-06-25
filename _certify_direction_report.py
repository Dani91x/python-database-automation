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


def agg_block(items):
    """Calcola n/hits/avg_prob/good_n/good_hits su una lista di direzioni."""
    valid = [r for r in items if r["hit"] is not None]
    n = len(valid)
    hits = sum(1 for r in valid if r["hit"])
    avg_prob = (sum(float(r["prob"]) for r in valid) / n) if n else None
    good_valid = [r for r in valid if is_good(r)]
    good_n = len(good_valid)
    good_hits = sum(1 for r in good_valid if r["hit"])
    return n, hits, avg_prob, good_n, good_hits


# --------------------------------------------------------------------------- oracolo
def oracle_report(rows, league_id, only_good):
    base_all = argmax_directions(rows)
    b = [r for r in base_all
         if (league_id is None or r["league_id"] == league_id)
         and (not only_good or is_good(r))]

    # KPI
    n, hits, avg_prob, good_n, good_hits = agg_block(b)
    lo, hi = wilson(hits, n)
    kpi = {
        "n": n, "hits": hits, "hit_rate": rate(hits, n), "avg_prob": avg_prob,
        "calib_gap": (rate(hits, n) - avg_prob) if n > 0 else None,
        "wilson_low": lo, "wilson_high": hi,
        "good_n": good_n, "good_hits": good_hits, "good_hit_rate": rate(good_hits, good_n),
    }

    # daily
    by_day: dict[date, list] = {}
    for r in b:
        by_day.setdefault(giorno_of(r["kickoff"]), []).append(r)
    daily = []
    for g in sorted(by_day):
        n_, h_, ap_, gn_, gh_ = agg_block(by_day[g])
        daily.append({"giorno": g.isoformat(), "n": n_, "hits": h_, "hit_rate": rate(h_, n_),
                      "avg_prob": ap_, "good_n": gn_, "good_hit_rate": rate(gh_, gn_)})

    # by_market
    by_mkt: dict[str, list] = {}
    for r in b:
        by_mkt.setdefault(r["market"], []).append(r)
    by_market = []
    for m in sorted(by_mkt):
        n_, h_, ap_, gn_, gh_ = agg_block(by_mkt[m])
        by_market.append({"market": m, "n": n_, "hits": h_, "hit_rate": rate(h_, n_),
                          "avg_prob": ap_, "good_n": gn_, "good_hit_rate": rate(gh_, gn_)})

    # by_market_day (heatmap)
    by_md: dict[tuple, list] = {}
    for r in b:
        by_md.setdefault((r["market"], giorno_of(r["kickoff"])), []).append(r)
    by_market_day = []
    for (m, g) in sorted(by_md, key=lambda k: (k[0], k[1])):
        valid = [r for r in by_md[(m, g)] if r["hit"] is not None]
        n_ = len(valid); h_ = sum(1 for r in valid if r["hit"])
        by_market_day.append({"market": m, "giorno": g.isoformat(), "n": n_, "hit_rate": rate(h_, n_)})

    # by_league
    by_lg: dict = {}
    for r in b:
        by_lg.setdefault(r["league_id"], []).append(r)
    by_league = []
    for lid in sorted(by_lg, key=lambda x: (x is None, x if x is not None else 0)):
        items = by_lg[lid]
        n_, h_, ap_, gn_, gh_ = agg_block(items)
        lname = next((r["league_name"] for r in items if r["league_name"] is not None), None)
        by_league.append({"league_id": lid, "league_name": lname, "n": n_, "hits": h_,
                          "hit_rate": rate(h_, n_), "avg_prob": ap_, "good_n": gn_,
                          "good_hit_rate": rate(gh_, gn_)})

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

    return {"kpi": kpi, "daily": daily, "by_market": by_market,
            "by_market_day": by_market_day, "by_league": by_league, "leagues": leagues}


def oracle_matches(rows, league_id, only_good):
    base_all = argmax_directions(rows)
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
        any_r = items[0]
        res.append({
            "fixture_id": fid,
            "giorno": giorno_of(any_r["kickoff"]).isoformat(),
            "league_id": max(r["league_id"] for r in items),
            "home_team": any_r["home_team"], "away_team": any_r["away_team"],
            "dir_tot": len(valid), "dir_ok": sum(1 for r in valid if r["hit"]),
            "good_tot": len(good_valid), "good_ok": sum(1 for r in good_valid if r["hit"]),
        })
    return {r["fixture_id"]: r for r in res}


# --------------------------------------------------------------------------- compare
def cmp_report(label, rpc, ora):
    print(f"\n=== (a) get_direction_report — {label} ===")
    # KPI
    for k in ("n", "hits", "hit_rate", "avg_prob", "calib_gap", "wilson_low",
              "wilson_high", "good_n", "good_hits", "good_hit_rate"):
        cmp_field(f"kpi.{k}", rpc["kpi"].get(k), ora["kpi"][k])
    # array allineati
    for arr, key in (("daily", "giorno"), ("by_market", "market"),
                     ("by_league", "league_id")):
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
        for f in ("dir_tot", "dir_ok", "good_tot", "good_ok", "giorno", "home_team", "away_team"):
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


def cmp_fixture(fid, rows):
    """(d) get_direction_report_fixture: argmax per mercato di UNA partita + hit."""
    rpc = sb.rpc("get_direction_report_fixture", {"p_fixture_id": fid}).execute().data
    # oracolo: argmax per mercato sulle righe di questa fixture
    frows = [r for r in rows if r["fixture_id"] == fid]
    by_mkt: dict = {}
    for r in frows:
        by_mkt.setdefault(r["market"], []).append(r)
    ora = []
    for m in sorted(by_mkt):
        cand = sorted(by_mkt[m], key=lambda r: (r["prob"] is None, -(r["prob"] or 0.0), r["selection"]))[0]
        ora.append({"market": m, "selection": cand["selection"], "prob": cand["prob"],
                    "n_engines_agree": cand["n_engines_agree"], "hit": cand["hit"]})
    rpc_rows = rpc.get("rows", [])
    if len(rpc_rows) != len(ora):
        fail(f"fixture[{fid}]: righe RPC={len(rpc_rows)} oracolo={len(ora)}")
        return
    for rr, oo in zip(rpc_rows, ora):
        for f in ("market", "selection", "prob", "n_engines_agree", "hit"):
            cmp_field(f"fixture[{fid}].{oo['market']}.{f}", rr.get(f), oo[f])


def call_report(d_from, d_to, league_id, market, only_good):
    return sb.rpc("get_direction_report", {
        "p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
        "p_league_id": league_id, "p_market": market, "p_only_good": only_good,
    }).execute().data


def call_matches(d_from, d_to, league_id, market, only_good, limit=2000):
    return sb.rpc("get_direction_report_matches", {
        "p_from": d_from.isoformat(), "p_to": d_to.isoformat(),
        "p_league_id": league_id, "p_market": market, "p_only_good": only_good,
        "p_limit": limit,
    }).execute().data


def run_scenario(label, d_from, d_to, league_id=None, market=None, only_good=False, do_matches=False):
    rows = pull_rows(d_from, d_to, market)
    ora = oracle_report(rows, league_id, only_good)
    rpc = call_report(d_from, d_to, league_id, market, only_good)
    cmp_report(label, rpc, ora)
    cmp_hit_rederive(label, rows)
    if do_matches:
        rpc_m = call_matches(d_from, d_to, league_id, market, only_good)["rows"]
        ora_m = oracle_matches(rows, league_id, only_good)
        cmp_matches(label, rpc_m, ora_m)


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

    # scenario 7: drill fine per partita (3 fixtures del 24/06)
    print("\n=== (d) get_direction_report_fixture — drill 3 partite del 24/06 ===")
    rows24 = pull_rows(d24, d24, None)
    fids = sorted({r["fixture_id"] for r in rows24})[:3]
    nb = len(_fails)
    for fid in fids:
        cmp_fixture(fid, rows24)
    print(f"  {len(fids)} partite (7 direzioni cad.) confrontate")
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
