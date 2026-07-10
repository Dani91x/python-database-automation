"""TennisLabStrategy — motore configurabile per lo SWEEP MASSIVO (centinaia di combo).

Un'unica strategia parametrica che copre le famiglie direzionali fondate su
edge reali del tennis-trading, con:
  - DELAY in-play modellato a livello strategia (l'ordine diventa vivo
    ``bet_delay_ms`` dopo la decisione: 3s in-play, 0 pre-match) — perche' il
    backtest puro di flumine NON applica il bet delay (solo la coda/PIQ).
  - CODA rispettata dall'harness (simulation_available_prices=False + PIQ flumine).
  - MOTORE DI USCITA con BLINDATURA del profitto: hold | green | lock_trail
    (blocca il profitto appena supera ``lock_profit`` e trascina uno stop che
    concede al massimo ``trail_give_back``).

Famiglie (archetipi direzionali):
  - lay favorito estremo (favourite-longshot bias)               [FLB, validato +]
  - back favorito (continuazione/trend del quasi-certo)
  - lay sfavorito (fade dell'over-reaction sull'underdog)
  - back sfavorito (value/momentum sul ribattitore)

Price-driven (niente nomi/score → niente quella classe di bug). Lo strato
score-condizionato arriva in un secondo modulo (usa il feed score sincronizzato).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.trade import Trade
from flumine.order.ordertype import LimitOrder
from flumine.utils import get_price, get_size, get_nearest_price, price_ticks_away

from .tennis_scalper_bot import compute_green, ticks_between

logger = logging.getLogger(__name__)
MIN_STAKE = 2.0
_EPS = 1e-9
IDLE, OPEN, DONE = "IDLE", "OPEN", "DONE"


class TennisLabStrategy(BaseStrategy):
    """Entrata direzionale configurabile + delay + motore di uscita blindante."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        c: Dict[str, Any] = dict(kwargs.pop("lab_params", {}) or {})
        super().__init__(*args, **kwargs)

        self.stake: float = max(MIN_STAKE, float(c.get("stake", 2.0)))
        # direzione: side su target
        self.side: str = str(c.get("side", "lay")).upper()          # LAY|BACK
        self.target: str = str(c.get("target", "favorite")).lower()  # favorite|underdog
        # banda prezzo di ingresso sul runner target
        self.price_min: float = float(c.get("price_min", 1.01))
        self.price_max: float = float(c.get("price_max", 1.10))
        # gate in-play
        self.gate: str = str(c.get("gate", "inplay")).lower()        # inplay|prematch|any
        # esecuzione
        self.maker: bool = bool(c.get("maker", True))
        # liquidita'
        self.min_matched: float = float(c.get("min_matched", 10_000.0))
        self.min_size: float = float(c.get("min_size", 5.0))
        # delay in-play (ms). None => usa il betDelay del mercato (3s tennis)
        self.bet_delay_ms: Optional[int] = (
            None if c.get("bet_delay_ms", "auto") == "auto"
            else int(c.get("bet_delay_ms")))
        # ri-arma quando il prezzo riesce dalla banda
        self.rearm_mult: float = float(c.get("rearm_mult", 1.10))
        self.entry_timeout: int = int(c.get("entry_timeout", 40))
        # uscita: hold | green | lock_trail
        self.exit_mode: str = str(c.get("exit_mode", "hold")).lower()
        self.green_ticks: int = int(c.get("green_ticks", 8))
        self.green_frac: float = float(c.get("green_frac", 1.0))
        self.lock_profit: float = float(c.get("lock_profit", 0.5))    # £ soglia blindatura
        self.trail_give_back: float = float(c.get("trail_give_back", 0.15))  # £ max concesso
        self.stop_ticks: int = int(c.get("stop_ticks", 0))            # 0 = no stop
        # PIRAMIDE / averaging-down: se la posizione va CONTRO di N tick, aggiunge
        # un'unita' (abbassando la quota media), fino a max_units, cap esposizione.
        self.pyramid: bool = bool(c.get("pyramid", False))
        self.add_spacing_ticks: int = int(c.get("add_spacing_ticks", 3))
        self.max_units: int = int(c.get("max_units", 1))
        self.dry_run: bool = bool(c.get("dry_run", False))

        # stato
        self._state: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._armed: Dict[Tuple[str, int], bool] = {}
        self._pending: Dict[Tuple[str, int], Dict[str, Any]] = {}  # intent in attesa (delay)
        self.stats: Dict[str, Any] = {"entries": 0, "greens": 0, "locks": 0,
                                      "stops": 0, "adds": 0}
        self.settled_pnl: float = 0.0
        # locked = P&L GARANTITO (min sui due esiti) = edge result-INDIPENDENTE.
        # settled_pnl dipende da chi ha vinto (puo' essere fortuna); locked no.
        self.locked_floor: float = 0.0
        self.score: Any = None  # popolato dallo strato score-condizionato (fase 2)

    def _entry_allowed(self, mb: Any, sel: int) -> bool:
        """Hook di gate sull'ingresso. Base = sempre True (price-driven).
        Lo strato score-condizionato lo sovrascrive per filtrare sullo stato di gioco."""
        return True

    def check_market_book(self, market: Any, mb: Any) -> bool:
        return getattr(mb, "status", None) == "OPEN" and bool(getattr(mb, "runners", None))

    # ---------------------------------------------------- posizione matchata
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

    def _lockable(self, market: Any, sel: int, close_price: float) -> float:
        """Profitto blindabile ORA (green-up) alla quota di chiusura."""
        b, ba, l, la = self._matched(market, sel)
        if (b + l) <= _EPS:
            return 0.0
        nw, nl = self._net(b, ba, l, la)
        g = compute_green(nw, nl, close_price)
        return float(g[2]) if g else min(nw, nl)

    def _place(self, market: Any, sel: int, side: str, price: float,
               size: float) -> Optional[Any]:
        size = round(max(0.0, float(size)), 2)
        if price is None or price <= 1.0 or size < 0.01 or self.dry_run:
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

    def _cancel_entry_orders(self, market: Any, st: Dict[str, Any]) -> None:
        """Cancella entry + ordini della PIRAMIDE (adds) ancora vivi.

        Fix 2026-07-10: gli add non venivano salvati né cancellati a
        stop/green/lock_trail — un add inevaso poteva riempirsi DOPO la
        chiusura riaprendo esposizione direzionale non gestita.
        """
        self._cancel(market, st.get("order"))
        for o in st.get("adds") or []:
            self._cancel(market, o)

    def _green(self, market: Any, sel: int, price: float, frac: float) -> Optional[float]:
        b, ba, l, la = self._matched(market, sel)
        nw, nl = self._net(b, ba, l, la)
        g = compute_green(nw, nl, price)
        if g is None:
            return None
        gside, gsize, locked = g
        self._place(market, sel, gside, get_nearest_price(price), gsize * frac)
        self.stats["realized"] = self.stats.get("realized", 0.0) + float(locked) * frac
        return float(locked)

    # --------------------------------------------------- selezione target
    def _pick_target(self, mb: Any) -> Optional[Tuple[int, Any]]:
        """Ritorna (selection_id, runner) del favorito o sfavorito per best-back."""
        best: Optional[Tuple[float, int, Any]] = None
        for r in mb.runners:
            if getattr(r, "status", None) != "ACTIVE":
                continue
            ex = getattr(r, "ex", None)
            if ex is None:
                continue
            bb = get_price(ex.available_to_back, 0)
            if not bb:
                continue
            key = bb
            if best is None:
                best = (key, int(r.selection_id), r)
            elif (self.target == "favorite" and key < best[0]) or \
                 (self.target == "underdog" and key > best[0]):
                best = (key, int(r.selection_id), r)
        if best is None:
            return None
        return best[1], best[2]

    def _delay_ms(self, mb: Any) -> int:
        if not bool(getattr(mb, "inplay", False)):
            return 0
        if self.bet_delay_ms is not None:
            return int(self.bet_delay_ms)
        bd = getattr(mb, "bet_delay", None)
        if bd is None:
            md = getattr(mb, "market_definition", None)
            bd = getattr(md, "bet_delay", None)
        return int((bd or 3)) * 1000

    # --------------------------------------------------------- main loop
    def process_market_book(self, market: Any, mb: Any) -> None:
        if float(getattr(mb, "total_matched", 0.0) or 0.0) < self.min_matched:
            return
        inplay = bool(getattr(mb, "inplay", False))
        if self.gate == "inplay" and not inplay:
            return
        if self.gate == "prematch" and inplay:
            return
        pt = int(getattr(mb, "publish_time_epoch", 0) or 0)
        pick = self._pick_target(mb)
        if pick is None:
            return
        sel, r = pick
        ex = r.ex
        mid = mb.market_id
        key = (mid, sel)

        # 1) intent in attesa del delay -> quando scade, piazza davvero
        pend = self._pending.get(key)
        if pend is not None:
            if pt >= pend["activate"]:
                price = self._entry_price(ex)
                if price is not None:
                    o = self._place(market, sel, self.side, price, self.stake)
                    self._state[key] = {"state": OPEN, "entry": price, "order": o,
                                        "wait": 0, "greened": False, "peak": 0.0,
                                        "locked_armed": False, "units": 1,
                                        "last_add": price, "adds": []}
                    self.stats["entries"] += 1
                self._pending.pop(key, None)
            return

        st = self._state.get(key)
        if st and st["state"] == OPEN:
            self._manage(market, sel, key, st, ex, mb)
            return
        if st and st["state"] == DONE:
            # ri-arma quando il prezzo riesce dalla banda
            trig = self._trigger_price(ex)
            if trig is not None and not self._in_band(trig):
                self._state.pop(key, None)
                self._armed[key] = True
            return

        # 2) trigger di ingresso: prezzo del target nella banda
        trig = self._trigger_price(ex)
        if trig is None or not self._in_band(trig):
            return
        if (self._trigger_size(ex) or 0) < self.min_size:
            return
        if not self._entry_allowed(mb, sel):
            return
        # crea l'intent con delay (in-play) — l'ordine sara' vivo dopo bet_delay
        self._pending[key] = {"activate": pt + self._delay_ms(mb)}

    def _entry_price(self, ex: Any) -> Optional[float]:
        """Prezzo a cui piazzare: maker=rest al best del proprio lato; taker=cross."""
        if self.side == "LAY":
            p = get_price(ex.available_to_lay, 0) if self.maker \
                else get_price(ex.available_to_back, 0)
        else:
            p = get_price(ex.available_to_back, 0) if self.maker \
                else get_price(ex.available_to_lay, 0)
        return get_nearest_price(p) if p else None

    def _trigger_price(self, ex: Any) -> Optional[float]:
        """Prezzo di riferimento per il trigger (best-lay se layiamo, best-back se backiamo)."""
        if self.side == "LAY":
            return get_price(ex.available_to_lay, 0)
        return get_price(ex.available_to_back, 0)

    def _trigger_size(self, ex: Any) -> Optional[float]:
        if self.side == "LAY":
            return get_size(ex.available_to_lay, 0)
        return get_size(ex.available_to_back, 0)

    def _in_band(self, price: float) -> bool:
        return self.price_min <= price <= self.price_max

    @staticmethod
    def _ticks(a: float, b: float) -> int:
        """Distanza in tick tra due quote (ordine-agnostica; 0 se non valida).

        ``ticks_between`` vuole (basso, alto) e torna None se invertiti: qui
        passiamo sempre (min, max) per non perdere mai gli scostamenti avversi."""
        if not a or not b:
            return 0
        n = ticks_between(min(a, b), max(a, b))
        return int(n) if n is not None else 0

    # --------------------------------------------------------- gestione uscita
    def _manage(self, market: Any, sel: int, key: Tuple[str, int],
                st: Dict[str, Any], ex: Any, mb: Any) -> None:
        b, ba, l, la = self._matched(market, sel)
        if (b + l) <= _EPS:
            st["wait"] += 1
            if st["wait"] > self.entry_timeout:
                self._cancel_entry_orders(market, st)
                self._state[key] = {"state": DONE}
            return

        entry = st["entry"]
        # quota per chiudere: se abbiamo layato chiudiamo backando (best-back); viceversa
        close_price = get_price(ex.available_to_back, 0) if self.side == "LAY" \
            else get_price(ex.available_to_lay, 0)
        if not close_price:
            return

        # --- PIRAMIDE / averaging-down: aggiungi se va CONTRO, abbassa la media ---
        if self.pyramid and st.get("units", 1) < self.max_units:
            add_price = self._entry_price(ex)  # best del proprio lato (maker/taker come entry)
            last = st.get("last_add", entry)
            # avverso per un LAY = quota SCESA; per un BACK = quota SALITA
            adverse = (self.side == "LAY" and add_price and add_price < last) or \
                      (self.side == "BACK" and add_price and add_price > last)
            if adverse and self._ticks(last, add_price) >= self.add_spacing_ticks:
                add_o = self._place(market, sel, self.side, add_price, self.stake)
                if add_o is not None:
                    # tracciato: va cancellato in OGNI percorso di uscita
                    st.setdefault("adds", []).append(add_o)
                st["units"] = st.get("units", 1) + 1
                st["last_add"] = add_price
                self.stats["adds"] += 1

        # --- hard stop (opzionale, per trend/fade) ---
        if self.stop_ticks > 0:
            adverse = self._ticks(entry, close_price) if (
                (self.side == "LAY" and close_price < entry) or
                (self.side == "BACK" and close_price > entry)) else 0
            if adverse and adverse >= self.stop_ticks:
                self._green(market, sel, close_price, 1.0)
                self.stats["stops"] += 1
                self._cancel_entry_orders(market, st)
                self._state[key] = {"state": DONE}
                return

        # --- green fisso allo swing favorevole ---
        if self.exit_mode == "green" and not st["greened"]:
            up = self._ticks(entry, close_price) if (
                (self.side == "LAY" and close_price > entry) or
                (self.side == "BACK" and close_price < entry)) else 0
            if up and up >= self.green_ticks:
                self._green(market, sel, close_price, 1.0)
                st["greened"] = True
                self.stats["greens"] += 1
                self._cancel_entry_orders(market, st)
                self._state[key] = {"state": DONE}
                return

        # --- lock_trail: blinda il profitto e trascina lo stop ---
        if self.exit_mode == "lock_trail":
            lockable = self._lockable(market, sel, close_price)
            st["peak"] = max(st["peak"], lockable)
            if not st["locked_armed"] and lockable >= self.lock_profit:
                st["locked_armed"] = True  # profitto blindabile raggiunto
                self.stats["locks"] += 1
            if st["locked_armed"] and (st["peak"] - lockable) >= self.trail_give_back:
                # ritraccia oltre il give-back -> chiudi e incassa
                self._green(market, sel, close_price, 1.0)
                self._cancel_entry_orders(market, st)
                self._state[key] = {"state": DONE}
                return
        # "hold" / residuo: nessuna azione, tiene fino al settlement

    def process_closed_market(self, market: Any, mb: Any) -> None:
        try:
            orders = list(market.blotter.strategy_orders(self))
        except Exception:  # noqa: BLE001
            orders = []
        for o in orders:
            sim = getattr(o, "simulated", None)
            self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        # locked floor = min del P&L sui due esiti possibili (result-INDIP).
        try:
            self.locked_floor += self._locked_from_orders(orders, mb)
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _locked_from_orders(orders: Any, mb: Any) -> float:
        """P&L GARANTITO: min sul possibile vincitore. Per un mercato a 2 runner
        misura l'edge indipendente dal risultato (una cattura verde vera ha
        locked>0; una gamba direzionale ha locked = -liability)."""
        outcomes = [int(getattr(r, "selection_id", 0) or 0)
                    for r in (getattr(mb, "runners", None) or [])]
        if not outcomes:
            outcomes = list({int(getattr(o, "selection_id", 0) or 0) for o in orders})
        if not outcomes:
            return 0.0
        pos = []
        for o in orders:
            sm = float(getattr(o, "size_matched", 0.0) or 0.0)
            ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if sm <= _EPS or ap <= 0:
                continue
            pos.append((int(getattr(o, "selection_id", 0) or 0),
                        (getattr(o, "side", "") or "").upper(), sm, ap))
        if not pos:
            return 0.0
        best = None
        for winner in outcomes:
            pnl = 0.0
            for sel, side, sm, ap in pos:
                won = (sel == winner)
                if side == "BACK":
                    pnl += sm * (ap - 1.0) if won else -sm
                else:  # LAY
                    pnl += -sm * (ap - 1.0) if won else sm
            best = pnl if best is None else min(best, pnl)
        return float(best or 0.0)
