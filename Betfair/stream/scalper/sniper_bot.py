"""SNIPER del tick in-play (Under O/U): porting di produzione del prototipo
validato in backtest l'11/07/2026 (config S16, harness flumine certificato:
+0.99 netti/14 eventi, 4 ev+ / 1 ev-, worst -0.49, posizione mediana ~114s).
Vedi BIBBIA_SCALPER_CALCIO.md §6.

FILOSOFIA: un solo tick per partita, esposizione minima. Il bot e' armato
tutta la partita ma spara SOLO quando il book dell'Under dice che il prossimo
tick-down e' imminente:
  GATE 1 (regime):  >= cadence_n tick-down del best-back negli ultimi
                    cadence_window_s, l'ultimo entro last_dn_max_s;
  GATE 2 (innesco): size al best-back <= queue_frac x massimo visto al
                    livello corrente (il livello sta per rompersi);
  GATE 3 (costo):   spread <= max_spread_ticks -> ingresso TAKER.
Uscita: close a entry-target_ticks; stop a stop_ticks avversi; TIMEOUT
max_pos_s -> flatten immediato; PRIMO verde -> evento chiuso; loss cap
evento -> stop + flatten. In sospensione (gol) gli ordini LAPSE cadono e la
posizione si gestisce alla riapertura via flatten.

MAI maker resting a lungo sull'Under in-play (fill dentro il gap del gol =
lotteria, misurato — bibbia §6.1/§9).

dry_run=True (default della sessione = DEMO): nessun ordine reale, ogni
trigger viene emesso via event_sink come ``sniper_dry_fire`` con il contesto
del book — la UI mostra QUANDO e A QUALE prezzo avrebbe sparato.
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

from .scalper_bot import compute_green, ticks_between

logger = logging.getLogger(__name__)
_EPS = 1e-9
MIN_STAKE = 2.0


@dataclass
class _Pos:
    """Posizione per (market_id, selection_id) — un ciclo alla volta."""

    entries: List[Any] = field(default_factory=list)
    close: Optional[Any] = None
    flatten_orders: List[Any] = field(default_factory=list)
    flattening: bool = False
    flat_tries: int = 0
    done: bool = False
    entry_odds: Optional[float] = None
    close_locked: float = 0.0
    entry_fill_pt: Optional[float] = None
    # sequenze park-trim-replace (uscite a size ESATTA su .it) — identico
    # al meccanismo di produzione dello scalper (_place_exact/_drive_submins)
    submins: List[dict] = field(default_factory=list)
    t_last_submin: int = 0
    submin_count: int = 0
    residual_accepted: float = 0.0   # entita' |nw-nl| del residuo accettato


class SniperStrategy(BaseStrategy):
    """Un tick sull'Under, al momento giusto, poi fuori. Config default = S16."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx = dict(kwargs.pop("sniper_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx}

        # ---- mercati / direzione ----
        # Linea target DINAMICA in live: Under (gol totali + 1).5 — a 0-0 e'
        # OVER_UNDER_15 (come nel backtest S16), dopo un gol si sposta. La
        # sessione la aggiorna via set_line() dal feed punteggi (pattern del
        # controllo esterno ht_active dello scalper).
        self.lines = set(c.get("lines", ["OVER_UNDER_15"]))
        self.stake: float = max(MIN_STAKE, float(c.get("stake", 10.0)))
        self.price_min: float = float(c.get("price_min", 1.20))
        self.price_max: float = float(c.get("price_max", 1000.0))
        self.min_size: float = float(c.get("min_size", 50.0))
        # ---- ciclo (S16) ----
        self.target_ticks: int = max(1, int(c.get("target_ticks", 1)))
        self.stop_ticks: int = max(1, int(c.get("stop_ticks", 2)))
        self.max_pos_s: float = float(c.get("max_pos_s", 300.0))
        # ---- gate di precisione (S16) ----
        self.use_cadence: bool = bool(c.get("use_cadence", True))
        self.cadence_n: int = int(c.get("cadence_n", 2))
        self.cadence_window_s: float = float(c.get("cadence_window_s", 240.0))
        self.last_dn_max_s: float = float(c.get("last_dn_max_s", 90.0))
        self.use_queue: bool = bool(c.get("use_queue", True))
        self.queue_frac: float = float(c.get("queue_frac", 0.35))
        self.queue_floor_eur: float = float(c.get("queue_floor_eur", 60.0))
        self.max_spread_ticks: int = int(c.get("max_spread_ticks", 1))
        # ---- finestra in-play (tutta la partita; il gate sceglie) ----
        self.inplay_from_s: float = float(c.get("inplay_from_s", 60.0))
        self.inplay_to_s: float = float(c.get("inplay_to_s", 6600.0))
        # ---- missione / protezioni evento ----
        # primo verde -> evento chiuso (il "1 tick in-play")
        self.profit_target: float = float(c.get("profit_target", 0.01))
        # ---- MULTI-COLPO (F4b, 11/07): layer SOPRA la S16 validata — i gate
        # non cambiano. Default = comportamento attuale (nessun cap extra,
        # nessun cooldown): la cella multi-colpo si accende via parametri
        # (profit_target alzato/0 + max_shots + cooldown) SOLO dopo i numeri
        # del conteggio occasioni (registro ipotesi §11).
        self.max_shots: int = max(0, int(c.get("max_shots", 0)))       # 0 = no cap
        self.shot_cooldown_s: float = float(c.get("shot_cooldown_s", 0.0))
        self._last_cycle_end_ms: float = 0.0
        # ---- MULTI-LINEA (F4a, 11/07): N linee OU parallele sopra quella
        # dinamica (conteggio 10/07: multi-linea +1.28 EUR/partita vs +0.10
        # mono, fill 74% stop 5% — n=1, da falsificare out-of-sample).
        # 0 = solo linea dinamica (comportamento S16 certificato).
        self.parallel_lines: int = max(0, int(c.get("parallel_lines", 0)))
        self.event_loss_cap: float = float(c.get("event_loss_cap", 1.0))
        self.dry_run: bool = bool(c.get("dry_run", False))
        # ---- PROTEZIONI LIVE .it (0 = off, i backtest restano identici) ----
        # L'exchange .it RIFIUTA size non multiple di 0,50 (INVALID_BET_SIZE,
        # verificato 02/07) e sotto il minimo 2€: un'uscita rifiutata =
        # posizione nuda. Stessa semantica dello scalper: size arrotondata
        # al multiplo; uscite sotto il minimo → micro-residuo accettato se
        # piccolo, altrimenti arrotondate al minimo (micro over-hedge).
        self.size_step: float = float(c.get("size_step", 0.0))
        self.live_min_bet: float = float(c.get("live_min_bet", 0.0))
        # USCITE A SIZE ESATTA (tool-pro, come lo scalper): le uscite non
        # piazzabili direttamente (multipli 0,50/minimi .it) vengono SPEZZATE
        # in parte diretta + resto ESATTO via park-trim-replace → il profitto
        # del green resta spalmato al centesimo su entrambi gli esiti.
        self.exact_exits: bool = bool(c.get("exact_exits", False))
        self.force_flat: bool = False
        self._event_done: bool = False
        # clock REALE di partita (da live_now.minute, spinto dal watcher di
        # sessione). SOLO telemetria: i gate S16 validati restano su elapsed
        # KO (fix 11/07: marketTime conta l'HT → "min 81.9" al 59' reale).
        self.live_minute: Optional[float] = None
        # F5: semaforo di rischio UNICO per evento (condiviso col maker),
        # iniettato dalla sessione: momenti caldi = niente nuovi fire.
        self.risk_sem: Optional[Any] = None

        # stato
        self._pos: Dict[Tuple[str, int], _Pos] = {}
        self._settled_by_id: Dict[Any, Tuple[Any, str]] = {}
        self._ko_ms: Dict[str, Optional[float]] = {}
        # microstruttura per (market_id, selection_id)
        self._dn_ts: Dict[Tuple[str, int], Deque[float]] = {}
        self._prev_bb: Dict[Tuple[str, int], float] = {}
        self._level_max_sb: Dict[Tuple[str, int], float] = {}
        self._gate_ok: Dict[Tuple[str, int], bool] = {}
        self._dry_last_fire: Dict[Tuple[str, int], float] = {}

        self.stats: Dict[str, float] = {
            "orders": 0, "entries": 0, "greens": 0, "stops": 0,
            "timeouts": 0, "flattens": 0, "dry_fires": 0,
            "pnl_locked": 0.0, "pos_ms_total": 0.0, "cycles": 0,
            "ledger_divergences": 0,
        }

    # ------------------------------------------------------------------ util
    def _emit(self, kind: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, payload)
        except Exception:  # noqa: BLE001 - il sink non rompe mai il bot
            logger.debug("[sniper] event_sink errore su %s", kind, exc_info=True)

    @property
    def settled_orders(self):
        return list(self._settled_by_id.values())

    def set_line(self, market_type: Optional[str]) -> None:
        """Aggiorna la linea target dal feed punteggi (controllo esterno).

        F4a (fix 11/07 — CECITA' POST-GOL, difetto meccanico visto live il
        10/07): lo storico di microstruttura NON viene piu' azzerato. Le
        history sono per (market_id, selection_id) e con il tracking
        multi-linea (check_market_book accetta TUTTI gli OU) la nuova linea
        ha i gate GIA' CALDI al momento dello switch: prima il bot restava
        cieco ~4 minuti esattamente nella finestra post-gol.
        Le posizioni aperte su mercati usciti dalla whitelist restano
        GESTITE: check_market_book li accetta finche' non sono flat.
        """
        if not market_type:
            return
        mt = str(market_type)
        if self.lines == {mt}:
            return
        self.lines = {mt}
        self._emit("sniper_line", line=mt)

    def set_lines(self, market_types) -> None:
        """Whitelist di fuoco MULTI-LINEA (F4a): piu' canne in parallelo,
        stessi gate S16 per-linea. Il watcher di sessione la aggiorna dal
        punteggio: [dinamica, dinamica+1, ...] secondo ``parallel_lines``."""
        mts = {str(m) for m in market_types if m}
        if not mts or mts == self.lines:
            return
        self.lines = mts
        self._emit("sniper_lines", lines=sorted(mts))

    def _has_open_pos(self, market_id: str) -> bool:
        for (mid, _sid), pos in self._pos.items():
            if mid != market_id:
                continue
            if pos.flattening or pos.entries:
                return True
            for o in (*pos.entries, pos.close, *pos.flatten_orders):
                if self._has_live(o):
                    return True
        return False

    def is_flat(self) -> bool:
        """True se nessuna posizione/ordine vivo (per lo stop sicuro della sessione)."""
        for pos in self._pos.values():
            if pos.flattening or pos.submins:
                return False
            for o in (*pos.entries, pos.close, *pos.flatten_orders):
                if self._has_live(o):
                    return False
            sb, _ob, sl, _ol = self._matched(
                pos.entries + ([pos.close] if pos.close else [])
                + pos.flatten_orders)
            if abs(sb - sl) > 0.02:
                return False
        return True

    def _p(self, mid: str, sid: int) -> _Pos:
        key = (mid, int(sid))
        v = self._pos.get(key)
        if v is None:
            v = _Pos()
            self._pos[key] = v
        return v

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
        """Under = sort_priority 1 nei mercati OVER_UNDER_*."""
        md = getattr(mb, "market_definition", None)
        for rd in (getattr(md, "runners", None) or []):
            if int(getattr(rd, "selection_id", -1)) == int(runner.selection_id):
                return int(getattr(rd, "sort_priority", 0) or 0) == 1
        return False

    # -------------------------------------------------------------- flumine
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        if getattr(market_book, "status", None) != "OPEN":
            # F5: la sospensione in-play (gol) arma il semaforo condiviso
            from .risk_semaphore import notice_suspension
            notice_suspension(self.risk_sem, market_book)
            return False
        if not getattr(market_book, "runners", None):
            return False
        md = getattr(market_book, "market_definition", None)
        mtype = (getattr(md, "market_type", None)
                 or getattr(market, "market_type", None))
        if mtype in self.lines:
            return True
        # F4a (multi-linea a storico caldo): TUTTI i mercati OU sottoscritti
        # alimentano la microstruttura (il fuoco resta SOLO sulla linea
        # attiva, vedi process_market_book) e le posizioni residue su linee
        # uscite dalla whitelist restano gestite finche' non sono flat.
        return str(mtype or "").startswith("OVER_UNDER")

    # ------------------------------------------------------- microstruttura
    def _update_micro(self, key: Tuple[str, int], now: float,
                      bb: Optional[float], sb: Optional[float],
                      bl: Optional[float]) -> None:
        if bb is None:
            self._gate_ok[key] = False
            return
        prev = self._prev_bb.get(key)
        if prev is not None and bb < prev - _EPS:
            self._dn_ts.setdefault(key, deque(maxlen=16)).append(now)
            self._level_max_sb[key] = float(sb or 0.0)
        elif prev is not None and bb > prev + _EPS:
            self._level_max_sb[key] = float(sb or 0.0)
        elif sb is not None:
            self._level_max_sb[key] = max(
                self._level_max_sb.get(key, 0.0), float(sb))
        self._prev_bb[key] = bb

        ok = True
        if self.use_cadence:
            dns = self._dn_ts.get(key) or ()
            recent = [t for t in dns
                      if now - t <= self.cadence_window_s * 1000.0]
            ok = (len(recent) >= self.cadence_n
                  and bool(recent)
                  and (now - recent[-1]) <= self.last_dn_max_s * 1000.0)
        if ok and self.use_queue:
            mx = self._level_max_sb.get(key, 0.0)
            ok = (mx >= self.queue_floor_eur
                  and sb is not None and sb <= self.queue_frac * mx)
        if ok and self.max_spread_ticks > 0 and bb and bl:
            spr = ticks_between(bb, bl)
            ok = spr is not None and spr <= self.max_spread_ticks
        self._gate_ok[key] = ok

    # ------------------------------------------------------------- processo
    def process_market_book(self, market: Any, market_book: Any) -> None:
        now = getattr(market_book, "publish_time_epoch", None)
        if now is None:
            return
        mid = market_book.market_id
        # difesa in profondita': stesso filtro di check_market_book (flumine
        # lo chiama gia', ma il cambio linea puo' avvenire TRA i due hook)
        md = getattr(market_book, "market_definition", None)
        mtype = getattr(md, "market_type", None)
        # F4a: ogni OU tiene la microstruttura CALDA; spara solo la linea attiva
        if (mtype not in self.lines
                and not str(mtype or "").startswith("OVER_UNDER")
                and not self._has_open_pos(mid)):
            return
        active_line = mtype in self.lines
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
            key = (mid, int(runner.selection_id))
            self._update_micro(key, float(now), bb, sb, bl)
            pos = self._p(mid, int(runner.selection_id))
            # avanza le sequenze exact (park-trim-replace) PRIMA di tutto
            self._drive_submins(market, pos)

            # RICONCILIAZIONE LEDGER↔ORDINI (fix 11/07 — LA rete del bug
            # 21:43): posizione considerata CHIUSA/inattiva ma gli ordini
            # reali mostrano esposizione direzionale = posizione INVISIBILE
            # (il 10/07: ledger "+0.03 flat" contro conto short ~10€, chiuso
            # a mano dall'operatore). Auto-heal col flatten certificato +
            # CRITICAL; divergenze ripetute → FREEZE (force_flat).
            if not pos.entries and not pos.flattening and not pos.submins:
                sb0, ob0, sl0, ol0 = self._matched(pos.flatten_orders)
                nw0 = sb0 * (ob0 - 1.0) - sl0 * (ol0 - 1.0)
                nl0 = sl0 - sb0
                if abs(nw0 - nl0) > max(0.30, pos.residual_accepted + 0.02):
                    self.stats["ledger_divergences"] += 1
                    self._emit("ledger_divergence", level="CRITICAL",
                               nw=round(nw0, 2), nl=round(nl0, 2),
                               n=int(self.stats["ledger_divergences"]))
                    if (self.stats["ledger_divergences"] >= 3
                            and not self.force_flat):
                        self._emit("recon_freeze", level="CRITICAL",
                                   msg="divergenze ledger ripetute: FREEZE "
                                       "sessione sniper (force-flat)")
                        self.force_flat = True
                    self._begin_flatten(market, pos)
                    self._drive_flatten(market, pos, bb, bl, now)
                    continue

            if pos.done:
                continue

            out_window = not (inplay and el is not None
                              and self.inplay_from_s <= el <= self.inplay_to_s)
            has_pos = bool(pos.entries) or pos.flattening

            # TIMEOUT duro: il tick non arriva -> fuori subito
            if (pos.entries and not pos.flattening
                    and pos.entry_fill_pt is not None
                    and now - pos.entry_fill_pt > self.max_pos_s * 1000.0):
                self.stats["timeouts"] += 1
                self._emit("sniper_timeout",
                           pos_s=round((now - pos.entry_fill_pt) / 1000.0, 1))
                self._begin_flatten(market, pos)

            if (self.force_flat or out_window) and has_pos and not pos.flattening:
                self._begin_flatten(market, pos)
            if pos.flattening:
                self._drive_flatten(market, pos, bb, bl, now)
                continue

            if bb is None or bl is None:
                continue
            if not (self.price_min <= bb <= self.price_max):
                continue

            # ---- posizione aperta: stop / close / verde ----
            if pos.entries:
                filled = sum(float(getattr(o, "size_matched", 0.0) or 0.0)
                             for o in pos.entries)
                if filled > 0:
                    if pos.entry_fill_pt is None:
                        pos.entry_fill_pt = now
                    sb_m, ob, sl_m, ol = self._matched(pos.entries)
                    up = ticks_between(get_nearest_price(ob),
                                       get_nearest_price(bb)) \
                        if (ob and bb and bb > ob) else 0
                    if up is not None and up >= self.stop_ticks:
                        self.stats["stops"] += 1
                        self._emit("sniper_stop", up=up)
                        self._begin_flatten(market, pos)
                        continue
                    if pos.close is None and ob and ob > 1.0:
                        nw = sb_m * (ob - 1.0) - sl_m * (ol - 1.0)
                        nl = sl_m - sb_m
                        price = price_ticks_away(
                            get_nearest_price(ob), -self.target_ticks)
                        if price and price > 1.0:
                            g = compute_green(nw, nl, price)
                            if g is not None:
                                side, size, locked = g
                                o = self._place(market, runner.selection_id,
                                                side, price, size,
                                                floor=False, pos=pos)
                                if o is not None:
                                    pos.close = o
                                    pos.close_locked = locked
                    if (pos.close is not None and not self._has_live(pos.close)
                            and float(getattr(pos.close, "size_matched", 0.0)
                                      or 0.0) > 0):
                        locked = float(getattr(pos, "close_locked", 0.0))
                        self.stats["greens"] += 1
                        self.stats["pnl_locked"] += locked
                        self._close_cycle_clock(pos, now)
                        self._emit("sniper_green", locked=round(locked, 3),
                                   minute=self._minute(el))
                        for o_t in pos.entries:
                            self._track(pos, o_t)
                        self._track(pos, pos.close)
                        pos.entries = []
                        pos.close = None
                        pos.close_locked = 0.0
                        pos.entry_odds = None
                        if (self.profit_target > 0
                                and self.stats["pnl_locked"] >= self.profit_target):
                            self._event_done = True
                            self._emit("sniper_mission_done",
                                       pnl=round(self.stats["pnl_locked"], 3))
                continue

            # ---- nessuna posizione: si spara SOLO col gate verde ----
            # F4a: le linee NON attive alimentano lo storico e gestiscono i
            # residui, ma NON sparano mai.
            if not active_line:
                continue
            if (out_window or self._event_done or self.force_flat
                    or self._loss_capped()):
                continue
            if (sb or 0) < self.min_size or (sl or 0) < self.min_size:
                continue
            if not self._gate_ok.get(key, False):
                continue
            # F5: semaforo di rischio evento — momento caldo = niente fire
            if self.risk_sem is not None and self.risk_sem.entries_halted(now):
                continue
            # F4b multi-colpo: cap colpi/evento + cooldown dal fine-ciclo
            # (0 = disattivi, comportamento identico alla S16 certificata).
            if self.max_shots > 0 and self.stats["entries"] >= self.max_shots:
                continue
            if (self.shot_cooldown_s > 0 and self._last_cycle_end_ms > 0
                    and now - self._last_cycle_end_ms
                    < self.shot_cooldown_s * 1000.0):
                continue
            self._fire(market, runner, pos, bb, bl, sb, sl, el, now)

    # --------------------------------------------------------------- azioni
    def _loss_capped(self) -> bool:
        if self.event_loss_cap <= 0:
            return False
        if self.stats["pnl_locked"] <= -self.event_loss_cap:
            if not self._event_done:
                self._event_done = True
                self._emit("sniper_loss_cap",
                           pnl=round(self.stats["pnl_locked"], 3))
            return True
        return False

    def _fire(self, market: Any, runner: Any, pos: _Pos,
              bb: float, bl: float, sb: float, sl: float,
              el: Optional[float], now: float) -> None:
        """Ingresso TAKER al best back (il gate ha detto ADESSO)."""
        price = get_nearest_price(bb)
        if not price or price <= 1.0:
            return
        if self.dry_run:
            key = (market.market_id, int(runner.selection_id))
            # anti-spam: max un segnale ogni 120s per selezione
            if now - self._dry_last_fire.get(key, 0.0) < 120_000.0:
                return
            self._dry_last_fire[key] = now
            self.stats["dry_fires"] += 1
            self._emit("sniper_dry_fire", price=price, size=self.stake,
                       minute=self._minute(el),
                       best_back=bb, best_lay=bl, size_back=sb, size_lay=sl,
                       exit_price=price_ticks_away(price, -self.target_ticks))
            return
        o = self._place(market, runner.selection_id, "BACK", price, self.stake)
        if o is not None:
            pos.entries.append(o)
            pos.entry_odds = price
            self.stats["entries"] += 1
            self._emit("sniper_fire", price=price, size=self.stake,
                       minute=self._minute(el))

    def _minute(self, el: Optional[float]) -> Optional[float]:
        """Minuto per la TELEMETRIA: live_now.minute se disponibile (clock
        reale di partita), altrimenti fallback elapsed-KO/60."""
        if self.live_minute is not None:
            return round(float(self.live_minute), 1)
        return round(el / 60.0, 1) if el else None

    def _close_cycle_clock(self, pos: _Pos, now: Optional[float]) -> None:
        if pos.entry_fill_pt is not None and now is not None:
            self.stats["pos_ms_total"] += max(0.0, now - pos.entry_fill_pt)
            self.stats["cycles"] += 1
        if now is not None:
            self._last_cycle_end_ms = float(now)  # ancora del cooldown F4b
        pos.entry_fill_pt = None

    def _matched(self, orders) -> Tuple[float, float, float, float]:
        # dedup by-identity: lo stesso oggetto ordine conta UNA volta sola
        # (un duplicato raddoppierebbe il matched: money-critical).
        sb = sl = sbp = slp = 0.0
        seen: set = set()
        for o in orders:
            if o is None or id(o) in seen:
                continue
            seen.add(id(o))
            m = float(getattr(o, "size_matched", 0.0) or 0.0)
            if m <= 0:
                continue
            p = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if p <= 0:
                continue
            if (getattr(o, "side", "") or "").upper() == "BACK":
                sb += m
                sbp += p * m
            else:
                sl += m
                slp += p * m
        return sb, (sbp / sb if sb else 0.0), sl, (slp / sl if sl else 0.0)

    def _begin_flatten(self, market: Any, pos: _Pos) -> None:
        for o in pos.entries + ([pos.close] if pos.close else []):
            self._cancel_if_live(market, o)
        # _track (dedup by-identity): con l'auto-tracking di _place gli ordini
        # possono essere GIA' in flatten_orders — un duplicato raddoppierebbe
        # il matched in _matched (money-critical).
        for o in pos.entries:
            self._track(pos, o)
        if pos.close is not None:
            self._track(pos, pos.close)
        pos.entries = []
        pos.close = None
        pos.flattening = True
        pos.flat_tries = 0

    def _drive_flatten(self, market: Any, pos: _Pos,
                       bb: Optional[float], bl: Optional[float],
                       now: Optional[float]) -> None:
        """Chiude finche' non e' piatta (escalation, tolleranza 0.02)."""
        for o in pos.flatten_orders:
            if self._has_live(o):
                self._cancel_if_live(market, o)
        sb, ob, sl, ol = self._matched(pos.flatten_orders)
        nw = sb * (ob - 1.0) - sl * (ol - 1.0)
        nl = sl - sb
        if abs(nw - nl) <= 0.02:
            locked = min(nw, nl)
            pos.flattening = False
            pos.done = False  # riarmabile (salvo event_done)
            self.stats["flattens"] += 1
            self.stats["pnl_locked"] += locked
            self._close_cycle_clock(pos, now)
            self._emit("sniper_flat", locked=round(locked, 3))
            self._loss_capped()
            return
        if any(self._has_live(o) for o in pos.flatten_orders):
            return
        # micro-residuo ACCETTATO (come lo scalper, fix 11/07): nessun ordine
        # vivo, nessuna sequenza exact in corso e sbilancio piccolo → si
        # chiude contabilizzando il worst-case (evita l'inseguimento infinito
        # quando il residuo non e' piazzabile sull'exchange)
        if not pos.submins and abs(nw - nl) <= 0.30:
            locked = min(nw, nl)
            pos.flattening = False
            pos.done = False
            pos.residual_accepted = abs(nw - nl)
            self.stats["flattens"] += 1
            self.stats["pnl_locked"] += locked
            self._close_cycle_clock(pos, now)
            self._emit("sniper_flat_residual", locked=round(locked, 3),
                       nw=round(nw, 3), nl=round(nl, 3))
            self._loss_capped()
            return
        if not pos.submins and pos.flat_tries > 12:
            # ULTIMA SPIAGGIA (direttiva operatore 10/07 §12.1: il flatten
            # TERMINA sempre, con ledger chiuso): niente e' piazzabile e
            # nessuna sequenza exact attiva dopo molti tentativi → il residuo
            # si ACCETTA e si CONTABILIZZA subito (worst-case), mai skip-loop.
            locked = min(nw, nl)
            pos.flattening = False
            pos.done = False
            pos.residual_accepted = abs(nw - nl)
            self.stats["flattens"] += 1
            self.stats["pnl_locked"] += locked
            self._close_cycle_clock(pos, now)
            self._emit("sniper_flat_forced", level="WARN",
                       locked=round(locked, 3),
                       nw=round(nw, 3), nl=round(nl, 3))
            self._loss_capped()
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
            o = self._place(market, self._sid(pos), side, price, size,
                            floor=False, pos=pos)
            if o is not None:
                self._track(pos, o)

    def _sid(self, pos: _Pos) -> int:
        for (mid, sid), p in self._pos.items():
            if p is pos:
                return int(sid)
        return -1

    # ---------------- esecuzione (semantica IDENTICA allo scalper live .it)
    @staticmethod
    def _side_min(side: str) -> float:
        """Minimo di piazzamento diretto per lato su .it (BACK 2 / LAY 0,50)."""
        return 2.0 if (side or "").upper() == "BACK" else 0.5

    def _size_direct_ok(self, side: str, size: float) -> bool:
        """True se la size e' piazzabile DIRETTAMENTE su .it (multiplo di
        0,50 e >= minimo del lato)."""
        if size < self._side_min(side) - _EPS:
            return False
        mult = size / 0.5
        return abs(mult - round(mult)) < 1e-6

    @staticmethod
    def _track(pos: _Pos, order: Any) -> None:
        """Aggiunge l'ordine alla contabilita' SENZA duplicati (un duplicato
        in flatten_orders raddoppierebbe il matched: money-critical)."""
        if order is None:
            return
        for o in pos.flatten_orders:
            if o is order:
                return
        pos.flatten_orders.append(order)

    def _place(self, market: Any, sid: int, side: str, price: float,
               size: float, floor: bool = True,
               pos: Optional[_Pos] = None) -> Optional[Any]:
        size = round(float(size), 2)
        if floor and size < MIN_STAKE:
            size = MIN_STAKE
        if size < 0.01 or float(price) <= 1.0:
            return None
        if self.dry_run:
            # le uscite in dry non esistono (niente posizioni in dry)
            return None
        # ---- USCITE A SIZE ESATTA (tool-pro): parte diretta + resto submin
        if (not floor and self.exact_exits and pos is not None
                and not self._size_direct_ok(side, size)):
            return self._place_exact(market, sid, side, price, size, pos)
        # granularita' exchange .it: multipli di 0,50 (size non multipla =
        # INVALID_BET_SIZE e la posizione RESTA APERTA)
        if self.size_step > 0:
            size = round(round(size / self.size_step) * self.size_step, 2)
            if size < self.size_step:
                size = 0.0
        # minimo del lato sugli hedge/close: sotto, l'exchange rifiuta →
        # meglio un micro over-hedge del residuo che una gamba aperta
        side_floor = self._side_min(side) if self.live_min_bet > 0 else 0.0
        if self.live_min_bet > 0 and not floor and size < side_floor:
            if size >= 0.25:
                import math as _m
                bumped = max(side_floor, round(_m.ceil(size / 0.5) * 0.5, 2))
                self._emit("min_bet_adjust", selection_id=int(sid), side=side,
                           size_orig=size, size=bumped)
                size = bumped
            else:
                self._emit("min_bet_skip", selection_id=int(sid), side=side,
                           size=size)
                return None
        if size < 0.01:
            return None
        self.stats["orders"] += 1
        tr = Trade(market_id=market.market_id, selection_id=int(sid),
                   handicap=0.0, strategy=self)
        o = tr.create_order(side=side, order_type=LimitOrder(
            price=float(price), size=size, persistence_type="LAPSE"))
        market.place_order(o)
        # ANTI-ORFANI (lezione live 10/07: exit rimasta viva 40+ min): ogni
        # ordine con una posizione nota entra in flatten_orders (dedup
        # by-identity) → il blanket-cancel del flatten lo copre SEMPRE.
        if pos is not None:
            self._track(pos, o)
        return o

    # ---- park-trim-replace (porting fedele da ScalperStrategy) ----
    _SUBMIN_MIN_INTERVAL_MS = 30_000
    _SUBMIN_MAX_PER_CYCLE = 5

    def _cancel_submins(self, market: Any, pos: _Pos) -> None:
        for entry in list(pos.submins):
            o = entry.get("order") or getattr(entry.get("ops"), "last_order", None)
            if o is not None:
                self._track(pos, o)
                self._cancel_if_live(market, o)
            pos.submins.remove(entry)

    def _place_exact(self, market: Any, sid: int, side: str, price: float,
                     size: float, pos: _Pos) -> Optional[Any]:
        """Uscita a QUALSIASI size: parte diretta (multipli 0,50) + resto
        ESATTO via park-trim-replace. Identico al percorso di produzione
        dello scalper (validato live: park legali 2,00 BACK@1000/LAY@1.01)."""
        from ..live_order_build import round_to_tick
        from ..trading.submin import FlumineSubminOps, SubminState, SubminStep

        smin = self._side_min(side)
        main = round(int(size / 0.5 + 1e-9) * 0.5, 2)
        if main < smin - _EPS:
            main = 0.0
        rest = round(size - main, 2)
        main_order = None
        if main >= smin - _EPS:
            # pos passato per il tracking anti-orfani; nessuna ricorsione:
            # main e' multiplo di 0,50 → _size_direct_ok=True → place diretto.
            main_order = self._place(market, sid, side, price, main,
                                     floor=False, pos=pos)
        if rest < 0.05:
            if rest >= 0.01:
                self._emit("min_bet_skip", selection_id=int(sid), side=side,
                           size=rest)
            return main_order

        import time as _t
        now_ms = int(_t.time() * 1000)
        rate_ok = now_ms - (pos.t_last_submin or 0) >= self._SUBMIN_MIN_INTERVAL_MS
        if pos.submin_count >= self._SUBMIN_MAX_PER_CYCLE:
            self._emit("min_bet_skip", selection_id=int(sid), side=side,
                       size=rest)
            return main_order
        if (pos.flattening and main_order is not None) or not rate_ok:
            self._emit("min_bet_skip", selection_id=int(sid), side=side,
                       size=rest)
            return main_order
        if pos.submins:
            for entry in pos.submins:
                st_old = entry.get("state")
                if (st_old is not None and st_old.side == side.lower()
                        and abs(st_old.target_size - rest) < 0.05
                        and abs(st_old.target_price - price) < 0.021):
                    return main_order  # sequenza equivalente gia' in corso
            self._cancel_submins(market, pos)
        try:
            state = SubminState(
                step=SubminStep.INIT, bet_id=None,
                target_size=round(rest, 2),
                target_price=round_to_tick(price),
                placed_size=2.0,          # park legale/universale (.it)
                side=side.lower(),
                note="exact exit",
            )

            class _CapturingOps(FlumineSubminOps):
                last_order: Any = None

                def place(self, market_, **kw):  # noqa: ANN001
                    o = super().place(market_, **kw)
                    _CapturingOps.last_order = o
                    return o

            ops = _CapturingOps(selection_id=int(sid), handicap=0.0,
                                jurisdiction="it", strategy=self)
            ref = f"sn{abs(hash((sid, price, rest, now_ms))) % 10**8:08d}"
            pos.submins.append({"state": state, "ops": ops, "order": None,
                                "ref": ref, "market_id": market.market_id})
            pos.t_last_submin = now_ms
            pos.submin_count += 1
            self._emit("submin_start", selection_id=int(sid), side=side,
                       size=rest, price=price)
        except Exception as exc:  # noqa: BLE001 - mai bloccare l'uscita
            self._emit("submin_error", msg=str(exc)[:200])
        return main_order

    def _drive_submins(self, market: Any, pos: _Pos) -> None:
        """Avanza le sequenze park-trim-replace (idempotente)."""
        if not pos.submins:
            return
        from ..trading.submin import SubminStep, advance_submin

        for entry in list(pos.submins):
            if entry.get("market_id") != market.market_id:
                continue
            order = entry.get("order")
            if order is None:
                order = getattr(entry["ops"], "last_order", None)
                if order is not None:
                    entry["order"] = order
                    self._track(pos, order)
            if order is not None:
                tr = getattr(order, "trade", None)
                t_orders = list(getattr(tr, "orders", None) or [])
                for o in t_orders:
                    self._track(pos, o)
                if t_orders:
                    entry["order"] = t_orders[-1]
            try:
                new_state = advance_submin(
                    market, entry["state"], order=entry.get("order"),
                    jurisdiction="it", customer_order_ref=entry["ref"],
                    ops=entry["ops"],
                )
            except Exception as exc:  # noqa: BLE001
                self._emit("submin_error", msg=str(exc)[:200])
                pos.submins.remove(entry)
                continue
            if entry.get("order") is None:
                o = getattr(entry["ops"], "last_order", None)
                if o is not None:
                    entry["order"] = o
                    self._track(pos, o)
            if new_state.step is not entry["state"].step:
                self._emit("submin_step", step=str(new_state.step.value),
                           note=new_state.note[:120])
            entry["state"] = new_state
            if new_state.step == SubminStep.DONE:
                pos.submins.remove(entry)
            elif new_state.step == SubminStep.ABORTED:
                o_ab = entry.get("order")
                matched = float(getattr(o_ab, "size_matched", 0.0) or 0.0) \
                    if o_ab is not None else 0.0
                self._emit("submin_abort", note=new_state.note[:200],
                           matched=round(matched, 2))
                pos.submins.remove(entry)
                # COMPENSAZIONE IMMEDIATA (bug live 10/07 21:43): park abbinato
                # = posizione reale non prevista → flatten certificato SUBITO
                # (l'ordine e' gia' tracciato in flatten_orders).
                if matched > 0.02 and not pos.flattening:
                    self._emit("submin_abort_matched", level="CRITICAL",
                               matched=round(matched, 2))
                    self._begin_flatten(market, pos)

    @staticmethod
    def _has_live(o: Any) -> bool:
        if o is None:
            return False
        if getattr(o, "status", None) not in (OrderStatus.EXECUTABLE,
                                              OrderStatus.PENDING):
            return False
        return float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS

    @staticmethod
    def _cancel_if_live(market: Any, o: Any) -> None:
        if o is None:
            return
        if getattr(o, "status", None) in (OrderStatus.EXECUTABLE,
                                          OrderStatus.PENDING):
            if float(getattr(o, "size_remaining", 0.0) or 0.0) > _EPS:
                try:
                    market.cancel_order(o)
                except Exception:  # noqa: BLE001
                    logger.debug("[sniper] cancel fallita", exc_info=True)

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
