"""Banco di prova della modalita' "media under" (05/10/2026) per i test.

Flumine VERO col client paper della sessione (``scalper_session._order_client_kwargs``:
esecuzione e middleware simulati di flumine), strategia VERA
(``media_under_bot.MediaUnderStrategy``) coi parametri di serie della UI, book
VERI: messaggi ``mcm`` nel formato nativo di Betfair passati allo
``StreamListener`` di betfairlightweight, poi a flumine, poi alla strategia con
le SUE ``check_market_book``/``process_market_book``. Nessun ordine o fill
scritto a mano: gli ordini li piazza la strategia, li abbina il simulatore di
flumine (taker sul disponibile, a riposo sul volume scambiato con la coda
davanti). Il lapse al fischio e' quello del banco comune
(``banco_comune.MotoreReplay._uccidi_appoggiati``: Betfair cancella i LAPSE non
abbinati quando il mercato va in gioco; i PERSIST restano).

Stesso schema del banco del cantiere S (``test_cantiere_s_scalper_ko_2026_09_29``).
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import queue
from typing import Any, Dict, List, Optional, Tuple

import betfairlightweight
from betfairlightweight import filters
from betfairlightweight.streaming.listener import StreamListener
from flumine import Flumine, clients
from flumine.events.events import MarketBookEvent
from flumine.utils import price_ticks_away

from Betfair.stream.backtest import banco_comune as BC
from Betfair.stream.scalper import media_under_bot as MU
from Betfair.stream.scalper import scalper_session as SS

#: ids veri di Betfair per le selezioni Over/Under (Under 2,5 = 47972)
MERCATI = {
    "OVER_UNDER_25": ("1.300000025", 47972, 47973),
    "OVER_UNDER_35": ("1.300000035", 1222344, 1222345),
}
KO_MS = 1_759_140_000_000
EVENTO = "35999999"


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")


def params_di_serie(mercato: str = "OVER_UNDER_25", **extra: Any) -> Dict[str, Any]:
    """I params che la scheda scrive (valori di serie) con la modalita' accesa."""
    p = dict(MU.VALORI_DI_SERIE)
    p.update({"media_mode": True, "media_mercato": mercato})
    p.update(extra)
    return p


class BancoMedia:
    """Flumine VERO, strategia VERA, book veri su UN mercato Over/Under."""

    def __init__(self, mercato: str = "OVER_UNDER_25", *, profondita: float = 500.0,
                 warmup_ms: int = 60000, **params: Any) -> None:
        self.mercato = mercato
        self.mid, self.under, self.over = MERCATI[mercato]
        api = betfairlightweight.APIClient("u", "p", app_key="k")
        self.client = clients.BetfairClient(api, **SS._order_client_kwargs(True))
        self.fw = Flumine(client=self.client)
        cfg = params_di_serie(mercato, **params)
        cfg.update({"flow_window_ms": SS.VALIDATED_PARAMS["flow_window_ms"],
                    "warmup_ms": warmup_ms,
                    "runner_names": {(self.mid, self.under): "Under %s Goals" % mercato[-2:-1],
                                     (self.mid, self.over): "Over %s Goals" % mercato[-2:-1]}})
        self.strat = MU.MediaUnderStrategy(
            market_filter=filters.streaming_market_filter(market_ids=[self.mid]),
            media_params=cfg, max_selection_exposure=None, max_order_exposure=None,
            max_trade_count=int(1e6), max_live_trade_count=int(1e6))
        self.righe: List[Tuple[str, Dict[str, Any]]] = []
        self.strat.event_sink = lambda k, p: self.righe.append((k, dict(p)))
        self.fw.add_strategy(self.strat)
        self.q: "queue.Queue[Any]" = queue.Queue()
        self.lis = StreamListener(output_queue=self.q, max_latency=None)
        self.lis.register_stream(9, "marketSubscription")
        self.pt = KO_MS - 3_600_000
        self.uid = 0
        self.profondita = float(profondita)
        # (best back, best lay) per selezione
        self.ladder: Dict[int, Tuple[float, float]] = {
            self.under: (1.50, 1.51), self.over: (2.98, 3.05)}
        self.taglie: Dict[Tuple[int, float], float] = {}
        self.trd: Dict[int, Dict[float, float]] = {}
        self.inplay = False
        self.stato = "OPEN"
        self.versione = 1
        # l'istante di MERCATO in cui nasce ogni ordine (``Flumine`` non simulato
        # timbra gli ordini con l'ora del PC; il replay del banco con il
        # ``publish_time``, come qui)
        self.nati: Dict[str, int] = {}

    # ----------------------------------------------------------------- book
    def _livelli(self, sid: int) -> Tuple[List[List[Any]], List[List[Any]]]:
        bb, bl = self.ladder[sid]
        batb, batl = [], []
        p = bb
        for i in range(5):
            batb.append([i, p, self.taglie.get((sid, p), self.profondita)])
            p = price_ticks_away(p, -1)
        p = bl
        for i in range(5):
            batl.append([i, p, self.taglie.get((sid, p), self.profondita)])
            p = price_ticks_away(p, 1)
        return batb, batl

    def scambia(self, sid: int, prezzo: float, volume: float) -> None:
        """Volume scambiato a un prezzo (cumulativo, come lo stream)."""
        tv = self.trd.setdefault(sid, {})
        tv[prezzo] = tv.get(prezzo, 0.0) + float(volume)

    def book(self, passo_ms: int = 1000, flusso: float = 20.0) -> Any:
        self.pt += passo_ms
        self.uid += 1
        rc = []
        for sid in (self.under, self.over):
            batb, batl = self._livelli(sid)
            bb, bl = self.ladder[sid]
            if flusso:
                self.scambia(sid, bb, flusso)
                self.scambia(sid, bl, flusso)
            r: Dict[str, Any] = {"id": sid, "batb": batb, "batl": batl}
            if self.trd.get(sid):
                r["trd"] = [[p, v] for p, v in sorted(self.trd[sid].items())]
            rc.append(r)
        md = {
            "bspMarket": False, "turnInPlayEnabled": True, "persistenceEnabled": True,
            "marketBaseRate": 5.0, "eventId": EVENTO, "eventTypeId": "1",
            "numberOfWinners": 1, "bettingType": "ODDS", "marketType": self.mercato,
            "marketTime": _iso(KO_MS), "suspendTime": _iso(KO_MS),
            "bspReconciled": False, "complete": True, "inPlay": self.inplay,
            "crossMatching": True, "runnersVoidable": False,
            "numberOfActiveRunners": 2, "betDelay": 0, "status": self.stato,
            "runners": [{"status": "ACTIVE", "sortPriority": 1, "id": self.under},
                        {"status": "ACTIVE", "sortPriority": 2, "id": self.over}],
            "regulators": ["MR_INT"], "countryCode": "IT", "discountAllowed": True,
            "timezone": "Europe/Rome", "openDate": _iso(KO_MS), "version": self.versione}
        mcm = {"op": "mcm", "id": 9, "clk": "C%d" % self.uid, "pt": self.pt,
               "initialClk": "I", "ct": "SUB_IMAGE",
               "mc": [{"id": self.mid, "img": True, "marketDefinition": md, "rc": rc}]}
        self.lis.on_data(json.dumps(mcm))
        books = self.q.get_nowait()
        self.fw._process_market_books(MarketBookEvent(books))
        market = self.fw.markets.markets[self.mid]
        if self.strat.check_market_book(market, market.market_book):
            self.strat.process_market_book(market, market.market_book)
        for o in market.blotter.strategy_orders(self.strat):
            self.nati.setdefault(str(o.id), self.pt)
        return market

    def in_gioco(self) -> None:
        """Il mercato passa in gioco: Betfair cancella i LAPSE non abbinati
        (regola del banco comune), i PERSIST restano."""
        self.inplay = True
        self.versione += 1
        BC.MotoreReplay._uccidi_appoggiati(self.market)

    @property
    def market(self) -> Any:
        return self.fw.markets.markets[self.mid]

    # ------------------------------------------------------------- letture
    def ordini(self) -> List[Any]:
        return list(self.market.blotter.strategy_orders(self.strat))

    def vivi(self, lato: Optional[str] = None) -> List[Any]:
        return [o for o in self.ordini() if MU.vivo_o_in_volo(o)
                and (lato is None or MU._lato(o) == lato)]

    def kinds(self, kind: str) -> List[Dict[str, Any]]:
        return [p for k, p in self.righe if k == kind]

    def posizione(self) -> MU.Posizione:
        return MU.posizione_da_ordini(self.ordini())

    def invarianti(self, i: int) -> List[str]:
        """Le invarianti della spec a OGNI book: mai due banche vive, mai due
        punte vive, nessun ordine nuovo in gioco, punte LAPSE e banche PERSIST."""
        out = []
        if len(self.vivi("LAY")) > 1:
            out.append("book %d: %d banche vive insieme" % (i, len(self.vivi("LAY"))))
        if len(self.vivi("BACK")) > 1:
            out.append("book %d: %d punte vive insieme" % (i, len(self.vivi("BACK"))))
        for o in self.ordini():
            pt = str(o.order_type.persistence_type)
            if MU._lato(o) == "LAY" and pt != "PERSIST":
                out.append("book %d: banca %s non PERSIST" % (i, pt))
            if MU._lato(o) == "BACK" and pt != "LAPSE":
                out.append("book %d: punta %s non LAPSE" % (i, pt))
        return out


def giri(b: BancoMedia, svuota: Any, n: int, **kw: Any) -> List[str]:
    """n book con l'esecuzione differita; torna le invarianti violate."""
    viol: List[str] = []
    for i in range(n):
        svuota()
        b.book(**kw)
        viol += b.invarianti(i)
    return viol
