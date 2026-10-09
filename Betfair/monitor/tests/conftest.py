"""Fixture dei test del modulo "Salute" (T0A, 09/10/2026)."""
from __future__ import annotations

import pytest

from Betfair.monitor import sonde as M


@pytest.fixture
def monitor_acceso(monkeypatch, tmp_path):
    """Il monitor ACCESO come in un servizio vero (interruttore a 1), senza
    thread di scrittura: i test chiamano ``Scrittore.giro`` a mano. Il banco e'
    caricato nel processo di pytest (altri test): qui il controllo "nel banco"
    e' sostituito, il test che lo prova davvero e' a parte."""
    monkeypatch.setenv(M.ENV, "1")
    monkeypatch.setattr(M, "nel_banco", lambda: False)
    assert M.avvia("prova-test", sport="calcio", scrittore=False, _consenti_in_test=True)
    yield M
    M.ferma()
    M.REGISTRO.azzera_tutto()
