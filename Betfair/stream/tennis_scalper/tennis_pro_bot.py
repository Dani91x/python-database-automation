"""TennisProStrategy — bot tennis best-practice, GUIDATO DAL PUNTEGGIO.

Implementa i setup che i trader/professionisti documentati usano davvero, sopra
un'infrastruttura di esecuzione provata. NON e' un maker cieco (quello, misurato,
fa ~zero e viene spellato dai courtsider).

SETUP IMPLEMENTATI (ognuno con fonte reale):
  1. BREAK POINT (0-40/15-40) — direzione per SUPERFICIE:
       erba/fast -> BACK chi serve (tiene, fade dello spike);
       clay/wta  -> BACK chi riceve (break probabile).                [botblog/JuiceStorm 15-40]
  2. FADE OVER-REACTION — back del favorito dopo un break PRECOCE che
     ne ha gonfiato la quota.                                          [Traderline/Pinnacle]
  3. SERVING FOR THE SET — LAY chi serve per il set (5-x, lead>=1): puo'
     fallire di servire il set -> pop.                                 [Daniel Temple]
  4. DOUBLE BREAK — LAY chi conduce di 2 break (lead game >=3): vantaggio
     fragile, rientro probabile.                                       [Daniel Temple]
  5. SET TRANSITION — nei primi game del set nuovo, LAY chi ha appena
     vinto il set (sovra-reazione).                                    [Traderline]
  6. COMPRESSED FAVOURITE — LAY il favorito cortissimo per il wobble
     (liability bassa, upside sul rientro).                            [Beating Betting/Bet Angel]

Tutti con: GATE liquidita' (mai challenger/ITF), GESTIONE A SCAGLIONI (-40% a
meta' strada), STOP asimmetrico, uscita strutturale (chiude alla risoluzione del
game). Riusa ``compute_green`` (green-up bit-identico) e la ladder ufficiale
flumine (tick perfetti a ogni soglia).

⚠️ Aspettativa ONESTA: il mercato in-play e' efficiente; questi edge sono piccoli
e in parte decaduti. E' il MIGLIOR bot possibile con le pratiche dei pro, non una
macchina dei soldi. Il backtest sincronizzato + il paper decidono coi numeri.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.trade import Trade
from flumine.order.ordertype import LimitOrder
from flumine.utils import get_price, get_size, price_ticks_away, get_nearest_price

from .tennis_scalper_bot import compute_green, ticks_between
from .tennis_score import TennisScore

logger = logging.getLogger(__name__)

MIN_STAKE = 2.0
_EPS = 1e-9

# CLOSING (fix audit #7): dopo il green/stop finale la posizione va SORVEGLIATA
# finche' il blotter non e' pari — mai un FLAT dichiarato col solo hedge piazzato.
FLAT, OPEN, CLOSING, DONE = "FLAT", "OPEN", "CLOSING", "DONE"


def _norm(name: Optional[str]) -> str:
    return " ".join(str(name or "").strip().lower().split())


def _point_rank(p: Any) -> Optional[int]:
    m = {"0": 0, "15": 1, "30": 2, "40": 3, "A": 4, "AD": 4, "ADV": 4}
    if p is None:
        return None
    s = str(p).strip().upper()
    if s in m:
        return m[s]
    if s.isdigit():
        return int(s)
    return None


class TennisProStrategy(BaseStrategy):
    """Strategia direzionale multi-setup ancorata al punteggio (best-practice)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ctx_in: Dict[str, Any] = dict(kwargs.pop("pro_params", {}) or {})
        self.event_sink = kwargs.pop("event_sink", None)
        # mappa nome->selection: i nomi del CATALOGO Betfair ("Ar Fery") e quelli
        # dell'IPS ("Arthur Fery") NON combaciano -> si indicizza anche per COGNOME
        # (ultimo token) cosi' il match e' robusto.
        _raw = {_norm(k): int(v) for k, v in dict(kwargs.pop("name_to_sel", {})).items()}
        self.name_to_sel: Dict[str, int] = dict(_raw)
        # fix audit #13: se i due runner CONDIVIDONO il cognome (sorelle/fratelli,
        # doppi omonimi) il cognome e' AMBIGUO e NON va indicizzato — un match
        # sbagliato scambierebbe server/receiver (direzione del trade invertita:
        # money-critical). Si indicizzano solo i cognomi univoci.
        _by_surname: Dict[str, set] = {}
        for _nm, _sid in _raw.items():
            parts = _nm.split()
            if parts:
                _by_surname.setdefault(parts[-1], set()).add(_sid)
        for _sn, _sids in _by_surname.items():
            if len(_sids) == 1:
                self.name_to_sel.setdefault(_sn, next(iter(_sids)))
        super().__init__(*args, **kwargs)
        c = {**(self.context or {}), **ctx_in}

        self.stake: float = max(MIN_STAKE, float(c.get("stake", 2.0)))
        self.surface: str = str(c.get("surface", "grass")).lower()
        # lay-reversione (lay del dominante): funziona su superfici break-friendly
        # (clay/WTA), NON su erba/fast dove il servizio tiene e servi il set.
        _lay_rev = self.surface not in ("grass", "fast")
        # TREND-FOLLOWING: i dati mostrano che il tennis TRENDA (il dominante
        # continua). Con trend=True i setup di dominio si FLIPPANO: BACK del
        # dominante (cavalca) invece di LAY (rientro). Attivi su ogni superficie.
        self.trend: bool = bool(c.get("trend", False))
        # ADATTIVO: il bot rileva il REGIME dal prezzo live (efficiency ratio di
        # Kaufman) e sceglie la direzione da solo: trend->BACK (cavalca),
        # range->LAY (fade), neutro->non entra. Si adatta a QUALSIASI scenario.
        self.adapt: bool = bool(c.get("adapt", False))
        self.er_window_ms: int = int(c.get("er_window_ms", 60_000))
        self.er_trend: float = float(c.get("er_trend", 0.45))   # >= => trend
        self.er_range: float = float(c.get("er_range", 0.30))   # <= => range
        self._px_hist: Dict[int, List[Tuple[int, float]]] = {}  # sel -> [(pt, mid)]
        _enable_rev = _lay_rev or self.trend or self.adapt
        self.min_matched: float = float(c.get("min_matched", 50_000.0))
        self.min_book_size: float = float(c.get("min_book_size", 10.0))
        self.price_min: float = float(c.get("price_min", 1.08))
        self.price_max: float = float(c.get("price_max", 3.6))
        self.staged: bool = bool(c.get("staged", True))
        self.staged_frac: float = float(c.get("staged_frac", 0.4))
        # TIMEOUT ENTRY in SECONDI di publish_time (fix 2026-07-10 live≠backtest:
        # prima contava gli UPDATE del book — in live sono molti al secondo →
        # l'entry veniva cancellata in 2-3s invece dei ~25s attesi). Il vecchio
        # nome ``entry_timeout_ticks`` resta accettato (retrocompatibilità) ma
        # il valore è interpretato in secondi (25 update → 25 s equivalenti).
        self.entry_timeout_s: float = float(
            c.get("entry_timeout_s", c.get("entry_timeout_ticks", 25)))
        # MAKER: entra a quota MIGLIORE del touch (in coda) -> INCASSA lo spread
        # invece di pagarlo ("bancare"). Fill non garantito (gestito dal timeout).
        self.maker: bool = bool(c.get("maker", False))
        self.maker_offset: int = int(c.get("maker_offset", 1))
        # CLOSING (fix audit #7): secondi di publish_time tra i re-hedge della
        # sorveglianza post-chiusura (fallback a conteggio update senza pt).
        self.close_retry_s: float = float(c.get("close_retry_s", 20.0))
        self.dry_run: bool = bool(c.get("dry_run", False))

        # 1) BREAK POINT
        self.enable_break_point: bool = bool(c.get("enable_break_point", True))
        self.bp_target_ticks: int = int(c.get("bp_target_ticks", 5))
        self.bp_stop_ticks: int = int(c.get("bp_stop_ticks", 3))
        # 2) FADE OVER-REACTION
        self.enable_fade: bool = bool(c.get("enable_fade", True))
        self.fade_jump_ticks: int = int(c.get("fade_jump_ticks", 8))
        self.fade_target_ticks: int = int(c.get("fade_target_ticks", 4))
        self.fade_stop_ticks: int = int(c.get("fade_stop_ticks", 4))
        self.fade_max_game: int = int(c.get("fade_max_game", 3))
        # 3) SERVING FOR THE SET (solo clay/wta di default)
        self.enable_serving_set: bool = bool(c.get("enable_serving_set", _enable_rev))
        self.sfs_target_ticks: int = int(c.get("sfs_target_ticks", 6))
        self.sfs_stop_ticks: int = int(c.get("sfs_stop_ticks", 4))
        # 4) DOUBLE BREAK (solo clay/wta di default)
        self.enable_double_break: bool = bool(c.get("enable_double_break", _enable_rev))
        self.db_lead_games: int = int(c.get("db_lead_games", 3))
        self.db_target_ticks: int = int(c.get("db_target_ticks", 6))
        self.db_stop_ticks: int = int(c.get("db_stop_ticks", 4))
        # 5) SET TRANSITION
        self.enable_set_transition: bool = bool(c.get("enable_set_transition", True))
        self.st_window_games: int = int(c.get("st_window_games", 2))
        self.st_target_ticks: int = int(c.get("st_target_ticks", 5))
        self.st_stop_ticks: int = int(c.get("st_stop_ticks", 4))
        # 6) COMPRESSED FAVOURITE (solo clay/wta di default: su erba il fav domina)
        self.enable_compressed_fav: bool = bool(c.get("enable_compressed_fav", _enable_rev))
        self.cf_max_price: float = float(c.get("cf_max_price", 1.20))
        self.cf_target_ticks: int = int(c.get("cf_target_ticks", 4))
        self.cf_stop_ticks: int = int(c.get("cf_stop_ticks", 3))

        # runtime
        self.score: Optional[TennisScore] = None
        self._now_pt: Optional[int] = None  # publish_time del book corrente (ms)
        self._trade: Dict[str, Dict[str, Any]] = {}                # mid -> trade attivo
        self._last_key: Dict[str, Any] = {}                        # mid -> ultima score-key
        self._prev_sets: Dict[str, Tuple[int, int]] = {}           # mid -> (sh,sa) tick prec.
        self._set_start_px: Dict[Tuple[str, int, int], float] = {}  # (mid,sel,setnum)->prezzo
        self._set_won: Dict[str, Tuple[int, int]] = {}             # mid -> (winner_sel, games_tot@win)
        self._last_game_traded: Dict[str, Any] = {}                # mid -> game gia' tradato
        self.stats = {"entries": 0, "greens": 0, "scratches": 0, "stops": 0,
                      "pnl": 0.0}

    # ------------------------------------------------------------- telemetria
    def _emit(self, event: str, **payload: Any) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event, payload)
        except Exception:  # noqa: BLE001
            logger.debug("event_sink errore", exc_info=True)

    def check_market_book(self, market: Any, market_book: Any) -> bool:
        return getattr(market_book, "status", None) == "OPEN" \
            and bool(getattr(market_book, "runners", None))

    # ---------------------------------------------------------- helper punteggio
    def _lookup_sel(self, name: Optional[str]) -> Optional[int]:
        """selection_id da un nome IPS: prova nome completo, poi cognome."""
        n = _norm(name)
        if not n:
            return None
        if n in self.name_to_sel:
            return self.name_to_sel[n]
        parts = n.split()
        return self.name_to_sel.get(parts[-1]) if parts else None

    def _server_receiver_sel(self) -> Tuple[Optional[int], Optional[int]]:
        s = self.score
        if s is None or s.server is None:
            return None, None
        srv_name = s.home_name if s.server == "home" else s.away_name
        rcv_name = s.away_name if s.server == "home" else s.home_name
        return self._lookup_sel(srv_name), self._lookup_sel(rcv_name)

    def _sel_for_ha(self, side_ha: str) -> Optional[int]:
        s = self.score
        if s is None:
            return None
        return self._lookup_sel(s.home_name if side_ha == "home" else s.away_name)

    def _is_break_point(self) -> bool:
        s = self.score
        if s is None or s.server is None:
            return False
        srv_pt = s.point_home if s.server == "home" else s.point_away
        rcv_pt = s.point_away if s.server == "home" else s.point_home
        rs, rr = _point_rank(srv_pt), _point_rank(rcv_pt)
        if rs is None or rr is None:
            return False
        return rr == 3 and rs <= 1          # 0-40 / 15-40 (30-40 escluso)

    @staticmethod
    def _favourite(px: Dict[int, Dict[str, Any]]) -> Optional[int]:
        cand = {k: v["ltp"] for k, v in px.items() if v.get("ltp")}
        return min(cand, key=cand.get) if cand else None

    @staticmethod
    def _games_total(s: TennisScore) -> int:
        return (s.games_home or 0) + (s.games_away or 0)

    # ------------------------------------------------------ REGIME ADATTIVO
    def _track_px(self, pt: Optional[int], px: Dict[int, Dict[str, Any]]) -> None:
        if pt is None:
            return
        for sel, d in px.items():
            mid = ((d["bb"] + d["bl"]) / 2.0) if (d["bb"] and d["bl"]) else d["ltp"]
            if mid is None:
                continue
            h = self._px_hist.setdefault(sel, [])
            h.append((int(pt), float(mid)))
            if len(h) > 400:
                del h[:len(h) - 400]

    def _regime(self, sel: int) -> Optional[str]:
        """Efficiency ratio di Kaufman su ``sel``: 'trend' | 'range' | None."""
        h = self._px_hist.get(sel)
        if not h or len(h) < 6:
            return None
        now_t = h[-1][0]
        win = [p for t, p in h if now_t - t <= self.er_window_ms]
        if len(win) < 6:
            return None
        net = abs(win[-1] - win[0])
        path = sum(abs(win[i] - win[i - 1]) for i in range(1, len(win)))
        if path <= _EPS:
            return None
        er = net / path
        if er >= self.er_trend:
            return "trend"
        if er <= self.er_range:
            return "range"
        return None

    def _setup_side(self, sel: int) -> Optional[str]:
        """Direzione di un setup di dominio. ADATTIVA se self.adapt (dal regime),
        altrimenti BACK se trend, LAY se reversione."""
        if self.adapt:
            r = self._regime(sel)
            if r == "trend":
                return "BACK"     # cavalca il dominante
            if r == "range":
                return "LAY"      # fade il dominante
            return None           # regime neutro -> non entrare
        return "BACK" if self.trend else "LAY"

    # ------------------------------------------------------- posizione matchata
    def _position(self, market: Any, sel: int) -> Tuple[float, float, float, float]:
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
        return (b, bw / b if b else 0.0, l, lw / l if l else 0.0)

    @staticmethod
    def _net(b: float, ba: float, l: float, la: float) -> Tuple[float, float]:
        return (b * (ba - 1.0) - l * (la - 1.0), l - b)

    def _place(self, market: Any, sel: int, side: str, price: float,
               size: float) -> Optional[Any]:
        size = round(max(0.0, float(size)), 2)
        if price is None or price <= 1.0 or size < 0.01:
            return None
        if self.dry_run:
            self._emit("dry_place", sel=sel, side=side, price=price, size=size)
            return None
        try:
            trade = Trade(market_id=market.market_id, selection_id=int(sel),
                          handicap=0, strategy=self)
            order = trade.create_order(
                side=side,
                order_type=LimitOrder(price=float(price), size=size,
                                      persistence_type="LAPSE"),
            )
            market.place_order(order)
            return order
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

    def _close_at(self, market: Any, sel: int, price: float,
                  frac: float = 1.0) -> "Tuple[float, Optional[Any]]":
        """Piazza l'hedge di green-up. Ritorna (profitto BLOCCATO, ordine hedge).

        Il locked e' una stima corretta SOLO se l'hedge si riempie (a hedge
        pendente il netto e' ancora a una gamba); l'ordine viene ritornato per
        poterlo tracciare/cancellare (fix 2026-07-09: doppio-hedge staged)."""
        b, ba, l, la = self._position(market, sel)
        nw, nl = self._net(b, ba, l, la)
        g = compute_green(nw, nl, price)
        if g is None:
            return min(nw, nl), None
        side, size, locked = g
        o = self._place(market, sel, side, get_nearest_price(price), size * frac)
        return float(locked), o

    # ------------------------------------------------------------- apertura
    def _open_trade(self, market: Any, sel: int, side: str, book: Dict[str, Any],
                    target_ticks: int, stop_ticks: int, kind: str) -> bool:
        """side BACK -> profitto se la quota CALA; LAY -> se SALE. True se aperta."""
        if side not in ("BACK", "LAY"):     # regime neutro (adattivo) -> niente trade
            return False
        if side == "BACK":
            price, avail = book["bb"], book["sb"]
        else:
            price, avail = book["bl"], book["sl"]
        if price is None or not (self.price_min <= price <= self.price_max):
            return False
        if (avail or 0) < self.min_book_size:
            return False
        entry = get_nearest_price(price)
        if self.maker:
            # entra a quota MIGLIORE (in coda): BACK piu' alto, LAY piu' basso ->
            # incassa lo spread se riempito (fill non garantito -> timeout).
            entry = price_ticks_away(entry, self.maker_offset if side == "BACK"
                                     else -self.maker_offset)
        order = self._place(market, sel, side, entry, self.stake)
        if order is None and not self.dry_run:
            return False
        if side == "BACK":
            target = price_ticks_away(entry, -target_ticks)   # green: quota GIU'
            stop = price_ticks_away(entry, stop_ticks)
        else:
            target = price_ticks_away(entry, target_ticks)    # green: quota SU
            stop = price_ticks_away(entry, -stop_ticks)
        s = self.score
        self._trade[market.market_id] = {
            "state": OPEN, "sel": int(sel), "side": side, "entry": entry,
            "target": target, "stop": stop, "kind": kind, "staged_done": False,
            "staged_order": None, "order": order, "wait": 0,
            # publish_time del piazzamento: base del timeout entry in secondi
            "t_open": getattr(self, "_now_pt", None),
            "entry_games": (s.games_home, s.games_away, s.sets_home, s.sets_away)
            if s else None,
        }
        if s is not None:
            self._last_game_traded[market.market_id] = (
                s.games_home, s.games_away, s.sets_home, s.sets_away)
        self.stats["entries"] += 1
        self._emit("entry", kind=kind, sel=sel, side=side, price=entry,
                   target=target, stop=stop)
        logger.info("[PRO] %s: %s sel=%s @%.2f (target %.2f / stop %.2f)",
                    kind.upper(), side, sel, entry, target, stop)
        return True

    # ------------------------------------------------------------- SEGNALI
    def _sig_break_point(self, market: Any, px: Dict[int, Dict[str, Any]]) -> bool:
        if not (self.enable_break_point and self._is_break_point()):
            return False
        srv, rcv = self._server_receiver_sel()
        sel = srv if self.surface in ("grass", "fast") else rcv
        if sel in px:
            return self._open_trade(market, sel, "BACK", px[sel],
                                    self.bp_target_ticks, self.bp_stop_ticks,
                                    "break_point")
        return False

    def _sig_fade(self, market: Any, mid: str, px: Dict[int, Dict[str, Any]]) -> bool:
        s = self.score
        if not self.enable_fade or s is None:
            return False
        if self._games_total(s) > self.fade_max_game:
            return False
        fav = self._favourite(px)
        if fav is None:
            return False
        d = px[fav]
        setnum = (s.sets_home or 0) + (s.sets_away or 0)
        start = self._set_start_px.get((mid, fav, setnum))
        if start is None or not d["bl"]:
            return False
        jump = ticks_between(get_nearest_price(start), get_nearest_price(d["bl"]))
        if jump is None or jump < self.fade_jump_ticks:
            return False
        return self._open_trade(market, fav, "BACK", d, self.fade_target_ticks,
                                self.fade_stop_ticks, "fade")

    def _sig_set_transition(self, market: Any, mid: str,
                            px: Dict[int, Dict[str, Any]]) -> bool:
        s = self.score
        if not self.enable_set_transition or s is None:
            return False
        won = self._set_won.get(mid)
        if won is None:
            return False
        winner_sel, games_at_win = won
        if self._games_total(s) - games_at_win > self.st_window_games:
            self._set_won.pop(mid, None)         # finestra scaduta
            return False
        if winner_sel in px:
            return self._open_trade(market, winner_sel, self._setup_side(winner_sel), px[winner_sel],
                                    self.st_target_ticks, self.st_stop_ticks,
                                    "set_transition")
        return False

    def _sig_serving_for_set(self, market: Any, px: Dict[int, Dict[str, Any]]) -> bool:
        s = self.score
        if not self.enable_serving_set or s is None or s.server is None:
            return False
        gh, ga = s.games_home or 0, s.games_away or 0
        srv_games = gh if s.server == "home" else ga
        oth_games = ga if s.server == "home" else gh
        if not (srv_games >= 5 and (srv_games - oth_games) >= 1):
            return False
        srv, _rcv = self._server_receiver_sel()
        if srv in px:
            return self._open_trade(market, srv, self._setup_side(srv), px[srv],
                                    self.sfs_target_ticks, self.sfs_stop_ticks,
                                    "serving_for_set")
        return False

    def _sig_double_break(self, market: Any, px: Dict[int, Dict[str, Any]]) -> bool:
        s = self.score
        if not self.enable_double_break or s is None:
            return False
        gh, ga = s.games_home or 0, s.games_away or 0
        if abs(gh - ga) < self.db_lead_games:
            return False
        sel = self._sel_for_ha("home" if gh > ga else "away")
        if sel in px:
            return self._open_trade(market, sel, self._setup_side(sel), px[sel],
                                    self.db_target_ticks, self.db_stop_ticks,
                                    "double_break")
        return False

    def _sig_compressed_fav(self, market: Any, px: Dict[int, Dict[str, Any]]) -> bool:
        if not self.enable_compressed_fav:
            return False
        fav = self._favourite(px)
        if fav is None:
            return False
        d = px[fav]
        if not d["ltp"] or d["ltp"] > self.cf_max_price:
            return False
        return self._open_trade(market, fav, self._setup_side(fav), d, self.cf_target_ticks,
                                self.cf_stop_ticks, "compressed_fav")

    # -------------------------------------------------------------- main loop
    def _track_sets(self, mid: str, px: Dict[int, Dict[str, Any]]) -> None:
        """Aggiorna prezzo inizio-set + rileva la vittoria di un set (ogni tick)."""
        s = self.score
        if s is None:
            return
        setnum = (s.sets_home or 0) + (s.sets_away or 0)
        for sel, d in px.items():
            k = (mid, sel, setnum)
            if k not in self._set_start_px and d["ltp"]:
                self._set_start_px[k] = float(d["ltp"])
        cur = (s.sets_home or 0, s.sets_away or 0)
        prev = self._prev_sets.get(mid)
        if prev is not None and cur != prev:
            winner_ha = "home" if cur[0] > prev[0] else (
                "away" if cur[1] > prev[1] else None)
            wsel = self._sel_for_ha(winner_ha) if winner_ha else None
            if wsel is not None:
                self._set_won[mid] = (int(wsel), self._games_total(s))
        self._prev_sets[mid] = cur

    def process_market_book(self, market: Any, market_book: Any) -> None:
        mid = market_book.market_id
        s = self.score
        px: Dict[int, Dict[str, Any]] = {}
        for r in market_book.runners:
            if getattr(r, "status", None) != "ACTIVE":
                continue
            ex = getattr(r, "ex", None)
            if ex is None:
                continue
            px[int(r.selection_id)] = {
                "bb": get_price(ex.available_to_back, 0),
                "bl": get_price(ex.available_to_lay, 0),
                "sb": get_size(ex.available_to_back, 0),
                "sl": get_size(ex.available_to_lay, 0),
                "ltp": getattr(r, "last_price_traded", None),
            }

        # traccia set + PREZZO (per il regime adattivo) ad OGNI tick
        pt = getattr(market_book, "publish_time_epoch", None)
        self._now_pt = pt  # publish_time corrente (timeout entry in secondi)
        self._track_sets(mid, px)
        self._track_px(pt, px)

        # 1) gestisci trade aperto
        trade = self._trade.get(mid)
        if trade and trade["state"] == OPEN:
            self._manage(market, trade, px)
            return
        # 1b) CLOSING (fix audit #7): la chiusura va SORVEGLIATA finche' il
        # blotter non e' pari — cancel falliti o hedge non riempito (bet delay
        # 3s) lascerebbero un'esposizione nuda/rovesciata non gestita.
        if trade and trade["state"] == CLOSING:
            self._surveil_closing(market, trade, px)
            return

        # 2) gate ingresso
        if not market_book.inplay:
            return
        if float(getattr(market_book, "total_matched", 0.0) or 0.0) < self.min_matched:
            return
        if s is None:
            return
        key = s.key()
        if self._last_key.get(mid) == key:       # solo su CAMBIO stato (nuovo punto)
            return
        self._last_key[mid] = key

        # COOLDOWN: un solo trade per game (niente ri-entrate a raffica)
        cur_game = (s.games_home, s.games_away, s.sets_home, s.sets_away)
        if self._last_game_traded.get(mid) == cur_game:
            return

        # 3) SEGNALI in ordine di priorita' (uno solo per volta)
        if self._sig_break_point(market, px):
            return
        if self._sig_fade(market, mid, px):
            return
        if self._sig_set_transition(market, mid, px):
            return
        if self._sig_serving_for_set(market, px):
            return
        if self._sig_double_break(market, px):
            return
        if self._sig_compressed_fav(market, px):
            return

    # --------------------------------------------------------------- gestione
    def _manage(self, market: Any, trade: Dict[str, Any],
                px: Dict[int, Dict[str, Any]]) -> None:
        sel = trade["sel"]
        d = px.get(sel)
        b, ba, l, la = self._position(market, sel)

        if (b + l) <= _EPS:
            # entry NON ancora riempita: timeout in SECONDI di publish_time
            # (fallback al conteggio update SOLO se il publish_time manca).
            trade["wait"] = int(trade.get("wait", 0)) + 1
            pt = getattr(self, "_now_pt", None)
            t0 = trade.get("t_open")
            timed_out = (
                pt is not None and t0 is not None
                and (pt - t0) / 1000.0 >= self.entry_timeout_s
            ) or (
                (pt is None or t0 is None) and trade["wait"] > self.entry_timeout_s
            )
            if timed_out:
                self._cancel(market, trade.get("order"))
                self._trade[market.market_id] = {"state": FLAT}
                self._emit("entry_timeout", sel=sel, kind=trade.get("kind"))
                logger.info("[PRO] entry timeout (%s) sel=%s: cancellata",
                            trade.get("kind"), sel)
            return
        if d is None:
            return

        mkt = d["bl"] if trade["side"] == "BACK" else d["bb"]
        if mkt is None:
            return
        entry = trade["entry"]
        favorable = (mkt < entry) if trade["side"] == "BACK" else (mkt > entry)
        move_t = ticks_between(min(entry, mkt), max(entry, mkt)) or 0
        target_t = ticks_between(min(entry, trade["target"]),
                                 max(entry, trade["target"])) or 1
        stop_t = ticks_between(min(entry, trade["stop"]),
                               max(entry, trade["stop"])) or 1

        # scaglione: a meta' strada verso il target, green del frac
        if (self.staged and not trade["staged_done"] and favorable
                and move_t >= max(1, target_t // 2)):
            _, staged_o = self._close_at(market, sel, mkt, frac=self.staged_frac)
            trade["staged_done"] = True
            trade["staged_order"] = staged_o
            self._emit("staged_green", sel=sel, price=mkt)

        if favorable and move_t >= target_t:      # TARGET -> green totale
            self._finish(market, trade, "green", sel,
                         *self._full_close(market, trade, sel, mkt))
            return
        if (not favorable) and move_t >= stop_t:  # STOP
            self._finish(market, trade, "stop", sel,
                         *self._full_close(market, trade, sel, mkt))
            return
        # USCITA STRUTTURALE: il game/set che ha innescato si e' risolto -> chiudi
        s = self.score
        if s is not None and trade.get("entry_games") is not None:
            if (s.games_home, s.games_away, s.sets_home, s.sets_away) != trade["entry_games"]:
                self._finish(market, trade, "scratch", sel,
                             *self._full_close(market, trade, sel, mkt))
                return

    def _full_close(self, market: Any, trade: Dict[str, Any], sel: int,
                    price: float) -> "Tuple[float, Optional[Any]]":
        """Chiusura TOTALE del trade (fix 2026-07-09: doppio-hedge staged).

        Col bet delay in-play del tennis (3s) l'hedge dello SCAGLIONE può essere
        ancora PENDENTE quando scatta target/stop/scratch: il green finale —
        calcolato sulla sola posizione MATCHED — ri-hedgerebbe l'intera size e,
        al fill di entrambi, la posizione risulterebbe ROVESCIATA (over-hedge).
        Prima del green finale si CANCELLA il residuo vivo dello staged hedge.
        Ritorna (locked stimato, ordine hedge) — l'ordine va SORVEGLIATO in
        CLOSING (fix audit #7): il locked e' reale solo a hedge matched."""
        self._cancel(market, trade.get("staged_order"))
        locked, order = self._close_at(market, sel, price)
        return locked, order

    def _finish(self, market: Any, trade: Dict[str, Any], outcome: str,
                sel: int, locked: float, close_order: Any = None) -> None:
        # cancella l'eventuale residuo dell'ordine di ingresso ancora vivo
        self._cancel(market, trade.get("order"))
        self.stats["pnl"] += float(locked)
        # contabilita' incrementale (review 16/07, pattern _book_locked dello
        # scalper): si ricorda quanto e' gia' stato accreditato — se la
        # sorveglianza CLOSING ri-hedgia a un prezzo diverso, stats["pnl"] viene
        # CORRETTO col delta (mai lasciare una stima vecchia nel dashboard).
        trade["booked"] = float(locked)
        self.stats[{"green": "greens", "stop": "stops",
                    "scratch": "scratches"}.get(outcome, "greens")] += 1
        self._emit("exit", outcome=outcome, kind=trade.get("kind"), sel=sel,
                   locked=round(float(locked), 3))
        logger.info("[PRO] EXIT %s (%s) sel=%s locked=%+.3f | stats=%s",
                    outcome, trade.get("kind"), sel, locked, self.stats)
        # CLOSING (fix audit #7): prima si passava dritti a FLAT col solo hedge
        # PIAZZATO — un cancel fallito del residuo entry o un hedge non riempito
        # sotto il delay 3s lasciava esposizione nuda/rovesciata NON gestita.
        # Ora la chiusura resta sorvegliata in process_market_book (pattern
        # tennis_swing_bot): FLAT solo quando il blotter dice |nw−nl| < 0.02.
        trade["state"] = CLOSING
        trade["close_order"] = close_order
        trade["t_close"] = getattr(self, "_now_pt", None)
        trade["close_wait"] = 0
        self._trade[market.market_id] = trade

    def _surveil_closing(self, market: Any, trade: Dict[str, Any],
                         px: Dict[int, Dict[str, Any]]) -> None:
        """Sorveglianza dello stato CLOSING (fix audit #7).

        A ogni update: ritenta i cancel dei residui (entry/staged, idempotenti);
        quando il blotter e' PARI (|nw−nl| < 0.02, o nessun matched) cancella
        l'eventuale residuo dell'hedge e SOLO allora dichiara FLAT. Se dopo
        ``close_retry_s`` secondi di publish_time (fallback: update senza pt) la
        posizione non e' ancora pari, l'hedge stantio viene cancellato e si
        RI-HEDGIA al touch corrente (compute_green sulle esposizioni fresche:
        self-correcting anche su fill parziali). Mai abbandonare la posizione."""
        sel = int(trade.get("sel") or 0)
        # residui di ingresso/scaglione: ritenta il cancel (puo' essere fallito)
        self._cancel(market, trade.get("order"))
        self._cancel(market, trade.get("staged_order"))
        b, ba, l, la = self._position(market, sel)
        nw, nl = self._net(b, ba, l, la)
        if (b + l) <= _EPS or abs(nw - nl) < 0.02:
            # blotter pari: cancella il residuo dell'hedge (un fill tardivo
            # ROVESCEREBBE la posizione appena chiusa) e chiudi davvero.
            self._cancel(market, trade.get("close_order"))
            self._trade[market.market_id] = {"state": FLAT}
            self._emit("closed_flat", sel=sel, kind=trade.get("kind"))
            return
        trade["close_wait"] = int(trade.get("close_wait", 0)) + 1
        pt = getattr(self, "_now_pt", None)
        t0 = trade.get("t_close")
        retry = (
            pt is not None and t0 is not None
            and (pt - t0) / 1000.0 >= self.close_retry_s
        ) or ((pt is None or t0 is None) and trade["close_wait"] > self.close_retry_s)
        if not retry:
            return
        d = px.get(sel)
        mkt = (d.get("bl") if trade.get("side") == "BACK" else d.get("bb")) if d else None
        if mkt is None:
            return  # book monco: si riprova al prossimo update (mai mollare)
        self._cancel(market, trade.get("close_order"))
        locked2, o2 = self._close_at(market, sel, mkt)
        # correzione contabile (review 16/07): il locked accreditato in _finish era
        # una STIMA al vecchio prezzo dell'hedge; il re-hedge cambia l'esito reale →
        # stats["pnl"] va aggiornato col DELTA rispetto all'ultimo accredito.
        booked = float(trade.get("booked") or 0.0)
        delta = float(locked2) - booked
        if abs(delta) > 1e-9:
            self.stats["pnl"] += delta
            trade["booked"] = float(locked2)
        trade["close_order"] = o2
        trade["t_close"] = pt
        trade["close_wait"] = 0
        self._emit("close_escalate", sel=sel, kind=trade.get("kind"), price=mkt,
                   locked=round(float(locked2), 3))
