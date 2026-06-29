"""
odds_refresh.py — refresh ON-DEMAND delle quote Betfair COMPLETE per UNA singola
fixture, in tabella betfair_market_odds.

Pensato per il pulsante "Aggiorna quote" della watchlist: è una normale chiamata
REST (listMarketCatalogue + listMarketBook), quindi funziona ANCHE PRE-MATCH
(le quote dei mercati sono disponibili molto prima del calcio d'inizio).

MONEY-CRITICAL: le quote DEVONO restare legate alla partita giusta. Due percorsi,
entrambi sicuri:
  (A) REFRESH dei market_id GIÀ associati alla fixture (run di OGGI in
      betfair_market_odds): si rinfrescano ESATTAMENTE quei market_id → è
      impossibile scambiare partita (non si ri-abbina nulla).
  (B) FALLBACK (fixture senza quote di oggi): match 1:1 evento↔fixture con
      Betfair/betfair_match.resolve_matches — STESSE garanzie money-safe di
      betfair_full_odds.py (fuzzy come il foglio + gate temporale + assegnazione
      unica) — poi si scrivono i market_id risolti.

La scrittura tocca SOLO le righe di QUESTA fixture per OGGI (delete+insert per
fixture_id+run_date): mai altre partite. Un lock di processo serializza i refresh
(evita race sul delete+insert e rispetta i limiti Betfair).
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- RISPETTO LIMITI BETFAIR (come betfair_full_odds.py: niente ban) ---
# listMarketBook: peso max 200/chiamata, EX_BEST_OFFERS = 5/mercato → batch 20 = peso 100.
BATCH = 20
REQ_DELAY = 0.6                 # secondi tra chiamate
LIMIT_MARKERS = ("TOO_MANY_REQUESTS", "TOO_MUCH_DATA")

# serializza i refresh on-demand nel processo: un solo set di chiamate per volta.
_REFRESH_LOCK = threading.Lock()

# client Betfair riusato tra le chiamate (login una volta, re-login su sessione scaduta).
_client: Any = None
_CLIENT_LOCK = threading.Lock()


class BetfairLimitHit(RuntimeError):
    """Limite Betfair raggiunto: STOP pulito, mai retry-storm (niente ban)."""


def _is_limit(ex: Exception) -> bool:
    return any(m in str(ex) for m in LIMIT_MARKERS)


def _best_levels(arr: Optional[List[Dict[str, Any]]], n: int = 3) -> List[Dict[str, Any]]:
    return [{"price": x.get("price"), "size": x.get("size")} for x in (arr or [])[:n]]


def _get_client() -> Any:
    """BetfairClient loggato, creato/condiviso lazy."""
    global _client
    with _CLIENT_LOCK:
        if _client is None:
            from Betfair.client import BetfairClient
            c = BetfairClient()
            c.login_cert()
            _client = c
        return _client


def _reset_client() -> None:
    global _client
    with _CLIENT_LOCK:
        _client = None


def _with_client(fn):
    """Esegue fn(client). Se fallisce (sessione forse scaduta), re-login UNA volta
    e ritenta. fn deve essere idempotente (solo letture REST)."""
    try:
        return fn(_get_client())
    except BetfairLimitHit:
        raise
    except Exception as ex:  # noqa: BLE001 - rilancio dopo un solo re-login
        if _is_limit(ex):
            raise BetfairLimitHit(str(ex))
        logger.warning("[odds_refresh] chiamata Betfair fallita, re-login e retry: %s", str(ex)[:140])
        _reset_client()
        return fn(_get_client())


# Accessori PUBBLICI: condividono la stessa sessione Betfair cached con altri moduli
# (es. order_exec), così il piazzamento ordini non apre una seconda sessione/login.
def get_shared_client() -> Any:
    """BetfairClient loggato e condiviso (login lazy una volta)."""
    return _get_client()


def reset_shared_client() -> None:
    """Forza il re-login alla prossima chiamata (sessione scaduta)."""
    _reset_client()


def _catalogue_meta(client: Any, *, market_ids: Optional[List[str]] = None,
                    event_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Mappa market_id → {name, runners{selection_id:(name, sort_priority)}} via
    listMarketCatalogue (RUNNER_DESCRIPTION). Filtra per market_ids OPPURE event_ids."""
    flt: Dict[str, Any] = {}
    if market_ids:
        flt["marketIds"] = market_ids
    if event_ids:
        flt["eventIds"] = event_ids
    try:
        cats = client.betting_rpc(
            "SportsAPING/v1.0/listMarketCatalogue",
            {"filter": flt, "maxResults": 1000, "marketProjection": ["RUNNER_DESCRIPTION"]},
        ) or []
    except Exception as ex:
        if _is_limit(ex):
            raise BetfairLimitHit(str(ex))
        raise
    meta: Dict[str, Dict[str, Any]] = {}
    for mk in cats:
        mid = mk["marketId"]
        meta[mid] = {
            "name": mk["marketName"],
            "runners": {
                r["selectionId"]: (r.get("runnerName", "?"), r.get("sortPriority"))
                for r in mk.get("runners", [])
            },
        }
    return meta


def _market_books(client: Any, market_ids: List[str]) -> List[Dict[str, Any]]:
    """listMarketBook in batch (peso = BATCH*5 = 100 < 200), con delay anti-throttle."""
    books: List[Dict[str, Any]] = []
    for i in range(0, len(market_ids), BATCH):
        try:
            books += client.list_market_book(market_ids[i:i + BATCH]) or []
        except Exception as ex:
            if _is_limit(ex):
                raise BetfairLimitHit(str(ex))
            raise
        time.sleep(REQ_DELAY)
    return books


def _rows_from_books(books: List[Dict[str, Any]], meta: Dict[str, Dict[str, Any]],
                     fixture_id: int, run_date: str) -> List[Dict[str, Any]]:
    """Costruisce le righe betfair_market_odds. fixture_id è FISSO: ogni riga è
    legata alla partita richiesta (i market_id provengono già da essa)."""
    rows: List[Dict[str, Any]] = []
    for b in books:
        mm = meta.get(b["marketId"])
        if not mm:
            continue
        for r in b.get("runners", []):
            rn, sp = mm["runners"].get(r["selectionId"], ("?", None))
            ex = r.get("ex", {})
            rows.append({
                "fixture_id": fixture_id,
                "market_name": mm["name"],
                "selection": rn,
                "sort_priority": sp,
                "market_id": b["marketId"],
                "run_date": run_date,
                "back": _best_levels(ex.get("availableToBack")),
                "lay": _best_levels(ex.get("availableToLay")),
            })
    return rows


def _resolve_market_ids_via_matching(sb: Any, fixture_id: int) -> Tuple[List[str], str]:
    """FALLBACK money-safe: abbina la fixture a UN evento Betfair di oggi (1:1) e
    ritorna i suoi market_id. ([], motivo) se non si abbina."""
    fx = sb.table("fixture_predictions").select(
        "fixture_id,home_team_name,away_team_name,fixture_date"
    ).eq("fixture_id", fixture_id).limit(1).execute().data
    if not fx:
        return [], "fallback_no_fixture"

    from Betfair.betfair_match import resolve_matches, load_name_map

    now_utc = datetime.now(timezone.utc)
    end_today = now_utc.replace(hour=23, minute=59, second=59, microsecond=0)
    to_date_str = end_today.strftime("%Y-%m-%dT%H:%M:%SZ")

    raw_evs = _with_client(lambda c: c.list_events(["1"], to_date=to_date_str) or [])
    events = [{
        "id": e.get("event", {}).get("id"),
        "name": e.get("event", {}).get("name", "") or "",
        "openDate": e.get("event", {}).get("openDate"),
    } for e in raw_evs]

    matched, _ = resolve_matches(events, fx, name_map=load_name_map())
    for m in matched:
        if int(m["fixture"]["fixture_id"]) == fixture_id:
            eid = m["event"]["id"]
            meta = _with_client(lambda c: _catalogue_meta(c, event_ids=[eid]))
            return sorted(meta.keys()), "fallback_match"
    return [], "fallback_unmatched"


def refresh_fixture_odds(fixture_id: int, sb: Any = None) -> Dict[str, Any]:
    """Rinfresca le quote Betfair complete della SOLA fixture indicata.

    Ritorna un dict-esito:
      {ok, fixture_id, markets, rows, source}              # successo
      {ok: False, fixture_id, reason, markets:0, rows:0, source}   # nessuna quota/match

    `source` ∈ {refresh, fallback_match, fallback_unmatched, fallback_no_fixture}.
    Solleva BetfairLimitHit se si tocca un limite Betfair (STOP pulito).
    """
    fixture_id = int(fixture_id)
    with _REFRESH_LOCK:
        if sb is None:
            from db_client import get_supabase_client
            sb = get_supabase_client()
        today = dt.date.today().isoformat()

        # (A) market_id GIÀ associati a questa fixture per OGGI → refresh diretto.
        existing = sb.table("betfair_market_odds").select("market_id").eq(
            "fixture_id", fixture_id).eq("run_date", today).execute().data or []
        market_ids = sorted({r["market_id"] for r in existing if r.get("market_id")})
        source = "refresh"

        # (B) nessuna riga di oggi → fallback con match 1:1.
        if not market_ids:
            market_ids, source = _resolve_market_ids_via_matching(sb, fixture_id)
            if not market_ids:
                logger.info("[odds_refresh] fixture %s: nessun mercato Betfair (%s)", fixture_id, source)
                return {"ok": False, "fixture_id": fixture_id, "reason": source,
                        "markets": 0, "rows": 0, "source": source}

        def _fetch(client: Any) -> List[Dict[str, Any]]:
            meta = _catalogue_meta(client, market_ids=market_ids)
            time.sleep(REQ_DELAY)
            books = _market_books(client, market_ids)
            return _rows_from_books(books, meta, fixture_id, today)

        rows = _with_client(_fetch)
        if not rows:
            return {"ok": False, "fixture_id": fixture_id, "reason": "no_quotes",
                    "markets": 0, "rows": 0, "source": source}

        # SCRITTURA idempotente: sostituisci SOLO le righe di QUESTA fixture per OGGI.
        # Scoping rigoroso (fixture_id + run_date): nessun'altra partita viene toccata.
        # LIMITAZIONE NOTA (basso rischio): il job mattutino betfair_full_odds.py fa un
        # DELETE GLOBALE run_date=today; se gira mentre l'utente rinfresca, può
        # sovrascrivere queste righe con quote più vecchie. Nessun fixture-swap (il
        # fixture_id resta corretto): basta ri-cliccare "Aggiorna quote".
        sb.table("betfair_market_odds").delete().eq(
            "fixture_id", fixture_id).eq("run_date", today).execute()
        for i in range(0, len(rows), 500):
            sb.table("betfair_market_odds").insert(rows[i:i + 500]).execute()

        n_markets = len({r["market_name"] for r in rows})
        logger.info("[odds_refresh] fixture %s: %d righe, %d mercati (%s)",
                    fixture_id, len(rows), n_markets, source)
        return {"ok": True, "fixture_id": fixture_id, "markets": n_markets,
                "rows": len(rows), "source": source}
