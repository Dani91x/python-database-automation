"""Backtest Automatico — motore di simulazione UFFICIALE flumine.

Esegue le strategie del progetto sopra i file nativi Betfair registrati dal
runner live (``<DATA_DIR>/<event_id>/<event_id>.raw.jsonl``) usando il motore
ufficiale di flumine :class:`flumine.FlumineSimulation` (replay storico +
matching/settlement simulato). NON usa ``master_backtest.py``: tutte le metriche
provengono esclusivamente dal settlement simulato di flumine
(``order.simulated.profit`` / ``order.size_matched``).

Gira in LOCALE (no Vercel). Il worker consuma la coda ``live_backtest_requests``
e scrive su ``live_backtest_results`` tramite ``Betfair.stream.db``.
"""
from __future__ import annotations

from .run_backtest import (
    aggregate_results,
    compute_group_metrics,
    order_profit,
    order_stake,
    run_backtest,
)
from .sim_strategy import SimStrategy

__all__ = [
    "SimStrategy",
    "run_backtest",
    "aggregate_results",
    "compute_group_metrics",
    "order_profit",
    "order_stake",
]
