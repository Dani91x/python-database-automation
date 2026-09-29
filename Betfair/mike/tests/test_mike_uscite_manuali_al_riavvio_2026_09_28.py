"""CANTIERE N (28/09/2026) - Mike: a ogni AVVIO NUOVO dell'app le uscite tornano MANUALI.

Servizio vero (``service.ferma_al_nuovo_avvio``), finto vero di Mike
(``test_mike_service.FakeDB``), riga costruita dalle colonne della migrazione.
File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_avvio_app_2026_09_16 import _db
from Betfair.stream import avvio_app as AA

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _guardia_pulita():
    S._GUARDIA_AVVIO.azzera()
    yield
    S._GUARDIA_AVVIO.azzera()


def test_avvio_nuovo_uscite_automatiche_tornano_manuali(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper",
             params={"uscite_automatiche": True, "stake": 5}, stats={"boot_id": "IERI"})
    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"]["uscite_automatiche"] is False
    assert db.control["params"]["stake"] == 5          # il resto non si tocca
    assert E.uscite_automatiche(db.control["params"]) is False
    assert esito["uscite_riportate_a_manuali"] is True


def test_riavvio_dal_watchdog_non_tocca_la_scelta_dell_utente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper",
             params={"uscite_automatiche": True}, stats={"boot_id": "OGGI"})
    assert S.ferma_al_nuovo_avvio(db=db, now=NOW) is None
    assert db.control["params"]["uscite_automatiche"] is True
