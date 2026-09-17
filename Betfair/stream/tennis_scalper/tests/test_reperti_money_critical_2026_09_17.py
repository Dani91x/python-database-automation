# -*- coding: utf-8 -*-
"""I TRE REPERTI MONEY-CRITICAL del 17/09, chiusi e falsificati.

Ognuno era stato MISURATO sul replay, non ipotizzato; ognuno qui ha il test che
dimostra la correzione E il test che dimostra che la correzione non ha spento
qualcos'altro (un test che non sa dire di no non certifica).

  R1 — SWING: 7,57 EUR di esposizione abbinata ABBANDONATA su 35790089 (se
       vince +2,91 / se perde -4,66) con il bot senza piu' nessun trade su
       quella selezione. Causa misurata: `_tr.pop()` al timeout d'ingresso dopo
       un `cancel` il cui esito non veniva mai verificato; l'ordine si riempiva
       DOPO. 15 ingressi, 5 uscite.
  R2 — SCALPER: il micro-residuo accettato per ciclo non era guardato da nessuno
       una volta riciclato lo slot (`_reset` butta via i riferimenti e
       `_net_position` non vede piu' niente).
  R3 — FLB e SCALPER: nessun freno dopo un rifiuto di Betfair (8.132 e 20.534
       tentativi in UNA partita).

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import types

import pytest
from flumine.order.order import OrderStatus

from Betfair.stream.tennis_scalper import condotta_ordini as CD
from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy
from Betfair.stream.tennis_scalper.tennis_swing_bot import TennisSwingStrategy


# ---------------------------------------------------------------------------
# i finti: parlano come il vero
# ---------------------------------------------------------------------------
def _ordine(sel, side, matched, avg, stato=OrderStatus.EXECUTION_COMPLETE,
            residuo=0.0, oid="o1"):
    return types.SimpleNamespace(
        id=oid, selection_id=sel, side=side, size_matched=matched,
        average_price_matched=avg, status=stato, size_remaining=residuo,
        simulated=types.SimpleNamespace(profit=0.0))


class _Blotter:
    def __init__(self, ordini=None):
        self.ordini = list(ordini or [])

    def strategy_orders(self, _s):
        return list(self.ordini)


class _Market:
    market_id = "1.1"

    def __init__(self, blotter=None, rifiuta=False):
        self.blotter = blotter or _Blotter()
        self.placed = []
        self.cancelled = []
        self.rifiuta = rifiuta

    def place_order(self, o):
        if self.rifiuta:
            try:
                o.violation("rifiuto del test")
            except Exception:  # noqa: BLE001
                pass
            return False
        self.placed.append(o)
        return True

    def cancel_order(self, o):
        self.cancelled.append(o)
        return True


class _Runner:
    def __init__(self, sel, back, lay):
        self.selection_id = sel
        self.status = "ACTIVE"
        self.last_price_traded = back[0]
        self.ex = types.SimpleNamespace(
            available_to_back=[{"price": back[0], "size": back[1]}],
            available_to_lay=[{"price": lay[0], "size": lay[1]}],
        )


class _MB:
    def __init__(self, runners, pt=1_000_000, tm=1_000_000.0, inplay=True):
        self.runners = list(runners)
        self.market_id = "1.1"
        self.status = "OPEN"
        self.publish_time_epoch = pt
        self.total_matched = tm
        self.inplay = inplay
        self.market_definition = None


def _swing(**p):
    return TennisSwingStrategy(swing_params=dict(p),
                               market_filter={"markets": ["x"]},
                               max_order_exposure=None,
                               max_selection_exposure=None,
                               max_trade_count=int(1e9),
                               max_live_trade_count=int(1e9))


def _flb(**p):
    return TennisFLBStrategy(flb_params=dict(p),
                             market_filter={"markets": ["x"]},
                             max_order_exposure=None,
                             max_selection_exposure=None,
                             max_trade_count=int(1e9),
                             max_live_trade_count=int(1e9))


# ===========================================================================
# R1 — lo swing non dimentica piu' un trade senza aver verificato il blotter
# ===========================================================================
def test_r1_il_timeout_ingresso_non_dimentica_il_trade():
    """LA SCENA DEL REPERTO: l'ingresso scade, il cancel non ha effetto e
    l'ordine si riempie DOPO. Prima il trade era gia' stato dimenticato e la
    posizione restava orfana; ora resta sorvegliato."""
    s = _swing(tmax=90)
    blotter = _Blotter()
    m = _Market(blotter)
    ordine = _ordine(111, "BACK", 0.0, 0.0, stato=OrderStatus.EXECUTABLE,
                     residuo=2.0)
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": 100, "anchor": 98,
                    "order": ordine, "held": 0, "wait": 0, "t0": 1_000_000}
    mb = lambda pt: _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=pt)  # noqa: E731
    s.process_market_book(m, mb(1_041_000))      # +41 s: l'ingresso scade
    assert "1.1" in s._tr, "il trade NON si dimentica al timeout"
    assert s._tr["1.1"]["closing"] is True
    # il cancel non ha avuto effetto e l'ordine si riempie DOPO
    ordine.status = OrderStatus.EXECUTION_COMPLETE
    ordine.size_matched, ordine.size_remaining = 2.0, 0.0
    ordine.average_price_matched = 2.00
    blotter.ordini.append(ordine)
    s.process_market_book(m, mb(1_042_000))
    assert m.placed, "la posizione scoperta viene COPERTA, non abbandonata"
    assert "1.1" in s._tr, "resta sorvegliata finche' il blotter non e' pari"


def test_r1_a_selezione_pari_il_trade_si_chiude_davvero():
    """LA FALSIFICAZIONE: la regola non deve tenere in vita un trade per sempre.
    Con la selezione verificata PARI il trade si chiude."""
    s = _swing()
    blotter = _Blotter([_ordine(111, "BACK", 2.0, 2.00, oid="a"),
                        _ordine(111, "LAY", 2.0, 2.00, oid="b")])
    m = _Market(blotter)
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": 100, "anchor": 98,
                    "order": None, "held": 0, "wait": 0, "t0": 1_000_000,
                    "closing": True, "close_order": None, "close_wait": 0,
                    "t_close": 1_000_000}
    s.process_market_book(
        m, _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=1_002_000))
    assert "1.1" not in s._tr


def test_r1_un_blotter_illeggibile_non_chiude_niente():
    """Fail-safe: se il blotter non si legge, NON si dichiara pari."""
    s = _swing()

    class _BlotterKO:
        def strategy_orders(self, _s):
            raise RuntimeError("giu'")

    m = _Market(_BlotterKO())
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": 100, "anchor": 98,
                    "order": None, "held": 0, "wait": 0, "t0": 1_000_000,
                    "closing": True, "close_order": None, "close_wait": 0,
                    "t_close": 1_000_000}
    s.process_market_book(
        m, _MB([_Runner(111, (2.00, 100), (2.02, 100))], pt=1_002_000))
    assert "1.1" in s._tr, "non si dimentica cio' che non si e' potuto vedere"


def test_r1_al_fischio_finale_la_posizione_aperta_si_dichiara():
    """A mercato CHIUSO il bot non riceve piu' book: se non dichiarasse nulla,
    una posizione creduta viva resterebbe tale per sempre (era il K4 al
    settlement)."""
    s = _swing()
    detto = []
    s.event_sink = lambda k, p: detto.append((k, p))
    m = _Market(_Blotter([_ordine(111, "BACK", 2.0, 2.00)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": 100, "anchor": 98,
                    "order": None, "held": 0, "wait": 0, "t0": 1}
    s.process_closed_market(m, None)
    assert "1.1" not in s._tr
    assert any(k == "mercato_chiuso" for k, _ in detto)
    assert "pnl_settled" in s.stats, "il P&L regolato entra nelle stats"


# ===========================================================================
# R2 — lo scalper guarda l'esposizione della SELEZIONE, non solo del ciclo
# ===========================================================================
def test_r2_la_soglia_del_residuo_e_quella_dichiarata_dal_bot():
    """Un residuo di pochi centesimi NON e' chiudibile: qualunque ordine di
    chiusura sarebbe piu' grande del residuo. Pretendere lo zero assoluto
    produceva un loop di flatten (misurato: 10.743 tentativi in una partita)."""
    assert CD.RESIDUO_ACCETTATO == 0.30


def test_r2_una_selezione_pari_non_blocca_i_cicli_nuovi():
    """LA FALSIFICAZIONE: la guardia non deve spegnere il bot su una selezione
    pulita."""
    m = _Market(_Blotter([_ordine(111, "BACK", 2.0, 2.00, oid="a"),
                          _ordine(111, "LAY", 2.0, 2.00, oid="b")]))
    sb = CD.sbilancio_selezione(m, object(), 111)
    assert sb is not None and sb <= CD.RESIDUO_ACCETTATO


def test_r2_una_selezione_scoperta_supera_la_soglia():
    m = _Market(_Blotter([_ordine(111, "BACK", 2.0, 2.00, oid="a")]))
    sb = CD.sbilancio_selezione(m, object(), 111)
    assert sb is not None and sb > CD.RESIDUO_ACCETTATO


# ===========================================================================
# R3 — il freno dopo un rifiuto, sul bot vero
# ===========================================================================
def test_r3_il_flb_smette_di_ritentare_dopo_un_rifiuto():
    """Dopo un rifiuto il bot NON ripresenta l'ordine al book successivo: il
    backoff conta il tempo DI MERCATO."""
    s = _flb(lay_max=1.10, min_lay_size=1.0, min_matched=0.0, require_inplay=True)
    m = _Market(rifiuta=True)
    mb = lambda pt: _MB([_Runner(111, (1.09, 200), (1.10, 200))], pt=pt)  # noqa: E731
    s.process_market_book(m, mb(1_000_000))
    assert s._freno.quanti("1.1", 111) == 1, "il rifiuto e' stato registrato"
    # entro il backoff non si ritenta
    s.process_market_book(m, mb(1_001_000))
    assert s._freno.quanti("1.1", 111) == 1
    # passato il backoff DI MERCATO si riprova (e viene rifiutato di nuovo)
    s.process_market_book(m, mb(1_000_000 + int(CD.BACKOFF_S[0] * 1000) + 500))
    assert s._freno.quanti("1.1", 111) == 2


def test_r3_senza_rifiuti_il_flb_non_viene_frenato():
    """LA FALSIFICAZIONE: il freno non deve toccare un conto sano."""
    s = _flb(lay_max=1.10, min_lay_size=1.0, min_matched=0.0)
    m = _Market()
    s.process_market_book(
        m, _MB([_Runner(111, (1.09, 200), (1.10, 200))], pt=1_000_000))
    assert m.placed, "senza rifiuti l'ordine parte"
    assert s._freno.bloccato("1.1", 111, 1_000_000.0) is None


def test_r3_il_tetto_ferma_del_tutto_la_selezione():
    s = _flb(lay_max=1.10, min_lay_size=1.0, min_matched=0.0)
    s._freno = CD.FrenoRifiuti(tetto=2)
    m = _Market(rifiuta=True)
    t = 1_000_000
    for _ in range(6):
        s.process_market_book(m, _MB([_Runner(111, (1.09, 200), (1.10, 200))],
                                     pt=t))
        t += int(CD.BACKOFF_S[-1] * 1000) + 1_000
    assert s._freno.quanti("1.1", 111) == 2, "oltre il tetto non si ritenta piu'"


def test_r3_le_coperture_non_sono_mai_frenate():
    """Una copertura deve poter partire SEMPRE: la sicurezza vince sui costi.
    E' la stessa regola del tetto transazioni dello scalper."""
    s = _flb(lay_max=1.10, min_lay_size=1.0, min_matched=0.0)
    s._freno.registra_rifiuto("1.1", 111, 1_000_000.0)
    s._now_ms = 1_000_500
    m = _Market()
    # un ingresso ora sarebbe frenato...
    assert s._place(m, 111, "LAY", 1.09, 2.0) is None
    # ...ma una copertura no
    assert s._place(m, 111, "BACK", 1.20, 2.0, copertura=True) is not None
