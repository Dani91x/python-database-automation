"""Aiuti comuni ai test W1-C2 (libro, P&L, attribuzione, riconciliazione).

I finti parlano come il vero (PSB par. 7 n.1, n.27):
  * un ordine del conto e' il JSON di Betfair di ``listCurrentOrders`` (camelCase,
    chiavi facoltative ASSENTI quando Betfair non le manda) trasformato in
    ``CurrentOrder`` dalla libreria VERA (``betfairlightweight.resources.
    CurrentOrders``); oppure un messaggio ``ocm`` dello stream ordini passato
    dalla cache VERA (``betfairlightweight.streaming.cache.OrderBookCache``);
  * gli ordini di flumine sono ``BetfairOrder`` VERI (``Trade.create_order``)
    con il ``CurrentOrder`` vero come risposta, in un ``Blotter`` vero;
  * il DB e' il client VERO supabase/postgrest/httpx con un
    ``httpx.MockTransport`` al posto della rete (modello:
    ``test_catchup_rete_2026_10_08.py``).

Questo file contiene anche due test degli aiuti stessi (che costruiscano
oggetti delle classi vere). ASCII-only.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import flumine  # noqa: F401 - come in produzione
import httpx
from betfairlightweight.resources import CurrentOrders
from betfairlightweight.resources.bettingresources import CurrentOrder
from betfairlightweight.streaming.cache import OrderBookCache

from Betfair.nucleo.betfair.contratto import OrdineDalConto
from Betfair.nucleo.ordini import libro_conto

MKT = "1.200"
HOME, AWAY, DRAW = 47999, 48000, 58805


def ordine_json(bet_id: str, side: str, abbinato: float, prezzo: float, *,
                csr: Optional[str] = None, cor: Optional[str] = None,
                residuo: float = 0.0, sel: int = HOME, market: str = MKT,
                handicap: float = 0.0, annullato: float = 0.0, scaduto: float = 0.0,
                avp: Optional[float] = None, status: Optional[str] = None,
                size: Optional[float] = None) -> Dict[str, Any]:
    """UN ordine come lo manda Betfair in ``listCurrentOrders``."""
    tot = size if size is not None else round(abbinato + residuo + annullato + scaduto, 2)
    d: Dict[str, Any] = {
        "betId": bet_id, "marketId": market, "selectionId": sel, "handicap": handicap,
        "priceSize": {"price": prezzo, "size": tot},
        "bspLiability": 0.0, "side": side,
        "status": status or ("EXECUTABLE" if residuo > 0 else "EXECUTION_COMPLETE"),
        "persistenceType": "LAPSE", "orderType": "LIMIT",
        "placedDate": "2026-10-08T12:00:00.000Z",
        "averagePriceMatched": (avp if avp is not None else (prezzo if abbinato > 0 else 0.0)),
        "sizeMatched": abbinato, "sizeRemaining": residuo, "sizeLapsed": scaduto,
        "sizeCancelled": annullato, "sizeVoided": 0.0,
        "regulatorCode": "MALTA LOTTERIES AND GAMBLING AUTHORITY",
    }
    if abbinato > 0:
        d["matchedDate"] = "2026-10-08T12:00:01.000Z"
    if csr is not None:
        d["customerStrategyRef"] = csr
    if cor is not None:
        d["customerOrderRef"] = cor
    return d


def correnti(*ordini: Dict[str, Any]) -> List[CurrentOrder]:
    """``CurrentOrder`` VERI da una risposta di ``listCurrentOrders``."""
    return CurrentOrders(currentOrders=list(ordini), moreAvailable=False).orders


def dal_conto(d: Dict[str, Any], ricevuto_ms: int = 1000) -> OrdineDalConto:
    return libro_conto.ordine_da_corrente(correnti(d)[0], ricevuto_ms=ricevuto_ms)


def uo(bet_id: str, side: str, abbinato: float, prezzo: float, *, residuo: float = 0.0,
       annullato: float = 0.0, scaduto: float = 0.0, rfo: Optional[str] = None,
       rfs: Optional[str] = None, avp: Optional[float] = None) -> Dict[str, Any]:
    """Un ordine ``uo`` dello stream ordini (chiavi di Betfair, Exchange Stream API)."""
    d: Dict[str, Any] = {
        "id": bet_id, "p": prezzo, "s": round(abbinato + residuo + annullato + scaduto, 2),
        "side": "B" if side == "BACK" else "L",
        "status": "E" if residuo > 0 else "EC", "pt": "L", "ot": "L",
        "pd": 1791460800000, "sm": abbinato, "sr": residuo, "sl": scaduto,
        "sc": annullato, "sv": 0.0, "rc": "REG_GGC", "rac": "1",
    }
    if abbinato > 0:
        d["avp"] = avp if avp is not None else prezzo
        d["md"] = 1791460801000
    if rfo is not None:
        d["rfo"] = rfo
    if rfs is not None:
        d["rfs"] = rfs
    return d


def dallo_stream(market: str, per_sel: Mapping[int, List[Dict[str, Any]]],
                 pt: int = 1791460802000) -> List[CurrentOrder]:
    """Messaggio ``ocm`` -> ``OrderBookCache`` VERA -> ``CurrentOrder``."""
    cache = OrderBookCache(market, pt, lightweight=False)
    orc = [{"id": sid, "fullImage": True, "uo": [dict(u, rfo=u.get("rfo"), rfs=u.get("rfs"))
                                                 for u in lista]}
           for sid, lista in per_sel.items()]
    cache.update_cache({"id": market, "orc": orc}, pt)
    return list(cache.create_resource(1, snap=True).orders)


class FlussoFinto:
    """Un ``FlussoOrdiniConto`` (protocollo del comparto A) con ordini VERI:
    ``ordini()`` e i consumatori come li chiederebbe il libro. Nessun thread."""

    def __init__(self, iniziali: Tuple[OrdineDalConto, ...] = ()) -> None:
        self._ordini: Dict[str, OrdineDalConto] = {o.bet_id: o for o in iniziali}
        self._cb: List[Callable[[OrdineDalConto], None]] = []
        self.vivo = False

    def avvia(self) -> None:
        self.vivo = True

    def ferma(self) -> None:
        self.vivo = False

    def aggiungi_consumatore(self, cb: Callable[[OrdineDalConto], None]) -> None:
        self._cb.append(cb)

    def ordini(self, market_id: Optional[str] = None) -> Tuple[OrdineDalConto, ...]:
        return tuple(o for o in self._ordini.values()
                     if market_id is None or o.market_id == market_id)

    def stato(self) -> Mapping[str, object]:
        return {"vivo": self.vivo}

    def manda(self, o: OrdineDalConto) -> None:
        self._ordini[o.bet_id] = o
        for cb in list(self._cb):
            cb(o)


class Registro:
    """Le richieste HTTP che il client supabase VERO manda (MockTransport)."""

    def __init__(self, risposte: Optional[Callable[[httpx.Request], Any]] = None) -> None:
        self.richieste: List[Tuple[str, str, Any]] = []
        self._risposte = risposte
        self._lock = threading.Lock()

    def gestisci(self, req: httpx.Request) -> httpx.Response:
        corpo = json.loads(req.content) if req.content else None
        with self._lock:
            self.richieste.append((req.method, str(req.url), corpo))
        if self._risposte is not None:
            dati = self._risposte(req)
            if isinstance(dati, httpx.Response):
                return dati
            return httpx.Response(200, json=dati, request=req)
        return httpx.Response(200, json=[], request=req)


def client_supabase(registro: Registro) -> Any:
    from supabase import create_client

    c = create_client("http://127.0.0.1:9", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
    c.postgrest.session._transport = httpx.MockTransport(registro.gestisci)
    return c


# --------------------------------------------------------------------- test degli aiuti
def test_aiuti_costruiscono_oggetti_veri():
    co = correnti(ordine_json("1", "BACK", 2.0, 3.0, csr="mike", cor="mike-t1"))[0]
    assert type(co) is CurrentOrder
    assert (co.customer_strategy_ref, co.customer_order_ref, co.size_matched) == ("mike", "mike-t1", 2.0)
    st = dallo_stream(MKT, {HOME: [uo("9", "LAY", 1.0, 2.5, residuo=1.0, rfs="omega", rfo="omega-t3")]})
    assert type(st[0]) is CurrentOrder
    assert (st[0].side, st[0].status, st[0].customer_strategy_ref) == ("LAY", "EXECUTABLE", "omega")
    o = libro_conto.ordine_da_corrente(st[0], ricevuto_ms=7)
    assert (o.lato, o.stato, o.abbinato, o.residuo, o.prezzo_medio) == ("lay", "EXECUTABLE", 1.0, 1.0, 2.5)


def test_aiuti_client_supabase_vero():
    reg = Registro(lambda req: [{"bet_id": "1"}])
    c = client_supabase(reg)
    res = c.table("omega_trades").select("bet_id").eq("mode", "live").execute()
    assert res.data == [{"bet_id": "1"}]
    assert reg.richieste[0][0] == "GET" and "omega_trades" in reg.richieste[0][1]
