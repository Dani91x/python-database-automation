"""flusso_ordini_conto.py - lo stream degli ordini del CONTO, senza filtro di strategia, in SOLA LETTURA.

Scopo (priorita' dell'utente, T11; ``contratto.FlussoOrdiniConto``): portare in
tempo reale OGNI ordine del conto Betfair (app, bot, sito, scalper, Mike) a chi lo
deve vedere: il ladder di Trading, il libro ordini del comparto C, la Salute. E'
una sottoscrizione ``orderSubscription`` della Exchange Stream API su una
connessione SUA, costruita con le classi VERE di betfairlightweight:
``APIClient.streaming.create_stream`` -> ``BetfairStream`` (socket, CRLF,
autenticazione) -> ``StreamListener`` -> ``OrderStream`` -> ``OrderBookCache``
(``UnmatchedOrder``). Qui si aggiunge solo cio' che la libreria non fa: la
conversione in ``OrdineDalConto``, la ripresa dopo una caduta, la salute, il
watchdog, i consumatori.

Le scelte del filtro (``filters.streaming_order_filter``):
* ``customer_strategy_refs`` ASSENTE: tutti gli ordini del conto, anche quelli
  senza riferimento (sito) e quelli di ogni bot;
* ``include_overall_position=True``: Betfair manda la posizione abbinata del conto
  per selezione (``mb``/``ml``), che la cache della libreria tiene aggiornata in
  delta (``Available.update``). E' la base del P&L di mercato anche per gli ordini
  EXECUTION_COMPLETE che dopo una caduta non tornano nell'immagine. Betfair la
  manda di serie (``true``): la si scrive esplicita. Una ``fullImage`` di mercato
  SOSTITUISCE le posizioni di quel mercato (un runner che non c'e' piu' esce);
* ``partition_matched_by_strategy_ref=False``: la posizione per strategia
  (``smc``) arriverebbe in delta, ma la cache di betfairlightweight 2.23.2 la
  memorizza SOLO alla creazione del runner e ignora i delta successivi
  (``streaming/cache.py:580-602``: aggiorna solo ``ml``, ``mb``, ``uo``): il dato
  in cache sarebbe vecchio. L'attribuzione per bot si fa sugli ordini (``rfs``,
  ``rfo``) nel comparto C. Meno traffico sulla connessione.

Ordini senza riferimenti (reperto di W1-C2, 09/10): in betfairlightweight 2.23.2
``UnmatchedOrder`` vuole ``rfo``, ``rfs``, ``p``, ``s``, ``pd`` e gli importi come
argomenti obbligatori e valida i codici in ``serialise``; l'esempio UFFICIALE di
Betfair non porta ``rfo``/``rfs``: un solo ordine cosi' farebbe cadere il messaggio e
lo stream. ``normalizza_ordini`` mette ``rfo``/``rfs`` = "" (default documentato) e
None negli altri campi assenti (MAI 0: il campo resta "assente" e
``OrdineDalContoEsteso.campi_assenti`` lo dice), poi prova OGNI ordine con la classe
vera PRIMA della cache: chi non va si toglie dal messaggio, si logga, si conta e si
segnala; gli altri passano.

Ordini non confermati: un ordine EXECUTABLE noto che una IMMAGINE (di sottoscrizione,
di mercato o di runner) non riporta si e' concluso a connessione giu' (o e' stato
scartato): resta nell'elenco con ``confermato=False`` (riconsegnato ai consumatori) e
in ``ordini_non_confermati()``; il comparto C lo riconcilia via REST. Torna confermato
alla prima notizia dallo stream.

Partenza da zero: una sottoscrizione SENZA clk riceve solo gli ordini EXECUTABLE (gli
EXECUTION_COMPLETE di prima arrivano "only when transitioning", documentazione
ufficiale): ``stato()["sottoscrizione"]`` dice ``ripresa_clk`` o ``da_zero`` e
``seme_rest_necessario`` avvisa il libro ordini di seminare da ``listCurrentOrders``.

Valuta: gli importi dello stream ORDINI sono gia' nella valuta del conto (EUR,
``Betfair/stream/valuta.py`` testata); la conversione GBP->EUR riguarda solo i book.

Ripresa: la sottoscrizione si rifa' con ``initialClk``/``clk`` dell'ultimo
messaggio completo (la libreria li tiene; con la segmentazione ``clk`` arriva
solo a fine segmento): Betfair risponde ``RESUB_DELTA`` con i soli cambi. Dopo
``INVALID_CLOCK``, un messaggio non applicabile o senza uno dei due clk si riparte
da immagine piena. Backoff fra i tentativi: 2, 4, 8, ... 60 s
(``attesa_di_backoff``), AZZERATO SOLO se la connessione caduta era rimasta su
oltre ``VIVA_DOPO_S`` dalla sottoscrizione: "ha ricevuto dati" NON basta (un
server che manda l'immagine e chiude a ogni giro farebbe una tempesta di
riconnessioni, seconda revisione A3-1); mai dopo ``ferma``. Le ultime attese
sono in ``stato()["ultime_attese_s"]``.

Salute e watchdog: ``stato()`` dice vivo/muto con la regola degli stream di mercato
(``Betfair/stream/stream_muto.stato_da_battiti``: 3 heartbeat senza messaggi =
muto; ``status`` 503 = latente), su orologio MONOTONO. Il watchdog chiude la
connessione muta oltre la stessa soglia e la fa ripartire con ripresa; la durata
della connessione si valuta PRIMA di chiuderla (una connessione su da ore che
diventa muta riparte dal backoff minimo, A3-2).

Connessioni (decisione del coordinatore, 09/10, DIVERGENZA da confermare con
l'utente): lo stream ordini usa UNA connessione e la riserva degli stream di mercato
NON vale per lui. Se chi crea il flusso passa ``disponibili`` (``connectionsAvailable``
letto da un'altra connessione, meglio con l'istante:
``GestoreFlussi.disponibili_con_istante``), le libere sono il valore PIU' RECENTE fra
quello e la risposta alla NOSTRA ultima autenticazione (+1: la nostra connessione,
caduta, ha liberato il suo slot): apre con libere >= 1 o valore ignoto; con 0 aspetta
``ATTESA_SLOT_S`` UNA volta e poi prova comunque (il valore puo' essere vecchio e un
tentativo con 0 libere non toglie lo slot a nessuno: Betfair rifiuta). Mai "in
attesa" per sempre. Un rifiuto di Betfair (``MAX_CONNECTION_LIMIT_EXCEEDED``) fa
ritentare con il backoff (2..60 s). Dopo ogni SUA autenticazione il valore vero
(``connectionsAvailable`` della risposta) vale finche' e' il piu' recente.

Entrate: una ``Sessione`` (``contratto.Sessione``; se offre anche
``segnala_sessione_morta(motivo)`` - ``SessioneConSegnalazione`` - la si usa dopo
``NO_SESSION``). Uscite: ``OrdineDalContoEsteso`` ai consumatori (thread proprio),
``ordini()``, ``posizioni()``, ``ordini_non_confermati()``, ``stato()``.

Cosa NON fa: non piazza, non annulla, non modifica ordini (nessun metodo lo fa);
non tocca lo stream ordini che flumine apre per i bot; non attribuisce gli ordini
(e' del comparto C); non scrive DB ne' file. Importare il modulo non apre socket
ne' thread: tutto nasce in ``avvia`` e muore in ``ferma``.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import logging
import collections
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Set, Tuple

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
#: battiti senza messaggi oltre i quali il watchdog chiude e riprende. Betfair dice
#: "2 x heartbeat = forse disconnesso"; si usa 3 (``stream_muto.BATTITI_PER_SOGLIA``):
#: la stessa soglia del "muto" di tutta l'app (un solo numero, mai due verdetti
#: diversi) e un battito di margine contro il ritardo di un singolo heartbeat.
BATTITI_WATCHDOG = _SM.BATTITI_PER_SOGLIA
#: backoff della riconnessione (s): 2, 4, 8, ... fino a 60 (``attesa_di_backoff``)
BACKOFF_MIN_S = 2.0
BACKOFF_MAX_S = 60.0
#: SOLO una connessione rimasta su oltre tanto dalla sottoscrizione azzera il backoff
#: (non basta che abbia ricevuto dati: immagine e chiusura a ogni giro = tempesta)
VIVA_DOPO_S = 60.0
#: quante attese di backoff recenti si mostrano nello stato
ATTESE_RICORDATE = 20
#: ordini EXECUTION_COMPLETE tenuti in memoria (i piu' vecchi escono oltre il tetto)
TETTO_COMPLETATI = 5000
#: con 0 connessioni libere dichiarate si aspetta tanto, UNA volta, poi si prova comunque
ATTESA_SLOT_S = 30.0
#: codici Betfair dopo i quali la sessione e' da rifare
CODICI_SESSIONE = frozenset({"NO_SESSION", "INVALID_SESSION_INFORMATION",
                             "NOT_AUTHORIZED", "INVALID_APP_KEY"})
#: codici Betfair = "connessione non concessa"
CODICI_SLOT = frozenset({"MAX_CONNECTION_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS"})
#: codice Betfair del clk non valido: si riparte da immagine piena
CODICE_CLK_NON_VALIDO = "INVALID_CLOCK"

_EPOCA = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
#: segnaposto: ``disponibili`` non ancora letto
_NON_LETTO = object()
_LATI = {StreamingSide.B.name: "back", StreamingSide.L.name: "lay"}
#: campi IMPORTO dello stream: assenti -> None e dichiarati in ``campi_assenti``
_IMPORTI = ("sm", "sr", "sl", "sc", "sv")


@dataclasses.dataclass(frozen=True)
class OrdineDalContoEsteso(OrdineDalConto):
    """``OrdineDalConto`` + due campi (estensione ADDITIVA proposta nel referto).

    ``campi_assenti``: chiavi dello stream che Betfair non ha mandato per questo
    ordine (il valore relativo e' None, mai 0). ``confermato``: False se un'immagine
    piena non l'ha piu' riportato (concluso a connessione giu': da riconciliare)."""

    campi_assenti: Tuple[str, ...] = ()
    confermato: bool = True


class SessioneConSegnalazione(Sessione, Protocol):
    """Estensione proposta di ``contratto.Sessione``: chi usa la sessione DICE che
    Betfair l'ha rifiutata (``rinnova_se_serve`` puo' essere a timer e non forzare)."""

    def segnala_sessione_morta(self, motivo: str) -> None: ...


def _ms(data: Optional[_dt.datetime]) -> Optional[int]:
    """Datetime della libreria (``utcfromtimestamp(pd / 1e3)``) -> ms epoch esatti."""
    if data is None:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=_dt.timezone.utc)
    d = data - _EPOCA
    return d.days * 86_400_000 + d.seconds * 1000 + int(round(d.microseconds / 1000.0))


def attesa_di_backoff(tentativo: int, minimo: float, massimo: float) -> float:
    """Attesa prima del tentativo ``tentativo`` (1, 2, ...): ``minimo`` raddoppiato a
    ogni caduta, al massimo ``massimo`` (2, 4, 8, ... 60 s con i valori di serie)."""
    t = max(1, int(tentativo))
    return float(min(massimo, minimo * (2 ** min(t - 1, 30))))


def _num(v: Any) -> Optional[float]:
    """Importo dello stream: None se assente (mai 0 al posto di assente, PSB 7 n.21)."""
    return float(v) if v is not None else None


def ordine_dalla_cache(uo: UnmatchedOrder, market_id: str, selection_id: int,
                       handicap: Any, ricevuto_ms: int,
                       campi_assenti: Tuple[str, ...] = ()) -> OrdineDalContoEsteso:
    """``UnmatchedOrder`` della cache di betfairlightweight -> ``OrdineDalContoEsteso``.

    Nessuna interpretazione: i codici brevi dello stream (``B``/``L``, ``E``/``EC``,
    ``L``/``P``/``MOC``) si traducono con gli enum della libreria; ``avp`` e gli
    importi assenti restano None (la libreria, serializzando, metterebbe 0.0). Un
    codice sconosciuto solleva ``KeyError`` (chi chiama lo logga col motivo)."""
    return OrdineDalContoEsteso(
        bet_id=str(uo.bet_id),
        market_id=str(market_id),
        selection_id=int(selection_id),
        handicap=float(handicap or 0.0),
        lato=_LATI[uo.side],  # type: ignore[arg-type]
        # BSP senza prezzo/size: ASSENTI (None), mai 0 (PSB 7 n.21); proposta Optional nel contratto
        prezzo=float(uo.price) if uo.price is not None else None,  # type: ignore[arg-type]
        importo=float(uo.size) if uo.size is not None else None,  # type: ignore[arg-type]
        stato=StreamingStatus[uo.status].value,
        persistenza=(StreamingPersistenceType[uo.persistence_type].value
                     if uo.persistence_type else None),
        tipo=StreamingOrderType[uo.order_type].value if uo.order_type else None,
        piazzato_ms=_ms(uo.placed_date),
        abbinato_ms=_ms(uo.matched_date),
        abbinato=_num(uo.size_matched),  # type: ignore[arg-type]
        residuo=_num(uo.size_remaining),  # type: ignore[arg-type]
        scaduto=_num(uo.size_lapsed),  # type: ignore[arg-type]
        annullato=_num(uo.size_cancelled),  # type: ignore[arg-type]
        annullato_da_betfair=_num(uo.size_voided),  # type: ignore[arg-type]
        prezzo_medio=float(uo.average_price_matched) if uo.average_price_matched is not None else None,
        customer_order_ref=uo.reference_order or None,
        customer_strategy_ref=uo.reference_strategy or None,
        regulator_code=uo.regulator_code or None,
        ricevuto_ms=int(ricevuto_ms),
        campi_assenti=tuple(campi_assenti),
    )


# ---------------------------------------------------------------------------
# normalizzazione PRIMA della cache della libreria
# ---------------------------------------------------------------------------
#: valori DI SERIE dei campi che Betfair puo' non mandare, con la fonte
#: (``AUDIT_2026-10-02/_fonti_betfair/bf_2687396.txt``, pagina "Exchange Stream API"):
#: * ``rfo``/``rfs``: "default is ''" (riga 909); l'esempio ufficiale di riga 1108 non li porta;
#: * importi (``sm``/``sr``/``sl``/``sc``/``sv``), ``p``/``s``/``pd``: nessun default
#:   documentato ("there will be no sc because a BSP bet does not have any Size before
#:   reconciliation", riga 1120): restano ASSENTI (None) e l'ordine lo dichiara.
_DI_SERIE_UO: Dict[str, Any] = {"rfo": "", "rfs": "", "p": None, "s": None, "pd": None,
                                "sm": None, "sr": None, "sl": None, "sc": None, "sv": None}
_RIFERIMENTI = ("rfo", "rfs")


def _prova_ordine(uo: Mapping[str, Any], publish_time: int, market_id: Any, sel: Any,
                  hc: Any) -> Optional[str]:
    """Prova l'ordine con la classe VERA della libreria (costruzione + ``serialise``)
    PRIMA di dargli il messaggio: None se va, altrimenti il motivo."""
    try:
        UnmatchedOrder(publish_time, **uo).serialise(True, market_id, sel, hc)
    except (TypeError, KeyError, ValueError, AttributeError) as e:
        return "%s: %s" % (type(e).__name__, e)
    return None


def normalizza_ordini(data: list, publish_time: int = 0
                      ) -> Tuple[List[str], Dict[str, Tuple[str, ...]]]:
    """Prepara IN PLACE il messaggio ``oc`` per la cache della libreria.

    Ordine per ordine: i campi assenti prendono il valore di serie (``_DI_SERIE_UO``:
    "" per i riferimenti, None per il resto), poi l'ordine si prova con la classe
    vera (``_prova_ordine``); se non va si toglie dal messaggio (gli altri passano), si
    logga col motivo e il suo ``id`` torna fra gli scartati. Ritorna (scartati,
    {bet_id: campi assenti diversi dai riferimenti})."""
    scartati: List[str] = []
    assenti: Dict[str, Tuple[str, ...]] = {}
    for oc in data or []:
        for orc in oc.get("orc") or []:
            uos = orc.get("uo")
            if not uos:
                continue
            tenuti = []
            for uo in uos:
                mancano = tuple(k for k in _DI_SERIE_UO if k not in uo)
                for k in mancano:
                    uo[k] = _DI_SERIE_UO[k]
                motivo = _prova_ordine(uo, publish_time, oc.get("id"), orc.get("id"), orc.get("hc", 0))
                if motivo is not None:
                    scartati.append(str(uo.get("id")))
                    logger.error("[ordini-conto] ordine %s del mercato %s non applicabile (%s): "
                                 "tolto dal messaggio, da riconciliare via REST",
                                 uo.get("id"), oc.get("id"), motivo)
                    continue
                veri = tuple(k for k in mancano if k not in _RIFERIMENTI)
                if veri:
                    assenti[str(uo.get("id"))] = veri
                tenuti.append(uo)
            orc["uo"] = tenuti
    return scartati, assenti


# ---------------------------------------------------------------------------
# listener e stream: la catena VERA della libreria, con le osservazioni in piu'
# ---------------------------------------------------------------------------
class _OrderStreamConto(OrderStream):
    """``OrderStream`` di betfairlightweight che, PRIMA, rende il messaggio
    applicabile dalla cache (``normalizza_ordini``) e, DOPO aver aggiornato la
    cache (``super()._process``), passa al listener il messaggio appena applicato."""

    def _process(self, data: list, publish_time: int) -> bool:
        scartati, assenti = normalizza_ordini(data, publish_time)
        img = super()._process(data, publish_time)
        self._listener.cambiati(self, data, scartati, assenti)
        return img


class ListenerConto(StreamListener):
    """``StreamListener`` vero (``lightweight=True``: nessuna risorsa costruita
    inutilmente, la cache resta quella della libreria) con il battito della
    connessione (orologio MONOTONO), le immagini e la conversione degli ordini."""

    def __init__(self, su_ordini: Callable[[List[OrdineDalContoEsteso], Dict[str, Any]], None],
                 orologio_ms: Callable[[], float],
                 orologio_mono: Callable[[], float] = time.monotonic,
                 fine_immagine: Optional[Callable[[Set[str]], None]] = None,
                 su_connessioni: Optional[Callable[[int], None]] = None) -> None:
        super().__init__(output_queue=None, max_latency=None, lightweight=True,
                         order_updates_only=True)
        self._su_ordini = su_ordini
        self._ora_ms = orologio_ms
        self._mono = orologio_mono
        self._fine_immagine = fine_immagine
        self._su_connessioni = su_connessioni
        self.ultimo_msg_mono: Optional[float] = None
        self.ultimo_dato_mono: Optional[float] = None
        self.autenticato = False
        self.ultimo_errore: Optional[str] = None
        # betfairlightweight tiene ``connectionsAvailable`` solo se vero: qui anche lo 0
        self.connessioni_disponibili: Optional[int] = None
        self.heartbeat_ms_server: Optional[int] = None
        self.errori_conversione = 0
        self.errore_elaborazione = False
        self.messaggi = 0
        self.ocm = 0
        self._immagine: Optional[Set[str]] = None

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

    def _on_change_message(self, data: dict, unique_id: int) -> None:
        """Le IMMAGINI di sottoscrizione (``SUB_IMAGE``, anche a segmenti e anche
        vuote): a fine immagine chi non c'era non e' piu' confermato."""
        ct, seg = data.get("ct", "UPDATE"), data.get("segmentType")
        if ct == "SUB_IMAGE" and seg in (None, "SEG_START"):
            self._immagine = set()
        super()._on_change_message(data, unique_id)
        if ct == "SUB_IMAGE" and seg in (None, "SEG_END") and self._immagine is not None:
            visti, self._immagine = self._immagine, None
            if self._fine_immagine is not None:
                self._fine_immagine(visti)

    def _osserva(self, raw_data: str) -> None:
        """Battito (qualunque messaggio), esito dell'autenticazione, errori."""
        self.ultimo_msg_mono = self._mono()
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
                if self._su_connessioni is not None:
                    self._su_connessioni(disp)      # il valore VERO della nostra autenticazione
            if d.get("statusCode") == "SUCCESS":
                self.autenticato = True
                self.ultimo_errore = None
            elif d.get("statusCode") == "FAILURE":
                self.autenticato = False
                self.ultimo_errore = str(d.get("errorCode") or "FAILURE")
                logger.warning("[ordini-conto] Betfair FAILURE %s: %s", self.ultimo_errore,
                               str(d.get("errorMessage") or "")[:160])
        elif op == "ocm":
            self.ocm += 1
            hb = d.get("heartbeatMs")
            if isinstance(hb, int) and not isinstance(hb, bool) and hb > 0:
                self.heartbeat_ms_server = hb
            if d.get("oc"):
                self.ultimo_dato_mono = self.ultimo_msg_mono

    def cambiati(self, stream: OrderStream, data: list, scartati: Optional[List[str]] = None,
                 assenti: Optional[Dict[str, Tuple[str, ...]]] = None) -> None:
        """Gli ordini toccati dal messaggio, letti dalla cache GIA' aggiornata."""
        ricevuto = int(self._ora_ms())
        ordini: List[OrdineDalContoEsteso] = []
        info: Dict[str, Any] = {"immagini": {}, "immagini_runner": {}, "posizioni": {},
                                "posizioni_da_rifare": set(), "chiusi": [],
                                "scartati": list(scartati or []), "assenti": dict(assenti or {})}
        for oc in data:
            mid = str(oc.get("id"))
            cache = stream._caches.get(mid)
            if cache is None:
                continue
            if oc.get("closed"):
                info["chiusi"].append(mid)
            if oc.get("fullImage"):
                info["immagini"][mid] = set()
                info["posizioni_da_rifare"].add(mid)
            for orc in oc.get("orc") or []:
                self._runner(cache, mid, orc, ricevuto, ordini, info)
        if self._immagine is not None:
            self._immagine.update(o.bet_id for o in ordini)
        self._su_ordini(ordini, info)

    def _runner(self, cache: Any, mid: str, orc: Mapping[str, Any], ricevuto: int,
                ordini: List[OrdineDalContoEsteso], info: Dict[str, Any]) -> None:
        sel, hc = orc.get("id"), orc.get("hc", 0)
        runner = cache.runners.get((sel, hc))
        if runner is None:
            return
        chiave = (mid, int(sel), float(hc or 0.0))
        if orc.get("fullImage"):
            info["immagini_runner"][chiave] = set()
        if "mb" in orc or "ml" in orc or orc.get("fullImage") or mid in info["posizioni_da_rifare"]:
            info["posizioni"][chiave] = {
                "abbinati_back": [[d["price"], d["size"]] for d in runner.matched_backs.serialised],
                "abbinati_lay": [[d["price"], d["size"]] for d in runner.matched_lays.serialised],
            }
        for uo in orc.get("uo") or []:
            bet = runner.unmatched_orders.get(uo.get("id"))
            if bet is None:
                continue
            try:
                ordini.append(ordine_dalla_cache(bet, mid, sel, hc, ricevuto,
                                                 info["assenti"].get(str(bet.bet_id), ())))
            except (KeyError, TypeError, ValueError) as e:
                self.errori_conversione += 1
                logger.error("[ordini-conto] ordine %s non convertibile (%s: %s)",
                             uo.get("id"), type(e).__name__, e)
                continue
            if mid in info["immagini"]:
                info["immagini"][mid].add(str(bet.bet_id))
            if chiave in info["immagini_runner"]:
                info["immagini_runner"][chiave].add(str(bet.bet_id))


def _crea_stream_libreria(client: Any, unique_id: int, listener: StreamListener) -> Any:
    """``APIClient.streaming.create_stream`` (betfairlightweight)."""
    return client.streaming.create_stream(unique_id=unique_id, listener=listener)


def _codice_errore(e: BaseException, listener: ListenerConto) -> str:
    if listener.ultimo_errore:
        return listener.ultimo_errore
    testo = str(e).upper()
    for codice in sorted(CODICI_SESSIONE | CODICI_SLOT | {CODICE_CLK_NON_VALIDO}):
        if codice in testo:
            return codice
    return type(e).__name__


def segnala_sessione(sessione: Any, motivo: str) -> str:
    """Dice alla sessione che Betfair l'ha rifiutata: ``segnala_sessione_morta``
    se c'e' (``SessioneConSegnalazione``), altrimenti ``rinnova_se_serve`` (che puo'
    NON forzare un rinnovo). Ritorna il metodo usato."""
    segnala = getattr(sessione, "segnala_sessione_morta", None)
    if callable(segnala):
        segnala(motivo)
        return "segnala_sessione_morta"
    sessione.rinnova_se_serve()
    return "rinnova_se_serve"


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
                 disponibili: Optional[Callable[[], Any]] = None,
                 crea_stream: Callable[[Any, int, StreamListener], Any] = _crea_stream_libreria,
                 orologio_ms: Callable[[], float] = lambda: time.time() * 1000.0,
                 orologio_mono: Callable[[], float] = time.monotonic,
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
        self._disponibili = disponibili
        self._crea_stream = crea_stream
        self._ora_ms = orologio_ms
        self._mono = orologio_mono
        self._id = int(id_iniziale)
        self._lock = threading.RLock()
        self._ordini: Dict[str, OrdineDalContoEsteso] = {}
        self._posizioni: Dict[Tuple[str, int, float], Dict[str, Any]] = {}
        self._non_confermati: Set[str] = set()
        self._chiusi: Set[str] = set()
        self._consumatori: List[Tuple[Callable[[OrdineDalConto], None], Optional[Set[str]]]] = []
        self._coda: "queue.Queue[Optional[List[OrdineDalContoEsteso]]]" = queue.Queue()
        self._fermo = threading.Event()
        self._forza_immagine = False
        self._listener = ListenerConto(self._su_ordini, orologio_ms, orologio_mono,
                                       self._su_fine_immagine, self._su_connessioni)
        self._stream: Any = None
        self._thread: Optional[threading.Thread] = None
        self._thread_consegna: Optional[threading.Thread] = None
        self._thread_watchdog: Optional[threading.Thread] = None
        self.conti: Dict[str, int] = {
            "connessioni": 0, "riconnessioni": 0, "riprese_con_clk": 0, "immagini_piene": 0,
            "ordini_ricevuti": 0, "ordini_scartati": 0, "errori_consumatori": 0,
            "rinnovi_sessione": 0, "riavvii_watchdog": 0, "slot_negati": 0,
            "attese_di_slot": 0, "completati_potati": 0,
        }
        self._avviato_ms: Optional[float] = None
        #: la sottoscrizione CORRENTE: "ripresa_clk" (RESUB_DELTA: nulla perso) o "da_zero"
        #: (immagine piena: Betfair manda SOLO gli EXECUTABLE; gli EXECUTION_COMPLETE di
        #: prima arrivano "only when transitioning", bf_2687396.txt:941 -> il libro ordini
        #: deve fare il seme REST da listCurrentOrders)
        self._sottoscrizione: Optional[str] = None
        self._sottoscrizione_ms: Optional[float] = None
        self._sottoscrizione_mono: Optional[float] = None
        #: il watchdog ha chiuso una connessione che era SANA (valutato prima di chiuderla)
        self._sana_al_watchdog = False
        #: le ultime attese di backoff (s), per la Salute e i test
        self._attese: "collections.deque[float]" = collections.deque(maxlen=ATTESE_RICORDATE)
        #: None | "in_attesa" (0 libere dichiarate: un'attesa, poi si prova) | "negato"
        #: (rifiuto di Betfair: si ritenta col backoff)
        self._slot: Optional[str] = None
        #: gia' atteso ``ATTESA_SLOT_S`` su 0 libere: il prossimo giro prova comunque
        self._slot_atteso = False
        #: ultimo ``connectionsAvailable`` noto: da ``disponibili`` o, dopo ogni
        #: autenticazione di QUESTA connessione, il valore vero della risposta
        self._libere_note: Optional[int] = None
        #: il valore della NOSTRA ultima autenticazione e il suo istante (orologio monotono)
        self._libere_proprie: Optional[int] = None
        self._libere_proprie_mono: Optional[float] = None
        #: ``disponibili`` senza istante: l'ultimo valore visto e quando e' cambiato
        self._altri_visto: Any = _NON_LETTO
        self._altri_mono: Optional[float] = None
        #: l'ultima decisione: quante libere e da quale fonte ("propria" | "prezzi")
        self._libere_usate: Optional[int] = None
        self._libere_fonte: Optional[str] = None
        self._sessione_segnalata: Optional[str] = None

    # ------------------------------------------------------------ contratto
    @property
    def filtro_ordini(self) -> Dict[str, Any]:
        """Il ``orderFilter`` mandato a Betfair (per i test e la Salute)."""
        return dict(self._filtro)

    def avvia(self) -> None:
        """Apre la connessione (thread proprio), la consegna e il watchdog."""
        if self._thread is not None:
            return
        self._fermo.clear()
        self._avviato_ms = self._ora_ms()
        self._thread_consegna = threading.Thread(target=self._consegna, name="ordini-conto-consegna",
                                                 daemon=True)
        self._thread_consegna.start()
        self._thread_watchdog = threading.Thread(target=self._watchdog, name="ordini-conto-watchdog",
                                                 daemon=True)
        self._thread_watchdog.start()
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
        for altro in (self._thread_consegna, self._thread_watchdog):
            if altro is not None:
                altro.join(timeout=max(0.1, fine - time.monotonic()))
        if t is not None and t.is_alive():
            logger.error("[ordini-conto] il thread della connessione non si e' fermato in %.1f s",
                         attesa_s)
        self._thread = None
        self._thread_consegna = None
        self._thread_watchdog = None

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
        """Ultimo stato noto di ogni ordine (anche EXECUTION_COMPLETE, entro
        ``TETTO_COMPLETATI``), per mercato. Gli ``OrdineDalContoEsteso`` dicono anche
        ``confermato`` e ``campi_assenti``."""
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
        """bet_id EXECUTABLE che un'immagine piena non ha piu' riportato, e ordini
        scartati: li riconcilia il comparto C (REST)."""
        with self._lock:
            return set(self._non_confermati)

    def stato(self) -> Mapping[str, object]:
        li = self._listener
        ora = self._mono()
        latente = li.status is not None and li.status != 200
        soglia_s = self._soglia_s()
        verdetto = _SM.stato_da_battiti(
            None if li.ultimo_msg_mono is None else li.ultimo_msg_mono * 1000.0,
            None if li.ultimo_dato_mono is None else li.ultimo_dato_mono * 1000.0,
            adesso_ms=ora * 1000.0, soglia_s=soglia_s, mercati=["conto"], latente=latente)
        avviato = self._thread is not None
        stream = self._stream
        with self._lock:
            n_ordini, n_mercati = len(self._ordini), len({o.market_id for o in self._ordini.values()})
            non_conf = len(self._non_confermati)
            n_cons = len(self._consumatori)
            chiusi = sorted(self._chiusi)[:50]
        return {
            "stato": ("assente" if not avviato else "vivo" if verdetto["vivo"] else "muto"),
            "motivo": verdetto["motivo"] if avviato else "non_avviato",
            "eta_ultimo_messaggio_s": verdetto["eta_s"],
            "eta_ultimo_ordine_s": (None if li.ultimo_dato_mono is None
                                    else round(ora - li.ultimo_dato_mono, 1)),
            "soglia_muto_s": soglia_s,
            "connesso": bool(stream is not None and getattr(stream, "running", False)),
            "autenticato": li.autenticato,
            "latente": latente,
            "initial_clk": li.initial_clk,
            "ultimo_clk": li.clk,
            "ultimo_errore": li.ultimo_errore,
            "connessioni_disponibili": li.connessioni_disponibili,
            "connessioni_libere_note": self._libere_note,
            "connessioni_libere_usate": self._libere_usate,
            "connessioni_libere_fonte": self._libere_fonte,
            "slot": self._slot,
            "ultime_attese_s": list(self._attese),
            "sessione_segnalata": self._sessione_segnalata,
            "heartbeat_ms": li.heartbeat_ms_server or self._heartbeat_ms,
            "filtro": self.filtro_ordini,
            "ordini": n_ordini,
            "mercati": n_mercati,
            "mercati_chiusi": chiusi,
            "non_confermati": non_conf,
            "consumatori": n_cons,
            "errori_conversione": li.errori_conversione,
            "messaggi": li.messaggi,
            "sottoscrizione": self._sottoscrizione,
            "sottoscrizione_ms": self._sottoscrizione_ms,
            # dopo una partenza da zero gli EXECUTION_COMPLETE precedenti NON arrivano:
            # il libro ordini (comparto C) semina da listCurrentOrders
            "seme_rest_necessario": self._sottoscrizione == "da_zero",
            **self.conti,
        }

    # ------------------------------------------------------------ connessione
    def _soglia_s(self) -> float:
        hb = (self._listener.heartbeat_ms_server or self._heartbeat_ms
              or _SM.HEARTBEAT_MS_MAX_RICHIESTA)
        return BATTITI_WATCHDOG * float(hb) / 1000.0

    def _connessione_sana(self) -> bool:
        """La connessione appena caduta e' rimasta su oltre ``VIVA_DOPO_S`` dalla
        sottoscrizione (azzera il backoff). Ricevere dati NON basta: un server che
        manda l'immagine e chiude a ogni giro non deve far ripartire da 2 s."""
        dal = self._sottoscrizione_mono
        if dal is None:
            return False
        return self._mono() - dal > VIVA_DOPO_S

    def _ciclo(self) -> None:
        tentativo = 0
        while not self._fermo.is_set():
            attesa_slot = self._slot_libero()
            if attesa_slot is not None:
                if self._fermo.wait(attesa_slot):
                    break
                continue
            try:
                self._connetti_e_leggi()
                if self._fermo.is_set():
                    break
                raise ConnectionError("lettura terminata senza ferma()")
            except Exception as e:  # noqa: BLE001 - si riconnette: niente resta muto in silenzio
                if self._fermo.is_set():
                    break
                # durata valutata PRIMA di azzerare il riferimento (anche dal watchdog)
                sana = self._connessione_sana() or self._sana_al_watchdog
                self._sana_al_watchdog = False
                self._sottoscrizione_mono = None
                if sana:
                    tentativo = 0
                tentativo += 1
                self._dopo_errore(e)
                attesa = attesa_di_backoff(tentativo, BACKOFF_MIN_S, BACKOFF_MAX_S)
                self._attese.append(attesa)
                logger.warning("[ordini-conto] connessione KO (%s): nuovo tentativo fra %.1f s",
                               str(e)[:160], attesa)
                if self._fermo.wait(attesa):
                    break
        logger.info("[ordini-conto] fermato")

    def _slot_libero(self) -> Optional[float]:
        """None = si apre adesso; altrimenti i secondi da aspettare.

        La riserva NON vale per lo stream ordini (UNA connessione). Le libere sono il
        valore PIU' RECENTE fra la nostra ultima autenticazione e ``disponibili()``
        (``_libere_adesso``). Con libere >= 1 o valore ignoto si apre; con 0 si aspetta
        ``ATTESA_SLOT_S`` UNA volta e poi si prova comunque: il valore puo' essere vecchio
        e con 0 libere Betfair rifiuta (backoff), senza togliere lo slot a nessuno."""
        if self._disponibili is None:
            return None
        if self._slot_atteso:
            self._slot_atteso = False
            return None                     # gia' aspettato su 0: si prova (decide Betfair)
        try:
            libere, fonte = self._libere_adesso()
        except Exception as e:  # noqa: BLE001 - lettura del budget fallita: si apre come oggi
            logger.warning("[ordini-conto] connectionsAvailable illeggibile (%s): si apre", e)
            return None
        self._libere_usate, self._libere_fonte = libere, fonte
        if libere is not None and libere < 1:
            if self._slot != "in_attesa":
                logger.warning("[ordini-conto] 0 connessioni libere dichiarate: lo stream ordini "
                               "aspetta %.0f s e poi prova comunque", ATTESA_SLOT_S)
            self._slot = "in_attesa"
            self._slot_atteso = True
            self.conti["attese_di_slot"] += 1
            return ATTESA_SLOT_S
        if self._slot == "in_attesa":
            self._slot = None
        return None

    def _libere_adesso(self) -> Tuple[Optional[int], Optional[str]]:
        """(connessioni libere, fonte): il valore PIU' RECENTE fra la NOSTRA ultima
        autenticazione ("propria") e ``disponibili()`` ("prezzi"). ``disponibili`` puo'
        tornare ``(valore, istante)`` (``GestoreFlussi.disponibili_con_istante``, stesso
        orologio monotono) o il solo valore: allora il suo istante e' quello in cui lo si
        e' visto cambiare. Il nostro valore non conta la nostra connessione, che qui e'
        giu' (si apre solo dopo una caduta o all'avvio): il suo slot e' di nuovo libero (+1)."""
        letto = self._disponibili() if self._disponibili is not None else None
        if isinstance(letto, tuple):
            altri, quando_altri = letto[0], letto[1]
        else:
            altri = letto
            if altri != self._altri_visto:
                self._altri_visto, self._altri_mono = altri, self._mono()
            quando_altri = self._altri_mono
        if altri is not None:
            self._libere_note = int(altri)
        proprie, quando_proprie = self._libere_proprie, self._libere_proprie_mono
        if proprie is not None and (altri is None or quando_altri is None
                                    or quando_proprie >= quando_altri):
            return int(proprie) + 1, "propria"
        if altri is None:
            return None, None
        return int(altri), "prezzi"

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
        self._slot = None
        self.conti["connessioni"] += 1
        self.conti["riprese_con_clk" if ripresa else "immagini_piene"] += 1
        self._sottoscrizione = "ripresa_clk" if ripresa else "da_zero"
        self._sottoscrizione_ms = self._ora_ms()
        self._sottoscrizione_mono = self._mono()
        logger.info("[ordini-conto] sottoscrizione %s (%s)", self._id,
                    "ripresa con clk" if ripresa else "immagine piena")
        if self._fermo.is_set():
            stream.stop()
            return
        stream.start()

    def _su_connessioni(self, libere: int) -> None:
        """Nel thread del socket, alla risposta della NOSTRA autenticazione: il valore
        vero di ``connectionsAvailable``, con il suo istante (vince se e' il piu' recente)."""
        self._libere_note = int(libere)
        self._libere_proprie, self._libere_proprie_mono = int(libere), self._mono()

    def _dopo_errore(self, e: BaseException) -> None:
        """Conta e decide cosa rifare (immagine piena, sessione); l'attesa e' il backoff."""
        li = self._listener
        self.conti["riconnessioni"] += 1
        codice = _codice_errore(e, li)
        if codice == CODICE_CLK_NON_VALIDO or li.errore_elaborazione:
            self._forza_immagine = True
            li.errore_elaborazione = False
        if codice in CODICI_SLOT:
            self._slot = "negato"
            self.conti["slot_negati"] += 1
            logger.error("[ordini-conto] Betfair ha rifiutato la connessione (%s): si ritenta "
                         "con il backoff", codice)
        if codice in CODICI_SESSIONE:
            self.conti["rinnovi_sessione"] += 1
            try:
                self._sessione_segnalata = segnala_sessione(self._sessione, codice)
            except Exception as ex:  # noqa: BLE001 - si ritenta al giro dopo
                logger.warning("[ordini-conto] rinnovo della sessione KO: %s", ex)
        li.autenticato = False

    def _watchdog(self) -> None:
        while not self._fermo.wait(max(0.05, min(1.0, self._soglia_s() / 4.0))):
            try:
                self._veglia()
            except Exception as e:  # noqa: BLE001 - il watchdog non muore
                logger.warning("[ordini-conto] giro del watchdog KO: %s", e)

    def _veglia(self) -> bool:
        """Un giro del watchdog: connessione su ma senza NESSUN messaggio (neanche
        heartbeat) da oltre ``BATTITI_WATCHDOG`` heartbeat, contati dal piu' recente
        fra l'ultimo messaggio e la sottoscrizione: si chiude; il ciclo la riapre con
        ripresa (``initialClk``/``clk``). True se l'ha chiusa."""
        stream, li = self._stream, self._listener
        dal = self._sottoscrizione_mono
        if stream is None or dal is None or not getattr(stream, "running", False):
            return False
        ultimo = max(li.ultimo_msg_mono or 0.0, dal)
        muto = self._mono() - ultimo
        if muto <= self._soglia_s():
            return False
        self.conti["riavvii_watchdog"] += 1
        logger.warning("[ordini-conto] stream ordini MUTO da %.1f s (soglia %.1f s): "
                       "chiudo e riprendo", muto, self._soglia_s())
        # A3-2: la durata si valuta PRIMA di azzerare il riferimento della sottoscrizione
        self._sana_al_watchdog = self._connessione_sana()
        self._sottoscrizione_mono = None
        try:
            stream.stop()
        except Exception as e:  # noqa: BLE001 - il ciclo riprova comunque
            logger.warning("[ordini-conto] stop dal watchdog: %s", e)
        return True

    # ------------------------------------------------------------ ordini
    def _su_ordini(self, ordini: List[OrdineDalContoEsteso], info: Dict[str, Any]) -> None:
        """Nel thread del socket: aggiorna lo stato (subito leggibile) e accoda."""
        uscita: List[OrdineDalContoEsteso] = []
        with self._lock:
            for o in ordini:
                self._ordini[o.bet_id] = o
                self._non_confermati.discard(o.bet_id)
            uscita.extend(ordini)
            for mid, visti in info["immagini"].items():
                uscita.extend(self._non_piu_confermati(
                    b for b, o in self._ordini.items() if o.market_id == mid and b not in visti))
            for (mid, sel, hc), visti in info["immagini_runner"].items():
                uscita.extend(self._non_piu_confermati(
                    b for b, o in self._ordini.items()
                    if (o.market_id, o.selection_id, o.handicap) == (mid, sel, hc) and b not in visti))
            for mid in info["posizioni_da_rifare"]:
                for k in [k for k in self._posizioni if k[0] == mid]:
                    del self._posizioni[k]
            self._posizioni.update(info["posizioni"])
            self._non_confermati.update(info["scartati"])
            self.conti["ordini_scartati"] += len(info["scartati"])
            self._chiusi.update(info["chiusi"])
            self.conti["ordini_ricevuti"] += len(ordini)
            self._pota()
        if uscita:
            self._coda.put(uscita)

    def _su_fine_immagine(self, visti: Set[str]) -> None:
        """Fine di un'immagine di SOTTOSCRIZIONE: ogni EXECUTABLE noto non riportato
        (in QUALUNQUE mercato, anche a immagine vuota) non e' piu' confermato."""
        with self._lock:
            uscita = self._non_piu_confermati(b for b in list(self._ordini) if b not in visti)
        if uscita:
            self._coda.put(uscita)

    def _non_piu_confermati(self, bet_ids: Any) -> List[OrdineDalContoEsteso]:
        """Sotto ``_lock``: segna gli EXECUTABLE dati come non confermati; ritorna
        quelli cambiati (da riconsegnare ai consumatori con ``confermato=False``)."""
        cambiati: List[OrdineDalContoEsteso] = []
        for b in list(bet_ids):
            o = self._ordini.get(b)
            if o is None or o.stato != "EXECUTABLE":
                continue
            self._non_confermati.add(b)
            if o.confermato:
                nuovo = dataclasses.replace(o, confermato=False)
                self._ordini[b] = nuovo
                cambiati.append(nuovo)
        return cambiati

    def _pota(self) -> None:
        """Sotto ``_lock``: oltre ``TETTO_COMPLETATI`` ordini EXECUTION_COMPLETE escono
        i piu' vecchi (per ``ricevuto_ms``). Gli EXECUTABLE non escono mai."""
        completi = [o for o in self._ordini.values() if o.stato == "EXECUTION_COMPLETE"]
        oltre = len(completi) - TETTO_COMPLETATI
        if oltre <= 0:
            return
        for o in sorted(completi, key=lambda x: (x.ricevuto_ms, x.bet_id))[:oltre]:
            del self._ordini[o.bet_id]
            self._non_confermati.discard(o.bet_id)
        self.conti["completati_potati"] += oltre

    def _consegna(self) -> None:
        while True:
            lotto = self._coda.get()
            if lotto is None:
                return
            consumatori = self._consumatori      # copia sostituita, mai modificata in place
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
