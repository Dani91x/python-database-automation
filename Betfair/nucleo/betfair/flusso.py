"""flusso.py - il gestore degli stream dei PREZZI per profilo (``contratto.FlussoMercato``).

Scopo (tappa T19, scheda A P4): UNA politica di connessione, sottoscrizione,
ripresa e salute per tutti gli stream di mercato, con il profilo
(``profili.py``) come unico parametro. Oggi le stesse cose sono scritte quattro
volte: ``frammenti_mercato.py`` (calcio), ``tennis_runner.py`` +
``iscrizione_a_caldo.py`` (tennis), ``safe_strategy/stream.py`` (scanner),
``scalper_session.py``.

Le regole (tutte nei test ``tests/test_a2_flusso*.py``):
* SUDDIVISIONE: i mercati vanno su connessioni da al massimo
  ``mercati_per_connessione`` (180 di serie, MAI oltre 200 = limite Betfair per
  sottoscrizione). Un mercato non cambia connessione finche' la sua connessione e'
  viva; i nuovi riempiono quelle esistenti in ordine, poi connessioni nuove fino a
  ``connessioni_max``. Il piano e' quello di ``frammenti_mercato.pianifica``,
  riscritto qui (``piano_connessioni``) e confrontato col vecchio su griglie.
* SOTTOSCRIZIONE SOSTITUTIVA: una ``marketSubscription`` nuova SOSTITUISCE la
  precedente sulla stessa connessione (Exchange Stream API): a ogni cambio si
  rimanda l'insieme INTERO dei mercati di quella connessione (immagine piena solo
  per lei), mai un pezzo. Mai una sottoscrizione vuota (= tutto l'exchange).
* BUDGET: una connessione nuova si apre solo se Betfair, all'ultima
  autenticazione, ha dichiarato piu' connessioni libere della ``riserva`` del
  profilo (``connectionsAvailable``, anche 0), e mai per ``PAUSA_RIFIUTO_S`` dopo un
  rifiuto (``MAX_CONNECTION_LIMIT_EXCEEDED``, ``TOO_MANY_REQUESTS``, ...): come
  ``GestoreFrammenti.massimo_adesso`` (``connessioni_concesse``, confrontata).
* RIPRESA: dopo una caduta la connessione si riapre con ``initialClk``/``clk``
  (``RESUB_DELTA``: solo i cambi), backoff 2..60 s azzerato SOLO dopo una
  connessione rimasta su oltre ``VIVA_DOPO_S`` dal COLLEGAMENTO
  (``connessa_dal_mono``: ne' le risottoscrizioni ne' il watchdog lo toccano), mai
  dopo ``ferma``/chiusura; ``INVALID_CLOCK``, un messaggio non applicabile, un cambio
  di mercati durante la caduta o il ricollegamento, o una risottoscrizione fallita =
  immagine piena (i criteri della ripresa devono essere IDENTICI: mai ``initialClk``/
  ``clk`` con un filtro diverso).
* RISOTTOSCRIZIONE: ``imposta_mercati`` non solleva MAI per un errore di rete:
  la connessione si chiude e riparte da immagine piena con l'insieme nuovo; se la
  libreria ricollega lo stream fermato DENTRO l'invio (``BetfairStream._send``),
  quel socket orfano si chiude subito (budget di 10 connessioni).
* CONSUMATORI MULTIPLI (decisioni 8 e 13 dell'utente, 10/10/2026: un gestore per
  tutta l'app, mai connessioni doppie): ogni consumatore (bot, ladder, scanner)
  dichiara il SUO insieme con ``richiedi_mercati(chi, mercati)``; si sottoscrive
  l'UNIONE delle richieste (stessi mercati da tre consumatori = le connessioni di
  uno). ``imposta_mercati`` (il contratto) e' la richiesta ``RICHIESTA_DIRETTA``:
  senza altre richieste fa esattamente quello che faceva. Un consumatore legato a
  una richiesta (``aggiungi_consumatore(cb, richiesta=chi)``) riceve solo i book
  dei mercati di quella richiesta, seguendola quando cambia.
* BOOK: ``book()`` e i consumatori vedono SOLO i mercati dell'insieme corrente
  (pianificato): un book in volo di un mercato tolto non si scrive ne' si consegna.
* SALUTE: per connessione, la regola di ``Betfair/stream/stream_muto.py``
  (riusata: ``stato_da_battiti``; 3 heartbeat senza messaggi = muto, ``status``
  503 = latente); per mercato ``vivo`` = connessione viva E un book ricevuto sulla
  sottoscrizione corrente; ``muto`` altrimenti; ``assente`` = non sottoscritto.
  ``manutenzione`` chiude le connessioni rifiutate e quelle mute oltre ``MUTO_S``
  mentre un'altra e' viva (i mercati tornano al piano), come
  ``GestoreFrammenti.manutenzione``.

Entrate: ``Sessione`` (``client()`` = ``APIClient`` valido), il ``ProfiloFlusso``,
``imposta_mercati``. Uscite: i ``MarketBook`` della libreria ai consumatori (un
thread di consegna; prima la conversione GBP->EUR di ``valuta.converti_libro``,
poi ``trasforma`` facoltativa), ``book``,
``stato``, ``stato_flusso``.

Cosa NON fa: non decide quali mercati seguire (auto-follow, D), non registra il
raw (P5), non scrive DB, non tocca flumine (il
banco resta su ``HistoricalStream``). Importare il modulo non apre socket ne'
thread: nascono in ``avvia``/``imposta_mercati`` e muoiono in ``ferma``.
"""
from __future__ import annotations

import collections
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from betfairlightweight.filters import streaming_market_filter
from betfairlightweight.streaming.listener import StreamListener

from Betfair.stream import stream_muto as _SM
from Betfair.stream import valuta as _valuta

from .contratto import ProfiloFlusso, Sessione, StatoFlusso
from .flusso_ordini_conto import attesa_di_backoff, segnala_sessione
from .profili import LIMITE_BETFAIR_CONNESSIONI, LIMITE_BETFAIR_MERCATI, filtro_dati

logger = logging.getLogger(__name__)

#: una connessione nuova non autenticata entro tanto = rifiutata (s)
#: (``frammenti_mercato.py:94``)
ATTESA_APERTURA_S = 60.0
#: dopo un rifiuto nessuna connessione nuova per tanto (s) (``frammenti_mercato.py:96``)
PAUSA_RIFIUTO_S = 300.0
#: una connessione senza NESSUN messaggio da tanto, con un'altra viva, si chiude
#: e i suoi mercati si ripiazzano (s) (``frammenti_mercato.py:98``)
MUTO_S = 180.0
#: codici Betfair = "connessione non concessa" (``frammenti_mercato.py:101-102``)
CODICI_RIFIUTO = frozenset({"MAX_CONNECTION_LIMIT_EXCEEDED", "TOO_MANY_REQUESTS",
                            "SUBSCRIPTION_LIMIT_EXCEEDED"})
CODICI_SESSIONE = frozenset({"NO_SESSION", "INVALID_SESSION_INFORMATION", "NOT_AUTHORIZED"})
CODICE_CLK_NON_VALIDO = "INVALID_CLOCK"
BACKOFF_MIN_S = 2.0
BACKOFF_MAX_S = 60.0
#: SOLO una connessione rimasta su oltre tanto dalla sottoscrizione azzera il backoff
#: (ricevere dati non basta: immagine e chiusura a ogni giro = tempesta).
#: DIVERGENZA MIGLIORATIVA dichiarata: ``FrammentoMarketStream.run`` di oggi
#: (``frammenti_mercato.py:203-217``) non azzera mai il tentativo: dopo qualche caduta
#: anche una connessione sana aspetta 60 s a ogni ripresa.
VIVA_DOPO_S = 60.0
#: quante attese di backoff recenti si mostrano nello stato di ogni connessione
ATTESE_RICORDATE = 20
#: battiti senza messaggi oltre i quali il watchdog chiude e riprende con clk: 3 come il
#: "muto" di ``stream_muto`` (Betfair dice 2 = "forse disconnesso"; un battito di margine)
BATTITI_WATCHDOG = _SM.BATTITI_PER_SOGLIA


# ---------------------------------------------------------------------------
# piano e budget (puri; gemelli di frammenti_mercato.pianifica / massimo_adesso)
# ---------------------------------------------------------------------------
@dataclass
class PianoConnessioni:
    #: sottoscrizione voluta per ogni connessione ESISTENTE (stesso ordine)
    bersagli: List[Set[str]]
    #: connessioni da aprire, ognuna con i suoi mercati
    nuovi: List[Set[str]] = field(default_factory=list)
    #: mercati voluti che non entrano
    fuori: Set[str] = field(default_factory=set)


def piano_connessioni(attuali: List[Set[str]], voluti: Iterable[str], per_conn: int,
                      max_conn: int) -> PianoConnessioni:
    """Distribuisce ``voluti`` sulle connessioni: chi c'e' resta dov'e', i nuovi
    (in ordine di id) riempiono le esistenti in ordine e poi connessioni nuove da
    al massimo ``per_conn`` fino a ``max_conn``; il resto e' ``fuori``. La prima
    connessione senza piu' niente di voluto tiene i mercati di prima (mai una
    sottoscrizione vuota); un'altra vuota ha bersaglio vuoto (= da chiudere)."""
    per_conn = max(1, min(int(per_conn), LIMITE_BETFAIR_MERCATI))
    max_conn = max(1, int(max_conn))
    vol = {str(m) for m in voluti if m}
    tenuti: List[Set[str]] = [set(a) & vol for a in attuali]
    presenti: Set[str] = set().union(*tenuti) if tenuti else set()
    da_mettere = sorted(vol - presenti)
    for t in tenuti:
        posto = per_conn - len(t)
        if posto > 0 and da_mettere:
            t.update(da_mettere[:posto])
            da_mettere = da_mettere[posto:]
    nuovi: List[Set[str]] = []
    while da_mettere and len(tenuti) + len(nuovi) < max_conn:
        nuovi.append(set(da_mettere[:per_conn]))
        da_mettere = da_mettere[per_conn:]
    if tenuti and not tenuti[0]:
        tenuti[0] = set(attuali[0])
    return PianoConnessioni(bersagli=tenuti, nuovi=nuovi, fuori=set(da_mettere))


def connessioni_concesse(aperte: int, max_conn: int, riserva: int, per_conn: int,
                         disponibili: Optional[int], in_pausa: bool,
                         ultimo_rifiuto: Optional[str], *,
                         pausa_s: float = PAUSA_RIFIUTO_S,
                         nome_env: str = "RUNNER_CALCIO_STREAM_CONNS") -> Tuple[int, str]:
    """(connessioni concesse ADESSO, motivo del limite): ``max_conn``, salvo pausa
    dopo un rifiuto o riserva per gli altri processi (in quei casi: quelle gia'
    aperte, mai meno di 1). ``disponibili`` = ultimo ``connectionsAvailable``."""
    aperti = max(1, int(aperte))
    if in_pausa:
        return (min(max_conn, aperti),
                "Betfair ha rifiutato una connessione (%s): nessuna connessione nuova per %.0f s"
                % (ultimo_rifiuto, pausa_s))
    if disponibili is not None and disponibili <= riserva and aperti < max_conn:
        return (min(max_conn, aperti),
                "Betfair dichiara %d connessioni libere, riserva %d per scanner/scalper/tennis"
                % (disponibili, riserva))
    return max_conn, ("tetto configurato: %d connessioni x %d mercati (%s)"
                      % (max_conn, per_conn, nome_env))


_NOMI_ENV = {"runner_calcio": "RUNNER_CALCIO_STREAM_CONNS",
             "scansione": "SAFE_STRATEGY_STREAM_CONNS"}


# ---------------------------------------------------------------------------
# listener di una connessione: libreria vera + battito + mercati serviti
# ---------------------------------------------------------------------------
class _Uscita:
    """La ``output_queue`` della libreria: riceve nel thread del socket la lista
    dei ``MarketBook`` di un messaggio; segna i mercati serviti e passa avanti."""

    def __init__(self, listener: "ListenerFlusso", inoltra: Callable[[List[Any]], None]) -> None:
        self._li = listener
        self._inoltra = inoltra

    def put(self, libri: List[Any]) -> None:
        for b in libri:
            self._li.serviti.add(str(b.market_id))
        self._li.ultimo_dato_mono = self._li.ora()
        self._inoltra(libri)


class ListenerFlusso(StreamListener):
    """``StreamListener`` di betfairlightweight (``MarketBook`` veri) con il battito
    della SUA connessione, come ``frammenti_mercato.FrammentoListener``."""

    def __init__(self, inoltra: Callable[[List[Any]], None], orologio: Callable[[], float]) -> None:
        super().__init__(output_queue=None, max_latency=None, lightweight=False)
        self.output_queue = _Uscita(self, inoltra)
        self.ora = orologio
        self.ultimo_msg_mono = 0.0
        self.ultimo_dato_mono = 0.0
        self.autenticato = False
        self.autenticato_una_volta = False
        self.ultimo_errore: Optional[str] = None
        self.connessioni_disponibili: Optional[int] = None
        self.connessioni_lette_mono = 0.0
        self.heartbeat_ms_server: Optional[int] = None
        self.errore_elaborazione = False
        self.mcm = 0
        #: mercati con almeno un book sulla sottoscrizione CORRENTE
        self.serviti: Set[str] = set()

    def register_stream(self, unique_id: int, operation: str) -> None:
        self.serviti = set()            # sottoscrizione nuova: immagine nuova
        super().register_stream(unique_id, operation)

    def on_data(self, raw_data: str) -> Optional[bool]:
        self._osserva(raw_data)
        try:
            return super().on_data(raw_data)
        except Exception:
            self.errore_elaborazione = True     # clk gia' avanzato: si riparte da immagine
            raise

    def _osserva(self, raw_data: str) -> None:
        self.ultimo_msg_mono = self.ora()
        try:
            d = json.loads(raw_data)
        except ValueError:
            logger.warning("[flusso] messaggio illeggibile: %s", str(raw_data)[:120])
            return
        op = d.get("op")
        if op == "status":
            disp = d.get("connectionsAvailable")
            if isinstance(disp, int) and not isinstance(disp, bool):
                self.connessioni_disponibili = disp
                self.connessioni_lette_mono = self.ultimo_msg_mono
            esito = str(d.get("statusCode") or "").upper()
            if esito == "SUCCESS":
                self.autenticato = True
                self.autenticato_una_volta = True
                self.ultimo_errore = None
            elif esito == "FAILURE":
                self.autenticato = False
                self.ultimo_errore = str(d.get("errorCode") or "FAILURE")
                logger.warning("[flusso] Betfair FAILURE %s: %s", self.ultimo_errore,
                               str(d.get("errorMessage") or "")[:160])
        elif op == "mcm":
            self.mcm += 1
            hb = d.get("heartbeatMs")
            if isinstance(hb, int) and not isinstance(hb, bool) and hb > 0:
                self.heartbeat_ms_server = hb


def _crea_stream_libreria(client: Any, unique_id: int, listener: StreamListener) -> Any:
    return client.streaming.create_stream(unique_id=unique_id, listener=listener)


# ---------------------------------------------------------------------------
# una connessione
# ---------------------------------------------------------------------------
class _Connessione:
    """Una connessione Stream API con UNA sottoscrizione di mercato, il suo thread
    di lettura e la sua ripresa. La governa ``GestoreFlussi``.

    Concorrenza: ``_lock`` protegge SOLO lo stato (mercati, versione, stream) e non
    si tiene mai durante la rete; gli invii delle sottoscrizioni sono in fila su
    ``_invio`` (mai tenuto da chi consegna i book)."""

    def __init__(self, gestore: "GestoreFlussi", numero: int, mercati: Set[str]) -> None:
        self.g = gestore
        self.numero = numero
        self.mercati: Set[str] = set(mercati)
        self.listener = ListenerFlusso(gestore._inoltra, gestore._ora)
        self.stream: Any = None
        self.chiusa = False
        self.rifiutata = False
        self.riconnessioni = 0
        self.aperta_mono = gestore._ora()
        #: ultima sottoscrizione (anche una risottoscrizione): base del watchdog dei messaggi
        self.sottoscritta_mono: Optional[float] = None
        #: quando la connessione CORRENTE si e' collegata (UNA volta per collegamento, mai
        #: toccato da ``risottoscrivi``): base della durata che azzera il backoff
        self.connessa_dal_mono: Optional[float] = None
        #: insieme PIANIFICATO dal gestore (sotto il suo lock): base dei mercati coperti
        self.piano: Set[str] = set(mercati)
        #: generazione del piano gia' applicata (una risottoscrizione vecchia non vince)
        self._generazione = 0
        self.attese: "collections.deque[float]" = collections.deque(maxlen=ATTESE_RICORDATE)
        self.id_sottoscrizione = numero * 10000
        self._forza_immagine = False
        self._versione = 0
        self._lock = threading.Lock()
        self._invio = threading.Lock()
        self._pausa = threading.Event()
        self.thread = threading.Thread(target=self._ciclo, name="flusso-%s-%d" % (
            gestore.profilo.nome, numero), daemon=True)

    def avvia(self) -> None:
        self.thread.start()

    def connessa(self) -> bool:
        s = self.stream
        return bool(s is not None and getattr(s, "running", False))

    def chiudi(self) -> None:
        self.chiusa = True
        self._pausa.set()
        self.ferma_lettura()

    def ferma_lettura(self) -> None:
        """Chiude il socket (anche dal watchdog): se la connessione non e' chiusa il
        suo ciclo la riapre con ripresa."""
        s = self.stream
        if s is not None:
            try:
                s.stop()
            except Exception as e:  # noqa: BLE001 - si chiude comunque
                logger.warning("[flusso] stop della connessione %d: %s", self.numero, e)

    def risottoscrivi(self, mercati: Set[str], generazione: Optional[int] = None) -> bool:
        """Sostituisce la sottoscrizione con ``mercati`` (insieme INTERO). True se
        mandata adesso; False se la connessione non e' su (la manda al collegamento,
        da immagine piena: i criteri della ripresa sarebbero cambiati), se un piano
        piu' nuovo (``generazione``) e' gia' stato applicato, o se l'invio e' fallito.

        Non solleva MAI per la rete (N1): un invio fallito chiude lo stream, che il
        ciclo riapre da immagine piena con l'insieme nuovo (mai una ripresa con un
        filtro diverso). Se la libreria, trovando lo stream fermato da un'altra parte,
        lo ha RICOLLEGATO dentro l'invio (``BetfairStream._send``: socket nuovo nel
        thread di chi chiama, che nessuno legge), quel socket si chiude subito."""
        if not mercati:
            raise ValueError("sottoscrizione vuota rifiutata")
        with self._lock:
            if generazione is not None:
                if generazione < self._generazione:
                    return False
                self._generazione = generazione
            self.mercati = set(mercati)
            self._versione += 1
            s = self.stream
            if s is None or not getattr(s, "running", False):
                self._forza_immagine = True
                return False
        with self._invio:                      # rete FUORI da ``_lock``
            socket_prima = getattr(s, "_socket", None)
            try:
                self._sottoscrivi(s, ripresa=False)
            except Exception as e:  # noqa: BLE001 - mai un errore di rete a chi chiama
                self._abbandona(s, "risottoscrizione fallita (%s: %s)" % (type(e).__name__, e),
                                "risottoscrizioni_fallite")
                return False
            if getattr(s, "_socket", None) is not socket_prima:
                self._abbandona(s, "la libreria ha ricollegato lo stream fermato dentro l'invio",
                                "connessioni_orfane_chiuse")
                return False
        return True

    def _abbandona(self, s: Any, motivo: str, conto: str) -> None:
        """Lo stream ``s`` non e' piu' affidabile: si chiude; il ciclo della
        connessione la riapre da immagine piena con l'insieme corrente."""
        with self._lock:
            self._forza_immagine = True
        self.g.conti[conto] += 1
        logger.warning("[flusso] connessione %d (%s): %s: chiudo e riparto da immagine piena",
                       self.numero, self.g.profilo.nome, motivo)
        try:
            s.stop()
        except Exception as e:  # noqa: BLE001 - si chiude comunque
            logger.warning("[flusso] stop della connessione %d: %s", self.numero, e)

    def _sottoscrivi(self, s: Any, ripresa: bool, versione: Optional[int] = None) -> bool:
        """Manda la sottoscrizione dell'insieme corrente. Con ``versione``: se i mercati
        sono cambiati da quando la ripresa e' stata decisa, si parte da immagine piena
        (mai ``initialClk``/``clk`` con un filtro diverso); insieme e decisione si leggono
        nello STESSO lock. Ritorna la ripresa davvero chiesta."""
        li = self.listener
        p = self.g.profilo
        with self._lock:
            ids = sorted(self.mercati)
            if ripresa and versione is not None and self._versione != versione:
                ripresa = False
        self.id_sottoscrizione = int(s.subscribe_to_markets(
            market_filter=streaming_market_filter(market_ids=ids),
            market_data_filter=filtro_dati(p),
            initial_clk=li.initial_clk if ripresa else None,
            clk=li.clk if ripresa else None,
            conflate_ms=p.conflate_ms,
            heartbeat_ms=p.heartbeat_ms,
            segmentation_enabled=True,
        ))
        self.sottoscritta_mono = self.g._ora()
        return ripresa

    def _sana(self) -> bool:
        """Rimasta su oltre ``VIVA_DOPO_S`` dal COLLEGAMENTO (azzera il backoff): le
        risottoscrizioni (auto-follow in gioco, anche ogni pochi secondi) non contano.
        Ricevere dati NON basta: immagine e chiusura a ogni giro = tempesta."""
        dal = self.connessa_dal_mono
        if dal is None:
            return False
        return self.g._ora() - dal > VIVA_DOPO_S

    def _ciclo(self) -> None:
        tentativo = 0
        while not self.chiusa and not self.g._fermo.is_set():
            try:
                self._collega_e_leggi()
                if self.chiusa or self.g._fermo.is_set():
                    break
                raise ConnectionError("lettura terminata senza chiusura")
            except Exception as e:  # noqa: BLE001 - riconnessione con backoff
                if self.chiusa or self.g._fermo.is_set():
                    break
                if self._dopo_errore(e):
                    break
                # durata dal collegamento: il watchdog e le risottoscrizioni non la toccano
                sana = self._sana()
                self.sottoscritta_mono = None
                self.connessa_dal_mono = None
                if sana:
                    tentativo = 0
                tentativo += 1
                attesa = attesa_di_backoff(tentativo, BACKOFF_MIN_S, BACKOFF_MAX_S)
                self.attese.append(attesa)
                logger.warning("[flusso] connessione %d (%s) KO (%s): nuovo tentativo fra %.1f s",
                               self.numero, self.g.profilo.nome, str(e)[:120], attesa)
                self._pausa.wait(attesa)

    def _collega_e_leggi(self) -> None:
        li = self.listener
        client = self.g._sessione.client()
        with self._lock:
            if self.chiusa:
                return
            versione = self._versione
            ripresa = bool(li.initial_clk and li.clk) and not self._forza_immagine
        s = self.g._crea_stream(client, self.id_sottoscrizione, li)
        with self._invio:                      # connessione e autenticazione: rete, senza _lock
            self.stream = s
            # la ripresa decisa prima vale solo se i mercati non sono cambiati nel frattempo
            ripresa = self._sottoscrivi(s, ripresa, versione)
            self.connessa_dal_mono = self.sottoscritta_mono
            with self._lock:
                cambiata = self._versione != versione
                self._forza_immagine = False
            if cambiata:                       # mercati cambiati mentre ci si collegava
                self._sottoscrivi(s, ripresa=False)
        if ripresa:
            self.g.conti["riprese_con_clk"] += 1
        if self.chiusa:
            s.stop()
            return
        s.start()

    def _dopo_errore(self, e: BaseException) -> bool:
        """Conta e decide; True = non riprovare (connessione rifiutata da Betfair)."""
        li = self.listener
        self.riconnessioni += 1
        codice = li.ultimo_errore or type(e).__name__
        if codice == CODICE_CLK_NON_VALIDO or li.errore_elaborazione:
            self._forza_immagine = True
            li.errore_elaborazione = False
        if codice in CODICI_RIFIUTO and not li.autenticato_una_volta:
            self.rifiutata = True           # la manutenzione chiude e mette in pausa
            return True
        if codice in CODICI_SESSIONE:
            try:
                segnala_sessione(self.g._sessione, codice)
            except Exception as ex:  # noqa: BLE001
                logger.warning("[flusso] rinnovo della sessione KO: %s", ex)
        li.autenticato = False
        return False


# ---------------------------------------------------------------------------
# il gestore
# ---------------------------------------------------------------------------
#: nomi degli eventi esposti (contratto: mercato_chiuso, flusso_muto, capacita_cambiata)
EVENTO_MERCATO_CHIUSO = "mercato_chiuso"
EVENTO_FLUSSO_MUTO = "flusso_muto"
EVENTO_CAPACITA_CAMBIATA = "capacita_cambiata"
#: il nome della richiesta di chi chiama ``imposta_mercati`` (il contratto): e' un
#: consumatore come gli altri del registro delle richieste (decisione 8, 10/10)
RICHIESTA_DIRETTA = "imposta_mercati"


class GestoreFlussi:
    """Implementa ``contratto.FlussoMercato`` per UN profilo.

    Concorrenza: ``_lock`` (piano, aperture, chiusure) non si tiene MAI durante la
    rete e non serve alla consegna dei book (che legge i consumatori da una lista
    sostituita per intero): una connessione lenta non ferma i book delle altre."""

    def __init__(self, sessione: Sessione, profilo: ProfiloFlusso, *,
                 crea_stream: Callable[[Any, int, StreamListener], Any] = _crea_stream_libreria,
                 orologio: Callable[[], float] = time.monotonic,
                 trasforma: Optional[Callable[[Any], Any]] = None,
                 cambio: Optional[Any] = None,
                 limite_mercati: int = LIMITE_BETFAIR_MERCATI) -> None:
        self.profilo = profilo
        # K1 (26/09): lo stream dei mercati e' SEMPRE in GBP, il conto in EUR. Come lo
        # scanner (``safe_strategy/stream.py`` ``drain``) ogni book si converte ALLA FONTE
        # con l'unica funzione ``valuta.converti_libro`` (cambio di processo
        # ``valuta.CAMBIO``, congelato per mercato) prima di ogni consumatore. Non si
        # spegne dal costruttore: la guardia K1 deve vedere una sola strada.
        self._cambio = cambio
        self._sessione = sessione
        self._crea_stream = crea_stream
        self._ora = orologio
        self._trasforma = trasforma
        # MAI oltre il limite Betfair per sottoscrizione (contratto: "mai > 200")
        self.per_conn = max(1, min(int(profilo.mercati_per_connessione), int(limite_mercati)))
        if self.per_conn < profilo.mercati_per_connessione:
            logger.warning("[flusso] %s: %d mercati per connessione nel profilo, limitati a %d",
                           profilo.nome, profilo.mercati_per_connessione, self.per_conn)
        self.max_conn = max(1, min(int(profilo.connessioni_max), LIMITE_BETFAIR_CONNESSIONI))
        self.riserva = max(0, int(profilo.riserva_connessioni))
        self._lock = threading.RLock()
        self._connessioni: List[_Connessione] = []
        self._numero = 0
        self._libri: Dict[str, Any] = {}
        #: i mercati dell'insieme PIANIFICATO (sostituito per intero sotto ``_lock``): la
        #: consegna scrive e consegna SOLO i loro book
        self._coperti: frozenset = frozenset()
        #: protegge solo ``_libri`` (mai tenuto durante rete o callback)
        self._libri_lock = threading.Lock()
        self._generazione = 0
        self._chiusi: Set[str] = set()
        #: (callback, filtro fisso, richiesta seguita): la lista si SOSTITUISCE per intero
        self._consumatori: List[Tuple[Callable[[Any], None], Optional[Set[str]], Optional[str]]] = []
        #: registro delle richieste (decisione 8 dell'utente, 10/10): consumatore -> i SUOI
        #: mercati. Si sottoscrive l'UNIONE: un mercato chiesto da piu' consumatori occupa UN
        #: posto su UNA connessione. Il dizionario si SOSTITUISCE per intero (sotto ``_lock``):
        #: la consegna lo legge senza lucchetti
        self._richieste: Dict[str, frozenset] = {}
        self._osservatori: List[Callable[[str, Any], None]] = []
        self._coda: "queue.Queue[Optional[List[Any]]]" = queue.Queue()
        self._fermo = threading.Event()
        self._consegna_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self._rifiuto_mono: Optional[float] = None
        self._ultima_capacita: Optional[int] = None
        self.ultimo_rifiuto: Optional[str] = None
        self.motivo_limite: Optional[str] = None
        self.ultimo_evento: Optional[str] = None
        self.conti: Dict[str, int] = {"aperture": 0, "chiusure": 0, "rifiuti": 0, "muti": 0,
                                      "risottoscrizioni": 0, "riprese_con_clk": 0,
                                      "book": 0, "errori_consumatori": 0, "riavvii_watchdog": 0,
                                      "libri_potati": 0, "errori_osservatori": 0,
                                      "book_fuori_insieme": 0, "risottoscrizioni_fallite": 0,
                                      "connessioni_orfane_chiuse": 0}

    # ------------------------------------------------------------ contratto
    def imposta_mercati(self, mercati: Iterable[str]) -> Set[str]:
        """Porta le connessioni a ``mercati``. Ritorna i mercati voluti che NON
        sono su nessuna connessione (capacita' o budget): il chiamante decide chi
        lasciare fuori (l'auto-follow di oggi pianifica sulla ``capacita()``).
        Il piano si fa sotto ``_lock``; le risottoscrizioni (rete) DOPO.

        E' la richiesta del consumatore ``RICHIESTA_DIRETTA``: senza altre richieste nel
        registro il risultato e' IDENTICO a prima (si sottoscrive esattamente
        ``mercati``); con altre richieste si sottoscrive l'unione (``richiedi_mercati``)."""
        voluti = {str(m) for m in mercati if m}
        if not voluti:
            raise ValueError("sottoscrizione vuota rifiutata")
        return self.richiedi_mercati(RICHIESTA_DIRETTA, voluti)

    def richiedi_mercati(self, chi: str, mercati: Iterable[str]) -> Set[str]:
        """Il consumatore ``chi`` (bot, ladder, scanner, ...) vuole ``mercati``: e' il
        SUO insieme intero e sostituisce la sua richiesta precedente (vuoto = rilascia).
        Il gestore sottoscrive l'UNIONE delle richieste di tutti i consumatori: stessi
        mercati chiesti da tre consumatori = le connessioni di UNO (decisione 8 e 13
        dell'utente, 10/10/2026: un gestore per tutta l'app, mai connessioni doppie).
        Ritorna i mercati di ``chi`` rimasti fuori (capacita' o budget).

        Concorrenza: il registro si aggiorna e l'unione si pianifica nello STESSO
        ``_lock`` (``_applica_richieste``): l'ultimo piano vede sempre tutte le richieste
        arrivate prima di lui; la rete resta FUORI dal lucchetto e una risottoscrizione
        vecchia non vince su una nuova (generazione di ``_Connessione.risottoscrivi``)."""
        nome = str(chi)
        if not nome:
            raise ValueError("richiesta senza nome del consumatore")
        voluti = frozenset(str(m) for m in mercati if m)
        with self._lock:
            nuove = dict(self._richieste)
            if voluti:
                nuove[nome] = voluti
            else:
                nuove.pop(nome, None)
            self._richieste = nuove
        coperti = self._applica_richieste()
        return set(voluti - coperti)

    def rilascia_mercati(self, chi: str) -> Set[str]:
        """Il consumatore ``chi`` non vuole piu' nulla: i mercati che nessun altro
        chiede escono dalle connessioni; senza richieste le connessioni si chiudono."""
        return self.richiedi_mercati(chi, ())

    def richieste(self) -> Dict[str, frozenset]:
        """Il registro delle richieste (copia): consumatore -> i suoi mercati."""
        return dict(self._richieste)

    def _applica_richieste(self) -> frozenset:
        """Porta le connessioni all'UNIONE delle richieste. Piano sotto ``_lock`` (con
        l'unione letta li', non prima), risottoscrizioni dopo. Unione vuota = nessuna
        connessione (mai una sottoscrizione vuota, che vorrebbe dire tutto l'exchange).
        Ritorna i mercati coperti dopo il piano."""
        self.avvia()
        da_mandare: List[Tuple[_Connessione, Set[str]]] = []
        with self._lock:
            voluti = frozenset().union(*self._richieste.values()) if self._richieste else frozenset()
            self._generazione += 1
            generazione = self._generazione
            if not voluti:
                for c in self._vive():
                    self._chiudi(c, "nessun consumatore chiede mercati")
                return self._coperti
            self.manutenzione()
            conn = self._vive()
            attuali = [set(c.piano) for c in conn]
            massimo = self.massimo_adesso()
            piano = piano_connessioni(attuali, voluti, self.per_conn, max(massimo, len(conn)))
            for i, (c, bersaglio) in enumerate(zip(conn, piano.bersagli)):
                if bersaglio == attuali[i]:
                    continue
                if not bersaglio and i > 0:
                    self._chiudi(c, "nessun mercato da seguire")
                    continue
                c.piano = set(bersaglio)
                da_mandare.append((c, bersaglio))
                self.conti["risottoscrizioni"] += 1
            for blocco in piano.nuovi:
                self._apri(blocco)
            # PRIMA della rete: i book dei mercati tolti smettono subito di entrare
            self._aggiorna_coperti()
            coperti = self._coperti
        for c, bersaglio in da_mandare:
            c.risottoscrivi(bersaglio, generazione)
        return coperti

    def aggiungi_consumatore(self, cb: Callable[[Any], None], *,
                             mercati: Optional[Set[str]] = None,
                             richiesta: Optional[str] = None) -> None:
        """``cb(book)`` nel thread di consegna. ``mercati`` = filtro fisso (None = tutti);
        ``richiesta`` = il consumatore riceve i book dei mercati della richiesta con quel
        nome, seguendola quando cambia (estensione additiva del contratto). Non tutti e due."""
        if mercati is not None and richiesta is not None:
            raise ValueError("filtro fisso e richiesta insieme: scegliere uno dei due")
        filtro = {str(m) for m in mercati} if mercati is not None else None
        segui = str(richiesta) if richiesta is not None else None
        with self._lock:
            self._consumatori = list(self._consumatori) + [(cb, filtro, segui)]

    def aggiungi_osservatore(self, cb: Callable[[str, Any], None]) -> None:
        """``cb(evento, dato)`` per gli eventi del contratto: ``mercato_chiuso``
        (market_id), ``flusso_muto`` (numero della connessione), ``capacita_cambiata``
        (mercati sottoscrivibili). Estensione additiva."""
        with self._lock:
            self._osservatori = list(self._osservatori) + [cb]

    def book(self, market_id: str) -> Any:
        with self._libri_lock:
            return self._libri.get(str(market_id))

    def stato_flusso(self, market_id: str) -> StatoFlusso:
        mid = str(market_id)
        for c in self._vive():
            if mid in c.mercati:
                return "vivo" if (self._verdetto(c)["vivo"] and mid in c.listener.serviti) else "muto"
        return "assente"

    def stato(self) -> Mapping[str, object]:
        ora = self._ora()

        def eta(t: float) -> Optional[float]:
            return round(ora - t, 1) if t else None
        righe = []
        for i, c in enumerate(self._vive()):
            li = c.listener
            v = self._verdetto(c)
            righe.append({
                "i": i, "stream_id": c.id_sottoscrizione, "mercati": len(c.mercati),
                "connesso": c.connessa(), "eta_msg_s": eta(li.ultimo_msg_mono),
                "eta_dati_s": eta(li.ultimo_dato_mono), "riconnessioni": c.riconnessioni,
                "errore": li.ultimo_errore, "vivo": v["vivo"], "motivo": v["motivo"],
                "initial_clk": li.initial_clk, "clk": li.clk,
                "ultime_attese_s": list(c.attese),
            })
        massimo = self.massimo_adesso()
        return {
            "profilo": self.profilo.nome,
            "connessioni_di_mercato": len(righe),
            "connessioni_massime": self.max_conn,
            "connessioni_concesse_adesso": massimo,
            "mercati_per_connessione": self.per_conn,
            "capacita_mercati": massimo * self.per_conn,
            "riserva_connessioni": self.riserva,
            "connessioni_disponibili_betfair": self._disponibili(),
            "in_pausa_dopo_rifiuto": self._in_pausa(),
            "motivo_limite": self.motivo_limite,
            "ultimo_rifiuto": self.ultimo_rifiuto,
            "ultimo_evento": self.ultimo_evento,
            "battito_eta_s": min((r["eta_msg_s"] for r in righe if r["eta_msg_s"] is not None),
                                 default=None),
            "soglia_watchdog_s": max((self._soglia_s(c) for c in self._vive()), default=None),
            "richieste": {chi: len(m) for chi, m in sorted(self._richieste.items())},
            "mercati_richiesti_somma": sum(len(m) for m in self._richieste.values()),
            "mercati_unione": len(frozenset().union(*self._richieste.values())) if self._richieste else 0,
            "mercati_chiusi": sorted(self._chiusi)[:50],
            "conti": dict(self.conti),
            "frammenti": righe,
        }

    # ------------------------------------------------------------ budget e salute
    def capacita(self) -> int:
        """Mercati sottoscrivibili adesso."""
        return self.massimo_adesso() * self.per_conn

    def massimo_adesso(self) -> int:
        n, self.motivo_limite = connessioni_concesse(
            len(self._vive()), self.max_conn, self.riserva, self.per_conn,
            self._disponibili(), self._in_pausa(), self.ultimo_rifiuto,
            nome_env=_NOMI_ENV.get(self.profilo.nome, "profilo %s" % self.profilo.nome))
        if self._ultima_capacita is not None and n != self._ultima_capacita:
            self._evento(EVENTO_CAPACITA_CAMBIATA, n * self.per_conn)
        self._ultima_capacita = n
        return n

    def manutenzione(self) -> Set[str]:
        """Chiude le connessioni rifiutate e quelle mute oltre ``MUTO_S`` (con
        un'altra viva). Ritorna i mercati che erano su di loro."""
        persi: Set[str] = set()
        with self._lock:
            ora = self._ora()
            conn = self._vive()
            for c in conn:
                li = c.listener
                mai = not li.autenticato_una_volta
                altri_vivi = any(self._viva_da_poco(x, ora) for x in conn if x is not c)
                if mai and (c.rifiutata or (li.ultimo_errore or "") in CODICI_RIFIUTO
                            or (altri_vivi and ora - c.aperta_mono > ATTESA_APERTURA_S)):
                    self._rifiuto_mono = ora
                    self.conti["rifiuti"] += 1
                    self.ultimo_rifiuto = li.ultimo_errore or (
                        "nessuna autenticazione in %.0f s" % ATTESA_APERTURA_S)
                    persi |= self._chiudi(c, "connessione rifiutata: " + self.ultimo_rifiuto)
                    continue
                ultimo = max(li.ultimo_msg_mono, c.aperta_mono)
                if not mai and altri_vivi and len(conn) > 1 and ora - ultimo > MUTO_S:
                    self.conti["muti"] += 1
                    persi |= self._chiudi(c, "muta da %.0f s (nessun messaggio, neanche "
                                          "heartbeat)" % (ora - ultimo))
        return persi

    def veglia(self) -> List[int]:
        """Un giro del watchdog: ogni connessione SU e sottoscritta senza NESSUN
        messaggio (neanche heartbeat) oltre ``BATTITI_WATCHDOG`` heartbeat si chiude
        al socket; il suo ciclo la riapre con ripresa (``initialClk``/``clk``).
        Ritorna i numeri delle connessioni riavviate."""
        riavviate: List[int] = []
        ora = self._ora()
        for c in self._vive():
            dal = c.sottoscritta_mono
            if dal is None or not c.connessa():
                continue
            muto = ora - max(c.listener.ultimo_msg_mono or 0.0, dal)
            if muto > self._soglia_s(c):
                self.conti["riavvii_watchdog"] += 1
                logger.warning("[flusso] %s: connessione %d MUTA da %.1f s (soglia %.1f s): "
                               "chiudo e riprendo", self.profilo.nome, c.numero, muto,
                               self._soglia_s(c))
                # A3-2: si azzera SOLO il riferimento dei messaggi; la durata del collegamento
                # (``connessa_dal_mono``) resta: il ciclo la valuta alla caduta
                c.sottoscritta_mono = None
                c.ferma_lettura()
                riavviate.append(c.numero)
                self._evento(EVENTO_FLUSSO_MUTO, c.numero)
        return riavviate

    # ------------------------------------------------------------ vita
    def avvia(self) -> None:
        """Consegna dei book e watchdog (le connessioni nascono con i mercati)."""
        with self._lock:
            if self._consegna_thread is not None:
                return
            self._fermo.clear()
            self._consegna_thread = threading.Thread(
                target=self._consegna, name="flusso-%s-consegna" % self.profilo.nome, daemon=True)
            self._consegna_thread.start()
            self._watchdog_thread = threading.Thread(
                target=self._ciclo_watchdog, name="flusso-%s-watchdog" % self.profilo.nome,
                daemon=True)
            self._watchdog_thread.start()

    def ferma(self, attesa_s: float = 5.0) -> None:
        """Chiude tutte le connessioni: nessuna riconnessione dopo."""
        self._fermo.set()
        with self._lock:
            conn = list(self._connessioni)
            self._connessioni = []
        fine = time.monotonic() + attesa_s
        for c in conn:
            while True:
                c.chiudi()
                if not c.thread.is_alive() or time.monotonic() >= fine:
                    break
                c.thread.join(timeout=0.1)
        self._coda.put(None)
        for t in (self._consegna_thread, self._watchdog_thread):
            if t is not None:
                t.join(timeout=max(0.1, fine - time.monotonic()))
        self._consegna_thread = None
        self._watchdog_thread = None

    # ------------------------------------------------------------ interni
    def _vive(self) -> List[_Connessione]:
        return [c for c in self._connessioni if not c.chiusa]

    def _in_pausa(self) -> bool:
        return self._rifiuto_mono is not None and self._ora() - self._rifiuto_mono < PAUSA_RIFIUTO_S

    def _disponibili(self) -> Optional[int]:
        """L'ultimo ``connectionsAvailable`` letto da una delle connessioni."""
        return self.disponibili_con_istante()[0]

    def disponibili_con_istante(self) -> Tuple[Optional[int], Optional[float]]:
        """(ultimo ``connectionsAvailable`` letto, istante della lettura sull'orologio del
        gestore): per lo stream ordini, che confronta col SUO valore (vince il piu' recente;
        stesso orologio monotono)."""
        migliore: Optional[int] = None
        quando: Optional[float] = None
        for c in self._vive():
            li = c.listener
            if li.connessioni_disponibili is not None and (
                    quando is None or li.connessioni_lette_mono > quando):
                migliore, quando = li.connessioni_disponibili, li.connessioni_lette_mono
        return migliore, quando

    def _viva_da_poco(self, c: _Connessione, ora: float) -> bool:
        u = c.listener.ultimo_msg_mono
        return u > 0.0 and ora - u <= MUTO_S

    def _soglia_s(self, c: _Connessione) -> float:
        hb = c.listener.heartbeat_ms_server or self.profilo.heartbeat_ms or _SM.HEARTBEAT_MS_RICHIESTO
        return BATTITI_WATCHDOG * float(hb) / 1000.0

    def _verdetto(self, c: _Connessione) -> Dict[str, Any]:
        li = c.listener
        latente = li.status is not None and li.status != 200
        return _SM.stato_da_battiti(
            li.ultimo_msg_mono * 1000.0 if li.ultimo_msg_mono else None, None,
            adesso_ms=self._ora() * 1000.0, soglia_s=self._soglia_s(c),
            mercati=sorted(c.mercati) or ["-"], latente=latente)

    def _apri(self, mercati: Set[str]) -> _Connessione:
        self._numero += 1
        c = _Connessione(self, self._numero, mercati)
        self._connessioni = list(self._connessioni) + [c]
        self.conti["aperture"] += 1
        self.ultimo_evento = "aperta connessione %d (%d mercati)" % (c.numero, len(mercati))
        logger.warning("[flusso] %s: APERTA connessione %d con %d mercati",
                       self.profilo.nome, c.numero, len(mercati))
        self._aggiorna_coperti()            # i suoi book entrano dal primo messaggio
        c.avvia()
        return c

    def _chiudi(self, c: _Connessione, motivo: str) -> Set[str]:
        persi = set(c.mercati)
        c.chiudi()
        self._connessioni = [x for x in self._connessioni if x is not c]
        self._aggiorna_coperti()
        self.conti["chiusure"] += 1
        self.ultimo_evento = "chiusa connessione %d: %s" % (c.numero, motivo)
        logger.warning("[flusso] %s: CHIUSA connessione %d (%d mercati): %s",
                       self.profilo.nome, c.numero, len(persi), motivo)
        return persi

    def _aggiorna_coperti(self) -> None:
        """Sotto ``_lock``: l'insieme pianificato delle connessioni vive diventa quello
        coperto; i book dei mercati fuori escono da ``book()``."""
        vive = self._vive()
        self._coperti = frozenset().union(*(c.piano for c in vive)) if vive else frozenset()
        self._pota_libri(self._coperti)

    def _pota_libri(self, coperti: Any) -> None:
        """I book dei mercati non piu' sottoscritti escono da ``book()``."""
        with self._libri_lock:
            via = [m for m in list(self._libri) if m not in coperti]
            for m in via:
                self._libri.pop(m, None)
        self.conti["libri_potati"] += len(via)

    def _evento(self, nome: str, dato: Any) -> None:
        for cb in self._osservatori:
            try:
                cb(nome, dato)
            except Exception as e:  # noqa: BLE001 - un osservatore non ferma il flusso
                self.conti["errori_osservatori"] += 1
                logger.error("[flusso] osservatore %r KO su %s: %s", getattr(cb, "__name__", cb), nome, e)

    def _ciclo_watchdog(self) -> None:
        while not self._fermo.wait(self._passo_watchdog()):
            try:
                self.veglia()
            except Exception as e:  # noqa: BLE001 - il watchdog non muore
                logger.warning("[flusso] giro del watchdog KO: %s", e)

    def _passo_watchdog(self) -> float:
        soglie = [self._soglia_s(c) for c in self._vive()]
        return max(0.05, min(1.0, min(soglie) / 4.0)) if soglie else 1.0

    def _inoltra(self, libri: List[Any]) -> None:
        """Nel thread del socket: accoda i book del messaggio (consegna altrove)."""
        if libri:
            self._coda.put(libri)

    def _consegna(self) -> None:
        while True:
            libri = self._coda.get()
            if libri is None:
                return
            consumatori = self._consumatori      # lista sostituita per intero: nessun lock
            richieste = self._richieste          # idem
            for b in libri:
                try:
                    b = _valuta.converti_libro(b, self._cambio or _valuta.CAMBIO)
                except Exception as e:  # noqa: BLE001 - un book in GBP non si consegna mai
                    logger.error("[flusso] conversione GBP->EUR KO su %s: book NON consegnato (%s)",
                                 getattr(b, "market_id", "?"), e)
                    continue
                if self._trasforma is not None:
                    try:
                        b = self._trasforma(b)
                    except Exception as e:  # noqa: BLE001 - book non consegnato, si dice
                        logger.error("[flusso] trasformazione KO su %s: %s",
                                     getattr(b, "market_id", "?"), e)
                        continue
                mid = str(b.market_id)
                with self._libri_lock:
                    if mid not in self._coperti:     # mercato tolto: book in volo, stantio
                        self.conti["book_fuori_insieme"] += 1
                        continue
                    self._libri[mid] = b
                self.conti["book"] += 1
                if getattr(b, "status", None) == "CLOSED" and mid not in self._chiusi:
                    self._chiusi.add(mid)
                    self._evento(EVENTO_MERCATO_CHIUSO, mid)
                for cb, mercati, segui in consumatori:
                    if mercati is not None and mid not in mercati:
                        continue
                    if segui is not None and mid not in richieste.get(segui, ()):
                        continue
                    try:
                        cb(b)
                    except Exception as e:  # noqa: BLE001 - un consumatore non ferma gli altri
                        self.conti["errori_consumatori"] += 1
                        logger.error("[flusso] consumatore %r KO su %s: %s",
                                     getattr(cb, "__name__", cb), mid, e)
