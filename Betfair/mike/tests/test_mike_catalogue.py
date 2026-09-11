"""Test catalogue (raggruppamento mercati, selezioni per nome, ranking, budget).

Nessuna rete. File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from Betfair.mike import catalogue as K
from Betfair.mike import config as C

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def mk(market_id, event_id, name, ko, mtype, runners, total=5000.0, comp="Serie A"):
    return {
        "marketId": market_id,
        "marketName": name,
        "totalMatched": total,
        "marketStartTime": ko.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "event": {"id": event_id, "name": f"Home v Away {event_id}", "openDate": ko.strftime("%Y-%m-%dT%H:%M:%S.000Z")},
        "competition": {"id": "81", "name": comp},
        "description": {"marketType": mtype},
        "runners": [{"selectionId": sid, "runnerName": rn, "sortPriority": i + 1}
                    for i, (sid, rn) in enumerate(runners)],
    }


def ou35(event_id, ko, total=5000.0, under_id=1222344, over_id=1222345):
    return mk(f"1.{event_id}35", event_id, "Over/Under 3.5 Goals", ko, "OVER_UNDER_35",
              [(under_id, "Under 3.5 Goals"), (over_id, "Over 3.5 Goals")], total)


def ou45(event_id, ko, total=3000.0, under_id=1222347, over_id=1222346):
    return mk(f"1.{event_id}45", event_id, "Over/Under 4.5 Goals", ko, "OVER_UNDER_45",
              [(under_id, "Under 4.5 Goals"), (over_id, "Over 4.5 Goals")], total)


def test_group_requires_both_markets_and_resolves_by_name():
    ko = NOW + timedelta(hours=2)
    events, warns = K.group_by_event([ou35("100", ko), ou45("100", ko), ou35("200", ko)])
    assert set(events) == {"100"}
    ev = events["100"]
    assert ev.ou35.market_id == "1.10035" and ev.ou45.market_id == "1.10045"
    assert ev.ou35.under_sel == 1222344 and ev.ou35.over_sel == 1222345
    assert ev.ou45.under_sel == 1222347 and ev.ou45.over_sel == 1222346
    assert ev.ko_at == ko
    assert ev.total_matched == 8000.0
    assert warns == []


def test_group_warns_on_unexpected_selection_ids_but_trusts_names():
    ko = NOW + timedelta(hours=2)
    events, warns = K.group_by_event([ou35("100", ko), ou45("100", ko, under_id=1222346, over_id=1222347)])
    ev = events["100"]
    assert ev.ou45.over_sel == 1222347          # per nome
    assert any("1222347" in w for w in warns)


def test_group_infers_type_from_name_when_description_missing():
    ko = NOW + timedelta(hours=2)
    a = ou35("100", ko); del a["description"]
    b = ou45("100", ko); del b["description"]
    events, _ = K.group_by_event([a, b])
    assert "100" in events


def test_rank_and_select():
    p = C.merge_params({"max_matches": 2, "min_total_matched": 1000})
    e1 = K.group_by_event([ou35("1", NOW + timedelta(hours=1)), ou45("1", NOW + timedelta(hours=1))])[0]["1"]
    e2 = K.group_by_event([ou35("2", NOW + timedelta(hours=5)), ou45("2", NOW + timedelta(hours=5))])[0]["2"]
    e3 = K.group_by_event([ou35("3", NOW - timedelta(minutes=30)), ou45("3", NOW - timedelta(minutes=30))])[0]["3"]
    e4 = K.group_by_event([ou35("4", NOW + timedelta(hours=2), total=100.0), ou45("4", NOW + timedelta(hours=2), total=100.0)])[0]["4"]
    ranked = K.rank_events([e1, e2, e3, e4], NOW, open_ids={"2"}, inplay_ids={"3"})
    assert [e.event_id for e in ranked][:2] == ["2", "3"]      # posizione aperta, poi in-play
    sel = K.select_events([e1, e2, e3, e4], NOW, p, open_ids=set(), inplay_ids={"3"},
                          safe_threshold=150, hard_cap=180)
    assert [e.event_id for e in sel.events] == ["3", "1"]      # cap 2, liquidita' esclude 4
    assert sel.n_markets == 4 and sel.verdict == "OK"
    assert "4" in sel.dropped_liquidity


def test_select_respects_hard_cap():
    p = C.merge_params({"max_matches": 90})
    evs = []
    for i in range(100):
        ko = NOW + timedelta(minutes=10 * i)
        evs.append(K.group_by_event([ou35(str(i), ko), ou45(str(i), ko)])[0][str(i)])
    sel = K.select_events(evs, NOW, p, open_ids=set(), inplay_ids=set(), safe_threshold=150, hard_cap=180)
    assert sel.n_markets == 180 and len(sel.events) == 90
    assert sel.verdict == "WARN"
    assert K.budget_verdict(80, 150, 180) == "OK"
    assert K.budget_verdict(200, 150, 180) == "REFUSE"


def test_window_bounds_iso():
    frm, to = K.window_bounds(NOW, hours_back=3.0, hours_ahead=24.0)
    assert frm == "2026-09-12T09:00:00Z" and to == "2026-09-13T12:00:00Z"


def test_market_ids_of_selection():
    ko = NOW + timedelta(hours=2)
    ev = K.group_by_event([ou35("100", ko), ou45("100", ko)])[0]["100"]
    assert K.market_ids([ev]) == ["1.10035", "1.10045"]
    assert ev.selection_key("1.10035", 1222344) == ("OU35", "UNDER")
    assert ev.selection_key("1.10045", 1222346) == ("OU45", "OVER")
    assert ev.selection_key("1.10045", 1222347) == ("OU45", "UNDER")
    assert ev.selection_key("x", 1) is None


def test_duplicate_market_same_type_keeps_most_liquid_and_warns():
    ko = NOW + timedelta(hours=2)
    a = ou35("100", ko, total=1000.0)
    b = ou35("100", ko, total=9000.0); b["marketId"] = "1.100dup"
    events, warns = K.group_by_event([a, b, ou45("100", ko)])
    assert events["100"].ou35.market_id == "1.100dup"
    assert any("duplicato" in w for w in warns)
