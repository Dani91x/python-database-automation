"""runner_lifecycle.py — auto-SPEGNIMENTO dei runner (logica PURA, condivisa).

Fix incidente 2026-07-08: i runner (calcio/tennis) restavano attivi per GIORNI a
martellare Betfair perché il worker watchlist/follow riagganciava sempre le partite
successive. Finché il software non sarà pensato per l'h24, il runner deve spegnersi
da solo quando non serve più. Due condizioni (entrambe configurabili via env, 0 = off):

  (a) VITA MASSIMA — backstop assoluto: dopo N ore il runner esce comunque;
  (b) INATTIVITÀ  — nessun evento "vivo" tra i follow attivi: né una partita in corso
      (iniziata da meno di ``stale_hours``) né una imminente (che inizia entro
      ``imminent_min`` minuti) → fine della giornata di trading, il runner esce.
      Si rilancia col .bat quando serve.

Qui SOLO matematica su datetimes (testabile a unità): niente I/O, niente flumine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def parse_open_date(raw: Any) -> Optional[datetime]:
    """open_date (ISO, anche con 'Z') → datetime aware UTC; None se non parsabile."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def event_is_alive(
    open_date: Optional[datetime],
    now: datetime,
    imminent_min: float,
    stale_hours: float,
) -> bool:
    """True se l'evento è IN CORSO (iniziato da < stale_hours) o IMMINENTE
    (inizia entro imminent_min). open_date non parsabile → True per PRUDENZA
    (mai spegnere il runner su un dato ambiguo)."""
    if open_date is None:
        return True
    return (open_date - timedelta(minutes=imminent_min)
            <= now
            <= open_date + timedelta(hours=stale_hours))


def any_follow_alive(
    follows: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    *,
    imminent_min: float,
    stale_hours: float,
) -> bool:
    """True se ALMENO un follow attivo (PENDING/STREAMING) è vivo o imminente."""
    t = now or datetime.now(timezone.utc)
    for f in follows:
        if event_is_alive(parse_open_date(f.get("open_date")), t, imminent_min, stale_hours):
            return True
    return False


def uptime_exceeded(started_monotonic: float, now_monotonic: float, max_hours: float) -> bool:
    """True se la vita massima è superata (max_hours <= 0 → mai)."""
    if max_hours <= 0:
        return False
    return (now_monotonic - started_monotonic) > max_hours * 3600.0


# ----------------------------------------------------------------------------
# Stallo del recorder raw (incidente 2026-07-16: stream MUTO per ~1.5h con
# runner vivo → nessun dato di mercato registrato, raw mai creati per i nuovi
# follow). Qui SOLO la matematica pura (testabile); l'azione è in runner.py.
# ----------------------------------------------------------------------------
def raw_stall_seconds(
    last_write_ms: float,
    now_ms: float,
    seconds_since_stream_start: Optional[float],
) -> Optional[float]:
    """Da quanti secondi il tee raw NON scrive.

    * ``last_write_ms > 0``: secondi trascorsi dall'ultimo write.
    * ``last_write_ms == 0`` (MAI scritto — il caso 16/07: stream mai connesso):
      l'età dello stream corrente, se nota.
    * altrimenti ``None`` (non determinabile → nessuna azione).
    """
    if last_write_ms and last_write_ms > 0:
        return max(0.0, (now_ms - last_write_ms) / 1000.0)
    if seconds_since_stream_start is not None:
        return max(0.0, seconds_since_stream_start)
    return None


def stall_restart_due(
    stall_s: Optional[float],
    threshold_s: float,
    last_restart_monotonic: float,
    now_monotonic: float,
    min_interval_s: float,
) -> bool:
    """True se lo stallo persistente giustifica una ricostruzione della
    subscription (throttled: mai più spesso di ``min_interval_s``).
    ``threshold_s <= 0`` disattiva il meccanismo."""
    if threshold_s <= 0 or stall_s is None or stall_s < threshold_s:
        return False
    return (now_monotonic - last_restart_monotonic) >= min_interval_s
