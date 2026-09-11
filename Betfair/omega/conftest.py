"""Fixture comuni ai test di Omega: lo stato di PROCESSO del servizio (budget dei
tentativi per gamba, dedup dei log, cicli "ciechi" del green-up, cache del fit di
mercato) si azzera a ogni test — i test usano gli stessi event_id fra file diversi."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_omega_process_state():
    from Betfair.omega import omega_service as S
    for name in ("_LEG_RETRY", "_SKIP_SEEN", "_BLIND_CYCLES", "_MARKET_FIT_CACHE"):
        d = getattr(S, name, None)
        if isinstance(d, dict):
            d.clear()
    yield
