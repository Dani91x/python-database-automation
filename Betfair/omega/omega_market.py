"""omega_market — wrapper Betfair REST per Omega (I/O, non testato in unità).

Riusa la sessione Betfair condivisa (``odds_refresh.get_shared_client``): NON
apre un secondo login. Espone: listing eventi calcio di oggi, risoluzione del
mercato CORRECT_SCORE, lettura del book (→ ScoreRunner), piazzamento LAY reale.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from Betfair.omega import omega_engine as E
from Betfair.omega.omega_config import CUSTOMER_STRATEGY_REF, FOOTBALL_EVENT_TYPE_ID

logger = logging.getLogger("omega.market")


# ---------------------------------------------------------------------------
# Sessione condivisa + retry con re-login (come odds_refresh._with_client)
# ---------------------------------------------------------------------------
def get_client() -> Any:
    from Betfair.odds_refresh import get_shared_client

    return get_shared_client()


def call(fn: Callable[[Any], Any]) -> Any:
    """Esegue ``fn(client)`` con un re-login+retry singolo su errore di sessione."""
    from Betfair.odds_refresh import get_shared_client, reset_shared_client

    try:
        return fn(get_shared_client())
    except Exception as ex:  # noqa: BLE001
        logger.warning("[omega] chiamata Betfair fallita, re-login e retry: %s", str(ex)[:160])
        reset_shared_client()
        return fn(get_shared_client())


def keep_alive() -> None:
    """Tiene VIVA la sessione condivisa con una chiamata leggera (listEventTypes).

    PROATTIVO (~600s dal loop di servizio, §8): il retry con re-login di
    ``call()`` resta solo rete di sicurezza — il place LIVE non è idempotente
    oltre i 60s di de-dup Betfair, quindi non bisogna MAI arrivare al place con
    la sessione scaduta contando sul retry. Passa da ``call()``: se la sessione
    è già morta, re-login immediato.
    """
    call(lambda c: c.betting_rpc("SportsAPING/v1.0/listEventTypes", {"filter": {}}))


# ---------------------------------------------------------------------------
# Modelli
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EventInfo:
    event_id: str
    name: str
    open_date: Optional[datetime]
    # metadati per la UI (menu Missione): competizione da Betfair, best-effort.
    country_code: Optional[str] = None
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None


@dataclass(frozen=True)
class CorrectScoreMarket:
    market_id: str
    event_id: str
    event_name: str
    market_start_time: Optional[datetime]
    runner_names: dict[int, str]


@dataclass(frozen=True)
class MarketSnapshot:
    status: str            # OPEN | SUSPENDED | CLOSED
    inplay: bool
    runners: list[E.ScoreRunner]
    closed: bool
    winner_selection_id: Optional[int]
    voided: bool


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _best_lay(levels: Any) -> tuple[Optional[float], float, tuple[tuple[float, float], ...]]:
    """Ritorna (best_price, best_size, ladder) da availableToLay."""
    if not levels:
        return None, 0.0, ()
    ladder = tuple((float(l["price"]), float(l["size"])) for l in levels if l.get("price"))
    if not ladder:
        return None, 0.0, ()
    best_price, best_size = ladder[0]
    return best_price, best_size, ladder


def _best_back_price(levels: Any) -> Optional[float]:
    if not levels:
        return None
    try:
        return float(levels[0]["price"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Listing eventi calcio di oggi (include i match già iniziati)
# ---------------------------------------------------------------------------
def list_today_football_events(lookback_hours: int = 12,
                               with_competitions: bool = False) -> list[EventInfo]:
    """Eventi calcio di oggi. ``with_competitions=True`` aggiunge la competizione
    (1 listMarketCatalogue extra per chunk da 100): serve SOLO al refresh della
    cache UI — il loop automatico, che chiama questa funzione a ogni ciclo,
    NON deve pagare la chiamata in più."""
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_today = now.replace(hour=23, minute=59, second=59, microsecond=0)
    to_date = end_today.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw = call(lambda c: c.list_events([FOOTBALL_EVENT_TYPE_ID], from_date=from_date, to_date=to_date)) or []
    out: list[EventInfo] = []
    for e in raw:
        ev = e.get("event", {}) or {}
        eid = ev.get("id")
        if not eid:
            continue
        out.append(EventInfo(str(eid), ev.get("name", "") or "", _parse_iso(ev.get("openDate")),
                             country_code=ev.get("countryCode")))
    if with_competitions:
        comps = competitions_by_event([e.event_id for e in out])
        if comps:
            from dataclasses import replace as _dc_replace

            out = [
                _dc_replace(e, competition_id=comps[e.event_id][0], competition_name=comps[e.event_id][1])
                if e.event_id in comps else e
                for e in out
            ]
    return out


def competitions_by_event(event_ids: list[str]) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """event_id -> (competition_id, competition_name) via listMarketCatalogue
    MATCH_ODDS con projection EVENT+COMPETITION (1 chiamata per chunk di 100).
    BEST-EFFORT: su errore torna la mappa parziale (la lista eventi non deve
    mai fallire per colpa dei metadati)."""
    out: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for i in range(0, len(event_ids), 100):
        chunk = event_ids[i:i + 100]
        try:
            cats = call(lambda c: c.list_market_catalogue(
                chunk, ["MATCH_ODDS"], max_results=200,
                market_projection=["EVENT", "COMPETITION"])) or []
        except Exception as ex:  # noqa: BLE001
            logger.warning("[omega] competizioni non lette (chunk %s): %s", i, str(ex)[:160])
            continue
        for mk in cats:
            ev = mk.get("event") or {}
            comp = mk.get("competition") or {}
            eid = ev.get("id")
            if not eid or str(eid) in out:
                continue
            if comp.get("id") is None and not comp.get("name"):
                continue
            out[str(eid)] = (
                str(comp["id"]) if comp.get("id") is not None else None,
                comp.get("name") or None,
            )
    return out


# ---------------------------------------------------------------------------
# Risoluzione mercato CORRECT_SCORE per evento
# ---------------------------------------------------------------------------
def get_correct_score_market(event: EventInfo) -> Optional[CorrectScoreMarket]:
    cats = call(lambda c: c.list_market_catalogue([event.event_id], ["CORRECT_SCORE"], max_results=5)) or []
    for mk in cats:
        mid = mk.get("marketId")
        if not mid:
            continue
        names = {
            int(r["selectionId"]): r.get("runnerName", "?")
            for r in mk.get("runners", [])
            if r.get("selectionId") is not None
        }
        return CorrectScoreMarket(
            market_id=str(mid),
            event_id=event.event_id,
            event_name=(mk.get("event", {}) or {}).get("name") or event.name,
            market_start_time=_parse_iso(mk.get("marketStartTime")),
            runner_names=names,
        )
    return None


# ---------------------------------------------------------------------------
# Lettura book → ScoreRunner + esito settlement
# ---------------------------------------------------------------------------
def read_market(market: CorrectScoreMarket) -> Optional[MarketSnapshot]:
    books = call(lambda c: c.list_market_book([market.market_id])) or []
    if not books:
        return None
    b = books[0]
    status = b.get("status", "OPEN")
    inplay = bool(b.get("inplay", False))
    closed = status == "CLOSED"
    runners: list[E.ScoreRunner] = []
    winner: Optional[int] = None
    any_winner = False
    runner_statuses: list[Optional[str]] = []
    for r in b.get("runners", []):
        sid = r.get("selectionId")
        if sid is None:
            continue
        sid = int(sid)
        rstatus = r.get("status")
        runner_statuses.append(rstatus)
        if rstatus == "WINNER":
            winner = sid
            any_winner = True
        ex = r.get("ex", {}) or {}
        lay_price, lay_size, ladder = _best_lay(ex.get("availableToLay"))
        runners.append(
            E.ScoreRunner(
                selection_id=sid,
                name=market.runner_names.get(sid, "?"),
                lay_price=lay_price,
                lay_size=lay_size,
                back_price=_best_back_price(ex.get("availableToBack")),
                lay_ladder=ladder,
            )
        )
    # money-critical: la decisione closed/voided è delegata a E.resolve_settlement
    # (funzione PURA e testata) — vedi omega_engine. Non dedurre mai 'void' dalla
    # sola assenza di WINNER: serve che TUTTI i runner siano terminali.
    closed, voided = E.resolve_settlement(status, runner_statuses, any_winner)
    return MarketSnapshot(
        status=status,
        inplay=inplay,
        runners=runners,
        closed=closed,
        winner_selection_id=winner,
        voided=voided,
    )


# ---------------------------------------------------------------------------
# MISSIONI: mercato per TIPO (HALF_TIME_SCORE / CORRECT_SCORE / OVER_UNDER_X5)
# ---------------------------------------------------------------------------
def get_event_market_by_type(
    event_id: str, event_name: str, market_type: str,
) -> Optional[CorrectScoreMarket]:
    """Risolve il mercato di ``market_type`` per l'evento, con i runner names
    presi DALLO STESSO catalogo (selectionId → runnerName: la coppia id/nome
    non può mai disallinearsi). Ritorna None se il mercato non esiste.
    """
    cats = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {
            "filter": {"eventIds": [event_id], "marketTypeCodes": [market_type]},
            "maxResults": 3,
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION",
                                 "MARKET_START_TIME", "EVENT"],
        },
    )) or []
    for mk in cats:
        mid = mk.get("marketId")
        # difesa money-critical: accetta SOLO il tipo richiesto (mai un mercato
        # "simile" restituito per errore dal filtro).
        mtype = (mk.get("description", {}) or {}).get("marketType")
        if not mid or mtype != market_type:
            continue
        names = {
            int(r["selectionId"]): r.get("runnerName", "?")
            for r in mk.get("runners", [])
            if r.get("selectionId") is not None
        }
        return CorrectScoreMarket(
            market_id=str(mid),
            event_id=str(event_id),
            event_name=(mk.get("event", {}) or {}).get("name") or event_name,
            market_start_time=_parse_iso(mk.get("marketStartTime")),
            runner_names=names,
        )
    return None


# ---------------------------------------------------------------------------
# MISSIONI: punteggi live BATCH dall'in-play service Betfair (endpoint pubblico,
# GET senza sessione exchange → NESSUN secondo login, coerente con §5).
# Parser riusato da Betfair/stream/scores (lo stesso in produzione nel runner).
# ---------------------------------------------------------------------------
_INPLAY_SCORES_URL = "https://ips.betfair.com/inplayservice/v1.1/scores"


def get_inplay_scores(event_ids: list) -> dict:
    """{event_id: ScoreSnapshot} per gli eventi live. Difensivo: errori → {}."""
    if not event_ids:
        return {}
    import requests

    from Betfair.stream.scores.betfair_inplay import parse_score_dict

    try:
        resp = requests.get(
            _INPLAY_SCORES_URL,
            params={"eventIds": ",".join(str(e) for e in event_ids),
                    "alt": "json", "regionCode": "UK", "locale": "en_GB"},
            headers={"Connection": "keep-alive", "Content-Type": "application/json"},
            timeout=8,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as ex:  # noqa: BLE001 — il punteggio non deve mai fermare il bot
        logger.warning("[omega] inplay scores KO: %s", str(ex)[:120])
        return {}
    out: dict = {}
    for item in raw if isinstance(raw, list) else []:
        eid = item.get("eventId")
        if eid is None:
            continue
        try:
            out[str(eid)] = parse_score_dict(str(eid), item)
        except Exception:  # noqa: BLE001 — una riga malformata non blocca le altre
            continue
    return out


# ---------------------------------------------------------------------------
# MANUALE: elenco mercati di un evento + lettura book generico
# ---------------------------------------------------------------------------
def list_event_markets(event_id: str, max_results: int = 30) -> list[dict]:
    """Tutti i mercati di un evento (per il menu Manuale), ordinati per volume."""
    cats = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {
            "filter": {"eventIds": [event_id]},
            "maxResults": max_results,
            "sort": "MAXIMUM_TRADED",
            "marketProjection": ["MARKET_DESCRIPTION", "RUNNER_DESCRIPTION", "MARKET_START_TIME", "EVENT"],
        },
    )) or []
    out: list[dict] = []
    for mk in cats:
        mid = mk.get("marketId")
        if not mid:
            continue
        desc = mk.get("description", {}) or {}
        out.append({
            "market_id": str(mid),
            "market_name": mk.get("marketName"),
            "market_type": desc.get("marketType"),
            "total_matched": mk.get("totalMatched"),
            "event_name": (mk.get("event", {}) or {}).get("name"),
            "runner_names": {
                int(r["selectionId"]): r.get("runnerName", "?")
                for r in mk.get("runners", []) if r.get("selectionId") is not None
            },
        })
    return out


def read_book(market_id: str, runner_names: dict[int, str]) -> Optional[dict]:
    """Snapshot generico di un mercato (lay+back best) per la modalità manuale."""
    books = call(lambda c: c.list_market_book([market_id])) or []
    if not books:
        return None
    b = books[0]
    runners = []
    for r in b.get("runners", []):
        sid = r.get("selectionId")
        if sid is None:
            continue
        sid = int(sid)
        ex = r.get("ex", {}) or {}
        lay_price, lay_size, ladder = _best_lay(ex.get("availableToLay"))
        back = ex.get("availableToBack") or []
        back_price = _best_back_price(back)
        back_size = float(back[0]["size"]) if back and back[0].get("size") is not None else 0.0
        runners.append({
            "selection_id": sid,
            "name": runner_names.get(sid, "?"),
            "status": r.get("status"),
            "lay_price": lay_price,
            "lay_size": lay_size,
            "back_price": back_price,
            "back_size": back_size,
            "lay_ladder": [list(x) for x in ladder],
        })
    return {
        "market_id": str(market_id),
        "status": b.get("status", "OPEN"),
        "inplay": bool(b.get("inplay", False)),
        "runners": runners,
    }


# ---------------------------------------------------------------------------
# Piazzamento LAY reale (LIVE) — soldi veri
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PlaceResult:
    ok: bool
    order_status: Optional[str]
    bet_id: Optional[str]
    size_matched: float
    avg_price_matched: Optional[float]
    raw: dict = field(default_factory=dict)


def place_order_live(
    *, market_id: str, selection_id: int, price: float, size: float, event_id: str,
    side: str = "lay", customer_ref: Optional[str] = None,
) -> PlaceResult:
    """Piazza un ordine REALE (lay/back). customerRef deterministico = de-dup Betfair (I1)."""
    side_bf = "BACK" if str(side).lower() == "back" else "LAY"
    customer_ref = (customer_ref or f"omega-{event_id}")[:32]
    instruction = {
        "selectionId": int(selection_id),
        "handicap": 0,
        "side": side_bf,
        "orderType": "LIMIT",
        # customerOrderRef è PERSISTITO sull'ordine e RITORNA in listCurrentOrders/
        # listClearedOrders → è la chiave forte per la riconciliazione (I3).
        "customerOrderRef": customer_ref,
        "limitOrder": {
            "size": round(float(size), 2),
            "price": E.round_to_tick(float(price)),
            "persistenceType": "LAPSE",
            # FILL_OR_KILL = "immediato o annullato": la parte NON matchata subito
            # viene cancellata da Betfair. Senza, un fill parziale lascerebbe un
            # residuo VIVO sul book che, matchando più tardi, sfuggirebbe alla
            # contabilità (la riga è già 'open' con la size congelata → I8 violato).
            "timeInForce": "FILL_OR_KILL",
        },
    }
    report = call(
        lambda c: c.place_orders(
            market_id,
            [instruction],
            customer_ref=customer_ref,
            customer_strategy_ref=CUSTOMER_STRATEGY_REF,
        )
    ) or {}
    reports = report.get("instructionReports") or []
    ir = reports[0] if reports else {}
    order_status = ir.get("orderStatus")
    ok = report.get("status") == "SUCCESS" and ir.get("status") == "SUCCESS"
    return PlaceResult(
        ok=bool(ok),
        order_status=order_status,
        bet_id=ir.get("betId"),
        size_matched=float(ir.get("sizeMatched") or 0.0),
        avg_price_matched=ir.get("averagePriceMatched"),
        raw=report if isinstance(report, dict) else {},
    )


def place_lay_live(
    *, market_id: str, selection_id: int, price: float, size: float, event_id: str
) -> PlaceResult:
    """Wrapper storico: LAY reale (usato dal loop automatico)."""
    return place_order_live(
        market_id=market_id, selection_id=selection_id, price=price,
        size=size, event_id=event_id, side="lay",
    )


# ---------------------------------------------------------------------------
# RICONCILIAZIONE: stato reale degli ordini Omega su Betfair
# ---------------------------------------------------------------------------
def order_state_by_bet_id(bet_id: str) -> dict:
    """Stato REALE di UN ordine per betId (riconciliazione del percorso LIVE via
    flumine, §6-bis: l'ordine piazzato dal runner NON porta né il customerOrderRef
    ``omega-*`` né la strategy 'omega' — l'unica chiave certa è il betId).

    Ritorna ``{"found": True, "size_matched", "avg_price_matched",
    "size_remaining"}`` oppure ``{"found": False}`` se Betfair non lo conosce
    in nessuna lista. SOLLEVA su errori di rete (il chiamante NON deve mai
    decidere al buio su soldi veri: riprova al ciclo dopo).
    """
    bid = str(bet_id)
    resp = call(lambda c: c.betting_rpc(
        "SportsAPING/v1.0/listCurrentOrders",
        {"betIds": [bid], "orderProjection": "ALL",
         "fromRecord": 0, "recordCount": 100},
    )) or {}
    for o in resp.get("currentOrders", []) or []:
        if str(o.get("betId")) == bid:
            return {
                "found": True,
                "size_matched": float(o.get("sizeMatched") or 0.0),
                "avg_price_matched": o.get("averagePriceMatched"),
                "size_remaining": float(o.get("sizeRemaining") or 0.0),
            }
    # SETTLED prima (porta i € matchati); poi gli stati "senza fill": un FOK
    # ucciso finisce in CANCELLED/LAPSED con sizeSettled=0.
    for status in ("SETTLED", "VOIDED", "LAPSED", "CANCELLED"):
        resp = call(lambda c, s=status: c.betting_rpc(
            "SportsAPING/v1.0/listClearedOrders",
            {"betStatus": s, "betIds": [bid], "fromRecord": 0, "recordCount": 100},
        )) or {}
        for o in resp.get("clearedOrders", []) or []:
            if str(o.get("betId")) == bid:
                return {
                    "found": True,
                    "size_matched": float(o.get("sizeSettled") or 0.0),
                    "avg_price_matched": o.get("priceMatched"),
                    "size_remaining": 0.0,
                }
    return {"found": False}


def list_current_orders(strategy_ref: str = CUSTOMER_STRATEGY_REF) -> list[dict]:
    """Ordini Omega APERTI/matchati (normalizzati) per la riconciliazione."""
    resp = call(lambda c: c.list_current_orders(customer_strategy_refs=[strategy_ref])) or {}
    out: list[dict] = []
    for o in resp.get("currentOrders", []) or []:
        sid = o.get("selectionId")
        out.append({
            "bet_id": o.get("betId"),
            "market_id": str(o["marketId"]) if o.get("marketId") else None,
            "selection_id": int(sid) if sid is not None else None,
            "side": str(o.get("side", "")).lower(),
            "status": o.get("status"),
            "size_matched": float(o.get("sizeMatched") or 0.0),
            "avg_price_matched": o.get("averagePriceMatched"),
            "size_remaining": float(o.get("sizeRemaining") or 0.0),
            "customer_order_ref": o.get("customerOrderRef"),
        })
    return out


def list_cleared_orders(
    strategy_ref: str = CUSTOMER_STRATEGY_REF,
    market_ids: Optional[list] = None,
    lookback_hours: int = 72,
) -> list[dict]:
    """Ordini Omega REGOLATI (normalizzati). Finestra temporale (default 72h) +
    stati SETTLED **e** VOIDED (un ordine parzialmente matchato su un mercato
    annullato non è SETTLED): così un ordine reale non sfugge alla riconciliazione.
    """
    settled_from = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    out: list[dict] = []
    for status in ("SETTLED", "VOIDED"):
        resp = call(
            lambda c, s=status: c.list_cleared_orders(
                bet_status=s, customer_strategy_refs=[strategy_ref],
                market_ids=market_ids, settled_from=settled_from,
            )
        ) or {}
        for o in resp.get("clearedOrders", []) or []:
            sid = o.get("selectionId")
            out.append({
                "bet_id": o.get("betId"),
                "market_id": str(o["marketId"]) if o.get("marketId") else None,
                "selection_id": int(sid) if sid is not None else None,
                "side": str(o.get("side", "")).lower(),
                "size_settled": float(o.get("sizeSettled") or 0.0),
                "price": o.get("priceMatched") or o.get("priceRequested"),
                "profit": float(o.get("profit") or 0.0),
                "bet_outcome": o.get("betOutcome"),
                "customer_order_ref": o.get("customerOrderRef"),
            })
    return out
