"""Test del circuit breaker dello ScorePoller."""
from __future__ import annotations

from typing import List, Optional

from Betfair.stream.scores.base import ScoreSnapshot
from Betfair.stream.scores.poller import ScorePoller


class FakeProvider:
    def __init__(self, name: str, results: List[Optional[ScoreSnapshot]]) -> None:
        self.name = name
        self._results = results
        self._i = 0
        self.calls = 0

    def get_score(self, event_id: str) -> Optional[ScoreSnapshot]:
        self.calls += 1
        if self._i < len(self._results):
            r = self._results[self._i]
            self._i += 1
            return r
        return self._results[-1] if self._results else None

    def healthcheck(self) -> bool:
        return True


def _snap(source: str) -> ScoreSnapshot:
    return ScoreSnapshot(event_id="e", ts="t", source=source, minute=10, score_home=0, score_away=0)


def test_uses_primary_when_healthy():
    primary = FakeProvider("betfair", [_snap("betfair")])
    fallback = FakeProvider("api_football", [_snap("api_football")])
    poller = ScorePoller(primary, fallback, threshold=3)
    snap = poller.poll("e")
    assert snap.source == "betfair"
    assert fallback.calls == 0
    assert not poller.circuit_open


def test_opens_circuit_after_threshold_and_uses_fallback():
    # primario sempre None, fallback ok
    primary = FakeProvider("betfair", [None])
    fallback = FakeProvider("api_football", [_snap("api_football")])
    poller = ScorePoller(primary, fallback, threshold=3)

    # i primi due tick: primario fallisce ma circuito non ancora aperto → fallback usato
    s1 = poller.poll("e")
    assert s1.source == "api_football"
    assert not poller.circuit_open
    poller.poll("e")
    assert not poller.circuit_open
    # terzo tick → soglia raggiunta → circuito aperto
    poller.poll("e")
    assert poller.circuit_open
    assert poller.fallback_count >= 3


def test_half_open_recovers_primary():
    clock_val = {"t": 0.0}

    def clock() -> float:
        return clock_val["t"]

    # primario: 3 fallimenti poi torna sano
    primary = FakeProvider("betfair", [None, None, None, _snap("betfair")])
    fallback = FakeProvider("api_football", [_snap("api_football")])
    poller = ScorePoller(primary, fallback, threshold=3, retry_primary_sec=100, clock=clock)

    poller.poll("e")  # fail1 → fallback
    poller.poll("e")  # fail2 → fallback
    poller.poll("e")  # fail3 → apre circuito, fallback
    assert poller.circuit_open

    # prima del retry window: resta sul fallback (non ritenta il primario)
    clock_val["t"] = 50.0
    s = poller.poll("e")
    assert s.source == "api_football"

    # dopo la finestra: half-open → ritenta il primario, che ora è sano
    clock_val["t"] = 200.0
    s = poller.poll("e")
    assert s.source == "betfair"
    assert not poller.circuit_open


def test_half_open_failed_retry_resets_backoff():
    """Dopo un retry half-open fallito, il primario NON va ritentato a ogni tick."""
    clock_val = {"t": 0.0}

    def clock() -> float:
        return clock_val["t"]

    primary = FakeProvider("betfair", [None])  # sempre None
    fallback = FakeProvider("api_football", [_snap("api_football")])
    poller = ScorePoller(primary, fallback, threshold=3, retry_primary_sec=100, clock=clock)

    for _ in range(3):  # apre il circuito (3 fallimenti consecutivi)
        poller.poll("e")
    assert poller.circuit_open
    calls_open = primary.calls

    clock_val["t"] = 50.0   # dentro la finestra: nessun retry del primario
    poller.poll("e")
    assert primary.calls == calls_open

    clock_val["t"] = 150.0  # finestra trascorsa: half-open retry (fallisce)
    poller.poll("e")
    assert primary.calls == calls_open + 1

    poller.poll("e")        # subito dopo: NON deve ritentare (backoff riavviato)
    assert primary.calls == calls_open + 1

    clock_val["t"] = 260.0  # nuova finestra: ritenta di nuovo
    poller.poll("e")
    assert primary.calls == calls_open + 2


def test_both_down_returns_none():
    primary = FakeProvider("betfair", [None])
    fallback = FakeProvider("api_football", [None])
    poller = ScorePoller(primary, fallback, threshold=1)
    assert poller.poll("e") is None
    assert poller.current_source is None
