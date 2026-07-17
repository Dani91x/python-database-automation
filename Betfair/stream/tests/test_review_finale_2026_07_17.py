"""Fix della review finale 17/07 (terza passata sui cantieri del pomeriggio).

Pinna: (1) gating opt-in ANCHE sul file curato <event>.jsonl del recorder
(CRITICAL: era il flusso più pesante e restava non-gated); (2) cache del
verdetto "regole armate" in _lifecycle_blockers (solo esito BLOCCATO, mai il
"libero"; fresh=True bypassa); (3) register_follow non sovrascrive mai un REC
spento a mano (flip-flop watchlist); (4) split-throttle del worker ordini
tennis (drain locale a ogni tick, coda DB max ~1/s).
"""
from __future__ import annotations

import time as _time
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# (1) recorder.py — <event>.jsonl SOLO per gli eventi in registrazione
# ---------------------------------------------------------------------------
def _mk_recorder(tmp_path, record_events):
    from betfairlightweight.filters import (
        streaming_market_data_filter,
        streaming_market_filter,
    )

    from Betfair.stream.recorder import MarketRecorderStrategy

    return MarketRecorderStrategy(
        market_filter=streaming_market_filter(market_ids=["1.1", "1.2"]),
        market_data_filter=streaming_market_data_filter(
            fields=["EX_BEST_OFFERS"], ladder_levels=3),
        context={
            "data_dir": str(tmp_path),
            "market_to_event": {"1.1": "EV_REC", "1.2": "EV_NO"},
            "depth": 3,
            "record_events": record_events,
        },
    )


class _Runner(SimpleNamespace):
    pass


def _book(mid):
    runner = SimpleNamespace(
        selection_id=1, handicap=0.0, status="ACTIVE",
        last_price_traded=2.0, total_matched=10.0,
        ex=SimpleNamespace(available_to_back=[], available_to_lay=[],
                           traded_volume=[]),
    )
    return SimpleNamespace(
        market_id=mid, publish_time_epoch=1_000, inplay=True,
        status="OPEN", total_matched=10.0,
        market_definition=SimpleNamespace(market_type="MATCH_ODDS",
                                          in_play=True, bet_delay=0),
        runners=[runner], streaming_unique_id=7,
    )


def test_recorder_file_solo_per_eventi_scelti(tmp_path):
    rec = _mk_recorder(tmp_path, lambda: {"EV_REC"})
    rec.process_market_book(object(), _book("1.1"))   # evento SCELTO
    rec.process_market_book(object(), _book("1.2"))   # evento NON scelto
    assert (tmp_path / "EV_REC" / "EV_REC.jsonl").exists()
    assert not (tmp_path / "EV_NO").exists()          # niente file, niente dir
    # la cache live (ladder/live_now) resta aggiornata per ENTRAMBI
    assert set(rec.latest_books().keys()) == {"1.1", "1.2"}


def test_recorder_gating_none_registra_tutto(tmp_path):
    # migrazione non applicata → None = comportamento storico
    rec = _mk_recorder(tmp_path, lambda: None)
    rec.process_market_book(object(), _book("1.2"))
    assert (tmp_path / "EV_NO" / "EV_NO.jsonl").exists()


def test_recorder_toggle_a_meta_partita(tmp_path):
    flags = {"set": set()}
    rec = _mk_recorder(tmp_path, lambda: flags["set"])
    rec.process_market_book(object(), _book("1.1"))
    assert not (tmp_path / "EV_REC").exists()
    flags["set"] = {"EV_REC"}                          # click "Segui live"
    rec.process_market_book(object(), _book("1.1"))
    assert (tmp_path / "EV_REC" / "EV_REC.jsonl").exists()


# ---------------------------------------------------------------------------
# (2) _lifecycle_blockers — cache SOLO del verdetto bloccato + fresh bypass
# ---------------------------------------------------------------------------
def _flat_flumine():
    blotter = SimpleNamespace(live_orders=[])
    return SimpleNamespace(markets=[SimpleNamespace(market_id="1.1",
                                                    blotter=blotter)])


def test_risk_rules_cache_solo_verdetto_bloccato(monkeypatch):
    from Betfair.stream import runner as R

    monkeypatch.setattr(R, "LIVE_ORDER_MODE", "PAPER")
    monkeypatch.setattr(R, "_RISK_RULES_BLOCKED_UNTIL", 0.0)
    calls = {"n": 0}

    class _Q:
        def __init__(self, data):
            self._d = data

        def select(self, *a, **k):
            return self

        def in_(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            calls["n"] += 1
            return SimpleNamespace(data=[{"id": 1}])

    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda *_: _Q([{"id": 1}])))

    fl = _flat_flumine()
    # 1° check: query reale → BLOCCATO → cache armata
    assert R._lifecycle_blockers(fl) is not None
    assert calls["n"] == 1
    # 2° e 3° check entro il TTL: NESSUNA query (verdetto dalla cache)
    assert R._lifecycle_blockers(fl) is not None
    assert R._lifecycle_blockers(fl) is not None
    assert calls["n"] == 1
    # fresh=True (check finale pre-stop): SEMPRE query fresca
    assert R._lifecycle_blockers(fl, fresh=True) is not None
    assert calls["n"] == 2


def test_risk_rules_esito_libero_mai_cacheato(monkeypatch):
    from Betfair.stream import runner as R

    monkeypatch.setattr(R, "LIVE_ORDER_MODE", "PAPER")
    monkeypatch.setattr(R, "_RISK_RULES_BLOCKED_UNTIL", 0.0)
    calls = {"n": 0}

    class _Q:
        def select(self, *a, **k):
            return self

        def in_(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            calls["n"] += 1
            return SimpleNamespace(data=[])

    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda *_: _Q()))

    fl = _flat_flumine()
    # esito LIBERO: la query gira OGNI volta (una regola appena armata non
    # può mai sfuggire — direzione money-critical della cache)
    assert R._lifecycle_blockers(fl) is None
    assert R._lifecycle_blockers(fl) is None
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# (3) register_follow — il REC spento a mano NON viene mai riacceso dal poll
# ---------------------------------------------------------------------------
def test_register_follow_non_riaccende_rec_spento(monkeypatch):
    from Betfair.stream import db as sdb

    upserts = []

    class _T:
        def __init__(self, name):
            self._name = name

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            if self._name == "personal_watchlist":
                return SimpleNamespace(data=[{"follow_live": True}])
            return SimpleNamespace(data=[{"event_id": "E1"}])  # follow ESISTE

        def upsert(self, row, **k):
            upserts.append(dict(row))
            return self

    monkeypatch.setattr(sdb, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda name: _T(name)))

    sdb.register_follow("E1", "Casa", "Ospite", "2026-07-17T15:00:00Z",
                        watchlist_id=9)
    assert upserts and "record" not in upserts[0]  # mai riscrivere la scelta


def test_register_follow_nuovo_da_watchlist_registra(monkeypatch):
    from Betfair.stream import db as sdb

    upserts = []

    class _T:
        def __init__(self, name):
            self._name = name

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            if self._name == "personal_watchlist":
                return SimpleNamespace(data=[{"follow_live": True}])
            return SimpleNamespace(data=[])  # follow NUOVO

        def upsert(self, row, **k):
            upserts.append(dict(row))
            return self

    monkeypatch.setattr(sdb, "get_supabase_client",
                        lambda: SimpleNamespace(table=lambda name: _T(name)))

    sdb.register_follow("E2", "Casa", "Ospite", "2026-07-17T15:00:00Z",
                        watchlist_id=9)
    assert upserts and upserts[0].get("record") is True


# ---------------------------------------------------------------------------
# (4) worker ordini tennis — coda DB throttlata, drain locale a ogni tick
# ---------------------------------------------------------------------------
def test_tennis_worker_split_throttle(monkeypatch):
    from Betfair.stream.tennis_live import tennis_live_order_worker as W

    monkeypatch.setattr(W, "_runner_mode", lambda: "PAPER")
    local = {"n": 0}
    monkeypatch.setattr(W, "_process_local_requests",
                        lambda *a, **k: local.__setitem__("n", local["n"] + 1))
    db_calls = {"n": 0}
    monkeypatch.setattr(
        W.tennis_db, "list_pending_tennis_orders",
        lambda limit=5: (db_calls.__setitem__("n", db_calls["n"] + 1) or []))
    monkeypatch.setattr(W, "_last_db_queue_poll", 0.0)
    monkeypatch.setattr(W, "_DB_QUEUE_MIN_INTERVAL_S", 1.0)

    for _ in range(5):                     # 5 tick ravvicinati (~0.15s l'uno)
        W.tennis_live_order_worker({}, object(), None)
    assert local["n"] == 5                 # drain locale SEMPRE (reattività)
    assert db_calls["n"] == 1              # coda DB: una sola lettura nel secondo
    _time.sleep(1.05)
    W.tennis_live_order_worker({}, object(), None)
    assert db_calls["n"] == 2              # scaduto l'intervallo: nuova lettura
