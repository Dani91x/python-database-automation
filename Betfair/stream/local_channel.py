"""local_channel.py — A7: canale LOCALE UI(desktop) ↔ runner (WebSocket su 127.0.0.1).

È il fix strutturale della latenza: quando l'app desktop è collegata, ladder/
stato/ordini/posizioni sono PUSHATI direttamente dalla cache flumine (niente
giro sul cloud) e i comandi ordine arrivano qui e vengono ESEGUITI DALLO STESSO
path di validazione del worker coda (stesse guardie, stesso specchio, stesso
journal) — nessun secondo path ordini: cambia solo il trasporto.

SICUREZZA: bind ESCLUSIVO su 127.0.0.1 (irraggiungibile dall'esterno). I comandi
NON vengono eseguiti nel thread del WebSocket: finiscono in una coda in-memory
drenata dal THREAD del live_order_worker (un solo thread tocca flumine per gli
ordini, come oggi). Il canale è best-effort: se cade, la UI ricade sul path DB.

Protocollo (JSON, una riga per messaggio):
  push  server→client : {"t": <topic>, "d": <payload>}   topic: hello|ladder|now|order|position|board
  req   client→server : {"id": <int>, "m": "order"|"snapshot", "p": {...}}
  res   server→client : {"id": <int>, "ok": bool, "d": {...}} | {"id",..,"ok":false,"e": "msg"}
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import queue
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

_ALLOWED_METHODS = frozenset({"order", "snapshot"})

# ---------------------------------------------------------------------------
# C1 (24/09) - ORIGINE + TOKEN DI SESSIONE.
#
# Un WebSocket del browser NON e' soggetto a CORS: prima di oggi qualunque
# pagina aperta sulla macchina poteva collegarsi a ws://127.0.0.1:47331 e
# mandare {"m": "order"}. Due chiavi, entrambe necessarie per un comando che
# ESEGUE:
#
# 1. ORIGINE. Un browser mette SEMPRE l'header ``Origin`` e una pagina non puo'
#    falsificarlo. Si accettano solo le origini dell'app (la UI servita da
#    ``desktop/main.js`` su 127.0.0.1:47330) e quelle scritte a mano in
#    ``LOCAL_CHANNEL_ORIGINS`` (virgole). Nessun header Origin = client NON
#    browser (i lettori Python dei bot, la sveglia): ammesso, perche' un
#    processo locale che volesse mentire potrebbe comunque farlo. "null" (iframe
#    in sandbox, pagine data:/file:) NON e' mai ammesso. Origine estranea ->
#    handshake RIFIUTATO (HTTP 403) con il motivo nel log.
# 2. TOKEN. I metodi che ESEGUONO (``order``) passano solo da una connessione
#    che si e' presentata col token di sessione (``?t=<token>`` nel percorso).
#    Il token lo genera ``desktop/main.js`` una volta per avvio dell'app e lo
#    passa ai runner nell'ambiente (``LOCAL_CHANNEL_TOKEN``, la stessa via di
#    ``APP_BOOT_ID``) e alla pagina dal preload. Senza token (o con un token
#    sbagliato) il comando e' RIFIUTATO, la connessione CHIUSA, il motivo nel
#    log: mai un comando eseguito. I lettori e i push non chiedono token.
#    Runner avviato fuori dall'app (niente variabile): token CASUALE che nessuno
#    conosce -> nessun comando dal canale, la UI usa la coda DB (fail-closed).
# ---------------------------------------------------------------------------
_METODI_CHE_ESEGUONO = frozenset({"order"})
ENV_TOKEN = "LOCAL_CHANNEL_TOKEN"
ENV_ORIGINI = "LOCAL_CHANNEL_ORIGINS"
# la UI dell'app desktop (desktop/main.js: UI_PORT = 47330, carica 127.0.0.1)
ORIGINI_APP = frozenset({"http://127.0.0.1:47330", "http://localhost:47330"})
_TOKEN_MIN_LEN = 32
_CHIUSURA_POLICY = 1008   # RFC 6455: violazione di policy


def origini_ammesse(extra: Optional[str] = None) -> frozenset:
    """Le origini browser ammesse: quelle dell'app piu' ``LOCAL_CHANNEL_ORIGINS``.

    "null" non entra mai, nemmeno se scritto nella variabile: e' l'origine di
    qualunque iframe in sandbox o pagina locale, cioe' di chiunque."""
    grezzo = os.getenv(ENV_ORIGINI, "") if extra is None else extra
    scritte = {o.strip().rstrip("/") for o in str(grezzo or "").split(",") if o.strip()}
    scritte.discard("null")
    return frozenset(ORIGINI_APP | scritte)


def token_di_sessione() -> str:
    """Il token dei comandi: quello dell'app (env) se valido, altrimenti uno
    CASUALE che nessuno conosce (nessun comando accettato dal canale)."""
    t = str(os.getenv(ENV_TOKEN, "") or "").strip()
    if len(t) >= _TOKEN_MIN_LEN:
        return t
    if t:
        logger.warning("[local-ws] %s troppo corto (%d caratteri, minimo %d): ignorato, "
                       "nessun comando accettato dal canale.", ENV_TOKEN, len(t), _TOKEN_MIN_LEN)
    else:
        logger.warning("[local-ws] %s assente (runner avviato fuori dall'app): nessun "
                       "comando ordine accettato dal canale, la UI usa la coda DB.", ENV_TOKEN)
    return secrets.token_hex(32)


def _origine_di(request: Any) -> Optional[str]:
    """L'header Origin della richiesta di connessione (solo per il log)."""
    try:
        return request.headers.get("Origin") if request is not None else None
    except Exception:  # noqa: BLE001
        return None


def token_dal_percorso(percorso: Any) -> Optional[str]:
    """Il token presentato nel percorso di connessione (``?t=...``), o None."""
    if not isinstance(percorso, str) or "?" not in percorso:
        return None
    valori = parse_qs(urlsplit(percorso).query).get("t") or []
    return str(valori[0]) if len(valori) == 1 and valori[0] else None
_MAX_QUEUE = 200  # anti-runaway: mai accumulare comandi all'infinito
# LETTORI (23/09, esiti degli ordini): un client che si collega al percorso
# ``/lettore/<topic>[,<topic>...]`` e' un LETTORE. Riceve SOLO i topic che ha
# dichiarato, NON conta come "desktop collegato" (``is_active``) e non puo'
# mandare comandi. Serve ai bot (Omega, Safe) che leggono gli esiti dei loro
# ordini dal canale del runner: senza questa distinzione il loro socket
# avrebbe acceso nel runner il ramo "desktop presente" (ladder su DB ogni 2 s,
# board_worker con chiamate REST a Betfair, coda letta ogni secondo), cioe'
# cambiato il comportamento del processo che gestisce i soldi solo per averlo
# ascoltato. Un client su qualunque altro percorso resta quello di sempre.
PREFISSO_LETTORE = "/lettore/"


def topic_del_lettore(percorso: Any) -> Optional[frozenset]:
    """I topic dichiarati da un lettore, o ``None`` se il percorso non e' da
    lettore (client di sempre). ``/lettore/`` senza topic = lettore che non
    riceve niente (frozenset vuoto): mai "tutto" per difetto."""
    if not isinstance(percorso, str) or not percorso.startswith(PREFISSO_LETTORE):
        return None
    coda = percorso[len(PREFISSO_LETTORE):].split("?", 1)[0]
    return frozenset(t.strip() for t in coda.split(",") if t.strip())
# COMANDI (24/09, motore ordini F3): un client che si collega a
# ``/comando/<attore>`` parla il protocollo «comando ordine» (busta
# ``{"t": ..., "d": {...}}``) servito dal MOTORE ORDINI del runner
# (``motore_ordini.py``). Come i lettori, NON riceve i topic in broadcast e NON
# conta come desktop collegato: riceve solo i messaggi indirizzati al suo
# attore (ack, eventi ``order`` con ``seq``). Il token si legge UNA volta
# all'apertura (header ``X-Canale-Token`` oppure ``?t=`` come C1) e si
# confronta con l'UNICO token del canale (``LocalChannel._token``, generato da
# ``token_di_sessione``); il rifiuto per token lo decide il motore (ack con motivo).
PREFISSO_COMANDO = "/comando/"
HEADER_TOKEN = "X-Canale-Token"
_MAX_COMANDI = 200  # stesso tetto anti-runaway della coda di /order


def token_canale() -> Optional[str]:
    """Il token dei comandi del canale ATTIVO nel processo (una sola sorgente:
    ``token_di_sessione`` al costruttore del canale), o ``None`` se il processo
    non ha canale. Serve agli attori in-process e ai test."""
    ch = _CHANNEL
    return ch._token if ch is not None else None


def attore_del_comando(percorso: Any) -> Optional[str]:
    """L'attore di un percorso ``/comando/<attore>``, o ``None`` se il percorso
    non e' di comando. ``/comando/`` senza attore -> stringa vuota (rifiutata
    dal motore, mai un attore "di default")."""
    if not isinstance(percorso, str) or not percorso.startswith(PREFISSO_COMANDO):
        return None
    return percorso[len(PREFISSO_COMANDO):].split("?", 1)[0].strip("/").strip()


def _header_token(ws: Any) -> Optional[str]:
    try:
        headers = getattr(getattr(ws, "request", None), "headers", None)
        return headers.get(HEADER_TOKEN) if headers is not None else None
    except Exception:  # noqa: BLE001 - richiesta inattesa: nessun token
        return None


# invii non ancora completati oltre i quali si smette di pubblicare: con pochi
# client su 127.0.0.1 non ci si arriva mai, e se ci si arriva vuol dire che il
# consumatore e' fermo — mandargli altra roba non lo aiuta.
_MAX_INVII_IN_VOLO = 64


@dataclass
class LocalRequest:
    """Richiesta drenata dal worker (il ws serve solo per la risposta)."""

    ws: Any
    msg_id: Any
    method: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComandoCanale:
    """Messaggio di un socket ``/comando/<attore>`` drenato dal motore ordini.
    ``tipo`` = ``t`` della busta (``comando`` | ``da_seq``); ``ricevuto_ms`` =
    orologio da parete all'arrivo sul canale (serve al limite d'eta')."""

    ws: Any
    attore: str
    token_ok: bool
    tipo: str
    d: Dict[str, Any] = field(default_factory=dict)
    ricevuto_ms: int = 0


class LocalChannel:
    """Server WS su localhost. publish/respond sono THREAD-SAFE (call_soon_threadsafe)."""

    def __init__(self, port: int, sport: str = "calcio", solo_lettura: bool = False,
                 token: Optional[str] = None,
                 origini: Optional[Iterable[str]] = None) -> None:
        self.port = int(port)
        self.sport = sport
        # C1 (24/09): chi puo' collegarsi (origini browser) e chi puo' comandare
        # (token). ``None`` = dall'ambiente (vedi ``token_di_sessione`` e
        # ``origini_ammesse``); i test passano valori espliciti.
        self._token: str = str(token) if token else token_di_sessione()
        self._origini: frozenset = (frozenset(str(o).rstrip("/") for o in origini) - {"null"}
                                    if origini is not None else origini_ammesse())
        # connessioni che si sono presentate col token giusto. SOLO thread del loop.
        self._autorizzati: set = set()
        self._conti_rifiuti: Dict[str, int] = {"origine": 0, "token": 0}
        # CANALE DI SOLA USCITA (14/09). I canali dei BOT (Mike, Omega, Safe)
        # servono a mostrare, non a comandare: nessuno drena la loro coda, e una
        # richiesta che arrivasse resterebbe li' senza risposta finche' la coda
        # non si riempie (200) e comincia a rifiutare in silenzio.
        # Meglio dirlo subito e chiaramente.
        #
        # E c'e' una ragione piu' importante del garbo: il canale del runner
        # ESEGUE ORDINI VERI. Tenere i due livelli di fiducia separati — chi
        # comanda e chi mostra — vuol dire che aggiungere uno schermo non
        # aggiunge mai una via per mandare soldi.
        self.solo_lettura = bool(solo_lettura)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: set = set()          # toccato SOLO dal thread del loop
        self._requests: "queue.Queue[LocalRequest]" = queue.Queue(maxsize=_MAX_QUEUE)
        self._n_clients = 0                 # letto cross-thread (int: atomico)
        self._in_volo = 0               # invii non ancora completati (contropressione)
        self._ultimo_avviso = 0.0
        self._started = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._hello_extra: Dict[str, Any] = {}
        # F6 (18/09): chi va avvisato quando la pagina manda una SVEGLIA.
        self._su_sveglia: Optional[Any] = None
        # F2/F3 (24/09): il motore ordini registra qui la sua sveglia: ogni
        # comando (``/order`` di sempre o ``/comando/<attore>``) la chiama
        # appena messo in coda, cosi' il thread ordini non dorme 1 s.
        self._su_comando: Optional[Any] = None
        self._comandi: "queue.Queue[ComandoCanale]" = queue.Queue(maxsize=_MAX_COMANDI)
        # ws di comando -> (attore, token_ok). SOLO thread del loop.
        self._comando_ws: Dict[Any, tuple] = {}
        # --- F1 (18/09), difetto D4: CONTROPRESSIONE PER CLIENT ---------------
        # Prima il tetto degli invii in volo era UNO SOLO per tutto il canale:
        # una Control Room aperta e lenta (browser in secondo piano, DevTools
        # aperto) toglieva il fotogramma anche al bot, che sul suo socket non
        # era indietro di niente. Adesso il conto e' per socket: chi e' indietro
        # perde il giro, gli altri ricevono.
        # ``_in_volo_ws`` e ``_client_pronti`` sono toccati SOLO dal thread del
        # loop; ``_client_pronti`` e' un int, letto cross-thread (atomico in
        # CPython) come gia' ``_n_clients``.
        self._in_volo_ws: Dict[Any, int] = {}
        self._client_pronti = 0
        # che cosa e' successo al canale: giri saltati (nessun client poteva
        # riceverli), push saltati per un singolo client indietro. Se si salta
        # LO SI DICE, non lo si assorbe.
        self._conti: Dict[str, int] = {"saltati": 0, "saltati_client": 0}
        # LETTORI (23/09): ws -> topic dichiarati. Toccato SOLO dal thread del
        # loop; ``_n_lettori`` (int) e ``_topic_lettori`` (frozenset, sostituito
        # per intero) sono letti cross-thread, atomici in CPython come
        # ``_n_clients``.
        self._lettori: Dict[Any, frozenset] = {}
        self._n_lettori = 0
        self._topic_lettori: frozenset = frozenset()
        # i client che NON sono lettori (desktop), in UNA sola assegnazione:
        # ``is_active`` letto da un altro thread non vede mai uno stato a meta'
        # fra l'aggiornamento dei client e quello dei lettori.
        self._n_desktop = 0

    # ------------------------------------------------------------- lifecycle
    def start(self) -> bool:
        """Avvia il server in un thread dedicato. False se la porta è occupata."""
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"local-ws-{self.port}")
        self._thread.start()
        self._started.wait(timeout=5.0)
        return self._loop is not None

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except Exception as ex:  # noqa: BLE001 - canale opzionale: il runner vive senza
            logger.warning("[local-ws] server KO (porta %d): %s", self.port, str(ex)[:160])
            self._started.set()

    async def _serve(self) -> None:
        from websockets.asyncio.server import serve

        self._loop = asyncio.get_running_loop()
        try:
            async with serve(self._handler, "127.0.0.1", self.port,
                             process_request=self._controlla_origine):
                self._started.set()
                logger.info("[local-ws] canale locale %s attivo su 127.0.0.1:%d", self.sport, self.port)
                await asyncio.Future()  # per sempre (thread daemon)
        finally:
            self._loop = None
            self._started.set()

    def _controlla_origine(self, connection: Any, request: Any) -> Any:
        """C1: handshake RIFIUTATO (403) se un browser si presenta da un'origine
        che non e' quella dell'app. Senza header Origin (client non browser) si
        passa: il token decide poi se puo' comandare. Mai solleva."""
        try:
            origini = list(request.headers.get_all("Origin"))
        except Exception:  # noqa: BLE001 - header illeggibili: si rifiuta
            origini = ["<illeggibile>"]
        if not origini:
            return None
        origine = str(origini[0]).rstrip("/")
        if len(origini) == 1 and origine in self._origini:
            return None
        self._conti_rifiuti["origine"] += 1
        logger.warning("[local-ws] connessione RIFIUTATA sulla porta %d: origine non "
                       "ammessa %r (ammesse: %s). Nessun comando puo' arrivare da li'.",
                       self.port, origini if len(origini) != 1 else origine,
                       ", ".join(sorted(self._origini)))
        return connection.respond(403, "origine non ammessa\n")

    def _token_valido(self, presentato: Optional[str]) -> bool:
        if not presentato:
            return False
        return hmac.compare_digest(str(presentato).encode("utf-8"),
                                   self._token.encode("utf-8"))

    async def _handler(self, ws: Any) -> None:
        percorso = getattr(getattr(ws, "request", None), "path", None)
        filtro = topic_del_lettore(percorso)
        attore = attore_del_comando(percorso)
        self._clients.add(ws)
        if attore is not None:
            # socket di COMANDO: nessun broadcast (filtro vuoto, come un lettore
            # senza topic) e non conta come desktop. Token letto UNA volta qui:
            # header ``X-Canale-Token`` o ``?t=`` (C1), confrontato con l'UNICO
            # token del canale (``self._token``, da ``token_di_sessione``).
            presentato = _header_token(ws) or token_dal_percorso(percorso)
            self._comando_ws[ws] = (attore, self._token_valido(presentato))
            filtro = frozenset()
        if filtro is not None:
            self._lettori[ws] = filtro
        elif self._token_valido(token_dal_percorso(percorso)):
            # C1: solo chi ha il token puo' mandare comandi che eseguono
            self._autorizzati.add(ws)
        self._ricalcola_lettori()
        self._n_clients = len(self._clients)
        self._ricalcola_pronti()
        try:
            await ws.send(json.dumps({"t": "hello", "d": {"sport": self.sport, **self._hello_extra}}))
            async for raw in ws:
                self._on_message(ws, raw)
        except Exception:  # noqa: BLE001 - disconnessioni brusche: normali
            pass
        finally:
            self._clients.discard(ws)
            self._in_volo_ws.pop(ws, None)
            self._lettori.pop(ws, None)
            self._comando_ws.pop(ws, None)
            self._autorizzati.discard(ws)
            self._ricalcola_lettori()
            self._n_clients = len(self._clients)
            self._ricalcola_pronti()

    def _ricalcola_lettori(self) -> None:
        """Conti dei lettori e dei desktop. SOLO dal thread del loop."""
        self._topic_lettori = frozenset().union(*self._lettori.values()) \
            if self._lettori else frozenset()
        self._n_lettori = len(self._lettori)
        self._n_desktop = sum(1 for w in self._clients if w not in self._lettori)

    def _ricalcola_pronti(self) -> None:
        """Quanti client possono ricevere adesso. SOLO dal thread del loop.

        I client su 127.0.0.1 sono pochissimi (la Control Room e i bot): il
        conteggio e' O(n) su una manciata di elementi e si paga una volta per
        invio completato, non per messaggio pubblicato. Serve a far uscire
        ``publish`` PRIMA di serializzare quando nessuno puo' ricevere, che e'
        la protezione che c'era gia' - qui resa per client.
        """
        self._client_pronti = sum(
            1 for w in self._clients if self._in_volo_ws.get(w, 0) <= _MAX_INVII_IN_VOLO
        )

    def _on_message(self, ws: Any, raw: Any) -> None:
        """Parse + enqueue (nel thread del loop). MAI eseguire ordini qui."""
        if ws in self._comando_ws:
            self._on_comando(ws, raw)
            return
        try:
            msg = json.loads(raw)
            method = str(msg.get("m") or "")
            msg_id = msg.get("id")
            if ws in self._lettori:
                # un LETTORE ascolta e basta: nessun comando, nessuna sveglia.
                # Aggiungere un ascoltatore non deve mai aggiungere una via per
                # mandare soldi.
                self._send(ws, {"id": msg_id, "ok": False,
                                "e": "lettore: nessun comando accettato"})
                return
            if method == "sveglia":
                # F6 (18/09): SOLO la sveglia. Esce PRIMA della coda dei comandi,
                # non passa da ``_ALLOWED_METHODS`` e non porta parametri d'ordine:
                # il comando vero resta la riga sul database, con le guardie di
                # sempre. Non puo' diventare un secondo percorso ordini.
                cb = self._su_sveglia
                if cb is not None:
                    try:
                        p = msg.get("p")
                        cb(p if isinstance(p, dict) else {})
                    except Exception:  # noqa: BLE001 - una sveglia non ferma il canale
                        pass
                self._send(ws, {"id": msg_id, "ok": cb is not None})
                return
            if self.solo_lettura:
                self._send(ws, {"id": msg_id, "ok": False,
                                "e": "canale di sola lettura: nessun comando accettato"})
                return
            if method not in _ALLOWED_METHODS:
                self._send(ws, {"id": msg_id, "ok": False, "e": f"metodo sconosciuto: {method}"})
                return
            if method in _METODI_CHE_ESEGUONO and ws not in self._autorizzati:
                # C1: comando che esegue da una connessione senza token (o col
                # token sbagliato). Si risponde, si CHIUDE, si scrive perche'.
                # Il comando non entra nemmeno in coda.
                self._rifiuta_senza_token(ws, msg_id, method)
                return
            params = msg.get("p")
            self._requests.put_nowait(
                LocalRequest(ws=ws, msg_id=msg_id, method=method,
                             params=params if isinstance(params, dict) else {})
            )
            self._sveglia_motore()
        except queue.Full:
            self._send(ws, {"id": msg.get("id"), "ok": False,
                            "e": "coda locale piena: comando NON accettato (riprova)"})
        except Exception as ex:  # noqa: BLE001 - messaggio malformato
            logger.debug("[local-ws] messaggio malformato: %s", str(ex)[:120])

    def _sveglia_motore(self) -> None:
        cb = self._su_comando
        if cb is not None:
            try:
                cb()
            except Exception:  # noqa: BLE001 - una sveglia non ferma il canale
                pass

    def _on_comando(self, ws: Any, raw: Any) -> None:
        """Messaggio di un socket ``/comando/<attore>`` (thread del loop). MAI
        eseguire qui: si mette in coda per il motore e lo si sveglia. Rifiuti
        immediati SOLO quando il motore non puo' nemmeno vederlo (nessun motore,
        coda piena, busta illeggibile): ack con ``seq`` None."""
        attore, token_ok = self._comando_ws.get(ws, ("", False))
        ricevuto_ms = int(time.time() * 1000)
        ref = None
        try:
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                raise ValueError("busta non e' un oggetto")
            tipo = str(msg.get("t") or "")
            d = msg.get("d") if isinstance(msg.get("d"), dict) else {}
            ref = d.get("ref") if isinstance(d.get("ref"), str) else None
        except Exception:  # noqa: BLE001 - messaggio malformato: rifiuto dichiarato
            self._send(ws, _ack_canale(None, "parametri_invalidi: busta JSON illeggibile",
                                       ricevuto_ms))
            return
        if tipo not in ("comando", "da_seq"):
            self._send(ws, _ack_canale(ref, f"parametri_invalidi: tipo sconosciuto {tipo!r}",
                                       ricevuto_ms))
            return
        if self._su_comando is None:
            self._send(ws, _ack_canale(ref, "motore_non_attivo: nessun esecutore ordini "
                                            "in questo processo", ricevuto_ms))
            return
        try:
            self._comandi.put_nowait(ComandoCanale(ws=ws, attore=attore, token_ok=token_ok,
                                                   tipo=tipo, d=d, ricevuto_ms=ricevuto_ms))
        except queue.Full:
            self._send(ws, _ack_canale(ref, "coda_piena: comando NON accettato",
                                       ricevuto_ms))
            return
        self._sveglia_motore()
    def _rifiuta_senza_token(self, ws: Any, msg_id: Any, method: str) -> None:
        """C1: risposta di rifiuto + chiusura della connessione (policy 1008)."""
        self._conti_rifiuti["token"] += 1
        req = getattr(ws, "request", None)
        logger.warning("[local-ws] comando %r RIFIUTATO sulla porta %d: token di sessione "
                       "assente o errato (origine %r). Nessun comando eseguito, "
                       "connessione chiusa.", method, self.port,
                       _origine_di(req))
        self._send(ws, {"id": msg_id, "ok": False,
                        "e": "comando rifiutato: token di sessione assente o errato "
                             "(NESSUN ordine eseguito)"})
        if self._loop is not None and hasattr(ws, "close"):
            self._loop.create_task(self._chiudi_dopo_la_risposta(ws))

    async def _chiudi_dopo_la_risposta(self, ws: Any) -> None:
        # un giro di loop per lasciar partire la risposta prima della chiusura
        await asyncio.sleep(0.05)
        try:
            await ws.close(_CHIUSURA_POLICY, "token di sessione assente o errato")
        except Exception:  # noqa: BLE001 - client gia' andato
            pass

    def _send(self, ws: Any, payload: Dict[str, Any]) -> None:
        """Send fire-and-forget dal thread del loop."""
        if self._loop is None:
            return
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            return
        self._loop.create_task(self._safe_send(ws, text))

    async def _safe_send(self, ws: Any, text: str) -> None:
        self._in_volo += 1              # solo dal thread del loop: nessuna corsa
        self._in_volo_ws[ws] = self._in_volo_ws.get(ws, 0) + 1
        self._ricalcola_pronti()
        try:
            await ws.send(text)
        except Exception:  # noqa: BLE001 - client andato: ignora
            pass
        finally:
            self._in_volo -= 1
            rimasti = self._in_volo_ws.get(ws, 1) - 1
            if rimasti <= 0:
                self._in_volo_ws.pop(ws, None)
            else:
                self._in_volo_ws[ws] = rimasti
            self._ricalcola_pronti()

    # ------------------------------------------------------- API thread-safe
    def is_active(self) -> bool:
        """True se almeno un client desktop è collegato.

        I LETTORI (23/09) non contano: un bot che ascolta gli esiti dei suoi
        ordini non e' un desktop, e non deve accendere nel runner i rami
        riservati al desktop presente."""
        return self._n_desktop > 0

    def set_hello(self, **extra: Any) -> None:
        self._hello_extra.update(extra)

    def set_su_comando(self, cb: Optional[Any]) -> None:
        """F2 (24/09): registra la sveglia del MOTORE ORDINI, chiamata (dal thread
        del loop) a ogni comando messo in coda. ``None`` = nessun motore: i
        comandi ``/comando/`` vengono rifiutati subito, ``/order`` resta in coda
        per il worker di sempre."""
        self._su_comando = cb

    def pop_comandi(self, max_n: int = 50) -> "list[ComandoCanale]":
        """Drena fino a max_n messaggi ``/comando/`` (thread del motore)."""
        out: list = []
        for _ in range(max_n):
            try:
                out.append(self._comandi.get_nowait())
            except queue.Empty:
                break
        return out

    def invia(self, ws: Any, payload: Dict[str, Any]) -> None:
        """Invio MIRATO a un socket (thread-safe). MAI solleva."""
        loop = self._loop
        if loop is None:
            return
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            return
        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(self._safe_send(ws, text)))
        except RuntimeError:
            pass

    def invia_attore(self, attore: str, payload: Dict[str, Any]) -> None:
        """Invio a TUTTI i socket di comando di un attore (thread-safe)."""
        loop = self._loop
        if loop is None:
            return
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            return

        def _manda() -> None:
            for w, (att, _tok) in list(self._comando_ws.items()):
                if att == attore:
                    loop.create_task(self._safe_send(w, text))
        try:
            loop.call_soon_threadsafe(_manda)
        except RuntimeError:
            pass

    def set_sveglia(self, cb: Optional[Any]) -> None:
        """F6: registra chi va avvisato all'arrivo di ``{"m": "sveglia"}``.
        Senza nessuno registrato la sveglia viene rifiutata (``ok: False``)."""
        self._su_sveglia = cb

    def statistiche(self) -> Dict[str, Any]:
        """Che cosa e' successo al canale: giri saltati perche' NESSUN client
        poteva riceverli, push saltati per un singolo client rimasto indietro,
        client agganciati, invii in volo. Se la coda cresce LO SI DICE, non lo
        si assorbe: e' il numero che la prova a secco di F1 deve leggere."""
        return {**self._conti, "client": self._n_clients,
                "rifiutati_origine": self._conti_rifiuti["origine"],
                "rifiutati_token": self._conti_rifiuti["token"],
                "lettori": self._n_lettori,
                "client_pronti": self._client_pronti, "in_volo": self._in_volo,
                "porta": self.port, "solo_lettura": self.solo_lettura}

    def publish(self, topic: str, payload: Any) -> None:
        """Broadcast a tutti i client. No-op senza client/loop. MAI solleva.

        CONTROPRESSIONE (14/09, resa PER CLIENT il 18/09 - difetto D4): se un
        consumatore rallenta, gli invii in volo si accumulano DENTRO il processo
        che gestisce i soldi, quindi un tetto serve. Ma il tetto era uno solo per
        l'intero canale: un client lento faceva saltare il fotogramma anche a
        tutti gli altri, cioe' una Control Room in secondo piano poteva togliere
        il prezzo al bot. Adesso il conto e' per socket.

        Il giro si salta - non si accumula - perche' qui passa uno STATO
        COMPLETO: il fotogramma dopo ripara. Per un flusso DIFFERENZIALE questa
        disciplina non andrebbe bene, ed e' per questo che il topic ``raw`` non
        esiste in questa fase (F7 del piano, opzionale).
        """
        loop = self._loop
        if loop is None or self._n_clients == 0:
            return
        if self._n_clients <= self._n_lettori and topic not in self._topic_lettori:
            # solo lettori collegati e nessuno ha chiesto questo topic: niente
            # da serializzare (23/09).
            return
        if self._client_pronti <= 0:
            # nessuno puo' ricevere: si esce PRIMA di serializzare, come prima
            self._conti["saltati"] += 1
            ora = time.monotonic()
            if ora - self._ultimo_avviso > 30.0:
                self._ultimo_avviso = ora
                logger.warning("[local-ws] %d invii in volo sulla porta %d, nessun "
                               "client pronto: salto i push finche' non recuperano.",
                               self._in_volo, self.port)
            return
        try:
            text = json.dumps({"t": topic, "d": payload}, default=str)
        except Exception as ex:  # noqa: BLE001 - payload non serializzabile: dichiara nel log
            logger.warning("[local-ws] publish %s non serializzabile: %s", topic, str(ex)[:120])
            return

        def _broadcast() -> None:
            for ws in list(self._clients):
                filtro = self._lettori.get(ws)
                if filtro is not None and topic not in filtro:
                    continue          # lettore: solo i topic che ha chiesto
                if self._in_volo_ws.get(ws, 0) > _MAX_INVII_IN_VOLO:
                    # SOLO questo client perde il giro: gli altri no
                    self._conti["saltati_client"] += 1
                    continue
                loop.create_task(self._safe_send(ws, text))
        try:
            loop.call_soon_threadsafe(_broadcast)
        except RuntimeError:  # loop chiuso
            pass

    def pop_requests(self, max_n: int = 20) -> "list[LocalRequest]":
        """Drena fino a max_n richieste (chiamato dal thread del worker)."""
        out: list[LocalRequest] = []
        for _ in range(max_n):
            try:
                out.append(self._requests.get_nowait())
            except queue.Empty:
                break
        return out

    def respond(self, req: LocalRequest, ok: bool, data: Any = None, error: Optional[str] = None) -> None:
        """Risposta a una richiesta (thread-safe). MAI solleva."""
        loop = self._loop
        if loop is None:
            return
        payload: Dict[str, Any] = {"id": req.msg_id, "ok": ok}
        if data is not None:
            payload["d"] = data
        if error:
            payload["e"] = str(error)[:300]
        try:
            text = json.dumps(payload, default=str)
        except Exception:  # noqa: BLE001
            text = json.dumps({"id": req.msg_id, "ok": False, "e": "risposta non serializzabile"})
        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(self._safe_send(req.ws, text)))
        except RuntimeError:
            pass


def _ack_canale(ref: Any, motivo: str, ricevuto_ms: int) -> Dict[str, Any]:
    """Ack di RIFIUTO emesso dal canale stesso (motore assente, coda piena,
    busta illeggibile): stessa forma dell'ack del motore, ``seq`` None perche'
    la numerazione per attore e' del motore."""
    return {"t": "ack", "d": {"ref": ref, "seq": None, "accettato": False,
                              "motivo": motivo, "ricevuto_ms": ricevuto_ms}}


# ---------------------------------------------------------------------------
# Singleton per-processo (calcio e tennis girano in PROCESSI separati).
# ---------------------------------------------------------------------------
_CHANNEL: Optional[LocalChannel] = None


def start_channel(port: int, sport: str, solo_lettura: bool = False) -> Optional[LocalChannel]:
    """Avvia (una volta) il canale locale del processo. None se non parte.

    ``solo_lettura=True`` per i canali dei BOT: mostrano e basta, non accettano
    comandi. Vedi ``LocalChannel.__init__``.

    18/09, difetto D1: il singleton e' per PROCESSO, e finche' un processo aveva
    un canale solo il difetto non si vedeva. Chiedere una porta DIVERSA da
    quella del canale gia' attivo restituiva in silenzio il canale vecchio: il
    secondo produttore avrebbe pubblicato sul canale del primo, e se il primo
    fosse 47331 (che ESEGUE ORDINI VERI) si sarebbe allargato il canale che
    comanda a un produttore che doveva solo mostrare. Adesso si rifiuta e si
    dichiara: meglio nessun canale che il canale sbagliato.
    """
    global _CHANNEL
    if _CHANNEL is not None:
        if int(port) != _CHANNEL.port:
            logger.error(
                "[local-ws] canale gia' attivo sulla porta %d: RIFIUTO la richiesta "
                "sulla porta %d (un processo, un canale). Chi chiedeva il canale "
                "nuovo resta senza: e' la direzione giusta del guasto.",
                _CHANNEL.port, int(port))
            return None
        return _CHANNEL
    ch = LocalChannel(port, sport, solo_lettura=solo_lettura)
    if ch.start():
        _CHANNEL = ch
        return ch
    return None


def get_channel() -> Optional[LocalChannel]:
    return _CHANNEL


def channel_active() -> bool:
    ch = _CHANNEL
    return ch is not None and ch.is_active()


def publish(topic: str, payload: Any) -> None:
    """Publish best-effort sul canale del processo (no-op se assente/inattivo)."""
    ch = _CHANNEL
    if ch is not None:
        ch.publish(topic, payload)


def statistiche() -> Optional[Dict[str, Any]]:
    """Le statistiche del canale del processo, o None se non ce n'e' uno."""
    ch = _CHANNEL
    return ch.statistiche() if ch is not None else None
