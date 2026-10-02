"""CHIUSURE ESATTE dei bot tennis (cantiere D2, seconda consegna, 28/09).

Regola permanente dell'utente (testuale): "le chiusure devono sempre essere
perfette e spalmare il profitto o la loss su entrambe le selezioni". Prima le
coperture di pro/FLB/swing si GONFIAVANO al gradino da 0,50 sopra (2,02 ->
2,50) e lo scalper tennis aveva le uscite esatte SPENTE (`tennis_runner`).

Qui la chiusura gira sul RUNNER PAPER VERO: Flumine + client paper del tennis
(`build_order_client("PAPER")` -> `SimulatedExecution`, `SimulatedMiddleware`)
del banco dell'iscrizione a caldo, bot istanziati da `_instantiate_bot`. Per
girare nel test l'esecuzione simulata e' resa SINCRONA (in produzione e' un
thread pool con `time.sleep(bet_delay + latenza)`: stessa funzione
`execute_*`, solo senza thread) e la latenza e' a zero. Il parcheggio a 1000,
la riduzione (`cancelOrders` con `sizeReduction`) e il rimpiazzo
(`replaceOrders`) sono quelli di flumine: nessun fill scritto a mano.

Criterio di accettazione: dopo la chiusura il netto "se vince" e "se perde"
della selezione coincidono AL CENTESIMO (dal blotter di flumine).
"""
from __future__ import annotations

from typing import Any, List

import pytest

# 01/10/2026 (RUNNER_MINIMI_CHIUSURE, reperto 1): minimi .it definitivi 01/10: punta 1,00 /
# banca 1,00 / trim >= 0,50. Una chiusura "esatta al centesimo" che riduce un parcheggio
# sotto 0,50 e' IMPOSSIBILE PER LEGGE (DM 47/2013 art. 8): condotta da riallineare con
# l'utente (equivalente sulla stessa selezione / residuo dichiarato), non adattata a forza.
XFAIL_REPERTO_1 = ("reperto 1 RUNNER_MINIMI_CHIUSURE: chiusura esatta con resto sotto 0,50 "
                   "impossibile per legge su .it (minimi definitivi 01/10)")

from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_tennis_iscrizione_a_caldo_2026_09_25 import (  # noqa: F401
    _banco,
    _control,
    _follow,
    banchi,
    db,
)
from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper.tennis_scalper_bot import compute_green


@pytest.fixture
def esecuzione_sincrona(monkeypatch):
    """L'esecuzione simulata di flumine SENZA thread e senza attese."""
    import flumine.config as fconf
    from flumine.execution.simulatedexecution import SimulatedExecution
    from flumine.order.orderpackage import OrderPackageType

    def _sincrono(self, pacchetto):
        func = {OrderPackageType.PLACE: self.execute_place,
                OrderPackageType.CANCEL: self.execute_cancel,
                OrderPackageType.UPDATE: self.execute_update,
                OrderPackageType.REPLACE: self.execute_replace}[pacchetto.package_type]
        func(pacchetto, None)
    monkeypatch.setattr(SimulatedExecution, "handler", _sincrono)
    for k in ("place_latency", "cancel_latency", "update_latency", "replace_latency"):
        monkeypatch.setattr(fconf, k, 0.0)
    yield


def _netto(market: Any, strat: Any, sel: int = 11) -> tuple:
    b, ba, l, la = CD.abbinato_selezione(market, strat, sel)
    return b * (ba - 1.0) - l * (la - 1.0), l - b


def _giri(b: Any, strat: Any, n: int = 8) -> None:
    """Book successivi (SUB_IMAGE vero) + un passo dell'uscita esatta a book."""
    for _ in range(n):
        b.book("101")
        strat._esatte.avanza(b.fw.markets.markets["1.101"])


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=XFAIL_REPERTO_1)
@pytest.mark.parametrize("bot", ["tennis_flb", "tennis_pro", "tennis_swing"])
def test_copertura_esatta_al_centesimo_nel_runner_paper(bot, db, banchi,
                                                       esecuzione_sincrona):
    """Posizione LAY 3,00 @2,10 abbinata; copertura BACK al best-back 2,00 =
    3,15 EUR (non diretta su .it): 3,00 diretti + 0,15 col place-and-trim.
    Prima: 3,50 (gonfiata) e la selezione restava sbilanciata di ~0,35."""
    db.controls = [_control("101", bot, status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", bot)]
    market = b.fw.markets.markets["1.101"]
    b.posizione("101", bot, lato="LAY", prezzo=2.10, size=3.0)
    nw, nl = _netto(market, strat)
    lato, size, _locked = compute_green(nw, nl, 2.0)
    assert lato == "BACK" and not CD.diretta_ok(size, lato)
    o = strat._place(market, 11, lato, 2.0, size, copertura=True)
    assert isinstance(o, CD.OrdineComposto)
    assert o.order_type.size == pytest.approx(round(size, 2))
    _giri(b, strat)
    assert not strat._esatte.attive, "la sequenza del resto e' finita"
    nw2, nl2 = _netto(market, strat)
    assert abs(nw2 - nl2) <= 0.01, (nw2, nl2)
    # il profitto/la perdita e' SPALMATO su entrambi gli esiti
    assert o.size_matched == pytest.approx(round(size, 2), abs=0.001)
    assert o.size_remaining == 0.0
    # la sequenza e' quella di Betfair, eseguita da flumine: parcheggio 2,00 a
    # 1000, riduzione al resto, rimpiazzo (ordine SOSTITUTO) alla quota vera
    resto = round(round(size, 2) - 3.0, 2)
    park = [x for x in o.parti() if float(x.order_type.price) == 1000.0]
    assert len(park) == 1 and float(park[0].order_type.size) == 2.0
    assert float(park[0].size_cancelled) == pytest.approx(2.0, abs=0.001)
    sost = [x for x in o.parti() if x.trade.orders[0] is not x]
    assert len(sost) == 1 and float(sost[0].order_type.price) == 2.0
    assert float(sost[0].size_matched) == pytest.approx(resto, abs=0.001)
    assert str(o.sequenza["state"].step.value) == "done"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=XFAIL_REPERTO_1)
def test_copertura_tutta_sotto_il_minimo_esatta(db, banchi, esecuzione_sincrona):
    """Copertura BACK 1,05 (sotto il minimo 2,00): tutta col place-and-trim,
    esatta; mai 2,00 (prima: gonfiata a 2,00, posizione ribaltata)."""
    db.controls = [_control("101", "tennis_flb", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_flb")]
    market = b.fw.markets.markets["1.101"]
    b.posizione("101", "tennis_flb", lato="LAY", prezzo=2.10, size=1.0)
    nw, nl = _netto(market, strat)
    lato, size, _l = compute_green(nw, nl, 2.0)
    assert size < 2.0
    o = strat._place(market, 11, lato, 2.0, size, copertura=True)
    assert o is not None and o.diretto is None and o.sequenza is not None
    _giri(b, strat)
    nw2, nl2 = _netto(market, strat)
    assert abs(nw2 - nl2) <= 0.01, (nw2, nl2)
    # nessun ordine piazzato a quota vera sopra la size voluta
    for x in market.blotter.strategy_orders(strat):
        if getattr(x, "side", "") == "BACK" and float(x.order_type.price) < 1000:
            assert float(x.order_type.size) <= round(size, 2) + 1e-9


def test_copertura_lay_sopra_il_minimo_diretta_esatta(db, banchi, esecuzione_sincrona):
    """LAY >= 0,50 e' diretto su .it (nessun multiplo): nessun place-and-trim."""
    db.controls = [_control("101", "tennis_pro", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_pro")]
    market = b.fw.markets.markets["1.101"]
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    o = strat._place(market, 11, "LAY", 2.1, 1.93, copertura=True)
    assert o is not None and not isinstance(o, CD.OrdineComposto)
    assert o.order_type.size == 1.93


def test_annullo_di_una_chiusura_esatta_ferma_la_sequenza(db, banchi, esecuzione_sincrona):
    db.controls = [_control("101", "tennis_swing", status="running")]
    b = _banco(db, banchi, [_follow("101")])
    b.book("101")
    strat = b.session.hosted[("101", "tennis_swing")]
    market = b.fw.markets.markets["1.101"]
    b.posizione("101", "tennis_swing", lato="LAY", prezzo=2.10, size=1.0)
    o = strat._place(market, 11, "BACK", 1000.0, 1.05, copertura=True)
    assert o is not None and o.in_corso()
    strat._cancel(market, o)
    assert not o.in_corso()
    _giri(b, strat, n=3)
    assert not any(CD.ordine_vivo(x) for x in o.parti())


def test_scalper_tennis_uscite_esatte_accese_in_paper_e_live():
    from betfairlightweight.filters import streaming_market_data_filter

    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    for mode in ("PAPER", "LIVE"):
        s = TR._instantiate_bot(
            "tennis_scalper", {"stake": 2.0, "dry_run": False, "params": {},
                               "mode": mode.lower()},
            "1.100", {}, lambda *a, **k: None, df, mode)
        # CANTIERE T: riaccese dopo la correzione vera (ripiego chiuso)
        assert s.exact_exits is True, mode


# ---------------------------------------------------------------------------
# la regola pura
# ---------------------------------------------------------------------------
# minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50 (banca 0,93 sotto il minimo: tutto al resto, trim legale >= 0,50).
# 1,98 BACK oggi si spezza 1,50 + 0,48: un resto sotto 0,50 e' impossibile per legge
# (reperto 1, condotta delle uscite esatte del tennis): xfail.
@pytest.mark.parametrize("size,lato,attesa", [
    (2.02, "BACK", (2.0, 0.02)),
    pytest.param(1.98, "BACK", (0.0, 1.98),
                 marks=pytest.mark.xfail(strict=True, raises=AssertionError, reason=XFAIL_REPERTO_1)),
    (3.15, "BACK", (3.0, 0.15)),
    (2.5, "BACK", (2.5, 0.0)), (0.30, "LAY", (0.0, 0.30)), (0.93, "LAY", (0.0, 0.93)),
])
def test_spezza_esatta_la_somma_e_sempre_la_size(size, lato, attesa):
    diretta, resto = CD.spezza_esatta(size, lato)
    assert (diretta, resto) == attesa
    assert round(diretta + resto, 2) == round(size, 2)


@pytest.mark.parametrize("size,lato", [(0.93, "BACK"), (2.03, "BACK"), (0.10, "LAY")])
def test_la_copertura_non_si_gonfia_mai(size, lato):
    legale, motivo = CD.size_legale(size, lato, live=True, riduce_liability=True)
    assert legale is None and "mai gonfiata" in (motivo or "")


# ---------------------------------------------------------------------------
# anti-cascata: gli STESSI numeri dello scalper tennis (30 s, 5 fallite)
# ---------------------------------------------------------------------------
class _BotFinto:
    """Le sole cose che ``UsciteEsatte`` legge dal bot: l'orologio del mercato."""

    def __init__(self) -> None:
        self.ora = 1000.0
        self.eventi: List[tuple] = []

    def _orologio_s(self) -> float:
        return self.ora

    def _emit(self, kind: str, **p: Any) -> None:
        self.eventi.append((kind, p))


class _MercatoFinto:
    market_id = "1.101"


def test_anti_cascata_mai_definitiva_intervallo_crescente(monkeypatch):
    """28/09 sera (revisione): la rinuncia NON e' mai definitiva. Dopo ogni
    sequenza fallita l'intervallo raddoppia (30, 60, 120, 240, poi 300 s fisso);
    ogni fallimento e ogni blocco scrivono una riga CRITICA con lo scoperto."""
    from Betfair.stream.trading import submin as SM

    def _esplode(*a, **k):
        raise ValueError("submin place RIFIUTATO - finto")
    monkeypatch.setattr(SM, "advance_submin", _esplode)
    bot = _BotFinto()
    ue = CD.UsciteEsatte(bot, bot._emit)
    m = _MercatoFinto()
    chiave = ("1.101", 11)

    def _prova() -> Any:   # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50: 0,70 e' tutto resto (1,20 oggi e' 1,00 diretto)
        return ue.piazza(m, 11, "BACK", 2.0, 0.7, diretto=lambda s: None)

    assert _prova() is not None                       # 1a: parte e fallisce
    attese = [60, 120, 240, 300, 300, 300]
    for att in attese:
        assert ue.intervallo_s(chiave) == att
        bot.ora += att - 1
        assert _prova() is None, att                   # dentro la finestra: bloccata
        assert _prova() is None                        # (riga critica UNA volta)
        bot.ora += 1
        assert _prova() is not None, att               # scaduta: RIPROVA, sempre
    critiche = [(k, p) for k, p in bot.eventi if p.get("level") == "CRITICAL"]
    abort = [p for k, p in critiche if k == "uscita_esatta_abort"]
    attesa = [p for k, p in critiche if k == "uscita_esatta_attesa"]
    assert len(abort) == 1 + len(attese)
    assert len(attesa) == len(attese)                  # una per finestra, mai per book
    assert all(p["scoperto"] == 0.7 and p["lato"] == "BACK" for p in abort + attesa)
    assert "chiudere a mano" in attesa[0]["note"]
    # un'altra selezione non e' toccata
    assert ue.piazza(m, 22, "BACK", 2.0, 0.7, diretto=lambda s: None) is not None


def test_anti_cascata_si_azzera_al_primo_successo(monkeypatch):
    from Betfair.stream.trading import submin as SM

    esito = {"x": "esplodi"}

    def _finto(market, state, **k):
        if esito["x"] == "esplodi":
            raise ValueError("rifiutato - finto")
        from dataclasses import replace as _r
        return _r(state, step=SM.SubminStep.DONE)
    monkeypatch.setattr(SM, "advance_submin", _finto)
    bot = _BotFinto()
    ue = CD.UsciteEsatte(bot, bot._emit)
    m = _MercatoFinto()
    chiave = ("1.101", 11)
    for _ in range(3):   # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
        ue.piazza(m, 11, "BACK", 2.0, 0.7, diretto=lambda s: None)
        bot.ora += ue.intervallo_s(chiave)
    assert ue.intervallo_s(chiave) == 240
    esito["x"] = "riesce"
    assert ue.piazza(m, 11, "BACK", 2.0, 0.7, diretto=lambda s: None) is not None
    assert ue.intervallo_s(chiave) == 30               # azzerato al successo


def test_composto_abortito_a_meta_non_e_completo(monkeypatch):
    """Revisione (MEDIO): una sequenza ABORTITA a meta' ha `status`
    EXECUTION_COMPLETE (a mercato non c'e' piu' niente) ma la chiusura NON e'
    finita: `completa` falso e `size_remaining` = il resto non abbinato."""
    from flumine.order.order import OrderStatus

    from Betfair.stream.trading import submin as SM

    def _esplode(*a, **k):
        raise ValueError("replace rifiutato - finto")
    monkeypatch.setattr(SM, "advance_submin", _esplode)
    bot = _BotFinto()
    ue = CD.UsciteEsatte(bot, bot._emit)
    # minimi .it definitivi 01/10: punta 1,00 / banca 1,00 / trim >= 0,50
    o = ue.piazza(_MercatoFinto(), 11, "BACK", 2.0, 0.7, diretto=lambda s: None)
    assert o.status == OrderStatus.EXECUTION_COMPLETE
    assert o.completa is False and o.size_remaining == 0.7


# ---------------------------------------------------------------------------
# B8 del banco: il SOSTITUTO e' solo la catena legittima del place-and-trim
# ---------------------------------------------------------------------------
def _ordine_finto(side: str, prezzo: float, size: float, cancellato: float = 0.0) -> Any:
    """Le chiavi che `riga_ordine` legge da un ordine flumine (`order_type.
    price/size`, `side`, `size_cancelled`, `trade.orders`, `status` Enum...)."""
    from types import SimpleNamespace

    from flumine.order.order import OrderStatus

    return SimpleNamespace(id=str(id(object())), bet_id=None, status=OrderStatus.EXECUTABLE,
                           side=side, selection_id=11, market_id="1.101",
                           order_type=SimpleNamespace(price=prezzo, size=size),
                           size_matched=0.0, size_remaining=size - cancellato,
                           size_cancelled=cancellato, size_lapsed=0.0, size_voided=0.0,
                           average_price_matched=0.0, customer_order_ref=None,
                           violation_msg=None, trade=None)


def _b8(ordini: list) -> Any:
    from Betfair.stream.tennis_live import certificazione_bot as CB

    return CB._b8(CB.Osservazione(modalita="live", giurisdizione="it",
                                  ordini=[CB.riga_ordine(o) for o in ordini]))


def _in_trade(*ordini: Any) -> list:
    from types import SimpleNamespace

    tr = SimpleNamespace(orders=list(ordini))
    for o in ordini:
        o.trade = tr
    return list(ordini)


def test_b8_catena_legittima_del_place_and_trim_non_viola():
    park = _ordine_finto("BACK", 1000.0, 2.0, cancellato=1.85)   # ridotto a 0,15
    sost = _ordine_finto("BACK", 2.0, 0.15)                       # il rimpiazzo
    assert _b8(_in_trade(park, sost)) is None


@pytest.mark.parametrize("prima", [
    None,                                            # nessun ordine prima
    ("BACK", 2.0, 2.0, 1.85),                        # prima NON a quota di parcheggio
    ("BACK", 1000.0, 2.0, 0.0),                      # parcheggio MAI ridotto
    ("BACK", 1000.0, 1.0, 0.85),                     # parcheggio sotto il minimo
    ("LAY", 1.01, 2.0, 1.85),                        # lato diverso
])
def test_b8_sotto_il_minimo_senza_catena_legittima_viola(prima):
    sotto = _ordine_finto("BACK", 2.0, 0.15)
    ordini = [sotto] if prima is None else _in_trade(_ordine_finto(*prima), sotto)
    if prima is None:
        _in_trade(_ordine_finto("BACK", 2.0, 3.0), sotto)   # secondo di un Trade condiviso
        ordini = [sotto]
    assert _b8(ordini) is not None
