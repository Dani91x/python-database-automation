"""23/09 - B-3 (revisore B): CP1 non vedeva un residuo o un prezzo medio NON scritti.

Difetto: ``Sorveglianza.verifica`` (ramo CP1) confrontava ``size_remaining`` e
``avg_price_matched`` solo se la riga li scriveva, e mai il CHIESTO: una riga che
scrive l'abbinato ma NON il residuo (o NON il medio) mentre il residuo e' vivo a
mercato passava verde. E' la regola permanente "chiesto/abbinato/residuo/medio
sempre" che CP1 dichiara di controllare.

Correzione: "residuo NON scritto" con residuo vivo, "prezzo medio NON scritto"
con abbinato, "chiesto NON scritto" / chiesto diverso da quello di flumine
(``order_type.size``, o abbinato + residuo dopo un place-and-trim).

Le sonde del revisore (``test_cp1_campo_mancante_non_scatta``, verdi = difetto)
sono qui INVERTITE. Finti: l'ordine ha gli attributi di ``flumine`` letti dal
modulo (``size_matched``, ``size_remaining``, ``average_price_matched``,
``status.value``, ``order_type.size``); la credenza ha le chiavi di
``credenze_da_righe``.
"""
from __future__ import annotations

import types

import pytest

from Betfair.stream.backtest import chiusura_parziale as CPZ


class _St:
    value = "Executable"


class _Ordine:
    """Ordine flumine appoggiato: chiesto 10, abbinato 4 a 2.0, residuo 6 vivo."""

    def __init__(self, size=10.0, matched=4.0, remaining=6.0, avg=2.0):
        self.id = "o1"
        self.bet_id = "B1"
        self.side = "LAY"
        self.size_matched = matched
        self.size_remaining = remaining
        self.average_price_matched = avg
        self.status = _St()
        self.notes = {"bot_ref": "safe-t2"}
        self.market_id = "1.1"
        self.selection_id = 7
        self.order_type = types.SimpleNamespace(size=size, price=2.0)


def _sorv(o):
    g = CPZ.GuastoChiusuraParziale()
    g.colpiti = [{"ordine": o, "chiave": ("1.1", 7), "fok": False}]
    g.mercato_chiuso = lambda mid: False
    g.tutti_gli_ordini = lambda: [o]
    return CPZ.Sorveglianza(g)


def _chiusura(**sovrascrivi):
    """La chiusura nella forma di ``credenze_da_righe`` (chiavi vere)."""
    c = {"bet_id": "B1", "id_riga": 2, "status": "open", "size": 10.0, "price": 2.0,
         "size_requested": 10.0, "size_matched": 4.0, "size_remaining": 6.0,
         "avg_price_matched": 2.0}
    c.update(sovrascrivi)
    return c


def _cp1(o, chiusura, giri=5):
    s = _sorv(o)
    cred = [{"id": "riga#1", "chiave": ("1.1", 7), "chiusure": [chiusura]}]
    out = []
    for _ in range(giri):
        out += s.verifica(cred, {})
    return [v for v in out if v[0] == "CP1"]


def test_credenza_onesta_nessuna_cp1():
    assert _cp1(_Ordine(), _chiusura()) == []


@pytest.mark.parametrize("campo,testo", [
    ("size_remaining", "residuo NON scritto"),
    ("avg_price_matched", "prezzo medio NON scritto"),
])
def test_campo_non_scritto_scatta_cp1(campo, testo):
    viol = _cp1(_Ordine(), _chiusura(**{campo: None}))
    assert len(viol) == 1, viol                    # una volta sola
    assert testo in viol[0][2]


def test_residuo_non_scritto_senza_residuo_a_mercato_non_scatta():
    # chiusura abbinata per intero: residuo 0, non scriverlo non racconta il falso
    o = _Ordine(size=10.0, matched=10.0, remaining=0.0)
    assert _cp1(o, _chiusura(size_matched=10.0, size_remaining=None)) == []


def test_medio_non_scritto_senza_abbinato_non_scatta():
    o = _Ordine(matched=0.0, remaining=10.0, avg=0.0)
    assert _cp1(o, _chiusura(size_matched=0.0, size_remaining=10.0,
                             avg_price_matched=None)) == []


def test_chiesto_diverso_da_flumine_scatta_cp1():
    viol = _cp1(_Ordine(), _chiusura(size_requested=7.0, size=7.0))
    assert len(viol) == 1 and "chiesto creduto 7.00 contro 10.00" in viol[0][2]


def test_chiesto_non_scritto_scatta_cp1():
    viol = _cp1(_Ordine(), _chiusura(size_requested=None, size=None))
    assert len(viol) == 1 and "chiesto NON scritto" in viol[0][2]


def test_chiesto_da_size_quando_manca_size_requested():
    # specchio tennis: nessuna ``size_requested``, il chiesto e' ``size``
    assert _cp1(_Ordine(), _chiusura(size_requested=None, size=10.0)) == []


def test_chiesto_dopo_place_and_trim_accettato():
    # piazzato al minimo (2.00) e tagliato a 0.50: flumine tiene 2.00 in
    # order_type.size, la riga il chiesto vero 0.50 = abbinato + residuo
    o = _Ordine(size=2.0, matched=0.2, remaining=0.3, avg=2.0)
    assert _cp1(o, _chiusura(size_requested=0.5, size=0.5, size_matched=0.2,
                             size_remaining=0.3)) == []


def test_controprova_residuo_sbagliato_scatta():
    viol = _cp1(_Ordine(), _chiusura(size_remaining=0.0))
    assert viol and "residuo creduto 0.00 contro 6.00" in viol[0][2]


def test_tolleranza_dei_giri_resta():
    # due giri non bastano (GIRI_DI_TOLLERANZA = 3): il bot non puo' saperlo subito
    assert _cp1(_Ordine(), _chiusura(size_remaining=None),
                giri=CPZ.GIRI_DI_TOLLERANZA - 1) == []


def test_credenze_da_righe_portano_size_requested():
    righe = [
        {"id": 1, "market_id": "1.1", "selection_id": 7, "status": "open", "size": 10.0,
         "price": 2.0, "bet_id": "A1", "closes_trade_id": None, "meta": {}},
        {"id": 2, "market_id": "1.1", "selection_id": 7, "status": "open", "size": 10.0,
         "price": 2.0, "bet_id": "B1", "closes_trade_id": 1, "size_requested": 10.0,
         "size_matched": 4.0, "size_remaining": 6.0, "avg_price_matched": 2.0,
         "meta": {"cashout": True, "closes_trade_id": 1}},
    ]
    cred = CPZ.credenze_da_righe(righe)
    assert cred[0]["chiusure"][0]["size_requested"] == 10.0
