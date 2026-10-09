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
    precedente, come una sottoscrizione dello stream; chi esce viene dimenticato);
  * ``aggiorna(adesso_s)``: UN giro (lettura della fonte, calcolo, eventi);
    lo chiama chi possiede il servizio (worker del runner, banco) oppure il
    thread di ``avvia``;
  * ``osserva_book(event_id, market_book)``: il ``MarketBook`` di flumine/bfl di
    un mercato della partita: calcio d'inizio (``KoPerMercato``) e "in gioco"
    con la regola del runner calcio (``runner.py:358-363``: un mercato in gioco
    e non CLOSED), per le fonti che non portano la riga dello scanner;
  * ``sveglia()``: anticipa il giro (es. una sospensione dello stream).

USCITE
  * ``stato(event_id)``: l'ultimo ``StatoPartita`` (eta' all'istante del giro);
  * ``iscrivi(cb)``: ``cb(StatoPartita)`` a ogni cambio (contratto);
  * ``iscrivi_eventi(cb)``: ``StatoCambiato``, ``GolSegnato``, ``FaseCambiata``,
    ``FlussoInterrotto``, ``FlussoRipreso`` (estensione dichiarata nel referto);
  * ``prezzi_vivi(event_id, mercati)``: ``flusso_prezzi.valuta`` sull'ultima
    riga, per i mercati di una decisione (i bot passano i loro).

COSA NON FA
  Nessuna soglia di freschezza (U-08), nessuna scrittura su DB o canale (le
  pubblicazioni ``live_now``/``tennis_live_now`` restano al codice di oggi
  finche' l'ondata 2 non le aggancia), nessun ordine. Un ``cb`` che solleva
  viene registrato nel log e non ferma gli altri. Thread SOLO in ``avvia``,
  chiuso da ``ferma``; importare il modulo non apre nulla.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from Betfair.nucleo.comuni import Sport
from Betfair.nucleo.stato_partita import calcolo as C
from Betfair.nucleo.stato_partita import freschezza as F
from Betfair.nucleo.stato_partita.contratto import Eta, FasePartita, FonteStato, StatoPartita
from Betfair.stream import flusso_prezzi as _flusso

logger = logging.getLogger(__name__)


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
    event_id: str
    prima: FasePartita
    dopo: FasePartita
    stato: StatoPartita


@dataclass(frozen=True)
class FlussoInterrotto:
    """I prezzi della partita sono passati da vivi a NON vivi (cond. 11)."""

    event_id: str
    esito: Any
    stato: StatoPartita


@dataclass(frozen=True)
class FlussoRipreso:
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
                     ko_ms: Optional[int] = None, in_gioco: bool = False) -> StatoPartita:
    """UNA busta (``adattatori/lettura.py``) -> UNO ``StatoPartita``.

    Scelta del calcolo (mai una regola nuova):
      * fonte ``api_football``          -> ``stato_calcio_da_api_football``
      * c'e' lo stato grezzo (calcio)   -> ``stato_calcio_da_grezzo`` (runner, banco)
      * c'e' la lista grezza (tennis)   -> ``stato_tennis_da_grezzo``
      * solo la riga dello scanner      -> ``stato_*_da_riga`` (numeri dei bot)
    ``in_gioco`` (dal book) vale solo per le fonti senza riga: con la riga
    vale ``payload.inplay`` dello scanner."""
    eid = str(event_id)
    eta = eta_da_lettura(let, adesso_s)
    prezzi = esito_flusso(let, eid, adesso_s)
    fonte = let.get("fonte")
    riga = let.get("riga") if isinstance(let.get("riga"), Mapping) else None
    if let.get("sport") == "tennis":
        if let.get("grezzi") is not None:
            return C.stato_tennis_da_grezzo(eid, let["grezzi"], fonte=fonte, eta=eta,
                                            prezzi_vivi=prezzi, in_gioco=_in_gioco(riga, in_gioco),
                                            ko_ms=ko_ms)
        if riga is not None:
            return C.stato_tennis_da_riga(riga, eta=eta, prezzi_vivi=prezzi, fonte=fonte, ko_ms=ko_ms)
        return C.stato_tennis_da_grezzo(eid, None, fonte=fonte, eta=eta, prezzi_vivi=prezzi,
                                        in_gioco=in_gioco, ko_ms=ko_ms)
    if fonte == "api_football":
        return C.stato_calcio_da_api_football(eid, let.get("grezzo"), eta=eta, prezzi_vivi=prezzi,
                                              in_gioco=in_gioco, ko_ms=ko_ms)
    if let.get("grezzo") is not None:
        return C.stato_calcio_da_grezzo(eid, let["grezzo"], fonte=fonte, eta=eta,
                                        prezzi_vivi=prezzi, in_gioco=_in_gioco(riga, in_gioco),
                                        ko_ms=ko_ms)
    if riga is not None:
        return C.stato_calcio_da_riga(riga, eta=eta, prezzi_vivi=prezzi, fonte=fonte, ko_ms=ko_ms)
    return C.stato_calcio_da_grezzo(eid, None, fonte=fonte, eta=eta, prezzi_vivi=prezzi,
                                    in_gioco=in_gioco, ko_ms=ko_ms)


def _in_gioco(riga: Optional[Mapping[str, Any]], dal_book: bool) -> bool:
    if riga is not None and isinstance(riga.get("payload"), Mapping):
        return riga["payload"].get("inplay") is True
    return bool(dal_book)


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


def eventi_fra(prima: Optional[StatoPartita], dopo: StatoPartita) -> List[Evento]:
    """Gli eventi del passaggio ``prima -> dopo`` (vuoto se la firma e' uguale)."""
    if prima is not None and firma(prima) == firma(dopo):
        return []
    eid = dopo.event_id
    out: List[Evento] = [StatoCambiato(eid, prima, dopo)]
    if prima is None:
        return out
    if _gol_noti(prima.gol) and _gol_noti(dopo.gol) and sum(dopo.gol) > sum(prima.gol):
        out.append(GolSegnato(eid, prima.gol, dopo.gol, dopo))
    if prima.fase != dopo.fase:
        out.append(FaseCambiata(eid, prima.fase, dopo.fase, dopo))
    vivo_prima = getattr(prima.prezzi_vivi, "vivo", None)
    vivo_dopo = getattr(dopo.prezzi_vivi, "vivo", None)
    if vivo_prima is True and vivo_dopo is False:
        out.append(FlussoInterrotto(eid, dopo.prezzi_vivi, dopo))
    elif vivo_prima is False and vivo_dopo is True:
        out.append(FlussoRipreso(eid, dopo.prezzi_vivi, dopo))
    return out


def _gol_noti(g: Any) -> bool:
    return isinstance(g, tuple) and len(g) == 2 and all(isinstance(x, int) for x in g)


# ---------------------------------------------------------------------------
# il servizio
# ---------------------------------------------------------------------------
class ServizioStatoPartita:
    """``StatoPartitaService`` in processo, su UNA ``FonteStato``."""

    def __init__(self, fonte: FonteStato, *, orologio_s: Optional[Callable[[], float]] = None,
                 nome: str = "stato-partita") -> None:
        self.fonte = fonte
        self.nome = str(nome)
        # None = l'orologio del PC al momento del giro (come oggi); il banco
        # passa il tempo di mercato
        self._orologio_s = orologio_s
        self._lock = threading.RLock()
        self._seguiti: Set[str] = set()
        self._stati: Dict[str, StatoPartita] = {}
        self._letture: Dict[str, Mapping[str, Any]] = {}
        self._ko = C.KoPerMercato()
        self._ko_evento: Dict[str, int] = {}
        self._in_gioco_mercati: Dict[str, Dict[str, bool]] = {}
        self._iscritti: Dict[int, Callable[[StatoPartita], None]] = {}
        self._iscritti_eventi: Dict[int, Callable[[Evento], None]] = {}
        self._prossimo_id = 0
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sveglia = threading.Event()
        self.giri = 0
        self.errori_fonte = 0
        self.errori_callback = 0

    # ------------------------------------------------------------ contratto
    def segui(self, event_ids: Iterable[str]) -> None:
        nuovi = {str(e) for e in event_ids}
        with self._lock:
            for eid in [e for e in self._seguiti if e not in nuovi]:
                self._stati.pop(eid, None)
                self._letture.pop(eid, None)
                self._ko_evento.pop(eid, None)
                self._in_gioco_mercati.pop(eid, None)
            self._seguiti = nuovi

    def seguiti(self) -> List[str]:
        with self._lock:
            return sorted(self._seguiti)

    def stato(self, event_id: str) -> Optional[StatoPartita]:
        with self._lock:
            return self._stati.get(str(event_id))

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
        ko = C.ko_ms_intero(self._ko(market_book))
        mid = str(getattr(market_book, "market_id", "") or "")
        in_gioco = bool(getattr(market_book, "inplay", False)) and \
            str(getattr(market_book, "status", "") or "") != "CLOSED"
        with self._lock:
            if eid not in self._seguiti:
                return
            if ko is not None:
                self._ko_evento[eid] = ko
            self._in_gioco_mercati.setdefault(eid, {})[mid] = in_gioco

    def _in_gioco_dal_book(self, eid: str) -> bool:
        return any(self._in_gioco_mercati.get(eid, {}).values())

    # ------------------------------------------------------------ il giro
    def adesso_s(self) -> float:
        return float(self._orologio_s()) if self._orologio_s is not None else time.time()

    def aggiorna(self, adesso_s: Optional[float] = None) -> List[Evento]:
        """UN giro: legge la fonte per le partite seguite, calcola, sveglia.
        Torna gli eventi del giro (anche gia' consegnati agli iscritti)."""
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
                let = letture.get(eid)
                if let is None or eid not in self._seguiti:
                    continue        # nessun dato: resta l'ultimo stato (come live_now oggi)
                nuovo = stato_da_lettura(eid, let, adesso_s=ora, ko_ms=self._ko_evento.get(eid),
                                         in_gioco=self._in_gioco_dal_book(eid))
                prima = self._stati.get(eid)
                self._stati[eid] = nuovo
                self._letture[eid] = let
                ev = eventi_fra(prima, nuovo)
                if ev:
                    eventi.extend(ev)
                    cambiati.append(nuovo)
            iscritti = list(self._iscritti.values())
            iscritti_eventi = list(self._iscritti_eventi.values())
        self._consegna(iscritti, cambiati)
        self._consegna(iscritti_eventi, eventi)
        return eventi

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
        self._sveglia.set()

    def avvia(self, periodo_s: float = 2.0) -> None:
        """Un thread che fa ``aggiorna`` ogni ``periodo_s`` o a ogni ``sveglia``."""
        if self._thread is not None:
            return
        self._stop.clear()
        periodo = max(0.05, float(periodo_s))

        def gira() -> None:
            while not self._stop.is_set():
                try:
                    self.aggiorna()
                except Exception as ex:  # noqa: BLE001 - il thread non muore per un giro
                    logger.exception("[%s] giro KO: %s", self.nome, str(ex)[:160])
                self._sveglia.wait(periodo)
                self._sveglia.clear()

        self._thread = threading.Thread(target=gira, name=self.nome, daemon=True)
        self._thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        t = self._thread
        if t is None:
            return
        self._stop.set()
        self._sveglia.set()
        t.join(attesa_s)
        self._thread = None

    @property
    def vivo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
