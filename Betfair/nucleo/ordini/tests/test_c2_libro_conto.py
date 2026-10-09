"""W1-C2 - il libro ordini del conto (``LibroConto``).

Alimentato da un ``FlussoOrdiniConto`` (protocollo del comparto A) con ordini
VERI (``CurrentOrder`` di betfairlightweight dal JSON di Betfair o dalla cache
dello stream ordini) e da una sorgente in prova. Paper e live mai sommati;
ordine dei messaggi; consumatori; concorrenza; tetto di memoria. ASCII-only.
"""
from __future__ import annotations

import dataclasses
import logging
import threading
from typing import List

import pytest

from Betfair.nucleo.betfair.contratto import FlussoOrdiniConto
from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini import libro_conto as L
from Betfair.nucleo.ordini.contratto import LibroOrdiniConto, OrdineConto
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, DRAW, HOME, MKT, FlussoFinto,
                                                       correnti, dal_conto, dallo_stream,
                                                       ordine_json, uo)


def _libro_con(*ordini) -> L.LibroConto:
    lib = L.LibroConto()
    lib.collega_live(FlussoFinto(tuple(ordini)))
    return lib


def test_implementa_i_protocolli_del_contratto():
    lib: LibroOrdiniConto = L.LibroConto()
    assert callable(lib.ordini) and callable(lib.posizione)
    f: FlussoOrdiniConto = FlussoFinto()
    assert callable(f.aggiungi_consumatore)


def test_ogni_ordine_con_autore_abbinato_residuo_prezzo_medio_stato():
    co = dallo_stream(MKT, {HOME: [uo("1", "BACK", 2.0, 3.0, residuo=1.0, rfs="mike", rfo="mike-t4"),
                                   uo("2", "LAY", 0.0, 2.5, residuo=2.0, rfs="live", rfo="h-1")],
                            AWAY: [uo("3", "BACK", 5.0, 4.0)]})
    flusso = FlussoFinto()
    lib = L.LibroConto()
    lib.collega_live(flusso)
    for c in co:
        flusso.manda(L.ordine_da_corrente(c, ricevuto_ms=10))
    per_bet = {o.bet_id: o for o in lib.ordini(MKT)}
    assert (per_bet["1"].autore, per_bet["1"].abbinato, per_bet["1"].residuo,
            per_bet["1"].prezzo_medio, per_bet["1"].stato) == ("mike", 2.0, 1.0, 3.0,
                                                               "abbinato_parziale")
    assert (per_bet["2"].autore, per_bet["2"].stato, per_bet["2"].prezzo_medio) == (
        "desktop", "accettato_betfair", None)
    assert (per_bet["3"].autore, per_bet["3"].stato) == ("sito", "abbinato")
    assert all(o.modo == "live" for o in per_bet.values())
    assert lib.ordini("1.999") == ()
    assert per_bet["1"].ref == "mike-t4"


def test_stato_e_la_fase_del_motore_di_oggi():
    from Betfair.stream.motore_ordini import fase_da_riga

    casi = [ordine_json("1", "BACK", 0.0, 2.0, residuo=2.0),
            ordine_json("2", "BACK", 1.0, 2.0, residuo=1.0),
            ordine_json("3", "BACK", 2.0, 2.0),
            ordine_json("4", "BACK", 1.5, 2.0, annullato=0.5),          # parziale poi annullato
            ordine_json("5", "BACK", 0.0, 2.0, scaduto=2.0)]             # LAPSE al fischio
    for d in casi:
        o = dal_conto(d)
        riga = {"status": d["status"], "size_matched": d["sizeMatched"],
                "size": d["priceSize"]["size"], "size_cancelled": d["sizeCancelled"],
                "size_lapsed": d["sizeLapsed"], "bet_id": d["betId"]}
        assert L.fase_dell_ordine(o) == fase_da_riga(riga)
    assert [L.fase_dell_ordine(dal_conto(d)) for d in casi] == [
        "accettato_betfair", "abbinato_parziale", "abbinato", "annullato", "scaduto"]


def test_rest_e_stream_danno_lo_stesso_ordine():
    rest = correnti(ordine_json("7", "LAY", 1.0, 2.5, residuo=1.0, csr="omega", cor="omega-t3",
                                sel=HOME))[0]
    st = dallo_stream(MKT, {HOME: [uo("7", "LAY", 1.0, 2.5, residuo=1.0, rfs="omega",
                                      rfo="omega-t3")]})[0]
    a = L.ordine_da_corrente(rest, ricevuto_ms=5)
    b = L.ordine_da_corrente(st, ricevuto_ms=5)
    campi = ("bet_id", "market_id", "selection_id", "handicap", "lato", "prezzo", "importo",
             "stato", "abbinato", "residuo", "scaduto", "annullato", "prezzo_medio",
             "customer_order_ref", "customer_strategy_ref", "persistenza", "tipo")
    assert [getattr(a, c) for c in campi] == [getattr(b, c) for c in campi]


def test_conversione_rifiuta_i_campi_mancanti():
    d = ordine_json("1", "BACK", 1.0, 2.0)
    for chiave, valore in (("priceSize", None), ("side", "X"), ("status", "PENDING"),
                           ("betId", None)):
        rotto = dict(d)
        rotto[chiave] = valore
        with pytest.raises(ValueError):
            L.ordine_da_riga_conto(rotto, ricevuto_ms=1)
    # chiave scritta in un'altra grafia (catalogo n.1): non si legge
    snake = dict(d)
    snake["size_matched"] = snake.pop("sizeMatched")
    assert L.ordine_da_riga_conto(snake, ricevuto_ms=1).abbinato == 0.0


def test_paper_e_live_mai_sommati():
    lib = L.LibroConto()
    live = dal_conto(ordine_json("1", "BACK", 10.0, 2.0, csr="mike", cor="mike-t1"))
    lib.ricevi_live(live)
    # STESSO bet_id in prova: resta separato
    lib.ricevi_prova(L.OrdineInProva(dal_conto(ordine_json("1", "LAY", 4.0, 3.0)), "omega"))
    assert [o.modo for o in lib.ordini(MKT)] == ["live", "paper"]
    assert [o.autore for o in lib.ordini(MKT, "paper")] == ["omega"]
    pl = lib.posizione(MKT, "live")
    pp = lib.posizione(MKT, "paper")
    assert pl.se_vince == {HOME: 10.0} and pl.modo == "live"
    assert pp.se_vince == {HOME: -8.0} and pp.modo == "paper"
    with pytest.raises(ValueError):
        lib.posizione(MKT, "tutti")  # type: ignore[arg-type]


def test_sorgente_in_prova_collegata():
    class Sorgente:
        def __init__(self):
            self.cb = []

        def aggiungi_consumatore(self, cb):
            self.cb.append(cb)

        def ordini(self, market_id=None):
            return (L.OrdineInProva(dal_conto(ordine_json("p1", "BACK", 2.0, 2.0)), "safe"),)

    s = Sorgente()
    lib = L.LibroConto()
    lib.collega_prova(s)
    assert [o.autore for o in lib.ordini(MKT, "paper")] == ["safe"]
    s.cb[0](L.OrdineInProva(dal_conto(ordine_json("p2", "LAY", 2.0, 2.0), 2000), None))
    assert {o.bet_id: o.autore for o in lib.ordini(MKT, "paper")} == {"p1": "safe", "p2": "sito"}
    assert lib.ordini(MKT, "live") == ()


def test_messaggio_piu_vecchio_non_sovrascrive():
    lib = L.LibroConto()
    nuovo = dal_conto(ordine_json("1", "BACK", 2.0, 2.0), ricevuto_ms=2000)
    vecchio = dal_conto(ordine_json("1", "BACK", 0.0, 2.0, residuo=2.0), ricevuto_ms=1000)
    lib.ricevi_live(nuovo)
    lib.ricevi_live(vecchio)
    assert lib.ordine("1", "live").abbinato == 2.0
    assert lib.conti["fuori_ordine"] == 1
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 2.0, 2.0), ricevuto_ms=2000))  # stesso istante: entra
    assert lib.conti["fuori_ordine"] == 1


def test_consumatori_avvisati_e_errore_isolato(caplog):
    lib = L.LibroConto()
    visti: List[OrdineConto] = []

    def rotto(_o):
        raise RuntimeError("consumatore rotto")

    lib.aggiungi_consumatore(rotto)
    lib.aggiungi_consumatore(visti.append)
    with caplog.at_level(logging.ERROR):
        lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 2.0, 2.0)))
    assert [o.bet_id for o in visti] == ["1"]
    assert lib.conti["consumatori_ko"] == 1
    assert "consumatore KO" in caplog.text


def test_indizi_riattribuiscono_e_avvisano():
    lib = L.LibroConto()
    visti: List[OrdineConto] = []
    lib.aggiungi_consumatore(visti.append)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 2.0, 2.0, csr="live", cor="h-1")))
    assert lib.ordine("1", "live").autore == "desktop"
    lib.aggiungi_indizi("1", A.indizi_da_riga_coda({"client_ref": "risk3s", "params": {}}))
    assert lib.ordine("1", "live").autore == "risk"
    assert lib.attribuzione("1", "live").fonte == "indizio"
    assert [o.autore for o in visti] == ["desktop", "risk"]
    # indizio PRIMA dell'ordine: si ricorda
    lib.aggiungi_indizi("2", [A.Indizio("tabella", "omega_trades")])
    lib.ricevi_live(dal_conto(ordine_json("2", "BACK", 2.0, 2.0, csr="live")))
    assert lib.ordine("2", "live").autore == "omega"


def test_ordine_illeggibile_scartato_e_detto(caplog):
    lib = L.LibroConto()
    o = dal_conto(ordine_json("1", "BACK", 2.0, 2.0))
    rotto = dataclasses.replace(o, selection_id="non un numero")  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR):
        lib.ricevi_live(rotto)
    assert lib.conti["scartati"] == 1 and lib.ordini(MKT) == ()
    assert "scartato" in caplog.text


def test_tetto_dimentica_solo_i_terminali_piu_vecchi():
    lib = L.LibroConto(max_ordini=3)
    lib.ricevi_live(dal_conto(ordine_json("v1", "BACK", 0.0, 2.0, residuo=2.0), 1))   # vivo, vecchio
    for i in range(4):
        lib.ricevi_live(dal_conto(ordine_json(f"t{i}", "BACK", 2.0, 2.0), 10 + i))
    ids = {o.bet_id for o in lib.ordini(MKT)}
    assert "v1" in ids and len(ids) == 3 and ids == {"v1", "t2", "t3"}
    assert lib.conti["dimenticati"] == 2
    assert lib.stato()["ordini"] == {"paper": 0, "live": 3}


def test_dimentica_mercato_e_mercati():
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 2.0, 2.0)))
    lib.ricevi_live(dal_conto(ordine_json("2", "BACK", 2.0, 2.0, market="1.300")))
    lib.ricevi_prova(L.OrdineInProva(dal_conto(ordine_json("3", "BACK", 2.0, 2.0)), "mike"))
    assert lib.mercati("live") == (MKT, "1.300")
    assert lib.dimentica_mercato(MKT, "live") == 1
    assert lib.mercati("live") == ("1.300",) and lib.mercati("paper") == (MKT,)
    assert lib.dimentica_mercato(MKT) == 1
    assert lib.stato()["ordini"] == {"paper": 0, "live": 1}


def test_concorrenza_piu_thread_che_alimentano_e_leggono():
    import sys

    # cambi di thread fittissimi: senza il lucchetto la lettura di un mercato
    # mentre un altro thread lo riempie solleva (insieme cambiato durante il giro)
    vecchio = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        _concorrenza()
    finally:
        sys.setswitchinterval(vecchio)


def _concorrenza():
    lib = L.LibroConto()
    A.regole_di_oggi()
    L.fase_dell_ordine(dal_conto(ordine_json("x", "BACK", 1.0, 2.0)))   # import pigri fuori dai thread
    errori: List[BaseException] = []

    def scrivi(base: int):
        try:
            for i in range(200):
                sel = (HOME, AWAY, DRAW)[i % 3]
                lib.ricevi_live(dal_conto(ordine_json(f"{base}-{i}", "BACK", 1.0, 2.0, sel=sel),
                                          ricevuto_ms=i))
        except BaseException as ex:  # noqa: BLE001
            errori.append(ex)

    def leggi():
        try:
            for _ in range(400):
                lib.posizione(MKT, "live")
                lib.ordini(MKT)
                lib.stato()
        except BaseException as ex:  # noqa: BLE001
            errori.append(ex)

    th = [threading.Thread(target=scrivi, args=(b,)) for b in range(4)] + \
         [threading.Thread(target=leggi) for _ in range(2)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    assert not errori
    assert len(lib.ordini(MKT, "live")) == 800
    pos = lib.posizione(MKT, "live")
    assert pos.abbinato_back == {HOME: 268.0, AWAY: 268.0, DRAW: 264.0}   # 4 x (67, 67, 66)


def test_comandi_ammessi_solo_sui_propri():
    def o(autore, residuo):
        return OrdineConto("1", MKT, HOME, 0.0, "back", 2.0, 2.0, 0.0, residuo, None, "x",
                           autore, None, "live", 1)  # type: ignore[arg-type]
    assert L.comandi_ammessi(o("desktop", 2.0)) == ("annulla", "sposta")
    assert L.comandi_ammessi(o("sito", 2.0)) == ("annulla", "sposta")
    for autore in ("mike", "omega", "risk", "sconosciuto", "scalper"):
        assert L.comandi_ammessi(o(autore, 2.0)) == ()
    assert L.comandi_ammessi(o("desktop", 0.0)) == ()


def test_modo_non_ammesso():
    with pytest.raises(ValueError):
        L.LibroConto()._ricevi("tutti", dal_conto(ordine_json("1", "BACK", 1.0, 2.0)), None)
    with pytest.raises(ValueError):
        L.componi_ordine_conto("x", dal_conto(ordine_json("1", "BACK", 1.0, 2.0)),
                               A.Attribuzione("sito", "sito", "riferimenti"))


def test_lettura_aspetta_lo_scrittore_deterministico(monkeypatch):
    """Il lucchetto, provato senza dipendere dal caso: lo scrittore si ferma
    DENTRO la composizione dell'ordine; un lettore deve aspettarlo."""
    dentro, rilascia, letto = threading.Event(), threading.Event(), threading.Event()
    vera = L.fase_dell_ordine

    def lenta(o):
        dentro.set()
        assert rilascia.wait(5)
        return vera(o)

    lib = L.LibroConto()
    A.regole_di_oggi()
    monkeypatch.setattr(L, "fase_dell_ordine", lenta)
    w = threading.Thread(target=lib.ricevi_live, args=(dal_conto(ordine_json("1", "BACK", 2.0, 2.0)),))
    w.start()
    assert dentro.wait(5)
    r = threading.Thread(target=lambda: (lib.ordini(MKT), letto.set()))
    r.start()
    assert not letto.wait(0.3), "il lettore non ha aspettato lo scrittore"
    rilascia.set()
    assert letto.wait(5)
    w.join()
    r.join()
    assert [o.bet_id for o in lib.ordini(MKT)] == ["1"]
