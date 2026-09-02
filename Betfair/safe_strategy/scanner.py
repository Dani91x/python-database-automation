"""scanner.py — logica PURA dello scanner Safe Strategy (testabile senza rete).

Qui vivono le decisioni "di testa": mappatura selezioni, finestre di interesse,
cadenze adattive, congelamento del riferimento pre-KO, firma write-on-change.
Il glue di rete/DB sta in service.py; NESSUNA valutazione di strategia qui
(quella è del motore certificato frontend, lib/safeStrategy.ts).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# finestre di interesse (minuti EFFETTIVI di gioco, come certificato):
# le strategie calcio vivono tra il 48' e il 70' — fuori da lì lo scanner
# rallenta per non sprecare peso API Betfair.
HOT_MINUTE_FROM = 40
HOT_MINUTE_TO = 78
# candidati Correct Score (strategia Risultato Esatto: finestra 48-50' +
# margine per parametri utente e latenze)
CS_MINUTE_FROM = 40
CS_MINUTE_TO = 60
CS_MAX_GOALS_SIDE = 2
# cattura pre-KO: da KO-15' fino al kickoff
PRE_KO_WINDOW_SEC = 15 * 60

_ANY_OTHER_HOME = re.compile(r"any\s*other.*home", re.IGNORECASE)
_ANY_OTHER_AWAY = re.compile(r"any\s*other.*away", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def best_price(levels: Any) -> Optional[float]:
    try:
        return float(levels[0].price) if levels else None
    except Exception:  # noqa: BLE001 - struttura inattesa = prezzo assente
        return None


def selection_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Mappa home/away/draw → selection_id dal catalogo MATCH_ODDS calcio.

    Regola Betfair: sort_priority 1 = casa, 2 = trasferta, 3 = pareggio.
    Fallback sul nome 'The Draw' se i sort mancano.
    """
    by_sort: Dict[int, int] = {}
    draw_by_name: Optional[int] = None
    for r in runners:
        sid = r.get("selection_id")
        if sid is None:
            continue
        sp = r.get("sort_priority")
        if isinstance(sp, int):
            by_sort[sp] = int(sid)
        name = str(r.get("name") or "").strip().lower()
        if name == "the draw":
            draw_by_name = int(sid)
    return {
        "home": by_sort.get(1),
        "away": by_sort.get(2),
        "draw": by_sort.get(3, draw_by_name),
    }


def tennis_sides(runners: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """p1/p2 → selection_id (sort_priority 1/2) dal catalogo MATCH_ODDS tennis."""
    by_sort: Dict[int, int] = {}
    for r in runners:
        sid = r.get("selection_id")
        sp = r.get("sort_priority")
        if sid is not None and isinstance(sp, int):
            by_sort[sp] = int(sid)
    return {"p1": by_sort.get(1), "p2": by_sort.get(2)}


def split_event_name(event_name: Optional[str]) -> "tuple[Optional[str], Optional[str]]":
    """'Casa v Ospite' → (Casa, Ospite); None se la forma non è riconoscibile."""
    if not event_name:
        return None, None
    for sep in (" v ", " vs ", " @ "):
        if sep in event_name:
            a, b = event_name.split(sep, 1)
            return a.strip() or None, b.strip() or None
    return None, None


def is_cs_candidate(minute: Optional[int], score_home: Optional[int], score_away: Optional[int]) -> bool:
    """Evento per cui vale la pena interrogare il mercato Correct Score."""
    if minute is None or score_home is None or score_away is None:
        return False
    if not (CS_MINUTE_FROM <= minute <= CS_MINUTE_TO):
        return False
    return score_home <= CS_MAX_GOALS_SIDE and score_away <= CS_MAX_GOALS_SIDE


def in_pre_ko_window(open_date: Optional[str], now: datetime) -> bool:
    ko = parse_iso(open_date)
    if ko is None:
        return False
    delta = (ko - now).total_seconds()
    return 0 < delta <= PRE_KO_WINDOW_SEC


def is_monitorable(inplay: bool, open_date: Optional[str], now: datetime) -> bool:
    """Riga da pubblicare: evento in-play oppure con KO entro la finestra pre-KO."""
    return inplay or in_pre_ko_window(open_date, now)


def freeze_pre_ko(
    prev: Optional[Dict[str, Any]],
    inplay: bool,
    odds: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Riferimento 1X2 pre-KO: si AGGIORNA solo prima del kickoff (closing line),
    si CONGELA per sempre al primo tick in-play. Mai quote in-play nel riferimento.
    """
    if inplay:
        return prev
    if not odds:
        return prev
    triple = {}
    for side in ("home", "draw", "away"):
        pair = odds.get(side) or {}
        back = pair.get("back")
        if not isinstance(back, (int, float)):
            return prev  # riferimento solo se il 1X2 è completo
        triple[side] = float(back)
    return {**triple, "captured_at": now_iso()}


def books_period_calcio(any_inplay: bool, any_hot: bool) -> float:
    """Cadenza (s) del poll quote MATCH_ODDS calcio: fitta solo quando serve."""
    if any_hot:
        return 10.0
    if any_inplay:
        return 20.0
    return 60.0


def books_period_tennis(any_inplay: bool) -> float:
    return 10.0 if any_inplay else 60.0


def payload_signature(payload: Dict[str, Any]) -> str:
    """Firma stabile del payload per il write-on-change (niente updated_at qui)."""
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.md5(canon.encode("utf-8")).hexdigest()


def build_cs_block(
    market_id: Optional[str],
    status: Optional[str],
    selections: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Blocco Correct Score del payload: solo le selezioni 'Any Other …'."""
    if market_id is None:
        return None
    any_home = any_away = None
    for s in selections:
        name = str(s.get("name") or "")
        pair = {"back": s.get("back"), "lay": s.get("lay")}
        if _ANY_OTHER_HOME.search(name):
            any_home = pair
        elif _ANY_OTHER_AWAY.search(name):
            any_away = pair
    return {
        "market_id": market_id,
        "status": status,
        "any_other_home": any_home,
        "any_other_away": any_away,
    }
