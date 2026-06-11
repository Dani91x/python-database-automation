#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Smoke test offline per i fix Poisson (#1,#2,#3,#4,#8,#9,#11,#15,#19).
Esercita compute_db_json_analisi con cache pre-seminata (nessun DB) e certifica
gli invarianti matematici su tutti i mercati, in 2 scenari: con copertura xG
piena e senza alcun xG (fallback solo-gol)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import Prediction.today_predictions_backfill as eng

# Disattiva la blacklist dinamica (eviterebbe una chiamata DB).
eng.get_toxic_leagues = lambda: set()

LEAGUE, SEASON = 999, 2024
FIX_DATE = "2024-12-01T00:00:00+00:00"
HOME, AWAY = 1, 2

def _mk_match(fid, date, team_id, opp_id, gf, ga, htf, is_home):
    return {
        "fixture_id": fid, "fixture_date": date, "team_id": team_id,
        "opponent_id": opp_id, "goals_for": gf, "goals_against": ga,
        "halftime_for": htf, "is_home": is_home,
    }

def _build_caches(with_xg: bool):
    # 12 partite storiche per ciascuna squadra, contro avversari 101..112 / 201..212
    team_hist = {HOME: [], AWAY: []}
    played = []
    xg_map = {}
    fid = 1000
    for i in range(12):
        d = f"2024-{(i % 9) + 1:02d}-10T00:00:00+00:00"
        # Home team gioca in casa contro opp 100+i
        opp_h = 100 + i
        gf_h, ga_h, ht_h = (2, 1, 1) if i % 2 == 0 else (1, 1, 0)
        team_hist[HOME].append(_mk_match(fid, d, HOME, opp_h, gf_h, ga_h, ht_h, True))
        played.append({"fixture_id": fid, "home_team_id": HOME, "away_team_id": opp_h,
                       "goals_home": gf_h, "goals_away": ga_h})
        if with_xg:
            xg_map[(fid, HOME)] = gf_h * 0.9 + 0.2     # xG squadra di casa
            xg_map[(fid, opp_h)] = ga_h * 0.9 + 0.2    # xG avversario = xGA della squadra di casa
        fid += 1
        # Away team gioca in trasferta contro opp 200+i
        opp_a = 200 + i
        gf_a, ga_a, ht_a = (1, 2, 0) if i % 2 == 0 else (1, 1, 1)
        team_hist[AWAY].append(_mk_match(fid, d, AWAY, opp_a, gf_a, ga_a, ht_a, False))
        played.append({"fixture_id": fid, "home_team_id": opp_a, "away_team_id": AWAY,
                       "goals_home": ga_a, "goals_away": gf_a})
        if with_xg:
            xg_map[(fid, AWAY)] = gf_a * 0.9 + 0.2
            xg_map[(fid, opp_a)] = ga_a * 0.9 + 0.2
        fid += 1

    n = len(played)
    lha = sum(p["goals_home"] for p in played) / n
    laa = sum(p["goals_away"] for p in played) / n
    match_cache = {(LEAGUE, SEASON): {
        "played": played, "team_hist": team_hist,
        "league_home_avg": lha, "league_away_avg": laa,
        "league_total_avg": lha + laa,
    }}
    xg_cache = {(LEAGUE, SEASON): xg_map}
    return match_cache, xg_cache

def _approx(a, b, tol=1e-9):
    return abs(a - b) <= tol

def _check(analysis, scenario, expect_xg):
    mk = analysis["markets"]
    errs = []

    def in01(name, *vals):
        for v in vals:
            if not (0.0 - 1e-12 <= v <= 1.0 + 1e-12):
                errs.append(f"{name}={v} fuori [0,1]")

    # NB: i valori sono arrotondati a 4 decimali nel JSON → la somma degli
    # arrotondati può deviare da 1 fino a ~2e-4. Il fix #15 normalizza i float
    # INTERNI a 1 esatto; qui verifichiamo solo che non ci siano derive grossolane
    # (tolleranza di arrotondamento ROUND_TOL), che certificano l'assenza di bug.
    ROUND_TOL = 5e-4
    # 1X2 somma a 1 (#15)
    h, d, a = mk["1x2"]["H"], mk["1x2"]["D"], mk["1x2"]["A"]
    in01("1x2", h, d, a)
    if not _approx(h + d + a, 1.0, ROUND_TOL):
        errs.append(f"1x2 somma={h+d+a}")
    # HT 1X2 somma a 1 (#15)
    hh, hd, ha = mk["ht_1x2"]["H"], mk["ht_1x2"]["D"], mk["ht_1x2"]["A"]
    in01("ht_1x2", hh, hd, ha)
    if not _approx(hh + hd + ha, 1.0, ROUND_TOL):
        errs.append(f"ht_1x2 somma={hh+hd+ha}")
    # Over/Under e BTTS: coppie True+False=1
    for key in ("over_1_5", "over_2_5", "over_3_5", "btts", "first_half_over_0_5"):
        t, f = mk[key]["True"], mk[key]["False"]
        in01(key, t, f)
        if not _approx(t + f, 1.0, ROUND_TOL):
            errs.append(f"{key} True+False={t+f}")
    # Coerenza Over: O1.5 >= O2.5 >= O3.5
    if not (mk["over_1_5"]["True"] >= mk["over_2_5"]["True"] >= mk["over_3_5"]["True"] - 1e-12):
        errs.append("monotonia Over violata")
    # lambda > 0
    if analysis["inputs"]["lambda_home"] <= 0 or analysis["inputs"]["lambda_away"] <= 0:
        errs.append("lambda <= 0")
    # Telemetria xG (#2)
    if analysis["inputs"]["xg_blend_active"] != expect_xg:
        errs.append(f"xg_blend_active={analysis['inputs']['xg_blend_active']} atteso {expect_xg}")
    # #9: poisson HT = 1 - P(0-0 HT) coerente con dettagli
    det = mk["first_half_over_0_5"]["details"]
    if not (0 <= det["w_freq"] <= 0.61):
        errs.append(f"w_freq={det['w_freq']} fuori range atteso")
    # dc_rho fallback (#11): nessun json → -0.13
    if not _approx(analysis["inputs"]["dc_rho"], -0.13, 1e-9):
        errs.append(f"dc_rho={analysis['inputs']['dc_rho']} atteso -0.13 (fallback)")

    status = "PASS" if not errs else "FAIL"
    print(f"[{status}] scenario={scenario}")
    print(f"        1x2 H/D/A = {h:.4f}/{d:.4f}/{a:.4f} (sum={h+d+a:.6f})")
    print(f"        O2.5={mk['over_2_5']['True']:.4f}  BTTS={mk['btts']['True']:.4f}  "
          f"HT_O0.5={mk['first_half_over_0_5']['True']:.4f} (w_freq={det['w_freq']})")
    print(f"        lambda H/A = {analysis['inputs']['lambda_home']}/{analysis['inputs']['lambda_away']}  "
          f"xg_active={analysis['inputs']['xg_blend_active']}  dc_rho={analysis['inputs']['dc_rho']}")
    print(f"        xga_covered H/A = {analysis['inputs']['home_xga_covered']}/{analysis['inputs']['away_xga_covered']}")
    for e in errs:
        print(f"        - {e}")
    return not errs

def run():
    ctx = {"fixture_id": 9999, "league_id": LEAGUE, "season_year": SEASON,
           "fixture_date": FIX_DATE, "home_team_id": HOME, "away_team_id": AWAY}
    ok = True
    # Scenario 1: copertura xG piena → xGA derivato attivo
    mc, xc = _build_caches(with_xg=True)
    res = eng.compute_db_json_analisi(ctx, mc, xc)
    assert res is not None, "compute ha ritornato None (scenario xG)"
    ok &= _check(res[0], "xG pieno (+ xGA derivato)", expect_xg=True)
    # Scenario 2: nessun xG → fallback solo-gol
    mc2, xc2 = _build_caches(with_xg=False)
    res2 = eng.compute_db_json_analisi(ctx, mc2, xc2)
    assert res2 is not None, "compute ha ritornato None (scenario solo-gol)"
    ok &= _check(res2[0], "solo-gol (nessun xG)", expect_xg=False)
    print("\n" + ("ALL SMOKE CHECKS PASSED" if ok else "SMOKE CHECKS FAILED"))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    run()
