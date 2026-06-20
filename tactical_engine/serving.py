"""Serving del Tactical Engine: predice le partite di una data e scrive su DB.

Funzione richiamabile `run_for_date(...)` usata sia dal motore giornaliero esistente
(`Prediction/today_predictions_backfill.py`, aggancio additivo) sia dalla CLI
`run_daily.py`. NON fa backfill storico: predice solo le partite della data data.

Per ogni lega con partite quel giorno:
  - fit Dixon-Coles (forze att/dif inferite) sulle partite GIOCATE PRIMA di quel
    giorno (leakage-free), vantaggio-campo per i club (neutro per i Mondiali);
  - predice ogni partita -> tutti i mercati;
  - UPSERT su fixture_predictions.tactical_engine_json (UPDATE se esiste, INSERT
    con status='ok' se manca; ht_predictions resta null -> nessuna interferenza
    con l'idempotenza del motore API).
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_client import get_supabase_client  # noqa: E402
from tactical_engine.dixon_coles import MatchScoreline  # noqa: E402
from tactical_engine.model import DixonColesModel, parse_iso  # noqa: E402

ENGINE_VERSION = "gsg-dc-z2-1.0"
METHOD = ("Dixon-Coles MLE + simmetria casa/trasferta + time-decay (forze inferite), "
          "fit leakage-free su partite precedenti")
PLAYED = ("FT", "AET", "PEN")
NEUTRAL_LEAGUES = {1}          # Mondiali: campo neutro
HALF_LIFE_CLUB = 420.0
HALF_LIFE_NEUTRAL = 1500.0
RIDGE = 0.08
MIN_PRIOR = 40

log = logging.getLogger("tactical_engine")


def _reg_goals(r):
    fh, fa = r.get("fulltime_home"), r.get("fulltime_away")
    if fh is not None and fa is not None:
        return int(fh), int(fa)
    gh, ga = r.get("goals_home"), r.get("goals_away")
    if gh is not None and ga is not None:
        return int(gh), int(ga)
    return None


def _ht_goals(r):
    hh, ha = r.get("halftime_home"), r.get("halftime_away")
    return (int(hh), int(ha)) if hh is not None and ha is not None else None


def _round_markets(m: Dict[str, float]) -> Dict[str, float]:
    return {k: round(float(v), 4) for k, v in m.items()}


def _load_prior(sb, league_id: int, before: datetime, half_life_days: float = HALF_LIFE_CLUB):
    # Limite inferiore: oltre ~4 emivite il peso time-decay e' <7% -> trascurabile.
    # Bound la query (perf: evita di caricare 15 anni di storico su leghe vecchie).
    from math import log as _log
    cutoff = before - timedelta(days=4.0 * half_life_days / _log(2.0))
    rows = sb.table("matches").select(
        "fixture_date,status_short,home_team_id,away_team_id,"
        "goals_home,goals_away,halftime_home,halftime_away,fulltime_home,fulltime_away"
    ).eq("league_id", league_id).lt("fixture_date", before.isoformat()).gte(
        "fixture_date", cutoff.isoformat()).execute().data
    ft_m: List[MatchScoreline] = []
    ft_d: List[datetime] = []
    ht_m: List[MatchScoreline] = []
    ht_d: List[datetime] = []
    for r in rows:
        if (r["status_short"] not in PLAYED or not r["fixture_date"]
                or not r["home_team_id"] or not r["away_team_id"]):
            continue
        rg = _reg_goals(r)
        if rg is None:
            continue
        d = parse_iso(r["fixture_date"])
        ft_m.append(MatchScoreline(r["home_team_id"], r["away_team_id"], rg[0], rg[1]))
        ft_d.append(d)
        hg = _ht_goals(r)
        if hg is not None:
            ht_m.append(MatchScoreline(r["home_team_id"], r["away_team_id"], hg[0], hg[1]))
            ht_d.append(d)
    return ft_m, ft_d, ht_m, ht_d


def _build_payload(fx, pf, ph, st, fit, neutral, generated_at) -> dict:
    hid, aid = fx["home_team_id"], fx["away_team_id"]
    return {
        "engine_version": ENGINE_VERSION,
        "method": METHOD,
        "generated_at": generated_at,
        "league_id": fx["league_id"],
        "league_name": fx.get("league_name"),
        "fixture_id": fx["fixture_id"],
        "season_year": fx.get("season_year"),
        "date": fx["fixture_date"],
        "status": fx["status_short"],
        "home_name": fx.get("home_team_name"),
        "away_name": fx.get("away_team_name"),
        "neutral": neutral,
        "exp_goals_home": round(pf["exp_goals_home"], 3),
        "exp_goals_away": round(pf["exp_goals_away"], 3),
        "lambda_home": round(pf["lambda_home"], 3),
        "lambda_away": round(pf["lambda_away"], 3),
        "markets": _round_markets(pf["markets"]),
        "markets_ht": _round_markets(ph["markets"]) if ph else None,
        "top_scores": [{"h": x, "a": y, "p": round(p, 4)} for x, y, p in pf["top_scores"]],
        "strength_home": {"att": round(st[hid]["att"], 3), "def_factor": round(st[hid]["def_factor"], 3)},
        "strength_away": {"att": round(st[aid]["att"], 3), "def_factor": round(st[aid]["def_factor"], 3)},
        "training": {"n_matches": fit.n_matches, "eff_matches": round(fit.eff_matches, 1),
                     "converged": fit.converged, "rho": round(fit.rho, 4),
                     "home_adv": round(fit.home_adv, 4),
                     "half_life_days": HALF_LIFE_NEUTRAL if neutral else HALF_LIFE_CLUB, "ridge": RIDGE},
        "actual": None,
        "predicted_correct_1x2": None,
    }


def run_for_date(target_date: Optional[str] = None, max_leagues: int = 0) -> dict:
    """Predice le partite della data (default oggi UTC) e fa upsert su DB.
    Ritorna un riepilogo. Non solleva: logga e ritorna in caso di errore globale."""
    day = (datetime.fromisoformat(target_date).date() if target_date
           else datetime.now(timezone.utc).date())
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    generated_at = datetime.now(timezone.utc).isoformat()
    log.info("[tactical_engine] partite del %s (UTC)", day.isoformat())

    sb = get_supabase_client()
    # NB: la tabella `matches` NON ha la colonna league_name (solo league_id).
    today = sb.table("matches").select(
        "fixture_id,league_id,season_year,fixture_date,status_short,"
        "home_team_id,home_team_name,away_team_id,away_team_name"
    ).gte("fixture_date", start.isoformat()).lt("fixture_date", end.isoformat()).execute().data
    today = [r for r in today if r.get("home_team_id") and r.get("away_team_id")
             and r["status_short"] not in PLAYED]
    log.info("[tactical_engine] partite di oggi da predire: %d", len(today))
    if not today:
        return {"fixtures": 0, "updated": 0, "inserted": 0}

    by_league: Dict[int, list] = {}
    for r in today:
        by_league.setdefault(r["league_id"], []).append(r)
    leagues = list(by_league)
    if max_leagues:
        leagues = leagues[:max_leagues]

    upserts: List[dict] = []
    skipped_leagues = skipped_fixtures = 0
    for lid in leagues:
        neutral = lid in NEUTRAL_LEAGUES
        hl = HALF_LIFE_NEUTRAL if neutral else HALF_LIFE_CLUB
        try:
            ft_m, ft_d, ht_m, ht_d = _load_prior(sb, lid, start, half_life_days=hl)
        except Exception as e:  # noqa: BLE001
            log.warning("[tactical_engine] lega %s: errore storico: %s", lid, e)
            skipped_leagues += 1
            continue
        if len(ft_m) < MIN_PRIOR:
            skipped_leagues += 1
            continue
        try:
            mft = DixonColesModel(max_goals=10, half_life_days=hl, ridge=RIDGE)
            fit = mft.fit(ft_m, dates=ft_d, ref_date=start, fit_home_adv=not neutral)
            mht = None
            if len(ht_m) >= MIN_PRIOR:
                mht = DixonColesModel(max_goals=8, half_life_days=hl, ridge=RIDGE)
                mht.fit(ht_m, dates=ht_d, ref_date=start, fit_home_adv=not neutral)
        except Exception as e:  # noqa: BLE001
            log.warning("[tactical_engine] lega %s: errore fit: %s", lid, e)
            skipped_leagues += 1
            continue

        st = {row["team_id"]: row for row in mft.strength_table()}
        for fx in by_league[lid]:
            hid, aid = fx["home_team_id"], fx["away_team_id"]
            if hid not in mft._idx or aid not in mft._idx:
                skipped_fixtures += 1
                continue
            pf = mft.predict(hid, aid, neutral=neutral)
            ph = mht.predict(hid, aid, neutral=neutral) if (mht and hid in mht._idx and aid in mht._idx) else None
            upserts.append({"fixture_id": fx["fixture_id"],
                            "tactical_engine_json": _build_payload(fx, pf, ph, st, fit, neutral, generated_at)})

    log.info("[tactical_engine] predizioni: %d (fixture saltate: %d, leghe saltate: %d)",
             len(upserts), skipped_fixtures, skipped_leagues)
    if not upserts:
        return {"fixtures": 0, "updated": 0, "inserted": 0}

    ids = [u["fixture_id"] for u in upserts]
    existing = set()
    for i in range(0, len(ids), 100):
        rs = sb.table("fixture_predictions").select("fixture_id").in_("fixture_id", ids[i:i + 100]).execute().data
        existing.update(r["fixture_id"] for r in rs)
    n_upd = n_ins = n_err = 0
    for u in upserts:
        if u["fixture_id"] in existing:
            try:
                resp = sb.table("fixture_predictions").update(
                    {"tactical_engine_json": u["tactical_engine_json"]}).eq("fixture_id", u["fixture_id"]).execute()
                if getattr(resp, "data", None):
                    n_upd += 1
                else:
                    n_err += 1
                    log.warning("[tactical_engine] UPDATE senza effetto fixture_id=%s", u["fixture_id"])
            except Exception as e:  # noqa: BLE001
                n_err += 1
                log.warning("[tactical_engine] UPDATE fallito fixture_id=%s: %s", u["fixture_id"], e)
    ins = [{"fixture_id": u["fixture_id"], "status": "ok", "tactical_engine_json": u["tactical_engine_json"]}
           for u in upserts if u["fixture_id"] not in existing]
    for i in range(0, len(ins), 100):
        batch = ins[i:i + 100]
        try:
            sb.table("fixture_predictions").insert(batch).execute()
            n_ins += len(batch)
        except Exception as e:  # noqa: BLE001
            n_err += len(batch)
            log.warning("[tactical_engine] INSERT batch fallito (%d righe): %s", len(batch), e)
    log.info("[tactical_engine] scritte: %d aggiornate, %d inserite, %d errori", n_upd, n_ins, n_err)
    return {"fixtures": len(upserts), "updated": n_upd, "inserted": n_ins, "errors": n_err}
