"""Grid runner MASSIVO per TennisLabStrategy: 1 replay per match, N config insieme.

Carica CENTINAIA di config come strategie separate in UNA sola FlumineSimulation
per match (blotter isolato per strategia => coda/PIQ indipendente per ognuna) e
aggrega il P&L di settlement per config su tutti i match conclusi.

Fill REALI (coda) + delay in-play modellato nella strategia. Classifica per
P&L totale, poi per numero di match verdi (l'obiettivo: profitto sul maggior
numero di match).

Uso:
  python -m Betfair.stream.tennis_scalper.lab_grid --data DIR [--smoke] [--top 40]
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from .tennis_lab import TennisLabStrategy

_MAXEXP = 1_000_000.0


# --------------------------------------------------------------------------- #
#  Generatore della griglia (archetipi x bande x gate x maker x uscita)       #
# --------------------------------------------------------------------------- #
ARCHETYPES = [
    ("layfav", "LAY", "favorite",
     [(1.01, 1.05), (1.01, 1.10), (1.05, 1.10), (1.10, 1.25)]),
    ("backfav", "BACK", "favorite",
     [(1.01, 1.05), (1.05, 1.15), (1.15, 1.40), (1.40, 1.90)]),
    ("laydog", "LAY", "underdog",
     [(2.0, 4.0), (4.0, 10.0), (10.0, 30.0), (2.0, 10.0)]),
    ("backdog", "BACK", "underdog",
     [(2.0, 4.0), (4.0, 12.0), (12.0, 50.0), (3.0, 20.0)]),
]

# motore di uscita. Priorita' daniele: CHIUDERE IN PROFIT appena possibile (trade),
# non tenere a settlement (scommessa direzionale). Uscite aggressive in testa.
EXITS = [
    # --- close-in-profit ASAP (trade: locked>0) ---
    ("green2", {"exit_mode": "green", "green_ticks": 2}),
    ("green4", {"exit_mode": "green", "green_ticks": 4}),
    ("lock0.1", {"exit_mode": "lock_trail", "lock_profit": 0.1, "trail_give_back": 0.08}),
    ("lock0.3", {"exit_mode": "lock_trail", "lock_profit": 0.3, "trail_give_back": 0.15}),
    # --- piu' lente / hold (riferimento direzionale) ---
    ("green8", {"exit_mode": "green", "green_ticks": 8}),
    ("lock0.6", {"exit_mode": "lock_trail", "lock_profit": 0.6, "trail_give_back": 0.15}),
    ("hold", {"exit_mode": "hold"}),
]
GATES = ["inplay", "any"]
MAKERS = [True, False]

# per trend/fade (backfav, laydog) aggiungi anche uno stop_ticks
STOP_ARCHS = {"backfav", "laydog"}
STOPS = [0, 10]


def build_grid(smoke: bool = False) -> List[Tuple[str, Dict[str, Any]]]:
    if smoke:
        return [
            ("layfav 1.01-1.10 inplay maker hold",
             {"side": "LAY", "target": "favorite", "price_min": 1.01,
              "price_max": 1.10, "gate": "inplay", "maker": True,
              "exit_mode": "hold", "min_matched": 5000.0}),
            ("layfav 1.01-1.10 inplay maker lock0.3",
             {"side": "LAY", "target": "favorite", "price_min": 1.01,
              "price_max": 1.10, "gate": "inplay", "maker": True,
              "exit_mode": "lock_trail", "lock_profit": 0.3,
              "trail_give_back": 0.15, "min_matched": 5000.0}),
            ("backdog 4-12 inplay maker green6",
             {"side": "BACK", "target": "underdog", "price_min": 4.0,
              "price_max": 12.0, "gate": "inplay", "maker": True,
              "exit_mode": "green", "green_ticks": 6, "min_matched": 5000.0}),
        ]
    grid: List[Tuple[str, Dict[str, Any]]] = []
    for arch, side, target, bands in ARCHETYPES:
        stops = STOPS if arch in STOP_ARCHS else [0]
        for (pmin, pmax), gate, maker, (ename, eparams), stop in itertools.product(
                bands, GATES, MAKERS, EXITS, stops):
            if stop and eparams["exit_mode"] == "hold":
                continue  # lo stop non ha senso con hold puro (no gestione)
            name = (f"{arch} {pmin:g}-{pmax:g} {gate} "
                    f"{'mk' if maker else 'tk'} {ename}"
                    + (f" stop{stop}" if stop else ""))
            params = {"side": side, "target": target, "price_min": pmin,
                      "price_max": pmax, "gate": gate, "maker": maker,
                      "min_matched": 10_000.0, "stop_ticks": stop, **eparams}
            grid.append((name, params))
    # --- SCALP mean-reversion sul favorito estremo (idea di daniele su Sinner):
    #     laya lo SPIKE (banda alta) e chiudi sul ritorno con green STRETTO, ripetuto.
    #     Testa se la coda permette davvero di harvestare l'oscillazione (queue-aware).
    for pmin, pmax in [(1.08, 1.15), (1.10, 1.20), (1.10, 1.30)]:
        for gt in (2, 3, 4):
            for maker in (True, False):
                name = (f"scalp lay {pmin:g}-{pmax:g} {'mk' if maker else 'tk'} green{gt}")
                grid.append((name, {"side": "LAY", "target": "favorite",
                                    "price_min": pmin, "price_max": pmax,
                                    "gate": "inplay", "maker": maker,
                                    "exit_mode": "green", "green_ticks": gt,
                                    "min_matched": 10_000.0, "stop_ticks": 0}))
    # --- PIRAMIDE FLB (idea di daniele): lay favorito estremo, se va contro AGGIUNGI
    #     (abbassa la quota media), TIENI per il crollo. taker vs maker, aggiunte/spaziatura.
    for pmax in (1.08, 1.10, 1.15):
        for maker in (True, False):
            for max_units, spacing in [(3, 3), (5, 2), (5, 4), (8, 2)]:
                name = (f"pyramid lay <= {pmax:g} {'mk' if maker else 'tk'} "
                        f"x{max_units} sp{spacing} hold")
                grid.append((name, {"side": "LAY", "target": "favorite",
                                    "price_min": 1.01, "price_max": pmax,
                                    "gate": "inplay", "maker": maker,
                                    "exit_mode": "hold", "min_matched": 10_000.0,
                                    "pyramid": True, "max_units": max_units,
                                    "add_spacing_ticks": spacing, "stop_ticks": 0}))
    return grid


# --------------------------------------------------------------------------- #
#  Replay: 1 match, TUTTE le config insieme                                   #
# --------------------------------------------------------------------------- #
def run_match(raw_path: str, grid: List[Tuple[str, Dict[str, Any]]]
              ) -> Dict[str, Tuple[float, Dict[str, Any]]]:
    prev_sim = getattr(flumine.config, "simulated", False)
    prev_av = getattr(flumine.config, "simulation_available_prices", False)
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False  # fill solo su volume tradato
    out: Dict[str, Tuple[float, Dict[str, Any]]] = {}
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
            s = TennisLabStrategy(
                market_filter={"markets": [raw_path]}, name=name,
                lab_params={**params, "dry_run": False},
                max_selection_exposure=_MAXEXP, max_order_exposure=_MAXEXP,
                max_trade_count=int(1e9), max_live_trade_count=int(1e9))
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
        with open(raw_path, "r", encoding="utf-8") as fh:
            for line in fh:
                if '"status":"CLOSED"' in line:
                    return True
    except OSError:
        return False
    return False


def find_matches(data_dir: str) -> List[str]:
    files = glob.glob(os.path.join(data_dir, "*", "*.raw.jsonl"))
    files += glob.glob(os.path.join(data_dir, "*.raw.jsonl"))
    return sorted(set(files))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Grid runner massivo TennisLab")
    p.add_argument("--data", required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--all", action="store_true", help="usa anche i match NON conclusi")
    p.add_argument("--min-coverage", type=float, default=None,
                   help="esclude i raw con copertura registrazione sotto soglia (%%)")
    args = p.parse_args(argv)

    files = find_matches(args.data)
    settled = files if args.all else [f for f in files if is_settled(f)]
    # GUARDIA REGISTRAZIONI (fix 17/07): warning visibile per i raw non-COMPLETE
    # (buchi/inizio tardivo/fine non confermata); --min-coverage esclude.
    from ..tools.validate_recordings import check_raw_paths_for_backtest

    settled = check_raw_paths_for_backtest(settled, args.min_coverage)
    grid = build_grid(args.smoke)
    print(f"# GRID: {len(grid)} config x {len(settled)} match "
          f"({'TUTTI' if args.all else 'settled'} su {len(files)} registrati)")
    if not settled:
        print("# Nessun match utilizzabile: rilancia quando finiscono.")
        return 0

    agg: Dict[str, Dict[str, Any]] = {
        name: {"tot": 0.0, "wins": 0, "n": 0, "entries": 0, "per": []}
        for name, _ in grid}
    for f in settled:
        ev = os.path.basename(os.path.dirname(f)) or os.path.basename(f)
        try:
            res = run_match(f, grid)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{ev}] ERRORE replay: {exc}")
            continue
        for name, (pnl, st) in res.items():
            a = agg[name]
            a["tot"] += pnl
            a["n"] += 1
            a["entries"] += int(st.get("entries", 0))
            if pnl > 1e-9:
                a["wins"] += 1
            a["per"].append((ev, round(pnl, 3), int(st.get("entries", 0))))
        print(f"  [{ev}] replay ok")

    board = sorted(agg.items(),
                   key=lambda kv: (kv[1]["tot"], kv[1]["wins"]), reverse=True)
    print("\n" + "=" * 84)
    print(f"{'#':>3} {'TOT':>8} {'WR':>7} {'ENTR':>5}  CONFIG")
    print("=" * 84)
    for i, (name, a) in enumerate(board[:args.top], 1):
        wr = f"{a['wins']}/{a['n']}"
        print(f"{i:>3} {a['tot']:>+8.2f} {wr:>7} {a['entries']:>5}  {name}")

    out = os.path.join(args.data, "_lab_leaderboard.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump([{"name": n, **a} for n, a in board], fh, indent=2, default=str)
    print(f"\n# classifica completa ({len(board)} config) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
