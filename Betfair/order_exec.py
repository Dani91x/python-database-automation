"""
order_exec.py — PIAZZAMENTO ORDINI REALI su Betfair (soldi veri) per UNA giocata
della watchlist. Cuore money-critical: ogni ordine va ESATTAMENTE sulla partita,
mercato e selezione richiesti.

Contratto: Betfair Exchange ``SportsAPING/v1.0/placeOrders`` (vedi doc ufficiale).
- LimitOrder: size, price (su TICK valido), persistenceType (LAPSE/PERSIST/
  MARKET_ON_CLOSE), opz. timeInForce=FILL_OR_KILL + minFillSize.
- Idempotenza: customerRef univoco per ordine → Betfair de-dup su finestra 60s
  (un retry di rete NON piazza due volte).
- Esito: PlaceExecutionReport → betId, orderStatus, sizeMatched, averagePriceMatched.

ABBINAMENTO BLINDATO (il rischio #1): la selezione viene risolta SOLO a partire dal
``market_id`` già associato a QUELLA fixture in ``betfair_market_odds`` (popolato dal
job giornaliero / "Aggiorna quote"), poi il selectionId viene letto da
``listMarketCatalogue`` su quel market_id. Nessun ri-abbinamento, nessun input utente
nel determinare market/selezione: solo le chiavi canoniche dello snapshot.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from Betfair.odds_refresh import BetfairLimitHit, get_shared_client, reset_shared_client

logger = logging.getLogger(__name__)

LIMIT_MARKERS = ("TOO_MANY_REQUESTS", "TOO_MUCH_DATA")
MIN_STAKE_EUR = 2.0          # stake minimo Exchange .it
EXCHANGE_FOOTBALL = "1"      # eventTypeId calcio (coerente col resto del repo)

# serializza i piazzamenti nel processo: niente race, una richiesta per volta.
_PLACE_LOCK = threading.Lock()
# timeout di acquisizione del lock: se un altro piazzamento è in corso oltre questo
# tempo, rispondiamo "occupato" invece di bloccare oltre il timeout del client.
_PLACE_LOCK_TIMEOUT_SEC = 20.0


class OrderBusy(RuntimeError):
    """Un altro piazzamento è già in corso: riprova tra poco (no doppio invio)."""


def _is_limit(ex: Exception) -> bool:
    return any(m in str(ex) for m in LIMIT_MARKERS)


# ---------------------------------------------------------------------------
# Mappatura chiave-mercato canonica → mercato/selezione Betfair.
# IDENTICA a get_betfair_direction_odds (SQL): garantisce coerenza tra ciò che
# l'utente vede nello snapshot e ciò su cui si piazza realmente.
#   _RUNNER_MAP: match per NOME runner. _SORT_MAP: match per sortPriority.
# ---------------------------------------------------------------------------
_RUNNER_MAP: Dict[Tuple[str, str], Tuple[str, str]] = {
    ("over_1_5", "Over"): ("Over/Under 1.5 Goals", "Over 1.5 Goals"),
    ("over_1_5", "Under"): ("Over/Under 1.5 Goals", "Under 1.5 Goals"),
    ("over_2_5", "Over"): ("Over/Under 2.5 Goals", "Over 2.5 Goals"),
    ("over_2_5", "Under"): ("Over/Under 2.5 Goals", "Under 2.5 Goals"),
    ("over_3_5", "Over"): ("Over/Under 3.5 Goals", "Over 3.5 Goals"),
    ("over_3_5", "Under"): ("Over/Under 3.5 Goals", "Under 3.5 Goals"),
    ("btts", "Yes"): ("Both teams to Score?", "Yes"),
    ("btts", "No"): ("Both teams to Score?", "No"),
    ("first_half_over_0_5", "Over"): ("First Half Goals 0.5", "Over 0.5 Goals"),
    ("first_half_over_0_5", "Under"): ("First Half Goals 0.5", "Under 0.5 Goals"),
}
_SORT_MAP: Dict[Tuple[str, str], Tuple[str, int]] = {
    ("1x2", "H"): ("Match Odds", 1),
    ("1x2", "A"): ("Match Odds", 2),
    ("1x2", "D"): ("Match Odds", 3),
    ("ht_1x2", "H"): ("Half Time", 1),
    ("ht_1x2", "A"): ("Half Time", 2),
    ("ht_1x2", "D"): ("Half Time", 3),
}

_VALID_PERSISTENCE = {"LAPSE", "PERSIST", "MARKET_ON_CLOSE"}
_VALID_SIDE = {"BACK", "LAY"}


# ---------------------------------------------------------------------------
# Ladder dei TICK validi Betfair (prezzo deve appartenere a questa scala).
# ---------------------------------------------------------------------------
_TICK_BANDS = [
    (1.01, 2.0, 0.01), (2.0, 3.0, 0.02), (3.0, 4.0, 0.05), (4.0, 6.0, 0.1),
    (6.0, 10.0, 0.2), (10.0, 20.0, 0.5), (20.0, 30.0, 1.0), (30.0, 50.0, 2.0),
    (50.0, 100.0, 5.0), (100.0, 1000.0, 10.0),
]


def _build_ticks() -> List[float]:
    ticks: List[float] = []
    for lo, hi, step in _TICK_BANDS:
        n = int(round((hi - lo) / step))
        for i in range(n):
            ticks.append(round(lo + i * step, 2))
    ticks.append(1000.0)
    return sorted(set(ticks))


_TICKS = _build_ticks()


def round_to_tick(price: float) -> float:
    """Arrotonda al TICK Betfair valido più vicino, clampando in [1.01, 1000]."""
    p = max(1.01, min(1000.0, float(price)))
    return min(_TICKS, key=lambda t: abs(t - p))


def _call(fn):
    """Esegue fn(client) con la sessione condivisa; un re-login su sessione scaduta.
    fn DEVE essere idempotente: per il piazzamento questo è garantito dal customerRef
    fisso (de-dup Betfair 60s), per le letture è naturale."""
    try:
        return fn(get_shared_client())
    except BetfairLimitHit:
        raise
    except (ValueError, LookupError):
        # errore PERMANENTE (risoluzione/dati: runner non trovato, ambiguità, ...):
        # non è una sessione scaduta → NON resettare il client né ritentare.
        raise
    except Exception as ex:  # noqa: BLE001
        if _is_limit(ex):
            raise BetfairLimitHit(str(ex))
        logger.warning("[order_exec] chiamata Betfair fallita, re-login e retry: %s", str(ex)[:140])
        reset_shared_client()
        return fn(get_shared_client())


def _resolve_target(market_key: str, selection: str) -> Tuple[str, Optional[str], Optional[int]]:
    """(market_key, selection) → (betfair_market_name, runner_name|None, sort_priority|None).
    Solleva ValueError se la coppia non è supportata."""
    key = (market_key, selection)
    if key in _RUNNER_MAP:
        bf_market, runner = _RUNNER_MAP[key]
        return bf_market, runner, None
    if key in _SORT_MAP:
        bf_market, sort = _SORT_MAP[key]
        return bf_market, None, sort
    raise ValueError(f"mercato/selezione non supportati per il piazzamento: {market_key} · {selection}")


def _market_id_for(sb: Any, fixture_id: int, bf_market_name: str, run_date: str) -> str:
    """market_id Betfair di QUELLA fixture per quel mercato (run di oggi). Solleva
    ValueError se assente (→ l'utente deve 'Aggiorna quote') o ambiguo (safety)."""
    rows = sb.table("betfair_market_odds").select("market_id").eq(
        "fixture_id", fixture_id).eq("market_name", bf_market_name).eq("run_date", run_date).execute().data or []
    mids = sorted({r["market_id"] for r in rows if r.get("market_id")})
    if not mids:
        raise ValueError(f"mercato Betfair '{bf_market_name}' non disponibile per questa partita: aggiorna le quote.")
    if len(mids) > 1:
        # invariante money-safe: un mercato per fixture deve avere UN market_id.
        raise ValueError(f"ambiguità market_id per '{bf_market_name}' (fixture {fixture_id}): STOP per sicurezza.")
    return mids[0]


def _resolve_selection(client: Any, market_id: str, runner_name: Optional[str],
                       sort_priority: Optional[int]) -> Dict[str, Any]:
    """Da market_id → selectionId + handicap + nomi abbinati, via listMarketCatalogue
    (RUNNER_DESCRIPTION). I market_id provengono dalla fixture: nessun ri-abbinamento."""
    cats = client.betting_rpc(
        "SportsAPING/v1.0/listMarketCatalogue",
        {"filter": {"marketIds": [market_id]}, "maxResults": 1,
         "marketProjection": ["RUNNER_DESCRIPTION"]},
    ) or []
    if not cats:
        raise ValueError(f"catalogo Betfair vuoto per market_id {market_id}.")
    mk = cats[0]
    runners = mk.get("runners", [])
    if runner_name is not None:
        matched = [r for r in runners if r.get("runnerName") == runner_name]
    else:
        matched = [r for r in runners if r.get("sortPriority") == sort_priority]
    if not matched:
        raise ValueError(f"runner non trovato nel mercato {market_id} "
                         f"(runner={runner_name!r}, sort={sort_priority}).")
    if len(matched) > 1:
        raise ValueError(f"runner ambiguo nel mercato {market_id}: STOP per sicurezza.")
    r = matched[0]
    return {
        "selection_id": r["selectionId"],
        "handicap": r.get("handicap", 0) or 0,
        "runner_name": r.get("runnerName"),
        "market_name": mk.get("marketName"),
    }


def _customer_order_ref(fixture_id: int, market_key: str) -> str:
    """Riferimento ordine PERSISTENTE e tracciabile (charset sicuro, <=32 char)."""
    base = f"awl-{fixture_id}-{market_key}"
    base = re.sub(r"[^A-Za-z0-9_-]", "", base)[:20]
    return f"{base}-{uuid.uuid4().hex[:8]}"[:32]


def place_order(
    fixture_id: int,
    market: str,
    selection: str,
    side: str,
    price: float,
    *,
    size: Optional[float] = None,
    liability: Optional[float] = None,
    persistence: str = "LAPSE",
    fill_or_kill: bool = False,
    min_fill_size: Optional[float] = None,
    max_stake: Optional[float] = None,
    sb: Any = None,
) -> Dict[str, Any]:
    """Piazza UN ordine reale e ritorna l'esito completo.

    Parametri principali:
      market/selection : chiavi canoniche dello snapshot (es. 'btts'/'Yes').
      side             : 'back'|'lay'.
      price            : quota richiesta (verrà arrotondata al tick valido).
      size             : stake in €. Per il LAY si può passare 'liability' al posto.
      persistence      : 'LAPSE'(Cancel)|'PERSIST'(Keep)|'MARKET_ON_CLOSE'(Take SP).
      fill_or_kill     : prendi-ora-o-annulla (timeInForce=FILL_OR_KILL).
      max_stake        : cap anti-errore: rifiuta se lo stake lo supera.

    Esito (dict): ok, status, error_code, instruction_status, order_status, bet_id,
      placed_date, size_matched, average_price_matched, size_remaining, + contesto
      abbinato (market_id, market_name, runner, selection_id, handicap, side, price,
      size, persistence, fill_or_kill, customer_order_ref).
    """
    fixture_id = int(fixture_id)
    side_up = str(side or "").strip().upper()
    if side_up not in _VALID_SIDE:
        raise ValueError(f"lato non valido: {side!r} (atteso back/lay).")
    persistence = str(persistence or "LAPSE").strip().upper()
    if persistence not in _VALID_PERSISTENCE:
        raise ValueError(f"persistenza non valida: {persistence!r}.")
    # FILL_OR_KILL sovrascrive la persistenza lato Betfair: la combinazione con
    # PERSIST/MARKET_ON_CLOSE è contraddittoria → la rifiutiamo esplicitamente.
    if fill_or_kill and persistence != "LAPSE":
        raise ValueError("Fill or Kill sovrascrive la persistenza: con FoK usa 'Cancel' (LAPSE).")

    # prezzo → tick valido
    price_tick = round_to_tick(price)
    if price_tick < 1.01:
        raise ValueError("quota non valida.")

    # stake: da 'size' oppure, per il LAY, da 'liability'
    if size is None and liability is not None:
        if side_up != "LAY":
            raise ValueError("la responsabilità (liability) si applica solo al LAY.")
        if price_tick <= 1.0:
            raise ValueError("quota troppo bassa per derivare lo stake dalla liability.")
        size = float(liability) / (price_tick - 1.0)
    if size is None:
        raise ValueError("stake (size) mancante.")
    size = round(float(size), 2)
    if size < MIN_STAKE_EUR:
        raise ValueError(f"stake €{size:.2f} sotto il minimo Betfair (€{MIN_STAKE_EUR:.2f}).")
    if max_stake is not None and size > float(max_stake) + 1e-9:
        raise ValueError(f"stake €{size:.2f} oltre il cap impostato (€{float(max_stake):.2f}).")
    if fill_or_kill and min_fill_size is not None:
        min_fill_size = round(float(min_fill_size), 2)
        if min_fill_size <= 0 or min_fill_size > size:
            raise ValueError("minFillSize deve essere >0 e <= size.")

    if sb is None:
        from db_client import get_supabase_client
        sb = get_supabase_client()

    # acquisizione del lock con timeout: se un altro piazzamento è in corso oltre la
    # soglia, segnaliamo "occupato" (no attesa infinita, no doppio invio).
    if not _PLACE_LOCK.acquire(timeout=_PLACE_LOCK_TIMEOUT_SEC):
        raise OrderBusy("un altro piazzamento è in corso: riprova tra poco.")
    try:
        # data calcolata DENTRO il lock: evita uno scarto a cavallo di mezzanotte se
        # il lock è stato tenuto a lungo.
        today = dt.date.today().isoformat()

        # 1) risolvi mercato/selezione SOLO dalle chiavi canoniche + market_id della fixture
        bf_market, runner_name, sort_priority = _resolve_target(market, selection)
        market_id = _market_id_for(sb, fixture_id, bf_market, today)
        sel = _call(lambda c: _resolve_selection(c, market_id, runner_name, sort_priority))

        # 2) costruisci l'istruzione LIMIT
        limit_order: Dict[str, Any] = {
            "size": size,
            "price": price_tick,
            "persistenceType": persistence,
        }
        if fill_or_kill:
            limit_order["timeInForce"] = "FILL_OR_KILL"
            if min_fill_size is not None:
                limit_order["minFillSize"] = min_fill_size

        customer_order_ref = _customer_order_ref(fixture_id, market)
        instruction = {
            "selectionId": sel["selection_id"],
            "handicap": sel["handicap"],
            "side": side_up,
            "orderType": "LIMIT",
            "limitOrder": limit_order,
            "customerOrderRef": customer_order_ref,
        }
        # customerRef FISSO per la chiamata → de-dup Betfair 60s su retry (no doppio piazzamento)
        customer_ref = uuid.uuid4().hex[:32]

        report = _call(lambda c: c.place_orders(
            market_id, [instruction],
            customer_ref=customer_ref, customer_strategy_ref="watchlist",
        ))
    finally:
        _PLACE_LOCK.release()

    # 3) parsing esito reale
    status = (report or {}).get("status")
    irs = (report or {}).get("instructionReports") or []
    ir = irs[0] if irs else {}
    instr_status = ir.get("status")
    size_matched = ir.get("sizeMatched")
    ok = status == "SUCCESS" and instr_status == "SUCCESS"

    size_remaining = None
    if isinstance(size_matched, (int, float)):
        size_remaining = round(size - float(size_matched), 2)

    result = {
        "ok": bool(ok),
        "status": status,
        "error_code": (report or {}).get("errorCode") or ir.get("errorCode"),
        "instruction_status": instr_status,
        "order_status": ir.get("orderStatus"),         # EXECUTABLE | EXECUTION_COMPLETE
        "bet_id": ir.get("betId"),
        "placed_date": ir.get("placedDate"),
        "size_matched": size_matched,
        "average_price_matched": ir.get("averagePriceMatched"),
        "size_remaining": size_remaining,
        # contesto abbinato (per conferma all'utente)
        "fixture_id": fixture_id,
        "market": market,
        "selection": selection,
        "side": side_up,
        "market_id": market_id,
        "market_name": sel["market_name"],
        "runner": sel["runner_name"],
        "selection_id": sel["selection_id"],
        "handicap": sel["handicap"],
        "price": price_tick,
        "size": size,
        "persistence": persistence,
        "fill_or_kill": bool(fill_or_kill),
        "customer_order_ref": customer_order_ref,
    }
    logger.info("[order_exec] fixture %s %s %s @%.2f €%.2f → ok=%s status=%s order=%s betId=%s matched=%s",
                fixture_id, side_up, market, price_tick, size, result["ok"], status,
                result["order_status"], result["bet_id"], size_matched)
    return result
