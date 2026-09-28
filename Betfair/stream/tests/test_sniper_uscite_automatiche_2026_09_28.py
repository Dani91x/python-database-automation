"""SNIPER e l'interruttore USCITE AUTOMATICHE (R-F2-9, cantiere D2, 28/09).

Reperto del coordinatore: ``sniper_bot.py`` non leggeva MAI
``uscite_automatiche`` (grep = 0) mentre ``scalper_bot.py`` lo rispetta dal
25/09; la sessione (``applica_uscite_automatiche``) lo portava solo al maker.
Lo sniper e' acceso di default dal 25/09: chiudeva sempre da solo.

Si allinea lo sniper alla semantica GIA' ESISTENTE dello scalper
(``test_scalper_uscite_automatiche_2026_09_25.py``), senza inventarne una:
  * spento (DEFAULT): la presa di profitto a +target_ticks NON parte, il bot
    emette 'uscita_proposta' UNA volta per motivo e per ciclo (stesse chiavi);
  * restano SEMPRE automatiche le protezioni: stop a N tick, timeout della
    posizione (come il ``lock_ttl`` dello scalper), force-flat (freno);
  * acceso: comportamento di prima (la chiusura la mette il bot);
  * riacceso a caldo: al book dopo la chiusura la mette il bot.

Finti: quelli del test sniper esistente (ordini con le chiavi di flumine).
"""
from __future__ import annotations

from typing import Any, List

import pytest

from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.tests.test_sniper_bot_2026_07_10 import (
    KO_MS,
    _book,
    _FakeMarket,
    _FakeOrder,
    _strategy,
)

CHIAVI_PROPOSTA_SCALPER = {"motivo", "selection_id", "entry_side", "lato", "prezzo",
                           "size", "bloccabile"}


def _in_posizione(**over: Any):
    s = _strategy(**over)
    mkt = _FakeMarket()
    pos = s._p("1.234", 1221385)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40)]
    pos.entry_fill_pt = KO_MS + 600_000.0
    return s, mkt, pos


def _proposte(s) -> List[dict]:
    return [p for k, p in s._test_events if k == "uscita_proposta"]


@pytest.mark.parametrize("grezzo,atteso", [(None, False), (False, False), (True, True),
                                            ("true", False), (1, False)])
def test_solo_un_booleano_vero_accende(grezzo, atteso):
    over = {} if grezzo is None else {"uscite_automatiche": grezzo}
    assert _strategy(**over).uscite_automatiche is atteso


def test_spento_la_presa_di_profitto_non_parte_e_si_propone():
    s, mkt, pos = _in_posizione()
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.close is None and mkt.orders == []
    prop = _proposte(s)
    assert len(prop) == 1
    p = prop[0]
    assert set(p) == CHIAVI_PROPOSTA_SCALPER
    assert p["motivo"] == "target" and p["lato"] == "LAY" and p["entry_side"] == "BACK"
    assert p["prezzo"] == pytest.approx(3.35) and p["size"] > 0 and p["bloccabile"] > 0


def test_spento_la_proposta_e_una_sola_anche_su_piu_book():
    s, mkt, _pos = _in_posizione()
    for i in range(5):
        s.process_market_book(mkt, _book(650 + i, bb=3.40, bl=3.45, sb=200))
    assert len(_proposte(s)) == 1
    assert s.stats["uscite_proposte"] == 1


def test_acceso_la_chiusura_la_mette_il_bot_come_prima():
    s, mkt, pos = _in_posizione(uscite_automatiche=True)
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.close is not None and pos.close.side == "LAY"
    assert pos.close.order_type.price == pytest.approx(3.35)
    assert _proposte(s) == []


def test_spento_lo_stop_a_n_tick_resta_automatico():
    s, mkt, pos = _in_posizione()
    # quote SALITE di 2 tick contro il back (3,40 -> 3,50): stop, chiusura garantita
    s.process_market_book(mkt, _book(650, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 1 and pos.flattening is True
    assert _proposte(s) == []                      # lo stop non e' una proposta
    # il flatten (protezione) piazza la chiusura al book dopo, da solo
    s.process_market_book(mkt, _book(651, bb=3.50, bl=3.55, sb=200))
    assert any(o.side == "LAY" for o in mkt.orders), "chiusura garantita attesa"


def test_spento_il_timeout_della_posizione_resta_automatico():
    s, mkt, pos = _in_posizione()
    pos.entry_fill_pt = KO_MS + 100_000.0          # 550 s fa (> max_pos_s 300)
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert s.stats["timeouts"] == 1
    assert any(o.side == "LAY" for o in mkt.orders), "chiusura garantita attesa"


@pytest.mark.parametrize("acceso", [False, True])
def test_freno_force_flat_chiude_in_entrambi_i_casi(acceso):
    s, mkt, pos = _in_posizione(uscite_automatiche=acceso)
    s.force_flat = True
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert any(o.side == "LAY" for o in mkt.orders), "chiusura garantita attesa"
    lays = [o for o in mkt.orders if o.side == "LAY"]
    assert lays, "il force-flat deve chiudere anche a uscite manuali"


def test_riaccendere_a_caldo_mette_la_chiusura_al_book_dopo():
    s, mkt, pos = _in_posizione()
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.close is None
    s.uscite_automatiche = True                    # come applica_uscite_automatiche
    s.process_market_book(mkt, _book(651, bb=3.40, bl=3.45, sb=200))
    assert pos.close is not None and pos.close.order_type.price == pytest.approx(3.35)


def test_la_sessione_porta_l_interruttore_anche_allo_sniper():
    """La funzione della sessione (``applica_uscite_automatiche``) sull'istanza
    VERA dello sniper: il valore letto a caldo arriva e si dichiara."""
    class _Db:
        def __init__(self) -> None:
            self.righe: List[tuple] = []

        def log(self, ev, livello, payload):
            self.righe.append((ev, livello, payload))
    s = _strategy()
    db = _Db()
    assert SS.applica_uscite_automatiche(db, "E1", s, {"uscite_automatiche": True}) is True
    assert s.uscite_automatiche is True and len(db.righe) == 1
    assert SS.applica_uscite_automatiche(db, "E1", s, {}) is False
    assert s.uscite_automatiche is False


def test_ciclo_nuovo_proposta_nuova():
    """UNA proposta per motivo E PER CICLO: chiuso il ciclo (fine ciclo dello
    sniper, ``_close_cycle_clock``) il ciclo dopo ne emette una sua."""
    s, mkt, pos = _in_posizione()
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    s.process_market_book(mkt, _book(651, bb=3.40, bl=3.45, sb=200))
    assert len(_proposte(s)) == 1
    s._close_cycle_clock(pos, KO_MS + 652_000.0)       # fine ciclo
    s.process_market_book(mkt, _book(653, bb=3.40, bl=3.45, sb=200))
    assert len(_proposte(s)) == 2
