"""E34 — Stop giornaliero di conto: matematica PURA (nessun I/O).

Fonte autoritativa del P&L di giornata (mai ricalcolato a mano):
  realized  = somma dei ``profit`` in ``betfair_live_settled`` nella giornata
              locale del runner (PAPER: flumine ``order.simulated.profit``;
              LIVE: cleared orders Betfair via flumine ``poll_market_closure``).
  open_mtm  = somma del mark-to-market (``risk_engine.mark_to_market``, stessa
              aritmetica del green-up) sulle posizioni matched ancora aperte,
              con W/L letti dal blotter flumine.
  totale    = realized + open_mtm → lo stop scatta quando totale <= -limit.

Regole money-critical:
  - limite None / <= 0 / non finito → stop DISATTIVATO (mai un falso scatto
    con la soglia spenta); la validazione UI/DB impedisce comunque <= 0.
  - posizione senza prezzi utilizzabili → si valuta il WORST-CASE
    (min(worst_if_win, worst_if_lose)): conservativo, può solo ANTICIPARE lo
    scatto, mai ritardarlo (mai un mancato scatto). Il flag ``degraded``
    segnala che la stima è worst-case.
  - dati corrotti/non finiti → ValueError (mai errori silenziosi → il worker
    li trasforma in alert, non in "0").
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from .risk_engine import FLAT_EPS, mark_to_market

# Tolleranza sul confine dello scatto: il rumore float NON deve mai salvare
# dallo scatto quando il totale è AL limite.
_BOUNDARY_EPS = 1e-9


def _to_finite(value: object, what: str) -> float:
    """Converte in float FINITO; qualunque altra cosa è un errore ESPLICITO."""
    if value is None:
        raise ValueError(f"{what} mancante")
    try:
        f = float(value)  # accetta anche NUMERIC serializzato come stringa
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} non numerico: {value!r}") from exc
    if not math.isfinite(f):
        raise ValueError(f"{what} non finito: {value!r}")
    return f


def realized_pnl(rows: Iterable[Mapping]) -> float:
    """Somma dei profit settled. Righe corrotte → ValueError (mai 0 silenzioso)."""
    total = 0.0
    for row in rows:
        if "profit" not in row:
            raise ValueError("riga settled senza campo profit")
        total += _to_finite(row.get("profit"), "profit settled")
    return total


@dataclass(frozen=True)
class OpenPosition:
    """Snapshot di una posizione aperta (tutti i numeri dal blotter flumine)."""

    matched_if_win: float
    matched_if_lose: float
    best_back: Optional[float]
    best_lay: Optional[float]
    worst_if_win: float = 0.0
    worst_if_lose: float = 0.0


def open_mtm(positions: Sequence[OpenPosition]) -> Tuple[float, bool]:
    """(MTM totale, degraded). degraded=True se almeno una posizione è stata
    valutata al worst-case per prezzi mancanti/invalidi (stima conservativa)."""
    total = 0.0
    degraded = False
    for pos in positions:
        w = _to_finite(pos.matched_if_win, "matched_if_win")
        l = _to_finite(pos.matched_if_lose, "matched_if_lose")
        if abs(w) < FLAT_EPS and abs(l) < FLAT_EPS:
            continue  # nessuna posizione matched
        mtm = mark_to_market(w, l, pos.best_back, pos.best_lay)
        if mtm is None:
            # prezzi inutilizzabili → worst-case (mai ignorare la posizione).
            ww = _to_finite(pos.worst_if_win, "worst_if_win")
            wl = _to_finite(pos.worst_if_lose, "worst_if_lose")
            total += min(ww, wl)
            degraded = True
        else:
            total += mtm
    return total, degraded


@dataclass(frozen=True)
class DailyStopDecision:
    fire: bool
    total: Optional[float]
    realized: float
    open_mtm: float
    limit: Optional[float]
    degraded: bool
    reason: str


def evaluate_daily_stop(
    realized: float,
    open_mtm_value: float,
    limit: Optional[float],
    *,
    degraded: bool = False,
) -> DailyStopDecision:
    """Decisione PURA dello stop giornaliero. ``limit`` è la perdita massima
    tollerata in EUR (positiva, es. 50 = scatta a −€50 di giornata)."""
    r = _to_finite(realized, "realized")
    m = _to_finite(open_mtm_value, "open_mtm")
    total = r + m
    if limit is None:
        return DailyStopDecision(False, total, r, m, None, degraded, "limit_off")
    try:
        lim = _to_finite(limit, "daily_loss_limit")
    except ValueError:
        return DailyStopDecision(False, total, r, m, None, degraded, "limit_invalid")
    if lim <= 0.0:
        return DailyStopDecision(False, total, r, m, lim, degraded, "limit_invalid")
    fire = total <= (-lim + _BOUNDARY_EPS)
    reason = "loss_limit_hit" if fire else "within_limit"
    return DailyStopDecision(fire, total, r, m, lim, degraded, reason)


def day_window_utc(now_local: datetime) -> Tuple[datetime, datetime]:
    """[mezzanotte locale, mezzanotte locale successiva) espressa in UTC.

    La "giornata" dello stop è quella LOCALE del runner (l'utente ragiona in
    ora italiana). Richiede un datetime timezone-aware: uno naive è ambiguo e
    va rifiutato (money-critical)."""
    if now_local.tzinfo is None or now_local.tzinfo.utcoffset(now_local) is None:
        raise ValueError("day_window_utc richiede un datetime timezone-aware")
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )
