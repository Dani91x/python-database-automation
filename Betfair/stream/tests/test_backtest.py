"""Test del Backtest Automatico (FlumineSimulation ufficiale + aggregazione).

Due livelli:

1. ``test_full_simulation_sandbox_back_winner`` — crea un file nativo
   ``<event>.raw.jsonl`` sintetico (SUB_IMAGE con prezzi + update + CLOSED con
   vincitore) in una dir temporanea, esegue una vera FlumineSimulation in
   modalita' ``sandbox`` che piazza UN ordine BACK sul vincitore, e verifica che
   l'aggregazione produca una riga con P&L del segno atteso (positivo).

2. ``test_compute_group_metrics_*`` — unit test PURO della funzione di
   aggregazione con oggetti-ordine finti (``size_matched`` / ``simulated.profit``
   / ``side`` / ``average_price_matched``), indipendente da flumine.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional

import pytest

from Betfair.stream.backtest.run_backtest import (
    aggregate_results,
    compute_group_metrics,
    order_profit,
    order_stake,
    run_backtest,
)

EVENT_ID = "test_evt_1"
MARKET_ID = "1.111"
WINNER = 111
LOSER = 222
T0 = 1_700_000_000_000  # publish_time base (ms)


def _market_definition(status: str, runners: List[dict]) -> dict:
    return {
        "betDelay": 0,
        "bettingType": "ODDS",
        "bspMarket": False,
        "bspReconciled": False,
        "complete": True,
        "crossMatching": True,
        "discountAllowed": True,
        "eventId": "32999999",
        "eventTypeId": "1",
        "inPlay": True,
        "marketBaseRate": 5.0,
        "marketTime": "2023-11-14T20:00:00.000Z",
        "numberOfActiveRunners": 2,
        "numberOfWinners": 1,
        "persistenceEnabled": True,
        "regulators": "MR_INT",
        "runnersVoidable": False,
        "status": status,
        "timezone": "GMT",
        "turnInPlayEnabled": True,
        "version": 1,
        "marketType": "MATCH_ODDS",
        "runners": runners,
    }


def _active(sid: int, sp: int) -> dict:
    return {"id": sid, "sortPriority": sp, "status": "ACTIVE"}


def _result(sid: int, sp: int, status: str) -> dict:
    return {"id": sid, "sortPriority": sp, "status": status}


def _write_raw_file(data_dir: str) -> str:
    ev_dir = os.path.join(data_dir, EVENT_ID)
    os.makedirs(ev_dir, exist_ok=True)
    path = os.path.join(ev_dir, f"{EVENT_ID}.raw.jsonl")

    # 1) SUB_IMAGE: mercato aperto in-play con prezzi (atb/atl) -> place
    sub_image = {
        "op": "mcm",
        "clk": "1",
        "pt": T0,
        "ct": "SUB_IMAGE",
        "mc": [
            {
                "id": MARKET_ID,
                "marketDefinition": _market_definition(
                    "OPEN", [_active(WINNER, 1), _active(LOSER, 2)]
                ),
                "rc": [
                    {"id": WINNER, "atb": [[3.0, 500.0]], "atl": [[3.05, 500.0]], "ltp": 3.0},
                    {"id": LOSER, "atb": [[1.5, 500.0]], "atl": [[1.52, 500.0]], "ltp": 1.5},
                ],
            }
        ],
    }
    # 2) update ~5s dopo: lascia processare la coda ordini (latency) -> match
    update = {
        "op": "mcm",
        "clk": "2",
        "pt": T0 + 5_000,
        "mc": [
            {
                "id": MARKET_ID,
                "rc": [
                    {"id": WINNER, "atb": [[3.0, 500.0]], "atl": [[3.05, 500.0]], "ltp": 3.0},
                    {"id": LOSER, "atb": [[1.5, 500.0]], "atl": [[1.52, 500.0]], "ltp": 1.5},
                ],
            }
        ],
    }
    # 3) CLOSED ~10s dopo: vincitore = WINNER -> settlement
    closed = {
        "op": "mcm",
        "clk": "3",
        "pt": T0 + 10_000,
        "mc": [
            {
                "id": MARKET_ID,
                "marketDefinition": _market_definition(
                    "CLOSED",
                    [_result(WINNER, 1, "WINNER"), _result(LOSER, 2, "LOSER")],
                ),
            }
        ],
    }

    with open(path, "w", encoding="utf-8") as fh:
        for msg in (sub_image, update, closed):
            fh.write(json.dumps(msg) + "\n")
    return path


def test_full_simulation_sandbox_back_winner(tmp_path: Any) -> None:
    """BACK 10 sul vincitore @3.0 -> profit atteso = 10*(3.0-1) = +20."""
    data_dir = str(tmp_path)
    _write_raw_file(data_dir)

    params = {
        "event_ids": [EVENT_ID],
        "mode": "sandbox",
        "rules": {
            "market_type": "MATCH_ODDS",
            "side": "BACK",
            "selection_id": WINNER,
            "stake": 10.0,
            "entry_price_max": 100.0,
        },
    }

    rows = run_backtest(params, data_dir=data_dir)

    assert rows, "nessuna riga risultato prodotta"
    all_row = next(r for r in rows if r["scope"] == "ALL")
    assert all_row["n_bets"] == 1, f"atteso 1 bet, righe={rows}"
    assert all_row["n_won"] == 1
    assert all_row["total_pnl"] > 0, f"P&L non positivo: {all_row}"
    # back @3.0 stake 10 -> +20 (al netto: la property profit e' lorda)
    assert all_row["total_pnl"] == pytest.approx(20.0, abs=1e-6)
    assert all_row["avg_odds"] == pytest.approx(3.0, abs=1e-6)

    # esiste anche la riga per market_type MATCH_ODDS
    mo_row = next(
        (r for r in rows if r["scope"] == "MARKET_TYPE" and r["grp"] == "MATCH_ODDS"),
        None,
    )
    assert mo_row is not None
    assert mo_row["total_pnl"] == pytest.approx(20.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Unit test PURO dell'aggregazione (mock di ordini simulati)
# ---------------------------------------------------------------------------
@dataclass
class _FakeSimulated:
    profit: float


@dataclass
class _FakeOrder:
    size_matched: float
    side: str
    average_price_matched: Optional[float]
    simulated: _FakeSimulated


def _mk(size: float, profit: float, side: str = "BACK", price: float = 2.0) -> _FakeOrder:
    return _FakeOrder(
        size_matched=size,
        side=side,
        average_price_matched=price,
        simulated=_FakeSimulated(profit=profit),
    )


def test_order_profit_and_stake_readers() -> None:
    o = _mk(size=10.0, profit=20.0)
    assert order_profit(o) == 20.0
    assert order_stake(o) == 10.0


def test_compute_group_metrics_mixed() -> None:
    orders = [
        _mk(size=10.0, profit=20.0, side="BACK", price=3.0),  # vinto
        _mk(size=10.0, profit=-10.0, side="BACK", price=2.0),  # perso
        _mk(size=5.0, profit=5.0, side="LAY", price=4.0),  # vinto
        _mk(size=0.0, profit=0.0, side="BACK", price=None),  # non matchato -> escluso
    ]
    m = compute_group_metrics(orders)

    assert m["n_bets"] == 3
    assert m["n_won"] == 2
    assert m["hit_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert m["total_pnl"] == pytest.approx(15.0, abs=1e-6)
    assert m["roi"] == pytest.approx(15.0 / 25.0, abs=1e-6)
    assert m["avg_odds"] == pytest.approx((3.0 + 2.0 + 4.0) / 3, abs=1e-6)
    assert m["metrics"]["n_back"] == 2
    assert m["metrics"]["n_lay"] == 1
    # drawdown: cumulato 20 -> 10 -> 15, picco 20, max DD = 10
    assert m["max_drawdown"] == pytest.approx(10.0, abs=1e-6)


def test_compute_group_metrics_empty() -> None:
    m = compute_group_metrics([])
    assert m["n_bets"] == 0
    assert m["total_pnl"] == 0.0
    assert m["roi"] == 0.0
    assert m["max_drawdown"] == 0.0


def test_aggregate_results_scopes() -> None:
    tagged = [
        (_mk(size=10.0, profit=20.0, price=3.0), "MATCH_ODDS"),
        (_mk(size=10.0, profit=-10.0, price=2.0), "OVER_UNDER_25"),
    ]
    rows = aggregate_results(tagged)
    scopes = {(r["scope"], r["grp"]) for r in rows}
    assert ("ALL", "ALL") in scopes
    assert ("MARKET_TYPE", "MATCH_ODDS") in scopes
    assert ("MARKET_TYPE", "OVER_UNDER_25") in scopes
    all_row = next(r for r in rows if r["scope"] == "ALL")
    assert all_row["n_bets"] == 2
    assert all_row["total_pnl"] == pytest.approx(10.0, abs=1e-6)
