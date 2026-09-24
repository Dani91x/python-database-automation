# -*- coding: utf-8 -*-
"""MODELLO E ORDINI A MANO: PAPER E LIVE, E IN LIVE L'ORDINE PARTE DAVVERO (24/09/2026).

Ordine dell'utente: «OGNI strumento che propone ingressi a mercato deve avere
sia la versione PAPER che LIVE, e in caso di LIVE gli ordini devono partire
DAVVERO.»

Cosa certifica questo file, sul codice di produzione (``run_once`` intero,
coda richieste -> ``_request_place`` -> ``_execute`` -> ``execution.place``):

  1. una proposta di opportunita' APPROVATA (``payload.opp_key``) con
     ``strategy_modes.model='live'`` e servizio in LIVE arriva al client LIVE
     di Safe (``market.place_order_live``) con i parametri dell'ordine;
  2. con ``strategy_modes.model='paper'`` la stessa approvazione resta PAPER:
     il client live non viene chiamato;
  3. un ordine A MANO (nessuna ``opp_key``) con ``strategy_modes.manual='live'``
     va al client live;
  4. un ordine a mano con la chiave ``manual`` ASSENTE e il servizio in LIVE
     vale PAPER: una richiesta che dice LIVE viene RIFIUTATA
     (``modalita_non_corrispondente``), una che dice PAPER diventa una riga
     paper. Mai ereditare il ``mode`` del servizio (prima del 24/09 lo
     ereditava);
  5. al nuovo avvio (``APP_BOOT_ID`` diverso) anche ``model`` e ``manual``
     tornano a PAPER;
  6. il freno globale ``LIVE_ORDER_MODE`` non LIVE ferma l'ordine live con il
     motivo ``live_order_mode_non_live``: nessuna chiamata a Betfair.

Il finto e' quello VERO dei test di Safe (``test_bot_service.FakeDB`` /
``FakeMarket``): stesse chiavi della riga di control (``status``, ``mode``,
``params.strategy_modes``) e della coda (``kind``, ``status``, ``payload``), e
``place_order_live`` con la firma di ``omega_market``.

FALSIFICAZIONE (referto): con ``_verifica_modalita_proposta`` riportata a
``control.mode`` nudo per l'ordine a mano, i test 4 diventano ROSSI (la
richiesta LIVE senza chiave passa e chiama Betfair). Con ``strategy_modes_a_paper``
che salta ``model``/``manual``, il test 5 diventa ROSSO.

File ASCII-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeMarket, _feed_row, _place_payload, _reset_module_state, _run,
)
from Betfair.stream import avvio_app as AA
from Betfair.stream.tests.test_avvio_app_2026_09_16 import riga_control


@pytest.fixture(autouse=True)
def _pulizia():
    _reset_module_state()
    S._GUARDIA_AVVIO.azzera()
    yield
    _reset_module_state()
    S._GUARDIA_AVVIO.azzera()


def _db(mode: str, modi: dict) -> FakeDB:
    """Servizio in corsa con la mappa ``strategy_modes`` SCRITTA come la
    scrive la Control Room: niente default del finto (che in live mette tutto
    a 'live')."""
    db = FakeDB(status="running", mode=mode,
                params={"variants": ["base"], "strategy_modes": dict(modi)})
    db.scan_rows = [_feed_row()]
    return db


def _proposta(mode: str, **kw) -> dict:
    """Payload di una proposta APPROVATA: le chiavi di
    ``proposte_opportunita.corpo_proposta`` che ``_request_place`` legge."""
    return _place_payload(mode=mode, opp_key="1.1|model|MATCH_ODDS|7|back",
                          strategy="model", kind="model", **kw)


def _accoda(db: FakeDB, payload: dict) -> None:
    db.requests.append({"id": len(db.requests) + 1, "kind": "place",
                        "status": "pending", "payload": payload})


def _skip(db: FakeDB, reason: str) -> list:
    return [p for k, p in db.activity if k == "skip" and p.get("reason") == reason]


# ---------------------------------------------------------------------------
# 1-2. proposta approvata: model LIVE -> client live; model PAPER -> paper
# ---------------------------------------------------------------------------
def test_proposta_approvata_model_live_chiama_il_client_live_coi_parametri():
    db = _db("live", {"base": "paper", "model": "live"})
    mkt = FakeMarket()
    _accoda(db, _proposta("live"))
    _run(db, market=mkt)
    assert db.requests[0]["status"] == "done", db.requests[0]
    assert len(mkt.placed) == 1, "l'ordine LIVE deve partire davvero"
    ordine = mkt.placed[0]
    assert ordine["market_id"] == "m1" and ordine["selection_id"] == 7
    assert ordine["side"] == "back" and ordine["price"] == 3.0 and ordine["size"] == 5.0
    assert ordine["event_id"] == "1.1"
    riga = db.trades[0]
    assert riga["mode"] == "live" and riga["strategy"] == "model"
    assert riga["bet_id"] == "b-1"


def test_proposta_approvata_model_paper_resta_paper_nessuna_chiamata_live():
    db = _db("live", {"base": "live", "model": "paper"})
    mkt = FakeMarket()
    _accoda(db, _proposta("paper"))
    _run(db, market=mkt)
    assert mkt.placed == []
    assert db.trades and db.trades[0]["mode"] == "paper"


def test_proposta_che_dice_live_col_model_assente_e_rifiutata():
    db = _db("live", {"base": "live"})
    mkt = FakeMarket()
    _accoda(db, _proposta("live"))
    _run(db, market=mkt)
    assert mkt.placed == [] and db.trades == []
    assert _skip(db, "modalita_non_corrispondente")


# ---------------------------------------------------------------------------
# 3-4. ordine a mano: manual LIVE -> client live; chiave assente -> paper
# ---------------------------------------------------------------------------
def test_ordine_a_mano_manual_live_chiama_il_client_live():
    db = _db("live", {"base": "paper", "manual": "live"})
    mkt = FakeMarket()
    _accoda(db, _place_payload(mode="live"))
    _run(db, market=mkt)
    assert db.requests[0]["status"] == "done", db.requests[0]
    assert len(mkt.placed) == 1
    assert mkt.placed[0]["market_id"] == "m1" and mkt.placed[0]["size"] == 5.0
    riga = db.trades[0]
    assert riga["mode"] == "live" and riga["strategy"] == "manual"
    assert riga["origin"] == "manual"


def test_ordine_a_mano_manual_assente_e_servizio_live_una_richiesta_live_e_rifiutata():
    """IL CUORE DEL 24/09: prima l'ordine a mano ereditava il ``mode`` del
    servizio. Armare il servizio in LIVE per il solo tennis mandava a soldi
    veri anche il clic a mano. Adesso la chiave assente vale PAPER."""
    db = _db("live", {"tennis": "live"})
    mkt = FakeMarket()
    _accoda(db, _place_payload(mode="live"))
    _run(db, market=mkt)
    assert mkt.placed == [], "nessun soldo vero senza strategy_modes.manual='live'"
    assert db.trades == []
    rif = _skip(db, "modalita_non_corrispondente")
    assert rif and rif[0]["attiva"] == "paper" and rif[0]["strategia"] == "manual"


def test_ordine_a_mano_manual_assente_e_servizio_live_una_richiesta_paper_diventa_paper():
    db = _db("live", {"tennis": "live"})
    mkt = FakeMarket()
    _accoda(db, _place_payload(mode="paper"))
    _run(db, market=mkt)
    assert mkt.placed == []
    assert db.requests[0]["status"] == "done", db.requests[0]
    assert db.trades[0]["mode"] == "paper"


def test_ordine_a_mano_manual_live_ma_servizio_paper_resta_paper():
    """Il ``mode`` del servizio e' un TETTO: la voce 'live' non basta."""
    db = _db("paper", {"manual": "live"})
    mkt = FakeMarket()
    _accoda(db, _place_payload(mode="live"))
    _run(db, market=mkt)
    assert mkt.placed == [] and db.trades == []
    assert _skip(db, "modalita_non_corrispondente")


# ---------------------------------------------------------------------------
# 5. avvio nuovo: model e manual tornano a paper come le altre
# ---------------------------------------------------------------------------
def test_avvio_nuovo_riporta_model_e_manual_a_paper(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    params = {"variants": ["base"], "strategy_modes": {
        "base": "paper", "model": "live", "manual": "live"}}
    db = FakeDB(status="running", mode="live")
    db.control = riga_control("safe_strategy_control", id=1, status="running", mode="live",
                              params=json.loads(json.dumps(params)),
                              stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["mode"] == "paper" and db.control["status"] == "stopped"
    assert db.control["params"]["strategy_modes"] == {
        "base": "paper", "model": "paper", "manual": "paper"}
    kind, payload = db.activity[0]
    assert kind == AA.KIND_ATTIVITA
    assert payload["strategy_modes_live"] == ["manual", "model"]


# ---------------------------------------------------------------------------
# 6. freno globale LIVE_ORDER_MODE: rifiuto dichiarato, nessuna chiamata
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("payload_fn,modi", [
    (lambda: _proposta("live"), {"model": "live"}),
    (lambda: _place_payload(mode="live"), {"manual": "live"}),
])
def test_freno_live_order_mode_non_live_ferma_l_ordine(monkeypatch, payload_fn, modi):
    monkeypatch.setenv("LIVE_ORDER_MODE", "PAPER")
    db = _db("live", modi)
    mkt = FakeMarket()
    _accoda(db, payload_fn())
    _run(db, market=mkt)
    assert mkt.placed == [], "col freno tirato nessun ordine arriva a Betfair"
    res = db.requests[0].get("result") or {}
    assert "live_order_mode_non_live" in json.dumps(res), res


# ---------------------------------------------------------------------------
# 7. la barriera SQL di `safe_request` segue la stessa regola (contratto sul
#    sorgente: il DB non e' raggiungibile dalla suite)
# ---------------------------------------------------------------------------
MIGRAZIONE = (Path(__file__).resolve().parents[3] / "migrations"
              / "safe_request_modalita_manuale_2026-09-24.sql")


def test_migrazione_barriera_per_strategia():
    sql = MIGRAZIONE.read_text(encoding="utf-8")
    corpo = sql[sql.index("CREATE OR REPLACE FUNCTION public.safe_request("):]
    # la barriera confronta con la modalita' ATTESA per strategia
    assert "v_req_mode <> v_atteso" in corpo
    assert "v_req_mode <> v_ctrl_mode" not in corpo
    # model (con opp_key) e manual (senza) dalla mappa strategy_modes
    assert "'strategy_modes'" in corpo and "'manual'" in corpo and "'model'" in corpo
    # il tetto: live solo se il servizio e' in live
    assert "WHEN v_ctrl_mode = 'live'" in corpo
    # e la barriera sta ancora prima dell'INSERT
    assert corpo.index("v_req_mode <> v_atteso") < corpo.index(
        "INSERT INTO public.safe_strategy_requests")
