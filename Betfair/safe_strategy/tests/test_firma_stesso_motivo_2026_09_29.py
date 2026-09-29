# -*- coding: utf-8 -*-
"""CANTIERE N (29/09/2026, verifica del coordinatore) - SAFE: una firma vale per
l'uscita che l'utente ha VISTO.

Il ricontrollo del cantiere D1 (``bot_service._proposta_non_piu_valida``)
confrontava solo il TIPO d'uscita (``exit_kind``): una firma su un 'profit'
"favorita_segna_ancora" passava anche se adesso la regola che scatta e' un
'profit' diverso ("controllo_passato_alla_sfavorita"). Ora conta anche il
MOTIVO (senza i numeri: il minuto dentro "minuto_81_senza_altri_gol" non fa un
motivo diverso).

Perche' la firma non puo' sopravvivere alla proposta in Safe: la proposta E' la
richiesta (``safe_strategy_requests``, 'proposed'); decaduta diventa 'rejected'
e la RPC ``safe_request_approve`` accetta solo 'proposed'.

``XE.decide`` e' sostituita da una funzione che rende l'``ExitDecision`` VERA
(stessa classe). ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import NOW


def _trade():
    return {"id": 7, "strategy": "base", "sport": "calcio", "side": "lay", "meta": {}}


def _riga():
    return {"payload": {"score_home": 1, "score_away": 0, "minute": 82}}


@pytest.mark.parametrize("firmato,adesso,esce", [
    (("profit", "favorita_segna_ancora"), ("profit", "favorita_segna_ancora"), True),
    (("profit", "favorita_segna_ancora"), ("profit", "controllo_passato_alla_sfavorita"), False),
    (("time", "minuto_81_senza_altri_gol"), ("time", "minuto_82_senza_altri_gol"), True),
    (("loss", "sfavorita_pareggia"), ("time", "minuto_82_senza_altri_gol"), False),
])
def test_la_firma_vale_per_il_motivo_visto(monkeypatch, firmato, adesso, esce):
    monkeypatch.setattr(S.XE, "track", lambda tr, payload, now_ts: {})
    monkeypatch.setattr(S.XE, "decide",
                        lambda tr, payload, meta, now_ts, xp: S.XE.ExitDecision(adesso[0], adesso[1], 0.0))
    payload = {"exit_kind": firmato[0], "exit_reason": firmato[1], "trade_id": 7}
    motivo = S._proposta_non_piu_valida(_trade(), payload, _riga(), S.resolve_params(None), NOW)
    assert (motivo is None) is esce, motivo
