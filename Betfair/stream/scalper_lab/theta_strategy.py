"""ThetaStrategy — LAB separato (NON tocca lo scalper). Time-decay DIREZIONALE.

Tesi: in-play, mentre la partita e' scoreless, la quota UNDER cala col tempo
(theta). La catturiamo DIREZIONALMENTE: BACK Under (maker, in coda al best
back), tieni mentre la quota scende, GREEN al target (lay piu' basso = profitto),
TAGLIA subito se la quota sale di stop_ticks (= gol / rischio). Force-flat a fine
finestra / KO. Under identificato da sortPriority==1 (verificato sui dati).

Niente look-ahead: solo book corrente + medie passate. Il gol si scopre DAL
book (salto avverso di stop_ticks o mercato sospeso), mai dai punteggi.

Config (theta_params):
  lines: list tipi OU da operare (default ["OVER_UNDER_25","OVER_UNDER_35"])
  stake: float=10          size per unita'
  max_units: int=3         quante unita' accumulare (pyramiding sulla deriva)
  add_step_ticks: int=3    aggiungi 1 unita' ogni N tick di discesa favorevole
  target_ticks: int=4      green quando la quota e' scesa di N tick dall'ingresso
  stop_ticks: int=3        flatten se la quota SALE di N tick (gol/avverso)
  entry_mode: "maker"|"taker"
  inplay_from_s/to_s: finestra (default 300..2400 = 5'-40')
  price_min/max, min_size  gate liquidita'
  flatten_before_s: 60     (usato solo se si opera anche a fine 1T)
  reenter: bool=True       riapre dopo un green se ancora in finestra
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.order import OrderStatus
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade
from flumine.utils import get_nearest_price, get_price, get_size, price_ticks_away

from Betfair.stream.scalper.scalper_bot import compute_green, ticks_between

logger = logging.getLogger(__name__)
_EPS = 1e-9
MIN_STAKE = 2.0


@dataclass
class _Pos:
    entries: List[Any] = field(default_factory=list)
    close: Optional[Any] = None
    flatten_orders: List[Any] = field(default_factory=list)
    flattening: bool = False
    flat_tries: int = 0
    done: bool = False
    entry_odds: Optional[float] = None   # miglior quota di back all'ultimo ingresso
    units: int = 0
    last_add_odds: Optional[float] = None
    close_locked: float = 0.0            # green atteso del lay di chiusura pre-piazzato


class ThetaStrategy(BaseStrategy):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx = dict(kwargs.pop("theta_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx}
        self.lines = set(c.get("lines", ["OVER_UNDER_25", "OVER_UNDER_35"]))
        # direzione: "under" (sortPriority 1, short-gamma, incassa theta) oppure
        # "over" (sortPriority 2, long-gamma, vince sui gol). Il resto della
        # logica e' identico: si opera sulla gamba scelta.
        self.direction = str(c.get("direction", "under")).lower()
        self.stake = max(MIN_STAKE, float(c.get("stake", 10.0)))
        self.max_units = int(c.get("max_units", 3))
        self.add_step_ticks = int(c.get("add_step_ticks", 3))
        self.target_ticks = int(c.get("target_ticks", 4))
        self.stop_ticks = int(c.get("stop_ticks", 3))
        self.entry_mode = str(c.get("entry_mode", "maker")).lower()
        self.inplay_from_s = float(c.get("inplay_from_s", 300.0))
        self.inplay_to_s = float(c.get("inplay_to_s", 2400.0))
        self.price_min = float(c.get("price_min", 1.20))
        self.price_max = float(c.get("price_max", 1000.0))
        self.min_size = float(c.get("min_size", 50.0))
        self.reenter = bool(c.get("reenter", True))
        self.force_flat = False

        self._pos: Dict[Tuple[str, int], _Pos] = {}
        self._settled_by_id: Dict[Any, Tuple[Any, str]] = {}
        self._ko_ms: Dict[str, Optional[float]] = {}
        self.last_mids: Dict[Tuple[str, int], float] = {}
        self.stats = {"orders": 0, "entries": 0, "greens": 0, "stops": 0,
                      "flattens": 0, "pnl_locked": 0.0, "max_units": 0}

    def _emit(self, kind: str, **p: Any) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, p)
        except Exception:  # noqa: BLE001
            pass

    @property
    def settled_orders(self):
        return list(self._settled_by_id.values())

    def _p(self, mid: str, sid: int) -> _Pos:
        k = (mid, int(sid))
        v = self._pos.get(k)
        if v is None:
            v = _Pos()
            self._pos[k] = v
        return v

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        if getattr(market_book, "status", None) != "OPEN":
            return False
        if not getattr(market_book, "runners", None):
            return False
        md = getattr(market_book, "market_definition", None)
        mtype = getattr(md, "market_type", None) or getattr(market, "market_type", None)
        return mtype in self.lines

    def _ko_epoch_ms(self, mb: Any) -> Optional[float]:
        mid = mb.market_id
        if self._ko_ms.get(mid) is not None:
            return self._ko_ms[mid]
        ko = None
        md = getattr(mb, "market_definition", None)
        mt = getattr(md, "market_time", None) if md is not None else None
        if callable(getattr(mt, "timestamp", None)):
            try:
                if getattr(mt, "tzinfo", None) is None:
                    mt = mt.replace(tzinfo=_dt.timezone.utc)
                ko = float(mt.timestamp()) * 1000.0
            except (TypeError, ValueError, OSError, OverflowError):
                ko = None
        if ko is not None:
            self._ko_ms[mid] = ko
        return ko

    def _is_target(self, mb: Any, runner: Any) -> bool:
        """La gamba da operare: Under=sortPriority 1, Over=sortPriority 2."""
        want = 1 if self.direction == "under" else 2
        md = getattr(mb, "market_definition", None)
        for rd in (getattr(md, "runners", None) or []):
            if int(getattr(rd, "selection_id", -1)) == int(runner.selection_id):
                return int(getattr(rd, "sort_priority", 0) or 0) == want
        return False

    def process_market_book(self, market: Any, market_book: Any) -> None:
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        mid = market_book.market_id
        inplay = bool(getattr(market_book, "inplay", False))
        ko = self._ko_epoch_ms(market_book)
        el = (now - ko) / 1000.0 if ko else None

        for runner in market_book.runners:
            if getattr(runner, "status", None) != "ACTIVE":
                continue
            if not self._is_target(market_book, runner):
                continue
            ex = getattr(runner, "ex", None)
            if ex is None:
                continue
            bb = get_price(ex.available_to_back, 0)
            bl = get_price(ex.available_to_lay, 0)
            sb = get_size(ex.available_to_back, 0)
            sl = get_size(ex.available_to_lay, 0)
            pos = self._p(mid, int(runner.selection_id))
            if bb and bl:
                self.last_mids[(mid, int(runner.selection_id))] = (bb + bl) / 2.0
            if pos.done:
                continue

            # force-flat globale o fuori finestra con posizione aperta
            out_window = not (inplay and el is not None
                              and self.inplay_from_s <= el <= self.inplay_to_s)
            has_pos = bool(pos.entries) or pos.flattening
            if (self.force_flat or out_window) and has_pos and not pos.flattening:
                self._begin_flatten(market, pos)
            if pos.flattening:
                self._drive_flatten(market, pos, bb, bl, now)
                continue

            if bb is None or bl is None:
                continue
            if not (self.price_min <= bb <= self.price_max):
                continue

            # --- gestione posizione aperta ---
            if pos.entries:
                filled = sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                             for o in pos.entries)
                if filled > 0:
                    sb_m, ob, sl_m, ol = self._matched(pos.entries)
                    # STOP: la quota (best back) e' salita di stop_ticks sopra
                    # l'ingresso medio -> gol/avverso -> flatten
                    up = ticks_between(get_nearest_price(ob), get_nearest_price(bb)) \
                        if (ob and bb and bb > ob) else 0
                    if up is not None and up >= self.stop_ticks:
                        self.stats["stops"] += 1
                        self._emit("stop", up=up)
                        self._begin_flatten(market, pos)
                        continue
                    # TARGET PRE-PIAZZATO (fix utente 07/07): appena l'ingresso e'
                    # riempito, metti UNA VOLTA il lay di chiusura al prezzo ESATTO
                    # (ingresso - target_ticks) come maker resting e ASPETTA che si
                    # riempia. Niente inseguimento del best_lay (che con 8s di ritardo
                    # riempie a prezzo peggiore -> layava piu' ALTO del back = perdita).
                    if pos.close is None and ob and ob > 1.0:
                        tgt = price_ticks_away(get_nearest_price(ob), -self.target_ticks)
                        if tgt and tgt > 1.0:
                            nw = sb_m * (ob - 1.0) - sl_m * (ol - 1.0)
                            nl = sl_m - sb_m
                            g = compute_green(nw, nl, tgt)
                            if g is not None:
                                side, size, locked = g
                                o = self._place(market, runner.selection_id, side,
                                                tgt, size, floor=False)
                                if o is not None:
                                    pos.close = o
                                    pos.close_locked = locked
                    # close riempita -> ciclo chiuso (GREEN reale), eventuale re-enter
                    if pos.close is not None and not self._has_live(pos.close) \
                            and float(getattr(pos.close, "size_matched", 0.0) or 0.0) > 0:
                        self.stats["greens"] += 1
                        self.stats["pnl_locked"] += getattr(pos, "close_locked", 0.0)
                        self._emit("green", locked=round(getattr(pos, "close_locked", 0.0), 3))
                        pos.flatten_orders.extend(pos.entries)
                        pos.flatten_orders.append(pos.close)
                        pos.entries = []
                        pos.close = None
                        pos.close_locked = 0.0
                        pos.units = 0
                        pos.entry_odds = None
                        if not self.reenter:
                            pos.done = True
                        continue
                    # PYRAMIDING: aggiungi 1 unita' se la quota e' scesa di
                    # add_step_ticks dall'ultimo ingresso e c'e' spazio
                    if (pos.units < self.max_units and pos.close is None
                            and pos.last_add_odds and bb < pos.last_add_odds):
                        drop = ticks_between(get_nearest_price(bb),
                                             get_nearest_price(pos.last_add_odds))
                        if drop is not None and drop >= self.add_step_ticks:
                            self._enter(market, runner, pos, bb, bl, sb, sl)
                continue

            # --- nessuna posizione: entra se in finestra e liquidita' ok ---
            if out_window:
                continue
            if (sb or 0) < self.min_size or (sl or 0) < self.min_size:
                continue
            self._enter(market, runner, pos, bb, bl, sb, sl)

    def _enter(self, market, runner, pos, bb, bl, sb, sl) -> None:
        if self.entry_mode == "taker":
            price = get_nearest_price(bl)   # cross: back al best lay (immediato)
        else:
            price = get_nearest_price(bb)   # maker: in coda al best back
        if not price or price <= 1.0:
            return
        o = self._place(market, runner.selection_id, "BACK", price, self.stake)
        if o is not None:
            pos.entries.append(o)
            pos.units += 1
            pos.entry_odds = price
            pos.last_add_odds = price
            self.stats["entries"] += 1
            self.stats["max_units"] = max(self.stats["max_units"], pos.units)

    def _matched(self, orders) -> Tuple[float, float, float, float]:
        sb = sl = sbp = slp = 0.0
        for o in orders:
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if m <= 0:
                continue
            p = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if p <= 0:
                continue
            if (getattr(o, "side", "") or "").upper() == "BACK":
                sb += m; sbp += p * m
            else:
                sl += m; slp += p * m
        return sb, (sbp / sb if sb else 0.0), sl, (slp / sl if sl else 0.0)

    def _begin_flatten(self, market, pos) -> None:
        for o in pos.entries + ([pos.close] if pos.close else []):
            self._cancel_if_live(market, o)
        pos.flatten_orders.extend([o for o in pos.entries if o is not None])
        if pos.close is not None:
            pos.flatten_orders.append(pos.close)
        pos.entries = []
        pos.close = None
        pos.flattening = True
        pos.flat_tries = 0

    def _drive_flatten(self, market, pos, bb, bl, now) -> None:
        for o in pos.flatten_orders:
            if self._has_live(o):
                self._cancel_if_live(market, o)
        sb, ob, sl, ol = self._matched(pos.flatten_orders)
        nw = sb * (ob - 1.0) - sl * (ol - 1.0)
        nl = sl - sb
        if abs(nw - nl) < _EPS:
            pos.flattening = False
            pos.done = True
            self.stats["flattens"] += 1
            self.stats["pnl_locked"] += nl
            return
        if any(self._has_live(o) for o in pos.flatten_orders):
            return
        cross = min(pos.flat_tries, 8)
        if nw > nl:
            base = get_nearest_price(bl) if bl else None
            price = price_ticks_away(base, +cross) if base else None
        else:
            base = get_nearest_price(bb) if bb else None
            price = price_ticks_away(base, -cross) if base else None
        g = compute_green(nw, nl, price) if price else None
        pos.flat_tries += 1
        if g is not None:
            side, size, _l = g
            o = self._place(market, self._sid(pos), side, price, size, floor=False)
            if o is not None:
                pos.flatten_orders.append(o)
        elif bb is None and bl is None and pos.flat_tries > 40:
            pos.flattening = False
            pos.done = True

    def _sid(self, pos) -> int:
        for (mid, sid), p in self._pos.items():
            if p is pos:
                return int(sid)
        return -1

    def _place(self, market, sid, side, price, size, floor=True) -> Optional[Any]:
        size = round(float(size), 2)
        if floor and size < MIN_STAKE:
            size = MIN_STAKE
        if size < 0.01 or price <= 1.0:
            return None
        self.stats["orders"] += 1
        tr = Trade(market_id=market.market_id, selection_id=int(sid),
                   handicap=0.0, strategy=self)
        o = tr.create_order(side=side, order_type=LimitOrder(
            price=float(price), size=size, persistence_type="LAPSE"))
        market.place_order(o)
        return o

    @staticmethod
    def _has_live(o) -> bool:
        if o is None:
            return False
        if getattr(o, "status", None) not in (OrderStatus.EXECUTABLE, OrderStatus.PENDING):
            return False
        return float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS

    @staticmethod
    def _cancel_if_live(market, o) -> None:
        if o is None:
            return
        if getattr(o, "status", None) in (OrderStatus.EXECUTABLE, OrderStatus.PENDING):
            if float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS:
                try:
                    market.cancel_order(o)
                except Exception:  # noqa: BLE001
                    pass

    def process_closed_market(self, market, market_book) -> None:
        md = getattr(market_book, "market_definition", None)
        mtype = (getattr(md, "market_type", None)
                 or getattr(market, "market_type", None) or "UNKNOWN")
        try:
            orders = market.blotter.strategy_orders(self)
        except Exception:  # noqa: BLE001
            orders = []
        for o in orders:
            oid = getattr(o, "id", None) or id(o)
            self._settled_by_id[oid] = (o, mtype)
