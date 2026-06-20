"""Genera le predizioni World Cup del Tactical Engine e le scrive sul DB.

Scrive nella colonna `tactical_engine_json` della tabella `fixture_predictions`
(la stessa tabella degli altri motori: Poisson->db_json_analisi, ML->model_predictions_json).
UPSERT per fixture_id, inviando SOLO fixture_id + tactical_engine_json: non tocca
le colonne degli altri motori.

Per OGNI partita la previsione e' LEAKAGE-FREE: modello addestrato solo sulle
partite con data STRETTAMENTE precedente (walk-forward per giorno-cutoff).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_client import get_supabase_client  # noqa: E402
from tactical_engine.dixon_coles import MatchScoreline  # noqa: E402
from tactical_engine.model import DixonColesModel, parse_iso  # noqa: E402

LEAGUE_ID = 1
ENGINE_VERSION = "gsg-dc-z2-1.0"
METHOD = ("Dixon-Coles MLE + simmetria casa/trasferta (Z2, campo neutro) + time-decay, "
          "walk-forward leakage-free")
HALF_LIFE = 2200.0
RIDGE = 0.15
MIN_PRIOR_MATCHES = 24
NEUTRAL = True
PLAYED = ("FT", "AET", "PEN")


def reg_goals(r):
    fh, fa = r.get("fulltime_home"), r.get("fulltime_away")
    if fh is not None and fa is not None:
        return int(fh), int(fa)
    gh, ga = r.get("goals_home"), r.get("goals_away")
    if gh is not None and ga is not None:
        return int(gh), int(ga)
    return None


def ht_goals(r):
    hh, ha = r.get("halftime_home"), r.get("halftime_away")
    return (int(hh), int(ha)) if hh is not None and ha is not None else None


def outcome(h, a):
    return "1" if h > a else ("X" if h == a else "2")


def round_markets(m: Dict[str, float]) -> Dict[str, float]:
    return {k: round(float(v), 4) for k, v in m.items()}


def main() -> int:
    sb = get_supabase_client()
    rows = sb.table("matches").select(
        "fixture_id,league_id,season_year,fixture_date,status_short,"
        "home_team_id,home_team_name,away_team_id,away_team_name,"
        "goals_home,goals_away,halftime_home,halftime_away,fulltime_home,fulltime_away"
    ).eq("league_id", LEAGUE_ID).execute().data

    hist = []
    for r in rows:
        if r["status_short"] in PLAYED and r["fixture_date"] and r["home_team_id"] and r["away_team_id"]:
            rg = reg_goals(r)
            if rg is None:
                continue
            d = parse_iso(r["fixture_date"])
            hist.append({"date": d,
                         "ft": MatchScoreline(r["home_team_id"], r["away_team_id"], rg[0], rg[1]),
                         "ht": MatchScoreline(r["home_team_id"], r["away_team_id"], *ht_goals(r)) if ht_goals(r) else None})
    hist.sort(key=lambda x: x["date"])

    generated_at = datetime.now(timezone.utc).isoformat()
    upserts: List[dict] = []
    fit_cache: Dict[str, tuple] = {}
    n_done = 0
    graded_correct = 0
    graded_total = 0

    for r in rows:
        if not r["fixture_date"] or not r["home_team_id"] or not r["away_team_id"]:
            continue
        fdate = parse_iso(r["fixture_date"])
        # cutoff a INIZIO giornata: esclude SEMPRE le partite dello stesso giorno
        # (no leakage intra-giornata tra match con orari diversi nello stesso giorno).
        fday = fdate.replace(hour=0, minute=0, second=0, microsecond=0)
        prior = [h for h in hist if h["date"] < fday]
        if len(prior) < MIN_PRIOR_MATCHES:
            continue
        seen = {m.home_id for m in (h["ft"] for h in prior)} | {m.away_id for m in (h["ft"] for h in prior)}
        if r["home_team_id"] not in seen or r["away_team_id"] not in seen:
            continue

        day = fday.strftime("%Y-%m-%d")
        if day not in fit_cache:
            mft = DixonColesModel(max_goals=10, half_life_days=HALF_LIFE, ridge=RIDGE)
            mft.fit([h["ft"] for h in prior], dates=[h["date"] for h in prior],
                    ref_date=fday, fit_home_adv=False)
            ht_pairs = [(h["ht"], h["date"]) for h in prior if h["ht"] is not None]
            mht = None
            if len(ht_pairs) >= MIN_PRIOR_MATCHES:
                mht = DixonColesModel(max_goals=8, half_life_days=HALF_LIFE, ridge=RIDGE)
                mht.fit([p[0] for p in ht_pairs], dates=[p[1] for p in ht_pairs],
                        ref_date=fday, fit_home_adv=False)
            fit_cache[day] = (mft, mht)
        mft, mht = fit_cache[day]

        hid, aid = r["home_team_id"], r["away_team_id"]
        if hid not in mft._idx or aid not in mft._idx:
            continue
        pf = mft.predict(hid, aid, neutral=NEUTRAL)
        ph = mht.predict(hid, aid, neutral=NEUTRAL) if (mht and hid in mht._idx and aid in mht._idx) else None
        st = {row["team_id"]: row for row in mft.strength_table()}

        actual = None
        correct = None
        if r["status_short"] in PLAYED:
            rg = reg_goals(r)
            if rg is not None:
                actual = {"home_goals": rg[0], "away_goals": rg[1], "outcome": outcome(rg[0], rg[1])}
                pred_out = max([("1", pf["markets"]["home"]), ("X", pf["markets"]["draw"]),
                                ("2", pf["markets"]["away"])], key=lambda t: t[1])[0]
                correct = (pred_out == actual["outcome"])
                graded_total += 1
                graded_correct += 1 if correct else 0

        payload = {
            "engine_version": ENGINE_VERSION,
            "method": METHOD,
            "generated_at": generated_at,
            "league_id": LEAGUE_ID,
            "league_name": "World Cup",
            "fixture_id": r["fixture_id"],
            "season_year": r["season_year"],
            "date": r["fixture_date"],
            "status": r["status_short"],
            "home_name": r["home_team_name"],
            "away_name": r["away_team_name"],
            "neutral": NEUTRAL,
            "exp_goals_home": round(pf["exp_goals_home"], 3),
            "exp_goals_away": round(pf["exp_goals_away"], 3),
            "lambda_home": round(pf["lambda_home"], 3),
            "lambda_away": round(pf["lambda_away"], 3),
            "markets": round_markets(pf["markets"]),
            "markets_ht": round_markets(ph["markets"]) if ph else None,
            "top_scores": [{"h": x, "a": y, "p": round(p, 4)} for x, y, p in pf["top_scores"]],
            "strength_home": {"att": round(st[hid]["att"], 3), "def_factor": round(st[hid]["def_factor"], 3)},
            "strength_away": {"att": round(st[aid]["att"], 3), "def_factor": round(st[aid]["def_factor"], 3)},
            "training": {"n_matches": mft.fit_.n_matches, "eff_matches": round(mft.fit_.eff_matches, 1),
                         "converged": mft.fit_.converged, "rho": round(mft.fit_.rho, 4),
                         "half_life_days": HALF_LIFE, "ridge": RIDGE},
            "actual": actual,
            "predicted_correct_1x2": correct,
        }
        upserts.append({"fixture_id": r["fixture_id"], "tactical_engine_json": payload})
        n_done += 1

    # Quali fixture hanno gia' una riga in fixture_predictions (per non interferire
    # con gli altri motori): le esistenti -> solo UPDATE della colonna nuova; le
    # nuove -> INSERT con status='ok' (ma ht_predictions resta null, quindi il motore
    # API NON le salta: prediction_already_done richiede status='ok' AND ht_predictions).
    all_ids = [u["fixture_id"] for u in upserts]
    existing = set()
    for i in range(0, len(all_ids), 100):
        chunk = all_ids[i:i + 100]
        rs = sb.table("fixture_predictions").select("fixture_id").in_("fixture_id", chunk).execute().data
        existing.update(r["fixture_id"] for r in rs)

    to_update = [u for u in upserts if u["fixture_id"] in existing]
    to_insert = [u for u in upserts if u["fixture_id"] not in existing]

    # UPDATE righe esistenti: SOLO tactical_engine_json (non tocca status/db_json_analisi/...)
    for u in to_update:
        sb.table("fixture_predictions").update(
            {"tactical_engine_json": u["tactical_engine_json"]}
        ).eq("fixture_id", u["fixture_id"]).execute()

    # INSERT righe nuove a blocchi
    ins_rows = [{"fixture_id": u["fixture_id"], "status": "ok",
                 "tactical_engine_json": u["tactical_engine_json"]} for u in to_insert]
    for i in range(0, len(ins_rows), 100):
        sb.table("fixture_predictions").insert(ins_rows[i:i + 100]).execute()

    print(f"  aggiornate {len(to_update)} righe esistenti, inserite {len(to_insert)} righe nuove")
    print(f"\nScritte {n_done} predizioni leakage-free su fixture_predictions.tactical_engine_json")
    if graded_total:
        print(f"Accuratezza 1X2 (su {graded_total} partite giocate, leakage-free): "
              f"{graded_correct / graded_total:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
