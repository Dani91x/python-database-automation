"""registratore_canale.py - il REGISTRATORE del canale locale (M-3, 11/10/2026).

Mandato: mappatura dei flussi reali per la v2 (``ARCHITETTURA_2026-10/mappa/
M3_CANALE_E_MAPPA.md``). Registra, per ogni processo che ha un canale locale
(``local_channel.py``, ws su 127.0.0.1: 47331 calcio, 47332 tennis, 47333 Mike,
47334 Omega, 47335 Safe, 47336 scanner, 47337 bot tennis, ...), che cosa passa
sul canale:

  * ogni messaggio PUBBLICATO (``publish`` -> giro ``_broadcast``): istante
    monotono ed epoca, porta e sport del processo, topic, byte, destinatari,
    client saltati per contropressione (oltre ``_MAX_INVII_IN_VOLO``), client e
    lettori collegati, sequenza; a ogni cambio dei client collegati anche la
    COMPOSIZIONE (chi riceve);
  * ogni giro SALTATO per intero (nessun client pronto);
  * ogni messaggio RICEVUTO da un client (comandi della UI, ``/comando/``,
    sveglie, richieste di sola lettura) e ogni RISPOSTA del canale (``respond``,
    ``_send``, ``invia``, ``invia_attore``): sono l'esito dei comandi.

PAYLOAD COMPLETO solo per i topic che servono alla v2 (``PIENI``: order, esiti,
conto, conto_paper, modo_ordini), per i messaggi ricevuti e per le risposte.
Per tutti gli altri topic (ladder, board, board_mercato, now, ...) il payload
si salva a CAMPIONE: il primo e poi 1 ogni ``N`` per topic e per porta
(``REGISTRA_CANALE_CAMPIONE``, di serie 20). I metadati si scrivono SEMPRE.
Il payload si scrive VERBATIM: e' il testo JSON che il canale ha gia'
serializzato per i client, mai riletto e riscritto (11/10, revisione: il
``json.loads``/``json.dumps`` dei payload pieni teneva il GIL e portava il p99
del loop del canale da 1,8 a 27 ms).

INTERRUTTORE ``REGISTRA_CANALE=0|1``, DI SERIE 0 (come ``MONITOR_SALUTE`` di
``Betfair/monitor/sonde.py``). Acceso solo se ``=1`` nell'ambiente del processo
(o, se l'ambiente non lo nomina, nel ``.env`` della radice, letto e MAI caricato)
E nel processo non gira pytest (salvo ``accendi(_consenti_in_test=True)``) E
non e' caricato il banco (``Betfair.stream.backtest*``, controllato anche al
primo record). Spento: ogni aggancio di ``local_channel`` e' un
``if _reg.ATTIVO`` falso, nessun file, nessun thread.

PERCORSO CALDO. Gli agganci NON scrivono su disco: mettono una tupla di
riferimenti (il testo JSON gia' serializzato, immutabile) in una ``deque`` con
un tetto in RECORD (``CODA_MAX``) e in BYTE (``CODA_MAX_BYTE``). Coda piena = il
record si SCARTA e si CONTA (``scartati_coda``), mai si aspetta. Il conto dei
byte e i contatori stanno sotto un lucchetto tenuto per qualche istruzione
(mai durante un I/O). La sequenza si assegna PRIMA del controllo della coda:
un buco nella sequenza del file e' un record scartato, e la mappa lo vede.

SCRITTURA. UN thread demone per processo (``registratore-canale``) drena la
coda, maschera i dati sensibili SUL TESTO e scrive JSONL compresso in
``<cartella>/<AAAA-MM-GG>/canale_<porta>_<pid>[_<n>].jsonl.gz``: un file per
processo e per giorno, creato in esclusiva (``xb``), MAI un append su un file
esistente (un pid riusato, o la riapertura dopo un errore, prende il suffisso
libero dopo). Ogni 5 s un flush del gzip; ogni 30 s una riga ``stato``; alla
fine del processo (``atexit``, con un'attesa massima: l'uscita non si appende
mai al registratore) una riga ``chiusura`` e la chiusura del gzip. Nel figlio di
un ``fork`` il registratore e' chiuso e i file ereditati sono dirottati su
``devnull`` (il figlio non deve mai scrivere nel gzip del padre). Rotazione a
mezzanotte (data LOCALE). TETTO in MB sull'intera cartella
(``REGISTRA_CANALE_MB``, di serie 1024) e conservazione in giorni
(``REGISTRA_CANALE_GIORNI``, di serie 7): oltre il tetto si cancellano i giorni
piu' vecchi (mai quello di oggi), e se oggi da solo supera il tetto la scrittura
si SOSPENDE fino a domani (``scartati_tetto``). Con un file per processo il
tetto e' controllato da ogni processo per conto suo: fra processi e' best-effort
(due processi possono sforarlo insieme di quanto scrivono in 30 s). Errori del
disco: contati (``errori_disco``), un avviso ogni 10 minuti, MAI propagati.

DATI SENSIBILI. Il token del canale viaggia nel percorso della connessione
(``?t=``) e nell'header ``X-Canale-Token``: il registratore NON legge mai ne'
percorso ne' header. Nei payload si mascherano (``"***"``) i valori delle chiavi
ESATTE di ``SENSIBILI`` (maiuscole e minuscole indifferenti, a qualunque
profondita', anche dentro le liste) e di ``SENSIBILI_CORTE`` (``t``, ``tk``)
quando il valore e' un testo di almeno 16 caratteri (``t`` e' anche il campo
del protocollo: ``{"t": "ladder"}`` resta). Il numero di mascherature e' nella
riga ``stato``.

Ogni funzione pubblica e' best-effort: NON solleva MAI verso il chiamante.
Nessuna connessione, nessun processo: un solo thread, acceso solo a interruttore
acceso e al primo record. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import atexit
import collections
import gzip
import itertools
import json
import logging
import os
import re
import sys
import threading
import time
import weakref
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENV = "REGISTRA_CANALE"
ENV_CARTELLA = "REGISTRA_CANALE_DIR"
ENV_TETTO_MB = "REGISTRA_CANALE_MB"
ENV_CAMPIONE = "REGISTRA_CANALE_CAMPIONE"
ENV_GIORNI = "REGISTRA_CANALE_GIORNI"

#: versione del formato delle righe (la mappa la legge)
VERSIONE = 2
#: topic con il payload SEMPRE completo (servono alla v2)
PIENI = frozenset({"order", "esiti", "conto", "conto_paper", "modo_ordini"})
CAMPIONE_DEFAULT = 20
TETTO_MB_DEFAULT = 1024.0
GIORNI_DEFAULT = 7
#: record in coda oltre i quali si scarta
CODA_MAX = 20000
#: byte di testo in coda oltre i quali si scarta (memoria limitata anche con
#: payload pieni grandi)
CODA_MAX_BYTE = 32 * 1024 * 1024
#: peso fisso stimato di un record (tupla e metadati) nel conto dei byte
PESO_RECORD = 200
FLUSH_OGNI_S = 5.0
STATO_OGNI_S = 30.0
TETTO_OGNI_S = 30.0
AVVISO_OGNI_S = 600.0
#: il thread di scrittura cede il GIL ogni tanti byte composti o scritti
CEDI_OGNI_BYTE = 32 * 1024
#: attesa massima del thread di scrittura a fine processo (atexit)
ATTESA_USCITA_S = 2.0
PREFISSO_FILE = "canale_"
SUFFISSO_FILE = ".jsonl.gz"

#: chiavi mascherate (confronto ESATTO, maiuscole indifferenti)
SENSIBILI = frozenset({
    "key", "x-authentication", "x-application", "token", "session_token", "sessiontoken",
    "password", "passwd", "authorization", "app_key", "appkey", "api_key", "apikey",
    "ssoid", "cookie", "secret", "client_secret",
})
#: chiavi corte mascherate solo se il valore e' un testo di almeno 16 caratteri
SENSIBILI_CORTE = frozenset({"t", "tk"})
MIN_CORTE = 16

RADICE_REPO = Path(__file__).resolve().parents[2]

#: True solo dopo un ``accendi`` riuscito (letto dagli agganci come ``_reg.ATTIVO``)
ATTIVO = False

_LOCK = threading.Lock()            # accensione, avvio del thread
_LOCK_CONTI = threading.Lock()      # contatori e conto dei byte: poche istruzioni
_CODA: "collections.deque" = collections.deque()
_SEQ = itertools.count(1)
_CONTI: Dict[str, int] = {"scartati_coda": 0, "scartati_tetto": 0, "errori_disco": 0,
                          "errori_aggancio": 0, "scritti": 0, "mascherati": 0,
                          "giorni_rimossi": 0, "peso_cartella_byte": 0, "byte_in_coda": 0}
#: (porta, topic) -> quanti publish visti (per il campione 1 ogni N). Solo il
#: thread del loop del canale lo tocca.
_VISTI: Dict[Tuple[int, str], int] = {}
#: numero del client assegnato alla CONNESSIONE (mai riusato nel processo)
_NUMERI: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_NUMERI_ID: Dict[int, int] = {}      # ripiego per oggetti senza weakref
_PROSSIMO_CLIENTE = itertools.count(1)
#: porta -> numeri dei client collegati all'ultimo giro (cambia = composizione)
_FIRME: Dict[int, Tuple[int, ...]] = {}
_CONF: Dict[str, Any] = {"cartella": None, "tetto_mb": TETTO_MB_DEFAULT,
                         "campione": CAMPIONE_DEFAULT, "giorni": GIORNI_DEFAULT,
                         "coda_max": CODA_MAX, "coda_max_byte": CODA_MAX_BYTE,
                         "pid": None, "av": None}
_STATO: Dict[str, Any] = {"thread": None, "max_in_volo": None, "chiuso": False,
                          "atexit": False}

# tipi di record (prima voce della tupla in coda)
_PUB = "pub"
_SALTO = "giro_saltato"
_RX = "rx"
_TX = "tx"


# ---------------------------------------------------------------------------
# interruttore
# ---------------------------------------------------------------------------
def leggi_file_env(percorso: Optional[Path] = None) -> Dict[str, str]:
    """Le coppie ``CHIAVE=valore`` del ``.env`` della radice, SOLO lette: niente
    entra in ``os.environ`` (caricarlo qui cambierebbe l'ambiente del processo).
    Serve perche' l'interruttore si legge all'import di ``local_channel``, che
    in alcuni servizi avviene prima del loro ``load_dotenv``. Mai solleva."""
    out: Dict[str, str] = {}
    try:
        p = Path(percorso) if percorso is not None else RADICE_REPO / ".env"
        if not p.is_file():
            return out
        for riga in p.read_text(encoding="utf-8", errors="replace").splitlines():
            riga = riga.strip()
            if not riga or riga.startswith("#") or "=" not in riga:
                continue
            if riga.startswith("export "):
                riga = riga[len("export "):].strip()
            k, v = riga.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            elif " #" in v:
                v = v.split(" #", 1)[0].strip()
            out[k.strip()] = v
    except Exception:  # noqa: BLE001 - .env illeggibile: come se non ci fosse
        return {}
    return out


def valore_env(nome: str, file_env: Optional[Path] = None) -> str:
    """L'ambiente vero ha la precedenza; poi il ``.env`` della radice."""
    v = os.environ.get(nome)
    if v is not None:
        return v
    return leggi_file_env(file_env).get(nome, "")


def interruttore_acceso(file_env: Optional[Path] = None) -> bool:
    """``REGISTRA_CANALE=1`` nell'ambiente o nel ``.env`` (qualunque altro valore
    = spento)."""
    return (valore_env(ENV, file_env) or "0").strip() == "1"


def nel_banco() -> bool:
    """True se nel processo e' caricato il banco di replay."""
    return any(m == "Betfair.stream.backtest" or m.startswith("Betfair.stream.backtest.")
               for m in list(sys.modules))


def in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _num_env(nome: str, difetto: float, minimo: float) -> float:
    raw = (valore_env(nome) or "").strip()
    try:
        v = float(raw) if raw else difetto
    except ValueError:
        v = difetto
    return v if v >= minimo else difetto


def cartella_base(base: Optional[str] = None) -> Path:
    if base:
        return Path(base)
    env = (valore_env(ENV_CARTELLA) or "").strip()
    return Path(env) if env else RADICE_REPO / "_logs" / "canale"


def accendi(*, cartella: Optional[str] = None, tetto_mb: Optional[float] = None,
            campione: Optional[int] = None, giorni: Optional[int] = None,
            coda_max: Optional[int] = None, coda_max_byte: Optional[int] = None,
            _consenti_in_test: bool = False, _senza_thread: bool = False) -> bool:
    """Accende il registratore per questo processo. Ritorna True se acceso.

    Chiamato da solo all'import se ``REGISTRA_CANALE=1`` (vedi in fondo). I
    parametri con ``_`` servono solo ai test: ``_senza_thread`` lascia i record
    in coda (li scrive ``scrivi_ora``), per provare coda piena e scarti."""
    global ATTIVO  # noqa: PLW0603 - interruttore di processo
    try:
        if not interruttore_acceso() and not _consenti_in_test:
            return False
        if nel_banco():
            logger.info("[reg-canale] banco caricato nel processo: registratore spento")
            return False
        if in_pytest() and not _consenti_in_test:
            return False
        with _LOCK:
            _CONF.update({
                "cartella": cartella_base(cartella),
                "tetto_mb": float(tetto_mb) if tetto_mb is not None
                else _num_env(ENV_TETTO_MB, TETTO_MB_DEFAULT, 1.0),
                "campione": int(campione) if campione is not None
                else int(_num_env(ENV_CAMPIONE, CAMPIONE_DEFAULT, 1)),
                "giorni": int(giorni) if giorni is not None
                else int(_num_env(ENV_GIORNI, GIORNI_DEFAULT, 1)),
                "coda_max": int(coda_max) if coda_max is not None else CODA_MAX,
                "coda_max_byte": int(coda_max_byte) if coda_max_byte is not None
                else CODA_MAX_BYTE,
                "pid": os.getpid(),
                # la VITA del processo: (pid, avvio) distingue due processi con
                # lo stesso pid (Windows lo riusa) nella mappa
                "av": int(time.time() * 1000),
                "senza_thread": bool(_senza_thread),
            })
            _STATO["chiuso"] = False
            ATTIVO = True
        logger.info("[reg-canale] registratore del canale ACCESO in %s (tetto %.0f MB, "
                    "campione 1/%d)", _CONF["cartella"], _CONF["tetto_mb"], _CONF["campione"])
        return True
    except Exception as e:  # noqa: BLE001 - il registratore non ferma mai un servizio
        logger.warning("[reg-canale] accensione KO (registratore spento): %s", str(e)[:200])
        ATTIVO = False
        return False


def spegni(attesa_s: float = 3.0) -> None:
    """Spegne il registratore: il thread scrive quello che resta, la riga di
    chiusura, e chiude i file."""
    global ATTIVO  # noqa: PLW0603
    try:
        ATTIVO = False
        t = _STATO.get("thread")
        if t is not None:
            t.ferma(attesa_s)
        _STATO["thread"] = None
    except Exception:  # noqa: BLE001
        ATTIVO = False


def _all_uscita() -> None:
    """``atexit``: svuota e chiude con un'attesa MASSIMA (l'uscita del processo
    non si appende mai al registratore: se il disco e' appeso si rinuncia)."""
    try:
        t = _STATO.get("thread")
        if t is not None and t.is_alive():
            t.ferma(ATTESA_USCITA_S)
    except Exception:  # noqa: BLE001
        pass


def _nel_figlio() -> None:
    """``fork``: nel figlio il registratore e' CHIUSO (nessun thread, coda vuota)
    e i file ereditati sono dirottati su ``devnull``: alla sua uscita il figlio
    non scrive mai nel gzip del padre (buffer duplicati, trailer)."""
    global ATTIVO  # noqa: PLW0603
    ATTIVO = False
    _STATO["chiuso"] = True
    t = _STATO.get("thread")
    _STATO["thread"] = None
    _CODA.clear()
    try:
        file_aperti = list(getattr(t, "_file", {}).values()) if t is not None else []
        if file_aperti:
            nul = os.open(os.devnull, os.O_WRONLY)
            try:
                for fh in file_aperti:
                    try:
                        os.dup2(nul, fh.fileobj.fileno())
                    except Exception:  # noqa: BLE001
                        pass
            finally:
                os.close(nul)
    except Exception:  # noqa: BLE001
        pass


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_nel_figlio)


def _conta(chiave: str, n: int = 1) -> None:
    with _LOCK_CONTI:
        _CONTI[chiave] += n


def conti() -> Dict[str, int]:
    """Copia dei contatori (per i test e per le righe ``stato``). ``seq_prossimo``
    = il numero che avra' il prossimo record: la mappa ci vede anche i record
    scartati DOPO l'ultimo scritto."""
    with _LOCK_CONTI:
        c = dict(_CONTI)
    c["in_coda"] = len(_CODA)
    c["seq_prossimo"] = _seq_prossimo()
    return c


def _seq_prossimo() -> int:
    """Legge il contatore senza consumarlo (``repr`` di ``itertools.count``:
    ``count(N)``). 0 = illeggibile."""
    try:
        return int(repr(_SEQ)[len("count("):-1])
    except ValueError:
        return 0


def azzera_per_test() -> None:
    """Solo per i test: coda, contatori, campioni e clienti da capo."""
    global _SEQ, _PROSSIMO_CLIENTE  # noqa: PLW0603
    _CODA.clear()
    with _LOCK_CONTI:
        for k in _CONTI:
            _CONTI[k] = 0
    _VISTI.clear()
    _NUMERI.clear()
    _NUMERI_ID.clear()
    _FIRME.clear()
    _SEQ = itertools.count(1)
    _PROSSIMO_CLIENTE = itertools.count(1)
    _STATO["chiuso"] = False


# ---------------------------------------------------------------------------
# agganci (chiamati da local_channel SOLO dopo ``if _reg.ATTIVO``). Mai sollevano.
# ---------------------------------------------------------------------------
def _accoda(rec: tuple, peso: int) -> None:
    """Coda limitata in record e in byte: se piena si scarta e si conta, MAI si
    aspetta (il lucchetto copre solo il conto, mai un I/O)."""
    with _LOCK_CONTI:
        if _STATO["chiuso"]:
            return
        if (len(_CODA) >= _CONF["coda_max"]
                or _CONTI["byte_in_coda"] + peso > _CONF["coda_max_byte"]):
            _CONTI["scartati_coda"] += 1
            return
        _CONTI["byte_in_coda"] += peso
        _CODA.append(rec)
    if _STATO["thread"] is None and not _CONF.get("senza_thread"):
        _avvia_thread()


def _max_in_volo() -> int:
    v = _STATO["max_in_volo"]
    if v is None:
        from . import local_channel as _lc  # import pigro: niente ciclo all'import
        v = _STATO["max_in_volo"] = int(_lc._MAX_INVII_IN_VOLO)
    return v


def _cliente(ws: Any) -> int:
    """Numero della CONNESSIONE, assegnato alla prima vista e mai riusato nel
    processo (un socket nuovo ha sempre un numero nuovo, anche se Python ne
    riusa l'``id``)."""
    try:
        n = _NUMERI.get(ws)
        if n is None:
            with _LOCK_CONTI:
                n = _NUMERI.get(ws)
                if n is None:
                    n = _NUMERI[ws] = next(_PROSSIMO_CLIENTE)
        return n
    except TypeError:   # oggetto senza weakref: ripiego per id (solo finti)
        k = id(ws)
        with _LOCK_CONTI:
            n = _NUMERI_ID.get(k)
            if n is None:
                if len(_NUMERI_ID) > 100000:
                    _NUMERI_ID.clear()
                n = _NUMERI_ID[k] = next(_PROSSIMO_CLIENTE)
        return n


def _genere(ch: Any, ws: Any) -> Tuple[str, Any]:
    """Che client e': ``comando`` (con l'attore), ``lettore`` (con i topic) o
    ``desktop``. Mai il percorso ne' gli header (portano il token)."""
    cw = getattr(ch, "_comando_ws", {}).get(ws)
    if cw is not None:
        return "comando", str(cw[0])[:40]
    f = getattr(ch, "_lettori", {}).get(ws)
    if f is not None:
        return "lettore", ",".join(sorted(f))[:200]
    return "desktop", None


def pubblicato(ch: Any, topic: str, text: str) -> None:
    """Giro di broadcast (thread del loop, PRIMA del ciclo di invio): conta i
    destinatari e i saltati con la STESSA regola di ``_broadcast``. Il ciclo di
    invio non cede mai il loop, quindi lo stato letto qui e' quello che il
    ciclo vedra'.

    Quando cambia l'insieme delle CONNESSIONI collegate (una che si apre, una che
    si chiude, una che si ricollega) il record porta anche la COMPOSIZIONE:
    ``[cliente, genere, chi]`` per ognuna. E' il "chi riceve"."""
    try:
        seq = next(_SEQ)
        mono, epoca = time.monotonic_ns(), time.time_ns()
        massimo = _max_in_volo()
        lettori, in_volo = ch._lettori, ch._in_volo_ws
        dest = salt = 0
        clienti = list(ch._clients)
        for w in clienti:
            f = lettori.get(w)
            if f is not None and topic not in f:
                continue
            if in_volo.get(w, 0) > massimo:
                salt += 1
                continue
            dest += 1
        numeri = tuple(sorted(_cliente(w) for w in clienti))
        comp = None
        if _FIRME.get(ch.port) != numeri:
            _FIRME[ch.port] = numeri
            comp = sorted([_cliente(w), *_genere(ch, w)] for w in clienti)
        chiave = (ch.port, topic)
        n = _VISTI.get(chiave, 0) + 1
        _VISTI[chiave] = n
        pieno = topic in PIENI
        tieni = pieno or _CONF["campione"] == 1 or (n % _CONF["campione"] == 1)
        _accoda((_PUB, seq, mono, epoca, ch.port, ch.sport, topic, len(text),
                 text if tieni else None, "pieno" if pieno else ("campione" if tieni else None),
                 dest, salt, ch._n_clients, ch._n_lettori, n, comp),
                PESO_RECORD + (len(text) if tieni else 0))
    except Exception:  # noqa: BLE001 - un record perso non ferma il canale
        _conta("errori_aggancio")


def giro_saltato(ch: Any, topic: str) -> None:
    """Giro saltato per intero (nessun client pronto). Thread del chiamante."""
    try:
        seq = next(_SEQ)
        _accoda((_SALTO, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 topic, ch._n_clients, ch._n_lettori, ch._in_volo), PESO_RECORD)
    except Exception:  # noqa: BLE001
        _conta("errori_aggancio")


def ricevuto(ch: Any, ws: Any, raw: Any) -> None:
    """Messaggio arrivato da un client (thread del loop), payload completo."""
    try:
        seq = next(_SEQ)
        genere, chi = _genere(ch, ws)
        n = len(raw) if isinstance(raw, (str, bytes, bytearray)) else 0
        _accoda((_RX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 _cliente(ws), genere, chi, n, raw), PESO_RECORD + n)
    except Exception:  # noqa: BLE001
        _conta("errori_aggancio")


def risposta(ch: Any, ws: Any, text: str, via: str) -> None:
    """Risposta MIRATA a un client (esito di un comando), payload completo."""
    try:
        seq = next(_SEQ)
        genere, chi = _genere(ch, ws)
        _accoda((_TX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 _cliente(ws), genere, chi, len(text), text, via), PESO_RECORD + len(text))
    except Exception:  # noqa: BLE001
        _conta("errori_aggancio")


def risposta_attore(ch: Any, attore: str, text: str) -> None:
    """Invio a tutti i socket di comando di un attore (``invia_attore``)."""
    try:
        seq = next(_SEQ)
        _accoda((_TX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 None, "comando", str(attore)[:40], len(text), text, "invia_attore"),
                PESO_RECORD + len(text))
    except Exception:  # noqa: BLE001
        _conta("errori_aggancio")


def _peso(rec: tuple) -> int:
    """Lo stesso peso calcolato all'accodamento (per scalarlo al drenaggio)."""
    tipo = rec[0]
    if tipo == _PUB:
        return PESO_RECORD + (rec[7] if rec[8] is not None else 0)
    if tipo == _SALTO:
        return PESO_RECORD
    return PESO_RECORD + int(rec[9] or 0)


# ---------------------------------------------------------------------------
# dati sensibili: mascheratura SUL TESTO (niente loads/dumps)
# ---------------------------------------------------------------------------
_ALT = "|".join(re.escape(k) for k in sorted(SENSIBILI, key=len, reverse=True))
#: chiave sensibile con valore scalare (testo con escape, numero, booleano, null)
_RE_SCALARE = re.compile(
    r'"(' + _ALT + r')"(\s*:\s*)(?:"(?:[^"\\]|\\.)*"|-?[0-9][^,}\]\s]*|true|false|null)',
    re.IGNORECASE)
#: chiave sensibile con valore oggetto o lista: si ripiega su loads + ripulitura
_RE_COMPOSTO = re.compile(r'"(' + _ALT + r')"\s*:\s*[\[{]', re.IGNORECASE)
_RE_CORTE = re.compile(r'"(t|tk)"(\s*:\s*)"(?:[^"\\]|\\.){%d,}"' % MIN_CORTE, re.IGNORECASE)
#: sottostringhe che OGNI chiave sensibile contiene (in minuscolo): poche
#: ricerche veloci invece di una per chiave; se nessuna c'e', niente regex
_SPIE = ('key"', 'token"', 'passw', 'authentication"', 'authorization"', 'ssoid"',
         'cookie"', 'secret"', 'x-application"')


def _sensibile(k: Any, v: Any) -> bool:
    if not isinstance(k, str):
        return False
    kl = k.lower()
    if kl in SENSIBILI:
        return True
    return kl in SENSIBILI_CORTE and isinstance(v, str) and len(v) >= MIN_CORTE


def _ripulisci(obj: Any, conta: List[int]) -> Any:
    """Copia con i valori delle chiavi sensibili mascherati, a qualunque
    profondita' (dentro gli oggetti e dentro le liste). Pura."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _sensibile(k, v):
                out[k] = "***"
                conta[0] += 1
            else:
                out[k] = _ripulisci(v, conta)
        return out
    if isinstance(obj, list):
        return [_ripulisci(v, conta) for v in obj]
    return obj


def maschera_testo(testo: str, conta: List[int]) -> str:
    """Il testo JSON con i valori sensibili sostituiti da ``"***"``. Di solito
    e' una ricerca di sottostringhe e nient'altro; il ripiego su
    ``json.loads`` scatta solo se una chiave sensibile ha per valore un oggetto
    o una lista (mai visto nel canale). Pura (salvo il conto)."""
    basso = testo.lower()
    sospetto = any(s in basso for s in _SPIE)
    if sospetto:
        if _RE_COMPOSTO.search(testo):
            try:
                return json.dumps(_ripulisci(json.loads(testo), conta),
                                  separators=(",", ":"), ensure_ascii=True, default=str)
            except Exception:  # noqa: BLE001 - testo non JSON: si maschera solo lo scalare
                pass
        testo, n = _RE_SCALARE.subn(lambda m: '"%s"%s"***"' % (m.group(1), m.group(2)), testo)
        conta[0] += n
    # ``t``/``tk``: il ``"t"`` della busta del protocollo c'e' sempre, la regex
    # serve solo se ce n'e' un altro o se c'e' un ``"tk"``
    busta = basso.startswith('{"t"')
    if (basso.count('"t"') > (1 if busta else 0) or '"tk"' in basso
            or (busta and _RE_CORTE.match(testo, 1))):
        testo, n = _RE_CORTE.subn(lambda m: '"%s"%s"***"' % (m.group(1), m.group(2)), testo)
        conta[0] += n
    return testo


def _testo_payload(testo: Any, verificare: bool, conta: List[int]) -> Tuple[str, str]:
    """(chiave, valore JSON) per il payload: ``msg`` VERBATIM se e' un oggetto
    JSON su una riga, altrimenti ``txt`` (il testo come stringa JSON).
    ``verificare`` = il testo viene da un client (puo' non essere JSON): lo si
    controlla con ``json.loads`` (messaggi rari e piccoli)."""
    if isinstance(testo, (bytes, bytearray)):
        testo = bytes(testo).decode("utf-8", "replace")
    testo = str(testo)
    s = testo.strip()
    ok = s.startswith("{") and s.endswith("}") and "\n" not in s and "\r" not in s
    if ok and verificare:
        try:
            ok = isinstance(json.loads(s), dict)
        except ValueError:
            ok = False
    if ok:
        try:
            s.encode("ascii")
        except UnicodeEncodeError:
            s = json.dumps(json.loads(s), separators=(",", ":"), ensure_ascii=True)
        return "msg", maschera_testo(s, conta)
    return "txt", maschera_testo(json.dumps(testo, ensure_ascii=True), conta)


def riga_da_record(rec: tuple, conta: List[int]) -> str:
    """La riga JSONL di un record della coda (senza a capo). I metadati con
    ``json.dumps`` (piccoli), il payload VERBATIM in coda."""
    tipo = rec[0]
    base: Dict[str, Any] = {"v": VERSIONE, "k": tipo, "seq": rec[1], "mono_ns": rec[2],
                            "epoca_ms": rec[3] // 1_000_000, "porta": rec[4],
                            "sport": rec[5], "pid": _CONF.get("pid"), "av": _CONF.get("av")}
    testo: Any = None
    verificare = False
    if tipo == _PUB:
        (_, _, _, _, _, _, topic, n_byte, testo, perche, dest, salt, n_cli, n_let, n_top,
         comp) = rec
        base.update({"topic": topic, "byte": n_byte, "dest": dest, "saltati": salt,
                     "client": n_cli, "lettori": n_let, "n_topic": n_top})
        if comp is not None:
            base["clienti"] = comp
        if testo is not None:
            base["payload"] = perche
    elif tipo == _SALTO:
        (_, _, _, _, _, _, topic, n_cli, n_let, in_volo) = rec
        base.update({"topic": topic, "client": n_cli, "lettori": n_let, "in_volo": in_volo})
    elif tipo == _RX:
        (_, _, _, _, _, _, cliente, genere, chi, n_byte, testo) = rec
        base.update({"cliente": cliente, "genere": genere, "chi": chi, "byte": n_byte})
        verificare = True
    elif tipo == _TX:
        (_, _, _, _, _, _, cliente, genere, chi, n_byte, testo, via) = rec
        base.update({"cliente": cliente, "genere": genere, "chi": chi, "byte": n_byte,
                     "via": via})
    testa = json.dumps(base, separators=(",", ":"), ensure_ascii=True, default=str)
    if testo is None:
        return testa
    chiave, valore = _testo_payload(testo, verificare, conta)
    return testa[:-1] + ',"' + chiave + '":' + valore + "}"


# ---------------------------------------------------------------------------
# disco: rotazione, tetto, conservazione
# ---------------------------------------------------------------------------
def giorno_locale(epoca_s: Optional[float] = None) -> str:
    """La data LOCALE del PC (la cartella del giorno)."""
    return datetime.fromtimestamp(time.time() if epoca_s is None else epoca_s).strftime("%Y-%m-%d")


def _giorno_valido(nome: str) -> bool:
    try:
        datetime.strptime(nome, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _nostro(nome: str) -> bool:
    return nome.startswith(PREFISSO_FILE) and nome.endswith(SUFFISSO_FILE)


def peso_cartella(base: Path) -> int:
    """Byte dei file del registratore sotto ``base`` (solo i nostri)."""
    tot = 0
    try:
        for d in base.iterdir():
            if d.is_dir() and _giorno_valido(d.name):
                for f in d.iterdir():
                    if _nostro(f.name):
                        try:
                            tot += f.stat().st_size
                        except OSError:
                            pass
    except OSError:
        pass
    return tot


def applica_tetto(base: Path, tetto_byte: int, giorni: int, oggi: str) -> Tuple[bool, int]:
    """Conservazione e tetto. Toglie i giorni oltre ``giorni`` e poi, finche' il
    peso supera il tetto, il giorno piu' vecchio (MAI ``oggi``). Cancella solo
    i NOSTRI file e la cartella del giorno se resta vuota. Ritorna
    ``(dentro_il_tetto, giorni_rimossi)``. Mai solleva."""
    rimossi = 0
    try:
        if not base.is_dir():
            return True, 0
        giorni_presenti = sorted(d.name for d in base.iterdir()
                                 if d.is_dir() and _giorno_valido(d.name) and d.name != oggi)
        soglia = datetime.strptime(oggi, "%Y-%m-%d").toordinal() - int(giorni)
        da_togliere = [g for g in giorni_presenti
                       if datetime.strptime(g, "%Y-%m-%d").toordinal() <= soglia]
        resto = [g for g in giorni_presenti if g not in da_togliere]
        for g in da_togliere:
            rimossi += _togli_giorno(base / g)
        while peso_cartella(base) > tetto_byte and resto:
            rimossi += _togli_giorno(base / resto.pop(0))
        return peso_cartella(base) <= tetto_byte, rimossi
    except Exception as e:  # noqa: BLE001
        logger.debug("[reg-canale] tetto non applicato: %s", str(e)[:160])
        return True, rimossi


def _togli_giorno(d: Path) -> int:
    for f in list(d.iterdir()):
        if _nostro(f.name):
            try:
                f.unlink()
            except OSError:
                pass
    try:
        if not any(d.iterdir()):
            d.rmdir()
    except OSError:
        pass
    return 1


def _apri_esclusivo(d: Path, porta: int, pid: int) -> Tuple[Any, Path]:
    """Crea un file NUOVO (``xb``): ``canale_<porta>_<pid>.jsonl.gz``, poi
    ``_2``, ``_3``... se esiste gia' (pid riusato, riapertura dopo un errore,
    secondo canale nello stesso processo). Mai un append."""
    base = "%s%d_%d" % (PREFISSO_FILE, int(porta), int(pid))
    for n in range(1, 1000):
        nome = base + (SUFFISSO_FILE if n == 1 else "_%d%s" % (n, SUFFISSO_FILE))
        p = d / nome
        try:
            return gzip.open(p, "xb", compresslevel=6), p
        except FileExistsError:
            continue
    raise OSError("nessun nome libero per %s in %s" % (base, d))


# ---------------------------------------------------------------------------
# il thread di scrittura
# ---------------------------------------------------------------------------
class _Scrittore(threading.Thread):
    """Drena la coda e scrive. UNO per processo, fuori dal percorso caldo."""

    def __init__(self, apri: Optional[Callable[[Path, int], Tuple[Any, Path]]] = None) -> None:
        super().__init__(name="registratore-canale", daemon=True)
        # 11/10 (revisione): ``_fermo``, non ``_stop`` - su Python <= 3.12
        # ``Thread._stop`` e' un metodo interno e oscurarlo rompe ``join``
        self._fermo = threading.Event()
        self._apri = apri or (lambda d, porta: _apri_esclusivo(d, porta, os.getpid()))
        self._file: Dict[int, Any] = {}
        self._percorsi: Dict[int, Path] = {}
        self._giorno: Optional[str] = None
        self._sospeso_per: Optional[str] = None
        self._ultimo_flush = time.monotonic()
        self._ultimo_stato = time.monotonic()
        self._ultimo_tetto = 0.0
        self._ultimo_avviso = 0.0
        self._porte: set = set()

    def run(self) -> None:
        try:
            while not self._fermo.is_set():
                try:
                    n = self.giro()
                except Exception as e:  # noqa: BLE001 - il thread non muore mai
                    _conta("errori_disco")
                    self._avvisa(f"giro KO: {type(e).__name__}: {str(e)[:160]}")
                    n = 0
                if n == 0:
                    self._fermo.wait(0.2)
            self.chiudi_tutto()
        except Exception:  # noqa: BLE001
            pass

    def ferma(self, attesa_s: float = 3.0) -> None:
        self._fermo.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=attesa_s)

    def chiudi_tutto(self, evento: str = "chiusura") -> None:
        """Ultimo giro, riga ``chiusura`` in ogni file aperto, chiusura dei gzip."""
        try:
            while self.giro():
                pass
        except Exception:  # noqa: BLE001
            pass
        if self._giorno is not None:
            self.scrivi_stato(self._giorno, evento=evento, solo_aperti=True)
        self._chiudi_tutti()

    def giro(self, max_n: int = 5000) -> int:
        """Un giro: drena fino a ``max_n`` record, scrive, flush/stato/tetto se
        e' ora. Ritorna quanti record ha tolto dalla coda."""
        oggi = giorno_locale()
        if oggi != self._giorno:
            self._ruota(oggi)
        ora = time.monotonic()
        recs = []
        for _ in range(max_n):
            try:
                recs.append(_CODA.popleft())
            except IndexError:
                break
        if recs:
            peso = sum(_peso(r) for r in recs)
            with _LOCK_CONTI:
                _CONTI["byte_in_coda"] = max(0, _CONTI["byte_in_coda"] - peso)
        for rec in recs:
            self._porte.add(rec[4])
        if ora - self._ultimo_tetto >= TETTO_OGNI_S:
            # dopo il drenaggio: se oggi sfora, la riga ``tetto_raggiunto`` va
            # anche nei file delle porte appena viste
            self._ultimo_tetto = ora
            self._controlla_tetto(oggi)
        if recs:
            self._scrivi(recs, oggi)
        if ora - self._ultimo_stato >= STATO_OGNI_S:
            self._ultimo_stato = ora
            self.scrivi_stato(oggi)
        if ora - self._ultimo_flush >= FLUSH_OGNI_S:
            self._ultimo_flush = ora
            self._flush()
        return len(recs)

    def _ruota(self, oggi: str) -> None:
        if self._giorno is not None:
            self.scrivi_stato(self._giorno, evento="chiusura", solo_aperti=True)
        self._chiudi_tutti()
        self._giorno = oggi
        if self._sospeso_per is not None and self._sospeso_per != oggi:
            self._sospeso_per = None
        self._ultimo_tetto = 0.0

    def _controlla_tetto(self, oggi: str) -> None:
        tetto = int(float(_CONF["tetto_mb"]) * 1024 * 1024)
        self._flush()
        dentro, rimossi = applica_tetto(Path(_CONF["cartella"]), tetto, int(_CONF["giorni"]), oggi)
        _conta("giorni_rimossi", rimossi)
        if not dentro and self._sospeso_per != oggi:
            # oggi da solo supera il tetto: si sospende fino a domani e lo si dice
            self.scrivi_stato(oggi, evento="tetto_raggiunto")
            self._sospeso_per = oggi
            self._chiudi_tutti()
            self._avvisa(f"tetto di {_CONF['tetto_mb']:.0f} MB raggiunto: registrazione "
                         f"sospesa fino a domani")

    def _scrivi(self, recs: List[tuple], oggi: str) -> None:
        if self._sospeso_per == oggi:
            _conta("scartati_tetto", len(recs))
            return
        per_porta: Dict[int, List[str]] = {}
        conta = [0]
        dal_cedimento = 0
        for rec in recs:
            try:
                riga = riga_da_record(rec, conta)
                per_porta.setdefault(rec[4], []).append(riga)
                dal_cedimento += len(riga)
            except Exception:  # noqa: BLE001 - un record illeggibile non ferma gli altri
                _conta("errori_aggancio")
            if dal_cedimento >= CEDI_OGNI_BYTE:
                # cede il GIL: senza, il thread del loop del canale (e quelli
                # dei bot) aspetterebbero fino all'intervallo di cambio
                # dell'interprete (5 ms) mentre qui si compongono righe grandi
                dal_cedimento = 0
                time.sleep(0)
        _conta("mascherati", conta[0])
        for porta, righe in per_porta.items():
            try:
                fh = self._file_di(porta, oggi)
                pezzo: List[str] = []
                peso = 0
                for riga in righe:
                    pezzo.append(riga)
                    peso += len(riga)
                    if peso >= CEDI_OGNI_BYTE:
                        fh.write(("\n".join(pezzo) + "\n").encode("ascii", "replace"))
                        pezzo, peso = [], 0
                        time.sleep(0)   # cede il GIL fra una compressione e l'altra
                if pezzo:
                    fh.write(("\n".join(pezzo) + "\n").encode("ascii", "replace"))
                _conta("scritti", len(righe))
            except Exception as e:  # noqa: BLE001 - disco pieno, permessi: contato, mai propagato
                _conta("errori_disco")
                self._chiudi(porta)
                self._avvisa(f"scrittura KO (porta {porta}): {type(e).__name__}: {str(e)[:160]}")

    def scrivi_stato(self, oggi: str, evento: str = "stato", solo_aperti: bool = False) -> None:
        """Riga ``stato`` (o ``chiusura``/``tetto_raggiunto``) con i contatori,
        in ogni file di oggi (``solo_aperti``: solo nei file gia' aperti)."""
        if self._sospeso_per == oggi and evento == "stato":
            return
        c = conti()
        porte = sorted(self._file) if solo_aperti else sorted(self._porte)
        for porta in porte:
            riga = {"v": VERSIONE, "k": evento, "mono_ns": time.monotonic_ns(),
                    "epoca_ms": time.time_ns() // 1_000_000, "porta": porta,
                    "pid": _CONF.get("pid"), "av": _CONF.get("av"), "conti": c,
                    "campione": _CONF["campione"], "pieni": sorted(PIENI),
                    "tetto_mb": _CONF["tetto_mb"], "coda_max": _CONF["coda_max"],
                    "coda_max_byte": _CONF["coda_max_byte"]}
            try:
                self._file_di(porta, oggi).write(
                    (json.dumps(riga, separators=(",", ":")) + "\n").encode("ascii"))
            except Exception as e:  # noqa: BLE001
                _conta("errori_disco")
                self._chiudi(porta)
                self._avvisa(f"riga {evento} KO: {type(e).__name__}: {str(e)[:160]}")

    def _file_di(self, porta: int, oggi: str) -> Any:
        fh = self._file.get(porta)
        if fh is None:
            d = Path(_CONF["cartella"]) / oggi
            d.mkdir(parents=True, exist_ok=True)
            fh, p = self._apri(d, porta)
            self._file[porta] = fh
            self._percorsi[porta] = p
        return fh

    def _flush(self) -> None:
        try:
            p = peso_cartella(Path(_CONF["cartella"]))
            with _LOCK_CONTI:
                _CONTI["peso_cartella_byte"] = p
        except Exception:  # noqa: BLE001
            pass
        for porta, fh in list(self._file.items()):
            try:
                fh.flush()
            except Exception as e:  # noqa: BLE001
                _conta("errori_disco")
                self._chiudi(porta)
                self._avvisa(f"flush KO: {type(e).__name__}: {str(e)[:160]}")

    def _chiudi(self, porta: int) -> None:
        fh = self._file.pop(porta, None)
        self._percorsi.pop(porta, None)
        if fh is not None:
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass

    def _chiudi_tutti(self) -> None:
        for porta in list(self._file):
            self._chiudi(porta)

    def _avvisa(self, testo: str) -> None:
        ora = time.monotonic()
        if self._ultimo_avviso == 0.0 or ora - self._ultimo_avviso >= AVVISO_OGNI_S:
            self._ultimo_avviso = ora
            logger.warning("[reg-canale] %s", testo)


def _avvia_thread() -> None:
    with _LOCK:
        if _STATO["thread"] is not None or not ATTIVO or _STATO["chiuso"]:
            return
        if nel_banco():
            _spegni_per_banco()
            return
        t = _Scrittore()
        _STATO["thread"] = t
        t.start()
        if not _STATO["atexit"]:
            _STATO["atexit"] = True
            try:
                atexit.register(_all_uscita)
            except Exception:  # noqa: BLE001
                pass


def _spegni_per_banco() -> None:
    global ATTIVO  # noqa: PLW0603
    ATTIVO = False
    _CODA.clear()
    with _LOCK_CONTI:
        _CONTI["byte_in_coda"] = 0
    logger.info("[reg-canale] banco caricato nel processo: registratore spento")


def scrivi_ora(apri: Optional[Callable[[Path, int], Tuple[Any, Path]]] = None) -> Dict[str, int]:
    """Solo per i test e la misura: drena la coda nel thread corrente con uno
    scrittore usa e getta (stessa logica del thread) e chiude i file con la
    riga ``chiusura``."""
    s = _Scrittore(apri=apri)
    try:
        s.chiudi_tutto()
    finally:
        s._chiudi_tutti()
    return conti()


def leggi_file(percorso: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Righe di un file del registratore. TOLLERANTE: coda tronca (processo
    morto), membri corrotti (un file rovinato), righe illeggibili: ritorna le
    righe intere lette e il problema in parole (``None`` se integro)."""
    from .gz_tollerante import problema, righe_file

    righe: List[Dict[str, Any]] = []
    try:
        grezze, resoconto = righe_file(percorso)
    except OSError as e:
        return [], "file illeggibile: %s" % type(e).__name__
    cattive = 0
    for g in grezze:
        try:
            o = json.loads(g)
        except ValueError:
            cattive += 1
            continue
        if isinstance(o, dict):
            righe.append(o)
    testo = problema(resoconto)
    if cattive:
        testo = (testo + "; " if testo else "") + "%d righe illeggibili" % cattive
    return righe, (testo or None)


# ---------------------------------------------------------------------------
# accensione da ambiente: all'import, una volta. Spento di serie.
# ---------------------------------------------------------------------------
if interruttore_acceso():
    accendi()

__all__ = ["ATTIVO", "ENV", "PIENI", "SENSIBILI", "accendi", "spegni", "conti",
           "pubblicato", "giro_saltato", "ricevuto", "risposta", "risposta_attore",
           "leggi_file", "applica_tetto", "peso_cartella", "riga_da_record", "scrivi_ora",
           "maschera_testo"]
