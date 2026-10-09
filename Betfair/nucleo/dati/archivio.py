"""archivio.py - l'archivio locale INVISIBILE di un processo (W1-G1, implementa ``Archivio``).

Scopo
    Rendere durevole sul PC, fuori dal ciclo di decisione, ogni riga che oggi
    va al cloud, e tenerla in coda per il postino. Tre regimi (04 par. 6.1,
    numeri del laboratorio ``m06``):

    * ``stato_denaro`` -> ``denaro.sqlite3``, WAL ``synchronous=FULL``: durevole
      anche a PC spento (documentazione SQLite); un commit per gruppo di eventi
      arrivati insieme (group commit: ogni evento e' confermato solo dopo il
      SUO commit, la garanzia e' la stessa di «1 commit per evento»);
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
    Il checkpoint del WAL e' spento nei commit (``wal_autocheckpoint=0``) e lo
    fa il thread di manutenzione (``archivio-manutenzione``) con una sua
    connessione: fuori dal percorso caldo e fuori dal thread di scrittura.
    La pulizia toglie da sola cio' che e' consegnato E riconciliato (mai le
    ``dead_letter``, mai cio' che e' in coda).
    Ripresa dopo crash: un file JSONL che non finisce con ``\\n`` ha una riga
    troncata: si taglia, si SEGNALA (tabella ``segnalazioni`` + evento
    ``dati.riga_troncata``), non e' una ``dead_letter`` (05 T8 rettifica 4).

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
    nulla sulle righe: ne' soglie ne' stati dei bot.
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
from pathlib import Path
from typing import (Any, Callable, Deque, Dict, Iterable, List, Mapping, Optional, Sequence,
                    Tuple, Union)

from .contratto import Operazione, Regime, SpecTabella
from .percorso import Lucchetto, cartella_processo, prepara_cartella
from .schema_locale import (applica_schema, chiave_canonica, giorno_utc, iso_utc, riga_log,
                            rev_ordinabile, tabella_della_riga_log)

logger = logging.getLogger(__name__)

Registro = Union[Mapping[str, SpecTabella], Callable[[str], SpecTabella]]
Eventi = Callable[[str, Mapping[str, Any]], None]

REGIMI_SQLITE: Tuple[str, ...] = ("stato_denaro", "stato_vivo")
FILE_DB = {"stato_denaro": "denaro.sqlite3", "stato_vivo": "vivo.sqlite3"}
SINCRONIA = {"stato_denaro": "FULL", "stato_vivo": "NORMAL"}
#: dove vivono marcatori dei log, segnalazioni e dead_letter dei log
REGIME_SERVIZIO = "stato_vivo"

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


def _ora_ms() -> int:
    return time.time_ns() // 1_000_000


class ArchivioChiuso(RuntimeError):
    """Scrittura su un archivio non aperto (o in chiusura)."""


# ---------------------------------------------------------------------------
# voci della coda del thread di scrittura
# ---------------------------------------------------------------------------
class _Scrittura:
    __slots__ = ("n", "regime", "tabella", "op", "chiave", "testo", "rev", "coalesce", "ms", "t_ns", "futuro")

    def __init__(self, n: int, regime: str, tabella: str, op: str, chiave: str, testo: str,
                 rev: Optional[int], coalesce: bool, ms: int, t_ns: int,
                 futuro: Optional["Future[int]"] = None) -> None:
        self.n, self.regime, self.tabella, self.op, self.chiave = n, regime, tabella, op, chiave
        self.testo, self.rev, self.coalesce, self.ms, self.t_ns = testo, rev, coalesce, ms, t_ns
        self.futuro = futuro


class _Lavoro:
    __slots__ = ("n", "regime", "fn", "futuro")

    def __init__(self, n: int, regime: str, fn: Callable[[sqlite3.Connection], Any], futuro: "Future[Any]") -> None:
        self.n, self.regime, self.fn, self.futuro = n, regime, fn, futuro


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
        self._n = 0
        self._n_lock = threading.Lock()
        self._confermato = 0
        self._cond = threading.Condition()
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
        self.guasto: Optional[str] = None
        self.contatori: Counter[str] = Counter()
        self._lat_accoda: Deque[int] = deque(maxlen=_MISURE_MAX)
        self._lat_commit: Dict[str, Deque[int]] = {r: deque(maxlen=_MISURE_MAX) for r in (*REGIMI_SQLITE, "log")}
        self._lat_durevole: Dict[str, Deque[int]] = {r: deque(maxlen=_MISURE_MAX) for r in (*REGIMI_SQLITE, "log")}
        self._lat_checkpoint: Deque[int] = deque(maxlen=_MISURE_MAX)

    # ------------------------------------------------------------------ ciclo di vita
    def apri(self) -> "ArchivioLocale":
        """Crea la cartella, prende il lucchetto, aggiorna lo schema, ripara i log
        troncati, avvia i due thread. Idempotente."""
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
        return self

    def chiudi(self, timeout_s: float = 30.0) -> None:
        """Scrive tutto cio' che e' in coda, ferma i thread, checkpoint finale, rilascia."""
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
            f.close()
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
        """Accoda la riga (upsert per lo stato, insert per i log con ``uid``).

        Il chiamante paga: copia, uid/timbro se mancano, chiave, JSON, accodamento.
        La riga e' durevole quando ``conferma()`` torna vero."""
        t0 = time.perf_counter_ns()
        self._controlla_aperto()
        spec = self.spec(tabella)
        r = self._prepara(spec, riga)
        chiave = chiave_canonica(spec, r)
        rev = self._rev_di(spec, r)
        op = "upsert" if spec.regime != "log" or spec.chiave_naturale not in (("uid",),) else "insert"
        testo = json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str)
        ms = self._ora_ms()
        n = self._prossimo_n()
        if spec.regime != "log":
            with self._attesa_lock:
                prec = self._in_attesa.get((tabella, chiave))
                if rev is None or prec is None or prec[2] is None or rev > prec[2]:
                    self._in_attesa[(tabella, chiave)] = (n, testo, rev)
        self._coda.put(_Scrittura(n, spec.regime, tabella, op, chiave, testo, rev, spec.coalesce, ms, t0))
        self._lat_accoda.append(time.perf_counter_ns() - t0)

    def leggi(self, tabella: str, chiave: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        """L'ultima versione per chiave naturale (anche se non ancora su disco).

        Solo regimi di stato: i log non si rileggono per chiave (``ValueError``)."""
        spec = self.spec(tabella)
        if spec.regime == "log":
            raise ValueError(f"tabella {tabella}: i log non si leggono per chiave")
        self._controlla_aperto()
        k = chiave_canonica(spec, chiave)
        with self._attesa_lock:
            p = self._in_attesa.get((tabella, k))
        if p is not None:
            return None if p[1] is None else json.loads(p[1])
        riga = self._leggi_uno(spec.regime, "SELECT json FROM righe WHERE tabella = ? AND chiave = ?", (tabella, k))
        return None if riga is None else json.loads(riga[0])

    def transizione(self, tabella: str, chiave: Mapping[str, Any], da: str, a: str) -> bool:
        """Claim atomico: ``colonna_stato`` passa da ``da`` ad ``a`` solo se vale ``da``.

        Eseguito dal thread di scrittura (dopo tutte le scritture accodate prima);
        riga e outbox nella stessa transazione; la versione di riga sale."""
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
            testo = json.dumps(d, ensure_ascii=False, separators=(",", ":"), default=str)
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
        byte della riga nel file del giorno)."""
        if op not in ("upsert", "insert", "patch", "delete"):
            raise ValueError(f"operazione non ammessa: {op}")
        self._controlla_aperto()
        spec = self.spec(tabella)
        r = self._prepara(spec, riga) if op in ("upsert", "insert") else dict(riga)
        k = chiave if chiave is not None else chiave_canonica(spec, r)
        rev = self._rev_di(spec, r) if op != "delete" or (spec.rev_colonna and spec.rev_colonna in r) else None
        testo = json.dumps(r, ensure_ascii=False, separators=(",", ":"), default=str)
        ms = self._ora_ms()
        futuro: "Future[int]" = Future()
        self._coda.put(_Scrittura(self._prossimo_n(), spec.regime, tabella, op, k, testo, rev,
                                  bool(coalesce or spec.coalesce), ms, time.perf_counter_ns(), futuro))
        return futuro.result(timeout_s)

    def conferma(self, timeout_s: float = 10.0) -> bool:
        """Barriera: vero quando tutto cio' che e' stato accodato FINO A QUI e' su disco."""
        with self._n_lock:
            obiettivo = self._n
        fine = time.monotonic() + timeout_s
        with self._cond:
            while self._confermato < obiettivo:
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
        with self._n_lock:
            self._n += 1
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

    def _sali_rev(self, spec: SpecTabella, d: Dict[str, Any], rev_prec: Optional[int]) -> Optional[int]:
        """Versione nuova per una transizione: intero +1, istante = adesso (mai indietro)."""
        if not spec.rev_colonna:
            return None
        col = spec.rev_colonna
        if isinstance(d.get(col), int) and not isinstance(d.get(col), bool):
            d[col] = int(d[col]) + 1
            return d[col]
        ms = self._ora_ms()
        if rev_prec is not None and ms * 1000 <= rev_prec:
            ms = rev_prec // 1000 + 1
        d[col] = iso_utc(ms)
        return rev_ordinabile(d[col])

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
            if isinstance(v, (_Lavoro, _Scrittura)) and v.futuro is not None:
                v.futuro.set_exception(ArchivioChiuso("archivio in chiusura"))

    def _esegui_con_ritento(self, lotto: List[Any]) -> None:
        tentativo = 0
        while True:
            try:
                self._esegui_lotto(lotto)
                if self.guasto is not None:
                    self._evento("dati.archivio_ripreso", {"processo": self.processo, "dopo_tentativi": tentativo})
                    self.guasto = None
                return
            except Exception as exc:  # disco pieno, I/O: si ritenta, MAI si scarta
                tentativo += 1
                self.guasto = f"{type(exc).__name__}: {exc}"[:300]
                self.contatori["guasti_scrittura"] += 1
                self._evento("dati.archivio_guasto", {"processo": self.processo, "errore": self.guasto,
                                                       "tentativo": tentativo, "voci": len(lotto)})
                if self._in_chiusura and tentativo >= 3:
                    logger.critical("[archivio] chiusura con %d voci NON scritte dopo %d tentativi: %s",
                                    len(lotto), tentativo, self.guasto)
                    for v in lotto:
                        if v.futuro is not None and not v.futuro.done():
                            v.futuro.set_exception(exc)
                    return
                time.sleep(min(30.0, 0.5 * (2 ** min(tentativo, 6))))

    def _esegui_lotto(self, lotto: List[Any]) -> None:
        aperte: List[str] = []
        posizioni: Dict[str, int] = {}
        esiti: List[Tuple[Any, Any, Optional[BaseException]]] = []
        try:
            for v in lotto:
                if isinstance(v, _Scrittura) and v.regime == "log":
                    esiti.append((v, self._scrivi_log(v, posizioni), None))
                    continue
                conn = self._scrittori[v.regime]
                if v.regime not in aperte:
                    conn.execute("BEGIN IMMEDIATE")
                    aperte.append(v.regime)
                if isinstance(v, _Scrittura):
                    esiti.append((v, self._applica(conn, v), None))
                else:
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
            t_log = time.perf_counter_ns()
            for nome in posizioni:
                self._file_log[nome].flush()
            if posizioni:
                self._lat_commit["log"].append(time.perf_counter_ns() - t_log)
            for regime in sorted(aperte):            # denaro prima di vivo
                t = time.perf_counter_ns()
                self._scrittori[regime].execute("COMMIT")
                self._lat_commit[regime].append(time.perf_counter_ns() - t)
        except BaseException:
            for regime in aperte:
                try:
                    self._scrittori[regime].execute("ROLLBACK")
                except sqlite3.Error as exc:
                    logger.error("[archivio] rollback di %s: %s", regime, exc)
            self._riavvolgi_log(posizioni)
            raise
        self._dopo_commit(lotto, esiti)

    def _dopo_commit(self, lotto: List[Any], esiti: List[Tuple[Any, Any, Optional[BaseException]]]) -> None:
        adesso = time.perf_counter_ns()
        with self._attesa_lock:
            for v in lotto:
                if isinstance(v, _Scrittura):
                    self._lat_durevole[v.regime].append(adesso - v.t_ns)
                    p = self._in_attesa.get((v.tabella, v.chiave))
                    if p is not None and p[0] == v.n:
                        del self._in_attesa[(v.tabella, v.chiave)]
        massimo = max(v.n for v in lotto)
        with self._cond:
            if massimo > self._confermato:
                self._confermato = massimo
            self._cond.notify_all()
        for v, valore, exc in esiti:
            if v.futuro is not None and not v.futuro.done():
                if exc is not None:
                    v.futuro.set_exception(exc)
                else:
                    v.futuro.set_result(valore)
        if self._alla_conferma is not None:
            try:
                self._alla_conferma(massimo)
            except Exception as exc:  # il gancio dei test/misure non ferma lo scrittore
                logger.error("[archivio] gancio alla_conferma: %s", exc)

    def _applica(self, conn: sqlite3.Connection, v: _Scrittura) -> int:
        """Riga locale + outbox (stessa transazione). Ritorna il seq (0 = riga vecchia ignorata)."""
        if v.op in ("upsert", "insert"):
            if v.op == "insert":
                sql = ("INSERT INTO righe (tabella, chiave, json, rev, aggiornato_ms) VALUES (?, ?, ?, ?, ?) "
                       "ON CONFLICT (tabella, chiave) DO NOTHING")
            else:
                sql = ("INSERT INTO righe (tabella, chiave, json, rev, aggiornato_ms) VALUES (?, ?, ?, ?, ?) "
                       "ON CONFLICT (tabella, chiave) DO UPDATE SET json = excluded.json, rev = excluded.rev, "
                       "aggiornato_ms = excluded.aggiornato_ms "
                       "WHERE righe.rev IS NULL OR excluded.rev IS NULL OR excluded.rev > righe.rev")
            cur = conn.execute(sql, (v.tabella, v.chiave, v.testo, v.rev, v.ms))
            if cur.rowcount == 0 and v.op == "upsert":
                self.contatori["righe_vecchie_ignorate"] += 1      # mai indietro, come nel cloud
                return 0
        elif v.op == "patch":
            riga = conn.execute("SELECT json, rev FROM righe WHERE tabella = ? AND chiave = ?",
                                (v.tabella, v.chiave)).fetchone()
            if riga is not None:
                if v.rev is not None and riga[1] is not None and v.rev <= riga[1]:
                    self.contatori["righe_vecchie_ignorate"] += 1
                    return 0
                d = json.loads(riga[0])
                d.update(json.loads(v.testo))
                conn.execute("UPDATE righe SET json = ?, rev = ?, aggiornato_ms = ? WHERE tabella = ? AND chiave = ?",
                             (json.dumps(d, ensure_ascii=False, separators=(",", ":")), v.rev if v.rev is not None
                              else riga[1], v.ms, v.tabella, v.chiave))
        else:
            conn.execute("DELETE FROM righe WHERE tabella = ? AND chiave = ?", (v.tabella, v.chiave))
        return self._in_outbox(conn, v.tabella, v.op, v.chiave, v.testo, v.ms, v.coalesce)

    @staticmethod
    def _in_outbox(conn: sqlite3.Connection, tabella: str, op: str, chiave: str, testo: str, ms: int,
                   coalesce: bool) -> int:
        if coalesce and op == "upsert":
            # resta SOLO l'ultima versione per chiave; una voce gia' in volo che viene
            # tolta qui non fa danni: la conferma del postino cancella per seq
            conn.execute("DELETE FROM outbox WHERE tabella = ? AND chiave = ? AND op = 'upsert'", (tabella, chiave))
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
        """Lotto fallito: i byte scritti nei file del giorno si tolgono (niente meta' righe)."""
        for nome, pos in posizioni.items():
            f = self._file_log.get(nome)
            try:
                if f is not None:
                    f.flush()
                    f.seek(pos)
                    f.truncate()
            except OSError as exc:
                logger.error("[archivio] riavvolgimento di %s a %d: %s", nome, pos, exc)

    def _ripara_log_troncati(self) -> None:
        """Ripresa dopo crash: una riga finale senza ``\\n`` si taglia e si SEGNALA."""
        for percorso in sorted(self.cartella_log().glob("*.jsonl")):
            dim = percorso.stat().st_size
            if dim == 0:
                continue
            with open(percorso, "rb+") as f:
                f.seek(max(0, dim - 1))
                if f.read(1) == b"\n":
                    continue
                inizio = max(0, dim - 1_048_576)
                f.seek(inizio)
                coda = f.read()
                ultimo = coda.rfind(b"\n")
                taglio = inizio + ultimo + 1 if ultimo >= 0 else 0
                frammento = coda[ultimo + 1:] if ultimo >= 0 else coda
                f.seek(taglio)
                f.truncate()
            dettagli = {"file": percorso.name, "offset": taglio, "byte": len(frammento),
                        "anteprima": frammento[:200].decode("ascii", "replace")}
            self.contatori["righe_log_troncate"] += 1
            self._segnala_diretto("riga_log_troncata", dettagli)
            self._evento("dati.riga_troncata", dettagli)

    def _segnala_diretto(self, tipo: str, dettagli: Mapping[str, Any]) -> None:
        conn = self._scrittori[REGIME_SERVIZIO]
        conn.execute("INSERT INTO segnalazioni (tipo, dettagli, ts_ms) VALUES (?, ?, ?)",
                     (tipo, json.dumps(dict(dettagli), default=str), self._ora_ms()))

    # ------------------------------------------------------------------ lavori sincroni
    def _esegui_sincrono(self, regime: str, fn: Callable[[sqlite3.Connection], Any], timeout_s: float = 30.0) -> Any:
        if not self._aperto:
            raise ArchivioChiuso(f"archivio {self.processo} non aperto")
        futuro: "Future[Any]" = Future()
        self._coda.put(_Lavoro(self._prossimo_n(), regime, fn, futuro))
        return futuro.result(timeout_s)

    def _leggi_uno(self, regime: str, sql: str, args: Sequence[Any]) -> Optional[Tuple[Any, ...]]:
        with self._lettori_lock[regime]:
            return self._lettori[regime].execute(sql, tuple(args)).fetchone()

    def _leggi_tutti(self, regime: str, sql: str, args: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
        with self._lettori_lock[regime]:
            return self._lettori[regime].execute(sql, tuple(args)).fetchall()

    # ------------------------------------------------------------------ API per il postino e riconcilia
    def outbox_pronta(self, regime: str, adesso_ms: int, limite: int) -> List[VoceOutbox]:
        righe = self._leggi_tutti(regime, "SELECT seq, tabella, op, chiave, json, tentativi, creato_ms FROM outbox "
                                          "WHERE prossimo_ms <= ? ORDER BY seq LIMIT ?", (adesso_ms, int(limite)))
        return [VoceOutbox(regime, *r) for r in righe]

    def conteggi_outbox(self, regime: str) -> Tuple[Counter[str], Optional[int], int]:
        """(voci per tabella, creato_ms piu' vecchio, dead_letter)."""
        per = Counter({t: n for t, n in self._leggi_tutti(regime, "SELECT tabella, count(*) FROM outbox GROUP BY tabella")})
        vecchio = self._leggi_uno(regime, "SELECT min(creato_ms) FROM outbox", ())
        morti = self._leggi_uno(regime, "SELECT count(*) FROM dead_letter", ())
        return per, (vecchio[0] if vecchio else None), int(morti[0] if morti else 0)

    def chiudi_voci(self, regime: str, consegnate: Sequence[int], rimandate: Sequence[Tuple[int, int, int, str]],
                    morte: Sequence[Tuple[int, str, str, int]]) -> None:
        """Esito di un giro del postino: cancella le consegnate, rimanda (tentativi,
        prossimo, errore), sposta le morte in ``dead_letter``: UNA transazione."""
        adesso = self._ora_ms()

        def fn(conn: sqlite3.Connection) -> None:
            conn.executemany("DELETE FROM outbox WHERE seq = ?", [(s,) for s in consegnate])
            conn.executemany("UPDATE outbox SET tentativi = ?, prossimo_ms = ?, ultimo_errore = ? WHERE seq = ?",
                             [(t, p, e[:500], s) for s, t, p, e in rimandate])
            for seq, codice, errore, tentativi in morte:
                conn.execute("INSERT INTO dead_letter (fonte, seq_origine, tabella, op, chiave, json, codice, errore, "
                             "tentativi, creato_ms, morto_ms) SELECT 'outbox', seq, tabella, op, chiave, json, ?, ?, ?, "
                             "creato_ms, ? FROM outbox WHERE seq = ?", (codice, errore[:1000], tentativi, adesso, seq))
                conn.execute("DELETE FROM outbox WHERE seq = ?", (seq,))

        self._esegui_sincrono(regime, fn)

    def file_log(self) -> List[Path]:
        return sorted(self.cartella_log().glob("*.jsonl"))

    def offset_log(self, nome: str) -> int:
        r = self._leggi_uno(REGIME_SERVIZIO, "SELECT offset FROM consegna WHERE fonte = ?", ("log/" + nome,))
        return int(r[0]) if r else 0

    def chiudi_log(self, nome: str, nuovo_offset: int,
                   morte: Sequence[Tuple[str, str, str, str, int, str, str, int]],
                   ritenti: Sequence[Tuple[str, str, str, str, int, int, int, str]]) -> None:
        """Avanza il marcatore del file e, NELLA STESSA transazione, mette le righe
        rifiutate in ``dead_letter`` e quelle da ritentare nella outbox del vivo."""
        adesso = self._ora_ms()

        def fn(conn: sqlite3.Connection) -> None:
            conn.execute("INSERT INTO consegna (fonte, offset, aggiornato_ms) VALUES (?, ?, ?) ON CONFLICT (fonte) "
                         "DO UPDATE SET offset = excluded.offset, aggiornato_ms = excluded.aggiornato_ms "
                         "WHERE excluded.offset > consegna.offset", ("log/" + nome, int(nuovo_offset), adesso))
            for tabella, op, chiave, testo, ms, codice, errore, tentativi in morte:
                conn.execute("INSERT INTO dead_letter (fonte, seq_origine, tabella, op, chiave, json, codice, errore, "
                             "tentativi, creato_ms, morto_ms) VALUES ('log', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             (tabella, op, chiave, testo, codice, errore[:1000], tentativi, ms, adesso))
            for tabella, op, chiave, testo, ms, tentativi, prossimo, errore in ritenti:
                conn.execute("INSERT INTO outbox (tabella, op, chiave, json, creato_ms, tentativi, prossimo_ms, "
                             "ultimo_errore) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                             (tabella, op, chiave, testo, ms, tentativi, prossimo, errore[:500]))

        self._esegui_sincrono(REGIME_SERVIZIO, fn)

    def segnala(self, tipo: str, dettagli: Mapping[str, Any]) -> None:
        testo = json.dumps(dict(dettagli), default=str)
        self._esegui_sincrono(REGIME_SERVIZIO, lambda c: c.execute(
            "INSERT INTO segnalazioni (tipo, dettagli, ts_ms) VALUES (?, ?, ?)", (tipo, testo, self._ora_ms())))

    def segnalazioni(self) -> List[Dict[str, Any]]:
        return [{"id": i, "tipo": t, "dettagli": json.loads(d), "ts_ms": ts} for i, t, d, ts in
                self._leggi_tutti(REGIME_SERVIZIO, "SELECT id, tipo, dettagli, ts_ms FROM segnalazioni ORDER BY id")]

    def dead_letter(self) -> List[Dict[str, Any]]:
        """Tutte le righe morte dei due file (visibili, mai cancellate da sole)."""
        out: List[Dict[str, Any]] = []
        for regime in REGIMI_SQLITE:
            for r in self._leggi_tutti(regime, "SELECT id, fonte, tabella, op, chiave, json, codice, errore, tentativi, "
                                               "morto_ms FROM dead_letter ORDER BY id"):
                out.append({"regime": regime, "id": r[0], "fonte": r[1], "tabella": r[2], "op": r[3], "chiave": r[4],
                            "riga": json.loads(r[5]), "codice": r[6], "errore": r[7], "tentativi": r[8],
                            "morto_ms": r[9]})
        return out

    def rimetti_in_coda(self, regime: str, id_dead_letter: int) -> int:
        """Dopo la correzione (es. migrazione applicata): la riga torna in outbox."""
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

    def scrivi_riconciliazione(self, tabella: str, giorno: str, esito: str, dettagli: Mapping[str, Any]) -> None:
        testo = json.dumps(dict(dettagli), default=str)
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
        Mai le ``dead_letter``. Ritorna i conteggi."""
        adesso = self._ora_ms() if adesso_ms is None else adesso_ms
        conteggi: Dict[str, int] = {}
        for regime in REGIMI_SQLITE:
            limite = adesso - int(self._conserva.get(regime, 30.0) * 86_400_000)

            def fn(conn: sqlite3.Connection, limite: int = limite) -> int:
                cur = conn.execute(
                    "DELETE FROM righe WHERE aggiornato_ms < ? AND NOT EXISTS (SELECT 1 FROM outbox o WHERE "
                    "o.tabella = righe.tabella AND o.chiave = righe.chiave) AND EXISTS (SELECT 1 FROM riconciliazioni r "
                    "WHERE r.tabella = righe.tabella AND r.esito = 'ok' AND "
                    "r.giorno = strftime('%Y-%m-%d', righe.aggiornato_ms / 1000, 'unixepoch'))", (limite,))
                conn.execute("DELETE FROM segnalazioni WHERE ts_ms < ?",
                             (adesso - int(CONSERVA_SEGNALAZIONI_GIORNI * 86_400_000),))
                return int(cur.rowcount or 0)

            conteggi[regime] = int(self._esegui_sincrono(regime, fn))
            self._esegui_sincrono(regime, lambda c: c.execute("PRAGMA incremental_vacuum(2000)").fetchall())
        conteggi["file_log"] = self._pulisci_log(adesso)
        self.contatori["pulizie"] += 1
        return conteggi

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
