"""CANTIERE T (28/09) - tennis PRO: nessuna posizione dichiarata FLAT con uno
sbilancio abbinato oltre il centesimo quando un ordine al centesimo lo chiude
(controllo K5 del banco).

Reperto del coordinatore (replay 35794049, D2 `8ada778`): K5 base x1, live
x1258, gate-aperto x1258: "sulla selezione 10372252 resta un'esposizione
ABBINATA sbilanciata di 0.02 (se vince -0.09, se perde -0.11), oltre la
tolleranza 0.011 ... e il bot la crede 'nessuna posizione'". Causa: la
sorveglianza CLOSING dichiarava FLAT con |se vince - se perde| < 0,02.

Il PRO VERO del runner paper riceve book veri dal Flumine (esecuzione differita
di un book, come la latenza del replay) e li processa con `process_market_book`.
A ogni book: se il bot e' FLAT, lo sbilancio abbinato e' entro 0,01 (oppure non
riducibile al centesimo) e nessun suo ordine e' vivo, nessuna chiusura esatta
in corso (`UsciteEsatte.attive`).
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_via_bot_2026_09_28 import (
    _netto,
    _nessun_vivo,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import tennis_pro_bot as PRO


@pytest.fixture
def esecuzione_differita(monkeypatch):
    """L'esecuzione simulata di flumine con la LATENZA di produzione ridotta a
    "un book": ogni pacchetto (place/cancel/update/replace) si esegue al book
    DOPO, con le stesse funzioni `execute_*` di flumine. E' la condizione del
    replay (place_latency 600 ms + betDelay): un ordine appena piazzato resta
    `PENDING` per almeno un book. Con l'esecuzione sincrona il difetto K6 non
    si vede, perche' il parcheggio nasce e muore dentro lo stesso book."""
    import flumine.config as fconf
    from flumine.execution.simulatedexecution import SimulatedExecution
    from flumine.order.orderpackage import OrderPackageType

    coda: List[Any] = []

    def _differito(self, pacchetto):
        func = {OrderPackageType.PLACE: self.execute_place,
                OrderPackageType.CANCEL: self.execute_cancel,
                OrderPackageType.UPDATE: self.execute_update,
                OrderPackageType.REPLACE: self.execute_replace}[pacchetto.package_type]
        coda.append([func, pacchetto, 0])
    monkeypatch.setattr(SimulatedExecution, "handler", _differito)
    for k in ("place_latency", "cancel_latency", "update_latency", "replace_latency"):
        monkeypatch.setattr(fconf, k, 0.0)

    class _Svuota:
        """Chiamato a ogni book: esegue i pacchetti in coda da `ritardo` book
        (1 = il book dopo; 3-5 = bet delay e coda piu' lunghi)."""
        ritardo = 1

        def __call__(self) -> None:
            for voce in coda:
                voce[2] += 1
            pronti = [v for v in coda if v[2] >= self.ritardo]
            for v in pronti:
                coda.remove(v)
            for func, pacchetto, _eta in pronti:
                func(pacchetto, None)
    yield _Svuota()


def _pro_in_closing(db: Any, banchi: Any, posizioni: List[tuple], retry_subito: bool = True):
    db.controls = [_control("101", "tennis_pro", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_pro")]
    market = b.fw.markets.markets["1.101"]
    ordini = [b.posizione("101", "tennis_pro", lato=lt, prezzo=p, size=s)
              for lt, p, s in posizioni]
    pt = market.market_book.publish_time_epoch
    strat._trade["1.101"] = {
        "state": PRO.CLOSING, "sel": 11, "side": "BACK", "kind": "test",
        "order": ordini[0], "staged_order": None,
        "close_order": ordini[-1] if len(ordini) > 1 else None,
        "close_wait": 0, "booked": 0.0,
        # la ri-copertura della sorveglianza scatta dopo `close_retry_s`
        "t_close": (pt - int(strat.close_retry_s * 1000) - 1) if retry_subito else pt,
    }
    return b, strat, market


def _giri(b: Any, strat: Any, svuota: Any, n: int = 30) -> List[str]:
    viol: List[str] = []
    for i in range(n):
        svuota()
        b.book("101")
        market = b.fw.markets.markets["1.101"]
        if strat.check_market_book(market, market.market_book):
            strat.process_market_book(market, market.market_book)
        tr = strat._trade.get("1.101") or {}
        if tr.get("state") == PRO.FLAT:
            nw, nl = _netto(market, strat)
            vivi = _nessun_vivo(market, strat)
            if abs(nw - nl) > 0.011 or vivi or strat._esatte.attive:
                viol.append("book %d: FLAT con se vince %.4f / se perde %.4f, vivi=%d, "
                            "esatte in corso=%d" % (i, nw, nl, len(vivi),
                                                    len(strat._esatte.attive)))
    return viol


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Latenza di 1 e di 4 book (bet delay e coda del banco piu' lunghi)."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


def test_sbilancio_di_centesimi_riducibile_non_si_dichiara_flat(db, banchi, differita):
    """BACK 3,00 @2,10 + copertura LAY 3,11 @2,02 abbinate: se vince 0,1278,
    se perde 0,11, sbilancio 0,0178 (< 0,02: prima FLAT subito). Un LAY da
    0,01 al best-lay 2,10 lo porta a 0,0032: il bot lo piazza (place-and-trim,
    0,01 e' sotto il minimo) e dichiara FLAT solo dopo, al centesimo."""
    b, strat, market = _pro_in_closing(db, banchi, [("BACK", 2.10, 3.0), ("LAY", 2.02, 3.11)])
    nw0, nl0 = _netto(market, strat)
    assert 0.011 < abs(nw0 - nl0) < 0.02, (nw0, nl0)
    viol = _giri(b, strat, differita)
    assert viol == [], viol[:3]
    assert strat._trade["1.101"]["state"] == PRO.FLAT
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)
    assert _nessun_vivo(market, strat) == []


def test_chiusura_esatta_in_corso_mai_flat(db, banchi, differita):
    """Posizione LAY 1,00 @2,10 senza copertura: la sorveglianza copre subito
    con BACK 1,05 (tutto place-and-trim, `UsciteEsatte`). Finche' la sequenza
    e' in corso (parcheggio Pending, taglio, rimpiazzo) il PRO non e' FLAT."""
    b, strat, market = _pro_in_closing(db, banchi, [("LAY", 2.10, 1.0)], retry_subito=False)
    # prezzo della copertura: best-back 2,00 (BACK abbinabile subito)
    strat._trade["1.101"]["side"] = "BACK"
    viste = []
    orig = strat._esatte.avanza

    def _spia(m):
        viste.append(len(strat._esatte.attive))
        return orig(m)
    strat._esatte.avanza = _spia
    viol = _giri(b, strat, differita)
    assert viol == [], viol[:3]
    assert max(viste) >= 1, "la copertura deve essere passata dal place-and-trim"
    assert strat._trade["1.101"]["state"] == PRO.FLAT
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)
