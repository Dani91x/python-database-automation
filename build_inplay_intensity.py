"""build_inplay_intensity.py — calibra GLI EFFETTI IN-PLAY dai dati storici reali.

Produce ``inplay_intensity_by_league.json`` con, per LEGA (+ globale), i coefficienti
usati dal motore Poisson live (live_engine.inplay_residual_rates):

  game_state: leader_per_goal, chaser_per_goal  (variazione % della rate di gol
              della squadra in vantaggio/svantaggio, per gol di scarto)
  red_card  : carded_factor, opponent_factor    (rapporto rate dopo/prima del rosso
              per la squadra punita e per l'avversaria)

Metodo (solo SELECT, read-only):
  - spine = ``matches`` (FT/AET/PEN) -> (league, home_id, away_id);
  - timeline gol da ``match_events`` (event_type=Goal, gestendo gli autogol);
  - GAME-STATE: per ogni intervallo tra gol, esposizione (team-minuti) per stato di
    scarto e gol attribuiti allo stato PRE-gol dello scorer -> rate(stato)/rate(0);
  - RED-CARD: per ogni primo rosso, rate gol prima/dopo della squadra punita e
    dell'avversaria;
  - aggregazione per-lega + globale, SHRINKAGE empirical-Bayes verso il globale.

Esegui:  python build_inplay_intensity.py
"""
from __future__ import annotations
import json
import os
from collections import defaultdict

from db_client import get_supabase_client

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inplay_intensity_by_league.json")
PAGE = 1000
MAX_GOAL_ROWS = 200_000      # campione ampio per una calibrazione stabile
MIN_FIXtur_LEAGUE = 150      # soglia fixture per stimare una lega (sotto -> solo globale)
SHRINK_K = 4000.0            # team-minuti-equivalenti del prior globale (game-state)
SHRINK_K_RED = 60.0          # rossi-equivalenti del prior globale (red-card)


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


def fetch_matches_for(fixture_ids) -> dict:
    """fixture_id -> (league_id, home_id, away_id, goals_home, goals_away) per le SOLE
    fixture date, in batch mirati ``.in_()`` (niente scan dell'intera tabella → niente timeout)."""
    sb = get_supabase_client()
    out = {}
    fids = list(fixture_ids)
    BATCH = 200
    for i in range(0, len(fids), BATCH):
        chunk = fids[i:i + BATCH]
        r = (sb.table("matches")
             .select("fixture_id,league_id,home_team_id,away_team_id,goals_home,goals_away,status_short")
             .in_("fixture_id", chunk).execute())
        for x in (getattr(r, "data", None) or []):
            fid = x.get("fixture_id")
            if (fid is not None and x.get("status_short") in ("FT", "AET", "PEN")
                    and x.get("home_team_id") is not None and x.get("away_team_id") is not None):
                out[fid] = (x.get("league_id"), x.get("home_team_id"), x.get("away_team_id"),
                            _to_int(x.get("goals_home")) or 0, _to_int(x.get("goals_away")) or 0)
    return out


def fetch_events(event_type: str, detail_filter=None) -> dict:
    """fixture_id -> [(minute, team_id, detail)] per il tipo evento dato.

    Paginazione KEYSET su ``id`` (id > last): usa l'indice PK, niente OFFSET profondo
    → evita i timeout su tabelle enormi (match_events >1M righe).
    """
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
    print("Carico gol (match_events)...")
    goals = fetch_events("Goal")
    print(f"  fixture con gol: {len(goals)}")
    print("Carico cartellini rossi...")
    reds = fetch_events("Card", detail_filter="Red")
    print(f"  fixture con rosso: {len(reds)}")
    fids = set(goals) | set(reds)
    print(f"Carico info-partita (league/teams/score) per {len(fids)} fixture in batch...")
    matches = fetch_matches_for(fids)
    print(f"  fixture risolte (FT): {len(matches)}")

    # --- GAME STATE: esposizione (team-minuti) e gol per stato di scarto ---
    # accumulatori: [scope][lead] -> exposure ; [scope][lead] -> goals
    g_exp = defaultdict(lambda: defaultdict(float))
    g_goal = defaultdict(lambda: defaultdict(float))
    fixtures_per_league = defaultdict(int)

    processed = set()
    # (1) fixture con gol REALMENTE recuperati -> timeline completa
    for fid, evs in goals.items():
        mi = matches.get(fid)
        if mi is None:
            continue
        lid, home, away, _gh, _ga = mi
        scope_keys = ["GLOBAL"] + ([str(lid)] if lid is not None else [])
        fixtures_per_league[str(lid)] += 1
        processed.add(fid)
        seq = []
        for (m, tid, det) in sorted(evs, key=lambda t: t[0]):
            side = "H" if tid == home else ("A" if tid == away else None)
            if side is None:
                continue
            if "own goal" in det.lower():     # autogol: punto all'altra squadra
                side = "A" if side == "H" else "H"
            seq.append((m, side))
        # timeline esposizione + gol per stato
        sh = sa = 0
        prev = 0
        for (m, side) in seq + [(90, None)]:
            dur = max(0, m - prev)
            if dur > 0:
                for sk in scope_keys:
                    g_exp[sk][sh - sa] += dur   # esposizione CASA allo stato (sh-sa)
                    g_exp[sk][sa - sh] += dur   # esposizione TRASF. allo stato (sa-sh)
            if side is not None:
                scorer_lead = (sh - sa) if side == "H" else (sa - sh)
                for sk in scope_keys:
                    g_goal[sk][scorer_lead] += 1
                if side == "H":
                    sh += 1
                else:
                    sa += 1
            prev = m

    # (2) veri 0-0 (gol totali = 0 in matches): 90' di esposizione a stato 0, nessun gol
    for fid, (lid, home, away, gh, ga) in matches.items():
        if fid in processed or (gh + ga) != 0:
            continue
        fixtures_per_league[str(lid)] += 1
        for sk in ["GLOBAL"] + ([str(lid)] if lid is not None else []):
            g_exp[sk][0] += 90.0 * 2  # entrambe le squadre 90' a scarto 0

    def game_state_coeffs(scope):
        exp, gl = g_exp[scope], g_goal[scope]
        base_exp, base_goal = exp.get(0, 0.0), gl.get(0, 0.0)
        if base_exp <= 0 or base_goal <= 0:
            return None
        base_rate = base_goal / base_exp
        def ratio(L):
            e = exp.get(L, 0.0)
            if e <= 0:
                return None
            return (gl.get(L, 0.0) / e) / base_rate
        # leader_per_goal: media pesata di (ratio(L)-1)/L per L>0 (1,2)
        num = den = 0.0
        for L in (1, 2):
            rt = ratio(L)
            if rt is not None:
                w = exp.get(L, 0.0)
                num += w * (rt - 1.0) / L
                den += w
        leader_pg = (num / den) if den > 0 else None
        num = den = 0.0
        for L in (-1, -2):
            rt = ratio(L)
            if rt is not None:
                w = exp.get(L, 0.0)
                num += w * (rt - 1.0) / abs(L)
                den += w
        chaser_pg = (num / den) if den > 0 else None
        if leader_pg is None or chaser_pg is None:
            return None
        return {"leader_per_goal": round(leader_pg, 4), "chaser_per_goal": round(chaser_pg, 4),
                "max_lead": 2, "late_amp": 0.0, "_exp": round(base_exp, 1)}

    glob_gs = game_state_coeffs("GLOBAL")

    # --- RED CARD: rate gol prima/dopo il primo rosso (punita + avversaria) ---
    # accumulatori: [scope] -> {carded:{goals_b,exp_b,goals_a,exp_a}, opp:{...}}
    rc = defaultdict(lambda: {"c_gb": 0.0, "c_eb": 0.0, "c_ga": 0.0, "c_ea": 0.0,
                              "o_gb": 0.0, "o_eb": 0.0, "o_ga": 0.0, "o_ea": 0.0, "n": 0})
    for fid, rlist in reds.items():
        mi = matches.get(fid)
        if not rlist or mi is None or fid not in processed:
            continue
        lid, home, away, _gh, _ga = mi
        scope_keys = ["GLOBAL"] + ([str(lid)] if lid is not None else [])
        # primo rosso per squadra
        first = {}
        for (m, tid, det) in sorted(rlist, key=lambda t: t[0]):
            side = "H" if tid == home else ("A" if tid == away else None)
            if side and side not in first:
                first[side] = m
        if not first:
            continue
        gseq_raw = []
        for (m, tid, det) in (goals.get(fid) or []):
            if tid not in (home, away):
                continue
            gside = "H" if tid == home else "A"
            if "own goal" in det.lower():     # autogol: punto all'altra squadra
                gside = "A" if gside == "H" else "H"
            gseq_raw.append((m, gside))
        gseq = sorted(gseq_raw, key=lambda t: t[0])
        for side, rmin in first.items():
            opp = "A" if side == "H" else "H"
            cg_b = sum(1 for (m, s) in gseq if s == side and m <= rmin)
            cg_a = sum(1 for (m, s) in gseq if s == side and m > rmin)
            og_b = sum(1 for (m, s) in gseq if s == opp and m <= rmin)
            og_a = sum(1 for (m, s) in gseq if s == opp and m > rmin)
            eb, ea = float(rmin), float(90 - rmin)
            if eb <= 0 or ea <= 0:
                continue
            for sk in scope_keys:
                a = rc[sk]
                a["c_gb"] += cg_b; a["c_eb"] += eb; a["c_ga"] += cg_a; a["c_ea"] += ea
                a["o_gb"] += og_b; a["o_eb"] += eb; a["o_ga"] += og_a; a["o_ea"] += ea
                a["n"] += 1

    def red_coeffs(scope):
        a = rc[scope]
        if a["n"] < 30 or min(a["c_gb"], a["c_ga"], a["o_gb"], a["o_ga"]) <= 0:
            return None
        carded = (a["c_ga"] / a["c_ea"]) / (a["c_gb"] / a["c_eb"])
        opp = (a["o_ga"] / a["o_ea"]) / (a["o_gb"] / a["o_eb"])
        return {"carded_factor": round(carded, 4), "opponent_factor": round(opp, 4), "_n": a["n"]}

    glob_rc = red_coeffs("GLOBAL")

    # --- per-lega con SHRINKAGE verso il globale ---
    def shrink(val, glob, w, k):
        if glob is None:
            return val
        if val is None:
            return glob
        return (w * val + k * glob) / (w + k)

    by_league = {}
    for lid_str, nfix in fixtures_per_league.items():
        if lid_str in ("None", "") or nfix < MIN_FIXtur_LEAGUE:
            continue
        gs_l = game_state_coeffs(lid_str)
        rc_l = red_coeffs(lid_str)
        node = {}
        if glob_gs is not None and gs_l is not None:
            w = gs_l.get("_exp", 0.0)
            node["game_state"] = {
                "leader_per_goal": round(shrink(gs_l["leader_per_goal"], glob_gs["leader_per_goal"], w, SHRINK_K), 4),
                "chaser_per_goal": round(shrink(gs_l["chaser_per_goal"], glob_gs["chaser_per_goal"], w, SHRINK_K), 4),
                "max_lead": 2, "late_amp": 0.0,
            }
        elif glob_gs is not None:
            node["game_state"] = {k: glob_gs[k] for k in ("leader_per_goal", "chaser_per_goal", "max_lead", "late_amp")}
        if glob_rc is not None and rc_l is not None:
            w = rc_l.get("_n", 0)
            node["red_card"] = {
                "carded_factor": round(shrink(rc_l["carded_factor"], glob_rc["carded_factor"], w, SHRINK_K_RED), 4),
                "opponent_factor": round(shrink(rc_l["opponent_factor"], glob_rc["opponent_factor"], w, SHRINK_K_RED), 4),
            }
        elif glob_rc is not None:
            node["red_card"] = {k: glob_rc[k] for k in ("carded_factor", "opponent_factor")}
        if node:
            by_league[lid_str] = node

    glob_node = {}
    if glob_gs is not None:
        glob_node["game_state"] = {k: glob_gs[k] for k in ("leader_per_goal", "chaser_per_goal", "max_lead", "late_amp")}
    if glob_rc is not None:
        glob_node["red_card"] = {k: glob_rc[k] for k in ("carded_factor", "opponent_factor")}

    result = {
        "generated_from": "match_events (storico reale)",
        "n_fixtures": len(matches),
        "n_leagues_calibrated": len(by_league),
        "global": glob_node,
        "by_league": by_league,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("\n=== RISULTATO ===")
    print("GLOBAL game_state:", glob_node.get("game_state"))
    print("GLOBAL red_card  :", glob_node.get("red_card"))
    print(f"leghe calibrate: {len(by_league)}")
    print(f"[OK] scritto {OUT}")


if __name__ == "__main__":
    main()
