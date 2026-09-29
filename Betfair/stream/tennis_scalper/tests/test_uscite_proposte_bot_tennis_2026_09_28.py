# -*- coding: utf-8 -*-
"""CANTIERE N (28/09/2026) - bot tennis: PROPOSTA -> FIRMA -> ORDINE.

Regola dell'utente di oggi: a uscite MANUALI ogni uscita di trading (presa di
profitto, stop, time-stop, strutturale) diventa una PROPOSTA coi numeri; parte
solo se l'utente la approva, sul mercato di ADESSO e solo se la condizione vale
ancora. A uscite AUTOMATICHE parte da sola. Le protezioni (freno, "Chiudi",
fine mercato) non passano dal cancello.

La firma arriva come la scrive la RPC ``tennis_bot_approva_uscita``
(``{chiave: istante ISO}`` nella colonna ``uscite_approvate`` della riga per
partita) e il runner la passa al bot (``cancello_uscite.approva``).

Finti: quelli delle suite dei bot (stesse chiavi del vero). ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from Betfair.stream import uscite_proposte as UP
from Betfair.stream.tennis_scalper.tennis_swing_bot import _tki
from Betfair.stream.tennis_scalper.tests import test_tennis_swing as SW


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------- il modulo puro
def test_cancello_automatico_lascia_sempre():
    c = UP.CancelloUscite()
    assert c.lascia_uscire(automatiche=True, chiave="k", now_s=10.0, proposta={}) is True
    assert c.vive() == []


def test_cancello_manuale_propone_una_volta_e_la_firma_vale_una_volta():
    eventi = []
    c = UP.CancelloUscite(emetti=lambda ev, p: eventi.append(ev))
    assert c.lascia_uscire(automatiche=False, chiave="k", now_s=10.0, proposta={"motivo": "stop"}) is False
    assert c.lascia_uscire(automatiche=False, chiave="k", now_s=11.0, proposta={"motivo": "stop"}) is False
    assert eventi == ["uscita_proposta"]
    assert c.vive()[0]["decided_at"] == 10.0 and c.vive()[0]["proposed_at"] == 11.0
    c.approva({"k": "1970-01-01T00:00:12+00:00"})
    assert c.lascia_uscire(automatiche=False, chiave="k", now_s=13.0, proposta={}) is True
    assert eventi[-1] == "uscita_eseguita_su_approvazione"
    # la stessa riga di controllo riletta: la firma consumata non riparte
    c.approva({"k": "1970-01-01T00:00:12+00:00"})
    assert c.lascia_uscire(automatiche=False, chiave="k", now_s=14.0, proposta={}) is False


def test_firma_scaduta_non_vale():
    c = UP.CancelloUscite()
    c.approva({"k": 0.0})
    assert c.lascia_uscire(automatiche=False, chiave="k",
                           now_s=UP.TTL_APPROVAZIONE_S + 1.0, proposta={}) is False


def test_firma_di_un_altra_uscita_non_vale():
    c = UP.CancelloUscite()
    c.approva({"pos|stop": 10.0})
    assert c.lascia_uscire(automatiche=False, chiave="pos|time", now_s=11.0, proposta={}) is False


def test_condizione_caduta_la_proposta_sparisce():
    c = UP.CancelloUscite()
    c.lascia_uscire(automatiche=False, chiave="pos|stop", now_s=1.0, proposta={})
    c.conferma_vive("pos|", ())
    assert c.vive() == []


def test_colonna_assente_nessuna_firma():
    c = UP.CancelloUscite()
    for grezzo in (None, [], "x", 3):
        c.approva(grezzo)
    assert c.approvate == {}


# ---------------------------------------------------------------- SWING
def _swing_stop(auto: bool):
    s = SW._make(uscite_automatiche=auto, stop_ticks=2, maker=False, tmax=10_000)
    m = SW._Market(SW._Blotter([SW._Order(111, "BACK", 2.0, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0,
                    "wait": 0, "t0": 1_000}
    return s, m


def _book_stop(pt: int):
    return SW._MB([SW._Runner(111, (1.60, 100), (1.62, 100), ltp=1.61)], pt=pt)


def _book_rientrato(pt: int):
    return SW._MB([SW._Runner(111, (1.50, 100), (1.51, 100), ltp=1.50)], pt=pt)


def test_swing_proposta_porta_i_numeri():
    s, m = _swing_stop(False)
    s.process_market_book(m, _book_stop(2_000))
    p = s.stats["uscite_proposte"][0]
    for k in ("chiave", "bot", "motivo", "market_id", "selection_id", "lato_ingresso",
              "prezzo", "lato_chiusura", "size_chiusura", "se_chiudi", "se_vince",
              "se_perde", "decided_at", "proposed_at", "urgente"):
        assert k in p, k
    assert p["bot"] == "tennis_swing" and p["market_id"] == "1.1" and p["selection_id"] == 111
    assert p["lato_chiusura"] == "LAY" and p["prezzo"] == 1.62
    assert p["se_chiudi"] < 0, "lo stop chiude in perdita e la scheda lo dice"
    assert m.placed == []


def test_swing_firma_e_condizione_ancora_vera_parte_al_book_dopo():
    s, m = _swing_stop(False)
    s.process_market_book(m, _book_stop(2_000))
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_500)})           # come il runner
    s.process_market_book(m, _book_stop(3_000))
    assert s._tr["1.1"].get("closing") is True and m.placed
    assert s.stats["uscite_proposte"] == []


def test_swing_firma_ma_condizione_caduta_non_parte():
    s, m = _swing_stop(False)
    s.process_market_book(m, _book_stop(2_000))
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.process_market_book(m, _book_rientrato(2_200))          # il prezzo e' rientrato
    assert s.stats["uscite_proposte"] == [], "la proposta non vale piu'"
    s.cancello_uscite.approva({chiave: _iso(2_300)})
    s.process_market_book(m, _book_rientrato(2_400))
    assert not s._tr["1.1"].get("closing") and m.placed == []


def test_swing_interruttore_a_caldo_la_proposta_parte_da_sola():
    s, m = _swing_stop(False)
    s.process_market_book(m, _book_stop(2_000))
    assert m.placed == []
    s.uscite_automatiche = True                                # l'utente, a caldo
    s.process_market_book(m, _book_stop(3_000))
    assert s._tr["1.1"].get("closing") is True and m.placed
    assert s.stats["uscite_proposte"] == []


def test_swing_chiudi_ora_resta_protezione_anche_in_manuale():
    """Il "Chiudi" dell'utente (D3) non passa dal cancello."""
    s, m = _swing_stop(False)
    s.uscita_manuale_chiesta = True
    s.process_market_book(m, _book_rientrato(2_000))
    assert s._tr["1.1"].get("closing") is True and m.placed


def test_swing_paper_uguale_live():
    """Il cancello non guarda la modalita': in dry-run (paper senza ordini
    veri) la proposta nasce identica e nessun esito virtuale viene contato."""
    s, m = _swing_stop(False)
    s.dry_run = True
    s._tr["1.1"]["px"] = 1.50
    s.process_market_book(m, _book_stop(2_000))
    assert [p["motivo"] for p in s.stats["uscite_proposte"]] == ["stop"]
    assert s.stats["losses"] == 0 and "1.1" in s._tr


# ---------------------------------------------------------------- PRO
from Betfair.stream.tennis_scalper.tennis_pro_bot import CLOSING as PRO_CLOSING  # noqa: E402
from Betfair.stream.tennis_scalper.tennis_pro_bot import OPEN as PRO_OPEN  # noqa: E402
from Betfair.stream.tennis_scalper.tests import test_tennis_pro_staged as PS  # noqa: E402


def _pro(auto: bool, **trade):
    s = PS._make(staged=True, staged_frac=0.4)
    s.uscite_automatiche = auto
    m = PS._Market(PS._Blotter([PS._Order(111, "BACK", 2.0, 1.80)]))
    s._trade["1.1"] = {**PS._open_trade(), "t_open": 1_000, **trade}
    return s, m


def _pro_book(back: float, lay: float, pt: int):
    mb = PS._MB([PS._Runner(111, (back, 100), (lay, 100))])
    mb.publish_time_epoch = pt
    return mb


def test_pro_manuale_target_e_scaglione_diventano_proposte_coi_numeri():
    s, m = _pro(False)
    s.process_market_book(m, _pro_book(1.74, 1.75, 2_000))
    motivi = sorted(p["motivo"] for p in s.stats["uscite_proposte"])
    assert motivi == ["scaglione", "target"] and m.placed == []
    sc = next(p for p in s.stats["uscite_proposte"] if p["motivo"] == "scaglione")
    assert sc["frazione"] == 0.4 and sc["se_chiudi"] > 0


def test_pro_firma_sullo_stop_e_condizione_vera_parte():
    s, m = _pro(False)
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_000))
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_100)})
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_200))
    assert s._trade["1.1"]["state"] == PRO_CLOSING and s.stats["stops"] == 1 and m.placed


def test_pro_firma_sullo_stop_ma_prezzo_rientrato_non_parte():
    s, m = _pro(False)
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_000))
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.process_market_book(m, _pro_book(1.79, 1.80, 2_050))      # rientrato
    assert s.stats["uscite_proposte"] == []
    s.cancello_uscite.approva({chiave: _iso(2_100)})
    s.process_market_book(m, _pro_book(1.79, 1.80, 2_200))
    assert s._trade["1.1"]["state"] == PRO_OPEN and m.placed == []


def test_pro_uscita_strutturale_in_manuale_e_proposta():
    from Betfair.stream.tennis_scalper.tennis_score import TennisScore
    s, m = _pro(False, entry_games=(1, 0, 0, 0))
    # stesso costruttore delle suite del PRO (test_tennis_pro.py): game 0-0,
    # set 0-0 -> diverso da quello d'ingresso (1-0)
    s.score = TennisScore(event_id="1", server="home", point_home="15", point_away="0")
    s.process_market_book(m, _pro_book(1.79, 1.80, 2_000))      # game cambiato
    assert [p["motivo"] for p in s.stats["uscite_proposte"]] == ["strutturale"]
    assert s._trade["1.1"]["state"] == PRO_OPEN and m.placed == []


# ---------------------------------------------------------------- FLB
from Betfair.stream.tennis_scalper.tennis_flb_bot import TennisFLBStrategy  # noqa: E402
from Betfair.stream.tennis_scalper.tests import test_tennis_flb_hybrid as FH  # noqa: E402


def _flb(auto: bool):
    s = TennisFLBStrategy(
        market_filter=FH.filters.streaming_market_filter(market_ids=["1.1"]),
        flb_params={"exit_mode": "hybrid", "green_ticks": 2, "green_frac": 0.5,
                    "lay_max": 1.10, "min_lay_size": 5.0, "dry_run": False},
    )
    s.uscite_automatiche = auto
    m = FH._Market()
    s.process_market_book(m, FH._MB([FH._Runner(111, (1.04, 200), (1.05, 200), ltp=1.05)]))
    m.blotter.orders.append(FH._Order(111, "LAY", 2.0, 1.05))
    return s, m


def _flb_su():
    return FH._MB([FH._Runner(111, (1.07, 200), (1.08, 200), ltp=1.07)])


def test_flb_manuale_il_green_e_proposta_coi_numeri():
    s, m = _flb(False)
    s.process_market_book(m, _flb_su())
    p = s.stats["uscite_proposte"]
    assert [x["motivo"] for x in p] == ["green"] and p[0]["frazione"] == 0.5
    assert p[0]["lato_chiusura"] == "BACK" and len(m.placed) == 1


def test_flb_firma_e_condizione_vera_greena():
    s, m = _flb(False)
    s.process_market_book(m, _flb_su())
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    import time as _t
    s.cancello_uscite.approva({chiave: _t.time()})
    s.process_market_book(m, _flb_su())
    assert s._pos_state[("1.1", 111)]["greened"] is True and len(m.placed) == 2
    assert s.stats["uscite_proposte"] == []


# ---------------------------------------------------------------- SCALPER TENNIS
# 28/09: "nessuna eccezione per strategia" - prima lo scalper tennis era SEMPRE
# automatico; ora ha l'interruttore e nasce manuale.
from Betfair.stream.tennis_scalper.tennis_scalper_bot import (  # noqa: E402
    FLATTENING as TS_FLATTENING, LOCKING as TS_LOCKING, QUOTING2 as TS_QUOTING2,
    TennisScalperStrategy,
)
from Betfair.stream.tests.test_scalper_presize_2026_07_11 import _FakeMarket, _FakeOrder  # noqa: E402


def _ts(auto: bool):
    ev = []
    s = TennisScalperStrategy(market_filter={}, scalper_params={
        "dry_run": False, "stake": 2.0, "stop_ticks": 2},
        event_sink=lambda k, p: ev.append((k, p)))
    s.uscite_automatiche = auto
    m = _FakeMarket()
    slot = s._slot("1.9", 7)
    slot.entry = _FakeOrder("BACK", price=2.22, size=2.0, size_matched=2.0, avg=2.22, live=False)
    slot.entry_side = "BACK"
    return ev, s, m, slot


def test_scalper_tennis_nasce_manuale():
    assert TennisScalperStrategy.uscite_automatiche is False


def test_scalper_tennis_automatico_non_propone_e_lo_stop_parte():
    ev, s, m, slot = _ts(True)
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    # il bot prova a mettere la SUA chiusura (il finto del calcio la rifiuta
    # col minimo tennis e il bot va, com'e' giusto, a chiusura garantita):
    # nessuna proposta, nessuna attesa dell'utente
    assert s.stats.get("uscite_proposte", []) == []
    assert slot.status in (TS_LOCKING, TS_FLATTENING) and not (
        slot.status == TS_LOCKING and slot.close is None)
    # stop su una posizione gia' in LOCKING con la sua chiusura
    slot.status, slot.close, slot.t_lock = TS_LOCKING, _FakeOrder(
        "LAY", price=2.20, size=2.0, live=True), 2_000
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == TS_FLATTENING


def test_scalper_tennis_manuale_target_e_stop_sono_proposte():
    ev, s, m, slot = _ts(False)
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    assert slot.status == TS_LOCKING and slot.close is None and m.orders == []
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == TS_LOCKING
    motivi = sorted(p["motivo"] for p in s.stats["uscite_proposte"])
    assert motivi == ["stop", "target"]
    stop = next(p for p in s.stats["uscite_proposte"] if p["motivo"] == "stop")
    assert stop["bot"] == "tennis_scalper" and stop["urgente"] is True


def test_scalper_tennis_firma_sullo_stop_e_condizione_vera_parte():
    ev, s, m, slot = _ts(False)
    s._open_lock(m, slot, 2_000, slot.entry, 2.22, 2.24)
    s._manage(m, None, None, slot, 2_500, 2.28, 2.30, 500.0, 500.0)
    chiave = next(p["chiave"] for p in s.stats["uscite_proposte"] if p["motivo"] == "stop")
    s.cancello_uscite.approva({chiave: 2.6})
    s._manage(m, None, None, slot, 2_700, 2.28, 2.30, 500.0, 500.0)
    assert slot.status == TS_FLATTENING


def test_scalper_tennis_gamba_opposta_ritirata_in_manuale():
    ev, s, m, slot = _ts(False)
    slot.entry = None
    slot.status = TS_QUOTING2
    eb = _FakeOrder("BACK", price=2.22, size=2.0, size_matched=2.0, avg=2.22, live=False)
    el = _FakeOrder("LAY", price=2.20, size=2.0, live=True)
    slot.entry_back, slot.entry_lay = eb, el
    slot.t_quote = 1_000
    s._manage_maker(m, slot, now=2_000, best_back=2.20, best_lay=2.22,
                    size_back=500.0, size_lay=500.0)
    assert slot.status == TS_LOCKING and slot.close is None
    assert [o for o, _ in m.cancelled] == [el], "la gamba opposta si ritira"
    assert [p["motivo"] for p in s.stats["uscite_proposte"]] == ["target"]


# ---------------------------------------------------------------- 29/09: firma e proposta vivono insieme
def test_firma_senza_proposta_viva_scartata_e_non_rimessa():
    c = UP.CancelloUscite()
    c.approva({"k": 10.0})                          # nessuna proposta: non vale
    assert c.approvate == {}
    c.lascia_uscire(automatiche=False, chiave="k", now_s=20.0, proposta={})
    c.approva({"k": 10.0})                          # riga riletta: firma vecchia
    assert c.approvate == {}, "firma anteriore alla proposta"
    assert c.lascia_uscire(automatiche=False, chiave="k", now_s=21.0, proposta={}) is False


def test_decadenza_porta_via_la_firma_in_tieni_solo_e_chiudi_posizione():
    for pota in ("tieni_solo", "chiudi_posizione"):
        c = UP.CancelloUscite()
        c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=1.0, proposta={})
        c.approva({"p|stop": 2.0})
        (c.tieni_solo(["altra|"]) if pota == "tieni_solo" else c.chiudi_posizione("p|"))
        c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=3.0, proposta={})
        c.approva({"p|stop": 2.0})                  # la stessa firma riletta
        assert c.lascia_uscire(automatiche=False, chiave="p|stop", now_s=4.0,
                               proposta={}) is False, pota


def test_i_file_nuovi_del_cantiere_sono_ascii():
    """29/09 (reperto F): codice e migrazione ASCII-only."""
    import pathlib
    radice = pathlib.Path(__file__).resolve().parents[4]
    for rel in ("Betfair/stream/uscite_proposte.py",
                "migrations/uscite_approva_bot_flusso_2026-09-28.sql"):
        testo = (radice / rel).read_bytes()
        assert all(b < 128 for b in testo), rel


# ---------------------------------------------------------------- 29/09: l'uscita FIRMATA passa dalla strada ESATTA di D2
from Betfair.stream.tennis_scalper.tennis_scalper_bot import compute_green as _cg  # noqa: E402


def _spia_place(s):
    """Registra le chiamate a ``_place`` (quella VERA resta sotto)."""
    chiamate = []
    vero = s._place

    def spia(market, sel, side, price, size, **kw):
        chiamate.append({"side": side, "price": price, "size": size,
                         "copertura": kw.get("copertura", False)})
        return vero(market, sel, side, price, size, **kw)
    s._place = spia
    return chiamate


def _spia_esatte(s):
    """Registra cosa arriva al place-and-trim di D2 (``UsciteEsatte.piazza``)."""
    arrivate = []
    vero = s._esatte.piazza

    def spia(market, sel, side, price, size, piazza):
        arrivate.append(round(float(size), 2))
        return vero(market, sel, side, price, size, piazza)
    s._esatte.piazza = spia
    return arrivate


def test_swing_uscita_firmata_parte_dalla_strada_esatta():
    s, m = _swing_stop(False)
    s.live = True                                    # come in live e paper (dal 28/09)
    s.process_market_book(m, _book_stop(2_000))
    prop = s.stats["uscite_proposte"][0]
    s.cancello_uscite.approva({prop["chiave"]: _iso(2_500)})
    chiamate, esatte = _spia_place(s), _spia_esatte(s)
    s.process_market_book(m, _book_stop(3_000))
    uscite = [c for c in chiamate if c["copertura"]]
    assert uscite, "l'uscita approvata non e' passata da _place(copertura=True)"
    atteso = round(_cg(2.0 * (1.50 - 1.0), -2.0, 1.62)[1], 2)
    assert uscite[0]["size"] == pytest.approx(atteso, abs=0.01), "importo gonfiato"
    from Betfair.stream.tennis_scalper.condotta_ordini import diretta_ok
    if diretta_ok(atteso, uscite[0]["side"]):
        assert esatte == [], "importo piazzabile diretto: niente place-and-trim"
    else:
        assert esatte and esatte[0] == pytest.approx(atteso, abs=0.01), \
            "sotto il minimo deve passare dal place-and-trim di D2 (UsciteEsatte)"


def test_pro_uscita_firmata_parte_dalla_strada_esatta():
    s, m = _pro(False)
    s.live = True
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_000))
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    s.cancello_uscite.approva({chiave: _iso(2_100)})
    chiamate = _spia_place(s)
    s.process_market_book(m, _pro_book(1.84, 1.85, 2_200))
    uscite = [c for c in chiamate if c["copertura"]]
    assert uscite, "l'uscita approvata non e' passata da _place(copertura=True)"
    atteso = round(_cg(2.0 * (1.80 - 1.0), -2.0, 1.85)[1], 2)
    assert uscite[0]["size"] == pytest.approx(atteso, abs=0.01), "importo gonfiato"


def test_flb_uscita_firmata_parte_dalla_strada_esatta():
    s, m = _flb(False)
    s.live = True
    s.process_market_book(m, _flb_su())
    chiave = s.stats["uscite_proposte"][0]["chiave"]
    frazione = s.stats["uscite_proposte"][0]["frazione"]
    import time as _t
    s.cancello_uscite.approva({chiave: _t.time()})
    chiamate = _spia_place(s)
    s.process_market_book(m, _flb_su())
    uscite = [c for c in chiamate if c["copertura"]]
    assert uscite, "il green approvato non e' passato da _place(copertura=True)"
    nw, nl = -2.0 * (1.05 - 1.0), 2.0
    atteso = round(_cg(nw, nl, 1.07)[1] * frazione, 2)
    assert uscite[0]["size"] == pytest.approx(atteso, abs=0.02), "importo gonfiato"


def test_swing_uscita_firmata_sotto_il_minimo_passa_dal_place_and_trim_di_d2():
    """Stop su un BACK da 1,20 EUR (fill parziale): l'hedge LAY e' piccolo e non
    piazzabile diretto -> la firma lo manda al place-and-trim di D2 all'importo
    ESATTO, mai gonfiato al minimo."""
    s = SW._make(uscite_automatiche=False, stop_ticks=2, maker=False, tmax=10_000)
    s.live = True
    m = SW._Market(SW._Blotter([SW._Order(111, "BACK", 0.30, 1.50)]))
    s._tr["1.1"] = {"sel": 111, "side": "BACK", "etk": _tki(1.50),
                    "anchor": _tki(1.40), "order": None, "held": 0, "wait": 0, "t0": 1_000}
    s.process_market_book(m, _book_stop(2_000))
    prop = s.stats["uscite_proposte"][0]
    s.cancello_uscite.approva({prop["chiave"]: _iso(2_500)})
    chiamate, esatte = _spia_place(s), _spia_esatte(s)
    s.process_market_book(m, _book_stop(3_000))
    atteso = round(_cg(0.30 * 0.50, -0.30, 1.62)[1], 2)
    assert [c["size"] for c in chiamate if c["copertura"]][0] == pytest.approx(atteso, abs=0.01)
    assert esatte and esatte[0] == pytest.approx(atteso, abs=0.01)
