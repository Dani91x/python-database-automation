"""Test feed.py: dal payload del feed unico allo Snapshot dell'engine. ASCII-only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Betfair.mike import config as C
from Betfair.mike import engine as E
from Betfair.mike import feed as F

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def blk(line, market_id, sels, status="OPEN", inplay=False, bet_delay=0):
    return {"market_id": market_id, "status": status, "inplay": inplay, "total_matched": 100.0,
            "market_type": f"OVER_UNDER_{str(line).replace('.', '')}", "line": line, "ts_ms": 1,
            "bet_delay": bet_delay,
            "selections": [{"selection_id": sid, "name": name, "runner_status": "ACTIVE",
                            "back": bb, "lay": bl, "back_size": bs, "lay_size": ls}
                           for sid, name, bb, bl, bs, ls in sels]}


def payload(ko=None, inplay=False, minute=None, sh=None, sa=None, status="OPEN", bet_delay=0,
            u35=(1.50, 1.52, 30.0, 25.0), o45=(6.0, 6.4, 12.0, 9.0), u45=(1.18, 1.19, 50.0, 40.0),
            match_status=None):
    ko = ko or (NOW + timedelta(hours=2))
    p = {
        "event_name": "Roma v Lazio", "home": "Roma", "away": "Lazio", "competition": "Serie A",
        "open_date": ko.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "inplay": inplay, "mo_market_id": "1.MO",
        "mo_status": status, "odds": None, "minute": minute, "score_home": sh, "score_away": sa,
        "ou": [
            blk(3.5, "1.35", [(1222344, "Under 3.5 Goals", *u35), (1222345, "Over 3.5 Goals", 2.60, 2.70, 20.0, 15.0)],
                status=status, inplay=inplay, bet_delay=bet_delay),
            blk(4.5, "1.45", [(1222347, "Under 4.5 Goals", *u45), (1222346, "Over 4.5 Goals", *o45)],
                status=status, inplay=inplay, bet_delay=bet_delay),
        ],
    }
    if match_status:
        p["score_raw"] = {"matchStatus": match_status}
    return p


def row(p, updated=None):
    return {"event_id": "E1", "sport": "calcio", "payload": p,
            "updated_at": (updated or NOW).isoformat()}


def test_event_info_resolves_by_name():
    info = F.event_info("E1", payload())
    assert info.complete
    assert info.markets == {"OU35": "1.35", "OU45": "1.45"}
    assert info.selection_id("OU35", "UNDER") == 1222344
    assert info.selection_id("OU45", "OVER") == 1222346
    assert info.selection_id("OU45", "UNDER") == 1222347
    assert info.ko_at == (NOW + timedelta(hours=2)).timestamp()
    assert info.selection_name("OU45", "OVER") == "Over 4.5 Goals"


def test_event_info_incomplete_without_45():
    p = payload()
    p["ou"] = p["ou"][:1]
    assert F.event_info("E1", p).complete is False


def test_snapshot_books_and_p4():
    p = payload()
    info = F.event_info("E1", p)
    s = F.snapshot_from_row(row(p), info, now=NOW.timestamp(), params=C.merge_params(None), scanner_age_s=5.0)
    assert s is not None and s.inplay is False and s.market_status == "OPEN"
    b = s.book("OU35", "UNDER")
    assert (b.best_back, b.best_lay, b.back_size, b.lay_size, b.bet_delay) == (1.50, 1.52, 30.0, 25.0, 0)
    assert s.book("OU45", "OVER").best_back == 6.0 and s.book("OU45", "UNDER").best_back == 1.18
    po35 = (1 / 2.60) / (1 / 2.60 + 1 / 1.50)
    po45 = (1 / 6.0) / (1 / 6.0 + 1 / 1.18)
    assert s.p4_market == round(po35 - po45, 4)
    assert s.feed_fresh is True and s.goals is None


def test_snapshot_inplay_goals_ht_and_stale_feed():
    p = payload(inplay=True, minute=45, sh=1, sa=1, bet_delay=5, match_status="FirstHalfEnd")
    info = F.event_info("E1", p)
    old = NOW - timedelta(seconds=40)
    s = F.snapshot_from_row(row(p, updated=old), info, now=NOW.timestamp(), params=C.merge_params(None),
                            scanner_age_s=60.0, hazard=0.07, p4_model=0.15, last_goal_ts=123.0)
    assert s.inplay and s.goals == 2 and s.minute == 45 and s.ht_active is True
    assert s.book("OU35", "UNDER").bet_delay == 5
    assert s.feed_fresh is False                 # riga vecchia E scanner morto
    assert s.hazard == 0.07 and s.p4_model == 0.15 and s.last_goal_ts == 123.0
    # scanner vivo -> la riga immutata e' fresca (write-on-change)
    s2 = F.snapshot_from_row(row(p, updated=old), info, now=NOW.timestamp(), params=C.merge_params(None),
                             scanner_age_s=10.0)
    assert s2.feed_fresh is True


def test_is_candidate_window_and_filter():
    p = payload()
    info = F.event_info("E1", p)
    params = C.merge_params(None)
    assert F.is_candidate(info, p, now=NOW.timestamp(), params=params) is True
    assert F.is_candidate(info, p, now=(NOW - timedelta(hours=2)).timestamp(), params=params) is False
    assert F.is_candidate(info, p, now=NOW.timestamp(), params=C.merge_params({"competition_filter": "premier"})) is False
    assert F.is_candidate(info, p, now=NOW.timestamp(), params=C.merge_params({"competition_filter": "serie a, liga"})) is True
    # L4 (audit 11/09): una partita GIA' IN CORSO non viene armata (Mike non
    # entra mai in-play da zero) → niente card IDLE_LIVE inutili
    p_live = payload(inplay=True, minute=10, sh=0, sa=0, ko=NOW - timedelta(minutes=10))
    assert F.is_candidate(F.event_info("E1", p_live), p_live, now=NOW.timestamp(), params=params) is False


def test_market_status_closed_from_block():
    p = payload(status="CLOSED")
    info = F.event_info("E1", p)
    s = F.snapshot_from_row(row(p), info, now=NOW.timestamp(), params=C.merge_params(None), scanner_age_s=1.0)
    assert s.market_status == "CLOSED"
