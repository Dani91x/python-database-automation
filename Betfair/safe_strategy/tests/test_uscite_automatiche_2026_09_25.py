# -*- coding: utf-8 -*-
"""25/09/2026 - SAFE: L'INTERRUTTORE "USCITE AUTOMATICHE" PER STRATEGIA.

Ordine dell'utente (testuale): «Tutti i bot (in live e in paper) DEVONO AVERE
L'ABILITAZIONE per le uscite automatiche e per l'operativita' totalmente
automatica; se disattivo il pulsante (TUTTO DEVE ESSERE IN UI PER SINGOLO BOT),
le uscite le gestisco io manualmente tramite l'apposita scheda».

Parametro di Safe `uscite_automatiche` = mappa PARZIALE strategia -> bool:
  * assente / non booleano = DEFAULT dal 25/09 sera (ordine dell'utente: «di
    default tutte le uscite le voglio spente, per tutti i bot»): MANUALI
    (base/esatto/punta/model/tennis); prima del 25/09 sera il default era
    automatiche;
  * False = ogni uscita della strategia diventa una PROPOSTA (kind='cashout',
    status='proposed', stesso corpo del cancelletto del tennis del 14/09);
  * True = il bot esegue da solo, come prima.
Cambia solo CHI esegue l'uscita: la decisione e' quella del manuale.

I finti sono `FakeDB`/`FakeMarket` di `test_bot_service.py` (stesse chiavi e
tipi di `bot_db`: `requests` con id/kind/status/payload, control con
id/status/mode/params). ASCII-only, commenti in italiano.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import (NOW, FakeDB, _auto_trade,
                                                          _closings, _cycle,
                                                          _exit_feed_row,
                                                          _reset_module_state,
                                                          _tennis_feed_row)


@pytest.fixture(autouse=True)
def _stato_pulito():
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()
    yield
    _reset_module_state()
    S._EVENTI_CHIUSI.clear()


def _proposte(db):
    return [r for r in db.requests if r.get("status") == "proposed"]


def _base_all_81(db, tid, at=NOW):
    """Base lay sull'ospite, 1-0 dal 56': al 81' senza altri gol scatta
    l'uscita A TEMPO del manuale (kind 'time')."""
    _cycle(db, _exit_feed_row(minute=60, sh=1, sa=0), at=at)
    return _cycle(db, _exit_feed_row(minute=81, sh=1, sa=0, updated_at=at), at=at)


def _tennis_game_perso(db):
    _cycle(db, _tennis_feed_row((1, 0), (4, 2)))
    _cycle(db, _tennis_feed_row((1, 0), (4, 3)))
    return _cycle(db, _tennis_feed_row((1, 0), (4, 4)))


def _trade_tennis(db):
    return _auto_trade(db, "tennis", event_id="2.1", market_id="mt", selection_id=11,
                       side="back", price=1.3, sport="tennis",
                       score_at_entry="set 1-0 · game 4-2", minute_at_entry=None,
                       signal_key="2.1:tennis:set 1-0")


# ---------------------------------------------------------------------------
# risoluzione dei parametri: il default e' il comportamento di oggi
# ---------------------------------------------------------------------------
def test_default_ora_e_manuale_per_tutti():
    """25/09 sera: il default e' cambiato da automatiche a manuali (ordine
    dell'utente: «di default tutte le uscite le voglio spente»)."""
    p = S.resolve_params(None)
    assert p["uscite_automatiche"] == {"base": False, "esatto": False, "punta": False,
                                       "tennis": False, "model": False}
    assert p["tennis_exit_approval"] is True
    # il cancelletto storico del tennis spento = uscite del tennis automatiche
    p = S.resolve_params({"tennis_exit_approval": False})
    assert p["uscite_automatiche"]["tennis"] is True
    assert p["uscite_automatiche"]["base"] is False


@pytest.mark.parametrize("grezzo", ["true", 1, None, "si", [], {}])
def test_solo_un_booleano_vero_cambia_qualcosa(grezzo):
    """Una stringa o un numero sul DB non riaccendono le uscite di nessuno."""
    p = S.resolve_params({"uscite_automatiche": {"base": grezzo}})
    assert p["uscite_automatiche"]["base"] is False
    assert S.uscite_automatiche_di(p, "base") is False


def test_la_mappa_vince_sul_cancelletto_storico_e_lo_riallinea():
    p = S.resolve_params({"tennis_exit_approval": True,
                          "uscite_automatiche": {"tennis": True}})
    assert p["uscite_automatiche"]["tennis"] is True
    assert p["tennis_exit_approval"] is False, "una sola verita' per il tennis"
    p = S.resolve_params({"tennis_exit_approval": False,
                          "uscite_automatiche": {"tennis": False}})
    assert p["tennis_exit_approval"] is True
    eff = S.params_effective(p)
    assert eff["uscite_automatiche"]["tennis"] is False
    assert eff["tennis_exit_approval"] is True


def test_manual_e_strategie_ignote_non_hanno_interruttore():
    p = S.resolve_params({"uscite_automatiche": {"manual": False, "boh": False}})
    assert "manual" not in p["uscite_automatiche"]
    assert S.uscite_automatiche_di(p, "manual") is True
    assert S.uscite_automatiche_di(p, "boh") is True


# ---------------------------------------------------------------------------
# ACCESO = come prima (parita')
# ---------------------------------------------------------------------------
def test_acceso_la_base_esce_da_sola_come_prima():
    db = FakeDB(status="running", params={"uscite_automatiche": {"base": True}})
    tid = _auto_trade(db, "base", minute_at_entry=60)
    r = _base_all_81(db, tid)
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1
    assert _proposte(db) == []


# ---------------------------------------------------------------------------
# SPENTO = la stessa uscita diventa una proposta; niente a mercato
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode", ["paper", "live"])
def test_spento_la_base_PROPONE_e_non_manda_niente(mode):
    """Paper e live identici: l'interruttore non guarda la modalita'."""
    db = FakeDB(status="running", mode=mode,
                params={"uscite_automatiche": {"base": False}})
    tid = _auto_trade(db, "base", minute_at_entry=60, mode=mode)
    r = _base_all_81(db, tid)
    assert r["exits"] == 0, "a mercato non deve andare niente"
    assert _closings(db, tid) == []
    prop = _proposte(db)
    assert len(prop) == 1
    q = prop[0]
    assert q["kind"] == "cashout" and q["status"] == "proposed"
    p = q["payload"]
    # le chiavi che la scheda legge (stesso corpo del cancelletto del tennis)
    for k in ("trade_id", "event_id", "market_id", "selection_id", "side",
              "entry_side", "price_at_decision", "size", "exit_kind", "exit_reason",
              "urgente", "locked_at_decision", "hold_profit", "loss_if_lose",
              "mode", "decided_at", "proposed_at"):
        assert k in p, k
    assert p["trade_id"] == tid and p["exit_kind"] == "time"
    assert p["strategy"] == "base" and p["mode"] == mode
    # chiudere un LAY vuol dire BACKare la stessa selezione
    assert p["side"] == "back" and p["entry_side"] == "lay"
    assert isinstance(p["price_at_decision"], float)
    # il marcatore sulla riga, come per il tennis
    tr = db.get_trade(tid)
    assert tr["meta"][S.PROPOSTA_KEY]["request_id"] == q["id"]


def test_spento_su_una_strategia_non_tocca_le_altre():
    # 25/09 sera: il default e' manuale per tutti, quindi "base" va accesa
    # esplicita per isolare l'effetto di "esatto" (spenta anche lei di
    # default, qui esplicita per chiarezza) sulle altre.
    db = FakeDB(status="running",
               params={"uscite_automatiche": {"esatto": False, "base": True}})
    tid = _auto_trade(db, "base", minute_at_entry=60)
    r = _base_all_81(db, tid)
    assert r["exits"] == 1 and _proposte(db) == []


def test_spento_il_tennis_dalla_mappa_propone_anche_col_cancelletto_storico_spento():
    db = FakeDB(status="running", params={"tennis_exit_approval": False,
                                          "uscite_automatiche": {"tennis": False}})
    tid = _trade_tennis(db)
    r = _tennis_game_perso(db)
    assert r["exits"] == 0 and _closings(db, tid) == []
    prop = _proposte(db)
    assert len(prop) == 1 and prop[0]["payload"]["exit_kind"] == "mandatory"
    assert prop[0]["payload"]["urgente"] is True


def test_acceso_il_tennis_dalla_mappa_esce_anche_col_cancelletto_storico_acceso():
    db = FakeDB(status="running", params={"tennis_exit_approval": True,
                                          "uscite_automatiche": {"tennis": True}})
    tid = _trade_tennis(db)
    r = _tennis_game_perso(db)
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1
    assert _proposte(db) == []


# ---------------------------------------------------------------------------
# LETTO A CALDO: il cambio vale dal giro dopo, senza riavvio
# ---------------------------------------------------------------------------
def test_riaccendere_a_caldo_esegue_e_fa_decadere_la_proposta_viva():
    db = FakeDB(status="running", params={"uscite_automatiche": {"base": False}})
    tid = _auto_trade(db, "base", minute_at_entry=60)
    _base_all_81(db, tid)
    assert len(_proposte(db)) == 1 and _closings(db, tid) == []
    # l'utente preme l'interruttore: la riga di control cambia a meta' partita
    db.control["params"] = {**db.control["params"], "uscite_automatiche": {"base": True}}
    t = NOW + timedelta(seconds=5)
    r = _cycle(db, _exit_feed_row(minute=82, sh=1, sa=0, updated_at=t), at=t)
    assert r["exits"] == 1 and len(_closings(db, tid)) == 1
    assert _proposte(db) == [], "la proposta viva non resta in scheda"
    decadute = [q for q in db.requests if q.get("status") == "rejected"]
    assert len(decadute) == 1
    assert decadute[0]["result"]["decaduta"] is True
    assert "automatiche" in decadute[0]["result"]["motivo"]
    assert S.PROPOSTA_KEY not in (db.get_trade(tid).get("meta") or {})


def test_spegnere_a_caldo_ferma_l_uscita_successiva():
    db = FakeDB(status="running", params={"uscite_automatiche": {"base": True}})
    tid = _auto_trade(db, "base", minute_at_entry=60)
    _cycle(db, _exit_feed_row(minute=60, sh=1, sa=0))
    db.control["params"] = {**db.control["params"], "uscite_automatiche": {"base": False}}
    r = _cycle(db, _exit_feed_row(minute=81, sh=1, sa=0))
    assert r["exits"] == 0 and _closings(db, tid) == []
    assert len(_proposte(db)) == 1


def test_approvare_la_proposta_della_base_la_manda_a_mercato():
    """L'approvazione (`safe_request_approve`: proposed -> pending) porta la
    riga sul percorso di sempre del cash out manuale."""
    db = FakeDB(status="running", params={"uscite_automatiche": {"base": False}})
    tid = _auto_trade(db, "base", minute_at_entry=60)
    _base_all_81(db, tid)
    _proposte(db)[0]["status"] = "pending"
    _cycle(db, _exit_feed_row(minute=81, sh=1, sa=0))
    assert len(_closings(db, tid)) == 1
    assert _proposte(db) == []
