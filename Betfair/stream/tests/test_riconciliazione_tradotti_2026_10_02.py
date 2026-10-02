"""02/10/2026 - RICONCILIAZIONE DEI TRADOTTI, lato RUNNER: UNA traduzione per ogni via.

Un ordine che il runner traduce nell'equivalente (banca Over 0,43 @18 -> punta Under
7,31 @1,06) si legge da QUATTRO vie: l'evento del canale (``_riporta_tradotto``), lo
specchio ``betfair_live_orders`` (encoder di produzione), lo stato per bet_id e gli ordini
correnti/regolati di Betfair (funzioni vere di ``omega_market``), il ``result`` della coda.
Qui si certifica che tutte danno gli STESSI numeri nei termini chiesti, che un ordine non
tradotto resta identico, e che i finti dei test dei bot parlano come il motore vero.
ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.omega import omega_market as OM
from Betfair.safe_strategy import execution as X
from Betfair.stream import live_order_build as LB
from Betfair.stream import motore_ordini as MO
from Betfair.stream.tests.test_motore_ordini_2026_09_24 import (  # noqa: F401 - fixture
    _ack,
    _cmd,
    _manda,
    amb,
)
from Betfair.stream.tests.test_runner_minimi_correzioni_2026_10_02 import (
    _due_esiti,
    _eventi,
)
from Betfair.stream.tests.tradotti_comuni import (
    OVER,
    UNDER,
    corrente_grezzo,
    evento_tradotto,
    monta_rete,
    regolato_grezzo,
    riga_vera,
    tradotto_di,
)

BET = "331"
RIGA_BOT = {"selection_id": OVER, "handicap": 0.0, "side": "lay", "price": 18.0,
            "size": 0.43}


def _chiave(d: dict) -> tuple:
    avg = d.get("average_price_matched", d.get("avg_price_matched"))
    return (d["selection_id"], d["side"], d["size_matched"], round(float(avg or 0.0), 4),
            d.get("size_remaining"))


@pytest.mark.parametrize("abbinato", [7.31, 3.66, 0.0])
def test_r_ogni_via_di_lettura_da_gli_stessi_numeri(monkeypatch, abbinato):
    t = tradotto_di("lay", 18.0, 0.43)
    residuo = round(7.31 - abbinato, 2)
    stato = "EXECUTION_COMPLETE" if residuo == 0 else "EXECUTABLE"
    # 1. evento del canale (motore)
    ev = evento_tradotto(t, ref="safe-t1", seq=1, fase="abbinato", matched=abbinato,
                         remaining=residuo, status=stato, bet_id=BET,
                         avg=(1.06 if abbinato else 0.0))
    # 2. specchio betfair_live_orders (encoder di produzione), letto dalla riga del bot
    specchio = riga_vera(selection_id=UNDER, side="back", price=1.06, size=7.31,
                         matched=abbinato, remaining=residuo, status=stato, bet_id=BET,
                         avg=(1.06 if abbinato else 0.0))
    da_specchio = X.nei_termini_della_riga(dict(RIGA_BOT), specchio)
    # 3. stato per bet_id e 4. ordine corrente (funzioni VERE di omega_market)
    rete = monta_rete(monkeypatch)
    rete.correnti = [corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                     price=1.06, size=7.31, matched=abbinato,
                                     remaining=residuo, status=stato,
                                     avg=(1.06 if abbinato else None))]
    stato_bet = OM.order_state_by_bet_id(BET)
    assert (stato_bet["selection_id"], stato_bet["side"]) == (UNDER, "back")
    da_stato = X.nei_termini_della_riga(dict(RIGA_BOT), stato_bet)
    corrente = OM._riga_corrente(rete.correnti[0])
    da_corrente = X.nei_termini_della_riga(dict(RIGA_BOT), corrente)
    attesi = _chiave(ev)
    assert attesi[:2] == (OVER, "lay")
    # i numeri ricalcolati QUI, indipendenti dalla funzione (ogni via la condivide):
    # abbinato = 0,43 x m/7,31; quota = 1 + m/abbinato; residuo = r x 0,43/7,31
    ab = round(0.43 * abbinato / 7.31, 2)
    quota = round(1.0 + abbinato / ab, 4) if ab > 0 else 0.0
    assert attesi[2:] == (ab, quota, round(residuo * 0.43 / 7.31, 2))
    assert _chiave(da_specchio) == attesi
    assert _chiave(da_stato) == attesi
    assert _chiave(da_corrente) == attesi
    # la dichiarazione ricostruita DAI DATI e' quella del runner
    for d in (da_specchio, da_stato, da_corrente):
        assert d["tradotto"]["mandato"] == t["mandato"]
        assert d["tradotto"]["originale"] == t["originale"]


def test_r_il_regolato_di_betfair_nei_termini_chiesti(monkeypatch):
    rete = monta_rete(monkeypatch)
    rete.regolati = [regolato_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                     price=1.06, settled=7.31, profit=0.44)]
    reg = OM.list_cleared_orders(["safe"])[0]
    letto = X.nei_termini_della_riga(dict(RIGA_BOT, closes_trade_id=1), reg)
    assert (letto["selection_id"], letto["side"], letto["size_settled"]) == (OVER, "lay", 0.43)
    assert letto["price"] == 18.0                     # quota riportata (regolato: abbinata)
    assert letto["profit"] == 0.44                    # il profit VERO resta quello di Betfair
    st = OM.order_state_by_bet_id(BET)
    assert st["selection_id"] == UNDER and st["price_requested"] == 1.06


def test_r_ordine_non_tradotto_torna_identico():
    vera = riga_vera(selection_id=OVER, side="lay", price=18.0, size=2.0, matched=2.0,
                     remaining=0.0, status="EXECUTION_COMPLETE", bet_id=BET, avg=18.0)
    assert X.nei_termini_della_riga(dict(RIGA_BOT, size=2.0), vera) is vera
    stato = {"found": True, "size_matched": 2.0, "avg_price_matched": 18.0,
             "size_remaining": 0.0}
    assert X.nei_termini_della_riga(dict(RIGA_BOT), stato) is stato


def test_r_mai_tradotto_un_ordine_dell_altra_selezione_con_lo_stesso_lato():
    """Stessa selezione diversa ma STESSO lato: non e' un equivalente (che e' sempre sul
    lato opposto), la lettura non si tocca."""
    vera = riga_vera(selection_id=UNDER, side="lay", price=1.06, size=7.31, matched=7.31,
                     remaining=0.0, status="EXECUTION_COMPLETE", bet_id=BET, avg=1.06)
    assert LB.lettura_nei_termini_chiesti(RIGA_BOT, vera) is None


def test_r_evento_del_canale_non_si_traduce_due_volte():
    t = tradotto_di("lay", 18.0, 0.43)
    ev = evento_tradotto(t, ref="safe-t1", seq=1, fase="abbinato", matched=7.31,
                         remaining=0.0, status="EXECUTION_COMPLETE", bet_id=BET)
    assert LB.lettura_nei_termini_chiesti(RIGA_BOT, ev, tradotto=t) is None


def test_r_impronta_equivalente_esatta():
    o = OM._riga_corrente(corrente_grezzo(bet_id=BET, selection_id=UNDER, side="back",
                                          price=1.06, size=7.31, matched=7.31,
                                          remaining=0.0))
    assert LB.impronta_equivalente(RIGA_BOT, o) is True
    for k, v in (("size_requested", 7.30), ("price_requested", 1.07), ("side", "lay"),
                 ("selection_id", OVER)):
        assert LB.impronta_equivalente(RIGA_BOT, dict(o, **{k: v})) is False


@pytest.mark.parametrize("runners,vincitori,atteso", [
    ([(OVER, "ACTIVE"), (UNDER, "ACTIVE")], 1, (UNDER, 0.0)),
    ([(OVER, "ACTIVE"), (UNDER, "ACTIVE")], None, (UNDER, 0.0)),
    ([(OVER, "ACTIVE"), (UNDER, "REMOVED")], 1, None),
    ([(OVER, "ACTIVE"), (UNDER, "ACTIVE")], 2, None),
    ([(OVER, "ACTIVE"), (UNDER, "ACTIVE"), (3, "ACTIVE")], 1, None),
    ([(7, "ACTIVE"), (UNDER, "ACTIVE")], 1, None),
])
def test_r_altro_esito_dal_book_rest_stessa_regola_del_canale(runners, vincitori, atteso):
    book = {"runners": [{"selectionId": s, "handicap": 0.0, "status": st}
                        for s, st in runners]}
    if vincitori is not None:
        book["numberOfWinners"] = vincitori
    assert OM.altro_esito_dal_book(book, OVER) == atteso


def test_r_banco_stato_per_bet_id_con_le_chiavi_della_produzione():
    """Il gemello del banco (``MercatoFlumine.order_state_by_bet_id``) porta le stesse
    chiavi d'identita' della produzione (difetto 27 del catalogo: il finto parla come il
    vero)."""
    from types import SimpleNamespace

    from Betfair.stream.backtest import banco_comune as BC

    ordine = SimpleNamespace(selection_id=UNDER, side="BACK",
                             order_type=SimpleNamespace(price=1.06, size=7.31))
    banco = BC._identita_ordine_flumine(ordine)
    vero = OM._identita_ordine({"selectionId": UNDER, "side": "BACK"}, 1.06, 7.31)
    assert banco == vero == {"selection_id": UNDER, "side": "back", "price_requested": 1.06,
                             "size_requested": 7.31}


def test_r_contratto_tradotto_del_finto_uguale_al_motore_vero(amb):
    """La dichiarazione e l'evento dei finti (``tradotti_comuni``) sono quelli del motore
    VERO: stesso ``tradotto``, stesse chiavi, stessi numeri nei termini chiesti."""
    _due_esiti(amb.market)
    amb.market.borsa = True
    ws = amb.ch.collega("safe")
    _manda(amb, ws, _cmd("safe", 1, mode="live", selection_id=OVER, side="LAY", price=18.0,
                         size=0.43, reduces_liability=True))
    assert _ack(amb, ws)["accettato"] is True
    ev_vero = _eventi(amb, ws, "safe-t1")[-1]
    t = tradotto_di("lay", 18.0, 0.43)
    assert ev_vero["tradotto"] == t
    finto = evento_tradotto(t, ref="safe-t1", seq=ev_vero["seq"], fase=ev_vero["fase"],
                            matched=0.0, remaining=7.31,
                            status=ev_vero["riga_mandata"].get("status") or "EXECUTABLE",
                            bet_id=ev_vero["bet_id"])
    assert set(finto) >= set(MO.CHIAVI_SPECCHIO) and set(ev_vero) >= set(MO.CHIAVI_SPECCHIO)
    for k in ("selection_id", "side", "price", "size", "size_matched",
              "average_price_matched"):
        assert finto[k] == ev_vero[k], k
    assert set(finto["riga_mandata"]) == set(ev_vero["riga_mandata"])
