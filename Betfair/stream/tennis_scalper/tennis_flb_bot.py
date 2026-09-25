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
    size_legale,
    stato_ordine,
)
from .tennis_scalper_bot import compute_green, ticks_between

logger = logging.getLogger(__name__)
MIN_STAKE = 2.0
_EPS = 1e-9

# stati per (market_id, selection_id)
IDLE, PENDING, OPEN, DONE = "IDLE", "PENDING", "OPEN", "DONE"


class TennisFLBStrategy(BaseStrategy):
    """Lay del favorito estremo, no stop (favourite-longshot bias)."""

    #: 25/09 - uscite automatiche (green sullo swing). Lo imposta il runner
    #: tennis dalla riga per partita; di classe = False (DEFAULT dal 25/09
    #: sera, ordine dell'utente: «di default tutte le uscite le voglio spente»).
    uscite_automatiche: bool = False

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
        # ESECUZIONE MAKER (decisione 17/09, dossier §4.3 «Esecuzione MAKER»).
        # Il dossier dichiara MAKER ma indicava «rest al best-lay», che e' il
        # prezzo del TAKER: un LAY a `available_to_lay[0]` incrocia lo spread e
        # si abbina subito, alla quota PIU' ALTA, cioe' alla liability massima.
        # La contraddizione si risolve nel senso del documento (MAKER) e con la
        # convenzione gia' in casa: il LAY maker sta al BEST-BACK
        # (`tennis_scalper_bot.py`, ramo join). Effetto misurato: in backtest
        # (`simulation_available_prices=False`) un ordine che incrocia non
        # incrocia mai e resta in coda, mentre in LIVE si riempie all'istante —
        # ingressi, prezzo medio e `entry_timeout` avevano significato OPPOSTO
        # nei due mondi (referto d'audit 17/09 §I.1). `maker=False` rimette il
        # taker, per chi voglia misurare la differenza.
        self.maker: bool = bool(c.get("maker", True))
        # LIVE: le size vanno legalizzate per la giurisdizione (.it), altrimenti
        # Betfair rifiuta e la gamba resta scoperta. Lo decide il runner:
        # `live_min_bet` > 0 solo in LIVE (`tennis_runner._instantiate_bot`).
        self.live: bool = float(c.get("live_min_bet", 0.0) or 0.0) > 0.0

        # stato runtime
        self._pos_state: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._armed: Dict[Tuple[str, int], bool] = {}
        # freno dopo i rifiuti di Betfair (condiviso coi quattro bot)
        self._freno = FrenoRifiuti()
        # D2 (24/09): il diario delle attese di riapertura (una riga per sospensione)
        self._attese = AttesaRiapertura()
        self._now_ms: Optional[int] = None
        self.stats: Dict[str, Any] = {"entries": 0, "greens": 0, "held": 0,
                                      "manuali": 0, "pnl": 0.0}
        # "CHIUDI ORA" (D3, 24/09): il runner alza la richiesta, il bot chiude
        # con la SUA copertura di green (`_green`, frazione intera) e non apre
        # piu' niente (`condotta_ordini` sezione 4).
        self.uscita_manuale_chiesta: bool = False
        self.uscita_manuale: Optional[Dict[str, Any]] = None
        self.settled_pnl: float = 0.0
        # gli ordini gia' contati nel settlement: `process_closed_market` puo'
        # essere richiamato piu' volte sullo stesso mercato (vedi la nota li').
        self._pnl_settled_oids: set = set()

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
               size: float, *, copertura: bool = False) -> Optional[Any]:
        size = round(max(0.0, float(size)), 2)
        if price is None or price <= 1.0 or size < 0.01 or self.dry_run:
            if self.dry_run:
                self._emit("dry_place", sel=sel, side=side, price=price, size=size)
            return None
        # SIZE LEGALE DI GIURISDIZIONE (.it): un ordine sotto il minimo o non
        # multiplo di 0,50 viene RIFIUTATO da Betfair e la gamba resta scoperta.
        # Le coperture si bumpano (meglio un over-hedge di pochi centesimi che
        # una posizione nuda), gli ingressi no (non si gonfia lo stake acceso).
        legale, motivo = size_legale(size, side, live=self.live,
                                     riduce_liability=copertura)
        if legale is None:
            self._emit("size_non_legale", sel=sel, side=side, price=price,
                       size=size, copertura=copertura, motivo=motivo)
            logger.warning("[FLB] size non legale sel=%s %s %s: %s",
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
        # FRENO DOPO I RIFIUTI: non tocca le coperture (una copertura deve poter
        # partire sempre), solo le aperture.
        if not copertura:
            fermo = self._freno.bloccato(market.market_id, sel, self._orologio_s())
            if fermo:
                # il motivo si scrive UNA volta per rifiuto, non a ogni tentativo
                if self._freno.da_annunciare(market.market_id, sel):
                    self._emit("freno_rifiuti", sel=sel, side=side, motivo=fermo)
                return None
        try:
            tr = Trade(market_id=market.market_id, selection_id=int(sel),
                       handicap=0, strategy=self)
            o = tr.create_order(side=side, order_type=LimitOrder(
                price=float(price), size=size, persistence_type="LAPSE"))
            # L'ESITO DEL PIAZZAMENTO SI LEGGE (catalogo §7 difetto 2, «`res.ok`
            # mai letto»). `Market.place_order` torna un BOOL: `False` significa
            # che un trading control ha bocciato l'ordine, che NON e' mai entrato
            # nel blotter e che il suo stato e' `OrderStatus.VIOLATION`
            # (`flumine/execution/transaction.py:67-75`). Trattarlo come piazzato
            # lasciava il bot a sorvegliare per 40 s un ordine inesistente, e la
            # posizione risultava OPEN senza niente a mercato (provato dal
            # replay: scenario `rifiuti-betfair`, K1/K2/K4 rossi).
            if not market.place_order(o):
                n, attesa = self._freno.registra_rifiuto(
                    market.market_id, sel, self._orologio_s())
                self._emit("place_rejected", sel=sel, side=side, price=price,
                           size=size, rifiuti=n, riprovo_fra_s=attesa,
                           motivo=str(getattr(o, "violation_msg", "") or "rifiutato"))
                logger.warning("[FLB] piazzamento RIFIUTATO sel=%s %s @%s per %s "
                               "(%d-esimo, riprovo fra %.0fs): %s",
                               sel, side, price, size, n, attesa,
                               getattr(o, "violation_msg", None))
                return None
            self._freno.registra_successo(market.market_id, sel)
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
        # COPERTURA: passa il freno rifiuti e puo' essere bumpata al minimo .it
        o = self._place(market, sel, gside, p, size, copertura=True)
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

    def _orologio_s(self) -> float:
        """L'ora del BOT, in secondi: il `publish_time` dell'ultimo book.

        Il freno dei rifiuti conta il tempo DI MERCATO, non quello del muro: e'
        l'unico modo perche' replay, paper e live si comportino allo stesso modo
        (stessa correzione gia' fatta al tetto transazioni dello scalper)."""
        if self._now_ms is not None:
            return float(self._now_ms) / 1000.0
        import time as _t

        return _t.time()

    # -------------------------------------------------------------- main loop
    def process_market_book(self, market: Any, mb: Any) -> None:
        pt0 = getattr(mb, "publish_time_epoch", None)
        if pt0 is not None:
            self._now_ms = int(pt0)
        if self.uscita_manuale_chiesta:
            # "CHIUDI ORA" dell'utente (D3, 24/09): da qui il bot solo CHIUDE
            # (nessun gate di liquidita': la chiusura non si ferma mai) e non
            # rientra finche' l'utente non lo riarma.
            self._uscita_manuale(market, mb)
            return
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

            # INGRESSO: laya il favorito estremo (best-lay <= soglia).
            # LA CONDIZIONE resta quella del dossier (`best-lay <= lay_max`):
            # decide QUANDO. Il PREZZO lo decide `maker`: appoggiato al
            # best-back (non incrocia, liability piu' piccola, coda) oppure al
            # best-lay (taker, si abbina subito). Vedi la nota su `self.maker`.
            if bl <= self.lay_max and (sl or 0) >= self.min_lay_size:
                entry = get_nearest_price(bb if self.maker else bl)
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
        if st.get("state") == PENDING:
            # ⚠️ CANCEL IN VOLO. `market.cancel_order` e' ASINCRONA: l'ordine
            # passa per `Cancelling` prima di morire, e in quella finestra puo'
            # ancora riempirsi. Dichiarare DONE subito dopo il cancel lasciava
            # un ordine VIVO sul book sotto una posizione «chiusa» (misurato sul
            # replay del 17/09, 35790089: K6, 2,00 EUR ancora `Cancelling`).
            if (b + l) > _EPS:
                # si e' riempito lo stesso: e' una posizione vera, si gestisce
                # come tutte le altre (uscite del dossier §4.3)
                st["state"] = OPEN
                self._emit("cancel_perso", sel=sel, abbinato=round(b + l, 2),
                           note=("l'ingresso si e' riempito mentre il cancel era "
                                 "in volo: la posizione e' vera e si gestisce"))
            elif ordini_vivi_su(market, self, sel) is False:
                # cancel CONFERMATO e nessun altro ordine vivo sulla selezione
                self._pos_state[key] = {"state": DONE}
                return
            else:
                return      # cancel non ancora confermato: si aspetta
        if (b + l) <= _EPS:
            # ⚠️ L'INGRESSO PUO' ESSERE GIA' MORTO: con `persistence_type=LAPSE`
            # Betfair uccide l'appoggiato a ogni SOSPENSIONE (in tennis: a ogni
            # punto). Prima il bot aspettava 40 s una quota che a mercato non
            # esisteva piu'. Si legge lo stato VERO (Enum `.value`).
            if ingresso_finito(st.get("order")):
                self._pos_state[key] = {"state": DONE}
                self._emit("entry_scaduta", sel=sel,
                           stato=stato_ordine(st.get("order")),
                           note=("l'ordine d'ingresso non esiste piu' a mercato: "
                                 "non aspetto il timeout"))
                return
            # entry LAY non ancora riempita: timeout in SECONDI di publish_time
            # (fallback al conteggio update SOLO se il publish_time manca).
            st["wait"] = int(st.get("wait", 0)) + 1
            t0 = st.get("t0")
            timed_out = (
                pt is not None and t0 is not None
                and (pt - t0) / 1000.0 >= self.entry_timeout
            ) or ((pt is None or t0 is None) and st["wait"] > self.entry_timeout)
            if timed_out:
                # il cancel e' ASINCRONO: si passa in PENDING e si dichiara DONE
                # solo quando l'ordine non e' piu' vivo sul book (vedi sopra).
                self._cancel(market, st.get("order"))
                st["state"] = PENDING
                self._emit("entry_timeout", sel=sel,
                           note=("ingresso scaduto: cancel chiesto, aspetto la "
                                 "conferma prima di dichiarare chiuso"))
            return

        # --- sorveglianza dell'HEDGE di green (fix 2026-07-10: prima non era
        # tracciato: greened=True fisso anche con hedge lapsed = scoperti) ---
        if st.get("greened") and not st.get("green_locked"):
            go = st.get("green_order")
            if go is None:
                # ⚠️ NESSUN ORDINE DI HEDGE. Sono due casi diversissimi e prima
                # erano confusi in uno solo (correzione 17/09):
                #   * posizione GIA' PARI (o dry-run): non c'era niente da
                #     coprire, il green e' davvero concluso;
                #   * l'hedge NON E' PARTITO (rifiutato, sotto il minimo,
                #     eccezione): la posizione e' ancora SBILANCIATA e contare
                #     un green e' una cifra inventata nel pannello — lo stesso
                #     difetto 3 del 15/09 in forma nuova.
                # Si distingue guardando il netto VERO dal blotter.
                if not self.dry_run:
                    nw_, nl_ = self._net(*self._matched(market, sel))
                    if abs(nw_ - nl_) > 0.01:
                        st["greened"] = False       # si riprova al prossimo book
                        self._emit("green_fallito", sel=sel,
                                   sbilancio=round(abs(nw_ - nl_), 3),
                                   note=("l'ordine di copertura non e' partito: "
                                         "nessun green contato, la posizione e' "
                                         "ancora aperta"))
                        return
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
                o2 = self._place(market, sel, gside, get_nearest_price(px), rem,
                                 copertura=True)
                if o2 is not None:
                    st["green_order"] = o2
                    self._emit("green_replaced", sel=sel, side=gside,
                               size=round(rem, 2), price=px)
            return

        entry = st["entry"]
        # green-up sullo swing: la quota (best-back per chiudere un lay) e' RISALITA
        up = ticks_between(entry, bb) if bb > entry else 0
        # 25/09 USCITE MANUALI: il green sullo swing e' una presa di profitto,
        # a interruttore spento non scatta (come exit_mode "hold"). Il FLB non
        # ha stop per progetto: restano chiudi-ora e fine mercato.
        if self.exit_mode in ("green", "hybrid") and not st["greened"] \
                and self.uscite_automatiche \
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

    # ---------------------------------------------- "CHIUDI ORA" dell'utente
    def _gia_in_uscita(self, st: Dict[str, Any]) -> bool:
        """La posizione sta GIA' uscendo: ingresso in annullo (PENDING) oppure
        copertura di green INTERA gia' in volo. In entrambi i casi un secondo
        ordine sarebbe una doppia uscita."""
        if st.get("state") == PENDING:
            return True
        return bool(st.get("greened") and not st.get("green_locked")
                    and float(st.get("green_fr") or 0.0) >= 1.0
                    and self._order_alive(st.get("green_order")))

    def _uscita_manuale(self, market: Any, mb: Any) -> None:
        """Il "chiudi ora" (D3, 24/09) sulle posizioni del FLB, con la SUA
        copertura di green (`_green`, frazione 1: tutto l'ABBINATO).

        L'esito si scrive UNA volta al primo book: "nessuna posizione", "gia' in
        uscita" (ogni posizione aperta sta gia' uscendo: nessun secondo ordine)
        o "uscita avviata". Poi, per ogni selezione ancora PENDING/OPEN:
        annullo dell'ingresso e di una copertura PARZIALE (hybrid), attesa che
        sul book non resti niente di vivo, e SOLO allora la copertura intera
        dell'abbinato al touch (`bb` per chiudere un lay, `bl` per un back)."""
        mid = str(getattr(mb, "market_id", "") or "")
        vive = {k: st for k, st in self._pos_state.items()
                if k[0] == mid and st.get("state") in (PENDING, OPEN)}
        if self.uscita_manuale is None:
            if not vive:
                registra_esito_manuale(self, ESITO_NESSUNA_POSIZIONE, market_id=mid)
            elif all(self._gia_in_uscita(st) for st in vive.values()):
                registra_esito_manuale(self, ESITO_GIA_IN_USCITA, market_id=mid,
                                       selezioni=sorted(k[1] for k in vive))
            else:
                registra_esito_manuale(self, ESITO_USCITA_AVVIATA, market_id=mid,
                                       selezioni=sorted(k[1] for k in vive))
        for r in mb.runners:
            sel = int(getattr(r, "selection_id", 0) or 0)
            key = (mid, sel)
            st = self._pos_state.get(key)
            if not st or st.get("state") not in (PENDING, OPEN):
                continue
            ex = getattr(r, "ex", None)
            bb = get_price(ex.available_to_back, 0) if ex is not None else None
            bl = get_price(ex.available_to_lay, 0) if ex is not None else None
            self._chiudi_selezione_manuale(market, sel, key, st, bb, bl)

    def _chiudi_selezione_manuale(self, market: Any, sel: int, key: Tuple[str, int],
                                  st: Dict[str, Any], bb: Optional[float],
                                  bl: Optional[float]) -> None:
        if not st.get("manuale"):
            st["manuale"] = True
            # la copertura INTERA gia' in volo E' l'uscita: si tiene
            if self._gia_in_uscita(st) and st.get("state") == OPEN:
                st["ordine_manuale"] = st.get("green_order")
        # tutto cio' che non e' la copertura dell'uscita si annulla: il residuo
        # dell'ingresso e una copertura PARZIALE (hybrid)
        self._cancel(market, st.get("order"))
        go = st.get("green_order")
        if go is not None and go is not st.get("ordine_manuale"):
            self._cancel(market, go)
        # ANTI DOPPIA USCITA: finche' un ordine del bot e' vivo sulla selezione
        # (compresa la copertura in volo, o un annullo non ancora confermato:
        # `cancel_order` e' asincrona) non si piazza niente. Blotter illeggibile
        # (`None`) = non si decide.
        if ordini_vivi_su(market, self, sel) is not False:
            return
        b, ba, l, la = self._matched(market, sel)
        nw, nl = self._net(b, ba, l, la)
        if abs(nw - nl) <= 0.01:
            self._pos_state[key] = {"state": DONE, "manuale": True}
            self._emit("uscita_manuale_flat", sel=sel, abbinato=round(b + l, 2),
                       note="selezione pari e nessun ordine vivo: chiusa")
            return
        lato = "LAY" if nw > nl else "BACK"
        px = bl if lato == "LAY" else bb
        if not px:
            return          # book monco: si riprova al prossimo book
        locked, o = self._green(market, sel, px, 1.0)
        if o is None:
            return          # non partita: si riprova al prossimo book
        st["ordine_manuale"] = o
        st["green_order"] = o
        st["greened"] = True
        st["green_locked"] = False
        st["green_price"] = px
        st["green_fr"] = 1.0
        st["green_est"] = round(float(locked), 3)
        if not st.get("manuale_contato"):
            st["manuale_contato"] = True
            self.stats["manuali"] += 1
        self._emit("exit", sel=sel, kind=MOTIVO_USCITA_MANUALE, price=px,
                   locked_est=round(float(locked), 3))

    def uscita_manuale_finita(self) -> bool:
        """Finita per il BOT: esito scritto e nessuna selezione PENDING/OPEN."""
        if self.uscita_manuale is None:
            return False
        return all(st.get("state") not in (PENDING, OPEN)
                   for st in self._pos_state.values())

    def process_closed_market(self, market: Any, mb: Any) -> None:
        # P&L VERO: profitto del settlement simulato (include hold-to-end).
        # DEDUP PER ORDINE (correzione 17/09, lo stesso fix che il PRO ha gia'
        # a `tennis_pro_bot.py:757-761`): flumine puo' richiamare
        # `process_closed_market` sullo stesso mercato — il book CLOSED puo'
        # arrivare piu' di una volta nello stream — e senza dedup `settled_pnl`
        # e `stats["pnl"]` si RADDOPPIAVANO. E' il numero che finisce nel
        # pannello e nello storico: doveva essere contato una volta sola.
        try:
            for o in market.blotter.strategy_orders(self):
                oid = str(getattr(o, "id", "") or id(o))
                if oid in self._pnl_settled_oids:
                    continue
                self._pnl_settled_oids.add(oid)
                sim = getattr(o, "simulated", None)
                self.settled_pnl += float(getattr(sim, "profit", 0.0) or 0.0)
        except Exception:  # noqa: BLE001
            pass
        self.stats["pnl"] = round(self.settled_pnl, 3)
        # FASE DI SETTLEMENT (17/09): a mercato CHIUSO il bot non riceve piu'
        # book, quindi una posizione ancora creduta aperta resterebbe tale per
        # sempre. Si dichiara che cosa c'era al fischio e si chiude la memoria.
        mid = str(getattr(market, "market_id", "") or "")
        aperte = [sel for (m, sel), st in list(self._pos_state.items())
                  if m == mid and str(st.get("state") or "") in (PENDING, OPEN)]
        for chiave in [k for k in self._pos_state if k[0] == mid]:
            self._pos_state.pop(chiave, None)
            self._armed.pop(chiave, None)
        dichiara_chiusura_mercato(market, self, self.event_sink, aperte,
                                  "tennis_flb")
