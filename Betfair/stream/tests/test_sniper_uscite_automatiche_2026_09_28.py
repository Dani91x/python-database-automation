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

# 29/09 (CANTIERE N): la proposta passa dal cancello comune
# (``uscite_proposte.proposta_di``): stesse chiavi di tutti i bot di flusso
CHIAVI_PROPOSTA = {"bot", "motivo", "urgente", "market_id", "selection_id", "lato_ingresso",
                   "prezzo", "lato_chiusura", "size_chiusura", "se_chiudi", "se_vince",
                   "se_perde", "chiave", "decided_at"}


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
    assert set(p) == CHIAVI_PROPOSTA
    assert p["motivo"] == "target" and p["lato_chiusura"] == "LAY" and p["lato_ingresso"] == "BACK"
    assert p["prezzo"] == pytest.approx(3.35) and p["size_chiusura"] > 0 and p["se_chiudi"] > 0
    assert p["bot"] == "sniper" and p["chiave"].startswith("scalper|1.234|1221385|sn-")


def test_spento_la_proposta_e_una_sola_anche_su_piu_book():
    s, mkt, _pos = _in_posizione()
    for i in range(5):
        s.process_market_book(mkt, _book(650 + i, bb=3.40, bl=3.45, sb=200))
    assert len(_proposte(s)) == 1
    assert s.stats["uscite_proposte_emesse"] == 1
    assert [p["motivo"] for p in s.stats["uscite_proposte"]] == ["target"]


def test_acceso_la_chiusura_la_mette_il_bot_come_prima():
    s, mkt, pos = _in_posizione(uscite_automatiche=True)
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.close is not None and pos.close.side == "LAY"
    assert pos.close.order_type.price == pytest.approx(3.35)
    assert _proposte(s) == []


def test_acceso_lo_stop_a_n_tick_parte():
    s, mkt, pos = _in_posizione(uscite_automatiche=True)
    # quote SALITE di 2 tick contro il back (3,40 -> 3,50): stop, chiusura garantita
    s.process_market_book(mkt, _book(650, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 1 and pos.flattening is True
    s.process_market_book(mkt, _book(651, bb=3.50, bl=3.55, sb=200))
    assert any(o.side == "LAY" for o in mkt.orders), "chiusura garantita attesa"


def test_spento_lo_stop_a_n_tick_diventa_proposta_e_parte_con_la_firma():
    """29/09 (CANTIERE N, regola dell'utente del 28/09): lo stop e' un'uscita di
    TRADING in perdita. In manuale non parte: proposta coi numeri; con la firma
    (condizione ancora vera) parte al book dopo."""
    s, mkt, pos = _in_posizione()
    s.process_market_book(mkt, _book(650, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 0 and pos.flattening is False and mkt.orders == []
    stop = [p for p in s.stats["uscite_proposte"] if p["motivo"] == "stop"]
    assert len(stop) == 1 and stop[0]["urgente"] is True and stop[0]["se_chiudi"] < 0
    s.cancello_uscite.approva({stop[0]["chiave"]: (KO_MS + 650_500.0) / 1000.0})
    s.process_market_book(mkt, _book(651, bb=3.50, bl=3.55, sb=200))
    assert s.stats["stops"] == 1 and pos.flattening is True


def test_acceso_il_timeout_della_posizione_parte():
    s, mkt, pos = _in_posizione(uscite_automatiche=True)
    pos.entry_fill_pt = KO_MS + 100_000.0          # 550 s fa (> max_pos_s 300)
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert s.stats["timeouts"] == 1
    assert any(o.side == "LAY" for o in mkt.orders), "chiusura garantita attesa"


def test_spento_il_timeout_della_posizione_diventa_proposta():
    """29/09 (CANTIERE N): il timeout ``max_pos_s`` prima scavalcava
    l'interruttore (``_begin_flatten`` diretto); ora in manuale e' una proposta."""
    s, mkt, pos = _in_posizione()
    pos.entry_fill_pt = KO_MS + 100_000.0
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert s.stats["timeouts"] == 0 and pos.flattening is False
    assert not any(o.side == "LAY" for o in mkt.orders)
    assert "timeout" in [p["motivo"] for p in s.stats["uscite_proposte"]]


def test_fuori_finestra_resta_protezione_in_manuale():
    """Fine finestra in-play: la strategia non puo' restare aperta -> chiude."""
    s, mkt, pos = _in_posizione()
    s.inplay_to_s = 100.0                          # finestra gia' chiusa
    s.process_market_book(mkt, _book(650, bb=3.40, bl=3.45, sb=200))
    assert pos.flattening is True


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
    # ciclo nuovo = ingresso NUOVO (la chiave della proposta porta l'ordine)
    pos.entries = [_FakeOrder("BACK", price=3.40, size_matched=10.0, avg=3.40)]
    pos.entry_fill_pt = KO_MS + 652_500.0
    s.process_market_book(mkt, _book(653, bb=3.40, bl=3.45, sb=200))
    assert len(_proposte(s)) == 2
