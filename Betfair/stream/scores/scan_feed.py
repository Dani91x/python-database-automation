"""scan_feed.py — punteggi/timeline dal FEED UNICO dello scanner Safe Strategy.

PERCHÉ (audit 09/09): lo scanner ``Betfair/safe_strategy`` interroga già l'IPS
Betfair in BATCH (chunk da 20, ogni 3s, tutti gli in-play calcio+tennis, più la
timeline calcio ogni 30s) e pubblica lo stato grezzo su ``safe_strategy_scan``.
I runner (calcio, tennis) facevano per OGNI evento seguito le stesse chiamate
(``get_scores([1 evento])`` ogni 5s/2s + ``get_event_timeline``) verso un
endpoint NON ufficiale senza rate-limit dichiarato: ~231 chiamate/min di cui
l'84% ridondanti. Qui i runner LEGGONO ciò che lo scanner ha già scaricato
(stesso pattern con cui Omega legge ``live_now``), con FALLBACK automatico alla
chiamata diretta quando la riga manca o è stantia (scanner giù, evento fuori dal
suo catalogo, pre-match): mai un buco dati, mai un punteggio vecchio.

Fedeltà: lo scanner salva lo ``state`` IPS INTEGRALE (``score_raw``): il runner
lo parsa con gli STESSI parser di sempre (``parse_score_dict`` calcio,
``parse_tennis_scores`` tennis) → nessuna differenza di formato.

Efficienza: UNA SELECT per ciclo per tutti gli eventi richiesti (cache con TTL
breve, condivisa fra i poller dello stesso processo), non una per evento.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from .base import ScoreSnapshot
from .betfair_inplay import BetfairInPlayProvider, parse_score_dict

logger = logging.getLogger(__name__)

SCAN_TABLE = "safe_strategy_scan"
# riga più vecchia di così = stantia (scanner fermo/lento): si torna alla chiamata
# diretta. Lo scanner pubblica i cambi di punteggio SUBITO (fuori throttle) con
# poll IPS a 3s: 15s è ampiamente sopra la cadenza normale.
DEFAULT_MAX_AGE_SEC = 15.0
# una SELECT al massimo ogni TTL per l'insieme di eventi richiesti
DEFAULT_CACHE_TTL_SEC = 1.0
# eventi non più richiesti da tanto escono dall'insieme letto
_WANTED_EXPIRE_SEC = 120.0


def _parse_ts(value: Any) -> Optional[float]:
    """ISO8601 (Postgres timestamptz) → epoch UTC; None se malformato."""
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


class ScanRowCache:
    """Cache per-processo delle righe ``safe_strategy_scan`` degli eventi richiesti.

    ``rows_for(event_ids)`` ritorna ``{event_id: row}``; la SELECT viene rifatta
    al massimo ogni ``ttl_sec`` sull'UNIONE degli eventi richiesti di recente, così
    N poller dello stesso processo costano UNA query, non N. Thread-safe.
    ``fetch`` iniettabile (test senza DB).
    """

    def __init__(
        self,
        ttl_sec: float = DEFAULT_CACHE_TTL_SEC,
        fetch: Optional[Callable[[List[str]], List[Dict[str, Any]]]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = max(0.0, float(ttl_sec))
        self._fetch = fetch or _fetch_rows
        self._clock = clock
        self._lock = threading.Lock()
        self._rows: Dict[str, Dict[str, Any]] = {}
        self._wanted: Dict[str, float] = {}   # event_id → ultimo monotonic richiesto
        self._loaded_at = -1e9
        self._pending: Set[str] = set()       # richiesti dopo l'ultima SELECT

    def rows_for(self, event_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        now = self._clock()
        with self._lock:
            for eid in event_ids:
                eid = str(eid)
                if eid not in self._wanted:
                    self._pending.add(eid)
                self._wanted[eid] = now
            # prune degli eventi non più richiesti
            for eid in [e for e, t in self._wanted.items() if now - t > _WANTED_EXPIRE_SEC]:
                self._wanted.pop(eid, None)
                self._rows.pop(eid, None)
            stale = now - self._loaded_at >= self._ttl
            if stale or self._pending:
                ids = sorted(self._wanted)
                self._pending.clear()
                self._loaded_at = now
                try:
                    fetched = self._fetch(ids) if ids else []
                    self._rows = {
                        str(r.get("event_id")): r for r in fetched
                        if isinstance(r, dict) and r.get("event_id") is not None
                    }
                except Exception as e:  # noqa: BLE001 - DB KO: si usa il fallback diretto
                    logger.debug("[scan-feed] SELECT KO (fallback diretto): %s", str(e)[:120])
                    self._rows = {}
            return {str(e): self._rows[str(e)] for e in event_ids if str(e) in self._rows}


def _fetch_rows(event_ids: List[str]) -> List[Dict[str, Any]]:
    from db_client import get_supabase_client

    sb = get_supabase_client()
    res = (
        sb.table(SCAN_TABLE)
        .select("event_id,sport,payload,updated_at")
        .in_("event_id", event_ids)
        .execute()
    )
    return getattr(res, "data", None) or []


# cache condivisa del processo (un runner = un processo)
_SHARED_CACHE: Optional[ScanRowCache] = None
_SHARED_LOCK = threading.Lock()


def shared_cache() -> ScanRowCache:
    global _SHARED_CACHE  # noqa: PLW0603 - singleton di processo
    with _SHARED_LOCK:
        if _SHARED_CACHE is None:
            _SHARED_CACHE = ScanRowCache()
        return _SHARED_CACHE


def row_age_sec(row: Dict[str, Any], now_epoch: Optional[float] = None) -> Optional[float]:
    ts = _parse_ts(row.get("updated_at"))
    if ts is None:
        return None
    return max(0.0, (now_epoch if now_epoch is not None else time.time()) - ts)


def fresh_payload(
    row: Optional[Dict[str, Any]], max_age_sec: float, now_epoch: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Payload della riga se FRESCA (età ≤ max_age), altrimenti None. PURA."""
    if not row:
        return None
    age = row_age_sec(row, now_epoch)
    if age is None or age > max_age_sec:
        return None
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else None


class ScanFeedScoreProvider:
    """ScoreProvider PRIMARIO dei runner: legge dal feed dello scanner, altrimenti
    delega alla chiamata IPS diretta (``direct``). Espone anche ``get_raw_state``
    (tennis: parser proprio) e ``get_timeline`` (calcio)."""

    name = "scan_feed"

    def __init__(
        self,
        direct: BetfairInPlayProvider,
        max_age_sec: float = DEFAULT_MAX_AGE_SEC,
        cache: Optional[ScanRowCache] = None,
    ) -> None:
        self.direct = direct
        self.max_age_sec = float(max_age_sec)
        self._cache = cache or shared_cache()
        self.feed_hits = 0
        self.direct_calls = 0

    # ------------------------------------------------------------ lettura feed
    def fresh_payload(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self._cache.rows_for([str(event_id)]).get(str(event_id))
        return fresh_payload(row, self.max_age_sec)

    def get_raw_state(self, event_id: str) -> Optional[Dict[str, Any]]:
        """``state`` IPS grezzo dell'evento dal feed (None = assente/stantio)."""
        p = self.fresh_payload(event_id)
        raw = p.get("score_raw") if p else None
        if isinstance(raw, dict):
            self.feed_hits += 1
            return raw
        return None

    # ------------------------------------------------------- ScoreProvider API
    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        raw = self.get_raw_state(event_id)
        if raw is not None:
            return parse_score_dict(str(event_id), raw)
        self.direct_calls += 1
        return self.direct.get_score(event_id)

    def get_timeline(self, event_id: str) -> List[Dict[str, Any]]:
        p = self.fresh_payload(event_id)
        tl = p.get("timeline") if p else None
        if isinstance(tl, list):
            return [x for x in tl if isinstance(x, dict)]
        self.direct_calls += 1
        return self.direct.get_timeline(event_id)

    def healthcheck(self) -> bool:
        return self.direct.healthcheck()
