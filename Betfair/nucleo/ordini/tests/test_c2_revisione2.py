"""W1-C2 - correzioni dopo la SECONDA revisione (09/10/2026).

1. G1: le righe della coda nella GRAFIA VERA, prodotte dalle funzioni di oggi:
   ``live_order_worker._record_local_request`` (client supabase VERO su
   MockTransport: il corpo dell'INSERT e' la riga), ``live_order_worker._result``
   e ``tennis_live_order_worker._result`` con un ordine flumine VERO; place,
   cancel/replace dell'utente su un ordine di un bot, ritentativi ``ft`` con
   ``params.ft_parent``, coda tennis (``local<sid>``, ``cmd<id>``).
2. M2: un ordine riassunto dal tetto che rientra (seme, aggiornamento tardivo)
   non si conta due volte e conserva autore e indizi.
3. Mutanti del revisore R14 (prezzo del riassunto) e R18 (asiatico single line).
4. ``vincitori_ignoti``; 5. ``posizione_per_json``.
ASCII-only.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Sequence

import pytest
from flumine import BaseStrategy
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from Betfair.nucleo.ordini import attribuzione as A
from Betfair.nucleo.ordini import libro_conto as L
from Betfair.nucleo.ordini import pnl_mercato as P
from Betfair.nucleo.ordini.contratto import OrdineConto
from Betfair.nucleo.ordini.tests.test_c2_aiuti import (AWAY, HOME, MKT, Registro, client_supabase,
                                                       correnti, dal_conto, ordine_json)


def _ordine_flumine(bet_id: str) -> Any:
    s = BaseStrategy(market_filter={}, name="LiveTradingStrategy")
    t = Trade(market_id=MKT, selection_id=HOME, handicap=0.0, strategy=s)
    o = t.create_order(side="BACK", order_type=LimitOrder(price=2.0, size=5.0,
                                                          persistence_type="PERSIST"))
    o.bet_id = bet_id
    return o


def _riga_locale(azione: str, bet_id_risultato: str, bet_id_comando: Optional[str] = None,
                 rid: int = 5) -> Dict[str, Any]:
    """La riga che ``_record_local_request`` INSERISCE davvero (corpo del POST)."""
    from Betfair.stream import live_order_worker as low

    riga = {"id": rid, "action": azione, "market_id": MKT, "selection_id": HOME, "handicap": 0.0,
            "side": "back", "order_type": "LIMIT", "price": 2.0, "size": 5.0,
            "persistence": "PERSIST", "bet_id": bet_id_comando, "params": None}
    risultato = low._result(ok=True, action=azione, mode="live", request_row=riga,
                            cust_ref=low._cust_ref(rid), order=_ordine_flumine(bet_id_risultato))
    reg = Registro(lambda req: [{"id": 9000 + rid}])
    assert low._record_local_request(client_supabase(reg), riga,
                                     {"status": "done", "result": risultato}, "live") == 9000 + rid
    metodo, url, corpo = reg.richieste[-1]
    assert metodo == "POST" and url.endswith("/betfair_live_order_requests")
    return corpo


def _ordine_live(bet_id: str, csr: str = "live") -> Any:
    return dal_conto(ordine_json(bet_id, "BACK", 0.0, 2.0, residuo=5.0, csr=csr,
                                 cor="a1b2c3d4e5f60-1"))


# ------------------------------------------------------------------ 1. G1
def test_g1a_place_dal_ladder_riconosciuto_dal_result_della_riga_vera():
    corpo = _riga_locale("place", "900")
    assert corpo["client_ref"] == "local5" and corpo["bet_id"] is None   # la colonna e' NULL
    assert A.bet_id_della_riga(corpo) == "900"
    ind = A.indizi_da_riga_coda(corpo, bet_id="900")
    assert ind == (A.Indizio("utente", "coda:local5"),)
    a = A.attribuisci(_ordine_live("900"), ind)
    assert (a.autore, a.provvisoria) == ("desktop", False)
    assert A.indizi_da_riga_coda(corpo, bet_id="999") == ()            # riga di un altro ordine


def test_g1a_riga_della_coda_db_col_bet_id_in_colonna():
    """La coda DB (``_write_done``) scrive il bet_id in colonna E nel result."""
    riga = {"client_ref": "3f2a9c10-aaaa", "action": "place", "bet_id": "905",
            "params": {}, "result": {"ok": True, "bet_id": "905"}}
    assert A.indizi_da_riga_coda(riga, bet_id="905") == (A.Indizio("utente", "coda:3f2a9c10-aaaa"),)


@pytest.mark.parametrize("azione", ["cancel", "replace"])
def test_g1c_cancel_o_replace_dell_utente_su_un_ordine_di_un_bot_non_e_prova(azione):
    corpo = _riga_locale(azione, "902", bet_id_comando="902", rid=6)
    assert corpo["bet_id"] == "902" and corpo["action"] == azione
    assert A.indizi_da_riga_coda(corpo, bet_id="902") == ()
    assert A.indizi_da_riga_coda(corpo) == ()
    o = _ordine_live("902")
    # l'ordine e' di Omega dalla coda: resta di Omega anche con la riga dell'utente
    a = A.attribuisci(o, [A.Indizio("tabella", "omega_trades")]
                      + list(A.indizi_da_riga_coda(corpo, bet_id="902")))
    assert a.autore == "omega"
    assert A.attribuisci(o, A.indizi_da_riga_coda(corpo, bet_id="902")).provvisoria


def test_g1c_greenup_dell_utente_e_un_suo_ordine():
    corpo = _riga_locale("greenup", "906", rid=7)
    assert A.indizi_da_riga_coda(corpo, bet_id="906") == (A.Indizio("utente", "coda:local7"),)


def _riga_ft(genitore_id: int, bet_id: str) -> Dict[str, Any]:
    """Il ritentativo del follow-through come lo accoda ``live_order_worker``
    (``:1867-1877``: ``ft<rid>s<sel>r<n>``, azione ``greenup``, ``params.ft_parent``)."""
    return {"client_ref": f"ft{genitore_id}s{HOME}r1", "action": "greenup", "mode": "live",
            "market_id": MKT, "selection_id": HOME, "handicap": 0,
            "params": {"fraction": 1.0, "ft_parent": genitore_id, "ft_retry": 1},
            "bet_id": bet_id, "result": {"ok": True, "bet_id": bet_id}}


def test_g1d_ritentativo_ft_eredita_l_autore_del_genitore():
    ft = _riga_ft(12, "907")
    utente = {"id": 12, "client_ref": "local12", "action": "greenup", "params": None,
              "bet_id": None, "result": {"bet_id": "800"}}
    assert A.indizi_da_riga_coda(ft, bet_id="907", genitore=utente) == (
        A.Indizio("utente", "coda:local12"),)
    rischio = {"id": 12, "client_ref": "risk4s", "action": "greenup", "params": {}}
    assert A.indizi_da_riga_coda(ft, bet_id="907", genitore=rischio) == (
        A.Indizio("coda", "rischio:risk4s"),)
    assert A.indizi_da_riga_coda(ft, bet_id="907") == ()                      # genitore ignoto
    assert A.indizi_da_riga_coda(ft, bet_id="907", genitore=dict(utente, id=13)) == ()
    assert A.attribuisci(_ordine_live("907"), A.indizi_da_riga_coda(ft, bet_id="907")).provvisoria


def _riga_tennis(client_ref: str, payload: Dict[str, Any], bet_id: str) -> Dict[str, Any]:
    """La riga di ``tennis_live_order_queue`` come la scrive il worker tennis
    (``tennis_live_order_worker.py:1830``) con il ``_result`` VERO."""
    from Betfair.stream.tennis_live import tennis_live_order_worker as tlow

    risultato = tlow._result(ok=True, action=str(payload["action"]), mode="live", cmd=payload,
                             cust_ref="tlq1", order=_ordine_flumine(bet_id))
    return {"client_ref": client_ref, "payload": payload, "status": "done", "result": risultato,
            "error": risultato.get("error"), "processed_at": "2026-10-09T12:00:00+00:00"}


def test_g1b_coda_tennis_place_del_ladder_e_comando_di_un_bot():
    cmd = {"action": "place", "mode": "live", "market_id": MKT, "selection_id": HOME,
           "side": "back", "price": 2.0, "size": 5.0, "persistence": "PERSIST"}
    locale = _riga_tennis("local7", cmd, "910")
    assert A.indizi_da_riga_tennis(locale, bet_id="910") == (A.Indizio("utente", "coda:local7"),)
    a = A.attribuisci(_ordine_live("910", csr="tennis"), A.indizi_da_riga_tennis(locale, bet_id="910"))
    assert a.autore == "desktop"
    bot = _riga_tennis("cmd3", dict(cmd, comando={"attore": "tennis_pro"}), "911")
    assert A.indizi_da_riga_tennis(bot, bet_id="911") == (A.Indizio("coda", "coda_attore:tennis_pro"),)
    annullo = _riga_tennis("local8", dict(cmd, action="cancel", bet_id="911"), "911")
    assert A.indizi_da_riga_tennis(annullo, bet_id="911") == ()


def test_g1_result_come_stringa_json_e_rotto():
    riga = {"client_ref": "local1", "action": "place", "bet_id": None,
            "result": json.dumps({"bet_id": "920"})}
    assert A.bet_id_della_riga(riga) == "920"
    assert A.bet_id_della_riga(dict(riga, result="{rotto")) is None


# ------------------------------------------------------------------ 2. M2
def _tetto(prezzo: float) -> L.LibroConto:
    lib = L.LibroConto(max_ordini=2)
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=1)
    for k in range(1, 4):
        lib.ricevi_live(dal_conto(ordine_json(str(k), "BACK", 10.0, prezzo, csr="mike",
                                              cor=f"mike-t{k}"), ricevuto_ms=100 + k))
    return lib


class _Rest:
    def __init__(self, *ordini: dict) -> None:
        self.ordini = ordini

    def ordini_correnti(self, market_ids: Optional[Sequence[str]] = None) -> List[Any]:
        return correnti(*self.ordini)


def test_m2_riassunto_con_prezzo_diverso_da_due():
    """R14 del revisore: 3 back da 10 @ 3,0 -> se vince 60 (non 50)."""
    c = _tetto(3.0).calcolo_posizione(MKT, "live")
    assert c.posizione.se_vince == {HOME: 60.0, AWAY: -30.0} and "ordini_riassunti" in c.motivi


def test_m2_seme_dopo_il_tetto_non_raddoppia():
    """probe_m2 del revisore: dopo il riseme il P&L era 120 invece di 60."""
    lib = _tetto(3.0)
    tutti = [ordine_json(str(k), "BACK", 10.0, 3.0, csr="mike", cor=f"mike-t{k}") for k in range(1, 4)]
    lib.riconnesso(con_ripresa=False, correnti=_Rest(*tutti))
    c = lib.calcolo_posizione(MKT, "live")
    assert c.posizione.se_vince == {HOME: 60.0, AWAY: -30.0}
    assert c.posizione.abbinato_back[HOME] == 30.0
    assert lib.stato()["conti"]["riassunti_rientrati"] >= 1
    lib.riconnesso(con_ripresa=False, correnti=_Rest(*tutti))           # due volte: uguale
    assert lib.posizione(MKT, "live").se_vince == {HOME: 60.0, AWAY: -30.0}


def test_m2_aggiornamento_tardivo_di_un_riassunto_storna_e_conserva_l_autore():
    lib = L.LibroConto(max_ordini=1)
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS", vincitori=1)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 3.0, csr="live", cor="h-1"), 1))
    lib.aggiungi_indizi("1", [A.Indizio("tabella", "omega_trades")])      # Omega dalla coda
    lib.ricevi_live(dal_conto(ordine_json("2", "BACK", 10.0, 3.0, csr="mike", cor="mike-t2"), 2))
    assert lib.ordine("1", "live") is None                                # riassunto
    assert lib.posizione(MKT, "live").se_vince_per_autore["omega"][HOME] == 20.0
    tardivo = ordine_json("1", "BACK", 6.0, 3.0, csr="live", cor="h-1")
    tardivo["sizeVoided"] = 4.0                                           # Betfair annulla 4
    lib.ricevi_live(dal_conto(tardivo, 3))
    pos = lib.posizione(MKT, "live")
    assert pos.se_vince[HOME] == 32.0                                     # 12 + 20, non 52
    assert pos.se_vince_per_autore["omega"][HOME] == 12.0                 # autore conservato
    # rientrato (il tetto ora riassume il 2, piu' vecchio): Omega, non provvisorio
    assert lib.ordine("1", "live").autore == "omega" and lib.ordine("2", "live") is None
    assert not lib.attribuzione("1", "live").provvisoria


def test_m2_rientro_vecchio_o_in_regressione_rifiutato():
    lib = _tetto(3.0)
    vecchio = dal_conto(ordine_json("1", "BACK", 10.0, 3.0, csr="mike", cor="mike-t1"), 50)
    lib.ricevi_live(vecchio)
    regresso = dal_conto(ordine_json("1", "BACK", 4.0, 3.0, residuo=6.0, csr="mike",
                                     cor="mike-t1"), 9999)
    lib.ricevi_live(regresso)
    assert lib.posizione(MKT, "live").se_vince[HOME] == 60.0
    assert lib.stato()["conti"]["regressioni"] == 1


# ------------------------------------------------------------------ 3. R18
def _oc(sel: int, abb: float, pm: float) -> OrdineConto:
    return OrdineConto(str(sel), MKT, sel, 0.0, "back", pm, abb, abb, 0.0, pm, "abbinato",
                       "mike", None, "live", 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("tipo", ["ASIAN_HANDICAP_SINGLE_LINE", "ASIAN_HANDICAP_DOUBLE_LINE",
                                  "LINE", "RANGE"])
def test_m4_tipi_non_a_vincitore_unico(tipo):
    c = P.calcola(MKT, "live", [_oc(HOME, 10.0, 2.0)], runner=[HOME, AWAY], tipo_scommessa=tipo,
                  vincitori=1)
    assert not c.supportato and c.posizione.se_vince == {}
    assert f"tipo_non_supportato:{tipo}" in c.motivi


# ------------------------------------------------------------------ 4. vincitori_ignoti
def test_vincitori_ignoti_e_tipi_a_vincitore_unico_per_definizione():
    o = [_oc(HOME, 10.0, 2.0)]
    ign = P.calcola(MKT, "live", o, runner=[HOME, AWAY], tipo_scommessa="ODDS")
    assert not ign.supportato and "vincitori_ignoti" in ign.motivi and ign.posizione.se_vince == {}
    assert ign.esposizione_massima == -10.0 and "stima_prudente" in ign.motivi
    for tipo in ("MATCH_ODDS", "OVER_UNDER_25", "CORRECT_SCORE", "FIRST_HALF_GOALS_05"):
        ok = P.calcola(MKT, "live", o, runner=[HOME, AWAY], tipo_scommessa="ODDS", tipo_mercato=tipo)
        assert ok.supportato and ok.posizione.se_vince == {HOME: 10.0, AWAY: -10.0}, tipo
    piazzato = P.calcola(MKT, "live", o, runner=[HOME, AWAY], tipo_scommessa="ODDS",
                         tipo_mercato="PLACE")
    assert "vincitori_ignoti" in piazzato.motivi
    lib = L.LibroConto()
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 2.0, csr="mike", cor="mike-t1")))
    lib.imposta_mercato(MKT, runner=[HOME, AWAY], tipo_scommessa="ODDS")
    assert "vincitori_ignoti" in lib.calcolo_posizione(MKT, "live").motivi
    lib.imposta_mercato(MKT, tipo_mercato="MATCH_ODDS")
    assert lib.posizione(MKT, "live").se_vince == {HOME: 10.0, AWAY: -10.0}


# ------------------------------------------------------------------ 5. JSON
def test_posizione_per_json_nan_diventa_null():
    c = P.calcola(MKT, "live", [_oc(HOME, 10.0, 2.0)], tipo_scommessa="ODDS", vincitori=1)
    assert math.isnan(c.posizione.esposizione_massima)
    j = P.posizione_per_json(c.posizione)
    assert j["esposizione_massima"] is None
    assert j["se_vince"] == {str(HOME): 10.0}
    assert set(j) == {"market_id", "modo", "se_vince", "se_vince_per_autore", "abbinato_back",
                      "abbinato_lay", "prezzo_medio_back", "prezzo_medio_lay", "esposizione_massima"}
    json.dumps(j, allow_nan=False)                                       # JSON valido
    pieno = P.posizione_per_json(P.calcola(MKT, "live", [_oc(HOME, 10.0, 2.0)], runner=[HOME, AWAY],
                                           tipo_scommessa="ODDS", vincitori=1).posizione)
    assert pieno["esposizione_massima"] == -10.0
    assert pieno["prezzo_medio_lay"] == {str(HOME): None, str(AWAY): None}


def test_m2_paper_riassunto_rientra_con_l_attore_dichiarato():
    lib = L.LibroConto(max_ordini=1)
    lib.ricevi_prova(L.OrdineInProva(dal_conto(ordine_json("p1", "BACK", 2.0, 2.0), 1), "mike"))
    lib.ricevi_prova(L.OrdineInProva(dal_conto(ordine_json("p2", "BACK", 2.0, 2.0), 2), "omega"))
    assert lib.ordine("p1", "paper") is None
    lib.ricevi_prova(L.OrdineInProva(dal_conto(ordine_json("p1", "BACK", 2.0, 2.0), 3), None))
    assert lib.ordine("p1", "paper").autore == "mike"


def test_m2_dopo_dimentica_mercato_il_riassunto_non_ferma_un_ordine_nuovo():
    lib = _tetto(3.0)
    lib.dimentica_mercato(MKT)
    lib.ricevi_live(dal_conto(ordine_json("1", "BACK", 10.0, 3.0, csr="mike", cor="mike-t1"), 5))
    assert lib.ordine("1", "live").abbinato == 10.0
