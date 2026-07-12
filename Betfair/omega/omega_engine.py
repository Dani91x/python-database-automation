"""omega_engine — LOGICA PURA del bot Omega (nessun I/O, nessuna rete).

Tutto ciò che è money-critical vive qui ed è coperto da test pytest:
selezione del risultato, sizing del lay, target dinamico, fill PAPER,
settlement, finestra d'ingresso. Nessuna funzione qui apre connessioni,
legge il DB o chiama Betfair: riceve dati già estratti e ritorna decisioni.

Riferimento: COSTITUZIONE_OMEGA.md §2 (matematica), §3 (selezione),
§4 (timing), §6 (lifecycle).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Betfair price ladder (tick validi Exchange). Correct Score sta quasi sempre
# nelle bande alte (>=20) → tick 1.0/2.0/5.0/10.0.
# ---------------------------------------------------------------------------
_LADDER: tuple[tuple[float, float, float], ...] = (
    (1.01, 2.0, 0.01),
    (2.0, 3.0, 0.02),
    (3.0, 4.0, 0.05),
    (4.0, 6.0, 0.10),
    (6.0, 10.0, 0.20),
    (10.0, 20.0, 0.50),
    (20.0, 30.0, 1.0),
    (30.0, 50.0, 2.0),
    (50.0, 100.0, 5.0),
    (100.0, 1000.0, 10.0),
)

MIN_PRICE = 1.01
MAX_PRICE = 1000.0

# Un nome runner è una "scoreline" numerica se è del tipo "H - A" (Betfair usa
# "0 - 0", "1 - 0", ...). Gli aggregati sono "Any Other Home Win", "Any Unquoted", ecc.
_SCORELINE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def round_to_tick(price: float) -> float:
    """Arrotonda un prezzo al tick Betfair valido più vicino (clamp ai limiti)."""
    if price <= MIN_PRICE:
        return MIN_PRICE
    if price >= MAX_PRICE:
        return MAX_PRICE
    for lo, hi, step in _LADDER:
        if lo <= price < hi:
            steps = round((price - lo) / step)
            snapped = lo + steps * step
            # evita di scivolare nella banda successiva per arrotondamento
            snapped = min(snapped, hi - step) if snapped >= hi else snapped
            return round(snapped, 2)
    return round(price, 2)


def is_scoreline(name: Optional[str]) -> bool:
    """True se il nome runner è un punteggio esatto numerico ("2 - 1")."""
    if not name:
        return False
    return bool(_SCORELINE_RE.match(name))


def parse_scoreline(name: str) -> Optional[tuple[int, int]]:
    """Ritorna (home, away) da "2 - 1", altrimenti None."""
    m = _SCORELINE_RE.match(name or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


@dataclass(frozen=True)
class ScoreRunner:
    """Uno runner del mercato CORRECT_SCORE con i suoi best lay/back."""

    selection_id: int
    name: str
    lay_price: Optional[float] = None
    lay_size: float = 0.0
    back_price: Optional[float] = None
    back_size: float = 0.0
    # ladder lay completa opzionale: [(price, size), ...] dal best al peggiore
    lay_ladder: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Selection:
    """Esito della selezione: il runner scelto + motivazione."""

    selection_id: int
    name: str
    price: float
    lay_size_available: float


def select_lay_runner(
    runners: list[ScoreRunner],
    *,
    price_min: float,
    price_max: float,
    min_liquidity: float,
    include_aggregate: bool,
) -> Optional[Selection]:
    """Sceglie il risultato esatto MENO probabile con quota nel range (§3).

    Regola: tra i runner con best-lay nel range [price_min, price_max] e
    liquidità >= min_liquidity (ed eventualmente solo scoreline numeriche),
    prende quello con **quota lay più ALTA** (probabilità minima).
    Tie-break: liquidità maggiore, poi selection_id (stabile).
    Ritorna None se nessuno qualifica.
    """
    candidates: list[ScoreRunner] = []
    for r in runners:
        if r.lay_price is None:
            continue
        if not include_aggregate and not is_scoreline(r.name):
            continue
        if r.lay_price < price_min or r.lay_price > price_max:
            continue
        if r.lay_size < min_liquidity:
            continue
        candidates.append(r)

    if not candidates:
        return None

    # quota più alta = meno probabile; tie-break su liquidità e id
    best = max(candidates, key=lambda r: (r.lay_price, r.lay_size, -r.selection_id))
    return Selection(
        selection_id=best.selection_id,
        name=best.name,
        price=round_to_tick(best.lay_price),
        lay_size_available=best.lay_size,
    )


# ---------------------------------------------------------------------------
# Target dinamico e sizing (§2)
# ---------------------------------------------------------------------------
def dynamic_target(goal: float, realized: float, matches_remaining: int) -> float:
    """P = (G − R) / max(M, 1), vincolato a P >= 0 (I4)."""
    remaining = max(int(matches_remaining), 1)
    p = (float(goal) - float(realized)) / remaining
    return max(p, 0.0)


def lay_size_from_target(
    target: float,
    *,
    commission: float,
    min_stake: float,
    rounding: float = 0.01,
) -> float:
    """Backer-stake s tale che l'incasso netto = target: s = target / (1 − c).

    Applica lo stake minimo .it e l'arrotondamento. Ritorna 0.0 se target<=0.
    """
    if target <= 0:
        return 0.0
    c = float(commission)
    denom = max(1.0 - c, 1e-6)
    s = target / denom
    if s < min_stake:
        s = min_stake
    if rounding and rounding > 0:
        s = round(round(s / rounding) * rounding, 2)
    return max(s, 0.0)


def liability_from_lay(size: float, price: float) -> float:
    """Liability di un lay: size · (price − 1)."""
    return round(float(size) * (float(price) - 1.0), 2)


def apply_liability_cap(size: float, price: float, cap: float) -> float:
    """Se cap>0 e liability>cap, riduce la size così che liability<=cap."""
    if not cap or cap <= 0:
        return size
    if price <= 1.0:
        return size
    max_size = cap / (price - 1.0)
    if size > max_size:
        return round(max_size, 2)
    return size


def net_profit_if_win(size: float, commission: float) -> float:
    """Incasso netto di un lay vinto (il risultato NON esce): size · (1 − c)."""
    return round(float(size) * (1.0 - float(commission)), 2)


# ---------------------------------------------------------------------------
# PAPER fill model (§6): cammina la ladder lay disponibile.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PaperFill:
    matched_size: float
    avg_price: float
    fully_matched: bool


def paper_fill(
    target_size: float,
    best_price: float,
    lay_ladder: tuple[tuple[float, float], ...] = (),
) -> Optional[PaperFill]:
    """Simula il match di un lay per ``target_size``.

    Se ``lay_ladder`` è fornita (dal best al peggiore) cammina i livelli;
    altrimenti usa solo (best_price, +inf) con la liquidità al best implicita.
    Ritorna None se non si può riempire nulla.
    """
    if target_size <= 0:
        return None
    levels = list(lay_ladder) if lay_ladder else [(best_price, target_size)]
    remaining = target_size
    cost = 0.0
    filled = 0.0
    for price, avail in levels:
        if remaining <= 0:
            break
        take = min(remaining, avail)
        if take <= 0:
            continue
        cost += take * price
        filled += take
        remaining -= take
    if filled <= 0:
        return None
    avg = cost / filled
    return PaperFill(
        matched_size=round(filled, 2),
        avg_price=round(avg, 4),
        fully_matched=remaining <= 1e-9,
    )


# ---------------------------------------------------------------------------
# Settlement (§6, I3): P&L dal risultato del mercato.
# ---------------------------------------------------------------------------
def aggregate_trades(rows: list[dict]) -> dict:
    """Aggrega le righe ``omega_trades`` → totali. PURA e testabile (money-critical).

    'won/lost/void' → realizzato; 'open' → liability aperta; 'pending' CON ``bet_id``
    → ordine reale già a mercato: conta nell'esposizione aperta (I8). 'pending'
    senza bet_id ed 'error' NON contano come piazzati.
    """
    realized = 0.0
    open_liab = 0.0
    settled = 0
    traded = 0
    open_n = 0
    for r in rows:
        st = r.get("status")
        if st in ("won", "lost", "void"):
            realized += float(r.get("pnl") or 0.0)
            settled += 1
            traded += 1
        elif st == "open" or (st == "pending" and r.get("bet_id")):
            open_liab += float(r.get("liability") or 0.0)
            open_n += 1
            traded += 1
    return {
        "realized_profit": round(realized, 2),
        "open_liability": round(open_liab, 2),
        "matches_traded": traded,
        "matches_open": open_n,
        "settled_count": settled,
        "total_count": len(rows),
    }


_TERMINAL_RUNNER = {"WINNER", "LOSER", "REMOVED", "REMOVED_VACANT"}


def resolve_settlement(
    market_status: Optional[str],
    runner_statuses: list[Optional[str]],
    any_winner: bool,
) -> tuple[bool, bool]:
    """Decide (closed, voided) da stato mercato + stati runner. PURA e testabile.

    Regola money-critical (I3): un mercato è REGOLATO solo se ``CLOSED`` **e** OGNI
    runner ha uno stato TERMINALE (WINNER/LOSER/REMOVED/REMOVED_VACANT); altrimenti
    è trattato come NON-chiuso (settle_open ritenta al ciclo dopo — mai un P&L
    sbagliato). ``voided`` = regolato senza alcun vincitore (mercato annullato).
    """
    closed = market_status == "CLOSED"
    if not closed:
        return (False, False)
    all_terminal = bool(runner_statuses) and all(s in _TERMINAL_RUNNER for s in runner_statuses)
    if not all_terminal:
        return (False, False)  # chiuso ma non finalizzato → non regolare ora
    return (True, not any_winner)


def settle_pnl(
    *,
    our_selection_id: int,
    winner_selection_id: Optional[int],
    size: float,
    price: float,
    commission: float,
    voided: bool = False,
    side: str = "lay",
) -> tuple[str, float]:
    """Ritorna (status, pnl) dato il vincitore del mercato. Default LAY (automatico).

    LAY:  runner nostro vince (risultato ESCE) → ('lost', −liability); altrimenti
          ('won', +size·(1−c)).
    BACK: runner nostro vince → ('won', +size·(price−1)·(1−c)); altrimenti
          ('lost', −size).
    voided → ('void', 0.0).
    """
    if voided or winner_selection_id is None:
        return ("void", 0.0)
    is_winner = int(winner_selection_id) == int(our_selection_id)
    if str(side).lower() == "back":
        if is_winner:
            return ("won", round(float(size) * (float(price) - 1.0) * (1.0 - float(commission)), 2))
        return ("lost", -round(float(size), 2))
    # LAY
    if is_winner:
        return ("lost", -liability_from_lay(size, price))
    return ("won", net_profit_if_win(size, commission))


# ---------------------------------------------------------------------------
# Finestra d'ingresso (§4)
# ---------------------------------------------------------------------------
def minute_from_clock(market_start: datetime, now: datetime) -> int:
    """Minuti trascorsi da marketStartTime (fallback quando manca il feed)."""
    if market_start.tzinfo is None:
        market_start = market_start.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = (now - market_start).total_seconds()
    return int(delta // 60)


def is_in_entry_window(minute: Optional[int], mn: int, mx: int) -> bool:
    """True se il minuto è dentro [mn, mx]."""
    if minute is None:
        return False
    return mn <= int(minute) <= mx


def is_eligible(
    *,
    inplay: bool,
    minute: Optional[int],
    entry_minute_min: int,
    entry_minute_max: int,
    already_traded: bool,
    traded_count: int,
    max_events: int,
    goal_reached: bool,
    stop_on_goal: bool,
) -> bool:
    """Compone tutte le condizioni di eleggibilità del §4 + stop_on_goal."""
    if already_traded:
        return False
    if not inplay:
        return False
    if not is_in_entry_window(minute, entry_minute_min, entry_minute_max):
        return False
    if max_events and max_events > 0 and traded_count >= max_events:
        return False
    if stop_on_goal and goal_reached:
        return False
    return True
