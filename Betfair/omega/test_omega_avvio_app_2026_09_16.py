"""OMEGA — FASE A: all'avvio dell'app il bot non opera (16/09/2026).

⚠️ Il reset NON passa da ``omega_activate``: quella RPC riscrive i ``params`` con
``coalesce(p_params,'{}')`` e azzererebbe la configurazione. Qui si usa
``set_control``, che tocca SOLO le colonne passate — e qui si verifica che
``params`` e ``daily_goal`` restino esattamente com'erano.

Il finto e' quello VERO dei test di Omega (``test_omega_service.FakeDB``) e la
riga di controllo si costruisce dalle COLONNE della migrazione.

File ASCII-only.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _closed_snapshot, _cs, _event, _open_snapshot,
)
from Betfair.stream import avvio_app as AA
from Betfair.stream.tests.test_avvio_app_2026_09_16 import riga_control


@pytest.fixture(autouse=True)
def _guardia_pulita():
    S._GUARDIA_AVVIO.azzera()
    yield
    S._GUARDIA_AVVIO.azzera()


PARAMS_VERI = {"engine": "single", "price_min": 20, "price_max": 120,
               "min_stake": 2.0, "daily_loss_stop": 40.0}


def _db(status="running", mode="live", stats=None, params=None) -> FakeDB:
    return FakeDB(riga_control(
        "omega_control", id=1, status=status, mode=mode, daily_goal=250,
        params=json.loads(json.dumps(params or PARAMS_VERI)), stats=stats))


# ---------------------------------------------------------------------------
# (a) avvio nuovo
# ---------------------------------------------------------------------------
def test_a_avvio_nuovo_spegne_e_riporta_in_prova(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(stats={"boot_id": "IERI", "realized_profit": 12.0})
    prima = json.loads(json.dumps(db.control["params"]))

    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)

    assert esito["azzerato"] is True
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"
    assert db.control["params"] == prima            # NESSUN parametro toccato
    assert db.control["daily_goal"] == 250          # e nemmeno l'obiettivo del giorno
    assert db.control["stats"]["boot_id"] == "OGGI"
    assert db.control["stats"]["realized_profit"] == 12.0
    assert db.activity[0][0] == AA.KIND_ATTIVITA
    assert db.activity[0][1]["status_precedente"] == "running"
    assert db.activity[0][1]["mode_precedente"] == "live"


def test_a_dopo_lo_spegnimento_il_ciclo_non_piazza(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = S.run_once(market=market, db=db, now=NOW)
    assert res.get("placed", 0) == 0 and db.trades == []


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
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    assert S.run_once(market=market, db=db, now=NOW)["placed"] == 1


# ---------------------------------------------------------------------------
# (c) ambiente senza APP_BOOT_ID
# ---------------------------------------------------------------------------
def test_c_env_senza_boot_id_e_un_avvio_nuovo(monkeypatch):
    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    db = _db(stats={"boot_id": "IERI"})
    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert esito["azzerato"] is True and esito["boot_id"] == ""
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"


# ---------------------------------------------------------------------------
# (d) posizione aperta + bot fermo: le PROTEZIONI girano
# ---------------------------------------------------------------------------
def test_d_a_bot_fermo_dall_avvio_il_settlement_gira(monkeypatch):
    """Fermare Omega blocca i NUOVI ingressi, non la regolazione dei lay gia'
    piazzati: il trade aperto prima dello spegnimento arriva al settlement."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    S.run_once(market=market, db=db, now=NOW)
    assert len(db.trades) == 1 and db.trades[0]["status"] == "open"

    # l'app viene riaperta: nuovo avvio, il bot si ferma
    db.control["stats"]["boot_id"] = "IERI"
    S._GUARDIA_AVVIO.azzera()
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["status"] == "stopped"

    # il mercato chiude: il settlement DEVE girare comunque
    market._snapshot = _closed_snapshot(winner_id=1)
    res = S.run_once(market=market, db=db, now=NOW + timedelta(hours=2))
    assert res.get("settled") == 1
    assert db.trades[0]["status"] == "won"


def test_d_a_bot_fermo_dall_avvio_le_richieste_manuali_girano(monkeypatch):
    """Il MANUALE gira sempre, anche a bot fermo: e' la fase con cui il trader
    interviene sulle posizioni."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    viste: list[int] = []
    vero = S.process_manual

    def spia(**kw):
        viste.append(1)
        return vero(**kw)

    try:
        S.process_manual = spia
        S.run_once(market=FakeMarket([], _cs(), _open_snapshot()), db=db, now=NOW)
    finally:
        S.process_manual = vero
    assert viste == [1]


# ---------------------------------------------------------------------------
# il timbro e il blocco delle aperture
# ---------------------------------------------------------------------------
def test_il_battito_non_perde_il_boot_id(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "OGGI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    assert db.control["stats"]["boot_id"] == "OGGI"


def test_senza_controllo_concluso_non_si_piazza(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper")
    S._GUARDIA_AVVIO.attiva = True              # controllo non ancora riuscito
    res = S.run_once(market=FakeMarket([_event()], _cs(), _open_snapshot()), db=db, now=NOW)
    assert res.get("placed", 0) == 0 and db.trades == []
