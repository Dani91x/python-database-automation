"""BANCO 08/10 - IL MERCATO CHE ATTRAVERSA: l'ordine appoggiato a P e' abbinato a
P quando il mercato SCAMBIA OLTRE P (``banco_comune``, testata 6-quater,
``MotoreReplay._mercato_che_attraversa``).

Reperto (35768297, O/U 2,5, Under 47972): banca 10,20 @2,02 appoggiata alle
23:15:40 UTC con 902,94 davanti; a 2,02 si scambiano 685,86 (meno della coda);
alle 23:18:01 il mercato scambia a 2,00. Il banco (coda di flumine) la abbinava
alle 23:21:53; su Betfair e' abbinata alle 23:18:01.

Tutto con oggetti VERI: ``FlumineSimulation`` + ``SimulatedMiddleware`` (uno),
``MotoreReplay`` del banco (bet delay atteso a tempo di mercato), ``MarketBook``
e ``RunnerBook`` di betfairlightweight con le chiavi dello stream (ladder e
``tradedVolume`` CUMULATIVO, come lo manda Betfair), ``LimitOrder`` LAPSE.
ASCII-only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import pytest

from Betfair.stream.backtest import banco_comune as B

MID = "1.259557067"
SEL, ALTRO = 47972, 47973
T0 = 1783034140000          # 23:15:40 UTC del 02/07/2026, come il reperto
DELAY = 5                   # betDelay in gioco del reperto


def _lv(livelli: Sequence[Tuple[float, float]]) -> List[Dict[str, float]]:
    return [{"price": p, "size": s} for p, s in livelli]


def _book(t_s: float, *, atb=(), atl=(), tv=(), stato: str = "OPEN") -> Any:
    """Un ``MarketBook`` VERO in gioco. ``tv`` = tradedVolume CUMULATIVO per prezzo."""
    from betfairlightweight.resources.bettingresources import MarketBook

    def runner(sid: int, atb_, atl_, tv_) -> Dict[str, Any]:
        return {"selectionId": sid, "handicap": 0.0, "status": "ACTIVE",
                "adjustmentFactor": None, "lastPriceTraded": None, "totalMatched": 0.0,
                "ex": {"availableToBack": _lv(atb_), "availableToLay": _lv(atl_),
                       "tradedVolume": _lv(tv_)}}

    return MarketBook(
        marketId=MID, isMarketDataDelayed=False, status=stato, betDelay=DELAY,
        bspReconciled=False, complete=True, inplay=True, numberOfWinners=1,
        numberOfRunners=2, numberOfActiveRunners=2, totalMatched=1000.0,
        totalAvailable=0.0, crossMatching=True, runnersVoidable=False, version=7,
        publishTime=int(T0 + t_s * 1000),
        runners=[runner(SEL, atb, atl, tv), runner(ALTRO, (), (), ())])


class _Scena:
    """Quadro flumine VERO + motore del banco. ``libri`` = i book che arrivano DOPO
    il primo (il motore li pompa durante il bet delay e con ``avanza``)."""

    def __init__(self, primo: Any, libri: Sequence[Any]) -> None:
        from flumine import BaseStrategy, FlumineSimulation

        class _Strategia(BaseStrategy):
            def check_market_book(self, market, market_book):  # pragma: no cover
                return False

            def process_market_book(self, market, market_book):  # pragma: no cover
                return None

        self.q = FlumineSimulation(client=B.cliente_simulato())
        assert B.assicura_middleware_simulato(self.q) == 1
        self.strategia = _Strategia(market_filter={}, max_order_exposure=1000,
                                    max_selection_exposure=1000)
        self.q.add_strategy(self.strategia)
        self.motore = B.MotoreReplay(self.q)
        self.motore._gen = iter([[mb] for mb in libri])
        self.mercato, _ = self.motore._a_flumine(primo)

    def piazza(self, lato: str, prezzo: float, size: float) -> Any:
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade

        trade = Trade(market_id=MID, selection_id=SEL, handicap=0.0,
                      strategy=self.strategia)
        ordine = trade.create_order(side=lato, order_type=LimitOrder(
            price=prezzo, size=size, persistence_type="LAPSE"))
        assert self.mercato.place_order(ordine) is not False
        # la REST sincrona: il tempo di mercato scorre per place_latency + betDelay
        self.motore.attendi_esecuzione(MID)
        return ordine

    def avanza_tutto(self) -> None:
        while self.motore.avanza_un_book() is not None:
            pass


def _gira(primo: Any, libri: Sequence[Any], lato: str, prezzo: float, size: float,
          attraversa: bool = True, dopo_piazzamento: Any = None) -> Tuple[Any, _Scena]:
    vecchio = B.ATTRAVERSAMENTO
    B.ATTRAVERSAMENTO = attraversa
    try:
        with B.simulazione_flumine():
            sc = _Scena(primo, libri)
            with sc.q.simulated_datetime:
                sc.q.simulated_datetime(primo.publish_time)
                ordine = sc.piazza(lato, prezzo, size)
                if dopo_piazzamento is not None:
                    dopo_piazzamento(ordine)
                sc.avanza_tutto()
        return ordine, sc
    finally:
        B.ATTRAVERSAMENTO = vecchio


def _ms(t_s: float) -> int:
    return int(T0 + t_s * 1000)


def _coda_lay(tv_202: float = 0.0, extra=()) -> Dict[str, Any]:
    return {"atb": [(2.02, 900.0), (2.0, 150.0)], "atl": [(2.04, 100.0)],
            "tv": [(2.02, tv_202)] + list(extra) if tv_202 else list(extra)}


# ---------------------------------------------------------------------------
# (a) LAY 2,02, coda 900: 600 scambiati a 2,02 (coda non consumata), poi uno
#     scambio a 2,00 -> abbinata a 2,02 all'istante dello scambio a 2,00
# ---------------------------------------------------------------------------
def _libri_a() -> Tuple[Any, List[Any]]:
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 3, 4, 5, 6)]
    # 1200 di volume a 2,02 = 600 per la coda di flumine (meta'): 300 restano davanti
    libri.append(_book(10, **_coda_lay(1200.0)))
    libri.append(_book(20, atb=[(2.0, 150.0)], atl=[(2.0, 187.0)],
                       tv=[(2.02, 1200.0), (2.0, 69.93)]))
    libri.append(_book(30, atb=[(1.98, 50.0)], atl=[(2.0, 80.0)],
                       tv=[(2.02, 1200.0), (2.0, 69.93), (1.98, 10.0)]))
    return primo, libri


def test_a_lay_abbinata_quando_il_mercato_scambia_sotto():
    primo, libri = _libri_a()
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    sim = ordine.simulated
    assert sim.matched == [[_ms(20), 2.02, 10.2]], sim.matched
    assert ordine.size_matched == 10.2 and ordine.average_price_matched == 2.02
    assert sim.fill_attraversati == [{
        "ms": _ms(20), "market_id": MID, "selection_id": SEL, "side": "LAY",
        "prezzo": 2.02, "size": 10.2, "prezzo_oltre": 2.0, "ordine": str(ordine.id),
        "motivo": "attraversato"}]
    assert len(sc.motore.fill_attraversati) == 1
    assert ordine.status.name == "EXECUTION_COMPLETE"


def test_a_senza_la_regola_resta_in_coda():
    """Il modello di sola coda (com'era): con la regola spenta la stessa banca NON
    e' abbinata allo scambio a 2,00 (e' il reperto)."""
    primo, libri = _libri_a()
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20, attraversa=False)
    assert ordine.simulated.matched == []
    assert sc.motore.fill_attraversati == []
    assert getattr(ordine.simulated, "fill_attraversati", None) is None


# ---------------------------------------------------------------------------
# (b) stesso, ma scambi SOLO a 2,02: resta in coda come oggi
# ---------------------------------------------------------------------------
def test_b_scambi_solo_al_suo_prezzo_resta_in_coda():
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 3, 4, 5, 6)]
    libri.append(_book(10, **_coda_lay(1200.0)))
    libri.append(_book(20, **_coda_lay(1500.0)))   # +300 a 2,02: coda 300 -> 150
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert ordine.simulated.matched == []
    # la coda davanti non e' finita (la quota esatta dipende dal modello di flumine)
    assert ordine.simulated._piq > 0
    assert sc.motore.fill_attraversati == []
    assert ordine.status.name == "EXECUTABLE"


def test_b_offerte_che_si_spostano_senza_scambi_non_abbinano():
    """Il SOLO spostamento delle offerte (ladder a 2,00, nessun volume nuovo) non
    e' uno scambio: niente fill."""
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 3, 4, 5, 6)]
    libri.append(_book(20, atb=[(1.98, 500.0)], atl=[(2.0, 300.0)], tv=[]))
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert ordine.simulated.matched == [] and sc.motore.fill_attraversati == []


# ---------------------------------------------------------------------------
# (c) BACK 2,10 e scambio a 2,12 -> abbinata a 2,10
# ---------------------------------------------------------------------------
def test_c_back_abbinata_quando_il_mercato_scambia_sopra():
    def b(t, tv=()):
        return _book(t, atb=[(2.08, 100.0)], atl=[(2.1, 500.0)], tv=tv)

    primo = b(0)
    libri = [b(t) for t in (1, 2, 3, 4, 5, 6)]
    libri.append(b(10, tv=[(2.1, 200.0)]))                 # coda 500 -> 400
    libri.append(b(20, tv=[(2.1, 200.0), (2.12, 15.0)]))   # scambio OLTRE: 2,12
    ordine, sc = _gira(primo, libri, "BACK", 2.10, 10.0)
    assert ordine.simulated.matched == [[_ms(20), 2.1, 10.0]]
    v = ordine.simulated.fill_attraversati[0]
    assert (v["side"], v["prezzo"], v["prezzo_oltre"], v["motivo"]) == (
        "BACK", 2.1, 2.12, "attraversato")


# ---------------------------------------------------------------------------
# (d) ordine ancora nel bet delay quando il mercato attraversa: NON abbinato
#     finche' non e' vivo
# ---------------------------------------------------------------------------
def test_d_attraversamento_durante_il_bet_delay_non_abbina():
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2)]
    # a t=3 (ordine ancora nel bet delay, 5,12 s) il mercato scambia a 2,00
    libri.append(_book(3, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 69.93)]))
    libri += [_book(t, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 69.93)])
              for t in (4, 5, 6, 10)]
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert sc.motore.fill_attraversati == []
    assert ordine.simulated.matched == [], ordine.simulated.matched
    assert ordine.status.name == "EXECUTABLE"


def test_d_scambio_oltre_nel_book_del_piazzamento_non_anticipa():
    """Lo scambio a 2,00 arriva nel book (t=6) su cui l'ordine diventa vivo: puo'
    essere avvenuto PRIMA che l'ordine esistesse, nel dubbio non si anticipa.
    Al book dopo, con un nuovo scambio oltre, si abbina."""
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 4)]
    libri.append(_book(6, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 5.0)]))
    libri.append(_book(8, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 5.0)]))
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert ordine.simulated.matched == [] and sc.motore.fill_attraversati == []
    libri.append(_book(9, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 6.0)]))
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert ordine.simulated.matched == [[_ms(9), 2.02, 10.2]]


def test_d_vivo_dopo_il_delay_abbina_al_primo_scambio_oltre():
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 4, 6)]
    libri.append(_book(8, atb=[(2.02, 900.0)], atl=[(2.04, 100.0)], tv=[(2.0, 5.0)]))
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    assert ordine.simulated.matched == [[_ms(8), 2.02, 10.2]]
    assert ordine.simulated.fill_attraversati[0]["ms"] == _ms(8)


# ---------------------------------------------------------------------------
# (e) parziale: la parte gia' abbinata (dalla coda, a P) resta, il residuo e'
#     abbinato a P allo scambio oltre
# ---------------------------------------------------------------------------
def test_e_parziale_residuo_abbinato_parte_abbinata_invariata():
    primo = _book(0, **_coda_lay())
    libri = [_book(t, **_coda_lay()) for t in (1, 2, 3, 4, 5, 6)]
    # 1810 a 2,02: la coda davanti (900) si consuma e una parte nostra si abbina
    libri.append(_book(10, **_coda_lay(1810.0)))
    # uno scambio PICCOLO a 2,00: la coda di flumine ne darebbe solo la meta',
    # su Betfair il residuo e' abbinato tutto
    libri.append(_book(20, atb=[(2.0, 150.0)], atl=[(2.0, 187.0)],
                       tv=[(2.02, 1810.0), (2.0, 2.0)]))
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    m = ordine.simulated.matched
    # il parziale della CODA (a t=10, a 2,02) resta com'e'
    assert m[0][0] == _ms(10) and m[0][1] == 2.02 and 0 < m[0][2] < 10.2
    # a t=20: la coda di flumine da' la sua meta' dello scambio (in EUR: il banco
    # converte le scale GBP), il residuo e' abbinato a 2,02 dalla regola
    assert m[1][:2] == [_ms(20), 2.02] and 0 < m[1][2] < 2.0, m
    assert m[2] == [_ms(20), 2.02, round(10.2 - m[0][2] - m[1][2], 2)], m
    assert len(m) == 3
    assert ordine.size_matched == 10.2 and ordine.average_price_matched == 2.02
    assert [v["size"] for v in ordine.simulated.fill_attraversati] == [m[2][2]]


def test_e_campi_dello_specchio_portano_il_motivo():
    """Lo specchio (``varianti_bot.campi_ordine``) porta ``_fill_attraversato``
    SOLO sull'ordine abbinato cosi'; senza, la chiave non c'e'."""
    from Betfair.stream.backtest import varianti_bot as VB

    primo, libri = _libri_a()
    ordine, _sc = _gira(primo, libri, "LAY", 2.02, 10.20)
    campi = VB.campi_ordine(ordine)
    assert campi["_fill_attraversato"][0]["motivo"] == "attraversato"
    assert campi["_fill_attraversato"][0]["ms"] == _ms(20)
    spento, _ = _gira(*_libri_a(), "LAY", 2.02, 10.20, attraversa=False)
    assert "_fill_attraversato" not in VB.campi_ordine(spento)


def test_e_guasto_con_tetto_niente_voce_senza_abbinato():
    """Lo scenario «chiusura-abbinata-in-parte» avvolge ``_update_matched`` con un
    tetto (``chiusura_parziale``): se il tetto rifiuta il fill, il referto NON deve
    raccontare un fill attraversato che non c'e' stato."""
    from Betfair.stream.backtest.chiusura_parziale import GuastoChiusuraParziale

    def tetto(ordine):
        GuastoChiusuraParziale._tetta_abbinato(ordine.simulated, 0.0)

    primo, libri = _libri_a()
    ordine, sc = _gira(primo, libri, "LAY", 2.02, 10.20, dopo_piazzamento=tetto)
    assert ordine.simulated.matched == []
    assert sc.motore.fill_attraversati == []
    assert getattr(ordine.simulated, "fill_attraversati", None) is None

    def tetto_4(ordine):
        GuastoChiusuraParziale._tetta_abbinato(ordine.simulated, 4.0)

    ordine, sc = _gira(*_libri_a(), "LAY", 2.02, 10.20, dopo_piazzamento=tetto_4)
    assert ordine.simulated.matched == [[_ms(20), 2.02, 4.0]]
    assert [v["size"] for v in sc.motore.fill_attraversati] == [4.0]
