"""porta_banco.py - F4: la porta ordini del BANCO passa dal MOTORE VERO del runner.

Strada unica (decisione dell'utente, 24/09): in produzione un bot manda i suoi
ordini al runner con il protocollo «comando ordine» (``/comando/<attore>``) e li
esegue ``motore_ordini.MotoreOrdini`` -> ``live_order_worker._dispatch`` sul
``Market`` di flumine. Nel replay la stessa cosa deve accadere: qui NON c'e' una
copia del motore ne' un piazzamento fatto in casa. ``PortaBanco`` costruisce il
``MotoreOrdini`` di produzione e gli consegna i comandi come farebbe il canale;
il motore esegue il ``_dispatch`` vero sul ``Market`` della ``FlumineSimulation``
del banco.

Contratto con il vivo (inchiodato da ``tests/test_porta_banco_f4_2026_09_24.py``
e ``tests/test_strada_unica_banco_2026_09_25.py``):
  * ``invia(comando)`` ritorna l'ack del motore (stesse chiavi: ref, seq,
    accettato, motivo, ricevuto_ms), con le STESSE regole (dedup per ref, eta',
    parametri, place-and-trim sotto il minimo);
  * gli eventi ``order`` sono quelli del motore: la riga dello specchio
    ``betfair_live_orders`` (costruita da ``LiveTradingStrategy._order_row``,
    la funzione di produzione, piu' ``updated_at``) + ref/seq/fase/esito_ms;
  * ``aggiorna()`` va chiamato a ogni book del replay: legge il blotter (come fa
    lo stream ordini in produzione -> specchio) e fa avanzare il place-and-trim.

25/09 - AGGANCIO AL REPLAY (F4 finita). Due pezzi nuovi:
  * ``WsBanco``: il SOCKET in-process su cui parla il client VERO del bot
    (``safe_strategy.porta_ordini.PortaCanale``, e quindi anche quello di Omega):
    stessa busta JSON ``{"t", "d"}`` dai due lati, stesso ``ComandoCanale`` che
    costruisce ``LocalChannel._on_comando``, stesse risposte che il motore manda
    con ``canale.invia``/``invia_attore``. Il client gira col SUO thread
    (``_gira`` -> ``collega_una_volta`` -> ``recv``): niente e' sostituito.
  * ``modo_processo="LIVE"``: il replay di riferimento certifica i bot con le
    righe in modalita' ``live`` (``MercatoFlumine`` serve ``place_order_live``
    sul matching di flumine). Perche' il motore VERO serva una riga ``live``
    senza toccare ``_client_for_mode`` (produzione), il banco gli presenta nel
    registro dei client un ``ClienteLiveBanco``: e' il client simulato del banco
    (stessa esecuzione simulata, stesso matching, nessun soldo) con un'etichetta
    di venue non simulata, cosi' la regola di produzione "una riga live esige un
    client non simulato" resta attiva e verificata. DICHIARATO: nel banco
    nessun ordine e' reale, ne' sulla coda ne' sul canale.

Differenze DICHIARATE dal vivo (nel banco non esistono):
  * niente DB: lo scrittore asincrono e' nullo (conta i lavori, non li esegue);
  * il modo effettivo della Control Room e l'eta' dei settings non si applicano
    (``blocco_modo`` nullo, ``eta_settings`` 0);
  * il diario si scrive in una cartella temporanea (o in quella indicata);
  * l'eta' del comando si misura con l'orologio da parete (come il vivo: il
    client scrive ``creato_ms`` col suo orologio, il canale ``ricevuto_ms``).
"""
from __future__ import annotations

import collections
import json
import queue
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Deque, Dict, List, Optional

from .. import motore_ordini as MO
from ..local_channel import ComandoCanale, LocalRequest

#: il token del canale nel banco (il client vero lo manda nell'header)
TOKEN_BANCO = "banco-token-di-prova-0123456789"


class _ScrittoreNullo:
    """Il banco non ha DB: i lavori si contano e si scartano (il diario resta)."""

    def __init__(self) -> None:
        self.lavori: List[str] = []

    def accoda(self, descrizione: str, _job: Any, tentativi: int = 1) -> bool:  # noqa: ARG002
        self.lavori.append(descrizione)
        return True

    def avvia(self) -> None:
        return None

    def ferma(self, timeout: float = 0.0) -> None:  # noqa: ARG002
        return None

    def svuota(self, timeout: float = 0.0) -> bool:  # noqa: ARG002
        return True


class ClienteLiveBanco:
    """Il client simulato del banco presentato al motore come client ``live``.

    Delega TUTTO al client simulato (esecuzione, controlli, username): flumine
    esegue l'ordine con la ``SimulatedExecution`` del banco, esattamente come
    per ``MercatoFlumine``. Cambia SOLO ``VENUE``, che e' cio' che
    ``live_order_worker._is_paper_client`` legge: cosi' ``_client_for_mode``
    di produzione sceglie questo per le righe ``live`` e il client simulato per
    le righe ``paper``, e un ordine live resta distinguibile da uno paper
    (``order.client``). Nessun soldo: nel banco non esiste un client reale."""

    VENUE = SimpleNamespace(name="BANCO_LIVE", value="BANCO_LIVE")
    paper_trade = False

    def __init__(self, simulato: Any) -> None:
        object.__setattr__(self, "_simulato", simulato)

    def __getattr__(self, nome: str) -> Any:
        return getattr(object.__getattribute__(self, "_simulato"), nome)

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        return "ClienteLiveBanco(%r)" % (object.__getattribute__(self, "_simulato"),)


class _QuadroBanco:
    """Il framework visto dal motore nel banco LIVE: tutto e' quello della
    ``FlumineSimulation`` vera, tranne ``clients``, che elenca il client
    simulato (per le righe paper) e il ``ClienteLiveBanco`` (per le live)."""

    def __init__(self, quadro: Any, clienti: List[Any]) -> None:
        object.__setattr__(self, "_quadro", quadro)
        object.__setattr__(self, "clients", clienti)

    def __getattr__(self, nome: str) -> Any:
        return getattr(object.__getattribute__(self, "_quadro"), nome)


def _cliente_simulato_di(quadro: Any) -> Any:
    clienti = getattr(quadro, "clients", None)
    try:
        lista = list(clienti) if clienti is not None else []
    except Exception:  # noqa: BLE001
        lista = []
    if lista:
        return lista[0]
    get_default = getattr(clienti, "get_default", None)
    return get_default() if callable(get_default) else None


class WsBanco:
    """Il socket ``/comando/<attore>`` del banco, visto dal client VERO.

    Lato client: ``send(testo)`` / ``recv(timeout)`` / ``close()`` e contesto
    ``with``, come ``websockets.sync.client.connect``. Lato canale: il testo si
    decodifica come in ``LocalChannel._on_comando`` e diventa un
    ``ComandoCanale`` che il motore gestisce SUBITO (``_gestisci``: nel vivo il
    motore e' svegliato a evento, qui lo si chiama nello stesso istante). Le
    risposte del motore tornano al client come testo JSON, nell'ordine."""

    def __init__(self, porta: "PortaBanco", attore: str, token_ok: bool) -> None:
        self.porta = porta
        self.attore = attore
        self.token_ok = token_ok
        self._uscita: "queue.Queue[str]" = queue.Queue()
        self._chiuso = threading.Event()
        self._in_attesa = threading.Event()
        self.inviati: List[Dict[str, Any]] = []

    # --- lato client (stessi nomi di websockets.sync) -----------------------
    def __enter__(self) -> "WsBanco":
        return self

    def __exit__(self, *_a: Any) -> None:
        self.close()

    def send(self, testo: str) -> None:
        if self._chiuso.is_set():
            raise ConnectionError("socket del banco chiuso")
        self.porta._dal_socket(self, testo)

    def recv(self, timeout: Optional[float] = None) -> str:
        if self._chiuso.is_set():
            raise ConnectionError("socket del banco chiuso")
        self._in_attesa.set()
        try:
            return self._uscita.get(timeout=timeout)
        except queue.Empty:
            if self._chiuso.is_set():
                raise ConnectionError("socket del banco chiuso")
            raise TimeoutError("nessun messaggio")
        finally:
            self._in_attesa.clear()

    def close(self) -> None:
        self._chiuso.set()

    # --- lato canale ---------------------------------------------------------
    def consegna(self, payload: Dict[str, Any]) -> None:
        if not self._chiuso.is_set():
            self._uscita.put(json.dumps(payload, default=str))
            self.porta.consegnati += 1

    def svuotato(self) -> bool:
        """True quando il client ha letto e INCASSATO tutto: la coda e' vuota e
        il suo thread e' tornato ad aspettare su ``recv``."""
        return self._uscita.empty() and self._in_attesa.is_set()


class _CanaleBanco:
    """Il canale in-process: raccoglie cio' che il motore manda all'attore."""

    def __init__(self) -> None:
        self.messaggi: List[Dict[str, Any]] = []
        self._comandi: Deque[ComandoCanale] = collections.deque()
        self._richieste: Deque[LocalRequest] = collections.deque()
        self.su_messaggio: Optional[Callable[[Dict[str, Any]], None]] = None
        self.socket: List[WsBanco] = []

    # --- interfaccia usata dal motore (stessi nomi di LocalChannel) ---------
    def set_su_comando(self, _cb: Any) -> None:
        return None

    def pop_comandi(self, max_n: int = 50) -> List[ComandoCanale]:
        out = []
        while self._comandi and len(out) < max_n:
            out.append(self._comandi.popleft())
        return out

    def pop_requests(self, max_n: int = 20) -> List[LocalRequest]:
        out = []
        while self._richieste and len(out) < max_n:
            out.append(self._richieste.popleft())
        return out

    def invia(self, ws: Any, payload: Dict[str, Any]) -> None:
        if isinstance(ws, WsBanco):
            ws.consegna(payload)
        self._ricevi(payload)

    def invia_attore(self, attore: str, payload: Dict[str, Any]) -> None:
        for ws in list(self.socket):
            if ws.attore == attore:
                ws.consegna(payload)
        self._ricevi(payload)

    def respond(self, *_a: Any, **_k: Any) -> None:
        return None

    def _ricevi(self, payload: Dict[str, Any]) -> None:
        self.messaggi.append(payload)
        if self.su_messaggio is not None:
            self.su_messaggio(payload)


class PortaBanco:
    """Porta ordini del banco = motore ordini di produzione su FlumineSimulation."""

    def __init__(self, framework: Any, strategia: Any, *, attore: str,
                 sport: str = "calcio", cartella_diario: Optional[str] = None,
                 orologio_ms: Optional[Callable[[], int]] = None,
                 modo_processo: str = "PAPER") -> None:
        modo_processo = str(modo_processo or "PAPER").upper()
        if modo_processo not in ("PAPER", "LIVE"):
            raise ValueError("modo_processo del banco: PAPER o LIVE, non %r" % modo_processo)
        self.attore = attore
        self.modo_processo = modo_processo
        self.mode = "paper"
        self.canale = _CanaleBanco()
        self._orologio = orologio_ms or (lambda: int(time.time() * 1000))
        self._cartella = cartella_diario or tempfile.mkdtemp(prefix="diario_banco_")
        self.motore = MO.MotoreOrdini(
            sport, canale=self.canale, diario=MO.Diario(self._cartella),
            scrittore=_ScrittoreNullo(), orologio_ms=self._orologio,
            modo_processo=modo_processo, blocco_modo=lambda *_a: None,
            eta_settings=lambda: 0.0)
        self.framework = framework
        self.strategia = strategia
        self.cliente_simulato: Any = None
        self.cliente_live: Optional[ClienteLiveBanco] = None
        if modo_processo == "LIVE":
            self.cliente_simulato = _cliente_simulato_di(framework)
            if self.cliente_simulato is None:
                raise ValueError("banco LIVE senza client simulato nel framework")
            self.cliente_live = ClienteLiveBanco(self.cliente_simulato)
            vista = _QuadroBanco(framework, [self.cliente_live, self.cliente_simulato])
            self.motore.aggancia(vista, {"live": strategia, "paper": strategia})
        else:
            self.motore.aggancia(framework, {"paper": strategia})
        self._firme: Dict[str, tuple] = {}
        # gli ordini flumine nati dai comandi (id -> ordine), visti dallo specchio
        self.ordini_visti: Dict[str, Any] = {}
        # quelli visti per la prima volta e non ancora letti da chi li adotta
        self.ordini_nuovi: List[Any] = []
        # ordini ancora VIVI (id -> (market, ordine)): lo specchio li rilegge a
        # ogni book; i blotter interi si rileggono solo dopo un comando o un
        # passo del place-and-trim (``_sporco``), che e' quando nascono ordini
        self._vivi: Dict[str, Any] = {}
        self._sporco = False
        self._tutti_i_mercati = False
        # messaggi consegnati ai socket del client vero / gia' drenati
        self.consegnati = 0
        self._consegnati_drenati = 0
        self._ack: Dict[str, Dict[str, Any]] = {}
        self._eventi: Dict[str, List[Dict[str, Any]]] = {}
        # i mercati su cui e' passato almeno un comando: lo specchio li legge
        # tutti a ogni book (un blotter vuoto costa zero), gli altri no
        self._mercati: Dict[str, None] = {}
        # la TRACCIA del trasporto: un record per comando consegnato al motore
        self.comandi: List[Dict[str, Any]] = []
        self.giu = False
        self.ultimo_ws: Optional[WsBanco] = None
        # l'ora di MERCATO del replay (per la traccia: in che istante della
        # partita e' uscito il comando). None nei test senza replay.
        self.orologio_mercato: Optional[Callable[[], Any]] = None
        # ritardo di consegna del canale (scenario «comando vecchio»): il
        # comando arriva al motore ``ritardo_ms`` dopo la sua creazione
        self.ritardo_ms = 0
        self.canale.su_messaggio = self._incassa

    # ------------------------------------------------------------ interfaccia
    def disponibile(self) -> bool:
        return self.motore.agganciato

    def invia(self, comando: Dict[str, Any]) -> Dict[str, Any]:
        """Consegna il comando al motore (come il canale) e torna l'ack."""
        ref = comando.get("ref")
        c = ComandoCanale(ws=self, attore=self.attore, token_ok=True, tipo="comando",
                          d=dict(comando), ricevuto_ms=int(self._orologio()))
        self._registra(c)
        self.motore._gestisci(c)
        self.aggiorna()
        return dict(self._ack.get(str(ref), {}))

    def esiti(self, ref: str) -> List[Dict[str, Any]]:
        return list(self._eventi.get(str(ref), []))

    def aggiorna(self) -> None:
        """A ogni book: specchio dal blotter (come lo stream ordini) e un passo
        del place-and-trim."""
        if self.motore._submin:
            self._sporco = True            # la macchina puo' piazzare/sostituire
        self._specchio()
        if self.motore._submin:
            self.motore.avanza_submin()
            self._sporco = True
            self._specchio()

    # ------------------------------------------- il socket del client vero
    def connetti(self, url: str, headers: Dict[str, str]) -> WsBanco:
        """La funzione ``connetti`` da dare a ``PortaCanale`` (stessa firma di
        ``porta_ordini._connetti_ws``). ``giu`` = il canale non risponde:
        solleva come una connessione rifiutata."""
        if self.giu:
            raise ConnectionRefusedError("canale del runner giu' (banco)")
        attore = str(url).rsplit("/", 1)[-1]
        tok = None
        for k, v in (headers or {}).items():
            if str(k).lower() == "x-canale-token":
                tok = v
        ws = WsBanco(self, attore, token_ok=(tok == TOKEN_BANCO))
        self.canale.socket.append(ws)
        self.ultimo_ws = ws
        return ws

    def metti_giu(self) -> None:
        """Il canale cade: i socket aperti si chiudono, i nuovi sono rifiutati."""
        self.giu = True
        for ws in list(self.canale.socket):
            ws.close()
        self.canale.socket.clear()

    def rialza(self) -> None:
        self.giu = False

    def attendi_client(self, timeout_s: float = 2.0) -> bool:
        """Aspetta che il client vero abbia incassato tutto cio' che il motore
        gli ha mandato (determinismo del replay: il bot legge ``esiti`` al giro
        dopo, e deve trovarci cio' che nel vivo sarebbe gia' arrivato)."""
        if self.consegnati == self._consegnati_drenati:
            return True                    # niente di nuovo da quando e' vuoto
        fine = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() < fine:
            if all(ws.svuotato() or ws._chiuso.is_set() for ws in self.canale.socket):
                self._consegnati_drenati = self.consegnati
                return True
            time.sleep(0.0005)
        return False

    def _dal_socket(self, ws: WsBanco, testo: str) -> None:
        """Come ``LocalChannel._on_comando``: busta illeggibile -> ack di
        rifiuto senza seq; altrimenti ``ComandoCanale`` al motore."""
        ricevuto_ms = int(self._orologio()) + int(self.ritardo_ms or 0)
        try:
            msg = json.loads(testo)
            if not isinstance(msg, dict):
                raise ValueError("busta non e' un oggetto")
            tipo = str(msg.get("t") or "")
            d = msg.get("d") if isinstance(msg.get("d"), dict) else {}
        except Exception:  # noqa: BLE001
            ws.consegna({"t": "ack", "d": {"ref": None, "seq": None, "accettato": False,
                                           "motivo": "parametri_invalidi: busta JSON "
                                                     "illeggibile",
                                           "ricevuto_ms": ricevuto_ms}})
            return
        ws.inviati.append({"t": tipo, "d": d})
        if tipo not in ("comando", "da_seq"):
            ws.consegna({"t": "ack", "d": {"ref": d.get("ref"), "seq": None,
                                           "accettato": False,
                                           "motivo": "parametri_invalidi: tipo sconosciuto "
                                                     "%r" % tipo,
                                           "ricevuto_ms": ricevuto_ms}})
            return
        c = ComandoCanale(ws=ws, attore=ws.attore, token_ok=ws.token_ok, tipo=tipo,
                          d=d, ricevuto_ms=ricevuto_ms)
        if tipo == "comando":
            self._registra(c)
        self.motore._gestisci(c)
        self.aggiorna()

    # ----------------------------------------------------------------- interno
    def _registra(self, c: ComandoCanale) -> None:
        d = c.d if isinstance(c.d, dict) else {}
        mid = d.get("market_id")
        if mid:
            self._mercati[str(mid)] = None
        self._sporco = True                # dopo il comando possono esserci ordini nuovi
        if d.get("azione") in ("greenup", "cashout_event", "cashout_all"):
            # il runner puo' piazzare su ALTRI mercati dell'evento: si leggono tutti
            self._tutti_i_mercati = True
        self.comandi.append({"ricevuto_ms": c.ricevuto_ms, "attore": c.attore,
                             "d": dict(d),
                             "t_mercato": (self.orologio_mercato()
                                           if self.orologio_mercato is not None else None)})

    def _incassa(self, msg: Dict[str, Any]) -> None:
        d = msg.get("d") or {}
        if msg.get("t") == "ack" and d.get("ref"):
            self._ack[str(d["ref"])] = dict(d)
        elif msg.get("t") == "order" and d.get("ref"):
            self._eventi.setdefault(str(d["ref"]), []).append(dict(d))

    def _mode_ordine(self, ordine: Any) -> str:
        if self.modo_processo != "LIVE":
            return "paper"
        return "live" if getattr(ordine, "client", None) is self.cliente_live else "paper"

    def _specchio(self) -> None:
        """Lo stream ordini del runner, nel banco: ogni ordine (della strategia,
        sui mercati toccati dai comandi) la cui FIRMA e' cambiata diventa la
        riga dello specchio (``LiveTradingStrategy._order_row``) e va al motore
        (``_su_riga_specchio``), che la trasforma in evento ``order``.

        Costo (25/09): i blotter interi si rileggono solo quando possono essere
        nati ordini nuovi (dopo un comando, durante un place-and-trim); negli
        altri book si rileggono solo gli ordini ancora VIVI. Un ordine chiuso
        (EXECUTION_COMPLETE) e gia' specchiato non cambia piu'."""
        from ..engine.live_trading_strategy import LiveTradingStrategy

        if self._sporco:
            self._sporco = False
            mercati = getattr(getattr(self.framework, "markets", None), "markets", None)
            if isinstance(mercati, dict) and not self._tutti_i_mercati:
                candidati = [mercati.get(m) for m in self._mercati]
            elif isinstance(mercati, dict):
                candidati = list(mercati.values())
            else:
                candidati = list(getattr(self.framework, "markets", []) or [])
            for market in candidati:
                if market is None:
                    continue
                blotter = getattr(market, "blotter", None)
                if blotter is None:
                    continue
                try:
                    ordini = list(blotter.strategy_orders(self.strategia))
                except Exception:  # noqa: BLE001 - blotter inatteso: niente specchio
                    continue
                for o in ordini:
                    chiave = str(getattr(o, "id", id(o)))
                    if chiave not in self._firme:
                        self._vivi[chiave] = (market, o)
        for chiave, (market, o) in list(self._vivi.items()):
            finto_self = SimpleNamespace(mode=self._mode_ordine(o))
            # prima la FIRMA (come ``LiveTradingStrategy.process_orders``:
            # nessuno specchio se niente e' cambiato), poi la riga
            firma = LiveTradingStrategy._order_signature(finto_self, o)
            if self._firme.get(chiave) != firma:
                riga = LiveTradingStrategy._order_row(
                    finto_self, o, event_id=getattr(market, "event_id", None),
                    market_id=getattr(market, "market_id", None))
                if riga is not None:
                    self._firme[chiave] = firma
                    if (chiave not in self.ordini_visti
                            and str(riga.get("client_order_ref") or "").startswith("awlq")):
                        # un ordine nato da un COMANDO (ref interno del motore);
                        # quelli della REST del banco (ripiego D5) no
                        self.ordini_visti[chiave] = o
                        self.ordini_nuovi.append(o)
                    riga["updated_at"] = MO._ora_iso()
                    self.motore._su_riga_specchio(riga)
            stato = getattr(getattr(o, "status", None), "name", None) or str(
                getattr(o, "status", ""))
            if stato == "EXECUTION_COMPLETE" and self._firme.get(chiave) == firma:
                self._vivi.pop(chiave, None)
