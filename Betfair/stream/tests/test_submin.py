"""Unit test della macchina a stati place-and-trim (`Betfair/stream/trading/submin.py`).

Money-critical: nessuna rete, nessun login, nessun ordine reale. Le operazioni
flumine (place/cancel/replace) sono dietro l'interfaccia iniettabile `SubminOps`,
qui sostituita da un mock che registra le chiamate. Il Market e l'ordine sono
namespace leggeri (solo gli attributi letti dalla macchina a stati).

Scenari coperti:
  - percorso felice (INIT→PLACED→TRIMMED→REPRICED→DONE);
  - match imprevisto alla quota non abbinabile → ABORTED, nessun ritento;
  - interruzione e ripresa (idempotenza: niente doppi place/cancel/replace);
  - target sotto il floor LAY .it (caso d'uso del submin) + validazioni di confine.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional, Tuple

import pytest
from flumine import BaseStrategy

from Betfair.stream.trading.submin import (
    FlumineSubminOps,
    SubminState,
    SubminStep,
    advance_submin,
    initial_place_price,
    place_min_size,
    start_submin,
)


# ---------------------------------------------------------------------------
# Helper / mock
# ---------------------------------------------------------------------------
def _market(market_id: str = "1.234567890"):
    """Mock minimale di flumine Market (solo market_id, usato da build_order)."""
    return SimpleNamespace(market_id=market_id)


def _order(
    *,
    bet_id: Optional[str] = "BET-1",
    status: str = "EXECUTABLE",
    size_matched: float = 0.0,
    size_remaining: Optional[float] = None,
    price: Optional[float] = None,
):
    """Mock di BetfairOrder: solo gli attributi letti dalla macchina a stati."""
    return SimpleNamespace(
        bet_id=bet_id,
        status=status,                       # 'EXECUTABLE' / 'EXECUTION_COMPLETE' ...
        size_matched=size_matched,
        size_remaining=size_remaining,
        order_type=SimpleNamespace(price=price),
    )


class _RecordingOps:
    """SubminOps mock: registra ogni chiamata e restituisce un ordine fittizio."""

    def __init__(self, place_bet_id: Optional[str] = "BET-1") -> None:
        self.calls: List[Tuple[str, dict]] = []
        self._place_bet_id = place_bet_id

    def place(self, market: Any, *, side: str, price: float, size: float, customer_order_ref: str) -> Any:
        self.calls.append(("place", {"side": side, "price": price, "size": size, "ref": customer_order_ref}))
        return _order(bet_id=self._place_bet_id, status="PENDING", size_matched=0.0, size_remaining=size)

    def cancel(self, market: Any, order: Any, size_reduction: float) -> None:
        self.calls.append(("cancel", {"size_reduction": size_reduction}))

    def replace(self, market: Any, order: Any, new_price: float) -> None:
        self.calls.append(("replace", {"new_price": new_price}))

    def names(self) -> List[str]:
        return [name for name, _ in self.calls]


def _advance(
    state: SubminState, ops: _RecordingOps, order=None,
    now_ms: Optional[int] = None,
) -> SubminState:
    return advance_submin(
        _market(), state, order=order, jurisdiction="it",
        customer_order_ref="awlq999", ops=ops, now_ms=now_ms,
    )


# ===========================================================================
# initial_place_price / place_min_size
# ===========================================================================
def test_initial_place_price_unmatchable_extremes():
    assert initial_place_price("back") == 1000.0
    assert initial_place_price("lay") == 1.01
    with pytest.raises(ValueError):
        initial_place_price("x")


def test_place_min_size_it():
    assert place_min_size("it", "back") == 2.00
    assert place_min_size("it", "lay") == 0.50
    assert place_min_size("com", "back") == 2.00
    with pytest.raises(ValueError):
        place_min_size("zz", "back")


# ===========================================================================
# start_submin — costruzione e validazioni
# ===========================================================================
def test_start_submin_lay_below_floor_is_the_use_case():
    """Target LAY €0,30 (< floor €0,50): è ESATTAMENTE lo scopo del submin.
    placed_size = €0,50 (minimo lay .it), size_reduction = 0,20."""
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    assert st.step is SubminStep.INIT
    assert st.placed_size == 0.50
    assert st.target_size == 0.30
    assert st.target_price == 5.0
    assert st.size_reduction == 0.20


def test_start_submin_back_below_min():
    st = start_submin(side="back", target_price=3.0, target_size=1.50, jurisdiction="it")
    assert st.placed_size == 2.00
    assert st.size_reduction == 0.50  # 2.00 - 1.50


def test_start_submin_rejects_below_absolute_floor():
    with pytest.raises(ValueError):
        start_submin(side="lay", target_price=5.0, target_size=0.005, jurisdiction="it")


def test_start_submin_rejects_target_at_or_above_place_minimum():
    # target >= minimo di piazzamento => non serve il submin (usa place normale)
    with pytest.raises(ValueError):
        start_submin(side="lay", target_price=5.0, target_size=0.50, jurisdiction="it")
    with pytest.raises(ValueError):
        start_submin(side="back", target_price=3.0, target_size=2.00, jurisdiction="it")


def test_start_submin_rounds_price_to_tick():
    st = start_submin(side="lay", target_price=5.3149, target_size=0.30, jurisdiction="it")
    assert st.target_price == 5.3  # snap al tick valido


# ===========================================================================
# PERCORSO FELICE (INIT → PLACED → TRIMMED → REPRICED → DONE)
# ===========================================================================
def test_happy_path_full_sequence():
    ops = _RecordingOps(place_bet_id="BET-77")
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")

    # step1: place min @ quota non abbinabile (1.01 lay), LAPSE
    st = _advance(st, ops)  # order=None
    assert st.step is SubminStep.PLACED
    assert st.bet_id == "BET-77"
    assert ops.names() == ["place"]
    assert ops.calls[0][1]["price"] == 1.01
    assert ops.calls[0][1]["size"] == 0.50  # placed_size = min lay .it

    # step2a: ordine a riposo (EXECUTABLE) con size piena → cancel RICHIESTO,
    # ma NIENTE promozione sulla fiducia dell'API (fix bug live 10/07 21:43)
    resting = _order(bet_id="BET-77", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=resting, now_ms=1_000_000)
    assert st.step is SubminStep.PLACED          # ancora PLACED: attesa verifica
    assert st.trim_requested_ms == 1_000_000
    assert ops.names() == ["place", "cancel"]
    assert ops.calls[1][1]["size_reduction"] == 0.20  # 0.50 - 0.30

    # step2b: il trim viene OSSERVATO (size_remaining ~ target) → TRIMMED
    observed = _order(bet_id="BET-77", status="EXECUTABLE", size_matched=0.0, size_remaining=0.30, price=1.01)
    st = _advance(st, ops, order=observed, now_ms=1_001_000)
    assert st.step is SubminStep.TRIMMED
    assert ops.names() == ["place", "cancel"]     # nessuna nuova operazione

    # step3: ridotto a target → replace alla target_price reale (5.0)
    trimmed = _order(bet_id="BET-77", status="EXECUTABLE", size_matched=0.0, size_remaining=0.30, price=1.01)
    st = _advance(st, ops, order=trimmed)
    assert st.step is SubminStep.REPRICED
    assert ops.names() == ["place", "cancel", "replace"]
    assert ops.calls[2][1]["new_price"] == 5.0

    # DONE
    repriced = _order(bet_id="BET-77", status="EXECUTABLE", size_matched=0.0, size_remaining=0.30, price=5.0)
    st = _advance(st, ops, order=repriced)
    assert st.step is SubminStep.DONE
    assert ops.names() == ["place", "cancel", "replace"]  # nessuna nuova chiamata

    # idempotenza terminale: ri-chiamare su DONE non fa nulla
    st2 = _advance(st, ops, order=repriced)
    assert st2.step is SubminStep.DONE
    assert ops.names() == ["place", "cancel", "replace"]


def test_back_happy_place_uses_1000_and_back_min():
    ops = _RecordingOps(place_bet_id="B1")
    st = start_submin(side="back", target_price=3.0, target_size=1.0, jurisdiction="it")
    st = _advance(st, ops)
    assert st.step is SubminStep.PLACED
    assert ops.calls[0][1]["price"] == 1000.0
    assert ops.calls[0][1]["size"] == 2.00  # back min .it


# ===========================================================================
# MATCH IMPREVISTO → ABORT (guardia rischio, nessun ritento)
# ===========================================================================
def test_unexpected_match_at_placed_aborts():
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    st = _advance(st, ops)  # PLACED
    assert st.step is SubminStep.PLACED

    # l'ordine "non abbinabile" risulta abbinato → ABORT, nessun cancel
    matched = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.50, size_remaining=0.0, price=1.01)
    st = _advance(st, ops, order=matched)
    assert st.step is SubminStep.ABORTED
    assert "ABORT" in st.note
    assert ops.names() == ["place"]  # NESSUN cancel dopo il match

    # nessun ritento: ri-chiamare resta ABORTED e non emette nuove operazioni
    st = _advance(st, ops, order=matched)
    assert st.step is SubminStep.ABORTED
    assert ops.names() == ["place"]


def test_unexpected_match_at_trimmed_aborts():
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.TRIMMED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    matched = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.30, size_remaining=0.0, price=1.01)
    st = _advance(st, ops, order=matched)
    assert st.step is SubminStep.ABORTED
    assert ops.names() == []  # nessun replace


def test_match_at_repriced_is_desired_not_abort():
    """Alla target_price l'abbinamento è l'ESITO VOLUTO: NON deve abortire."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.REPRICED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    matched = _order(bet_id="BET-1", status="EXECUTION_COMPLETE", size_matched=0.30, size_remaining=0.0, price=5.0)
    st = _advance(st, ops, order=matched)
    assert st.step is SubminStep.DONE
    assert ops.names() == []


# ===========================================================================
# INTERRUZIONE E RIPRESA (idempotenza)
# ===========================================================================
def test_resume_init_with_existing_order_does_not_replace():
    """Crash dopo il place ma prima di salvare PLACED: alla ripresa lo stato è
    ancora INIT ma l'ordine esiste già (bet_id) → riconcilia a PLACED senza ri-piazzare."""
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    existing = _order(bet_id="ALREADY", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=existing)
    assert st.step is SubminStep.PLACED
    assert st.bet_id == "ALREADY"
    assert ops.names() == []  # NESSUN place duplicato


def test_placed_waits_until_executable_with_bet_id():
    """Idempotenza: finché l'ordine non è EXECUTABLE con bet_id, niente cancel."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.PLACED, bet_id=None, target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    # ancora PENDING senza bet_id → resta PLACED, nessuna operazione
    pending = _order(bet_id=None, status="PENDING", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=pending)
    assert st.step is SubminStep.PLACED
    assert ops.names() == []

    # anche order=None (nessuna info) → resta PLACED
    st = _advance(st, ops, order=None)
    assert st.step is SubminStep.PLACED
    assert ops.names() == []


def test_resume_placed_already_trimmed_does_not_cancel():
    """Crash dopo il cancel ma prima di salvare TRIMMED: alla ripresa lo stato è
    ancora PLACED ma l'ordine è già ridotto (size_remaining ~ target) → no re-cancel."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.PLACED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    already_trimmed = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.30, price=1.01)
    st = _advance(st, ops, order=already_trimmed)
    assert st.step is SubminStep.TRIMMED
    assert ops.names() == []  # nessun cancel duplicato


def test_resume_trimmed_already_repriced_does_not_replace():
    """Crash dopo il replace ma prima di salvare REPRICED: l'ordine è già alla
    target_price → no re-replace."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.TRIMMED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    already_repriced = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.30, price=5.0)
    st = _advance(st, ops, order=already_repriced)
    assert st.step is SubminStep.REPRICED
    assert ops.names() == []  # nessun replace duplicato


def test_trimmed_waits_if_not_executable():
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.TRIMMED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    st = _advance(st, ops, order=None)
    assert st.step is SubminStep.TRIMMED
    assert ops.names() == []


# ===========================================================================
# RIPRESA SICURA dopo RIAVVIO (allow_place=False): MAI un secondo place
# ===========================================================================
def test_resume_init_not_reconcilable_aborts_never_replaces():
    """Sola-ripresa (allow_place=False) con stato INIT e NESSUN ordine riconciliabile
    (order=None): il place potrebbe essere già avvenuto → ABORTED per riconciliazione
    manuale, MAI un secondo place."""
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    out = advance_submin(
        _market(), st, order=None, jurisdiction="it",
        customer_order_ref="awlq999", ops=ops, allow_place=False,
    )
    assert out.step is SubminStep.ABORTED
    assert ops.names() == []  # NESSUN place
    assert "riconciliare manualmente" in out.note
    assert "NON ripiazzato" in out.note


def test_resume_init_reconciles_to_placed_when_bet_id_present():
    """Sola-ripresa (allow_place=False) con ordine ritrovato e bet_id assegnato →
    riconciliato a PLACED, senza ri-piazzare."""
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    existing = _order(bet_id="B-REAL", status="EXECUTABLE", size_remaining=0.50, price=1.01)
    out = advance_submin(
        _market(), st, order=existing, jurisdiction="it",
        customer_order_ref="awlq999", ops=ops, allow_place=False,
    )
    assert out.step is SubminStep.PLACED
    assert out.bet_id == "B-REAL"
    assert ops.names() == []  # nessun place


def test_resume_init_waits_when_order_found_without_bet_id():
    """Sola-ripresa (allow_place=False) con ordine ritrovato ma bet_id non ancora
    assegnato (async): si ATTENDE (stato invariato), niente place, niente abort."""
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    pending = _order(bet_id=None, status="PENDING", size_remaining=0.50, price=1.01)
    out = advance_submin(
        _market(), st, order=pending, jurisdiction="it",
        customer_order_ref="awlq999", ops=ops, allow_place=False,
    )
    assert out.step is SubminStep.INIT  # invariato: attende il bet_id
    assert ops.names() == []


def test_resume_init_allow_place_false_match_still_aborts_guard_first():
    """Anche in sola-ripresa, un match alla quota non abbinabile resta prioritario:
    ABORT della guardia rischio (non il path di riconciliazione)."""
    ops = _RecordingOps()
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    matched = _order(bet_id="B-REAL", status="EXECUTABLE", size_matched=0.50, size_remaining=0.0, price=1.01)
    out = advance_submin(
        _market(), st, order=matched, jurisdiction="it",
        customer_order_ref="awlq999", ops=ops, allow_place=False,
    )
    assert out.step is SubminStep.ABORTED
    assert "ABORT" in out.note  # guardia rischio, non il messaggio di riconciliazione
    assert ops.names() == []


def test_advance_requires_ops_for_place():
    """Senza `ops` non si può piazzare: errore esplicito (il runner deve iniettare)."""
    st = start_submin(side="lay", target_price=5.0, target_size=0.30, jurisdiction="it")
    with pytest.raises(ValueError):
        advance_submin(_market(), st, jurisdiction="it", customer_order_ref="awlq1", ops=None)


# ===========================================================================
# REGRESSIONE BUG LIVE 10/07 21:43 — "trimmed ✓" su park abbinato intero
# (il replace portava la size PIENA a quota reale → fill istantaneo, ×4)
# ===========================================================================
def _placed_state(trim_requested_ms: int = 0) -> SubminState:
    return SubminState(
        step=SubminStep.PLACED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
        trim_requested_ms=trim_requested_ms,
    )


def test_bug_2143_snapshot_stantio_poi_match_niente_replace():
    """LA regressione della serata: al poll del cancel lo snapshot è stantio
    (matched=0), al poll dopo il park risulta ABBINATO INTERO. La macchina
    NON deve mai arrivare al replace: guardia rischio → ABORTED."""
    ops = _RecordingOps()
    st = _placed_state()
    # poll 1: snapshot stantio, size piena a riposo → cancel richiesto, NO promozione
    stale = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=stale, now_ms=1_000_000)
    assert st.step is SubminStep.PLACED
    assert ops.names() == ["cancel"]
    # poll 2: la verità arriva — park abbinato per intero → ABORT, mai replace
    matched = _order(bet_id="BET-1", status="EXECUTION_COMPLETE", size_matched=0.50, size_remaining=0.0, price=1.01)
    st = _advance(st, ops, order=matched, now_ms=1_002_000)
    assert st.step is SubminStep.ABORTED
    assert "ABORT" in st.note
    assert "replace" not in ops.names()  # MAI il replace della size piena


def test_step2_attesa_senza_nuove_operazioni_prima_del_recheck():
    """Dopo la richiesta di cancel, entro la latenza attesa NON si ri-emette
    nulla: si aspetta l'osservazione."""
    ops = _RecordingOps()
    st = _placed_state(trim_requested_ms=1_000_000)
    intact = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=intact, now_ms=1_002_000)  # +2s < recheck 5s
    assert st.step is SubminStep.PLACED
    assert ops.names() == []


def test_step2_riemissione_unica_su_residuo_intatto():
    """Residuo INTATTO oltre la latenza attesa (cancel mai agito) → UNA
    ri-emissione del cancel parziale, timestamp aggiornato."""
    ops = _RecordingOps()
    st = _placed_state(trim_requested_ms=1_000_000)
    intact = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=intact, now_ms=1_006_000)  # +6s ≥ recheck 5s
    assert st.step is SubminStep.PLACED
    assert ops.names() == ["cancel"]
    assert ops.calls[0][1]["size_reduction"] == 0.20  # parziale, non full
    assert st.trim_requested_ms == 1_006_000


def test_step2_timeout_full_cancel_e_abort():
    """Trim MAI osservato entro il timeout → ritiro TOTALE (size_reduction
    None) + ABORTED: mai proseguire verso il replace."""
    ops = _RecordingOps()
    st = _placed_state(trim_requested_ms=1_000_000)
    # rem parziale strano (né target né intatto): niente ri-emissione, al
    # timeout si ritira tutto
    weird = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.42, price=1.01)
    st = _advance(st, ops, order=weird, now_ms=1_016_000)  # +16s ≥ timeout 15s
    assert st.step is SubminStep.ABORTED
    assert ops.names() == ["cancel"]
    assert ops.calls[0][1]["size_reduction"] is None  # full cancel
    assert "mai replace" in st.note


def test_step2_park_scomparso_abort_pulito():
    """Park sparito dopo la richiesta (zero matched, zero residuo, non
    executable) = cancellato per intero → ABORT pulito, nessuna attesa infinita."""
    ops = _RecordingOps()
    st = _placed_state(trim_requested_ms=1_000_000)
    gone = _order(bet_id="BET-1", status="EXECUTION_COMPLETE", size_matched=0.0, size_remaining=0.0, price=1.01)
    st = _advance(st, ops, order=gone, now_ms=1_003_000)
    assert st.step is SubminStep.ABORTED
    assert "scomparso" in st.note
    assert ops.names() == []


def test_step3_rifiuta_replace_con_residuo_oltre_target():
    """DIFESA IN PROFONDITÀ: in TRIMMED (es. stato ripristinato) con residuo
    osservato OLTRE il target il replace è VIETATO → full cancel + ABORTED.
    È esattamente la mossa che il 10/07 ha portato 2€ pieni a quota reale."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.TRIMMED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    full = _order(bet_id="BET-1", status="EXECUTABLE", size_matched=0.0, size_remaining=0.50, price=1.01)
    st = _advance(st, ops, order=full, now_ms=1_000_000)
    assert st.step is SubminStep.ABORTED
    assert ops.names() == ["cancel"]
    assert ops.calls[0][1]["size_reduction"] is None  # ritiro totale
    assert "replace VIETATO" in st.note
    assert "replace" not in ops.names()


def test_step3_park_scomparso_abort_pulito():
    """Anche in TRIMMED un park sparito senza matched → ABORT pulito."""
    ops = _RecordingOps()
    st = SubminState(
        step=SubminStep.TRIMMED, bet_id="BET-1", target_size=0.30,
        target_price=5.0, placed_size=0.50, side="lay",
    )
    gone = _order(bet_id="BET-1", status="EXECUTION_COMPLETE", size_matched=0.0, size_remaining=0.0, price=1.01)
    st = _advance(st, ops, order=gone, now_ms=1_000_000)
    assert st.step is SubminStep.ABORTED
    assert "scomparso" in st.note
    assert ops.names() == []


# ===========================================================================
# FlumineSubminOps — usa le API NATIVE del Market (verificato con mock di Market)
# ===========================================================================
def test_flumine_ops_calls_native_market_methods():
    placed = {}

    class _FakeMarket:
        market_id = "1.234567890"

        def place_order(self, order):
            placed["order"] = order

        def cancel_order(self, order, size_reduction):
            placed["cancel"] = (order, size_reduction)

        def replace_order(self, order, new_price):
            placed["replace"] = (order, new_price)

    mkt = _FakeMarket()
    ops = FlumineSubminOps(
        selection_id=47999, handicap=0.0, jurisdiction="it",
        strategy=BaseStrategy(market_filter={}, name="live_trading"),
    )

    order = ops.place(mkt, side="lay", price=1.01, size=0.50, customer_order_ref="awlq5")
    assert placed["order"] is order  # ordine NATIVO flumine passato a place_order

    ops.cancel(mkt, order, 0.20)
    assert placed["cancel"] == (order, 0.20)

    ops.replace(mkt, order, 5.0)
    assert placed["replace"] == (order, 5.0)


# ===========================================================================
# CODE-MED-1 — replace LAY ri-valida il cap (liability = size*(price-1) cresce col prezzo)
# ===========================================================================
class _ReplaceMarket:
    """Mock di Market che registra (o vieta) il replace nativo."""

    market_id = "1.234567890"

    def __init__(self) -> None:
        self.replaced: Optional[Tuple[Any, float]] = None

    def replace_order(self, order: Any, new_price: float) -> None:
        self.replaced = (order, new_price)


def _ops_with_cap(cap: Optional[float]) -> FlumineSubminOps:
    return FlumineSubminOps(
        selection_id=47999, handicap=0.0, jurisdiction="it",
        strategy=BaseStrategy(market_filter={}, name="live_trading"), max_stake=cap,
    )


def test_replace_lay_over_cap_raises_no_native_replace():
    """LAY: replace alla target_price con liability oltre il cap → ValueError, e
    market.replace_order NON è chiamato (il cap scatta prima)."""
    mkt = _ReplaceMarket()
    ops = _ops_with_cap(1.0)
    # size 0.50 @ 5.0 → liability 0.50*(5-1)=€2,00 > cap €1,00
    order = SimpleNamespace(side="LAY", size_remaining=0.50,
                            order_type=SimpleNamespace(size=0.50, price=1.01))
    with pytest.raises(ValueError):
        ops.replace(mkt, order, 5.0)
    assert mkt.replaced is None  # nessun replace nativo


def test_replace_lay_under_cap_calls_native():
    """LAY: liability sotto il cap → replace nativo eseguito (no falsi positivi)."""
    mkt = _ReplaceMarket()
    ops = _ops_with_cap(10.0)
    # size 0.30 @ 5.0 → liability 0.30*(5-1)=€1,20 < cap €10
    order = SimpleNamespace(side="LAY", size_remaining=0.30,
                            order_type=SimpleNamespace(size=0.30, price=1.01))
    ops.replace(mkt, order, 5.0)
    assert mkt.replaced == (order, 5.0)


def test_replace_back_not_capped_by_liability():
    """BACK: il rischio è la size, non la liability; il guard liability NON si applica."""
    mkt = _ReplaceMarket()
    ops = _ops_with_cap(1.0)
    order = SimpleNamespace(side="BACK", size_remaining=100.0,
                            order_type=SimpleNamespace(size=100.0, price=1000.0))
    ops.replace(mkt, order, 3.0)  # nessun ValueError per un BACK
    assert mkt.replaced == (order, 3.0)


def test_replace_lay_no_cap_set_does_not_block():
    """max_stake=None (cap non impostato) → il guard non blocca (replace eseguito)."""
    mkt = _ReplaceMarket()
    ops = _ops_with_cap(None)
    order = SimpleNamespace(side="LAY", size_remaining=5.0,
                            order_type=SimpleNamespace(size=5.0, price=1.01))
    ops.replace(mkt, order, 5.0)
    assert mkt.replaced == (order, 5.0)
