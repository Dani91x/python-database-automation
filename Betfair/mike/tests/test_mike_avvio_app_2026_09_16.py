"""MIKE — FASE A: all'avvio dell'app il bot non opera (16/09/2026).

Il finto e' quello VERO dei test di Mike (``test_mike_service.FakeDB``, che e'
lo specchio in memoria delle tabelle ``mike_*``), e la riga di controllo si
costruisce dalle COLONNE della migrazione (``riga_control``): nessuna chiave
scritta a memoria.

File ASCII-only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_feed import payload, row
from Betfair.mike.tests.test_mike_service import FakeDB, FakeMarket
from Betfair.stream import avvio_app as AA
from Betfair.stream.tests.test_avvio_app_2026_09_16 import riga_control

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _guardia_pulita():
    """La guardia vive per PROCESSO: senza azzerarla un test erediterebbe lo
    stato del precedente."""
    S._GUARDIA_AVVIO.azzera()
    yield
    S._GUARDIA_AVVIO.azzera()


def _db(status="running", mode="live", params=None, stats=None) -> FakeDB:
    db = FakeDB(status=status, mode=mode, params=params or {"stake": 5})
    # la riga vera ha TUTTE le colonne di mike_control, non solo le quattro che
    # servono al ciclo: il finto deve parlare come il vero.
    db.control = riga_control("mike_control", id=1, status=status, mode=mode,
                              params=params or {"stake": 5}, stats=stats)
    return db


# ---------------------------------------------------------------------------
# (a) avvio nuovo
# ---------------------------------------------------------------------------
def test_a_avvio_nuovo_spegne_e_riporta_in_prova(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="live", params={"stake": 5, "max_open_matches": 2},
             stats={"boot_id": "IERI", "realized_today": 7.5})
    prima = dict(db.control["params"])

    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)

    assert esito["azzerato"] is True
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"
    assert db.control["params"] == prima            # nessun parametro toccato
    assert db.control["stats"]["boot_id"] == "OGGI"
    assert db.control["stats"]["realized_today"] == 7.5
    assert db.control["stats"]["fermato_all_avvio_at"] == NOW.isoformat()
    kind, payload_log, _ev = db.activity[0]
    assert kind == AA.KIND_ATTIVITA
    assert payload_log["status_precedente"] == "running"
    assert payload_log["mode_precedente"] == "live"


def test_a_il_ciclo_dopo_non_apre_niente(monkeypatch):
    """Dopo lo spegnimento d'avvio il ciclo vero legge 'stopped' e non arma
    nessuna partita nuova, anche con una candidata perfetta sul feed."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    res = S.run_once(db=db, market=FakeMarket(), now=NOW, rows=[row(payload())], atlas=None)
    assert res["new"] == 0 and db.events == {}


# ---------------------------------------------------------------------------
# (b) stesso avvio: riavvio dal watchdog
# ---------------------------------------------------------------------------
def test_b_stesso_boot_id_non_scrive_niente(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="live", stats={"boot_id": "OGGI"})
    assert S.ferma_al_nuovo_avvio(db=db, now=NOW) is None
    assert db.control["status"] == "running" and db.control["mode"] == "live"
    assert db.activity == []


def test_b_il_bot_acceso_sopravvive_al_crash_e_continua_ad_aprire(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", params={"stake": 10},
             stats={"boot_id": "OGGI"})
    S._GUARDIA_AVVIO.attiva = True              # come in ``main()``
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    res = S.run_once(db=db, market=FakeMarket(), now=NOW, rows=[row(payload())], atlas=None)
    assert res["new"] == 1                      # il bot dell'utente e' ancora vivo


# ---------------------------------------------------------------------------
# (c) ambiente senza APP_BOOT_ID
# ---------------------------------------------------------------------------
def test_c_env_senza_boot_id_e_un_avvio_nuovo(monkeypatch):
    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    db = _db(status="running", mode="live", stats={"boot_id": "IERI"})
    esito = S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert esito["azzerato"] is True and esito["boot_id"] == ""
    assert db.control["status"] == "stopped" and db.control["mode"] == "paper"
    assert "APP_BOOT_ID assente" in esito["motivo"]


def test_c_due_avvii_senza_id_restano_due_avvii_diversi(monkeypatch):
    """Fail-closed: salvato vuoto e corrente vuoto NON sono «lo stesso avvio»."""
    monkeypatch.delenv(AA.ENV_BOOT_ID, raising=False)
    db = _db(status="running", mode="live", stats={"boot_id": "IERI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["stats"]["boot_id"] == ""
    db.control["status"], db.control["mode"] = "running", "live"
    S._GUARDIA_AVVIO.azzera()                   # nuovo processo
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["status"] == "stopped"


# ---------------------------------------------------------------------------
# (d) posizione aperta + bot fermo: le PROTEZIONI girano
# ---------------------------------------------------------------------------
def test_d_posizione_aperta_a_bot_fermo_le_uscite_girano(monkeypatch):
    """Il bot viene fermato all'avvio MENTRE una partita ha gia' una gamba
    aperta: il green-up deve continuare a essere gestito. Fermare toglie le
    APERTURE, mai le uscite."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", params={"stake": 10},
             stats={"boot_id": "OGGI"})
    mk = FakeMarket()
    # il bot dell'utente apre la posizione (stesso avvio: nessuno lo spegne)
    S.run_once(db=db, market=mk, now=NOW, rows=[row(payload())], atlas=None)
    assert db.events["E1"]["state"] == "PRE_ENTRY_PENDING"

    # ora l'app viene riaperta: nuovo avvio, il bot si ferma
    db.control["stats"]["boot_id"] = "IERI"
    S._GUARDIA_AVVIO.azzera()
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    assert db.control["status"] == "stopped"

    # la partita gia' avviata continua a essere lavorata: la gamba di uscita
    # viene appoggiata come se il bot fosse acceso.
    res = S.run_once(db=db, market=mk, now=NOW + timedelta(seconds=2),
                     rows=[row(payload())], atlas=None)
    assert db.events["E1"]["state"] == "PRE_OPEN"
    green = [l for l in db.events["E1"]["positions"] if l["role"] == "under_green"]
    assert green and green[0]["status"] == "pending"
    assert res["new"] == 0                      # ma nessuna partita NUOVA


def test_d_a_bot_fermo_le_richieste_della_ui_girano(monkeypatch):
    """Il cash out chiesto dal trader e' una PROTEZIONE: deve essere lavorato
    anche a bot fermo dall'avvio dell'app."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", params={"stake": 10},
             stats={"boot_id": "OGGI"})
    mk = FakeMarket()
    S.run_once(db=db, market=mk, now=NOW, rows=[row(payload())], atlas=None)
    db.control["stats"]["boot_id"] = "IERI"
    S._GUARDIA_AVVIO.azzera()
    S.ferma_al_nuovo_avvio(db=db, now=NOW)

    db.requests.append({"id": 1, "kind": "cashout", "status": "pending",
                        "payload": {"event_id": "E1"}})
    res = S.run_once(db=db, market=mk, now=NOW + timedelta(seconds=2),
                     rows=[row(payload())], atlas=None)
    assert res["requests"] == 1
    assert db.requests[0]["status"] in ("done", "error")


# ---------------------------------------------------------------------------
# il timbro: l'id non deve sparire al primo battito
# ---------------------------------------------------------------------------
def test_il_battito_non_perde_il_boot_id(monkeypatch):
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", params={"stake": 10},
             stats={"boot_id": "OGGI"})
    S.ferma_al_nuovo_avvio(db=db, now=NOW)
    S.run_once(db=db, market=FakeMarket(), now=NOW, rows=[row(payload())], atlas=None)
    assert db.control["stats"]["boot_id"] == "OGGI"


def test_senza_controllo_concluso_non_si_apre(monkeypatch):
    """Database muto in avvio: la guardia resta chiusa e il ciclo non apre
    niente, anche se la riga dice 'running'."""
    monkeypatch.setenv(AA.ENV_BOOT_ID, "OGGI")
    db = _db(status="running", mode="paper", params={"stake": 10})
    S._GUARDIA_AVVIO.attiva = True              # come in ``main()``, controllo non fatto
    res = S.run_once(db=db, market=FakeMarket(), now=NOW, rows=[row(payload())], atlas=None)
    assert res["new"] == 0
