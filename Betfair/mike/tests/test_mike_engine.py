"""Test dell'engine puro di Mike (matematica + macchina a stati).

Nessuna rete, nessun DB. File ASCII-only (console Windows cp1252).
"""
from __future__ import annotations

import pytest

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.stream.trading.greenup import compute_greenup

KO = 1_800_000_000.0          # epoch fittizio del calcio d'inizio
H = 3600.0


def params(**over):
    p = C.merge_params(None)
    p.update(over)
    return p


def book(bb, bs=100.0, bl=None, ls=100.0, status="OPEN", inplay=False):
    if bl is None:
        bl = E.ticks_away(bb, 1)
    return E.Book(best_back=bb, back_size=bs, best_lay=bl, lay_size=ls,
                  status=status, inplay=inplay)


def snap(now, *, u35=None, o45=None, u45=None, inplay=False, minute=None, goals=None,
         ht_active=False, feed_fresh=True, hazard=None, p4_market=None,
         last_goal_ts=None, market_status="OPEN", final_total=None, pressure=1.0, model_probs=None):
    books = {}
    if u35 is not None:
        books[(E.MARKET_OU35, E.SEL_UNDER)] = u35
    if o45 is not None:
        books[(E.MARKET_OU45, E.SEL_OVER)] = o45
    if u45 is not None:
        books[(E.MARKET_OU45, E.SEL_UNDER)] = u45
    return E.Snapshot(now=now, ko_at=KO, books=books, inplay=inplay, minute=minute,
                      goals=goals, ht_active=ht_active, feed_fresh=feed_fresh,
                      hazard=hazard, p4_market=p4_market, last_goal_ts=last_goal_ts,
                      market_status=market_status, final_total=final_total,
                      pressure=pressure, model_probs=model_probs)


def fill(leg, size=None, price=None):
    """Simula il fill completo di una gamba (come farebbe process_orders)."""
    leg.matched = float(size if size is not None else leg.size)
    leg.avg_price = float(price if price is not None else leg.price)
    leg.status = "open"
    return leg


# ---------------------------------------------------------------------------
# Matematica pura
# ---------------------------------------------------------------------------
def test_locked_pnl_back_matches_compute_greenup():
    locked = E.locked_pnl_back(20.0, 1.50, 1.48)
    assert locked == pytest.approx(20 * (1.5 / 1.48 - 1), abs=1e-6)
    plan = compute_greenup(matched_if_win=10.0, matched_if_lose=-20.0,
                           best_back_price=1.49, best_lay_price=1.48, fraction=1.0)
    assert plan.side == "lay"
    assert abs(plan.expected_if_win - plan.expected_if_lose) < 0.011
    assert plan.expected_if_win == pytest.approx(locked, abs=0.011)


def test_green_target_two_ticks_below():
    assert E.green_target(1.50, 2) == pytest.approx(1.48)
    assert E.green_target(2.00, 2) == pytest.approx(1.98)
    assert E.green_target(3.00, 2) == pytest.approx(2.96)   # fra 2 e 3 il tick e' 0.02
    assert E.green_target(3.10, 2) == pytest.approx(3.00)   # sopra 3 il tick e' 0.05


def test_cover_size_formula_and_legalization():
    x = E.cover_size(20.0, 8.0, 0.05, 1.2)
    assert x == pytest.approx(24 / (7 * 0.95), abs=1e-6)          # 3.609
    size, over = E.legalize_back_size(x, "ceil")
    assert size == 4.0 and over == pytest.approx((4.0 / x - 1) * 100, abs=1e-3)
    size, _ = E.legalize_back_size(x, "floor")
    assert size == 3.5
    size, _ = E.legalize_back_size(x, "nearest")
    assert size == 3.5
    # sotto il minimo .it -> 2.00 con overshoot esplicito
    size, over = E.legalize_back_size(E.cover_size(10.0, 8.0, 0.05, 1.2), "floor")
    assert size == 2.0 and over > 0
    # con exact_sizes la size resta al centesimo (3.61), overshoot 0
    assert E.cover_legal_size(x, params()) == (3.61, 0.0)
    assert E.cover_legal_size(x, params(exact_sizes=False)) == (4.0, pytest.approx(10.8333, abs=1e-3))
    # pareggio esatto: con 5+ gol il netto e' +20% dello stake Under
    S, Po, c = 20.0, 8.0, 0.05
    X = E.cover_size(S, Po, c, 1.2)
    assert X * (Po - 1) * (1 - c) - S == pytest.approx(0.2 * S, abs=1e-6)


def test_net_pnl_by_total_two_legs():
    legs = [
        fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="back", price=1.50, size=20.0)),
        fill(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                   side="back", price=8.0, size=4.0)),
    ]
    pnl = E.net_pnl_by_total(legs, 0.05)
    assert pnl[0] == pytest.approx(20 * 0.5 * 0.95 - 4, abs=0.01)
    assert pnl[3] == pytest.approx(5.5, abs=0.01)
    assert pnl[4] == pytest.approx(-24.0, abs=0.01)
    assert pnl[5] == pytest.approx(4 * 7 * 0.95 - 20, abs=0.01)
    assert pnl[8] == pnl[5]


def test_net_pnl_by_total_with_green_lay_is_flat_on_that_market():
    legs = [
        fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="back", price=1.50, size=20.0)),
        fill(E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="lay", price=1.48, size=round(20 * 1.5 / 1.48, 2))),
    ]
    pnl = E.net_pnl_by_total(legs, 0.0)
    assert pnl[0] == pytest.approx(pnl[6], abs=0.02)
    assert pnl[0] == pytest.approx(E.locked_pnl_back(20, 1.5, 1.48), abs=0.02)


def test_exposure_and_cashout_value_single_leg():
    legs = [fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                       side="back", price=1.50, size=20.0))]
    w, l = E.exposure(legs, E.MARKET_OU35, E.SEL_UNDER)
    assert (w, l) == (10.0, -20.0)
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.39, bl=1.40)}
    cv = E.cashout_value(legs, books, 0.05)
    locked = -20 + 30 / 1.40
    assert cv.gross == pytest.approx(locked, abs=0.02)
    assert cv.net == pytest.approx(locked * 0.95, abs=0.02)
    assert cv.complete is True
    # prezzo mancante -> incompleto, mai un numero inventato
    cv2 = E.cashout_value(legs, {}, 0.05)
    assert cv2.complete is False


def test_should_cashout_and_loss_exit():
    assert E.should_cashout(1.30, 24.0, 5.0) is True     # 5.4%
    assert E.should_cashout(1.10, 24.0, 5.0) is False
    assert E.loss_exit_ok(-5.0, 24.0, 25.0, goals=2, gmin=2, gmax=4) is True   # -20.8%
    assert E.loss_exit_ok(-7.0, 24.0, 25.0, goals=2, gmin=2, gmax=4) is False  # -29%
    assert E.loss_exit_ok(-5.0, 24.0, 25.0, goals=1, gmin=2, gmax=4) is False
    assert E.loss_exit_ok(1.0, 24.0, 25.0, goals=3, gmin=2, gmax=4) is True


def test_cover_timing_policy():
    p = params()
    kw = dict(goals=0, minute=5, hazard=0.05, p4_market=0.12, last_goal_ts=None, now=KO + 300)
    assert E.cover_timing(params=p, **kw) == "wait"
    assert E.cover_timing(params=params(cover_policy="immediate"), **kw) == "cover"
    assert E.cover_timing(params=p, **{**kw, "minute": 20}) == "cover"
    assert E.cover_timing(params=p, **{**kw, "hazard": 0.12}) == "cover"
    assert E.cover_timing(params=p, **{**kw, "p4_market": 0.20}) == "cover"
    assert E.cover_timing(params=p, **{**kw, "hazard": None}) == "cover"   # senza dati: copri
    # dopo un gol: attesa di riprezzo poi copertura
    assert E.cover_timing(params=p, goals=1, minute=30, hazard=0.05, p4_market=0.1,
                          last_goal_ts=KO + 1790, now=KO + 1800) == "wait"
    assert E.cover_timing(params=p, goals=1, minute=30, hazard=0.05, p4_market=0.1,
                          last_goal_ts=KO + 1700, now=KO + 1800) == "cover"
    assert E.cover_timing(params=p, goals=3, minute=60, hazard=0.05, p4_market=0.1,
                          last_goal_ts=None, now=KO + 3600) == "skip"
    assert E.cover_timing(params=params(cover_policy="wait"), **{**kw, "minute": 8}) == "wait"
    assert E.cover_timing(params=params(cover_policy="wait"), **{**kw, "minute": 10}) == "cover"
    # "intelligente ma non lenta": quota gia' buona → copri; risparmio atteso basso → copri
    assert E.cover_timing(params=p, price_over=7.0, **kw) == "cover"
    assert E.cover_timing(params=p, price_over=6.0, **kw) == "wait"
    assert E.cover_timing(params=p, price_over=6.0, cover_gain_pct=5.0, **kw) == "cover"
    assert E.cover_timing(params=p, price_over=6.0, cover_gain_pct=12.0, **kw) == "wait"
    # hazard 6.5% (> 6%) → copri: la fonte piu' prudente comanda
    assert E.cover_timing(params=p, **{**kw, "hazard": 0.065}) == "cover"


def test_settle_legs():
    legs = [
        fill(E.Leg(role="under_entry", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                   side="back", price=1.50, size=20.0)),
        fill(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                   side="back", price=8.0, size=4.0)),
    ]
    r = E.settle_legs(legs, 2, 0.05)
    assert r.per_leg[0][1] == "won" and r.per_leg[1][1] == "lost"
    assert r.net == pytest.approx(20 * 0.5 * 0.95 - 4, abs=0.01)
    r4 = E.settle_legs(legs, 4, 0.05)
    assert r4.net == pytest.approx(-24.0, abs=0.01)
    r5 = E.settle_legs(legs, 5, 0.05)
    assert r5.per_leg[1][1] == "won"
    assert r5.net == pytest.approx(4 * 7 * 0.95 - 20, abs=0.01)
    # gamba non abbinata: void, contributo 0
    legs.append(E.Leg(role="under_green", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                      side="lay", price=1.48, size=10.0, status="cancelled"))
    assert E.settle_legs(legs, 2, 0.05).per_leg[2][1] == "void"


# ---------------------------------------------------------------------------
# Macchina a stati: pre-match
# ---------------------------------------------------------------------------
def test_watch_before_window_does_nothing():
    ctx = E.MatchCtx()
    d = E.decide(ctx, snap(KO - 5 * H, u35=book(1.50)), params())
    assert d.state == "WATCH" and d.actions == []
    assert "finestra" in d.reason


def test_watch_entry_places_back_under():
    ctx = E.MatchCtx()
    s = snap(KO - 2 * H, u35=book(1.50, bs=50.0))
    d = E.decide(ctx, s, params())
    assert d.state == "PRE_ENTRY_PENDING"
    assert len(d.actions) == 1
    a = d.actions[0]
    assert (a.kind, a.role, a.market, a.selection, a.side) == (
        "place", "under_entry", E.MARKET_OU35, E.SEL_UNDER, "back")
    assert a.price == 1.50 and a.size == 10.0 and a.persistence == "LAPSE"
    E.apply_decision(ctx, d, s.now)
    assert ctx.state == "PRE_ENTRY_PENDING"
    assert len(ctx.legs) == 1 and ctx.legs[0].status == "pending"


@pytest.mark.parametrize("bb,bs,bl,reason", [
    (1.50, 5.0, 1.51, "liquidita"),      # size 5 < stake 10
    (1.20, 100.0, 1.21, "prezzo"),        # sotto price_min
    (1.50, 100.0, 1.60, "spread"),        # 1.50 -> 1.60 = 10 tick
])
def test_watch_entry_guards(bb, bs, bl, reason):
    d = E.decide(E.MatchCtx(), snap(KO - 2 * H, u35=book(bb, bs=bs, bl=bl)), params())
    assert d.state == "WATCH" and d.actions == []
    assert reason in d.reason


def test_watch_no_entry_when_feed_stale_or_disabled():
    d = E.decide(E.MatchCtx(), snap(KO - 2 * H, u35=book(1.50), feed_fresh=False), params())
    assert d.actions == [] and "feed" in d.reason
    d = E.decide(E.MatchCtx(), snap(KO - 2 * H, u35=book(1.50)), params(pre_enabled=False))
    assert d.actions == []


def test_entry_fill_places_resting_green():
    p = params(pre_exit_mode="resting", stake=20.0)
    ctx = E.MatchCtx()
    s0 = snap(KO - 2 * H, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    s1 = snap(KO - 2 * H + 5, u35=book(1.50))
    d = E.decide(ctx, s1, p)
    assert d.state == "PRE_OPEN"
    assert len(d.actions) == 1
    a = d.actions[0]
    assert (a.role, a.side, a.market, a.selection) == ("under_green", "lay", E.MARKET_OU35, E.SEL_UNDER)
    assert a.price == pytest.approx(1.48)
    assert a.size == pytest.approx(round(20 * 1.5 / 1.48, 2), abs=0.01)
    E.apply_decision(ctx, d, s1.now)
    assert ctx.entry_price_initial == 1.50
    assert ctx.state == "PRE_OPEN"


def test_entry_ttl_cancels_unmatched():
    ctx = E.MatchCtx()
    s0 = snap(KO - 2 * H, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, params()), s0.now)
    s1 = snap(KO - 2 * H + 61, u35=book(1.52))
    d = E.decide(ctx, s1, params())
    assert d.state == "WATCH"
    assert d.actions[0].kind == "cancel" and d.actions[0].ref == ctx.legs[0].ref


def _open_prematch(mode="resting"):
    """Ctx con entry 20@1.50 fillata e (in resting) green 1.48 appoggiata."""
    p = params(pre_exit_mode=mode, stake=20.0)
    ctx = E.MatchCtx()
    s0 = snap(KO - 2 * H, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0])
    s1 = snap(KO - 2 * H + 5, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s1, p), s1.now)
    return ctx, p


def test_resting_green_fill_completes_cycle():
    ctx, p = _open_prematch()
    fill(ctx.legs[1])
    s = snap(KO - 1.5 * H, u35=book(1.46))
    d = E.decide(ctx, s, p)
    assert d.state == "WATCH" and d.actions == []
    E.apply_decision(ctx, d, s.now)
    assert ctx.cycle_no == 1
    assert ctx.last_green_at == s.now
    cyc = d.telemetry["pre_cycle"]
    assert cyc["locked"] == pytest.approx(E.locked_pnl_back(20, 1.5, 1.48), abs=0.02)
    # cooldown: subito dopo niente nuovo ingresso
    d2 = E.decide(ctx, snap(s.now + 10, u35=book(1.46)), p)
    assert d2.actions == [] and "cooldown" in d2.reason
    d3 = E.decide(ctx, snap(s.now + 61, u35=book(1.46)), p)
    assert d3.state == "PRE_ENTRY_PENDING"


def test_taker_mode_closes_when_two_ticks_available():
    ctx, p = _open_prematch("taker")
    assert len(ctx.legs) == 1                       # nessuna resting
    d = E.decide(ctx, snap(KO - 1.5 * H, u35=book(1.47, bl=1.49)), p)
    assert d.actions == []                           # 1.49 > target 1.48
    d = E.decide(ctx, snap(KO - 1.5 * H, u35=book(1.47, bl=1.48)), p)
    assert d.state == "PRE_GREEN_PENDING"
    assert d.actions[0].side == "lay" and d.actions[0].price == pytest.approx(1.48)


def test_last_entry_in_profit_greens_then_places_persist():
    ctx, p = _open_prematch()
    s = snap(KO - 9 * 60, u35=book(1.44, bl=1.45))
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_GREEN_PENDING"
    kinds = [a.kind for a in d.actions]
    assert kinds == ["cancel", "place"]              # cancella resting, chiude taker
    assert d.actions[1].price == 1.45 and d.actions[1].final is True
    E.apply_decision(ctx, d, s.now)
    green = [l for l in ctx.legs if l.status == "pending"][-1]
    fill(green)
    s2 = snap(KO - 8 * 60, u35=book(1.44, bl=1.45))
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "PRE_LAST_ENTRY_PENDING"
    a = d2.actions[0]
    assert (a.role, a.side, a.persistence, a.price, a.size) == ("under_last", "back", "PERSIST", 1.44, 20.0)
    E.apply_decision(ctx, d2, s2.now)
    fill(ctx.legs[-1])
    d3 = E.decide(ctx, snap(KO + 30, u35=book(1.44, inplay=True), inplay=True, minute=0, goals=0), p)
    assert d3.state == "LIVE_UNCOVERED"


def test_last_entry_in_loss_holds_into_live():
    ctx, p = _open_prematch()
    s = snap(KO - 9 * 60, u35=book(1.54, bl=1.55))
    d = E.decide(ctx, s, p)
    assert d.state == "HOLD"
    assert [a.kind for a in d.actions] == ["cancel"]
    E.apply_decision(ctx, d, s.now)
    d2 = E.decide(ctx, snap(KO + 30, u35=book(1.54, inplay=True), inplay=True, minute=0, goals=0), p)
    assert d2.state == "LIVE_UNCOVERED"


def test_last_entry_persist_disabled_goes_idle_live():
    ctx, p = _open_prematch()
    p["last_entry_persist"] = False
    s = snap(KO - 9 * 60, u35=book(1.44, bl=1.45))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.status == "pending"][-1])
    d = E.decide(ctx, snap(KO - 8 * 60, u35=book(1.44)), p)
    assert d.state == "IDLE_LIVE" and d.actions == []


def test_unmatched_persist_cancelled_after_ko_grace():
    ctx, p = _open_prematch()
    s = snap(KO - 9 * 60, u35=book(1.44, bl=1.45))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    fill([l for l in ctx.legs if l.status == "pending"][-1])
    s2 = snap(KO - 8 * 60, u35=book(1.44))
    E.apply_decision(ctx, E.decide(ctx, s2, p), s2.now)
    last = ctx.legs[-1]
    last.matched = 10.0; last.avg_price = 1.44; last.status = "pending"   # meta' abbinata
    d = E.decide(ctx, snap(KO + 130, u35=book(1.44, inplay=True), inplay=True, minute=2, goals=0), p)
    assert any(a.kind == "cancel" and a.ref == last.ref for a in d.actions)
    assert d.state == "LIVE_UNCOVERED"


# ---------------------------------------------------------------------------
# Macchina a stati: live
# ---------------------------------------------------------------------------
def _live_uncovered():
    p = params()
    ctx = E.MatchCtx(state="LIVE_UNCOVERED", entry_price_initial=1.50)
    ctx.legs.append(fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                               side="back", price=1.50, size=20.0, persistence="PERSIST")))
    return ctx, p


def test_live_cover_wait_then_cover():
    ctx, p = _live_uncovered()
    s = snap(KO + 300, u35=book(1.45, inplay=True), o45=book(6.0, bs=50, inplay=True),
             inplay=True, minute=5, goals=0, hazard=0.05, p4_market=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_UNCOVERED" and d.actions == []
    assert d.telemetry["cover_wait"]["x_now"] == pytest.approx(E.cover_size(20, 6.0, 0.05, 1.2), abs=1e-6)
    # quota Over gia' buona (>= 7): si copre subito anche con hazard basso
    s_good = snap(KO + 300, u35=book(1.45, inplay=True), o45=book(8.0, bs=50, inplay=True),
                  inplay=True, minute=5, goals=0, hazard=0.05, p4_market=0.12)
    assert E.decide(ctx, s_good, p).state == "LIVE_COVER_PENDING"
    s2 = snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(9.0, bs=50, inplay=True),
              inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "LIVE_COVER_PENDING"
    a = d2.actions[0]
    assert (a.role, a.market, a.selection, a.side, a.price) == ("over_cover", E.MARKET_OU45, E.SEL_OVER, "back", 9.0)
    x = E.cover_size(20, 9.0, 0.05, 1.2)
    assert a.size == round(x, 2)                      # importo ESATTO (exact_sizes)
    assert E.needs_submin("back", a.size) is True     # 3.16: fuori passo 0.50 -> place-and-trim
    assert E.needs_submin("back", 2.5) is False and E.needs_submin("back", 1.23) is True
    assert E.needs_submin("lay", 1.23) is False
    E.apply_decision(ctx, d2, s2.now)
    fill(ctx.legs[-1])
    d3 = E.decide(ctx, s2, p)
    assert d3.state == "LIVE_COVERED"


def test_live_cover_skipped_when_too_many_goals():
    ctx, p = _live_uncovered()
    s = snap(KO + 40 * 60, u35=book(3.0, inplay=True), o45=book(2.0, inplay=True),
             inplay=True, minute=40, goals=3, hazard=0.1, p4_market=0.3)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []
    assert d.updates.get("cover_skipped") is True


def _live_covered():
    ctx, p = _live_uncovered()
    ctx.state = "LIVE_COVERED"
    ctx.legs.append(fill(E.Leg(role="over_cover", market=E.MARKET_OU45, selection=E.SEL_OVER,
                               side="back", price=8.0, size=4.0)))
    return ctx, p


def test_live_global_cashout_at_profit():
    ctx, p = _live_covered()
    # Under scesa a 1.30 (lay 1.31): W=10 L=-20 -> locked = -20 + 30/1.31 = 2.90 ; Over 4.5 salita a 12 (lay 12.5):
    # W=28 L=-4 -> locked = -4 + 32/12.5 = -1.44 -> netto = 2.90*0.95 - 1.44 = 1.31 -> 5.5% di 24
    s = snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True), o45=book(12.0, bl=12.5, inplay=True),
             inplay=True, minute=30, goals=0)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING"
    assert d.reason.startswith("profit")
    roles = sorted(a.role for a in d.actions)
    assert roles == ["over_close", "under_close"]
    for a in d.actions:
        assert a.kind == "place" and a.side == "lay"
    assert d.telemetry["cashout"]["net"] == pytest.approx(1.31, abs=0.05)
    E.apply_decision(ctx, d, s.now)
    for l in ctx.legs:
        if l.status == "pending":
            fill(l)
    d2 = E.decide(ctx, s, p)
    assert d2.state == "FLAT"
    E.apply_decision(ctx, d2, s.now)
    assert ctx.reentry_allowed is True


def test_live_no_cashout_below_threshold():
    ctx, p = _live_covered()
    s = snap(KO + 10 * 60, u35=book(1.44, bl=1.45, inplay=True), o45=book(8.0, bl=8.2, inplay=True),
             inplay=True, minute=10, goals=0)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []


def test_ht_loss_tolerated_exit():
    ctx, p = _live_covered()
    # 2 gol al 45': Under 3.5 a 2.2 (lay 2.24): locked = -20 + 30/2.24 = -6.61 ; Over 4.5 a 6 (lay 6.2): locked = -4 + 32/6.2 = 1.16*0.95
    # netto ~ -5.5 su base 24 = -23% -> entro il 25% -> chiudi
    s = snap(KO + 46 * 60, u35=book(2.20, bl=2.24, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
             inplay=True, minute=45, goals=2, ht_active=True)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("loss")
    # perdita oltre soglia -> tieni
    s2 = snap(KO + 46 * 60, u35=book(3.0, bl=3.1, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
              inplay=True, minute=45, goals=2, ht_active=True)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "LIVE_COVERED" and d2.actions == []
    # 2T stessa regola dal minuto h2_loss_from_min
    s3 = snap(KO + 60 * 60, u35=book(2.20, bl=2.24, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
              inplay=True, minute=60, goals=2)
    assert E.decide(ctx, s3, p).state == "LIVE_CLOSING"
    # con 1 gol la regola non si applica
    s4 = snap(KO + 46 * 60, u35=book(2.20, bl=2.24, inplay=True), o45=book(6.0, bl=6.2, inplay=True),
              inplay=True, minute=45, goals=1, ht_active=True)
    assert E.decide(ctx, s4, p).state == "LIVE_COVERED"


def test_closing_retry_replaces_unmatched_leg():
    ctx, p = _live_covered()
    s = snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True), o45=book(12.0, bl=12.5, inplay=True),
             inplay=True, minute=30, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    pend = [l for l in ctx.legs if l.status == "pending"]
    fill(pend[0])                                            # una gamba fillata, l'altra no
    s2 = snap(s.now + 11, u35=book(1.30, bl=1.32, inplay=True), o45=book(12.0, bl=13.0, inplay=True),
              inplay=True, minute=31, goals=0)
    d = E.decide(ctx, s2, p)
    assert d.state == "LIVE_CLOSING"
    kinds = [a.kind for a in d.actions]
    assert kinds == ["cancel", "place"]
    assert d.actions[1].role == pend[1].role


def test_reentry_after_profit_close():
    p = params()
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)
    s = snap(KO + 30 * 60, u35=book(2.5, inplay=True), o45=book(5.0, inplay=True),
             u45=book(1.60, bs=50, inplay=True), inplay=True, minute=30, goals=1)
    d = E.decide(ctx, s, p)
    assert d.state == "REENTRY_PENDING"
    a = d.actions[0]
    assert (a.role, a.market, a.selection, a.side, a.price, a.size) == (
        "reentry", E.MARKET_OU45, E.SEL_UNDER, "back", 1.60, 10.0)
    E.apply_decision(ctx, d, s.now)
    fill(ctx.legs[-1])
    d2 = E.decide(ctx, s, p)
    assert d2.state == "REENTRY_OPEN"
    assert d2.actions[0].role == "reentry_green" and d2.actions[0].price == pytest.approx(1.58)
    E.apply_decision(ctx, d2, s.now)
    fill(ctx.legs[-1])
    d3 = E.decide(ctx, s, p)
    assert d3.state == "FLAT"
    E.apply_decision(ctx, d3, s.now)
    assert ctx.reentry_done is True
    assert E.decide(ctx, s, p).actions == []               # una sola volta


def test_reentry_guards():
    p = params()
    base = dict(u35=book(2.5, inplay=True), o45=book(5.0, inplay=True), inplay=True)
    # quota U4.5 non superiore alla quota iniziale U3.5
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)
    d = E.decide(ctx, snap(KO + 30 * 60, u45=book(1.45, inplay=True), minute=30, goals=1, **base), p)
    assert d.actions == []
    # senza chiusura in profitto
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=False)
    d = E.decide(ctx, snap(KO + 30 * 60, u45=book(1.60, inplay=True), minute=30, goals=1, **base), p)
    assert d.actions == []
    # oltre il minuto limite
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)
    d = E.decide(ctx, snap(KO + 50 * 60, u45=book(1.60, inplay=True), minute=50, goals=1, **base), p)
    assert d.actions == []
    # 2 gol: linea 5.5 non sottoscritta
    d = E.decide(ctx, snap(KO + 30 * 60, u45=book(1.60, inplay=True), minute=30, goals=2, **base), p)
    assert d.actions == []


def test_reentry_open_closes_at_market_after_limit_minute():
    p = params()
    ctx = E.MatchCtx(state="REENTRY_OPEN", entry_price_initial=1.50, reentry_allowed=True)
    ctx.legs.append(fill(E.Leg(role="reentry", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                               side="back", price=1.60, size=10.0)))
    ctx.legs.append(E.Leg(role="reentry_green", market=E.MARKET_OU45, selection=E.SEL_UNDER,
                          side="lay", price=1.58, size=20.25, ref="g1"))
    s = snap(KO + 81 * 60, u45=book(1.70, bl=1.72, inplay=True), inplay=True, minute=81, goals=1)
    d = E.decide(ctx, s, p)
    assert d.state == "REENTRY_GREEN_PENDING"
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    assert d.actions[1].price == 1.72


# ---------------------------------------------------------------------------
# Settlement e chiusura mercato
# ---------------------------------------------------------------------------
def test_market_closed_settles():
    ctx, p = _live_covered()
    ctx.legs.append(E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER,
                          side="lay", price=1.3, size=5.0, ref="x"))
    s = snap(KO + 95 * 60, inplay=True, minute=90, goals=2, market_status="CLOSED", final_total=None)
    d = E.decide(ctx, s, p)
    assert d.state == "SETTLING"
    assert d.actions[0].kind == "cancel" and d.actions[0].ref == "x"
    E.apply_decision(ctx, d, s.now)
    s2 = snap(KO + 96 * 60, inplay=True, minute=90, goals=2, market_status="CLOSED", final_total=2)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "SETTLED"
    assert d2.updates["settled_pnl"] == pytest.approx(20 * 0.5 * 0.95 - 4, abs=0.01)


def test_skipped_and_error_are_terminal():
    p = params()
    for st in ("SKIPPED", "ERROR", "SETTLED"):
        d = E.decide(E.MatchCtx(state=st), snap(KO - H, u35=book(1.5)), p)
        assert d.state == st and d.actions == []


def test_force_flat_plan_closes_every_open_selection():
    ctx, p = _live_covered()
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.40, bl=1.41), (E.MARKET_OU45, E.SEL_OVER): book(9.0, bl=9.4)}
    actions = E.force_flat_actions(ctx, books, p)
    assert sorted(a.role for a in actions) == ["over_close", "under_close"]
    assert all(a.side == "lay" for a in actions)


# ---------------------------------------------------------------------------
# Regressioni dalla code review F0
# ---------------------------------------------------------------------------
def test_closing_retry_includes_partially_matched_leg():
    """CRITICAL #1: il riprezzo di una chiusura parzialmente abbinata deve
    dimensionare SOLO il residuo (mai raddoppiare la copertura)."""
    ctx, p = _live_covered()
    s = snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True), o45=book(12.0, bl=12.5, inplay=True),
             inplay=True, minute=30, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    under_close = [l for l in ctx.legs if l.role == "under_close"][0]
    over_close = [l for l in ctx.legs if l.role == "over_close"][0]
    fill(over_close)
    # meta' della lay Under abbinata, il resto ancora sul book (pending)
    under_close.matched = round(under_close.size / 2, 2)
    under_close.avg_price = under_close.price
    s2 = snap(s.now + 11, u35=book(1.30, bl=1.32, inplay=True), o45=book(12.0, bl=13.0, inplay=True),
              inplay=True, minute=31, goals=0)
    d = E.decide(ctx, s2, p)
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    new = d.actions[1]
    # residuo: W/L dopo la meta' gia' abbinata -> lay size ~ (10 - matched*(1.31-1)) ...
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert new.size == pytest.approx(round((w - l) / 1.32, 2), abs=0.02)
    assert new.size < under_close.size            # mai la size intera di nuovo


def test_archived_cycles_do_not_inflate_open_capital():
    """CRITICAL #2: dopo N cicli chiusi in green, S/invested contano SOLO il ciclo vivo."""
    ctx, p = _open_prematch("resting")          # ciclo 0: entry 20@1.50 + green resting
    fill(ctx.legs[1])
    s = snap(KO - 1.5 * H, u35=book(1.46))
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)   # ciclo chiuso -> archiviato
    assert all(l.archived for l in ctx.legs)
    assert E.invested(ctx.legs) == 0.0
    assert E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER) == (0.0, 0.0)
    # ciclo 1
    s1 = snap(s.now + 61, u35=book(1.46))
    E.apply_decision(ctx, E.decide(ctx, s1, p), s1.now)
    fill(ctx.legs[-1])
    S, Pe = E.position(ctx.legs, E.MARKET_OU35, E.SEL_UNDER, ("under_entry", "under_last"))
    assert S == 20.0 and Pe == 1.46                     # non 40
    # la contabilita' storica resta intera: settle include il ciclo archiviato
    r = E.settle_legs(ctx.legs, 2, 0.0)
    assert len(r.per_leg) == 3
    assert r.net == pytest.approx(E.locked_pnl_back(20, 1.5, 1.48) + 20 * 0.46, abs=0.03)


def test_liability_cap_blocks_entry_cover_and_reentry():
    p = params(max_liability_per_match=25.0, stake=20.0)
    # ingresso ok (20 <= 25)
    d = E.decide(E.MatchCtx(), snap(KO - 2 * H, u35=book(1.50, bs=50.0)), p)
    assert d.state == "PRE_ENTRY_PENDING"
    # copertura clampata al residuo (25 - 20 = 5)
    ctx, _ = _live_uncovered()
    s = snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(3.0, bs=50, inplay=True),
             inplay=True, minute=20, goals=0, hazard=0.2, p4_market=0.2)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVER_PENDING" and d.actions[0].size == 5.0
    # senza spazio: copertura saltata
    p2 = params(max_liability_per_match=20.0, stake=20.0)
    d = E.decide(ctx, s, p2)
    assert d.state == "LIVE_COVERED" and d.updates.get("cover_skipped") is True
    # re-ingresso bloccato dal cap (posizione flat, stake 20 > tetto 5)
    p3 = params(max_liability_per_match=5.0, stake=20.0)
    ctx = E.MatchCtx(state="FLAT", entry_price_initial=1.50, reentry_allowed=True)
    d = E.decide(ctx, snap(KO + 30 * 60, u45=book(1.60, bs=50, inplay=True), inplay=True, minute=30, goals=1), p3)
    assert d.state == "FLAT" and "cap" in d.reason


def test_closing_attempts_exhausted_is_reported():
    ctx, p = _live_covered()
    s = snap(KO + 30 * 60, u35=book(1.30, bl=1.31, inplay=True), o45=book(12.0, bl=12.5, inplay=True),
             inplay=True, minute=30, goals=0)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    ctx.attempts = int(p["close_max_attempts"])
    d = E.decide(ctx, snap(s.now + 60, u35=book(1.30, bl=1.31, inplay=True),
                           o45=book(12.0, bl=12.5, inplay=True), inplay=True, minute=31, goals=0), p)
    assert d.state == "LIVE_CLOSING" and d.actions == []
    assert d.telemetry.get("close_retries_exhausted") is True


# ---------------------------------------------------------------------------
# CERTIFICAZIONE FILL PARZIALI: il lato opposto e' sempre dimensionato sull'esposizione REALE
# ---------------------------------------------------------------------------
def test_partial_entry_fill_sizes_green_on_matched_only():
    p = params(pre_exit_mode="resting", stake=10.0)
    ctx = E.MatchCtx()
    s0 = snap(KO - 2 * H, u35=book(1.50))
    E.apply_decision(ctx, E.decide(ctx, s0, p), s0.now)
    fill(ctx.legs[0], size=6.0)                       # 6 su 10 abbinati, residuo ritirato
    d = E.decide(ctx, snap(KO - 2 * H + 5, u35=book(1.50)), p)
    g = d.actions[0]
    assert g.role == "under_green" and g.price == pytest.approx(1.48)
    assert g.size == pytest.approx(round(6 * 1.5 / 1.48, 2), abs=0.01)     # 6.08, NON 10.14
    E.apply_decision(ctx, d, s0.now + 5)
    fill(ctx.legs[-1])
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert abs(w - l) < 0.011 and w == pytest.approx(E.locked_pnl_back(6, 1.5, 1.48), abs=0.011)


def test_partial_resting_green_never_closes_cycle_and_reposts_residual():
    ctx, p = _open_prematch("resting")
    green = ctx.legs[1]
    # 4 € su 10.14 abbinati, poi ordine ritirato (es. dall'utente): NON e' un ciclo chiuso
    green.matched = 4.0; green.avg_price = 1.48; green.status = "open"
    s = snap(KO - 1.5 * H, u35=book(1.50))
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_OPEN"
    assert d.actions and d.actions[0].role == "under_green" and d.actions[0].side == "lay"
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert d.actions[0].size == pytest.approx(round((w - l) / 1.48, 2), abs=0.01)   # solo il residuo
    assert d.actions[0].size == pytest.approx(20.27 - 4.0, abs=0.02)     # stake 20: green 20.27
    E.apply_decision(ctx, d, s.now)
    assert not any(l.archived for l in ctx.legs)       # nulla archiviato con esposizione aperta
    fill(ctx.legs[-1])
    d2 = E.decide(ctx, snap(s.now + 2, u35=book(1.50)), p)
    assert d2.state == "WATCH"                          # ora e' piatta: ciclo chiuso
    assert d2.telemetry["pre_cycle"]["locked"] == pytest.approx(E.locked_pnl_back(20, 1.5, 1.48), abs=0.03)


def test_last_entry_with_partial_green_uses_net_exposure():
    ctx, p = _open_prematch("resting")
    green = ctx.legs[1]
    green.matched = 5.0; green.avg_price = 1.48; green.status = "pending"    # meta' abbinata, ancora viva
    s = snap(KO - 9 * 60, u35=book(1.44, bl=1.45))
    d = E.decide(ctx, s, p)
    assert d.state == "PRE_GREEN_PENDING"
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    w, l = E.exposure(ctx.legs, E.MARKET_OU35, E.SEL_UNDER)
    assert d.actions[1].size == pytest.approx(round((w - l) / 1.45, 2), abs=0.01)
    assert d.actions[1].size < 20.0                     # solo il residuo (stake 20, 5 gia' coperti)


def test_partial_cover_reprice_uses_exact_residual():
    ctx, p = _live_uncovered()
    s = snap(KO + 20 * 60, u35=book(1.35, inplay=True), o45=book(8.0, bs=50, inplay=True),
             inplay=True, minute=20, goals=0, hazard=0.05, p4_market=0.12)
    E.apply_decision(ctx, E.decide(ctx, s, p), s.now)
    cover = ctx.legs[-1]
    x_full = E.cover_size(20, 8.0, 0.05, 1.2)
    assert cover.size == pytest.approx(round(x_full, 2))
    cover.matched = 1.0; cover.avg_price = 8.0          # 1 € abbinato a 8.0, resto sul book
    s2 = snap(s.now + 11, u35=book(1.35, inplay=True), o45=book(6.0, bs=50, inplay=True),
              inplay=True, minute=21, goals=0)
    d = E.decide(ctx, s2, p)
    assert [a.kind for a in d.actions] == ["cancel", "place"]
    resid = E.cover_size_residual(20, 6.0, 0.05, 1.2, matched=1.0, matched_price=8.0)
    assert d.actions[1].size == pytest.approx(round(resid, 2))
    # verifica del target: con 5+ gol il netto e' esattamente +20% dello stake Under
    net_if_over = 1.0 * 7 * 0.95 + resid * 5 * 0.95 - 20
    assert net_if_over == pytest.approx(4.0, abs=1e-6)


def test_partial_close_settles_on_matched_sizes():
    legs = [
        fill(E.Leg(role="under_last", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="back", price=1.5, size=10.0)),
        E.Leg(role="under_close", market=E.MARKET_OU35, selection=E.SEL_UNDER, side="lay", price=1.3, size=11.54,
              matched=5.0, avg_price=1.3, status="open"),
    ]
    r = E.settle_legs(legs, 2, 0.05)          # Under vince: back +5, lay parziale -1.5 → netto (5-1.5)*0.95
    assert r.net == pytest.approx((5.0 - 1.5) * 0.95, abs=0.01)
    r4 = E.settle_legs(legs, 4, 0.05)         # Under perde: -10 + 5 (lay vinta) → -5
    assert r4.net == pytest.approx(-5.0, abs=0.01)


# ---------------------------------------------------------------------------
# Cash-out INTELLIGENTE (chiude prima della soglia quando tenere non vale il rischio)
# ---------------------------------------------------------------------------
# Posizione di riferimento (_live_covered): Under 3.5 20 @ 1.50 + Over 4.5 4 @ 8.0, base 24.
# Book "quasi in soglia": Under lay 1.33 -> locked -20 + 30/1.33 = 2.556*0.95 = 2.43 ;
# Over lay 12.5 -> -1.44 ; netto ~ 0.99 = 4.1% (soglia 5% = 1.20, min 2% = 0.48, tolleranza 2% -> vicino da 0.72)
_NEAR = dict(u35=book(1.32, bl=1.33, inplay=True), o45=book(12.0, bl=12.5, inplay=True))
# Book "sopra il minimo ma lontano": Under lay 1.40 -> (-20+30/1.40)*0.95 = 1.357 ; Over -1.44 -> netto -0.08 -> sotto il minimo
_LOW = dict(u35=book(1.39, bl=1.40, inplay=True), o45=book(12.0, bl=12.5, inplay=True))


def _model_probs(u35_now, u35_goal, u35_later, o45_now, o45_goal, o45_later):
    return {"u35_now": u35_now, "u35_goal": u35_goal, "u35_later": u35_later,
            "o45_now": o45_now, "o45_goal": o45_goal, "o45_later": o45_later,
            "u45_now": 1 - o45_now, "u45_goal": 1 - o45_goal, "u45_later": 1 - o45_later}


def test_smart_cashout_near_threshold_and_hot_phase_closes():
    ctx, p = _live_covered()
    s = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=0, hazard=0.12)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING" and d.reason.startswith("profit smart")
    assert d.telemetry["cashout"]["smart"]["trigger"] == "hot_near"
    assert d.updates["close_reason"] == "profit"          # re-ingresso permesso come un profit pieno
    assert sorted(a.role for a in d.actions) == ["over_close", "under_close"]
    # stessa cosa con la PRESSIONE (corner/cartellini) anche se l'hazard e' basso
    s2 = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=0, hazard=0.04, pressure=1.2)
    assert E.decide(ctx, s2, p).telemetry["cashout"]["smart"]["trigger"] == "hot_near"


def test_smart_cashout_holds_when_calm_without_model():
    ctx, p = _live_covered()
    s = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=0, hazard=0.04)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []
    st = d.telemetry["cashout"]["smart"]
    assert st["near"] is True and st["hot"] is False and "trigger" not in st


def test_smart_cashout_never_below_min_profit():
    ctx, p = _live_covered()
    # fase caldissima e 3 gol, ma il valore e' sotto il profitto minimo: si tiene
    # (al 30': la regola 2T di perdita tollerata non e' ancora attiva)
    s = snap(KO + 30 * 60, **_LOW, inplay=True, minute=30, goals=3, hazard=0.3, pressure=1.25)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []


def test_smart_cashout_hot_score_closes_at_min_profit():
    ctx, p = _live_covered()
    # 3 gol: il prossimo e' il 4o -> chiude appena sopra il minimo anche lontano dalla soglia
    # Under lay 1.42 -> (-20+30/1.42)*0.95 = 1.07 ; Over lay 9.0 -> -4 + 32/9 = -0.44 -> netto 0.63 = 2.6%
    # (sopra il minimo 2%, sotto la zona "vicino" 3%): chiude SOLO per il punteggio caldo
    s = snap(KO + 30 * 60, u35=book(1.41, bl=1.42, inplay=True), o45=book(8.8, bl=9.0, inplay=True),
             inplay=True, minute=30, goals=3, hazard=0.02)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_CLOSING" and d.telemetry["cashout"]["smart"]["trigger"] == "goals_hot"


def test_smart_cashout_expected_value_of_waiting():
    ctx, p = _live_covered()
    # modello: un gol dimezza P(Under 3.5) e raddoppia P(Over 4.5); aspettare 5' senza gol migliora poco
    mp = _model_probs(0.80, 0.40, 0.86, 0.06, 0.13, 0.05)
    # hazard alto ma sotto la soglia "calda" (0.10): decide il valore atteso
    s = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=0, hazard=0.09, model_probs=mp)
    d = E.decide(ctx, s, p)
    st = d.telemetry["cashout"]["smart"]
    assert st["cv_goal"] < 0 < st["cv_later"]
    assert st["ev_hold"] < d.telemetry["cashout"]["net"]
    assert d.state == "LIVE_CLOSING" and st["trigger"] == "ev_near"
    # partita tranquilla (hazard 1%): aspettare vale di piu' -> si tiene
    s2 = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=0, hazard=0.01, model_probs=mp)
    d2 = E.decide(ctx, s2, p)
    assert d2.state == "LIVE_COVERED" and d2.telemetry["cashout"]["smart"]["ev_hold"] > d2.telemetry["cashout"]["net"]


def test_smart_cashout_disabled_keeps_plain_rule():
    ctx, p = _live_covered()
    p["cashout_smart_enabled"] = False
    s = snap(KO + 30 * 60, **_NEAR, inplay=True, minute=30, goals=3, hazard=0.5, pressure=1.25)
    d = E.decide(ctx, s, p)
    assert d.state == "LIVE_COVERED" and d.actions == []
    assert d.telemetry["cashout"]["smart"] == {"enabled": False}


def test_projected_books_scale_market_prices_by_model_ratio():
    books = {(E.MARKET_OU35, E.SEL_UNDER): book(1.30, bl=1.32), (E.MARKET_OU45, E.SEL_OVER): book(10.0, bl=11.0)}
    mp = _model_probs(0.80, 0.40, 0.82, 0.06, 0.12, 0.05)
    g = E.projected_books(books, mp, "goal")
    assert g[(E.MARKET_OU35, E.SEL_UNDER)].best_lay == pytest.approx(1.32 * 2.0)
    assert g[(E.MARKET_OU45, E.SEL_OVER)].best_lay == pytest.approx(11.0 * 0.5)
    lt = E.projected_books(books, mp, "later")
    assert lt[(E.MARKET_OU35, E.SEL_UNDER)].best_lay == pytest.approx(1.32 * 0.80 / 0.82)
    # selezione morta -> quota 1000 ; dato mancante -> None
    dead = dict(mp, u35_goal=0.0)
    assert E.projected_books(books, dead, "goal")[(E.MARKET_OU35, E.SEL_UNDER)].best_lay == 1000.0
    assert E.projected_books(books, {"u35_now": 0.8}, "goal") is None
    assert E.projected_books(books, None, "goal") is None
