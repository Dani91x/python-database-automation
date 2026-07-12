"""Test del motore puro di Omega (COSTITUZIONE_OMEGA.md §2–§6)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.omega import omega_engine as E


# ---------------------------------------------------------------------------
# round_to_tick
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        (1.005, 1.01),  # clamp basso
        (2.03, 2.02),   # banda 0.02
        (3.07, 3.05),   # banda 0.05
        (23.4, 23.0),   # banda 1.0
        (40.8, 40.0),   # banda 2.0 (40.8 -> 40)
        (43.1, 44.0),   # banda 2.0 (43.1 -> 44, più vicino)
        (73.0, 75.0),   # banda 5.0
        (128.0, 130.0), # banda 10.0
        (5000.0, 1000.0),  # clamp alto
    ],
)
def test_round_to_tick(raw, expected):
    assert E.round_to_tick(raw) == expected


def test_round_to_tick_non_scavalca_banda():
    # 29.6 non deve diventare 30.0 (banda successiva ha tick 2.0)
    assert E.round_to_tick(29.6) == 29.0


# ---------------------------------------------------------------------------
# scoreline parsing
# ---------------------------------------------------------------------------
def test_is_scoreline():
    assert E.is_scoreline("0 - 0")
    assert E.is_scoreline("3 - 2")
    assert not E.is_scoreline("Any Other Home Win")
    assert not E.is_scoreline("Any Unquoted")
    assert not E.is_scoreline(None)
    assert E.parse_scoreline("2 - 1") == (2, 1)
    assert E.parse_scoreline("nope") is None


# ---------------------------------------------------------------------------
# select_lay_runner (§3)
# ---------------------------------------------------------------------------
def _runners():
    return [
        E.ScoreRunner(1, "0 - 0", lay_price=8.0, lay_size=100),
        E.ScoreRunner(2, "1 - 0", lay_price=9.0, lay_size=100),
        E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=50),
        E.ScoreRunner(4, "3 - 2", lay_price=110.0, lay_size=40),
        E.ScoreRunner(5, "4 - 4", lay_price=500.0, lay_size=20),   # troppo alta
        E.ScoreRunner(6, "Any Other Home Win", lay_price=95.0, lay_size=200),
    ]


def test_select_prende_quota_piu_alta_nel_range():
    sel = E.select_lay_runner(
        _runners(), price_min=20, price_max=120, min_liquidity=5, include_aggregate=False
    )
    assert sel is not None
    assert sel.selection_id == 4  # "3 - 2" a 110, la più alta <= 120 tra le scoreline
    assert sel.name == "3 - 2"
    assert sel.price == 110.0


def test_select_esclude_aggregati_di_default():
    sel = E.select_lay_runner(
        _runners(), price_min=20, price_max=120, min_liquidity=5, include_aggregate=False
    )
    assert sel.selection_id != 6  # l'aggregato a 95 è escluso


def test_select_include_aggregati_se_richiesto():
    sel = E.select_lay_runner(
        _runners(), price_min=20, price_max=100, min_liquidity=5, include_aggregate=True
    )
    # con cap 100: scoreline valide = "2 - 1"@75; aggregato "Any Other"@95 è più alto
    assert sel.selection_id == 6


def test_select_filtra_liquidita():
    runners = [E.ScoreRunner(3, "2 - 1", lay_price=75.0, lay_size=2)]
    sel = E.select_lay_runner(
        runners, price_min=20, price_max=120, min_liquidity=5, include_aggregate=False
    )
    assert sel is None


def test_select_nessun_candidato_ritorna_none():
    runners = [E.ScoreRunner(1, "0 - 0", lay_price=8.0, lay_size=100)]
    sel = E.select_lay_runner(
        runners, price_min=20, price_max=120, min_liquidity=5, include_aggregate=False
    )
    assert sel is None


def test_select_ignora_runner_senza_lay():
    runners = [E.ScoreRunner(3, "2 - 1", lay_price=None, lay_size=100)]
    assert E.select_lay_runner(
        runners, price_min=20, price_max=120, min_liquidity=5, include_aggregate=False
    ) is None


# ---------------------------------------------------------------------------
# target dinamico (§2)
# ---------------------------------------------------------------------------
def test_dynamic_target_base():
    assert E.dynamic_target(250, 0, 50) == pytest.approx(5.0)


def test_dynamic_target_ricalcolo_in_avanti():
    # incassati 100, restano 10 match → (250-100)/10 = 15
    assert E.dynamic_target(250, 100, 10) == pytest.approx(15.0)


def test_dynamic_target_mai_negativo():
    assert E.dynamic_target(250, 300, 5) == 0.0


def test_dynamic_target_zero_match_non_divide_per_zero():
    assert E.dynamic_target(250, 0, 0) == pytest.approx(250.0)


# ---------------------------------------------------------------------------
# sizing (§2)
# ---------------------------------------------------------------------------
def test_lay_size_from_target():
    # target 5, comm 5% → 5 / 0.95 = 5.263 → arrotondato 5.26
    s = E.lay_size_from_target(5.0, commission=0.05, min_stake=0.5, rounding=0.01)
    assert s == pytest.approx(5.26, abs=0.01)
    # incasso netto ~ target
    assert E.net_profit_if_win(s, 0.05) == pytest.approx(5.0, abs=0.02)


def test_lay_size_rispetta_min_stake():
    s = E.lay_size_from_target(0.10, commission=0.05, min_stake=0.5, rounding=0.01)
    assert s == 0.5


def test_lay_size_target_zero():
    assert E.lay_size_from_target(0, commission=0.05, min_stake=0.5) == 0.0


def test_liability_from_lay():
    # size 5.26 a quota 110 → 5.26 * 109 = 573.34
    assert E.liability_from_lay(5.26, 110.0) == pytest.approx(573.34, abs=0.01)


def test_apply_liability_cap():
    # size 5.26 @110 liability 573 → cap 200 → size max = 200/109 = 1.83
    capped = E.apply_liability_cap(5.26, 110.0, 200.0)
    assert E.liability_from_lay(capped, 110.0) <= 200.0 + 0.01


def test_apply_liability_cap_off():
    assert E.apply_liability_cap(5.26, 110.0, 0) == 5.26


# ---------------------------------------------------------------------------
# paper fill (§6)
# ---------------------------------------------------------------------------
def test_paper_fill_best_price():
    f = E.paper_fill(5.0, best_price=110.0)
    assert f is not None
    assert f.matched_size == 5.0
    assert f.avg_price == 110.0
    assert f.fully_matched


def test_paper_fill_cammina_ladder():
    ladder = ((110.0, 3.0), (100.0, 10.0))
    f = E.paper_fill(5.0, best_price=110.0, lay_ladder=ladder)
    assert f.matched_size == 5.0
    # 3@110 + 2@100 = 330+200=530 / 5 = 106
    assert f.avg_price == pytest.approx(106.0, abs=0.01)
    assert f.fully_matched


def test_paper_fill_parziale():
    ladder = ((110.0, 2.0),)
    f = E.paper_fill(5.0, best_price=110.0, lay_ladder=ladder)
    assert f.matched_size == 2.0
    assert not f.fully_matched


def test_paper_fill_zero():
    assert E.paper_fill(0, best_price=110.0) is None


# ---------------------------------------------------------------------------
# settlement (§6, I3)
# ---------------------------------------------------------------------------
def test_settle_won_quando_risultato_non_esce():
    status, pnl = E.settle_pnl(
        our_selection_id=4, winner_selection_id=1, size=5.26, price=110.0, commission=0.05
    )
    assert status == "won"
    assert pnl == pytest.approx(5.0, abs=0.02)


def test_settle_lost_quando_risultato_esce():
    status, pnl = E.settle_pnl(
        our_selection_id=4, winner_selection_id=4, size=5.26, price=110.0, commission=0.05
    )
    assert status == "lost"
    assert pnl == pytest.approx(-573.34, abs=0.01)


def test_resolve_settlement_open():
    assert E.resolve_settlement("OPEN", ["ACTIVE", "ACTIVE"], False) == (False, False)
    assert E.resolve_settlement("SUSPENDED", [], False) == (False, False)


def test_resolve_settlement_regolato_con_vincitore():
    assert E.resolve_settlement("CLOSED", ["WINNER", "LOSER", "LOSER"], True) == (True, False)


def test_resolve_settlement_void_senza_vincitore():
    # tutti terminali, nessun WINNER → void
    assert E.resolve_settlement("CLOSED", ["LOSER", "REMOVED", "LOSER"], False) == (True, True)


def test_resolve_settlement_closed_ma_non_finalizzato():
    # CLOSED ma un runner ancora ACTIVE → NON regolare (ritenta)
    assert E.resolve_settlement("CLOSED", ["WINNER", "ACTIVE"], True) == (False, False)


def test_resolve_settlement_closed_senza_runner():
    assert E.resolve_settlement("CLOSED", [], False) == (False, False)


def test_aggregate_trades():
    rows = [
        {"status": "won", "pnl": 5, "liability": 100},
        {"status": "lost", "pnl": -300, "liability": 300},
        {"status": "void", "pnl": 0, "liability": 50},
        {"status": "open", "pnl": 0, "liability": 200},
        {"status": "pending", "pnl": 0, "liability": 150, "bet_id": "b1"},   # reale a mercato
        {"status": "pending", "pnl": 0, "liability": 999},                    # solo riservato
        {"status": "error", "pnl": 0, "liability": 999},
    ]
    agg = E.aggregate_trades(rows)
    assert agg["realized_profit"] == pytest.approx(-295.0)   # 5 -300 +0
    assert agg["open_liability"] == pytest.approx(350.0)     # 200 (open) + 150 (pending+bet_id)
    assert agg["matches_open"] == 2                          # open + pending-con-bet_id
    assert agg["matches_traded"] == 5                        # 3 settled + 2 aperti (no pending-riservato/error)
    assert agg["settled_count"] == 3


def _pending(placed_at="2026-07-12T15:00:00+00:00"):
    return {"event_id": "1.100", "market_id": "m1", "selection_id": 4,
            "side": "lay", "price": 110, "size": 5, "placed_at": placed_at}


NOW_ISO = "2026-07-12T16:00:00+00:00"


def test_reconcile_confirm_da_current_matchato():
    current = [{"customer_order_ref": "omega-1.100", "market_id": "m1", "selection_id": 4,
                "side": "lay", "size_matched": 5.0, "avg_price_matched": 110.0, "bet_id": "b9"}]
    d = E.reconcile_decision(_pending(), current, [], NOW_ISO)
    assert d["action"] == "confirm" and d["bet_id"] == "b9"
    assert d["size"] == 5.0 and d["price"] == 110.0


def test_reconcile_keep_se_non_matchato():
    current = [{"customer_order_ref": "omega-1.100", "market_id": "m1", "selection_id": 4,
                "side": "lay", "size_matched": 0.0, "bet_id": "b9"}]
    assert E.reconcile_decision(_pending(), current, [], NOW_ISO)["action"] == "keep"


def test_reconcile_keep_se_parzialmente_matchato():
    # matched>0 ma remaining>0 → ordine ancora in esecuzione → keep (non congelare)
    current = [{"customer_order_ref": "omega-1.100", "market_id": "m1", "selection_id": 4,
                "side": "lay", "size_matched": 2.0, "size_remaining": 3.0, "bet_id": "bP"}]
    assert E.reconcile_decision(_pending(), current, [], NOW_ISO)["action"] == "keep"


def test_reconcile_ref_diverso_non_matcha():
    # ordine con customerOrderRef di un ALTRO trade → non deve confermare questo
    current = [{"customer_order_ref": "omega-9.999", "market_id": "m1", "selection_id": 4,
                "side": "lay", "size_matched": 5.0, "size_remaining": 0.0, "bet_id": "bZ"}]
    assert E.reconcile_decision(_pending(), current, [], NOW_ISO)["action"] != "confirm"


def test_reconcile_confirm_da_cleared():
    cleared = [{"customer_order_ref": "omega-1.100", "market_id": "m1", "selection_id": 4,
                "side": "lay", "size_settled": 5.0, "price": 110.0, "bet_id": "bc"}]
    d = E.reconcile_decision(_pending(), [], cleared, NOW_ISO)
    assert d["action"] == "confirm" and d["bet_id"] == "bc" and d["size"] == 5.0


def test_reconcile_free_se_recente_e_non_trovato():
    # non trovato da nessuna parte, piazzato di recente → mai piazzato → libera
    assert E.reconcile_decision(_pending(), [], [], NOW_ISO)["action"] == "free"


def test_reconcile_error_se_vecchio_e_non_trovato():
    # non trovato e VECCHIO (>24h) → non rischiare un doppio → error
    old = _pending(placed_at="2026-07-10T10:00:00+00:00")
    assert E.reconcile_decision(old, [], [], NOW_ISO)["action"] == "error"


def test_reconcile_match_per_market_selection_senza_ref():
    # se il customerOrderRef manca, match su market_id + selection_id + side
    current = [{"market_id": "m1", "selection_id": 4, "side": "lay",
                "size_matched": 5.0, "avg_price_matched": 110.0, "bet_id": "b1"}]
    assert E.reconcile_decision(_pending(), current, [], NOW_ISO)["action"] == "confirm"


def test_settle_void():
    status, pnl = E.settle_pnl(
        our_selection_id=4, winner_selection_id=None, size=5.26, price=110.0, commission=0.05
    )
    assert status == "void"
    assert pnl == 0.0
    status2, pnl2 = E.settle_pnl(
        our_selection_id=4, winner_selection_id=1, size=5.26, price=110.0, commission=0.05, voided=True
    )
    assert status2 == "void" and pnl2 == 0.0


# ---------------------------------------------------------------------------
# finestra d'ingresso (§4)
# ---------------------------------------------------------------------------
def test_minute_from_clock():
    start = datetime(2026, 7, 12, 15, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 12, 15, 42, tzinfo=timezone.utc)
    assert E.minute_from_clock(start, now) == 42


def test_is_in_entry_window():
    assert E.is_in_entry_window(42, 30, 60)
    assert not E.is_in_entry_window(70, 30, 60)
    assert not E.is_in_entry_window(None, 30, 60)


def test_is_eligible_happy_path():
    assert E.is_eligible(
        inplay=True, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=3, max_events=0,
        goal_reached=False, stop_on_goal=True,
    )


def test_is_eligible_blocca_gia_piazzato():
    assert not E.is_eligible(
        inplay=True, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=True, traded_count=3, max_events=0,
        goal_reached=False, stop_on_goal=True,
    )


def test_is_eligible_blocca_fuori_finestra_e_non_inplay():
    assert not E.is_eligible(
        inplay=False, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=0, max_events=0,
        goal_reached=False, stop_on_goal=True,
    )
    assert not E.is_eligible(
        inplay=True, minute=10, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=0, max_events=0,
        goal_reached=False, stop_on_goal=True,
    )


def test_is_eligible_max_events_e_goal():
    assert not E.is_eligible(
        inplay=True, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=10, max_events=10,
        goal_reached=False, stop_on_goal=True,
    )
    assert not E.is_eligible(
        inplay=True, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=1, max_events=0,
        goal_reached=True, stop_on_goal=True,
    )
    # stop_on_goal off → l'obiettivo raggiunto non blocca
    assert E.is_eligible(
        inplay=True, minute=42, entry_minute_min=30, entry_minute_max=60,
        already_traded=False, traded_count=1, max_events=0,
        goal_reached=True, stop_on_goal=False,
    )
