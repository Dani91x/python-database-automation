"""tennis_live_order_worker.py — drena ``tennis_live_order_queue`` (ordini manuali
della ladder tennis) e li esegue sullo STESSO stream/framework del runner tennis.

Mirror di ``Betfair/stream/live_order_worker.py`` (calcio) ma DEDICATO al tennis:
scrive SOLO tabelle ``tennis_*``. Gira come ``BackgroundWorker`` nel runner tennis
(registrato solo quando la modalità ordini ∈ {PAPER, LIVE}).

Ad ogni poll, per ogni riga ``pending``:
  * CLAIM atomico pending→processing (una sola esecuzione per riga);
  * parse del payload (place | cancel | replace | greenup);
  * gli ordini sono creati SOTTO la capture-strategy dell'evento (già sottoscritta al
    mercato → nessuna subscription nuova) e piazzati con le API native del Market
    flumine (``place_order`` / ``cancel_order`` / ``replace_order``);
  * esito scritto nella riga + specchio in ``tennis_live_orders`` / ``tennis_live_positions``.

Idempotenza: ``client_ref`` UNIQUE sulla coda (DB) + claim atomico = anti-doppio-ordine.
``replace`` = cancel-then-place lato Betfair (in-play bet delay del tennis).
Best-effort: ogni errore va in ``error`` e NON fa cadere il runner. Testabile a unità
(nessuna rete): framework/Market/coda mockabili; ``parse_order_payload`` è puro.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import tennis_db

logger = logging.getLogger(__name__)

CUSTOMER_STRATEGY_REF = "tennis"

# Stati terminali flumine (OrderStatus.name): un ordine in questi stati non muterà più →
# la sua firma write-on-change si può togliere dalla cache e l'ordine si può togliere dal
# tracking (evita crescita illimitata del dict e re-mirror inutili — fix #10).
_TERMINAL_STATUSES = frozenset(
    {"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION", "VOIDED"}
)


def _runner_mode() -> str:
    """Modalità REALE di esecuzione del runner tennis (OFF | PAPER | LIVE, UPPER).

    RI-LETTA ad ogni ciclo dallo stesso env di ``tennis_runner.live_order_mode``
    (``TENNIS_LIVE_ORDER_MODE``): un downgrade di sicurezza ha effetto subito. Il worker
    processa SOLO le righe della coda la cui ``mode`` dichiarata coincide con questa
    (cross-mode → error senza esecuzione, fix C1).
    """
    return os.getenv("TENNIS_LIVE_ORDER_MODE", "OFF").strip().upper()


# ---------------------------------------------------------------------------
# Parsing PURO del payload di coda (testabile senza rete)
# ---------------------------------------------------------------------------
def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_order_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalizza una riga di ``tennis_live_order_queue`` in un comando tipizzato.

    Tollera due forme: colonne top-level OPPURE un ``payload``/``params`` jsonb
    (il frontend accoda ``{...cmd, client_ref}``). Solleva ValueError su campi assenti
    obbligatori per l'azione.
    """
    src: Dict[str, Any] = {}
    for key in ("payload", "params", "cmd", "command"):
        node = row.get(key)
        if isinstance(node, dict):
            src = {**node, **src}
    merged = {**src, **{k: v for k, v in row.items() if k not in ("payload", "params")}}

    action = str(merged.get("action") or "").strip().lower()
    if not action:
        raise ValueError("azione mancante")
    side = merged.get("side")
    cmd = {
        "action": action,
        "mode": str(merged.get("mode") or "paper").lower(),
        "market_id": merged.get("market_id"),
        "selection_id": _int(merged.get("selection_id")),
        "handicap": _f(merged.get("handicap")) or 0.0,
        "side": str(side).lower() if isinstance(side, str) else side,
        "order_type": str(merged.get("order_type") or "LIMIT"),
        "price": _f(merged.get("price")),
        "size": _f(merged.get("size")),
        "liability": _f(merged.get("liability")),
        "persistence": str(merged.get("persistence") or "LAPSE"),
        "bet_id": (str(merged["bet_id"]) if merged.get("bet_id") else None),
        "new_price": _f(merged.get("new_price")),
        "size_reduction": _f(merged.get("size_reduction")),
        "params": merged.get("params") if isinstance(merged.get("params"), dict) else (src.get("params") or {}),
        "client_ref": merged.get("client_ref"),
    }
    if action == "place":
        if cmd["market_id"] is None or cmd["selection_id"] is None or cmd["side"] is None:
            raise ValueError("place richiede market_id + selection_id + side")
        if cmd["price"] is None or (cmd["size"] is None and cmd["liability"] is None):
            raise ValueError("place richiede price + (size o liability)")
    elif action in ("cancel", "replace", "greenup"):
        if action != "greenup" and not cmd["bet_id"]:
            raise ValueError(f"{action} richiede bet_id")
        if action == "replace" and cmd["new_price"] is None:
            raise ValueError("replace richiede new_price")
    return cmd


# ---------------------------------------------------------------------------
# Helper flumine (difensivi)
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round_tick(price: float) -> float:
    from flumine.utils import get_nearest_price

    return float(get_nearest_price(float(price)))


def _val(o: Any, attr: str) -> Any:
    try:
        return getattr(o, attr)
    except Exception:  # noqa: BLE001
        return None


def _status_name(order: Any) -> Optional[str]:
    st = _val(order, "status")
    if st is None:
        return None
    return getattr(st, "name", None) or str(st)


def _cust_ref(rid: Any) -> str:
    return ("awtq" + str(rid))[:32]


def _request_id_from_ref(ref: Optional[str]) -> Optional[int]:
    """Estrae il request_id dal nostro ref interno ``awtq<id>`` (None se non è dei nostri)."""
    if not ref or not isinstance(ref, str) or not ref.startswith("awtq"):
        return None
    return _int(ref[4:])


def _merged_field(row: Dict[str, Any], field: str) -> Any:
    """Legge un campo dalla riga di coda tollerando payload/params annidati (come il parser).

    Le righe ``tennis_live_order_queue`` incapsulano il comando in ``payload`` jsonb: la
    ``mode``/``action`` NON è una colonna top-level. Va quindi cercata anche lì."""
    for key in ("payload", "params", "cmd", "command"):
        node = row.get(key)
        if isinstance(node, dict) and node.get(field) not in (None, ""):
            return node.get(field)
    return row.get(field)


def _declared_mode(row: Dict[str, Any]) -> str:
    """Mode DICHIARATA della riga (lower). Default 'paper' se assente: direzione sicura —
    una riga senza mode esplicita NON viene mai eseguita da un runner LIVE (trattata paper)."""
    m = _merged_field(row, "mode")
    return str(m or "paper").strip().lower()


def _declared_action(row: Dict[str, Any]) -> str:
    a = _merged_field(row, "action")
    return str(a or "?").strip().lower()


def _is_terminal(order: Any) -> bool:
    return _status_name(order) in _TERMINAL_STATUSES


def _order_sig(order: Any) -> tuple:
    """Firma dei campi MUTABILI di un ordine (write-on-change dello specchio, fix #10)."""
    return (
        _val(order, "bet_id"),
        _status_name(order),
        _f(_val(order, "size_matched")),
        _f(_val(order, "average_price_matched")),
        _f(_val(order, "size_remaining")),
        _f(_val(order, "size_cancelled")),
        _f(_val(order, "size_lapsed")),
        _f(_val(order, "size_voided")),
    )


def _trade_current_order(trade: Any, fallback: Any) -> Any:
    """Ordine ATTUALE di un trade (fix #6 replace): dopo un ``replace_order`` nativo flumine
    crea un ordine di rimpiazzo sullo STESSO trade (``trade.create_order_replacement`` →
    ``trade.orders``). Ritorna l'ultimo ordine non-terminale (il rimpiazzo vivo) o l'ultimo
    in lista, così lo specchio segue il bet corrente sotto lo stesso client_order_ref."""
    orders = getattr(trade, "orders", None) if trade is not None else None
    if not orders:
        return fallback
    for o in reversed(list(orders)):
        if not _is_terminal(o):
            return o
    return list(orders)[-1]


def _resolve_market(flumine: Any, market_id: Optional[str]) -> Any:
    if not market_id:
        raise ValueError("market_id mancante")
    market = None
    try:
        market = flumine.markets.markets.get(market_id)
    except Exception:  # noqa: BLE001
        market = None
    if market is None:
        raise ValueError(f"market {market_id} non sottoscritto nel runner tennis")
    return market


def _find_order_by_bet_id(flumine: Any, market_id: Optional[str], bet_id: str) -> Any:
    if not bet_id:
        return None
    try:
        if market_id:
            m = flumine.markets.markets.get(market_id)
            if m is not None:
                o = m.blotter.get_order_bet_id(bet_id)
                if o is not None:
                    return o
    except Exception:  # noqa: BLE001
        pass
    try:
        for m in flumine.markets:
            o = m.blotter.get_order_bet_id(bet_id)
            if o is not None:
                return o
    except Exception:  # noqa: BLE001
        pass
    return None


def _order_snapshot(order: Any) -> Dict[str, Any]:
    if order is None:
        return {}
    ot = _val(order, "order_type")
    side = _val(order, "side")
    return {
        "bet_id": _val(order, "bet_id"),
        "status": _status_name(order),
        "size_matched": _f(_val(order, "size_matched")),
        "average_price_matched": _f(_val(order, "average_price_matched")),
        "size_remaining": _f(_val(order, "size_remaining")),
        "size_cancelled": _f(_val(order, "size_cancelled")),
        "size_lapsed": _f(_val(order, "size_lapsed")),
        "size_voided": _f(_val(order, "size_voided")),
        "market_id": _val(order, "market_id"),
        "selection_id": _int(_val(order, "selection_id")),
        "side": side.lower() if isinstance(side, str) else side,
        "price": _f(getattr(ot, "price", None)) if ot is not None else None,
        "size": _f(getattr(ot, "size", None)) if ot is not None else None,
    }


def _result(*, ok: bool, action: str, mode: str, cmd: Dict[str, Any],
            cust_ref: str, order: Any = None, error: Optional[str] = None,
            detail: Optional[str] = None) -> Dict[str, Any]:
    snap = _order_snapshot(order)
    return {
        "ok": ok,
        "action": action,
        "mode": mode,
        "bet_id": snap.get("bet_id"),
        "status": snap.get("status"),
        "size_matched": snap.get("size_matched"),
        "average_price_matched": snap.get("average_price_matched"),
        "size_remaining": snap.get("size_remaining"),
        "market_id": cmd.get("market_id") or snap.get("market_id"),
        "selection_id": cmd.get("selection_id") if cmd.get("selection_id") is not None else snap.get("selection_id"),
        "side": cmd.get("side") or snap.get("side"),
        "price": snap.get("price") if snap.get("price") is not None else cmd.get("price"),
        "size": snap.get("size") if snap.get("size") is not None else cmd.get("size"),
        "customer_order_ref": cust_ref,
        "error": (str(error)[:300] if error is not None else None),
        "detail": (str(detail)[:300] if detail is not None else None),
    }


def _mirror_order(mode: str, event_id: Optional[str], cust_ref: str, order: Any,
                  cmd: Dict[str, Any], source: str = "manual",
                  status_override: Optional[str] = None) -> None:
    """Specchia l'ordine in ``tennis_live_orders`` (best-effort).

    ``source`` = 'manual' (ordini da coda) | bot_key (ordini di un bot ospitato, fix #8).
    ``status`` è NOT NULL nello specchio: se lo snapshot non ha status (ordine non ancora
    materializzato) si salta la scrittura invece di violare il vincolo (fix #6).
    ``status_override``: stato TERMINALE forzato (fix audit #8: ordine simulato di un
    framework smontato → la riga specchio va chiusa una volta, mai EXECUTABLE fantasma)."""
    snap = _order_snapshot(order)
    status = status_override or snap.get("status")
    if status is None:
        # niente status → ordine non ancora reale (es. rimpiazzo async non materializzato):
        # NON scrivere (status è NOT NULL). Il prossimo giro di reconcile lo prenderà.
        return
    mode_l = str(mode or "paper").strip().lower()
    try:
        tennis_db.upsert_tennis_order({
            "mode": mode_l,
            "source": source,
            "client_order_ref": cust_ref,
            "request_id": _request_id_from_ref(cust_ref),
            "event_id": event_id,
            "market_id": snap.get("market_id") or cmd.get("market_id"),
            "selection_id": snap.get("selection_id") or cmd.get("selection_id"),
            "handicap": cmd.get("handicap") or 0.0,
            "side": snap.get("side") or cmd.get("side"),
            "order_type": cmd.get("order_type") or "LIMIT",
            "price": snap.get("price"),
            "size": snap.get("size"),
            "size_matched": snap.get("size_matched") or 0.0,
            "size_remaining": snap.get("size_remaining") or 0.0,
            "size_cancelled": snap.get("size_cancelled") or 0.0,
            "size_lapsed": snap.get("size_lapsed") or 0.0,
            "size_voided": snap.get("size_voided") or 0.0,
            "average_price_matched": snap.get("average_price_matched") or 0.0,
            "status": status,
            "bet_id": snap.get("bet_id"),
            "persistence": cmd.get("persistence"),
        })
    except Exception as e:  # noqa: BLE001 - lo specchio non deve far cadere il worker
        logger.debug("[tennis-order] mirror KO %s: %s", cust_ref, e)


# ---------------------------------------------------------------------------
# Azioni
# ---------------------------------------------------------------------------
def _capture_strategy(session: Any, market_id: str) -> Any:
    """Capture-strategy dell'evento del mercato (gli ordini vi si agganciano)."""
    if session is None:
        return None
    for event_id, meta in getattr(session, "market_meta", {}).items():
        if meta.get("market_id") == market_id:
            return session.capture.get(event_id)
    return None


def _event_id_of(session: Any, market_id: str) -> Optional[str]:
    for event_id, meta in getattr(session, "market_meta", {}).items():
        if meta.get("market_id") == market_id:
            return event_id
    return None


def _jurisdiction() -> str:
    """Giurisdizione per le regole di stake minimo (.it default, come il conto)."""
    return (os.getenv("TENNIS_LIVE_JURISDICTION") or "it").strip().lower()


def _max_stake_per_order() -> Optional[float]:
    """Cap opzionale per-ordine (mirror di LIVE_MAX_STAKE_PER_ORDER del calcio)."""
    raw = (os.getenv("TENNIS_LIVE_MAX_STAKE_PER_ORDER") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


_VALID_PLACE_SIDES = ("BACK", "LAY")
_VALID_PLACE_PERSISTENCE = ("LAPSE", "PERSIST", "MARKET_ON_CLOSE")


def _do_place(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    # validazione money-critical CONDIVISA col calcio (fix review HIGH): min_stake_rules è
    # logica PURA di live_order_build (nessun accesso a dati calcio) — ultima barriera
    # esplicita prima di un ordine REALE, invece di delegare al rifiuto grezzo di Betfair.
    from ..live_order_build import min_stake_rules

    market = _resolve_market(flumine, cmd["market_id"])
    strategy = _capture_strategy(session, cmd["market_id"])
    if strategy is None:
        raise ValueError("nessuna strategy sottoscritta al mercato per agganciare l'ordine")
    side = str(cmd["side"]).upper()
    if side not in _VALID_PLACE_SIDES:
        raise ValueError(f"side non valido: {cmd.get('side')!r} (atteso back|lay)")
    persistence = str(cmd.get("persistence") or "LAPSE").upper()
    if persistence not in _VALID_PLACE_PERSISTENCE:
        raise ValueError(f"persistence non valida: {cmd.get('persistence')!r}")
    price = _round_tick(cmd["price"])
    if not (1.01 - 1e-9 <= float(price) <= 1000 + 1e-9):
        raise ValueError(f"price fuori range Betfair [1.01, 1000]: {price}")
    size = cmd["size"]
    if size is None and cmd.get("liability") is not None and side == "LAY" and price > 1.0:
        size = round(float(cmd["liability"]) / (price - 1.0), 2)
    if size is None:
        raise ValueError("size non derivabile")
    verdict = min_stake_rules(_jurisdiction(), side.lower(), float(price), float(size))
    if not verdict.valid or verdict.legalized_size is None:
        raise ValueError(f"stake non valido: {verdict.reason}")
    size = verdict.legalized_size
    cap = _max_stake_per_order()
    if cap is not None and size > cap + 1e-9:
        raise ValueError(f"size {size:.2f} oltre il cap TENNIS_LIVE_MAX_STAKE_PER_ORDER={cap:.2f}")
    trade = Trade(market_id=market.market_id, selection_id=int(cmd["selection_id"]),
                  handicap=float(cmd.get("handicap") or 0.0), strategy=strategy)
    order = trade.create_order(
        side=side,
        order_type=LimitOrder(price=price, size=round(float(size), 2),
                              persistence_type=persistence),
    )
    ok = market.place_order(order, customer_strategy_ref=CUSTOMER_STRATEGY_REF)
    if ok is False:
        raise ValueError(f"place RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
    _track_manual(session, cust_ref, order, cmd["mode"], _event_id_of(session, cmd.get("market_id")))
    return _result(ok=True, action="place", mode=cmd["mode"], cmd=cmd,
                   cust_ref=cust_ref, order=order, detail=f"place {side} @{price}")


def _do_cancel(flumine: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    order = _find_order_by_bet_id(flumine, cmd.get("market_id"), cmd["bet_id"])
    if order is None:
        raise ValueError(f"ordine bet_id {cmd['bet_id']} non nel blotter")
    market = _resolve_market(flumine, _val(order, "market_id") or cmd.get("market_id"))
    sr = cmd.get("size_reduction")
    ok = market.cancel_order(order, sr) if sr is not None else market.cancel_order(order)
    if ok is False:
        raise ValueError(f"cancel RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
    return _result(ok=True, action="cancel", mode=cmd["mode"], cmd=cmd,
                   cust_ref=cust_ref, order=order, detail="cancel")


def _do_replace(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    order = _find_order_by_bet_id(flumine, cmd.get("market_id"), cmd["bet_id"])
    if order is None:
        raise ValueError(f"ordine bet_id {cmd['bet_id']} non nel blotter")
    market = _resolve_market(flumine, _val(order, "market_id") or cmd.get("market_id"))
    new_price = _round_tick(cmd["new_price"])
    trade = _val(order, "trade")
    # replace nativo = cancel-then-place lato Betfair (in-play delay del tennis). flumine crea
    # un ordine di RIMPIAZZO sullo stesso trade (async). Tracciamo il TRADE (fix #6): il
    # reconcile seguirà l'ordine corrente del trade (il rimpiazzo) sotto lo stesso cust_ref,
    # così lo specchio non resta congelato sull'ordine vecchio dopo un replace.
    ok = market.replace_order(order, new_price)
    if ok is False:
        raise ValueError(f"replace RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
    _track_manual(session, cust_ref, order, cmd["mode"],
                  _event_id_of(session, _val(order, "market_id") or cmd.get("market_id")),
                  trade=trade)
    return _result(ok=True, action="replace", mode=cmd["mode"], cmd=cmd,
                   cust_ref=cust_ref, order=order, detail=f"replace → {new_price}")


def _level_price(level: Any) -> Optional[float]:
    """Prezzo di UN livello del book, tollerante alla forma (port dal calcio).

    MONEY-CRITICAL: con lo stream LIVE betfairlightweight espone
    ``ex.available_to_back/lay`` come lista di **dict** ``{'price':…,'size':…}``,
    NON di oggetti PriceSize. Il solo ``getattr`` ritornerebbe sempre None sui
    dati reali → ogni green-up sarebbe un no-op "prezzo non disponibile"."""
    if level is None:
        return None
    if isinstance(level, dict):
        return _f(level.get("price"))
    return _f(_val(level, "price"))


def _best_prices(market: Any, selection_id: int,
                 handicap: float) -> "tuple[Optional[float], Optional[float]]":
    """(best_available_to_back, best_available_to_lay) dal MarketBook flumine GIÀ in
    memoria (stesso stream, ZERO chiamate API). Port 1:1 dal worker calcio."""
    mb = _val(market, "market_book")
    if mb is None:
        return None, None
    runners = _val(mb, "runners") or []
    for r in runners:
        if _int(_val(r, "selection_id")) != int(selection_id):
            continue
        rh = _f(_val(r, "handicap")) or 0.0
        if abs(rh - float(handicap or 0.0)) > 1e-6:
            continue
        ex = _val(r, "ex")
        atb = (_val(ex, "available_to_back") or []) if ex is not None else []
        atl = (_val(ex, "available_to_lay") or []) if ex is not None else []
        best_back = _level_price(atb[0]) if atb else None
        best_lay = _level_price(atl[0]) if atl else None
        return best_back, best_lay
    return None, None


def _read_matched_exposures(market: Any, strategy: Any, selection_id: int,
                            handicap: float) -> "tuple[float, float]":
    """(profit_if_win, profit_if_lose) MATCHED dal blotter flumine — autoritativo.

    MONEY-CRITICAL: il green-up si calcola sulle esposizioni REALI al MOMENTO
    dell'esecuzione (mai su numeri pollati dal frontend, potenzialmente stantii).
    Difensivo: struttura inattesa → (0,0) → no-op a monte (posizione piatta)."""
    blotter = _val(market, "blotter")
    if blotter is None or strategy is None:
        return 0.0, 0.0
    lookup = (_val(market, "market_id"), int(selection_id), float(handicap or 0.0))
    try:
        exp = blotter.get_exposures(strategy, lookup)
    except Exception:  # noqa: BLE001 - blotter mock/edge → nessuna esposizione
        return 0.0, 0.0
    if not isinstance(exp, dict):
        return 0.0, 0.0
    w = _f(exp.get("matched_profit_if_win")) or 0.0
    l = _f(exp.get("matched_profit_if_lose")) or 0.0
    return w, l


def _cancel_unmatched_selection(market: Any, strategy: Any,
                                selection_id: int) -> "tuple[int, list]":
    """Cancella i NOSTRI resting della selezione (cash-out COMPLETO, port dal calcio):
    prima si annullano gli unmatched, POI si hedgia il matched — un resting
    dimenticato può abbinarsi DOPO l'hedge e riaprire l'esposizione appena chiusa.
    Ritorna (n_cancellati, falliti)."""
    blotter = _val(market, "blotter")
    if blotter is None or strategy is None:
        return 0, []
    try:
        orders = list(blotter.strategy_orders(strategy))
    except Exception:  # noqa: BLE001 - blotter mock/edge: niente da cancellare
        return 0, []
    cancelled = 0
    failed: list = []
    for order in orders:
        if _int(_val(order, "selection_id")) != int(selection_id):
            continue
        rem = _f(_val(order, "size_remaining")) or 0.0
        if _status_name(order) != "EXECUTABLE" or rem <= 0:
            continue
        try:
            ok = market.cancel_order(order)
            if ok is False:
                raise ValueError(_val(order, "violation_msg") or "violation")
            cancelled += 1
        except Exception as ex:  # noqa: BLE001 - continua con gli altri, ma TRACCIA
            failed.append({
                "bet_id": _val(order, "bet_id"),
                "error": f"cancel unmatched fallito: {str(ex)[:120]}",
            })
    return cancelled, failed


def _do_greenup(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    """Green-up / cash-out (fix audit #2): chiude (totale o frazione) l'esposizione
    MATCHED di una selezione, modellato 1:1 sul ``_do_greenup`` del calcio.

    Esposizioni FRESCHE dal blotter flumine (capture-strategy dell'evento) + best
    price opposto dal book già in memoria → UNICO ordine di hedge calcolato dalla
    matematica condivisa ``trading.greenup.compute_greenup`` (stessa formula del
    display lockedPnl del ladder). Onora ``params``: fraction, target_price
    (greening column), place_at_ticks, cancel_unmatched. L'hedge è self-bounded
    (liability < |W−L|) → ``min_stake_rules(..., reduces_liability=True)`` consente
    il sotto-minimo .it. Gating di modalità identico a ``_do_place`` (cross-mode
    rifiutato a monte dal worker; OFF non registra il worker).

    DEVIAZIONE CONSAPEVOLE dal calcio (review 16/07): l'ordine è costruito
    direttamente via ``Trade.create_order`` e NON passa da ``build_order`` — il
    cap MAX_PAYOUT_IT e la validazione generica di range non servono qui perché
    l'hedge è per costruzione limitato dall'esposizione già aperta (validata al
    piazzamento originale) e il prezzo arriva dal book/target già validato sopra."""
    from flumine.order.ordertype import LimitOrder
    from flumine.order.trade import Trade

    from ..live_order_build import min_stake_rules
    from ..trading.greenup import FLAT_EPS, compute_greenup

    market = _resolve_market(flumine, cmd.get("market_id"))
    strategy = _capture_strategy(session, cmd.get("market_id"))
    # MONEY-CRITICAL: senza la capture-strategy NON possiamo leggere le esposizioni
    # (blotter.get_exposures(strategy, ...)) → (0,0) → "posizione piatta" FALSO con
    # la posizione APERTA. Fallire forte invece di un 'done' bugiardo.
    if strategy is None:
        raise ValueError("greenup richiede la capture-strategy del mercato (esposizioni dal blotter)")
    if cmd.get("selection_id") is None:
        raise ValueError("greenup richiede selection_id")
    selection_id = int(cmd["selection_id"])
    handicap = float(cmd.get("handicap") or 0.0)

    params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
    fraction = _f(params.get("fraction"))
    if fraction is None:
        fraction = 1.0
    place_at = _int(params.get("place_at_ticks")) or 0
    # target_price ("greening column"): chiudi A QUEL prezzo assoluto. Un target
    # malformato è un ERRORE di richiesta: mai ripiegare in silenzio sul best.
    target_price = _f(params.get("target_price"))
    if params.get("target_price") is not None and (
        target_price is None or not (1.0 < target_price <= 1000.0)
    ):
        raise ValueError(
            f"greenup: params.target_price non valido ({params.get('target_price')!r}): "
            "atteso un prezzo in (1.0, 1000]"
        )
    # combinazione contraddittoria (mirror calcio): annullare i resting e POI
    # piazzare un take-profit resting non ha senso — mai eseguirla in silenzio.
    if params.get("cancel_unmatched") and params.get("target_price") is not None:
        raise ValueError(
            "greenup: params.cancel_unmatched non è compatibile con params.target_price "
            "(cash-out completo vs take-profit resting)"
        )

    cancel_note = ""
    cancel_failed: list = []
    if params.get("cancel_unmatched"):
        n_cancelled, cancel_failed = _cancel_unmatched_selection(market, strategy, selection_id)
        cancel_note = f"; unmatched annullati: {n_cancelled}"
        if cancel_failed:
            cancel_note += f" ({len(cancel_failed)} cancel FALLITI)"

    w, l = _read_matched_exposures(market, strategy, selection_id, handicap)
    best_back, best_lay = _best_prices(market, selection_id, handicap)
    plan = compute_greenup(
        matched_if_win=w, matched_if_lose=l,
        best_back_price=best_back, best_lay_price=best_lay, fraction=fraction,
        place_at_ticks=place_at, target_price=target_price,
    )

    if not plan.actionable:
        # posizione APERTA ma piano non eseguibile (book vuoto/sospeso): FALLIRE
        # forte — un ok=True qui direbbe "chiuso" con la posizione a sanguinare.
        if abs(w - l) >= FLAT_EPS:
            raise ValueError(
                f"greenup NON eseguibile con esposizione aperta (W={w:.2f} L={l:.2f}): "
                f"{plan.note} — ritentare (mercato sospeso/book vuoto?)"
            )
        if cancel_failed:
            raise ValueError(
                f"cash-out selezione INCOMPLETO: posizione piatta ma {len(cancel_failed)} "
                f"resting NON annullati ({cancel_failed[0].get('error')}) — ritentare"
            )
        # niente da chiudere: esito ok con motivo, nessun ordine (mai place a vuoto)
        return _result(ok=True, action="greenup", mode=cmd["mode"], cmd=cmd,
                       cust_ref=cust_ref, detail=f"{plan.note}{cancel_note}")

    # hedge SELF-BOUNDED: riduce la liability → sotto-minimo .it consentito
    verdict = min_stake_rules(_jurisdiction(), str(plan.side), float(plan.price),
                              float(plan.size), reduces_liability=True)
    if not verdict.valid or verdict.legalized_size is None:
        raise ValueError(f"greenup: size hedge non valida: {verdict.reason}")
    size = verdict.legalized_size
    trade = Trade(market_id=market.market_id, selection_id=selection_id,
                  handicap=handicap, strategy=strategy)
    order = trade.create_order(
        side=str(plan.side).upper(),
        order_type=LimitOrder(price=float(plan.price), size=round(float(size), 2),
                              persistence_type="LAPSE"),
    )
    try:
        # marca la CHIUSURA (come build_order calcio): eventuali control di flusso
        # devono lasciare SEMPRE passare un'uscita.
        order.context["reduces_liability"] = True
    except Exception:  # noqa: BLE001 - context assente su mock: solo metadato
        pass
    ok = market.place_order(order, customer_strategy_ref=CUSTOMER_STRATEGY_REF)
    if ok is False:
        raise ValueError(f"greenup RIFIUTATO — {_val(order, 'violation_msg') or 'violation'}")
    _track_manual(session, cust_ref, order, cmd["mode"],
                  _event_id_of(session, cmd.get("market_id")))
    if cancel_failed:
        # hedge PIAZZATO ma resting non annullati: esito INCOMPLETO esplicito
        # (mai un done bugiardo: il resting vivo può riaprire la posizione).
        raise ValueError(
            f"cash-out selezione INCOMPLETO: hedge {plan.side} {size}@{plan.price} "
            f"piazzato ma {len(cancel_failed)} resting NON annullati "
            f"({cancel_failed[0].get('error')}) — ritentare il cash-out"
        )
    return _result(ok=True, action="greenup", mode=cmd["mode"], cmd=cmd,
                   cust_ref=cust_ref, order=order,
                   detail=f"{plan.note}; atteso vince={plan.expected_if_win} "
                          f"perde={plan.expected_if_lose}{cancel_note}")


def _dispatch(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    action = cmd["action"]
    if action == "place":
        return _do_place(flumine, session, cmd, cust_ref)
    if action == "cancel":
        return _do_cancel(flumine, cmd, cust_ref)
    if action == "replace":
        return _do_replace(flumine, session, cmd, cust_ref)
    if action == "greenup":
        # fix audit #2: green-up IMPLEMENTATO (prima falliva sempre → ogni click
        # di cash-out sul ladder tennis era un errore). Stesso modello del calcio.
        return _do_greenup(flumine, session, cmd, cust_ref)
    raise ValueError(f"azione non supportata: {action}")


# ---------------------------------------------------------------------------
# Tracking + reconcile (specchio write-on-change, prune terminali) — fix #5/#6/#8/#10
# ---------------------------------------------------------------------------
def _track_manual(session: Any, cust_ref: str, order: Any, mode: str,
                  event_id: Optional[str], trade: Any = None) -> None:
    """Registra un ordine manuale per il reconcile. Memorizza la MODE per-ordine (fix #5):
    lo specchio del fill asincrono usa la mode con cui l'ordine è stato piazzato, non un
    'live' hardcoded (altrimenti un fill PAPER finirebbe sotto 'live')."""
    if session is None:
        return
    session.tracked_orders[cust_ref] = {
        "order": order,
        "trade": trade if trade is not None else _val(order, "trade"),
        "mode": str(mode or "paper").strip().lower(),
        "event_id": event_id,
        "source": "manual",
        # generazione del framework al piazzamento (fix audit #8): dopo un restart
        # l'Order appartiene a un framework smontato e va chiuso/scartato, non
        # ri-specchiato per sempre come EXECUTABLE fantasma.
        "gen": getattr(session, "framework_gen", 0),
    }


def _sig_cache(session: Any) -> Dict[str, Any]:
    cache = getattr(session, "order_sig_cache", None)
    if cache is None:
        cache = {}
        try:
            session.order_sig_cache = cache
        except Exception:  # noqa: BLE001 - session mock senza slot: cache locale effimera
            pass
    return cache


def _reconcile_tracked(session: Any, flumine: Any) -> None:
    """Ri-specchia i fill ASINCRONI (best-effort), WRITE-ON-CHANGE + prune terminali (#10).

    - ordini MANUALI: tracciati per cust_ref (awtq<rid>), mode per-ordine (#5); dopo un
      replace segue l'ordine CORRENTE del trade (#6). Terminali → rimossi dal tracking.
    - ordini dei BOT ospitati: specchiati dal blotter con source=bot_key (#8), senza aprire
      alcuna subscription (si legge solo ``blotter.strategy_orders``).
    """
    if session is None:
        return
    cache = _sig_cache(session)
    cur_gen = getattr(session, "framework_gen", 0)

    # 1) ordini manuali
    for cust_ref, rec in list(getattr(session, "tracked_orders", {}).items()):
        try:
            order = _trade_current_order(rec.get("trade"), rec.get("order"))
            # fix audit #8: ordine di un framework SMONTATO (restart avvenuto dopo
            # il piazzamento) non terminale → in paper l'ordine simulato è morto
            # col framework: specchio chiuso UNA volta con stato terminale (VOIDED)
            # e tracking rimosso. In LIVE non si falsifica nulla (l'ordine reale
            # può vivere sull'Exchange): si smette solo di seguirlo, con warning
            # esplicito (fail-loud) — il nuovo blotter/ordine stream lo rivedrà.
            if rec.get("gen", cur_gen) != cur_gen and not _is_terminal(order):
                if (rec.get("mode") or "paper") != "live":
                    _mirror_order(rec.get("mode") or "paper", rec.get("event_id"),
                                  cust_ref, order, {}, source=rec.get("source") or "manual",
                                  status_override="VOIDED")
                else:
                    logger.warning(
                        "[tennis-order] ordine LIVE %s appartiene a un framework "
                        "smontato: tracking rimosso — verifica lo stato su Betfair",
                        cust_ref,
                    )
                session.tracked_orders.pop(cust_ref, None)
                cache.pop(cust_ref, None)
                continue
            sig = _order_sig(order)
            if cache.get(cust_ref) == sig:
                if _is_terminal(order):
                    session.tracked_orders.pop(cust_ref, None)
                    cache.pop(cust_ref, None)
                continue
            _mirror_order(rec.get("mode") or "paper", rec.get("event_id"),
                          cust_ref, order, {}, source=rec.get("source") or "manual")
            if _is_terminal(order):
                session.tracked_orders.pop(cust_ref, None)
                cache.pop(cust_ref, None)
            else:
                cache[cust_ref] = sig
        except Exception as e:  # noqa: BLE001 - lo specchio non deve far cadere il worker
            logger.debug("[tennis-order] reconcile manuale %s KO: %s", cust_ref, e)

    # 2) ordini dei bot ospitati (source=bot_key)
    _reconcile_bots(session, flumine, cache)


def _session_mode(session: Any) -> str:
    """Mode (lower) CATTURATA al build del framework (fix audit #14).

    Gli specchi di ordini bot/posizioni devono restare coerenti con la mode con cui
    gli ordini sono stati PIAZZATI: ri-leggere l'env a ogni ciclo permetterebbe a un
    cambio di TENNIS_LIVE_ORDER_MODE a metà processo di far divergere lo specchio
    dagli ordini (righe 'live' per ordini paper o viceversa). Fallback all'env solo
    se la session non espone la mode (mock/percorsi legacy)."""
    m = getattr(session, "order_mode", None)
    return str(m or _runner_mode()).strip().lower()


def _reconcile_bots(session: Any, flumine: Any, cache: Dict[str, Any]) -> None:
    hosted = getattr(session, "hosted", None)
    if not hosted or flumine is None:
        return
    for (event_id, bot_key), strat in list(hosted.items()):
        meta = getattr(session, "market_meta", {}).get(event_id) or {}
        market_id = meta.get("market_id")
        if not market_id:
            continue
        try:
            market = flumine.markets.markets.get(market_id)
        except Exception:  # noqa: BLE001 - struttura inattesa → salta
            market = None
        if market is None:
            continue
        blotter = _val(market, "blotter")
        if blotter is None:
            continue
        try:
            orders = blotter.strategy_orders(strat)
        except Exception:  # noqa: BLE001 - blotter mock/edge → niente ordini bot
            continue
        # bot → paper|live (OFF non registra il worker); mode di BUILD (fix #14)
        mode = _session_mode(session)
        for order in orders or []:
            oid = _val(order, "id")
            ref = ("bot:" + str(oid))[:32] if oid is not None else None
            if ref is None:
                continue
            sig = _order_sig(order)
            if cache.get(ref) == sig:
                if _is_terminal(order):
                    cache.pop(ref, None)
                continue
            _mirror_order(mode, event_id, ref, order, {}, source=bot_key)
            if _is_terminal(order):
                cache.pop(ref, None)
            else:
                cache[ref] = sig


# ---------------------------------------------------------------------------
# Worker posizioni (#7): esposizione per selezione dal blotter → tennis_live_positions
# ---------------------------------------------------------------------------
def _position_row(market: Any, strategy: Any, mode: str, event_id: Optional[str],
                  market_id: str, selection_id: int, handicap: float) -> Optional[Dict[str, Any]]:
    blotter = _val(market, "blotter")
    if blotter is None:
        return None
    lookup = (market_id, int(selection_id), float(handicap or 0.0))
    try:
        exp = blotter.get_exposures(strategy, lookup)
        sel_exp = blotter.selection_exposure(strategy, lookup)
    except Exception:  # noqa: BLE001 - esposizione non calcolabile → nessuna riga
        return None
    if not isinstance(exp, dict):
        return None
    net = 0.0
    try:
        for o in blotter.strategy_selection_orders(strategy, int(selection_id),
                                                   float(handicap or 0.0), matched_only=True) or []:
            sm = _f(_val(o, "size_matched")) or 0.0
            side = _val(o, "side")
            net += -sm if (isinstance(side, str) and side.upper() == "LAY") else sm
    except Exception:  # noqa: BLE001 - net è un extra: mai bloccare la riga posizione
        net = 0.0
    return {
        "mode": str(mode or "paper").strip().lower(),
        "event_id": event_id,
        "market_id": market_id,
        "selection_id": int(selection_id),
        "handicap": float(handicap or 0.0),
        "matched_if_win": _f(exp.get("matched_profit_if_win")) or 0.0,
        "matched_if_lose": _f(exp.get("matched_profit_if_lose")) or 0.0,
        "worst_if_win": _f(exp.get("worst_possible_profit_on_win")) or 0.0,
        "worst_if_lose": _f(exp.get("worst_possible_profit_on_lose")) or 0.0,
        "selection_exposure": _f(sel_exp) or 0.0,
        "unmatched_back_exposure": _f(exp.get("worst_potential_unmatched_profit_if_lose")) or 0.0,
        "unmatched_lay_exposure": _f(exp.get("worst_potential_unmatched_profit_if_win")) or 0.0,
        "net_position": round(net, 2),
    }


def _iter_tracked_strategies(session: Any) -> Any:
    """(strategy, event_id) per ogni strategy che può avere esposizione: capture (ordini
    manuali) + bot ospitati. Le esposizioni sono PER-strategy nel blotter flumine."""
    out = []
    for event_id, strat in list(getattr(session, "capture", {}).items()):
        out.append((strat, event_id))
    for (event_id, _bot_key), strat in list(getattr(session, "hosted", {}).items()):
        out.append((strat, event_id))
    return out


def positions_worker(context: dict, flumine: Any, session: Any = None) -> None:  # noqa: ARG001
    """BackgroundWorker (#7): calcola l'esposizione per selezione dal blotter flumine e la
    scrive in ``tennis_live_positions`` (prima ZERO writer → tabella sempre vuota). Registrato
    solo in PAPER/LIVE. Non apre subscription: legge solo blotter già in memoria. Best-effort."""
    if session is None or flumine is None:
        return
    mode = _session_mode(session)  # mode di BUILD del framework (fix audit #14)
    # AGGREGAZIONE per (mode, market_id, selection_id, handicap) — fix 2026-07-10:
    # prima un dedup "first-wins" scartava i duplicati: l'esposizione della PRIMA
    # strategy (di norma la capture) vinceva e quella dei BOT andava PERSA nella
    # riga tennis_live_positions. Ora si SOMMANO le esposizioni di tutte le
    # strategy sulla stessa chiave (nessun cambio di schema DB).
    _SUM_FIELDS = (
        "matched_if_win", "matched_if_lose", "worst_if_win", "worst_if_lose",
        "selection_exposure", "unmatched_back_exposure", "unmatched_lay_exposure",
        "net_position",
    )
    agg: Dict[tuple, Dict[str, Any]] = {}
    for strategy, event_id in _iter_tracked_strategies(session):
        meta = getattr(session, "market_meta", {}).get(event_id) or {}
        market_id = meta.get("market_id")
        if not market_id:
            continue
        try:
            market = flumine.markets.markets.get(market_id)
        except Exception:  # noqa: BLE001
            market = None
        if market is None:
            continue
        blotter = _val(market, "blotter")
        if blotter is None:
            continue
        try:
            orders = blotter.strategy_orders(strategy)
        except Exception:  # noqa: BLE001
            continue
        lookups = set()
        for o in orders or []:
            sel = _int(_val(o, "selection_id"))
            if sel is None:
                continue
            lookups.add((sel, _f(_val(o, "handicap")) or 0.0))
        for sel, hcap in lookups:
            row = _position_row(market, strategy, mode, event_id, market_id, sel, hcap)
            if row is None:
                continue
            key = (mode, market_id, sel, hcap)
            cur = agg.get(key)
            if cur is None:
                agg[key] = row
            else:
                for f in _SUM_FIELDS:
                    cur[f] = round(
                        float(cur.get(f) or 0.0) + float(row.get(f) or 0.0), 2
                    )
    # registro delle chiavi scritte in sessione (fix audit #8): serve per azzerare
    # le righe rimaste ORFANE quando una chiave sparisce dal blotter corrente
    # (tipicamente dopo un restart del framework: blotter nuovo e VUOTO, ma le
    # vecchie righe tennis_live_positions resterebbero non-zero per sempre).
    written = getattr(session, "positions_written", None)
    if written is None:
        written = {}
        try:
            session.positions_written = written
        except Exception:  # noqa: BLE001 - session mock senza slot: registro effimero
            pass
    for key, row in agg.items():
        (_mode_k, market_id, sel, _hcap) = key
        try:
            tennis_db.upsert_tennis_position(row)
            written[key] = {"event_id": row.get("event_id"), "miss": 0}
        except Exception as e:  # noqa: BLE001
            logger.debug("[tennis-pos] upsert KO %s/%s: %s", market_id, sel, e)
    # chiavi scritte in passato ma ASSENTI dall'aggregato corrente → riga azzerata
    # UNA volta (write-once: la chiave esce dal registro solo a upsert riuscito).
    # ANTI-FALSO-FLAT (review 16/07): l'assenza deve persistere per ≥2 cicli
    # consecutivi — una lettura del blotter fallita TRANSITORIAMENTE (market/blotter
    # None, strategy_orders in eccezione: sopra sono tutti `continue` best-effort)
    # non deve mai mostrare "flat" al trader con l'esposizione ancora aperta.
    _ZERO_AFTER_MISSES = 2
    for key in [k for k in list(written.keys()) if k not in agg]:
        mode_k, market_id, sel, hcap = key
        info = written.get(key) or {}
        miss = int(info.get("miss") or 0) + 1
        if miss < _ZERO_AFTER_MISSES:
            info["miss"] = miss
            written[key] = info
            continue
        written.pop(key, None)
        zero = {
            "mode": mode_k,
            "event_id": info.get("event_id"),
            "market_id": market_id,
            "selection_id": int(sel),
            "handicap": float(hcap or 0.0),
        }
        zero.update({f: 0.0 for f in _SUM_FIELDS})
        try:
            tennis_db.upsert_tennis_position(zero)
        except Exception as e:  # noqa: BLE001 - riprova al prossimo giro
            written[key] = info
            logger.debug("[tennis-pos] azzeramento KO %s/%s: %s", market_id, sel, e)


# ---------------------------------------------------------------------------
# Worker principale
# ---------------------------------------------------------------------------
def _reject_cross_mode(rid: int, row: Dict[str, Any], runner_mode_l: str) -> None:
    """Marca 'error' una riga la cui mode dichiarata NON è servibile da questo runner (C1).

    Mirror di ``live_order_worker._fail_cross_mode``: un runner gira in UNA sola mode; una
    riga della mode opposta (misconfig o residuo) va RIFIUTATA SENZA ESECUZIONE, mai lasciata
    'pending' all'infinito né eseguita nella mode sbagliata (denaro reale)."""
    declared = _declared_mode(row)
    msg = (
        f"mode '{declared}' non servibile dal runner in modalità '{runner_mode_l}' "
        f"(TENNIS_LIVE_ORDER_MODE={runner_mode_l.upper()}): rifiutata, NON eseguita"
    )
    try:
        tennis_db.write_tennis_order_error(
            rid, _result(ok=False, action=_declared_action(row), mode=declared,
                         cmd=row, cust_ref=_cust_ref(rid), error=msg))
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-order] scrittura cross-mode %s KO: %s", rid, e)


import itertools as _itertools

_LOCAL_SID = _itertools.count(9_000_000_000)
_LOCAL_TENNIS_ACTIONS = frozenset({"place", "cancel", "replace", "greenup"})
# fix review HIGH: dedup per client_ref (mai doppia esecuzione su reinvio)
_LOCAL_SEEN: Dict[str, tuple] = {}
_LOCAL_SEEN_TTL = 300.0


def _process_local_requests(flumine: Any, session: Any, runner_mode_l: str) -> None:
    """A7 — comandi dal canale locale desktop: STESSO _dispatch della coda tennis
    (greenup incluso: hedge calcolato dalle esposizioni fresche). Il comando viene poi
    REGISTRATO nella coda DB (status done/error) per storico/audit. Il drain
    avviene nel thread di QUESTO worker (un solo thread tocca flumine)."""
    from .. import local_channel

    ch = local_channel.get_channel()
    if ch is None:
        return
    for req in ch.pop_requests():
        try:
            if req.method == "snapshot":
                # tennis: snapshot iniziale via DB (le push tengono fresco il resto)
                ch.respond(req, True, {"orders": [], "positions": []})
                continue
            cmd = dict(req.params)
            action = str(cmd.get("action") or "")
            if action not in _LOCAL_TENNIS_ACTIONS:
                ch.respond(req, False, error=f"azione non supportata dal canale locale tennis: {action}")
                continue
            if str(cmd.get("mode") or "") != runner_mode_l:
                ch.respond(req, False,
                           error=f"mode richiesta '{cmd.get('mode')}' diversa dal runner '{runner_mode_l}'")
                continue
            client_ref = str(cmd.get("client_ref") or "") or None
            if client_ref:
                import time as _t

                hit = _LOCAL_SEEN.get(client_ref)
                if hit and _t.monotonic() - hit[0] <= _LOCAL_SEEN_TTL:
                    ch.respond(req, hit[1], hit[2],
                               error=None if hit[1] else "comando già eseguito (dedup)")
                    continue
            sid = next(_LOCAL_SID)
            cust_ref = ("awtq" + str(sid))[:32]
            status = "done"
            try:
                cmd_parsed = parse_order_payload({"payload": cmd, "id": sid})
                result = _dispatch(flumine, session, cmd_parsed, cust_ref)
            except Exception as ex:  # noqa: BLE001
                status = "error"
                result = _result(ok=False, action=action, mode=runner_mode_l,
                                 cmd=cmd, cust_ref=cust_ref, error=str(ex))
            ch.respond(req, bool(result.get("ok")), result,
                       error=None if result.get("ok") else result.get("error"))
            if client_ref:
                import time as _t

                _LOCAL_SEEN[client_ref] = (_t.monotonic(), bool(result.get("ok")), result)
            if result.get("ok") and action in ("place", "replace", "greenup"):
                rec = (getattr(session, "tracked_orders", {}) or {}).get(cust_ref)                     if session is not None else None
                order = rec.get("order") if isinstance(rec, dict) else None
                _mirror_order(runner_mode_l, _event_id_of(session, cmd.get("market_id")),
                              cust_ref, order, cmd_parsed)
            # registrazione best-effort nella coda DB (storico, mai bloccante)
            try:
                sb = tennis_db.get_tennis_client()
                sb.table("tennis_live_order_queue").insert({
                    "client_ref": f"local{sid}",
                    "payload": cmd,
                    "status": status,
                    "result": result,
                    "error": result.get("error"),
                    "processed_at": tennis_db._now_iso(),
                }).execute()
            except Exception as ex:  # noqa: BLE001
                logger.warning("[tennis-local] registrazione comando KO: %s", str(ex)[:120])
        except Exception:  # noqa: BLE001 - mai far cadere il worker
            logger.exception("[tennis-local] comando locale KO")
            try:
                ch.respond(req, False, error="errore interno")
            except Exception:  # noqa: BLE001
                pass


# SPLIT-THROTTLE (audit latenza 17/07, parità col calcio): il drain del canale
# LOCALE (desktop, in-memory) gira a OGNI tick del worker — è lui che dà la
# reattività al click (0.15s con l'env dell'exe); la lettura della coda su DB
# (fallback browser esterni) resta throttlata a ~1s, così abbassare il tick
# NON moltiplica le query Supabase. Stesso design di live_order_worker (calcio).
_DB_QUEUE_MIN_INTERVAL_S = float(os.getenv("TENNIS_DB_QUEUE_POLL_SEC", "1.0"))
_last_db_queue_poll = 0.0


def tennis_live_order_worker(context: dict, flumine: Any, session: Any = None) -> None:  # noqa: ARG001
    global _last_db_queue_poll
    runner_mode = _runner_mode()
    if runner_mode not in ("PAPER", "LIVE"):
        return  # OFF/ignoto: worker inerte (non dovrebbe nemmeno essere registrato)
    runner_mode_l = runner_mode.lower()
    # A7: drain dei comandi desktop PRIMA della coda DB (stesso path _dispatch)
    _process_local_requests(flumine, session, runner_mode_l)
    now_m = time.monotonic()
    if now_m - _last_db_queue_poll < _DB_QUEUE_MIN_INTERVAL_S:
        return  # coda DB: al massimo ~1 lettura/s, qualunque sia il tick
    _last_db_queue_poll = now_m
    try:
        rows = tennis_db.list_pending_tennis_orders(limit=5)
    except Exception as e:  # noqa: BLE001
        logger.warning("[tennis-order] list pending KO: %s", e)
        rows = []
    for row in rows:
        rid = row.get("id")
        if rid is None:
            continue
        # CROSS-MODE (C1): una riga della mode opposta NON va eseguita. Claim atomico + error.
        if _declared_mode(row) != runner_mode_l:
            if tennis_db.claim_tennis_order(rid):
                _reject_cross_mode(rid, row, runner_mode_l)
            continue
        if not tennis_db.claim_tennis_order(rid):
            continue  # preso da un altro poll
        cust_ref = _cust_ref(rid)
        result = None
        try:
            cmd = parse_order_payload(row)
            result = _dispatch(flumine, session, cmd, cust_ref)
            tennis_db.write_tennis_order_done(rid, result)
            if result.get("ok") and cmd["action"] in ("place", "replace", "greenup"):
                rec = (getattr(session, "tracked_orders", {}) or {}).get(cust_ref) \
                    if session is not None else None
                order = rec.get("order") if isinstance(rec, dict) else None
                _mirror_order(cmd["mode"], _event_id_of(session, cmd.get("market_id")),
                              cust_ref, order, cmd)
        except Exception as e:  # noqa: BLE001 - riga in error, mai crash del runner
            logger.warning("[tennis-order] riga %s KO: %s", rid, e)
            mode = _declared_mode(row)
            # BUG FIX cert 10/07 (VISTO DAL VIVO): se il DISPATCH è riuscito e a fallire
            # è stata solo la SCRITTURA dell'esito, un errore generico fa credere
            # l'ordine NON eseguito (l'utente lo ripete = doppio ordine con soldi veri).
            # Si RITENTA il done; se fallisce ancora, l'errore DICHIARA che l'ordine
            # È STATO eseguito ("NON reinviare").
            if isinstance(result, dict) and result.get("ok"):
                try:
                    tennis_db.write_tennis_order_done(rid, result)
                    continue
                except Exception:  # noqa: BLE001 - retry esaurito: errore ONESTO sotto
                    logger.exception("[tennis-order] retry write_done %s KO", rid)
                err_msg = ("ORDINE ESEGUITO ma esito non registrato (errore di scrittura: "
                           f"{str(e)[:120]}) — NON reinviare: verifica la lista ordini")
                try:
                    tennis_db.write_tennis_order_error(
                        rid, _result(ok=False, action=_declared_action(row), mode=mode,
                                     cmd=row, cust_ref=cust_ref, error=err_msg))
                except Exception:  # noqa: BLE001 - perfino l'errore è best-effort
                    logger.exception("[tennis-order] scrittura errore %s KO", rid)
                continue
            try:
                tennis_db.write_tennis_order_error(
                    rid, _result(ok=False, action=_declared_action(row),
                                 mode=mode, cmd=row, cust_ref=cust_ref, error=str(e)))
            except Exception:  # noqa: BLE001 - perfino l'errore è best-effort
                logger.exception("[tennis-order] scrittura errore %s KO", rid)
    # riconcilia i fill degli ordini tracciati (manuali + bot), write-on-change + prune.
    _reconcile_tracked(session, flumine)
