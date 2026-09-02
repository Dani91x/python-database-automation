"""stream.py — quote in TEMPO REALE via Exchange Stream API ufficiale.

UNA sola connessione stream per lo scanner: sottoscrive per market_ids tutti i
MATCH_ODDS del giorno (calcio+tennis, cap 180 < limite Betfair 200/subscription)
con conflate 1s e best offers (ladder_levels=1). Il thread ri-connette da solo
con backoff; se il set di mercati cambia in modo sostanziale la subscription
viene ricreata (throttle 60s). Il servizio consuma i MarketBook dalla coda; se
lo stream non è in salute il poll REST fa da fallback — mai un buco dati.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, List, Set

logger = logging.getLogger("safe_strategy")

_RECONNECT_BACKOFF = (2.0, 5.0, 10.0, 30.0)
_RESUB_MIN_INTERVAL = 60.0
_HEALTHY_MAX_AGE_SEC = 30.0
# limite Betfair: 200 mercati per subscription → margine difensivo
MAX_STREAM_MARKETS = 180


class MarketStreamWorker:
    """Thread di streaming mercati: push in coda, riconnessione, resubscribe."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.queue: "queue.Queue[Any]" = queue.Queue()
        self._desired: Set[str] = set()
        self._subscribed: Set[str] = set()
        self._stream: Any = None
        self._thread: threading.Thread | None = None
        self._stop = False
        self._last_msg_mono = 0.0
        self._last_resub = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------- controllo
    def set_markets(self, market_ids: List[str]) -> None:
        ids = set(market_ids[:MAX_STREAM_MARKETS])
        with self._lock:
            changed = ids != self._desired
            self._desired = ids
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="safe-scan-stream", daemon=True
            )
            self._thread.start()
        elif (
            changed
            and ids != self._subscribed
            and time.monotonic() - self._last_resub > _RESUB_MIN_INTERVAL
        ):
            # stop del socket: il loop del thread ricrea la subscription col set nuovo
            self._kick()

    def _kick(self) -> None:
        st = self._stream
        if st is not None:
            try:
                st.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug("[safe-scan] stream stop: %s", e)

    def stop(self) -> None:
        self._stop = True
        self._kick()

    # ------------------------------------------------------------- consumo
    def healthy(self) -> bool:
        return (
            self._last_msg_mono > 0.0
            and time.monotonic() - self._last_msg_mono < _HEALTHY_MAX_AGE_SEC
        )

    def drain(self) -> List[Any]:
        """Svuota la coda: lista piatta di MarketBook aggiornati."""
        out: List[Any] = []
        while True:
            try:
                books = self.queue.get_nowait()
            except queue.Empty:
                break
            if books:
                out.extend(books)
                self._last_msg_mono = time.monotonic()
        return out

    # ------------------------------------------------------------- thread
    def _run(self) -> None:
        from betfairlightweight import StreamListener
        from betfairlightweight import filters as bf

        backoff_i = 0
        while not self._stop:
            with self._lock:
                ids = sorted(self._desired)
            if not ids:
                time.sleep(2.0)
                continue
            try:
                listener = StreamListener(output_queue=self.queue)
                stream = self.client.streaming.create_stream(listener=listener)
                self._stream = stream
                self._subscribed = set(ids)
                self._last_resub = time.monotonic()
                stream.subscribe_to_markets(
                    market_filter=bf.streaming_market_filter(market_ids=ids),
                    market_data_filter=bf.streaming_market_data_filter(
                        fields=["EX_BEST_OFFERS", "EX_MARKET_DEF"],
                        ladder_levels=1,
                    ),
                    conflate_ms=1000,
                )
                logger.info(
                    "[safe-scan] stream ufficiale ATTIVO: %d mercati sottoscritti",
                    len(ids),
                )
                self._last_msg_mono = time.monotonic()
                backoff_i = 0
                stream.start()  # blocca fino a stop()/errore di rete
            except Exception as e:  # noqa: BLE001 - riconnessione con backoff
                logger.warning("[safe-scan] stream KO: %s", str(e)[:140])
            self._stream = None
            if self._stop:
                break
            delay = _RECONNECT_BACKOFF[min(backoff_i, len(_RECONNECT_BACKOFF) - 1)]
            backoff_i += 1
            time.sleep(delay)
