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

import dataclasses
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita import freschezza as F
from Betfair.nucleo.stato_partita.contratto import Eta, FasePartita, FonteStato, StatoPartita
from Betfair.stream import flusso_prezzi as _flusso

logger = logging.getLogger(__name__)

#: al piu' una riga di log al minuto per partita su un dato che fa sollevare il calcolo
ERRORE_CALCOLO_OGNI_S = 60.0


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
    """Passaggio fra due fasi NOTE: 'sconosciuta' (fonte che non sa la fase, es.
    il ripiego API-Football) non e' una fase; il confronto e' con l'ultima nota."""

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
                                            ko_ms=ko_ms)
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
    ``fase_nota``: l'ultima fase NOTA della partita (default: quella di ``prima``);
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
    nota = fase_nota if fase_nota is not None else prima.fase
    if nota != "sconosciuta" and dopo.fase != "sconosciuta" and nota != dopo.fase:
        out.append(FaseCambiata(eid, nota, dopo.fase, dopo))
    if vivo_noto is None:
        vivo_noto = _vivo_se_noto(prima.prezzi_vivi)
    vivo_dopo = _vivo_se_noto(dopo.prezzi_vivi)
    if vivo_dopo is False and vivo_noto is not False:
        out.append(FlussoInterrotto(eid, dopo.prezzi_vivi, dopo))
    elif vivo_dopo is True and vivo_noto is False:
        out.append(FlussoRipreso(eid, dopo.prezzi_vivi, dopo))
    return out


def _vivo_se_noto(esito: Any) -> Optional[bool]:
    """``Esito.vivo`` se l'esito e' noto, altrimenti None (un "non noto" e'
    ``vivo=True`` per non cambiare la condotta: non e' una prova di prezzi vivi)."""
    if getattr(esito, "noto", False) is not True:
        return None
    vivo = getattr(esito, "vivo", None)
    return vivo if isinstance(vivo, bool) else None


def _gol_noti(g: Any) -> bool:
    return isinstance(g, tuple) and len(g) == 2 and all(isinstance(x, int) for x in g)


# ---------------------------------------------------------------------------
# il servizio
# ---------------------------------------------------------------------------
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
        self._giro_lock = threading.RLock()       # un giro alla volta: calcolo + consegna
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
        if st is None or let is None:
            return st
        return dataclasses.replace(st, eta=eta_da_lettura(let, adesso_s),
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
        """UN giro: legge la fonte per le partite seguite, calcola, sveglia.
        Torna gli eventi del giro (anche gia' consegnati agli iscritti)."""
        with self._giro_lock:
            ora = self.adesso_s() if adesso_s is None else float(adesso_s)
            ids = self.seguiti()
            if not ids:
                return []
            try:
                letture = self.fonte.leggi(ids)
            except Exception as ex:  # noqa: BLE001 - una fonte giu' non ferma il servizio
                self.errori_fonte += 1
                logger.warning("[%s] lettura della fonte KO: %s", self.nome, str(ex)[:160])
                return []
            eventi: List[Evento] = []
            cambiati: List[StatoPartita] = []
            with self._lock:
                self.giri += 1
                for eid in ids:
                    if eid not in self._seguiti:
                        continue
                    ev = self._calcola_uno(eid, letture.get(eid), ora)
                    if ev:
                        eventi.extend(ev)
                        cambiati.append(ev[0].dopo)
                iscritti = list(self._iscritti.values())
                iscritti_eventi = list(self._iscritti_eventi.values())
            self._consegna(iscritti, cambiati)
            self._consegna(iscritti_eventi, eventi)
            return eventi

    def _calcola_uno(self, eid: str, let: Optional[Mapping[str, Any]], ora: float) -> List[Evento]:
        """Stato ed eventi di UNA partita (con il lock dello stato preso). Un dato
        che fa sollevare il calcolo non ferma le altre partite: si registra
        (una riga al minuto per partita) e la partita resta com'era."""
        prima = self._stati.get(eid)
        try:
            if let is None:
                nuovo = self._senza_dato(eid, prima)
                if nuovo is None:
                    return []        # calcio: resta l'ultimo stato (come live_now oggi)
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
        else:
            self._letture.pop(eid, None)
        if nuovo.fase != "sconosciuta":
            self._fase_nota[eid] = nuovo.fase
        vivo = _vivo_se_noto(nuovo.prezzi_vivi)
        if vivo is not None:
            self._vivo_noto[eid] = vivo
        return ev

    def _senza_dato(self, eid: str, prima: Optional[StatoPartita]) -> Optional[StatoPartita]:
        """Nessun dato in questo giro. Tennis: stato senza punteggio (come
        ``strat.score = None`` del runner tennis); calcio: None = resta il vecchio."""
        if prima is None or prima.sport != "tennis":
            return None
        return dataclasses.replace(prima, set_game=None, eta=F.ETA_ASSENTE,
                                   prezzi_vivi=_flusso.NON_NOTO, grezzo={})

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
        ``attesa_s``; False se e' ancora dentro un giro (es. bloccato in ``leggi``):
        resta fermo per sempre e uscira' alla fine del giro, senza rifarne un altro."""
        with self._ciclo_lock:
            g = self._giro_vivo
            self._giro_vivo = None
        if g is None or g.thread is None:
            return True
        g.stop.set()
        g.sveglia.set()
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
