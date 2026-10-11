"""registratore_ordini.py - M-1 della mappatura dei flussi reali (11/10/2026).

Registra su disco, per la v2 e per certificare lo stream ordini sostituito
(``ARCHITETTURA_2026-10/ondata2/PIANO_AGGANCIO.md``, rischio R3: nel repo non
esiste nessuna registrazione ``ocm``), due cose che oggi non lascia traccia
nessuno:

  1. le righe GREZZE dello STREAM ORDINI del conto (``connection``, ``status``,
     ``ocm``) cosi' come arrivano al listener dello stream ordini che il
     processo ha GIA' aperto (flumine LIVE: ``OrderStream.run`` ->
     ``betting_client.streaming.create_stream`` -> ``subscribe_to_orders``);
     nessuna connessione nuova, nessuna sottoscrizione nuova;
  2. ogni CHIAMATA REST con soldi (``placeOrders``, ``cancelOrders``,
     ``replaceOrders``, ``updateOrders``): richiesta, risposta GREZZA di
     Betfair, codici d'errore, istante d'invio e di risposta (epoca e orologio
     monotono), chi l'ha fatta (dai riferimenti), il mercato.

PUNTI D'AGGANCIO (una riga ciascuno, vedi ``M1_REGISTRATORE_ORDINI.md``):
  * ``Betfair/stream/auth.py`` ``build_client``: l'UNICO costruttore degli
    APIClient di betfairlightweight di tutti i processi (runner calcio, runner
    tennis, sessioni scalper, safe). ``aggancia_api_client`` avvolge, sulla
    SOLA istanza, ``betting.request`` (tutte le chiamate betting passano di li':
    flumine ``BetfairExecution``, la copertura di ``live_order_worker``) e
    ``streaming.create_stream`` (per mettere il tee sul listener SOLO quando
    sullo stream si chiama ``subscribe_to_orders``; gli stream dei prezzi non
    si toccano);
  * ``Betfair/client.py`` ``BetfairClient.betting_rpc``: il client REST nostro
    (``order_exec`` del desktop, ``omega_market`` di Omega e Mike);
  * ``Betfair/stream/tempi_ordine.py`` ``place``: la DECISIONE (chiave del
    comando, ``emesso_ms``/``decisione_ms`` se il comando li porta) legata al
    ``customerOrderRef`` che l'ordine avra' sulla REST.

INTERRUTTORE ``REGISTRO_ORDINI=0|1``, DI SERIE 0 (come ``sonde.py``: acceso
SOLO se vale ``1``). Spento: gli agganci sono un ``if _ro.attivo()`` falso;
nessun file, nessuna cartella, nessun thread, nessuna istanza avvolta. Anche
acceso il registratore e' spento nel banco (``Betfair.stream.backtest``
caricato) e sotto pytest (salvo i test di questo modulo).

AGGANCI (11/10): lo stesso tee dello stream ordini serve anche al monitor
"Salute" (``MONITOR_SALUTE``, interruttore indipendente): ``build_client``
chiama ``aggancia_api_client`` se ALMENO UNO dei due e' acceso; il tee scrive
su disco solo a registratore acceso e conta gli ``ocm`` in "Salute"
(``sonde.osserva_stream("ordini-<sport>", riga)``) solo a monitor acceso.
Registratore spento e monitor acceso: si avvolge solo ``create_stream`` (mai
``betting.request``), nessuno scrittore, nessun file, nessun thread.

PERCORSO CALDO. Sul thread dello stream e su quello della REST si fa solo:
due letture d'orologio, un numero di sequenza e un ``deque.append`` (mai un
lucchetto, mai un'attesa). Se la coda e' piena la riga si PERDE (contata, e il
buco si vede nella sequenza): mai frenare un ordine per registrarlo. La REST
serializza richiesta e risposta DOPO la risposta (decine di microsecondi su una
chiamata da decine di millisecondi). Il resto (gzip, rotazione, tetto) lo fa
UN thread a parte, demone, avviato solo al primo record e solo se acceso.

DOVE: ``<LIVE_STREAM_DATA_DIR>/_ordini/<AAAAMMGG>/ordini_<servizio>_<pid>.jsonl.gz``
(la cartella del raw, ``config_stream.DATA_DIR``; ``REGISTRO_ORDINI_DIR`` la
sostituisce). Un file per processo e per giorno (UTC), JSON per riga, gzip con
svuotamento ogni secondo (un arresto brusco perde al piu' l'ultimo secondo, il
lettore tollera la coda tronca). Tetto ``REGISTRO_ORDINI_TETTO_MB`` (di serie
512): oltre il tetto si cancellano i file piu' vecchi (mai quello aperto); se
non basta si smette di scrivere finche' non si rientra (righe contate).

DATI SENSIBILI: mai intestazioni HTTP, mai il token di sessione, mai l'app key
(le chiamate betting non portano la password); ogni riga REST passa da una
pulizia che sostituisce token e app key con ``***`` se comparissero in un testo
d'errore.

Ogni funzione pubblica e' best-effort: NON solleva MAI verso il chiamante, e
ogni errore e' loggato col motivo (WARNING, al piu' uno al minuto per motivo).
ASCII-only; commenti in italiano.
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
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple

from . import sonde as _mon  # agganci (11/10): ocm contati in "Salute" (spento di serie)

logger = logging.getLogger(__name__)

ENV = "REGISTRO_ORDINI"
ENV_DIR = "REGISTRO_ORDINI_DIR"
ENV_TETTO = "REGISTRO_ORDINI_TETTO_MB"
TETTO_DEFAULT_MB = 512.0
SOTTOCARTELLA = "_ordini"
PREFISSO_FILE = "ordini_"
ESTENSIONE = ".jsonl.gz"
VERSIONE_FORMATO = 1

#: righe in attesa del thread di scrittura oltre le quali si perde (contato)
CODA_MAX = 50_000
#: ... e byte in attesa (stessa regola: si perde, contato)
CODA_MAX_BYTE = 64 * 1024 * 1024
#: dopo un avvio fallito del thread di scrittura si riprova fra (s)
RIPROVA_AVVIO_S = 60.0
#: ``chiudi`` (atexit) non aspetta il thread di scrittura oltre (s)
CHIUDI_ATTESA_S = 2.0
#: dopo un errore di file si riapre (in un file nuovo) non prima di (s)
RIAPRI_DOPO_ERRORE_S = 5.0
#: ogni quanto il thread di scrittura svuota la coda e il gzip (s)
GIRO_S = 0.1
SVUOTA_GZIP_S = 1.0
#: ogni quanto si ricontrolla il tetto di disco (s)
POTATURA_S = 600.0
#: un file toccato negli ultimi RECENTE_S secondi non si pota (e' di un vivo)
RECENTE_S = 900.0

#: i metodi REST che muovono soldi (nome breve, senza ``SportsAPING/v1.0/``)
METODI_SOLDI = frozenset({"placeOrders", "cancelOrders", "replaceOrders", "updateOrders"})

#: ``customerStrategyRef`` del terminale manuale (stessi valori di
#: ``tennis_scalper/ordini_esterni.py`` RIF_MANUALE_*) e del desktop watchlist
#: (``order_exec.py``): qui non si importano i worker
_RIF_DESKTOP = {"live": "desktop", "tennis": "desktop", "watchlist": "desktop_watchlist"}

_MARCA = "_registro_ordini_m1"

#: test di questo modulo: True permette l'accensione sotto pytest
_consenti_in_test = False

_STATO: Dict[str, Any] = {"deciso": None}
_LOCK = threading.Lock()
_ULTIMO_AVVISO: Dict[str, float] = {}


# ---------------------------------------------------------------------------
# interruttore
# ---------------------------------------------------------------------------
def interruttore_acceso() -> bool:
    """``REGISTRO_ORDINI=1`` nell'ambiente (qualunque altro valore = spento)."""
    return (os.environ.get(ENV) or "0").strip() == "1"


def nel_banco() -> bool:
    """True se nel processo e' caricato il banco di replay."""
    return any(m == "Betfair.stream.backtest" or m.startswith("Betfair.stream.backtest.")
               for m in list(sys.modules))


def in_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ and not _consenti_in_test


def attivo() -> bool:
    """Deciso UNA volta per processo, al primo aggancio (dopo il ``.env``: gli
    agganci stanno dove servono le credenziali). Non solleva mai."""
    d = _STATO.get("deciso")
    if d is not None:
        return d
    try:
        acceso = interruttore_acceso() and not in_pytest() and not nel_banco()
    except Exception:  # noqa: BLE001
        acceso = False
    _STATO["deciso"] = bool(acceso)
    if acceso:
        logger.info("[registro-ordini] ACCESO (stream ordini e REST con soldi su disco)")
    return bool(acceso)


def _avvisa(motivo: str, testo: str, *args: Any) -> None:
    """WARNING col motivo, al piu' uno al minuto per motivo."""
    try:
        adesso = time.monotonic()
        if adesso - _ULTIMO_AVVISO.get(motivo, -1e9) >= 60.0:
            _ULTIMO_AVVISO[motivo] = adesso
            logger.warning("[registro-ordini] " + testo, *args)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# orologi
# ---------------------------------------------------------------------------
def adesso_us() -> Tuple[int, int]:
    """(epoca in microsecondi, orologio monotono in microsecondi).

    Il monotono e' ``perf_counter``: su Windows e' QueryPerformanceCounter, su
    Linux CLOCK_MONOTONIC, entrambi comuni a tutti i processi della macchina
    (le durate si confrontano fra file di processi diversi)."""
    return time.time_ns() // 1000, time.perf_counter_ns() // 1000


def _adesso_sicuro() -> Tuple[int, int]:
    """``adesso_us`` che non solleva mai (sui percorsi dei soldi)."""
    try:
        return adesso_us()
    except Exception as ex:  # noqa: BLE001
        _avvisa("orologio", "orologio non letto: %s", str(ex)[:160])
        return 0, 0


# ---------------------------------------------------------------------------
# il thread di scrittura (uno per processo)
# ---------------------------------------------------------------------------
def _nome_servizio() -> str:
    """Il nome del processo per il file: servizio del monitor se acceso, poi il
    modulo di ``python -m``, poi lo script."""
    nome = None
    try:
        from . import sonde as _mon

        nome = (_mon.stato() or {}).get("servizio")
    except Exception:  # noqa: BLE001
        nome = None
    if not nome:
        main = sys.modules.get("__main__")
        spec = getattr(main, "__spec__", None)
        nome = getattr(spec, "name", None)
    if not nome:
        nome = os.path.splitext(os.path.basename(sys.argv[0] if sys.argv else ""))[0]
    nome = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(nome or "processo"))[:60].strip("-.")
    return nome or "processo"


def cartella_base() -> str:
    """``REGISTRO_ORDINI_DIR`` se impostata, altrimenti ``<DATA_DIR del raw>/_ordini``."""
    d = (os.environ.get(ENV_DIR) or "").strip()
    if d:
        return d
    from Betfair.stream.config_stream import DATA_DIR

    return os.path.join(DATA_DIR, SOTTOCARTELLA)


def tetto_byte() -> int:
    raw = (os.environ.get(ENV_TETTO) or "").strip()
    try:
        mb = float(raw) if raw else TETTO_DEFAULT_MB
    except ValueError:
        mb = TETTO_DEFAULT_MB
    if mb <= 0:
        mb = TETTO_DEFAULT_MB
    return int(mb * 1024 * 1024)


def giorno_utc(ep_s: Optional[float] = None) -> str:
    return time.strftime("%Y%m%d", time.gmtime(time.time() if ep_s is None else ep_s))


class Scrittore:
    """Coda senza lucchetti (``deque``) + un thread demone che scrive.

    ``metti_*`` sono i soli metodi chiamati dai thread del bot: non scrivono,
    non aspettano, non sollevano."""

    def __init__(self, cartella: Optional[str] = None, servizio: Optional[str] = None,
                 tetto: Optional[int] = None, avvia_thread: bool = True) -> None:
        self._cartella = cartella
        self._servizio = servizio
        self._tetto = tetto
        self._avvia_thread = avvia_thread
        self._coda: Deque[Any] = collections.deque()
        self._seq = itertools.count(1)
        self._thread: Optional[threading.Thread] = None
        self._io = threading.Lock()          # solo fra thread di scrittura e atexit
        self._fermo = threading.Event()
        self._fh: Any = None
        self._percorso: Optional[str] = None
        self._giorno: Optional[str] = None
        self._sporco = False
        self._ultimo_svuota = 0.0
        self._ultima_potatura = 0.0
        self._pieno = False
        self._chiuso = False
        # contatori (letti dai test e scritti nella riga di chiusura)
        self.persi_coda = 0
        self.scartati_tetto = 0
        self.errori_scrittura = 0
        self.righe_scritte = 0
        self.byte_scritti = 0
        self.file_potati = 0
        self.avvii_falliti = 0
        self.scartati_errore = 0
        self._riapri_dopo = 0.0
        # byte in coda = entrati - usciti. ``entrati`` lo scrivono i thread del
        # bot senza lucchetto: un aggiornamento perso fa CONTARE MENO (mai uno
        # scarto in piu'); ``usciti`` lo scrive solo il thread di scrittura.
        self._byte_entrati = 0
        self._byte_usciti = 0
        self._prossimo_avvio = 0.0

    # -- percorso caldo ----------------------------------------------------
    def _accoda(self, voce: Any, n_byte: int) -> None:
        if self._chiuso:
            return
        if len(self._coda) >= CODA_MAX or \
                self._byte_entrati - self._byte_usciti >= CODA_MAX_BYTE:
            self.persi_coda += 1
            return
        self._byte_entrati += n_byte
        self._coda.append(voce)
        if self._thread is None and self._avvia_thread and \
                time.monotonic() >= self._prossimo_avvio:
            self._avvia()

    @staticmethod
    def _dimensione(voce: Any) -> int:
        """I byte di una voce, calcolati UGUALI in entrata e in uscita."""
        dato = voce[5] if voce[0] == "s" else voce[1]
        return len(dato) if isinstance(dato, (str, bytes)) else 0

    def metti_stream(self, sid: int, raw: Any) -> None:
        """Una riga grezza dello stream ordini (dal ``on_data`` del listener)."""
        try:
            ep, mono = adesso_us()
            voce = ("s", next(self._seq), ep, mono, sid, raw)
            self._accoda(voce, self._dimensione(voce))
        except Exception as ex:  # noqa: BLE001
            _avvisa("metti_stream", "riga dello stream non accodata: %s", str(ex)[:160])

    def metti_record(self, rec: Dict[str, Any], segreti: Iterable[Any] = ()) -> None:
        """Un record gia' composto (REST, sottoscrizione, decisione)."""
        try:
            rec["seq"] = next(self._seq)
            riga = json.dumps(rec, separators=(",", ":"), ensure_ascii=True, default=str)
            voce = ("l", riga, tuple(s for s in segreti if isinstance(s, str) and len(s) >= 8))
            self._accoda(voce, self._dimensione(voce))
        except Exception as ex:  # noqa: BLE001
            _avvisa("metti_record", "record %s non accodato: %s", rec.get("k"), str(ex)[:160])

    # -- thread di scrittura -------------------------------------------------
    def _avvia(self) -> None:
        with _LOCK:
            if self._thread is not None:
                return
            try:
                t = threading.Thread(target=self._giro_continuo, name="registro-ordini",
                                     daemon=True)
                t.start()
            except Exception as ex:  # noqa: BLE001 - mai verso il bot
                self.avvii_falliti += 1
                self._prossimo_avvio = time.monotonic() + RIPROVA_AVVIO_S
                _avvisa("avvio", "thread di scrittura non avviato (riprovo fra %.0f s): %s",
                        RIPROVA_AVVIO_S, str(ex)[:160])
                return
            self._thread = t        # SOLO dopo un avvio riuscito
            _registra_fork()
            try:
                atexit.register(self.chiudi)
            except Exception:  # noqa: BLE001
                pass

    def dimentica_nel_figlio(self) -> None:
        """Nel FIGLIO di un ``fork``: il file e' del padre. Il figlio non scrive
        mai (nemmeno alla chiusura): lo scrittore e' chiuso, la coda vuota, e il
        descrittore ereditato punta a /dev/null (cosi' anche un ``close`` del
        gzip ereditato, o lo svuotamento dei suoi buffer, non tocca il file)."""
        self._chiuso = True
        self._io = threading.Lock()
        self._coda = collections.deque()
        fh, self._fh = self._fh, None
        if fh is None:
            return
        _ORFANI.append(fh)
        f = getattr(fh, "myfileobj", None) or getattr(fh, "fileobj", None)
        try:
            fd = f.fileno()
            nul = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(nul, fd)
            finally:
                os.close(nul)
        except Exception:  # noqa: BLE001
            pass

    def _giro_continuo(self) -> None:
        while not self._fermo.is_set():
            try:
                self.giro()
            except Exception as ex:  # noqa: BLE001 - il thread non muore mai
                _avvisa("giro", "giro di scrittura KO: %s", str(ex)[:160])
            self._fermo.wait(GIRO_S)

    def giro(self, forza_svuota: bool = False) -> int:
        """Scrive cio' che e' in coda. Ritorna le righe scritte (test)."""
        n = 0
        with self._io:
            if self._chiuso:
                return 0
            n = self._scrivi_coda()
            adesso = time.monotonic()
            if self._fh is not None and self._sporco and (
                    forza_svuota or adesso - self._ultimo_svuota >= SVUOTA_GZIP_S):
                try:
                    self._fh.flush()
                    self._sporco = False
                    self._ultimo_svuota = adesso
                except Exception as ex:  # noqa: BLE001
                    self._errore_file("svuotamento gzip KO: %s" % str(ex)[:160])
            if adesso - self._ultima_potatura >= POTATURA_S:
                self._potatura()
        return n

    def _scrivi_coda(self) -> int:
        n = 0
        while self._coda:
            try:
                voce = self._coda.popleft()
            except IndexError:
                break
            self._byte_usciti += self._dimensione(voce)
            try:
                riga = self._riga(voce)
            except Exception as ex:  # noqa: BLE001
                _avvisa("riga", "riga non composta (scartata): %s", str(ex)[:160])
                continue
            if self._scrivi_riga(riga):
                n += 1
        return n

    @staticmethod
    def _riga(voce: Any) -> str:
        if voce[0] == "s":
            _, seq, ep, mono, sid, raw = voce
            testo = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            testo = testo.strip()
            testa = '{"k":"stream","seq":%d,"ep_us":%d,"mono_us":%d,"sid":%d' % (
                seq, ep, mono, int(sid))
            if testo.startswith("{") and testo.endswith("}") and "\n" not in testo:
                # la riga di Betfair VERBATIM (nessuna ri-serializzazione)
                return testa + ',"msg":' + testo + "}"
            return testa + ',"txt":' + json.dumps(testo, ensure_ascii=True) + "}"
        _, riga, segreti = voce
        for s in segreti:
            if s in riga:
                riga = riga.replace(s, "***")
        return riga

    def _scrivi_riga(self, riga: str) -> bool:
        giorno = giorno_utc()
        if self._fh is None or giorno != self._giorno:
            if self._fh is not None:
                self._chiudi_file("giorno")
            if time.monotonic() < self._riapri_dopo:
                # dopo un errore di file (disco pieno...) non si riapre a ogni
                # riga: si aspetta RIAPRI_DOPO_ERRORE_S, contando cio' che si perde
                self.scartati_errore += 1
                return False
            if not self._apri(giorno):
                return False
        if self._pieno:
            self.scartati_tetto += 1
            return False
        dati = (riga + "\n").encode("utf-8", "replace")
        try:
            self._fh.write(dati)
        except Exception as ex:  # noqa: BLE001
            self._errore_file("scrittura KO: %s" % str(ex)[:160])
            return False
        self._sporco = True
        self.righe_scritte += 1
        self.byte_scritti += len(dati)
        return True

    def _errore_file(self, motivo: str) -> None:
        """Handle rotto: si chiude e si riapre alla riga dopo (come il tee raw)."""
        self.errori_scrittura += 1
        self._riapri_dopo = time.monotonic() + RIAPRI_DOPO_ERRORE_S
        _avvisa("file", "%s (file %s, riapro fra %.0f s in un file NUOVO)", motivo,
                self._percorso, RIAPRI_DOPO_ERRORE_S)
        fh, self._fh = self._fh, None
        if fh is not None:
            try:
                fh.close()
            except Exception:  # noqa: BLE001
                pass

    def cartella(self) -> str:
        if self._cartella is None:
            self._cartella = cartella_base()
        return self._cartella

    def _apri(self, giorno: str) -> bool:
        try:
            if self._servizio is None:
                self._servizio = _nome_servizio()
            d = os.path.join(self.cartella(), giorno)
            os.makedirs(d, exist_ok=True)
            percorso = self._nome_libero(d)
            # MAI in coda a un file non vuoto (pid riusato, riapertura dopo un
            # errore di disco): un membro gzip tronco seguito da un altro rende
            # illeggibile cio' che segue. Sempre un file nuovo.
            self._fh = gzip.open(percorso, "wb", compresslevel=6)  # noqa: SIM115 - chiuso in chiudi()
            self._percorso = percorso
            self._giorno = giorno
            self._ultima_potatura = 0.0
            self._potatura()
            ep, mono = adesso_us()
            testa = {"k": "avvio", "seq": 0, "ep_us": ep, "mono_us": mono,
                     "versione": VERSIONE_FORMATO, "servizio": self._servizio,
                     "pid": os.getpid(), "giorno": giorno, "tetto_mb": round(self.tetto() / 1048576, 1),
                     "librerie": _versioni()}
            dati = (json.dumps(testa, separators=(",", ":")) + "\n").encode("ascii", "replace")
            self._fh.write(dati)
            self._sporco = True
            logger.info("[registro-ordini] scrivo %s", percorso)
            return True
        except Exception as ex:  # noqa: BLE001
            self._errore_file("apertura KO: %s" % str(ex)[:160])
            return False

    def _nome_libero(self, d: str) -> str:
        """``ordini_<servizio>_<pid>.jsonl.gz``, poi ``_2``, ``_3``...: il primo
        che non esiste (o e' vuoto)."""
        radice = "%s%s_%d" % (PREFISSO_FILE, self._servizio, os.getpid())
        for n in range(1, 10_000):
            p = os.path.join(d, radice + ("" if n == 1 else "_%d" % n) + ESTENSIONE)
            if not os.path.exists(p) or os.path.getsize(p) == 0:
                return p
        raise OSError("nessun nome libero per %s" % radice)

    def tetto(self) -> int:
        if self._tetto is None:
            self._tetto = tetto_byte()
        return int(self._tetto)

    def _potatura(self) -> None:
        """Il tetto di disco: oltre il tetto si cancellano i file piu' vecchi
        (mai quello aperto da questo processo); se non basta, si smette di
        scrivere fino al prossimo controllo."""
        self._ultima_potatura = time.monotonic()
        try:
            base = self.cartella()
            if not os.path.isdir(base):
                self._pieno = False
                return
            mio = os.path.abspath(self._percorso) if self._percorso else None
            if self._fh is not None and self._sporco:
                try:
                    self._fh.flush()
                    self._sporco = False
                except Exception:  # noqa: BLE001
                    pass
            voci: List[Tuple[float, str, int]] = []
            for radice, _dirs, files in os.walk(base):
                for f in files:
                    if f.startswith(PREFISSO_FILE) and f.endswith(ESTENSIONE):
                        p = os.path.join(radice, f)
                        try:
                            st = os.stat(p)
                        except OSError:
                            continue
                        voci.append((st.st_mtime, p, st.st_size))
            totale = sum(v[2] for v in voci)
            tetto = self.tetto()
            recente = time.time() - RECENTE_S
            if totale > tetto:
                for mt, p, dim in sorted(voci):
                    if totale <= tetto:
                        break
                    if mio is not None and os.path.abspath(p) == mio:
                        continue
                    if mt > recente:
                        # scritto da poco: probabilmente aperto da un altro
                        # processo vivo (su Linux lo si cancellerebbe sotto i
                        # suoi piedi); resta, e se non basta si smette di scrivere
                        continue
                    try:
                        os.remove(p)
                        totale -= dim
                        self.file_potati += 1
                        logger.info("[registro-ordini] tetto %d MB: cancellato %s",
                                    tetto // 1048576, p)
                    except OSError as ex:
                        _avvisa("potatura", "file %s non cancellato: %s", p, str(ex)[:160])
                self._togli_cartelle_vuote(base)
            pieno = totale > tetto
            if pieno and not self._pieno:
                _avvisa("pieno", "tetto di disco %d MB raggiunto anche dopo la potatura: "
                        "smetto di scrivere fino al prossimo controllo", tetto // 1048576)
            self._pieno = pieno
        except Exception as ex:  # noqa: BLE001
            _avvisa("potatura", "controllo del tetto KO: %s", str(ex)[:160])

    @staticmethod
    def _togli_cartelle_vuote(base: str) -> None:
        try:
            for nome in os.listdir(base):
                if not _RE_GIORNO.fullmatch(nome):
                    continue        # solo le cartelle giorno AAAAMMGG del registratore
                p = os.path.join(base, nome)
                if os.path.isdir(p) and not os.listdir(p):
                    os.rmdir(p)
        except OSError:
            pass

    def _chiudi_file(self, motivo: str) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            ep, mono = adesso_us()
            fine = {"k": "chiusura", "seq": 0, "ep_us": ep, "mono_us": mono, "motivo": motivo,
                    "persi_coda": self.persi_coda, "scartati_tetto": self.scartati_tetto,
                    "errori_scrittura": self.errori_scrittura,
                    "righe_scritte": self.righe_scritte,
                    "scartati_errore": self.scartati_errore}
            fh.write((json.dumps(fine, separators=(",", ":")) + "\n").encode("ascii"))
        except Exception as ex:  # noqa: BLE001
            _avvisa("chiusura", "riga di chiusura KO: %s", str(ex)[:160])
        try:
            fh.close()
        except Exception as ex:  # noqa: BLE001
            _avvisa("chiusura", "chiusura del file KO: %s", str(ex)[:160])
        self._fh = None
        self._sporco = False

    def chiudi(self) -> None:
        """Fine processo: scrive cio' che resta e chiude il file. Idempotente.
        Non aspetta il thread di scrittura oltre ``CHIUDI_ATTESA_S`` (un disco
        appeso non deve trattenere l'uscita del processo)."""
        try:
            if self._chiuso:
                return
            self._fermo.set()
            if not self._io.acquire(timeout=CHIUDI_ATTESA_S):
                self._chiuso = True
                _avvisa("chiudi", "scrittura occupata da oltre %.1f s: chiudo senza "
                        "svuotare la coda", CHIUDI_ATTESA_S)
                return
            try:
                if self._chiuso:
                    return
                self._riapri_dopo = 0.0      # all'uscita si ritenta subito
                self._scrivi_coda()
                if self._fh is None and self._percorso is not None:
                    # il file era stato chiuso da un errore: la riga di chiusura
                    # (con i contatori delle perdite) va comunque in un file nuovo
                    self._apri(giorno_utc())
                self._chiudi_file("fine_processo")
                self._chiuso = True
            finally:
                self._io.release()
        except Exception as ex:  # noqa: BLE001
            _avvisa("chiudi", "chiusura KO: %s", str(ex)[:160])


def _versioni() -> Dict[str, Any]:
    out: Dict[str, Any] = {"python": sys.version.split()[0]}
    for nome in ("betfairlightweight", "flumine"):
        m = sys.modules.get(nome)
        if m is not None:
            out[nome] = getattr(m, "__version__", None)
    return out


_SCRITTORE: Optional[Scrittore] = None
_RE_GIORNO = re.compile(r"\d{8}")
#: gzip ereditati da un fork: tenuti vivi nel figlio (puntano a /dev/null)
_ORFANI: List[Any] = []
_FORK: Dict[str, bool] = {"registrato": False}


def _dopo_fork_nel_figlio() -> None:
    s = _SCRITTORE
    if s is not None:
        try:
            s.dimentica_nel_figlio()
        except Exception:  # noqa: BLE001
            pass


def _registra_fork() -> None:
    """Una volta per processo, solo a registratore avviato (Windows: niente fork)."""
    if _FORK["registrato"] or not hasattr(os, "register_at_fork"):
        return
    try:
        os.register_at_fork(after_in_child=_dopo_fork_nel_figlio)
        _FORK["registrato"] = True
    except Exception as ex:  # noqa: BLE001
        _avvisa("fork", "gancio del fork non registrato: %s", str(ex)[:160])


def scrittore() -> Scrittore:
    global _SCRITTORE  # noqa: PLW0603 - uno per processo
    s = _SCRITTORE
    if s is None:
        with _LOCK:
            if _SCRITTORE is None:
                _SCRITTORE = Scrittore()
            s = _SCRITTORE
    return s


def _azzera_per_test(nuovo: Optional[Scrittore] = None) -> None:
    """Solo test: decisione e scrittore dimenticati."""
    global _SCRITTORE  # noqa: PLW0603
    _STATO["deciso"] = None
    _ULTIMO_AVVISO.clear()
    _SCRITTORE = nuovo


# ---------------------------------------------------------------------------
# REST: chi, cosa, quando
# ---------------------------------------------------------------------------
def nome_metodo(method: Any) -> str:
    return str(method or "").rsplit("/", 1)[-1]


def metodo_soldi(method: Any) -> bool:
    return nome_metodo(method) in METODI_SOLDI


def attore_da(params: Any) -> str:
    """Chi ha fatto la chiamata, dai riferimenti: ``desktop`` (terminale manuale
    ``live``/``tennis``), ``desktop_watchlist`` (``order_exec``), ``bot:<ref>``
    per ogni altro ``customerStrategyRef``. ``?`` quando la richiesta non lo porta
    (cancel/replace/update: si ricava dal ``betId`` in lettura)."""
    if not isinstance(params, dict):
        return "?"
    csr = params.get("customerStrategyRef")
    if not csr:
        return "?"
    c = str(csr).strip()
    return _RIF_DESKTOP.get(c.lower(), "bot:" + c)


def _codici(risposta: Any) -> Tuple[Optional[str], Optional[str], List[Any]]:
    """(status, errorCode, [errorCode per istruzione]) di un ExecutionReport."""
    if not isinstance(risposta, dict):
        return None, None, []
    res = risposta.get("result", risposta)
    if not isinstance(res, dict):
        return None, None, []
    codici = []
    for r in res.get("instructionReports") or []:
        if isinstance(r, dict):
            codici.append(r.get("errorCode"))
    return res.get("status"), res.get("errorCode"), codici


def _rif_istruzioni(params: Any) -> List[Any]:
    out = []
    if isinstance(params, dict):
        for i in params.get("instructions") or []:
            if isinstance(i, dict):
                out.append(i.get("customerOrderRef"))
    return out


def registra_rest(*, via: str, method: Any, params: Any, invio: Tuple[int, int],
                  risposta: Tuple[int, int], esito: Any = None, eccezione: Any = None,
                  segreti: Iterable[Any] = ()) -> None:
    """Un record ``rest``. ``esito`` = il JSON della risposta (busta JSON-RPC
    di betfairlightweight o il ``result`` del client nostro). Non solleva."""
    try:
        nome = nome_metodo(method)
        stato, codice, codici = _codici(esito)
        rec: Dict[str, Any] = {
            "k": "rest", "via": via, "metodo": nome,
            "ep_us": invio[0], "mono_us": invio[1],
            "risposta_ep_us": risposta[0], "risposta_mono_us": risposta[1],
            "durata_ms": round((risposta[1] - invio[1]) / 1000.0, 3),
            "market_id": params.get("marketId") if isinstance(params, dict) else None,
            "attore": attore_da(params),
            "csr": params.get("customerStrategyRef") if isinstance(params, dict) else None,
            "cref": params.get("customerRef") if isinstance(params, dict) else None,
            "corefs": _rif_istruzioni(params),
            "thread": threading.current_thread().name,
            "richiesta": params,
            "risposta": esito,
            "stato": stato, "errore": codice, "codici": codici,
        }
        if eccezione is not None:
            rec["eccezione"] = "%s: %s" % (type(eccezione).__name__, str(eccezione)[:400])
            r = getattr(eccezione, "response", None)
            if isinstance(r, dict) and esito is None:
                rec["risposta"] = r
                rec["stato"], rec["errore"], rec["codici"] = _codici(r)
                if rec["errore"] is None:
                    err = r.get("error")
                    if isinstance(err, dict):
                        dati = err.get("data") or {}
                        exc = dati.get("APINGException") if isinstance(dati, dict) else None
                        rec["errore"] = (exc or {}).get("errorCode") if isinstance(exc, dict) \
                            else err.get("message")
        scrittore().metti_record(rec, segreti)
    except Exception as ex:  # noqa: BLE001
        _avvisa("rest", "chiamata %s non registrata: %s", method, str(ex)[:160])


def _leggi_segreti(segreti: Any) -> Tuple[Any, ...]:
    """I segreti da oscurare: una tupla, o una funzione che li legge ADESSO
    (il token puo' cambiare durante la chiamata se il client rifa' il login)."""
    try:
        valori = segreti() if callable(segreti) else segreti
        return tuple(valori or ())
    except Exception as ex:  # noqa: BLE001
        _avvisa("segreti", "segreti non letti: %s", str(ex)[:160])
        return ()


def _registra_sicuro(**kwargs: Any) -> None:
    """``registra_rest`` che non solleva MAI (secondo strato: la chiamata a
    Betfair e' gia' avvenuta, il suo esito deve tornare al chiamante)."""
    try:
        registra_rest(**kwargs)
    except Exception as ex:  # noqa: BLE001
        _avvisa("rest", "chiamata %s non registrata: %s", kwargs.get("method"), str(ex)[:160])


def rest_nostro(method: str, params: Dict[str, Any], chiama: Callable[[], Any],
                segreti: Any = ()) -> Any:
    """``BetfairClient.betting_rpc`` (client REST nostro): esegue ``chiama`` UNA
    volta sola, identica, e ne registra richiesta e risultato. L'esito o
    l'eccezione (lo STESSO oggetto) tornano al chiamante tali e quali.
    ``segreti`` (tupla o funzione) si leggono prima e DOPO la chiamata."""
    prima = _leggi_segreti(segreti)
    invio = _adesso_sicuro()
    try:
        out = chiama()
    except BaseException as ex:
        _registra_sicuro(via="rest_nostro", method=method, params=params, invio=invio,
                         risposta=_adesso_sicuro(), eccezione=ex,
                         segreti=prima + _leggi_segreti(segreti))
        raise
    _registra_sicuro(via="rest_nostro", method=method, params=params, invio=invio,
                     risposta=_adesso_sicuro(), esito=out,
                     segreti=prima + _leggi_segreti(segreti))
    return out


# ---------------------------------------------------------------------------
# betfairlightweight: l'APIClient di ``build_client``
# ---------------------------------------------------------------------------
def _segreti_di(client: Any) -> Tuple[Any, ...]:
    """Token e app key dell'APIClient, letti ADESSO (prima e dopo la chiamata)."""
    out = []
    for nome in ("session_token", "app_key"):
        try:
            out.append(getattr(client, nome, None))
        except Exception:  # noqa: BLE001
            pass
    return tuple(out)


def _avvolgi_request(client: Any, endpoint: Any) -> None:
    originale = endpoint.request

    def request(*args: Any, **kwargs: Any) -> Any:
        method = args[0] if args else kwargs.get("method")
        try:
            soldi = metodo_soldi(method)
        except Exception:  # noqa: BLE001
            soldi = False
        if not soldi:
            return originale(*args, **kwargs)
        params = args[1] if len(args) > 1 else kwargs.get("params")
        prima = _segreti_di(client)
        invio = _adesso_sicuro()
        # UNA sola chiamata a Betfair; il suo esito (o la sua eccezione, lo
        # stesso oggetto) torna al chiamante qualunque cosa faccia la registrazione
        try:
            out = originale(*args, **kwargs)
        except BaseException as ex:
            _registra_sicuro(via="bflw", method=method, params=params, invio=invio,
                             risposta=_adesso_sicuro(), eccezione=ex,
                             segreti=prima + _segreti_di(client))
            raise
        try:
            esito = out[1] if isinstance(out, tuple) and len(out) > 1 else None
        except Exception:  # noqa: BLE001
            esito = None
        _registra_sicuro(via="bflw", method=method, params=params, invio=invio,
                         risposta=_adesso_sicuro(), esito=esito,
                         segreti=prima + _segreti_di(client))
        return out

    setattr(request, _MARCA, True)
    endpoint.request = request


_SID = itertools.count(1)


def sorgente_salute() -> Optional[str]:
    """La sorgente con cui la "Salute" conta i messaggi dello stream ORDINI:
    ``ordini-<sport>`` (lo sport che il servizio ha dato a ``sonde.avvia``;
    senza sport, il nome del servizio). ``None`` a monitor spento. Nessuna
    lettura nuova: solo lo stato in memoria del monitor. Non solleva mai."""
    try:
        if not _mon.ATTIVO:
            return None
        st = _mon.stato() or {}
        nome = st.get("sport") or st.get("servizio") or "processo"
        return "ordini-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", str(nome))[:30]
    except Exception:  # noqa: BLE001
        return None


def _monta_tee(stream: Any, kwargs: Dict[str, Any], args: Tuple[Any, ...]) -> None:
    """Il tee sul listener dello stream ordini (una volta per listener; a ogni
    sottoscrizione nuova un ``sid`` nuovo e un record ``sub``).

    Agganci (11/10): il tee ha DUE usi indipendenti, ciascuno col suo
    interruttore. Registratore acceso (``REGISTRO_ORDINI``): la riga su disco e
    il record ``sub``. Monitor acceso (``MONITOR_SALUTE``): il conteggio degli
    ``ocm`` in "Salute" (``sonde.osserva_stream``). Con uno solo dei due acceso
    l'altro non lascia traccia (registratore spento: nessuno scrittore, nessun
    file, nessun thread)."""
    listener = getattr(stream, "listener", None)
    if listener is None:
        return
    registra = attivo()
    sid = next(_SID)
    attuale = getattr(listener, "on_data", None)
    contesto = getattr(attuale, "_contesto_m1", None)
    if contesto is not None:
        contesto["sid"] = sid
    elif callable(attuale):
        originale = attuale
        contesto = {"sid": sid}
        scr = scrittore() if registra else None
        sorgente = sorgente_salute()

        def on_data(raw_data: Any) -> Any:
            try:
                if scr is not None:
                    scr.metti_stream(contesto["sid"], raw_data)
            except Exception as ex:  # noqa: BLE001 - mai rompere lo stream
                _avvisa("tee", "tee dello stream ordini KO: %s", str(ex)[:160])
            if sorgente is not None and _mon.ATTIVO:
                try:
                    _mon.osserva_stream(sorgente, raw_data)
                except Exception as ex:  # noqa: BLE001 - la misura non rompe lo stream
                    _avvisa("salute", "ocm non contato in Salute: %s", str(ex)[:160])
            return originale(raw_data)

        setattr(on_data, "_contesto_m1", contesto)
        setattr(on_data, _MARCA, True)
        listener.on_data = on_data
    if not registra:
        return
    nomi = ("order_filter", "initial_clk", "clk", "conflate_ms", "heartbeat_ms",
            "segmentation_enabled")
    valori = dict(zip(nomi, args))
    valori.update({k: v for k, v in kwargs.items() if k in nomi})
    ep, mono = adesso_us()
    scrittore().metti_record({
        "k": "sub", "ep_us": ep, "mono_us": mono, "sid": sid,
        "unique_id": getattr(stream, "unique_id", None),
        "filtro": valori.get("order_filter"),
        "initial_clk": valori.get("initial_clk"), "clk": valori.get("clk"),
        "conflate_ms": valori.get("conflate_ms"), "heartbeat_ms": valori.get("heartbeat_ms"),
        "ripresa": bool(valori.get("initial_clk") and valori.get("clk")),
        "thread": threading.current_thread().name,
    })


def _avvolgi_create_stream(streaming: Any) -> None:
    originale = streaming.create_stream

    def create_stream(*args: Any, **kwargs: Any) -> Any:
        stream = originale(*args, **kwargs)
        try:
            sub = getattr(stream, "subscribe_to_orders", None)
            if callable(sub) and not getattr(sub, _MARCA, False):
                def subscribe_to_orders(*a: Any, **kw: Any) -> Any:
                    try:
                        _monta_tee(stream, kw, a)
                    except Exception as ex:  # noqa: BLE001
                        _avvisa("sub", "tee dello stream ordini non montato: %s", str(ex)[:160])
                    return sub(*a, **kw)

                setattr(subscribe_to_orders, _MARCA, True)
                stream.subscribe_to_orders = subscribe_to_orders
        except Exception as ex:  # noqa: BLE001
            _avvisa("create_stream", "stream non osservato: %s", str(ex)[:160])
        return stream

    setattr(create_stream, _MARCA, True)
    streaming.create_stream = create_stream


def aggancia_api_client(client: Any) -> Any:
    """Avvolge, sulla SOLA istanza, ``client.betting.request`` (REST con soldi) e
    ``client.streaming.create_stream`` (tee dello stream ordini). Idempotente.
    Ritorna il client (lo stesso oggetto). Spento: non tocca niente.

    Agganci (11/10): registratore SPENTO e monitor "Salute" ACCESO = si avvolge
    SOLO ``create_stream`` (tee per contare gli ``ocm``); ``betting.request``
    resta quello di betfairlightweight. Entrambi spenti: non tocca niente."""
    if client is None:
        return client
    registra = attivo()
    if not registra and not _mon.ATTIVO:
        return client
    try:
        betting = getattr(client, "betting", None) if registra else None
        if betting is not None and not getattr(getattr(betting, "request", None), _MARCA, False):
            _avvolgi_request(client, betting)
        streaming = getattr(client, "streaming", None)
        if streaming is not None and not getattr(
                getattr(streaming, "create_stream", None), _MARCA, False):
            _avvolgi_create_stream(streaming)
    except Exception as ex:  # noqa: BLE001 - client finti o versioni diverse
        _avvisa("aggancio", "APIClient non agganciato: %s", str(ex)[:160])
    return client


# ---------------------------------------------------------------------------
# decisione -> ordine (``tempi_ordine.place``)
# ---------------------------------------------------------------------------
def decisione(order: Any, voce: Any) -> None:
    """La decisione dietro un ordine flumine: la chiave del comando e
    l'istante di decisione (``emesso_ms``/``decisione_ms`` se il comando li
    porta), col ``customerOrderRef`` che l'ordine avra' nella REST."""
    if not attivo():
        return
    try:
        try:
            cor = getattr(order, "customer_order_ref", None)
        except Exception:  # noqa: BLE001 - ordine senza trade/strategia
            cor = None
        v = voce if isinstance(voce, dict) else {}
        ep, mono = adesso_us()
        scrittore().metti_record({
            "k": "dec", "ep_us": ep, "mono_us": mono,
            "cor": cor, "ordine": str(getattr(order, "id", "") or "") or None,
            "chiave": v.get("chiave"), "strada": v.get("strada"), "via": v.get("via"),
            "azione": v.get("azione"), "mode": v.get("mode"), "rif": v.get("rif"),
            "decisione_ms": v.get("decisione_ms"), "invio_ms": v.get("invio_ms"),
            "ricezione_ms": v.get("ricezione_wall"),
        })
    except Exception as ex:  # noqa: BLE001
        _avvisa("decisione", "decisione non registrata: %s", str(ex)[:160])
