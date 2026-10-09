"""porta.py - ``PortaOrdini`` sopra un ``Esecutore`` iniettato (W1-C1, 09/10/2026).

Scopo
-----
La porta unica degli ordini del contratto C (04 par. 3.4): riceve una
``RichiestaOrdine``, risponde con un ``Ack`` e pubblica la sequenza di ``EventoOrdine``
dell'ordine, con le garanzie che oggi da' ``motore_ordini.MotoreOrdini`` (F3 del suo
docstring) e nello stesso ordine:

  1. il ``ref`` e' ``"<attore>-<id>"`` di al massimo 32 caratteri, l'attore e' ammesso;
     altrimenti rifiuto NON registrato (senza seq, senza dedup), come il motore;
  2. DEDUP per ``ref``: lo stesso ref = la stessa richiesta, mai un secondo invio. Vale
     per tutta la vita del processo (ben oltre i 60 s di Betfair, che a monte deduplica il
     customerRef) e SOPRAVVIVE al riavvio: memoria, diario e le righe ``TABELLA_REF`` che la
     porta scrive (``Archivio.scrivi``) e rilegge (``Archivio.leggi``) sotto il suo
     lucchetto: SOLO le primitive del contratto, con la loro semantica vera. UNA porta per
     archivio: l'archivio locale ha un lucchetto esclusivo per cartella (un solo processo
     lo apre, W1-G1) e una seconda ``PortaLocale`` nello stesso processo sullo stesso
     archivio e' rifiutata alla costruzione (``ArchivioGiaInUso``). Parita' col motore
     di oggi (``motore_ordini.py:997-1005``): stesso ref = stessa richiesta, mai un
     secondo invio; il ref gia' visto risponde ``accettato`` e ``seq`` della PRIMA
     risposta, motivo ``ref_gia_visto``, qualunque sia la sua fase (in volo, ignoto,
     terminale), anche dopo il riavvio; l'esito lo dicono ``stato``/``eventi``;
  3. validazione con ``valida_comando`` di oggi (via ``adattatore_comando``); i ``params``
     del bot arrivano all'esecutore che li dichiara (``accetta_params``), altrimenti la
     richiesta e' RIFIUTATA (``params_non_serviti``): un cap che sparisce in silenzio no;
  4. freni (``controlli.controlla``): eta', modo della RIGA (mai del servizio), guardia
     d'avvio, modo effettivo sulle aperture, kill-switch, settings;
  5. minimi .it (``minimi.verdetto_porta``): punta diretta a multiplo di 0,50 per difetto
     col residuo dichiarato (``punta_050``), TENNIS: apertura sotto il minimo portata AL
     minimo (``portata_al_minimo``, come ``esecutore_tennis._apertura_al_minimo``) e
     nessun place-and-trim; sotto il minimo rifiuto ``SOTTO_MINIMO_NON_PIAZZABILE``; una
     taglia gia' rifiutata da Betfair (``INVALID_BET_SIZE``) non si ritenta identica; il
     place-and-trim NON passa dalla porta (il contratto non sa marcarlo);
  6. tetto delle transazioni/ora UNO per conto e PER MODO (paper e live mai sommati: il
     contatore del live e, se dato, uno del paper);
  7. ``seq`` per attore (UN contatore per ack ed eventi), assegnato e messo in memoria
     nella STESSA sezione di lucchetto (``da_seq`` non vede mai un seq non ancora in
     memoria); mai indietro, nemmeno dopo un riavvio con l'orologio indietro (blocchi di
     seq prenotati nell'archivio, ``TABELLA_SEQ``); memoria degli ultimi 500 per ``da_seq``;
  8. DIARIO write-ahead (la classe ``motore_ordini.Diario`` di oggi, iniettata): ``inviato``
     su disco PRIMA dell'archivio e dell'esecutore (un crash in mezzo non lascia mai un
     ack accettato senza traccia); ``esito``/``evento`` durevoli come nel motore;
  9. un esito IGNOTO (eccezione o timeout dell'esecutore) e' l'evento ``ignoto``: MAI
     trasformato in ``accettato``/``abbinato``, MAI ritentato; un ref ``ignoto`` resta
     ``in_volo`` anche dopo il riavvio finche' un evento vero non lo risolve;
 10. stato MONOTONO per ref, per gli eventi E per l'esito del place (il flusso degli ordini
     puo' arrivare PRIMA della risposta REST): un terminale non si sovrascrive, l'abbinato
     non cala; la memoria per ref espelle SOLO ordini chiusi (un ordine aperto non si
     dimentica: oltre il tetto si cresce e si dice).

I consumatori iscritti ricevono i messaggi FUORI da ogni lucchetto (coda di consegna): un
consumatore puo' chiamare ``invia`` dalla sua callback senza bloccare nulla.

Cosa NON fa (ondata 1): non e' agganciata all'app; e' SINCRONA e SERIALIZZATA (un invio
alla volta, come il thread unico del motore); non fa place-and-trim ne' ordini equivalenti
ne' azioni composte (sopra la porta); non calcola la posizione (comparto C2); non
riconcilia con Betfair gli ordini in volo al riavvio: li marca ``ignoto`` e li elenca.
"""
from __future__ import annotations

import collections
import dataclasses
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import (Any, Callable, Deque, Dict, Iterator, List, Mapping, Optional, Protocol,
                    Tuple, Union)

from Betfair.nucleo.dati.contratto import Archivio
from Betfair.nucleo.ordini import controlli as CT
from Betfair.nucleo.ordini import minimi as MN
from Betfair.nucleo.ordini.adattatore_comando import (ExtraComando, RichiestaComposta,
                                                      comando_da_richiesta)
from Betfair.nucleo.ordini.contratto import (Ack, Esecutore, EventoOrdine, PosizioneConto,
                                             RichiestaOrdine, StatoOrdine)
from Betfair.nucleo.ordini.eventi import FASI_TERMINALI, Messaggio, RispostaDaSeq

logger = logging.getLogger(__name__)

#: la tabella LOCALE dell'archivio con gli ack gia' dati (chiave: ``ref``)
TABELLA_REF = "ordini_ref_visti"
#: la tabella LOCALE con il blocco di seq prenotato (chiave: ``chiave="seq"``)
TABELLA_SEQ = "ordini_seq"
BLOCCO_SEQ = 1000
MAX_REF = 32
MEMORIA_EVENTI = 500
#: ref tenuti in RAM (come ``MemoriaComandi.MAX_REF_IN_MEMORIA``): oltre, il dedup legge
#: l'archivio
MAX_IN_MEMORIA = 5000
MAX_ETA_DEFAULT_MS = 3000
MAX_ETA_SETTINGS_S_DEFAULT = 10.0
#: codice dell'evento di un esito IGNOTO (eccezione/timeout dell'esecutore)
CODICE_ESITO_IGNOTO = "ESITO_IGNOTO"
#: rifiuti della porta che il motore non ha
M_ARCHIVIO = "archivio_non_disponibile"
M_COMPOSTA = "azione_composta_sopra_la_porta"
M_PARAMS = "params_non_serviti"
#: un ref prenotato da un'ALTRA porta sullo stesso archivio, senza ack entro l'attesa
#: un ref gia' inviato con esito non certo (in volo dopo un riavvio, o ignoto): nessun
#: invio, ``accettato=False``, si riconcilia per ref
_EPS = 1e-9


class Diario(Protocol):
    """La forma di ``motore_ordini.Diario`` che la porta usa."""

    def scrivi(self, record: Dict[str, Any], *, durevole: bool = True) -> None: ...
    def leggi(self, giorni: List[str]) -> List[Dict[str, Any]]: ...
    def chiudi(self) -> None: ...


def _motore() -> Any:
    from Betfair.stream import motore_ordini

    return motore_ordini


def _codice_betfair(codice: Optional[str]) -> bool:
    """True se ``codice`` e' un errore d'istruzione di Betfair (la richiesta e' ARRIVATA
    e conta come transazione fallita). Enum di betfairlightweight, nessuna copia."""
    if not codice:
        return False
    from betfairlightweight.enums import InstructionReportErrorCode

    return codice in InstructionReportErrorCode.__members__


def _ack_in_riga(ack: Ack, attore: str, ts_ms: int) -> Dict[str, Any]:
    """La riga di ``TABELLA_REF`` (chiave ``ref``): l'ack dato la prima volta."""
    return {"ref": ack.ref, "attore": attore, "accettato": ack.accettato, "seq": ack.seq,
            "motivo": ack.motivo, "ts_ms": ts_ms}


class ArchivioGiaInUso(RuntimeError):
    """Una seconda ``PortaLocale`` nello stesso processo sullo stesso archivio."""


#: le cartelle d'archivio con una porta aperta in QUESTO processo (registro di processo)
_ARCHIVI_IN_USO: Dict[str, int] = {}
_LOCK_ARCHIVI = threading.Lock()


def _chiave_archivio(archivio: Any) -> str:
    """La cartella dell'archivio (``ArchivioLocale.cartella``), o l'identita' dell'oggetto."""
    cartella = getattr(archivio, "cartella", None)
    return f"cartella:{cartella}" if cartella is not None else f"oggetto:{id(archivio)}"


def _ack_da_riga(riga: Mapping[str, Any]) -> Ack:
    seq = riga.get("seq")
    return Ack(ref=str(riga.get("ref")), accettato=bool(riga.get("accettato")),
               seq=int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None,
               motivo=riga.get("motivo"))


def _stantio(prima: Optional[StatoOrdine], ev: EventoOrdine) -> bool:
    """Un evento che farebbe REGREDIRE lo stato: dopo un terminale, o con meno abbinato."""
    if prima is None:
        return False
    if prima.fase in FASI_TERMINALI:
        return True
    return float(ev.abbinato) < float(prima.abbinato) - _EPS


def _pota(d: "collections.OrderedDict[Any, Any]", massimo: int) -> None:
    """Potatura FIFO (solo per strutture che non sono stato di ordini aperti)."""
    while len(d) > massimo:
        d.popitem(last=False)


class PortaLocale:
    """``PortaOrdini`` in-process sopra un ``Esecutore``. Thread-safe: gli invii sono
    SERIALIZZATI (``_lock_invio``, come il thread unico del motore); seq, memoria e stati
    stanno sotto ``_lock`` (seq assegnato e memorizzato insieme); le callback dei
    consumatori girano fuori da ogni lucchetto (``_consegna``)."""

    def __init__(self, esecutore: Esecutore, *, freni: CT.FreniConto, archivio: Archivio,
                 diario: Diario, contatore: Optional[CT.ContatoreTransazioni] = None,
                 contatore_paper: Optional[CT.ContatoreTransazioni] = None,
                 orologio_ms: Callable[[], int] = lambda: int(time.time() * 1000),
                 attori: Optional[frozenset] = None,
                 max_eta_ms: int = MAX_ETA_DEFAULT_MS,
                 max_eta_settings_s: float = MAX_ETA_SETTINGS_S_DEFAULT,
                 riduzione_verificata: Optional[Callable[[RichiestaOrdine], bool]] = None,
                 guardia_armata: Callable[[], bool] = lambda: False,
                 fonte_posizione: Optional[Callable[[str, Optional[int]], PosizioneConto]] = None,
                 memoria_eventi: int = MEMORIA_EVENTI) -> None:
        self._esecutore = esecutore
        self._freni = freni
        self._archivio = archivio
        self._diario = diario
        # UN contatore PER MODO, mai sommati: ``contatore`` e' quello del LIVE (il tetto di
        # Betfair, per conto); ``contatore_paper`` (facoltativo) riproduce il tetto proprio
        # del client simulato di oggi (``runner.py`` lo crea con lo stesso limite)
        self._contatori: Dict[str, Optional[CT.ContatoreTransazioni]] = {
            "live": contatore, "paper": contatore_paper}
        self._ora_ms = orologio_ms
        self._attori = attori if attori is not None else _motore().ATTORI_COMANDO
        self.max_eta_ms = int(max_eta_ms)
        self.max_eta_settings_s = float(max_eta_settings_s)
        self._riduzione_verificata = riduzione_verificata
        self._guardia_armata = guardia_armata
        self._fonte_posizione = fonte_posizione
        self._memoria_max = int(memoria_eventi)
        self._lock = threading.RLock()
        self._lock_invio = threading.Lock()
        self._lock_consegna = threading.Lock()
        self._da_consegnare: Deque[Tuple[str, Messaggio]] = collections.deque()
        self._base_seq = int(orologio_ms())
        self._seq_riservato = 0
        self._soglia_avviso = 0
        # UNA porta per archivio nel processo (fra processi: il lucchetto di W1-G1)
        self._chiave_archivio = _chiave_archivio(archivio)
        with _LOCK_ARCHIVI:
            if self._chiave_archivio in _ARCHIVI_IN_USO:
                raise ArchivioGiaInUso(
                    f"misconfigurazione: l'archivio {self._chiave_archivio} ha gia' una "
                    f"PortaLocale aperta in questo processo (una porta per archivio)")
            _ARCHIVI_IN_USO[self._chiave_archivio] = id(self)
        self._seq: Dict[str, int] = {}
        self._memoria: Dict[str, Deque[Messaggio]] = {}
        self._visti: "collections.OrderedDict[str, Ack]" = collections.OrderedDict()
        self._attore_di_ref: "collections.OrderedDict[str, str]" = collections.OrderedDict()
        self._richieste: "collections.OrderedDict[str, RichiestaOrdine]" = \
            collections.OrderedDict()
        self._stati: "collections.OrderedDict[str, StatoOrdine]" = collections.OrderedDict()
        self._extra_eventi: "collections.OrderedDict[str, Dict[str, Any]]" = \
            collections.OrderedDict()
        self._taglie_rifiutate: "collections.OrderedDict[Tuple[str, str, float], int]" = \
            collections.OrderedDict()
        self._consumatori: Dict[str, List[Callable[[Messaggio], None]]] = {}
        self._in_volo: List[str] = []
        self.conti: Dict[str, int] = {"richieste": 0, "accettate": 0, "rifiutate": 0,
                                      "doppioni": 0, "eventi": 0, "ignoti": 0, "stantii": 0}

    # ------------------------------------------------------------ ciclo di vita
    def _giorni(self) -> List[str]:
        oggi = datetime.fromtimestamp(self._ora_ms() / 1000.0)
        return [(oggi - timedelta(days=1)).strftime("%Y-%m-%d"), oggi.strftime("%Y-%m-%d")]

    def apri(self) -> None:
        """Riavvio: base dei seq (mai indietro: blocco prenotato nell'archivio e seq del
        diario), ack gia' dati (dedup), ultimo stato per ref, ordini in volo (``inviato``
        senza esito o con esito ``ignoto``) -> stato ``ignoto`` ed elenco ``in_volo``.
        Diario o archivio illeggibili: si DICE (log) e si prosegue col resto."""
        massimo = self._base_seq
        try:
            riga = self._archivio.leggi(TABELLA_SEQ, {"chiave": "seq"})
            if riga is not None:
                massimo = max(massimo, int(riga.get("fino_a") or 0))
        except Exception as ex:  # noqa: BLE001
            logger.error("[porta] blocco dei seq illeggibile all'apertura: %s", str(ex)[:200])
        try:
            righe = self._diario.leggi(self._giorni())
        except Exception as ex:  # noqa: BLE001 - il dedup resta all'archivio
            logger.error("[porta] diario illeggibile all'apertura: %s", str(ex)[:200])
            righe = []
        with self._lock:
            massimo = max(massimo, self._rileggi(righe))
            self._base_seq = massimo
        if self._in_volo:
            logger.warning("[porta] %d ordini in volo al riavvio (stato ignoto, da "
                           "riconciliare): %s", len(self._in_volo), ", ".join(self._in_volo)[:300])

    def _rileggi(self, righe: List[Dict[str, Any]]) -> int:
        """Rilegge le righe del diario (in ordine); ritorna il seq piu' alto visto."""
        inviati: Dict[str, Dict[str, Any]] = {}
        massimo = 0
        for rec in righe:
            ref = rec.get("ref")
            if not isinstance(ref, str):
                continue
            tipo = rec.get("tipo")
            ack = rec.get("ack")
            if tipo in ("inviato", "rifiuto") and isinstance(ack, dict):
                self._visti[ref] = _ack_da_riga(ack)       # l'ultima riga vince
                massimo = max(massimo, int(ack.get("seq") or 0))
                if rec.get("attore"):
                    self._attore_di_ref[ref] = str(rec["attore"])
            if tipo == "inviato":
                inviati[ref] = rec
            elif tipo == "rifiuto":
                # chiuso: nulla e' partito (lo stato 'rifiutato' lo toglie dagli in volo)
                self._stati[ref] = StatoOrdine(ref=ref, bet_id=None, fase="rifiutato",
                                               abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                               ultimo_seq=int((ack or {}).get("seq") or 0))
            elif tipo in ("esito", "evento") and isinstance(rec.get("evento"), dict):
                try:
                    ev = EventoOrdine(**rec["evento"])
                except (TypeError, ValueError) as ex:
                    logger.error("[porta] diario: evento di %s illeggibile: %s", ref,
                                 str(ex)[:160])
                    continue
                massimo = max(massimo, int(ev.seq))
                if not _stantio(self._stati.get(ref), ev):
                    self._aggiorna_stato(ev)
        for ref in inviati:
            st = self._stati.get(ref)
            if st is None or st.fase == "ignoto":
                # inviato senza esito, o con esito IGNOTO: resta da riconciliare
                self._in_volo.append(ref)
                if st is None:
                    seq = (inviati[ref].get("ack") or {}).get("seq") or 0
                    self._stati[ref] = StatoOrdine(ref=ref, bet_id=None, fase="ignoto",
                                                   abbinato=0.0, residuo=0.0,
                                                   prezzo_medio=None, ultimo_seq=int(seq))
        return massimo

    def chiudi(self) -> None:
        """Chiude il diario e libera l'archivio (un'altra porta potra' aprirlo)."""
        try:
            self._diario.chiudi()
        except Exception as ex:  # noqa: BLE001
            logger.error("[porta] chiusura del diario KO: %s", str(ex)[:200])
        with _LOCK_ARCHIVI:
            if _ARCHIVI_IN_USO.get(self._chiave_archivio) == id(self):
                del _ARCHIVI_IN_USO[self._chiave_archivio]

    def in_volo(self) -> Tuple[str, ...]:
        """I ref inviati e senza esito certo al riavvio: li riconcilia C2, mai un reinvio."""
        with self._lock:
            return tuple(self._in_volo)

    # ------------------------------------------------------------ seq e memoria
    def _nuovo_seq(self, attore: str) -> int:
        """Da chiamare CON ``_lock`` tenuto, nella stessa sezione di ``_memorizza``."""
        s = self._seq.get(attore, self._base_seq) + 1
        self._seq[attore] = s
        if s > self._seq_riservato:
            self._seq_riservato = s + BLOCCO_SEQ
            try:
                self._archivio.scrivi(TABELLA_SEQ, {"chiave": "seq",
                                                    "fino_a": self._seq_riservato})
            except Exception as ex:  # noqa: BLE001 - il seq resta valido; il riavvio no
                logger.error("[porta] blocco dei seq NON prenotato (dopo un riavvio con "
                             "l'orologio indietro i seq potrebbero ripetersi): %s",
                             str(ex)[:160])
        return s

    def _memorizza(self, attore: str, m: Messaggio) -> None:
        """Da chiamare CON ``_lock`` tenuto: memoria per ``da_seq`` e coda di consegna."""
        mem = self._memoria.get(attore)
        if mem is None:
            mem = collections.deque(maxlen=self._memoria_max)
            self._memoria[attore] = mem
        mem.append(m)
        self._da_consegnare.append((attore, m))

    def _consegna(self) -> None:
        """Consegna ai consumatori FUORI da ogni lucchetto, in ordine. Una callback che
        chiama ``invia`` (stesso thread) non blocca: i suoi messaggi li consegna il giro
        gia' in corso."""
        while True:
            if not self._lock_consegna.acquire(blocking=False):
                return
            try:
                while True:
                    with self._lock:
                        if not self._da_consegnare:
                            break
                        attore, m = self._da_consegnare.popleft()
                        cbs = list(self._consumatori.get(attore, ()))
                    for cb in cbs:
                        try:
                            cb(m)
                        except Exception:  # noqa: BLE001 - un consumatore rotto non ferma la porta
                            logger.exception("[porta] consumatore di %s KO", attore)
            finally:
                self._lock_consegna.release()
            with self._lock:
                if not self._da_consegnare:
                    return

    def aggiungi_consumatore(self, attore: str, cb: Callable[[Messaggio], None]) -> None:
        """Iscrive ``cb`` ai messaggi (ack ed eventi) di ``attore``: il PUSH, che puo'
        perdere un messaggio (consumatore lento): ``da_seq`` ripara."""
        with self._lock:
            self._consumatori.setdefault(attore, []).append(cb)

    def da_seq(self, attore: str, dal: int) -> RispostaDaSeq:
        """I messaggi di ``attore`` con ``seq > dal`` ancora in memoria (``completo`` False
        se la memoria non arriva fino a ``dal``), come ``_rispondi_da_seq`` del motore."""
        with self._lock:
            mem = list(self._memoria.get(attore) or ())
            ultimo = self._seq.get(attore, self._base_seq)
        mancanti = tuple(m for m in mem if int(m.seq or 0) > dal)
        primo = int(mem[0].seq or 0) if mem else ultimo + 1
        return RispostaDaSeq(dal=int(dal), fino_a=int(ultimo), messaggi=mancanti,
                             completo=int(dal) >= primo - 1)

    def eventi(self, attore: str, da_seq: int = 0) -> Iterator[EventoOrdine]:
        """Gli ``EventoOrdine`` di ``attore`` con ``seq > da_seq`` ancora in memoria."""
        for m in self.da_seq(attore, da_seq).messaggi:
            if isinstance(m, EventoOrdine):
                yield m

    # ------------------------------------------------------------------- stato
    def _aggiorna_stato(self, ev: EventoOrdine) -> None:
        prima = self._stati.get(ev.ref)
        self._stati[ev.ref] = StatoOrdine(
            ref=ev.ref, bet_id=ev.bet_id or (prima.bet_id if prima else None), fase=ev.fase,
            abbinato=float(ev.abbinato), residuo=float(ev.residuo),
            prezzo_medio=ev.prezzo_medio, ultimo_seq=int(ev.seq))
        self._stati.move_to_end(ev.ref)
        self._pota_ref(self._stati)

    def _espellibile(self, ref: str) -> bool:
        """Un ref si puo' dimenticare solo se il suo ordine e' CHIUSO (o non ha stato:
        visto solo nell'archivio). Un ordine aperto (PERSIST a riposo) MAI."""
        st = self._stati.get(ref)
        return (st is None and ref not in self._in_volo) or \
            (st is not None and st.fase in FASI_TERMINALI)

    def _pota_ref(self, d: "collections.OrderedDict[str, Any]") -> None:
        """Con ``_lock`` tenuto: oltre ``MAX_IN_MEMORIA`` espelle i ref piu' vecchi CHIUSI;
        se il tetto e' pieno di ordini aperti cresce e lo dice (WARNING)."""
        eccesso = len(d) - MAX_IN_MEMORIA
        if eccesso <= 0:
            return
        for ref in list(d.keys()):
            if eccesso <= 0:
                break
            if self._espellibile(ref):
                del d[ref]
                eccesso -= 1
        if eccesso > 0 and len(d) > self._soglia_avviso:
            self._soglia_avviso = len(d) + MAX_IN_MEMORIA // 10
            logger.warning("[porta] %d ref ancora APERTI oltre il tetto di %d in memoria: "
                           "si cresce (nessun ordine aperto si dimentica)", len(d),
                           MAX_IN_MEMORIA)

    def stato(self, ref: str) -> Optional[StatoOrdine]:
        with self._lock:
            return self._stati.get(ref)

    def posizione(self, market_id: str, selection_id: Optional[int] = None) -> PosizioneConto:
        if self._fonte_posizione is None:
            raise NotImplementedError("posizione: la calcola il libro ordini del conto "
                                      "(comparto C2), non iniettato in questa porta")
        return self._fonte_posizione(market_id, selection_id)

    # ------------------------------------------------------------------- dedup
    def _ricorda(self, attore: str, ack: Ack) -> None:
        """Ack nel dedup in RAM (con ``_lock`` tenuto)."""
        self._visti[ack.ref] = ack
        self._attore_di_ref[ack.ref] = attore
        self._pota_ref(self._visti)
        self._pota_ref(self._attore_di_ref)

    def _registra_ack(self, attore: str, ack: Ack) -> None:
        """Ack nel dedup: RAM e archivio (persistente). Un errore dell'archivio SALE."""
        with self._lock:
            self._ricorda(attore, ack)
        self._archivio.scrivi(TABELLA_REF, _ack_in_riga(ack, attore, int(self._ora_ms())))

    def _dedup(self, ref: str) -> Optional[Ack]:
        """La risposta a un ref gia' visto, o None se nuovo. Fonti: memoria (riempita
        anche dal diario in ``apri``), poi la riga che QUESTA porta ha scritto
        nell'archivio (``leggi``). Solleva se l'archivio non risponde (il chiamante
        rifiuta: fail-closed).

        Parita' col motore di oggi (``motore_ordini.py:997-1005``): stesso ref = stessa
        richiesta, mai un secondo invio; si risponde con ``accettato`` e ``seq`` della
        PRIMA risposta e motivo ``ref_gia_visto``, QUALUNQUE sia la fase del ref (in volo,
        ignoto, terminale). Lo stato del ref non cambia: resta ignoto o in volo finche' un
        evento vero o la riconciliazione per ref lo chiudono; l'esito lo legge il bot da
        ``stato``/``eventi``. L'unico ``accettato=False`` su un ref noto e' quello di una
        prima risposta che era gia' un rifiuto."""
        M = _motore()
        with self._lock:
            ack = self._visti.get(ref)
        if ack is None:
            riga = self._archivio.leggi(TABELLA_REF, {"ref": ref})
            if riga is None:
                return None
            ack = _ack_da_riga(riga)
        return dataclasses.replace(ack, motivo=M.MOTIVO_REF_GIA_VISTO)

    # --------------------------------------------------------------- l'invio
    def _rifiuto_non_registrato(self, ref: str, motivo: str) -> Ack:
        self.conti["rifiutate"] += 1
        return Ack(ref=ref, accettato=False, seq=None, motivo=motivo)

    def _rifiuto_registrato(self, r: Union[RichiestaOrdine, RichiestaComposta],
                            motivo: str) -> Ack:
        with self._lock:
            seq = self._nuovo_seq(r.attore)
            ack = Ack(ref=r.ref, accettato=False, seq=seq, motivo=motivo)
            self.conti["rifiutate"] += 1
            try:
                self._registra_ack(r.attore, ack)
            except Exception as ex:  # noqa: BLE001 - il rifiuto resta rifiuto (dedup in RAM)
                logger.error("[porta] archivio KO sul rifiuto di %s (dedup solo in RAM): %s",
                             r.ref, str(ex)[:160])
            try:
                self._diario.scrivi({"tipo": "rifiuto", "ref": r.ref, "attore": r.attore,
                                     "ts_ms": int(self._ora_ms()),
                                     "ack": _ack_in_riga(ack, r.attore, 0)}, durevole=False)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[porta] diario del rifiuto %s non scritto: %s", r.ref, ex)
            self._stati[r.ref] = StatoOrdine(ref=r.ref, bet_id=None, fase="rifiutato",
                                             abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                             ultimo_seq=seq)
            self._pota_ref(self._stati)
            self._memorizza(r.attore, ack)
        return ack

    def invia(self, r: Union[RichiestaOrdine, RichiestaComposta],
              extra: Optional[ExtraComando] = None) -> Ack:
        """Il percorso di un ordine (vedi il docstring del modulo, passi 1-10)."""
        try:
            # UN invio alla volta, come il thread unico del motore (``LUCCHETTO_ORDINI``)
            with self._lock_invio:
                return self._invia(r, extra)
        finally:
            self._consegna()

    def _invia(self, r: Union[RichiestaOrdine, RichiestaComposta],
               extra: Optional[ExtraComando]) -> Ack:
        ricevuto = int(self._ora_ms())
        self.conti["richieste"] += 1
        ref = r.ref if isinstance(r.ref, str) else ""
        subito = self._ref_e_dedup(r, ref)
        if subito is not None:
            return subito
        motivo, da_eseguire, extra_eventi = self._valuta(r, extra, ricevuto)
        if motivo is not None:
            return self._rifiuto_registrato(r, motivo)
        ack = self._accetta(r, ref, da_eseguire, extra, extra_eventi)
        if ack.accettato:
            self._esegui(da_eseguire, extra)          # 9. l'esecutore, una volta sola
        return ack

    def _ref_e_dedup(self, r: Union[RichiestaOrdine, RichiestaComposta],
                     ref: str) -> Optional[Ack]:
        """Passi 1-2: attore e forma del ref (rifiuto NON registrato), poi il dedup."""
        M = _motore()
        if r.attore not in self._attori:
            return self._rifiuto_non_registrato(ref, f"{M.M_ATTORE}: {r.attore!r}")
        prefisso = f"{r.attore}-"
        if not ref or len(ref) > MAX_REF or not ref.startswith(prefisso) \
                or len(ref) == len(prefisso):
            return self._rifiuto_non_registrato(
                ref, f"{M.M_PARAM}: ref deve essere '{prefisso}<id>' di al massimo "
                     f"{MAX_REF} caratteri")
        try:
            prima = self._dedup(ref)
        except Exception as ex:  # noqa: BLE001 - dedup non verificabile: fail-closed
            logger.error("[porta] archivio illeggibile, %s RIFIUTATO: %s", ref, str(ex)[:160])
            return self._rifiuto_non_registrato(
                ref, f"{M_ARCHIVIO}: dedup per ref non verificabile ({str(ex)[:120]})")
        if prima is not None:
            self.conti["doppioni"] += 1
        return prima

    def _valuta(self, r: Union[RichiestaOrdine, RichiestaComposta],
                extra: Optional[ExtraComando],
                ricevuto: int) -> Tuple[Optional[str], Any, Dict[str, Any]]:
        """Passi 3-6: validazione di oggi, params, freni, minimi, tetto delle transazioni.
        Ritorna (motivo del rifiuto o None, richiesta da eseguire, extra degli eventi)."""
        M = _motore()
        try:
            piano = M.valida_comando(r.attore, comando_da_richiesta(r, extra))
        except M.Rifiuto as rif:
            return str(rif), r, {}
        if isinstance(r, RichiestaComposta):
            return (f"{M_COMPOSTA}: azione '{r.azione}' composta: sta sopra la porta "
                    f"(contratto C, Azione = place|cancel|replace)"), r, {}
        params = dict(extra.params) if extra is not None and extra.params else {}
        if params and not getattr(self._esecutore, "accetta_params", False):
            return (f"{M_PARAMS}: params {sorted(params)} non arrivano a questo esecutore: "
                    f"richiesta NON eseguita (mai un cap che sparisce in silenzio)"), r, {}
        max_eta = int(extra.max_eta_ms) if extra is not None and extra.max_eta_ms else \
            self.max_eta_ms
        verifica = (lambda: bool(self._riduzione_verificata(r))) \
            if self._riduzione_verificata is not None else None
        esito = CT.controlla(r, self._freni, None, ricevuto_ms=ricevuto, max_eta_ms=max_eta,
                             riduzione_verificata=verifica, guardia_armata=self._guardia_armata,
                             max_eta_settings_s=self.max_eta_settings_s)
        if not esito.ammesso:
            return str(esito.motivo), r, {}
        da_eseguire: RichiestaOrdine = r
        extra_eventi: Dict[str, Any] = {}
        if r.azione == "place":
            ok, da_eseguire, extra_eventi, motivo = self._minimi(r, piano)
            if not ok:
                return str(motivo), r, {}
        # paper e live MAI sommati: ogni modo ha il SUO contatore (o nessuno)
        contatore = self._contatori.get(r.modo)
        if contatore is not None and not contatore.consentito():
            return (f"{CT.CODICE_TETTO}: Max Transaction Count has been reached "
                    f"({contatore.totale_ora}) for current hour"), r, {}
        return None, da_eseguire, extra_eventi

    def _accetta(self, r: RichiestaOrdine, ref: str, da_eseguire: RichiestaOrdine,
                 extra: Optional[ExtraComando], extra_eventi: Dict[str, Any]) -> Ack:
        """Passi 7-8: seq, DIARIO write-ahead e poi dedup persistente, nello stesso lucchetto
        che memorizza l'ack. Se uno dei due non si scrive il comando e' RIFIUTATO
        (fail-closed); se il diario ha gia' ``inviato``, il rifiuto lo CHIUDE (riga
        ``rifiuto``), cosi' il riavvio non lo crede in volo."""
        M = _motore()
        with self._lock:
            seq = self._nuovo_seq(r.attore)
            ack = Ack(ref=ref, accettato=True, seq=seq, motivo=None)
            try:
                self._diario.scrivi({"tipo": "inviato", "canale": "porta", "ref": ref,
                                     "attore": r.attore, "azione": r.azione, "mode": r.modo,
                                     "seq": seq, "ts_ms": int(self._ora_ms()),
                                     "parametri": comando_da_richiesta(da_eseguire, extra),
                                     "ack": _ack_in_riga(ack, r.attore, 0)})
            except Exception as ex:  # noqa: BLE001 - fail-closed: senza diario niente ordine
                logger.error("[porta] diario NON scrivibile, %s RIFIUTATO: %s", ref, ex)
                return self._rifiuto_dopo_seq(
                    r, Ack(ref=ref, accettato=False, seq=seq,
                           motivo=f"{M.M_DIARIO}: {str(ex)[:160]}"), chiudi_diario=False)
            try:
                self._registra_ack(r.attore, ack)
            except Exception as ex:  # noqa: BLE001 - senza dedup persistente niente ordine
                logger.error("[porta] archivio NON scrivibile, %s RIFIUTATO: %s", ref, ex)
                return self._rifiuto_dopo_seq(
                    r, Ack(ref=ref, accettato=False, seq=seq,
                           motivo=f"{M_ARCHIVIO}: {str(ex)[:160]}"), chiudi_diario=True)
            self._richieste[ref] = da_eseguire
            self._pota_ref(self._richieste)
            if extra_eventi:
                self._extra_eventi[ref] = extra_eventi
                self._pota_ref(self._extra_eventi)
            self.conti["accettate"] += 1
            self._memorizza(r.attore, ack)
        return ack

    def _rifiuto_dopo_seq(self, r: RichiestaOrdine, ack: Ack, *, chiudi_diario: bool) -> Ack:
        """Un rifiuto col seq gia' assegnato (diario o archivio non scrivibili), con
        ``_lock`` tenuto: nel dedup (RAM, archivio se possibile) e, se ``inviato`` era gia'
        sul diario, una riga ``rifiuto`` che lo chiude."""
        self._ricorda(r.attore, ack)
        try:
            self._archivio.scrivi(TABELLA_REF, _ack_in_riga(ack, r.attore,
                                                            int(self._ora_ms())))
        except Exception as ex:  # noqa: BLE001 - il dedup resta in RAM
            logger.error("[porta] archivio KO sul rifiuto di %s: %s", ack.ref, ex)
        if chiudi_diario:
            try:
                self._diario.scrivi({"tipo": "rifiuto", "ref": ack.ref, "attore": r.attore,
                                     "ts_ms": int(self._ora_ms()),
                                     "ack": _ack_in_riga(ack, r.attore, 0)})
            except Exception as ex:  # noqa: BLE001
                logger.critical("[porta] %s: 'inviato' nel diario ma rifiuto NON scritto: "
                                "al riavvio risultera' in volo (mai partito): %s", ack.ref, ex)
        self.conti["rifiutate"] += 1
        self._stati[ack.ref] = StatoOrdine(ref=ack.ref, bet_id=None, fase="rifiutato",
                                           abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                           ultimo_seq=int(ack.seq or 0))
        self._memorizza(r.attore, ack)
        return ack

    def _minimi(self, r: RichiestaOrdine,
                piano: Mapping[str, Any]) -> Tuple[bool, RichiestaOrdine, Dict[str, Any], Optional[str]]:
        """I minimi .it (``_controlla`` + ``_applica_minimi`` del motore): apertura TENNIS
        portata al minimo, verdetto, punta 0,50, taglia gia' rifiutata."""
        M = _motore()
        riga = piano["riga"]
        lato = str(riga["side"]).lower()
        extra: Dict[str, Any] = {}
        da_eseguire = r
        if r.sport == "tennis" and not r.riduce_esposizione:
            # 28/09 (decisione dell'utente): apertura tennis sotto il minimo -> AL minimo
            chiesto = float(riga["size"])
            portata = float(MN.porta_al_minimo(lato, chiesto))
            if portata > chiesto + _EPS:
                da_eseguire = dataclasses.replace(r, importo=portata)
                extra["portata_al_minimo"] = {"chiesto": round(chiesto, 2),
                                              "piazzato": round(portata, 2)}
        importo = float(da_eseguire.importo or 0.0)
        # place-and-trim MAI dalla porta: ``RichiestaOrdine`` non ha un campo che lo dica
        # all'esecutore (un place da 0,60 partirebbe come place normale). Estensione
        # proposta nel referto; fino ad allora il verdetto e' quello di un esecutore
        # senza place-and-trim (come il runner tennis di oggi).
        v = MN.verdetto_porta(lato, float(riga["price"]), importo, submin_disponibile=False)
        if v.esito == "impossibile":
            dettaglio = str(v.motivo or "")
            if dettaglio.startswith(M.M_SOTTO_MINIMO + ":"):
                dettaglio = dettaglio[len(M.M_SOTTO_MINIMO) + 1:].strip()
            return False, r, extra, f"{M.M_SOTTO_MINIMO}: {dettaglio[:480]}"
        if v.esito == "diretto" and float(v.residuo or 0.0) > 0.0:
            chiesta = round(importo, 2)
            da_eseguire = dataclasses.replace(da_eseguire, importo=float(v.size))
            extra["punta_050"] = {"chiesto": chiesta, "piazzato": float(v.size),
                                  "residuo": round(float(v.residuo), 2),
                                  "motivo": "punta .it diretta solo a multipli di 0,50: "
                                            "arrotondata per difetto, residuo NON piazzato"}
        chiave = (r.modo, lato, round(float(da_eseguire.importo or 0.0), 2))
        if chiave in self._taglie_rifiutate:
            return False, r, extra, (
                f"{M.M_SOTTO_MINIMO}: Betfair ha gia' rifiutato INVALID_BET_SIZE un "
                f"{chiave[1].upper()} da {chiave[2]:.2f} EUR ({chiave[0]}): non si ritenta "
                f"identico")
        return True, da_eseguire, extra, None

    def _esegui(self, r: RichiestaOrdine, extra: Optional[ExtraComando]) -> None:
        """UNA chiamata all'esecutore. Un'eccezione e' un esito IGNOTO: evento ``ignoto``,
        mai ``accettato``, mai un secondo tentativo."""
        params = dict(extra.params) if extra is not None and extra.params else None
        try:
            metodo = getattr(self._esecutore, r.azione)
            ev = metodo(r, params=params) if params else metodo(r)
        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia
            logger.error("[porta] esito IGNOTO di %s (%s): %s", r.ref, r.azione, str(ex)[:200])
            self.conti["ignoti"] += 1
            ev = EventoOrdine(ref=r.ref, seq=0, fase="ignoto", bet_id=None, abbinato=0.0,
                              residuo=0.0, prezzo_medio=None,
                              codice_errore=CODICE_ESITO_IGNOTO, esito_ms=None)
        contatore = self._contatori.get(r.modo)
        if contatore is not None:
            try:
                self._conta(contatore, r, ev)
            except Exception as ex:  # noqa: BLE001 - l'ordine e' partito: l'esito si scrive
                logger.error("[porta] contatore delle transazioni KO per %s: %s", r.ref, ex)
        self._emetti(r.attore, ev, tipo="esito")

    @staticmethod
    def _conta(contatore: CT.ContatoreTransazioni, r: RichiestaOrdine,
               ev: EventoOrdine) -> None:
        """La transazione nel contatore del SUO modo: rifiutato da Betfair = contato;
        rifiutato prima di Betfair (validazione locale) = nulla; ignoto = nulla (flumine)."""
        if ev.fase == "ignoto":
            return
        if ev.fase == "rifiutato":
            if _codice_betfair(ev.codice_errore):
                contatore.registra(r.azione, "fallito", attore=r.attore)
            return
        contatore.registra(r.azione, "ok", attore=r.attore)

    def _emetti(self, attore: str, ev: EventoOrdine, *, tipo: str) -> Optional[EventoOrdine]:
        """Seq, diario (durevole), stato e memoria nella STESSA sezione di lucchetto. Un
        evento successivo (``tipo="evento"``) che farebbe regredire lo stato si scarta."""
        with self._lock:
            if _stantio(self._stati.get(ev.ref), ev):
                # anche l'ESITO del place: il flusso degli ordini puo' averlo preceduto
                self.conti["stantii"] += 1
                logger.info("[porta] %s: evento %s scartato (stato gia' %s)", ev.ref, ev.fase,
                            self._stati[ev.ref].fase)
                return None
            extra = self._extra_eventi.get(ev.ref) or {}
            if "punta_050" in extra and ev.punta_050 is None:
                ev = dataclasses.replace(ev, punta_050=extra["punta_050"])
            if "portata_al_minimo" in extra and ev.portata_al_minimo is None:
                ev = dataclasses.replace(ev, portata_al_minimo=extra["portata_al_minimo"])
            ev = dataclasses.replace(ev, seq=self._nuovo_seq(attore),
                                     esito_ms=ev.esito_ms if ev.esito_ms is not None
                                     else int(self._ora_ms()))
            self._ricorda_taglia(ev)
            try:
                self._diario.scrivi({"tipo": tipo, "ref": ev.ref, "ts_ms": int(self._ora_ms()),
                                     "evento": dataclasses.asdict(ev)})
            except Exception as ex:  # noqa: BLE001 - l'evento resta in memoria e si dice
                logger.error("[porta] diario dell'evento %s/%s non scritto: %s", ev.ref,
                             ev.seq, ex)
            self._aggiorna_stato(ev)
            if ev.fase != "ignoto" and ev.ref in self._in_volo:
                self._in_volo.remove(ev.ref)
            self.conti["eventi"] += 1
            self._memorizza(attore, ev)
        return ev

    def _ricorda_taglia(self, ev: EventoOrdine) -> None:
        """``INVALID_BET_SIZE``: quella taglia (modo, lato, importo) non si ritenta."""
        if ev.codice_errore != "INVALID_BET_SIZE":
            return
        rr = self._richieste.get(ev.ref)
        if rr is not None and rr.azione == "place":
            self._taglie_rifiutate[(rr.modo, str(rr.lato).lower(),
                                    round(float(rr.importo or 0.0), 2))] = ev.seq
            _pota(self._taglie_rifiutate, 500)

    def notifica(self, ev: EventoOrdine) -> Optional[EventoOrdine]:
        """Un aggiornamento SUCCESSIVO dell'ordine ``ev.ref`` (abbinamento, scadenza) dal
        flusso degli ordini: nuovo ``seq`` dell'attore del ref. Un ref sconosciuto o un
        evento che farebbe regredire lo stato si ignorano (e si dice)."""
        try:
            with self._lock:
                attore = self._attore_di_ref.get(ev.ref)
            if attore is None:
                logger.warning("[porta] evento per un ref sconosciuto %s: ignorato", ev.ref)
                return None
            return self._emetti(attore, ev, tipo="evento")
        finally:
            self._consegna()
