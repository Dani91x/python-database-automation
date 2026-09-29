"""CANTIERE N3 (28/09) - una firma PIU' VECCHIA di TTL_APPROVAZIONE_S non esegue.

Reperto del coordinatore (mutazione sopravvissuta): in
``CancelloUscite.lascia_uscire`` la scadenza della firma
(``now_s - firma <= TTL_APPROVAZIONE_S``) si poteva togliere e i test restavano
verdi. Regola (la stessa di Mike, 120 s): la firma data a una proposta vale per
120 s; se la strategia ridecide quell'uscita piu' tardi, la firma e' scaduta:
l'uscita NON parte, la proposta RESTA (stessa nascita) e va firmata di nuovo;
la nuova firma, con la condizione ancora vera, la fa partire.

Per il cancello puro e per ogni bot di flusso: scalper calcio (maker), sniper,
tennis swing, pro, flb, scalper tennis. Finti: quelli delle suite dei bot
(stesse chiavi del vero). La firma ha il tipo che scrive la RPC (ISO) o il
numero che le suite gia' usano: ``_secondi`` li legge entrambi.
"""
from __future__ import annotations

from datetime import datetime, timezone

from Betfair.stream import uscite_proposte as UP

TTL = UP.TTL_APPROVAZIONE_S


def _iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _proposta(s, motivo: str) -> dict:
    return next(p for p in s.stats["uscite_proposte"] if p["motivo"] == motivo)


# ---------------------------------------------------------------- il cancello
def test_cancello_firma_scaduta_non_esegue_la_proposta_resta_e_va_rifirmata():
    eventi = []
    c = UP.CancelloUscite(emetti=lambda ev, p: eventi.append(ev))
    assert c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=10.0,
                           proposta={"motivo": "stop"}) is False
    c.approva({"p|stop": 11.0})                       # firma VALIDA (dopo la nascita)
    assert c.firmata("p|stop")
    # la strategia ridecide lo stop 121 s dopo la firma: scaduta
    assert c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=11.0 + TTL + 1.0,
                           proposta={"motivo": "stop"}) is False
    assert "uscita_eseguita_su_approvazione" not in eventi
    vive = c.vive()
    assert [p["chiave"] for p in vive] == ["p|stop"], "la proposta resta"
    assert vive[0]["decided_at"] == 10.0, "e' la STESSA proposta"
    assert not c.firmata("p|stop"), "la firma scaduta non c'e' piu'"
    # la stessa riga riletta non la rimette
    c.approva({"p|stop": 11.0})
    assert not c.firmata("p|stop")
    # la firma NUOVA la fa partire
    c.approva({"p|stop": 11.0 + TTL + 2.0})
    assert c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=11.0 + TTL + 3.0,
                           proposta={"motivo": "stop"}) is True
    assert eventi[-1] == "uscita_eseguita_su_approvazione"


def test_cancello_firma_al_limite_del_ttl_vale():
    c = UP.CancelloUscite()
    c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=10.0, proposta={})
    c.approva({"p|stop": 11.0})
    assert c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=11.0 + TTL,
                           proposta={}) is True


# ---------------------------------------------------------------- scalper calcio
def test_scalper_maker_stop_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.scalper.scalper_bot import FLATTENING, LOCKING
    from Betfair.stream.tests.test_scalper_uscite_automatiche_2026_09_25 import _in_stop

    events, s, m, slot = _in_stop(False)
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    chiave = _proposta(s, "stop")["chiave"]
    s.cancello_uscite.approva({chiave: 2.6})
    tardi = int((2.6 + TTL + 1.0) * 1000)
    s._manage(m, None, None, slot, tardi, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == LOCKING and "stop" not in [k for k, _ in events]
    assert _proposta(s, "stop")["decided_at"] == 2.5, "la stessa proposta resta"
    s.cancello_uscite.approva({chiave: tardi / 1000.0 + 0.1})
    s._manage(m, None, None, slot, tardi + 200, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == FLATTENING and "stop" in [k for k, _ in events]


def test_sniper_stop_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.tests.test_sniper_bot_2026_07_10 import KO_MS, _book
    from Betfair.stream.tests.test_sniper_uscite_automatiche_2026_09_28 import _in_posizione

    s, mkt, pos = _in_posizione()
    s.process_market_book(mkt, _book(650, bb=3.50, bl=3.55, sb=200))
    chiave = _proposta(s, "stop")["chiave"]
    s.cancello_uscite.approva({chiave: (KO_MS + 650_500.0) / 1000.0})
    tardi_s = 650.5 + TTL + 1.0
    s.process_market_book(mkt, _book(tardi_s, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 0 and pos.flattening is False
    assert _proposta(s, "stop")["chiave"] == chiave, "la proposta resta"
    s.cancello_uscite.approva({chiave: (KO_MS + (tardi_s + 0.2) * 1000.0) / 1000.0})
    s.process_market_book(mkt, _book(tardi_s + 0.5, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 1 and pos.flattening is True


# ---------------------------------------------------------------- tennis
def test_swing_stop_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.tennis_scalper.tests.test_uscite_proposte_bot_tennis_2026_09_28 import (
        _book_stop, _swing_stop)

    s, m = _swing_stop(False)
    s.process_market_book(m, _book_stop(2_000))
    chiave = _proposta(s, "stop")["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_500)})
    tardi = int(2_500 + (TTL + 1.0) * 1000)
    s.process_market_book(m, _book_stop(tardi))
    assert not s._tr["1.1"].get("closing") and m.placed == []
    assert _proposta(s, "stop")["chiave"] == chiave, "la proposta resta"
    s.cancello_uscite.approva({chiave: _iso(tardi + 100)})
    s.process_market_book(m, _book_stop(tardi + 500))
    assert s._tr["1.1"].get("closing") is True and m.placed


def test_pro_stop_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.tennis_scalper.tennis_pro_bot import CLOSING, OPEN
    from Betfair.stream.tennis_scalper.tests.test_uscite_proposte_bot_tennis_2026_09_28 import (
        _pro, _pro_book)

    s, m = _pro(False)
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_000))
    chiave = _proposta(s, "stop")["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_100)})
    tardi = int(2_100 + (TTL + 1.0) * 1000)
    s.process_market_book(m, _pro_book(1.84, 1.85, tardi))
    assert s._trade["1.1"]["state"] == OPEN and m.placed == []
    assert _proposta(s, "stop")["chiave"] == chiave, "la proposta resta"
    s.cancello_uscite.approva({chiave: _iso(tardi + 100)})
    s.process_market_book(m, _pro_book(1.84, 1.85, tardi + 200))
    assert s._trade["1.1"]["state"] == CLOSING and s.stats["stops"] == 1 and m.placed


def test_flb_green_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.tennis_scalper.tests.test_uscite_proposte_bot_tennis_2026_09_28 import (
        _flb, _flb_su)

    def _su(pt_ms: int):
        mb = _flb_su()
        mb.publish_time_epoch = pt_ms              # la chiave che il FLB legge
        return mb

    s, m = _flb(False)
    s.process_market_book(m, _su(2_000))
    chiave = _proposta(s, "green")["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_500)})
    tardi = int(2_500 + (TTL + 1.0) * 1000)
    s.process_market_book(m, _su(tardi))
    assert s._pos_state[("1.1", 111)]["greened"] is False and len(m.placed) == 1
    assert _proposta(s, "green")["chiave"] == chiave, "la proposta resta"
    s.cancello_uscite.approva({chiave: _iso(tardi + 100)})
    s.process_market_book(m, _su(tardi + 200))
    assert s._pos_state[("1.1", 111)]["greened"] is True and len(m.placed) == 2


def test_scalper_tennis_stop_firma_scaduta_non_parte_e_va_rifirmata():
    from Betfair.stream.tennis_scalper.tennis_scalper_bot import FLATTENING, LOCKING
    from Betfair.stream.tennis_scalper.tests.test_uscite_proposte_bot_tennis_2026_09_28 import _ts

    ev, s, m, slot = _ts(False)
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    chiave = _proposta(s, "stop")["chiave"]
    s.cancello_uscite.approva({chiave: 2.6})
    tardi = int((2.6 + TTL + 1.0) * 1000)
    s._manage(m, None, None, slot, tardi, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == LOCKING and "stop" not in [k for k, _ in ev]
    assert _proposta(s, "stop")["chiave"] == chiave, "la proposta resta"
    s.cancello_uscite.approva({chiave: tardi / 1000.0 + 0.1})
    s._manage(m, None, None, slot, tardi + 200, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == FLATTENING
