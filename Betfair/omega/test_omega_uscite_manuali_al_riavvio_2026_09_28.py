"""CANTIERE N (28/09/2026) - Omega: a ogni AVVIO NUOVO dell'app le uscite tornano
"avvisa e proponi" (manuali).

Servizio vero (``omega_service.ferma_al_nuovo_avvio``), finto vero di Omega,
riga costruita dalle colonne della migrazione. File ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_avvio_app_2026_09_16 import PARAMS_VERI, _db
from Betfair.omega.test_omega_service import NOW
from Betfair.stream import avvio_app as AA


@pytest.fixture(autouse=True)
def _guardia_pulita():
    S._GUARDIA_AVVIO.azzera()
    yield
    S._GUARDIA_AVVIO.azzera()


def test_avvio_nuovo_uscite_automatiche_tornano_avvisa_e_proponi(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "IERI"},
             params={**PARAMS_VERI, "uscite_protezione": "automatico"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"]["uscite_protezione"] == "avvisa_e_proponi"
    assert db.control["params"]["daily_loss_stop"] == PARAMS_VERI["daily_loss_stop"]


def test_riavvio_dal_watchdog_non_tocca_la_scelta_dell_utente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"},
             params={**PARAMS_VERI, "uscite_protezione": "automatico"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"]["uscite_protezione"] == "automatico"
