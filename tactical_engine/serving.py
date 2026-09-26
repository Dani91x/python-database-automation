"""Serving del Tactical Engine: predice le partite di una data e scrive su DB.

Funzione richiamabile `run_for_date(...)` usata sia dal motore giornaliero esistente
(`Prediction/today_predictions_backfill.py`, aggancio additivo) sia dalla CLI
`run_daily.py`. NON fa backfill storico: predice solo le partite della data data.

Per ogni lega con partite quel giorno:
  - fit Dixon-Coles (forze att/dif inferite) sulle partite GIOCATE PRIMA di quel
    giorno (leakage-free), vantaggio-campo per i club (neutro per i Mondiali);
  - predice ogni partita -> tutti i mercati;
  - UPDATE di fixture_predictions.tactical_engine_json sulla riga della partita.

Fonte delle partite del giorno (25/09/2026, reperto R1 dell'audit tab Dashboard):
`fixture_predictions`, NON `matches`. In `matches` le partite del giorno entrano solo
in parte e in anticipo variabile (25/09: 33 su 263 fixture di oggi): leggere li' le
partite di oggi ne trovava poche e il motore ne saltava la gran parte in silenzio
(copertura misurata dal coordinatore: 34/263 oggi, 374/7.977 = 4,7 % su 14 gg).
`fixture_predictions` contiene TUTTE le partite del giorno (le scrive il loop Poisson
di today_predictions_backfill.py, che gira prima di questo motore), quindi la riga
esiste sempre: si fa solo UPDATE, nessun INSERT.

Paginazione (reperto R2): ogni lettura e' a pagine KEYSET su fixture_id (chiave
univoca -> ordine totale), pagine da PAGE_SIZE, uscita SOLO a pagina vuota (stessa
meccanica di generate_dynamic_cal.py / master_backtest.py). Lo storico e' poi messo in
ordine cronologico deterministico (fixture_date, fixture_id) prima del fit.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

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
PAGE_SIZE = 1000               # righe per pagina keyset (= max_rows di default di PostgREST)
PRIOR_COLS = ("fixture_id,fixture_date,status_short,home_team_id,away_team_id,"
              "goals_home,goals_away,halftime_home,halftime_away,fulltime_home,fulltime_away")
# Colonne di fixture_predictions per le partite del giorno. NB: la colonna `status`
# di fixture_predictions e' lo stato della PREDIZIONE API (ok/empty/no_coverage/
# error), NON lo stato della partita: lo stato partita e' `result_status_short`
# (scritto da predictions_results_backfill a partita finita, NULL prima). Il filtro
# "non giocata" di prima (matches.status_short NOT IN PLAYED) diventa quindi
# result_status_short NULL oppure NOT IN PLAYED.
TODAY_COLS = ("fixture_id,league_id,league_name,season_year,fixture_date,"
              "home_team_id,home_team_name,away_team_id,away_team_name,result_status_short")

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


def _leggi_keyset(costruisci: Callable[[], object], page_size: int = PAGE_SIZE) -> List[dict]:
    """Legge TUTTE le righe di una query a pagine keyset su fixture_id.

    `costruisci()` ritorna la query GIA' filtrata; qui si aggiungono il cursore
    (fixture_id > ultimo letto), l'ORDER BY fixture_id (ordine totale: fixture_id e'
    univoco sia in `matches` sia in `fixture_predictions`) e il LIMIT. Si esce SOLO a
    pagina vuota: fermarsi su "meno righe del limite" darebbe per finita la lettura
    anche quando e' il server a troncare la pagina (max_rows < page_size), perdendo
    righe in silenzio.
    """
    rows: List[dict] = []
    cursore: Optional[int] = None
    while True:
        q = costruisci()
        if cursore is not None:
            q = q.gt("fixture_id", cursore)
        batch = q.order("fixture_id").limit(page_size).execute().data or []
        if not batch:
            break
        rows.extend(batch)
        cursore = batch[-1]["fixture_id"]
    return rows


def _load_prior(sb, league_id: int, before: datetime, half_life_days: float = HALF_LIFE_CLUB,
                page_size: int = PAGE_SIZE):
    # Limite inferiore: oltre ~4 emivite il peso time-decay e' <7% -> trascurabile.
    # Bound la query (perf: evita di caricare 15 anni di storico su leghe vecchie).
    from math import log as _log
    cutoff = before - timedelta(days=4.0 * half_life_days / _log(2.0))
    rows = _leggi_keyset(lambda: sb.table("matches").select(PRIOR_COLS)
                         .eq("league_id", league_id)
                         .lt("fixture_date", before.isoformat())
                         .gte("fixture_date", cutoff.isoformat()),
                         page_size=page_size)
    # Ordine cronologico DETERMINISTICO (tiebreaker fixture_id: i kickoff simultanei
    # sono comuni). Il fit e' una somma pesata sulle partite e le squadre sono
    # indicizzate in ordine di id (model.fit): l'ordine delle righe cambia il
    # risultato solo per l'arrotondamento in virgola mobile; fissarlo rende il
    # risultato riproducibile fra un run e l'altro.
    rows.sort(key=lambda r: (r.get("fixture_date") or "", r.get("fixture_id") or 0))
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


def _load_today(sb, start: datetime, end: datetime) -> List[dict]:
    """Partite NON giocate del giorno [start, end) lette da fixture_predictions (R1).

    Ritorna righe nella forma interna usata da _build_payload: `status_short` =
    result_status_short (NULL prima del fischio d'inizio)."""
    rows = _leggi_keyset(lambda: sb.table("fixture_predictions").select(TODAY_COLS)
                         .gte("fixture_date", start.isoformat())
                         .lt("fixture_date", end.isoformat()))
    today = [dict(r, status_short=r.get("result_status_short")) for r in rows]
    return [r for r in today if r.get("home_team_id") and r.get("away_team_id")
            and r["status_short"] not in PLAYED]


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
    """Predice le partite della data (default oggi UTC) e aggiorna il DB.
    Ritorna un riepilogo. Non solleva: logga e ritorna in caso di errore globale."""
    day = (datetime.fromisoformat(target_date).date() if target_date
           else datetime.now(timezone.utc).date())
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    generated_at = datetime.now(timezone.utc).isoformat()
    log.info("[tactical_engine] partite del %s (UTC)", day.isoformat())

    sb = get_supabase_client()
    today = _load_today(sb, start, end)
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

    # La riga esiste sempre (e' quella letta sopra da fixture_predictions): solo UPDATE
    # della colonna del motore, nessun altro campo toccato. Un UPDATE senza effetto
    # (riga sparita fra lettura e scrittura) e' contato come errore, non ignorato.
    n_upd = n_err = 0
    for u in upserts:
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
    log.info("[tactical_engine] scritte: %d aggiornate, %d errori", n_upd, n_err)
    # "inserted" resta nel riepilogo (sempre 0) per non rompere chi lo legge o lo logga.
    return {"fixtures": len(upserts), "updated": n_upd, "inserted": 0, "errors": n_err}


# ---------------------------------------------------------------------------
# ESITO REALE (26/09/2026, KO9 del referto di fase 3 sessione B)
# ---------------------------------------------------------------------------
# _build_payload scrive "actual": None perche' predice solo partite NON giocate; nessun
# processo lo aggiornava a partita finita (233/5.976 payload con l'esito, tutti da
# generate_predictions.py offline) e il blocco "Esito reale (90')" della UI non compariva
# mai. run_esiti_reali, chiamata dallo STESSO job giornaliero subito dopo il motore
# (Prediction/today_predictions_backfill.py), completa i payload delle partite finite
# negli ultimi ACTUAL_LOOKBACK_DAYS giorni: stessa forma di generate_predictions.py
# ({"home_goals", "away_goals", "outcome": "1"|"X"|"2"} + predicted_correct_1x2 sull'argmax
# 1X2 del payload). Esito a 90': fulltime_* di matches; goals_* solo se lo stato e' FT
# (su AET/PEN i gol includono i supplementari: senza fulltime l'esito a 90' e' ignoto e
# NON si scrive). Si tocca SOLO tactical_engine_json, SOLO se actual e' ancora NULL.
ACTUAL_LOOKBACK_DAYS = 3
ACTUAL_COLS = "fixture_id,fixture_date,result_status_short,result_home_goals,result_away_goals"
MATCH_RESULT_COLS = "fixture_id,status_short,goals_home,goals_away,fulltime_home,fulltime_away"


def _esito_1x2(h: int, a: int) -> str:
    return "1" if h > a else ("X" if h == a else "2")


def _gol_90(stato: Optional[str], match: Optional[dict], fp_row: dict):
    """(casa, ospite) a 90' o None se non noto con certezza."""
    if match is not None:
        fh, fa = match.get("fulltime_home"), match.get("fulltime_away")
        if fh is not None and fa is not None:
            return int(fh), int(fa)
        gh, ga = match.get("goals_home"), match.get("goals_away")
        if match.get("status_short") == "FT" and gh is not None and ga is not None:
            return int(gh), int(ga)
    rh, ra = fp_row.get("result_home_goals"), fp_row.get("result_away_goals")
    if stato == "FT" and rh is not None and ra is not None:
        return int(rh), int(ra)
    return None


def run_esiti_reali(target_date: Optional[str] = None) -> dict:
    """Scrive l'esito reale sui payload TacticAI delle partite finite di
    [giorno - ACTUAL_LOOKBACK_DAYS, giorno + 1). Non solleva: errori per partita contati."""
    day = (datetime.fromisoformat(target_date).date() if target_date
           else datetime.now(timezone.utc).date())
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    since = start - timedelta(days=ACTUAL_LOOKBACK_DAYS)
    end = start + timedelta(days=1)
    sb = get_supabase_client()
    rows = _leggi_keyset(lambda: sb.table("fixture_predictions").select(ACTUAL_COLS)
                         .gte("fixture_date", since.isoformat())
                         .lt("fixture_date", end.isoformat()))
    finite = [r for r in rows if r.get("result_status_short") in PLAYED]
    res = {"finite": len(finite), "scritti": 0, "gia_presenti": 0, "senza_payload": 0,
           "senza_esito_90": 0, "errori": 0}
    for r in finite:
        fid = r["fixture_id"]
        try:
            righe = (sb.table("fixture_predictions").select("fixture_id,tactical_engine_json")
                     .eq("fixture_id", fid).limit(1).execute().data or [])
            payload = righe[0].get("tactical_engine_json") if righe else None
            if not isinstance(payload, dict):
                res["senza_payload"] += 1
                continue
            if payload.get("actual") is not None:
                res["gia_presenti"] += 1
                continue
            m = (sb.table("matches").select(MATCH_RESULT_COLS)
                 .eq("fixture_id", fid).limit(1).execute().data or [])
            gol = _gol_90(r.get("result_status_short"), m[0] if m else None, r)
            if gol is None:
                res["senza_esito_90"] += 1
                continue
            esito = _esito_1x2(*gol)
            mk = payload.get("markets") or {}
            corretto = None
            if all(isinstance(mk.get(k), (int, float)) for k in ("home", "draw", "away")):
                previsto = max([("1", mk["home"]), ("X", mk["draw"]), ("2", mk["away"])],
                               key=lambda t: t[1])[0]
                corretto = previsto == esito
            nuovo = dict(payload)
            nuovo["actual"] = {"home_goals": gol[0], "away_goals": gol[1], "outcome": esito}
            nuovo["predicted_correct_1x2"] = corretto
            resp = sb.table("fixture_predictions").update(
                {"tactical_engine_json": nuovo}).eq("fixture_id", fid).execute()
            if getattr(resp, "data", None):
                res["scritti"] += 1
            else:
                res["errori"] += 1
                log.warning("[tactical_engine] esito reale: UPDATE senza effetto fixture_id=%s", fid)
        except Exception as e:  # noqa: BLE001
            res["errori"] += 1
            log.warning("[tactical_engine] esito reale fallito fixture_id=%s: %s", fid, e)
    log.info("[tactical_engine] esiti reali: %s", res)
    return res
