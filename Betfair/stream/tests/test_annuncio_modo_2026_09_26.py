"""F-9 (26/09): il banner/alert della modalita' ordini dice il modo EFFETTIVO.

Reperto: con ``LIVE_ORDER_MODE=LIVE`` nel .env (il TETTO) e la scelta dalla UI
``betfair_live_settings.order_mode='paper'`` il runner calcio annunciava
«*** LIVE *** ORDINI REALI (SOLDI VERI)» con alert CRITICAL, mentre gli ordini
andavano in PAPER (``modo_ordini.modo_effettivo`` = il piu' restrittivo). Il
gate degli ordini non cambia: cambia solo cio' che si annuncia.
"""
from __future__ import annotations

import inspect
from typing import Any, List, Tuple

import pytest

import Betfair.stream.runner as R
from Betfair.stream import modo_ordini as MO


class _FakeDb:
    """Firma di Betfair/stream/db.py::insert_alert."""

    def __init__(self) -> None:
        self.alerts: List[Tuple[str, str, str]] = []

    def insert_alert(self, level: str, code: str, message: str,
                     event_id: Any = None, **_kw: Any) -> None:
        self.alerts.append((level, code, message))


@pytest.fixture()
def fdb(monkeypatch: Any) -> _FakeDb:
    f = _FakeDb()
    monkeypatch.setattr(R, "db", f)
    return f


def test_tetto_live_effettivo_paper_non_grida_soldi_veri(fdb: _FakeDb) -> None:
    eff = MO.modo_effettivo("LIVE", "paper")       # la regola vera
    assert eff == "PAPER"
    R._announce_order_mode("LIVE", True, eff)
    assert len(fdb.alerts) == 1
    level, code, msg = fdb.alerts[0]
    assert code == "ORDER_MODE"
    assert level == "INFO", "CRITICAL solo se l'effettivo e' LIVE"
    assert "tetto LIVE, effettivo PAPER" in msg
    assert "SOLDI VERI" not in msg
    assert "modalita' PAPER attiva" in msg


def test_effettivo_live_resta_critical(fdb: _FakeDb) -> None:
    R._announce_order_mode("LIVE", True, MO.modo_effettivo("LIVE", "live"))
    level, _c, msg = fdb.alerts[0]
    assert level == "CRITICAL"
    assert "SOLDI VERI" in msg and "tetto" not in msg


def test_scelta_non_letta_effettivo_off(fdb: _FakeDb) -> None:
    R._announce_order_mode("LIVE", True, MO.modo_effettivo("LIVE", None))
    level, _c, msg = fdb.alerts[0]
    assert level == "INFO"
    assert "tetto LIVE, effettivo OFF" in msg and "SOLDI VERI" not in msg


def test_paper_uguale_al_tetto_come_prima(fdb: _FakeDb) -> None:
    R._announce_order_mode("PAPER", True, "PAPER")
    level, _c, msg = fdb.alerts[0]
    assert level == "INFO" and "tetto" not in msg and "PAPER -- ordini SIMULATI" in msg


def test_senza_effettivo_comportamento_di_prima(fdb: _FakeDb) -> None:
    R._announce_order_mode("LIVE", True)
    assert fdb.alerts[0][0] == "CRITICAL"


def test_off_nessuna_scrittura(fdb: _FakeDb) -> None:
    R._announce_order_mode("OFF", False, "OFF")
    assert fdb.alerts == []


def test_testo_puro() -> None:
    assert R._testo_modo_ordini("LIVE", "PAPER") == (
        "PAPER",
        "tetto LIVE, effettivo PAPER -- PAPER -- ordini SIMULATI (soldi finti, dati live)",
        "INFO",
    )
    assert R._testo_modo_ordini("live", "live")[2] == "CRITICAL"


def test_setup_and_run_passa_il_modo_effettivo() -> None:
    """Il chiamante vero annuncia l'effettivo (tetto x scelta UI letta)."""
    src = inspect.getsource(R.setup_and_run)
    assert "_MO.modo_effettivo(modo_avvio, _MO.valore_db())" in src
