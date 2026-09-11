"""engine — logica PURA del bot Mike (COSTITUZIONE_MIKE.md §2).

Zero I/O: nessun DB, nessuna rete, nessun flumine (solo la ladder ufficiale
per i tick). Tutto cio' che decide il bot passa da ``decide(ctx, snap, params)``:
riceve lo stato della partita (``MatchCtx``), una fotografia del mercato e del
feed (``Snapshot``) e i parametri risolti; restituisce una ``Decision`` con le
azioni (place/cancel) e il nuovo stato. E' il chiamante (strategy.py) a
tradurre le azioni in ordini flumine e a riportare i fill sulle ``Leg``.

Convenzioni money-critical:
  - esposizioni SOLO dai fill (``Leg.matched`` / ``Leg.avg_price``), mai dalla size chiesta;
  - green-up / cash-out con ``compute_greenup`` (stessa aritmetica del ladder);
  - commissione applicata per MERCATO sul netto positivo (come execution.settle_group);
  - nessun numero inventato: prezzo mancante -> nessuna azione, ``complete=False``.

Mercati: ``OU35`` (Under 3.5 = selezione UNDER) e ``OU45`` (Over 4.5 = OVER,
Under 4.5 = UNDER per il re-ingresso). Esiti per gol totali T:
  Under 3.5 vince se T <= 3; Over 4.5 vince se T >= 5; Under 4.5 vince se T <= 4.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from Betfair.stream.live_order_build import round_to_tick, ticks_away
from Betfair.stream.scalper.scalper_bot import ticks_between
from Betfair.stream.trading.greenup import GreenupPlan, compute_greenup

MARKET_OU35 = "OU35"
MARKET_OU45 = "OU45"
SEL_UNDER = "UNDER"
SEL_OVER = "OVER"

LINE = {MARKET_OU35: 3.5, MARKET_OU45: 4.5}

STATES = (
    "WATCH", "PRE_ENTRY_PENDING", "PRE_OPEN", "PRE_GREEN_PENDING", "HOLD",
    "PRE_LAST_ENTRY_PENDING", "IDLE_LIVE", "LIVE_UNCOVERED", "LIVE_COVER_PENDING",
    "LIVE_COVERED", "LIVE_CLOSING", "FLAT", "REENTRY_PENDING", "REENTRY_OPEN",
    "REENTRY_GREEN_PENDING", "SETTLING", "SETTLED", "ERROR", "SKIPPED",
)
TERMINAL_STATES = ("SETTLED", "ERROR", "SKIPPED")

ROLES = (
    "under_entry", "under_green", "under_last", "over_cover", "under_close",
    "over_close", "reentry", "reentry_green", "manual_close",
)
OPENING_ROLES = ("under_entry", "under_last", "over_cover", "reentry")

IT_BACK_MIN = 2.0
IT_BACK_STEP = 0.5
_EPS = 1e-9
_FLAT_EPS = 0.01


# ---------------------------------------------------------------------------
# Dati
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Book:
    """Best price/size di UNA selezione (livello 0 del ladder) + stato mercato."""

    best_back: Optional[float]
    back_size: float = 0.0
    best_lay: Optional[float] = None
    lay_size: float = 0.0
    status: str = "OPEN"
    inplay: bool = False
    bet_delay: int = 0


@dataclass
class Leg:
    """Un ordine del bot (pending) o una posizione (matched > 0).

    CONTRATTO con il chiamante (service/strategy), money-critical:
      - ``status='pending'`` finche' l'ordine e' VIVO sull'exchange, anche se
        parzialmente abbinato (``matched`` cresce, ``remaining`` > 0): cosi' i
        percorsi di cancellazione (``is_live``) lo vedono sempre;
      - ``status='open'`` SOLO quando non e' piu' vivo: abbinato per intero
        oppure residuo cancellato con ``matched`` > 0;
      - ``status='cancelled'`` = mai abbinato e ritirato; ``'settled'`` a fine mercato;
      - ``archived=True`` = gamba di un ciclo pre-match gia' CHIUSO in green: resta
        per la contabilita' (settle) ma NON conta piu' come capitale a rischio
        (``position``/``invested``/``exposure``).
    """

    role: str
    market: str
    selection: str
    side: str                       # 'back' | 'lay'
    price: float
    size: float
    matched: float = 0.0
    avg_price: Optional[float] = None
    ref: str = ""
    status: str = "pending"          # pending | open | cancelled | settled
    placed_at: float = 0.0
    persistence: str = "LAPSE"
    cycle_no: int = 0
    final: bool = False
    archived: bool = False

    @property
    def remaining(self) -> float:
        return max(0.0, float(self.size) - float(self.matched))

    @property
    def is_live(self) -> bool:
        return self.status == "pending"

    @property
    def filled(self) -> bool:
        return float(self.matched) >= float(self.size) - 0.005 or (
            self.status == "open" and float(self.matched) > 0.0
        )

    @property
    def fill_price(self) -> float:
        return float(self.avg_price if self.avg_price else self.price)


@dataclass(frozen=True)
class Snapshot:
    """Fotografia di mercato + feed al momento della decisione."""

    now: float
    ko_at: float
    books: Dict[Tuple[str, str], Book]
    inplay: bool = False
    minute: Optional[int] = None
    goals: Optional[int] = None
    ht_active: bool = False
    feed_fresh: bool = True
    hazard: Optional[float] = None
    p4_market: Optional[float] = None
    p4_model: Optional[float] = None
    last_goal_ts: Optional[float] = None
    market_status: str = "OPEN"
    final_total: Optional[int] = None
    # risparmio atteso (%) sulla copertura se si aspetta cover_wait_step_min senza gol
    cover_gain_pct: Optional[float] = None
    # pressione (corner/cartellini dal feed): moltiplicatore >= 1.0, 1.0 = neutra
    pressure: float = 1.0
    # probabilita' di MODELLO per le selezioni (u35/o45/u45) in tre scenari:
    # "_now" (adesso), "_goal" (subito dopo un gol), "_later" (fra cover_wait_step_min
    # minuti senza gol). Servono al cash-out intelligente (valore atteso dell'attesa).
    model_probs: Optional[Dict[str, float]] = None
    # distribuzione dei GOL TOTALI a fine gara {0..8, 8 = 8+}: dal modello (griglia
    # residua Omega) e dalla tabella empirica HT->FT (solo finche' il punteggio e'
    # quello dell'intervallo). Servono all'uscita in perdita "a modello".
    p_total_model: Optional[Dict[int, float]] = None
    p_total_emp: Optional[Dict[int, float]] = None

    def book(self, market: str, selection: str) -> Optional[Book]:
        return self.books.get((market, selection))


@dataclass
class MatchCtx:
    state: str = "WATCH"
    legs: List[Leg] = field(default_factory=list)
    cycle_no: int = 0
    entry_price_initial: Optional[float] = None
    last_green_at: Optional[float] = None
    last_action_at: Optional[float] = None
    attempts: int = 0
    reentry_allowed: bool = False
    reentry_done: bool = False
    close_reason: Optional[str] = None
    cover_skipped: bool = False
    seq: int = 0
    settled_pnl: Optional[float] = None


@dataclass(frozen=True)
class Action:
    kind: str                       # 'place' | 'cancel'
    role: Optional[str] = None
    market: Optional[str] = None
    selection: Optional[str] = None
    side: Optional[str] = None
    price: Optional[float] = None
    size: Optional[float] = None
    persistence: str = "LAPSE"
    ref: Optional[str] = None        # cancel: ref della gamba
    final: bool = False
    note: str = ""


@dataclass
class Decision:
    state: str
    actions: List[Action] = field(default_factory=list)
    reason: str = ""
    updates: Dict[str, Any] = field(default_factory=dict)
    telemetry: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CashoutValue:
    net: float
    gross: float
    per_selection: Dict[Tuple[str, str], float]
    plans: Dict[Tuple[str, str], GreenupPlan]
    complete: bool


@dataclass(frozen=True)
class SettleResult:
    per_leg: List[Tuple[str, str, float]]     # (ref, status, pnl lordo)
    per_market: Dict[str, float]               # netto per mercato (commissione applicata)
    net: float


# ---------------------------------------------------------------------------
# Matematica pura
# ---------------------------------------------------------------------------
def green_target(entry_price: float, ticks: int) -> float:
    """Prezzo di chiusura a ``ticks`` tick SOTTO il prezzo d'ingresso (back)."""
    return float(ticks_away(float(entry_price), -int(ticks)))


def locked_pnl_back(stake: float, entry_price: float, close_price: float) -> float:
    """P&L lordo bloccato su entrambi gli esiti chiudendo un back S@Pe con lay a p."""
    return float(stake) * (float(entry_price) / float(close_price) - 1.0)


def cover_size(stake_under: float, price_over: float, commission: float, factor: float) -> float:
    """Stake sull'Over 4.5 tale che, se vince, il netto sia (factor-1)*stake_under."""
    if price_over is None or price_over <= 1.0:
        raise ValueError(f"price_over non valido: {price_over!r}")
    return float(factor) * float(stake_under) / ((float(price_over) - 1.0) * (1.0 - float(commission)))


def cover_size_residual(stake_under: float, price_over: float, commission: float, factor: float, *,
                        matched: float, matched_price: float) -> float:
    """Stake RESIDUO sull'Over 4.5 dopo un fill parziale ``matched`` @ ``matched_price``:
    la parte abbinata rende gia' m·(p_old−1)·(1−c); il resto porta il netto a (factor-1)·S."""
    if price_over is None or price_over <= 1.0:
        raise ValueError(f"price_over non valido: {price_over!r}")
    target = float(factor) * float(stake_under)
    already = float(matched) * (float(matched_price) - 1.0) * (1.0 - float(commission))
    residual = (target - already) / ((float(price_over) - 1.0) * (1.0 - float(commission)))
    return max(0.0, residual)


def legalize_back_size(size: float, rounding: str = "ceil",
                       min_stake: float = IT_BACK_MIN, step: float = IT_BACK_STEP) -> Tuple[float, float]:
    """Size BACK legale .it (min 2.00, passo 0.50) + overshoot % rispetto alla size chiesta."""
    x = float(size)
    if x <= 0 or not math.isfinite(x):
        return (0.0, 0.0)
    n = x / step
    if rounding == "floor":
        k = math.floor(n + _EPS)
    elif rounding == "nearest":
        k = math.floor(n + 0.5)
    else:
        k = math.ceil(n - _EPS)
    legal = max(min_stake, round(k * step, 2))
    overshoot = (legal / x - 1.0) * 100.0
    return (legal, round(overshoot, 4))


def cover_legal_size(x: float, params: Dict[str, Any]) -> Tuple[float, float]:
    """Size effettiva della copertura: ESATTA al centesimo (exact_sizes, default) oppure
    legalizzata .it (min 2.00 / passo 0.50) come ripiego. Ritorna (size, overshoot %)."""
    if params.get("exact_sizes", True):
        return (round(float(x), 2), 0.0)
    return legalize_back_size(x, str(params.get("cover_rounding", "ceil")))


def needs_submin(side: str, size: float, min_stake: float = IT_BACK_MIN, step: float = IT_BACK_STEP) -> bool:
    """True se un ordine BACK di apertura con questa size richiede il place-and-trim (.it)."""
    if side != "back":
        return False
    s = round(float(size), 2)
    if s < min_stake - _EPS:
        return True
    return abs(round(s / step) * step - s) > 0.005


def selection_wins(market: str, selection: str, total_goals: int) -> bool:
    line = LINE[market]
    if selection == SEL_UNDER:
        return total_goals < line
    return total_goals > line


def exposure(legs: List[Leg], market: str, selection: str) -> Tuple[float, float]:
    """(W, L) = profit se la selezione vince / perde, dai soli fill."""
    w = l = 0.0
    for leg in legs:
        if leg.market != market or leg.selection != selection or leg.matched <= 0:
            continue
        if leg.archived:
            continue  # ciclo pre-match gia' chiuso in green: non e' capitale a rischio
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            w += s * (p - 1.0)
            l -= s
        else:
            w -= s * (p - 1.0)
            l += s
    return (round(w, 4), round(l, 4))


def open_selections(legs: List[Leg]) -> List[Tuple[str, str]]:
    """Selezioni con esposizione non piatta (ordine deterministico)."""
    out = []
    for key in ((MARKET_OU35, SEL_UNDER), (MARKET_OU45, SEL_OVER), (MARKET_OU45, SEL_UNDER)):
        w, l = exposure(legs, *key)
        if abs(w - l) >= _FLAT_EPS:
            out.append(key)
    return out


def position(legs: List[Leg], market: str, selection: str, roles: Tuple[str, ...]) -> Tuple[float, Optional[float]]:
    """(stake abbinato, prezzo medio) dei back di apertura su una selezione."""
    tot = 0.0
    wsum = 0.0
    for leg in legs:
        if leg.market != market or leg.selection != selection or leg.role not in roles:
            continue
        if leg.side != "back" or leg.matched <= 0 or leg.archived:
            continue
        tot += float(leg.matched)
        wsum += float(leg.matched) * leg.fill_price
    if tot <= 0:
        return (0.0, None)
    return (round(tot, 2), round(wsum / tot, 4))


def invested(legs: List[Leg]) -> float:
    """Capitale investito nei back di apertura ancora abbinati (base del cash-out)."""
    return round(sum(float(l.matched) for l in legs
                     if l.side == "back" and l.role in OPENING_ROLES and l.matched > 0
                     and not l.archived), 2)


def _market_pnl_by_total(legs: List[Leg], market: str, total: int) -> float:
    pnl = 0.0
    for leg in legs:
        if leg.market != market or leg.matched <= 0:
            continue
        win = selection_wins(market, leg.selection, total)
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            pnl += s * (p - 1.0) if win else -s
        else:
            pnl += -s * (p - 1.0) if win else s
    return pnl


def _net(value: float, commission: float) -> float:
    return value * (1.0 - commission) if value > 0 else value


def net_pnl_by_total(legs: List[Leg], commission: float, max_total: int = 8) -> Dict[int, float]:
    """P&L NETTO complessivo per ogni somma gol 0..max_total (commissione per mercato)."""
    out: Dict[int, float] = {}
    for t in range(0, max_total + 1):
        tot = 0.0
        for market in (MARKET_OU35, MARKET_OU45):
            tot += _net(_market_pnl_by_total(legs, market, t), commission)
        out[t] = round(tot, 2)
    return out


def cashout_value(legs: List[Leg], books: Dict[Tuple[str, str], Book], commission: float,
                  place_at_ticks: int = 0) -> CashoutValue:
    """Valore di cash-out globale: somma dei P&L bloccati chiudendo OGNI selezione ora."""
    per: Dict[Tuple[str, str], float] = {}
    plans: Dict[Tuple[str, str], GreenupPlan] = {}
    complete = True
    gross = net = 0.0
    for key in open_selections(legs):
        w, l = exposure(legs, *key)
        bk = books.get(key)
        plan = compute_greenup(
            matched_if_win=w, matched_if_lose=l,
            best_back_price=bk.best_back if bk else None,
            best_lay_price=bk.best_lay if bk else None,
            fraction=1.0, place_at_ticks=int(place_at_ticks),
        )
        plans[key] = plan
        if not plan.actionable:
            complete = False
            continue
        locked = float(min(plan.expected_if_win, plan.expected_if_lose))
        per[key] = round(locked, 2)
        gross += locked
        net += _net(locked, commission)
    return CashoutValue(net=round(net, 2), gross=round(gross, 2), per_selection=per,
                        plans=plans, complete=complete)


def should_cashout(value_net: float, base: float, pct: float) -> bool:
    if base <= 0:
        return False
    return value_net >= base * float(pct) / 100.0 - _EPS


def loss_exit_ok(value_net: float, base: float, pct: float, *, goals: Optional[int],
                 gmin: int, gmax: int) -> bool:
    """Chiudi comunque se la perdita bloccabile e' entro pct% della base (o in profitto)."""
    if goals is None or base <= 0 or goals < gmin or goals > gmax:
        return False
    return value_net >= -base * float(pct) / 100.0 - _EPS


_PROB_KEY = {(MARKET_OU35, SEL_UNDER): "u35", (MARKET_OU45, SEL_OVER): "o45", (MARKET_OU45, SEL_UNDER): "u45"}
_DEAD_PRICE = 1000.0


def projected_books(books: Dict[Tuple[str, str], Book], model_probs: Optional[Dict[str, float]],
                    scenario: str) -> Optional[Dict[Tuple[str, str], Book]]:
    """Book PROIETTATI nello scenario ``goal`` | ``later``.

    La quota equa e' proporzionale a 1/P: la quota di MERCATO viene scalata per
    P_now/P_scenario, cosi' si conserva il margine reale del book. P_scenario ~ 0
    (selezione morta, es. Under 3.5 dopo il 4o gol) -> quota 1000. None se manca un dato.
    """
    if not model_probs:
        return None
    out: Dict[Tuple[str, str], Book] = {}
    for key, bk in books.items():
        k = _PROB_KEY.get(key)
        if k is None:
            continue
        p_now, p_new = model_probs.get(f"{k}_now"), model_probs.get(f"{k}_{scenario}")
        if p_now is None or p_new is None or float(p_now) <= 0:
            return None
        ratio = _DEAD_PRICE if float(p_new) <= 1e-6 else float(p_now) / float(p_new)

        def _sc(x: Optional[float]) -> Optional[float]:
            return None if x is None else max(1.01, min(_DEAD_PRICE, float(x) * ratio))

        out[key] = replace(bk, best_back=_sc(bk.best_back), best_lay=_sc(bk.best_lay))
    return out


def smart_cashout(*, cv_net: float, base: float, legs: List[Leg], books: Dict[Tuple[str, str], Book],
                  commission: float, params: Dict[str, Any], hazard: Optional[float], pressure: float,
                  goals: Optional[int], model_probs: Optional[Dict[str, float]],
                  place_at_ticks: int = 0) -> Tuple[bool, str, Dict[str, Any]]:
    """Cash-out INTELLIGENTE: chiude prima della soglia quando tenere la posizione
    non vale il rischio. Mai sotto ``cashout_smart_min_pct`` della base (profitto
    minimo garantito). Ordine dei criteri:
      1. punteggio caldo: gol >= cashout_smart_goals_hot (il prossimo gol e' il 4o);
      2. vicino alla soglia (entro cashout_smart_tolerance_pct) E fase calda
         (hazard 3' >= cashout_smart_hazard_hot O pressione >= cashout_smart_pressure_hot);
      3. valore atteso dell'attesa (modello): EV_hold = h*V_gol + (1-h)*V_dopo con
         h = P(gol entro cover_wait_step_min) dall'hazard 3'. Vicino alla soglia
         basta EV_hold < V_ora; lontano serve EV_hold < V_ora - cashout_smart_ev_margin_pct.
    Ritorna (chiudi, motivo, telemetria)."""
    tele: Dict[str, Any] = {"enabled": bool(params.get("cashout_smart_enabled", False))}
    if not tele["enabled"] or base <= 0:
        return False, "", tele
    target = base * float(params["cashout_profit_pct"]) / 100.0
    floor = base * float(params["cashout_smart_min_pct"]) / 100.0
    tol = base * float(params["cashout_smart_tolerance_pct"]) / 100.0
    near = cv_net >= target - tol - _EPS
    tele.update({"floor": round(floor, 2), "near": near, "hazard": hazard, "pressure": round(float(pressure), 3)})
    if cv_net < floor - _EPS:
        return False, "", tele
    g = int(goals or 0)
    if g >= int(params["cashout_smart_goals_hot"]):
        tele["trigger"] = "goals_hot"
        return True, f"punteggio caldo ({g} gol) sopra il profitto minimo", tele
    hot = (hazard is not None and float(hazard) >= float(params["cashout_smart_hazard_hot"])) or \
        float(pressure) >= float(params["cashout_smart_pressure_hot"])
    tele["hot"] = hot
    if near and hot:
        tele["trigger"] = "hot_near"
        return True, "fase calda (hazard/pressione) a un passo dalla soglia", tele
    if model_probs and hazard is not None:
        bg = projected_books(books, model_probs, "goal")
        bl = projected_books(books, model_probs, "later")
        if bg and bl:
            cv_goal = cashout_value(legs, bg, commission, place_at_ticks)
            cv_later = cashout_value(legs, bl, commission, place_at_ticks)
            if cv_goal.complete and cv_later.complete:
                step = max(1.0, float(params.get("cover_wait_step_min", 5)))
                h_step = 1.0 - (1.0 - min(1.0, max(0.0, float(hazard)))) ** (step / 3.0)
                ev_hold = h_step * cv_goal.net + (1.0 - h_step) * cv_later.net
                tele.update({"cv_goal": cv_goal.net, "cv_later": cv_later.net,
                             "h_step": round(h_step, 4), "ev_hold": round(ev_hold, 2)})
                margin = base * float(params["cashout_smart_ev_margin_pct"]) / 100.0
                if near and ev_hold < cv_net - _EPS:
                    tele["trigger"] = "ev_near"
                    return True, f"aspettare vale {ev_hold:.2f} < {cv_net:.2f} a un passo dalla soglia", tele
                if ev_hold < cv_net - margin - _EPS:
                    tele["trigger"] = "ev_margin"
                    return True, f"attesa a valore atteso {ev_hold:.2f} << {cv_net:.2f}", tele
    return False, "", tele


def blend_totals(*dists: Optional[Dict[int, float]]) -> Optional[Dict[int, float]]:
    """Media delle distribuzioni disponibili dei gol totali (None ignorati), normalizzata."""
    ok = [d for d in dists if d]
    if not ok:
        return None
    keys = sorted({int(k) for d in ok for k in d})
    out = {k: sum(float(d.get(k, 0.0)) for d in ok) / len(ok) for k in keys}
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot > 0 else None


def hold_expectation(pnl_by_total: Dict[int, float], p_total: Dict[int, float],
                     p4_floor: Optional[float] = None) -> Tuple[float, float]:
    """(EV a fine gara tenendo tutto, P(4) usata). Con ``p4_floor`` la P(4) viene
    alzata (mai abbassata) e il resto della distribuzione riscalato: e' la scelta
    PRUDENTE (fra modello, empirico e mercato comanda il piu' pessimista sui 4 gol)."""
    dist = {int(k): float(v) for k, v in p_total.items()}
    p4 = dist.get(4, 0.0)
    if p4_floor is not None and float(p4_floor) > p4:
        rest = 1.0 - p4
        scale = (1.0 - float(p4_floor)) / rest if rest > 0 else 0.0
        dist = {k: (float(p4_floor) if k == 4 else v * scale) for k, v in dist.items()}
        p4 = float(p4_floor)
    max_t = max(pnl_by_total) if pnl_by_total else 8
    ev = 0.0
    for t, p in dist.items():
        ev += p * float(pnl_by_total.get(min(t, max_t), 0.0))
    return round(ev, 4), round(p4, 4)


def loss_exit_model(*, cv_net: float, base: float, pnl_by_total: Dict[int, float],
                    p_total_model: Optional[Dict[int, float]], p_total_emp: Optional[Dict[int, float]],
                    p4_market: Optional[float], params: Dict[str, Any]) -> Tuple[Optional[bool], str, Dict[str, Any]]:
    """Uscita in perdita A MODELLO: confronta il valore CERTO di chiudere ora (cv_net)
    con il valore ATTESO di tenere fino alla fine (EV = sum P(tot) * P&L(tot)), meno un
    premio al rischio proporzionale alla P(4 gol): premio = risk_premium% * P(4) * base.
    Chiude se cv_net >= EV - premio. P(4) prudente = max(modello/empirico, mercato).
    Ritorna (None, ...) quando i dati mancano (il chiamante usa la regola fissa)."""
    tele: Dict[str, Any] = {"mode": "model"}
    dist = blend_totals(p_total_model, p_total_emp)
    if dist is None or base <= 0 or not pnl_by_total:
        tele["missing"] = True
        return None, "", tele
    p4_floor = None
    if params.get("loss_exit_p4_prudent", True) and p4_market is not None:
        p4_floor = float(p4_market)
    ev_hold, p4 = hold_expectation(pnl_by_total, dist, p4_floor)
    premium = base * float(params["loss_exit_risk_premium_pct"]) / 100.0 * p4
    threshold = ev_hold - premium
    tele.update({"ev_hold": round(ev_hold, 2), "p4": p4, "p4_model": (p_total_model or {}).get(4),
                 "p4_emp": (p_total_emp or {}).get(4), "p4_market": p4_market,
                 "premium": round(premium, 2), "threshold": round(threshold, 2),
                 "sources": [n for n, d in (("model", p_total_model), ("emp", p_total_emp)) if d]})
    cap = float(params.get("loss_exit_max_pct") or 0.0)
    if cap > 0 and cv_net < -base * cap / 100.0 - _EPS:
        tele["beyond_cap"] = True
        return False, f"perdita {cv_net:.2f} oltre il tetto {cap}%: si tiene", tele
    if cv_net >= threshold - _EPS:
        return True, f"chiudere ({cv_net:.2f}) vale piu' di tenere ({ev_hold:.2f} - premio {premium:.2f}, P4 {p4:.0%})", tele
    return False, f"tenere vale {ev_hold:.2f} - premio {premium:.2f} > {cv_net:.2f}", tele


def cover_timing(*, goals: Optional[int], minute: Optional[int], hazard: Optional[float],
                 p4_market: Optional[float], last_goal_ts: Optional[float], now: float,
                 params: Dict[str, Any], price_over: Optional[float] = None,
                 cover_gain_pct: Optional[float] = None) -> str:
    """'cover' | 'wait' | 'skip' per la copertura sull'Over 4.5.

    Regola "intelligente ma non lenta": si ASPETTA solo se TUTTE valgono:
      0 gol · minuto < cover_wait_max_min · hazard 3' ≤ cover_wait_hazard_max ·
      P(4) mercato ≤ cover_wait_p4_max · quota Over < cover_good_price ·
      risparmio atteso ≥ cover_wait_min_gain_pct (se stimabile).
    Ogni dato mancante = si copre (mai attesa al buio). Dopo un gol: attesa del
    solo riprezzo (cover_postgoal_delay_s), poi copertura.
    """
    g = int(goals or 0)
    if g > int(params["cover_max_goals"]):
        return "skip"
    policy = params.get("cover_policy", "auto")
    if policy == "immediate":
        return "cover"
    if g >= 1:
        if last_goal_ts is not None and now - float(last_goal_ts) < float(params["cover_postgoal_delay_s"]):
            return "wait"
        return "cover"
    if minute is None:
        return "cover"
    if int(minute) >= int(params["cover_wait_max_min"]):
        return "cover"
    if policy == "wait":
        return "wait"
    if hazard is None or p4_market is None:
        return "cover"
    if float(hazard) > float(params["cover_wait_hazard_max"]):
        return "cover"
    if float(p4_market) > float(params["cover_wait_p4_max"]):
        return "cover"
    if price_over is not None and float(price_over) >= float(params.get("cover_good_price", 7.0)):
        return "cover"          # la quota e' gia' buona: aspettare non paga il rischio
    if cover_gain_pct is not None and float(cover_gain_pct) < float(params.get("cover_wait_min_gain_pct", 8.0)):
        return "cover"          # il risparmio atteso non vale il rischio di un gol
    return "wait"


def settle_legs(legs: List[Leg], total_goals: int, commission: float) -> SettleResult:
    per_leg: List[Tuple[str, str, float]] = []
    per_market: Dict[str, float] = {}
    for leg in legs:
        if leg.matched <= 0:
            per_leg.append((leg.ref, "void", 0.0))
            continue
        win = selection_wins(leg.market, leg.selection, int(total_goals))
        s = float(leg.matched)
        p = leg.fill_price
        if leg.side == "back":
            pnl = s * (p - 1.0) if win else -s
            status = "won" if win else "lost"
        else:
            pnl = -s * (p - 1.0) if win else s
            status = "lost" if win else "won"
        per_leg.append((leg.ref, status, round(pnl, 2)))
        per_market[leg.market] = per_market.get(leg.market, 0.0) + pnl
    net = 0.0
    for m, v in list(per_market.items()):
        per_market[m] = round(_net(v, commission), 2)
        net += per_market[m]
    return SettleResult(per_leg=per_leg, per_market=per_market, net=round(net, 2))


# ---------------------------------------------------------------------------
# Helper di stato
# ---------------------------------------------------------------------------
def _legs(ctx: MatchCtx, role: Optional[str] = None, live: Optional[bool] = None) -> List[Leg]:
    out = []
    for leg in ctx.legs:
        if role is not None and leg.role != role:
            continue
        if live is True and not leg.is_live:
            continue
        if live is False and leg.is_live:
            continue
        out.append(leg)
    return out


def _last(ctx: MatchCtx, role: str) -> Optional[Leg]:
    legs = _legs(ctx, role)
    return legs[-1] if legs else None


def _cancel_live(ctx: MatchCtx, roles: Optional[Tuple[str, ...]] = None) -> List[Action]:
    return [Action(kind="cancel", ref=l.ref, role=l.role, market=l.market, selection=l.selection)
            for l in ctx.legs if l.is_live and (roles is None or l.role in roles)]


def _place(role: str, market: str, selection: str, side: str, price: float, size: float,
           persistence: str = "LAPSE", final: bool = False, note: str = "") -> Action:
    return Action(kind="place", role=role, market=market, selection=selection, side=side,
                  price=float(round_to_tick(price)), size=round(float(size), 2),
                  persistence=persistence, final=final, note=note)


def _under_position(ctx: MatchCtx) -> Tuple[float, Optional[float]]:
    return position(ctx.legs, MARKET_OU35, SEL_UNDER, ("under_entry", "under_last"))


def _cashout_base(ctx: MatchCtx, params: Dict[str, Any]) -> float:
    if params.get("cashout_base") == "under":
        return _under_position(ctx)[0]
    return invested(ctx.legs)


def liability_room(ctx: MatchCtx, params: Dict[str, Any]) -> float:
    """Capitale ancora piazzabile sulla partita sotto ``max_liability_per_match``
    (0 = nessun tetto → inf). Clamp DIFENSIVO dentro l'engine: vale anche se il
    livello esterno e' mal configurato (review F0, HIGH #3)."""
    cap = float(params.get("max_liability_per_match") or 0.0)
    if cap <= 0:
        return float("inf")
    return max(0.0, cap - invested(ctx.legs))


def _close_actions(ctx: MatchCtx, cv: CashoutValue, params: Dict[str, Any],
                   role_map: Optional[Dict[Tuple[str, str], str]] = None) -> List[Action]:
    role_map = role_map or {
        (MARKET_OU35, SEL_UNDER): "under_close",
        (MARKET_OU45, SEL_OVER): "over_close",
        (MARKET_OU45, SEL_UNDER): "reentry_green",
    }
    acts = []
    for key, plan in cv.plans.items():
        if not plan.actionable:
            continue
        acts.append(_place(role_map[key], key[0], key[1], plan.side, plan.price, plan.size,
                           note=plan.note))
    return acts


def force_flat_actions(ctx: MatchCtx, books: Dict[Tuple[str, str], Book],
                       params: Dict[str, Any]) -> List[Action]:
    """Chiusura al best di ogni selezione aperta (richiesta manuale / stop)."""
    c = float(params["commission_pct"]) / 100.0
    cv = cashout_value(ctx.legs, books, c, int(params["cashout_place_at_ticks"]))
    return _cancel_live(ctx) + _close_actions(ctx, cv, params)


def _pending_closings(ctx: MatchCtx) -> List[Leg]:
    return [l for l in ctx.legs if l.is_live and l.role in ("under_close", "over_close", "manual_close")]


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------
def decide(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Decision:
    st = ctx.state
    if st in TERMINAL_STATES:
        return Decision(st, [], "terminale")

    c = float(params["commission_pct"]) / 100.0

    # -- mercato chiuso: regolamento -------------------------------------------------
    if snap.market_status == "CLOSED" or st == "SETTLING":
        if st != "SETTLING":
            return Decision("SETTLING", _cancel_live(ctx), "mercato chiuso")
        if snap.final_total is None:
            return Decision("SETTLING", [], "attesa punteggio finale")
        res = settle_legs(ctx.legs, int(snap.final_total), c)
        return Decision("SETTLED", [], f"regolato T={snap.final_total}",
                        updates={"settled_pnl": res.net},
                        telemetry={"settle": {"per_leg": res.per_leg, "per_market": res.per_market,
                                              "net": res.net}})

    if st in ("WATCH", "PRE_ENTRY_PENDING", "PRE_OPEN", "PRE_GREEN_PENDING", "HOLD",
              "PRE_LAST_ENTRY_PENDING"):
        return _decide_prematch(ctx, snap, params, c)
    if st == "IDLE_LIVE":
        return Decision(st, [], "nessuna posizione")
    if st == "LIVE_UNCOVERED":
        return _decide_uncovered(ctx, snap, params, c)
    if st == "LIVE_COVER_PENDING":
        return _decide_cover_pending(ctx, snap, params, c)
    if st == "LIVE_COVERED":
        return _decide_covered(ctx, snap, params, c)
    if st == "LIVE_CLOSING":
        return _decide_closing(ctx, snap, params, c)
    if st == "FLAT":
        return _decide_flat(ctx, snap, params, c)
    if st == "REENTRY_PENDING":
        return _decide_reentry_pending(ctx, snap, params, c)
    if st == "REENTRY_OPEN":
        return _decide_reentry_open(ctx, snap, params, c)
    if st == "REENTRY_GREEN_PENDING":
        return _decide_reentry_green_pending(ctx, snap, params, c)
    return Decision("ERROR", _cancel_live(ctx), f"stato sconosciuto {st}")


# ---- pre-match -------------------------------------------------------------------
def _entry_guard(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> Optional[str]:
    """None se si puo' entrare, altrimenti il motivo."""
    if not params["pre_enabled"]:
        return "pre_disabilitato"
    if not snap.feed_fresh:
        return "feed stantio"
    window_from = snap.ko_at - float(params["entry_hours_before_ko"]) * 3600.0
    if snap.now < window_from:
        return "fuori finestra"
    if snap.now >= snap.ko_at - float(params["pre_last_entry_min"]) * 60.0:
        return "finestra pre-match chiusa"
    if ctx.cycle_no >= int(params["pre_max_cycles"]):
        return "max cicli"
    if ctx.last_green_at is not None and snap.now - ctx.last_green_at < float(params["pre_reentry_cooldown_s"]):
        return "cooldown"
    bk = snap.book(MARKET_OU35, SEL_UNDER)
    if bk is None or bk.best_back is None or bk.status != "OPEN" or bk.inplay:
        return "book assente"
    if bk.best_back < float(params["pre_entry_price_min"]) or bk.best_back > float(params["pre_entry_price_max"]):
        return f"prezzo {bk.best_back} fuori banda"
    need = float(params["stake"]) * float(params["pre_min_back_size_factor"])
    if float(bk.back_size) < need:
        return f"liquidita {bk.back_size:.2f} < {need:.2f}"
    if bk.best_lay is not None:
        t = ticks_between(bk.best_back, bk.best_lay)
        if t is None or t > int(params["pre_max_spread_ticks"]):
            return f"spread {t} tick"
    if float(params["stake"]) > liability_room(ctx, params) + _EPS:
        return "cap liability partita"
    return None


def _decide_prematch(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    st = ctx.state
    stake = float(params["stake"])
    bk = snap.book(MARKET_OU35, SEL_UNDER)
    S, Pe = _under_position(ctx)
    last_entry_at = snap.ko_at - float(params["pre_last_entry_min"]) * 60.0

    # -- KO arrivato: si passa al live con quello che c'e' ----------------------------
    if snap.inplay:
        acts = []
        for leg in ctx.legs:
            if not leg.is_live:
                continue
            if leg.persistence == "PERSIST" and leg.role == "under_last":
                if snap.now - snap.ko_at < float(params["cancel_unmatched_after_ko_s"]):
                    continue           # grazia: il residuo PERSIST puo' ancora abbinarsi
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                               selection=leg.selection))
        if S > 0:
            return Decision("LIVE_UNCOVERED", acts, "in-play con posizione Under",
                            updates={"entry_price_initial": ctx.entry_price_initial or Pe})
        return Decision("IDLE_LIVE", acts, "in-play senza posizione")

    if st == "WATCH":
        why = _entry_guard(ctx, snap, params)
        if why:
            return Decision("WATCH", [], why)
        return Decision("PRE_ENTRY_PENDING",
                        [_place("under_entry", MARKET_OU35, SEL_UNDER, "back", bk.best_back, stake)],
                        f"ingresso ciclo {ctx.cycle_no}")

    if st == "PRE_ENTRY_PENDING":
        leg = _last(ctx, "under_entry")
        if leg is None:
            return Decision("WATCH", [], "gamba assente")
        if not leg.is_live and leg.matched <= 0:
            return Decision("WATCH", [], "ingresso non abbinato")
        if leg.filled and not leg.is_live:
            return _after_entry_fill(ctx, snap, params, leg)
        if leg.is_live and snap.now - leg.placed_at >= float(params["pre_entry_ttl_s"]):
            if leg.matched > 0:
                return Decision("PRE_OPEN", [Action(kind="cancel", ref=leg.ref, role=leg.role)],
                                "ttl: tengo la parte abbinata")
            return Decision("WATCH", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl scaduto")
        if leg.filled:
            return _after_entry_fill(ctx, snap, params, leg)
        return Decision(st, [], "attesa fill ingresso")

    if st == "PRE_OPEN":
        if S <= 0:
            return Decision("WATCH", _cancel_live(ctx), "posizione assente")
        green = _last(ctx, "under_green")
        # ESPOSIZIONE NETTA della selezione (ingresso + eventuali fill PARZIALI della
        # green): e' l'unica base coerente per size di chiusura e P&L bloccato
        w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
        flat = abs(w - l) < _FLAT_EPS
        # ultimo ingresso: KO - pre_last_entry_min
        if snap.now >= last_entry_at:
            acts = _cancel_live(ctx, ("under_green",))
            if flat:
                return _cycle_done(ctx, snap, S, Pe, green, w)
            if bk is None or bk.best_lay is None:
                return Decision("HOLD", acts, "ultimo ingresso: prezzo lay assente, tengo")
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            locked = min(plan.expected_if_win, plan.expected_if_lose) if plan.actionable else 0.0
            if plan.actionable and locked > _FLAT_EPS:
                acts.append(_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price,
                                   plan.size, final=True, note="ultimo ingresso: chiusura in profitto"))
                return Decision("PRE_GREEN_PENDING", acts, f"ultimo ingresso: locked {locked:.2f} > 0",
                                telemetry={"last_entry_locked": round(locked, 2)})
            return Decision("HOLD", acts, f"ultimo ingresso: locked {locked:.2f} <= 0, tengo")
        # esposizione piatta (green abbinata per intero) -> ciclo chiuso
        if flat and (green is None or not green.is_live):
            return _cycle_done(ctx, snap, S, Pe, green, w)
        if params["pre_exit_mode"] == "resting":
            # nessuna green viva sul book (mai appoggiata, ritirata, o abbinata SOLO in
            # parte e ritirata): si (ri)appoggia una lay per il RESIDUO al target
            if green is None or not green.is_live:
                target = green_target(Pe, int(params["pre_green_ticks"]))
                plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                                       best_lay_price=None, fraction=1.0, target_price=target)
                if plan.actionable:
                    return Decision("PRE_OPEN",
                                    [_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size)],
                                    "green resting appoggiata (residuo)" if green is not None else "green resting appoggiata")
            return Decision("PRE_OPEN", [], "posizione aperta, green resting sul book")
        # taker
        target = green_target(Pe, int(params["pre_green_ticks"]))
        if bk is not None and bk.best_lay is not None and bk.best_lay <= target + _EPS:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                return Decision("PRE_GREEN_PENDING",
                                [_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size)],
                                "green taker: 2 tick disponibili")
        return Decision("PRE_OPEN", [], "posizione aperta, in attesa dei 2 tick")

    if st == "PRE_GREEN_PENDING":
        green = _last(ctx, "under_green")
        if green is None:
            return Decision("PRE_OPEN", [], "green assente")
        if not green.is_live and green.matched <= 0:
            # chiusura non abbinata: posizione ancora aperta → si torna a gestirla
            # (finale = KO imminente: HOLD, entrera' in live scoperta)
            return Decision("HOLD" if green.final else "PRE_OPEN", [], "green non abbinata")
        if green.filled and not green.is_live:
            w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
            if abs(w - l) >= _FLAT_EPS:
                # chiusura taker abbinata SOLO in parte: residuo ancora scoperto →
                # si torna a gestirlo (PRE_OPEN riappoggia/chiude il residuo); la
                # finale (KO imminente) va in HOLD col residuo
                return Decision("HOLD" if green.final else "PRE_OPEN", [], "green parziale: residuo aperto")
            if green.final:
                return _after_final_green(ctx, snap, params, bk, stake)
            return _cycle_done(ctx, snap, S, Pe, green, w)
        if green.is_live and snap.now - green.placed_at >= float(params["close_retry_s"]) and \
                ctx.attempts < int(params["close_max_attempts"]):
            if bk is not None and bk.best_lay is not None:
                w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
                plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                       best_lay_price=bk.best_lay, fraction=1.0)
                if plan.actionable:
                    return Decision(st, [Action(kind="cancel", ref=green.ref, role=green.role),
                                         _place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price,
                                                plan.size, final=green.final)],
                                    "green taker: riprezzo", updates={"attempts": ctx.attempts + 1})
        return Decision(st, [], "attesa fill green")

    if st == "HOLD":
        return Decision("HOLD", [], "in perdita pre-KO: tengo fino al live")

    if st == "PRE_LAST_ENTRY_PENDING":
        return Decision(st, [], "attesa fill ingresso PERSIST")

    return Decision("ERROR", _cancel_live(ctx), f"stato pre-match sconosciuto {st}")


def _after_entry_fill(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], leg: Leg) -> Decision:
    upd = {}
    if ctx.entry_price_initial is None:
        upd["entry_price_initial"] = leg.fill_price
    acts: List[Action] = []
    if params["pre_exit_mode"] == "resting":
        target = green_target(leg.fill_price, int(params["pre_green_ticks"]))
        w, l = exposure(ctx.legs, MARKET_OU35, SEL_UNDER)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                               best_lay_price=None, fraction=1.0, target_price=target)
        if plan.actionable:
            acts.append(_place("under_green", MARKET_OU35, SEL_UNDER, "lay", plan.price, plan.size,
                               note="take-profit resting"))
    return Decision("PRE_OPEN", acts, "ingresso abbinato", updates=upd)


def _cycle_done(ctx: MatchCtx, snap: Snapshot, S: float, Pe: Optional[float], green: Optional[Leg],
                locked_w: Optional[float] = None) -> Decision:
    # P&L bloccato = esposizione netta reale (W ≈ L a green completa), coerente
    # anche con fill parziali; il calcolo "S·(Pe/p−1)" resta solo come fallback
    if locked_w is not None:
        locked = float(locked_w)
    else:
        locked = locked_pnl_back(S, Pe, green.fill_price) if (Pe and green is not None) else 0.0
    tele = {"pre_cycle": {"cycle": ctx.cycle_no, "entry": Pe, "exit": green.fill_price if green else None,
                          "stake": S, "locked": round(locked, 2),
                          "closed_at": snap.now}}
    return Decision("WATCH", [], f"ciclo {ctx.cycle_no} chiuso: +{locked:.2f}",
                    updates={"cycle_no": ctx.cycle_no + 1, "last_green_at": snap.now,
                             "attempts": 0, "_archive_legs": True},
                    telemetry=tele)


def _after_final_green(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any],
                       bk: Optional[Book], stake: float) -> Decision:
    upd = {"cycle_no": ctx.cycle_no + 1, "last_green_at": snap.now, "attempts": 0, "_archive_legs": True}
    if not params["last_entry_persist"]:
        return Decision("IDLE_LIVE", [], "ultimo ingresso disabilitato", updates=upd)
    if bk is None or bk.best_back is None or bk.status != "OPEN":
        return Decision("IDLE_LIVE", [], "ultimo ingresso: book assente", updates=upd)
    need = stake * float(params["pre_min_back_size_factor"])
    if float(bk.back_size) < need:
        return Decision("IDLE_LIVE", [], f"ultimo ingresso: liquidita {bk.back_size:.2f} < {need:.2f}", updates=upd)
    # il ciclo appena chiuso viene archiviato dagli updates → il tetto si misura
    # sul capitale che resta davvero a rischio (qui: zero) piu' il nuovo stake
    if stake > float(params.get("max_liability_per_match") or float("inf")) + _EPS and \
            float(params.get("max_liability_per_match") or 0.0) > 0:
        return Decision("IDLE_LIVE", [], "ultimo ingresso: cap liability partita", updates=upd)
    price = bk.best_back
    n_up = int(params["last_entry_ticks_above"])
    if n_up > 0:
        price = float(ticks_away(price, n_up))
    return Decision("PRE_LAST_ENTRY_PENDING",
                    [_place("under_last", MARKET_OU35, SEL_UNDER, "back", price, stake, persistence="PERSIST")],
                    "ultimo ingresso PERSIST", updates=upd)


# ---- live -----------------------------------------------------------------------
def _decide_uncovered(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    S, Pe = _under_position(ctx)
    if S <= 0:
        return Decision("IDLE_LIVE", _cancel_live(ctx), "nessuna posizione Under")
    acts = _late_persist_cancel(ctx, snap, params)
    if not params["cover_enabled"]:
        return Decision("LIVE_COVERED", acts, "copertura disabilitata", updates={"cover_skipped": True})
    bk = snap.book(MARKET_OU45, SEL_OVER)
    timing = cover_timing(goals=snap.goals, minute=snap.minute, hazard=snap.hazard,
                          p4_market=snap.p4_market, last_goal_ts=snap.last_goal_ts,
                          now=snap.now, params=params,
                          price_over=bk.best_back if bk else None,
                          cover_gain_pct=snap.cover_gain_pct)
    x_now = None
    if bk is not None and bk.best_back is not None and bk.best_back > 1.0:
        x_now = cover_size(S, bk.best_back, c, float(params["cover_profit_factor"]))
    if timing == "skip":
        return Decision("LIVE_COVERED", acts, "copertura saltata: troppi gol", updates={"cover_skipped": True})
    if timing == "wait" or bk is None or bk.best_back is None or bk.status != "OPEN":
        tele = {"cover_wait": {"minute": snap.minute, "goals": snap.goals, "hazard": snap.hazard,
                               "p4_market": snap.p4_market, "price_over": bk.best_back if bk else None,
                               "x_now": x_now}}
        return Decision("LIVE_UNCOVERED", acts, "attendo per coprire", telemetry=tele)
    size, over = cover_legal_size(x_now, params)
    room = liability_room(ctx, params)
    if room < 0.01:
        return Decision("LIVE_COVERED", acts, "copertura saltata: cap liability partita",
                        updates={"cover_skipped": True})
    if size > room:
        size = round(room, 2)   # clamp difensivo (mai oltre il tetto per partita)
    if float(bk.back_size) + _EPS < size:
        tele = {"cover_wait": {"minute": snap.minute, "goals": snap.goals, "x_now": x_now,
                               "reason": "liquidita"}}
        return Decision("LIVE_UNCOVERED", acts, f"copertura: liquidita {bk.back_size:.2f} < {size:.2f}",
                        telemetry=tele)
    acts.append(_place("over_cover", MARKET_OU45, SEL_OVER, "back", bk.best_back, size,
                       note=f"X={x_now:.2f} legal={size:.2f} over={over:.1f}%"))
    return Decision("LIVE_COVER_PENDING", acts, "copertura Over 4.5",
                    telemetry={"cover": {"x": round(x_now, 2), "size": size, "overshoot_pct": over,
                                         "price": bk.best_back, "minute": snap.minute}})


def _late_persist_cancel(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any]) -> List[Action]:
    acts = []
    for leg in ctx.legs:
        if leg.is_live and leg.role == "under_last" and \
                snap.now - snap.ko_at >= float(params["cancel_unmatched_after_ko_s"]):
            acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                               selection=leg.selection))
    return acts


def _decide_cover_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    leg = _last(ctx, "over_cover")
    if leg is None:
        return Decision("LIVE_UNCOVERED", [], "gamba copertura assente")
    if not leg.is_live and leg.matched <= 0:
        return Decision("LIVE_UNCOVERED", [], "copertura non abbinata: ritento",
                        updates={"attempts": ctx.attempts + 1})
    if leg.filled and not leg.is_live:
        return Decision("LIVE_COVERED", [], "copertura abbinata", updates={"attempts": 0})
    if leg.is_live and snap.now - leg.placed_at >= float(params["close_retry_s"]) and \
            ctx.attempts < int(params["close_max_attempts"]):
        bk = snap.book(MARKET_OU45, SEL_OVER)
        if bk is not None and bk.best_back is not None and leg.remaining > 0:
            S, _ = _under_position(ctx)
            # RESIDUO ESATTO: la parte gia' abbinata (m @ p_old) contribuisce
            # m·(p_old−1)·(1−c); il resto va dimensionato al prezzo NUOVO
            x = cover_size_residual(S, bk.best_back, c, float(params["cover_profit_factor"]),
                                    matched=leg.matched, matched_price=leg.fill_price)
            if x <= 0:
                return Decision("LIVE_COVERED", [Action(kind="cancel", ref=leg.ref, role=leg.role)],
                                "copertura sufficiente", updates={"attempts": 0})
            size, _ = cover_legal_size(x, params)
            return Decision("LIVE_COVER_PENDING",
                            [Action(kind="cancel", ref=leg.ref, role=leg.role),
                             _place("over_cover", MARKET_OU45, SEL_OVER, "back", bk.best_back, size)],
                            "copertura: riprezzo", updates={"attempts": ctx.attempts + 1})
    return Decision("LIVE_COVER_PENDING", [], "attesa fill copertura")


def _loss_rule(snap: Snapshot, params: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    """(pct, etichetta) della regola di perdita tollerata applicabile ora, o None."""
    if snap.ht_active and params["ht_loss_exit_enabled"]:
        return (float(params["ht_loss_pct"]), "ht")
    if snap.minute is not None and params["h2_loss_exit_enabled"] and \
            int(params["h2_loss_from_min"]) <= int(snap.minute) <= int(params["h2_loss_to_min"]):
        return (float(params["h2_loss_pct"]), "2t")
    return None


def _decide_covered(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    if not open_selections(ctx.legs):
        return Decision("FLAT", [], "nessuna esposizione")
    acts = _late_persist_cancel(ctx, snap, params)
    cv = cashout_value(ctx.legs, snap.books, c, int(params["cashout_place_at_ticks"]))
    base = _cashout_base(ctx, params)
    tele = {"cashout": {"net": cv.net, "gross": cv.gross, "base": base, "complete": cv.complete,
                        "pct": round(100.0 * cv.net / base, 2) if base > 0 else None}}
    if not cv.complete:
        return Decision("LIVE_COVERED", acts, "prezzi incompleti", telemetry=tele)
    if should_cashout(cv.net, base, float(params["cashout_profit_pct"])):
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"profit: {cv.net:.2f} >= {params['cashout_profit_pct']}% di {base:.2f}",
                        updates={"close_reason": "profit", "attempts": 0}, telemetry=tele)
    smart, why, stele = smart_cashout(
        cv_net=cv.net, base=base, legs=ctx.legs, books=snap.books, commission=c, params=params,
        hazard=snap.hazard, pressure=float(snap.pressure or 1.0), goals=snap.goals,
        model_probs=snap.model_probs, place_at_ticks=int(params["cashout_place_at_ticks"]))
    tele["cashout"]["smart"] = stele
    if smart:
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"profit smart: {cv.net:.2f} ({why})",
                        updates={"close_reason": "profit", "attempts": 0}, telemetry=tele)
    rule = _loss_rule(snap, params)
    if rule is not None:
        pct, label = rule
        gmin, gmax = int(params["ht_loss_goals_min"]), int(params["ht_loss_goals_max"])
        in_goals = snap.goals is not None and gmin <= int(snap.goals) <= gmax
        decided = None
        if in_goals and params.get("loss_exit_mode", "model") == "model":
            decided, why, ltele = loss_exit_model(
                cv_net=cv.net, base=base, pnl_by_total=net_pnl_by_total(ctx.legs, c),
                p_total_model=snap.p_total_model, p_total_emp=snap.p_total_emp,
                p4_market=snap.p4_market, params=params)
            ltele["window"] = label
            tele["loss_exit"] = ltele
            if decided:
                return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                                f"uscita a modello ({label}): {why}",
                                updates={"close_reason": f"loss_{label}", "attempts": 0}, telemetry=tele)
        if decided is None and loss_exit_ok(cv.net, base, pct, goals=snap.goals, gmin=gmin, gmax=gmax):
            tele.setdefault("loss_exit", {"mode": "fixed", "window": label, "pct": pct})
            return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                            f"loss tollerata ({label}): {cv.net:.2f} entro {pct}% di {base:.2f}",
                            updates={"close_reason": f"loss_{label}", "attempts": 0}, telemetry=tele)
    cap = float(params["event_loss_cap_pct"])
    if cap > 0 and base > 0 and cv.net <= -base * cap / 100.0:
        return Decision("LIVE_CLOSING", acts + _close_actions(ctx, cv, params),
                        f"cap perdita evento: {cv.net:.2f}",
                        updates={"close_reason": "loss_cap", "attempts": 0}, telemetry=tele)
    return Decision("LIVE_COVERED", acts, "tengo", telemetry=tele)


def _decide_closing(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    pend = _pending_closings(ctx)
    if not pend:
        if open_selections(ctx.legs):
            # residuo non chiuso (fill parziale gia' consolidato): riprova
            cv = cashout_value(ctx.legs, snap.books, c, int(params["cashout_place_at_ticks"]))
            acts = _close_actions(ctx, cv, params)
            if acts and ctx.attempts < int(params["close_max_attempts"]):
                return Decision("LIVE_CLOSING", acts, "chiusura residuo",
                                updates={"attempts": ctx.attempts + 1})
        upd = {"reentry_allowed": ctx.close_reason == "profit", "attempts": 0}
        return Decision("FLAT", [], f"chiuso ({ctx.close_reason})", updates=upd)
    acts: List[Action] = []
    if ctx.attempts >= int(params["close_max_attempts"]):
        # tentativi esauriti: si resta in attesa (chiusura naturale a fine
        # mercato / force_flat dalla UI), ma lo si DICE in telemetria
        return Decision("LIVE_CLOSING", [], "chiusura: tentativi esauriti",
                        telemetry={"close_retries_exhausted": True, "attempts": ctx.attempts})
    for leg in pend:
        if snap.now - leg.placed_at < float(params["close_retry_s"]):
            continue
        bk = snap.book(leg.market, leg.selection)
        if bk is None:
            continue
        # riprezzo del RESIDUO: l'esposizione include la parte gia' abbinata della
        # gamba pending (fix review F0: escluderla avrebbe raddoppiato la copertura)
        w, l = exposure(ctx.legs, leg.market, leg.selection)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                               best_lay_price=bk.best_lay, fraction=1.0,
                               place_at_ticks=int(params["cashout_place_at_ticks"]))
        acts.append(Action(kind="cancel", ref=leg.ref, role=leg.role, market=leg.market,
                           selection=leg.selection))
        if plan.actionable:
            acts.append(_place(leg.role, leg.market, leg.selection, plan.side, plan.price, plan.size))
    if acts:
        return Decision("LIVE_CLOSING", acts, "chiusura: riprezzo", updates={"attempts": ctx.attempts + 1})
    return Decision("LIVE_CLOSING", [], "attesa fill chiusura")


def _decide_flat(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    if open_selections(ctx.legs):
        return Decision("LIVE_COVERED", [], "esposizione residua")
    if not params["reentry_enabled"] or not ctx.reentry_allowed or ctx.reentry_done:
        return Decision("FLAT", [], "flat")
    if not snap.feed_fresh or snap.goals is None or snap.minute is None:
        return Decision("FLAT", [], "flat: dati feed mancanti")
    g = int(snap.goals)
    if g < 1 or g > int(params["reentry_max_goals"]):
        return Decision("FLAT", [], f"flat: {g} gol fuori range re-ingresso")
    if int(snap.minute) > int(params["reentry_until_min"]):
        return Decision("FLAT", [], "flat: oltre il minuto di re-ingresso")
    bk = snap.book(MARKET_OU45, SEL_UNDER)          # linea gol+3.5 con 1 gol = Under 4.5
    if bk is None or bk.best_back is None or bk.status != "OPEN":
        return Decision("FLAT", [], "flat: book Under 4.5 assente")
    if params["reentry_price_min_over_entry"] and ctx.entry_price_initial is not None and \
            bk.best_back <= float(ctx.entry_price_initial) + _EPS:
        return Decision("FLAT", [], f"flat: U4.5 {bk.best_back} <= ingresso {ctx.entry_price_initial}")
    stake = float(params["stake"])
    if float(bk.back_size) < stake * float(params["pre_min_back_size_factor"]):
        return Decision("FLAT", [], "flat: liquidita re-ingresso")
    if stake > liability_room(ctx, params) + _EPS:
        return Decision("FLAT", [], "flat: cap liability partita")
    return Decision("REENTRY_PENDING",
                    [_place("reentry", MARKET_OU45, SEL_UNDER, "back", bk.best_back, stake)],
                    "re-ingresso Under 4.5")


def _decide_reentry_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    leg = _last(ctx, "reentry")
    if leg is None:
        return Decision("FLAT", [], "gamba re-ingresso assente")
    if not leg.is_live and leg.matched <= 0:
        return Decision("FLAT", [], "re-ingresso non abbinato", updates={"reentry_done": True})
    if leg.filled and not leg.is_live:
        target = green_target(leg.fill_price, int(params["reentry_green_ticks"]))
        w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                               best_lay_price=None, fraction=1.0, target_price=target)
        acts = [_place("reentry_green", MARKET_OU45, SEL_UNDER, "lay", plan.price, plan.size)] \
            if plan.actionable else []
        return Decision("REENTRY_OPEN", acts, "re-ingresso abbinato")
    if leg.is_live and snap.now - leg.placed_at >= float(params["pre_entry_ttl_s"]):
        if leg.matched > 0:
            return Decision("REENTRY_OPEN", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl: parte abbinata")
        return Decision("FLAT", [Action(kind="cancel", ref=leg.ref, role=leg.role)], "ttl re-ingresso",
                        updates={"reentry_done": True})
    return Decision("REENTRY_PENDING", [], "attesa fill re-ingresso")


def _decide_reentry_open(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    green = _last(ctx, "reentry_green")
    w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
    if abs(w - l) < _FLAT_EPS:
        return Decision("FLAT", _cancel_live(ctx, ("reentry_green",)), "re-ingresso chiuso",
                        updates={"reentry_done": True})
    # (green abbinata SOLO in parte e non piu' viva → esposizione non piatta → si
    #  riappoggia una lay per il residuo, sotto)
    bk = snap.book(MARKET_OU45, SEL_UNDER)
    exit_min = int(params.get("reentry_exit_until_min") or 0)      # 0 = mai (si va a fine gara)
    if exit_min > 0 and snap.minute is not None and int(snap.minute) >= exit_min:
        if params["reentry_hold_if_loss"]:
            return Decision("REENTRY_OPEN", [], "oltre il limite: tengo (hold_if_loss)")
        acts = _cancel_live(ctx, ("reentry_green",))
        if bk is not None and bk.best_lay is not None:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                acts.append(_place("reentry_green", MARKET_OU45, SEL_UNDER, plan.side, plan.price, plan.size))
                return Decision("REENTRY_GREEN_PENDING", acts, "re-ingresso: chiusura a mercato")
        return Decision("REENTRY_OPEN", acts, "re-ingresso: prezzo assente")
    if green is None or not green.is_live:
        S, Pe = position(ctx.legs, MARKET_OU45, SEL_UNDER, ("reentry",))
        if Pe:
            target = green_target(Pe, int(params["reentry_green_ticks"]))
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=None,
                                   best_lay_price=None, fraction=1.0, target_price=target)
            if plan.actionable:
                return Decision("REENTRY_OPEN",
                                [_place("reentry_green", MARKET_OU45, SEL_UNDER, "lay", plan.price, plan.size)],
                                "green re-ingresso appoggiata")
    return Decision("REENTRY_OPEN", [], "re-ingresso aperto, green sul book")


def _decide_reentry_green_pending(ctx: MatchCtx, snap: Snapshot, params: Dict[str, Any], c: float) -> Decision:
    green = _last(ctx, "reentry_green")
    w, l = exposure(ctx.legs, MARKET_OU45, SEL_UNDER)
    if abs(w - l) < _FLAT_EPS or (green is not None and green.filled and not green.is_live):
        return Decision("FLAT", [], "re-ingresso chiuso", updates={"reentry_done": True})
    if green is not None and not green.is_live and green.matched <= 0:
        return Decision("REENTRY_OPEN", [], "chiusura re-ingresso non abbinata")
    if green is not None and green.is_live and snap.now - green.placed_at >= float(params["close_retry_s"]) \
            and ctx.attempts < int(params["close_max_attempts"]):
        bk = snap.book(MARKET_OU45, SEL_UNDER)
        if bk is not None and bk.best_lay is not None:
            plan = compute_greenup(matched_if_win=w, matched_if_lose=l, best_back_price=bk.best_back,
                                   best_lay_price=bk.best_lay, fraction=1.0)
            if plan.actionable:
                return Decision("REENTRY_GREEN_PENDING",
                                [Action(kind="cancel", ref=green.ref, role=green.role),
                                 _place("reentry_green", MARKET_OU45, SEL_UNDER, plan.side, plan.price, plan.size)],
                                "re-ingresso: riprezzo chiusura", updates={"attempts": ctx.attempts + 1})
    return Decision("REENTRY_GREEN_PENDING", [], "attesa fill chiusura re-ingresso")


# ---------------------------------------------------------------------------
# apply_decision
# ---------------------------------------------------------------------------
def apply_decision(ctx: MatchCtx, d: Decision, now: float) -> List[Leg]:
    """Applica stato/updates e crea le gambe pending per le azioni ``place``.

    Le azioni ``cancel`` NON cambiano lo stato della gamba: e' il chiamante
    (strategy) a marcare ``cancelled``/``open`` quando flumine conferma.
    Ritorna le nuove gambe create (in ordine), gia' con ``ref`` deterministico.
    """
    archive = False
    for k, v in d.updates.items():
        if k == "_archive_legs":
            archive = bool(v)
            continue
        setattr(ctx, k, v)
    if archive:
        # gambe del ciclo chiuso: restano nella lista (contabilita' del settlement)
        # ma escono dal capitale a rischio (fix review F0: senza `archived` lo stake
        # dei cicli precedenti si sommava a S e gonfiava copertura e basi %)
        for leg in ctx.legs:
            if leg.archived:
                continue
            if leg.status == "pending" and leg.matched <= 0:
                leg.status = "cancelled"
            leg.archived = True
    ctx.state = d.state
    new: List[Leg] = []
    for a in d.actions:
        if a.kind != "place":
            continue
        ctx.seq += 1
        ref = a.ref or f"{a.role}-{ctx.cycle_no}-{ctx.seq}"
        leg = Leg(role=a.role, market=a.market, selection=a.selection, side=a.side,
                  price=float(a.price), size=float(a.size), ref=ref, status="pending",
                  placed_at=float(now), persistence=a.persistence, cycle_no=ctx.cycle_no,
                  final=a.final)
        ctx.legs.append(leg)
        new.append(leg)
    if d.actions:
        ctx.last_action_at = float(now)
    return new
