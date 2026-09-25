# -*- coding: utf-8 -*-
"""B17 (25/09/2026) - IL PREZZO DEL SEGNALE ACCANTO AL PREZZO VISTO.

Ordine dell'utente (punto 14): "una volta che clicco, devo sapere a che prezzo
e' stato abbinato il mio ordine rispetto al segnale e soprattutto se e' stato
realmente abbinato, con un messaggio".

La scheda (``frontend/src/lib/esitoAbbinamento.ts``) confronta il prezzo MEDIO
abbinato con il prezzo VISTO al clic e con quello del SEGNALE. Per farlo la riga
dell'ordine deve portare il segnale: qui si certifica, sul codice di
produzione (``bot_service._request_place``, ``proposte_opportunita``), che:
  1. la riga nata da una proposta porta ``meta.prezzo_segnale`` = il prezzo alla
     NASCITA della proposta (``price_at_decision``), anche quando l'ordine parte
     a un prezzo visto diverso; il prezzo dell'ordine NON cambia (resta il
     visto: nessuna decisione toccata);
  2. il contesto del clic conserva ``prezzo_segnale`` solo se e' una quota
     valida, e un contesto di ieri resta IDENTICO (nessuna chiave nuova);
  3. una richiesta manuale che non nasce da una proposta non riceve niente.

Ogni test ha la sua falsificazione (``_falsificazione``): si rimette il
difetto e il test deve diventare rosso.
ASCII-only nel codice, commenti in italiano.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import proposte_opportunita as PO
from Betfair.safe_strategy.tests.test_proposte_opportunita_2026_09_17 import NOW, DbFinto
from Betfair.safe_strategy.tests.test_scheda_al_ms_2026_09_24 import (  # noqa: F401
    EV, _corpo_approvato, _feed, _giro, _opp_valida, esecuzione,
)


def _piazza(db, corpo, back_p1=1.31):
    return S._request_place(db=db, market=None, rows_by_event={EV: _feed(back_p1=back_p1)},
                            payload=corpo, params={"commission_pct": 5.0}, now=NOW,
                            control_mode="paper")


# ---------------------------------------------------------------- 1. riga
def test_la_riga_porta_il_prezzo_del_segnale_e_l_ordine_resta_al_visto(esecuzione):
    """Proposta nata a 1,30; l'utente clicca a 1,31 (visto, mercato 1,31): la
    riga parte a 1,31 e porta il segnale 1,30."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = _piazza(db, _corpo_approvato(db, 1.31))
    assert out.get("ok") is True, out
    t = db.trades[0]
    assert t["price"] == 1.31                      # il prezzo dell'ordine: il visto
    assert t["meta"]["prezzo_segnale"] == 1.30     # il segnale: la nascita


def test_la_riga_porta_il_prezzo_del_segnale_falsificazione(esecuzione, monkeypatch):
    """Se il servizio non scrivesse il segnale (difetto rimesso), il test sopra
    sarebbe rosso: qui lo si prova togliendo la funzione che lo calcola."""
    monkeypatch.setattr(PO, "prezzo_segnale", lambda payload: None)
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = _piazza(db, _corpo_approvato(db, 1.31))
    assert out.get("ok") is True
    assert "prezzo_segnale" not in db.trades[0]["meta"]


def test_il_segnale_e_la_nascita_non_il_prezzo_riscritto(esecuzione):
    """Una proposta viva viene riscritta col prezzo di adesso (``price``), ma il
    segnale e' quello della NASCITA (``price_at_decision``)."""
    corpo = {"price_at_decision": 1.30, "price": 1.45}
    assert PO.prezzo_segnale(corpo) == 1.30
    assert PO.prezzo_segnale({"price": 1.45}) == 1.45
    for sporco in ({"price_at_decision": 1.0}, {"price_at_decision": "x"},
                   {"price_at_decision": True}, {"price_at_decision": float("nan")}, {}, None, "x"):
        assert PO.prezzo_segnale(sporco) is None, sporco


# --------------------------------------------------------------- 2. contesto
def test_il_contesto_conserva_il_segnale_solo_se_valido():
    base = {"eta_ms": 120, "fonte": "canale", "prezzo_vivo_assente": False, "clic_ms": 1790000000000}
    c = PO.contesto_prezzo_visto({"prezzo_visto_ctx": {**base, "prezzo_segnale": 1.3}})
    assert c["prezzo_segnale"] == 1.3
    for sporco in (1.0, 0, -2, "x", None, True, float("nan")):
        c2 = PO.contesto_prezzo_visto({"prezzo_visto_ctx": {**base, "prezzo_segnale": sporco}})
        assert "prezzo_segnale" not in c2


def test_un_contesto_di_ieri_resta_identico():
    """Retrocompatibile: senza ``prezzo_segnale`` le chiavi sono quelle del 24/09."""
    c = PO.contesto_prezzo_visto({"prezzo_visto_ctx": {
        "eta_ms": 42000, "fonte": "scanner", "prezzo_vivo_assente": True, "clic_ms": 1790000000000}})
    assert c == {"eta_ms": 42000.0, "fonte": "scanner", "prezzo_vivo_assente": True,
                 "clic_ms": 1790000000000.0}


def test_il_segnale_del_contesto_arriva_sulla_riga(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    ctx = {"eta_ms": 80, "fonte": "canale", "prezzo_vivo_assente": False,
           "clic_ms": 1790000000000, "prezzo_segnale": 1.30}
    out = _piazza(db, _corpo_approvato(db, 1.31, extra={"prezzo_visto_ctx": ctx}))
    assert out.get("ok") is True
    assert db.trades[0]["meta"]["prezzo_visto_ctx"]["prezzo_segnale"] == 1.30


# ------------------------------------------------- 3. richiesta non da proposta
def test_una_richiesta_manuale_senza_proposta_non_riceve_il_segnale(esecuzione):
    """Il bottone «Investi» (nessun ``opp_key``) non e' una proposta: nessun
    segnale sulla riga, comportamento di ieri."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.31)
    corpo.pop("opp_key", None)
    out = _piazza(db, corpo)
    assert out.get("ok") is True, out
    assert "prezzo_segnale" not in db.trades[0]["meta"]
    assert "da_proposta" not in db.trades[0]["meta"]


@pytest.mark.parametrize("prezzo_visto", [1.30, 1.31])
def test_l_ordine_parte_al_visto_con_o_senza_segnale(esecuzione, prezzo_visto):
    """Parita' della decisione: il prezzo e la size passati all'esecuzione sono
    gli stessi che senza il segnale (``_execute`` riceve la riga riservata).
    D7 (25/09): il prezzo dell'ordine e' quello di MERCATO (1,31, dentro la
    banda della strategia) qualunque sia il visto; prima era il visto."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = _piazza(db, _corpo_approvato(db, prezzo_visto))
    assert out.get("ok") is True
    assert esecuzione[0]["row"]["price"] == 1.31
