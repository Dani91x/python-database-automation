"""catalogue — catalogo giornaliero O/U 3.5 + 4.5, ranking e budget mercati.

UNA sola chiamata ``listMarketCatalogue`` per refresh (TTL nel service), con
filtro ``marketTypeCodes=[OVER_UNDER_35, OVER_UNDER_45]`` e finestra di
``marketStartTime``; niente altro. Le selezioni sono risolte PER NOME
(``Under 3.5 Goals`` / ``Over 4.5 Goals``): gli id attesi in ``config.EXPECTED_SEL``
sono usati solo per un WARN, mai per decidere.

Tutta la logica e' pura (input: dict nel formato JSON di Betfair, come li
restituisce betfairlightweight con ``lightweight=True``); l'unica funzione con
rete e' ``fetch_day_markets``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from Betfair.stream.limits import BudgetVerdict, check_market_budget
from Betfair.stream.trading.xhedge import OVER_UNDER, canonical_selection

from . import config as C

_TYPE_BY_NAME = {"over/under 3.5 goals": C.OU35, "over/under 4.5 goals": C.OU45}
_KEY_BY_TYPE = {C.OU35: "OU35", C.OU45: "OU45"}


@dataclass(frozen=True)
class MarketRef:
    market_id: str
    market_type: str
    under_sel: int
    over_sel: int
    total_matched: float


@dataclass(frozen=True)
class EventMarkets:
    event_id: str
    event_name: str
    competition: str
    competition_id: str
    ko_at: datetime
    ou35: MarketRef
    ou45: MarketRef

    @property
    def total_matched(self) -> float:
        return round(float(self.ou35.total_matched) + float(self.ou45.total_matched), 2)

    @property
    def market_ids(self) -> List[str]:
        return [self.ou35.market_id, self.ou45.market_id]

    def selection_key(self, market_id: str, selection_id: int) -> Optional[Tuple[str, str]]:
        """(MARKET, SELECTION) dell'engine da (market_id, selection_id), o None."""
        for key, ref in (("OU35", self.ou35), ("OU45", self.ou45)):
            if ref.market_id != str(market_id):
                continue
            if int(selection_id) == ref.under_sel:
                return (key, "UNDER")
            if int(selection_id) == ref.over_sel:
                return (key, "OVER")
        return None


@dataclass
class Selection:
    events: List[EventMarkets]
    n_markets: int
    verdict: BudgetVerdict
    dropped_liquidity: List[str] = field(default_factory=list)
    dropped_cap: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _parse_dt(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _market_type(m: Dict[str, Any]) -> Optional[str]:
    desc = m.get("description") or {}
    mt = str(desc.get("marketType") or m.get("marketType") or "").upper()
    if mt in _KEY_BY_TYPE:
        return mt
    name = str(m.get("marketName") or "").strip().lower()
    return _TYPE_BY_NAME.get(name)


def _market_ref(m: Dict[str, Any], mtype: str, warns: List[str]) -> Optional[MarketRef]:
    under = over = None
    for r in m.get("runners") or []:
        canon = canonical_selection(OVER_UNDER, r.get("runnerName"), r.get("sortPriority"))
        try:
            sid = int(r.get("selectionId"))
        except (TypeError, ValueError):
            continue
        if canon == "UNDER":
            under = sid
        elif canon == "OVER":
            over = sid
    if under is None or over is None:
        warns.append(f"{m.get('marketId')}: runner Under/Over non risolti per nome")
        return None
    line = "35" if mtype == C.OU35 else "45"
    exp_u, exp_o = C.EXPECTED_SEL[f"UNDER_{line}"], C.EXPECTED_SEL[f"OVER_{line}"]
    if under != exp_u or over != exp_o:
        warns.append(f"{m.get('marketId')} {mtype}: selection id {under}/{over} diversi dagli attesi "
                     f"{exp_u}/{exp_o} (uso i nomi)")
    try:
        total = float(m.get("totalMatched") or 0.0)
    except (TypeError, ValueError):
        total = 0.0
    return MarketRef(market_id=str(m.get("marketId")), market_type=mtype, under_sel=under,
                     over_sel=over, total_matched=total)


def group_by_event(markets: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, EventMarkets], List[str]]:
    """Raggruppa per evento: servono ENTRAMBI i mercati. Ritorna (eventi, warnings)."""
    warns: List[str] = []
    by_ev: Dict[str, Dict[str, Any]] = {}
    for m in markets:
        mtype = _market_type(m)
        if mtype is None:
            continue
        ev = m.get("event") or {}
        eid = str(ev.get("id") or "")
        if not eid:
            continue
        ref = _market_ref(m, mtype, warns)
        if ref is None:
            continue
        slot = by_ev.setdefault(eid, {
            "name": str(ev.get("name") or ""),
            "competition": str((m.get("competition") or {}).get("name") or ""),
            "competition_id": str((m.get("competition") or {}).get("id") or ""),
            "ko": _parse_dt(m.get("marketStartTime") or ev.get("openDate")),
        })
        key = _KEY_BY_TYPE[mtype]
        prev = slot.get(key)
        if prev is not None and prev.market_id != ref.market_id:
            # due mercati dello stesso tipo per lo stesso evento: mai sovrascrivere in
            # silenzio — resta il PIU' liquido, e lo si dice (review F0, MEDIUM #7)
            warns.append(f"evento {eid}: {mtype} duplicato ({prev.market_id} vs {ref.market_id}), "
                         f"tengo il piu' liquido")
            if prev.total_matched >= ref.total_matched:
                continue
        slot[key] = ref
        if slot["ko"] is None:
            slot["ko"] = _parse_dt(m.get("marketStartTime") or ev.get("openDate"))
    out: Dict[str, EventMarkets] = {}
    for eid, slot in by_ev.items():
        if "OU35" not in slot or "OU45" not in slot or slot["ko"] is None:
            continue
        out[eid] = EventMarkets(event_id=eid, event_name=slot["name"], competition=slot["competition"],
                                competition_id=slot["competition_id"], ko_at=slot["ko"],
                                ou35=slot["OU35"], ou45=slot["OU45"])
    return out, warns


# ---------------------------------------------------------------------------
# Ranking / selezione / budget
# ---------------------------------------------------------------------------
def rank_events(events: Iterable[EventMarkets], now: datetime, *, open_ids: Set[str],
                inplay_ids: Set[str]) -> List[EventMarkets]:
    """Priorita': posizione aperta > in-play > KO piu' vicino > piu' liquido."""
    def key(e: EventMarkets):
        tier = 0 if e.event_id in open_ids else (1 if e.event_id in inplay_ids else 2)
        dist = abs((e.ko_at - now).total_seconds())
        return (tier, dist, -e.total_matched)
    return sorted(events, key=key)


def budget_verdict(n_markets: int, safe_threshold: int, hard_cap: int) -> BudgetVerdict:
    return check_market_budget(int(n_markets), int(safe_threshold), int(hard_cap))


def select_events(events: Iterable[EventMarkets], now: datetime, params: Dict[str, Any], *,
                  open_ids: Set[str], inplay_ids: Set[str], safe_threshold: int, hard_cap: int) -> Selection:
    """Sottoinsieme da sottoscrivere: filtro liquidita'/competizione, ranking, cap partite e mercati."""
    min_tm = float(params.get("min_total_matched", 0.0))
    comp_filter = [s.strip().lower() for s in str(params.get("competition_filter") or "").split(",") if s.strip()]
    kept: List[EventMarkets] = []
    dropped_liq: List[str] = []
    for e in events:
        if e.event_id not in open_ids:
            if e.total_matched < min_tm:
                dropped_liq.append(e.event_id)
                continue
            if comp_filter and not any(f in e.competition.lower() for f in comp_filter):
                continue
        kept.append(e)
    ranked = rank_events(kept, now, open_ids=open_ids, inplay_ids=inplay_ids)
    max_matches = int(params.get("max_matches", 40))
    max_by_cap = int(hard_cap) // 2
    limit = min(max_matches, max_by_cap)
    chosen = ranked[:limit]
    dropped_cap = [e.event_id for e in ranked[limit:]]
    n = 2 * len(chosen)
    return Selection(events=chosen, n_markets=n, verdict=budget_verdict(n, safe_threshold, hard_cap),
                     dropped_liquidity=dropped_liq, dropped_cap=dropped_cap)


def market_ids(events: Iterable[EventMarkets]) -> List[str]:
    out: List[str] = []
    for e in events:
        out.extend(e.market_ids)
    return out


def window_bounds(now: datetime, *, hours_back: float, hours_ahead: float) -> Tuple[str, str]:
    """(from, to) ISO Z per il filtro marketStartTime."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    n = now.astimezone(timezone.utc)
    return ((n - timedelta(hours=float(hours_back))).strftime(fmt),
            (n + timedelta(hours=float(hours_ahead))).strftime(fmt))


# ---------------------------------------------------------------------------
# Rete (unica funzione con I/O)
# ---------------------------------------------------------------------------
def fetch_day_markets(trading: Any, now: datetime, *, hours_back: float = 3.0,
                      hours_ahead: float = 24.0, max_results: int = 1000) -> List[Dict[str, Any]]:
    """UNA listMarketCatalogue (lightweight=True -> dict) sulle due linee nella finestra."""
    from betfairlightweight import filters  # import locale: modulo puro altrove

    frm, to = window_bounds(now, hours_back=hours_back, hours_ahead=hours_ahead)
    mf = filters.market_filter(
        event_type_ids=[C.FOOTBALL_EVENT_TYPE_ID],
        market_type_codes=[C.OU35, C.OU45],
        market_start_time={"from": frm, "to": to},
    )
    res = trading.betting.list_market_catalogue(
        filter=mf,
        market_projection=["EVENT", "COMPETITION", "MARKET_START_TIME", "RUNNER_DESCRIPTION",
                           "MARKET_DESCRIPTION"],
        sort="FIRST_TO_START",
        max_results=int(max_results),
        lightweight=True,
    )
    return list(res or [])
