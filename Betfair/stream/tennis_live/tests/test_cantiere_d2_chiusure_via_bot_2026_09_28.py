"""CHIUSURE ESATTE guidate SOLO dal bot (cantiere D2, terza consegna, 28/09).

Reperto del coordinatore: sostituendo nei bot `self._esatte.avanza(market)` con
`pass` i test restavano VERDI, perche' il test end-to-end faceva avanzare la
sequenza per conto suo (`strat._esatte.avanza` chiamato dal test). Qui il test
NON tocca mai la macchina: consegna book veri in sequenza al Flumine del runner
paper e chiama `process_market_book` del BOT VERO, come fa flumine. Tutto il
resto (parcheggio, riduzione, rimpiazzo, abbinamento) lo fanno il bot e
flumine.

Per ciascuno dei tre bot pro/FLB/swing e per lo scalper tennis (`_drive_submins`):
  1. dopo N book la chiusura e' abbinata all'importo ESATTO al centesimo;
  2. a fine sequenza NESSUN ordine della strategia resta vivo a mercato
     (il parcheggio da 2,00 a quota non abbinabile compreso);
  3. "se vince" = "se perde" al centesimo sulla selezione.
"""
from __future__ import annotations

from typing import Any

import pytest

# 01/10/2026 (RUNNER_MINIMI_CHIUSURE, reperto 1): minimi .it definitivi 01/10: punta 1,00 /
# banca 1,00 / trim >= 0,50. Una chiusura "esatta al centesimo" che riduce un parcheggio
# sotto 0,50 e' IMPOSSIBILE PER LEGGE (DM 47/2013 art. 8): condotta da riallineare con
# l'utente (equivalente sulla stessa selezione / residuo dichiarato), non adattata a forza.
XFAIL_REPERTO_1 = ("reperto 1 RUNNER_MINIMI_CHIUSURE: chiusura esatta con resto sotto 0,50 "
                   "impossibile per legge su .it (minimi definitivi 01/10)")

from Betfair.stream.tennis_live.tests.test_cantiere_d2_chiusure_esatte_2026_09_28 import (  # noqa: F401
    esecuzione_sincrona,
)
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper.tennis_scalper_bot import compute_green

N_BOOK = 8


def _netto(market: Any, strat: Any, sel: int = 11) -> tuple:
    b, ba, l, la = CD.abbinato_selezione(market, strat, sel)
    return b * (ba - 1.0) - l * (la - 1.0), l - b


def _book_al_bot(b: Any, strat: Any, n: int = N_BOOK) -> None:
    """Book VERI (SUB_IMAGE sulla sottoscrizione) processati da flumine e poi
    consegnati al bot con la sua `process_market_book`: NESSUNA chiamata alla
    macchina dell'uscita esatta dal test."""
    for _ in range(n):
        b.book("101")
        market = b.fw.markets.markets["1.101"]
        if strat.check_market_book(market, market.market_book):
            strat.process_market_book(market, market.market_book)


def _nessun_vivo(market: Any, strat: Any) -> list:
    """Ordini della strategia ancora A MERCATO: stato vivo E residuo > 0.
    (Nel banco l'order stream simulato non gira: un ordine tutto abbinato
    resta `EXECUTABLE` con `size_remaining` 0 finche' flumine non lo chiude;
    a mercato non c'e' piu' niente. Stessa regola di `_has_live` dello
    scalper tennis.)"""
    return [o for o in market.blotter.strategy_orders(strat)
            if CD.ordine_vivo(o) and float(getattr(o, "size_remaining", 0.0) or 0.0) > 1e-9]


def _prepara(db: Any, banchi: Any, bot: str, params: Any = None, size_lay: float = 3.0):
    ctl = _control("101", bot, status="running")
    if params:
        ctl["params"] = dict(params)
    db.controls = [ctl]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", bot)]
    market = b.fw.markets.markets["1.101"]
    # posizione LAY 3,00 @2,10 ABBINATA della strategia: la copertura al
    # best-back 2,00 vale 3,15 BACK (3,00 diretti + 0,15 col place-and-trim)
    # 04/10 (decisione 1 dell'utente): con LAY 3,00 la copertura 3,15 = 3,00 diretti +
    # 0,15 di RESIDUO (sotto 0,50 nessun place-and-trim); col place-and-trim si
    # chiude esatta solo una copertura fra 0,50 e 1,00 (LAY 0,60 -> BACK 0,63)
    b.posizione("101", bot, lato="LAY", prezzo=2.10, size=size_lay)
    nw, nl = _netto(market, strat)
    lato, size, _l = compute_green(nw, nl, 2.0)
    assert lato == "BACK" and not CD.diretta_ok(size, lato)
    return b, strat, market, round(size, 2)


@pytest.mark.parametrize("bot", ["tennis_flb", "tennis_pro", "tennis_swing"])
def test_chiusura_esatta_guidata_dai_book_del_bot(bot, db, banchi, esecuzione_sincrona):
    # 04/10 (decisione 1 dell'utente): l'xfail del reperto 1 e' tolto: il resto e' ora
    # 0,63 (>= 0,50, place-and-trim legale), la chiusura esatta e' possibile
    b, strat, market, size = _prepara(db, banchi, bot, size_lay=0.6)
    o = strat._place(market, 11, "BACK", 2.0, size, copertura=True)
    assert isinstance(o, CD.OrdineComposto) and o.in_corso()
    _book_al_bot(b, strat)
    # 1. abbinata all'importo esatto
    assert o.size_matched == pytest.approx(size, abs=0.001), (bot, o.size_matched)
    assert not o.in_corso()
    # 2. nessun ordine vivo della strategia (parcheggio compreso)
    assert _nessun_vivo(market, strat) == []
    park = [x for x in o.parti() if float(x.order_type.price) == 1000.0]
    assert len(park) == 1 and float(park[0].size_remaining) == 0.0
    # il parcheggio e' quello della fonte unica (minimi_it, oggi 1,00; era 2,00)
    assert float(park[0].size_cancelled) == pytest.approx(CD.IT_BACK_MIN_STAKE, abs=0.001)
    # 3. se vince = se perde al centesimo
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (bot, nw, nl)


def test_scalper_tennis_chiusura_esatta_guidata_dai_book_del_bot(db, banchi,
                                                                esecuzione_sincrona):
    """Lo scalper tennis: `_place_exact` (uscite esatte accese dal runner) e
    `_drive_submins` chiamato SOLO dalla sua `process_market_book`. Ingressi
    spenti coi soli numeri della UI (liquidita' minima irraggiungibile)."""
    b, strat, market, size = _prepara(
        db, banchi, "tennis_scalper", params={"min_size": 1e12, "min_flow": 1e12,
                                              "exact_exits": True}, size_lay=0.6)
    assert strat.exact_exits is True
    slot = strat._slot("1.101", 11)
    o = strat._place(market, 11, "BACK", 2.0, size, floor_min=False, slot=slot)
    # 04/10 (decisione 1 dell'utente): 0,63 BACK e' tutta place-and-trim (nessuna
    # parte diretta sotto 1,00): `_place_exact` torna None e AVVIA la sequenza
    assert o is None
    assert slot.submins, "la copertura (0,63) deve partire col place-and-trim"
    _book_al_bot(b, strat)
    assert not slot.submins, "la sequenza del resto deve essere finita"
    back = [x for x in market.blotter.strategy_orders(strat)
            if getattr(x, "side", "") == "BACK" and float(x.order_type.price) < 1000]
    assert sum(float(x.size_matched) for x in back) == pytest.approx(size, abs=0.001)
    assert _nessun_vivo(market, strat) == []
    nw, nl = _netto(market, strat)
    assert abs(nw - nl) <= 0.01, (nw, nl)


def _esplode(*_a: Any, **_k: Any) -> Any:
    raise ValueError("replace rifiutato - finto")


def test_flb_non_conta_un_verde_su_una_chiusura_abortita_a_meta(db, banchi,
                                                               esecuzione_sincrona,
                                                               monkeypatch):
    """Revisione (MEDIO): il FLB decide "chiusura finita" dall'ABBINATO
    (`size_remaining` del composto), non dallo stato. Una sequenza abortita a
    meta' (stato EXECUTION_COMPLETE, resto non abbinato) NON conta un verde."""
    from Betfair.stream.trading import submin as SM

    b, strat, market, size = _prepara(db, banchi, "tennis_flb", size_lay=0.6)
    monkeypatch.setattr(SM, "advance_submin", _esplode)
    o = strat._place(market, 11, "BACK", 2.0, size, copertura=True)
    assert isinstance(o, CD.OrdineComposto) and not o.in_corso()
    assert o.completa is False and o.size_remaining > 0
    key = ("1.101", 11)
    st = {"state": "OPEN", "entry": 2.1, "order": None, "wait": 0, "greened": True,
          "green_order": o, "green_locked": False, "green_price": 2.0,
          "green_fr": 1.0, "green_est": 0.0, "t0": 0}
    strat._pos_state[key] = st
    greens = strat.stats["greens"]
    strat._manage(market, 11, key, st, 2.0, 2.1, 0)
    assert strat.stats["greens"] == greens, "nessun verde su una chiusura incompleta"
    assert st.get("green_locked") is False
