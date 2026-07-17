"""Registrazione nativa raw via tee nel listener (F1).

betfairlightweight `StreamListener.on_data(raw_data)` riceve la stringa grezza di
ogni messaggio (mcm/status/...). Sottoclassandolo possiamo SCRIVERE il raw nativo
E lasciar parsare normalmente il MarketBook → dalla STESSA subscription otteniamo
sia il file nativo (per FlumineSimulation/Backtest) sia i book parsati (live_now +
curator). Niente seconda connessione/subscription → nessun rischio limiti.

Il file nativo è newline-delimited di messaggi `mcm` (formato storico Betfair),
filtrati per evento → un file replayabile per partita: `<event>/<event>.raw.jsonl`.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Set

from betfairlightweight import StreamListener
from flumine.streams.marketstream import MarketStream

logger = logging.getLogger(__name__)


class _RawState:
    """Stato condiviso (impostato dal runner prima dello stream)."""

    def __init__(self) -> None:
        self.dir: Optional[str] = None
        self.market_to_event: Dict[str, str] = {}
        self.enabled: bool = False
        # REGISTRAZIONE OPT-IN (17/07, cantiere "Segui live"): set degli
        # event_id con live_follow.record=true → SOLO questi finiscono nel tee
        # raw. None = NESSUN gating (comportamento storico: registra tutto) —
        # è il fallback quando la migrazione live_follow_record.sql non è
        # applicata (colonna assente) e il default dei runner tennis.
        self.record_events: Optional[Set[str]] = None
        self._files: Dict[str, Any] = {}
        self._lock = threading.Lock()
        # HEARTBEAT "recorder vivo" (fix 11/07, lezione 10/07: tee morto in
        # silenzio = in-play perso per sempre): contatori esposti alla
        # telemetria — bytes scritti, ts ultimo write, errori di scrittura.
        self.bytes_written: Dict[str, int] = {}
        self.last_write_ms: Dict[str, int] = {}
        self.write_errors: int = 0
        self._err_logged: Dict[str, float] = {}
        # HEARTBEAT DI CONNESSIONE (fix 17/07): Betfair manda mcm ct=HEARTBEAT
        # ogni 0.5-5s quando non c'è traffico dati. Tracciarli SEPARATAMENTE
        # distingue un mercato quieto (heartbeat freschi, dati fermi) da uno
        # stream morto (nessun messaggio di alcun tipo). 0 = mai visto.
        self.last_heartbeat_ms: int = 0
        # BATTITO DATI (opt-in 17/07): pt dell'ultimo messaggio mcm CON market
        # change visto, A PRESCINDERE dal gating record. Con la registrazione
        # opt-in la maggior parte delle partite NON scrive raw: il rilevamento
        # stallo del runner deve misurare la salute dello STREAM, non quante
        # partite registriamo — altrimenti restart a raffica su stream sani.
        self.last_data_ms: int = 0

    def configure(
        self,
        data_dir: str,
        market_to_event: Dict[str, str],
        enabled: bool,
        record_events: Optional[Set[str]] = None,
    ) -> None:
        self.dir = data_dir
        self.market_to_event = market_to_event  # riferimento vivo (aggiornato dal runner)
        self.enabled = enabled
        # gating opt-in: copia difensiva; None = registra tutto (storico/tennis)
        self.record_events = set(record_events) if record_events is not None else None
        # reset dei contatori di salute a ogni (ri)configurazione (review 16/07):
        # il singleton sopravvive ai restart della subscription — senza reset,
        # dopo un rebuild lo "stall" veniva misurato sui timestamp della vita
        # precedente e uno stream sano-ma-quieto rischiava un re-restart inutile.
        self.last_write_ms = {}
        self.last_heartbeat_ms = 0
        self.last_data_ms = 0

    def set_record_events(self, record_events: Optional[Set[str]]) -> None:
        """Aggiorna il set degli eventi in REGISTRAZIONE (chiamato dal runner a
        ogni risincronizzazione dei follow): un click su "Segui live" a partita
        in corso fa entrare l'evento nel set → il tee inizia a scrivere da quel
        momento. None = gating disattivato (colonna record assente).

        MARKER FORENSE (review 17/07): ogni toggle ON/OFF lascia una riga
        ``record_toggle`` nel sidecar .recmeta.jsonl — un buco nel raw causato
        da uno spegni/riaccendi DELIBERATO è spiegato, non un mistero."""
        with self._lock:
            old = self.record_events
            new = set(record_events) if record_events is not None else None
            self.record_events = new
        if old is None or new is None or old == new:
            return
        ts = int(time.time() * 1000)
        for ev in new - old:
            self._write_meta(ev, {"kind": "record_toggle", "on": True, "ts_ms": ts})
        for ev in old - new:
            self._write_meta(ev, {"kind": "record_toggle", "on": False, "ts_ms": ts})

    def file_for(self, event_id: str) -> Any:
        fh = self._files.get(event_id)
        if fh is None:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            raw_path = os.path.join(ev_dir, f"{event_id}.raw.jsonl")
            # MARKER DI COPERTURA (fix registrazioni parziali 16/07): documenta
            # l'inizio di una SESSIONE di registrazione nel sidecar .recmeta.jsonl
            # (mai dentro il raw: il formato nativo deve restare replayabile).
            # raw_bytes_at_open > 0 = ripresa in append dopo un restart → il
            # confine del possibile buco e' esplicito per la validazione.
            size0 = os.path.getsize(raw_path) if os.path.exists(raw_path) else 0
            self._write_meta(event_id, {
                "kind": "open",
                "ts_ms": int(time.time() * 1000),
                "raw_bytes_at_open": size0,
                "pid": os.getpid(),
            })
            fh = open(raw_path, "a", encoding="utf-8")  # noqa: SIM115 - chiuso in close()
            self._files[event_id] = fh
            logger.info("[raw] apro file nativo: %s", raw_path)
        return fh

    def _write_meta(self, event_id: str, record: Dict[str, Any]) -> None:
        """Appende una riga al sidecar `<event>.recmeta.jsonl`. Best-effort:
        un errore sul meta NON deve mai toccare il tee del raw."""
        try:
            ev_dir = os.path.join(self.dir or ".", event_id)
            os.makedirs(ev_dir, exist_ok=True)
            path = os.path.join(ev_dir, f"{event_id}.recmeta.jsonl")
            with open(path, "a", encoding="utf-8") as mfh:
                mfh.write(json.dumps(record, separators=(",", ":")) + "\n")
        except Exception as exc:  # noqa: BLE001 - solo telemetria
            logger.debug("[raw] recmeta KO per %s (ignorato): %s", event_id, exc)

    def health(self) -> Dict[str, Any]:
        """Snapshot per la telemetria (bytes/ultimo write per evento)."""
        with self._lock:
            return {
                "enabled": self.enabled,
                "bytes": dict(self.bytes_written),
                "last_write_ms": dict(self.last_write_ms),
                "last_heartbeat_ms": self.last_heartbeat_ms,
                "last_data_ms": self.last_data_ms,
                "write_errors": self.write_errors,
            }

    def write_message(self, raw_data: str) -> None:
        if not self.enabled or not self.dir:
            return
        try:
            msg = json.loads(raw_data)
        except (ValueError, TypeError):
            return
        if msg.get("op") != "mcm":
            return
        # HEARTBEAT (fix 17/07, PRIMA dello scarto "senza mc"): i messaggi
        # ct=HEARTBEAT non hanno market change e non vanno nel raw, ma provano
        # che la CONNESSIONE è viva. Prima venivano scartati senza traccia →
        # un mercato quieto (metà tempo) era indistinguibile da uno stream
        # morto e il runner si auto-infliggeva restart inutili.
        if str(msg.get("ct") or "").upper() == "HEARTBEAT":
            pt = msg.get("pt")
            hb_ms = int(pt) if isinstance(pt, (int, float)) else int(time.time() * 1000)
            with self._lock:  # coerenza col resto della classe (review 17/07)
                self.last_heartbeat_ms = hb_ms
            return
        mc = msg.get("mc")
        if not mc:
            return
        # BATTITO DATI + snapshot del gating (opt-in 17/07): il battito va
        # aggiornato PRIMA dello scarto record — prova che lo stream è vivo
        # anche quando nessuna partita è in registrazione.
        pt_msg = msg.get("pt")
        with self._lock:
            self.last_data_ms = (
                int(pt_msg) if isinstance(pt_msg, (int, float)) else int(time.time() * 1000)
            )
            rec = None if self.record_events is None else set(self.record_events)
        # raggruppa i market change per evento e scrive un messaggio mcm valido per file
        by_event: Dict[str, list] = {}
        for change in mc:
            mid = change.get("id")
            ev = self.market_to_event.get(mid, "_unrouted")
            by_event.setdefault(ev, []).append(change)
        # REGISTRAZIONE OPT-IN: gli eventi SENZA "Segui live" (record=false)
        # vengono scartati QUI, prima di aprire/scrivere qualunque file — per
        # loro niente raw, niente directory, niente byte su disco. rec=None =
        # gating disattivato (colonna assente/tennis) → si registra tutto.
        if rec is not None:
            by_event = {ev: changes for ev, changes in by_event.items() if ev in rec}
            if not by_event:
                return
        with self._lock:
            for ev, changes in by_event.items():
                out = {k: msg[k] for k in ("op", "clk", "pt", "ct") if k in msg}
                out["mc"] = changes
                line = json.dumps(out, separators=(",", ":")) + "\n"
                # SELF-HEAL (fix 11/07): un handle rotto (disco, close
                # concorrente durante un soft-restart) prima uccideva il tee
                # PER SEMPRE in silenzio (debug-log). Ora: drop dell'handle e
                # riapertura al prossimo messaggio, WARNING visibile
                # (throttled 60s per evento), contatore errori esposto.
                try:
                    fh = self.file_for(ev)
                    fh.write(line)
                    fh.flush()
                except Exception as exc:  # noqa: BLE001 - mai rompere lo stream
                    self.write_errors += 1
                    bad = self._files.pop(ev, None)
                    if bad is not None:
                        try:
                            bad.close()
                        except Exception:  # noqa: BLE001
                            pass
                    import time as _t
                    now_s = _t.time()
                    if now_s - self._err_logged.get(ev, 0.0) >= 60.0:
                        self._err_logged[ev] = now_s
                        logger.warning(
                            "[raw] write KO per evento %s (riapro al prossimo "
                            "messaggio): %s", ev, str(exc)[:150])
                    continue
                self.bytes_written[ev] = self.bytes_written.get(ev, 0) + len(line)
                pt = msg.get("pt")
                self.last_write_ms[ev] = int(pt) if isinstance(pt, (int, float)) else 0

    def mark_resubscribe(self, reason: str) -> None:
        """Marker ``kind:"resubscribe"`` nel sidecar `.recmeta.jsonl` (fix 17/07).

        I restart SOFT della subscription (stall-recovery, F3 nuove partite)
        NON passano dal marker open/close di processo: senza traccia, un buco
        di registrazione da resubscribe era indistinguibile da un buco di rete.
        Scrive SOLO nel sidecar — il formato raw resta byte-identico. Best-effort.
        """
        if not self.enabled or not self.dir:
            return
        ts = int(time.time() * 1000)
        with self._lock:
            events = set(self._files.keys()) | set(self.market_to_event.values())
            # opt-in 17/07: il marker riguarda solo gli eventi IN registrazione
            # (o con un file già aperto) — mai creare sidecar/directory per
            # partite che per scelta non vengono registrate.
            if self.record_events is not None:
                events = {e for e in events if e in self.record_events or e in self._files}
            for ev in sorted(events):
                self._write_meta(ev, {
                    "kind": "resubscribe",
                    "ts_ms": ts,
                    "reason": str(reason)[:200],
                    "last_pt_ms": self.last_write_ms.get(ev, 0),
                })

    def close(self) -> None:
        with self._lock:
            for ev, fh in self._files.items():
                try:
                    fh.close()
                except Exception:  # noqa: BLE001
                    pass
                # MARKER DI COPERTURA: fine sessione di registrazione (shutdown
                # pulito). last_pt_ms = publish-time dell'ultimo messaggio scritto.
                self._write_meta(ev, {
                    "kind": "close",
                    "ts_ms": int(time.time() * 1000),
                    "last_pt_ms": self.last_write_ms.get(ev, 0),
                    "bytes_written": self.bytes_written.get(ev, 0),
                })
            self._files.clear()


# singleton condiviso processo-wide (il listener è creato da flumine internamente)
RAW_STATE = _RawState()


def configure_raw(
    data_dir: str,
    market_to_event: Dict[str, str],
    enabled: bool,
    record_events: Optional[Set[str]] = None,
) -> None:
    RAW_STATE.configure(data_dir, market_to_event, enabled, record_events)


def close_raw() -> None:
    RAW_STATE.close()


class RawTeeStreamListener(StreamListener):
    """StreamListener che fa il tee del raw nativo e poi parsa normalmente."""

    def on_data(self, raw_data: str):  # type: ignore[override]
        try:
            RAW_STATE.write_message(raw_data)
        except Exception as e:  # noqa: BLE001 - il recording NON deve mai rompere lo stream
            logger.debug("[raw] tee fallito (ignorato): %s", e)
        return super().on_data(raw_data)


class RawTeeMarketStream(MarketStream):
    """MarketStream che usa il listener con tee del raw (una sola subscription)."""

    LISTENER = RawTeeStreamListener
