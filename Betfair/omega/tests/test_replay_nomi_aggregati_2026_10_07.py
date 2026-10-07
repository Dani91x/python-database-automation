# -*- coding: utf-8 -*-
"""I nomi degli aggregati nel replay di Omega hanno la DIREZIONE giusta (07/10).

9063254 / 9063255 / 9063256 = Home / Away / Draw: `sortPriority` 17/18/19 nel
`marketDefinition` delle registrazioni, nell'ordine del catalogo Betfair, e i
prezzi pre-match della 35797769 (9063255 a 80, 9063256 a 400)."""
from __future__ import annotations

from Betfair.omega import omega_v3 as V3
from Betfair.omega.tools import replay_registrazioni as R


def test_direzioni_degli_aggregati_come_il_catalogo_betfair():
    assert V3.direzione_aggregato(R.nome_runner_punteggio(9063254)) == "home"
    assert V3.direzione_aggregato(R.nome_runner_punteggio(9063255)) == "away"
    assert V3.direzione_aggregato(R.nome_runner_punteggio(9063256)) == "draw"


def test_stessa_mappa_della_safe_strategy():
    from Betfair.safe_strategy.tools import validate_opportunity as V
    for sid in (9063254, 9063255, 9063256):
        safe = V.selection_name("CORRECT_SCORE", sid, 0, "A", "B")
        assert V3.direzione_aggregato(safe) == V3.direzione_aggregato(
            R.nome_runner_punteggio(sid)), sid
