"""xhedge.py — hedging CROSS-MARKET correlato via modello SCORELINE (punto #9).

Nel calcio quasi tutti i mercati sono FUNZIONE del risultato finale (gol casa, gol trasferta):
Match Odds, Over/Under, BTTS, Correct Score sono tutti risolvibili da (h, a). Se hai posizioni
su PIÙ mercati correlati, il tuo P&L NETTO dipende dal risultato: qui lo calcoliamo per OGNI
scoreline della griglia, esponendo la vera esposizione cross-market (cosa che nessun tool pro
mostra) e suggerendo una copertura a gamba singola sul Correct Score per alzare il worst-case.

⚠️ Money-critical ma NON auto-piazzante: qui è SOLO aritmetica pura (nessun ordine). Il worker/UI
usa ``pnl_by_scoreline`` per mostrare la matrice e ``suggest_cs_hedge`` per proporre l'hedge; il
piazzamento passa dalla coda ordini normale (back sul Correct Score suggerito). Nessun netting
"magico": ogni numero è derivato dalle regole esatte di risoluzione dei mercati.

Convenzioni P&L per posizione su un dato scoreline:
    back size S @ quota O:  +S·(O−1) se la selezione VINCE, altrimenti −S.
    lay  size S @ quota O:  −S·(O−1) se la selezione VINCE, altrimenti +S.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Tipi di mercato supportati (chiavi canoniche).
MATCH_ODDS = "MATCH_ODDS"
OVER_UNDER = "OVER_UNDER"          # richiede ``line`` (es. 2.5)
BTTS = "BOTH_TEAMS_TO_SCORE"
CORRECT_SCORE = "CORRECT_SCORE"

_EPS = 1e-9


@dataclass(frozen=True)
class XPosition:
    """Una posizione MATCHED su un mercato correlato."""

    market_type: str            # MATCH_ODDS | OVER_UNDER | BOTH_TEAMS_TO_SCORE | CORRECT_SCORE
    selection: str              # HOME/DRAW/AWAY | OVER/UNDER | YES/NO | "h-a"
    side: str                   # 'back' | 'lay'
    size: float                 # stake matched (>0)
    odds: float                 # quota di abbinamento (>1)
    line: Optional[float] = None  # solo OVER_UNDER (es. 2.5)


# ---------------------------------------------------------------------------
# Risoluzione: la selezione VINCE nello scoreline (h, a)?
# ---------------------------------------------------------------------------
def selection_wins(market_type: str, selection: str, h: int, a: int, line: Optional[float] = None) -> bool:
    mt = (market_type or "").upper()
    sel = (selection or "").upper().strip()
    if mt == MATCH_ODDS:
        if sel in ("HOME", "1", "H"):
            return h > a
        if sel in ("AWAY", "2", "A"):
            return h < a
        if sel in ("DRAW", "X", "D"):
            return h == a
        raise ValueError(f"selezione MATCH_ODDS non valida: {selection!r}")
    if mt in (OVER_UNDER, "OVER_UNDER_25", "OVER/UNDER"):
        if line is None:
            raise ValueError("OVER_UNDER richiede line")
        total = h + a
        if sel.startswith("OVER") or sel == "O":
            return total > float(line)
        if sel.startswith("UNDER") or sel == "U":
            return total < float(line)
        raise ValueError(f"selezione OVER_UNDER non valida: {selection!r}")
    if mt in (BTTS, "BTTS"):
        yes = h >= 1 and a >= 1
        if sel in ("YES", "Y"):
            return yes
        if sel in ("NO", "N"):
            return not yes
        raise ValueError(f"selezione BTTS non valida: {selection!r}")
    if mt in (CORRECT_SCORE, "CS"):
        try:
            sh, sa = (int(x) for x in sel.replace(":", "-").split("-"))
        except (ValueError, AttributeError):
            raise ValueError(f"selezione CORRECT_SCORE non valida: {selection!r}")
        return h == sh and a == sa
    raise ValueError(f"market_type non supportato: {market_type!r}")


def position_pnl(pos: XPosition, h: int, a: int) -> float:
    """P&L della posizione se il risultato finale è (h, a)."""
    win = selection_wins(pos.market_type, pos.selection, h, a, pos.line)
    s = float(pos.size)
    o = float(pos.odds)
    if (pos.side or "").lower() == "lay":
        return round(-s * (o - 1.0) if win else s, 2)
    return round(s * (o - 1.0) if win else -s, 2)


# ---------------------------------------------------------------------------
# Matrice P&L per scoreline
# ---------------------------------------------------------------------------
def pnl_by_scoreline(positions: Sequence[XPosition], max_goals: int = 8) -> Dict[Tuple[int, int], float]:
    """{(h,a): P&L netto} su tutta la griglia 0..max_goals × 0..max_goals.

    Somma il contributo di OGNI posizione a OGNI scoreline. La griglia copre i risultati
    realistici; punteggi oltre ``max_goals`` (probabilità trascurabile) NON sono inclusi —
    il chiamante lo sa e ragiona sul range coperto.
    """
    grid: Dict[Tuple[int, int], float] = {}
    for h in range(0, max_goals + 1):
        for a in range(0, max_goals + 1):
            total = 0.0
            for pos in positions:
                total += position_pnl(pos, h, a)
            grid[(h, a)] = round(total, 2)
    return grid


@dataclass(frozen=True)
class ExposureSummary:
    worst: float
    best: float
    mean: float
    worst_scoreline: Tuple[int, int]
    best_scoreline: Tuple[int, int]
    n_scorelines: int


def exposure_summary(grid: Dict[Tuple[int, int], float]) -> ExposureSummary:
    """Sintesi dell'esposizione cross-market: peggiore/migliore/media + gli scoreline estremi."""
    if not grid:
        return ExposureSummary(0.0, 0.0, 0.0, (0, 0), (0, 0), 0)
    items = list(grid.items())
    worst_sl, worst = min(items, key=lambda kv: kv[1])
    best_sl, best = max(items, key=lambda kv: kv[1])
    mean = sum(v for _, v in items) / len(items)
    return ExposureSummary(
        worst=round(worst, 2), best=round(best, 2), mean=round(mean, 2),
        worst_scoreline=worst_sl, best_scoreline=best_sl, n_scorelines=len(items),
    )


# ---------------------------------------------------------------------------
# Suggerimento hedge a gamba singola sul Correct Score (alza il worst-case)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HedgeSuggestion:
    """Copertura suggerita: BACK sul Correct Score dello scoreline peggiore per alzare il floor."""

    actionable: bool
    scoreline: Optional[Tuple[int, int]]
    side: Optional[str]          # 'back' (copertura standard del worst-case)
    odds: Optional[float]
    size: Optional[float]
    new_worst: float
    new_best: float
    note: str


def suggest_cs_hedge(
    grid: Dict[Tuple[int, int], float],
    cs_back_odds: Dict[Tuple[int, int], float],
    *,
    max_size: Optional[float] = None,
) -> HedgeSuggestion:
    """Suggerisce UN back sul Correct Score dello scoreline PEGGIORE per alzarne il P&L verso il
    resto della distribuzione (riduce il worst-case).

    Backando lo scoreline peggiore w con size x @ quota O_w:
        nuovo P&L(w)      = P&L(w) + x·(O_w−1)
        nuovo P&L(altri s)= P&L(s) − x
    La size ottimale porta il worst-case verso il MINIMO degli ALTRI scoreline (oltre il quale
    continuare non aiuta, perché backare w abbassa tutti gli altri). x* = (m − P&L(w))/(O_w−1 + 1)
    dove m = min P&L sugli altri scoreline, cioè x* = (m − P&L(w))/O_w (perché il worst sale di
    x·(O_w−1) mentre gli altri scendono di x → si incontrano quando P&L(w)+x·(O_w−1) = m − x).
    Se non serve (già bilanciato) o manca la quota → non azionabile.
    """
    if not grid:
        return HedgeSuggestion(False, None, None, None, None, 0.0, 0.0, "nessuna posizione")
    summary = exposure_summary(grid)
    w = summary.worst_scoreline
    pnl_w = grid[w]
    others = [v for k, v in grid.items() if k != w]
    if not others:
        return HedgeSuggestion(False, None, None, None, summary.worst, summary.best, "griglia 1×1")
    m_others = min(others)
    # già bilanciato: il worst non è (strettamente) il punto più basso da alzare.
    if pnl_w >= m_others - 0.01:
        return HedgeSuggestion(False, w, None, None, None, summary.worst, summary.best,
                               "worst-case già allineato al resto: nessuna copertura utile")
    odds = cs_back_odds.get(w)
    if odds is None or not math.isfinite(odds) or odds <= 1.0:
        return HedgeSuggestion(False, w, None, None, None, summary.worst, summary.best,
                               f"quota Correct Score {w} non disponibile per la copertura")
    # x* dove worst sale e min-altri scende fino a incontrarsi: P&L(w)+x(O-1) = m_others - x
    x = (m_others - pnl_w) / odds
    if max_size is not None and max_size > 0:
        x = min(x, float(max_size))
    x = round(x, 2)
    if x <= 0:
        return HedgeSuggestion(False, w, None, None, None, summary.worst, summary.best,
                               "size copertura → 0")
    # ricalcola worst/best dopo la copertura
    new_grid = {k: (v + x * (odds - 1.0) if k == w else v - x) for k, v in grid.items()}
    ns = exposure_summary(new_grid)
    return HedgeSuggestion(
        True, w, "back", odds, x, ns.worst, ns.best,
        f"BACK Correct Score {w[0]}-{w[1]} {x:.2f}@{odds}: worst {summary.worst:.2f}→{ns.worst:.2f}",
    )


# ---------------------------------------------------------------------------
# Mapper catalogo Betfair → selezione canonica (per costruire XPosition dai dati live)
# ---------------------------------------------------------------------------
# Tipi di mercato Betfair supportati → tipo canonico.
_MO_TYPES = {"MATCH_ODDS"}
_BTTS_TYPES = {"BOTH_TEAMS_TO_SCORE"}
_CS_TYPES = {"CORRECT_SCORE"}
_OU_RE = re.compile(r"OVER_UNDER_(\d+)")   # es. OVER_UNDER_25 → linea 2.5


def canonical_market(market_type: str) -> Optional[Tuple[str, Optional[float]]]:
    """(tipo_canonico, line) da un market_type Betfair, o None se non gestito.
    OVER_UNDER_25 → (OVER_UNDER, 2.5); MATCH_ODDS → (MATCH_ODDS, None); ecc."""
    mt = (market_type or "").upper()
    if mt in _MO_TYPES:
        return MATCH_ODDS, None
    if mt in _BTTS_TYPES:
        return BTTS, None
    if mt in _CS_TYPES:
        return CORRECT_SCORE, None
    m = _OU_RE.fullmatch(mt)
    if m:
        return OVER_UNDER, int(m.group(1)) / 10.0
    return None


def canonical_selection(canon_type: str, runner_name: Optional[str], sort_priority: Optional[int]) -> Optional[str]:
    """Selezione canonica (HOME/DRAW/AWAY | OVER/UNDER | YES/NO | 'h-a') dal nome runner Betfair.
    None se non mappabile (es. 'Any Other Home Win' nel Correct Score → si ignora)."""
    name = (runner_name or "").strip()
    low = name.lower()
    if canon_type == MATCH_ODDS:
        if "draw" in low:
            return "DRAW"
        if sort_priority == 1:
            return "HOME"
        if sort_priority == 2:
            return "AWAY"
        return None
    if canon_type == OVER_UNDER:
        if low.startswith("over"):
            return "OVER"
        if low.startswith("under"):
            return "UNDER"
        return None
    if canon_type == BTTS:
        if low in ("yes", "y"):
            return "YES"
        if low in ("no", "n"):
            return "NO"
        return None
    if canon_type == CORRECT_SCORE:
        m = re.fullmatch(r"\s*(\d+)\s*[-:]\s*(\d+)\s*", name)
        if m:
            return f"{int(m.group(1))}-{int(m.group(2))}"
        return None  # 'Any Other ...' non mappabile su una scoreline singola
    return None


def build_positions(
    orders: Sequence[Dict[str, Any]],
    market_meta: Dict[str, Dict[str, Any]],
) -> List[XPosition]:
    """Costruisce le XPosition dagli ordini MATCHED live + i metadati mercato.

    ``orders``: righe con market_id, selection_id, side, average_price_matched (o price),
    size_matched (>0). ``market_meta``: {market_id: {"market_type": str,
    "selections": {selection_id: {"name": str, "sort_priority": int}}}}. Ordini su mercati
    non gestiti o selezioni non mappabili sono IGNORATI (degradazione morbida, mai un errore).
    """
    out: List[XPosition] = []
    for o in orders:
        try:
            matched = float(o.get("size_matched") or 0.0)
            if matched <= 0:
                continue
            meta = market_meta.get(str(o.get("market_id")))
            if not meta:
                continue
            cm = canonical_market(meta.get("market_type"))
            if cm is None:
                continue
            canon_type, line = cm
            sel_meta = (meta.get("selections") or {}).get(o.get("selection_id")) \
                or (meta.get("selections") or {}).get(str(o.get("selection_id"))) or {}
            sel = canonical_selection(canon_type, sel_meta.get("name"), sel_meta.get("sort_priority"))
            if sel is None:
                continue
            odds = float(o.get("average_price_matched") or o.get("price") or 0.0)
            if odds <= 1.0:
                continue
            side = (o.get("side") or "").lower()
            if side not in ("back", "lay"):
                continue
            out.append(XPosition(canon_type, sel, side, matched, odds, line))
        except (TypeError, ValueError):
            continue
    return out


def _matched_size(order: Dict[str, Any]) -> float:
    """size_matched difensiva di una riga ordine (0.0 se assente/non numerica)."""
    try:
        return float(order.get("size_matched") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def compute_xhedge(
    orders: Sequence[Dict[str, Any]],
    market_meta: Dict[str, Dict[str, Any]],
    cs_back_odds: Optional[Dict[Tuple[int, int], float]] = None,
    *,
    max_goals: int = 8,
    max_size: Optional[float] = None,
) -> Dict[str, Any]:
    """Analisi cross-market completa da dati live: costruisce le posizioni, la matrice P&L per
    scoreline, la sintesi e (se ci sono quote Correct Score) il suggerimento di copertura.
    Ritorna un dict serializzabile per DB/UI. Nessun I/O."""
    positions = build_positions(orders, market_meta)
    # MONEY-CRITICAL: gli ordini matched NON mappabili (es. "Any Other" del Correct Score,
    # mercati fuori modello) sono esposizione REALE assente dalla matrice. Contarli ed
    # esporli permette alla UI di dichiarare la matrice INCOMPLETA invece di spacciarla
    # per esatta (senza contatore ogni cella sarebbe silenziosamente sbagliata).
    n_matched_input = sum(1 for o in orders if _matched_size(o) > 0)
    ignored_orders = max(0, n_matched_input - len(positions))
    grid = pnl_by_scoreline(positions, max_goals=max_goals)
    summary = exposure_summary(grid)
    suggestion = None
    if cs_back_odds:
        sug = suggest_cs_hedge(grid, cs_back_odds, max_size=max_size)
        suggestion = {
            "actionable": sug.actionable, "scoreline": list(sug.scoreline) if sug.scoreline else None,
            "side": sug.side, "odds": sug.odds, "size": sug.size,
            "new_worst": sug.new_worst, "new_best": sug.new_best, "note": sug.note,
        }
    return {
        "n_positions": len(positions),
        # > 0 ⟹ la matrice è INCOMPLETA: esposizione matched reale non modellata (la UI
        # DEVE mostrare un avviso, mai presentare la griglia come esatta).
        "ignored_orders": ignored_orders,
        "summary": {
            "worst": summary.worst, "best": summary.best, "mean": summary.mean,
            "worst_scoreline": list(summary.worst_scoreline),
            "best_scoreline": list(summary.best_scoreline), "n_scorelines": summary.n_scorelines,
        },
        # griglia come lista compatta [[h,a,pnl],...] solo per gli scoreline con P&L ≠ 0 vicino agli estremi
        "grid": [[h, a, v] for (h, a), v in grid.items()],
        "suggestion": suggestion,
    }
