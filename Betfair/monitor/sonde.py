"""sonde.py - l'interruttore e gli AGGANCI del modulo "Salute" (T0A, 09/10/2026).

Mandato: ``ARCHITETTURA_2026-10/05_PIANO_DI_MIGRAZIONE.md`` par. 1 T0A (P0210 fase 0).
Contatori IN MEMORIA agganciati ai client DB e Betfair che esistono gia', marche
di tempo additive sui messaggi, una riga ogni 30 s per servizio verso
``monitor_metrics`` scritta da un thread a parte (``scrittore.py``).

INTERRUTTORE ``MONITOR_SALUTE=0|1``, DI SERIE 0. Il monitor e' acceso SOLO se:
  * ``MONITOR_SALUTE=1`` nell'ambiente del processo, E
  * il ``main`` di un servizio ha chiamato ``avvia(<servizio>)``, E
  * nel processo NON e' caricato il banco (``Betfair.stream.backtest*``) e non
    gira pytest (salvo ``_consenti_in_test`` dei test di questo modulo).
Quindi nel banco e' spento PER COSTRUZIONE: il banco non chiama mai un ``main``
di servizio, e anche se lo facesse il controllo sui moduli caricati lo rifiuta.

A monitor spento ogni aggancio e' un ``if _mon.ATTIVO`` falso: nessun campo in
piu', nessuna scrittura, nessun thread, nessun handler di log.

LE MARCHE SONO CAMPI ADDITIVI (``rx`` nel raw, ``ts_pub_ms``/``pt`` nel ladder del
canale, ``emesso_ms`` nei ``params`` della coda, ``ricevuto_ms`` del canale):
nessuno le legge per decidere. Le legge solo la misura (``tempi_ordine.py``
legge ``emesso_ms`` per il tratto ``decisione_ms``, come previsto da F0).

Ogni funzione pubblica e' best-effort: NON solleva MAI verso il chiamante.
ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from typing import Any, Dict, Optional

from .registro import Registro

logger = logging.getLogger(__name__)

ENV = "MONITOR_SALUTE"
ENV_INTERVALLO = "MONITOR_SALUTE_SEC"
INTERVALLO_DEFAULT_S = 30.0

#: True solo dopo un ``avvia`` riuscito (letto dagli agganci come ``_mon.ATTIVO``)
ATTIVO = False

REGISTRO = Registro()

_STATO: Dict[str, Any] = {"servizio": None, "sport": None, "avvio_ms": None,
                          "scrittore": None, "gestori": [], "pid": None}
_LOCK = threading.Lock()
_TLS = threading.local()


# ---------------------------------------------------------------------------
# interruttore
# ---------------------------------------------------------------------------
def interruttore_acceso() -> bool:
    """``MONITOR_SALUTE=1`` nell'ambiente (qualunque altro valore = spento)."""
    return (os.environ.get(ENV) or "0").strip() == "1"


def nel_banco() -> bool:
    """True se nel processo e' caricato il banco di replay."""
    return any(m == "Betfair.stream.backtest" or m.startswith("Betfair.stream.backtest.")
               for m in list(sys.modules))


def in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ


def intervallo_s() -> float:
    raw = (os.environ.get(ENV_INTERVALLO) or "").strip()
    try:
        v = float(raw) if raw else INTERVALLO_DEFAULT_S
    except ValueError:
        v = INTERVALLO_DEFAULT_S
    return v if v >= 1.0 else INTERVALLO_DEFAULT_S


def avvia(servizio: str, sport: Optional[str] = None, *, scrittore: bool = True,
          _consenti_in_test: bool = False, _invia: Any = None,
          _cartella: Optional[str] = None) -> bool:
    """Accende il monitor per questo processo (una volta). Ritorna True se acceso.

    Da chiamare in testa al ``main`` di un servizio, MAI da un modulo condiviso.
    ``_invia``/``_cartella``/``_consenti_in_test`` servono solo ai test."""
    global ATTIVO  # noqa: PLW0603 - interruttore di processo
    try:
        if not interruttore_acceso():
            return False
        if nel_banco():
            logger.info("[monitor] banco caricato nel processo: monitor spento per costruzione")
            return False
        if in_pytest() and not _consenti_in_test:
            return False
        with _LOCK:
            if ATTIVO:
                return True
            _STATO.update({"servizio": str(servizio)[:80], "sport": sport,
                           "avvio_ms": int(time.time() * 1000), "pid": os.getpid()})
            REGISTRO.azzera_tutto()
            _installa_gestori_log()
            ATTIVO = True
        if scrittore:
            from .scrittore import Scrittore

            s = Scrittore(servizio=_STATO["servizio"], sport=sport, intervallo=intervallo_s(),
                          invia=_invia, cartella=_cartella)
            _STATO["scrittore"] = s
            s.start()
        logger.info("[monitor] Salute ACCESO per %s (una riga ogni %.0f s)", servizio,
                    intervallo_s())
        return True
    except Exception as e:  # noqa: BLE001 - la misura non ferma mai un servizio
        logger.warning("[monitor] avvio KO (monitor spento): %s", str(e)[:200])
        ATTIVO = False
        return False


def ferma(attesa_s: float = 2.0) -> None:
    """Spegne il monitor (ultima riga best-effort, handler tolti)."""
    global ATTIVO  # noqa: PLW0603
    try:
        s = _STATO.get("scrittore")
        if s is not None:
            s.ferma(attesa_s)
        with _LOCK:
            ATTIVO = False
            _togli_gestori_log()
            _STATO.update({"scrittore": None, "servizio": None, "sport": None,
                           "avvio_ms": None, "pid": None})
    except Exception:  # noqa: BLE001
        ATTIVO = False


def stato() -> Dict[str, Any]:
    """Chi sono (per lo scrittore e i test)."""
    return {k: v for k, v in _STATO.items() if k not in ("scrittore", "gestori")}


# ---------------------------------------------------------------------------
# primitive (chiamate dagli agganci SOLO dopo ``if _mon.ATTIVO``)
# ---------------------------------------------------------------------------
def ora_ms() -> int:
    return int(time.time() * 1000)


def conta(gruppo: str, chiave: str, n: float = 1) -> None:
    if ATTIVO:
        try:
            REGISTRO.conta(gruppo, chiave, n)
        except Exception:  # noqa: BLE001
            pass


def tratto(nome: str, ms: float) -> None:
    if ATTIVO:
        try:
            REGISTRO.tratto(nome, ms)
        except Exception:  # noqa: BLE001
            pass


def valore(gruppo: str, chiave: str, v: Any) -> None:
    if ATTIVO:
        try:
            REGISTRO.valore(gruppo, chiave, v)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# marche additive
# ---------------------------------------------------------------------------
def ricevuto_ms() -> int:
    """Istante d'arrivo per ``LocalRequest.ricevuto_ms``: 0 a monitor spento."""
    return int(time.time() * 1000) if ATTIVO else 0


def drenate(richieste: Any) -> None:
    """Il worker ha drenato richieste del canale: attesa in coda = ora - ricevuto."""
    if not ATTIVO:
        return
    try:
        adesso = time.time() * 1000.0
        for r in richieste or ():
            REGISTRO.conta("canale_richieste", str(getattr(r, "method", "?"))[:40])
            ric = getattr(r, "ricevuto_ms", 0) or 0
            if ric > 0:
                REGISTRO.tratto("canale_coda_ms", adesso - float(ric))
    except Exception:  # noqa: BLE001
        pass


def marca_ladder(row: Dict[str, Any], book: Any) -> Dict[str, Any]:
    """COPIA della riga del ladder per il CANALE con ``ts_pub_ms`` e ``pt``.

    Mai la riga originale: la stessa riga va anche a ``live_ladder`` (upsert con
    le colonne della tabella) e un campo in piu' romperebbe la scrittura."""
    if not ATTIVO:
        return row
    try:
        ts = int(time.time() * 1000)
        out = dict(row)
        out["ts_pub_ms"] = ts
        pt = book.get("pt") if isinstance(book, dict) else None
        if isinstance(pt, (int, float)) and not isinstance(pt, bool) and pt > 0:
            out["pt"] = int(pt)
            REGISTRO.tratto("ladder_pub_pt_ms", ts - float(pt))
        REGISTRO.conta("ladder", "pubblicati_canale")
        return out
    except Exception:  # noqa: BLE001
        return row


def marca_emesso(params: Dict[str, Any]) -> Dict[str, Any]:
    """``emesso_ms`` (istante in cui il bot emette il comando) nei ``params`` della
    coda: lo legge ``tempi_ordine`` per ``decisione_ms``. A monitor spento il dict
    torna identico."""
    if ATTIVO and isinstance(params, dict):
        try:
            params["emesso_ms"] = int(time.time() * 1000)
            REGISTRO.conta("ordini_emessi", str(params.get("source") or "?")[:30])
        except Exception:  # noqa: BLE001
            pass
    return params


# ---------------------------------------------------------------------------
# stream Betfair: messaggi, eta' del dato, connectionsAvailable
# ---------------------------------------------------------------------------
_RE_PT = re.compile(r'"pt"\s*:\s*(\d+)')
_RE_OP_STATUS = re.compile(r'"op"\s*:\s*"status"')


def osserva_stream(sorgente: str, raw_data: Any) -> None:
    """Un messaggio grezzo dello stream (dal ``on_data`` del listener).

    mcm: conteggio + ``rx - pt`` (eta' del messaggio all'arrivo, orologio del PC
    contro quello di Betfair: include lo scarto dell'orologio). status: il
    ``connectionsAvailable`` (anche lo 0, che betfairlightweight non salva) e
    l'esito. Lettura della sola testa del messaggio (nessun ``json.loads`` sui
    mcm)."""
    if not ATTIVO or not isinstance(raw_data, str):
        return
    try:
        rx = time.time() * 1000.0
        testa = raw_data[:240]
        if '"mcm"' in testa:
            REGISTRO.conta("stream_msg", sorgente)
            m = _RE_PT.search(testa)
            if m:
                eta = rx - float(m.group(1))
                # il MINIMO di finestra di questo tratto e' il limite superiore
                # dello scarto dell'orologio del PC (scarto + latenza minima)
                REGISTRO.tratto("feed_rx_pt_ms." + sorgente, eta)
            return
        if _RE_OP_STATUS.search(testa):
            _osserva_status(sorgente, raw_data)
            return
        REGISTRO.conta("stream_altri", sorgente)
    except Exception:  # noqa: BLE001 - la misura non rompe mai lo stream
        pass


def _osserva_status(sorgente: str, raw_data: str) -> None:
    import json

    d = json.loads(raw_data)
    esito = str(d.get("statusCode") or "?")
    errore = d.get("errorCode")
    REGISTRO.conta("stream_status", f"{sorgente} {esito}{(' ' + str(errore)) if errore else ''}")
    disp = d.get("connectionsAvailable")
    if isinstance(disp, int) and not isinstance(disp, bool):
        REGISTRO.valore("connessioni_disponibili", sorgente, disp)
        REGISTRO.valore("connessioni_lette_ms", sorgente, int(time.time() * 1000))


# ---------------------------------------------------------------------------
# client DB (httpx del PostgREST di supabase-py)
# ---------------------------------------------------------------------------
_MARCA_GANCIO = "_monitor_salute"


def _tabella_di(path: str) -> str:
    p = path.split("/rest/v1/", 1)
    if len(p) < 2:
        return path[:40] or "?"
    resto = p[1]
    if resto.startswith("rpc/"):
        return "rpc:" + resto[4:].split("/", 1)[0][:60]
    return resto.split("/", 1)[0].split("?", 1)[0][:60]


def _db_richiesta(request: Any) -> None:
    try:
        _TLS.db_t0 = time.perf_counter()
        _TLS.db_chiave = f"{request.method} {_tabella_di(str(request.url.path))}"
        REGISTRO.conta("db", _TLS.db_chiave)
    except Exception:  # noqa: BLE001
        pass


def _db_risposta(response: Any) -> None:
    try:
        t0 = getattr(_TLS, "db_t0", None)
        if t0 is not None:
            REGISTRO.tratto("db_ms", (time.perf_counter() - t0) * 1000.0)
            _TLS.db_t0 = None
        st = int(getattr(response, "status_code", 0) or 0)
        if st >= 400:
            REGISTRO.conta("db_errori", f"{st} {getattr(_TLS, 'db_chiave', '?')}")
    except Exception:  # noqa: BLE001
        pass


setattr(_db_richiesta, _MARCA_GANCIO, True)
setattr(_db_risposta, _MARCA_GANCIO, True)


def aggancia_client_db(client: Any) -> Any:
    """Conta le richieste PostgREST del client (hook di httpx, come il contatore
    di rinnovo di ``db_client._installa_contatore``). Idempotente. Ritorna il
    client (lo stesso oggetto)."""
    if not ATTIVO or client is None:
        return client
    try:
        hooks = client.postgrest.session.event_hooks
        if any(getattr(f, _MARCA_GANCIO, False) for f in hooks.get("request", [])):
            return client
        hooks["request"].append(_db_richiesta)
        hooks["response"].append(_db_risposta)
    except Exception:  # noqa: BLE001 - client finti o versioni diverse: niente conteggio
        pass
    return client


# ---------------------------------------------------------------------------
# client Betfair (requests.Session dell'APIClient di betfairlightweight)
# ---------------------------------------------------------------------------
_RE_METODO = re.compile(r'"method"\s*:\s*"([^"]+)"')


def _metodo_betfair(resp: Any) -> str:
    req = getattr(resp, "request", None)
    url = str(getattr(req, "url", "") or "")
    if "certlogin" in url:
        return "certlogin"
    if "/api/login" in url:
        return "login"
    if "keepAlive" in url:
        return "keepAlive"
    if "logout" in url:
        return "logout"
    corpo = getattr(req, "body", None)
    if isinstance(corpo, bytes):
        corpo = corpo[:240].decode("ascii", "replace")
    if isinstance(corpo, str):
        m = _RE_METODO.search(corpo[:240])
        if m:
            return m.group(1).rsplit("/", 1)[-1][:40]
    return "altro"


def _bf_risposta(resp: Any, *args: Any, **kwargs: Any) -> None:
    try:
        metodo = _metodo_betfair(resp)
        REGISTRO.conta("betfair_rest", metodo)
        el = getattr(resp, "elapsed", None)
        if el is not None:
            REGISTRO.tratto("rest_ms." + metodo, el.total_seconds() * 1000.0)
        st = int(getattr(resp, "status_code", 0) or 0)
        if st >= 400:
            REGISTRO.conta("betfair_rest_errori", f"{st} {metodo}")
    except Exception:  # noqa: BLE001
        pass
    return None


setattr(_bf_risposta, _MARCA_GANCIO, True)


def aggancia_client_betfair(client: Any) -> Any:
    """Conta le chiamate REST (login, keepAlive, metodi JSON-RPC) della sessione
    HTTP dell'APIClient. Gli ordini di flumine passano da sessioni sue: quelli si
    contano dal log di ``flumine.execution`` (vedi ``_GestoreEsecuzione``)."""
    if not ATTIVO or client is None:
        return client
    try:
        sess = getattr(client, "session", None)
        hooks = getattr(sess, "hooks", None)
        if not isinstance(hooks, dict):
            return client
        lista = hooks.setdefault("response", [])
        if not isinstance(lista, list):
            lista = hooks["response"] = [lista]
        if not any(getattr(f, _MARCA_GANCIO, False) for f in lista):
            lista.append(_bf_risposta)
    except Exception:  # noqa: BLE001
        pass
    return client


# ---------------------------------------------------------------------------
# handler di log (letture di cio' che le librerie GIA' registrano: zero agganci)
# ---------------------------------------------------------------------------
class _Gestore(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - sovrascritto
        pass

    def handleError(self, record: logging.LogRecord) -> None:  # noqa: N802
        pass  # la misura non scrive mai tracce d'errore nel log del servizio


class _GestoreLatenzaFlumine(_Gestore):
    """``flumine.baseflumine``: "High latency between current time and
    MarketBook publish time" (> 2 s) con ``extra={"latency": s}``. Oggi il
    formato del log dei runner non stampa ``extra``: il valore andava perso."""

    def emit(self, record: logging.LogRecord) -> None:
        lat = getattr(record, "latency", None)
        if isinstance(lat, (int, float)):
            REGISTRO.tratto("flumine_latenza_alta_ms", float(lat) * 1000.0)


class _GestoreEsecuzione(_Gestore):
    """``flumine.execution``: ``execute_<place|cancel|update|replace>`` con
    ``elapsed_time`` e ``order_package`` (``order_count``). Dal logger si sa se
    e' Betfair vero (``betfairexecution``) o simulato (paper): MAI sommati."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg if isinstance(record.msg, str) else ""
        live = record.name.endswith("betfairexecution")
        pacchetto = getattr(record, "order_package", None)
        n = 1
        if isinstance(pacchetto, dict):
            try:
                n = int(pacchetto.get("order_count") or 1)
            except (TypeError, ValueError):
                n = 1
        if msg.startswith("execute_"):
            fn = msg[len("execute_"):][:20]
            gruppo = "esecuzione_live" if live else "esecuzione_paper"
            REGISTRO.conta(gruppo, fn, n)
            el = getattr(record, "elapsed_time", None)
            if live and isinstance(el, (int, float)):
                REGISTRO.tratto("betfair_" + fn + "_ms", float(el) * 1000.0)
            if live and fn in ("place", "replace"):
                REGISTRO.conta("transazioni", fn, n)
        elif msg.startswith("High latency between current time and OrderPackage"):
            lat = getattr(record, "latency", None)
            if isinstance(lat, (int, float)):
                REGISTRO.tratto("pacchetto_attesa_ms", float(lat) * 1000.0)
        elif msg.startswith("Execution error"):
            REGISTRO.conta("esecuzione_errori", "live" if live else "paper", n)
            if live:
                tipo = (pacchetto or {}).get("package_type") if isinstance(pacchetto, dict) else None
                if tipo in ("Place", "Replace"):
                    REGISTRO.conta("transazioni", "fallite", n)


class _GestoreStatoStream(_Gestore):
    """``betfairlightweight.streaming.listener``: "[stream: id]: SUCCESS (N
    connections available)". Ripiego per i processi senza listener nostro
    (sessioni dello scalper): betfairlightweight non salva lo 0, quindi con 0
    qui si legge il valore PRECEDENTE (dichiarato nel referto)."""

    def emit(self, record: logging.LogRecord) -> None:
        a = record.args
        if not isinstance(a, tuple) or len(a) != 4 or record.msg != "[%s: %s]: %s (%s connections available)":
            return
        REGISTRO.conta("stream_status_log", str(a[2])[:30])
        if isinstance(a[3], int) and not isinstance(a[3], bool):
            REGISTRO.valore("connessioni_disponibili_log", f"stream-{a[1]}", a[3])


class _GestoreAvviiStream(_Gestore):
    """``flumine.streams``: "Starting MarketStream/OrderStream ..." a ogni
    (ri)connessione."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.msg if isinstance(record.msg, str) else ""
        if msg.startswith("Starting ") and "Stream" in msg:
            REGISTRO.conta("stream_avvii", msg.split()[1][:30])


class _GestoreErrori(_Gestore):
    """Radice: ERROR e CRITICAL per logger (solo il conteggio)."""

    def emit(self, record: logging.LogRecord) -> None:
        REGISTRO.conta("log_errori", f"{record.levelname} {record.name[:60]}")


_GESTORI = (
    ("flumine.baseflumine", _GestoreLatenzaFlumine, logging.WARNING),
    ("flumine.execution", _GestoreEsecuzione, logging.INFO),
    ("betfairlightweight.streaming.listener", _GestoreStatoStream, logging.INFO),
    ("flumine.streams", _GestoreAvviiStream, logging.INFO),
    ("", _GestoreErrori, logging.ERROR),
)


def _installa_gestori_log() -> None:
    """Aggiunge gli handler (nessun livello di logger cambiato: si legge solo
    cio' che il processo registra gia')."""
    _togli_gestori_log()
    for nome, cls, livello in _GESTORI:
        h = cls(level=livello)
        logging.getLogger(nome).addHandler(h)
        _STATO["gestori"].append((nome, h))


def _togli_gestori_log() -> None:
    for nome, h in list(_STATO.get("gestori") or []):
        try:
            logging.getLogger(nome).removeHandler(h)
        except Exception:  # noqa: BLE001
            pass
    _STATO["gestori"] = []
