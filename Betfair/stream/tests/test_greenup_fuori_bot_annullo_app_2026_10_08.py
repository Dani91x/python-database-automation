# -*- coding: utf-8 -*-
"""08/10/2026 sera, decisione dell'utente D-7 ("annullarlo") sul green-up FUORI BOT.

Prima: un ordine DELL'APP (``customerStrategyRef`` 'live', fuori bot) ancora non
abbinato sul lato della copertura FERMAVA la chiusura di un ordine del sito (rifiuto
col motivo, per non avere due coperture vive). Adesso: si ANNULLA in automatico
(``cancelOrders`` del client reale), si RILEGGE il conto e si copre l'esposizione
REALE di adesso; l'esito dichiara l'annullo. Annullo fallito (l'ordine resta vivo):
nessuna copertura, rifiuto col motivo. Gli ordini degli ALTRI BOT non si toccano.

I finti sono quelli del file del W2 (``test_greenup_fuori_bot_2026_10_08.py``): il
conto e' il ``BetfairClient`` VERO di flumine attorno all'``APIClient`` VERO di
betfairlightweight, col SOLO trasporto (``betting.request``) sostituito. Qui il
trasporto risponde anche a ``cancelOrders`` con il JSON di Betfair (``status``,
``marketId``, ``instructionReports`` con ``instruction.betId``, ``sizeCancelled``,
``cancelledDate``, ``errorCode``) e, come su Betfair, CAMBIA lo stato dell'ordine sul
conto (la rilettura vede l'annullo o l'abbinamento avvenuto nel frattempo). La
forma della risposta e' provata con la classe VERA ``CancelOrders`` della libreria.

Ogni test e' stato falsificato (referto
``AUDIT_2026-10-08/decisioni_sera/W2_D7_ANNULLO_ORDINE_APP.md``). ASCII-only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from betfairlightweight.resources import CancelOrders

import Betfair.stream.live_order_worker as wk
from Betfair.stream.tests.test_greenup_fuori_bot_2026_10_08 import (  # noqa: F401
    AWAY, DRAW, HOME, MIKE_BACK, MKT, MO, OVER, UNDER, Conto, Sb, _runner_live, book,
    esegui, framework, mercato_mo, mercato_ou, ordine, piazzati, riga_greenup,
)

LIST = "SportsAPING/v1.0/listCurrentOrders"
CANCEL = "SportsAPING/v1.0/cancelOrders"


class ContoConAnnullo(Conto):
    """Il conto che risponde anche a ``cancelOrders`` come Betfair.

    ``annullo`` dice che cosa succede all'ordine chiesto:
      * ``"ok"``: annullato tutto il residuo (``SUCCESS``, ``sizeCancelled``);
      * ``("abbina", x)``: prima dell'annullo si abbinano ``x`` (al prezzo
        dell'ordine), poi si annulla il resto (``SUCCESS`` col solo resto);
      * ``"abbinato_tutto"``: l'ordine si e' abbinato tutto prima dell'annullo
        (``FAILURE`` / ``BET_TAKEN_OR_LAPSED``, come Betfair);
      * ``"rifiuta"``: Betfair rifiuta l'annullo e l'ordine resta vivo
        (``FAILURE`` / ``ERROR_IN_ORDER``);
      * ``"rete"``: il trasporto esplode (esito ignoto), l'ordine resta vivo;
      * ``"muto"``: l'esito dice ``SUCCESS`` ma l'ordine resta vivo sul conto.
    ``esplode_dopo_annullo``: la RILETTURA del conto fallisce."""

    def __init__(self, ordini: List[Dict[str, Any]], *, annullo: Any = "ok",
                 esplode_dopo_annullo: bool = False, mercato: Any = None,
                 sospendi_dopo_annullo: bool = False) -> None:
        super().__init__(ordini)
        self.sospendi_dopo_annullo = sospendi_dopo_annullo
        self.annullo = annullo
        self.esplode_dopo_annullo = esplode_dopo_annullo
        self.mercato = mercato
        self.piazzati_all_annullo: Optional[int] = None
        self.risposte_annullo: List[Dict[str, Any]] = []

    def _ordine(self, bet_id: str) -> Optional[Dict[str, Any]]:
        return next((o for o in self.ordini if o["betId"] == bet_id), None)

    def request(self, method: str, params: Dict[str, Any], session: Any = None) -> tuple:
        if method != CANCEL:
            if self.esplode_dopo_annullo and any(m == CANCEL for m, _ in self.chiamate):
                self.chiamate.append((method, dict(params)))
                raise RuntimeError("rete giu' alla rilettura")
            return super().request(method, params, session)
        self.chiamate.append((method, dict(params)))
        if self.mercato is not None:
            self.piazzati_all_annullo = len(self.mercato.piazzati)
            if self.sospendi_dopo_annullo:
                # il mercato si sospende durante l'annullo: book VERO senza prezzi
                self.mercato.market_book = book(MO, [
                    {"selectionId": s, "handicap": 0.0, "status": "ACTIVE",
                     "ex": {"availableToBack": [], "availableToLay": [],
                            "tradedVolume": []}} for s in (HOME, AWAY, DRAW)])
        if self.annullo == "rete":
            raise RuntimeError("timeout su cancelOrders")
        reports = []
        stato = "SUCCESS"
        for ins in params.get("instructions") or []:
            o = self._ordine(str(ins["betId"]))
            rem = float(o["sizeRemaining"]) if o else 0.0
            if self.annullo == "rifiuta":
                reports.append({"status": "FAILURE", "errorCode": "ERROR_IN_ORDER",
                                "instruction": {"betId": ins["betId"]}})
                stato = "FAILURE"
                continue
            if self.annullo == "muto":
                reports.append({"status": "SUCCESS", "instruction": {"betId": ins["betId"]},
                                "sizeCancelled": rem,
                                "cancelledDate": "2026-10-08T20:00:05.000Z"})
                continue
            if self.annullo == "abbinato_tutto":
                o["sizeMatched"] = round(o["sizeMatched"] + rem, 2)
                o["averagePriceMatched"] = o["priceSize"]["price"]
                o["sizeRemaining"] = 0.0
                o["status"] = "EXECUTION_COMPLETE"
                o["matchedDate"] = "2026-10-08T20:00:04.000Z"
                reports.append({"status": "FAILURE", "errorCode": "BET_TAKEN_OR_LAPSED",
                                "instruction": {"betId": ins["betId"]}})
                stato = "FAILURE"
                continue
            if isinstance(self.annullo, tuple) and self.annullo[0] == "abbina":
                x = float(self.annullo[1])
                o["sizeMatched"] = round(o["sizeMatched"] + x, 2)
                o["averagePriceMatched"] = o["priceSize"]["price"]
                o["matchedDate"] = "2026-10-08T20:00:04.000Z"
                rem = round(rem - x, 2)
            o["sizeCancelled"] = round(o["sizeCancelled"] + rem, 2)
            o["sizeRemaining"] = 0.0
            o["status"] = "EXECUTION_COMPLETE"
            reports.append({"status": "SUCCESS", "instruction": {"betId": ins["betId"]},
                            "sizeCancelled": rem,
                            "cancelledDate": "2026-10-08T20:00:05.000Z"})
        risultato: Dict[str, Any] = {"status": stato, "marketId": params.get("marketId"),
                                     "instructionReports": reports}
        if stato == "FAILURE":
            risultato["errorCode"] = "BET_ACTION_ERROR"
        self.risposte_annullo.append(risultato)
        return (None, {"jsonrpc": "2.0", "id": 1, "result": risultato}, 0.01)

    def metodi(self) -> List[str]:
        return [m for m, _p in self.chiamate]


def sito_back_e_app_lay_appesa(residuo: float = 6.0, prezzo_app: float = 2.6,
                               abbinato_app: float = 0.0) -> List[Dict[str, Any]]:
    """Sito BACK HOME 5 @3 (W 10, L -5) + ordine dell'app LAY non abbinato sul lato
    della copertura (csr 'live', ref del terminale manuale)."""
    return [ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
            ordine("H1", "LAY", abbinato_app, prezzo_app, csr="live", cor="9f1c2-77",
                   residuo=residuo, market=MO, sel=HOME)]


def sb_con_app() -> Sb:
    # l'ordine dell'app ha la sua riga di specchio con source 'runner' (come in
    # produzione): NON e' di un bot
    return Sb(betfair_live_orders=[{"bet_id": "H1", "mode": "live", "source": "runner"}])


# ===========================================================================
# (a) ordine dell'app non abbinato -> annullato, poi la copertura
# ===========================================================================
def test_a_ordine_dell_app_appeso_si_annulla_poi_si_copre_e_l_esito_lo_dice():
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), mercato=m)
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    # leggi, annulla SOLO quell'ordine su QUEL mercato, rileggi; poi la copertura
    assert conto.metodi() == [LIST, CANCEL, LIST]
    par = conto.chiamate[1][1]
    assert par["marketId"] == MO and par["instructions"] == [{"betId": "H1"}]
    assert conto.piazzati_all_annullo == 0, "copertura piazzata PRIMA dell'annullo"
    # la copertura e' quella del sito (W 10, L -5 -> LAY 15/2,5 = 6,00)
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    res = r["result"]
    assert res["annullati_app"] == [{
        "bet_id": "H1", "side": "lay", "price": 2.6, "non_abbinato": 6.0,
        "size_annullata": 6.0, "esito": "annullato", "errore": None}]
    assert res["detail"].startswith(
        "annullo automatico ordine dell'app: H1 LAY @2.60 (6.00 non abbinato) "
        "annullato 6.00; esposizione riletta dal conto; LAY 6.00")
    assert (res["conto"]["w"], res["conto"]["l"]) == (10.0, -5.0)
    assert sorted(res["conto"]["fuori_bot"]) == ["H1", "S1"]


def test_a_la_risposta_del_finto_e_quella_della_libreria_vera():
    """La risposta di ``cancelOrders`` del finto si costruisce con la classe VERA
    ``CancelOrders`` di betfairlightweight (chiavi e tipi di Betfair)."""
    m = mercato_mo(back=2.48, lay=2.5)
    for modo in ("ok", ("abbina", 2.0), "abbinato_tutto", "rifiuta"):
        conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), annullo=modo)
        esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
        (risposta,) = conto.risposte_annullo
        co = CancelOrders(elapsed_time=0.01, **risposta)
        rep = co.cancel_instruction_reports[0]
        assert rep.instruction.bet_id == "H1"
        assert co.market_id == MO and rep.status in ("SUCCESS", "FAILURE")


# ===========================================================================
# (b) annullo fallito -> nessuna copertura, esito col motivo
# ===========================================================================
@pytest.mark.parametrize("modo,motivo", [
    ("rifiuta", "annullo FALLITO: cancelOrders FAILURE: ERROR_IN_ORDER"),
    ("rete", "annullo FALLITO: cancelOrders KO: RuntimeError: timeout su cancelOrders"),
    ("muto", "(6.00 non abbinato) annullato 6.00"),
])
def test_b_annullo_fallito_nessuna_copertura_e_il_motivo(modo, motivo):
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), annullo=modo)
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error"
    assert piazzati(m) == [], "copertura piazzata con l'ordine dell'app ancora vivo"
    assert conto.metodi() == [LIST, CANCEL, LIST]
    err = r["error"]
    assert err.startswith("greenup fuori_bot: ordine dell'app H1 LAY ancora non abbinato "
                          "(6.0) dopo l'annullo: nessuna copertura; annullo automatico")
    assert motivo in err
    assert len(err) < 300, "il motivo non deve essere troncato"


def test_b_annullo_riuscito_ma_conto_non_rileggibile_nessuna_copertura():
    """Mai una copertura su un'esposizione VECCHIA: se dopo l'annullo il conto non si
    rilegge, nessun ordine; l'errore dice anche dell'annullo gia' fatto."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), esplode_dopo_annullo=True)
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert conto.metodi() == [LIST, CANCEL, LIST]
    assert r["error"].startswith("annullo automatico ordine dell'app: H1 LAY @2.60 "
                                 "(6.00 non abbinato) annullato 6.00")
    assert "conto non leggibile" in r["error"]


# ===========================================================================
# (c) abbinato in parte (o in tutto) durante l'annullo -> esposizione riletta
# ===========================================================================
def test_c_abbinato_in_parte_durante_l_annullo_copertura_sulla_parte_vera():
    """L'app aveva LAY 6 @2,5 appesa; durante l'annullo se ne abbinano 2 @2,5 e si
    annullano i 4 restanti. Esposizione VERA: sito (W 10, L -5) + app LAY 2 @2,5
    (W -3, L +2) = W 7, L -3 -> LAY 10/2,5 = 4,00 (non 6,00 della lettura vecchia)."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(prezzo_app=2.5),
                            annullo=("abbina", 2.0))
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == [("LAY", 2.5, 4.0)]
    res = r["result"]
    assert (res["conto"]["w"], res["conto"]["l"]) == (7.0, -3.0)
    assert res["annullati_app"][0]["size_annullata"] == 4.0
    assert res["annullati_app"][0]["esito"] == "annullato"
    assert res["detail"].startswith(
        "annullo automatico ordine dell'app: H1 LAY @2.50 (6.00 non abbinato) "
        "annullato 4.00, 2.00 abbinato nel frattempo; esposizione riletta dal conto")


def test_c_abbinato_tutto_prima_dell_annullo_posizione_piatta_nessun_ordine():
    """L'app LAY 6 @2,5 si e' abbinata tutta prima dell'annullo (Betfair:
    BET_TAKEN_OR_LAPSED). Riletto il conto, la posizione e' gia' piatta (W = L = 1):
    nessuna seconda copertura, e l'esito dice dell'annullo non riuscito."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(prezzo_app=2.5),
                            annullo="abbinato_tutto")
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert piazzati(m) == []
    res = r["result"]
    assert (res["conto"]["w"], res["conto"]["l"]) == (1.0, 1.0)
    assert res["annullati_app"][0]["esito"] == "fallito"
    assert "BET_TAKEN_OR_LAPSED" in res["annullati_app"][0]["errore"]
    assert res["detail"].startswith(
        "annullo automatico ordine dell'app: H1 LAY @2.50 (6.00 non abbinato) annullo "
        "FALLITO: cancelOrders FAILURE: BET_TAKEN_OR_LAPSED; esposizione riletta dal "
        "conto; esposizione fuori bot gia' piatta")


def test_c_annullo_fatto_poi_il_mercato_si_sospende_l_errore_dice_dell_annullo():
    """Annullo riuscito, ma alla rilettura il book non ha prezzi (mercato sospeso):
    nessuna copertura e l'errore dice, IN TESTA, che l'ordine dell'app e' gia' stato
    annullato (l'utente deve saperlo: il suo ordine non e' piu' sul mercato)."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), mercato=m,
                            sospendi_dopo_annullo=True)
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error" and piazzati(m) == []
    assert r["error"].startswith("annullo automatico ordine dell'app: H1 LAY @2.60 "
                                 "(6.00 non abbinato) annullato 6.00; esposizione "
                                 "riletta dal conto; greenup fuori_bot NON eseguibile")


def test_c_annullo_fatto_poi_la_copertura_e_rifiutata_l_errore_dice_dell_annullo():
    """Annullo riuscito, poi il piazzamento della copertura e' RIFIUTATO: la testa
    dell'errore resta quella di sempre (codici, ``post_place:``), l'annullo e' detto
    IN CODA e il tipo dell'eccezione non cambia."""
    m = mercato_mo(back=2.48, lay=2.5)
    m.place_order = lambda order, **kw: False
    conto = ContoConAnnullo(sito_back_e_app_lay_appesa(), mercato=m)
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error"
    assert conto.metodi() == [LIST, CANCEL, LIST]
    assert r["error"].startswith("greenup fuori_bot: place RIFIUTATO")
    assert r["error"].endswith("[prima: annullo automatico ordini dell'app H1]")


def test_c_annullo_fatto_poi_la_copertura_chiuderebbe_mike_rifiuto_che_lo_dice():
    """Il caso del W2 "la copertura chiuderebbe Mike" (sito LAY Over 10 @3, Mike BACK
    Under 10) con in piu' un LAY Under dell'app appeso sul lato della copertura:
    l'ordine dell'app si annulla, la rilettura porta allo stesso rifiuto di prima
    ("CHIUSA DALL'UTENTE", nessun ordine) e l'errore dice IN TESTA dell'annullo."""
    m = mercato_ou(lay_under=1.50, back_under=1.49)
    conto = ContoConAnnullo([MIKE_BACK, ordine("S1", "LAY", 10.0, 3.0, sel=OVER),
                             ordine("H1", "LAY", 0.0, 1.55, csr="live", cor="9f1c2-77",
                                    residuo=4.0, sel=UNDER, market=MKT)])
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(sel=UNDER))
    assert r["status"] == "error" and piazzati(m) == []
    assert conto.metodi() == [LIST, CANCEL, LIST]
    assert r["error"].startswith("annullo automatico ordine dell'app: H1 LAY @1.55 "
                                 "(4.00 non abbinato) annullato 4.00")
    assert "CHIUSA DALL'UTENTE" in r["error"]


def test_senza_annullo_l_errore_del_piazzamento_e_quello_di_sempre():
    m = mercato_mo(back=2.48, lay=2.5)
    m.place_order = lambda order, **kw: False
    conto = ContoConAnnullo([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "error"
    assert r["error"].startswith("greenup fuori_bot: place RIFIUTATO")
    assert "annullo" not in r["error"]


# ===========================================================================
# (d) ordine di un ALTRO BOT non abbinato -> non si tocca (come prima)
# ===========================================================================
def test_d_ordini_non_abbinati_degli_altri_bot_non_si_toccano():
    """Sul lato della copertura: Omega dalla CODA del runner (csr 'live', bet_id in
    omega_trades) e Mike REST, entrambi non abbinati. Non sono fuori bot: nessun
    ``cancelOrders``, la copertura parte come prima."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo([
        ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
        ordine("O1", "LAY", 0.0, 2.6, csr="live", cor="abc-1", residuo=6.0,
               market=MO, sel=HOME),
        ordine("M1", "LAY", 0.0, 2.6, csr="mike", cor="mike-t1", residuo=4.0,
               market=MO, sel=HOME),
    ])
    sb = Sb(omega_trades=[{"id": 7, "bet_id": "O1", "mode": "live"}],
            betfair_live_orders=[{"bet_id": "O1", "mode": "live", "source": "runner"}])
    r = esegui(sb, framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert CANCEL not in conto.metodi()
    assert conto.metodi() == [LIST]
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    assert "annullati_app" not in r["result"]
    motivi = {b["bet_id"]: b["motivo"] for b in r["result"]["conto"]["bot"]}
    assert motivi == {"O1": "tabella:omega_trades", "M1": "strategia:mike"}


# ===========================================================================
# niente ordine dell'app appeso sul lato della copertura -> tutto come prima
# ===========================================================================
@pytest.mark.parametrize("altro", [
    # ordine del SITO appeso sul lato della copertura: non si annulla, non ferma
    ordine("S2", "LAY", 0.0, 2.6, residuo=3.0, market=MO, sel=HOME),
    # ordine dell'APP appeso sul lato OPPOSTO: non e' una copertura, non si tocca
    ordine("H2", "BACK", 0.0, 3.2, csr="live", cor="9f1c2-78", residuo=3.0,
           market=MO, sel=HOME),
])
def test_senza_ordini_dell_app_sul_lato_della_copertura_nessun_annullo(altro):
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo([ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
                             dict(altro)])
    r = esegui(Sb(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert conto.metodi() == [LIST]
    assert piazzati(m) == [("LAY", 2.5, 6.0)]
    assert "annullati_app" not in r["result"]
    assert not r["result"]["detail"].startswith("annullo")


def test_posizione_piatta_con_ordine_dell_app_appeso_nessun_annullo():
    """Nessuna copertura da fare (posizione gia' piatta): l'ordine dell'app appeso
    non e' d'intralcio a niente e resta dov'e'."""
    m = mercato_mo(back=2.48, lay=2.5)
    conto = ContoConAnnullo([
        ordine("S1", "BACK", 5.0, 3.0, market=MO, sel=HOME),
        ordine("H1", "LAY", 6.0, 2.5, csr="live", cor="9f1c2-77", residuo=3.0,
               market=MO, sel=HOME),
    ])
    r = esegui(sb_con_app(), framework(m, conto), riga_greenup(market=MO, sel=HOME))
    assert r["status"] == "done", r.get("error")
    assert conto.metodi() == [LIST] and piazzati(m) == []
    assert "gia' piatta" in r["result"]["detail"]


# ===========================================================================
# guardie dell'annullo (logica pura)
# ===========================================================================
class _BettingSpia:
    def __init__(self) -> None:
        self.chiamate: List[Dict[str, Any]] = []

    def cancel_orders(self, **kw: Any) -> Dict[str, Any]:
        self.chiamate.append(kw)
        return {"status": "SUCCESS", "instructionReports": []}


def _client_spia() -> Any:
    from types import SimpleNamespace

    spia = _BettingSpia()
    return SimpleNamespace(betting_client=SimpleNamespace(betting=spia)), spia


@pytest.mark.parametrize("market_id,bet_id", [("", "H1"), ("1.100", ""), (None, "H1")])
def test_mai_cancel_orders_senza_mercato_o_senza_bet_id(market_id, bet_id):
    """MONEY-CRITICAL: ``cancelOrders`` senza ``betId`` annulla TUTTO il mercato
    (anche i bot), senza ``marketId`` tutto il CONTO. Mai una chiamata cosi'."""
    client, spia = _client_spia()
    appese = [{"betId": bet_id, "side": "LAY", "sizeRemaining": 6.0,
               "priceSize": {"price": 2.6, "size": 6.0}}]
    out = wk._efb_annulla_app(client, market_id, appese)
    assert spia.chiamate == []
    assert out[0]["esito"] == "fallito" and "nessun annullo" in out[0]["errore"]


def test_esito_senza_report_per_l_ordine_e_un_fallimento():
    client, spia = _client_spia()
    appese = [{"betId": "H1", "side": "LAY", "sizeRemaining": 6.0,
               "priceSize": {"price": 2.6, "size": 6.0}}]
    out = wk._efb_annulla_app(client, "1.100", appese)
    assert spia.chiamate == [{"market_id": "1.100", "instructions": [{"betId": "H1"}],
                              "lightweight": True}]
    assert out[0]["esito"] == "fallito"
    assert out[0]["errore"] == "cancelOrders: nessun esito per l'ordine"
