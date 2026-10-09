"""W1-C2 - terza verifica del coordinatore (09/10/2026): replaceOrders.

L'ordine NUOVO nato da un replace eredita autore e provvisorieta' dell'ordine
SOSTITUITO (parita' col ladder di oggi: un ordine dell'utente spostato resta
suo e comandabile). Il legame si prende dalle FONTI VERE, costruite qui con le
funzioni di produzione:

* calcio: la riga di ``betfair_live_order_requests`` del replace porta in
  ``result.bet_id`` il bet_id VECCHIO (``live_order_worker._do_replace``: il
  ``_result`` e' preso sull'ordine sostituito, il rimpiazzo di flumine e'
  asincrono); il legame col NUOVO e' lo specchio ``betfair_live_orders``
  (``LiveTradingStrategy._order_row``): il rimpiazzo di flumine
  (``Trade.create_order_replacement``) eredita il ``context``, quindi la sua
  riga porta ``client_order_ref = awlq<origine>`` e ``request_id = origine``;
* tennis: la riga di ``tennis_live_order_queue`` del replace (``payload.bet_id``
  vecchio, ``result.customer_order_ref`` del comando) e la riga
  ``tennis_live_orders`` del rimpiazzo scritta sotto lo stesso ref
  (``tennis_live_order_worker._do_replace`` traccia il trade);
* tabelle dei bot: il bot scrive il bet_id NUOVO (``omega_market`` place-and-trim:
  ``PlaceResult.bet_id = nuovo_bet``): e' prova propria del nuovo;
* stream: lo stesso customerOrderRef sul rimpiazzo (prova in piu', da provare
  nell'ombra).
ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from flumine import BaseStrategy
from flumine.order.ordertype import LimitOrder

from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini import libro_conto as L
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, HOME, MKT, Registro, client_supabase,
                                                       dal_conto, ordine_json)
from Betfair.nucleo.ordini.tests.test_c2_revisione2 import _riga_locale

EVENTO = "35000001"
COR = "a1b2c3d4e5f60-1"          # il customerOrderRef che flumine manda (name_hash + sep + id)


# ------------------------------------------------------------------ fonti vere
def _ordine_calcio(rid: int, bet_id: str, prezzo: float = 2.0) -> Any:
    """L'ordine flumine come lo crea ``live_order_build._create_order`` per la
    richiesta ``rid`` (ref interno ``awlq<rid>`` in context e notes)."""
    from Betfair.stream import live_order_worker as low
    from Betfair.stream.live_order_build import _create_order

    s = BaseStrategy(market_filter={}, name="LiveTradingStrategy")
    o = _create_order(s, MKT, HOME, 0.0, "BACK",
                      LimitOrder(price=prezzo, size=5.0, persistence_type="PERSIST"),
                      low._cust_ref(rid))
    o.bet_id = bet_id
    return o


def _rimpiazzo(vecchio: Any, bet_id: str, prezzo: float) -> Any:
    """Il rimpiazzo che flumine crea dopo un replaceOrders riuscito
    (``BetfairExecution.execute_replace`` -> ``Trade.create_order_replacement``)."""
    n = vecchio.trade.create_order_replacement(vecchio, prezzo, vecchio.order_type.size,
                                               datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    n.bet_id = bet_id
    return n


def _specchio_calcio(order: Any) -> Dict[str, Any]:
    """La riga di ``betfair_live_orders`` (``LiveTradingStrategy._order_row``)."""
    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    riga = LiveTradingStrategy._order_row(SimpleNamespace(mode="live"), order,
                                          event_id=EVENTO, market_id=MKT)
    assert riga is not None
    return riga


def _riga_coda_db(rid: int, client_ref: str, params: Dict[str, Any], order: Any) -> Dict[str, Any]:
    """Una riga della coda DB scritta da un bot (colonne della tabella) dopo
    ``live_order_worker._write_done`` (corpo VERO dell'UPDATE)."""
    from Betfair.stream import live_order_worker as low

    riga = {"id": rid, "client_ref": client_ref, "action": "place", "mode": "live",
            "market_id": MKT, "selection_id": HOME, "handicap": 0.0, "side": "back",
            "order_type": "LIMIT", "price": 2.0, "size": 5.0, "persistence": "PERSIST",
            "bet_id": None, "params": params}
    risultato = low._result(ok=True, action="place", mode="live", request_row=riga,
                            cust_ref=low._cust_ref(rid), order=order)
    reg = Registro(lambda req: [{"id": rid}])
    low._write_done(client_supabase(reg), rid, risultato)
    patch = [c for m, u, c in reg.richieste if m == "PATCH" and "betfair_live_order_requests" in u]
    assert patch and patch[0]["status"] == "done"
    return dict(riga, **patch[0])


def _conto(bet_id: str, *, residuo: float = 5.0, annullato: float = 0.0, cor: Optional[str] = COR,
           csr: str = "live", prezzo: float = 2.0, side: str = "BACK", ms: int = 1000) -> Any:
    return dal_conto(ordine_json(bet_id, side, 0.0, prezzo, residuo=residuo, annullato=annullato,
                                 csr=csr, cor=cor), ricevuto_ms=ms)


def _libro() -> L.LibroConto:
    lib = L.LibroConto()
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=1)
    return lib


# ------------------------------------------------------- 0. la grafia vera delle fonti
def test_fonti_calcio_il_replace_porta_il_vecchio_lo_specchio_lega_il_nuovo():
    vecchio = _ordine_calcio(40, "100")
    nuovo = _rimpiazzo(vecchio, "101", 2.2)
    replace = _riga_locale("replace", "100", bet_id_comando="100", rid=41)
    # la riga del replace NON contiene il bet_id nuovo: result.bet_id e' il vecchio
    assert replace["action"] == "replace" and replace["bet_id"] == "100"
    assert replace["result"]["bet_id"] == "100"
    sv, sn = _specchio_calcio(vecchio), _specchio_calcio(nuovo)
    assert (sv["bet_id"], sv["client_order_ref"], sv["request_id"]) == ("100", "awlq40", 40)
    assert (sn["bet_id"], sn["client_order_ref"], sn["request_id"]) == ("101", "awlq40", 40)
    assert A.origine_della_riga_specchio(sn) == 40
    assert A.origine_della_riga_specchio({"client_order_ref": "awlq40"}) == 40
    assert A.origine_della_riga_specchio({"client_order_ref": "awtq40"}) is None
    assert A.origine_della_riga_specchio({"request_id": "x"}) is None


# -------------------------------------------- 1. replace di un ordine dell'utente
def test_replace_dell_utente_dallo_specchio_il_nuovo_e_desktop_e_comandabile():
    origine = _riga_locale("place", "100", rid=40)
    nuovo = _rimpiazzo(_ordine_calcio(40, "100"), "101", 2.2)
    ind = A.indizi_da_origine(_specchio_calcio(nuovo), origine)
    assert ind == (A.Indizio("utente", "coda:local40"),)
    lib = _libro()
    lib.ricevi_live(_conto("101"))
    assert lib.ordine("101", "live").autore == "sconosciuto"            # ref manuale: provvisorio
    o = lib.aggiungi_indizi("101", ind)
    assert (o.autore, L.comandi_ammessi(o)) == ("desktop", ("annulla", "sposta"))
    # la richiesta di un'ALTRA origine non prova niente
    assert A.indizi_da_origine(_specchio_calcio(nuovo), _riga_locale("place", "100", rid=39)) == ()
    assert A.indizi_da_origine({"client_order_ref": "x"}, origine) == ()


def test_replace_dell_utente_nel_libro_il_nuovo_eredita():
    origine = _riga_locale("place", "100", rid=40)
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", A.indizi_da_riga_coda(origine, bet_id="100"))
    assert lib.ordine("100", "live").autore == "desktop"
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=2))   # sostituito: annullato
    lib.ricevi_live(_conto("101", cor=None, ms=3))                     # niente ref sullo stream
    assert lib.ordine("101", "live").autore == "sconosciuto"
    o = lib.lega_sostituzione("100", "101")
    assert (o.autore, L.comandi_ammessi(o)) == ("desktop", ("annulla", "sposta"))
    assert lib.attribuzione("101", "live").motivo == "sostituisce:100"
    assert lib.stato()["conti"]["legami"] == 1
    assert lib.lega_sostituzione("100", "101").autore == "desktop"     # idempotente
    assert lib.stato()["conti"]["legami"] == 1


def test_legame_prima_dell_ordine_nuovo():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    assert lib.lega_sostituzione("100", "101") is None                  # il nuovo non c'e' ancora
    lib.ricevi_live(_conto("101", cor=None, ms=2))
    assert lib.ordine("101", "live").autore == "desktop"


def test_sostituito_arriva_dopo_il_nuovo():
    lib = _libro()
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=2))
    lib.lega_sostituzione("100", "101")
    # senza l'ordine sostituito valgono i suoi indizi (riavvio: annullato, non torna)
    assert lib.ordine("101", "live").autore == "desktop"
    lib2 = _libro()
    lib2.ricevi_live(_conto("101", cor=None, ms=2))
    lib2.lega_sostituzione("100", "101")
    assert lib2.attribuzione("101", "live").provvisoria                 # niente da ereditare
    lib2.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, csr="mike", cor="mike-t4", ms=1))
    assert lib2.ordine("101", "live").autore == "mike"                 # arriva il sostituito: eredita


def test_legami_non_ammessi():
    lib = _libro()
    with pytest.raises(ValueError):
        lib.lega_sostituzione("1", "2", modo="prova")
    assert lib.lega_sostituzione("1", "1") is None
    assert lib.lega_sostituzione("", "2") is None
    assert lib.stato()["conti"]["legami"] == 0


# ------------------------------------------------- 2. replace di un ordine di Omega
def test_replace_di_un_ordine_di_omega_il_nuovo_e_omega():
    vecchio = _ordine_calcio(50, "200")
    origine = _riga_coda_db(50, "omega-t9", {"comando": {"attore": "omega"}}, vecchio)
    assert origine["bet_id"] == "200" and origine["client_ref"] == "omega-t9"
    # l'utente sposta l'ordine di Omega dal ladder: riga del replace dell'utente
    replace = _riga_locale("replace", "200", bet_id_comando="200", rid=51)
    assert A.indizi_da_riga_coda(replace) == ()                         # non e' prova
    nuovo = _rimpiazzo(vecchio, "201", 2.4)
    ind = A.indizi_da_origine(_specchio_calcio(nuovo), origine)
    assert ind and A.attribuisci(_conto("201"), ind).autore == "omega"
    # nel libro: il legame fa omega il nuovo, senza comandi
    lib = _libro()
    lib.ricevi_live(_conto("200", ms=1))
    lib.aggiungi_indizi("200", A.indizi_da_riga_coda(origine, bet_id="200"))
    assert lib.ordine("200", "live").autore == "omega"
    lib.ricevi_live(_conto("201", cor=None, ms=2))
    o = lib.lega_sostituzione("200", "201")
    assert (o.autore, L.comandi_ammessi(o)) == ("omega", ())


def test_omega_riprezza_da_solo_la_sua_tabella_e_prova_del_nuovo():
    """Il place-and-trim di Omega (replaceOrders REST) scrive in ``omega_trades``
    il bet_id NUOVO: prova propria, coerente col sostituito."""
    lib = _libro()
    lib.ricevi_live(_conto("300", csr="omega", cor="omega-t3", residuo=0.0, annullato=5.0, ms=1))
    lib.ricevi_live(_conto("301", csr="omega", cor="omega-t3", ms=2))
    lib.aggiungi_indizi("301", [A.indizio_da_riga_bot("omega_trades", {"bet_id": "301"})])
    lib.lega_sostituzione("300", "301")
    a = lib.attribuzione("301", "live")
    assert (a.autore, a.conflitto) == ("omega", None) and a.motivo == "tabella:omega_trades"


def test_eredita_prova_propria_di_un_bot_diverso_resta_col_conflitto():
    sost = A.Attribuzione("desktop", "utente:x", "indizio")
    propria = A.Attribuzione("omega", "tabella:omega_trades", "indizio")
    a = A.eredita(sost, "100", propria)
    assert a.autore == "omega" and a.conflitto == "sostituisce 100 di desktop"
    dich = A.Attribuzione("mike", "attore:mike", "dichiarato")
    assert A.eredita(sost, "100", dich) is dich
    rif = A.Attribuzione("sconosciuto", "strategia_manuale_da_confermare:live", "riferimenti",
                         provvisoria=True)
    e = A.eredita(sost, "100", rif)
    assert (e.autore, e.motivo, e.fonte, e.provvisoria) == ("desktop", "sostituisce:100",
                                                           "indizio", False)
    # anche un ref di bot del nuovo cede al sostituito: i riferimenti li porta Betfair
    rif_bot = A.Attribuzione("mike", "ref:mike-t1", "riferimenti")
    assert A.eredita(sost, "100", rif_bot).autore == "desktop"


# ------------------------------------------------- 3. replace di un provvisorio
def test_replace_di_un_provvisorio_resta_provvisorio():
    lib = _libro()
    lib.ricevi_live(_conto("400", ms=1))
    assert lib.attribuzione("400", "live").provvisoria
    lib.ricevi_live(_conto("401", cor=None, ms=2))
    o = lib.lega_sostituzione("400", "401")
    a = lib.attribuzione("401", "live")
    assert (o.autore, a.provvisoria, L.comandi_ammessi(o)) == ("sconosciuto", True, ())
    assert a.motivo == "sostituisce:400"
    # arriva la prova sul sostituito: il nuovo la segue
    o2 = lib.aggiungi_indizi("400", [A.indizio_ack_desktop("400")])
    assert o2.autore == "desktop"
    assert lib.ordine("401", "live").autore == "desktop"
    assert not lib.attribuzione("401", "live").provvisoria


def test_eredita_conserva_la_provvisorieta_e_il_conflitto():
    sost = A.Attribuzione("sconosciuto", "x", "riferimenti", "c1", provvisoria=True)
    e = A.eredita(sost, "9", A.Attribuzione("sconosciuto", "y", "riferimenti", provvisoria=True))
    assert (e.provvisoria, e.conflitto) == (True, "c1")


# ------------------------------------------------------ 4. catena di due replace
def test_catena_di_due_replace_specchio():
    origine = _riga_locale("place", "100", rid=40)
    v = _ordine_calcio(40, "100")
    n1 = _rimpiazzo(v, "101", 2.2)
    n2 = _rimpiazzo(n1, "102", 2.4)
    s2 = _specchio_calcio(n2)
    assert (s2["client_order_ref"], s2["request_id"]) == ("awlq40", 40)
    assert A.indizi_da_origine(s2, origine) == (A.Indizio("utente", "coda:local40"),)


def test_catena_di_due_replace_nel_libro():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.ricevi_live(_conto("101", cor=None, ms=2))
    lib.ricevi_live(_conto("102", cor=None, ms=3))
    lib.lega_sostituzione("101", "102")
    lib.lega_sostituzione("100", "101")
    assert lib.attribuzione("102", "live").provvisoria
    visti: List[str] = []
    lib.aggiungi_consumatore(lambda o: visti.append(o.bet_id))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])        # prova sulla radice
    assert [lib.ordine(b, "live").autore for b in ("100", "101", "102")] == ["desktop"] * 3
    assert lib.attribuzione("102", "live").motivo == "sostituisce:101"
    assert sorted(set(visti)) == ["100", "101", "102"]                 # avvisati tutti


def test_catena_dopo_un_riavvio_solo_l_ultimo_torna_dal_conto():
    """Riavvio: ritornano dal conto solo gli ordini vivi; i legami e gli indizi
    si rileggono dalle righe (aggancio del referto, par. 12)."""
    lib = _libro()
    lib.ricevi_live(_conto("102", cor=None, ms=3))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.lega_sostituzione("100", "101")
    lib.lega_sostituzione("101", "102")
    a = lib.attribuzione("102", "live")
    assert (a.autore, a.provvisoria, a.motivo) == ("desktop", False, "sostituisce:101")


def test_catena_ciclica_non_gira_all_infinito():
    lib = _libro()
    lib.ricevi_live(_conto("101", cor=None, ms=2))
    lib.lega_sostituzione("100", "101")
    lib.lega_sostituzione("101", "100")
    assert lib.attribuzione("101", "live").autore == "sconosciuto"
    # ciclo di tre legami gia' scritti quando arriva l'ordine (nessuna attribuzione nota)
    lib2 = _libro()
    lib2.lega_sostituzione("100", "101")
    lib2.lega_sostituzione("102", "100")
    lib2.lega_sostituzione("101", "102")
    lib2.ricevi_live(_conto("101", cor=None, ms=2))
    assert lib2.attribuzione("101", "live").autore == "sconosciuto"


# ------------------------------------------------------------------ 5. tennis
def _ordine_tennis(bet_id: str) -> Any:
    s = BaseStrategy(market_filter={}, name="TennisLiveStrategy")
    from flumine.order.trade import Trade

    t = Trade(market_id=MKT, selection_id=HOME, handicap=0.0, strategy=s)
    o = t.create_order(side="BACK", order_type=LimitOrder(price=2.0, size=5.0,
                                                          persistence_type="PERSIST"))
    o.bet_id = bet_id
    return o


def _riga_coda_tennis(sid: int, payload: Dict[str, Any], order: Any) -> Dict[str, Any]:
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow

    risultato = tlow._result(ok=True, action=str(payload["action"]), mode="live", cmd=payload,
                             cust_ref=f"awtq{sid}", order=order)
    return {"client_ref": f"local{sid}", "payload": payload, "status": "done",
            "result": risultato, "error": None, "processed_at": "2026-10-09T12:00:00+00:00"}


def test_tennis_replace_dell_utente_legame_dalla_coda_e_dallo_specchio():
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow

    vecchio = _ordine_tennis("700")
    place = _riga_coda_tennis(7, {"action": "place", "mode": "live", "market_id": MKT,
                                  "selection_id": HOME, "side": "back", "price": 2.0,
                                  "size": 5.0}, vecchio)
    cmd = {"action": "replace", "mode": "live", "market_id": MKT, "bet_id": "700",
           "new_price": 2.2}
    replace = _riga_coda_tennis(8, cmd, vecchio)                         # _result sul VECCHIO
    assert replace["result"]["bet_id"] == "700"
    assert replace["result"]["customer_order_ref"] == "awtq8"
    nuovo = vecchio.trade.create_order_replacement(vecchio, 2.2, 5.0,
                                                   datetime(2026, 10, 9, tzinfo=timezone.utc))
    nuovo.bet_id = "701"
    specchio = tlow.riga_specchio("live", EVENTO, "awtq8", nuovo, cmd,
                                  status_override="EXECUTABLE")
    assert (specchio["bet_id"], specchio["client_order_ref"]) == ("701", "awtq8")
    assert A.legame_da_replace_tennis(replace, specchio) == ("700", "701")
    # non e' un replace, ref diverso, stesso bet_id: niente legame
    assert A.legame_da_replace_tennis(place, specchio) is None
    assert A.legame_da_replace_tennis(replace, dict(specchio, client_order_ref="awtq9")) is None
    assert A.legame_da_replace_tennis(replace, dict(specchio, bet_id="700")) is None
    assert A.legame_da_replace_tennis(dict(replace, result=dict(replace["result"],
                                                                customer_order_ref=None)),
                                      specchio) is None
    lib = _libro()
    lib.ricevi_live(_conto("701", cor=None, csr="tennis", ms=2))
    lib.aggiungi_indizi("700", A.indizi_da_riga_tennis(place, bet_id="700"))
    o = lib.lega_sostituzione(*A.legame_da_replace_tennis(replace, specchio))
    assert (o.autore, L.comandi_ammessi(o)) == ("desktop", ("annulla", "sposta"))


# ------------------------------------------------------ 6. stream (prova in piu')
def test_stream_stesso_ref_lega_il_rimpiazzo():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=2))
    lib.ricevi_live(_conto("101", ms=3))
    assert lib.ordine("101", "live").autore == "desktop"
    assert lib.stato()["conti"]["legami_dallo_stream"] == 1


def test_stream_il_rimpiazzo_arriva_prima_che_il_vecchio_sia_completo():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", ms=2))
    assert lib.ordine("101", "live").autore == "sconosciuto"           # il vecchio e' vivo
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=3))
    assert lib.ordine("101", "live").autore == "desktop"
    assert lib.stato()["conti"]["legami_dallo_stream"] == 1
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=4))   # di nuovo: niente doppio
    assert lib.stato()["conti"]["legami_dallo_stream"] == 1


@pytest.mark.parametrize("nuovo", [
    dict(cor="altro-1"),                       # ref diverso
    dict(side="LAY"),                          # lato diverso
    dict(cor=None),                            # senza ref
])
def test_stream_senza_legame(nuovo):
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=2))
    lib.ricevi_live(_conto("101", ms=3, **nuovo))
    assert lib.ordine("101", "live").autore == "sconosciuto"
    assert lib.stato()["conti"]["legami_dallo_stream"] == 0


def test_stream_selezione_diversa_e_vecchio_vivo_non_legano():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(dal_conto(ordine_json("101", "BACK", 0.0, 2.0, residuo=5.0, csr="live",
                                          cor=COR, sel=AWAY), ricevuto_ms=2))
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=3))
    assert lib.ordine("101", "live").autore == "sconosciuto"
    lib.ricevi_live(_conto("102", ms=4))                                # vivo il 101? no: altra sel
    assert lib.ordine("102", "live").autore == "desktop"


def test_stream_il_verso_lo_dice_il_bet_id():
    """Il bet_id del rimpiazzo e' maggiore: se arriva prima il completo
    MAGGIORE, non diventa lui il sostituito del vivo minore."""
    lib = _libro()
    lib.ricevi_live(_conto("101", residuo=0.0, annullato=5.0, ms=1))
    lib.aggiungi_indizi("101", [A.indizio_ack_desktop("101")])
    lib.ricevi_live(_conto("100", ms=2))
    assert lib.ordine("100", "live").autore == "sconosciuto"
    assert lib.stato()["conti"]["legami_dallo_stream"] == 0


def test_stream_bet_id_non_numerico_non_lega():
    lib = _libro()
    lib.ricevi_live(_conto("x100", residuo=0.0, annullato=5.0, ms=1))
    lib.aggiungi_indizi("x100", [A.indizio_ack_desktop("x100")])
    lib.ricevi_live(_conto("101", ms=2))
    lib.ricevi_live(_conto("y102", ms=3))
    assert lib.stato()["conti"]["legami_dallo_stream"] == 0


def test_stream_un_messaggio_rifiutato_non_lega():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=5))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", ms=6))
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=1))    # piu' vecchio: scartato
    assert lib.stato()["conti"]["legami_dallo_stream"] == 0
    assert lib.ordine("101", "live").autore == "sconosciuto"


# ------------------------------------------------------ 7. tetto e dimenticanza
def test_il_sostituito_riassunto_dal_tetto_si_eredita():
    lib = L.LibroConto(max_ordini=1)
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=1)
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=1))
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=2))                      # il 100 va riassunto
    assert lib.ordine("100", "live") is None
    o = lib.lega_sostituzione("100", "101")
    assert o.autore == "desktop"


def test_dimentica_mercato_toglie_i_legami():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.ricevi_live(_conto("101", cor=None, ms=2))
    lib.lega_sostituzione("100", "101")
    lib.dimentica_mercato(MKT)
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=3))
    assert lib.ordine("101", "live").autore == "sconosciuto"


def test_dimentica_mercato_toglie_i_legami_dei_riassunti():
    lib = L.LibroConto(max_ordini=1)
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=1)
    lib.ricevi_live(_conto("100", residuo=0.0, annullato=5.0, ms=1))
    lib.ricevi_live(_conto("101", residuo=0.0, annullato=5.0, cor=None, ms=2))
    lib.lega_sostituzione("100", "101")
    lib.ricevi_live(_conto("102", cor=None, ms=3))                      # 100 e 101 riassunti
    lib.dimentica_mercato(MKT)
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=4))
    assert lib.ordine("101", "live").autore == "sconosciuto"


def test_dimentica_il_sostituito_toglie_il_legame_verso_il_nuovo_assente():
    lib = _libro()
    lib.ricevi_live(_conto("100", ms=1))
    lib.lega_sostituzione("100", "101")                                 # il 101 non c'e' ancora
    lib.dimentica_mercato(MKT)
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=3))
    assert lib.ordine("101", "live").autore == "sconosciuto"


def test_dimentica_il_nuovo_toglie_il_suo_legame():
    lib = _libro()
    lib.ricevi_live(_conto("101", cor=None, ms=1))
    lib.lega_sostituzione("100", "101")                                 # il 100 non c'e'
    lib.dimentica_mercato(MKT)
    lib.aggiungi_indizi("100", [A.indizio_ack_desktop("100")])
    lib.ricevi_live(_conto("101", cor=None, ms=3))
    assert lib.ordine("101", "live").autore == "sconosciuto"


def test_origine_dal_solo_request_id():
    """La colonna ``request_id`` basta (una SELECT che non legge il ref)."""
    assert A.origine_della_riga_specchio({"request_id": 40}) == 40
    assert A.origine_della_riga_specchio({"request_id": "40", "client_order_ref": "awlq7"}) == 40
    assert A.origine_della_riga_specchio({}) is None


def test_tennis_un_cancel_non_lega():
    vecchio = _ordine_tennis("700")
    cmd = {"action": "cancel", "mode": "live", "market_id": MKT, "bet_id": "700"}
    cancel = _riga_coda_tennis(8, cmd, vecchio)
    specchio = {"bet_id": "701", "client_order_ref": "awtq8"}
    assert A.legame_da_replace_tennis(cancel, specchio) is None
    assert A.legame_da_replace_tennis(dict(cancel, payload=dict(cmd, action="replace")),
                                      specchio) == ("700", "701")


def test_paper_non_eredita_dagli_indizi_live():
    """La prova paper dichiara l'attore: il legame non lo cambia."""
    lib = _libro()
    lib.ricevi_prova(L.OrdineInProva(_conto("101", cor=None), "mike"))
    lib.lega_sostituzione("100", "101", modo="paper")
    assert lib.ordine("101", "paper").autore == "mike"
