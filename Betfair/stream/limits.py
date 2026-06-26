"""Sicurezza limiti Betfair (F5) — logica PURA e testabile.

Obiettivo: NON farsi bannare. Due meccanismi:
  - budget mercati: avvisa (WARN) oltre la soglia di sicurezza, RIFIUTA oltre il
    tetto duro (così non si sottoscrivono troppi mercati su una connessione).
  - backoff esponenziale: davanti a SUBSCRIPTION_LIMIT_EXCEEDED / TOO_MANY_REQUESTS
    si aspetta sempre di più prima di ritentare (mai sub/unsub rapidi).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BudgetVerdict = Literal["OK", "WARN", "REFUSE"]


def check_market_budget(n_markets: int, safe_threshold: int, hard_cap: int) -> BudgetVerdict:
    """Valuta quanti mercati totali si sta per avere sotto una sola connessione."""
    if n_markets > hard_cap:
        return "REFUSE"
    if n_markets >= safe_threshold:
        return "WARN"
    return "OK"


def budget_message(verdict: BudgetVerdict, n_markets: int, safe: int, hard: int) -> str:
    if verdict == "REFUSE":
        return (
            f"Tetto mercati Betfair superato ({n_markets} > {hard}): nuove partite "
            f"NON verranno sottoscritte per evitare il ban. Riduci le partite seguite."
        )
    if verdict == "WARN":
        return (
            f"Vicino al limite Betfair: {n_markets} mercati attivi (soglia {safe}, "
            f"tetto {hard}). Attenzione ad aggiungere altre partite."
        )
    return f"Mercati attivi: {n_markets} (entro i limiti)."


@dataclass
class Backoff:
    """Backoff esponenziale con tetto, per i ritenti dopo errori di limite."""

    base_sec: float = 5.0
    max_sec: float = 300.0
    _failures: int = 0

    def reset(self) -> None:
        self._failures = 0

    @property
    def failures(self) -> int:
        return self._failures

    def next_delay(self) -> float:
        """Incrementa il contatore e ritorna il ritardo da attendere (secondi)."""
        delay = min(self.max_sec, self.base_sec * (2 ** self._failures))
        self._failures += 1
        return delay


# codici di errore Betfair che indicano sovraccarico → backoff
LIMIT_ERROR_CODES = frozenset(
    {
        "SUBSCRIPTION_LIMIT_EXCEEDED",
        "TOO_MANY_REQUESTS",
        "CONNECTION_FAILED",
        "MAX_CONNECTION_LIMIT_EXCEEDED",
    }
)


def is_limit_error(code: str | None) -> bool:
    return bool(code) and code.upper() in LIMIT_ERROR_CODES
