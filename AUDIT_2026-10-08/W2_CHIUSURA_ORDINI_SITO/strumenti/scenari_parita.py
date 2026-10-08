"""Scenari di parita' del greenup SENZA esposizione: stesso input al worker di HEAD
(b5547eb) e al worker modificato, confronto byte per byte degli esiti."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import flumine  # noqa: F401 - applica il patch del ladder a dict
from betfairlightweight.resources import MarketBook
from flumine import BaseStrategy


def _mb(market_id: str, runners: List[Dict[str, Any]]) -> MarketBook:
    return MarketBook(marketId=market_id, isMarketDataDelayed=False, status="OPEN",
                      betDelay=0, bspReconciled=False, complete=True, inplay=True,
                      numberOfWinners=1, numberOfRunners=len(runners),
                      numberOfActiveRunners=len(runners), totalMatched=0.0,
                      totalAvailable=0.0, crossMatching=True, runnersVoidable=False,
                      version=1, runners=runners, publishTime=1_700_000_000_000)


def _runner(sel: int, atb: List[tuple], atl: List[tuple]) -> Dict[str, Any]:
    return {"selectionId": sel, "handicap": 0.0, "status": "ACTIVE",
            "ex": {"availableToBack": [{"price": p, "size": s} for p, s in atb],
                   "availableToLay": [{"price": p, "size": s} for p, s in atl],
                   "tradedVolume": []}}


class Blotter:
    def __init__(self, exp: Dict[int, Dict[str, float]]) -> None:
        self.exp = exp

    def get_exposures(self, strategy: Any, lookup: tuple) -> Dict[str, float]:
        return dict(self.exp.get(int(lookup[1]), {"matched_profit_if_win": 0.0,
                                                  "matched_profit_if_lose": 0.0}))

    def strategy_orders(self, strategy: Any) -> List[Any]:
        return []


class Market:
    def __init__(self, market_id: str, book: MarketBook, exp: Dict[int, Dict[str, float]]):
        self.market_id = market_id
        self.market_book = book
        self.blotter = Blotter(exp)
        self.calls: List[Dict[str, Any]] = []

    def place_order(self, order: Any, **kw: Any) -> bool:
        self.calls.append({"side": order.side, "price": order.order_type.price,
                           "size": order.order_type.size,
                           "persistence": order.order_type.persistence_type,
                           "kw": sorted(kw.keys()),
                           "csr": kw.get("customer_strategy_ref")})
        return True


class Sb:
    def __init__(self, row: Dict[str, Any]) -> None:
        self.row = row
        self.updates: List[Dict[str, Any]] = []
        self.altro: List[str] = []

    def table(self, name: str) -> Any:
        sb = self

        class Q:
            def __init__(self) -> None:
                self.payload = None

            def update(self, payload):
                self.payload = payload
                return self

            def insert(self, payload):
                sb.altro.append(name)
                return self

            def select(self, *a):
                sb.altro.append("select:" + name)
                return self

            def eq(self, *a):
                return self

            def in_(self, *a):
                return self

            def execute(self):
                if self.payload is not None and name == "betfair_live_order_requests":
                    p = dict(self.payload)
                    p.pop("processed_at", None)
                    sb.updates.append(p)
                return SimpleNamespace(data=[])
        return Q()

    def rpc(self, *a, **k):
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=None))


MO = "1.100"
OU = "1.200"
SEL = 47999


def scenari() -> List[Dict[str, Any]]:
    out = []
    lay_led = {SEL: {"matched_profit_if_win": 10.0, "matched_profit_if_lose": -5.0}}
    back_led = {SEL: {"matched_profit_if_win": -8.0, "matched_profit_if_lose": 4.0}}
    flat = {SEL: {"matched_profit_if_win": 3.0, "matched_profit_if_lose": 3.0}}
    plist = [None, {}, {"fraction": 0.5}, {"amount": 2.5}, {"amount": 100.0},
             {"target_price": 3.5}, {"place_at_ticks": 2}, {"persistence": "PERSIST"},
             {"cancel_unmatched": True}, {"esposizione": None},
             {"esposizione": None, "fraction": 0.25}, {"amount": "x"},
             {"persistence": "BOH"}, {"cancel_unmatched": True, "target_price": 3.5},
             {"fraction": 1.0, "ft_parent": 9, "ft_retry": 1},
             {"allow_sub_minimum": False, "fraction": 0.05}]
    for nome_exp, exp in (("lay_led", lay_led), ("back_led", back_led), ("flat", flat)):
        for i, p in enumerate(plist):
            out.append({"nome": f"MO-{nome_exp}-{i}", "market": MO, "exp": exp,
                        "params": p})
    # mercato a due esiti: l'altra selezione pesa
    ou_exp = {SEL: {"matched_profit_if_win": 6.0, "matched_profit_if_lose": -3.0},
              48000: {"matched_profit_if_win": -2.0, "matched_profit_if_lose": 1.0}}
    for i, p in enumerate([None, {"fraction": 0.5}, {"esposizione": None}]):
        out.append({"nome": f"OU-{i}", "market": OU, "exp": ou_exp, "params": p})
    return out


def esegui(wk: Any, sc: Dict[str, Any]) -> Dict[str, Any]:
    if sc["market"] == MO:
        book = _mb(MO, [_runner(SEL, [(2.98, 60)], [(3.0, 80)]),
                        _runner(48000, [(4.0, 10)], [(4.2, 10)]),
                        _runner(58805, [(3.4, 10)], [(3.5, 10)])])
    else:
        book = _mb(OU, [_runner(SEL, [(1.9, 60)], [(1.95, 80)]),
                        _runner(48000, [(2.0, 10)], [(2.1, 10)])])
    market = Market(sc["market"], book, sc["exp"])
    fl = SimpleNamespace(markets=SimpleNamespace(markets={sc["market"]: market}))
    row = {"id": 77, "action": "greenup", "mode": "paper", "status": "processing",
           "market_id": sc["market"], "selection_id": SEL, "handicap": 0,
           "side": None, "price": None, "size": None, "params": sc["params"],
           "result": None, "error": None}
    sb = Sb(row)
    strat = BaseStrategy(market_filter={}, name="live_trading")
    errore = None
    try:
        wk._dispatch(sb, fl, row, "paper", strat)
    except Exception as ex:  # noqa: BLE001
        errore = f"{type(ex).__name__}: {ex}"
    return json.loads(json.dumps({"calls": market.calls, "updates": sb.updates,
                                  "errore": errore, "altro": sb.altro}, default=str))
