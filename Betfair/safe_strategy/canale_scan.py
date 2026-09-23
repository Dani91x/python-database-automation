"""canale_scan.py - F4: il CLIENT del canale dello scanner, lato bot Safe.

Che cosa risolve. Fra "lo scanner ha il prezzo" e "il bot ce l'ha in mano" oggi
passano 2,0-2,9 s: 2 s di poll (``poll_interval_s``) piu' 92-307 ms di
PostgREST (misura del 17/09). Lo scanner, da F1, pubblica la STESSA riga anche
sul canale locale 47336 (``scan_calcio`` / ``scan_tennis`` / ``scanner_stato``)
e nessuno la legge. Questo modulo e' il lettore.

LE REGOLE, tutte inchiodate da un test
(``Betfair/safe_strategy/tests/test_canale_scan_f4_2026_09_18.py``):

1. **Il database resta il registro e la LISTA.** Quali partite esistono lo dice
   solo il database (``fetch_scan_rows`` -> ``purge_orphans``). Il canale porta
   la FRESCHEZZA di una riga che il database sta gia' elencando, e non puo'
   AGGIUNGERE una partita: ``fondi`` itera sugli ``event_id`` del database.
2. **A parita', e nel dubbio, vince il database.** La riga del canale vince
   solo se il suo ``updated_at`` e' STRETTAMENTE piu' recente **e** il suo
   ``payload.odds_ts_ms`` e' un numero: una riga senza l'istante del prezzo non
   sposta mai una riga del libro mastro (invariante B11).
3. **Nessun privilegio.** La riga fusa passa da ``_row_is_fresh`` e da tutte le
   guardie di oggi senza sapere da dove viene: se e' stantia viene scartata
   come qualunque altra.
4. **Il client non solleva MAI verso il bot.** Canale giu', porta chiusa,
   ``websockets`` assente, messaggio storto: il bot lavora identico a oggi e
   torna al poll del database. Le eccezioni si contano, il silenzio totale non
   e' ammesso.
5. **Interruttori per processo, via ``.env``, DEFAULT SPENTO.** Accesi solo se
   qualcuno li scrive davvero (``1``/``true``/``si``/``yes``): vuoto, assente o
   qualunque altra scritta vale spento. E' la regola di ``canale_bot.acceso``,
   importata da li' e non riscritta (difetto D2 di F1).

MODULO PURO: nessun import di flumine, betfairlightweight, supabase o rete a
livello di modulo. ``websockets`` entra solo dentro la sessione del client, in
un thread daemon. Test di contratto: ``test_canale_scan_e_un_modulo_puro``
(sottoprocesso VERO).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Dict, List, Mapping, Optional

from Betfair.safe_strategy.exits import FEED_FRESH_S, parse_ts
from Betfair.stream.canale_bot import VALORI_ACCESI, acceso

logger = logging.getLogger("safe.bot.canale_scan")

__all__ = [
    "VALORI_ACCESI", "acceso",
    "ENV_LEGGE_CANALE", "ENV_SVEGLIA", "ENV_PORTA", "PORTA_SCAN",
    "TOPIC_SCAN", "TOPIC_SCANNER_STATO", "TOPIC_SCAN_NOMI",
    "MSG_SVEGLIA", "MOTIVI_SVEGLIA", "MAX_RIGHE", "MAX_ETA_CONTESTO_S",
    "CacheScan", "ClientScan", "piu_recente", "fondi", "installa_sveglia",
    "porta_scan",
]

# --------------------------------------------------------------- interruttori
#: Il bot Safe legge le righe di scan dal canale invece che dal solo database.
ENV_LEGGE_CANALE = "SAFE_BOT_LEGGE_CANALE"
#: Il canale del bot Safe (47335) accetta la SOLA sveglia dalla UI.
ENV_SVEGLIA = "SAFE_BOT_SVEGLIA_CANALE"
#: La porta del canale dello scanner. Stesso nome che usa il produttore
#: (``service.py::_PORTA_CANALE_ENV``): un solo nome, due lati.
ENV_PORTA = "SAFE_SCAN_WS_PORT"
PORTA_SCAN = 47336

#: I nomi dei topic. Il produttore li tiene in ``service.py`` (_TOPIC_SCAN /
#: _TOPIC_SCANNER_STATO); qui sono gli stessi, e un test di contratto lo
#: verifica invece di fidarsi (difetto 33 del catalogo: una stringa scritta due
#: volte diverge sempre, prima o poi). Calcio e tennis restano SEPARATI
#: (invariante B12).
TOPIC_SCAN: Mapping[str, str] = MappingProxyType({
    "calcio": "scan_calcio",
    "tennis": "scan_tennis",
})
TOPIC_SCANNER_STATO = "scanner_stato"
TOPIC_SCAN_NOMI = frozenset(TOPIC_SCAN.values())

#: Tetto della memoria del client: oltre questo numero di eventi si butta il
#: piu' vecchio per ARRIVO. Lo scanner segue qualche decina di partite; 2000 e'
#: due ordini di grandezza sopra, ed esiste perche' una cache senza tetto in un
#: processo che vive giorni e' un guasto che arriva sempre.
MAX_RIGHE = 2000

#: Il messaggio di SVEGLIA, l'unico che il canale del bot accetta dalla UI.
#: Non porta e non puo' portare NESSUN parametro d'ordine: dice solo "c'e'
#: qualcosa da leggere sul database". Il comando vero resta la riga sul DB.
MSG_SVEGLIA = "sveglia"
MOTIVI_SVEGLIA = frozenset({"approvazione", "comando"})

#: Eta' massima del contesto di rischio per un giro svegliato fuori banda
#: (decisione dell'utente, 18/09: "5 secondi AL MASSIMO"). Dichiarata qui
#: perche' e' il contratto della corsia calda; il consumatore non esiste ancora
#: (vedi il referto di F4, "cosa NON ho fatto").
MAX_ETA_CONTESTO_S = 5.0


def porta_scan() -> int:
    """La porta del canale dello scanner, dall'ambiente o quella di serie."""
    grezza = (os.getenv(ENV_PORTA) or "").strip()
    if not grezza:
        return PORTA_SCAN
    try:
        return int(grezza)
    except ValueError:
        logger.info("[scan-ws] %s non e' un numero (%r): uso %d",
                    ENV_PORTA, grezza[:20], PORTA_SCAN)
        return PORTA_SCAN


# ------------------------------------------------------------------- la cache
class CacheScan:
    """Le righe di scan arrivate dal canale, l'ULTIMA per ``event_id``.

    IL CONTRATTO, che e' il punto piu' importante del percorso "al ms":

        il DATABASE resta la verita' del LIBRO MASTRO - posizioni, richieste,
        control, riserve. Il canale e' la verita' della SOLA QUOTA.

    Due fonti per un *prezzo* si possono avere (vince la piu' recente, e ogni
    riga porta il proprio istante). Due fonti per una *posizione* no, mai.
    """

    def __init__(self, max_righe: int = MAX_RIGHE) -> None:
        self.max_righe = int(max_righe)
        self._righe: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.ricevute = 0
        self.scartate = 0
        self.buttate = 0
        self.ultimo_mono = 0.0

    def aggiorna(self, riga: Any) -> bool:
        """Una riga dal canale. ``False`` se non entra, e non e' un guasto.

        Si accetta SOLO cio' che ha la forma della riga vera (``event_id`` +
        ``payload`` dizionario + ``updated_at`` leggibile): una riga a meta' non
        entra in memoria travestita da buona (catalogo par.7.27). E non si
        sostituisce mai una riga con una PIU' VECCHIA: i messaggi arrivano in
        ordine, ma "arrivano in ordine" non e' una cosa che si assume.
        """
        if not isinstance(riga, dict):
            self._conta_scarto()
            return False
        eid = riga.get("event_id")
        payload = riga.get("payload")
        if not eid or not isinstance(payload, dict):
            self._conta_scarto()
            return False
        ts = parse_ts(riga.get("updated_at"))
        if ts is None:
            # senza istante non si sa se e' piu' nuova o piu' vecchia: non entra
            self._conta_scarto()
            return False
        chiave = str(eid)
        with self._lock:
            vecchia = self._righe.get(chiave)
            if vecchia is not None:
                ts_vecchia = parse_ts(vecchia.get("updated_at"))
                if ts_vecchia is not None and ts < ts_vecchia:
                    self.scartate += 1
                    return False
            else:
                self._butta_il_piu_vecchio()
            self._righe[chiave] = dict(riga)
            self.ricevute += 1
            self.ultimo_mono = time.monotonic()
        return True

    def _conta_scarto(self) -> None:
        with self._lock:
            self.scartate += 1

    def _butta_il_piu_vecchio(self) -> None:
        """Tetto della memoria. SOLO con il lock preso."""
        while len(self._righe) >= self.max_righe:
            try:
                piu_vecchia = next(iter(self._righe))
            except StopIteration:  # pragma: no cover - dizionario vuoto
                return
            self._righe.pop(piu_vecchia, None)
            self.buttate += 1

    def riga(self, event_id: Any) -> Optional[Dict[str, Any]]:
        with self._lock:
            riga = self._righe.get(str(event_id))
        return dict(riga) if riga else None

    def righe_recenti(self, max_eta_s: float = FEED_FRESH_S,
                      ora: Optional[float] = None) -> Dict[str, Dict[str, Any]]:
        """Le righe la cui eta' e' ``<= max_eta_s``, per ``event_id``.

        La soglia di serie e' ``exits.FEED_FRESH_S`` (20 s), la STESSA che il
        bot usa gia' in ``_row_is_fresh``: qui non si inventa nessun numero
        nuovo. Le righe piu' vecchie restano in memoria (il database le
        riallineera') ma non escono di qui.
        """
        adesso = float(ora) if ora is not None else time.time()
        limite = float(max_eta_s)
        with self._lock:
            tutte = list(self._righe.items())
        fuori: Dict[str, Dict[str, Any]] = {}
        for eid, riga in tutte:
            ts = parse_ts(riga.get("updated_at"))
            if ts is None or adesso - ts > limite:
                continue
            fuori[eid] = dict(riga)
        return fuori

    def dimentica(self, event_ids: Any) -> None:
        with self._lock:
            for eid in event_ids or ():
                self._righe.pop(str(eid), None)

    def azzera(self) -> None:
        with self._lock:
            self._righe.clear()
            self.ricevute = 0
            self.scartate = 0
            self.buttate = 0
            self.ultimo_mono = 0.0

    def eta_s(self) -> Optional[float]:
        """Da quanto non arriva NIENTE dal canale. ``None`` = non e' mai
        arrivato niente, che non e' "zero secondi fa"."""
        with self._lock:
            ultimo = self.ultimo_mono
        return (time.monotonic() - ultimo) if ultimo else None

    def stato(self) -> Dict[str, Any]:
        eta = self.eta_s()
        with self._lock:
            return {"righe": len(self._righe), "ricevute": self.ricevute,
                    "scartate": self.scartate, "buttate": self.buttate,
                    "eta_s": round(eta, 2) if eta is not None else None}


# ------------------------------------------------------------------ la fusione
def piu_recente(dal_db: Optional[Dict[str, Any]],
                dal_canale: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Fra la riga del database e quella del canale, la piu' RECENTE.

    Il confronto e' su ``updated_at`` (ordine dell'utente, 18/09). A parita' -
    e in ogni dubbio - vince il DATABASE, che e' il libro mastro.

    Due condizioni, entrambe necessarie, perche' la riga del canale vinca:
      1. il suo ``updated_at`` e' STRETTAMENTE piu' recente di quello del DB;
      2. il suo ``payload.odds_ts_ms`` e' un numero vero.
    La seconda e' l'invariante B11 scritta qui: una riga che non dichiara
    l'istante del proprio prezzo non entra in decisione, e quindi non puo'
    nemmeno spostare quella che c'e'.
    """
    if not isinstance(dal_canale, dict):
        return dal_db
    if not isinstance(dal_db, dict):
        # nessuna riga sul database: il canale NON puo' aggiungere una partita
        # (regola 1 del modulo). Lo decide ``fondi``; qui si resta coerenti.
        return None
    if not _numero(_odds_ts_ms(dal_canale)):
        return dal_db
    a = parse_ts(dal_db.get("updated_at"))
    b = parse_ts(dal_canale.get("updated_at"))
    if a is None or b is None:
        return dal_db
    if b > a:
        return dal_canale
    return dal_db


def _odds_ts_ms(riga: Dict[str, Any]) -> Any:
    payload = riga.get("payload")
    return payload.get("odds_ts_ms") if isinstance(payload, dict) else None


def _numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fondi(righe_db: Any, fresche: Optional[Mapping[str, Dict[str, Any]]]
          ) -> tuple[List[Dict[str, Any]], int]:
    """Le righe del ciclo: quelle del database, con quelle del canale al posto
    delle piu' vecchie. Torna ``(righe, quante_dal_canale)``.

    Si itera sul DATABASE, sempre: il canale non aggiunge nessuna partita e non
    ne toglie nessuna. L'ordine delle righe non cambia.
    """
    righe = [r for r in (righe_db or []) if isinstance(r, dict)]
    if not fresche:
        return righe, 0
    fuori: List[Dict[str, Any]] = []
    dal_canale = 0
    for riga in righe:
        eid = riga.get("event_id")
        if not eid:
            fuori.append(riga)
            continue
        candidata = fresche.get(str(eid))
        scelta = piu_recente(riga, candidata)
        if scelta is candidata and candidata is not None:
            dal_canale += 1
            fuori.append(candidata)
        else:
            fuori.append(riga)
    return fuori, dal_canale


# ------------------------------------------------------------------- il client
class ClientScan:
    """Client WebSocket del canale dello scanner, in un thread daemon.

    Non porta NIENTE del libro mastro: solo righe di FEED. Se cade, chi lo usa
    torna al poll del database senza una riga di differenza - ed e' per questo
    che puo' essere best-effort senza rischi.
    """

    #: attesa crescente fra due tentativi di aggancio
    ATTESE = (0.5, 1.0, 2.0, 5.0)

    def __init__(self, porta: int, cache: CacheScan, *,
                 host: str = "127.0.0.1",
                 evento: Optional[threading.Event] = None,
                 interessa: Optional[Callable[[str], bool]] = None) -> None:
        self.porta = int(porta)
        self.host = host
        self.cache = cache
        #: la sveglia. ``interessa`` decide QUALI righe la alzano: senza
        #: ``interessa`` non la alza NESSUNA riga (default prudente: chi non ha
        #: collegato la corsia calda non se la ritrova accesa per sbaglio).
        self.evento = evento
        self.interessa = interessa
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.riagganci = 0
        self.collegato = False
        self.errori = 0
        self.ultimo_errore: Optional[str] = None
        self.svegliate = 0
        self._detto_niente_websockets = False
        #: PUNTEGGI_CANALE (23/09): istante monotono dell'ultimo battito dello
        #: scanner (topic ``scanner_stato``) arrivato su questo client. 0.0 =
        #: mai arrivato. Serve ai lettori dei punteggi per sapere se lo
        #: scanner e' VIVO senza rileggere ``safe_strategy_status`` dal DB.
        #: Il battito NON e' una riga: ``incassa`` continua a tornare False.
        self.stato_mono = 0.0

    # ------------------------------------------------------------- ciclo vita
    def avvia(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._gira, daemon=True,
                                        name="safe-scan-ws-client")
        self._thread.start()

    def ferma(self) -> None:
        self._stop.set()

    def stato(self) -> Dict[str, Any]:
        return {"collegato": self.collegato, "riagganci": self.riagganci,
                "errori": self.errori, "ultimo_errore": self.ultimo_errore,
                "svegliate": self.svegliate, "porta": self.porta,
                "cache": self.cache.stato()}

    # ------------------------------------------------------------------ thread
    def _gira(self) -> None:
        i = 0
        while not self._stop.is_set():
            try:
                self._sessione()
                i = 0
            except Exception as ex:  # noqa: BLE001 - il bot vive senza canale
                self.errori += 1
                self.ultimo_errore = str(ex)[:200]
                self._log_aggancio_ko(ex)
            finally:
                self.collegato = False
            if self._stop.is_set():
                break
            self.riagganci += 1
            # ``Event.wait`` invece di ``sleep``: ``ferma()`` non deve aspettare
            # cinque secondi per essere ubbidita.
            self._stop.wait(self.ATTESE[min(i, len(self.ATTESE) - 1)])
            i += 1

    def _log_aggancio_ko(self, ex: Exception) -> None:
        """Una riga a INFO la PRIMA volta, poi solo debug.

        ``websockets`` assente o porta chiusa e' la condizione NORMALE con
        l'interruttore appena acceso e lo scanner non ancora riavviato: non e'
        un allarme, ma dirlo una volta si deve.
        """
        if not self._detto_niente_websockets:
            self._detto_niente_websockets = True
            logger.info("[scan-ws] canale dello scanner non disponibile su "
                        "%s:%d (%s): il bot continua a leggere dal database.",
                        self.host, self.porta, str(ex)[:160])
            return
        logger.debug("[scan-ws] aggancio KO (%s): riprovo.", str(ex)[:160])

    def _sessione(self) -> None:
        from websockets.sync.client import connect

        with connect("ws://%s:%d" % (self.host, self.porta), open_timeout=5) as ws:
            self.collegato = True
            self._detto_niente_websockets = False
            logger.info("[scan-ws] agganciato al canale dello scanner su %s:%d",
                        self.host, self.porta)
            for grezzo in ws:
                if self._stop.is_set():
                    return
                self.incassa(grezzo)

    def eta_stato_s(self) -> Optional[float]:
        """Da quanti secondi non arriva il battito dello scanner su QUESTO
        client. ``None`` = mai arrivato (che non e' "zero secondi fa") oppure
        client non collegato adesso: un battito vecchio su un socket caduto
        non dice niente dello scanner di adesso."""
        ultimo = self.stato_mono
        if not ultimo or not self.collegato:
            return None
        return max(0.0, time.monotonic() - ultimo)

    # ------------------------------------------------------------- un messaggio
    def incassa(self, grezzo: Any) -> bool:
        """Un messaggio del canale. NON SOLLEVA MAI. ``True`` se e' entrato.

        Separata dalla sessione apposta: e' il pezzo che i test esercitano
        senza aprire nessun socket.
        """
        try:
            msg = json.loads(grezzo)
        except (ValueError, TypeError):
            return False
        if not isinstance(msg, dict):
            return False
        if msg.get("t") == TOPIC_SCANNER_STATO:
            # il battito dello scanner: si annota QUANDO e' arrivato (lo
            # scanner lo emette ogni ``_STATUS_PERIOD_SEC``) e basta. Non e' una
            # riga e non entra nella cache delle righe.
            self.stato_mono = time.monotonic()
            return False
        if msg.get("t") not in TOPIC_SCAN_NOMI:
            # ``hello`` e gli altri topic passano di qui e non sono righe:
            # si ignorano senza contarli come scarti.
            return False
        riga = msg.get("d")
        if not self.cache.aggiorna(riga):
            return False
        self._forse_sveglia(riga)
        return True

    def _forse_sveglia(self, riga: Any) -> None:
        """Alza la sveglia solo se ``interessa`` dice di si'. Mai solleva."""
        if self.evento is None or self.interessa is None:
            return
        try:
            eid = str((riga or {}).get("event_id") or "")
            if eid and self.interessa(eid):
                self.svegliate += 1
                self.evento.set()
        except Exception as ex:  # noqa: BLE001 - svegliare non ferma il bot
            self.errori += 1
            self.ultimo_errore = str(ex)[:200]


# -------------------------------------------------------------- la sveglia UI
def installa_sveglia(canale: Any, evento: Optional[threading.Event],
                     conti: Optional[Dict[str, Any]] = None) -> bool:
    """Il canale del bot (47335) accetta la SOLA sveglia. Torna ``True`` se
    installata.

    Il canale resta ``solo_lettura=True``: il messaggio di sveglia non entra
    nella coda delle richieste, non ha un ``_dispatch``, non porta e non puo'
    portare nessun parametro d'ordine. Alza un ``threading.Event`` e basta. Il
    COMANDO vero resta la riga su ``safe_strategy_requests``, che il bot legge
    con la funzione di oggi, con le stesse guardie e la stessa idempotenza.

    Un ``sveglia`` con un ``motivo`` che non si conosce NON alza l'evento: si
    conta in ``rifiutate`` e basta. Fail-closed, come oggi.

    Usa il meccanismo pulito gia' in ``local_channel.LocalChannel``
    (F6, 18/09): ``set_sveglia(cb)`` registra ``cb`` come ``_su_sveglia``, e
    ``_on_message`` (``local_channel.py:157``) chiama ``cb(p)`` PRIMA della
    coda dei comandi per qualunque messaggio ``{"m": "sveglia"}``, qualunque
    sia il canale (``solo_lettura`` o no). Qui non si sostituisce piu'
    ``_on_message`` sull'ISTANZA del canale: la riga che mancava in
    ``local_channel.py`` e' stata applicata, ed e' quella che fa il lavoro.
    """
    if canale is None or evento is None:
        return False
    set_sveglia = getattr(canale, "set_sveglia", None)
    if not callable(set_sveglia):
        return False
    numeri = conti if isinstance(conti, dict) else {}
    numeri.setdefault("sveglie", 0)
    numeri.setdefault("rifiutate", 0)

    def _su_sveglia(payload: Any) -> None:
        """Chiamata da ``LocalChannel._on_message`` con SOLO ``p`` (un dict,
        mai altro: il canale garantisce gia' ``p if isinstance(p, dict) else
        {}``). Di questo messaggio non si legge nient'altro che ``motivo``."""
        motivo = ""
        if isinstance(payload, dict):
            grezzo_motivo = payload.get("motivo")
            if isinstance(grezzo_motivo, str):
                motivo = grezzo_motivo.strip().lower()
        if motivo not in MOTIVI_SVEGLIA:
            numeri["rifiutate"] = int(numeri.get("rifiutate", 0)) + 1
            return
        numeri["sveglie"] = int(numeri.get("sveglie", 0)) + 1
        numeri["ultimo_motivo"] = motivo
        evento.set()
        logger.info("[safe.bot] sveglia dal canale (%s): ciclo anticipato", motivo)

    try:
        set_sveglia(_su_sveglia)
    except Exception as ex:  # noqa: BLE001 - senza sveglia si lavora come oggi
        logger.warning("[safe.bot] sveglia sul canale NON installata: %s", str(ex)[:160])
        return False
    return True
