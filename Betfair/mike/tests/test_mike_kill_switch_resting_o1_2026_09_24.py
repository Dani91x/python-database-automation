"""O1 (24/09) - la lay appoggiata di Mike e il kill-switch condiviso.

``_piazza_resting_live`` chiama ``market.place_order_live`` DIRETTO, senza
passare da ``X.place`` (che ha ``_live_brake``): era l'unica strada REST di
Mike senza freno. Oggi le appoggiate sono tutte coperture (ruoli ``*_green``),
cioe' CHIUSURE, e a freno tirato devono poter partire; un'appoggiata che
APRISSE (ruolo non ``*_green`` e nessuna riga chiusa) viene fermata prima di
scrivere la riserva.

Finti presi da ``test_mike_loop_resting_2026_09_15`` (``PlaceResult`` vero).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from Betfair.mike import engine as E
from Betfair.mike import service as S
from Betfair.omega.omega_market import PlaceResult
from Betfair.stream.trading import controls as CTL


class _Db:
    def __init__(self):
        self.righe: list = []
        self.log_righe: list = []
        self._id = 2000

    def trades_for_event(self, event_id, **_kw):
        return list(self.righe)

    def insert_trade(self, row, **_kw):
        self._id += 1
        self.righe.append({**row, "id": self._id})
        return self._id

    def update_trade(self, trade_id, **campi):
        for r in self.righe:
            if r.get("id") == trade_id:
                r.update(campi)
        return True

    def log(self, kind, payload=None, event_id=None):
        self.log_righe.append((kind, payload or {}))


def _info():
    return SimpleNamespace(event_id="E1", event_name="Casa v Ospiti",
                           market_id=lambda m: "1.1", selection_id=lambda m, s: 1,
                           selection_name=lambda m, s: "Under 3.5 Goals")


def _gamba(ruolo="under_green"):
    return E.Leg(ref=f"{ruolo}-0-1", role=ruolo, market=E.MARKET_OU35,
                 selection=E.SEL_UNDER, side="lay", price=1.43, size=5.07, cycle_no=0)


def _piazza(leg, *, chiude=None):
    db, piazzati = _Db(), []

    def _place(**kw):
        piazzati.append(kw)
        return PlaceResult(ok=True, order_status="EXECUTABLE", bet_id="777",
                           size_matched=0.0, avg_price_matched=None, raw={})

    S._piazza_resting_live(db=db, market=SimpleNamespace(place_order_live=_place),
                           info=_info(), leg=leg, mode="live", params={}, minuto=10,
                           score="0-0", chiude=chiude, motivo=None, ev={"event_id": "E1"})
    return db, piazzati


@pytest.fixture
def kill(monkeypatch):
    def _imposta(sorgente):
        monkeypatch.setenv("LIVE_KILL_SWITCH", "true" if sorgente == "env" else "false")
        monkeypatch.setattr(CTL, "get_live_settings",
                            lambda *a, **k: {"kill_switch": sorgente == "db"})
    return _imposta


@pytest.mark.parametrize("sorgente", ["env", "db"])
@pytest.mark.parametrize("ruolo", ["under_green", "reentry_green", "ko_green"])
def test_kill_attivo_la_copertura_appoggiata_parte_lo_stesso(kill, sorgente, ruolo):
    kill(sorgente)
    db, piazzati = _piazza(_gamba(ruolo))
    assert len(piazzati) == 1, "una copertura e' una chiusura: il freno non la ferma"
    assert not [p for k, p in db.log_righe if p.get("reason") == "kill_switch"]


@pytest.mark.parametrize("sorgente", ["env", "db"])
def test_kill_attivo_un_apertura_appoggiata_si_ferma_senza_riserva(kill, sorgente):
    kill(sorgente)
    leg = _gamba("entry")                    # ruolo che non copre niente
    db, piazzati = _piazza(leg)
    assert piazzati == []
    assert db.righe == [], "nessuna riserva scritta per un ordine che non parte"
    assert leg.status == "cancelled"
    motivo = ("live_kill_switch_attivo" if sorgente == "env" else "db_kill_switch_attivo")
    saltati = [p for k, p in db.log_righe if k == "place_saltato"]
    assert saltati and saltati[0]["reason"] == "kill_switch" and saltati[0]["motivo"] == motivo


def test_kill_attivo_un_apertura_che_dichiara_cosa_chiude_passa(kill):
    kill("db")
    db, piazzati = _piazza(_gamba("entry"), chiude=41)
    assert len(piazzati) == 1


def test_kill_spento_parita(kill):
    kill(None)
    for ruolo in ("under_green", "entry"):
        db, piazzati = _piazza(_gamba(ruolo))
        assert len(piazzati) == 1
        assert piazzati[0]["fill_or_kill"] is False and piazzati[0]["side"] == "lay"
        assert piazzati[0]["customer_ref"] == f"mike-t{db.righe[0]['id']}"


def test_resting_e_chiusura():
    assert S._resting_e_chiusura(_gamba("under_green"), None) is True
    assert S._resting_e_chiusura(_gamba("entry"), None) is False
    assert S._resting_e_chiusura(_gamba("entry"), 7) is True
