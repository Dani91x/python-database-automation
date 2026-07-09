"""Test ADVERSARIALI di net_retry (A1 — fix WinError 10035).

Garanzie money-critical:
  - retry SOLO su errori TRANSITORI di rete (WinError 10035/10054/10060, timeout,
    connection reset), MAI su errori applicativi (RLS, CHECK, 4xx, ValueError);
  - backoff esponenziale con tetto; numero di tentativi BOUNDED;
  - l'ultima eccezione viene SEMPRE ri-sollevata (mai un fallimento silenzioso).
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.net_retry import is_transient, with_backoff


# ---------------------------------------------------------------------------
# is_transient — riconoscimento errori
# ---------------------------------------------------------------------------
def _win_oserror(winerror: int) -> OSError:
    e = OSError(f"[WinError {winerror}] operazione socket non bloccante")
    e.winerror = winerror  # type: ignore[attr-defined]
    return e


def test_winerror_10035_is_transient():
    assert is_transient(_win_oserror(10035)) is True


@pytest.mark.parametrize("code", [10054, 10060])
def test_other_socket_winerrors_are_transient(code):
    assert is_transient(_win_oserror(code)) is True


def test_timeout_and_reset_strings_are_transient():
    assert is_transient(Exception("The read operation timed out")) is True
    assert is_transient(Exception("Connection reset by peer")) is True
    assert is_transient(Exception("[WinError 10035] A non-blocking socket operation could not be completed")) is True


def test_nested_cause_is_walked():
    inner = _win_oserror(10035)
    outer = RuntimeError("scrittura fallita")
    outer.__cause__ = inner
    assert is_transient(outer) is True


def test_nested_context_is_walked():
    inner = Exception("connection aborted")
    outer = RuntimeError("boom")
    outer.__context__ = inner
    assert is_transient(outer) is True


def test_application_errors_are_not_transient():
    assert is_transient(ValueError("prezzo non valido")) is False
    assert is_transient(Exception("new row violates check constraint")) is False
    assert is_transient(Exception("permission denied for table")) is False
    assert is_transient(None) is False  # difensivo


def test_cycle_in_exception_chain_terminates():
    a = RuntimeError("a")
    b = RuntimeError("b")
    a.__cause__ = b
    b.__cause__ = a  # ciclo artificiale
    assert is_transient(a) is False  # nessun hang, nessun match


# ---------------------------------------------------------------------------
# with_backoff — retry bounded
# ---------------------------------------------------------------------------
def test_success_first_try_no_sleep():
    sleeps: List[float] = []
    assert with_backoff(lambda: 42, sleep=sleeps.append) == 42
    assert sleeps == []


def test_retries_transient_then_succeeds():
    sleeps: List[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _win_oserror(10035)
        return "ok"

    assert with_backoff(flaky, attempts=4, base_delay=0.1, sleep=sleeps.append) == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.1, 0.2]  # backoff esponenziale


def test_backoff_is_capped():
    sleeps: List[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 5:
            raise _win_oserror(10035)
        return "ok"

    assert with_backoff(flaky, attempts=5, base_delay=0.2, max_delay=0.5, sleep=sleeps.append) == "ok"
    assert sleeps == [0.2, 0.4, 0.5, 0.5]  # cap rispettato


def test_gives_up_after_attempts_and_reraises():
    sleeps: List[float] = []
    calls = {"n": 0}

    def always_fail() -> None:
        calls["n"] += 1
        raise _win_oserror(10035)

    with pytest.raises(OSError):
        with_backoff(always_fail, attempts=3, base_delay=0.05, sleep=sleeps.append)
    assert calls["n"] == 3
    assert len(sleeps) == 2  # nessuno sleep dopo l'ultimo tentativo


def test_non_transient_never_retried():
    calls = {"n": 0}

    def app_error() -> None:
        calls["n"] += 1
        raise ValueError("errore applicativo")

    with pytest.raises(ValueError):
        with_backoff(app_error, attempts=5, sleep=lambda _s: None)
    assert calls["n"] == 1


def test_on_retry_callback_invoked():
    seen: List[Any] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _win_oserror(10035)
        return "ok"

    with_backoff(flaky, sleep=lambda _s: None, on_retry=lambda exc, i: seen.append((type(exc).__name__, i)))
    assert seen == [("OSError", 1)]


# ---------------------------------------------------------------------------
# db_client — client PER-THREAD (fix WinError 10035 alla radice)
# ---------------------------------------------------------------------------
def test_db_client_is_per_thread(monkeypatch):
    import threading

    import db_client

    created: List[str] = []
    monkeypatch.setattr(
        db_client, "create_client",
        lambda url, key: object.__new__(type(f"C{len(created)}", (), {})) or created.append("x") or object(),
    )

    # implementazione robusta del fake: un oggetto nuovo per chiamata
    counter = {"n": 0}

    def _mk(url: str, key: str) -> object:
        counter["n"] += 1
        return object()

    monkeypatch.setattr(db_client, "create_client", _mk)
    monkeypatch.setattr(db_client, "_TLS", threading.local(), raising=False)

    main_a = db_client.get_supabase_client()
    main_b = db_client.get_supabase_client()
    assert main_a is main_b  # stesso thread → stesso client (cache)

    from_thread: List[object] = []
    t = threading.Thread(target=lambda: from_thread.append(db_client.get_supabase_client()))
    t.start()
    t.join()
    assert from_thread[0] is not main_a  # thread diverso → client DIVERSO
    assert counter["n"] == 2
