"""GridStrategy — LAB separato (NON tocca lo scalper). Grid/ladder maker.

Modello: ladder di livelli attorno a un centro (static o EMA). Su ogni livello
un SEED resting: BACK se il livello e' sopra il centro, LAY se sotto. Quando il
seed si riempie, piazza il TAKE-PROFIT uno step verso il centro (back-alto/lay-
basso = profitto) e, alla chiusura del TP, ri-arma il livello. Cap di inventario
netto come controllo del rischio. Force-flat prima del KO e su rottura di banda.

Config (scalper_params-like), tutti opzionali con default:
  market_types: set|None    tipi mercato da operare (None=tutti; es {"MATCH_ODDS"})
  under_only: bool          su OVER_UNDER opera SOLO la selezione "Under" (theta)
  step_ticks: int=1         spaziatura griglia
  levels: int=3             livelli per lato
  stake: float=10           size per livello
  center_mode: "ema"|"static"
  ema_span_ms: int=60000
  recenter_ticks: int=0     se il centro si sposta >= N tick, ricentra (0=static)
  inv_cap_units: float=3    max |inventario netto| in multipli di stake
  side_bias: "sym"|"long"|"short"   asimmetria (long=solo back-sopra=accumula back)
  price_min/max, min_size   gate liquidita'
  allow_inplay: bool=False
  inplay_from_s/to_s: float finestra in-play (0/0 = tutto l'in-play)
  scoreless_only: bool      (theta) entra solo se il book NON e' esploso (proxy 0-0)
  regime_break_ticks: int=0 flatten se il prezzo sfonda la banda di N tick (0=off)
  flatten_before_s: 120     chiusura forzata pre-KO
  entry_stop_before_s: 300  stop nuovi seed pre-KO
"""
from __future__ import annotations

import datetime as _dt
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.order import OrderStatus
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade
from flumine.utils import get_nearest_price, get_price, get_size, price_ticks_away

# matematica TESTATA riusata dallo scalper (import puro, nessuna modifica al bot)
from Betfair.stream.scalper.scalper_bot import (
    compute_green, micro_price, ticks_between,
)

logger = logging.getLogger(__name__)
_EPS = 1e-9
MIN_STAKE = 2.0


@dataclass
class _Rung:
    level: float                 # odds del livello (sulla ladder)
    side: str                    # "BACK" (sopra centro) | "LAY" (sotto)
    seed: Optional[Any] = None   # ordine seed
    tp: Optional[Any] = None     # ordine take-profit
    tp_price: Optional[float] = None


@dataclass
class _Slot:
    center: Optional[float] = None
    rungs: List[_Rung] = field(default_factory=list)
    flatten_orders: List[Any] = field(default_factory=list)
    flat_tries: int = 0
    flattening: bool = False
    first_seen: Optional[int] = None
    hist: Deque[Tuple[int, float]] = field(default_factory=lambda: deque(maxlen=256))
    done: bool = False           # chiuso definitivamente (post force-flat)


class GridStrategy(BaseStrategy):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx = dict(kwargs.pop("grid_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx}

        mt = c.get("market_types")
        self.market_types: Optional[set] = set(mt) if mt else None
        self.under_only: bool = bool(c.get("under_only", False))
        self.step_ticks: int = max(1, int(c.get("step_ticks", 1)))
        self.levels: int = max(1, int(c.get("levels", 3)))
        self.stake: float = max(MIN_STAKE, float(c.get("stake", 10.0)))
        self.center_mode: str = str(c.get("center_mode", "ema")).lower()
        self.ema_span_ms: int = int(c.get("ema_span_ms", 60_000))
        self.recenter_ticks: int = int(c.get("recenter_ticks", 0))
        self.inv_cap_units: float = float(c.get("inv_cap_units", 3.0))
        self.side_bias: str = str(c.get("side_bias", "sym")).lower()
        self.price_min: float = float(c.get("price_min", 1.20))
        self.price_max: float = float(c.get("price_max", 6.0))
        self.min_size: float = float(c.get("min_size", 50.0))
        self.allow_inplay: bool = bool(c.get("allow_inplay", False))
        self.inplay_from_s: float = float(c.get("inplay_from_s", 0.0))
        self.inplay_to_s: float = float(c.get("inplay_to_s", 0.0))
        self.scoreless_only: bool = bool(c.get("scoreless_only", False))
        self.regime_break_ticks: int = int(c.get("regime_break_ticks", 0))
        self.flatten_before_s: float = float(c.get("flatten_before_s", 120.0))
        self.entry_stop_before_s: float = float(c.get("entry_stop_before_s", 300.0))
        self.force_flat: bool = False

        self._slots: Dict[Tuple[str, int], _Slot] = {}
        self._settled_by_id: Dict[Any, Tuple[Any, str]] = {}
        self._ko_ms: Dict[str, Optional[float]] = {}
        # ultimo micro-price per (market, selection): per il mark-to-market
        # onesto del residuo a fine dati (nessun look-ahead: e' l'ultimo
        # book realmente osservato).
        self.last_mids: Dict[Tuple[str, int], float] = {}
        self.stats: Dict[str, float] = {
            "orders": 0, "seed_fills": 0, "tp_fills": 0, "roundtrips": 0,
            "flattens": 0, "pnl_locked": 0.0, "max_inv": 0.0,
        }

    # ------------------------------------------------------------ telemetria
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

    def _slot(self, mid: str, sid: int) -> _Slot:
        k = (mid, int(sid))
        s = self._slots.get(k)
        if s is None:
            s = _Slot()
            self._slots[k] = s
        return s

    # --------------------------------------------------------------- flumine
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        if getattr(market_book, "status", None) != "OPEN":
            return False
        if not getattr(market_book, "runners", None):
            return False
        if self.market_types is not None:
            md = getattr(market_book, "market_definition", None)
            mtype = getattr(md, "market_type", None) or getattr(market, "market_type", None)
            if mtype not in self.market_types:
                return False
        return True

    def _ko_epoch_ms(self, mb: Any) -> Optional[float]:
        mid = mb.market_id
        cached = self._ko_ms.get(mid)
        if cached is not None:
            return cached
        ko = None
        md = getattr(mb, "market_definition", None)
        mt = getattr(md, "market_time", None) if md is not None else None
        ts_fn = getattr(mt, "timestamp", None)
        if callable(ts_fn):
            try:
                if getattr(mt, "tzinfo", None) is None:
                    mt = mt.replace(tzinfo=_dt.timezone.utc)
                ko = float(mt.timestamp()) * 1000.0
            except (TypeError, ValueError, OSError, OverflowError):
                ko = None
        if ko is not None:
            self._ko_ms[mid] = ko
        return ko

    def _under_selection(self, market_book: Any, runner: Any) -> bool:
        """True se la selezione e' la gamba 'Under' del mercato OVER_UNDER.

        Il firehose NON porta i nomi runner. VERIFICATO sui dati (35768297,
        finestra scoreless 0'-50'): sortPriority 1 = UNDER (47972: 2.16->1.32,
        scende col tempo senza gol), sortPriority 2 = OVER (47973: 1.86->4.30,
        sale). Under = sortPriority 1. Riferimento statico, nessun look-ahead.
        """
        md = getattr(market_book, "market_definition", None)
        for rd in (getattr(md, "runners", None) or []):
            if int(getattr(rd, "selection_id", -1)) == int(runner.selection_id):
                return int(getattr(rd, "sort_priority", 0) or 0) == 1
        return False

    def process_market_book(self, market: Any, market_book: Any) -> None:
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        mid = market_book.market_id
        inplay = bool(getattr(market_book, "inplay", False))

        near_ko = False
        no_entry = False
        if self.force_flat:
            near_ko = True
        elif not self.allow_inplay and inplay:
            near_ko = True
        else:
            ko = self._ko_epoch_ms(market_book)
            if ko is not None and not inplay:
                left = (ko - now) / 1000.0
                if self.flatten_before_s > 0 and left <= self.flatten_before_s:
                    near_ko = True
                if self.entry_stop_before_s > 0 and left <= self.entry_stop_before_s:
                    no_entry = True

        for runner in market_book.runners:
            if getattr(runner, "status", None) != "ACTIVE":
                continue
            ex = getattr(runner, "ex", None)
            if ex is None:
                continue
            bb = get_price(ex.available_to_back, 0)
            bl = get_price(ex.available_to_lay, 0)
            sb = get_size(ex.available_to_back, 0)
            sl = get_size(ex.available_to_lay, 0)
            mp = micro_price(bb, sb, bl, sl)
            slot = self._slot(mid, int(runner.selection_id))
            if slot.first_seen is None:
                slot.first_seen = int(now)
            if mp is not None:
                slot.hist.append((int(now), float(mp)))
                self.last_mids[(mid, int(runner.selection_id))] = float(mp)
                # EMA del centro
                if slot.center is None:
                    slot.center = mp
                elif self.center_mode == "ema":
                    # alpha ~ dt/span, clamp
                    a = 0.02
                    slot.center = slot.center + a * (mp - slot.center)

            if slot.done:
                continue

            # filtro selezione (theta: solo Under)
            if self.under_only and not self._under_selection(market_book, runner):
                continue

            # regime break: flatten se il prezzo sfonda la banda
            if (self.regime_break_ticks > 0 and slot.center and mp is not None
                    and not slot.flattening):
                d = ticks_between(min(slot.center, mp), max(slot.center, mp))
                if d is not None and d > self.levels * self.step_ticks + self.regime_break_ticks:
                    self._flatten_all(market, slot)

            if near_ko:
                self._flatten_all(market, slot)
            if slot.flattening:
                self._drive_flatten(market, slot, bb, bl, now)
                continue

            # gate liquidita'/prezzo
            if bb is None or bl is None or mp is None or slot.center is None:
                continue
            if not (self.price_min <= bb <= self.price_max):
                continue
            if (sb or 0.0) < self.min_size or (sl or 0.0) < self.min_size:
                continue

            # finestra in-play
            if inplay:
                if not self.allow_inplay:
                    continue
                if self.inplay_to_s > 0:
                    ko = self._ko_epoch_ms(market_book)
                    el = (now - ko) / 1000.0 if ko else None
                    if el is None or not (self.inplay_from_s <= el <= self.inplay_to_s):
                        continue
            elif no_entry:
                # niente nuovi seed sotto il buffer pre-KO (ma gestisci i tp)
                self._manage_rungs(market, slot, now, bb, bl, seed_new=False)
                continue

            self._manage_rungs(market, slot, now, bb, bl, seed_new=True)

    def _net_inventory(self, slot: _Slot) -> float:
        """Inventario netto in stake (back - lay) su TUTTI gli ordini matchati."""
        sb = sl = 0.0
        for r in slot.rungs:
            for o in (r.seed, r.tp):
                if o is None:
                    continue
                m = float(getattr(o, "size_matched", 0.0) or 0.0)
                if (getattr(o, "side", "") or "").upper() == "BACK":
                    sb += m
                else:
                    sl += m
        for o in slot.flatten_orders:
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if (getattr(o, "side", "") or "").upper() == "BACK":
                sb += m
            else:
                sl += m
        return sb - sl

    def _manage_rungs(self, market: Any, slot: _Slot, now: int,
                      bb: float, bl: float, seed_new: bool) -> None:
        center = slot.center
        inv = self._net_inventory(slot)
        self.stats["max_inv"] = max(self.stats["max_inv"], abs(inv))
        cap = self.inv_cap_units * self.stake

        # 1) gestisci le rung esistenti: seed pieno -> piazza tp; tp pieno -> chiudi
        for r in list(slot.rungs):
            seed_m = float(getattr(r.seed, "size_matched", 0.0) or 0.0) if r.seed else 0.0
            if seed_m > 0 and r.tp is None:
                # take-profit uno step verso il centro
                if r.side == "BACK":
                    # backato ALTO (level) -> chiudo layando piu' BASSO = profitto
                    tp_price = price_ticks_away(get_nearest_price(r.level), -self.step_ticks)
                    tp_side = "LAY"
                else:
                    # layato BASSO (level) -> chiudo backando piu' ALTO = profitto
                    tp_price = price_ticks_away(get_nearest_price(r.level), +self.step_ticks)
                    tp_side = "BACK"
                if tp_price and tp_price > 1.0:
                    o = self._place(market, r.seed.selection_id, tp_side, tp_price, seed_m)
                    if o is not None:
                        r.tp = o
                        r.tp_price = tp_price
                        self.stats["seed_fills"] += 1
                continue
            if r.tp is not None:
                tp_m = float(getattr(r.tp, "size_matched", 0.0) or 0.0)
                if tp_m > 0 and not self._has_live(r.tp):
                    # roundtrip completo: profitto realizzato, libera la rung
                    self.stats["tp_fills"] += 1
                    self.stats["roundtrips"] += 1
                    # sposta gli ordini in contabilita' e rimuovi la rung
                    slot.flatten_orders.append(r.seed)
                    slot.flatten_orders.append(r.tp)
                    slot.rungs.remove(r)

        if not seed_new:
            return

        # 2) semina i livelli mancanti nella banda (rispettando cap e bias)
        covered = {round(r.level, 4) for r in slot.rungs}
        base = get_nearest_price(center)
        for j in range(1, self.levels + 1):
            up = price_ticks_away(base, +j * self.step_ticks)   # odds piu' alte
            dn = price_ticks_away(base, -j * self.step_ticks)   # odds piu' basse
            # BACK sopra il centro (odds alte) — apre long; salta se bias short
            if up and up > 1.0 and self.price_min <= up <= self.price_max \
                    and round(up, 4) not in covered and self.side_bias != "short":
                if inv - self.stake >= -cap:   # backare aumenta long
                    o = self._place(market, self._sid(slot), "BACK", up, self.stake)
                    if o is not None:
                        slot.rungs.append(_Rung(level=up, side="BACK", seed=o))
                        inv += 0.0  # non ancora matchato
            # LAY sotto il centro (odds basse) — apre short; salta se bias long
            if dn and dn > 1.0 and self.price_min <= dn <= self.price_max \
                    and round(dn, 4) not in covered and self.side_bias != "long":
                if inv + self.stake <= cap:
                    o = self._place(market, self._sid(slot), "LAY", dn, self.stake)
                    if o is not None:
                        slot.rungs.append(_Rung(level=dn, side="LAY", seed=o))

    def _sid(self, slot: _Slot) -> int:
        # recupera il selection_id dalla chiave dello slot
        for (mid, sid), s in self._slots.items():
            if s is slot:
                return int(sid)
        return -1

    def _flatten_all(self, market: Any, slot: _Slot) -> None:
        if slot.flattening:
            return
        for r in slot.rungs:
            self._cancel_if_live(market, r.seed)
            self._cancel_if_live(market, r.tp)
            if r.seed is not None:
                slot.flatten_orders.append(r.seed)
            if r.tp is not None:
                slot.flatten_orders.append(r.tp)
        slot.rungs = []
        slot.flattening = True
        slot.flat_tries = 0

    def _matched(self, *orders: Any) -> Tuple[float, float, float, float]:
        sb = sl = sbp = slp = 0.0
        for o in orders:
            if o is None:
                continue
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
        ob = sbp / sb if sb > 0 else 0.0
        ol = slp / sl if sl > 0 else 0.0
        return sb, ob, sl, ol

    def _drive_flatten(self, market: Any, slot: _Slot,
                       bb: Optional[float], bl: Optional[float], now: int) -> None:
        for r in slot.rungs:
            self._cancel_if_live(market, r.seed)
            self._cancel_if_live(market, r.tp)
        allo = list(slot.flatten_orders)
        for r in slot.rungs:
            allo += [r.seed, r.tp]
        sb, ob, sl, ol = self._matched(*allo)
        nw = sb * (ob - 1.0) - sl * (ol - 1.0)
        nl = sl - sb
        if abs(nw - nl) < _EPS:
            slot.flattening = False
            slot.done = True
            self.stats["flattens"] += 1
            self.stats["pnl_locked"] += nl
            self._emit("flatten_done", locked=round(nl, 4))
            return
        # ripiazza aggressivo
        live = [o for o in slot.flatten_orders if self._has_live(o)]
        if live:
            return
        cross = min(slot.flat_tries, 8)
        if nw > nl:
            base = get_nearest_price(bl) if bl else None
            price = price_ticks_away(base, +cross) if base else None
        else:
            base = get_nearest_price(bb) if bb else None
            price = price_ticks_away(base, -cross) if base else None
        g = compute_green(nw, nl, price) if price else None
        slot.flat_tries += 1
        if g is not None:
            side, size, _lock = g
            o = self._place(market, self._sid(slot), side, price, size, floor=False)
            if o is not None:
                slot.flatten_orders.append(o)
        elif bb is None and bl is None and slot.flat_tries > 40:
            slot.flattening = False
            slot.done = True

    def _place(self, market: Any, sid: int, side: str, price: float,
               size: float, floor: bool = True) -> Optional[Any]:
        size = round(float(size), 2)
        if floor and size < MIN_STAKE:
            size = MIN_STAKE
        if size < 0.01:
            return None
        price = float(price)
        if price <= 1.0:
            return None
        self.stats["orders"] += 1
        trade = Trade(market_id=market.market_id, selection_id=int(sid),
                      handicap=0.0, strategy=self)
        order = trade.create_order(
            side=side,
            order_type=LimitOrder(price=price, size=size, persistence_type="LAPSE"))
        market.place_order(order)
        return order

    @staticmethod
    def _has_live(order: Any) -> bool:
        if order is None:
            return False
        if getattr(order, "status", None) not in (OrderStatus.EXECUTABLE, OrderStatus.PENDING):
            return False
        return float(getattr(order, "size_remaining", 0.0) or 0.0) > _EPS

    @staticmethod
    def _cancel_if_live(market: Any, order: Any) -> None:
        if order is None:
            return
        if getattr(order, "status", None) in (OrderStatus.EXECUTABLE, OrderStatus.PENDING):
            if float(getattr(order, "size_remaining", 0.0) or 0.0) > _EPS:
                try:
                    market.cancel_order(order)
                except Exception:  # noqa: BLE001
                    pass

    def process_closed_market(self, market: Any, market_book: Any) -> None:
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
