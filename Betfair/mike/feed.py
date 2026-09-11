"""feed — dal payload del FEED UNICO (``safe_strategy_scan``) allo ``Snapshot`` dell'engine.

Logica PURA (testabile senza DB): riceve la riga pubblicata dallo scanner Safe
(ramo pre-KO O/U acceso con ``SAFE_PRE_KO_OU_HOURS``) e ne estrae:
  - ``EventInfo``: nomi, KO, market_id/selection_id delle due linee (risolti PER NOME);
  - ``Snapshot``: book per selezione (best back/lay + size, stato, inplay, betDelay),
    minuto, gol, intervallo, freschezza, P(4) implicita di mercato.

Nessuna chiamata Betfair: Mike legge SOLO il feed (regola dei processi).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from Betfair.stream.trading.xhedge import OVER_UNDER, canonical_selection

from . import config as C
from . import engine as E

_LINE_TO_MARKET = {3.5: E.MARKET_OU35, 4.5: E.MARKET_OU45}


@dataclass(frozen=True)
class EventInfo:
    event_id: str
    event_name: str
    home: Optional[str]
    away: Optional[str]
    competition: Optional[str]
    ko_at: Optional[float]                      # epoch UTC
    open_date: Optional[str]
    markets: Dict[str, str]                     # {"OU35": market_id, "OU45": market_id}
    selections: Dict[Tuple[str, str], int]     # {(market, UNDER|OVER): selection_id}

    @property
    def complete(self) -> bool:
        return (E.MARKET_OU35 in self.markets and E.MARKET_OU45 in self.markets
                and (E.MARKET_OU35, E.SEL_UNDER) in self.selections
                and (E.MARKET_OU45, E.SEL_OVER) in self.selections)

    def market_id(self, market: str) -> Optional[str]:
        return self.markets.get(market)

    def selection_id(self, market: str, selection: str) -> Optional[int]:
        return self.selections.get((market, selection))

    def selection_name(self, market: str, selection: str) -> str:
        line = E.LINE[market]
        return f"{'Under' if selection == E.SEL_UNDER else 'Over'} {line} Goals"


def parse_iso_epoch(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError):
        return None


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def ou_blocks(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{OU35: blocco, OU45: blocco} dalla lista ``ou`` del payload."""
    out: Dict[str, Dict[str, Any]] = {}
    for blk in payload.get("ou") or []:
        if not isinstance(blk, dict):
            continue
        line = _num(blk.get("line"))
        market = _LINE_TO_MARKET.get(line) if line is not None else None
        if market is None:
            continue
        out[market] = blk
    return out


def event_info(event_id: str, payload: Dict[str, Any]) -> EventInfo:
    blocks = ou_blocks(payload)
    markets: Dict[str, str] = {}
    sels: Dict[Tuple[str, str], int] = {}
    for market, blk in blocks.items():
        if blk.get("market_id"):
            markets[market] = str(blk["market_id"])
        for i, s in enumerate(blk.get("selections") or []):
            if not isinstance(s, dict) or s.get("selection_id") is None:
                continue
            canon = canonical_selection(OVER_UNDER, s.get("name"), i + 1)
            if canon in (E.SEL_UNDER, E.SEL_OVER):
                sels[(market, canon)] = int(s["selection_id"])
    return EventInfo(
        event_id=str(event_id),
        event_name=str(payload.get("event_name") or ""),
        home=payload.get("home"), away=payload.get("away"),
        competition=payload.get("competition"),
        ko_at=parse_iso_epoch(payload.get("open_date")),
        open_date=payload.get("open_date"),
        markets=markets, selections=sels,
    )


def _book_for(blk: Optional[Dict[str, Any]], selection_id: Optional[int]) -> Optional[E.Book]:
    if not blk or selection_id is None:
        return None
    for s in blk.get("selections") or []:
        if isinstance(s, dict) and s.get("selection_id") is not None and int(s["selection_id"]) == int(selection_id):
            return E.Book(
                best_back=_num(s.get("back")), back_size=float(_num(s.get("back_size")) or 0.0),
                best_lay=_num(s.get("lay")), lay_size=float(_num(s.get("lay_size")) or 0.0),
                status=str(blk.get("status") or "OPEN").upper(),
                inplay=bool(blk.get("inplay")),
                bet_delay=int(_num(blk.get("bet_delay")) or 0),
            )
    return None


def implied_p4(blocks: Dict[str, Dict[str, Any]], info: EventInfo) -> Optional[float]:
    """P(esattamente 4 gol) implicita dai back devig delle due linee: P(O3.5) - P(O4.5)."""
    def p_over(market: str) -> Optional[float]:
        blk = blocks.get(market)
        bo = _book_for(blk, info.selection_id(market, E.SEL_OVER))
        bu = _book_for(blk, info.selection_id(market, E.SEL_UNDER))
        if bo is None or bu is None or not bo.best_back or not bu.best_back:
            return None
        io, iu = 1.0 / bo.best_back, 1.0 / bu.best_back
        return io / (io + iu) if io + iu > 0 else None
    po35, po45 = p_over(E.MARKET_OU35), p_over(E.MARKET_OU45)
    if po35 is None or po45 is None:
        return None
    return round(max(0.0, po35 - po45), 4)


def ht_active_from_payload(payload: Dict[str, Any]) -> bool:
    raw = payload.get("score_raw") or {}
    status = str(raw.get("matchStatus") or raw.get("match_status") or "").lower()
    if not status:
        return False
    return ("half" in status and "end" in status) or status in ("halftime", "half_time", "ht")


def goals_from_payload(payload: Dict[str, Any]) -> Optional[int]:
    h, a = payload.get("score_home"), payload.get("score_away")
    if h is None or a is None:
        return None
    try:
        return int(h) + int(a)
    except (TypeError, ValueError):
        return None


def feed_fresh(row: Dict[str, Any], now: float, max_age_s: float, scanner_age_s: Optional[float],
               scanner_alive_max_s: float = 30.0) -> bool:
    """Riga fresca (età ≤ max_age) OPPURE scanner vivo (write-on-change: riga
    immutata = nulla e' cambiato) — stessa regola di scan_feed.fresh_payload."""
    age = None
    ts = parse_iso_epoch(row.get("updated_at"))
    if ts is not None:
        age = now - ts
    if age is not None and age <= max_age_s:
        return True
    return scanner_age_s is not None and scanner_age_s <= scanner_alive_max_s


def snapshot_from_row(row: Dict[str, Any], info: EventInfo, *, now: float, params: Dict[str, Any],
                      scanner_age_s: Optional[float], hazard: Optional[float] = None,
                      p4_model: Optional[float] = None, last_goal_ts: Optional[float] = None,
                      market_status_override: Optional[str] = None,
                      cover_gain_pct: Optional[float] = None, pressure: float = 1.0,
                      model_probs: Optional[Dict[str, float]] = None,
                      p_total_model: Optional[Dict[int, float]] = None,
                      p_total_emp: Optional[Dict[int, float]] = None) -> Optional[E.Snapshot]:
    payload = row.get("payload") if isinstance(row, dict) else None
    if not isinstance(payload, dict) or info.ko_at is None:
        return None
    blocks = ou_blocks(payload)
    books: Dict[Tuple[str, str], E.Book] = {}
    for key in ((E.MARKET_OU35, E.SEL_UNDER), (E.MARKET_OU45, E.SEL_OVER), (E.MARKET_OU45, E.SEL_UNDER)):
        bk = _book_for(blocks.get(key[0]), info.selection_id(*key))
        if bk is not None:
            books[key] = bk
    blk35 = blocks.get(E.MARKET_OU35) or {}
    inplay = bool(payload.get("inplay")) or bool(blk35.get("inplay"))
    status = market_status_override or str(blk35.get("status") or payload.get("mo_status") or "OPEN").upper()
    return E.Snapshot(
        now=float(now), ko_at=float(info.ko_at), books=books, inplay=inplay,
        minute=payload.get("minute") if isinstance(payload.get("minute"), int) else None,
        goals=goals_from_payload(payload),
        ht_active=ht_active_from_payload(payload),
        feed_fresh=feed_fresh(row, now, float(params["feed_max_age_s"]), scanner_age_s),
        hazard=hazard, p4_market=implied_p4(blocks, info), p4_model=p4_model,
        last_goal_ts=last_goal_ts, market_status=status, final_total=None,
        cover_gain_pct=cover_gain_pct, pressure=float(pressure or 1.0), model_probs=model_probs,
        p_total_model=p_total_model, p_total_emp=p_total_emp,
    )


def is_candidate(info: EventInfo, payload: Dict[str, Any], *, now: float, params: Dict[str, Any]) -> bool:
    """Partita da seguire ADESSO: entrambe le linee nel feed e KO entro la finestra
    (o gia' in corso). Il filtro per competizione e liquidita' vive in config."""
    if not info.complete or info.ko_at is None:
        return False
    comp_filter = [s.strip().lower() for s in str(params.get("competition_filter") or "").split(",") if s.strip()]
    if comp_filter and not any(f in str(info.competition or "").lower() for f in comp_filter):
        return False
    if bool(payload.get("inplay")):
        return True
    return 0 < info.ko_at - now <= float(params["entry_hours_before_ko"]) * 3600.0
