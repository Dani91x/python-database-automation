"""CANTIERE S-bis (29/09) - SNIPER calcio: i gemelli dei difetti corretti nello
scalper (cantiere S): chiusura doppia col cancel in volo, sostituto del
place-and-trim non agganciato, piatta dichiarata con ordini vivi o sequenze,
parcheggio della sequenza ritirato a ogni book dal flatten, sequenza col
parcheggio morto che aspetta per sempre, ULTIMA SPIAGGIA che accetta una
posizione piazzabile o a prezzi assenti.

Il bot VERO (``SniperStrategy`` coi parametri che gli passa la sessione:
uscite esatte, multipli 0,50, minimi .it, stake 10) riceve book VERI (mcm
Betfair -> ``StreamListener``) da un ``Flumine`` VERO col client paper della
sessione scalper (``_order_client_kwargs``). Esecuzione DIFFERITA di 1 e 4
book. Il test consegna i book SOLO con ``process_market_book``.

A OGNI book, per la selezione Under (lo sniper spara solo li'):
  * K5/K6 (posizione dichiarata chiusa: niente ingressi, niente close, non in
    chiusura): esposizione abbinata VERA entro la tolleranza che lo sniper
    stesso usa per dirsi piatto (``is_flat``: max(0,02; residuo accettato +
    0,02)), nessun suo ordine vivo o in volo, nessuna sequenza in corso;
  * B2 (lo sniper e' in gioco per progetto: il suo "fischio" e' la FINE
    FINESTRA ``inplay_to_s``): fuori finestra la posizione si chiude e non si
    accetta mai come residuo una posizione piazzabile.
"""
from __future__ import annotations

import json
import queue
from typing import Any, Dict, List, Tuple

import betfairlightweight
import pytest
from betfairlightweight import filters
from betfairlightweight.streaming.listener import StreamListener
from flumine import Flumine, clients
from flumine.events.events import MarketBookEvent

from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper import sniper_bot as SN
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)

MID = "1.259819700"
UNDER = 47973
OVER = 47974
KO_MS = 1_759_140_000_000


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


class BancoSniper:
    """Flumine VERO (client paper della sessione), sniper VERO, book veri."""

    def __init__(self, **extra: Any) -> None:
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        client = clients.BetfairClient(api, **SS._order_client_kwargs(True))
        self.fw = Flumine(client=client)
        self.client = client
        params: Dict[str, Any] = {
            # come `scalper_session` arma lo sniper
            "stake": 10.0, "dry_run": False, "exact_exits": True,
            "size_step": 0.5, "live_min_bet": 2.0, "uscite_automatiche": True,
            # ingressi spenti coi soli numeri (le posizioni le mette il test)
            "min_size": 1e12,
        }
        params.update(extra)
        self.strat = SN.SniperStrategy(
            market_filter=filters.streaming_market_filter(market_ids=[MID]),
            sniper_params=params, max_selection_exposure=30.0,
            max_order_exposure=30.0, max_trade_count=int(1e6),
            max_live_trade_count=int(1e6))
        self.righe: List[Tuple[str, Dict[str, Any]]] = []
        self.strat.event_sink = lambda k, p: self.righe.append((k, dict(p)))
        self.fw.add_strategy(self.strat)
        self.q: "queue.Queue[Any]" = queue.Queue()
        self.lis = StreamListener(output_queue=self.q, max_latency=None)
        self.lis.register_stream(9, "marketSubscription")
        self.pt = KO_MS + 1_200_000             # 20' di gioco, in finestra
        self.uid = 0
        self.ladder: Dict[int, Tuple[float, float]] = {UNDER: (1.5, 1.51), OVER: (2.96, 3.0)}
        self.trd: Dict[int, Dict[float, float]] = {}
        self.senza_scambi: set = set()

    def book(self, passo_ms: int = 1000, muto_prezzi: bool = False) -> Any:
        self.pt += passo_ms
        self.uid += 1
        rc = []
        for sid, (bb, bl) in self.ladder.items():
            r: Dict[str, Any] = {"id": sid}
            if muto_prezzi:
                r["batb"], r["batl"] = [], []
            else:
                r["batb"] = [[0, bb, 50.0], [1, round(bb - 0.01, 2), 50.0]]
                r["batl"] = [[0, bl, 50.0], [1, round(bl + 0.01, 2), 50.0]]
                tv = self.trd.setdefault(sid, {})
                if sid not in self.senza_scambi:
                    for p in (bb, bl):
                        tv[p] = tv.get(p, 0.0) + 20.0
            if self.trd.get(sid):
                r["trd"] = [[p, v] for p, v in sorted(self.trd[sid].items())]
            rc.append(r)
        mcm = {
            "op": "mcm", "id": 9, "clk": "C%d" % self.uid, "pt": self.pt,
            "initialClk": "I", "ct": "SUB_IMAGE",
            "mc": [{"id": MID, "img": True, "marketDefinition": {
                "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
                "marketBaseRate": 5.0, "eventId": "35797769", "eventTypeId": "1",
                "numberOfWinners": 1, "bettingType": "ODDS",
                "marketType": "OVER_UNDER_15",
                "marketTime": _iso(KO_MS), "suspendTime": _iso(KO_MS),
                "bspReconciled": False, "complete": True, "inPlay": True,
                "crossMatching": True, "runnersVoidable": False,
                "numberOfActiveRunners": 2, "betDelay": 0, "status": "OPEN",
                "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": UNDER},
                            {"status": "ACTIVE", "sortPriority": 2, "id": OVER}],
                "regulators": ["MR_INT"], "countryCode": "IT", "discountAllowed": True,
                "timezone": "Europe/Rome", "openDate": _iso(KO_MS), "version": 1},
                "rc": rc}]}
        self.lis.on_data(json.dumps(mcm))
        books = self.q.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))
        m = self.fw.markets.markets[MID]
        if self.strat.check_market_book(m, m.market_book):
            self.strat.process_market_book(m, m.market_book)
        return m

    @property
    def market(self) -> Any:
        return self.fw.markets.markets[MID]

    def pos(self) -> Any:
        return self.strat._p(MID, UNDER)

    def abbinato(self, lato: str, prezzo: float, size: float) -> Any:
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade
        tr = Trade(MID, UNDER, 0, self.strat)
        o = tr.create_order(lato, LimitOrder(prezzo, size))
        o.update_client(self.client)
        o.simulated.matched = [[0, prezzo, size]]
        o.simulated.size_matched = size
        o.simulated.average_price_matched = prezzo
        o.execution_complete()
        self.market.blotter[o.id] = o
        return o


def esposizione_vera(b: BancoSniper) -> Tuple[float, float]:
    righe = [CERT.riga_ordine(o) for o in b.market.blotter.strategy_orders(b.strat)
             if int(getattr(o, "selection_id", 0) or 0) == UNDER]
    return CERT.esposizione(righe)


def vivi(b: BancoSniper) -> List[Any]:
    return [o for o in b.market.blotter.strategy_orders(b.strat)
            if int(getattr(o, "selection_id", 0) or 0) == UNDER
            and SN.SniperStrategy._has_live(o)]


def chiusa(pos: Any) -> bool:
    return not pos.entries and pos.close is None and not pos.flattening


def tolleranza(pos: Any) -> float:
    return max(0.02, float(pos.residual_accepted) + 0.02)


def invarianti(b: BancoSniper, i: int) -> List[str]:
    out: List[str] = []
    pos = b.pos()
    if chiusa(pos):
        w, l = esposizione_vera(b)
        if abs(w - l) > tolleranza(pos) + 1e-6:
            out.append("book %d K5: chiusa con sbilancio %.2f (w %.2f, l %.2f) oltre %.2f"
                       % (i, abs(w - l), w, l, tolleranza(pos)))
        v = vivi(b)
        if v or pos.submins:
            out.append("book %d K6: chiusa con vivi=%s sequenze=%d" % (
                i, [(o.side, float(o.order_type.price), float(o.size_remaining)) for o in v],
                len(pos.submins)))
    return out


def giri(b: BancoSniper, svuota: Any, n: int, muto_prezzi: bool = False) -> List[str]:
    viol: List[str] = []
    for i in range(n):
        svuota()
        b.book(muto_prezzi=muto_prezzi)
        viol += invarianti(b, i)
    return viol


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def orologio_mercato(monkeypatch):
    """Come il banco del replay: `time.time` = ora del book corrente."""
    import time as _time
    stato: Dict[str, Any] = {"banco": None}
    monkeypatch.setattr(_time, "time",
                        lambda: (stato["banco"].pt / 1000.0) if stato["banco"] else 0.0)
    return stato


def _in_chiusura(size: float, prezzo: float = 1.5, **extra: Any) -> BancoSniper:
    """Un ingresso BACK Under ABBINATO e la chiusura avviata (come dopo uno
    stop, un timeout firmato o il force-flat)."""
    b = BancoSniper(**extra)
    b.book()
    pos = b.pos()
    pos.entries = [b.abbinato("BACK", prezzo, size)]
    b.strat._begin_flatten(b.market, pos)
    return b


# ---------------------------------------------------------------------------
@pytest.mark.parametrize("size", [0.4, 1.0, 3.3, 10.0])
def test_chiusura_esatta_senza_ordini_vivi_ne_sequenze(size, differita, orologio_mercato):
    """BACK Under abbinato @1,50; la chiusura e' una LAY ~size*1,5/1,51 a
    quota fuori multiplo: parte diretta + resto col place-and-trim. La
    posizione si dichiara chiusa solo piatta, senza ordini vivi ne' sequenze,
    qualunque sia la latenza."""
    b = _in_chiusura(size)
    orologio_mercato["banco"] = b
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    w, l = esposizione_vera(b)
    assert abs(w - l) <= tolleranza(b.pos()) + 1e-9, (w, l, b.righe[-8:])
    assert chiusa(b.pos())
    assert vivi(b) == []


def test_il_parcheggio_della_sequenza_non_si_ritira_a_ogni_book(differita,
                                                               orologio_mercato):
    """Prima `_drive_flatten` ritirava A OGNI BOOK ogni ordine vivo della
    posizione, parcheggio compreso: la sequenza del resto moriva al taglio o
    prima (abort) e il resto non si chiudeva mai col place-and-trim."""
    b = _in_chiusura(3.3)
    orologio_mercato["banco"] = b
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    passi = [r[1].get("step") for r in b.righe if r[0] == "submin_step"]
    assert "done" in passi, [r for r in b.righe if r[0].startswith("submin")]
    assert not [r for r in b.righe if r[0] == "submin_abort"], \
        [r for r in b.righe if r[0].startswith("submin")]


def test_nessuna_chiusura_doppia_col_cancel_in_volo(differita, orologio_mercato):
    """Una chiusura LAY a mercato ancora viva (il book non l'ha presa) viene
    ritirata dal flatten per ripiazzarla piu' aggressiva: finche' il cancel e'
    IN VOLO (Cancelling) la vecchia puo' ancora abbinarsi. Prima lo sniper
    ripiazzava subito la chiusura: con la vecchia abbinata, chiusura DOPPIA
    e posizione ROVESCIATA (il reperto del maker, 35797769)."""
    b = _in_chiusura(10.0)
    orologio_mercato["banco"] = b
    pos = b.pos()
    # una chiusura precedente ancora VIVA, a quota non presa dal book
    vecchia = b.strat._place(b.market, UNDER, "LAY", 1.49, 10.0, floor=False, pos=None)
    assert vecchia is not None
    for _ in range(differita.ritardo):
        differita()
    b.strat._track(pos, vecchia)
    b.book()                                  # il flatten ritira la vecchia
    assert str(vecchia.status.value) == "Cancelling"
    # mentre il cancel e' in coda, la vecchia si abbina (scambi a 1,49)
    b.ladder[UNDER] = (1.49, 1.5)
    viol: List[str] = []
    rovesciata: List[Tuple[int, float, float]] = []
    for i in range(126):
        if i >= 6:
            differita()
        b.book()
        viol += invarianti(b, i)
        w, l = esposizione_vera(b)
        # posizione iniziale LONG (BACK: se vince > se perde): una chiusura
        # doppia la ROVESCIA (se perde > se vince oltre la tolleranza)
        if l - w > tolleranza(pos) + 1e-6:
            rovesciata.append((i, round(w, 2), round(l, 2)))
    assert viol == [], viol[:3]
    assert rovesciata == [], rovesciata[:3]
    w, l = esposizione_vera(b)
    assert abs(w - l) <= tolleranza(pos) + 1e-9, (w, l)


def test_sostituto_agganciato_nessun_residuo_fantasma(differita, orologio_mercato):
    """Il SOSTITUTO del rimpiazzo nasce book dopo la fine della sequenza: prima
    non si agganciava e lo sniper vedeva un resto che non c'era (residuo
    accettato fantasma o chiusura ripiazzata = posizione rovesciata)."""
    b = _in_chiusura(10.0)
    orologio_mercato["banco"] = b
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    ids = {id(o) for o in b.pos().flatten_orders}
    for o in b.market.blotter.strategy_orders(b.strat):
        assert id(o) in ids, ("ordine non agganciato", o.side,
                              float(o.order_type.price), float(o.size_matched))
    w, l = esposizione_vera(b)
    nw, nl = b.strat._real_net(b.pos())
    assert abs(w - nw) <= 0.011 and abs(l - nl) <= 0.011, ((w, l), (nw, nl))


def test_piatta_con_un_ordine_vivo_non_si_dichiara_chiusa(differita, orologio_mercato):
    """Posizione gia' piatta (BACK 1,00 @1,50 + LAY 0,99 @1,51... qui pari
    esatta) con un ordine VIVO a quota non abbinabile nella posizione (LAY
    2,00 @1,01 come un parcheggio): prima la piatta si dichiarava con quel
    ordine a mercato (K6). Ora si ritira e si dichiara dopo."""
    b = _in_chiusura(2.0)
    orologio_mercato["banco"] = b
    pos = b.pos()
    b.strat._track(pos, b.abbinato("LAY", 1.5, 2.0))
    vivo = b.strat._place(b.market, UNDER, "LAY", 1.01, 2.0, floor=False, pos=None)
    assert vivo is not None
    b.strat._track(pos, vivo)
    viol = giri(b, differita, 12)
    assert viol == [], viol[:3]
    assert chiusa(pos)
    assert vivi(b) == []


def test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_chiusura(differita,
                                                                     orologio_mercato):
    """Il parcheggio della sequenza viene ritirato da un'altra via prima del
    taglio: `advance_submin` in PLACED aspetterebbe per sempre e lo sniper,
    che non accetta ne' chiude con una sequenza in corso, restava fermo.
    Ora la sequenza si chiude dichiarata e la chiusura si rifa'."""
    b = _in_chiusura(0.4)
    orologio_mercato["banco"] = b
    b.book()
    pos = b.pos()
    assert pos.submins, "la sequenza deve essere partita"
    b.book()
    for _ in range(differita.ritardo):
        differita()
    park = pos.submins[0]["order"]
    assert park is not None and park.bet_id is not None
    b.market.cancel_order(park)
    for _ in range(differita.ritardo):
        differita()
    assert str(pos.submins[0]["state"].step.value) == "placed"
    viol = giri(b, differita, 120)
    assert viol == [], viol[:3]
    assert not pos.submins
    assert chiusa(pos)
    assert any(r[0] == "submin_abort" and "non piu' vivo" in str(r[1].get("note"))
               for r in b.righe)


def test_ultima_spiaggia_non_accetta_una_posizione_piazzabile(differita, orologio_mercato):
    """Ogni chiusura RIFIUTATA davvero da flumine (controllo di esposizione),
    prezzi presenti, sequenze esaurite: prima, dopo 12 tentativi, lo sniper
    accettava come residuo la posizione intera (BACK 10). Ora resta in
    chiusura e lo dichiara UNA volta, CRITICAL."""
    b = _in_chiusura(10.0)
    orologio_mercato["banco"] = b
    pos = b.pos()
    pos.submin_count = b.strat._SUBMIN_MAX_PER_CYCLE
    b.strat.max_order_exposure = 0.5
    viol = giri(b, differita, 40)
    assert viol == [], viol[:3]
    assert pos.flattening
    assert not [r for r in b.righe if r[0] in ("sniper_flat_forced", "sniper_flat_residual")]
    assert len([r for r in b.righe if r[0] == "flatten_bloccato"]) == 1


def test_fine_finestra_a_prezzi_assenti_mai_residuo(differita, orologio_mercato):
    """B2 dello sniper: a fine finestra (`inplay_to_s`) la posizione si chiude
    (protezione, in manuale come in automatico). Se il book arriva SENZA prezzi
    la protezione resta armata: prima, dopo 12 tentativi, la posizione intera
    diventava un "residuo accettato"; ora si aspetta e si chiude appena i
    prezzi tornano, con UNA riga CRITICAL."""
    for automatiche in (True, False):
        b = BancoSniper(uscite_automatiche=automatiche)
        orologio_mercato["banco"] = b
        b.pt = KO_MS + int(b.strat.inplay_to_s * 1000) + 5_000   # fuori finestra
        b.book(muto_prezzi=True)
        pos = b.pos()
        pos.entries = [b.abbinato("BACK", 1.5, 10.0)]
        viol = giri(b, differita, 30, muto_prezzi=True)
        assert viol == [], (automatiche, viol[:3])
        assert pos.flattening, (automatiche, "la protezione deve restare armata")
        assert not [r for r in b.righe if r[0] in ("sniper_flat_forced",
                                                   "sniper_flat_residual")]
        assert len([r for r in b.righe if r[0] == "flatten_bloccato"]) == 1
        viol = giri(b, differita, 60)
        assert viol == [], (automatiche, viol[:3])
        w, l = esposizione_vera(b)
        assert abs(w - l) <= tolleranza(pos) + 1e-9, (automatiche, w, l)
        assert chiusa(pos)
