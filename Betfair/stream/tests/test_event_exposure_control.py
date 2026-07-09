"""Test ADVERSARIALI di LiveEventExposureControl (E35 — limiti per evento/campionato).

NESSUNA rete: flumine/blotter/settings/league-map sono fake. La perdita di mercato
viene da un blotter fake che imita ``Blotter.market_exposure`` (negativo = perdita).

Garanzie sotto test:
  - limiti spenti → mai un blocco;
  - chiusure (reduces_liability) → MAI bloccate, anche oltre cap;
  - cap EVENTO: somma dei worst-case dei mercati dell'evento (target col nuovo
    ordine incluso) → blocco STRETTO oltre soglia, permesso entro;
  - cap CAMPIONATO: somma degli eventi dello stesso campionato (mappa live_follow);
  - fail-open: target non valutabile → nessun blocco; secondario non valutabile →
    escluso dalla somma (mai un falso blocco);
  - package CANCEL/REPLACE ignorati; mercati chiusi esclusi.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine.exceptions import ControlError
from flumine.order.orderpackage import OrderPackageType

import Betfair.stream.trading.controls as ctl


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class _Blotter:
    """market_exposure fake: valore fisso; con new_order aggiunge il suo contributo."""

    def __init__(self, exposure: Optional[float], new_order_delta: float = 0.0,
                 raises: bool = False) -> None:
        self._exposure = exposure
        self._delta = new_order_delta
        self._raises = raises

    def market_exposure(self, strategy: Any, market_book: Any, exclusion: Any = None,
                        new_order: Any = None) -> float:
        if self._raises:
            raise RuntimeError("blotter boom")
        base = self._exposure
        if base is None:
            raise RuntimeError("exposure non calcolabile")
        return base + (self._delta if new_order is not None else 0.0)


def _mkt(market_id: str, event_id: Optional[str], exposure: Optional[float],
         *, new_order_delta: float = 0.0, closed: bool = False,
         raises: bool = False) -> Any:
    return SimpleNamespace(
        market_id=market_id,
        event_id=event_id,
        closed=closed,
        blotter=_Blotter(exposure, new_order_delta, raises),
        market_book=SimpleNamespace(number_of_active_runners=3, number_of_winners=1),
    )


class _Order:
    def __init__(self, market_id: str, context: Optional[Dict[str, Any]] = None) -> None:
        self.market_id = market_id
        self.context = context or {}
        self.trade = SimpleNamespace(strategy=object())
        self.violations: List[str] = []
        self.info = {"market_id": market_id}

    def violation(self, msg: str) -> None:
        self.violations.append(msg)


def _control(*markets: Any) -> ctl.LiveEventExposureControl:
    flu = SimpleNamespace(markets=SimpleNamespace(markets={m.market_id: m for m in markets}))
    return ctl.LiveEventExposureControl(flu)


@pytest.fixture()
def caps(monkeypatch):
    state = {"max_exposure_per_event": None, "max_exposure_per_league": None}
    monkeypatch.setattr(ctl, "get_live_settings", lambda force=False: dict(state))
    monkeypatch.setattr(ctl, "_league_map", lambda force=False: {})
    return state


# ---------------------------------------------------------------------------
# Limiti spenti / package non-PLACE / chiusure
# ---------------------------------------------------------------------------
def test_no_caps_never_blocks(caps):
    c = _control(_mkt("1.1", "ev1", -1000.0))
    c(_Order("1.1"), OrderPackageType.PLACE)  # nessuna eccezione


def test_cancel_package_ignored(caps):
    caps["max_exposure_per_event"] = 10.0
    c = _control(_mkt("1.1", "ev1", -1000.0))
    c(_Order("1.1"), OrderPackageType.CANCEL)  # nessuna eccezione


def test_closing_orders_never_blocked(caps):
    caps["max_exposure_per_event"] = 10.0
    c = _control(_mkt("1.1", "ev1", -1000.0))
    c(_Order("1.1", context={"reduces_liability": True}), OrderPackageType.PLACE)


# ---------------------------------------------------------------------------
# Cap per EVENTO
# ---------------------------------------------------------------------------
def test_event_cap_blocks_when_resulting_exceeds(caps):
    caps["max_exposure_per_event"] = 50.0
    # evento ev1: mercato target −25 (−25 in più col nuovo ordine) + altro mercato −30
    target = _mkt("1.1", "ev1", -25.0, new_order_delta=-25.0)
    other = _mkt("1.2", "ev1", -30.0)
    order = _Order("1.1")
    with pytest.raises(ControlError):
        _control(target, other)(order, OrderPackageType.PLACE)
    assert order.violations and "EVENTO" in order.violations[0]


def test_event_cap_allows_within_limit(caps):
    caps["max_exposure_per_event"] = 50.0
    target = _mkt("1.1", "ev1", -10.0, new_order_delta=-10.0)
    other = _mkt("1.2", "ev1", -29.0)
    _control(target, other)(_Order("1.1"), OrderPackageType.PLACE)  # 49 <= 50


def test_event_cap_ignores_other_events(caps):
    caps["max_exposure_per_event"] = 50.0
    target = _mkt("1.1", "ev1", -40.0)
    other_event = _mkt("1.9", "ev2", -500.0)
    _control(target, other_event)(_Order("1.1"), OrderPackageType.PLACE)


def test_event_cap_excludes_closed_markets(caps):
    caps["max_exposure_per_event"] = 50.0
    target = _mkt("1.1", "ev1", -40.0)
    closed = _mkt("1.2", "ev1", -500.0, closed=True)
    _control(target, closed)(_Order("1.1"), OrderPackageType.PLACE)


def test_positive_market_exposure_counts_as_zero_loss(caps):
    caps["max_exposure_per_event"] = 50.0
    # market_exposure positivo = profitto garantito → perdita 0
    target = _mkt("1.1", "ev1", -40.0)
    green = _mkt("1.2", "ev1", 200.0)
    _control(target, green)(_Order("1.1"), OrderPackageType.PLACE)


# ---------------------------------------------------------------------------
# Fail-open (mai un falso blocco per dati mancanti)
# ---------------------------------------------------------------------------
def test_target_market_missing_fails_open(caps):
    caps["max_exposure_per_event"] = 10.0
    c = _control(_mkt("1.2", "ev1", -1000.0))
    c(_Order("1.1"), OrderPackageType.PLACE)  # target assente → nessun blocco


def test_target_exposure_unreadable_fails_open(caps):
    caps["max_exposure_per_event"] = 10.0
    target = _mkt("1.1", "ev1", None, raises=True)
    c = _control(target)
    c(_Order("1.1"), OrderPackageType.PLACE)


def test_secondary_unreadable_is_excluded_not_blocking(caps):
    caps["max_exposure_per_event"] = 50.0
    target = _mkt("1.1", "ev1", -40.0)
    broken = _mkt("1.2", "ev1", None, raises=True)
    _control(target, broken)(_Order("1.1"), OrderPackageType.PLACE)  # 40 <= 50


def test_no_strategy_fails_open(caps):
    caps["max_exposure_per_event"] = 10.0
    order = _Order("1.1")
    order.trade = None
    _control(_mkt("1.1", "ev1", -1000.0))(order, OrderPackageType.PLACE)


# ---------------------------------------------------------------------------
# Cap per CAMPIONATO
# ---------------------------------------------------------------------------
def test_league_cap_blocks_across_events(caps, monkeypatch):
    caps["max_exposure_per_league"] = 60.0
    monkeypatch.setattr(ctl, "_league_map",
                        lambda force=False: {"ev1": "Serie A", "ev2": "Serie A"})
    target = _mkt("1.1", "ev1", -30.0, new_order_delta=-10.0)
    other_event = _mkt("1.9", "ev2", -25.0)
    order = _Order("1.1")
    with pytest.raises(ControlError):
        _control(target, other_event)(order, OrderPackageType.PLACE)  # 40+25 > 60
    assert order.violations and "CAMPIONATO" in order.violations[0]


def test_league_cap_ignores_other_leagues(caps, monkeypatch):
    caps["max_exposure_per_league"] = 60.0
    monkeypatch.setattr(ctl, "_league_map",
                        lambda force=False: {"ev1": "Serie A", "ev2": "Premier"})
    target = _mkt("1.1", "ev1", -50.0)
    other_event = _mkt("1.9", "ev2", -500.0)
    _control(target, other_event)(_Order("1.1"), OrderPackageType.PLACE)


def test_league_unknown_fails_open(caps, monkeypatch):
    caps["max_exposure_per_league"] = 10.0
    monkeypatch.setattr(ctl, "_league_map", lambda force=False: {})
    target = _mkt("1.1", "ev1", -1000.0)
    _control(target)(_Order("1.1"), OrderPackageType.PLACE)


def test_event_and_league_caps_are_independent(caps, monkeypatch):
    # evento entro cap ma campionato sfondato → blocca comunque (e viceversa)
    caps["max_exposure_per_event"] = 100.0
    caps["max_exposure_per_league"] = 50.0
    monkeypatch.setattr(ctl, "_league_map",
                        lambda force=False: {"ev1": "Serie A", "ev2": "Serie A"})
    target = _mkt("1.1", "ev1", -30.0)
    other_event = _mkt("1.9", "ev2", -30.0)
    order = _Order("1.1")
    with pytest.raises(ControlError):
        _control(target, other_event)(order, OrderPackageType.PLACE)
