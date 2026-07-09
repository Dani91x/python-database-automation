"""Test ADVERSARIALI del watchdog (A5 — sentinella del runner di trading live).

NESSUN processo reale e NESSUNA rete: Popen, sleep, clock, alert, heartbeat e
telegram sono fake iniettati. Sotto test le garanzie money-critical:
  - uscita PULITA (rc 0) → MAI riavvio (decisione utente: niente h24 automatico);
  - lock di singola istanza (rc != 0 con uptime sotto grace) → WARN e stop,
    MAI un loop di riavvii contro il lock;
  - CRASH → riavvio con backoff esponenziale + alert CRITICAL + telegram;
  - tetto riavvii/ora (finestra scorrevole) → "SERVE INTERVENTO MANUALE" + exit 1;
  - alert/heartbeat/telegram che sollevano NON fanno mai morire il watchdog.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import Betfair.stream.watchdog as wd


# ---------------------------------------------------------------------------
# Fake: processo figlio, factory Popen, clock (now+sleep coerenti)
# ---------------------------------------------------------------------------
class _FakeProc:
    """Figlio fake: ``poll()`` consuma una sequenza di valori (None = ancora vivo,
    int = exit code). L'ultimo valore della sequenza resta 'appiccicato'."""

    def __init__(self, polls: List[Optional[int]]) -> None:
        assert polls, "sequenza poll vuota"
        self._polls = list(polls)
        self.returncode: Optional[int] = None

    def poll(self) -> Optional[int]:
        v = self._polls.pop(0) if len(self._polls) > 1 else self._polls[0]
        if v is not None:
            self.returncode = v
        return v


class _FakePopen:
    """Factory Popen fake: uno ``spawns[i]`` (sequenza di poll) per ogni lancio."""

    def __init__(self, spawns: List[List[Optional[int]]]) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._spawns = [list(s) for s in spawns]

    def __call__(self, cmd: List[str], cwd: Any = None, **kw: Any) -> _FakeProc:
        self.calls.append({"cmd": list(cmd), "cwd": cwd})
        assert self._spawns, "spawn INATTESO: il watchdog ha rilanciato troppe volte"
        return _FakeProc(self._spawns.pop(0))


class _FakeClock:
    """now() monotonic fake; sleep() registra la durata E avanza il tempo."""

    def __init__(self) -> None:
        self.t = 1_000.0
        self.sleeps: List[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, sec: float) -> None:
        self.sleeps.append(float(sec))
        self.t += float(sec)


def _run(
    monkeypatch: Any,
    spawns: List[List[Optional[int]]],
    argv: Optional[List[str]] = None,
    *,
    grace: float = 5.0,
    max_per_hour: int = 5,
    hb_sec: float = 30.0,
    alert: Any = None,
    heartbeat: Any = None,
    telegram: Any = None,
    max_cycles: Optional[int] = 20,
) -> Tuple[int, List[Tuple[str, str]], List[str], List[int], _FakePopen, _FakeClock]:
    """Esegue run_watchdog in ambiente ERMETICO (env pinnata, tutto fake)."""
    monkeypatch.setenv("WATCHDOG_MAX_RESTARTS_PER_HOUR", str(max_per_hour))
    monkeypatch.setenv("WATCHDOG_BACKOFF_BASE_SEC", "10")
    monkeypatch.setenv("WATCHDOG_BACKOFF_CAP_SEC", "300")
    monkeypatch.setenv("WATCHDOG_LOCK_GRACE_SEC", str(grace))
    monkeypatch.setenv("WATCHDOG_HEARTBEAT_SEC", str(hb_sec))
    alerts: List[Tuple[str, str]] = []
    telegrams: List[str] = []
    heartbeats: List[int] = []
    popen = _FakePopen(spawns)
    clock = _FakeClock()
    rc = wd.run_watchdog(
        argv or [],
        popen=popen,
        sleep=clock.sleep,
        now=clock.now,
        alert=alert if alert is not None else (lambda lv, msg: alerts.append((lv, msg))),
        heartbeat=heartbeat if heartbeat is not None else (lambda: heartbeats.append(1)),
        telegram=telegram if telegram is not None else telegrams.append,
        max_cycles=max_cycles,
    )
    return rc, alerts, telegrams, heartbeats, popen, clock


# ---------------------------------------------------------------------------
# 1) classify_exit — funzione pura
# ---------------------------------------------------------------------------
class TestClassifyExit:
    def test_rc_zero_e_clean_anche_con_uptime_lungo(self) -> None:
        assert wd.classify_exit(0, 0.5) == "clean"
        assert wd.classify_exit(0, 3_600.0) == "clean"
        assert wd.classify_exit(0, 18 * 3_600.0) == "clean"

    def test_rc_nonzero_uptime_brevissimo_e_lock(self) -> None:
        # lock porta (single_instance): SystemExit → rc 1 in pochi istanti
        assert wd.classify_exit(1, 2.0) == "lock"
        assert wd.classify_exit(1, 0.0) == "lock"

    def test_rc_nonzero_uptime_lungo_e_crash(self) -> None:
        assert wd.classify_exit(1, 60.0) == "crash"
        assert wd.classify_exit(1, 5.0) == "crash"  # bordo: uptime == grace NON è lock

    def test_altri_exit_code_sono_crash(self) -> None:
        assert wd.classify_exit(-9, 120.0) == "crash"   # SIGKILL
        assert wd.classify_exit(2, 999.0) == "crash"
        assert wd.classify_exit(-9, 1.0) == "lock"      # sotto grace resta lock (mai loop)

    def test_grace_personalizzata(self) -> None:
        assert wd.classify_exit(1, 8.0, lock_grace_sec=10.0) == "lock"
        assert wd.classify_exit(1, 12.0, lock_grace_sec=10.0) == "crash"


# ---------------------------------------------------------------------------
# 2) next_backoff — 1-BASED (dichiarato nel docstring): 1° crash → base
# ---------------------------------------------------------------------------
class TestNextBackoff:
    def test_progressione_esponenziale(self) -> None:
        assert wd.next_backoff(1) == 10.0
        assert wd.next_backoff(2) == 20.0
        assert wd.next_backoff(3) == 40.0
        assert wd.next_backoff(4) == 80.0
        assert wd.next_backoff(5) == 160.0

    def test_cap_a_300(self) -> None:
        assert wd.next_backoff(6) == 300.0   # 10*2^5 = 320 → cap
        assert wd.next_backoff(50) == 300.0  # niente overflow / esplosioni

    def test_docstring_dichiara_la_convenzione(self) -> None:
        assert "1-based" in (wd.next_backoff.__doc__ or "")

    def test_input_degeneri_non_scendono_sotto_base(self) -> None:
        assert wd.next_backoff(0) == 10.0
        assert wd.next_backoff(-3) == 10.0

    def test_base_e_cap_personalizzati(self) -> None:
        assert wd.next_backoff(1, base=5.0, cap=60.0) == 5.0
        assert wd.next_backoff(4, base=5.0, cap=60.0) == 40.0
        assert wd.next_backoff(5, base=5.0, cap=60.0) == 60.0


# ---------------------------------------------------------------------------
# 3) should_restart — finestra scorrevole di 1 ora su timestamp monotonic
# ---------------------------------------------------------------------------
class TestShouldRestart:
    def test_nessun_riavvio_precedente(self) -> None:
        assert wd.should_restart([], now=10_000.0, max_per_hour=5) is True

    def test_cap_raggiunto_nella_finestra(self) -> None:
        now = 10_000.0
        ts = [now - 60.0 * i for i in range(1, 6)]  # 5 riavvii negli ultimi 5 min
        assert wd.should_restart(ts, now=now, max_per_hour=5) is False
        assert wd.should_restart(ts, now=now, max_per_hour=6) is True

    def test_ts_vecchi_oltre_1h_non_contano(self) -> None:
        now = 10_000.0
        vecchi = [now - 3_700.0, now - 7_200.0]           # fuori finestra
        assert wd.should_restart(vecchi + [now - 30.0], now=now, max_per_hour=2) is True
        assert wd.should_restart([now - 3_600.0], now=now, max_per_hour=1) is True  # bordo: esattamente 1h = fuori

    def test_cap_a_uno(self) -> None:
        now = 10_000.0
        assert wd.should_restart([], now=now, max_per_hour=1) is True
        assert wd.should_restart([now - 10.0], now=now, max_per_hour=1) is False


# ---------------------------------------------------------------------------
# 4) uscita pulita → stop del watchdog, NESSUN riavvio
# ---------------------------------------------------------------------------
def test_uscita_pulita_nessun_riavvio(monkeypatch: Any) -> None:
    rc, alerts, telegrams, _hb, popen, clock = _run(monkeypatch, spawns=[[None, 0]])
    assert rc == 0
    assert len(popen.calls) == 1, "MAI riavviare un runner uscito pulito"
    assert [lv for lv, _ in alerts] == ["INFO"]
    assert "pulito" in alerts[0][1]
    assert telegrams == []
    assert all(s != 10.0 for s in clock.sleeps), "nessun backoff atteso"


# ---------------------------------------------------------------------------
# 5) crash x2 poi uscita pulita → 3 spawn, backoff 10 poi 20
# ---------------------------------------------------------------------------
def test_crash_due_volte_poi_pulito(monkeypatch: Any) -> None:
    # grace=0: qualunque rc != 0 è un crash anche se il figlio muore subito →
    # gli unici sleep del test sono i backoff (niente sleep di heartbeat).
    rc, alerts, _tg, _hb, popen, clock = _run(
        monkeypatch, spawns=[[1], [1], [0]], grace=0.0,
    )
    assert rc == 0
    assert len(popen.calls) == 3
    critici = [msg for lv, msg in alerts if lv == "CRITICAL"]
    assert len(critici) == 2
    assert "exit code 1" in critici[0]
    assert "Riavvio n. 1" in critici[0] and "10" in critici[0]
    assert "Riavvio n. 2" in critici[1] and "20" in critici[1]
    assert clock.sleeps == [10.0, 20.0], "backoff esponenziale 10 → 20"
    assert alerts[-1][0] == "INFO"  # chiusura pulita finale


# ---------------------------------------------------------------------------
# 6) lock porta (rc 1, uptime < grace) → WARN e stop, nessun riavvio
# ---------------------------------------------------------------------------
def test_lock_porta_warn_e_stop(monkeypatch: Any) -> None:
    # il figlio muore al primo poll → uptime 0 < grace 5 → "già attivo"
    rc, alerts, telegrams, _hb, popen, clock = _run(monkeypatch, spawns=[[1]], grace=5.0)
    assert rc == 0
    assert len(popen.calls) == 1, "MAI loop di riavvii contro il lock"
    assert [lv for lv, _ in alerts] == ["WARN"]
    assert "già attivo" in alerts[0][1]
    assert telegrams == []
    assert clock.sleeps == []


# ---------------------------------------------------------------------------
# 7) tetto riavvii/ora → alert MANUALE + exit 1
# ---------------------------------------------------------------------------
def test_cap_riavvii_ora_serve_intervento_manuale(monkeypatch: Any) -> None:
    rc, alerts, telegrams, _hb, popen, _clock = _run(
        monkeypatch, spawns=[[2], [2]], grace=0.0, max_per_hour=1,
    )
    assert rc == 1
    assert len(popen.calls) == 2  # 1° lancio + 1 unico riavvio permesso
    manuali = [msg for lv, msg in alerts if lv == "CRITICAL" and "MANUALE" in msg]
    assert len(manuali) == 1
    assert any("MANUALE" in t for t in telegrams), "notifica FORTE anche via telegram"


# ---------------------------------------------------------------------------
# 8) telegram sui crash + heartbeat durante l'attesa
# ---------------------------------------------------------------------------
def test_telegram_su_crash_e_heartbeat_durante_attesa(monkeypatch: Any) -> None:
    # 1° figlio vive 2 giri di heartbeat (2×30s → uptime 60 > grace) poi crasha
    rc, alerts, telegrams, heartbeats, popen, _clock = _run(
        monkeypatch, spawns=[[None, None, 1], [0]], hb_sec=30.0,
    )
    assert rc == 0
    assert len(popen.calls) == 2
    assert len(heartbeats) >= 2, "heartbeat scritto mentre il figlio gira"
    assert len(telegrams) == 1 and "exit code 1" in telegrams[0]
    assert [lv for lv, _ in alerts] == ["CRITICAL", "INFO"]


# ---------------------------------------------------------------------------
# 9) argv dopo `--` cambia il modulo target
# ---------------------------------------------------------------------------
def test_argv_dopo_doppio_trattino_cambia_target(monkeypatch: Any) -> None:
    rc, _a, _t, _h, popen, _c = _run(
        monkeypatch,
        spawns=[[0]],
        argv=["--", "Betfair.stream.tennis_live.tennis_runner", "--evento", "X1"],
    )
    assert rc == 0
    cmd = popen.calls[0]["cmd"]
    assert cmd == [
        sys.executable, "-m",
        "Betfair.stream.tennis_live.tennis_runner", "--evento", "X1",
    ]


def test_default_target_e_cwd_radice_repo(monkeypatch: Any) -> None:
    rc, _a, _t, _h, popen, _c = _run(monkeypatch, spawns=[[0]], argv=[])
    assert rc == 0
    assert popen.calls[0]["cmd"] == [sys.executable, "-m", "Betfair.stream.runner"]
    # cwd = radice del repo (parent di Betfair/) → gli import `-m` funzionano
    atteso = str(Path(wd.__file__).resolve().parents[2])
    assert popen.calls[0]["cwd"] == atteso


# ---------------------------------------------------------------------------
# 10) alert/heartbeat/telegram che sollevano NON uccidono il watchdog
# ---------------------------------------------------------------------------
def test_callback_che_sollevano_non_uccidono_il_watchdog(monkeypatch: Any) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("DB/telegram giù")

    rc, _alerts, _tg, _hb, popen, clock = _run(
        monkeypatch,
        spawns=[[None, 1], [0]],  # crash (uptime 30 > grace) poi uscita pulita
        alert=_boom,
        heartbeat=_boom,
        telegram=_boom,
    )
    assert rc == 0, "il watchdog sopravvive a DB e telegram giù"
    assert len(popen.calls) == 2, "il riavvio avviene comunque"
    assert 10.0 in clock.sleeps  # il backoff del crash c'è stato
