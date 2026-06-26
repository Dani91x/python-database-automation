"""Registrazione nativa raw via tee nel listener (F1).

betfairlightweight `StreamListener.on_data(raw_data)` riceve la stringa grezza di
ogni messaggio (mcm/status/...). Sottoclassandolo possiamo SCRIVERE il raw nativo
E lasciar parsare normalmente il MarketBook → dalla STESSA subscription otteniamo
sia il file nativo (per FlumineSimulation/Backtest) sia i book parsati (live_now +
curator). Niente seconda connessione/subscription → nessun rischio limiti.

Il file nativo è newline-delimited di messaggi `mcm` (formato storico Betfair),
filtrati per evento → un file replayabile per partita: `<event>/<event>.raw.jsonl`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

from betfairlightweight import StreamListener
from flumine.streams.marketstream import MarketStream

logger = logging.getLogger(__name__)


class _RawState:
    """Stato condiviso (impostato dal runner prima dello stream)."""

    def __init__(self) -> None:
        self.dir: Optional[str] = None
        self.market_to_event: Dict[str, str] = {}
        self.enabled: bool = False
        self._files: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def configure(self, data_dir: str, market_to_event: Dict[str, str], enabled: bool) -> None:
        self.dir = data_dir
        self.market_to_event = market_to_event  # riferimento vivo (aggiornato dal runner)
        self.enabled = enabled

    def file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            fh = open(os.path.join(ev_dir, f"{event_id}.raw.jsonl"), "a", encoding="utf-8")  # noqa: SIM115
            self._files[event_id] = fh
            logger.info("[raw] apro file nativo: %s", os.path.join(ev_dir, f"{event_id}.raw.jsonl"))
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
        # raggruppa i market change per evento e scrive un messaggio mcm valido per file
        by_event: Dict[str, list] = {}
        for change in mc:
            mid = change.get("id")
            ev = self.market_to_event.get(mid, "_unrouted")
            by_event.setdefault(ev, []).append(change)
        with self._lock:
            for ev, changes in by_event.items():
                out = {k: msg[k] for k in ("op", "clk", "pt", "ct") if k in msg}
                out["mc"] = changes
                fh = self.file_for(ev)
                fh.write(json.dumps(out, separators=(",", ":")) + "\n")
                fh.flush()

    def close(self) -> None:
        with self._lock:
            for fh in self._files.values():
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
            self._files.clear()


# singleton condiviso processo-wide (il listener è creato da flumine internamente)
RAW_STATE = _RawState()


def configure_raw(data_dir: str, market_to_event: Dict[str, str], enabled: bool) -> None:
    RAW_STATE.configure(data_dir, market_to_event, enabled)


def close_raw() -> None:
    RAW_STATE.close()


class RawTeeStreamListener(StreamListener):
    """StreamListener che fa il tee del raw nativo e poi parsa normalmente."""

    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            RAW_STATE.write_message(raw_data)
        except Exception as e:  # noqa: BLE001 - il recording NON deve mai rompere lo stream
            logger.debug("[raw] tee fallito (ignorato): %s", e)
        return super().on_data(raw_data)


class RawTeeMarketStream(MarketStream):
    """MarketStream che usa il listener con tee del raw (una sola subscription)."""

    LISTENER = RawTeeStreamListener
