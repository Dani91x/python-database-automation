"""Unit test del ladder_worker (pipeline dati ladder LIVE, Step 1).

NESSUNA rete, NESSUN login, NESSUNA API Betfair: i ``latest_books`` sono MOCKATI e
``db.upsert_live_ladder`` e' monkeypatchata per catturare le scritture in memoria.

Copre:
  * compute_wom        — weight of money (rosa/blu) nei livelli vicino al best;
  * build_ladder_selection — costruzione selezione dalla cache (back/lay limitati, trd full);
  * ladder_signature   — firma stabile per il WRITE-ON-CHANGE (cambia solo se cambia il book);
  * ladder_worker      — pubblica solo i mercati CAMBIATI, salta i finished, best-effort.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from Betfair.stream import runner


# ===========================================================================
# compute_wom — weight of money
# ===========================================================================
def test_wom_balanced_50_50():
    wom = runner.compute_wom([[2.0, 100.0]], [[2.02, 100.0]], levels=3)
    assert wom == {"back_pct": 50.0, "lay_pct": 50.0}


def test_wom_back_heavy():
    # 300 back vs 100 lay → 75% / 25%
    wom = runner.compute_wom([[2.0, 300.0]], [[2.02, 100.0]], levels=3)
    assert wom == {"back_pct": 75.0, "lay_pct": 25.0}


def test_wom_sums_to_100_and_complementary():
    wom = runner.compute_wom([[2.0, 33.0]], [[2.02, 67.0]], levels=3)
    assert wom["back_pct"] + wom["lay_pct"] == pytest.approx(100.0)


def test_wom_only_first_n_levels_counted():
    # con levels=2 il 3o livello (1000 di lay) NON deve entrare nel calcolo
    back = [[2.0, 100.0], [1.99, 100.0], [1.98, 100.0]]
    lay = [[2.02, 100.0], [2.03, 100.0], [2.04, 1000.0]]
    wom = runner.compute_wom(back, lay, levels=2)
    # back 200 vs lay 200 → 50/50 (il 1000 escluso)
    assert wom == {"back_pct": 50.0, "lay_pct": 50.0}


def test_wom_empty_no_division_by_zero():
    assert runner.compute_wom([], [], levels=3) == {"back_pct": 0.0, "lay_pct": 0.0}
    # solo back, nessun lay → 100/0
    assert runner.compute_wom([[2.0, 10.0]], [], levels=3) == {"back_pct": 100.0, "lay_pct": 0.0}


# ===========================================================================
# build_ladder_selection — costruzione dalla cache (back/lay limitati, trd full)
# ===========================================================================
def test_build_selection_limits_levels_keeps_trd_full():
    runner_book = {
        "b": [[2.0, 10.0], [1.99, 20.0], [1.98, 30.0]],
        "l": [[2.02, 5.0], [2.03, 6.0], [2.04, 7.0]],
        "ltp": 2.0,
        "tv": 1234.5,
        "trd": [[1.95, 100.0], [2.0, 150.0], [2.05, 50.0], [2.10, 20.0]],
    }
    sel = runner.build_ladder_selection(47999, runner_book, "Home", max_levels=2)
    assert sel["selection_id"] == 47999
    assert sel["name"] == "Home"
    assert sel["ltp"] == 2.0
    assert sel["tv"] == 1234.5
    assert sel["back"] == [[2.0, 10.0], [1.99, 20.0]]      # limitato a 2
    assert sel["lay"] == [[2.02, 5.0], [2.03, 6.0]]        # limitato a 2
    assert len(sel["trd"]) == 4                             # trd full (non limitato)
    assert sel["wom"]["back_pct"] + sel["wom"]["lay_pct"] == pytest.approx(100.0)


def test_build_selection_tolerates_missing_fields():
    sel = runner.build_ladder_selection(1, {}, None, max_levels=10)
    assert sel["back"] == [] and sel["lay"] == [] and sel["trd"] == []
    assert sel["ltp"] is None and sel["tv"] is None
    assert sel["wom"] == {"back_pct": 0.0, "lay_pct": 0.0}


# ===========================================================================
# ladder_signature — firma write-on-change
# ===========================================================================
def _sel(**kw: Any) -> Dict[str, Any]:
    base = {
        "selection_id": 1, "ltp": 2.0, "tv": 100.0,
        "back": [[2.0, 10.0]], "lay": [[2.02, 8.0]], "trd": [[2.0, 50.0]],
        "wom": {"back_pct": 55.6, "lay_pct": 44.4},
    }
    base.update(kw)
    return base


def test_signature_stable_for_identical_books():
    assert runner.ladder_signature([_sel()]) == runner.ladder_signature([_sel()])


def test_signature_changes_when_back_changes():
    a = runner.ladder_signature([_sel()])
    b = runner.ladder_signature([_sel(back=[[2.0, 11.0]])])
    assert a != b


def test_signature_changes_when_ltp_changes():
    a = runner.ladder_signature([_sel()])
    b = runner.ladder_signature([_sel(ltp=2.02)])
    assert a != b


def test_signature_changes_when_trd_changes():
    a = runner.ladder_signature([_sel()])
    b = runner.ladder_signature([_sel(trd=[[2.0, 60.0]])])
    assert a != b


def test_signature_ignores_derived_tv_and_wom():
    # tv/wom sono DERIVATI da ltp/back/lay/trd → non devono cambiare la firma da soli.
    a = runner.ladder_signature([_sel()])
    b = runner.ladder_signature([_sel(tv=999.0, wom={"back_pct": 1.0, "lay_pct": 99.0})])
    assert a == b


# ===========================================================================
# ladder_worker — write-on-change end-to-end (latest_books MOCKATI, db MOCKATO)
# ===========================================================================
class _FakeRecorder:
    def __init__(self, books: Dict[str, Any]) -> None:
        self._books = books

    def latest_books(self) -> Dict[str, Any]:
        return dict(self._books)


class _FakeSession:
    def __init__(self, books: Dict[str, Any]) -> None:
        self.recorder = _FakeRecorder(books)
        self.markets_by_event: Dict[str, List[Dict[str, Any]]] = {}
        self.selection_names: Dict[str, Dict[str, str]] = {}
        self.finished_events: set = set()
        self._last_ladder_sig: Dict[str, str] = {}


def _book(status: str = "OPEN") -> Dict[str, Any]:
    return {
        "status": status,
        "runners": {
            "11": {"b": [[2.0, 50.0]], "l": [[2.02, 40.0]], "ltp": 2.0, "tv": 500.0,
                   "trd": [[2.0, 80.0]]},
        },
    }


@pytest.fixture
def captured(monkeypatch) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    monkeypatch.setattr(runner.db, "upsert_live_ladder", lambda row: calls.append(dict(row)))
    return calls


def test_worker_writes_changed_market_once(captured):
    books = {"1.1": _book()}
    sess = _FakeSession(books)
    sess.markets_by_event["31.1"] = [
        {"market_id": "1.1", "market_type": "MATCH_ODDS", "market_name": "Match Odds"}
    ]
    sess.selection_names["1.1"] = {"11": "Home"}

    # primo giro → scrive
    runner.ladder_worker({}, None, sess)
    assert len(captured) == 1
    row = captured[0]
    assert row["event_id"] == "31.1"
    assert row["market_id"] == "1.1"
    assert row["market_type"] == "MATCH_ODDS"
    assert row["status"] == "OPEN"
    assert row["ladder"]["selections"][0]["name"] == "Home"
    assert "updated_ms" in row["ladder"]

    # secondo giro, book INVARIATO → write-on-change salta (nessuna scrittura nuova)
    runner.ladder_worker({}, None, sess)
    assert len(captured) == 1


def test_worker_rewrites_when_book_changes(captured):
    books = {"1.1": _book()}
    sess = _FakeSession(books)
    sess.markets_by_event["31.1"] = [{"market_id": "1.1", "market_type": "MATCH_ODDS"}]
    sess.selection_names["1.1"] = {"11": "Home"}

    runner.ladder_worker({}, None, sess)
    assert len(captured) == 1

    # il book cambia (size al back) → nuova firma → nuova scrittura
    books["1.1"]["runners"]["11"]["b"] = [[2.0, 75.0]]
    runner.ladder_worker({}, None, sess)
    assert len(captured) == 2


def test_worker_skips_finished_events(captured):
    sess = _FakeSession({"1.1": _book()})
    sess.markets_by_event["31.1"] = [{"market_id": "1.1", "market_type": "MATCH_ODDS"}]
    sess.finished_events.add("31.1")
    runner.ladder_worker({}, None, sess)
    assert captured == []


def test_worker_skips_market_without_book(captured):
    sess = _FakeSession({})  # nessun book in cache
    sess.markets_by_event["31.1"] = [{"market_id": "1.1", "market_type": "MATCH_ODDS"}]
    runner.ladder_worker({}, None, sess)
    assert captured == []


def test_worker_best_effort_on_db_error(monkeypatch):
    # un errore di upsert NON deve propagare (best-effort) e la firma NON va memorizzata
    # (cosi' al giro dopo si ritenta).
    def _boom(row: Dict[str, Any]) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(runner.db, "upsert_live_ladder", _boom)
    sess = _FakeSession({"1.1": _book()})
    sess.markets_by_event["31.1"] = [{"market_id": "1.1", "market_type": "MATCH_ODDS"}]
    runner.ladder_worker({}, None, sess)  # non deve sollevare
    assert sess._last_ladder_sig == {}     # firma non memorizzata → ritenta al giro dopo


def test_worker_no_recorder_is_noop(captured):
    sess = _FakeSession({})
    sess.recorder = None
    runner.ladder_worker({}, None, sess)
    assert captured == []
