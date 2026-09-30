"""REGOLAMENTO AL CENTESIMO (30/09, banco RG1 sulle sintetiche).

Reperto: `_synth_mike_reingresso` - Mike scriveva +3,30, il banco +3,28. La
regola di Betfair (``listClearedOrders``, documentazione in
``Betfair/Betfair_api_documentation.pdf`` pag. 54-55: ``profit`` e
``commission`` PER SCOMMESSA, a due decimali; la commissione e' il 5 % del netto
vincente del MERCATO, al centesimo: 0,56 -> 0,03; 2,14 -> 0,11; 2,36 -> 0,12;
2,52 -> 0,13):
  * il P&L di ogni scommessa e' in centesimi (4,8672 -> 4,87);
  * il netto del mercato e' la somma delle scommesse;
  * la commissione e' round(5 % x netto vincente del mercato, 2);
  * il netto del mercato e' il lordo meno quella commissione.
Mike sommava i P&L NON arrotondati e toglieva la commissione NON arrotondata
(``_net``): +3,30 invece di +3,27.

Finti: ``Leg`` vera del motore, con le quantita' ESATTE della sintetica (sonda
``AUDIT_2026-09-30/replay/_strumenti/sonda_rg1.py``). ASCII-only.
"""
from __future__ import annotations

import pytest

from Betfair.mike import engine as E


def _gamba(ref, role, market, side, matched, prezzo):
    return E.Leg(role=role, market=market, selection=E.SEL_UNDER, side=side, price=prezzo,
                 size=matched, matched=matched, avg_price=prezzo if matched > 0 else None,
                 ref=ref, status="open")


def _reingresso():
    return [
        _gamba("under_entry-0-1", "under_entry", E.MARKET_OU35, "back", 10.0, 1.5),
        _gamba("under_green-0-2", "under_green", E.MARKET_OU35, "lay", 0.0, 1.48),
        _gamba("ko_green-0-3", "ko_green", E.MARKET_OU35, "lay", 10.14, 1.48),
        _gamba("reentry-0-4", "reentry", E.MARKET_OU45, "back", 10.0, 1.6),
        _gamba("reentry_green-0-5", "reentry_green", E.MARKET_OU45, "lay", 10.13, 1.2),
        _gamba("reentry_green-0-6", "reentry_green", E.MARKET_OU45, "lay", 2.43, 1.2),
        _gamba("reentry_green-0-7", "reentry_green", E.MARKET_OU45, "lay", 0.59, 1.2),
        _gamba("reentry_green-0-8", "reentry_green", E.MARKET_OU45, "lay", 0.14, 1.2),
        _gamba("reentry_green-0-9", "reentry_green", E.MARKET_OU45, "lay", 0.03, 1.2),
        _gamba("reentry_green-0-10", "reentry_green", E.MARKET_OU45, "lay", 0.01, 1.2),
    ]


def test_regolamento_come_betfair_scommessa_al_centesimo_commissione_al_centesimo():
    res = E.settle_legs_by_market(_reingresso(), {E.MARKET_OU35: E.SEL_UNDER,
                                                  E.MARKET_OU45: E.SEL_UNDER}, 0.05)
    # OU35: +5,00 - 4,87 = 0,13 lordo; commissione round(0,0065) = 0,01; netto 0,12
    # OU45: +6,00 - 2,03 - 0,49 - 0,12 - 0,03 - 0,01 - 0,00 = 3,32; comm. 0,17; netto 3,15
    assert res.commission_by_market == {E.MARKET_OU35: 0.01, E.MARKET_OU45: 0.17}
    assert res.per_market == {E.MARKET_OU35: 0.12, E.MARKET_OU45: 3.15}
    assert res.net == pytest.approx(3.27, abs=1e-9)
    assert round(sum(p for _r, _s, p in res.per_leg), 2) == pytest.approx(res.net, abs=1e-9)
    lordi = dict((r, p) for r, _s, p in res.per_leg_gross)
    assert lordi["ko_green-0-3"] == -4.87 and lordi["reentry_green-0-5"] == -2.03


def test_netto_del_mercato_uguale_lordo_meno_commissione_addebitata():
    """Con il lordo gia' in centesimi, round(lordo x (1 - c), 2) coincide con
    lordo - round(lordo x c, 2) (la commissione che Betfair addebita): lo si
    verifica su tutti i lordi da -5,00 a +50,00."""
    for centesimi in [c for c in range(-500, 5001) if c]:
        lordo = centesimi / 100.0
        gambe = [_gamba("a", "under_entry", E.MARKET_OU35, "back", 100.0, 1.0 + lordo / 100.0)
                 if lordo > 0 else
                 _gamba("a", "under_entry", E.MARKET_OU35, "back", -lordo, 2.0)]
        vince = E.SEL_UNDER if lordo > 0 else E.SEL_OVER
        res = E.settle_legs_by_market(gambe, {E.MARKET_OU35: vince}, 0.05)
        g = dict((r, p) for r, _s, p in res.per_leg_gross)["a"]
        assert res.per_market[E.MARKET_OU35] == round(g - res.commission_by_market[E.MARKET_OU35], 2)


def test_rg1_uno_scarto_di_un_centesimo_e_rosso():
    """RG1 confronta al centesimo: 3,28 contro 3,27 e' una violazione."""
    from Betfair.mike import certificazione as CERT

    assert CERT.confronta_regolamento("SETTLED", 3.27, [], {}, 3.27, {}) == []
    v = CERT.confronta_regolamento("SETTLED", 3.28, [], {}, 3.27, {})
    assert len(v) == 1 and v[0].codice == "RG1"


def test_banco_pnl_betfair_commissione_per_mercato_al_centesimo():
    """La regola del banco, con ordini VERI di flumine abbinati come nella
    sintetica (lordi per ordine gia' al centesimo da ``simulatedorder.profit``)."""
    from flumine import BaseStrategy
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    from Betfair.stream.backtest import banco_comune as B

    m = B.MercatoFlumine(strategia=None)
    casi = [("1.35", "BACK", 1.5, 10.0, "WINNER"), ("1.35", "LAY", 1.48, 10.14, "WINNER"),
            ("1.45", "BACK", 1.6, 10.0, "WINNER")] + [
        ("1.45", "LAY", 1.2, s, "WINNER") for s in (10.13, 2.43, 0.59, 0.14, 0.03, 0.01)]
    with B.simulazione_flumine():
        for i, (mid, lato, prezzo, size, esito) in enumerate(casi):
            o = Trade(market_id=mid, selection_id=1, handicap=0.0,
                      strategy=BaseStrategy(market_filter={})).create_order(
                side=lato, order_type=LimitOrder(price=prezzo, size=size))
            o.simulated._update_matched([0, prezzo, size])
            o.runner_status = esito
            m.ordini[f"r{i}"] = o
    c = m.pnl_betfair(0.05)
    assert c["mercati"] == {"1.35": 0.13, "1.45": 3.32}
    assert c["commissione_mercati"] == {"1.35": 0.01, "1.45": 0.17}
    assert c["netto"] == 3.27
    # la nota storica del referto (``pnl``) arrotonda solo il totale: 3,28
    assert m.pnl(0.05)["netto"] == 3.28


def test_mercato_in_perdita_nessuna_commissione_e_lordo_in_centesimi():
    gambe = [_gamba("a", "under_entry", E.MARKET_OU35, "back", 10.0, 1.5),
             _gamba("b", "ko_green", E.MARKET_OU35, "lay", 3.333, 1.48)]
    res = E.settle_legs_by_market(gambe, {E.MARKET_OU35: E.SEL_OVER}, 0.05)
    # -10,00 + 3,333 (la banca vince il suo importo: 3,33 al centesimo)
    assert res.commission_by_market == {E.MARKET_OU35: 0.0}
    assert res.per_market == {E.MARKET_OU35: -6.67}
    assert res.net == pytest.approx(-6.67, abs=1e-9)
