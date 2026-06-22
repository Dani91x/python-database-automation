"""build_analytics_signals.py — popola la tabella analytics_signals (centro di
controllo) appiattendo i motori PREDITTIVI in tabella + esito reale certificato.

MOTORI IN TABELLA: 'poisson' (markets_calibrated), 'ml' (model_predictions_json.
targets, forward-only), 'tacticai' (tactical_engine_json). L'API NON è in tabella:
i suoi esiti sono già risolti in fixture_predictions (result_*) e vengono PESCATI
a sola lettura dall'RPC get_analytics (nessuna migrazione, nessun doppio conteggio).

Mercati coperti (v1): i 7 con logica hit CERTIFICATA, comuni ai 3 motori:
  1x2, ht_1x2, over_1_5, over_2_5, over_3_5, btts, first_half_over_0_5.
I mercati esotici (ML clean_sheet/ht_ft/home_over, TacticAI doppia chance) sono
una estensione successiva (ognuno richiede la sua hit certificata).

Esito SEMPRE a 90' (analytics_settlement: fulltime primario, fallback goals solo
per FT, AET/PEN senza fulltime → non settlabile). Niente supplementari/rigori.

Uso:
  python build_analytics_signals.py --league 256
  python build_analytics_signals.py --days 3        # incrementale (action notturna)
  python build_analytics_signals.py --all           # tutto lo storico
  python build_analytics_signals.py --league 256 --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_client import get_supabase_client
from analytics_settlement import ft_score_90, ht_score, hit

# Mercati canonici (market, [(selection_canonica, ...)]) — i 7 certificati.
# Selezioni canoniche: 1x2/ht_1x2 → H|D|A ; over_* → Over|Under ; btts → Yes|No.


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fair(p: Optional[float]) -> Optional[float]:
    return round(1.0 / p, 4) if p and p > 0 else None


# ---- ESTRATTORI per-motore → forma canonica {market: {selection: (prob, prob_raw)}} ----

def extract_poisson(analisi: dict) -> dict:
    mc = analisi.get("markets_calibrated") or {}
    raw = analisi.get("markets") or {}
    M = {
        "1x2": [("H", "H"), ("D", "D"), ("A", "A")],
        "ht_1x2": [("H", "H"), ("D", "D"), ("A", "A")],
        "over_1_5": [("Over", "True"), ("Under", "False")],
        "over_2_5": [("Over", "True"), ("Under", "False")],
        "over_3_5": [("Over", "True"), ("Under", "False")],
        "btts": [("Yes", "True"), ("No", "False")],
        "first_half_over_0_5": [("Over", "True"), ("Under", "False")],
    }
    out: dict = {}
    for market, sels in M.items():
        mk = mc.get(market)
        if not isinstance(mk, dict):
            continue
        rk = raw.get(market) if isinstance(raw.get(market), dict) else {}
        out[market] = {c: (_num(mk.get(j)), _num(rk.get(j))) for c, j in sels}
    return out


def extract_ml(mpj: dict) -> tuple[dict, set]:
    targets = mpj.get("targets") or {}
    not_rel = {x.get("target") for x in (mpj.get("targets_not_reliable") or []) if isinstance(x, dict)}
    M = {
        "1x2": ("target_1x2", [("H", "H"), ("D", "D"), ("A", "A")]),
        "ht_1x2": ("target_ht_1x2", [("H", "H"), ("D", "D"), ("A", "A")]),
        "over_1_5": ("target_over_1_5", [("Over", "True"), ("Under", "False")]),
        "over_2_5": ("target_over_2_5", [("Over", "True"), ("Under", "False")]),
        "over_3_5": ("target_over_3_5", [("Over", "True"), ("Under", "False")]),
        "btts": ("target_btts", [("Yes", "True"), ("No", "False")]),
        "first_half_over_0_5": ("target_ht_over_0_5", [("Over", "True"), ("Under", "False")]),
    }
    out: dict = {}
    rel_by_market: dict = {}
    for market, (tname, sels) in M.items():
        tk = targets.get(tname)
        if not isinstance(tk, dict):
            continue
        out[market] = {c: (_num(tk.get(j)), None) for c, j in sels}
        rel_by_market[market] = tname not in not_rel  # affidabile se non nel gate
    return out, rel_by_market


def extract_tacticai(tj: dict) -> dict:
    mk = tj.get("markets") or {}
    ht = tj.get("markets_ht") or {}
    out: dict = {}
    if mk:
        out["1x2"] = {"H": (_num(mk.get("home")), None), "D": (_num(mk.get("draw")), None), "A": (_num(mk.get("away")), None)}
        out["btts"] = {"Yes": (_num(mk.get("btts_yes")), None), "No": (_num(mk.get("btts_no")), None)}
        for lab in ("1_5", "2_5", "3_5"):
            out[f"over_{lab}"] = {"Over": (_num(mk.get(f"over_{lab}")), None), "Under": (_num(mk.get(f"under_{lab}")), None)}
    if ht:
        out["ht_1x2"] = {"H": (_num(ht.get("home")), None), "D": (_num(ht.get("draw")), None), "A": (_num(ht.get("away")), None)}
        out["first_half_over_0_5"] = {"Over": (_num(ht.get("over_0_5")), None), "Under": (_num(ht.get("under_0_5")), None)}
    return out


_LINE = {"over_1_5": 1.5, "over_2_5": 2.5, "over_3_5": 3.5, "first_half_over_0_5": 0.5}


def _rows_for_fixture(fp: dict, match: Optional[dict]) -> list[dict]:
    fid = fp["fixture_id"]
    ctx = {
        "fixture_id": fid, "league_id": fp.get("league_id"), "league_name": fp.get("league_name"),
        "season_year": fp.get("season_year"), "home_team": fp.get("home_team_name"),
        "away_team": fp.get("away_team_name"), "kickoff": fp.get("fixture_date"),
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

    # estrai i 3 motori in forma canonica
    analisi = fp.get("db_json_analisi") or {}
    engines: dict = {}
    rel_flags: dict = {}
    if isinstance(analisi, dict) and analisi.get("markets_calibrated"):
        engines["poisson"] = (extract_poisson(analisi), analisi.get("generated_at"))
    mpj = fp.get("model_predictions_json")
    if isinstance(mpj, dict) and mpj.get("targets"):
        ml_markets, rel = extract_ml(mpj)
        engines["ml"] = (ml_markets, mpj.get("generated_at"))
        rel_flags["ml"] = rel
    tj = fp.get("tactical_engine_json")
    if isinstance(tj, dict) and tj.get("markets"):
        engines["tacticai"] = (extract_tacticai(tj), tj.get("generated_at"))

    rows: list[dict] = []
    eng_prob: dict = {}   # (market, selection, engine) -> prob
    picks: dict = {}      # market -> {engine: top_selection}

    for engine, (mkts, gen_at) in engines.items():
        for market, sels in mkts.items():
            best_sel, best_p = None, -1.0
            for selection, (prob, prob_raw) in sels.items():
                h = hit(market, selection, ft, ht)
                result = "WON" if h is True else ("LOST" if h is False else None)
                reliable = rel_flags.get(engine, {}).get(market) if engine == "ml" else None
                rows.append({
                    "signal_uid": f"{engine}|{fid}|{market}|{selection}",
                    "engine": engine, "generated_at": gen_at, **ctx,
                    "market": market, "selection": selection, "line": _LINE.get(market),
                    "direction": "back", "prob": prob, "prob_raw": prob_raw, "fair_odds": _fair(prob),
                    "n_engines_agree": None, "consensus_prob": None,
                    "placed": False, "status": None,
                    "settled": settled, "result": result, "hit": h, **g,
                    "oos_valid": True, "reliable": reliable,
                })
                if prob is not None:
                    eng_prob[(market, selection, engine)] = prob
                    if prob > best_p:
                        best_sel, best_p = selection, prob
            if best_sel:
                picks.setdefault(market, {})[engine] = best_sel

    # concordanza: per ogni riga, quanti motori "scelgono" quella selezione
    for r in rows:
        mkt, sel = r["market"], r["selection"]
        agree = [e for e, top in picks.get(mkt, {}).items() if top == sel]
        r["n_engines_agree"] = len(agree)
        ps = [eng_prob[(mkt, sel, e)] for e in agree if (mkt, sel, e) in eng_prob]
        r["consensus_prob"] = round(sum(ps) / len(ps), 4) if ps else None
    return rows


def _fetch_fixtures(sb, league_id: Optional[int], days: Optional[int], page=500):
    sel = ("fixture_id,league_id,league_name,season_year,fixture_date,home_team_name,away_team_name,"
           "db_json_analisi,model_predictions_json,tactical_engine_json")
    off = 0
    since = None
    if days:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    while True:
        q = sb.table("fixture_predictions").select(sel).not_.is_("db_json_analisi", "null")
        if league_id:
            q = q.eq("league_id", league_id)
        if since:
            q = q.gte("fixture_date", f"{since}T00:00:00+00:00")
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
    ap.add_argument("--days", type=int, default=None, help="incrementale: solo fixture_date ultimi N giorni")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.league and not args.all and not args.days:
        raise SystemExit("Specificare --league N | --days N | --all")

    sb = get_supabase_client()
    counters = {"failed_rows": 0}
    tot_rows = tot_fix = settled_fix = 0
    for batch in _fetch_fixtures(sb, args.league, args.days):
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
