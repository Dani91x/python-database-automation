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

from ..trading.stato_mercato import AttesaRiapertura, guardia_flumine
from .condotta_ordini import (
    ESITO_GIA_IN_USCITA,
    ESITO_NESSUNA_POSIZIONE,
    ESITO_USCITA_AVVIATA,
    MOTIVO_USCITA_MANUALE,
    FrenoRifiuti,
    dichiara_chiusura_mercato,
    ingresso_finito,
    ordini_vivi_su,
    registra_esito_manuale,
    sbilancio_selezione,
    size_legale,
    stato_ordine,
)
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
    #: 25/09 - uscite automatiche (presa di profitto). Lo imposta il runner
    #: tennis dalla riga per partita; di classe = False (DEFAULT dal 25/09
    #: sera, ordine dell'utente: «di default tutte le uscite le voglio
    #: spente»; replay e backtest non lo toccano, quindi con questo default
    #: prendono anche loro il ramo manuale finche' non lo passano esplicito).
    uscite_automatiche: bool = False

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
        # escalation della chiusura MAKER → TAKER al touch in SECONDI di
        # publish_time (fix audit #10, come tmax: prima contava gli UPDATE del
        # book — in live sono molti al secondo → escalation in 1-2s invece dei
        # ~20s attesi). close_retry_ticks resta come FALLBACK a conteggio update
        # quando il publish_time manca (replay/mocks vecchi).
        self.close_retry_s = float(c.get("close_retry_s", 20.0))
        self.close_retry_ticks = int(c.get("close_retry_ticks", 20))
        self.maker = bool(c.get("maker", True))
        self.maker_offset = int(c.get("maker_offset", 1))
        self.min_matched = float(c.get("min_matched", 10_000.0))
        self.price_min = float(c.get("price_min", 1.08))
        self.price_max = float(c.get("price_max", 8.0))
        self.dry_run = bool(c.get("dry_run", False))
        # LIVE: le size vanno legalizzate per la giurisdizione (.it), altrimenti
        # Betfair rifiuta e la gamba resta scoperta. Lo dichiara il runner
        # (`live_min_bet` > 0 solo in LIVE, `tennis_runner._instantiate_bot`).
        self.live = float(c.get("live_min_bet", 0.0) or 0.0) > 0.0
        # TOLLERANZA di «posizione pari» sulla SELEZIONE, in EUR. E' la soglia
        # che lo swing usava gia' per dire «flat» (0,01), qui resa esplicita e
        # applicata al blotter della SELEZIONE, non al solo trade corrente.
        self.tolleranza_flat = float(c.get("tolleranza_flat", 0.01))
        # stato per market
        self._hist: Dict[str, deque] = {}       # mid tick history
        self._prev_rsi: Dict[str, float] = {}
        self._tr: Dict[str, Dict[str, Any]] = {}  # trade attivo
        self.stats = {"entries": 0, "wins": 0, "losses": 0, "manuali": 0, "pnl": 0.0}
        # "CHIUDI ORA" (D3, 24/09): il runner alza la richiesta, il bot esce
        # col SUO stato `closing` e non apre piu' niente (`condotta_ordini` 4).
        self.uscita_manuale_chiesta: bool = False
        self.uscita_manuale: Optional[Dict[str, Any]] = None
        self.settled_pnl: float = 0.0
        self._pnl_settled_oids: set = set()
        # freno dopo i rifiuti di Betfair (modulo condiviso coi quattro bot)
        self._freno = FrenoRifiuti()
        # D2 (24/09): il diario delle attese di riapertura (una riga per sospensione)
        self._attese = AttesaRiapertura()
        self._now_ms: Optional[int] = None
        # il blotter e' stato letto davvero in questo giro? Un'esposizione non
        # letta NON e' un'esposizione nulla: senza questo flag, un'eccezione del
        # blotter faceva dichiarare piatta una posizione aperta.
        self._blotter_letto: bool = True

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
        self._blotter_letto = True
        try: orders = market.blotter.strategy_orders(self)
        except Exception as _e:  # noqa
            # ⚠️ UN'ESPOSIZIONE NON LETTA NON E' UN'ESPOSIZIONE NULLA. Prima si
            # tornava (0,0,0,0) in silenzio e chi chiamava concludeva «flat»,
            # dimenticando una posizione ancora aperta. Ora il flag lo dice.
            self._blotter_letto = False
            logger.warning("[SWING] blotter illeggibile sel=%s: %s — la posizione "
                           "NON e' dichiarata piatta", sel, _e)
            orders = []
        for o in orders:
            if int(getattr(o, "selection_id", 0) or 0) != int(sel): continue
            sm = float(getattr(o, "size_matched", 0.0) or 0.0)
            ap = float(getattr(o, "average_price_matched", 0.0) or 0.0)
            if sm <= _EPS or ap <= 0: continue
            if (getattr(o, "side", "") or "").upper() == "BACK": b += sm; bw += sm*ap
            else: l += sm; lw += sm*ap
        return b, (bw/b if b else 0), l, (lw/l if l else 0)

    def _orologio_s(self) -> float:
        """L'ora del BOT, in secondi: il `publish_time` dell'ultimo book."""
        if self._now_ms is not None:
            return float(self._now_ms) / 1000.0
        import time as _t

        return _t.time()

    def _place(self, market: Any, sel: int, side: str, price: float, size: float,
               *, copertura: bool = False) -> Optional[Any]:
        size = round(max(0.0, size), 2)
        if price is None or price <= 1.0 or size < 0.01 or self.dry_run: return None
        # SIZE LEGALE DI GIURISDIZIONE (.it): sotto il minimo Betfair rifiuta e
        # la gamba resta scoperta. Le coperture si bumpano, gli ingressi no.
        legale, motivo = size_legale(size, side, live=self.live,
                                     riduce_liability=copertura)
        if legale is None:
            self._emit("size_non_legale", sel=sel, side=side, price=price,
                       size=size, copertura=copertura, motivo=motivo)
            logger.warning("[SWING] size non legale sel=%s %s %s: %s",
                           sel, side, size, motivo)
            return None
        size = legale
        # D2 (24/09) GUARDIA DELLO STATO DEL MERCATO, per OGNI ordine (anche
        # le coperture): a mercato sospeso/chiuso Betfair e il `MarketValidation`
        # di flumine lo rifiuterebbero comunque. L'ordine non parte (esito
        # identico al rifiuto di oggi), UNA riga `attesa_riapertura`, e NON si
        # conta nel freno: una sospensione non e' un rifiuto.
        if guardia_flumine(market, self._attese, self._emit,
                           sel=int(sel), side=side) is not None:
            return None
        # FRENO DOPO I RIFIUTI: mai sulle coperture (devono poter partire sempre)
        if not copertura:
            fermo = self._freno.bloccato(market.market_id, sel, self._orologio_s())
            if fermo:
                # il motivo si scrive UNA volta per rifiuto, non a ogni tentativo
                if self._freno.da_annunciare(market.market_id, sel):
                    self._emit("freno_rifiuti", sel=sel, side=side, motivo=fermo)
                return None
        try:
            tr = Trade(market_id=market.market_id, selection_id=int(sel), handicap=0, strategy=self)
            o = tr.create_order(side=side, order_type=LimitOrder(price=float(price), size=size, persistence_type="LAPSE"))
            # L'ESITO DEL PIAZZAMENTO SI LEGGE (catalogo §7 difetto 2): il bool
            # di `Market.place_order` e' False quando un trading control boccia
            # l'ordine, che non entra nel blotter e resta in VIOLATION
            # (`flumine/execution/transaction.py:67-75`). Prima lo swing
            # registrava comunque il trade e contava l'ingresso.
            if not market.place_order(o):
                n, attesa = self._freno.registra_rifiuto(
                    market.market_id, sel, self._orologio_s())
                self._emit("place_rejected", sel=sel, side=side, price=price, size=size,
                           rifiuti=n, riprovo_fra_s=attesa,
                           motivo=str(getattr(o, "violation_msg", "") or "rifiutato"))
                logger.warning("[SWING] piazzamento RIFIUTATO sel=%s %s @%s per %s "
                               "(%d-esimo, riprovo fra %.0fs): %s",
                               sel, side, price, size, n, attesa,
                               getattr(o, "violation_msg", None))
                return None
            self._freno.registra_successo(market.market_id, sel)
            return o
        except Exception as e:  # noqa
            logger.debug("place fail %s", e); return None

    def _close(self, market: Any, sel: int, price: float) -> Tuple[float, Optional[Any]]:
        """Piazza l'hedge di green. Ritorna (locked stimato, ordine di chiusura)."""
        b, ba, l, la = self._pos(market, sel)
        nw, nl = b*(ba-1)-l*(la-1), l-b
        g = compute_green(nw, nl, price)
        if g is None: return min(nw, nl), None
        side, sz, locked = g
        # COPERTURA: passa il freno rifiuti e puo' essere bumpata al minimo .it
        o = self._place(market, sel, side, get_nearest_price(price), sz,
                        copertura=True)
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

    def _puo_dimenticare(self, market: Any, sel: int, tr: Dict[str, Any],
                         b: float, l: float, nw: float, nl: float) -> bool:
        """L'UNICO punto da cui un trade puo' essere dimenticato.

        Si dimentica SOLO se la SELEZIONE e' pari secondo il blotter, che e'
        l'unica fonte di verita' dell'esposizione. Tre condizioni, tutte
        necessarie:
          * il blotter e' stato letto davvero in questo giro;
          * lo sbilancio ABBINATO della selezione sta dentro la tolleranza
            dichiarata (`tolleranza_flat`) — si guarda la SELEZIONE e non il
            solo trade corrente, perche' un residuo di un ciclo precedente resta
            comunque denaro esposto;
          * nessun ordine del bot su quella selezione e' ancora VIVO sul book.
        """
        if not self._blotter_letto:
            return False
        sb = sbilancio_selezione(market, self, sel)
        if sb is None or sb > self.tolleranza_flat:
            return False
        # nessun ordine ancora vivo: un residuo appoggiato — o un ordine ancora
        # `Cancelling`, perche' `cancel_order` e' asincrona — puo' riempirsi dopo
        if ordini_vivi_su(market, self, sel) is not False:
            return False
        self._cancel(market, tr.get("order"))
        self._cancel(market, tr.get("close_order"))
        mid = str(getattr(market, "market_id", "") or "")
        self._tr.pop(mid, None)
        self._emit("posizione_pari", sel=sel, sbilancio=round(sb, 3),
                   note="selezione verificata pari dal blotter: trade chiuso")
        return True

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
            # ⚠️ IL RUNNER NON E' NEL BOOK. Di norma e' un update parziale e si
            # riprova al giro dopo. Ma se la SELEZIONE e' verificata pari e non
            # c'e' nessun ordine vivo, quel trade non tornera' MAI: uscire e
            # basta lo lascia in memoria per sempre, e il referto lo legge come
            # «il bot sorveglia il nulla» (misurato il 17/09: K4 x2 su 35790089
            # scenario `live`, trade su una selezione sparita dal book con
            # ZERO ordini del bot su di essa). Si chiude solo a conti fatti:
            # `_puo_dimenticare` pretende blotter letto, selezione pari e
            # nessun ordine ancora vivo.
            if self._puo_dimenticare(market, sel, tr, 0.0, 0.0, 0.0, 0.0):
                self._emit("runner_sparito", sel=sel,
                           note=("la selezione non e' piu' nel book e non ha "
                                 "nulla di abbinato ne' di vivo: trade chiuso"))
            return
        bb = get_price(ex.available_to_back, 0); bl = get_price(ex.available_to_lay, 0)
        if not bb or not bl:
            # book MONCO su quella selezione (un lato senza denaro): stessa
            # regola del runner sparito — non si esce e basta lasciando il trade
            # in memoria per sempre. Se la selezione e' verificata pari e non ha
            # ordini vivi, il trade e' finito e si chiude.
            if self._puo_dimenticare(market, sel, tr, 0.0, 0.0, 0.0, 0.0):
                self._emit("book_monco", sel=sel,
                           note=("book senza uno dei due lati e selezione "
                                 "verificata pari: trade chiuso"))
            return
        tmid = _tki((bb+bl)/2)
        side = tr["side"]
        # DRY (16/07): posizione VIRTUALE dal prezzo d'ingresso — cosi' il
        # ciclo target/stop/time gira identico al reale e il paper produce
        # un ESITO (prima: matched 0 → ramo 'non riempita' → trade evaporato
        # a 40s senza exit ne' P&L)
        if self.dry_run:
            pe = float(tr.get("px") or 0.0)
            if pe <= 1.0:
                self._tr.pop(mid, None)
                return
            if side == "BACK":
                b, ba, l, la = self.stake, pe, 0.0, 0.0
            else:
                b, ba, l, la = 0.0, 0.0, self.stake, pe
        else:
            b, ba, l, la = self._pos(market, sel)

        # fase CLOSING: l'hedge MAKER può non riempirsi MAI → mai abbandonare la
        # posizione: dopo close_retry_ticks update si cancella e si chiude TAKER
        # al touch (fill certo, si paga lo spread). Pop SOLO a posizione flat.
        if tr.get("closing"):
            nw, nl = b*(ba-1)-l*(la-1), l-b
            if self._puo_dimenticare(market, sel, tr, b, l, nw, nl):
                return
            # ⚠️ IL PRIMO HEDGE. Quando si entra in CLOSING dal TIMEOUT
            # D'INGRESSO non c'e' nessun `close_order`: prima si aspettavano i
            # 20 s dell'escalation con la posizione scoperta. Se c'e' da
            # coprire e non c'e' niente in volo, si copre SUBITO.
            if tr.get("close_order") is None and not self.dry_run:
                px0 = bb if side == "BACK" else bl
                _, o0 = self._close(market, sel, px0)
                if o0 is not None:
                    tr["close_order"] = o0
                    tr["close_wait"] = 0
                    tr["t_close"] = getattr(mb, "publish_time_epoch", None)
                    self._emit("copertura_tardiva", sel=sel, price=px0,
                               note=("l'ingresso si e' riempito DOPO il timeout: "
                                     "copro subito invece di abbandonarlo"))
                    return
            # escalation in SECONDI di publish_time (fix audit #10, come tmax);
            # fallback al conteggio update SOLO se il publish_time manca.
            tr["close_wait"] = tr.get("close_wait", 0) + 1
            ptc = getattr(mb, "publish_time_epoch", None)
            tc = tr.get("t_close")
            if tc is None and ptc is not None:
                tr["t_close"] = ptc  # base tempo mancante (closing legacy): parte ora
                tc = ptc
            escalate = (
                ptc is not None and tc is not None
                and (ptc - tc) / 1000.0 >= self.close_retry_s
            ) or ((ptc is None or tc is None) and tr["close_wait"] > self.close_retry_ticks)
            if escalate:
                self._cancel(market, tr.get("close_order"))
                px = bl if side == "BACK" else bb   # TAKER al touch: attraversa
                locked2, o2 = self._close(market, sel, px)
                # RETTIFICA DEL P&L (stessa cosa che fa il PRO): il `locked`
                # accreditato all'uscita era la stima al prezzo MAKER. Se
                # l'hedge non si e' riempito e si ri-chiude al TOUCH, il numero
                # nel pannello non e' mai esistito: si applica il DELTA.
                prima = float(tr.get("locked", 0.0) or 0.0)
                delta = float(locked2) - prima
                if abs(delta) > 1e-9:
                    self.stats["pnl"] += delta
                    tr["locked"] = float(locked2)
                tr["close_order"] = o2
                tr["close_wait"] = 0
                tr["t_close"] = ptc
                self._emit("close_escalate", sel=sel, price=px,
                           locked=round(float(locked2), 3),
                           rettifica=round(delta, 3))
            return

        if (b+l) <= _EPS:
            # ⚠️ L'INGRESSO PUO' ESSERE GIA' MORTO. Con `persistence_type=LAPSE`
            # Betfair uccide l'ordine appoggiato a ogni SOSPENSIONE (in tennis:
            # a ogni punto). Prima il bot continuava ad aspettare 40 s una quota
            # che a mercato non esisteva piu', e nel frattempo credeva di essere
            # OPEN senza un solo ordine vivo (misurato: K4 su 35795739).
            # Si legge lo stato VERO dell'ordine (Enum `.value`, mai stringa).
            if ingresso_finito(tr.get("order")):
                self._emit("entry_scaduta", sel=sel,
                           stato=stato_ordine(tr.get("order")),
                           note=("l'ordine d'ingresso non esiste piu' a mercato "
                                 "(scaduto alla sospensione o annullato): non "
                                 "aspetto il timeout"))
                self._puo_dimenticare(market, sel, tr, b, l, 0.0, 0.0)
                return
            # entry non riempita: timeout in SECONDI di publish_time (fix
            # 2026-07-10, come tmax) — fallback a 40 update solo senza pt.
            tr["wait"] = tr.get("wait", 0)+1
            pt0 = getattr(mb, "publish_time_epoch", None)
            t00 = tr.get("t0")
            entry_timed_out = (
                (pt0 is not None and t00 is not None
                 and (pt0 - t00) / 1000.0 >= 40.0)
                or ((pt0 is None or t00 is None) and tr["wait"] > 40)
            )
            if entry_timed_out:
                # ⚠️ NON SI DIMENTICA IL TRADE. Prima qui si faceva `pop` subito
                # dopo un `cancel` il cui esito non veniva MAI verificato: se il
                # cancel non aveva effetto (ordine PENDING senza `bet_id`:
                # `BetfairOrder.cancel()` alza `OrderUpdateError`, ingoiata) o
                # se un fill arrivava nello stesso istante, l'ingresso si
                # riempiva DOPO e la posizione restava orfana, senza stop, senza
                # uscita e senza che nessuno la vedesse.
                # MISURATO nel replay del 17/09 su 35790089: 15 ingressi, 5
                # uscite, e 7,57 EUR di esposizione abbinata abbandonata su una
                # selezione su cui il bot non aveva piu' nessun trade.
                # Adesso si passa in CLOSING: si dimentica solo a posizione
                # verificata PARI dal blotter (`_puo_dimenticare`).
                self._cancel(market, tr.get("order"))
                tr["closing"] = True
                tr["close_order"] = None
                tr["close_wait"] = 0
                tr["t_close"] = pt0
                self._emit("entry_timeout", sel=sel,
                           note=("ingresso scaduto: cancello e sorveglio finche' "
                                 "il blotter non dice che la selezione e' pari"))
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
        # 25/09 USCITE MANUALI (interruttore del bot, letto a caldo dal runner):
        # si spegne SOLO la presa di profitto (target). Stop a tick e time-stop
        # restano: sono protezioni. Default True = identico a prima.
        if hit and not self.uscite_automatiche:
            hit = False
        if hit or adverse or timed_out:
            # esci a quota migliore (maker) o al touch
            px = (bb if self.maker else bl) if side == "BACK" else (bl if self.maker else bb)
            kind = "target" if hit else ("stop" if adverse else "time")
            if self.dry_run:
                # esito VIRTUALE al prezzo di uscita: green spalmato dalla
                # posizione sintetica (stesso compute_green del reale)
                nw = b*(ba-1.0) - l*(la-1.0)
                nl = l - b
                g = compute_green(nw, nl, px)
                locked = float(g[2]) if g is not None else min(nw, nl)
                self.stats["pnl"] += locked
                # VINTO/PERSO SI DECIDE DAL RISULTATO, non dal motivo d'uscita:
                # prima un time-stop in profitto era contato come perdita e uno
                # stop con green positivo pure, e le metriche del pannello non
                # erano riconciliabili col P&L (referto d'audit, S7).
                self.stats["wins" if locked > 0 else "losses"] += 1
                self._emit("exit", sel=sel, kind=kind,
                           locked=round(locked, 3), dry=True)
                self._tr.pop(mid, None)   # nessuna posizione reale da smontare
                return
            locked, close_order = self._close(market, sel, px)
            self.stats["pnl"] += locked
            self.stats["wins" if locked > 0 else "losses"] += 1
            tr["locked"] = float(locked)   # per rettificare dopo l'escalation
            self._emit("exit", sel=sel, kind=kind, locked=round(locked,3))
            self._cancel(market, tr.get("order"))
            # NON si abbandona la posizione: stato closing finché il blotter è flat
            tr["closing"] = True
            tr["close_order"] = close_order
            tr["close_wait"] = 0
            tr["t_close"] = pt  # base dell'escalation in secondi (fix audit #10)
        return

    def process_market_book(self, market: Any, mb: Any) -> None:
        # l'orologio del bot e' quello del MERCATO: lo leggono il freno dei
        # rifiuti e ogni finestra temporale
        _pt = getattr(mb, "publish_time_epoch", None)
        if _pt is not None:
            self._now_ms = int(_pt)
        mid = mb.market_id
        if self.uscita_manuale_chiesta:
            # "CHIUDI ORA" dell'utente (D3, 24/09): si avvia l'uscita, poi la
            # gestione del trade e' quella di sempre (stato `closing`). Nessun
            # ingresso: il bot non rientra finche' l'utente non lo riarma.
            self._avvia_uscita_manuale(market, mb, mid)
            tr_m = self._tr.get(mid)
            if tr_m:
                self._manage_trade(market, mb, mid, tr_m)
            return
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
        med = statistics.median(base); mad = statistics.median([abs(x-med) for x in base])
        # FIX 16/07 (caso reale: entry LAY con z=-674.500.000): con book piatto
        # la MAD e' 0 e il vecchio fallback 1e-9 trasformava UN tick di
        # movimento in uno z astronomico → falso segnale garantito. Nessuna
        # dispersione = nessuno z-score sensato = NESSUN segnale.
        if mad <= 0:
            return
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
        # px (16/07): prezzo d'ingresso FLOAT — in dry e' la base della posizione
        # VIRTUALE (paper con esito: prima l'entry dry evaporava dopo 40s senza
        # exit ne' P&L → il paper non misurava nulla).
        self._tr[mid] = {"sel": sel, "side": side, "etk": tmid, "anchor": med,
                         "order": o, "held": 0, "wait": 0,
                         "px": float(get_nearest_price(entry_price) or 0.0),
                         "t0": getattr(mb, "publish_time_epoch", None)}
        self.stats["entries"] += 1
        self._emit("entry", sel=sel, side=side, z=round(z,2), price=entry_price)

    # ---------------------------------------------- "CHIUDI ORA" dell'utente
    def _avvia_uscita_manuale(self, market: Any, mb: Any, mid: str) -> None:
        """Esegue il "chiudi ora" UNA volta (D3, 24/09) con l'uscita dello SWING:
        la stessa `_close` di target/stop/time, al TOUCH (`bl` per chiudere un
        BACK, `bb` per un LAY: il prezzo che l'escalation usa gia'), calcolata
        da `compute_green` sull'ABBINATO del blotter; poi stato `closing`, che
        la gestione di sempre porta a posizione pari (`_puo_dimenticare`).

        * trade gia' `closing` -> "gia' in uscita", NESSUN secondo ordine;
        * nessun trade -> "nessuna posizione".
        Book monco o blotter non letto: si riprova al book dopo."""
        if self.uscita_manuale is not None:
            return
        tr = self._tr.get(mid)
        if not tr:
            registra_esito_manuale(self, ESITO_NESSUNA_POSIZIONE, market_id=str(mid))
            return
        if tr.get("closing"):
            registra_esito_manuale(self, ESITO_GIA_IN_USCITA, market_id=str(mid),
                                   sel=tr.get("sel"))
            return
        sel = int(tr.get("sel") or 0)
        r = self._runner_by_sel(mb, sel)
        ex = getattr(r, "ex", None) if r is not None else None
        bb = get_price(ex.available_to_back, 0) if ex is not None else None
        bl = get_price(ex.available_to_lay, 0) if ex is not None else None
        if not bb or not bl:
            return          # book monco: si riprova al prossimo book
        side = tr["side"]
        px = bl if side == "BACK" else bb       # TAKER al touch
        pt = getattr(mb, "publish_time_epoch", None)
        if self.dry_run:
            # posizione VIRTUALE come in `_manage_trade` (paper senza ordini)
            pe = float(tr.get("px") or 0.0)
            if pe > 1.0:
                if side == "BACK":
                    nw, nl = self.stake * (pe - 1.0), -self.stake
                else:
                    nw, nl = -self.stake * (pe - 1.0), self.stake
                g = compute_green(nw, nl, px)
                locked = float(g[2]) if g is not None else min(nw, nl)
                self.stats["pnl"] += locked
                self.stats["wins" if locked > 0 else "losses"] += 1
                self.stats["manuali"] += 1
                self._emit("exit", sel=sel, kind=MOTIVO_USCITA_MANUALE,
                           locked=round(locked, 3), dry=True)
            self._tr.pop(mid, None)
            registra_esito_manuale(self, ESITO_USCITA_AVVIATA, market_id=str(mid),
                                   sel=sel, prezzo=px, dry=True)
            return
        b, _ba, l, _la = self._pos(market, sel)
        if not self._blotter_letto:
            return          # esposizione non letta: non si chiude al buio
        locked, close_order = self._close(market, sel, px)
        self.stats["pnl"] += locked
        self.stats["wins" if locked > 0 else "losses"] += 1
        self.stats["manuali"] += 1
        tr["locked"] = float(locked)
        self._emit("exit", sel=sel, kind=MOTIVO_USCITA_MANUALE, locked=round(locked, 3))
        self._cancel(market, tr.get("order"))
        tr["closing"] = True
        tr["close_order"] = close_order
        tr["close_wait"] = 0
        tr["t_close"] = pt
        registra_esito_manuale(self, ESITO_USCITA_AVVIATA, market_id=str(mid),
                               sel=sel, prezzo=px, abbinato=round(b + l, 2))

    def uscita_manuale_finita(self) -> bool:
        """Finita per il BOT: esito scritto e nessun trade ancora in memoria (lo
        swing dimentica un trade SOLO a selezione pari e senza ordini vivi)."""
        if self.uscita_manuale is None:
            return False
        return not any(self._tr.values())

    def process_closed_market(self, market: Any, mb: Any) -> None:
        # DEDUP PER ORDINE (correzione 17/09, lo stesso fix del PRO e del FLB):
        # flumine puo' richiamare `process_closed_market` sullo stesso mercato e
        # senza dedup il P&L di settlement RADDOPPIA.
        # E il numero finisce in `stats`, non solo in un attributo privato:
        # prima `settled_pnl` viveva FUORI da `self.stats` e percio' non entrava
        # ne' nell'heartbeat ne' in nessuna tabella — il P&L regolato dello
        # swing era invisibile ovunque (referto d'audit, S6 e B6).
        self.settled_pnl = getattr(self, "settled_pnl", 0.0)
        try:
            for o in market.blotter.strategy_orders(self):
                oid = str(getattr(o, "id", "") or id(o))
                if oid in self._pnl_settled_oids:
                    continue
                self._pnl_settled_oids.add(oid)
                sim = getattr(o, "simulated", None)
                self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        except Exception: pass  # noqa
        self.stats["pnl_settled"] = round(float(self.settled_pnl), 3)
        # FASE DI SETTLEMENT: si dichiara cosa era aperto al fischio e si chiude
        # la memoria. Senza, una posizione creduta viva restava tale per sempre.
        mid = str(getattr(market, "market_id", "") or "")
        tr = self._tr.pop(mid, None)
        if tr is not None:
            dichiara_chiusura_mercato(market, self, self.event_sink,
                                      [tr.get("sel")], "tennis_swing")
