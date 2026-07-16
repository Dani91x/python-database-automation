"""TennisFLBStrategy — LAY del favorito ESTREMO, senza stop (favourite-longshot bias).

L'UNICA strategia risultata POSITIVA nel backtest reale (fill sulla coda, volume
tradato vero): +€1.84 su 2 match. Meccanismo documentato:

  Il mercato SOVRA-prezza le quasi-certezze (favourite-longshot bias, piu' forte
  agli ESTREMI). Layare un favorito a <=1.05-1.10 costa una liability MINUSCOLA
  (stake*(odds-1) ~ 0.10 su 2 EUR) ma, se il "quasi-certo" viene sfidato/crolla,
  l'upside e' l'intero stake. Niente stop: la liability e' cosi' piccola che si
  tiene attraverso lo swing (gli stop ci scuotevano via). Dimitrov e' arrivato a
  1.01 e HA PERSO -> lay tenuto = vinci pieno.

USCITA (configurabile):
  - "green": green-up appena la quota risale di ``green_ticks`` (incassa lo swing,
    non serve che perda il match) -> bassa varianza.
  - "hold":  tiene fino al settlement (vince pieno sul crollo, perde la piccola
    liability se il favorito tiene) -> paga sui crolli, il migliore nel backtest.
  - "hybrid" (default): green-up PARZIALE sullo swing + resto a settlement.

Price-driven: nessun punteggio, nessuna mappa nomi (evita quella classe di bug).
Esecuzione MAKER (rest al best-lay). P&L VERO dal settlement simulato in backtest.

⚠️ Onesta': validato su 2 partite (una col crollo ideale). Va confermato su >=10
match prima del live. Ma e' il primo candidato positivo coi fill reali.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.trade import Trade
from flumine.order.ordertype import LimitOrder
from flumine.utils import get_price, get_size, price_ticks_away, get_nearest_price

from .tennis_scalper_bot import compute_green, ticks_between

logger = logging.getLogger(__name__)
MIN_STAKE = 2.0
_EPS = 1e-9

# stati per (market_id, selection_id)
IDLE, PENDING, OPEN, DONE = "IDLE", "PENDING", "OPEN", "DONE"


class TennisFLBStrategy(BaseStrategy):
    """Lay del favorito estremo, no stop (favourite-longshot bias)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx_in: Dict[str, Any] = dict(kwargs.pop("flb_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx_in}

        self.stake: float = max(MIN_STAKE, float(c.get("stake", 2.0)))
        # soglia: si laya un runner quando il suo best-lay <= lay_max (estremo)
        self.lay_max: float = float(c.get("lay_max", 1.10))
        # ri-arma solo quando il prezzo RIESCE dalla zona (evita re-lay a raffica)
        self.rearm_mult: float = float(c.get("rearm_mult", 1.10))
        # uscita: "green" | "hold" | "hybrid"
        self.exit_mode: str = str(c.get("exit_mode", "hybrid")).lower()
        self.green_ticks: int = int(c.get("green_ticks", 8))     # swing per green-up
        self.green_frac: float = float(c.get("green_frac", 0.5))  # quota greenata (hybrid)
        self.min_matched: float = float(c.get("min_matched", 10_000.0))
        self.min_lay_size: float = float(c.get("min_lay_size", 5.0))
        # TIMEOUT ENTRY in SECONDI di publish_time (fix 2026-07-10 live≠backtest:
        # prima contava gli UPDATE del book — in live sono molti al secondo →
        # l'entry moriva in pochi secondi invece dei ~40s attesi). Nome storico
        # mantenuto: 40 update → 40 s equivalenti (fallback a update senza pt).
        self.entry_timeout: float = float(c.get("entry_timeout", 40))
        # la tesi FLB e' validata IN-PLAY: di default nessun ingresso pre-match.
        self.require_inplay: bool = bool(c.get("require_inplay", True))
        self.dry_run: bool = bool(c.get("dry_run", False))

        # stato runtime
        self._pos_state: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._armed: Dict[Tuple[str, int], bool] = {}
        self.stats: Dict[str, Any] = {"entries": 0, "greens": 0, "held": 0, "pnl": 0.0}
        self.settled_pnl: float = 0.0

    # ------------------------------------------------------------- telemetria
    def _emit(self, event: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event, payload)
        except Exception:  # noqa: BLE001
            logger.debug("event_sink errore", exc_info=True)

    def check_market_book(self, market: Any, mb: Any) -> bool:
        return getattr(mb, "status", None) == "OPEN" and bool(getattr(mb, "runners", None))

    # ------------------------------------------------------- posizione matchata
    def _matched(self, market: Any, sel: int) -> Tuple[float, float, float, float]:
        b = bw = l = lw = 0.0
        try:
            orders = market.blotter.strategy_orders(self)
        except Exception:  # noqa: BLE001
            orders = []
        for o in orders:
            if int(getattr(o, "selection_id", 0) or 0) != int(sel):
                continue
            sm = float(getattr(o, "size_matched", 0.0) or 0.0)
            ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if sm <= _EPS or ap <= 0:
                continue
            if (getattr(o, "side", "") or "").upper() == "BACK":
                b += sm; bw += sm * ap
            else:
                l += sm; lw += sm * ap
        return b, (bw / b if b else 0.0), l, (lw / l if l else 0.0)

    @staticmethod
    def _net(b: float, ba: float, l: float, la: float) -> Tuple[float, float]:
        return b * (ba - 1.0) - l * (la - 1.0), l - b

    def _place(self, market: Any, sel: int, side: str, price: float,
               size: float) -> Optional[Any]:
        size = round(max(0.0, float(size)), 2)
        if price is None or price <= 1.0 or size < 0.01 or self.dry_run:
            if self.dry_run:
                self._emit("dry_place", sel=sel, side=side, price=price, size=size)
            return None
        try:
            tr = Trade(market_id=market.market_id, selection_id=int(sel),
                       handicap=0, strategy=self)
            o = tr.create_order(side=side, order_type=LimitOrder(
                price=float(price), size=size, persistence_type="LAPSE"))
            market.place_order(o)
            return o
        except Exception as exc:  # noqa: BLE001
            logger.debug("place fallito: %s", exc)
            return None

    def _cancel(self, market: Any, order: Any) -> None:
        if order is None:
            return
        try:
            market.cancel_order(order)
        except Exception:  # noqa: BLE001
            pass

    def _green(self, market: Any, sel: int, price: float,
               frac: float) -> Tuple[float, Optional[Any]]:
        """Green-up (parziale se frac<1). Ritorna (locked stimato, ordine hedge).

        Il locked e' REALE solo quando l'hedge risulta matched: l'ordine viene
        ritornato per poterlo sorvegliare/ripiazzare (fix 2026-07-10: prima
        l'hedge non era tracciato e un lapse lasciava la posizione scoperta
        con ``greened=True`` bugiardo in telemetria).
        """
        b, ba, l, la = self._matched(market, sel)
        nw, nl = self._net(b, ba, l, la)
        g = compute_green(nw, nl, price)
        if g is None:
            return min(nw, nl), None
        gside, gsize, _locked_full = g
        p = float(get_nearest_price(price))
        size = gsize * frac
        o = self._place(market, sel, gside, p, size)
        # STIMA ESATTA col frac (fix audit #11): compute_green ritorna il locked
        # del green TOTALE; con frac<1 l'hedge copre solo una parte → il floor
        # reale e' min(nw', nl') DOPO l'hedge parziale. Prima la telemetria
        # sovrastimava il locked di ~2x (green_est bugiardo con hybrid frac=0.5).
        if gside == "LAY":
            nw2, nl2 = nw - size * (p - 1.0), nl + size
        else:
            nw2, nl2 = nw + size * (p - 1.0), nl - size
        return float(min(nw2, nl2)), o

    # stati flumine di un ordine ancora VIVO sul book (il resto e' terminale)
    _LIVE_ORDER_STATUSES = frozenset(
        {"PENDING", "CANCELLING", "UPDATING", "REPLACING", "EXECUTABLE"})

    @classmethod
    def _order_alive(cls, order: Any) -> bool:
        st = getattr(order, "status", None)
        name = getattr(st, "name", None) or (str(st) if st is not None else "")
        return name in cls._LIVE_ORDER_STATUSES

    # -------------------------------------------------------------- main loop
    def process_market_book(self, market: Any, mb: Any) -> None:
        if float(getattr(mb, "total_matched", 0.0) or 0.0) < self.min_matched:
            return
        mid = mb.market_id
        pt = getattr(mb, "publish_time_epoch", None)
        inplay = bool(getattr(mb, "inplay", False))
        for r in mb.runners:
            if getattr(r, "status", None) != "ACTIVE":
                continue
            ex = getattr(r, "ex", None)
            if ex is None:
                continue
            sel = int(r.selection_id)
            bl = get_price(ex.available_to_lay, 0)
            bb = get_price(ex.available_to_back, 0)
            sl = get_size(ex.available_to_lay, 0)
            if not bl or not bb:
                continue
            key = (mid, sel)
            st = self._pos_state.get(key)

            if st and st["state"] in (PENDING, OPEN):
                self._manage(market, sel, key, st, bb, bl, pt)
                continue

            # ri-arma quando il prezzo e' RIUSCITO dalla zona estrema
            if self._armed.get(key, True) is False:
                if bl > self.lay_max * self.rearm_mult:
                    self._armed[key] = True
                continue

            # gate IN-PLAY: la tesi FLB e' validata in-play — pre-match niente
            # ingressi (le posizioni aperte restano gestite sopra).
            if self.require_inplay and not inplay:
                continue

            # INGRESSO: laya il favorito estremo (best-lay <= soglia)
            if bl <= self.lay_max and (sl or 0) >= self.min_lay_size:
                entry = get_nearest_price(bl)
                o = self._place(market, sel, "LAY", entry, self.stake)
                if o is None and not self.dry_run:
                    continue
                self._pos_state[key] = {"state": OPEN, "entry": entry,
                                        "order": o, "wait": 0, "greened": False,
                                        "t0": pt}
                self._armed[key] = False
                self.stats["entries"] += 1
                self._emit("entry", sel=sel, side="LAY", price=entry,
                           liability=round(self.stake * (entry - 1.0), 2))
                logger.info("[FLB] LAY favorito estremo sel=%s @%.2f (liab %.2f)",
                            sel, entry, self.stake * (entry - 1.0))

    def _confirm_green(self, sel: int, st: Dict[str, Any]) -> None:
        """Telemetria del green CONFERMATO: solo a hedge completamente matched."""
        st["green_locked"] = True
        self.stats["greens"] += 1
        self._emit("green", sel=sel, price=st.get("green_price"),
                   frac=st.get("green_fr"), locked=st.get("green_est"))
        logger.info("[FLB] GREEN matched sel=%s @%s frac=%s locked~%s",
                    sel, st.get("green_price"), st.get("green_fr"),
                    st.get("green_est"))

    def _manage(self, market: Any, sel: int, key: Tuple[str, int],
                st: Dict[str, Any], bb: float, bl: float,
                pt: Optional[int] = None) -> None:
        b, ba, l, la = self._matched(market, sel)
        if (b + l) <= _EPS:
            # entry LAY non ancora riempita: timeout in SECONDI di publish_time
            # (fallback al conteggio update SOLO se il publish_time manca).
            st["wait"] = int(st.get("wait", 0)) + 1
            t0 = st.get("t0")
            timed_out = (
                pt is not None and t0 is not None
                and (pt - t0) / 1000.0 >= self.entry_timeout
            ) or ((pt is None or t0 is None) and st["wait"] > self.entry_timeout)
            if timed_out:
                self._cancel(market, st.get("order"))
                self._pos_state[key] = {"state": DONE}
                self._emit("entry_timeout", sel=sel)
            return

        # --- sorveglianza dell'HEDGE di green (fix 2026-07-10: prima non era
        # tracciato: greened=True fisso anche con hedge lapsed = scoperti) ---
        if st.get("greened") and not st.get("green_locked"):
            go = st.get("green_order")
            if go is None:
                # dry-run o posizione gia' pari: nulla da sorvegliare
                self._confirm_green(sel, st)
                if self.exit_mode == "green":
                    self._pos_state[key] = {"state": DONE}
                return
            rem = float(getattr(go, "size_remaining", 0.0) or 0.0)
            if rem <= _EPS:
                # hedge completamente matched → il locked e' REALE
                self._confirm_green(sel, st)
                if self.exit_mode == "green":
                    self._pos_state[key] = {"state": DONE}
            elif not self._order_alive(go):
                # hedge MORTO (lapsed/cancelled/violation) con residuo: si
                # ripiazza la size residua al touch corrente — best-effort,
                # al piu' UN retry per book update.
                gside = (getattr(go, "side", "") or "").upper() or "BACK"
                px = bb if gside == "BACK" else bl
                o2 = self._place(market, sel, gside, get_nearest_price(px), rem)
                if o2 is not None:
                    st["green_order"] = o2
                    self._emit("green_replaced", sel=sel, side=gside,
                               size=round(rem, 2), price=px)
            return

        entry = st["entry"]
        # green-up sullo swing: la quota (best-back per chiudere un lay) e' RISALITA
        up = ticks_between(entry, bb) if bb > entry else 0
        if self.exit_mode in ("green", "hybrid") and not st["greened"] \
                and up and up >= self.green_ticks:
            frac = 1.0 if self.exit_mode == "green" else self.green_frac
            locked, go = self._green(market, sel, bb, frac)
            st["greened"] = True
            st["green_order"] = go
            st["green_locked"] = False
            st["green_price"] = bb
            st["green_fr"] = frac
            st["green_est"] = round(float(locked), 3)
            # telemetria di PIAZZAMENTO: il "green" vero arriva a hedge matched
            self._emit("green_placed", sel=sel, price=bb, frac=frac,
                       locked_est=round(float(locked), 3))
            logger.info("[FLB] GREEN piazzato sel=%s @%.2f frac=%.1f locked~%.3f",
                        sel, bb, frac, locked)
            # ENTRAMBE le modalita' (fix 2026-07-09): il resto INEVASO dell'entry
            # LAY va cancellato — un fill successivo riaprirebbe esposizione
            # oltre la frazione dichiarata. In "green" lo stato passa a DONE
            # SOLO quando l'hedge risulta matched (vedi sorveglianza sopra).
            self._cancel(market, st.get("order"))
        # "hold" / residuo hybrid: nessuno stop, si tiene fino alla chiusura mercato

    def process_closed_market(self, market: Any, mb: Any) -> None:
        # P&L VERO: profitto del settlement simulato (include hold-to-end).
        try:
            for o in market.blotter.strategy_orders(self):
                sim = getattr(o, "simulated", None)
                self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass
        self.stats["pnl"] = round(self.settled_pnl, 3)
