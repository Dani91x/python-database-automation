"""Grid runner FASE 2: TennisLab SCORE-CONDIZIONATO su tutti i match conclusi.

Per ogni evento: inietta la timeline dei punteggi (.score.jsonl) allineata al
book, costruisce il side_map (selezione -> home/away, per le condizioni sul
servizio/break) e gira una griglia di config score-gated in UNA passata per match
(multi-strategia). Fill reali (coda) + delay in-play (dalla base TennisLab).

Uso:
  python -m Betfair.stream.tennis_scalper.lab_grid_score --data DIR [--top 50]
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from .tennis_lab_score import ScoreConditionedLab, SIDE_AGNOSTIC, SIDE_AWARE
from .tennis_score import TennisScore, parse_tennis_scores

_MAXEXP = 1_000_000.0

ARCH = [
    ("layfav", "LAY", "favorite", [(1.01, 1.10), (1.01, 1.20)]),
    ("backfav", "BACK", "favorite", [(1.05, 1.40), (1.40, 1.90)]),
    ("laydog", "LAY", "underdog", [(2.0, 10.0), (10.0, 40.0)]),
    ("backdog", "BACK", "underdog", [(3.0, 20.0), (4.0, 12.0)]),
]
CONDS = ["any", "set1", "set2plus", "pressure", "calm", "setlead", "early",
         "serving", "receiving", "broke", "gotbroken", "post_game"]
EXITS = [
    # close-in-profit ASAP (trade) in testa; hold in coda (riferimento)
    ("green2", {"exit_mode": "green", "green_ticks": 2}),
    ("lock0.1", {"exit_mode": "lock_trail", "lock_profit": 0.1, "trail_give_back": 0.08}),
    ("green8", {"exit_mode": "green", "green_ticks": 8}),
    ("hold", {"exit_mode": "hold"}),
]


def build_grid() -> List[Tuple[str, Dict[str, Any]]]:
    grid = []
    for arch, side, target, bands in ARCH:
        for (pmin, pmax), cond, (ename, ep) in itertools.product(bands, CONDS, EXITS):
            name = f"{arch} {pmin:g}-{pmax:g} @{cond} {ename}"
            params = {"side": side, "target": target, "price_min": pmin,
                      "price_max": pmax, "gate": "inplay", "maker": True,
                      "min_matched": 10_000.0, "score_cond": cond, **ep}
            grid.append((name, params))
    # --- MODELLO serve-hold (fade over-reaction): back il sottovalutato / lay il
    #     sopravvalutato secondo la win-prob vs mercato. side legato alla condizione.
    for target in ("favorite", "underdog"):
        for cond, side in (("model_under", "BACK"), ("model_over", "LAY")):
            for edge in (0.03, 0.06, 0.10):
                for ename, ep in [("green2", {"exit_mode": "green", "green_ticks": 2}),
                                  ("lock0.1", {"exit_mode": "lock_trail",
                                               "lock_profit": 0.1, "trail_give_back": 0.08})]:
                    name = f"model {target} @{cond} e{edge:g} {ename}"
                    grid.append((name, {"side": side, "target": target,
                                        "price_min": 1.01, "price_max": 1000.0,
                                        "gate": "inplay", "maker": True,
                                        "min_matched": 10_000.0, "score_cond": cond,
                                        "model_edge": edge, **ep}))
    return grid


# --------------------------------------------------------------- names/side_map
def _read_market_id(raw_path: str) -> Optional[str]:
    try:
        with open(raw_path, encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                for c in obj.get("mc", []):
                    if c.get("id"):
                        return c["id"]
    except (OSError, ValueError):
        return None
    return None


def build_names_cache(data_dir: str, events: List[str]) -> Dict[str, Dict[str, str]]:
    """{event_id: {selection_id: runner_name}} con cache su _names.json."""
    cache_path = os.path.join(data_dir, "_names.json")
    cache: Dict[str, Dict[str, str]] = {}
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as fh:
                cache = json.load(fh)
        except (OSError, ValueError):
            cache = {}
    missing = [e for e in events if e not in cache]
    if missing:
        try:
            from ..auth import build_client
            from betfairlightweight import filters
            trading = build_client(login=True)
            for i in range(0, len(missing), 20):
                chunk = missing[i:i + 20]
                cat = trading.betting.list_market_catalogue(
                    filter=filters.market_filter(
                        event_ids=chunk, event_type_ids=["2"],
                        market_type_codes=["MATCH_ODDS"]),
                    market_projection=["RUNNER_DESCRIPTION", "EVENT"], max_results=100)
                for mo in cat or []:
                    ev = str(getattr(getattr(mo, "event", None), "id", "") or "")
                    if ev:
                        cache[ev] = {str(r.selection_id): r.runner_name
                                     for r in (mo.runners or [])}
            with open(cache_path, "w", encoding="utf-8") as fh:
                json.dump(cache, fh, indent=2, default=str)
        except Exception as exc:  # noqa: BLE001
            print(f"# names cache: fetch parziale/fallito ({type(exc).__name__})")
    return cache


def _surnames(name: str) -> set:
    toks = [t.strip().lower() for t in str(name).replace("/", " ").split() if t.strip()]
    return {t for t in toks if len(t) >= 3}


def build_side_map(names: Dict[str, str], ts: Optional[TennisScore]) -> Dict[int, str]:
    """sel -> home/away confrontando i cognomi runner vs score home/away."""
    if not names or ts is None or not ts.home_name or not ts.away_name:
        return {}
    hs, as_ = _surnames(ts.home_name), _surnames(ts.away_name)
    out: Dict[int, str] = {}
    for sel, rn in names.items():
        rs = _surnames(rn)
        h_ov, a_ov = len(rs & hs), len(rs & as_)
        if h_ov > a_ov:
            out[int(sel)] = "home"
        elif a_ov > h_ov:
            out[int(sel)] = "away"
        # ambiguo (pari) -> non mappato (fail-safe)
    return out


def load_timeline(score_path: str, event_id: str) -> List[Tuple[float, TennisScore]]:
    tl: List[Tuple[float, TennisScore]] = []
    if not os.path.isfile(score_path):
        return tl
    with open(score_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts = parse_tennis_scores([rec.get("score")], event_id)
            if ts is not None and rec.get("t") is not None:
                tl.append((float(rec["t"]) * 1000.0, ts))
    tl.sort(key=lambda x: x[0])
    return tl


# --------------------------------------------------------------- replay
def run_match(raw_path: str, timeline, side_map, grid) -> Dict[str, Tuple[float, Dict]]:
    prev_sim = getattr(flumine.config, "simulated", False)
    prev_av = getattr(flumine.config, "simulation_available_prices", False)
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False
    out: Dict[str, Tuple[float, Dict]] = {}
    try:
        client = clients.SimulatedClient(min_bet_validation=False)
        try:
            client.commission_base = 0.0
        except (TypeError, ValueError):
            pass
        fw = FlumineSimulation(client=client)
        fw.add_market_middleware(SimulatedMiddleware())
        strats = []
        for name, params in grid:
            s = ScoreConditionedLab(
                market_filter={"markets": [raw_path]}, name=name,
                lab_params={**params, "dry_run": False},
                max_selection_exposure=_MAXEXP, max_order_exposure=_MAXEXP,
                max_trade_count=int(1e9), max_live_trade_count=int(1e9))
            s.set_timeline(timeline)
            s.set_side_map(side_map)
            strats.append((name, s))
            fw.add_strategy(s)
        fw.run()
        for name, s in strats:
            stt = dict(s.stats)
            stt["locked"] = float(getattr(s, "locked_floor", 0.0))
            out[name] = (float(s.settled_pnl), stt)
    finally:
        flumine.config.simulated = prev_sim
        flumine.config.simulation_available_prices = prev_av
    return out


def is_settled(raw_path: str) -> bool:
    try:
        with open(raw_path, encoding="utf-8") as fh:
            for line in fh:
                if '"status":"CLOSED"' in line:
                    return True
    except OSError:
        return False
    return False


def find_matches(data_dir: str) -> List[str]:
    fs = glob.glob(os.path.join(data_dir, "*", "*.raw.jsonl"))
    return sorted(set(fs))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Grid score-condizionato TennisLab")
    p.add_argument("--data", required=True)
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--all", action="store_true")
    args = p.parse_args(argv)

    files = find_matches(args.data)
    usable = files if args.all else [f for f in files if is_settled(f)]
    grid = build_grid()
    print(f"# GRID score-cond: {len(grid)} config x {len(usable)} match "
          f"({'TUTTI' if args.all else 'settled'})")
    if not usable:
        print("# Nessun match utilizzabile.")
        return 0

    events = [os.path.basename(os.path.dirname(f)) for f in usable]
    names_cache = build_names_cache(args.data, events)

    agg = {name: {"tot": 0.0, "wins": 0, "n": 0, "entries": 0, "nomap": 0}
           for name, _ in grid}
    for f in usable:
        ev = os.path.basename(os.path.dirname(f))
        tl = load_timeline(os.path.join(os.path.dirname(f), f"{ev}.score.jsonl"), ev)
        ts0 = tl[-1][1] if tl else None
        side_map = build_side_map(names_cache.get(ev, {}), ts0)
        try:
            res = run_match(f, tl, side_map, grid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{ev}] ERRORE: {exc}")
            continue
        for name, (pnl, st) in res.items():
            a = agg[name]
            a["tot"] += pnl; a["n"] += 1
            a["entries"] += int(st.get("entries", 0))
            a["nomap"] += int(st.get("skipped_nomap", 0))
            if pnl > 1e-9:
                a["wins"] += 1
        print(f"  [{ev}] tl={len(tl)} sidemap={len(side_map)} ok")

    board = sorted(agg.items(), key=lambda kv: (kv[1]["tot"], kv[1]["wins"]), reverse=True)
    print("\n" + "=" * 88)
    print(f"{'#':>3} {'TOT':>8} {'WR':>7} {'ENTR':>5}  CONFIG")
    print("=" * 88)
    for i, (name, a) in enumerate(board[:args.top], 1):
        print(f"{i:>3} {a['tot']:>+8.2f} {a['wins']}/{a['n']:<4} {a['entries']:>5}  {name}")
    out = os.path.join(args.data, "_lab_score_leaderboard.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump([{"name": n, **a} for n, a in board], fh, indent=2, default=str)
    print(f"\n# classifica score-cond ({len(board)}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
