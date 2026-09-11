"""omega_engine — LOGICA PURA del bot Omega (nessun I/O, nessuna rete).

Tutto ciò che è money-critical vive qui ed è coperto da test pytest:
selezione del risultato, sizing del lay, target dinamico, fill PAPER,
settlement, finestra d'ingresso. Nessuna funzione qui apre connessioni,
legge il DB o chiama Betfair: riceve dati già estratti e ritorna decisioni.

Riferimento: COSTITUZIONE_OMEGA.md §2 (matematica), §3 (selezione),
§4 (timing), §6 (lifecycle).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional
from zoneinfo import ZoneInfo

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


def _tick_bounds(price: float) -> tuple[float, float]:
    """(tick valido ≤ price, tick valido ≥ price) sulla scala Betfair. Il bordo
    superiore di una banda È un tick valido (è l'inizio della banda dopo)."""
    if price <= MIN_PRICE:
        return MIN_PRICE, MIN_PRICE
    if price >= MAX_PRICE:
        return MAX_PRICE, MAX_PRICE
    for lo, hi, step in _LADDER:
        if lo <= price < hi:
            n = int((price - lo) / step + 1e-9)
            low = round(lo + n * step, 2)
            high = round(min(low + step, hi), 2)
            if abs(low - price) < 1e-9:
                high = low
            return low, high
    return round(price, 2), round(price, 2)


def round_to_tick(price: float) -> float:
    """Tick Betfair valido PIÙ VICINO (review 11/09 HIGH-2: la vecchia versione
    scendeva di un tick intero quando il tick giusto era il bordo della banda:
    49,9 → 48 invece di 50; 99 → 95 invece di 100)."""
    low, high = _tick_bounds(float(price))
    return low if (price - low) <= (high - price) else high


def tick_up(price: float) -> float:
    """Primo tick valido ≥ price (per un LAY taker: accettare un prezzo ≥ per matchare)."""
    return _tick_bounds(float(price))[1]


def tick_down(price: float) -> float:
    """Ultimo tick valido ≤ price (per un BACK taker)."""
    return _tick_bounds(float(price))[0]


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
# Giornata operativa (§2): "oggi" = giorno solare Europe/Rome. Senza questo
# scoping R/matches_traded sarebbero CUMULATIVI A VITA → con stop_on_goal=true
# il bot smetterebbe di piazzare per sempre dal 2° giorno in profitto.
# ---------------------------------------------------------------------------
OPERATIONAL_TZ = "Europe/Rome"


def day_start_utc(now: datetime, tz_name: str = OPERATIONAL_TZ) -> datetime:
    """Mezzanotte locale (tz operativa) del giorno di ``now``, come datetime UTC."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local = now.astimezone(ZoneInfo(tz_name))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(timezone.utc)


def _ts_on_or_after(iso: Optional[str], boundary: Optional[datetime]) -> bool:
    """True se ``iso`` >= ``boundary`` (o se il confine manca: retro-compatibile).

    Un timestamp assente/non parsabile con un confine attivo ritorna False:
    un trade senza data certa non deve MAI gonfiare i contatori di oggi.
    """
    if boundary is None:
        return True
    if not iso:
        return False
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t >= boundary


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
    if rounding and rounding > 0:
        s = round(round(s / rounding) * rounding, 2)
    if s < min_stake:
        s = float(min_stake)          # minimo DOPO l'arrotondamento (review LOW)
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
    max_size = math.floor(cap / (price - 1.0) * 100.0) / 100.0   # mai sopra il cap (review MED-11)
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
    limit_price: Optional[float] = None,
    side: str = "lay",
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
        # review MED-9: un ordine LIMITE non cammina oltre il proprio prezzo
        # (lay: mai a prezzi PIÙ ALTI del limite; back: mai più bassi)
        if limit_price is not None and (
                (side == "lay" and price > float(limit_price) + 1e-9)
                or (side == "back" and price < float(limit_price) - 1e-9)):
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
def aggregate_trades(rows: list[dict], day_start: Optional[datetime] = None) -> dict:
    """Aggrega le righe ``omega_trades`` → totali. PURA e testabile (money-critical).

    'won/lost/void' → realizzato; 'open' → liability aperta; 'pending' CON ``bet_id``
    → ordine reale già a mercato: conta nell'esposizione aperta (I8). Anche il
    'pending' PAPER in attesa del fill flumine (``meta.flumine_client_ref``,
    fix F2 review 16/07) conta come piazzato: l'ordine simulato È sul book del
    runner — senza, ``max_events``/liability sarebbero aggirabili nella finestra
    TTL. 'pending' senza bet_id/marker ed 'error' NON contano come piazzati.

    Con ``day_start`` (mezzanotte operativa, vedi ``day_start_utc``) calcola ANCHE
    i valori della GIORNATA (§2/§14). GIORNATA DI UNA POSIZIONE = giorno in cui
    la sua APERTURA è stata piazzata (``placed_at``): le gambe di chiusura
    ereditano il giorno dell'apertura che chiudono. Così R di oggi è il P&L
    delle PARTITE DI OGGI, e una gamba di ieri regolata dopo mezzanotte non
    sposta la barra di oggi (decisione utente 11/09: "ogni giorno il P&L parte
    da 0 in base alle partite di quella giornata"). liability aperta resta
    SEMPRE totale: il rischio vivo non ha giorno. Senza ``day_start`` i campi
    _today coincidono col cumulato (fallback).
    """
    realized = 0.0
    open_liab = 0.0
    settled = 0
    traded = 0
    open_n = 0
    realized_today = 0.0
    traded_today = 0
    events_all: set = set()
    events_today: set = set()
    # AUDIT 11/09 (H-02/H-06/H-08): numeri della giornata e stati del rischio
    reconciling_liab = 0.0
    locked_open = 0.0
    locked_open_today = 0.0
    legs_today = 0
    live_events: set = set()
    pnl_by_parent: dict[Any, float] = {}
    placed_by_id = {r.get("id"): r.get("placed_at") for r in rows if r.get("id") is not None}
    for r in rows:
        # esito della POSIZIONE (apertura + chiusure) per il segno V/P della giornata
        if r.get("closes_trade_id") and r.get("status") in ("won", "lost", "void"):
            pnl_by_parent[r["closes_trade_id"]] = pnl_by_parent.get(r["closes_trade_id"], 0.0) \
                + float(r.get("pnl") or 0.0)
    won_today = 0
    lost_today = 0
    won_all = 0
    lost_all = 0
    for r in rows:
        st = r.get("status")
        if r.get("closes_trade_id"):
            # gamba di CHIUSURA (cash out, 10/09): il rischio vivo della coppia è già
            # contato dall'originale 'hedged' (stima prudente: liability piena fino al
            # settlement); il suo pnl entra nel realizzato solo quando regolata, nel
            # GIORNO dell'apertura che chiude (fallback: il proprio placed_at).
            if st in ("won", "lost", "void"):
                pnl = float(r.get("pnl") or 0.0)
                realized += pnl
                day_ts = placed_by_id.get(r.get("closes_trade_id")) or r.get("placed_at")
                if _ts_on_or_after(day_ts, day_start):
                    realized_today += pnl
            continue
        if st in ("won", "lost", "void"):
            pnl = float(r.get("pnl") or 0.0)
            realized += pnl
            settled += 1
            traded += 1
            events_all.add(str(r.get("event_id")))
            # esito della POSIZIONE (apertura + chiusure) per SEGNO del P&L totale
            total = pnl + pnl_by_parent.get(r.get("id"), 0.0)
            if total > 0:
                won_all += 1
            elif total < 0:
                lost_all += 1
            if _ts_on_or_after(r.get("placed_at"), day_start):
                realized_today += pnl
                traded_today += 1
                legs_today += 1
                events_today.add(str(r.get("event_id")))
                if total > 0:
                    won_today += 1
                elif total < 0:
                    lost_today += 1
        elif st in ("open", "hedged") or (st == "pending" and is_placed(r)):
            open_liab += residual_liability(r)
            lk = locked_open_pnl(r)
            if lk is not None:
                locked_open += lk
                # review H1: la quota della GIORNATA serve alle guardie giornaliere
                # (stop-loss, target dinamico); il totale serve al cap di esposizione
                if _ts_on_or_after(r.get("placed_at"), day_start):
                    locked_open_today += lk
            if st == "pending" and is_reconciling(r):
                reconciling_liab += float(r.get("liability") or 0.0)
            open_n += 1
            traded += 1
            live_events.add(str(r.get("event_id")))
            if _ts_on_or_after(r.get("placed_at"), day_start):
                traded_today += 1
                legs_today += 1
                events_today.add(str(r.get("event_id")))
            events_all.add(str(r.get("event_id")))
    return {
        "realized_profit": round(realized, 2),
        "open_liability": round(open_liab, 2),
        # P&L già BLOCCATO sulle posizioni vive a copertura completa: non è più
        # rischio (open_liability non lo conta) ma non è ancora realizzato (H-06)
        "locked_pnl_open": round(locked_open, 2),
        # quota del bloccato attribuita alla GIORNATA (posizioni piazzate oggi):
        # è la parte che deve pesare su stop-loss e target dinamico (review H1)
        "locked_pnl_open_today": round(locked_open_today if day_start else locked_open, 2),
        # liability di un ordine a esito IGNOTO in riconciliazione (H-02): è già
        # dentro open_liability, esposta a parte perché la UI la dica al trader
        "reconciling_liability": round(reconciling_liab, 2),
        "matches_traded": traded,
        "matches_open": open_n,
        "settled_count": settled,
        "total_count": len(rows),
        "realized_today": round(realized_today if day_start else realized, 2),
        "matches_traded_today": traded_today if day_start else traded,
        # §16: partite DISTINTE (il cap max_events è per partita, non per gamba)
        "events_traded": len(events_all),
        "events_today": len(events_today) if day_start else len(events_all),
        # H-08: la giornata la dicono SOLO questi campi (mai il client).
        # review L3/L4: senza ``day_start`` i campi _today cadono sul CUMULATO
        # (come realized_today/matches_traded_today) e matches_won/matches_lost
        # ci sono sempre — il fallback senza RPC espone le STESSE chiavi.
        "legs_today": legs_today if day_start else traded,
        "won_today": won_today if day_start else won_all,
        "lost_today": lost_today if day_start else lost_all,
        "matches_won": won_all,
        "matches_lost": lost_all,
        "live_now": len(live_events),
    }


def hedge_complete(r: dict) -> bool:
    """La posizione è coperta del TUTTO (P&L identico su ogni esito)? È lo stesso
    criterio di ``safe_strategy.execution.hedge_state``: ``meta.locked_pnl`` è
    scritto (non None) SOLO a copertura completa; il residuo nullo è la conferma."""
    meta = r.get("meta") or {}
    if meta.get("locked_pnl") is None:
        return False
    res = meta.get("residual_size")
    try:
        return res is None or float(res) <= 0.01
    except (TypeError, ValueError):
        return False


def locked_open_pnl(r: dict) -> Optional[float]:
    """P&L GIÀ BLOCCATO di una posizione ancora non regolata (copertura completa),
    None se la posizione è nuda o coperta solo in parte. Non è realizzato (si
    incassa al settlement) ma non è più a rischio: va mostrato a parte, mai
    sommato alla 'liability aperta' (AUDIT 11/09 H-06)."""
    if not hedge_complete(r):
        return None
    try:
        return round(float((r.get("meta") or {})["locked_pnl"]), 2)
    except (TypeError, ValueError, KeyError):
        return None


def realized_effective(aggregates: dict) -> float:
    """R della giornata ai fini delle GUARDIE (stop-loss giornaliero, target
    dinamico, stop sull'obiettivo): realizzato di oggi PIÙ le perdite già
    BLOCCATE dalle coperture complete ancora non regolate (review H1).

    Money-critical: con ``residual_liability``=0 a copertura completa (H-06) una
    giornata con dieci green-up chiusi a −22 € mostrava R=0 e il bot continuava
    a entrare — 220 € persi e nessuna guardia che se ne accorgeva. Il bloccato
    POSITIVO invece NON si somma: il profitto si conta quando è incassato (mai
    anticipare un utile, sempre anticipare una perdita).
    """
    r = float(aggregates.get("realized_today",
                             aggregates.get("realized_profit", 0.0)) or 0.0)
    lk = aggregates.get("locked_pnl_open_today", aggregates.get("locked_pnl_open"))
    try:
        lk_f = float(lk or 0.0)
    except (TypeError, ValueError):
        lk_f = 0.0
    return round(r + min(0.0, lk_f), 2)


def open_liability_effective(aggregates: dict) -> float:
    """Capitale IMPEGNATO ai fini del cap ``max_open_liability``: liability viva
    più le perdite già bloccate non ancora incassate (review H1 — senza queste
    il cap si liberava a ogni green-up in perdita e il bot si riesponeva subito
    coi soldi che aveva appena perso)."""
    ol = float(aggregates.get("open_liability", 0.0) or 0.0)
    try:
        lk = float(aggregates.get("locked_pnl_open") or 0.0)
    except (TypeError, ValueError):
        lk = 0.0
    return round(ol + max(0.0, -lk), 2)


def residual_liability(r: dict) -> float:
    """Rischio ancora VIVO di una posizione: la liability piena se nuda; per una
    posizione coperta (anche in parte) il residuo `max(0, −if_win)` scritto
    dallo strato di esecuzione (review MED-5: un trade chiuso a −22 contava
    ancora 116 € di rischio).

    AUDIT 11/09 (H-06): a copertura COMPLETA il rischio è ZERO anche quando il
    P&L bloccato è negativo — una perdita bloccata è già fatta, non può più
    peggiorare. Prima una posizione greenata a −22 € contava 22 € di
    "liability aperta" (doppio conteggio del danno, cap di esposizione falsato).
    """
    meta = r.get("meta") or {}
    if hedge_complete(r):
        return 0.0
    if meta.get("hedged_size") is not None and meta.get("if_win") is not None:
        try:
            return round(max(0.0, -float(meta["if_win"])), 2)
        except (TypeError, ValueError):
            pass
    return float(r.get("liability") or 0.0)


def is_reconciling(r: dict) -> bool:
    """'pending' il cui ordine REALE potrebbe essere vivo (eccezione dopo
    l'accettazione Betfair): ``meta.reconciling`` / ``meta.reason``. È denaro a
    rischio finché la riconciliazione non decide (AUDIT 11/09 H-02)."""
    meta = r.get("meta") or {}
    return bool(meta.get("reconciling")) or \
        str(meta.get("reason") or "") == "place_exception_reconciling"


def is_placed(r: dict) -> bool:
    """La riga corrisponde a un ordine che ESISTE (o può esistere) sul mercato:
    bet_id reale, marker della coda flumine, o riconciliazione in corso."""
    return bool(r.get("bet_id") or (r.get("meta") or {}).get("flumine_client_ref")
                or is_reconciling(r))


# ---------------------------------------------------------------------------
# Riconciliazione dei trade 'pending' con lo stato reale Betfair (I3) — PURA
# ---------------------------------------------------------------------------
def _order_matches(o: dict, ref: Optional[str], market_id, selection_id, side: str) -> bool:
    """Un ordine Betfair (normalizzato) corrisponde al trade pending?

    Se l'ordine DICHIARA un customerOrderRef, è un match SOLO se coincide con
    ``omega-<event_id>`` (mai un fallback ambiguo che confonderebbe due trade
    diversi sullo stesso mercato/selezione). Solo se l'ordine NON ha ref si
    ricade su market_id + selection_id (+ side).
    """
    o_ref = o.get("customer_order_ref")
    if o_ref:
        refs = list(ref) if isinstance(ref, (list, tuple, set)) else ([ref] if ref else [])
        return o_ref in refs
    if o.get("market_id") != market_id or o.get("selection_id") != selection_id:
        return False
    o_side = o.get("side")
    return (not o_side) or (o_side == side)


def customer_ref_for(trade_id: Any) -> str:
    """customerOrderRef PER GAMBA (§16): ``omega-t<trade_id>`` — lo stesso della
    coda flumine e delle chiusure, unico per riga. Con due gambe per partita
    il vecchio ref per-evento faceva rifiutare il secondo ordine e confondeva
    la riconciliazione (review C1)."""
    return f"omega-t{int(trade_id)}"[:32]


def candidate_customer_refs(trade: dict) -> list[str]:
    """Ref con cui un pending può essere riconosciuto su Betfair, in ordine:
    per-gamba (nuovo, ``omega-t<id>``), poi i ref STORICI (``omega-m<id>``
    manuale, ``omega-<event_id>`` auto) — MAI per le gambe di chiusura, che
    altrimenti verrebbero confermate con l'ordine dell'APERTURA (review CRIT-1)."""
    refs: list[str] = []
    if trade.get("id") is not None:
        refs.append(customer_ref_for(trade["id"]))
    if trade.get("closes_trade_id") is not None:
        return refs
    if str(trade.get("origin") or "auto") == "manual" and trade.get("id") is not None:
        refs.append(f"omega-m{trade['id']}"[:32])
    else:
        refs.append(f"omega-{trade.get('event_id')}"[:32])
    return refs


def expected_customer_ref(trade: dict) -> str:
    """Ref principale atteso (compatibilità): il primo dei candidati."""
    return candidate_customer_refs(trade)[0]


# GRACE PERIOD: sotto questa età un pending non trovato su Betfair NON viene
# liberato (potrebbe essere un ordine reale non ancora propagato via API). Deve
# essere >> di qualunque latenza di propagazione Betfair (sub-secondo tipico).
RECON_GRACE_S = 120


def _age_seconds(iso: Optional[str], now_iso: str) -> Optional[float]:
    """Età in secondi di ``iso`` rispetto a ``now_iso`` (None se non parsabile)."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        n = datetime.fromisoformat(str(now_iso).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return (n - t).total_seconds()


def reconcile_decision(
    trade: dict, current_orders: list[dict], cleared_orders: list[dict], now_iso: str,
) -> dict:
    """Decide cosa fare di un trade 'pending' LIVE dato lo stato reale Betfair. PURA.

    - trovato tra gli ordini CORRENTI e matchato → 'confirm' (apri con fill reale)
    - trovato corrente ma NON ancora matchato → 'keep' (aspetta il prossimo ciclo)
    - trovato tra i REGOLATI → 'confirm' (poi settle_open lo chiude sul mercato)
    - non trovato da nessuna parte e recente (<24h) → 'free' (mai piazzato → libera)
    - non trovato e vecchio → 'error' (non rischiare: mai un doppio ordine)
    """
    ref = candidate_customer_refs(trade)
    mid = trade.get("market_id")
    sid = trade.get("selection_id")
    sid = int(sid) if sid is not None else None
    side = str(trade.get("side", "lay")).lower()
    if trade.get("closes_trade_id") is not None:
        # una gamba di CHIUSURA condivide mercato+selezione con l'apertura: mai il
        # fallback senza ref (confermerebbe la chiusura con l'ordine del lay)
        mid, sid = None, None

    for o in current_orders:
        if _order_matches(o, ref, mid, sid, side):
            matched = float(o.get("size_matched") or 0.0)
            remaining = float(o.get("size_remaining") or 0.0)
            # conferma SOLO a fill COMPLETO: un ordine ancora parzialmente in
            # esecuzione (remaining>0) verrebbe congelato con size sbagliata →
            # esposizione/cap errati. Finché non è completo → 'keep' (aspetta).
            if matched > 0 and remaining <= 0:
                return {"action": "confirm",
                        "price": float(o.get("avg_price_matched") or trade.get("price") or 0.0),
                        "size": matched, "bet_id": o.get("bet_id")}
            return {"action": "keep"}
    for o in cleared_orders:
        if _order_matches(o, ref, mid, sid, side):
            settled = float(o.get("size_settled") or 0.0)
            if settled <= 0:
                # F6: ordine chiuso SENZA size (lapsed/cancellato/void): nessuna
                # esposizione — mai confermare con la size della riserva
                return {"action": "free"}
            return {"action": "confirm",
                    "price": float(o.get("price") or trade.get("price") or 0.0),
                    "size": settled,
                    "bet_id": o.get("bet_id")}
    # non trovato in nessuna lista: decidi con GRACE PERIOD (mai 'free' su un ordine
    # appena piazzato ma non ancora visibile via API → eviterebbe un doppio).
    age = _age_seconds(trade.get("placed_at"), now_iso)
    if age is None or age > 24 * 3600:
        return {"action": "error"}   # non parsabile o vecchio → non rischiare un doppio
    if age < RECON_GRACE_S:
        return {"action": "keep"}    # troppo fresco: aspetta un ciclo (propagazione Betfair)
    return {"action": "free"}        # abbastanza vecchio e non trovato → mai piazzato


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
# MISSIONI (centro di controllo per partita) — funzioni PURE
# ---------------------------------------------------------------------------
# 'secondhalfend' DEVE stare qui: contiene 'secondhalf' e il check FINISHED
# corre prima del check 2T (ordine dei check = precedenza). abandoned/postponed/
# cancelled → 'finita': niente da tradare oggi, la missione si chiude e i trade
# si regolano al settlement (void) del mercato.
_PHASE_FINISHED = ("finished", "matchended", "fulltime", "ended",
                   "secondhalfend", "abandoned", "postponed", "cancelled")
# stati che chiudono la partita SENZA un risultato valido (mercato VOID): la
# missione si chiude ('finita') ma nessun risultato reale va dedotto (review MED-8)
_PHASE_VOID = ("abandoned", "postponed", "cancelled", "interrupted", "suspended")
# supplementari/rigori PRIMA dell'intervallo: "ExtraTimeHalfTime" contiene
# anche "halftime" e senza precedenza verrebbe classificato 'ht' (review 15/07)
_PHASE_ET = ("extratime", "penalt")
_PHASE_HT = ("halftime", "firsthalfend")
_PHASE_2T = ("secondhalf",)
_PHASE_1T = ("firsthalf", "kickoff")


def mission_phase(
    *,
    status: Optional[str],
    minute: Optional[int],
    kickoff: Optional[datetime],
    now: datetime,
    prev: str = "pre",
) -> str:
    """Fase della partita: 'pre'|'1t'|'ht'|'2t'|'finita'. PURA e difensiva.

    Priorità: status del provider (FirstHalf/HalfTime/SecondHalf/Finished, con
    matching per SOTTOSTRINGA normalizzata: 'FirstHalfEnd' deve battere
    'FirstHalf' → l'ordine dei check conta). Fallback: minuto; poi kickoff
    (futuro → pre; passato da >3h senza dati → finita); altrimenti la fase
    precedente (mai retrocedere a caso su un buco dati).
    """
    s = re.sub(r"[^a-z]", "", str(status or "").lower())
    if s:
        if any(k in s for k in _PHASE_FINISHED):
            return "finita"
        if any(k in s for k in _PHASE_ET):
            return "2t"
        if any(k in s for k in _PHASE_HT):
            return "ht"
        if any(k in s for k in _PHASE_2T):
            return "2t"
        if any(k in s for k in _PHASE_1T):
            return "1t"
    if minute is not None:
        return "1t" if int(minute) <= 45 else "2t"
    if kickoff is not None:
        k = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
        n = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        if n < k:
            return "pre"
        if (n - k).total_seconds() > 3 * 3600:
            return "finita"
    return prev if prev in ("pre", "1t", "ht", "2t", "finita") else "pre"


def scalp_market_types(total_goals: int) -> list[str]:
    """Tipi mercato Over/Under per lo scalp back-Under: linea = gol attuali + 2.5
    (es. 1-0 → Under 3.5 → 'OVER_UNDER_35'), con fallback alla linea sopra.
    Verificati LIVE su Betfair: 'OVER_UNDER_15'..'OVER_UNDER_85'."""
    g = max(int(total_goals), 0)
    out = []
    for line in (g + 2, g + 3):
        if line <= 8:
            out.append(f"OVER_UNDER_{line}5")
    return out


def pick_under_runner(runners: list) -> Optional[object]:
    """Il runner 'Under X.5 Goals' scelto PER NOME (mai per posizione: se
    l'ordine dei runner cambiasse, un match posizionale punterebbe l'Over —
    utenti che perdono soldi). Ritorna il runner o None."""
    for r in runners:
        name = str(getattr(r, "name", "") or "").strip().lower()
        if name.startswith("under"):
            return r
    return None


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


# ---------------------------------------------------------------------------
# OMEGA v2 — DUE GAMBE PER PARTITA (§14, 11/09): gambe residue e target
# ---------------------------------------------------------------------------
LEG_PHASES: tuple[str, ...] = ("ht_cs", "ft_cs")
HT_BREAK_MIN = 15     # intervallo: l'orologio dal kickoff corre anche durante la pausa


def legs_remaining(
    events: list,
    traded_legs: "set[tuple[str, str]]",
    *,
    now: datetime,
    ht_entry_max: int,
    ft_entry_max: int,
    max_events: int = 0,
    traded_count: int = 0,
    excluded_ids: "set[str] | frozenset[str] | None" = None,
    minute_of: Optional[Callable[[str], Optional[int]]] = None,
) -> tuple[int, int]:
    """(gambe ancora piazzabili, partite con almeno una gamba piazzabile).

    Per OGNI partita del giorno Omega piazza DUE gambe (1T sul Half Time Score,
    2T sul Correct Score): una gamba resta piazzabile finché la sua finestra
    (minuto dall'orologio del kickoff, largo) non è passata e non è già stata
    riservata/piazzata. Il target di gamba è (G − R) / gambe residue: così
    l'obiettivo si spalma su tutte le operazioni che restano nella giornata
    (non solo sulle partite intere) e una partita "presa in corsa" nel 2T pesa
    per la sola gamba che può ancora fare. Con ``max_events`` > 0 le partite
    residue sono cappate a quelle ancora ammesse. Mai sotto (1, 1).
    """
    excluded = set(excluded_ids or ())
    # partite NON ancora toccate (soggette al cap max_events) e partite già in
    # posizione con una gamba ancora da fare (hanno già consumato il cap: la
    # loro seconda gamba si fa SEMPRE — review 11/09 HIGH-2)
    new_legs = new_matches = 0
    pending_legs = pending_matches = 0
    for ev in events:
        eid = str(getattr(ev, "event_id", ""))
        if not eid or eid in excluded:
            continue
        # minuto REALE dal feed quando c'è (review HIGH-1: l'orologio include
        # l'intervallo → a 66′ reali diceva 81′ → 1 sola gamba → target ×10);
        # fallback orologio corretto dell'intervallo (prudente: sovrastima le gambe)
        minute = minute_of(eid) if minute_of is not None else None
        if minute is None:
            open_date = getattr(ev, "open_date", None)
            clock = minute_from_clock(open_date, now) if open_date is not None else 0
            minute = clock if clock <= 45 else max(45, clock - HT_BREAK_MIN)
        ht_done = (eid, "ht_cs") in traded_legs
        ft_done = (eid, "ft_cs") in traded_legs
        n = 0
        if not ht_done and minute <= int(ht_entry_max):
            n += 1
        if not ft_done and minute <= int(ft_entry_max):
            n += 1
        if not n:
            continue
        if ht_done or ft_done:
            pending_legs += n
            pending_matches += 1
        else:
            new_legs += n
            new_matches += 1
    if max_events and int(max_events) > 0:
        allowed = max(int(max_events) - int(traded_count), 0)
        if new_matches > allowed:
            new_legs = min(new_legs, 2 * allowed)
            new_matches = allowed
    legs = pending_legs + new_legs
    matches = pending_matches + new_matches
    # nessun floor silenzioso (review HIGH-1): 0 gambe = niente da piazzare, non
    # "tutto l'obiettivo su questa gamba"
    return max(legs, 0), max(matches, 0)


# ---------------------------------------------------------------------------
# RISULTATI REALI di fine 1T / fine 2T (§14): dal feed IPS e dal settlement
# ---------------------------------------------------------------------------
def _score_str(h: object, a: object) -> Optional[str]:
    """'H-A' da due valori numerici (anche stringhe '2'); None se uno manca/è vuoto."""
    try:
        if h is None or a is None or str(h).strip() == "" or str(a).strip() == "":
            return None
        return f"{int(str(h).strip())}-{int(str(a).strip())}"
    except (TypeError, ValueError):
        return None


def results_from_payload(payload: Optional[dict], *, now: Optional[datetime] = None) -> tuple[Optional[str], Optional[str]]:
    """(risultato al 45′, risultato finale) dal payload del feed unico. PURA.

    Fonti, in ordine: il blocco IPS grezzo ``score_raw.score.{home,away}``
    (``halfTimeScore`` / ``fullTimeScore`` — vuoti finché il tempo non è finito);
    poi la FASE della partita: all'intervallo il punteggio corrente È il
    risultato del 1T, a partita finita è il finale. Mai un risultato dedotto
    a partita in corso: None finché non è certo.
    """
    if not isinstance(payload, dict):
        return None, None
    ht = ft = None
    raw = payload.get("score_raw")
    score = raw.get("score") if isinstance(raw, dict) else None
    if isinstance(score, dict):
        home = score.get("home") if isinstance(score.get("home"), dict) else {}
        away = score.get("away") if isinstance(score.get("away"), dict) else {}
        ht = _score_str(home.get("halfTimeScore"), away.get("halfTimeScore"))
        ft = _score_str(home.get("fullTimeScore"), away.get("fullTimeScore"))
    status = raw.get("matchStatus") if isinstance(raw, dict) else None
    current = _score_str(payload.get("score_home"), payload.get("score_away"))
    if current is not None and status:
        norm = re.sub(r"[^a-z]", "", str(status).lower())
        phase = mission_phase(status=str(status), minute=None, kickoff=None,
                              now=now or datetime.now(timezone.utc), prev="pre")
        if phase == "ht" and ht is None:
            ht = current
        # a partita finita il corrente È il finale SOLO senza supplementari/rigori
        # (il Correct Score si regola sui 90′) e MAI per sospesa/rinviata/annullata
        if phase == "finita" and ft is None and not any(k in norm for k in _PHASE_ET) \
                and not any(k in norm for k in _PHASE_VOID):
            ft = current
    return ht, ft


def scoreline_names(runners: list) -> dict[str, str]:
    """{selection_id: 'H - A'} dei soli runner a punteggio esatto (per il
    settlement: dal WINNER si ricava il risultato reale del mercato)."""
    out: dict[str, str] = {}
    for r in runners or []:
        name = str(getattr(r, "name", "") or "")
        if is_scoreline(name):
            out[str(getattr(r, "selection_id"))] = name
    return out


def winner_scoreline(meta: Optional[dict], winner_selection_id: Optional[int]) -> Optional[str]:
    """'H-A' del runner vincitore dal dizionario ``meta.runners`` salvato al
    piazzamento; None se ignoto o non a punteggio esatto."""
    if winner_selection_id is None or not isinstance(meta, dict):
        return None
    names = meta.get("runners")
    if not isinstance(names, dict):
        return None
    parsed = parse_scoreline(str(names.get(str(int(winner_selection_id))) or ""))
    return None if parsed is None else f"{parsed[0]}-{parsed[1]}"


def result_key_for_trade(trade: dict) -> Optional[str]:
    """Chiave di ``meta`` su cui scrivere il risultato del mercato regolato:
    'result_ht' per la gamba Half Time Score, 'result_ft' per il Correct Score
    (gamba 2T, motore v1 senza gamba, manuale CS). None per gli altri mercati."""
    phase = trade.get("phase")
    if phase == "ht_cs":
        return "result_ht"
    if phase in ("ft_cs", None):
        return "result_ft"
    return None
