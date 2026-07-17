"""Harness backtest MULTI-PARTITA con fill REALI (coda + volume tradato).

Rigioca ogni ``.raw.jsonl`` registrato via FlumineSimulation + SimulatedMiddleware
(``simulation_available_prices=False`` = fill solo sul volume realmente scambiato,
coda rispettata) e riporta il P&L di SETTLEMENT per-partita e aggregato.

Strategie testabili (registro estendibile):
  - "flb"   -> TennisFLBStrategy (lay del favorito estremo, no stop) [VALIDATO +]
  - "swing" -> TennisSwingStrategy (mean-reversion detector) [oggi negativo, si ri-testa]

Uso (domani su 10+ partite):
  python -m Betfair.stream.tennis_scalper.flb_backtest --data <DIR_registrazioni>
  # <DIR>/<event>/<event>.raw.jsonl  (uno per partita)
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Any, Callable, Dict, List, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from .tennis_flb_bot import TennisFLBStrategy

_MAX_EXPOSURE = 1_000_000.0


def _make_strategy(kind: str, raw_path: str, params: Dict[str, Any]) -> Any:
    common = dict(market_filter={"markets": [raw_path]},
                  max_selection_exposure=_MAX_EXPOSURE,
                  max_order_exposure=_MAX_EXPOSURE,
                  max_trade_count=int(1e9), max_live_trade_count=int(1e9))
    if kind == "flb":
        return TennisFLBStrategy(flb_params={**params, "dry_run": False}, **common)
    if kind == "swing":
        from .tennis_swing_bot import TennisSwingStrategy
        return TennisSwingStrategy(swing_params={**params, "dry_run": False}, **common)
    raise ValueError(f"strategia sconosciuta: {kind}")


def backtest_one(raw_path: str, kind: str, params: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Rigioca UNA partita con fill reali. Ritorna (settled_pnl, stats)."""
    prev_sim = getattr(flumine.config, "simulated", False)
    prev_av = getattr(flumine.config, "simulation_available_prices", False)
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False   # fill solo su volume tradato
    try:
        client = clients.SimulatedClient(min_bet_validation=False)
        try:
            client.commission_base = 0.0
        except (TypeError, ValueError):
            pass
        fw = FlumineSimulation(client=client)
        fw.add_market_middleware(SimulatedMiddleware())
        strat = _make_strategy(kind, raw_path, params)
        fw.add_strategy(strat)
        fw.run()
    finally:
        flumine.config.simulated = prev_sim
        flumine.config.simulation_available_prices = prev_av
    return float(getattr(strat, "settled_pnl", 0.0)), dict(strat.stats)


def find_matches(data_dir: str) -> List[str]:
    files = glob.glob(os.path.join(data_dir, "*", "*.raw.jsonl"))
    files += glob.glob(os.path.join(data_dir, "*.raw.jsonl"))
    return sorted(set(files))


# configurazioni di default da confrontare domani su >=20 partite.
# TUTTO cio' che oggi e' uscito verde (FLB) o leggermente negativo (Swing) e'
# qui, price-only -> gira su qualsiasi .raw.jsonl registrato.
# (Post-break e' score-driven: si testa col percorso score-injected, vedi
#  backtest_pro.BacktestProStrategy, quando la registrazione include lo score.)
DEFAULT_CONFIGS: List[Tuple[str, str, Dict[str, Any]]] = [
    # --- VERDE oggi: FLB lay del favorito estremo (no stop) ---
    ("FLB lay<=1.10 hold",   "flb", {"lay_max": 1.10, "exit_mode": "hold"}),
    ("FLB lay<=1.10 hybrid", "flb", {"lay_max": 1.10, "exit_mode": "hybrid"}),
    ("FLB lay<=1.05 hold",   "flb", {"lay_max": 1.05, "exit_mode": "hold"}),
    ("FLB lay<=1.20 hybrid", "flb", {"lay_max": 1.20, "exit_mode": "hybrid"}),
    ("FLB lay<=1.10 green",  "flb", {"lay_max": 1.10, "exit_mode": "green"}),
    # --- LEGGERMENTE NEGATIVO oggi: Swing detector (si ri-testa sul campione) ---
    ("SWING z2.0 stop8",     "swing", {"maker": True, "maker_offset": 2, "zin": 2.0, "stop_ticks": 8}),
    ("SWING z2.5 stop8",     "swing", {"maker": True, "maker_offset": 2, "zin": 2.5, "stop_ticks": 8}),
    ("SWING z2.0 taker",     "swing", {"maker": False, "zin": 2.0, "stop_ticks": 8}),
]


def run_suite(files: List[str], configs=DEFAULT_CONFIGS) -> None:
    print(f"# Backtest MULTI-PARTITA (fill reali) su {len(files)} match\n")
    for name, kind, params in configs:
        results: List[Tuple[str, float, Dict[str, Any]]] = []
        for f in files:
            ev = os.path.basename(os.path.dirname(f)) or os.path.basename(f)
            try:
                pnl, st = backtest_one(f, kind, params)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{ev}] ERRORE: {exc}"); continue
            results.append((ev, pnl, st))
        tot = sum(p for _, p, _ in results)
        wins = sum(1 for _, p, _ in results if p > 0)
        print(f"== {name} ==  TOT {tot:+.2f}  su {len(results)} match "
              f"({wins} verdi / {len(results)-wins} rossi)")
        for ev, pnl, st in results:
            print(f"     {ev:14s} {pnl:+7.2f}  (lay {st.get('entries',0)}, "
                  f"green {st.get('greens',0)})")
        print()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backtest multi-partita FLB (fill reali)")
    p.add_argument("--data", required=True, help="cartella con <event>/<event>.raw.jsonl")
    p.add_argument("--files", nargs="*", help="opzionale: lista esplicita di .raw.jsonl")
    p.add_argument("--min-coverage", type=float, default=None,
                   help="esclude i raw con copertura registrazione sotto soglia (%%)")
    args = p.parse_args(argv)
    files = args.files or find_matches(args.data)
    if not files:
        print(f"Nessun .raw.jsonl trovato in {args.data}"); return 1
    # GUARDIA REGISTRAZIONI (fix 17/07): warning visibile per i raw non-COMPLETE;
    # --min-coverage esclude sotto soglia.
    from ..tools.validate_recordings import check_raw_paths_for_backtest

    files = check_raw_paths_for_backtest(files, args.min_coverage)
    if not files:
        print("# Nessun raw utilizzabile dopo la validazione."); return 1
    run_suite(files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
