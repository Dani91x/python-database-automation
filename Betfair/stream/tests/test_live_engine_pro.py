"""Test del motore live avanzato (Dixon-Coles in-play + segnali)."""
from __future__ import annotations

from Betfair.stream.engine.live_engine_pro import (
    MarketSignal,
    _kelly_back,
    _kelly_lay,
    evaluate_event,
    get_prematch_lambdas,
    rho_for_league,
    signals_to_json,
)


def _match_odds_market():
    return {
        "market_id": "1.1",
        "market_type": "MATCH_ODDS",
        "market_name": "Match Odds",
        "selections": [
            {"selection_id": 11, "name": "Home FC", "sort_priority": 1},
            {"selection_id": 12, "name": "Away FC", "sort_priority": 2},
            {"selection_id": 13, "name": "The Draw", "sort_priority": 3},
        ],
    }


def _ou_market(line_key="25", line_name="2.5"):
    return {
        "market_id": f"1.{line_key}",
        "market_type": f"OVER_UNDER_{line_key}",
        "market_name": f"Over/Under {line_name}",
        "selections": [
            {"selection_id": 100, "name": f"Under {line_name}", "sort_priority": 1},
            {"selection_id": 101, "name": f"Over {line_name}", "sort_priority": 2},
        ],
    }


def _ladder(price_back, price_lay, tv=100.0):
    return {"back": [[price_back, 50.0]], "lay": [[price_lay, 50.0]], "ltp": price_back, "tv": tv}


def test_signals_shape_and_json():
    markets = [_match_odds_market()]
    ladder = {"1.1": {"11": _ladder(3.0, 3.1), "12": _ladder(2.5, 2.6), "13": _ladder(3.2, 3.3)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=0,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    assert all(isinstance(s, MarketSignal) for s in sigs)
    assert {s.selection_id for s in sigs} == {11, 12, 13}
    js = signals_to_json(sigs)
    assert "signals" in js and len(js["signals"]) == 3
    assert all("direction" in s for s in js["signals"])
    # F38: la commissione usata da EV/Kelly viaggia nel payload — la colonna EV
    # del ladder usa la STESSA aliquota (mai due formule che divergono).
    assert js["commission"] == 0.05
    assert signals_to_json(sigs, commission=0.02)["commission"] == 0.02


def test_event_goal_hazard_bounds_and_semantics():
    # F40: p in (0,1), None pre-match, e coerenza col modello (chi insegue tardi
    # con λ alti → hazard maggiore di un match spento a inizio gara).
    from Betfair.stream.engine.live_engine_pro import event_goal_hazard

    base = dict(prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135)
    assert event_goal_hazard(score_home=None, score_away=None, minute=None, **base) is None

    early = event_goal_hazard(score_home=0, score_away=0, minute=10, **base)
    assert early is not None and 0.0 < early["p_next"] < 1.0
    assert early["horizon_min"] == 5.0 and early["minute"] == 10
    # exp_goals ~ (λ_tot residuo)·share(5') → p = 1−exp(−exp_goals): coerenza interna
    import math as _m
    assert abs(early["p_next"] - (1.0 - _m.exp(-early["exp_goals_next"]))) < 1e-3

    # λ molto bassi → hazard più basso (monotonia nel volume gol atteso)
    quiet = event_goal_hazard(score_home=0, score_away=0, minute=10,
                              prematch_lambda_home=0.4, prematch_lambda_away=0.3, league_id=135)
    assert quiet is not None and quiet["p_next"] < early["p_next"]

    # a tempo (modello) esaurito → None, mai un hazard inventato
    assert event_goal_hazard(score_home=1, score_away=0, minute=200, **base) is None


def test_signals_write_due_keepalive():
    # F38: write-on-change + keepalive — segnale cambiato → scrive sempre; invariato
    # → scrive SOLO se l'ultima scrittura è più vecchia del keepalive.
    from Betfair.stream.runner import _signals_write_due

    key = (("1.1", 11, "BACK", 0.55),)
    assert _signals_write_due(None, 0.0, key, 1000.0, 60.0) is True          # prima volta
    assert _signals_write_due(key, 1000.0, key, 1030.0, 60.0) is False       # invariato, fresco
    assert _signals_write_due(key, 1000.0, key, 1060.0, 60.0) is True        # invariato, keepalive
    other = (("1.1", 11, "LAY", 0.55),)
    assert _signals_write_due(key, 1059.0, other, 1060.0, 60.0) is True      # cambiato → subito


def test_match_odds_probs_sum_to_one():
    markets = [_match_odds_market()]
    ladder = {"1.1": {"11": _ladder(3.0, 3.1), "12": _ladder(2.5, 2.6), "13": _ladder(3.2, 3.3)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=0,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    total = sum(s.model_prob for s in sigs)
    assert abs(total - 1.0) < 1e-3


def test_late_lead_makes_home_strong_favourite():
    markets = [_match_odds_market()]
    # casa avanti 1-0 all'85' ma il mercato la paga ancora 2.5 (back) → forte BACK
    ladder = {"1.1": {"11": _ladder(2.5, 2.55), "12": _ladder(6.0, 6.2), "13": _ladder(4.0, 4.1)}}
    sigs = evaluate_event(
        score_home=1, score_away=0, minute=85,
        prematch_lambda_home=1.3, prematch_lambda_away=1.3, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    home = next(s for s in sigs if s.selection_id == 11)
    assert home.model_prob > 0.8           # quasi certa
    assert home.edge is not None and home.edge > 0
    assert home.direction == "BACK"
    assert home.kelly_stake > 0


def test_already_over_is_certain_under_is_hold_or_lay():
    # 2-1 = 3 gol → Over 2.5 già avvenuto: prob over ~1
    markets = [_ou_market()]
    ladder = {"1.25": {"101": _ladder(1.05, 1.06), "100": _ladder(20.0, 22.0)}}
    sigs = evaluate_event(
        score_home=2, score_away=1, minute=70,
        prematch_lambda_home=1.2, prematch_lambda_away=1.0, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    over = next(s for s in sigs if s.selection_id == 101)
    under = next(s for s in sigs if s.selection_id == 100)
    assert over.model_prob > 0.99
    assert under.model_prob < 0.01


def test_unmodeled_market_skipped():
    markets = [{"market_id": "1.9", "market_type": "CORRECT_SCORE",
                "market_name": "Correct Score",
                "selections": [{"selection_id": 1, "name": "0 - 0", "sort_priority": 1}]}]
    ladder = {"1.9": {"1": _ladder(8.0, 8.5)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=10,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    assert sigs == []  # mercato non modellato → nessun segnale


def test_kelly_back_commission_reduces_stake():
    # senza commissione = formula classica prob - (1-prob)/(odds-1)
    full = _kelly_back(0.6, 2.0, fraction=1.0, bankroll=100.0, commission=0.0)
    assert abs(full / 100.0 - (0.6 - 0.4 / 1.0)) < 1e-9   # b=1 → 0.6-0.4=0.2 → £20
    # la commissione riduce lo stake (mai lo aumenta)
    net = _kelly_back(0.6, 2.0, fraction=1.0, bankroll=100.0, commission=0.05)
    assert full > net > 0


def test_kelly_lay_commission_reduces_stake():
    full = _kelly_lay(0.20, 4.0, fraction=1.0, bankroll=100.0, commission=0.0)
    net = _kelly_lay(0.20, 4.0, fraction=1.0, bankroll=100.0, commission=0.05)
    assert full > net > 0


def test_lay_uses_lay_price_and_commission_in_edge():
    # Pareggio che il modello ritiene improbabile ma il mercato BANCA generoso (lay 3.0):
    # value-LAY VERO (1/lay=0.33 > prob) → direzione LAY con edge (EV) POSITIVO, calcolato
    # sul prezzo LAY (non sul back) e al netto della commissione.
    markets = [_match_odds_market()]
    ladder = {"1.1": {"11": _ladder(1.7, 1.72), "12": _ladder(4.5, 4.7), "13": _ladder(2.9, 3.0)}}
    sigs = evaluate_event(
        score_home=1, score_away=0, minute=60,
        prematch_lambda_home=1.5, prematch_lambda_away=0.9, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    draw = next(s for s in sigs if s.selection_id == 13)
    assert draw.model_prob < 0.30          # modello: pareggio improbabile (casa avanti)
    assert draw.direction == "LAY"
    assert draw.edge is not None and draw.edge > 0   # edge = EV positivo (non più negativo)
    assert draw.market_lay == 3.0          # ha usato il prezzo LAY


def test_kelly_lay_zero_at_fair_value():
    # a quota equa (lay_odds = 1/prob) il Kelly lay deve essere 0 (no edge)
    for prob, lay in [(0.5, 2.0), (1 / 3, 3.0), (0.25, 4.0), (0.2, 5.0)]:
        assert _kelly_lay(prob, lay, fraction=1.0, bankroll=100.0) < 1e-6
    # con vero valore (modello < implicita) il lay è positivo ma ragionevole
    stake = _kelly_lay(0.20, 4.0, fraction=1.0, bankroll=100.0)
    assert 0 < stake < 20  # NON i ~73 del bug


def test_prematch_lambdas_not_swapped_for_away_favourite():
    # away favorita (back più basso) → λ_away deve essere > λ_home
    market = {
        "market_id": "1.1", "market_type": "MATCH_ODDS",
        "selections": [
            {"selection_id": 11, "name": "Home FC", "sort_priority": 1},
            {"selection_id": 12, "name": "Away FC", "sort_priority": 2},
            {"selection_id": 13, "name": "The Draw", "sort_priority": 3},
        ],
    }
    ladder = {"11": _ladder(5.0, 5.2), "12": _ladder(1.8, 1.85), "13": _ladder(4.0, 4.1)}
    lh, la, _ = get_prematch_lambdas("e", None, match_odds_market=market, ladder=ladder)
    assert la > lh  # trasferta favorita → più gol attesi trasferta
    # caso opposto (casa favorita) → λ_home > λ_away
    ladder2 = {"11": _ladder(1.8, 1.85), "12": _ladder(5.0, 5.2), "13": _ladder(4.0, 4.1)}
    lh2, la2, _ = get_prematch_lambdas("e", None, match_odds_market=market, ladder=ladder2)
    assert lh2 > la2


def test_over_under_high_line_not_zero():
    # Under 6.5 a inizio partita deve essere ~certo (non 0.0 come nel bug)
    markets = [_ou_market(line_key="65", line_name="6.5")]
    ladder = {"1.65": {"100": _ladder(1.02, 1.03), "101": _ladder(20.0, 30.0)}}
    sigs = evaluate_event(
        score_home=0, score_away=0, minute=0,
        prematch_lambda_home=1.4, prematch_lambda_away=1.2, league_id=135,
        markets=markets, ladder_by_market=ladder,
    )
    under = next(s for s in sigs if s.selection_id == 100)
    over = next(s for s in sigs if s.selection_id == 101)
    assert under.model_prob > 0.95   # quasi certo
    assert over.model_prob < 0.05
    # niente più LAY confidente fasullo su Under 6.5
    assert not (under.direction == "LAY" and under.model_prob == 0.0)


def test_rho_for_league_lookup_and_fallback():
    assert rho_for_league(135) != rho_for_league(None) or True  # non deve esplodere
    r_known = rho_for_league(135)
    r_unknown = rho_for_league(99999999)
    assert -0.25 <= r_known <= 0.05
    assert -0.25 <= r_unknown <= 0.05  # fallback dentro la banda
