"""porta.py - ``PortaOrdini`` sopra un ``Esecutore`` iniettato (W1-C1, 09/10/2026).

Scopo
-----
La porta unica degli ordini del contratto C (04 par. 3.4): riceve una
``RichiestaOrdine``, risponde con un ``Ack`` e pubblica la sequenza di ``EventoOrdine``
dell'ordine, con le garanzie che oggi da' ``motore_ordini.MotoreOrdini`` (F3 del suo
docstring) e nello stesso ordine:

  1. il ``ref`` e' ``"<attore>-<id>"`` di al massimo 32 caratteri, l'attore e' ammesso;
     altrimenti rifiuto NON registrato (senza seq, senza dedup), come il motore;
  2. DEDUP per ``ref``: lo stesso ref = la stessa richiesta, mai un secondo invio; la
     risposta e' l'ack della PRIMA volta con motivo ``ref_gia_visto``. Il dedup vale per
     tutta la vita del processo (ben oltre i 60 s di Betfair) e SOPRAVVIVE al riavvio
     tramite l'``Archivio`` iniettato (``nucleo/dati/contratto.py``, tabella locale
     ``TABELLA_REF``) e il diario;
  3. validazione con ``valida_comando`` di oggi (via ``adattatore_comando``);
  4. freni (``controlli.controlla``): eta', modo della RIGA (mai del servizio), guardia
     d'avvio, modo effettivo sulle aperture, kill-switch, settings;
  5. minimi .it (``minimi.verdetto_porta``): punta diretta a multiplo di 0,50 per difetto
     col residuo dichiarato (``punta_050`` negli eventi), sotto il minimo rifiuto
     ``SOTTO_MINIMO_NON_PIAZZABILE`` (place-and-trim solo se l'esecutore lo dichiara);
     una taglia gia' rifiutata da Betfair (``INVALID_BET_SIZE``) non si ritenta identica;
  6. tetto delle transazioni/ora UNO per conto (``controlli.ContatoreTransazioni``);
  7. ``seq`` per attore (UN contatore per ack ed eventi, base = istante d'avvio, mai
     indietro), memoria degli ultimi ``MEMORIA_EVENTI`` messaggi per ``da_seq``;
  8. DIARIO write-ahead (la classe ``motore_ordini.Diario`` di oggi, iniettata): la riga
     ``inviato`` e' su disco (flush+fsync) PRIMA dell'esecutore; senza diario niente
     ordine (``diario_non_scrivibile``); poi ``esito`` ed ``evento``;
  9. un esito IGNOTO (eccezione o timeout dell'esecutore) e' l'evento ``ignoto``: MAI
     trasformato in ``accettato``/``abbinato``, MAI ritentato (i soldi non si ritentano).

Entrate: ``Esecutore`` (place/cancel/replace -> ``EventoOrdine``), ``FreniConto``,
``Archivio``, diario, orologio, contatore. Uscite: ``Ack``, ``EventoOrdine`` (in memoria,
ai consumatori iscritti, in ``eventi``/``da_seq``), ``StatoOrdine`` per ref.

Cosa NON fa (ondata 1): non e' agganciata all'app; e' SINCRONA (l'esecutore gira nel
thread di ``invia``: il thread del motore e' dell'ondata 2); non fa place-and-trim ne'
ordini equivalenti ne' azioni composte (green-up, cash-out: sopra la porta); non calcola
la posizione (comparto C2: ``posizione`` delega a una fonte iniettata); non riconcilia
con Betfair gli ordini in volo al riavvio: li marca ``ignoto`` e li elenca (``in_volo``).
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
MAX_REF = 32
MEMORIA_EVENTI = 500
MAX_ETA_DEFAULT_MS = 3000
MAX_ETA_SETTINGS_S_DEFAULT = 10.0
#: codice dell'evento di un esito IGNOTO (eccezione/timeout dell'esecutore)
CODICE_ESITO_IGNOTO = "ESITO_IGNOTO"
#: rifiuti della porta che il motore non ha (fail-closed sul dedup persistente)
M_ARCHIVIO = "archivio_non_disponibile"
M_COMPOSTA = "azione_composta_sopra_la_porta"


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
    return {"ref": ack.ref, "attore": attore, "accettato": ack.accettato, "seq": ack.seq,
            "motivo": ack.motivo, "ts_ms": ts_ms}


def _ack_da_riga(riga: Mapping[str, Any]) -> Ack:
    seq = riga.get("seq")
    return Ack(ref=str(riga.get("ref")), accettato=bool(riga.get("accettato")),
               seq=int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None,
               motivo=riga.get("motivo"))


def _evento_in_riga(ev: EventoOrdine) -> Dict[str, Any]:
    return dataclasses.asdict(ev)


class PortaLocale:
    """``PortaOrdini`` in-process sopra un ``Esecutore``. Thread-safe: gli invii sono
    SERIALIZZATI (``_lock_invio``, come il thread unico del motore di oggi); seq, memoria e
    stati hanno il loro lucchetto, e ``notifica`` (flusso degli ordini) non aspetta l'invio."""

    def __init__(self, esecutore: Esecutore, *, freni: CT.FreniConto, archivio: Archivio,
                 diario: Diario, contatore: Optional[CT.ContatoreTransazioni] = None,
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
        self._contatore = contatore
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
        self._base_seq = int(orologio_ms())
        self._seq: Dict[str, int] = {}
        self._memoria: Dict[str, Deque[Messaggio]] = {}
        self._visti: Dict[str, Ack] = {}
        self._attore_di_ref: Dict[str, str] = {}
        self._richieste: Dict[str, RichiestaOrdine] = {}
        self._stati: Dict[str, StatoOrdine] = {}
        self._extra_eventi: Dict[str, Dict[str, Any]] = {}
        self._taglie_rifiutate: "collections.OrderedDict[Tuple[str, str, float], int]" = \
            collections.OrderedDict()
        self._consumatori: Dict[str, List[Callable[[Messaggio], None]]] = {}
        self._in_volo: List[str] = []
        self.conti: Dict[str, int] = {"richieste": 0, "accettate": 0, "rifiutate": 0,
                                      "doppioni": 0, "eventi": 0, "ignoti": 0}

    # ------------------------------------------------------------ ciclo di vita
    def _giorni(self) -> List[str]:
        oggi = datetime.fromtimestamp(self._ora_ms() / 1000.0)
        return [(oggi - timedelta(days=1)).strftime("%Y-%m-%d"), oggi.strftime("%Y-%m-%d")]

    def apri(self) -> None:
        """Rilegge il diario: ack gia' dati (dedup), ultimo stato per ref, ordini in volo
        al riavvio (``inviato`` senza ``esito``) -> stato ``ignoto`` ed elenco ``in_volo``.
        Diario illeggibile: si DICE (dedup dall'archivio, stati vuoti)."""
        try:
            righe = self._diario.leggi(self._giorni())
        except Exception as ex:  # noqa: BLE001 - il dedup resta all'archivio
            logger.error("[porta] diario illeggibile all'apertura: %s", str(ex)[:200])
            return
        inviati: Dict[str, Dict[str, Any]] = {}
        chiusi = set()
        with self._lock:
            for rec in righe:
                ref = rec.get("ref")
                if not isinstance(ref, str):
                    continue
                tipo = rec.get("tipo")
                if tipo in ("inviato", "rifiuto") and isinstance(rec.get("ack"), dict):
                    self._visti.setdefault(ref, _ack_da_riga(rec["ack"]))
                    if rec.get("attore"):
                        self._attore_di_ref[ref] = str(rec["attore"])
                if tipo == "inviato":
                    inviati[ref] = rec
                elif tipo in ("esito", "evento") and isinstance(rec.get("evento"), dict):
                    chiusi.add(ref)
                    try:
                        self._aggiorna_stato(EventoOrdine(**rec["evento"]))
                    except (TypeError, ValueError) as ex:
                        # riga scritta da un'altra versione: si DICE, lo stato resta
                        # quello delle righe leggibili (il ref resta chiuso: nessun reinvio)
                        logger.error("[porta] diario: evento di %s illeggibile: %s", ref,
                                     str(ex)[:160])
            for ref, rec in inviati.items():
                if ref in chiusi:
                    continue
                self._in_volo.append(ref)
                seq = (rec.get("ack") or {}).get("seq") or 0
                self._stati[ref] = StatoOrdine(ref=ref, bet_id=None, fase="ignoto",
                                               abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                               ultimo_seq=int(seq))
        if self._in_volo:
            logger.warning("[porta] %d ordini in volo al riavvio (stato ignoto, da "
                           "riconciliare): %s", len(self._in_volo), ", ".join(self._in_volo)[:300])

    def chiudi(self) -> None:
        try:
            self._diario.chiudi()
        except Exception as ex:  # noqa: BLE001
            logger.error("[porta] chiusura del diario KO: %s", str(ex)[:200])

    def in_volo(self) -> Tuple[str, ...]:
        """I ref inviati e senza esito al riavvio: li riconcilia C2, mai un secondo invio."""
        with self._lock:
            return tuple(self._in_volo)

    # ------------------------------------------------------------ seq e memoria
    def _prossimo_seq(self, attore: str) -> int:
        with self._lock:
            s = self._seq.get(attore, self._base_seq) + 1
            self._seq[attore] = s
            return s

    def _pubblica(self, attore: str, m: Messaggio) -> None:
        with self._lock:
            mem = self._memoria.get(attore)
            if mem is None:
                mem = collections.deque(maxlen=self._memoria_max)
                self._memoria[attore] = mem
            mem.append(m)
            cbs = list(self._consumatori.get(attore, ()))
        for cb in cbs:
            try:
                cb(m)
            except Exception:  # noqa: BLE001 - un consumatore rotto non ferma la porta
                logger.exception("[porta] consumatore di %s KO", attore)

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
        if prima is not None and prima.fase in FASI_TERMINALI and ev.fase not in FASI_TERMINALI:
            return
        self._stati[ev.ref] = StatoOrdine(
            ref=ev.ref, bet_id=ev.bet_id or (prima.bet_id if prima else None), fase=ev.fase,
            abbinato=float(ev.abbinato), residuo=float(ev.residuo),
            prezzo_medio=ev.prezzo_medio, ultimo_seq=int(ev.seq))

    def stato(self, ref: str) -> Optional[StatoOrdine]:
        with self._lock:
            return self._stati.get(ref)

    def posizione(self, market_id: str, selection_id: Optional[int] = None) -> PosizioneConto:
        if self._fonte_posizione is None:
            raise NotImplementedError("posizione: la calcola il libro ordini del conto "
                                      "(comparto C2), non iniettato in questa porta")
        return self._fonte_posizione(market_id, selection_id)

    # ------------------------------------------------------------------- dedup
    def _gia_visto(self, ref: str) -> Optional[Ack]:
        """L'ack della prima volta, dalla RAM o dall'archivio. Solleva se l'archivio non
        risponde (il chiamante rifiuta: fail-closed)."""
        with self._lock:
            ack = self._visti.get(ref)
        if ack is not None:
            return ack
        riga = self._archivio.leggi(TABELLA_REF, {"ref": ref})
        if riga is None:
            return None
        ack = _ack_da_riga(riga)
        with self._lock:
            self._visti.setdefault(ref, ack)
        return ack

    def _registra_ack(self, attore: str, ack: Ack) -> None:
        """Ack nel dedup: RAM e archivio (persistente). Un errore dell'archivio SALE."""
        with self._lock:
            self._visti[ack.ref] = ack
            self._attore_di_ref[ack.ref] = attore
        self._archivio.scrivi(TABELLA_REF, _ack_in_riga(ack, attore, int(self._ora_ms())))

    # --------------------------------------------------------------- l'invio
    def _rifiuto_non_registrato(self, ref: str, motivo: str) -> Ack:
        self.conti["rifiutate"] += 1
        return Ack(ref=ref, accettato=False, seq=None, motivo=motivo)

    def _rifiuto_registrato(self, r: Union[RichiestaOrdine, RichiestaComposta],
                            motivo: str) -> Ack:
        seq = self._prossimo_seq(r.attore)
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
        with self._lock:
            self._stati[r.ref] = StatoOrdine(ref=r.ref, bet_id=None, fase="rifiutato",
                                             abbinato=0.0, residuo=0.0, prezzo_medio=None,
                                             ultimo_seq=seq)
        self._pubblica(r.attore, ack)
        return ack

    def invia(self, r: Union[RichiestaOrdine, RichiestaComposta],
              extra: Optional[ExtraComando] = None) -> Ack:
        """Il percorso di un ordine (vedi il docstring del modulo, passi 1-9)."""
        # UN invio alla volta, come il thread unico del motore (``LUCCHETTO_ORDINI``): due
        # thread con lo stesso ref non passano mai insieme il controllo del dedup
        with self._lock_invio:
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
                self._esegui(da_eseguire)          # 9. l'esecutore, una volta sola
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
            prima = self._gia_visto(ref)
        except Exception as ex:  # noqa: BLE001 - dedup non verificabile: fail-closed
            logger.error("[porta] archivio illeggibile, %s RIFIUTATO: %s", ref, str(ex)[:160])
            return self._rifiuto_non_registrato(
                ref, f"{M_ARCHIVIO}: dedup per ref non verificabile ({str(ex)[:120]})")
        if prima is not None:
            self.conti["doppioni"] += 1
            return dataclasses.replace(prima, motivo=M.MOTIVO_REF_GIA_VISTO)
        return None

    def _valuta(self, r: Union[RichiestaOrdine, RichiestaComposta],
                extra: Optional[ExtraComando],
                ricevuto: int) -> Tuple[Optional[str], Any, Dict[str, Any]]:
        """Passi 3-6: validazione di oggi, freni, minimi, tetto delle transazioni.
        Ritorna (motivo del rifiuto o None, richiesta da eseguire, extra degli eventi)."""
        M = _motore()
        try:
            piano = M.valida_comando(r.attore, comando_da_richiesta(r, extra))
        except M.Rifiuto as rif:
            return str(rif), r, {}
        if isinstance(r, RichiestaComposta):
            return (f"{M_COMPOSTA}: azione '{r.azione}' composta: sta sopra la porta "
                    f"(contratto C, Azione = place|cancel|replace)"), r, {}
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
        if self._contatore is not None and not self._contatore.consentito():
            return (f"{CT.CODICE_TETTO}: Max Transaction Count has been reached "
                    f"({self._contatore.totale_ora}) for current hour"), r, {}
        return None, da_eseguire, extra_eventi

    def _accetta(self, r: RichiestaOrdine, ref: str, da_eseguire: RichiestaOrdine,
                 extra: Optional[ExtraComando], extra_eventi: Dict[str, Any]) -> Ack:
        """Passi 7-8: seq, dedup persistente (archivio), diario write-ahead. Se uno dei
        due non si scrive il comando e' RIFIUTATO (fail-closed) e il rifiuto resta nel
        dedup."""
        M = _motore()
        seq = self._prossimo_seq(r.attore)
        ack = Ack(ref=ref, accettato=True, seq=seq, motivo=None)
        try:
            self._registra_ack(r.attore, ack)
        except Exception as ex:  # noqa: BLE001 - senza dedup persistente niente ordine
            logger.error("[porta] archivio NON scrivibile, %s RIFIUTATO: %s", ref, ex)
            return self._rifiuto_dopo_seq(r, Ack(ref=ref, accettato=False, seq=seq,
                                                 motivo=f"{M_ARCHIVIO}: {str(ex)[:160]}"),
                                          persisti=False)
        try:
            self._diario.scrivi({"tipo": "inviato", "canale": "porta", "ref": ref,
                                 "attore": r.attore, "azione": r.azione, "mode": r.modo,
                                 "seq": seq, "ts_ms": int(self._ora_ms()),
                                 "parametri": comando_da_richiesta(da_eseguire, extra),
                                 "ack": _ack_in_riga(ack, r.attore, 0)})
        except Exception as ex:  # noqa: BLE001 - fail-closed: senza diario niente ordine
            logger.error("[porta] diario NON scrivibile, %s RIFIUTATO: %s", ref, ex)
            return self._rifiuto_dopo_seq(r, Ack(ref=ref, accettato=False, seq=seq,
                                                 motivo=f"{M.M_DIARIO}: {str(ex)[:160]}"),
                                          persisti=True)
        with self._lock:
            self._richieste[ref] = da_eseguire
            if extra_eventi:
                self._extra_eventi[ref] = extra_eventi
        self.conti["accettate"] += 1
        self._pubblica(r.attore, ack)
        return ack

    def _rifiuto_dopo_seq(self, r: RichiestaOrdine, ack: Ack, *, persisti: bool) -> Ack:
        """Un rifiuto con il seq gia' assegnato (archivio o diario non scrivibili)."""
        with self._lock:
            self._visti[ack.ref] = ack
        if persisti:
            try:
                self._registra_ack(r.attore, ack)
            except Exception as ex:  # noqa: BLE001 - il dedup resta in RAM
                logger.error("[porta] archivio KO sul rifiuto di %s: %s", ack.ref, ex)
        self.conti["rifiutate"] += 1
        self._pubblica(r.attore, ack)
        return ack

    def _minimi(self, r: RichiestaOrdine,
                piano: Mapping[str, Any]) -> Tuple[bool, RichiestaOrdine, Dict[str, Any], Optional[str]]:
        """Il verdetto dei minimi .it e la taglia gia' rifiutata (``_applica_minimi``)."""
        M = _motore()
        riga = piano["riga"]
        lato = str(riga["side"]).lower()
        v = MN.verdetto_porta(lato, float(riga["price"]), float(riga["size"]),
                              submin_disponibile=bool(getattr(self._esecutore,
                                                              "submin_disponibile", False)))
        extra: Dict[str, Any] = {}
        da_eseguire = r
        if v.esito == "impossibile":
            dettaglio = str(v.motivo or "")
            if dettaglio.startswith(M.M_SOTTO_MINIMO + ":"):
                dettaglio = dettaglio[len(M.M_SOTTO_MINIMO) + 1:].strip()
            return False, r, extra, f"{M.M_SOTTO_MINIMO}: {dettaglio[:480]}"
        if v.esito == "diretto" and float(v.residuo or 0.0) > 0.0:
            chiesta = round(float(riga["size"]), 2)
            da_eseguire = dataclasses.replace(r, importo=float(v.size))
            extra["punta_050"] = {"chiesto": chiesta, "piazzato": float(v.size),
                                  "residuo": round(float(v.residuo), 2),
                                  "motivo": "punta .it diretta solo a multipli di 0,50: "
                                            "arrotondata per difetto, residuo NON piazzato"}
        chiave = (r.modo, lato, round(float(da_eseguire.importo or 0.0), 2))
        if v.esito != "submin" and chiave in self._taglie_rifiutate:
            return False, r, extra, (
                f"{M.M_SOTTO_MINIMO}: Betfair ha gia' rifiutato INVALID_BET_SIZE un "
                f"{chiave[1].upper()} da {chiave[2]:.2f} EUR ({chiave[0]}): non si ritenta "
                f"identico")
        return True, da_eseguire, extra, None

    def _esegui(self, r: RichiestaOrdine) -> None:
        """UNA chiamata all'esecutore. Un'eccezione e' un esito IGNOTO: evento ``ignoto``,
        mai ``accettato``, mai un secondo tentativo."""
        try:
            if r.azione == "place":
                ev = self._esecutore.place(r)
            elif r.azione == "cancel":
                ev = self._esecutore.cancel(r)
            else:
                ev = self._esecutore.replace(r)
        except Exception as ex:  # noqa: BLE001 - esito ignoto, si dice e si riconcilia
            logger.error("[porta] esito IGNOTO di %s (%s): %s", r.ref, r.azione, str(ex)[:200])
            self.conti["ignoti"] += 1
            ev = EventoOrdine(ref=r.ref, seq=0, fase="ignoto", bet_id=None, abbinato=0.0,
                              residuo=0.0, prezzo_medio=None,
                              codice_errore=CODICE_ESITO_IGNOTO, esito_ms=None)
        if self._contatore is not None:
            self._conta(r, ev)
        self._emetti(r.attore, ev, tipo="esito")

    def _conta(self, r: RichiestaOrdine, ev: EventoOrdine) -> None:
        """La transazione per conto: rifiutato da Betfair = fallita; rifiutato prima di
        Betfair (validazione locale) = nulla; ignoto = nulla (come flumine)."""
        if ev.fase == "ignoto":
            return
        if ev.fase == "rifiutato":
            if _codice_betfair(ev.codice_errore):
                self._contatore.registra(r.azione, "fallito", attore=r.attore)
            return
        self._contatore.registra(r.azione, "ok", attore=r.attore)

    def _emetti(self, attore: str, ev: EventoOrdine, *, tipo: str) -> EventoOrdine:
        with self._lock:
            extra = self._extra_eventi.get(ev.ref)
        if extra and "punta_050" in extra and ev.punta_050 is None:
            ev = dataclasses.replace(ev, punta_050=extra["punta_050"])
        ev = dataclasses.replace(ev, seq=self._prossimo_seq(attore),
                                 esito_ms=ev.esito_ms if ev.esito_ms is not None
                                 else int(self._ora_ms()))
        if ev.codice_errore == "INVALID_BET_SIZE":
            with self._lock:
                rr = self._richieste.get(ev.ref)
                if rr is not None and rr.azione == "place":
                    self._taglie_rifiutate[(rr.modo, str(rr.lato),
                                            round(float(rr.importo or 0.0), 2))] = ev.seq
                    while len(self._taglie_rifiutate) > 500:
                        self._taglie_rifiutate.popitem(last=False)
        try:
            self._diario.scrivi({"tipo": tipo, "ref": ev.ref, "ts_ms": int(self._ora_ms()),
                                 "evento": _evento_in_riga(ev)}, durevole=False)
        except Exception as ex:  # noqa: BLE001 - l'evento resta in memoria e si dice
            logger.error("[porta] diario dell'evento %s/%s non scritto: %s", ev.ref, ev.seq, ex)
        with self._lock:
            self._aggiorna_stato(ev)
        self.conti["eventi"] += 1
        self._pubblica(attore, ev)
        return ev

    def notifica(self, ev: EventoOrdine) -> Optional[EventoOrdine]:
        """Un aggiornamento SUCCESSIVO dell'ordine ``ev.ref`` (abbinamento, scadenza) dal
        flusso degli ordini: nuovo ``seq`` dell'attore del ref. Un ref sconosciuto o un
        evento non terminale dopo un terminale si ignorano (e si dice)."""
        with self._lock:
            attore = self._attore_di_ref.get(ev.ref)
            prima = self._stati.get(ev.ref)
        if attore is None:
            logger.warning("[porta] evento per un ref sconosciuto %s: ignorato", ev.ref)
            return None
        if prima is not None and prima.fase in FASI_TERMINALI and ev.fase not in FASI_TERMINALI:
            logger.info("[porta] %s: evento %s dopo la fase terminale %s ignorato", ev.ref,
                        ev.fase, prima.fase)
            return None
        return self._emetti(attore, ev, tipo="evento")
