"""anomaly.py — QUOTE STANTIE/INCOERENTI in-play, solo logica INTERNA ai mercati.

Punto 4 del piano: "mercati sostanzialmente improbabili dove recuperare un
piccolo profitto". Qui NON serve un modello: si segnalano solo prezzi che
violano un VINCOLO LOGICO fra mercati dello stesso evento (o col punteggio),
percio' la regola resta valida anche quando il modello sbaglia.

Regole (``rule`` nel dict restituito):
  ou_ladder  monotonia della scala Over/Under: P(Under n+1) >= P(Under n) e
             P(Over n) >= P(Over n+1). Un back dell'Under alto a quota >=
             (1+min_gap) x back dell'Under basso e' incoerente (es. Under 7.5
             back 1.10 con Under 6.5 a 1.01). Simmetrico per gli Over e per i
             lay (lay dell'Over alto sotto il back dell'Over basso, lay
             dell'Under basso sotto il back dell'Under alto).
  decided    linea gia' DECISA dal punteggio (3 gol: Over 2.5 vinto), Gol/NoGol
             Si' con entrambe a segno, celle CORRECT_SCORE ormai impossibili:
             back del vincitore certo a quota > 1.01, o lay del perdente certo
             a quota bassa, con size abbinabile -> p = 1.0 (o 0.0).
  mo_cs      P(1X2) implicita dalle celle del CORRECT_SCORE de-viggate vs 1X2
             de-viggato: scarto > mo_cs_gap -> si segnala il LATO A BUON
             MERCATO (back del runner 1X2 se il CS lo da' piu' probabile, lay
             se lo da' meno probabile).
  ht_open    1X2 primo tempo ancora OPEN dopo il 45' con esito noto dalla
             timeline (gol entro il 45'): back del vincitore certo.

Il ``book`` del modello (OpportunityModel.book) e' usato SOLO come veto
(``book_veto``): mai segnalare un'operazione che il modello da' a EV<=0. Con
book vuoto la logica resta puramente di mercato.

Puro: nessun I/O. Output = lista di dict con la forma di ``Opportunity``
(opportunity.py) + ``kind='anomaly'``, ``rule``, ``gap``, ``ref``.
Rationale in italiano, SOLO ASCII (console Windows cp1252).
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_ANOMALY_PARAMS: Dict[str, Any] = {
    "min_gap": 0.03,            # scarto relativo minimo fra quote della scala O/U
    "mo_cs_gap": 0.08,          # scarto minimo P(1X2 da CS) vs P(1X2 da MO)
    "commission": 0.05,         # commissione sul profitto netto
    "min_size": 10.0,           # EUR abbinabili SUBITO al prezzo segnalato
    "max_per_event": 5,         # cap di segnali per evento
    "decided_min_price": 1.01,  # back di un esito deciso: sopra questa quota e' anomalia
    "max_lay_price": 5.0,       # mai lay oltre (liability sproporzionata)
    "min_edge": 0.005,          # edge minimo per segnalare
    "book_veto": True,          # scarta se il book del modello da' EV<=0
    "cs_book_range": (0.85, 1.30),  # somma 1/back del CS accettabile (mercato completo)
    "cs_min_runners": 6,        # celle CS con back valido per fidarsi del confronto
    "conf_decided": 0.90,
    "conf_ladder": 0.75,
    "conf_mo_cs": 0.60,
}

_EPS = 1e-9
_SCORELINE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)
_ANY_OTHER_DRAW = re.compile(r"any\s*other.*draw", re.IGNORECASE)


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


def _devig(runners: List[dict]) -> Dict[int, float]:
    """P implicite de-viggate (moltiplicativo) dai back validi dello stesso mercato."""
    inv: Dict[int, float] = {}
    for r in runners:
        p = _price(r.get("back"))
        if p is not None:
            inv[id(r)] = 1.0 / p
    s = sum(inv.values())
    if s <= 0:
        return {}
    return {k: v / s for k, v in inv.items()} if len(inv) > 1 else inv


def _ev(side: str, price: float, p: float, comm: float) -> float:
    """Profitto atteso per 1 EUR di stake, netto commissione."""
    if side == "back":
        return p * (price - 1.0) * (1.0 - comm) - (1.0 - p)
    return (1.0 - p) * (1.0 - comm) - p * (price - 1.0)


def _edge(side: str, price: float, p: float) -> float:
    return (p - 1.0 / price) if side == "back" else (1.0 / price - p)


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


# ------------------------------------------------------------------ parsing
def _ou_lines(payload: dict) -> List[dict]:
    """Blocchi O/U OPEN -> [{line, market_id, under, over}] ordinati per linea."""
    out: List[dict] = []
    ou = payload.get("ou")
    for blk in (ou if isinstance(ou, list) else []):
        if not isinstance(blk, dict) or not _is_open(blk.get("status")):
            continue
        line = _num(blk.get("line"))
        if line is None:
            continue
        under = over = None
        for s in (blk.get("selections") or []):
            if not _runner_ok(s):
                continue
            nm = str(s.get("name") or "").lower()
            if "under" in nm:
                under = s
            elif "over" in nm:
                over = s
        out.append({"line": line, "market_id": blk.get("market_id"),
                    "under": under, "over": over})
    out.sort(key=lambda d: d["line"])
    return out


def _cs_cells(payload: dict) -> Tuple[Optional[dict], List[dict]]:
    """Blocco CS OPEN -> (blocco, [runner + 'cell'=(h,a) | 'agg'='home|away|draw'])."""
    blk = payload.get("cs")
    if not isinstance(blk, dict) or not _is_open(blk.get("status")):
        return None, []
    cells: List[dict] = []
    for s in (blk.get("selections") or []):
        if not _runner_ok(s):
            continue
        name = str(s.get("name") or "")
        m = _SCORELINE_RE.match(name)
        if m:
            cells.append({**s, "cell": (int(m.group(1)), int(m.group(2))), "agg": None})
        elif _ANY_OTHER_HOME.search(name):
            cells.append({**s, "cell": None, "agg": "home"})
        elif _ANY_OTHER_AWAY.search(name):
            cells.append({**s, "cell": None, "agg": "away"})
        elif _ANY_OTHER_DRAW.search(name):
            cells.append({**s, "cell": None, "agg": "draw"})
    return blk, cells


def _cell_winner(cell: Optional[Tuple[int, int]], agg: Optional[str]) -> str:
    if agg:
        return agg
    h, a = cell  # type: ignore[misc]
    return "home" if h > a else ("away" if a > h else "draw")


def _ht_score(payload: dict) -> Optional[Tuple[int, int]]:
    """Punteggio al 45' se noto: campi espliciti oppure timeline GOAL coerente
    col punteggio corrente (stesso numero di gol), altrimenti None."""
    hh, ha = payload.get("ht_score_home"), payload.get("ht_score_away")
    if hh is not None and ha is not None:
        return _int(hh), _int(ha)
    tl = payload.get("timeline")
    if not isinstance(tl, list):
        return None
    sh, sa = _int(payload.get("score_home")), _int(payload.get("score_away"))
    home_name = str(payload.get("home") or "").strip().lower()
    goals = [e for e in tl if isinstance(e, dict)
             and str(e.get("type") or "").upper() == "GOAL"]
    if len(goals) != sh + sa:
        return None                     # timeline incompleta: non fidarsi
    h = a = 0
    for e in goals:
        if _int(e.get("minute"), 999) > 45:
            continue
        team = str(e.get("team") or e.get("side") or "").strip().lower()
        if not team:
            return None                 # squadra ignota: esito 1T non ricostruibile
        if team in ("home", "casa") or (home_name and team == home_name):
            h += 1
        else:
            a += 1
    return h, a


# ------------------------------------------------------------------ builder
class _Ctx:
    """Stato dell'evento + accumulatore delle anomalie validate."""

    def __init__(self, payload: dict, book: Dict[str, float], params: Dict[str, Any]) -> None:
        self.p = params
        self.payload = payload
        self.book = book
        self.minute = _int(payload.get("minute"))
        self.sh = _int(payload.get("score_home"))
        self.sa = _int(payload.get("score_away"))
        self.score = f"{self.sh}-{self.sa}"
        self.out: List[dict] = []

    def emit(self, *, rule: str, market_type: str, market_name: str, line: Optional[float],
             market_id: Any, runner: dict, side: str, p_model: float, p_implied: Optional[float],
             confidence: float, gap: float, ref: str, why: str) -> None:
        """Valida prezzo/size/edge/ev/veto e accoda l'anomalia."""
        p = self.p
        price = _price(runner.get("back") if side == "back" else runner.get("lay"))
        if price is None:
            return
        size = _size(runner.get("back_size") if side == "back" else runner.get("lay_size"))
        if size < float(p["min_size"]):
            return
        if side == "lay" and price > float(p["max_lay_price"]):
            return
        p_model = max(0.0, min(1.0, p_model))
        edge = _edge(side, price, p_model)
        if edge < float(p["min_edge"]):
            return
        comm = float(p["commission"])
        ev = _ev(side, price, p_model, comm)
        if ev <= 0:
            return
        key = runner.get("prob_key")
        if p.get("book_veto") and key and key in self.book:
            pb = _num(self.book.get(key))
            if pb is not None and _ev(side, price, pb, comm) <= 0:
                return                  # il modello dice EV<=0: non e' un'anomalia
        name = str(runner.get("name") or "")
        head = f"{name} {side} {price:.2f}"
        sid = runner.get("selection_id")
        self.out.append({
            "kind": "anomaly", "rule": rule,
            "market_type": market_type, "market_name": market_name, "line": line,
            "market_id": market_id,
            "selection_id": int(sid) if sid is not None else None,
            "selection_name": name, "side": side,
            "price": round(price, 4), "size_available": round(size, 2),
            "p_model": round(p_model, 6),
            "p_implied": round(p_implied if p_implied is not None else 1.0 / price, 6),
            "edge": round(edge, 6), "ev": round(ev, 6),
            "confidence": round(float(confidence), 4),
            "gap": round(gap, 6), "ref": ref,
            "rationale": (f"{head} {why} sul {self.score} al {self.minute}': "
                          f"edge {_pct(edge)}, {size:.0f} EUR abbinabili"),
            "minute": self.minute, "score": self.score,
        })


# ------------------------------------------------------------------- regole
def _rule_ou_ladder(ctx: _Ctx, lines: List[dict]) -> None:
    p = ctx.p
    gap_min = float(p["min_gap"])
    conf = float(p["conf_ladder"])
    for hi in lines:
        for lo in lines:
            if lo["line"] >= hi["line"]:
                continue
            # --- UNDER: P(Under hi) >= P(Under lo) -> back(Under hi) <= back(Under lo)
            u_lo, u_hi = lo["under"], hi["under"]
            if u_lo and u_hi:
                ref = _price(u_lo.get("back"))
                cur = _price(u_hi.get("back"))
                if ref and cur and cur >= (1.0 + gap_min) * ref:
                    ctx.emit(rule="ou_ladder", market_type="OVER_UNDER",
                             market_name=f"Over/Under {hi['line']}", line=hi["line"],
                             market_id=hi["market_id"],
                             runner={**u_hi, "prob_key": f"under_{_line_key(hi['line'])}"},
                             side="back", p_model=1.0 / ref, p_implied=1.0 / cur,
                             confidence=conf, gap=cur / ref - 1.0,
                             ref=f"Under {lo['line']} back {ref:.2f}",
                             why=(f"con Under {lo['line']} a {ref:.2f}: quota incoerente, "
                                  f"{_pct(cur / ref - 1.0)}"))
                # lay(Under lo) sotto il back(Under hi): P(Under lo) <= 1/back(Under hi)
                lay_lo = _price(u_lo.get("lay"))
                if lay_lo and cur and lay_lo * (1.0 + gap_min) <= cur:
                    ctx.emit(rule="ou_ladder", market_type="OVER_UNDER",
                             market_name=f"Over/Under {lo['line']}", line=lo["line"],
                             market_id=lo["market_id"],
                             runner={**u_lo, "prob_key": f"under_{_line_key(lo['line'])}"},
                             side="lay", p_model=1.0 / cur, p_implied=1.0 / lay_lo,
                             confidence=conf, gap=cur / lay_lo - 1.0,
                             ref=f"Under {hi['line']} back {cur:.2f}",
                             why=(f"con Under {hi['line']} back a {cur:.2f}: lay incoerente, "
                                  f"{_pct(cur / lay_lo - 1.0)}"))
            # --- OVER: P(Over lo) >= P(Over hi) -> back(Over lo) <= back(Over hi)
            o_lo, o_hi = lo["over"], hi["over"]
            if o_lo and o_hi:
                ref = _price(o_hi.get("back"))
                cur = _price(o_lo.get("back"))
                if ref and cur and cur >= (1.0 + gap_min) * ref:
                    ctx.emit(rule="ou_ladder", market_type="OVER_UNDER",
                             market_name=f"Over/Under {lo['line']}", line=lo["line"],
                             market_id=lo["market_id"],
                             runner={**o_lo, "prob_key": f"over_{_line_key(lo['line'])}"},
                             side="back", p_model=1.0 / ref, p_implied=1.0 / cur,
                             confidence=conf, gap=cur / ref - 1.0,
                             ref=f"Over {hi['line']} back {ref:.2f}",
                             why=(f"con Over {hi['line']} a {ref:.2f}: quota incoerente, "
                                  f"{_pct(cur / ref - 1.0)}"))
                # lay(Over hi) sotto il back(Over lo): P(Over hi) <= 1/back(Over lo)
                lay_hi = _price(o_hi.get("lay"))
                if lay_hi and cur and lay_hi * (1.0 + gap_min) <= cur:
                    ctx.emit(rule="ou_ladder", market_type="OVER_UNDER",
                             market_name=f"Over/Under {hi['line']}", line=hi["line"],
                             market_id=hi["market_id"],
                             runner={**o_hi, "prob_key": f"over_{_line_key(hi['line'])}"},
                             side="lay", p_model=1.0 / cur, p_implied=1.0 / lay_hi,
                             confidence=conf, gap=cur / lay_hi - 1.0,
                             ref=f"Over {lo['line']} back {cur:.2f}",
                             why=(f"con Over {lo['line']} back a {cur:.2f}: lay incoerente, "
                                  f"{_pct(cur / lay_hi - 1.0)}"))


def _emit_decided(ctx: _Ctx, *, market_type: str, market_name: str, line: Optional[float],
                  market_id: Any, runner: dict, won: bool, why: str) -> None:
    """Esito gia' deciso: back del vincitore sopra decided_min_price, lay del perdente."""
    p = ctx.p
    conf = float(p["conf_decided"])
    if won:
        back = _price(runner.get("back"))
        if back and back > float(p["decided_min_price"]) + _EPS:
            ctx.emit(rule="decided", market_type=market_type, market_name=market_name,
                     line=line, market_id=market_id, runner=runner, side="back",
                     p_model=1.0, p_implied=1.0 / back, confidence=conf,
                     gap=back - 1.0, ref="punteggio", why=why)
    else:
        lay = _price(runner.get("lay"))
        if lay:
            ctx.emit(rule="decided", market_type=market_type, market_name=market_name,
                     line=line, market_id=market_id, runner=runner, side="lay",
                     p_model=0.0, p_implied=1.0 / lay, confidence=conf,
                     gap=1.0 / lay, ref="punteggio", why=why)


def _rule_decided(ctx: _Ctx, lines: List[dict], cs_cells: List[dict],
                  cs_blk: Optional[dict]) -> None:
    goals = ctx.sh + ctx.sa
    # O/U: con goals > linea l'Over e' VINTO e l'Under PERSO (l'Under si decide solo al 90')
    for ln in lines:
        if goals <= ln["line"]:
            continue
        why = f"gia' deciso ({goals} gol segnati)"
        k = _line_key(ln["line"])
        mname = f"Over/Under {ln['line']}"
        if ln["over"]:
            _emit_decided(ctx, market_type="OVER_UNDER", market_name=mname, line=ln["line"],
                          market_id=ln["market_id"],
                          runner={**ln["over"], "prob_key": f"over_{k}"}, won=True, why=why)
        if ln["under"]:
            _emit_decided(ctx, market_type="OVER_UNDER", market_name=mname, line=ln["line"],
                          market_id=ln["market_id"],
                          runner={**ln["under"], "prob_key": f"under_{k}"}, won=False, why=why)
    # Gol/NoGol: entrambe a segno -> Si' vinto, No perso
    blk = ctx.payload.get("btts")
    if ctx.sh > 0 and ctx.sa > 0 and isinstance(blk, dict) and _is_open(blk.get("status")):
        why = "gia' deciso (entrambe a segno)"
        for s in (blk.get("selections") or []):
            if not _runner_ok(s):
                continue
            nm = str(s.get("name") or "").strip().lower()
            if nm in ("yes", "si", "si'"):
                _emit_decided(ctx, market_type="BOTH_TEAMS_TO_SCORE", market_name="Gol/NoGol",
                              line=None, market_id=blk.get("market_id"),
                              runner={**s, "prob_key": "btts_yes"}, won=True, why=why)
            elif nm == "no":
                _emit_decided(ctx, market_type="BOTH_TEAMS_TO_SCORE", market_name="Gol/NoGol",
                              line=None, market_id=blk.get("market_id"),
                              runner={**s, "prob_key": "btts_no"}, won=False, why=why)
    # CORRECT SCORE: celle sotto il punteggio corrente sono impossibili -> lay a quota bassa
    for c in cs_cells:
        cell = c.get("cell")
        if cell is None:
            continue
        h, a = cell
        if h < ctx.sh or a < ctx.sa:
            _emit_decided(ctx, market_type="CORRECT_SCORE", market_name="Risultato esatto",
                          line=None, market_id=(cs_blk or {}).get("market_id"),
                          runner={**c, "prob_key": f"cs_{h}_{a}"}, won=False,
                          why=f"impossibile sul {ctx.score}")


def _rule_mo_cs(ctx: _Ctx, cs_cells: List[dict]) -> None:
    p = ctx.p
    payload = ctx.payload
    odds = payload.get("odds")
    if not isinstance(odds, dict) or not _is_open(payload.get("mo_status")):
        return
    priced = [(c, _price(c.get("back"))) for c in cs_cells]
    priced = [(c, b) for c, b in priced if b is not None]
    if len(priced) < int(p["cs_min_runners"]):
        return
    inv_sum = sum(1.0 / b for _, b in priced)
    lo, hi = p["cs_book_range"]
    if not (float(lo) <= inv_sum <= float(hi)):
        return                          # CS incompleto o folle: confronto inaffidabile
    cs_p = {"home": 0.0, "draw": 0.0, "away": 0.0}
    for c, b in priced:
        cs_p[_cell_winner(c["cell"], c["agg"])] += (1.0 / b) / inv_sum
    names = {"home": payload.get("home") or "Casa", "draw": "The Draw",
             "away": payload.get("away") or "Trasferta"}
    runners = []
    for side_k in ("home", "draw", "away"):
        pair = odds.get(side_k)
        if isinstance(pair, dict):
            runners.append({**pair, "name": names[side_k], "prob_key": side_k,
                            "runner_status": "ACTIVE"})
    mo_p = _devig(runners)
    if len(mo_p) < 3:
        return
    gap_min = float(p["mo_cs_gap"])
    labels = {"home": "1", "draw": "X", "away": "2"}
    for r in runners:
        k = r["prob_key"]
        pm, pc = mo_p[id(r)], cs_p[k]
        gap = pc - pm
        if abs(gap) < gap_min:
            continue
        side = "back" if gap > 0 else "lay"
        ctx.emit(rule="mo_cs", market_type="MATCH_ODDS", market_name="1X2", line=None,
                 market_id=payload.get("mo_market_id"), runner=r, side=side,
                 p_model=pc, p_implied=pm, confidence=float(p["conf_mo_cs"]),
                 gap=gap, ref=f"CS P({labels[k]})={pc * 100:.1f}%",
                 why=(f"1X2 da' {pm * 100:.1f}% ma il Risultato esatto implica "
                      f"{pc * 100:.1f}% ({_pct(gap)})"))


def _rule_ht_open(ctx: _Ctx) -> None:
    payload = ctx.payload
    blk = payload.get("ht_result")
    if ctx.minute < 46 or not isinstance(blk, dict) or not _is_open(blk.get("status")):
        return
    ht = _ht_score(payload)
    if ht is None:
        return
    h, a = ht
    winner = "home" if h > a else ("away" if a > h else "draw")
    home_name = str(payload.get("home") or "").strip().lower()
    away_name = str(payload.get("away") or "").strip().lower()
    for s in (blk.get("selections") or []):
        if not _runner_ok(s):
            continue
        nm = str(s.get("name") or "").strip().lower()
        if "draw" in nm or "pareggio" in nm:
            side_k = "draw"
        elif home_name and nm == home_name:
            side_k = "home"
        elif away_name and nm == away_name:
            side_k = "away"
        else:
            continue
        _emit_decided(ctx, market_type="HALF_TIME", market_name="1X2 primo tempo", line=None,
                      market_id=blk.get("market_id"), runner={**s, "prob_key": f"ht_{side_k}"},
                      won=(side_k == winner),
                      why=f"1T finito {h}-{a}, mercato ancora aperto al {ctx.minute}'")


# ----------------------------------------------------------------------- API
def detect(payload: dict, book: Dict[str, float], *, params: Optional[dict] = None) -> List[dict]:
    """Anomalie di prezzo azionabili per l'evento, ordinate per EV decrescente.

    ``payload``: riga calcio di safe_strategy_scan; ``book``: P del modello
    (solo veto, puo' essere vuoto). Mai eccezioni su blocchi mancanti.
    """
    prm = {**DEFAULT_ANOMALY_PARAMS, **(params or {})}
    if not isinstance(payload, dict):
        return []
    ctx = _Ctx(payload, book if isinstance(book, dict) else {}, prm)
    lines = _ou_lines(payload)
    cs_blk, cs_cells = _cs_cells(payload)
    _rule_decided(ctx, lines, cs_cells, cs_blk)
    _rule_ou_ladder(ctx, lines)
    _rule_mo_cs(ctx, cs_cells)
    _rule_ht_open(ctx)
    # dedup (stesso runner/lato segnalato da piu' regole): tiene l'EV migliore
    best: Dict[Tuple[Any, Any, str], dict] = {}
    for a in ctx.out:
        k = (a["market_id"], a["selection_id"], a["side"])
        if k not in best or a["ev"] > best[k]["ev"]:
            best[k] = a
    out = sorted(best.values(), key=lambda d: (-d["ev"], -d["confidence"]))
    return out[: max(0, int(prm["max_per_event"]))]
