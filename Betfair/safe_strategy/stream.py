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
    SIZE), heartbeat 5s; riconnessione con backoff; resubscribe throttled 30s e
    SENZA abbattere la connessione (nuova marketSubscription sullo stesso socket,
    solo per mercati NUOVI: 17/09, prima il set che cambiava per il calcio in
    gioco rifaceva la connessione ogni 30 s per ore);
  · salute per shard su DUE misure distinte: ``healthy()`` = socket vivo (ogni
    messaggio, heartbeat incluso) e ``serving()`` = BOOK consegnati di recente.
    La COPERTURA (chi non va al fallback REST) si decide su ``serving()``: il
    17/09 una connessione viva che non consegnava quote e' rimasta "sana" per
    ore e il poll REST non e' mai partito.

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

from Betfair.stream import valuta as _valuta

logger = logging.getLogger("safe_strategy")

_RECONNECT_BACKOFF = (2.0, 5.0, 10.0, 30.0)
_RESUB_MIN_INTERVAL = 30.0  # un CS nuovo (candidato) va sullo stream entro 30s
_HEALTHY_MAX_AGE_SEC = 30.0
# 17/09 - uno shard che riceve heartbeat ma NON book non copre niente: oltre
# questa eta' i suoi mercati tornano al poll REST. Con la salute misurata sul
# solo socket, il 17/09 il feed e' rimasto senza quote per ore mentre il badge
# STREAM restava verde e `last_error` nullo.
_SERVING_MAX_AGE_SEC = 20.0
# mercati USCITI dal set che si tollerano senza risottoscrivere: togliere un
# mercato non fa perdere una quota, aggiungerlo si'. Sotto questa soglia la
# subscription resta com'e' (vedi maybe_resubscribe).
_RESUB_EXTRA_TOLLERATI = 25
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


def _descrivi_errore_stream(e: BaseException) -> str:
    """Tipo dell'errore + il codice Betfair se c'e' (NO_SESSION, ...), mai il
    messaggio intero: e' cio' che va nello stato, letto da tutti."""
    nome = type(e).__name__
    testo = str(e).upper()
    for codice in ("INVALID_SESSION_INFORMATION", "NO_SESSION", "MAX_CONNECTION_LIMIT_EXCEEDED",
                   "SUBSCRIPTION_LIMIT_EXCEEDED", "NOT_AUTHORIZED", "TIMEOUT"):
        if codice in testo:
            return f"{nome}: {codice}"
    if "GETADDRINFO" in testo:
        return f"{nome}: getaddrinfo failed"
    if "CLOSED BY SERVER" in testo:
        return f"{nome}: connection closed by server"
    if "TIMED OUT" in testo:
        return f"{nome}: timed out"
    return nome


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
        # ultimo BOOK consegnato (non heartbeat): e' questo che dice se lo
        # shard sta davvero servendo quote
        self._last_book_mono = 0.0
        self.books = 0
        # FIX-C (26/09): quante volte la connessione e' caduta e perche'
        # (solo il tipo e un estratto senza dati di sessione): il 26/09 lo
        # shard e' rimasto a ``subscribed=0`` per 4 ore e lo stato non diceva
        # che ogni riconnessione falliva per la sessione scaduta.
        self.riconnessioni = 0
        self.ultimo_errore: Optional[str] = None
        self._last_resub = 0.0
        self._lock = threading.Lock()
        # serializza la risottoscrizione "a caldo" con la ricostruzione del
        # thread: senza, si potrebbe scrivere sul socket di uno stream morente
        self._io_lock = threading.Lock()

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
        """Aggiorna la subscription SOLO per un cambio che conta, e SENZA
        abbattere la connessione.

        17/09 - con calcio in gioco il set cambia in continuazione (linee O/U
        che diventano vive, candidati CS dal 30', HALF_TIME dal 15', partite
        seguite da Mike, ramo pre-KO): con la vecchia condizione
        ``desired != _subscribed`` l'UNICA connessione veniva abbattuta e
        rifatta OGNI 30 SECONDI per ore. Ogni ricostruzione azzera la cache di
        betfairlightweight ed e' un'occasione perche' il primo messaggio di un
        mercato sia di sola definizione, cioe' senza prezzi.

        Due correzioni:
          * si risottoscrive solo se ci sono mercati NUOVI non serviti (o se i
            mercati in piu' sono tanti da pesare sul limite per connessione);
          * la nuova ``marketSubscription`` viaggia sullo STESSO socket vivo
            (betfairlightweight ``betfairstream.py:99-143``: e' un ``_send`` e
            il listener sostituisce la subscription), quindi niente
            disconnessione, niente riautenticazione, niente backoff. Il
            ripiego - abbattere e ricostruire - resta solo per l'errore.
        """
        with self._lock:
            desired = set(self._desired)
        if self._stream is None:
            return
        if not desired:
            self._kick()  # shard svuotato: connessione chiusa, il loop attende
            return
        mancanti = desired - self._subscribed     # mercati NUOVI: servono davvero
        in_piu = self._subscribed - desired       # mercati usciti: costano poco
        if not mancanti and len(in_piu) < _RESUB_EXTRA_TOLLERATI:
            return
        if time.monotonic() - self._last_resub <= _RESUB_MIN_INTERVAL:
            return
        self._resubscribe(sorted(desired))

    def _subscribe(self, stream: Any, ids: List[str]) -> None:
        """La marketSubscription, identica per la prima e per le successive."""
        from betfairlightweight import filters as bf

        stream.subscribe_to_markets(
            market_filter=bf.streaming_market_filter(market_ids=ids),
            market_data_filter=bf.streaming_market_data_filter(
                fields=["EX_BEST_OFFERS", "EX_MARKET_DEF"],
                ladder_levels=1,
            ),
            conflate_ms=_CONFLATE_MS,
            heartbeat_ms=_HEARTBEAT_MS,
        )

    def _resubscribe(self, ids: List[str]) -> None:
        """Nuova subscription sul socket VIVO; se non si puo', si ricostruisce.

        I mercati appena sottoscritti non hanno ancora consegnato un prezzo:
        restano "scoperti" per il servizio (``stream_price_mono`` in
        service.py) e in quel giro li copre il poll REST. Mai un buco dati.
        """
        with self._io_lock:
            st = self._stream
            if st is None:
                return
            self._last_resub = time.monotonic()
            # solo su un socket GIA' connesso e autenticato: se ``_running`` e'
            # falso, ``_send`` aprirebbe e autenticherebbe una connessione dal
            # thread sbagliato, lasciandola senza subscription (muta)
            if getattr(st, "_running", False) and getattr(st, "_socket", None) is not None:
                try:
                    self._subscribe(st, ids)
                    self._subscribed = set(ids)
                    logger.info(
                        "[safe-scan] stream#%d subscription aggiornata a caldo: %d mercati "
                        "(connessione NON abbattuta)", self.index, len(ids),
                    )
                    return
                except Exception as e:  # noqa: BLE001 - si ripiega sulla ricostruzione
                    logger.warning(
                        "[safe-scan] stream#%d resubscribe a caldo KO (%s): ricostruisco",
                        self.index, str(e)[:120])
            self._kick()

    # ------------------------------------------------------------- consumo
    def healthy(self) -> bool:
        """Socket vivo (messaggio o heartbeat entro _HEALTHY_MAX_AGE_SEC)."""
        return (
            self._stream is not None
            and self._last_msg_mono > 0.0
            and time.monotonic() - self._last_msg_mono < _HEALTHY_MAX_AGE_SEC
        )

    def serving(self) -> bool:
        """Sta consegnando BOOK, non solo heartbeat.

        ``healthy()`` guarda il socket, e un socket vivo che non consegna quote
        resta "sano" per sempre: e' cosi' che il 17/09 il fallback REST non e'
        mai partito (``covered_ids`` dichiarava coperti tutti i mercati).
        """
        return (
            self.healthy()
            and self._last_book_mono > 0.0
            and time.monotonic() - self._last_book_mono < _SERVING_MAX_AGE_SEC
        )

    def stato(self) -> dict:
        """Referto per ``safe_strategy_status`` (visibilita', 17/09)."""
        mono = time.monotonic()

        def eta(t: float) -> Optional[float]:
            return round(mono - t, 1) if t else None

        return {
            "i": self.index,
            "desired": self.desired_count(),
            "subscribed": len(self._subscribed),
            "books": self.books,
            "eta_book_s": eta(self._last_book_mono),
            "eta_msg_s": eta(self._last_msg_mono),
            "eta_resub_s": eta(self._last_resub),
            "riconnessioni": self.riconnessioni,
            "ultimo_errore": self.ultimo_errore,
        }

    def drain(self) -> List[Any]:
        out: List[Any] = []
        while True:
            try:
                books = self.queue.get_nowait()
            except queue.Empty:
                break
            if books:
                out.extend(books)
        if out:
            # K1 (26/09): lo stream consegna le size in GBP (valuta dell'exchange),
            # il conto e' in EUR. Conversione ALLA FONTE, prima di ogni consumatore;
            # il poll REST (gia' in EUR) non passa di qui.
            for b in out:
                _valuta.converti_libro(b, _valuta.CAMBIO)
            # un BOOK e' arrivato davvero: e' questa, non l'eta' del socket, la
            # misura della copertura
            self._last_book_mono = time.monotonic()
            self.books += len(out)
        self.maybe_resubscribe()
        return out

    # ------------------------------------------------------------- thread
    def _run(self) -> None:
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
                # 17/09 - la subscription PRIMA della pubblicazione di
                # ``self._stream``. Pubblicandolo prima, un ``_kick()`` che
                # cadeva nella finestra fra ``create_stream`` e ``start()``
                # lasciava ``_running=False``: ``start()`` riapriva e
                # riautenticava il socket SENZA rimandare la marketSubscription,
                # cioe' una connessione viva, autenticata e MUTA - e con la
                # salute misurata sul socket era indistinguibile da una sana.
                self._subscribe(stream, ids)
                self._stream = stream
                self._subscribed = set(ids)
                self._last_resub = time.monotonic()
                self.ultimo_errore = None
                logger.info(
                    "[safe-scan] stream#%d ATTIVO: %d mercati sottoscritti", self.index, len(ids)
                )
                # NIENTE _touch() qui: la salute la fa il primo messaggio VERO.
                # Marcarla adesso significava dichiarare "sano" - e quindi
                # "coperto" - uno shard che non aveva ancora ricevuto nulla.
                backoff_i = 0
                if self._stop:
                    self._kick()
                    break
                stream.start()  # blocca fino a stop()/errore di rete
            except Exception as e:  # noqa: BLE001 - riconnessione con backoff
                logger.warning("[safe-scan] stream#%d KO: %s", self.index, str(e)[:140])
                self.ultimo_errore = _descrivi_errore_stream(e)
            if not self._stop:
                self.riconnessioni += 1
            with self._io_lock:
                self._stream = None
                self._subscribed = set()
            self._last_book_mono = 0.0
            self._last_msg_mono = 0.0
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

    def serving(self) -> bool:
        """Almeno uno shard attivo sta CONSEGNANDO book (badge STREAM/REST)."""
        return any(s.serving() for s in self.shards if s.desired_count() > 0)

    def covered_ids(self) -> Set[str]:
        """Mercati di shard che CONSEGNANO book: il resto va al fallback REST.

        Prima era ``healthy()``, cioe' l'eta' dell'ultimo messaggio sul socket -
        heartbeat compresi, uno ogni 5 s. Una connessione viva che non
        consegnava quote restava "sana" per sempre e ``poll_books`` non partiva
        mai (17/09: ``fasi_p95.book = 0.0`` per ore, con le uscite congelate).
        Il filtro FINE, per mercato, lo fa service.py con ``stream_price_mono``.
        """
        out: Set[str] = set()
        for s in self.shards:
            if s.serving():
                out |= s.subscribed_ids()
        return out

    def subscribed_ids(self) -> Set[str]:
        out: Set[str] = set()
        for s in self.shards:
            out |= s.subscribed_ids()
        return out

    def active_connections(self) -> int:
        return sum(1 for s in self.shards if s.healthy())

    def stato_shard(self) -> List[dict]:
        """Referto per shard, per gli shard con mercati assegnati."""
        return [s.stato() for s in self.shards if s.desired_count() > 0]

    def stop(self) -> None:
        for s in self.shards:
            s.stop()
