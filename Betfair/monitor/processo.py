"""processo.py - risorse del processo e del sistema per il modulo "Salute" (T0A).

``psutil`` (``requirements.txt``: ``psutil==7.2.2``) se importabile; senza, si
DEGRADA alla libreria standard e lo si dichiara nella riga (``"psutil": false``):
CPU da ``os.times()`` (utente + sistema del processo), RSS da ``/proc`` (solo
Linux), thread Python da ``threading.active_count()``.

``info_sistema()`` (una volta ogni 10 minuti, chiamata dallo scrittore): versioni
di Python e dei pacchetti, e su Windows - se leggibili dal registro, SOLA
LETTURA, nessun processo lanciato - stato del servizio Ora di Windows, orario
attivo di Windows Update e riavvio pendente. Mai la rete.

ASCII-only; commenti in italiano.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import threading
import time
from typing import Any, Dict, Optional

#: pacchetti di cui si riporta la versione (il manifesto di T0C li bloccheranno)
PACCHETTI = ("flumine", "betfairlightweight", "supabase", "postgrest", "httpx", "requests",
             "websockets", "psutil", "python-dotenv")

_MB = 1024.0 * 1024.0


def _psutil() -> Any:
    try:
        import psutil  # noqa: PLC0415 - dipendenza facoltativa

        return psutil
    except Exception:  # noqa: BLE001
        return None


class CampionatoreProcesso:
    """CPU (% di UN core, media sulla finestra), memoria, thread, handle."""

    def __init__(self, radice: Optional[str] = None) -> None:
        self._ps = _psutil()
        self._radice = radice or os.getcwd()
        self._proc: Any = None
        if self._ps is not None:
            try:
                self._proc = self._ps.Process(os.getpid())
                self._proc.cpu_percent(None)        # innesco: la prima lettura vale 0
                self._ps.cpu_percent(None)
            except Exception:  # noqa: BLE001
                self._proc = None
        t = os.times()
        self._cpu_prec = (t.user + t.system, time.monotonic())

    @property
    def con_psutil(self) -> bool:
        return self._proc is not None

    def campiona(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"psutil": self.con_psutil}
        if self._proc is not None:
            try:
                p = self._proc
                with p.oneshot():
                    out["cpu_pct"] = round(float(p.cpu_percent(None)), 2)
                    mi = p.memory_info()
                    out["rss_mb"] = round(mi.rss / _MB, 2)
                    out["vms_mb"] = round(mi.vms / _MB, 2)
                    out["thread"] = int(p.num_threads())
                    if hasattr(p, "num_handles"):
                        out["handle"] = int(p.num_handles())
                    elif hasattr(p, "num_fds"):
                        out["fd"] = int(p.num_fds())
                out["cpu_sistema_pct"] = round(float(self._ps.cpu_percent(None)), 2)
                out["ram_sistema_pct"] = round(float(self._ps.virtual_memory().percent), 2)
            except Exception as e:  # noqa: BLE001
                out["errore"] = type(e).__name__
        else:
            t = os.times()
            ora = time.monotonic()
            cpu, prima = t.user + t.system, self._cpu_prec
            dt = ora - prima[1]
            out["cpu_pct"] = round(100.0 * (cpu - prima[0]) / dt, 2) if dt > 0 else None
            self._cpu_prec = (cpu, ora)
            out["rss_mb"] = _rss_proc_mb()
            out["thread"] = threading.active_count()
        try:
            du = shutil.disk_usage(self._radice)
            out["disco_libero_gb"] = round(du.free / (_MB * 1024.0), 2)
        except Exception:  # noqa: BLE001
            pass
        return out


def _rss_proc_mb() -> Optional[float]:
    """RSS da ``/proc/self/statm`` (Linux); None altrove."""
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as fh:
            pagine = int(fh.read().split()[1])
        return round(pagine * os.sysconf("SC_PAGE_SIZE") / _MB, 2)
    except Exception:  # noqa: BLE001
        return None


def versioni() -> Dict[str, Any]:
    out: Dict[str, Any] = {"python": sys.version.split()[0],
                           "piattaforma": platform.platform()[:80]}
    pk: Dict[str, Optional[str]] = {}
    try:
        from importlib import metadata

        for nome in PACCHETTI:
            try:
                pk[nome] = metadata.version(nome)
            except Exception:  # noqa: BLE001
                pk[nome] = None
    except Exception:  # noqa: BLE001
        pass
    out["pacchetti"] = pk
    return out


def _leggi_reg(radice: Any, chiave: str, nome: str) -> Any:
    import winreg  # noqa: PLC0415 - solo Windows

    with winreg.OpenKey(radice, chiave) as k:
        return winreg.QueryValueEx(k, nome)[0]


def _esiste_reg(radice: Any, chiave: str) -> bool:
    import winreg  # noqa: PLC0415

    try:
        with winreg.OpenKey(radice, chiave):
            return True
    except OSError:
        return False


def windows() -> Optional[Dict[str, Any]]:
    """Ora di Windows e Windows Update dal registro (sola lettura). None fuori
    da Windows; le voci illeggibili restano assenti (mai inventate)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    hk = winreg.HKEY_LOCAL_MACHINE
    out: Dict[str, Any] = {}
    letture = (
        ("w32time_avvio", r"SYSTEM\CurrentControlSet\Services\W32Time", "Start"),
        ("w32time_tipo", r"SYSTEM\CurrentControlSet\Services\W32Time\Parameters", "Type"),
        ("wu_ore_attive_inizio", r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", "ActiveHoursStart"),
        ("wu_ore_attive_fine", r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", "ActiveHoursEnd"),
        ("wu_pausa_fino_a", r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings", "PauseUpdatesExpiryTime"),
    )
    for campo, chiave, nome in letture:
        try:
            v = _leggi_reg(hk, chiave, nome)
            out[campo] = v if isinstance(v, (int, str)) else str(v)
        except Exception:  # noqa: BLE001
            pass
    out["wu_riavvio_pendente"] = (
        _esiste_reg(hk, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired")
        or _esiste_reg(hk, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending"))
    return out


def info_sistema() -> Dict[str, Any]:
    out = versioni()
    w = windows()
    if w is not None:
        out["windows"] = w
    ps = _psutil()
    if ps is not None:
        try:
            out["avvio_pc_s"] = int(ps.boot_time())
        except Exception:  # noqa: BLE001
            pass
    return out
