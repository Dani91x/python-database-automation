"""Audit 11/09 C1 — le partite SEGUITE da Mike restano nel feed (linee 3.5/4.5
vive) anche oltre il tetto dei 20 eventi e anche a linea decisa."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Betfair.safe_strategy import scanner
from Betfair.safe_strategy import service as S


class _Betting:
    def list_market_catalogue(self, **_):
        return []


@pytest.fixture
def scan(monkeypatch):
    sc = S.Scanner(SimpleNamespace(betting=_Betting()), dry=True, use_stream=False)
    sc.pre_ko_ou_hours = 0.0
    sc.dry = False          # il ramo C1 legge il DB solo nel run reale (qui monkeypatchato)
    return sc


def test_dry_scanner_never_touches_db(monkeypatch):
    sc = S.Scanner(SimpleNamespace(betting=_Betting()), dry=True, use_stream=False)

    def boom():
        raise AssertionError("query in dry")
    monkeypatch.setattr(S.scan_db, "list_mike_followed_event_ids", boom)
    assert sc._mike_followed() == set()


def _inplay(minute: int) -> dict:
    return {"sport": "calcio", "inplay": True, "minute": minute, "mo_status": "OPEN",
            "score_home": 2, "score_away": 2}


def test_mike_followed_cached_and_tolerant(scan, monkeypatch):
    calls = []
    monkeypatch.setattr(S.scan_db, "list_mike_followed_event_ids", lambda: calls.append(1) or ["M1"])
    assert scan._mike_followed(now_mono=100.0) == {"M1"}
    assert scan._mike_followed(now_mono=105.0) == {"M1"}      # entro il TTL: nessuna query
    assert len(calls) == 1
    # lettura fallita → resta l'ultima lista buona (mai togliere quote a una posizione aperta)
    monkeypatch.setattr(S.scan_db, "list_mike_followed_event_ids", lambda: None)
    assert scan._mike_followed(now_mono=120.0) == {"M1"}


def test_c1_followed_event_exempt_from_cap(scan, monkeypatch):
    monkeypatch.setattr(scanner, "OPP_MAX_EVENTS", 2)
    # 3 partite in gioco: la partita Mike è al 3' (ultima per priorità)
    scan.events = {"A": _inplay(80), "B": _inplay(60), "MIKE": _inplay(3)}
    monkeypatch.setattr(S.scan_db, "list_mike_followed_event_ids", lambda: ["MIKE"])
    cands = scan.opp_candidates()
    assert "MIKE" in cands
    assert cands == ["MIKE", "A", "B"]          # esente dal tetto, poi i minuti più avanzati


def test_c2_followed_event_keeps_decided_lines(scan, monkeypatch):
    monkeypatch.setattr(S.scan_db, "list_mike_followed_event_ids", lambda: ["MIKE"])
    ev = {"sport": "calcio", "inplay": True, "minute": 70, "mo_status": "OPEN",
          "score_home": 3, "score_away": 1,   # 4 gol: la 3.5 è decisa
          "opp": {
              "1.35": {"market_type": "OVER_UNDER_35", "line": 3.5, "selections": []},
              "1.45": {"market_type": "OVER_UNDER_45", "line": 4.5, "selections": []},
          }}
    live = scan._prune_opp_blocks(ev, "MIKE")
    assert set(live) == {"1.35", "1.45"}       # entrambe vive per la posizione Mike
    other = {**ev, "opp": dict(ev["opp"])}
    live_other = scan._prune_opp_blocks(other, "OTHER")
    assert "1.35" not in live_other            # per gli altri la linea decisa esce


def test_db_helper_never_raises(monkeypatch):
    from Betfair.safe_strategy import db as scan_db

    def boom():
        raise RuntimeError("no env")
    monkeypatch.setattr(scan_db, "get_supabase_client", boom)
    assert scan_db.list_mike_followed_event_ids() is None
