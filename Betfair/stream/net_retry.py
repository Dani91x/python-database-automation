"""net_retry.py — A1: retry con backoff per errori TRANSITORI di rete (WinError 10035).

Sotto picco in-play le scritture specchio/ladder verso Supabase fallivano a
raffica con ``[WinError 10035]`` (WSAEWOULDBLOCK: socket non bloccante) e affini.
Il fix è doppio:
  1. client Supabase PER-THREAD (``db_client.get_supabase_client``): ogni
     BackgroundWorker flumine ha il suo client → niente contesa sullo stesso
     pool di connessioni httpx da thread concorrenti;
  2. questo modulo: retry BOUNDED con backoff esponenziale, SOLO per errori
     riconosciuti come transitori di rete. MAI retry su errori applicativi
     (RLS, CHECK, validazioni): ritenterebbero un'operazione che rifallirà
     identica, mascherando il problema vero.

MONEY-CRITICAL: l'ultima eccezione viene SEMPRE ri-sollevata — il chiamante
decide (le scritture specchio sono già best-effort con log espliciti); qui
non esiste alcun "ingoia e prosegui".
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

# Codici WinSock transitori: 10035 WSAEWOULDBLOCK, 10054 reset, 10060 timeout.
_TRANSIENT_WINERRORS = frozenset({10035, 10054, 10060})

# Marker testuali (case-insensitive) di errori di trasporto transitori.
_TRANSIENT_MARKERS = (
    "winerror 10035",
    "winerror 10054",
    "winerror 10060",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "remote protocol error",
    "server disconnected",
    "eof occurred",
)

_MAX_CHAIN_DEPTH = 8  # difensivo: catene __cause__/__context__ cicliche


def is_transient(exc: Optional[BaseException]) -> bool:
    """True se l'eccezione (o una sua causa) è un errore di rete TRANSITORIO."""
    seen = 0
    current: Optional[BaseException] = exc
    while current is not None and seen < _MAX_CHAIN_DEPTH:
        if isinstance(current, OSError):
            win = getattr(current, "winerror", None)
            if win in _TRANSIENT_WINERRORS:
                return True
        try:
            text = str(current).lower()
        except Exception:  # noqa: BLE001 - __str__ esotici
            text = ""
        if any(marker in text for marker in _TRANSIENT_MARKERS):
            return True
        # nome classe (httpx.ReadTimeout / ConnectError / RemoteProtocolError, ecc.)
        name = type(current).__name__.lower()
        if "timeout" in name or "connecterror" in name or "connectionerror" in name:
            return True
        nxt = current.__cause__ if current.__cause__ is not None else current.__context__
        current = nxt if nxt is not current else None
        seen += 1
    return False


def with_backoff(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.15,
    max_delay: float = 1.0,
    sleep: Callable[[float], Any] = time.sleep,
    on_retry: Optional[Callable[[BaseException, int], Any]] = None,
) -> T:
    """Esegue ``fn`` ritentando SOLO gli errori transitori di rete.

    Backoff esponenziale: base, 2·base, 4·base… con tetto ``max_delay``.
    ``attempts`` = tentativi TOTALI (bounded). Errore non transitorio o ultimo
    tentativo → l'eccezione originale viene ri-sollevata.
    """
    total = max(1, int(attempts))
    delay = max(0.0, float(base_delay))
    for attempt in range(1, total + 1):
        try:
            return fn()
        except BaseException as exc:  # noqa: BLE001 - filtrato subito sotto
            if attempt >= total or not is_transient(exc):
                raise
            if on_retry is not None:
                try:
                    on_retry(exc, attempt)
                except Exception:  # noqa: BLE001 - il callback non deve rompere il retry
                    pass
            sleep(min(delay, float(max_delay)))
            delay *= 2.0
    raise RuntimeError("unreachable")  # pragma: no cover - difensivo
