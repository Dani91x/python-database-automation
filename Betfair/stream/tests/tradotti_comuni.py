"""02/10/2026 - RICONCILIAZIONE DEI TRADOTTI: i finti comuni ai test di runner, Omega e Safe.

Nessun numero scritto a mano dove esiste la funzione vera:
- la riga dello specchio nasce da ``LiveTradingStrategy._order_row`` (encoder di produzione);
- l'evento del canale di un ordine tradotto nasce da ``motore_ordini._riporta_tradotto``
  (la stessa funzione che il motore chiama in ``_emetti``), con la dichiarazione
  ``tradotto`` costruita come ``MotoreOrdini._applica_minimi`` dal verdetto VERO
  (``live_order_build.verdetto_minimi``); un test di contratto la confronta con
  quella del motore vero;
- le letture REST passano dalle funzioni VERE di ``omega_market``
  (``order_state_by_bet_id``, ``list_current_orders``, ``list_cleared_orders``) con un
  Betfair finto A LIVELLO DI RETE (``OM.call``) che risponde coi dizionari grezzi di
  ``CurrentOrder``/``ClearedOrder``.
ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

OVER, UNDER = 47972, 47973
MID = "1.234"
NOW = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)


class _Enum:
    def __init__(self, name: str) -> None:
        self.name = name


def tradotto_di(side: str, price: float, size: float, *, sel: int = OVER,
                altra: int = UNDER) -> Dict[str, Any]:
    """La dichiarazione ``piano["tradotto"]`` di ``MotoreOrdini._applica_minimi`` per
    l'ordine chiesto (stesse chiavi, stesso verdetto vero)."""
    from Betfair.stream import live_order_build as LB

    # 04/10/2026 (regola delle punte .it): il verdetto VERO non sceglie piu' un
    # equivalente PUNTA non multiplo di 0,50 (es. 0,43 @18 -> 7,31). Questi test
    # collaudano la RICONCILIAZIONE di un ordine gia' tradotto (la dichiarazione): la si
    # costruisce con la stessa funzione del verdetto (``equivalente_lato_opposto``).
    v = LB.verdetto_minimi("it", side, price, size, altra_selezione=(altra, 0.0))
    if v.esito == LB.VERDETTO_EQUIVALENTE:
        eq = v.equivalente
    else:
        eq = LB.equivalente_lato_opposto(side, price, round(float(size), 2))
        assert eq is not None, v
    mandato = {"selection_id": int(altra), "handicap": 0.0, "side": eq.side,
               "price": float(eq.price), "size": float(eq.size)}
    return {
        "originale": {"selection_id": int(sel), "handicap": 0.0, "side": side.lower(),
                      "price": float(price), "size": round(float(size), 2)},
        "mandato": dict(mandato),
        "quota_esatta": eq.price_esatta,
        "scarto_se_vince_chiesta": eq.scarto_se_vince_chiesta,
        "scarto_se_vince_altra": eq.scarto_se_vince_altra,
        "motivo": v.motivo,
    }


def riga_vera(*, selection_id: int, side: str, price: float, size: float, matched: float,
              remaining: float, status: str, bet_id: Optional[str], avg: float = 0.0,
              mode: str = "live", ref: str = "awlq7") -> Dict[str, Any]:
    """La riga di ``betfair_live_orders`` di un ordine flumine (encoder di produzione)."""
    from Betfair.stream.engine.live_trading_strategy import LiveTradingStrategy

    ot = SimpleNamespace(ORDER_TYPE=_Enum("LIMIT"), price=price, size=size,
                         persistence_type="LAPSE")
    ordine = SimpleNamespace(
        order_type=ot, side=side.upper(), context={"customer_order_ref": ref}, notes=None,
        responses=SimpleNamespace(date_time_placed=NOW),
        size_matched=matched, date_time_status_update=NOW + timedelta(milliseconds=5),
        bet_id=bet_id, market_id=MID, selection_id=selection_id, handicap=0.0,
        size_remaining=remaining, size_cancelled=round(size - matched - remaining, 2),
        size_lapsed=0.0, size_voided=0.0, average_price_matched=avg,
        status=_Enum(status))
    riga = dict(LiveTradingStrategy._order_row(SimpleNamespace(mode=mode), ordine,
                                               event_id="35760084", market_id=MID))
    riga["updated_at"] = (NOW + timedelta(milliseconds=6)).isoformat()
    return riga


def evento_tradotto(t: Dict[str, Any], *, ref: str, seq: int, fase: str, matched: float,
                    remaining: float, status: str, bet_id: str, mode: str = "live",
                    avg: Optional[float] = None) -> Dict[str, Any]:
    """L'evento ``order`` che il motore manda al bot per un ordine TRADOTTO: la riga vera
    dell'equivalente riportata nei termini chiesti da ``motore_ordini._riporta_tradotto``."""
    from Betfair.stream import motore_ordini as MO

    m = t["mandato"]
    vera = riga_vera(selection_id=m["selection_id"], side=m["side"], price=m["price"],
                     size=m["size"], matched=matched, remaining=remaining, status=status,
                     bet_id=bet_id, avg=(m["price"] if avg is None and matched else (avg or 0.0)),
                     mode=mode)
    d = MO._riporta_tradotto(vera, t)
    d.update({"ref": ref, "seq": seq, "fase": fase, "esito_ms": 1.0})
    return d


def corrente_grezzo(*, bet_id: str, selection_id: int, side: str, price: float, size: float,
                    matched: float, remaining: float, status: str = "EXECUTION_COMPLETE",
                    ref: str = "4f1a2b-1", avg: Optional[float] = None) -> Dict[str, Any]:
    """Un ``CurrentOrder`` grezzo di Betfair (listCurrentOrders)."""
    return {
        "betId": bet_id, "marketId": MID, "selectionId": selection_id,
        "side": side.upper(), "status": status, "sizeMatched": matched,
        "averagePriceMatched": (price if avg is None and matched else avg),
        "sizeRemaining": remaining, "sizeCancelled": round(size - matched - remaining, 2),
        "sizeLapsed": 0.0, "sizeVoided": 0.0, "customerOrderRef": ref,
        "matchedDate": "2026-10-02T20:00:03.000Z", "placedDate": "2026-10-02T20:00:00.000Z",
        "priceSize": {"price": price, "size": size},
    }


def regolato_grezzo(*, bet_id: str, selection_id: int, side: str, price: float,
                    settled: float, profit: float, ref: str = "4f1a2b-1") -> Dict[str, Any]:
    """Un ``ClearedOrder`` grezzo di Betfair (listClearedOrders, SETTLED)."""
    return {
        "betId": bet_id, "marketId": MID, "selectionId": selection_id,
        "side": side.upper(), "sizeSettled": settled, "priceMatched": price,
        "priceRequested": price, "profit": profit, "betOutcome": "WON",
        "customerOrderRef": ref, "lastMatchedDate": "2026-10-02T20:00:03.000Z",
        "placedDate": "2026-10-02T20:00:00.000Z", "settledDate": "2026-10-02T22:00:00.000Z",
    }


class ReteBetfair:
    """Betfair finto a livello di RETE per ``omega_market`` (``OM.call``): tutte le
    funzioni di lettura restano quelle vere. ``correnti``/``regolati`` = dizionari grezzi."""

    def __init__(self) -> None:
        self.correnti: List[Dict[str, Any]] = []
        self.regolati: List[Dict[str, Any]] = []
        self.book: List[Dict[str, Any]] = []
        self.chiamate: List[str] = []
        self.piazzati: List[Any] = []

    def _filtra_bet(self, righe: List[Dict[str, Any]], params: Any) -> List[Dict[str, Any]]:
        ids = (params or {}).get("betIds") if isinstance(params, dict) else None
        return [r for r in righe if not ids or str(r.get("betId")) in {str(i) for i in ids}]

    def legge(self, fn: Any) -> Any:
        rete = self

        class Cli:
            def betting_rpc(_s, method: Any = None, params: Any = None, *a: Any,
                            **k: Any) -> Any:
                m = str(method or "")
                rete.chiamate.append(m)
                if "listCurrentOrders" in m:
                    return {"currentOrders": rete._filtra_bet(rete.correnti, params)}
                if "listClearedOrders" in m:
                    if (params or {}).get("betStatus") not in (None, "SETTLED"):
                        return {"clearedOrders": []}
                    return {"clearedOrders": rete._filtra_bet(rete.regolati, params)}
                if "listMarketBook" in m:
                    return list(rete.book)
                return {}

            def list_current_orders(_s, **k: Any) -> Any:
                rete.chiamate.append("list_current_orders")
                return {"currentOrders": list(rete.correnti)}

            def list_cleared_orders(_s, **k: Any) -> Any:
                rete.chiamate.append("list_cleared_orders")
                if k.get("bet_status") not in (None, "SETTLED"):
                    return {"clearedOrders": []}
                return {"clearedOrders": list(rete.regolati)}

            def list_market_book(_s, *a: Any, **k: Any) -> Any:
                rete.chiamate.append("list_market_book")
                return list(rete.book)

        return fn(Cli())


    def muta(self, fn: Any) -> Any:
        """``OM.call_mutating``: ``place_orders`` registra l'istruzione e risponde con un
        ``PlaceExecutionReport`` grezzo ABBINATO per intero (FOK coperto)."""
        rete = self

        class Cli:
            def place_orders(_s, market_id: Any, instructions: Any, **k: Any) -> Any:
                ins = instructions[0]
                rete.piazzati.append((market_id, dict(ins), dict(k)))
                lo = ins["limitOrder"]
                return {"status": "SUCCESS", "marketId": market_id, "instructionReports": [{
                    "status": "SUCCESS", "orderStatus": "EXECUTION_COMPLETE",
                    "betId": "PIAZZATO%d" % len(rete.piazzati),
                    "sizeMatched": lo["size"], "averagePriceMatched": lo["price"],
                    "placedDate": "2026-10-02T20:00:00.000Z"}]}

        return fn(Cli())


def book_grezzo(*selezioni: int, vincitori: int = 1, stato_runner: str = "ACTIVE"
                ) -> List[Dict[str, Any]]:
    """``listMarketBook`` grezzo (lightweight): runner con stato e ``numberOfWinners``."""
    return [{"marketId": MID, "status": "OPEN", "inplay": True,
             "numberOfWinners": vincitori,
             "runners": [{"selectionId": s, "handicap": 0.0,
                          "status": stato_runner if i == 0 else "ACTIVE",
                          "ex": {"availableToBack": [{"price": 1.06, "size": 500.0}],
                                 "availableToLay": [{"price": 18.0, "size": 500.0}]}}
                         for i, s in enumerate(selezioni)]}]


def monta_rete(monkeypatch: Any) -> ReteBetfair:
    from Betfair.omega import omega_market as OM

    rete = ReteBetfair()
    monkeypatch.setattr(OM, "call", rete.legge)
    monkeypatch.setattr(OM, "call_mutating", rete.muta)
    return rete
