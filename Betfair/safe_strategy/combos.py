"""combos.py — COMBINAZIONI a rischio quasi nullo fra mercati dello STESSO evento.

Punto 5 del piano: due/tre gambe sullo stesso evento il cui profitto e'
BLOCCATO DAI PREZZI (non da una stima): per ogni punteggio finale possibile
il saldo netto delle gambe e' >= 0, e in almeno un esito supera ``min_lock``.

Famiglie (``combo`` nel dict restituito):
  dutch       stesse selezioni mutuamente esclusive di UN mercato (1X2, O/U,
              Gol/NoGol, Risultato esatto celle+Any Other) con somma 1/back < 1:
              stake per gamba da ``Betfair/stream/trading/dutching.dutch_back``
              (profitto uguale qualunque vinca), verificato sulla griglia.
  under_stack back Under N+1 + lay Under N quando le quote si incrociano
              (back alto > lay basso): guadagna se i gol sono <= N+1, non
              perde se sono di piu'. Simmetrico ``over_stack`` (back Over N +
              lay Over N+1) e ``ou_span`` (back Under N+1 + back Over N).
  cs_cover    lay di una cella lontana del Risultato esatto + back dell'Over
              che copre esattamente i gol di quella cella (lay 3-3 + back
              Over 5.5): la gamba Over vince quando la cella si realizza.

Metodo: si enumerano i punteggi finali raggiungibili (gol residui 0..
``max_extra_goals``), si calcola il saldo NETTO per esito (commissione sul
profitto del singolo mercato, le perdite non si compensano fra mercati) e, per
le combinazioni a 2 gambe, si sceglie la ripartizione dello stake che MASSIMIZZA
il caso peggiore (funzione concava: ricerca ternaria). Gli stake vengono poi
arrotondati al centesimo su ``combo_stake`` EUR e il lock ri-verificato sugli
stake reali; ogni gamba deve avere ``size_available`` >= stake.

Il ``book`` del modello serve solo come sanity check: ordina le gambe con
quella piu' "regalata" per prima (da eseguire per prima) e riempie ``p_model``.

Puro: nessun I/O. Output = dict con la forma di ``Opportunity`` (prima gamba)
+ ``kind='combo'``, ``combo``, ``legs``, ``locked_profit_per_eur``,
``worst_case_per_eur``, ``best_case_per_eur``, ``total_stake``.
Rationale in italiano, SOLO ASCII.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from Betfair.stream.trading.dutching import dutch_back

DEFAULT_COMBO_PARAMS: Dict[str, Any] = {
    "commission": 0.05,         # commissione sul profitto netto di ogni mercato
    "min_lock": 0.01,           # profitto MASSIMO per EUR richiesto (almeno un esito)
    "min_worst": 0.0,           # caso peggiore netto per EUR (mai negativo)
    "combo_stake": 10.0,        # EUR totali della combinazione (size e arrotondamento)
    "min_size": 10.0,           # size minima per gamba (oltre allo stake reale)
    "max_per_event": 5,
    "max_extra_goals": 9,       # gol residui enumerati (>= linea O/U massima + 1)
    "conf_single_market": 0.85,
    "conf_multi_market": 0.65,
    "ternary_iters": 70,
}

_EPS = 1e-9
_SCORELINE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)
_ANY_OTHER_DRAW = re.compile(r"any\s*other.*draw", re.IGNORECASE)

Outcome = Tuple[int, int]
WinFn = Callable[[int, int], bool]


# --------------------------------------------------------------------- utils
def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def _price(v: Any) -> Optional[float]:
    f = _num(v)
    return f if f is not None and f > 1.0 else None


def _size(v: Any) -> float:
    f = _num(v)
    return max(0.0, f) if f is not None else 0.0


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _line_key(line: float) -> str:
    return str(float(line)).replace(".", "_")


def _is_open(status: Any) -> bool:
    return status == "OPEN"


def _runner_ok(r: Any) -> bool:
    return isinstance(r, dict) and r.get("runner_status") in (None, "ACTIVE")


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


# --------------------------------------------------------- funzioni "vince su"
def _win_under(line: float) -> WinFn:
    def win(h: int, a: int) -> bool:
        return h + a < line
    return win


def _win_over(line: float) -> WinFn:
    def win(h: int, a: int) -> bool:
        return h + a > line
    return win


def _win_cell(cell: Outcome) -> WinFn:
    def win(h: int, a: int) -> bool:
        return (h, a) == cell
    return win


def _win_any_other(agg: str, cs_max: int) -> WinFn:
    """Any Other Home/Away Win / Any Other Draw: risultato NON fra le celle quotate."""
    def win(h: int, a: int) -> bool:
        unlisted = h > cs_max or a > cs_max
        if agg == "home":
            return h > a and unlisted
        if agg == "away":
            return a > h and unlisted
        return h == a and unlisted
    return win


# ---------------------------------------------------------------------- gambe
class Leg:
    """Una gamba: selezione + lato + prezzo + size + funzione 'vince su (h,a)'."""

    __slots__ = ("market_type", "market_name", "line", "market_id", "selection_id",
                 "selection_name", "side", "price", "size_available", "win", "prob_key")

    def __init__(self, *, market_type: str, market_name: str, line: Optional[float],
                 market_id: Any, runner: dict, side: str, win: WinFn, prob_key: Optional[str]):
        self.market_type = market_type
        self.market_name = market_name
        self.line = line
        self.market_id = market_id
        sid = runner.get("selection_id")
        self.selection_id = int(sid) if sid is not None else None
        self.selection_name = str(runner.get("name") or "")
        self.side = side
        self.price = float(_price(runner.get("back") if side == "back" else runner.get("lay")) or 0.0)
        self.size_available = _size(runner.get("back_size") if side == "back" else runner.get("lay_size"))
        self.win = win
        self.prob_key = prob_key

    @property
    def valid(self) -> bool:
        return self.price > 1.0 and self.size_available > 0.0 and self.market_id is not None

    def profit(self, stake: float, h: int, a: int) -> float:
        """P&L LORDO della gamba con ``stake`` (stake back / stake lay) sull'esito (h,a)."""
        won = self.win(h, a)
        if self.side == "back":
            return stake * (self.price - 1.0) if won else -stake
        return -stake * (self.price - 1.0) if won else stake

    def label(self) -> str:
        return f"{'Back' if self.side == 'back' else 'Lay'} {self.selection_name} @{self.price:.2f}"


def _unit_profits(legs: Sequence[Leg], outcomes: Sequence[Outcome]) -> List[List[float]]:
    """Per gamba: P&L lordo per esito con stake 1 (calcolato una volta sola)."""
    return [[leg.profit(1.0, h, a) for h, a in outcomes] for leg in legs]


def _net_from_units(legs: Sequence[Leg], units: Sequence[Sequence[float]],
                    stakes: Sequence[float], comm: float) -> List[float]:
    """Saldo NETTO per esito: commissione sul profitto positivo di ogni mercato,
    le perdite di un mercato NON compensano i profitti di un altro."""
    n = len(units[0]) if units else 0
    groups: Dict[Any, List[int]] = {}
    for i, leg in enumerate(legs):
        groups.setdefault(leg.market_id, []).append(i)
    out = [0.0] * n
    for idxs in groups.values():
        for k in range(n):
            v = sum(units[i][k] * stakes[i] for i in idxs)
            out[k] += v * (1.0 - comm) if v > 0 else v
    return out


def _net_payoffs(legs: Sequence[Leg], stakes: Sequence[float], outcomes: Sequence[Outcome],
                 comm: float) -> List[float]:
    return _net_from_units(legs, _unit_profits(legs, outcomes), stakes, comm)


def _best_split(legs: Sequence[Leg], outcomes: Sequence[Outcome], comm: float,
                iters: int) -> float:
    """Frazione ``b`` dello stake sulla prima di DUE gambe che massimizza il caso
    peggiore (min sugli esiti di una funzione concava in b: ricerca ternaria)."""
    units = _unit_profits(legs, outcomes)

    def worst(b: float) -> float:
        return min(_net_from_units(legs, units, (b, 1.0 - b), comm))

    lo, hi = 0.0, 1.0
    for _ in range(max(10, iters)):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if worst(m1) < worst(m2):
            lo = m1
        else:
            hi = m2
    return (lo + hi) / 2.0


# ------------------------------------------------------------------ parsing
class _Event:
    """Mercati dell'evento gia' tradotti in gambe candidate."""

    def __init__(self, payload: dict, book: Dict[str, float], params: Dict[str, Any]) -> None:
        self.p = params
        self.payload = payload
        self.book = book
        self.minute = _int(payload.get("minute"))
        self.sh = _int(payload.get("score_home"))
        self.sa = _int(payload.get("score_away"))
        self.goals = self.sh + self.sa
        g = max(1, int(params["max_extra_goals"]))
        self.outcomes: List[Outcome] = [
            (self.sh + dh, self.sa + da) for dh in range(g + 1) for da in range(g + 1 - dh)
        ]
        self.ou = self._parse_ou()          # {line: {"under": Leg|None, "over": Leg|None, ...}}
        self.mo = self._parse_mo()          # [Leg] (3) oppure []
        self.btts = self._parse_btts()      # [Leg] (2) oppure []
        self.cs_legs, self.cs_complete = self._parse_cs()

    # --- O/U
    def _parse_ou(self) -> Dict[float, Dict[str, Any]]:
        out: Dict[float, Dict[str, Any]] = {}
        ou = self.payload.get("ou")
        for blk in (ou if isinstance(ou, list) else []):
            if not isinstance(blk, dict) or not _is_open(blk.get("status")):
                continue
            line = _num(blk.get("line"))
            if line is None or line <= self.goals:
                continue                # linea gia' decisa: e' un'anomalia, non una combo
            mid = blk.get("market_id")
            mname = f"Over/Under {line}"
            k = _line_key(line)
            entry: Dict[str, Any] = {"line": line, "market_id": mid,
                                     "under": None, "over": None, "under_lay": None, "over_lay": None}
            for s in (blk.get("selections") or []):
                if not _runner_ok(s):
                    continue
                nm = str(s.get("name") or "").lower()
                if "under" in nm:
                    win = _win_under(line)
                    entry["under"] = Leg(market_type="OVER_UNDER", market_name=mname, line=line,
                                         market_id=mid, runner=s, side="back", win=win,
                                         prob_key=f"under_{k}")
                    entry["under_lay"] = Leg(market_type="OVER_UNDER", market_name=mname, line=line,
                                             market_id=mid, runner=s, side="lay", win=win,
                                             prob_key=f"under_{k}")
                elif "over" in nm:
                    win_o = _win_over(line)
                    entry["over"] = Leg(market_type="OVER_UNDER", market_name=mname, line=line,
                                        market_id=mid, runner=s, side="back", win=win_o,
                                        prob_key=f"over_{k}")
                    entry["over_lay"] = Leg(market_type="OVER_UNDER", market_name=mname, line=line,
                                            market_id=mid, runner=s, side="lay", win=win_o,
                                            prob_key=f"over_{k}")
            out[line] = entry
        return out

    # --- 1X2
    def _parse_mo(self) -> List[Leg]:
        payload = self.payload
        odds = payload.get("odds")
        if not isinstance(odds, dict) or not _is_open(payload.get("mo_status")):
            return []
        mid = payload.get("mo_market_id")
        names = {"home": payload.get("home") or "Casa", "draw": "The Draw",
                 "away": payload.get("away") or "Trasferta"}
        wins: Dict[str, WinFn] = {"home": lambda h, a: h > a, "draw": lambda h, a: h == a,
                                  "away": lambda h, a: a > h}
        legs: List[Leg] = []
        for k in ("home", "draw", "away"):
            pair = odds.get(k)
            if not isinstance(pair, dict):
                return []
            legs.append(Leg(market_type="MATCH_ODDS", market_name="1X2", line=None, market_id=mid,
                            runner={**pair, "name": names[k]}, side="back", win=wins[k], prob_key=k))
        return legs

    # --- Gol/NoGol
    def _parse_btts(self) -> List[Leg]:
        blk = self.payload.get("btts")
        if not isinstance(blk, dict) or not _is_open(blk.get("status")):
            return []
        legs: List[Leg] = []
        for s in (blk.get("selections") or []):
            if not _runner_ok(s):
                continue
            nm = str(s.get("name") or "").strip().lower()
            if nm in ("yes", "si", "si'"):
                legs.append(Leg(market_type="BOTH_TEAMS_TO_SCORE", market_name="Gol/NoGol", line=None,
                                market_id=blk.get("market_id"), runner=s, side="back",
                                win=lambda h, a: h > 0 and a > 0, prob_key="btts_yes"))
            elif nm == "no":
                legs.append(Leg(market_type="BOTH_TEAMS_TO_SCORE", market_name="Gol/NoGol", line=None,
                                market_id=blk.get("market_id"), runner=s, side="back",
                                win=lambda h, a: h == 0 or a == 0, prob_key="btts_no"))
        return legs

    # --- Risultato esatto
    def _parse_cs(self) -> Tuple[List[Dict[str, Any]], bool]:
        """[{leg_back, leg_lay, cell|agg, cover_line}], complete = ogni runner vivo ha un back."""
        blk = self.payload.get("cs")
        if not isinstance(blk, dict) or not _is_open(blk.get("status")):
            return [], False
        mid = blk.get("market_id")
        sels = [s for s in (blk.get("selections") or []) if _runner_ok(s)]
        cells: List[Tuple[dict, Optional[Outcome], Optional[str]]] = []
        cs_max = 0
        for s in sels:
            name = str(s.get("name") or "")
            m = _SCORELINE_RE.match(name)
            if m:
                cell = (int(m.group(1)), int(m.group(2)))
                cs_max = max(cs_max, cell[0], cell[1])
                cells.append((s, cell, None))
            elif _ANY_OTHER_HOME.search(name):
                cells.append((s, None, "home"))
            elif _ANY_OTHER_AWAY.search(name):
                cells.append((s, None, "away"))
            elif _ANY_OTHER_DRAW.search(name):
                cells.append((s, None, "draw"))
        out: List[Dict[str, Any]] = []
        complete = bool(cells)
        for s, cell, agg in cells:
            if cell is not None:
                if cell[0] < self.sh or cell[1] < self.sa:
                    continue            # cella morta: esclusa (non puo' piu' vincere)
                win = _win_cell(cell)
                cover_line = cell[0] + cell[1] - 0.5
                key = f"cs_{cell[0]}_{cell[1]}"
            else:
                win = _win_any_other(str(agg), cs_max)
                cover_line = cs_max + 0.5
                key = f"cs_any_other_{agg}"
            if not any(win(h, a) for h, a in self.outcomes):
                continue                # irraggiungibile nella griglia: esclusa
            back = Leg(market_type="CORRECT_SCORE", market_name="Risultato esatto", line=None,
                       market_id=mid, runner=s, side="back", win=win, prob_key=key)
            lay = Leg(market_type="CORRECT_SCORE", market_name="Risultato esatto", line=None,
                      market_id=mid, runner=s, side="lay", win=win, prob_key=key)
            if not back.valid:
                complete = False
            out.append({"back": back, "lay": lay, "cover_line": cover_line})
        return out, complete

    # --- book sanity
    def book_edge(self, leg: Leg) -> Optional[float]:
        pb = _num(self.book.get(leg.prob_key)) if leg.prob_key else None
        if pb is None:
            return None
        return (pb - 1.0 / leg.price) if leg.side == "back" else (1.0 / leg.price - pb)


# ---------------------------------------------------------------- valutazione
def _evaluate(ev: _Event, combo: str, legs: List[Leg], ratios: List[float],
              why: str) -> Optional[dict]:
    """Stake reali, lock sugli stake reali, size, forma finale. None se non regge."""
    p = ev.p
    comm = float(p["commission"])
    total_req = float(p["combo_stake"])
    if any(not leg.valid for leg in legs) or len(legs) < 2:
        return None
    stakes = [round(r * total_req, 2) for r in ratios]
    if any(s < 0.01 for s in stakes):
        return None
    total = sum(stakes)
    if total <= 0:
        return None
    for leg, s in zip(legs, stakes):
        if leg.size_available < s or leg.size_available < float(p["min_size"]):
            return None
    net = _net_payoffs(legs, stakes, ev.outcomes, comm)
    worst = min(net) / total
    best = max(net) / total
    if worst < float(p["min_worst"]) - _EPS or best < float(p["min_lock"]) - _EPS:
        return None
    markets = {leg.market_id for leg in legs}
    base = float(p["conf_single_market"] if len(markets) == 1 else p["conf_multi_market"])
    depth = min(leg.size_available / max(_EPS, 2.0 * s) for leg, s in zip(legs, stakes))
    conf = base * (0.5 + 0.5 * min(1.0, depth))
    # gamba "regalata" per prima (book): e' quella da eseguire per prima
    order = sorted(range(len(legs)),
                   key=lambda i: -(ev.book_edge(legs[i]) if ev.book_edge(legs[i]) is not None else -1.0))
    legs = [legs[i] for i in order]
    stakes = [stakes[i] for i in order]
    first = legs[0]
    pb = _num(ev.book.get(first.prob_key)) if first.prob_key else None
    score = f"{ev.sh}-{ev.sa}"
    parts = " + ".join(f"{leg.label()} ({s / total:.2f} EUR/EUR)" for leg, s in zip(legs, stakes))
    return {
        "kind": "combo", "combo": combo,
        "market_type": first.market_type, "market_name": first.market_name, "line": first.line,
        "market_id": first.market_id, "selection_id": first.selection_id,
        "selection_name": first.selection_name, "side": first.side,
        "price": round(first.price, 4), "size_available": round(first.size_available, 2),
        "p_model": round(pb if pb is not None else 1.0 / first.price, 6),
        "p_implied": round(1.0 / first.price, 6),
        "edge": round(worst, 6), "ev": round(worst, 6),
        "confidence": round(conf, 4),
        "rationale": (f"{parts} sul {score} al {ev.minute}': {why}; profitto bloccato "
                      f"{_pct(worst)} per EUR (caso migliore {_pct(best)}), "
                      f"{total:.2f} EUR totali"),
        "minute": ev.minute, "score": score,
        "legs": [{
            "market_type": leg.market_type, "market_id": leg.market_id,
            "selection_id": leg.selection_id, "selection_name": leg.selection_name,
            "side": leg.side, "price": round(leg.price, 4),
            "size_available": round(leg.size_available, 2),
            "stake_ratio": round(s / total, 6), "stake": s,
        } for leg, s in zip(legs, stakes)],
        "locked_profit_per_eur": round(worst, 6),
        "worst_case_per_eur": round(worst, 6),
        "best_case_per_eur": round(best, 6),
        "total_stake": round(total, 2),
    }


def _pair(ev: _Event, combo: str, a: Leg, b: Leg, why: str) -> Optional[dict]:
    if not (a.valid and b.valid) or a.market_id == b.market_id and a.selection_id == b.selection_id:
        return None
    frac = _best_split((a, b), ev.outcomes, float(ev.p["commission"]), int(ev.p["ternary_iters"]))
    return _evaluate(ev, combo, [a, b], [frac, 1.0 - frac], why)


# ------------------------------------------------------------------- famiglie
def _dutch_market(ev: _Event, legs: List[Leg], label: str) -> Optional[dict]:
    """Dutching su tutti i runner VIVI di un mercato (somma 1/back < 1)."""
    if len(legs) < 2 or any(not leg.valid for leg in legs):
        return None
    inv = sum(1.0 / leg.price for leg in legs)
    if inv >= 1.0 - _EPS:
        return None
    plan = dutch_back([(leg.selection_id or i, leg.price) for i, leg in enumerate(legs)],
                      float(ev.p["combo_stake"]))
    if not plan.actionable or len(plan.legs) != len(legs) or plan.total_stake <= 0:
        return None
    ratios = [dl.size / plan.total_stake for dl in plan.legs]
    return _evaluate(ev, "dutch", legs, ratios,
                     f"dutching {label} con book {inv * 100:.2f}% (< 100%)")


def _family_dutch(ev: _Event, out: List[dict]) -> None:
    if ev.mo:
        live = [leg for leg in ev.mo if any(leg.win(h, a) for h, a in ev.outcomes)]
        r = _dutch_market(ev, live, "1X2")
        if r:
            out.append(r)
    for line, e in ev.ou.items():
        if e["under"] and e["over"]:
            r = _dutch_market(ev, [e["under"], e["over"]], f"Over/Under {line}")
            if r:
                out.append(r)
    if ev.btts:
        live = [leg for leg in ev.btts if any(leg.win(h, a) for h, a in ev.outcomes)]
        r = _dutch_market(ev, live, "Gol/NoGol")
        if r:
            out.append(r)
    if ev.cs_legs and ev.cs_complete:
        r = _dutch_market(ev, [c["back"] for c in ev.cs_legs], "Risultato esatto")
        if r:
            out.append(r)


def _family_ladder(ev: _Event, out: List[dict]) -> None:
    lines = sorted(ev.ou)
    for i, lo in enumerate(lines):
        for hi in lines[i + 1:]:
            e_lo, e_hi = ev.ou[lo], ev.ou[hi]
            # under_stack: back Under hi + lay Under lo, serve back(hi) > lay(lo)
            u_hi, ul_lo = e_hi["under"], e_lo["under_lay"]
            if u_hi and ul_lo and u_hi.valid and ul_lo.valid and u_hi.price > ul_lo.price:
                r = _pair(ev, "under_stack", u_hi, ul_lo,
                          f"Under {hi} back {u_hi.price:.2f} sopra il lay di Under {lo} {ul_lo.price:.2f}")
                if r:
                    out.append(r)
            # over_stack: back Over lo + lay Over hi, serve back(lo) > lay(hi)
            o_lo, ol_hi = e_lo["over"], e_hi["over_lay"]
            if o_lo and ol_hi and o_lo.valid and ol_hi.valid and o_lo.price > ol_hi.price:
                r = _pair(ev, "over_stack", o_lo, ol_hi,
                          f"Over {lo} back {o_lo.price:.2f} sopra il lay di Over {hi} {ol_hi.price:.2f}")
                if r:
                    out.append(r)
            # ou_span: back Under hi + back Over lo (coprono tutto: 1/U + 1/O < 1)
            if u_hi and o_lo and u_hi.valid and o_lo.valid and 1.0 / u_hi.price + 1.0 / o_lo.price < 1.0:
                r = _pair(ev, "ou_span", u_hi, o_lo,
                          f"Under {hi} @{u_hi.price:.2f} e Over {lo} @{o_lo.price:.2f} coprono ogni esito")
                if r:
                    out.append(r)


def _family_cs_cover(ev: _Event, out: List[dict]) -> None:
    for c in ev.cs_legs:
        lay: Leg = c["lay"]
        e = ev.ou.get(c["cover_line"])
        if not lay.valid or not e or not e["over"] or not e["over"].valid:
            continue
        over: Leg = e["over"]
        if lay.price >= over.price:
            continue                    # serve lay(cella) < back(Over di copertura)
        r = _pair(ev, "cs_cover", lay, over,
                  f"lay {lay.selection_name} @{lay.price:.2f} coperto da Over {e['line']} @{over.price:.2f}")
        if r:
            out.append(r)


# ----------------------------------------------------------------------- API
def find_combos(payload: dict, book: Dict[str, float], *, params: Optional[dict] = None) -> List[dict]:
    """Combinazioni a profitto bloccato per l'evento, ordinate per lock decrescente.

    ``payload``: riga calcio di safe_strategy_scan; ``book``: P del modello
    (solo sanity/ordinamento gambe, puo' essere vuoto). Mai eccezioni su
    blocchi mancanti.
    """
    prm = {**DEFAULT_COMBO_PARAMS, **(params or {})}
    if not isinstance(payload, dict):
        return []
    ev = _Event(payload, book if isinstance(book, dict) else {}, prm)
    out: List[dict] = []
    _family_dutch(ev, out)
    _family_ladder(ev, out)
    _family_cs_cover(ev, out)
    out.sort(key=lambda d: (-d["locked_profit_per_eur"], -d["best_case_per_eur"], -d["confidence"]))
    return out[: max(0, int(prm["max_per_event"]))]
