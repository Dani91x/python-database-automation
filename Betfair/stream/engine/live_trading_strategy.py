"""LiveTradingStrategy — strategia flumine ADVISORY (NON piazza ordini in automatico).

Per chi: gira DENTRO il processo del runner (Betfair/stream/runner.py), aggiunta al
framework SOLO quando ``LIVE_ORDER_MODE`` ∈ {PAPER, LIVE}. Convive con la
``MarketRecorderStrategy`` sugli stessi mercati senza interferire.

Cosa fa, e SOLO questo:
  * ``process_market_book`` → NO-OP. Nessun ordine viene MAI generato qui: gli ordini
    arrivano esclusivamente dalla coda comandi (``betfair_live_order_worker``), su
    richiesta esplicita del frontend. Questa strategia non decide nulla.
  * ``process_orders`` → SPECCHIO write-on-change. Ad ogni cambio degli ordini della
    strategia riflette nel DB:
      - ``betfair_live_orders``  : un record per ordine (bet_id, size_matched,
        average_price_matched, status flumine, size_remaining/cancelled/lapsed/voided);
      - ``betfair_live_positions``: un record per selezione TOCCATA, con le esposizioni
        prese SEMPRE da ``market.blotter.get_exposures(self, lookup)`` e
        ``selection_exposure`` (MAI ricalcolate a mano — MONEY-CRITICAL).

Il fill (size_matched / average_price_matched) arriva ASINCRONO: in LIVE dal
``order_stream`` Betfair, in PAPER dalla ``SimulatedExecution`` di flumine. In entrambi
i casi flumine richiama ``process_orders`` ed è qui che lo specchio si aggiorna.

Testabile a unità: Market, blotter, ordini e le scritture DB sono mockabili; nessuna
rete, nessun login, nessun ordine reale.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flumine import BaseStrategy

logger = logging.getLogger(__name__)

# Stati terminali flumine: un ordine in questi stati non muterà più → la sua firma
# write-on-change può essere rimossa dalla cache (evita crescita illimitata del dict).
_TERMINAL_ORDER_STATUSES = frozenset(
    {"EXECUTION_COMPLETE", "EXPIRED", "LAPSED", "VIOLATION"}
)


# ---------------------------------------------------------------------------
# Accesso DB lazy: evita di importare supabase/config all'import del modulo (e
# rende le scritture monkeypatchabili nei test senza toccare la rete).
# ---------------------------------------------------------------------------
def _db() -> Any:
    from .. import db  # import ritardato: supabase non è richiesto per importare la strategia

    return db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _val(obj: Any, attr: str) -> Any:
    """getattr difensivo: alcune property dell'ordine possono sollevare in stati di confine."""
    try:
        return getattr(obj, attr)
    except Exception:  # noqa: BLE001
        return None


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _f0(v: Any) -> float:
    """Come ``_f`` ma con default 0.0 (colonne NOT NULL DEFAULT 0 dello specchio)."""
    out = _f(v)
    return out if out is not None else 0.0


def _int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _enum_name(v: Any) -> Optional[str]:
    """Nome di un Enum flumine (OrderStatus/OrderTypes) → es. 'EXECUTABLE', 'LIMIT'."""
    if v is None:
        return None
    name = getattr(v, "name", None)
    return name or str(v)


def _dt_iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        return v.isoformat()
    except Exception:  # noqa: BLE001
        return str(v)


def _request_id_from_ref(ref: Optional[str]) -> Optional[int]:
    """Estrae l'id richiesta dal customer_order_ref deterministico ``awlq<id>``."""
    if not ref or not isinstance(ref, str) or not ref.startswith("awlq"):
        return None
    return _int(ref[4:])


def _client_order_ref(order: Any) -> Optional[str]:
    """Il NOSTRO ref deterministico ``awlq<id>`` salvato da live_order_build in
    ``order.context``/``order.notes``.

    NB: l'attributo flumine ``order.customer_order_ref`` è invece ``name_hash+sep+id`` —
    NON il nostro ref — quindi va letto da context/notes per ricostruire request_id↔ordine.
    Fallback finale all'attributo per compatibilità con ordini/mock che lo espongono diretto.
    """
    for src in ("context", "notes"):
        d = _val(order, src)
        if isinstance(d, dict):
            v = d.get("customer_order_ref")
            if v:
                return v
    return _val(order, "customer_order_ref")


class LiveTradingStrategy(BaseStrategy):
    """Strategia advisory: specchia ordini e posizioni nel DB, NON fa auto-trading."""

    def __init__(self, *args: Any, session: Any = None, mode: str = "paper", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.session = session
        self.mode = (mode or "paper").lower()
        # cache write-on-change: order.id → firma dei campi mutabili già scritti.
        self._last_order_sig: Dict[str, Tuple] = {}

    # ------------------------------------------------------------------
    # NO auto-trading: nessun ordine viene mai generato dai dati di mercato.
    # ------------------------------------------------------------------
    def check_market_book(self, market: Any, market_book: Any) -> bool:  # pragma: no cover - trivial
        # process_market_book non verrà comunque eseguito (è NO-OP), ma manteniamo
        # esplicito che non vogliamo essere risvegliati per logica di trading.
        return False

    def process_market_book(self, market: Any, market_book: Any) -> None:
        """NO-OP: questa strategia non piazza ordini in automatico."""
        return

    # ------------------------------------------------------------------
    # Specchio fill: write-on-change → betfair_live_orders + betfair_live_positions
    # ------------------------------------------------------------------
    def process_orders(self, market: Any, orders: list) -> None:
        """Hook fill di flumine. Riflette nel DB SOLO ciò che è cambiato.

        Best-effort: qualunque errore è loggato ma NON deve mai far cadere il runner.
        """
        if not orders:
            return
        try:
            self._mirror_orders(market, orders)
        except Exception as ex:  # noqa: BLE001 - lo specchio non deve mai propagare
            logger.warning("[live-strategy] specchio ordini KO: %s", str(ex)[:200])

    # ------------------------------------------------------------------
    # Implementazione
    # ------------------------------------------------------------------
    def _mirror_orders(self, market: Any, orders: list) -> None:
        dbm = _db()
        event_id = _val(market, "event_id")
        market_id = _val(market, "market_id")
        dirty_lookups: Dict[Tuple[Any, int, float], Tuple[int, float]] = {}

        for order in orders:
            sig = self._order_signature(order)
            oid = _val(order, "id")
            # write-on-change: salta se nulla è cambiato per questo ordine.
            if oid is not None and self._last_order_sig.get(oid) == sig:
                continue
            row = self._order_row(order, event_id=event_id, market_id=market_id)
            if row is None:
                continue
            dbm.upsert_live_order(row)
            if oid is not None:
                # Cleanup cache: un ordine in stato terminale non muterà più → rimuovi
                # la firma (il dict resta limitato agli ordini ancora vivi, niente crescita
                # illimitata). Altrimenti memorizza la firma per il write-on-change.
                if _enum_name(_val(order, "status")) in _TERMINAL_ORDER_STATUSES:
                    self._last_order_sig.pop(oid, None)
                else:
                    self._last_order_sig[oid] = sig
            # marca la selezione (lookup) per il ricalcolo dell'esposizione.
            sel = _int(_val(order, "selection_id"))
            if sel is not None:
                hcap = _f0(_val(order, "handicap"))
                dirty_lookups[(market_id, sel, hcap)] = (sel, hcap)

        # ricalcolo posizioni SOLO per le selezioni toccate (esposizioni da flumine).
        for (mkt, sel, hcap) in dirty_lookups:
            pos = self._position_row(market, event_id, mkt, sel, hcap)
            if pos is not None:
                dbm.upsert_live_position(pos)

    def _order_signature(self, order: Any) -> Tuple:
        """Campi mutabili che, cambiando, richiedono un nuovo specchio."""
        return (
            _val(order, "bet_id"),
            _enum_name(_val(order, "status")),
            _f0(_val(order, "size_matched")),
            _f0(_val(order, "average_price_matched")),
            _f0(_val(order, "size_remaining")),
            _f0(_val(order, "size_cancelled")),
            _f0(_val(order, "size_lapsed")),
            _f0(_val(order, "size_voided")),
        )

    def _order_row(
        self, order: Any, *, event_id: Any, market_id: Any
    ) -> Optional[Dict[str, Any]]:
        ot = _val(order, "order_type")
        side = _val(order, "side")
        ref = _client_order_ref(order)
        placed_at = None
        responses = _val(order, "responses")
        if responses is not None:
            placed_at = _dt_iso(_val(responses, "date_time_placed"))
        size_matched = _f0(_val(order, "size_matched"))
        matched_at = _dt_iso(_val(order, "date_time_status_update")) if size_matched else None
        return {
            "bet_id": _val(order, "bet_id"),
            "client_order_ref": ref,
            "request_id": _request_id_from_ref(ref),
            "mode": self.mode,
            "event_id": event_id,
            "market_id": _val(order, "market_id") or market_id,
            "selection_id": _int(_val(order, "selection_id")),
            "handicap": _f0(_val(order, "handicap")),
            "side": side.lower() if isinstance(side, str) else side,
            "order_type": _enum_name(_val(ot, "ORDER_TYPE")) if ot is not None else "LIMIT",
            "price": _f(getattr(ot, "price", None)) if ot is not None else None,
            "size": _f(getattr(ot, "size", None)) if ot is not None else None,
            "size_matched": size_matched,
            "size_remaining": _f0(_val(order, "size_remaining")),
            "size_cancelled": _f0(_val(order, "size_cancelled")),
            "size_lapsed": _f0(_val(order, "size_lapsed")),
            "size_voided": _f0(_val(order, "size_voided")),
            "average_price_matched": _f0(_val(order, "average_price_matched")),
            "status": _enum_name(_val(order, "status")),
            "persistence": getattr(ot, "persistence_type", None) if ot is not None else None,
            "placed_at": placed_at,
            "matched_at": matched_at,
        }

    def _position_row(
        self, market: Any, event_id: Any, market_id: Any, selection_id: int, handicap: float
    ) -> Optional[Dict[str, Any]]:
        blotter = _val(market, "blotter")
        if blotter is None:
            return None
        lookup = (market_id, selection_id, handicap)
        # ESPOSIZIONI: sempre da flumine, mai ricalcolate a mano (MONEY-CRITICAL).
        exposures = blotter.get_exposures(self, lookup)
        sel_exposure = blotter.selection_exposure(self, lookup)
        return {
            "mode": self.mode,
            "event_id": event_id,
            "market_id": market_id,
            "selection_id": selection_id,
            "handicap": handicap,
            "matched_if_win": _f0(exposures.get("matched_profit_if_win")),
            "matched_if_lose": _f0(exposures.get("matched_profit_if_lose")),
            "worst_if_win": _f0(exposures.get("worst_possible_profit_on_win")),
            "worst_if_lose": _f0(exposures.get("worst_possible_profit_on_lose")),
            "selection_exposure": _f0(sel_exposure),
            # unmatched: contributi worst-case da flumine (negativi = perdita potenziale).
            "unmatched_back_exposure": _f0(
                exposures.get("worst_potential_unmatched_profit_if_lose")
            ),
            "unmatched_lay_exposure": _f0(
                exposures.get("worst_potential_unmatched_profit_if_win")
            ),
            "net_position": self._net_position(blotter, selection_id, handicap),
        }

    def _net_position(self, blotter: Any, selection_id: int, handicap: float) -> float:
        """Size netta matched (BACK − LAY) sulla selezione. È un'aggregazione di size
        (non un'esposizione): la calcoliamo dagli ordini matched del blotter."""
        net = 0.0
        try:
            sel_orders = blotter.strategy_selection_orders(
                self, selection_id, handicap, matched_only=True
            )
        except Exception:  # noqa: BLE001 - blotter mock/edge: niente net
            return 0.0
        for o in sel_orders or []:
            sm = _f0(_val(o, "size_matched"))
            side = _val(o, "side")
            if isinstance(side, str) and side.upper() == "LAY":
                net -= sm
            else:
                net += sm
        return round(net, 2)
