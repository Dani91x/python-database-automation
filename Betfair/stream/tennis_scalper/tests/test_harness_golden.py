"""GOLDEN-RULE: valida l'harness backtest con scenari sintetici a risultato NOTO.

Protegge dal bug piu' pericoloso (metrica P&L rotta / green non catturato = falso
"no edge"). Costruisce stream Betfair mcm sintetici con trd CUMULATIVO e verifica
che TennisLab in FlumineSimulation (simulation_available_prices=False) registri il
P&L GIUSTO:
  CRASH (fav perde) -> ~+stake ;  HOLD (fav vince) -> ~-liability ;
  DEAD (0 volume)   -> 0 fill  ;  SCALP (green)    -> round-trip verde > 0.
"""
from __future__ import annotations

import json
import os

import flumine.config
import pytest
from flumine import FlumineSimulation, clients
from flumine.markets.middleware import SimulatedMiddleware

from ..tennis_lab import TennisLabStrategy

MID = "1.999999999"
A, B = 111, 222  # A favorito, B sfavorito


def _mdef(status, inplay, winner=None):
    runners = []
    for rid in (A, B):
        st = "ACTIVE"
        if status == "CLOSED":
            st = "WINNER" if rid == winner else "LOSER"
        runners.append({"id": rid, "status": st, "sortPriority": 1 if rid == A else 2})
    return {"betDelay": 3, "bspMarket": False, "turnInPlayEnabled": True,
            "persistenceEnabled": True, "marketBaseRate": 0.0, "eventId": "1",
            "eventTypeId": "2", "numberOfWinners": 1, "bettingType": "ODDS",
            "marketType": "MATCH_ODDS", "marketTime": "2026-07-07T12:00:00.000Z",
            "suspendTime": "2026-07-07T12:00:00.000Z", "bspReconciled": False,
            "complete": True, "inPlay": inplay, "crossMatching": True,
            "runnersVoidable": False, "numberOfActiveRunners": 2,
            "status": status, "regulators": ["MR_INT"], "discountAllowed": True,
            "timezone": "GMT", "priceLadderDefinition": {"type": "CLASSIC"},
            "runners": runners, "version": 1, "marketId": MID}


def _line(pt, rc, md=None, img=False, clk="1"):
    mc = {"id": MID, "rc": rc}
    if md is not None:
        mc["marketDefinition"] = md
    if img:
        mc["img"] = True
    return json.dumps({"op": "mcm", "clk": clk, "pt": pt, "mc": [mc]})


def _rc(rid, back, lay, trd_cum, ltp):
    return {"id": rid, "atb": back, "atl": lay, "trd": trd_cum, "ltp": ltp}


def _write(path, frames):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(frames) + "\n")


def _crash(path, favorite_loses):
    fr = []
    pt = 1_700_000_000_000
    fr.append(_line(pt, [_rc(A, [[1.04, 500]], [[1.05, 3]], [], 1.05),
                         _rc(B, [[15, 20]], [[17, 20]], [], 16.0)],
                    md=_mdef("OPEN", False), img=True, clk="0"))
    pt += 1000
    fr.append(_line(pt, [_rc(A, [[1.04, 500]], [[1.05, 3]], [[1.05, 0.0]], 1.05),
                         _rc(B, [[15, 20]], [[17, 20]], [], 16.0)], md=_mdef("OPEN", True)))
    cum = 0.0
    for _ in range(12):
        pt += 2000; cum += 50.0
        fr.append(_line(pt, [_rc(A, [[1.04, 500]], [[1.05, 3]], [[1.05, cum]], 1.05),
                             _rc(B, [[15, 20]], [[17, 20]], [], 16.0)]))
    for p in (1.2, 1.8, 2.5, 3.0):
        pt += 2000
        fr.append(_line(pt, [_rc(A, [[p - 0.1, 100]], [[p, 100]], [[1.05, cum]], p),
                             _rc(B, [[1.4, 100]], [[1.5, 100]], [], 1.45)]))
    pt += 2000
    fr.append(_line(pt, [_rc(A, [], [], [[1.05, cum]], None), _rc(B, [], [], [], None)],
                    md=_mdef("CLOSED", True, winner=B if favorite_loses else A)))
    _write(path, fr)


def _dead(path):
    fr = []
    pt = 1_700_000_000_000
    fr.append(_line(pt, [_rc(A, [[1.5, 5]], [[2.0, 5]], [], 1.7),
                         _rc(B, [[2.0, 5]], [[2.5, 5]], [], 2.2)],
                    md=_mdef("OPEN", False), img=True, clk="0"))
    pt += 1000
    fr.append(_line(pt, [_rc(A, [[1.5, 5]], [[2.0, 5]], [], 1.7),
                         _rc(B, [[2.0, 5]], [[2.5, 5]], [], 2.2)], md=_mdef("OPEN", True)))
    for _ in range(10):
        pt += 2000
        fr.append(_line(pt, [_rc(A, [[1.5, 5]], [[2.0, 5]], [], 1.7),
                             _rc(B, [[2.0, 5]], [[2.5, 5]], [], 2.2)]))
    pt += 2000
    fr.append(_line(pt, [_rc(A, [], [], [], None), _rc(B, [], [], [], None)],
                    md=_mdef("CLOSED", True, winner=A)))
    _write(path, fr)


def _scalp(path):
    fr = []
    pt = 1_700_000_000_000
    fr.append(_line(pt, [_rc(A, [[1.09, 500]], [[1.10, 3]], [], 1.10),
                         _rc(B, [[9, 20]], [[11, 20]], [], 10.0)],
                    md=_mdef("OPEN", False), img=True, clk="0"))
    pt += 1000
    fr.append(_line(pt, [_rc(A, [[1.09, 500]], [[1.10, 3]], [[1.10, 0.0]], 1.10),
                         _rc(B, [[9, 20]], [[11, 20]], [], 10.0)], md=_mdef("OPEN", True)))
    cum = 0.0
    for _ in range(6):
        pt += 2000; cum += 50.0
        fr.append(_line(pt, [_rc(A, [[1.09, 500]], [[1.10, 3]], [[1.10, cum]], 1.10),
                             _rc(B, [[9, 20]], [[11, 20]], [], 10.0)]))
    cumu = 0.0
    for p in (1.13, 1.16, 1.20, 1.20, 1.20):
        pt += 2000; cumu += 50.0
        fr.append(_line(pt, [_rc(A, [[p, 3]], [[p + 0.01, 500]], [[1.10, cum], [p, cumu]], p),
                             _rc(B, [[6, 20]], [[7, 20]], [], 6.5)]))
    pt += 2000
    fr.append(_line(pt, [_rc(A, [], [], [[1.10, cum]], None), _rc(B, [], [], [], None)],
                    md=_mdef("CLOSED", True, winner=A)))
    _write(path, fr)


def _run(path, params):
    prev = getattr(flumine.config, "simulation_available_prices", False)
    flumine.config.simulated = True
    flumine.config.simulation_available_prices = False
    try:
        c = clients.SimulatedClient(min_bet_validation=False)
        try:
            c.commission_base = 0.0
        except (TypeError, ValueError):
            pass
        fw = FlumineSimulation(client=c)
        fw.add_market_middleware(SimulatedMiddleware())
        s = TennisLabStrategy(market_filter={"markets": [path]},
                              lab_params={**params, "dry_run": False},
                              max_selection_exposure=1e6, max_order_exposure=1e6,
                              max_trade_count=int(1e9), max_live_trade_count=int(1e9))
        fw.add_strategy(s)
        fw.run()
        return s.settled_pnl, dict(s.stats)
    finally:
        flumine.config.simulation_available_prices = prev


_FLB = {"side": "LAY", "target": "favorite", "price_min": 1.01, "price_max": 1.10,
        "gate": "inplay", "maker": True, "exit_mode": "hold", "min_matched": 0.0,
        "min_size": 1.0, "bet_delay_ms": 0}
_SCALP = {**_FLB, "price_max": 1.12, "exit_mode": "green", "green_ticks": 3}


def test_crash_registra_profitto(tmp_path):
    p = str(tmp_path / "crash.raw.jsonl"); _crash(p, favorite_loses=True)
    pnl, st = _run(p, _FLB)
    assert pnl > 1.0, f"CRASH deve dare ~+stake, dato {pnl}"
    assert st["entries"] >= 1


def test_hold_perdita_piccola(tmp_path):
    p = str(tmp_path / "hold.raw.jsonl"); _crash(p, favorite_loses=False)
    pnl, _ = _run(p, _FLB)
    assert -0.5 < pnl < 0.0, f"HOLD deve dare piccola liability, dato {pnl}"


def test_dead_nessun_profitto_finto(tmp_path):
    p = str(tmp_path / "dead.raw.jsonl"); _dead(p)
    pnl, st = _run(p, _FLB)
    assert abs(pnl) < 0.01 and st["entries"] == 0, f"DEAD non deve fillare, dato {pnl}"


def test_scalp_roundtrip_verde_catturato(tmp_path):
    p = str(tmp_path / "scalp.raw.jsonl"); _scalp(p)
    pnl, st = _run(p, _SCALP)
    assert pnl > 0.02, f"green round-trip deve dare P&L>0 (bug #1/#2), dato {pnl}"
    assert st.get("greens", 0) >= 1


# ---------------------------------------------------------------------------
# METRICA LOCKED (fix review): il "VERDETTO PRIMARIO" di validate.py e' locked,
# non settled_pnl — la matematica del min-sul-vincitore va protetta a unita'
# (una regressione qui produrrebbe un falso "no edge" su TUTTA la ricerca).
# ---------------------------------------------------------------------------
class _FakeOrder:
    def __init__(self, sel: int, side: str, size_matched: float, avg_price: float) -> None:
        self.selection_id = sel
        self.side = side
        self.size_matched = size_matched
        self.average_price_matched = avg_price


class _FakeRunner:
    def __init__(self, sel: int) -> None:
        self.selection_id = sel


class _FakeBook:
    def __init__(self, sels: list) -> None:
        self.runners = [_FakeRunner(s) for s in sels]


def test_locked_greenup_round_trip_is_positive_on_both_outcomes():
    """BACK 10@2.2 poi LAY 11@2.0 (round-trip verde): locked = min esiti > 0.
    Vince A: +10*1.2 - 11*1.0 = +1.0 ; vince B: -10 + 11 = +1.0 -> locked=+1.0."""
    orders = [_FakeOrder(111, "BACK", 10.0, 2.2), _FakeOrder(111, "LAY", 11.0, 2.0)]
    locked = TennisLabStrategy._locked_from_orders(orders, _FakeBook([111, 222]))
    assert locked == pytest.approx(1.0, abs=1e-9)


def test_locked_naked_back_leg_is_minus_stake():
    """Gamba BACK nuda 10@2.2: worst case (selezione perde) = -10 (mai il best case)."""
    orders = [_FakeOrder(111, "BACK", 10.0, 2.2)]
    locked = TennisLabStrategy._locked_from_orders(orders, _FakeBook([111, 222]))
    assert locked == pytest.approx(-10.0, abs=1e-9)


def test_locked_naked_lay_leg_is_minus_liability():
    """Gamba LAY nuda 10@3.0: worst case (selezione vince) = -liability = -20."""
    orders = [_FakeOrder(111, "LAY", 10.0, 3.0)]
    locked = TennisLabStrategy._locked_from_orders(orders, _FakeBook([111, 222]))
    assert locked == pytest.approx(-20.0, abs=1e-9)


def test_locked_ignores_unmatched_and_empty():
    """Ordini senza matched non contano; nessun ordine matched -> 0."""
    orders = [_FakeOrder(111, "BACK", 0.0, 2.2), _FakeOrder(111, "LAY", 5.0, 0.0)]
    assert TennisLabStrategy._locked_from_orders(orders, _FakeBook([111, 222])) == 0.0
    assert TennisLabStrategy._locked_from_orders([], _FakeBook([111, 222])) == 0.0
