"""Test dei trading control NATIVI flumine (Betfair/stream/trading/controls.py).

Prova, con soli mock (nessuna rete, nessun flumine reale):
  * LiveExposureControl: over cap => rifiutato (ControlError), under cap => passa,
    NULL/disattivato => passa, fail-open su blotter/esposizione KO;
  * LiveRateControl: scatta al cap e si resetta dopo 60s, disattivato => passa;
  * get_live_settings: fail-open su errore DB, lettura + cache TTL.

I control sono esercitati via ``control(order, package_type)`` (BaseControl.__call__ -> _validate);
il rifiuto è segnalato da ``flumine.exceptions.ControlError`` dopo ``order.violation(...)``.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from flumine.exceptions import ControlError
from flumine.order.orderpackage import OrderPackageType

import Betfair.stream.trading.controls as ctl


# ---------------------------------------------------------------------------
# Fixture: stato pulito (cache settings) fra un test e l'altro.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_settings_cache():
    ctl._SETTINGS_CACHE["data"] = {}
    ctl._SETTINGS_CACHE["ts"] = 0.0
    ctl.reset_rate_window()  # §7.2: finestra rate CONDIVISA a livello modulo
    yield
    ctl._SETTINGS_CACHE["data"] = {}
    ctl._SETTINGS_CACHE["ts"] = 0.0
    ctl.reset_rate_window()


def _set_settings(monkeypatch, **kw):
    """Sostituisce get_live_settings con uno snapshot fisso (bypassa DB e TTL)."""
    monkeypatch.setattr(ctl, "get_live_settings", lambda *a, **k: dict(kw))


# ---------------------------------------------------------------------------
# Mock flumine order / market / blotter
# ---------------------------------------------------------------------------
class _Blotter:
    def __init__(self, exposure, raises=False):
        self._e = exposure
        self._raises = raises
        self.calls = []

    def selection_exposure(self, strategy, lookup):
        self.calls.append((strategy, lookup))
        if self._raises:
            raise RuntimeError("blotter boom")
        return self._e


class _Order:
    """Ordine flumine minimale: side/lookup/order_type/trade + violation()/info."""

    def __init__(self, side, market_id, selection_id, handicap, size, price,
                 liability=None, strategy=object()):
        self.side = side
        self.market_id = market_id
        self.selection_id = selection_id
        self.handicap = handicap
        self.lookup = (market_id, selection_id, handicap)
        self.order_type = SimpleNamespace(
            size=size, price=price, liability=liability, bet_target_size=None
        )
        self.trade = SimpleNamespace(strategy=strategy)
        self.violation_msg = None

    # BaseControl._on_error chiama order.violation(msg) e legge order.info nel log.
    def violation(self, msg):
        self.violation_msg = msg

    @property
    def info(self):
        return {"market_id": self.market_id, "selection_id": self.selection_id}


def _flumine(market_id, market):
    return SimpleNamespace(markets=SimpleNamespace(markets={market_id: market}))


def _market_with(exposure, raises=False):
    return SimpleNamespace(blotter=_Blotter(exposure, raises=raises))


# ===========================================================================
# LiveExposureControl
# ===========================================================================
def test_exposure_over_cap_rejected(monkeypatch):
    _set_settings(monkeypatch, max_exposure_per_selection=50.0)
    market = _market_with(40.0)                       # esposizione corrente 40
    order = _Order("BACK", "1.1", 10, 0.0, size=20.0, price=3.0)   # +20 => 60 > 50
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    with pytest.raises(ControlError):
        control(order, OrderPackageType.PLACE)        # __call__ -> _validate
    assert order.violation_msg is not None            # ordine marcato violazione


def test_exposure_under_cap_allowed(monkeypatch):
    _set_settings(monkeypatch, max_exposure_per_selection=50.0)
    market = _market_with(20.0)
    order = _Order("BACK", "1.1", 10, 0.0, size=20.0, price=3.0)   # 20+20=40 <= 50
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    control(order, OrderPackageType.PLACE)            # non solleva
    assert order.violation_msg is None


def test_exposure_lay_liability_over_cap_rejected(monkeypatch):
    # LAY: contributo = size*(price-1) = 10*(6-1) = 50; corrente 5 => 55 > 50
    _set_settings(monkeypatch, max_exposure_per_selection=50.0)
    market = _market_with(5.0)
    order = _Order("LAY", "1.1", 10, 0.0, size=10.0, price=6.0)
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    with pytest.raises(ControlError):
        control(order, OrderPackageType.PLACE)


def test_exposure_disabled_null_allows(monkeypatch):
    _set_settings(monkeypatch)                        # nessun max_exposure_per_selection => NULL
    market = _market_with(1000.0)
    order = _Order("BACK", "1.1", 10, 0.0, size=999.0, price=2.0)
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    control(order, OrderPackageType.PLACE)            # disattivato => passa
    assert order.violation_msg is None


def test_exposure_non_place_ignored(monkeypatch):
    _set_settings(monkeypatch, max_exposure_per_selection=1.0)
    market = _market_with(1000.0)
    order = _Order("BACK", "1.1", 10, 0.0, size=999.0, price=2.0)
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    control(order, OrderPackageType.CANCEL)           # non è un PLACE => ignorato
    control(order, OrderPackageType.REPLACE)
    assert order.violation_msg is None


def test_exposure_fail_open_on_blotter_error(monkeypatch):
    _set_settings(monkeypatch, max_exposure_per_selection=1.0)
    market = _market_with(0.0, raises=True)           # selection_exposure solleva
    order = _Order("BACK", "1.1", 10, 0.0, size=999.0, price=2.0)
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    control(order, OrderPackageType.PLACE)            # fail-open: non blocca
    assert order.violation_msg is None


def test_exposure_fail_open_market_not_subscribed(monkeypatch):
    _set_settings(monkeypatch, max_exposure_per_selection=1.0)
    order = _Order("BACK", "9.9", 10, 0.0, size=999.0, price=2.0)
    control = ctl.LiveExposureControl(_flumine("1.1", _market_with(0.0)))  # market diverso
    control(order, OrderPackageType.PLACE)            # market non trovato => fail-open
    assert order.violation_msg is None


def test_exposure_boundary_exactly_at_cap_allowed(monkeypatch):
    # risultante == cap => consentito (stretto: solo > cap rifiuta)
    _set_settings(monkeypatch, max_exposure_per_selection=50.0)
    market = _market_with(30.0)
    order = _Order("BACK", "1.1", 10, 0.0, size=20.0, price=2.0)   # 30+20=50 == 50
    control = ctl.LiveExposureControl(_flumine("1.1", market))
    control(order, OrderPackageType.PLACE)
    assert order.violation_msg is None


# ===========================================================================
# LiveRateControl
# ===========================================================================
def test_rate_disabled_when_unset(monkeypatch):
    _set_settings(monkeypatch)                        # nessun max_orders_per_min
    control = ctl.LiveRateControl(SimpleNamespace())
    order = _Order("BACK", "1.1", 10, 0.0, size=1.0, price=2.0)
    for _ in range(100):
        control(order, OrderPackageType.PLACE)        # nessun limite => mai rifiutato
    assert order.violation_msg is None


def test_rate_trips_at_cap_and_resets_after_60s(monkeypatch):
    _set_settings(monkeypatch, max_orders_per_min=2)
    clock = [1000.0]
    monkeypatch.setattr(ctl, "_now_epoch", lambda: clock[0])
    control = ctl.LiveRateControl(SimpleNamespace())
    order = _Order("BACK", "1.1", 10, 0.0, size=1.0, price=2.0)

    control(order, OrderPackageType.PLACE)            # 1° place: ok
    control(order, OrderPackageType.PLACE)            # 2° place: ok (raggiunge il cap)
    with pytest.raises(ControlError):
        control(order, OrderPackageType.PLACE)        # 3° nel minuto => rifiutato

    clock[0] += 61.0                                  # oltre la finestra di 60s
    order.violation_msg = None
    control(order, OrderPackageType.PLACE)            # finestra svuotata => di nuovo ok
    assert order.violation_msg is None


def test_rate_rejected_place_not_recorded(monkeypatch):
    # Un place RIFIUTATO non consuma slot: appena si supera la finestra riparte pulito.
    _set_settings(monkeypatch, max_orders_per_min=1)
    clock = [0.0]
    monkeypatch.setattr(ctl, "_now_epoch", lambda: clock[0])
    control = ctl.LiveRateControl(SimpleNamespace())
    order = _Order("BACK", "1.1", 10, 0.0, size=1.0, price=2.0)

    control(order, OrderPackageType.PLACE)            # ok (slot pieno)
    for _ in range(5):
        clock[0] += 1.0                               # ancora dentro i 60s
        with pytest.raises(ControlError):
            control(order, OrderPackageType.PLACE)    # tutti rifiutati, nessuno registrato
    # la finestra contiene ancora SOLO il primo place (t=0); a t=61 si libera.
    clock[0] = 61.0
    order.violation_msg = None
    control(order, OrderPackageType.PLACE)
    assert order.violation_msg is None


def test_rate_non_place_ignored(monkeypatch):
    _set_settings(monkeypatch, max_orders_per_min=1)
    control = ctl.LiveRateControl(SimpleNamespace())
    order = _Order("BACK", "1.1", 10, 0.0, size=1.0, price=2.0)
    for _ in range(10):
        control(order, OrderPackageType.CANCEL)       # non-place non conta mai
    assert order.violation_msg is None


def test_rate_window_shared_between_control_and_worker_precheck(monkeypatch):
    # §7.2: UNA finestra sola — i place contati dal control sono visti dal pre-check
    # del worker (rate_violation) e viceversa: mai due conteggi che divergono.
    _set_settings(monkeypatch, max_orders_per_min=2)
    monkeypatch.setattr(ctl, "_now_epoch", lambda: 1000.0)
    control = ctl.LiveRateControl(SimpleNamespace())
    order = _Order("BACK", "1.1", 10, 0.0, size=1.0, price=2.0)

    control(order, OrderPackageType.PLACE)            # 1 place registrato dal control
    assert ctl.rate_violation(2, extra=1) is None      # 1+1 = 2 <= 2 → capacità ok
    assert ctl.rate_violation(2, extra=2) is not None  # 1+2 = 3 > 2 → violazione

    ctl.record_place()                                 # 2° slot consumato
    with pytest.raises(ControlError):
        control(order, OrderPackageType.PLACE)         # il control vede la finestra piena


def test_rate_violation_disabled_when_cap_none():
    assert ctl.rate_violation(None) is None
    assert ctl.rate_violation(0) is None


# ===========================================================================
# get_live_settings — fail-open su errore DB, lettura + cache TTL
# ===========================================================================
def test_settings_fail_open_on_db_error(monkeypatch):
    import db_client

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_client, "get_supabase_client", _boom)
    ctl._SETTINGS_CACHE["ts"] = 0.0                   # forza il tentativo di lettura
    out = ctl.get_live_settings(force=True)           # non deve sollevare
    assert out == {}                                  # fail-open: snapshot vuoto (limiti off)


def test_settings_read_and_cache(monkeypatch):
    import db_client

    calls = {"n": 0}

    def _fake_client():
        calls["n"] += 1

        class _Res:
            data = {"max_exposure_per_selection": 25.0, "max_orders_per_min": 3}

        return SimpleNamespace(rpc=lambda name, params: SimpleNamespace(execute=lambda: _Res()))

    monkeypatch.setattr(db_client, "get_supabase_client", _fake_client)
    # tempo fisso => entro il TTL la seconda chiamata NON ricontatta il DB.
    monkeypatch.setattr(ctl, "_now_epoch", lambda: 500.0)
    ctl._SETTINGS_CACHE["ts"] = 0.0

    s1 = ctl.get_live_settings(force=True)
    assert s1["max_exposure_per_selection"] == 25.0
    assert ctl._max_orders_per_min() == 3             # legge dalla cache, stesso istante
    assert ctl._max_exposure_per_selection() == 25.0
    assert calls["n"] == 1                            # una sola lettura DB (cache TTL)
