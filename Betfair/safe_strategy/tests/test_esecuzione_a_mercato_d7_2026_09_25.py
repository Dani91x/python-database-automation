# -*- coding: utf-8 -*-
"""D7 (25/09/2026) - AL CLIC L'ORDINE PARTE A MERCATO, DENTRO LA BANDA DELLA STRATEGIA.

Ordine dell'utente (testuale): «I prezzi delle schede devono aggiornarsi anche
se il mercato si sposta; quando clicco devo essere avvisato del prezzo reale di
abbinamento e se l'ordine e' stato abbinato». Regola di esecuzione: al clic
l'ordine si piazza al MIGLIOR prezzo disponibile in quel momento purche' dentro
la banda che la strategia ammette per quell'operazione; fuori banda non si
piazza e la scheda lo dice («prezzo attuale X fuori dalla banda Y-Z della
strategia»).

Si certifica sul codice di produzione (``proposte_opportunita`` e
``bot_service._request_place``):
  1. la banda e' ESATTAMENTE l'insieme dei tick dove i criteri DI PREZZO di
     ``valuta_al_prezzo`` reggono (parita' su tutta la scala Betfair), e non
     esiste senza criteri o senza P del modello (mai un limite inventato);
  2. il file d'oro condiviso con la porta TypeScript e' quello del Python di oggi;
  3. l'ordine parte al prezzo di ADESSO (back e lay), non al visto; fuori banda
     o senza prezzo nessun ordine e un messaggio con i numeri;
  4. senza banda (proposta di prima del 24/09) resta la regola del 18/09 (prezzo
     visto + tolleranza) ed e' DICHIARATA sulla riga.
I finti sono quelli di ``test_scheda_al_ms_2026_09_24`` (chiavi del vero).
ASCII-only nel codice.
"""
from __future__ import annotations

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import proposte_opportunita as PO
from Betfair.safe_strategy.tests.test_proposte_opportunita_2026_09_17 import EV, NOW, DbFinto
from Betfair.safe_strategy.tests.test_scheda_al_ms_2026_09_24 import (
    _corpo_approvato, _feed, _giro, _opp_valida,
)
from Betfair.safe_strategy.tools import genera_oro_banda_strategia as ORO
from Betfair.safe_strategy.tools.genera_oro_valuta_proposta import _ANOMALIA, _MODELLO, _TENNIS


# ===========================================================================
# 1. LA BANDA = i tick dove i criteri DI PREZZO reggono
# ===========================================================================
@pytest.mark.parametrize("side,p,criteri", [
    ("back", 0.99, _TENNIS), ("lay", 0.01, _TENNIS), ("back", 0.5, _MODELLO),
    ("lay", 0.1, _MODELLO), ("back", 0.7, _ANOMALIA), ("lay", 0.2, _ANOMALIA),
])
def test_la_banda_e_la_valutazione_al_prezzo_su_tutta_la_scala(side, p, criteri):
    banda = PO.banda_della_strategia(side=side, p_model=p, criteri=criteri)
    dentro = []
    for q in PO._scala_betfair():
        v = PO.valuta_al_prezzo(side=side, prezzo=q, abbinabile=None, p_model=p,
                                criteri=criteri)
        regge = not [m for m in v["motivi"] if m["codice"] in PO.CODICI_DI_PREZZO]
        assert PO.in_banda(side=side, prezzo=q, p_model=p, criteri=criteri) is regge, q
        if regge:
            dentro.append(q)
    assert banda == {"min": dentro[0], "max": dentro[-1], "vuota": False}


def test_la_banda_non_guarda_ne_l_abbinabile_ne_le_soglie_di_probabilita():
    """Tennis lay p=0,2: ``max_prob_lay`` 0,1 cade a ogni prezzo (non e' un
    prezzo: lo decide l'utente come dal 24/09); la banda e' quella del prezzo."""
    b = PO.banda_della_strategia(side="lay", p_model=0.2, criteri=_TENNIS)
    assert b == {"min": 1.01, "max": 4.3, "vuota": False}


@pytest.mark.parametrize("side,p,criteri", [
    ("back", 0.8, None), ("back", None, _MODELLO), ("back", 1.5, _MODELLO),
    ("punta", 0.8, _MODELLO), ("back", float("nan"), _MODELLO), ("back", True, _MODELLO),
])
def test_senza_criteri_o_p_del_modello_la_banda_non_esiste(side, p, criteri):
    assert PO.banda_della_strategia(side=side, p_model=p, criteri=criteri) is None
    assert PO.in_banda(side=side, prezzo=2.0, p_model=p, criteri=criteri) is False


def test_banda_vuota_e_testo():
    b = PO.banda_della_strategia(side="lay", p_model=1.0, criteri=_ANOMALIA)
    assert b == {"min": None, "max": None, "vuota": True}
    assert PO.motivo_fuori_banda(1.5, b, "lay") == (
        "rifiutato: prezzo attuale 1.5 (lay) fuori dalla banda vuota (nessun prezzo la "
        "soddisfa con la P del modello di adesso) della strategia")
    assert PO.motivo_fuori_banda(None, {"min": 1.05, "max": 1000.0, "vuota": False},
                                 "back") == ("rifiutato: al clic non c'era un prezzo back "
                                             "sul mercato (banda della strategia 1.05-1000)")


# ===========================================================================
# 2. FILE D'ORO (Python <-> TypeScript)
# ===========================================================================
def test_il_file_d_oro_e_quello_del_python_di_oggi():
    assert ORO.main([]) == 0


# ===========================================================================
# 3. L'ORDINE PARTE AL PREZZO DI ADESSO, DENTRO LA BANDA
# ===========================================================================
class _Esito:
    def __init__(self, status, price, size):
        self.status, self.price, self.size = status, price, size
        self.fill_note = ""


@pytest.fixture
def esecuzione(monkeypatch):
    chiamate = []

    def finta(**kw):
        chiamate.append(kw)
        return _Esito(status="open", price=kw["row"]["price"], size=kw["row"]["size"])

    monkeypatch.setattr(S, "_execute", finta)
    return chiamate


def _piazza(db, corpo, riga):
    return S._request_place(db=db, market=None, rows_by_event={EV: riga}, payload=corpo,
                            params={"commission_pct": 5.0}, now=NOW, control_mode="paper")


@pytest.mark.parametrize("mercato", [1.05, 1.29, 1.31, 2.0, 10.0])
def test_back_parte_al_prezzo_di_adesso_ovunque_nella_banda(esecuzione, mercato):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = _piazza(db, _corpo_approvato(db, 1.30), _feed(back_p1=mercato))
    assert out.get("ok") is True, out
    assert esecuzione[0]["row"]["price"] == mercato == db.trades[0]["price"]
    assert db.trades[0]["meta"]["esecuzione_al_clic"]["regola"] == PO.ESECUZIONE_A_MERCATO
    att = [p for k, p in db.attivita if k == "opportunita_piazzata"][0]
    assert att["esecuzione_al_clic"]["prezzo_attuale"] == mercato


@pytest.mark.parametrize("mercato", [1.01, 1.02, 1.04])
def test_back_sotto_la_banda_nessun_ordine_e_il_messaggio(esecuzione, mercato):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    out = _piazza(db, _corpo_approvato(db, 1.30), _feed(back_p1=mercato))
    assert out["error"] == "fuori_banda_strategia"
    assert out["message"] == (f"rifiutato: prezzo attuale {mercato:g} (back) fuori dalla "
                              f"banda 1.05-1000 della strategia")
    assert db.trades == [] and esecuzione == []
    skip = [p for k, p in db.attivita if k == "skip"][-1]
    assert skip["reason"] == "fuori_banda_strategia" and skip["price_attuale"] == mercato


def _opp_lay(price=3.0):
    return {"market_type": "MATCH_ODDS", "market_id": "1.900", "selection_id": 11,
            "selection_name": "Leader", "side": "lay", "price": price,
            "size_available": 500.0, "confidence": 1.0, "p_model": 0.01,
            "edge": round(1 / price - 0.01, 6), "p_implied": round(1 / price, 6),
            "ev": 0.1, "rationale": "lay della sfavorita"}


def _feed_lay(lay_p1):
    r = _feed()
    r["payload"]["odds"]["p1"]["lay"] = lay_p1
    r["payload"]["odds"]["p1"]["lay_size"] = 500.0
    return r


def test_lay_parte_al_prezzo_di_adesso_e_sopra_la_banda_no(esecuzione):
    """Lay tennis p=0,01: banda 1,01-5 (tetto di responsabilita' 20 EUR con stake
    5). Il mercato a 4,4 -> parte a 4,4; a 5,1 -> fuori banda, nessun ordine."""
    db = DbFinto()
    _giro(db, [_opp_lay(3.0)], riga=_feed_lay(3.0),
          params={"max_liability_per_trade": 20.0})
    corpo = _corpo_approvato(db, 3.0)
    assert corpo["side"] == "lay"
    out = _piazza(db, corpo, _feed_lay(4.4))
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 4.4
    assert db.trades[0]["liability"] == round(db.trades[0]["size"] * 3.4, 2)
    db2 = DbFinto()
    _giro(db2, [_opp_lay(3.0)], riga=_feed_lay(3.0),
          params={"max_liability_per_trade": 20.0})
    esecuzione.clear()
    out = _piazza(db2, _corpo_approvato(db2, 3.0), _feed_lay(5.1))
    assert out["error"] == "fuori_banda_strategia" and esecuzione == []
    assert out["message"] == ("rifiutato: prezzo attuale 5.1 (lay) fuori dalla banda "
                              "1.01-5 della strategia")


def test_senza_prezzo_sul_mercato_nessun_ordine(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    senza = _feed()
    senza["payload"]["odds"]["p1"]["back"] = None
    out = _piazza(db, _corpo_approvato(db, 1.30), senza)
    assert out["error"] == "prezzo_attuale_assente" and esecuzione == [] and db.trades == []


def test_anche_senza_prezzo_visto_parte_a_mercato(esecuzione):
    """Client di prima del 18/09 (nessun ``price_visto``): la banda c'e', quindi
    la regola e' la stessa - a mercato - e il clic vecchio non si misura."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = dict(db.vive()[0]["payload"])
    out = _piazza(db, corpo, _feed(back_p1=1.33))
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 1.33
    assert db.trades[0]["meta"]["esecuzione_al_clic"]["prezzo_visto"] is None


# ===========================================================================
# 4. SENZA BANDA: la regola del 18/09, dichiarata
# ===========================================================================
def test_senza_criteri_resta_il_prezzo_visto_con_la_tolleranza_e_lo_dice(esecuzione):
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30)
    corpo.pop("criteri")
    out = _piazza(db, corpo, _feed(back_p1=1.31))
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 1.30, "senza banda l'ordine resta al prezzo VISTO"
    assert db.trades[0]["meta"]["esecuzione_al_clic"] == {"regola": PO.ESECUZIONE_PREZZO_VISTO,
                                                  "banda": None}
    db2 = DbFinto()
    _giro(db2, [_opp_valida(1.30)])
    corpo2 = _corpo_approvato(db2, 1.30)
    corpo2.pop("criteri")
    out = _piazza(db2, corpo2, _feed(back_p1=1.36))
    assert out["error"] == "prezzo_visto_fuori_tolleranza"


def test_richiesta_manuale_senza_proposta_invariata(esecuzione):
    """«Investi» dalla tabella (nessun ``opp_key``): nessuna banda, nessuna
    ``esecuzione`` sulla riga, il prezzo e' quello della richiesta."""
    db = DbFinto()
    _giro(db, [_opp_valida(1.30)])
    corpo = _corpo_approvato(db, 1.30)
    corpo.pop("opp_key")
    out = _piazza(db, corpo, _feed(back_p1=1.60))
    assert out.get("ok") is True, out
    assert db.trades[0]["price"] == 1.30 and "esecuzione_al_clic" not in db.trades[0]["meta"]
