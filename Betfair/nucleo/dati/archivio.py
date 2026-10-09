"""archivio.py - l'archivio locale INVISIBILE di un processo (W1-G1, implementa ``Archivio``).

Scopo
    Rendere durevole sul PC, fuori dal ciclo di decisione, ogni riga che oggi
    va al cloud, e tenerla in coda per il postino. Tre regimi (04 par. 6.1,
    numeri del laboratorio ``m06``):

    * ``stato_denaro`` -> ``denaro.sqlite3``, WAL ``synchronous=FULL``: durevole
      anche a PC spento (documentazione SQLite); un commit per gruppo di eventi
      arrivati insieme (group commit: ogni evento e' confermato solo dopo il
      SUO commit, la garanzia e' la stessa di "1 commit per evento");
    * ``stato_vivo``   -> ``vivo.sqlite3``, WAL ``synchronous=NORMAL``, lotti fino
      a ``lotto_max`` righe per commit (righe ri-derivabili dallo stream);
    * ``log``          -> ``log/AAAA-MM-GG.jsonl`` (giorno UTC), write+flush:
      0 persi al crash del processo (07 par. 6.1); il file E' la coda del
      postino (offset in ``consegna``), nessuna doppia scrittura.

    Due file SQLite separati (U-55): il checkpoint dell'uno non ferma l'altro.
    UN thread di scrittura per processo (``archivio-scrittore``): il chiamante
    di ``scrivi`` paga solo copia + JSON + accodamento. Riga e outbox nascono
    nella STESSA transazione. ``transizione`` e' un claim atomico eseguito dal
    thread di scrittura (vede tutte le scritture accodate prima).

    Revisione del 09/10 (referto W1-G1, "Correzioni dopo la revisione"):
    * ogni lotto e' diviso in TRE unita' indipendenti (log, denaro, vivo): ognuna
      si conferma da sola; se un commit fallisce si ritenta SOLO quell'unita'
      (un claim gia' confermato non si riesegue, M5); la barriera ``conferma`` e'
      una soglia contigua (nessun numero piu' basso ancora in volo);
    * una voce che non si puo' salvare per un errore DETERMINISTICO (intero oltre
      2^63, chiave con un surrogato...) si isola: va nel file
      ``scarti_scrittore.jsonl`` (dead_letter locale su file, fsync) e il resto del
      lotto prosegue (A2). Gli errori di I/O (disco pieno) si ritentano per sempre;
    * alla chiusura con il disco in errore le voci accettate vanno in
      ``salvataggio-*.jsonl`` e rientrano da sole all'apertura dopo (M6);
    * upsert = FUSIONE delle colonne (come l'upsert di PostgREST di oggi), anche
      nella coalescenza (B2); versione per riga: una versione uguale o piu'
      vecchia di non oltre ``TOLLERANZA_OROLOGIO_US`` (orologio che torna
      indietro) viene portata a "precedente + 1 us" e VINCE; piu' vecchia
      oltre la tolleranza e' un dato stantio: scartata con un evento (M3);
    * outbox letta in ordine FIFO PER CHIAVE: una voce non parte prima di una
      voce piu' vecchia della stessa chiave (M4);
    * dead_letter con CAUSA e rientro automatico (A4); pulizia a pezzi (M7);
      riparazione dei log troncati a blocchi fino all'inizio del file (A3).

Entrate
    ``ArchivioLocale(processo, registro, ...)``; ``apri()``; ``scrivi``,
    ``leggi``, ``transizione``, ``accoda`` (forma sincrona usata dal postino),
    ``conferma(timeout_s)`` (barriera: tutto cio' che e' stato accodato prima e'
    su disco).

Uscite
    File sotto ``percorso.cartella_processo``; eventi ``dati.*`` alla funzione
    ``eventi``; ``misure()`` con p50/p99/max di accodamento, commit, durevole-
    dopo e checkpoint (come ``m06``).

Cosa NON fa
    Mai la rete (il cloud e' del postino). Nessun thread e nessun file
    all'import: tutto nasce in ``apri()`` e muore in ``chiudi()``. Non decide
    nulla sulle righe: ne' soglie ne' stati dei bot. ``apri()`` puo' sollevare
    ``OSError`` (cartella non creabile, disco) o ``ArchivioOccupato``: l'aggancio
    resta allora sulla scrittura di oggi ("vecchio") con un allarme (B3).
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sqlite3
import threading
import time
import uuid
from collections import Counter, deque
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturoScaduto
from pathlib import Path
from typing import (Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Sequence,
                    Tuple, Union)

from .contratto import Operazione, SpecTabella
from .percorso import Lucchetto, cartella_processo, prepara_cartella
from .schema_locale import (applica_schema, chiave_canonica, giorno_utc, iso_da_us, iso_utc, riga_log,
                            rev_ordinabile, tabella_della_riga_log, testo_json)

logger = logging.getLogger(__name__)

Registro = Union[Mapping[str, SpecTabella], Callable[[str], SpecTabella]]
Eventi = Callable[[str, Mapping[str, Any]], None]

REGIMI_SQLITE: Tuple[str, ...] = ("stato_denaro", "stato_vivo")
FILE_DB = {"stato_denaro": "denaro.sqlite3", "stato_vivo": "vivo.sqlite3"}
SINCRONIA = {"stato_denaro": "FULL", "stato_vivo": "NORMAL"}
#: dove vivono marcatori dei log, segnalazioni e dead_letter dei log
REGIME_SERVIZIO = "stato_vivo"
FILE_SCARTI = "scarti_scrittore.jsonl"
PREFISSO_SALVATAGGIO = "salvataggio-"

#: colonne chiave generate nel punto di scrittura se mancano (U-50)
COLONNE_UID = ("uid", "trade_uid")

#: colonna del tempo che il cloud oggi riempie con ``now()`` all'insert: l'archivio
#: la timbra all'ACCODAMENTO (se il chiamante non l'ha scritta), cosi' una consegna
#: tardiva (offline) non sposta l'istante dell'evento. Estensione proposta a
#: ``SpecTabella`` (campo ``colonna_tempo``): referto W1-G1 par. 2.
COLONNE_TEMPO_PREDEFINITE: Mapping[str, str] = {
    "mike_activity": "ts",
    "omega_activity": "ts",
    "safe_strategy_activity": "ts",
    "scalper_activity": "ts",
    "tennis_bot_activity": "ts",
    "live_alerts": "created_at",
    "betfair_live_journal": "ts",
    "betfair_live_audit": "ts",
    "signal_history": "created_at",
    "theta_confirm_requests": "created_at",
}

CONSERVA_GIORNI_PREDEFINITI: Mapping[str, float] = {"stato_denaro": 30.0, "stato_vivo": 2.0, "log": 3.0}
CONSERVA_SEGNALAZIONI_GIORNI = 30.0
_MISURE_MAX = 200_000

#: M3: un orologio che torna indietro fino a 5 s (passo dell'NTP di Windows: 0,84 s
#: misurato, AVANZAMENTO U-62) non fa perdere l'aggiornamento: la versione diventa
#: "precedente + 1 us" e vince, come vince oggi l'ultimo upsert. Oltre: dato stantio.
TOLLERANZA_OROLOGIO_US = 5_000_000
#: A2: tentativi di un lotto prima di isolare la voce velenosa
TENTATIVI_PRIMA_DI_ISOLARE = 3
#: M7: righe cancellate per lavoro di pulizia (il lavoro dura millisecondi)
PULIZIA_PEZZO = 1000
#: A4: rientro automatico delle dead_letter, per causa (millisecondi)
RIENTRO_MS: Mapping[str, int] = {"transitorio": 15 * 60_000, "dato": 24 * 3_600_000, "registro": 24 * 3_600_000}


def _ora_ms() -> int:
    return time.time_ns() // 1_000_000


class ArchivioChiuso(RuntimeError):
    """Scrittura su un archivio non aperto (o in chiusura)."""


def errore_di_dato(exc: BaseException) -> bool:
    """Errore DETERMINISTICO della voce (rifarlo da' lo stesso errore): si isola."""
    return isinstance(exc, (UnicodeError, OverflowError, ValueError, TypeError, sqlite3.InterfaceError,
                            sqlite3.IntegrityError, sqlite3.DataError, sqlite3.ProgrammingError))


def errore_di_io(exc: BaseException) -> bool:
    """Errore del disco o del file (pieno, I/O, bloccato): si ritenta per sempre."""
    return isinstance(exc, (sqlite3.OperationalError, OSError)) and not isinstance(exc, UnicodeError)


# ---------------------------------------------------------------------------
# voci della coda del thread di scrittura
# ---------------------------------------------------------------------------
class _Scrittura:
    __slots__ = ("n", "regime", "tabella", "op", "chiave", "testo", "rev", "rev_col", "coalesce", "ms", "t_ns",
                 "futuro", "avviata")

    def __init__(self, n: int, regime: str, tabella: str, op: str, chiave: str, testo: str,
                 rev: Optional[int], rev_col: Optional[str], coalesce: bool, ms: int, t_ns: int,
                 futuro: Optional["Future[int]"] = None) -> None:
        self.n, self.regime, self.tabella, self.op, self.chiave = n, regime, tabella, op, chiave
        self.testo, self.rev, self.rev_col, self.coalesce, self.ms, self.t_ns = testo, rev, rev_col, coalesce, ms, t_ns
        self.futuro = futuro
        self.avviata = False

    def salvabile(self) -> Dict[str, Any]:
        return {"regime": self.regime, "tabella": self.tabella, "op": self.op, "chiave": self.chiave,
                "testo": self.testo, "rev": self.rev, "rev_col": self.rev_col, "coalesce": self.coalesce,
                "ms": self.ms}


class _Lavoro:
    __slots__ = ("n", "regime", "fn", "futuro", "avviata")

    def __init__(self, n: int, regime: str, fn: Callable[[sqlite3.Connection], Any], futuro: "Future[Any]") -> None:
        self.n, self.regime, self.fn, self.futuro = n, regime, fn, futuro
        self.avviata = False


_FERMA = object()


class VoceOutbox:
    """Una voce della outbox letta dal postino (sola lettura)."""

    __slots__ = ("regime", "seq", "tabella", "op", "chiave", "testo", "tentativi", "creato_ms")

    def __init__(self, regime: str, seq: int, tabella: str, op: str, chiave: Optional[str], testo: str,
                 tentativi: int, creato_ms: int) -> None:
        self.regime, self.seq, self.tabella, self.op, self.chiave = regime, seq, tabella, op, chiave
        self.testo, self.tentativi, self.creato_ms = testo, tentativi, creato_ms


def _percentili(valori: Iterable[float]) -> Dict[str, float]:
    v = sorted(valori)
    if not v:
        return {"n": 0}

    def q(x: float) -> float:
        return v[min(len(v) - 1, max(0, int(round(x * (len(v) - 1)))))]

    return {"n": len(v), "p50": q(0.5), "p95": q(0.95), "p99": q(0.99), "max": v[-1]}


def _eventi_nel_log(nome: str, dati: Mapping[str, Any]) -> None:
    """Destinazione di serie degli eventi: il log del processo (mai il silenzio)."""
    livello = logging.ERROR if nome in ("dati.dead_letter", "dati.archivio_guasto", "dati.postino_bloccato",
                                        "dati.tetto_disco") else logging.WARNING
    logger.log(livello, "[%s] %s", nome, json.dumps(dict(dati), default=str)[:600])


def _fondi(vecchio: Optional[str], nuovo: Mapping[str, Any]) -> Dict[str, Any]:
    """Fusione delle colonne (semantica dell'upsert di oggi: le colonne non scritte restano)."""
    d = json.loads(vecchio) if vecchio else {}
    d.update(nuovo)
    return d


class ArchivioLocale:
    """Implementazione di ``contratto.Archivio`` (vedi docstring del modulo)."""

    def __init__(self, processo: str, registro: Registro, *, base: Optional[Path] = None,
                 orologio_ms: Callable[[], int] = _ora_ms, colonna_stato: str = "status",
                 colonne_tempo: Mapping[str, str] = COLONNE_TEMPO_PREDEFINITE,
                 lotto_max: int = 100, checkpoint_ogni_s: float = 1.0, checkpoint_esterno: bool = True,
                 pulizia_ogni_s: float = 3600.0,
                 conserva_giorni: Mapping[str, float] = CONSERVA_GIORNI_PREDEFINITI,
                 eventi: Optional[Eventi] = None,
                 alla_conferma: Optional[Callable[[int], None]] = None) -> None:
        self.processo = processo
        self.cartella = cartella_processo(processo, base)
        self._registro = registro
        self._ora_ms = orologio_ms
        self._colonna_stato = colonna_stato
        self._colonne_tempo = dict(colonne_tempo)
        self._lotto_max = max(1, int(lotto_max))
        self._checkpoint_ogni_s = float(checkpoint_ogni_s)
        self._checkpoint_esterno = bool(checkpoint_esterno)
        self._pulizia_ogni_s = float(pulizia_ogni_s)
        self._conserva = dict(conserva_giorni)
        self._eventi = eventi or _eventi_nel_log
        self._alla_conferma = alla_conferma

        self._lucchetto = Lucchetto(self.cartella)
        self._coda: "queue.SimpleQueue[Any]" = queue.SimpleQueue()
        self._cond = threading.Condition()
        self._n = 0
        self._in_volo: set[int] = set()            # numeri accodati e non ancora risolti
        self._soglia_annunciata = 0
        self._in_attesa: Dict[Tuple[str, str], Tuple[int, Optional[str], Optional[int]]] = {}
        self._attesa_lock = threading.Lock()
        self._scrittori: Dict[str, sqlite3.Connection] = {}
        self._lettori: Dict[str, sqlite3.Connection] = {}
        self._lettori_lock: Dict[str, threading.Lock] = {r: threading.Lock() for r in REGIMI_SQLITE}
        self._file_log: Dict[str, Any] = {}
        self._thread: Optional[threading.Thread] = None
        self._manutenzione: Optional[threading.Thread] = None
        self._stop_manutenzione = threading.Event()
        self._aperto = False
        self._in_chiusura = False
        self._ultimo_errore_unita: Optional[BaseException] = None
        self.guasto: Optional[str] = None
        self.contatori: Counter[str] = Counter()
        self._lat_accoda: Deque[int] = deque(maxlen=_MISURE_MAX)
        self._lat_commit: Dict[str, Deque[int]] = {r: deque(maxlen=_MISURE_MAX) for r in (*REGIMI_SQLITE, "log")}
        self._lat_durevole: Dict[str, Deque[int]] = {r: deque(maxlen=_MISURE_MAX) for r in (*REGIMI_SQLITE, "log")}
        self._lat_checkpoint: Deque[int] = deque(maxlen=_MISURE_MAX)

    # ------------------------------------------------------------------ ciclo di vita
    def apri(self) -> "ArchivioLocale":
        """Crea la cartella, prende il lucchetto, aggiorna lo schema, ripara i log
        troncati, avvia i due thread, fa rientrare un eventuale salvataggio. Idempotente.
        Puo' sollevare ``OSError``/``ArchivioOccupato`` (B3): l'aggancio resta su "vecchio"."""
        if self._aperto:
            return self
        prepara_cartella(self.cartella)
        self._lucchetto.prendi()
        try:
            for regime in REGIMI_SQLITE:
                percorso = str(self.cartella / FILE_DB[regime])
                scrittore = self._connetti(percorso, regime, autocheckpoint=not self._checkpoint_esterno)
                applica_schema(scrittore)
                self._scrittori[regime] = scrittore
                self._lettori[regime] = self._connetti(percorso, regime, autocheckpoint=False)
            self._ripara_log_troncati()
        except BaseException:
            self._chiudi_connessioni()
            self._lucchetto.rilascia()
            raise
        self._aperto = True
        self._in_chiusura = False
        self._stop_manutenzione.clear()
        self._thread = threading.Thread(target=self._ciclo_scrittore, name="archivio-scrittore", daemon=True)
        self._thread.start()
        self._manutenzione = threading.Thread(target=self._ciclo_manutenzione, name="archivio-manutenzione",
                                              daemon=True)
        self._manutenzione.start()
        self._riprendi_salvataggi()
        return self

    def chiudi(self, timeout_s: float = 30.0) -> None:
        """Scrive tutto cio' che e' in coda, ferma i thread, checkpoint finale, rilascia.
        Con il disco in errore le voci accettate vanno nel file di salvataggio (M6)."""
        if not self._aperto:
            return
        self._in_chiusura = True
        self._stop_manutenzione.set()
        if self._manutenzione is not None:
            self._manutenzione.join(timeout_s)
        self._coda.put(_FERMA)
        if self._thread is not None:
            self._thread.join(timeout_s)
            if self._thread.is_alive():
                logger.error("[archivio] il thread di scrittura non si e' fermato entro %.0f s", timeout_s)
        for f in self._file_log.values():
            try:
                f.close()
            except OSError as exc:
                logger.error("[archivio] chiusura di un file di log: %s", exc)
        self._file_log.clear()
        for regime, conn in self._scrittori.items():
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.Error as exc:
                logger.warning("[archivio] checkpoint finale di %s: %s", regime, exc)
        self._chiudi_connessioni()
        self._lucchetto.rilascia()
        self._aperto = False

    def __enter__(self) -> "ArchivioLocale":
        return self.apri()

    def __exit__(self, *_: Any) -> None:
        self.chiudi()

    @property
    def aperto(self) -> bool:
        return self._aperto

    def _connetti(self, percorso: str, regime: str, *, autocheckpoint: bool) -> sqlite3.Connection:
        conn = sqlite3.connect(percorso, isolation_level=None, check_same_thread=False, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA synchronous={SINCRONIA[regime]}")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute(f"PRAGMA wal_autocheckpoint={1000 if autocheckpoint else 0}")
        return conn

    def _chiudi_connessioni(self) -> None:
        for d in (self._scrittori, self._lettori):
            for conn in d.values():
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    logger.warning("[archivio] chiusura connessione: %s", exc)
            d.clear()

    # ------------------------------------------------------------------ contratto Archivio
    def spec(self, tabella: str) -> SpecTabella:
        """La riga del registro; una tabella non registrata e' rifiutata."""
        try:
            s = self._registro(tabella) if callable(self._registro) else self._registro[tabella]
        except KeyError:
            raise KeyError(f"tabella non registrata nell'archivio: {tabella}") from None
        if s is None:
            raise KeyError(f"tabella non registrata nell'archivio: {tabella}")
        if s.regime not in (*REGIMI_SQLITE, "log"):
            raise ValueError(f"tabella {tabella}: regime {s.regime} non e' dell'archivio locale")
        return s

    def scrivi(self, tabella: str, riga: Mapping[str, Any]) -> None:
        """Accoda la riga (upsert = fusione delle colonne per lo stato, insert per i log
        con ``uid``). Il chiamante paga: copia, uid/timbro se mancano, chiave, JSON,
        accodamento. La riga e' durevole quando ``conferma()`` torna vero."""
        t0 = time.perf_counter_ns()
        self._controlla_aperto()
        spec = self.spec(tabella)
        r = self._prepara(spec, riga)
        chiave = chiave_canonica(spec, r)
        rev = self._rev_di(spec, r)
        op = "upsert" if spec.regime != "log" or spec.chiave_naturale not in (("uid",),) else "insert"
        testo = testo_json(r)
        ms = self._ora_ms()
        n = self._prossimo_n()
        if spec.regime != "log":
            self._in_attesa_aggiorna(tabella, chiave, n, r, rev, r.get(spec.rev_colonna) if spec.rev_colonna else None)
        self._coda.put(_Scrittura(n, spec.regime, tabella, op, chiave, testo, rev, spec.rev_colonna,
                                  spec.coalesce, ms, t0))
        self._lat_accoda.append(time.perf_counter_ns() - t0)

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        """L'ultima versione per chiave naturale (anche se non ancora su disco): la riga
        su disco con sopra le colonne ancora in coda. Solo regimi di stato."""
        spec = self.spec(tabella)
        if spec.regime == "log":
            raise ValueError(f"tabella {tabella}: i log non si leggono per chiave")
        self._controlla_aperto()
        k = chiave_canonica(spec, chiave)
        with self._attesa_lock:
            p = self._in_attesa.get((tabella, k))
        riga = self._leggi_uno(spec.regime, "SELECT json FROM righe WHERE tabella = ? AND chiave = ?", (tabella, k))
        if p is None:
            return None if riga is None else json.loads(riga[0])
        return _fondi(riga[0] if riga else None, json.loads(p[1] or "{}"))

    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool:
        """Claim atomico: ``colonna_stato`` passa da ``da`` ad ``a`` solo se vale ``da``.

        Eseguito dal thread di scrittura (dopo tutte le scritture accodate prima);
        riga e outbox nella stessa transazione; la versione di riga sale. L'esito che
        torna e' quello VERO anche se scade l'attesa o se un commit va ritentato (M5)."""
        spec = self.spec(tabella)
        if spec.regime == "log":
            raise ValueError(f"tabella {tabella}: nessuna transizione sui log")
        k = chiave_canonica(spec, chiave)
        col = self._colonna_stato

        def fn(conn: sqlite3.Connection) -> bool:
            riga = conn.execute("SELECT json, rev FROM righe WHERE tabella = ? AND chiave = ?", (tabella, k)).fetchone()
            if riga is None:
                return False
            d = json.loads(riga[0])
            if d.get(col) != da:
                return False
            d[col] = a
            rev = self._sali_rev(spec, d, riga[1])
            testo = testo_json(d)
            ms = self._ora_ms()
            conn.execute("UPDATE righe SET json = ?, rev = ?, aggiornato_ms = ? WHERE tabella = ? AND chiave = ?",
                         (testo, rev, ms, tabella, k))
            self._in_outbox(conn, tabella, "upsert", k, testo, ms, spec.coalesce)
            return True

        return bool(self._esegui_sincrono(spec.regime, fn))

    # ------------------------------------------------------------------ forma sincrona (postino.accoda)
    def accoda(self, tabella: str, op: Operazione, chiave: Optional[str], riga: Mapping[str, Any], *,
               coalesce: bool = False, timeout_s: float = 30.0) -> int:
        """Applica ``op`` alla riga locale e mette la voce in outbox, STESSA transazione,
        e aspetta il commit. Ritorna il ``seq`` della outbox (per i log: l'offset in
        byte della riga nel file del giorno; 0 = riga vecchia scartata)."""
        if op not in ("upsert", "insert", "patch", "delete"):
            raise ValueError(f"operazione non ammessa: {op}")
        self._controlla_aperto()
        spec = self.spec(tabella)
        r = self._prepara(spec, riga) if op in ("upsert", "insert") else dict(riga)
        k = chiave if chiave is not None else chiave_canonica(spec, r)
        rev = self._rev_di(spec, r) if op != "delete" or (spec.rev_colonna and spec.rev_colonna in r) else None
        futuro: "Future[int]" = Future()
        self._coda.put(_Scrittura(self._prossimo_n(), spec.regime, tabella, op, k, testo_json(r), rev,
                                  spec.rev_colonna, bool(coalesce or spec.coalesce), self._ora_ms(),
                                  time.perf_counter_ns(), futuro))
        return int(self._attendi(futuro, timeout_s))

    def conferma(self, timeout_s: float = 10.0) -> bool:
        """Barriera: vero quando tutto cio' che e' stato accodato FINO A QUI e' su disco
        (o, se impossibile da salvare, isolato nel file degli scarti)."""
        fine = time.monotonic() + timeout_s
        with self._cond:
            obiettivo = self._n
            while self._in_volo and min(self._in_volo) <= obiettivo:
                resto = fine - time.monotonic()
                if resto <= 0:
                    return False
                self._cond.wait(resto)
        return True

    # ------------------------------------------------------------------ preparazione nel chiamante
    def _controlla_aperto(self) -> None:
        if not self._aperto or self._in_chiusura:
            raise ArchivioChiuso(f"archivio {self.processo} non aperto")

    def _prossimo_n(self) -> int:
        with self._cond:
            self._n += 1
            self._in_volo.add(self._n)
            return self._n

    def _prepara(self, spec: SpecTabella, riga: Mapping[str, Any]) -> Dict[str, Any]:
        r = dict(riga)
        for c in spec.chiave_naturale:
            if c in COLONNE_UID and r.get(c) is None:
                r[c] = str(uuid.uuid4())
        col_t = self._colonne_tempo.get(spec.nome)
        if col_t and r.get(col_t) is None:
            r[col_t] = iso_utc(self._ora_ms())
        return r

    @staticmethod
    def _rev_di(spec: SpecTabella, r: Mapping[str, Any]) -> Optional[int]:
        if not spec.rev_colonna:
            return None
        if r.get(spec.rev_colonna) is None:
            raise ValueError(f"tabella {spec.nome}: manca la versione di riga '{spec.rev_colonna}'")
        return rev_ordinabile(r[spec.rev_colonna])

    def _in_attesa_aggiorna(self, tabella: str, chiave: str, n: int, r: Mapping[str, Any], rev: Optional[int],
                            valore_rev: Any) -> None:
        """Vista per ``leggi`` prima del commit, con la STESSA regola dello scrittore."""
        with self._attesa_lock:
            prec = self._in_attesa.get((tabella, chiave))
            if prec is None:
                self._in_attesa[(tabella, chiave)] = (n, testo_json(r), rev)
                return
            if rev is not None and prec[2] is not None and _stantia(rev, prec[2], valore_rev):
                return                                       # lo scrittore la scartera'
            nuova_rev = rev if rev is None or prec[2] is None or rev > prec[2] else prec[2] + 1
            self._in_attesa[(tabella, chiave)] = (n, testo_json(_fondi(prec[1], r)), nuova_rev)

    def _sali_rev(self, spec: SpecTabella, d: Dict[str, Any], rev_prec: Optional[int]) -> Optional[int]:
        """Versione nuova per una transizione: intero +1, istante = adesso (mai indietro)."""
        if not spec.rev_colonna:
            return None
        col = spec.rev_colonna
        if isinstance(d.get(col), int) and not isinstance(d.get(col), bool):
            d[col] = int(d[col]) + 1
            return d[col]
        us = self._ora_ms() * 1000
        if rev_prec is not None and us <= rev_prec:
            us = rev_prec + 1
        d[col] = iso_da_us(us)
        return us

    def _attendi(self, futuro: "Future[Any]", timeout_s: float) -> Any:
        """M5: allo scadere, se il lavoro non e' partito si annulla (esito vero: non
        avvenuto); se e' partito si aspetta l'esito vero, non un'eccezione falsa."""
        try:
            return futuro.result(timeout_s)
        except FuturoScaduto:
            if futuro.cancel():
                raise TimeoutError("archivio: lavoro annullato prima di partire (non eseguito)") from None
            return futuro.result()

    # ------------------------------------------------------------------ thread di scrittura
    def _ciclo_scrittore(self) -> None:
        fermati = False
        while not fermati:
            voce = self._coda.get()
            lotto: List[Any] = [voce]
            while len(lotto) < self._lotto_max:
                try:
                    lotto.append(self._coda.get_nowait())
                except queue.Empty:
                    break
            fermati = any(v is _FERMA for v in lotto)
            lotto = [v for v in lotto if v is not _FERMA]
            if lotto:
                self._esegui_con_ritento(lotto)
        # dopo _FERMA non arrivano scritture (scrivi rifiuta in chiusura); i lavori rimasti falliscono
        while True:
            try:
                v = self._coda.get_nowait()
            except queue.Empty:
                break
            if isinstance(v, (_Lavoro, _Scrittura)) and v.futuro is not None and not v.futuro.done():
                v.futuro.set_exception(ArchivioChiuso("archivio in chiusura"))

    def _esegui_con_ritento(self, lotto: List[Any]) -> None:
        rimasti = lotto
        tentativo = 0
        while True:
            rimasti = self._esegui_unita(rimasti)
            if rimasti and (errore_di_dato(self._ultimo_errore_unita) or tentativo + 1 >= TENTATIVI_PRIMA_DI_ISOLARE):
                rimasti = self._isola(rimasti)
            if not rimasti:
                if self.guasto is not None:
                    self._evento("dati.archivio_ripreso", {"processo": self.processo, "dopo_tentativi": tentativo})
                    self.guasto = None
                return
            tentativo += 1
            exc = self._ultimo_errore_unita
            self.guasto = f"{type(exc).__name__}: {exc}"[:300]
            self.contatori["guasti_scrittura"] += 1
            self._evento("dati.archivio_guasto", {"processo": self.processo, "errore": self.guasto,
                                                   "tentativo": tentativo, "voci": len(rimasti)})
            if self._in_chiusura and tentativo >= TENTATIVI_PRIMA_DI_ISOLARE:
                self._salva(rimasti, exc)
                return
            time.sleep(min(30.0, 0.5 * (2 ** min(tentativo, 6))))

    def _esegui_unita(self, voci: List[Any]) -> List[Any]:
        """Tre unita' indipendenti (log, denaro, vivo). Ritorna le voci delle unita' fallite."""
        unita: Dict[str, List[Any]] = {}
        for v in voci:
            unita.setdefault(v.regime, []).append(v)
        falliti: List[Any] = []
        for regime in ("log", *REGIMI_SQLITE):
            gruppo = unita.get(regime)
            if not gruppo:
                continue
            try:
                esiti = self._unita_log(gruppo) if regime == "log" else self._unita_sqlite(regime, gruppo)
            except Exception as exc:
                self._ultimo_errore_unita = exc
                falliti.extend(gruppo)
                continue
            self._dopo_unita(gruppo, esiti)
        falliti.sort(key=lambda v: v.n)
        return falliti

    def _unita_sqlite(self, regime: str, voci: List[Any]) -> List[Tuple[Any, Any, Optional[BaseException]]]:
        conn = self._scrittori[regime]
        esiti: List[Tuple[Any, Any, Optional[BaseException]]] = []
        conn.execute("BEGIN IMMEDIATE")
        try:
            for v in voci:
                if not self._parte(v):
                    esiti.append((v, None, None))
                    continue
                if isinstance(v, _Scrittura):
                    esiti.append((v, self._applica(conn, v), None))
                    continue
                conn.execute("SAVEPOINT lavoro")
                try:
                    valore = v.fn(conn)
                except Exception as exc:  # l'errore torna al chiamante del lavoro
                    conn.execute("ROLLBACK TO lavoro")
                    conn.execute("RELEASE lavoro")
                    esiti.append((v, None, exc))
                else:
                    conn.execute("RELEASE lavoro")
                    esiti.append((v, valore, None))
            t = time.perf_counter_ns()
            conn.execute("COMMIT")
            self._lat_commit[regime].append(time.perf_counter_ns() - t)
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error as exc:
                logger.error("[archivio] rollback di %s: %s", regime, exc)
            raise
        return esiti

    def _unita_log(self, voci: List[Any]) -> List[Tuple[Any, Any, Optional[BaseException]]]:
        posizioni: Dict[str, int] = {}
        esiti: List[Tuple[Any, Any, Optional[BaseException]]] = []
        try:
            for v in voci:
                if not self._parte(v):
                    esiti.append((v, None, None))
                    continue
                esiti.append((v, self._scrivi_log(v, posizioni), None))
            t = time.perf_counter_ns()
            for nome in posizioni:
                self._file_log[nome].flush()
            if posizioni:
                self._lat_commit["log"].append(time.perf_counter_ns() - t)
        except BaseException:
            self._riavvolgi_log(posizioni)
            raise
        return esiti

    @staticmethod
    def _parte(v: Any) -> bool:
        """Una voce con un futuro annullato (attesa scaduta prima che partisse) non si esegue."""
        if v.futuro is None or v.avviata:
            return True
        v.avviata = True
        return bool(v.futuro.set_running_or_notify_cancel())

    def _isola(self, voci: List[Any]) -> List[Any]:
        """A2: voce per voce. Una voce che fallisce per un errore che NON e' di I/O e'
        velenosa: va negli scarti su file e il resto prosegue. Un errore di I/O ferma
        l'isolamento: le voci restano per il ritento (mai buttate)."""
        rimasti = list(voci)
        while rimasti:
            v = rimasti[0]
            if not self._esegui_unita([v]):
                rimasti.pop(0)
                continue
            exc = self._ultimo_errore_unita
            if exc is not None and errore_di_io(exc):
                return rimasti
            try:
                self._veleno(v, exc)
            except OSError as err:                           # nemmeno il file degli scarti: e' I/O, si ritenta
                self._ultimo_errore_unita = err
                return rimasti
            rimasti.pop(0)
        return []

    def _veleno(self, v: Any, exc: Optional[BaseException]) -> None:
        errore = f"{type(exc).__name__}: {exc}"[:500]
        if isinstance(v, _Scrittura):
            riga = {"ms": self._ora_ms(), "errore": errore, **v.salvabile()}
            with open(self.cartella / FILE_SCARTI, "a", encoding="ascii") as f:   # un OSError qui = I/O: si ritenta
                f.write(testo_json(riga) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self.contatori["scarti_scrittore"] += 1
            self._evento("dati.dead_letter", {"tabella": v.tabella, "fonte": "scrittore", "motivo": "dato",
                                              "errore": errore})
        if v.futuro is not None and not v.futuro.done():
            v.futuro.set_exception(exc if exc is not None else RuntimeError(errore))
        self._risolti([v])

    def _salva(self, voci: List[Any], exc: Optional[BaseException]) -> None:
        """M6: chiusura con il disco in errore: le scritture accettate vanno in un file di
        salvataggio (rientra all'apertura); i lavori sincroni falliscono col motivo."""
        scritture = [v for v in voci if isinstance(v, _Scrittura)]
        if scritture:
            nome = self.cartella / f"{PREFISSO_SALVATAGGIO}{time.time_ns()}.jsonl"
            try:
                with open(nome, "w", encoding="ascii") as f:
                    for v in scritture:
                        f.write(testo_json(v.salvabile()) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                self._evento("dati.archivio_salvataggio", {"file": nome.name, "voci": len(scritture),
                                                           "errore": f"{exc}"[:300]})
            except OSError as err:
                logger.critical("[archivio] chiusura: %d voci NON salvate (%s; poi %s)", len(scritture), exc, err)
        for v in voci:
            if v.futuro is not None and not v.futuro.done():
                v.futuro.set_exception(exc if exc is not None else ArchivioChiuso("archivio in chiusura"))
        self._risolti(voci)

    def _riprendi_salvataggi(self) -> None:
        for percorso in sorted(self.cartella.glob(PREFISSO_SALVATAGGIO + "*.jsonl")):
            voci = []
            for linea in percorso.read_text(encoding="ascii").splitlines():
                if not linea.strip():
                    continue
                d = json.loads(linea)
                voci.append(_Scrittura(self._prossimo_n(), d["regime"], d["tabella"], d["op"], d["chiave"],
                                       d["testo"], d["rev"], d["rev_col"], bool(d["coalesce"]), int(d["ms"]),
                                       time.perf_counter_ns()))
            for v in voci:
                self._coda.put(v)
            if self.conferma(120):
                percorso.unlink()
                self._evento("dati.archivio_salvataggio_ripreso", {"file": percorso.name, "voci": len(voci)})
            else:
                logger.error("[archivio] salvataggio %s non ancora ripreso: resta per l'apertura dopo", percorso.name)

    def _dopo_unita(self, voci: List[Any], esiti: List[Tuple[Any, Any, Optional[BaseException]]]) -> None:
        adesso = time.perf_counter_ns()
        with self._attesa_lock:
            for v in voci:
                if isinstance(v, _Scrittura):
                    self._lat_durevole[v.regime].append(adesso - v.t_ns)
                    p = self._in_attesa.get((v.tabella, v.chiave))
                    if p is not None and p[0] <= v.n:
                        del self._in_attesa[(v.tabella, v.chiave)]
        for v, valore, exc in esiti:
            if v.futuro is not None and not v.futuro.done():
                if exc is not None:
                    v.futuro.set_exception(exc)
                else:
                    v.futuro.set_result(valore)
        self._risolti(voci)

    def _risolti(self, voci: Sequence[Any]) -> None:
        with self._cond:
            for v in voci:
                self._in_volo.discard(v.n)
            soglia = (min(self._in_volo) - 1) if self._in_volo else self._n
            nuova = soglia > self._soglia_annunciata
            if nuova:
                self._soglia_annunciata = soglia
            self._cond.notify_all()
        if nuova and self._alla_conferma is not None:
            try:
                self._alla_conferma(soglia)
            except Exception as exc:  # il gancio dei test/misure non ferma lo scrittore
                logger.error("[archivio] gancio alla_conferma: %s", exc)

    def _versione(self, conn: sqlite3.Connection, v: _Scrittura, nuova: Dict[str, Any],
                  prec: Optional[int]) -> Optional[int]:
        """M3. Ritorna la versione da salvare, o None se la riga e' stantia (scartata)."""
        if v.rev is None or prec is None or v.rev > prec:
            return v.rev
        if _stantia(v.rev, prec, nuova.get(v.rev_col)):
            self.contatori["righe_vecchie_scartate"] += 1
            self._evento("dati.riga_vecchia", {"tabella": v.tabella, "chiave": v.chiave, "versione": nuova.get(v.rev_col),
                                               "versione_locale": prec})
            return None
        rev = prec + 1
        if v.rev_col is not None:
            nuova[v.rev_col] = rev if isinstance(nuova.get(v.rev_col), int) else iso_da_us(rev)
        self.contatori["versioni_corrette"] += 1
        return rev

    def _applica(self, conn: sqlite3.Connection, v: _Scrittura) -> int:
        """Riga locale + outbox (stessa transazione). Ritorna il seq (0 = riga stantia scartata)."""
        riga = conn.execute("SELECT json, rev FROM righe WHERE tabella = ? AND chiave = ?",
                            (v.tabella, v.chiave)).fetchone()
        if v.op == "delete":
            conn.execute("DELETE FROM righe WHERE tabella = ? AND chiave = ?", (v.tabella, v.chiave))
            return self._in_outbox(conn, v.tabella, v.op, v.chiave, v.testo, v.ms, v.coalesce)
        nuova = json.loads(v.testo)
        if v.op == "insert" and riga is not None:
            return self._in_outbox(conn, v.tabella, v.op, v.chiave, v.testo, v.ms, v.coalesce)   # idempotente
        rev = self._versione(conn, v, nuova, riga[1] if riga else None)
        if rev is None and v.rev is not None:
            return 0
        testo = testo_json(nuova)
        if riga is not None:
            conn.execute("UPDATE righe SET json = ?, rev = ?, aggiornato_ms = ? WHERE tabella = ? AND chiave = ?",
                         (testo_json(_fondi(riga[0], nuova)), rev if rev is not None else riga[1], v.ms,
                          v.tabella, v.chiave))
        elif v.op != "patch":
            conn.execute("INSERT INTO righe (tabella, chiave, json, rev, aggiornato_ms) VALUES (?, ?, ?, ?, ?)",
                         (v.tabella, v.chiave, testo, rev, v.ms))
        return self._in_outbox(conn, v.tabella, v.op, v.chiave, testo, v.ms, v.coalesce)

    @staticmethod
    def _in_outbox(conn: sqlite3.Connection, tabella: str, op: str, chiave: str, testo: str, ms: int,
                   coalesce: bool) -> int:
        if coalesce and op == "upsert":
            # resta SOLO una voce per chiave, con le colonne FUSE (B2): nessuna colonna di un
            # upsert parziale precedente si perde. Una voce gia' in volo tolta qui non fa danni:
            # la conferma del postino cancella per seq
            prec = conn.execute("SELECT seq, json FROM outbox WHERE tabella = ? AND chiave = ? AND op = 'upsert' "
                                "ORDER BY seq", (tabella, chiave)).fetchall()
            if prec:
                fusa: Dict[str, Any] = {}
                for _, j in prec:
                    fusa.update(json.loads(j))
                fusa.update(json.loads(testo))
                testo = testo_json(fusa)
                conn.executemany("DELETE FROM outbox WHERE seq = ?", [(s,) for s, _ in prec])
        cur = conn.execute("INSERT INTO outbox (tabella, op, chiave, json, creato_ms, coalesce) VALUES (?, ?, ?, ?, ?, ?)",
                           (tabella, op, chiave, testo, ms, 1 if coalesce else 0))
        return int(cur.lastrowid or 0)

    # ------------------------------------------------------------------ log JSONL
    def cartella_log(self) -> Path:
        return self.cartella / "log"

    def _scrivi_log(self, v: _Scrittura, posizioni: Dict[str, int]) -> int:
        nome = giorno_utc(v.ms) + ".jsonl"
        f = self._file_log.get(nome)
        if f is None:
            self._chiudi_log_vecchi(nome)
            f = open(self.cartella_log() / nome, "ab")
            self._file_log[nome] = f
        if nome not in posizioni:
            posizioni[nome] = f.tell()
        offset = f.tell()
        f.write(riga_log(v.tabella, v.op, v.ms, json.loads(v.testo)).encode("ascii"))
        return offset

    def _chiudi_log_vecchi(self, tenere: str) -> None:
        for nome in [n for n in self._file_log if n < tenere]:
            self._file_log.pop(nome).close()

    def _riavvolgi_log(self, posizioni: Mapping[str, int]) -> None:
        """Unita' di log fallita: i byte scritti si tolgono (niente meta' righe, niente doppioni)."""
        for nome, pos in posizioni.items():
            f = self._file_log.pop(nome, None)
            try:
                if f is not None:
                    try:
                        f.close()                          # il buffer non svuotato non deve finire nel file
                    except OSError:
                        pass
                with open(self.cartella_log() / nome, "rb+") as g:
                    g.truncate(pos)
            except OSError as exc:
                logger.error("[archivio] riavvolgimento di %s a %d: %s", nome, pos, exc)

    def _ripara_log_troncati(self) -> None:
        """Ripresa dopo crash: una riga finale senza ``\\n`` si taglia e si SEGNALA.

        A3: l'ultimo ``\\n`` si cerca all'indietro a blocchi fino all'inizio del file;
        si taglia a 0 SOLO se il file non ne contiene nessuno (tutto il file e' il frammento)."""
        for percorso in sorted(self.cartella_log().glob("*.jsonl")):
            dim = percorso.stat().st_size
            if dim == 0:
                continue
            with open(percorso, "rb+") as f:
                f.seek(dim - 1)
                if f.read(1) == b"\n":
                    continue
                taglio = 0
                fine = dim
                while fine > 0:
                    inizio = max(0, fine - 1_048_576)
                    f.seek(inizio)
                    blocco = f.read(fine - inizio)
                    i = blocco.rfind(b"\n")
                    if i >= 0:
                        taglio = inizio + i + 1
                        break
                    fine = inizio
                f.seek(taglio)
                anteprima = f.read(200)
                f.truncate(taglio)
            dettagli = {"file": percorso.name, "offset": taglio, "byte": dim - taglio,
                        "anteprima": anteprima.decode("ascii", "replace")}
            self.contatori["righe_log_troncate"] += 1
            self._segnala_diretto("riga_log_troncata", dettagli)
            self._evento("dati.riga_troncata", dettagli)

    def _segnala_diretto(self, tipo: str, dettagli: Mapping[str, Any]) -> None:
        conn = self._scrittori[REGIME_SERVIZIO]
        conn.execute("INSERT INTO segnalazioni (tipo, dettagli, ts_ms) VALUES (?, ?, ?)",
                     (tipo, testo_json(dict(dettagli)), self._ora_ms()))

    # ------------------------------------------------------------------ lavori sincroni
    def _esegui_sincrono(self, regime: str, fn: Callable[[sqlite3.Connection], Any], timeout_s: float = 30.0) -> Any:
        if not self._aperto:
            raise ArchivioChiuso(f"archivio {self.processo} non aperto")
        futuro: "Future[Any]" = Future()
        self._coda.put(_Lavoro(self._prossimo_n(), regime, fn, futuro))
        return self._attendi(futuro, timeout_s)

    def _leggi_uno(self, regime: str, sql: str, args: Sequence[Any]) -> Optional[Tuple[Any, ...]]:
        with self._lettori_lock[regime]:
            return self._lettori[regime].execute(sql, tuple(args)).fetchone()

    def _leggi_tutti(self, regime: str, sql: str, args: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
        with self._lettori_lock[regime]:
            return self._lettori[regime].execute(sql, tuple(args)).fetchall()

    # ------------------------------------------------------------------ API per il postino e riconcilia
    def outbox_pronta(self, regime: str, adesso_ms: int, limite: int) -> List[VoceOutbox]:
        """Voci pronte in ordine di seq, FIFO PER CHIAVE (M4): una voce non e' pronta se
        una voce piu' vecchia della stessa chiave aspetta ancora il suo turno."""
        righe = self._leggi_tutti(regime, "SELECT o.seq, o.tabella, o.op, o.chiave, o.json, o.tentativi, o.creato_ms "
                                          "FROM outbox o WHERE o.prossimo_ms <= ? AND NOT EXISTS (SELECT 1 FROM outbox p "
                                          "WHERE p.tabella = o.tabella AND p.chiave = o.chiave AND p.seq < o.seq "
                                          "AND p.prossimo_ms > ?) ORDER BY o.seq LIMIT ?",
                                  (adesso_ms, adesso_ms, int(limite)))
        return [VoceOutbox(regime, *r) for r in righe]

    def conteggi_outbox(self, regime: str) -> Tuple[Counter[str], Optional[int], int]:
        """(voci per tabella, creato_ms piu' vecchio, dead_letter)."""
        per = Counter({t: n for t, n in self._leggi_tutti(regime, "SELECT tabella, count(*) FROM outbox GROUP BY tabella")})
        vecchio = self._leggi_uno(regime, "SELECT min(creato_ms) FROM outbox", ())
        morti = self._leggi_uno(regime, "SELECT count(*) FROM dead_letter", ())
        return per, (vecchio[0] if vecchio else None), int(morti[0] if morti else 0)

    def chiudi_voci(self, regime: str, consegnate: Sequence[int], rimandate: Sequence[Tuple[int, int, int, str]],
                    morte: Sequence[Tuple[Any, ...]]) -> None:
        """Esito di un giro del postino: cancella le consegnate, rimanda (tentativi,
        prossimo, errore), sposta le morte in ``dead_letter`` con la CAUSA (``motivo``,
        default ``dato``) e la data del rientro automatico: UNA transazione."""
        adesso = self._ora_ms()

        def fn(conn: sqlite3.Connection) -> None:
            conn.executemany("DELETE FROM outbox WHERE seq = ?", [(s,) for s in consegnate])
            conn.executemany("UPDATE outbox SET tentativi = ?, prossimo_ms = ?, ultimo_errore = ? WHERE seq = ?",
                             [(t, p, e[:500], s) for s, t, p, e in rimandate])
            for m in morte:
                seq, codice, errore, tentativi = m[:4]
                motivo = m[4] if len(m) > 4 else "dato"
                conn.execute("INSERT INTO dead_letter (fonte, seq_origine, tabella, op, chiave, json, codice, errore, "
                             "tentativi, creato_ms, morto_ms, motivo, rientri, prossimo_rientro_ms) SELECT 'outbox', seq, "
                             "tabella, op, chiave, json, ?, ?, ?, creato_ms, ?, ?, rientri, ? FROM outbox WHERE seq = ?",
                             (codice, errore[:1000], tentativi, adesso, motivo, adesso + RIENTRO_MS.get(motivo, 86_400_000),
                              seq))
                conn.execute("DELETE FROM outbox WHERE seq = ?", (seq,))

        self._esegui_sincrono(regime, fn)

    def rientro_dead_letter(self, adesso_ms: Optional[int] = None, massimo: int = 500) -> int:
        """A4: rientro AUTOMATICO delle dead_letter scadute (transitorie ogni 15 min, dato e
        registro ogni 24 h), nessun tetto di rientri: tornano in outbox con i tentativi a zero
        e il contatore ``rientri`` +1. Ritorna quante sono rientrate."""
        adesso = self._ora_ms() if adesso_ms is None else adesso_ms
        totale = 0
        for regime in REGIMI_SQLITE:
            def fn(conn: sqlite3.Connection) -> int:
                righe = conn.execute("SELECT id, tabella, op, chiave, json, creato_ms, rientri FROM dead_letter "
                                     "WHERE prossimo_rientro_ms <= ? ORDER BY id LIMIT ?", (adesso, massimo)).fetchall()
                for i, tabella, op, chiave, testo, creato, rientri in righe:
                    conn.execute("INSERT INTO outbox (tabella, op, chiave, json, creato_ms, prossimo_ms, rientri) "
                                 "VALUES (?, ?, ?, ?, ?, 0, ?)", (tabella, op, chiave, testo, creato, rientri + 1))
                    conn.execute("DELETE FROM dead_letter WHERE id = ?", (i,))
                return len(righe)

            totale += int(self._esegui_sincrono(regime, fn))
        if totale:
            self.contatori["rientri_dead_letter"] += totale
            self._evento("dati.dead_letter_rientro", {"righe": totale})
        return totale

    def file_log(self) -> List[Path]:
        return sorted(self.cartella_log().glob("*.jsonl"))

    def offset_log(self, nome: str) -> int:
        return self.marcatore_log(nome)[0]

    def marcatore_log(self, nome: str) -> Tuple[int, Optional[str]]:
        """(offset consegnato, firma della prima riga del file quando l'offset e' stato scritto)."""
        r = self._leggi_uno(REGIME_SERVIZIO, "SELECT offset, firma FROM consegna WHERE fonte = ?", ("log/" + nome,))
        return (int(r[0]), r[1]) if r else (0, None)

    def azzera_marcatore(self, nome: str, dettagli: Mapping[str, Any]) -> None:
        """M2: il file non e' piu' quello del marcatore (troncato, sostituito): si riparte da 0
        (il ritento e' sicuro: ``uid`` + ``ON CONFLICT DO NOTHING``) e si segnala."""
        testo = testo_json(dict(dettagli))

        def fn(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM consegna WHERE fonte = ?", ("log/" + nome,))
            conn.execute("INSERT INTO segnalazioni (tipo, dettagli, ts_ms) VALUES ('marcatore_log_azzerato', ?, ?)",
                         (testo, self._ora_ms()))

        self._esegui_sincrono(REGIME_SERVIZIO, fn)
        self._evento("dati.marcatore_azzerato", dettagli)

    def chiudi_log(self, nome: str, nuovo_offset: int,
                   morte: Sequence[Tuple[Any, ...]],
                   ritenti: Sequence[Tuple[str, str, str, str, int, int, int, str]],
                   firma: Optional[str] = None) -> None:
        """Avanza il marcatore del file e, NELLA STESSA transazione, mette le righe
        rifiutate in ``dead_letter`` e quelle da ritentare nella outbox del vivo."""
        adesso = self._ora_ms()

        def fn(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO consegna (fonte, offset, aggiornato_ms, firma) VALUES (?, ?, ?, ?) "
                         "ON CONFLICT (fonte) DO UPDATE SET offset = excluded.offset, aggiornato_ms = "
                         "excluded.aggiornato_ms, firma = coalesce(excluded.firma, consegna.firma) "
                         "WHERE excluded.offset > consegna.offset", ("log/" + nome, int(nuovo_offset), adesso, firma))
            for m in morte:
                tabella, op, chiave, testo, ms, codice, errore, tentativi = m[:8]
                motivo = m[8] if len(m) > 8 else "dato"
                conn.execute("INSERT INTO dead_letter (fonte, seq_origine, tabella, op, chiave, json, codice, errore, "
                             "tentativi, creato_ms, morto_ms, motivo, prossimo_rientro_ms) "
                             "VALUES ('log', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (tabella, op, chiave, testo, codice, errore[:1000], tentativi, ms, adesso, motivo,
                              adesso + RIENTRO_MS.get(motivo, 86_400_000)))
            for tabella, op, chiave, testo, ms, tentativi, prossimo, errore in ritenti:
                conn.execute("INSERT INTO outbox (tabella, op, chiave, json, creato_ms, tentativi, prossimo_ms, "
                             "ultimo_errore) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (tabella, op, chiave, testo, ms, tentativi, prossimo, errore[:500]))

        self._esegui_sincrono(REGIME_SERVIZIO, fn)

    def segnala(self, tipo: str, dettagli: Mapping[str, Any]) -> None:
        testo = testo_json(dict(dettagli))
        self._esegui_sincrono(REGIME_SERVIZIO, lambda c: c.execute(
            "INSERT INTO segnalazioni (tipo, dettagli, ts_ms) VALUES (?, ?, ?)", (tipo, testo, self._ora_ms())))

    def segnalazioni(self) -> List[Dict[str, Any]]:
        return [{"id": i, "tipo": t, "dettagli": json.loads(d), "ts_ms": ts} for i, t, d, ts in
                self._leggi_tutti(REGIME_SERVIZIO, "SELECT id, tipo, dettagli, ts_ms FROM segnalazioni ORDER BY id")]

    def scarti_scrittore(self) -> List[Dict[str, Any]]:
        """Le voci che lo scrittore non ha potuto salvare (A2): visibili, mai cancellate da sole."""
        percorso = self.cartella / FILE_SCARTI
        if not percorso.exists():
            return []
        return [json.loads(x) for x in percorso.read_text(encoding="ascii").splitlines() if x.strip()]

    def dead_letter(self) -> List[Dict[str, Any]]:
        """Tutte le righe morte dei due file e degli scarti dello scrittore (visibili)."""
        out: List[Dict[str, Any]] = []
        for regime in REGIMI_SQLITE:
            for r in self._leggi_tutti(regime, "SELECT id, fonte, tabella, op, chiave, json, codice, errore, tentativi, "
                                               "morto_ms, motivo, rientri FROM dead_letter ORDER BY id"):
                out.append({"regime": regime, "id": r[0], "fonte": r[1], "tabella": r[2], "op": r[3], "chiave": r[4],
                            "riga": json.loads(r[5]), "codice": r[6], "errore": r[7], "tentativi": r[8],
                            "morto_ms": r[9], "motivo": r[10], "rientri": r[11]})
        for s in self.scarti_scrittore():
            out.append({"regime": "scrittore", "id": None, "fonte": "scrittore", "tabella": s["tabella"], "op": s["op"],
                        "chiave": s["chiave"], "riga": s["testo"], "codice": None, "errore": s["errore"],
                        "tentativi": 0, "morto_ms": s["ms"], "motivo": "dato", "rientri": 0})
        return out

    def rimetti_in_coda(self, regime: str, id_dead_letter: int) -> int:
        """Rientro immediato di UNA riga (il rientro periodico e' gia' automatico)."""
        adesso = self._ora_ms()

        def fn(conn: sqlite3.Connection) -> int:
            r = conn.execute("SELECT tabella, op, chiave, json, creato_ms FROM dead_letter WHERE id = ?",
                             (id_dead_letter,)).fetchone()
            if r is None:
                return 0
            cur = conn.execute("INSERT INTO outbox (tabella, op, chiave, json, creato_ms, prossimo_ms) "
                               "VALUES (?, ?, ?, ?, ?, ?)", (*r, adesso))
            conn.execute("DELETE FROM dead_letter WHERE id = ?", (id_dead_letter,))
            return int(cur.lastrowid or 0)

        return int(self._esegui_sincrono(regime, fn))

    def righe_finestra(self, tabella: str, da_ms: int, a_ms: Optional[int]) -> List[Tuple[str, str]]:
        """(chiave, json) delle righe di stato aggiornate in [da, a)."""
        spec = self.spec(tabella)
        if spec.regime == "log":
            raise ValueError(f"tabella {tabella}: i log non hanno righe di stato")
        return [(k, j) for k, j in self._leggi_tutti(
            spec.regime, "SELECT chiave, json FROM righe WHERE tabella = ? AND aggiornato_ms >= ? AND aggiornato_ms < ?",
            (tabella, int(da_ms), int(a_ms if a_ms is not None else 2 ** 62)))]

    def esistono(self, tabella: str, chiavi: Sequence[str]) -> set[str]:
        spec = self.spec(tabella)
        trovate: set[str] = set()
        for i in range(0, len(chiavi), 500):
            pezzo = list(chiavi[i:i + 500])
            segni = ",".join("?" * len(pezzo))
            trovate.update(r[0] for r in self._leggi_tutti(
                spec.regime, f"SELECT chiave FROM righe WHERE tabella = ? AND chiave IN ({segni})", [tabella, *pezzo]))
        return trovate

    def chiavi_in_coda(self, tabella: str) -> set[str]:
        spec = self.spec(tabella)
        regimi = (spec.regime,) if spec.regime != "log" else (REGIME_SERVIZIO,)
        out: set[str] = set()
        for regime in regimi:
            out.update(r[0] for r in self._leggi_tutti(regime, "SELECT chiave FROM outbox WHERE tabella = ?", (tabella,))
                       if r[0] is not None)
        return out

    def tabelle_del_giorno(self, giorno: str) -> List[str]:
        """Le tabelle con righe locali nel giorno UTC (stato aggiornato o log scritto)."""
        trovate: set[str] = set()
        for regime in REGIMI_SQLITE:
            trovate.update(r[0] for r in self._leggi_tutti(
                regime, "SELECT DISTINCT tabella FROM righe WHERE strftime('%Y-%m-%d', aggiornato_ms / 1000, "
                        "'unixepoch') = ?", (giorno,)))
        percorso = self.cartella_log() / (giorno + ".jsonl")
        if percorso.exists():
            with open(percorso, "r", encoding="ascii", errors="replace") as f:
                for linea in f:
                    t = tabella_della_riga_log(linea)
                    if t:
                        trovate.add(t)
        return sorted(trovate)

    def scrivi_riconciliazione(self, tabella: str, giorno: str, esito: str, dettagli: Mapping[str, Any]) -> None:
        testo = testo_json(dict(dettagli))
        regime = self.spec(tabella).regime
        regime = regime if regime != "log" else REGIME_SERVIZIO
        self._esegui_sincrono(regime, lambda c: c.execute(
            "INSERT INTO riconciliazioni (tabella, giorno, esito, dettagli, ts_ms) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (tabella, giorno) DO UPDATE SET esito = excluded.esito, dettagli = excluded.dettagli, "
            "ts_ms = excluded.ts_ms", (tabella, giorno, esito, testo, self._ora_ms())))

    def riconciliazione(self, tabella: str, giorno: str) -> Optional[str]:
        regime = self.spec(tabella).regime
        regime = regime if regime != "log" else REGIME_SERVIZIO
        r = self._leggi_uno(regime, "SELECT esito FROM riconciliazioni WHERE tabella = ? AND giorno = ?", (tabella, giorno))
        return r[0] if r else None

    def dimensione_byte(self) -> int:
        totale = 0
        for radice, _, nomi in os.walk(self.cartella):
            for n in nomi:
                try:
                    totale += os.path.getsize(os.path.join(radice, n))
                except OSError:
                    continue
        return totale

    # ------------------------------------------------------------------ manutenzione
    def _ciclo_manutenzione(self) -> None:
        ultimo_pulizia = time.monotonic()
        connessioni: Dict[str, sqlite3.Connection] = {}
        try:
            for regime in REGIMI_SQLITE:
                connessioni[regime] = self._connetti(str(self.cartella / FILE_DB[regime]), regime, autocheckpoint=False)
            while not self._stop_manutenzione.wait(self._checkpoint_ogni_s):
                if self._checkpoint_esterno:
                    self._checkpoint(connessioni)
                if time.monotonic() - ultimo_pulizia >= self._pulizia_ogni_s:
                    ultimo_pulizia = time.monotonic()
                    try:
                        self.pulisci()
                    except Exception as exc:  # la pulizia riprova al giro dopo, mai in silenzio
                        logger.error("[archivio] pulizia: %s", exc)
        except Exception as exc:
            logger.error("[archivio] manutenzione ferma: %s", exc)
            self._evento("dati.archivio_guasto", {"processo": self.processo, "errore": f"manutenzione: {exc}"})
        finally:
            for conn in connessioni.values():
                conn.close()

    def _checkpoint(self, connessioni: Mapping[str, sqlite3.Connection]) -> None:
        for regime, conn in connessioni.items():
            t = time.perf_counter_ns()
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            except sqlite3.Error as exc:
                logger.warning("[archivio] checkpoint %s: %s", regime, exc)
                continue
            self._lat_checkpoint.append(time.perf_counter_ns() - t)

    def pulisci(self, adesso_ms: Optional[int] = None) -> Dict[str, int]:
        """Toglie cio' che e' gia' consegnato E riconciliato, oltre la conservazione.

        Righe di stato: aggiornate prima del limite, senza voci in outbox, giorno
        riconciliato ``ok``. File di log: giorno prima del limite, consegnati
        fino all'ultimo byte, ogni tabella del file riconciliata ``ok`` quel giorno.
        Mai le ``dead_letter``. M7: a pezzi di ``PULIZIA_PEZZO`` righe, ciascuno un lavoro
        di millisecondi: le scritture e i claim passano fra un pezzo e l'altro."""
        adesso = self._ora_ms() if adesso_ms is None else adesso_ms
        conteggi: Dict[str, int] = {}
        for regime in REGIMI_SQLITE:
            limite = adesso - int(self._conserva.get(regime, 30.0) * 86_400_000)
            conteggi[regime] = self._pulisci_righe(regime, limite)
            self._esegui_sincrono(regime, lambda c: c.execute(
                "DELETE FROM segnalazioni WHERE ts_ms < ?",
                (adesso - int(CONSERVA_SEGNALAZIONI_GIORNI * 86_400_000),)))
            for _ in range(200):                             # spazio restituito a pezzi (auto_vacuum INCREMENTAL)
                liberi = self._leggi_uno(regime, "PRAGMA freelist_count", ())
                if not liberi or int(liberi[0]) == 0:
                    break
                self._esegui_sincrono(regime, lambda c: c.execute("PRAGMA incremental_vacuum(500)").fetchall())
        conteggi["file_log"] = self._pulisci_log(adesso)
        self.contatori["pulizie"] += 1
        return conteggi

    def _pulisci_righe(self, regime: str, limite: int) -> int:
        tolte = 0
        cursore = ("", "")
        while True:
            candidate = self._leggi_tutti(
                regime, "SELECT tabella, chiave FROM righe WHERE (tabella, chiave) > (?, ?) AND aggiornato_ms < ? "
                        "ORDER BY tabella, chiave LIMIT ?", (*cursore, limite, PULIZIA_PEZZO))
            if not candidate:
                return tolte
            cursore = (candidate[-1][0], candidate[-1][1])

            def fn(conn: sqlite3.Connection, pezzo: List[Tuple[Any, ...]] = candidate) -> int:
                prima = conn.total_changes
                conn.executemany(
                    "DELETE FROM righe WHERE tabella = ? AND chiave = ? AND aggiornato_ms < ? AND NOT EXISTS ("
                    "SELECT 1 FROM outbox o WHERE o.tabella = righe.tabella AND o.chiave = righe.chiave) AND EXISTS ("
                    "SELECT 1 FROM riconciliazioni r WHERE r.tabella = righe.tabella AND r.esito = 'ok' AND "
                    "r.giorno = strftime('%Y-%m-%d', righe.aggiornato_ms / 1000, 'unixepoch'))",
                    [(t, k, limite) for t, k in pezzo])
                return conn.total_changes - prima

            tolte += int(self._esegui_sincrono(regime, fn))

    def _pulisci_log(self, adesso: int) -> int:
        limite = giorno_utc(adesso - int(self._conserva.get("log", 3.0) * 86_400_000))
        tolti = 0
        for percorso in self.file_log():
            giorno = percorso.stem
            if giorno >= limite:
                continue
            if self.offset_log(percorso.name) < percorso.stat().st_size:
                continue                                         # non ancora consegnato tutto
            tabelle = set()
            with open(percorso, "r", encoding="ascii", errors="replace") as f:
                for linea in f:
                    t = tabella_della_riga_log(linea)
                    if t:
                        tabelle.add(t)
            if any(self.riconciliazione(t, giorno) != "ok" for t in tabelle):
                continue

            def togli(conn: sqlite3.Connection, p: Path = percorso) -> None:
                # nel thread di scrittura: l'unico che scrive i file del giorno
                f = self._file_log.pop(p.name, None)
                if f is not None:
                    f.close()
                p.unlink()
                conn.execute("DELETE FROM consegna WHERE fonte = ?", ("log/" + p.name,))

            self._esegui_sincrono(REGIME_SERVIZIO, togli)
            tolti += 1
        return tolti

    # ------------------------------------------------------------------ misure ed eventi
    def misure(self) -> Dict[str, Any]:
        """p50/p95/p99/max in microsecondi (come ``m06``)."""
        def us(d: Iterable[int]) -> Dict[str, float]:
            return _percentili(x / 1000.0 for x in list(d))

        return {
            "accodamento_us": us(self._lat_accoda),
            "commit_us": {r: us(d) for r, d in self._lat_commit.items()},
            "durevole_dopo_us": {r: us(d) for r, d in self._lat_durevole.items()},
            "checkpoint_us": us(self._lat_checkpoint),
            "contatori": dict(self.contatori),
        }

    def _evento(self, nome: str, dati: Mapping[str, Any]) -> None:
        try:
            self._eventi(nome, dati)
        except Exception as exc:  # un ascoltatore guasto non ferma l'archivio, ma si vede
            logger.error("[archivio] ascoltatore dell'evento %s: %s", nome, exc)


def _stantia(rev: int, prec: int, valore: Any) -> bool:
    """M3: versione piu' vecchia OLTRE la tolleranza dell'orologio (intero: qualunque
    regressione; uguale = stessa versione, vince l'ultima scritta)."""
    if rev >= prec:
        return False
    if isinstance(valore, int) and not isinstance(valore, bool):
        return True
    return prec - rev > TOLLERANZA_OROLOGIO_US
