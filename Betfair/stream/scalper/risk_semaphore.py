"""Semaforo di rischio UNICO per evento (F5 review 11/07 — versione minima).

Visione (bibbia §11-bis punto 3): l'unico killer del multi-colpo/multi-linea
e' il GOL. Un semaforo per evento sospende i NUOVI INGRESSI di TUTTE le
micro-strategie (maker pre-match, sniper in-play, celle future) nei momenti
caldi e si riarma da solo; le CHIUSURE passano sempre. N strategie, UN rischio.

Versione minima (meccanismo, non edge): il segnale "momento caldo" e' la
SOSPENSIONE del mercato in-play (i gol sospendono tutti i mercati) → halt
degli ingressi per ``post_suspension_cooldown_s`` dopo l'ultima sospensione
vista. Il colpo del 10/07 alle 43.5' (fire nella turbolenza post-gol, stop in
16s) sarebbe stato fermato da questo semaforo. La taratura fine (celle
"minuti dal gol", tripwire pre-gol) arriva dall'Atlante — registro ipotesi §11.

Thread-safety: usato dai thread flumine delle strategie e dai watcher di
sessione; stato minimo protetto da lock.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional


class EventRiskSemaphore:
    """Semaforo condiviso tra le strategie di UNO stesso evento."""

    def __init__(
        self,
        post_suspension_cooldown_s: float = 120.0,
        emit: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.cooldown_ms = max(0.0, float(post_suspension_cooldown_s)) * 1000.0
        self._emit = emit
        self._lock = threading.Lock()
        self._halted_until_ms: float = 0.0
        self._suspensions: int = 0

    # ------------------------------------------------------------- segnali
    def on_suspension(self, now_ms: float) -> None:
        """Chiamata da OGNI strategia quando vede un book SUSPENDED in-play.

        Idempotente e cumulativa: ogni sospensione estende l'halt a
        now + cooldown (il gol tiene i mercati sospesi diversi secondi:
        l'halt decorre dall'ULTIMO segnale)."""
        if self.cooldown_ms <= 0:
            return
        emit_payload = None
        with self._lock:
            until = float(now_ms) + self.cooldown_ms
            if until > self._halted_until_ms:
                was_idle = float(now_ms) >= self._halted_until_ms
                self._halted_until_ms = until
                if was_idle:  # nuovo periodo caldo (non l'estensione di uno attivo)
                    self._suspensions += 1
                    emit_payload = {
                        "until_ms": until,
                        "cooldown_s": self.cooldown_ms / 1000.0,
                        "n": self._suspensions,
                    }
        if emit_payload is not None and self._emit is not None:
            try:
                self._emit("risk_halt", emit_payload)
            except Exception:  # noqa: BLE001 - telemetria best-effort
                pass

    # -------------------------------------------------------------- query
    def entries_halted(self, now_ms: float) -> bool:
        """True se i NUOVI ingressi sono sospesi (le chiusure passano sempre)."""
        with self._lock:
            return float(now_ms) < self._halted_until_ms

    def stats(self) -> dict:
        with self._lock:
            return {
                "halted_until_ms": self._halted_until_ms,
                "suspensions": self._suspensions,
            }


def notice_suspension(sem: Optional[Any], market_book: Any) -> None:
    """Hook difensivo per check_market_book: segnala al semaforo un book
    SUSPENDED in-play. No-op senza semaforo o fuori dall'in-play."""
    if sem is None:
        return
    try:
        if (getattr(market_book, "status", None) == "SUSPENDED"
                and bool(getattr(market_book, "inplay", False))):
            now = getattr(market_book, "publish_time_epoch", None)
            if now is not None:
                sem.on_suspension(float(now))
    except Exception:  # noqa: BLE001 - il semaforo non rompe mai lo stream
        pass
