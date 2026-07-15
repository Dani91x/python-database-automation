"""Backtest del THETA SCALPER via FlumineSimulation (clonato da run_scalper).

Replay forward-only sui raw nativi in ``_live_raw/<event>/<event>.raw.jsonl``:
  * FILL CONSERVATIVI: default ``simulation_available_prices=False`` → gli
    ordini si riempiono SOLO contro il volume realmente scambiato (coda PIQ
    di flumine), mai contro i prezzi disponibili;
  * BET DELAY DAI RAW: in-play flumine applica il betDelay letto dalla
    marketDefinition del raw (5s reali certificati 11/07);
  * PROTEZIONI SOLO-LIVE SPENTE: size_step/live_min_bet/exact_exits a zero
    (il simulatore accetta size esatte), conferme manuali OFF;
  * punteggio/minuto dalla sidecar ``<event>.scores.jsonl`` (stessa fonte
    del backtest ufficiale, allineata al publish_time: NESSUN look-ahead);
  * semaforo di quiete: EventRiskSemaphore locale (120s) alimentato dalle
    sospensioni del replay — identico al percorso live.

CAVEAT (dossier 15/07): void e slippage nel gap-gol non sono modellati →
lo stop post-gol nel simulatore e' OTTIMISTICO. Il verdetto vero e' il PAPER.

Uso:
    from Betfair.stream.scalper.run_theta import run_theta
    rows = run_theta({"event_ids": ["35674515"], "commission_rate": 0.05,
                      "theta": {"stake": 25.0, "hazard_max": 0.085}})
oppure da CLI (tutti gli eventi con raw+scores in DATA_DIR):
    python -m Betfair.stream.scalper.run_theta 35674515 35759636 ...
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from ..backtest.run_backtest import _load_scores, aggregate_results
from ..config_stream import DATA_DIR
from .risk_semaphore import EventRiskSemaphore
from .theta_bot import ThetaStrategy, load_hazard_atlas

logger = logging.getLogger(__name__)

# esposizioni ampie: il sizing e' della strategia (come run_scalper)
_MAX_EXPOSURE: float = 1_000_000.0

# flumine.config e' GLOBALE: serializza per run concorrenti
_CONFIG_LOCK = threading.Lock()


def _theta_cell_params(
    cell: Dict[str, Any], atlas: Optional[Dict[str, Any]],
    scores: List[Tuple[int, Optional[int], int, int]],
) -> Dict[str, Any]:
    """Completa i parametri di UNA cella coi default del simulatore."""
    theta_params: Dict[str, Any] = dict(cell or {})
    # protezioni SOLO-LIVE spente nel simulatore (default sovrascrivibili)
    theta_params.setdefault("dry_run", False)
    theta_params.setdefault("exact_exits", False)
    theta_params.setdefault("size_step", 0.0)
    theta_params.setdefault("live_min_bet", 0.0)
    theta_params.setdefault("confirm_mode", False)
    if "atlas" not in theta_params:
        theta_params["atlas"] = atlas
    # punteggio/minuto REALI dalla sidecar (no look-ahead: allineati al pt)
    theta_params.setdefault("scores_timeline", list(scores))
    return theta_params


def _run_one_event(
    event_id: str, params: Dict[str, Any], data_dir: str,
    atlas: Optional[Dict[str, Any]],
) -> List[Tuple[Any, str]]:
    """Replay di UN evento. Con ``params['theta_cells']`` (lista di dict di
    parametri theta) il raw viene riprodotto UNA volta con N strategie
    INDIPENDENTI (una per cella: fill flumine per-ordine, nessuna
    interferenza) e il ritorno e' la concatenazione dei settled di tutte le
    celle; ``params['stats_out']`` (dict) riceve stats per (event, cella).
    Ogni cella puo' portare un proprio ``event_sink`` (callable)."""
    raw_path = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(f"file nativo mancante: {raw_path}")

    base = dict(params.get("theta") or {})
    cells = params.get("theta_cells")
    multi = isinstance(cells, (list, tuple)) and len(cells) > 0
    cell_list: List[Dict[str, Any]] = (
        [dict(base, **dict(c)) for c in cells] if multi else [base])
    scores = _load_scores(data_dir, str(event_id))

    with _CONFIG_LOCK:
        _prev = {
            "simulated": getattr(flumine.config, "simulated", False),
            "simulation_available_prices": getattr(
                flumine.config, "simulation_available_prices", False),
            "place_latency": getattr(flumine.config, "place_latency", 0.120),
            "cancel_latency": getattr(flumine.config, "cancel_latency", 0.170),
        }
        flumine.config.simulated = True
        # default CONSERVATIVO: fill solo su volume scambiato
        flumine.config.simulation_available_prices = bool(
            params.get("simulation_available_prices", False))
        if params.get("place_latency") is not None:
            flumine.config.place_latency = float(params["place_latency"])
        if params.get("cancel_latency") is not None:
            flumine.config.cancel_latency = float(params["cancel_latency"])
        try:
            # min_bet_validation=False: hedge/close a size esatta;
            # commission_base=0: commissione UNA volta in aggregate_results
            client = clients.SimulatedClient(min_bet_validation=False)
            try:
                client.commission_base = 0.0
            except (TypeError, ValueError):
                pass
            framework = FlumineSimulation(client=client)
            framework.add_market_middleware(SimulatedMiddleware())

            strategies: List[ThetaStrategy] = []
            for cell in cell_list:
                theta_params = _theta_cell_params(cell, atlas, scores)
                sink = theta_params.pop("event_sink", None)
                strategy = ThetaStrategy(
                    market_filter={"markets": [raw_path]},
                    theta_params=theta_params,
                    event_sink=sink,
                    max_selection_exposure=_MAX_EXPOSURE,
                    max_order_exposure=_MAX_EXPOSURE,
                    max_trade_count=int(1e9),
                    max_live_trade_count=int(1e9),
                )
                # quiete post-sospensione IDENTICA al live (gol → halt 120s)
                strategy.risk_sem = EventRiskSemaphore(
                    post_suspension_cooldown_s=float(
                        params.get("risk_cooldown_s", 120.0)))
                framework.add_strategy(strategy)
                strategies.append(strategy)
            framework.run()
        finally:
            flumine.config.simulated = _prev["simulated"]
            flumine.config.simulation_available_prices = \
                _prev["simulation_available_prices"]
            flumine.config.place_latency = _prev["place_latency"]
            flumine.config.cancel_latency = _prev["cancel_latency"]

    stats_out = params.get("stats_out")
    settled_out = params.get("settled_out")
    settled: List[Tuple[Any, str]] = []
    for i, strategy in enumerate(strategies):
        cell_settled = list(strategy.settled_orders)
        settled.extend(cell_settled)
        key = (str(event_id), i) if multi else str(event_id)
        if isinstance(stats_out, dict):
            stats_out[key] = dict(strategy.stats)
        if isinstance(settled_out, dict):
            settled_out[key] = cell_settled
        logger.info("[theta] evento %s cella %d: %d ordini regolati "
                    "(stats=%s)", event_id, i, len(cell_settled),
                    {k: v for k, v in strategy.stats.items() if v})
    return settled


def run_theta(
    params: Dict[str, Any], data_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Esegue il theta su tutti gli ``event_ids`` e aggrega le metriche.

    :param params: ``{event_ids:[str], commission_rate?, place_latency?,
        cancel_latency?, simulation_available_prices?, risk_cooldown_s?,
        atlas_path?, theta:{...}, theta_cells?:[{...}], stats_out?:{},
        settled_out?:{}}`` dove ``theta`` sono i parametri di ThetaStrategy
        (e ``theta_cells`` le celle della taratura S4, vedi _run_one_event).
    :returns: righe risultato (vedi ``aggregate_results``).
    """
    root = data_dir or DATA_DIR
    event_ids = [str(e) for e in (params.get("event_ids") or [])]
    if not event_ids:
        raise ValueError("params['event_ids'] vuoto")
    try:
        commission_rate = float(params.get("commission_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        commission_rate = 0.0

    # Atlante caricato UNA volta per tutta la batteria (v1 default;
    # ``atlas_path`` seleziona un file diverso, es. hazard_atlas_v2.json)
    atlas = (params.get("theta") or {}).get("atlas")
    if atlas is None:
        atlas = load_hazard_atlas(params.get("atlas_path"))

    tagged: List[Tuple[Any, str]] = []
    for event_id in event_ids:
        tagged.extend(_run_one_event(event_id, params, root, atlas))
    return aggregate_results(tagged, commission_rate=commission_rate)


def main() -> None:
    """CLI: ``python -m Betfair.stream.scalper.run_theta <event_id> ...``
    con i parametri di taratura S4 come flag ``--chiave=valore``:

    --hazard-max=0.085 --scratch-s=240 --line-offset=2 --max-goals=0
    --windows=0-35,46-70 --green-ticks=1 --entry-mode=maker|taker
    --taker-ticks=3 --postgol-wait-s=0 --overshoot --overshoot-min-s=30
    --overshoot-max-s=90 --atlas-path=<file.json> --commission=0.05
    """
    import sys

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    ids = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags: Dict[str, str] = {}
    for a in sys.argv[1:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("=")
            flags[k.replace("-", "_")] = v
    if not ids:
        raise SystemExit(
            "uso: python -m Betfair.stream.scalper.run_theta <event_id> ... "
            "[--hazard-max=..] (vedi docstring)")

    theta: Dict[str, Any] = {}
    if "hazard_max" in flags:
        theta["hazard_max"] = float(flags["hazard_max"])
    if "scratch_s" in flags:
        theta["scratch_s"] = float(flags["scratch_s"])
    if "line_offset" in flags:
        theta["line_offset"] = int(flags["line_offset"])
    if "max_goals" in flags:
        theta["max_goals"] = int(flags["max_goals"])
    if "windows" in flags and flags["windows"]:
        theta["entry_windows"] = [
            (float(w.split("-")[0]), float(w.split("-")[1]))
            for w in flags["windows"].split(",") if "-" in w]
    if "green_ticks" in flags:
        theta["green_ticks"] = int(flags["green_ticks"])
    if "entry_mode" in flags:
        theta["entry_mode"] = flags["entry_mode"]
    if "taker_ticks" in flags:
        theta["taker_ticks"] = int(flags["taker_ticks"])
    if "postgol_wait_s" in flags:
        theta["postgol_wait_s"] = float(flags["postgol_wait_s"])
    if "overshoot" in flags:
        theta["overshoot_only"] = True
    if "overshoot_min_s" in flags:
        theta["overshoot_min_s"] = float(flags["overshoot_min_s"])
    if "overshoot_max_s" in flags:
        theta["overshoot_max_s"] = float(flags["overshoot_max_s"])

    params: Dict[str, Any] = {
        "event_ids": ids,
        "commission_rate": float(flags.get("commission", 0.05) or 0.05),
        "theta": theta,
    }
    if flags.get("atlas_path"):
        params["atlas_path"] = flags["atlas_path"]
    rows = run_theta(params)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
