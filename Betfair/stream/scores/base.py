"""Interfaccia comune dei provider di punteggio.

Disaccoppia il sistema dalla sorgente: il primario è l'in-play Betfair (stessi
event_id dello stream → nessun matching), il fallback è API-Football. Cambiare/
aggiungere un provider = nuova classe che implementa ScoreProvider.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class ScoreSnapshot:
    """Fotografia immutabile del punteggio a un istante."""

    event_id: str
    ts: str                       # ISO8601 UTC
    source: str                   # 'betfair' | 'api_football'
    minute: Optional[int] = None
    score_home: Optional[int] = None
    score_away: Optional[int] = None
    status: Optional[str] = None  # es. 'FirstHalf'|'HalfTime'|'SecondHalf'|'Finished'
    event_type: Optional[str] = None  # 'GOAL'|'RED_CARD'|... se disponibile
    payload: Dict[str, Any] = field(default_factory=dict)  # raw del provider (audit)

    def score_tuple(self) -> tuple[Optional[int], Optional[int]]:
        return (self.score_home, self.score_away)


@runtime_checkable
class ScoreProvider(Protocol):
    """Contratto di un provider di punteggio."""

    name: str

    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        """Ritorna lo snapshot corrente o None se non disponibile/errore."""
        ...

    def healthcheck(self) -> bool:
        """True se il provider risponde correttamente."""
        ...
