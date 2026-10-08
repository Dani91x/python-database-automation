"""frammenti_mercato.py - la connessione di mercato del runner calcio a FRAMMENTI (28/09/2026).

Ordine dell'utente (28/09, testuale): «questo va risolto, informati sulla
documentazione e sulle migliori pratiche, non possiamo lasciare eventi "fuori",
noi lavoriamo sul volume.»

PRIMA: il runner calcio seguiva tutto su UNA connessione di mercato, tetto 180
mercati (``HARD_MARKET_CAP``). Il 26/09 era SATURO (179/180) e 24 partite idonee
del feed sono rimaste fuori dall'auto-follow, in silenzio.

I LIMITI VERI (Betfair Exchange Stream API, referto
``AUDIT_2026-09-28/CANTIERE_B_CAPACITA_MERCATI.md``): 200 mercati per
SOTTOSCRIZIONE (``SUBSCRIPTION_LIMIT_EXCEEDED``), una sottoscrizione per
connessione (una nuova SOSTITUISCE la precedente), un numero di connessioni
contemporanee per conto/app key (10 di serie, ``MAX_CONNECTION_LIMIT_EXCEEDED``;
``connectionsAvailable`` nella risposta all'autenticazione dice quante se ne
possono ancora aprire). Quindi la capacita' si allarga solo con PIU'
CONNESSIONI, ognuna con la sua sottoscrizione: i frammenti.

DOPO: lo stesso framework flumine (stessi worker, stesso blotter, stesse
strategie) riceve i book da N ``MarketStream`` (N connessioni), ognuna con al
massimo ``per_conn`` mercati. Il frammento 0 e' quello che flumine crea al
``add_strategy``; gli altri li apre e li chiude QUI, a caldo, mentre il
framework gira (mai un riavvio: il blotter e le posizioni restano quelli).

Regole (tutte provate in ``tests/test_frammenti_mercato_2026_09_28.py``):

* UN MERCATO NON CAMBIA MAI FRAMMENTO finche' il suo frammento e' vivo: una
  partita con posizione aperta o ordine in corso non perde mai la sottoscrizione
  per un ribilanciamento. I mercati nuovi riempiono i frammenti esistenti in
  ordine; un frammento nuovo si apre solo quando gli altri sono pieni.
* Si risottoscrive SOLO il frammento che cambia (immagine piena solo per lui).
* Un frammento in piu' rimasto vuoto si CHIUDE (la connessione torna libera per
  scanner, scalper, tennis). Il frammento 0 non resta mai con una
  sottoscrizione vuota (Betfair la leggerebbe come «tutto l'exchange»): se non
  serve piu' niente tiene i mercati di prima.
* Se Betfair RIFIUTA la connessione nuova (``MAX_CONNECTION_LIMIT_EXCEEDED``,
  ``TOO_MANY_REQUESTS``, o nessuna autenticazione entro ``ATTESA_APERTURA_S``)
  il frammento si chiude, i suoi mercati tornano al piano (``manutenzione``
  ritorna i "persi"), la capacita' scende per ``PAUSA_RIFIUTO_S`` e poi si
  riprova. Il piano dell'auto-follow allora fa uscire le voci MENO prioritarie
  (mai quelle con ordini): chi resta fuori e perche' e' scritto nello stato.
* Riserva: un frammento nuovo si apre solo se Betfair, all'ultima
  autenticazione, ha dichiarato piu' di ``riserva`` connessioni libere (le altre
  servono a scanner, scalper, tennis).
* RESILIENZA PER FRAMMENTO: ogni frammento ha il suo battito (qualunque
  messaggio, heartbeat compresi) misurato dal SUO listener. La riconnessione
  del singolo frammento la fa flumine (stessa logica della ``run`` di
  ``MarketStream``, con ``initialClk``/``clk``); un frammento MUTO oltre
  ``MUTO_S`` (180 s, la stessa finestra della ricostruzione per stallo del
  26/09) viene chiuso e i suoi mercati ripiazzati su una connessione nuova.
  Lo stallo di TUTTO lo stream resta al controllo del runner (``RAW_STATE``).
* Un frammento chiuso non si riconnette mai piu' da solo (prima una
  ``MarketStream`` in errore ritentava per sempre anche dopo ``stop()``:
  sarebbe stata una connessione fantasma che occupa il limite).

Nessun processo nuovo, nessuna chiamata Betfair in piu' oltre alle connessioni
e ai ``marketSubscription``. Nessun I/O verso il database.
ASCII-only nel codice; commenti in italiano.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import weakref
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from flumine.streams.historicalstream import HistoricalStream
from flumine.streams.marketstream import MarketStream

from . import sottoscrizione_a_caldo as _SC
from .raw_listener import RawTeeMarketStream, RawTeeStreamListener
from .runner_lifecycle import MSG_DATI, classifica_messaggio_stream

logger = logging.getLogger(__name__)

#: limite Betfair per SOTTOSCRIZIONE (docs Exchange Stream API: "set to 200
#: markets by default"); una connessione porta una sola sottoscrizione
LIMITE_BETFAIR_MERCATI = _SC.LIMITE_BETFAIR_MERCATI
#: connessioni contemporanee di serie per conto/app key (Betfair, alzabile dal BDP)
LIMITE_BETFAIR_CONNESSIONI = 10

#: connessioni di mercato massime del runner calcio (env RUNNER_CALCIO_STREAM_CONNS)
DEFAULT_MAX_CONNESSIONI = 3
#: connessioni che si lasciano libere agli altri processi (env RUNNER_CALCIO_STREAM_RISERVA)
DEFAULT_RISERVA = 1

#: un frammento nuovo non autenticato entro tanto = rifiutato (s)
ATTESA_APERTURA_S = 60.0
#: dopo un rifiuto non si aprono frammenti nuovi per tanto (s)
PAUSA_RIFIUTO_S = 300.0
#: un frammento senza NESSUN messaggio (neanche heartbeat) da tanto = muto (s)
MUTO_S = 180.0

#: codici Betfair che dicono «connessione non concessa» (la manutenzione chiude subito)
CODICI_RIFIUTO = frozenset({"MAX_CONNECTION_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS",
                            "SUBSCRIPTION_LIMIT_EXCEEDED"})

_RE_OP_STATUS = re.compile(r'"op"\s*:\s*"status"')
_RE_HEARTBEAT_MS = re.compile(r'"heartbeatMs"\s*:\s*(\d+)')


def _env_int(nome: str, default: int, lo: int, hi: int) -> int:
    """Intero da env con clamp [lo, hi]; vuoto/malformato -> default (mai ``??``)."""
    raw = (os.environ.get(nome) or "").strip()
    try:
        val = int(raw) if raw else default
    except ValueError:
        val = default
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# listener e stream del frammento: il battito PER CONNESSIONE
# ---------------------------------------------------------------------------
class FrammentoListener(RawTeeStreamListener):
    """Il listener del runner (tee del raw nativo, ``RawTeeStreamListener``) che
    in piu' misura la salute della SUA connessione. ``RAW_STATE`` e' unico per
    processo: con piu' connessioni un frammento morto sarebbe coperto dagli
    altri. Qui ogni frammento ha i suoi tempi e i suoi errori."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ultimo_msg_mono = 0.0       # qualunque messaggio (heartbeat compresi)
        self.ultimo_dato_mono = 0.0      # mcm con market change
        self.autenticato = False         # ultimo status = SUCCESS
        self.autenticato_una_volta = False
        self.ultimo_errore: Optional[str] = None   # errorCode dell'ultimo status FAILURE
        # betfairlightweight salva ``connectionsAvailable`` solo se VERO
        # (``if connections_available:``): lo 0 - il caso che conta - si
        # perderebbe. Qui si tiene anche lo 0.
        self.connessioni_disponibili: Optional[int] = None
        self.connessioni_lette_mono = 0.0
        # J2 (28/09): l'heartbeat VERO che Betfair ha rimandato a questa
        # connessione (``heartbeatMs`` dell'immagine iniziale, schema ESA): la
        # soglia dello stream muto e' 3 volte questo (``stream_muto.soglia_per``)
        self.heartbeat_ms_server: Optional[int] = None

    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            self._osserva(raw_data)
        except Exception:  # noqa: BLE001 - la misura non rompe mai lo stream
            pass
        return super().on_data(raw_data)

    def _osserva(self, raw_data: Any) -> None:
        ora = time.monotonic()
        self.ultimo_msg_mono = ora
        tipo = classifica_messaggio_stream(raw_data)
        if isinstance(raw_data, str) and '"heartbeatMs"' in raw_data:
            m = _RE_HEARTBEAT_MS.search(raw_data)
            if m:
                self.heartbeat_ms_server = int(m.group(1))
        if tipo == MSG_DATI:
            self.ultimo_dato_mono = ora
            return
        if tipo is not None or not isinstance(raw_data, str):
            return
        if not _RE_OP_STATUS.search(raw_data):
            return
        d = json.loads(raw_data)
        disp = d.get("connectionsAvailable")
        if isinstance(disp, int) and not isinstance(disp, bool):
            self.connessioni_disponibili = disp
            self.connessioni_lette_mono = ora
        esito = str(d.get("statusCode") or "").upper()
        if esito == "SUCCESS":
            self.autenticato = True
            self.autenticato_una_volta = True
            self.ultimo_errore = None
        elif esito == "FAILURE":
            self.autenticato = False
            self.ultimo_errore = str(d.get("errorCode") or "FAILURE")


# la run di MarketStream SENZA il retry infinito di tenacity: il ciclo di
# riconnessione e' quello sotto, che si ferma quando il frammento e' chiuso
_RUN_MARKETSTREAM = MarketStream.run.__wrapped__  # type: ignore[attr-defined]


class FrammentoMarketStream(RawTeeMarketStream):
    """``MarketStream`` del runner calcio (tee del raw + battito per connessione).

    Riconnessione: come flumine (``wait_exponential(min=2, max=60)``, riuso di
    ``initialClk``/``clk`` del listener), ma una volta chiuso (``stop``) il
    frammento NON si riconnette piu': la ``run`` di flumine con ``@retry``
    ritentava per sempre anche dopo ``stop()`` se era in errore."""

    LISTENER = FrammentoListener

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chiuso = False
        self.riconnessioni = 0
        self.aperto_mono = time.monotonic()
        self._pausa = threading.Event()

    def run(self) -> None:  # type: ignore[override]
        tentativo = 0
        while not self.chiuso:
            try:
                _RUN_MARKETSTREAM(self)
                return                          # stop() pulito: fine
            except Exception as e:  # noqa: BLE001 - come @retry di flumine
                if self.chiuso:
                    return
                tentativo += 1
                self.riconnessioni += 1
                attesa = max(2.0, min(60.0, float(2 ** tentativo)))
                logger.warning("[frammenti] MarketStream %s KO (%s): riconnessione fra %.0f s",
                               self.stream_id, str(e)[:120], attesa)
                self._pausa.wait(attesa)

    def stop(self) -> None:
        self.chiuso = True
        self._pausa.set()
        super().stop()


# ---------------------------------------------------------------------------
# il piano (puro)
# ---------------------------------------------------------------------------
@dataclass
class PianoFrammenti:
    #: sottoscrizione voluta per ogni frammento ESISTENTE (stesso ordine)
    bersagli: List[Set[str]]
    #: frammenti da aprire, ognuno con i suoi mercati
    nuovi: List[Set[str]] = field(default_factory=list)
    #: mercati voluti che non entrano (capacita' esaurita)
    fuori: Set[str] = field(default_factory=set)


def pianifica(attuali: List[Set[str]], voluti: Iterable[str], per_conn: int,
              max_conn: int) -> PianoFrammenti:
    """Distribuisce ``voluti`` sui frammenti.

    * ogni mercato gia' su un frammento RESTA li' (mai spostato);
    * i mercati nuovi (ordine deterministico) riempiono i frammenti esistenti
      in ordine, poi frammenti nuovi (ognuno <= ``per_conn``) fino a
      ``max_conn`` frammenti in tutto; il resto e' ``fuori``;
    * frammento 0 senza piu' niente di voluto: tiene i mercati di prima (mai
      una sottoscrizione vuota); un frammento in piu' vuoto: bersaglio vuoto
      (= da chiudere).
    """
    per_conn = max(1, min(int(per_conn), LIMITE_BETFAIR_MERCATI))
    max_conn = max(1, int(max_conn))
    vol = {str(m) for m in voluti if m}
    tenuti: List[Set[str]] = [set(a) & vol for a in attuali]
    gia = set().union(*tenuti) if tenuti else set()
    da_mettere = sorted(vol - gia)
    for t in tenuti:
        while da_mettere and len(t) < per_conn:
            t.add(da_mettere.pop(0))
    nuovi: List[Set[str]] = []
    while da_mettere and len(tenuti) + len(nuovi) < max_conn:
        blocco = set(da_mettere[:per_conn])
        da_mettere = da_mettere[per_conn:]
        nuovi.append(blocco)
    if tenuti and not tenuti[0]:
        tenuti[0] = set(attuali[0])             # mai vuoto: tiene quelli di prima
    return PianoFrammenti(bersagli=tenuti, nuovi=nuovi, fuori=set(da_mettere))


def primo_frammento(market_ids: Iterable[str], prima: Iterable[str], per_conn: int,
                    con_soldi: Iterable[str] = ()) -> List[str]:
    """I mercati del frammento 0 alla (ri)costruzione del framework, fino a
    ``per_conn``, in quest'ordine:

    1. ``con_soldi``: mercati con posizione aperta o ordine vivo (paper e
       live) e comandi in volo. Dopo una ricostruzione il blotter nuovo e'
       vuoto ma i soldi ci sono: questi mercati devono avere i dati SUBITO,
       sulla connessione che nasce col framework;
    2. ``prima``: le partite seguite a mano;
    3. gli altri, in ordine deterministico.

    Il resto lo apre l'auto-follow a caldo appena lo stream gira (flumine,
    all'avvio, aspetta che OGNI stream sia connesso: una connessione rifiutata
    bloccherebbe l'intero runner). Se i mercati con soldi sono PIU' di
    ``per_conn`` quelli in eccesso vanno nei frammenti aperti a caldo (qualche
    secondo dopo): il runner lo dichiara (``oltre_frammento0``)."""
    per_conn = max(1, min(int(per_conn), LIMITE_BETFAIR_MERCATI))
    tutti = {str(m) for m in market_ids if m}
    soldi = sorted(tutti & {str(m) for m in con_soldi})
    manuali = sorted((tutti & {str(m) for m in prima}) - set(soldi))
    dietro = sorted(tutti - set(soldi) - set(manuali))
    return (soldi + manuali + dietro)[:per_conn]


def mercati_con_ordini(framework: Any) -> Set[str]:
    """I mercati con ALMENO un ordine nel blotter del framework (paper e live,
    vivi o eseguiti: un eseguito e' una posizione). Letto alla fine di un
    framework per la costruzione successiva. Illeggibile -> insieme vuoto."""
    out: Set[str] = set()
    try:
        mercati = list(getattr(getattr(framework, "markets", None), "markets", {}).values())
    except Exception:  # noqa: BLE001
        return out
    for m in mercati:
        try:
            if len(list(iter(m.blotter))) > 0:
                out.add(str(m.market_id))
        except Exception:  # noqa: BLE001 - nel dubbio: con soldi
            out.add(str(getattr(m, "market_id", "") or ""))
    out.discard("")
    return out


def kwargs_stream_condiviso(recorder: Any) -> Dict[str, Any]:
    """I parametri di stream che una strategia deve avere per RIUSARE lo stream
    del recorder (``flumine.Streams.add_stream`` confronta classe,
    ``market_filter``, ``market_data_filter``, ``streaming_timeout`` e
    ``conflate_ms``).

    28/09: la ``LiveTradingStrategy`` veniva creata col solo ``market_filter``:
    il suo ``market_data_filter`` era quello di serie di flumine (senza
    ``ladderLevels``) e flumine apriva una SECONDA connessione di mercato con
    gli stessi mercati (sonda ``AUDIT_2026-09-28/sonda_stream_runner.py``: 2
    ``MarketStream``). In piu' quella seconda connessione non riceveva mai i
    mercati dell'auto-follow (la risottoscrizione a caldo tocca lo stream del
    recorder), quindi le chiusure di quei mercati non arrivavano alla
    strategia degli ordini."""
    return {
        "market_filter": recorder.market_filter,
        "market_data_filter": recorder.market_data_filter,
        "conflate_ms": recorder.conflate_ms,
        "streaming_timeout": recorder.streaming_timeout,
    }


class CapacitaInsufficiente(_SC.NonPronto):
    """I mercati voluti non entrano nelle connessioni concesse: niente e'
    cambiato; il piano dell'auto-follow deve rientrare nella capacita'."""


# ---------------------------------------------------------------------------
# il gestore (usato dal thread dell'auto-follow)
# ---------------------------------------------------------------------------
def _riferimento(oggetto: Any) -> Callable[[], Any]:
    """Un riferimento che non tiene in vita ``oggetto`` (weakref); se l'oggetto non lo
    consente (finti dei test), un riferimento normale: l'esito e' lo stesso."""
    try:
        return weakref.ref(oggetto)
    except TypeError:
        return lambda: oggetto


def _avvia_thread(stream: Any) -> None:
    stream.start()


class GestoreFrammenti:
    """Apre, risottoscrive e chiude i frammenti della connessione di mercato
    del runner calcio. Interfaccia per ``auto_follow.AutoFollow``:
    ``applica(framework, market_ids)`` (come ``SottoscrittoreStream``),
    ``manutenzione(framework)`` -> mercati persi, ``capacita(framework)`` ->
    mercati sottoscrivibili adesso, ``stato(framework)``.

    Senza stato proprio sui mercati: chi e' dove lo dice il filtro di ogni
    stream (``mercati_dello_stream``), cosi' un'applicazione a meta' (un
    frammento non ancora connesso) si completa al giro dopo senza doppioni."""

    def __init__(self, *, per_conn: int, max_conn: int, riserva: int = DEFAULT_RISERVA,
                 orologio: Callable[[], float] = time.monotonic,
                 avvia_stream: Callable[[Any], None] = _avvia_thread,
                 sottoscrivi: Optional[Callable[[Any, Any, List[str]], int]] = None) -> None:
        self.per_conn = max(1, min(int(per_conn), LIMITE_BETFAIR_MERCATI))
        self.max_conn = max(1, min(int(max_conn), LIMITE_BETFAIR_CONNESSIONI))
        self.riserva = max(0, int(riserva))
        self._ora = orologio
        self._avvia = avvia_stream
        self._sottoscrivi = sottoscrivi or _SC.sottoscrivi
        self._modello: Optional[Dict[str, Any]] = None
        # id(stream) -> (riferimento debole allo stream, prima volta visto). 08/10: il
        # riferimento serve a riconoscere un id() RICICLATO: un frammento chiuso da
        # flumine (non da ``_chiudi``) lascia la sua voce, e un frammento nuovo con lo
        # stesso id() ne ereditava il «dal» (test instabile
        # `test_auto_follow_rifiuto_betfair_rientra_e_dichiara`). Lo stream_id non va
        # bene come chiave: cambia all'iscrizione.
        self._visto_dal: Dict[int, Tuple[Callable[[], Any], float]] = {}
        self._rifiuto_mono: Optional[float] = None
        self.conti = {"aperture": 0, "chiusure": 0, "rifiuti": 0, "muti": 0,
                      "risottoscrizioni": 0}
        self.ultimo_rifiuto: Optional[str] = None
        self.ultimo_evento: Optional[str] = None
        self.motivo_limite: Optional[str] = None
        #: ultima costruzione del framework: mercati con soldi e dove sono finiti
        self.costruzione: Optional[Dict[str, Any]] = None

    def segna_costruzione(self, con_soldi: Iterable[str], frammento0: Iterable[str],
                          fonti: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Registra (per lo stato) i mercati con soldi alla costruzione e quanti
        NON sono entrati nel frammento 0 (piu' di ``per_conn``)."""
        soldi = {str(m) for m in con_soldi}
        oltre = sorted(soldi - {str(m) for m in frammento0})
        self.costruzione = {"con_soldi": len(soldi), "oltre_frammento0": len(oltre),
                            "oltre_frammento0_mercati": oltre[:50], "fonti": dict(fonti or {}),
                            "ts": time.time()}
        return self.costruzione

    @classmethod
    def da_ambiente(cls) -> "GestoreFrammenti":
        """``per_conn`` = il tetto per connessione di sempre (``tetto_mercati``:
        ``HARD_MARKET_CAP`` 180, mai oltre 200); ``RUNNER_CALCIO_STREAM_CONNS``
        (1..10, di serie 3); ``RUNNER_CALCIO_STREAM_RISERVA`` (0..9, di serie 1)."""
        from .auto_follow import tetto_mercati
        return cls(per_conn=tetto_mercati(),
                   max_conn=_env_int("RUNNER_CALCIO_STREAM_CONNS", DEFAULT_MAX_CONNESSIONI,
                                     1, LIMITE_BETFAIR_CONNESSIONI),
                   riserva=_env_int("RUNNER_CALCIO_STREAM_RISERVA", DEFAULT_RISERVA,
                                    0, LIMITE_BETFAIR_CONNESSIONI - 1))

    # ------------------------------------------------------------ letture
    @staticmethod
    def frammenti(framework: Any) -> List[Any]:
        """Le MarketStream di mercato vive del framework, in ordine di creazione."""
        out = []
        for s in list(getattr(framework, "streams", None) or []):
            if (isinstance(s, MarketStream) and not isinstance(s, HistoricalStream)
                    and not getattr(s, "chiuso", False)):
                out.append(s)
        return out

    @staticmethod
    def _connesso(stream: Any) -> bool:
        bs = getattr(stream, "_stream", None)
        return bool(bs is not None and getattr(bs, "running", False))

    def _connessioni_disponibili(self, fr: List[Any]) -> Optional[int]:
        """L'ultimo ``connectionsAvailable`` dichiarato da Betfair a uno dei
        nostri frammenti (None = mai letto)."""
        migliore: Optional[int] = None
        quando = -1.0
        for s in fr:
            li = getattr(s, "_listener", None)
            v = getattr(li, "connessioni_disponibili", None)
            t = float(getattr(li, "connessioni_lette_mono", 0.0) or 0.0)
            if v is not None and t > quando:
                migliore, quando = int(v), t
        return migliore

    def massimo_adesso(self, framework: Any) -> int:
        """Quanti frammenti si possono avere ADESSO: ``max_conn``, salvo pausa
        dopo un rifiuto o riserva di connessioni per gli altri processi (in quei
        casi: quelli gia' aperti, mai meno di 1)."""
        fr = self.frammenti(framework) if framework is not None else []
        aperti = max(1, len(fr))
        if (self._rifiuto_mono is not None
                and self._ora() - self._rifiuto_mono < PAUSA_RIFIUTO_S):
            self.motivo_limite = ("Betfair ha rifiutato una connessione (%s): nessuna "
                                  "connessione nuova per %.0f s" % (self.ultimo_rifiuto,
                                                                   PAUSA_RIFIUTO_S))
            return min(self.max_conn, aperti)
        disp = self._connessioni_disponibili(fr)
        if disp is not None and disp <= self.riserva and aperti < self.max_conn:
            self.motivo_limite = ("Betfair dichiara %d connessioni libere, riserva %d per "
                                  "scanner/scalper/tennis" % (disp, self.riserva))
            return min(self.max_conn, aperti)
        self.motivo_limite = ("tetto configurato: %d connessioni x %d mercati "
                              "(RUNNER_CALCIO_STREAM_CONNS)" % (self.max_conn, self.per_conn))
        return self.max_conn

    def capacita(self, framework: Any = None) -> int:
        """Mercati sottoscrivibili adesso (il tetto del piano dell'auto-follow)."""
        return self.massimo_adesso(framework) * self.per_conn

    # ------------------------------------------------------------ scritture
    def _ricorda_modello(self, s: Any) -> None:
        if self._modello is None:
            self._modello = {"cls": type(s), "market_data_filter": s.market_data_filter,
                             "streaming_timeout": s.streaming_timeout,
                             "conflate_ms": s.conflate_ms}

    def _strategie_di(self, framework: Any, s: Any) -> List[Any]:
        return [st for st in list(getattr(framework, "strategies", None) or [])
                if s in list(getattr(st, "streams", None) or [])]

    def _allinea_filtri(self, framework: Any) -> None:
        """Il ``market_filter`` di ogni strategia = la LISTA dei filtri dei suoi
        frammenti (``sottoscrivi`` gli scrive il solo filtro dello stream toccato)."""
        fr = self.frammenti(framework)
        for st in list(getattr(framework, "strategies", None) or []):
            suoi = [s for s in fr if s in list(getattr(st, "streams", None) or [])]
            if len(suoi) > 1:
                st.market_filter = [s.market_filter for s in suoi]
            elif len(suoi) == 1:
                st.market_filter = suoi[0].market_filter

    def _apri(self, framework: Any, fr: List[Any], ids: Set[str]) -> Any:
        if self._modello is None:
            raise _SC.NonPronto("nessun frammento di riferimento")
        m = self._modello
        streams = framework.streams
        sid = streams._increment_stream_id()
        s = m["cls"](flumine=framework, stream_id=sid,
                     market_filter=_SC.filtro_mercati(ids),
                     market_data_filter=m["market_data_filter"],
                     streaming_timeout=m["streaming_timeout"], conflate_ms=m["conflate_ms"])
        # CONCORRENZA: il ciclo principale di flumine legge queste liste da un
        # altro thread (``strategy.stream_ids`` = list comprehension su
        # ``strategy.streams``, ``strategy.py:238-242``; ``Streams.__iter__`` =
        # ``iter(self._streams)``, ``streams.py:321-322``). Mai modificarle sul
        # posto: si costruisce una lista NUOVA e si sostituisce il riferimento
        # (un'assegnazione e' atomica), cosi' chi sta iterando finisce sulla
        # vecchia intera e chi legge dopo vede la nuova intera.
        streams._streams = list(streams._streams) + [s]
        base = fr[0] if fr else None
        for st in list(getattr(framework, "strategies", None) or []):
            if base is None or base in list(getattr(st, "streams", None) or []):
                st.streams = list(st.streams) + [s]
        self._visto_dal[id(s)] = (_riferimento(s), self._ora())
        self._avvia(s)
        self.conti["aperture"] += 1
        self.ultimo_evento = "aperto frammento %s (%d mercati)" % (sid, len(ids))
        logger.warning("[frammenti] APERTO frammento %s con %d mercati (connessione in piu')",
                       sid, len(ids))
        return s

    def _chiudi(self, framework: Any, s: Any, motivo: str) -> Set[str]:
        persi = set(_SC.mercati_dello_stream(s))
        # copia e sostituzione, mai ``remove`` sul posto (vedi ``_apri``): un
        # ``remove`` durante la list comprehension di ``stream_ids`` fa SALTARE
        # l'elemento successivo, cioe' un book o una chiusura di un frammento sano
        for st in list(getattr(framework, "strategies", None) or []):
            lista = getattr(st, "streams", None)
            if isinstance(lista, list) and s in lista:
                st.streams = [x for x in lista if x is not s]
        contenitore = getattr(framework, "streams", None)
        interni = getattr(contenitore, "_streams", None)
        if isinstance(interni, list) and s in interni:
            contenitore._streams = [x for x in interni if x is not s]
        try:
            s.stop()
        except Exception as e:  # noqa: BLE001
            logger.warning("[frammenti] stop del frammento %s: %s", s.stream_id, str(e)[:120])
        self._visto_dal.pop(id(s), None)
        self.conti["chiusure"] += 1
        self.ultimo_evento = "chiuso frammento %s: %s" % (s.stream_id, motivo)
        logger.warning("[frammenti] CHIUSO frammento %s (%d mercati): %s",
                       s.stream_id, len(persi), motivo)
        self._allinea_filtri(framework)
        return persi

    def applica(self, framework: Any, market_ids: List[str]) -> int:
        """Porta i frammenti a ``market_ids``. Ritorna quanti frammenti ci sono.

        ``ValueError`` (lista vuota), ``CapacitaInsufficiente`` (non entra: nulla
        cambiato), ``NonPronto`` (un frammento che doveva cambiare non e'
        connesso: gli altri sono gia' allineati, si completa al giro dopo)."""
        voluti = {str(m) for m in market_ids if m}
        if not voluti:
            raise ValueError("sottoscrizione vuota rifiutata")
        fr = self.frammenti(framework)
        for s in fr:
            self._ricorda_modello(s)
            self._dal_visto(s, self._ora())
        if not fr:
            # nessun frammento vivo: framework non ancora nato o GIA' fermato
            # (``Flumine.__exit__`` -> ``streams.stop()`` li chiude tutti).
            # Mai aprire una connessione su un framework in arresto: resterebbe
            # un thread orfano che occupa il limite di Betfair.
            raise _SC.NonPronto("nessun frammento di mercato vivo (framework assente o in arresto)")
        attuali = [set(_SC.mercati_dello_stream(s)) for s in fr]
        massimo = self.massimo_adesso(framework)
        piano = pianifica(attuali, voluti, self.per_conn, max(massimo, len(fr)))
        if piano.fuori:
            raise CapacitaInsufficiente(
                "%d mercati voluti, capacita' %d (%d connessioni x %d)"
                % (len(voluti), massimo * self.per_conn, massimo, self.per_conn))
        in_attesa = 0
        for i, (s, bersaglio) in enumerate(zip(fr, piano.bersagli)):
            if bersaglio == attuali[i]:
                continue
            if not bersaglio and i > 0:
                self._chiudi(framework, s, "nessun mercato da seguire")
                continue
            if not self._connesso(s):
                in_attesa += 1
                continue
            self._sottoscrivi(framework, s, sorted(bersaglio))
            self.conti["risottoscrizioni"] += 1
        for blocco in piano.nuovi:
            self._apri(framework, self.frammenti(framework), blocco)
        self._allinea_filtri(framework)
        if in_attesa:
            raise _SC.NonPronto("%d frammenti non ancora connessi" % in_attesa)
        return len(self.frammenti(framework))

    def _dal_visto(self, s: Any, ora: float) -> float:
        """Da quando il frammento ``s`` e' visto (``ora`` se e' la prima volta, o se
        la voce trovata sotto il suo id() era di un ALTRO frammento: id() riciclato)."""
        voce = self._visto_dal.get(id(s))
        if voce is not None and voce[0]() is s:
            return voce[1]
        self._visto_dal[id(s)] = (_riferimento(s), ora)
        return ora

    def _vivo(self, s: Any, ora: float) -> bool:
        """Il frammento ha ricevuto un messaggio (anche heartbeat) entro ``MUTO_S``."""
        li = getattr(s, "_listener", None)
        ultimo = float(getattr(li, "ultimo_msg_mono", 0.0) or 0.0)
        return ultimo > 0.0 and ora - ultimo <= MUTO_S

    def manutenzione(self, framework: Any) -> Set[str]:
        """Rifiuti e frammenti muti: si chiudono e i loro mercati tornano al
        piano (ritornati: l'auto-follow li ripiazza). Mai un frammento sano.

        * RIFIUTO = una connessione nuova MAI autenticata che Betfair ha
          respinto con un codice di limite (``CODICI_RIFIUTO``), oppure che non
          si e' autenticata in ``ATTESA_APERTURA_S`` mentre un altro frammento
          riceve messaggi (la rete c'e'). Si chiude, pausa ``PAUSA_RIFIUTO_S``.
        * MUTO = frammento gia' autenticato senza NESSUN messaggio da
          ``MUTO_S`` mentre un altro frammento e' vivo: si chiude e i suoi
          mercati vanno su una connessione nuova. Se sono muti TUTTI e' la rete
          o la sessione: qui non si tocca niente, decide il controllo di stallo
          del runner (``RAW_STATE``, commit 67c3ad4) e il custode della sessione
          (2220288). Un errore su una connessione GIA' autenticata (riconnessione)
          resta alla riconnessione con backoff del frammento."""
        persi: Set[str] = set()
        if framework is None:
            return persi
        ora = self._ora()
        fr = self.frammenti(framework)
        for s in fr:
            self._ricorda_modello(s)
            dal = self._dal_visto(s, ora)
            li = getattr(s, "_listener", None)
            errore = str(getattr(li, "ultimo_errore", None) or "")
            mai_autenticato = not bool(getattr(li, "autenticato_una_volta", False))
            altri_vivi = any(self._vivo(x, ora) for x in fr if x is not s)
            if mai_autenticato and (errore in CODICI_RIFIUTO
                                    or (altri_vivi and ora - dal > ATTESA_APERTURA_S)):
                self._rifiuto_mono = ora
                self.conti["rifiuti"] += 1
                self.ultimo_rifiuto = errore or ("nessuna autenticazione in %.0f s"
                                                 % ATTESA_APERTURA_S)
                persi |= self._chiudi(framework, s, "connessione rifiutata: "
                                      + self.ultimo_rifiuto)
                continue
            ultimo = float(getattr(li, "ultimo_msg_mono", 0.0) or 0.0)
            if (not mai_autenticato and altri_vivi and len(fr) > 1
                    and ora - max(ultimo, dal) > MUTO_S):
                self.conti["muti"] += 1
                persi |= self._chiudi(framework, s, "muto da %.0f s (nessun messaggio, "
                                      "neanche heartbeat)" % (ora - max(ultimo, dal)))
        return persi

    # ------------------------------------------------------------ stato
    def stato(self, framework: Any = None) -> Dict[str, Any]:
        ora = time.monotonic()
        fr = self.frammenti(framework) if framework is not None else []

        def eta(t: float) -> Optional[float]:
            return round(ora - t, 1) if t else None
        righe = []
        for i, s in enumerate(fr):
            li = getattr(s, "_listener", None)
            righe.append({
                "i": i,
                "stream_id": getattr(s, "stream_id", None),
                "mercati": len(_SC.mercati_dello_stream(s)),
                "connesso": self._connesso(s),
                "eta_msg_s": eta(float(getattr(li, "ultimo_msg_mono", 0.0) or 0.0)),
                "eta_dati_s": eta(float(getattr(li, "ultimo_dato_mono", 0.0) or 0.0)),
                "riconnessioni": int(getattr(s, "riconnessioni", 0) or 0),
                "errore": getattr(li, "ultimo_errore", None),
            })
        massimo = self.massimo_adesso(framework)
        return {
            "connessioni_di_mercato": len(fr),
            "connessioni_massime": self.max_conn,
            "connessioni_concesse_adesso": massimo,
            "mercati_per_connessione": self.per_conn,
            "capacita_mercati": massimo * self.per_conn,
            "riserva_connessioni": self.riserva,
            "connessioni_disponibili_betfair": self._connessioni_disponibili(fr),
            "in_pausa_dopo_rifiuto": bool(self._rifiuto_mono is not None
                                          and self._ora() - self._rifiuto_mono
                                          < PAUSA_RIFIUTO_S),
            "motivo_limite": self.motivo_limite,
            "costruzione": self.costruzione,
            "ultimo_rifiuto": self.ultimo_rifiuto,
            "ultimo_evento": self.ultimo_evento,
            "conti": dict(self.conti),
            "frammenti": righe,
        }
