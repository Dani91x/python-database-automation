"""Provider punteggio FALLBACK: API-Football (ufficiale, già pagato).

Richiede il nostro fixture_id. Il mapping betfair event_id → fixture_id viene
risolto UNA VOLTA dal runner (riusando Betfair/betfair_match.py) e passato qui.
Senza fixture_id il provider è inerte (get_score → None): il sistema continua a
funzionare con la sola sorgente Betfair.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from api_client import APIFootballClient

from .base import ScoreSnapshot

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_fixture_response(event_id: str, data: Dict[str, Any]) -> Optional[ScoreSnapshot]:
    """Converte la risposta /fixtures?id= in ScoreSnapshot."""
    resp = data.get("response") if isinstance(data, dict) else None
    if not resp:
        return None
    entry = resp[0] if isinstance(resp, list) else resp
    fixture = entry.get("fixture") or {}
    status = fixture.get("status") or {}
    goals = entry.get("goals") or {}

    return ScoreSnapshot(
        event_id=str(event_id),
        ts=_now_iso(),
        source="api_football",
        minute=_to_int(status.get("elapsed")),
        score_home=_to_int(goals.get("home")),
        score_away=_to_int(goals.get("away")),
        status=status.get("short"),
        event_type=None,
        payload=entry,
    )


class ApiFootballProvider:
    """Implementa ScoreProvider via API-Football (/fixtures?id=fixture_id)."""

    name = "api_football"

    def __init__(
        self,
        fixture_id: Optional[int],
        client: Optional[APIFootballClient] = None,
    ) -> None:
        self._fixture_id = fixture_id
        self._client = client or APIFootballClient()

    @property
    def fixture_id(self) -> Optional[int]:
        return self._fixture_id

    def set_fixture_id(self, fixture_id: Optional[int]) -> None:
        self._fixture_id = fixture_id

    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        if not self._fixture_id:
            return None
        data = self._client.call("/fixtures", params={"id": self._fixture_id})
        if not data:
            return None
        snap = parse_fixture_response(event_id, data)
        if snap is None:
            logger.warning("[fallback-apifootball] nessun punteggio per fixture %s", self._fixture_id)
        return snap

    def healthcheck(self) -> bool:
        return self._fixture_id is not None
