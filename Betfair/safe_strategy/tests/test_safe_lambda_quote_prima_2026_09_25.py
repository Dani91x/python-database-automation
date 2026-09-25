# -*- coding: utf-8 -*-
"""O1 lato Safe (25/09 sera): Safe usa la catena dei lambda di Omega
(`bot_service.resolve_event_lambdas` -> `omega_service._prematch_lambdas`) e le
passa i params RISOLTI di Omega, cosi' segue lo stesso ordine di Omega:
`lambda_quote_prima` ACCESO di default (ordine dell'utente: "per TUTTI i bot i
valori statistici e gli aiuti di default accesi") = quote 1X2 pre-KO prima
della fixture.

Si usa la catena VERA di Omega; i finti sono quelli di
`Betfair/omega/tests/test_o1_quote_prima_2026_09_25.py` (riga `omega_events`
con `fixture_id`, client PostgREST con la query vera di
`get_fixture_prematch_lambdas`, `pre_ko` costruito dal produttore vero
`safe_strategy.scanner.freeze_pre_ko`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from Betfair.omega import omega_model as M
from Betfair.omega import omega_service as OS
from Betfair.omega.tests.test_o1_quote_prima_2026_09_25 import (LEGA, _DB, _evento,
                                                               _pre_ko, client)  # noqa: F401
from Betfair.safe_strategy import bot_service as S

ADESSO = datetime(2026, 9, 25, 18, 0, tzinfo=timezone.utc)


class _OppNessuno:
    """Il modulo opportunita': qui non deve servire (risponde la catena di Omega)."""

    @staticmethod
    def resolve_lambdas(payload, fixture=None):
        raise AssertionError("la catena di Omega doveva rispondere")


@pytest.fixture(autouse=True)
def _cache_pulita():
    OS._LAMBDA_CACHE.clear()
    yield
    OS._LAMBDA_CACHE.clear()


def _risolvi(eid: str, payload: dict) -> dict:
    db = _DB({eid: _evento(eid)})
    return S.resolve_event_lambdas(db=db, event_id=eid, payload=payload,
                                   opp_mod=_OppNessuno, now=ADESSO, state={})


def test_safe_default_quote_pre_ko_prima_della_fixture(client):  # noqa: F811
    pk = _pre_ko()
    atteso = M.lambdas_from_pre_ko(pk)
    out = _risolvi("s1", {"pre_ko": pk})
    assert out["source"] == "pre_ko_odds"
    assert out["lambdas"] == (atteso[0], atteso[1]) and out["league_id"] == LEGA
    assert client.letture == 0                 # la fixture non si legge


def test_safe_passa_i_params_risolti_di_omega(monkeypatch, client):  # noqa: F811
    visti: list = []
    vero = OS._prematch_lambdas

    def _spia(db, event_id, payload, **kw):
        visti.append(kw.get("params"))
        return vero(db, event_id, payload, **kw)

    monkeypatch.setattr(OS, "_prematch_lambdas", _spia)
    _risolvi("s2", {"pre_ko": _pre_ko()})
    assert len(visti) == 1 and isinstance(visti[0], dict)
    assert visti[0]["lambda_quote_prima"] is True


def test_safe_con_lambda_quote_prima_spento_fixture_prima_come_oggi(monkeypatch, client):  # noqa: F811
    """Con i params di Omega a `lambda_quote_prima=False` (esplicito) Safe torna
    alla catena di prima: la fixture vince sulle quote."""
    monkeypatch.setattr(S, "_omega_params_catena_lambda",
                        lambda: {"lambda_quote_prima": False})
    out = _risolvi("s3", {"pre_ko": _pre_ko()})
    assert out["source"] == "fixture"
    assert out["lambdas"] == (1.9, 0.7) and out["league_id"] == LEGA


def test_safe_senza_quote_fixture(client):  # noqa: F811
    out = _risolvi("s4", {})
    assert out["source"] == "fixture" and out["lambdas"] == (1.9, 0.7)
