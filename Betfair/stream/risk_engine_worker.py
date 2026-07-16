"""risk_engine_worker.py — BackgroundWorker del RUNNER: ARMA/monitora le regole risk
(``betfair_live_risk_rules``) e, allo scattare, ACCODA le chiusure/coperture nella coda
esistente ``betfair_live_order_requests`` (STESSO path audited/mirror di ogni ordine).

Risk engine **v2** (punti #2/#3/#4/#6):
  * OFFSET completo — timing ``immediate`` (piazza subito il resting a target) o ``on_fill``
    (piazza SOLO quando l'ingresso ``entry_bet_id`` si è abbinato) + variante ``greening``
    (size che pareggia). ANTI-GAMBA-NUDA (#3): se l'ingresso lapsa/cancella senza match →
    NESSUN offset orfano, regola chiusa.
  * BRACKET (OCO, #2) — offset (take-profit) + stop insieme: chi scatta per primo chiude la
    posizione e cancella l'altro (one-cancels-other).
  * STOP a 2 parametri (#4) — trigger vs place_at: la chiusura passa ``place_at_ticks`` al
    green-up → chiude N tick più a fondo nel book per fill garantito.
  * Transizione PRE-MATCH→IN-PLAY (#6) — policy ``on_inplay`` ∈ {keep, cancel, rebaseline}:
    al calcio d'inizio la regola resta / si annulla / si ri-basa sul prezzo corrente (+alert).

MONEY-CRITICAL. Ogni ordine reale passa comunque dalla coda (validazioni + guardie + specchio).
Anti-doppio-trigger: client_ref DETERMINISTICO per ogni azione accodata (``risk<id>``,
``risk<id>o`` offset, ``risk<id>oc`` cancel-offset, ``risk<id>s`` stop) → il vincolo UNIQUE
della coda garantisce UN SOLO ordine anche se la regola viene rivalutata.

⚠️ SOFTWARE-SIDE: se il runner cade, stop/offset NON esistono (come in Bet Angel/Cymatic).
BEST-EFFORT: un errore TRANSITORIO NON disarma una regola protettiva (resta armata, retry).
Testabile a unità: framework/Market/blotter/coda mockabili, nessuna rete.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from . import live_order_worker as low
from .trading import risk_engine

logger = logging.getLogger(__name__)

_TABLE = "betfair_live_risk_rules"

# Stati terminali flumine di un ordine (per rilevare ingresso lapsato = gamba nuda evitata).
_TERMINAL = frozenset({"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION", "CANCELLED"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _batch() -> int:
    try:
        from . import config_stream
        return max(1, int(getattr(config_stream, "RISK_ENGINE_BATCH", 20)))
    except Exception:  # noqa: BLE001
        return 20


# ---------------------------------------------------------------------------
# Lettura stato di mercato / ordini
# ---------------------------------------------------------------------------
def _ltp(market: Any, selection_id: int, handicap: float) -> Optional[float]:
    """Last Traded Price della selezione dal market_book flumine (riferimento trigger prezzo)."""
    mb = low._val(market, "market_book")
    if mb is None:
        return None
    for r in (low._val(mb, "runners") or []):
        if low._int(low._val(r, "selection_id")) != int(selection_id):
            continue
        rh = low._f(low._val(r, "handicap")) or 0.0
        if abs(rh - float(handicap or 0.0)) > 1e-6:
            continue
        return low._f(low._val(r, "last_price_traded"))
    return None


def _market_inplay(market: Any) -> Optional[bool]:
    """True/False se il mercato è in-play, None se non determinabile (dal market_book flumine)."""
    mb = low._val(market, "market_book")
    if mb is None:
        return None
    v = low._val(mb, "inplay")
    return bool(v) if v is not None else None


def _entry_status(flumine: Any, market_id: Optional[str], entry_bet_id: Optional[str]) -> Tuple[float, Optional[str]]:
    """(size_matched, status_name) dell'ordine d'INGRESSO osservato. (0, None) se non trovato."""
    if not entry_bet_id:
        return 0.0, None
    o = low._find_order_by_bet_id(flumine, market_id, str(entry_bet_id))
    if o is None:
        return 0.0, None
    matched = low._f(low._val(o, "size_matched")) or 0.0
    st = low._val(o, "status")
    name = getattr(st, "name", None) or (str(st) if st is not None else None)
    return matched, name


def _offset_order_obj(flumine: Any, market_id: Optional[str], offset_request_id: Optional[int]) -> Any:
    """Ritrova l'ordine OFFSET piazzato (per OCO) tramite il suo ref interno awlq<req_id>."""
    if offset_request_id is None:
        return None
    return low._find_order_by_cust_ref(flumine, market_id, low._cust_ref(int(offset_request_id)))


# ---------------------------------------------------------------------------
# Scritture regola + accodamento
# ---------------------------------------------------------------------------
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


def _alert(level: str, msg: str) -> None:
    try:
        from . import db
        db.insert_alert(level, "RISK_ENGINE", msg)
    except Exception:  # noqa: BLE001 - alert best-effort
        pass


def _kill_active() -> bool:
    return low._kill_switch() or low._db_kill_switch()


def _params(rule: Dict[str, Any]) -> Dict[str, Any]:
    p = rule.get("params")
    return p if isinstance(p, dict) else {}


def _result(rule: Dict[str, Any]) -> Dict[str, Any]:
    r = rule.get("result")
    return dict(r) if isinstance(r, dict) else {}


# ---------------------------------------------------------------------------
# Transizione pre-match → in-play (#6)
# ---------------------------------------------------------------------------
def _apply_inplay_policy(sb: Any, rule: Dict[str, Any], market: Any, res: Dict[str, Any]) -> Optional[str]:
    """Applica la policy ``on_inplay`` alla transizione pre→in. Ritorna:
      'disarmed'  → regola annullata (interrompi il ciclo su questa regola);
      'rebaselined' → entry_price ri-basato sul prezzo corrente (continua, ``rule`` aggiornato);
      None        → nessuna azione (aggiorna solo il flag inplay memorizzato).
    """
    inplay = _market_inplay(market)
    if inplay is None:
        return None
    # FIX review MEDIUM: NON trattare il PRIMO avvistamento come transizione. Se la regola è armata
    # mentre il mercato è GIÀ in-play, ``result.inplay`` non è ancora seminato (default False) → una
    # FALSA transizione pre→in annullerebbe/ri-baserebbe uno stop protettivo. Alla prima osservazione
    # SEMINA lo stato reale (persistendolo) e NON applica la policy. Solo un genuino False→True scatta.
    if "inplay" not in res:
        res["inplay"] = bool(inplay)
        _update_rule(sb, rule["id"], {"result": res})
        return None
    prev = bool(res.get("inplay"))
    transition = bool(inplay) and not prev
    if not transition:
        if bool(inplay) != prev:
            res["inplay"] = bool(inplay)
            _update_rule(sb, rule["id"], {"result": res})  # persisti il cambiamento (raro: KO/half-time)
        return None

    policy = str(_params(rule).get("on_inplay") or "keep").lower()
    res["inplay"] = True
    if policy == "cancel":
        res["note"] = "annullata al calcio d'inizio (on_inplay=cancel)"
        _update_rule(sb, rule["id"], {"status": "cancelled", "result": res})
        _alert("WARN", f"Regola risk {rule.get('id')} annullata all'inizio in-play")
        return "disarmed"
    if policy == "rebaseline":
        ltp = _ltp(market, int(rule["selection_id"]), float(rule.get("handicap") or 0))
        newp = ltp if (ltp and ltp > 1.0) else low._f(rule.get("entry_price"))
        rule["entry_price"] = newp
        res["note"] = f"ri-basata in-play a {newp}"
        _update_rule(sb, rule["id"], {"entry_price": newp, "trail_extreme": None, "result": res})
        _alert("INFO", f"Regola risk {rule.get('id')} ri-basata in-play a {newp}")
        return "rebaselined"
    return None  # keep


# ---------------------------------------------------------------------------
# OFFSET (plain) — immediate / on_fill / greening / anti-gamba-nuda
# ---------------------------------------------------------------------------
def _build_offset_order(rule: Dict[str, Any], size: float, w: Optional[float], l: Optional[float]) -> Any:
    p = _params(rule)
    return risk_engine.offset_order(
        str(rule.get("entry_side")), low._f(rule.get("entry_price")), size,
        offset_ticks=risk_engine._int_param(p, "offset_ticks"),
        offset_pct=risk_engine._num(p, "offset_pct"),
        greening=bool(p.get("greening")),
        matched_if_win=w, matched_if_lose=l,
    )


def _enqueue_offset(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str,
                    size: float, w: Optional[float], l: Optional[float]) -> Tuple[Optional[int], Any]:
    """Costruisce e ACCODA l'ordine offset (resting take-profit). Ritorna (request_id, RiskOrder)."""
    order = _build_offset_order(rule, size, w, l)
    if not order.actionable:
        return None, order
    p = _params(rule)
    payload = {
        "client_ref": f"risk{rule['id']}o",
        "action": "place",
        "mode": mode_l,
        "market_id": rule["market_id"],
        "selection_id": rule["selection_id"],
        "handicap": rule.get("handicap") or 0,
        "side": order.side,
        "price": order.price,
        "size": order.size,
        # un take-profit resting deve sopravvivere al KO per potersi abbinare: default PERSIST.
        "persistence": (p.get("persistence") or "PERSIST"),
        "params": {"risk_rule_id": rule["id"], "role": "offset"},
    }
    return _enqueue(sb, payload), order


def _entry_ready_or_naked(flumine: Any, rule: Dict[str, Any]) -> str:
    """Per le regole ON-FILL (entry_bet_id): 'ready' (ingresso abbinato), 'naked' (ingresso
    terminato senza match → niente offset), 'wait' (ancora in attesa di abbinamento)."""
    matched, status = _entry_status(flumine, rule.get("market_id"), rule.get("entry_bet_id"))
    if matched > 0:
        return "ready"
    if status in _TERMINAL:
        return "naked"
    return "wait"


def _handle_offset(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    """Offset semplice (take-profit resting). timing immediate | on_fill; greening opzionale."""
    p = _params(rule)
    timing = str(p.get("timing") or ("on_fill" if rule.get("entry_bet_id") else "immediate")).lower()
    market = low._resolve_market(flumine, rule.get("market_id"))
    # FIX audit #16: anche l'offset rispetta la policy on_inplay (cancel/rebaseline) alla
    # transizione pre→in — prima veniva IGNORATA in silenzio (solo _handle_monitored la
    # applicava): un offset on_fill armato pre-match sopravviveva al KO contro la policy.
    if _apply_inplay_policy(sb, rule, market, _result(rule)) == "disarmed":
        return
    sel = int(rule["selection_id"]); hcap = float(rule.get("handicap") or 0)

    if timing == "on_fill" or rule.get("entry_bet_id"):
        state = _entry_ready_or_naked(flumine, rule)
        if state == "wait":
            return  # resta armata, attende il fill dell'ingresso
        if state == "naked":
            _update_rule(sb, rule["id"], {"status": "done",
                "result": {"note": "ingresso non abbinato (lapse/cancel): nessun offset (anti-gamba-nuda)"}})
            return
        matched, _ = _entry_status(flumine, rule.get("market_id"), rule.get("entry_bet_id"))
        size = matched
    else:
        size = low._f(rule.get("entry_size"))
    if size is None or size <= 0:
        _update_rule(sb, rule["id"], {"status": "error", "error": "offset: size ingresso non determinabile"})
        return

    if _kill_active():
        return  # freno d'emergenza: non piazzare, resta armata
    w, l = low._read_matched_exposures(flumine, market, strategy, sel, hcap) if p.get("greening") else (None, None)
    req_id, order = _enqueue_offset(sb, flumine, rule, mode_l, size, w, l)
    if req_id is None:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"offset non calcolabile: {order.note}"})
        return
    _update_rule(sb, rule["id"], {"status": "done", "enqueued_client_ref": f"risk{rule['id']}o",
        "enqueued_request_id": req_id, "triggered_at": _now_iso(),
        "result": {"note": order.note, "side": order.side, "price": order.price, "size": order.size}})


# ---------------------------------------------------------------------------
# MONITORED — stop_loss / take_profit / trailing_stop (+ place_at + in-play)
# ---------------------------------------------------------------------------
def _handle_monitored(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    market = low._resolve_market(flumine, rule.get("market_id"))
    sel = int(rule["selection_id"]); hcap = float(rule.get("handicap") or 0)
    res = _result(rule)
    if _apply_inplay_policy(sb, rule, market, res) == "disarmed":
        return

    # FIX audit #3: timing 'on_fill' — NON sorvegliare finché l'INGRESSO (entry_bet_id)
    # non è abbinato. Prima veniva ignorato: uno stop/take-profit/trailing "al fill"
    # monitorava SUBITO e poteva scattare (flatten) su una posizione ancora inesistente.
    # Stessa macchina anti-gamba-nuda di _handle_offset: wait → resta armata;
    # naked (ingresso lapsato/cancellato senza match) → regola chiusa, niente da proteggere.
    p = _params(rule)
    if str(p.get("timing") or "").lower() == "on_fill" and rule.get("entry_bet_id"):
        state = _entry_ready_or_naked(flumine, rule)
        if state == "wait":
            return  # attende il fill dell'ingresso: si valuta solo a posizione reale
        if state == "naked":
            _update_rule(sb, rule["id"], {"status": "done",
                "result": {**res, "note": "ingresso non abbinato (lapse/cancel): "
                                          "nessuna posizione da proteggere (anti-gamba-nuda)"}})
            return

    ltp = _ltp(market, sel, hcap)
    best_back, best_lay = low._best_prices(market, sel, hcap)
    w, l = low._read_matched_exposures(flumine, market, strategy, sel, hcap)
    decision = risk_engine.evaluate_rule(
        rule_type=str(rule.get("rule_type")), entry_side=str(rule.get("entry_side")),
        entry_price=low._f(rule.get("entry_price")), params=_params(rule), current_price=ltp,
        matched_if_win=w, matched_if_lose=l, best_back_price=best_back, best_lay_price=best_lay,
        trail_extreme=low._f(rule.get("trail_extreme")),
    )
    # Parametri INVALIDI (errore PERMANENTE dei dati della regola, non del mercato): la regola
    # non potrà MAI scattare così com'è. Disarmo VISIBILE (status 'error' + alert CRITICAL),
    # mai il retry silenzioso "transitorio": l'utente si crederebbe protetto da uno stop MORTO.
    if decision.error:
        _update_rule(sb, rule["id"], {"status": "error",
                                      "error": f"parametri non validi: {decision.error}"})
        _alert("CRITICAL",
               f"Regola risk {rule.get('id')} ({rule.get('rule_type')}) DISATTIVATA: parametri "
               f"non validi ({decision.error}). LA PROTEZIONE NON È ATTIVA: ri-armare la regola.")
        return
    if not decision.fire:
        patch: Dict[str, Any] = {}
        if decision.trail_extreme is not None:
            prev = low._f(rule.get("trail_extreme"))
            if prev is None or abs(prev - decision.trail_extreme) > 1e-9:
                patch["trail_extreme"] = decision.trail_extreme
        if res.get("inplay") != _market_inplay(market) and _market_inplay(market) is not None:
            res["inplay"] = bool(_market_inplay(market)); patch["result"] = res
        if patch:
            _update_rule(sb, rule["id"], patch)
        return

    if _kill_active():
        logger.warning("[risk] kill-switch ATTIVO: regola %s non innescata", rule.get("id"))
        return
    if abs(w - l) < risk_engine.FLAT_EPS:
        _update_rule(sb, rule["id"], {"status": "done", "triggered_at": _now_iso(),
            "result": {"note": f"{decision.reason}; posizione già piatta, nessun ordine"}})
        return
    req_id = _enqueue_flatten(sb, rule, mode_l)
    _update_rule(sb, rule["id"], {"status": "triggered", "enqueued_client_ref": f"risk{rule['id']}s",
        "enqueued_request_id": req_id, "triggered_at": _now_iso(),
        "trail_extreme": decision.trail_extreme if decision.trail_extreme is not None else rule.get("trail_extreme"),
        "result": {"note": decision.reason, "action": "greenup"}})


def _enqueue_flatten(
    sb: Any, rule: Dict[str, Any], mode_l: str, client_ref: Optional[str] = None
) -> Optional[int]:
    """Accoda un greenup (flatten) con place_at_ticks per un fill sicuro (stop a 2 parametri).

    ``client_ref`` esplicito = ritentativo del follow-through (fix HIGH-3): il ref di default
    ``risk<id>s`` è già bruciato dalla richiesta fallita (UNIQUE + RPC idempotente
    ritornerebbero la VECCHIA riga in error) → ogni retry usa un ref nuovo ``risk<id>s<n>``.
    """
    p = _params(rule)
    flatten_params: Dict[str, Any] = {
        "fraction": 1.0, "risk_rule_id": rule["id"],
        "place_at_ticks": risk_engine._int_param(p, "place_at_ticks") or 0,
    }
    # FIX audit #25: la persistenza scelta armando la regola vale ANCHE per la chiusura
    # (prima veniva ignorata in silenzio: la UI la mostrava, il flatten usava sempre
    # LAPSE). Il worker greenup la valida e la applica all'ordine di hedge.
    if p.get("persistence"):
        flatten_params["persistence"] = p.get("persistence")
    payload = {
        "client_ref": client_ref or f"risk{rule['id']}s",
        "action": "greenup",
        "mode": mode_l,
        "market_id": rule["market_id"],
        "selection_id": rule["selection_id"],
        "handicap": rule.get("handicap") or 0,
        "params": flatten_params,
    }
    return _enqueue(sb, payload)


# ---------------------------------------------------------------------------
# FOLLOW-THROUGH delle regole scattate (fix HIGH-3): 'triggered' NON è una garanzia.
# La chiusura accodata può finire in 'error' (mercato sospeso al momento del place, blip)
# o l'hedge LIMIT può restare unmatched se il prezzo scappa. Senza verifica, la protezione
# andrebbe persa IN SILENZIO: qui si controlla l'esito, si ritenta (greenup idempotente:
# ricalcola dalle esposizioni fresche → se già piatta è un no-op) e si escala con alert.
# ---------------------------------------------------------------------------
_MAX_CLOSE_RETRIES = 2       # ritentativi del flatten dopo una richiesta in 'error'
_FILL_ALERT_AFTER_SEC = 10.0  # hedge resting non abbinato dopo N secondi → alert CRITICAL


def _age_seconds(iso_ts: Any) -> Optional[float]:
    """Secondi trascorsi da un timestamp ISO (None se non parsabile)."""
    if not iso_ts:
        return None
    try:
        ts = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except (TypeError, ValueError):
        return None


def _follow_through(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str) -> None:
    """Verifica l'esito della chiusura accodata da una regola 'triggered' e agisce."""
    req_id = rule.get("enqueued_request_id")
    if not req_id:
        return
    rows = (
        sb.table("betfair_live_order_requests").select("id,status,error")
        .eq("id", int(req_id)).limit(1).execute().data or []
    )
    if not rows:
        return
    req_status = str(rows[0].get("status") or "")
    res = _result(rule)

    if req_status in ("pending", "processing"):
        return  # ancora in coda: attendi il prossimo giro

    if req_status == "done":
        # Richiesta eseguita: verifica il FILL dell'hedge (LIMIT LAPSE al best ± place_at può
        # restare unmatched in un mercato veloce). Ordine ritrovato per ref awlq<req_id>.
        order = low._find_order_by_cust_ref(
            flumine, rule.get("market_id"), low._cust_ref(int(req_id))
        )
        remaining = low._f(low._val(order, "size_remaining")) if order is not None else None
        if order is None or remaining is None or remaining <= 0:
            # nessun ordine (greenup no-op: posizione già piatta) o interamente abbinato.
            _update_rule(sb, rule["id"], {"status": "done",
                "result": {**res, "note": f"{res.get('note') or 'chiusura'}; eseguita e verificata"}})
            return
        if res.get("fill_alerted"):
            return  # già escalato: non spammare
        age = _age_seconds(rule.get("triggered_at"))
        if age is not None and age >= _FILL_ALERT_AFTER_SEC:
            _alert("CRITICAL",
                   f"STOP regola {rule.get('id')}: hedge NON (interamente) abbinato dopo "
                   f"{age:.0f}s (resta €{remaining:.2f} unmatched). VERIFICARE e chiudere a mano "
                   f"se necessario (mercato {rule.get('market_id')}).")
            _update_rule(sb, rule["id"], {"result": {**res, "fill_alerted": True}})
        return

    if req_status == "error":
        if _kill_active():
            return  # freno tirato: non accodare (si riprende quando viene tolto)
        retries = int(res.get("close_retries") or 0)
        if retries >= _MAX_CLOSE_RETRIES:
            _update_rule(sb, rule["id"], {"status": "error",
                "error": f"chiusura FALLITA dopo {retries + 1} tentativi "
                         f"(ultimo: {str(rows[0].get('error'))[:120]})"})
            _alert("CRITICAL",
                   f"STOP regola {rule.get('id')}: chiusura FALLITA dopo {retries + 1} tentativi. "
                   f"POSIZIONE ANCORA APERTA su {rule.get('market_id')}: chiudere A MANO.")
            return
        new_ref = f"risk{rule['id']}s{retries + 2}"
        new_req = _enqueue_flatten(sb, rule, mode_l, client_ref=new_ref)
        if new_req is None:
            return  # enqueue KO (transitorio): riprova al giro dopo senza consumare tentativi
        _update_rule(sb, rule["id"], {
            "enqueued_client_ref": new_ref, "enqueued_request_id": new_req,
            "result": {**res, "close_retries": retries + 1}})
        _alert("WARN",
               f"STOP regola {rule.get('id')}: chiusura fallita "
               f"({str(rows[0].get('error'))[:120]}), ritento "
               f"({retries + 1}/{_MAX_CLOSE_RETRIES}).")
        return


def _check_triggered_rules(sb: Any, flumine: Any, mode_l: str) -> int:
    """Follow-through di tutte le regole 'triggered' (best-effort per riga)."""
    try:
        rules = (
            sb.table(_TABLE).select("*").eq("status", "triggered").eq("mode", mode_l)
            .order("id").limit(_batch()).execute().data or []
        )
    except Exception as ex:  # noqa: BLE001 - lettura KO: salta il giro
        logger.warning("[risk] lettura regole triggered KO: %s", str(ex)[:160])
        return 0
    handled = 0
    for rule in rules:
        try:
            _follow_through(sb, flumine, rule, mode_l)
        except Exception:  # noqa: BLE001 - errore transitorio: retry al giro dopo
            logger.warning("[risk] follow-through regola %s: errore transitorio (retry)",
                           rule.get("id"))
        handled += 1
    return handled


# ---------------------------------------------------------------------------
# BRACKET (OCO) — offset take-profit + stop, one-cancels-other (#2)
# ---------------------------------------------------------------------------
def _handle_bracket(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    # FIX audit #1 (defense in depth): un bracket SENZA gamba stop (nessun trigger_*/
    # stop_amount/trail_*) non potrà MAI scattare lo stop — errore PERMANENTE dei dati
    # della regola: disarmo VISIBILE subito, mai "armata" con la protezione morta.
    bad = risk_engine.bracket_missing_stop(_params(rule))
    if bad is not None:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"parametri non validi: {bad}"})
        _alert("CRITICAL",
               f"Regola risk {rule.get('id')} (bracket) DISATTIVATA: {bad}. "
               "LA PROTEZIONE NON È ATTIVA: ri-armare la regola con la gamba stop.")
        return
    market = low._resolve_market(flumine, rule.get("market_id"))
    sel = int(rule["selection_id"]); hcap = float(rule.get("handicap") or 0)
    res = _result(rule)
    if _apply_inplay_policy(sb, rule, market, res) == "disarmed":
        return
    state = str(res.get("state") or "init")

    # FASE 1: piazza l'offset (take-profit) — subito o on-fill dell'ingresso.
    if state == "init":
        timing = str(_params(rule).get("timing") or ("on_fill" if rule.get("entry_bet_id") else "immediate")).lower()
        if timing == "on_fill" or rule.get("entry_bet_id"):
            st = _entry_ready_or_naked(flumine, rule)
            if st == "wait":
                return
            if st == "naked":
                _update_rule(sb, rule["id"], {"status": "done",
                    "result": {**res, "note": "ingresso non abbinato: bracket annullato (anti-gamba-nuda)"}})
                return
            matched, _ = _entry_status(flumine, rule.get("market_id"), rule.get("entry_bet_id"))
            size = matched
        else:
            size = low._f(rule.get("entry_size"))
        if size is None or size <= 0:
            _update_rule(sb, rule["id"], {"status": "error", "error": "bracket: size ingresso non determinabile"})
            return
        if _kill_active():
            return
        p = _params(rule)
        w, l = low._read_matched_exposures(flumine, market, strategy, sel, hcap) if p.get("greening") else (None, None)
        req_id, order = _enqueue_offset(sb, flumine, rule, mode_l, size, w, l)
        if req_id is None:
            _update_rule(sb, rule["id"], {"status": "error", "error": f"bracket offset non calcolabile: {order.note}"})
            return
        res.update({"state": "offset_placed", "offset_request_id": req_id,
                    "offset": {"side": order.side, "price": order.price, "size": order.size}})
        _update_rule(sb, rule["id"], {"enqueued_client_ref": f"risk{rule['id']}o",
                                      "enqueued_request_id": req_id, "result": res})
        return

    # FASE 2: OCO — l'offset è piazzato; monitora take-profit vs stop.
    if state == "offset_placed":
        offset_req = res.get("offset_request_id")
        off = _offset_order_obj(flumine, rule.get("market_id"), offset_req)
        off_status = None
        off_matched = 0.0
        off_bet_id = None
        if off is not None:
            st = low._val(off, "status")
            off_status = getattr(st, "name", None) or (str(st) if st is not None else None)
            off_matched = low._f(low._val(off, "size_matched")) or 0.0
            off_bet_id = low._val(off, "bet_id")

        # a) TAKE-PROFIT eseguito → OCO: posizione chiusa dall'offset, stop non serve più.
        if off_matched > 0 and off_status == "EXECUTION_COMPLETE":
            _update_rule(sb, rule["id"], {"status": "done", "triggered_at": _now_iso(),
                "result": {**res, "state": "done", "note": "take-profit (offset) eseguito; stop annullato (OCO)"}})
            return

        # b) STOP: valuta la condizione avversa.
        ltp = _ltp(market, sel, hcap)
        best_back, best_lay = low._best_prices(market, sel, hcap)
        w, l = low._read_matched_exposures(flumine, market, strategy, sel, hcap)
        decision = risk_engine.evaluate_rule(
            rule_type="stop_loss", entry_side=str(rule.get("entry_side")),
            entry_price=low._f(rule.get("entry_price")), params=_params(rule), current_price=ltp,
            matched_if_win=w, matched_if_lose=l, best_back_price=best_back, best_lay_price=best_lay,
            trail_extreme=low._f(rule.get("trail_extreme")),
        )
        # Parametri invalidi = errore PERMANENTE → disarmo VISIBILE (mai retry silenzioso).
        if decision.error:
            _update_rule(sb, rule["id"], {"status": "error",
                                          "error": f"parametri non validi: {decision.error}"})
            _alert("CRITICAL",
                   f"Regola risk {rule.get('id')} (bracket) DISATTIVATA: parametri non validi "
                   f"({decision.error}). LA PROTEZIONE NON È ATTIVA: ri-armare la regola.")
            return
        # trailing opzionale nel bracket: se sono presenti trail_*, valuta anche quello.
        if not decision.fire and (risk_engine._int_param(_params(rule), "trail_ticks") is not None
                                  or risk_engine._num(_params(rule), "trail_pct") is not None):
            dtr = risk_engine.evaluate_rule(
                rule_type="trailing_stop", entry_side=str(rule.get("entry_side")),
                entry_price=low._f(rule.get("entry_price")), params=_params(rule), current_price=ltp,
                matched_if_win=w, matched_if_lose=l, best_back_price=best_back, best_lay_price=best_lay,
                trail_extreme=low._f(rule.get("trail_extreme")))
            if dtr.error:
                _update_rule(sb, rule["id"], {"status": "error",
                                              "error": f"parametri non validi: {dtr.error}"})
                _alert("CRITICAL",
                       f"Regola risk {rule.get('id')} (bracket/trailing) DISATTIVATA: parametri "
                       f"non validi ({dtr.error}). LA PROTEZIONE NON È ATTIVA.")
                return
            if dtr.trail_extreme is not None:
                prev = low._f(rule.get("trail_extreme"))
                if prev is None or abs(prev - dtr.trail_extreme) > 1e-9:
                    _update_rule(sb, rule["id"], {"trail_extreme": dtr.trail_extreme})
            decision = dtr if dtr.fire else decision

        if not decision.fire:
            return
        if _kill_active():
            return

        # STOP scattato → OCO: DEVI prima cancellare l'offset, POI chiudere. FIX review HIGH:
        # se NON hai ancora il bet_id dell'offset (non ancora piazzato dalla coda, oppure bet_id
        # non assegnato) NON flattenare: ASPETTA un giro. Altrimenti la coda piazzerebbe DOPO
        # l'offset come take-profit resting NUDO che il monitoraggio (solo 'armed') non cancella
        # mai → una posizione nuova indesiderata a mercato. Solo con bet_id disponibile si procede.
        if not off_bet_id:
            return
        _enqueue(sb, {"client_ref": f"risk{rule['id']}oc", "action": "cancel",
                      "mode": mode_l, "market_id": rule["market_id"], "bet_id": str(off_bet_id)})
        if abs(w - l) < risk_engine.FLAT_EPS:
            _update_rule(sb, rule["id"], {"status": "done", "triggered_at": _now_iso(),
                "result": {**res, "state": "done", "note": f"{decision.reason}; posizione piatta (offset cancellato)"}})
            return
        stop_req = _enqueue_flatten(sb, rule, mode_l)
        _update_rule(sb, rule["id"], {"status": "triggered", "enqueued_client_ref": f"risk{rule['id']}s",
            "enqueued_request_id": stop_req, "triggered_at": _now_iso(),
            "result": {**res, "state": "stopped", "note": f"{decision.reason}; offset cancellato (OCO)"}})
        return


# ---------------------------------------------------------------------------
# STOP-ENTRY (roadmap C23) — ordine condizionale: ENTRA al tocco della soglia
# ---------------------------------------------------------------------------
def _handle_stop_entry(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str) -> None:
    """Entra (place) SOLO quando l'LTP tocca ``params.trigger_price`` nella direzione
    ``params.trigger_direction`` (at_or_above|at_or_below). Un INGRESSO mancato non è
    una posizione che sanguina: niente follow-through di flatten — l'esito dell'ordine
    è visibile nello specchio; la regola chiude qui ('done')."""
    market = low._resolve_market(flumine, rule.get("market_id"))
    sel = int(rule["selection_id"]); hcap = float(rule.get("handicap") or 0)
    res = _result(rule)
    if _apply_inplay_policy(sb, rule, market, res) == "disarmed":
        return
    p = _params(rule)
    trigger = low._f(p.get("trigger_price"))
    direction = str(p.get("trigger_direction") or "")
    size = low._f(rule.get("entry_size"))
    side = str(rule.get("entry_side") or "").lower()
    if size is None or size <= 0 or side not in ("back", "lay"):
        _update_rule(sb, rule["id"], {"status": "error",
                                      "error": "stop_entry: entry_size/entry_side non validi"})
        _alert("CRITICAL", f"Stop-entry {rule.get('id')} DISATTIVATO: entry_size/side non validi.")
        return
    ltp = _ltp(market, sel, hcap)
    try:
        fired = risk_engine.stop_entry_fires(
            direction, trigger if trigger is not None else float("nan"), ltp)
    except ValueError as ex:  # parametri PERMANENTEMENTE invalidi: disarmo VISIBILE
        _update_rule(sb, rule["id"], {"status": "error", "error": f"parametri non validi: {ex}"})
        _alert("CRITICAL", f"Stop-entry {rule.get('id')} DISATTIVATO: {ex}.")
        return
    if not fired:
        return  # resta armata
    if _kill_active():
        return  # freno d'emergenza: non entrare, resta armata
    best_back, best_lay = low._best_prices(market, sel, hcap)
    place_at = str(p.get("place_at") or "best").lower()
    price = trigger if place_at == "trigger" else (best_back if side == "back" else best_lay)
    if price is None:
        return  # book momentaneamente vuoto: transitorio, riprova al giro dopo
    req_id = _enqueue(sb, {
        "client_ref": f"risk{rule['id']}e", "action": "place", "mode": mode_l,
        "market_id": rule["market_id"], "selection_id": rule["selection_id"],
        "handicap": rule.get("handicap") or 0, "side": side,
        "price": price, "size": size,
        "persistence": (p.get("persistence") or "LAPSE"),
        "params": {"risk_rule_id": rule["id"], "role": "stop_entry"},
    })
    _update_rule(sb, rule["id"], {"status": "done", "enqueued_client_ref": f"risk{rule['id']}e",
        "enqueued_request_id": req_id, "triggered_at": _now_iso(),
        "result": {"note": f"stop-entry scattato: LTP {ltp} {direction} {trigger}",
                   "side": side, "price": price, "size": size}})


# ---------------------------------------------------------------------------
# CHASE / tick-offset sul re-quote (roadmap C25) — insegui il best
# ---------------------------------------------------------------------------
# Macchina a stati CANCEL→PLACE (mai un replaceOrders singolo, stessa filosofia del
# drag-move): non esistono MAI due ordini vivi contemporaneamente, e si ripiazza SOLO
# la size rimasta non abbinata. Stato persistito in result jsonb:
#   phase: 'tracking' | 'cancelling' | 'placing' · chase_count · place_request_id ·
#   pending_size (size da ripiazzare, catturata alla decisione di re-quote).
_CHASE_DEFAULT_MAX = 20


def _chase_done(sb: Any, rule: Dict[str, Any], res: Dict[str, Any], note: str) -> None:
    _update_rule(sb, rule["id"], {"status": "done", "triggered_at": _now_iso(),
                                  "result": {**res, "note": note}})


def _handle_chase(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str) -> None:
    market = low._resolve_market(flumine, rule.get("market_id"))
    sel = int(rule["selection_id"]); hcap = float(rule.get("handicap") or 0)
    res = _result(rule)
    # Fix review MEDIUM: la policy in-play può disarmare SOLO in fase 'tracking' — mai a
    # metà di un ciclo cancel→place (disarmo in 'placing' orfanerebbe l'ordine ripiazzato,
    # che nessuna regola tornerebbe a tracciare).
    if str(res.get("phase") or "tracking") == "tracking" \
       and _apply_inplay_policy(sb, rule, market, res) == "disarmed":
        return
    p = _params(rule)
    side = str(rule.get("entry_side") or "").lower()
    try:
        offset_ticks = int(p.get("offset_ticks") or 0)
        if offset_ticks < 0:
            raise ValueError(f"offset_ticks non valido: {offset_ticks!r}")
    except (TypeError, ValueError) as ex:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"parametri non validi: {ex}"})
        _alert("CRITICAL", f"Chase {rule.get('id')} DISATTIVATO: {ex}.")
        return
    max_chases = int(low._f(p.get("max_chases")) or _CHASE_DEFAULT_MAX)
    phase = str(res.get("phase") or "tracking")
    count = int(res.get("chase_count") or 0)

    # ---- fase PLACING: attende che il ripiazzo diventi un ordine vivo -----------------
    if phase == "placing":
        rid = res.get("place_request_id")
        order = _offset_order_obj(flumine, rule.get("market_id"), rid)
        if order is None:
            # richiesta ancora in coda o fallita: se la coda l'ha marcata 'error' → disarmo
            try:
                row = (sb.table(low._TABLE).select("status,error").eq("id", int(rid))
                       .limit(1).execute().data or [None])[0]
            except Exception:  # noqa: BLE001 - lettura best-effort: riprova al giro dopo
                row = None
            if row and row.get("status") == "error":
                _update_rule(sb, rule["id"], {"status": "error",
                    "error": f"chase: ripiazzo rifiutato ({str(row.get('error'))[:120]}) — nessun ordine a mercato"})
                _alert("CRITICAL", f"Chase {rule.get('id')}: ripiazzo RIFIUTATO, l'ordine NON è più a mercato.")
                return
            # Fix review MEDIUM: ripiazzo che non si materializza (coda ferma/worker giù):
            # dopo la soglia escala UNA volta con alert — l'ordine è FUORI mercato e
            # l'utente deve saperlo (stesso pattern del follow-through degli stop).
            age = _age_seconds(res.get("placing_since"))
            if age is not None and age > _FILL_ALERT_AFTER_SEC * 3 and not res.get("placing_alerted"):
                res["placing_alerted"] = True
                _update_rule(sb, rule["id"], {"result": res})
                _alert("CRITICAL",
                       f"Chase {rule.get('id')}: ripiazzo in coda da {age:.0f}s senza esito — "
                       "l'ordine NON è a mercato (runner/coda fermi?). Verifica.")
            return
        new_bet = getattr(order, "bet_id", None)
        res.update({"phase": "tracking", "chase_count": count + 1,
                    "current_bet_id": str(new_bet) if new_bet else None,
                    "place_request_id": None, "pending_size": None})
        _update_rule(sb, rule["id"], {"result": res})
        return

    # ---- risolvi l'ordine CORRENTE da inseguire ---------------------------------------
    bet_id = str(res.get("current_bet_id") or rule.get("entry_bet_id") or "")
    if not bet_id:
        _update_rule(sb, rule["id"], {"status": "error", "error": "chase: entry_bet_id obbligatorio"})
        return
    order = low._find_order_by_bet_id(flumine, rule.get("market_id"), bet_id)
    if order is None:
        _chase_done(sb, rule, res, "ordine non più nel blotter: chase concluso")
        return
    st = getattr(getattr(order, "status", None), "name", None) or str(getattr(order, "status", ""))
    rem = low._f(getattr(order, "size_remaining", None)) or 0.0

    # ---- fase CANCELLING: aspetta il terminale, poi ripiazza SOLO il non-abbinato -----
    if phase == "cancelling":
        if st == "EXECUTION_COMPLETE":
            _chase_done(sb, rule, res, "abbinato durante il re-quote: chase concluso")
            return
        if st in _TERMINAL:
            # Fix review CRITICAL: il terminale può essere CANCELLED ma anche LAPSED/
            # VOIDED/EXPIRED (es. persistence LAPSE + passaggio in-play durante il cancel):
            # flumine espone campi SEPARATI (size_cancelled/lapsed/voided, mutuamente
            # esclusivi). Si sommano i campi PRESENTI; il fallback a pending_size (snapshot
            # pre-cancel, che NON sconta un fill avvenuto nella race) è SOLO per oggetti
            # privi di tutti i campi. MAI `or` su uno 0.0 legittimo (nulla da ripiazzare
            # ≠ dato mancante: ripiazzerebbe size già abbinata → esposizione doppiata).
            parts = [low._f(getattr(order, f, None))
                     for f in ("size_cancelled", "size_lapsed", "size_voided")]
            known = [v for v in parts if v is not None]
            to_place = float(sum(known)) if known else (low._f(res.get("pending_size")) or 0.0)
            if to_place <= 0:
                _chase_done(sb, rule, res, "nulla da ripiazzare dopo il cancel: chase concluso")
                return
            best_back, best_lay = low._best_prices(market, sel, hcap)
            target = risk_engine.chase_target_price(side, best_back, best_lay, offset_ticks)
            if target is None:
                return  # book vuoto: transitorio, ripiazza al giro dopo (ordine GIÀ cancellato)
            if _kill_active():
                return
            req_id = _enqueue(sb, {
                "client_ref": f"risk{rule['id']}cp{count}", "action": "place", "mode": mode_l,
                "market_id": rule["market_id"], "selection_id": rule["selection_id"],
                "handicap": rule.get("handicap") or 0, "side": side,
                "price": target, "size": round(float(to_place), 2),
                "persistence": (p.get("persistence") or "LAPSE"),
                "params": {"risk_rule_id": rule["id"], "role": "chase"},
            })
            res.update({"phase": "placing", "place_request_id": req_id,
                        "placing_since": _now_iso(), "placing_alerted": False})
            _update_rule(sb, rule["id"], {"result": res})
        return  # cancel ancora in volo: aspetta

    # ---- fase TRACKING: decide se re-quotare -------------------------------------------
    if st in _TERMINAL or rem <= 0:
        _chase_done(sb, rule, res, f"ordine terminale ({st or 'abbinato'}): chase concluso")
        return
    best_back, best_lay = low._best_prices(market, sel, hcap)
    try:
        target = risk_engine.chase_target_price(side, best_back, best_lay, offset_ticks)
    except ValueError as ex:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"parametri non validi: {ex}"})
        _alert("CRITICAL", f"Chase {rule.get('id')} DISATTIVATO: {ex}.")
        return
    cur_price = low._f(getattr(getattr(order, "order_type", None), "price", None))
    if not risk_engine.chase_should_requote(cur_price, target):
        return
    if count >= max_chases:
        _chase_done(sb, rule, res, f"cap re-quote raggiunto ({max_chases}): l'ordine resta @ {cur_price}")
        return
    if _kill_active():
        return
    _enqueue(sb, {"client_ref": f"risk{rule['id']}cc{count}", "action": "cancel",
                  "mode": mode_l, "market_id": rule["market_id"], "bet_id": bet_id})
    res.update({"phase": "cancelling", "pending_size": rem, "current_bet_id": bet_id})
    _update_rule(sb, rule["id"], {"result": res})


# ---------------------------------------------------------------------------
# AUTO-HEDGE (F39) — floor-keeper del worst-case SCORELINE dell'evento
# ---------------------------------------------------------------------------
# Analisi più vecchia di così = stantia: MAI coprire su quote/esposizioni vecchie
# (l'xhedge_worker riscrive ogni ~5s → 30s = 6 cicli di tolleranza).
_AUTOHEDGE_FRESH_SEC = 30.0
_AUTOHEDGE_DEFAULT_MAX = 3
_AUTOHEDGE_DEFAULT_COOLDOWN_SEC = 60.0
# sotto il minimo stake .it il place normale verrebbe rifiutato → flusso submin.
_AUTOHEDGE_MIN_STAKE_IT = 2.0


def _handle_auto_hedge(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str) -> None:
    """Mantiene il worst-case scoreline dell'EVENTO ≥ −params.floor: quando sfora,
    accoda la copertura CS suggerita da betfair_live_xhedge (ID esatti dal worker).

    MONEY-CRITICAL — guardie esplicite, MAI una copertura al buio:
      * analisi FRESCA (≤30s) e matrice COMPLETA (ignored_orders=0);
      * suggerimento actionable CON market_id/selection_id/odds/size validi;
      * cooldown tra coperture (default 60s: lascia abbinare e rientrare l'analisi);
      * cap coperture (default 3): raggiunto con worst ancora sotto il floor →
        alert CRITICAL e regola 'done' (mai inseguire all'infinito);
      * kill-switch → nessuna copertura (resta armata);
      * la regola RESTA armata dopo una copertura (floor-keeper), stato in result.
    """
    p = _params(rule)
    res = _result(rule)
    floor = low._f(p.get("floor"))
    event_id = str(p.get("event_id") or "")
    if floor is None or floor <= 0 or not event_id:
        _update_rule(sb, rule["id"], {"status": "error",
                                      "error": "auto_hedge: params.floor>0 e params.event_id obbligatori"})
        _alert("CRITICAL", f"Auto-hedge {rule.get('id')} DISATTIVATO: parametri non validi.")
        return
    max_hedges = int(low._f(p.get("max_hedges")) or _AUTOHEDGE_DEFAULT_MAX)
    cooldown = float(low._f(p.get("cooldown_sec")) or _AUTOHEDGE_DEFAULT_COOLDOWN_SEC)
    hedges = int(res.get("hedges_done") or 0)

    # cooldown fra coperture: la copertura precedente deve abbinarsi ed entrare
    # nello specchio prima di rivalutare (altrimenti si copre due volte lo stesso buco).
    age_last = _age_seconds(res.get("last_hedge_ts"))
    if age_last is not None and age_last < cooldown:
        return

    # analisi x-hedge dell'evento (scritta dall'xhedge_worker ogni ~5s)
    try:
        rows = (sb.table("betfair_live_xhedge").select("analysis,updated_at")
                .eq("event_id", event_id).eq("mode", mode_l).limit(1).execute().data or [])
    except Exception:  # noqa: BLE001 - blip DB: transitorio, riprova al giro dopo
        return
    if not rows:
        return  # nessuna analisi (ancora): resta armata
    row = rows[0]
    if (_age_seconds(row.get("updated_at")) or 1e9) > _AUTOHEDGE_FRESH_SEC:
        return  # analisi stantia: MAI coprire su dati vecchi (riprova al giro dopo)
    analysis = row.get("analysis") or {}
    if int(analysis.get("ignored_orders") or 0) > 0:
        # matrice INCOMPLETA = il worst mostrato NON è il worst reale → mai auto-coprire.
        if not res.get("warned_incomplete"):
            res["warned_incomplete"] = True
            _update_rule(sb, rule["id"], {"result": res})
            _alert("WARN", f"Auto-hedge {rule.get('id')}: matrice x-hedge INCOMPLETA "
                           "(ordini non modellati) — coperture SOSPESE finché non si risolve.")
        return
    if res.get("warned_incomplete"):
        res.pop("warned_incomplete", None)  # rientrata: riabilita (e azzera l'anti-spam)
        _update_rule(sb, rule["id"], {"result": res})

    worst = low._f((analysis.get("summary") or {}).get("worst"))
    if worst is None:
        return
    if worst >= -floor:
        return  # floor rispettato: resta armata, nessuna azione

    # floor SFORATO → serve una copertura
    if hedges >= max_hedges:
        _update_rule(sb, rule["id"], {"status": "done", "triggered_at": _now_iso(),
            "result": {**res, "note": f"cap coperture raggiunto ({max_hedges}) con worst "
                                      f"{worst:.2f} < −{floor:.2f}: intervento manuale richiesto"}})
        _alert("CRITICAL", f"Auto-hedge {rule.get('id')}: cap {max_hedges} coperture raggiunto "
                           f"ma worst-case €{worst:.2f} ancora sotto −€{floor:.2f} — INTERVENIRE A MANO.")
        return
    if _kill_active():
        return  # freno d'emergenza: nessuna apertura, resta armata

    sug = analysis.get("suggestion") or {}
    sug_mid = sug.get("market_id")
    sug_sel = sug.get("selection_id")
    odds = low._f(sug.get("odds"))
    size = low._f(sug.get("size"))
    if not (sug.get("actionable") and sug_mid and sug_sel is not None
            and odds is not None and odds > 1.01 and size is not None and size >= 0.01):
        # floor sforato ma nessuna copertura eseguibile (quota CS assente, ID mancanti):
        # l'utente DEVE saperlo — alert una volta per episodio (flag azzerato al rientro).
        if not res.get("warned_nosug"):
            res["warned_nosug"] = True
            _update_rule(sb, rule["id"], {"result": res})
            _alert("CRITICAL", f"Auto-hedge {rule.get('id')}: worst-case €{worst:.2f} sotto "
                               f"−€{floor:.2f} ma NESSUNA copertura eseguibile (quota/ID CS "
                               "mancanti) — VALUTARE A MANO.")
        return
    res.pop("warned_nosug", None)

    max_stake = low._f(p.get("max_stake"))
    if max_stake is not None and max_stake > 0:
        size = min(size, max_stake)
    size = round(size, 2)
    submin = size < _AUTOHEDGE_MIN_STAKE_IT
    n = hedges + 1
    ref = f"risk{rule['id']}h{n}"  # deterministico: mai due coperture per lo stesso trigger
    payload = {
        "client_ref": ref, "action": ("place_submin" if submin else "place"),
        "mode": mode_l, "market_id": str(sug_mid), "selection_id": int(sug_sel),
        "handicap": 0, "side": "back", "price": odds, "size": size,
        "persistence": "LAPSE",
        "params": {"risk_rule_id": rule["id"], "role": "auto_hedge",
                   # FoK 10s (C22) sul place normale: una copertura non abbinata NON deve
                   # restare sul book a un prezzo vecchio (il submin ha la sua macchina a stati).
                   **({} if submin else {"fok_ttl_sec": 10})},
    }
    req_id = _enqueue(sb, payload)
    res.update({"hedges_done": n, "last_hedge_ts": _now_iso(), "last_request_id": req_id,
                "note": f"copertura #{n}: BACK CS {sug.get('scoreline')} €{size:.2f}@{odds} "
                        f"(worst €{worst:.2f} < −€{floor:.2f})"})
    _update_rule(sb, rule["id"], {"result": res, "triggered_at": _now_iso()})
    _alert("WARN", f"AUTO-HEDGE {rule.get('id')}: worst-case €{worst:.2f} sotto −€{floor:.2f} → "
                   f"copertura #{n}/{max_hedges} accodata: BACK CS {sug.get('scoreline')} "
                   f"€{size:.2f}@{odds} ({'submin' if submin else 'FoK 10s'}).")


# ---------------------------------------------------------------------------
# BUG FIX cert 10/07 (#9) — DISARM di una regola con TP resting GIÀ piazzato:
# l'ordine offset creato DALLA REGOLA restava VIVO sul book (ordine nudo che può
# abbinarsi dopo = perdita). Al disarm (status 'cancelled') il worker ora CANCELLA
# anche l'offset resting. Idempotente via flag result.offset_cleanup.
# ---------------------------------------------------------------------------
def _cleanup_cancelled_offsets(sb: Any, flumine: Any, mode_l: str) -> int:
    """Cancella gli offset resting delle regole DISARMATE manualmente. Ritorna
    quante regole ha ripulito. Best-effort: un KO non ferma il ciclo."""
    try:
        rows = (
            sb.table(_TABLE).select("*").eq("status", "cancelled").eq("mode", mode_l)
            .order("id", desc=True).limit(20).execute().data or []
        )
    except Exception:  # noqa: BLE001 - lettura best-effort
        return 0
    cleaned = 0
    for rule in rows:
        res = _result(rule)
        req_id = res.get("offset_request_id")
        if req_id is None or res.get("offset_cleanup"):
            continue  # nessun TP creato dalla regola, o già ripulito
        order = _offset_order_obj(flumine, rule.get("market_id"), req_id)
        note = None
        if order is None:
            # ordine non risolvibile sul framework CORRENTE (restart/mercato chiuso):
            # non possiamo garantire il ritiro → ALERT esplicito, mai silenzio.
            note = "disarm: offset NON risolvibile sul framework — VERIFICARE a mano"
            _alert("CRITICAL", f"Regola {rule.get('id')} disarmata ma il take-profit "
                               "resting non è risolvibile: VERIFICA il book a mano.")
        else:
            rem = low._f(low._val(order, "size_remaining")) or 0.0
            if rem > 0:
                bet_id = low._val(order, "bet_id")
                _enqueue(sb, {"client_ref": f"risk{rule['id']}dc", "action": "cancel",
                              "mode": mode_l, "market_id": rule.get("market_id"),
                              "bet_id": bet_id})
                note = f"disarm: take-profit resting CANCELLATO (bet {bet_id})"
                _alert("INFO", f"Regola {rule.get('id')} disarmata: TP resting ritirato dal book.")
            else:
                note = "disarm: offset già abbinato/terminale — nulla da ritirare"
        res["offset_cleanup"] = True
        if note:
            res["cleanup_note"] = note
        _update_rule(sb, rule["id"], {"result": res})
        cleaned += 1
    return cleaned


# ---------------------------------------------------------------------------
# Dispatch + ciclo
# ---------------------------------------------------------------------------
def _process_rule(sb: Any, flumine: Any, rule: Dict[str, Any], mode_l: str, strategy: Any) -> None:
    rt = str(rule.get("rule_type") or "")
    if rt == "offset":
        _handle_offset(sb, flumine, rule, mode_l, strategy)
    elif rt == "bracket":
        _handle_bracket(sb, flumine, rule, mode_l, strategy)
    elif rt in ("stop_loss", "take_profit", "trailing_stop"):
        _handle_monitored(sb, flumine, rule, mode_l, strategy)
    elif rt == "stop_entry":
        _handle_stop_entry(sb, flumine, rule, mode_l)
    elif rt == "chase":
        _handle_chase(sb, flumine, rule, mode_l)
    elif rt == "auto_hedge":
        _handle_auto_hedge(sb, flumine, rule, mode_l)
    else:
        _update_rule(sb, rule["id"], {"status": "error", "error": f"rule_type sconosciuto: {rt!r}"})


def _read_armed_rules(sb: Any, mode_l: str) -> list:
    try:
        return (
            sb.table(_TABLE).select("*").eq("status", "armed").eq("mode", mode_l)
            .order("id").limit(_batch()).execute().data or []
        )
    except Exception as ex:  # noqa: BLE001
        logger.warning("[risk] lettura regole armate KO: %s", str(ex)[:160])
        return []


def _process_once(sb: Any, flumine: Any, strategy: Any = None) -> int:
    mode = low._live_order_mode()
    if mode not in ("PAPER", "LIVE"):
        return 0
    low._refresh_settings(sb)  # snapshot settings (kill-switch UI condiviso con l'order worker)
    # #15 velocità runtime: rallenta la cadenza al target risk_poll_sec (se impostato), senza riavvio.
    if low._throttled("risk_cycle", low._risk_poll_target()):
        return 0
    mode_l = mode.lower()
    rules = _read_armed_rules(sb, mode_l)
    handled = 0
    for rule in rules:
        rid = rule.get("id")
        try:
            _process_rule(sb, flumine, rule, mode_l, strategy)
        except Exception:  # noqa: BLE001 - errore TRANSITORIO: NON disarmare la regola protettiva
            # (mercato momentaneamente assente, blip DB) → resta 'armed', retry al giro dopo.
            # Le condizioni davvero invalide sono marcate 'error' ESPLICITAMENTE negli handler
            # (evaluate_rule le classifica in RuleDecision.error: MAI un ValueError da params).
            logger.warning("[risk] regola %s: errore transitorio, resta armata (retry)", rid)
        handled += 1
    # Fix HIGH-3: 'triggered' non è terminale di fiducia — verifica esito/fill delle chiusure
    # accodate, ritenta le fallite (bounded) ed escala con alert quelle irrecuperabili.
    handled += _check_triggered_rules(sb, flumine, mode_l)
    # BUG FIX #9 (cert 10/07): disarm manuale → ritira anche il TP resting della regola
    handled += _cleanup_cancelled_offsets(sb, flumine, mode_l)
    return handled


def risk_engine_worker(context: dict, flumine: Any, session: Any = None, strategy: Any = None) -> None:
    """BackgroundWorker flumine (firma: context, flumine, **func_kwargs). Non solleva MAI.

    Aggiunto al framework SOLO se LIVE_ORDER_MODE ∈ {PAPER, LIVE} (vedi runner). ``strategy``
    (LiveTradingStrategy) serve per leggere le esposizioni MATCHED (flatten/greening).
    """
    if flumine is None:
        return
    try:
        from db_client import get_supabase_client
        sb = get_supabase_client()
    except Exception as ex:  # noqa: BLE001
        logger.warning("[risk] supabase non disponibile: %s", str(ex)[:160])
        return
    try:
        _process_once(sb, flumine, strategy)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[risk] ciclo KO: %s", str(ex)[:200])
