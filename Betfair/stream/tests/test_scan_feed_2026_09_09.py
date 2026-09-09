"""Test del FEED UNICO punteggi (scores/scan_feed.py) + board dal feed (audit 09/09).

Nessuna rete/DB: fetch iniettato. Garanzie:
  - riga fresca con score_raw → punteggio dal feed, ZERO chiamate dirette;
  - riga stantia/assente/senza score_raw → fallback alla chiamata diretta;
  - UNA sola SELECT per ciclo per N eventi (cache condivisa con TTL);
  - timeline dal feed se presente, altrimenti diretta;
  - board: riga dal payload scanner solo se ha mo_market_id + selection_id.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from Betfair.stream import board_worker as bw
from Betfair.stream.scores import scan_feed as sf
from Betfair.stream.scores.base import ScoreSnapshot


def _iso(age_sec: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=age_sec)).isoformat()


def _state(minute: int = 58, home: int = 1, away: int = 0) -> Dict[str, Any]:
    return {
        "eventId": 1, "timeElapsed": minute, "matchStatus": "SecondHalf",
        "score": {"home": {"score": str(home), "numberOfRedCards": 0},
                  "away": {"score": str(away), "numberOfRedCards": 1}},
    }


class _Direct:
    """Provider IPS diretto fake: conta le chiamate."""
    name = "betfair"

    def __init__(self) -> None:
        self.score_calls: List[str] = []
        self.timeline_calls: List[str] = []

    def get_score(self, event_id: str):
        self.score_calls.append(event_id)
        return ScoreSnapshot(event_id=event_id, ts=_iso(0), source="betfair", minute=1)

    def get_timeline(self, event_id: str):
        self.timeline_calls.append(event_id)
        return [{"update_id": "direct"}]

    def healthcheck(self) -> bool:
        return True


class _Fetch:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: List[List[str]] = []

    def __call__(self, ids: List[str]) -> List[Dict[str, Any]]:
        self.calls.append(list(ids))
        return [r for r in self.rows if r["event_id"] in ids]


def _provider(rows, clock=None):
    fetch = _Fetch(rows)
    cache = sf.ScanRowCache(ttl_sec=1.0, fetch=fetch, clock=clock or (lambda: 0.0),
                            fetch_status=lambda: None)
    direct = _Direct()
    return sf.ScanFeedScoreProvider(direct, cache=cache), direct, fetch


def test_riga_fresca_punteggio_dal_feed_senza_chiamate_dirette():
    rows = [{"event_id": "e1", "sport": "calcio", "updated_at": _iso(2),
             "payload": {"score_raw": _state(58, 1, 0), "timeline": [{"update_id": 7, "type": "GOAL"}]}}]
    prov, direct, fetch = _provider(rows)
    snap = prov.get_score("e1")
    assert snap is not None and snap.minute == 58 and snap.score_home == 1 and snap.score_away == 0
    assert snap.red_away == 1 and snap.source == "betfair"   # stesso parser del provider diretto
    assert prov.get_timeline("e1") == [{"update_id": 7, "type": "GOAL"}]
    assert direct.score_calls == [] and direct.timeline_calls == []
    assert prov.feed_hits == 1 and prov.direct_calls == 0


def test_riga_stantia_o_assente_fallback_diretto():
    rows = [{"event_id": "old", "sport": "calcio", "updated_at": _iso(40),
             "payload": {"score_raw": _state()}},
            {"event_id": "noraw", "sport": "calcio", "updated_at": _iso(1), "payload": {"odds": {}}}]
    prov, direct, _ = _provider(rows)
    assert prov.get_score("old").minute == 1          # stantia (40s > 15s) → diretto
    assert prov.get_score("noraw").minute == 1        # senza score_raw → diretto
    assert prov.get_score("missing").minute == 1      # assente → diretto
    assert direct.score_calls == ["old", "noraw", "missing"]
    assert prov.get_timeline("old") == [{"update_id": "direct"}]


def test_una_select_per_ciclo_per_tutti_gli_eventi():
    clock = {"t": 100.0}
    rows = [{"event_id": e, "sport": "calcio", "updated_at": _iso(1), "payload": {"score_raw": _state()}}
            for e in ("a", "b", "c")]
    prov, _, fetch = _provider(rows, clock=lambda: clock["t"])
    for e in ("a", "b", "c"):
        prov.get_score(e)
    # 3 eventi nuovi: la prima richiesta carica, le due nuove chiavi ricaricano
    # (insieme "richiesti" cresciuto) ma dal secondo ciclo in poi è UNA sola SELECT
    n0 = len(fetch.calls)
    clock["t"] += 1.5
    for e in ("a", "b", "c"):
        prov.get_score(e)
    assert len(fetch.calls) == n0 + 1
    assert sorted(fetch.calls[-1]) == ["a", "b", "c"]
    # entro il TTL: nessuna nuova SELECT
    for e in ("a", "b", "c"):
        prov.get_score(e)
    assert len(fetch.calls) == n0 + 1


def test_fetch_ko_non_solleva_e_usa_il_diretto():
    def boom(_ids):
        raise RuntimeError("db giù")
    cache = sf.ScanRowCache(ttl_sec=1.0, fetch=boom, clock=lambda: 0.0, fetch_status=lambda: None)
    direct = _Direct()
    prov = sf.ScanFeedScoreProvider(direct, cache=cache)
    assert prov.get_score("x").minute == 1
    assert direct.score_calls == ["x"]


def test_fresh_payload_pura():
    assert sf.fresh_payload(None, 15.0) is None
    assert sf.fresh_payload({"updated_at": "garbage", "payload": {}}, 15.0) is None
    assert sf.fresh_payload({"updated_at": _iso(20), "payload": {"a": 1}}, 15.0) is None
    assert sf.fresh_payload({"updated_at": _iso(3), "payload": {"a": 1}}, 15.0) == {"a": 1}
    assert sf.fresh_payload({"updated_at": _iso(3), "payload": "no"}, 15.0) is None


# ------------------------------------------------------------- board dal feed
def _meta():
    return {"market_id": "1.9", "event_id": "e1", "event_name": "Nord v Sud",
            "open_date": "2026-09-09T15:00:00+00:00", "runners": {11: "Nord", 22: "Sud", 33: "The Draw"}}


def test_board_riga_dal_payload_scanner():
    payload = {
        "mo_market_id": "1.9", "mo_status": "OPEN", "inplay": True, "mo_total_matched": 12345.5,
        "odds": {"home": {"selection_id": 11, "back": 1.5, "lay": 1.52, "ltp": 1.51, "back_size": 10, "lay_size": 5},
                 "away": {"selection_id": 22, "back": 7.0, "lay": 7.4, "ltp": 7.2},
                 "draw": {"selection_id": 33, "back": 4.0, "lay": 4.2, "ltp": 4.1}},
    }
    row = bw.row_from_scan_payload(_meta(), payload)
    assert row is not None
    assert row["market_id"] == "1.9" and row["inplay"] is True and row["status"] == "OPEN"
    assert row["total_matched"] == 12345.5
    assert [s["selection_id"] for s in row["selections"]] == [11, 22, 33]
    assert row["selections"][0] == {"selection_id": 11, "name": "Nord", "back": 1.5, "lay": 1.52, "ltp": 1.51}


def test_board_payload_incompleto_va_al_fallback_rest():
    # mercato diverso
    assert bw.row_from_scan_payload(_meta(), {"mo_market_id": "1.8", "odds": {"home": {"selection_id": 11}}}) is None
    # scanner vecchio senza selection_id
    assert bw.row_from_scan_payload(_meta(), {"mo_market_id": "1.9", "odds": {"home": {"back": 1.5}}}) is None
    # senza odds
    assert bw.row_from_scan_payload(_meta(), {"mo_market_id": "1.9"}) is None


def test_scanner_vivo_rende_valida_una_riga_non_riscritta():
    """Write-on-change: con lo scanner VIVO una riga vecchia (0-0 fermo) è
    l'ultimo stato, non un dato stantio; con lo scanner FERMO torna il fallback."""
    old = {"event_id": "e1", "sport": "calcio", "updated_at": _iso(120), "payload": {"score_raw": _state(70, 0, 0)}}
    assert sf.fresh_payload(old, 15.0) is None
    assert sf.fresh_payload(old, 15.0, scanner_age_sec=8.0) == old["payload"]     # scanner vivo
    assert sf.fresh_payload(old, 15.0, scanner_age_sec=90.0) is None              # scanner fermo
    fetch = _Fetch([old])
    alive = sf.ScanRowCache(ttl_sec=1.0, fetch=fetch, clock=lambda: 0.0,
                            fetch_status=lambda: {"id": "scanner", "updated_at": _iso(5), "payload": {}})
    dead = sf.ScanRowCache(ttl_sec=1.0, fetch=fetch, clock=lambda: 0.0,
                           fetch_status=lambda: {"id": "scanner", "updated_at": _iso(600), "payload": {}})
    assert alive.scanner_alive() is True and dead.scanner_alive() is False
    assert sf.ScanFeedScoreProvider(_Direct(), cache=alive).get_score("e1").minute == 70
    assert sf.ScanFeedScoreProvider(_Direct(), cache=dead).get_score("e1").minute == 1   # diretto
