"""
betfair_tennis_odds.py — "Partite del Giorno" TENNIS: quote Betfair COMPLETE
(tutti i mercati, back + lay + volume tradato) per gli eventi tennis (eventTypeId=2)
di OGGI, in tabella ``tennis_markets``.

Mirror di ``betfair_full_odds.py`` (calcio) ma DEDICATO al tennis e keyato
sull'EVENTO Betfair (il tennis non ha fixture calcio): login Betfair → list_events
["2"] di oggi → per ogni evento listMarketCatalogue (TUTTI i market type:
MATCH_ODDS, SET_BETTING, ...) + listMarketBook (EX_BEST_OFFERS + EX_TRADED_VOLUME) →
costruisce un record TennisFixtureRow-shaped (player1/player2 dal MATCH_ODDS per
sortPriority, moneyline back/lay, total_matched, markets[], full_odds[]) → upsert in
``tennis_markets`` (event_id, run_date=oggi). NESSUNA tabella del calcio.

Uso:
  python betfair_tennis_odds.py                 # tutti gli eventi tennis di oggi
  python betfair_tennis_odds.py --filter atp    # solo eventi che contengono "atp"
  python betfair_tennis_odds.py --interval 300  # loop: ri-scarica ogni 5 min
"""
import argparse
import datetime as dt
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- RISPETTO LIMITI BETFAIR (tassativo: niente ban) ---
BATCH = 39            # mercati per listMarketBook (peso 39*5 = 195 < 200)
REQ_DELAY = 0.6       # secondi tra chiamate
EVENT_DELAY = 0.2     # secondi extra tra eventi
CAT_CHUNK = 10        # eventi per chiamata listMarketCatalogue
TENNIS_EVENT_TYPE_ID = "2"
LIMIT_MARKERS = ("TOO_MANY_REQUESTS", "TOO_MUCH_DATA")


class BetfairLimitHit(RuntimeError):
    pass


def _is_limit(ex: Exception) -> bool:
    return any(m in str(ex) for m in LIMIT_MARKERS)


def best_levels(arr: Optional[List[Dict[str, Any]]], n: int = 5) -> List[Dict[str, Any]]:
    """[{price,size}, ...] dai primi n livelli (TennisOddLevel del frontend)."""
    return [{"price": x.get("price"), "size": x.get("size")} for x in (arr or [])[:n]]


def _list_catalogue(c: Any, event_ids: List[str]) -> List[Dict[str, Any]]:
    """listMarketCatalogue per una lista di eventIds — TUTTI i market type."""
    try:
        cats = c.betting_rpc(
            "SportsAPING/v1.0/listMarketCatalogue",
            {
                "filter": {"eventIds": event_ids, "eventTypeIds": [TENNIS_EVENT_TYPE_ID]},
                "maxResults": 1000,
                "marketProjection": [
                    "COMPETITION",
                    "MARKET_START_TIME",
                    "RUNNER_DESCRIPTION",
                    "MARKET_DESCRIPTION",
                    "EVENT",
                ],
            },
        ) or []
    except Exception as ex:  # noqa: BLE001
        if _is_limit(ex):
            raise BetfairLimitHit(str(ex))
        raise
    time.sleep(REQ_DELAY)
    return cats


def _runner_levels(ex_obj: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """(back, lay) come liste di {price,size} dai campi availableTo* di un runner."""
    ex = ex_obj or {}
    return best_levels(ex.get("availableToBack")), best_levels(ex.get("availableToLay"))


def _build_event_record(
    ev_meta: Dict[str, Any],
    cats: List[Dict[str, Any]],
    books_by_mid: Dict[str, Dict[str, Any]],
    today: str,
) -> Optional[Dict[str, Any]]:
    """Costruisce la riga tennis_markets (TennisFixtureRow-shaped) per un evento."""
    market_type_of = {}
    market_name_of = {}
    runners_meta = {}
    for mk in cats:
        mid = mk["marketId"]
        desc = mk.get("description") or {}
        market_type_of[mid] = desc.get("marketType")
        market_name_of[mid] = mk.get("marketName")
        runners_meta[mid] = {
            r["selectionId"]: (r.get("runnerName", "?"), r.get("sortPriority"))
            for r in mk.get("runners", [])
        }

    markets_out = []       # TennisEventMarket[]
    full_odds = []         # TennisFullMarket[]
    mo_market_id = None
    mo_players = []
    mo_total_matched = None
    mo_status = None
    mo_inplay = False

    for mk in cats:
        mid = mk["marketId"]
        book = books_by_mid.get(mid) or {}
        total_matched = book.get("totalMatched")
        mtype = market_type_of.get(mid)
        markets_out.append(
            {
                "market_id": mid,
                "market_type": mtype,
                "market_name": market_name_of.get(mid),
                "total_matched": total_matched,
            }
        )
        full_runners = []
        for r in book.get("runners", []):
            sel_id = r.get("selectionId")
            name, sort = runners_meta.get(mid, {}).get(sel_id, ("?", None))
            back, lay = _runner_levels(r.get("ex"))
            full_runners.append(
                {
                    "selection": name,
                    "selection_id": sel_id,
                    "sort_priority": sort,
                    "back": back,
                    "lay": lay,
                    "ltp": r.get("lastPriceTraded"),
                }
            )
        full_odds.append(
            {
                "market_id": mid,
                "market": market_name_of.get(mid),
                "market_type": mtype,
                "total_matched": total_matched,
                "runners": full_runners,
            }
        )
        if mtype == "MATCH_ODDS" and mo_market_id is None:
            mo_market_id = mid
            mo_total_matched = total_matched
            mo_status = book.get("status")
            mo_inplay = bool(book.get("inplay"))
            # player1/player2 per sortPriority (1 = P1, 2 = P2)
            ordered = sorted(
                book.get("runners", []),
                key=lambda rr: runners_meta.get(mid, {}).get(rr.get("selectionId"), ("?", 99))[1] or 99,
            )
            for rr in ordered[:2]:
                sel_id = rr.get("selectionId")
                name, sort = runners_meta.get(mid, {}).get(sel_id, ("?", None))
                back, lay = _runner_levels(rr.get("ex"))
                mo_players.append(
                    {
                        "selection_id": sel_id,
                        "name": name,
                        "sort_priority": sort,
                        "back": back,
                        "lay": lay,
                        "ltp": rr.get("lastPriceTraded"),
                    }
                )

    if mo_market_id is None or len(mo_players) < 2:
        return None  # senza MATCH_ODDS a 2 giocatori non è una riga "match del giorno"

    comp = ev_meta.get("competition") or {}
    return {
        "event_id": ev_meta["id"],
        "run_date": today,
        "market_id": mo_market_id,
        "competition_id": comp.get("id"),
        "competition_name": comp.get("name") or ev_meta.get("name") or "",
        "competition_region": ev_meta.get("countryCode"),
        "open_date": ev_meta.get("openDate"),
        "inplay": mo_inplay,
        "status": mo_status or "OPEN",
        "player1": mo_players[0],
        "player2": mo_players[1],
        "total_matched": mo_total_matched,
        "markets": markets_out,
        "full_odds": full_odds,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


def run_once(c: Any, sb: Any, today: str, name_filter: str = "") -> int:
    now_utc = datetime.now(timezone.utc)
    end_today = now_utc.replace(hour=23, minute=59, second=59, microsecond=0)
    to_date_str = end_today.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_evs = c.list_events([TENNIS_EVENT_TYPE_ID], to_date=to_date_str) or []

    events = []
    for e in raw_evs:
        ev = e.get("event", {})
        events.append(
            {
                "id": ev.get("id"),
                "name": ev.get("name", "") or "",
                "countryCode": ev.get("countryCode"),
                "openDate": ev.get("openDate"),
            }
        )
    if name_filter:
        events = [e for e in events if name_filter.lower() in e["name"].lower()]
    logger.info("Eventi Tennis di OGGI (fino a %s): %d", to_date_str, len(events))

    rows = []
    for ci in range(0, len(events), CAT_CHUNK):
        chunk = events[ci:ci + CAT_CHUNK]
        chunk_eids = [e["id"] for e in chunk]
        cats_all = _list_catalogue(c, chunk_eids)
        cats_by_event = {}
        comp_by_event = {}
        for mk in cats_all:
            eid = (mk.get("event") or {}).get("id")
            if not eid:
                continue
            cats_by_event.setdefault(eid, []).append(mk)
            if mk.get("competition"):
                comp_by_event.setdefault(eid, mk.get("competition"))

        for e in chunk:
            eid = e["id"]
            cats = cats_by_event.get(eid, [])
            if not cats:
                continue
            try:
                mids = [mk["marketId"] for mk in cats]
                books = []
                for i in range(0, len(mids), BATCH):
                    try:
                        books += c.list_market_book(
                            mids[i:i + BATCH],
                            price_projection={
                                "priceData": ["EX_BEST_OFFERS", "EX_TRADED_VOLUME"],
                                "virtualise": True,
                            },
                        ) or []
                    except Exception as ex:  # noqa: BLE001
                        if _is_limit(ex):
                            raise BetfairLimitHit(str(ex))
                        raise
                    time.sleep(REQ_DELAY)
                books_by_mid = {b["marketId"]: b for b in books}
                ev_meta = dict(e)
                ev_meta["competition"] = comp_by_event.get(eid)
                rec = _build_event_record(ev_meta, cats, books_by_mid, today)
                if rec is not None:
                    rows.append(rec)
                    logger.info("  [ok] %s (%s): %d mercati", e["name"], eid, len(rec["markets"]))
                time.sleep(EVENT_DELAY)
            except BetfairLimitHit:
                raise
            except Exception as ex:  # noqa: BLE001
                logger.warning("  [ERRORE evento %s '%s']: %s → salto.", eid, e["name"], str(ex)[:140])
                continue

    # Idempotenza: la giornata riparte pulita (event_id + run_date=oggi).
    try:
        sb.table("tennis_markets").delete().eq("run_date", today).execute()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[purge] tennis_markets run_date=%s KO (%s) → proseguo.", today, str(ex)[:120])
    for i in range(0, len(rows), 200):
        sb.table("tennis_markets").upsert(
            rows[i:i + 200], on_conflict="event_id"
        ).execute()
    logger.info("Fatto. Eventi tennis scritti: %d", len(rows))
    return len(rows)


def main() -> None:
    # reconfigure spostata QUI (fix #12): non è un side-effect all'import del modulo, ma
    # accade solo quando si esegue lo script (import puro = nessun effetto sullo stdout).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Quote tennis del giorno (tennis_markets)")
    ap.add_argument("--filter", default="", help="solo eventi il cui nome contiene questa stringa")
    ap.add_argument("--interval", type=int, default=0, help="loop: secondi tra le run (0 = una volta)")
    args = ap.parse_args()

    from db_client import get_supabase_client
    from Betfair.client import BetfairClient

    sb = get_supabase_client()
    c = BetfairClient()
    c.login_cert()

    while True:
        today = dt.date.today().isoformat()
        try:
            run_once(c, sb, today, name_filter=args.filter)
        except BetfairLimitHit as ex:
            logger.error("[STOP LIMITE BETFAIR] interrotto per sicurezza: %s", str(ex)[:140])
        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
