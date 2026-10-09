"""servizio.py - UN servizio dello stato della partita, in processo (comparto B).

SCOPO
  Implementa ``StatoPartitaService`` (``contratto.py``): segue un insieme di
  partite, le legge da UNA ``FonteStato`` (``adattatori/``), calcola lo stato
  UNA volta (``calcolo.py``) con le eta' (``freschezza.py``) e il verdetto
  della condizione 11 sui prezzi (``flusso_prezzi.valuta``, importata: non e'
  separabile dallo stato), lo tiene in memoria e SVEGLIA chi si e' iscritto
  quando cambia: nessuna SELECT per chi legge, nessun relay.

ENTRATE
  * ``segui(event_ids)``: l'insieme delle partite seguite (SOSTITUISCE il
    precedente, come una sottoscrizione dello stream; chi esce viene dimenticato,
    compresa la sua parte della cache del calcio d'inizio);
  * ``aggiorna(adesso_s)``: UN giro (lettura della fonte, calcolo, eventi,
    consegna), SERIALIZZATO: due giri concorrenti non si mescolano e gli
    iscritti ricevono gli stati nell'ordine in cui sono stati calcolati;
  * ``osserva_book(event_id, market_book)``: il ``MarketBook`` di flumine/bfl di
    un mercato della partita: calcio d'inizio (``KoPerMercato``) e "in gioco".
    Con almeno un book osservato, "in gioco" segue la regola del runner calcio
    (``runner.py:358-363``: un mercato in gioco e non CLOSED), qualunque sia la
    fonte; senza book vale ``payload.inplay`` della riga dello scanner (cio' che
    leggono i bot lettori della riga) e, senza riga, False;
  * ``sveglia()``: anticipa il giro (es. una sospensione dello stream).

USCITE
  * ``stato(event_id)``: l'ultimo ``StatoPartita`` con eta' e verdetto del flusso
    RICALCOLATI all'istante della chiamata (orologio del servizio) dall'ultimo
    dato ricevuto: un dato che non si rinnova invecchia, non resta "fresco";
  * ``istante_dato_s(event_id)``: quando (orologio del servizio) e' arrivato
    l'ultimo dato della partita; serve anche per le fonti senza riga (IPS
    diretto), le cui eta' restano None come oggi (``score_age_sec``);
  * ``iscrivi(cb)``: ``cb(StatoPartita)`` a ogni cambio (contratto);
  * ``iscrivi_eventi(cb)``: ``StatoCambiato``, ``GolSegnato``, ``FaseCambiata``,
    ``FlussoInterrotto``, ``FlussoRipreso`` (estensione dichiarata nel referto);
  * ``prezzi_vivi(event_id, mercati)``: ``flusso_prezzi.valuta`` sull'ultima
    riga, per i mercati di una decisione (i bot passano i loro).

QUANDO LA FONTE TACE (nessun dato per una partita in un giro)
  * calcio: resta l'ultimo stato (come ``live_now``, che senza snapshot non
    riscrive minuto e punteggio, ``runner.py:407-411``), ma le sue eta' crescono;
  * tennis: lo stato diventa SENZA punteggio (``set_game`` None), come oggi nel
    worker del runner tennis, dove un feed in errore porta ``strat.score`` a None
    (``tennis_runner.py:1641-1661``).

COSA NON FA
  Nessuna soglia di freschezza (U-08), nessuna scrittura su DB o canale (le
  pubblicazioni ``live_now``/``tennis_live_now`` restano al codice di oggi
  finche' l'ondata 2 non le aggancia), nessun ordine. Un ``cb`` che solleva
  viene registrato nel log e non ferma gli altri; un dato che fa sollevare il
  calcolo di una partita viene registrato (al piu' una riga al minuto per
  partita) e non ferma le altre. Thread SOLO in ``avvia``, chiuso da ``ferma``;
  importare il modulo non apre nulla.
"""
from __future__ import annotations

import collections
import dataclasses
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita import freschezza as F
from Betfair.nucleo.stato_partita.contratto import Eta, FasePartita, FonteStato, StatoPartita
from Betfair.stream import flusso_prezzi as _flusso

logger = logging.getLogger(__name__)

#: al piu' una riga di log al minuto per partita su un dato che fa sollevare il calcolo
ERRORE_CALCOLO_OGNI_S = 60.0
#: voci in coda oltre le quali si avvisa (una volta al minuto) che la consegna e'
#: ferma: gli STATI si coalescono per partita, gli EVENTI non si scartano mai, quindi
#: oltre il tetto la coda cresce solo di eventi veri (gol, fasi, flusso)
TETTO_CODA = 1000
CODA_AVVISO_OGNI_S = 60.0


# ---------------------------------------------------------------------------
# eventi esposti
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class StatoCambiato:
    event_id: str
    prima: Optional[StatoPartita]
    dopo: StatoPartita


@dataclass(frozen=True)
class GolSegnato:
    """Il totale dei gol e' SALITO fra due stati noti (una correzione al ribasso,
    es. un gol annullato, e' solo ``StatoCambiato``)."""

    event_id: str
    prima: Tuple[int, int]
    dopo: Tuple[int, int]
    stato: StatoPartita


@dataclass(frozen=True)
class FaseCambiata:
    """Passaggio fra due fasi LETTE da uno stato del fornitore: 'sconosciuta' e
    le fasi DEDOTTE dal minuto (ripiego API-Football, ``fase_dedotta``) non
    contano; il confronto e' con l'ultima fase letta."""

    event_id: str
    prima: FasePartita
    dopo: FasePartita
    stato: StatoPartita


@dataclass(frozen=True)
class FlussoInterrotto:
    """I prezzi della partita sono FERMI (cond. 11, esito noto) e l'ultimo
    verdetto noto non era "fermo"."""

    event_id: str
    esito: Any
    stato: StatoPartita


@dataclass(frozen=True)
class FlussoRipreso:
    """Da fermi a vivi CON PROVA: l'esito nuovo e' noto (``Esito.noto``) e
    l'ultimo esito noto era "fermo". Un "non noto" (riga assente, fonte diretta)
    non dice che i prezzi sono ripartiti: non conta."""

    event_id: str
    esito: Any
    stato: StatoPartita


Evento = Any  # una delle cinque classi qui sopra


# ---------------------------------------------------------------------------
# lettura -> StatoPartita (puro)
# ---------------------------------------------------------------------------
def eta_da_lettura(let: Mapping[str, Any], adesso_s: Optional[float]) -> Eta:
    """Le tre eta' della busta: dalla riga dello scanner, o dall'istante del
    record del sidecar; nessuna riga = eta' assenti (come ``score_age_sec``)."""
    riga = let.get("riga")
    if not riga and let.get("istante_ms") is not None:
        riga = F.riga_da_istante_ms(let.get("istante_ms"))
    return F.calcola_eta(riga, adesso_s, scanner_s=let.get("scanner_s"))


def esito_flusso(let: Mapping[str, Any], event_id: str, adesso_s: Optional[float],
                 mercati: Optional[Iterable[Any]] = None) -> Any:
    """``flusso_prezzi.valuta`` sul payload della riga e sullo stato dello scanner.
    Senza riga ne' stato: ``NON_NOTO`` (come oggi per chi non ha la riga)."""
    riga = let.get("riga")
    payload = riga.get("payload") if isinstance(riga, Mapping) else None
    adesso_ms = None if adesso_s is None else int(float(adesso_s) * 1000)
    return _flusso.valuta(payload if isinstance(payload, Mapping) else None,
                          let.get("stato_scanner"), event_id, mercati, adesso_ms)


def stato_da_lettura(event_id: str, let: Mapping[str, Any], *, adesso_s: Optional[float] = None,
                     ko_ms: Optional[int] = None, in_gioco: Optional[bool] = None) -> StatoPartita:
    """UNA busta (``adattatori/lettura.py``) -> UNO ``StatoPartita``.

    Scelta del calcolo (mai una regola nuova):
      * fonte ``api_football``          -> ``stato_calcio_da_api_football``
      * c'e' lo stato grezzo (calcio)   -> ``stato_calcio_da_grezzo`` (runner, banco)
      * c'e' la lista grezza (tennis)   -> ``stato_tennis_da_grezzo``
      * solo la riga dello scanner      -> ``stato_*_da_riga`` (numeri dei bot)
    ``in_gioco``: None = nessun book osservato (vale ``payload.inplay`` della
    riga, o False senza riga); un booleano = regola del runner sui book, vince."""
    eid = str(event_id)
    eta = eta_da_lettura(let, adesso_s)
    prezzi = esito_flusso(let, eid, adesso_s)
    fonte = let.get("fonte")
    riga = let.get("riga") if isinstance(let.get("riga"), Mapping) else None
    if let.get("sport") == "tennis":
        if let.get("grezzi") is not None:
            st = C.stato_tennis_da_grezzo(eid, let["grezzi"], fonte=fonte, eta=eta,
                                          prezzi_vivi=prezzi, ko_ms=ko_ms)
        elif riga is not None:
            st = C.stato_tennis_da_riga(riga, eta=eta, prezzi_vivi=prezzi, fonte=fonte, ko_ms=ko_ms)
        else:
            st = C.stato_tennis_da_grezzo(eid, None, fonte=fonte, eta=eta, prezzi_vivi=prezzi,
                                          ko_ms=ko_ms)
    elif fonte == "api_football":
        st = C.stato_calcio_da_api_football(eid, let.get("grezzo"), eta=eta, prezzi_vivi=prezzi,
                                            ko_ms=ko_ms, adesso_s=adesso_s)
    elif let.get("grezzo") is not None:
        st = C.stato_calcio_da_grezzo(eid, let["grezzo"], fonte=fonte, eta=eta,
                                      prezzi_vivi=prezzi, ko_ms=ko_ms)
    elif riga is not None:
        st = C.stato_calcio_da_riga(riga, eta=eta, prezzi_vivi=prezzi, fonte=fonte, ko_ms=ko_ms)
    else:
        st = C.stato_calcio_da_grezzo(eid, None, fonte=fonte, eta=eta, prezzi_vivi=prezzi,
                                      ko_ms=ko_ms)
    return dataclasses.replace(st, in_gioco=_in_gioco(riga, in_gioco))


def _in_gioco(riga: Optional[Mapping[str, Any]], dal_book: Optional[bool]) -> bool:
    if dal_book is not None:
        return bool(dal_book)
    if riga is not None and isinstance(riga.get("payload"), Mapping):
        return riga["payload"].get("inplay") is True
    return False


def firma(stato: StatoPartita) -> tuple:
    """Cio' che conta per dire "e' cambiato": tutto tranne le eta' (crescono a
    ogni giro), il grezzo (``timeElapsedSeconds`` cambia ogni secondo) e il
    testo del flusso (porta "da N s")."""
    p = stato.prezzi_vivi
    prezzi = (getattr(p, "vivo", None), getattr(p, "motivo", None), getattr(p, "noto", None),
              tuple(getattr(p, "mercati", ()) or ()))
    return (stato.sport, stato.in_gioco, stato.fase, stato.minuto, stato.tempo, stato.gol,
            stato.rossi, stato.corner, stato.gialli, stato.set_game, stato.ko_ms, stato.fonte,
            prezzi)


def eventi_fra(prima: Optional[StatoPartita], dopo: StatoPartita,
               fase_nota: Optional[FasePartita] = None,
               vivo_noto: Optional[bool] = None) -> List[Evento]:
    """Gli eventi del passaggio ``prima -> dopo`` (vuoto se la firma e' uguale).
    ``fase_nota``: l'ultima fase LETTA della partita (default: quella di ``prima``
    se letta). Una fase 'sconosciuta' o DEDOTTA dal minuto (ripiego API-Football,
    ``calcolo.fase_dedotta``) non fa mai scattare ``FaseCambiata``;
    ``vivo_noto``: l'ultimo verdetto NOTO del flusso (default: quello di ``prima``
    se noto). Gli esiti "non noti" non contano ne' come vivi ne' come fermi."""
    if prima is not None and firma(prima) == firma(dopo):
        return []
    eid = dopo.event_id
    out: List[Evento] = [StatoCambiato(eid, prima, dopo)]
    if prima is None:
        return out
    if _gol_noti(prima.gol) and _gol_noti(dopo.gol) and sum(dopo.gol) > sum(prima.gol):
        out.append(GolSegnato(eid, prima.gol, dopo.gol, dopo))
    nota = fase_nota if fase_nota is not None else _fase_letta(prima)
    letta = _fase_letta(dopo)
    if nota is not None and letta is not None and nota != letta:
        out.append(FaseCambiata(eid, nota, dopo.fase, dopo))
    if vivo_noto is None:
        vivo_noto = _vivo_se_noto(prima.prezzi_vivi)
    vivo_dopo = _vivo_se_noto(dopo.prezzi_vivi)
    if vivo_dopo is False and vivo_noto is not False:
        out.append(FlussoInterrotto(eid, dopo.prezzi_vivi, dopo))
    elif vivo_dopo is True and vivo_noto is False:
        out.append(FlussoRipreso(eid, dopo.prezzi_vivi, dopo))
    return out


def _fase_letta(stato: StatoPartita) -> Optional[FasePartita]:
    """La fase se LETTA da uno stato del fornitore; None se sconosciuta o dedotta."""
    if stato.fase == "sconosciuta" or C.fase_dedotta(stato):
        return None
    return stato.fase


def _vivo_se_noto(esito: Any) -> Optional[bool]:
    """``Esito.vivo`` se l'esito e' noto, altrimenti None (un "non noto" e'
    ``vivo=True`` per non cambiare la condotta: non e' una prova di prezzi vivi)."""
    if getattr(esito, "noto", False) is not True:
        return None
    vivo = getattr(esito, "vivo", None)
    return vivo if isinstance(vivo, bool) else None


def _nome_callback(cb: Any) -> str:
    return str(getattr(cb, "__qualname__", None) or getattr(cb, "__name__", None) or repr(cb))[:120]


def _gol_noti(g: Any) -> bool:
    return isinstance(g, tuple) and len(g) == 2 and all(isinstance(x, int) for x in g)


# ---------------------------------------------------------------------------
# il servizio
# ---------------------------------------------------------------------------
class _Voce:
    """Una consegna in coda. ``tipo`` = "stato" (agli iscritti di ``iscrivi``) o
    "evento" (a quelli di ``iscrivi_eventi``); ``ids`` = gli iscritti AL CALCOLO
    (fotografia degli id, non delle funzioni: alla consegna si ricontrolla che
    ognuno sia ancora iscritto). Uguaglianza per identita' (``deque.remove``)."""

    __slots__ = ("tipo", "event_id", "cosa", "ids")

    def __init__(self, tipo: str, event_id: str, cosa: Any, ids: Tuple[int, ...]) -> None:
        self.tipo = tipo
        self.event_id = event_id
        self.cosa = cosa
        self.ids = ids


class _Giro:
    """Una generazione del thread di ``avvia``: il SUO segnale di stop e la SUA
    sveglia. Un thread fermato (anche se ancora dentro ``leggi``) resta fermo
    per sempre: un ``avvia`` successivo crea una generazione nuova."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.sveglia = threading.Event()
        self.thread: Optional[threading.Thread] = None


class ServizioStatoPartita:
    """``StatoPartitaService`` in processo, su UNA ``FonteStato``."""

    def __init__(self, fonte: FonteStato, *, orologio_s: Optional[Callable[[], float]] = None,
                 nome: str = "stato-partita") -> None:
        self.fonte = fonte
        self.nome = str(nome)
        # None = l'orologio del PC (come oggi); il banco passa il tempo di mercato
        self._orologio_s = orologio_s
        self._lock = threading.RLock()            # stato in memoria
        self._giro_lock = threading.RLock()       # un giro alla volta: lettura + calcolo
        self._coda_lock = threading.Lock()        # la coda delle consegne
        self._coda: Deque[_Voce] = collections.deque()
        # stato e StatoCambiato NON ancora consegnati, per partita (coalescenza)
        self._voce_stato: Dict[str, _Voce] = {}
        self._voce_cambio: Dict[str, _Voce] = {}
        self._consegnatore: Optional[int] = None  # thread che sta svuotando la coda
        self._cb_in_corso: Optional[Callable[[Any], None]] = None
        self.tetto_coda = TETTO_CODA
        self._avviso_coda = _flusso.Promemoria(CODA_AVVISO_OGNI_S)
        self.coda_max = 0
        self.coda_oltre_tetto = 0
        self.stati_coalescati = 0
        self._ciclo_lock = threading.Lock()       # avvia / ferma
        self._seguiti: Set[str] = set()
        self._stati: Dict[str, StatoPartita] = {}
        self._letture: Dict[str, Mapping[str, Any]] = {}
        self._istanti: Dict[str, float] = {}
        self._fase_nota: Dict[str, FasePartita] = {}
        self._vivo_noto: Dict[str, bool] = {}
        self._ko = C.KoPerMercato()
        self._ko_evento: Dict[str, int] = {}
        self._in_gioco_mercati: Dict[str, Dict[str, bool]] = {}
        self._iscritti: Dict[int, Callable[[StatoPartita], None]] = {}
        self._iscritti_eventi: Dict[int, Callable[[Evento], None]] = {}
        self._prossimo_id = 0
        self._giro_vivo: Optional[_Giro] = None
        self._promemoria = _flusso.Promemoria(ERRORE_CALCOLO_OGNI_S)
        self.giri = 0
        self.errori_fonte = 0
        self.errori_calcolo = 0
        self.errori_callback = 0

    # ------------------------------------------------------------ contratto
    def segui(self, event_ids: Iterable[str]) -> None:
        nuovi = {str(e) for e in event_ids}
        with self._lock:
            for eid in [e for e in self._seguiti if e not in nuovi]:
                self._dimentica(eid)
            self._seguiti = nuovi

    def _dimentica(self, eid: str) -> None:
        self._stati.pop(eid, None)
        self._letture.pop(eid, None)
        self._istanti.pop(eid, None)
        self._fase_nota.pop(eid, None)
        self._vivo_noto.pop(eid, None)
        self._ko_evento.pop(eid, None)
        self._ko.dimentica(self._in_gioco_mercati.pop(eid, {}).keys())

    def seguiti(self) -> List[str]:
        with self._lock:
            return sorted(self._seguiti)

    def stato(self, event_id: str) -> Optional[StatoPartita]:
        """L'ultimo stato, con eta' e flusso all'istante della chiamata."""
        return self.stato_a(event_id, self.adesso_s())

    def stato_a(self, event_id: str, adesso_s: float) -> Optional[StatoPartita]:
        """L'ultimo stato con eta' e verdetto del flusso ricalcolati ad ``adesso_s``
        dall'ultimo dato ricevuto (il contenuto - minuto, gol, fase - non cambia)."""
        eid = str(event_id)
        with self._lock:
            st = self._stati.get(eid)
            let = self._letture.get(eid)
            istante = self._istanti.get(eid)
        if st is None or let is None:
            return st
        return self._ricalcolato(st, let, eid, adesso_s, istante)

    @staticmethod
    def _ricalcolato(st: StatoPartita, let: Mapping[str, Any], eid: str, adesso_s: float,
                     istante: Optional[float]) -> StatoPartita:
        """``st`` con le TRE eta' e il verdetto del flusso ad ``adesso_s``.
        ``scanner_s`` (battito dello scanner al momento della lettura) cresce del
        tempo passato da allora (``istante``, orologio del servizio)."""
        scanner = let.get("scanner_s")
        if scanner is not None and istante is not None:
            scanner = float(scanner) + max(0.0, float(adesso_s) - float(istante))
        riga = let.get("riga")
        if not riga and let.get("istante_ms") is not None:
            riga = F.riga_da_istante_ms(let.get("istante_ms"))
        return dataclasses.replace(st, eta=F.calcola_eta(riga, adesso_s, scanner_s=scanner),
                                   prezzi_vivi=esito_flusso(let, eid, adesso_s))

    def istante_dato_s(self, event_id: str) -> Optional[float]:
        """Istante (orologio del servizio) dell'ultimo dato arrivato per la partita."""
        with self._lock:
            return self._istanti.get(str(event_id))

    def iscrivi(self, cb: Callable[[StatoPartita], None]) -> Callable[[], None]:
        return self._aggiungi(self._iscritti, cb)

    def iscrivi_eventi(self, cb: Callable[[Evento], None]) -> Callable[[], None]:
        return self._aggiungi(self._iscritti_eventi, cb)

    def _aggiungi(self, dove: Dict[int, Any], cb: Callable[[Any], None]) -> Callable[[], None]:
        with self._lock:
            self._prossimo_id += 1
            chiave = self._prossimo_id
            dove[chiave] = cb

        def disiscrivi() -> None:
            with self._lock:
                dove.pop(chiave, None)

        return disiscrivi

    # ------------------------------------------------------------ book
    def osserva_book(self, event_id: str, market_book: Any) -> None:
        """Calcio d'inizio e "in gioco" dal ``MarketBook`` vero di un mercato."""
        eid = str(event_id)
        with self._lock:
            if eid not in self._seguiti:
                return
            ko = C.ko_ms_intero(self._ko(market_book))
            mid = str(getattr(market_book, "market_id", "") or "")
            in_gioco = bool(getattr(market_book, "inplay", False)) and \
                str(getattr(market_book, "status", "") or "") != "CLOSED"
            if ko is not None:
                self._ko_evento[eid] = ko
            self._in_gioco_mercati.setdefault(eid, {})[mid] = in_gioco

    def _in_gioco_dal_book(self, eid: str) -> Optional[bool]:
        mercati = self._in_gioco_mercati.get(eid)
        return any(mercati.values()) if mercati else None

    # ------------------------------------------------------------ il giro
    def adesso_s(self) -> float:
        return float(self._orologio_s()) if self._orologio_s is not None else time.time()

    def aggiorna(self, adesso_s: Optional[float] = None) -> List[Evento]:
        """UN giro: legge la fonte per le partite seguite, calcola, ACCODA la
        consegna e consegna. Torna gli eventi del giro.

        Le callback NON girano mai sotto un lock del servizio: il calcolo avviene
        sotto ``_giro_lock`` e finisce in una coda; UN solo consegnatore alla volta
        svuota la coda FUORI dal lock, nell'ordine di calcolo. Se un altro thread
        sta gia' consegnando (o una callback chiama ``aggiorna`` dallo stesso
        thread), il giro accoda e torna: lo consegnera' quel consegnatore, dopo i
        giri calcolati prima. Anche un giro senza partite o con la fonte giu'
        prova a svuotare la coda (es. resti lasciati da una ``BaseException``)."""
        eventi: List[Evento] = []
        with self._giro_lock:
            ora = self.adesso_s() if adesso_s is None else float(adesso_s)
            ids = self.seguiti()
            letture: Optional[Mapping[str, Mapping[str, Any]]] = None
            if ids:
                try:
                    letture = self.fonte.leggi(ids)
                except Exception as ex:  # noqa: BLE001 - una fonte giu' non ferma il servizio
                    self.errori_fonte += 1
                    logger.warning("[%s] lettura della fonte KO: %s", self.nome, str(ex)[:160])
            if letture is not None:
                eventi = self._calcola_e_accoda(ids, letture, ora)
        self._svuota_coda()
        return eventi

    def _calcola_e_accoda(self, ids: Sequence[str], letture: Mapping[str, Mapping[str, Any]],
                          ora: float) -> List[Evento]:
        eventi: List[Evento] = []
        with self._lock:
            self.giri += 1
            cambiati: List[StatoPartita] = []
            for eid in ids:
                if eid not in self._seguiti:
                    continue     # uscita da ``segui`` durante la lettura: non torna in memoria
                ev = self._calcola_uno(eid, letture.get(eid), ora)
                if ev:
                    eventi.extend(ev)
                    cambiati.append(ev[0].dopo)
            ids_stati = tuple(self._iscritti)
            ids_eventi = tuple(self._iscritti_eventi)
        if cambiati or eventi:
            self._accoda(cambiati, ids_stati, eventi, ids_eventi)
        return eventi

    def _accoda(self, cambiati: Sequence[StatoPartita], ids_stati: Tuple[int, ...],
                eventi: Sequence[Evento], ids_eventi: Tuple[int, ...]) -> None:
        """In coda, nell'ordine di calcolo. Uno STATO (e il suo ``StatoCambiato``)
        ancora non consegnato della stessa partita viene SOSTITUITO dal nuovo, che
        va in fondo: chi legge riceve sempre l'ultimo stato, mai uno vecchio dopo
        uno nuovo. Gli altri eventi non si scartano mai."""
        with self._coda_lock:
            if ids_stati:
                for st in cambiati:
                    self._sostituisci(self._voce_stato, _Voce("stato", st.event_id, st, ids_stati))
            if ids_eventi:
                for ev in eventi:
                    if isinstance(ev, StatoCambiato):
                        vecchia = self._voce_cambio.get(ev.event_id)
                        if vecchia is not None:   # dal primo "prima" non consegnato all'ultimo "dopo"
                            ev = StatoCambiato(ev.event_id, vecchia.cosa.prima, ev.dopo)
                        self._sostituisci(self._voce_cambio, _Voce("evento", ev.event_id, ev, ids_eventi))
                    else:
                        self._coda.append(_Voce("evento", ev.event_id, ev, ids_eventi))
            lunghezza = len(self._coda)
            self.coda_max = max(self.coda_max, lunghezza)
            oltre = lunghezza > self.tetto_coda
            if oltre:
                self.coda_oltre_tetto += 1
            bloccante = self._cb_in_corso
        if oltre and self._avviso_coda.dovuto("coda", time.monotonic()):
            logger.warning("[%s] coda delle consegne oltre il tetto (%d voci > %d): consegna ferma "
                           "nella callback %s", self.nome, lunghezza, self.tetto_coda,
                           _nome_callback(bloccante))

    def _sostituisci(self, mappa: Dict[str, _Voce], voce: _Voce) -> None:
        """Con ``_coda_lock`` preso: la voce nuova al posto della vecchia della partita."""
        vecchia = mappa.get(voce.event_id)
        if vecchia is not None:
            self._coda.remove(vecchia)
            self.stati_coalescati += 1
        mappa[voce.event_id] = voce
        self._coda.append(voce)

    def _svuota_coda(self) -> None:
        """Il consegnatore: uno solo alla volta, fuori da ogni lock del servizio.
        Ogni callback riceve la voce solo se e' ANCORA iscritta in quel momento
        (chi ha chiamato ``disiscrivi`` non riceve piu' niente; chi si e' iscritto
        dopo il calcolo non riceve le voci calcolate prima)."""
        with self._coda_lock:
            if self._consegnatore is not None:
                return
            self._consegnatore = threading.get_ident()
        try:
            while True:
                with self._coda_lock:
                    if not self._coda:
                        self._consegnatore = None
                        return
                    voce = self._coda.popleft()
                    mappa = self._voce_stato if voce.tipo == "stato" else self._voce_cambio
                    if mappa.get(voce.event_id) is voce:
                        del mappa[voce.event_id]
                self._consegna_voce(voce)
        except BaseException:
            with self._coda_lock:
                self._consegnatore = None
                self._cb_in_corso = None
            raise

    def _consegna_voce(self, voce: _Voce) -> None:
        iscritti = self._iscritti if voce.tipo == "stato" else self._iscritti_eventi
        for chiave in voce.ids:
            with self._lock:
                cb = iscritti.get(chiave)
            if cb is None:
                continue                       # disiscritto prima della consegna
            with self._coda_lock:
                self._cb_in_corso = cb
            self._consegna([cb], [voce.cosa])
            with self._coda_lock:
                self._cb_in_corso = None

    def stato_servizio(self) -> Dict[str, Any]:
        """Lo stato del SERVIZIO (non di una partita): coda, contatori, callback in corso."""
        with self._coda_lock:
            coda = len(self._coda)
            cb = self._cb_in_corso
        return {
            "giri": self.giri, "seguiti": len(self.seguiti()), "coda": coda,
            "coda_max": self.coda_max, "tetto_coda": self.tetto_coda,
            "coda_oltre_tetto": self.coda_oltre_tetto, "stati_coalescati": self.stati_coalescati,
            "callback_in_corso": _nome_callback(cb) if cb is not None else None,
            "errori_fonte": self.errori_fonte, "errori_calcolo": self.errori_calcolo,
            "errori_callback": self.errori_callback, "thread_vivo": self.vivo,
        }

    def _calcola_uno(self, eid: str, let: Optional[Mapping[str, Any]], ora: float) -> List[Evento]:
        """Stato ed eventi di UNA partita (con il lock dello stato preso). Un dato
        che fa sollevare il calcolo non ferma le altre partite: si registra
        (una riga al minuto per partita) e la partita resta com'era."""
        prima = self._stati.get(eid)
        try:
            if let is None:
                nuovo = self._senza_dato(eid, prima, ora)
                if nuovo is None:
                    return []
            else:
                nuovo = stato_da_lettura(eid, let, adesso_s=ora, ko_ms=self._ko_evento.get(eid),
                                         in_gioco=self._in_gioco_dal_book(eid))
        except Exception as ex:  # noqa: BLE001 - una partita rotta non ferma le altre
            self.errori_calcolo += 1
            if self._promemoria.dovuto(eid, ora):
                logger.warning("[%s] stato della partita %s non calcolabile: %s: %s", self.nome,
                               eid, type(ex).__name__, str(ex)[:160])
            return []
        ev = eventi_fra(prima, nuovo, self._fase_nota.get(eid), self._vivo_noto.get(eid))
        self._stati[eid] = nuovo
        if let is not None:
            self._letture[eid] = let
            self._istanti[eid] = ora
        elif nuovo.sport == "tennis":
            self._letture.pop(eid, None)        # tennis muto: la lettura vecchia non vale piu'
        letta = _fase_letta(nuovo)
        if letta is not None:
            self._fase_nota[eid] = letta
        vivo = _vivo_se_noto(nuovo.prezzi_vivi)
        if vivo is not None:
            self._vivo_noto[eid] = vivo
        return ev

    def _senza_dato(self, eid: str, prima: Optional[StatoPartita],
                    ora: float) -> Optional[StatoPartita]:
        """Nessun dato in questo giro.
        Tennis: stato senza punteggio (come ``strat.score = None`` del runner tennis).
        Calcio: resta l'ultimo stato (come ``live_now`` oggi) con eta' e verdetto
        del flusso ricalcolati ADESSO dall'ultimo dato: se il verdetto passa a
        "fermo" (es. scanner bloccato) lo stato e gli eventi lo dicono in QUESTO
        giro, come ``stato()``. None = nessuno stato precedente."""
        if prima is None:
            return None
        if prima.sport == "tennis":
            return dataclasses.replace(prima, set_game=None, eta=F.ETA_ASSENTE,
                                       prezzi_vivi=_flusso.NON_NOTO, grezzo={})
        let = self._letture.get(eid)
        if let is None:
            return None
        return self._ricalcolato(prima, let, eid, ora, self._istanti.get(eid))

    def _consegna(self, cbs: Sequence[Callable[[Any], None]], cose: Sequence[Any]) -> None:
        for cosa in cose:
            for cb in cbs:
                try:
                    cb(cosa)
                except Exception as ex:  # noqa: BLE001 - un iscritto non ferma gli altri
                    self.errori_callback += 1
                    logger.warning("[%s] iscritto KO su %s: %s", self.nome,
                                   type(cosa).__name__, str(ex)[:160])

    # ------------------------------------------------------------ prezzi
    def prezzi_vivi(self, event_id: str, mercati: Optional[Iterable[Any]] = None,
                    adesso_s: Optional[float] = None) -> Any:
        """``flusso_prezzi.valuta`` sull'ultima lettura della partita, per i
        ``mercati`` della decisione (None = MATCH_ODDS). Senza lettura: ``NON_NOTO``."""
        with self._lock:
            let = self._letture.get(str(event_id))
        if let is None:
            return _flusso.NON_NOTO
        ora = self.adesso_s() if adesso_s is None else float(adesso_s)
        return esito_flusso(let, str(event_id), ora, mercati)

    # ------------------------------------------------------------ thread
    def sveglia(self) -> None:
        g = self._giro_vivo
        if g is not None:
            g.sveglia.set()

    def avvia(self, periodo_s: float = 2.0) -> None:
        """Un thread che fa ``aggiorna`` ogni ``periodo_s`` o a ogni ``sveglia``.
        Una generazione per volta: se ce n'e' una viva non ne parte un'altra."""
        with self._ciclo_lock:
            if self._giro_vivo is not None:
                return
            g = _Giro()
            periodo = max(0.05, float(periodo_s))

            def gira() -> None:
                while not g.stop.is_set():
                    try:
                        self.aggiorna()
                    except Exception as ex:  # noqa: BLE001 - il thread non muore per un giro
                        logger.exception("[%s] giro KO: %s", self.nome, str(ex)[:160])
                    g.sveglia.wait(periodo)
                    g.sveglia.clear()

            g.thread = threading.Thread(target=gira, name=self.nome, daemon=True)
            self._giro_vivo = g
            g.thread.start()

    def ferma(self, attesa_s: float = 5.0) -> bool:
        """Ferma la generazione viva. True se il suo thread e' terminato entro
        ``attesa_s``; False se e' ancora dentro un giro (es. bloccato in ``leggi``
        o in una callback) o se la chiamata viene dal thread del giro: resta fermo
        per sempre e uscira' alla fine del giro, senza rifarne un altro.

        ``ferma`` NON scarta la coda delle consegne: gli stati e gli eventi gia'
        calcolati vengono consegnati dal consegnatore attuale (anche se e' il
        thread fermato, prima di uscire) o dal prossimo ``aggiorna``."""
        with self._ciclo_lock:
            g = self._giro_vivo
            self._giro_vivo = None
        if g is None or g.thread is None:
            return True
        g.stop.set()
        g.sveglia.set()
        if g.thread is threading.current_thread():
            # chiamata dal thread del giro (es. da una callback): non ci si puo'
            # aspettare da soli; il thread uscira' alla fine di questo giro
            return False
        g.thread.join(attesa_s)
        terminato = not g.thread.is_alive()
        if not terminato:
            logger.warning("[%s] thread ancora dentro un giro dopo %.1f s: uscira' alla fine",
                           self.nome, float(attesa_s))
        return terminato

    @property
    def vivo(self) -> bool:
        g = self._giro_vivo
        return g is not None and g.thread is not None and g.thread.is_alive()
