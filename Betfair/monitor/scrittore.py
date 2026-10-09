"""scrittore.py - la riga di "Salute" ogni 30 s per servizio (T0A, 09/10/2026).

UN thread demone per processo (``monitor-salute``), FUORI dal ciclo caldo: dorme
``intervallo`` secondi, fotografa e azzera i contatori in memoria
(``registro.py``), campiona il processo (``processo.py``) e scrive UNA riga:

  1. in locale, ``<repo>/_logs/monitor/<AAAA-MM-GG>/<servizio>.jsonl`` (append;
     ``_logs/`` e' gia' fuori da git): il referto puo' rileggerla senza DB;
  2. nel DB, tabella ``monitor_metrics`` (migrazione
     ``migrations/monitor_metrics_2026-10-09.sql``, la applica l'utente), con
     il client del thread (``db_client.get_supabase_client``). Se la tabella
     non c'e' o la rete e' giu': un avviso ogni 10 minuti, la riga locale resta.

Nessun processo nuovo, nessun I/O nei thread dei bot: il costo del giro dello
scrittore e' a sua volta misurato (tratto ``monitor_giro_ms``).

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import sonde
from .processo import CampionatoreProcesso, info_sistema

logger = logging.getLogger(__name__)

TABELLA = "monitor_metrics"
VERSIONE_RIGA = 1
#: ogni quante righe si allega ``sistema`` (versioni, Windows): 20 x 30 s = 10 min
OGNI_RIGHE_SISTEMA = 20
AVVISO_OGNI_S = 600.0

RADICE_REPO = Path(__file__).resolve().parents[2]


def cartella_locale(base: Optional[str] = None) -> Path:
    return Path(base) if base else RADICE_REPO / "_logs" / "monitor"


def _iso(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def costruisci_riga(servizio: str, sport: Optional[str], foto: Dict[str, Any],
                    proc: Dict[str, Any], *, adesso_ms: int, avvio_ms: Optional[int],
                    finestra_s: float, pid: int, sistema: Optional[Dict[str, Any]] = None,
                    host: Optional[str] = None) -> Dict[str, Any]:
    """La riga di ``monitor_metrics`` (colonne della migrazione). Pura."""
    cont = foto.get("contatori") or {}
    db_tot = int(sum((cont.get("db") or {}).values()))
    rest_tot = int(sum((cont.get("betfair_rest") or {}).values()))
    metriche: Dict[str, Any] = {
        "v": VERSIONE_RIGA,
        "finestra_s": round(float(finestra_s), 3),
        "processo": proc,
        "contatori": cont,
        "tratti": foto.get("tratti") or {},
        "valori": foto.get("valori") or {},
    }
    if sistema is not None:
        metriche["sistema"] = sistema
    return {
        "ts": _iso(adesso_ms),
        "servizio": servizio,
        "sport": sport,
        "pid": int(pid),
        "host": (host if host is not None else socket.gethostname())[:64],
        "avvio_ts": _iso(avvio_ms),
        "uptime_s": round((adesso_ms - avvio_ms) / 1000.0, 1) if avvio_ms else None,
        "cpu_pct": proc.get("cpu_pct"),
        "rss_mb": proc.get("rss_mb"),
        "db_richieste": db_tot,
        "rest_richieste": rest_tot,
        "metriche": metriche,
    }


def _invia_db(riga: Dict[str, Any]) -> None:
    """Scrittura nel DB col client del thread dello scrittore."""
    from db_client import get_supabase_client  # noqa: PLC0415 - import pigro

    get_supabase_client().table(TABELLA).insert(riga).execute()


class Scrittore(threading.Thread):
    def __init__(self, *, servizio: str, sport: Optional[str], intervallo: float,
                 invia: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 cartella: Optional[str] = None) -> None:
        super().__init__(name="monitor-salute", daemon=True)
        self.servizio = servizio
        self.sport = sport
        self.intervallo = float(intervallo)
        self._invia = invia or _invia_db
        self._cartella = cartella_locale(cartella)
        self._stop = threading.Event()
        self._proc = CampionatoreProcesso(str(RADICE_REPO))
        self._ultimo_ms = int(time.time() * 1000)
        self._righe = 0
        self._ultimo_avviso = 0.0
        self.scritte_db = 0
        self.errori_db = 0
        self._client_agganciato = False

    def run(self) -> None:
        while not self._stop.wait(self.intervallo):
            self.giro()

    def ferma(self, attesa_s: float = 2.0) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        try:
            self.giro()          # ultima riga (best-effort)
        except Exception:  # noqa: BLE001
            pass
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=attesa_s)

    def giro(self) -> Optional[Dict[str, Any]]:
        t0 = time.perf_counter()
        try:
            adesso = int(time.time() * 1000)
            finestra = (adesso - self._ultimo_ms) / 1000.0
            self._ultimo_ms = adesso
            foto = sonde.REGISTRO.fotografa_e_azzera()
            proc = self._proc.campiona()
            sistema = info_sistema() if self._righe % OGNI_RIGHE_SISTEMA == 0 else None
            st = sonde.stato()
            riga = costruisci_riga(self.servizio, self.sport, foto, proc, adesso_ms=adesso,
                                   avvio_ms=st.get("avvio_ms"), finestra_s=finestra,
                                   pid=os.getpid(), sistema=sistema)
            self._righe += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[monitor] riga non costruita: %s", str(e)[:200])
            return None
        self._scrivi_locale(riga)
        self._scrivi_db(riga)
        sonde.tratto("monitor_giro_ms", (time.perf_counter() - t0) * 1000.0)
        return riga

    def _scrivi_locale(self, riga: Dict[str, Any]) -> None:
        try:
            giorno = datetime.now().strftime("%Y-%m-%d")
            d = self._cartella / giorno
            d.mkdir(parents=True, exist_ok=True)
            nome = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in self.servizio)
            with open(d / f"{nome}.jsonl", "a", encoding="ascii") as fh:
                fh.write(json.dumps(riga, separators=(",", ":"), sort_keys=True,
                                    ensure_ascii=True, default=str) + "\n")
        except Exception as e:  # noqa: BLE001
            self._avvisa(f"riga locale non scritta: {str(e)[:160]}")

    def _scrivi_db(self, riga: Dict[str, Any]) -> None:
        try:
            self._invia(riga)
            self.scritte_db += 1
        except Exception as e:  # noqa: BLE001 - tabella assente, rete giu': si dice e si va avanti
            self.errori_db += 1
            self._avvisa(f"riga non scritta in {TABELLA} ({self.errori_db} in tutto; "
                         f"migrazione applicata?): {type(e).__name__}: {str(e)[:160]}")

    def _avvisa(self, testo: str) -> None:
        ora = time.monotonic()
        if ora - self._ultimo_avviso >= AVVISO_OGNI_S or self._ultimo_avviso == 0.0:
            self._ultimo_avviso = ora
            logger.warning("[monitor] %s", testo)
