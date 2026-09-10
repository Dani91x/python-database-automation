"""execution.py — strato CONDIVISO di piazzamento e CHIUSURA (cash-out/green-up).

Perché qui e non dentro un bot: la stessa matematica e la stessa sequenza di
scritture servono a DUE bot (Omega e Safe Strategy) e domani a un terzo. Il
modulo è ORCHESTRAZIONE PURA con dipendenze INIETTATE (``db``, ``market``):
non conosce Supabase né Betfair, quindi è collaudabile con fake.

Contratto (tutto money-critical, invarianti del repo):
  • RESERVE-FIRST: la riga 'pending' esiste PRIMA dell'ordine (il chiamante la
    inserisce per il place automatico; ``close_trade`` la inserisce da sé per la
    gamba di chiusura). Un ordine reale non resta MAI non tracciato.
  • MAI un fill parziale non contabilizzato: la size è CAPPATA alla liquidità
    abbinabile al miglior prezzo (``best_size``) prima di piazzare.
  • PAPER = LIVE: se il gate flumine passa, anche il paper passa dalla coda del
    runner (fill simulato REALE: coda, liquidità, betDelay). Gate KO → fallback
    dichiarato (fill su snapshot in paper, place REST FOK in live).
  • Il ``mode`` deriva SEMPRE e SOLO dal trade: mai un ordine 'live' da un
    trade paper (invariante supremo di Omega §6-bis).

Nota sul ``client_ref``: la coda ``betfair_live_order_requests`` ha UNIQUE su
``client_ref``. Omega usa ``omega-t<id>``; il bot Safe Strategy ha una sequenza
di id INDIPENDENTE, quindi deve usare un suo prefisso (``safe-t<id>``) o due
trade diversi condividerebbero la stessa riga di coda (fill attribuito al trade
sbagliato). Per questo l'enqueue qui è parametrico sul ref: è il PORT fedele di
``omega_service._flumine_enqueue_place`` (stesse scritture, stesso ordine,
stesso recovery per client_ref), col ref reso esplicito. Il GATE invece è
riusato tale e quale da ``omega_service._flumine_gate``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from Betfair.omega import omega_engine as E
from Betfair.stream.trading.greenup import GreenupPlan, compute_greenup

logger = logging.getLogger("safe.execution")

# sentinella: esito enqueue IGNOTO in LIVE (mai il place REST subito).
ENQUEUE_UNKNOWN = -1


def _omega_service() -> Any:
    """omega_service (gate flumine) con import PIGRO e guardato: se manca, il
    gate resta CHIUSO e si usa il percorso legacy — mai un crash del bot."""
    try:
        from Betfair.omega import omega_service as _os

        return _os
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.exec] omega_service non importabile (gate chiuso): %s", str(ex)[:160])
        return None


def liability_of(side: str, size: float, price: float) -> float:
    """Rischio massimo della gamba: LAY = size*(price-1); BACK = stake."""
    if str(side).lower() == "lay":
        return E.liability_from_lay(size, price)
    return round(float(size), 2)


def opposite(side: str) -> str:
    return "back" if str(side).lower() == "lay" else "lay"


# ---------------------------------------------------------------------------
# PIAZZAMENTO
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PlaceOutcome:
    """Esito del piazzamento.

    status 'open'    = matchato (price/size sono quelli REALI)
           'pending' = accodato su flumine, il fill arriva dal poll di ciclo
           'error'   = nessun ordine attivo (motivo in ``fill_note``)
    """

    status: str
    price: Optional[float]
    size: float
    bet_id: Optional[str]
    fill_note: str

    @property
    def ok(self) -> bool:
        return self.status in ("open", "pending")


def place(
    *,
    db,
    market,
    mode: str,
    event_id: str,
    market_id: str,
    selection_id: int,
    side: str,
    price: Optional[float],
    size: Optional[float],
    best_size: Optional[float] = None,
    ladder: Any = (),
    client_ref: str,
    trade_id: Optional[int] = None,
    meta: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
    params: Optional[dict[str, Any]] = None,
) -> PlaceOutcome:
    """Esegue UN ordine per una riga già RISERVATA ('pending').

    ``trade_id`` serve solo alle scritture di marcatura flumine; se assente si
    ricava dal suffisso di ``client_ref``. ``best_size`` è la liquidità
    abbinabile al miglior prezzo: la size viene cappata lì (mai fill parziali).
    """
    params = params or {}
    meta = dict(meta or {})
    mode = str(mode)
    side = str(side).lower()
    if mode not in ("paper", "live"):
        return PlaceOutcome("error", None, 0.0, None, f"mode_non_valido:{mode}")
    if side not in ("back", "lay"):
        return PlaceOutcome("error", None, 0.0, None, f"side_non_valido:{side}")
    if price is None or float(price) <= 1.0:
        return PlaceOutcome("error", None, 0.0, None, "prezzo_non_disponibile")
    if size is None or float(size) <= 0:
        return PlaceOutcome("error", None, 0.0, None, "size_non_valida")

    price = E.round_to_tick(float(price))  # tick Betfair valido: salvato == piazzato
    size = round(float(size), 2)
    if best_size is not None:
        try:
            avail = round(float(best_size), 2)
        except (TypeError, ValueError):
            avail = None
        if avail is not None and avail > 0 and size > avail:
            meta["size_capped_from"] = size
            size = avail  # MEGLIO COMPLETO CHE PARZIALE (esposizione tracciata)
    if size <= 0:
        return PlaceOutcome("error", None, 0.0, None, "liquidita_insufficiente")

    tid = trade_id if trade_id is not None else _trade_id_from_ref(client_ref)

    # --- gate flumine (PAPER e LIVE): riuso 1:1 di omega_service._flumine_gate ---
    use_flumine, gate_reason = _gate(event_id, db=db, mode=mode, params=params, now=now)
    if use_flumine and tid is not None:
        rid = enqueue_place(
            db=db, trade_id=tid, client_ref=client_ref, event_id=event_id,
            market_id=market_id, selection_id=selection_id, side=side,
            price=price, size=size, base_meta=meta, now=now, mode=mode,
        )
        if rid:
            return PlaceOutcome("pending", price, size, None,
                                f"flumine_{mode}:{rid if rid > 0 else 'unknown'}")
        gate_reason = "enqueue_failed"

    # --- percorso legacy (fallback SEMPRE disponibile) ---
    if mode == "paper":
        try:
            fill = E.paper_fill(size, best_price=price, lay_ladder=_ladder_tuple(ladder))
        except Exception as ex:  # noqa: BLE001 — stessa semantica del live
            return _reconciling(db, tid, meta=meta, mode=mode, price=price, size=size, ex=ex)
        if fill is None or fill.matched_size <= 0:
            return PlaceOutcome("error", None, 0.0, None, f"paper_no_fill:{gate_reason}")
        return PlaceOutcome("open", fill.avg_price, fill.matched_size, None,
                            f"paper_fill:{gate_reason}")

    # LIVE — soldi veri: REST FOK generico (side esplicito).
    try:
        res = market.place_order_live(
            market_id=str(market_id), selection_id=int(selection_id), price=price,
            size=size, event_id=str(event_id), side=side, customer_ref=client_ref[:32],
        )
    except Exception as ex:  # noqa: BLE001 — esito IGNOTO: MAI ripiazzare
        return _reconciling(db, tid, meta=meta, mode=mode, price=price, size=size, ex=ex)
    # rifiuto PROVATO dall'exchange (risposta ricevuta, nessun fill): 'error' legittimo
    if not res.ok or res.size_matched <= 0:
        return PlaceOutcome("error", None, 0.0, None,
                            f"live_not_matched:{res.order_status}")
    return PlaceOutcome("open", float(res.avg_price_matched or price),
                        round(float(res.size_matched), 2), res.bet_id,
                        f"live_rest:{res.order_status}")


def _reconciling(db, trade_id: Optional[int], *, meta: dict[str, Any], mode: str,
                 price: float, size: float, ex: Exception) -> PlaceOutcome:
    """ESITO IGNOTO del place (eccezione: es. timeout DOPO che Betfair ha accettato).

    Come ``omega_service._manual_place``: la riga resta 'pending' (così resta
    nell'indice unico parziale e in ``traded_signal_keys`` → nessun
    ripiazzamento) con ``meta.reason='place_exception_reconciling'``; la
    risolve ``reconcile_pending`` contro lo stato reale su Betfair. 'error' è
    riservato al rifiuto PROVATO dell'exchange prima dell'accettazione.
    """
    err = str(ex)[:160]
    m = dict(meta or {})
    m.update({"phase": "reserved", "reason": "place_exception_reconciling", "err": err})
    if trade_id is not None:
        try:
            db.update_trade(trade_id, meta=m)
        except Exception as ex2:  # noqa: BLE001 — la riga resta comunque pending
            logger.critical("[safe.exec] marker reconciling FALLITO (trade %s): %s",
                            trade_id, str(ex2)[:160])
    _log(db, "place_exception", {"trade_id": trade_id, "mode": mode, "err": err})
    return PlaceOutcome("pending", price, size, None,
                        f"place_exception_reconciling:{err[:120]}")


def is_reconciling(trade: dict[str, Any]) -> bool:
    """Riga 'pending' senza marker flumine il cui ordine potrebbe esistere."""
    meta = trade.get("meta") or {}
    return str(meta.get("reason") or "") == "place_exception_reconciling"


def has_flumine_marker(trade: dict[str, Any]) -> bool:
    meta = trade.get("meta") or {}
    return bool(meta.get("flumine_request_id") or meta.get("flumine_client_ref"))


def reconcile_decision(trade: dict[str, Any], current_orders: list[dict],
                       cleared_orders: list[dict], now_iso: str, *, ref: str) -> dict:
    """Decisione PURA per un pending LIVE dato lo stato reale Betfair — stessa
    logica di ``omega_engine.reconcile_decision`` ma col customerOrderRef
    ESPLICITO (il bot Safe usa ``safe-t<id>``, Omega ``omega-…``)."""
    mid = trade.get("market_id")
    sid = trade.get("selection_id")
    sid = int(sid) if sid is not None else None
    side = str(trade.get("side", "lay")).lower()
    for o in current_orders or []:
        if E._order_matches(o, ref, mid, sid, side):
            matched = float(o.get("size_matched") or 0.0)
            remaining = float(o.get("size_remaining") or 0.0)
            if matched > 0 and remaining <= 0:
                return {"action": "confirm",
                        "price": float(o.get("avg_price_matched") or trade.get("price") or 0.0),
                        "size": matched, "bet_id": o.get("bet_id")}
            return {"action": "keep"}
    for o in cleared_orders or []:
        if E._order_matches(o, ref, mid, sid, side):
            return {"action": "confirm",
                    "price": float(o.get("price") or trade.get("price") or 0.0),
                    "size": float(o.get("size_settled") or trade.get("size") or 0.0),
                    "bet_id": o.get("bet_id")}
    age = E._age_seconds(trade.get("placed_at"), now_iso)
    if age is None or age > 24 * 3600:
        return {"action": "error"}
    if age < E.RECON_GRACE_S:
        return {"action": "keep"}
    return {"action": "free"}


def _trade_id_from_ref(client_ref: str) -> Optional[int]:
    try:
        return int(str(client_ref).rsplit("t", 1)[-1])
    except (ValueError, IndexError):
        return None


def _ladder_tuple(ladder: Any) -> tuple:
    """Normalizza la ladder (lista di liste dal DB / tuple dal book) per paper_fill."""
    if not ladder:
        return ()
    try:
        return tuple((float(p), float(s)) for p, s in ladder)
    except (TypeError, ValueError):
        return ()


def _gate(event_id: str, *, db, mode: str, params: dict[str, Any],
          now: Optional[datetime]) -> "tuple[bool, str]":
    """Gate flumine di Omega (fail-closed): (usa_flumine, motivo)."""
    os_mod = _omega_service()
    if os_mod is None or now is None:
        return False, "gate_non_disponibile"
    try:
        return os_mod._flumine_gate(str(event_id), db=db, mode=str(mode),
                                    params=params, now=now)
    except Exception as ex:  # noqa: BLE001 — qualunque dubbio → legacy
        return False, f"gate_error:{str(ex)[:80]}"


def enqueue_place(*, db, trade_id: int, client_ref: str, event_id: str, market_id: str,
                  selection_id: int, side: str, price: float, size: float,
                  base_meta: Optional[dict], now: datetime,
                  mode: str = "paper") -> Optional[int]:
    """Accoda il place sulla coda del runner col ``client_ref`` dato.

    PORT fedele di ``omega_service._flumine_enqueue_place`` (ref parametrico):
    marker ``flumine_client_ref`` persistito PRIMA dell'enqueue (se il processo
    muore in mezzo il pending resta riconoscibile e il recovery lo adotta per
    ref), ``time_in_force=FILL_OR_KILL`` in live (il FOK vero lo esegue Betfair),
    ``mode`` derivato SOLO dal trade. Ritorna l'id di coda, ``ENQUEUE_UNKNOWN``
    se l'esito live è ignoto (riserva in attesa, MAI place REST), None se
    l'enqueue non è mai avvenuto (il chiamante ripiega sul legacy).
    """
    mode = str(mode)
    if mode not in ("paper", "live"):  # INVARIANTE SUPREMO
        logger.error("[safe.exec] enqueue rifiutato: mode %r fuori whitelist", mode)
        return None
    ref = str(client_ref)
    pre = dict(base_meta or {})
    pre.update({"phase": "flumine_wait", "flumine_client_ref": ref,
                "flumine_enqueued_at": now.isoformat()})
    try:
        db.update_trade(trade_id, meta=pre)  # marker PRIMA dell'enqueue
    except Exception as ex:  # noqa: BLE001 — nessun enqueue avvenuto: legacy sicuro
        logger.warning("[safe.exec] pre-mark flumine KO (trade %s): %s", trade_id, str(ex)[:160])
        return None
    payload: dict[str, Any] = {
        "client_ref": ref,
        "action": "place",
        "mode": mode,
        "market_id": str(market_id),
        "selection_id": int(selection_id),
        "side": str(side),
        "order_type": "LIMIT",
        "price": float(price),
        "size": float(size),
        "persistence": "LAPSE",
        "params": {"source": "safe", "trade_id": int(trade_id)},
    }
    if mode == "live":
        payload["time_in_force"] = "FILL_OR_KILL"
    try:
        rid = db.enqueue_live_order(payload)
        if not rid:
            raise RuntimeError("enqueue rifiutato (rid nullo)")
        meta = dict(pre)
        meta["flumine_request_id"] = int(rid)
        db.update_trade(trade_id, meta=meta)
        db.log("flumine_enqueue", {"trade_id": trade_id, "event_id": event_id,
                                   "request_id": int(rid), "price": price,
                                   "size": size, "mode": mode})
        return int(rid)
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.exec] enqueue flumine KO (trade %s): %s", trade_id, str(ex)[:160])
        lookup_failed = False
        try:
            req = db.get_live_order_request_by_ref(ref)
        except Exception:  # noqa: BLE001
            req, lookup_failed = None, True
        if req is not None and req.get("id") is not None:
            meta = dict(pre)
            meta["flumine_request_id"] = int(req["id"])
            try:
                db.update_trade(trade_id, meta=meta)
            except Exception:  # noqa: BLE001 — recovery al prossimo poll (client_ref)
                pass
            return int(req["id"])
        if mode == "live" and lookup_failed:
            logger.warning("[safe.exec] enqueue LIVE esito IGNOTO (trade %s): riserva "
                           "in attesa di recovery, NESSUN place REST", trade_id)
            return ENQUEUE_UNKNOWN
        try:
            db.update_trade(trade_id, meta=dict(base_meta or {}))
        except Exception:  # noqa: BLE001
            pass
        return None


# ---------------------------------------------------------------------------
# CHIUSURA A MERCATO (green-up totale / cash-out parziale)
# ---------------------------------------------------------------------------
def exposures(trade: dict[str, Any]) -> "tuple[float, float]":
    """(profit_se_la_selezione_VINCE, profit_se_PERDE) della gamba, LORDI.

    LAY  size@L → vince: -size*(L-1)  | perde: +size
    BACK size@B → vince: +size*(B-1)  | perde: -size
    """
    size = float(trade.get("size") or 0.0)
    price = float(trade.get("price") or 0.0)
    if str(trade.get("side") or "lay").lower() == "back":
        return (size * (price - 1.0), -size)
    return (-size * (price - 1.0), size)


# stati di una gamba di chiusura il cui fill è CERTO (contano nell'hedge)
_FILLED = ("open", "won", "lost", "void")
# sotto questo residuo (in stake dell'apertura) la posizione è chiusa del tutto
HEDGE_EPS = 0.01


def net_exposures(trade: dict[str, Any],
                  closings: Optional[list[dict[str, Any]]]) -> "tuple[float, float]":
    """Esposizioni NETTE (win, lose) dell'apertura più le chiusure FILLATE."""
    win, lose = exposures(trade)
    for c in closings or []:
        if str(c.get("status")) in _FILLED:
            w, lo = exposures(c)
            win += w
            lose += lo
    return win, lose


def hedge_state(trade: dict[str, Any],
                closings: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    """Stato dell'hedge di una gamba dato l'elenco delle sue chiusure. PURO.

    ``hedged_size`` è in STAKE DELL'APERTURA: una chiusura di size s al prezzo
    p neutralizza s·p/p₀ di apertura (è la stessa formula del green-up: la
    size che azzera W−L a p è S·p₀/p). Solo le chiusure con fill CERTO
    contano; una chiusura 'pending' BLOCCA (``blocked``) ogni nuovo cash-out
    perché l'esposizione residua non è conoscibile. ``complete`` = residuo
    sotto ``HEDGE_EPS``: solo allora l'apertura può passare a 'hedged'.
    """
    size = float(trade.get("size") or 0.0)
    price = float(trade.get("price") or 0.0)
    filled = [c for c in closings or [] if str(c.get("status")) in _FILLED]
    pending = [c for c in closings or [] if str(c.get("status")) == "pending"]
    hedged = 0.0
    for c in filled:
        if price > 1.0:
            hedged += float(c.get("size") or 0.0) * float(c.get("price") or 0.0) / price
    hedged = round(hedged, 2)
    residual = round(max(size - hedged, 0.0), 2)
    win, lose = net_exposures(trade, filled)
    return {
        "hedged_size": hedged,
        "residual_size": residual,
        "if_win": round(win, 2),
        "if_lose": round(lose, 2),
        "locked_pnl": round(min(win, lose), 2) if filled else None,
        "filled_ids": [c.get("id") for c in filled],
        "pending_ids": [c.get("id") for c in pending],
        "blocked": bool(pending),
        "complete": bool(filled) and residual < HEDGE_EPS,
    }


def apply_hedge_state(db, trade: dict[str, Any], closings: list[dict[str, Any]],
                      now: datetime) -> dict[str, Any]:
    """Scrive sull'apertura lo stato dell'hedge (meta) e la porta a 'hedged'
    SOLO quando il residuo è nullo e nessuna chiusura è in sospeso.
    Idempotente: nessuna scrittura se non cambia nulla."""
    st = hedge_state(trade, closings)
    meta = dict(trade.get("meta") or {})
    last_id = (st["pending_ids"] or st["filled_ids"] or [meta.get("closing_trade_id")])[-1]
    upd = {
        "hedged_size": st["hedged_size"],
        "residual_size": st["residual_size"],
        "locked_pnl": st["locked_pnl"],
        "hedge_pending_ids": list(st["pending_ids"]),
        "closing_ids": list(st["filled_ids"]),
        "closing_trade_id": last_id,
        "closing_status": "pending" if st["blocked"] else ("open" if st["filled_ids"] else None),
    }
    status = str(trade.get("status") or "open")
    new_status = "hedged" if (status == "open" and st["complete"] and not st["blocked"]) else status
    if new_status == status and all(meta.get(k) == v for k, v in upd.items()):
        return st
    meta.update(upd)
    meta["hedge_synced_at"] = now.isoformat()
    try:
        if new_status != status:
            db.update_trade(trade["id"], status=new_status, meta=meta)
        else:
            db.update_trade(trade["id"], meta=meta)
    except Exception as ex:  # noqa: BLE001
        logger.critical("[safe.exec] sync hedge FALLITO (trade %s): %s",
                        trade.get("id"), str(ex)[:160])
        return st
    trade["meta"] = meta
    trade["status"] = new_status
    return st


def has_closing_marker(trade: dict[str, Any]) -> bool:
    """L'apertura ha (o attende) almeno una gamba di chiusura → si regola in coppia."""
    meta = trade.get("meta") or {}
    return bool(meta.get("closing_trade_id") or meta.get("hedge_pending_ids")
                or meta.get("closing_ids"))


def known_closings(db, trade: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """Chiusure NON in errore dell'apertura (None = lettura fallita: fail-closed)."""
    fn = getattr(db, "closing_trades_for", None)
    if not callable(fn):
        # senza accessor si ripiega sui marker in meta: mai ignorare un pending
        pend = (trade.get("meta") or {}).get("hedge_pending_ids") or []
        return [{"id": i, "status": "pending", "size": 0.0, "price": 0.0} for i in pend]
    try:
        return [c for c in fn([int(trade["id"])]) or []
                if str(c.get("status")) != "error"]
    except Exception as ex:  # noqa: BLE001
        logger.warning("[safe.exec] lettura chiusure KO (trade %s): %s",
                       trade.get("id"), str(ex)[:160])
        return None


def close_plan(trade: dict[str, Any], *, best_back: Optional[float],
               best_lay: Optional[float], amount: Optional[float] = None,
               fraction: float = 1.0,
               closings: Optional[list[dict[str, Any]]] = None) -> GreenupPlan:
    """Ordine UNICO che chiude (tutta o in parte) la gamba, al best opposto.

    Riusa ``compute_greenup`` (matematica pura e testata del runner live). Il
    kwarg ``amount`` (stake assoluto) è passato SOLO se disponibile: su una
    versione più vecchia della libreria si ripiega su ``fraction`` (guardia
    TypeError) invece di rompere il cash-out. ``closings`` = chiusure già
    fillate: il piano lavora sull'esposizione RESIDUA (cash-out ripetuti).
    """
    win, lose = net_exposures(trade, closings)
    kw = dict(matched_if_win=win, matched_if_lose=lose,
              best_back_price=best_back, best_lay_price=best_lay)
    if amount is not None:
        try:
            return compute_greenup(**kw, amount=float(amount), fraction=_frac(fraction))
        except TypeError:  # libreria senza 'amount': degrada alla frazione
            logger.warning("[safe.exec] compute_greenup senza 'amount': uso fraction=%s", fraction)
    return compute_greenup(**kw, fraction=_frac(fraction))


def _frac(fraction: Optional[float]) -> float:
    try:
        f = float(fraction) if fraction is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, f))


def locked_pnl(trade: dict[str, Any], plan: GreenupPlan) -> float:
    """P&L BLOCCATO (lordo) dopo l'hedge: identico su ogni esito se f=1."""
    return round(min(float(plan.expected_if_win), float(plan.expected_if_lose)), 2)


def close_trade(*, db, market, trade: dict[str, Any], prices: dict[str, Any],
                amount: Optional[float] = None, fraction: float = 1.0,
                mode: Optional[str] = None, now: datetime,
                params: Optional[dict[str, Any]] = None,
                origin: str = "manual", table_prefix: str = "safe",
                extra_row: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Chiude a mercato la gamba ``trade`` piazzando l'ordine opposto.

    ``prices``: {'back','back_size','lay','lay_size','lay_ladder'?} della STESSA
    selezione. ``mode`` default = mode del trade (mai promuovere un paper a live).
    ``extra_row``: colonne extra della riga di chiusura (es. ``phase`` per Omega).
    Ritorna il dict di esito da scrivere nel ``result`` della richiesta.
    """
    params = params or {}
    mode = str(mode or trade.get("mode") or "paper")
    if mode not in ("paper", "live"):
        return {"error": f"mode_non_valido:{mode}"}
    if str(trade.get("status")) not in ("open",):
        return {"error": f"trade_non_aperto:{trade.get('status')}"}

    # chiusure già esistenti: una 'pending' (fill flumine in arrivo o esito
    # REST ignoto in riconciliazione) BLOCCA — un secondo hedge sull'intera
    # gamba invertirebbe la posizione. Le fillate riducono il residuo.
    legs = known_closings(db, trade)
    if legs is None:
        return {"error": "lettura_chiusure_fallita"}
    st = hedge_state(trade, legs)
    if st["blocked"]:
        return {"error": "chiusura_in_corso", "pending_closing_ids": st["pending_ids"]}
    if st["complete"]:
        return {"error": "posizione_gia_chiusa", "hedged_size": st["hedged_size"]}

    best_back = _num(prices.get("back"))
    best_lay = _num(prices.get("lay"))
    plan = close_plan(trade, best_back=best_back, best_lay=best_lay,
                      amount=amount, fraction=fraction, closings=legs)
    if not plan.actionable:
        return {"error": "niente_da_chiudere", "note": plan.note}

    side = str(plan.side)
    best_size = _num(prices.get(f"{side}_size"))
    lock = locked_pnl(trade, plan)

    reserve: dict[str, Any] = {
        "event_id": trade.get("event_id"),
        "event_name": trade.get("event_name"),
        "market_id": trade.get("market_id"),
        "selection_id": trade.get("selection_id"),
        "side": side,
        "mode": mode,
        "origin": origin,
        "price": plan.price,
        "size": plan.size,
        "liability": liability_of(side, plan.size, plan.price),
        "commission": trade.get("commission"),
        "status": "pending",
        "pnl": 0.0,
        "closes_trade_id": trade.get("id"),
        "meta": {"phase": "reserved", "cashout": True,
                 "closes_trade_id": trade.get("id"),
                 "plan_note": plan.note,
                 "expected_if_win": plan.expected_if_win,
                 "expected_if_lose": plan.expected_if_lose},
    }
    reserve.update(extra_row or {})
    try:
        closing_id = db.insert_trade(reserve)
    except Exception as ex:  # noqa: BLE001
        return {"error": "riserva_chiusura_fallita", "detail": str(ex)[:160]}
    if not closing_id:
        return {"error": "riserva_chiusura_senza_id"}

    out = place(
        db=db, market=market, mode=mode, event_id=str(trade.get("event_id") or ""),
        market_id=str(trade.get("market_id") or ""),
        selection_id=int(trade.get("selection_id") or 0), side=side,
        price=plan.price, size=plan.size, best_size=best_size,
        ladder=prices.get(f"{side}_ladder") or (),
        client_ref=f"{table_prefix}-t{closing_id}", trade_id=int(closing_id),
        meta={"cashout": True, "closes_trade_id": trade.get("id")},
        now=now, params=params,
    )
    if out.status == "error":
        try:
            db.update_trade(closing_id, status="error",
                            meta={"cashout": True, "reason": out.fill_note,
                                  "closes_trade_id": trade.get("id")})
        except Exception:  # noqa: BLE001
            pass
        _log(db, "cashout_error", {"trade_id": trade.get("id"),
                                   "closing_trade_id": closing_id,
                                   "reason": out.fill_note})
        return {"error": "chiusura_non_eseguita", "detail": out.fill_note,
                "closing_trade_id": closing_id}

    closing_row = dict(reserve)
    closing_row["id"] = closing_id
    if out.status == "open":
        closing_row.update({"status": "open", "price": out.price, "size": out.size})
        try:
            db.update_trade(closing_id, status="open", price=out.price, size=out.size,
                            liability=liability_of(side, out.size, out.price or 0.0),
                            bet_id=out.bet_id,
                            meta={"cashout": True, "closes_trade_id": trade.get("id"),
                                  "fill": out.fill_note, "plan_note": plan.note})
        except Exception as ex:  # noqa: BLE001 — ordine eseguito, riga non confermata
            logger.critical("[safe.exec] conferma chiusura FALLITA (trade %s, mode %s): %s",
                            closing_id, mode, str(ex)[:160])
    # 'pending' (fill flumine in arrivo / esito REST ignoto): la riga resta
    # 'pending' con i suoi marker; l'apertura registra la chiusura IN SOSPESO
    # (blocca un secondo cash-out) e passerà a 'hedged' SOLO a fill confermato.

    # stato dell'hedge dall'insieme REALE delle gambe fillate: l'apertura resta
    # 'open' con hedged_size/locked_pnl finché c'è un residuo (cash-out
    # parziale, size cappata, fill in sospeso); 'hedged' solo a residuo nullo.
    trade["meta"] = {**(trade.get("meta") or {}), "cashout_at": now.isoformat()}
    st = apply_hedge_state(db, trade, [*legs, closing_row], now)
    _log(db, "cashout", {"trade_id": trade.get("id"), "closing_trade_id": closing_id,
                         "side": side, "price": out.price, "size": out.size,
                         "locked_pnl": st["locked_pnl"], "planned_lock": lock,
                         "hedged_size": st["hedged_size"],
                         "residual_size": st["residual_size"],
                         "mode": mode, "status": out.status})
    return {"ok": True, "trade_id": trade.get("id"), "closing_trade_id": closing_id,
            "side": side, "price": out.price, "size": out.size,
            "locked_pnl": st["locked_pnl"] if st["locked_pnl"] is not None else lock,
            "pending_fill": out.status == "pending",
            "hedged": trade.get("status") == "hedged",
            "hedged_size": st["hedged_size"], "residual_size": st["residual_size"],
            "note": plan.note}


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _log(db, kind: str, payload: dict[str, Any]) -> None:
    try:
        db.log(kind, payload)
    except Exception:  # noqa: BLE001 — il log non ferma mai il trading
        pass


# ---------------------------------------------------------------------------
# SETTLEMENT DELLA COPPIA (apertura 'hedged' + chiusura)
# ---------------------------------------------------------------------------
def gross_pnl(trade: dict[str, Any], runner_won: bool) -> float:
    """P&L LORDO (senza commissione) della gamba dato l'esito della selezione."""
    win, lose = exposures(trade)
    return win if runner_won else lose


def settle_group(trade: dict[str, Any], closings: list[dict[str, Any]],
                 runner_won: bool, commission: float) -> "tuple[float, list[float]]":
    """(pnl_apertura, [pnl_chiusure]) NETTI per una posizione chiusa a mercato
    con UNA O PIÙ gambe di chiusura (cash-out parziali ripetuti).

    Betfair applica la commissione sulle VINCITE NETTE DEL MERCATO, non gamba
    per gamba: si netta PRIMA l'insieme delle gambe, la commissione si applica
    SOLO se il netto è positivo e viene poi ripartita in proporzione alle gambe
    in utile (ripartizione di sola VISUALIZZAZIONE: la somma resta esatta).
    """
    legs = [trade] + list(closings or [])
    gross = [gross_pnl(t, runner_won) for t in legs]
    net = sum(gross)
    try:
        c = max(0.0, float(commission))
    except (TypeError, ValueError):
        c = 0.0
    comm = net * c if net > 0 else 0.0
    total = round(net - comm, 2)
    pos_sum = sum(g for g in gross if g > 0)
    if comm > 0 and pos_sum > 0:
        pnls = [round(g - comm * (max(g, 0.0) / pos_sum), 2) for g in gross]
    else:
        pnls = [round(g, 2) for g in gross]
    # l'arrotondamento non deve mai creare/distruggere centesimi: il residuo
    # va sull'ULTIMA gamba, così sum(pnls) == total esattamente.
    drift = round(total - sum(pnls), 2)
    if drift and pnls:
        pnls[-1] = round(pnls[-1] + drift, 2)
    return pnls[0], pnls[1:]


def settle_pair(trade: dict[str, Any], closing: Optional[dict[str, Any]],
                runner_won: bool, commission: float) -> "tuple[float, float]":
    """(pnl_apertura, pnl_chiusura) NETTI — caso a due gambe di ``settle_group``."""
    pnl_open, closes = settle_group(trade, [closing] if closing else [],
                                    runner_won, commission)
    return pnl_open, (closes[0] if closes else 0.0)


_SETTLED = ("won", "lost", "void")


def settle_row(db, tr: dict[str, Any], status: str, pnl: float, now: datetime) -> None:
    db.update_trade(tr["id"], status=status, pnl=round(float(pnl), 2),
                    settled_at=now.isoformat())
    tr["status"] = status
    tr["pnl"] = round(float(pnl), 2)
    _log(db, "settle", {"trade_id": tr.get("id"), "event_id": tr.get("event_id"),
                        "status": status, "pnl": round(float(pnl), 2),
                        "closes_trade_id": tr.get("closes_trade_id"),
                        "selection": tr.get("selection_name") or tr.get("runner_name")})


def settle_position(*, db, trade: dict[str, Any], closings: list[dict[str, Any]],
                    snap: Any, commission: float, now: datetime) -> bool:
    """Regola un'apertura CON TUTTE le sue chiusure (o da sola se non ne ha),
    a mercato ``snap`` CHIUSO. Ritorna True se l'apertura è stata regolata.

    Money-critical:
      • una chiusura 'pending' rinvia tutto (mai un P&L su un fill incerto);
      • le gambe si NETTANO insieme (commissione sul netto di mercato);
      • RIPRENDIBILE: le chiusure si scrivono PRIMA dell'apertura e le gambe
        già regolate (crash a metà del ciclo precedente) restano nel netto ma
        non vengono riscritte; l'apertura è l'ultima scrittura, quindi finché
        è viva il ciclo successivo ripete il calcolo identico.
    """
    legs = [c for c in closings or [] if str(c.get("status")) != "error"]
    if any(str(c.get("status")) == "pending" for c in legs):
        _log(db, "settle_wait", {"trade_id": trade.get("id"),
                                 "reason": "chiusura_non_ancora_confermata",
                                 "pending_closing_ids": [c.get("id") for c in legs
                                                         if str(c.get("status")) == "pending"]})
        return False
    if snap.voided or snap.winner_selection_id is None:
        for c in legs:
            if str(c.get("status")) not in _SETTLED:
                settle_row(db, c, "void", 0.0, now)
        settle_row(db, trade, "void", 0.0, now)
        return True
    won = int(snap.winner_selection_id) == int(trade["selection_id"])
    if legs:
        pnl_open, pnl_closes = settle_group(trade, legs, won, commission)
        for c, p in zip(legs, pnl_closes):
            if str(c.get("status")) in _SETTLED:
                continue  # già regolata da un ciclo interrotto: resta nel netto
            settle_row(db, c, "won" if p >= 0 else "lost", p, now)
        settle_row(db, trade, "won" if pnl_open >= 0 else "lost", pnl_open, now)
        return True
    status, pnl = E.settle_pnl(
        our_selection_id=int(trade["selection_id"]),
        winner_selection_id=snap.winner_selection_id,
        size=float(trade["size"]), price=float(trade["price"]),
        commission=commission, voided=snap.voided,
        side=str(trade.get("side") or "lay"),
    )
    settle_row(db, trade, status, pnl, now)
    return True


def runner_won_from_parent(parent: dict[str, Any]) -> Optional[bool]:
    """Esito della selezione ricavato da un'apertura GIÀ regolata (None = void/ignoto)."""
    status = str(parent.get("status") or "")
    is_back = str(parent.get("side") or "lay").lower() == "back"
    if status == "won":
        return is_back
    if status == "lost":
        return not is_back
    return None


def settle_orphan_closing(*, db, closing: dict[str, Any], parent: dict[str, Any],
                          commission: float, now: datetime) -> bool:
    """Gamba di chiusura rimasta viva con l'apertura GIÀ regolata (ciclo
    interrotto tra le due scritture, o dati storici): si regola con l'esito
    della selezione dedotto dall'apertura — mai lasciarla orfana."""
    status = str(parent.get("status") or "")
    if status == "void":
        settle_row(db, closing, "void", 0.0, now)
        return True
    won = runner_won_from_parent(parent)
    if won is None:
        return False
    g = gross_pnl(closing, won)
    try:
        c = max(0.0, float(commission))
    except (TypeError, ValueError):
        c = 0.0
    pnl = round(g * (1.0 - c), 2) if g > 0 else round(g, 2)
    settle_row(db, closing, "won" if pnl >= 0 else "lost", pnl, now)
    _log(db, "settle_orphan_closing", {"trade_id": closing.get("id"),
                                       "parent_id": parent.get("id"), "pnl": pnl})
    return True
