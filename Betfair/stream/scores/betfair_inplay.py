"""Provider punteggio PRIMARIO: in-play service Betfair.

Stessi event_id dello stream → nessun matching con la nostra API.

⚠️ Endpoint NON ufficiale (usato da betfair.com): può cambiare forma o rompersi.
Per questo: (1) parser DIFENSIVO tollerante a forme diverse, (2) payload grezzo
sempre conservato per audit, (3) il poller passa automaticamente al fallback
API-Football se questo provider fallisce ripetutamente.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import betfairlightweight

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


def _extract_side_score(side: Any) -> Optional[int]:
    """Estrae il punteggio da un lato (home/away) tollerando più forme."""
    if side is None:
        return None
    if isinstance(side, (int, float, str)):
        return _to_int(side)
    if isinstance(side, dict):
        # forme note/possibili: {"score": "1"} | {"value": 1} | {"goals": 1}
        for key in ("score", "value", "goals", "runningScore"):
            if key in side:
                return _to_int(side[key])
    return None


def parse_score_dict(event_id: str, raw: Dict[str, Any]) -> ScoreSnapshot:
    """Converte il dict grezzo dell'in-play in ScoreSnapshot (difensivo)."""
    # NB: guardie esplicite is-not-None (il minuto 0 è valido ma falsy → un
    # 'or' lo scarterebbe scegliendo il campo sbagliato).
    minute: Optional[int] = None
    if raw.get("timeElapsed") is not None:
        minute = _to_int(raw.get("timeElapsed"))
    elif raw.get("elapsedRegularTime") is not None:
        minute = _to_int(raw.get("elapsedRegularTime"))
    elif raw.get("timeElapsedSeconds") is not None:
        secs = _to_int(raw.get("timeElapsedSeconds"))
        minute = secs // 60 if secs is not None else None
    status = raw.get("matchStatus") or raw.get("status")

    home = away = None
    home_side = away_side = {}
    score = raw.get("score")
    if isinstance(score, dict):
        home_side = score.get("home") if isinstance(score.get("home"), dict) else {}
        away_side = score.get("away") if isinstance(score.get("away"), dict) else {}
        home = _extract_side_score(score.get("home"))
        away = _extract_side_score(score.get("away"))
        # forma alternativa: score.fullTime.home / score.current.home
        if home is None and isinstance(score.get("fullTime"), dict):
            home = _extract_side_score(score["fullTime"].get("home"))
            away = _extract_side_score(score["fullTime"].get("away"))
        if home is None and isinstance(score.get("current"), dict):
            home = _extract_side_score(score["current"].get("home"))
            away = _extract_side_score(score["current"].get("away"))

    # statistiche live (corner per tempo, cartellini Y/R, booking points)
    corners_home = _to_int(home_side.get("numberOfCorners"))
    corners_away = _to_int(away_side.get("numberOfCorners"))
    yellow_home = _to_int(home_side.get("numberOfYellowCards"))
    yellow_away = _to_int(away_side.get("numberOfYellowCards"))
    red_home = _to_int(home_side.get("numberOfRedCards"))
    red_away = _to_int(away_side.get("numberOfRedCards"))
    booking = _to_int(score.get("bookingPoints")) if isinstance(score, dict) else None

    stats: Dict[str, Any] = {
        "corners": {
            "home": corners_home, "away": corners_away,
            "home_1h": _to_int(home_side.get("numberOfCornersFirstHalf")),
            "home_2h": _to_int(home_side.get("numberOfCornersSecondHalf")),
            "away_1h": _to_int(away_side.get("numberOfCornersFirstHalf")),
            "away_2h": _to_int(away_side.get("numberOfCornersSecondHalf")),
        },
        "cards": {
            "yellow_home": yellow_home, "yellow_away": yellow_away,
            "red_home": red_home, "red_away": red_away,
        },
        "booking_points": booking,
        "match_status": status,
        "elapsed_added_time": _to_int(raw.get("elapsedAddedTime")),
        "home_name": home_side.get("name"),
        "away_name": away_side.get("name"),
    }

    return ScoreSnapshot(
        event_id=str(event_id),
        ts=_now_iso(),
        source="betfair",
        minute=minute,
        score_home=home,
        score_away=away,
        status=status,
        event_type=None,
        corners_home=corners_home,
        corners_away=corners_away,
        yellow_home=yellow_home,
        yellow_away=yellow_away,
        red_home=red_home,
        red_away=red_away,
        booking_points=booking,
        stats=stats,
        payload=raw,
    )


class BetfairInPlayProvider:
    """Implementa ScoreProvider via betfairlightweight in_play_service."""

    name = "betfair"

    def __init__(self, client: betfairlightweight.APIClient) -> None:
        self._client = client

    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        try:
            results = self._client.in_play_service.get_scores(
                event_ids=[event_id], lightweight=True
            )
        except Exception as e:  # noqa: BLE001 - non ufficiale: qualsiasi errore → None
            logger.warning("[inplay-betfair] get_scores KO per %s: %s", event_id, e)
            return None

        if not results:
            return None

        raw = results[0] if isinstance(results, list) else results
        if not isinstance(raw, dict):
            logger.warning("[inplay-betfair] forma inattesa per %s: %r", event_id, type(raw))
            return None

        return parse_score_dict(event_id, raw)

    def get_timeline(self, event_id: str) -> list[Dict[str, Any]]:
        """Cronologia eventi (gol/cartellini/kickoff col minuto) via get_event_timeline.

        Ritorna una lista di eventi normalizzati; lista vuota se non disponibile.
        """
        try:
            res = self._client.in_play_service.get_event_timeline(
                int(event_id), lightweight=True
            )
        except Exception as e:  # noqa: BLE001 - endpoint non ufficiale
            logger.debug("[inplay-betfair] get_event_timeline KO %s: %s", event_id, e)
            return []
        if not isinstance(res, dict):
            return []
        out: list[Dict[str, Any]] = []
        for u in res.get("updateDetails") or []:
            out.append(
                {
                    "update_id": u.get("updateId"),
                    "type": u.get("updateType") or u.get("type"),
                    "team": u.get("team"),
                    "team_name": u.get("teamName"),
                    "minute": _to_int(u.get("matchTime")),
                    "elapsed_regular": _to_int(u.get("elapsedRegularTime")),
                    "elapsed_added": _to_int(u.get("elapsedAddedTime")),
                }
            )
        return out

    def healthcheck(self) -> bool:
        # un client loggato è condizione sufficiente; la salute reale si misura
        # sul primo get_score (il poller gestisce il circuit breaker).
        return getattr(self._client, "session_token", None) is not None
