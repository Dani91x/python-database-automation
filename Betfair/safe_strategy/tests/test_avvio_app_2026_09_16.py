"""SAFE — FASE A: all'avvio dell'app il bot non opera (16/09/2026).

Oltre a stato e modalita', per Safe si azzerano le modalita' PER STRATEGIA
(``params.strategy_modes``): e' l'unica chiave di ``params`` che il controllo
d'avvio puo' toccare, e non e' strategia — e' *con che soldi*. Ogni altra
chiave deve restare identica byte per byte, e qui lo si verifica con un
confronto JSON.

Il finto e' quello VERO dei test di Safe (``test_bot_service.FakeDB``) e la riga
di controllo si costruisce dalle COLONNE della migrazione.

File ASCII-only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from Betfair.safe_strategy import bot_service as S
from Betfair.safe_strategy.tests.test_bot_service import (
    NOW, FakeDB, FakeEngine, FakeMarket, _feed_row, _reset_module_state, _signal,
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


#: parametri REALI come li scrive la UI: le quattro strategie con la loro
#: modalita', piu' le chiavi money-critical che NON si devono toccare.
PARAMS_VERI = {
    "variants": ["base", "esatto", "punta", "tennis"],
    "strategy_modes": {"base": "live", "esatto": "paper", "punta": "live", "tennis": "live"},
    "stake": {"backSize": 3, "laySize": 10},
    "max_liability_per_trade": 25.0,
    "daily_loss_stop": 50.0,
    "exits": {"greenUpAt": 0.6},
}


def _db(status="running", mode="live", params=None, stats=None) -> FakeDB:
    db = FakeDB(status=status, mode=mode)
    db.control = riga_control("safe_strategy_control", id=1, status=status, mode=mode,
                              params=json.loads(json.dumps(params or PARAMS_VERI)),
                              stats=stats)
    return db


# ---------------------------------------------------------------------------
# (a) avvio nuovo
# ---------------------------------------------------------------------------
def test_a_avvio_nuovo_spegne_tutto_e_riporta_le_4_strategie_in_prova(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(stats={"boot_id": "IERI", "realized_today": 2.0})
    prima = json.loads(json.dumps(db.control["params"]))

    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)

    assert esito["azzerato"] is True
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"
    assert db.control["params"]["strategy_modes"] == {
        "base": "paper", "esatto": "paper", "punta": "paper", "tennis": "paper"}
    # OGNI ALTRA CHIAVE IDENTICA: confronto byte per byte sul resto di params
    dopo = json.loads(json.dumps(db.control["params"]))
    prima.pop("strategy_modes"), dopo.pop("strategy_modes")
    assert json.dumps(prima, sort_keys=True) == json.dumps(dopo, sort_keys=True)
    # l'attivita' elenca che cosa era in live
    kind, payload = db.activity[0]
    assert kind == AA.KIND_ATTIVITA
    assert payload["strategy_modes_live"] == ["base", "punta", "tennis"]
    assert payload["mode_precedente"] == "live"


def test_a_nessuna_strategia_in_live_nessuna_scrittura_di_params(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    params = json.loads(json.dumps(PARAMS_VERI))
    params["strategy_modes"] = {k: "paper" for k in params["strategy_modes"]}
    db = _db(status="running", mode="paper", params=params, stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"] == params           # nemmeno una riscrittura inutile


def test_a_mappa_strategy_modes_assente_resta_assente(monkeypatch):
    """La mappa VUOTA e' legittima («vale il mode del control per tutti»): non si
    inventa una mappa che l'utente non ha mai scritto."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="live", params={"stake": {"backSize": 3}},
             stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["params"] == {"stake": {"backSize": 3}}
    assert db.control["mode"] == "paper"            # e il tetto e' comunque paper


def test_a_dopo_lo_spegnimento_il_ciclo_non_piazza(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    db.scan_rows = [_feed_row()]
    res = S.run_once(db=db, market=FakeMarket(), engine=FakeEngine([_signal()]), now=NOW)
    assert res["placed"] == 0 and db.trades == []


# ---------------------------------------------------------------------------
# (b) stesso avvio: riavvio dal watchdog
# ---------------------------------------------------------------------------
def test_b_stesso_boot_id_non_scrive_niente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(stats={"boot_id": "OGGI"})
    prima = json.loads(json.dumps(db.control))
    assert S.ferma_al_nuovo_avvio(db=db, now=NOW) is None
    assert json.loads(json.dumps(db.control)) == prima
    assert db.activity == []


def test_b_il_bot_acceso_dall_utente_continua_a_piazzare(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    S._GUARDIA_AVVIO.attiva = True              # come in ``main()``
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    db.scan_rows = [_feed_row()]
    res = S.run_once(db=db, market=FakeMarket(), engine=FakeEngine([_signal()]), now=NOW)
    assert res["placed"] == 1


# ---------------------------------------------------------------------------
# (c) ambiente senza APP_BOOT_ID
# ---------------------------------------------------------------------------
def test_c_env_senza_boot_id_e_un_avvio_nuovo(monkeypatch):
    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    db = _db(stats={"boot_id": "IERI"})
    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert esito["azzerato"] is True and esito["boot_id"] == ""
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"
    assert set(db.control["params"]["strategy_modes"].values()) == {"paper"}


# ---------------------------------------------------------------------------
# (d) posizione aperta + bot fermo: le PROTEZIONI girano
# ---------------------------------------------------------------------------
def test_d_a_bot_fermo_dall_avvio_il_cash_out_del_trader_gira(monkeypatch):
    """Fermare toglie le APERTURE, non le uscite: una posizione gia' a mercato
    deve poter essere chiusa anche subito dopo lo spegnimento d'avvio."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    db.scan_rows = [_feed_row()]
    # il bot dell'utente apre la posizione (stesso avvio: nessuno lo spegne)
    S.run_once(db=db, market=FakeMarket(), engine=FakeEngine([_signal()]), now=NOW)
    assert len(db.trades) == 1 and db.trades[0]["status"] == "open"

    # l'app viene riaperta: nuovo avvio, il bot si ferma
    db.control["stats"]["boot_id"] = "IERI"
    S._GUARDIA_AVVIO.azzera()
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["status"] == "stopped"

    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"trade_id": db.trades[0]["id"]}})
    res = S.run_once(db=db, market=FakeMarket(), now=NOW)
    assert res["requests"] == 1
    assert db.requests[0]["status"] != "pending"   # lavorata, non ignorata


def test_d_a_bot_fermo_dall_avvio_le_uscite_automatiche_girano(monkeypatch):
    """``process_exits`` riceve le posizioni vive anche a bot fermo: il ciclo le
    guarda tutte, in qualunque modalita' siano state aperte."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    db.scan_rows = [_feed_row()]
    S.run_once(db=db, market=FakeMarket(), engine=FakeEngine([_signal()]), now=NOW)
    db.control["stats"]["boot_id"] = "IERI"
    S._GUARDIA_AVVIO.azzera()
    S.ferma_al_nuovo_avvio(db=db, now=NOW)

    viste: list[int] = []
    vero_exits = S.process_exits

    def spia(**kw):
        viste.append(len(kw.get("open_rows") or []))
        return vero_exits(**kw)

    try:
        S.process_exits = spia
        S.run_once(db=db, market=FakeMarket(), now=NOW)
    finally:
        S.process_exits = vero_exits
    assert viste and viste[0] == 1                # la posizione aperta e' stata guardata


# ---------------------------------------------------------------------------
# il timbro e il blocco delle aperture
# ---------------------------------------------------------------------------
def test_il_battito_non_perde_il_boot_id(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    db.scan_rows = [_feed_row()]
    S.run_once(db=db, market=FakeMarket(), now=NOW)
    assert db.control["stats"]["boot_id"] == "OGGI"


def test_senza_controllo_concluso_non_si_piazza(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper")
    S._GUARDIA_AVVIO.attiva = True              # controllo non ancora riuscito
    db.scan_rows = [_feed_row()]
    res = S.run_once(db=db, market=FakeMarket(), engine=FakeEngine([_signal()]), now=NOW)
    assert res["placed"] == 0


# ---------------------------------------------------------------------------
# la funzione pura che tocca SOLO strategy_modes
# ---------------------------------------------------------------------------
def test_strategy_modes_a_paper_non_tocca_nient_altro():
    patched, live = S.strategy_modes_a_paper(PARAMS_VERI)
    assert live == ["base", "punta", "tennis"]
    assert patched["strategy_modes"] == {k: "paper" for k in PARAMS_VERI["strategy_modes"]}
    for k, v in PARAMS_VERI.items():
        if k != "strategy_modes":
            assert patched[k] == v
    assert PARAMS_VERI["strategy_modes"]["base"] == "live"   # l'originale non muta


def test_strategy_modes_a_paper_ignora_i_params_non_mappa():
    assert S.strategy_modes_a_paper(None) == (None, [])
    assert S.strategy_modes_a_paper({"stake": 3}) == (None, [])
    assert S.strategy_modes_a_paper({"strategy_modes": {}}) == (None, [])
