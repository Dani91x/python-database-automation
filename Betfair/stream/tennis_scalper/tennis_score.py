"""Feed punteggio TENNIS per la gap-guard (cintura 2).

Legge il punteggio in-play dall'``InPlayService`` di Betfair
(``ips.betfair.com``) e deriva se siamo su un **punto che pesa** (break point o
set point): i momenti in cui la quota gappa. Il worker setta
``strategy.point_pressure`` che il bot usa per ritirare le quote inevase e non
aprire nuovi ingressi (vedi ``tennis_scalper_bot``).

NON tocca ``scores/betfair_inplay.py`` (solo-calcio): file separato, parser
separato. Difensivo: se il match non e' coperto dall'IPS (ITF minori) o il feed
e' assente, ``point_pressure`` resta ``False`` e il bot si affida alla cintura 1
(anti-gap sull'order-book, ``max_signal_ticks``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 0/15/30/40/AD -> rango confrontabile. Il tie-break usa i punti numerici.
_POINT_RANK: Dict[str, int] = {
    "0": 0, "15": 1, "30": 2, "40": 3, "A": 4, "AD": 4, "ADV": 4,
}


def _to_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _rank(p: Any) -> Optional[int]:
    """Rango di un punteggio di gioco. None se non interpretabile."""
    if p is None:
        return None
    s = str(p).strip().upper()
    if s in _POINT_RANK:
        return _POINT_RANK[s]
    if s.isdigit():  # tie-break: 0,1,2,... (>=4 possibili)
        return int(s)
    return None


@dataclass(frozen=True)
class TennisScore:
    event_id: str
    status: Optional[str] = None
    sets_home: Optional[int] = None
    sets_away: Optional[int] = None
    games_home: Optional[int] = None
    games_away: Optional[int] = None
    point_home: Optional[str] = None
    point_away: Optional[str] = None
    server: Optional[str] = None          # "home" | "away" | None
    home_name: Optional[str] = None
    away_name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple:
        """Identita' dello stato di gioco (per rilevare i cambi punto)."""
        return (self.sets_home, self.sets_away, self.games_home, self.games_away,
                self.point_home, self.point_away, self.server)

    def receiver(self) -> Optional[str]:
        if self.server == "home":
            return "away"
        if self.server == "away":
            return "home"
        return None

    def pressures(self) -> Tuple[bool, bool, bool]:
        """(break_point, set_point, game_point). Best-effort e fail-safe.

        - game_point: un lato e' a >=40 (o in vantaggio) con lead >=1 punto,
          oppure in tie-break con max>=6 e lead>=1.
        - break_point: game_point in cui il leader NON e' chi serve (il
          ribattitore e' a un punto dal break) -> il gap grande.
        - set_point: il leader e' a un game dal set (5-x con lead>=1) oppure
          set point nel tie-break sul 6-6.
        """
        rh, ra = _rank(self.point_home), _rank(self.point_away)
        if rh is None or ra is None:
            return (False, False, False)

        lead: Optional[str] = None
        if rh >= 3 and rh - ra >= 1:
            lead = "home"
        elif ra >= 3 and ra - rh >= 1:
            lead = "away"
        elif max(rh, ra) >= 6 and abs(rh - ra) >= 1:  # tie-break
            lead = "home" if rh > ra else "away"
        if lead is None:
            return (False, False, False)

        game_point = True
        break_point = self.server is not None and self.server != lead

        lg = self.games_home if lead == "home" else self.games_away
        og = self.games_away if lead == "home" else self.games_home
        set_point = False
        if lg is not None and og is not None:
            if lg >= 5 and (lg - og) >= 1:
                set_point = True
            if lg == 6 and og == 6 and max(rh, ra) >= 6 and abs(rh - ra) >= 1:
                set_point = True
        return (break_point, set_point, game_point)

    @property
    def point_pressure(self) -> bool:
        """True sui punti che gappano davvero: break point o set point.

        Il game point del SERVITORE (semplice hold) non muove quasi la quota:
        di proposito NON attiva la guardia, per non congelare il bot inutilmente.
        """
        bp, sp, _ = self.pressures()
        return bool(bp or sp)


def _server(home: Dict[str, Any], away: Dict[str, Any]) -> Optional[str]:
    if bool(home.get("isServing")):
        return "home"
    if bool(away.get("isServing")):
        return "away"
    return None


def parse_tennis_scores(
    raw_list: Optional[List[Dict[str, Any]]], event_id: Any
) -> Optional[TennisScore]:
    """Parsa la lista dict di ``get_scores(..., lightweight=True)`` per il tennis.

    Ritorna ``None`` se non c'e' punteggio utile (pre-match / non coperto).
    """
    if not raw_list:
        return None
    rec: Optional[Dict[str, Any]] = None
    for r in raw_list:
        if isinstance(r, dict) and str(r.get("eventId")) == str(event_id):
            rec = r
            break
    if rec is None:
        rec = raw_list[0] if isinstance(raw_list[0], dict) else None
    if rec is None:
        return None

    score = rec.get("score") or {}
    home = score.get("home") or {}
    away = score.get("away") or {}

    ph = home.get("score")
    pa = away.get("score")
    cp = rec.get("currentPoint")
    if (ph is None or pa is None) and isinstance(cp, str) and "-" in cp:
        parts = cp.split("-", 1)
        ph = ph if ph is not None else parts[0].strip()
        pa = pa if pa is not None else parts[1].strip()

    return TennisScore(
        event_id=str(rec.get("eventId") or event_id),
        status=rec.get("status") or rec.get("matchStatus"),
        sets_home=_to_int(home.get("sets")),
        sets_away=_to_int(away.get("sets")),
        games_home=_to_int(home.get("games")),
        games_away=_to_int(away.get("games")),
        point_home=str(ph) if ph is not None else None,
        point_away=str(pa) if pa is not None else None,
        server=_server(home, away),
        home_name=home.get("name"),
        away_name=away.get("name"),
        raw=rec,
    )


def tennis_score_poll(
    context: Dict[str, Any],
    flumine: Any,
    *,
    trading: Any,
    event_id: Any,
    strategy: Any,
) -> None:
    """Worker flumine: interroga l'IPS e aggiorna ``strategy.point_pressure``.

    Firma richiesta da ``BackgroundWorker``: ``function(context, flumine, ...)``.
    Best-effort e FAIL-SAFE: qualsiasi errore (o punteggio assente) lascia
    ``point_pressure`` INVARIATO e il bot continua sull'anti-gap dell'order-book.
    """
    try:
        raw = trading.in_play_service.get_scores(
            event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],
            lightweight=True,
        )
    except Exception as exc:  # noqa: BLE001 - il feed non deve mai rompere il bot
        # FAIL-SAFE (fix 2026-07-10): su errore NON si tocca point_pressure.
        # Prima veniva forzato a False (fail-OPEN): un blackout del feed sul
        # break point spegneva la guardia proprio nel momento del gap.
        logger.debug("[tennis-score] get_scores fallito: %s", exc)
        return

    ts = parse_tennis_scores(raw, event_id)
    if ts is None:
        # nessun punteggio utile (pre-match/non coperto/feed vuoto transitorio):
        # anche qui la guardia resta INVARIATA (mai fail-open).
        context["last_score"] = None
        return

    was = bool(getattr(strategy, "point_pressure", False))
    pressure = ts.point_pressure
    strategy.point_pressure = pressure
    context["last_score"] = ts
    if pressure != was:
        bp, sp, _ = ts.pressures()
        kind = "BREAK point" if bp else ("SET point" if sp else "-")
        logger.info(
            "[tennis-score] gap-guard %s (%s) server=%s pts=%s-%s games=%s-%s sets=%s-%s",
            "ON" if pressure else "OFF", kind, ts.server,
            ts.point_home, ts.point_away, ts.games_home, ts.games_away,
            ts.sets_home, ts.sets_away,
        )


def tennis_score_poll_full(
    context: Dict[str, Any],
    flumine: Any,
    *,
    trading: Any,
    event_id: Any,
    strategy: Any,
    record_fh: Any = None,
) -> None:
    """Worker per la strategia PRO: aggiorna ``strategy.score`` col punteggio
    COMPLETO (TennisScore). Se ``record_fh`` e' un file, ci scrive (pt, score)
    per allineare punteggio e book nel backtest futuro.
    """
    try:
        raw = trading.in_play_service.get_scores(
            event_ids=[int(event_id)] if str(event_id).isdigit() else [event_id],
            lightweight=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[tennis-score] get_scores fallito: %s", exc)
        return
    ts = parse_tennis_scores(raw, event_id)
    strategy.score = ts
    if ts is None:
        return
    prev = context.get("last_key")
    if prev != ts.key():
        context["last_key"] = ts.key()
        logger.info("[score] set %s-%s  games %s-%s  %s-%s  serve=%s",
                    ts.sets_home, ts.sets_away, ts.games_home, ts.games_away,
                    ts.point_home, ts.point_away, ts.server)
        if record_fh is not None:
            try:
                import json as _json
                import time as _time
                record_fh.write(_json.dumps(
                    {"t": _time.time(), "score": ts.raw}, default=str) + "\n")
                record_fh.flush()
            except Exception:  # noqa: BLE001
                pass
