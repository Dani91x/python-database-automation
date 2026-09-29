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
    # 28/09 (CANTIERE N): le chiavi comuni a tutti i bot (uscite_proposte.proposta_di)
    assert p["motivo"] == "target" and p["lato_chiusura"] == "LAY" and p["lato_ingresso"] == "BACK"
    assert p["prezzo"] == pytest.approx(2.20) and p["size_chiusura"] > 0 and p["se_chiudi"] > 0
    assert slot.t_lock == 2_000, "i timer di stop e lock_ttl partono dal fill"
    assert s.stats["uscite_proposte"][0]["chiave"] == p["chiave"]


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


def _in_stop(auto: bool):
    events = []
    s = _strategy(events, uscite_automatiche=auto)
    m = _FakeMarket()
    slot = s._slot("1.234", 42)
    slot.entry, slot.entry_side = _back_abbinato(), "BACK"
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    return events, s, m, slot


def test_acceso_lo_stop_a_n_tick_parte():
    events, s, m, slot = _in_stop(True)
    # il best back sale di 3 tick oltre il nostro back (2.22 -> 2.28): stop
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == FLATTENING
    assert "stop" in [k for k, _ in events]


def test_spento_lo_stop_a_n_tick_diventa_proposta():
    """28/09 (CANTIERE N, regola dell'utente): lo stop e' un'uscita di TRADING
    in perdita. A uscite manuali la posizione resta: nasce la proposta coi
    numeri (chiusura a mercato adesso) e parte solo con la firma."""
    events, s, m, slot = _in_stop(False)
    assert slot.status == LOCKING and slot.close is None
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == LOCKING and "stop" not in [k for k, _ in events]
    stop = [p for p in s.stats["uscite_proposte"] if p["motivo"] == "stop"]
    assert len(stop) == 1 and stop[0]["urgente"] is True and stop[0]["se_chiudi"] < 0
    # l'utente firma: al book dopo, se lo stop vale ancora, parte
    s.cancello_uscite.approva({stop[0]["chiave"]: 2.6})
    s._manage(m, None, None, slot, 2_700, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == FLATTENING and "stop" in [k for k, _ in events]


def test_spento_stop_firmato_ma_rientrato_non_parte():
    events, s, m, slot = _in_stop(False)
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    chiave = next(p["chiave"] for p in s.stats["uscite_proposte"] if p["motivo"] == "stop")
    s._manage(m, None, None, slot, 2_600, 2.20, 2.22, 500.0, 500.0)   # rientrato
    assert [p["motivo"] for p in s.stats["uscite_proposte"]] == ["target"]
    s.cancello_uscite.approva({chiave: 2.65})
    s._manage(m, None, None, slot, 2_700, 2.20, 2.22, 500.0, 500.0)
    assert slot.status == LOCKING and m.orders == []


def test_spento_il_timeout_lock_ttl_diventa_proposta():
    events, s, m, slot = _in_stop(False)
    s._manage(m, None, None, slot, 2_000 + s.lock_ttl_ms + 1, 2.20, 2.22, 500.0, 500.0)
    assert slot.status == LOCKING
    assert "timeout" in [p["motivo"] for p in s.stats["uscite_proposte"]]


def test_spento_la_firma_del_target_mette_la_chiusura():
    events, s, m, slot = _in_stop(False)
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.cancello_uscite.approva({chiave: 2.4})
    s._manage(m, None, None, slot, 2_500, 2.20, 2.22, 500.0, 500.0)
    assert slot.close is not None and m.orders, "la chiusura a target parte con la firma"


def test_force_flat_resta_protezione_in_manuale():
    events, s, m, slot = _in_stop(False)
    s.force_flat = True
    mb = SimpleNamespace(market_id="1.234", publish_time_epoch=2_500, inplay=False,
                         runners=[], market_definition=None, status="OPEN")
    try:
        s.process_market_book(m, mb)
    except Exception:  # noqa: BLE001 - il finto del book e' minimo
        pass
    assert slot.status != LOCKING or s.force_flat is True


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


def test_la_sessione_passa_le_firme_ai_bot_vivi():
    """28/09 (CANTIERE N): la firma scritta dalla RPC scalper_approva_uscita
    in params.uscite_approvate arriva al maker (lo sniper, se c'e', uguale)."""
    s = _strategy([], uscite_automatiche=False)
    # 29/09: la firma vale solo per una proposta VIVA nata prima della firma
    s.cancello_uscite.lascia_uscire(automatiche=False, chiave="k",
                                    now_s=SS._UP._secondi("2026-09-28T11:59:00+00:00"),
                                    proposta={"motivo": "stop"})
    n = SS._UP.applica_firme((s, None), {"uscite_approvate": {"k": "2026-09-28T12:00:00+00:00"},
                                         "uscite_automatiche": False})
    assert n == 1 and "k" in s.cancello_uscite.approvate
    assert SS._UP.applica_firme((s,), None) == 0, "params non letti: niente cambia"


def test_firma_data_prima_di_un_riavvio_cade_e_non_esegue_su_altre_posizioni():
    """29/09 (reperto I del revisore): la chiave della proposta porta l'ordine
    d'ingresso (``Order.id``, o ``id()`` dell'oggetto se manca). Dopo un
    riavvio del processo la posizione rinasce con un ordine nuovo: la firma
    rimasta sulla riga di controllo ha la chiave VECCHIA, non trova la sua
    proposta e cade; e anche se la chiave coincidesse, e' anteriore alla
    proposta nuova e cade lo stesso. Mai un'uscita su un'altra posizione."""
    events, s, m, slot = _in_stop(False)
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    vecchia = next(p["chiave"] for p in s.stats["uscite_proposte"] if p["motivo"] == "stop")
    # ---- riavvio: istanza nuova, posizione ritrovata con un ordine nuovo
    events2, s2, m2, slot2 = _in_stop(False)
    s2._manage(m2, None, None, slot2, 9_000, 2.28, 2.30, 500.0, 500.0)
    nuova = next(p["chiave"] for p in s2.stats["uscite_proposte"] if p["motivo"] == "stop")
    assert nuova != vecchia
    SS._UP.applica_firme((s2,), {"uscite_approvate": {vecchia: 2.6}})
    s2._manage(m2, None, None, slot2, 9_200, 2.28, 2.30, 500.0, 500.0)
    assert slot2.status == LOCKING and m2.orders == []
    # stessa chiave (caso peggiore), firma anteriore alla proposta nuova: cade
    SS._UP.applica_firme((s2,), {"uscite_approvate": {nuova: 2.6}})
    s2._manage(m2, None, None, slot2, 9_300, 2.28, 2.30, 500.0, 500.0)
    assert slot2.status == LOCKING and m2.orders == []
