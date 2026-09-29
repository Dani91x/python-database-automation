"""CANTIERE S (29/09) - scalper CALCIO: posizione aperta al fischio col bot che
si crede chiuso (banco: B2 x1 e K5 x1 su 35797769, sbilancio 4,44).

Il bot VERO (``ScalperStrategy`` coi parametri che gli passa la sessione:
``VALIDATED_PARAMS`` = uscite esatte, multipli 0,50, minimi .it) riceve book
VERI (mcm Betfair -> ``StreamListener`` di betfairlightweight) da un ``Flumine``
VERO col client paper della sessione (``_order_client_kwargs``: esecuzione e
middleware simulati di flumine). L'esecuzione dei pacchetti e' DIFFERITA di 1 e
di 4 book (fixture del cantiere T): latenza, bet delay e coda del replay. Il
test consegna i book al bot SOLO con la sua ``process_market_book``: non chiama
mai ``_drive_flatten`` ne' ``_drive_submins``.

A OGNI book si verificano gli invarianti del banco:
  * K5/K6: slot IDLE/DONE -> esposizione abbinata della selezione entro la
    tolleranza che il bot dichiara (``certificazione.tolleranza_slot``) e
    nessun ordine della strategia vivo, nessuna sequenza in corso;
  * B2: dopo il fischio esposizione piatta entro la tolleranza e nessun
    ingresso vivo.
"""
from __future__ import annotations

import json
import queue
from typing import Any, Dict, List, Optional, Tuple

import betfairlightweight
import pytest
from betfairlightweight import filters
from betfairlightweight.streaming.listener import StreamListener
from flumine import Flumine, clients
from flumine.events.events import MarketBookEvent

from Betfair.stream.scalper import certificazione as CERT
from Betfair.stream.scalper import scalper_bot as SB
from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tennis_live.tests.test_cantiere_t_pro_residuo_2026_09_28 import (  # noqa: F401
    esecuzione_differita,
)

MID = "1.259819682"
SEL = 47972
ALTRE = (58805, 58806)
KO_MS = 1_759_140_000_000            # fischio (epoch ms)
KO_ISO = "2025-09-29T10:00:00.000Z"  # stesso istante, per il marketDefinition


def _iso_ko() -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(KO_MS / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# il banco
# ---------------------------------------------------------------------------
class Banco:
    """Flumine VERO (client paper della sessione scalper), bot VERO, book veri."""

    def __init__(self, **params_extra: Any) -> None:
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        client = clients.BetfairClient(api, **SS._order_client_kwargs(True))
        self.fw = Flumine(client=client)
        self.client = client
        params = dict(SS.VALIDATED_PARAMS, stake=25.0, dry_run=False,
                      uscite_automatiche=True)
        # ingressi spenti coi soli numeri (le posizioni le mette il test)
        params.update({"min_size": 1e12, "min_flow": 1e12})
        params.update(params_extra)
        cap = 25.0 * (params["price_max"] - 1.0) * 2.0
        self.strat = SB.ScalperStrategy(
            market_filter=filters.streaming_market_filter(market_ids=[MID]),
            scalper_params=params, max_selection_exposure=cap,
            max_order_exposure=cap, max_trade_count=int(1e6),
            max_live_trade_count=int(1e6))
        self.righe: List[Tuple[str, Dict[str, Any]]] = []
        self.strat.event_sink = lambda kind, payload: self.righe.append((kind, dict(payload)))
        self.fw.add_strategy(self.strat)
        self.q: "queue.Queue[Any]" = queue.Queue()
        self.lis = StreamListener(output_queue=self.q, max_latency=None)
        self.lis.register_stream(9, "marketSubscription")
        self.pt = KO_MS - 400_000
        self.uid = 0
        # ladder di ogni selezione: (best back, best lay); size 50 a ogni livello
        self.ladder: Dict[int, Tuple[float, float]] = {
            SEL: (2.20, 2.22), ALTRE[0]: (3.5, 3.55), ALTRE[1]: (3.4, 3.45)}
        self.inplay = False
        self.trd: Dict[int, Dict[float, float]] = {}
        # selezioni senza volume scambiato (un ordine a riposo non si abbina)
        self.senza_scambi: set = set()

    # un book: SUB_IMAGE del mercato, processato da flumine e poi dal bot
    def book(self, passo_ms: int = 1000, muto_prezzi: bool = False) -> Any:
        self.pt += passo_ms
        if self.pt >= KO_MS and not self.inplay:
            self.inplay = True
        self.uid += 1
        rc = []
        for sid, (bb, bl) in self.ladder.items():
            r: Dict[str, Any] = {"id": sid}
            if not muto_prezzi:
                r["batb"] = [[0, bb, 50.0], [1, round(bb - 0.02, 2), 50.0]]
                r["batl"] = [[0, bl, 50.0], [1, round(bl + 0.02, 2), 50.0]]
                # volume scambiato ai due best (cumulativo, come lo stream):
                # e' cio' con cui flumine abbina gli ordini A RIPOSO
                tv = self.trd.setdefault(sid, {})
                for p in (bb, bl):
                    if sid not in self.senza_scambi:
                        tv[p] = tv.get(p, 0.0) + 20.0
            else:
                r["batb"] = []
                r["batl"] = []
            if self.trd.get(sid):
                r["trd"] = [[p, v] for p, v in sorted(self.trd[sid].items())]
            rc.append(r)
        mcm = {
            "op": "mcm", "id": 9, "clk": "C%d" % self.uid, "pt": self.pt,
            "initialClk": "I", "ct": "SUB_IMAGE",
            "mc": [{"id": MID, "img": True, "marketDefinition": {
                "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
                "marketBaseRate": 5.0, "eventId": "35797769", "eventTypeId": "1",
                "numberOfWinners": 1, "bettingType": "ODDS", "marketType": "MATCH_ODDS",
                "marketTime": _iso_ko(), "suspendTime": _iso_ko(),
                "bspReconciled": False, "complete": True, "inPlay": self.inplay,
                "crossMatching": True, "runnersVoidable": False,
                "numberOfActiveRunners": 3, "betDelay": 0, "status": "OPEN",
                "runners": [{"status": "ACTIVE", "sortPriority": i + 1, "id": sid}
                            for i, sid in enumerate(self.ladder)],
                "regulators": ["MR_INT"], "countryCode": "IT", "discountAllowed": True,
                "timezone": "Europe/Rome", "openDate": _iso_ko(), "version": 1},
                "rc": rc}]}
        self.lis.on_data(json.dumps(mcm))
        books = self.q.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))
        market = self.fw.markets.markets[MID]
        if self.strat.check_market_book(market, market.market_book):
            self.strat.process_market_book(market, market.market_book)
        return market

    @property
    def market(self) -> Any:
        return self.fw.markets.markets[MID]

    def abbinato(self, lato: str, prezzo: float, size: float) -> Any:
        """Un ordine della strategia ABBINATO per intero nel blotter vero."""
        from flumine.order.ordertype import LimitOrder
        from flumine.order.trade import Trade
        trade = Trade(MID, SEL, 0, self.strat)
        o = trade.create_order(lato, LimitOrder(prezzo, size))
        o.update_client(self.client)
        o.simulated.matched = [[0, prezzo, size]]
        o.simulated.size_matched = size
        o.simulated.average_price_matched = prezzo
        o.execution_complete()
        self.market.blotter[o.id] = o
        return o

    def slot(self) -> Any:
        return self.strat._slot(MID, SEL)


# ---------------------------------------------------------------------------
# gli invarianti del banco, calcolati dai campi VERI di flumine
# ---------------------------------------------------------------------------
def esposizione_vera(market: Any, strat: Any, sel: int = SEL) -> Tuple[float, float]:
    righe = [CERT.riga_ordine(o) for o in market.blotter.strategy_orders(strat)
             if int(getattr(o, "selection_id", 0) or 0) == sel]
    return CERT.esposizione(righe)


def vivi(market: Any, strat: Any, sel: int = SEL) -> List[Any]:
    return [o for o in market.blotter.strategy_orders(strat)
            if int(getattr(o, "selection_id", 0) or 0) == sel
            and SB.ScalperStrategy._has_live(o)]


def invarianti(b: Banco, i: int) -> List[str]:
    """K5/K6 (slot chiuso) e B2 (dopo il fischio) su questo book."""
    out: List[str] = []
    slot = b.slot()
    m = b.market
    w, l = esposizione_vera(m, b.strat)
    tol = CERT.tolleranza_slot(slot)
    chiuso = slot.status in (SB.IDLE, SB.DONE)
    if chiuso:
        # K5: la tolleranza e' per ciclo (come il controllo del banco)
        tol_k5 = tol + 0.02 * max(0, int(slot.cycles or 0))
        if abs(w - l) > tol_k5 + 1e-6:
            out.append("book %d K5: slot %s con sbilancio %.2f (w %.2f, l %.2f) oltre %.2f"
                       % (i, slot.status, abs(w - l), w, l, tol_k5))
        v = vivi(m, b.strat)
        if v or slot.submins:
            out.append("book %d K6: slot %s con vivi=%s sequenze=%d" % (
                i, slot.status, [(o.side, float(o.order_type.price),
                                  float(o.size_remaining)) for o in v],
                len(slot.submins)))
    if b.inplay:
        if abs(w - l) > tol + 1e-6:
            out.append("book %d B2: in gioco sbilancio %.2f (w %.2f, l %.2f) oltre %.2f, "
                       "slot %s" % (i, abs(w - l), w, l, tol, slot.status))
        ingressi = {id(o) for o in (slot.entry, slot.entry_back, slot.entry_lay,
                                    slot.next_entry) if o is not None}
        for o in vivi(m, b.strat):
            if id(o) in ingressi:
                out.append("book %d B2: ingresso vivo in gioco" % i)
    return out


def giri(b: Banco, svuota: Any, n: int, passo_ms: int = 1000,
         muto_prezzi: bool = False) -> List[str]:
    viol: List[str] = []
    for i in range(n):
        svuota()
        b.book(passo_ms, muto_prezzi=muto_prezzi)
        viol += invarianti(b, i)
    return viol


@pytest.fixture(params=[1, 4])
def differita(request, esecuzione_differita):
    """Esecuzione dei pacchetti di flumine differita di 1 e di 4 book."""
    esecuzione_differita.ritardo = request.param
    return esecuzione_differita


@pytest.fixture
def orologio_mercato(monkeypatch):
    """Come il banco del replay ("orologio di mercato per `time.time`"): il
    tempo del processo e' quello del book corrente."""
    import time as _time
    stato = {"banco": None}

    def _ora() -> float:
        b = stato["banco"]
        return (b.pt / 1000.0) if b is not None else 0.0
    monkeypatch.setattr(_time, "time", _ora)
    return stato


def _in_flatten(lato: str, prezzo: float, size: float, **extra: Any) -> Banco:
    """Una posizione ABBINATA nello slot e la chiusura garantita avviata (come
    dopo uno stop o il force-flat)."""
    b = Banco(**extra)
    b.book()
    slot = b.slot()
    slot.entry = b.abbinato(lato, prezzo, size)
    slot.entry_side = lato
    b.strat._begin_flatten(slot)
    return b


@pytest.mark.parametrize("size_lay", [0.2, 1.0, 25.0])
def test_flatten_non_dichiara_chiuso_con_sequenza_o_ordini_vivi(size_lay, differita,
                                                               orologio_mercato):
    """Il flatten chiude la posizione ESATTAMENTE e lo slot si dichiara chiuso
    solo senza ordini vivi e senza sequenze (K5/K6), qualunque sia la latenza.
    LAY 0,20: chiusura tutta sotto il minimo (place-and-trim), prima il
    "micro-residuo" si accettava a sequenza appena avviata e lo slot andava
    DONE col parcheggio da 2,00 vivo. LAY 25: 25 diretti + resto esatto."""
    b = _in_flatten("LAY", 2.22, size_lay)
    orologio_mercato["banco"] = b
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= 0.02 + 1e-9, (w, l, b.righe[-10:])
    assert vivi(b.market, b.strat) == []
    assert b.slot().status in (SB.IDLE, SB.DONE)


def test_reperto_35797769_nessuna_chiusura_doppia_col_taglio_in_volo(differita,
                                                                   orologio_mercato):
    """IL REPERTO del replay (sonda del cantiere S, codice di master): LAY 1,98
    @2,22 abbinata, force-flat (loss cap). La chiusura e' un BACK 1,98 sotto il
    minimo -> place-and-trim. Al taglio il parcheggio e' `Cancelling`: prima
    `_has_live` lo dava per morto e il flatten piazzava una SECONDA chiusura
    diretta (BACK 2,00 @2,20, abbinata); poi il sostituto della sequenza (BACK
    1,98 @2,22) si abbinava senza essere agganciato. Il bot vedeva +0,02/-0,02,
    andava DONE ("residuo 0,04") con un BACK 2,00 NUDO a mercato: se vince
    +2,44, se perde -2,00, fino al fischio (B2, K5)."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.ladder[SEL] = (2.22, 2.24)
    b.book()
    slot = b.slot()
    slot.entry = b.abbinato("LAY", 2.22, 1.98)
    slot.entry_side = "LAY"
    b.strat.force_flat = True
    b.strat._begin_flatten(slot)
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= 0.02 + 1e-9, (w, l)
    # UNA sola chiusura: nessun ordine BACK diretto accanto alla sequenza
    diretti = [r for r in b.righe if r[0] == "place" and r[1].get("side") == "BACK"
               and float(r[1].get("size") or 0) >= 2.0]
    assert diretti == [], diretti


def test_sostituto_del_rimpiazzo_agganciato_mai_posizione_rovesciata(differita,
                                                                    orologio_mercato):
    """Il SOSTITUTO del rimpiazzo (gradino 3 del place-and-trim) nasce quando
    flumine esegue il replace, cioe' book DOPO che la sequenza e' finita: prima
    nessuno lo agganciava, il bot si credeva ancora scoperto e, passata la pausa
    di 30 s, ripiazzava la chiusura: posizione ROVESCIATA (cantiere T, K5)."""
    b = _in_flatten("LAY", 2.22, 25.0)
    orologio_mercato["banco"] = b
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    # nessun residuo "accettato" che nella realta' non c'e'
    assert not [r for r in b.righe if r[0].startswith("flatten_residual")], \
        [r for r in b.righe if r[0].startswith("flatten_residual")]
    # UNA sola sequenza per chiudere il resto
    assert len([r for r in b.righe if r[0] == "submin_start"]) == 1, \
        [r for r in b.righe if r[0].startswith("submin")]


def test_piatta_con_un_ordine_dello_slot_vivo_non_si_dichiara_chiusa(differita,
                                                                    orologio_mercato):
    """Posizione gia' piatta (LAY 1,00 @2,22 + BACK 1,01 @2,20 abbinati) ma
    nello slot resta un ordine VIVO a quota non abbinabile (BACK 2,00 @1000,
    come il parcheggio di una sequenza finita male): prima lo slot andava DONE
    con quell'ordine a mercato (K6). Ora si ritira e si dichiara chiusa dopo."""
    b = _in_flatten("LAY", 2.22, 1.0)
    orologio_mercato["banco"] = b
    slot = b.slot()
    slot.flatten_orders.append(b.abbinato("BACK", 2.20, 1.01))
    vivo = b.strat._place(b.market, SEL, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert vivo is not None
    slot.flatten_orders.append(vivo)
    viol = giri(b, differita, 12)
    assert viol == [], viol[:3]
    assert slot.status in (SB.IDLE, SB.DONE)
    assert vivi(b.market, b.strat) == []


def test_parcheggio_orfano_si_ritira_e_la_chiusura_parte(differita, orologio_mercato):
    """Un parcheggio ORFANO (BACK 2,00 @1000 di una sequenza non piu' in corso)
    nello slot di una posizione APERTA (LAY 25 @2,22): lo stale del flatten
    salta i parcheggi per progetto, e prima il flatten lo aspettava per sempre
    (`any(_has_live)`): la chiusura non partiva mai. Ora un parcheggio fuori da
    ogni sequenza si ritira e la posizione si chiude."""
    b = _in_flatten("LAY", 2.22, 25.0)
    orologio_mercato["banco"] = b
    slot = b.slot()
    orfano = b.strat._place(b.market, SEL, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert orfano is not None
    slot.flatten_orders.append(orfano)
    viol = giri(b, differita, 150)
    assert viol == [], viol[:3]
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= 0.02 + 1e-9, (w, l, slot.status)
    assert not b.strat._has_live(orfano)
    assert slot.status in (SB.IDLE, SB.DONE)


def test_locking_non_chiude_il_ciclo_con_un_parcheggio_ancora_pending(differita,
                                                                     orologio_mercato):
    """LOCKING: ingresso BACK 2,00 @2,22 e close LAY 2,00 @2,22 abbinate (ciclo
    pari), ma nello slot resta un parcheggio BACK 2,00 @1000 ancora PENDING (il
    cancel su un ordine senza bet_id fallisce). Prima lo slot andava DONE col
    parcheggio vivo (K6): 2,00 EUR a mercato senza padrone."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.book()
    slot = b.slot()
    slot.entry = b.abbinato("BACK", 2.22, 2.0)
    slot.entry_side = "BACK"
    slot.close = b.abbinato("LAY", 2.22, 2.0)
    slot.status = SB.LOCKING
    slot.t_lock = b.pt
    park = b.strat._place(b.market, SEL, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert park is not None
    slot.flatten_orders.append(park)
    viol = giri(b, differita, 15)
    assert viol == [], viol[:3]
    assert slot.status in (SB.IDLE, SB.DONE)
    assert vivi(b.market, b.strat) == []


def test_parcheggio_ritirato_prima_del_taglio_non_blocca_la_sorveglianza(differita,
                                                                        orologio_mercato):
    """Il parcheggio di una sequenza viene ritirato da un'altra via prima del
    taglio (cancel delle vecchie close in LOCKING, force-flat) e lo slot e'
    DONE. Prima la sequenza restava in PLACED per sempre (`advance_submin`
    aspetta il taglio), lo slot DONE saltava la sorveglianza
    (`if slot.submins: continue`) e la posizione restava senza padrone (K5)."""
    b = _in_flatten("LAY", 2.22, 1.0)
    orologio_mercato["banco"] = b
    b.book()
    slot = b.slot()
    assert slot.submins, "la sequenza deve essere partita"
    b.book()                                     # il parcheggio parte (in coda)
    for _ in range(differita.ritardo):
        differita()                              # ... ed e' eseguito da flumine
    park = slot.submins[0]["order"]
    assert park is not None and float(park.order_type.price) == 1000.0
    assert park.bet_id is not None
    b.market.cancel_order(park)                  # ritirato da un'altra via
    for _ in range(differita.ritardo):
        differita()
    assert not b.strat._vivo_o_in_volo(park) if hasattr(b.strat, "_vivo_o_in_volo") \
        else not b.strat._has_live(park)
    assert str(slot.submins[0]["state"].step.value) == "placed"
    slot.status = SB.DONE                        # dichiarato chiuso da un altro ramo
    viol: List[str] = []
    ripresa = False
    for i in range(80):
        differita()
        b.book()
        if slot.status == SB.FLATTENING:
            ripresa = True
        if slot.status in (SB.IDLE, SB.DONE) and ripresa:
            break
        viol += invarianti(b, i)
    assert viol == [], viol[:3]
    assert ripresa, "la posizione deve tornare governata (FLATTENING)"
    assert not slot.submins
    assert slot.status == SB.DONE
    # chiusa: l'esposizione VERA e' quella che il bot contabilizza e dichiara
    # (piatta, o il micro-residuo che dichiara con i suoi numeri)
    w, l = esposizione_vera(b.market, b.strat)
    nw, nl = b.strat._net_position(slot)
    assert abs(w - nw) <= 0.011 and abs(l - nl) <= 0.011, ((w, l), (nw, nl))
    assert abs(w - l) <= CERT.tolleranza_slot(slot) + 1e-9, (w, l)


@pytest.mark.parametrize("automatiche", [True, False])
def test_la_close_a_target_resta_a_mercato_automatica_o_firmata(automatiche, differita,
                                                               orologio_mercato):
    """UF2 (replay 35797769, uscite firmate: "proposta 24,42, ordini nuovi
    0,00"). La close a target di `_open_lock` (automatica, o firmata
    dall'utente a uscite manuali) entrava in `flatten_orders` (tracciamento
    anti-orfani di `_place`) e il ciclo LOCKING delle "vecchie close
    sostituite" la RITIRAVA al book dopo, con l'aggiunta di pre-dimensione e
    il suo parcheggio. Ora resta a riposo alla quota target, all'importo
    ESATTO della proposta, finche' non si abbina (o uno stop la sostituisce)."""
    b = Banco(uscite_automatiche=automatiche)
    orologio_mercato["banco"] = b
    b.pt = KO_MS - 3_000_000
    # il book non tocca la quota target (2,20 LAY) ne' va contro l'ingresso
    # (niente stop, niente scratch): la close RIPOSA
    b.senza_scambi.add(SEL)
    b.book()
    slot = b.slot()
    slot.entry = b.abbinato("BACK", 2.22, 25.0)
    slot.entry_side = "BACK"
    b.strat._open_lock(b.market, slot, b.pt, slot.entry, 2.20, 2.22)
    if not automatiche:
        # a uscite manuali la close non parte: e' una PROPOSTA coi numeri
        assert slot.close is None and slot.status == SB.LOCKING
        viva = [p for p in b.strat.cancello_uscite.vive() if p.get("motivo") == "target"]
        assert len(viva) == 1
        proposta = viva[0]
        # l'utente FIRMA (la via di produzione: `approvate[chiave] = istante`)
        b.strat.cancello_uscite.approvate[proposta["chiave"]] = b.pt / 1000.0
        differita()
        b.book()
        assert slot.close is not None, "la firma deve far partire la close"
    close = slot.close
    assert close is not None
    for i in range(40):
        differita()
        b.book()
        assert slot.status == SB.LOCKING, (i, slot.status)
        assert slot.close is close
        assert str(close.status.value) in ("Pending", "Executable"), (i, close.status)
        assert float(close.size_remaining) == float(close.order_type.size)
    # la chiusura e' ESATTA: 25,00 diretti + 0,23 col place-and-trim, tutti a
    # riposo alla quota target (il parcheggio a 1,01 non e' un importo)
    assert not [r for r in b.righe if r[0] == "submin_abort"], \
        [r for r in b.righe if r[0].startswith("submin")]
    uscita = [o for o in b.market.blotter.strategy_orders(b.strat)
              if o.side == "LAY" and float(o.order_type.price) == 2.20]
    tot = round(sum(float(o.size_remaining) + float(o.size_matched) for o in uscita), 2)
    atteso = SB.compute_green(2.22 * 25.0 - 25.0, -25.0, 2.20)[1]
    assert abs(tot - atteso) <= 0.011, (tot, atteso)


def _ciclo_in_locking(b: Banco, size: float = 25.0) -> Any:
    """Un ciclo VERO in LOCKING: ingresso BACK abbinato @2,22 e la close LAY a
    +1 tick (2,20) piazzata dal bot, a riposo (il book non ci arriva)."""
    slot = b.slot()
    slot.entry = b.abbinato("BACK", 2.22, size)
    slot.entry_side = "BACK"
    slot.status = SB.LOCKING
    slot.t_lock = b.pt
    close = b.strat._place(b.market, SEL, "LAY", 2.16, size, floor_min=False, slot=slot)
    assert close is not None
    slot.close = close
    return slot


@pytest.mark.parametrize("muto", [False, True])
def test_al_fischio_posizione_piatta_anche_col_flusso_prezzi_interrotto(
        muto, differita, orologio_mercato):
    """B2 (bibbia: "mai posizioni aperte al KO", `flatten_before_s`=180): un
    ciclo in LOCKING a KO-200 s. La finestra di flatten lo chiude PRIMA del
    fischio, passando SOLO da `process_market_book`, in automatico come in
    manuale (e' una PROTEZIONE: non passa dal cancello delle uscite).
    `muto`: per 60 s dentro la finestra il book arriva SENZA prezzi (flusso dei
    prezzi interrotto): la protezione resta armata, lo slot resta governato
    (mai DONE con la posizione aperta, mai un residuo "accettato" grande
    quanto la posizione) e chiude appena i prezzi tornano."""
    for automatiche in (True, False):
        b = Banco(uscite_automatiche=automatiche)
        orologio_mercato["banco"] = b
        b.pt = KO_MS - 200_000
        b.book()
        slot = _ciclo_in_locking(b)
        viol: List[str] = []
        for i in range(400):
            differita()
            t_ko = (b.pt + 1000 - KO_MS) / 1000.0
            # i prezzi spariscono PRIMA della finestra (KO-180) e tornano 70 s
            # dopo: la protezione scatta a book senza prezzi
            senza = muto and -190.0 <= t_ko <= -110.0
            b.book(1000, muto_prezzi=senza)
            viol += invarianti(b, i)
            if senza and t_ko >= -179.0:
                # a prezzi fermi la posizione e' governata, mai dichiarata chiusa
                w, l = esposizione_vera(b.market, b.strat)
                if abs(w - l) > 0.30:
                    assert slot.status == SB.FLATTENING, (i, slot.status, w, l)
        assert viol == [], (automatiche, viol[:3])
        assert b.inplay
        w, l = esposizione_vera(b.market, b.strat)
        assert abs(w - l) <= CERT.tolleranza_slot(slot) + 1e-9, (w, l)
        assert not slot.residual_ok or slot.residual_accepted <= 0.28, \
            (slot.residual_accepted, [r for r in b.righe if "residual" in r[0]])


# ---------------------------------------------------------------------------
# v2 (29/09, revisione del coordinatore): tre rami che nessun test provava
# ---------------------------------------------------------------------------
def _esegui_in_coda(differita: Any) -> None:
    """Esegue i pacchetti in coda SENZA consegnare book al bot."""
    for _ in range(differita.ritardo):
        differita()


def test_done_non_riparte_con_un_rimpiazzo_in_volo(differita, orologio_mercato):
    """Ciclo chiuso e pari (DONE), ma nello slot c'e' un ordine in REPLACING
    (il rimpiazzo e' chiesto, flumine non l'ha ancora eseguito): il SOSTITUTO
    nascera' book dopo. Prima (`_has_live`) l'ordine contava come morto, lo
    slot ripartiva (`_reset` svuota `flatten_orders`) e il sostituto, BACK
    2,00 abbinato, restava a mercato senza padrone (K5). Ora lo slot aspetta,
    aggancia il sostituto e lo chiude."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.book()
    slot = b.slot()
    park = b.strat._place(b.market, SEL, "BACK", 1000.0, 2.0, floor_min=False, slot=None)
    assert park is not None
    _esegui_in_coda(differita)
    assert str(park.status.value) == "Executable"
    b.market.replace_order(park, 2.20)       # rimpiazzo IN VOLO
    assert str(park.status.value) == "Replacing"
    slot.entry = b.abbinato("BACK", 2.22, 2.0)
    slot.entry_side = "BACK"
    slot.close = b.abbinato("LAY", 2.22, 2.0)
    slot.flatten_orders.append(park)
    slot.status = SB.DONE
    slot.cycles = 1
    viol = giri(b, differita, 40)
    assert viol == [], viol[:3]
    sost = [o for o in park.trade.orders if o is not park]
    assert sost and float(sost[0].size_matched) > 0, "il sostituto deve essere nato e abbinato"
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= CERT.tolleranza_slot(slot) + 1e-9, (w, l, slot.status)


def test_cancelling_aspetta_il_cancel_eseguito_prima_di_ripartire(differita,
                                                                 orologio_mercato):
    """Ingresso a due gambe ritirato (slot CANCELLING, gambe `Cancelling`): in
    Betfair, come nel simulatore di flumine (`LIVE_STATUS` del middleware),
    una gamba in Cancelling puo' ancora ABBINARSI finche' il cancel non e'
    eseguito. Prima il reset partiva al primo book senza abbinato e la gamba
    abbinata DOPO restava fuori da ogni slot (K5). Ora si riparte solo a
    cancel eseguito; un abbinato arrivato nel frattempo si chiude."""
    b = Banco()
    orologio_mercato["banco"] = b
    b.senza_scambi.add(SEL)                  # niente scambi: niente abbinamenti
    b.book()
    slot = b.slot()
    eb = b.strat._place(b.market, SEL, "BACK", 2.22, 25.0)
    el = b.strat._place(b.market, SEL, "LAY", 2.16, 25.0)
    assert eb is not None and el is not None
    _esegui_in_coda(differita)
    assert str(eb.status.value) == "Executable"
    b.market.cancel_order(eb)
    b.market.cancel_order(el)
    assert str(eb.status.value) == "Cancelling"
    slot.entry_back, slot.entry_lay = eb, el
    slot.status = SB.CANCELLING
    viol: List[str] = []
    b.book()                                  # il bot decide a gambe in volo
    viol += invarianti(b, 0)
    b.senza_scambi.discard(SEL)               # adesso si scambia a 2,22
    for i in range(1, 9):                     # il cancel e' ancora in coda:
        b.book()                              # la gamba in Cancelling si abbina
        viol += invarianti(b, i)
    assert float(eb.size_matched) > 0, "la gamba in Cancelling deve abbinarsi"
    viol += giri(b, differita, 80)
    assert viol == [], viol[:3]
    w, l = esposizione_vera(b.market, b.strat)
    assert abs(w - l) <= CERT.tolleranza_slot(slot) + 0.02 * slot.cycles + 1e-9, (w, l)


def test_ultima_spiaggia_non_accetta_una_posizione_piazzabile(differita, orologio_mercato):
    """Ogni chiusura RIFIUTATA (qui dal controllo di esposizione di flumine,
    un rifiuto vero: `place_order` torna False), prezzi presenti, sequenze del
    ciclo esaurite (5, tetto invariato): dopo 12 tentativi la ULTIMA SPIAGGIA
    accettava come "residuo" una LAY 25 intera, piazzabile. Ora accetta solo
    un resto sotto il minimo diretto: la posizione resta in chiusura
    (FLATTENING) e lo si dichiara UNA volta, CRITICAL."""
    b = _in_flatten("LAY", 2.22, 25.0)
    orologio_mercato["banco"] = b
    slot = b.slot()
    slot.submin_count = b.strat._SUBMIN_MAX_PER_CYCLE
    b.strat.max_order_exposure = 1.0          # ogni chiusura oltre 1 EUR e' rifiutata
    viol = giri(b, differita, 40)
    assert viol == [], viol[:3]
    assert slot.status == SB.FLATTENING, slot.status
    assert slot.residual_ok is False
    assert not [r for r in b.righe if r[0].startswith("flatten_residual")]
    assert len([r for r in b.righe if r[0] == "flatten_bloccato"]) == 1
    assert [r for r in b.righe if r[0] == "place_rifiutato"], "i rifiuti devono essere veri"
