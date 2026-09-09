"""stream.py — quote in TEMPO REALE via Exchange Stream API ufficiale, su un POOL
di connessioni (sharding), nel pieno rispetto dei limiti Betfair.

Limiti Betfair (documentazione + risposte del BDP sul forum ufficiale, 09/09/2026):
  · massimo 200 mercati per connessione stream (default; il BDP può alzarlo a
    1000 su richiesta) — oltre: SUBSCRIPTION_LIMIT_EXCEEDED e subscription rifiutata;
  · fino a 10 connessioni stream per app key;
  · i mercati CLOSED vengono esclusi dal conteggio al re-subscribe (job interno
    Betfair ogni 5', eviction dopo 1h): il client non deve fare nulla;
  · cosa fanno i tool concorrenti (Bet Angel, BFExplorer): catalogo via REST,
    stream per marketIds SOLO sui mercati monitorati, più connessioni quando il
    numero supera il limite per connessione — esattamente questo modulo.

Architettura:
  · MarketStreamPool.set_markets(ids ordinati per priorità) → sharding STABILE
    per market_id (hash mod N): un mercato cambia shard solo quando cambia N, così
    un evento nuovo ricrea la subscription di UNO shard, non di tutti;
  · N connessioni = ceil(mercati / cap_per_connessione), mai oltre il massimo
    configurato (default 4 → 720 mercati; hard cap 10 = limite Betfair). Se anche
    così non basta, gli shard tengono i mercati a priorità più alta (in-play
    prima) e il resto va al poll REST di fallback (service.py);
  · ogni shard: 1 connessione, conflate 1s, best offers (ladder_levels=1, prezzo +
    SIZE), heartbeat 5s; riconnessione con backoff; resubscribe throttled 60s;
  · salute per shard misurata sul socket (ogni messaggio, heartbeat incluso): un
    mercato fermo NON rende lo shard "malato" e non spreca REST.

Config (env, opzionali):
  SAFE_STRATEGY_STREAM_CONNS             connessioni massime (default 4, max 10)
  SAFE_STRATEGY_STREAM_MARKETS_PER_CONN  mercati per connessione (default 180 <
                                         200 Betfair; alzare SOLO se il BDP ha
                                         alzato il limite dell'app key)
"""
from __future__ import annotations

import logging
import math
import os
import queue
import threading
import time
from typing import Any, Callable, List, Optional, Set

logger = logging.getLogger("safe_strategy")

_RECONNECT_BACKOFF = (2.0, 5.0, 10.0, 30.0)
_RESUB_MIN_INTERVAL = 60.0
_HEALTHY_MAX_AGE_SEC = 30.0
_HEARTBEAT_MS = 5000
_CONFLATE_MS = 1000

# limiti Betfair (hard cap: mai superabili da configurazione)
BETFAIR_MAX_CONNECTIONS = 10
BETFAIR_DEFAULT_MARKETS_PER_CONN = 200
BETFAIR_MAX_MARKETS_PER_CONN = 1000

# default prudenti: margine 20 sotto il limite standard per connessione
DEFAULT_MAX_CONNECTIONS = 4
DEFAULT_MARKETS_PER_CONN = 180


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    """Intero da env con clamp [lo, hi]; vuoto/malformato → default."""
    raw = (os.getenv(name) or "").strip()
    try:
        val = int(raw) if raw else default
    except ValueError:
        val = default
    return max(lo, min(hi, val))


def shard_index(market_id: str, n_shards: int) -> int:
    """Shard STABILE di un mercato: dipende solo dall'id e dal numero di shard
    (niente hash() di Python, che cambia a ogni processo)."""
    digits = "".join(ch for ch in str(market_id) if ch.isdigit()) or "0"
    return int(digits) % max(1, n_shards)


def plan_shards(ranked_ids: List[str], max_conns: int, per_conn: int) -> List[List[str]]:
    """Distribuisce i mercati (già ordinati per priorità) in shard ≤ per_conn.

    Parte da ceil(n/per_conn) connessioni e aggiunge shard finché tutti stanno
    nel cap (o si raggiunge max_conns); se anche con max_conns uno shard sfora,
    tiene i primi per_conn per priorità (i tagliati vanno al fallback REST).
    Ritorna SEMPRE max_conns liste (vuote per gli shard non usati).
    """
    per_conn = max(1, per_conn)
    max_conns = max(1, max_conns)
    n = min(max_conns, max(1, math.ceil(len(ranked_ids) / per_conn)))
    while True:
        buckets: List[List[str]] = [[] for _ in range(n)]
        for mid in ranked_ids:
            buckets[shard_index(mid, n)].append(mid)
        if all(len(b) <= per_conn for b in buckets) or n >= max_conns:
            break
        n += 1
    out = [b[:per_conn] for b in buckets]
    out.extend([] for _ in range(max_conns - len(out)))
    return out


class _HealthListener:
    """Wrapper che marca la salute del socket su OGNI messaggio (heartbeat incluso).
    Istanzia il vero StreamListener di betfairlightweight in modo pigro (import
    solo nel thread) e gli delega tutto."""

    def __init__(self, output_queue: "queue.Queue[Any]", on_message: Callable[[], None]) -> None:
        from betfairlightweight import StreamListener

        class _Listener(StreamListener):  # type: ignore[misc]
            def on_data(self_inner, raw_data: str):  # noqa: N805 - classe interna
                on_message()
                return super().on_data(raw_data)

        # max_latency=None: con l'orologio locale sfasato (−2.8s misurati) il
        # warning "Latency high" scattava a OGNI messaggio (rumore + CPU)
        self.listener = _Listener(output_queue=output_queue, max_latency=None)


class StreamShard:
    """UNA connessione stream: push in coda, riconnessione, resubscribe."""

    def __init__(self, client: Any, index: int) -> None:
        self.client = client
        self.index = index
        self.queue: "queue.Queue[Any]" = queue.Queue()
        self._desired: Set[str] = set()
        self._subscribed: Set[str] = set()
        self._stream: Any = None
        self._thread: Optional[threading.Thread] = None
        self._stop = False
        self._last_msg_mono = 0.0
        self._last_resub = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------- controllo
    def set_markets(self, ids: Set[str]) -> None:
        """Set desiderato. Non ricrea la subscription qui: lo fa
        maybe_resubscribe() a ogni drain (così un cambio arrivato durante il
        throttle viene applicato appena il throttle scade)."""
        with self._lock:
            self._desired = set(ids)
        if self._thread is None and ids:
            self._thread = threading.Thread(
                target=self._run, name=f"safe-scan-stream-{self.index}", daemon=True
            )
            self._thread.start()

    def _touch(self) -> None:
        self._last_msg_mono = time.monotonic()

    def _kick(self) -> None:
        st = self._stream
        if st is not None:
            try:
                st.stop()
            except Exception as e:  # noqa: BLE001
                logger.debug("[safe-scan] stream#%d stop: %s", self.index, e)

    def stop(self) -> None:
        self._stop = True
        self._kick()

    def subscribed_ids(self) -> Set[str]:
        return set(self._subscribed)

    def desired_count(self) -> int:
        with self._lock:
            return len(self._desired)

    def maybe_resubscribe(self) -> None:
        """Ricrea la subscription se il set desiderato è cambiato (throttle 60s);
        chiude la connessione se lo shard non ha più mercati."""
        with self._lock:
            desired = set(self._desired)
        if self._stream is None:
            return
        if not desired:
            self._kick()  # shard svuotato: connessione chiusa, il loop attende
            return
        if desired != self._subscribed and time.monotonic() - self._last_resub > _RESUB_MIN_INTERVAL:
            self._last_resub = time.monotonic()
            self._kick()

    # ------------------------------------------------------------- consumo
    def healthy(self) -> bool:
        """Socket vivo (messaggio o heartbeat entro _HEALTHY_MAX_AGE_SEC)."""
        return (
            self._stream is not None
            and self._last_msg_mono > 0.0
            and time.monotonic() - self._last_msg_mono < _HEALTHY_MAX_AGE_SEC
        )

    def drain(self) -> List[Any]:
        out: List[Any] = []
        while True:
            try:
                books = self.queue.get_nowait()
            except queue.Empty:
                break
            if books:
                out.extend(books)
        self.maybe_resubscribe()
        return out

    # ------------------------------------------------------------- thread
    def _run(self) -> None:
        from betfairlightweight import filters as bf

        backoff_i = 0
        while not self._stop:
            with self._lock:
                ids = sorted(self._desired)
            if not ids:
                time.sleep(2.0)
                continue
            try:
                listener = _HealthListener(self.queue, self._touch).listener
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
                    conflate_ms=_CONFLATE_MS,
                    heartbeat_ms=_HEARTBEAT_MS,
                )
                logger.info(
                    "[safe-scan] stream#%d ATTIVO: %d mercati sottoscritti", self.index, len(ids)
                )
                self._touch()
                backoff_i = 0
                stream.start()  # blocca fino a stop()/errore di rete
            except Exception as e:  # noqa: BLE001 - riconnessione con backoff
                logger.warning("[safe-scan] stream#%d KO: %s", self.index, str(e)[:140])
            self._stream = None
            self._subscribed = set()
            if self._stop:
                break
            delay = _RECONNECT_BACKOFF[min(backoff_i, len(_RECONNECT_BACKOFF) - 1)]
            backoff_i += 1
            time.sleep(delay)


class MarketStreamPool:
    """Pool di shard: stessa interfaccia del vecchio worker singolo, N connessioni."""

    def __init__(
        self,
        client: Any,
        max_conns: Optional[int] = None,
        per_conn: Optional[int] = None,
    ) -> None:
        self.max_conns = (
            max_conns
            if max_conns is not None
            else _env_int("SAFE_STRATEGY_STREAM_CONNS", DEFAULT_MAX_CONNECTIONS, 1, BETFAIR_MAX_CONNECTIONS)
        )
        self.per_conn = (
            per_conn
            if per_conn is not None
            else _env_int(
                "SAFE_STRATEGY_STREAM_MARKETS_PER_CONN",
                DEFAULT_MARKETS_PER_CONN, 1, BETFAIR_MAX_MARKETS_PER_CONN,
            )
        )
        if self.per_conn > BETFAIR_DEFAULT_MARKETS_PER_CONN:
            logger.warning(
                "[safe-scan] %d mercati/connessione > 200 (limite Betfair standard): "
                "valido SOLO se il BDP ha alzato il limite di questa app key",
                self.per_conn,
            )
        self.shards = [StreamShard(client, i) for i in range(self.max_conns)]
        self._planned: List[List[str]] = [[] for _ in range(self.max_conns)]

    @property
    def capacity(self) -> int:
        return self.max_conns * self.per_conn

    def set_markets(self, ranked_ids: List[str]) -> None:
        plan = plan_shards(ranked_ids, self.max_conns, self.per_conn)
        if plan != self._planned:
            self._planned = plan
            for shard, ids in zip(self.shards, plan):
                shard.set_markets(set(ids))

    def planned_ids(self) -> Set[str]:
        return {mid for ids in self._planned for mid in ids}

    def drain(self) -> List[Any]:
        out: List[Any] = []
        for shard in self.shards:
            out.extend(shard.drain())
        return out

    def healthy(self) -> bool:
        """Almeno uno shard attivo è vivo (per il badge STREAM/REST)."""
        return any(s.healthy() for s in self.shards if s.desired_count() > 0)

    def covered_ids(self) -> Set[str]:
        """Mercati serviti da shard VIVI: tutto il resto va al fallback REST."""
        out: Set[str] = set()
        for s in self.shards:
            if s.healthy():
                out |= s.subscribed_ids()
        return out

    def subscribed_ids(self) -> Set[str]:
        out: Set[str] = set()
        for s in self.shards:
            out |= s.subscribed_ids()
        return out

    def active_connections(self) -> int:
        return sum(1 for s in self.shards if s.healthy())

    def stop(self) -> None:
        for s in self.shards:
            s.stop()
