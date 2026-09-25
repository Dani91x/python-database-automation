"""25/09/2026 - SCALPER CALCIO: L'INTERRUTTORE "USCITE AUTOMATICHE".

Ordine dell'utente (testuale): «Tutti i bot (in live e in paper) DEVONO AVERE
L'ABILITAZIONE per le uscite automatiche [...]; se disattivo il pulsante (TUTTO
IN UI PER SINGOLO BOT), le uscite le gestisco io manualmente».

`uscite_automatiche` (scalper_control.params, whitelist della sessione):
  * True = close a +scalp_ticks, scratch a pari, gamba opposta del maker come
    chiusura, come sempre;
  * False (DEFAULT dal 25/09 sera - ordine dell'utente: «di default tutte le
    uscite le voglio spente»; prima del 25/09 sera il default era True) =
    queste uscite DISCREZIONALI non partono; la posizione resta in LOCKING
    senza chiusura e il bot emette 'uscita_proposta' (una volta); stop a N
    tick / lock_ttl / flatten / pre-KO restano automatici.
La sessione rilegge il valore a caldo a ogni battito
(`scalper_session.applica_uscite_automatiche`).

Finti: `_FakeMarket`/`_FakeOrder` di test_scalper_presize_2026_07_11 (stessi
attributi degli Order flumine usati dal bot). File ASCII-only.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Betfair.stream.scalper import scalper_session as SS
from Betfair.stream.scalper.scalper_bot import (FLATTENING, LOCKING, QUOTING2,
                                                ScalperStrategy)
from Betfair.stream.tests.test_scalper_presize_2026_07_11 import _FakeMarket, _FakeOrder


def _strategy(events, **over):
    params = {"dry_run": False, "stake": 25.0, "stop_ticks": 2}
    params.update(over)
    return ScalperStrategy(market_filter={}, scalper_params=params,
                           event_sink=lambda kind, payload: events.append((kind, payload)))


def _maker_slot(s, eb, el):
    slot = s._slot("1.234", 42)
    slot.status = QUOTING2
    slot.entry_back, slot.entry_lay = eb, el
    slot.t_quote = 1_000
    return slot


def _back_abbinato():
    return _FakeOrder("BACK", price=2.22, size=25.0, size_matched=25.0, avg=2.22, live=False)


def _proposte(events):
    return [p for k, p in events if k == "uscita_proposta"]


# ---------------------------------------------------------------------------
# il parametro
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("grezzo,atteso", [(None, False), (True, True), (False, False),
                                           ("true", False), (1, False)])
def test_solo_un_booleano_vero_accende(grezzo, atteso):
    """25/09 sera: solo un booleano vero ACCENDE (default ora manuale)."""
    params = {} if grezzo is None else {"uscite_automatiche": grezzo}
    s = ScalperStrategy(market_filter={}, scalper_params=params)
    assert s.uscite_automatiche is atteso


def test_la_sessione_accetta_il_parametro_dalla_ui():
    assert "uscite_automatiche" in SS.UI_PARAM_WHITELIST


# ---------------------------------------------------------------------------
# ACCESO = come prima (parita' col test del 10/07)
# ---------------------------------------------------------------------------
def test_acceso_la_gamba_opposta_del_maker_resta_la_chiusura():
    events = []
    # 25/09 sera: `uscite_automatiche` esplicito (default di produzione ora
    # False/manuale).
    s = _strategy(events, uscite_automatiche=True)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    m = _FakeMarket()
    slot = _maker_slot(s, _back_abbinato(), el)
    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)
    assert slot.status == LOCKING and slot.close is el
    assert not m.cancelled and _proposte(events) == []


# ---------------------------------------------------------------------------
# SPENTO = nessuna chiusura, proposta dichiarata
# ---------------------------------------------------------------------------
def test_spento_il_maker_ritira_la_gamba_opposta_e_propone():
    events = []
    s = _strategy(events, uscite_automatiche=False)
    el = _FakeOrder("LAY", price=2.20, size=25.0, live=True)
    m = _FakeMarket()
    slot = _maker_slot(s, _back_abbinato(), el)
    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)
    assert slot.status == LOCKING
    assert slot.close is None, "nessuna chiusura del bot"
    assert m.orders == [], "a mercato non va niente"
    assert [o for o, _ in m.cancelled] == [el], "la gamba opposta si ritira"
    prop = _proposte(events)
    assert len(prop) == 1
    p = prop[0]
    assert p["motivo"] == "target" and p["lato"] == "LAY" and p["entry_side"] == "BACK"
    assert p["prezzo"] == pytest.approx(2.20) and p["size"] > 0 and p["bloccabile"] > 0
    assert slot.t_lock == 2_000, "stop e lock_ttl armati dal fill"


def test_spento_la_proposta_e_una_sola_anche_su_piu_book():
    events = []
    s = _strategy(events, uscite_automatiche=False)
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry, slot.entry_side = _back_abbinato(), "BACK"
    # book sotto il nostro back (2.20/2.22): ne' avverso ne' scratch
    for t in (2_000, 2_500, 3_000):
        if slot.status == LOCKING:
            s._manage(m, None, None, slot, t, 2.20, 2.22, 500.0, 500.0)
        else:
            s._open_lock(m, slot, t, slot.entry, 2.20, 2.22)
    assert len(_proposte(events)) == 1 and m.orders == []


def test_spento_lo_stop_a_n_tick_resta_automatico():
    events = []
    s = _strategy(events, uscite_automatiche=False)
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry, slot.entry_side = _back_abbinato(), "BACK"
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    assert slot.status == LOCKING and slot.close is None
    # il best back sale di 3 tick oltre il nostro back (2.22 -> 2.28): stop
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == FLATTENING
    assert "stop" in [k for k, _ in events]


def test_spento_lo_scratch_a_pari_non_parte_ma_si_propone():
    events = []
    s = _strategy(events, uscite_automatiche=False, scratch_enable=True)
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry, slot.entry_side = _back_abbinato(), "BACK"
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    # il touch torna al nostro prezzo d'ingresso: lo scratch scatterebbe
    s._manage(m, None, None, slot, 2_500, 2.22, 2.24, 500.0, 500.0)
    assert m.orders == [] and slot.close is None and not slot.close_scratched
    assert [p["motivo"] for p in _proposte(events)] == ["target", "scratch"]


# ---------------------------------------------------------------------------
# A CALDO: riaccendere mette la chiusura del bot
# ---------------------------------------------------------------------------
def test_riaccendere_mette_la_chiusura_calcolata_come_sempre():
    events = []
    s = _strategy(events, uscite_automatiche=False)
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry, slot.entry_side = _back_abbinato(), "BACK"
    s._open_lock(m, slot, 2_000, slot.entry, 2.20, 2.22)
    assert m.orders == []
    s.uscite_automatiche = True
    s._manage(m, None, None, slot, 2_500, 2.20, 2.22, 500.0, 500.0)
    assert len(m.orders) == 1 and slot.close is m.orders[0]
    assert m.orders[0].side == "LAY"
    assert m.orders[0].order_type.price == pytest.approx(2.20)


class _DbFinto:
    """Stesse firme di scalper_session.Db.log."""

    def __init__(self):
        self.righe = []

    def log(self, event_id, kind, payload):
        self.righe.append((event_id, kind, payload))


def test_sessione_applica_il_valore_letto_a_caldo():
    db = _DbFinto()
    strat = SimpleNamespace(uscite_automatiche=True)
    assert SS.applica_uscite_automatiche(db, "E1", strat, {"uscite_automatiche": False}) is False
    assert strat.uscite_automatiche is False and len(db.righe) == 1
    # stesso valore: nessun log
    assert SS.applica_uscite_automatiche(db, "E1", strat, {"uscite_automatiche": False}) is None
    assert len(db.righe) == 1
    # lettura fallita: niente cambia
    assert SS.applica_uscite_automatiche(db, "E1", strat, None) is None
    assert strat.uscite_automatiche is False
    # l'utente riaccende esplicito...
    assert SS.applica_uscite_automatiche(db, "E1", strat, {"uscite_automatiche": True}) is True
    assert strat.uscite_automatiche is True
    # ...poi la chiave sparisce / arriva un valore non booleano: DEFAULT dal
    # 25/09 sera (manuale), non piu' "comportamento di sempre" (automatiche).
    assert SS.applica_uscite_automatiche(db, "E1", strat, {"uscite_automatiche": "no"}) is False
    assert strat.uscite_automatiche is False
    assert db.righe[-1][1] == "info" and db.righe[-1][2]["uscite_automatiche"] is False
