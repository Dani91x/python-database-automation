"""Registrazione OPT-IN per-partita del raw nativo tennis (tee nel listener).

RIUSO del recorder della missione 1-tick tennis (10/07): stesso pattern e stesso
FORMATO di ``tennis_scalper/record_multi.py`` (tee del messaggio ``mcm`` nativo
nel ``StreamListener.on_data`` → ``<DIR>/<event>/<event>.raw.jsonl`` + punteggio
sincronizzato ``<event>/<event>.score.jsonl``), che è esattamente il layout
consumato dai lab tennis (``flb_backtest``/``lab_grid``/``lab_grid_score``/
``backtest_pro``/``validate``: glob ``<dir>/*/*.raw.jsonl``).

Differenze rispetto a record_multi (processo di campagna massiva):
  * qui il tee vive DENTRO il runner tennis, sulla STESSA subscription per-evento
    (stream unico: nessuna seconda connessione Betfair, zero REST extra);
  * gating PER-EVENTO opt-in: si registra SOLO l'evento con ``record=true`` in
    ``tennis_live_follow`` (migrazione ``tennis_follow_record.sql``). Il flag è
    riletto periodicamente dal ``record_flag_worker`` → il toggle a metà partita
    accende/spegne il tee senza riavviare lo stream;
  * fallback conservativo: colonna assente (migrazione non applicata) → NESSUNA
    registrazione + warning una tantum, il runner non si rompe mai.

Self-contained come record_multi: NON tocca ``raw_listener``/``recorder``
condivisi col calcio (singleton e listener DEDICATI al tennis). Il tee non deve
MAI rompere lo stream: ogni scrittura è best-effort con self-heal dell'handle.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set

from betfairlightweight import StreamListener
from flumine.streams.marketstream import MarketStream

logger = logging.getLogger(__name__)


def default_record_dir(now: Optional[datetime] = None) -> str:
    """Cartella di output delle registrazioni tennis.

    Root = env ``TENNIS_RECORD_DIR`` oppure ``~/Desktop/tennis_rec`` (la stessa
    usata dalle campagne record_multi della missione 1-tick, vedi
    BIBBIA_SCALPER_TENNIS §dati), con sottocartella per giorno UTC — layout
    finale ``<root>/<YYYYMMDD>/<event>/<event>.raw.jsonl``, replayabile as-is
    dai lab (``--data <root>/<YYYYMMDD>``).
    """
    root = os.getenv("TENNIS_RECORD_DIR", "").strip() or os.path.join(
        os.path.expanduser("~"), "Desktop", "tennis_rec"
    )
    day = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return os.path.join(root, day)


class TennisRawTee:
    """Stato del tee raw tennis con gating PER-EVENTO (istanza dedicata al tennis).

    Adattamento di ``record_multi._MultiRawState``: stesso formato su disco,
    in più ``enabled_events`` (opt-in per-partita) e lo score tee integrato
    (dedup sulla score key, come lo ``_score_worker`` di record_multi).
    """

    def __init__(self) -> None:
        self.dir: Optional[str] = None
        self.market_to_event: Dict[str, str] = {}
        self.enabled_events: Set[str] = set()
        self._files: Dict[str, Any] = {}          # event_id -> raw file handle
        self._score_files: Dict[str, Any] = {}    # event_id -> score file handle
        self._score_lastkey: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}
        self._err_logged: Dict[str, float] = {}

    # -- controllo (record_flag_worker) ------------------------------------ #
    def enable(self, event_id: str, market_ids: Iterable[str]) -> None:
        """Accende la registrazione per UN evento (idempotente)."""
        ev = str(event_id)
        with self._lock:
            if self.dir is None:
                self.dir = default_record_dir()
            for mid in market_ids or []:
                if mid:
                    self.market_to_event[str(mid)] = ev
            if ev not in self.enabled_events:
                self.enabled_events.add(ev)
                logger.info("[tennis-rec] REC ON evento %s -> %s", ev, self.dir)

    def disable(self, event_id: str) -> None:
        """Spegne la registrazione per UN evento e chiude i file (idempotente)."""
        ev = str(event_id)
        with self._lock:
            if ev in self.enabled_events:
                self.enabled_events.discard(ev)
                logger.info("[tennis-rec] REC OFF evento %s", ev)
            for pool in (self._files, self._score_files):
                fh = pool.pop(ev, None)
                if fh is not None:
                    try:
                        fh.close()
                    except Exception:  # noqa: BLE001
                        pass

    def is_enabled(self, event_id: str) -> bool:
        return str(event_id) in self.enabled_events

    # -- tee raw (listener) ------------------------------------------------ #
    def _file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
            fh = open(path, "a", encoding="utf-8")  # noqa: SIM115 - chiuso in disable/close
            self._files[event_id] = fh
            logger.info("[tennis-rec] apro file nativo: %s", path)
        return fh

    def write_message(self, raw_data: str) -> None:
        """Tee di UN messaggio raw dello stream. Percorso veloce: nessun evento
        registrato → return immediato (zero impatto sulle partite non registrate)."""
        if not self.enabled_events or not self.dir:
            return
        try:
            msg = json.loads(raw_data)
        except (ValueError, TypeError):
            return
        if msg.get("op") != "mcm":
            return
        mc = msg.get("mc")
        if not mc:
            return
        # auto-routing market->event dalla marketDefinition (come record_multi):
        # copre i mercati imparati dopo l'enable senza dipendere dal worker.
        for change in mc:
            mid = change.get("id")
            mdef = change.get("marketDefinition") or {}
            ev = mdef.get("eventId")
            if mid and ev and mid not in self.market_to_event:
                self.market_to_event[mid] = str(ev)
        by_event: Dict[str, list] = {}
        for change in mc:
            mid = change.get("id")
            ev = self.market_to_event.get(mid)
            if ev is None or ev not in self.enabled_events:
                continue  # opt-in: gli eventi non registrati non toccano il disco
            by_event.setdefault(ev, []).append(change)
        if not by_event:
            return
        with self._lock:
            for ev, changes in by_event.items():
                if ev not in self.enabled_events:  # ricontrollo sotto lock (toggle)
                    continue
                out = {k: msg[k] for k in ("op", "clk", "pt", "ct") if k in msg}
                out["mc"] = changes
                # SELF-HEAL (lezione raw_listener 11/07): un handle rotto non deve
                # uccidere il tee per sempre — drop e riapertura al prossimo messaggio.
                try:
                    fh = self._file_for(ev)
                    fh.write(json.dumps(out, separators=(",", ":")) + "\n")
                    fh.flush()
                except Exception as exc:  # noqa: BLE001 - mai rompere lo stream
                    bad = self._files.pop(ev, None)
                    if bad is not None:
                        try:
                            bad.close()
                        except Exception:  # noqa: BLE001
                            pass
                    now_s = time.time()
                    if now_s - self._err_logged.get(ev, 0.0) >= 60.0:
                        self._err_logged[ev] = now_s
                        logger.warning("[tennis-rec] write KO evento %s (riapro al "
                                       "prossimo messaggio): %s", ev, str(exc)[:150])
                    continue
                self._counts[ev] = self._counts.get(ev, 0) + 1

    # -- tee punteggio (score_and_now_worker) ------------------------------ #
    def write_score(self, event_id: str, ts: Any) -> None:
        """Appende il punteggio sincronizzato (formato record_multi: una riga
        ``{"t": epoch, "score": raw}`` per cambio di score key). Best-effort."""
        ev = str(event_id)
        if ts is None or ev not in self.enabled_events or not self.dir:
            return
        try:
            key = ts.key()
            if self._score_lastkey.get(ev) == key:
                return
            with self._lock:
                if ev not in self.enabled_events:
                    return
                self._score_lastkey[ev] = key
                fh = self._score_files.get(ev)
                if fh is None:
                    ev_dir = os.path.join(self.dir, ev)
                    os.makedirs(ev_dir, exist_ok=True)
                    fh = open(os.path.join(ev_dir, f"{ev}.score.jsonl"), "a",
                              encoding="utf-8")  # noqa: SIM115
                    self._score_files[ev] = fh
                fh.write(json.dumps({"t": time.time(), "score": ts.raw},
                                    default=str) + "\n")
                fh.flush()
        except Exception as exc:  # noqa: BLE001 - lo score tee non rompe mai il worker
            logger.debug("[tennis-rec] score tee KO %s (ignorato): %s", ev, exc)

    # -- telemetria / teardown --------------------------------------------- #
    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def close(self) -> None:
        with self._lock:
            for pool in (self._files, self._score_files):
                for fh in pool.values():
                    try:
                        fh.close()
                    except Exception:  # noqa: BLE001
                        pass
                pool.clear()
            self.enabled_events.clear()


# singleton DEDICATO al tennis (il listener è istanziato da flumine internamente;
# sopravvive ai restart del framework → il toggle e i file restano coerenti).
RAW_TEE = TennisRawTee()

# warning una tantum "migrazione non applicata" (fallback conservativo)
_MISSING_COLUMN_WARNED = False


class _TennisRecListener(StreamListener):
    """StreamListener tennis: tee del raw nativo, poi parsing normale."""

    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            RAW_TEE.write_message(raw_data)
        except Exception as e:  # noqa: BLE001 - il recording non deve MAI rompere lo stream
            logger.debug("[tennis-rec] tee fallito (ignorato): %s", e)
        return super().on_data(raw_data)


class TennisRecMarketStream(MarketStream):
    """MarketStream del runner tennis con tee opt-in (stessa subscription)."""

    LISTENER = _TennisRecListener


def sync_record_flags(follows: List[Dict[str, Any]],
                      market_meta: Dict[str, Dict[str, Any]],
                      tee: Optional[TennisRawTee] = None) -> Set[str]:
    """Allinea il tee ai flag ``record`` di ``tennis_live_follow``.

    ``follows`` = righe follow (select *, quindi con ``record`` SOLO se la
    migrazione è applicata); ``market_meta`` = mappa event_id -> meta del runner
    (per il routing market->event). Ritorna gli eventi con registrazione attiva.

    FALLBACK CONSERVATIVO: se nessuna riga espone la chiave ``record`` (colonna
    assente = migrazione ``tennis_follow_record.sql`` non applicata) NON si
    registra nulla (default storico del tennis) e si logga un warning una
    tantum. Mai un'eccezione verso il chiamante.
    """
    global _MISSING_COLUMN_WARNED  # noqa: PLW0603 - warning una tantum di processo
    tee = tee if tee is not None else RAW_TEE
    enabled: Set[str] = set()
    try:
        rows = [r for r in (follows or []) if r.get("event_id")]
        if rows and not any("record" in r for r in rows):
            if not _MISSING_COLUMN_WARNED:
                _MISSING_COLUMN_WARNED = True
                logger.warning(
                    "[tennis-rec] colonna 'record' assente su tennis_live_follow: "
                    "applica migrations/tennis_follow_record.sql per la "
                    "registrazione opt-in. Nessuna registrazione (default storico).")
            rows = []
        wanted = {str(r["event_id"]) for r in rows if bool(r.get("record"))}
        # enable SOLO per gli eventi effettivamente streammati dal runner
        for ev in sorted(wanted):
            meta = market_meta.get(ev) or {}
            mid = meta.get("market_id")
            if not mid:
                continue  # non (ancora) catalogato: riproverà al prossimo giro
            tee.enable(ev, [mid])
            enabled.add(ev)
        # disable per gli eventi accesi ma non più richiesti (toggle OFF a metà)
        for ev in sorted(set(tee.enabled_events) - enabled):
            tee.disable(ev)
    except Exception as e:  # noqa: BLE001 - il gating non rompe mai il worker
        logger.warning("[tennis-rec] sync flag KO (ignorato): %s", e)
    return enabled
