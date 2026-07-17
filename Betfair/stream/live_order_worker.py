"""live_order_worker.py — BackgroundWorker del RUNNER live che processa la coda
``betfair_live_order_requests`` PIAZZANDO ORDINI (paper o REALI, soldi veri in mode='live').

Per chi: gira DENTRO il processo del runner (Betfair/stream/runner.py), aggiunto al
framework flumine come ``BackgroundWorker(function=live_order_worker, ...)`` SOLO quando
``LIVE_ORDER_MODE`` ∈ {PAPER, LIVE}. Ad ogni poll fa UN passo:
  - claim atomico ``pending → processing`` (una sola esecuzione per riga);
  - risolve il ``Market`` dal framework (``flumine.markets.markets[market_id]``);
  - dispatch per azione: ``place`` / ``cancel`` / ``replace`` / ``place_submin``;
  - usa ``live_order_build.build_order`` (validazione = ultima barriera money-critical) e le
    API NATIVE del Market (``place_order`` / ``cancel_order`` / ``replace_order``);
  - scrive esito + bet_id nella riga (shape stabile ``LiveOrderResult``, letta dal frontend).

MONEY-CRITICAL. Garanzie anti-doppio-ordine REALI (identiche a order_worker.py):
  * CLAIM atomico pending→processing: ogni riga è eseguita UNA sola volta (anche con più
    worker/poll concorrenti, una sola ``update`` vince la transizione).
  * client_ref UNIQUE sulla coda (vincolo DB in betfair_live_order_queue.sql): la stessa
    richiesta del frontend non genera due righe → enqueue idempotente, retry di rete sicuro.
  Queste due — claim atomico + client_ref UNIQUE — sono l'INTERA garanzia anti-doppio-ordine.
  NON esiste alcun customerRef Betfair "deterministico": l'attributo che flumine invia a
  Betfair è ``order.customer_order_ref = name_hash + sep + order.id`` (order.id = uuid1, NON
  deterministico). Il nostro ``awlq<id>`` (vedi ``_cust_ref``) è un ref INTERNO di
  correlazione richiesta↔ordine: va in ``order.notes``/``order.context`` ed è riletto da
  ``LiveTradingStrategy.process_orders`` per legare la riga di coda allo specchio DB —
  NON viaggia mai verso Betfair e NON fa alcun de-dup lato Exchange.
  * NON ri-processa MAI righe ``done``/``error`` né righe ``processing`` (crash a metà →
    la riga resta ``processing`` e va riconciliata A MANO, mai ripiazzata in automatico).
    UNICA ECCEZIONE deliberata: le sequenze ``place_submin`` in corso vivono in
    ``processing`` e vengono fatte avanzare di uno step ad ogni poll finché terminali
    (lo SubminState è persistito in ``result.submin_state``, quindi l'avanzamento è
    idempotente e ripristinabile — vedi trading/submin.py).

BEST-EFFORT: qualunque errore di una riga è scritto in ``error`` e NON deve mai far cadere
il runner. Il fill (size_matched/avg_price) arriva ASINCRONO (LIVE via order_stream, PAPER
via SimulatedExecution) ed è riflesso nello specchio DB da ``LiveTradingStrategy.process_orders``.

Testabile a unità: framework, Market, blotter e coda sono mockabili; nessuna rete, nessun login.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TABLE = "betfair_live_order_requests"

# customerStrategyRef passato a market.place_order (<=15 char per Betfair).
CUSTOMER_STRATEGY_REF = "live"

# Azioni che RIDUCONO il rischio (ritiro resting / hedge self-bounded): col kill-switch
# attivo restano le UNICHE eseguibili — il freno blocca le aperture, mai le vie di uscita.
_CLOSING_ACTIONS = frozenset({"cancel", "greenup", "cashout_all", "cashout_event"})


# ---------------------------------------------------------------------------
# Config (letta da config_stream se presente, altrimenti da .env). Wrappata in
# funzioni così che il runner E i test possano sovrascriverla deterministicamente.
# ---------------------------------------------------------------------------
def _cfg_attr(name: str) -> Any:
    try:
        from . import config_stream  # import lazy: evita cicli all'avvio
        if hasattr(config_stream, name):
            return getattr(config_stream, name)
    except Exception:  # noqa: BLE001 - config opzionale, fallback a env
        pass
    return None


def _live_order_mode() -> str:
    """OFF | PAPER | LIVE (UPPER) RI-LETTA LIVE ad ogni ciclo (no riavvio). Default OFF.

    Money-critical: come kill-switch/cap, un DOWNGRADE di sicurezza (LIVE→PAPER/OFF) deve
    avere effetto SUBITO. Usa ``config_stream.live_order_mode()`` che rilegge l'env ad ogni
    chiamata; NON la costante ``config_stream.LIVE_ORDER_MODE`` (congelata all'import).
    Fallback diretto a ``os.getenv('LIVE_ORDER_MODE','OFF')``.
    """
    try:
        from . import config_stream  # import lazy: evita cicli all'avvio
        if hasattr(config_stream, "live_order_mode"):
            return str(config_stream.live_order_mode()).upper()
    except Exception:  # noqa: BLE001 - config opzionale, fallback a env
        pass
    return os.getenv("LIVE_ORDER_MODE", "OFF").strip().upper()


def _jurisdiction() -> str:
    val = _cfg_attr("BETFAIR_JURISDICTION")
    if val is None:
        val = os.getenv("LIVE_BETFAIR_JURISDICTION", "it")
    return str(val).lower()


def _batch() -> int:
    val = _cfg_attr("LIVE_ORDER_QUEUE_BATCH")
    if val is None:
        val = os.getenv("LIVE_ORDER_QUEUE_BATCH", "5")
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return 5


def _max_stake() -> Optional[float]:
    """Cap di stake per ordine RI-LETTO LIVE ad ogni chiamata (modificabile senza riavvio).
    ``None`` = NESSUN cap (scelta utente 2026-07-01: importi liberi; cap OPT-IN via env).

    Usa ``config_stream.live_max_stake_per_order()`` che rilegge l'env (NON la costante
    congelata all'import). Fallback diretto all'env (vuoto/0/non numerico → None).
    """
    try:
        from . import config_stream  # import lazy: evita cicli all'avvio
        if hasattr(config_stream, "live_max_stake_per_order"):
            return config_stream.live_max_stake_per_order()
    except Exception:  # noqa: BLE001 - config opzionale, fallback a env
        pass
    raw = os.getenv("LIVE_MAX_STAKE_PER_ORDER", "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    return val if val > 0 else None


def _kill_switch() -> bool:
    """Kill-switch RI-LETTO LIVE ad ogni ciclo (freno d'emergenza, niente riavvio).

    Usa ``config_stream.live_kill_switch()`` che rilegge l'env ad ogni chiamata: esportare
    ``LIVE_KILL_SWITCH=true`` blocca ogni place al giro successivo. NON usa la costante
    ``config_stream.LIVE_KILL_SWITCH`` (congelata all'import). Fallback diretto all'env.
    """
    try:
        from . import config_stream  # import lazy: evita cicli all'avvio
        if hasattr(config_stream, "live_kill_switch"):
            return bool(config_stream.live_kill_switch())
    except Exception:  # noqa: BLE001 - config opzionale, fallback a env
        pass
    return os.getenv("LIVE_KILL_SWITCH", "false").strip().lower() == "true"


# ---------------------------------------------------------------------------
# Fase 6 — settings runtime (kill-switch da UI / limiti), audit, rate-limit.
# Snapshot letto UNA volta per ciclo (thread singolo del worker) → nessun read DB
# per-ordine. I limiti sono OPT-IN (NULL in betfair_live_settings = disattivato).
# §7.2: la LOGICA delle guardie (finestra rate condivisa + math esposizione) vive in
# trading/controls.py — unica implementazione per pre-check del worker e control nativi.
# ---------------------------------------------------------------------------
from .trading.controls import rate_violation, selection_exposure_violation

_SETTINGS: Dict[str, Any] = {}


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _refresh_settings(sb: Any) -> None:
    """Aggiorna lo snapshot dei settings (una volta per ciclo). Best-effort: KO → invariato.

    MONEY-CRITICAL (fix review HIGH): REBIND ATOMICO, mai ``clear()``+``update()``. Order worker
    e risk worker sono due thread flumine che leggono ``_SETTINGS`` concorrentemente: un
    clear()-poi-update() lascerebbe una finestra col dict VUOTO in cui ``_db_kill_switch()``
    tornerebbe False → il freno d'emergenza sarebbe saltato per un intero ciclo. Costruiamo il
    nuovo dict localmente e ri-leghiamo il nome globale (assegnazione atomica): ogni lettore
    osserva sempre lo stato VECCHIO o quello NUOVO completo, mai uno parziale.
    """
    global _SETTINGS
    try:
        res = sb.rpc("get_live_settings", {}).execute()
        data = getattr(res, "data", None)
        if isinstance(data, dict):
            _SETTINGS = dict(data)
    except Exception:  # noqa: BLE001 - settings opzionali; il worker resta operativo
        pass


def _db_kill_switch() -> bool:
    return bool(_SETTINGS.get("kill_switch"))


def _max_exposure_per_selection() -> Optional[float]:
    return _f(_SETTINGS.get("max_exposure_per_selection"))


def _max_orders_per_min() -> Optional[int]:
    return _int(_SETTINGS.get("max_orders_per_min"))


# Cadenza runtime (#15): il worker si auto-pacizza al target letto da betfair_live_settings
# (order_poll_sec / risk_poll_sec) SENZA riavvio. Solo RALLENTAMENTO: il BackgroundWorker è
# registrato a una cadenza base; se il target è più lento, si saltano cicli fino a rispettarlo.
# Target non impostato (NULL) → nessun throttle (cadenza = base, default invariato).
_LAST_CYCLE: Dict[str, float] = {}


def _throttled(name: str, target_sec: Optional[float]) -> bool:
    """True se questo ciclo va SALTATO per rispettare il target di cadenza runtime.
    target None/<=0 → mai throttle (comportamento di default invariato)."""
    if not target_sec or target_sec <= 0:
        return False
    now = _now_epoch()
    if now - _LAST_CYCLE.get(name, 0.0) < float(target_sec):
        return True
    _LAST_CYCLE[name] = now
    return False


def _order_poll_target() -> Optional[float]:
    """Cadenza target del worker coda da settings (runtime). None = nessun override."""
    v = _f(_SETTINGS.get("order_poll_sec"))
    return v if (v and v > 0) else None


def _risk_poll_target() -> Optional[float]:
    """Cadenza target del risk worker da settings (runtime). None = nessun override."""
    v = _f(_SETTINGS.get("risk_poll_sec"))
    return v if (v and v > 0) else None


def _rate_guard(extra: int = 1) -> None:
    """Pre-check ESPLICITO rate-limit (§7.2: logica in trading/controls.rate_violation,
    finestra CONDIVISA coi control nativi). Usato SOLO dove serve atomicità: dutch
    (capacità per TUTTE le gambe prima di piazzarne una) e submin (prima di persistere
    lo step INIT). Il place semplice è coperto dal LiveRateControl nativo, sincrono
    dentro market.place_order → errore esplicito via _place_or_raise."""
    msg = rate_violation(_max_orders_per_min(), extra=extra)
    if msg is not None:
        raise ValueError(msg)


def _check_exposure_guard(market: Any, strategy: Any, selection_id: int, handicap: float, order_risk: float) -> None:
    """Pre-check ESPLICITO max esposizione per selezione (§7.2: math in
    trading/controls.selection_exposure_violation, la STESSA del LiveExposureControl
    nativo — mai due implementazioni). Solleva sul superamento; fail-open difensivo
    (dati non calcolabili → non blocca) dentro la funzione condivisa."""
    msg = selection_exposure_violation(
        _max_exposure_per_selection(), market, strategy, selection_id, handicap, order_risk
    )
    if msg is not None:
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Helper generici
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _cust_ref(rid: int) -> str:
    """Ref INTERNO di correlazione richiesta↔ordine (``awlq<id>``), NON un customerRef Betfair.

    Salvato in ``order.notes``/``order.context`` da live_order_build e riletto da
    ``LiveTradingStrategy.process_orders`` per legare la riga di coda allo specchio DB.
    Non viaggia verso Betfair (lì va ``order.customer_order_ref`` = name_hash+sep+id) e non
    fornisce de-dup lato Exchange: l'anti-doppio-ordine è claim atomico + client_ref UNIQUE.
    """
    return ("awlq" + str(rid))[:32]


# ---------------------------------------------------------------------------
# Risoluzione Market / ordini dal framework flumine
# ---------------------------------------------------------------------------
def _resolve_market(flumine: Any, market_id: Optional[str]) -> Any:
    """Market dal framework. Solleva ValueError se non sottoscritto (no ordine alla cieca)."""
    if not market_id:
        raise ValueError("market_id mancante per risolvere il Market")
    market = None
    try:
        market = flumine.markets.markets.get(market_id)
    except Exception:  # noqa: BLE001 - struttura inattesa → trattata come non trovato
        market = None
    if market is None:
        raise ValueError(f"market {market_id} non sottoscritto nel runner")
    return market


def _find_order_by_bet_id(flumine: Any, market_id: Optional[str], bet_id: str) -> Optional[Any]:
    """Trova l'ordine per bet_id usando le lookup NATIVE del blotter flumine.

    Prima nel mercato indicato (``blotter.get_order_bet_id``), poi — se ``market_id`` è
    assente o non combacia — scandendo tutti i mercati del framework. None se non trovato.
    """
    if not bet_id:
        return None
    # 1) mercato indicato
    try:
        if market_id:
            m = flumine.markets.markets.get(market_id)
            if m is not None:
                o = m.blotter.get_order_bet_id(bet_id)
                if o is not None:
                    return o
    except Exception:  # noqa: BLE001 - best-effort, si passa allo scan
        pass
    # 2) scan di tutti i mercati
    try:
        for m in flumine.markets:
            o = m.blotter.get_order_bet_id(bet_id)
            if o is not None:
                return o
    except Exception:  # noqa: BLE001
        pass
    return None


def _order_cust_ref(order: Any) -> Optional[str]:
    """Rilegge il NOSTRO ref interno deterministico (awlq<id>) annotato dall'ordine in
    ``notes``/``context['customer_order_ref']`` da live_order_build. None se assente."""
    for attr in ("notes", "context"):
        try:
            d = getattr(order, attr, None)
            if isinstance(d, dict):
                ref = d.get("customer_order_ref")
                if ref:
                    return str(ref)
        except Exception:  # noqa: BLE001 - struttura inattesa → ignora
            pass
    return None


def _find_order_by_cust_ref(
    flumine: Any, market_id: Optional[str], cust_ref: Optional[str]
) -> Optional[Any]:
    """Ritrova un ordine per il NOSTRO ref interno DETERMINISTICO (awlq<id>) scandendo il
    blotter (``notes``/``context['customer_order_ref']``).

    RICONCILIAZIONE post-crash (fix MEDIUM finestra di crash): se il processo cade tra il
    ``market.place_order`` REALE e la persistenza di order_id/bet_id, alla ripresa non
    abbiamo né l'uno né l'altro — ma l'ordine reale è già nel blotter (ricostruito
    dall'order stream) con il nostro ref interno. Ritrovarlo per ref evita un ordine ORFANO
    e, soprattutto, un RI-PIAZZAMENTO (advance_submin lo riconosce e non ripiazza).
    """
    if not cust_ref:
        return None

    def _scan(m: Any) -> Optional[Any]:
        try:
            for o in m.blotter:
                if _order_cust_ref(o) == cust_ref:
                    return o
        except Exception:  # noqa: BLE001 - blotter non iterabile / stato di confine
            return None
        return None

    # 1) mercato indicato
    try:
        if market_id:
            m = flumine.markets.markets.get(market_id)
            if m is not None:
                o = _scan(m)
                if o is not None:
                    return o
    except Exception:  # noqa: BLE001 - best-effort, si passa allo scan globale
        pass
    # 2) scan di tutti i mercati
    try:
        for m in flumine.markets:
            o = _scan(m)
            if o is not None:
                return o
    except Exception:  # noqa: BLE001
        pass
    return None


def _find_submin_order(
    flumine: Any,
    market_id: Optional[str],
    order_id: Optional[str],
    bet_id: Optional[str],
    cust_ref: Optional[str] = None,
) -> Optional[Any]:
    """Ritrova l'ordine di una sequenza submin tra un poll e l'altro.

    Prima per ``bet_id`` (quando assegnato), poi per l'id flumine dell'ordine
    (``order.id`` = chiave del blotter) persistito in ``result.submin_order_id``, infine —
    riconciliazione post-crash — per il ref interno deterministico ``cust_ref`` (awlq<id>).
    """
    if bet_id:
        o = _find_order_by_bet_id(flumine, market_id, bet_id)
        if o is not None:
            return o
    if order_id and market_id:
        try:
            m = flumine.markets.markets.get(market_id)
            if m is not None:
                return m.blotter[order_id]
        except Exception:  # noqa: BLE001 - non ancora nel blotter o id sconosciuto → prova il ref
            pass
    return _find_order_by_cust_ref(flumine, market_id, cust_ref)


# ---------------------------------------------------------------------------
# Lettura difensiva dello stato di un ordine flumine
# ---------------------------------------------------------------------------
def _val(order: Any, attr: str) -> Any:
    try:
        return getattr(order, attr)
    except Exception:  # noqa: BLE001 - alcune property possono sollevare in stati di confine
        return None


def _status_name(order: Any) -> Optional[str]:
    st = _val(order, "status")
    if st is None:
        return None
    name = getattr(st, "name", None)
    return name or str(st)


def _order_snapshot(order: Any) -> Dict[str, Any]:
    """Estrae i campi dell'ordine usati dallo specchio/esito (tutti opzionali, difensivi)."""
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


# ---------------------------------------------------------------------------
# Costruzione esito (shape stabile LiveOrderResult, condivisa con il frontend)
# ---------------------------------------------------------------------------
def _result(
    *,
    ok: bool,
    action: str,
    mode: str,
    request_row: Dict[str, Any],
    cust_ref: Optional[str],
    order: Any = None,
    price: Optional[float] = None,
    size: Optional[float] = None,
    side: Optional[str] = None,
    submin_step: Optional[str] = None,
    error: Optional[str] = None,
    detail: Optional[str] = None,
) -> Dict[str, Any]:
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
        "market_id": request_row.get("market_id") or snap.get("market_id"),
        "selection_id": (
            _int(request_row.get("selection_id"))
            if request_row.get("selection_id") is not None
            else snap.get("selection_id")
        ),
        "side": side or snap.get("side") or request_row.get("side"),
        "price": price if price is not None else snap.get("price"),
        "size": size if size is not None else snap.get("size"),
        "customer_order_ref": cust_ref,
        "submin_step": submin_step,
        "error": (str(error)[:300] if error is not None else None),
        "detail": (str(detail)[:300] if detail is not None else None),
    }


# ---------------------------------------------------------------------------
# Scritture sulla riga di coda
# ---------------------------------------------------------------------------
def _claim(sb: Any, rid: int) -> bool:
    """CLAIM atomico: pending → processing. True se questa chiamata l'ha preso."""
    claimed = (
        sb.table(_TABLE)
        .update({"status": "processing"})
        .eq("id", rid)
        .eq("status", "pending")
        .execute()
        .data
        or []
    )
    return len(claimed) > 0


def _audit(sb: Any, rid: int, result: Dict[str, Any], status: str) -> None:
    """Append-only sull'audit log (Fase 6, events log). Best-effort: non deve mai far cadere il
    worker né bloccare la scrittura dell'esito (un errore qui è silenziato)."""
    try:
        sb.table("betfair_live_audit").insert({
            "mode": result.get("mode"),
            "action": result.get("action"),
            "market_id": result.get("market_id"),
            "selection_id": result.get("selection_id"),
            "side": result.get("side"),
            "price": result.get("price"),
            "size": result.get("size"),
            "status": status,
            "error": result.get("error"),
            "request_id": rid,
            "detail": {"note": result.get("detail"), "bet_id": result.get("bet_id")},
        }).execute()
    except Exception:  # noqa: BLE001 - l'audit è best-effort, mai bloccante
        pass


# ---------------------------------------------------------------------------
# E37 — trade journal AUTOMATICO (contesto al momento dell'esecuzione)
# ---------------------------------------------------------------------------
_JOURNAL_WARNED_DAY: Dict[str, str] = {}  # anti-spam: un alert WARN al giorno


def _ltp_of(market: Any, selection_id: Optional[int], handicap: float) -> Optional[float]:
    """Last Traded Price della selezione dal market_book flumine (best-effort)."""
    if selection_id is None:
        return None
    mb = _val(market, "market_book")
    if mb is None:
        return None
    for r in _val(mb, "runners") or []:
        if _int(_val(r, "selection_id")) != int(selection_id):
            continue
        rh = _f(_val(r, "handicap")) or 0.0
        if abs(rh - float(handicap or 0.0)) > 1e-6:
            continue
        return _f(_val(r, "last_price_traded"))
    return None


def _level_pair(level: Any) -> Optional[list]:
    price = _level_price(level)
    if price is None:
        return None
    size = _f(level.get("size")) if isinstance(level, dict) else _f(_val(level, "size"))
    return [price, size]


def _book_snapshot(market: Any, selection_id: Optional[int], handicap: float) -> Optional[Dict[str, Any]]:
    """Top-3 livelli back/lay della selezione al momento del click (best-effort)."""
    if selection_id is None:
        return None
    mb = _val(market, "market_book")
    if mb is None:
        return None
    for r in _val(mb, "runners") or []:
        if _int(_val(r, "selection_id")) != int(selection_id):
            continue
        rh = _f(_val(r, "handicap")) or 0.0
        if abs(rh - float(handicap or 0.0)) > 1e-6:
            continue
        ex = _val(r, "ex")
        if ex is None:
            return None
        back = [p for p in (_level_pair(x) for x in (_val(ex, "available_to_back") or [])[:3]) if p]
        lay = [p for p in (_level_pair(x) for x in (_val(ex, "available_to_lay") or [])[:3]) if p]
        return {"back": back, "lay": lay}
    return None


def _signal_for(sb: Any, event_id: Any, market_id: Any, selection_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """Segnale del motore attivo per (market, selection) da live_signals (best-effort)."""
    if not event_id:
        return None
    res = (
        sb.table("live_signals")
        .select("signals")
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    rows = getattr(res, "data", None) or []
    if not rows:
        return None
    payload = rows[0].get("signals") or {}
    # shape reale (engine/live_engine_pro.signals_to_json): {"signals": [MarketSignal...]}
    sig_list = payload.get("signals") if isinstance(payload, dict) else None
    if not isinstance(sig_list, list):
        return None
    for m in sig_list:
        if not isinstance(m, dict) or m.get("market_id") != market_id:
            continue
        if selection_id is None or _int(m.get("selection_id")) == _int(selection_id):
            return m
    return None


def _journal_done(sb: Any, flumine: Any, request_row: Dict[str, Any], mode_l: str) -> None:
    """Riga di trade journal per una richiesta ESEGUITA (E37).

    Contesto catturato ADESSO (minuto/score da live_now, book/LTP dal market_book in
    memoria, segnale attivo da live_signals). BEST-EFFORT DICHIARATO: il journal non
    deve MAI bloccare né far fallire un ordine — un errore produce un log WARN e (una
    volta al giorno) un alert WARN, mai un'eccezione verso il chiamante.
    """
    try:
        rid = request_row.get("id")
        market_id = request_row.get("market_id")
        selection_id = _int(request_row.get("selection_id"))
        handicap = _f(request_row.get("handicap")) or 0.0
        params = request_row.get("params") or {}
        origin = "risk_rule" if isinstance(params, dict) and params.get("risk_rule_id") else "manual"

        market = None
        try:
            market = flumine.markets.markets.get(market_id) if market_id else None
        except Exception:  # noqa: BLE001
            market = None
        event_id = _val(market, "event_id") if market is not None else None

        # esito scritto dalla dispatch (bet_id) — una select puntuale, best-effort
        bet_id = None
        try:
            res = sb.table(_TABLE).select("bet_id").eq("id", rid).limit(1).execute()
            rows = getattr(res, "data", None) or []
            if rows:
                bet_id = rows[0].get("bet_id")
        except Exception:  # noqa: BLE001
            pass

        minute = score_home = score_away = inplay = None
        if event_id:
            try:
                res = (
                    sb.table("live_now")
                    .select("minute,score_home,score_away,inplay")
                    .eq("event_id", event_id)
                    .limit(1)
                    .execute()
                )
                rows = getattr(res, "data", None) or []
                if rows:
                    minute = rows[0].get("minute")
                    score_home = rows[0].get("score_home")
                    score_away = rows[0].get("score_away")
                    inplay = rows[0].get("inplay")
            except Exception:  # noqa: BLE001
                pass

        signal = None
        try:
            signal = _signal_for(sb, event_id, market_id, selection_id)
        except Exception:  # noqa: BLE001
            signal = None

        best_back = best_lay = None
        book = None
        ltp = None
        if market is not None and selection_id is not None:
            best_back, best_lay = _best_prices(market, selection_id, handicap)
            book = _book_snapshot(market, selection_id, handicap)
            ltp = _ltp_of(market, selection_id, handicap)

        # BUG FIX cert 10/07: usare il ``sb`` DEL CICLO (per-thread nel runner, FAKE nei
        # test) — la vecchia dbm.insert_live_journal apriva il client REALE anche nei
        # test unit, che INQUINAVANO il journal di produzione con righe fake ("1.1").
        sb.table("betfair_live_journal").insert(
            {
                "mode": mode_l,
                "request_id": rid,
                "action": str(request_row.get("action") or ""),
                "origin": origin,
                "event_id": event_id,
                "market_id": market_id,
                "selection_id": selection_id,
                "side": request_row.get("side"),
                "price": _f(request_row.get("price")),
                "size": _f(request_row.get("size")),
                "persistence": request_row.get("persistence"),
                "bet_id": bet_id,
                "minute": minute,
                "score_home": score_home,
                "score_away": score_away,
                "inplay": inplay,
                "ltp": ltp,
                "best_back": best_back,
                "best_lay": best_lay,
                "book": book,
                "signals": signal,
                "params": params if isinstance(params, dict) and params else None,
            }
        ).execute()
    except Exception as ex:  # noqa: BLE001 - journal best-effort: MAI bloccare l'ordine
        logger.warning("[live-order] journal KO: %s", str(ex)[:200])
        day = datetime.now(timezone.utc).date().isoformat()
        if _JOURNAL_WARNED_DAY.get("ko") != day:
            _JOURNAL_WARNED_DAY["ko"] = day
            try:
                # BUG FIX cert 10/07: anche l'alert passa dal ``sb`` del ciclo (mai il
                # client reale nei test: scrivevano alert fake su live_alerts di produzione).
                sb.table("live_alerts").insert({
                    "level": "WARN", "code": "JOURNAL",
                    "message": f"trade journal KO (ordini NON impattati): {str(ex)[:200]}",
                }).execute()
            except Exception:  # noqa: BLE001
                pass


def _write_done(sb: Any, rid: int, result: Dict[str, Any]) -> None:
    sb.table(_TABLE).update(
        {
            "status": "done",
            "result": result,
            "error": result.get("error"),
            "bet_id": result.get("bet_id"),
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()
    _audit(sb, rid, result, "done")


def _write_error(sb: Any, rid: int, request_row: Dict[str, Any], mode: str, ex: Any) -> None:
    result = _result(
        ok=False,
        action=str(request_row.get("action") or "?"),
        mode=mode,
        request_row=request_row,
        cust_ref=_cust_ref(rid),
        error=str(ex),
    )
    sb.table(_TABLE).update(
        {
            "status": "error",
            "error": str(ex)[:300],
            "result": result,
            "processed_at": _now_iso(),
        }
    ).eq("id", rid).execute()
    _audit(sb, rid, result, "error")


def _write_processing(sb: Any, rid: int, result: Dict[str, Any]) -> None:
    """Aggiorna il result lasciando la riga in 'processing' (sequenza submin in corso)."""
    sb.table(_TABLE).update(
        {"result": result, "bet_id": result.get("bet_id")}
    ).eq("id", rid).execute()


# ---------------------------------------------------------------------------
# Cap di sicurezza per ordine
# ---------------------------------------------------------------------------
def _effective_cap(request_row: Dict[str, Any]) -> Optional[float]:
    """Cap EFFETTIVO per l'ordine: il più stretto tra il cap globale env (se attivo) e
    l'eventuale ``params.max_stake`` per-ordine. ``None`` = nessun cap (default utente)."""
    cap = _max_stake()  # None = nessun cap globale
    params = request_row.get("params") or {}
    if isinstance(params, dict) and params.get("max_stake") is not None:
        pm = _f(params.get("max_stake"))
        if pm is not None and pm > 0:
            cap = pm if cap is None else min(cap, pm)
    return cap


# ---------------------------------------------------------------------------
# Esiti flumine (fix CRITICAL-1): place/cancel/replace ritornano **False** quando un
# trading control rifiuta l'istruzione (ControlError interno: ordine marcato VIOLATION,
# MAI inviato a Betfair — vedi flumine/execution/transaction.py). Ignorare il valore di
# ritorno scriverebbe 'done ok=True' su un ordine INESISTENTE: uno stop-loss "eseguito"
# su mercato sospeso che in realtà non ha chiuso nulla. Qui ogni esito è verificato.
# ---------------------------------------------------------------------------
def _violation_msg(order: Any) -> str:
    msg = _val(order, "violation_msg")
    return str(msg) if msg else "rifiutato dai trading control flumine (violation)"


def _place_or_raise(market: Any, order: Any, what: str) -> None:
    # Il confine del contratto ``post_place:`` è "place_order è tornato senza
    # sollevare": SOLO il rifiuto esplicito dei trading control (ritorno False,
    # ordine mai inviato) è provabilmente pre-place. Un'eccezione sollevata
    # DENTRO place_order è AMBIGUA (l'ordine può essere già nel blotter/in
    # dispatch a seconda degli internals flumine): va marcata post_place: così
    # chi legge l'esito (omega) non libera mai una riserva potenzialmente viva.
    try:
        ok = market.place_order(order, customer_strategy_ref=CUSTOMER_STRATEGY_REF)
    except Exception as ex:  # noqa: BLE001 - ambiguo per contratto, mai pre-place
        raise RuntimeError(
            f"post_place:{type(ex).__name__}: {str(ex)[:200]}") from ex
    if ok is False:
        raise ValueError(f"{what}: place RIFIUTATO — {_violation_msg(order)}")


def _cancel_or_raise(market: Any, order: Any, size_reduction: Optional[float], what: str) -> None:
    if size_reduction is not None:
        ok = market.cancel_order(order, size_reduction)
    else:
        ok = market.cancel_order(order)
    if ok is False:
        raise ValueError(f"{what}: cancel RIFIUTATO — {_violation_msg(order)}")


def _replace_or_raise(market: Any, order: Any, new_price: float, what: str) -> None:
    ok = market.replace_order(order, new_price)
    if ok is False:
        raise ValueError(f"{what}: replace RIFIUTATO — {_violation_msg(order)}")


# ---------------------------------------------------------------------------
# Azioni place / cancel / replace
# ---------------------------------------------------------------------------
def _do_place(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    from .live_order_build import build_order

    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    market = _resolve_market(flumine, request_row.get("market_id"))
    built = build_order(
        market,
        strategy=strategy,
        selection_id=int(request_row["selection_id"]),
        handicap=float(request_row.get("handicap") or 0),
        side=str(request_row["side"]),
        order_type=str(request_row.get("order_type") or "LIMIT"),
        price=_f(request_row.get("price")),
        size=_f(request_row.get("size")),
        liability=_f(request_row.get("liability")),
        persistence=str(request_row.get("persistence") or "LAPSE"),
        time_in_force=request_row.get("time_in_force"),
        min_fill_size=_f(request_row.get("min_fill_size")),
        jurisdiction=_jurisdiction(),
        max_stake=_effective_cap(request_row),
        customer_order_ref=cust_ref,
    )
    # §7.2: NESSUN pre-check duplicato qui — rate-limit e max esposizione/selezione sono
    # dei control NATIVI (LiveRateControl/LiveExposureControl), che girano SINCRONI dentro
    # market.place_order (Transaction._validate_controls): un rifiuto fa tornare False e
    # _place_or_raise lo trasforma in errore esplicito sulla riga coda (violation_msg).
    _place_or_raise(market, built.order, "place")
    # Da qui in poi l'ordine è STATO DISPATCHATO (in live: ordine reale in volo):
    # un fallimento successivo (registro TTL, result, _write_done) NON può finire
    # sulla riga coda come un normale errore di validazione — chi legge l'esito
    # (es. omega, che su 'error' pre-place libera la riserva) deve poter
    # distinguere. Prefisso contrattuale ``post_place:`` sul messaggio d'errore.
    try:
        # C22 (roadmap): Fill-or-Kill SOFTWARE con timer — params.fok_ttl_sec > 0 registra
        # l'ordine nel registro TTL: se dopo N secondi non è (tutto) abbinato, il worker lo
        # CANCELLA al giro successivo. Caveat software-side (come stop/offset): se il runner
        # cade il TTL non esiste più — l'ordine resta a mercato con la sua persistence.
        _register_fok_ttl(request_row, market, built.order)
        result = _result(
            ok=True,
            action="place",
            mode=mode,
            request_row=request_row,
            cust_ref=cust_ref,
            order=built.order,
            price=built.price,
            size=built.size,
            side=built.side.lower() if isinstance(built.side, str) else built.side,
            detail=built.note,
        )
        _write_done(sb, rid, result)
    except Exception as ex:  # noqa: BLE001
        raise RuntimeError(
            f"post_place:{type(ex).__name__}: {str(ex)[:200]}") from ex


# ---------------------------------------------------------------------------
# C22 — Fill-or-Kill SOFTWARE con timer (registro TTL in-memory del worker)
# ---------------------------------------------------------------------------
# Voci: dict {deadline, market_id, cust_ref, bet_id, alerted}. Fix review CRITICAL:
# NIENTE riferimenti diretti a market/order — un restart dello stream (evento di
# ROUTINE: nuova partita agganciata) ricostruisce il framework e renderebbe i vecchi
# oggetti morti (cancel su ThreadPool chiuso = retry infinito silenzioso). L'ordine
# viene RI-RISOLTO a ogni sweep sul framework CORRENTE via cust_ref/bet_id; se dopo
# la scadenza non è più risolvibile → alert CRITICAL una volta e voce rimossa
# (verifica manuale: mai fingere una protezione che non possiamo più esercitare).
_FOK_TTLS: List[Dict[str, Any]] = []
_FOK_MAX_TTL_SEC = 3600.0  # guardia: TTL oltre 1h non ha senso per un FoK


def _register_fok_ttl(request_row: Dict[str, Any], market: Any, order: Any) -> None:  # noqa: ARG001
    params = request_row.get("params") or {}
    raw = params.get("fok_ttl_sec") if isinstance(params, dict) else None
    ttl = _f(raw)
    # 0 (o assente) = FoK disattivato — convenzione "0 = off" del resto del codebase.
    if ttl is None or ttl == 0:
        return
    if not (0 < ttl <= _FOK_MAX_TTL_SEC):
        # TTL malformato = errore di richiesta, MAI ignorato in silenzio: qui siamo DOPO
        # il place (fallire forte lascerebbe l'ordine senza esito) → clamp dichiarato.
        logger.warning("[worker] fok_ttl_sec %r fuori range: clampato a [1, %s]s",
                       ttl, int(_FOK_MAX_TTL_SEC))
        ttl = min(max(float(ttl), 1.0), _FOK_MAX_TTL_SEC)
    _FOK_TTLS.append({
        "deadline": time.monotonic() + float(ttl),
        "market_id": str(request_row.get("market_id") or ""),
        "cust_ref": _cust_ref(request_row["id"]),
        "bet_id": getattr(order, "bet_id", None),
        "alerted": False,
    })


def _fok_alert(entry: Dict[str, Any], why: str) -> None:
    """Escalation UNA volta per voce: l'utente credeva l'ordine protetto dal timer."""
    if entry.get("alerted"):
        return
    entry["alerted"] = True
    msg = (f"FoK timer: impossibile cancellare l'ordine {entry.get('bet_id') or entry.get('cust_ref')} "
           f"({why}) — VERIFICA MANUALMENTE su Betfair, il timer non è più attivo.")
    logger.error("[worker] %s", msg)
    try:
        from . import db
        db.insert_alert("CRITICAL", "FOK_TTL", msg)
    except Exception:  # noqa: BLE001 - l'alert è best-effort
        pass


def _sweep_fok_ttls(flumine: Any) -> None:
    """Cancella gli ordini FoK scaduti e NON (completamente) abbinati. Chiamata a ogni
    giro del worker (~1s): la precisione del timer è la cadenza del poll, come nei tool
    pro. L'ordine è ri-risolto sul framework CORRENTE (sopravvive ai restart)."""
    if not _FOK_TTLS:
        return
    now = time.monotonic()
    keep: List[Dict[str, Any]] = []
    for entry in _FOK_TTLS:
        order = None
        if entry.get("bet_id"):
            order = _find_order_by_bet_id(flumine, entry["market_id"], str(entry["bet_id"]))
        if order is None and entry.get("cust_ref"):
            order = _find_order_by_cust_ref(flumine, entry["market_id"], entry["cust_ref"])
        if order is None:
            if now < entry["deadline"]:
                keep.append(entry)  # non ancora nel blotter (appena piazzato): riprova
                continue
            # scaduto E non più risolvibile (restart senza recovery/blotter ripulito):
            # non possiamo più cancellarlo noi → escalation, mai retry muto all'infinito.
            _fok_alert(entry, "ordine non risolvibile nel blotter corrente")
            continue
        if getattr(order, "bet_id", None) and not entry.get("bet_id"):
            entry["bet_id"] = getattr(order, "bet_id")
        status = getattr(getattr(order, "status", None), "name", None) or str(getattr(order, "status", ""))
        rem = _f(getattr(order, "size_remaining", None)) or 0.0
        if status in ("EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION", "CANCELLED") or rem <= 0:
            continue  # abbinato/terminale: TTL consumato
        if now < entry["deadline"]:
            keep.append(entry)
            continue
        try:
            market = _resolve_market(flumine, entry["market_id"])
            market.cancel_order(order)
            logger.info("[worker] FoK timer scaduto: cancel bet=%s (rem=%.2f)",
                        getattr(order, "bet_id", None), rem)
            keep.append(entry)  # resta finché l'ordine non è TERMINALE (retry-safe)
        except Exception as e:  # noqa: BLE001 - ritenta al giro dopo, MAI muto
            logger.warning("[worker] FoK cancel KO bet=%s: %s (ritento)",
                           getattr(order, "bet_id", None), e)
            keep.append(entry)
    _FOK_TTLS[:] = keep


def _do_cancel(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str) -> None:
    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    bet_id = str(request_row.get("bet_id") or "")
    if not bet_id:
        raise ValueError("cancel richiede bet_id")
    order = _find_order_by_bet_id(flumine, request_row.get("market_id"), bet_id)
    if order is None:
        raise ValueError(f"ordine bet_id {bet_id} non trovato nel blotter")
    market = _resolve_market(flumine, _val(order, "market_id") or request_row.get("market_id"))
    size_reduction = _f(request_row.get("size_reduction"))
    _cancel_or_raise(market, order, size_reduction, "cancel")
    result = _result(
        ok=True, action="cancel", mode=mode, request_row=request_row,
        cust_ref=cust_ref, order=order, detail=f"cancel size_reduction={size_reduction}",
    )
    _write_done(sb, rid, result)


def _do_replace(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str) -> None:
    from .live_order_build import round_to_tick

    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    bet_id = str(request_row.get("bet_id") or "")
    new_price_raw = _f(request_row.get("new_price"))
    if not bet_id or new_price_raw is None:
        raise ValueError("replace richiede bet_id + new_price")
    order = _find_order_by_bet_id(flumine, request_row.get("market_id"), bet_id)
    if order is None:
        raise ValueError(f"ordine bet_id {bet_id} non trovato nel blotter")
    market = _resolve_market(flumine, _val(order, "market_id") or request_row.get("market_id"))
    new_price = round_to_tick(new_price_raw)
    # CODE-MED-1: per un LAY ri-valida il cap PRIMA del replace. La liability = size*(price-1)
    # CRESCE spostando l'ordine verso quote più alte, quindi un replace al rialzo potrebbe
    # sfondare il cap money-critical che il place iniziale rispettava. Usa il cap EFFETTIVO
    # della richiesta (env + params.max_stake) e solleva senza piazzare se superato.
    snap = _order_snapshot(order)
    side_l = snap.get("side")
    osize = snap.get("size")
    if isinstance(side_l, str) and side_l.lower() == "lay" and osize is not None:
        new_liab = round(float(osize) * (new_price - 1.0), 2)
        cap = _effective_cap(request_row)
        # cap None = nessun limite (scelta utente): si salta la guardia. Se attivo, un replace
        # LAY al rialzo che sfonderebbe il cap è rifiutato (la liability cresce con la quota).
        if cap is not None and new_liab > cap + 1e-9:
            raise ValueError(
                f"replace LAY: liability €{new_liab:.2f} a quota {new_price} "
                f"oltre cap €{cap:.2f}"
            )
    _replace_or_raise(market, order, new_price, "replace")
    result = _result(
        ok=True, action="replace", mode=mode, request_row=request_row,
        cust_ref=cust_ref, order=order, price=new_price, detail=f"replace → {new_price}",
    )
    _write_done(sb, rid, result)


# ---------------------------------------------------------------------------
# greenup — green-up / cash-out (hedge) da esposizioni MATCHED flumine fresche
# ---------------------------------------------------------------------------
def _read_matched_exposures(
    flumine: Any, market: Any, strategy: Any, selection_id: int, handicap: float
) -> "tuple[float, float]":
    """(profit_if_win, profit_if_lose) MATCHED dal blotter flumine — autoritativo.

    MONEY-CRITICAL: il green-up si calcola sulle esposizioni REALI al MOMENTO
    dell'esecuzione (non su quelle pollate dal frontend, potenzialmente stantie). Prese da
    ``blotter.get_exposures(strategy, lookup)`` (le stesse di betfair_live_positions), MAI
    ricalcolate a mano. Difensivo: qualunque struttura inattesa → (0,0) → no-op a monte.
    """
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


def _level_price(level: Any) -> Optional[float]:
    """Prezzo di UN livello del book, tollerante alla forma.

    MONEY-CRITICAL (fix cert PAPER 2026-07-02): con lo stream LIVE betfairlightweight
    espone ``ex.available_to_back/lay`` come lista di **dict** ``{'price':…,'size':…}``,
    NON di oggetti PriceSize (stessa tolleranza già presente in recorder._price_sizes).
    Il solo ``getattr`` ritornava sempre None sui dati reali → ogni green-up/cash-out
    era un no-op "prezzo non disponibile" (i test coprivano solo la forma a oggetti).
    """
    if level is None:
        return None
    if isinstance(level, dict):
        return _f(level.get("price"))
    return _f(_val(level, "price"))


def _best_prices(
    market: Any, selection_id: int, handicap: float
) -> "tuple[Optional[float], Optional[float]]":
    """(best_available_to_back, best_available_to_lay) per la selezione dal market_book flumine.

    Prezzi "taker" immediatamente abbinabili: per backare si prende il best available-to-back,
    per layare il best available-to-lay. Letti dal MarketBook GIA' in memoria (stesso stream,
    ZERO chiamate API). Difensivo su ogni livello: None se il book non è disponibile.
    Livelli in forma oggetto (PriceSize) O dict (stream live): entrambe supportate.
    """
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


# ---------------------------------------------------------------------------
# A4 — FOLLOW-THROUGH dei cash-out MANUALI (greenup / cashout_all / cashout_event)
# ---------------------------------------------------------------------------
# Come per le regole di rischio (risk_engine_worker._follow_through), ma per i
# comandi manuali: dopo un cash-out 'done' si VERIFICA che ogni hedge si sia
# abbinato; un hedge rimasto unmatched oltre la soglia viene CANCELLATO e
# ri-accodato come NUOVO greenup (che ricalcola dalle esposizioni reali →
# self-correcting anche su fill parziali), con retry BOUNDED e alert CRITICAL
# finale se la posizione resta scoperta. Stato persistito nella colonna
# ``result`` della riga coda (jsonb ``ft``) → sopravvive ai restart; gli ordini
# si ri-risolvono per bet_id/customer_order_ref come nel registro FoK.
_FT_ACTIONS = ("greenup", "cashout_all", "cashout_event")
_FT_WINDOW_MIN = 15.0          # oltre questa età la riga non viene più seguita
_FT_FILL_AFTER_SEC = 10.0      # attesa fill prima di intervenire
_FT_MAX_RETRIES = 2            # re-hedge massimi per gamba (poi alert CRITICAL)
_FT_POLL_SEC = 5.0             # throttle dello sweep


def _ft_age_seconds(processed_at: Any) -> Optional[float]:
    if not processed_at:
        return None
    try:
        ts = datetime.fromisoformat(str(processed_at).replace("Z", "+00:00"))
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except Exception:  # noqa: BLE001 - timestamp malformato
        return None


def _ft_legs_from_result(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Gambe hedge da verificare per una riga 'done' di cash-out/greenup."""
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    action = str(row.get("action") or "")
    if action == "greenup":
        if not result.get("bet_id") and not result.get("customer_order_ref"):
            return []
        if result.get("size") is None:
            return []  # no-op (posizione già piatta): nessun hedge da seguire
        return [{
            "market_id": row.get("market_id"),
            "selection_id": _int(row.get("selection_id")),
            "handicap": _f(row.get("handicap")) or 0.0,
            "ref": result.get("customer_order_ref"),
            "bet_id": result.get("bet_id"),
        }]
    legs = result.get("legs")
    if not isinstance(legs, list):
        return []
    out: List[Dict[str, Any]] = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        out.append({
            "market_id": leg.get("market_id"),
            "selection_id": _int(leg.get("selection_id")),
            "handicap": _f(leg.get("handicap")) or 0.0,
            "ref": leg.get("ref"),
            "bet_id": leg.get("bet_id"),
        })
    return out


def _ft_leg_key(leg: Dict[str, Any]) -> str:
    return f"{leg.get('market_id')}:{leg.get('selection_id')}"


def _ft_enqueue_rehedge(
    sb: Any, row: Dict[str, Any], leg: Dict[str, Any], retry_n: int, fraction: float
) -> Optional[int]:
    """Accoda il re-hedge (NUOVO greenup) per la gamba. client_ref DETERMINISTICO
    ``ft<rid>s<sel>r<n>`` → il vincolo UNIQUE della coda garantisce UN SOLO
    re-hedge anche se lo sweep rivaluta la riga più volte."""
    payload = {
        "client_ref": f"ft{row.get('id')}s{leg.get('selection_id')}r{retry_n}",
        "action": "greenup",
        "mode": str(row.get("mode") or ""),
        "market_id": leg.get("market_id"),
        "selection_id": leg.get("selection_id"),
        "handicap": leg.get("handicap") or 0,
        "params": {
            "fraction": fraction,
            "ft_parent": row.get("id"),
            "ft_retry": retry_n,
        },
    }
    try:
        res = sb.rpc("request_betfair_live_order", {"p": payload}).execute()
        data = getattr(res, "data", None)
        return int(data) if data is not None else None
    except Exception as ex:  # noqa: BLE001 - enqueue KO transitorio: riprova al prossimo giro
        logger.warning("[live-order] follow-through: enqueue re-hedge KO: %s", str(ex)[:160])
        return None


def _ft_alert(msg: str) -> bool:
    """True se l'alert è ARRIVATO al DB. fix review CRITICAL: il flag 'alerted'
    va persistito SOLO a consegna avvenuta — un blip di rete nel momento
    peggiore perderebbe per sempre l'unico segnale "CHIUDERE A MANO".
    Il log locale resta comunque (fallback minimo)."""
    logger.error("[live-order] follow-through CRITICAL: %s", msg)
    try:
        from . import db as dbm

        dbm.insert_alert("CRITICAL", "CASHOUT_FT", msg)
        return True
    except Exception as ex:  # noqa: BLE001 - riprova al prossimo ciclo
        logger.warning("[live-order] follow-through: alert KO (%s), riprovo", str(ex)[:120])
        return False


def _check_manual_followthrough(sb: Any, flumine: Any, mode_l: str) -> int:
    """Sweep del follow-through (A4): una passata sulle righe cash-out recenti.

    Regole money-critical:
      * righe originate dal RISK ENGINE (params.risk_rule_id) → ESCLUSE: hanno
        già il loro follow-through (mai due meccanismi sullo stesso hedge);
      * mai due hedge vivi per gamba: il re-hedge parte SOLO dopo il cancel
        riuscito dell'hedge stantio;
      * retry BOUNDED per gamba; esauriti → alert CRITICAL "chiudere a mano"
        UNA volta (flag persistito).
    """
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=_FT_WINDOW_MIN)).isoformat()
    try:
        rows = (
            sb.table(_TABLE)
            .select("id,action,mode,market_id,selection_id,handicap,params,result,processed_at")
            .eq("status", "done")
            .eq("mode", mode_l)
            .in_("action", list(_FT_ACTIONS))
            .gte("processed_at", cutoff)
            .order("id")
            .limit(30)
            .execute()
            .data
            or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura KO: riprova al prossimo giro
        logger.warning("[live-order] follow-through: lettura righe KO: %s", str(ex)[:160])
        return 0

    handled = 0
    for row in rows:
        params = row.get("params") if isinstance(row.get("params"), dict) else {}
        if params.get("risk_rule_id"):
            continue  # già seguito dal risk engine
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        ft = dict(result.get("ft") or {})
        if ft.get("done"):
            continue
        age = _ft_age_seconds(row.get("processed_at"))
        if age is None or age < _FT_FILL_AFTER_SEC:
            continue  # troppo presto per giudicare il fill

        legs = _ft_legs_from_result(row)
        if not legs:
            # nulla da seguire (no-op/piatta): chiudi il follow-through.
            _ft_mark(sb, row, result, {**ft, "done": True, "note": "nessun hedge da seguire"})
            handled += 1
            continue

        leg_state: Dict[str, Any] = dict(ft.get("legs") or {})
        changed = False
        all_ok = True
        # frazione originale del comando: il re-hedge deve riprodurre l'INTENTO
        # (un cash-out parziale resta parziale), mai chiudere più del richiesto.
        fraction = _f(params.get("fraction")) or 1.0
        retry_base = _int(params.get("ft_retry")) or 0

        for leg in legs:
            key = _ft_leg_key(leg)
            st = dict(leg_state.get(key) or {})
            if st.get("ok") or st.get("handed_off") or st.get("alerted"):
                if not (st.get("ok") or st.get("handed_off")):
                    all_ok = False
                continue
            order = None
            if leg.get("bet_id"):
                order = _find_order_by_bet_id(flumine, leg.get("market_id"), str(leg["bet_id"]))
            if order is None and leg.get("ref"):
                order = _find_order_by_cust_ref(flumine, leg.get("market_id"), str(leg["ref"]))

            status = None
            rem = None
            if order is not None:
                status = getattr(getattr(order, "status", None), "name", None) or str(
                    getattr(order, "status", "")
                )
                rem = _f(_val(order, "size_remaining")) or 0.0
            if order is not None and (status == "EXECUTION_COMPLETE" or (rem is not None and rem <= 0)):
                st["ok"] = True
                leg_state[key] = st
                changed = True
                continue
            # fix review HIGH: stato AMBIGUO (PENDING/None: ordine appena piazzato,
            # stream non ancora allineato) → NIENTE re-hedge alla cieca, si aspetta
            # il prossimo giro (mai rischiare due hedge vivi sulla stessa gamba).
            if order is not None and status not in ("EXECUTABLE", "EXPIRED", "LAPSED", "VIOLATION", "CANCELLED"):
                all_ok = False
                continue

            # hedge NON (interamente) abbinato oltre la soglia → intervieni.
            all_ok = False
            total_retry = retry_base + 1
            if total_retry > _FT_MAX_RETRIES:
                delivered = _ft_alert(
                    f"CASH-OUT NON COMPLETATO dopo {retry_base + 1} tentativi: hedge "
                    f"non abbinato su {leg.get('market_id')} sel {leg.get('selection_id')} "
                    f"(resta €{rem if rem is not None else '?'} unmatched) — CHIUDERE A MANO."
                )
                if delivered:
                    st["alerted"] = True
                    leg_state[key] = st
                    changed = True
                continue
            # 1) cancella l'hedge stantio (mai due hedge vivi per gamba).
            if order is not None and status == "EXECUTABLE" and (rem or 0) > 0:
                try:
                    market = _resolve_market(flumine, leg.get("market_id"))
                    _cancel_or_raise(market, order, None, "follow-through cancel hedge stantio")
                except Exception as ex:  # noqa: BLE001 - cancel KO: riprova al prossimo giro
                    logger.warning(
                        "[live-order] follow-through: cancel hedge stantio KO: %s", str(ex)[:160]
                    )
                    continue
            # 2) ri-accoda il greenup (ricalcola dalle esposizioni REALI correnti).
            new_req = _ft_enqueue_rehedge(sb, row, leg, total_retry, fraction)
            if new_req is None:
                continue  # enqueue KO: riprova senza consumare il tentativo
            st["handed_off"] = True
            st["retry_req"] = new_req
            leg_state[key] = st
            changed = True
            logger.info(
                "[live-order] follow-through: re-hedge accodato (req %s) per %s (retry %d)",
                new_req, key, total_retry,
            )

        new_ft = {**ft, "legs": leg_state}
        if all_ok and all(
            (leg_state.get(_ft_leg_key(leg)) or {}).get("ok")
            or (leg_state.get(_ft_leg_key(leg)) or {}).get("handed_off")
            for leg in legs
        ):
            new_ft["done"] = True
        if changed or new_ft.get("done") != ft.get("done"):
            _ft_mark(sb, row, result, new_ft)
        handled += 1
    return handled


def _ft_mark(sb: Any, row: Dict[str, Any], result: Dict[str, Any], ft: Dict[str, Any]) -> None:
    """Persiste lo stato follow-through nella colonna result della riga coda."""
    try:
        sb.table(_TABLE).update({"result": {**result, "ft": ft}}).eq("id", row.get("id")).execute()
    except Exception as ex:  # noqa: BLE001 - retry al prossimo giro (stato ricostruibile)
        logger.warning("[live-order] follow-through: persist stato KO: %s", str(ex)[:160])


def _cancel_unmatched(
    market: Any, strategy: Any, selection_id: Optional[int] = None
) -> "tuple[int, List[Dict[str, Any]]]":
    """A3 — cancella i NOSTRI ordini unmatched del mercato (o della sola selezione).

    Sequenza pro del cash-out COMPLETO (Bet Angel): prima si annullano i resting,
    POI si hedgia il matched — altrimenti un resting dimenticato può abbinarsi
    DOPO l'hedge e riaprire l'esposizione appena chiusa. Cancella solo ordini
    EXECUTABLE con size_remaining > 0 (gli unici cancellabili). Un fallimento
    non blocca gli altri cancel. Ritorna (n_cancellati, falliti)."""
    blotter = _val(market, "blotter")
    if blotter is None or strategy is None:
        return 0, []
    try:
        orders = list(blotter.strategy_orders(strategy))
    except Exception:  # noqa: BLE001 - blotter mock/edge: niente da cancellare
        return 0, []
    cancelled = 0
    failed: List[Dict[str, Any]] = []
    for order in orders:
        if selection_id is not None and _int(_val(order, "selection_id")) != int(selection_id):
            continue
        status = getattr(getattr(order, "status", None), "name", None) or str(
            getattr(order, "status", "")
        )
        rem = _f(_val(order, "size_remaining")) or 0.0
        if status != "EXECUTABLE" or rem <= 0:
            continue
        try:
            _cancel_or_raise(market, order, None, "cash-out cancel-unmatched")
            cancelled += 1
        except Exception as ex:  # noqa: BLE001 - continua con gli altri
            failed.append({
                "bet_id": _val(order, "bet_id"),
                "selection_id": _int(_val(order, "selection_id")),
                "error": f"cancel unmatched fallito: {str(ex)[:120]}",
            })
    return cancelled, failed


def _do_greenup(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Green-up / cash-out: chiude (totale o frazione) l'esposizione MATCHED di una selezione.

    Legge le esposizioni FRESCHE da flumine + il best price opposto dal book, calcola l'UNICO
    ordine di hedge (trading/greenup.compute_greenup) e lo piazza con ``reduces_liability=True``
    (sotto-minimo consentito, hedge self-bounded → ``max_stake=None``). Se la posizione è già
    piatta / frazione nulla / prezzo assente → riga 'done' SENZA piazzare (no-op tracciato).
    """
    from .live_order_build import build_order
    from .trading.greenup import compute_greenup

    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    # MONEY-CRITICAL: senza la strategy registrata NON possiamo leggere le esposizioni
    # (blotter.get_exposures(strategy, ...)) → (0,0) → "posizione piatta" FALSO con la
    # posizione invece APERTA. Fallire forte (riga 'error') invece di un 'done' bugiardo.
    if strategy is None:
        raise ValueError("greenup richiede la strategy registrata (LiveTradingStrategy)")
    market = _resolve_market(flumine, request_row.get("market_id"))
    selection_id = int(request_row["selection_id"])
    handicap = float(request_row.get("handicap") or 0)

    params = request_row.get("params") or {}
    fraction = _f(params.get("fraction")) if isinstance(params, dict) else None
    if fraction is None:
        fraction = 1.0
    # place_at_ticks (stop a 2 parametri): chiude N tick più a fondo nel book per fill sicuro.
    place_at = _int(params.get("place_at_ticks")) if isinstance(params, dict) else None
    # persistence dell'ordine di hedge (fix audit #25: le regole risk la passano dal form).
    # Valore malformato = errore di richiesta ESPLICITO, mai un default silenzioso diverso
    # da quello chiesto. Assente → LAPSE (comportamento storico invariato).
    persistence = "LAPSE"
    if isinstance(params, dict) and params.get("persistence") is not None:
        persistence = str(params.get("persistence"))
        if persistence not in ("LAPSE", "PERSIST", "MARKET_ON_CLOSE"):
            raise ValueError(
                f"greenup: params.persistence non valida ({params.get('persistence')!r}): "
                "attesa LAPSE|PERSIST|MARKET_ON_CLOSE"
            )
    # target_price ("greening column"): chiudi A QUEL prezzo assoluto invece che al best
    # opposto — l'ordine può restare sul book come take-profit resting. Un target malformato
    # è un ERRORE di richiesta: mai ripiegare in silenzio sul best (l'utente ha cliccato UN
    # livello preciso; chiudere altrove sarebbe un ordine inatteso).
    target_price = _f(params.get("target_price")) if isinstance(params, dict) else None
    if isinstance(params, dict) and params.get("target_price") is not None:
        if target_price is None or not (1.0 < target_price <= 1000.0):
            raise ValueError(
                f"greenup: params.target_price non valido ({params.get('target_price')!r}): "
                "atteso un prezzo in (1.0, 1000]"
            )
    # A3 (fix review HIGH): la coda accetta richieste da QUALUNQUE origine → la
    # incompatibilità cancel_unmatched+target_price va rifiutata ANCHE qui, non
    # solo nel client TS: annullare i resting e poi piazzare un take-profit
    # resting è una combinazione contraddittoria (mai eseguirla in silenzio).
    if isinstance(params, dict) and params.get("cancel_unmatched") and params.get("target_price") is not None:
        raise ValueError(
            "greenup: params.cancel_unmatched non è compatibile con params.target_price "
            "(cash-out completo vs take-profit resting)"
        )

    # A3 (opt-in dal frontend, params.cancel_unmatched): cash-out COMPLETO della
    # selezione — prima annulla i resting della selezione, POI hedgia il matched.
    # MAI per la greening column (target_price = take-profit resting intenzionale)
    # né per i flatten del risk engine (che non passano il flag): cancellerebbero
    # ordini resting NON legati a questo cash-out.
    cancel_note = ""
    cancel_failed: List[Dict[str, Any]] = []
    if isinstance(params, dict) and params.get("cancel_unmatched"):
        n_cancelled, cancel_failed = _cancel_unmatched(market, strategy, selection_id)
        cancel_note = f"; unmatched annullati: {n_cancelled}"
        if cancel_failed:
            # fix review CRITICAL: l'hedge del matched procede COMUNQUE (chiudere
            # l'esposizione vale più di fermarsi), ma l'esito NON può essere un
            # "done ok" bugiardo: il resting rimasto vivo può riabbinarsi e
            # riaprire la posizione appena chiusa. Si piazza l'hedge e POI si
            # alza INCOMPLETO (retry idempotente: greenup su piatta = no-op,
            # restano solo i cancel da ritentare).
            cancel_note += f" ({len(cancel_failed)} cancel FALLITI)"

    w, l = _read_matched_exposures(flumine, market, strategy, selection_id, handicap)
    best_back, best_lay = _best_prices(market, selection_id, handicap)
    plan = compute_greenup(
        matched_if_win=w, matched_if_lose=l,
        best_back_price=best_back, best_lay_price=best_lay, fraction=fraction,
        place_at_ticks=place_at or 0,
        target_price=target_price,
    )

    if not plan.actionable:
        # Fix cert PAPER 2026-07-02: distinguere i DUE no-op. Posizione GIÀ piatta =
        # vero successo. Esposizione APERTA ma piano non eseguibile (prezzo assente:
        # mercato sospeso/book vuoto) = FALLIMENTO da dichiarare: un 'done ok=True'
        # qui consumerebbe uno stop scattato ("eseguita e verificata") lasciando la
        # posizione a sanguinare. L'errore fa scattare il retry del follow-through.
        from .trading.greenup import FLAT_EPS
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
        # niente da chiudere: esito ok con motivo, nessun ordine (mai un place a vuoto).
        result = _result(
            ok=True, action="greenup", mode=mode, request_row=request_row,
            cust_ref=cust_ref, detail=f"{plan.note}{cancel_note}",
        )
        _write_done(sb, rid, result)
        return

    built = build_order(
        market,
        strategy=strategy,
        selection_id=selection_id,
        handicap=handicap,
        side=str(plan.side),
        order_type="LIMIT",
        price=plan.price,
        size=plan.size,
        liability=None,
        persistence=persistence,
        time_in_force=None,
        min_fill_size=None,
        jurisdiction=_jurisdiction(),
        max_stake=None,                 # hedge self-bounded (liability < |W−L|): nessun cap
        customer_order_ref=cust_ref,
        reduces_liability=True,         # green-up: sotto-minimo .it consentito
    )
    _place_or_raise(market, built.order, "greenup")
    if cancel_failed:
        # hedge PIAZZATO ma resting non annullati: esito INCOMPLETO esplicito
        # (mai un done bugiardo — stessa semantica di _flatten_market).
        raise ValueError(
            f"cash-out selezione INCOMPLETO: hedge {plan.side} {built.size}@{built.price} "
            f"piazzato ma {len(cancel_failed)} resting NON annullati "
            f"({cancel_failed[0].get('error')}) — ritentare il cash-out"
        )
    result = _result(
        ok=True, action="greenup", mode=mode, request_row=request_row,
        cust_ref=cust_ref, order=built.order, price=built.price, size=built.size,
        side=plan.side,
        detail=f"{plan.note}; atteso vince={plan.expected_if_win} "
               f"perde={plan.expected_if_lose}{cancel_note}",
    )
    _write_done(sb, rid, result)


# ---------------------------------------------------------------------------
# dutch — dutching/bookmaking: UNA richiesta → N ordini (profitto/liability uguale)
# ---------------------------------------------------------------------------
def _leg_ref(rid: int, suffix: str) -> str:
    """Ref interno per una GAMBA di un ordine multiplo (dutch/cashout): ``awlq<rid><suffix>``.

    Unico per gamba → una riga di specchio per gamba (chiave mode+client_order_ref). NB: non è
    parsabile come request_id intero (``_request_id_from_ref`` ritorna None), ma il legame
    richiesta↔ordine resta tracciato dal prefisso; il request_id è solo un link soft.
    """
    return (_cust_ref(rid) + suffix)[:32]


def _do_dutch(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Dutching: ripartisce uno stake totale su N selezioni (profitto uguale) e PIAZZA ogni gamba.

    La MATEMATICA è server-side (trading/dutching, autoritativa): il frontend manda solo
    ``params={selections:[{selection_id,price}], total_stake, side:'back'|'lay',
    mode:'equal'|'variable', persistence}``. Ogni gamba passa da ``build_order`` (stesse
    validazioni money-critical) e da ``market.place_order`` (stesso path/specchio del place).
    """
    from .live_order_build import build_order, ticks_away
    from .trading.dutching import dutch_back, dutch_back_for_target, dutch_lay, dutch_variable

    rid = request_row["id"]
    market = _resolve_market(flumine, request_row.get("market_id"))
    params = request_row.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("dutch: params mancanti")
    sels_in = params.get("selections") or []
    total = _f(params.get("total_stake"))
    side = str(params.get("side") or "back").lower()
    dmode = str(params.get("mode") or "equal").lower()
    pricing = str(params.get("pricing") or "as_given").lower()
    nominated = _f(params.get("nominated_price"))
    persistence = str(params.get("persistence") or "LAPSE")
    hcap = float(request_row.get("handicap") or 0)
    if not sels_in:
        raise ValueError("dutch: selections obbligatorio")
    if dmode != "target" and (total is None or total <= 0):
        raise ValueError("dutch: total_stake (>0) obbligatorio (salvo mode=target)")

    # #7 modalità PREZZO: as_given (quote passate) | best (miglior prezzo corrente dal book) |
    # in_front (1 tick davanti al book) | nominated (prezzo unico). Deriva il prezzo per gamba.
    def _price_for(sel_id: int, given: Optional[float]) -> Optional[float]:
        if pricing == "nominated" and nominated:
            return nominated
        if pricing in ("best", "in_front"):
            bb, bl = _best_prices(market, sel_id, hcap)
            base = bb if side == "back" else bl
            if base is None:
                return given  # fallback difensivo al prezzo fornito
            if pricing == "in_front":  # back → odds più alte, lay → più basse (davanti al book)
                return ticks_away(base, 1 if side == "back" else -1)
            return base
        return given

    # Fix HIGH (review DB): una gamba senza prezzo risolvibile NON può essere scartata in
    # silenzio — il dutch verrebbe piazzato su N−1 selezioni e, se quella esclusa vince, si
    # perde l'intero stake (l'opposto dell'equal-profit chiesto). O TUTTE le gambe hanno un
    # prezzo, o la richiesta fallisce senza piazzare nulla.
    def _price_or_raise(s: Dict[str, Any]) -> float:
        sel_id = int(s["selection_id"])
        price = _price_for(sel_id, _f(s.get("price")))
        if price is None:
            raise ValueError(
                f"dutch: prezzo non risolvibile per la selezione {sel_id} "
                f"(pricing={pricing}): nessuna gamba piazzata"
            )
        return price

    if dmode == "variable":
        triples = [
            (int(s["selection_id"]), _price_or_raise(s), _f(s.get("weight")) or 1.0)
            for s in sels_in
        ]
        plan = dutch_variable(triples, total)
    else:
        pairs = [(int(s["selection_id"]), _price_or_raise(s)) for s in sels_in]
        if dmode == "target":
            if side == "lay":
                raise ValueError("dutch mode=target: supportato solo per back")
            target = _f(params.get("target_profit"))
            if target is None or target <= 0:
                raise ValueError("dutch mode=target richiede params.target_profit > 0")
            plan = dutch_back_for_target(pairs, target)
        else:  # equal
            plan = dutch_lay(pairs, total) if side == "lay" else dutch_back(pairs, total)

    if not plan.actionable:
        _write_done(sb, rid, _result(
            ok=True, action="dutch", mode=mode, request_row=request_row,
            cust_ref=_cust_ref(rid), detail=plan.note,
        ))
        return

    live_legs = [leg for leg in plan.legs if leg.size > 0]
    # Fase 6 + §7.2 (pre-check di ATOMICITÀ, logica condivisa coi control nativi): le gambe
    # dutch APRONO esposizione → capacità rate per TUTTE le gambe e pre-check esposizione di
    # OGNI gamba PRIMA di piazzarne una sola (all-or-nothing: mai un dutching a metà perché
    # la gamba i>0 viene rifiutata dai control quando le precedenti sono GIÀ a mercato).
    _rate_guard(extra=len(live_legs))
    for leg in live_legs:
        leg_risk = leg.size if plan.side == "back" else round(leg.size * (leg.price - 1.0), 2)
        _check_exposure_guard(market, strategy, leg.selection_id, hcap, float(leg_risk))

    # Fix HIGH-2 (all-or-nothing sul BUILD): costruisci e valida TUTTE le gambe PRIMA di
    # piazzarne una sola. Un errore di build (min-stake .it €2 sulla gamba i>0, cap, tick)
    # a metà loop lascerebbe le gambe precedenti GIÀ a mercato → esposizione direzionale
    # non voluta. Con la pre-costruzione, qualunque gamba invalida = zero ordini.
    built_legs = []
    for i, leg in enumerate(live_legs):
        built_legs.append(build_order(
            market, strategy=strategy, selection_id=leg.selection_id,
            handicap=hcap, side=plan.side,
            order_type="LIMIT", price=leg.price, size=leg.size, liability=None,
            persistence=persistence, time_in_force=None, min_fill_size=None,
            jurisdiction=_jurisdiction(), max_stake=_effective_cap(request_row),
            customer_order_ref=_leg_ref(rid, f"d{i}"),
        ))

    placed = []
    placed_orders = []
    for i, (leg, built) in enumerate(zip(live_legs, built_legs)):
        try:
            _place_or_raise(market, built.order, f"dutch gamba {i + 1}/{len(built_legs)}")
        except Exception as ex:
            # Rifiuto a runtime (control/mercato) a metà piazzamento: le gambe precedenti
            # sono a mercato e il dutching è SBILANCIATO. Rollback best-effort: cancel di
            # ogni gamba già piazzata (unmatched), poi errore esplicito con l'esito.
            cancelled = 0
            for prev in placed_orders:
                try:
                    if market.cancel_order(prev) is not False:
                        cancelled += 1
                except Exception:  # noqa: BLE001 - rollback best-effort, mai mascherare l'errore vero
                    logger.exception("[live-order] rollback dutch: cancel gamba fallito")
            raise ValueError(
                f"{ex}; dutch interrotto: {len(placed_orders)} gambe piazzate, "
                f"{cancelled} cancellate in rollback — VERIFICARE il mercato"
            ) from ex
        placed_orders.append(built.order)
        placed.append({"selection_id": leg.selection_id, "side": plan.side,
                       "price": built.price, "size": built.size,
                       "profit_if_wins": leg.profit_if_wins})

    result = _result(
        ok=True, action="dutch", mode=mode, request_row=request_row,
        cust_ref=_cust_ref(rid),
        detail=f"{plan.note}; {len(placed)} gambe; book {plan.book_pct:.2f}% "
               f"worst {plan.worst_profit:.2f} best {plan.best_profit:.2f}",
    )
    result["legs"] = placed
    _write_done(sb, rid, result)


# ---------------------------------------------------------------------------
# cashout — flatten di TUTTE le selezioni di un MERCATO (cashout_all) o dell'INTERO
# EVENTO / tutti i mercati (cashout_event). Distinzione netta (#8).
# ---------------------------------------------------------------------------
def _flatten_market(
    flumine: Any, market: Any, strategy: Any, fraction: float, rid: int, idx0: int
) -> "tuple[list, int, list, int]":
    """Flatten (green-up) di ogni selezione del mercato con esposizione ≠ 0. Ritorna
    (gambe_chiuse, prossimo_indice, gambe_rifiutate, unmatched_annullati). Ogni gamba ha
    un customer_order_ref UNIVOCO ``awlq<rid>x<idx>`` (idx globale progressivo → nessuna
    collisione nello specchio anche su più mercati). Riusa la matematica di greenup
    (esposizioni FRESCHE + best opposto) con ``reduces_liability=True``.

    A3 (cash-out COMPLETO): PRIMA si annullano TUTTI i nostri ordini unmatched del
    mercato, POI si hedgia il matched — un resting dimenticato si abbinerebbe DOPO
    l'hedge riaprendo l'esposizione appena chiusa. Un cancel fallito finisce in
    ``failed`` (cash-out INCOMPLETO, il chiamante alza l'errore e si ritenta).

    Fix CRITICAL-1: l'esito di OGNI place è verificato. Un rifiuto NON interrompe il flatten
    (in emergenza chiudere le altre selezioni vale più di fermarsi): la gamba finisce in
    ``failed`` e il CHIAMANTE deve alzare l'errore (il greenup è idempotente: un retry chiude
    solo ciò che è rimasto aperto).
    """
    from .live_order_build import build_order
    from .trading.greenup import FLAT_EPS as GREENUP_FLAT_EPS, compute_greenup

    mb = _val(market, "market_book")
    runners = (_val(mb, "runners") or []) if mb is not None else []
    market_id = _val(market, "market_id")
    closed: list = []
    failed: list = []
    idx = idx0

    # A3: cancel-first di TUTTI gli unmatched del mercato (sequenza pro).
    cancelled, cancel_failed = _cancel_unmatched(market, strategy)
    for cf in cancel_failed:
        failed.append({"market_id": market_id, "selection_id": cf.get("selection_id"),
                       "error": cf.get("error")})
    for r in runners:
        sel = _int(_val(r, "selection_id"))
        if sel is None:
            continue
        hcap = _f(_val(r, "handicap")) or 0.0
        w, l = _read_matched_exposures(flumine, market, strategy, sel, hcap)
        best_back, best_lay = _best_prices(market, sel, hcap)
        plan = compute_greenup(matched_if_win=w, matched_if_lose=l,
                               best_back_price=best_back, best_lay_price=best_lay, fraction=fraction)
        if not plan.actionable:
            # Fix cert PAPER 2026-07-02: esposizione APERTA ma piano non eseguibile
            # (prezzo assente) = gamba FALLITA, mai saltata in silenzio — altrimenti il
            # cash-out riporta "done, 0 chiuse" con le posizioni ancora a mercato.
            if abs(w - l) >= GREENUP_FLAT_EPS:
                failed.append({"market_id": market_id, "selection_id": sel,
                               "error": f"non eseguibile (W={w:.2f} L={l:.2f}): {plan.note}"})
            continue
        try:
            built = build_order(
                market, strategy=strategy, selection_id=sel, handicap=hcap,
                side=str(plan.side), order_type="LIMIT", price=plan.price, size=plan.size,
                liability=None, persistence="LAPSE", time_in_force=None, min_fill_size=None,
                jurisdiction=_jurisdiction(), max_stake=None,
                customer_order_ref=_leg_ref(rid, f"x{idx}"), reduces_liability=True,
            )
            _place_or_raise(market, built.order, f"cashout sel {sel}")
        except Exception as ex:  # noqa: BLE001 - continua a chiudere le ALTRE selezioni
            logger.exception("[live-order] cashout: chiusura selezione %s rifiutata", sel)
            failed.append({"market_id": market_id, "selection_id": sel, "error": str(ex)[:160]})
            idx += 1
            continue
        closed.append({"market_id": market_id, "selection_id": sel, "handicap": hcap,
                       "side": plan.side, "price": built.price, "size": built.size,
                       "ref": _leg_ref(rid, f"x{idx}")})
        idx += 1
    return closed, idx, failed, cancelled


def _cashout_fraction(request_row: Dict[str, Any]) -> float:
    params = request_row.get("params") or {}
    f = _f(params.get("fraction")) if isinstance(params, dict) else None
    return f if f is not None else 1.0


def _do_cashout_all(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Cash-out di UN SOLO MERCATO (cashout_all): flatten di ogni selezione del mercato indicato.
    ``params.fraction`` ∈ (0,1] per un cash-out parziale."""
    if strategy is None:
        raise ValueError("cashout_all richiede la strategy registrata (LiveTradingStrategy)")
    rid = request_row["id"]
    market = _resolve_market(flumine, request_row.get("market_id"))
    fraction = _cashout_fraction(request_row)
    closed, _, failed, cancelled = _flatten_market(flumine, market, strategy, fraction, rid, 0)
    if failed:
        # MAI un 'done ok=True' con selezioni rimaste aperte: errore ESPLICITO (il greenup è
        # idempotente: un nuovo cash-out chiude solo ciò che è ancora sbilanciato).
        raise ValueError(
            f"cash-out MERCATO INCOMPLETO: {len(closed)} selezioni chiuse, {len(failed)} "
            f"RIFIUTATE ({'; '.join(f['error'] for f in failed[:3])}) — ritentare il cash-out"
        )
    result = _result(
        ok=True, action="cashout_all", mode=mode, request_row=request_row,
        cust_ref=_cust_ref(rid),
        detail=f"cash-out MERCATO {_val(market, 'market_id')}: {cancelled} unmatched "
               f"annullati, {len(closed)} selezioni chiuse (frazione {fraction:.2f})",
    )
    result["legs"] = closed
    result["cancelled"] = cancelled
    result["scope"] = "market"
    _write_done(sb, rid, result)


def _do_cashout_event(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Cash-out dell'INTERO EVENTO (cashout_event): flatten di TUTTI i mercati che condividono
    l'event_id — chiusura globale multi-mercato (benchmark Betting Toolkit). L'event_id è preso
    da ``params.event_id`` o, in fallback, dal ``market.event_id`` del market_id passato.

    OGNI mercato è chiuso PER CONTO SUO (flatten indipendente): nessun netting cross-market
    (che richiederebbe un modello di correlazione — vedi trading/hedging per l'hedge dedicato)."""
    if strategy is None:
        raise ValueError("cashout_event richiede la strategy registrata (LiveTradingStrategy)")
    rid = request_row["id"]
    params = request_row.get("params") or {}
    fraction = _cashout_fraction(request_row)
    ref_market = _resolve_market(flumine, request_row.get("market_id"))
    event_id = (params.get("event_id") if isinstance(params, dict) else None) or _val(ref_market, "event_id")
    if not event_id:
        raise ValueError("cashout_event: event_id non determinabile (né params.event_id né market.event_id)")

    closed: list = []
    failed_all: list = []
    idx = 0
    markets_done = 0
    cancelled_all = 0
    for m in flumine.markets:
        if _val(m, "event_id") != event_id:
            continue
        legs, idx, failed, cancelled = _flatten_market(flumine, m, strategy, fraction, rid, idx)
        closed.extend(legs)
        failed_all.extend(failed)
        cancelled_all += cancelled
        markets_done += 1

    if failed_all:
        raise ValueError(
            f"cash-out EVENTO INCOMPLETO: {len(closed)} selezioni chiuse, {len(failed_all)} "
            f"RIFIUTATE ({'; '.join(f['error'] for f in failed_all[:3])}) — ritentare il cash-out"
        )
    result = _result(
        ok=True, action="cashout_event", mode=mode, request_row=request_row,
        cust_ref=_cust_ref(rid),
        detail=f"cash-out EVENTO {event_id}: {cancelled_all} unmatched annullati, "
               f"{len(closed)} selezioni su {markets_done} mercati (frazione {fraction:.2f})",
    )
    result["legs"] = closed
    result["cancelled"] = cancelled_all
    result["scope"] = "event"
    result["event_id"] = event_id
    result["markets"] = markets_done
    _write_done(sb, rid, result)


# ---------------------------------------------------------------------------
# place_submin — macchina a stati (place-and-trim) ripartita su più poll
# ---------------------------------------------------------------------------
class _RecordingFlumineOps:
    """Avvolge FlumineSubminOps per catturare l'id flumine dell'ordine piazzato,
    così da ritrovarlo (blotter[order_id]) nei poll successivi."""

    def __init__(self, base: Any) -> None:
        self._base = base
        self.last_order: Any = None

    def place(self, market: Any, *, side: str, price: float, size: float, customer_order_ref: str) -> Any:
        order = self._base.place(
            market, side=side, price=price, size=size, customer_order_ref=customer_order_ref
        )
        self.last_order = order
        return order

    def cancel(self, market: Any, order: Any, size_reduction: float) -> None:
        self._base.cancel(market, order, size_reduction)

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        self._base.replace(market, order, new_price)


def _submin_state_to_dict(state: Any) -> Dict[str, Any]:
    return {
        "step": state.step.value,
        "bet_id": state.bet_id,
        "target_size": state.target_size,
        "target_price": state.target_price,
        "placed_size": state.placed_size,
        "side": state.side,
        "note": state.note,
        "trim_requested_ms": int(getattr(state, "trim_requested_ms", 0) or 0),
    }


def _submin_state_from_dict(d: Dict[str, Any]) -> Any:
    from .trading.submin import SubminState, SubminStep

    return SubminState(
        step=SubminStep(d["step"]),
        bet_id=d.get("bet_id"),
        target_size=float(d["target_size"]),
        target_price=float(d["target_price"]),
        placed_size=float(d["placed_size"]),
        side=str(d["side"]),
        note=str(d.get("note") or ""),
        # persistito dal fix 11/07 (verifica osservata del trim); default 0
        # per righe scritte prima del fix.
        trim_requested_ms=int(d.get("trim_requested_ms") or 0),
    )


def _submin_result(
    *, request_row: Dict[str, Any], mode: str, cust_ref: str, state: Any,
    order: Any, order_id: Optional[str], ok: bool, error: Optional[str] = None,
) -> Dict[str, Any]:
    res = _result(
        ok=ok, action="place_submin", mode=mode, request_row=request_row,
        cust_ref=cust_ref, order=order, side=state.side, price=state.target_price,
        size=state.target_size, submin_step=state.step.value, error=error,
        detail=state.note,
    )
    # bet_id dello stato submin ha priorità (l'ordine python può non averlo ancora)
    res["bet_id"] = state.bet_id or res.get("bet_id")
    res["submin_state"] = _submin_state_to_dict(state)
    res["submin_order_id"] = order_id
    return res


def _start_submin(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Step iniziale (INIT→PLACED) di una sequenza submin. La riga resta 'processing'
    finché terminale; lo SubminState è persistito in result.submin_state."""
    from .trading.submin import FlumineSubminOps, SubminStep, advance_submin, start_submin

    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    market = _resolve_market(flumine, request_row.get("market_id"))

    params = request_row.get("params") or {}
    ts = params.get("target_size") if isinstance(params, dict) else None
    target_size = _f(ts) if ts is not None else _f(request_row.get("size"))
    if target_size is None:
        raise ValueError("place_submin richiede size (target sotto-minimo) o params.target_size")

    juris = _jurisdiction()
    state = start_submin(
        side=str(request_row["side"]),
        target_price=float(request_row["price"]),
        target_size=target_size,
        jurisdiction=juris,
    )
    # Fase 6 + §7.2 (pre-check di ATOMICITÀ, logica condivisa coi control nativi): anche il
    # submin APRE esposizione reale → rate-limit + max esposizione/selezione PRIMA di
    # persistere lo step INIT, così una richiesta oltre i limiti non lascia una riga
    # 'processing' orfana (il control nativo rifiuterebbe DOPO la persistenza).
    _rate_guard()
    _sub_side = str(request_row["side"]).lower()
    _sub_risk = target_size if _sub_side == "back" else round(target_size * (float(request_row["price"]) - 1.0), 2)
    _check_exposure_guard(market, strategy, int(request_row["selection_id"]),
                          float(request_row.get("handicap") or 0), float(_sub_risk))

    # FIX (a) finestra di crash: persisti lo SubminState ATTESO (step=INIT) PRIMA del place
    # REALE. Il ref interno deterministico (awlq<id>) viaggia nell'esito (customer_order_ref).
    # Se il processo cade TRA il market.place_order e la persistenza dello step, alla ripresa
    # la riga è già 'processing' con submin_state=INIT: _advance_submin_row ritrova l'ordine
    # reale nel blotter PER REF (_find_order_by_cust_ref) e NON ripiazza mai (riconciliazione).
    _persist_submin_step(sb, rid, request_row, mode, cust_ref, state, None, None)

    ops = _RecordingFlumineOps(
        FlumineSubminOps(
            selection_id=int(request_row["selection_id"]),
            handicap=float(request_row.get("handicap") or 0),
            jurisdiction=juris,
            strategy=strategy,
            max_stake=_effective_cap(request_row),         # FIX (b): cap effettivo, non None
            customer_strategy_ref=CUSTOMER_STRATEGY_REF,    # FIX (b): strategy-ref nativo Betfair
        )
    )
    new_state = advance_submin(
        market, state, order=None, jurisdiction=juris, customer_order_ref=cust_ref, ops=ops,
    )
    order = ops.last_order
    # §7.2: il place del submin è conteggiato dal LiveRateControl nativo (finestra
    # condivisa) nel path sincrono di market.place_order — nessuna doppia registrazione.
    order_id = _val(order, "id")
    try:
        _persist_submin_step(sb, rid, request_row, mode, cust_ref, new_state, order, order_id)
    except Exception:
        # Fix MEDIUM-2: place riuscito ma persistenza DB fallita → la riga finirà 'error'
        # (mai più avanzata) con l'ordine step1 ORFANO a riposo a 1000/1.01. Cancel
        # best-effort PRIMA di propagare: niente resting non tracciati sul conto.
        if order is not None:
            try:
                market.cancel_order(order)
                logger.warning("[live-order] submin %s: persistenza KO, step1 cancellato", rid)
            except Exception:  # noqa: BLE001 - il cancel di emergenza è best-effort
                logger.exception("[live-order] submin %s: cancel di emergenza fallito", rid)
        raise


def _advance_submin_row(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    """Avanza di UNO step una sequenza submin già in corso (riga 'processing')."""
    from .trading.submin import FlumineSubminOps, SubminStep, advance_submin

    rid = request_row["id"]
    cust_ref = _cust_ref(rid)
    prev = request_row.get("result") or {}
    state_dict = prev.get("submin_state") if isinstance(prev, dict) else None
    if not state_dict:
        raise ValueError("place_submin in 'processing' senza submin_state persistito")
    state = _submin_state_from_dict(state_dict)
    order_id = prev.get("submin_order_id") if isinstance(prev, dict) else None

    # già terminale (es. crash dopo l'avanzamento ma prima della finalizzazione)
    if state.step in (SubminStep.DONE, SubminStep.ABORTED):
        _persist_submin_step(sb, rid, request_row, mode, cust_ref, state, None, order_id)
        return

    juris = _jurisdiction()
    market = _resolve_market(flumine, request_row.get("market_id"))
    # cust_ref incluso nella lookup: per un crash IN-PROCESS (tra place e persist, stessa
    # esecuzione) l'ordine reale porta ancora in memoria le annotazioni notes/context con il
    # ref interno → ritrovabile per ref, niente re-place. ATTENZIONE: dopo un RIAVVIO REALE del
    # processo l'ordine è ricostruito dall'order stream SENZA quelle annotazioni (vedi flumine
    # order/process.create_order_from_current), quindi il ref interno NON sopravvive: se non c'è
    # né order_id né bet_id persistito il ritrovamento fallisce di proposito → advance_submin
    # (allow_place=False) abortisce per riconciliazione manuale anziché ri-piazzare.
    order = _find_submin_order(
        flumine, request_row.get("market_id"), order_id, state.bet_id, cust_ref=cust_ref
    )
    ops = FlumineSubminOps(
        selection_id=int(request_row["selection_id"]),
        handicap=float(request_row.get("handicap") or 0),
        jurisdiction=juris,
        strategy=strategy,
        max_stake=_effective_cap(request_row),         # FIX (b): cap effettivo, non None
        customer_strategy_ref=CUSTOMER_STRATEGY_REF,    # FIX (b): strategy-ref nativo Betfair
    )
    # allow_place=False: questo è il percorso di SOLA-RIPRESA. Lo step1 (place) avviene
    # UNA volta sola in _start_submin; qui non si deve MAI piazzare. Se lo stato è INIT
    # (place persistito ma non confermato) e l'ordine non è riconciliabile con certezza,
    # advance_submin marca ABORTED ("riconciliare manualmente") invece di ri-piazzare.
    new_state = advance_submin(
        market, state, order=order, jurisdiction=juris, customer_order_ref=cust_ref,
        ops=ops, allow_place=False,
    )
    # mantieni l'order_id noto se l'ordine non è (ancora) ritrovabile
    new_order_id = _val(order, "id") or order_id
    _persist_submin_step(sb, rid, request_row, mode, cust_ref, new_state, order, new_order_id)


def _persist_submin_step(
    sb: Any, rid: int, request_row: Dict[str, Any], mode: str, cust_ref: str,
    state: Any, order: Any, order_id: Optional[str],
) -> None:
    from .trading.submin import SubminStep

    if state.step == SubminStep.DONE:
        result = _submin_result(
            request_row=request_row, mode=mode, cust_ref=cust_ref, state=state,
            order=order, order_id=order_id, ok=True,
        )
        _write_done(sb, rid, result)
    elif state.step == SubminStep.ABORTED:
        result = _submin_result(
            request_row=request_row, mode=mode, cust_ref=cust_ref, state=state,
            order=order, order_id=order_id, ok=False, error=state.note,
        )
        sb.table(_TABLE).update(
            {
                "status": "error",
                "error": str(state.note)[:300],
                "result": result,
                "bet_id": result.get("bet_id"),
                "processed_at": _now_iso(),
            }
        ).eq("id", rid).execute()
    else:
        result = _submin_result(
            request_row=request_row, mode=mode, cust_ref=cust_ref, state=state,
            order=order, order_id=order_id, ok=True,
        )
        _write_processing(sb, rid, result)


# ---------------------------------------------------------------------------
# A7 — CANALE LOCALE (desktop): drain dei comandi dal WebSocket localhost.
# STESSO path di validazione/esecuzione del path DB (_dispatch + guardie +
# controls + FoK + journal): cambia SOLO il trasporto. La risposta torna al
# client via WS; SUBITO DOPO il comando viene REGISTRATO come riga reale nella
# coda DB (status done/error) così audit, storico e follow-through A4 lavorano
# in modo identico sui comandi locali. MAI un ordine dal thread del WS: il
# drain avviene QUI, nel thread del worker (un solo thread tocca flumine).
# ---------------------------------------------------------------------------
import itertools as _itertools

_LOCAL_RID = _itertools.count(9_000_000_000)  # id sintetici: mai in collisione col bigserial
_LOCAL_ACTIONS = frozenset(
    {"place", "cancel", "replace", "greenup", "dutch", "cashout_all", "cashout_event"}
)  # place_submin ESCLUSO: la sua macchina a stati vive sulla coda DB

_LOCAL_ROW_KEYS = (
    "market_id", "selection_id", "handicap", "side", "order_type", "price", "size",
    "liability", "persistence", "time_in_force", "min_fill_size", "bet_id",
    "new_price", "size_reduction", "params",
)

# fix review HIGH: DEDUP server-side per client_ref (come l'UNIQUE della coda DB).
# Un reinvio dello stesso comando (bug UI/retry futuro) NON deve mai rieseguire:
# risponde l'esito già calcolato. Cache bounded con TTL.
_LOCAL_SEEN: "Dict[str, tuple]" = {}   # client_ref -> (monotonic_ts, ok, result)
_LOCAL_SEEN_TTL = 300.0
_LOCAL_SEEN_MAX = 500


def _local_dedup_get(client_ref: Optional[str]) -> Optional[tuple]:
    if not client_ref:
        return None
    import time as _t

    now = _t.monotonic()
    # purge scaduti/bounded
    if len(_LOCAL_SEEN) > _LOCAL_SEEN_MAX:
        for k in list(_LOCAL_SEEN)[: len(_LOCAL_SEEN) - _LOCAL_SEEN_MAX]:
            _LOCAL_SEEN.pop(k, None)
    hit = _LOCAL_SEEN.get(client_ref)
    if hit and now - hit[0] <= _LOCAL_SEEN_TTL:
        return hit
    _LOCAL_SEEN.pop(client_ref, None)
    return None


def _local_dedup_put(client_ref: Optional[str], ok: bool, result: Any) -> None:
    if client_ref:
        import time as _t

        _LOCAL_SEEN[client_ref] = (_t.monotonic(), ok, result)


class _LocalTable:
    """Proxy della tabella coda per i comandi LOCALI: cattura update/select
    sull'rid sintetico invece di scrivere/leggere il DB."""

    def __init__(self, owner: "_LocalSb") -> None:
        self._o = owner
        self._op: Optional[str] = None
        self._payload: Dict[str, Any] = {}

    def update(self, payload: Dict[str, Any]) -> "_LocalTable":
        self._op = "update"
        self._payload = dict(payload)
        return self

    def select(self, *_a: Any) -> "_LocalTable":
        self._op = "select"
        return self

    def eq(self, *_a: Any) -> "_LocalTable":
        return self

    def limit(self, *_a: Any) -> "_LocalTable":
        return self

    def execute(self) -> Any:
        from types import SimpleNamespace

        if self._op == "update":
            self._o.captured.update(self._payload)
            return SimpleNamespace(data=[])
        # select (journal: bet_id della riga) → servito dall'esito catturato
        res = self._o.captured.get("result") or {}
        return SimpleNamespace(
            data=[{"bet_id": self._o.captured.get("bet_id") or res.get("bet_id")}]
        )


class _LocalSb:
    """sb adapter per un comando locale: intercetta SOLO la tabella coda;
    audit/journal/live_now/segnali passano al client Supabase REALE."""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.captured: Dict[str, Any] = {}

    def table(self, name: str) -> Any:
        if name == _TABLE:
            return _LocalTable(self)
        return self._real.table(name)

    def rpc(self, *a: Any, **k: Any) -> Any:
        return self._real.rpc(*a, **k)


def _local_snapshot(flumine: Any, strategy: Any, market_id: str, mode_l: str) -> Dict[str, Any]:
    """Snapshot iniziale ordini+posizioni di UN mercato, dal blotter (zero DB)."""
    orders: List[Dict[str, Any]] = []
    positions: List[Dict[str, Any]] = []
    try:
        market = _resolve_market(flumine, market_id)
    except Exception:  # noqa: BLE001 - mercato non sottoscritto: snapshot vuoto
        return {"orders": orders, "positions": positions}
    blotter = _val(market, "blotter")
    if blotter is None or strategy is None:
        return {"orders": orders, "positions": positions}
    event_id = _val(market, "event_id")
    lookups = set()
    try:
        for o in blotter.strategy_orders(strategy):
            row = strategy._order_row(o, event_id=event_id, market_id=market_id)
            if row is not None and row.get("mode") == mode_l:
                orders.append(row)
            lk = _val(o, "lookup")
            if lk is not None:
                lookups.add(lk)
        for lk in lookups:
            pos = strategy._position_row(market, event_id, lk[0], lk[1], lk[2])
            if pos is not None:
                positions.append(pos)
    except Exception as ex:  # noqa: BLE001 - snapshot best-effort
        logger.debug("[local] snapshot KO %s: %s", market_id, str(ex)[:120])
    return {"orders": orders, "positions": positions}


def _record_local_request(
    sb: Any, row: Dict[str, Any], captured: Dict[str, Any], mode_l: str
) -> Optional[int]:
    """Registra il comando locale come riga REALE della coda (status done/error):
    audit-trail completo e follow-through A4 identici al path DB. Best-effort:
    un KO qui non tocca l'ordine (già eseguito e già risposto al client)."""
    try:
        payload = {k: row.get(k) for k in _LOCAL_ROW_KEYS}
        payload.update({
            "client_ref": f"local{row['id']}",
            "action": row.get("action"),
            "mode": mode_l,
            "status": captured.get("status") or "done",
            "result": captured.get("result"),
            "error": captured.get("error"),
            "processed_at": _now_iso(),
        })
        from .net_retry import with_backoff

        res = with_backoff(sb.table(_TABLE).insert(payload).execute, attempts=3, base_delay=0.2)
        data = getattr(res, "data", None) or []
        return int(data[0]["id"]) if data and data[0].get("id") is not None else None
    except Exception as ex:  # noqa: BLE001
        logger.warning("[local] registrazione comando KO: %s", str(ex)[:160])
        # fix review CRITICAL: un cash-out ESEGUITO ma non registrato perde il
        # follow-through A4 (verifica fill) — mai in silenzio: alert CRITICAL.
        if str(row.get("action") or "") in ("greenup", "cashout_all", "cashout_event"):
            try:
                from . import db as dbm

                dbm.insert_alert(
                    "CRITICAL", "LOCAL_RECORD",
                    f"{row.get('action')} LOCALE eseguito ma NON registrato in coda "
                    f"({str(ex)[:100]}): follow-through NON attivo — VERIFICARE il fill "
                    f"dell'hedge su {row.get('market_id')} manualmente.",
                )
            except Exception:  # noqa: BLE001
                pass
        return None


def _process_local_requests(sb: Any, flumine: Any, mode_l: str, strategy: Any) -> int:
    """Esegue i comandi arrivati dal canale locale (drain nel thread del worker)."""
    from . import local_channel

    ch = local_channel.get_channel()
    if ch is None:
        return 0
    reqs = ch.pop_requests()
    if not reqs:
        return 0
    handled = 0
    for req in reqs:
        handled += 1
        try:
            if req.method == "snapshot":
                mid = str(req.params.get("market_id") or "")
                ch.respond(req, True, _local_snapshot(flumine, strategy, mid, mode_l))
                continue
            cmd = req.params
            action = str(cmd.get("action") or "")
            if action not in _LOCAL_ACTIONS:
                ch.respond(req, False, error=f"azione non supportata dal canale locale: {action}")
                continue
            if str(cmd.get("mode") or "") != mode_l:
                ch.respond(req, False,
                           error=f"mode richiesta '{cmd.get('mode')}' diversa dal runner '{mode_l}'")
                continue
            # kill-switch RI-LETTO PER-COMANDO: stessa semantica del path DB
            # (aperture bloccate, chiusure sempre permesse).
            if (_kill_switch() or _db_kill_switch()) and action not in _CLOSING_ACTIONS:
                ch.respond(req, False, error="kill-switch ATTIVO: solo chiusure permesse")
                continue
            # fix review HIGH: dedup per client_ref — un reinvio identico risponde
            # l'esito già calcolato, MAI una seconda esecuzione reale.
            client_ref = str(cmd.get("client_ref") or "") or None
            dup = _local_dedup_get(client_ref)
            if dup is not None:
                ch.respond(req, dup[1], dup[2],
                           error=None if dup[1] else "comando già eseguito (dedup)")
                continue
            rid = next(_LOCAL_RID)
            row: Dict[str, Any] = {k: cmd.get(k) for k in _LOCAL_ROW_KEYS}
            row["id"] = rid
            row["action"] = action
            row["mode"] = mode_l
            lsb = _LocalSb(sb)
            try:
                _dispatch(lsb, flumine, row, mode_l, strategy)
            except Exception as ex:  # noqa: BLE001 - errore del comando, worker vivo
                try:
                    _write_error(lsb, rid, row, mode_l, ex)  # cattura esito + audit reale
                except Exception:  # noqa: BLE001
                    pass
                ch.respond(req, False, lsb.captured.get("result"), error=str(ex))
                _local_dedup_put(client_ref, False, lsb.captured.get("result"))
                _record_local_request(sb, row, lsb.captured, mode_l)
                continue
            # esito catturato da _write_done → risposta IMMEDIATA al client
            result = lsb.captured.get("result") or {"ok": True, "action": action, "mode": mode_l}
            ch.respond(req, True, result)
            _local_dedup_put(client_ref, True, result)
            db_id = _record_local_request(sb, row, lsb.captured, mode_l)
            # journal E37 col rid REALE della riga registrata (contesto al click)
            _journal_done(sb, flumine, {**row, "id": db_id or rid}, mode_l)
        except Exception as ex:  # noqa: BLE001 - mai far cadere il worker per un comando locale
            logger.exception("[local] comando locale KO")
            try:
                ch.respond(req, False, error=str(ex))
            except Exception:  # noqa: BLE001
                pass
    return handled


# ---------------------------------------------------------------------------
# Dispatch + ciclo
# ---------------------------------------------------------------------------
def _dispatch(sb: Any, flumine: Any, request_row: Dict[str, Any], mode: str, strategy: Any) -> None:
    action = str(request_row.get("action") or "")
    if action == "place":
        _do_place(sb, flumine, request_row, mode, strategy)
    elif action == "cancel":
        _do_cancel(sb, flumine, request_row, mode)
    elif action == "replace":
        _do_replace(sb, flumine, request_row, mode)
    elif action == "place_submin":
        _start_submin(sb, flumine, request_row, mode, strategy)
    elif action == "greenup":
        _do_greenup(sb, flumine, request_row, mode, strategy)
    elif action == "dutch":
        _do_dutch(sb, flumine, request_row, mode, strategy)
    elif action == "cashout_all":
        _do_cashout_all(sb, flumine, request_row, mode, strategy)
    elif action == "cashout_event":
        _do_cashout_event(sb, flumine, request_row, mode, strategy)
    else:
        raise ValueError(f"action sconosciuta: {action!r}")


def _advance_inflight_submins(sb: Any, flumine: Any, mode_l: str, strategy: Any) -> int:
    """Fa avanzare le sequenze submin in corso (UNICA eccezione al non-riprocessare
    'processing'). Best-effort per riga: un errore non blocca le altre né il runner."""
    try:
        rows = (
            sb.table(_TABLE)
            .select("*")
            .eq("status", "processing")
            .eq("action", "place_submin")
            .eq("mode", mode_l)
            .order("id")
            .limit(_batch())
            .execute()
            .data
            or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura coda momentaneamente KO
        logger.warning("[live-order] lettura submin in corso KO: %s", str(ex)[:160])
        return 0

    handled = 0
    for r in rows:
        # kill-switch RI-LETTO PER-RIGA: attivarlo a metà avanzamento FERMA SUBITO anche le
        # sequenze submin in corso (i prossimi cancel/replace non partono). Le righe restano
        # 'processing' col loro submin_state persistito → riprendono quando il freno è tolto.
        if _kill_switch():
            logger.warning(
                "[live-order] kill-switch ATTIVO: avanzamento submin in corso interrotto"
            )
            break
        rid = r.get("id")
        try:
            _advance_submin_row(sb, flumine, r, mode_l, strategy)
        except Exception as ex:  # noqa: BLE001 - scrivi error, non cadere
            logger.exception("[live-order] avanzamento submin %s fallito", rid)
            try:
                _write_error(sb, rid, r, mode_l, ex)
            except Exception:  # noqa: BLE001
                pass
        handled += 1
    return handled


def _fail_cross_mode(sb: Any, mode_l: str) -> int:
    """Marca 'error' le righe pending il cui ``mode`` NON è servibile da questo runner.

    Il runner gira in UNA sola mode (``LIVE_ORDER_MODE`` = PAPER|LIVE) e processa solo le
    righe di quella mode. Senza questo passo, una riga della mode opposta (es. enqueue 'live'
    mentre gira un runner 'paper': misconfigurazione o residuo) resterebbe 'pending' all'INFINITO,
    senza esito e senza diagnosi per il frontend.

    Assunzione di deployment: un SOLO runner attivo per coda (non un runner paper E uno live
    in parallelo sulla STESSA coda). Sotto questa assunzione marcare error è corretto e sicuro;
    il claim atomico pending→processing garantisce comunque che la transizione avvenga UNA volta.
    Best-effort: qualunque errore qui non blocca il ciclo né il runner.
    """
    try:
        rows = (
            sb.table(_TABLE)
            .select("*")
            .eq("status", "pending")
            .neq("mode", mode_l)
            .order("id")
            .limit(_batch())
            .execute()
            .data
            or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura coda KO: non cadere
        logger.warning("[live-order] lettura righe cross-mode KO: %s", str(ex)[:160])
        return 0

    handled = 0
    for r in rows:
        rid = r.get("id")
        # claim atomico: se un altro l'ha già preso (o non è più pending), salta.
        if not _claim(sb, rid):
            continue
        row_mode = str(r.get("mode") or "?")
        msg = (
            f"mode '{row_mode}' non servibile dal runner in modalità '{mode_l}' "
            f"(LIVE_ORDER_MODE={mode_l.upper()}): richiesta rifiutata, non lasciata appesa"
        )
        try:
            _write_error(sb, rid, r, mode_l, msg)
        except Exception:  # noqa: BLE001 - perfino la scrittura errore è best-effort
            logger.exception("[live-order] scrittura error cross-mode %s fallita", rid)
        handled += 1
    return handled


def _process_once(sb: Any, flumine: Any, session: Any = None, strategy: Any = None) -> int:
    """UN passo del worker. Ritorna quante righe ha gestito. Mai solleva (best-effort).

    ``strategy`` è l'istanza LiveTradingStrategy registrata nel framework: gli ordini
    piazzati sono creati sotto di essa (vedi build_order) così che lo specchio si popoli.
    """
    mode = _live_order_mode()
    if mode not in ("PAPER", "LIVE"):
        return 0  # OFF (o valore ignoto): worker inerte
    # Fase 6 + A7: snapshot settings a cadenza ~1s — col canale locale il worker
    # gira a intervallo BREVE per il drain (env LIVE_ORDER_QUEUE_POLL_SEC bassa):
    # mai martellare la RPC settings ad ogni giro (freschezza effettiva invariata).
    if not _throttled("settings_refresh", 1.0):
        _refresh_settings(sb)
    # A7: comandi dal canale LOCALE (desktop) — drenati SEMPRE, ad ogni giro.
    handled_local = _process_local_requests(sb, flumine, mode.lower(), strategy)
    # #15 velocità runtime: poll DB al target esplicito, oppure 1s di default quando
    # il canale locale è attivo (i comandi passano dal locale; la coda DB resta per
    # uso remoto/fallback e per il follow-through).
    from . import local_channel as _lc

    _db_target = _order_poll_target() or (1.0 if _lc.channel_active() else None)
    if _throttled("order_cycle", _db_target):
        return handled_local
    # C22: Fill-or-Kill software — cancella gli ordini col timer scaduto non abbinati.
    # PRIMA del gate kill-switch: il cancel è un'azione di CHIUSURA (sempre permessa).
    _sweep_fok_ttls(flumine)
    # Kill-switch (ENV *o* DB/UI): blocca le APERTURE ma NON le CHIUSURE. Col freno tirato
    # l'utente deve comunque poter cancellare resting e cash-outare le posizioni aperte —
    # bloccare anche le uscite sarebbe l'opposto della protezione (posizione che sanguina
    # senza via di fuga). Le azioni di chiusura sono risk-reducing per costruzione
    # (cancel = ritiro; greenup/cashout = hedge self-bounded reduces_liability).
    kill_cycle = _kill_switch() or _db_kill_switch()
    if kill_cycle:
        logger.warning(
            "[live-order] kill-switch ATTIVO (env o UI): processate SOLO azioni di chiusura"
        )

    mode_l = mode.lower()
    handled = handled_local

    # 1) sequenze submin in corso (place_submin) → avanza di uno step (APERTURE: mai col freno)
    if not kill_cycle:
        handled += _advance_inflight_submins(sb, flumine, mode_l, strategy)

    # 2) nuove richieste pending della stessa mode → claim atomico + dispatch
    try:
        rows = (
            sb.table(_TABLE)
            .select("*")
            .eq("status", "pending")
            .eq("mode", mode_l)
            .order("id")
            .limit(_batch())
            .execute()
            .data
            or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura coda KO: non cadere
        logger.warning("[live-order] lettura coda KO: %s", str(ex)[:160])
        return handled

    for r in rows:
        # kill-switch RI-LETTO PER-ORDINE (non solo a inizio ciclo): flipparlo a metà
        # batch blocca SUBITO le aperture rimanenti. Si controlla PRIMA del claim.
        # Le azioni di CHIUSURA passano sempre (vedi nota sul kill-switch a inizio funzione).
        # BUG FIX cert 10/07 (VISTO DAL VIVO): lasciare l'apertura 'pending' era una
        # TRAPPOLA — la riga sopravviveva al freno e veniva ESEGUITA al RIARMO (36s dopo
        # nel test), quando l'utente la credeva morta (timeout UI "NON reinviare").
        # Ora l'apertura è RIFIUTATA con esito esplicito (stessa semantica del canale
        # locale): errore in UI subito, e nessun ordine parte "da solo" a freno spento.
        if (kill_cycle or _kill_switch()) and str(r.get("action") or "") not in _CLOSING_ACTIONS:
            rid_k = r.get("id")
            if _claim(sb, rid_k):
                try:
                    _write_error(sb, rid_k, r, mode_l, ValueError(
                        "kill-switch ATTIVO: apertura RIFIUTATA — riprovare a freno spento"))
                except Exception:  # noqa: BLE001 - perfino la scrittura errore è best-effort
                    logger.exception("[live-order] esito kill per riga %s non scritto", rid_k)
            handled += 1
            continue
        rid = r.get("id")
        # claim: se un altro l'ha già preso (o non è più pending), salta.
        if not _claim(sb, rid):
            continue
        try:
            _dispatch(sb, flumine, r, mode_l, strategy)
        except Exception as ex:  # noqa: BLE001 - errore della riga, worker vivo
            logger.exception("[live-order] richiesta %s fallita", rid)
            try:
                _write_error(sb, rid, r, mode_l, ex)
            except Exception:  # noqa: BLE001 - perfino la scrittura errore è best-effort
                pass
        else:
            # E37 — trade journal AUTOMATICO: contesto al momento dell'esecuzione
            # (minuto/score, book, segnali attivi). SOLO dopo un dispatch riuscito;
            # MAI bloccante per l'ordine (best-effort dentro _journal_done).
            _journal_done(sb, flumine, r, mode_l)
        handled += 1

    # 3) A4 — follow-through dei cash-out MANUALI: verifica fill degli hedge,
    # re-hedge bounded, alert CRITICAL se resta scoperto. È un'azione di
    # CHIUSURA: gira anche col kill-switch tirato (come i cancel FoK).
    if not _throttled("manual_ft", _FT_POLL_SEC):
        handled += _check_manual_followthrough(sb, flumine, mode_l)

    # 4) righe pending della mode OPPOSTA → error (mai lasciate appese all'infinito)
    handled += _fail_cross_mode(sb, mode_l)
    return handled


def live_order_worker(
    context: dict, flumine: Any, session: Any = None, strategy: Any = None
) -> None:
    """BackgroundWorker flumine (firma: context, flumine, **func_kwargs).

    Aggiunto al framework SOLO se LIVE_ORDER_MODE ∈ {PAPER, LIVE} (vedi runner.setup_and_run).
    Esegue UN passo di coda per invocazione; il BackgroundWorker gestisce l'intervallo.
    Non solleva MAI: qualunque errore è loggato/scritto, il runner resta in piedi.

    ``strategy`` (da func_kwargs) è l'istanza LiveTradingStrategy registrata: gli ordini
    sono creati sotto di essa così che flumine instradi process_orders → specchio DB.
    """
    if flumine is None:
        return
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001 - DB non raggiungibile: salta il giro
        logger.warning("[live-order] supabase non disponibile: %s", str(ex)[:160])
        return
    try:
        _process_once(sb, flumine, session, strategy)
    except Exception as ex:  # noqa: BLE001 - ultima rete di sicurezza
        logger.warning("[live-order] ciclo KO: %s", str(ex)[:200])
