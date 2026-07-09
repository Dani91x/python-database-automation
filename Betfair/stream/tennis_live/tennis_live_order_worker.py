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
                  cmd: Dict[str, Any], source: str = "manual") -> None:
    """Specchia l'ordine in ``tennis_live_orders`` (best-effort).

    ``source`` = 'manual' (ordini da coda) | bot_key (ordini di un bot ospitato, fix #8).
    ``status`` è NOT NULL nello specchio: se lo snapshot non ha status (ordine non ancora
    materializzato) si salta la scrittura invece di violare il vincolo (fix #6)."""
    snap = _order_snapshot(order)
    status = snap.get("status")
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


def _dispatch(flumine: Any, session: Any, cmd: Dict[str, Any], cust_ref: str) -> Dict[str, Any]:
    action = cmd["action"]
    if action == "place":
        return _do_place(flumine, session, cmd, cust_ref)
    if action == "cancel":
        return _do_cancel(flumine, cmd, cust_ref)
    if action == "replace":
        return _do_replace(flumine, session, cmd, cust_ref)
    if action == "greenup":
        # FAIL LOUDLY (fix #9): il green-up NON è implementato lato tennis. Un tempo ritornava
        # ok=True (no-op) → il frontend lo dava per ESEGUITO mentre la posizione restava aperta
        # (azione di RISCHIO: bugia money-critical). Ora solleva → riga 'error' col motivo,
        # così la UI mostra un errore reale e l'utente può chiudere a mano.
        raise ValueError(
            "greenup non supportato dal runner tennis: usare place/cancel/replace per "
            "chiudere manualmente (azione non eseguita)"
        )
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

    # 1) ordini manuali
    for cust_ref, rec in list(getattr(session, "tracked_orders", {}).items()):
        try:
            order = _trade_current_order(rec.get("trade"), rec.get("order"))
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
        mode = _runner_mode().lower()  # bot → paper|live (OFF non registra il worker)
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
    mode = _runner_mode().lower()
    seen: set = set()
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
            if (mode, market_id, sel, hcap) in seen:
                continue
            seen.add((mode, market_id, sel, hcap))
            row = _position_row(market, strategy, mode, event_id, market_id, sel, hcap)
            if row is not None:
                try:
                    tennis_db.upsert_tennis_position(row)
                except Exception as e:  # noqa: BLE001
                    logger.debug("[tennis-pos] upsert KO %s/%s: %s", market_id, sel, e)


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
    (greenup incluso: fallisce forte come da design). Il comando viene poi
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
            if result.get("ok") and action in ("place", "replace"):
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


def tennis_live_order_worker(context: dict, flumine: Any, session: Any = None) -> None:  # noqa: ARG001
    runner_mode = _runner_mode()
    if runner_mode not in ("PAPER", "LIVE"):
        return  # OFF/ignoto: worker inerte (non dovrebbe nemmeno essere registrato)
    runner_mode_l = runner_mode.lower()
    # A7: drain dei comandi desktop PRIMA della coda DB (stesso path _dispatch)
    _process_local_requests(flumine, session, runner_mode_l)
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
        try:
            cmd = parse_order_payload(row)
            result = _dispatch(flumine, session, cmd, cust_ref)
            tennis_db.write_tennis_order_done(rid, result)
            if result.get("ok") and cmd["action"] in ("place", "replace"):
                rec = (getattr(session, "tracked_orders", {}) or {}).get(cust_ref) \
                    if session is not None else None
                order = rec.get("order") if isinstance(rec, dict) else None
                _mirror_order(cmd["mode"], _event_id_of(session, cmd.get("market_id")),
                              cust_ref, order, cmd)
        except Exception as e:  # noqa: BLE001 - riga in error, mai crash del runner
            logger.warning("[tennis-order] riga %s KO: %s", rid, e)
            mode = _declared_mode(row)
            tennis_db.write_tennis_order_error(
                rid, _result(ok=False, action=_declared_action(row),
                             mode=mode, cmd=row, cust_ref=cust_ref, error=str(e)))
    # riconcilia i fill degli ordini tracciati (manuali + bot), write-on-change + prune.
    _reconcile_tracked(session, flumine)
