# -*- coding: utf-8 -*-
"""B1 - LADDER E ORDINI A MANO DEL TENNIS TERMINAL (cantiere tetto tennis, passo 4).

Prima ``tennis_live_now.state.order_mode`` era il TETTO del runner
(``TENNIS_LIVE_ORDER_MODE``): ladder, grid, ladder staccato, testata del Terminal
(«LIVE · REALE») e scheda dei bot mandavano/mostravano quella modalita'. Col tetto
LIVE ogni clic sul ladder sarebbe stato REALE al primo avvio, senza nessun gesto.

Ora e' il modo EFFETTIVO (come ``live_now.state.order_mode`` del calcio): LIVE solo
con «Ordini reali» = LIVE scelto in QUESTO avvio dell'app. Il ladder manda il
``mode`` che lo stato dichiara (``LadderView.tsx``: ``mode = orderMode`` minuscolo).

Sessione e capture VERE (``TennisLiveSession``, ``_make_capture``); la riga di
``get_live_settings`` con le chiavi del vero.
"""
from __future__ import annotations

import pytest

from Betfair.stream import modo_ordini as MO
from Betfair.stream.tennis_live import tennis_runner as TR

BOOT = "boot-di-oggi"
EV = "35795993"
MID = "1.248"


def _riga(modo, boot=BOOT):
    return {"id": 1, "kill_switch": False, "order_mode": modo, "order_mode_boot_id": boot,
            "order_mode_updated_at": None, "order_mode_updated_by": None}


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    MO.azzera()
    monkeypatch.setenv("APP_BOOT_ID", BOOT)
    yield
    MO.azzera()


def _stato():
    s = TR.TennisLiveSession(trading=None)
    s.market_meta[EV] = {"market_id": MID, "market_type": "MATCH_ODDS",
                         "market_name": "Match Odds", "selection_names": {}}
    s.capture[EV] = TR._make_capture(MID, EV, market_ids=[MID])
    return TR._build_now_state(s, EV)[0]


@pytest.mark.parametrize("tetto,riga,atteso", [
    ("LIVE", None, "PAPER"),                         # app appena aperta: prova
    ("LIVE", _riga("paper"), "PAPER"),               # «Ordini reali» in prova
    ("LIVE", _riga("live", "boot-di-ieri"), "PAPER"),  # scelta di ieri: non vale
    ("LIVE", _riga("live"), "LIVE"),                 # il gesto di oggi
    ("PAPER", _riga("live"), "PAPER"),               # mai sopra il tetto
    ("OFF", None, "OFF"),
])
def test_lo_stato_del_terminal_dice_il_modo_effettivo(monkeypatch, tetto, riga, atteso):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", tetto)
    if riga is not None:
        MO.registra_settings(riga)
    st = _stato()
    assert st["order_mode"] == atteso
    assert st["order_mode_tetto"] == tetto


def test_lo_stato_porta_tetto_scelta_e_motivo(monkeypatch):
    monkeypatch.setenv("TENNIS_LIVE_ORDER_MODE", "LIVE")
    MO.registra_settings(_riga("live", "boot-di-ieri"))
    st = _stato()
    assert (st["order_mode"], st["order_mode_tetto"], st["order_mode_scelto"],
            st["order_mode_motivo"]) == ("PAPER", "LIVE", None, MO.MOTIVO_AVVIO_DIVERSO)
