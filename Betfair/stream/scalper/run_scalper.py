"""Esecuzione backtest dello SCALPER via FlumineSimulation (replay forward-only).

Riusa l'aggregazione P&L del backtest ufficiale (:mod:`Betfair.stream.backtest.
run_backtest`): il profitto deriva ESCLUSIVAMENTE dal settlement simulato di
flumine (``order.simulated.profit``), con commissione per-mercato sul netto
vincente. Nessun dato futuro entra nelle decisioni della strategia.

Uso:
    from Betfair.stream.scalper.run_scalper import run_scalper
    rows = run_scalper({"event_ids": ["35674515"], "commission_rate": 0.05,
                        "scalper": {"scalp_ticks": 1, "max_spread_ticks": 2}})
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from ..backtest.run_backtest import aggregate_results
from ..config_stream import DATA_DIR
from .scalper_bot import ScalperStrategy

logger = logging.getLogger(__name__)

# esposizioni ampie: il sizing e' deciso dalla strategia, non vogliamo che i
# controlli di esposizione di default scartino gli ordini.
_MAX_EXPOSURE: float = 1_000_000.0

# flumine.config e' GLOBALE: serializza l'accesso per backtest concorrenti
# (es. grid-search multi-thread) altrimenti i flag si mescolano tra le run.
_CONFIG_LOCK = threading.Lock()


def _run_one_event(
    event_id: str, params: Dict[str, Any], data_dir: str
) -> List[Tuple[Any, str]]:
    raw_path = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(f"file nativo mancante: {raw_path}")

    scalper_params: Dict[str, Any] = dict(params.get("scalper") or {})

    with _CONFIG_LOCK:
        _prev = {
            "simulated": getattr(flumine.config, "simulated", False),
            "simulation_available_prices": getattr(
                flumine.config, "simulation_available_prices", False
            ),
            "place_latency": getattr(flumine.config, "place_latency", 0.120),
            "cancel_latency": getattr(flumine.config, "cancel_latency", 0.170),
        }
        flumine.config.simulated = True
        # default CONSERVATIVO: fill solo su volume realmente scambiato (no match
        # contro i prezzi disponibili) -> coerente con un maker che aspetta in coda.
        flumine.config.simulation_available_prices = bool(
            params.get("simulation_available_prices", False)
        )
        if params.get("place_latency") is not None:
            flumine.config.place_latency = float(params["place_latency"])
        if params.get("cancel_latency") is not None:
            flumine.config.cancel_latency = float(params["cancel_latency"])
        try:
            # min_bet_validation=False: consente hedge/close di size esatta (anche
            # < MIN_STAKE) cosi' i fill parziali si chiudono senza inflazione.
            # commission_base=0.0: la commissione e' applicata UNA SOLA volta, in
            # aggregate_results (evita doppio conteggio sul settlement simulato).
            client = clients.SimulatedClient(min_bet_validation=False)
            try:
                client.commission_base = 0.0
            except (TypeError, ValueError):
                pass
            framework = FlumineSimulation(client=client)
            framework.add_market_middleware(SimulatedMiddleware())

            strategy = ScalperStrategy(
                market_filter={"markets": [raw_path]},
                scalper_params=scalper_params,
                max_selection_exposure=_MAX_EXPOSURE,
                max_order_exposure=_MAX_EXPOSURE,
                max_trade_count=int(1e9),
                max_live_trade_count=int(1e9),
            )
            framework.add_strategy(strategy)
            framework.run()
        finally:
            flumine.config.simulated = _prev["simulated"]
            flumine.config.simulation_available_prices = _prev["simulation_available_prices"]
            flumine.config.place_latency = _prev["place_latency"]
            flumine.config.cancel_latency = _prev["cancel_latency"]

    settled = list(strategy.settled_orders)
    logger.info("[scalper] evento %s: %d ordini regolati", event_id, len(settled))
    return settled


def run_scalper(
    params: Dict[str, Any], data_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Esegue lo scalper su tutti gli ``event_ids`` e aggrega le metriche.

    :param params: ``{event_ids:[str], commission_rate?, place_latency?,
        cancel_latency?, simulation_available_prices?, scalper:{...}}`` dove
        ``scalper`` contiene i parametri di :class:`ScalperStrategy`.
    :returns: righe risultato (vedi :func:`aggregate_results`).
    """
    root = data_dir or DATA_DIR
    event_ids = [str(e) for e in (params.get("event_ids") or [])]
    if not event_ids:
        raise ValueError("params['event_ids'] vuoto")

    # GUARDIA REGISTRAZIONI PARZIALI (fix 17/07 "tuning senza guardia", come
    # run_backtest/run_theta): default = solo WARNING visibile per evento
    # non-COMPLETE; con ``params['min_coverage']`` (percento) gli eventi sotto
    # soglia vengono ESCLUSI (ValueError se non resta nulla). L'esito finisce
    # anche nei risultati (metrics.coverage_pct / coverage_verdict) + alert WARN.
    coverage_reports: Dict[str, Any] = {}
    try:
        from ..tools.validate_recordings import check_events_with_reports

        event_ids, coverage_reports = check_events_with_reports(
            event_ids, root, params.get("min_coverage"))
    except ValueError:
        raise  # filtro esplicito richiesto e nessun evento valido: deve fallire
    except Exception as e:  # noqa: BLE001 - la guardia non blocca il replay
        logger.warning("[scalper] validazione registrazioni KO (ignorata): %s", e)

    try:
        commission_rate = float(params.get("commission_rate", 0.0) or 0.0)
    except (TypeError, ValueError):
        commission_rate = 0.0

    tagged: List[Tuple[Any, str]] = []
    for event_id in event_ids:
        tagged.extend(_run_one_event(event_id, params, root))
    rows = aggregate_results(tagged, commission_rate=commission_rate)
    if coverage_reports:
        from ..backtest.run_backtest import (
            attach_coverage, build_coverage_meta, emit_coverage_alerts)

        attach_coverage(rows, build_coverage_meta(coverage_reports, event_ids))
        emit_coverage_alerts(coverage_reports, event_ids, "scalper")
    return rows
