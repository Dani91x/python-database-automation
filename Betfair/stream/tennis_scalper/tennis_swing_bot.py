"""TennisSwingStrategy — fade degli ESTREMI del favorito con esecuzione MAKER.

Detector research-grounded (mean-reversion): tick-index + z robusto (mediana/MAD)
+ gate di regime (Efficiency Ratio) + conferma d'inversione (prezzo girato + RSI
cross) -> entra MAKER contro l'estremo, esce verso l'ancora. Price-driven (nessun
punteggio). Pensato per il backtest con fill REALI (FlumineSimulation +
SimulatedMiddleware: riempie solo sul volume tradato, rispetta la coda).
"""
from __future__ import annotations

import logging
import statistics
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.trade import Trade
from flumine.order.ordertype import LimitOrder
from flumine.utils import get_price, get_size, price_ticks_away, get_nearest_price

from .tennis_scalper_bot import compute_green

logger = logging.getLogger(__name__)
MIN_STAKE = 2.0
_EPS = 1e-9


def _ladder() -> List[float]:
    steps = [(1.01,2,.01),(2,3,.02),(3,4,.05),(4,6,.1),(6,10,.2),(10,20,.5),
             (20,30,1),(30,50,2),(50,100,5),(100,1000,10)]
    pr: List[float] = []
    for lo, hi, inc in steps:
        p = lo
        while p < hi - 1e-9:
            pr.append(round(p, 2)); p = round(p + inc, 2)
    pr.append(1000.0)
    return pr
_LAD = _ladder()
import bisect
def _tki(p: float) -> int:
    return bisect.bisect_left(_LAD, round(p, 2))


class TennisSwingStrategy(BaseStrategy):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx_in: Dict[str, Any] = dict(kwargs.pop("swing_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx_in}
        self.stake = max(MIN_STAKE, float(c.get("stake", 2.0)))
        self.N = int(c.get("N", 40))
        self.zin = float(c.get("zin", 2.0))
        self.er_max = float(c.get("er_max", 0.4))
        self.conf_ticks = int(c.get("conf_ticks", 2))
        self.target_frac = float(c.get("target_frac", 0.5))
        self.stop_ticks = int(c.get("stop_ticks", 8))
        # time-stop in SECONDI di publish_time (fix 2026-07-09: prima contava gli
        # UPDATE del book — in live sono molti al secondo → usciva dopo ~15-20s
        # invece dei 90s documentati; il fallback a update resta solo senza pt).
        self.tmax = int(c.get("tmax", 90))
        # update del book concessi alla chiusura MAKER prima dell'escalation a
        # TAKER al touch (fix orfani: l'hedge maker può non riempirsi MAI).
        self.close_retry_ticks = int(c.get("close_retry_ticks", 20))
        self.maker = bool(c.get("maker", True))
        self.maker_offset = int(c.get("maker_offset", 1))
        self.min_matched = float(c.get("min_matched", 10_000.0))
        self.price_min = float(c.get("price_min", 1.08))
        self.price_max = float(c.get("price_max", 8.0))
        self.dry_run = bool(c.get("dry_run", False))
        # stato per market
        self._hist: Dict[str, deque] = {}       # mid tick history
        self._prev_rsi: Dict[str, float] = {}
        self._tr: Dict[str, Dict[str, Any]] = {}  # trade attivo
        self.stats = {"entries": 0, "wins": 0, "losses": 0, "pnl": 0.0}

    def _emit(self, ev: str, **p: Any) -> None:
        if self.event_sink:
            try: self.event_sink(ev, p)
            except Exception: pass  # noqa

    def check_market_book(self, market: Any, mb: Any) -> bool:
        return getattr(mb, "status", None) == "OPEN" and bool(getattr(mb, "runners", None))

    # ---- indicatori ----
    @staticmethod
    def _er(tk: List[int], N: int) -> float:
        if len(tk) <= N: return 1.0
        seg = tk[-N-1:]
        net = abs(seg[-1]-seg[0]); path = sum(abs(seg[j]-seg[j-1]) for j in range(1,len(seg)))
        return net/path if path else 1.0

    @staticmethod
    def _rsi(tk: List[int], N: int = 14) -> float:
        if len(tk) <= N: return 50.0
        seg = tk[-N-1:]; g = l = 0.0
        for j in range(1, len(seg)):
            d = seg[j]-seg[j-1]
            if d > 0: g += d
            else: l += -d
        if g+l == 0: return 50.0
        return 100 - 100/(1 + g/(l if l else 1e-9))

    def _favourite(self, mb: Any) -> Optional[Any]:
        best = None; bp = 1e9
        for r in mb.runners:
            if getattr(r, "status", None) != "ACTIVE": continue
            ltp = getattr(r, "last_price_traded", None)
            ex = getattr(r, "ex", None)
            p = ltp or (get_price(ex.available_to_back, 0) if ex else None)
            if p and p < bp: bp = p; best = r
        return best

    def _pos(self, market: Any, sel: int) -> Tuple[float, float, float, float]:
        b = bw = l = lw = 0.0
        try: orders = market.blotter.strategy_orders(self)
        except Exception: orders = []  # noqa
        for o in orders:
            if int(getattr(o, "selection_id", 0) or 0) != int(sel): continue
            sm = float(getattr(o, "size_matched", 0.0) or 0.0)
            ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if sm <= _EPS or ap <= 0: continue
            if (getattr(o, "side", "") or "").upper() == "BACK": b += sm; bw += sm*ap
            else: l += sm; lw += sm*ap
        return b, (bw/b if b else 0), l, (lw/l if l else 0)

    def _place(self, market: Any, sel: int, side: str, price: float, size: float) -> Optional[Any]:
        size = round(max(0.0, size), 2)
        if price is None or price <= 1.0 or size < 0.01 or self.dry_run: return None
        try:
            tr = Trade(market_id=market.market_id, selection_id=int(sel), handicap=0, strategy=self)
            o = tr.create_order(side=side, order_type=LimitOrder(price=float(price), size=size, persistence_type="LAPSE"))
            market.place_order(o); return o
        except Exception as e:  # noqa
            logger.debug("place fail %s", e); return None

    def _close(self, market: Any, sel: int, price: float) -> Tuple[float, Optional[Any]]:
        """Piazza l'hedge di green. Ritorna (locked stimato, ordine di chiusura)."""
        b, ba, l, la = self._pos(market, sel)
        nw, nl = b*(ba-1)-l*(la-1), l-b
        g = compute_green(nw, nl, price)
        if g is None: return min(nw, nl), None
        side, sz, locked = g
        o = self._place(market, sel, side, get_nearest_price(price), sz)
        return float(locked), o

    @staticmethod
    def _runner_by_sel(mb: Any, sel: int) -> Optional[Any]:
        for r in mb.runners:
            if int(getattr(r, "selection_id", 0) or 0) == int(sel):
                return r
        return None

    def _cancel(self, market: Any, order: Any) -> None:
        if order is None: return
        try: market.cancel_order(order)
        except Exception: pass  # noqa

    def _manage_trade(self, market: Any, mb: Any, mid: str, tr: Dict[str, Any]) -> None:
        """Gestione del trade aperto sulla SELEZIONE TRADATA (fix 2026-07-09).

        BUG storico: la gestione usava il FAVORITO CORRENTE del book; se il favorito
        flippava a metà trade, la posizione sul vecchio favorito restava ORFANA
        (b+l=0 sul nuovo sel → dopo 40 update il trade veniva scartato con la
        posizione matched ancora aperta, senza stop né uscita). Ora sel/prezzi
        vengono SEMPRE dalla selezione su cui si è entrati.
        """
        sel = int(tr.get("sel") or 0)
        r = self._runner_by_sel(mb, sel)
        ex = getattr(r, "ex", None) if r is not None else None
        if ex is None:
            return  # runner non nel book in questo update: si riprova al prossimo
        bb = get_price(ex.available_to_back, 0); bl = get_price(ex.available_to_lay, 0)
        if not bb or not bl: return
        tmid = _tki((bb+bl)/2)
        side = tr["side"]
        b, ba, l, la = self._pos(market, sel)

        # fase CLOSING: l'hedge MAKER può non riempirsi MAI → mai abbandonare la
        # posizione: dopo close_retry_ticks update si cancella e si chiude TAKER
        # al touch (fill certo, si paga lo spread). Pop SOLO a posizione flat.
        if tr.get("closing"):
            nw, nl = b*(ba-1)-l*(la-1), l-b
            if (b + l) <= _EPS or abs(nw - nl) < 0.01:
                self._cancel(market, tr.get("order"))
                self._cancel(market, tr.get("close_order"))
                self._tr.pop(mid, None)
                return
            tr["close_wait"] = tr.get("close_wait", 0) + 1
            if tr["close_wait"] > self.close_retry_ticks:
                self._cancel(market, tr.get("close_order"))
                px = bl if side == "BACK" else bb   # TAKER al touch: attraversa
                _, o2 = self._close(market, sel, px)
                tr["close_order"] = o2
                tr["close_wait"] = 0
                self._emit("close_escalate", sel=sel, price=px)
            return

        if (b+l) <= _EPS:
            tr["wait"] = tr.get("wait", 0)+1
            if tr["wait"] > 40:  # entry non riempita -> cancella
                self._cancel(market, tr.get("order"))
                self._tr.pop(mid, None)
            return
        tr["held"] = tr.get("held", 0)+1
        etk = tr["etk"]; anchor = tr["anchor"]
        tgt = anchor + (etk-anchor)*(1-self.target_frac)
        hit = (tmid <= tgt) if side == "BACK" else (tmid >= tgt)
        adverse = (tmid >= etk+self.stop_ticks) if side == "BACK" else (tmid <= etk-self.stop_ticks)
        # time-stop in SECONDI di publish_time (fallback: numero update se pt assente)
        pt = getattr(mb, "publish_time_epoch", None)
        t0 = tr.get("t0")
        timed_out = ((pt is not None and t0 is not None and (pt - t0) / 1000.0 >= self.tmax)
                     or ((pt is None or t0 is None) and tr["held"] >= self.tmax))
        if hit or adverse or timed_out:
            # esci a quota migliore (maker) o al touch
            px = (bb if self.maker else bl) if side == "BACK" else (bl if self.maker else bb)
            locked, close_order = self._close(market, sel, px)
            self.stats["pnl"] += locked
            self.stats["wins" if hit else "losses"] += 1
            self._emit("exit", sel=sel, kind="target" if hit else ("stop" if adverse else "time"), locked=round(locked,3))
            self._cancel(market, tr.get("order"))
            # NON si abbandona la posizione: stato closing finché il blotter è flat
            tr["closing"] = True
            tr["close_order"] = close_order
            tr["close_wait"] = 0
        return

    def process_market_book(self, market: Any, mb: Any) -> None:
        mid = mb.market_id
        tr = self._tr.get(mid)
        if tr:  # la GESTIONE della posizione non è mai gateata (né da min_matched
            #     né dal favorito corrente): prima il denaro, poi i segnali.
            self._manage_trade(market, mb, mid, tr)
            return
        if float(getattr(mb, "total_matched", 0) or 0) < self.min_matched: return
        fav = self._favourite(mb)
        if fav is None: return
        ex = fav.ex
        bb = get_price(ex.available_to_back, 0); bl = get_price(ex.available_to_lay, 0)
        if not bb or not bl: return
        sel = int(fav.selection_id)
        tmid = _tki((bb+bl)/2)
        h = self._hist.setdefault(mid, deque(maxlen=200)); h.append(tmid)
        tk = list(h)
        r = self._rsi(tk); pr = self._prev_rsi.get(mid, 50.0); self._prev_rsi[mid] = r

        # ingresso
        if len(tk) <= self.N: return
        base = tk[-self.N:-2] or tk[-self.N:]
        med = statistics.median(base); mad = statistics.median([abs(x-med) for x in base]) or 1e-9
        z = 0.6745*(tmid-med)/mad
        if self._er(tk, 20) >= self.er_max: return          # gate regime
        if not (self.price_min <= (bb+bl)/2 <= self.price_max): return
        turned_down = tmid <= max(tk[-self.conf_ticks-1:])-self.conf_ticks
        turned_up = tmid >= min(tk[-self.conf_ticks-1:])+self.conf_ticks
        side = None; entry_price = None
        if z >= self.zin and turned_down and r < 65 <= pr:      # esteso ALTO -> BACK
            side = "BACK"; entry_price = price_ticks_away(bl, self.maker_offset) if self.maker else bb
        elif z <= -self.zin and turned_up and r > 35 >= pr:     # esteso BASSO -> LAY
            side = "LAY"; entry_price = price_ticks_away(bb, -self.maker_offset) if self.maker else bl
        if side is None: return
        o = self._place(market, sel, side, get_nearest_price(entry_price), self.stake)
        if o is None and not self.dry_run: return
        # sel + t0 MEMORIZZATI nel trade (fix 2026-07-09): la gestione deve seguire la
        # selezione TRADATA (non il favorito corrente) e il time-stop conta i secondi.
        self._tr[mid] = {"sel": sel, "side": side, "etk": tmid, "anchor": med,
                         "order": o, "held": 0, "wait": 0,
                         "t0": getattr(mb, "publish_time_epoch", None)}
        self.stats["entries"] += 1
        self._emit("entry", sel=sel, side=side, z=round(z,2), price=entry_price)

    def process_closed_market(self, market: Any, mb: Any) -> None:
        self.settled_pnl = getattr(self, "settled_pnl", 0.0)
        try:
            for o in market.blotter.strategy_orders(self):
                sim = getattr(o, "simulated", None)
                self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        except Exception: pass  # noqa
