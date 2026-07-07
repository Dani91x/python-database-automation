"""Recorder MULTI-PARTITA tennis: registra N match live in un solo stream.

Obiettivo: campagna di registrazione MASSIVA. Sottoscrive tutti i MATCH_ODDS
tennis in-play (+ quelli che iniziano entro poche ore) SENZA gate di liquidita'
(la liquidita' arriva durante il match) e fa il tee del book NATIVO grezzo su
``<DIR>/<event>/<event>.raw.jsonl`` (replayabile da ``flb_backtest``), piu' il
punteggio sincronizzato su ``<event>/<event>.score.jsonl``.

Self-contained: NON tocca ``raw_listener`` / ``recorder`` condivisi col calcio.
Ha il proprio tee-listener con auto-routing per-evento (impara market->event dalla
``marketDefinition`` presente nello stream, cosi' cattura anche i match che vanno
in-play dopo l'avvio).

Uso:
  python -m Betfair.stream.tennis_scalper.record_multi --out C:/.../tennis_rec/20260707
  # opzioni: --start-within-hours 4  --max-markets 60  --score-interval 3
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from betfairlightweight import StreamListener, filters
from flumine import BaseStrategy, Flumine, clients
from flumine.streams.marketstream import MarketStream
from flumine.worker import BackgroundWorker

from ..auth import build_client, keep_alive
from .tennis_score import parse_tennis_scores

logger = logging.getLogger(__name__)
TENNIS = "2"


# --------------------------------------------------------------------------- #
#  Stato del tee raw (per-evento) — istanza dedicata, NON il singleton calcio  #
# --------------------------------------------------------------------------- #
class _MultiRawState:
    def __init__(self) -> None:
        self.dir: Optional[str] = None
        self.market_to_event: Dict[str, str] = {}
        self.enabled: bool = False
        self._files: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def configure(self, data_dir: str, market_to_event: Dict[str, str]) -> None:
        self.dir = data_dir
        self.market_to_event = market_to_event  # riferimento vivo
        self.enabled = True

    def _file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
            fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
            self._files[event_id] = fh
            logger.info("[raw] apro file nativo: %s", path)
        return fh

    def write_message(self, raw_data: str) -> None:
        if not self.enabled or not self.dir:
            return
        try:
            msg = json.loads(raw_data)
        except (ValueError, TypeError):
            return
        if msg.get("op") != "mcm":
            return
        mc = msg.get("mc")
        if not mc:
            return
        # auto-routing: impara market->event dalla marketDefinition (se presente)
        for change in mc:
            mid = change.get("id")
            mdef = change.get("marketDefinition") or {}
            ev = mdef.get("eventId")
            if mid and ev and mid not in self.market_to_event:
                self.market_to_event[mid] = str(ev)
        by_event: Dict[str, list] = {}
        for change in mc:
            mid = change.get("id")
            ev = self.market_to_event.get(mid, "_unrouted")
            by_event.setdefault(ev, []).append(change)
        with self._lock:
            for ev, changes in by_event.items():
                out = {k: msg[k] for k in ("op", "clk", "pt", "ct") if k in msg}
                out["mc"] = changes
                fh = self._file_for(ev)
                fh.write(json.dumps(out, separators=(",", ":")) + "\n")
                fh.flush()
                self._counts[ev] = self._counts.get(ev, 0) + 1

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def close(self) -> None:
        with self._lock:
            for fh in self._files.values():
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
            self._files.clear()


MULTI_RAW = _MultiRawState()
SCORE_FHS: Dict[str, Any] = {}  # event_id -> score file handle (cleanup a fine run)


class _MultiRawListener(StreamListener):
    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            MULTI_RAW.write_message(raw_data)
        except Exception as e:  # noqa: BLE001 - il recording non deve mai rompere lo stream
            logger.debug("[raw] tee fallito (ignorato): %s", e)
        return super().on_data(raw_data)


class _MultiRawMarketStream(MarketStream):
    LISTENER = _MultiRawListener


class _PassiveRecorder(BaseStrategy):
    """Strategia passiva: nessun ordine. Serve solo a definire la subscription;
    il tee del raw avviene a livello di listener (on_data)."""

    def check_market_book(self, market: Any, market_book: Any) -> bool:  # noqa: D401
        return False  # niente processing: il tee e' gia' avvenuto nel listener

    def process_market_book(self, market: Any, market_book: Any) -> None:
        pass


# --------------------------------------------------------------------------- #
#  Discovery                                                                   #
# --------------------------------------------------------------------------- #
def discover_markets(trading: Any, start_within_hours: float,
                     max_markets: int,
                     market_types: Optional[List[str]] = None) -> Dict[str, str]:
    """Ritorna {market_id: event_id} per i mercati tennis in-play + in partenza."""
    mtypes = market_types or ["MATCH_ODDS"]
    m2e: Dict[str, str] = {}
    meta: Dict[str, Dict[str, Any]] = {}

    def _ingest(cat: List[Any]) -> None:
        for mo in cat or []:
            ev = getattr(mo, "event", None)
            ev_id = getattr(ev, "id", None)
            if not ev_id:
                continue
            m2e[mo.market_id] = str(ev_id)
            meta[mo.market_id] = {
                "matched": float(getattr(mo, "total_matched", 0.0) or 0.0),
                "name": getattr(ev, "name", "?"),
            }

    # in-play adesso
    _ingest(trading.betting.list_market_catalogue(
        filter=filters.market_filter(
            event_type_ids=[TENNIS], market_type_codes=mtypes,
            in_play_only=True),
        market_projection=["EVENT", "MARKET_START_TIME"],
        sort="MAXIMUM_TRADED", max_results=100))

    # in partenza entro N ore (li catturiamo dall'inizio dell'in-play)
    if start_within_hours > 0:
        now = datetime.now(timezone.utc)
        _ingest(trading.betting.list_market_catalogue(
            filter=filters.market_filter(
                event_type_ids=[TENNIS], market_type_codes=mtypes,
                market_start_time={
                    "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": (now + timedelta(hours=start_within_hours)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")}),
            market_projection=["EVENT", "MARKET_START_TIME"],
            sort="MAXIMUM_TRADED", max_results=100))

    # cap: tieni i piu' scambiati
    if len(m2e) > max_markets:
        top = sorted(m2e, key=lambda mid: meta.get(mid, {}).get("matched", 0.0),
                     reverse=True)[:max_markets]
        m2e = {mid: m2e[mid] for mid in top}
    for mid, ev in m2e.items():
        logger.info("  seguo %s ev=%s  %s (matched %.0f)", mid, ev,
                    meta.get(mid, {}).get("name", "?"),
                    meta.get(mid, {}).get("matched", 0.0))
    return m2e


# --------------------------------------------------------------------------- #
#  Worker punteggio (batch, per tutti gli eventi)                             #
# --------------------------------------------------------------------------- #
def _score_worker(context: Dict[str, Any], flumine: Any, *, trading: Any,
                  m2e: Dict[str, str], out_dir: str) -> None:
    """Poll batch degli score per tutti gli eventi noti -> per-event score.jsonl."""
    event_ids = sorted({int(e) for e in m2e.values() if str(e).isdigit()})
    if not event_ids:
        return
    fhs = SCORE_FHS
    last_key: Dict[str, Any] = context.setdefault("_score_lastkey", {})
    for i in range(0, len(event_ids), 20):
        chunk = event_ids[i:i + 20]
        try:
            raw = trading.in_play_service.get_scores(event_ids=chunk, lightweight=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[score] get_scores fallito: %s", exc)
            continue
        for rec in (raw or []):
            if not isinstance(rec, dict):
                continue
            ev = str(rec.get("eventId"))
            ts = parse_tennis_scores([rec], ev)
            if ts is None:
                continue
            if last_key.get(ev) == ts.key():
                continue
            last_key[ev] = ts.key()
            fh = fhs.get(ev)
            if fh is None:
                ev_dir = os.path.join(out_dir, ev)
                os.makedirs(ev_dir, exist_ok=True)
                fh = open(os.path.join(ev_dir, f"{ev}.score.jsonl"), "a",
                          encoding="utf-8")  # noqa: SIM115
                fhs[ev] = fh
            fh.write(json.dumps({"t": time.time(), "score": ts.raw},
                                default=str) + "\n")
            fh.flush()


def _keepalive_worker(context: Dict[str, Any], flumine: Any, *, trading: Any) -> None:
    keep_alive(trading)


def _rediscover_worker(context: Dict[str, Any], flumine: Any, *, trading: Any,
                       m2e: Dict[str, str], start_within_hours: float,
                       max_markets: int) -> None:
    """Aggiorna la mappa market->event (nuovi match) — il tee e lo score worker
    la leggono per riferimento vivo. La subscription resta quella iniziale; i
    nuovi mercati vengono comunque auto-appresi dal tee via marketDefinition."""
    try:
        fresh = discover_markets(trading, start_within_hours, max_markets)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[rediscover] fallito: %s", exc)
        return
    added = 0
    for mid, ev in fresh.items():
        if mid not in m2e:
            m2e[mid] = ev
            added += 1
    if added:
        logger.info("[rediscover] +%d nuovi eventi noti (score/routing aggiornati)", added)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    p = argparse.ArgumentParser(description="Recorder multi-partita tennis (raw+score)")
    p.add_argument("--out", required=True, help="cartella radice registrazioni")
    p.add_argument("--start-within-hours", type=float, default=4.0,
                   help="includi anche i match che iniziano entro N ore (0=solo in-play)")
    p.add_argument("--max-markets", type=int, default=60)
    p.add_argument("--score-interval", type=float, default=3.0)
    p.add_argument("--market-types", default="MATCH_ODDS",
                   help="tipi mercato separati da virgola (es. SET_BETTING)")
    args = p.parse_args(argv)
    mtypes = [t.strip() for t in args.market_types.split(",") if t.strip()]

    os.makedirs(args.out, exist_ok=True)
    trading = build_client(login=True)

    m2e = discover_markets(trading, args.start_within_hours, args.max_markets, mtypes)
    if not m2e:
        logger.warning("Nessun mercato tennis da seguire adesso.")
        return 1
    logger.info("=== RECORD MULTI === %d mercati -> %s", len(m2e), args.out)

    MULTI_RAW.configure(args.out, m2e)  # riferimento VIVO alla mappa

    market_ids = sorted(m2e.keys())
    data_filter = filters.streaming_market_data_filter(
        fields=["EX_ALL_OFFERS", "EX_TRADED", "EX_TRADED_VOL", "EX_LTP",
                "EX_MARKET_DEF"],
        ladder_levels=10)
    strat = _PassiveRecorder(
        market_filter=filters.streaming_market_filter(market_ids=market_ids),
        market_data_filter=data_filter,
        stream_class=_MultiRawMarketStream,
    )

    framework = Flumine(client=clients.BetfairClient(trading, paper_trade=True))
    framework.add_strategy(strat)
    framework.add_worker(BackgroundWorker(
        framework, function=_score_worker, interval=float(args.score_interval),
        func_kwargs={"trading": trading, "m2e": m2e, "out_dir": args.out},
        name="score_multi"))
    framework.add_worker(BackgroundWorker(
        framework, function=_keepalive_worker, interval=300.0,
        func_kwargs={"trading": trading}, name="keepalive"))
    framework.add_worker(BackgroundWorker(
        framework, function=_rediscover_worker, interval=180.0,
        func_kwargs={"trading": trading, "m2e": m2e,
                     "start_within_hours": args.start_within_hours,
                     "max_markets": args.max_markets},
        name="rediscover"))

    try:
        framework.run()
    except KeyboardInterrupt:
        logger.info("interrotto")
    finally:
        MULTI_RAW.close()
        for fh in SCORE_FHS.values():
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass
        logger.info("STATS righe raw per evento: %s", MULTI_RAW.counts())
    return 0


if __name__ == "__main__":
    sys.exit(main())
