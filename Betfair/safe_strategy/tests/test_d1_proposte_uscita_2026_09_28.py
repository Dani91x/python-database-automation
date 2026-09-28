# -*- coding: utf-8 -*-
"""D1 (28/09) - SAFE: UNA PROPOSTA D'USCITA DECADE QUANDO NON E' PIU' ESEGUIBILE.

Reperto del coordinatore (DB, 28/09): sei proposte ``cashout`` ancora
'proposed' del 26/09 (id 311, 315, 318-321, tutte paper; 318 «uscita in
perdita» decisa al 65', 315 tennis) su partite finite da due giorni, ancora
approvabili dalla scheda. Safe faceva decadere da solo SOLO le proposte
``kind='place'`` (``bot_db.scadi_proposte_opportunita``); quelle d'uscita
decadevano solo dentro ``_process_exit_one``, cioe' solo per le posizioni che
il ciclo delle uscite guardava ancora.

Atteso: decade quando la posizione e' chiusa/regolata, quando il mercato e'
chiuso, quando il dato e' superato (il bot non la riconferma piu'); e
un'approvazione si esegue solo se la condizione d'uscita vale ANCORA, al
mercato di ADESSO. Calcio e tennis, paper e live: stesso codice. Quando e
perche' la proposta NASCE non cambia.

Finti: ``FakeDB`` / ``FakeMarket`` di ``test_bot_service.py`` (stesse chiavi di
``bot_db``: ``requests`` con id/kind/status/payload/result).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy import execution as X
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, _auto_trade,
                                                          _closings, _cycle,
                                                          _exit_feed_row,
                                                          _reset_module_state,
                                                          _tennis_feed_row)


@pytest.fixture(autouse=True)
def _stato_pulito(monkeypatch):
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()
    monkeypatch.setattr(X, "_freno_aperture", lambda: None)
    monkeypatch.setattr(X, "_live_brake", lambda: None)

    def _vietato(*_a, **_k):
        raise AssertionError("accesso al database vero da un test")
    import db_client
    monkeypatch.setattr(db_client, "get_supabase_client", _vietato)
    yield
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()


def _proposte(db, stato="proposed"):
    return [r for r in db.requests if r.get("kind") == "cashout" and r.get("status") == stato]


def _proposta_base(db, mode="paper"):
    """Base lay sull'ospite, 1-0: al 81' la regola «a tempo» diventa una
    PROPOSTA (uscite automatiche spente, default dal 25/09)."""
    tid = _auto_trade(db, "base", minute_at_entry=60, mode=mode)
    _cycle(db, _exit_feed_row(minute=60, sh=1, sa=0))
    _cycle(db, _exit_feed_row(minute=81, sh=1, sa=0))
    viva = _proposte(db)
    assert len(viva) == 1 and viva[0]["payload"]["exit_kind"] == "time", "precondizione"
    return tid, viva[0]


def _db(mode="paper"):
    return FakeDB(status="running", mode=mode, params={"uscite_automatiche": {"base": False}})


# ===========================================================================
# 1. LO SPAZZINO
# ===========================================================================
@pytest.mark.parametrize("mode", ["paper", "live"])
@pytest.mark.parametrize("stato", ["won", "lost", "error", "hedged"])
def test_posizione_regolata_o_chiusa_la_proposta_DECADE(mode, stato):
    """Il caso del 26/09: la posizione non e' piu' 'open' ma la proposta
    restava approvabile. Identico in paper e live."""
    db = _db(mode)
    tid, prop = _proposta_base(db, mode)
    db.get_trade(tid)["status"] = stato
    t = NOW + timedelta(seconds=40)
    _cycle(db, _exit_feed_row(minute=83, sh=1, sa=0, updated_at=t), at=t)
    assert prop["status"] == "rejected", "proposta ancora approvabile su una posizione finita"
    assert prop["result"]["decaduta"] is True
    assert "non piu' aperta" in prop["result"]["motivo"]


def test_mercato_CHIUSO_la_proposta_decade():
    db = _db()
    tid, prop = _proposta_base(db)
    t = NOW + timedelta(seconds=40)
    _cycle(db, _exit_feed_row(minute=90, sh=1, sa=0, mo_status="CLOSED", updated_at=t), at=t)
    assert prop["status"] == "rejected"
    assert prop["result"]["decaduta"] is True


def test_mercato_SOSPESO_non_e_chiuso_la_proposta_resta_finche_ha_senso():
    """Una sospensione breve (gol, VAR) non fa decadere: il mercato riapre."""
    db = _db()
    tid, prop = _proposta_base(db)
    t = NOW + timedelta(seconds=40)
    _cycle(db, _exit_feed_row(minute=82, sh=1, sa=0, mo_status="SUSPENDED", updated_at=t), at=t)
    assert prop["status"] == "proposed"


def test_uscita_NON_RICONFERMATA_dal_bot_decade_e_poi_rinasce_coi_dati_nuovi():
    """Dato superato: il bot non riesce piu' a riconfermare la condizione (qui
    il mercato resta sospeso oltre il limite). La proposta decade, il
    marcatore sparisce, e alla riapertura nasce una proposta NUOVA coi numeri
    di allora (non viene trattata come «ignorata dall'utente»)."""
    db = _db()
    tid, prop = _proposta_base(db)
    t = NOW
    for _ in range(8):                     # 8 x 20 s = 160 s di sospensione
        t = t + timedelta(seconds=20)
        _cycle(db, _exit_feed_row(minute=82, sh=1, sa=0, mo_status="SUSPENDED",
                                  updated_at=t), at=t)
    assert prop["status"] == "rejected"
    assert "riconfermata" in prop["result"]["motivo"]
    assert S.PROPOSTA_KEY not in (db.get_trade(tid).get("meta") or {})
    t = t + timedelta(seconds=5)
    _cycle(db, _exit_feed_row(minute=85, sh=1, sa=0, updated_at=t), at=t)
    nuove = _proposte(db)
    assert len(nuove) == 1 and nuove[0]["id"] != prop["id"]


def test_una_proposta_che_REGGE_non_decade_mai():
    """Cintura: la condizione regge per 5 minuti, il bot la riconferma e la
    proposta resta la stessa, viva."""
    db = _db()
    tid, prop = _proposta_base(db)
    t = NOW
    for _ in range(15):
        t = t + timedelta(seconds=20)
        _cycle(db, _exit_feed_row(minute=82, sh=1, sa=0, updated_at=t), at=t)
    assert prop["status"] == "proposed"
    assert [r["id"] for r in _proposte(db)] == [prop["id"]]


def test_tennis_posizione_regolata_la_proposta_decade():
    db = FakeDB(status="running", params={"tennis_exit_approval": True,
                                          "uscite_automatiche": {"tennis": False}})
    tid = _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                      side="back", price=1.3, sport="tennis",
                      score_at_entry="set 1-0 · game 4-2", minute_at_entry=None,
                      signal_key="2.1:tennis:set 1-0")
    _cycle(db, _tennis_feed_row((1, 0), (4, 2)))
    _cycle(db, _tennis_feed_row((1, 0), (4, 3)))
    _cycle(db, _tennis_feed_row((1, 0), (4, 4)))
    prop = _proposte(db)
    assert len(prop) == 1, "precondizione"
    db.get_trade(tid)["status"] = "lost"
    t = NOW + timedelta(seconds=40)
    _cycle(db, _tennis_feed_row((1, 0), (4, 4)), at=t)
    assert prop[0]["status"] == "rejected" and prop[0]["result"]["decaduta"] is True


def test_la_proposta_di_COPERTURA_di_una_gamba_manuale_non_scade_a_tempo():
    """Le coperture B25 non si riconfermano a ritmo: valgono finche' la gamba
    e' aperta. Lo spazzino le chiude solo a posizione finita o mercato chiuso."""
    db = _db()
    tid = _auto_trade(db, "manual", origin="manual", signal_key="1.1:manual:x")
    db.requests.append({"id": 50, "kind": "cashout", "status": "proposed", "result": None,
                        "payload": {"trade_id": tid, "exit_kind": "forced",
                                    "motivo": "copertura_combo_incompleta"}})
    t = NOW + timedelta(minutes=30)
    _cycle(db, _exit_feed_row(minute=70, sh=1, sa=0, updated_at=t), at=t)
    assert db.requests[-1]["status"] == "proposed"
    db.get_trade(tid)["status"] = "won"
    S._SPAZZINO_PROPOSTE["ts"] = 0.0
    _cycle(db, _exit_feed_row(minute=90, sh=1, sa=0, updated_at=t), at=t)
    assert db.requests[-1]["status"] == "rejected"


def test_una_proposta_gia_FIRMATA_non_la_tocca_nessuno():
    """La decadenza per id vale solo su 'proposed': un'approvazione arrivata
    nello stesso istante non viene sovrascritta."""
    db = _db()
    tid, prop = _proposta_base(db)
    prop["status"] = "pending"
    assert db.chiudi_proposta_per_id(prop["id"], "x") is False
    assert prop["status"] == "pending"


# ===========================================================================
# 2. L'APPROVAZIONE DI UNA PROPOSTA VECCHIA
# ===========================================================================
@pytest.mark.parametrize("mode", ["paper", "live"])
def test_approvata_con_la_condizione_CAMBIATA_nessun_ordine(mode):
    """Proposta «a tempo» (1-0 al 81'); l'utente firma dopo il 2-0: adesso la
    regola sarebbe un'altra. Nessun ordine, richiesta rifiutata e marcata
    decaduta; il bot ripropone coi dati di adesso."""
    db = _db(mode)
    tid, prop = _proposta_base(db, mode)
    prop["status"] = "pending"
    prop["payload"]["approved_at"] = NOW.isoformat()
    t = NOW + timedelta(seconds=10)
    _cycle(db, _exit_feed_row(minute=84, sh=2, sa=0, updated_at=t), at=t)
    assert _closings(db, tid) == [], "chiusura partita su una condizione superata"
    assert prop["status"] == "rejected"
    assert prop["result"]["decaduta"] is True
    assert "cambiata" in prop["result"]["motivo"]


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_approvata_con_la_condizione_che_REGGE_parte_al_prezzo_di_ADESSO(mode):
    db = _db(mode)
    tid, prop = _proposta_base(db, mode)
    prop["status"] = "pending"
    prop["payload"]["approved_at"] = NOW.isoformat()
    t = NOW + timedelta(seconds=10)
    feed = _exit_feed_row(minute=83, sh=1, sa=0, updated_at=t)
    feed["payload"]["odds"]["away"].update({"back": 10.0, "lay": 10.5})
    _cycle(db, feed, at=t)
    chiusure = _closings(db, tid)
    assert len(chiusure) == 1
    assert chiusure[0]["price"] == 10.0, "si chiude al mercato di adesso, non a quello della proposta"
    assert prop["payload"]["price_at_decision"] != 10.0


def test_approvata_senza_la_partita_nel_feed_non_si_esegue():
    db = _db()
    tid, prop = _proposta_base(db)
    trade = db.get_trade(tid)
    res = S._request_cashout(db=db, market=None, rows_by_event={},
                             payload={**prop["payload"], "approved_at": NOW.isoformat()},
                             params=S.resolve_params(db.control["params"]), now=NOW)
    assert res.get("rejected") == "condizione_uscita_non_valida"
    assert trade["status"] == "open" and _closings(db, tid) == []


def test_modello_approvata_con_marcatore_vecchio_rifiutata_fresco_passa():
    trade = {"id": 1, "strategy": "model", "meta": {S.PROPOSTA_KEY: {
        "request_id": 9, "ts": (NOW - timedelta(seconds=600)).isoformat()}}}
    corpo = {"trade_id": 1, "exit_kind": "profit"}
    assert S._proposta_non_piu_valida(trade, corpo, None, {}, NOW) is not None
    trade["meta"][S.PROPOSTA_KEY]["ts"] = (NOW - timedelta(seconds=15)).isoformat()
    assert S._proposta_non_piu_valida(trade, corpo, None, {}, NOW) is None


def test_il_cash_out_della_SCHEDA_non_passa_dalla_verifica():
    """Senza ``exit_kind`` e' una decisione dell'utente: nessun controllo di
    condizione (non e' una proposta del bot)."""
    trade = {"id": 1, "strategy": "base", "meta": {}}
    assert S._proposta_non_piu_valida(trade, {"trade_id": 1, "fraction": 1.0},
                                      None, {}, NOW) is None
