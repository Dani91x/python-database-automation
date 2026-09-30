# -*- coding: utf-8 -*-
"""BANCO VELOCE (30/09): ogni risparmio di tempo ha la sua prova di equivalenza.

Standard dell'utente del 29/09 (`PROCESSO_STANDARD_BOT.md` par. 6.9): un replay piu'
veloce si accetta solo se il referto esce identico numero per numero e se ogni
struttura messa in memoria ha un test di equivalenza con la versione lenta. Le
quattro ottimizzazioni del 30/09, e per ognuna la versione lenta come metro:

1. `omega_model.lambdas_from_pre_ko` memoizzata (`_lambdas_da_quote_1x2`):
   stesso numero della catena senza cache, e la chiave usa TUTTI gli argomenti.
2. `BaseFlumine.info` calcolata solo se il log INFO di flumine e' acceso
   (`banco_comune.info_flumine_solo_se_loggata`): con INFO acceso e' la vera,
   all'uscita dal banco torna la vera, il testo dei WARNING non cambia.
3. `_VistaEx.traded_volume` convertita solo se letta: stessi livelli, presi
   all'istante della vista.
4. `ScannerReplay._vista_di`: la vista di un book GIA' CONVERTITO si riusa per
   lo stesso oggetto; un book non convertito, o convertito dopo, si rifa'.

I finti sono oggetti VERI: `MarketBook` di betfairlightweight (con le scale nella
forma di flumine), `FlumineSimulation`, `ClearedOrders`, `valuta.converti_libro`.

ASCII-only nel codice; i commenti sono in italiano.
"""
from __future__ import annotations

import logging

import flumine  # noqa: F401 - come nel banco: le scale del book diventano dict
import pytest
from betfairlightweight import resources
from betfairlightweight.resources.bettingresources import MarketBook

from flumine.events import events as fevents

from Betfair.omega import omega_model as M
from Betfair.stream import valuta
from Betfair.stream.backtest import banco_comune as BC


# ---------------------------------------------------------------------------
# 1. la catena dei lambda pre-KO memoizzata
# ---------------------------------------------------------------------------
_PRE_KO = [
    {"home": 1.75, "draw": 3.6, "away": 4.8},
    {"home": 2.9, "draw": 3.2, "away": 2.5},
    {"home": 1.25, "draw": 6.0, "away": 12.0},
    {"home": "2.1", "draw": "3.3", "away": "3.9"},      # stringhe: come arrivano da JSON
    {"home": None, "draw": 3.4, "away": 4.5},             # quota assente
    {"home": 0, "draw": 3.4, "away": 4.5},                # quota nulla
    {"home": 2, "draw": 3, "away": 4},                    # interi
    {"home": 2.0, "draw": 3.0, "away": 4.0},              # gli stessi, float
]


def _senza_cache(pre, total_goals=M.DEFAULT_TOTAL_GOALS, rho=M.DEFAULT_RHO):
    return M._lambdas_da_quote_1x2.__wrapped__(
        pre.get("home"), pre.get("draw"), pre.get("away"), total_goals, rho)


def test_lambda_pre_ko_con_cache_identici_a_senza():
    M._lambdas_da_quote_1x2.cache_clear()
    for pre in _PRE_KO:
        atteso = _senza_cache(pre)
        for _ in range(3):                       # vuota, poi piena, poi piena
            assert M.lambdas_from_pre_ko(dict(pre)) == atteso, pre
    assert M._lambdas_da_quote_1x2.cache_info().hits >= 2 * len(_PRE_KO)


def test_lambda_pre_ko_forme_insolite_come_prima():
    assert M.lambdas_from_pre_ko(None) is None
    assert M.lambdas_from_pre_ko("x") is None
    # una quota NON hashabile non rompe niente: si calcola senza cache
    assert M.lambdas_from_pre_ko({"home": [2.0], "draw": 3.0, "away": 4.0}) is None


@pytest.mark.parametrize("argomento", ["home", "draw", "away", "total_goals", "rho"])
def test_la_chiave_usa_ogni_argomento(argomento):
    """FALSIFICAZIONE incorporata: cambiando UN solo argomento il risultato vero
    cambia, quindi una chiave che lo ignorasse darebbe il numero sbagliato. Si
    controlla che la cache dia quello vero anche alla seconda chiamata."""
    M._lambdas_da_quote_1x2.cache_clear()
    base = {"home": 1.75, "draw": 3.6, "away": 4.8}
    kw_a = {"total_goals": 2.4, "rho": M.DEFAULT_RHO}
    pre_b, kw_b = dict(base), dict(kw_a)
    if argomento in base:
        pre_b[argomento] = base[argomento] * 1.2
    elif argomento == "total_goals":
        # il ripiego conta solo se il pareggio e' fuori banda: quota X altissima
        base = {"home": 1.9, "draw": 60.0, "away": 2.1}
        pre_b = dict(base)
        kw_b["total_goals"] = 3.1
    else:
        kw_b["rho"] = -0.05
    a = M.lambdas_from_pre_ko(dict(base), **kw_a)
    b = M.lambdas_from_pre_ko(dict(pre_b), **kw_b)
    assert _senza_cache(base, **kw_a) != _senza_cache(pre_b, **kw_b), (
        f"cambiare {argomento} non cambia il risultato: il campione non falsifica")
    assert a == _senza_cache(base, **kw_a)
    assert b == _senza_cache(pre_b, **kw_b)


# ---------------------------------------------------------------------------
# 2. BaseFlumine.info solo se il suo log e' acceso
# ---------------------------------------------------------------------------
@pytest.fixture
def livello_flumine():
    log = logging.getLogger("flumine.baseflumine")
    prima = log.level
    yield log
    log.setLevel(prima)


def _quadro():
    from flumine import FlumineSimulation

    return FlumineSimulation(client=BC.cliente_simulato())


def test_info_vera_se_il_log_info_e_acceso(livello_flumine):
    from flumine.baseflumine import BaseFlumine

    vera = BaseFlumine.__dict__["info"]
    q = _quadro()
    livello_flumine.setLevel(logging.INFO)
    with BC.simulazione_flumine():
        dentro = q.info
    atteso = vera.fget(q)
    assert set(dentro) == set(atteso) == {"clients", "markets", "streams",
                                          "logging_controls", "threads"}
    for k in ("clients", "markets", "streams", "logging_controls"):
        assert dentro[k] == atteso[k], k


def test_info_vuota_se_il_log_info_e_spento_e_ripristino(livello_flumine):
    from flumine.baseflumine import BaseFlumine

    vera = BaseFlumine.__dict__["info"]
    q = _quadro()
    livello_flumine.setLevel(logging.WARNING)
    with BC.simulazione_flumine():
        assert q.info == {}
        assert BaseFlumine.__dict__["info"] is not vera
    assert BaseFlumine.__dict__["info"] is vera, "la info vera non e' tornata"
    assert q.info["markets"] == {"market_count": 0, "open_market_count": 0}


class _Raccolta(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        self.righe = []

    def emit(self, record):
        self.righe.append(self.format(record))


def _warning_di_flumine(livello_flumine, dentro_il_banco: bool):
    """Il solo record che nasce a WARNING: il mercato assente alla pulizia."""
    q = _quadro()
    raccolta = _Raccolta()
    livello_flumine.addHandler(raccolta)
    livello_flumine.setLevel(logging.WARNING)
    try:
        cleared = resources.ClearedOrders(moreAvailable=False, clearedOrders=[])
        cleared.market_id = "1.999"
        evento = fevents.ClearedOrdersEvent(cleared)
        if dentro_il_banco:
            with BC.simulazione_flumine():
                q._process_cleared_orders(evento)
        else:
            q._process_cleared_orders(evento)
    finally:
        livello_flumine.removeHandler(raccolta)
    return raccolta.righe


def test_il_testo_dei_warning_non_cambia(livello_flumine):
    fuori = _warning_di_flumine(livello_flumine, dentro_il_banco=False)
    dentro = _warning_di_flumine(livello_flumine, dentro_il_banco=True)
    assert fuori == dentro
    assert fuori == ["WARNING:flumine.baseflumine:Market 1.999 not present when clearing"]


# ---------------------------------------------------------------------------
# 3 e 4. le viste del book per lo scanner
# ---------------------------------------------------------------------------
def _book(back=2.0, size=10.0, tv=((2.0, 50.0), (2.02, 7.5)), mid="1.500"):
    return MarketBook(
        marketId=mid, isMarketDataDelayed=False, status="OPEN", betDelay=5,
        bspReconciled=False, complete=True, inplay=True, numberOfWinners=1,
        numberOfRunners=2, numberOfActiveRunners=2, totalMatched=123.4,
        totalAvailable=0, crossMatching=False, runnersVoidable=False, version=1,
        runners=[{"selectionId": sid, "status": "ACTIVE", "handicap": 0.0,
                  "totalMatched": 11.0 * (i + 1), "lastPriceTraded": back + i,
                  "ex": {"availableToBack": [{"price": back + i, "size": size},
                                             {"price": back + i - 0.02, "size": 3.0}],
                         "availableToLay": [{"price": back + i + 0.02, "size": size / 2}],
                         "tradedVolume": [{"price": p, "size": s} for p, s in tv]}}
                 for i, sid in enumerate((101, 102))])


def _livelli(xs):
    return [(x.price, x.size) for x in xs]


def _impronta(v):
    """Tutti i campi della vista, nella forma che si confronta."""
    return (v.market_id, v.inplay, v.status, v.total_matched, v.bet_delay,
            v.market_definition, v.publish_time,
            [(r.selection_id, r.status, r.last_price_traded, r.total_matched,
              _livelli(r.ex.available_to_back), _livelli(r.ex.available_to_lay),
              _livelli(r.ex.traded_volume)) for r in v.runners])


def test_traded_volume_pigro_uguale_a_quello_di_prima():
    mb = _book()
    for r in mb.runners:
        vista = BC._VistaEx(r.ex)
        assert _livelli(vista.traded_volume) == _livelli(
            BC._livelli_di_produzione(r.ex.traded_volume))
        assert _livelli(vista.traded_volume) == [(2.0, 50.0), (2.02, 7.5)]
        assert vista.traded_volume is vista.traded_volume     # convertito una volta
    assert BC._VistaEx(None).traded_volume == []


def test_traded_volume_preso_all_istante_della_vista():
    """La vista legge la scala quando nasce, come prima: se dopo il book cambia
    scala (la conversione ne mette una NUOVA), la vista vecchia non cambia."""
    mb = _book()
    ex = mb.runners[0].ex
    vista = BC._VistaEx(ex)
    ex.traded_volume = [{"price": 9.0, "size": 1.0}]
    assert _livelli(vista.traded_volume) == [(2.0, 50.0), (2.02, 7.5)]


def test_traded_volume_assegnabile_come_un_campo():
    vista = BC._VistaEx(_book().runners[0].ex)
    vista.traded_volume = None
    assert vista.traded_volume is None
    vista.traded_volume = [1]
    assert vista.traded_volume == [1]


@pytest.fixture
def scanner():
    return BC.ScannerReplay()


def test_vista_riusata_solo_per_lo_stesso_book_convertito(scanner):
    cambio = valuta.CambioGbpEur(fisso=1.2)
    mb = valuta.converti_libro(_book(), cambio)
    a = scanner._vista_di(mb)
    b = scanner._vista_di(mb)
    assert a is b, "stesso book convertito: la vista si riusa"
    assert _impronta(a) == _impronta(BC.libro_di_produzione(mb))
    altro = valuta.converti_libro(_book(back=2.5), cambio)
    c = scanner._vista_di(altro)
    assert c is not a and _impronta(c) == _impronta(BC.libro_di_produzione(altro))
    # di nuovo il primo (non piu' l'ultimo del mercato): vista rifatta, uguale
    assert _impronta(scanner._vista_di(mb)) == _impronta(a)


def test_book_non_convertito_si_rifa_sempre_e_la_conversione_si_vede(scanner):
    """FALSIFICAZIONE incorporata: la vista presa PRIMA della conversione ha le
    size in GBP; se la cache la tenesse anche dopo, lo scanner leggerebbe GBP."""
    mb = _book(size=10.0)
    a = scanner._vista_di(mb)
    b = scanner._vista_di(mb)
    assert a is not b
    assert _livelli(a.runners[0].ex.available_to_back)[0] == (2.0, 10.0)
    valuta.converti_libro(mb, valuta.CambioGbpEur(fisso=1.2))
    c = scanner._vista_di(mb)
    assert _livelli(c.runners[0].ex.available_to_back)[0] == (2.0, 12.0)
    assert _impronta(c) == _impronta(BC.libro_di_produzione(mb))
