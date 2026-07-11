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
        # HEARTBEAT "recorder vivo" (fix 11/07, lezione 10/07: tee morto in
        # silenzio = in-play perso per sempre): contatori esposti alla
        # telemetria — bytes scritti, ts ultimo write, errori di scrittura.
        self.bytes_written: Dict[str, int] = {}
        self.last_write_ms: Dict[str, int] = {}
        self.write_errors: int = 0
        self._err_logged: Dict[str, float] = {}

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

    def health(self) -> Dict[str, Any]:
        """Snapshot per la telemetria (bytes/ultimo write per evento)."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "bytes": dict(self.bytes_written),
                "last_write_ms": dict(self.last_write_ms),
                "write_errors": self.write_errors,
            }

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
                line = json.dumps(out, separators=(",", ":")) + "\n"
                # SELF-HEAL (fix 11/07): un handle rotto (disco, close
                # concorrente durante un soft-restart) prima uccideva il tee
                # PER SEMPRE in silenzio (debug-log). Ora: drop dell'handle e
                # riapertura al prossimo messaggio, WARNING visibile
                # (throttled 60s per evento), contatore errori esposto.
                try:
                    fh = self.file_for(ev)
                    fh.write(line)
                    fh.flush()
                except Exception as exc:  # noqa: BLE001 - mai rompere lo stream
                    self.write_errors += 1
                    bad = self._files.pop(ev, None)
                    if bad is not None:
                        try:
                            bad.close()
                        except Exception:  # noqa: BLE001
                            pass
                    import time as _t
                    now_s = _t.time()
                    if now_s - self._err_logged.get(ev, 0.0) >= 60.0:
                        self._err_logged[ev] = now_s
                        logger.warning(
                            "[raw] write KO per evento %s (riapro al prossimo "
                            "messaggio): %s", ev, str(exc)[:150])
                    continue
                self.bytes_written[ev] = self.bytes_written.get(ev, 0) + len(line)
                pt = msg.get("pt")
                self.last_write_ms[ev] = int(pt) if isinstance(pt, (int, float)) else 0

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
