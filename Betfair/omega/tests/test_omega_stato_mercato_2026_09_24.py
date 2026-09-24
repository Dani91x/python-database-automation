# -*- coding: utf-8 -*-
"""D2 (24/09) - OMEGA: lo stato del mercato davanti agli invii che non lo
guardavano (mappa del 24/09).

  * motore v1 (``scan_and_place``): aveva ``snapshot.status`` in mano e non lo
    leggeva -> ``_mercato_in_attesa`` (guardia condivisa, una riga
    ``attesa_riapertura`` per sospensione);
  * cash-out manuale / proposta approvata (``_cashout_prices``, ramo del FEED):
    restituiva i prezzi anche a mercato SOSPESO (quote congelate) -> None, come
    il ramo REST.

Il feed ha le chiavi dello scanner (``cs.status``/``cs.inplay``), lo snapshot e'
il ``MarketSnapshot`` VERO di ``omega_market``. ASCII-only nel codice.
"""
from __future__ import annotations

from typing import Any, List

from Betfair.omega import omega_engine as E
from Betfair.omega import omega_market as M
from Betfair.omega import omega_service as S
from Betfair.stream.trading import stato_mercato as SM


def _payload(status: str) -> dict:
    return {
        "event_name": "Nord v Sud", "inplay": True, "minute": 52,
        "score_home": 1, "score_away": 0,
        "cs": {
            "market_id": "1.777", "status": status, "inplay": True, "total_matched": 500.0,
            "selections": [
                {"selection_id": 2, "name": "3 - 0", "back": 90.0, "lay": 110.0,
                 "back_size": 2, "lay_size": 7.5, "runner_status": "ACTIVE"},
            ],
        },
    }


def _trade() -> dict:
    return {"id": 1, "event_id": "ev1", "market_id": "1.777", "selection_id": 2,
            "side": "lay", "status": "open", "mode": "paper", "price": 110.0,
            "size": 3.0, "meta": {}}


class _Rest:
    def __init__(self) -> None:
        self.calls: List[str] = []

    def read_book(self, market_id: Any, _opts: Any) -> dict:
        self.calls.append(str(market_id))
        return {"status": "SUSPENDED", "runners": []}


def _cashout(monkeypatch, status: str):
    monkeypatch.setattr(S, "_feed_row", lambda eid, hard_max_age=None:
                        (_payload(status), "2026-09-24T20:00:00+00:00"))
    rest = _Rest()
    monkeypatch.setattr(M, "read_book", rest.read_book)
    return S._cashout_prices(M, _trade()), rest


def test_cashout_dal_feed_a_mercato_sospeso_non_da_prezzi(monkeypatch):
    prezzi, rest = _cashout(monkeypatch, "SUSPENDED")
    assert prezzi is None
    assert rest.calls == []          # nessuna chiamata in piu': si sa gia' che e' sospeso


def test_cashout_dal_feed_a_mercato_aperto_prezza_come_prima(monkeypatch):
    prezzi, rest = _cashout(monkeypatch, "OPEN")
    assert prezzi is not None and prezzi["lay"] == 110.0 and rest.calls == []


class _Db:
    def __init__(self) -> None:
        self.righe: List[tuple] = []

    def log(self, kind: str, payload: dict) -> None:
        self.righe.append((kind, payload))


def _snap(status: str) -> M.MarketSnapshot:
    return M.MarketSnapshot(status=status, inplay=True,
                            runners=[E.ScoreRunner(selection_id=2, name="3 - 0")],
                            closed=False, winner_selection_id=None, voided=False)


def test_v1_guardia_una_riga_per_sospensione_e_riapertura():
    db = _Db()
    for _ in range(20):
        assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("SUSPENDED"), "v1") is True
    att = [p for k, p in db.righe if k == SM.KIND_ATTESA]
    assert len(att) == 1 and att[0]["motivo"] == "SUSPENDED" and att[0]["aspetta"] is True
    assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("OPEN"), "v1") is False
    assert S._mercato_in_attesa(db, "ev1", "1.777", _snap("SUSPENDED"), "v1") is True
    assert len([k for k, _ in db.righe if k == SM.KIND_ATTESA]) == 2


def test_v1_stato_mancante_si_passa_come_oggi():
    """Fail-open storico di Omega: irrigidirlo e' una decisione dell'utente."""
    db = _Db()
    snap = _snap(None)  # type: ignore[arg-type] - il campo che manca nella riga
    assert S._mercato_in_attesa(db, "ev2", "1.777", snap, "v1") is False
    assert db.righe == []


def test_svuota_le_cache_dimentica_le_attese():
    db = _Db()
    S._mercato_in_attesa(db, "ev3", "1.777", _snap("SUSPENDED"), "v1")
    S.svuota_le_cache()
    S._mercato_in_attesa(db, "ev3", "1.777", _snap("SUSPENDED"), "v1")
    assert len(db.righe) == 2
