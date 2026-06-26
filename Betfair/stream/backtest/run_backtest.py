"""Esecuzione del backtest via motore UFFICIALE flumine (FlumineSimulation).

API flumine usata (verificata su flumine 2.13.11 / betfairlightweight 2.23.2):

    import flumine.config
    flumine.config.simulated = True
    from flumine import FlumineSimulation, clients
    from flumine.markets.middleware import SimulatedMiddleware

    framework = FlumineSimulation(client=clients.SimulatedClient())
    framework.add_market_middleware(SimulatedMiddleware())
    strategy = SimStrategy(..., market_filter={"markets": [raw_file_path]})
    framework.add_strategy(strategy)
    framework.run()

``Streams.__call__`` rileva ``framework.SIMULATED`` e, leggendo
``market_filter["markets"]`` (lista di PATH a file nativi), crea per ciascuno una
``flumine.streams.historicalstream.HistoricalStream`` che fa il replay del file
``.raw.jsonl`` (formato storico/registrato Betfair). Il matching e il settlement
degli ordini sono eseguiti da ``SimulatedMiddleware`` + dal client simulato.

Le metriche sono calcolate ESCLUSIVAMENTE dal settlement simulato di flumine:
``order.simulated.profit`` (P&L netto post-settlement) e ``order.size_matched``
(stake matchato). Nulla proviene da ``master_backtest``.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import flumine.config
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from ..config_stream import DATA_DIR
from .sim_strategy import SimStrategy

logger = logging.getLogger(__name__)

# esposizioni ampie: il dimensionamento e' gia' deciso da Kelly/regole, non
# vogliamo che i controlli di esposizione di default scartino gli ordini.
_MAX_EXPOSURE: float = 1_000_000.0


# ---------------------------------------------------------------------------
# Estrazione campi dal settlement simulato di flumine
# ---------------------------------------------------------------------------
def order_profit(order: Any) -> float:
    """P&L netto post-settlement dell'ordine simulato (``order.simulated.profit``).

    Campo individuato per la versione installata: la property ``profit`` di
    ``flumine.simulation.simulatedorder.SimulatedOrder`` (esposta su
    ``order.simulated``), che applica WINNER/LOSER/PLACED in base a
    ``runner_status``.
    """
    sim = getattr(order, "simulated", None)
    if sim is not None:
        profit = getattr(sim, "profit", None)
        if profit is not None:
            return float(profit)
    return 0.0


def order_stake(order: Any) -> float:
    """Stake effettivamente matchato (``order.size_matched``)."""
    return float(getattr(order, "size_matched", 0.0) or 0.0)


def _order_price(order: Any) -> Optional[float]:
    price = getattr(order, "average_price_matched", None)
    return float(price) if price else None


def _order_side(order: Any) -> Optional[str]:
    side = getattr(order, "side", None)
    if side:
        return str(side)
    sim = getattr(order, "simulated", None)
    return str(getattr(sim, "side", None)) if sim is not None else None


# ---------------------------------------------------------------------------
# Aggregazione metriche (pura, testabile con mock)
# ---------------------------------------------------------------------------
def compute_group_metrics(orders: List[Any]) -> Dict[str, Any]:
    """Calcola le metriche per un gruppo di ordini SIMULATI matchati.

    Ogni ``order`` deve esporre ``size_matched``, ``simulated.profit``,
    ``side`` e ``average_price_matched`` (compatibile con flumine BetfairOrder).
    Considera solo gli ordini con ``size_matched > 0``.
    """
    matched = [o for o in orders if order_stake(o) > 0]
    n_bets = len(matched)
    if n_bets == 0:
        return {
            "n_bets": 0,
            "n_won": 0,
            "hit_rate": 0.0,
            "roi": 0.0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "avg_odds": 0.0,
            "metrics": {"n_back": 0, "n_lay": 0, "total_stake": 0.0},
        }

    total_pnl = 0.0
    total_stake = 0.0
    n_won = 0
    n_back = 0
    n_lay = 0
    odds_sum = 0.0
    odds_n = 0
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0

    for o in matched:
        profit = order_profit(o)
        stake = order_stake(o)
        total_pnl += profit
        total_stake += stake
        if profit > 0:
            n_won += 1
        side = (_order_side(o) or "").upper()
        if side == "BACK":
            n_back += 1
        elif side == "LAY":
            n_lay += 1
        price = _order_price(o)
        if price:
            odds_sum += price
            odds_n += 1
        # drawdown sul P&L cumulato (sequenza d'ingresso)
        cumulative += profit
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    return {
        "n_bets": n_bets,
        "n_won": n_won,
        "hit_rate": round(n_won / n_bets, 6) if n_bets else 0.0,
        "roi": round(total_pnl / total_stake, 6) if total_stake else 0.0,
        "total_pnl": round(total_pnl, 4),
        "max_drawdown": round(max_drawdown, 4),
        "avg_odds": round(odds_sum / odds_n, 4) if odds_n else 0.0,
        "metrics": {
            "n_back": n_back,
            "n_lay": n_lay,
            "total_stake": round(total_stake, 4),
        },
    }


def _row(scope: str, grp: str, orders: List[Any]) -> Dict[str, Any]:
    m = compute_group_metrics(orders)
    return {
        "scope": scope,
        "grp": grp,
        "n_bets": m["n_bets"],
        "n_won": m["n_won"],
        "hit_rate": m["hit_rate"],
        "roi": m["roi"],
        "total_pnl": m["total_pnl"],
        "max_drawdown": m["max_drawdown"],
        "avg_odds": m["avg_odds"],
        "metrics": m["metrics"],
    }


def aggregate_results(tagged_orders: List[Tuple[Any, str]]) -> List[Dict[str, Any]]:
    """Aggrega gli ordini simulati in righe risultato.

    :param tagged_orders: lista di ``(order, market_type)``.
    :returns: una riga ``scope='ALL'`` + una riga per ``market_type``.
    """
    all_orders = [o for o, _ in tagged_orders]
    rows: List[Dict[str, Any]] = [_row("ALL", "ALL", all_orders)]

    by_type: Dict[str, List[Any]] = {}
    for order, mtype in tagged_orders:
        by_type.setdefault(str(mtype or "UNKNOWN"), []).append(order)

    for mtype in sorted(by_type):
        rows.append(_row("MARKET_TYPE", mtype, by_type[mtype]))
    return rows


# ---------------------------------------------------------------------------
# Caricamento dati sidecar (scores / catalogo nomi) — opzionali
# ---------------------------------------------------------------------------
def _load_scores(
    data_dir: str, event_id: str
) -> List[Tuple[int, Optional[int], int, int]]:
    """Carica ``<event>.scores.jsonl`` se presente: [(ts_ms, minute, sh, sa)]."""
    path = os.path.join(data_dir, str(event_id), f"{event_id}.scores.jsonl")
    out: List[Tuple[int, Optional[int], int, int]] = []
    if not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except (ValueError, TypeError):
                continue
            ts = rec.get("ts_ms")
            if ts is None:
                continue
            out.append(
                (
                    int(ts),
                    rec.get("minute"),
                    int(rec.get("score_home") or 0),
                    int(rec.get("score_away") or 0),
                )
            )
    return out


def _load_catalogue(data_dir: str, event_id: str) -> Dict[str, Dict[str, Any]]:
    """Carica ``<event>.catalogue.json`` se presente (nomi selezioni reali).

    Formato atteso: {market_id: {market_type, selections:[{selection_id,name,
    sort_priority}]}}. Opzionale: in sua assenza i nomi sono sintetizzati.
    """
    path = os.path.join(data_dir, str(event_id), f"{event_id}.catalogue.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, TypeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Esecuzione
# ---------------------------------------------------------------------------
def _run_one_event(
    event_id: str, params: Dict[str, Any], data_dir: str
) -> List[Tuple[Any, str]]:
    """Esegue una FlumineSimulation per un evento e ritorna [(order, mtype)]."""
    raw_path = os.path.join(data_dir, str(event_id), f"{event_id}.raw.jsonl")
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(f"file nativo mancante: {raw_path}")

    scores = _load_scores(data_dir, event_id)
    catalogue = _load_catalogue(data_dir, event_id)

    # richiesto da questa versione per il path di simulazione/ordini
    flumine.config.simulated = True

    framework = FlumineSimulation(client=clients.SimulatedClient())
    framework.add_market_middleware(SimulatedMiddleware())

    strategy = SimStrategy(
        params=params,
        event_id=str(event_id),
        scores=scores,
        catalogue=catalogue,
        market_filter={"markets": [raw_path]},
        max_selection_exposure=_MAX_EXPOSURE,
        max_order_exposure=_MAX_EXPOSURE,
        max_trade_count=int(1e9),
        max_live_trade_count=int(1e9),
    )
    framework.add_strategy(strategy)
    framework.run()

    logger.info(
        "[backtest] evento %s: %d ordini regolati",
        event_id,
        len(strategy.settled_orders),
    )
    return list(strategy.settled_orders)


def run_backtest(
    params: Dict[str, Any], data_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Esegue il backtest su tutti gli ``event_ids`` e aggrega le metriche.

    :param params: ``{event_ids:[str], mode:'engine'|'sandbox', bankroll?,
        min_edge?, kelly_fraction?, rules?:{}}``.
    :param data_dir: radice dei file nativi (default ``config_stream.DATA_DIR``).
    :returns: righe risultato (vedi :func:`aggregate_results`).
    """
    root = data_dir or DATA_DIR
    event_ids = [str(e) for e in (params.get("event_ids") or [])]
    if not event_ids:
        raise ValueError("params['event_ids'] vuoto")

    tagged: List[Tuple[Any, str]] = []
    for event_id in event_ids:
        tagged.extend(_run_one_event(event_id, params, root))

    return aggregate_results(tagged)
