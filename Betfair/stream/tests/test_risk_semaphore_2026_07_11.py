"""F5 review 11/07 — semaforo di rischio UNICO per evento (versione minima).

Il killer del multi-colpo/multi-linea e' il GOL: la sospensione in-play arma
un halt sui NUOVI ingressi di TUTTE le strategie per un cooldown; le chiusure
passano sempre. Il colpo live del 10/07 alle 43.5' (fire nella turbolenza
post-gol → stop in 16s) sarebbe stato fermato da questo semaforo.
"""
from __future__ import annotations

from types import SimpleNamespace

from Betfair.stream.scalper.risk_semaphore import (
    EventRiskSemaphore,
    notice_suspension,
)


def test_sospensione_arma_e_scade():
    events = []
    sem = EventRiskSemaphore(post_suspension_cooldown_s=120.0,
                             emit=lambda k, p: events.append((k, p)))
    assert sem.entries_halted(1_000_000) is False
    sem.on_suspension(1_000_000)
    assert sem.entries_halted(1_000_000 + 1) is True
    assert sem.entries_halted(1_000_000 + 119_000) is True
    assert sem.entries_halted(1_000_000 + 121_000) is False
    assert [k for k, _ in events] == ["risk_halt"]


def test_sospensioni_ripetute_estendono_senza_spam():
    """Il gol tiene i mercati sospesi vari secondi: ogni segnale estende
    l'halt (decorre dall'ULTIMO), ma l'evento risk_halt esce UNA volta per
    periodo caldo."""
    events = []
    sem = EventRiskSemaphore(post_suspension_cooldown_s=120.0,
                             emit=lambda k, p: events.append((k, p)))
    sem.on_suspension(1_000_000)
    sem.on_suspension(1_005_000)   # 5s dopo, halt ancora attivo → estende
    assert sem.entries_halted(1_000_000 + 121_000) is True   # esteso
    assert sem.entries_halted(1_005_000 + 121_000) is False
    assert len([k for k, _ in events if k == "risk_halt"]) == 1


def test_cooldown_zero_disattiva():
    sem = EventRiskSemaphore(post_suspension_cooldown_s=0.0)
    sem.on_suspension(1_000_000)
    assert sem.entries_halted(1_000_001) is False


def test_notice_suspension_solo_inplay():
    sem = EventRiskSemaphore(post_suspension_cooldown_s=120.0)
    # pre-match SUSPENDED (routine, non gol) → NON arma
    pre = SimpleNamespace(status="SUSPENDED", inplay=False,
                          publish_time_epoch=1_000_000.0)
    notice_suspension(sem, pre)
    assert sem.entries_halted(1_000_001) is False
    # in-play SUSPENDED (gol) → arma
    live = SimpleNamespace(status="SUSPENDED", inplay=True,
                           publish_time_epoch=2_000_000.0)
    notice_suspension(sem, live)
    assert sem.entries_halted(2_000_001) is True
    # None-safe
    notice_suspension(None, live)


def test_sniper_book_sospeso_arma_il_semaforo_condiviso():
    """check_market_book dello sniper con book SUSPENDED in-play arma il
    semaforo condiviso (e rifiuta il book come prima)."""
    from Betfair.stream.scalper.sniper_bot import SniperStrategy

    s = SniperStrategy(market_filter={}, sniper_params={"stake": 5.0})
    sem = EventRiskSemaphore(post_suspension_cooldown_s=120.0)
    s.risk_sem = sem
    book = SimpleNamespace(status="SUSPENDED", inplay=True,
                           publish_time_epoch=5_000_000.0,
                           market_id="1.234", runners=[1],
                           market_definition=SimpleNamespace(
                               market_type="OVER_UNDER_15"))
    assert s.check_market_book(SimpleNamespace(market_id="1.234"), book) is False
    assert sem.entries_halted(5_000_001) is True
