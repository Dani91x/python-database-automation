"""Test del RAMO PRE-KO O/U del feed unico (linee 3.5/4.5 per il bot Mike).

Nessuna rete/DB: client Betfair finto. File ASCII-only.
Regola: a ramo spento (SAFE_PRE_KO_OU_HOURS assente/0) il feed e' identico a prima.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service as S

# orologio REALE: _apply_opp_book (chiamato dallo stream, senza `now`) usa
# datetime.now per riconoscere il ramo pre-KO; tutti gli offset sono relativi
NOW = datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------- logica pura
def test_window_and_candidate():
    ko = iso(NOW + timedelta(hours=2))
    assert scanner.in_pre_ko_ou_window(ko, NOW, 3.0) is True
    assert scanner.in_pre_ko_ou_window(ko, NOW, 1.0) is False
    assert scanner.in_pre_ko_ou_window(ko, NOW, 0.0) is False
    assert scanner.in_pre_ko_ou_window(iso(NOW - timedelta(minutes=5)), NOW, 3.0) is False
    assert scanner.is_pre_ko_ou_candidate(False, None, ko, NOW, 3.0) is True
    assert scanner.is_pre_ko_ou_candidate(True, None, ko, NOW, 3.0) is False
    assert scanner.is_pre_ko_ou_candidate(False, "CLOSED", ko, NOW, 3.0) is False


def test_is_monitorable_backward_compatible():
    ko = iso(NOW + timedelta(hours=2))
    assert scanner.is_monitorable(False, ko, NOW) is False          # firma storica
    assert scanner.is_monitorable(False, ko, NOW, 0.0) is False
    assert scanner.is_monitorable(False, ko, NOW, 3.0) is True
    assert scanner.is_monitorable(False, iso(NOW + timedelta(minutes=10)), NOW) is True


def test_is_opp_market_live_pre_ko_only_two_lines():
    assert scanner.is_opp_market_live("OVER_UNDER_35", 3.5, None, None, None, pre_ko=True) is True
    assert scanner.is_opp_market_live("OVER_UNDER_45", 4.5, None, None, None, pre_ko=True) is True
    assert scanner.is_opp_market_live("OVER_UNDER_25", 2.5, None, None, None, pre_ko=True) is False
    assert scanner.is_opp_market_live("BOTH_TEAMS_TO_SCORE", None, None, None, None, pre_ko=True) is False
    # senza pre_ko la linea senza punteggio resta NON viva (comportamento storico)
    assert scanner.is_opp_market_live("OVER_UNDER_35", 3.5, None, None, None) is False


def test_build_market_block_bet_delay_optional():
    sel = [{"selection_id": 1, "name": "Under 3.5 Goals", "back": 1.5, "lay": 1.52,
            "back_size": 10.0, "lay_size": 8.0}]
    blk = scanner.build_market_block("1.1", "OPEN", sel, inplay=False, market_type="OVER_UNDER_35", line=3.5)
    assert "bet_delay" not in blk
    blk = scanner.build_market_block("1.1", "OPEN", sel, inplay=True, bet_delay=5)
    assert blk["bet_delay"] == 5


# ---------------------------------------------------------------- service (fake client)
class _Betting:
    def __init__(self, cats):
        self.cats = cats
        self.calls = []

    def list_market_catalogue(self, **kw):
        self.calls.append(kw)
        types = set(kw["filter"].get("marketTypeCodes") or [])
        return [c for c in self.cats if c.description.market_type in types]


def _cat(event_id, market_id, mtype, runners):
    return SimpleNamespace(
        event=SimpleNamespace(id=event_id, name="A v B"),
        market_id=market_id,
        market_name=None,
        description=SimpleNamespace(market_type=mtype),
        runners=[SimpleNamespace(selection_id=s, runner_name=n) for s, n in runners],
    )


def _book(market_id, inplay=False, bet_delay=0, status="OPEN"):
    ex = SimpleNamespace(
        available_to_back=[SimpleNamespace(price=1.50, size=30.0)],
        available_to_lay=[SimpleNamespace(price=1.52, size=25.0)],
    )
    return SimpleNamespace(
        market_id=market_id, status=status, inplay=inplay, bet_delay=bet_delay,
        total_matched=1234.0,
        runners=[SimpleNamespace(selection_id=1222344, status="ACTIVE", ex=ex),
                 SimpleNamespace(selection_id=1222345, status="ACTIVE", ex=ex)],
    )


def _scanner(hours, cats):
    """Scanner finto; il KO e' a +2h dall'orologio REALE perche' _apply_opp_book
    (chiamato dallo stream, senza `now`) usa datetime.now per il ramo pre-KO."""
    scan = S.Scanner(SimpleNamespace(betting=_Betting(cats)), dry=True, use_stream=False)
    scan.pre_ko_ou_hours = hours
    ko = iso(NOW + timedelta(hours=2))
    scan.sports["calcio"].metas = {
        "E1": {"event_id": "E1", "market_id": "1.MO1", "event_name": "A v B", "open_date": ko,
               "competition": "Serie A", "runners": [], "sides": {"home": 1, "away": 2, "draw": 3}},
    }
    scan.sports["calcio"].catalogue_ts = 1.0
    scan.sports["tennis"].catalogue_ts = 1.0
    scan._rebuild_market_index()
    return scan


CATS = [
    _cat("E1", "1.OU35", "OVER_UNDER_35", [(1222344, "Under 3.5 Goals"), (1222345, "Over 3.5 Goals")]),
    _cat("E1", "1.OU45", "OVER_UNDER_45", [(1222347, "Under 4.5 Goals"), (1222346, "Over 4.5 Goals")]),
    _cat("E1", "1.OU25", "OVER_UNDER_25", [(47972, "Under 2.5 Goals"), (47973, "Over 2.5 Goals")]),
]


def test_branch_off_changes_nothing():
    scan = _scanner(0.0, CATS)
    assert scan.pre_ko_ou_candidates(NOW) == []
    assert scan._opp_ranked_market_ids(NOW) == []
    rows, wanted = scan.build_rows(NOW)
    assert rows == [] and wanted == []
    scan._apply_market_book(_book("1.OU35"))
    assert "E1" not in scan.events


def test_pre_ko_catalogue_only_two_lines_and_ranked_tier2():
    scan = _scanner(3.0, CATS)
    cands = scan.pre_ko_ou_candidates(NOW)
    assert cands == ["E1"]
    scan.refresh_opp_catalogue(cands, market_types=scanner.PRE_KO_OU_MARKET_TYPES)
    betting = scan.client.betting
    assert len(betting.calls) == 1
    assert set(betting.calls[0]["filter"]["marketTypeCodes"]) == {"OVER_UNDER_35", "OVER_UNDER_45"}
    assert set(scan.opp_markets["E1"]) == {"1.OU35", "1.OU45"}
    assert "E1" not in scan.opp_full_eids
    ranked = scan._opp_ranked_market_ids(NOW)
    assert sorted(mid for _, mid in ranked) == ["1.OU35", "1.OU45"]
    assert all(key[0] == 2 for key, _ in ranked)
    # nessuna seconda chiamata finche' i mercati sono in cache
    scan.refresh_opp_catalogue(cands, market_types=scanner.PRE_KO_OU_MARKET_TYPES)
    assert len(betting.calls) == 1
    # la MO resta fuori (KO fra 2h > 20'): solo le due linee sono rilevanti
    assert scan.relevant_market_ids("calcio", NOW) == ["1.OU35", "1.OU45"]


def test_pre_ko_book_creates_event_and_row_with_bet_delay():
    scan = _scanner(3.0, CATS)
    scan.refresh_opp_catalogue(["E1"], market_types=scanner.PRE_KO_OU_MARKET_TYPES)
    scan._apply_market_book(_book("1.OU35", bet_delay=0))
    scan._apply_market_book(_book("1.OU45", bet_delay=0))
    assert scan.events["E1"]["inplay"] is False
    rows, wanted = scan.build_rows(NOW)
    assert wanted == ["E1"] and len(rows) == 1
    p = rows[0]["payload"]
    assert p["inplay"] is False and p["odds"] is None
    lines = sorted(b["line"] for b in p["ou"])
    assert lines == [3.5, 4.5]
    blk = p["ou"][0]
    assert blk["bet_delay"] == 0 and blk["status"] == "OPEN"
    sel = {s["selection_id"]: s for s in blk["selections"]}
    assert sel[1222344]["back"] == 1.50 and sel[1222344]["back_size"] == 30.0


def test_inplay_completes_catalogue_with_all_lines():
    scan = _scanner(3.0, CATS)
    scan.refresh_opp_catalogue(["E1"], market_types=scanner.PRE_KO_OU_MARKET_TYPES)
    scan._apply_market_book(_book("1.OU35"))
    # la partita inizia: evento in-play al 10', 0-0
    scan.events["E1"].update({"inplay": True, "minute": 10, "score_home": 0, "score_away": 0,
                              "mo_status": "OPEN"})
    assert scan.pre_ko_ou_candidates(NOW) == []          # non piu' pre-KO
    assert scan.opp_candidates() == ["E1"]
    scan.refresh_opp_catalogue(["E1"])                    # completo: chiamata nuova
    assert len(scan.client.betting.calls) == 2
    assert set(scan.opp_markets["E1"]) == {"1.OU35", "1.OU45", "1.OU25"}
    assert "E1" in scan.opp_full_eids
    scan.refresh_opp_catalogue(["E1"])                    # gia' completo: nessuna chiamata
    assert len(scan.client.betting.calls) == 2
    # in-play le linee vive tornano a dipendere dal punteggio (comportamento storico)
    live = scan._prune_opp_blocks(scan.events["E1"], "E1", NOW)
    assert set(live) == {"1.OU35"}
