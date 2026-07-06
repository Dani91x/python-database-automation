"""Test della logica dei segnali della TennisProStrategy."""

import pytest
from betfairlightweight import filters

from Betfair.stream.tennis_scalper.tennis_pro_bot import (
    TennisProStrategy, _point_rank, FLAT,
)
from Betfair.stream.tennis_scalper.tennis_score import TennisScore


def _make(**params):
    return TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"stake": 2.0, **params},
        name_to_sel={"De Minaur": 111, "Cobolli": 222},
    )


def test_point_rank():
    assert _point_rank("0") == 0
    assert _point_rank("40") == 3
    assert _point_rank("AD") == 4
    assert _point_rank("7") == 7
    assert _point_rank(None) is None


def test_break_point_15_40_detected():
    s = _make()
    # De Minaur (home) serve, sotto 15-40 (server 15, receiver 40)
    s.score = TennisScore(event_id="1", server="home", point_home="15",
                          point_away="40", home_name="De Minaur", away_name="Cobolli")
    assert s._is_break_point() is True


def test_break_point_0_40_detected():
    s = _make()
    s.score = TennisScore(event_id="1", server="away", point_home="40",
                          point_away="0", home_name="De Minaur", away_name="Cobolli")
    assert s._is_break_point() is True   # away serve, home ribatte a 40 (0-40)


def test_30_40_NOT_break_point():
    s = _make()
    s.score = TennisScore(event_id="1", server="home", point_home="30",
                          point_away="40", home_name="De Minaur", away_name="Cobolli")
    assert s._is_break_point() is False   # 30-40 escluso di proposito


def test_deuce_not_break_point():
    s = _make()
    s.score = TennisScore(event_id="1", server="home", point_home="40",
                          point_away="40", home_name="De Minaur", away_name="Cobolli")
    assert s._is_break_point() is False


def test_server_receiver_mapping():
    s = _make()
    s.score = TennisScore(event_id="1", server="home", home_name="De Minaur",
                          away_name="Cobolli")
    srv, rcv = s._server_receiver_sel()
    assert srv == 111 and rcv == 222   # De Minaur serve


def test_name_mapping_by_surname():
    # nomi CATALOGO Betfair ("Ar Fery") != nomi IPS ("Arthur Fery"): match per cognome
    s = TennisProStrategy(
        market_filter=filters.streaming_market_filter(market_ids=["1.1"]),
        pro_params={"stake": 2.0},
        name_to_sel={"Dimitrov": 3120166, "Ar Fery": 26402980},
    )
    s.score = TennisScore(event_id="1", server="away",
                          home_name="Grigor Dimitrov", away_name="Arthur Fery")
    srv, rcv = s._server_receiver_sel()
    assert srv == 26402980       # Fery serve (away) -> match per cognome "fery"
    assert rcv == 3120166        # Dimitrov riceve -> "dimitrov"


def test_net_pnl_lay_position():
    # LAY 2 @ 3.0 : se vince -2*(3-1)=-4 ; se perde +2
    nw, nl = TennisProStrategy._net(0.0, 0.0, 2.0, 3.0)
    assert nw == pytest.approx(-4.0)
    assert nl == pytest.approx(2.0)


def test_net_pnl_back_position():
    nw, nl = TennisProStrategy._net(2.0, 2.5, 0.0, 0.0)
    assert nw == pytest.approx(3.0)    # 2*(2.5-1)
    assert nl == pytest.approx(-2.0)


def test_no_signal_without_score():
    s = _make()
    s.score = None
    assert s._is_break_point() is False
    assert s._server_receiver_sel() == (None, None)


# ---------------- nuovi setup (Daniel Temple & co.) ----------------

class _FakeMarket:
    market_id = "1.1"

    class _Blotter:
        def strategy_orders(self, _s):
            return []
    blotter = _Blotter()


def _dry(**params):
    return _make(dry_run=True, **params)


def _book(bb, bl, sb=100.0, sl=100.0, ltp=None):
    return {"bb": bb, "bl": bl, "sb": sb, "sl": sl, "ltp": ltp if ltp else bb}


def test_favourite_is_lowest_price():
    assert TennisProStrategy._favourite(
        {111: {"ltp": 1.4}, 222: {"ltp": 3.0}}) == 111


def test_open_trade_back_direction():
    s = _dry()
    s.score = TennisScore(event_id="1", games_home=0, games_away=0,
                          sets_home=0, sets_away=0)
    assert s._open_trade(_FakeMarket(), 111, "BACK", _book(1.50, 1.52), 5, 3, "t")
    tr = s._trade["1.1"]
    assert tr["side"] == "BACK" and tr["entry"] == 1.50
    assert tr["target"] < tr["entry"]     # BACK: green quando la quota CALA
    assert tr["stop"] > tr["entry"]


def test_open_trade_lay_direction():
    s = _dry()
    s.score = TennisScore(event_id="1", games_home=0, games_away=0,
                          sets_home=0, sets_away=0)
    assert s._open_trade(_FakeMarket(), 222, "LAY", _book(3.0, 3.05), 6, 4, "t")
    tr = s._trade["1.1"]
    assert tr["side"] == "LAY" and tr["entry"] == 3.05
    assert tr["target"] > tr["entry"]     # LAY: green quando la quota SALE
    assert tr["stop"] < tr["entry"]


def test_serving_for_set_lays_server():
    s = _dry(surface="clay")
    s.score = TennisScore(event_id="1", server="home", games_home=5, games_away=3,
                          sets_home=0, sets_away=0, home_name="De Minaur",
                          away_name="Cobolli")
    px = {111: _book(1.5, 1.52), 222: _book(3.0, 3.1)}
    assert s._sig_serving_for_set(_FakeMarket(), px) is True
    tr = s._trade["1.1"]
    assert tr["kind"] == "serving_for_set" and tr["side"] == "LAY"
    assert tr["sel"] == 111            # De Minaur serve per il set -> lay lui


def test_serving_for_set_not_triggered_early():
    s = _dry(surface="clay")
    s.score = TennisScore(event_id="1", server="home", games_home=3, games_away=2,
                          home_name="De Minaur", away_name="Cobolli")
    px = {111: _book(1.5, 1.52), 222: _book(3.0, 3.1)}
    assert s._sig_serving_for_set(_FakeMarket(), px) is False


def test_double_break_lays_leader():
    s = _dry(surface="clay")
    s.score = TennisScore(event_id="1", games_home=4, games_away=1,
                          home_name="De Minaur", away_name="Cobolli")
    px = {111: _book(1.3, 1.32), 222: _book(3.4, 3.5)}
    assert s._sig_double_break(_FakeMarket(), px) is True
    tr = s._trade["1.1"]
    assert tr["kind"] == "double_break" and tr["side"] == "LAY" and tr["sel"] == 111


def test_compressed_fav_lays_short_favourite():
    s = _dry(surface="clay")
    s.score = TennisScore(event_id="1", games_home=1, games_away=0)
    px = {111: _book(1.15, 1.16, ltp=1.15), 222: _book(5.0, 5.5, ltp=5.2)}
    assert s._sig_compressed_fav(_FakeMarket(), px) is True
    tr = s._trade["1.1"]
    assert tr["kind"] == "compressed_fav" and tr["side"] == "LAY" and tr["sel"] == 111


def test_set_transition_detects_and_lays_winner():
    s = _dry()
    px = {111: _book(1.4, 1.42), 222: _book(3.0, 3.1)}
    s.score = TennisScore(event_id="1", sets_home=0, sets_away=0, games_home=5,
                          games_away=3, home_name="De Minaur", away_name="Cobolli")
    s._track_sets("1.1", px)          # prev inizializzato
    s.score = TennisScore(event_id="1", sets_home=1, sets_away=0, games_home=0,
                          games_away=0, home_name="De Minaur", away_name="Cobolli")
    s._track_sets("1.1", px)          # rileva set vinto da home
    assert s._set_won["1.1"][0] == 111
    assert s._sig_set_transition(_FakeMarket(), "1.1", px) is True
    tr = s._trade["1.1"]
    assert tr["kind"] == "set_transition" and tr["side"] == "LAY" and tr["sel"] == 111


def test_set_transition_window_expires():
    s = _dry()
    px = {111: _book(1.4, 1.42), 222: _book(3.0, 3.1)}
    s.score = TennisScore(event_id="1", sets_home=0, sets_away=0, games_home=5,
                          games_away=3, home_name="De Minaur", away_name="Cobolli")
    s._track_sets("1.1", px)
    s.score = TennisScore(event_id="1", sets_home=1, sets_away=0, games_home=0,
                          games_away=0, home_name="De Minaur", away_name="Cobolli")
    s._track_sets("1.1", px)
    # avanza oltre la finestra (3 game nel nuovo set)
    s.score = TennisScore(event_id="1", sets_home=1, sets_away=0, games_home=2,
                          games_away=1, home_name="De Minaur", away_name="Cobolli")
    assert s._sig_set_transition(_FakeMarket(), "1.1", px) is False
