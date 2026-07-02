"""Place-and-trim (`submin`): macchina a stati per piazzare un ordine di size
SOTTO il minimo di giurisdizione, in modo idempotente e ripristinabile.

Per chi: il `live_order_worker` (azione `place_submin` della coda comandi) chiama
`advance_submin()` ad ogni poll, facendo avanzare UNO step alla volta in base allo
stato REALE dell'ordine sul mercato. Il worker persiste lo `SubminState` (nel
`result`/`params` della riga di coda) così che, dopo un crash o un riavvio del
framework, la sequenza riprenda esattamente da dove era rimasta.

TECNICA (Betfair): non puoi piazzare direttamente un ordine sotto il minimo
(.it BACK €2,00 / LAY €0,50), ma puoi RIDURRE un ordine esistente sotto quel
minimo. Quindi:

  step1 PLACED  - place size = minimo di giurisdizione a una quota NON abbinabile
                  (BACK→1000.0, LAY→1.01), persistenza LAPSE;
  step2 TRIMMED - cancel parziale di `size_reduction = placed_size - target_size`
                  → resta esattamente la `target_size` (sotto-minima);
  step3 REPRICED- replace alla `target_price` reale (la quota a cui vuoi operare);
  DONE          - ordine a riposo a (target_price, target_size).

GUARDIA RISCHIO (money-critical): mentre l'ordine è alla quota NON abbinabile
(fasi INIT/PLACED/TRIMMED) NON dovrebbe MAI abbinarsi. Se `size_matched > 0` in
quella fase → stato `ABORTED` e NESSUN ritento: la sequenza si ferma e va
riconciliata a mano (siamo entrati in mercato in modo non previsto). Alla fase
REPRICED, invece, l'abbinamento alla `target_price` è l'esito DESIDERATO e non
fa scattare l'abort.

Le operazioni flumine (place/cancel/replace) sono dietro l'interfaccia iniettabile
`SubminOps`: il runner inietta `FlumineSubminOps` (che usa `build_order` +
`market.place_order/cancel_order/replace_order` NATIVI); i test iniettano un mock.
Nessuna rete, nessun login: testabile a unità.
"""
from __future__ import annotations

from dataclasses import dataclass, replace as _dc_replace
from enum import Enum
from typing import Any, Optional, Protocol, runtime_checkable

from Betfair.stream.live_order_build import (
    COM_MIN_STAKE,
    IT_BACK_MIN_STAKE,
    IT_LAY_MIN_SIZE,
    JURISDICTION_COM,
    JURISDICTION_IT,
    build_order,
    round_to_tick,
)

# Tolleranza confronti float (size/price già arrotondati a 2 decimali / al tick).
_TOL = 1e-6

# Floor ASSOLUTO della size residua dopo il trim: non si può ridurre a zero/negativo.
# Conservativo; il valore esatto su .it va verificato empiricamente (cert LIVE minimale).
SUBMIN_ABS_MIN_SIZE = 0.01

_VALID_SIDES = ("back", "lay")


# ---------------------------------------------------------------------------
# Stato della macchina
# ---------------------------------------------------------------------------
class SubminStep(str, Enum):
    INIT = "init"
    PLACED = "placed"        # step1: place min @ quota non abbinabile, LAPSE
    TRIMMED = "trimmed"      # step2: cancel size_reduction → resta target
    REPRICED = "repriced"    # step3: replace new_price = quota target
    DONE = "done"
    ABORTED = "aborted"      # guardia rischio: step1 abbinato → STOP, niente ritento


# Fasi in cui l'ordine è alla quota NON abbinabile (un match qui = anomalia → abort).
_UNMATCHABLE_PHASES = (SubminStep.INIT, SubminStep.PLACED, SubminStep.TRIMMED)
# Stati terminali (idempotenti: nessuna ulteriore azione).
_TERMINAL = (SubminStep.DONE, SubminStep.ABORTED)


@dataclass
class SubminState:
    step: SubminStep
    bet_id: Optional[str]
    target_size: float
    target_price: float          # già al tick
    placed_size: float           # = minimo di giurisdizione (€2 .it BACK / €0,50 LAY)
    side: str                    # 'back' | 'lay'
    note: str = ""

    @property
    def size_reduction(self) -> float:
        """Quantità da cancellare allo step2 per arrivare alla target_size."""
        return round(self.placed_size - self.target_size, 2)


# ---------------------------------------------------------------------------
# Interfaccia iniettabile sulle operazioni flumine (per testabilità con MOCK)
# ---------------------------------------------------------------------------
@runtime_checkable
class SubminOps(Protocol):
    """Astrazione delle 3 operazioni flumine usate dalla macchina a stati.

    Il default di produzione è `FlumineSubminOps`; i test iniettano un mock che
    registra le chiamate senza toccare la rete.
    """

    def place(
        self,
        market: Any,
        *,
        side: str,
        price: float,
        size: float,
        customer_order_ref: str,
    ) -> Any:
        """Piazza l'ordine iniziale (size minima @ quota non abbinabile). Ritorna
        il BetfairOrder flumine (il cui `bet_id` arriverà async)."""
        ...

    def cancel(self, market: Any, order: Any, size_reduction: float) -> None:
        """Cancel PARZIALE di `size_reduction` (riduce l'ordine sotto il minimo)."""
        ...

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        """Sposta l'ordine a riposo alla `new_price` (la quota target reale)."""
        ...


@dataclass
class FlumineSubminOps:
    """Implementazione di produzione di `SubminOps` su un Market flumine NATIVO.

    Legata a (selection_id, handicap, jurisdiction, strategy) — costanti per l'intera
    sequenza submin — così che `advance_submin` non debba trasportarli nello stato.
    ``strategy`` è l'istanza LiveTradingStrategy registrata: il Trade è creato sotto di
    essa così che lo specchio (process_orders) intercetti anche gli ordini submin.

    ``max_stake`` (cap effettivo per-ordine) e ``customer_strategy_ref`` (customerStrategyRef
    NATIVO inviato a Betfair) replicano nel ramo submin le stesse barriere del place normale:
    il cap è l'ultima guardia money-critical (NON deve essere bypassato con None) e lo
    strategy-ref instrada correttamente l'ordine lato Exchange.
    """

    selection_id: int
    handicap: float
    jurisdiction: str
    strategy: Any
    max_stake: Optional[float] = None
    customer_strategy_ref: Optional[str] = None

    def place(
        self,
        market: Any,
        *,
        side: str,
        price: float,
        size: float,
        customer_order_ref: str,
    ) -> Any:
        built = build_order(
            market,
            strategy=self.strategy,
            selection_id=self.selection_id,
            handicap=self.handicap,
            side=side,
            order_type="LIMIT",
            price=price,
            size=size,
            liability=None,
            persistence="LAPSE",          # step1 deve decadere se non gestito
            time_in_force=None,
            min_fill_size=None,
            jurisdiction=self.jurisdiction,
            max_stake=self.max_stake,     # cap effettivo: NON bypassare la guardia
            customer_order_ref=customer_order_ref,
        )
        # Fix CRITICAL-1: place/cancel/replace flumine ritornano **False** se un trading
        # control rifiuta (ordine VIOLATION, MAI inviato a Betfair). Ignorarlo lascerebbe la
        # sequenza submin ad attendere un ordine INESISTENTE ('processing' per sempre).
        if self.customer_strategy_ref is not None:
            ok = market.place_order(built.order, customer_strategy_ref=self.customer_strategy_ref)
        else:
            ok = market.place_order(built.order)
        if ok is False:
            raise ValueError(f"submin place RIFIUTATO — {_violation_reason(built.order)}")
        return built.order

    def cancel(self, market: Any, order: Any, size_reduction: float) -> None:
        if market.cancel_order(order, size_reduction) is False:
            raise ValueError(f"submin cancel RIFIUTATO — {_violation_reason(order)}")

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        # CODE-MED-1: per un LAY ri-valida il cap PRIMA del replace. Lo step3 REPRICED sposta
        # l'ordine dalla quota NON abbinabile (1.01) alla target_price reale: la liability
        # (= size*(price-1)) CRESCE col prezzo, quindi un reprice al rialzo potrebbe sfondare
        # il cap money-critical che il place del minimo rispettava. Solleva senza piazzare.
        _guard_replace_cap_lay(order, new_price, self.max_stake)
        if market.replace_order(order, new_price) is False:
            raise ValueError(f"submin replace RIFIUTATO — {_violation_reason(order)}")


def _violation_reason(order: Any) -> str:
    """Motivo del rifiuto dal trading control (violation_msg), con fallback leggibile."""
    try:
        msg = getattr(order, "violation_msg", None)
    except Exception:  # noqa: BLE001 - property di confine
        msg = None
    return str(msg) if msg else "rifiutato dai trading control flumine (violation)"


# ---------------------------------------------------------------------------
# Helper su size minima di piazzamento per giurisdizione
# ---------------------------------------------------------------------------
def place_min_size(jurisdiction: str, side: str) -> float:
    """Size minima LEGALE per PIAZZARE un ordine (lo step1 usa questa)."""
    j = (jurisdiction or "").lower()
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    if j == JURISDICTION_IT:
        return IT_BACK_MIN_STAKE if s == "back" else IT_LAY_MIN_SIZE
    if j == JURISDICTION_COM:
        return COM_MIN_STAKE
    raise ValueError(f"giurisdizione sconosciuta: {jurisdiction!r}")


def initial_place_price(side: str) -> float:
    """Quota NON abbinabile per lo step1: BACK→1000.0, LAY→1.01.

    A questi estremi della scala un match è quasi impossibile; va comunque
    verificato empiricamente (la guardia rischio resta l'ultima barriera).
    """
    s = (side or "").lower()
    if s == "back":
        return round_to_tick(1000.0)
    if s == "lay":
        return round_to_tick(1.01)
    raise ValueError(f"side non valido: {side!r} (atteso back|lay)")


# ---------------------------------------------------------------------------
# Costruttore di stato (valida e calcola placed_size)
# ---------------------------------------------------------------------------
def start_submin(
    *,
    side: str,
    target_price: float,
    target_size: float,
    jurisdiction: str,
    note: str = "",
) -> SubminState:
    """Crea uno `SubminState` iniziale (step=INIT) validando i vincoli.

    Solleva `ValueError` se: side non valido; target_size ≤ floor assoluto;
    target_size ≥ minimo di piazzamento (in tal caso usa un place NORMALE, non
    serve il submin). `placed_size` = minimo di giurisdizione per quel side.
    """
    s = (side or "").lower()
    if s not in _VALID_SIDES:
        raise ValueError(f"side non valido: {side!r} (atteso back|lay)")
    if target_size is None or target_size <= SUBMIN_ABS_MIN_SIZE - _TOL:
        raise ValueError(
            f"target_size {target_size!r} ≤ floor assoluto €{SUBMIN_ABS_MIN_SIZE:.2f}"
        )
    placed = place_min_size(jurisdiction, s)
    tsize = round(float(target_size), 2)
    if tsize >= placed - _TOL:
        raise ValueError(
            f"target_size €{tsize:.2f} ≥ minimo di piazzamento €{placed:.2f}: "
            "usa un place normale (submin non necessario)"
        )
    tick = round_to_tick(target_price)
    return SubminState(
        step=SubminStep.INIT,
        bet_id=None,
        target_size=tsize,
        target_price=tick,
        placed_size=round(float(placed), 2),
        side=s,
        note=note or "submin init",
    )


# ---------------------------------------------------------------------------
# Lettura difensiva dello stato dell'ordine (mock-friendly)
# ---------------------------------------------------------------------------
def _size_matched(order: Any) -> float:
    return float(getattr(order, "size_matched", 0.0) or 0.0)


def _size_remaining(order: Any) -> Optional[float]:
    val = getattr(order, "size_remaining", None)
    return None if val is None else float(val)


def _bet_id(order: Any) -> Optional[str]:
    return getattr(order, "bet_id", None)


def _status_name(order: Any) -> Optional[str]:
    st = getattr(order, "status", None)
    if st is None:
        return None
    # OrderStatus.EXECUTABLE -> name "EXECUTABLE"; stringa "Executable"/"EXECUTABLE" -> str()
    name = getattr(st, "name", None)
    return (name or str(st)).upper()


def _is_executable(order: Any) -> bool:
    return _status_name(order) == "EXECUTABLE"


def _order_price(order: Any) -> Optional[float]:
    ot = getattr(order, "order_type", None)
    price = getattr(ot, "price", None)
    return None if price is None else float(price)


def _order_side(order: Any) -> Optional[str]:
    side = getattr(order, "side", None)
    return None if side is None else str(side).lower()


def _order_size(order: Any) -> Optional[float]:
    """Size NOMINALE dell'ordine (order_type.size), fallback alla size residua. Difensivo."""
    ot = getattr(order, "order_type", None)
    size = getattr(ot, "size", None)
    if size is None:
        size = _size_remaining(order)
    return None if size is None else float(size)


def _guard_replace_cap_lay(
    order: Any, new_price: float, max_stake: Optional[float]
) -> None:
    """Ri-valida il cap money-critical prima di un replace LAY (CODE-MED-1).

    Per un LAY la liability = size*(price-1) CRESCE col prezzo: un replace verso quote più
    alte può sfondare il cap che il place iniziale rispettava. Se l'ordine è LAY e la nuova
    liability supera ``max_stake`` (cap effettivo) solleva ``ValueError`` (nessun replace).
    Difensivo: se cap/side/size non sono determinabili NON blocca (no falsi positivi su mock).
    """
    if max_stake is None:
        return
    if _order_side(order) != "lay":
        return
    size = _order_size(order)
    if size is None:
        return
    new_liab = round(float(size) * (float(new_price) - 1.0), 2)
    if new_liab > float(max_stake) + _TOL:
        raise ValueError(
            f"replace LAY: liability €{new_liab:.2f} a quota {new_price} "
            f"oltre cap €{float(max_stake):.2f}"
        )


# ---------------------------------------------------------------------------
# Macchina a stati
# ---------------------------------------------------------------------------
def advance_submin(
    market: Any,
    state: SubminState,
    *,
    order: Any = None,
    jurisdiction: str,
    customer_order_ref: str,
    ops: Optional[SubminOps] = None,
    allow_place: bool = True,
) -> SubminState:
    """Avanza la sequenza submin di UNO step in base allo stato REALE dell'ordine.

    - Guardia rischio: se nelle fasi a quota non abbinabile (INIT/PLACED/TRIMMED)
      l'ordine risulta `size_matched > 0` → `ABORTED` (mai ritentare).
    - Idempotente / ripristinabile: le transizioni si basano su ciò che si OSSERVA
      sull'ordine (bet_id, status, size_remaining, prezzo), non solo su `state.step`;
      ri-chiamarla con lo stesso stato non causa doppi place/cancel/replace.
    - `ops` (iniettabile) astrae place/cancel/replace per i test; in produzione il
      runner inietta `FlumineSubminOps`.

    `allow_place` (SICUREZZA money-critical): l'UNICO step che può PIAZZARE è INIT.
    Il primo avvio (``_start_submin``) chiama con il default ``allow_place=True``. La
    sola-ripresa (``_advance_submin_row``, righe già 'processing') chiama con
    ``allow_place=False``: in quel percorso lo stato INIT significa che lo step1 era
    stato persistito *prima* del place reale e il processo è poi caduto/ripartito,
    quindi il place POTREBBE essere GIÀ avvenuto. In ripresa NON si piazza mai un
    secondo ordine: o l'ordine è riconciliabile con certezza (bet_id assegnato), o si
    abortisce per riconciliazione manuale. Vedi il ramo STEP 1.
    """
    # Stati terminali: nessuna azione (idempotente).
    if state.step in _TERMINAL:
        return state

    # --- GUARDIA RISCHIO ---------------------------------------------------
    # Un match mentre l'ordine è alla quota non abbinabile = anomalia: STOP, niente ritento.
    if (
        state.step in _UNMATCHABLE_PHASES
        and order is not None
        and _size_matched(order) > _TOL
    ):
        return _dc_replace(
            state,
            step=SubminStep.ABORTED,
            bet_id=_bet_id(order) or state.bet_id,
            note=(
                f"ABORT: step1 abbinato (size_matched={_size_matched(order):.2f}) "
                "alla quota non abbinabile — nessun ritento, riconciliare a mano"
            ),
        )

    # --- STEP 1: place size minima @ quota non abbinabile ------------------
    if state.step == SubminStep.INIT:
        # Ripresa: se un ordine risulta GIÀ piazzato (bet_id assegnato), non ri-piazzare.
        if order is not None and _bet_id(order) is not None:
            return _dc_replace(
                state,
                step=SubminStep.PLACED,
                bet_id=_bet_id(order),
                note="resume: ordine step1 già presente (no re-place)",
            )
        # SICUREZZA money-critical — ripresa dopo RIAVVIO del processo (allow_place=False):
        # lo stato INIT in sola-ripresa = step1 persistito PRIMA del place reale + crash,
        # quindi il place POTREBBE essere già avvenuto sul mercato. Dopo un riavvio reale le
        # annotazioni locali (notes/context con il ref interno awlq<id>) sono PERSE — l'ordine
        # ricostruito dall'order stream non le porta — e non abbiamo né order_id né bet_id:
        # l'ordine NON è riconciliabile con CERTEZZA. Regola onesta: MAI un secondo place.
        #   - ordine ritrovato ma bet_id non ancora assegnato → ATTENDI (stato invariato);
        #   - ordine NON riconciliabile → ABORTED (riconciliazione manuale), zero place.
        if not allow_place:
            if order is not None:
                return state  # ritrovato (in-process, per ref): attende il bet_id, no place
            return _dc_replace(
                state,
                step=SubminStep.ABORTED,
                bet_id=state.bet_id,
                note=(
                    "submin interrotto a meta': riconciliare manualmente su Betfair, "
                    "NON ripiazzato"
                ),
            )
        placed_order = _require_ops(ops).place(
            market,
            side=state.side,
            price=initial_place_price(state.side),
            size=state.placed_size,
            customer_order_ref=customer_order_ref,
        )
        return _dc_replace(
            state,
            step=SubminStep.PLACED,
            bet_id=_bet_id(placed_order),
            note=f"step1 place {state.placed_size:.2f}@{initial_place_price(state.side)} (LAPSE)",
        )

    # --- STEP 2: cancel parziale (size_reduction) → resta target -----------
    if state.step == SubminStep.PLACED:
        # Serve l'ordine a riposo (EXECUTABLE) con bet_id assegnato prima di cancellare.
        bid = _bet_id(order)
        if order is None or bid is None or not _is_executable(order):
            return state  # attesa: l'ordine non è ancora confermato/abbinabile
        # Idempotenza/ripresa: se è già stato ridotto (size_remaining ~ target), avanza.
        rem = _size_remaining(order)
        if rem is not None and rem <= state.target_size + _TOL:
            return _dc_replace(
                state, step=SubminStep.TRIMMED, bet_id=bid,
                note="resume: ordine già ridotto a target (no re-cancel)",
            )
        _require_ops(ops).cancel(market, order, state.size_reduction)
        return _dc_replace(
            state, step=SubminStep.TRIMMED, bet_id=bid,
            note=f"step2 cancel {state.size_reduction:.2f} → resta {state.target_size:.2f}",
        )

    # --- STEP 3: replace alla quota target reale ---------------------------
    if state.step == SubminStep.TRIMMED:
        bid = _bet_id(order) or state.bet_id
        if order is None or not _is_executable(order):
            return state  # attesa
        # Idempotenza/ripresa: se è già alla target_price, avanza.
        cur_price = _order_price(order)
        if cur_price is not None and abs(cur_price - state.target_price) <= _TOL:
            return _dc_replace(
                state, step=SubminStep.REPRICED, bet_id=bid,
                note="resume: ordine già alla target_price (no re-replace)",
            )
        _require_ops(ops).replace(market, order, state.target_price)
        return _dc_replace(
            state, step=SubminStep.REPRICED, bet_id=bid,
            note=f"step3 replace → {state.target_price}",
        )

    # --- DONE: ordine a riposo a (target_price, target_size) ---------------
    if state.step == SubminStep.REPRICED:
        return _dc_replace(
            state, step=SubminStep.DONE, bet_id=_bet_id(order) or state.bet_id,
            note="submin completato: ordine sotto-minimo a riposo alla target_price",
        )

    return state  # difensivo (mai raggiunto)


def _require_ops(ops: Optional[SubminOps]) -> SubminOps:
    if ops is None:
        raise ValueError(
            "advance_submin richiede `ops` (SubminOps) per place/cancel/replace: "
            "il runner deve iniettare FlumineSubminOps(selection_id, handicap, jurisdiction)"
        )
    return ops
