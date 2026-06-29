"""build_inplay_intensity.py — calibra GLI EFFETTI IN-PLAY dai dati storici reali,
controllando i CONFOUND (forza-squadra e tempo). Produce ``inplay_intensity_by_league.json``.

Per LEGA (+ globale):
  game_state: leader_per_goal, chaser_per_goal
  red_card / yellow_card: carded_factor, opponent_factor

Metodo (solo SELECT, read-only):
  - GAME-STATE — EXPECTED-vs-ACTUAL con FORZA-SQUADRA come riferimento di sé stessa
    (team-fixed-effects): per ogni stato di scarto d, moltiplicatore
      m(d) = Σ_squadra gol_attuali(team,d) / Σ_squadra R(team)·esposizione(team,d)
    dove R(team) = tasso-gol PROPRIO della squadra (gol/esposizione su tutti gli stati).
    Così m(d)<1 a d>0 significa che la squadra, QUANDO È IN VANTAGGIO, segna sotto la
    PROPRIA media → effetto-stato puro, NON forza-squadra (il confound che dava +0.30).
  - CARTELLINI — rate gol prima/dopo il PRIMO cartellino della squadra, NORMALIZZATA
    NEL TEMPO con la CDF gol reale (gol/quota-attesa-di-gol nella finestra) → toglie il
    confound "nel 2º tempo si segna di più".
  - per-lega con SHRINKAGE empirical-Bayes verso il globale.

Esegui:  python build_inplay_intensity.py
"""
from __future__ import annotations
import json
import os
from collections import defaultdict

from db_client import get_supabase_client

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "inplay_intensity_by_league.json")
CDF_PATH = os.path.join(ROOT, "value_engine", "data", "goal_time_cdf.json")
PAGE = 1000
MAX_GOAL_ROWS = 250_000
MIN_FIX_LEAGUE = 150          # soglia fixture per stimare una lega
SHRINK_K = 4000.0            # shrinkage game-state (unità di esposizione)
SHRINK_K_CARD = 60.0         # shrinkage cartellini (n. eventi)
MIN_N_RED, MIN_N_YEL = 50, 200


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _reg_minute(m):
    m = _to_int(m)
    if m is None:
        return None
    return 1 if m < 1 else (90 if m > 90 else m)


def _load_goal_cdf():
    """CDF gol per minuto (0..90) per normalizzare i cartellini nel tempo."""
    try:
        with open(CDF_PATH, encoding="utf-8") as f:
            c = json.load(f)["cdf_by_minute"]
        if isinstance(c, list) and len(c) == 91:
            return c
    except Exception:
        pass
    return [m / 90.0 for m in range(91)]   # fallback lineare


def fetch_matches_for(fixture_ids) -> dict:
    """fixture_id -> (league_id, home, away, goals_home, goals_away) in batch .in_()."""
    sb = get_supabase_client()
    out, fids, B = {}, list(fixture_ids), 200
    for i in range(0, len(fids), B):
        r = (sb.table("matches")
             .select("fixture_id,league_id,home_team_id,away_team_id,goals_home,goals_away,status_short")
             .in_("fixture_id", fids[i:i + B]).execute())
        for x in (getattr(r, "data", None) or []):
            fid = x.get("fixture_id")
            if (fid is not None and x.get("status_short") in ("FT", "AET", "PEN")
                    and x.get("home_team_id") is not None and x.get("away_team_id") is not None):
                out[fid] = (x.get("league_id"), x.get("home_team_id"), x.get("away_team_id"),
                            _to_int(x.get("goals_home")) or 0, _to_int(x.get("goals_away")) or 0)
    return out


def fetch_events(event_type: str, detail_filter=None) -> dict:
    """fixture_id -> [(minute, team_id, detail)]. Paginazione KEYSET su id (no timeout)."""
    sb = get_supabase_client()
    out, n, last_id = defaultdict(list), 0, 0
    while n < MAX_GOAL_ROWS:
        r = (sb.table("match_events")
             .select("id,fixture_id,team_id,minute,detail")
             .eq("event_type", event_type)
             .gt("id", last_id).order("id").limit(PAGE).execute())
        rows = getattr(r, "data", None) or []
        if not rows:
            break
        for x in rows:
            last_id = x["id"]
            d = (x.get("detail") or "")
            if detail_filter and detail_filter.lower() not in d.lower():
                continue
            m = _reg_minute(x.get("minute"))
            fid, tid = x.get("fixture_id"), x.get("team_id")
            if m is None or fid is None or tid is None:
                continue
            out[fid].append((m, tid, d))
            n += 1
        if len(rows) < PAGE:
            break
    return out


def main() -> None:
    cdf = _load_goal_cdf()

    def share_before(rmin):
        return max(1e-6, cdf[max(0, min(90, int(rmin)))])

    def share_after(rmin):
        return max(1e-6, 1.0 - cdf[max(0, min(90, int(rmin)))])

    print("Carico gol / rossi / gialli (match_events, keyset)...")
    goals = fetch_events("Goal")
    reds = fetch_events("Card", detail_filter="Red")
    yellows = fetch_events("Card", detail_filter="Yellow")
    print(f"  fixture: gol={len(goals)} rossi={len(reds)} gialli={len(yellows)}")
    fids = set(goals) | set(reds) | set(yellows)
    print(f"Carico info-partita per {len(fids)} fixture in batch...")
    matches = fetch_matches_for(fids)
    print(f"  fixture risolte (FT): {len(matches)}")

    # ---- GAME-STATE per-squadra: gs[scope][team][lead] = [gol, esposizione] ----
    def _cell():
        return [0.0, 0.0]
    gs = defaultdict(lambda: defaultdict(lambda: defaultdict(_cell)))
    fixtures_per_league = defaultdict(int)
    processed = set()

    for fid, evs in goals.items():
        mi = matches.get(fid)
        if mi is None:
            continue
        lid, home, away, _gh, _ga = mi
        scopes = ["GLOBAL"] + ([str(lid)] if lid is not None else [])
        fixtures_per_league[str(lid)] += 1
        processed.add(fid)
        seq = []
        for (m, tid, det) in sorted(evs, key=lambda t: t[0]):
            side = "H" if tid == home else ("A" if tid == away else None)
            if side is None:
                continue
            if "own goal" in det.lower():
                side = "A" if side == "H" else "H"
            seq.append((m, side))
        sh = sa = 0
        prev = 0
        for (m, side) in seq + [(90, None)]:
            dur = max(0, m - prev)
            if dur > 0:
                for sk in scopes:
                    gs[sk][home][sh - sa][1] += dur
                    gs[sk][away][sa - sh][1] += dur
            if side is not None:
                lead = (sh - sa) if side == "H" else (sa - sh)
                team = home if side == "H" else away
                for sk in scopes:
                    gs[sk][team][lead][0] += 1
                if side == "H":
                    sh += 1
                else:
                    sa += 1
            prev = m
    # veri 0-0
    for fid, (lid, home, away, gh, ga) in matches.items():
        if fid in processed or (gh + ga) != 0:
            continue
        fixtures_per_league[str(lid)] += 1
        for sk in ["GLOBAL"] + ([str(lid)] if lid is not None else []):
            gs[sk][home][0][1] += 90.0
            gs[sk][away][0][1] += 90.0

    def game_state_coeffs(scope):
        teams = gs.get(scope) or {}
        actual = defaultdict(float)
        expected = defaultdict(float)
        for _team, byd in teams.items():
            tg = sum(v[0] for v in byd.values())
            te = sum(v[1] for v in byd.values())
            if te <= 0 or tg <= 0:
                continue
            R = tg / te                       # tasso PROPRIO della squadra
            for d, (g, e) in byd.items():
                actual[d] += g
                expected[d] += R * e          # gol attesi se segnasse al PROPRIO tasso

        def coef(states):
            num = den = 0.0
            for L in states:
                if expected.get(L, 0.0) > 0:
                    md = actual[L] / expected[L]   # m(d): >1 sopra la media, <1 sotto
                    w = expected[L]
                    num += w * (md - 1.0) / abs(L)
                    den += w
            return (num / den) if den > 0 else None

        leader_pg = coef((1, 2))               # in vantaggio: atteso <0
        chaser_pg = coef((-1, -2))             # in svantaggio: atteso >0
        if leader_pg is None or chaser_pg is None:
            return None
        return {"leader_per_goal": round(leader_pg, 4), "chaser_per_goal": round(chaser_pg, 4),
                "max_lead": 2, "late_amp": 0.0, "_w": round(expected.get(0, 0.0), 1)}

    # ---- CARTELLINI (rosso/giallo): rate gol prima/dopo, NORMALIZZATA NEL TEMPO ----
    def card_accum(card_events):
        acc = defaultdict(lambda: {"cgb": 0.0, "csb": 0.0, "cga": 0.0, "csa": 0.0,
                                   "ogb": 0.0, "osb": 0.0, "oga": 0.0, "osa": 0.0, "n": 0})
        for fid, clist in card_events.items():
            mi = matches.get(fid)
            if not clist or mi is None or fid not in processed:
                continue
            lid, home, away, _gh, _ga = mi
            scopes = ["GLOBAL"] + ([str(lid)] if lid is not None else [])
            first = {}
            for (m, tid, det) in sorted(clist, key=lambda t: t[0]):
                side = "H" if tid == home else ("A" if tid == away else None)
                if side and side not in first:
                    first[side] = m
            if not first:
                continue
            gseq = []
            for (m, tid, det) in (goals.get(fid) or []):
                if tid not in (home, away):
                    continue
                gsd = "H" if tid == home else "A"
                if "own goal" in det.lower():
                    gsd = "A" if gsd == "H" else "H"
                gseq.append((m, gsd))
            for side, rmin in first.items():
                opp = "A" if side == "H" else "H"
                sb_, sa_ = share_before(rmin), share_after(rmin)
                cgb = sum(1 for (m, s) in gseq if s == side and m <= rmin)
                cga = sum(1 for (m, s) in gseq if s == side and m > rmin)
                ogb = sum(1 for (m, s) in gseq if s == opp and m <= rmin)
                oga = sum(1 for (m, s) in gseq if s == opp and m > rmin)
                for sk in scopes:
                    a = acc[sk]
                    a["cgb"] += cgb; a["csb"] += sb_; a["cga"] += cga; a["csa"] += sa_
                    a["ogb"] += ogb; a["osb"] += sb_; a["oga"] += oga; a["osa"] += sa_
                    a["n"] += 1
        return acc

    def card_coeffs(acc, scope, min_n):
        a = acc.get(scope)
        if not a or a["n"] < min_n:
            return None
        # rate normalizzato nel tempo = gol / quota-attesa-di-gol nella finestra
        cb = a["cgb"] / a["csb"] if a["csb"] > 0 else 0.0
        ca = a["cga"] / a["csa"] if a["csa"] > 0 else 0.0
        ob = a["ogb"] / a["osb"] if a["osb"] > 0 else 0.0
        oa = a["oga"] / a["osa"] if a["osa"] > 0 else 0.0
        if min(cb, ca, ob, oa) <= 0:
            return None
        return {"carded_factor": round(ca / cb, 4), "opponent_factor": round(oa / ob, 4), "_n": a["n"]}

    red_acc, yel_acc = card_accum(reds), card_accum(yellows)
    glob_gs = game_state_coeffs("GLOBAL")
    glob_rc = card_coeffs(red_acc, "GLOBAL", MIN_N_RED)
    glob_yc = card_coeffs(yel_acc, "GLOBAL", MIN_N_YEL)

    def shrink(val, glob, w, k):
        if glob is None:
            return val
        if val is None:
            return glob
        return (w * val + k * glob) / (w + k)

    by_league = {}
    for lid_str, nfix in fixtures_per_league.items():
        if lid_str in ("None", "") or nfix < MIN_FIX_LEAGUE:
            continue
        node = {}
        gs_l = game_state_coeffs(lid_str)
        if glob_gs is not None and gs_l is not None:
            w = gs_l.get("_w", 0.0)
            node["game_state"] = {
                "leader_per_goal": round(shrink(gs_l["leader_per_goal"], glob_gs["leader_per_goal"], w, SHRINK_K), 4),
                "chaser_per_goal": round(shrink(gs_l["chaser_per_goal"], glob_gs["chaser_per_goal"], w, SHRINK_K), 4),
                "max_lead": 2, "late_amp": 0.0,
            }
        elif glob_gs is not None:
            node["game_state"] = {k: glob_gs[k] for k in ("leader_per_goal", "chaser_per_goal", "max_lead", "late_amp")}
        for sect, acc, glob_c, mn in (("red_card", red_acc, glob_rc, MIN_N_RED),
                                      ("yellow_card", yel_acc, glob_yc, MIN_N_YEL)):
            cl = card_coeffs(acc, lid_str, mn)
            if glob_c is not None and cl is not None:
                w = cl.get("_n", 0)
                node[sect] = {
                    "carded_factor": round(shrink(cl["carded_factor"], glob_c["carded_factor"], w, SHRINK_K_CARD), 4),
                    "opponent_factor": round(shrink(cl["opponent_factor"], glob_c["opponent_factor"], w, SHRINK_K_CARD), 4),
                }
            elif glob_c is not None:
                node[sect] = {k: glob_c[k] for k in ("carded_factor", "opponent_factor")}
        if node:
            by_league[lid_str] = node

    glob_node = {}
    if glob_gs is not None:
        glob_node["game_state"] = {k: glob_gs[k] for k in ("leader_per_goal", "chaser_per_goal", "max_lead", "late_amp")}
    if glob_rc is not None:
        glob_node["red_card"] = {k: glob_rc[k] for k in ("carded_factor", "opponent_factor")}
    if glob_yc is not None:
        glob_node["yellow_card"] = {k: glob_yc[k] for k in ("carded_factor", "opponent_factor")}

    result = {
        "generated_from": "match_events (team-fixed-effects + time-normalized)",
        "n_fixtures": len(matches),
        "n_leagues_calibrated": len(by_league),
        "global": glob_node,
        "by_league": by_league,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("\n=== RISULTATO (segni attesi: leader<0, chaser>0, carded_rosso<1) ===")
    print("GLOBAL game_state :", glob_node.get("game_state"))
    print("GLOBAL red_card   :", glob_node.get("red_card"))
    print("GLOBAL yellow_card:", glob_node.get("yellow_card"))
    print(f"leghe calibrate: {len(by_league)}")
    print(f"[OK] scritto {OUT}")


if __name__ == "__main__":
    main()
