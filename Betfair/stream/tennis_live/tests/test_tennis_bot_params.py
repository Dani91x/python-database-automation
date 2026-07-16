"""Fix 2026-07-09: lo scalper armato dalla UI deve partire col PRESET TENNIS.

BUG: ``_instantiate_bot`` passava al bot SOLO i params del control (UI) → i default
di classe restavano quelli CALCIO: ``max_signal_ticks=4`` (l'anti-gap blocca ogni
punto tennis, che muove 2-6 tick), ``max_spread_ticks=2``, ``min_size=150``,
``price 1.50-4.6`` e — in LIVE — NESSUNA blindatura .it (``size_step``/``live_min_bet``):
un green-up con size non multipla di 0,50 € veniva RIFIUTATO da Betfair.it lasciando
la posizione SCOPERTA. Ora la base è ``run_tennis_scalper.TENNIS_PARAMS`` (preset
validato); i valori del control hanno la precedenza.
"""
from __future__ import annotations

from betfairlightweight.filters import streaming_market_data_filter

from Betfair.stream.tennis_live import tennis_runner


def _mk(mode: str = "PAPER", params: dict | None = None, dry_run: bool = False):
    df = streaming_market_data_filter(fields=["EX_BEST_OFFERS"], ladder_levels=3)
    return tennis_runner._instantiate_bot(
        "tennis_scalper",
        {"stake": 2.0, "dry_run": dry_run, "params": params or {}},
        "1.100", {}, lambda *a, **k: None, df, mode,
    )


def test_scalper_gets_tennis_preset_not_calcio_defaults():
    bot = _mk()
    # calibrazione tennis (un punto = 2-6 tick; i default calcio bloccavano tutto)
    assert bot.max_signal_ticks == 10.0
    assert bot.max_spread_ticks == 6
    assert bot.join_max_spread == 3
    assert bot.capture_max_ticks == 20
    assert bot.min_size == 5.0
    assert bot.price_min == 1.20
    assert bot.price_max == 6.0
    assert bot.allow_inplay is True


def test_scalper_paper_zeroes_it_stake_rules():
    bot = _mk("PAPER")
    # in simulazione i fill sono a size esatte: green-up esatti, cicli completi
    assert bot.size_step == 0.0
    assert bot.live_min_bet == 0.0


def test_scalper_live_keeps_it_stake_rules():
    bot = _mk("LIVE")
    # blindature Betfair.it: multipli di 0,50 € + over-hedge dei close sotto minimo
    assert bot.size_step == 0.5
    assert bot.live_min_bet == 2.0
    assert bot.max_txn_hour == 300


def test_ui_params_override_preset():
    bot = _mk(params={"max_signal_ticks": 7.0, "price_max": 4.0})
    assert bot.max_signal_ticks == 7.0
    assert bot.price_max == 4.0


def test_dry_run_forced_only_when_off():
    """Regola specchio 16/07: in PAPER dry_run=False è AMMESSO (ordini simulati per
    costruzione, visibili sul ladder); il kill-switch forza dry_run solo con OFF."""
    assert _mk("PAPER", dry_run=False).dry_run is False
    assert _mk("PAPER", dry_run=True).dry_run is True
    assert _mk("OFF", dry_run=False).dry_run is True  # kill-switch invariato
