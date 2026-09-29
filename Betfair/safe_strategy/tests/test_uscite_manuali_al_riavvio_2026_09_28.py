"""CANTIERE N (28/09/2026) - Safe: a ogni AVVIO NUOVO dell'app le uscite di OGNI
strategia tornano MANUALI (mappa ``uscite_automatiche`` + cancelletto del tennis).

Servizio vero (``bot_service.ferma_al_nuovo_avvio``), finto vero di Safe, riga
costruita dalle colonne della migrazione. File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_avvio_app_2026_09_16 import PARAMS_VERI, _db
from Betfair.safe_strategy.tests.test_bot_service import NOW, _reset_module_state
from Betfair.stream import avvio_app as AA


@pytest.fixture(autouse=True)
def _pulizia():
    _reset_module_state()
    S._GUARDIA_AVVIO.azzera()
    yield
    _reset_module_state()
    S._GUARDIA_AVVIO.azzera()


def _auto():
    return {**PARAMS_VERI,
            "uscite_automatiche": {"base": True, "esatto": True, "punta": True,
                                   "tennis": True, "model": True},
            "tennis_exit_approval": False}


def test_avvio_nuovo_tutte_le_strategie_tornano_manuali(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="live", params=_auto(), stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    p = db.control["params"]
    eff = S.resolve_params(p)
    for s in S.STRATEGIE_CON_USCITE:
        assert S.uscite_automatiche_di(eff, s) is False, s
    assert p["tennis_exit_approval"] is True
    # e il reset delle modalita' di prima c'e' ancora
    assert set(p["strategy_modes"].values()) == {"paper"}
    assert p["daily_loss_stop"] == PARAMS_VERI["daily_loss_stop"]


def test_riavvio_dal_watchdog_non_tocca_la_scelta_dell_utente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="live", params=_auto(), stats={"boot_id": "OGGI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"]["uscite_automatiche"]["base"] is True
