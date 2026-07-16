"""FIX audit LIVE TRADING 2026-07-16 — gate della scalper_session.

  #5  sniper_profit_target=0 ("nessun tetto profitto", caccia F4) veniva mangiato
      dalla coercizione falsy (`or 0.01`) → il bot si fermava al primo centesimo.
  #7  il gate "THETA solo PAPER" viveva SOLO nel client (ScalperPanel): una
      scalper_control con theta_mode=true + dry_run=false armava il theta con
      ORDINI REALI non validati out-of-sample. Ora il server FORZA il paper.

Helper puri, nessuna rete: si testano direttamente.
"""
from __future__ import annotations

from Betfair.stream.scalper.scalper_session import (
    _sniper_profit_target,
    _theta_dry_run,
)


class _Db:
    def __init__(self) -> None:
        self.logs = []

    def log(self, ev, kind, payload):
        self.logs.append((ev, kind, payload))


# ---------------------------------------------------------------- #5 sniper
def test_profit_target_zero_esplicito_preservato():
    """0 = nessun tetto profitto (F4): va PRESERVATO, mai trasformato in 0.01."""
    assert _sniper_profit_target({"sniper_profit_target": 0}) == 0.0
    assert _sniper_profit_target({"sniper_profit_target": 0.0}) == 0.0


def test_profit_target_assente_usa_default():
    assert _sniper_profit_target({}) == 0.01
    assert _sniper_profit_target({"sniper_profit_target": None}) == 0.01


def test_profit_target_valore_esplicito_passa():
    assert _sniper_profit_target({"sniper_profit_target": 0.5}) == 0.5
    # anche stringhe jsonb numeriche (params arrivano dal DB)
    assert _sniper_profit_target({"sniper_profit_target": "0"}) == 0.0


# ----------------------------------------------------------------- #7 theta
def test_theta_dry_run_paper_resta_paper_senza_log():
    db = _Db()
    assert _theta_dry_run(db, "E1", True) is True
    assert db.logs == []          # nessun warning: era già paper


def test_theta_dry_run_live_forzato_a_paper_con_log_forte():
    db = _Db()
    assert _theta_dry_run(db, "E1", False) is True   # FORZATO in paper
    assert len(db.logs) == 1
    ev, kind, payload = db.logs[0]
    assert ev == "E1" and kind == "warn"
    assert "THETA solo PAPER" in payload["msg"]
