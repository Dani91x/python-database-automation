"""flusso_ordini_conto.py - lo stream degli ordini del CONTO, senza filtro di strategia, in SOLA LETTURA.

Scopo (priorita' dell'utente, T11; ``contratto.FlussoOrdiniConto``): portare in
tempo reale OGNI ordine del conto Betfair (app, bot, sito, scalper, Mike) a chi lo
deve vedere: il ladder di Trading, il libro ordini del comparto C, la Salute. E'
una sottoscrizione ``orderSubscription`` della Exchange Stream API su una
connessione SUA, costruita con le classi VERE di betfairlightweight:
``APIClient.streaming.create_stream`` -> ``BetfairStream`` (socket, CRLF,
autenticazione) -> ``StreamListener`` -> ``OrderStream`` -> ``OrderBookCache``
(``UnmatchedOrder``). Qui si aggiunge solo cio' che la libreria non fa: la
conversione in ``OrdineDalConto``, la ripresa dopo una caduta, la salute, i
consumatori.

Le scelte del filtro (``filters.streaming_order_filter``):
* ``customer_strategy_refs`` ASSENTE: tutti gli ordini del conto, anche quelli
  senza riferimento (sito) e quelli di ogni bot;
* ``include_overall_position=True``: Betfair manda la posizione abbinata del conto
  per selezione (``mb``/``ml``), che la cache della libreria tiene aggiornata in
  delta (``Available.update``). E' la base del P&L di mercato anche per gli ordini
  EXECUTION_COMPLETE che dopo una caduta non tornano nell'immagine. Betfair la
  manda di serie (``true``): la si scrive esplicita;
* ``partition_matched_by_strategy_ref=False``: la posizione per strategia
  (``smc``) arriverebbe in delta, ma la cache di betfairlightweight 2.23.2 la
  memorizza SOLO alla creazione del runner e ignora i delta successivi
  (``streaming/cache.py:580-602``: aggiorna solo ``ml``, ``mb``, ``uo``): il dato
  in cache sarebbe vecchio. L'attribuzione per bot si fa sugli ordini (``rfs``,
  ``rfo``) nel comparto C. Meno traffico sulla connessione.

Ripresa: la sottoscrizione si rifa' con ``initialClk``/``clk`` dell'ultimo
messaggio completo (la libreria li tiene; con la segmentazione ``clk`` arriva
solo a fine segmento): Betfair risponde ``RESUB_DELTA`` con i soli cambi. Dopo
``INVALID_CLOCK`` (o senza clk) si riparte da immagine piena. Backoff fra i
tentativi: 2, 4, 8, ... 60 s, mai dopo ``ferma``.

Salute: ``stato()`` dice vivo/muto con la stessa regola degli stream di mercato
(``Betfair/stream/stream_muto.stato_da_battiti``: 3 heartbeat senza messaggi =
muto; ``status`` 503 = latente).

Entrate: una ``Sessione`` (``contratto.Sessione``: ``client()`` con un
``APIClient`` valido, ``rinnova_se_serve()``). Uscite: ``OrdineDalConto`` ai
consumatori (thread proprio), ``ordini()``, ``posizioni()``, ``stato()``.

Cosa NON fa: non piazza, non annulla, non modifica ordini (nessun metodo lo fa);
non tocca lo stream ordini che flumine apre per i bot; non attribuisce gli ordini
(e' del comparto C); non scrive DB ne' file. Importare il modulo non apre socket
ne' thread: tutto nasce in ``avvia`` e muore in ``ferma``.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from betfairlightweight.enums import (
    StreamingOrderType,
    StreamingPersistenceType,
    StreamingSide,
    StreamingStatus,
)
from betfairlightweight.filters import streaming_order_filter
from betfairlightweight.streaming.cache import UnmatchedOrder
from betfairlightweight.streaming.listener import StreamListener
from betfairlightweight.streaming.stream import OrderStream

from Betfair.stream import stream_muto as _SM

from .contratto import OrdineDalConto, Sessione

logger = logging.getLogger(__name__)

#: heartbeat chiesto a Betfair (limiti 500-5000): misura certa del "muto"
HEARTBEAT_MS = 5000
#: backoff della riconnessione (s): 2, 4, 8, ... fino a 60
BACKOFF_MIN_S = 2.0
BACKOFF_MAX_S = 60.0
#: codici Betfair dopo i quali conviene rinnovare la sessione prima di riprovare
CODICI_SESSIONE = frozenset({"NO_SESSION", "INVALID_SESSION_INFORMATION",
                             "NOT_AUTHORIZED", "INVALID_APP_KEY"})
#: codice Betfair del clk non valido: si riparte da immagine piena
CODICE_CLK_NON_VALIDO = "INVALID_CLOCK"

_EPOCA = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
_LATI = {StreamingSide.B.name: "back", StreamingSide.L.name: "lay"}


def _ms(data: Optional[_dt.datetime]) -> Optional[int]:
    """Datetime della libreria (``utcfromtimestamp(pd / 1e3)``) -> ms epoch esatti."""
    if data is None:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=_dt.timezone.utc)
    d = data - _EPOCA
    return d.days * 86_400_000 + d.seconds * 1000 + int(round(d.microseconds / 1000.0))


def _num(v: Any) -> float:
    return float(v) if v is not None else 0.0


def ordine_dalla_cache(uo: UnmatchedOrder, market_id: str, selection_id: int,
                       handicap: Any, ricevuto_ms: int) -> OrdineDalConto:
    """``UnmatchedOrder`` della cache di betfairlightweight -> ``OrdineDalConto``.

    Nessuna interpretazione: i codici brevi dello stream (``B``/``L``, ``E``/``EC``,
    ``L``/``P``/``MOC``) si traducono con gli enum della libreria; ``avp`` assente
    resta None (la libreria, serializzando, lo metterebbe 0.0). Un codice
    sconosciuto solleva ``KeyError`` (chi chiama lo logga col motivo)."""
    return OrdineDalConto(
        bet_id=str(uo.bet_id),
        market_id=str(market_id),
        selection_id=int(selection_id),
        handicap=float(handicap or 0.0),
        lato=_LATI[uo.side],  # type: ignore[arg-type]
        prezzo=float(uo.price),
        importo=float(uo.size),
        stato=StreamingStatus[uo.status].value,
        persistenza=(StreamingPersistenceType[uo.persistence_type].value
                     if uo.persistence_type else None),
        tipo=StreamingOrderType[uo.order_type].value if uo.order_type else None,
        piazzato_ms=_ms(uo.placed_date),
        abbinato_ms=_ms(uo.matched_date),
        abbinato=_num(uo.size_matched),
        residuo=_num(uo.size_remaining),
        scaduto=_num(uo.size_lapsed),
        annullato=_num(uo.size_cancelled),
        annullato_da_betfair=_num(uo.size_voided),
        prezzo_medio=float(uo.average_price_matched) if uo.average_price_matched is not None else None,
        customer_order_ref=uo.reference_order or None,
        customer_strategy_ref=uo.reference_strategy or None,
        regulator_code=uo.regulator_code or None,
        ricevuto_ms=int(ricevuto_ms),
    )


# ---------------------------------------------------------------------------
# listener e stream: la catena VERA della libreria, con due osservazioni in piu'
# ---------------------------------------------------------------------------
class _OrderStreamConto(OrderStream):
    """``OrderStream`` di betfairlightweight che, DOPO aver aggiornato la cache
    (``super()._process``), passa al listener il messaggio appena applicato."""

    def _process(self, data: list, publish_time: int) -> bool:
        img = super()._process(data, publish_time)
        self._listener.cambiati(self, data)
        return img


class ListenerConto(StreamListener):
    """``StreamListener`` vero (``lightweight=True``: nessuna risorsa costruita
    inutilmente, la cache resta quella della libreria) con il battito della
    connessione e la conversione degli ordini cambiati."""

    def __init__(self, su_ordini: Callable[[List[OrdineDalConto], Dict[str, Any]], None],
                 orologio_ms: Callable[[], float]) -> None:
        super().__init__(output_queue=None, max_latency=None, lightweight=True,
                         order_updates_only=True)
        self._su_ordini = su_ordini
        self._ora_ms = orologio_ms
        self.ultimo_msg_ms: Optional[float] = None
        self.ultimo_dato_ms: Optional[float] = None
        self.autenticato = False
        self.ultimo_errore: Optional[str] = None
        # betfairlightweight tiene ``connectionsAvailable`` solo se vero: qui anche lo 0
        self.connessioni_disponibili: Optional[int] = None
        self.heartbeat_ms_server: Optional[int] = None
        self.errori_conversione = 0
        self.errore_elaborazione = False
        self.messaggi = 0

    def _add_stream(self, unique_id: int, operation: str) -> Any:
        if operation == "orderSubscription":
            return _OrderStreamConto(self, unique_id)
        return super()._add_stream(unique_id, operation)

    def on_data(self, raw_data: str) -> Optional[bool]:
        self._osserva(raw_data)
        try:
            return super().on_data(raw_data)
        except Exception:
            # la libreria aggiorna ``clk`` PRIMA di applicare il messaggio
            # (``stream.py`` ``on_update``): riprendere da quel clk salterebbe il
            # messaggio fallito. Si segna: la riconnessione chiede l'immagine piena.
            self.errore_elaborazione = True
            raise

    def _osserva(self, raw_data: str) -> None:
        """Battito (qualunque messaggio), esito dell'autenticazione, errori."""
        self.ultimo_msg_ms = self._ora_ms()
        self.messaggi += 1
        try:
            d = json.loads(raw_data)
        except ValueError:
            logger.warning("[ordini-conto] messaggio illeggibile: %s", str(raw_data)[:120])
            return
        op = d.get("op")
        if op == "status":
            disp = d.get("connectionsAvailable")
            if isinstance(disp, int) and not isinstance(disp, bool):
                self.connessioni_disponibili = disp
            if d.get("statusCode") == "SUCCESS":
                self.autenticato = True
                self.ultimo_errore = None
            elif d.get("statusCode") == "FAILURE":
                self.autenticato = False
                self.ultimo_errore = str(d.get("errorCode") or "FAILURE")
                logger.warning("[ordini-conto] Betfair FAILURE %s: %s", self.ultimo_errore,
                               str(d.get("errorMessage") or "")[:160])
        elif op == "ocm":
            hb = d.get("heartbeatMs")
            if isinstance(hb, int) and not isinstance(hb, bool) and hb > 0:
                self.heartbeat_ms_server = hb
            if d.get("oc"):
                self.ultimo_dato_ms = self.ultimo_msg_ms

    def cambiati(self, stream: OrderStream, data: list) -> None:
        """Gli ordini toccati dal messaggio, letti dalla cache GIA' aggiornata."""
        ricevuto = int(self._ora_ms())
        ordini: List[OrdineDalConto] = []
        info: Dict[str, Any] = {"immagini": {}, "posizioni": {}, "chiusi": []}
        for oc in data:
            mid = str(oc.get("id"))
            cache = stream._caches.get(mid)
            if cache is None:
                continue
            if oc.get("closed"):
                info["chiusi"].append(mid)
            if oc.get("fullImage"):
                info["immagini"][mid] = set()
            for orc in oc.get("orc") or []:
                self._runner(cache, mid, orc, ricevuto, ordini, info)
        self._su_ordini(ordini, info)

    def _runner(self, cache: Any, mid: str, orc: Mapping[str, Any], ricevuto: int,
                ordini: List[OrdineDalConto], info: Dict[str, Any]) -> None:
        sel, hc = orc.get("id"), orc.get("hc", 0)
        runner = cache.runners.get((sel, hc))
        if runner is None:
            return
        if "mb" in orc or "ml" in orc or orc.get("fullImage"):
            info["posizioni"][(mid, int(sel), float(hc or 0.0))] = {
                "abbinati_back": [[d["price"], d["size"]] for d in runner.matched_backs.serialised],
                "abbinati_lay": [[d["price"], d["size"]] for d in runner.matched_lays.serialised],
            }
        for uo in orc.get("uo") or []:
            bet = runner.unmatched_orders.get(uo.get("id"))
            if bet is None:
                continue
            try:
                ordini.append(ordine_dalla_cache(bet, mid, sel, hc, ricevuto))
            except (KeyError, TypeError, ValueError) as e:
                self.errori_conversione += 1
                logger.error("[ordini-conto] ordine %s non convertibile (%s: %s)",
                             uo.get("id"), type(e).__name__, e)
                continue
            if mid in info["immagini"]:
                info["immagini"][mid].add(str(bet.bet_id))


def _crea_stream_libreria(client: Any, unique_id: int, listener: StreamListener) -> Any:
    """``APIClient.streaming.create_stream`` (betfairlightweight)."""
    return client.streaming.create_stream(unique_id=unique_id, listener=listener)


def _codice_errore(e: BaseException, listener: ListenerConto) -> str:
    if listener.ultimo_errore:
        return listener.ultimo_errore
    testo = str(e).upper()
    for codice in sorted(CODICI_SESSIONE | {CODICE_CLK_NON_VALIDO}):
        if codice in testo:
            return codice
    return type(e).__name__


# ---------------------------------------------------------------------------
# il flusso degli ordini del conto
# ---------------------------------------------------------------------------
class FlussoOrdiniContoBetfair:
    """Implementa ``contratto.FlussoOrdiniConto`` (sola lettura)."""

    def __init__(self, sessione: Sessione, *,
                 heartbeat_ms: Optional[int] = HEARTBEAT_MS,
                 conflate_ms: Optional[int] = None,
                 segmentazione: bool = True,
                 includi_posizione_complessiva: bool = True,
                 partizione_per_strategia: bool = False,
                 crea_stream: Callable[[Any, int, StreamListener], Any] = _crea_stream_libreria,
                 orologio_ms: Callable[[], float] = lambda: time.time() * 1000.0,
                 id_iniziale: int = 9000) -> None:
        self._sessione = sessione
        self._heartbeat_ms = heartbeat_ms
        self._conflate_ms = conflate_ms
        self._segmentazione = bool(segmentazione)
        self._filtro = streaming_order_filter(
            include_overall_position=bool(includi_posizione_complessiva),
            customer_strategy_refs=None,
            partition_matched_by_strategy_ref=bool(partizione_per_strategia),
        )
        self._crea_stream = crea_stream
        self._ora_ms = orologio_ms
        self._id = int(id_iniziale)
        self._lock = threading.RLock()
        self._ordini: Dict[str, OrdineDalConto] = {}
        self._posizioni: Dict[Tuple[str, int, float], Dict[str, Any]] = {}
        self._non_confermati: Set[str] = set()
        self._chiusi: Set[str] = set()
        self._consumatori: List[Tuple[Callable[[OrdineDalConto], None], Optional[Set[str]]]] = []
        self._coda: "queue.Queue[Optional[List[OrdineDalConto]]]" = queue.Queue()
        self._fermo = threading.Event()
        self._forza_immagine = False
        self._listener = ListenerConto(self._su_ordini, orologio_ms)
        self._stream: Any = None
        self._thread: Optional[threading.Thread] = None
        self._thread_consegna: Optional[threading.Thread] = None
        self.conti: Dict[str, int] = {
            "connessioni": 0, "riconnessioni": 0, "riprese_con_clk": 0, "immagini_piene": 0,
            "ordini_ricevuti": 0, "errori_consumatori": 0, "rinnovi_sessione": 0,
        }
        self._avviato_ms: Optional[float] = None

    # ------------------------------------------------------------ contratto
    @property
    def filtro_ordini(self) -> Dict[str, Any]:
        """Il ``orderFilter`` mandato a Betfair (per i test e la Salute)."""
        return dict(self._filtro)

    def avvia(self) -> None:
        """Apre la connessione (thread proprio) e il thread di consegna."""
        if self._thread is not None:
            return
        self._fermo.clear()
        self._avviato_ms = self._ora_ms()
        self._thread_consegna = threading.Thread(target=self._consegna, name="ordini-conto-consegna",
                                                 daemon=True)
        self._thread_consegna.start()
        self._thread = threading.Thread(target=self._ciclo, name="ordini-conto", daemon=True)
        self._thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        """Chiude la connessione: nessuna riconnessione dopo."""
        self._fermo.set()
        fine = time.monotonic() + attesa_s
        t = self._thread
        # si ferma lo stream finche' il thread non esce: ``BetfairStream.start``
        # dopo uno ``stop`` arrivato fra la sottoscrizione e la lettura si
        # ricollegherebbe; un secondo ``stop`` chiude anche quella
        while True:
            self._ferma_stream()
            if t is None or not t.is_alive() or time.monotonic() >= fine:
                break
            t.join(timeout=0.1)
        self._coda.put(None)
        if self._thread_consegna is not None:
            self._thread_consegna.join(timeout=max(0.1, fine - time.monotonic()))
        if t is not None and t.is_alive():
            logger.error("[ordini-conto] il thread della connessione non si e' fermato in %.1f s",
                         attesa_s)
        self._thread = None
        self._thread_consegna = None

    def _ferma_stream(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            stream.stop()
        except Exception as e:  # noqa: BLE001 - si chiude comunque
            logger.warning("[ordini-conto] stop dello stream: %s", e)

    def aggiungi_consumatore(self, cb: Callable[[OrdineDalConto], None], *,
                             mercati: Optional[Set[str]] = None) -> None:
        """``cb(ordine)`` per ogni ordine cambiato (thread di consegna); ``mercati``
        None = tutti, altrimenti solo quelli (estensione additiva del contratto)."""
        filtro = {str(m) for m in mercati} if mercati is not None else None
        with self._lock:
            self._consumatori = list(self._consumatori) + [(cb, filtro)]

    def ordini(self, market_id: Optional[str] = None) -> Tuple[OrdineDalConto, ...]:
        """Ultimo stato noto di ogni ordine (anche EXECUTION_COMPLETE), per mercato."""
        with self._lock:
            tutti = list(self._ordini.values())
        if market_id is not None:
            tutti = [o for o in tutti if o.market_id == str(market_id)]
        return tuple(sorted(tutti, key=lambda o: (o.market_id, o.piazzato_ms or 0, o.bet_id)))

    def posizioni(self, market_id: str) -> List[Dict[str, Any]]:
        """Posizione abbinata del CONTO per selezione (``mb``/``ml`` di Betfair)."""
        with self._lock:
            return [dict(v, selection_id=k[1], handicap=k[2])
                    for k, v in sorted(self._posizioni.items()) if k[0] == str(market_id)]

    def ordini_non_confermati(self) -> Set[str]:
        """bet_id EXECUTABLE assenti dall'ultima immagine piena del loro mercato
        (concluso mentre la connessione era giu'): li riconcilia il comparto C."""
        with self._lock:
            return set(self._non_confermati)

    def stato(self) -> Mapping[str, object]:
        li = self._listener
        ora = self._ora_ms()
        latente = li.status is not None and li.status != 200
        hb = li.heartbeat_ms_server or self._heartbeat_ms or _SM.HEARTBEAT_MS_MAX_RICHIESTA
        soglia_s = _SM.BATTITI_PER_SOGLIA * float(hb) / 1000.0
        verdetto = _SM.stato_da_battiti(li.ultimo_msg_ms, li.ultimo_dato_ms, adesso_ms=ora,
                                        soglia_s=soglia_s, mercati=["conto"], latente=latente)
        avviato = self._thread is not None
        stream = self._stream
        with self._lock:
            n_ordini, n_mercati = len(self._ordini), len({o.market_id for o in self._ordini.values()})
            non_conf = len(self._non_confermati)
            n_cons = len(self._consumatori)
        return {
            "stato": ("assente" if not avviato else "vivo" if verdetto["vivo"] else "muto"),
            "motivo": verdetto["motivo"] if avviato else "non_avviato",
            "eta_ultimo_messaggio_s": verdetto["eta_s"],
            "eta_ultimo_ordine_s": (None if li.ultimo_dato_ms is None
                                    else round((ora - li.ultimo_dato_ms) / 1000.0, 1)),
            "soglia_muto_s": soglia_s,
            "connesso": bool(stream is not None and getattr(stream, "running", False)),
            "autenticato": li.autenticato,
            "latente": latente,
            "initial_clk": li.initial_clk,
            "ultimo_clk": li.clk,
            "ultimo_errore": li.ultimo_errore,
            "connessioni_disponibili": li.connessioni_disponibili,
            "heartbeat_ms": hb,
            "filtro": self.filtro_ordini,
            "ordini": n_ordini,
            "mercati": n_mercati,
            "non_confermati": non_conf,
            "consumatori": n_cons,
            "errori_conversione": li.errori_conversione,
            "messaggi": li.messaggi,
            **self.conti,
        }

    # ------------------------------------------------------------ connessione
    def _ciclo(self) -> None:
        tentativo = 0
        while not self._fermo.is_set():
            try:
                self._connetti_e_leggi()
                if self._fermo.is_set():
                    break
                raise ConnectionError("lettura terminata senza ferma()")
            except Exception as e:  # noqa: BLE001 - si riconnette: niente resta muto in silenzio
                if self._fermo.is_set():
                    break
                tentativo += 1
                self._dopo_errore(e)
                attesa = max(BACKOFF_MIN_S, min(BACKOFF_MAX_S, float(2 ** tentativo)))
                logger.warning("[ordini-conto] connessione KO (%s): nuovo tentativo fra %.0f s",
                               str(e)[:160], attesa)
                if self._fermo.wait(attesa):
                    break
                continue
        logger.info("[ordini-conto] fermato")

    def _connetti_e_leggi(self) -> None:
        li = self._listener
        client = self._sessione.client()
        stream = self._crea_stream(client, self._id, li)
        self._stream = stream
        if self._fermo.is_set():
            return
        ic, clk = li.initial_clk, li.clk
        ripresa = bool(ic and clk) and not self._forza_immagine
        self._id = int(stream.subscribe_to_orders(
            order_filter=dict(self._filtro),
            initial_clk=ic if ripresa else None,
            clk=clk if ripresa else None,
            conflate_ms=self._conflate_ms,
            heartbeat_ms=self._heartbeat_ms,
            segmentation_enabled=self._segmentazione,
        ))
        self._forza_immagine = False
        self.conti["connessioni"] += 1
        self.conti["riprese_con_clk" if ripresa else "immagini_piene"] += 1
        logger.info("[ordini-conto] sottoscrizione %s (%s)", self._id,
                    "ripresa con clk" if ripresa else "immagine piena")
        if self._fermo.is_set():
            stream.stop()
            return
        stream.start()

    def _dopo_errore(self, e: BaseException) -> None:
        self.conti["riconnessioni"] += 1
        codice = _codice_errore(e, self._listener)
        if codice == CODICE_CLK_NON_VALIDO or self._listener.errore_elaborazione:
            self._forza_immagine = True
            self._listener.errore_elaborazione = False
        if codice in CODICI_SESSIONE:
            self.conti["rinnovi_sessione"] += 1
            try:
                self._sessione.rinnova_se_serve()
            except Exception as ex:  # noqa: BLE001 - si ritenta al giro dopo
                logger.warning("[ordini-conto] rinnovo della sessione KO: %s", ex)
        self._listener.autenticato = False

    # ------------------------------------------------------------ ordini
    def _su_ordini(self, ordini: List[OrdineDalConto], info: Dict[str, Any]) -> None:
        """Nel thread del socket: aggiorna lo stato (subito leggibile) e accoda."""
        with self._lock:
            for o in ordini:
                self._ordini[o.bet_id] = o
                self._non_confermati.discard(o.bet_id)
            for mid, visti in info["immagini"].items():
                for bet_id, o in self._ordini.items():
                    if o.market_id == mid and o.stato == "EXECUTABLE" and bet_id not in visti:
                        self._non_confermati.add(bet_id)
            self._posizioni.update(info["posizioni"])
            self._chiusi.update(info["chiusi"])
            self.conti["ordini_ricevuti"] += len(ordini)
        if ordini:
            self._coda.put(ordini)

    def _consegna(self) -> None:
        while True:
            lotto = self._coda.get()
            if lotto is None:
                return
            with self._lock:
                consumatori = list(self._consumatori)
            for o in lotto:
                for cb, mercati in consumatori:
                    if mercati is not None and o.market_id not in mercati:
                        continue
                    try:
                        cb(o)
                    except Exception as e:  # noqa: BLE001 - un consumatore non ferma gli altri
                        self.conti["errori_consumatori"] += 1
                        logger.error("[ordini-conto] consumatore %r KO su %s: %s",
                                     getattr(cb, "__name__", cb), o.bet_id, e)
