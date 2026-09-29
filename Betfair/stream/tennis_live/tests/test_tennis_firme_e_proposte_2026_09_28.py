"""CANTIERE N (28/09/2026) - tennis: la FIRMA arriva al bot e la PROPOSTA arriva
alla Control Room.

  * runner: ``_aggiorna_uscite`` (battito, riga per partita gia' letta) passa al
    bot le firme di ``params.uscite_approvate`` (scritte dalla RPC
    ``tennis_bot_approva_uscita``);
  * ponte: ``_stato_auto`` raccoglie le proposte che ogni bot tiene in
    ``stats.uscite_proposte`` (scritte dal runner nel battito) con la partita.

Finti con le chiavi vere delle righe (``tennis_bot_control``). ASCII-only.
"""
from __future__ import annotations

from Betfair.stream import uscite_proposte as UP
from Betfair.stream.tennis_live import tennis_bot_service as S
from Betfair.stream.tennis_live import tennis_runner as TR
from Betfair.stream.tennis_live.tests.test_tennis_auto_mode_2026_09_25 import (  # noqa: F401
    _Db, _Sess, _control, _feed, _follow, _servizio, _stats, runner_db,
)


class _StratCancello:
    def __init__(self) -> None:
        self.uscite_automatiche = False
        self.stats = {}
        self.cancello_uscite = UP.CancelloUscite()


def test_il_runner_passa_la_firma_al_bot(monkeypatch, runner_db):
    s = _StratCancello()
    # 29/09: una firma vale solo per una proposta VIVA nata prima della firma
    s.cancello_uscite.lascia_uscire(automatiche=False, chiave="k",
                                    now_s=UP._secondi("2026-09-28T11:59:00+00:00"),
                                    proposta={"motivo": "stop"})
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    riga = {"event_id": "1", "bot_key": "tennis_swing", "uscite_automatiche": False,
            "params": {"soglia": 2, UP.CHIAVE_FIRME: {"k": "2026-09-28T12:00:00+00:00"}}}
    TR._aggiorna_uscite(None, _Sess(), ("1", "tennis_swing"), s, riga)
    assert "k" in s.cancello_uscite.approvate


def test_senza_firme_o_senza_params_niente(monkeypatch, runner_db):
    s = _StratCancello()
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    TR._aggiorna_uscite(None, _Sess(), ("1", "tennis_swing"), s,
                        {"event_id": "1", "bot_key": "tennis_swing", "params": None})
    assert s.cancello_uscite.approvate == {}


def test_il_ponte_porta_le_proposte_in_control_room():
    prop = {"chiave": "tennis_swing|1.1|11|1000|stop", "motivo": "stop", "se_chiudi": -0.4}
    db = _Db([_servizio(con_uscite=True, uscite=False)],
             controls=[_control("1", uscite=False, stats={UP.CHIAVE_STATS: [prop]})],
             follows=[_follow("1", origine="auto")], feed=[_feed("1")])
    S.riconcilia_interruttori(db)
    viste = _stats(db)["auto"]["uscite_proposte"]
    assert viste == [{**prop, "event_id": "1"}]


def test_il_messaggio_all_utente_dice_il_vero(monkeypatch, runner_db):
    """29/09 (reperto E del revisore): prima diceva "stop e protezioni restano";
    da oggi in manuale stop, time-stop e uscita strutturale sono proposte."""
    s = _StratCancello()
    s.uscite_automatiche = True
    monkeypatch.setattr(TR, "_strategy_is_flat", lambda fl, st: True)
    TR._aggiorna_uscite(None, _Sess(), ("1", "tennis_pro"), s,
                        {"event_id": "1", "bot_key": "tennis_pro", "uscite_automatiche": False})
    nota = runner_db[-1][3]["note"]
    assert "stop" in nota and "PROPOSTA" in nota
    assert "restano" not in nota.split(";")[0], nota
