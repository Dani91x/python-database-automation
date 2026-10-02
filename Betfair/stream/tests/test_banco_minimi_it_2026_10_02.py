"""BANCO 02/10 - L'EXCHANGE DEL BANCO RIFIUTA COME BETFAIR .it GLI ORDINI SOTTO IL MINIMO.

Reperto R1 del correttore di Mike (01/10) e punto 3 dell'utente: il simulatore
del banco ABBINAVA ordini sotto il minimo (banche di chiusura da 0,59 / 0,14 /
0,03 / 0,01 «abbinate» nelle sintetiche), per questo il difetto di Ashdod (banca
0,43 rifiutata INVALID_BET_SIZE 21 volte) nel replay non si vedeva.

Oggetti VERI: registrazione 35760084, ``FlumineSimulation`` + ``MotoreReplay`` +
``MercatoFlumine`` del banco (``trasporto_rapido.BancoRapido``), esecuzione
simulata di flumine con la regola di ``minimi_banco`` montata da
``simulazione_flumine``. Ogni prova ha la sua falsificazione nel corpo
(``ATTIVO = False``: il controllo deve trovare l'abbinato). ASCII-only.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from Betfair.omega.omega_market import PlaceRifiutato
from Betfair.stream.backtest import banco_comune as B
from Betfair.stream.backtest import certifica as CF
from Betfair.stream.backtest import minimi_banco as MB

EVENTO = "35760084"


def _cartella_registrazioni() -> str:
    candidati = [os.getenv("LIVE_STREAM_DATA_DIR") or ""]
    radice = Path(__file__).resolve().parents[3]
    candidati += [str(radice / "_live_raw"), str(radice.parents[2] / "_live_raw")]
    for c in candidati:
        if c and os.path.exists(os.path.join(c, EVENTO, "%s.raw.jsonl" % EVENTO)):
            return c
    return ""


pytestmark = pytest.mark.skipif(not _cartella_registrazioni(),
                                reason="registrazione 35760084 assente su questa macchina")


@pytest.fixture
def banco():
    from Betfair.stream.backtest import trasporto_rapido as TRR

    with B.simulazione_flumine():
        b = TRR.BancoRapido("mike", EVENTO, _cartella_registrazioni())
        b.__enter__()
        try:
            assert b.trova_match_odds(), "nessun MATCH_ODDS aperto nella registrazione"
            yield b
        finally:
            b.__exit__(None, None, None)


def _lay(b: Any, size: float, ref: str, **kw: Any):
    sel, prezzo, _ = b.quota("lay")
    return b.mercato_rest.place_order_live(market_id=b.market_id, selection_id=sel,
                                           price=prezzo, size=size, event_id=EVENTO,
                                           side="lay", customer_ref=ref, **kw)


def _back(b: Any, size: float, ref: str, prezzo: Any = None, **kw: Any):
    sel, p, _ = b.quota("back")
    return b.mercato_rest.place_order_live(market_id=b.market_id, selection_id=sel,
                                           price=p if prezzo is None else prezzo, size=size,
                                           event_id=EVENTO, side="back", customer_ref=ref, **kw)


# ---------------------------------------------------------------------------
# 1. la REST del banco: la stessa guardia del vero (omega_market.place_order_live)
# ---------------------------------------------------------------------------
def test_rest_del_banco_banca_0_43_rifiutata_prima_di_partire(banco):
    with pytest.raises(PlaceRifiutato) as ex:
        _lay(banco, 0.43, "t-043")
    assert ex.value.error_code == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert "t-043" not in banco.mercato_rest.ordini
    # dal minimo in su l'ordine parte e si abbina
    r = _lay(banco, 1.00, "t-100")
    assert r.ok and r.size_matched == 1.00


# ---------------------------------------------------------------------------
# 2. l'EXCHANGE del banco: INVALID_BET_SIZE, mai un abbinato (con falsificazione)
# ---------------------------------------------------------------------------
def test_exchange_del_banco_rifiuta_invalid_bet_size_e_il_controllo_lo_vede(banco, monkeypatch):
    """Un ordine che arriva all'exchange sotto il suo minimo (qui: place-and-trim
    con importo finale 0,43 < 0,50, l'unica via per cui la REST lo lascia passare)
    torna ``ok=False`` ``INVALID_BET_SIZE`` e nessun abbinato. Falsificazione: a
    regola spenta lo stesso ordine si abbina e il controllo lo trova."""
    banco.mercato_rest._place_and_trim_in_corso = True
    try:
        r = _lay(banco, 0.43, "t-x1")
    finally:
        banco.mercato_rest._place_and_trim_in_corso = False
    assert r.ok is False and r.error_code == "INVALID_BET_SIZE" and r.size_matched == 0.0
    assert MB.abbinati_sotto_minimo() == []
    assert [x["codice"] for x in MB.REGISTRO.rifiutati] == ["INVALID_BET_SIZE"]
    # FALSIFICAZIONE: regola spenta -> il banco ottimista di prima, il controllo e' rosso
    monkeypatch.setattr(MB, "ATTIVO", False)
    banco.mercato_rest._place_and_trim_in_corso = True
    try:
        r2 = _lay(banco, 0.43, "t-x2")
    finally:
        banco.mercato_rest._place_and_trim_in_corso = False
    assert r2.ok is True and r2.size_matched == 0.43
    fuori = MB.abbinati_sotto_minimo()
    assert len(fuori) == 1 and fuori[0]["size"] == 0.43 and fuori[0]["abbinato"] == 0.43


def test_place_and_trim_della_coda_floor_0_50(banco):
    """``place_submin_live`` del banco come il vero: 0,60 riesce (importo finale
    sopra il floor di legge), 0,30 e' ``SOTTO_MINIMO_NON_PIAZZABILE`` e nulla parte."""
    sel, p, _ = banco.quota("back")
    r = banco.mercato_rest.place_submin_live(market_id=banco.market_id, selection_id=sel,
                                             price=p, size=0.60, event_id=EVENTO, side="back",
                                             customer_ref="t-p60")
    assert r.ok and r.size_matched == 0.60
    assert any(t == MB.PLACE_AND_TRIM and round(s, 2) == 0.60
               for _o, t, s in MB.REGISTRO.piazzati)
    with pytest.raises(PlaceRifiutato) as ex:
        banco.mercato_rest.place_submin_live(market_id=banco.market_id, selection_id=sel,
                                             price=p, size=0.30, event_id=EVENTO, side="back",
                                             customer_ref="t-p30")
    assert ex.value.error_code == "SOTTO_MINIMO_NON_PIAZZABILE"
    assert MB.abbinati_sotto_minimo() == []


def test_replace_con_importo_finale_sotto_0_50_rifiutato(banco):
    """La coda del place-and-trim sul canale: parcheggio 1,00 a una quota che non
    si abbina, taglio a 0,40, replace alla quota buona -> il NUOVO ordine del
    replace (0,40 < 0,50) e' rifiutato INVALID_BET_SIZE. Con 0,60 passa."""
    for resto, atteso_ok in ((0.40, False), (0.60, True)):
        ref = "t-park-%d" % int(resto * 100)
        r = _back(banco, 1.00, ref, prezzo=1000.0, fill_or_kill=False)
        assert r.ok and r.size_matched == 0.0
        ordine = banco.mercato_rest.ordini[ref]
        c = banco.mercato_rest.cancel_order_live(r.bet_id, banco.market_id,
                                                 size_reduction=round(1.00 - resto, 2))
        assert c.ok and round(float(ordine.size_remaining), 2) == resto
        _sel, p, _ = banco.quota("back")
        mercato = banco.mercato_rest.s.mercati[banco.market_id]
        mercato.replace_order(ordine, p)
        banco.motore.attendi_esecuzione(banco.market_id)
        nuovo = ordine.trade.orders[-1]
        assert nuovo is not ordine
        risposta = nuovo.responses.place_response
        rifiutati = [x for x in MB.REGISTRO.rifiutati
                     if x["tipo"] == MB.SOSTITUZIONE and x["size"] == resto]
        if atteso_ok:
            # flumine registra la risposta del replace solo se riuscito
            assert getattr(risposta, "status", None) == "SUCCESS" and rifiutati == []
        else:
            assert len(rifiutati) == 1 and rifiutati[0]["codice"] == "INVALID_BET_SIZE"
            assert float(nuovo.simulated.size_matched) == 0.0
            assert float(nuovo.simulated.size_voided) == resto     # mai vivo a mercato
    assert any(t == MB.SOSTITUZIONE and round(s, 2) == 0.40 for _o, t, s in MB.REGISTRO.piazzati)
    assert MB.abbinati_sotto_minimo() == []


# ---------------------------------------------------------------------------
# 3. il controllo di certificazione nel referto (``certifica.segna_sotto_minimo``)
# ---------------------------------------------------------------------------
def test_certifica_scrive_la_violazione_banco_sotto_minimo(monkeypatch):
    from Betfair.mike import certificazione as CERT

    finto = SimpleNamespace(side="LAY", simulated=SimpleNamespace(size_matched=0.43))
    reg = MB.Registro()
    reg.piazzati.append((finto, MB.DIRETTO, 0.43))
    monkeypatch.setattr(MB, "REGISTRO", reg)
    r = CERT.Referto(event_id="x")
    assert CF.segna_sotto_minimo(r, CERT) == 1
    assert [v.codice for v in r.violazioni] == [MB.CODICE_CONTROLLO]
    # una seconda chiamata non la duplica; un referto sano non ha ne' violazione ne' nota
    CF.segna_sotto_minimo(r, CERT)
    assert len(r.violazioni) == 1
    monkeypatch.setattr(MB, "REGISTRO", MB.Registro())
    sano = CERT.Referto(event_id="y")
    assert CF.segna_sotto_minimo(sano, CERT) == 0 and sano.violazioni == [] and sano.note == []
