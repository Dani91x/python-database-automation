"""Strategia flumine per la simulazione (Backtest Automatico).

Una sola classe :class:`SimStrategy` con due modalita':

* ``engine``  — ad ogni ``process_market_book`` ricostruisce il ladder dal
  :class:`~betfairlightweight.resources.bettingresources.MarketBook`, recupera
  (e mette in cache) i lambda pre-match per l'evento e invoca
  :func:`Betfair.stream.engine.live_engine_pro.evaluate_event`. Per ogni segnale
  BACK/LAY con edge sufficiente piazza un ordine simulato tramite
  ``market.place_order``.
* ``sandbox`` — regole semplici e configurabili dai parametri della richiesta
  (``market_type``, ``side``, ``entry_minute``, ``entry_price_max``, ``stake``,
  ``selection_id``): piazza un ordine quando le condizioni sono soddisfatte.

Il settlement (profit/perdita) e' interamente delegato a flumine: in
``process_closed_market`` raccogliamo gli ordini gia' regolati dal blotter
(flumine ha popolato ``runner_status`` prima di chiamare la strategia).

NOTE / LIMITI (replay puramente sul file di mercato nativo):

* Il punteggio live NON e' contenuto nel file ``.raw.jsonl`` di mercato. Se
  accanto e' presente ``<event>.scores.jsonl`` (scritto dal runner live) lo
  usiamo per allineare ``score``/``minute`` al ``publish_time``; altrimenti la
  modalita' engine usa 0-0 e ``minute=None`` (equivale a "match pieno residuo").
* I nomi delle selezioni non sono nello stream: se manca un catalogo sidecar i
  nomi vengono sintetizzati per ``sort_priority`` (convenzione Betfair calcio).
"""
from __future__ import annotations

import logging
from bisect import bisect_right
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy
from flumine.order.ordertype import LimitOrder
from flumine.order.trade import Trade

from ..engine.live_engine_pro import (
    evaluate_event,
    get_prematch_lambdas,
    total_goals_from_ou,
)

logger = logging.getLogger(__name__)

# stake minimo Betfair / minimo accettato dal client simulato
MIN_STAKE: float = 2.0


def _offer_price(offer: Any) -> Optional[float]:
    """Estrae il prezzo da un livello del ladder.

    flumine, in simulazione, espone ``available_to_back/lay`` come dict
    ``{"price":, "size":}``; betfairlightweight (live) come ``PriceSize``
    (.price/.size); il formato nativo grezzo come ``[price, size]``.
    """
    if offer is None:
        return None
    if isinstance(offer, dict):
        p = offer.get("price")
    elif isinstance(offer, (list, tuple)):
        p = offer[0] if offer else None
    else:
        p = getattr(offer, "price", None)
    return float(p) if p is not None else None


def _offer_size(offer: Any) -> Optional[float]:
    if offer is None:
        return None
    if isinstance(offer, dict):
        s = offer.get("size")
    elif isinstance(offer, (list, tuple)):
        s = offer[1] if len(offer) > 1 else None
    else:
        s = getattr(offer, "size", None)
    return float(s) if s is not None else None


def _synth_name(market_type: Optional[str], sort_priority: Optional[int]) -> Optional[str]:
    """Sintetizza un nome selezione dal ``sort_priority`` (convenzione Betfair).

    Usato SOLO se manca un catalogo con i nomi reali. Heuristica calcio:
      * MATCH_ODDS:           1 -> Home, 2 -> Away, 3 -> The Draw
      * OVER_UNDER_x:         1 -> Under, 2 -> Over
      * BOTH_TEAMS_TO_SCORE:  1 -> Yes, 2 -> No
    """
    if sort_priority is None:
        return None
    mt = (market_type or "").upper()
    if mt == "MATCH_ODDS":
        return {1: "Home", 2: "Away", 3: "The Draw"}.get(int(sort_priority))
    if "OVER_UNDER" in mt:
        return {1: "Under", 2: "Over"}.get(int(sort_priority))
    if "BOTH_TEAMS_TO_SCORE" in mt or mt == "BTTS":
        return {1: "Yes", 2: "No"}.get(int(sort_priority))
    return None


class SimStrategy(BaseStrategy):
    """Strategia di simulazione (engine | sandbox)."""

    def __init__(
        self,
        *,
        params: Dict[str, Any],
        event_id: str,
        scores: Optional[List[Tuple[int, Optional[int], int, int]]] = None,
        catalogue: Optional[Dict[str, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        self.params: Dict[str, Any] = params or {}
        self.event_id: str = str(event_id)
        self.mode: str = str(self.params.get("mode", "engine")).lower()
        self.bankroll: float = float(self.params.get("bankroll", 100.0))
        self.min_edge: float = float(self.params.get("min_edge", 0.03))
        self.kelly_fraction: float = float(self.params.get("kelly_fraction", 0.25))
        self.rules: Dict[str, Any] = dict(self.params.get("rules") or {})
        # parametri di ESECUZIONE (realismo flumine): tipo di persistenza degli
        # ordini non matchati a fine mercato. LAPSE = annulla l'inmatchato (default
        # Betfair), PERSIST = lo porta in-play, MARKET_ON_CLOSE = SP a chiusura.
        self.persistence_type: str = str(
            self.params.get("persistence_type") or "LAPSE"
        ).upper()

        # scores ordinati per ts_ms: lista di (ts_ms, minute, score_home, score_away)
        self._scores: List[Tuple[int, Optional[int], int, int]] = sorted(
            scores or [], key=lambda x: x[0]
        )
        self._score_ts: List[int] = [s[0] for s in self._scores]
        # catalogo opzionale: market_id -> {market_type, selections:[{selection_id,name,sort_priority}]}
        self._catalogue: Dict[str, Dict[str, Any]] = catalogue or {}

        # anti-replay: (market_id, selection_id, side) gia' piazzati
        self._placed: set = set()
        # lambda pre-match per evento (cache)
        self._lambdas: Optional[Tuple[float, float, Optional[int]]] = None
        # cache ultimi book/struct per stimare il TOTALE gol dal mercato O/U (data-driven)
        self._latest_ladder: Dict[str, Any] = {}
        self._latest_struct: Dict[str, Any] = {}
        # ordini regolati raccolti alla chiusura mercato, DEDUPLICATI per order.id:
        # {order_id: (order, market_type)}
        self._settled_by_id: Dict[str, Tuple[Any, str]] = {}

        super().__init__(**kwargs)

    @property
    def settled_orders(self) -> List[Tuple[Any, str]]:
        """Ordini regolati UNICI (deduplicati per ``order.id``).

        ``process_closed_market`` puo' essere invocato decine di migliaia di volte
        per lo stesso mercato durante il replay del raw Betfair (chiusure/market
        definition ri-emesse di continuo). Senza dedup ogni ordine verrebbe
        conteggiato ~10^4 volte, gonfiando P&L/stake dello stesso fattore. La
        dedup per ``id`` garantisce un solo settlement per ordine.
        """
        return list(self._settled_by_id.values())

    # ------------------------------------------------------------------ utils
    def _score_at(self, pt_ms: Optional[int]) -> Tuple[int, int, Optional[int]]:
        """Punteggio/minuto allineati al publish_time (ultimo score <= pt)."""
        if not self._scores or pt_ms is None:
            return 0, 0, None
        idx = bisect_right(self._score_ts, int(pt_ms)) - 1
        if idx < 0:
            return 0, 0, None
        _, minute, sh, sa = self._scores[idx]
        return int(sh), int(sa), (int(minute) if minute is not None else None)

    @staticmethod
    def _ladder_for_book(market_book: Any) -> Dict[str, Dict[str, Any]]:
        """MarketBook -> {selection_id(str): {back,lay,ltp,tv}} (formato motore)."""
        out: Dict[str, Dict[str, Any]] = {}
        for r in getattr(market_book, "runners", None) or []:
            ex = getattr(r, "ex", None)
            atb = (ex.available_to_back if ex else None) or []
            atl = (ex.available_to_lay if ex else None) or []
            back = [[_offer_price(o), _offer_size(o)] for o in atb]
            lay = [[_offer_price(o), _offer_size(o)] for o in atl]
            out[str(r.selection_id)] = {
                "back": back,
                "lay": lay,
                "ltp": getattr(r, "last_price_traded", None),
                "tv": getattr(r, "total_matched", None),
            }
        return out

    def _market_struct(self, market: Any, market_book: Any) -> Dict[str, Any]:
        """Struttura mercato per il motore (market_type + selezioni con nome)."""
        mid = market_book.market_id
        cat = self._catalogue.get(mid)
        if cat:
            return cat
        md = getattr(market_book, "market_definition", None)
        mtype = getattr(md, "market_type", None) or getattr(market, "market_type", None)
        sels: List[Dict[str, Any]] = []
        for rd in getattr(md, "runners", None) or []:
            sid = getattr(rd, "selection_id", None)
            if sid is None:
                continue
            sp = getattr(rd, "sort_priority", None)
            name = getattr(rd, "name", None) or _synth_name(mtype, sp)
            sels.append(
                {"selection_id": int(sid), "name": name, "sort_priority": sp}
            )
        return {"market_id": mid, "market_type": mtype, "selections": sels}

    def _place(
        self, market: Any, selection_id: int, side: str, price: float, size: float
    ) -> None:
        trade = Trade(
            market_id=market.market_id,
            selection_id=int(selection_id),
            handicap=0.0,
            strategy=self,
        )
        order = trade.create_order(
            side=side,
            order_type=LimitOrder(
                price=float(price),
                size=round(float(size), 2),
                persistence_type=self.persistence_type,
            ),
        )
        market.place_order(order)

    # ------------------------------------------------------------ flumine hook
    def check_market_book(self, market: Any, market_book: Any) -> bool:
        # processa solo mercati aperti con runner presenti
        return (
            getattr(market_book, "status", None) == "OPEN"
            and bool(getattr(market_book, "runners", None))
        )

    def process_market_book(self, market: Any, market_book: Any) -> None:
        if self.mode == "sandbox":
            self._process_sandbox(market, market_book)
        else:
            self._process_engine(market, market_book)

    def process_closed_market(self, market: Any, market_book: Any) -> None:
        """Raccoglie gli ordini gia' regolati da flumine (settlement automatico)."""
        md = getattr(market_book, "market_definition", None)
        mtype = (
            getattr(md, "market_type", None)
            or getattr(market, "market_type", None)
            or "UNKNOWN"
        )
        try:
            orders = market.blotter.strategy_orders(self)
        except Exception:  # noqa: BLE001 - blotter puo' non avere ordini
            orders = []
        for order in orders:
            oid = getattr(order, "id", None) or id(order)
            self._settled_by_id[oid] = (order, mtype)

    # --------------------------------------------------------------- engine
    def _process_engine(self, market: Any, market_book: Any) -> None:
        mid = market_book.market_id
        ladder = {mid: self._ladder_for_book(market_book)}
        mstruct = self._market_struct(market, market_book)
        mtype = (mstruct.get("market_type") or "").upper()
        # cache per stimare il totale gol atteso dal mercato O/U (data-driven, no 2.6)
        self._latest_ladder[mid] = ladder[mid]
        self._latest_struct[mid] = {**mstruct, "market_id": mid}

        if self._lambdas is not None:
            lam = self._lambdas
        elif mtype == "MATCH_ODDS":
            # totale gol DATA-DRIVEN dal mercato O/U; split dal 1X2. Cache SOLO quando
            # il totale viene da dati reali (O/U disponibile) → niente lock sul 2.6.
            total = total_goals_from_ou(list(self._latest_struct.values()), self._latest_ladder)
            lh, la, league = get_prematch_lambdas(
                self.event_id, None,
                match_odds_market=mstruct, ladder=ladder[mid],
                expected_total_goals=total,
            )
            lam = (lh, la, league)
            if total is not None:
                self._lambdas = lam
        else:
            # transitorio finche' non arriva un MATCH_ODDS
            lam = get_prematch_lambdas(self.event_id, None)

        sh, sa, minute = self._score_at(getattr(market_book, "publish_time_epoch", None))

        signals = evaluate_event(
            score_home=sh,
            score_away=sa,
            minute=minute,
            prematch_lambda_home=lam[0],
            prematch_lambda_away=lam[1],
            league_id=lam[2],
            markets=[mstruct],
            ladder_by_market=ladder,
            bankroll=self.bankroll,
            min_edge=self.min_edge,
            kelly_fraction=self.kelly_fraction,
        )

        for s in signals:
            if s.direction not in ("BACK", "LAY"):
                continue
            key = (s.market_id, int(s.selection_id), s.direction)
            if key in self._placed:
                continue
            price = s.market_back if s.direction == "BACK" else s.market_lay
            if not price:
                continue
            if s.kelly_stake <= 0:
                continue
            size = max(MIN_STAKE, round(float(s.kelly_stake), 2))
            self._place(market, s.selection_id, s.direction, price, size)
            self._placed.add(key)

    # -------------------------------------------------------------- sandbox
    def _process_sandbox(self, market: Any, market_book: Any) -> None:
        r = self.rules
        # accetta sia "market_type" (canonico) sia "market" (alias dalla UI)
        want_mtype = (r.get("market_type") or r.get("market") or "").upper()
        md = getattr(market_book, "market_definition", None)
        mtype = (
            getattr(md, "market_type", None)
            or getattr(market, "market_type", None)
            or ""
        ).upper()
        if want_mtype and mtype != want_mtype:
            return

        _, _, minute = self._score_at(getattr(market_book, "publish_time_epoch", None))
        entry_minute = r.get("entry_minute")
        if entry_minute is not None and (minute is None or minute < int(entry_minute)):
            return

        side = (r.get("side") or "BACK").upper()
        stake = max(MIN_STAKE, float(r.get("stake", MIN_STAKE)))
        price_max = r.get("entry_price_max")
        target_sel = r.get("selection_id")

        for rb in getattr(market_book, "runners", None) or []:
            sid = rb.selection_id
            if target_sel is not None and int(sid) != int(target_sel):
                continue
            key = (market_book.market_id, int(sid), side)
            if key in self._placed:
                continue
            ex = getattr(rb, "ex", None)
            offers = (ex.available_to_back if side == "BACK" else ex.available_to_lay) if ex else []
            if not offers:
                continue
            price = _offer_price(offers[0])
            if price is None:
                continue
            if price_max is not None and price > float(price_max):
                continue
            self._place(market, sid, side, price, stake)
            self._placed.add(key)
