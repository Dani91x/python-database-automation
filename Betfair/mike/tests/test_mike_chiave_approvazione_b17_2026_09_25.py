"""25/09 (residui B17) - MIKE: le gambe di un'uscita APPROVATA portano la
CHIAVE dell'approvazione (``meta.approvazione_id`` = id della richiesta
``approva_uscita``), scritta dal SERVIZIO al momento dell'esecuzione.

Prima la scheda della Control Room attribuiva al clic «le righe nuove del bot
sulla partita» (correlazione): una protezione nata nello stesso istante
sarebbe stata presa per l'uscita approvata. La strategia (``engine.py``) non
si tocca: il servizio legge l'approvazione prima del giro e, se il motore la
consuma (telemetria ``uscita_eseguita_su_approvazione`` con la stessa
chiave), annota le sole gambe d'uscita discrezionale nate in quel giro.

Finti: FakeDB/FakeMarket di ``test_mike_service`` (stesse chiavi di mike_*).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.mike.tests.test_mike_service import (NOW, FakeDB, FakeMarket, legs,
                                                  payload, row, run)


def _fino_alla_proposta():
    db = FakeDB(params={"stake": 10, "uscite_automatiche": False})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    return db, mk


def test_la_green_approvata_porta_la_chiave_della_richiesta():
    db, mk = _fino_alla_proposta()
    ingresso = [t for t in db.trades if t["role"] != "under_green"]
    assert ingresso and all("approvazione_id" not in (t.get("meta") or {}) for t in ingresso)
    chiave = db.events["E1"]["ctx"]["uscita_proposta"]["chiave"]
    db.requests.append({"id": 7, "kind": "approva_uscita", "status": "pending",
                        "payload": {"event_id": "E1", "chiave": chiave,
                                    "contesto": {"prezzo_visto": 1.48, "fonte": "canale"}}})
    run(db, mk, NOW + timedelta(seconds=4), [row(payload())])
    assert db.requests[0]["status"] == "done", db.requests[0]["result"]
    assert len([l for l in legs(db) if l["role"] == "under_green"]) == 1
    green = [t for t in db.trades if t["role"] == "under_green"]
    assert len(green) == 1
    assert green[0]["meta"]["approvazione_id"] == 7
    # le righe che NON sono l'uscita approvata non la portano
    for t in db.trades:
        if t["role"] != "under_green":
            assert "approvazione_id" not in (t.get("meta") or {})
    # l'attivita' dice QUALE richiesta e' stata eseguita
    eseguita = [p for k, p, _ in db.activity if k == "uscita_eseguita_su_approvazione"]
    assert eseguita and eseguita[-1]["approvazione_id"] == 7


def test_ad_interruttore_acceso_nessuna_chiave():
    """Parita' col ciclo di sempre: nessuna approvazione, nessuna chiave."""
    db = FakeDB(params={"stake": 10, "uscite_automatiche": True})
    mk = FakeMarket()
    run(db, mk, NOW, [row(payload())])
    run(db, mk, NOW + timedelta(seconds=2), [row(payload())])
    green = [t for t in db.trades if t["role"] == "under_green"]
    assert len(green) == 1 and "approvazione_id" not in green[0]["meta"]


class _D:
    def __init__(self, telemetry):
        self.telemetry = telemetry


def test_approvazione_eseguita_solo_con_la_stessa_chiave():
    prima = {"chiave": "green_pre|c0", "at": 1.0, "request_id": 7}
    assert S._approvazione_eseguita(prima, _D({"uscita_eseguita_su_approvazione":
                                               {"chiave": "green_pre|c0"}})) == 7
    # un'altra chiave, nessuna telemetria, nessuna approvazione: nessuna chiave
    assert S._approvazione_eseguita(prima, _D({"uscita_eseguita_su_approvazione":
                                               {"chiave": "ko_green|c0"}})) is None
    assert S._approvazione_eseguita(prima, _D({})) is None
    assert S._approvazione_eseguita(None, _D({"uscita_eseguita_su_approvazione":
                                              {"chiave": "green_pre|c0"}})) is None
    # un'approvazione scritta prima di oggi (senza request_id): nessuna chiave inventata
    vecchia = {"chiave": "green_pre|c0", "at": 1.0}
    assert S._approvazione_eseguita(vecchia, _D({"uscita_eseguita_su_approvazione":
                                                 {"chiave": "green_pre|c0"}})) is None


@pytest.mark.parametrize("ruolo,atteso", [
    ("under_green", 7), ("ko_green", 7), ("under_close", 7), ("over_close", 7),
    ("reentry_green", 7),
    # coperture e ingressi nati nello stesso giro NON sono l'uscita approvata
    ("over_cover", None), ("under_entry", None),
])
def test_la_chiave_va_solo_sulle_uscite_discrezionali(ruolo, atteso):
    leg = E.Leg(role=ruolo, market="OU35", selection="UNDER", side="back", price=2.0, size=1.0)
    assert S._chiave_gamba(7, leg) == atteso
    assert S._chiave_gamba(None, leg) is None


@pytest.mark.parametrize("v,atteso", [(7, 7), ("9", 9), (0, None), (-1, None),
                                      (True, None), (None, None), ("x", None)])
def test_id_approvazione_mai_inventato(v, atteso):
    assert S._id_approvazione(v) == atteso


def test_trade_row_scrive_la_chiave_solo_se_c_e():
    class Info:
        event_id = "E1"
        event_name = "A v B"

        def selection_id(self, m, s):
            return 11

        def market_id(self, m):
            return "1.9"

        def selection_name(self, m, s):
            return "Under 3.5"

    leg = E.Leg(role="under_green", market="OU35", selection="UNDER", side="lay", price=1.48,
                size=3.0, ref="under_green-0-2")
    con = S._trade_row(Info(), leg, "paper", {"commission_pct": 5.0}, 10, "0-0",
                       approvazione_id=7)
    senza = S._trade_row(Info(), leg, "paper", {"commission_pct": 5.0}, 10, "0-0")
    assert con["meta"]["approvazione_id"] == 7
    assert "approvazione_id" not in senza["meta"]
    # nient'altro cambia nella riga
    assert {k: v for k, v in con.items() if k != "meta"} == {k: v for k, v in senza.items() if k != "meta"}
