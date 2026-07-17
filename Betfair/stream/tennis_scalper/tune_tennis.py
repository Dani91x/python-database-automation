"""Grid-tuner DETERMINISTICO del tennis_scalper su una registrazione nativa.

Rigioca il file ``.raw.jsonl`` (formato Betfair, prodotto da run_tennis_scalper
--record) via ``FlumineSimulation`` con la strategia VERA (TennisScalperStrategy),
provando molte configurazioni di parametri, e classifica per P&L. I fill sono
simulati SOLO sul volume realmente scambiato (``simulation_available_prices=False``)
= coda realistica del maker. Nessun dato futuro entra nelle decisioni.

Uso:
  python -m Betfair.stream.tennis_scalper.tune_tennis --raw <path>/35790054.raw.jsonl
"""

from __future__ import annotations

import argparse
import itertools
import logging
import sys
import threading
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from .tennis_scalper_bot import TennisScalperStrategy

logger = logging.getLogger(__name__)

_MAX_EXPOSURE = 1_000_000.0
_CONFIG_LOCK = threading.Lock()


def _sim_one(raw_path: str, scalper_params: Dict[str, Any]) -> Tuple[float, int, int]:
    """Rigioca il file con una config. Ritorna (pnl_lordo, n_ordini, n_matched)."""
    with _CONFIG_LOCK:
        prev_sim = getattr(flumine.config, "simulated", False)
        prev_avail = getattr(flumine.config, "simulation_available_prices", False)
        flumine.config.simulated = True
        flumine.config.simulation_available_prices = False  # solo volume scambiato
        try:
            client = clients.SimulatedClient(min_bet_validation=False)
            try:
                client.commission_base = 0.0
            except (TypeError, ValueError):
                pass
            framework = FlumineSimulation(client=client)
            framework.add_market_middleware(SimulatedMiddleware())
            params = {**scalper_params, "dry_run": False,
                      # in simulazione i fill sono a qualsiasi size: niente .it
                      "size_step": 0.0, "live_min_bet": 0.0}
            strategy = TennisScalperStrategy(
                market_filter={"markets": [raw_path]},
                scalper_params=params,
                max_selection_exposure=_MAX_EXPOSURE,
                max_order_exposure=_MAX_EXPOSURE,
                max_trade_count=int(1e9),
                max_live_trade_count=int(1e9),
            )
            framework.add_strategy(strategy)
            framework.run()
        finally:
            flumine.config.simulated = prev_sim
            flumine.config.simulation_available_prices = prev_avail

    settled = list(strategy.settled_orders)
    pnl = 0.0
    matched = 0
    for order, _ev in settled:
        sim = getattr(order, "simulated", None)
        pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        if float(getattr(order, "size_matched", 0.0) or 0.0) > 1e-9:
            matched += 1
    return pnl, len(settled), matched


# Griglia: il difetto chiave e' il CHASING (reprice_ticks basso -> cancella gli
# ordini a ogni punto -> non riempie mai). reprice_ticks alto = RESTA fermo e
# lascia che l'oscillazione torni sui suoi ordini.
GRID: Dict[str, List[Any]] = {
    "reprice_ticks": [2, 6, 12, 30],    # LEVA FILL: 2=insegue (rotto), 30=resta fermo
    "max_signal_ticks": [8.0, 999.0],   # anti-gap: 999 = quasi off
    "scalp_ticks": [1, 3],
    "stop_ticks": [3, 8],
}
BASE: Dict[str, Any] = {
    "mode": "auto", "min_size": 5.0, "min_flow": 2.0, "price_min": 1.20,
    "price_max": 6.0, "allow_inplay": True, "warmup_ms": 20000,
    "max_spread_ticks": 8, "join_max_spread": 3, "capture_min_ticks": 2,
    "capture_max_ticks": 20, "entry_ttl_ms": 600000, "lock_ttl_ms": 3600000,
    "stake": 2.0,
}


def _grid_configs() -> List[Dict[str, Any]]:
    keys = list(GRID.keys())
    out = []
    for combo in itertools.product(*(GRID[k] for k in keys)):
        cfg = dict(BASE)
        cfg.update(dict(zip(keys, combo)))
        out.append(cfg)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s | %(message)s")
    p = argparse.ArgumentParser(description="Grid-tuner tennis_scalper su registrazione")
    p.add_argument("--raw", required=True, help="Path al file .raw.jsonl")
    p.add_argument("--top", type=int, default=15, help="Quante config mostrare")
    p.add_argument("--min-coverage", type=float, default=None,
                   help="rifiuta la registrazione se la copertura e' sotto soglia (%%)")
    args = p.parse_args(argv)

    # GUARDIA REGISTRAZIONE (fix 17/07 "tuning senza guardia"): un tuning su un
    # raw monco MENTE. Default: warning visibile; --min-coverage rifiuta.
    from ..tools.validate_recordings import check_raw_paths_for_backtest

    try:
        kept = check_raw_paths_for_backtest([args.raw], args.min_coverage)
    except ValueError as exc:
        print(f"# REGISTRAZIONE RIFIUTATA: {exc}")
        return 2
    if not kept:
        print(f"# REGISTRAZIONE RIFIUTATA (copertura sotto soglia): {args.raw}")
        return 2

    configs = _grid_configs()
    print(f"# Tuning su {args.raw}")
    print(f"# {len(configs)} configurazioni, fill=solo-volume-scambiato (coda reale)\n")
    results: List[Tuple[float, int, int, Dict[str, Any]]] = []
    for i, cfg in enumerate(configs, 1):
        try:
            pnl, n, matched = _sim_one(args.raw, cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}/{len(configs)}] ERRORE: {exc}")
            continue
        results.append((pnl, n, matched, cfg))
        tag = (f"sig{cfg['max_signal_ticks']:g} scalp{cfg['scalp_ticks']} "
               f"stop{cfg['stop_ticks']} capMax{cfg['capture_max_ticks']}")
        print(f"[{i}/{len(configs)}] pnl={pnl:+.2f}  ordini={n} matched={matched}  | {tag}")

    results.sort(key=lambda r: r[0], reverse=True)
    print("\n===== CLASSIFICA (P&L lordo, migliori in alto) =====")
    for pnl, n, matched, cfg in results[:args.top]:
        tag = (f"max_signal_ticks={cfg['max_signal_ticks']:g} scalp_ticks={cfg['scalp_ticks']} "
               f"stop_ticks={cfg['stop_ticks']} capture_max_ticks={cfg['capture_max_ticks']}")
        print(f"  pnl={pnl:+.2f}  matched={matched}/{n}  | {tag}")
    if results:
        best = results[0]
        print(f"\nMIGLIORE: pnl={best[0]:+.2f}  ->  {best[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
