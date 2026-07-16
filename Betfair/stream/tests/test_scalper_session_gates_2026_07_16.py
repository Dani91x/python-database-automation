"""FIX audit LIVE TRADING 2026-07-16 — gate della scalper_session.

  #5  sniper_profit_target=0 ("nessun tetto profitto", caccia F4) veniva mangiato
      dalla coercizione falsy (`or 0.01`) → il bot si fermava al primo centesimo.
  #7  il gate "THETA solo PAPER" viveva SOLO nel client (ScalperPanel): una
      scalper_control con theta_mode=true + dry_run=false armava il theta con
      ORDINI REALI non validati out-of-sample. Ora il server FORZA il paper.

REGOLA SPECCHIO (16/07 sera): la DEMO della sessione scalper non è più uno
snapshot — control.dry_run=true → client flumine ``paper_trade=True`` e
strategie PIENE (ordini SIMULATI, ciclo completo). Gate money-critical:
  * _order_client_kwargs: paper_trade segue ESATTAMENTE session_paper;
  * _theta_dry_run: theta PIENO in demo, MAI reale in live;
  * _handle_flumine_crash: lo sweep REST market-wide (cancella ordini del
    CONTO, anche di altri processi) parte SOLO in LIVE;
  * _make_session_mirror: specchia SOLO ordini, MAI posizioni (due scrittori
    su betfair_live_positions si sovrascriverebbero col runner).

Helper puri, nessuna rete: si testano direttamente.
"""
from __future__ import annotations

from types import SimpleNamespace

from Betfair.stream.scalper.scalper_session import (
    _handle_flumine_crash,
    _make_session_mirror,
    _order_client_kwargs,
    _order_mirror_loop,
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
def test_theta_dry_run_demo_gira_pieno_senza_log():
    """Regola specchio: in sessione DEMO (client paper) il theta piazza ordini
    SIMULATI con ciclo completo — dry_run=False, nessun warning."""
    db = _Db()
    assert _theta_dry_run(db, "E1", True) is False
    assert db.logs == []


def test_theta_dry_run_live_forzato_a_paper_con_log_forte():
    """Invariante S4 immutato: theta MAI con soldi veri."""
    db = _Db()
    assert _theta_dry_run(db, "E1", False) is True   # FORZATO in dry-run
    assert len(db.logs) == 1
    ev, kind, payload = db.logs[0]
    assert ev == "E1" and kind == "warn"
    assert "THETA solo PAPER" in payload["msg"]


# ------------------------------------------------- regola specchio: client
def test_order_client_kwargs_demo_e_paper_trade():
    kw = _order_client_kwargs(True)
    assert kw["paper_trade"] is True
    assert kw["order_stream"] is True          # SimulatedOrderStream (fill async)
    assert kw["min_bet_validation"] is False   # come il runner (CRITICAL-3)


def test_order_client_kwargs_live_invariato():
    kw = _order_client_kwargs(False)
    assert kw["paper_trade"] is False
    assert kw["order_stream"] is True
    assert kw["min_bet_validation"] is False


# --------------------------------------- regola specchio: sweep solo LIVE
class _Trading:
    def __init__(self) -> None:
        self.cancelled = []
        self.betting = SimpleNamespace(
            cancel_orders=lambda market_id: self.cancelled.append(market_id))


def test_crash_paper_non_fa_mai_sweep_rest():
    """MONEY-CRITICAL: lo sweep REST è market-wide sul CONTO — in paper
    cancellerebbe ordini REALI di altri processi. Mai eseguirlo."""
    db, trading = _Db(), _Trading()
    _handle_flumine_crash(db, "E1", trading, ["1.1", "1.2"], session_paper=True)
    assert trading.cancelled == []
    assert any("PAPER" in p["msg"] for _, _, p in db.logs)


def test_crash_live_esegue_sweep_su_tutti_i_mercati():
    db, trading = _Db(), _Trading()
    db.sb = SimpleNamespace(table=lambda *_: SimpleNamespace(
        insert=lambda row: SimpleNamespace(execute=lambda: None)))
    _handle_flumine_crash(db, "E1", trading, ["1.1", "1.2"], session_paper=False)
    assert trading.cancelled == ["1.1", "1.2"]
    assert any("sweep cancel eseguito" in p["msg"] for _, _, p in db.logs)


# ------------------------------------- regola specchio: mirror solo-ordini
def test_session_mirror_non_scrive_mai_posizioni():
    """Il mirror della sessione specchia SOLO ordini: _position_row è
    neutralizzata (betfair_live_positions resta del runner live)."""
    mirror = _make_session_mirror(["1.1"], "paper")
    assert mirror.mode == "paper"
    assert mirror._position_row("m", "ev", "1.1", 47999, 0.0) is None


def test_session_mirror_mode_live():
    assert _make_session_mirror(["1.1"], "live").mode == "live"


def test_session_mirror_mai_riconciliazione_per_bet_id():
    """Fix HIGH review 16/07: in PAPER i bet_id simulati NON sono univoci tra
    sessioni — il lookup per bet_id aggancerebbe la riga di un ALTRO ordine.
    Il mirror di sessione NON deve mai riconciliare: riga sempre invariata,
    dbm mai interrogato (dbm=None esploderebbe se venisse usato)."""
    mirror = _make_session_mirror(["1.1"], "paper")
    row = {"bet_id": "100000000001", "client_order_ref": "hash-uuid-1"}
    assert mirror._reconcile_ref_by_bet(None, row) is row


def test_order_mirror_loop_passa_gli_ordini_del_blotter():
    """Un giro di loop: gli ordini di ogni blotter arrivano al mirror
    (qualunque strategia); poi lo stop_flag ferma il thread."""
    seen = []

    class _Mirror:
        def process_orders(self, market, orders):
            seen.append((market.market_id, list(orders)))

    class _Flag:
        def __init__(self) -> None:
            self._n = 0

        def is_set(self) -> bool:
            self._n += 1
            return self._n > 1          # un solo giro

        def wait(self, _s) -> None:
            return None

    market = SimpleNamespace(market_id="1.1", blotter=["o1", "o2"])
    framework = SimpleNamespace(markets=[market])
    _order_mirror_loop(_Mirror(), framework, _Flag(), tick_s=0.0)
    assert seen == [("1.1", ["o1", "o2"])]
