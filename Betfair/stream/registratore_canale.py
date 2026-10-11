"""registratore_canale.py - il REGISTRATORE del canale locale (M-3, 11/10/2026).

Mandato: mappatura dei flussi reali per la v2 (``ARCHITETTURA_2026-10/mappa/
M3_CANALE_E_MAPPA.md``). Registra, per ogni processo che ha un canale locale
(``local_channel.py``, ws su 127.0.0.1: 47331 calcio, 47332 tennis, 47333 Mike,
47334 Omega, 47336 scanner, ...), che cosa passa sul canale:

  * ogni messaggio PUBBLICATO (``publish`` -> giro ``_broadcast``): istante
    monotono ed epoca, porta e sport del processo, topic, byte, destinatari,
    client saltati per contropressione (oltre ``_MAX_INVII_IN_VOLO``), client e
    lettori collegati, sequenza;
  * ogni giro SALTATO per intero (nessun client pronto);
  * ogni messaggio RICEVUTO da un client (comandi della UI, ``/comando/``,
    sveglie, richieste di sola lettura) e ogni RISPOSTA del canale (``respond``,
    ``_send``, ``invia``, ``invia_attore``): sono l'esito dei comandi.

PAYLOAD COMPLETO solo per i topic che servono alla v2 (``PIENI``: order, esiti,
conto, conto_paper, modo_ordini), per i messaggi ricevuti e per le risposte.
Per tutti gli altri topic (ladder, board, board_mercato, now, ...) il payload
si salva a CAMPIONE: il primo e poi 1 ogni ``N`` per topic e per porta
(``REGISTRA_CANALE_CAMPIONE``, di serie 20). I metadati si scrivono SEMPRE.

INTERRUTTORE ``REGISTRA_CANALE=0|1``, DI SERIE 0 (come ``MONITOR_SALUTE`` di
``Betfair/monitor/sonde.py``). Acceso solo se ``=1`` nell'ambiente del processo
(o, se l'ambiente non lo nomina, nel ``.env`` della radice, letto e MAI caricato)
E nel processo non gira pytest (salvo ``accendi(_consenti_in_test=True)``) E
non e' caricato il banco (``Betfair.stream.backtest*``, controllato anche al
primo record). Spento: ogni aggancio di ``local_channel`` e' un
``if _reg.ATTIVO`` falso, nessun file, nessun thread.

PERCORSO CALDO. Gli agganci NON scrivono su disco e NON prendono lucchetti:
mettono una tupla di riferimenti (il testo JSON gia' serializzato dal canale,
immutabile) in una ``deque`` con un tetto (``CODA_MAX``). Coda piena = il
record si SCARTA e si CONTA (``scartati_coda``), mai si aspetta. La sequenza si
assegna PRIMA del controllo della coda: un buco nella sequenza del file e' un
record scartato, e la mappa lo vede.

SCRITTURA. UN thread demone per processo (``registratore-canale``) drena la
coda, toglie i dati sensibili (``_ripulisci``), scrive JSONL compresso in
``<cartella>/<AAAA-MM-GG>/canale_<porta>.jsonl.gz`` (un file per processo -
il canale e' uno per processo - e per giorno; un riavvio aggiunge un membro
gzip in coda, leggibile da ``gzip.open``). Ogni 5 s un flush del gzip (un
crash perde al piu' gli ultimi secondi). Ogni 30 s una riga ``stato`` con i
contatori. Rotazione a mezzanotte (data locale). TETTO in MB sull'intera
cartella (``REGISTRA_CANALE_MB``, di serie 1024) e conservazione in giorni
(``REGISTRA_CANALE_GIORNI``, di serie 7): oltre il tetto si cancellano i giorni
piu' vecchi (mai quello di oggi), e se oggi da solo supera il tetto la
scrittura si SOSPENDE fino a domani (``scartati_tetto``). Errori del disco:
contati (``errori_disco``), un avviso ogni 10 minuti, MAI propagati.

DATI SENSIBILI. Il token del canale viaggia nel percorso della connessione
(``?t=``) e nell'header ``X-Canale-Token``: il registratore NON legge mai ne'
percorso ne' header. In piu' ogni chiave che somiglia a una credenziale
(``token``, ``password``, ``secret``, ``app_key``, ``session``, ``ssoid``,
``cookie``, ``authorization``, ``cert``) viene mascherata nei payload prima
della scrittura (``"***"``), e il numero di mascherature e' nella riga ``stato``.

Ogni funzione pubblica e' best-effort: NON solleva MAI verso il chiamante.
Nessuna connessione, nessun processo: un solo thread, acceso solo a interruttore
acceso e al primo record. ASCII-only; commenti in italiano.
"""
from __future__ import annotations

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
VERSIONE = 1
#: topic con il payload SEMPRE completo (servono alla v2)
PIENI = frozenset({"order", "esiti", "conto", "conto_paper", "modo_ordini"})
CAMPIONE_DEFAULT = 20
TETTO_MB_DEFAULT = 1024.0
GIORNI_DEFAULT = 7
#: record in coda oltre i quali si scarta (memoria: ~200 B di tupla per record
#: piu' i testi campionati; vedi il documento M3 per il conto)
CODA_MAX = 20000
FLUSH_OGNI_S = 5.0
STATO_OGNI_S = 30.0
TETTO_OGNI_S = 30.0
AVVISO_OGNI_S = 600.0
PREFISSO_FILE = "canale_"
SUFFISSO_FILE = ".jsonl.gz"

RADICE_REPO = Path(__file__).resolve().parents[2]

#: True solo dopo un ``accendi`` riuscito (letto dagli agganci come ``_reg.ATTIVO``)
ATTIVO = False

_LOCK = threading.Lock()
_CODA: "collections.deque" = collections.deque()
_SEQ = itertools.count(1)
_CONTI: Dict[str, int] = {"scartati_coda": 0, "scartati_tetto": 0, "errori_disco": 0,
                          "errori_aggancio": 0, "scritti": 0,
                          "mascherati": 0, "giorni_rimossi": 0, "peso_cartella_byte": 0}
#: (porta, topic) -> quanti publish visti (per il campione 1 ogni N)
_VISTI: Dict[Tuple[int, str], int] = {}
#: id(ws) -> numero progressivo del client (stabile nel processo, nessun dato del socket)
_CLIENTI: Dict[int, int] = {}
#: porta -> firma (xor degli id) dei client collegati all'ultimo giro: quando
#: cambia, il record ``pub`` porta la COMPOSIZIONE dei client (chi riceve)
_FIRME: Dict[int, int] = {}
_CONF: Dict[str, Any] = {"cartella": None, "tetto_mb": TETTO_MB_DEFAULT,
                         "campione": CAMPIONE_DEFAULT, "giorni": GIORNI_DEFAULT,
                         "coda_max": CODA_MAX, "pid": None}
_STATO: Dict[str, Any] = {"thread": None, "max_in_volo": None}

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
            coda_max: Optional[int] = None, _consenti_in_test: bool = False,
            _senza_thread: bool = False) -> bool:
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
                "pid": os.getpid(),
                "senza_thread": bool(_senza_thread),
            })
            ATTIVO = True
        logger.info("[reg-canale] registratore del canale ACCESO in %s (tetto %.0f MB, "
                    "campione 1/%d)", _CONF["cartella"], _CONF["tetto_mb"], _CONF["campione"])
        return True
    except Exception as e:  # noqa: BLE001 - il registratore non ferma mai un servizio
        logger.warning("[reg-canale] accensione KO (registratore spento): %s", str(e)[:200])
        ATTIVO = False
        return False


def spegni(attesa_s: float = 3.0) -> None:
    """Spegne il registratore: il thread scrive quello che resta e chiude i file."""
    global ATTIVO  # noqa: PLW0603
    try:
        ATTIVO = False
        t = _STATO.get("thread")
        if t is not None:
            t.ferma(attesa_s)
        _STATO["thread"] = None
    except Exception:  # noqa: BLE001
        ATTIVO = False


def conti() -> Dict[str, int]:
    """Copia dei contatori (per i test e per la riga ``stato``). ``seq_prossimo``
    = il numero che avra' il prossimo record: la mappa ci vede anche i record
    scartati DOPO l'ultimo scritto."""
    return {**_CONTI, "in_coda": len(_CODA), "seq_prossimo": _seq_prossimo()}


def _seq_prossimo() -> int:
    """Legge il contatore senza consumarlo (``repr`` di ``itertools.count``:
    ``count(N)``). 0 = illeggibile."""
    try:
        return int(repr(_SEQ)[len("count("):-1])
    except ValueError:
        return 0


def azzera_per_test() -> None:
    """Solo per i test: coda, contatori, campioni e clienti da capo."""
    global _SEQ  # noqa: PLW0603
    _CODA.clear()
    for k in _CONTI:
        _CONTI[k] = 0
    _VISTI.clear()
    _CLIENTI.clear()
    _FIRME.clear()
    _SEQ = itertools.count(1)


# ---------------------------------------------------------------------------
# agganci (chiamati da local_channel SOLO dopo ``if _reg.ATTIVO``). Mai sollevano.
# ---------------------------------------------------------------------------
def _accoda(rec: tuple) -> None:
    """Coda limitata: se piena si scarta e si conta, MAI si aspetta."""
    if len(_CODA) >= _CONF["coda_max"]:
        _CONTI["scartati_coda"] += 1
        return
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
    k = id(ws)
    n = _CLIENTI.get(k)
    if n is None:
        if len(_CLIENTI) > 100000:   # anti-runaway: mai una mappa infinita
            _CLIENTI.clear()
        n = _CLIENTI[k] = len(_CLIENTI) + 1
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

    Quando cambia l'insieme dei client collegati (connessione o chiusura) il
    record porta anche la COMPOSIZIONE: ``[cliente, genere, chi]`` per ognuno.
    Succede di rado: e' l'unico punto in cui si sa CHI riceve."""
    try:
        seq = next(_SEQ)
        mono, epoca = time.monotonic_ns(), time.time_ns()
        massimo = _max_in_volo()
        lettori, in_volo = ch._lettori, ch._in_volo_ws
        dest = salt = firma = 0
        clienti = list(ch._clients)
        for w in clienti:
            firma ^= id(w)
            f = lettori.get(w)
            if f is not None and topic not in f:
                continue
            if in_volo.get(w, 0) > massimo:
                salt += 1
                continue
            dest += 1
        comp = None
        if _FIRME.get(ch.port) != firma:
            _FIRME[ch.port] = firma
            comp = sorted([_cliente(w), *_genere(ch, w)] for w in clienti)
        chiave = (ch.port, topic)
        n = _VISTI.get(chiave, 0) + 1
        _VISTI[chiave] = n
        pieno = topic in PIENI
        tieni = pieno or (n % _CONF["campione"] == 1) or _CONF["campione"] == 1
        _accoda((_PUB, seq, mono, epoca, ch.port, ch.sport, topic, len(text),
                 text if tieni else None, "pieno" if pieno else ("campione" if tieni else None),
                 dest, salt, ch._n_clients, ch._n_lettori, n, comp))
    except Exception:  # noqa: BLE001 - un record perso non ferma il canale
        _CONTI["errori_aggancio"] += 1


def giro_saltato(ch: Any, topic: str) -> None:
    """Giro saltato per intero (nessun client pronto). Thread del chiamante."""
    try:
        seq = next(_SEQ)
        _accoda((_SALTO, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 topic, ch._n_clients, ch._n_lettori, ch._in_volo))
    except Exception:  # noqa: BLE001
        _CONTI["errori_aggancio"] += 1


def ricevuto(ch: Any, ws: Any, raw: Any) -> None:
    """Messaggio arrivato da un client (thread del loop), payload completo."""
    try:
        seq = next(_SEQ)
        genere, chi = _genere(ch, ws)
        n = len(raw) if isinstance(raw, (str, bytes, bytearray)) else 0
        _accoda((_RX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 _cliente(ws), genere, chi, n, raw))
    except Exception:  # noqa: BLE001
        _CONTI["errori_aggancio"] += 1


def risposta(ch: Any, ws: Any, text: str, via: str) -> None:
    """Risposta MIRATA a un client (esito di un comando), payload completo."""
    try:
        seq = next(_SEQ)
        genere, chi = _genere(ch, ws)
        _accoda((_TX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 _cliente(ws), genere, chi, len(text), text, via))
    except Exception:  # noqa: BLE001
        _CONTI["errori_aggancio"] += 1


def risposta_attore(ch: Any, attore: str, text: str) -> None:
    """Invio a tutti i socket di comando di un attore (``invia_attore``)."""
    try:
        seq = next(_SEQ)
        _accoda((_TX, seq, time.monotonic_ns(), time.time_ns(), ch.port, ch.sport,
                 None, "comando", str(attore)[:40], len(text), text, "invia_attore"))
    except Exception:  # noqa: BLE001
        _CONTI["errori_aggancio"] += 1


# ---------------------------------------------------------------------------
# dati sensibili
# ---------------------------------------------------------------------------
_SENSIBILE = re.compile(r"token|passw|secret|app_?key|session|ssoid|cookie|authoriz|"
                        r"cert|credenzial|api_?key", re.IGNORECASE)


def _ripulisci(obj: Any, conta: List[int]) -> Any:
    """Copia con i valori delle chiavi sensibili mascherati. Pura."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SENSIBILE.search(k):
                out[k] = "***"
                conta[0] += 1
            else:
                out[k] = _ripulisci(v, conta)
        return out
    if isinstance(obj, list):
        return [_ripulisci(v, conta) for v in obj]
    return obj


def _payload(testo: Any, conta: List[int]) -> Tuple[Any, Optional[str]]:
    """Il payload come oggetto (ripulito) o, se non e' JSON, ``None`` + motivo."""
    if testo is None:
        return None, None
    try:
        if isinstance(testo, (bytes, bytearray)):
            testo = bytes(testo).decode("utf-8", "replace")
        return _ripulisci(json.loads(testo), conta), None
    except Exception:  # noqa: BLE001 - messaggio malformato: si dice, non si copia
        return None, "non_json"


def riga_da_record(rec: tuple, conta: List[int]) -> Dict[str, Any]:
    """La riga JSONL di un record della coda. Pura (salvo il conto mascherature)."""
    tipo = rec[0]
    base: Dict[str, Any] = {"v": VERSIONE, "k": tipo, "seq": rec[1], "mono_ns": rec[2],
                            "epoca_ms": rec[3] // 1_000_000, "porta": rec[4],
                            "sport": rec[5], "pid": _CONF.get("pid")}
    if tipo == _PUB:
        (_, _, _, _, _, _, topic, n_byte, testo, perche, dest, salt, n_cli, n_let, n_top,
         comp) = rec
        base.update({"topic": topic, "byte": n_byte, "dest": dest, "saltati": salt,
                     "client": n_cli, "lettori": n_let, "n_topic": n_top})
        if comp is not None:
            base["clienti"] = comp
        if testo is not None:
            msg, errore = _payload(testo, conta)
            base["payload"] = perche
            base["msg"] = msg
            if errore:
                base["errore"] = errore
    elif tipo == _SALTO:
        (_, _, _, _, _, _, topic, n_cli, n_let, in_volo) = rec
        base.update({"topic": topic, "client": n_cli, "lettori": n_let, "in_volo": in_volo})
    elif tipo == _RX:
        (_, _, _, _, _, _, cliente, genere, chi, n_byte, testo) = rec
        msg, errore = _payload(testo, conta)
        base.update({"cliente": cliente, "genere": genere, "chi": chi, "byte": n_byte,
                     "msg": msg})
        if errore:
            base["errore"] = errore
    elif tipo == _TX:
        (_, _, _, _, _, _, cliente, genere, chi, n_byte, testo, via) = rec
        msg, errore = _payload(testo, conta)
        base.update({"cliente": cliente, "genere": genere, "chi": chi, "byte": n_byte,
                     "via": via, "msg": msg})
        if errore:
            base["errore"] = errore
    return base


def _riga_json(riga: Dict[str, Any]) -> bytes:
    return (json.dumps(riga, separators=(",", ":"), ensure_ascii=True, default=str)
            + "\n").encode("ascii")


# ---------------------------------------------------------------------------
# disco: rotazione, tetto, conservazione
# ---------------------------------------------------------------------------
def giorno_locale(epoca_s: Optional[float] = None) -> str:
    return datetime.fromtimestamp(time.time() if epoca_s is None else epoca_s).strftime("%Y-%m-%d")


def _giorno_valido(nome: str) -> bool:
    try:
        datetime.strptime(nome, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def peso_cartella(base: Path) -> int:
    """Byte dei file del registratore sotto ``base`` (solo i nostri)."""
    tot = 0
    try:
        for d in base.iterdir():
            if d.is_dir() and _giorno_valido(d.name):
                for f in d.iterdir():
                    if f.name.startswith(PREFISSO_FILE) and f.name.endswith(SUFFISSO_FILE):
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
        if f.name.startswith(PREFISSO_FILE) and f.name.endswith(SUFFISSO_FILE):
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


# ---------------------------------------------------------------------------
# il thread di scrittura
# ---------------------------------------------------------------------------
class _Scrittore(threading.Thread):
    """Drena la coda e scrive. UNO per processo, fuori dal percorso caldo."""

    def __init__(self, apri: Optional[Callable[[Path], Any]] = None) -> None:
        super().__init__(name="registratore-canale", daemon=True)
        self._stop = threading.Event()
        self._apri = apri or (lambda p: gzip.open(p, "ab", compresslevel=6))
        self._file: Dict[int, Any] = {}
        self._giorno: Optional[str] = None
        self._sospeso_per: Optional[str] = None
        self._ultimo_flush = time.monotonic()
        self._ultimo_stato = time.monotonic()
        self._ultimo_tetto = 0.0
        self._ultimo_avviso = 0.0
        self._porte: set = set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                n = self.giro()
            except Exception as e:  # noqa: BLE001 - il thread non muore mai
                _CONTI["errori_disco"] += 1
                self._avvisa(f"giro KO: {type(e).__name__}: {str(e)[:160]}")
                n = 0
            if n == 0:
                self._stop.wait(0.2)
        try:
            self.giro()
        finally:
            self._chiudi_tutti()

    def ferma(self, attesa_s: float = 3.0) -> None:
        self._stop.set()
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=attesa_s)

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
        self._chiudi_tutti()
        self._giorno = oggi
        if self._sospeso_per is not None and self._sospeso_per != oggi:
            self._sospeso_per = None
        self._ultimo_tetto = 0.0

    def _controlla_tetto(self, oggi: str) -> None:
        tetto = int(float(_CONF["tetto_mb"]) * 1024 * 1024)
        self._flush()
        dentro, rimossi = applica_tetto(Path(_CONF["cartella"]), tetto, int(_CONF["giorni"]), oggi)
        _CONTI["giorni_rimossi"] += rimossi
        if not dentro and self._sospeso_per != oggi:
            # oggi da solo supera il tetto: si sospende fino a domani e lo si dice
            self.scrivi_stato(oggi, evento="tetto_raggiunto")
            self._sospeso_per = oggi
            self._chiudi_tutti()
            self._avvisa(f"tetto di {_CONF['tetto_mb']:.0f} MB raggiunto: registrazione "
                         f"sospesa fino a domani")

    def _scrivi(self, recs: List[tuple], oggi: str) -> None:
        if self._sospeso_per == oggi:
            _CONTI["scartati_tetto"] += len(recs)
            return
        per_porta: Dict[int, List[bytes]] = {}
        conta = [0]
        for rec in recs:
            try:
                per_porta.setdefault(rec[4], []).append(_riga_json(riga_da_record(rec, conta)))
            except Exception:  # noqa: BLE001 - un record illeggibile non ferma gli altri
                _CONTI["errori_aggancio"] += 1
        _CONTI["mascherati"] += conta[0]
        for porta, righe in per_porta.items():
            self._porte.add(porta)
            try:
                fh = self._file_di(porta, oggi)
                dati = b"".join(righe)
                fh.write(dati)
                _CONTI["scritti"] += len(righe)
            except Exception as e:  # noqa: BLE001 - disco pieno, permessi: contato, mai propagato
                _CONTI["errori_disco"] += 1
                self._chiudi(porta)
                self._avvisa(f"scrittura KO (porta {porta}): {type(e).__name__}: {str(e)[:160]}")

    def scrivi_stato(self, oggi: str, evento: str = "stato") -> None:
        """Riga ``stato`` con i contatori, in ogni file aperto oggi."""
        if self._sospeso_per == oggi:
            return
        c = conti()
        for porta in sorted(self._porte):
            riga = {"v": VERSIONE, "k": evento, "mono_ns": time.monotonic_ns(),
                    "epoca_ms": time.time_ns() // 1_000_000, "porta": porta,
                    "pid": _CONF.get("pid"), "conti": c,
                    "campione": _CONF["campione"], "pieni": sorted(PIENI),
                    "tetto_mb": _CONF["tetto_mb"], "coda_max": _CONF["coda_max"]}
            try:
                self._file_di(porta, oggi).write(_riga_json(riga))
            except Exception as e:  # noqa: BLE001
                _CONTI["errori_disco"] += 1
                self._chiudi(porta)
                self._avvisa(f"riga stato KO: {type(e).__name__}: {str(e)[:160]}")

    def _file_di(self, porta: int, oggi: str) -> Any:
        fh = self._file.get(porta)
        if fh is None:
            d = Path(_CONF["cartella"]) / oggi
            d.mkdir(parents=True, exist_ok=True)
            fh = self._apri(d / f"{PREFISSO_FILE}{int(porta)}{SUFFISSO_FILE}")
            self._file[porta] = fh
        return fh

    def _flush(self) -> None:
        try:
            _CONTI["peso_cartella_byte"] = peso_cartella(Path(_CONF["cartella"]))
        except Exception:  # noqa: BLE001
            pass
        for porta, fh in list(self._file.items()):
            try:
                fh.flush()
            except Exception as e:  # noqa: BLE001
                _CONTI["errori_disco"] += 1
                self._chiudi(porta)
                self._avvisa(f"flush KO: {type(e).__name__}: {str(e)[:160]}")

    def _chiudi(self, porta: int) -> None:
        fh = self._file.pop(porta, None)
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
        if _STATO["thread"] is not None or not ATTIVO:
            return
        if nel_banco():
            _spegni_per_banco()
            return
        t = _Scrittore()
        _STATO["thread"] = t
        t.start()


def _spegni_per_banco() -> None:
    global ATTIVO  # noqa: PLW0603
    ATTIVO = False
    _CODA.clear()
    logger.info("[reg-canale] banco caricato nel processo: registratore spento")


def scrivi_ora(apri: Optional[Callable[[Path], Any]] = None) -> Dict[str, int]:
    """Solo per i test e la misura: drena la coda nel thread corrente con uno
    scrittore usa e getta (stessa logica del thread) e chiude i file."""
    s = _Scrittore(apri=apri)
    try:
        while s.giro():
            pass
        s.scrivi_stato(giorno_locale())
    finally:
        s._chiudi_tutti()
    return conti()


def leggi_file(percorso: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Righe di un file del registratore. Tollera un gzip TRONCATO (processo
    morto prima della chiusura): ritorna le righe intere lette e il motivo."""
    righe: List[Dict[str, Any]] = []
    errore = None
    try:
        with gzip.open(percorso, "rt", encoding="ascii", errors="replace") as fh:
            for linea in fh:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    righe.append(json.loads(linea))
                except ValueError:
                    errore = "riga illeggibile (probabile troncamento)"
    except (EOFError, OSError, gzip.BadGzipFile) as e:  # noqa: B014
        errore = f"file troncato o illeggibile: {type(e).__name__}"
    return righe, errore


# ---------------------------------------------------------------------------
# accensione da ambiente: all'import, una volta. Spento di serie.
# ---------------------------------------------------------------------------
if interruttore_acceso():
    accendi()

__all__ = ["ATTIVO", "ENV", "PIENI", "accendi", "spegni", "conti", "pubblicato",
           "giro_saltato", "ricevuto", "risposta", "risposta_attore", "leggi_file",
           "applica_tetto", "peso_cartella", "riga_da_record", "scrivi_ora"]
