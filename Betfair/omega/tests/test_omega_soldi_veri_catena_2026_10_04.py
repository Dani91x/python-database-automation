"""04/10/2026 - OMEGA: la catena dei soldi veri, stessa condotta di Safe.

Ordine dell'utente («QUESTO PER TUTTI I BOT»): un bot in «soldi veri» con la
catena che non serve il live (runner solo in prova, «Ordini reali» sotto LIVE,
freno) non spara a vuoto e lo DICE:
  * nessun tentativo della gamba consumato (``mode_non_servibile`` era un esito
    di mercato e bruciava ``LEG_RETRY_MAX``);
  * ``stats.motivo_blocco`` con parole da trader;
  * una sola sonda ogni ``X.CATENA_PROVA_S``, nessuna riserva fra una e l'altra;
  * UN CRITICAL per episodio;
  * il REST live rispetta anche il modo EFFETTIVO (prima solo il kill-switch:
    con «Ordini reali» su PAPER il REST di Omega mandava soldi veri).
Finti di ``test_omega_service`` (chiavi vere); freni e modo dalle funzioni vere
(``modo_ordini.dichiara_per_banco``, ``execution._live_brake``).
"""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from Betfair.omega import omega_service as S
from Betfair.omega.test_omega_service import (
    NOW, FakeDB, FakeMarket, _control, _cs, _event, _open_snapshot,
)
from Betfair.safe_strategy import execution as X
from Betfair.stream import modo_ordini as MOD
from Betfair.stream import motore_ordini as MO

ERRORE_MODO = str(MO.Rifiuto(MO.M_MODE, "modo ordini PAPER (scelta dalla Control Room): "
                                       "apertura 'live' RIFIUTATA - si cambia da Control "
                                       "Room, Ordini reali"))


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    monkeypatch.setenv("OMEGA_ORDINI_VIA_CANALE", "0")
    monkeypatch.setenv("LIVE_KILL_SWITCH", "false")
    X._EPISODI_CATENA.clear()
    yield
    X._EPISODI_CATENA.clear()


def _giro(db, market, secondi):
    return S.run_once(market=market, db=db, now=NOW + timedelta(seconds=secondi))


def _canale_che_rifiuta(monkeypatch, chiamate):
    """La strada del canale con il PlaceOutcome VERO di un ack rifiutato."""
    monkeypatch.setattr(S, "_porta_per", lambda params, mode: object())

    def _rifiuta(porta, **kw):
        chiamate.append(kw)
        return X.PlaceOutcome("error", None, 0.0, None, f"canale_rifiutato:{ERRORE_MODO}",
                              size_requested=kw.get("size"), size_remaining=0.0,
                              error_code=ERRORE_MODO)
    monkeypatch.setattr(S, "_place_via_canale", _rifiuta)


def test_canale_mode_non_servibile_non_brucia_e_dichiara(monkeypatch):
    chiamate: list = []
    _canale_che_rifiuta(monkeypatch, chiamate)
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    res = _giro(db, market, 0)
    assert res["placed"] == 0 and len(chiamate) == 1
    assert all(S._leg_attempts("1.100", ph)[0] == 0 for ph in ("ht_cs", "ft_cs", ""))
    motivo = res["stats"].get("motivo_blocco")
    assert motivo and "aperture in soldi veri FERME" in motivo and "Ordini reali" in motivo
    # fra una sonda e l'altra NESSUNA riserva e nessun comando
    righe = len(db.trades)
    _giro(db, market, X.CATENA_PROVA_S - 5)
    assert len(chiamate) == 1 and len(db.trades) == righe
    # scaduta l'attesa: UNA sonda
    _giro(db, market, X.CATENA_PROVA_S + 1)
    assert len(chiamate) == 2


def test_rest_live_rispetta_ordini_reali(monkeypatch, caplog):
    """«Ordini reali» su PAPER: il REST live NON manda soldi veri (prima si')."""
    monkeypatch.setattr(S, "_porta_per", lambda params, mode: None)
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    caplog.set_level(logging.WARNING, logger="omega.service")
    with MOD.dichiara_per_banco("PAPER"):
        for i in range(3):
            res = _giro(db, market, i * (X.CATENA_PROVA_S + 1))
    assert market.placed == [], "nessuna lay REST con «Ordini reali» su PAPER"
    assert "Ordini reali" in str(res["stats"].get("motivo_blocco"))
    assert all(S._leg_attempts("1.100", ph)[0] == 0 for ph in ("ht_cs", "ft_cs", ""))
    critici = [r for r in caplog.records if r.levelno == logging.CRITICAL
               and "apertura REST FERMATA" in r.getMessage()]
    assert len(critici) == 1, "un CRITICAL per episodio"
    # «Ordini reali» torna LIVE: alla sonda successiva la lay parte e il blocco finisce
    res = _giro(db, market, 4 * (X.CATENA_PROVA_S + 1))
    assert market.placed, "con la catena armata Omega opera"
    assert "motivo_blocco" not in res["stats"]


def test_manuale_live_rest_rispetta_ordini_reali():
    db = FakeDB(_control(mode="live"))
    db.manual_reqs = [{
        "id": 1, "kind": "place", "status": "pending",
        "payload": {"event_id": "1.100", "market_id": "m-1.100", "selection_id": 3,
                    "runner_name": "2 - 1", "side": "lay", "mode": "live", "size": 2},
    }]
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    with MOD.dichiara_per_banco("PAPER"):
        S.run_once(market=market, db=db, now=NOW)
    assert market.placed == []
    righe = [t for t in db.trades if (t.get("meta") or {}).get("reason") == "modo_ordini"]
    assert righe and righe[0]["status"] == "error"


def test_ack_senza_motivo_chiude_il_blocco(monkeypatch):
    chiamate: list = []
    _canale_che_rifiuta(monkeypatch, chiamate)
    db = FakeDB(_control(mode="live"))
    market = FakeMarket([_event()], _cs(), _open_snapshot())
    _giro(db, market, 0)
    assert S._motivo_catena_omega()
    monkeypatch.setattr(S, "_place_via_canale", lambda porta, **kw: X.PlaceOutcome(
        "pending", kw.get("price"), kw.get("size"), None, "canale_live:omega-t9",
        size_requested=kw.get("size"), catena_servita=True))
    _giro(db, market, X.CATENA_PROVA_S + 1)
    assert S._motivo_catena_omega() is None


def _evento(ref, fase, errore=None):
    riga = {"market_id": "m-1.100", "selection_id": 3, "side": "lay", "price": 75.0,
            "size": 1.0}
    ev = MO.riga_specchio_da_esito({"ok": errore is None, "action": "place", "mode": "live",
                                    "error": errore}, cust_ref="awlq1", rid=1, mode="live",
                                   riga=riga)
    ev.update({"ref": ref, "seq": 7, "fase": fase, "esito_ms": 1.0})
    if errore:
        ev.update(MO._estremi_errore(errore))
    return ev


@pytest.mark.parametrize("chiude", [False, True])
def test_rifiuto_asincrono_dopo_aggancio(chiude):
    db = FakeDB(_control(mode="live"))
    riga = {"event_id": "E-ag", "market_id": "m-1.100", "selection_id": 3, "side": "lay",
            "mode": "live", "origin": "auto", "status": "pending", "price": 75.0,
            "size": 1.0, "phase": "ft_cs", "liability": 74.0, "pnl": 0.0,
            "meta": {"phase": "reserved", "canale_ref": "omega-t41"}}
    if chiude:
        riga["closes_trade_id"] = 5
    tid = db.insert_trade(riga)
    tr = next(t for t in db.trades if t["id"] == tid)
    for _ in range(2):
        S._chiudi_da_evento(dict(tr), _evento("omega-t41", "rifiutato", ERRORE_MODO),
                            db=db, mode="live", min_stake=1.0, now=NOW)
    rif = [p for k, p in db.activity if k == "canale_rifiutato"]
    if chiude:
        assert rif == [] and S._motivo_catena_omega() is None, "una chiusura non blocca"
        return
    assert [p["critical"] for p in rif] == [True, False], "un CRITICAL per episodio"
    assert S._motivo_catena_omega()
    assert S._leg_attempts("E-ag", "ft_cs")[0] == 0
