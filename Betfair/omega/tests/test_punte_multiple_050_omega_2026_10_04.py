"""04/10/2026 - OMEGA: il green-up in punta parte a multiplo di 0,50 per DIFETTO e il resto
non piazzabile si dichiara UNA volta e non si ritenta (decisione dell'utente: "IL RESIDUO
RESTA RICORDATO E LO CHIUDO IO"). Giro VERO del green-up (``process_auto_greenup``),
runner paper finto, conftest di Omega (servizio senza memoria, cadenze a zero).

Gli altri casi (REST, coda, canale, terminale, Safe) stanno in
``safe_strategy/tests/test_punte_multiple_050_2026_10_04.py``. ASCII-only.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_greenup_2026_09_10 import (
    _closings,
    _db_with_model,
    _params,
    _payload,
    _run,
    _sel,
    _trade,
)
from Betfair.omega.test_omega_service import NOW
from Betfair.safe_strategy import execution as X


@pytest.fixture
def lambdas(monkeypatch):
    import Betfair.stream.db as sdb
    monkeypatch.setattr(sdb, "get_fixture_prematch_lambdas", lambda fid: (1.6, 1.1, 135))
    S._LAMBDA_CACHE.clear()


def _critici(db) -> list:
    return [p for k, p in db.activity
            if k == "place_parziale" and p.get("reason") == X.ERR_RESIDUO]


def test_green_up_con_residuo_un_avviso_stato_residual_dropped_nessun_ritento(lambdas):
    """Banca 1-3 5@55, green-up a 8,0 = 34,38 -> parte 34,00 (runner paper finto). Al
    giro dopo il resto non ha via: stato 'residual_dropped' (meccanismo che c'era), UN
    CRITICAL con la proposta, nessuna seconda chiusura nei giri seguenti."""
    db = _db_with_model()
    tr = _trade(db)
    goal = _payload(70, 1, 2, cs=[_sel(14, "1 - 3", 8.2, 8.0)])
    p = _params(greenup_settle_delay_s=0, greenup_retry_s=0)
    assert _run(db, goal, p, now=NOW) == 1
    legs = _closings(db, tr["id"])
    assert len(legs) == 1 and legs[0]["size"] == 34.0
    assert legs[0]["meta"]["punta_050"]["residuo"] == 0.38
    for s in range(1, 8):
        _run(db, goal, p, now=NOW + timedelta(seconds=25 * s))
    assert len(_closings(db, tr["id"])) == 1, "nessun ritento del residuo"
    apri = db.get_trade(tr["id"])
    assert apri["status"] == "open" and X.residuo_ricordato(apri)
    assert apri["meta"]["greenup"]["state"] == "residual_dropped"
    crit = _critici(db)
    assert len(crit) == 1 and crit[0]["critical"] is True
    assert "chiudi tu il residuo" in crit[0]["proposta"]
    assert [k for k, _ in db.activity if k == "place_rifiutato"] == []
