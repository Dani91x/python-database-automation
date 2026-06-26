"""Recorder: strategia flumine che registra i MarketBook in JSONL locale.

Il file locale per-evento è la SOURCE OF TRUTH (resiste ai crash). Il curator lo
rilegge a fine partita per produrre gli snapshot curati su Supabase.

serialize_book() è una funzione PURA (testabile senza rete): MarketBook → dict
compatto { market_id, pt, status, inplay, tv, runners:{sel_id:{b,l,ltp,tv}} }.

La strategia mantiene anche una cache in-memory dell'ultimo book per mercato,
letta dal worker punteggio per aggiornare live_now (live glance).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import TYPE_CHECKING, Any, Dict, List

from betfairlightweight.resources.bettingresources import MarketBook
from flumine import BaseStrategy
from flumine.markets.market import Market

if TYPE_CHECKING:
    from flumine import Flumine

logger = logging.getLogger(__name__)


def _price_sizes(level_list: Any, depth: int) -> List[List[float]]:
    """Converte una lista di PriceSize in [[price, size], ...] limitata a `depth`."""
    out: List[List[float]] = []
    if not level_list:
        return out
    for ps in level_list[:depth]:
        price = getattr(ps, "price", None)
        size = getattr(ps, "size", None)
        if price is None and isinstance(ps, dict):  # tolleranza forma dict
            price, size = ps.get("price"), ps.get("size")
        if price is not None:
            out.append([float(price), float(size or 0.0)])
    return out


def serialize_book(market_book: Any, depth: int = 3) -> Dict[str, Any]:
    """MarketBook betfairlightweight → dict compatto serializzabile."""
    runners: Dict[str, Any] = {}
    for r in getattr(market_book, "runners", []) or []:
        ex = getattr(r, "ex", None)
        back = _price_sizes(getattr(ex, "available_to_back", None), depth) if ex else []
        lay = _price_sizes(getattr(ex, "available_to_lay", None), depth) if ex else []
        runners[str(r.selection_id)] = {
            "b": back,
            "l": lay,
            "ltp": getattr(r, "last_price_traded", None),
            "tv": getattr(r, "total_matched", None),
        }
    return {
        "market_id": market_book.market_id,
        "pt": getattr(market_book, "publish_time_epoch", None),
        "status": getattr(market_book, "status", None),
        "inplay": bool(getattr(market_book, "inplay", False)),
        "tv": getattr(market_book, "total_matched", None),
        "runners": runners,
    }


class MarketRecorderStrategy(BaseStrategy):
    """Registra ogni MarketBook su file JSONL per-evento + cache live.

    context richiesto:
      data_dir        : str  — cartella radice dei file grezzi
      market_to_event : dict — {market_id: event_id}
      depth           : int  — livelli di ladder da conservare
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lock = threading.Lock()
        self._files: Dict[str, Any] = {}        # event_id -> file handle
        self._latest: Dict[str, Dict[str, Any]] = {}  # market_id -> serialized book
        self._counts: Dict[str, int] = {}       # event_id -> n righe scritte
        self._closed_markets: Dict[str, set] = {}   # event_id -> set(market_id chiusi)
        self._finished: set = set()             # eventi già segnalati come finiti
        self._finished_queue: List[str] = []    # eventi finiti da drenare (F4)

    # --- helpers -----------------------------------------------------------
    @property
    def data_dir(self) -> str:
        return self.context["data_dir"]

    @property
    def market_to_event(self) -> Dict[str, str]:
        return self.context["market_to_event"]

    @property
    def depth(self) -> int:
        return int(self.context.get("depth", 3))

    @property
    def market_type_by_id(self) -> Dict[str, str]:
        return self.context.get("market_type_by_id", {})

    @property
    def event_markets(self) -> Dict[str, set]:
        return self.context.get("event_markets", {})

    def drain_finished(self) -> List[str]:
        """Ritorna (e svuota) gli eventi finiti dall'ultima chiamata (F4)."""
        with self._lock:
            out = list(self._finished_queue)
            self._finished_queue.clear()
            return out

    def _file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.data_dir, event_id)
            os.makedirs(ev_dir, exist_ok=True)
            path = os.path.join(ev_dir, f"{event_id}.jsonl")
            fh = open(path, "a", encoding="utf-8")  # noqa: SIM115 - chiuso in finish()
            self._files[event_id] = fh
            logger.info("[recorder] apro file grezzo: %s", path)
        return fh

    def latest_books(self) -> Dict[str, Dict[str, Any]]:
        """Snapshot della cache in-memory (per il worker live)."""
        with self._lock:
            return dict(self._latest)

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def file_path_for(self, event_id: str) -> str:
        return os.path.join(self.data_dir, event_id, f"{event_id}.jsonl")

    # --- flumine hooks -----------------------------------------------------
    def check_market_book(self, market: Market, market_book: MarketBook) -> bool:
        # flumine esegue process_market_book SOLO se questo ritorna True.
        # Vogliamo processare ogni aggiornamento di ogni mercato seguito.
        return True

    def process_market_book(self, market: Market, market_book: MarketBook) -> None:
        event_id = self.market_to_event.get(market_book.market_id)
        if event_id is None:
            # mercato non atteso (subscription per eventId può portare extra): ignora
            return
        record = serialize_book(market_book, self.depth)
        line = json.dumps(record, separators=(",", ":"), default=str)
        with self._lock:
            fh = self._file_for(event_id)
            fh.write(line + "\n")
            fh.flush()
            self._latest[market_book.market_id] = record
            self._counts[event_id] = self._counts.get(event_id, 0) + 1

    def process_closed_market(self, market: Market, market_book: MarketBook) -> None:
        """Rileva la fine di una partita (F4): quando MATCH_ODDS chiude (o tutti i
        mercati dell'evento sono chiusi) accoda l'evento per il finalize."""
        mid = market_book.market_id
        event_id = self.market_to_event.get(mid)
        if event_id is None:
            return
        mkt_type = self.market_type_by_id.get(mid) or getattr(
            getattr(market_book, "market_definition", None), "market_type", None
        )
        with self._lock:
            self._closed_markets.setdefault(event_id, set()).add(mid)
            all_markets = self.event_markets.get(event_id, set())
            all_closed = bool(all_markets) and all_markets.issubset(self._closed_markets[event_id])
            is_match_odds = mkt_type == "MATCH_ODDS"
            if (is_match_odds or all_closed) and event_id not in self._finished:
                self._finished.add(event_id)
                self._finished_queue.append(event_id)
                logger.info(
                    "[recorder] partita finita event=%s (match_odds=%s all_closed=%s)",
                    event_id, is_match_odds, all_closed,
                )
        try:
            self.remove_market(market_book.market_id)
        except Exception:  # noqa: BLE001
            pass

    def finish(self, flumine: "Flumine") -> None:
        with self._lock:
            for fh in self._files.values():
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
            self._files.clear()
        logger.info("[recorder] file grezzi chiusi.")
