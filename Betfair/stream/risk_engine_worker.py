"""risk_engine_worker.py — BackgroundWorker del RUNNER che ARMA/monitora le regole risk
(``betfair_live_risk_rules``) e, allo scattare, ACCODA l'ordine di chiusura/copertura nella
coda esistente ``betfair_live_order_requests`` (STESSO path audited/mirror di ogni ordine).

Per chi: gira DENTRO il processo del runner, aggiunto al framework flumine come
``BackgroundWorker(function=risk_engine_worker, ...)`` SOLO quando LIVE_ORDER_MODE ∈ {PAPER, LIVE}.
Ad ogni poll:
  - legge le regole ``armed`` della mode corrente;
  - risolve il Market e legge LTP + best price + esposizioni MATCHED FRESCHE (da flumine);
  - valuta con ``trading/risk_engine`` (matematica pura, già verificata):
      * ``offset``      → piazza UNA volta l'ordine OPPOSTO resting al target profit ('place'),
                          poi marca la regola 'done';
      * ``stop_loss`` / ``take_profit`` / ``trailing_stop`` → se scatta, accoda un ``greenup``
        (flatten: chiude la posizione MATCHED al best opposto, con reduces_liability) e marca
        la regola 'triggered'. Il trailing aggiorna l'estremo favorevole (write-on-change).

MONEY-CRITICAL. La CHIUSURA riusa i path PROVATI (place/greenup del live_order_worker): stesse
validazioni, stesso specchio DB, stesse garanzie. Anti-doppio-trigger:
  * client_ref della regola UNIQUE (una richiesta = una regola);
  * quando scatta, l'accodamento usa un client_ref DETERMINISTICO ``risk<rule_id>`` → il vincolo
    UNIQUE della coda ordini garantisce UN SOLO ordine di chiusura anche se la regola venisse
    rivalutata prima di risultare 'triggered'.

⚠️ SOFTWARE-SIDE: se il runner cade, stop/offset NON esistono (come in Bet Angel/Cymatic/Fairbot).
BEST-EFFORT: qualunque errore su una regola è scritto in ``error`` e non fa cadere il runner.
Testabile a unità: framework/Market/blotter/coda mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import live_order_worker as low
from .trading import risk_engine

logger = logging.getLogger(__name__)

_TABLE = "betfair_live_risk_rules"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch() -> int:
    try:
        from . import config_stream
        return max(1, int(getattr(config_stream, "RISK_ENGINE_BATCH", 20)))
    except Exception:  # noqa: BLE001
        return 20


def _ltp(market: Any, selection_id: int, handicap: float) -> Optional[float]:
    """Last Traded Price della selezione dal market_book flumine (prezzo di riferimento per i
    trigger di prezzo). None se non disponibile. Difensivo su ogni livello."""
    mb = low._val(market, "market_book")
    if mb is None:
        return None
    runners = low._val(mb, "runners") or []
    for r in runners:
        if low._int(low._val(r, "selection_id")) != int(selection_id):
            continue
        rh = low._f(low._val(r, "handicap")) or 0.0
        if abs(rh - float(handicap or 0.0)) > 1e-6:
            continue
        return low._f(low._val(r, "last_price_traded"))
    return None


def _read_armed_rules(sb: Any, mode_l: str) -> list:
    try:
        return (
            sb.table(_TABLE)
            .select("*")
            .eq("status", "armed")
            .eq("mode", mode_l)
            .order("id")
            .limit(_batch())
            .execute()
            .data
            or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura coda momentaneamente KO
        logger.warning("[risk] lettura regole armate KO: %s", str(ex)[:160])
        return []


def _update_rule(sb: Any, rule_id: int, fields: Dict[str, Any]) -> None:
    payload = dict(fields)
    payload["updated_at"] = _now_iso()
    sb.table(_TABLE).update(payload).eq("id", rule_id).execute()


def _enqueue(sb: Any, payload: Dict[str, Any]) -> Optional[int]:
    """Accoda un comando nella coda ordini via RPC idempotente. Ritorna l'id richiesta o None."""
    res = sb.rpc("request_betfair_live_order", {"p": payload}).execute()
    data = getattr(res, "data", None)
    try:
        return int(data) if data is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Gestione di UNA regola
# ---------------------------------------------------------------------------
def _handle_offset(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str) -> None:
    """Offset: piazza UNA volta l'ordine opposto resting al target profit, poi 'done'."""
    params = rule.get("params") or {}
    entry_side = str(rule.get("entry_side"))
    entry_price = low._f(rule.get("entry_price"))
    entry_size = low._f(rule.get("entry_size"))
    if entry_price is None or entry_size is None or entry_size <= 0:
        _update_rule(sb, rule["id"], {"status": "error", "error": "offset: entry_price/entry_size mancanti"})
        return
    order = risk_engine.offset_order(
        entry_side, entry_price, entry_size,
        offset_ticks=risk_engine._int_param(params, "offset_ticks"),
        offset_pct=risk_engine._num(params, "offset_pct"),
        greening=False,   # v1: offset non-green (size = entry_size), ordine resting valido
    )
    if not order.actionable:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"offset non calcolabile: {order.note}"})
        return
    client_ref = f"risk{rule['id']}"
    payload = {
        "client_ref": client_ref,
        "action": "place",
        "mode": mode_l,
        "market_id": rule["market_id"],
        "selection_id": rule["selection_id"],
        "handicap": rule.get("handicap") or 0,
        "side": order.side,
        "price": order.price,
        "size": order.size,
        "persistence": (params.get("persistence") or "LAPSE"),
        "params": {"risk_rule_id": rule["id"]},
    }
    req_id = _enqueue(sb, payload)
    _update_rule(sb, rule["id"], {
        "status": "done",
        "enqueued_client_ref": client_ref,
        "enqueued_request_id": req_id,
        "triggered_at": _now_iso(),
        "result": {"note": order.note, "side": order.side, "price": order.price, "size": order.size},
    })


def _handle_monitored(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    """stop_loss / take_profit / trailing_stop: valuta e, se scatta, accoda un greenup (flatten)."""
    market = low._resolve_market(flumine, rule.get("market_id"))
    sel = int(rule["selection_id"])
    hcap = float(rule.get("handicap") or 0)
    ltp = _ltp(market, sel, hcap)
    best_back, best_lay = low._best_prices(market, sel, hcap)
    w, l = low._read_matched_exposures(flumine, market, strategy, sel, hcap)

    decision = risk_engine.evaluate_rule(
        rule_type=str(rule.get("rule_type")),
        entry_side=str(rule.get("entry_side")),
        entry_price=low._f(rule.get("entry_price")),
        params=rule.get("params") or {},
        current_price=ltp,
        matched_if_win=w,
        matched_if_lose=l,
        best_back_price=best_back,
        best_lay_price=best_lay,
        trail_extreme=low._f(rule.get("trail_extreme")),
    )

    if not decision.fire:
        # write-on-change del solo estremo del trailing (non spammare il DB).
        if decision.trail_extreme is not None:
            prev = low._f(rule.get("trail_extreme"))
            if prev is None or abs(prev - decision.trail_extreme) > 1e-9:
                _update_rule(sb, rule["id"], {"trail_extreme": decision.trail_extreme})
        return

    # Kill-switch (env o UI/DB): freno d'emergenza — non accodare chiusure, tieni armata.
    if low._kill_switch() or low._db_kill_switch():
        logger.warning("[risk] kill-switch ATTIVO: regola %s non innescata", rule.get("id"))
        return

    # Posizione già piatta → niente da chiudere: chiudi la regola come 'done' (non lasciarla armata).
    if abs(w - l) < risk_engine.FLAT_EPS:
        _update_rule(sb, rule["id"], {
            "status": "done", "triggered_at": _now_iso(),
            "result": {"note": f"{decision.reason}; posizione già piatta, nessun ordine"},
        })
        return

    client_ref = f"risk{rule['id']}"
    payload = {
        "client_ref": client_ref,
        "action": "greenup",
        "mode": mode_l,
        "market_id": rule["market_id"],
        "selection_id": rule["selection_id"],
        "handicap": rule.get("handicap") or 0,
        "params": {"fraction": 1.0, "risk_rule_id": rule["id"]},
    }
    req_id = _enqueue(sb, payload)
    _update_rule(sb, rule["id"], {
        "status": "triggered",
        "enqueued_client_ref": client_ref,
        "enqueued_request_id": req_id,
        "triggered_at": _now_iso(),
        "trail_extreme": decision.trail_extreme if decision.trail_extreme is not None else rule.get("trail_extreme"),
        "result": {"note": decision.reason, "action": "greenup"},
    })


def _process_rule(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    rule_type = str(rule.get("rule_type") or "")
    if rule_type == "offset":
        _handle_offset(sb, flumine, rule, mode_l)
    elif rule_type in ("stop_loss", "take_profit", "trailing_stop"):
        _handle_monitored(sb, flumine, rule, mode_l, strategy)
    else:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"rule_type sconosciuto: {rule_type!r}"})


def _process_once(sb: Any, flumine: Any, strategy: Any = None) -> int:
    mode = low._live_order_mode()
    if mode not in ("PAPER", "LIVE"):
        return 0
    # Fase 6: aggiorna lo snapshot settings (kill-switch UI condiviso con l'order worker).
    low._refresh_settings(sb)
    mode_l = mode.lower()
    rules = _read_armed_rules(sb, mode_l)
    handled = 0
    for rule in rules:
        rid = rule.get("id")
        try:
            _process_rule(sb, flumine, rule, mode_l, strategy)
        except Exception:  # noqa: BLE001 - errore TRANSITORIO: NON disarmare la regola
            # MONEY-CRITICAL (fix review MEDIUM): un errore transitorio (mercato momentaneamente
            # assente in _resolve_market, blip DB sull'update di trail_extreme) NON deve mettere
            # la regola in 'error'. La query processa solo le 'armed', quindi marcarla 'error'
            # la escluderebbe PER SEMPRE → uno stop-loss/trailing che protegge una posizione
            # aperta verrebbe DISARMATO in silenzio. La lasciamo 'armed' e si ritenta al giro
            # dopo. Le condizioni DAVVERO invalide (rule_type ignoto, offset senza entry_price)
            # sono già marcate 'error' ESPLICITAMENTE dentro i singoli handler (permanenti).
            logger.warning("[risk] regola %s: errore transitorio, resta armata (retry)", rid)
        handled += 1
    return handled


def risk_engine_worker(context: dict, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """BackgroundWorker flumine (firma: context, flumine, **func_kwargs).

    Aggiunto al framework SOLO se LIVE_ORDER_MODE ∈ {PAPER, LIVE} (vedi runner). Non solleva MAI.
    ``strategy`` (LiveTradingStrategy) è necessaria per leggere le esposizioni MATCHED (flatten).
    """
    if flumine is None:
        return
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001 - DB non raggiungibile: salta il giro
        logger.warning("[risk] supabase non disponibile: %s", str(ex)[:160])
        return
    try:
        _process_once(sb, flumine, strategy)
    except Exception as ex:  # noqa: BLE001 - ultima rete di sicurezza
        logger.warning("[risk] ciclo KO: %s", str(ex)[:200])
