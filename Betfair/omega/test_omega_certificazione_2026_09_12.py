"""Certificazione chirurgica 12/09/2026 — motore, modello, mercato, config di Omega.

Ogni test qui è o la regressione di un difetto corretto oggi (C-xx) o la
certificazione esplicita di una proprietà money-critical che il brief chiede di
verificare (scala tick Betfair, segni del P&L, cap di liability, probabilità in
[0, 1], NaN/valori mancanti, fusi orari).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from Betfair.omega import omega_config as C
from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_model as MO


# ---------------------------------------------------------------------------
# Scala tick Betfair (1.01-2 0.01, 2-3 0.02, 3-4 0.05, 4-6 0.1, 6-10 0.2,
# 10-20 0.5, 20-30 1, 30-50 2, 50-100 5, 100-1000 10) — certificazione completa
# ---------------------------------------------------------------------------
_BANDS = ((1.01, 2.0, 0.01), (2.0, 3.0, 0.02), (3.0, 4.0, 0.05), (4.0, 6.0, 0.10),
          (6.0, 10.0, 0.20), (10.0, 20.0, 0.50), (20.0, 30.0, 1.0), (30.0, 50.0, 2.0),
          (50.0, 100.0, 5.0), (100.0, 1000.0, 10.0))


def _all_ticks() -> list[float]:
    out: list[float] = []
    for lo, hi, step in _BANDS:
        n = int(round((hi - lo) / step))
        out += [round(lo + i * step, 2) for i in range(n)]
    out.append(1000.0)
    return out


def test_ogni_tick_valido_e_punto_fisso_e_tick_up_down_coerenti():
    ticks = _all_ticks()
    assert len(ticks) == 350
    for t in ticks:
        assert E.round_to_tick(t) == t
        assert E.tick_up(t) == t and E.tick_down(t) == t
    # fra due tick consecutivi: down = il precedente, up = il successivo,
    # round = il più vicino (bordo di banda incluso)
    for a, b in zip(ticks, ticks[1:]):
        mid = a + (b - a) * 0.3
        assert E.tick_down(mid) == a and E.tick_up(mid) == b
        assert E.round_to_tick(mid) == a
        assert E.round_to_tick(a + (b - a) * 0.7) == b


def test_tick_clamp_estremi():
    assert E.round_to_tick(0.5) == 1.01 and E.tick_up(1.0) == 1.01
    assert E.round_to_tick(5000) == 1000.0 and E.tick_down(1e9) == 1000.0


def test_c01_prezzo_non_finito_non_e_arrotondabile():
    """C-01: prima ``round_to_tick(nan)`` ritornava NaN in silenzio (→ prezzo
    dell'ordine indefinito). Ora solleva."""
    with pytest.raises(ValueError):
        E.round_to_tick(float("nan"))
    with pytest.raises(ValueError):
        E.tick_up(float("inf"))


def test_c01_select_lay_runner_ignora_prezzo_nan():
    runners = [E.ScoreRunner(1, "2 - 1", lay_price=float("nan"), lay_size=100),
               E.ScoreRunner(2, "3 - 1", lay_price=60.0, lay_size=100)]
    sel = E.select_lay_runner(runners, price_min=20, price_max=120, min_liquidity=5, include_aggregate=False)
    assert sel is not None and sel.selection_id == 2


def test_c01_select_by_model_ignora_prezzo_nan():
    state = MO.LiveState(minute=60, score_home=0, score_away=0)
    probs = {(2, 1): 0.005, (3, 1): 0.004}
    runners = [E.ScoreRunner(1, "2 - 1", lay_price=float("nan"), lay_size=100),
               E.ScoreRunner(2, "3 - 1", lay_price=80.0, lay_size=100)]
    sel = MO.select_by_model(runners, probs, state=state, price_min=20, price_max=120,
                             min_liquidity=5, p_max=0.02)
    assert sel is not None and sel.selection_id == 2


# ---------------------------------------------------------------------------
# Matematica §2: stake, liability, segni P&L, commissione solo sul netto vincente
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("price", [1.5, 2.02, 3.05, 21.0, 55.0, 110.0, 1000.0])
def test_liability_e_pnl_lay_su_tick_reali(price):
    size = 5.26
    liab = E.liability_from_lay(size, price)
    assert liab == pytest.approx(round(size * (price - 1.0), 2), abs=1e-9)
    st, pnl = E.settle_pnl(our_selection_id=1, winner_selection_id=1, size=size, price=price, commission=0.05)
    assert st == "lost" and pnl == -liab                      # lay PERSO: −liability, mai commissione
    st, pnl = E.settle_pnl(our_selection_id=1, winner_selection_id=2, size=size, price=price, commission=0.05)
    assert st == "won" and pnl == pytest.approx(size * 0.95, abs=0.005)   # lay VINTO: stake netto 5 %


def test_pnl_back_segni_e_commissione():
    st, pnl = E.settle_pnl(our_selection_id=1, winner_selection_id=1, size=10.0, price=4.0,
                           commission=0.05, side="back")
    assert st == "won" and pnl == pytest.approx(10.0 * 3.0 * 0.95)
    st, pnl = E.settle_pnl(our_selection_id=1, winner_selection_id=2, size=10.0, price=4.0,
                           commission=0.05, side="back")
    assert st == "lost" and pnl == -10.0                       # back perso: −stake, nessuna commissione


def test_stake_da_target_incassa_il_target_netto():
    """s = target/(1-c), MA lo stake minimo Betfair.it vince sempre sul target.

    Certificazione 12/09: la prima stesura pretendeva ``netto == target`` anche
    per un target sotto il minimo (0,37 EUR -> s=0,39 -> clamp a 0,50 -> netto
    0,47). Ha ragione il CODICE: sotto il minimo l'unica alternativa a incassare
    un po' PIU' del target sarebbe piazzare una size non accettata dall'exchange.
    Il contratto money-critical e' quindi: mai MENO del target, e mai piu' del
    minimo tecnico quando il target e' irraggiungibile per difetto.
    """
    min_stake = 0.5
    for target in (0.37, 3.5, 7.49, 12.0):
        s = E.lay_size_from_target(target, commission=0.05, min_stake=min_stake)
        assert s >= min_stake
        netto = E.net_profit_if_win(s, 0.05)
        if s > min_stake:                      # target raggiungibile: incasso esatto
            assert netto == pytest.approx(target, abs=0.01)
        else:                                  # target sotto il minimo: mai meno del target
            assert netto >= target
            assert netto == pytest.approx(min_stake * 0.95, abs=0.01)
    assert E.lay_size_from_target(-3, commission=0.05, min_stake=min_stake) == 0.0


def test_cap_liability_mai_superato_su_tutta_la_scala():
    for price in _all_ticks()[::7]:
        for cap in (1.0, 12.34, 200.0):
            s = E.apply_liability_cap(50.0, price, cap)
            assert s >= 0.0
            assert E.liability_from_lay(s, price) <= cap + 1e-9
    assert E.apply_liability_cap(5.0, 1.0, 10.0) == 5.0        # prezzo 1.0: nessuna liability, invariato


# ---------------------------------------------------------------------------
# PAPER = LIVE senza soldi (C-02)
# ---------------------------------------------------------------------------
def test_c02_paper_fill_senza_ladder_non_regala_nulla():
    assert E.paper_fill(5.0, best_price=110.0, lay_ladder=()) is None
    # con la ladder del feed (best + size) il fill è cappato dalla size REALE
    f = E.paper_fill(5.0, best_price=110.0, lay_ladder=((110.0, 2.0),), limit_price=110.0)
    assert f is not None and f.matched_size == 2.0 and not f.fully_matched
    # e mai oltre il prezzo limite (lay: mai più ALTO)
    f = E.paper_fill(5.0, best_price=110.0, lay_ladder=((110.0, 2.0), (120.0, 50.0)), limit_price=110.0)
    assert f is not None and f.matched_size == 2.0


# ---------------------------------------------------------------------------
# Riconciliazione (C-03)
# ---------------------------------------------------------------------------
def _pending():
    return {"id": 7, "event_id": "1.100", "market_id": "m1", "selection_id": 4,
            "side": "lay", "price": 110, "size": 5, "placed_at": "2026-07-12T15:00:00+00:00"}


def test_c03_ordine_completo_a_zero_libera_la_riserva():
    """C-03: EXECUTION_COMPLETE con 0 abbinato e 0 residuo (FOK ucciso) restava
    'keep' per sempre. Ora 'free'; un EXECUTABLE senza fill resta 'keep'."""
    now = "2026-07-12T16:00:00+00:00"
    dead = [{"customer_order_ref": "omega-t7", "status": "EXECUTION_COMPLETE",
             "size_matched": 0.0, "size_remaining": 0.0, "bet_id": "bX"}]
    assert E.reconcile_decision(_pending(), dead, [], now)["action"] == "free"
    alive = [{"customer_order_ref": "omega-t7", "status": "EXECUTABLE",
              "size_matched": 0.0, "size_remaining": 5.0, "bet_id": "bY"}]
    assert E.reconcile_decision(_pending(), alive, [], now)["action"] == "keep"
    # stato ignoto (fake senza 'status') → prudente: keep
    unknown = [{"customer_order_ref": "omega-t7", "size_matched": 0.0, "size_remaining": 0.0}]
    assert E.reconcile_decision(_pending(), unknown, [], now)["action"] == "keep"


# ---------------------------------------------------------------------------
# Fusi orari (C-04): universo "eventi di oggi" = giornata Europe/Rome
# ---------------------------------------------------------------------------
def test_c04_day_end_utc_ora_legale_solare_e_cambio_ora():
    # estate: 15/07 10:00Z → fine giornata Rome = 16/07 00:00 CEST = 15/07 22:00Z
    assert E.day_end_utc(datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)) == \
        datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)
    # inverno: 15/01 10:00Z → 15/01 23:00Z
    assert E.day_end_utc(datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)) == \
        datetime(2026, 1, 15, 23, 0, tzinfo=timezone.utc)
    # giorno del cambio ora (25/10/2026, 25 ore): inizio 24/10 22:00Z, fine 25/10 23:00Z
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert E.day_start_utc(now) == datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc)
    assert E.day_end_utc(now) == datetime(2026, 10, 25, 23, 0, tzinfo=timezone.utc)
    # naive = UTC
    assert E.day_end_utc(datetime(2026, 7, 15, 10, 0)) == datetime(2026, 7, 15, 22, 0, tzinfo=timezone.utc)


def test_c04_finestra_eventi_oggi_chiude_a_mezzanotte_di_roma():
    now = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    frm, to = M.today_window_utc(now, lookback_hours=12)
    assert frm == "2026-07-14T22:00:00Z"
    assert to == "2026-07-15T21:59:59Z"          # prima: 2026-07-15T23:59:59Z (01:59 Roma di DOMANI)
    # alle 23:30Z (01:30 Roma) la giornata è già quella dopo
    frm2, to2 = M.today_window_utc(datetime(2026, 7, 15, 23, 30, tzinfo=timezone.utc))
    assert to2 == "2026-07-16T21:59:59Z"


# ---------------------------------------------------------------------------
# Lettura book (C-05): valori mancanti / non finiti dal feed
# ---------------------------------------------------------------------------
def test_c05_best_lay_robusto_a_livelli_malformati():
    price, size, ladder = M._best_lay([
        {"price": 60.0},                       # senza size: prima KeyError su tutto il book
        {"price": float("nan"), "size": 10.0},
        {"price": 65.0, "size": 0.0},
        {"price": 70.0, "size": 12.5},
        {"price": "80", "size": "3"},
        "spazzatura",
    ])
    assert (price, size) == (70.0, 12.5)
    assert ladder == ((70.0, 12.5), (80.0, 3.0))
    assert M._best_lay([{"price": 60.0}]) == (None, 0.0, ())
    assert M._best_lay(None) == (None, 0.0, ())


def test_snapshot_dal_book_senza_size_non_esplode():
    mk = M.CorrectScoreMarket(market_id="1.1", event_id="e", event_name="A v B",
                              market_start_time=None, runner_names={1: "0 - 0", 2: "2 - 1"})
    snap = M._snapshot_from_book(mk, {"status": "OPEN", "inplay": True, "runners": [
        {"selectionId": 1, "status": "ACTIVE", "ex": {"availableToLay": [{"price": 8.0}]}},
        {"selectionId": 2, "status": "ACTIVE", "ex": {"availableToLay": [{"price": 60.0, "size": 4.0}],
                                                       "availableToBack": [{"price": 50.0, "size": 2.0}]}},
    ]})
    by = {r.selection_id: r for r in snap.runners}
    assert by[1].lay_price is None and by[1].lay_size == 0.0
    assert by[2].lay_price == 60.0 and by[2].lay_ladder == ((60.0, 4.0),) and by[2].back_price == 50.0
    assert not snap.closed and not snap.voided


# ---------------------------------------------------------------------------
# Whitelist parametri (C-06/C-07/C-08)
# ---------------------------------------------------------------------------
def test_c06_nan_e_inf_non_entrano_nella_whitelist():
    p = C.resolve_params({"price_min": float("nan"), "price_max": "inf",
                          "max_liability_per_match": float("-inf"), "model_tail_factor": "nan"})
    assert p["price_min"] == 20.0 and p["price_max"] == 120.0
    assert p["max_liability_per_match"] == 0.0 and p["model_tail_factor"] == 1.3
    assert all(math.isfinite(v) for v in p.values() if isinstance(v, float))


def test_c07_model_empirical_validato():
    assert C.resolve_params({"model_empirical": "off"})["model_empirical"] == "off"
    assert C.resolve_params({"model_empirical": "xxx"})["model_empirical"] == "veto"
    assert C.resolve_params({"model_empirical": None})["model_empirical"] == "veto"


def test_c08_calibration_path_null_e_stringa_vuota():
    assert C.resolve_params({"model_calibration_path": None})["model_calibration_path"] == ""
    assert C.resolve_params({"model_calibration_path": "  /x/y.json "})["model_calibration_path"] == "/x/y.json"


def test_clamp_int_e_swap_finestre_gambe():
    p = C.resolve_params({"ht_entry_min": 44, "ht_entry_max": 10, "ft_entry_min": 200, "ft_entry_max": 30,
                          "greenup_hold_max_risk": 0.5, "greenup_risk_cap": 0.1, "poll_interval_s": 1})
    assert (p["ht_entry_min"], p["ht_entry_max"]) == (10, 44)
    assert (p["ft_entry_min"], p["ft_entry_max"]) == (45, 130)      # clamp [45,130] poi swap
    assert p["greenup_hold_max_risk"] == 0.1 and p["poll_interval_s"] == 5


# ---------------------------------------------------------------------------
# Modello: probabilità sempre in [0, 1] e normalizzate; minuto > 90; λ residui
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cv", [0.0, 0.3, 1.0])
@pytest.mark.parametrize("lh,la", [(0.001, 0.001), (1.4, 1.1), (4.0, 0.2)])
def test_griglia_residua_normalizzata_e_non_negativa(lh, la, cv):
    g = MO.residual_grid(lh, la, -0.13, MO.MAX_GOALS_GRID, dixon_coles=True, cv=cv)
    assert g and abs(sum(g.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in g.values())


def test_score_probs_minuto_oltre_90_e_recupero():
    for minute in (89, 90, 95, 120):
        for half in (False, True):
            st = MO.LiveState(minute=minute, score_home=1, score_away=0)
            probs = MO.score_probs(lh_pre=1.4, la_pre=1.1, rho=-0.13, state=st, league_id=None, half=half, cv=0.3)
            assert probs and abs(sum(probs.values()) - 1.0) < 1e-9
            assert all(0.0 <= v <= 1.0 for v in probs.values())
            assert all(h >= 1 and a >= 0 for (h, a) in probs)     # mai un risultato irraggiungibile
            assert probs[(1, 0)] > 0.5                              # oltre il 90′ il corrente domina


def test_ht_residual_share_in_0_1_ovunque():
    for m in (0, 20, 44, 45, 46, 47, 48, 60, 90, 130):
        s = MO.ht_residual_share(m)
        assert 0.0 <= s <= 1.0
    assert MO.ht_residual_share(0) > MO.ht_residual_share(30) > MO.ht_residual_share(44)
    assert MO.ht_residual_share(48) == 0.0 and MO.ht_residual_share(90) == 0.0


def test_tail_factor_monotono_e_limitato():
    prev = 0.0
    for p in (0.0, 0.001, 0.01, 0.05, 0.2, 0.9, 1.0):
        q = MO.apply_tail_factor(p, 1.3)
        assert 0.0 <= q <= 1.0 and q >= prev
        prev = q
    assert MO.apply_tail_factor(0.01, 0.0) == 0.01 and MO.apply_tail_factor(0.01, float("nan")) == 0.01


def test_devig_e_lambda_pre_ko_su_input_rotti():
    assert MO.devig_1x2(0, 3.5, 4.0) is None
    assert MO.devig_1x2("x", 3.5, 4.0) is None
    assert MO.lambdas_from_pre_ko({"home": None, "draw": 3.4, "away": 4.5}) is None
    lam = MO.lambdas_from_pre_ko({"home": 1.5, "draw": 4.2, "away": 6.5})
    assert lam is not None and lam[0] > lam[1] > 0.2


def test_wilson_upper_in_0_1_e_mai_zero():
    from Betfair.omega import omega_empirical as EMP
    assert EMP.p_upper(0, 0) == 1.0
    for k, n in ((0, 200), (3, 200), (200, 200), (5, 5000)):
        u = EMP.p_upper(k, n)
        assert 0.0 < u <= 1.0 and u >= k / n
    assert 0.0 < EMP.shrunk_upper(0, 10, 4, 300) <= 1.0


# ---------------------------------------------------------------------------
# Aggregati: due gambe su mercati diversi si sommano; segni della giornata
# ---------------------------------------------------------------------------
def test_aggregati_due_gambe_stessa_partita_mercati_diversi():
    day = E.day_start_utc(datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc))
    rows = [
        {"id": 1, "event_id": "e1", "market_id": "ht", "status": "open", "liability": 40.0,
         "placed_at": "2026-09-12T09:00:00+00:00"},
        {"id": 2, "event_id": "e1", "market_id": "cs", "status": "open", "liability": 60.0,
         "placed_at": "2026-09-12T09:30:00+00:00"},
        {"id": 3, "event_id": "e2", "market_id": "cs2", "status": "won", "pnl": 3.0,
         "placed_at": "2026-09-12T08:00:00+00:00"},
        # chiusura in perdita della 3 → la POSIZIONE 3 è PERSA (3 − 5 = −2)
        {"id": 4, "event_id": "e2", "closes_trade_id": 3, "status": "lost", "pnl": -5.0,
         "placed_at": "2026-09-12T08:30:00+00:00"},
    ]
    agg = E.aggregate_trades(rows, day)
    assert agg["open_liability"] == 100.0 and agg["live_now"] == 1 and agg["events_today"] == 2
    assert agg["realized_today"] == -2.0 and agg["won_today"] == 0 and agg["lost_today"] == 1
    assert agg["legs_today"] == 3 and agg["matches_open"] == 2
