"""reconcile_worker.py — A2: RICONCILIAZIONE dello specchio col CONTO Betfair (+ A6 ripresa).

BackgroundWorker del RUNNER (registrato SOLO con LIVE_ORDER_MODE ∈ {PAPER, LIVE}).
Il CONTO Betfair è la VERITÀ ULTIMA: dove specchio e conto divergono, vince
SEMPRE il conto. Ad ogni ciclo:

  1. (PAPER e LIVE — il conto è reale in entrambe) saldo/exposure da
     ``getAccountFunds`` → ``betfair_live_account`` (write-on-change).
  2. (SOLO LIVE — il conto riflette solo ordini reali) riconciliazione ordini:
     a. current orders REST (paginati) vs specchio ``betfair_live_orders``;
     b. ordini ESTERNI (piazzati dal sito, mai visti dal runner) → upsert nello
        specchio con ``client_order_ref = ext<bet_id>`` e ``source='account'``
        + alert WARN una volta per bet;
     c. DIVERGENZE (size_matched/status) → lo specchio viene CORRETTO coi
        valori del conto + alert WARN una volta per bet;
     d. ordini specchio EXECUTABLE assenti dal conto → MAI toccati (lo stream
        può essere più aggiornato del REST), solo WARN se persiste 2 cicli;
     e. cleared orders della giornata locale (groupBy MARKET) →
        ``betfair_live_settled`` (write-on-change): il P&L realizzato viene
        dal conto, non da una stima.
  3. (A6, una volta per avvio, solo LIVE) report di RIPRESA: alert INFO con il
     riepilogo conto/specchio + verifica delle regole armate il cui
     ``entry_bet_id`` non esiste più né sul conto né nello specchio (WARN:
     restano armate, il flatten ricalcola dalle esposizioni reali).

MONEY-CRITICAL:
  * il conto vince SEMPRE: mai "correggere" il conto dallo specchio;
  * gli ordini esterni NON vengono mai ignorati: entrano nello specchio
    (chi somma lo specchio — xhedge, esposizioni — deve vederli) e l'utente
    viene avvisato (WARN, una volta per bet: anti-spam, mai silenzioso);
  * un ordine specchio assente dal REST NON viene cancellato/chiuso d'ufficio:
    il REST può essere in ritardo sullo stream — solo segnalazione;
  * REST KO → log warning e retry al prossimo ciclo: il saldo che salta NON
    blocca la riconciliazione ordini (e viceversa). MAI far cadere il runner.

Testabile a unità: session/supabase/db mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import live_order_worker as low
from .net_retry import with_backoff
from .trading.daily_pnl import day_window_utc

logger = logging.getLogger(__name__)

_RECONCILE_TABLE = "betfair_live_orders"
_MAX_PAGES = 5  # cap difensivo alla paginazione REST (5×1000 ordini: oltre è patologico)

# anti-spam: chiavi (prefissate per tipo) delle divergenze già segnalate.
_ALERTED_BETS: set[str] = set()
# report di ripresa (A6) fatto una volta per mode per avvio del runner.
_STARTUP_DONE: dict[str, bool] = {}
# bet EXECUTABLE nello specchio ma assenti dal conto: cicli consecutivi visti.
_MISSING_SEEN: dict[str, int] = {}
# write-on-change del saldo / dei settled per mercato.
_LAST_ACCOUNT_SIG: Optional[Tuple] = None
_LAST_CLEARED_SIG: Dict[str, Tuple] = {}


def _alert(level: str, msg: str) -> None:
    try:
        from . import db

        db.insert_alert(level, "RECONCILE", msg)
    except Exception:  # noqa: BLE001 - alert best-effort
        pass


def _warn_once(key: str, msg: str) -> None:
    """Alert WARN al massimo UNA volta per chiave (anti-spam per bet)."""
    if key in _ALERTED_BETS:
        return
    _ALERTED_BETS.add(key)
    _alert("WARN", msg)


def _rest(fn: Callable[[], Any]) -> Any:
    """Chiamata REST Betfair con retry SOLO su errori transitori di rete (A1).

    ``sleep=time.sleep`` risolto a runtime (testabile senza attese reali)."""
    return with_backoff(fn, attempts=2, base_delay=0.5, sleep=time.sleep)


def _now_local() -> datetime:
    """Ora nella timezone della giornata (Europe/Rome, come il daily stop)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Europe/Rome"))
    except Exception:  # noqa: BLE001 - tzdata assente: fallback al fuso di sistema
        return datetime.now().astimezone()


def _round2(v: Optional[float]) -> Optional[float]:
    return round(v, 2) if v is not None else None


# ---------------------------------------------------------------------------
# 1) Saldo del conto (PAPER e LIVE) — write-on-change
# ---------------------------------------------------------------------------
def _sync_account(session: Any) -> None:
    global _LAST_ACCOUNT_SIG
    try:
        funds = _rest(lambda: session.context_api_client.account.get_account_funds())
    except Exception as ex:  # noqa: BLE001 - best-effort periodico: ritenta al prossimo ciclo
        logger.warning("[reconcile] getAccountFunds KO: %s", str(ex)[:200])
        return
    sig = (
        _round2(low._f(low._val(funds, "available_to_bet_balance"))),
        _round2(low._f(low._val(funds, "exposure"))),
    )
    if sig == _LAST_ACCOUNT_SIG:
        return
    try:
        from . import db

        db.upsert_live_account(sig[0], sig[1])
        _LAST_ACCOUNT_SIG = sig
    except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
        logger.warning("[reconcile] upsert account KO: %s", str(ex)[:200])


# ---------------------------------------------------------------------------
# 2) Riconciliazione ordini (SOLO LIVE): il CONTO vince sempre
# ---------------------------------------------------------------------------
def _fetch_current_orders(session: Any) -> Dict[str, Any]:
    """Tutti i current orders del CONTO, paginati: dict bet_id → CurrentOrder."""
    orders: Dict[str, Any] = {}
    from_record = 0
    for _page in range(_MAX_PAGES):
        res = _rest(
            lambda fr=from_record: session.context_api_client.betting.list_current_orders(
                from_record=fr, record_count=1000
            )
        )
        page = low._val(res, "orders") or []
        for order in page:
            bet_id = low._val(order, "bet_id")
            if bet_id is not None:
                orders[str(bet_id)] = order
        from_record += len(page)
        if not page or not low._val(res, "more_available"):
            break
    return orders


def _dt_iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:  # noqa: BLE001 - già stringa o tipo esotico
        return str(v)


def _account_order_row(order: Any) -> Dict[str, Any]:
    """Riga specchio COMPLETA per un ordine visto SOLO sul conto (source='account').

    Shape allineata a ``LiveTradingStrategy._order_row`` (specchio betfair_live_orders),
    campi mappati dal CurrentOrder betfairlightweight."""
    bet_id = str(low._val(order, "bet_id"))
    side = low._val(order, "side")
    ps = low._val(order, "price_size")
    # fix 11/07 (rumore live 10/07): flumine stampa customerStrategyRef su
    # OGNI ordine bot → un ordine col ref NON e' "esterno dal sito", e' di un
    # bot noto (scalper/sniper girano in un processo separato dal runner).
    csr = low._val(order, "customer_strategy_ref")
    source = (f"bot:{csr}"[:32] if csr and str(csr) != "live" else "account")
    return {
        "bet_id": bet_id,
        "client_order_ref": f"ext{bet_id}"[:32],
        "mode": "live",
        "source": source,
        "market_id": low._val(order, "market_id"),
        "selection_id": low._int(low._val(order, "selection_id")),
        "handicap": low._f(low._val(order, "handicap")) or 0.0,
        "side": side.lower() if isinstance(side, str) else side,
        "order_type": str(low._val(order, "order_type") or "LIMIT"),
        "price": low._f(low._val(ps, "price")) if ps is not None else None,
        "size": low._f(low._val(ps, "size")) if ps is not None else None,
        "size_matched": low._f(low._val(order, "size_matched")) or 0.0,
        "size_remaining": low._f(low._val(order, "size_remaining")) or 0.0,
        "size_cancelled": low._f(low._val(order, "size_cancelled")) or 0.0,
        "size_lapsed": low._f(low._val(order, "size_lapsed")) or 0.0,
        "size_voided": low._f(low._val(order, "size_voided")) or 0.0,
        "average_price_matched": low._f(low._val(order, "average_price_matched")) or 0.0,
        "status": low._val(order, "status"),
        "persistence": low._val(order, "persistence_type"),
        "placed_at": _dt_iso(low._val(order, "placed_date")),
    }


def _reconcile_orders(sb: Any, current: Dict[str, Any], mirror: List[Dict[str, Any]]) -> int:
    """Confronto conto ↔ specchio. Ritorna il numero di ordini ESTERNI trovati."""
    by_bet = {str(r["bet_id"]): r for r in mirror if r.get("bet_id")}

    # b) ordini ESTERNI: sul conto ma NON nello specchio → entrano nello specchio.
    externals = 0
    for bet_id, order in current.items():
        if bet_id in by_bet:
            continue
        row = _account_order_row(order)
        try:
            sb.table(_RECONCILE_TABLE).upsert(row, on_conflict="mode,client_order_ref").execute()
        except Exception as ex:  # noqa: BLE001 - upsert idempotente: retry al prossimo ciclo
            logger.warning("[reconcile] upsert esterno %s KO: %s", bet_id, str(ex)[:200])
        if str(row.get("source") or "").startswith("bot:"):
            # ordine di un BOT noto (customerStrategyRef presente): entra
            # nello specchio ma NIENTE allarme — la pioggia di WARN del
            # 10/07 rendeva il feed alert inutile proprio quando serviva.
            continue
        externals += 1
        _warn_once(
            f"ext:{bet_id}",
            f"ordine ESTERNO sul conto (dal sito?): bet {bet_id} "
            f"mercato {low._val(order, 'market_id')} — aggiunto allo specchio.",
        )

    # c) DIVERGENZE: bet in entrambi ma con fill/status diversi → il CONTO vince.
    for bet_id, order in current.items():
        row = by_bet.get(bet_id)
        if row is None:
            continue
        acc_matched = low._f(low._val(order, "size_matched")) or 0.0
        acc_status = low._val(order, "status")
        mir_matched = low._f(row.get("size_matched")) or 0.0
        mir_status = row.get("status")
        if abs(mir_matched - acc_matched) <= 0.01 and mir_status == acc_status:
            continue
        updates = {
            "size_matched": acc_matched,
            "size_remaining": low._f(low._val(order, "size_remaining")) or 0.0,
            "size_cancelled": low._f(low._val(order, "size_cancelled")) or 0.0,
            "size_lapsed": low._f(low._val(order, "size_lapsed")) or 0.0,
            "size_voided": low._f(low._val(order, "size_voided")) or 0.0,
            "average_price_matched": low._f(low._val(order, "average_price_matched")) or 0.0,
            "status": acc_status,
        }
        try:
            (
                sb.table(_RECONCILE_TABLE)
                .update(updates)
                .eq("mode", "live")
                .eq("bet_id", bet_id)
                .execute()
            )
        except Exception as ex:  # noqa: BLE001 - retry al prossimo ciclo
            logger.warning("[reconcile] correzione %s KO: %s", bet_id, str(ex)[:200])
        _warn_once(
            f"div:{bet_id}",
            f"specchio divergente dal conto, corretto: bet {bet_id} "
            f"matched {mir_matched}→{acc_matched}, status {mir_status}→{acc_status}.",
        )

    # d) specchio NON-terminale ma assente dal conto: MAI toccare (lo stream può
    # essere più aggiornato del REST) — WARN solo se persiste 2 cicli consecutivi.
    # gli ordini bot (source 'bot:*' o 'account') spariscono dal conto per i
    # cancel rapidi del maker (requote/scratch): e' il loro funzionamento
    # normale, non un'anomalia da segnalare (rumore live 10/07).
    missing_now = {
        str(r["bet_id"])
        for r in mirror
        if r.get("bet_id") and r.get("status") == "EXECUTABLE"
        and str(r["bet_id"]) not in current
        and not str(r.get("source") or "").startswith("bot:")
        and str(r.get("source") or "") != "account"
    }
    for bet_id in list(_MISSING_SEEN):
        if bet_id not in missing_now:
            _MISSING_SEEN.pop(bet_id, None)  # ricomparso/risolto: reset del contatore
    for bet_id in missing_now:
        _MISSING_SEEN[bet_id] = _MISSING_SEEN.get(bet_id, 0) + 1
        if _MISSING_SEEN[bet_id] >= 2:
            _warn_once(
                f"miss:{bet_id}",
                f"ordine specchio EXECUTABLE bet {bet_id} ASSENTE dai current orders "
                "del conto da 2 cicli — verificare (riga NON toccata).",
            )
    return externals


# ---------------------------------------------------------------------------
# 2e) Settled dal conto: cleared orders della giornata (verità ultima)
# ---------------------------------------------------------------------------
def _event_by_market(sb: Any) -> Dict[str, str]:
    """market_id → event_id dallo specchio ordini live (fix review MEDIUM: il
    settled scritto da REST deve portare event_id come quello del path blotter,
    per i raggruppamenti per-evento della dashboard). Best-effort: {} su errore."""
    try:
        res = (
            sb.table("betfair_live_orders")
            .select("market_id,event_id")
            .eq("mode", "live")
            .limit(1000)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return {
            str(r["market_id"]): str(r["event_id"])
            for r in rows
            if r.get("market_id") and r.get("event_id")
        }
    except Exception:  # noqa: BLE001 - arricchimento opzionale
        return {}


def _sync_cleared(session: Any, sb: Any = None) -> None:
    from betfairlightweight import filters

    start_utc, end_utc = day_window_utc(_now_local())
    date_range = filters.time_range(from_=start_utc.isoformat(), to=end_utc.isoformat())
    groups: List[Any] = []
    from_record = 0
    for _page in range(_MAX_PAGES):
        res = _rest(
            lambda fr=from_record: session.context_api_client.betting.list_cleared_orders(
                bet_status="SETTLED",
                group_by="MARKET",
                settled_date_range=date_range,
                from_record=fr,
                record_count=1000,
            )
        )
        page = low._val(res, "orders") or []
        groups.extend(page)
        from_record += len(page)
        if not page or not low._val(res, "more_available"):
            break

    ev_map = _event_by_market(sb) if sb is not None else {}
    for group in groups:
        market_id = low._val(group, "market_id")
        profit = low._f(low._val(group, "profit"))
        if market_id is None or profit is None:
            continue
        bet_count = low._int(low._val(group, "bet_count")) or 0
        sig = (round(profit, 2), bet_count)
        if _LAST_CLEARED_SIG.get(str(market_id)) == sig:
            continue
        try:
            from . import db

            db.upsert_live_settled(
                {
                    "mode": "live",
                    "market_id": market_id,
                    "event_id": ev_map.get(str(market_id)),
                    "profit": round(profit, 2),
                    "orders": bet_count,
                    "source": "cleared",
                }
            )
            _LAST_CLEARED_SIG[str(market_id)] = sig
        except Exception as ex:  # noqa: BLE001 - upsert idempotente: retry al prossimo ciclo
            logger.warning("[reconcile] upsert settled %s KO: %s", market_id, str(ex)[:200])


# ---------------------------------------------------------------------------
# 3) Ripresa (A6): report una volta per avvio + regole armate orfane
# ---------------------------------------------------------------------------
def _startup_report(
    sb: Any, mode_l: str, current: Dict[str, Any], mirror: List[Dict[str, Any]], externals: int
) -> None:
    if _STARTUP_DONE.get(mode_l):
        return
    _STARTUP_DONE[mode_l] = True
    _alert(
        "INFO",
        f"ripresa LIVE: {len(current)} ordini correnti sul conto, "
        f"{externals} esterni, {len(mirror)} righe specchio.",
    )
    # regole armate con entry_bet_id che non esiste più né sul conto né nello specchio:
    # restano armate (il flatten ricalcola dalle esposizioni reali) ma vanno DICHIARATE.
    try:
        res = (
            sb.table("betfair_live_risk_rules")
            .select("id,entry_bet_id,market_id")
            .eq("status", "armed")
            .eq("mode", "live")
            .execute()
        )
        rules = getattr(res, "data", None) or []
        mirror_bets = {str(r["bet_id"]) for r in mirror if r.get("bet_id")}
        for rule in rules:
            entry_bet = rule.get("entry_bet_id")
            if not entry_bet:
                continue
            if str(entry_bet) in current or str(entry_bet) in mirror_bets:
                continue
            _alert(
                "WARN",
                f"regola {rule.get('id')} armata con riferimento bet {entry_bet} non trovato "
                "dopo il riavvio (resta armata: il flatten ricalcola dalle esposizioni reali).",
            )
    except Exception as ex:  # noqa: BLE001 - report best-effort, il runner prosegue
        logger.warning("[reconcile] verifica regole armate KO: %s", str(ex)[:200])


# ---------------------------------------------------------------------------
# Ciclo
# ---------------------------------------------------------------------------
def _process_once(sb: Any, session: Any, mode_l: str) -> None:
    if mode_l not in ("paper", "live"):
        return
    if getattr(session, "context_api_client", None) is None:
        return

    # 1) saldo del conto (entrambe le mode: il conto è reale). Un KO qui NON
    # blocca la riconciliazione ordini (gestito dentro _sync_account).
    _sync_account(session)

    if mode_l != "live":
        return  # in PAPER il conto non riflette gli ordini simulati: stop qui

    # 2) current orders del conto + specchio → esterni/divergenze/assenti.
    try:
        current = _fetch_current_orders(session)
    except Exception as ex:  # noqa: BLE001 - REST KO: retry al prossimo ciclo
        logger.warning("[reconcile] listCurrentOrders KO: %s", str(ex)[:200])
        return
    try:
        res = (
            sb.table(_RECONCILE_TABLE)
            .select("bet_id,client_order_ref,size_matched,status,source")
            .eq("mode", "live")
            .execute()
        )
        mirror = getattr(res, "data", None) or []
    except Exception as ex:  # noqa: BLE001 - DB KO: retry al prossimo ciclo
        logger.warning("[reconcile] lettura specchio KO: %s", str(ex)[:200])
        return
    externals = _reconcile_orders(sb, current, mirror)

    # 2e) settled della giornata dal conto (best-effort: KO → retry al prossimo ciclo).
    try:
        _sync_cleared(session, sb)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[reconcile] listClearedOrders KO: %s", str(ex)[:200])

    # 3) ripresa A6: report una volta per avvio (solo dopo un ciclo LIVE riuscito).
    _startup_report(sb, mode_l, current, mirror, externals)


def reconcile_worker(context: Any, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """Entry BackgroundWorker (vedi runner.py). Non solleva MAI."""
    if session is None:
        return
    mode = low._live_order_mode()
    if mode not in ("PAPER", "LIVE"):
        return
    try:
        from db_client import get_supabase_client

        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001 - DB non raggiungibile: salta il giro
        logger.warning("[reconcile] client supabase KO: %s", str(ex)[:200])
        return
    try:
        _process_once(sb, session, mode.lower())
    except Exception as ex:  # noqa: BLE001 - il worker non deve mai far cadere il runner
        logger.exception("[reconcile] ciclo KO: %s", str(ex)[:200])
