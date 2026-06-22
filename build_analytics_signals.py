"""build_analytics_signals.py — popola la tabella analytics_signals (centro di
controllo) appiattendo i motori predittivi + esito reale certificato.

v1: engine 'poisson' (markets_calibrated, tutti i mercati) + 'api' (1x2 da
percent_*). Esito via analytics_settlement (settlement 90' certificato). I campi
freq_*/delay_* restano NULL in v1 (enrichment fase-2 via RPC; il frontend li
mostra live nel frattempo). ML/TacticAI: struttura pronta, popolati quando
disponibili leak-free.

Uso:
  python build_analytics_signals.py --league 256          # una lega (certificazione)
  python build_analytics_signals.py --league 256 --dry-run
  python build_analytics_signals.py --all                 # tutte (migrazione, gentile)
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from analytics_settlement import ft_score_90, ht_score, hit

# mappa (market → [(selection_canonica, chiave_json, line)])
POISSON_MARKETS = {
    "1x2": [("H", "H", None), ("D", "D", None), ("A", "A", None)],
    "ht_1x2": [("H", "H", None), ("D", "D", None), ("A", "A", None)],
    "over_1_5": [("Over", "True", 1.5), ("Under", "False", 1.5)],
    "over_2_5": [("Over", "True", 2.5), ("Under", "False", 2.5)],
    "over_3_5": [("Over", "True", 3.5), ("Under", "False", 3.5)],
    "btts": [("Yes", "True", None), ("No", "False", None)],
    "first_half_over_0_5": [("Over", "True", 0.5), ("Under", "False", 0.5)],
}


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fair(p: Optional[float]) -> Optional[float]:
    return round(1.0 / p, 4) if p and p > 0 else None


def _rows_for_fixture(fp: dict, match: Optional[dict]) -> list[dict]:
    """Costruisce le righe analytics_signals per una fixture (poisson + api)."""
    fid = fp["fixture_id"]
    ctx = {
        "fixture_id": fid,
        "league_id": fp.get("league_id"),
        "league_name": fp.get("league_name"),
        "season_year": fp.get("season_year"),
        "home_team": fp.get("home_team_name"),
        "away_team": fp.get("away_team_name"),
        "kickoff": fp.get("fixture_date"),
    }
    ft = ht = None
    settled = False
    g = {"goals_home": None, "goals_away": None, "total_goals": None, "ht_home": None, "ht_away": None}
    if match:
        ft, ht = ft_score_90(match), ht_score(match)
        settled = ft is not None
        if ft is not None:
            g["goals_home"], g["goals_away"], g["total_goals"] = ft[0], ft[1], ft[0] + ft[1]
        if ht is not None:
            g["ht_home"], g["ht_away"] = ht[0], ht[1]

    analisi = fp.get("db_json_analisi") or {}
    mc = analisi.get("markets_calibrated") or {}
    raw = analisi.get("markets") or {}
    gen_at = analisi.get("generated_at")

    # raccoglie per (market) i pick di ogni engine, per la concordanza
    picks: dict[str, dict[str, str]] = {}   # market -> {engine: selection_top}
    eng_prob: dict[tuple, float] = {}       # (market, selection, engine) -> prob

    rows: list[dict] = []

    def emit(engine, market, selection, line, prob, prob_raw):
        h = hit(market, selection, ft, ht)
        result = None
        if h is True:
            result = "WON"
        elif h is False:
            result = "LOST"
        rows.append({
            "signal_uid": f"{engine}|{fid}|{market}|{selection}",
            "engine": engine, "generated_at": gen_at, **ctx,
            "market": market, "selection": selection, "line": line, "direction": "back",
            "prob": prob, "prob_raw": prob_raw, "fair_odds": _fair(prob),
            "n_engines_agree": None, "consensus_prob": None,
            "placed": False, "status": None,
            "settled": settled, "result": result, "hit": h, **g,
            "oos_valid": True, "reliable": None,
        })
        if prob is not None:
            eng_prob[(market, selection, engine)] = prob

    # --- POISSON ---
    for market, sels in POISSON_MARKETS.items():
        mk = mc.get(market)
        if not isinstance(mk, dict):
            continue
        best_sel, best_p = None, -1.0
        for sel_canon, jkey, line in sels:
            p = _num(mk.get(jkey))
            pr = _num((raw.get(market) or {}).get(jkey))
            emit("poisson", market, sel_canon, line, p, pr)
            if p is not None and p > best_p:
                best_sel, best_p = sel_canon, p
        if best_sel:
            picks.setdefault(market, {})["poisson"] = best_sel

    # --- API (solo 1x2 dai percent_*; scala 0-100) ---
    # SOLO se TUTTE e 3 le percentuali sono presenti: l'API fornisce il 1x2
    # completo o niente. Fabbricare 0.0 su una leg mancante falserebbe avg_prob
    # e la concordanza (un percent=0.0 reale è invece ammesso).
    ph, pd_, pa = _num(fp.get("percent_home")), _num(fp.get("percent_draw")), _num(fp.get("percent_away"))
    if ph is not None and pd_ is not None and pa is not None:
        api_1x2 = {"H": ph / 100.0, "D": pd_ / 100.0, "A": pa / 100.0}
        best_sel, _bp = max(api_1x2.items(), key=lambda kv: kv[1])
        for sel_canon, p in api_1x2.items():
            emit("api", "1x2", sel_canon, None, p, None)
        picks.setdefault("1x2", {})["api"] = best_sel

    # --- CONCORDANZA: per ogni riga, quanti engine "scelgono" quella selezione ---
    for r in rows:
        mkt, sel = r["market"], r["selection"]
        agree_engines = [e for e, top in picks.get(mkt, {}).items() if top == sel]
        if agree_engines:
            r["n_engines_agree"] = len(agree_engines)
            ps = [eng_prob[(mkt, sel, e)] for e in agree_engines if (mkt, sel, e) in eng_prob]
            r["consensus_prob"] = round(sum(ps) / len(ps), 4) if ps else None
        else:
            r["n_engines_agree"] = 0
    return rows


def _fetch_fixtures(sb, league_id: Optional[int], page=500):
    sel = ("fixture_id,league_id,league_name,season_year,fixture_date,"
           "home_team_name,away_team_name,percent_home,percent_draw,percent_away,db_json_analisi")
    off = 0
    while True:
        q = (sb.table("fixture_predictions").select(sel)
             .eq("db_json_analisi->>model", "poisson_xg_hybrid_dc")
             .not_.is_("db_json_analisi->markets_calibrated", "null"))
        if league_id:
            q = q.eq("league_id", league_id)
        r = q.range(off, off + page - 1).execute()
        batch = r.data or []
        if not batch:
            break
        yield batch
        if len(batch) < page:
            break
        off += page


def _fetch_matches(sb, fids: list[int]) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for i in range(0, len(fids), 300):
        chunk = fids[i:i + 300]
        r = (sb.table("matches")
             .select("fixture_id,status_short,goals_home,goals_away,fulltime_home,fulltime_away,halftime_home,halftime_away")
             .in_("fixture_id", chunk).execute())
        for m in r.data or []:
            out[m["fixture_id"]] = m
    return out


def _upsert(sb, rows: list[dict], dry: bool, counters: dict) -> int:
    if dry or not rows:
        return len(rows)
    n = 0
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        for attempt in range(3):
            try:
                sb.table("analytics_signals").upsert(chunk, on_conflict="signal_uid").execute()
                n += len(chunk)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    # Fallimento PERMANENTE: NON silenzioso. Un chunk perso = hit-rate
                    # calcolato su dati incompleti → il run deve segnalare l'errore.
                    counters["failed_rows"] += len(chunk)
                    print(f"\n  [ERRORE PERMANENTE] chunk {len(chunk)} righe perse: {type(e).__name__}: {str(e)[:120]}")
                else:
                    time.sleep(0.5 * (attempt + 1))
    return n


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.league and not args.all:
        raise SystemExit("Specificare --league N o --all")

    sb = get_supabase_client()
    counters = {"failed_rows": 0}
    tot_rows = tot_fix = settled_fix = 0
    for batch in _fetch_fixtures(sb, None if args.all else args.league):
        fids = [b["fixture_id"] for b in batch]
        matches = _fetch_matches(sb, fids)
        rows = []
        for fp in batch:
            m = matches.get(fp["fixture_id"])
            if m and m.get("status_short") in ("FT", "AET", "PEN"):
                settled_fix += 1
            rows.extend(_rows_for_fixture(fp, m))
        tot_fix += len(batch)
        tot_rows += _upsert(sb, rows, args.dry_run, counters)
        print(f"  ...fixture {tot_fix} | righe {tot_rows} | settlate {settled_fix}", end="\r")
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Fixture {tot_fix} | righe {tot_rows} | "
          f"settlate {settled_fix} | righe perse {counters['failed_rows']}")
    if counters["failed_rows"]:
        raise SystemExit(f"ATTENZIONE: {counters['failed_rows']} righe NON scritte (dati incompleti).")


if __name__ == "__main__":
    main()
