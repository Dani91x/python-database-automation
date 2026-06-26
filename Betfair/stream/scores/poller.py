"""ScorePoller: orchestrazione primario→fallback con circuit breaker.

Logica PURA e testabile (nessuna I/O di rete diretta qui se non via i provider;
clock iniettabile). Il runner chiama poll() a cadenza fissa e decide cosa
scrivere (live_now / live_score_timeline).

Comportamento:
  - interroga il PRIMARIO (Betfair in-play) finché risponde.
  - dopo `threshold` fallimenti consecutivi → apre il circuito e usa il FALLBACK.
  - a circuito aperto, ogni `retry_primary_sec` ritenta il primario (half-open):
    se torna a rispondere, richiude il circuito.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from .base import ScoreProvider, ScoreSnapshot

logger = logging.getLogger(__name__)


class ScorePoller:
    def __init__(
        self,
        primary: ScoreProvider,
        fallback: ScoreProvider,
        threshold: int = 3,
        retry_primary_sec: float = 120.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._threshold = max(1, threshold)
        self._retry_primary_sec = retry_primary_sec
        self._clock = clock

        self._consecutive_failures = 0
        self._circuit_open = False
        self._opened_at: Optional[float] = None
        self.fallback_count = 0
        self.current_source: Optional[str] = None

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    @property
    def primary(self) -> ScoreProvider:
        return self._primary

    def _try_primary(self, event_id: str) -> Optional[ScoreSnapshot]:
        snap = self._primary.get_score(event_id)
        if snap is not None:
            if self._consecutive_failures or self._circuit_open:
                logger.info("[poller] primario '%s' di nuovo sano.", self._primary.name)
            self._consecutive_failures = 0
            self._circuit_open = False
            self._opened_at = None
            self.current_source = self._primary.name
            return snap

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._threshold and not self._circuit_open:
            self._circuit_open = True
            self._opened_at = self._clock()
            logger.warning(
                "[poller] circuito APERTO dopo %d fallimenti: passo al fallback '%s'.",
                self._consecutive_failures,
                self._fallback.name,
            )
        return None

    def poll(self, event_id: str) -> Optional[ScoreSnapshot]:
        """Ritorna lo snapshot corrente dalla sorgente migliore disponibile."""
        if not self._circuit_open:
            snap = self._try_primary(event_id)
            if snap is not None:
                return snap
            # primario fallito ma circuito non ancora aperto → prova comunque fallback
            return self._use_fallback(event_id)

        # circuito aperto: half-open se è passato abbastanza tempo
        if self._opened_at is not None and (self._clock() - self._opened_at) >= self._retry_primary_sec:
            logger.info("[poller] half-open: ritento il primario '%s'.", self._primary.name)
            snap = self._try_primary(event_id)
            if snap is not None:
                return snap
            # retry fallito: riavvia la finestra di backoff (altrimenti ritenteremmo
            # il primario a ogni tick, vanificando il circuit breaker).
            self._opened_at = self._clock()

        return self._use_fallback(event_id)

    def _use_fallback(self, event_id: str) -> Optional[ScoreSnapshot]:
        snap = self._fallback.get_score(event_id)
        if snap is not None:
            self.fallback_count += 1
            self.current_source = self._fallback.name
            return snap
        # né primario né fallback: nessun dato per questo tick
        self.current_source = None
        return None
